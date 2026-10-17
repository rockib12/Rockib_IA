import pytest
import uuid
import json
from unittest.mock import AsyncMock, Mock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.cognitive.schemas import CognitiveOutput
from app.core.dependencies import get_async_db, get_current_user
from app.core.security import create_access_token
from app.decision_engine.models import (
    ControlOutcome,
    DecisionStatus,
    PermissionAction,
    RiskLevel,
)
from app.decision_engine.schemas import DecisionRequest
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.execution.models import ActionRecord
from app.identity.models import Agent, User
from app.intelligence.schemas import IntelligenceOutput
from app.connectors.agent_connectors import agent_spawn_handler


@pytest.mark.asyncio
async def test_post_agent_without_jwt_returns_401():
    """Vérifie qu'un appel à POST /api/v1/agents sans token JWT valide reçoit 401 Unauthorized."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agents",
            json={
                "workspace_id": str(uuid.uuid4()),
                "name": "Unauthenticated Agent",
                "role": "Attacker",
                "default_autonomy_level": 3,
                "parent_agent_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_agent_user_not_workspace_member_returns_403():
    """Vérifie qu'un utilisateur authentifié mais non membre du workspace ciblé reçoit 403 Forbidden."""
    user_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        email="outsider@example.com",
        password_hash="hashed_pw",
        is_active=True,
    )
    token = create_access_token({"sub": str(user_id)})

    mock_db = AsyncMock()
    # Le membership query renvoie None (non-membre)
    mock_result_membership = Mock()
    mock_result_membership.first.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result_membership)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_async_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agents",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "workspace_id": str(uuid.uuid4()),
                    "name": "Unauthorized Agent",
                    "role": "Worker",
                    "default_autonomy_level": 2,
                    "parent_agent_id": str(uuid.uuid4()),
                },
            )
            assert response.status_code == 403
            data = response.json()
            assert "vous n'êtes pas membre de cet espace de travail" in data["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_agent_missing_parent_agent_id_returns_400():
    """Vérifie que l'absence de parent_agent_id renvoie formellement 400 Bad Request."""
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        email="member@example.com",
        password_hash="hashed_pw",
        is_active=True,
    )
    token = create_access_token({"sub": str(user_id)})

    mock_db = AsyncMock()
    # Le membership query renvoie un enregistrement (membre du workspace)
    mock_result_membership = Mock()
    mock_result_membership.first.return_value = (workspace_id, user_id, "member")
    mock_db.execute = AsyncMock(return_value=mock_result_membership)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_async_db] = lambda: mock_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agents",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "workspace_id": str(workspace_id),
                    "name": "Orphan Agent Without Parent",
                    "role": "Worker",
                    "default_autonomy_level": 2,
                    "parent_agent_id": None,  # Absent ou nul
                },
            )
            assert response.status_code == 400
            data = response.json()
            assert "parent_agent_id is required" in data["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_agent_spawn_without_policy_escalates_and_creates_no_agent():
    """Vérifie que le pipeline complet sans policy pour 'agent' escalade et ne crée aucun agent."""
    workspace_id = uuid.uuid4()
    caller_agent_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_scalars = Mock()
    mock_scalars.all.return_value = []
    mock_result = Mock()
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one.return_value = Agent(
        id=caller_agent_id,
        workspace_id=workspace_id,
        name="Parent Agent",
        role="Orchestrator",
        is_active=True,
        default_autonomy_level=2,
    )
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = Mock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.flush = AsyncMock()

    classifier = DomainClassifier(mapping={"spawn": ("agent", PermissionAction.CREATE)})
    arbitrator = DeterministicArbitrator(db=mock_db)

    cog_service = AsyncMock()
    cog_service.simulate.return_value = CognitiveOutput(action="spawn sub-agent", confidence=0.8)

    intel_service = AsyncMock()
    intel_service.evaluate.return_value = IntelligenceOutput(
        suggested_action="spawn sub-agent",
        confidence=0.8,
        risk_level="medium",
        is_rational=True,
        reasons=[],
    )

    orchestrator = DecisionOrchestrator(
        db=mock_db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intel_service,
        cognitive_simulator=cog_service,
    )

    request = DecisionRequest(
        workspace_id=workspace_id,
        agent_id=caller_agent_id,
        objective="Spawn sub-agent 'Worker 1'",
        situation="Auto scale request",
        proposed_action='spawn agent {"name": "Worker 1", "role": "Coder"}',
        requested_autonomy_level=2,
    )

    resp = await orchestrator.handle_decision(request)

    # Sans config dans decision_domain_config :
    assert resp.approval_required is True
    assert resp.permission_granted is False
    assert resp.control_outcome in (ControlOutcome.ESCALATE, ControlOutcome.STOP)

    # Vérifier qu'aucun nouvel Agent n'a été inséré dans le mock_db
    added_classes = [call.args[0].__class__.__name__ for call in mock_db.add.call_args_list]
    assert "Agent" not in added_classes


@pytest.mark.asyncio
@patch("app.connectors.agent_connectors.AsyncSessionLocal")
async def test_agent_spawn_execution_with_valid_authorization_creates_agent(mock_session_local):
    """Vérifie qu'après autorisation valide, agent_spawn_handler crée l'agent en base."""
    mock_db = mock_session_local.return_value.__aenter__.return_value
    mock_db.add = Mock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None)))

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        decision_id=uuid.uuid4(),
        tool="agent",
        operation="spawn",
        arguments={
            "name": "Authorized SubAgent",
            "role": "Analyst",
            "objective": "Deep data analysis",
        },
    )

    res = await agent_spawn_handler(action)
    assert res.success is True
    assert "Successfully spawned sub-agent 'Authorized SubAgent'" in res.output

    # Vérifie l'insertion de l'Agent, du Goal et de la Task
    added_entities = [call.args[0] for call in mock_db.add.call_args_list]
    agent_entries = [e for e in added_entities if isinstance(e, Agent)]
    assert len(agent_entries) == 1
    assert agent_entries[0].name == "Authorized SubAgent"
    assert agent_entries[0].role == "Analyst"


