"""
Moteur Central de Reconnaissance Sémantique — Architecture EmbeddingGemma / Gemma-2 (768d).

Unifie toutes les couches de reconnaissance de Rockib IA sous un même espace vectoriel 768d :
1. Reconnaissance de Domaine & Permission (DomainClassifier Semantic Layer)
2. Reconnaissance & Sélection JIT de Compétences parmi les 107 Skills (SkillSelector)
3. Reconnaissance d'Agent Pair pour le Routage P2P (Inter-Agent Dialogue Bus)
4. Reconnaissance d'Intention Visiteur / Prospect (Concierge Inbound Gateway)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.decision_engine.models import ClassificationStatus, PermissionAction
from app.decision_engine.schemas import ClassificationResult
from app.memory.services.embedding import (
    cosine_similarity,
    embed_text,
    embed_texts,
    get_active_embedding_backend,
)

logger = logging.getLogger(__name__)


@dataclass
class SemanticDomainCentroid:
    domain: str
    permission: PermissionAction
    anchor_description: str
    prototype_phrases: Tuple[str, ...]


@dataclass
class InboundIntentResult:
    intent: str
    confidence: float
    recommended_skill: str
    should_capture_lead: bool
    runner_up_intent: Optional[str] = None
    scores: Dict[str, float] = field(default_factory=dict)


# Centroïdes de gouvernance bilingues (FR/EN) pour la reconnaissance de domaine
DOMAIN_CENTROIDS: Tuple[SemanticDomainCentroid, ...] = (
    SemanticDomainCentroid(
        domain="finance",
        permission=PermissionAction.SPEND,
        anchor_description=(
            "finance budget payer paiement spend dépenser facturer facture invoice stripe "
            "argent money coût cost tarif acheter purchase sponsoriser campagne ads eur usd xof"
        ),
        prototype_phrases=(
            "dépenser du budget publicitaire ou effectuer un paiement financier",
            "payer une facture fournisseur ou souscrire un abonnement payant",
            "lancer une campagne sponsorisée avec budget en euros ou dollars",
        ),
    ),
    SemanticDomainCentroid(
        domain="finance",
        permission=PermissionAction.READ,
        anchor_description=(
            "consulter budget vérifier dépenses inspecter solde financier rapport comptable "
            "analyse financière lire coûts roas cpc ctr"
        ),
        prototype_phrases=(
            "vérifier l'état du budget et consulter l'historique des dépenses",
            "analyser les indicateurs financiers sans dépenser d'argent",
        ),
    ),
    SemanticDomainCentroid(
        domain="security",
        permission=PermissionAction.READ,
        anchor_description=(
            "cyber security sécurité audit owasp sast vulnérabilité pentest firewall "
            "zero-trust hmac jwt auth chiffrement encryption aes secret vault token xss sqli ssrf"
        ),
        prototype_phrases=(
            "réaliser un audit de cybersécurité SAST et vérifier les vulnérabilités OWASP",
            "analyser la posture de sécurité zero-trust et détecter les fuites de secrets",
        ),
    ),
    SemanticDomainCentroid(
        domain="infrastructure",
        permission=PermissionAction.UPDATE,
        anchor_description=(
            "infra infrastructure docker kubernetes k8s deploy déployer déploiement nginx "
            "server serveur cloud aws gcp terraform ansible ci/cd pipeline linux cluster scaling production"
        ),
        prototype_phrases=(
            "déployer un conteneur Docker ou provisionner un cluster Kubernetes en production",
            "configurer le reverse proxy Nginx et orchestrer le pipeline CI/CD cloud",
        ),
    ),
    SemanticDomainCentroid(
        domain="code",
        permission=PermissionAction.UPDATE,
        anchor_description=(
            "frontend backend react vite ui ux threejs 3d cockpit composant django fastapi "
            "python api rest graphql celery uvicorn endpoint webhook microservice postgres sql sqlalchemy alembic"
        ),
        prototype_phrases=(
            "développer un composant React ou implémenter un endpoint FastAPI / Django",
            "créer une migration SQLAlchemy Alembic et optimiser les requêtes PostgreSQL",
        ),
    ),
    SemanticDomainCentroid(
        domain="communication",
        permission=PermissionAction.SEND,
        anchor_description=(
            "communication message email mail telegram whatsapp discord slack notification "
            "alerte envoyer send contact appeler call voix voice rappel callback"
        ),
        prototype_phrases=(
            "envoyer une notification Telegram, un message WhatsApp ou un email au client",
            "transmettre une alerte ou contacter un collaborateur sur Discord ou Slack",
        ),
    ),
    SemanticDomainCentroid(
        domain="content",
        permission=PermissionAction.CREATE,
        anchor_description=(
            "content rédiger écrire write article post blog linkedin twitter instagram "
            "facebook publication copywriting marketing seo rapport report synthèse summary"
        ),
        prototype_phrases=(
            "rédiger un article technique, un post LinkedIn ou un rapport exécutif",
            "préparer un brouillon de publication marketing et optimiser le contenu SEO",
        ),
    ),
    SemanticDomainCentroid(
        domain="research",
        permission=PermissionAction.READ,
        anchor_description=(
            "research recherche chercher search analyser analyse analyze study benchmark "
            "comparer explorer veille documentation web wikipedia news inspecter vérifier read"
        ),
        prototype_phrases=(
            "rechercher de la documentation technique et effectuer une veille comparative",
            "analyser des articles scientifiques ou explorer des sources web",
        ),
    ),
    SemanticDomainCentroid(
        domain="system",
        permission=PermissionAction.DELETE,
        anchor_description=(
            "destructive delete supprimer effacer drop truncate destroy détruire "
            "purge remove révoquer revoke format wipe kill"
        ),
        prototype_phrases=(
            "supprimer définitivement des données, purger une table ou détruire une ressource",
            "effacer un fichier critique ou révoquer des accès de manière irréversible",
        ),
    ),
)

# Centroïdes d'intention visiteur / prospect pour le Concierge
INBOUND_INTENT_CENTROIDS: Dict[str, Dict[str, Any]] = {
    "COMMERCIAL_QUOTE": {
        "anchor": (
            "commercial lead prospect client vente devis quote tarif prix budget coût "
            "combien coûte projet développer application saas e-commerce agence iia"
        ),
        "skill": "lead_qualification",
        "capture_lead": True,
    },
    "CYBER_SECURITY_AUDIT": {
        "anchor": (
            "cyber security sécurité audit owasp sast pentest vulnérabilité faille "
            "protection chiffrement zero-trust conformité sécuriser"
        ),
        "skill": "cybersecurity_defensive",
        "capture_lead": True,
    },
    "AI_SYSTEM_ARCHITECTURE": {
        "anchor": (
            "ai ia agent autonome orchestrateur arbitrage déterministe llm rag pgvector "
            "gemma mémoire multi-agents architecture système"
        ),
        "skill": "portfolio_ambassador",
        "capture_lead": False,
    },
    "FULLSTACK_ENGINEERING": {
        "anchor": (
            "frontend backend react vite django fastapi python postgres docker "
            "martistore waauto api microservice performance"
        ),
        "skill": "backend_django",
        "capture_lead": False,
    },
    "URGENT_CALLBACK": {
        "anchor": (
            "communication appeler call téléphone whatsapp rdv meeting rendez-vous "
            "rappel callback parler directement contact urgent"
        ),
        "skill": "lead_qualification",
        "capture_lead": True,
    },
}


class GemmaRecognitionEngine:
    """Moteur unifié de reconnaissance vectorielle 768d basé sur EmbeddingGemma / Gemma-2."""

    _domain_centroid_Cache: Optional[List[Tuple[SemanticDomainCentroid, List[float]]]] = None
    _intent_centroid_cache: Optional[Dict[str, List[float]]] = None

    @classmethod
    async def _get_domain_centroids(cls) -> List[Tuple[SemanticDomainCentroid, List[float]]]:
        if cls._domain_centroid_Cache is None:
            texts = [
                f"{c.anchor_description} {' '.join(c.prototype_phrases)}"
                for c in DOMAIN_CENTROIDS
            ]
            vecs = await embed_texts(texts, task_type="classification")
            cls._domain_centroid_Cache = list(zip(DOMAIN_CENTROIDS, vecs))
        return cls._domain_centroid_Cache

    @classmethod
    async def _get_intent_centroids(cls) -> Dict[str, List[float]]:
        if cls._intent_centroid_cache is None:
            keys = list(INBOUND_INTENT_CENTROIDS.keys())
            texts = [INBOUND_INTENT_CENTROIDS[k]["anchor"] for k in keys]
            vecs = await embed_texts(texts, task_type="classification")
            cls._intent_centroid_cache = dict(zip(keys, vecs))
        return cls._intent_centroid_cache

    @classmethod
    async def recognize_domain(
        cls,
        proposed_action: str,
        objective: str = "",
        situation: str = "",
        min_confidence: float = 0.32,
        min_margin: float = 0.04,
    ) -> Tuple[ClassificationResult, Dict[str, Any]]:
        """Reconnaît sémantiquement le domaine et la permission d'une action via Gemma-2 768d.

        Garantit l'invariant Fail-Closed :
        - Si le score maximal < min_confidence -> ClassificationStatus.UNKNOWN
        - Si deux domaines distincts sont trop proches (écart < min_margin) -> ClassificationStatus.AMBIGUOUS
        - Sinon -> ClassificationStatus.CERTAIN
        """
        combined = f"{proposed_action} {objective} {situation}".strip()
        if not combined:
            return ClassificationResult(status=ClassificationStatus.UNKNOWN), {"reason": "empty_input"}

        query_vec = await embed_text(combined, task_type="classification")
        centroids = await cls._get_domain_centroids()

        scored: List[Tuple[float, SemanticDomainCentroid]] = []
        for centroid, c_vec in centroids:
            sim = cosine_similarity(query_vec, c_vec)
            scored.append((sim, centroid))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_centroid = scored[0]
        second_score, second_centroid = scored[1] if len(scored) > 1 else (0.0, best_centroid)
        margin = best_score - second_score

        diagnostics = {
            "engine": get_active_embedding_backend(),
            "top_domain": best_centroid.domain,
            "top_permission": best_centroid.permission.value,
            "confidence": round(best_score, 4),
            "runner_up_domain": second_centroid.domain,
            "runner_up_score": round(second_score, 4),
            "margin": round(margin, 4),
        }

        if best_score < min_confidence:
            return ClassificationResult(status=ClassificationStatus.UNKNOWN), diagnostics

        if (
            len(scored) > 1
            and second_score >= min_confidence
            and margin < min_margin
            and (best_centroid.domain != second_centroid.domain or best_centroid.permission != second_centroid.permission)
        ):
            return ClassificationResult(status=ClassificationStatus.AMBIGUOUS), diagnostics

        return (
            ClassificationResult(
                domain=best_centroid.domain,
                permission_action=best_centroid.permission,
                status=ClassificationStatus.CERTAIN,
            ),
            diagnostics,
        )

    @classmethod
    async def rank_skills_by_similarity(
        cls,
        task_text: str,
        skill_profiles: Sequence[Tuple[str, str]],
    ) -> Dict[str, float]:
        """Calcule la similarité cosinus Gemma-2 768d entre une tâche et une liste de (slug, profile_text)."""
        if not task_text or not skill_profiles:
            return {}

        query_vec = await embed_text(task_text, task_type="classification")
        profile_texts = [prof for _, prof in skill_profiles]
        profile_vecs = await embed_texts(profile_texts, task_type="search_document")

        scores: Dict[str, float] = {}
        for (slug, _), p_vec in zip(skill_profiles, profile_vecs):
            scores[slug] = round(cosine_similarity(query_vec, p_vec), 4)
        return scores

    @classmethod
    async def recognize_best_peer_agent(
        cls,
        message_text: str,
        subject: str,
        candidate_agents: Sequence[Any],
    ) -> Tuple[Optional[Any], float]:
        """Identifie l'agent pair optimal pour un dialogue P2P par similarité vectorielle Gemma-2."""
        if not candidate_agents:
            return None, 0.0
        if len(candidate_agents) == 1:
            return candidate_agents[0], 1.0

        query = f"{subject} {message_text}".strip()
        query_vec = await embed_text(query, task_type="classification")

        agent_descriptions = [
            f"{getattr(ag, 'name', '')} {getattr(ag, 'role', '')} {getattr(ag, 'description', '')}".strip()
            for ag in candidate_agents
        ]
        agent_vecs = await embed_texts(agent_descriptions, task_type="search_document")

        best_agent = candidate_agents[0]
        best_sim = -1.0
        for ag, a_vec in zip(candidate_agents, agent_vecs):
            sim = cosine_similarity(query_vec, a_vec)
            if sim > best_sim:
                best_sim = sim
                best_agent = ag

        return best_agent, round(best_sim, 4)

    @classmethod
    async def recognize_inbound_intent(cls, user_message: str) -> InboundIntentResult:
        """Reconnaît l'intention d'un visiteur/prospect via les centroïdes Gemma-2 768d."""
        cleaned = (user_message or "").strip()
        if not cleaned:
            return InboundIntentResult(
                intent="PORTFOLIO_EXPLORATION",
                confidence=0.0,
                recommended_skill="portfolio_ambassador",
                should_capture_lead=False,
            )

        query_vec = await embed_text(cleaned, task_type="classification")
        centroids = await cls._get_intent_centroids()

        scored: List[Tuple[str, float]] = []
        for intent_key, c_vec in centroids.items():
            sim = cosine_similarity(query_vec, c_vec)
            scored.append((intent_key, round(sim, 4)))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_intent, top_score = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else None
        meta = INBOUND_INTENT_CENTROIDS[top_intent]

        return InboundIntentResult(
            intent=top_intent,
            confidence=top_score,
            recommended_skill=meta["skill"],
            should_capture_lead=bool(meta["capture_lead"] and top_score >= 0.25),
            runner_up_intent=runner_up,
            scores=dict(scored),
        )
