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


@pytest.mark.asyncio
async def test_agent_message_missing_content():
    from app.connectors.agent_connectors import agent_message_handler

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="agent",
        operation="send",
        arguments={"recipient_name": "Cyber Agent"},
    )
    result = await agent_message_handler(action)
    assert not result.success
    assert result.error_code == "MISSING_MESSAGE"


@pytest.mark.asyncio
@patch("app.connectors.agent_connectors.AsyncSessionLocal")
async def test_agent_message_p2p_dialogue_success(mock_session_local):
    """Vérifie le bus de dialogue P2P inter-agents et la création d'un AgentMessage."""
    from app.connectors.agent_connectors import agent_message_handler
    from app.identity.models import Agent, AgentMessage

    ws_id = uuid.uuid4()
    sender = Agent(id=uuid.uuid4(), workspace_id=ws_id, name="Architect Agent", role="Lead Architect")
    recipient = Agent(id=uuid.uuid4(), workspace_id=ws_id, name="Security Agent", role="Cybersecurity Specialist")

    mock_db = mock_session_local.return_value.__aenter__.return_value
    added_entities = []
    mock_db.add = MagicMock(side_effect=lambda entity: added_entities.append(entity))
    mock_db.commit = AsyncMock()

    # 1er appel: sender_agent, 2ème appel: recipient_agent par ID
    res_sender = MagicMock(scalar_one_or_none=MagicMock(return_value=sender))
    res_recipient = MagicMock(scalar_one_or_none=MagicMock(return_value=recipient))
    mock_db.execute = AsyncMock(side_effect=[res_sender, res_recipient])

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=sender.id,
        decision_id=uuid.uuid4(),
        tool="agent",
        operation="send",
        arguments={
            "recipient_agent_id": str(recipient.id),
            "subject": "Audit SAST API Payments",
            "message": "Peux-tu valider le schéma HMAC du webhook de paiement avant déploiement ?",
        },
    )

    with patch("app.memory.services.ingestion.store_agent_lesson", new_callable=AsyncMock):
        result = await agent_message_handler(action)

    assert result.success
    assert "Architect Agent -> Security Agent" in result.output
    msg_entities = [e for e in added_entities if isinstance(e, AgentMessage)]
    assert len(msg_entities) == 1
    assert msg_entities[0].sender_agent_id == sender.id
    assert msg_entities[0].recipient_agent_id == recipient.id
    assert msg_entities[0].status == "REPLIED"
    assert msg_entities[0].reply_content is not None


