"""Create durable tenant-scoped Concierge execution traces.

Revision ID: 013_concierge_traces
Revises: 012_concierge_leads
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa


revision = "013_concierge_traces"
down_revision = "012_concierge_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concierge_execution_traces",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("site_key", sa.String(length=63), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="chat"),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("tools_called", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("result_status", sa.String(length=30), nullable=False, server_default="ok"),
        sa.Column("lead_captured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("transferred_to_rockib", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_concierge_traces_site_created",
        "concierge_execution_traces",
        ["site_key", "created_at"],
    )
    op.create_index(
        "ix_concierge_traces_conv_created",
        "concierge_execution_traces",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_concierge_traces_conv_created", table_name="concierge_execution_traces")
    op.drop_index("ix_concierge_traces_site_created", table_name="concierge_execution_traces")
    op.drop_table("concierge_execution_traces")
