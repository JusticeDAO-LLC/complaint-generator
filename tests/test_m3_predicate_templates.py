"""Tests for M3 logic adapter predicate templates and claim-element mapping.

Covers:
- get_predicate_templates: returns templates for employment_discrimination, housing_discrimination, retaliation
- map_claim_elements_to_predicates: maps claim elements to FOL predicates ready for prove_claim_elements
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from integrations.ipfs_datasets.logic import (
    _COMPLAINT_PREDICATE_TEMPLATES,
    get_predicate_templates,
    map_claim_elements_to_predicates,
)

pytestmark = pytest.mark.no_auto_network


# ---------------------------------------------------------------------------
# get_predicate_templates
# ---------------------------------------------------------------------------

def test_get_templates_returns_implemented_status():
    result = get_predicate_templates("employment_discrimination")
    assert result["metadata"]["implementation_status"] == "implemented"


def test_get_templates_employment_discrimination():
    result = get_predicate_templates("employment_discrimination")
    assert result["status"] == "success"
    assert result["complaint_type"] == "employment_discrimination"
    assert result["element_count"] == 4
    element_ids = {e["element_id"] for e in result["elements"]}
    assert "protected_trait" in element_ids
    assert "employment_relationship" in element_ids
    assert "adverse_action" in element_ids
    assert "discriminatory_motive" in element_ids


def test_get_templates_housing_discrimination():
    result = get_predicate_templates("housing_discrimination")
    assert result["status"] == "success"
    assert result["element_count"] == 4
    element_ids = {e["element_id"] for e in result["elements"]}
    assert "protected_trait" in element_ids
    assert "housing_context" in element_ids


def test_get_templates_retaliation():
    result = get_predicate_templates("retaliation")
    assert result["status"] == "success"
    element_ids = {e["element_id"] for e in result["elements"]}
    assert "protected_activity" in element_ids
    assert "causal_connection" in element_ids


def test_get_templates_unknown_type_returns_not_found():
    result = get_predicate_templates("unknown_claim_type")
    assert result["status"] == "not_found"
    assert result["element_count"] == 0
    assert isinstance(result["supported_complaint_types"], list)
    assert "employment_discrimination" in result["supported_complaint_types"]


def test_get_templates_each_element_has_required_fields():
    for claim_type in _COMPLAINT_PREDICATE_TEMPLATES:
        result = get_predicate_templates(claim_type)
        for element in result["elements"]:
            assert "element_id" in element, f"Missing element_id in {claim_type}"
            assert "element_text" in element, f"Missing element_text in {claim_type}"
            assert "fol_template" in element, f"Missing fol_template in {claim_type}"
            assert "dcec_template" in element, f"Missing dcec_template in {claim_type}"
            assert "predicate_types" in element, f"Missing predicate_types in {claim_type}"
            assert "grounded_facts" in element, f"Missing grounded_facts in {claim_type}"
            assert len(element["fol_template"]) > 0, f"Empty fol_template in {claim_type}/{element['element_id']}"
            assert len(element["dcec_template"]) > 0, f"Empty dcec_template in {claim_type}/{element['element_id']}"
            assert len(element["grounded_facts"]) > 0, f"No grounded facts in {claim_type}/{element['element_id']}"


def test_get_templates_supported_types_list():
    result = get_predicate_templates("employment_discrimination")
    assert "supported_complaint_types" in result
    assert "employment_discrimination" in result["supported_complaint_types"]
    assert "housing_discrimination" in result["supported_complaint_types"]
    assert "retaliation" in result["supported_complaint_types"]
    assert "fair_housing" in result["supported_complaint_types"]


# ---------------------------------------------------------------------------
# map_claim_elements_to_predicates
# ---------------------------------------------------------------------------

def test_map_elements_returns_implemented_status():
    result = map_claim_elements_to_predicates("employment_discrimination", [])
    assert result["metadata"]["implementation_status"] == "implemented"


def test_map_elements_returns_required_keys():
    result = map_claim_elements_to_predicates("employment_discrimination", [])
    for key in ("predicates", "predicate_count", "template_match_count", "unmapped_element_ids"):
        assert key in result, f"Missing key: {key}"


def test_map_elements_empty_input():
    result = map_claim_elements_to_predicates("employment_discrimination", [])
    assert result["predicate_count"] == 0
    assert result["template_match_count"] == 0
    assert result["predicates"] == []


def test_map_elements_known_elements_match_templates():
    elements = [
        {"element_id": "protected_trait", "element_text": "Protected trait or class", "status": "supported"},
        {"element_id": "adverse_action", "element_text": "Adverse employment action", "status": "incomplete"},
        {"element_id": "discriminatory_motive", "element_text": "Discriminatory motive", "status": "missing"},
    ]
    result = map_claim_elements_to_predicates("employment_discrimination", elements)
    assert result["predicate_count"] == 3
    assert result["template_match_count"] == 3
    assert result["unmapped_element_ids"] == []

    predicates = result["predicates"]
    for pred in predicates:
        assert pred["predicate_type"] == "claim_element"
        assert pred["claim_type"] == "employment_discrimination"
        assert pred["template_matched"] is True
        assert len(pred["fol_template"]) > 0
        assert len(pred["dcec_template"]) > 0
        assert len(pred["grounded_facts"]) > 0


def test_map_elements_unknown_element_still_produces_predicate():
    elements = [
        {"element_id": "unknown_element", "element_text": "Some unknown element", "status": "missing"},
    ]
    result = map_claim_elements_to_predicates("employment_discrimination", elements)
    assert result["predicate_count"] == 1
    assert result["template_match_count"] == 0
    assert "unknown_element" in result["unmapped_element_ids"]
    pred = result["predicates"][0]
    assert pred["template_matched"] is False
    assert pred["fol_template"] == ""


def test_map_elements_coverage_status_preserved():
    elements = [
        {"element_id": "protected_trait", "status": "supported"},
        {"element_id": "adverse_action", "status": "incomplete"},
    ]
    result = map_claim_elements_to_predicates("employment_discrimination", elements)
    statuses = {p["claim_element_id"]: p["coverage_status"] for p in result["predicates"]}
    assert statuses["protected_trait"] == "supported"
    assert statuses["adverse_action"] == "incomplete"


def test_map_elements_preserves_fact_registry_summary_for_predicates():
    elements = [
        {
            "element_id": "protected_activity",
            "element_text": "Protected activity",
            "status": "supported",
            "support_facts": [
                {
                    "fact_id": "fact-1",
                    "text": "Plaintiff reported discrimination to HR.",
                    "support_kind": "evidence",
                    "source_table": "evidence_facts",
                    "source_family": "evidence",
                    "source_record_id": 7,
                    "source_ref": "bafy-email",
                    "record_scope": "claim",
                    "artifact_family": "archived_web_page",
                    "corpus_family": "web_archive",
                    "content_origin": "historical_archive_capture",
                    "parse_source": "ipfs_datasets_py",
                    "input_format": "html",
                    "quality_tier": "high",
                    "chunk_id": "chunk-1",
                    "source_passage": {"chunk_id": "chunk-1", "text": "reported discrimination"},
                }
            ],
        }
    ]

    result = map_claim_elements_to_predicates("retaliation", elements)

    predicate = result["predicates"][0]
    assert predicate["support_facts"][0]["source_family"] == "evidence"
    assert predicate["fact_registry_summary"]["source_family_counts"] == {"evidence": 1}
    assert predicate["fact_registry_summary"]["corpus_family_counts"] == {"web_archive": 1}
    assert predicate["fact_registry_summary"]["passage_anchored_count"] == 1
    assert result["fact_registry_summary"]["artifact_family_counts"] == {"archived_web_page": 1}
    assert result["metadata"]["fact_registry_summary"]["unique_source_record_count"] == 1


def test_prove_claim_elements_preserves_fact_registry_summary():
    from integrations.ipfs_datasets.logic import prove_claim_elements

    mapped = map_claim_elements_to_predicates(
        "retaliation",
        [
            {
                "element_id": "protected_activity",
                "status": "supported",
                "support_facts": [
                    {
                        "fact_id": "fact-1",
                        "text": "Plaintiff filed a discrimination complaint.",
                        "support_kind": "evidence",
                        "source_table": "evidence_facts",
                        "source_family": "evidence",
                        "source_record_id": 9,
                        "source_ref": "bafy-complaint",
                        "record_scope": "claim",
                        "artifact_family": "archived_web_page",
                        "corpus_family": "web_archive",
                        "content_origin": "historical_archive_capture",
                        "parse_source": "ipfs_datasets_py",
                        "input_format": "html",
                        "quality_tier": "high",
                        "chunk_id": "chunk-9",
                    }
                ],
            }
        ],
    )

    proof_result = prove_claim_elements(mapped)

    assert proof_result["fact_registry_summary"]["fact_count"] == 1
    assert proof_result["fact_registry_summary"]["source_family_counts"] == {"evidence": 1}
    assert proof_result["temporal_reasoning_payload"]["fact_registry_summary"]["corpus_family_counts"] == {
        "web_archive": 1
    }
    assert proof_result["theorem_export"]["fact_registry_summary"]["source_family_counts"] == {
        "evidence": 1
    }
    claim_element = proof_result["temporal_reasoning_payload"]["claim_elements"][0]
    assert claim_element["fact_registry_summary"]["passage_anchored_count"] == 1


def test_map_elements_predicate_id_format():
    elements = [
        {"element_id": "protected_trait"},
    ]
    result = map_claim_elements_to_predicates("employment_discrimination", elements)
    pred = result["predicates"][0]
    assert "employment_discrimination" in pred["predicate_id"]
    assert "protected_trait" in pred["predicate_id"]


def test_map_elements_ready_for_prove_claim_elements():
    """Predicates produced by map_claim_elements_to_predicates should be
    accepted by prove_claim_elements without error."""
    from integrations.ipfs_datasets.logic import prove_claim_elements

    elements = [
        {"element_id": "protected_trait", "status": "supported"},
        {"element_id": "employment_relationship", "status": "supported"},
        {"element_id": "adverse_action", "status": "incomplete"},
        {"element_id": "discriminatory_motive", "status": "missing"},
    ]
    mapped = map_claim_elements_to_predicates("employment_discrimination", elements)
    predicates = mapped["predicates"]

    proof_result = prove_claim_elements(predicates)
    assert proof_result["metadata"]["implementation_status"] == "implemented"
    assert isinstance(proof_result.get("predicate_count"), int)
    assert proof_result["predicate_count"] == 4


def test_map_elements_housing_claim_type():
    elements = [
        {"element_id": "protected_trait", "status": "supported"},
        {"element_id": "housing_context", "status": "incomplete"},
        {"element_id": "adverse_action", "status": "missing"},
    ]
    result = map_claim_elements_to_predicates("housing_discrimination", elements)
    assert result["predicate_count"] == 3
    assert result["template_match_count"] == 3
    for pred in result["predicates"]:
        assert pred["claim_type"] == "housing_discrimination"


def test_predicate_templates_registry_has_all_types():
    assert "employment_discrimination" in _COMPLAINT_PREDICATE_TEMPLATES
    assert "housing_discrimination" in _COMPLAINT_PREDICATE_TEMPLATES
    assert "retaliation" in _COMPLAINT_PREDICATE_TEMPLATES
    assert "fair_housing" in _COMPLAINT_PREDICATE_TEMPLATES
