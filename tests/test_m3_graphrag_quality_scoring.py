"""Tests for M3 GraphRAG ontology quality scoring and gap detection.

Covers:
- score_ontology_support_paths: returns structured quality payload for a claim type
- identify_ontology_gaps: returns gap list consumable by follow-up planning
- _CLAIM_ONTOLOGY_PROFILES: expected profiles for employment_discrimination etc.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from integrations.ipfs_datasets.graphrag import (
    _CLAIM_ONTOLOGY_PROFILES,
    build_validate_score_ontology,
    identify_ontology_gaps,
    score_support_path_quality,
    score_ontology_support_paths,
)

pytestmark = pytest.mark.no_auto_network


# ---------------------------------------------------------------------------
# score_ontology_support_paths
# ---------------------------------------------------------------------------

def test_score_returns_implemented_status():
    ontology = {"entities": [{"name": "Employee"}], "relations": [], "concepts": []}
    result = score_ontology_support_paths(ontology, claim_type="employment_discrimination")
    assert result["metadata"]["implementation_status"] == "implemented"


def test_score_returns_required_keys():
    ontology = {"entities": [], "relations": [], "concepts": []}
    result = score_ontology_support_paths(ontology, claim_type="employment_discrimination")
    for key in (
        "overall_quality_score", "grade", "gap_signals", "entity_coverage_score",
        "concept_completeness_score", "relation_density_score", "gap_signal_count",
    ):
        assert key in result, f"Missing key: {key}"


def test_score_empty_ontology_returns_error():
    result = score_ontology_support_paths({}, claim_type="employment_discrimination")
    assert result["status"] == "error"
    assert result["grade"] == "F"
    assert len(result["gap_signals"]) > 0


def test_score_non_dict_ontology_returns_error():
    result = score_ontology_support_paths(None, claim_type="employment_discrimination")
    assert result["status"] == "error"
    assert result["overall_quality_score"] == 0.0


def test_score_good_employment_ontology():
    ontology = {
        "entities": [
            {"name": "Employee"},
            {"name": "Employer"},
            {"name": "Supervisor"},
            {"name": "HR"},
            {"name": "Complainant"},
        ],
        "relations": [
            {"subject": "Employee", "predicate": "terminated", "object": "Complainant"},
            {"subject": "Supervisor", "predicate": "discriminated", "object": "Employee"},
            {"subject": "Complainant", "predicate": "reported", "object": "HR"},
        ],
        "concepts": [
            {"name": "discrimination"},
            {"name": "retaliation"},
            {"name": "termination"},
            {"name": "protected"},
            {"name": "race"},
            {"name": "employment"},
        ],
    }
    result = score_ontology_support_paths(ontology, claim_type="employment_discrimination")
    assert result["status"] == "success"
    assert result["overall_quality_score"] > 0.35
    assert result["entity_coverage_score"] > 0.0
    assert result["concept_completeness_score"] > 0.0
    assert result["grade"] in ("A", "B", "C", "D")


def test_score_empty_entity_list_gives_low_entity_score():
    ontology = {
        "entities": [],
        "relations": [],
        "concepts": [{"name": "discrimination"}, {"name": "employment"}],
    }
    result = score_ontology_support_paths(ontology, claim_type="employment_discrimination")
    assert result["entity_coverage_score"] == 0.0


def test_score_unknown_claim_type_uses_default_profile():
    ontology = {
        "entities": [{"name": "Complainant"}],
        "relations": [],
        "concepts": [{"name": "discrimination"}],
    }
    result = score_ontology_support_paths(ontology, claim_type="unknown_claim_type")
    assert result["status"] == "success"
    assert isinstance(result["overall_quality_score"], float)


def test_score_housing_discrimination_profile():
    ontology = {
        "entities": [
            {"name": "Tenant"},
            {"name": "Landlord"},
            {"name": "Complainant"},
        ],
        "relations": [
            {"subject": "Landlord", "predicate": "denied", "object": "Tenant"},
        ],
        "concepts": [
            {"name": "housing"},
            {"name": "discrimination"},
            {"name": "protected"},
        ],
    }
    result = score_ontology_support_paths(ontology, claim_type="housing_discrimination")
    assert result["status"] == "success"
    assert result["claim_type"] == "housing_discrimination"
    assert result["entity_coverage_score"] > 0.0


def test_claim_ontology_profiles_have_required_keys():
    for claim_type, profile in _CLAIM_ONTOLOGY_PROFILES.items():
        assert "expected_entity_keywords" in profile, f"Missing entity keywords in {claim_type}"
        assert "expected_relation_predicates" in profile, f"Missing relation predicates in {claim_type}"
        assert "expected_concept_keywords" in profile, f"Missing concept keywords in {claim_type}"
        assert len(profile["expected_entity_keywords"]) > 0
        assert len(profile["expected_concept_keywords"]) > 0


def test_score_grade_thresholds():
    # Very good ontology should get a high grade
    good_ontology = {
        "entities": [
            {"name": "employee"},
            {"name": "employer"},
            {"name": "supervisor"},
            {"name": "manager"},
            {"name": "hr"},
            {"name": "complainant"},
            {"name": "company"},
            {"name": "coworker"},
        ],
        "relations": [
            {"subject": "employer", "predicate": "terminated", "object": "employee"},
            {"subject": "employer", "predicate": "discriminated", "object": "employee"},
            {"subject": "employee", "predicate": "reported", "object": "hr"},
            {"subject": "supervisor", "predicate": "harassed", "object": "employee"},
            {"subject": "employer", "predicate": "violated", "object": "employee"},
            {"subject": "complainant", "predicate": "employed", "object": "company"},
        ],
        "concepts": [
            {"name": "discrimination"},
            {"name": "retaliation"},
            {"name": "harassment"},
            {"name": "termination"},
            {"name": "demotion"},
            {"name": "protected"},
            {"name": "race"},
            {"name": "gender"},
            {"name": "disability"},
            {"name": "religion"},
            {"name": "age"},
            {"name": "employment"},
        ],
    }
    result = score_ontology_support_paths(good_ontology, claim_type="employment_discrimination")
    assert result["grade"] in ("A", "B"), f"Expected high grade but got {result['grade']}"


# ---------------------------------------------------------------------------
# identify_ontology_gaps
# ---------------------------------------------------------------------------

def test_identify_gaps_returns_implemented_status():
    ontology = {"entities": [{"name": "Employee"}], "relations": [], "concepts": []}
    result = identify_ontology_gaps(ontology, claim_type="employment_discrimination")
    assert result["metadata"]["implementation_status"] == "implemented"


def test_identify_gaps_returns_required_keys():
    ontology = {"entities": [], "relations": [], "concepts": []}
    result = identify_ontology_gaps(ontology, claim_type="employment_discrimination")
    for key in ("gaps", "gap_count", "has_blocking_gaps", "has_gaps", "overall_quality_score", "grade"):
        assert key in result, f"Missing key: {key}"


def test_identify_gaps_empty_ontology_has_gaps():
    result = identify_ontology_gaps({}, claim_type="employment_discrimination")
    assert result["has_gaps"] is True
    assert result["gap_count"] >= 1


def test_identify_gaps_populated_ontology_fewer_gaps():
    rich_ontology = {
        "entities": [
            {"name": "employee"}, {"name": "employer"}, {"name": "supervisor"},
            {"name": "manager"}, {"name": "hr"}, {"name": "complainant"},
        ],
        "relations": [
            {"subject": "employer", "predicate": "terminated", "object": "employee"},
            {"subject": "employer", "predicate": "discriminated", "object": "employee"},
        ],
        "concepts": [
            {"name": "discrimination"}, {"name": "retaliation"}, {"name": "termination"},
            {"name": "protected"}, {"name": "race"}, {"name": "employment"},
        ],
    }
    sparse_ontology = {"entities": [], "relations": [], "concepts": []}

    rich_result = identify_ontology_gaps(rich_ontology, claim_type="employment_discrimination")
    sparse_result = identify_ontology_gaps(sparse_ontology, claim_type="employment_discrimination")

    assert rich_result["overall_quality_score"] > sparse_result["overall_quality_score"]


def test_identify_gaps_each_gap_has_required_fields():
    result = identify_ontology_gaps({"entities": [], "relations": [], "concepts": []},
                                     claim_type="employment_discrimination")
    for gap in result["gaps"]:
        assert "gap_type" in gap
        assert "description" in gap
        assert "severity" in gap
        assert "follow_up_action" in gap
        assert gap["severity"] in ("blocking", "moderate", "minor")


def test_identify_gaps_follow_up_actions_are_actionable():
    result = identify_ontology_gaps(
        {"entities": [], "relations": [], "concepts": [{"name": "discrimination"}]},
        claim_type="housing_discrimination",
    )
    actions = [g["follow_up_action"] for g in result["gaps"]]
    # All actions should be non-empty strings
    for action in actions:
        assert isinstance(action, str) and len(action) > 0


# ---------------------------------------------------------------------------
# build_validate_score_ontology
# ---------------------------------------------------------------------------

def test_build_validate_score_ontology_returns_normalized_quality_payload():
    result = build_validate_score_ontology(
        "Employee reported discrimination to HR. Employer terminated Employee after the complaint.",
        claim_type="retaliation",
        refinement_rounds=1,
    )

    assert result["metadata"]["operation"] == "build_validate_score_ontology"
    assert result["metadata"]["implementation_status"] == "implemented"
    assert result["status"] in {"success", "degraded"}
    assert isinstance(result["ontology"], dict)
    assert result["build"]["metadata"]["operation"] == "build_ontology"
    assert result["validation"]["metadata"]["operation"] == "validate_ontology"
    assert result["quality"]["metadata"]["operation"] == "score_ontology_support_paths"
    assert result["gaps"]["metadata"]["operation"] == "identify_ontology_gaps"

    ontology_quality = result["ontology_quality"]
    for key in (
        "valid",
        "validation_issues",
        "overall_quality_score",
        "grade",
        "entity_count",
        "relation_count",
        "concept_count",
        "gap_count",
        "has_gaps",
    ):
        assert key in ontology_quality
    assert ontology_quality["valid"] is True
    assert ontology_quality["entity_count"] >= 1
    assert ontology_quality["overall_quality_score"] == result["quality"]["overall_quality_score"]


# ---------------------------------------------------------------------------
# score_support_path_quality
# ---------------------------------------------------------------------------

def test_score_support_path_quality_distinguishes_weak_missing_required_support():
    support_path = {
        "proof_path_id": "path:test",
        "fact_ids": ["fact:1"],
        "fact_count": 1,
        "support_refs": ["artifact:hr"],
        "support_ref_count": 1,
        "support_kinds": ["evidence"],
        "source_families": ["evidence"],
        "trace_count": 1,
        "graph_id_count": 0,
        "metadata": {
            "support_trace_summary": {
                "trace_count": 1,
                "fact_trace_count": 1,
                "avg_parse_quality_score": 60.0,
                "support_by_kind": {"evidence": 1},
            },
            "graph_trace_summary": {"traced_link_count": 0},
        },
    }
    ontology = {
        "entities": [{"name": "Employee"}, {"name": "HR"}],
        "relations": [{"subject": "Employee", "predicate": "reported", "object": "HR"}],
        "concepts": [{"name": "evidence"}, {"name": "retaliation"}],
    }

    result = score_support_path_quality(
        support_path,
        ontology=ontology,
        required_support_kinds=["evidence", "authority"],
    )

    assert result["metadata"]["operation"] == "score_support_path_quality"
    assert result["metadata"]["implementation_status"] == "implemented"
    assert result["status"] == "success"
    assert 0.0 < result["support_quality_score"] < 1.0
    assert result["support_quality_tier"] in {"weak_support", "moderate_support"}
    assert result["missing_required_support_kinds"] == ["authority"]
    assert any(signal["signal_type"] == "missing_required_support_kind" for signal in result["quality_signals"])
