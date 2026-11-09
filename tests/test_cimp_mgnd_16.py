"""Acquire bounded canonical legal-source candidates.

Cases are synthetic private fixtures. No test is skipped. Local acquisition
reads owned fixture bytes and does not infer or download. Remote acquisition
is dispatched only after the purpose and data-class gate. A hit, snippet, or
relevance score is not applicability or proof.
"""

from __future__ import annotations

import json

import pytest

from integrations.ipfs_datasets.legal import (
    CANONICAL_CORPUS_PARAMETER_APIS,
    acquire_bounded_canonical_legal_sources,
    build_bounded_legal_acquisition_request,
    classify_legal_date,
)
from integrations.ipfs_datasets.llm import privacy_policy_for_mode
from mediator.legal_authority_hooks import LegalAuthoritySearchHook
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-mgnd-16"


def _dated(value: str, role: str):
    return classify_legal_date(value, role=role)


def _binding(case, **overrides):
    file_overrides = {
        "jurisdiction": "Oregon" if case.narrative.jurisdiction == "US-OR" else case.narrative.jurisdiction,
        "applicable_law_date": _dated("2024-03-15", "applicable_law_date"),
        "event_date": _dated("" if case.label == "baseline" else case.narrative.event_date, "event_date"),
        "filing_reference_date": _dated("2024-04-02", "filing_reference_date"),
        "corpus_retrieval_date": _dated("2024-06-01", "corpus_retrieval_date"),
    }
    if case.narrative.jurisdiction == "unknown":
        return build_bounded_legal_acquisition_request(
            {"jurisdiction": "unknown"},
            [{"claim_type": "termination", "name": "Termination"}],
            query_terms=["termination statute"],
            narrative=case.narrative.text,
            storage_available=case.storage_available,
        )
    file_overrides.update(overrides)
    return build_bounded_legal_acquisition_request(
        file_overrides,
        [{"claim_type": "termination", "name": "Termination"}],
        query_terms=["termination statute"],
        narrative=case.narrative.text,
        storage_available=case.storage_available,
    )


def _rows_for(case, **extra):
    rows = []
    for source in case.sources:
        row = {
            "text": source.source_text,
            "citation": source.citation,
            "uri": "fixture://" + source.authority_id,
            "corpus_version": source.version,
            "jurisdiction": "OR",
            "effective_date": source.effective_date,
            "applicable": True,
            "verified": True,
            "relevance": 0.99,
        }
        row.update(extra)
        rows.append(row)
    return {"state_statute": rows, "state_administrative_rule": []}


def _acquire(case, **kwargs):
    binding = _binding(case)
    payload = dict(
        owner_id=_OWNER,
        case_id=case.case_id,
        purpose="public_law_citation",
        data_class="public_legal_source_graph",
        provider_kind="local",
        retrieval_mode="cache",
        max_bytes=4096,
        deadline_seconds=2.0,
        max_results=5,
    )
    if case.label == "cancellation":
        payload["cancelled"] = True
    elif case.narrative.jurisdiction != "unknown" and case.storage_available is not False and case.label != "cancellation":
        payload["local_rows"] = _rows_for(case)
    payload.update(kwargs)
    return acquire_bounded_canonical_legal_sources(binding, **payload)


def _assert_not_proof(result, case):
    encoded = json.dumps(result, sort_keys=True, default=str)
    assert case.narrative.text not in encoded
    assert result["contains_private_narrative"] is False
    assert result["proof"] is False
    assert result["applicability"] == "unknown"
    assert result["model_inference_used"] is False
    assert result["commoncrawl_initialized"] is False
    assert result["corpus_download_started"] is False
    assert result["live_model_identity_verified"] is False
    assert result["resume"]["worker_stalled"] is False
    for candidate in result["candidates"]:
        assert candidate["source_text"]
        assert candidate["locator"]
        assert candidate["version"]
        assert candidate["retrieval"]["content_hash"]
        assert candidate["applicable"] is False
        assert candidate["verified"] is False
        assert candidate["proof"] is False
        assert candidate["support_eligible"] is False
        assert candidate["parameter_api"] in CANONICAL_CORPUS_PARAMETER_APIS.values()


