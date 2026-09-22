from __future__ import annotations
import logging
from typing import Dict

from app.decision_engine.models import RiskLevel
from app.intelligence.schemas import RiskAnalystOutput
from app.intelligence.services.ai_provider import AIProvider
from app.intelligence.exceptions import AIProviderParsingError

logger = logging.getLogger(__name__)

class RiskAnalyst:
    """
    Analyse les signaux de risque dans une action propos?e.
    L'analyste ne peut qu'?lever le risque de base, jamais l'abaisser.
    """
    
    _RISK_RANK: Dict[RiskLevel, int] = {
        RiskLevel.low: 0,
        RiskLevel.medium: 1,
        RiskLevel.high: 2,
        RiskLevel.critical: 3,
    }

    def __init__(self, provider: AIProvider):
        self.provider = provider

    async def assess(
        self, 
        objective: str, 
        situation: str, 
        proposed_action: str, 
        base_risk: RiskLevel
    ) -> RiskAnalystOutput:
        """
        Analyse si l'action propos?e pr?sente des signaux de risque 
        sup?rieurs au risque de base d?fini par la politique.
        """
        prompt = (
            f"You are a Senior Risk Analyst. Your role is to detect hidden risks in a proposed action.\n\n"
            f"CONTEXT:\n"
            f"- Objective: {objective}\n"
            f"- Situation: {situation}\n"
            f"- Proposed Action: {proposed_action}\n"
            f"- Base Policy Risk: {base_risk}\n\n"
            f"TASK:\n"
            f"Determine if the specific content of the action (e.g., mentions of money, external recipients, "
            f"irreversible operations, high volumes, or sensitive data) suggests a risk level HIGHER than the base risk.\n\n"
            f"RULE:\n"
            f"1. If you detect higher risk signals, return the appropriate RiskLevel (medium, high, critical).\n"
            f"2. If the action seems consistent with the base risk or lower, return the base risk level.\n"
            f"3. You MUST provide clear reasoning based on the text signals."
        )

        try:
            result = await self.provider.complete(
                prompt=prompt, 
                response_model=RiskAnalystOutput
            )
            
            ai_risk = result.risk_level
            
            # Garantie de s?curit? : max(base_risk, ai_risk)
            final_risk = self._get_max_risk(base_risk, ai_risk)
            
            reasoning = result.reasoning
            if self._RISK_RANK[ai_risk] < self._RISK_RANK[base_risk]:
                reasoning = f"[Security Guardrail: Risk cannot be lowered below {base_risk}]. {reasoning}"
            elif final_risk != ai_risk:
                reasoning = f"[Security Override: Adjusted from {ai_risk} to {final_risk}]. {reasoning}"

            return RiskAnalystOutput(
                risk_level=final_risk,
                reasoning=reasoning
            )

        except (AIProviderParsingError, Exception) as e:
            logger.error(f"RiskAnalyst failure: {e}. Falling back to base risk {base_risk}.")
            return RiskAnalystOutput(
                risk_level=base_risk,
                reasoning=f"Risk analysis failed ({type(e).__name__}), maintaining base risk."
            )

    def _get_max_risk(self, risk_a: RiskLevel, risk_b: RiskLevel) -> RiskLevel:
        return risk_a if self._RISK_RANK[risk_a] >= self._RISK_RANK[risk_b] else risk_b
