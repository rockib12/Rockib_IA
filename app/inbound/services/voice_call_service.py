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
            "Je vous écoute : parlez-moi de votre projet de site, d'automatisation ou de boutique WhatsApp !"
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
            "Tu es le Concierge VOCAL officiel de Rockib Quenum (Cotonou, Bénin) en appel direct avec un visiteur.\n"
            "DIRECTIVES VOCALES CRITIQUES (TEXT-TO-SPEECH) :\n"
            "1. Tes réponses vont être lues à voix haute par un moteur de synthèse vocale. Écris dans un style parlé naturel, vivant et fluide.\n"
            "2. N'utilise JAMAIS de mise en forme Markdown : aucun astérisque (*), aucun dièse (#), aucune puce (-), aucun lien markdown.\n"
            "3. Fais des phrases courtes (2 à 3 phrases maximum par réponse) pour permettre un échange dynamique.\n"
            "4. Si l'interlocuteur souhaite un devis ou une estimation, demande-lui son adresse email ou son numéro de téléphone.\n"
            "5. BASE DE CONNAISSANCES : Rockib conçoit des systèmes en production réelle (le vendeur IA WhatsApp MARTISTORE, l'Agence IIA, WaAuto Commercial). Contact : rockibdev@gmail.com.\n"
            "6. Si l'interlocuteur dit au revoir ou veut raccrocher, salue-le chaleureusement et souhaite-lui une excellente journée."
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
