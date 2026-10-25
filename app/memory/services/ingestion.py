from __future__ import annotations

import logging
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.models import Memory, MemoryStatus, MemoryType
from app.memory.services.embedding import embed_text

logger = logging.getLogger(__name__)

_STATUS_PROGRESSION = {
    MemoryStatus.supposed: MemoryStatus.deduced,
    MemoryStatus.deduced: MemoryStatus.known,
    MemoryStatus.known: MemoryStatus.verified,
    MemoryStatus.verified: MemoryStatus.verified,  # déjà au maximum
}


def promote_on_confirmation(memory: Memory, confirmation_boost: float = 0.15) -> Memory:
    """Renforce une mémoire confirmée : augmente sa confidence et fait progresser son statut d'un cran."""
    memory.confidence_level = min(memory.confidence_level + confirmation_boost, 1.0)
    memory.status = _STATUS_PROGRESSION[memory.status]
    return memory


async def store_agent_lesson(
    db: AsyncSession,
    workspace_id: uuid.UUID | str,
    agent_id: Optional[uuid.UUID | str],
    lesson_text: str,
    memory_type: str = "experience",
    confidence: float = 0.85,
    importance: float = 0.80,
    metadata: Optional[dict] = None,
) -> Memory:
    """
    Crée et persiste une mémoire/leçon vectorisée pour un agent ou un objectif.
    Génère l'embedding 768d pour alimenter pgvector.
    """
    clean_text = (lesson_text or "").strip()
    if not clean_text:
        raise ValueError("Le texte de la leçon/mémoire ne peut être vide.")

    # 1. Calcul de l'embedding
    embedding_vec = await embed_text(clean_text)

    # 2. Construction de la métadonnée
    meta = dict(metadata or {})
    if agent_id:
        meta["agent_id"] = str(agent_id)

    # 3. Création de l'enregistrement Memory
    mem = Memory(
        workspace_id=uuid.UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id,
        type=MemoryType(memory_type) if isinstance(memory_type, str) else memory_type,
        status=MemoryStatus.verified,
        content=clean_text,
        metadata_json=meta,
        confidence_level=confidence,
        importance_level=importance,
    )
    if hasattr(mem, "embedding"):
        mem.embedding = embedding_vec

    db.add(mem)
    await db.flush()
    return mem
