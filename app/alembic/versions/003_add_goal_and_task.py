"""add goal and task models

Revision ID: 003_add_goal_and_task
Revises: 002_default_autonomy
Create Date: 2026-09-17 19:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "003_add_goal_and_task"
down_revision = "002_default_autonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create goals table (which creates the goal_status enum)
    op.create_table(
        "goals",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("objective", sa.String(500), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "PLANNING", "ACTIVE", "PAUSED", "COMPLETED", "FAILED", "CANCELLED", name="goal_status"), nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("requested_autonomy_level", sa.SmallInteger(), nullable=False),
        sa.Column("applied_autonomy_level", sa.SmallInteger(), nullable=False),
        sa.Column("parent_goal_id", sa.UUID(), sa.ForeignKey("goals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("goal_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 2. Create tasks table (which creates the task_status enum)
    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("goal_id", sa.UUID(), sa.ForeignKey("goals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_id", sa.UUID(), sa.ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "READY", "ACTIVE", "COMPLETED", "FAILED", "BLOCKED", name="task_status"), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("tasks")
    op.execute("DROP TYPE IF EXISTS task_status")
    op.drop_table("goals")
    op.execute("DROP TYPE IF EXISTS goal_status")
