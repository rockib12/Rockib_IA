from typing import Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.memory.models import Memory, MemoryType
from app.memory.services.decay import compute_effective_confidence, compute_effective_weight
from app.memory.services.embedding import cosine_similarity, embed_text


async def mine_patterns(
    db: AsyncSession,
    workspace_id: str,
    limit: int = 20,
    query_context: Optional[str] = None,
) -> str:
    """
    Récupère les préférences, règles de décision, expériences d'apprentissage et
    accords P2P d'un workspace, pondérés par fraîcheur temporelle et similarité
    vectorielle Gemma-2 (768d).
    """
    stmt = select(Memory).where(
        Memory.workspace_id == workspace_id,
        or_(
            Memory.type == MemoryType.preference,
            Memory.type == MemoryType.decision_rule,
            Memory.type == MemoryType.experience,
            Memory.type == MemoryType.project_memory,
        ),
    )

    result = await db.execute(stmt)
    memories = result.scalars().all()

    if not memories:
        return "Aucun pattern cognitif (preference/decision) trouve pour ce workspace."

    query_vec = None
    if query_context:
        try:
            query_vec = await embed_text(query_context, task_type="search_query")
        except Exception:
            query_vec = None

    scored = []
    for m in memories:
        base_weight = compute_effective_weight(
            compute_effective_confidence(m.confidence_level, m.status, m.last_accessed_at),
            m.importance_level,
        )
        sim_bonus = 0.0
        if query_vec is not None:
            mem_vec = getattr(m, "embedding", None)
            if mem_vec is not None and len(mem_vec) == len(query_vec):
                sim_bonus = max(0.0, cosine_similarity(query_vec, list(mem_vec))) * 0.35
        scored.append((m, base_weight + sim_bonus))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    top_memories = scored[:limit]

    label_map = {
        MemoryType.preference: "PREFERENCE",
        MemoryType.decision_rule: "DECISION",
        MemoryType.experience: "EXPERIENCE_APPRISE",
        MemoryType.project_memory: "ACCORD_P2P_PROJET",
    }

    lines = []
    for m, weight in top_memories:
        label = label_map.get(m.type, "MEMOIRE")
        lines.append(f"- [{label}] {m.content} (poids: {weight:.2f})")

    return "\n".join(lines)
