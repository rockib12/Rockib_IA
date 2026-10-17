"""SQLAlchemy models for Rockib AI Skill System.

Tables:
- skills: Canonical identity and workspace ownership.
- skill_versions: Immutable, sealed versions with canonical content_hash SHA-256.
- workspace_skills: Workspace level enablement / authorization boundary.
- agent_skills: Agent level delegation with parental provenance.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Contrainte d'unicité : slug unique par workspace (et pour is_system=True avec workspace_id=None)
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_skills_workspace_slug"),
    )

    # Relations
    versions: Mapped[List["SkillVersion"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan", order_by="SkillVersion.created_at.desc()", lazy="selectin"
    )
    workspace_activations: Mapped[List["WorkspaceSkill"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan", lazy="selectin"
    )


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    manifest_version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    semver: Mapped[str] = mapped_column(String(50), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    suggested_risk: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    conflicts_with: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("skill_id", "semver", name="uq_skill_versions_skill_semver"),
        UniqueConstraint("content_hash", name="uq_skill_versions_content_hash"),
    )

    # Relations
    skill: Mapped["Skill"] = relationship(back_populates="versions", lazy="joined")
    agent_assignments: Mapped[List["AgentSkill"]] = relationship(
        back_populates="skill_version", cascade="all, delete-orphan", lazy="selectin"
    )


class WorkspaceSkill(Base):
    __tablename__ = "workspace_skills"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relations
    skill: Mapped["Skill"] = relationship(back_populates="workspace_activations", lazy="joined")


class AgentSkill(Base):
    __tablename__ = "agent_skills"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    skill_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skill_versions.id", ondelete="RESTRICT"), primary_key=True
    )
    granted_by_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relations
    skill_version: Mapped["SkillVersion"] = relationship(back_populates="agent_assignments", lazy="joined")
