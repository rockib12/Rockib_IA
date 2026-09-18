import pytest
import asyncio
from typing import Protocol
from app.intelligence.services.ai_provider import AIProvider
from app.intelligence.exceptions import (
    AIProviderError, 
    AIProviderAuthError, 
    AIProviderTimeoutError,
    AIProviderNetworkError,
    AIProviderResponseError,
    AIProviderParsingError
)

# Mock pour test structurel
class MockProvider:
    async def generate(self, messages: list[dict[str, str]]) -> str:
        return "response"

def test_ai_provider_protocol_compatibility():
    # Vérification structurelle
    provider: AIProvider = MockProvider()
    assert asyncio.iscoroutinefunction(provider.generate)

@pytest.mark.asyncio
async def test_ai_provider_call():
    provider = MockProvider()
    response = await provider.generate([{"role": "user", "content": "hi"}])
    assert response == "response"

def test_ai_provider_exception_hierarchy():
    assert issubclass(AIProviderAuthError, AIProviderError)
    assert issubclass(AIProviderTimeoutError, AIProviderError)
    assert issubclass(AIProviderNetworkError, AIProviderError)
    assert issubclass(AIProviderResponseError, AIProviderError)
    assert issubclass(AIProviderParsingError, AIProviderError)
