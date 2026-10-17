from typing import List, Optional
from pydantic import ValidationError
from app.intelligence.schemas import RationalAgentOutput
from app.intelligence.services.ai_provider import AIProvider
from app.intelligence.exceptions import RationalAgentParsingError
from app.skills.schemas import ActiveSkillContext

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
        active_skills: Optional[List[ActiveSkillContext]] = None,
    ) -> RationalAgentOutput:
        """
        Détermine l'action la plus rationnelle pour atteindre l'objectif.
        """
        system_prompt = (
            "You are a Rational AI Agent making decisions to achieve an objective.\n"
            "You MUST output valid JSON strictly matching the RationalAgentOutput schema:\n"
            "{\n"
            '  "suggested_action": "<Short action name or identifier, e.g. fs.read>",\n'
            '  "arguments": {<key-value pairs of parameters required by the tool>},\n'
            '  "confidence": <float between 0.0 and 1.0>,\n'
            '  "reasoning": "<Your step-by-step reasoning>"\n'
            "}\n\n"
            "CONCRETE EXAMPLE:\n"
            "For reading a file 'config.json':\n"
            "{\n"
            '  "suggested_action": "fs.read",\n'
            '  "arguments": {"path": "config.json"},\n'
            '  "confidence": 0.95,\n'
            '  "reasoning": "Need to inspect config.json to check current settings."\n'
            "}\n\n"
            "AVAILABLE TOOLS & EXPECTED PAYLOAD IN 'arguments':\n"
            "1. Domain: 'fs', Action: 'read' -> arguments: {\"path\": \"<relative/path/to/file>\"}\n"
            "2. Domain: 'system', Action: 'read' -> arguments: {}\n"
            "3. Domain: 'system', Action: 'create' -> arguments: {\"path\": \"<filename, e.g. index.html>\"}\n"
            "   CRITICAL: In 'arguments', output ONLY {\"path\": \"index.html\"} (or appropriate file path). NEVER put raw code, HTML or content inside 'arguments'. The code will be synthesized directly by the executor.\n"
            "4. Domain: 'fs', Action: 'write' -> arguments: {\"path\": \"<filename>\"}\n"
            "5. Domain: 'web', Action: 'search' -> arguments: {\"query\": \"<search terms>\", \"max_results\": 5}\n"
            "6. Domain: 'web', Action: 'fetch' -> arguments: {\"url\": \"<https://url>\"}\n"
            "7. Domain: 'api', Action: 'call' -> arguments: {\"method\": \"GET/POST/PUT\", \"url\": \"<url>\", \"headers\": {}, \"body\": {}}\n"
            "8. Domain: 'agent', Action: 'spawn' -> arguments: {\"name\": \"<agent name>\", \"role\": \"<role>\", \"objective\": \"<task objective>\"}\n"
            "9. Domain: 'facebook', Action: 'post' -> arguments: {\"text\": \"<post content>\"}\n"
            "10. Domain: 'instagram', Action: 'post' -> arguments: {\"image_url\": \"<url>\", \"caption\": \"<caption>\"}\n"
            "11. Domain: 'whatsapp', Action: 'send' -> arguments: {\"phone_number\": \"<number>\", \"message\": \"<message>\"}\n"
            "12. Domain: 'twitter', Action: 'post' -> arguments: {\"text\": \"<tweet content>\"}\n"
            "13. Domain: 'discord', Action: 'send' -> arguments: {\"channel_id\": \"<id>\", \"content\": \"<message>\"}\n\n"
            "CRITICAL RULES:\n"
            "- 'arguments' MUST always be a JSON dictionary (never a string, never null).\n"
            "- 'suggested_action' should indicate the tool/action name (e.g. 'fs.read')."
        )

        if active_skills:
            skill_blocks = []
            for s in active_skills:
                constraints_str = "\n".join(f"      - {c}" for c in s.constraints)
                tools_str = ", ".join(s.required_tools)
                block = (
                    f'  <skill id="{s.id}" version="{s.semver}">\n'
                    f'    <name>{s.name}</name>\n'
                    f'    <instructions>\n{s.instructions}\n    </instructions>\n'
                    f'    <constraints>\n{constraints_str}\n    </constraints>\n'
                    f'    <declared_tools>{tools_str}</declared_tools>\n'
                    f'  </skill>'
                )
                skill_blocks.append(block)
            system_prompt += (
                "\n\n<skills_context>\n"
                "The following procedural skills and guidelines are active for this task:\n"
                + "\n".join(skill_blocks)
                + "\n</skills_context>\n"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Objective: {objective}\nSituation: {situation}\nProposed action: {proposed_action}\nDomain: {domain}"}
        ]
        
        # Le provider peut lever des AIProviderError, elles doivent remonter naturellement.
        raw_response = await self.provider.generate(messages)
        
        try:
            return RationalAgentOutput.model_validate_json(raw_response)
        except ValidationError as exc:
            raise RationalAgentParsingError("Failed to parse LLM response into RationalAgentOutput") from exc
