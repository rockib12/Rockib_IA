"""Arbitre déterministe du Decision Engine.

Ce module applique des règles de configuration lues en base
(`decision_domain_config`) pour produire un objet `Decision`
structuré sans le persister.
"""
from __future__ import annotations

import math
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.decision_engine.models import (
    ArbitrationRule,
    ControlOutcome,
    Decision,
    DecisionDomainConfig,
    DecisionStatus,
    DominantSource,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)

from app.decision_engine.services.control import set_control

# --- Rang explicite des niveaux de risque ---
_RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.low: 0,
    RiskLevel.medium: 1,
    RiskLevel.high: 2,
    RiskLevel.critical: 3,
}


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Renvoie le niveau de risque le plus élevé selon le rang."""
    return a if _RISK_RANK[a] >= _RISK_RANK[b] else b


class DeterministicArbitrator:
    """Arbitre déterministe basé sur des règles de configuration.
    
    L'arbitrage est purement logique et s'appuie sur la base de données
    pour les seuils et règles par domaine.
    """

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def _load_domain_config(
        self,
        workspace_id: str,
        domain: str,
        permission_action: PermissionAction,
    ) -> DecisionDomainConfig | None:
        """Charge la configuration du domaine depuis la base via la session asynchrone."""
        if self.db is None:
            return None

        stmt = (
            select(DecisionDomainConfig)
            .where(
                DecisionDomainConfig.workspace_id == workspace_id,
                DecisionDomainConfig.domain == domain,
                DecisionDomainConfig.permission_action == permission_action,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def arbitrate(
        self,
        *,
        objective: str,
        situation: str,
        proposed_action: str,
        cognitive_opinion: dict[str, Any],
        intelligence_opinion: dict[str, Any],
        domain: str,
        permission_action: PermissionAction,
        requested_autonomy_level: int,
        workspace_id: str,
        agent_id: str,
    ) -> Decision:
        """Applique les règles d'arbitrage et retourne un objet Decision.
        
        Ce processus ne persiste pas la décision en base de données.
        """
        if type(requested_autonomy_level) is not int or not 0 <= requested_autonomy_level <= 5:
            raise ValueError("requested_autonomy_level must be an integer between 0 and 5")

        # Invalid confidence must never bypass an approval threshold (NaN included).
        cognitive_conf = float(cognitive_opinion.get('confidence', 0.0))
        intelligence_conf = float(intelligence_opinion.get('confidence', 0.0))
        if not all(math.isfinite(c) and 0 <= c <= 1 for c in (cognitive_conf, intelligence_conf)):
            raise ValueError("confidence must be finite and between 0 and 1")
        disagreement = abs(cognitive_conf - intelligence_conf)

        # 2. Chargement de la configuration du domaine
        config = await self._load_domain_config(
            workspace_id, domain, permission_action
        )

        if config is None:
            # Valeurs par défaut sûres si aucune config n'est trouvée
            arbitration_rule = ArbitrationRule.escalate
            base_risk_level = RiskLevel.medium
            base_reversibility = ReversibilityLevel.reversible
            base_impact = ImpactType.internal
            disagreement_threshold = 0.40
            domain_config_id = None
        else:
            arbitration_rule = config.arbitration_rule
            base_risk_level = config.base_risk_level
            base_reversibility = config.base_reversibility
            base_impact = config.base_impact
            disagreement_threshold = float(config.disagreement_threshold)
            domain_config_id = config.id

        # 3. Calcul du Risque (L'IA peut augmenter, jamais diminuer)
        ai_suggested_risk_raw = intelligence_opinion.get('risk_level', base_risk_level)
        
        try:
            ai_suggested_risk = RiskLevel(ai_suggested_risk_raw)
            invalid_risk = False
        except (ValueError, TypeError):
            ai_suggested_risk = RiskLevel.critical
            invalid_risk = True

        risk_level_final = _max_risk(base_risk_level, ai_suggested_risk)
        risk_ai_adjusted = (risk_level_final != base_risk_level)

        # 4. Arbitrage de l'action finale
        dominant_source: DominantSource
        final_action: str
        final_confidence: float
        approval_required = False

        if arbitration_rule == ArbitrationRule.cognitive_wins:
            dominant_source = DominantSource.cognitive
            final_action = cognitive_opinion.get('action', proposed_action)
            final_confidence = cognitive_conf

        elif arbitration_rule == ArbitrationRule.intelligence_wins:
            dominant_source = DominantSource.intelligence
            final_action = intelligence_opinion.get('action', proposed_action)
            final_confidence = intelligence_conf

        elif arbitration_rule == ArbitrationRule.consensus_required:
            cog_act = cognitive_opinion.get('action')
            int_act = intelligence_opinion.get('action')
            if cog_act and int_act and cog_act == int_act:
                dominant_source = DominantSource.consensus
                final_action = cog_act
                final_confidence = (cognitive_conf + intelligence_conf) / 2
            else:
                # Désaccord -> on garde l'action proposée et on force l'approbation
                dominant_source = DominantSource.cognitive  # Placeholder neutre
                final_action = proposed_action
                final_confidence = 0.0
                approval_required = True

        elif arbitration_rule == ArbitrationRule.escalate:
            dominant_source = DominantSource.cognitive  # Placeholder neutre
            final_action = proposed_action
            final_confidence = 0.0
            approval_required = True
        else:
            # Fallback sécurité
            dominant_source = DominantSource.cognitive
            final_action = proposed_action
            final_confidence = 0.0
            approval_required = True

        # 5. Détermination de l'approbation requise (OR)
        if (
            disagreement > disagreement_threshold
            or risk_level_final in {RiskLevel.high, RiskLevel.critical}
            or base_reversibility == ReversibilityLevel.irreversible
            or arbitration_rule == ArbitrationRule.escalate
            or permission_action == PermissionAction.DELETE
        ):
            approval_required = True

        # 6. Autonomie
        max_allowed_autonomy = config.max_autonomy_level if config is not None else 0
        valid_cap = type(max_allowed_autonomy) is int and 0 <= max_allowed_autonomy <= 5
        applied_autonomy_level = min(requested_autonomy_level, max_allowed_autonomy) if valid_cap else 0
        


        # 7. Construction de l'objet Decision
        decision = Decision(
            workspace_id=workspace_id,
            agent_id=agent_id,
            domain_config_id=domain_config_id,
            objective=objective,
            situation=situation,
            proposed_action=proposed_action,
            cognitive_action=cognitive_opinion.get('action'),
            cognitive_confidence=cognitive_conf,
            intelligence_action=intelligence_opinion.get('action'),
            intelligence_confidence=intelligence_conf,
            dominant_source=dominant_source,
            disagreement=disagreement,
            risk_level=risk_level_final,
            risk_reversibility=base_reversibility,
            risk_impact=base_impact,
            risk_ai_adjusted=risk_ai_adjusted,
            requested_autonomy_level=requested_autonomy_level,
            applied_autonomy_level=applied_autonomy_level,
            permission_required=permission_action,
            permission_granted=False,
            approval_required=approval_required,
            approval_reason=None if not approval_required else 'Arbitration rules required human approval',
            approved_by=None,
            approved_at=None,
            escalated_at=None,
            final_action=final_action,
            final_confidence=final_confidence,
            status=DecisionStatus.pending_approval,
        )

        # Permission derived only from server-side policy, never from an AI opinion.
        if config is None:
            outcome, reason = ControlOutcome.STOP, "POLICY_MISSING"
        elif not valid_cap or not math.isfinite(disagreement_threshold) or not 0 <= disagreement_threshold <= 1:
            outcome, reason = ControlOutcome.STOP, "POLICY_INVALID"
        elif invalid_risk:
            outcome, reason = ControlOutcome.STOP, "RISK_INVALID"
        elif not isinstance(final_action, str) or not final_action.strip():
            outcome, reason = ControlOutcome.STOP, "ACTION_INVALID"
        elif config.execution_enabled is not True:
            outcome, reason = ControlOutcome.DENY, "EXECUTION_NOT_PREAUTHORIZED"
        elif applied_autonomy_level == 0 or approval_required:
            outcome = ControlOutcome.ESCALATE
            reason = "AUTONOMY_ZERO" if applied_autonomy_level == 0 else "APPROVAL_REQUIRED"
        else:
            outcome, reason = ControlOutcome.ALLOW, "POLICY_ALLOWED"
        set_control(decision, outcome, reason)

        return decision
