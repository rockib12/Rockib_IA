"""Phase 2 sur PostgreSQL réel : autorisation, exécution fiable, audit.

Le contrat (§10) exige que les garanties de persistance soient prouvées sur la base :
verrous, contraintes, trigger append-only et concurrence. Les mocks ne prouvent rien
ici ; chaque test crée son workspace et le supprime en sortie (cascade complète).
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.decision_engine.models import ControlOutcome, PermissionAction
from app.execution.models import (
    ActionReservation,
    AuditEntry,
    AuditEventType,
    EffectCertainty,
    ExecutionAttempt,
    ExecutionResultRecord,
    ReservationStatus,
    ResourceBudget,
)
from app.execution.services import attempts as attempts_service
from app.execution.services import authorizations, reservations
from app.execution.services.authorizations import AuthorizationError
from app.execution.services.executor import ExecutionResult
from app.execution.services.reliable_executor import (
    dispatch_authorized_action,
    reconcile_unknown_attempt,
)

from tests.conftest import make_action, make_decision

pytestmark = pytest.mark.asyncio

ACTOR = "phase2-test"


async def _stage(db, workspace, agent, *, permission=PermissionAction.PUBLISH):
    """Persiste une décision autorisée et son action structurée (empreinte canonique)."""
    decision = make_decision(
        workspace_id=workspace.id,
        agent_id=agent.id,
        permission_action=permission,
    )
    db.add(decision)
    await db.flush()

    action = make_action(
        workspace_id=workspace.id,
        agent_id=agent.id,
        decision_id=decision.id,
        permission_action=permission,
        idempotency_scope=f"stage-{uuid.uuid4().hex}",
    )
    db.add(action)
    await db.flush()
    return decision, action


async def test_full_allow_flow_end_to_end(db_session, workspace_agent):
    """ALLOW émis par le contrôle -> autorisation -> effet confirmé -> audit corrélé."""
    workspace, agent = workspace_agent
    decision, action = await _stage(db_session, workspace, agent)

    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor=ACTOR
    )

    async def handler(action_record):
        return ExecutionResult(
            success=True,
            output="published",
            error=None,
            provider_reference="ext-123",
            cost_amount=Decimal("0.5"),
            cost_unit="credits",
        )

    outcome = await dispatch_authorized_action(
        db_session,
        action=action,
        authorization_id=authorization.id,
        actor=ACTOR,
        lease_owner="worker-1",
        handler=handler,
    )

    assert outcome.effect is EffectCertainty.confirmed
    assert outcome.success is True

    attempt = await db_session.get(ExecutionAttempt, outcome.attempt_id)
    assert attempt.status is attempts_service.AttemptStatus.SUCCEEDED
    assert attempt.finished_at is not None

    result = (
        await db_session.execute(
            select(ExecutionResultRecord).where(
                ExecutionResultRecord.attempt_id == attempt.id
            )
        )
    ).scalar_one()
    assert result.effect is EffectCertainty.confirmed
    assert result.provider_reference == "ext-123"
    assert result.cost_amount == Decimal("0.5")

    await db_session.refresh(authorization)
    assert authorization.consumed_at is not None

    events = (
        await db_session.execute(
            select(AuditEntry).where(AuditEntry.decision_id == decision.id)
        )
    ).scalars().all()
    event_types = {entry.event_type for entry in events}
    assert AuditEventType.AUTHORIZATION_ISSUED in event_types
    assert AuditEventType.AUTHORIZATION_CONSUMED in event_types
    assert AuditEventType.ATTEMPT_CLAIMED in event_types
    assert AuditEventType.EFFECT_CONFIRMED in event_types
    # Journal corrélé : chaque entrée porte le workspace émetteur.
    assert {entry.workspace_id for entry in events} == {workspace.id}


async def test_denied_decision_never_issues_authorization(db_session, workspace_agent):
    """INV-01 : DENY, ESCALATE et STOP n'émettent aucune autorisation consommable."""
    workspace, agent = workspace_agent
    for outcome in (
        ControlOutcome.DENY,
        ControlOutcome.ESCALATE,
        ControlOutcome.STOP,
    ):
        decision, action = await _stage(db_session, workspace, agent)
        decision.control_outcome = outcome
        decision.permission_granted = False

        with pytest.raises(AuthorizationError) as exc_info:
            await authorizations.issue_authorization(
                db_session, decision=decision, action=action, actor=ACTOR
            )
        assert exc_info.value.code == f"CONTROL_{outcome.value}"

        # Le refus est audité, pas seulement levé.
        events = (
            await db_session.execute(
                select(AuditEntry).where(AuditEntry.action_id == action.id)
            )
        ).scalars().all()
        assert AuditEventType.AUTHORIZATION_REJECTED in {e.event_type for e in events}


