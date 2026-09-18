"""Phase 2 — exécution fiable : Action, Autorisation, Tentative, Résultat, Réservation, Audit.

Ces tables séparent explicitement :

- l'**action structurée** : ce qui est proposé puis autorisé, avec son empreinte canonique ;
- l'**autorisation** : dérivée côté serveur uniquement (résultat de contrôle, validité, révocation) ;
- la **tentative d'exécution** : qui l'a prise en charge, sous quel bail ;
- le **résultat** : effet confirmé, échec confirmé sans effet, ou effet inconnu ;
- les **réservations** : quotas tenus de façon atomique ;
- le **journal d'audit** : durable et append-only (trigger PostgreSQL).

Aucun de ces objets n'accorde de droit : ils enregistrent des droits déjà accordés
par une politique serveur. Le LLM ne peut en créer ni en modifier.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.decision_engine.models import (  # noqa: F401  (registre des FK cibles)
    ControlOutcome,
    Decision,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.goal_engine.models import Goal  # noqa: F401  (relation Task.goal)
from app.task_engine.models import Task  # noqa: F401  (FK actions.task_id)


def _utcnow() -> datetime:
    """Horodatage conscient du fuseau : la colonne est TIMESTAMPTZ."""
    return datetime.now(timezone.utc)


class AttemptStatus(str, PyEnum):
    """PENDING -> RUNNING -> SUCCEEDED | FAILED | UNKNOWN ; PENDING -> CANCELLED."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"


class EffectCertainty(str, PyEnum):
    """Un résultat ne dit jamais « peut-être » : l'incertitude est un état explicite."""

    confirmed = "confirmed"  # effet confirmé
    none = "none"  # échec confirmé sans effet
    unknown = "unknown"  # effet possible, non établi : à réconcilier


class ReservationStatus(str, PyEnum):
    HELD = "HELD"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class AuditEventType(str, PyEnum):
    CONTROL_EVALUATED = "CONTROL_EVALUATED"
    AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
    AUTHORIZATION_ISSUED = "AUTHORIZATION_ISSUED"
    AUTHORIZATION_CONSUMED = "AUTHORIZATION_CONSUMED"
    AUTHORIZATION_REVOKED = "AUTHORIZATION_REVOKED"
    ATTEMPT_CLAIMED = "ATTEMPT_CLAIMED"
    ATTEMPT_ABANDONED = "ATTEMPT_ABANDONED"
    EFFECT_CONFIRMED = "EFFECT_CONFIRMED"
    EFFECT_FAILED = "EFFECT_FAILED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
    EFFECT_RECONCILED = "EFFECT_RECONCILED"
    RESERVATION_HELD = "RESERVATION_HELD"
    RESERVATION_CONSUMED = "RESERVATION_CONSUMED"
    RESERVATION_RELEASED = "RESERVATION_RELEASED"
    STATE_TRANSITION = "STATE_TRANSITION"


