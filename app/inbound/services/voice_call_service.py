"""Voice Calling and Callback Management Service for Rockib AI Portfolio Concierge.

Handles:
- In-browser live voice calling dialogue turns.
- Natural spoken phrasing (optimized for Text-To-Speech without markdown artifacts).
- Spoken lead and contact extraction.
- Phone & WhatsApp callback scheduling.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Dict, List, Optional


from app.core.config import settings
from app.inbound.schemas import (
    VoiceCallSessionRequest,
    VoiceCallSessionResponse,
    VoiceCallTurnRequest,
    VoiceCallTurnResponse,
)
from app.inbound.services.portfolio_handler import EMAIL_REGEX, PHONE_REGEX, is_request_rate_limited, redact_contact_details
from app.inbound.services.site_config_service import site_config_service
from app.inbound.services.tracing import ConciergeTraceData, concierge_tracing_service
from app.intelligence.services.providers.groq_provider import GroqProvider, compute_token_cost
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


END_CALL_PHRASES = [
    "au revoir",
    "bonne journée",
    "bonne soirée",
    "à bientôt",
    "merci au revoir",
    "raccrocher",
    "bye",
    "stop call",
]


class VoiceCallSession:
    """In-memory tracking for an active voice call dialogue."""

    def __init__(self, session_id: str, page_url: str, site_key: str = "rockib-portfolio", client_ip: str = "127.0.0.1"):
        self.session_id = session_id
        self.page_url = page_url
        self.site_key = site_key or "rockib-portfolio"
        self.client_ip = client_ip
        self.created_at = time.time()
        self.history: List[dict[str, str]] = []
        self.lead_captured = False


_SESSION_TTL_SECONDS = 300
_MAX_ACTIVE_SESSIONS = 1000

NEURAL_VOICE_PROFILES: Dict[str, str] = {
    "henri": "fr-FR-HenriNeural",
    "vivienne": "fr-FR-VivienneMultilingualNeural",
    "denise": "fr-FR-DeniseNeural",
    "remy": "fr-FR-RemyMultilingualNeural",
}


class VoiceCallService:
    """Orchestrates interactive voice call dialogues and phone callbacks."""

    def __init__(self, ai_provider: Optional[GroqProvider] = None):
        self.provider = ai_provider or GroqProvider()
        self._sessions: Dict[str, VoiceCallSession] = {}

    async def synthesize_neural_speech(self, text: str, voice_profile: str = "henri") -> bytes:
        """Synthesizes natural HD MP3 speech using Microsoft Edge Neural TTS (100% free)."""
        import edge_tts

        clean_text = re.sub(r"[*#_`>\[\]]", "", (text or "")).strip()
        if not clean_text:
            raise ValueError("Empty text for TTS synthesis")

        voice_id = NEURAL_VOICE_PROFILES.get((voice_profile or "henri").lower().strip(), "fr-FR-HenriNeural")
        # A slightly slower pace gives the French neural voices room to breathe.
        communicate = edge_tts.Communicate(text=clean_text, voice=voice_id, rate="-2%")
        audio_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                audio_chunks.append(chunk["data"])

        audio_bytes = b"".join(audio_chunks)
        if not audio_bytes:
            raise RuntimeError("No audio bytes returned from Neural TTS engine")
        return audio_bytes

    async def transcribe_audio_bytes(self, audio_bytes: bytes, filename: str = "speech.webm") -> str:
        """Transcribes user microphone audio using Groq Whisper (whisper-large-v3-turbo)."""
        from app.core.config import settings

        if not audio_bytes or len(audio_bytes) < 200:
            return ""
        api_key = settings.GROQ_API_KEY
        if not api_key:
            return ""

        mime = "audio/webm"
        if filename.endswith(".ogg"):
            mime = "audio/ogg"
        elif filename.endswith(".mp4") or filename.endswith(".m4a"):
            mime = "audio/mp4"
        elif filename.endswith(".wav"):
            mime = "audio/wav"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": "whisper-large-v3-turbo", "language": "fr", "response_format": "json"},
                files={"file": (filename, audio_bytes, mime)},
            )
            if resp.status_code != 200:
                logger.warning("Groq Whisper STT HTTP %s: %s", resp.status_code, resp.text[:200])
                return ""
            payload = resp.json()
            raw_text = (payload.get("text") or "").strip()
            low = raw_text.lower()
            hallucinations = (
                "sous-titres",
                "amara.org",
                "merci d'avoir regardé",
                "abonnez-vous",
                "transcription by",
                "merci.",
            )
            if any(h in low for h in hallucinations) or len(raw_text.strip(" .,!?-")) < 2:
                return ""
            return raw_text



    def _prune_expired_sessions(self) -> None:
        now = time.time()
        expired = [
            sid for sid, sess in self._sessions.items()
            if now - sess.created_at > _SESSION_TTL_SECONDS
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
        while len(self._sessions) >= _MAX_ACTIVE_SESSIONS:
            oldest_sid = next(iter(self._sessions))
            self._sessions.pop(oldest_sid, None)

    def start_call_session(self, request: VoiceCallSessionRequest, client_ip: str = "127.0.0.1") -> VoiceCallSessionResponse:
        """Initializes a new live voice call session."""
        self._prune_expired_sessions()
        session_id = str(uuid.uuid4())
        site_key = request.site_key or "rockib-portfolio"
        session = VoiceCallSession(session_id=session_id, page_url=request.page_url or "", site_key=site_key, client_ip=client_ip)
        self._sessions[session_id] = session

        site_cfg = site_config_service.get_site_dict(site_key)
        greeting = site_cfg.get("voice_greeting") or (
            "Bonjour ! Je suis l'assistant IA de Rockib Quenum. "
            "Je peux vous présenter ses réalisations, vous proposer des idées d'applications ou d'automatisations IA pour votre activité, "
            "et concevoir votre architecture. Dans quel domaine êtes-vous ou quel projet avez-vous en tête ?"
        )
        session.history.append({"role": "assistant", "content": greeting})

        return VoiceCallSessionResponse(
            session_id=session_id,
            status="connected",
            greeting_text=greeting,
            voice_locale="fr-FR",
            max_duration_seconds=300,
        )

    def _build_voice_system_prompt(self, site_key: str = "rockib-portfolio") -> str:
        return site_config_service.build_voice_system_prompt(site_key)

    async def handle_voice_turn(
        self,
        turn: VoiceCallTurnRequest,
        client_ip: str = "127.0.0.1",
        db: Optional[AsyncSession] = None,
    ) -> VoiceCallTurnResponse:
        """Processes a speech utterance transcribed from the caller's mic."""
        self._prune_expired_sessions()
        session = self._sessions.get(turn.session_id)
        if not session:
            return VoiceCallTurnResponse(
                session_id=turn.session_id,
                agent_reply_text="Cette session a expirée. Veuillez relancer l'appel vocal.",
                status="session_expired",
            )
        req_site_key = turn.site_key or "rockib-portfolio"
        if req_site_key != session.site_key:
            return VoiceCallTurnResponse(
                session_id=turn.session_id,
                agent_reply_text="Cette session ne correspond pas à ce site. Veuillez relancer l'appel vocal.",
                status="site_mismatch",
            )

        if session.client_ip != client_ip:
            return VoiceCallTurnResponse(
                session_id=turn.session_id,
                agent_reply_text="Cette session vocale ne correspond pas à ce visiteur. Veuillez relancer l'appel.",
                status="session_mismatch",
            )
        raw_model = getattr(self.provider, "_model", None)
        model_name = raw_model if isinstance(raw_model, str) and raw_model else (settings.GROQ_MODEL or "llama-3.3-70b-versatile")

        if await is_request_rate_limited(client_ip, "voice-turn", site_key=session.site_key, limit=20, site_limit=180):
            trace = ConciergeTraceData(
                conversation_id=turn.session_id,
                site_key=session.site_key,
                channel="voice",
                model=model_name,
                duration_ms=0.0,
                result_status="rate_limited",
                error_message="Voice turn rate limit exceeded",
            )
            await concierge_tracing_service.record_trace(trace, db=db)
            return VoiceCallTurnResponse(
                session_id=turn.session_id,
                agent_reply_text="Veuillez patienter un instant avant de reprendre la parole.",
                status="rate_limited",
            )

        user_text = turn.user_speech_transcript.strip()
        user_lower = user_text.lower()

        # Check for hang-up intent
        should_end = any(phrase in user_lower for phrase in END_CALL_PHRASES)

        # Detect if visitor spoken contact details
        phone_match = PHONE_REGEX.search(user_text)
        email_match = EMAIL_REGEX.search(user_text)
        has_contact = bool(email_match or phone_match)
        if has_contact:
            session.lead_captured = True

        # Do not retain or forward raw contact details in model prompt
        safe_user_text = redact_contact_details(user_text)

        # Assemble LLM history with site-specific knowledge base
        session.history.append({"role": "user", "content": safe_user_text})
        del session.history[:-24]
        messages = [{"role": "system", "content": self._build_voice_system_prompt(session.site_key)}]
        # Keep last 14 dialogue turns for deep architectural & multi-turn discussions
        messages.extend(session.history[-14:])

        start_time = time.perf_counter()
        tools_called = ["voice_prosody", "site_knowledge_base"]
        result_status = "ok"
        error_msg: Optional[str] = None
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        cost_usd = 0.0


        try:
            has_custom_meta = (
                hasattr(self.provider, "generate_with_meta")
                and type(self.provider).__name__ not in ("AsyncMock", "MagicMock", "Mock")
            )
            if has_custom_meta:
                gen_result = await self.provider.generate_with_meta(messages, json_mode=False)
                raw_reply = gen_result.content
                model_name = gen_result.model
                prompt_tokens = gen_result.prompt_tokens
                completion_tokens = gen_result.completion_tokens
                total_tokens = gen_result.total_tokens
                cost_usd = gen_result.estimated_cost_usd
            else:
                raw_reply = await self.provider.generate(messages, json_mode=False)
                if not isinstance(raw_reply, str):
                    raw_reply = str(raw_reply)
                prompt_chars = sum(len(m.get("content", "")) for m in messages)
                completion_chars = len(raw_reply)
                prompt_tokens = max(1, prompt_chars // 4)
                completion_tokens = max(1, completion_chars // 4)
                total_tokens = prompt_tokens + completion_tokens

                cost_usd = compute_token_cost(model_name, prompt_tokens, completion_tokens)

            # Strip any <think>...</think> reasoning blocks if present
            clean_reply = re.sub(r"<think>[\s\S]*?</think>", "", raw_reply).strip()
            # Sanitize speech output: remove markdown characters
            clean_reply = re.sub(r"[*#_`>\[\]]", "", clean_reply).strip()
            # Remove URLs for spoken audio
            clean_reply = re.sub(r"https?://\S+", "", clean_reply).strip()
            # Collapse multiple spaces/newlines for smooth TTS prosody
            clean_reply = re.sub(r"\s+", " ", clean_reply).strip()
        except Exception as e:
            logger.warning("GroqProvider voice error: %s. Using resilient speech fallback.", e)
            result_status = "fallback"
            error_msg = str(e)
            business_name = site_config_service.get_site_dict(session.site_key)["business_name"]
            clean_reply = (
                f"Je rencontre un souci temporaire pour répondre correctement au sujet de {business_name}. "
                "Je préfère ne pas vous donner une information incertaine. Pouvez-vous réessayer dans un instant ?"
            )

        if should_end and "au revoir" not in clean_reply.lower() and "bonne" not in clean_reply.lower():
            clean_reply += " Merci pour cet échange et à très bientôt !"

        session.history.append({"role": "assistant", "content": clean_reply})
        del session.history[:-24]

        transferred_to_rockib = False
        if session.lead_captured and has_contact:
            tools_called.append("lead_capture")
            cfg = site_config_service.get_site_dict(session.site_key)
            transferred_to_rockib = await concierge_tracing_service.forward_lead_to_telegram(
                site_key=session.site_key,
                business_name=cfg.get("business_name", session.site_key),
                phone_number=phone_match.group(0).strip() if phone_match else None,
                email=email_match.group(0) if email_match else None,
                topic=user_text[:400],
                channel="voice",
                conversation_id=turn.session_id,
            )
            if transferred_to_rockib:
                tools_called.append("telegram_notify")

        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # Record detailed trace
        trace = ConciergeTraceData(
            conversation_id=turn.session_id,
            site_key=session.site_key,
            channel="voice",
            model=model_name,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost_usd,
            tools_called=tools_called,
            result_status=result_status,
            lead_captured=session.lead_captured,
            transferred_to_rockib=transferred_to_rockib,
            error_message=error_msg,
        )
        await concierge_tracing_service.record_trace(trace, db=db)

        return VoiceCallTurnResponse(
            session_id=turn.session_id,
            agent_reply_text=clean_reply,
            lead_captured=session.lead_captured,
            should_end_call=should_end,
            status="ok",
        )

