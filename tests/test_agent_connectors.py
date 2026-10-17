import pytest
import uuid
from unittest.mock import patch, MagicMock, AsyncMock

from app.execution.models import ActionRecord
from app.connectors.agent_connectors import agent_spawn_handler

@pytest.fixture
def fake_action_agent():
    return ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        decision_id=uuid.uuid4(),
        tool="agent",
        operation="spawn",
        arguments={"name": "Test Sub-Agent", "objective": "Do some task"}
    )

@pytest.mark.asyncio
async def test_agent_spawn_missing_args():
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="agent",
        operation="spawn",
        arguments={"name": "Only Name"}
    )
    result = await agent_spawn_handler(action)
    assert not result.success
    assert result.error_code == "MISSING_ARGS"

@pytest.mark.asyncio
@patch("app.connectors.agent_connectors.AsyncSessionLocal")
async def test_agent_spawn_success(mock_session_local, fake_action_agent):
    mock_db = mock_session_local.return_value.__aenter__.return_value
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    
    result = await agent_spawn_handler(fake_action_agent)
    
    assert result.success
    assert "Successfully spawned sub-agent" in result.output
    # Il doit ajouter un Agent, un Goal, et une Task
    assert mock_db.add.call_count == 3
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
@patch("app.connectors.agent_connectors.AsyncSessionLocal")
async def test_agent_spawn_bounds_child_autonomy_by_parent(mock_session_local):
    """Vérifie que l'agent enfant ne dépasse jamais l'autonomie de son parent (ex: parent=1, req=4 -> child=1)."""
    from app.identity.models import Agent
    from app.goal_engine.models import Goal

    mock_db = mock_session_local.return_value.__aenter__.return_value
    added_entities = []
    mock_db.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))
    mock_db.commit = AsyncMock()

    parent_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="Parent Agent",
        default_autonomy_level=1,
    )

    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=parent_agent))
    )

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=parent_agent.workspace_id,
        agent_id=parent_agent.id,
        tool="agent",
        operation="spawn",
        arguments={
            "name": "Overambitious Child",
            "objective": "High autonomy task",
            "requested_autonomy_level": 4,
            "default_autonomy_level": 5,
        },
    )

    result = await agent_spawn_handler(action)
    assert result.success

    # Vérifier l'autonomie assignée au sous-agent et au goal
    spawned_agent = next(e for e in added_entities if isinstance(e, Agent))
    spawned_goal = next(e for e in added_entities if isinstance(e, Goal))

    assert spawned_agent.default_autonomy_level == 1
    assert spawned_goal.applied_autonomy_level == 1
    assert spawned_goal.applied_autonomy_level <= parent_agent.default_autonomy_level

