import asyncio
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.goal_engine.services.wake_runner import WakeRunner
from app.goal_engine.models import Goal, GoalStatus

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_engine():
    engine = AsyncMock()
    return engine

@pytest.fixture
def runner(mock_engine):
    r = WakeRunner(mock_engine)
    return r

async def test_runner_start_stop(runner):
    """Test 5 : Vérifier le Graceful Shutdown."""
    assert not runner._is_running
    runner.start()
    assert runner._is_running
    assert runner._task is not None
    assert not runner._task.done()
    
    await runner.stop()
    assert not runner._is_running
    assert runner._task.done()

@patch("app.goal_engine.services.wake_runner.wake_goal")
async def test_runner_no_goals(mock_wake, runner):
    """Test 1 : Le runner dort s'il n'y a aucun Goal."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    
    worked = await runner._poll_and_wake(mock_db)
    
    assert worked is False
    mock_wake.assert_not_called()

@patch("app.goal_engine.services.wake_runner.wake_goal")
async def test_runner_eligible_goal(mock_wake, runner):
    """Test 2 : Le runner appelle wake_goal pour un Goal éligible."""
    mock_db = AsyncMock()
    gid = uuid.uuid4()
    
    # Mock du select()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [gid]
    mock_db.execute.return_value = mock_result
    
    # Mock de wake_goal
    mock_wake_result = MagicMock()
    mock_wake_result.status = "COMPLETED"
    mock_wake.return_value = mock_wake_result
    
    # Simulation d'exécution du runner allumé
    runner._is_running = True
    worked = await runner._poll_and_wake(mock_db)
    
    assert worked is True
    mock_wake.assert_called_once()
    args, kwargs = mock_wake.call_args
    assert kwargs["goal_id"] == gid

@patch("app.goal_engine.services.wake_runner.wake_goal")
async def test_runner_error_handling(mock_wake, runner):
    """Test 4 : Une erreur sur un Goal n'interrompt pas les suivants."""
    mock_db = AsyncMock()
    gid1 = uuid.uuid4()
    gid2 = uuid.uuid4()
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [gid1, gid2]
    mock_db.execute.return_value = mock_result
    
    # wake_goal échoue sur le premier, passe sur le second
    mock_wake_result = MagicMock()
    mock_wake_result.status = "COMPLETED"
    mock_wake.side_effect = [Exception("Crash !"), mock_wake_result]
    
    runner._is_running = True
    worked = await runner._poll_and_wake(mock_db)
    
    assert worked is True  # Le 2ème a marché
    assert mock_wake.call_count == 2
