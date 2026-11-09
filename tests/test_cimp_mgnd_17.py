"""Admit acquired authorities through stored source records.

Cases are synthetic private fixtures. No test is skipped. Acquisition and
admission stay separate outcomes. Hashes are recomputed from owned bytes.
Caller verification flags, substituted metadata text, and model-invented
citations are rejected. Missing legal sources leave a nonempty unresolved
dependency graph.
"""

from __future__ import annotations

import copy

import pytest

from integrations.ipfs_datasets.legal import (
    acquire_bounded_canonical_legal_sources,
    build_bounded_legal_acquisition_request,
    classify_legal_date,
)
from integrations.ipfs_datasets.logic import prepare_acquired_authority_record, sha256_utf8
from mediator.mediator import Mediator
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-mgnd-17"
_LAW_DATE = "2024-03-15"
_CLAIM = {"type": "termination", "name": "Termination"}


class _SilentBackend:
    id = "synthetic-mgnd-17"

    def __call__(self, prompt):
        return ""


def _dated(value: str, role: str):
    return classify_legal_date(value, role=role)


def _binding(case):
    if case.narrative.jurisdiction == "unknown":
        return build_bounded_legal_acquisition_request(
            {"jurisdiction": "unknown"},
            [_CLAIM],
            query_terms=["termination statute"],
            narrative=case.narrative.text,
            storage_available=case.storage_available,
        )
    return build_bounded_legal_acquisition_request(
        {
            "jurisdiction": "Oregon",
            "applicable_law_date": _dated(_LAW_DATE, "applicable_law_date"),
            "event_date": _dated(case.narrative.event_date, "event_date"),
            "filing_reference_date": _dated("2024-04-02", "filing_reference_date"),
            "corpus_retrieval_date": _dated("2024-06-01", "corpus_retrieval_date"),
        },
        [_CLAIM],
        query_terms=["termination statute"],
        narrative=case.narrative.text,
        storage_available=case.storage_available,
    )


def _rows_for(case):
    rows = []
    for source in case.sources:
        rows.append({
            "text": source.source_text,
            "citation": source.citation,
            "uri": "fixture://" + source.authority_id,
            "corpus_version": source.version,
            "jurisdiction": "OR",
            "effective_date": source.effective_date,
        })
    return {"state_statute": rows, "state_administrative_rule": []}


def _acquire(case, **kwargs):
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
    return acquire_bounded_canonical_legal_sources(_binding(case), **payload)


def _case_file(case):
    text = case.narrative.text
    if case.narrative.jurisdiction == "US-OR":
        text += " Under Oregon law. Applicable law date: " + _LAW_DATE + "."
    return {
        "source_complaint_text": text,
        "candidate_claims": [{"claim_type": "termination", "name": "Termination"}],
    }


def _mediator(tmp_path):
    mediator = Mediator(
        [_SilentBackend()],
        evidence_db_path=str(tmp_path / "evidence.duckdb"),
        legal_authority_db_path=str(tmp_path / "authority.duckdb"),
        claim_support_db_path=str(tmp_path / "support.duckdb"),
    )
    mediator.state.username = _OWNER
    return mediator


def _nodes(graph, dependency_class):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict) and node.attributes.get("dependency_class") == dependency_class
    ]


def _admit(tmp_path, case, acquisition=None):
    mediator = _mediator(tmp_path)
    result = mediator.admit_acquired_authorities(
        acquisition if acquisition is not None else _acquire(case),
        [_CLAIM],
        _case_file(case),
        user_id=_OWNER,
    )
    return mediator, result


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id for case in cases)


def test_owned_candidate_is_stored_then_admitted(tmp_path):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    acquired = _acquire(case)
    mediator, result = _admit(tmp_path, case, acquired)
    assert result["acquisition"]["status"] == "candidates"
    assert result["acquisition"]["stage"] == "acquisition"
    assert result["admission"]["status"] == "admitted"
    assert result["admission"]["stage"] == "admission"
    assert result["acquisition"] is not result["admission"]
    assert result["acquisition"]["proof"] is False
    assert result["admission"]["proof"] is False
    assert result["admission"]["stored_record_ids"]
    source = case.sources[0]
    owned_hash = sha256_utf8(source.source_text)
    decision = result["admission"]["decisions"][0]
    assert decision["hashes"]["source_hash"] == owned_hash
    assert decision["hashes"]["authority_text_sha256"] == owned_hash
    assert decision["hashes"]["span_sha256"] == sha256_utf8(source.source_text)
    assert decision["authority_version"] == source.version
    assert decision["jurisdiction"] == "OR"
    assert decision["effective_date"] == source.effective_date
    assert decision["source_locator"] == "fixture://" + source.authority_id
    stored = mediator.get_legal_authorities(user_id=_OWNER, claim_type="termination")
    assert len(stored) == 1
    assert stored[0]["content"] == source.source_text
    assert stored[0]["metadata"]["source_hash"] == owned_hash
    assert stored[0]["metadata"]["authority_version"] == source.version
    assert stored[0]["metadata"]["source_locator"] == decision["source_locator"]
    assert stored[0]["metadata"].get("verified") is not True
    assert stored[0]["metadata"].get("applicable") is not True
    assert stored[0]["metadata"].get("support_eligible") is not True
    sourced = _nodes(result["dependency_graph"], "legally_sourced_requirement")
    assert sourced
    assert not _nodes(result["dependency_graph"], "legal_source_gap")
    proof = sourced[0].attributes
    assert proof["source_hash"] == owned_hash
    assert proof["authority_version"] == source.version
    assert proof["jurisdiction"] == "OR"
    assert proof["source_record"]["source_text"] == source.source_text
    span = proof["source_span"]
    assert source.source_text.encode("utf-8")[span["start"]:span["end"]].decode("utf-8") == proof["rule_text"]
    assert proof["span_sha256"] == sha256_utf8(proof["rule_text"])
    assert result["dependency_graph"].metadata["acquisition_status"] == "candidates"
    assert result["dependency_graph"].metadata["admission_status"] == "admitted"


