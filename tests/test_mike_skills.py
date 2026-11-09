"""Tests for integrations/mike/skills/ — skill file loading.

These tests verify that the skill JSON files can be loaded and contain
the expected schema keys.
"""

from __future__ import annotations

from typing import Any, Dict, List
import json

import pytest


EXPECTED_SKILL_IDS = [
    "complaint-grounding",
    "complaint-logic",
    "complaint-corpus-search",
    "complaint-policy-rules",
    "complaint-authority-graphs",
    "complaint-router",
    "complaint-draft-logic-pipeline",
    "complaint-corpus-containment",
    "complaint-mike-llm-patch",
]


def test_skills_dir_exists():
    from integrations.mike.skills import SKILLS_DIR
    assert SKILLS_DIR.is_dir(), f"SKILLS_DIR does not exist: {SKILLS_DIR}"


def test_list_skill_ids_returns_all_expected():
    from integrations.mike.skills import list_skill_ids
    ids = list_skill_ids()
    for expected_id in EXPECTED_SKILL_IDS:
        assert expected_id in ids, f"Missing skill: {expected_id}"


def test_list_skill_ids_count():
    from integrations.mike.skills import list_skill_ids
    ids = list_skill_ids()
    assert len(ids) == len(EXPECTED_SKILL_IDS)


def test_load_skill_returns_dict_for_known_id():
    from integrations.mike.skills import load_skill
    for skill_id in EXPECTED_SKILL_IDS:
        result = load_skill(skill_id)
        assert isinstance(result, dict), f"load_skill({skill_id!r}) returned non-dict"


def test_load_skill_returns_none_for_unknown_id():
    from integrations.mike.skills import load_skill
    assert load_skill("nonexistent-skill-xyz") is None


def test_load_skill_contains_required_keys():
    from integrations.mike.skills import load_skill
    required_keys = {"skill_asset_id", "name", "capability", "adapter"}
    for skill_id in EXPECTED_SKILL_IDS:
        result = load_skill(skill_id)
        for key in required_keys:
            assert key in result, f"Skill {skill_id!r} missing key {key!r}"


def test_load_skill_asset_id_matches_filename():
    from integrations.mike.skills import load_skill
    for skill_id in EXPECTED_SKILL_IDS:
        result = load_skill(skill_id)
        assert result["skill_asset_id"] == skill_id


def test_load_all_skills_returns_all():
    from integrations.mike.skills import load_all_skills
    skills = load_all_skills()
    assert len(skills) == len(EXPECTED_SKILL_IDS)


def test_load_all_skills_each_has_name():
    from integrations.mike.skills import load_all_skills
    for skill in load_all_skills():
        assert "name" in skill
        assert isinstance(skill["name"], str)
        assert skill["name"]


def test_skill_draft_logic_pipeline_has_pipeline_steps():
    from integrations.mike.skills import load_skill
    skill = load_skill("complaint-draft-logic-pipeline")
    assert "pipeline_steps" in skill
    assert isinstance(skill["pipeline_steps"], list)
    assert len(skill["pipeline_steps"]) == 5


def test_skill_draft_logic_pipeline_step_ids():
    from integrations.mike.skills import load_skill
    skill = load_skill("complaint-draft-logic-pipeline")
    step_ids = {s["step"] for s in skill["pipeline_steps"]}
    assert step_ids == {"A", "B", "C", "D", "E"}


def test_skill_mike_llm_patch_has_patch_version():
    from integrations.mike.skills import load_skill
    skill = load_skill("complaint-mike-llm-patch")
    assert "patch_version" in skill
    assert "mike-llm-router-patch" in str(skill["patch_version"])


def test_skill_corpus_containment_has_outputs_schema():
    from integrations.mike.skills import load_skill
    skill = load_skill("complaint-corpus-containment")
    assert "outputs" in skill
    assert "corpus_coverage_percent" in skill["outputs"]


def test_skill_logic_has_theorem_export_in_outputs():
    from integrations.mike.skills import load_skill
    skill = load_skill("complaint-logic")
    assert "outputs" in skill
    assert "theorem_export" in skill["outputs"]


def test_mike_init_exposes_load_skill():
    from integrations.mike import load_skill, list_skill_ids
    assert callable(load_skill)
    assert callable(list_skill_ids)
