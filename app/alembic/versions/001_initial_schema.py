"""Initial schema — Rockib AI Phase 0

Creates:
- ENUMs: workspace_type, user_role, memory_type, memory_status,
  arbitration_rule, dominant_source, risk_level, reversibility_level,
  impact_type, permission_action, decision_status
- Tables: workspaces, users, workspace_memberships, memories, agents,
  decision_domain_config, decisions, decision_outcomes
- Trigger function set_updated_at() + triggers on every table
- Indexes on memories and decisions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None




# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

\

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


# list of all ENUM names used in the schema
ENUM_NAMES: Sequence[str] = [
    "workspace_type",
    "user_role",
    "memory_type",
    "memory_status",
    "arbitration_rule",
    "dominant_source",
    "risk_level",
    "reversibility_level",
    "impact_type",
    "permission_action",
    "decision_status",
]


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    # --- Trigger function ----------------------------------------------
    op.execute(
        """CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql"""
    )

    # --- Tables --------------------------------------------------------
    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.VARCHAR(150), nullable=False),
        sa.Column("slug", sa.VARCHAR(50), unique=True, nullable=False),
        sa.Column("type", sa.Enum("owner", "client", name="workspace_type"), nullable=False, server_default="client"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.VARCHAR(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.VARCHAR(255), nullable=False),
        sa.Column("first_name", sa.VARCHAR(100)),
        sa.Column("last_name", sa.VARCHAR(100)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "workspace_memberships",
        sa.Column("workspace_id", sa.UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.Enum("owner", "admin", "viewer", name="user_role"), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.VARCHAR(150), nullable=False),
        sa.Column("role", sa.VARCHAR(100)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "memories",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Enum("fact", "preference", "decision_rule", "experience", "project_memory", name="memory_type"), nullable=False),
        sa.Column("status", sa.Enum("supposed", "deduced", "known", "verified", name="memory_status"), nullable=False, server_default="supposed"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("confidence_level", sa.NUMERIC(4, 3), nullable=False),
        sa.Column("importance_level", sa.NUMERIC(4, 3), nullable=False),
        sa.Column("last_accessed_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "decision_domain_config",
        sa.Column("id", sa.INTEGER, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.VARCHAR(100), nullable=False),
        sa.Column("permission_action", sa.Enum("READ", "CREATE", "UPDATE", "DELETE", "SEND", "PUBLISH", "SPEND", name="permission_action"), nullable=False),
        sa.Column("arbitration_rule", sa.Enum("cognitive_wins", "intelligence_wins", "consensus_required", "escalate", name="arbitration_rule"), nullable=False),
        sa.Column("base_risk_level", sa.Enum("low", "medium", "high", "critical", name="risk_level"), nullable=False),
        sa.Column("base_reversibility", sa.Enum("reversible", "partially_reversible", "irreversible", name="reversibility_level"), nullable=False),
        sa.Column("base_impact", sa.Enum("internal", "client_facing", "financial", "reputational", name="impact_type"), nullable=False),
        sa.Column("disagreement_threshold", sa.NUMERIC(3, 2), nullable=False, server_default="0.40"),
        sa.Column("approval_timeout_minutes", sa.INTEGER, nullable=False, server_default="60"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "domain", "permission_action"),
    )
    op.create_table(
        "decisions",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.UUID, sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_config_id", sa.INTEGER, sa.ForeignKey("decision_domain_config.id")),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("situation", sa.Text, nullable=False),
        sa.Column("proposed_action", sa.Text, nullable=False),
        sa.Column("cognitive_action", sa.Text),
        sa.Column("cognitive_confidence", sa.NUMERIC(4, 3)),
        sa.Column("intelligence_action", sa.Text),
        sa.Column("intelligence_confidence", sa.NUMERIC(4, 3)),
        sa.Column("dominant_source", sa.Enum("cognitive", "intelligence", "consensus", name="dominant_source")),
        sa.Column("disagreement", sa.NUMERIC(4, 3)),
        sa.Column("risk_level", sa.Enum("low", "medium", "high", "critical", name="risk_level", create_type=False), nullable=False),
        sa.Column("risk_reversibility", sa.Enum("reversible", "partially_reversible", "irreversible", name="reversibility_level", create_type=False), nullable=False),
        sa.Column("risk_impact", sa.Enum("internal", "client_facing", "financial", "reputational", name="impact_type", create_type=False), nullable=False),
        sa.Column("risk_ai_adjusted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("requested_autonomy_level", sa.SMALLINT, nullable=False),
        sa.Column("applied_autonomy_level", sa.SMALLINT, nullable=False),
        sa.Column("permission_required", sa.Enum("READ", "CREATE", "UPDATE", "DELETE", "SEND", "PUBLISH", "SPEND", name="permission_action", create_type=False), nullable=False),
        sa.Column("permission_granted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("approval_required", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("approval_reason", sa.Text),
        sa.Column("approved_by", sa.UUID, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("escalated_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("final_action", sa.Text),
        sa.Column("final_confidence", sa.NUMERIC(4, 3)),
        sa.Column("status", sa.Enum("pending_approval", "executed", "rejected", "escalated", "expired", name="decision_status"), nullable=False, server_default="pending_approval"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint("applied_autonomy_level <= requested_autonomy_level", name="applied_never_exceeds_requested"),
        sa.CheckConstraint("requested_autonomy_level BETWEEN 0 AND 5", name="requested_autonomy_range"),
        sa.CheckConstraint("applied_autonomy_level BETWEEN 0 AND 5", name="applied_autonomy_range"),
    )
    op.create_table(
        "decision_outcomes",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("decision_id", sa.UUID, sa.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result_summary", sa.Text, nullable=False),
        sa.Column("success", sa.Boolean),
        sa.Column("lesson", sa.Text),
        sa.Column("cognitive_was_right", sa.Boolean),
        sa.Column("intelligence_was_right", sa.Boolean),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # --- Indexes -------------------------------------------------------
    op.create_index("idx_memories_workspace_type", "memories", ["workspace_id", "type"])
    op.create_index("idx_memories_status", "memories", ["status"])
    op.create_index("idx_memories_last_accessed", "memories", ["last_accessed_at"])
    op.create_index("idx_memories_metadata", "memories", ["metadata"], postgresql_using="gin")
    op.create_index("idx_decisions_workspace_status", "decisions", ["workspace_id", "status"])
    op.create_index("idx_decisions_agent", "decisions", ["agent_id"])
    op.create_index(
        "idx_decisions_pending_timeout",
        "decisions",
        ["status", "created_at"],
        postgresql_where=sa.text("status = 'pending_approval'"),
    )
    op.create_index("idx_outcomes_decision", "decision_outcomes", ["decision_id"])

    # --- Triggers ------------------------------------------------------
    for tbl in [
        "workspaces", "users", "workspace_memberships",
        "agents", "memories", "decision_domain_config", "decisions",
    ]:
        op.execute(
            f"""CREATE TRIGGER trg_{tbl}_updated_at
                BEFORE UPDATE ON {tbl}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at()"""
        )


def downgrade() -> None:
    bind = op.get_bind()

    for tbl in [
        "workspaces", "users", "workspace_memberships",
        "agents", "memories", "decision_domain_config", "decisions",
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tbl}_updated_at ON {tbl}")

    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    op.drop_index("idx_outcomes_decision", table_name="decision_outcomes")
    op.drop_index("idx_decisions_pending_timeout", table_name="decisions")
    op.drop_index("idx_decisions_agent", table_name="decisions")
    op.drop_index("idx_decisions_workspace_status", table_name="decisions")
    op.drop_index("idx_memories_metadata", table_name="memories")
    op.drop_index("idx_memories_last_accessed", table_name="memories")
    op.drop_index("idx_memories_status", table_name="memories")
    op.drop_index("idx_memories_workspace_type", table_name="memories")

    op.drop_table("decision_outcomes")
    op.drop_table("decisions")
    op.drop_table("decision_domain_config")
    op.drop_table("memories")
    op.drop_table("agents")
    op.drop_table("workspace_memberships")
    op.drop_table("users")
    op.drop_table("workspaces")

    for enum in ENUM_NAMES:
        op.execute(f"DROP TYPE IF EXISTS {enum}")




