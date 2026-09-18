from __future__ import annotations
from app.intelligence.schemas import RiskAnalystOutput
from app.decision_engine.models import PermissionAction, RiskLevel

class RiskAnalyst:
    """Analyste de risque IA."""
    
    async def evaluate(
        self,
        action_to_evaluate: str,
        situation: str,
        domain: str,
        permission_action: PermissionAction,
    ) -> RiskAnalystOutput:
        """
        ?value le risque de l'action effectivement propos?e.
        PLACEHOLDER contractuel.
        """
        # Note: L'impl?mentation r?elle viendra plus tard.
        return RiskAnalystOutput(
            risk_level=RiskLevel.low,
            reasoning="Placeholder: Risk assessed as low."
        )
