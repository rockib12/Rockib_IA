"""Rockib AI 107 Skills Official Catalog.

Aggregation of all skill modules:
- core (5 historical core skills)
- engineering (23 additional skills, total 25 engineering)
- ai_agentic (18 skills)
- devops (20 skills)
- cybersecurity (17 additional skills, total 18 cybersecurity)
- data (14 skills)
- business (10 additional skills, total 12 business)

Total: 5 + 23 + 18 + 20 + 17 + 14 + 10 = 107 Skills.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.models import SkillVersion
from app.skills.schemas import SkillManifest
from app.skills.services.registry import SkillRegistry
from app.skills.catalog.builder import build_manifest as _build_manifest
from app.skills.catalog.core import get_core_catalogue
from app.skills.catalog.engineering import get_engineering_skills
from app.skills.catalog.ai_agentic import get_ai_agentic_skills
from app.skills.catalog.devops import get_devops_skills
from app.skills.catalog.cybersecurity import get_cybersecurity_skills
from app.skills.catalog.data import get_data_skills
from app.skills.catalog.business import get_business_skills

logger = logging.getLogger(__name__)


def get_default_catalogue() -> List[SkillManifest]:
    """Returns the complete, sealed 107 skills catalog."""
    catalogue: List[SkillManifest] = []
    
    # 1. 5 Core Skills
    catalogue.extend(get_core_catalogue())
    
    # 2. Engineering (23 skills)
    catalogue.extend(get_engineering_skills())
    
    # 3. AI Agentic (18 skills)
    catalogue.extend(get_ai_agentic_skills())
    
    # 4. DevOps (20 skills)
    catalogue.extend(get_devops_skills())
    
    # 5. Cybersecurity (17 skills)
    catalogue.extend(get_cybersecurity_skills())
    
    # 6. Data (14 skills)
    catalogue.extend(get_data_skills())
    
    # 7. Business (10 skills)
    catalogue.extend(get_business_skills())
    
    return catalogue


async def seed_default_skills(session: AsyncSession) -> List[SkillVersion]:
    """Registers all 107 default skills into the database idempotently."""
    registered: List[SkillVersion] = []
    for manifest in get_default_catalogue():
        version = await SkillRegistry.register_manifest(session, manifest)
        registered.append(version)
        logger.info(
            "Seeded default skill '%s' v%s (hash: %s)",
            manifest.identity.id,
            version.semver,
            version.content_hash[:16],
        )
    return registered


__all__ = [
    "get_core_catalogue",
    "get_default_catalogue",
    "seed_default_skills",
    "_build_manifest",
    "get_engineering_skills",
    "get_ai_agentic_skills",
    "get_devops_skills",
    "get_cybersecurity_skills",
    "get_data_skills",
    "get_business_skills",
]
