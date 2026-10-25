"""Tests for ElevenLabs Scribe v2 Realtime Flag & 100% Free Mode Dual-Control."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.inbound.services.elevenlabs_service import elevenlabs_service
from app.inbound.services.site_config_service import site_config_service
from app.inbound.services.voice_call_service import VoiceCallService
from app.main import app


@pytest.mark.asyncio
async def test_default_free_mode_behavior():
    """Verify default setting (ENABLE_ELEVENLABS_REALTIME=False) runs 100% free mode."""
    with patch.object(settings, "ENABLE_ELEVENLABS_REALTIME", False), \
         patch.object(settings, "ELEVENLABS_API_KEY", None):
        
        assert elevenlabs_service.is_realtime_enabled() is False
        
        caps = elevenlabs_service.get_capabilities()
        assert caps["realtime_enabled"] is False
        assert caps["provider"] == "native"
        assert caps["scribe_model"] == "web-speech-native"
        assert caps["free_mode_fallback_ready"] is True

        cfg = site_config_service.get_public_config("rockib-portfolio")
        assert cfg.realtime_voice_enabled is False
        assert cfg.voice_provider == "native"


@pytest.mark.asyncio
async def test_realtime_flag_true_without_key_falls_back_safely():
    """If ENABLE_ELEVENLABS_REALTIME is True but no API key is set, safe fallback to False."""
    with patch.object(settings, "ENABLE_ELEVENLABS_REALTIME", True), \
         patch.object(settings, "ELEVENLABS_API_KEY", ""):
        
        assert elevenlabs_service.is_realtime_enabled() is False
        cfg = site_config_service.get_public_config("rockib-portfolio")
        assert cfg.realtime_voice_enabled is False
        assert cfg.voice_provider == "native"


@pytest.mark.asyncio
async def test_realtime_flag_true_with_key():
    """If ENABLE_ELEVENLABS_REALTIME is True and key is present, realtime is enabled."""
    with patch.object(settings, "ENABLE_ELEVENLABS_REALTIME", True), \
         patch.object(settings, "ELEVENLABS_API_KEY", "sk_test_elevenlabs_realtime_key"):
        
        assert elevenlabs_service.is_realtime_enabled() is True
        
        caps = elevenlabs_service.get_capabilities()
        assert caps["realtime_enabled"] is True
        assert caps["provider"] == "elevenlabs"
        assert caps["scribe_model"] == "scribe_v2_realtime"
        assert caps["tts_model"] == "eleven_turbo_v2_5"

        cfg = site_config_service.get_public_config("rockib-portfolio")
        assert cfg.realtime_voice_enabled is True
        assert cfg.voice_provider == "elevenlabs"


@pytest.mark.asyncio
async def test_voice_capabilities_endpoint():
    """Verify GET /api/v1/inbound/voice/capabilities returns matching payload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. In default free mode
        with patch.object(settings, "ENABLE_ELEVENLABS_REALTIME", False):
            resp = await client.get("/api/v1/inbound/voice/capabilities")
            assert resp.status_code == 200
            data = resp.json()
            assert data["realtime_enabled"] is False
            assert data["provider"] == "native"
            assert data["barge_in_supported"] is True

        # 2. In realtime Scribe v2 mode
        with patch.object(settings, "ENABLE_ELEVENLABS_REALTIME", True), \
             patch.object(settings, "ELEVENLABS_API_KEY", "sk_test_key"):
            resp = await client.get("/api/v1/inbound/voice/capabilities")
            assert resp.status_code == 200
            data = resp.json()
            assert data["realtime_enabled"] is True
            assert data["provider"] == "elevenlabs"
            assert data["scribe_model"] == "scribe_v2_realtime"


@pytest.mark.asyncio
async def test_synthesize_neural_speech_fallback_on_elevenlabs_error():
    """If ElevenLabs throws or returns an error, synthesize_neural_speech automatically falls back to Edge-TTS."""
    service = VoiceCallService()
    fake_edge_audio = b"ID3_fake_edge_tts_audio_data"

    with patch.object(settings, "ENABLE_ELEVENLABS_REALTIME", True), \
         patch.object(settings, "ELEVENLABS_API_KEY", "sk_fake_key"), \
         patch.object(elevenlabs_service, "synthesize_speech", side_effect=Exception("ElevenLabs 429 Quota Exceeded")), \
         patch("edge_tts.Communicate") as mock_comm:
        
        # Configure mock edge_tts Communicate
        async def mock_stream():
            yield {"type": "audio", "data": fake_edge_audio}

        mock_instance = AsyncMock()
        mock_instance.stream = mock_stream
        mock_comm.return_value = mock_instance

        audio = await service.synthesize_neural_speech("Bonjour, ceci est un test de fallback.")
        assert audio == fake_edge_audio
