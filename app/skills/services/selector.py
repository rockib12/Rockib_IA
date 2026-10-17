"""SkillSelector service for Rockib AI.

Responsibilities:
- Assign skills to agents with monotonic parent-child restriction (SKILL-INV-02).
- JIT resolution of effective skills for a specific task (§11).
- Prevent prompt bloat by budgeting context (max 2 skills).
- Format ActiveSkillContext for RationalAgent prompt injection.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.skills.models import AgentSkill, Skill, SkillVersion, WorkspaceSkill
from app.skills.schemas import ActiveSkillContext, SkillStatus
from app.skills.services.registry import MissingTransitiveSkillDependencyError, SkillRegistry

logger = logging.getLogger(__name__)


class SkillDelegationError(Exception):
    """Raised when delegation violates monotonic non-elevation rules."""
    pass


class SkillConflictError(Exception):
    """Raised when mutually exclusive skills conflict."""
    pass


class SkillSelector:
    """Manages skill assignment and Just-in-Time task resolution."""

    @staticmethod
    async def get_agent_active_skills(
        session: AsyncSession,
        agent_id: UUID,
    ) -> List[SkillVersion]:
        """Fetch all active SkillVersions formally assigned to an agent."""
        stmt = (
            select(SkillVersion)
            .join(AgentSkill, AgentSkill.skill_version_id == SkillVersion.id)
            .where(
                and_(
                    AgentSkill.agent_id == agent_id,
                    SkillVersion.status == SkillStatus.ACTIVE.value,
                )
            )
            .options(selectinload(SkillVersion.skill))
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @classmethod
    async def assign_skill_to_agent(
        cls,
        session: AsyncSession,
        agent_id: UUID,
        skill_version: SkillVersion,
        granted_by_agent_id: Optional[UUID] = None,
    ) -> AgentSkill:
        """Assigns a skill version to an agent.

        Enforces SKILL-INV-02 (Monotonic Delegation):
        If granted_by_agent_id is provided, verifies that parent agent holds
        an active version of this skill.
        """
        if granted_by_agent_id:
            parent_skills = await cls.get_agent_active_skills(session, granted_by_agent_id)
            parent_skill_ids = {s.skill_id for s in parent_skills}
            if skill_version.skill_id not in parent_skill_ids:
                raise SkillDelegationError(
                    f"Monotonic delegation violation: Child agent '{agent_id}' cannot receive skill "
                    f"'{skill_version.skill_id}' because parent agent '{granted_by_agent_id}' does not possess it."
                )

        # Check if already assigned
        stmt = select(AgentSkill).where(
            and_(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_version_id == skill_version.id,
            )
        )
        res = await session.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return existing

        assignment = AgentSkill(
            agent_id=agent_id,
            skill_version_id=skill_version.id,
            granted_by_agent_id=granted_by_agent_id,
        )
        session.add(assignment)
        await session.flush()
        return assignment

    @staticmethod
    def are_skills_conflicting(v1: SkillVersion, v2: SkillVersion) -> bool:
        """Checks if two skill versions are mutually exclusive (symmetrical)."""
        slug1 = v1.skill.slug if (hasattr(v1, "skill") and v1.skill) else str(v1.skill_id)
        slug2 = v2.skill.slug if (hasattr(v2, "skill") and v2.skill) else str(v2.skill_id)
        conflicts1 = set(v1.conflicts_with or [])
        conflicts2 = set(v2.conflicts_with or [])
        return slug2 in conflicts1 or slug1 in conflicts2

    @classmethod
    def verify_no_conflicts(cls, versions: List[SkillVersion]) -> None:
        """Verifies that no two skills in the given list conflict with each other."""
        n = len(versions)
        for i in range(n):
            for j in range(i + 1, n):
                if cls.are_skills_conflicting(versions[i], versions[j]):
                    slug_i = versions[i].skill.slug if versions[i].skill else str(versions[i].skill_id)
                    slug_j = versions[j].skill.slug if versions[j].skill else str(versions[j].skill_id)
                    raise SkillConflictError(
                        f"Mutual exclusion conflict between skill '{slug_i}' and skill '{slug_j}'."
                    )

    @classmethod
    async def select_skills_for_task(
        cls,
        session: AsyncSession,
        agent_id: UUID,
        workspace_id: UUID,
        task_skill_hint: Optional[str] = None,
        task_description: Optional[str] = None,
        max_skills: int = 2,
    ) -> List[ActiveSkillContext]:
        r"""Selects and formats the minimal effective skill set for a specific task.

        Applies the formula:
        effective_skills = ASSIGNED(Agent) ∩ AVAILABLE(Workspace) \ REVOKED
        """
        assigned_versions = await cls.get_agent_active_skills(session, agent_id)
        if not assigned_versions:
            return []

        # Check workspace enablement for non-system skills
        eligible_versions: List[SkillVersion] = []
        for ver in assigned_versions:
            skill = ver.skill
            if skill.is_system:
                eligible_versions.append(ver)
            else:
                # Check workspace_skills
                ws_stmt = select(WorkspaceSkill).where(
                    and_(
                        WorkspaceSkill.workspace_id == workspace_id,
                        WorkspaceSkill.skill_id == skill.id,
                        WorkspaceSkill.is_enabled == True,  # noqa: E712
                    )
                )
                ws_res = await session.execute(ws_stmt)
                if ws_res.scalars().first():
                    eligible_versions.append(ver)

        if not eligible_versions:
            return []

        # Scoring heuristics to choose top matching skills
        scored_skills: List[tuple[int, SkillVersion]] = []
        hint_lower = (task_skill_hint or "").lower().strip()
        desc_lower = (task_description or "").lower().strip()

        for ver in eligible_versions:
            score = 0
            slug = ver.skill.slug.lower()
            name = ver.skill.name.lower()

            # Exact hint match (highest priority)
            if hint_lower and (hint_lower == slug or hint_lower in slug):
                score += 100

            # Description keyword matching
            if desc_lower:
                if slug in desc_lower:
                    score += 50
                if name in desc_lower:
                    score += 30
                # Match required tools with description
                for tool in ver.required_tools:
                    if tool.lower() in desc_lower:
                        score += 15

            scored_skills.append((score, ver))

        # Sort descending by score, tie-breaking deterministically by slug ascending
        scored_skills.sort(key=lambda x: (-x[0], x[1].skill.slug))

        # Budget context: Take up to max_skills while rejecting mutually exclusive conflicts
        selected_versions: List[SkillVersion] = []
        conflicting_slugs: set[str] = set()

        for score, ver in scored_skills:
            if len(selected_versions) >= max_skills:
                break
            slug = ver.skill.slug
            # Check mutual exclusion against already selected skills
            ver_conflicts = set(ver.conflicts_with or [])
            if slug in conflicting_slugs or any(s.skill.slug in ver_conflicts for s in selected_versions):
                logger.info("Skill '%s' rejected from selection due to mutual exclusion conflict.", slug)
                continue

            selected_versions.append(ver)
            conflicting_slugs.update(ver_conflicts)

        # Enforce SKILL-INV-09: Transitive dependency satisfaction
        eligible_slugs = {ev.skill.slug for ev in eligible_versions}
        for v in selected_versions:
            if v.required_skills:
                transitive_deps = await SkillRegistry.resolve_transitive_dependencies(
                    session, v, workspace_id=workspace_id
                )
                for dep in transitive_deps:
                    if dep.skill.slug not in eligible_slugs:
                        raise MissingTransitiveSkillDependencyError(
                            f"Skill '{v.skill.slug}' requires transitive dependency '{dep.skill.slug}' which is not assigned to agent '{agent_id}'."
                        )

        # Format into ActiveSkillContext
        return [
            ActiveSkillContext(
                id=v.skill.slug,
                name=v.skill.name,
                semver=v.semver,
                content_hash=v.content_hash,
                instructions=v.instructions,
                constraints=v.constraints or [],
                required_tools=v.required_tools or [],
            )
            for v in selected_versions
        ]
