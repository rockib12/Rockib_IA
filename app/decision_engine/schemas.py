from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from app.decision_engine.models import PermissionAction, ClassificationStatus, ControlOutcome

class DecisionRequest(BaseModel):
    """Requ?te d'arbitrage vers le Decision Engine."""
    workspace_id: str
    agent_id: str
    objective: str = Field(..., description="Objectif de la d?cision")
    situation: str = Field(default="", description="Situation actuelle")
    proposed_action: str = Field(..., description="Action propos?e")
    requested_autonomy_level: int | None = Field(default=None, ge=0, le=5, strict=True)

class ClassificationResult(BaseModel):
    """R?sultat de la classification d'une action."""
    domain: Optional[str] = None
    permission_action: Optional[PermissionAction] = None
    status: ClassificationStatus

class DecisionResponse(BaseModel):
    """R?ponse d'arbitrage du Decision Engine."""
    decision_id: str
    dominant_source: str
    final_action: str
    risk_level: str
    approval_required: bool
    control_outcome: ControlOutcome
    control_reason: str
    permission_granted: bool
