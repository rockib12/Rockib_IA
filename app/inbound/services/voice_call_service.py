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
from app.intelligence.services.providers.groq_provider import GroqProvider

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?[0-9]{1,4}[\s-]?)?(\(?[0-9]{2,4}\)?[\s-]?)?[0-9]{3,4}[\s-]?[0-9]{3,4}")

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

    def __init__(self, session_id: str, page_url: str):
        self.session_id = session_id
        self.page_url = page_url
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
        session = VoiceCallSession(session_id=session_id, page_url=request.page_url or "")
        self._sessions[session_id] = session

        greeting = (
            "Bonjour ! Je suis le concierge vocal de Rockib Quenum. "
            "Je vous écoute, de quel projet souhaitez-vous parler ?"
        )
        session.history.append({"role": "assistant", "content": greeting})

        return VoiceCallSessionResponse(
            session_id=session_id,
            status="connected",
            greeting_text=greeting,
            voice_locale="fr-FR",
            max_duration_seconds=300,
        )

    def _build_voice_system_prompt(self) -> str:
        return (
            "Tu es le Concierge VOCAL temps réel de Rockib Quenum (Cotonou, Bénin), inspiré du mode vocal fluide de ChatGPT.\n"
            "DIRECTIVES VOCALES CRITIQUES (CONVERSATION TEMPS RÉEL) :\n"
            "1. Réponds TOUJOURS en 1 à 2 phrases très courtes et percutantes (maximum 35 mots) pour garder un rythme de dialogue ultra-rapide et naturel.\n"
            "2. N'utilise JAMAIS de mise en forme Markdown : aucun astérisque (*), aucun dièse (#), aucune puce (-), aucun lien.\n"
            "3. Parle de façon chaleureuse, directe et humaine, comme au téléphone.\n"
            "4. Si l'interlocuteur souhaite un devis ou travailler avec Rockib, demande-lui simplement son email ou son numéro WhatsApp.\n"
            "5. BASE DE CONNAISSANCES : Rockib est Lead Software Architect & AI Systems Engineer (Rockib AI Engine, vendeur IA WhatsApp MARTISTORE, WaAuto Commercial, Agence IIA). Contact : rockibdev@gmail.com.\n"
            "6. Si l'interlocuteur dit au revoir ou veut raccrocher, salue-le chaleureusement."
        )

    async def handle_voice_turn(
        self,
        turn: VoiceCallTurnRequest,
        client_ip: str = "127.0.0.1",
    ) -> VoiceCallTurnResponse:
        """Processes a speech utterance transcribed from the caller's mic."""
        session = self._sessions.get(turn.session_id)
        if not session:
            # Recreate session if expired
            session = VoiceCallSession(session_id=turn.session_id, page_url="")
            self._sessions[turn.session_id] = session

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
                contact_name="Appelant Vocal Portfolio",
                email=detected_email or "vocal-lead@portfolio.com",
                need=user_text,
                phone=detected_phone,
            )

        # Assemble LLM history
        session.history.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": self._build_voice_system_prompt()}]
        # Keep last 6 dialogue turns for context without overflow
        messages.extend(session.history[-6:])

        try:
            raw_reply = await self.provider.generate(messages, json_mode=False)
            # Sanitize speech output: remove markdown characters
            clean_reply = re.sub(r"[*#_`>\[\]]", "", raw_reply).strip()
            # Remove URLs for spoken audio
            clean_reply = re.sub(r"https?://\S+", "", clean_reply).strip()
        except Exception as e:
            logger.warning("GroqProvider voice error: %s. Using resilient speech fallback.", e)
            clean_reply = (
                "Je vous entends parfaitement. Rockib réalise des systèmes comme le vendeur IA WhatsApp MARTISTORE "
                "et le portail client de l'Agence IIA. Vous pouvez me donner votre email pour qu'il vous recontacte."
            )

        if should_end and "au revoir" not in clean_reply.lower() and "bonne" not in clean_reply.lower():
            clean_reply += " Merci pour cet appel et à très bientôt !"

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
    ) -> None:
        payload = {
            "company_name": "Inbound Portfolio Call / Voice",
            "contact_name": contact_name,
            "email": email,
            "automation_need": f"{need} (Phone: {phone})" if phone else need,
        }
        logger.info("Captured voice call lead: %s", payload)

        agency_leads_url = "http://127.0.0.1:8000/api/leads/"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(agency_leads_url, json=payload)
        except Exception:
            pass
