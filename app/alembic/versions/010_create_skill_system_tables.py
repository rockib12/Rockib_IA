"""Create skill system tables (skills, skill_versions, workspace_skills, agent_skills).

Revision ID: 010_create_skill_system_tables
Revises: 009_task_graph_and_cancelled
Create Date: 2026-09-28 01:25:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "010_create_skill_system_tables"
down_revision = "009_task_graph_and_cancelled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. skills
    op.create_table(
        "skills",
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
            nullable=True,
            index=True,
        ),
        sa.Column("slug", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="general"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_skills_workspace_slug"),
    )

    # 2. skill_versions
    op.create_table(
        "skill_versions",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "skill_id",
            sa.UUID(),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("manifest_version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("semver", sa.String(50), nullable=False),
        sa.Column("content_hash", sa.String(100), nullable=False, index=True),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("required_tools", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("required_skills", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("suggested_risk", sa.String(20), nullable=False, server_default="low"),
        sa.Column("conflicts_with", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("skill_id", "semver", name="uq_skill_versions_skill_semver"),
        sa.UniqueConstraint("content_hash", name="uq_skill_versions_content_hash"),
    )

    # 3. workspace_skills
    op.create_table(
        "workspace_skills",
        sa.Column(
            "workspace_id",
            sa.UUID(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id",
            sa.UUID(),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "enabled_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 4. agent_skills
    op.create_table(
        "agent_skills",
        sa.Column(
            "agent_id",
            sa.UUID(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_version_id",
            sa.UUID(),
            sa.ForeignKey("skill_versions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "granted_by_agent_id",
            sa.UUID(),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "granted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_skills")
    op.drop_table("workspace_skills")
    op.drop_table("skill_versions")
    op.drop_table("skills")