def test_meaningful_cases_drive_acquisition():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    seen = []
    for case in cases:
        result = _acquire(case)
        seen.append(case.label)
        _assert_not_proof(result, case)
        if case.label == "unknown":
            assert result["status"] == "blocked"
            assert result["backend_invoked"] is False
            assert result["remote_dispatched"] is False
            assert result["resume"]["resumable"] is True
            assert result["resume"]["next_action"] == "resolve_legal_context"
        elif case.label == "storage_outage":
            assert result["status"] == "unavailable"
            assert result["error_code"] == "storage_unavailable"
            assert result["backend_invoked"] is False
            assert result["resume"]["resumable"] is True
            assert result["resume"]["next_action"] == "retry_unavailable"
        elif case.label == "cancellation":
            assert result["status"] == "cancelled"
            assert result["backend_invoked"] is False
            assert result["resume"]["next_action"] == "awaiting_user"
            assert result["resume"]["resumable"] is False
        elif case.label == "missing_authority":
            assert result["status"] == "empty"
            assert result["candidates"] == []
            assert result["backend_invoked"] is True
            assert result["remote_dispatched"] is False
            assert {item["parameter_api"] for item in result["operations"]} == {
                "search_state_law_corpus_from_parameters",
            }
            assert {item["status"] for item in result["operations"]} == {"empty"}
        else:
            assert result["status"] == "candidates"
            assert result["candidates"]
            assert result["remote_dispatched"] is False
            texts = {item["source_text"] for item in result["candidates"]}
            assert texts == {source.source_text for source in case.sources}
            versions = {item["version"] for item in result["candidates"]}
            assert versions == {source.version for source in case.sources}
            assert all(item["edition_selected"] is False for item in result["candidates"])
    assert seen == list(CASE_LABELS)


def test_snippet_relevance_and_missing_edition_are_not_owned_proof():
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    snippet = _acquire(case, local_rows={
        "state_statute": [{
            "snippet": "A covered employer must keep a written record.",
            "citation": "Synth. Or. Safety 1",
            "corpus_version": "2024-edition",
            "relevance": 1.0,
            "applicable": True,
        }],
        "state_administrative_rule": [],
    })
    assert snippet["status"] == "incomplete"
    assert snippet["candidates"] == []
    assert snippet["proof"] is False
    assert snippet["resume"]["next_action"] == "supply_owned_source_text"
    assert snippet["operations"][0]["withheld"][0]["reason"] == "snippet_not_owned"

    missing_edition = _acquire(case, local_rows={
        "state_statute": [{
            "text": case.sources[0].source_text,
            "uri": "fixture://synth-or-safety-1",
            "citation": "Synth. Or. Safety 1",
        }],
        "state_administrative_rule": [],
    })
    assert missing_edition["status"] == "missing_edition"
    assert missing_edition["error_code"] == "missing_edition"
    assert missing_edition["candidates"] == []
    assert missing_edition["resume"]["resumable"] is True
    assert missing_edition["resume"]["next_action"] == "supply_edition"
    assert missing_edition["status"] != snippet["status"]


def test_timeout_unavailable_and_empty_stay_distinct(monkeypatch):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    binding = _binding(case)

    def _timeout(**kwargs):
        return {"status": "timeout", "error_code": "timeout", "results": [], "source_family": kwargs.get("source_family")}

    monkeypatch.setattr(
        "integrations.ipfs_datasets.legal.lookup_bounded_legal_corpus",
        _timeout,
    )
    timed = acquire_bounded_canonical_legal_sources(
        binding,
        owner_id=_OWNER,
        case_id=case.case_id,
        retrieval_mode="cache",
        local_rows={"state_statute": [], "state_administrative_rule": []},
        deadline_seconds=1.0,
    )
    assert timed["status"] == "timeout"
    assert timed["error_code"] == "timeout"
    assert timed["resume"]["next_action"] == "retry_timeout"
    assert timed["commoncrawl_initialized"] is False
    assert timed["corpus_download_started"] is False

    monkeypatch.undo()
    absent = acquire_bounded_canonical_legal_sources(
        binding,
        owner_id=_OWNER,
        case_id=case.case_id,
        retrieval_mode="offline",
    )
    assert absent["status"] == "unavailable"
    assert absent["error_code"] == "offline_asset_missing"
    assert absent["backend_invoked"] is False
    assert absent["status"] != timed["status"]

    empty = _acquire(next(item for item in meaningful_cases() if item.label == "missing_authority"))
    assert empty["status"] == "empty"
    assert {empty["status"], timed["status"], absent["status"], "missing_edition"} == {
        "empty",
        "timeout",
        "unavailable",
        "missing_edition",
    }


