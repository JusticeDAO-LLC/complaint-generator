"""Per-case consent is read before new remote hook work.

Cases are synthetic private fixtures. No test is skipped. A synthetic
provider loader never verifies a live Grok model.
"""

from __future__ import annotations

import json

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService
from integrations.ipfs_datasets.llm import (
    clear_remote_invocation_bindings,
    privacy_policy_for_mode,
)
from mediator.hook_runtime import accept_late_hook_result, prepare_remote_hook_query
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-owner"
_COMPLAINT = "PRIVATE-COMPLAINT-BODY-should-not-leak"
_CITATION = "Synthetic Code 1"


def setup_function() -> None:
    clear_remote_invocation_bindings()


def _record(case, mode: str, *, consent=None, found: bool = True, case_match: bool = True, case_id: str | None = None):
    case_id = case.case_id if case_id is None else case_id
    policy = privacy_policy_for_mode(_OWNER, case_id, mode)
    if consent is None:
        consent = {
            "generation": 1,
            "revoked": False,
            "grants": [],
        }
    return {
        "found": found,
        "user_id": _OWNER,
        "case_id": case_id,
        "case_match": case_match,
        "privacy_policy": policy,
        "operation_consent": consent,
    }


def _run(case, record, *, purpose, provider_kind, data_class, tools=False, citation=None, private_fields=None, loader_status="available"):
    log: list[str] = []
    submitted: list[dict] = []

    def reader():
        log.append("policy")
        return record

    def loader():
        log.append("provider")
        if loader_status == "raise":
            raise RuntimeError("synthetic provider missing")
        return {"status": loader_status}

    def submit(query):
        log.append("query")
        submitted.append(query)

    result = prepare_remote_hook_query(
        policy_reader=reader,
        provider_loader=loader,
        query_submitter=submit,
        owner_id=_OWNER,
        case_id=case.case_id,
        purpose=purpose,
        provider_kind=provider_kind,
        data_class=data_class,
        tools=tools,
        citation=citation,
        complaint_text=_COMPLAINT,
        private_fields=private_fields,
    )
    return log, submitted, result


def test_meaningful_cases_are_collected_without_skips():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id and case.label for case in cases)


def test_policy_is_read_before_provider_and_query_for_every_case():
    seen = []
    for case in meaningful_cases():
        log, submitted, result = _run(
            case,
            _record(case, "grok"),
            purpose="extract_facts",
            provider_kind="grok_inference",
            data_class="raw_intake",
            private_fields={"source_text": "safety report", "target_ref": f"target.{case.label}", "complaint": case.narrative.text},
        )
        assert log == ["policy", "provider", "query"]
        assert result["policy_read"] is True
        assert result["provider_loader_called"] is True
        assert result["query_submitted"] is True
        assert result["effectful"] is True
        assert result["code"] == "authorized"
        assert result["live_model_identity_verified"] is False
        assert result["tools_authorized"] is False
        assert result["complaint_included"] is False
        assert submitted[0]["query_class"] == "minimized_fields"
        assert set(submitted[0]["fields"]) == {"source_text", "target_ref"}
        assert _COMPLAINT not in json.dumps(submitted[0])
        assert case.narrative.text not in json.dumps(submitted[0])
        seen.append(result["invocation_id"])
    assert len(set(seen)) == len(seen)
    assert all(seen)


