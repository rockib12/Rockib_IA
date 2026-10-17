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


# =========================================================================== #
# P4 : GET /api/v1/decisions/ & GET /api/v1/decisions/{id} & CSP Sandbox
# =========================================================================== #

@pytest.mark.asyncio
async def test_get_decisions_requires_auth():
    """GET /api/v1/decisions/ et GET /api/v1/decisions/{id} sans token -> 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_list = await client.get("/api/v1/decisions/")
        assert r_list.status_code == 401
        r_get = await client.get(f"/api/v1/decisions/{uuid.uuid4()}")
        assert r_get.status_code == 401


@pytest.mark.asyncio
async def test_get_decisions_multi_tenant_isolation_and_anti_enumeration(db_session: AsyncSession):
    """Vérifie que GET /api/v1/decisions/ filtre par workspace et que GET /{id} retourne 404 sur un tenant étranger."""
    from sqlalchemy import insert
    from app.core.database import get_async_db
    from app.core.security import create_access_token
    from app.decision_engine.models import (
        ControlOutcome,
        Decision,
        DecisionStatus,
        ImpactType,
        ReversibilityLevel,
        RiskLevel,
    )

    ws_a = Workspace(name="WS Dec A", slug=f"wsda-{uuid.uuid4().hex[:8]}")
    ws_b = Workspace(name="WS Dec B", slug=f"wsdb-{uuid.uuid4().hex[:8]}")
    user_a = User(email=f"uda-{uuid.uuid4().hex[:8]}@test.io", password_hash="x", is_active=True)
    db_session.add_all([ws_a, ws_b, user_a])
    await db_session.flush()

    await db_session.execute(
        insert(workspace_memberships).values(
            workspace_id=ws_a.id, user_id=user_a.id, role=UserRole.admin
        )
    )
    agent_a = Agent(workspace_id=ws_a.id, name="Agent A", default_autonomy_level=2)
    agent_b = Agent(workspace_id=ws_b.id, name="Agent B", default_autonomy_level=2)
    db_session.add_all([agent_a, agent_b])
    await db_session.flush()

    dec_a = Decision(
        workspace_id=ws_a.id,
        agent_id=agent_a.id,
        objective="Obj A",
        situation="Sit A",
        proposed_action="Read A",
        risk_level=RiskLevel.low,
        risk_reversibility=ReversibilityLevel.reversible,
        risk_impact=ImpactType.internal,
        requested_autonomy_level=2,
        applied_autonomy_level=2,
        control_outcome=ControlOutcome.ALLOW,
        control_reason="POLICY_ALLOWED",
        permission_granted=True,
        status=DecisionStatus.executed,
    )
    dec_b = Decision(
        workspace_id=ws_b.id,
        agent_id=agent_b.id,
        objective="Obj B Secret",
        situation="Sit B",
        proposed_action="Read B",
        risk_level=RiskLevel.high,
        risk_reversibility=ReversibilityLevel.irreversible,
        risk_impact=ImpactType.financial,
        requested_autonomy_level=2,
        applied_autonomy_level=2,
        control_outcome=ControlOutcome.ESCALATE,
        control_reason="RISK_HIGH",
        permission_granted=False,
        status=DecisionStatus.escalated,
    )
    db_session.add_all([dec_a, dec_b])
    await db_session.flush()

    token_a = create_access_token({"sub": str(user_a.id)})

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_async_db] = _override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token_a}"},
        ) as client:
            # 1. Liste globale ne retourne que les décisions de ws_a
            res_list = await client.get("/api/v1/decisions/")
            assert res_list.status_code == 200
            ids = [d["decision_id"] for d in res_list.json()]
            assert str(dec_a.id) in ids
            assert str(dec_b.id) not in ids

            # 2. Filtre explicite sur ws_b -> 403 Forbidden
            res_forbid = await client.get(f"/api/v1/decisions/?workspace_id={ws_b.id}")
            assert res_forbid.status_code == 403

            # 3. Accès direct à dec_a -> 200 OK
            res_own = await client.get(f"/api/v1/decisions/{dec_a.id}")
            assert res_own.status_code == 200
            assert res_own.json()["decision_id"] == str(dec_a.id)

            # 4. Accès direct à dec_b (autre tenant) -> 404 Not Found (anti-énumération)
            res_foreign = await client.get(f"/api/v1/decisions/{dec_b.id}")
            assert res_foreign.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_preview_workspace_file_includes_csp_sandbox_header(tmp_path, monkeypatch):
    """Vérifie que l'endpoint de prévisualisation renvoie Content-Security-Policy: sandbox."""
    from app.core.signed_urls import sign_preview

    monkeypatch.setattr(settings, "WORKSPACES_ROOT", str(tmp_path))
    ws_id = uuid.uuid4()
    ws_dir = tmp_path / str(ws_id)
    ws_dir.mkdir(parents=True, exist_ok=True)
    html_file = ws_dir / "index.html"
    html_file.write_text("<html><body><h1>Rockib Sandbox</h1></body></html>", encoding="utf-8")

    exp, sig = sign_preview(ws_id, "index.html")
    signed_url = f"/api/v1/workspaces/{ws_id}/preview/index.html?exp={exp}&sig={sig}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(signed_url)
        assert res.status_code == 200
        csp = res.headers.get("content-security-policy", "")
        assert "sandbox" in csp
        assert res.headers.get("x-content-type-options") == "nosniff"


