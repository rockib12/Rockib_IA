import uuid
import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.cognitive.schemas import CognitiveOutput
from app.decision_engine.models import (
    ArbitrationRule,
    ControlOutcome,
    DecisionDomainConfig,
    DominantSource,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.decision_engine.schemas import DecisionRequest
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.identity.models import Agent
from app.intelligence.schemas import IntelligenceOutput
from app.connectors.fs_connector import fs_read_handler


def make_mock_db():
    mock_result = Mock()
    mock_scalars = Mock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


def make_mock_agent(autonomy: int = 3):
    agent = Mock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.default_autonomy_level = autonomy
    return agent


def make_fs_read_domain_config(workspace_id: uuid.UUID):
    return DecisionDomainConfig(
        workspace_id=workspace_id,
        domain="fs",
        permission_action=PermissionAction.READ,
        arbitration_rule=ArbitrationRule.intelligence_wins,
        base_risk_level=RiskLevel.low,
        base_reversibility=ReversibilityLevel.reversible,
        base_impact=ImpactType.internal,
        disagreement_threshold=0.5,
        max_autonomy_level=5,
    )


@pytest.mark.asyncio
async def test_intelligence_output_arguments_flows_to_action_record():
    """Vérifie qu'un IntelligenceOutput avec arguments structurés se retrouve tel quel dans ActionRecord.arguments."""
    mock_db = make_mock_db()
    workspace_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    mock_agent = make_mock_agent(autonomy=3)

    decision_request = DecisionRequest(
        workspace_id=workspace_id,
        agent_id=agent_id,
        objective="Inspecter la configuration",
        situation="Vérification",
        proposed_action="lis le fichier config.json",
        requested_autonomy_level=3,
    )

    classifier = DomainClassifier(mapping={"lis": ("fs", PermissionAction.READ)})
    arbitrator = DeterministicArbitrator()

    cognitive_simulator = AsyncMock()
    cognitive_simulator.simulate.return_value = CognitiveOutput(
        action="fs.read",
        confidence=0.8,
        arguments={"path": "config.json"},
    )

    intelligence_service = AsyncMock()
    intelligence_service.evaluate.return_value = IntelligenceOutput(
        suggested_action="fs.read",
        arguments={"path": "config.json"},
        confidence=0.95,
        risk_level=RiskLevel.low,
        reasoning="Besoin de lire la config",
    )

    orchestrator = DecisionOrchestrator(
        db=mock_db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )

    domain_cfg = make_fs_read_domain_config(workspace_id)

    with patch("app.decision_engine.services.orchestrator.mine_patterns", new_callable=AsyncMock) as mock_mine, \
         patch("app.decision_engine.services.orchestrator.issue_authorization", new_callable=AsyncMock), \
         patch("app.decision_engine.services.orchestrator.dispatch_authorized_action", new_callable=AsyncMock), \
         patch.object(orchestrator, "_load_agent", new_callable=AsyncMock) as mock_load_agent, \
         patch.object(orchestrator.arbitrator, "_load_domain_config", new_callable=AsyncMock) as mock_load_cfg:

        mock_mine.return_value = ""
        mock_load_agent.return_value = mock_agent
        mock_load_cfg.return_value = domain_cfg

        response = await orchestrator.handle_decision(decision_request)

        assert response.decision_id is not None
        # mock_db.add est appelé pour decision (0) puis action_record (1)
        assert mock_db.add.call_count >= 2
        action_record = mock_db.add.call_args_list[1][0][0]

        assert action_record.tool == "fs"
        assert action_record.operation == "READ"
        assert action_record.arguments == {"path": "config.json"}


@pytest.mark.asyncio
async def test_missing_or_malformed_arguments_defaults_to_empty_dict():
    """Vérifie que si les arguments sont manquants ou invalides, ActionRecord.arguments reste {} sans planter."""
    mock_db = make_mock_db()
    workspace_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    mock_agent = make_mock_agent(autonomy=3)

    decision_request = DecisionRequest(
        workspace_id=workspace_id,
        agent_id=agent_id,
        objective="Inspecter la configuration",
        situation="Vérification",
        proposed_action="lis le fichier config.json",
        requested_autonomy_level=3,
    )

    classifier = DomainClassifier(mapping={"lis": ("fs", PermissionAction.READ)})
    arbitrator = DeterministicArbitrator()

    cognitive_simulator = AsyncMock()
    cognitive_simulator.simulate.return_value = CognitiveOutput(
        action="fs.read",
        confidence=0.8,
    )

    # IntelligenceOutput sans arguments (default_factory=dict => {})
    intelligence_service = AsyncMock()
    intel_output = IntelligenceOutput(
        suggested_action="fs.read",
        confidence=0.9,
        risk_level=RiskLevel.low,
    )
    # Simuler un cas où le champ arguments aurait été écrasé par une valeur non-dict
    intel_output.__dict__["arguments"] = "invalid_string_args"
    intelligence_service.evaluate.return_value = intel_output

    orchestrator = DecisionOrchestrator(
        db=mock_db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )

    domain_cfg = make_fs_read_domain_config(workspace_id)

    with patch("app.decision_engine.services.orchestrator.mine_patterns", new_callable=AsyncMock) as mock_mine, \
         patch("app.decision_engine.services.orchestrator.issue_authorization", new_callable=AsyncMock), \
         patch("app.decision_engine.services.orchestrator.dispatch_authorized_action", new_callable=AsyncMock), \
         patch.object(orchestrator, "_load_agent", new_callable=AsyncMock) as mock_load_agent, \
         patch.object(orchestrator.arbitrator, "_load_domain_config", new_callable=AsyncMock) as mock_load_cfg:

        mock_mine.return_value = ""
        mock_load_agent.return_value = mock_agent
        mock_load_cfg.return_value = domain_cfg

        response = await orchestrator.handle_decision(decision_request)

        assert response.decision_id is not None
        action_record = mock_db.add.call_args_list[1][0][0]

        # Doit être un dict vide défensif sans avoir levé d'exception
        assert isinstance(action_record.arguments, dict)
        assert action_record.arguments == {}


@pytest.mark.asyncio
async def test_end_to_end_read_file_arguments_consumed_by_fs_read_handler(tmp_path, monkeypatch):
    """Test de bout en bout : proposition 'lis le fichier test.txt' -> arguments={'path': 'test.txt'} -> consommé avec succès par fs_read_handler."""
    ws_id = uuid.uuid4()
    ws_dir = tmp_path / str(ws_id)
    ws_dir.mkdir(parents=True, exist_ok=True)

    test_file = ws_dir / "test.txt"
    test_file.write_text("Hello Rockib E2E Content", encoding="utf-8")

    monkeypatch.setattr("app.connectors.fs_connector.WORKSPACES_ROOT", tmp_path)

    mock_db = make_mock_db()
    agent_id = uuid.uuid4()
    mock_agent = make_mock_agent(autonomy=3)

    decision_request = DecisionRequest(
        workspace_id=ws_id,
        agent_id=agent_id,
        objective="Lire le fichier de test",
        situation="Vérification E2E",
        proposed_action="lis le fichier test.txt",
        requested_autonomy_level=3,
    )

    classifier = DomainClassifier(mapping={"lis": ("fs", PermissionAction.READ)})
    arbitrator = DeterministicArbitrator()

    cognitive_simulator = AsyncMock()
    cognitive_simulator.simulate.return_value = CognitiveOutput(
        action="fs.read",
        confidence=0.85,
    )

    intelligence_service = AsyncMock()
    intelligence_service.evaluate.return_value = IntelligenceOutput(
        suggested_action="fs.read",
        arguments={"path": "test.txt"},
        confidence=0.95,
        risk_level=RiskLevel.low,
    )

    orchestrator = DecisionOrchestrator(
        db=mock_db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )

    domain_cfg = make_fs_read_domain_config(ws_id)

    with patch("app.decision_engine.services.orchestrator.mine_patterns", new_callable=AsyncMock) as mock_mine, \
         patch("app.decision_engine.services.orchestrator.issue_authorization", new_callable=AsyncMock), \
         patch("app.decision_engine.services.orchestrator.dispatch_authorized_action", new_callable=AsyncMock), \
         patch.object(orchestrator, "_load_agent", new_callable=AsyncMock) as mock_load_agent, \
         patch.object(orchestrator.arbitrator, "_load_domain_config", new_callable=AsyncMock) as mock_load_cfg:

        mock_mine.return_value = ""
        mock_load_agent.return_value = mock_agent
        mock_load_cfg.return_value = domain_cfg

        response = await orchestrator.handle_decision(decision_request)

        assert response.decision_id is not None
        action_record = mock_db.add.call_args_list[1][0][0]

        # 1. Vérification que l'ActionRecord contient bien les arguments
        assert action_record.tool == "fs"
        assert action_record.operation == "READ"
        assert action_record.arguments == {"path": "test.txt"}

        # 2. Exécution directe par le handler du connecteur
        result = await fs_read_handler(action_record)
        assert result.success is True
        assert result.output == "Hello Rockib E2E Content"
        assert result.error is None