async def test_authorization_cannot_be_consumed_twice(db_session, workspace_agent):
    """INV-14 : l'autorisation consommée refuse un second effet, sans nouvelle tentative."""
    workspace, agent = workspace_agent
    decision, action = await _stage(db_session, workspace, agent)
    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor=ACTOR
    )

    async def handler(action_record):
        return ExecutionResult(success=True, output="ok", error=None)

    first = await dispatch_authorized_action(
        db_session,
        action=action,
        authorization_id=authorization.id,
        actor=ACTOR,
        lease_owner="worker-1",
        handler=handler,
    )
    assert first.effect is EffectCertainty.confirmed

    with pytest.raises(AuthorizationError) as exc_info:
        await dispatch_authorized_action(
            db_session,
            action=action,
            authorization_id=authorization.id,
            actor=ACTOR,
            lease_owner="worker-2",
            handler=handler,
        )
    assert exc_info.value.code == "AUTHORIZATION_ALREADY_CONSUMED"

    # Une seule tentative : le refus précède toute prise en charge.
    attempts = (
        await db_session.execute(
            select(ExecutionAttempt).where(
                ExecutionAttempt.authorization_id == authorization.id
            )
        )
    ).scalars().all()
    assert len(attempts) == 1


async def test_revoked_authorization_blocks_execution(db_session, workspace_agent):
    """INV-14 : une autorisation révoquée avant l'effet n'est jamais consommée."""
    workspace, agent = workspace_agent
    decision, action = await _stage(db_session, workspace, agent)
    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor=ACTOR
    )

    await authorizations.revoke_authorization(
        db_session, authorization_id=authorization.id, reason="OWNER_REVOKED", actor="owner"
    )

    async def handler(action_record):
        raise AssertionError("Aucun handler ne doit être appelé.")

    with pytest.raises(AuthorizationError) as exc_info:
        await dispatch_authorized_action(
            db_session,
            action=action,
            authorization_id=authorization.id,
            actor=ACTOR,
            lease_owner="worker-1",
            handler=handler,
        )
    assert exc_info.value.code == "AUTHORIZATION_REVOKED"


async def test_foreign_workspace_is_refused_before_any_effect(db_session, workspace_agent):
    """INV-02 : l'appelant d'un autre workspace est refusé avant tout accès à l'outil."""
    workspace, agent = workspace_agent
    decision, action = await _stage(db_session, workspace, agent)
    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor=ACTOR
    )

    async def handler(action_record):
        raise AssertionError("Aucun handler ne doit être appelé.")

    with pytest.raises(AuthorizationError) as exc_info:
        await dispatch_authorized_action(
            db_session,
            action=action,
            authorization_id=authorization.id,
            actor=ACTOR,
            lease_owner="worker-1",
            caller_workspace_id=uuid.uuid4(),
            handler=handler,
        )
    assert exc_info.value.code == "WORKSPACE_MISMATCH"


