"""STEP 5B — Boucle autonome bornée : wake_goal 1-tâche/appel (P0/P1).

Registre handlers vide (attendu Phase 3) : aucun faux handler inventé.
Le chemin e2e utilise un orchestrateur injecté qui rejoue EXACTEMENT le
contrat observé de l'orchestrateur réel (ALLOW + NO_HANDLER_REGISTERED →
execution_effect=none, execution_attempt_id=None), sans LLM (le legacy
app.core.ai.provider manque — pré-existant, hors périmètre).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.decision_engine.models import ControlOutcome
from app.decision_engine.schemas import DecisionResponse
from app.execution.models import (
    ActionRecord,
    AttemptStatus,
    ExecutionAttempt,
    ExecutionAuthorization,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.autonomous_loop import (
    _admit_one_step,
    _close_task_with_outcome,
    _recover_one_orphan,
    build_decision_request,
    decide_task_transition,
    wake_goal,
)
from app.task_engine.models import Task, TaskDependency, TaskStatus
from app.task_engine.services.task_graph import TaskGraph


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_goal(ws, agent, **overrides) -> Goal:
    values = dict(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        agent_id=agent.id,
        objective="STEP 5B probe",
        requested_autonomy_level=2,
        applied_autonomy_level=2,
        status=GoalStatus.ACTIVE,
        goal_metadata={
            "limits": {"max_steps": 10},
            "usage": {"current_steps": 0, "replanning_count": 0},
        },
    )
    values.update(overrides)
    return Goal(**values)


def _response(control, effect, attempt_id, error, decision_id=None):
    return DecisionResponse(
        decision_id=str(decision_id or uuid.uuid4()),
        dominant_source="cognitive",
        final_action="act",
        risk_level="low",
        approval_required=False,
        control_outcome=control,
        control_reason="PROBE",
        permission_granted=(control == ControlOutcome.ALLOW),
        execution_effect=effect,
        execution_attempt_id=str(attempt_id) if attempt_id else None,
        execution_error=error,
    )


class _ContractOrchestrator:
    """Rejoue le contrat réel observé (orchestrator.py:206-226) sans LLM."""

    def __init__(self, db, response: DecisionResponse):
        self.db = db
        self.response = response
        self.seen_task_ids: list = []

    async def handle_decision(self, request, *, task_id=None):
        self.seen_task_ids.append(task_id)
        return self.response

async def _fetch(db, model, pk):
    """Relecture fraîche d'une ligne par PK (court, sans lazy-load)."""
    return (await db.execute(select(model).where(model.id == pk))).scalar_one()


async def _persisted_decision(db_session, ws, agent):
    """Décision réelle persistée (FK tasks/task_id + authorizations exigée)."""
    from tests.conftest import make_decision

    d = make_decision(workspace_id=ws.id, agent_id=agent.id)
    db_session.add(d)
    await db_session.flush()
    return d



def test_build_decision_request_is_pure_and_deterministic():
    goal_id = uuid.uuid4()
    ws_id, ag_id = uuid.uuid4(), uuid.uuid4()
    goal = Goal(
        id=goal_id, workspace_id=ws_id, agent_id=ag_id, objective="obj",
        requested_autonomy_level=2, applied_autonomy_level=2,
        status=GoalStatus.ACTIVE, goal_metadata={},
    )
    t1 = Task(id=uuid.uuid4(), goal_id=goal_id, description="do X",
              status=TaskStatus.COMPLETED)
    t2 = Task(id=uuid.uuid4(), goal_id=goal_id, description="do Y",
              status=TaskStatus.PENDING, decision_id=uuid.uuid4())
    dep = TaskDependency(goal_id=goal_id, task_id=t2.id, depends_on_task_id=t1.id)
    graph = TaskGraph([t1, t2], [dep])
    r1 = build_decision_request(goal=goal, task=t2, graph=graph)
    r2 = build_decision_request(goal=goal, task=t2, graph=graph)
    assert r1.workspace_id == ws_id and r1.agent_id == ag_id
    assert r1.objective == "obj" and r1.proposed_action == "do Y"
    assert r1.requested_autonomy_level == 2
    assert str(t2.id) in r1.situation and "previous_decision" in r1.situation
    assert r1 == r2
    assert t2.status is TaskStatus.PENDING and goal.status is GoalStatus.ACTIVE