class ActionRecord(Base):
    """Action structurée : le seul objet que l'Executor a le droit d'appeler.

    Toute modification d'arguments, de destinataire ou d'outil crée une nouvelle
    version (``version``) exigeant un nouveau contrôle : l'empreinte canonique
    change, donc l'autorisation précédente ne vaut plus.
    """

    __tablename__ = "actions"
    __table_args__ = (
        # Protège l'opération logique contre les doublons.
        UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_actions_workspace_idempotency"
        ),
        CheckConstraint(
            "(cost_estimate IS NULL) = (cost_unit IS NULL)",
            name="action_cost_unit_required",
        ),
        CheckConstraint("version >= 1", name="action_version_positive"),
        Index("ix_actions_decision_id", "decision_id"),
        Index(
            "ix_actions_workspace_fingerprint",
            "workspace_id",
            "canonical_fingerprint",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    objective: Mapped[str] = mapped_column(String(500), nullable=False)

    # Outil/opération enregistrés dans un catalogue versionné (Phase 4).
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    permission_required: Mapped[PermissionAction] = mapped_column(
        Enum(
            PermissionAction,
            native_enum=False,
            length=16,
            create_constraint=True,
            name="action_permission_required",
        ),
        nullable=False,
    )

    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(
            RiskLevel,
            native_enum=False,
            length=16,
            create_constraint=True,
            name="action_risk_level",
        ),
        nullable=False,
    )
    risk_reversibility: Mapped[ReversibilityLevel] = mapped_column(
        Enum(
            ReversibilityLevel,
            native_enum=False,
            length=24,
            create_constraint=True,
            name="action_risk_reversibility",
        ),
        nullable=False,
    )
    risk_impact: Mapped[ImpactType] = mapped_column(
        Enum(
            ImpactType,
            native_enum=False,
            length=16,
            create_constraint=True,
            name="action_risk_impact",
        ),
        nullable=False,
    )

    # Un coût inconnu n'est pas nul : l'absence de borne est NULL + unité NULL.
    cost_estimate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    cost_unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    canonical_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class ExecutionAuthorization(Base):
    """Autorisation dérivée du contrôle serveur. Jamais fournie par le client ni le LLM.

    Conserve le résultat (ALLOW/DENY/ESCALATE/STOP), le motif stable, l'empreinte de
    l'action autorisée, la version de politique, la validité, la consommation et une
    éventuelle référence d'approbation.
    """

    __tablename__ = "execution_authorizations"
    __table_args__ = (
        Index("ix_exec_auth_action_id", "action_id"),
        Index("ix_exec_auth_decision_id", "decision_id"),
        CheckConstraint(
            "expires_at IS NULL OR expires_at >= issued_at",
            name="authorization_expiry_after_issue",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )
    action_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )

    outcome: Mapped[ControlOutcome] = mapped_column(
        Enum(
            ControlOutcome,
            native_enum=False,
            length=8,
            create_constraint=True,
            name="authorization_outcome",
        ),
        nullable=False,
    )
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # L'autorisation porte sur une empreinte et une version précises de l'action.
    action_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    action_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoke_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    approval_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    approval_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class ExecutionAttempt(Base):
    """Tentative d'exécution d'une action autorisée.

    La prise en charge est exclusive : ``PENDING -> RUNNING`` via un UPDATE
    conditionnel avec bail. Un bail expiré ne prouve pas l'absence d'effet :
    la tentative passe à ``UNKNOWN`` et exige une réconciliation.
    """

    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint(
            "authorization_id", "attempt_number", name="uq_attempt_authorization_number"
        ),
        Index("ix_attempt_action_id", "action_id"),
        Index("ix_attempt_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    action_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    authorization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_authorizations.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )

    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    status: Mapped[AttemptStatus] = mapped_column(
        Enum(
            AttemptStatus,
            native_enum=False,
            length=16,
            create_constraint=True,
            name="attempt_status",
        ),
        default=AttemptStatus.PENDING,
        server_default=AttemptStatus.PENDING.value,
        nullable=False,
    )

    lease_owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_reference: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class ExecutionResultRecord(Base):
    """Résultat d'une tentative : effet confirmé, échec sans effet, ou effet inconnu.

    Un résultat ``unknown`` interdit la répétition aveugle ; il ne se résout que par
    une réconciliation portant une référence de preuve.
    """

    __tablename__ = "execution_results"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_execution_result_attempt"),
        CheckConstraint(
            "(cost_amount IS NULL) = (cost_unit IS NULL)",
            name="execution_result_cost_unit_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="CASCADE"), nullable=False
    )

    effect: Mapped[EffectCertainty] = mapped_column(
        Enum(
            EffectCertainty,
            native_enum=False,
            length=16,
            create_constraint=True,
            name="execution_effect",
        ),
        nullable=False,
    )
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    output_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    provider_reference: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    evidence_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    cost_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    cost_unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class ActionReservation(Base):
    """Réservation de quota attachée à une action autorisée (INV-08).

    Le solde n'est jamais copié : les unités tenues sont additionnées sous verrou
    consultatif PostgreSQL, ce qui rend la vérification atomique entre workers.
    """

    __tablename__ = "action_reservations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "resource",
            "idempotency_key",
            name="uq_reservation_logical_operation",
        ),
        CheckConstraint("units > 0", name="reservation_units_positive"),
        Index("ix_reservation_ledger", "workspace_id", "resource", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    action_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    authorization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_authorizations.id", ondelete="CASCADE"), nullable=False
    )

    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    units: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            native_enum=False,
            length=16,
            create_constraint=True,
            name="reservation_status",
        ),
        default=ReservationStatus.HELD,
        server_default=ReservationStatus.HELD.value,
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    release_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class AuditEntry(Base):
    """Journal d'audit durable et append-only (INV-11).

    Conserve identifiants corrélés, versions de politique, motif du contrôle,
    empreinte d'action, transitions, acteur et horodatages. Le payload est filtré
    des secrets avant écriture. La migration ``005`` installe un trigger qui refuse
    toute mise à jour ou suppression : le journal ne peut pas être réécrit par un
    agent exécutant.
    """

    __tablename__ = "audit_entries"
    __table_args__ = (
        Index("ix_audit_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_decision_id", "decision_id"),
        Index("ix_audit_attempt_id", "attempt_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(
            AuditEventType,
            native_enum=False,
            length=32,
            create_constraint=True,
            name="audit_event_type",
        ),
        nullable=False,
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True
    )
    action_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("actions.id", ondelete="SET NULL"), nullable=True
    )
    authorization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("execution_authorizations.id", ondelete="SET NULL"), nullable=True
    )
    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("execution_attempts.id", ondelete="SET NULL"), nullable=True
    )

    reason_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    action_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class ResourceBudget(Base):
    """Borne persistante d'un quota partagé par workspace (INV-08, INV-13).

    Le solde n'est pas stocké : il est dérivé des réservations. Une ressource sans
    budget déclaré n'est pas « illimitée » — la réservation est refusée avec un
    motif explicite (``QUOTA_UNKNOWN``), car une absence de preuve n'est pas une
    autorisation.
    """

    __tablename__ = "resource_budgets"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "resource", name="uq_budget_workspace_resource"
        ),
        CheckConstraint("limit_units >= 0", name="budget_limit_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    limit_units: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    period: Mapped[str] = mapped_column(String(50), default="lifetime", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
