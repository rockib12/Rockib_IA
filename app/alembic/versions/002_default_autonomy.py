"""add default_autonomy_level to agents

Revision ID: 002_default_autonomy
Revises: 001
Create Date: 2026-09-16 08:55:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "002_default_autonomy"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "default_autonomy_level",
            sa.SmallInteger(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "default_autonomy_level")
