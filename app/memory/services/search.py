from __future__ import annotations

import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.models import Memory, HAS_PGVECTOR
from app.memory.services.decay import compute_effective_confidence, compute_effective_weight
from app.memory.services.embedding import embed_text

logger = logging.getLogger(__name__)


async def search_memories(
    db: AsyncSession,
    workspace_id: str,
    query: str,
    memory_type: str | None = None,
    limit: int = 10,
) -> list[Memory]:
    """Recherche des mémoires par correspondance textuelle simple, triées par poids effectif décroissant."""
    stmt = select(Memory).where(
        Memory.workspace_id == workspace_id,
        Memory.content.ilike(f"%{query}%"),
    )
    if memory_type:
        stmt = stmt.where(Memory.type == memory_type)

    result = await db.execute(stmt)
    memories = result.scalars().all()

    scored = [
        (
            m,
            compute_effective_weight(
                compute_effective_confidence(m.confidence_level, m.status, m.last_accessed_at),
                m.importance_level,
            ),
        )
        for m in memories
    ]
    
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [m for m, _ in scored[:limit]]


async def vector_search_memories(
    db: AsyncSession,
    workspace_id: str,
    query_text: str,
    memory_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = 5,
) -> List[Memory]:
    """
    Recherche vectorielle sémantique s'appuyant sur pgvector (Cosine Distance <=>).
    Utilise le support natif ORM de pgvector ou fallback textuel.
    """
    if not query_text or not query_text.strip():
        return []

    # 1. Calcul du vecteur d'embedding de la requête
    try:
        query_vec = await embed_text(query_text)
    except Exception as exc:
        logger.warning("Échec du calcul d'embedding pour la recherche: %s", exc)
        return await search_memories(db, workspace_id, query_text, memory_type, limit)

    # 2. Requête Cosine Distance via pgvector ORM
    if HAS_PGVECTOR and hasattr(Memory, "embedding"):
        try:
            stmt = select(Memory).where(
                Memory.workspace_id == workspace_id,
                Memory.embedding.isnot(None),
            )
            if memory_type:
                stmt = stmt.where(Memory.type == memory_type)
            if agent_id:
                stmt = stmt.where(Memory.metadata_json["agent_id"].astext == str(agent_id))

            # pgvector ORM cosine_distance
            stmt = stmt.order_by(Memory.embedding.cosine_distance(query_vec)).limit(limit)
            res = await db.execute(stmt)
            return list(res.scalars().all())
        except Exception as exc:
            logger.warning("Recherche vectorielle pgvector impossible (%s). Fallback textuel.", exc)

    # Fallback textuel
    return await search_memories(db, workspace_id, query_text, memory_type, limit)
