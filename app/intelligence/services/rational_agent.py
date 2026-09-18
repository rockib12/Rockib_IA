from __future__ import annotations
from pydantic import ValidationError
from app.intelligence.schemas import RationalAgentOutput
from app.intelligence.services.ai_provider import AIProvider
from app.intelligence.exceptions import RationalAgentParsingError

class RationalAgent:
    """Agent rationnel (LLM-backed) pour la couche Intelligence."""
    
    def __init__(self, provider: AIProvider):
        self.provider = provider
    
    async def evaluate(
        self,
        objective: str,
        situation: str,
        proposed_action: str,
        domain: str,
    ) -> RationalAgentOutput:
        """
        Détermine l'action la plus rationnelle pour atteindre l'objectif.
        """
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"Objective: {objective}\nSituation: {situation}\nProposed action: {proposed_action}\nDomain: {domain}"}
        ]
        
        # Le provider peut lever des AIProviderError, elles doivent remonter naturellement.
        raw_response = await self.provider.generate(messages)
        
        try:
            return RationalAgentOutput.model_validate_json(raw_response)
        except ValidationError as exc:
            raise RationalAgentParsingError("Failed to parse LLM response into RationalAgentOutput") from exc
