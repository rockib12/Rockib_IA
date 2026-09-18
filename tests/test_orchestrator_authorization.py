"""Authorization must gate dispatch in the actual decision pipeline."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.cognitive.schemas import CognitiveOutput
from app.decision_engine.models import (
    ArbitrationRule,
    ControlOutcome,
    DecisionDomainConfig,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.decision_engine.schemas import DecisionRequest
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.intelligence.schemas import IntelligenceOutput


@pytest.mark.asyncio
async def test_unauthorized_action_never_reaches_executor():
    db = AsyncMock()
    db.add = Mock()
    policy = DecisionDomainConfig(
        id=1,
        workspace_id="workspace-test",
        domain="communication",
        permission_action=PermissionAction.SEND,
        execution_enabled=False,
        max_autonomy_level=3,
        arbitration_rule=ArbitrationRule.consensus_required,
        base_risk_level=RiskLevel.low,
        base_reversibility=ReversibilityLevel.reversible,
        base_impact=ImpactType.internal,
        disagreement_threshold=0.4,
    )
    arbitrator = DeterministicArbitrator(db=db)
    action = "send message"
    cognitive = AsyncMock()
    cognitive.simulate.return_value = CognitiveOutput(action=action, confidence=0.9)
    intelligence = AsyncMock()
    intelligence.evaluate.return_value = IntelligenceOutput(
        suggested_action=action, confidence=0.9, risk_level=RiskLevel.low
    )
    orchestrator = DecisionOrchestrator(
        db=db,
        classifier=DomainClassifier(
            mapping={"send": ("communication", PermissionAction.SEND)}
        ),
        arbitrator=arbitrator,
        intelligence=intelligence,
        cognitive_simulator=cognitive,
    )
    request = DecisionRequest(
        workspace_id="workspace-test",
        agent_id="agent-test",
        objective="Send an update",
        proposed_action=action,
        requested_autonomy_level=3,
    )

    with (
        patch.object(orchestrator, "_load_agent", new_callable=AsyncMock) as load_agent,
        patch.object(
            arbitrator, "_load_domain_config", new_callable=AsyncMock
        ) as load_policy,
        patch(
            "app.decision_engine.services.orchestrator.mine_patterns",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "app.decision_engine.services.orchestrator.execute",
            new_callable=AsyncMock,
        ) as execute,
    ):
        load_agent.return_value = Mock(default_autonomy_level=3)
        load_policy.return_value = policy

        response = await orchestrator.handle_decision(request)

        assert response.control_outcome == ControlOutcome.DENY
        assert response.control_reason == "EXECUTION_NOT_PREAUTHORIZED"
        assert response.permission_granted is False
        assert response.final_action == action
        execute.assert_not_called()
        execute.assert_not_awaited()
        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        saved = db.add.call_args.args[0]
        assert saved.control_outcome == ControlOutcome.DENY
        assert saved.permission_granted is False
        assert saved.final_action == action
        load_policy.assert_awaited_once_with(
            "workspace-test", "communication", PermissionAction.SEND
        )