@pytest.mark.parametrize(
    "control,effect,attempt,error,expected",
    [
        (ControlOutcome.ALLOW, "confirmed", uuid.uuid4(), None, TaskStatus.COMPLETED),
        (ControlOutcome.ALLOW, "none", uuid.uuid4(), None, TaskStatus.FAILED),
        (ControlOutcome.ALLOW, "none", None, "NO_HANDLER_REGISTERED: x",
         TaskStatus.BLOCKED),
        (ControlOutcome.ALLOW, "none", None, "HANDLER_ABSENT: x",
         TaskStatus.BLOCKED),
        (ControlOutcome.ALLOW, "unknown", uuid.uuid4(), None, TaskStatus.BLOCKED),
        (ControlOutcome.DENY, "none", None, None, TaskStatus.BLOCKED),
        (ControlOutcome.STOP, None, None, None, TaskStatus.BLOCKED),
        (ControlOutcome.ESCALATE, "none", None, "CLASSIFICATION_UNCERTAIN",
         TaskStatus.BLOCKED),
    ],
)
def test_decide_task_transition_table(control, effect, attempt, error, expected):
    resp = _response(control, effect, attempt, error)
    assert decide_task_transition(resp) is expected


@pytest.mark.asyncio
async def test_close_is_idempotent_on_terminal(db_session, workspace_agent):
    ws, agent = workspace_agent
    decision = await _persisted_decision(db_session, ws, agent)
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    t = Task(goal_id=goal.id, description="t", status=TaskStatus.RUNNING,
             decision_id=decision.id)
    db_session.add(t)
    await db_session.commit()
    task_id, goal_id, decision_pk = t.id, goal.id, decision.id
    resp = _response(ControlOutcome.ALLOW, "confirmed", uuid.uuid4(), None,
                     decision_id=decision_pk)
    first = await _close_task_with_outcome(db_session, task_id=task_id, response=resp)
    assert first.closed is True and first.to_status is TaskStatus.COMPLETED
    second = await _close_task_with_outcome(db_session, task_id=task_id, response=resp)
    assert second.closed is False and second.reason == "ALREADY_TERMINAL"
    await db_session.rollback()
    db_session.expire_all()
    check = await _fetch(db_session, Task, task_id)
    assert check.status is TaskStatus.COMPLETED
    assert check.decision_id is not None



@pytest.mark.asyncio
async def test_w1_orphan_grace_then_failed_never_ready(db_session, workspace_agent):
    ws, agent = workspace_agent
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    t = Task(goal_id=goal.id, description="orphan", status=TaskStatus.RUNNING)
    db_session.add(t)
    await db_session.commit()
    w1_task_id, w1_goal_id = t.id, goal.id

    fresh = await _recover_one_orphan(db_session, goal_id=w1_goal_id)
    assert fresh.recovered is False and fresh.reason == "GRACE_NOT_EXPIRED"

    old = await _recover_one_orphan(
        db_session, goal_id=w1_goal_id, orphan_grace_seconds=0
    )
    assert old.recovered is True and old.to_status is TaskStatus.FAILED
    await db_session.rollback()
    db_session.expire_all()
    check = await _fetch(db_session, Task, w1_task_id)
    assert check.status is TaskStatus.FAILED
    g = await _fetch(db_session, Goal, w1_goal_id)
    assert g.goal_metadata["last_orphan_recovery"]["kind"] == "W1_NO_ACTION"


def _action(ws, agent, task_id, scope: str) -> ActionRecord:
    return ActionRecord(
        workspace_id=ws.id, agent_id=agent.id, task_id=task_id,
        objective="probe", tool="t", operation="op", arguments={},
        permission_required=PermissionAction.READ, risk_level=RiskLevel.low,
        risk_reversibility=ReversibilityLevel.reversible,
        risk_impact=ImpactType.internal,
        canonical_fingerprint=f"fp-{scope}", idempotency_key=f"idem-{scope}",
        version=1,
    )


