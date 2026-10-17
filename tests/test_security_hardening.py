"""Tests de sécurité exhaustifs pour les correctifs critiques P0-1, P0-2, P1-1 et P1-2.

Couvre :
- P0-1 : Validation stricte du header X-Telegram-Bot-Api-Secret-Token sur le webhook Telegram
- P0-2 : Protection anti-SSRF (DNS + plages privées + métadonnées cloud + blocage de redirections)
- P1-1 : Fail-fast du Credential Vault et interdiction des clés par défaut au démarrage
- P1-2 : Authentification JWT, isolation multi-tenant (403) et anti-énumération (404) sur /api/v1/decisions/
"""
from __future__ import annotations

import socket
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.connectors.api_connector import api_call_handler
from app.connectors.web_connectors import web_fetch_handler
from app.core.config import settings
from app.core.network_security import SSRFSecurityViolation, validate_url_for_ssrf
from app.credentials.services.vault import derive_master_key
from app.decision_engine.schemas import DecisionRequest
from app.execution.models import ActionRecord
from app.identity.models import Agent, User, UserRole, Workspace, workspace_memberships
from app.main import app
from app.telegram.services.telegram_service import TelegramService


# =========================================================================== #
# P0-1 : Webhook Telegram — Validation de secret_token
# =========================================================================== #

@pytest.mark.asyncio
async def test_telegram_webhook_missing_secret_token_returns_403():
    """Requête au webhook Telegram sans header secret -> 403 Forbidden."""
    test_secret = "webhook_secret_secure_987654321"
    with patch.object(settings, "TELEGRAM_WEBHOOK_SECRET", test_secret):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/inbound/telegram/webhook",
                json={"update_id": 1, "message": {"text": "/status"}},
            )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Invalid webhook secret token"


@pytest.mark.asyncio
async def test_telegram_webhook_wrong_secret_token_returns_403():
    """Requête au webhook Telegram avec un mauvais token -> 403 Forbidden."""
    test_secret = "webhook_secret_secure_987654321"
    with patch.object(settings, "TELEGRAM_WEBHOOK_SECRET", test_secret):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/inbound/telegram/webhook",
                json={"update_id": 1, "message": {"text": "/status"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "bad_secret_intruder"},
            )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Invalid webhook secret token"


@pytest.mark.asyncio
async def test_telegram_webhook_valid_secret_token_succeeds():
    """Requête au webhook Telegram avec le token exact -> traitement 200."""
    test_secret = "webhook_secret_secure_987654321"
    with patch.object(settings, "TELEGRAM_WEBHOOK_SECRET", test_secret):
        with patch("app.inbound.router.telegram_service.process_update", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = {"status": "ok"}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/inbound/telegram/webhook",
                    json={"update_id": 1, "message": {"text": "/status"}},
                    headers={"X-Telegram-Bot-Api-Secret-Token": test_secret},
                )
                assert resp.status_code == 200
                assert resp.json() == {"status": "ok"}
                mock_proc.assert_called_once()


# =========================================================================== #
# P0-2 : Protection Anti-SSRF (DNS + IP + Redirections)
# =========================================================================== #

@pytest.mark.parametrize("bad_url", [
    "http://127.0.0.1:8000/",
    "http://127.0.0.1:5432/",
    "http://localhost:6379/",
    "http://10.0.0.1/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "ftp://example.com/file",
    "file:///etc/shadow",
    "",
])
def test_validate_url_for_ssrf_rejects_dangerous_targets(bad_url):
    """Vérifie que la fonction de filtrage SSRF lève une exception sur toute adresse interne/réservée."""
    with pytest.raises(SSRFSecurityViolation):
        validate_url_for_ssrf(bad_url)


@patch("socket.getaddrinfo", return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
def test_validate_url_for_ssrf_accepts_public_url(mock_dns):
    """Vérifie qu'une adresse publique légitime est acceptée après résolution DNS."""
    ips = validate_url_for_ssrf("https://example.com/api/data")
    assert "93.184.216.34" in ips


@pytest.mark.asyncio
async def test_api_connector_blocks_ssrf_before_http_request():
    """Vérifie que api_call_handler bloque les cibles SSRF sans émettre de requête."""
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="api",
        operation="call",
        arguments={"url": "http://169.254.169.254/latest/meta-data/", "method": "GET"}
    )
    res = await api_call_handler(action)
    assert not res.success
    assert res.error_code == "SSRF_SECURITY_VIOLATION"


