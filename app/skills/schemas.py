"""Pydantic schemas and canonical hashing contract for Rockib AI Skill System.

Contract locked in SKILL_SYSTEM_DESIGN.md:
- Canonical payload sorting (required_tools, required_skills).
- Instructions LF normalization.
- SHA-256 hash formatting: "sha256:" + hex digest.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SkillStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class SkillCategory(str, Enum):
    ENGINEERING = "engineering"
    AI_AGENTIC = "ai_agentic"
    DEVOPS = "devops"
    CYBERSECURITY = "cybersecurity"
    DATA = "data"
    BUSINESS = "business"
    MARKETING = "marketing"
    OPERATIONS = "operations"
    SECURITY = "security"
    RESEARCH = "research"
    GENERAL = "general"


SKILL_ID_REGEX = re.compile(r"^[a-z0-9_]{3,50}$")
SEMVER_REGEX = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$")


class SkillManifestIdentity(BaseModel):
    id: str = Field(..., description="Technical snake_case identifier (3-50 chars)")
    is_system: bool = Field(default=False, description="True for core system skills, False for workspace skills")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not SKILL_ID_REGEX.match(v):
            raise ValueError(f"Skill id '{v}' must match pattern ^[a-z0-9_]{{3,50}}$")
        return v


class SkillManifestVersioning(BaseModel):
    version: str = Field(..., description="Semver version of the skill")
    content_hash: str = Field(..., description="Canonical SHA-256 content hash (sha256:...)")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not SEMVER_REGEX.match(v):
            raise ValueError(f"Skill version '{v}' must be valid SemVer (e.g. 1.0.0)")
        return v

    @field_validator("content_hash")
    @classmethod
    def validate_hash(cls, v: str) -> str:
        if not v.startswith("sha256:") or len(v) != 71:
            raise ValueError("content_hash must be in format 'sha256:<64-hex-chars>'")
        return v


class SkillManifestMetadata(BaseModel):
    name: str = Field(..., max_length=150)
    description: str = Field(..., max_length=1000)
    category: str = Field(default=SkillCategory.GENERAL.value)
    author: str = Field(default="Rockib AI")


class SkillManifestKnowledge(BaseModel):
    instructions: str = Field(..., min_length=10, description="Procedural guidance for RationalAgent")
    constraints: List[str] = Field(default_factory=list, description="Strict negative behavioral rules")


class SkillManifestDependencies(BaseModel):
    required_tools: List[str] = Field(default_factory=list, description="Declarative required tools (non-permissive)")
    required_skills: List[str] = Field(default_factory=list, description="Declarative required upstream skills")


class SkillManifestGovernanceHints(BaseModel):
    suggested_risk: str = Field(default="low", description="Cognitive risk indicator (low/medium/high)")
    conflicts_with: List[str] = Field(default_factory=list, description="Mutually exclusive skill slugs")


class SkillManifest(BaseModel):
    """Canonical Skill Manifest adhering strictly to SKILL_SYSTEM_DESIGN.md."""
    manifest_version: str = Field(default="1.0", description="Manifest schema grammar version")
    identity: SkillManifestIdentity
    versioning: SkillManifestVersioning
    metadata: SkillManifestMetadata
    knowledge: SkillManifestKnowledge
    dependencies: SkillManifestDependencies = Field(default_factory=SkillManifestDependencies)
    governance_hints: SkillManifestGovernanceHints = Field(default_factory=SkillManifestGovernanceHints)


def normalize_instructions(text: str) -> str:
    """Normalize line endings to LF and strip trailing line whitespaces."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def build_canonical_payload(
    knowledge: SkillManifestKnowledge | dict[str, Any],
    dependencies: SkillManifestDependencies | dict[str, Any],
) -> dict[str, Any]:
    """Build the exact locked JSON structure for canonical content hash calculation."""
    if isinstance(knowledge, SkillManifestKnowledge):
        raw_instructions = knowledge.instructions
        raw_constraints = knowledge.constraints
    else:
        raw_instructions = knowledge.get("instructions", "")
        raw_constraints = knowledge.get("constraints", [])

    if isinstance(dependencies, SkillManifestDependencies):
        raw_tools = dependencies.required_tools
        raw_skills = dependencies.required_skills
    else:
        raw_tools = dependencies.get("required_tools", [])
        raw_skills = dependencies.get("required_skills", [])

    norm_instructions = normalize_instructions(raw_instructions)
    norm_constraints = [c.strip() for c in raw_constraints if c and c.strip()]
    sorted_tools = sorted([t.strip() for t in raw_tools if t and t.strip()])
    sorted_skills = sorted([s.strip() for s in raw_skills if s and s.strip()])

    return {
        "dependencies": {
            "required_skills": sorted_skills,
            "required_tools": sorted_tools,
        },
        "knowledge": {
            "constraints": norm_constraints,
            "instructions": norm_instructions,
        },
    }


def compute_canonical_content_hash(
    knowledge: SkillManifestKnowledge | dict[str, Any],
    dependencies: SkillManifestDependencies | dict[str, Any],
) -> str:
    """Computes the deterministic SHA-256 hash of the canonical payload."""
    payload = build_canonical_payload(knowledge, dependencies)
    canonical_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()


def verify_skill_manifest_hash(manifest: SkillManifest) -> bool:
    """Verifies that the sealed content_hash matches the recomputed canonical hash."""
    expected_hash = compute_canonical_content_hash(manifest.knowledge, manifest.dependencies)
    return manifest.versioning.content_hash == expected_hash


# Read & Response schemas
class SkillVersionRead(BaseModel):
    id: UUID
    skill_id: UUID
    manifest_version: str
    semver: str
    content_hash: str
    instructions: str
    constraints: List[str]
    required_tools: List[str]
    required_skills: List[str]
    suggested_risk: str
    conflicts_with: List[str]
    status: SkillStatus
    created_at: datetime


class SkillRead(BaseModel):
    id: UUID
    workspace_id: Optional[UUID] = None
    slug: str
    name: str
    category: str
    is_system: bool
    created_at: datetime
    active_version: Optional[SkillVersionRead] = None


class ActiveSkillContext(BaseModel):
    """Context snippet formatted for prompt injection into RationalAgent."""
    id: str
    name: str
    semver: str
    content_hash: str
    instructions: str
    constraints: List[str]
    required_tools: List[str]
