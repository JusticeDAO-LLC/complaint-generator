"""Mike editor integration package.

Exposes the LLM router patch, editor adapter utilities, and skill asset loader
so the complaint workspace can programmatically reach the Mike frontend/backend
layer and enforce its router-ownership policy at every handoff boundary.
"""

from __future__ import annotations

from .llm_patch import apply_mike_llm_router_patch, MIKE_LLM_PATCH_VERSION
from .skills import load_skill, list_skill_ids, SKILLS_DIR

__all__ = [
    "apply_mike_llm_router_patch",
    "MIKE_LLM_PATCH_VERSION",
    "load_skill",
    "list_skill_ids",
    "SKILLS_DIR",
]
