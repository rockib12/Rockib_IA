from app.intelligence.schemas import IntelligenceInput, IntelligenceOutput
from app.intelligence.services.rational_agent import RationalAgent
from app.intelligence.services.risk_analyst import RiskAnalyst

class IntelligenceService:
    def __init__(self, rational_agent: RationalAgent, risk_analyst: RiskAnalyst):
        self.rational_agent = rational_agent
        self.risk_analyst = risk_analyst

    async def evaluate(
        self,
        input: IntelligenceInput,
    ) -> IntelligenceOutput:
        """
        Orchestre le RationalAgent et le RiskAnalyst.
        """
        # 1. RationalAgent (Quoi faire ?)
        ra_output = await self.rational_agent.evaluate(
            objective=input.objective,
            situation=input.situation,
            proposed_action=input.proposed_action,
            domain=input.domain
        )

        # 2. RiskAnalyst (Est-ce s?r ?) - ?value l'action produite par RA
        risk_output = await self.risk_analyst.evaluate(
            action_to_evaluate=ra_output.suggested_action,
            situation=input.situation,
            domain=input.domain,
            permission_action=input.permission_action
        )

        # 3. Aggregation
        final_reasoning = f"[Rationality]: {ra_output.reasoning} | [Risk]: {risk_output.reasoning}"
        
        return IntelligenceOutput(
            suggested_action=ra_output.suggested_action,
            confidence=ra_output.confidence,
            risk_level=risk_output.risk_level,
            reasoning=final_reasoning
        )
