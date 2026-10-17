"""Automated tests for Inbound Portfolio Gateway & Concierge Service."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.inbound.services.portfolio_handler import PortfolioConciergeService, is_rate_limited
from app.inbound.schemas import PortfolioInboundMessageRequest


@pytest.mark.asyncio
async def test_inbound_portfolio_health():
    """Verify health endpoint of the portfolio inbound gateway."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/inbound/portfolio/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "rockib-quenum.netlify.app" in data["portfolio_target"]


@pytest.mark.asyncio
async def test_inbound_portfolio_message_flow():
    """Verify portfolio message processing with mock AI provider."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Bonjour ! Rockib conçoit des systèmes réels comme MARTISTORE."

    service = PortfolioConciergeService(ai_provider=mock_provider)
    req = PortfolioInboundMessageRequest(
        message="Comment fonctionne le vendeur IA WhatsApp ?",
        page_url="https://rockib-quenum.netlify.app/",
    )

    response = await service.handle_message(req, client_ip="192.168.1.50")
    assert response.status_code if hasattr(response, "status_code") else True
    assert "MARTISTORE" in response.reply
    assert response.lead_captured is False
    assert response.status == "ok"
    assert response.conversation_id is not None


@pytest.mark.asyncio
async def test_inbound_portfolio_lead_capture():
    """Verify that providing an email captures a qualified lead."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Merci pour votre intérêt, je transmets vos coordonnées à Rockib."

    service = PortfolioConciergeService(ai_provider=mock_provider)
    req = PortfolioInboundMessageRequest(
        message="Je souhaite un devis pour un site e-commerce. Mon email est client@agency.com et budget 2M FCFA",
        page_url="https://rockib-quenum.netlify.app/",
    )

    response = await service.handle_message(req, client_ip="192.168.1.51")
    assert response.lead_captured is True
    assert "client@agency.com" in response.reply


def test_rate_limiter_eviction():
    """Verify that exceeding rate limits returns True."""
    test_ip = "10.0.0.99"
    # Exhaust budget (max 20)
    for _ in range(20):
        is_rate_limited(test_ip)

    # 21st call must be blocked
    assert is_rate_limited(test_ip) is True


@pytest.mark.asyncio
async def test_multi_site_concierge_customization_and_knowledge_base():
    """Verify each client site can customize its concierge branding and knowledge base."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create/Update a custom client site config
        custom_payload = {
            "business_name": "Clinique Espoir · Accueil IA",
            "subtitle": "Consultations 24h/24 · Pédiatrie & Cardiologie",
            "launcher_label": "🏥 Accueil Médical IA",
            "primary_color": "#38BDF8",
            "position": "left",
            "default_voice": "denise",
            "welcome_message": "Bienvenue à la Clinique Espoir ! Comment puis-je vous orienter ?",
            "voice_greeting": "Bonjour et bienvenue à la Clinique Espoir.",
            "quick_chips": ["Prendre RDV", "Horaires d'ouverture"],
            "assistant_role": "Tu es l'assistante d'accueil de la Clinique Espoir à Cotonou.",
            "knowledge_base": "SPÉCIALITÉS : Cardiologie, Pédiatrie, Imagerie IRM. HORAIRES : 24h/24.",
            "pricing_rule": "Pour tout devis chirurgical, redirige vers le secrétariat.",
            "contact_whatsapp": "+229 01 97 00 00 00",
            "contact_email": "contact@clinique-espoir.bj",
            "client_token": "secret-clinique-token",
        }
        put_resp = await client.put("/api/v1/inbound/sites/clinique-espoir/config", json=custom_payload)
        assert put_resp.status_code == 200
        saved = put_resp.json()
        assert saved["config"]["site_key"] == "clinique-espoir"
        assert saved["config"]["business_name"] == "Clinique Espoir · Accueil IA"
        assert saved["config"]["primary_color"] == "#38BDF8"
        assert "Cardiologie" in saved["config"]["knowledge_base"]
        assert "data-site-key=\"clinique-espoir\"" in saved["embed_script"]

        # 2. Verify wrong token is rejected with 403
        bad_payload = dict(custom_payload, client_token="wrong-token")
        bad_resp = await client.put("/api/v1/inbound/sites/clinique-espoir/config", json=bad_payload)
        assert bad_resp.status_code == 403

        # 3. Verify GET returns the customized config & knowledge base
        get_resp = await client.get("/api/v1/inbound/sites/clinique-espoir/config")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["position"] == "left"
        assert "Imagerie IRM" in fetched["knowledge_base"]

        # 4. Verify chat handler injects the client's specific knowledge base into the LLM system prompt
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = "La Clinique Espoir propose la Cardiologie et l'Imagerie IRM 24h/24."
        service = PortfolioConciergeService(ai_provider=mock_provider)
        msg_req = PortfolioInboundMessageRequest(
            message="Quelles sont vos spécialités ?",
            site_key="clinique-espoir",
        )
        msg_res = await service.handle_message(msg_req, client_ip="192.168.1.99")
        assert "Clinique Espoir" in msg_res.reply
        sent_messages = mock_provider.generate.call_args[0][0]
        assert "Imagerie IRM" in sent_messages[0]["content"]