@pytest.mark.asyncio
async def test_w2_expired_lease_unknown_goes_blocked(db_session, workspace_agent):
    ws, agent = workspace_agent
    decision = await _persisted_decision(db_session, ws, agent)
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    t = Task(goal_id=goal.id, description="w2", status=TaskStatus.RUNNING)
    db_session.add(t)
    await db_session.flush()
    scope = uuid.uuid4().hex[:8]
    a = _action(ws, agent, t.id, scope)
    db_session.add(a)
    await db_session.flush()
    auth = ExecutionAuthorization(
        workspace_id=ws.id, agent_id=agent.id, action_id=a.id,
        decision_id=decision.id, outcome=ControlOutcome.ALLOW,
        reason_code="PROBE", action_fingerprint=a.canonical_fingerprint,
        action_version=1,
    )
    db_session.add(auth)
    await db_session.flush()
    att = ExecutionAttempt(
        action_id=a.id, authorization_id=auth.id, workspace_id=ws.id,
        attempt_number=1, idempotency_key=f"ea-{scope}",
        status=AttemptStatus.RUNNING,
        lease_expires_at=_now() - timedelta(seconds=5),
    )
    db_session.add(att)
    await db_session.commit()
    w2_goal_id, w2_att_id = goal.id, att.id

    res = await _recover_one_orphan(
        db_session, goal_id=w2_goal_id, orphan_grace_seconds=0
    )
    assert res.recovered is True and res.to_status is TaskStatus.BLOCKED
    assert res.reason == "W2_UNKNOWN"
    await db_session.rollback()
    db_session.expire_all()
    check_att = await _fetch(db_session, ExecutionAttempt, w2_att_id)
    assert check_att.status is AttemptStatus.UNKNOWN


@pytest.mark.asyncio
async def test_w2_succeeded_attempt_completes_task(db_session, workspace_agent):
    ws, agent = workspace_agent
    decision = await _persisted_decision(db_session, ws, agent)
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    t = Task(goal_id=goal.id, description="w2ok", status=TaskStatus.RUNNING)
    db_session.add(t)
    await db_session.flush()
    scope = uuid.uuid4().hex[:8]
    a = _action(ws, agent, t.id, scope)
    db_session.add(a)
    await db_session.flush()
    auth = ExecutionAuthorization(
        workspace_id=ws.id, agent_id=agent.id, action_id=a.id,
        decision_id=decision.id, outcome=ControlOutcome.ALLOW,
        reason_code="PROBE", action_fingerprint=a.canonical_fingerprint,
        action_version=1,
    )
    db_session.add(auth)
    await db_session.flush()
    att = ExecutionAttempt(
        action_id=a.id, authorization_id=auth.id, workspace_id=ws.id,
        attempt_number=1, idempotency_key=f"ea-{scope}",
        status=AttemptStatus.SUCCEEDED,
    )
    db_session.add(att)
    await db_session.commit()
    w2ok_goal_id = goal.id
    res = await _recover_one_orphan(
        db_session, goal_id=w2ok_goal_id, orphan_grace_seconds=0
    )
    assert res.recovered is True and res.to_status is TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_wake_goal_e2e_handler_absent_goes_blocked(db_session, workspace_agent):
    """P0-1 : wake e2e avec contrat orchestrateur sans handler → BLOCKED (T3)."""
    ws, agent = workspace_agent
    decision = await _persisted_decision(db_session, ws, agent)
    decision_pk = decision.id
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    t = Task(goal_id=goal.id, description="real task", status=TaskStatus.READY)
    db_session.add(t)
    await db_session.commit()
    goal_pk = goal.id

    resp = _response(
        ControlOutcome.ALLOW, "none", None,
        "NO_HANDLER_REGISTERED: Aucun handler pour t.op",
        decision_id=decision_pk,
    )

    def _factory(db, _resp=resp):
        return _ContractOrchestrator(db, _resp)

    res = await wake_goal(db_session, goal_id=goal_pk, orchestrator_factory=_factory)
    assert res.task_id is not None
    assert res.execution_effect == "none"
    await db_session.rollback()
    db_session.expire_all()
    check = (
        await db_session.execute(select(Task).where(Task.id == res.task_id))
    ).scalar_one()
    assert check.status is TaskStatus.BLOCKED
    assert check.decision_id == decision_pk


