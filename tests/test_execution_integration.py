"""Phase 2 — tests d'intégration sur PostgreSQL réel.

Le contrat (§10) exige que les garanties de persistance soient prouvées sur la
base : verrous, contraintes, unicité, trigger append-only. Aucun mock sur la couche
persistance ; seuls les handlers d'outils sont des coroutines factices contrôlées.

Invariants couverts : INV-01, INV-02, INV-03, INV-08, INV-09, INV-10, INV-11,
INV-14, INV-16.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.decision_engine.models import ControlOutcome
from app.execution.models import (
    ActionReservation,
    AttemptStatus,
    AuditEntry,
    AuditEventType,
    EffectCertainty,
    ExecutionAttempt,
    ExecutionAuthorization,
    ReservationStatus,
    ResourceBudget,
)
from app.execution.services import attempts as attempts_service
from app.execution.services import audit, authorizations, fingerprint, reservations
from app.execution.services.authorizations import AuthorizationError
from app.execution.services.executor import ExecutionResult
from app.execution.services.reliable_executor import (
    dispatch_authorized_action,
    reconcile_unknown_attempt,
)

from tests.conftest import make_action, make_decision


@pytest_asyncio.fixture
async def authorized_action(db_session, workspace_agent):
    """Décision ``ALLOW``, action structurée et autorisation émise, prêts à consommer."""
    workspace, agent = workspace_agent
    decision = make_decision(workspace_id=workspace.id, agent_id=agent.id)
    db_session.add(decision)
    await db_session.flush()

    action = make_action(
        workspace_id=workspace.id,
        agent_id=agent.id,
        decision_id=decision.id,
    )
    db_session.add(action)
    await db_session.flush()

    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor="test-suite"
    )
    return workspace, agent, decision, action, authorization


async def _ok_handler(action) -> ExecutionResult:
    """Handler factice : effet confirmé, sans ambiguïté."""
    return ExecutionResult(
        success=True,
        output=f"read {action.arguments['document_id']}",
        error=None,
        provider_reference="prov-evt-ok-1",
    )


async def _exploding_handler(action) -> ExecutionResult:
    """Échec réseau après engagement : l'effet est incertain, jamais un échec franc."""
    raise RuntimeError("network partition after request sent")


@pytest.mark.asyncio
async def test_end_to_end_allow_runs_without_confirmation(
    db_session, authorized_action
):
    """INV-16 : une action préautorisée conforme s'exécute sans confirmation."""
    workspace, agent, decision, action, authorization = authorized_action

    outcome = await dispatch_authorized_action(
        db_session,
        action=action,
        authorization_id=authorization.id,
        actor="worker-1",
        lease_owner="worker-1",
        handler=_ok_handler,
    )

    assert outcome.effect is EffectCertainty.confirmed
    assert outcome.success is True
    assert outcome.output == "read doc-1"

    attempt = await db_session.get(ExecutionAttempt, outcome.attempt_id)
    assert attempt.status is AttemptStatus.SUCCEEDED
    assert attempt.attempt_number == 1

    refreshed = await db_session.get(ExecutionAuthorization, authorization.id)
    assert refreshed.consumed_at is not None


@pytest.mark.asyncio
async def test_non_allow_decision_never_issues_authorization(
    db_session, workspace_agent
):
    """INV-01 : aucun ``STOP`` ne devient exécutable, quelle que soit la pression."""
    workspace, agent = workspace_agent
    decision = make_decision(
        workspace_id=workspace.id,
        agent_id=agent.id,
        outcome=ControlOutcome.STOP,
        reason_code="EMERGENCY_STOP_ACTIVE",
    )
    db_session.add(decision)
    await db_session.flush()

    action = make_action(workspace_id=workspace.id, agent_id=agent.id)
    db_session.add(action)
    await db_session.flush()

    with pytest.raises(AuthorizationError) as excinfo:
        await authorizations.issue_authorization(
            db_session, decision=decision, action=action, actor="test-suite"
        )
    assert excinfo.value.code == "CONTROL_STOP"

    entries = (
        await db_session.execute(
            select(AuditEntry).where(
                AuditEntry.event_type == AuditEventType.AUTHORIZATION_REJECTED,
                AuditEntry.workspace_id == workspace.id,
            )
        )
    ).scalars().all()
    assert len(entries) == 1
    assert entries[0].reason_code == "CONTROL_STOP"


@pytest.mark.asyncio
async def test_revoked_authorization_is_never_consumed(db_session, authorized_action):
    """INV-14 : une autorisation révoquée est refusée au moment de l'effet."""
    workspace, agent, decision, action, authorization = authorized_action

    await authorizations.revoke_authorization(
        db_session,
        authorization_id=authorization.id,
        reason="OWNER_REQUESTED",
        actor="owner",
    )

    with pytest.raises(AuthorizationError) as excinfo:
        await authorizations.consume_authorization(
            db_session,
            authorization_id=authorization.id,
            action=action,
            actor="worker-1",
        )
    assert excinfo.value.code == "AUTHORIZATION_REVOKED"


@pytest.mark.asyncio
async def test_expired_authorization_is_never_consumed(db_session, authorized_action):
    """INV-14 : une autorisation expirée n'est pas consommable."""
    workspace, agent, decision, action, authorization = authorized_action

    stale = await authorizations.issue_authorization(
        db_session,
        decision=decision,
        action=action,
        actor="test-suite",
        ttl_seconds=0,
    )
    with pytest.raises(AuthorizationError) as excinfo:
        await authorizations.consume_authorization(
            db_session,
            authorization_id=stale.id,
            action=action,
            actor="worker-1",
        )
    assert excinfo.value.code == "AUTHORIZATION_EXPIRED"


@pytest.mark.asyncio
async def test_modified_action_breaks_authorization(db_session, authorized_action):
    """INV-03 : l'action arbitrée est immuable ; la modifier invalide le droit."""
    workspace, agent, decision, action, authorization = authorized_action

    # Mutation post-arbitrage : nouveaux arguments, nouvelle empreinte, nouvelle version.
    action.arguments = {"document_id": "doc-2"}
    action.canonical_fingerprint = fingerprint.compute_fingerprint(
        workspace_id=action.workspace_id,
        agent_id=action.agent_id,
        tool=action.tool,
        operation=action.operation,
        permission_required=action.permission_required,
        objective=action.objective,
        arguments=action.arguments,
    )
    action.version += 1
    await db_session.flush()

    with pytest.raises(AuthorizationError) as excinfo:
        await authorizations.consume_authorization(
            db_session,
            authorization_id=authorization.id,
            action=action,
            actor="worker-1",
        )
    assert excinfo.value.code == "ACTION_FINGERPRINT_CHANGED"


@pytest.mark.asyncio
async def test_authorization_is_single_use(db_session, authorized_action):
    """INV-14 : une autorisation ne se consomme pas deux fois."""
    workspace, agent, decision, action, authorization = authorized_action

    consumed = await authorizations.consume_authorization(
        db_session,
        authorization_id=authorization.id,
        action=action,
        actor="worker-1",
    )
    assert consumed.consumed_at is not None

    with pytest.raises(AuthorizationError) as excinfo:
        await authorizations.consume_authorization(
            db_session,
            authorization_id=authorization.id,
            action=action,
            actor="worker-2",
        )
    assert excinfo.value.code == "AUTHORIZATION_ALREADY_CONSUMED"