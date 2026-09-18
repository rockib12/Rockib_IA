import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from app.cognitive.schemas import CognitiveInput, CognitiveOutput
from app.decision_engine.models import (
    ArbitrationRule,
    DecisionDomainConfig,
    PermissionAction,
    RiskLevel,
)
from app.decision_engine.schemas import ClassificationResult, ClassificationStatus, DecisionRequest
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.execution.services.executor import ExecutionResult
from app.intelligence.schemas import IntelligenceInput, IntelligenceOutput
from app.identity.models import Agent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_mock_db():
    """Mock de session DB avec add, commit, refresh, execute."""
    # Mocking result for DB execute
    mock_result = Mock()
    mock_scalars = Mock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    
    # Configure execute to be awaited and return the mock_result
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db

def make_mock_agent():
    """Mock d''un agent valide."""
    agent = Mock(spec=Agent)
    agent.id = "test-agent-123"
    agent.default_autonomy_level = 3
    return agent

def mock_domain_config():
    """Config de domaine pour un arbitrage déterministe simple."""
    return DecisionDomainConfig(
        workspace_id="ws-1",
        domain="finance",
        permission_action=PermissionAction.UPDATE,
        arbitration_rule=ArbitrationRule.consensus_required,
        base_risk_level=RiskLevel.low,
        base_reversibility="reversible",
        base_impact="internal",
        disagreement_threshold=0.5,
        max_autonomy_level=5,
    )

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_db():
    return make_mock_db()

@pytest.fixture
def mock_agent():
    return make_mock_agent()

@pytest.fixture
def decision_request():
    return DecisionRequest(
        workspace_id="ws-1",
        agent_id="test-agent-123",
        objective="Test objective",
        situation="Test situation",
        proposed_action="Test action",
    )

# ---------------------------------------------------------------------------
# Test 1 : Flux nominal (classification CERTAIN)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_orchestrator_full_flow(
    mock_db,
    mock_agent,
    decision_request,
):
    """Vérifie le flux complet : classification CERTAIN -> Cognitive -> Intelligence -> Arbitrage."""
    # Arrange
    cognitive_simulator = AsyncMock()
    cognitive_simulator.simulate.return_value = CognitiveOutput(
        action="cognitive action",
        confidence=0.9,
        reasoning="Cognitive reasoning",
    )

    intelligence_service = AsyncMock()
    intelligence_service.evaluate.return_value = IntelligenceOutput(
        suggested_action="intelligence action",
        confidence=0.8,
        risk_level=RiskLevel.low,
        reasoning="Intelligence reasoning",
    )

    # Mapping : "test" -> CERTAIN. On s''assure que l''action contient "test".
    mapping = {"test": ("finance", PermissionAction.UPDATE)}
    decision_request.proposed_action = "test action"
    
    classifier = DomainClassifier(mapping=mapping)
    arbitrator = DeterministicArbitrator()

    orchestrator = DecisionOrchestrator(
        db=mock_db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )

    with patch(
        "app.decision_engine.services.orchestrator.mine_patterns",
        new_callable=AsyncMock,
    ) as mock_mine_patterns, patch(
        "app.decision_engine.services.orchestrator.execute",
        new_callable=AsyncMock,
    ) as mock_execute, patch(
        "app.decision_engine.services.orchestrator.log_execution",
        new_callable=Mock,
    ) as mock_log_execution, patch.object(
        orchestrator,
        "_load_agent",
        new_callable=AsyncMock,
    ) as mock_load_agent, patch.object(
        orchestrator.arbitrator,
        "_load_domain_config",
        new_callable=AsyncMock,
    ) as mock_load_domain_config:
        mock_mine_patterns.return_value = "Mocked patterns"
        mock_load_agent.return_value = mock_agent
        mock_load_domain_config.return_value = mock_domain_config()
        mock_execute.return_value = ExecutionResult(success=True, output="ok", error=None)

        # Act
        response = await orchestrator.handle_decision(decision_request)

        # Assert
        # 1. Appels obligatoires
        mock_mine_patterns.assert_awaited_once_with(mock_db, decision_request.workspace_id)
        cognitive_simulator.simulate.assert_awaited_once()
        intelligence_service.evaluate.assert_awaited_once()
        mock_load_agent.assert_awaited_once_with(decision_request.agent_id)

        # 2. Vérification des inputs
        cog_input, patterns = cognitive_simulator.simulate.await_args[0]
        assert isinstance(cog_input, CognitiveInput)
        assert cog_input.workspace_id == decision_request.workspace_id
        assert cog_input.objective == decision_request.objective
        assert cog_input.situation == decision_request.situation
        assert patterns == "Mocked patterns"

        intel_input = intelligence_service.evaluate.await_args[0][0]
        assert isinstance(intel_input, IntelligenceInput)
        assert intel_input.objective == decision_request.objective
        assert intel_input.situation == decision_request.situation
        assert intel_input.proposed_action == decision_request.proposed_action
        assert intel_input.domain == "finance"
        assert intel_input.permission_action == PermissionAction.UPDATE

        # 3. Résultat final et persistance
        assert response.decision_id is not None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

# ---------------------------------------------------------------------------
# Test 2 : Escalade sur classification UNKNOWN
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_orchestrator_escalation_unknown(
    mock_db,
    mock_agent,
    decision_request,
):
    """Classification UNKNOWN -> Escalade immédiate, aucun service appelé."""
    intelligence_service = AsyncMock()
    cognitive_simulator = AsyncMock()
    
    classifier = DomainClassifier(mapping={})
    arbitrator = DeterministicArbitrator()

    orchestrator = DecisionOrchestrator(
        db=mock_db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )

    response = await orchestrator.handle_decision(decision_request)

    assert response.approval_required is True
    assert response.dominant_source == "human"
    intelligence_service.evaluate.assert_not_awaited()

# ---------------------------------------------------------------------------
# Test 3 : Escalade sur classification AMBIGUOUS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_orchestrator_escalation_ambiguous(
    mock_db,
    mock_agent,
    decision_request,
):
    """Classification AMBIGUOUS -> Escalade immédiate, aucun service appelé."""
    intelligence_service = AsyncMock()
    cognitive_simulator = AsyncMock()
    
    # Deux mots-clés matchant -> AMBIGUOUS
    mapping = {
        "test": ("finance", PermissionAction.UPDATE),
        "action": ("security", PermissionAction.READ),
    }
    decision_request.proposed_action = "test action"
    
    classifier = DomainClassifier(mapping=mapping)
    arbitrator = DeterministicArbitrator()

    orchestrator = DecisionOrchestrator(
        db=mock_db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )

    response = await orchestrator.handle_decision(decision_request)

    assert response.approval_required is True
    assert response.dominant_source == "human"
    intelligence_service.evaluate.assert_not_awaited()

# ---------------------------------------------------------------------------
# Test 4 : Escalade sur classification ERROR
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_orchestrator_escalation_error(
    mock_db,
    mock_agent,
    decision_request,
):
    """Classification ERROR -> Escalade immédiate, aucun service appelé."""
    intelligence_service = AsyncMock()
    cognitive_simulator = AsyncMock()
    
    # Permission invalide -> ERROR
    mapping = {"test": ("finance", "INVALID_PERMISSION")}
    decision_request.proposed_action = "test action"
    
    classifier = DomainClassifier(mapping=mapping)
    arbitrator = DeterministicArbitrator()

    orchestrator = DecisionOrchestrator(
        db=mock_db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )

    response = await orchestrator.handle_decision(decision_request)

    assert response.approval_required is True
    assert response.dominant_source == "human"
    intelligence_service.evaluate.assert_not_awaited()
