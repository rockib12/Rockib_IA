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
        ra_kwargs = {
            "objective": input.objective,
            "situation": input.situation,
            "proposed_action": input.proposed_action,
            "domain": input.domain,
        }
        if input.active_skills is not None:
            ra_kwargs["active_skills"] = input.active_skills
        ra_output = await self.rational_agent.evaluate(**ra_kwargs)

        # 2. RiskAnalyst (Est-ce sûr ?) - Évalue l'action produite par RA
        # On a besoin d'un base_risk fourni par l'orchestrateur.
        # Pour l'instant, on va simuler un risque de base High par prudence, ou l'extraire si on modifie l'input.
        # On assume que IntelligenceInput ne contient pas base_risk, alors on utilise RiskLevel.high par défaut
        # (Dans la vraie vie, l'orchestrateur le passe, mais l'input schema actuel ne l'a pas).
        from app.decision_engine.models import RiskLevel
        risk_output = await self.risk_analyst.assess(
            objective=input.objective,
            situation=input.situation,
            proposed_action=ra_output.suggested_action,
            base_risk=RiskLevel.medium  # Valeur défensive en attendant
        )

        # 3. Aggregation
        final_reasoning = f"[Rationality]: {ra_output.reasoning} | [Risk]: {risk_output.reasoning}"
        
        return IntelligenceOutput(
            suggested_action=ra_output.suggested_action,
            arguments=ra_output.arguments,
            confidence=ra_output.confidence,
            risk_level=risk_output.risk_level,
            reasoning=final_reasoning
        )
