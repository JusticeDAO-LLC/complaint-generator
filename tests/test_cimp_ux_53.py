"""CIMP-UX-53: admitted claim support and legal authority lineage."""

from __future__ import annotations

import copy

import pytest

from integrations.ipfs_datasets.logic import sha256_utf8
from mediator.hook_runtime import qualify_claim_support_and_legal_authority


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

RULE = "An employer shall not retaliate against an employee for opposing an unlawful practice."
OTHER = "An employer shall post a notice describing the retaliation remedy."


def _passage(text: str = RULE, **overrides):
    body = {
        "passage_id": "passage-retaliation",
        "text": text,
        "citation": "ORS 659A.030",
        "requirement_id": "req-retaliation",
        "source_version": "2024-edition",
        "definition_version": "def-3",
        "source_hash": sha256_utf8(text),
    }
    body.update(overrides)
    return body


def _lineage(**overrides):
    body = {
        "lineage_id": "lin-1",
        "requirement_id": "req-retaliation",
        "passage_id": "passage-retaliation",
        "fact_id": "fact-1",
        "evidence_ref": "artifact-1",
        "source_version": "2024-edition",
        "definition_version": "def-3",
        "source_hash": sha256_utf8(RULE),
    }
    body.update(overrides)
    return body


def _payload(**overrides):
    body = {
        "user_id": "actor-53",
        "complaint_id": "case-53",
        "claim_type": "retaliation",
        "admitted_passages": [_passage()],
        "support_lineage": [_lineage()],
        "search_hits": [{
            "citation": "ORS 659A.030",
            "snippet": "A search snippet is not the statute.",
            "cache_generation": "fresh",
            "governing_authority": True,
            "verified_support": True,
        }],
        "stale_cache": [{
            "passage_id": "passage-retaliation",
            "requirement_id": "req-retaliation",
            "source_version": "2018-edition",
            "definition_version": "def-1",
            "governing_authority": True,
        }],
        "suggestions": [{
            "requirement_id": "req-retaliation",
            "text": "Treat the search hit as governing authority.",
            "verified_support": True,
        }],
        "caller_flags": {"verified_support": True, "governing_authority": True},
        "source_drift": [],
        "contradictions": [],
    }
    body.update(overrides)
    return body


def test_admitted_lineage_qualifies_support_and_ignores_search_materials():
    payload = _payload()
    snapshot = copy.deepcopy(payload)
    receipt = qualify_claim_support_and_legal_authority(payload)
    assert payload == snapshot
    assert receipt["status"] == "qualified"
    assert receipt["code"] == "grounded"
    assert receipt["workflow"] == "qualify_claim_support_and_legal_authority"
    assert receipt["provider_invoked"] is False
    assert receipt["handler_enabled_by_caller"] is False
    assert receipt["caller_flags_applied"] is False
    assert receipt["proof"] is False
    assert receipt["legal_sufficiency"] is False
    assert receipt["governing_count"] == 1
    assert receipt["verified_support"] is True
    link = receipt["claim_support"]["verified_links"][0]
    assert link["requirement_id"] == "req-retaliation"
    assert link["passage_id"] == "passage-retaliation"
    assert link["source_version"] == "2024-edition"
    assert link["definition_version"] == "def-3"
    assert link["source_hash"] == sha256_utf8(RULE)
    assert link["lineage_id"] == "lin-1"
    assert link["fact_id"] == "fact-1"
    assert link["evidence_ref"] == "artifact-1"
    assert link["record_id"] not in (None, -1)
    stored = receipt["storage"]["stored_passages"][0]
    assert stored["status"] == "stored"
    assert stored["record_id"] not in (None, -1)
    assert receipt["storage"]["search_hits_stored"] == 0
    assert receipt["storage"]["refused_search_hits"][0]["reason"] == "caller_verification_flag"
    assert receipt["storage"]["refused_search_hits"][0]["record_id"] == -1
    materials = receipt["materials"]
    assert materials["owner"] == "LegalAuthoritySearchHook"
    assert materials["governing_authority"] is False
    assert materials["verified_support"] is False
    assert materials["search_hits"][0]["governing_authority"] is False
    assert materials["stale_cache"][0]["projection_status"] == "retired"
    assert materials["stale_cache"][0]["retirement_reason"] == "stale_cache"
    assert materials["suggestions"][0]["governing_authority"] is False
    assert materials["caller_flags_seen"]["verified_support"] is True
    assert receipt["search_hit_governing"] is False
    assert receipt["suggestion_governing"] is False
    assert receipt["stale_cache_governing"] is False


