"""Create workspace_credentials table (Phase A - Multi-tenant Secret Vault).

Revision ID: 011_create_workspace_credentials_table
Revises: 010_create_skill_system_tables
Create Date: 2026-09-29 18:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "011_workspace_credentials"
down_revision = "010_create_skill_system_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_credentials",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            sa.UUID(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("key_alias", sa.String(100), nullable=False, server_default="default"),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("secret_fingerprint", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "key_alias",
            name="uq_workspace_credentials_provider_alias",
        ),
    )
    op.create_index(
        "ix_workspace_credentials_workspace_provider",
        "workspace_credentials",
        ["workspace_id", "provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_credentials_workspace_provider", table_name="workspace_credentials")
    op.drop_table("workspace_credentials")
