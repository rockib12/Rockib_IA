"""Persist phase-one control outcomes without changing historical status enums.

Revision ID: 004_decision_control
Revises: 003_add_goal_and_task
"""
from alembic import op
import sqlalchemy as sa

revision = "004_decision_control"
down_revision = "003_add_goal_and_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decision_domain_config",
        sa.Column("execution_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "decision_domain_config",
        sa.Column("max_autonomy_level", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "policy_autonomy_range", "decision_domain_config",
        "max_autonomy_level BETWEEN 0 AND 5",
    )
    op.add_column(
        "decisions",
        sa.Column("control_outcome", sa.String(8), nullable=False, server_default="STOP"),
    )
    op.create_check_constraint(
        "control_outcome", "decisions",
        "control_outcome IN ('ALLOW', 'DENY', 'ESCALATE', 'STOP')",
    )
    op.add_column(
        "decisions",
        sa.Column("control_reason", sa.String(100), nullable=False, server_default="NOT_EVALUATED"),
    )
    op.add_column(
        "decisions", sa.Column("action_fingerprint", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("decisions", "action_fingerprint")
    op.drop_column("decisions", "control_reason")
    op.drop_constraint("control_outcome", "decisions", type_="check")
    op.drop_column("decisions", "control_outcome")
    op.drop_constraint("policy_autonomy_range", "decision_domain_config", type_="check")
    op.drop_column("decision_domain_config", "max_autonomy_level")
    op.drop_column("decision_domain_config", "execution_enabled")