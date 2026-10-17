"""Multi-Tenant Site Configuration & Knowledge Base Service for Rockib Concierge SaaS.

Allows each client website (`site_key`) to have its own:
- Visual branding (business_name, subtitle, launcher_label, primary_color, position)
- Voice & conversation defaults (default_voice, welcome_message, voice_greeting, quick_chips, voice_topic_chips)
- Custom Knowledge Base (knowledge_base, assistant_role, pricing_rule, contact_whatsapp, contact_email)
- Client secret token (`client_token`) so each client can customize their own concierge safely.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from pathlib import Path
from typing import Dict, List, Optional

from app.inbound.schemas import (
    ConciergeSiteConfigPublic,
    ConciergeSiteConfigUpsertRequest,
    VoiceTopicChip,
)

logger = logging.getLogger(__name__)

_SAFE_SITE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_DATA_FILE = Path(os.environ.get("CONCIERGE_SITES_PATH", "data/concierge_sites.json"))


def normalize_site_key(raw_key: Optional[str]) -> str:
    """Normalizes a site_key or defaults to 'rockib-portfolio'."""
    if not raw_key:
        return "rockib-portfolio"
    cleaned = re.sub(r"[^a-z0-9_-]", "-", raw_key.strip().lower()).strip("-_")
    if not cleaned or len(cleaned) < 2:
        return "rockib-portfolio"
    return cleaned[:63]


DEFAULT_SITES: Dict[str, dict] = {
    "rockib-portfolio": {
        "site_key": "rockib-portfolio",
        "business_name": "Rockib Quenum · Co-Architecte & Assistant IA",
        "subtitle": "Projets en production · Conception d'Architecture · Vocal Temps Réel",
        "launcher_label": "📞 Concierge & Appel IA",
        "primary_color": "#00F0FF",
        "position": "right",
        "default_voice": "henri",
        "welcome_message": (
            "Bonjour ! Je suis l'Assistant IA et Co-Architecte de Rockib Quenum.\n\n"
            "Je peux vous proposer des idées concrètes d'applications ou d'automatisations IA pour votre activité, "
            "concevoir votre architecture technique, ou vous présenter ses systèmes en production "
            "(Rockib AI Engine, MARTISTORE, WaAuto, Agence IIA).\n\n"
            "Quelle est votre activité ou votre idée de projet ?"
        ),
        "voice_greeting": (
            "Bonjour ! Je suis l'assistant IA de Rockib Quenum. "
            "Je peux vous présenter ses réalisations, vous proposer des idées d'applications ou d'automatisations IA pour votre activité, "
            "et concevoir votre architecture. Dans quel domaine êtes-vous ou quel projet avez-vous en tête ?"
        ),
        "quick_chips": [
            "💡 Propose-moi des idées d'IA pour mon activité",
            "🚀 Découvrir les projets en production de Rockib",
            "🏗️ Concevoir l'architecture de mon projet",
            "🤝 Discuter du tarif avec Rockib",
        ],
        "voice_topic_chips": [
            {
                "label": "💡 Proposer des Idées",
                "prompt": "Propose-moi des idées innovantes de projets IA et d'automatisations rentables que Rockib peut créer pour une entreprise.",
            },
            {
                "label": "🚀 Ses Projets",
                "prompt": "Présente-moi les projets en production de Rockib Quenum.",
            },
            {
                "label": "🏗️ Architecture & Devis",
                "prompt": "Propose-moi une architecture technique moderne et explique comment voir le prix avec Rockib.",
            },
        ],
        "assistant_role": (
            "Assistant IA Vocal et Écrit, Conseiller en Innovation et Co-Architecte Logiciel de Rockib Quenum "
            "(Lead Software Architect & Autonomous AI Systems Engineer basé à Cotonou, Bénin)."
        ),
        "knowledge_base": (
            "PROJETS EN PRODUCTION DE ROCKIB QUENUM :\n"
            "1. Rockib AI Engine : Système d'orchestration multi-agents autonome avec gouvernance déterministe (`DeterministicArbitrator`), "
            "exécution transactionnelle ACID (`ReliableExecutor`), coffre-fort AES-256-GCM, 107 skills scellés SHA-256 et 686 tests automatisés 100% verts.\n"
            "2. MARTISTORE (martistore.shop) : Vendeur IA WhatsApp + boutique e-commerce en production (100+ articles, reconnaissance visuelle par photo "
            "OpenAI CLIP Vision permettant d'identifier un produit depuis une image envoyée sur WhatsApp, Meta Cloud API, Groq, Celery, PostgreSQL).\n"
            "3. WaAuto Commercial (waauto-commercial.vercel.app) : Plateforme SaaS B2B multi-tenant d'automatisation WhatsApp en 4 écrans, "
            "tarification dynamique FCFA / EUR / USD et double connecteur WhatsApp.\n"
            "4. Agence IIA : Portail client et facturation automatisée (Django 5.2, React 19, suivi temps réel par webhooks Git HMAC, "
            "paiements FedaPay Mobile Money & Stripe, barrière HTTP 402 sur les livrables).\n"
            "TECHNOLOGIES MAÎTRISÉES : Python, FastAPI, Django 5.2, Flask, React 19, Next.js, TypeScript, PostgreSQL, Redis, Celery, Groq LLM, "
            "OpenAI CLIP Vision, Whisper, Edge Neural TTS, Docker, Nginx, FedaPay, Stripe."
        ),
        "pricing_rule": (
            "Ne donne JAMAIS de prix chiffré toi-même. Dès que le visiteur parle de prix, de budget ou de devis, "
            "explique que le tarif dépend du périmètre exact et guide-le directement vers Rockib Quenum : "
            "invite-le à donner son numéro WhatsApp ou son email, ou à contacter Rockib au +229 01 46 42 09 22 / rockibdev@gmail.com."
        ),
        "contact_whatsapp": "+229 01 46 42 09 22",
        "contact_email": "rockibdev@gmail.com",
        "client_token": "rockib-master-key",
    },
    "martistore": {
        "site_key": "martistore",
        "business_name": "MARTISTORE · Conseiller Mode & Shopping IA",
        "subtitle": "Boutique en ligne & Commandes WhatsApp 24h/24",
        "launcher_label": "🛍️ Conseiller Mode IA",
        "primary_color": "#00FF9D",
        "position": "right",
        "default_voice": "vivienne",
        "welcome_message": (
            "Bienvenue sur MARTISTORE ! Je suis votre conseillère shopping IA.\n\n"
            "Je peux vous aider à trouver un article, vérifier les tailles disponibles ou enregistrer votre commande.\n\n"
            "Que recherchez-vous aujourd'hui ?"
        ),
        "voice_greeting": (
            "Bienvenue chez MARTISTORE ! Je suis votre conseillère vocale. "
            "Quel style de vêtement, chaussure ou accessoire recherchez-vous aujourd'hui ?"
        ),
        "quick_chips": [
            "👗 Quelles sont les nouveautés en stock ?",
            "📸 Comment chercher un article par photo sur WhatsApp ?",
            "🚚 Quels sont les délais et modes de livraison ?",
            "💳 Comment commander et payer par Mobile Money ?",
        ],
        "voice_topic_chips": [
            {"label": "👗 Nouveautés", "prompt": "Quels sont les articles phares disponibles sur MARTISTORE ?"},
            {"label": "📸 Recherche Photo", "prompt": "Comment fonctionne la recherche par photo sur WhatsApp ?"},
            {"label": "🚚 Livraison", "prompt": "Comment fonctionne la livraison et le paiement ?"},
        ],
        "assistant_role": "Conseillère shopping IA officielle de la boutique MARTISTORE (martistore.shop).",
        "knowledge_base": (
            "MARTISTORE (martistore.shop) est une boutique de mode et d'articles tendances avec plus de 100 références en stock.\n"
            "- Recherche par photo sur WhatsApp : envoyez la photo d'un article et notre IA CLIP Vision retrouve immédiatement le modèle exact.\n"
            "- Livraison rapide à Cotonou et expédition partout.\n"
            "- Paiement sécurisé par Mobile Money (MTN, Moov, Celtiis) ou à la livraison selon les articles."
        ),
        "pricing_rule": (
            "Pour valider une commande ou obtenir une remise sur quantité, invite le client à laisser son numéro WhatsApp "
            "pour recevoir le lien de commande direct."
        ),
        "contact_whatsapp": "+229 01 46 42 09 22",
        "contact_email": "contact@martistore.shop",
        "client_token": "martistore-secret-token",
    },
}


class SiteConfigService:
    """Manages per-site Concierge configurations and knowledge bases."""

    def __init__(self) -> None:
        self._sites: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        self._sites = {k: dict(v) for k, v in DEFAULT_SITES.items()}
        try:
            if _DATA_FILE.exists():
                raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if isinstance(v, dict):
                            self._sites[normalize_site_key(k)] = v
        except Exception as exc:
            logger.warning("Failed to load concierge_sites.json: %s", exc)

    def _save(self) -> None:
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            _DATA_FILE.write_text(
                json.dumps(self._sites, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist concierge_sites.json: %s", exc)

    def get_site_dict(self, site_key: Optional[str]) -> dict:
        key = normalize_site_key(site_key)
        return self._sites.get(key) or self._sites["rockib-portfolio"]

    def get_public_config(self, site_key: Optional[str]) -> ConciergeSiteConfigPublic:
        data = self.get_site_dict(site_key)
        return ConciergeSiteConfigPublic(
            site_key=data["site_key"],
            business_name=data["business_name"],
            subtitle=data.get("subtitle") or "",
            launcher_label=data.get("launcher_label") or "📞 Concierge & Appel IA",
            primary_color=data.get("primary_color") or "#00F0FF",
            position=data.get("position") or "right",
            default_voice=data.get("default_voice") or "henri",
            welcome_message=data.get("welcome_message") or "",
            voice_greeting=data.get("voice_greeting") or "",
            quick_chips=list(data.get("quick_chips") or []),
            voice_topic_chips=[
                VoiceTopicChip(**c) if isinstance(c, dict) else c
                for c in (data.get("voice_topic_chips") or [])
            ],
            assistant_role=data.get("assistant_role") or "",
            knowledge_base=data.get("knowledge_base") or "",
            pricing_rule=data.get("pricing_rule") or "",
            contact_whatsapp=data.get("contact_whatsapp") or "",
            contact_email=data.get("contact_email") or "",
        )

    def list_public_configs(self) -> List[ConciergeSiteConfigPublic]:
        return [self.get_public_config(k) for k in sorted(self._sites.keys())]

    def upsert_site_config(
        self,
        site_key: str,
        payload: ConciergeSiteConfigUpsertRequest,
    ) -> tuple[ConciergeSiteConfigPublic, str]:
        """Creates or updates a client site configuration.

        If the site already exists, requires matching `client_token` (or master key).
        Returns `(public_config, client_token)`.
        """
        key = normalize_site_key(site_key)
        existing = self._sites.get(key)
        master_key = os.environ.get("ROCKIB_MASTER_CONCIERGE_KEY", "rockib-master-key")

        if existing:
            expected_token = existing.get("client_token") or master_key
            provided_token = (payload.client_token or "").strip()
            if provided_token not in (expected_token, master_key):
                raise PermissionError(
                    "Clé d'édition client (client_token) invalide pour ce site_key."
                )
            token_to_save = expected_token
        else:
            token_to_save = (payload.client_token or "").strip() or f"tok_{secrets.token_hex(8)}"

        record = {
            "site_key": key,
            "business_name": payload.business_name.strip(),
            "subtitle": (payload.subtitle or "").strip(),
            "launcher_label": (payload.launcher_label or "📞 Concierge & Appel IA").strip(),
            "primary_color": (payload.primary_color or "#00F0FF").strip(),
            "position": "left" if (payload.position or "").lower() == "left" else "right",
            "default_voice": (payload.default_voice or "henri").lower().strip(),
            "welcome_message": payload.welcome_message.strip(),
            "voice_greeting": payload.voice_greeting.strip(),
            "quick_chips": [c.strip() for c in payload.quick_chips if c.strip()][:6],
            "voice_topic_chips": [
                {"label": c.label.strip(), "prompt": c.prompt.strip()}
                for c in payload.voice_topic_chips
                if c.label.strip() and c.prompt.strip()
            ][:4],
            "assistant_role": payload.assistant_role.strip(),
            "knowledge_base": payload.knowledge_base.strip(),
            "pricing_rule": payload.pricing_rule.strip(),
            "contact_whatsapp": (payload.contact_whatsapp or "").strip(),
            "contact_email": (payload.contact_email or "").strip(),
            "client_token": token_to_save,
        }
        self._sites[key] = record
        self._save()
        return self.get_public_config(key), token_to_save

    def build_chat_system_prompt(self, site_key: Optional[str]) -> str:
        """Builds a dynamic chat system prompt tailored to the target client site."""
        cfg = self.get_site_dict(site_key)
        if cfg["site_key"] == "rockib-portfolio":
            return (
                f"Tu es {cfg['assistant_role']} sur son site officiel.\n\n"
                "TON RÔLE ET TON COMPORTEMENT (TRÈS IMPORTANT) :\n"
                "1. PROPOSER DES IDÉES DE PROJETS, D'AUTOMATISATIONS IA ET D'ARCHITECTURES :\n"
                "  * Sois force de proposition ! Quand un visiteur te parle de son activité, propose-lui proactivement des idées concrètes et rentables "
                "(vendeur IA WhatsApp avec reconnaissance photo, agent IA autonome 24h/24, plateforme web/SaaS ou portail client avec Mobile Money/Stripe).\n"
                "  * Lorsqu'il a une idée, enrichis-la et propose une architecture technique claire.\n\n"
                f"2. BASE DE CONNAISSANCES OFFICIELLE :\n{cfg['knowledge_base']}\n\n"
                f"3. RÈGLE SUR LES PRIX ET DEVIS :\n{cfg['pricing_rule']}\n"
                f"Contacts officiels : WhatsApp {cfg.get('contact_whatsapp', '')} | Email {cfg.get('contact_email', '')}."
            )

        return (
            f"Tu es l'Assistant IA officiel de « {cfg['business_name']} ».\n"
            f"Ton rôle : {cfg['assistant_role']}\n\n"
            f"BASE DE CONNAISSANCES DE L'ENTREPRISE ({cfg['business_name']}) :\n"
            f"{cfg['knowledge_base']}\n\n"
            "DIRECTIVES CONVERSATIONNELLES :\n"
            "1. Réponds avec chaleur, professionnalisme et précision en t'appuyant strictement sur la base de connaissances ci-dessus.\n"
            "2. Sois proactif : conseille le visiteur, propose les services/produits adaptés à son besoin.\n"
            f"3. RÈGLE TARIFS / CONTACT : {cfg['pricing_rule']}\n"
            f"Coordonnées directes de l'entreprise : WhatsApp {cfg.get('contact_whatsapp', '')} | Email {cfg.get('contact_email', '')}."
        )

    def build_voice_system_prompt(self, site_key: Optional[str]) -> str:
        """Builds a dynamic spoken voice system prompt tailored to the target client site."""
        cfg = self.get_site_dict(site_key)
        return (
            f"Tu es l'Assistant IA VOCAL temps réel de « {cfg['business_name']} » ({cfg['assistant_role']}).\n\n"
            f"BASE DE CONNAISSANCES DE L'ENTREPRISE :\n{cfg['knowledge_base']}\n\n"
            "CONSIGNES D'EXPRESSION VOCALE (TRÈS IMPORTANT) :\n"
            "1. Sois force de proposition : propose des idées concrètes, des solutions ou des conseils adaptés à l'interlocuteur.\n"
            f"2. RÈGLE SUR LES PRIX ET DEVIS : {cfg['pricing_rule']}\n"
            "3. Parle de façon naturelle, dynamique et chaleureuse en 3 à 5 phrases fluides, comme dans le mode vocal de ChatGPT.\n"
            "4. N'utilise JAMAIS de symboles Markdown (aucun astérisque *, aucun dièse #, aucune puce -) car ta réponse est lue à haute voix."
        )


site_config_service = SiteConfigService()
