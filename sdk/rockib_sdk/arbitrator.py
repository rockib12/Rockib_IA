"""Arbitre déterministe — portage local et sans effet de bord des règles Rockib IA.

Règles (dans l'ordre, la première règle bloquante gagne) :
1. Montant invalide (float, négatif, devise non supportée) → DENY.
2. Montant > budget restant → DENY `BUDGET_CEILING_VIOLATION`.
3. `applied_autonomy = min(requested, allowed)`.
4. Autonomie appliquée insuffisante pour le niveau de risque → ESCALATE.
5. Déclencheurs d'approbation humaine : risque HIGH/CRITICAL, action irréversible,
   permission DELETE, dépense au-delà du seuil d'auto-approbation → ESCALATE.
6. Sinon → ALLOW.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import FrozenSet, Optional

from .models import ActionProposal, Decision, Outcome, Permission, RiskLevel

# Autonomie minimale requise pour exécuter sans humain selon le risque
MIN_AUTONOMY_FOR_RISK = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 4,
    RiskLevel.CRITICAL: 5,
}


@dataclass(frozen=True)
class Policy:
    """Politique configurable par domaine ou par essaim."""

    auto_spend_limit: Decimal = Decimal("0")
    supported_currencies: FrozenSet[str] = field(
        default_factory=lambda: frozenset({"EUR", "USD", "XOF"})
    )
    escalate_on_high_risk: bool = True
    escalate_on_irreversible: bool = True
    escalate_on_delete: bool = True


class DeterministicArbitrator:
    def __init__(self, policy: Optional[Policy] = None) -> None:
        self.policy = policy or Policy()

    def decide(
        self,
        proposal: ActionProposal,
        remaining_budget: Optional[Decimal] = None,
    ) -> Decision:
        reasons: list[str] = []
        applied = max(0, min(proposal.requested_autonomy, proposal.allowed_autonomy))

        # 1-2. Garde-fous financiers stricts
        if proposal.permission == Permission.SPEND or proposal.amount is not None:
            amount = proposal.amount
            if amount is None or not isinstance(amount, Decimal):
                return Decision(Outcome.DENY, applied, ["Montant absent ou non décimal"], False, "INVALID_AMOUNT")
            if amount < 0:
                return Decision(Outcome.DENY, applied, ["Montant négatif"], False, "INVALID_AMOUNT")
            if proposal.currency.upper() not in self.policy.supported_currencies:
                return Decision(Outcome.DENY, applied, [f"Devise {proposal.currency} refusée"], False, "INVALID_CURRENCY")
            if remaining_budget is not None and amount > remaining_budget:
                return Decision(
                    Outcome.DENY,
                    applied,
                    [f"Montant {amount} > budget restant {remaining_budget}"],
                    False,
                    "BUDGET_CEILING_VIOLATION",
                )
            if amount > self.policy.auto_spend_limit:
                reasons.append(f"Dépense {amount} {proposal.currency} > seuil auto {self.policy.auto_spend_limit}")

        # 4. Autonomie
        if applied < MIN_AUTONOMY_FOR_RISK[proposal.risk]:
            reasons.append(
                f"Autonomie appliquée {applied} < requise {MIN_AUTONOMY_FOR_RISK[proposal.risk]} pour risque {proposal.risk.value}"
            )

        # 5. Déclencheurs d'approbation
        if self.policy.escalate_on_high_risk and proposal.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            reasons.append(f"Risque {proposal.risk.value}")
        if self.policy.escalate_on_irreversible and not proposal.reversible:
            reasons.append("Action irréversible")
        if self.policy.escalate_on_delete and proposal.permission == Permission.DELETE:
            reasons.append("Permission DELETE")

        if reasons:
            return Decision(Outcome.ESCALATE, applied, reasons, True)
        return Decision(Outcome.ALLOW, applied, ["Conforme à la politique"], False)