@pytest.mark.asyncio
@patch("app.connectors.web_connectors.httpx.AsyncClient")
async def test_web_fetch_blocks_ssrf_redirect(mock_httpx_class):
    """Vérifie que web_fetch_handler bloque les redirections pointant vers une IP interne."""
    mock_client = mock_httpx_class.return_value.__aenter__.return_value

    redirect_resp = MagicMock()
    redirect_resp.is_redirect = True
    redirect_resp.status_code = 301
    redirect_resp.headers = {"location": "http://127.0.0.1:8000/internal"}
    mock_client.get.return_value = redirect_resp

    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]):
        action = ActionRecord(
            id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            tool="web",
            operation="fetch",
            arguments={"url": "https://legit-site.com/start"}
        )
        res = await web_fetch_handler(action)
        assert not res.success
        assert res.error_code == "SSRF_REDIRECT_BLOCKED"


@pytest.mark.asyncio
async def test_dns_rebinding_backend_pins_tcp_connection():
    """Vérifie que PinnedIPBackend force le socket TCP sur l'IP pré-validée en ignorant le hostname."""
    from app.core.network_security import PinnedIPBackend

    backend = PinnedIPBackend(pinned_ip="93.184.216.34")
    with patch("httpcore.AnyIOBackend.connect_tcp", new=AsyncMock()) as mock_super_connect:
        await backend.connect_tcp(
            host="attacker-rebind.evil.com",
            port=443,
            timeout=5.0,
            local_address=None,
            socket_options=None,
        )
        mock_super_connect.assert_called_once_with(
            host="93.184.216.34",
            port=443,
            timeout=5.0,
            local_address=None,
            socket_options=None,
        )


@pytest.mark.asyncio
@patch("socket.getaddrinfo", return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
@patch("app.connectors.api_connector.httpx.AsyncClient")
async def test_api_connector_pins_transport_to_validated_ip(mock_httpx_class, mock_dns):
    """Vérifie que api_call_handler passe un transport épinglé sur l'IP validée à httpx.AsyncClient."""
    mock_client = mock_httpx_class.return_value.__aenter__.return_value
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_resp.raise_for_status = MagicMock()
    mock_client.request.return_value = mock_resp

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="api",
        operation="call",
        arguments={"url": "https://api.external.com/v1/test", "method": "GET"}
    )
    res = await api_call_handler(action)
    assert res.success

    # Vérification que httpx.AsyncClient a reçu un transport épinglé sur 93.184.216.34
    call_kwargs = mock_httpx_class.call_args.kwargs
    assert "transport" in call_kwargs
    transport = call_kwargs["transport"]
    assert transport._pool._network_backend.pinned_ip == "93.184.216.34"


@pytest.mark.asyncio
@patch("socket.getaddrinfo", return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
@patch("app.connectors.web_connectors.httpx.AsyncClient")
async def test_web_fetch_pins_transport_to_validated_ip(mock_httpx_class, mock_dns):
    """Vérifie que web_fetch_handler passe un transport épinglé sur l'IP validée à httpx.AsyncClient."""
    mock_client = mock_httpx_class.return_value.__aenter__.return_value
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_redirect = False
    mock_resp.text = "<html><body>Clean Content</body></html>"
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="web",
        operation="fetch",
        arguments={"url": "https://target-site.com/page"}
    )
    res = await web_fetch_handler(action)
    assert res.success

    # Vérification que httpx.AsyncClient a reçu un transport épinglé sur 93.184.216.34
    call_kwargs = mock_httpx_class.call_args.kwargs
    assert "transport" in call_kwargs
    transport = call_kwargs["transport"]
    assert transport._pool._network_backend.pinned_ip == "93.184.216.34"



# =========================================================================== #
# P1-1 : Credential Vault — Fail-Fast et Clés par Défaut
# =========================================================================== #

def test_derive_master_key_fails_when_vault_key_missing():
    """derive_master_key refuse de fonctionner sans CREDENTIAL_VAULT_KEY explicite."""
    with patch.object(settings, "CREDENTIAL_VAULT_KEY", None):
        with pytest.raises(RuntimeError) as exc_info:
            derive_master_key()
        assert "CREDENTIAL_VAULT_KEY is not defined" in str(exc_info.value)


@pytest.mark.asyncio
async def test_lifespan_fail_fast_on_insecure_defaults():
    """Le serveur refuse de démarrer si CREDENTIAL_VAULT_KEY est absent et JWT_SECRET_KEY est par défaut."""
    from app.main import lifespan
    default_secret = "supersecretkeythatisatleast32characterslongforsecurity"
    with patch.object(settings, "CREDENTIAL_VAULT_KEY", None):
        with patch.object(settings, "JWT_SECRET_KEY", default_secret):
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass
            assert "FATAL SECURITY CONFIGURATION ERROR" in str(exc_info.value)


# =========================================================================== #
# P1-2 : Authentification et Cloisonnement Multi-Tenant sur /decisions/
# =========================================================================== #

