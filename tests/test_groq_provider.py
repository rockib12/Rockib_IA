import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.intelligence.exceptions import (
    AIProviderAuthError,
    AIProviderNetworkError,
    AIProviderParsingError,
    AIProviderResponseError,
    AIProviderTimeoutError,
)
from app.intelligence.services.providers.groq_provider import GroqProvider


# ---------------------------------------------------------------------------
# Mock client HTTP réutilisable pour les tests
# ---------------------------------------------------------------------------
class MockHTTPClient:
    """Mini-client HTTP mocké pour simuler les réponses Groq."""

    def __init__(self, response: httpx.Response | None = None, side_effect=None):
        self.response = response
        self.side_effect = side_effect
        self.post = AsyncMock()
        if response is not None:
            self.post.return_value = response
        if side_effect is not None:
            self.post.side_effect = side_effect


def make_response(status_code: int = 200, content: str | None = None, body=None):
    """Construit une réponse httpx de test avec le body donné."""
    if content is None and body is not None:
        content = json.dumps(body)
    if content is None:
        content = '{"choices": []}'
    return httpx.Response(
        status_code=status_code,
        content=content.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


# ---------------------------------------------------------------------------
# Test 1 : appel réussi retourne la structure attendue par le Protocol
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_success_returns_content():
    """Une réponse Groq valide retourne le contenu JSON brut."""
    expected_content = (
        '{"suggested_action": "TEST", "confidence": 0.5, "reasoning": "TEST"}'
    )
    response = make_response(
        body={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": expected_content,
                    },
                    "finish_reason": "stop",
                }
            ]
        }
    )
    client = MockHTTPClient(response=response)
    provider = GroqProvider(
        api_key="test-key", model="llama-3.3-70b-versatile", client=client
    )

    messages = [{"role": "user", "content": "Hello"}]

    result = await provider.generate(messages)

    assert result == expected_content
    client.post.assert_awaited_once()
    args, kwargs = client.post.await_args
    assert args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert kwargs["json"]["model"] == "llama-3.3-70b-versatile"
    assert kwargs["json"]["messages"] == messages
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"


# ---------------------------------------------------------------------------
# Test 2 : erreur HTTP (429, 500) lève AIProviderResponseError
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status_code", [429, 500])
@pytest.mark.asyncio
async def test_generate_http_error_raises_response_error(status_code):
    """Les erreurs HTTP 4xx/5xx sont mappées sur AIProviderResponseError."""
    response = make_response(status_code=status_code, content="API error")
    client = MockHTTPClient(response=response)
    provider = GroqProvider(api_key="test-key", model="test-model", client=client)

    with pytest.raises(AIProviderResponseError, match=f"HTTP {status_code}"):
        await provider.generate([{"role": "user", "content": "Hello"}])


# ---------------------------------------------------------------------------
# Test 3 : JSON malformé lève AIProviderParsingError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_malformed_json_raises_parsing_error():
    """Une réponse JSON illisible ou malformée lève AIProviderParsingError."""
    response = make_response(status_code=200, content="{not valid json}")
    client = MockHTTPClient(response=response)
    provider = GroqProvider(api_key="test-key", model="test-model", client=client)

    with pytest.raises(AIProviderParsingError):
        await provider.generate([{"role": "user", "content": "Hello"}])


# ---------------------------------------------------------------------------
# Test 4 : le timeout est bien configuré
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_timeout_is_configured():
    """Le client httpx est créé avec le timeout explicite demandé."""
    with patch(
        "app.intelligence.services.providers.groq_provider.httpx.AsyncClient"
    ) as mock_async_client:
        mock_async_client.return_value.post = AsyncMock(
            return_value=make_response(
                body={
                    "choices": [
                        {"message": {"content": '{"suggested_action": "TEST"}'}}
                    ]
                }
            )
        )
        mock_async_client.return_value.aclose = AsyncMock()
        provider = GroqProvider(api_key="test-key", model="test-model", timeout=30)

        result = await provider.generate([{"role": "user", "content": "Hello"}])

        assert result == '{"suggested_action": "TEST"}'
        mock_async_client.assert_called_once_with(timeout=30)


# ---------------------------------------------------------------------------
# Tests complémentaires : auth, timeout transport, réseau
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_api_key_raises_auth_error():
    """Absence de clé API => AIProviderAuthError."""
    provider = GroqProvider(api_key=None, model="test-model")

    with pytest.raises(AIProviderAuthError, match="GROQ_API_KEY"):
        await provider.generate([{"role": "user", "content": "Hello"}])


@pytest.mark.asyncio
async def test_http_timeout_raises_timeout_error():
    """Timeout HTTP => AIProviderTimeoutError."""
    client = MockHTTPClient(side_effect=httpx.TimeoutException("timeout"))
    provider = GroqProvider(api_key="test-key", model="test-model", client=client)

    with pytest.raises(AIProviderTimeoutError, match="timed out"):
        await provider.generate([{"role": "user", "content": "Hello"}])


@pytest.mark.asyncio
async def test_network_error_raises_network_error():
    """Erreur de transport => AIProviderNetworkError."""
    client = MockHTTPClient(side_effect=httpx.ConnectError("connection refused"))
    provider = GroqProvider(api_key="test-key", model="test-model", client=client)

    with pytest.raises(AIProviderNetworkError, match="network error"):
        await provider.generate([{"role": "user", "content": "Hello"}])


@pytest.mark.asyncio
async def test_unauthorized_raises_auth_error():
    """401/403 Groq => AIProviderAuthError."""
    response = make_response(status_code=401, content="unauthorized")
    client = MockHTTPClient(response=response)
    provider = GroqProvider(api_key="test-key", model="test-model", client=client)

    with pytest.raises(AIProviderAuthError, match="authentication failed"):
        await provider.generate([{"role": "user", "content": "Hello"}])


@pytest.mark.asyncio
async def test_empty_content_raises_parsing_error():
    """Contenu vide => AIProviderParsingError."""
    response = make_response(body={"choices": [{"message": {"content": ""}}]})
    client = MockHTTPClient(response=response)
    provider = GroqProvider(api_key="test-key", model="test-model", client=client)

    with pytest.raises(AIProviderParsingError, match="empty"):
        await provider.generate([{"role": "user", "content": "Hello"}])