@pytest.mark.asyncio
async def test_wake_goal_e2e_confirmed_completes_and_heals_counter(
    db_session, workspace_agent
):
    """P0-1b : ALLOW+confirmed → COMPLETED + compteur guéri."""
    ws, agent = workspace_agent
    decision = await _persisted_decision(db_session, ws, agent)
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    db_session.add_all(
        [Task(goal_id=goal.id, description=f"t-{i}", status=TaskStatus.READY)
         for i in range(2)]
    )
    await db_session.commit()
    goal_pk = goal.id
    resp = _response(
        ControlOutcome.ALLOW, "confirmed", uuid.uuid4(), None,
        decision_id=decision.id,
    )

    def _factory(db, _resp=resp):
        return _ContractOrchestrator(db, _resp)

    res = await wake_goal(db_session, goal_id=goal_pk, orchestrator_factory=_factory)
    assert res.execution_effect == "confirmed"
    await db_session.rollback()
    db_session.expire_all()
    done = (
        await db_session.execute(select(Task).where(Task.id == res.task_id))
    ).scalar_one()
    assert done.status is TaskStatus.COMPLETED
    g = (await db_session.execute(select(Goal).where(Goal.id == goal_pk))).scalar_one()
    current = int((g.goal_metadata.get("usage") or {}).get("current_steps", 0))
    assert current >= 1


async def _run_wakes(goal_id, n_workers, factory):
    async def _one():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL, poolclass=None)
        maker = async_sessionmaker(bind=engine, expire_on_commit=False)
        try:
            async with maker() as session:
                return await wake_goal(session, goal_id=goal_id,
                                       orchestrator_factory=factory)
        finally:
            await engine.dispose()

    return list(await asyncio.gather(*(_one() for _ in range(n_workers))))


@pytest.mark.asyncio
@pytest.mark.parametrize("n_workers", [2, 5, 10])
async def test_double_wake_no_duplicate_admission(
    db_session, workspace_agent, n_workers
):
    ws, agent = workspace_agent
    decision = await _persisted_decision(db_session, ws, agent)
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    db_session.add_all(
        [Task(goal_id=goal.id, description=f"t-{i}", status=TaskStatus.READY)
         for i in range(10)]
    )
    await db_session.commit()
    goal_pk = goal.id
    resp = _response(
        ControlOutcome.ALLOW, "none", None, "NO_HANDLER_REGISTERED: x",
        decision_id=decision.id,
    )

    def _factory(db, _resp=resp):
        return _ContractOrchestrator(db, _resp)

    results = await _run_wakes(goal_pk, n_workers, _factory)
    admitted = [r for r in results if r.task_id is not None]
    ids = [r.task_id for r in admitted]
    print(f"\nWAKE workers={n_workers} admitted={len(admitted)} unique={len(set(ids))} "
          f"statuses={[r.status for r in results]}")
    assert len(set(ids)) == len(ids)
    assert len(admitted) <= 10


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [(GoalStatus.COMPLETED, "GOAL_TERMINAL"), (GoalStatus.FAILED, "GOAL_TERMINAL"),
     (GoalStatus.CANCELLED, "GOAL_TERMINAL"), (GoalStatus.PAUSED, "GOAL_PAUSED")],
)
async def test_wake_refuses_non_executable_goal(
    db_session, workspace_agent, status, expected
):
    ws, agent = workspace_agent
    goal = _make_goal(ws, agent, status=status)
    db_session.add(goal)
    await db_session.flush()
    db_session.add(Task(goal_id=goal.id, description="t", status=TaskStatus.READY))
    await db_session.commit()
    res = await wake_goal(db_session, goal_id=goal.id)
    assert res.task_id is None
    assert res.status == expected


