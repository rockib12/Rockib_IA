import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ArbitrationRule(str, PyEnum):
    cognitive_wins = "cognitive_wins"
    intelligence_wins = "intelligence_wins"
    consensus_required = "consensus_required"
    escalate = "escalate"


class DominantSource(str, PyEnum):
    cognitive = "cognitive"
    intelligence = "intelligence"
    consensus = "consensus"


class RiskLevel(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ReversibilityLevel(str, PyEnum):
    reversible = "reversible"
    partially_reversible = "partially_reversible"
    irreversible = "irreversible"


class ImpactType(str, PyEnum):
    internal = "internal"
    client_facing = "client_facing"
    financial = "financial"
    reputational = "reputational"


class PermissionAction(str, PyEnum):
    READ = "READ"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SEND = "SEND"
    PUBLISH = "PUBLISH"
    SPEND = "SPEND"



class ClassificationStatus(str, PyEnum):
    CERTAIN = "CERTAIN"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"

class ControlOutcome(str, PyEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"
    STOP = "STOP"


class DecisionStatus(str, PyEnum):
    pending_approval = "pending_approval"
    executed = "executed"
    rejected = "rejected"
    escalated = "escalated"
    expired = "expired"


# Types Enum déjà présents en base (migration 001). Le nom doit être déclaré
# explicitement : sinon SQLAlchemy dérive « risklevel » du nom de la classe Python
# et PostgreSQL refuse la requête (écart §11 « Noms d'Enums divergents »).
ARBITRATION_RULE_ENUM = Enum(ArbitrationRule, name="arbitration_rule")
DOMINANT_SOURCE_ENUM = Enum(DominantSource, name="dominant_source")
RISK_LEVEL_ENUM = Enum(RiskLevel, name="risk_level")
REVERSIBILITY_LEVEL_ENUM = Enum(ReversibilityLevel, name="reversibility_level")
IMPACT_TYPE_ENUM = Enum(ImpactType, name="impact_type")
PERMISSION_ACTION_ENUM = Enum(PermissionAction, name="permission_action")
DECISION_STATUS_ENUM = Enum(DecisionStatus, name="decision_status")


class DecisionDomainConfig(Base):
    __tablename__ = "decision_domain_config"
    __table_args__ = (
        CheckConstraint("max_autonomy_level BETWEEN 0 AND 5", name="policy_autonomy_range"),
    )

    # Explicit opt-in: an existing arbitration policy grants no execution rights.
    execution_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    max_autonomy_level: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0", nullable=False)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    permission_action: Mapped[PermissionAction] = mapped_column(PERMISSION_ACTION_ENUM, nullable=False)

    arbitration_rule: Mapped[ArbitrationRule] = mapped_column(ARBITRATION_RULE_ENUM, nullable=False)
    base_risk_level: Mapped[RiskLevel] = mapped_column(RISK_LEVEL_ENUM, nullable=False)
    base_reversibility: Mapped[ReversibilityLevel] = mapped_column(REVERSIBILITY_LEVEL_ENUM, nullable=False)
    base_impact: Mapped[ImpactType] = mapped_column(IMPACT_TYPE_ENUM, nullable=False)

    disagreement_threshold: Mapped[float] = mapped_column(Numeric(3, 2), default=0.40, nullable=False)
    approval_timeout_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Decision(Base):
    __tablename__ = "decisions"

    control_outcome: Mapped[ControlOutcome] = mapped_column(
        Enum(ControlOutcome, native_enum=False, length=8, create_constraint=True, name="control_outcome"),
        default=ControlOutcome.STOP, server_default="STOP", nullable=False,
    )
    control_reason: Mapped[str] = mapped_column(String(100), default="NOT_EVALUATED", server_default="NOT_EVALUATED", nullable=False)
    action_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    domain_config_id: Mapped[Optional[int]] = mapped_column(ForeignKey("decision_domain_config.id"), nullable=True)

    objective: Mapped[str] = mapped_column(nullable=False)
    situation: Mapped[str] = mapped_column(nullable=False)
    proposed_action: Mapped[str] = mapped_column(nullable=False)

    # Avis des deux couches
    cognitive_action: Mapped[Optional[str]] = mapped_column(nullable=True)
    cognitive_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    intelligence_action: Mapped[Optional[str]] = mapped_column(nullable=True)
    intelligence_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)

    # Arbitrage
    dominant_source: Mapped[Optional[DominantSource]] = mapped_column(DOMINANT_SOURCE_ENUM, nullable=True)
    disagreement: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)

    # Risques
    risk_level: Mapped[RiskLevel] = mapped_column(RISK_LEVEL_ENUM, nullable=False)
    risk_reversibility: Mapped[ReversibilityLevel] = mapped_column(REVERSIBILITY_LEVEL_ENUM, nullable=False)
    risk_impact: Mapped[ImpactType] = mapped_column(IMPACT_TYPE_ENUM, nullable=False)
    risk_ai_adjusted: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Autonomie
    requested_autonomy_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    applied_autonomy_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Permission
    permission_required: Mapped[PermissionAction] = mapped_column(
        PERMISSION_ACTION_ENUM, nullable=False
    )
    permission_granted: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Approbation
    approval_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    approval_reason: Mapped[Optional[str]] = mapped_column(nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Décision finale
    final_action: Mapped[Optional[str]] = mapped_column(nullable=True)
    final_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    status: Mapped[DecisionStatus] = mapped_column(
        DECISION_STATUS_ENUM,
        default=DecisionStatus.pending_approval.value,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class DecisionOutcome(Base):
    __tablename__ = "decision_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False)

    result_summary: Mapped[str] = mapped_column(nullable=False)
    success: Mapped[Optional[bool]] = mapped_column(nullable=True)
    lesson: Mapped[Optional[str]] = mapped_column(nullable=True)

    cognitive_was_right: Mapped[Optional[bool]] = mapped_column(nullable=True)
    intelligence_was_right: Mapped[Optional[bool]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
