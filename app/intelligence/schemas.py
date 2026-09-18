from __future__ import annotations
from pydantic import BaseModel, Field
from app.decision_engine.models import PermissionAction, RiskLevel

class IntelligenceInput(BaseModel):
    """Entr?e pour l'analyse de l'Intelligence."""
    objective: str
    situation: str
    proposed_action: str
    domain: str
    permission_action: PermissionAction

class IntelligenceOutput(BaseModel):
    """Sortie de l'analyse de l'Intelligence."""
    suggested_action: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    reasoning: str = ""

class RationalAgentOutput(BaseModel):
    """Sortie interne du RationalAgent."""
    suggested_action: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str

class RiskAnalystOutput(BaseModel):
    """Sortie interne du RiskAnalyst."""
    risk_level: RiskLevel
    reasoning: str
