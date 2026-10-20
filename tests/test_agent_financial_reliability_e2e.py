"""End-to-End Agent Reliability, Real Financial Governance, PostgreSQL Locks & Post-Crash Reconciliation."""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.decision_engine.models import (
    ControlOutcome,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
    Decision,
)
from app.execution.models import (
    ActionRecord,
    ActionReservation,
    AttemptStatus,
    EffectCertainty,
    ExecutionAttempt,
    ExecutionResultRecord,
    ReservationStatus,
    ResourceBudget,
)
from app.execution.services import authorizations, reliable_executor, reservations
from app.execution.services.authorizations import AuthorizationError
from app.execution.services.executor import ExecutionResult
from app.execution.services.fingerprint import compute_fingerprint
from app.execution.services.financial_governance import (
    BudgetCeilingExceededError,
    FinancialAmountError,
    FinancialConsistencyError,
)
from app.connectors.social_connectors import meta_ads_create_handler
from app.connectors.agent_connectors import agent_spawn_handler
from app.goal_engine.models import Goal, GoalStatus
from tests.conftest import make_decision


@pytest.mark.asyncio
async def test_financial_consistency_and_budget_ceiling_enforcement(db_session: AsyncSession, workspace_agent):
    """Garantit que toute incohérence ou dépassement de plafond bloque l'exécution avant tout effet."""
    workspace, agent = workspace_agent
    ws_id, agent_id = workspace.id, agent.id

    # 1. Action avec budget_ceiling = 100 EUR mais amount = 150 EUR
    args_excess = {
        "amount": "150",
        "currency": "EUR",
        "budget_ceiling": "100",
        "budget_currency": "EUR",
    }
    fp_excess = compute_fingerprint(
        workspace_id=ws_id,
        agent_id=agent_id,
        tool="meta_ads",
        operation="create_campaign",
        permission_required=PermissionAction.SPEND,
        objective="Campagne pub",
        arguments=args_excess,
    )
    decision = make_decision(
        workspace_id=ws_id,
        agent_id=agent_id,
        outcome=ControlOutcome.ALLOW,
        permission_action=PermissionAction.SPEND,
    )
    decision.action_fingerprint = fp_excess
    db_session.add(decision)
    await db_session.flush()

    action_excess = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=agent_id,
        decision_id=decision.id,
        objective="Campagne pub",
        tool="meta_ads",
        operation="create_campaign",
        arguments=args_excess,
        permission_required=PermissionAction.SPEND,
        risk_level=RiskLevel.high,
        risk_reversibility=ReversibilityLevel.irreversible,
        risk_impact=ImpactType.financial,
        cost_estimate=Decimal("150"),
        cost_unit="EUR",
        canonical_fingerprint=fp_excess,
        idempotency_key=f"excess_{uuid.uuid4()}",
        version=1,
    )
    db_session.add(action_excess)
    await db_session.flush()

    auth = await authorizations.issue_authorization(
        db_session, decision=decision, action=action_excess, actor="test_runner"
    )
    await db_session.commit()

    # Doit être rejeté avec BUDGET_CEILING_VIOLATION avant d'appeler le handler
    with pytest.raises(AuthorizationError) as exc_info:
        await reliable_executor.dispatch_authorized_action(
            db_session,
            action=action_excess,
            authorization_id=auth.id,
            actor="test_runner",
            lease_owner="worker_1",
        )
    assert exc_info.value.code == "BUDGET_CEILING_VIOLATION"