def test_missing_local_and_unrelated_consent_do_not_dispatch():
    case = meaningful_cases()[0]
    refused = []
    for label, record, purpose, kind, data_class, tools in (
        ("missing", {"found": False}, "extract_facts", "grok_inference", "raw_intake", False),
        ("local", _record(case, "local"), "extract_facts", "grok_inference", "raw_intake", False),
        ("web", _record(case, "grok"), "public_law_citation", "web_search", "public_legal_source_graph", False),
        ("archive", _record(case, "grok"), "public_law_citation", "archive_fetch", "public_legal_source_graph", False),
        ("tools", _record(case, "grok"), "extract_facts", "grok_inference", "raw_intake", True),
        ("facts", _record(case, "grok"), "explain_candidate", "grok_inference", "fact_kg", False),
        ("other-case", _record(case, "grok", case_match=False), "extract_facts", "grok_inference", "raw_intake", False),
    ):
        log, submitted, result = _run(
            case,
            record,
            purpose=purpose,
            provider_kind=kind,
            data_class=data_class,
            tools=tools,
        )
        assert log == ["policy"], label
        assert submitted == [], label
        assert result["provider_loader_called"] is False, label
        assert result["query_submitted"] is False, label
        assert result["effectful"] is False, label
        assert result["live_model_identity_verified"] is False
        refused.append(result["code"])
    assert refused == [
        "consent_missing",
        "local_private",
        "provider_not_authorized",
        "provider_not_authorized",
        "tools_not_authorized",
        "data_class_not_authorized",
        "wrong_case",
    ]


def test_public_law_queries_stay_citation_only_and_local():
    for case in meaningful_cases():
        citation = case.sources[0].citation if case.sources else _CITATION
        log, submitted, result = _run(
            case,
            _record(case, "local"),
            purpose="public_law_citation",
            provider_kind="local",
            data_class="public_legal_source_graph",
            citation=f"{citation} {_COMPLAINT}",
        )
        assert log == ["policy", "query"]
        assert result["status"] == "local_only"
        assert result["provider_loader_called"] is False
        assert submitted[0]["query_class"] == "public_law_citation_only"
        assert submitted[0]["citation"] == citation
        assert case.narrative.text not in submitted[0]["citation"]
        assert _COMPLAINT not in json.dumps(submitted[0])


def test_explicit_data_class_grant_does_not_cross_cases():
    case = meaningful_cases()[0]
    other = meaningful_cases()[1]
    grant = {
        "generation": 4,
        "revoked": False,
        "grants": [
            {
                "explicit": True,
                "purpose": "explain_candidate",
                "provider_kind": "grok_inference",
                "provider": "grok_cli",
                "model": "grok-4.7",
                "data_class": "fact_kg",
                "tools": False,
            }
        ],
    }
    log, _submitted, result = _run(
        case,
        _record(case, "grok", consent=grant),
        purpose="explain_candidate",
        provider_kind="grok_inference",
        data_class="fact_kg",
        private_fields={"candidate_ref": f"candidate.{case.label}", "gap_code": "gap"},
    )
    assert log[0] == "policy"
    assert result["code"] == "authorized"
    assert result["invocation_id"]
    refused_log, refused_submitted, refused = _run(
        other,
        _record(other, "grok"),
        purpose="explain_candidate",
        provider_kind="grok_inference",
        data_class="fact_kg",
    )
    assert refused_log == ["policy"]
    assert refused_submitted == []
    assert refused["code"] == "data_class_not_authorized"


def test_revocation_and_other_case_block_late_results():
    case = meaningful_cases()[0]
    other = meaningful_cases()[1]
    record = _record(case, "grok")
    _log, _submitted, result = _run(
        case,
        record,
        purpose="extract_facts",
        provider_kind="grok_inference",
        data_class="raw_intake",
        private_fields={"source_text": "report", "target_ref": "target.baseline"},
    )
    invocation_id = result["invocation_id"]
    accepted_calls = []

    def reader_revoked():
        revoked = _record(case, "grok", consent={"generation": 2, "revoked": True, "grants": []})
        return revoked

    late = accept_late_hook_result(
        policy_reader=reader_revoked,
        invocation_id=invocation_id,
        owner_id=_OWNER,
        case_id=case.case_id,
        result_acceptor=lambda: accepted_calls.append("accepted"),
    )
    assert late["policy_read"] is True
    assert late["accepted"] is False
    assert late["code"] == "consent_revoked"
    assert late["acceptor_called"] is False
    assert accepted_calls == []

    reused = accept_late_hook_result(
        policy_reader=lambda: _record(case, "grok"),
        invocation_id=invocation_id,
        owner_id=_OWNER,
        case_id=other.case_id,
        result_acceptor=lambda: accepted_calls.append("reused"),
    )
    assert reused["accepted"] is False
    assert reused["code"] == "invocation_not_reusable"
    assert accepted_calls == []

    still = accept_late_hook_result(
        policy_reader=lambda: record,
        invocation_id=invocation_id,
        owner_id=_OWNER,
        case_id=case.case_id,
        result_acceptor=lambda: accepted_calls.append("same"),
    )
    assert still["accepted"] is True
    assert still["code"] == "accepted"
    assert still["live_model_identity_verified"] is False
    assert accepted_calls == ["same"]


