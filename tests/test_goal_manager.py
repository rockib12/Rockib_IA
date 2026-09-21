"""Tests exhaustifs pour GoalManager (STEP 4D).

Couvre l'ensemble des exigences et invariants :
1. Autonomie (requested, agent cap, parent cap, bornes [0, 5], requested=0).
2. Hiérarchie Parent/Child (workspace mismatch, agent mismatch, cycles, etc.).
3. Deadlines (normalisation UTC, rejet naïf, rejet expirée, héritage parent).
4. Limites & Compteurs (check_limits, max_steps, replanning, budget, deadline).
5. Cycle de vie (start_planning, activate_plan, replanning, pause, resume, etc.).
6. Preuve externe de succès (GoalSuccessProof, critères requis, complétude).
7. Impasse DAG (evaluate_dag_stalemate, bascule PLANNING ou FAILED).
8. Immutabilité des états terminaux (first-terminal-commit-wins).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.decision_engine.models import ImpactType
from app.execution.models import (
    ActionRecord,
    AttemptStatus,
    EffectCertainty,
    ExecutionAttempt,
    ExecutionAuthorization,
    ExecutionResultRecord,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.goal_engine.exceptions import (
    GoalAlreadyTerminalError,
    GoalAutonomyLevelInvalidError,
    GoalDeadlineExceededError,
    GoalDeadlineInvalidError,
    GoalIncompleteTasksError,
    GoalMissingReasonError,
    GoalParentCycleError,
    GoalParentDeadlineExpiredError,
    GoalParentTerminalError,
    GoalPlanEmptyError,
    GoalReplanningLimitExceededError,
    GoalRunningTasksActiveError,
    GoalStepLimitExceededError,
    GoalSuccessCriteriaNotMetError,
    GoalTimezoneNaiveError,
    GoalWorkspaceMismatchError,
    InvalidGoalTransitionError,
)
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.goal_manager import (
    GoalManager,
    GoalSuccessProof,
)
from app.identity.models import Agent, Workspace
from app.task_engine.models import Task, TaskDependency, TaskStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_goal(workspace: Workspace, agent: Agent, **overrides) -> Goal:
    values = dict(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        agent_id=agent.id,
        objective="Objectif de test robuste",
        requested_autonomy_level=2,
        applied_autonomy_level=2,
        status=GoalStatus.PENDING,
        goal_metadata={},
    )
    values.update(overrides)
    return Goal(**values)


# =============================================================================
# 1. TESTS AUTONOMIE (PURS)
# =============================================================================


def test_autonomy_calculation_nominal():
    # min(3, 4) = 3
    assert GoalManager.calculate_applied_autonomy(3, 4) == 3
    # min(5, 2) = 2 (agent cap)
    assert GoalManager.calculate_applied_autonomy(5, 2) == 2
    # requested = 0 (doit rester 0)
    assert GoalManager.calculate_applied_autonomy(0, 5) == 0


def test_autonomy_calculation_with_parent():
    # min(4, 5, 2) = 2 (parent cap)
    assert GoalManager.calculate_applied_autonomy(4, 5, 2) == 2
    # min(2, 5, 4) = 2 (requested cap)
    assert GoalManager.calculate_applied_autonomy(2, 5, 4) == 2
    # min(5, 3, 4) = 3 (agent cap)
    assert GoalManager.calculate_applied_autonomy(5, 3, 4) == 3


def test_autonomy_calculation_invalid_bounds():
    with pytest.raises(GoalAutonomyLevelInvalidError):
        GoalManager.calculate_applied_autonomy(-1, 3)
    with pytest.raises(GoalAutonomyLevelInvalidError):
        GoalManager.calculate_applied_autonomy(6, 3)
    with pytest.raises(GoalAutonomyLevelInvalidError):
        GoalManager.calculate_applied_autonomy(3, -1)
    with pytest.raises(GoalAutonomyLevelInvalidError):
        GoalManager.calculate_applied_autonomy(3, 3, parent_applied_autonomy=-1)
    with pytest.raises(GoalAutonomyLevelInvalidError):
        GoalManager.calculate_applied_autonomy(3, 3, parent_applied_autonomy=6)


# =============================================================================
# 2. TESTS DEADLINES (PURS & RESOLUTION)
# =============================================================================


def test_resolve_child_deadline_timezone_naive_rejected():
    naive_dt = datetime(2030, 1, 1, 12, 0, 0)
    with pytest.raises(GoalTimezoneNaiveError):
        GoalManager.resolve_child_deadline(naive_dt, None)


def test_resolve_child_deadline_expired_rejected():
    past = _now() - timedelta(hours=1)
    with pytest.raises(GoalDeadlineInvalidError):
        GoalManager.resolve_child_deadline(past, None)


def test_resolve_child_deadline_parent_expired_rejected():
    past = _now() - timedelta(hours=1)
    future = _now() + timedelta(days=2)
    with pytest.raises(GoalParentDeadlineExpiredError):
        GoalManager.resolve_child_deadline(future, past)


def test_resolve_child_deadline_inheritance_and_clamping():
    now = _now()
    parent_dl = now + timedelta(days=5)
    child_longer = now + timedelta(days=10)
    child_shorter = now + timedelta(days=2)

    # 1. Child sans deadline hérite de la parent deadline
    assert GoalManager.resolve_child_deadline(None, parent_dl) == parent_dl

    # 2. Child avec deadline > parent est écrêté à parent
    assert GoalManager.resolve_child_deadline(child_longer, parent_dl) == parent_dl

    # 3. Child avec deadline < parent conserve sa deadline plus courte
    assert GoalManager.resolve_child_deadline(child_shorter, parent_dl) == child_shorter

    # 4. Parent sans deadline -> child conserve sa deadline
    assert GoalManager.resolve_child_deadline(child_shorter, None) == child_shorter


# =============================================================================
# 3. TESTS PARENT / ENFANT & DÉTECTION DE CYCLES (DB)
# =============================================================================


@pytest.mark.asyncio
async def test_parent_hierarchy_workspace_mismatch(db_session, workspace_agent):
    ws1, agent1 = workspace_agent
    ws2 = Workspace(name="WS2", slug=f"ws2-{uuid.uuid4().hex[:8]}")
    db_session.add(ws2)
    await db_session.flush()

    manager = GoalManager(db_session)

    # Parent dans ws1
    parent = _make_goal(ws1, agent1)
    db_session.add(parent)
    await db_session.flush()

    # Tentative de lier un child dans ws2 au parent dans ws1
    with pytest.raises(GoalWorkspaceMismatchError):
        await manager.validate_parent_hierarchy(
            goal_id=None,
            workspace_id=ws2.id,
            parent_goal_id=parent.id,
        )


@pytest.mark.asyncio
async def test_parent_hierarchy_parent_terminal(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    parent = _make_goal(ws, agent, status=GoalStatus.COMPLETED)
    db_session.add(parent)
    await db_session.flush()

    with pytest.raises(GoalParentTerminalError):
        await manager.validate_parent_hierarchy(
            goal_id=None,
            workspace_id=ws.id,
            parent_goal_id=parent.id,
        )


@pytest.mark.asyncio
async def test_parent_hierarchy_cycle_detection(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    g_a = _make_goal(ws, agent)
    g_b = _make_goal(ws, agent)
    g_c = _make_goal(ws, agent)
    db_session.add_all([g_a, g_b, g_c])
    await db_session.flush()

    # Chaîne A -> B -> C
    g_b.parent_goal_id = g_a.id
    g_c.parent_goal_id = g_b.id
    await db_session.flush()

    # 1. Cycle direct : A -> A
    with pytest.raises(GoalParentCycleError):
        await manager.validate_parent_hierarchy(
            goal_id=g_a.id,
            workspace_id=ws.id,
            parent_goal_id=g_a.id,
        )

    # 2. Cycle indirect : tenter de donner C comme parent à A (A -> B -> C -> A)
    with pytest.raises(GoalParentCycleError):
        await manager.validate_parent_hierarchy(
            goal_id=g_a.id,
            workspace_id=ws.id,
            parent_goal_id=g_c.id,
        )


# =============================================================================
# 4. TESTS CHECK_LIMITS
# =============================================================================


@pytest.mark.asyncio
async def test_check_limits_nominal_and_violations(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    future = _now() + timedelta(days=1)
    goal = _make_goal(
        ws,
        agent,
        goal_metadata={
            "deadline": future.isoformat(),
            "limits": {
                "max_steps": 10,
                "max_replanning_count": 2,
                "budget_limit": "50.0",
            },
            "usage": {
                "current_steps": 5,
                "replanning_count": 1,
                "budget_consumed": 20.0,
            },
        },
    )
    db_session.add(goal)
    await db_session.flush()

    # Nominal
    res = await manager.check_limits(goal.id, raise_on_violation=False)
    assert res.ok is True
    assert res.current_steps == 5
    assert res.max_steps == 10

    # Dépassement max_steps
    goal.goal_metadata["usage"]["current_steps"] = 10
    res_steps = await manager.check_limits(goal.id, raise_on_violation=False)
    assert res_steps.ok is False
    assert res_steps.steps_ok is False

    with pytest.raises(GoalStepLimitExceededError):
        await manager.check_limits(goal.id, raise_on_violation=True)

    # Dépassement deadline
    past = _now() - timedelta(seconds=1)
    goal.goal_metadata["usage"]["current_steps"] = 5
    goal.goal_metadata["deadline"] = past.isoformat()
    with pytest.raises(GoalDeadlineExceededError):
        await manager.check_limits(goal.id, raise_on_violation=True)


# =============================================================================
# 5. TESTS CYCLE DE VIE (PLANNING, ACTIVATION, REPLANNING, PAUSE, RESUME)
# =============================================================================


@pytest.mark.asyncio
async def test_lifecycle_planning_and_empty_activation_rejected(
    db_session, workspace_agent
):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()

    # PENDING -> PLANNING
    goal = await manager.start_planning(goal.id)
    assert goal.status is GoalStatus.PLANNING

    # Tentative d'activation sans tâche -> GoalPlanEmptyError
    with pytest.raises(GoalPlanEmptyError):
        await manager.activate_plan(goal.id)


@pytest.mark.asyncio
async def test_lifecycle_activation_with_valid_dag(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(ws, agent, status=GoalStatus.PLANNING)
    db_session.add(goal)
    await db_session.flush()

    # Création de 2 tâches (T1 -> T2)
    t1 = Task(goal_id=goal.id, description="Task 1", status=TaskStatus.PENDING)
    t2 = Task(goal_id=goal.id, description="Task 2", status=TaskStatus.PENDING)
    db_session.add_all([t1, t2])
    await db_session.flush()

    dep = TaskDependency(goal_id=goal.id, task_id=t2.id, depends_on_task_id=t1.id)
    db_session.add(dep)
    await db_session.flush()

    # PLANNING -> ACTIVE
    goal = await manager.activate_plan(goal.id)
    assert goal.status is GoalStatus.ACTIVE
    assert goal.completed_at is None
    assert goal.goal_metadata["limits"]["max_steps"] == 100
    assert goal.goal_metadata["usage"]["current_steps"] == 0


@pytest.mark.asyncio
async def test_lifecycle_replanning_atomicity_and_limit(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(
        ws,
        agent,
        status=GoalStatus.ACTIVE,
        goal_metadata={"limits": {"max_replanning_count": 2}},
    )
    db_session.add(goal)
    await db_session.flush()

    # 1er replanning
    goal = await manager.request_replanning(goal.id, reason="Changement d'approche")
    assert goal.status is GoalStatus.PLANNING
    assert goal.goal_metadata["usage"]["replanning_count"] == 1
    assert len(goal.goal_metadata["replanning_history"]) == 1

    # Réactivation (ajouter une tâche pour permettre activation)
    t = Task(goal_id=goal.id, description="Task 1", status=TaskStatus.PENDING)
    db_session.add(t)
    await db_session.flush()
    goal = await manager.activate_plan(goal.id)
    assert goal.status is GoalStatus.ACTIVE

    # 2eme replanning
    goal = await manager.request_replanning(goal.id, reason="Deuxième ajustement")
    assert goal.goal_metadata["usage"]["replanning_count"] == 2

    # Réactivation
    goal = await manager.activate_plan(goal.id)

    # 3eme replanning -> dépasse la limite (max = 2)
    with pytest.raises(GoalReplanningLimitExceededError):
        await manager.request_replanning(goal.id, reason="Troisième tentative refusée")


@pytest.mark.asyncio
async def test_lifecycle_pause_and_resume(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(ws, agent, status=GoalStatus.ACTIVE)
    db_session.add(goal)
    await db_session.flush()

    t = Task(goal_id=goal.id, description="T", status=TaskStatus.PENDING)
    db_session.add(t)
    await db_session.flush()

    # Pause
    goal = await manager.pause_goal(goal.id, reason="Attente intervention humaine")
    assert goal.status is GoalStatus.PAUSED
    assert goal.goal_metadata["pause_reason"] == "Attente intervention humaine"

    # Resume (tâche PENDING prête -> ACTIVE)
    goal = await manager.resume_goal(goal.id)
    assert goal.status is GoalStatus.ACTIVE
    assert "pause_reason" not in goal.goal_metadata


# =============================================================================
# 6. TESTS COMPLETION, PREUVE EXTERNE ET CRITÈRES DE SUCCÈS
# =============================================================================


@pytest.mark.asyncio
async def test_complete_goal_nominal_and_proof_validation(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(
        ws,
        agent,
        status=GoalStatus.ACTIVE,
        goal_metadata={
            "success_criteria": ["Livrable généré", "Tests unitaires 100%"],
        },
    )
    db_session.add(goal)
    await db_session.flush()

    t = Task(goal_id=goal.id, description="Tâche terminée", status=TaskStatus.COMPLETED)
    db_session.add(t)
    await db_session.flush()

    # 1. Preuve invalide / incomplète sur critères
    incomplete_proof = GoalSuccessProof(
        reference="PROOF-001",
        verified_by="QA_BOT",
        verified_at=_now(),
        criteria_verified=["Livrable généré"],  # manque Tests unitaires 100%
    )
    with pytest.raises(GoalSuccessCriteriaNotMetError):
        await manager.complete_goal(goal.id, proof=incomplete_proof)

    # 2. Preuve complète
    valid_proof = GoalSuccessProof(
        reference="PROOF-002",
        verified_by="QA_BOT",
        verified_at=_now(),
        criteria_verified=["Livrable généré", "Tests unitaires 100%"],
    )
    goal = await manager.complete_goal(goal.id, proof=valid_proof)
    assert goal.status is GoalStatus.COMPLETED
    assert goal.completed_at is not None
    assert goal.goal_metadata["success_proof"]["reference"] == "PROOF-002"


@pytest.mark.asyncio
async def test_complete_goal_rejected_if_tasks_incomplete(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(ws, agent, status=GoalStatus.ACTIVE)
    db_session.add(goal)
    await db_session.flush()

    t1 = Task(goal_id=goal.id, description="T1", status=TaskStatus.COMPLETED)
    t2 = Task(goal_id=goal.id, description="T2", status=TaskStatus.RUNNING)
    db_session.add_all([t1, t2])
    await db_session.flush()

    proof = GoalSuccessProof(
        reference="PROOF-003",
        verified_by="QA_BOT",
        verified_at=_now(),
    )
    with pytest.raises(GoalIncompleteTasksError):
        await manager.complete_goal(goal.id, proof=proof)


# =============================================================================
# 7. TESTS TERMINAUX (FAIL, CANCEL, IMMUTABILITÉ)
# =============================================================================


@pytest.mark.asyncio
async def test_fail_and_cancel_goal(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    # Fail
    g1 = _make_goal(ws, agent, status=GoalStatus.ACTIVE)
    db_session.add(g1)
    await db_session.flush()

    g1 = await manager.fail_goal(g1.id, reason="Crash irrécupérable")
    assert g1.status is GoalStatus.FAILED
    assert g1.completed_at is not None
    assert g1.goal_metadata["failure_reason"] == "Crash irrécupérable"

    # Cancel
    g2 = _make_goal(ws, agent, status=GoalStatus.PLANNING)
    db_session.add(g2)
    await db_session.flush()

    g2 = await manager.cancel_goal(g2.id, reason="Demande utilisateur")
    assert g2.status is GoalStatus.CANCELLED
    assert g2.completed_at is not None
    assert g2.goal_metadata["cancellation_reason"] == "Demande utilisateur"


@pytest.mark.asyncio
async def test_terminal_immutability(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    g = _make_goal(ws, agent, status=GoalStatus.COMPLETED)
    db_session.add(g)
    await db_session.flush()

    with pytest.raises(GoalAlreadyTerminalError):
        await manager.fail_goal(g.id, reason="Tentative après complétion")

    with pytest.raises(GoalAlreadyTerminalError):
        await manager.cancel_goal(g.id, reason="Tentative après complétion")

    with pytest.raises(InvalidGoalTransitionError) as exc_info:
        await manager.start_planning(g.id)
    assert exc_info.value.code == "TERMINAL_STATE_IMMUTABLE"


# =============================================================================
# 8. TESTS IMPASSE DU DAG (DEADLOCK EVALUATION)
# =============================================================================


@pytest.mark.asyncio
async def test_evaluate_dag_stalemate_replanning_or_failure(
    db_session, workspace_agent
):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    # Goal actif avec 2 tâches dont l'une est FAILED, bloquant la suivante (impasse)
    goal = _make_goal(
        ws,
        agent,
        status=GoalStatus.ACTIVE,
        goal_metadata={"limits": {"max_replanning_count": 1}},
    )
    db_session.add(goal)
    await db_session.flush()

    t1 = Task(goal_id=goal.id, description="T1", status=TaskStatus.FAILED)
    t2 = Task(goal_id=goal.id, description="T2", status=TaskStatus.PENDING)
    db_session.add_all([t1, t2])
    await db_session.flush()

    dep = TaskDependency(goal_id=goal.id, task_id=t2.id, depends_on_task_id=t1.id)
    db_session.add(dep)
    await db_session.flush()

    # 1. Première évaluation d'impasse : replanning_count (0 < 1) -> bascule en PLANNING
    status = await manager.evaluate_dag_stalemate(goal.id)
    assert status is GoalStatus.PLANNING
    assert goal.status is GoalStatus.PLANNING
    assert goal.goal_metadata["usage"]["replanning_count"] == 1

    # On réactive le goal en fournissant un plan avec une tâche prête alternative
    t3 = Task(goal_id=goal.id, description="T3 alternative", status=TaskStatus.PENDING)
    db_session.add(t3)
    await db_session.flush()

    goal = await manager.activate_plan(goal.id)
    assert goal.status is GoalStatus.ACTIVE

    # On simule la complétion de t3 tout en conservant t1(FAILED) -> t2(PENDING) bloqué
    t3.status = TaskStatus.COMPLETED
    await db_session.flush()

    # 2. Deuxième évaluation d'impasse : replanning épuisé (1 >= 1) -> bascule en FAILED
    status2 = await manager.evaluate_dag_stalemate(goal.id)
    assert status2 is GoalStatus.FAILED
    assert goal.status is GoalStatus.FAILED
    assert goal.completed_at is not None


# =============================================================================
# 9. TESTS AGENT MISMATCH & MOTIFS OBLIGATOIRES
# =============================================================================


@pytest.mark.asyncio
async def test_parent_hierarchy_agent_workspace_mismatch(db_session, workspace_agent):
    ws1, _ = workspace_agent
    ws2 = Workspace(name="WS2", slug=f"ws2-{uuid.uuid4().hex[:8]}")
    db_session.add(ws2)
    await db_session.flush()

    agent2 = Agent(
        workspace_id=ws2.id, name="Agent 2", role="other", default_autonomy_level=1
    )
    db_session.add(agent2)
    await db_session.flush()

    manager = GoalManager(db_session)
    with pytest.raises(GoalWorkspaceMismatchError):
        await manager.validate_parent_hierarchy(
            goal_id=None,
            workspace_id=ws1.id,
            parent_goal_id=None,
            agent_id=agent2.id,
        )


@pytest.mark.asyncio
async def test_missing_mandatory_reasons(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(ws, agent, status=GoalStatus.ACTIVE)
    db_session.add(goal)
    await db_session.flush()

    with pytest.raises(GoalMissingReasonError):
        await manager.pause_goal(goal.id, reason="")

    with pytest.raises(GoalMissingReasonError):
        await manager.request_replanning(goal.id, reason="   ")

    with pytest.raises(GoalMissingReasonError):
        await manager.fail_goal(goal.id, reason="")

    with pytest.raises(GoalMissingReasonError):
        await manager.cancel_goal(goal.id, reason="   ")


@pytest.mark.asyncio
async def test_running_tasks_block_replanning(db_session, workspace_agent):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(ws, agent, status=GoalStatus.ACTIVE)
    db_session.add(goal)
    await db_session.flush()

    t = Task(goal_id=goal.id, description="Task running", status=TaskStatus.RUNNING)
    db_session.add(t)
    await db_session.flush()

    with pytest.raises(GoalRunningTasksActiveError):
        await manager.request_replanning(goal.id, reason="Changement d'approche")


# =============================================================================
# 10. TEST CHECK_LIMITS AVEC EXECUTIONATTEMPTS ET RESULTRECORDS RÉELS
# =============================================================================


@pytest.mark.asyncio
async def test_check_limits_with_real_execution_attempts_and_results(
    db_session, workspace_agent
):
    ws, agent = workspace_agent
    manager = GoalManager(db_session)

    goal = _make_goal(
        ws,
        agent,
        status=GoalStatus.ACTIVE,
        goal_metadata={
            "limits": {
                "max_steps": 3,
                "budget_limit": "25.00",
            },
        },
    )
    db_session.add(goal)
    await db_session.flush()

    t = Task(goal_id=goal.id, description="Tache 1", status=TaskStatus.RUNNING)
    db_session.add(t)
    await db_session.flush()

    # Création d'une action rattachée à la tâche
    action = ActionRecord(
        workspace_id=ws.id,
        agent_id=agent.id,
        task_id=t.id,
        objective="Action test",
        tool="test_tool",
        operation="run",
        arguments={},
        permission_required=PermissionAction.READ,
        risk_level=RiskLevel.low,
        risk_reversibility=ReversibilityLevel.reversible,
        risk_impact=ImpactType.internal,
        idempotency_key=f"idem-{uuid.uuid4().hex[:12]}",
        canonical_fingerprint=f"fp-{uuid.uuid4().hex[:12]}",
        version=1,
    )
    db_session.add(action)
    await db_session.flush()

    from tests.conftest import make_decision

    decision = make_decision(workspace_id=ws.id, agent_id=agent.id)
    db_session.add(decision)
    await db_session.flush()

    auth = ExecutionAuthorization(
        workspace_id=ws.id,
        agent_id=agent.id,
        action_id=action.id,
        decision_id=decision.id,
        outcome="ALLOW",
        reason_code="AUTHORIZED",
        action_fingerprint=action.canonical_fingerprint,
        action_version=1,
    )
    db_session.add(auth)
    await db_session.flush()

    # 2 tentatives réelles : SUCCEEDED + RUNNING -> 2 steps consommés
    ea1 = ExecutionAttempt(
        action_id=action.id,
        authorization_id=auth.id,
        workspace_id=ws.id,
        attempt_number=1,
        idempotency_key=f"ea-{uuid.uuid4().hex[:12]}",
        status=AttemptStatus.SUCCEEDED,
    )
    ea2 = ExecutionAttempt(
        action_id=action.id,
        authorization_id=auth.id,
        workspace_id=ws.id,
        attempt_number=2,
        idempotency_key=f"ea-{uuid.uuid4().hex[:12]}",
        status=AttemptStatus.RUNNING,
    )
    # Et une tentative PENDING (ne doit PAS être comptée)
    ea3 = ExecutionAttempt(
        action_id=action.id,
        authorization_id=auth.id,
        workspace_id=ws.id,
        attempt_number=3,
        idempotency_key=f"ea-{uuid.uuid4().hex[:12]}",
        status=AttemptStatus.PENDING,
    )
    db_session.add_all([ea1, ea2, ea3])
    await db_session.flush()

    # Résultat d'exécution avec coût
    res1 = ExecutionResultRecord(
        attempt_id=ea1.id,
        effect=EffectCertainty.confirmed,
        success=True,
        cost_amount=Decimal("15.50"),
        cost_unit="USD",
    )
    db_session.add(res1)
    await db_session.flush()

    # Vérification des limites calculées depuis PostgreSQL
    check = await manager.check_limits(goal.id, raise_on_violation=False)
    assert check.ok is True
    assert check.current_steps == 2  # ea1 + ea2 (ea3 en PENDING exclu)
    assert check.max_steps == 3
    assert check.steps_ok is True
    assert check.consumed_budget == Decimal("15.50")
    assert check.budget_limit == Decimal("25.00")
    assert check.budget_ok is True

    # Ajout d'une 3ème tentative RUNNING -> atteint max_steps (3/3)
    ea4 = ExecutionAttempt(
        action_id=action.id,
        authorization_id=auth.id,
        workspace_id=ws.id,
        attempt_number=4,
        idempotency_key=f"ea-{uuid.uuid4().hex[:12]}",
        status=AttemptStatus.RUNNING,
    )
    db_session.add(ea4)
    await db_session.flush()

    check_steps = await manager.check_limits(goal.id, raise_on_violation=False)
    assert check_steps.current_steps == 3
    assert check_steps.steps_ok is False
    assert check_steps.ok is False
