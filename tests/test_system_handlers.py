"""Tests du premier handler de production system.read (STEP 5C.4).

Vérifie :
- Signature et nature asynchrone
- Exécution nominale pure (ActionRecord -> ExecutionResult)
- Format de l'output et métadonnées de diagnostic
- Rejet des actions non conformes (mauvais tool, mauvaise opération, workspace_id absent)
- Enregistrement dans le registre et idempotence
- Résolution dynamique par dispatch_authorized_action sans handler explicite
- Isolation de workspace (WORKSPACE_MISMATCH)
- Persistance et observabilité (ExecutionResultRecord, provider_reference)
"""
from __future__ import annotations

import inspect
import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.decision_engine.models import PermissionAction
from app.execution.models import (
    ActionRecord,
    EffectCertainty,
    ExecutionAttempt,
    ExecutionResultRecord,
)
from app.execution.services import attempts as attempts_service
from app.execution.services import authorizations
from app.execution.services.authorizations import AuthorizationError
from app.execution.services.reliable_executor import (
    clear_action_handlers,
    dispatch_authorized_action,
    get_action_handler,
)
from app.execution.services.system_handlers import (
    install_production_handlers,
    system_read_handler,
)
from tests.conftest import make_action, make_decision


@pytest.fixture(autouse=True)
def _clean_registry():
    """Isole chaque test vis-à-vis du registre d'actions."""
    clear_action_handlers()
    yield
    clear_action_handlers()


def _make_dummy_action(**overrides) -> ActionRecord:
    values = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        decision_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        objective="Diagnostic système",
        tool="system",
        operation="read",
        arguments={},
        permission_required=PermissionAction.READ,
        canonical_fingerprint="f" * 64,
        idempotency_key="k" * 64,
        version=1,
    )
    values.update(overrides)
    return ActionRecord(**values)


# ---------------------------------------------------------------------------
# Tests unitaires du handler pur
# ---------------------------------------------------------------------------


def test_t1_handler_signature():
    """T1 — Le handler est une fonction coroutine (async def)."""
    assert inspect.iscoroutinefunction(system_read_handler)


@pytest.mark.asyncio
async def test_t2_nominal_execution():
    """T2 — Exécution nominale avec un ActionRecord valide."""
    action = _make_dummy_action()
    result = await system_read_handler(action)

    assert result.success is True
    assert result.effect_unknown is False
    assert result.error is None
    assert result.error_code is None
    assert result.provider_reference == "system:diagnostics"
    assert result.cost_amount == Decimal("0.0")
    assert result.cost_unit == "credits"


@pytest.mark.asyncio
async def test_t3_output_structure_and_metadata():
    """T3 — Parsing du JSON d'output et validation des métadonnées."""
    action = _make_dummy_action()
    result = await system_read_handler(action)

    data = json.loads(result.output)
    assert data["status"] == "operational"
    assert data["tool"] == "system"
    assert data["operation"] == "read"
    assert data["workspace_id"] == str(action.workspace_id)
    assert data["agent_id"] == str(action.agent_id)
    assert data["action_id"] == str(action.id)
    assert data["task_id"] == str(action.task_id)
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_t4_reject_wrong_tool():
    """T4 — Rejet si tool != 'system'."""
    action = _make_dummy_action(tool="other_tool")
    with pytest.raises(ValueError, match="Invalid tool for system_read_handler"):
        await system_read_handler(action)


@pytest.mark.asyncio
async def test_t5_reject_wrong_operation():
    """T5 — Rejet si operation != 'read'."""
    action = _make_dummy_action(operation="write")
    with pytest.raises(ValueError, match="Invalid operation for system_read_handler"):
        await system_read_handler(action)


@pytest.mark.asyncio
async def test_t6_reject_missing_workspace():
    """T6 — Rejet si workspace_id est absent / None."""
    action = _make_dummy_action(workspace_id=None)
    with pytest.raises(ValueError, match="must have a non-null workspace_id"):
        await system_read_handler(action)