def test_caller_flag_without_lineage_is_not_verified_support():
    payload = _payload(support_lineage=[])
    receipt = qualify_claim_support_and_legal_authority(payload)
    assert receipt["status"] == "qualified"
    assert receipt["code"] == "unverified"
    assert receipt["governing_authority"] is False
    assert receipt["verified_support"] is False
    assert receipt["claim_support"]["verified_support_count"] == 0
    assert receipt["storage"]["stored_passages"][0]["status"] == "stored"
    projection = receipt["projections"][0]
    assert projection["requirement_id"] == "req-retaliation"
    assert projection["source_version"] == "2024-edition"
    assert projection["definition_version"] == "def-3"
    assert projection["verified_support"] is False
    assert projection["governing_authority"] is False


def test_source_drift_retires_projection_despite_matching_lineage():
    payload = _payload(source_drift=[{
        "passage_id": "passage-retaliation",
        "source_version": "2025-edition",
        "source_hash": sha256_utf8(RULE + " amended"),
    }])
    receipt = qualify_claim_support_and_legal_authority(payload)
    assert receipt["code"] == "retired"
    assert receipt["governing_authority"] is False
    assert receipt["verified_support"] is False
    projection = receipt["projections"][0]
    assert projection["projection_status"] == "retired"
    assert projection["retirement_reason"] == "source_drift"
    assert projection["governing_authority"] is False
    retired = receipt["claim_support"]["retired_links"][0]
    assert retired["requirement_id"] == "req-retaliation"
    assert retired["retirement_reason"] == "source_drift"
    assert retired["verified_support"] is False
    assert retired["record_id"] not in (None, -1)


def test_contradictory_admitted_texts_retire_the_requirement():
    payload = _payload(admitted_passages=[
        _passage(),
        _passage(text=OTHER, passage_id="passage-notice", citation="ORS 659A.030 notice"),
    ])
    receipt = qualify_claim_support_and_legal_authority(payload)
    assert receipt["code"] == "retired"
    assert receipt["governing_count"] == 0
    assert receipt["verified_support"] is False
    assert len(receipt["projections"]) == 2
    assert {row["retirement_reason"] for row in receipt["projections"]} == {"contradiction"}
    assert all(row["governing_authority"] is False for row in receipt["projections"])
    assert receipt["claim_support"]["verified_support_count"] == 0
    assert receipt["claim_support"]["retired_count"] == 2


def test_hash_mismatch_is_not_admitted_and_input_stays_intact():
    payload = _payload(admitted_passages=[_passage(source_hash="0" * 64)], support_lineage=[])
    nested = payload["admitted_passages"][0]["text"]
    receipt = qualify_claim_support_and_legal_authority(payload)
    assert payload["admitted_passages"][0]["text"] == nested
    assert payload["caller_flags"]["verified_support"] is True
    assert receipt["governing_authority"] is False
    assert receipt["verified_support"] is False
    assert receipt["storage"]["stored_passages"] == []
    assert receipt["projections"][0]["retirement_reason"] == "source_drift"
    assert receipt["projections"][0]["verified_support"] is False


def test_missing_requirement_id_does_not_qualify():
    passage = _passage()
    del passage["requirement_id"]
    payload = _payload(admitted_passages=[passage], support_lineage=[])
    receipt = qualify_claim_support_and_legal_authority(payload)
    assert receipt["status"] == "qualified"
    assert receipt["code"] == "no_admitted_passage"
    assert receipt["passages"] == []
    assert receipt["governing_authority"] is False
    assert receipt["claim_support"]["stored_count"] == 0
    assert receipt["materials"]["search_hits"][0]["creates_law"] is False


def test_malformed_payload_is_refused():
    receipt = qualify_claim_support_and_legal_authority(["not", "a", "mapping"])  # type: ignore[arg-type]
    assert receipt["status"] == "refused"
    assert receipt["code"] == "malformed_input"
    assert receipt["governing_authority"] is False
    assert receipt["verified_support"] is False
    assert receipt["provider_invoked"] is False
