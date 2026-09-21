"""Garanties de persistance et contraintes d'intégrité du graphe de tâches (§10).

Vérifie sur PostgreSQL réel :
1. L'alignement de l'ENUM task_status (RUNNING, CANCELLED).
2. L'interdiction stricte d'auto-dépendance (CHECK check_task_no_self_dependency).
3. L'unicité des dépendances (UNIQUE uq_task_dependencies_task_depends).
4. La garantie physique que les deux tâches appartiennent au même Goal
   (FK composites fk_task_dependencies_task_goal & fk_task_dependencies_depends_goal).
5. La suppression en cascade (supprimer une tâche ou un Goal supprime les dépendances).
6. Les relations ORM bidirectionnelles Task.dependencies et Task.dependents.
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.goal_engine.models import Goal, GoalStatus
from app.task_engine.models import Task, TaskDependency, TaskStatus

pytestmark = pytest.mark.asyncio


def _make_goal(workspace, agent, **overrides) -> Goal:
    values = dict(
        workspace_id=workspace.id,
        agent_id=agent.id,
        objective="Objectif pour test de graphe de tâches",
        requested_autonomy_level=2,
        applied_autonomy_level=2,
    )
    values.update(overrides)
    return Goal(**values)


def _make_task(goal: Goal, **overrides) -> Task:
    values = dict(
        goal_id=goal.id,
        description="Tâche bornée de test",
    )
    values.update(overrides)
    return Task(**values)


async def test_task_status_running_and_cancelled_roundtrip(db_session, workspace_agent):
    """Vérifie que les statuts RUNNING et CANCELLED sont acceptés par l'Enum PostgreSQL."""
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent)
    db_session.add(goal)
    await db_session.flush()

    task_running = _make_task(goal, description="Tâche en cours", status=TaskStatus.RUNNING)
    task_cancelled = _make_task(goal, description="Tâche annulée", status=TaskStatus.CANCELLED)

    db_session.add_all([task_running, task_cancelled])
    await db_session.flush()

    await db_session.refresh(task_running)
    await db_session.refresh(task_cancelled)

    assert task_running.status is TaskStatus.RUNNING
    assert task_cancelled.status is TaskStatus.CANCELLED


async def test_task_dependency_nominal_and_orm_relationships(db_session, workspace_agent):
    """Création nominale d'une dépendance A -> B et validation des relations ORM."""
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent)
    db_session.add(goal)
    await db_session.flush()

    task_a = _make_task(goal, description="Tâche A (prérequis)")
    task_b = _make_task(goal, description="Tâche B (dépendante de A)")
    db_session.add_all([task_a, task_b])
    await db_session.flush()

    dep = TaskDependency(
        goal_id=goal.id,
        task_id=task_b.id,
        depends_on_task_id=task_a.id,
    )
    db_session.add(dep)
    await db_session.flush()

    await db_session.refresh(task_b, ["dependencies"])
    await db_session.refresh(task_a, ["dependents"])

    # Task B a pour dépendance Task A
    assert len(task_b.dependencies) == 1
    assert task_b.dependencies[0].depends_on_task_id == task_a.id
    assert task_b.dependencies[0].depends_on_task.id == task_a.id

    # Task A a pour dépendante Task B
    assert len(task_a.dependents) == 1
    assert task_a.dependents[0].task_id == task_b.id
    assert task_a.dependents[0].task.id == task_b.id


async def test_task_no_self_dependency(db_session, workspace_agent):
    """Une tâche ne peut pas dépendre d'elle-même (CHECK constraint)."""
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent)
    db_session.add(goal)
    await db_session.flush()

    task = _make_task(goal, description="Tâche réflexive")
    db_session.add(task)
    await db_session.flush()

    dep = TaskDependency(
        goal_id=goal.id,
        task_id=task.id,
        depends_on_task_id=task.id,
    )
    db_session.add(dep)

    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()

    assert "check_task_no_self_dependency" in str(exc_info.value).lower()
    await db_session.rollback()


async def test_task_dependency_duplicate_rejected(db_session, workspace_agent):
    """L'arc de dépendance (task_id, depends_on_task_id) doit être unique."""
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent)
    db_session.add(goal)
    await db_session.flush()

    task_a = _make_task(goal, description="Tâche A")
    task_b = _make_task(goal, description="Tâche B")
    db_session.add_all([task_a, task_b])
    await db_session.flush()

    dep1 = TaskDependency(goal_id=goal.id, task_id=task_b.id, depends_on_task_id=task_a.id)
    dep2 = TaskDependency(goal_id=goal.id, task_id=task_b.id, depends_on_task_id=task_a.id)
    db_session.add(dep1)
    await db_session.flush()

    db_session.add(dep2)
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()

    assert "uq_task_dependencies_task_depends" in str(exc_info.value).lower()
    await db_session.rollback()


async def test_task_dependency_same_goal_enforced(db_session, workspace_agent):
    """Une dépendance entre deux tâches d'objectifs différents est rejetée par la FK composite."""
    workspace, agent = workspace_agent
    goal_1 = _make_goal(workspace, agent, objective="Objectif 1")
    goal_2 = _make_goal(workspace, agent, objective="Objectif 2")
    db_session.add_all([goal_1, goal_2])
    await db_session.flush()

    task_1 = _make_task(goal_1, description="Tâche du Goal 1")
    task_2 = _make_task(goal_2, description="Tâche du Goal 2")
    db_session.add_all([task_1, task_2])
    await db_session.flush()

    # Tentative d'attacher task_2 (Goal 2) dépendant de task_1 (Goal 1) sous le goal_id du Goal 1
    dep = TaskDependency(
        goal_id=goal_1.id,
        task_id=task_2.id,
        depends_on_task_id=task_1.id,
    )
    db_session.add(dep)

    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()

    # La FK composite (task_id, goal_id) échoue car task_2 appartient à goal_2, pas goal_1
    assert "fk_task_dependencies_task_goal" in str(exc_info.value).lower() or "violates foreign key constraint" in str(exc_info.value).lower()
    await db_session.rollback()


async def test_task_dependency_cascade_delete(db_session, workspace_agent):
    """Supprimer une tâche prérequise supprime en cascade la dépendance, mais conserve la tâche dépendante."""
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent)
    db_session.add(goal)
    await db_session.flush()

    task_a = _make_task(goal, description="Tâche A")
    task_b = _make_task(goal, description="Tâche B")
    db_session.add_all([task_a, task_b])
    await db_session.flush()

    dep = TaskDependency(goal_id=goal.id, task_id=task_b.id, depends_on_task_id=task_a.id)
    db_session.add(dep)
    await db_session.flush()
    dep_id = dep.id

    # Supprimer Task A
    await db_session.delete(task_a)
    await db_session.flush()

    # La dépendance a été supprimée par cascade
    remaining_dep = (
        await db_session.execute(select(TaskDependency).where(TaskDependency.id == dep_id))
    ).scalar_one_or_none()
    assert remaining_dep is None

    # Task B existe toujours
    remaining_task_b = (
        await db_session.execute(select(Task).where(Task.id == task_b.id))
    ).scalar_one_or_none()
    assert remaining_task_b is not None
