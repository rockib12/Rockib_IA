"""Create durable tenant-scoped Concierge leads.

Revision ID: 012_concierge_leads
Revises: 011_workspace_credentials
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa


revision = "012_concierge_leads"
down_revision = "011_workspace_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concierge_leads",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("site_key", sa.String(length=63), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("phone_number", sa.String(length=30), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="received"),
        sa.Column("consent_version", sa.String(length=20), nullable=False, server_default="2026-10"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_concierge_leads_site_created",
        "concierge_leads",
        ["site_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_concierge_leads_site_created", table_name="concierge_leads")
    op.drop_table("concierge_leads")

