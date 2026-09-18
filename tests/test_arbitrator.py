"""Tests unitaires pour decision_engine/services/arbitrator.py.

Vérifie les règles fermes du Decision Engine sans besoin de base de données.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.decision_engine.models import (
    ArbitrationRule,
    DecisionDomainConfig,
    DominantSource,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.decision_engine.services.arbitrator import (
    DeterministicArbitrator,
    _max_risk,
)

# --- Fixtures utilitaires ---------------------------------------------------


def _fake_config(
    *,
    arbitration_rule: ArbitrationRule = ArbitrationRule.cognitive_wins,
    base_risk_level: RiskLevel = RiskLevel.medium,
    base_reversibility: ReversibilityLevel = ReversibilityLevel.reversible,
    base_impact: ImpactType = ImpactType.internal,
    disagreement_threshold: float = 0.40,
    max_autonomy_level: int = 5,
) -> MagicMock:
    """Retourne un mock de DecisionDomainConfig avec les valeurs par défaut."""
    cfg = MagicMock(spec=DecisionDomainConfig)
    cfg.arbitration_rule = arbitration_rule
    cfg.base_risk_level = base_risk_level
    cfg.base_reversibility = base_reversibility
    cfg.base_impact = base_impact
    cfg.disagreement_threshold = disagreement_threshold
    cfg.max_autonomy_level = max_autonomy_level
    return cfg


async def _arbitrate(
    arbitrator: DeterministicArbitrator,
    *,
    requested_autonomy_level: int = 3,
    permission_action: PermissionAction = PermissionAction.READ,
    arbitration_rule: ArbitrationRule = ArbitrationRule.cognitive_wins,
    base_risk_level: RiskLevel = RiskLevel.medium,
    base_reversibility: ReversibilityLevel = ReversibilityLevel.reversible,
    proposed_action: str = "proposed_action",
    cognitive_action: str = "action_A",
    intelligence_action: str = "action_A",
    cognitive_confidence: float = 0.8,
    intelligence_confidence: float = 0.7,
) -> MagicMock:
    """Helper : crée un arbitre avec config mockée et lance arbitrate().

    Retourne le Decision résultant.
    """
    config = _fake_config(
        arbitration_rule=arbitration_rule,
        base_risk_level=base_risk_level,
        base_reversibility=base_reversibility,
    )
    with patch.object(
        DeterministicArbitrator,
        "_load_domain_config",
        new_callable=AsyncMock,
        return_value=config,
    ):
        result = await arbitrator.arbitrate(
            objective="Test objective",
            situation="Test situation",
            proposed_action=proposed_action,
            cognitive_opinion={
                "action": cognitive_action,
                "confidence": cognitive_confidence,
            },
            intelligence_opinion={
                "action": intelligence_action,
                "confidence": intelligence_confidence,
            },
            domain="test_domain",
            permission_action=permission_action,
            requested_autonomy_level=requested_autonomy_level,
            workspace_id="ws-123",
            agent_id="agent-456",
        )
    return result


# --- Tests -------------------------------------------------------------------


@pytest.mark.asyncio
class TestAutonomyRule:
    """Règle : applied_autonomy_level ne doit JAMAIS dépasser requested."""

    async def test_applied_never_exceeds_requested_low(self) -> None:
        """requested=0 → applied=0."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator, requested_autonomy_level=0
        )
        assert result.applied_autonomy_level <= result.requested_autonomy_level
        assert result.applied_autonomy_level == 0

    async def test_applied_never_exceeds_requested_medium(self) -> None:
        """requested=3 → applied=3."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator, requested_autonomy_level=3
        )
        assert result.applied_autonomy_level <= result.requested_autonomy_level
        assert result.applied_autonomy_level == 3

    async def test_applied_never_exceeds_requested_high(self) -> None:
        """requested=5 → applied=5."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator, requested_autonomy_level=5
        )
        assert result.applied_autonomy_level <= result.requested_autonomy_level
        assert result.applied_autonomy_level == 5

    async def test_autonomy_invariant_guaranteed(self) -> None:
        """Vérifie que l'autonomie appliquée ne dépasse jamais l'autonomie demandée."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(arbitrator, requested_autonomy_level=2)
        assert result.applied_autonomy_level <= result.requested_autonomy_level
        assert result.applied_autonomy_level <= result.requested_autonomy_level
        assert result.applied_autonomy_level <= result.requested_autonomy_level
        assert result.applied_autonomy_level <= result.requested_autonomy_level
        assert result.applied_autonomy_level <= result.requested_autonomy_level
        assert result.applied_autonomy_level <= result.requested_autonomy_level


@pytest.mark.asyncio
class TestApprovalRule:
    """Règle : approval_required = True si AU MOINS UNE condition est vraie."""

    async def test_delete_always_requires_approval(self) -> None:
        """DELETE force toujours approval.required = True, sans exception."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            permission_action=PermissionAction.DELETE,
            base_risk_level=RiskLevel.low,
            cognitive_confidence=0.99,
            intelligence_confidence=0.99,
        )
        assert result.approval_required is True
        assert result.permission_required == PermissionAction.DELETE

    async def test_escalate_rule_requires_approval(self) -> None:
        """arbitration_rule=escalate force approval.required = True."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            arbitration_rule=ArbitrationRule.escalate,
            base_risk_level=RiskLevel.low,
        )
        assert result.approval_required is True

    async def test_high_risk_requires_approval(self) -> None:
        """risk_level_final=high → approval.required = True."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            base_risk_level=RiskLevel.high,
        )
        assert result.approval_required is True

    async def test_critical_risk_requires_approval(self) -> None:
        """risk_level_final=critical → approval.required = True."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            base_risk_level=RiskLevel.critical,
        )
        assert result.approval_required is True

    async def test_irreversible_requires_approval(self) -> None:
        """reversibility=irreversible → approval.required = True."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            base_reversibility=ReversibilityLevel.irreversible,
        )
        assert result.approval_required is True

    async def test_disagreement_exceeds_threshold_requires_approval(self) -> None:
        """disagreement > seuil → approval.required = True."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            cognitive_action="action_A",
            intelligence_action="action_B",
            cognitive_confidence=0.95,
            intelligence_confidence=0.10,
        )
        assert result.approval_required is True

    async def test_low_risk_read_no_approval_when_no_trigger(self) -> None:
        """Sans aucun déclencheur, approval.required reste False.

        cognitive_wins + low + réversible + pas de DELETE + pas de disagreement.
        """
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            permission_action=PermissionAction.READ,
            arbitration_rule=ArbitrationRule.cognitive_wins,
            base_risk_level=RiskLevel.low,
            cognitive_action="action_A",
            intelligence_action="action_A",
            cognitive_confidence=0.8,
            intelligence_confidence=0.7,
        )
        assert result.approval_required is False


@pytest.mark.asyncio
class TestRiskRule:
    """Règle : risk.level_final = max(base, IA). L'IA ne peut jamais baisser."""

    def test_max_risk_low_medium(self) -> None:
        """max(low, medium) = medium."""
        assert _max_risk(RiskLevel.low, RiskLevel.medium) == RiskLevel.medium

    def test_max_risk_medium_high(self) -> None:
        """max(medium, high) = high."""
        assert _max_risk(RiskLevel.medium, RiskLevel.high) == RiskLevel.high

    def test_max_risk_low_critical(self) -> None:
        """max(low, critical) = critical."""
        assert _max_risk(RiskLevel.low, RiskLevel.critical) == RiskLevel.critical

    def test_max_risk_same(self) -> None:
        """max(medium, medium) = medium."""
        assert _max_risk(RiskLevel.medium, RiskLevel.medium) == RiskLevel.medium

    def test_max_risk_never_below_base(self) -> None:
        """IA propose low mais base est medium → final = medium."""
        assert _max_risk(RiskLevel.medium, RiskLevel.low) == RiskLevel.medium

    @pytest.mark.asyncio
    async def test_risk_never_below_base_in_arbitration(self) -> None:
        """Dans arbitrate(), même si l'IA ajusterait à low, la base medium l'emporte."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            base_risk_level=RiskLevel.medium,
        )
        # Le rang de medium (1) > low (0) → final doit être medium
        assert result.risk_level == RiskLevel.medium

    @pytest.mark.asyncio
    async def test_risk_high_not_lowered(self) -> None:
        """Si la base est high, même un ajustement IA low garde high."""
        arbitrator = DeterministicArbitrator()
        result = await _arbitrate(
            arbitrator,
            base_risk_level=RiskLevel.high,
        )
        assert result.risk_level == RiskLevel.high
