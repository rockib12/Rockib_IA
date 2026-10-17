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


class PortfolioConciergeService:
    """Orchestrates conversations with visitors on https://rockib-quenum.netlify.app/."""

    def __init__(self, ai_provider: Optional[GroqProvider] = None):
        self.provider = ai_provider or GroqProvider()
        # Cache catalog manifests
        self._skills = {m.identity.id: m for m in get_default_catalogue()}

    def _build_system_prompt(self) -> str:
        ambassador = self._skills.get("portfolio_ambassador")
        qualification = self._skills.get("lead_qualification")

        prompt_lines = [
            "Tu es le Concierge & Assistant Virtuel officiel de Rockib Quenum sur son portfolio (https://rockib-quenum.netlify.app/).",
            "Ton rôle est d'accueillir les visiteurs avec professionnalisme, clarté et précision technique.",
            "",
            "BASE DE CONNAISSANCES OFFICIELLE (ROCKIB QUENUM) :",
            "- Métier : Architecte full-stack & automation IA, basé à Cotonou, Bénin.",
            "- Philosophie : 'En production, pas en démo'. Du code résilient qui tourne chaque nuit pour de vraies entreprises.",
            "- Réalisations Phares :",
            "  * MARTISTORE (martistore.shop) : Vendeur IA WhatsApp + boutique en ligne complète (100+ articles, reconnaissance photo CLIP vision, Meta Cloud API, Celery, PostgreSQL).",
            "  * WaAuto Commercial (waauto-commercial.vercel.app) : Landing d'acquisition, configurateur en 4 écrans, devises dynamiques (FCFA / EUR / USD).",
            "  * Agence IIA : Portail client d'agence avec facturation, paiements FedaPay Mobile Money et Stripe, paywall strict HTTP 402.",
            "  * SaaS multi-boutique : Plateforme multi-tenant en Docker avec double connecteur WhatsApp.",
            "- Stack technique : Python, Flask, Django, Celery, PostgreSQL, Redis, Docker, React, Next.js, Groq, Meta Cloud API.",
            "- Contact : rockibdev@gmail.com, WhatsApp direct, GitHub (rockib12), LinkedIn.",
            "",
            "CONSIGNES CONVERSATIONNELLES :",
            "1. Réponds toujours dans la langue de l'utilisateur (français par défaut).",
            "2. Sois concis, technique et percutant (2 à 4 paragraphes maximum). Évite le jargon creux.",
            "3. Si le visiteur pose des questions sur un devis ou souhaite construire un projet, invite-le à préciser son besoin, son budget et ses coordonnées (email ou WhatsApp).",
            "4. Reste courtois et valorise toujours le travail en production réelle.",
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

        # Call LLM
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": f"Message du visiteur: {request.message}"},
        ]

        try:
            raw_reply = await self.provider.generate(messages, json_mode=False)
            reply_text = raw_reply.strip()
        except Exception as e:
            logger.warning("GroqProvider unavailable for inbound portfolio: %s. Using resilient fallback.", e)
            reply_text = (
                "Bonjour ! Je suis le concierge IA de Rockib Quenum.\n\n"
                "Rockib conçoit et déploie des sites web performants, des automatisations avancées et des agents IA "
                "en production réelle — comme le vendeur IA WhatsApp de MARTISTORE ou le portail client de l'Agence IIA.\n\n"
                "Pour discuter de votre projet ou obtenir une estimation, vous pouvez me laisser votre adresse email "
                "ou contacter Rockib directement par email à rockibdev@gmail.com ou sur WhatsApp !"
            )

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
