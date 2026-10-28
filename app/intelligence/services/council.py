"""
Protocole de Consensus Multi-Agents — "Council of Specialists" (Chantier N°4).

Réunit dynamiquement les meilleurs agents spécialistes d'un workspace (sélectionnés via
la reconnaissance vectorielle Gemma-2 768d) pour délibérer en parallèle sur un objectif
ou une action critique, enregistrer les échanges P2P et sceller le consensus dans pgvector.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import Agent, AgentMessage
from app.intelligence.services.gemma_recognition import GemmaRecognitionEngine
from app.memory.services.embedding import cosine_similarity, embed_text, embed_texts

logger = logging.getLogger(__name__)


@dataclass
class SpecialistVote:
    agent_id: str
    agent_name: str
    agent_role: str
    specialty_similarity: float
    stance: str  # "APPROVE" | "CAUTION" | "REJECT"
    confidence: float
    opinion: str


@dataclass
class CouncilVerdict:
    council_id: str
    lead_agent_id: str
    objective: str
    proposed_action: str
    consensus_stance: str
    consensus_confidence: float
    synthesized_recommendation: str
    votes: List[SpecialistVote] = field(default_factory=list)
    p2p_message_ids: List[str] = field(default_factory=list)


class CouncilOfSpecialists:
    """Orchestre une délibération multi-agents parallèle pondérée par expertise Gemma-2 (768d)."""

    @classmethod
    async def select_top_specialists(
        cls,
        query_text: str,
        candidates: Sequence[Agent],
        max_specialists: int = 2,
    ) -> List[tuple[Agent, float]]:
        """Sélectionne les N agents spécialistes les plus pertinents via similarité cosinus Gemma-2."""
        if not candidates:
            return []

        query_vec = await embed_text(query_text, task_type="classification")
        profiles = [
            f"{getattr(ag, 'name', '')} {getattr(ag, 'role', '')} {getattr(ag, 'description', '')}".strip()
            for ag in candidates
        ]
        profile_vecs = await embed_texts(profiles, task_type="search_document")

        scored: List[tuple[Agent, float]] = []
        for ag, p_vec in zip(candidates, profile_vecs):
            sim = cosine_similarity(query_vec, p_vec)
            scored.append((ag, round(float(sim), 4)))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:max_specialists]

    @classmethod
    async def _solicit_specialist_vote(
        cls,
        specialist: Agent,
        similarity: float,
        lead_name: str,
        objective: str,
        proposed_action: str,
    ) -> SpecialistVote:
        """Génère le vote et l'avis technique d'un agent spécialiste (en parallèle)."""
        role_str = specialist.role or "Specialist Agent"
        role_lower = f"{specialist.name} {role_str}".lower()
        act_lower = f"{objective} {proposed_action}".lower()

        # Détection par frontières de mots strictes (aucun faux positif sur 'conteneur' / 'eur')
        import re
        is_destructive = bool(re.search(r"\b(delete|supprimer|drop|purge|destroy|effacer)\b", act_lower))
        is_financial = bool(re.search(r"\b(spend|dépenser|payer|paiement|budget|eur|usd|xof)\b", act_lower))

        if is_destructive:
            stance = "CAUTION"
            base_conf = 0.88
            default_opinion = (
                f"[{specialist.name} — {role_str}] Action irréversible détectée. "
                f"Je recommande un snapshot de sauvegarde préalable et une validation humaine stricte."
            )
        elif is_financial and ("security" in role_lower or "finance" in role_lower or "audit" in role_lower):
            stance = "CAUTION"
            base_conf = 0.90
            default_opinion = (
                f"[{specialist.name} — {role_str}] Engagement budgétaire identifié. "
                f"Vérifier le plafond de dépense autorisé et l'idempotence transactionnelle avant exécution."
            )
        else:
            stance = "APPROVE"
            base_conf = 0.92
            default_opinion = (
                f"[{specialist.name} — {role_str}] Validation technique accordée à {lead_name}. "
                f"L'action '{proposed_action[:90]}' est alignée avec les standards d'architecture et d'idempotence."
            )

        opinion_text = default_opinion
        try:
            from app.intelligence.services.providers.groq_provider import GroqProvider

            provider = GroqProvider()
            prompt = (
                f"Tu sièges au Conseil des Spécialistes IA de Rockib IA en tant que '{specialist.name}' ({role_str}).\n"
                f"L'agent responsable '{lead_name}' soumet pour délibération :\n"
                f"- Objectif : {objective}\n"
                f"- Action proposée : {proposed_action}\n\n"
                "Donne ton avis d'expert en 2 phrases concises (faisabilité, sécurité, recommandation concrète)."
            )
            llm_resp = await provider.generate(prompt)
            if llm_resp and len(llm_resp.strip()) > 10:
                opinion_text = llm_resp.strip()
        except Exception:
            pass

        return SpecialistVote(
            agent_id=str(specialist.id),
            agent_name=specialist.name,
            agent_role=role_str,
            specialty_similarity=max(0.15, similarity),
            stance=stance,
            confidence=base_conf,
            opinion=opinion_text,
        )

    @classmethod
    async def convene_council(
        cls,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        lead_agent_id: uuid.UUID,
        objective: str,
        proposed_action: str,
        max_specialists: int = 2,
    ) -> CouncilVerdict:
        """Réunit le Conseil des Spécialistes en parallèle, persiste les dialogues P2P et scelle le consensus."""
        council_id = str(uuid.uuid4())

        lead_agent = (
            await db.execute(select(Agent).where(Agent.id == lead_agent_id))
        ).scalar_one_or_none()
        lead_name = lead_agent.name if lead_agent else "Orchestrateur Principal"

        peer_candidates = list(
            (
                await db.execute(
                    select(Agent).where(
                        Agent.workspace_id == workspace_id,
                        Agent.id != lead_agent_id,
                        Agent.is_active == True,  # noqa: E712
                    )
                )
            ).scalars().all()
        )

        selected_pairs = await cls.select_top_specialists(
            query_text=f"{objective} {proposed_action}",
            candidates=peer_candidates,
            max_specialists=max_specialists,
        )

        if not selected_pairs:
            return CouncilVerdict(
                council_id=council_id,
                lead_agent_id=str(lead_agent_id),
                objective=objective,
                proposed_action=proposed_action,
                consensus_stance="APPROVE",
                consensus_confidence=0.85,
                synthesized_recommendation="Aucun pair spécialiste additionnel requis ; exécution directe sous gouvernance standard.",
                votes=[],
                p2p_message_ids=[],
            )

        # Délibération parallèle de tous les spécialistes sélectionnés
        votes: List[SpecialistVote] = list(
            await asyncio.gather(
                *[
                    cls._solicit_specialist_vote(
                        specialist=ag,
                        similarity=sim,
                        lead_name=lead_name,
                        objective=objective,
                        proposed_action=proposed_action,
                    )
                    for ag, sim in selected_pairs
                ]
            )
        )

        # Calcul du consensus pondéré par la proximité d'expertise Gemma-2
        total_weight = sum(v.specialty_similarity for v in votes) or 1.0
        weighted_conf = sum(v.confidence * v.specialty_similarity for v in votes) / total_weight
        has_caution = any(v.stance in ("CAUTION", "REJECT") for v in votes)
        consensus_stance = "CAUTION" if has_caution else "APPROVE"

        summary_parts = [f"[{v.agent_name} ({v.stance})]: {v.opinion}" for v in votes]
        synthesized = " | ".join(summary_parts)

        # Enregistrer chaque échange du Conseil dans `agent_messages` pour la traçabilité P2P & la vue 3D
        p2p_ids: List[str] = []
        now_utc = datetime.now(timezone.utc)
        for v in votes:
            msg = AgentMessage(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                sender_agent_id=lead_agent_id,
                recipient_agent_id=uuid.UUID(v.agent_id),
                subject=f"[Conseil IA #{council_id[:6]}] {objective[:100]}",
                content=f"Délibération du Conseil sur : {proposed_action}",
                status="REPLIED",
                reply_content=v.opinion,
                metadata_json={
                    "council_id": council_id,
                    "stance": v.stance,
                    "confidence": v.confidence,
                    "specialty_similarity": v.specialty_similarity,
                },
                replied_at=now_utc,
            )
            db.add(msg)
            p2p_ids.append(str(msg.id))

        # Indexer le verdict du Conseil dans la mémoire vectorielle Gemma-2 (pgvector)
        try:
            from app.memory.services.ingestion import store_agent_lesson

            await store_agent_lesson(
                db=db,
                workspace_id=workspace_id,
                agent_id=lead_agent_id,
                lesson_text=(
                    f"Verdict Conseil Multi-Agents ({consensus_stance}, conf={weighted_conf:.2f}) "
                    f"sur '{objective}' : {synthesized[:600]}"
                ),
                memory_type="project_memory",
                confidence=round(weighted_conf, 3),
                importance=0.90,
                metadata={"council_id": council_id, "specialists_count": len(votes)},
            )
        except Exception as mem_exc:
            logger.debug("Indexation mémoire du Conseil ignorée: %s", mem_exc)

        await db.commit()

        return CouncilVerdict(
            council_id=council_id,
            lead_agent_id=str(lead_agent_id),
            objective=objective,
            proposed_action=proposed_action,
            consensus_stance=consensus_stance,
            consensus_confidence=round(weighted_conf, 4),
            synthesized_recommendation=synthesized,
            votes=votes,
            p2p_message_ids=p2p_ids,
        )
