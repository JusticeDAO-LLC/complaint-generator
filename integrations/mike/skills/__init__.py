"""Skill asset loader for the Mike editor integration.

Provides helpers to read the JSON skill descriptor files from
``integrations/mike/skills/`` and surface them to the workspace manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILLS_DIR: Path = Path(__file__).resolve().parent

_SKILL_CACHE: Dict[str, Dict[str, Any]] = {}


def list_skill_ids() -> List[str]:
    """Return a sorted list of all skill asset IDs found in ``SKILLS_DIR``."""
    ids: List[str] = []
    for path in sorted(SKILLS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            skill_id = str(data.get("skill_asset_id") or "").strip()
            if skill_id:
                ids.append(skill_id)
        except Exception:
            pass
    return ids


def load_skill(skill_asset_id: str) -> Optional[Dict[str, Any]]:
    """Load and return the skill descriptor for *skill_asset_id*.

    Returns ``None`` if the skill file does not exist or cannot be parsed.
    Results are cached in-process after the first successful load.
    """
    skill_asset_id = str(skill_asset_id or "").strip()
    if not skill_asset_id:
        return None
    if skill_asset_id in _SKILL_CACHE:
        return dict(_SKILL_CACHE[skill_asset_id])
    path = SKILLS_DIR / f"{skill_asset_id}.json"
    if not path.is_file():
        return None
    try:
        data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        _SKILL_CACHE[skill_asset_id] = data
        return dict(data)
    except Exception:
        return None


def load_all_skills() -> List[Dict[str, Any]]:
    """Load and return all skill descriptors from ``SKILLS_DIR``."""
    skills: List[Dict[str, Any]] = []
    for path in sorted(SKILLS_DIR.glob("*.json")):
        try:
            data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            skill_id = str(data.get("skill_asset_id") or "").strip()
            if skill_id:
                _SKILL_CACHE[skill_id] = data
            skills.append(data)
        except Exception:
            pass
    return skills


__all__ = [
    "SKILLS_DIR",
    "list_skill_ids",
    "load_skill",
    "load_all_skills",
]