def test_caller_flags_substituted_text_and_invented_citations_are_rejected(tmp_path):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    acquired = _acquire(case)
    candidate = copy.deepcopy(acquired["candidates"][0])
    flagged = copy.deepcopy(acquired)
    flagged["candidates"] = [dict(candidate, verified=True, applicable=True, support_eligible=True)]
    _mediator_flagged, flagged_result = _admit(tmp_path, case, flagged)
    assert flagged_result["admission"]["status"] == "rejected"
    assert flagged_result["admission"]["reason"] == "caller_verification_flag"
    assert flagged_result["admission"]["stored_record_ids"] == []
    assert not _nodes(flagged_result["dependency_graph"], "legally_sourced_requirement")
    assert _nodes(flagged_result["dependency_graph"], "legal_source_gap")
    assert flagged_result["dependency_graph"].nodes

    substituted = copy.deepcopy(acquired)
    substituted["candidates"] = [dict(candidate, metadata={"source_text": "A model rewrote this statute."})]
    prepared = prepare_acquired_authority_record(
        substituted["candidates"][0], jurisdiction="OR", as_of_date=_LAW_DATE,
    )
    assert prepared["status"] == "rejected"
    assert prepared["reason"] == "substituted_metadata_text"
    assert prepared["record"] is None

    invented = copy.deepcopy(acquired)
    invented["candidates"] = [dict(candidate, citation="42 U.S.C. § 1983")]
    prepared_citation = prepare_acquired_authority_record(
        invented["candidates"][0], jurisdiction="OR", as_of_date=_LAW_DATE,
    )
    assert prepared_citation["status"] == "rejected"
    assert prepared_citation["reason"] == "model_invented_citation"

    mismatched = copy.deepcopy(acquired)
    bad = copy.deepcopy(candidate)
    bad["retrieval"] = dict(candidate["retrieval"], content_hash="sha256:" + ("ab" * 32))
    mismatched["candidates"] = [bad]
    _mediator_hash, hash_result = _admit(tmp_path / "hash", case, mismatched)
    assert hash_result["admission"]["status"] == "rejected"
    assert hash_result["admission"]["decisions"][0]["reason"] == "caller_hash_mismatch"
    assert hash_result["admission"]["stored_record_ids"] == []


def test_each_case_keeps_acquisition_distinct_from_admission(tmp_path):
    seen = []
    for case in meaningful_cases():
        mediator, result = _admit(tmp_path / case.label, case)
        seen.append(case.label)
        graph = result["dependency_graph"]
        assert graph.nodes
        assert result["acquisition"]["proof"] is False
        assert result["admission"]["proof"] is False
        assert result["acquisition"]["worker_stalled"] is False
        assert result["admission"]["worker_stalled"] is False
        assert result["acquisition"]["stage"] != result["admission"]["stage"]
        unresolved = _nodes(graph, "unresolved_legal_requirement") + _nodes(graph, "legal_source_gap")
        if case.label == "baseline":
            assert result["acquisition"]["status"] == "candidates"
            assert result["admission"]["status"] == "admitted"
            assert _nodes(graph, "legally_sourced_requirement")
        elif case.label == "contradiction":
            assert result["acquisition"]["status"] == "candidates"
            assert result["admission"]["status"] == "admitted"
            assert len(result["admission"]["stored_record_ids"]) == 2
            assert _nodes(graph, "legally_sourced_requirement")
        elif case.label == "missing_authority":
            assert result["acquisition"]["status"] == "empty"
            assert result["admission"]["status"] == "empty"
            assert result["admission"]["stored_record_ids"] == []
            assert unresolved
            assert not _nodes(graph, "legally_sourced_requirement")
        elif case.label == "unknown":
            assert result["acquisition"]["status"] == "blocked"
            assert result["admission"]["status"] == "not_admitted"
            assert result["admission"]["reason"] == "legal_context_not_ready"
            assert unresolved
        elif case.label == "cancellation":
            assert result["acquisition"]["status"] == "cancelled"
            assert result["admission"]["status"] == "not_admitted"
            assert result["admission"]["reason"] == "cancelled"
            assert unresolved or _nodes(graph, "legal_source_gap") or _nodes(graph, "unresolved_legal_requirement")
        elif case.label == "storage_outage":
            assert result["acquisition"]["status"] == "unavailable"
            assert result["admission"]["status"] == "not_admitted"
            assert result["admission"]["reason"] == "storage_unavailable"
            assert mediator.get_legal_authorities(user_id=_OWNER, claim_type="termination") == []
        else:
            raise AssertionError(case.label)
    assert seen == list(CASE_LABELS)
