import pytest
import uuid
import httpx
from unittest.mock import patch, AsyncMock

from app.execution.models import ActionRecord
from app.connectors.web_connectors import web_search_handler, web_fetch_handler

@pytest.fixture
def fake_action_search():
    return ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="web",
        operation="search",
        arguments={"query": "test query", "max_results": 2}
    )

@pytest.fixture
def fake_action_fetch():
    return ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="web",
        operation="fetch",
        arguments={"url": "https://example.com"}
    )

@pytest.mark.asyncio
async def test_web_search_missing_query():
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="web",
        operation="search",
        arguments={}
    )
    result = await web_search_handler(action)
    assert not result.success
    assert result.error == "Missing 'query' argument"

@pytest.mark.asyncio
@patch("app.connectors.web_connectors.DDGS")
async def test_web_search_success(mock_ddgs_class, fake_action_search):
    # Setup mock
    mock_ddgs_instance = mock_ddgs_class.return_value.__enter__.return_value
    mock_ddgs_instance.text.return_value = [
        {"title": "Result 1", "href": "http://res1.com", "body": "Snippet 1"},
        {"title": "Result 2", "href": "http://res2.com", "body": "Snippet 2"}
    ]
    
    result = await web_search_handler(fake_action_search)
    
    assert result.success
    assert "Result 1" in result.output
    assert "http://res2.com" in result.output
    mock_ddgs_instance.text.assert_called_once_with("test query", max_results=2)

@pytest.mark.asyncio
async def test_web_fetch_missing_url():
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="web",
        operation="fetch",
        arguments={}
    )
    result = await web_fetch_handler(action)
    assert not result.success
    assert result.error == "Missing 'url' argument"

@pytest.mark.asyncio
@patch("app.connectors.web_connectors.httpx.AsyncClient")
async def test_web_fetch_success(mock_httpx_class, fake_action_fetch):
    mock_client = mock_httpx_class.return_value.__aenter__.return_value
    
    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_redirect = False
    mock_response.text = "<html><head><title>Test</title><script>var a = 1;</script></head><body><h1>Hello World</h1><p>This is a test.</p></body></html>"
    mock_response.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_response
    
    result = await web_fetch_handler(fake_action_fetch)
    
    assert result.success
    # Le script doit être retiré, et le texte extrait
    assert "var a = 1;" not in result.output
    assert "Hello World" in result.output
    assert "This is a test." in result.output
    mock_client.get.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize("target_url", [
    "http://127.0.0.1:8000/internal",
    "http://localhost:6379",
    "http://10.200.0.1/admin",
    "http://172.16.5.5/",
    "http://192.168.0.254/status",
    "http://169.254.169.254/latest/meta-data",
    "ftp://example.com/",
])
async def test_web_fetch_ssrf_violations_blocked(target_url):
    """Vérifie que web_fetch_handler bloque les adresses locales, privées et métadonnées cloud."""
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="web",
        operation="fetch",
        arguments={"url": target_url}
    )
    result = await web_fetch_handler(action)
    assert not result.success
    assert result.error_code == "SSRF_SECURITY_VIOLATION"
    assert "SSRF Security Violation" in result.error


@pytest.mark.asyncio
@patch("app.connectors.web_connectors.httpx.AsyncClient")
async def test_web_fetch_ssrf_redirect_blocked(mock_httpx_class, fake_action_fetch):
    """Vérifie qu'une redirection vers une adresse de métadonnées cloud est interceptée et bloquée."""
    mock_client = mock_httpx_class.return_value.__aenter__.return_value
    from unittest.mock import MagicMock

    # Premier appel renvoie une redirection 302 vers 169.254.169.254
    mock_redirect = MagicMock()
    mock_redirect.is_redirect = True
    mock_redirect.status_code = 302
    mock_redirect.headers = {"location": "http://169.254.169.254/latest/meta-data/"}

    mock_client.get.return_value = mock_redirect

    result = await web_fetch_handler(fake_action_fetch)
    assert not result.success
    assert result.error_code == "SSRF_REDIRECT_BLOCKED"
    assert "SSRF Security Violation in redirect" in result.error

