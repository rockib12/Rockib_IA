"""Phase 2 — exécution fiable : action, autorisation, tentative, résultat, réservation, audit.

Revision ID: 005_execution_reliable
Revises: 004_decision_control
"""
from alembic import op
import sqlalchemy as sa

from app.decision_engine.models import (
    ControlOutcome,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.execution.models import (
    AttemptStatus,
    AuditEventType,
    EffectCertainty,
    ReservationStatus,
)

revision = "005_execution_reliable"
down_revision = "004_decision_control"
branch_labels = None
depends_on = None


def _enum(enum_cls, name: str, length: int) -> sa.Enum:
    """Enum stocké en VARCHAR + contrainte CHECK (pas de type PostgreSQL natif).

    Les valeurs viennent des Enums Python pour éviter toute divergence entre le
    modèle et la migration.
    """
    return sa.Enum(
        *[member.value for member in enum_cls],
        native_enum=False,
        length=length,
        name=name,
        create_constraint=True,
    )


def upgrade() -> None:
    # 1. Action structurée ---------------------------------------------------
    op.create_table(
        "actions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_id", sa.UUID(), sa.ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("objective", sa.String(500), nullable=False),
        sa.Column("tool", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("permission_required", _enum(PermissionAction, "action_permission_required", 16), nullable=False),
        sa.Column("risk_level", _enum(RiskLevel, "action_risk_level", 16), nullable=False),
        sa.Column("risk_reversibility", _enum(ReversibilityLevel, "action_risk_reversibility", 24), nullable=False),
        sa.Column("risk_impact", _enum(ImpactType, "action_risk_impact", 16), nullable=False),
        sa.Column("cost_estimate", sa.Numeric(18, 6), nullable=True),
        sa.Column("cost_unit", sa.String(20), nullable=True),
        sa.Column("canonical_fingerprint", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_actions_workspace_idempotency"),
        sa.CheckConstraint("(cost_estimate IS NULL) = (cost_unit IS NULL)", name="action_cost_unit_required"),
        sa.CheckConstraint("version >= 1", name="action_version_positive"),
    )
    op.create_index("ix_actions_decision_id", "actions", ["decision_id"])
    op.create_index("ix_actions_workspace_fingerprint", "actions", ["workspace_id", "canonical_fingerprint"])

    # 2. Autorisation --------------------------------------------------------
    op.create_table(
        "execution_authorizations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("decision_id", sa.UUID(), sa.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", sa.UUID(), sa.ForeignKey("actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome", _enum(ControlOutcome, "authorization_outcome", 8), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("action_fingerprint", sa.String(64), nullable=False),
        sa.Column("action_version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=True),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(100), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approval_reference", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("expires_at IS NULL OR expires_at >= issued_at", name="authorization_expiry_after_issue"),
    )
    op.create_index("ix_exec_auth_action_id", "execution_authorizations", ["action_id"])
    op.create_index("ix_exec_auth_decision_id", "execution_authorizations", ["decision_id"])

    # 3. Tentative d'exécution ----------------------------------------------
    op.create_table(
        "execution_attempts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("action_id", sa.UUID(), sa.ForeignKey("actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("authorization_id", sa.UUID(), sa.ForeignKey("execution_authorizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", _enum(AttemptStatus, "attempt_status", 16), nullable=False, server_default=AttemptStatus.PENDING.value),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("provider_reference", sa.String(150), nullable=True),
        sa.Column("claimed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("authorization_id", "attempt_number", name="uq_attempt_authorization_number"),
    )
    op.create_index("ix_attempt_action_id", "execution_attempts", ["action_id"])
    op.create_index("ix_attempt_status_lease", "execution_attempts", ["status", "lease_expires_at"])

    # 4. Résultat ------------------------------------------------------------
    op.create_table(
        "execution_results",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("attempt_id", sa.UUID(), sa.ForeignKey("execution_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("effect", _enum(EffectCertainty, "execution_effect", 16), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider_reference", sa.String(150), nullable=True),
        sa.Column("evidence_reference", sa.String(255), nullable=True),
        sa.Column("cost_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("cost_unit", sa.String(20), nullable=True),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("attempt_id", name="uq_execution_result_attempt"),
        sa.CheckConstraint("(cost_amount IS NULL) = (cost_unit IS NULL)", name="execution_result_cost_unit_required"),
    )

    # 5. Réservation de quota ------------------------------------------------
    op.create_table(
        "action_reservations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", sa.UUID(), sa.ForeignKey("actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("authorization_id", sa.UUID(), sa.ForeignKey("execution_authorizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("units", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", _enum(ReservationStatus, "reservation_status", 16), nullable=False, server_default=ReservationStatus.HELD.value),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("released_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "resource", "idempotency_key", name="uq_reservation_logical_operation"),
        sa.CheckConstraint("units > 0", name="reservation_units_positive"),
    )
    op.create_index("ix_reservation_ledger", "action_reservations", ["workspace_id", "resource", "status"])

    # 5bis. Borne de quota ---------------------------------------------------
    op.create_table(
        "resource_budgets",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("limit_units", sa.Numeric(18, 6), nullable=False),
        sa.Column("period", sa.String(50), nullable=False, server_default="lifetime"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "resource", name="uq_budget_workspace_resource"),
        sa.CheckConstraint("limit_units >= 0", name="budget_limit_non_negative"),
    )

    # 6. Audit durable (append-only) ----------------------------------------
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("event_type", _enum(AuditEventType, "audit_event_type", 32), nullable=False),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_id", sa.UUID(), sa.ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_id", sa.UUID(), sa.ForeignKey("actions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("authorization_id", sa.UUID(), sa.ForeignKey("execution_authorizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempt_id", sa.UUID(), sa.ForeignKey("execution_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason_code", sa.String(100), nullable=True),
        sa.Column("action_fingerprint", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(100), nullable=True),
        sa.Column("actor", sa.String(100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_workspace_created", "audit_entries", ["workspace_id", "created_at"])
    op.create_index("ix_audit_decision_id", "audit_entries", ["decision_id"])
    op.create_index("ix_audit_attempt_id", "audit_entries", ["attempt_id"])

    # Le journal est protégé contre les modifications par les agents exécutants.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION rockib_audit_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_entries est append-only : % refuse', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_entries_append_only
        BEFORE UPDATE OR DELETE ON audit_entries
        FOR EACH ROW EXECUTE FUNCTION rockib_audit_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_entries_append_only ON audit_entries")
    op.execute("DROP FUNCTION IF EXISTS rockib_audit_append_only()")
    op.drop_table("audit_entries")

    op.drop_table("resource_budgets")
    op.drop_table("action_reservations")
    op.drop_table("execution_results")
    op.drop_table("execution_attempts")
    op.drop_table("execution_authorizations")
    op.drop_table("actions")