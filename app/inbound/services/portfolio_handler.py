"""Service handling inbound portfolio inquiries and lead capture.

Features:
- IP Sliding-window rate limiting.
- Conversational concierge backed by GroqProvider & portfolio_ambassador skill.
- Lead capture and optional dispatch to Agence IIA (POST /api/leads/).
- Resilient offline fallback.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from collections import defaultdict, deque
from typing import Optional

import httpx

from app.inbound.schemas import PortfolioInboundMessageRequest, PortfolioInboundResponse
from app.inbound.services.site_config_service import site_config_service
from app.intelligence.services.providers.groq_provider import GroqProvider
from app.skills.catalog import get_default_catalogue

logger = logging.getLogger(__name__)

# In-memory sliding window rate limiter: IP -> deque of timestamps
_RATE_LIMIT_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 20
_MAX_TRACKED_IPS = 2000
_ip_request_history: dict[str, deque[float]] = defaultdict(deque)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}(?:[\s.-]?\d{2,4})?")


def is_rate_limited(client_ip: str) -> bool:
    """Returns True if the IP has exceeded allowed requests in the last window."""
    now = time.time()

    # Bound total tracked IPs to prevent memory exhaustion on spoofed IP floods
    if client_ip not in _ip_request_history and len(_ip_request_history) >= _MAX_TRACKED_IPS:
        stale_ips = [
            ip for ip, q in _ip_request_history.items()
            if not q or (now - q[-1] > _RATE_LIMIT_WINDOW_SECONDS)
        ]
        for ip in stale_ips:
            _ip_request_history.pop(ip, None)
        while len(_ip_request_history) >= _MAX_TRACKED_IPS:
            oldest_ip = next(iter(_ip_request_history))
            _ip_request_history.pop(oldest_ip, None)

    history = _ip_request_history[client_ip]

    # Evict timestamps older than window
    while history and now - history[0] > _RATE_LIMIT_WINDOW_SECONDS:
        history.popleft()

    if len(history) >= _MAX_REQUESTS_PER_WINDOW:
        return True

    history.append(now)
    return False


_CONVERSATION_History_MAX_SESSIONS = 1000
_conversation_store: dict[tuple[str, str], list[dict[str, str]]] = {}


class PortfolioConciergeService:
    """Orchestrates conversations with visitors on https://rockib-quenum.netlify.app/."""

    def __init__(self, ai_provider: Optional[GroqProvider] = None):
        self.provider = ai_provider or GroqProvider()
        # Cache catalog manifests
        self._skills = {m.identity.id: m for m in get_default_catalogue()}

    def _build_system_prompt(self, site_key: str = "rockib-portfolio") -> str:
        return site_config_service.build_chat_system_prompt(site_key)

    async def handle_message(
        self,
        request: PortfolioInboundMessageRequest,
        client_ip: str = "127.0.0.1",
    ) -> PortfolioInboundResponse:
        """Processes a visitor message and returns a tailored AI response."""
        conversation_id = request.conversation_id or str(uuid.uuid4())
        site_key = request.site_key or "rockib-portfolio"

        # Check rate limit
        if is_rate_limited(client_ip):
            return PortfolioInboundResponse(
                reply="Désolé, vous avez envoyé trop de messages en peu de temps. Veuillez patienter une minute avant de continuer la discussion.",
                conversation_id=conversation_id,
                status="rate_limited",
            )

        # Detect email/phone from explicit fields or message text
        detected_email = request.contact_email or None
        detected_phone = request.contact_phone or None

        if not detected_email:
            email_match = EMAIL_REGEX.search(request.message)
            if email_match:
                detected_email = email_match.group(0)

        if not detected_phone:
            phone_match = PHONE_REGEX.search(request.message)
            if phone_match:
                cleaned_digits = re.sub(r"[^\d]", "", phone_match.group(0))
                if len(cleaned_digits) >= 8:
                    detected_phone = phone_match.group(0).strip()

        lead_captured = bool(detected_email or detected_phone)

        # Dispatch lead to Agence IIA and notify Rockib on Telegram
        if lead_captured:
            await self._dispatch_lead_to_agency(
                contact_name=request.sender_name or f"Visiteur ({site_key})",
                email=detected_email or "non-fourni@portfolio.lead",
                need=request.message,
                phone=detected_phone,
                site_key=site_key,
            )

        # Maintain multi-turn conversation history
        conversation_key = (site_key, conversation_id)
        if conversation_key not in _conversation_store and len(_conversation_store) >= _CONVERSATION_History_MAX_SESSIONS:
            _conversation_store.pop(next(iter(_conversation_store)), None)
        history = _conversation_store.setdefault(conversation_key, [])
        history.append({"role": "user", "content": request.message})
        del history[:-24]

        # Call LLM with conversation history and site-specific knowledge base
        messages = [{"role": "system", "content": self._build_system_prompt(site_key)}]
        messages.extend(history[-12:])

        try:
            raw_reply = await self.provider.generate(messages, json_mode=False)
            reply_text = re.sub(r"<think>[\s\S]*?</think>", "", raw_reply).strip()
        except Exception as e:
            logger.warning("GroqProvider unavailable for inbound portfolio: %s. Using resilient fallback.", e)
            business_name = site_config_service.get_site_dict(site_key)["business_name"]
            reply_text = (
                f"Bonjour, je suis l'assistant de {business_name}. Je rencontre un souci temporaire et je ne veux pas "
                "vous donner une information incertaine. Pouvez-vous reformuler votre demande dans un instant, ou contacter directement l'entreprise ?"
            )

        history.append({"role": "assistant", "content": reply_text})
        del history[:-24]

        # If lead was captured, append reassurance
        if lead_captured and detected_email and detected_email not in reply_text:
            reply_text += f"\n\n*(Vos coordonnées {detected_email} ont bien été transmises à Rockib. Il vous recontactera très rapidement !)*"

        return PortfolioInboundResponse(
            reply=reply_text,
            conversation_id=conversation_id,
            lead_captured=lead_captured,
            status="ok",
        )

    async def _dispatch_lead_to_agency(
        self,
        contact_name: str,
        email: str,
        need: str,
        phone: Optional[str] = None,
        site_key: str = "rockib-portfolio",
    ) -> None:
        """Asynchronously dispatches lead to IIA Agency API and sends a high-priority alert to Rockib via Telegram."""
        payload = {
            "company_name": f"Lead Inbound ({site_key})",
            "contact_name": contact_name,
            "email": email,
            "automation_need": f"{need} (Phone: {phone})" if phone else need,
        }
        logger.info("Captured qualified lead for concierge site %s (email=%s, phone=%s)", site_key, bool(email), bool(phone))

        # 1. Envoi prioritaire de l'alerte sur Telegram directement à Rockib
        from app.telegram.services.telegram_service import telegram_service
        from app.inbound.services.site_config_service import site_config_service
        site_cfg = site_config_service.get_site_dict(site_key)
        client_biz = site_cfg.get("business_name", site_key)
        client_wa = site_cfg.get("contact_whatsapp", "")
        client_mail = site_cfg.get("contact_email", "")

        if telegram_service.is_configured():
            try:
                tg_msg = (
                    "🔔 *NOUVEAU CONTACT CLIENT DÉTECTÉ SUR LE CONCIERGE IA* 🚀\n\n"
                    f"🏢 *Entreprise / Site* : `{client_biz}` (`{site_key}`)\n"
                    f"👤 *Nom du Prospect* : `{contact_name}`\n"
                    f"📞 *Téléphone / WhatsApp* : `{phone or 'Non spécifié'}`\n"
                    f"📧 *Email* : `{email}`\n"
                    + (f"📲 *Contact Client WhatsApp* : `{client_wa}`\n" if client_wa else "")
                    + (f"📩 *Contact Client Email* : `{client_mail}`\n" if client_mail else "")
                    + f"\n📝 *Besoin / Message exprimé* :\n_{need}_\n\n"
                    "👉 *Action recommandée* : Effectuer le rappel ou transférer au client !"
                )
                await telegram_service.send_message(
                    chat_id=telegram_service.admin_chat_id,
                    text=tg_msg,
                    parse_mode="Markdown",
                )
                logger.info("Telegram notification sent to Rockib for new lead from %s on %s", contact_name, site_key)
            except Exception as tg_err:
                logger.warning("Failed to dispatch lead alert to Telegram: %s", tg_err)

        # 2. Attempt forwarding to IIA backend if reachable
        agency_leads_url = "http://127.0.0.1:8000/api/leads/"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(agency_leads_url, json=payload)
                logger.info("Successfully posted lead to Agence IIA at %s", agency_leads_url)
        except Exception as exc:
            logger.debug("Agence IIA local endpoint not responding (%s), lead safely logged in Rockib AI.", exc)
