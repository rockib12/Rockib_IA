"""Modèles Goal/Task : garanties de persistance sur PostgreSQL réel (§10).

Les défauts SQLAlchemy (``default=uuid.uuid4``, statut, priorité, métadonnées) ne
s'appliquent qu'au flush : ces tests passent par une vraie session PostgreSQL pour
prouver les valeurs persistées, le sens des Enums natifs (``goal_status``,
``task_status``, migration 003) et la cascade de suppression. Les mocks seuls ne
prouvent rien — doctrine §10.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.goal_engine.models import Goal, GoalStatus
from app.task_engine.models import Task, TaskStatus

pytestmark = pytest.mark.asyncio


def _make_goal(workspace, agent, **overrides) -> Goal:
    values = dict(
        workspace_id=workspace.id,
        agent_id=agent.id,
        objective="Atteindre un objectif vérifiable",
        requested_autonomy_level=2,
        applied_autonomy_level=2,
    )
    values.update(overrides)
    return Goal(**values)


def _make_task(goal: Goal, **overrides) -> Task:
    values = dict(
        goal_id=goal.id,
        description="Première tâche bornée",
    )
    values.update(overrides)
    return Task(**values)


async def test_goal_flush_assigns_id_and_defaults(db_session, workspace_agent):
    """Un Goal flushé reçoit identifiant, statut par défaut et horodatage.

    Avant le flush, ``id`` vaut ``None`` : les défauts Python-side de SQLAlchemy
    s'appliquent à l'INSERT, pas à la construction.
    """
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent)
    assert goal.id is None  # pas encore flushé : aucun défaut appliqué

    db_session.add(goal)
    await db_session.flush()

    assert isinstance(goal.id, uuid.UUID)
    assert goal.status is GoalStatus.PENDING
    assert goal.priority == 1
    assert goal.goal_metadata == {}
    assert goal.created_at is not None


async def test_task_flush_assigns_id_and_links_goal(db_session, workspace_agent):
    """Une Task flushée reçoit son identifiant et résout sa relation vers le Goal."""
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent)
    db_session.add(goal)
    await db_session.flush()

    task = _make_task(goal)
    db_session.add(task)
    await db_session.flush()

    assert isinstance(task.id, uuid.UUID)
    assert task.status is TaskStatus.PENDING

    await db_session.refresh(task, ["goal"])
    assert task.goal is not None
    assert task.goal.id == goal.id


async def test_goal_status_enum_roundtrip(db_session, workspace_agent):
    """Le statut traversé PostgreSQL conserve le sens de l'Enum natif ``goal_status``."""
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent, status=GoalStatus.ACTIVE)
    db_session.add(goal)
    await db_session.flush()

    await db_session.refresh(goal)
    assert goal.status is GoalStatus.ACTIVE


async def test_goal_deletion_cascades_to_tasks(db_session, workspace_agent):
    """Supprimer un Goal supprime ses tâches : aucun état orphelin en base."""
    workspace, agent = workspace_agent
    goal = _make_goal(workspace, agent)
    db_session.add(goal)
    await db_session.flush()

    task = _make_task(goal)
    db_session.add(task)
    await db_session.flush()
    task_id = task.id

    await db_session.delete(goal)
    await db_session.flush()

    remaining = (
        await db_session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    assert remaining is None
