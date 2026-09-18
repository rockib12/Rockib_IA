"""Schémas Pydantic pour la Memory Layer (à compléter)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    workspace_id: str
    type: str = Field(..., description="Type de mémoire (fact, preference, decision_rule, experience, project_memory)")
    content: str
    metadata: dict[str, object] = Field(default_factory=dict)
    confidence_level: float = Field(default=0.5, ge=0.0, le=1.0)
    importance_level: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryRead(BaseModel):
    id: str
    workspace_id: str
    type: str
    status: str
    content: str
    metadata: dict[str, object]
    confidence_level: float
    importance_level: float
