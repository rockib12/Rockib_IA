import uuid

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone
from sqlalchemy import select

from app.cognitive.schemas import CognitiveInput, CognitiveOutput
from app.decision_engine.models import (
    ArbitrationRule,
    ControlOutcome,
    Decision,
    DecisionDomainConfig,
    DominantSource,
    PermissionAction,
    RiskLevel,
)
from app.decision_engine.schemas import ClassificationResult, ClassificationStatus, DecisionRequest
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.arbitrator import DeterministicArbitrator
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
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
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
        "app.decision_engine.services.orchestrator.issue_authorization",
        new_callable=AsyncMock,
    ) as mock_issue_authorization, patch(
        "app.decision_engine.services.orchestrator.dispatch_authorized_action",
        new_callable=AsyncMock,
    ) as mock_dispatch, patch.object(
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
        # Décision + action structurée (audit de ce qui a été demandé, même
        # pour une escalade).
        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()
        # Escalade : aucune autorisation ni exécution (INV-01).
        mock_issue_authorization.assert_not_awaited()
        mock_dispatch.assert_not_awaited()
        assert response.execution_effect is None
        assert response.execution_error is None

# ---------------------------------------------------------------------------
# Tests 2-4 : Classification incertaine -> vraie Decision persistée (PostgreSQL)
# ---------------------------------------------------------------------------
# Doctrine §10 : ces tests prouvent la persistance sur vraie base via les
# fixtures db_session/workspace_agent — aucun mock de session. Vérifié :
# ligne Decision réelle, decision_id = UUID valide, permission_required NULL.
async def _assert_persisted_escalation(db_session, workspace_id, agent_id, response):
    assert response.control_outcome == ControlOutcome.ESCALATE
    assert response.control_reason == "CLASSIFICATION_UNCERTAIN"
    assert response.permission_granted is False
    assert response.approval_required is True
    assert response.dominant_source == DominantSource.cognitive

    # decision_id est un UUID valide correspondant à une vraie ligne en base.
    # Nouvelle session : la session du test est en transaction, expire_all() +
    # relecture directe dessus declenchent un MissingGreenlet au teardown
    # (lazy-load ORM hors boucle). On relit en isolation, sans toucher aux
    # objets ORM du test.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.config import settings

    decision_id = uuid.UUID(response.decision_id)
    engine = create_async_engine(settings.ASYNC_DATABASE_URL, poolclass=None)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as reader:
        row = (
            await reader.execute(
                select(Decision).where(Decision.id == decision_id)
            )
        ).scalar_one()
        assert row.workspace_id == workspace_id
        assert row.agent_id == agent_id
        assert row.control_outcome == ControlOutcome.ESCALATE
        assert row.control_reason == "CLASSIFICATION_UNCERTAIN"
        # Inconnu, jamais classifié : pas de valeur fabriquée (§6).
        assert row.permission_required is None
        assert row.permission_granted is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_escalation_unknown_persists(
    db_session,
    workspace_agent,
):
    """Classification UNKNOWN -> escalade persistée, aucun service appelé."""
    from app.decision_engine.services.orchestrator import DecisionOrchestrator as _Orch
    from app.decision_engine.services.domain_classifier import DomainClassifier as _Clf
    from app.decision_engine.services.arbitrator import DeterministicArbitrator as _Arb
    workspace_id, agent_id = workspace_agent[0].id, workspace_agent[1].id
    intelligence_service = AsyncMock()
    cognitive_simulator = AsyncMock()

    classifier = _Clf(mapping={})
    arbitrator = _Arb()

    orchestrator = _Orch(
        db=db_session,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )
    decision_request = DecisionRequest(
        workspace_id=workspace_id,
        agent_id=agent_id,
        objective="Test objective",
        situation="Test situation",
        proposed_action="Test action",
    )

    response = await orchestrator.handle_decision(decision_request)

    await _assert_persisted_escalation(db_session, workspace_id, agent_id, response)
    intelligence_service.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_orchestrator_escalation_ambiguous_persists(
    db_session,
    workspace_agent,
):
    """Classification AMBIGUOUS -> escalade persistée, aucun service appelé."""
    from app.decision_engine.services.orchestrator import DecisionOrchestrator as _Orch
    from app.decision_engine.services.domain_classifier import DomainClassifier as _Clf
    from app.decision_engine.services.arbitrator import DeterministicArbitrator as _Arb
    workspace_id, agent_id = workspace_agent[0].id, workspace_agent[1].id
    intelligence_service = AsyncMock()
    cognitive_simulator = AsyncMock()

    # Deux mots-clés matchant -> AMBIGUOUS
    mapping = {
        "test": ("finance", PermissionAction.UPDATE),
        "action": ("security", PermissionAction.READ),
    }

    classifier = _Clf(mapping=mapping)
    arbitrator = _Arb()

    orchestrator = _Orch(
        db=db_session,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )
    decision_request = DecisionRequest(
        workspace_id=workspace_id,
        agent_id=agent_id,
        objective="Test objective",
        situation="Test situation",
        proposed_action="test action",
    )

    response = await orchestrator.handle_decision(decision_request)

    await _assert_persisted_escalation(db_session, workspace_id, agent_id, response)
    intelligence_service.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_orchestrator_escalation_error_persists(
    db_session,
    workspace_agent,
):
    """Classification ERROR -> escalade persistée, aucun service appelé."""
    from app.decision_engine.services.orchestrator import DecisionOrchestrator as _Orch
    from app.decision_engine.services.domain_classifier import DomainClassifier as _Clf
    from app.decision_engine.services.arbitrator import DeterministicArbitrator as _Arb
    workspace_id, agent_id = workspace_agent[0].id, workspace_agent[1].id
    intelligence_service = AsyncMock()
    cognitive_simulator = AsyncMock()

    # Permission invalide -> ERROR
    mapping = {"test": ("finance", "INVALID_PERMISSION")}

    classifier = _Clf(mapping=mapping)
    arbitrator = _Arb()

    orchestrator = _Orch(
        db=db_session,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )
    decision_request = DecisionRequest(
        workspace_id=workspace_id,
        agent_id=agent_id,
        objective="Test objective",
        situation="Test situation",
        proposed_action="test action",
    )

    response = await orchestrator.handle_decision(decision_request)

    await _assert_persisted_escalation(db_session, workspace_id, agent_id, response)
    intelligence_service.evaluate.assert_not_awaited()
