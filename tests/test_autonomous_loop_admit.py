"""STEP 5C — Test de concurrence de ``_admit_one_step()`` (M5, isolée).

Sans orchestrateur : N workers asyncio × sessions indépendantes appellent
``_admit_one_step()`` en rafale sur le même goal. On vérifie que la limite
``max_steps`` n'est JAMAIS dépassée et que deux workers ne claiment jamais
la même tâche.

Matrice exigée : workers {2, 5, 10} × max_steps {1, 2, 10}.
``n_tasks`` est volontairement large (10) pour que seul ``max_steps``
borne l'admission — jamais le manque de tâches READY.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.autonomous_loop import _admit_one_step
from app.task_engine.models import Task, TaskStatus


def _make_goal(ws, agent, *, max_steps: int) -> Goal:
    return Goal(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        agent_id=agent.id,
        objective="STEP 5C concurrency probe",
        requested_autonomy_level=2,
        applied_autonomy_level=2,
        status=GoalStatus.ACTIVE,
        goal_metadata={
            "limits": {"max_steps": max_steps},
            "usage": {"current_steps": 0, "replanning_count": 0},
        },
    )


async def _run_workers(goal_id: uuid.UUID, n_workers: int) -> list:
    """Lance N workers concurrents, chacun avec SA PROPRE session.

    Une ``AsyncSession`` n'est pas concurrent-safe : partager ``db_session``
    entre workers fausserait le test (et sérialiserait artificiellement).
    """

    async def _one_worker():
        engine = create_async_engine(settings.ASYNC_DATABASE_URL, poolclass=None)
        maker = async_sessionmaker(bind=engine, expire_on_commit=False)
        try:
            async with maker() as session:
                return await _admit_one_step(session, goal_id=goal_id)
        finally:
            await engine.dispose()

    return list(await asyncio.gather(*(_one_worker() for _ in range(n_workers))))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_workers,max_steps",
    [
        (2, 1),
        (2, 2),
        (2, 10),
        (5, 1),
        (5, 2),
        (5, 10),
        (10, 1),
        (10, 2),
        (10, 10),
    ],
)
async def test_admit_never_exceeds_max_steps(db_session, workspace_agent, n_workers, max_steps):
    ws, agent = workspace_agent

    goal = _make_goal(ws, agent, max_steps=max_steps)
    db_session.add(goal)
    await db_session.flush()
    db_session.add_all(
        [
            Task(goal_id=goal.id, description=f"task-{i}", status=TaskStatus.READY)
            for i in range(10)
        ]
    )
    await db_session.commit()  # publié AVANT la rafale : tous les workers voient le même état
    goal_id = goal.id

    results = await _run_workers(goal_id, n_workers)

    admitted = [r for r in results if r.admitted]
    rejected = [r for r in results if not r.admitted]

    # Brut : qui a été admis / refusé (motif).
    print(f"\nworkers={n_workers} max_steps={max_steps} "
          f"admitted={len(admitted)} rejected={len(rejected)} "
          f"reasons={[r.reason for r in rejected]}")

    # 1. Borne dure : jamais plus de max_steps admissions, jamais plus que N workers.
    assert len(admitted) == min(n_workers, max_steps)
    assert len(admitted) + len(rejected) == n_workers

    # 2. Pas de double-claim : chaque tâche admise est distincte.
    admitted_ids = [r.task_id for r in admitted]
    assert None not in admitted_ids
    assert len(set(admitted_ids)) == len(admitted_ids)

    # 3. État DB : exactement len(admitted) tâches RUNNING, le reste READY.
    await db_session.rollback()  # relecture fraîche post-rafale
    db_session.expire_all()  # purge l'identity map : le goal créé avant la rafale est stale (synchrone)
    n_running = (
        await db_session.execute(
            select(func.count(Task.id)).where(
                Task.goal_id == goal_id, Task.status == TaskStatus.RUNNING
            )
        )
    ).scalar_one()
    n_ready = (
        await db_session.execute(
            select(func.count(Task.id)).where(
                Task.goal_id == goal_id, Task.status == TaskStatus.READY
            )
        )
    ).scalar_one()
    print(f"db: RUNNING={n_running} READY={n_ready}")
    assert n_running == len(admitted)
    assert n_ready == 10 - len(admitted)

    # 4. Réservation : usage.current_steps == nombre d'admissions (1 slot par admission).
    g = (await db_session.execute(select(Goal).where(Goal.id == goal_id))).scalar_one()
    current_steps = int((g.goal_metadata.get("usage") or {}).get("current_steps", 0))
    print(f"db: usage.current_steps={current_steps}")
    assert current_steps == len(admitted)
    assert current_steps <= max_steps

    # 5. Tout refus doit être motivé (LIMIT_HIT quand la borne est atteinte).
    for r in rejected:
        assert r.reason in ("LIMIT_HIT", "NO_READY_TASK")
    if len(admitted) == max_steps and len(rejected) > 0:
        assert all(r.reason == "LIMIT_HIT" for r in rejected)
