"""Tests for Concierge execution tracing, cost calculation, and lead dispatch."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.inbound.schemas import PortfolioInboundMessageRequest, VoiceCallTurnRequest
from app.inbound.services.portfolio_handler import PortfolioConciergeService
from app.inbound.services.tracing import ConciergeTraceData, ConciergeTracingService
from app.inbound.services.voice_call_service import VoiceCallService
from app.intelligence.services.providers.groq_provider import (
    ProviderGenerationResult,
    compute_token_cost,
)


def test_token_cost_calculation():
    """Verify cost formula matches published model pricing."""
    # 70B model: $0.59 / 1M prompt, $0.79 / 1M completion
    cost_70b = compute_token_cost("llama-3.3-70b-versatile", 1000, 500)
    expected_70b = round((1000 * 0.59 + 500 * 0.79) / 1_000_000.0, 6)
    assert cost_70b == expected_70b

    # 8B model: $0.05 / 1M prompt, $0.08 / 1M completion
    cost_8b = compute_token_cost("llama-3.1-8b-instant", 2000, 1000)
    expected_8b = round((2000 * 0.05 + 1000 * 0.08) / 1_000_000.0, 6)
    assert cost_8b == expected_8b


@pytest.mark.asyncio
async def test_trace_recorded_on_message():
    """Verify that handle_message records trace with tokens, cost, and tools."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Bonjour ! Rockib Quenum a développé MARTISTORE et WaAuto."

    service = PortfolioConciergeService(ai_provider=mock_provider)
    tracing = ConciergeTracingService(max_in_memory_traces=100)

    with patch("app.inbound.services.portfolio_handler.concierge_tracing_service", tracing):
        req = PortfolioInboundMessageRequest(
            message="Quels sont les projets récents de Rockib ?",
            site_key="rockib-portfolio",
            conversation_id="conv-trace-test-01",
        )
        resp = await service.handle_message(req, client_ip="192.168.1.101")
        assert resp.status == "ok"

        traces = await tracing.get_traces(conversation_id="conv-trace-test-01")
        assert len(traces) == 1
        t = traces[0]
        assert t.conversation_id == "conv-trace-test-01"
        assert t.channel == "chat"
        assert t.result_status == "ok"
        assert t.total_tokens > 0
        assert t.duration_ms >= 0.0
        assert "site_knowledge_base" in t.tools_called
        assert t.lead_captured is False


@pytest.mark.asyncio
async def test_trace_and_telegram_lead_dispatch():
    """Verify that detecting contact details captures lead and notifies Telegram."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Merci pour votre message, vos coordonnées sont bien enregistrées !"

    service = PortfolioConciergeService(ai_provider=mock_provider)
    tracing = ConciergeTracingService(max_in_memory_traces=100)

    with patch("app.inbound.services.portfolio_handler.concierge_tracing_service", tracing):
        with patch("app.inbound.services.tracing.telegram_service") as mock_tg:
            mock_tg.is_configured.return_value = True
            mock_tg.admin_chat_id = "12345678"
            mock_tg.send_message = AsyncMock(return_value={"ok": True})

            req = PortfolioInboundMessageRequest(
                message="Je souhaite automatiser notre service client. Mon WhatsApp est +229 97 00 11 22 et mon email contact@fintech.bj",
                site_key="rockib-portfolio",
                conversation_id="conv-lead-tg-01",
            )
            resp = await service.handle_message(req, client_ip="192.168.1.102")
            assert resp.lead_captured is True

            traces = await tracing.get_traces(conversation_id="conv-lead-tg-01")
            assert len(traces) == 1
            t = traces[0]
            assert t.lead_captured is True
            assert t.transferred_to_rockib is True
            assert "lead_capture" in t.tools_called
            assert "telegram_notify" in t.tools_called

            # Check Telegram message call
            mock_tg.send_message.assert_awaited_once()
            call_kwargs = mock_tg.send_message.await_args[1]
            assert call_kwargs["chat_id"] == "12345678"
            assert "+229 97 00 11 22" in call_kwargs["text"]
            assert "contact@fintech.bj" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_voice_turn_trace():
    """Verify voice turns record voice channel traces with prosody tools."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Bonjour, bienvenue sur le service vocal de Rockib."

    voice_svc = VoiceCallService(ai_provider=mock_provider)
    tracing = ConciergeTracingService(max_in_memory_traces=100)

    # Initialize a session
    sess_resp = voice_svc.start_call_session(
        AsyncMock(site_key="rockib-portfolio", page_url="https://test", visitor_id="v1"),
        client_ip="192.168.1.103",
    )
    sid = sess_resp.session_id

    with patch("app.inbound.services.voice_call_service.concierge_tracing_service", tracing):
        turn_req = VoiceCallTurnRequest(
            session_id=sid,
            user_speech_transcript="Bonjour, j'aimerais en savoir plus sur votre architecture",
            site_key="rockib-portfolio",
        )
        turn_resp = await voice_svc.handle_voice_turn(turn_req, client_ip="192.168.1.103")
        assert turn_resp.status == "ok"

        traces = await tracing.get_traces(conversation_id=sid)
        assert len(traces) == 1
        t = traces[0]
        assert t.channel == "voice"
        assert "voice_prosody" in t.tools_called


@pytest.mark.asyncio
async def test_api_traces_and_metrics_endpoints():
    """Verify GET /api/v1/inbound/traces and GET /api/v1/inbound/metrics."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get metrics
        metrics_resp = await client.get("/api/v1/inbound/metrics")
        assert metrics_resp.status_code == 200
        m_data = metrics_resp.json()
        assert "total_requests" in m_data
        assert "success_rate" in m_data
        assert "total_cost_usd" in m_data

        # Get traces
        traces_resp = await client.get("/api/v1/inbound/traces?limit=10")
        assert traces_resp.status_code == 200
        assert isinstance(traces_resp.json(), list)
