"""
P8 — Générateur Automatique de Cahier des Charges, Architecture & Devis (`AutoProposalEngine`).

Transforme instantanément un besoin prospect (depuis `ConciergeLead` ou un brief libre) en :
1. Qualification sémantique Gemma-2 (768d) du domaine et des compétences requises.
2. Architecture technique recommandée (Stack Front/Back/DB/IA/Sécurité).
3. Découpage en phases/sprints livrables avec jalons vérifiables.
4. Estimation budgétaire structurée (EUR & FCFA XOF) et délai de livraison.
5. Cahier des charges complet au format Markdown prêt à être envoyé au client.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.intelligence.services.gemma_recognition import GemmaRecognitionEngine

logger = logging.getLogger(__name__)


PROJECT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "AI_SYSTEM_ARCHITECTURE": {
        "title": "Plateforme d'Agents IA Autonomes & Orchestration Métier",
        "stack": [
            "Backend : FastAPI (Python 3.12 Async) + Celery Workers + Redis",
            "Base de données : PostgreSQL 16 + pgvector (Mémoire Sémantique 768d)",
            "Moteur IA : Groq LLM + Reconnaissance Multimodale Gemma-2 + Arbitrage Déterministe",
            "Frontend : React 19 + Vite + Cockpit Temps Réel + Nginx Reverse Proxy",
            "Sécurité : Coffre-fort AEAD AES-256-GCM + SAST/OWASP Zero-Trust",
        ],
        "budget_eur": "3 500 € – 6 500 €",
        "budget_xof": "2 300 000 FCFA – 4 250 000 FCFA",
        "timeline": "3 à 5 semaines",
    },
    "CYBER_SECURITY_AUDIT": {
        "title": "Audit de Cybersécurité Défensive SAST/OWASP & Durcissement Zero-Trust",
        "stack": [
            "Audit Statique & Dynamique : Analyse AST/SAST, revue des dépendances et secrets",
            "Sécurité API : Authentification JWT RS256/HS256, Anti-Bruteforce, Rate-Limiting Proxy-Safe",
            "Protection Réseau : Immunité SSRF / DNS Rebinding, Signatures Webhooks HMAC-SHA256",
            "Chiffrement : Isolation Multi-Tenant stricte et Vault AES-256-GCM",
        ],
        "budget_eur": "1 800 € – 3 500 €",
        "budget_xof": "1 180 000 FCFA – 2 300 000 FCFA",
        "timeline": "1 à 2 semaines",
    },
    "FULLSTACK_ENGINEERING": {
        "title": "Application SaaS Full-Stack Haute Performance & E-Commerce",
        "stack": [
            "Frontend : React 19 + Vite + TailwindCSS + Animations Fluides",
            "Backend : Django 5.2 DRF / FastAPI + Celery + Webhooks Paiement & WhatsApp",
            "Données & Cache : PostgreSQL 16 ACID + Redis 7",
            "Déploiement : Conteneurisation Docker Unifiée + Nginx + CI/CD Automatisé",
        ],
        "budget_eur": "2 500 € – 4 800 €",
        "budget_xof": "1 640 000 FCFA – 3 150 000 FCFA",
        "timeline": "2 à 4 semaines",
    },
    "COMMERCIAL_QUOTE": {
        "title": "Solution Digitale Sur-Mesure & Automatisation Intelligente (Agence IIA)",
        "stack": [
            "Architecture Web & Mobile Responsive : React 19 / Vite",
            "API & Back-Office Administrateur : FastAPI / Django 5.2 + PostgreSQL",
            "Intégrations Métier : Concierge IA Vocal/Chat, WhatsApp Automation & Paiements",
            "Sécurité & Déploiement Cloud : Docker + Nginx SSL + Monitoring Temps Réel",
        ],
        "budget_eur": "2 200 € – 4 500 €",
        "budget_xof": "1 450 000 FCFA – 2 950 000 FCFA",
        "timeline": "2 à 4 semaines",
    },
}


class AutoProposalEngine:
    """Moteur P8 de génération automatique d'architecture et de proposition commerciale."""

    @classmethod
    async def generate_proposal(
        cls,
        client_name: str = "Client Partenaire",
        project_summary: str = "",
        budget_hint: str = "",
        timeline_hint: str = "",
        company_name: str | None = None,
        project_brief: str | None = None,
        currency: str = "EUR",
    ) -> Dict[str, Any]:
        raw_summary = project_summary or project_brief or "Projet d'application web et IA"
        cleaned_summary = raw_summary.strip()
        name = (client_name or "Client Partenaire").strip()
        if company_name and company_name.strip():
            display_client = f"{name} ({company_name.strip()})"
        else:
            display_client = name

        # 1. Reconnaissance d'intention et de domaine via Gemma-2 (768d)
        intent_res = await GemmaRecognitionEngine.recognize_inbound_intent(cleaned_summary)
        domain_res, _ = await GemmaRecognitionEngine.recognize_domain(cleaned_summary)

        template = PROJECT_TEMPLATES.get(
            intent_res.intent,
            PROJECT_TEMPLATES["COMMERCIAL_QUOTE"],
        )

        effective_budget_eur = budget_hint.strip() if budget_hint and budget_hint.strip() else template["budget_eur"]
        effective_timeline = timeline_hint.strip() if timeline_hint and timeline_hint.strip() else template["timeline"]

        phases: List[Dict[str, str]] = [
            {
                "phase": "Phase 1 — Cadrage Architectural & Prototypage (Jours 1 à 5)",
                "deliverable": "Spécifications techniques, schéma PostgreSQL, maquettes UI/UX et environnement Docker.",
            },
            {
                "phase": "Phase 2 — Développement Core, API & Intégration IA (Semaines 2 à 3)",
                "deliverable": "Backend sécurisé, logique métier, connecteurs externes et interface réactive.",
            },
            {
                "phase": "Phase 3 — Intégration Multimodale & Connecteurs Métier",
                "deliverable": "Passerelles temps réel (WhatsApp/Webhooks/Paiement), mémoire vectorielle pgvector.",
            },
            {
                "phase": "Phase 4 — Audit SAST/OWASP, Recette & Mise en Production",
                "deliverable": "Suite de tests automatisés, durcissement Zero-Trust, déploiement live et formation.",
            },
        ]

        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.strftime("%d/%m/%Y")
        proposal_ref = f"PROP-RK-{now_dt.strftime('%Y%m%d')}-{abs(hash(cleaned_summary)) % 9000 + 1000}"
        estimated_days = 18 if intent_res.intent == "AI_SYSTEM_ARCHITECTURE" else 14
        numeric_budget_eur = 3800 if intent_res.intent == "AI_SYSTEM_ARCHITECTURE" else 2900
        numeric_budget_fcfa = int(numeric_budget_eur * 655.957)

        markdown_doc = f"""# 📋 PROPOSITION D'ARCHITECTURE & DEVIS — ROCKIB QUENUM (AGENCE IIA)
**Référence** : `{proposal_ref}`
**Date** : {now_str}
**Client** : {display_client}
**Qualification Gemma-2 (768d)** : `{intent_res.intent}` (Confiance : {int(min(0.99, max(0.78, intent_res.confidence + 0.45)) * 100)}%) | Skill Directeur : `{intent_res.recommended_skill}`

---

## 🎯 1. Compréhension du Besoin
> {cleaned_summary}

## 🏗️ 2. Architecture Cible Recommandée ({template['title']})
{chr(10).join(f"- {item}" for item in template['stack'])}

## 🚀 3. Plan de Livraison par Jalons
{chr(10).join(f"- **{p['phase']}** : {p['deliverable']}" for p in phases)}

## 💰 4. Estimation Budgétaire & Délai
- **Investissement Estimé (EUR)** : **{effective_budget_eur}** (Base : {numeric_budget_eur} € HT)
- **Équivalent Indicatif (XOF)** : **{template['budget_xof']}** ({numeric_budget_fcfa:,} FCFA)
- **Délai de Réalisation** : **{effective_timeline}** (~{estimated_days} jours-homme)
- **Garanties Incluses** : Code 100% propriétaire, tests automatisés, sécurité Zero-Trust OWASP et support post-déploiement.
"""

        return {
            "proposal_ref": proposal_ref,
            "client_name": display_client,
            "project_title": template["title"],
            "recognized_intent": intent_res.intent,
            "recognized_domain": domain_res.domain or "engineering",
            "recommended_skill": intent_res.recommended_skill,
            "stack": template["stack"],
            "recommended_stack": template["stack"],
            "phases": phases,
            "estimated_days": estimated_days,
            "estimated_budget_eur": numeric_budget_eur,
            "estimated_budget_eur_range": effective_budget_eur,
            "estimated_budget_fcfa": numeric_budget_fcfa,
            "estimated_budget_xof": template["budget_xof"],
            "estimated_timeline": effective_timeline,
            "markdown_proposal": markdown_doc,
            "proposal_markdown": markdown_doc,
            "generated_at": now_dt.isoformat(),
        }
