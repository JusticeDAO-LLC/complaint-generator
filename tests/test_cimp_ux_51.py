"""CIMP-UX-51: grounded classification, statute, requirement, and question hooks."""

from __future__ import annotations

import copy

import pytest

from integrations.ipfs_datasets.logic import sha256_utf8
from mediator.hook_runtime import qualify_grounded_legal_hooks


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

RULE = "An employer shall not retaliate against an employee for opposing an unlawful practice."


def _authority(**overrides):
    payload = {
        "source_text": RULE,
        "jurisdiction": "OR",
        "authority_id": "ors:659A.030",
        "citation": "ORS 659A.030",
        "authority_version": "2024-edition",
        "source_hash": sha256_utf8(RULE),
        "effective_date": "2024-01-01",
        "as_of_date": "2024-06-01",
    }
    payload.update(overrides)
    return payload


def _payload(**overrides):
    body = {
        "narrative": "The employer fired the complainant after the complainant reported a grievance.",
        "jurisdiction": "OR",
        "applicable_law_date": "2024-06-01",
        "context_revision": 1,
        "claim_candidates": ["retaliation"],
        "admitted_authorities": [_authority()],
        "model_text": "The court must enter judgment for the plaintiff.",
        "model_requirements": ["Protected class membership is automatically proven."],
        "corpus_query": "retaliation",
        "offline_cache": {
            "state_statute|retaliation|or|OR": [
                {
                    "citation": "ORS 659A.030",
                    "snippet": "Discovery snippet only.",
                    "jurisdiction": "OR",
                }
            ]
        },
        "inquiry_cap": 4,
        "capability_available": True,
    }
    body.update(overrides)
    return body


def test_admitted_authority_grounds_requirements_and_cache_hit_stays_discovery():
    payload = _payload()
    snapshot = copy.deepcopy(payload)
    receipt = qualify_grounded_legal_hooks(payload)
    assert payload == snapshot
    assert receipt["status"] == "qualified"
    assert receipt["code"] == "grounded"
    assert receipt["workflow"] == "qualify_grounded_legal_hooks"
    assert receipt["provider_invoked"] is False
    assert receipt["handler_enabled_by_caller"] is False
    assert receipt["classification"]["record_kind"] == "classifier_suggestion"
    assert receipt["classification"]["creates_law"] is False
    assert receipt["classification"]["jurisdiction"] == "OR"
    assert receipt["factual_assertion"]["record_kind"] == "factual_assertion"
    assert receipt["factual_assertion"]["creates_law"] is False
    assert receipt["statute_discovery"]["tool"] == "lookup_bounded_legal_corpus"
    assert receipt["statute_discovery"]["discovery_only"] is True
    assert receipt["statute_discovery"]["creates_law"] is False
    assert receipt["statute_discovery"]["result_count"] == 1
    assert receipt["statute_discovery"]["citations"] == ["ORS 659A.030"]
    assert receipt["legal_element_count"] == 1
    assert receipt["model_text_created_law"] is False
    assert receipt["default_taxonomy_created_law"] is False
    assert receipt["taxonomy_names_in_legal_elements"] == []
    assert "Protected Class Membership" in receipt["taxonomy_names"]
    assert receipt["factual_legal_separated"] is True
    assert receipt["factual_nodes"]
    assert all(node["law_derived"] is False for node in receipt["factual_nodes"])
    assert any(node["record_kind"] == "legal_requirement" for node in receipt["legal_nodes"])
    assert receipt["inquiries"]
    assert len(receipt["inquiries"]) <= receipt["inquiry_cap"]
    assert all(item["creates_law"] is False and item["finite"] is True for item in receipt["inquiries"])
    assert all(item["record_kind"] != "legal_requirement" for item in receipt["inquiries"])


def test_unknown_context_is_explicit_and_does_not_search():
    payload = _payload(jurisdiction="not-a-jurisdiction", applicable_law_date="", admitted_authorities=[])
    receipt = qualify_grounded_legal_hooks(payload)
    assert receipt["status"] == "qualified"
    assert receipt["code"] == "unknown_legal_context"
    assert receipt["classification"]["jurisdiction"] == "unknown"
    assert receipt["classification"]["jurisdiction_explicit"] is False
    assert receipt["tool_calls"] == 0
    assert receipt["legal_element_count"] == 0
    assert receipt["statute_discovery"]["status"] == "not_called"
    assert receipt["inquiries"][0]["record_kind"] == "unknown_legal_context"
    assert receipt["inquiries"][0]["creates_law"] is False
    assert receipt["model_text_created_law"] is False


def test_input_dto_is_not_mutated():
    payload = _payload()
    nested = payload["admitted_authorities"][0]
    before_nested = copy.deepcopy(nested)
    qualify_grounded_legal_hooks(payload)
    assert nested == before_nested
    assert payload["model_text"] == "The court must enter judgment for the plaintiff."
    payload["narrative"] += " extra"
    assert payload["narrative"].endswith(" extra")


def test_inquiry_cap_stops_further_questions():
    payload = _payload(inquiry_cap=1)
    receipt = qualify_grounded_legal_hooks(payload)
    assert len(receipt["inquiries"]) == 1
    assert receipt["inquiry_truncated"] is True
    assert receipt["inquiry_semantics"] == "capped"
    assert receipt["inquiries"][0]["sequence"] == 1


def test_model_text_and_taxonomy_do_not_create_law_without_authority():
    payload = _payload(admitted_authorities=[], offline_cache={})
    receipt = qualify_grounded_legal_hooks(payload)
    assert receipt["status"] == "qualified"
    assert receipt["legal_element_count"] == 0
    assert receipt["statute_discovery"]["result_count"] == 0
    assert receipt["model_text_created_law"] is False
    assert receipt["default_taxonomy_created_law"] is False
    assert receipt["taxonomy_names_in_legal_elements"] == []
    assert any(reason for reason in receipt["unresolved_reasons"])
    assert "model_or_taxonomy_text_is_not_law" in receipt["unresolved_reasons"] or "summary_judgment_string_is_not_authority" in receipt["unresolved_reasons"]


def test_missing_corpus_tool_is_unavailable_despite_caller_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("integrations.ipfs_datasets.legal.lookup_bounded_legal_corpus", None)
    payload = _payload(capability_available=True)
    receipt = qualify_grounded_legal_hooks(payload)
    assert receipt["status"] == "unavailable"
    assert receipt["code"] == "missing_capability"
    assert receipt["legal_element_count"] == 0
    assert receipt["creates_law"] is False
    assert receipt["provider_invoked"] is False
    assert payload["capability_available"] is True