def test_retry_limit_is_declared_but_unenforced():
    """Frontière §18 : max_task_retries=2 posé, jamais lu — STOP documenté."""
    import pathlib

    text = pathlib.Path("app/goal_engine/services/autonomous_loop.py").read_text(
        encoding="utf-8"
    )
    assert "max_task_retries" not in text


@pytest.mark.asyncio
async def test_wake_goal_aborts_when_admission_sees_non_executable_goal(
    db_session, workspace_agent, monkeypatch
):
    """Course A0→admission : GOAL_NOT_EXECUTABLE → aucun effet de bord.

    Le statut a changé sous le verrou (PAUSED/CANCELLED/terminal). On exige
    que wake_goal NE tente PAS de récupération d'orphelin ni de stalemate :
    la tâche RUNNING doit rester intacte et le Goal inchangé.
    """
    from app.goal_engine.services import autonomous_loop as loop

    async def _fake_admit(db, *, goal_id):
        return loop.AdmitResult(admitted=False, reason="GOAL_NOT_EXECUTABLE")

    monkeypatch.setattr(loop, "_admit_one_step", _fake_admit)

    ws, agent = workspace_agent
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    # RUNNING ancienne (grâce dépassée) : sans la garde, la récupération
    # W1 la passerait à FAILED (effet de bord interdit sur Goal non exécutable).
    t = Task(
        goal_id=goal.id, description="orphan", status=TaskStatus.RUNNING,
        updated_at=_now() - timedelta(hours=2),
    )
    db_session.add(t)
    await db_session.commit()
    task_id, goal_pk = t.id, goal.id

    res = await loop.wake_goal(db_session, goal_id=goal_pk, orphan_grace_seconds=0)
    assert res.status == "GOAL_NOT_EXECUTABLE"
    assert res.task_id is None
    await db_session.rollback()
    db_session.expire_all()
    check = await _fetch(db_session, Task, task_id)
    assert check.status is TaskStatus.RUNNING  # aucun effet de bord
    g = await _fetch(db_session, Goal, goal_pk)
    assert "last_orphan_recovery" not in (g.goal_metadata or {})


@pytest.mark.asyncio
async def test_admission_blocks_on_unmet_dag_upstream(db_session, workspace_agent):
    """CRITICAL-1 : READY en DB mais amont non COMPLETED → jamais admise."""
    ws, agent = workspace_agent
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    up = Task(goal_id=goal.id, description="up", status=TaskStatus.RUNNING)
    down = Task(goal_id=goal.id, description="down", status=TaskStatus.READY)
    db_session.add_all([up, down])
    await db_session.flush()
    db_session.add(
        TaskDependency(goal_id=goal.id, task_id=down.id, depends_on_task_id=up.id)
    )
    await db_session.commit()
    up_id, down_id = up.id, down.id

    res = await _admit_one_step(db_session, goal_id=goal.id)
    assert res.admitted is False and res.reason == "NO_READY_TASK"
    await db_session.rollback()
    db_session.expire_all()
    check = await _fetch(db_session, Task, down_id)
    assert check.status is TaskStatus.READY
    upstream = await _fetch(db_session, Task, up_id)
    assert upstream.status is TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_admission_allows_ready_task_with_completed_upstream(
    db_session, workspace_agent
):
    """CRITICAL-1 (versant positif) : amonts COMPLETED → admission normale."""
    ws, agent = workspace_agent
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    up = Task(goal_id=goal.id, description="up", status=TaskStatus.COMPLETED)
    down = Task(goal_id=goal.id, description="down", status=TaskStatus.READY)
    db_session.add_all([up, down])
    await db_session.flush()
    db_session.add(
        TaskDependency(goal_id=goal.id, task_id=down.id, depends_on_task_id=up.id)
    )
    await db_session.commit()
    down_id = down.id

    res = await _admit_one_step(db_session, goal_id=goal.id)
    assert res.admitted is True and res.task_id == down_id


