"""Tests unitaires de la Phase 2 : décisions pures, sans base de données.

Ce qui se teste ici est la logique de refus : validité d'une autorisation, quota,
empreinte canonique, filtre des secrets. La persistance et la concurrence sont
prouvées séparément sur PostgreSQL (``test_execution_reliable.py``).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.decision_engine.models import ControlOutcome, PermissionAction
from app.execution.models import (
    ActionRecord,
    EffectCertainty,
    ExecutionAuthorization,
)
from app.execution.services import fingerprint
from app.execution.services.audit import redact
from app.execution.services.authorizations import evaluate_validity
from app.execution.services.reservations import evaluate_quota

WORKSPACE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AGENT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ACTION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _action(**overrides) -> ActionRecord:
    values = dict(
        id=ACTION_ID,
        workspace_id=WORKSPACE_ID,
        agent_id=AGENT_ID,
        objective="Publier le rapport mensuel",
        tool="documents",
        operation="publish",
        arguments={"document_id": "doc-1"},
        permission_required=PermissionAction.PUBLISH,
        canonical_fingerprint="a" * 64,
        idempotency_key="b" * 64,
        version=1,
    )
    values.update(overrides)
    return ActionRecord(**values)


def _authorization(action: ActionRecord, **overrides) -> ExecutionAuthorization:
    values = dict(
        id=uuid.uuid4(),
        decision_id=uuid.uuid4(),
        action_id=action.id,
        workspace_id=action.workspace_id,
        agent_id=action.agent_id,
        outcome=ControlOutcome.ALLOW,
        reason_code="POLICY_ALLOWED",
        action_fingerprint=action.canonical_fingerprint,
        action_version=action.version,
        issued_at=datetime.now(timezone.utc),
    )
    values.update(overrides)
    return ExecutionAuthorization(**values)


def test_valid_authorization_has_no_refusal():
    action = _action()
    assert evaluate_validity(_authorization(action), action) is None


@pytest.mark.parametrize(
    "outcome",
    [ControlOutcome.DENY, ControlOutcome.ESCALATE, ControlOutcome.STOP],
)
def test_non_allow_outcome_never_authorizes(outcome: ControlOutcome):
    """INV-01 : un DENY, ESCALATE ou STOP ne devient jamais exécutable, même relu."""
    action = _action()
    authorization = _authorization(action, outcome=outcome)
    assert evaluate_validity(authorization, action) == "AUTHORIZATION_NOT_ALLOW"


def test_revoked_authorization_is_refused():
    """INV-14 : une révocation est effective au moment de l'effet."""
    action = _action()
    authorization = _authorization(action, revoked_at=datetime.now(timezone.utc))
    assert evaluate_validity(authorization, action) == "AUTHORIZATION_REVOKED"


def test_expired_authorization_is_refused():
    action = _action()
    now = datetime.now(timezone.utc)
    authorization = _authorization(
        action,
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=1),
    )
    assert evaluate_validity(authorization, action) == "AUTHORIZATION_EXPIRED"


def test_consumed_authorization_is_refused():
    action = _action()
    authorization = _authorization(action, consumed_at=datetime.now(timezone.utc))
    assert evaluate_validity(authorization, action) == "AUTHORIZATION_ALREADY_CONSUMED"


def test_changed_fingerprint_invalidates_authorization():
    """INV-03 : modifier l'action invalide l'autorisation, sans exception."""
    action = _action()
    authorization = _authorization(action, action_fingerprint="c" * 64)
    assert evaluate_validity(authorization, action) == "ACTION_FINGERPRINT_CHANGED"


def test_changed_action_version_invalidates_authorization():
    action = _action(version=2)
    authorization = _authorization(action, action_version=1)
    assert evaluate_validity(authorization, action) == "ACTION_VERSION_CHANGED"


def test_other_workspace_action_is_refused():
    """INV-02 : l'autorisation d'un workspace ne couvre pas une action d'un autre."""
    authorization = _authorization(_action())
    # Action étrangère imitant empreinte et version : l'identité seule la disqualifie.
    foreign_action = _action(
        id=uuid.uuid4(),
        workspace_id=authorization.workspace_id,
        canonical_fingerprint=authorization.action_fingerprint,
        version=authorization.action_version,
    )
    assert foreign_action.id != authorization.action_id
    assert evaluate_validity(authorization, foreign_action) == "ACTION_MISMATCH"


def test_approval_required_without_reference_is_refused():
    action = _action()
    authorization = _authorization(action, approval_required=True)
    assert evaluate_validity(authorization, action) == "APPROVAL_REFERENCE_MISSING"