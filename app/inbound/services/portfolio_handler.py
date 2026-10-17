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
from app.intelligence.services.providers.groq_provider import GroqProvider
from app.skills.catalog import get_default_catalogue

logger = logging.getLogger(__name__)

# In-memory sliding window rate limiter: IP -> deque of timestamps
_RATE_LIMIT_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 20
_MAX_TRACKED_IPS = 2000
_ip_request_history: dict[str, deque[float]] = defaultdict(deque)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?[0-9]{1,4}[\s-]?)?(\(?[0-9]{2,4}\)?[\s-]?)?[0-9]{3,4}[\s-]?[0-9]{3,4}")


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
_conversation_store: dict[str, list[dict[str, str]]] = {}


class PortfolioConciergeService:
    """Orchestrates conversations with visitors on https://rockib-quenum.netlify.app/."""

    def __init__(self, ai_provider: Optional[GroqProvider] = None):
        self.provider = ai_provider or GroqProvider()
        # Cache catalog manifests
        self._skills = {m.identity.id: m for m in get_default_catalogue()}

    def _build_system_prompt(self) -> str:
        prompt_lines = [
            "Tu es l'Assistant IA, Conseiller en Innovation et Co-Architecte de Rockib Quenum (Lead Software Architect & Autonomous AI Systems Engineer basé à Cotonou, Bénin) sur son portfolio (https://rockib-quenum.netlify.app/).",
            "",
            "TON RÔLE ET TON COMPORTEMENT (TRÈS IMPORTANT) :",
            "1. PROPOSER DES IDÉES DE PROJETS, D'AUTOMATISATIONS IA ET D'ARCHITECTURES :",
            "  * Sois force de proposition ! Quand un visiteur te parle de son activité (boutique, entreprise, service, startup) ou cherche ce qu'il pourrait automatiser, propose-lui proactivement des idées concrètes et à fort impact :",
            "    - Un vendeur IA sur WhatsApp capable de reconnaître les produits par photo et de prendre les commandes 24h/24,",
            "    - Un agent IA autonome qui qualifie ses prospects, répond aux clients et automatise ses tâches répétitives,",
            "    - Une plateforme web ou SaaS sur mesure avec tableau de bord temps réel et encaissement Mobile Money / Carte bancaire.",
            "  * Lorsqu'il a une idée de projet, enrichis-la avec des fonctionnalités pertinentes et propose-lui une architecture technique claire (React 19 / Next.js, FastAPI / Django 5.2, PostgreSQL, Redis, Celery, IA Groq / Vision CLIP, Docker).",
            "",
            "2. ILLUSTRER AVEC LES PROJETS EN PRODUCTION DE ROCKIB QUENUM :",
            "  * Rockib AI Engine : Moteur d'orchestration multi-agents autonome avec gouvernance déterministe (`DeterministicArbitrator`), exécution transactionnelle ACID (`ReliableExecutor`), coffre-fort AES-256-GCM et 107 skills scellés SHA-256.",
            "  * MARTISTORE (martistore.shop) : Vendeur IA WhatsApp + boutique en ligne (100+ articles, reconnaissance photo OpenAI CLIP Vision, Meta Cloud API, Groq, Celery, PostgreSQL).",
            "  * WaAuto Commercial (waauto-commercial.vercel.app) : Plateforme SaaS B2B multi-tenant d'automatisation WhatsApp en 4 écrans.",
            "  * Agence IIA : Portail client et facturation automatisée (Django 5.2, React 19, suivi temps réel par webhooks Git HMAC, paiements FedaPay Mobile Money & Stripe, protection HTTP 402 des livrables).",
            "",
            "3. RÈGLE STRICTE SUR LES PRIX, TARIFS ET DEVIS — TOUJOURS GUIDER VERS ROCKIB :",
            "  * Ne donne JAMAIS de prix, de tarif chiffré ou d'estimation financière toi-même.",
            "  * Dès que le visiteur pose une question sur le prix, le coût, le budget ou un devis (ou dès qu'une des idées proposées l'intéresse), explique que chaque chiffrage est ajusté sur mesure par Rockib et guide-le directement vers Rockib Quenum :",
            "    - Invite-le à laisser son numéro WhatsApp ou son adresse email directement dans la conversation pour que Rockib le recontacte personnellement,",
            "    - Ou oriente-le vers l'onglet « 📲 Rappel » du widget ou l'adresse rockibdev@gmail.com.",
        ]
        return "\n".join(prompt_lines)

    async def handle_message(
        self,
        request: PortfolioInboundMessageRequest,
        client_ip: str = "127.0.0.1",
    ) -> PortfolioInboundResponse:
        """Processes a visitor message and returns a tailored AI response."""
        conversation_id = request.conversation_id or str(uuid.uuid4())

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

        lead_captured = bool(detected_email or detected_phone)

        # Dispatch lead to Agence IIA if captured
        if lead_captured:
            await self._dispatch_lead_to_agency(
                contact_name=request.sender_name or "Visiteur Portfolio",
                email=detected_email or "non-fourni@portfolio.lead",
                need=request.message,
                phone=detected_phone,
            )

        # Maintain multi-turn conversation history
        if conversation_id not in _conversation_store and len(_conversation_store) >= _CONVERSATION_History_MAX_SESSIONS:
            oldest_cid = next(iter(_conversation_store))
            _conversation_store.pop(oldest_cid, None)
        history = _conversation_store.setdefault(conversation_id, [])
        history.append({"role": "user", "content": request.message})

        # Call LLM with conversation history
        messages = [{"role": "system", "content": self._build_system_prompt()}]
        messages.extend(history[-12:])

        try:
            raw_reply = await self.provider.generate(messages, json_mode=False)
            reply_text = re.sub(r"<think>[\s\S]*?</think>", "", raw_reply).strip()
        except Exception as e:
            logger.warning("GroqProvider unavailable for inbound portfolio: %s. Using resilient fallback.", e)
            reply_text = (
                "Bonjour ! Je suis l'assistant IA et co-architecte de Rockib Quenum.\n\n"
                "Rockib conçoit et déploie des architectures distribuées, des automatisations avancées et des agents IA "
                "en production réelle — comme le moteur d'arbitrage multi-agents Rockib AI, le vendeur IA WhatsApp de MARTISTORE "
                "(avec vision CLIP), WaAuto Commercial ou le portail client de l'Agence IIA.\n\n"
                "Décrivez-moi votre projet pour que je vous propose une architecture technique complète, ou laissez-moi "
                "votre adresse email (ou contactez rockibdev@gmail.com) !"
            )

        history.append({"role": "assistant", "content": reply_text})

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
    ) -> None:
        """Asynchronously dispatches lead to IIA Agency API (POST /api/leads/)."""
        payload = {
            "company_name": "Lead Inbound Portfolio",
            "contact_name": contact_name,
            "email": email,
            "automation_need": f"{need} (Phone: {phone})" if phone else need,
        }
        logger.info("Captured qualified lead for Agence IIA: %s", payload)

        # Attempt forwarding to IIA backend if reachable
        agency_leads_url = "http://127.0.0.1:8000/api/leads/"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(agency_leads_url, json=payload)
                logger.info("Successfully posted lead to Agence IIA at %s", agency_leads_url)
        except Exception as exc:
            logger.debug("Agence IIA local endpoint not responding (%s), lead safely logged in Rockib AI.", exc)