@pytest.mark.asyncio
async def test_postgresql_atomic_quota_reservation_and_exhaustion(db_session: AsyncSession, workspace_agent):
    """Prouve que PostgreSQL advisory lock sérialise les réservations et refuse tout dépassement."""
    workspace, agent = workspace_agent
    ws_id, agent_id = workspace.id, agent.id

    # 1. Configurer un budget de 100 EUR dans la table resource_budgets
    budget = ResourceBudget(
        workspace_id=ws_id,
        resource="currency:EUR",
        limit_units=Decimal("100.00"),
    )
    db_session.add(budget)
    await db_session.commit()

    # 2. Action A demandant 70 EUR
    args_a = {"amount": "70", "currency": "EUR"}
    fp_a = compute_fingerprint(
        workspace_id=ws_id,
        agent_id=agent_id,
        tool="meta_ads",
        operation="create",
        permission_required=PermissionAction.SPEND,
        objective="Campagne A",
        arguments=args_a,
    )
    dec_a = make_decision(workspace_id=ws_id, agent_id=agent_id, outcome=ControlOutcome.ALLOW, permission_action=PermissionAction.SPEND)
    dec_a.action_fingerprint = fp_a
    db_session.add(dec_a)
    await db_session.flush()

    action_a = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=agent_id,
        decision_id=dec_a.id,
        objective="Campagne A",
        tool="meta_ads",
        operation="create",
        arguments=args_a,
        permission_required=PermissionAction.SPEND,
        risk_level=RiskLevel.high,
        risk_reversibility=ReversibilityLevel.irreversible,
        risk_impact=ImpactType.financial,
        cost_estimate=Decimal("70"),
        cost_unit="EUR",
        canonical_fingerprint=fp_a,
        idempotency_key=f"act_a_{uuid.uuid4()}",
        version=1,
    )
    db_session.add(action_a)
    await db_session.flush()

    auth_a = await authorizations.issue_authorization(db_session, decision=dec_a, action=action_a, actor="test")
    await db_session.commit()

    async def _mock_ads_handler(act: ActionRecord) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            output="Campagne créée",
            cost_amount=Decimal("70"),
            cost_unit="EUR",
            provider_reference="meta:camp_123",
        )

    outcome_a = await reliable_executor.dispatch_authorized_action(
        db_session,
        action=action_a,
        authorization_id=auth_a.id,
        actor="test",
        lease_owner="w1",
        handler=_mock_ads_handler,
    )
    assert outcome_a.success is True

    # 3. Action B demandant 50 EUR (70 + 50 = 120 > 100 EUR) -> doit être refusée
    args_b = {"amount": "50", "currency": "EUR"}
    fp_b = compute_fingerprint(
        workspace_id=ws_id,
        agent_id=agent_id,
        tool="meta_ads",
        operation="create",
        permission_required=PermissionAction.SPEND,
        objective="Campagne B",
        arguments=args_b,
    )
    dec_b = make_decision(workspace_id=ws_id, agent_id=agent_id, outcome=ControlOutcome.ALLOW, permission_action=PermissionAction.SPEND)
    dec_b.action_fingerprint = fp_b
    db_session.add(dec_b)
    await db_session.flush()

    action_b = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=agent_id,
        decision_id=dec_b.id,
        objective="Campagne B",
        tool="meta_ads",
        operation="create",
        arguments=args_b,
        permission_required=PermissionAction.SPEND,
        risk_level=RiskLevel.high,
        risk_reversibility=ReversibilityLevel.irreversible,
        risk_impact=ImpactType.financial,
        cost_estimate=Decimal("50"),
        cost_unit="EUR",
        canonical_fingerprint=fp_b,
        idempotency_key=f"act_b_{uuid.uuid4()}",
        version=1,
    )
    db_session.add(action_b)
    await db_session.flush()

    auth_b = await authorizations.issue_authorization(db_session, decision=dec_b, action=action_b, actor="test")
    await db_session.commit()

    with pytest.raises(AuthorizationError) as exc_b:
        await reliable_executor.dispatch_authorized_action(
            db_session,
            action=action_b,
            authorization_id=auth_b.id,
            actor="test",
            lease_owner="w1",
            handler=_mock_ads_handler,
        )
    assert exc_b.value.code == "QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_crash_recovery_unknown_effect_and_reconciliation(db_session: AsyncSession, workspace_agent):
    """Prouve que lors d'un crash/timeout ambigu, la réservation reste HELD jusqu'à réconciliation."""
    workspace, agent = workspace_agent
    ws_id, agent_id = workspace.id, agent.id

    budget = ResourceBudget(
        workspace_id=ws_id,
        resource="currency:EUR",
        limit_units=Decimal("200.00"),
    )
    db_session.add(budget)
    await db_session.commit()

    args = {"amount": "80", "currency": "EUR"}
    fp = compute_fingerprint(
        workspace_id=ws_id,
        agent_id=agent_id,
        tool="meta_ads",
        operation="create",
        permission_required=PermissionAction.SPEND,
        objective="Campagne ambiguë",
        arguments=args,
    )
    decision = make_decision(workspace_id=ws_id, agent_id=agent_id, outcome=ControlOutcome.ALLOW, permission_action=PermissionAction.SPEND)
    decision.action_fingerprint = fp
    db_session.add(decision)
    await db_session.flush()

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=agent_id,
        decision_id=decision.id,
        objective="Campagne ambiguë",
        tool="meta_ads",
        operation="create",
        arguments=args,
        permission_required=PermissionAction.SPEND,
        risk_level=RiskLevel.high,
        risk_reversibility=ReversibilityLevel.irreversible,
        risk_impact=ImpactType.financial,
        cost_estimate=Decimal("80"),
        cost_unit="EUR",
        canonical_fingerprint=fp,
        idempotency_key=f"crash_{uuid.uuid4()}",
        version=1,
    )
    db_session.add(action)
    await db_session.flush()

    auth = await authorizations.issue_authorization(db_session, decision=decision, action=action, actor="test")
    await db_session.commit()

    # Simuler un handler qui crashe ou timeout
    async def _crashing_handler(act: ActionRecord) -> ExecutionResult:
        raise TimeoutError("Simulation coupure réseau / timeout externe")

    outcome = await reliable_executor.dispatch_authorized_action(
        db_session,
        action=action,
        authorization_id=auth.id,
        actor="test",
        lease_owner="w1",
        handler=_crashing_handler,
    )
    assert outcome.effect == EffectCertainty.unknown

    # La réservation doit être HELD (pas libérée, pour protéger le solde)
    res_stmt = select(ActionReservation).where(ActionReservation.id == outcome.reservation_id)
    res = (await db_session.execute(res_stmt)).scalar_one()
    assert res.status == ReservationStatus.HELD

    # Réconciliation avec preuve que la campagne a bien été créée
    reconciled_attempt = await reliable_executor.reconcile_unknown_attempt(
        db_session,
        attempt_id=outcome.attempt_id,
        resolved_effect=EffectCertainty.confirmed,
        actor="auditor",
        evidence_reference="provider_tx_verified_999",
        settle_reservation=True,
    )
    await db_session.commit()
    assert reconciled_attempt.status == AttemptStatus.SUCCEEDED
    result_rec = (await db_session.execute(
        select(ExecutionResultRecord).where(ExecutionResultRecord.attempt_id == outcome.attempt_id)
    )).scalar_one()
    assert result_rec.effect == EffectCertainty.confirmed

    # La réservation doit maintenant être CONSUMED
    res_updated = (await db_session.execute(res_stmt)).scalar_one()
    assert res_updated.status == ReservationStatus.CONSUMED