@pytest.mark.asyncio
async def test_post_decisions_unauthenticated_returns_401():
    """POST /api/v1/decisions/ sans token Bearer -> 401 Unauthorized."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "workspace_id": str(uuid.uuid4()),
            "agent_id": str(uuid.uuid4()),
            "objective": "Test security",
            "proposed_action": "Read document",
        }
        res = await client.post("/api/v1/decisions/", json=payload)
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_post_decisions_foreign_workspace_returns_403(db_session: AsyncSession):
    """POST /api/v1/decisions/ sur un workspace dont l'utilisateur n'est pas membre -> 403 Forbidden."""
    from sqlalchemy import insert
    from app.core.database import get_async_db
    from app.core.security import create_access_token

    # Workspace A (membre) et Workspace B (étranger)
    ws_a = Workspace(name="WS Auth A", slug=f"wsa-{uuid.uuid4().hex[:8]}")
    ws_b = Workspace(name="WS Auth B", slug=f"wsb-{uuid.uuid4().hex[:8]}")
    user_a = User(email=f"u-{uuid.uuid4().hex[:8]}@test.io", password_hash="x", is_active=True)
    db_session.add_all([ws_a, ws_b, user_a])
    await db_session.flush()

    await db_session.execute(
        insert(workspace_memberships).values(
            workspace_id=ws_a.id, user_id=user_a.id, role=UserRole.admin
        )
    )
    await db_session.flush()

    agent_b = Agent(workspace_id=ws_b.id, name="Agent B", default_autonomy_level=3)
    db_session.add(agent_b)
    await db_session.flush()

    token = create_access_token({"sub": str(user_a.id)})

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_async_db] = _override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            payload = {
                "workspace_id": str(ws_b.id),
                "agent_id": str(agent_b.id),
                "objective": "Unauthorized attempt",
                "proposed_action": "Execute privileged operation",
            }
            res = await client.post("/api/v1/decisions/", json=payload)
            assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_decisions_foreign_agent_returns_404(db_session: AsyncSession):
    """POST /api/v1/decisions/ avec agent_id n'appartenant pas au workspace -> 404 (anti-énumération)."""
    from sqlalchemy import insert
    from app.core.database import get_async_db
    from app.core.security import create_access_token

    ws_a = Workspace(name="WS Valid", slug=f"wsv-{uuid.uuid4().hex[:8]}")
    user_a = User(email=f"u2-{uuid.uuid4().hex[:8]}@test.io", password_hash="x", is_active=True)
    db_session.add_all([ws_a, user_a])
    await db_session.flush()

    await db_session.execute(
        insert(workspace_memberships).values(
            workspace_id=ws_a.id, user_id=user_a.id, role=UserRole.admin
        )
    )
    await db_session.flush()

    token = create_access_token({"sub": str(user_a.id)})

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_async_db] = _override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            # Agent UUID aléatoire / étranger
            payload = {
                "workspace_id": str(ws_a.id),
                "agent_id": str(uuid.uuid4()),
                "objective": "Probe foreign agent",
                "proposed_action": "Read document",
            }
            res = await client.post("/api/v1/decisions/", json=payload)
            assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_decisions_authorized_member_success(db_session: AsyncSession):
    """POST /api/v1/decisions/ membre authentifié + agent valide -> 200 OK."""
    from sqlalchemy import insert
    from app.core.database import get_async_db
    from app.core.security import create_access_token
    from app.decision_engine.models import ControlOutcome, RiskLevel
    from app.decision_engine.schemas import DecisionResponse

    ws_a = Workspace(name="WS Success", slug=f"wss-{uuid.uuid4().hex[:8]}")
    user_a = User(email=f"u3-{uuid.uuid4().hex[:8]}@test.io", password_hash="x", is_active=True)
    db_session.add_all([ws_a, user_a])
    await db_session.flush()

    agent_a = Agent(workspace_id=ws_a.id, name="Agent Valid", default_autonomy_level=3)
    db_session.add(agent_a)
    await db_session.flush()

    await db_session.execute(
        insert(workspace_memberships).values(
            workspace_id=ws_a.id, user_id=user_a.id, role=UserRole.admin
        )
    )
    await db_session.flush()

    token = create_access_token({"sub": str(user_a.id)})

    mock_resp = DecisionResponse(
        decision_id=str(uuid.uuid4()),
        dominant_source="arbitrator",
        final_action="Read logs",
        risk_level="low",
        approval_required=False,
        control_outcome=ControlOutcome.ALLOW,
        control_reason="Risk is low and policy allows",
        permission_granted=True,
    )

    async def _override_db():
        yield db_session

    from app.decision_engine.router import get_orchestrator
    mock_orchestrator = MagicMock()
    mock_orchestrator.handle_decision = AsyncMock(return_value=mock_resp)

    app.dependency_overrides[get_async_db] = _override_db
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            payload = {
                "workspace_id": str(ws_a.id),
                "agent_id": str(agent_a.id),
                "objective": "Legitimate task",
                "proposed_action": "Read logs",
            }
            res = await client.post("/api/v1/decisions/", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["control_outcome"] == "ALLOW"
            assert data["approval_required"] is False
    finally:
        app.dependency_overrides.clear()

