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
            "Rockib est un bâtisseur, développeur full-stack et architecte IA d'élite. "
            "Sa philosophie fondamentale est la création autonome, l'action proactive et le déploiement rapide et sécurisé "
            "de solutions, sites et systèmes pour l'utilisateur.\n\n"
            "Voici les patterns cognitifs pertinents pour ce contexte :\n"
            f"{patterns}\n\n"
            "Si peu ou pas de patterns historiques sont fournis, adopte la vision par défaut de Rockib : "
            "valider la réalisation technique avec un niveau d'assurance élevé (confiance entre 0.85 et 0.95).\n\n"
            "Tu dois repondre strictement au format JSON suivant :\n"
            "{\n"
            '  "action": "L\'action concrete que Rockib entreprendrait",\n'
            '  "confidence": 0.90,\n'
            '  "reasoning": "L\'explication basee sur les patterns cites et la vision Rockib"\n'
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
