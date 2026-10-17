"""SkillRegistry service for Rockib AI.

Responsibilities:
- Register and validate SkillManifest.
- Enforce cryptographic immutability (SKILL-INV-08).
- Detect and prevent tampering.
- Calculate bounded transitive dependency closures (SKILL-INV-09).
"""
from __future__ import annotations

import logging
from typing import List, Optional, Set
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.skills.models import Skill, SkillVersion, WorkspaceSkill
from app.skills.schemas import (
    SkillManifest,
    SkillStatus,
    compute_canonical_content_hash,
    verify_skill_manifest_hash,
)

logger = logging.getLogger(__name__)


class SkillRegistryError(Exception):
    """Base exception for skill registry operations."""
    pass


class SkillHashTamperingError(SkillRegistryError):
    """Raised when manifest hash does not match computed canonical hash."""
    pass


class SkillVersionImmutableViolationError(SkillRegistryError):
    """Raised when an existing semver version is submitted with a different content_hash."""
    pass


class SkillDependencyCycleError(SkillRegistryError):
    """Raised when a cyclical dependency is detected among skills."""
    pass


class MissingTransitiveSkillDependencyError(SkillRegistryError):
    """Raised when a required skill dependency is missing or unresolvable."""
    pass


class SkillRegistry:
    """Manages skill declarations, versioning, and dependency graphs."""

    @staticmethod
    async def register_manifest(
        session: AsyncSession,
        manifest: SkillManifest,
        workspace_id: Optional[UUID] = None,
    ) -> SkillVersion:
        """Register a validated SkillManifest into the database.

        Guarantees:
        - Cryptographic verification of content_hash.
        - Idempotency if identical (version, content_hash) already exists.
        - Strict rejection of version-hash collisions (SKILL-INV-08).
        """
        # 1. Verify cryptographic seal
        if not verify_skill_manifest_hash(manifest):
            computed = compute_canonical_content_hash(manifest.knowledge, manifest.dependencies)
            raise SkillHashTamperingError(
                f"Manifest for '{manifest.identity.id}' has invalid content_hash '{manifest.versioning.content_hash}'. "
                f"Expected canonical hash: '{computed}'."
            )

        # 2. Scope resolution
        target_ws_id = None if manifest.identity.is_system else workspace_id

        # 3. Locate or create Skill entity
        stmt = select(Skill).where(
            and_(
                Skill.slug == manifest.identity.id,
                Skill.workspace_id == target_ws_id,
                Skill.is_system == manifest.identity.is_system,
            )
        )
        result = await session.execute(stmt)
        skill = result.scalars().first()

        if not skill:
            skill = Skill(
                slug=manifest.identity.id,
                name=manifest.metadata.name,
                category=manifest.metadata.category,
                is_system=manifest.identity.is_system,
                workspace_id=target_ws_id,
            )
            session.add(skill)
            await session.flush()
        else:
            # Update display metadata if changed (metadata is mutable, knowledge is not)
            skill.name = manifest.metadata.name
            skill.category = manifest.metadata.category

        # 4. Check for existing version
        stmt_ver = select(SkillVersion).where(
            and_(
                SkillVersion.skill_id == skill.id,
                SkillVersion.semver == manifest.versioning.version,
            )
        )
        res_ver = await session.execute(stmt_ver)
        existing_version = res_ver.scalars().first()

        if existing_version:
            existing_version.skill = skill
            if existing_version.content_hash == manifest.versioning.content_hash:
                logger.info(
                    "Skill %s v%s already registered with identical hash %s (idempotent)",
                    skill.slug,
                    existing_version.semver,
                    existing_version.content_hash,
                )
                return existing_version
            raise SkillVersionImmutableViolationError(
                f"Skill '{skill.slug}' version '{manifest.versioning.version}' is already sealed with hash "
                f"'{existing_version.content_hash}'. Cannot overwrite with hash '{manifest.versioning.content_hash}'. "
                "Bump the SemVer version to publish modifications."
            )

        # 5. Insert immutable SkillVersion
        new_version = SkillVersion(
            skill=skill,
            skill_id=skill.id,
            manifest_version=manifest.manifest_version,
            semver=manifest.versioning.version,
            content_hash=manifest.versioning.content_hash,
            instructions=manifest.knowledge.instructions,
            constraints=manifest.knowledge.constraints,
            required_tools=sorted(manifest.dependencies.required_tools),
            required_skills=sorted(manifest.dependencies.required_skills),
            suggested_risk=manifest.governance_hints.suggested_risk,
            conflicts_with=manifest.governance_hints.conflicts_with,
            status=SkillStatus.ACTIVE.value,
        )
        session.add(new_version)
        await session.flush()

        # If system skill, automatically register in workspace_skills if requested for workspace
        if workspace_id and not manifest.identity.is_system:
            ws_skill_stmt = select(WorkspaceSkill).where(
                and_(
                    WorkspaceSkill.workspace_id == workspace_id,
                    WorkspaceSkill.skill_id == skill.id,
                )
            )
            ws_res = await session.execute(ws_skill_stmt)
            if not ws_res.scalars().first():
                ws_entry = WorkspaceSkill(
                    workspace_id=workspace_id,
                    skill_id=skill.id,
                    is_enabled=True,
                )
                session.add(ws_entry)
                await session.flush()

        return new_version

    @staticmethod
    async def get_skill(
        session: AsyncSession,
        slug: str,
        workspace_id: Optional[UUID] = None,
    ) -> Optional[Skill]:
        """Fetch a skill by slug, searching workspace first then system scope."""
        conditions = [and_(Skill.slug == slug, Skill.is_system == True)]  # noqa: E712
        if workspace_id:
            conditions.append(and_(Skill.slug == slug, Skill.workspace_id == workspace_id))

        stmt = (
            select(Skill)
            .where(or_(*conditions))
            .order_by(Skill.is_system.asc(), Skill.created_at.desc())
            .options(selectinload(Skill.versions))
        )
        res = await session.execute(stmt)
        return res.scalars().first()

    @staticmethod
    async def get_active_version(
        session: AsyncSession,
        skill_id: UUID,
    ) -> Optional[SkillVersion]:
        """Get the latest ACTIVE version of a skill."""
        stmt = (
            select(SkillVersion)
            .where(
                and_(
                    SkillVersion.skill_id == skill_id,
                    SkillVersion.status == SkillStatus.ACTIVE.value,
                )
            )
            .order_by(SkillVersion.created_at.desc())
        )
        res = await session.execute(stmt)
        return res.scalars().first()

    @classmethod
    async def resolve_transitive_dependencies(
        cls,
        session: AsyncSession,
        root_version: SkillVersion,
        workspace_id: Optional[UUID] = None,
        max_depth: int = 4,
        max_skills: int = 16,
    ) -> List[SkillVersion]:
        """Resolves required_skills transitively up to max_depth and max_skills.

        Guarantees:
        - Cycle detection.
        - Bounded closure (SKILL-INV-09).
        """
        resolved: List[SkillVersion] = []
        visited_slugs: Set[str] = set()

        root_slug = (
            root_version.skill.slug
            if (hasattr(root_version, "skill") and root_version.skill and hasattr(root_version.skill, "slug"))
            else str(root_version.skill_id)
        )

        async def _traverse(current_ver: SkillVersion, depth: int, path: List[str]) -> None:
            if depth > max_depth or len(resolved) >= max_skills:
                return

            req_skills = current_ver.required_skills or []
            for dep_slug in req_skills:
                if dep_slug in path:
                    raise SkillDependencyCycleError(
                        f"Cycle detected in skill dependencies: {' -> '.join(path + [dep_slug])}"
                    )
                if dep_slug in visited_slugs:
                    continue

                visited_slugs.add(dep_slug)
                dep_skill = await cls.get_skill(session, dep_slug, workspace_id)
                if not dep_skill:
                    curr_slug = (
                        current_ver.skill.slug
                        if (hasattr(current_ver, "skill") and current_ver.skill and hasattr(current_ver.skill, "slug"))
                        else str(current_ver.skill_id)
                    )
                    raise MissingTransitiveSkillDependencyError(
                        f"Required skill dependency '{dep_slug}' not found in registry for skill '{curr_slug}'."
                    )

                active_ver = await cls.get_active_version(session, dep_skill.id)
                if not active_ver:
                    raise MissingTransitiveSkillDependencyError(
                        f"Active version for required skill dependency '{dep_slug}' not found in registry."
                    )

                resolved.append(active_ver)
                await _traverse(active_ver, depth + 1, path + [dep_slug])

        await _traverse(root_version, 1, [root_slug])
        return resolved
