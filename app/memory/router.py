"""Routeur FastAPI pour la Memory Layer vectorielle et épisodique (P1)."""
from __future__ import annotations

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.dependencies import get_current_user
from app.identity.models import User
from app.memory.services.ingestion import store_agent_lesson
from app.memory.services.search import vector_search_memories, search_memories

memory_router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryCreateRequest(BaseModel):
    workspace_id: uuid.UUID
    content: str = Field(..., min_length=3, max_length=5000)
    agent_id: Optional[uuid.UUID] = None
    type: str = Field(default="experience")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    importance: float = Field(default=0.80, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


class MemoryResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    type: str
    status: str
    content: str
    confidence_level: float
    importance_level: float
    metadata: dict
    created_at: str

    class Config:
        from_attributes = True


@memory_router.post("/lesson", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_lesson(
    body: MemoryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Enregistre une leçon/mémoire vectorisée avec persistance pgvector."""
    try:
        mem = await store_agent_lesson(
            db=db,
            workspace_id=body.workspace_id,
            agent_id=body.agent_id,
            lesson_text=body.content,
            memory_type=body.type,
            confidence=body.confidence,
            importance=body.importance,
            metadata=body.metadata,
        )
        await db.commit()
        return MemoryResponse(
            id=mem.id,
            workspace_id=mem.workspace_id,
            type=mem.type.value if hasattr(mem.type, "value") else str(mem.type),
            status=mem.status.value if hasattr(mem.status, "value") else str(mem.status),
            content=mem.content,
            confidence_level=float(mem.confidence_level),
            importance_level=float(mem.importance_level),
            metadata=mem.metadata_json or {},
            created_at=mem.created_at.isoformat(),
        )
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Échec d'enregistrement mémoire: {exc}",
        )


@memory_router.get("/search", response_model=List[MemoryResponse])
async def search_agent_memories(
    q: str = Query(..., min_length=1, description="Requête sémantique ou mot-clé"),
    workspace_id: uuid.UUID = Query(...),
    agent_id: Optional[uuid.UUID] = Query(None),
    type: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Recherche sémantique vectorielle via pgvector avec fallback textuel."""
    try:
        memories = await vector_search_memories(
            db=db,
            workspace_id=str(workspace_id),
            query_text=q,
            memory_type=type,
            agent_id=str(agent_id) if agent_id else None,
            limit=limit,
        )
        return [
            MemoryResponse(
                id=m.id,
                workspace_id=m.workspace_id,
                type=m.type.value if hasattr(m.type, "value") else str(m.type),
                status=m.status.value if hasattr(m.status, "value") else str(m.status),
                content=m.content,
                confidence_level=float(m.confidence_level),
                importance_level=float(m.importance_level),
                metadata=m.metadata_json or {},
                created_at=m.created_at.isoformat(),
            )
            for m in memories
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur de recherche mémoire: {exc}",
        )


class GemmaRecognitionRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=2000, description="Texte ou intention à reconnaître")
    objective: Optional[str] = Field(default="")
    situation: Optional[str] = Field(default="")


@memory_router.post("/recognize")
async def recognize_with_gemma(
    body: GemmaRecognitionRequest,
    current_user: User = Depends(get_current_user),
):
    """Point d'entrée unifié de reconnaissance vectorielle EmbeddingGemma / Gemma-2 (768d).

    Retourne simultanément :
    - La classification Domaine & Permission (DomainClassifier + Gemma-2)
    - La reconnaissance d'intention visiteur/prospect (Inbound Intent)
    - Le backend d'embedding 768d actif
    """
    from app.intelligence.services.gemma_recognition import GemmaRecognitionEngine
    from app.memory.services.embedding import get_active_embedding_backend

    domain_res, domain_diag = await GemmaRecognitionEngine.recognize_domain(
        proposed_action=body.text,
        objective=body.objective or "",
        situation=body.situation or "",
    )
    intent_res = await GemmaRecognitionEngine.recognize_inbound_intent(body.text)

    return {
        "embedding_engine": get_active_embedding_backend(),
        "dimensions": 768,
        "domain_recognition": {
            "status": domain_res.status.value,
            "domain": domain_res.domain,
            "permission_action": domain_res.permission_action.value if domain_res.permission_action else None,
            "diagnostics": domain_diag,
        },
        "intent_recognition": {
            "intent": intent_res.intent,
            "confidence": intent_res.confidence,
            "recommended_skill": intent_res.recommended_skill,
            "should_capture_lead": intent_res.should_capture_lead,
            "runner_up_intent": intent_res.runner_up_intent,
            "scores": intent_res.scores,
        },
    }