@pytest.mark.asyncio
async def test_agent_spawn_autonomy_clamped_by_caller_agent():
    """Vérifie qu'un agent appelant avec autonomie=1 tentant de spawner un enfant avec autonomie=5
    voit la DecisionRequest plafonnée à min(5, 1) = 1 (règle stricte enfant <= parent)."""
    from app.goal_engine.router import create_agent, CreateAgentRequest

    workspace_id = uuid.uuid4()
    parent_id = uuid.uuid4()

    mock_user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash="hashed_pw",
        is_active=True,
    )

    caller_agent = Agent(
        id=parent_id,
        workspace_id=workspace_id,
        name="Low Autonomy Parent",
        role="Worker",
        is_active=True,
        default_autonomy_level=1,  # Autonomie parent = 1
    )

    mock_db = AsyncMock()
    # 1er appel execute: vérification membership workspace -> membre
    # 2eme appel execute: select Agent parent -> caller_agent
    mock_result_membership = Mock()
    mock_result_membership.first.return_value = (workspace_id, mock_user.id, "admin")
    mock_result_parent = Mock()
    mock_result_parent.scalar_one_or_none.return_value = caller_agent

    mock_db.execute = AsyncMock(side_effect=[mock_result_membership, mock_result_parent])

    payload = CreateAgentRequest(
        workspace_id=workspace_id,
        name="High Autonomy Child",
        role="Coder",
        default_autonomy_level=5,  # Demande d'autonomie enfant = 5
        parent_agent_id=parent_id,
    )

    mock_classifier = Mock()
    mock_cog = Mock()
    mock_intel = Mock()

    with patch("app.goal_engine.router.DecisionOrchestrator") as MockOrchestrator:
        mock_orch_instance = MockOrchestrator.return_value
        mock_decision_resp = Mock(
            approval_required=True,
            permission_granted=False,
            control_outcome=ControlOutcome.ESCALATE,
            control_reason="APPROVAL_REQUIRED",
            decision_id=str(uuid.uuid4()),
        )
        mock_orch_instance.handle_decision = AsyncMock(return_value=mock_decision_resp)

        with pytest.raises(Exception):
            await create_agent(
                payload=payload,
                db=mock_db,
                current_user=mock_user,
                classifier=mock_classifier,
                cognitive_simulator=mock_cog,
                intelligence_service=mock_intel,
            )

        # Vérifier l'appel à handle_decision
        mock_orch_instance.handle_decision.assert_called_once()
        sent_request = mock_orch_instance.handle_decision.call_args[0][0]
        # L'autonomie demandée DOIT être 1 (min(5, 1)), JAMAIS 5
        assert sent_request.requested_autonomy_level == 1
