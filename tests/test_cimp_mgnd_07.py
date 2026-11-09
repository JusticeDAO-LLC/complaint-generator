"""Bounded sanitized receipts for legal and evidence hook outcomes.

Cases are synthetic private fixtures. No test is skipped. Receipts record
operation, request, revision, and outcome in order. Empty search, source
failure, and rejected admission stay distinct. Error text and tool payloads
are not logged.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
from mediator.hook_runtime import (
    LEGAL_EVIDENCE_OPERATIONS,
    bind_hook_execution_context,
    record_bounded_hook_outcome,
)
from mediator.mediator import Mediator
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 12, 1, tzinfo=timezone.utc)
_SECRET = "PRIVATE-PROMPT-do-not-echo"
_KINDS = ("operation", "request", "revision", "outcome")


class _SilentBackend:
    def __call__(self, prompt, **kwargs):
        raise AssertionError("hook outcome recording called a backend")


def _privacy(owner_id: str, case_id: str):
    policy = privacy_policy_for_mode(owner_id, case_id, "local")
    return build_complaint_privacy_context(policy, user_id=owner_id, case_id=case_id, data_class="fact_kg")


def _legal_context(case) -> dict:
    event = case.narrative.event_date
    return {
        "status": "explicit" if event and case.narrative.jurisdiction != "unknown" else "unknown",
        "jurisdiction": case.narrative.jurisdiction,
        "jurisdiction_explicit": case.narrative.jurisdiction != "unknown",
        "context_revision": 1,
        "applicable_law_date": {"role": "applicable_law_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "event_date": {"role": "event_date", "raw_text": event, "start_date": event, "end_date": event, "is_uncertain": not bool(event)},
        "filing_reference_date": {"role": "filing_reference_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "corpus_retrieval_date": {"role": "corpus_retrieval_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "questions": [_SECRET],
    }


def _bindings(case) -> list[dict]:
    if not case.sources:
        return [{"source_id": f"src-{case.label}", "content_hash": "ab" * 32}]
    return [
        {"source_id": source.authority_id, "content_hash": source.source_sha256, "source_text": source.source_text}
        for source in case.sources
    ]


def _source_refs(case) -> list[dict]:
    return [{"source_id": row["source_id"], "content_hash": row["content_hash"]} for row in _bindings(case)]


def _bind(case, operation: str):
    owner_id = "synthetic-owner"
    return bind_hook_execution_context(
        operation=operation,
        owner_id=owner_id,
        case_id=case.case_id,
        session_id=f"session-{case.label}",
        session_revision=2,
        graph_revision=f"gr-{case.label}-1",
        legal_context=_legal_context(case),
        purpose=operation,
        deadline=_DEADLINE,
        source_bindings=_bindings(case),
        privacy_context=_privacy(owner_id, case.case_id),
    )


def _request(case, operation: str):
    body = {
        "operation": operation,
        "role": "extract_facts",
        "target_ref": f"target.{case.label}",
        "source_refs": _source_refs(case),
    }
    if operation == "acquire_legal_sources":
        body["citation_ref"] = f"cite.{case.label}"
    elif operation == "ingest_private_evidence":
        body["evidence_ref"] = f"evidence.{case.label}"
    else:
        body["graph_revision"] = f"gr-{case.label}-1"
    return body


def _auth(case, context, **overrides):
    fields = {
        "context": context,
        "owner_id": context.owner_id,
        "case_id": context.case_id,
        "session_id": context.session_id,
        "session_revision": context.session_revision,
        "graph_revision": context.graph_revision,
        "legal_context": _legal_context(case),
        "purpose": context.purpose,
        "source_bindings": _bindings(case),
        "privacy_context": _privacy(context.owner_id, context.case_id),
        "now": _NOW,
        "host_targets": (f"target.{case.label}",),
        "storage_available": True,
        "request_state": "active",
        "key_available": True,
        "private_store_available": True,
        "derived_index_ready": True,
    }
    fields.update(overrides)
    return fields


def _mediator(tmp_path, case):
    mediator = Mediator(
        [_SilentBackend()],
        evidence_db_path=tmp_path / "evidence.db",
        legal_authority_db_path=tmp_path / "authority.db",
        claim_support_db_path=tmp_path / "support.db",
    )
    mediator._interview_privacy_context = _privacy("synthetic-owner", case.case_id)
    mediator.workflow_actions._interview_meta = {"session_revision": 2}
    return mediator


def _assert_private(payload, case) -> None:
    encoded = json.dumps(payload, sort_keys=True, default=str)
    assert _SECRET not in encoded
    assert case.narrative.text not in encoded
    for source in case.sources:
        assert source.source_text not in encoded
    assert "tool_calls" not in encoded
    assert "fallback_provider" not in encoded


def _assert_ordered(trace: dict, *, terminal: str) -> dict:
    assert trace["schema"] == "hook_dispatch_trace_v1"
    assert trace["ordered"] is True
    assert trace["terminal"] == terminal
    assert trace["hides_failure"] is False
    assert trace["provider_invoked"] is False
    assert trace["fallback_used"] is False
    assert trace["retry_count"] == 0
    receipts = trace["receipts"]
    assert [item["kind"] for item in receipts] == list(_KINDS)
    assert [item["ordinal"] for item in receipts] == [1, 2, 3, 4]
    outcome = receipts[3]
    assert outcome["status"] == terminal
    assert outcome["backend_completed"] is False
    assert outcome["effect_dispatched"] is False
    assert outcome["requirements_satisfied"] is False
    assert outcome["tool_payload_logged"] is False
    assert outcome["retry_count"] == 0
    if terminal != "successful":
        assert all(item["status"] != "successful" for item in receipts)
    return outcome


def test_stage_distinctions_are_not_collapsed(tmp_path):
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    mediator = _mediator(tmp_path, cases[0])
    seen = []
    for case in cases:
        operation = LEGAL_EVIDENCE_OPERATIONS[len(seen) % len(LEGAL_EVIDENCE_OPERATIONS)]
        empty = mediator.record_bounded_hook_outcome({
            "operation": operation,
            "terminal": "empty",
            "source_search": "empty",
            "admission": "not_run",
            "session_revision": 2,
            "graph_revision": f"gr-{case.label}-1",
            "counts": {"seen": 0, "admitted": 0, "errors": 0},
            "error_text": _SECRET,
            "tools": [{"name": "search", "payload": case.narrative.text}],
        })
        failed = mediator.record_bounded_hook_outcome({
            "operation": operation,
            "terminal": "successful",
            "source_search": "failed",
            "admission": "not_run",
            "code": "successful",
            "session_revision": 2,
            "graph_revision": f"gr-{case.label}-1",
            "error_text": f"{_SECRET} source exploded",
            "error_type": "RuntimeError",
        })
        rejected = mediator.record_bounded_hook_outcome({
            "operation": operation,
            "terminal": "successful",
            "source_search": "found",
            "admission": "rejected",
            "session_revision": 2,
            "graph_revision": f"gr-{case.label}-1",
            "counts": {"seen": 2, "admitted": 9, "errors": 0},
            "tool_payload": {"prompt": _SECRET},
        })
        empty_outcome = _assert_ordered(empty, terminal="empty")
        failed_outcome = _assert_ordered(failed, terminal="unavailable")
        rejected_outcome = _assert_ordered(rejected, terminal="denied")
        assert empty["code"] == "empty_source_search"
        assert empty_outcome["source_search"] == "empty"
        assert empty_outcome["admission"] == "not_run"
        assert failed["code"] == "source_failure"
        assert failed_outcome["source_search"] == "failed"
        assert failed_outcome["error_type"] == "RuntimeError"
        assert rejected["code"] == "rejected_admission"
        assert rejected_outcome["source_search"] == "found"
        assert rejected_outcome["admission"] == "rejected"
        assert rejected_outcome["counts"]["seen"] == 2
        assert rejected_outcome["counts"]["admitted"] == 2
        assert empty["terminal"] != failed["terminal"] != rejected["terminal"]
        for trace in (empty, failed, rejected):
            _assert_private(trace, case)
        seen.append(case.label)
    assert seen
    logs = [item for item in mediator.state.log if item.get("type") == "legal_evidence_hook_outcome"]
    assert len(logs) == len(cases) * 3
    _assert_private(logs, cases[0])
    assert {item["terminal"] for item in logs} == {"empty", "unavailable", "denied"}
    assert {item["code"] for item in logs} >= {"empty_source_search", "source_failure", "rejected_admission"}
    assert all(item["tool_payload_logged"] is False and item["prompt_logged"] is False for item in logs)
    assert all(item["retry_count"] == 0 and item["fallback_used"] is False and item["provider_invoked"] is False for item in logs)


def test_dispatcher_records_each_result_class(tmp_path):
    cases = meaningful_cases()
    assert cases
    mediator = _mediator(tmp_path, cases[0])
    recorded = []
    for case in cases:
        operation = "acquire_legal_sources" if case.label != "storage_outage" else "refresh_grounding"
        context = _bind(case, operation)
        common = _auth(case, context)
        if case.label == "baseline":
            result = mediator.dispatch_registered_legal_evidence_hook(_request(case, operation), **common)
            assert result["status"] == "unavailable"
            assert result["code"] == "prerequisite_unavailable"
            outcome = _assert_ordered(result["trace"], terminal="unavailable")
            assert outcome["source_search"] == "not_run"
            assert outcome["admission"] == "not_run"
            assert outcome["code"] == "prerequisite_unavailable"
        elif case.label == "missing_authority":
            result = mediator.dispatch_registered_legal_evidence_hook(
                _request(case, operation),
                **_auth(case, context, privacy_context=None),
            )
            assert result["status"] == "refused"
            assert result["code"] == "consent_missing"
            _assert_ordered(result["trace"], terminal="denied")
            assert result["trace"]["code"] == "consent_missing"
        elif case.label == "contradiction":
            result = mediator.dispatch_registered_legal_evidence_hook({"operation": operation, "tools": [_SECRET]}, **common)
            assert result["code"] == "model_cannot_invoke_tools"
            outcome = _assert_ordered(result["trace"], terminal="denied")
            assert result["trace"]["receipts"][2]["status"] == "not_reached"
            assert outcome["source_search"] == "not_run"
        elif case.label == "unknown":
            result = mediator.dispatch_registered_legal_evidence_hook(None, **common)
            assert result["code"] == "malformed"
            _assert_ordered(result["trace"], terminal="malformed")
            assert result["trace"]["receipts"][0]["operation"] == ""
        elif case.label == "cancellation":
            result = mediator.dispatch_registered_legal_evidence_hook(
                _request(case, operation),
                **_auth(case, context, request_state="cancelled"),
            )
            assert result["status"] == "cancelled"
            assert result["code"] == "cancelled"
            _assert_ordered(result["trace"], terminal="cancelled")
        else:
            result = mediator.dispatch_registered_legal_evidence_hook(
                _request(case, operation),
                **_auth(case, context, request_state="timeout"),
            )
            assert result["status"] == "timeout"
            assert result["code"] == "timeout"
            outcome = _assert_ordered(result["trace"], terminal="timeout")
            assert outcome["error_type"] == "TimeoutError"
            assert outcome["source_search"] == "not_run"
        assert result["provider_invoked"] is False
        assert result["effect_dispatched"] is False
        assert result["writes"] == 0
        assert result["trace"]["receipts"][2]["graph_revision"] == f"gr-{case.label}-1" or result["code"] in {
            "malformed",
            "model_cannot_invoke_tools",
        }
        _assert_private(result, case)
        recorded.append(result["trace"]["terminal"])
    assert recorded == ["unavailable", "denied", "denied", "malformed", "cancelled", "timeout"]
    logs = [item for item in mediator.state.log if item.get("type") == "legal_evidence_hook_outcome"]
    assert [item["terminal"] for item in logs] == recorded
    assert all(item["response_logged"] is False and item["tool_payload_logged"] is False for item in logs)
    _assert_private(logs, cases[0])


def test_success_requires_found_and_admitted_stages():
    cases = meaningful_cases()
    assert cases
    case = cases[0]
    hidden = record_bounded_hook_outcome({
        "operation": "ingest_private_evidence",
        "terminal": "successful",
        "source_search": "not_run",
        "admission": "not_run",
        "session_revision": 2,
        "graph_revision": f"gr-{case.label}-1",
        "retry": True,
        "fallback_provider": "other-provider",
        "error_text": _SECRET,
        "counts": {"seen": 10**9, "admitted": 10**9, "errors": 0},
    })
    outcome = _assert_ordered(hidden, terminal="unavailable")
    assert hidden["code"] == "stage_not_observed"
    assert outcome["counts"]["seen"] == 64
    assert outcome["counts"]["admitted"] == 64
    assert outcome["backend_completed"] is False
    clean = record_bounded_hook_outcome({
        "operation": "ingest_private_evidence",
        "terminal": "successful",
        "source_search": "found",
        "admission": "admitted",
        "session_revision": 2,
        "graph_revision": f"gr-{case.label}-1",
        "request_id": "ab" * 16,
        "counts": {"seen": 1, "admitted": 1, "errors": 4},
        "error_type": f"Boom{_SECRET}",
    })
    clean_outcome = _assert_ordered(clean, terminal="successful")
    assert clean_outcome["source_search"] == "found"
    assert clean_outcome["admission"] == "admitted"
    assert clean_outcome["counts"]["errors"] == 0
    assert clean_outcome["error_type"] == ""
    assert clean["request_id"] == "ab" * 16
    assert clean["receipts"][0]["status"] == "recorded"
    _assert_private([hidden, clean], case)
    stale = record_bounded_hook_outcome({
        "operation": "refresh_grounding",
        "terminal": "denied",
        "code": "stale_revision",
        "revision_status": "denied",
        "source_search": "not_run",
        "admission": "not_run",
        "session_revision": 2,
        "graph_revision": _SECRET,
    })
    stale_outcome = _assert_ordered(stale, terminal="denied")
    assert stale["code"] == "stale_revision"
    assert stale["receipts"][2]["status"] == "denied"
    assert stale["receipts"][2]["graph_revision"] == ""
    assert stale_outcome["status"] != "successful"
    _assert_private(stale, case)