# ---------------------------------------------------------------------------
# Tests du registre et idempotence
# ---------------------------------------------------------------------------


def test_registry_installation_and_idempotence():
    """Enregistrement officiel et vérification de l'idempotence."""
    assert get_action_handler("system", "read") is None

    # Premier enregistrement
    install_production_handlers()
    assert get_action_handler("system", "read") is system_read_handler

    # Deuxième enregistrement : idempotent et silencieux
    install_production_handlers()
    assert get_action_handler("system", "read") is system_read_handler


# ---------------------------------------------------------------------------
# Tests d'intégration dispatch réel & persistance PostgreSQL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_dispatch_without_explicit_handler(db_session, workspace_agent):
    """Section 9 & 11 — Dispatch réel avec résolution par le registre et persistance."""
    workspace, agent = workspace_agent
    install_production_handlers()

    decision = make_decision(
        workspace_id=workspace.id,
        agent_id=agent.id,
        permission_action=PermissionAction.READ,
    )
    db_session.add(decision)
    await db_session.flush()

    action = make_action(
        workspace_id=workspace.id,
        agent_id=agent.id,
        decision_id=decision.id,
        tool="system",
        operation="read",
        permission_action=PermissionAction.READ,
        idempotency_scope=f"system-read-{uuid.uuid4().hex}",
    )
    db_session.add(action)
    await db_session.flush()

    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor="test-runner"
    )

    # Dispatch SANS passer d'argument handler : doit être résolu via _ACTION_HANDLERS
    outcome = await dispatch_authorized_action(
        db_session,
        action=action,
        authorization_id=authorization.id,
        actor="test-runner",
        lease_owner="worker-sys-1",
        handler=None,
    )

    assert outcome.effect is EffectCertainty.confirmed
    assert outcome.success is True
    assert outcome.provider_reference == "system:diagnostics"

    # Vérification de l'Attempt
    attempt = await db_session.get(ExecutionAttempt, outcome.attempt_id)
    assert attempt.status is attempts_service.AttemptStatus.SUCCEEDED

    # Section 11 — Observabilité et persistance dans execution_results
    result_record = (
        await db_session.execute(
            select(ExecutionResultRecord).where(
                ExecutionResultRecord.attempt_id == attempt.id
            )
        )
    ).scalar_one()
    assert result_record.effect is EffectCertainty.confirmed
    assert result_record.provider_reference == "system:diagnostics"
    assert result_record.cost_amount == Decimal("0.0")
    assert result_record.success is True


@pytest.mark.asyncio
async def test_isolation_workspace_mismatch(db_session, workspace_agent):
    """Section 10 — WORKSPACE_MISMATCH empêche toute exécution du handler."""
    workspace, agent = workspace_agent
    install_production_handlers()

    decision = make_decision(
        workspace_id=workspace.id,
        agent_id=agent.id,
        permission_action=PermissionAction.READ,
    )
    db_session.add(decision)
    await db_session.flush()

    action = make_action(
        workspace_id=workspace.id,
        agent_id=agent.id,
        decision_id=decision.id,
        tool="system",
        operation="read",
        permission_action=PermissionAction.READ,
        idempotency_scope=f"system-iso-{uuid.uuid4().hex}",
    )
    db_session.add(action)
    await db_session.flush()

    authorization = await authorizations.issue_authorization(
        db_session, decision=decision, action=action, actor="test-runner"
    )

    foreign_workspace_id = uuid.uuid4()
    with pytest.raises(AuthorizationError) as exc_info:
        await dispatch_authorized_action(
            db_session,
            action=action,
            authorization_id=authorization.id,
            actor="test-runner",
            lease_owner="worker-sys-1",
            caller_workspace_id=foreign_workspace_id,
            handler=None,
        )

    assert exc_info.value.code == "WORKSPACE_MISMATCH"