@pytest.mark.asyncio
async def test_meta_ads_connector_strict_financial_validation(workspace_agent):
    """Prouve que le connecteur Meta Ads refuse strictement les floats et devises invalides."""
    workspace, agent = workspace_agent

    # 1. Float interdit
    action_float = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        agent_id=agent.id,
        tool="meta_ads",
        operation="create",
        arguments={"name": "Test Camp", "amount": 25.50, "currency": "EUR"},
        permission_required=PermissionAction.SPEND,
        canonical_fingerprint="fp1",
        idempotency_key="idemp_float",
    )
    res_float = await meta_ads_create_handler(action_float)
    assert res_float.success is False
    assert res_float.error_code == "FINANCIAL_VALIDATION_ERROR"
    assert "Float type is forbidden" in res_float.error

    # 2. Devise invalide (minuscules)
    action_curr = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        agent_id=agent.id,
        tool="meta_ads",
        operation="create",
        arguments={"name": "Test Camp", "amount": "25", "currency": "eur"},
        permission_required=PermissionAction.SPEND,
        canonical_fingerprint="fp2",
        idempotency_key="idemp_curr",
    )
    res_curr = await meta_ads_create_handler(action_curr)
    assert res_curr.success is False
    assert res_curr.error_code == "FINANCIAL_VALIDATION_ERROR"
    assert "strictly uppercase" in res_curr.error


@pytest.mark.asyncio
async def test_agent_spawn_parent_child_ceiling_monotony(db_session: AsyncSession, workspace_agent):
    """Prouve que l'Inception interdit à un sous-agent de dépasser le plafond de budget de son parent."""
    workspace, agent = workspace_agent

    # Parent goal avec plafond de 100 EUR
    parent_goal = Goal(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        agent_id=agent.id,
        objective="Parent Mission",
        status=GoalStatus.ACTIVE,
        priority=1,
        requested_autonomy_level=3,
        applied_autonomy_level=3,
        goal_metadata={"budget_ceiling": "100", "budget_currency": "EUR"},
    )
    db_session.add(parent_goal)
    await db_session.flush()

    # Action pour spawner un sous-agent qui demande 500 EUR (dépassement parent !)
    action_spawn_excess = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        agent_id=agent.id,
        tool="agent",
        operation="spawn",
        arguments={
            "name": "Sub-Agent Greedy",
            "objective": "Achat de licences",
            "budget_ceiling": "500",
            "budget_currency": "EUR",
        },
        permission_required=PermissionAction.CREATE,
        canonical_fingerprint="fp_spawn",
        idempotency_key="idemp_spawn",
    )
    # Lier la tâche au parent_goal
    from app.task_engine.models import Task, TaskStatus
    parent_task = Task(
        id=uuid.uuid4(),
        goal_id=parent_goal.id,
        description="Spawning task",
        status=TaskStatus.RUNNING,
    )
    db_session.add(parent_task)
    await db_session.commit()
    action_spawn_excess.task_id = parent_task.id

    res_excess = await agent_spawn_handler(action_spawn_excess)
    assert res_excess.success is False
    assert res_excess.error_code == "BUDGET_CEILING_VIOLATION"
    assert "exceeds parent ceiling" in res_excess.error

    # Sous-agent demandant 40 EUR (inférieur ou égal au parent) -> accepté
    action_spawn_valid = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        agent_id=agent.id,
        task_id=parent_task.id,
        tool="agent",
        operation="spawn",
        arguments={
            "name": "Sub-Agent Reasonable",
            "objective": "Achat modéré",
            "budget_ceiling": "40",
            "budget_currency": "EUR",
        },
        permission_required=PermissionAction.CREATE,
        canonical_fingerprint="fp_spawn_ok",
        idempotency_key="idemp_spawn_ok",
    )
    res_valid = await agent_spawn_handler(action_spawn_valid)
    assert res_valid.success is True
    assert "Successfully spawned" in res_valid.output
