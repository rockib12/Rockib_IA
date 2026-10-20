"""Tests unitaires pour les tâches Celery Beat & Worker (STEP 5B/5C).

Vérifie :
1. dispatch_active_goals() dispatche une tâche wake_goal_task par Goal ACTIVE via .delay().
2. wake_goal_task() exécute une seule admission atomique.
3. Simulation de crash worker Celery : la tâche reste RUNNING et M6 (_recover_one_orphan)
   la récupère proprement sans régression d'état ni violation de contraintes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.goal_engine.tasks import dispatch_active_goals, wake_goal_task
from app.goal_engine.services.autonomous_loop import _recover_one_orphan
from app.task_engine.models import Task, TaskStatus
from app.goal_engine.models import Goal, GoalStatus
from app.identity.models import Agent, Workspace


def test_dispatch_active_goals_calls_delay_per_goal():
    """Vérifie que la tâche Beat dispatch_active_goals() envoie un message Celery par Goal."""
    g1 = str(uuid.uuid4())
    g2 = str(uuid.uuid4())

    with patch("app.goal_engine.tasks._dispatch_active_goals_async", return_value=[g1, g2]):
        with patch("app.goal_engine.tasks.wake_goal_task.delay") as mock_delay:
            res = dispatch_active_goals()

            assert "2 active goal(s)" in res
            assert mock_delay.call_count == 2
            mock_delay.assert_any_call(g1)
            mock_delay.assert_any_call(g2)


def test_wake_goal_task_executes_single_step():
    """Vérifie que wake_goal_task exécute exactement une étape atomique sans boucle while."""
    gid = str(uuid.uuid4())
    fake_result = {
        "status": "STEP_COMPLETED",
        "reason": "TASK_COMPLETED",
        "task_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "attempt_id": None,
    }

    with patch("app.goal_engine.tasks._wake_single_goal_async", return_value=fake_result) as mock_wake:
        res = wake_goal_task(gid)

        assert res["status"] == "STEP_COMPLETED"
        assert res["reason"] == "TASK_COMPLETED"
        mock_wake.assert_called_once_with(gid)


@pytest.mark.asyncio
async def test_celery_worker_crash_simulation_recovers_via_m6():
    """Simule un crash brusque (SIGKILL/OOM) d'un worker Celery pendant l'exécution d'un Goal.
    
    La tâche était passée en RUNNING. Au réveil suivant, l'admission constate qu'aucune tâche
    n'est READY et déclenche M6 (_recover_one_orphan), qui passe la tâche en FAILED (W1_NO_ACTION).
    """
    mock_db = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    goal_id = uuid.uuid4()
    task_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    crashed_task = Task(
        id=task_id,
        goal_id=goal_id,
        description="Task interrupted by worker crash",
        status=TaskStatus.RUNNING,
        updated_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )


    goal = Goal(
        id=goal_id,
        workspace_id=workspace_id,
        agent_id=uuid.uuid4(),
        objective="Crash test goal",
        status=GoalStatus.ACTIVE,
        priority=1,
        requested_autonomy_level=2,
        applied_autonomy_level=2,
        goal_metadata={},
    )

    with patch("app.goal_engine.services.autonomous_loop.GoalManager") as MockGoalManager:
        mock_gm = MockGoalManager.return_value
        mock_gm.get_goal = AsyncMock(return_value=goal)

        # Mock query return for task
        mock_result_task = Mock()
        mock_result_task.scalars.return_value.first.return_value = crashed_task

        # Mock query return for actions (W1: no action record created yet)
        mock_result_action = Mock()
        mock_result_action.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [
            None,  # SET TRANSACTION ISOLATION LEVEL
            mock_result_task,
            mock_result_action,
        ]

        # Récupération de l'orphelin
        res = await _recover_one_orphan(mock_db, goal_id=goal_id, orphan_grace_seconds=10)

        # Vérifications M6 :
        assert res.recovered is True
        assert res.to_status == TaskStatus.FAILED
        assert res.reason == "W1_NO_ACTION"
        assert crashed_task.status == TaskStatus.FAILED
        assert goal.goal_metadata["last_orphan_recovery"]["kind"] == "W1_NO_ACTION"
        mock_db.commit.assert_called()
