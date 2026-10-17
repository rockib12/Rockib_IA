from __future__ import annotations
from pydantic import BaseModel, Field
from app.decision_engine.models import PermissionAction, RiskLevel

from typing import Any, Optional, List
from app.skills.schemas import ActiveSkillContext

class IntelligenceInput(BaseModel):
    """Entrée pour l'analyse de l'Intelligence."""
    objective: str
    situation: str
    proposed_action: str
    domain: str
    permission_action: PermissionAction
    active_skills: Optional[List[ActiveSkillContext]] = Field(default=None)

class IntelligenceOutput(BaseModel):
    """Sortie de l'analyse de l'Intelligence."""
    suggested_action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    reasoning: str = ""

class RationalAgentOutput(BaseModel):
    """Sortie interne du RationalAgent."""
    suggested_action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str

class RiskAnalystOutput(BaseModel):
    """Sortie interne du RiskAnalyst."""
    risk_level: RiskLevel
    reasoning: str
