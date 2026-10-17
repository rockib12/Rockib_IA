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