@pytest.mark.asyncio
async def test_admission_refuses_cancelled_goal_under_lock(db_session, workspace_agent):
    """P2 : CANCELLED pendant admission → refus atomique, rien consommé."""
    ws, agent = workspace_agent
    goal = _make_goal(ws, agent, status=GoalStatus.CANCELLED)
    db_session.add(goal)
    await db_session.flush()
    t = Task(goal_id=goal.id, description="t", status=TaskStatus.READY)
    db_session.add(t)
    await db_session.commit()
    task_id, goal_pk = t.id, goal.id

    res = await _admit_one_step(db_session, goal_id=goal_pk)
    assert res.admitted is False and res.reason == "GOAL_NOT_EXECUTABLE"
    await db_session.rollback()
    db_session.expire_all()
    check = await _fetch(db_session, Task, task_id)
    assert check.status is TaskStatus.READY
    g = await _fetch(db_session, Goal, goal_pk)
    assert int((g.goal_metadata.get("usage") or {}).get("current_steps", 0)) == 0


@pytest.mark.asyncio
async def test_wake_with_no_ready_task_does_not_report_stalemate_while_running(
    db_session, workspace_agent
):
    """P2 : DAG sans READY mais avec une RUNNING → pas de stalemate, pas de vol."""
    ws, agent = workspace_agent
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    up = Task(goal_id=goal.id, description="up", status=TaskStatus.RUNNING)
    down = Task(goal_id=goal.id, description="down", status=TaskStatus.PENDING)
    db_session.add_all([up, down])
    await db_session.flush()
    db_session.add(
        TaskDependency(goal_id=goal.id, task_id=down.id, depends_on_task_id=up.id)
    )
    await db_session.commit()
    up_id, goal_pk = up.id, goal.id

    # Deux lectures orphelines AVANT : la grâce (300 s par défaut) doit protéger
    # l'orphelin frais. Non-régression du bug mesuré « updated_at naïf /
    # timestamptz » : sans compensation, la ligne (écrite 0.02 s plus tôt)
    # apparaissait vieille de 3600 s → vol de tâche.
    probe = await _recover_one_orphan(db_session, goal_id=goal_pk)
    assert probe.recovered is False
    assert probe.reason == "GRACE_NOT_EXPIRED"

    res = await wake_goal(db_session, goal_id=goal_pk)
    assert res.task_id is None
    assert res.status == GoalStatus.ACTIVE.value
    await db_session.rollback()
    db_session.expire_all()
    check = await _fetch(db_session, Task, up_id)
    assert check.status is TaskStatus.RUNNING  # jamais volée
    g = await _fetch(db_session, Goal, goal_pk)
    assert g.status is GoalStatus.ACTIVE  # pas de stalemate tant qu'une RUNNING existe
    assert "last_orphan_recovery" not in (g.goal_metadata or {})
    check = await _fetch(db_session, Task, up_id)
    assert check.status is TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_wake_goal_all_completed_sets_proof_pending(db_session, workspace_agent):
    """P2 : toutes les Tasks COMPLETED → proof_pending, jamais COMPLETED direct."""
    ws, agent = workspace_agent
    decision = await _persisted_decision(db_session, ws, agent)
    goal = _make_goal(ws, agent)
    db_session.add(goal)
    await db_session.flush()
    t = Task(goal_id=goal.id, description="solo", status=TaskStatus.READY)
    db_session.add(t)
    await db_session.commit()
    goal_pk = goal.id

    resp = _response(ControlOutcome.ALLOW, "confirmed", uuid.uuid4(), None,
                     decision_id=decision.id)

    def _factory(db, _resp=resp):
        return _ContractOrchestrator(db, _resp)

    res = await wake_goal(db_session, goal_id=goal_pk, orchestrator_factory=_factory)
    assert res.status == "AWAITING_PROOF"
    await db_session.rollback()
    db_session.expire_all()
    g = (await db_session.execute(select(Goal).where(Goal.id == goal_pk))).scalar_one()
    assert g.goal_metadata.get("proof_pending") is True
    assert g.status is GoalStatus.ACTIVE  # jamais COMPLETED sans preuve externe
