"""Regression tests for explicit server-side execution preauthorization."""
from unittest.mock import AsyncMock

import pytest

from app.decision_engine.models import (
    ArbitrationRule,
    ControlOutcome,
    DecisionDomainConfig,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.decision_engine.services.arbitrator import DeterministicArbitrator


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preauthorization", "expected_permission", "expected_outcome"),
    [
        (None, False, ControlOutcome.DENY),
        (False, False, ControlOutcome.DENY),
        (True, True, ControlOutcome.ALLOW),
    ],
    ids=["not-explicitly-configured", "explicitly-disabled", "explicitly-enabled"],
)
async def test_permission_requires_explicit_policy_preauthorization(
    preauthorization, expected_permission, expected_outcome
):
    policy = DecisionDomainConfig(
        id=1,
        domain="documents",
        permission_action=PermissionAction.READ,
        arbitration_rule=ArbitrationRule.consensus_required,
        base_risk_level=RiskLevel.low,
        base_reversibility=ReversibilityLevel.reversible,
        base_impact=ImpactType.internal,
        disagreement_threshold=0.40,
        max_autonomy_level=3,
    )
    # Omit the field to represent an unevaluated/default policy object.
    if preauthorization is not None:
        policy.execution_enabled = preauthorization

    arbitrator = DeterministicArbitrator()
    arbitrator._load_domain_config = AsyncMock(return_value=policy)
    decision = await arbitrator.arbitrate(
        workspace_id="workspace-test",
        agent_id="agent-test",
        objective="Read the authorized document",
        situation="Local unit test; no tool execution",
        proposed_action="Read document",
        cognitive_opinion={"action": "Read document", "confidence": 0.9},
        intelligence_opinion={
            "action": "Read document",
            "confidence": 0.9,
            "risk_level": RiskLevel.low,
            # Untrusted AI fields must not grant server-side permissions.
            "permission_granted": True,
            "execution_enabled": True,
        },
        domain="documents",
        permission_action=PermissionAction.READ,
        requested_autonomy_level=3,
    )

    arbitrator._load_domain_config.assert_awaited_once_with(
        "workspace-test", "documents", PermissionAction.READ
    )
    assert decision.permission_granted is expected_permission
    assert decision.control_outcome == expected_outcome
    assert decision.final_action == "Read document"
    assert decision.risk_level == RiskLevel.low
    assert decision.approval_required is False