# ==============================================================================
# LOT P5 : Anti-Bruteforce Auth, X-Request-ID & Bounded Voice Sessions
# ==============================================================================


@pytest.mark.asyncio
async def test_auth_login_rate_limiting_blocks_bruteforce():
    """Vérifie que plus de 15 tentatives de login en 60s depuis une même IP renvoient HTTP 429."""
    from app.identity.router import _auth_ip_attempts, _AUTH_MAX_ATTEMPTS

    test_ip = "203.0.113.99"
    _auth_ip_attempts.pop(test_ip, None)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(_AUTH_MAX_ATTEMPTS):
                res = await client.post(
                    "/api/v1/auth/login",
                    json={"email": "nonexistent_bruteforce@example.com", "password": "wrongpassword"},
                    headers={"X-Forwarded-For": test_ip},
                )
                assert res.status_code == 401

            # La 16e tentative doit être bloquée en 429 Too Many Requests
            res_blocked = await client.post(
                "/api/v1/auth/login",
                json={"email": "nonexistent_bruteforce@example.com", "password": "wrongpassword"},
                headers={"X-Forwarded-For": test_ip},
            )
            assert res_blocked.status_code == 429
            assert res_blocked.headers.get("retry-after") == "60"
    finally:
        _auth_ip_attempts.pop(test_ip, None)


@pytest.mark.asyncio
async def test_x_request_id_header_injection_and_sanitization():
    """Vérifie l'injection automatique et la validation stricte du header X-Request-ID."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Sans header entrant -> UUID généré
        res1 = await client.get("/")
        assert res1.status_code == 200
        assert res1.headers.get("x-request-id") is not None
        assert len(res1.headers["x-request-id"]) >= 32

        # 2. Avec header valide -> conservé
        res2 = await client.get("/", headers={"X-Request-ID": "trace-rockib-2026-001"})
        assert res2.headers.get("x-request-id") == "trace-rockib-2026-001"

        # 3. Avec header malveillant (CRLF / caractères spéciaux) -> remplacé par un UUID propre
        res3 = await client.get("/", headers={"X-Request-ID": "bad<script>id"})
        assert res3.headers.get("x-request-id") != "bad<script>id"


def test_voice_call_session_ttl_and_capacity_eviction():
    """Vérifie que VoiceCallService évince les sessions expirées et plafonne la mémoire."""
    from app.inbound.services.voice_call_service import VoiceCallService, _SESSION_TTL_SECONDS
    from app.inbound.schemas import VoiceCallSessionRequest

    svc = VoiceCallService()
    resp1 = svc.start_call_session(VoiceCallSessionRequest(page_url="https://rockib-quenum.netlify.app/"))
    sid1 = resp1.session_id
    assert sid1 in svc._sessions

    # Vieillir artificiellement la session au-delà du TTL
    svc._sessions[sid1].created_at -= (_SESSION_TTL_SECONDS + 10)

    # Le démarrage d'une nouvelle session doit purger sid1
    resp2 = svc.start_call_session(VoiceCallSessionRequest(page_url="https://rockib-quenum.netlify.app/"))
    assert sid1 not in svc._sessions
    assert resp2.session_id in svc._sessions
