from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.memory.models import Memory
from app.memory.services.decay import compute_effective_confidence, compute_effective_weight

async def mine_patterns(db: AsyncSession, workspace_id: str, limit: int = 20) -> str:
    """
    Recupere les preferences et decisions les plus pertinentes d'un workspace
    et les consolide en un resume textuel condense.
    """
    stmt = select(Memory).where(
        Memory.workspace_id == workspace_id,
        or_(Memory.type == "preference", Memory.type == "decision")
    )
    
    result = await db.execute(stmt)
    memories = result.scalars().all()

    scored = [
        (m, compute_effective_weight(
            compute_effective_confidence(m.confidence_level, m.status, m.last_accessed_at),
            m.importance_level,
        ))
        for m in memories
    ]
    
    scored.sort(key=lambda pair: pair[1], reverse=True)
    top_memories = scored[:limit]
    
    if not top_memories:
        return "Aucun pattern cognitif (preference/decision) trouve pour ce workspace."

    lines = []
    for m, weight in top_memories:
        label = "PREFERENCE" if m.type == "preference" else "DECISION"
        lines.append(f"- [{label}] {m.content} (poids: {weight:.2f})")

    return "\n".join(lines)