async def test_quota_exceeded_blocks_second_action(db_session, workspace_agent):
    """INV-08 : la borne est vérifiée atomiquement ; un dépassement refuse avant l'effet."""
    workspace, agent = workspace_agent
    db_session.add(
        ResourceBudget(workspace_id=workspace.id, resource="api_calls", limit_units=Decimal("5"))
    )
    await db_session.flush()

    async def handler(action_record):
        return ExecutionResult(success=True, output="ok", error=None)

    # Première action : 4 unités, acceptée.
    decision, action = await _stage(db_session, workspace, agent)
    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor=ACTOR
    )
    await dispatch_authorized_action(
        db_session,
        action=action,
        authorization_id=authorization.id,
        actor=ACTOR,
        lease_owner="worker-1",
        resource="api_calls",
        units=Decimal("4"),
        handler=handler,
    )

    # Seconde action : 2 unités de plus -> dépasse la borne de 5.
    decision2, action2 = await _stage(db_session, workspace, agent)
    authorization2 = await authorizations.issue_authorization(
        db_session, decision=decision2, action=action2, actor=ACTOR
    )

    with pytest.raises(AuthorizationError) as exc_info:
        await dispatch_authorized_action(
            db_session,
            action=action2,
            authorization_id=authorization2.id,
            actor=ACTOR,
            lease_owner="worker-2",
            resource="api_calls",
            units=Decimal("2"),
            handler=handler,
        )
    assert exc_info.value.code == "QUOTA_EXCEEDED"

    # Aucune tentative n'a été ouverte pour l'action refusée.
    remaining = (
        await db_session.execute(
            select(ExecutionAttempt).where(ExecutionAttempt.action_id == action2.id)
        )
    ).scalars().all()
    assert remaining == []

    # Le refus est audité avec le détail du solde.
    events = (
        await db_session.execute(
            select(AuditEntry).where(AuditEntry.action_id == action2.id)
        )
    ).scalars().all()
    rejections = [e for e in events if e.reason_code == "QUOTA_EXCEEDED"]
    assert rejections
    assert rejections[0].payload["limit_units"] is not None
    assert Decimal(rejections[0].payload["limit_units"]) == Decimal("5")
    assert Decimal(rejections[0].payload["committed_units"]) == Decimal("4")


async def test_unknown_budget_refuses_reservation(db_session, workspace_agent):
    """INV-08 : une ressource sans budget déclaré n'est pas « illimitée »."""
    workspace, agent = workspace_agent
    decision, action = await _stage(db_session, workspace, agent)
    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor=ACTOR
    )

    with pytest.raises(AuthorizationError) as exc_info:
        await reservations.reserve_quota(
            db_session,
            action=action,
            authorization_id=authorization.id,
            resource="sms_credits",
            units=Decimal("1"),
            idempotency_key=action.idempotency_key,
            actor=ACTOR,
        )
    assert exc_info.value.code == "QUOTA_UNKNOWN"


async def test_same_logical_operation_never_double_charges(db_session, workspace_agent):
    """INV-08 : rejouer la même opération logique réutilise la réservation existante."""
    workspace, agent = workspace_agent
    db_session.add(
        ResourceBudget(workspace_id=workspace.id, resource="api_calls", limit_units=Decimal("10"))
    )
    decision, action = await _stage(db_session, workspace, agent)
    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor=ACTOR
    )

    first = await reservations.reserve_quota(
        db_session,
        action=action,
        authorization_id=authorization.id,
        resource="api_calls",
        units=Decimal("2"),
        idempotency_key=action.idempotency_key,
        actor=ACTOR,
    )
    retry = await reservations.reserve_quota(
        db_session,
        action=action,
        authorization_id=authorization.id,
        resource="api_calls",
        units=Decimal("2"),
        idempotency_key=action.idempotency_key,
        actor=ACTOR,
    )

    assert first.id == retry.id
    held = (
        await db_session.execute(
            select(ActionReservation).where(
                ActionReservation.workspace_id == workspace.id,
                ActionReservation.resource == "api_calls",
                ActionReservation.status == ReservationStatus.HELD,
            )
        )
    ).scalars().all()
    assert len(held) == 1
    assert held[0].units == Decimal("2")