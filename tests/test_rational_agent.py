import pytest
from unittest.mock import AsyncMock
from app.intelligence.services.rational_agent import RationalAgent
from app.intelligence.schemas import RationalAgentOutput
from app.intelligence.exceptions import RationalAgentParsingError, AIProviderError
from app.intelligence.services.ai_provider import AIProvider

# Mock pour test structurel
class MockProvider:
    def __init__(self, response: str = "", side_effect: Exception | None = None):
        self.response = response
        self.side_effect = side_effect
    
    async def generate(self, messages: list[dict[str, str]]) -> str:
        if self.side_effect:
            raise self.side_effect
        return self.response

@pytest.mark.asyncio
async def test_rational_agent_di():
    provider = MockProvider()
    agent = RationalAgent(provider=provider)
    assert agent.provider == provider

@pytest.mark.asyncio
async def test_rational_agent_evaluate_call():
    json_response = '{"suggested_action": "TEST", "confidence": 0.5, "reasoning": "TEST"}'
    provider = MockProvider(response=json_response)
    agent = RationalAgent(provider=provider)
    
    result = await agent.evaluate("obj", "sit", "act", "dom")
    
    assert isinstance(result, RationalAgentOutput)
    assert result.suggested_action == "TEST"
    assert result.confidence == 0.5
    assert result.reasoning == "TEST"

@pytest.mark.asyncio
async def test_rational_agent_parsing_error_invalid_json():
    # Chaîne non JSON
    provider = MockProvider(response="invalid json")
    agent = RationalAgent(provider=provider)
    
    with pytest.raises(RationalAgentParsingError):
        await agent.evaluate("obj", "sit", "act", "dom")

@pytest.mark.asyncio
async def test_rational_agent_parsing_error_schema_mismatch():
    # JSON valide mais schéma invalide (confidence trop haut)
    json_response = '{"suggested_action": "TEST", "confidence": 2.5, "reasoning": "TEST"}'
    provider = MockProvider(response=json_response)
    agent = RationalAgent(provider=provider)
    
    with pytest.raises(RationalAgentParsingError):
        await agent.evaluate("obj", "sit", "act", "dom")

@pytest.mark.asyncio
async def test_rational_agent_error_propagation():
    # Provider lève une exception native
    provider = MockProvider(side_effect=AIProviderError("API Down"))
    agent = RationalAgent(provider=provider)
    
    with pytest.raises(AIProviderError, match="API Down"):
        await agent.evaluate("obj", "sit", "act", "dom")
