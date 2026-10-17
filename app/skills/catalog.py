"""Rockib AI Official Skill Catalog (Module Aggregator).

Re-exports from app.skills.catalog package for transparent backwards compatibility.
"""
from __future__ import annotations

from app.skills.catalog import (
    _build_manifest,
    get_core_catalogue,
    get_default_catalogue,
    seed_default_skills,
)

__all__ = [
    "get_core_catalogue",
    "get_default_catalogue",
    "seed_default_skills",
    "_build_manifest",
]
