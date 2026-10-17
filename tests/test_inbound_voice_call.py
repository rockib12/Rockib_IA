"""Automated tests for Voice Calling and Callback Scheduling features."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.inbound.schemas import (
    CallMeBackRequest,
    VoiceCallSessionRequest,
    VoiceCallTurnRequest,
)
from app.inbound.services.voice_call_service import VoiceCallService


@pytest.mark.asyncio
async def test_start_voice_session():
    """Verify initiation of an interactive voice calling session."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/inbound/portfolio/voice/session",
            json={"page_url": "https://rockib-quenum.netlify.app/"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert len(data["session_id"]) > 10
        assert "Rockib Quenum" in data["greeting_text"]
        assert data["voice_locale"] == "fr-FR"


@pytest.mark.asyncio
async def test_voice_turn_flow_and_clean_speech():
    """Verify voice dialogue turn produces clean spoken text without markdown syntax."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Très bien ! Rockib a conçu le vendeur **MARTISTORE** sur #WhatsApp."

    service = VoiceCallService(ai_provider=mock_provider)
    session_resp = service.start_call_session(VoiceCallSessionRequest())

    turn_req = VoiceCallTurnRequest(
        session_id=session_resp.session_id,
        user_speech_transcript="Parlez-moi de vos réalisations",
    )

    turn_resp = await service.handle_voice_turn(turn_req)
    assert turn_resp.status == "ok"
    assert "MARTISTORE" in turn_resp.agent_reply_text
    # Verify markdown characters were stripped for TTS
    assert "**" not in turn_resp.agent_reply_text
    assert "#" not in turn_resp.agent_reply_text
    assert turn_resp.should_end_call is False


@pytest.mark.asyncio
async def test_voice_turn_lead_capture_and_end_call():
    """Verify spoken lead extraction and hang-up detection."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Entendu, nous vous recontacterons au revoir !"

    service = VoiceCallService(ai_provider=mock_provider)
    session_resp = service.start_call_session(VoiceCallSessionRequest())

    turn_req = VoiceCallTurnRequest(
        session_id=session_resp.session_id,
        user_speech_transcript="Mon email est ceo@entreprise.bj, merci au revoir !",
    )

    turn_resp = await service.handle_voice_turn(turn_req)
    assert turn_resp.lead_captured is True
    assert turn_resp.should_end_call is True


@pytest.mark.asyncio
async def test_request_callback_scheduling():
    """Verify scheduling of a phone or WhatsApp callback."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "phone_number": "+229 97 12 34 56",
            "contact_name": "Directeur Commercial",
            "topic": "Installation vendeur IA WhatsApp",
            "channel": "whatsapp",
            "preferred_time": "immediate",
        }
        resp = await client.post("/api/v1/inbound/portfolio/voice/request-callback", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "scheduled"
        assert data["channel"] == "whatsapp"
        assert "+229 97 12 34 56" in data["phone_number"]
        assert data["estimated_wait_minutes"] <= 10
