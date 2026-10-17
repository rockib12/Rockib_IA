import pytest
import uuid
import httpx
from unittest.mock import patch, MagicMock, AsyncMock

from app.execution.models import ActionRecord
from app.connectors.api_connector import api_call_handler

@pytest.fixture
def fake_action_api():
    return ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="api",
        operation="call",
        arguments={"url": "https://api.example.com/data", "method": "POST", "body": {"key": "value"}}
    )

@pytest.mark.asyncio
async def test_api_call_missing_url():
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="api",
        operation="call",
        arguments={"method": "GET"}
    )
    result = await api_call_handler(action)
    assert not result.success
    assert result.error == "Missing 'url' argument"

@pytest.mark.asyncio
async def test_api_call_unsupported_method():
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="api",
        operation="call",
        arguments={"url": "https://example.com", "method": "INVALID"}
    )
    result = await api_call_handler(action)
    assert not result.success
    assert "Unsupported method" in result.error

@pytest.mark.asyncio
@patch("socket.getaddrinfo", return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
@patch("app.connectors.api_connector.httpx.AsyncClient")
async def test_api_call_success(mock_httpx_class, mock_dns, fake_action_api):
    mock_client = mock_httpx_class.return_value.__aenter__.return_value
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"status": "ok"}'
    mock_response.raise_for_status = MagicMock()
    mock_client.request.return_value = mock_response
    
    result = await api_call_handler(fake_action_api)
    
    assert result.success
    assert result.output == '{"status": "ok"}'
    mock_client.request.assert_called_once_with("POST", "https://api.example.com/data", headers={}, json={"key": "value"})

@pytest.mark.asyncio
@patch("socket.getaddrinfo", return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
@patch("app.connectors.api_connector.httpx.AsyncClient")
async def test_api_call_http_error(mock_httpx_class, mock_dns, fake_action_api):
    mock_client = mock_httpx_class.return_value.__aenter__.return_value
    
    # Simuler une erreur HTTP
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Forbidden"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
    
    mock_client.request.return_value = mock_response
    
    result = await api_call_handler(fake_action_api)
    
    assert not result.success
    assert result.error_code == "API_HTTP_ERROR"
    assert "403" in result.error


@pytest.mark.asyncio
@pytest.mark.parametrize("target_url", [
    "http://127.0.0.1:8000/api/v1/decisions",
    "http://localhost:5432",
    "http://10.0.0.1:80/secret",
    "http://172.16.0.10:8080/data",
    "http://192.168.1.1/router",
    "http://169.254.169.254/latest/meta-data",
    "file:///etc/passwd",
    "ftp://example.com/file",
])
async def test_api_call_ssrf_violations_blocked(target_url):
    """Vérifie que api_call_handler rejette immédiatement les URLs privées/internes/métadonnées."""
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="api",
        operation="call",
        arguments={"url": target_url, "method": "GET"}
    )
    result = await api_call_handler(action)
    assert not result.success
    assert result.error_code == "SSRF_SECURITY_VIOLATION"
    assert "SSRF Security Violation" in result.error

