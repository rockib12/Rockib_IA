from __future__ import annotations
import uuid
from pydantic import BaseModel, Field

class CognitiveInput(BaseModel):
    """Entree standard vers le Cognitive Model."""
    workspace_id: uuid.UUID
    objective: str = Field(..., description="Objectif a analyser")
    situation: str = Field(default="", description="Situation actuelle / contexte")

class CognitiveOutput(BaseModel):
    """Sortie standard du Cognitive Model."""
    action: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reasoning: str = ""
