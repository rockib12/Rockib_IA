"""Phase-one invariants: autonomy zero, policy cap, payload integrity."""
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
from app.decision_engine.services.control import action_fingerprint


def _policy(**overrides) -> DecisionDomainConfig:
    values = dict(
        id=1,
        domain="documents",
        permission_action=PermissionAction.READ,
        execution_enabled=True,
        max_autonomy_level=2,
        arbitration_rule=ArbitrationRule.consensus_required,
        base_risk_level=RiskLevel.low,
        base_reversibility=ReversibilityLevel.reversible,
        base_impact=ImpactType.internal,
        disagreement_threshold=0.40,
    )
    values.update(overrides)
    return DecisionDomainConfig(**values)


async def _arbitrate(policy, requested_autonomy_level):
    arbitrator = DeterministicArbitrator()
    arbitrator._load_domain_config = AsyncMock(return_value=policy)
    return await arbitrator.arbitrate(
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
        },
        domain="documents",
        permission_action=PermissionAction.READ,
        requested_autonomy_level=requested_autonomy_level,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested", "expected_applied", "expected_outcome"),
    [
        (0, 0, ControlOutcome.ESCALATE),
        (1, 1, ControlOutcome.ALLOW),
        (2, 2, ControlOutcome.ALLOW),
        (3, 2, ControlOutcome.ALLOW),
        (5, 2, ControlOutcome.ALLOW),
    ],
    ids=["zero", "one", "at-cap", "above-cap", "far-above-cap"],
)
async def test_autonomy_zero_preserved_and_policy_cap_applied(
    requested, expected_applied, expected_outcome
):
    decision = await _arbitrate(_policy(), requested)
    assert decision.applied_autonomy_level == expected_applied
    assert decision.applied_autonomy_level <= decision.requested_autonomy_level
    assert decision.control_outcome == expected_outcome


@pytest.mark.asyncio
async def test_policy_cap_zero_blocks_autonomous_execution():
    decision = await _arbitrate(_policy(max_autonomy_level=0), 5)
    assert decision.applied_autonomy_level == 0
    assert decision.control_outcome == ControlOutcome.ESCALATE
    assert decision.control_reason == "AUTONOMY_ZERO"


@pytest.mark.asyncio
async def test_missing_policy_stops_and_never_allows():
    arbitrator = DeterministicArbitrator()
    arbitrator._load_domain_config = AsyncMock(return_value=None)
    decision = await arbitrator.arbitrate(
        workspace_id="workspace-test",
        agent_id="agent-test",
        objective="Read the authorized document",
        situation="Local unit test; no tool execution",
        proposed_action="Read document",
        cognitive_opinion={"action": "Read document", "confidence": 0.9},
        intelligence_opinion={"action": "Read document", "confidence": 0.9},
        domain="documents",
        permission_action=PermissionAction.READ,
        requested_autonomy_level=3,
    )
    assert decision.control_outcome == ControlOutcome.STOP
    assert decision.control_reason == "POLICY_MISSING"
    assert decision.permission_granted is False


@pytest.mark.asyncio
async def test_invalid_risk_opinion_stops_instead_of_allowing():
    decision = await _arbitrate(_policy(), 2)
    assert decision.control_outcome == ControlOutcome.ALLOW

    arbitrator = DeterministicArbitrator()
    arbitrator._load_domain_config = AsyncMock(return_value=_policy())
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
            "risk_level": "not-a-risk",
        },
        domain="documents",
        permission_action=PermissionAction.READ,
        requested_autonomy_level=2,
    )
    assert decision.control_outcome == ControlOutcome.STOP
    assert decision.control_reason == "RISK_INVALID"
    assert decision.permission_granted is False


@pytest.mark.asyncio
async def test_fingerprint_changes_when_authorized_payload_changes():
    decision = await _arbitrate(_policy(), 2)
    assert decision.control_outcome == ControlOutcome.ALLOW
    original = decision.action_fingerprint
    assert original

    decision.final_action = "Delete everything"
    assert action_fingerprint(decision) != original