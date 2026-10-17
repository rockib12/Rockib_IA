"""Common builder for SkillManifest instances with canonical content hashing."""
from __future__ import annotations

from typing import List, Optional

from app.skills.schemas import (
    SkillManifest,
    SkillManifestDependencies,
    SkillManifestGovernanceHints,
    SkillManifestIdentity,
    SkillManifestKnowledge,
    SkillManifestMetadata,
    SkillManifestVersioning,
    compute_canonical_content_hash,
)


def build_manifest(
    skill_id: str,
    version: str,
    name: str,
    description: str,
    category: str,
    instructions: str,
    constraints: list[str],
    required_tools: list[str],
    required_skills: Optional[list[str]] = None,
    suggested_risk: str = "low",
    conflicts_with: Optional[list[str]] = None,
    author: str = "Rockib AI Core",
) -> SkillManifest:
    """Builds a sealed SkillManifest with canonical SHA-256 content_hash."""
    knowledge = SkillManifestKnowledge(
        instructions=instructions,
        constraints=constraints,
    )
    dependencies = SkillManifestDependencies(
        required_tools=sorted(required_tools),
        required_skills=sorted(required_skills or []),
    )
    content_hash = compute_canonical_content_hash(knowledge, dependencies)

    return SkillManifest(
        manifest_version="1.0",
        identity=SkillManifestIdentity(id=skill_id, is_system=True),
        versioning=SkillManifestVersioning(version=version, content_hash=content_hash),
        metadata=SkillManifestMetadata(
            name=name,
            description=description,
            category=category,
            author=author,
        ),
        knowledge=knowledge,
        dependencies=dependencies,
        governance_hints=SkillManifestGovernanceHints(
            suggested_risk=suggested_risk,
            conflicts_with=conflicts_with or [],
        ),
    )
