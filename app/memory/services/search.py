from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.memory.models import Memory
from app.memory.services.decay import compute_effective_confidence, compute_effective_weight

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
        (m, compute_effective_weight(
            compute_effective_confidence(m.confidence_level, m.status, m.last_accessed_at),
            m.importance_level,
        ))
        for m in memories
    ]
    
    # Tri par poids décroissant
    scored.sort(key=lambda pair: pair[1], reverse=True)
    
    return [m for m, _ in scored[:limit]]