def test_remote_gate_blocks_dispatch_until_purpose_and_data_class_pass(monkeypatch):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    binding = _binding(case)
    calls = []

    def _track(**kwargs):
        calls.append(kwargs.get("source_family"))
        text = case.sources[0].source_text
        return {
            "status": "success",
            "results": [{
                "source_family": kwargs.get("source_family"),
                "source_passage": text,
                "passage_status": "full_text",
                "uri": "fixture://remote-statute",
                "uri_status": "source",
                "citation": "Synth. Or. Safety 1",
                "citation_status": "source",
                "corpus_version": "2024-edition",
                "content_hash": "sha256:synthetic",
                "content_hash_scope": "source_passage",
                "provenance_status": "present",
                "retrieved_at": "2024-06-01T00:00:00+00:00",
                "retrieval_mode": "live",
                "applicability": "unknown",
                "jurisdiction_status": "source",
            }],
        }

    monkeypatch.setattr("integrations.ipfs_datasets.legal.lookup_bounded_legal_corpus", _track)
    refused = acquire_bounded_canonical_legal_sources(
        binding,
        owner_id=_OWNER,
        case_id=case.case_id,
        retrieval_mode="live",
        purpose="public_law_citation",
        data_class="public_legal_source_graph",
        provider_kind="legal_corpus",
        policy_reader=lambda: {"found": False},
        provider_loader=lambda: {"status": "available"},
        query_vector=[0.1, 0.2],
        collection_name="synthetic-collection",
        contains_private_facts=False,
        privacy_policy_accepted=True,
    )
    assert calls == []
    assert refused["remote_dispatched"] is False
    assert refused["backend_invoked"] is False
    assert refused["status"] == "refused"
    assert refused["model_inference_used"] is False

    record = {
        "found": True,
        "user_id": _OWNER,
        "case_id": case.case_id,
        "case_match": True,
        "privacy_policy": privacy_policy_for_mode(_OWNER, case.case_id, "grok"),
        "operation_consent": {
            "generation": 1,
            "revoked": False,
            "grants": [{
                "explicit": True,
                "tools": False,
                "purpose": "public_law_citation",
                "provider_kind": "legal_corpus",
                "data_class": "public_legal_source_graph",
            }],
        },
    }
    allowed = acquire_bounded_canonical_legal_sources(
        binding,
        owner_id=_OWNER,
        case_id=case.case_id,
        retrieval_mode="live",
        purpose="public_law_citation",
        data_class="public_legal_source_graph",
        provider_kind="legal_corpus",
        policy_reader=lambda: record,
        provider_loader=lambda: {"status": "available"},
        query_vector=[0.1, 0.2],
        collection_name="synthetic-collection",
        contains_private_facts=False,
        privacy_policy_accepted=True,
        allowed_backends=["search_state_law_corpus_from_parameters"],
    )
    assert calls
    assert allowed["remote_dispatched"] is True
    assert allowed["gate"]["code"] == "authorized"
    assert allowed["gate"]["policy_read"] is True
    assert allowed["status"] == "candidates"
    assert allowed["candidates"][0]["source_text"] == case.sources[0].source_text
    assert allowed["candidates"][0]["proof"] is False
    assert allowed["candidates"][0]["applicable"] is False
    assert allowed["live_model_identity_verified"] is False
    assert all(item["parameter_api"] == "search_state_law_corpus_from_parameters" for item in allowed["operations"] if item["backend_invoked"])
    assert all(item["corpus_download_started"] is False and item["commoncrawl_initialized"] is False for item in allowed["operations"])


def test_hook_uses_declared_apis_without_initializing_common_crawl():
    case = next(item for item in meaningful_cases() if item.label == "contradiction")
    logs = []

    class _Mediator:
        def log(self, event, **fields):
            logs.append((event, fields))

    hook = LegalAuthoritySearchHook.__new__(LegalAuthoritySearchHook)
    hook.mediator = _Mediator()
    hook.web_search = None
    result = hook.acquire_bounded_canonical_sources(
        _binding(case),
        owner_id=_OWNER,
        case_id=case.case_id,
        retrieval_mode="cache",
        local_rows=_rows_for(case),
        deadline_seconds=1.5,
        max_results=4,
        max_bytes=2048,
    )
    assert result["status"] == "candidates"
    assert len(result["candidates"]) == 2
    assert {item["parameter_api"] for item in result["operations"]} <= set(CANONICAL_CORPUS_PARAMETER_APIS.values())
    assert result["commoncrawl_initialized"] is False
    assert logs and logs[-1][0] == "legal_source_candidate_acquisition"
    assert logs[-1][1]["commoncrawl_initialized"] is False
    federal = build_bounded_legal_acquisition_request(
        {
            "jurisdiction": "federal",
            "applicable_law_date": _dated("2024-03-15", "applicable_law_date"),
            "event_date": _dated("2024-03-04", "event_date"),
            "filing_reference_date": _dated("2024-04-02", "filing_reference_date"),
            "corpus_retrieval_date": _dated("2024-06-01", "corpus_retrieval_date"),
        },
        [{"claim_type": "retaliation", "name": "Retaliation"}],
        query_terms=["retaliation statute"],
        authority_families=["statute", "regulation", "court_rule"],
    )
    covered = hook.acquire_bounded_canonical_sources(
        federal,
        owner_id=_OWNER,
        case_id=case.case_id,
        retrieval_mode="cache",
        local_rows={"us_code": [], "federal_register": [], "court_rule": []},
    )
    assert {item["parameter_api"] for item in covered["operations"]} == {
        "search_us_code_corpus_from_parameters",
        "search_federal_register_corpus_from_parameters",
        "search_court_rules_corpus_from_parameters",
    }
    assert covered["status"] == "empty"
    assert covered["corpus_download_started"] is False