def test_provider_failure_stays_unavailable_and_does_not_submit():
    case = meaningful_cases()[0]
    for status in ("unavailable", "raise"):
        log, submitted, result = _run(
            case,
            _record(case, "grok"),
            purpose="propose_questions",
            provider_kind="grok_inference",
            data_class="raw_intake",
            private_fields={"gap_code": "gap", "target_ref": "target.baseline"},
            loader_status=status,
        )
        assert log == ["policy", "provider"]
        assert submitted == []
        assert result["status"] == "unavailable"
        assert result["code"] == "provider_unavailable"
        assert result["query_submitted"] is False
        assert result["effectful"] is False
        assert result["invocation_id"] is None
        assert result["live_model_identity_verified"] is False


def test_workspace_persisted_policy_gates_remote_work(tmp_path):
    case = meaningful_cases()[0]
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    user_id = "synthetic-mgnd-28"
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic mgnd 28 phrase")
    service.ensure_private_case_key(user_id, user_id)
    saved = service.set_privacy_policy(user_id, "grok")
    assert saved["updated"] is True
    log: list[str] = []

    def loader():
        log.append("provider")
        return {"status": "available"}

    def submit(query):
        log.append("query")
        assert _COMPLAINT not in json.dumps(query)

    prepared = service.dispatch_consented_hook_query(
        user_id,
        purpose="extract_facts",
        provider_kind="grok_inference",
        data_class="raw_intake",
        provider_loader=loader,
        query_submitter=submit,
        complaint_text=_COMPLAINT,
        private_fields={"source_text": "safety report", "target_ref": f"target.{case.label}"},
    )
    assert log == ["provider", "query"]
    assert prepared["policy_read"] is True
    assert prepared["code"] == "authorized"
    assert prepared["live_model_identity_verified"] is False
    invocation_id = prepared["invocation_id"]
    case_id = service.get_privacy_policy(user_id)["case_id"]

    unrelated = service.dispatch_consented_hook_query(
        user_id,
        purpose="public_law_citation",
        provider_kind="archive_fetch",
        data_class="public_legal_source_graph",
        provider_loader=lambda: log.append("archive-provider"),
        query_submitter=lambda _query: log.append("archive-query"),
        citation=_CITATION,
        complaint_text=_COMPLAINT,
    )
    assert unrelated["code"] == "provider_not_authorized"
    assert "archive-provider" not in log
    assert "archive-query" not in log

    other = service.dispatch_consented_hook_query(
        user_id,
        purpose="extract_facts",
        provider_kind="grok_inference",
        data_class="raw_intake",
        case_id=case.case_id + "-other",
        provider_loader=lambda: log.append("other-provider"),
        query_submitter=lambda _query: log.append("other-query"),
    )
    assert other["code"] == "wrong_case"
    assert "other-provider" not in log

    service.set_privacy_policy(user_id, "local")
    accepted = []
    late = service.accept_late_consented_hook_result(
        user_id,
        invocation_id=invocation_id,
        case_id=case_id,
        result_acceptor=lambda: accepted.append("late"),
    )
    assert late["accepted"] is False
    assert late["code"] == "consent_revoked"
    assert late["policy_read"] is True
    assert accepted == []

    missing = service.dispatch_consented_hook_query(
        user_id,
        purpose="extract_facts",
        provider_kind="grok_inference",
        data_class="raw_intake",
        provider_loader=lambda: log.append("after-revoke"),
        query_submitter=lambda _query: log.append("after-query"),
    )
    assert missing["code"] == "consent_revoked"
    assert "after-revoke" not in log
    assert missing["live_model_identity_verified"] is False
