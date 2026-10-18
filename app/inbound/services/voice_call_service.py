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

import httpx

from app.inbound.schemas import (
    CallMeBackRequest,
    CallMeBackResponse,
    VoiceCallSessionRequest,
    VoiceCallSessionResponse,
    VoiceCallTurnRequest,
    VoiceCallTurnResponse,
)
from app.inbound.services.portfolio_handler import is_rate_limited
from app.inbound.services.site_config_service import site_config_service
from app.intelligence.services.providers.groq_provider import GroqProvider

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}(?:[\s.-]?\d{2,4})?")

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

    def __init__(self, session_id: str, page_url: str, site_key: str = "rockib-portfolio"):
        self.session_id = session_id
        self.page_url = page_url
        self.site_key = site_key or "rockib-portfolio"
        self.created_at = time.time()
        self.history: List[dict[str, str]] = []
        self.lead_captured = False


_SESSION_TTL_SECONDS = 900
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
        communicate = edge_tts.Communicate(text=clean_text, voice=voice_id, rate="+4%")
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

    def start_call_session(self, request: VoiceCallSessionRequest) -> VoiceCallSessionResponse:
        """Initializes a new live voice call session."""
        self._prune_expired_sessions()
        session_id = str(uuid.uuid4())
        site_key = request.site_key or "rockib-portfolio"
        session = VoiceCallSession(session_id=session_id, page_url=request.page_url or "", site_key=site_key)
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
    ) -> VoiceCallTurnResponse:
        """Processes a speech utterance transcribed from the caller's mic."""
        req_site_key = turn.site_key or "rockib-portfolio"
        session = self._sessions.get(turn.session_id)
        if not session:
            # Recreate session if expired
            session = VoiceCallSession(session_id=turn.session_id, page_url="", site_key=req_site_key)
            self._sessions[turn.session_id] = session
        elif turn.site_key and turn.site_key != "rockib-portfolio":
            session.site_key = turn.site_key

        if is_rate_limited(client_ip):
            return VoiceCallTurnResponse(
                session_id=turn.session_id,
                agent_reply_text="Veuillez patienter un instant avant de reprendre la parole.",
                status="rate_limited",
            )

        user_text = turn.user_speech_transcript.strip()
        user_lower = user_text.lower()

        # Check for hang-up intent
        should_end = any(phrase in user_lower for phrase in END_CALL_PHRASES)

        # Detect email or phone in spoken text
        detected_email = None
        email_match = EMAIL_REGEX.search(user_text)
        if email_match:
            detected_email = email_match.group(0)

        detected_phone = None
        phone_match = PHONE_REGEX.search(user_text)
        if phone_match and len(phone_match.group(0).replace(" ", "").replace("-", "")) >= 8:
            detected_phone = phone_match.group(0)

        if detected_email or detected_phone:
            session.lead_captured = True
            await self._dispatch_lead(
                contact_name=f"Appelant Vocal ({session.site_key})",
                email=detected_email or "vocal-lead@portfolio.com",
                need=user_text,
                phone=detected_phone,
                site_key=session.site_key,
            )

        # Assemble LLM history with site-specific knowledge base
        session.history.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": self._build_voice_system_prompt(session.site_key)}]
        # Keep last 14 dialogue turns for deep architectural & multi-turn discussions
        messages.extend(session.history[-14:])

        try:
            raw_reply = await self.provider.generate(messages, json_mode=False)
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
            clean_reply = (
                "Je vous entends parfaitement. Rockib conçoit des architectures complètes en production comme le moteur multi-agents Rockib AI, "
                "le vendeur IA WhatsApp MARTISTORE avec reconnaissance visuelle CLIP, WaAuto Commercial et le portail de l'Agence IIA. "
                "Décrivez-moi votre besoin technique et je vous propose immédiatement une architecture adaptée."
            )

        if should_end and "au revoir" not in clean_reply.lower() and "bonne" not in clean_reply.lower():
            clean_reply += " Merci pour cet échange et à très bientôt !"

        session.history.append({"role": "assistant", "content": clean_reply})

        return VoiceCallTurnResponse(
            session_id=turn.session_id,
            agent_reply_text=clean_reply,
            lead_captured=session.lead_captured,
            should_end_call=should_end,
            status="ok",
        )

    async def schedule_callback(self, request: CallMeBackRequest) -> CallMeBackResponse:
        """Schedules a phone or WhatsApp callback for the visitor."""
        callback_id = str(uuid.uuid4())
        channel_label = "WhatsApp" if request.channel.lower() == "whatsapp" else "Téléphone"

        lead_need = (
            f"DEMANDE DE RAPPEL ({channel_label.upper()}) : "
            f"Créneau: {request.preferred_time} | Sujet: {request.topic}"
        )

        await self._dispatch_lead(
            contact_name=request.contact_name or "Demande de Rappel Vocal",
            email=f"{request.phone_number.replace('+', '').replace(' ', '')}@call.lead",
            need=lead_need,
            phone=request.phone_number,
            site_key=request.site_key or "rockib-portfolio",
        )

        message = (
            f"Votre demande d'appel {channel_label} au {request.phone_number} a bien été enregistrée. "
            f"Rockib ou un agent de l'équipe vous contactera sous peu !"
        )

        return CallMeBackResponse(
            callback_id=callback_id,
            status="scheduled",
            channel=request.channel,
            phone_number=request.phone_number,
            message=message,
            estimated_wait_minutes=5 if request.preferred_time == "immediate" else 30,
        )

    async def _dispatch_lead(
        self,
        contact_name: str,
        email: str,
        need: str,
        phone: Optional[str] = None,
        site_key: str = "rockib-portfolio",
    ) -> None:
        payload = {
            "company_name": f"Inbound Voice / Call ({site_key})",
            "contact_name": contact_name,
            "email": email,
            "automation_need": f"{need} (Phone: {phone})" if phone else need,
        }
        logger.info("Captured voice call lead: %s", payload)

        # 1. Alerte prioritaire immédiate sur Telegram pour Rockib
        from app.telegram.services.telegram_service import telegram_service
        from app.inbound.services.site_config_service import site_config_service
        site_cfg = site_config_service.get_site_dict(site_key)
        client_biz = site_cfg.get("business_name", site_key)
        client_wa = site_cfg.get("contact_whatsapp", "")
        client_mail = site_cfg.get("contact_email", "")

        if telegram_service.is_configured():
            try:
                tg_msg = (
                    "🎙️ *DEMANDE DE RAPPEL / LEAD VOCAL DU CONCIERGE IA* 📞\n\n"
                    f"🏢 *Entreprise / Site* : `{client_biz}` (`{site_key}`)\n"
                    f"👤 *Nom / Contact* : `{contact_name}`\n"
                    f"📞 *Numéro de rappel* : `{phone or 'Non spécifié'}`\n"
                    f"📧 *Email* : `{email}`\n"
                    + (f"📲 *Contact Client WhatsApp* : `{client_wa}`\n" if client_wa else "")
                    + (f"📩 *Contact Client Email* : `{client_mail}`\n" if client_mail else "")
                    + f"\n📝 *Détail / Contexte de l'appel* :\n_{need}_\n\n"
                    "⚡ *Action requise* : Contacter le prospect au plus vite ou transférer au client !"
                )
                await telegram_service.send_message(
                    chat_id=telegram_service.admin_chat_id,
                    text=tg_msg,
                    parse_mode="Markdown",
                )
                logger.info("Telegram voice lead alert sent to Rockib for %s on %s", phone or contact_name, site_key)
            except Exception as tg_err:
                logger.warning("Failed to dispatch voice lead to Telegram: %s", tg_err)

        # 2. Transmission vers Agence IIA
        agency_leads_url = "http://127.0.0.1:8000/api/leads/"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(agency_leads_url, json=payload)
        except Exception:
            pass
