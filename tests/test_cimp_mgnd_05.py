"""Host-owned legal/evidence hook contexts stay bound to the current case.

Cases are synthetic private fixtures. No test is skipped. A context receipt
is not a provider call, a legal search, or an evidence publication.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
from mediator.hook_runtime import (
    LEGAL_EVIDENCE_OPERATIONS,
    authorize_hook_execution,
    bind_hook_execution_context,
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
_SECRET_PROMPT = "PRIVATE-PROMPT-do-not-echo"
_SECRET_KEY = "synthetic-hook-key-do-not-echo"


class _SilentBackend:
    def __call__(self, prompt, **kwargs):
        raise AssertionError("hook context dispatch called a backend")


def _privacy(owner_id: str, case_id: str, mode: str = "local"):
    policy = privacy_policy_for_mode(owner_id, case_id, mode)
    return build_complaint_privacy_context(
        policy, user_id=owner_id, case_id=case_id, data_class="fact_kg",
    )


def _legal_context(case) -> dict:
    event = case.narrative.event_date
    known = bool(event) and case.narrative.jurisdiction != "unknown"
    return {
        "status": "explicit" if known else "unknown",
        "jurisdiction": case.narrative.jurisdiction,
        "jurisdiction_explicit": case.narrative.jurisdiction != "unknown",
        "context_revision": 1,
        "applicable_law_date": {"role": "applicable_law_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "event_date": {
            "role": "event_date",
            "raw_text": event,
            "start_date": event,
            "end_date": event,
            "is_uncertain": not bool(event),
        },
        "filing_reference_date": {"role": "filing_reference_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "corpus_retrieval_date": {"role": "corpus_retrieval_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "questions": [_SECRET_PROMPT, case.narrative.text],
    }


def _bindings(case) -> list[dict]:
    rows = []
    for source in case.sources:
        rows.append({
            "source_id": source.authority_id,
            "content_hash": source.source_sha256,
            "source_text": source.source_text,
        })
    return rows


def _purpose(case) -> str:
    return f"grounding-review:{case.label}:{_SECRET_PROMPT}"


def _bind(case, **overrides):
    owner_id = overrides.pop("owner_id", "synthetic-owner")
    case_id = overrides.pop("case_id", case.case_id)
    fields = {
        "operation": "refresh_grounding",
        "owner_id": owner_id,
        "case_id": case_id,
        "session_id": f"session-{case.label}",
        "session_revision": 2,
        "graph_revision": f"gr-case-{case.label}-1",
        "legal_context": _legal_context(case),
        "purpose": _purpose(case),
        "deadline": _DEADLINE,
        "source_bindings": _bindings(case),
        "privacy_context": _privacy(owner_id, case_id),
    }
    fields.update(overrides)
    return bind_hook_execution_context(**fields)


def _observed(case, context, **overrides):
    owner_id = context.owner_id
    fields = {
        "owner_id": owner_id,
        "case_id": context.case_id,
        "session_id": context.session_id,
        "session_revision": context.session_revision,
        "graph_revision": context.graph_revision,
        "legal_context": _legal_context(case),
        "purpose": context.purpose,
        "source_bindings": _bindings(case),
        "privacy_context": _privacy(owner_id, context.case_id),
        "now": _NOW,
        "storage_available": case.storage_available,
        "request_state": "cancelled" if case.label == "cancellation" else "active",
    }
    fields.update(overrides)
    return fields


def _assert_public(document: dict, case) -> None:
    encoded = json.dumps(document, sort_keys=True)
    assert _SECRET_PROMPT not in encoded
    assert _SECRET_KEY not in encoded
    assert case.narrative.text not in encoded
    for source in case.sources:
        assert source.source_text not in encoded
    assert "prompt" not in document
    assert "source_text" not in document
    assert "api_key" not in document
    receipt = document.get("receipt") or document
    assert receipt["operation_id"]
    assert receipt["purpose_hash"] != _purpose(case)
    assert len(receipt["purpose_hash"]) == 64
    assert receipt["legal_context_id"].startswith("lc_")
    assert receipt["source_binding_hash"].startswith("sb_")
    assert receipt["context_binding_hash"].startswith("cb_")
    assert "questions" not in encoded


def test_catalog_cases_bind_and_reject_before_any_effect():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    seen = []
    for case in cases:
        calls = []
        context = _bind(case)
        assert context.operation in LEGAL_EVIDENCE_OPERATIONS
        decision = authorize_hook_execution(context, effect=lambda receipt: calls.append(receipt), **_observed(case, context))
        seen.append(decision["code"])
        assert decision["provider_invoked"] is False
        assert decision["effect_dispatched"] is False
        _assert_public(decision, case)
        if case.label == "cancellation":
            assert decision["code"] == "cancelled"
            assert decision["authorized"] is False
            assert calls == []
        elif case.label == "storage_outage":
            assert decision["code"] == "storage_unavailable"
            assert decision["authorized"] is False
            assert calls == []
        elif case.label == "missing_authority":
            assert decision["authorized"] is True
            assert decision["code"] == "context_authorized"
            assert decision["receipt"]["source_count"] == 0
            assert calls and calls[0]["source_count"] == 0
        else:
            assert decision["authorized"] is True
            assert decision["code"] == "context_authorized"
            assert calls and "source_text" not in calls[0]
            if case.label == "contradiction":
                assert decision["receipt"]["source_count"] == 2
            if case.label == "unknown":
                assert decision["receipt"]["legal_context_id"] != _bind(
                    case, legal_context={**_legal_context(case), "jurisdiction": "federal", "jurisdiction_explicit": True}
                ).legal_context_id
    assert "context_authorized" in seen
    assert "cancelled" in seen
    assert "storage_unavailable" in seen


def test_dispatch_rejects_wrong_case_stale_revision_purpose_and_bindings():
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    context = _bind(case)
    calls = []

    def effect(receipt):
        calls.append(receipt)

    wrong = authorize_hook_execution(context, effect=effect, **_observed(case, context, case_id="other-case"))
    assert wrong["code"] == "wrong_case" and wrong["authorized"] is False
    stale = authorize_hook_execution(context, effect=effect, **_observed(case, context, graph_revision="gr-stale"))
    assert stale["code"] == "stale_revision"
    missing = authorize_hook_execution(context, effect=effect, **_observed(case, context, purpose="  "))
    assert missing["code"] == "missing_purpose"
    changed_source = authorize_hook_execution(
        context, effect=effect, **_observed(case, context, source_bindings=[]),
    )
    assert changed_source["code"] == "source_binding_changed"
    drifted = _legal_context(case)
    drifted["jurisdiction"] = "otherland"
    drifted["context_revision"] = 2
    changed_context = authorize_hook_execution(
        context, effect=effect, **_observed(case, context, legal_context=drifted),
    )
    assert changed_context["code"] == "context_binding_changed"
    assert calls == []
    for decision in (wrong, stale, missing, changed_source, changed_context):
        assert decision["effect_invoked"] is False
        assert decision["provider_invoked"] is False
        _assert_public(decision, case)


def test_secret_material_and_missing_consent_fail_closed():
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    with pytest.raises(Exception) as caught:
        _bind(case, source_bindings=[{
            "source_id": "src-1",
            "content_hash": "ab" * 32,
            "api_key": _SECRET_KEY,
        }])
    assert getattr(caught.value, "code", "") == "secret_material"
    unbound = authorize_hook_execution(
        None,
        owner_id="synthetic-owner",
        case_id=case.case_id,
        session_id="session-baseline",
        session_revision=2,
        graph_revision="gr-case-baseline-1",
        legal_context=_legal_context(case),
        purpose=_purpose(case),
        source_bindings=_bindings(case),
        privacy_context=_privacy("synthetic-owner", case.case_id),
        now=_NOW,
    )
    assert unbound["code"] == "binding_missing"
    assert unbound["receipt"] is None
    assert unbound["effect_dispatched"] is False


def test_legacy_callers_are_not_forced_onto_the_new_context(tmp_path):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    mediator = Mediator(
        [_SilentBackend()],
        evidence_db_path=tmp_path / "evidence.db",
        legal_authority_db_path=tmp_path / "authority.db",
        claim_support_db_path=tmp_path / "support.db",
    )
    assert mediator.statute_retriever is not None
    assert mediator.evidence_storage is not None
    assert mediator.query_intake_candidates(collection_key="entities", source_text="synthetic") is None
    assert getattr(mediator, "_intake_action", None) is None
    mediator._interview_privacy_context = _privacy("synthetic-owner", case.case_id)
    mediator.workflow_actions._interview_meta = {"session_revision": 2}
    bound = mediator.bind_legal_evidence_hook_context(
        operation="acquire_legal_sources",
        owner_id="synthetic-owner",
        case_id=case.case_id,
        session_id="session-baseline",
        session_revision=2,
        graph_revision="gr-case-baseline-1",
        legal_context=_legal_context(case),
        purpose=_purpose(case),
        deadline=_DEADLINE,
        source_bindings=_bindings(case),
    )
    assert bound["bound"] is True
    assert bound["provider_invoked"] is False
    assert getattr(mediator, "_intake_action", None) is None
    assert mediator.query_intake_candidates(collection_key="entities", source_text="synthetic") is None
    _assert_public(bound, case)
    calls = []
    decision = mediator.dispatch_legal_evidence_hook(
        bound["receipt"]["operation_id"],
        now=_NOW,
        effect=lambda receipt: calls.append("should-not-run"),
        owner_id="synthetic-owner",
        case_id=case.case_id,
        session_id="session-baseline",
        session_revision=2,
        graph_revision="gr-case-baseline-1",
        legal_context=_legal_context(case),
        purpose=_purpose(case),
        source_bindings=_bindings(case),
        storage_available=True,
        request_state="active",
    )
    assert decision["authorized"] is True
    assert decision["code"] == "context_authorized"
    assert decision["effect_dispatched"] is False
    assert decision["effect_invoked"] is False
    assert decision["provider_invoked"] is False
    assert calls == []
    _assert_public(decision, case)
    mediator.workflow_actions._interview_meta = {"session_revision": 3}
    drifted = mediator.dispatch_legal_evidence_hook(
        bound["receipt"]["operation_id"],
        now=_NOW,
        effect=lambda receipt: calls.append("should-not-run"),
        owner_id="synthetic-owner",
        case_id=case.case_id,
        session_id="session-baseline",
        session_revision=2,
        graph_revision="gr-case-baseline-1",
        legal_context=_legal_context(case),
        purpose=_purpose(case),
        source_bindings=_bindings(case),
    )
    assert drifted["code"] == "stale_request"
    assert calls == []
    missing = mediator.bind_legal_evidence_hook_context(
        operation="ingest_private_evidence",
        owner_id="synthetic-owner",
        case_id=case.case_id,
        session_id="session-baseline",
        session_revision=3,
        graph_revision="gr-case-baseline-1",
        legal_context=_legal_context(case),
        purpose="",
        deadline=_DEADLINE,
        source_bindings=_bindings(case),
    )
    assert missing["bound"] is False
    assert missing["code"] == "missing_purpose"
    assert missing["receipt"] is None
