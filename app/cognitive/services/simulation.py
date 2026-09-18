import json
from app.cognitive.schemas import CognitiveInput, CognitiveOutput
from app.intelligence.services.ai_provider import AIProvider
from app.intelligence.exceptions import AIProviderParsingError

class CognitiveSimulator:
    def __init__(self, provider: AIProvider):
        self.provider = provider

    async def simulate(self, cognitive_input: CognitiveInput, patterns: str) -> CognitiveOutput:
        """
        Simule la reaction de Rockib basee sur son historique personnel (patterns)
        et la situation actuelle.
        """
        system_prompt = (
            "Tu es le simulateur cognitif de Rockib. Ton role est de repondre a la question : "
            "\"Que ferait Rockib dans cette situation ?\"\n\n"
            "Pour cela, tu t'appuies sur ses patterns personnels (preferences et decisions passees) "
            "plutot que sur un raisonnement froid generaliste.\n\n"
            "Voici les patterns cognitifs pertinents pour ce contexte :\n"
            f"{patterns}\n\n"
            "Tu dois repondre strictement au format JSON suivant :\n"
            "{\n"
            '  "action": "L\'action concrete que Rockib entreprendrait",\n'
            '  "confidence": 0.0,\n'
            '  "reasoning": "L\'explication basee sur les patterns cites"\n'
            "}\n"
        )

        user_prompt = (
            f"Objectif : {cognitive_input.objective}\n"
            f"Situation : {cognitive_input.situation}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response_text = await self.provider.generate(messages)
            
            cleaned_response = response_text.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            
            data = json.loads(cleaned_response.strip())
            
            return CognitiveOutput(
                action=data["action"],
                confidence=data.get("confidence", 0.0),
                reasoning=data.get("reasoning", "")
            )
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise AIProviderParsingError(f"La reponse du provider n'est pas un JSON valide pour CognitiveOutput : {str(e)}") from e
