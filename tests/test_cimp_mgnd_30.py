"""Private invocation associations stay in the encrypted session.

Synthetic transports are labeled fake and cannot verify a live Grok identity.
Cold resume and /status read the stored association and do not dispatch again.
No test is skipped.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

import integrations.ipfs_datasets.llm as llm
from applications.complaint_cli import TerminalComplaintWorkspaceService, _status_text
from integrations.ipfs_datasets.llm import (
    build_complaint_privacy_context,
    clear_remote_invocation_bindings,
    privacy_policy_for_mode,
)
from mediator.hook_runtime import (
    bind_hook_execution_context,
    dispatch_declared_hook_purpose,
    dispatch_observed_hook_purpose,
    invocation_label_for_receipt,
    public_router_trace_entry,
)
from tests.mgnd_fixtures import CASE_LABELS, PASSPHRASE, USER_ID, materialize_case, meaningful_cases
from tests.private_session_assertions import assert_private_session_frame, private_session_path


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 12, 1, tzinfo=timezone.utc)
_OWNER = "synthetic-owner"
_ENV_MARKER = "SYNTHETIC_ENV_VALUE"
_TOOL_MARKER = "SYNTHETIC_TOOL_ARGUMENT"
_KEY_MARKER = "SYNTHETIC_PRIVATE_KEY_MATERIAL"


class FakeObservation:
    """Explicit stand-in. This is not a Native Grok observation."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeGeneration:
    def __init__(self, text, observation):
        self.text = text
        self.observation = observation


def setup_function() -> None:
    clear_remote_invocation_bindings()


def test_meaningful_cases_are_collected_without_skips():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id and case.narrative.text for case in cases)


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
    }


def _bindings(case) -> list[dict]:
    if case.sources:
        return [{"source_id": source.authority_id, "content_hash": source.source_sha256} for source in case.sources]
    return [{"source_id": f"src-{case.label}", "content_hash": "a" * 64}]


def _privacy(case):
    policy = privacy_policy_for_mode(_OWNER, case.case_id, "grok")
    return build_complaint_privacy_context(policy, user_id=_OWNER, case_id=case.case_id, data_class="raw_intake")


def _bind(case, purpose_id: str):
    return bind_hook_execution_context(
        operation="refresh_grounding",
        owner_id=_OWNER,
        case_id=case.case_id,
        session_id=f"session-{case.label}",
        session_revision=2,
        graph_revision=f"gr-{case.label}-1",
        legal_context=_legal_context(case),
        purpose=purpose_id,
        deadline=_DEADLINE,
        source_bindings=_bindings(case),
        privacy_context=_privacy(case),
    )


def _auth(case, context, **extra):
    payload = {
        "owner_id": context.owner_id,
        "case_id": context.case_id,
        "session_id": context.session_id,
        "session_revision": context.session_revision,
        "graph_revision": context.graph_revision,
        "legal_context": _legal_context(case),
        "source_bindings": _bindings(case),
        "privacy_context": _privacy(case),
        "now": _NOW,
        "storage_available": True,
        "request_state": "active",
    }
    payload.update(extra)
    return payload


def _consent(case) -> dict:
    return {
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
                "purpose": "extract_facts",
                "provider_kind": "grok_inference",
                "data_class": "raw_intake",
                "provider": "grok_cli",
                "model": "grok-4.7",
            }],
        },
    }


def _law_text(case) -> str:
    if case.sources:
        return case.sources[0].source_text
    return "SYNTHETIC_LAW_PASSAGE"


def _assert_public(document: str, case) -> None:
    assert case.narrative.text not in document
    assert _law_text(case) not in document
    assert _ENV_MARKER not in document
    assert _TOOL_MARKER not in document
    assert _KEY_MARKER not in document


def test_label_is_real_only_for_a_bound_native_observation():
    assert invocation_label_for_receipt({
        "transport_kind": "native_observation",
        "native_observation_bound": True,
        "evidence_class": "native_final_end_model_usage",
    }) == "real"
    assert invocation_label_for_receipt({
        "transport_kind": "native_observation",
        "native_observation_bound": False,
        "evidence_class": "native_final_end_model_usage",
    }) == "fake"
    assert invocation_label_for_receipt({
        "transport_kind": "synthetic",
        "route_observation": "synthetic",
        "evidence_class": "synthetic",
    }) == "fake"


def test_synthetic_dispatch_associates_every_case_without_a_second_call(monkeypatch):
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("plain generate fallback")))
    seen = []
    for case in meaningful_cases():
        context = _bind(case, "extract_facts")
        calls = []

        def transport(payload, case=case, calls=calls, context=context):
            calls.append(payload)
            assert payload["grok_tools"] == ""
            replay = dispatch_declared_hook_purpose(
                context,
                "extract_facts",
                {"source_text": case.narrative.text[:240], "target_ref": f"target.{case.label}"},
                model_transport=lambda _call: (_ for _ in ()).throw(AssertionError("replayed provider")),
                **_auth(case, context),
            )
            assert replay["code"] == "duplicate_dispatch"
            assert replay["provider_replayed"] is False
            assert replay["model_dispatched"] is False
            return {
                "status": "available",
                "output": {"facts": [{"field": "act", "value": "reported", "target_ref": f"target.{case.label}"}]},
                "prompt": case.narrative.text,
                "env": _ENV_MARKER,
                "tool_arguments": [_TOOL_MARKER],
                "api_key": _KEY_MARKER,
                "evidence_class": "synthetic",
                "observed_provider": "grok_cli",
                "observed_model": "grok-4.7",
            }

        result = dispatch_declared_hook_purpose(
            context,
            "extract_facts",
            {"source_text": case.narrative.text[:240], "target_ref": f"target.{case.label}"},
            model_transport=transport,
            **_auth(case, context),
        )
        assert calls and len(calls) == 1
        association = result["invocation_association"]
        assert association["invocation_label"] == "fake"
        assert association["purpose"] == "extract_facts"
        assert association["request_id"]
        assert association["case_id"] == case.case_id
        assert association["session_id"] == context.session_id
        assert association["accepted_graph_revision"] == context.graph_revision
        assert association["live_model_identity_verified"] is False
        assert association["provider_replayed"] is False
        assert result["live_model_identity_verified"] is False
        _assert_public(json.dumps(association), case)
        seen.append(association["request_id"])
    assert len(set(seen)) == len(meaningful_cases())


def test_fake_observation_association_does_not_claim_live_identity(monkeypatch):
    case = meaningful_cases()[0]

    def generate(**kwargs):
        kwargs["grok_progress_callback"]({"phase": "provider_progress", "tool_arguments": _TOOL_MARKER, "env": _ENV_MARKER})
        body = json.dumps({"facts": [{"field": "act", "value": "reported", "target_ref": "target.baseline"}]})
        observation = FakeObservation(
            invocation_id=uuid.uuid4().hex,
            request_id=kwargs["observation_request_id"],
            native_dispatch_count=1,
            selected_provider_name="grok_cli",
            selected_model_name="grok-4.7",
            provider_reported_model="grok-4.7",
            wire_model_observed=True,
            process_returncode=0,
            stream_complete=True,
            evidence_class="native_final_end_model_usage",
            schema="native-grok-invocation-observation@1",
            invocation_scope="current_call",
            observation_only=True,
            raw_provider_data_exported=False,
            prompt=case.narrative.text,
            tool_arguments=_TOOL_MARKER,
        )
        return FakeGeneration(body, observation)

    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (generate, FakeGeneration, FakeObservation))
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("plain generate fallback")))
    context = _bind(case, "extract_facts")
    result = dispatch_observed_hook_purpose(
        context,
        "extract_facts",
        {"source_text": case.narrative.text[:240], "target_ref": "target.baseline"},
        consent_record=_consent(case),
        **_auth(case, context),
    )
    association = result["invocation_association"]
    assert result["code"] == "proposal_accepted"
    assert association["invocation_label"] == "fake"
    assert association["live_model_identity_verified"] is False
    assert result["live_model_identity_verified"] is False
    assert association["purpose"] == "extract_facts"
    assert association["case_id"] == case.case_id
    assert association["accepted_graph_revision"] == context.graph_revision
    _assert_public(json.dumps(result["receipt"]), case)
    _assert_public(json.dumps(association), case)


def test_encrypted_resume_and_status_keep_associations_without_replay(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: calls.append("generate") or (_ for _ in ()).throw(AssertionError("provider replay")))
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: calls.append("load") or (_ for _ in ()).throw(AssertionError("provider replay")))
    stored = []
    for case in meaningful_cases():
        context = _bind(case, "extract_facts")
        receipt = {
            "kind": "task_receipt",
            "request_id": uuid.uuid4().hex,
            "transport_kind": "synthetic",
            "route_observation": "synthetic",
            "evidence_class": "synthetic",
            "native_observation_bound": False,
            "purpose_id": "extract_facts",
            "status": "available",
            "prompt": case.narrative.text,
            "source_text": _law_text(case),
            "env": _ENV_MARKER,
            "tool_arguments": _TOOL_MARKER,
            "api_key": _KEY_MARKER,
            "live_model_identity_verified": True,
            "prompt_logged": True,
        }
        entry = public_router_trace_entry(
            receipt,
            purpose="extract_facts",
            case_id=case.case_id,
            session_id=context.session_id,
            accepted_graph_revision=context.graph_revision,
            interview_session_id=context.session_id,
            interview_revision=2,
        )
        assert entry is not None
        assert entry["invocation_label"] == "fake"
        assert entry["live_model_identity_verified"] is False
        assert entry["prompt_logged"] is False
        _assert_public(json.dumps(entry), case)
        root = materialize_case(tmp_path / case.label, monkeypatch, case)
        service = root.terminal
        service.unlock_private_keys(passphrase=PASSPHRASE)
        first = service.remember_invocation_associations(USER_ID, [entry])
        again = service.remember_invocation_associations(USER_ID, [entry])
        assert first["provider_replayed"] is False
        assert again["receipts"] == first["receipts"]
        assert len(again["receipts"]) == 1
        status = _status_text(service._load_state(USER_ID))
        assert f"label=fake" in status
        assert f"purpose=extract_facts" in status
        assert f"request={entry['request_id']}" in status
        assert f"case={case.case_id}" in status
        assert f"session={context.session_id}" in status
        assert f"accepted_graph_revision={context.graph_revision}" in status
        assert status.count("invocation ") == 1
        _assert_public(status, case)
        frame = private_session_path(service._session_dir, USER_ID).read_bytes()
        assert_private_session_frame(frame, case.narrative.text, _law_text(case), _ENV_MARKER, _TOOL_MARKER, _KEY_MARKER)
        resumed = TerminalComplaintWorkspaceService(root_dir=service._session_dir)
        resumed.unlock_private_keys(passphrase=PASSPHRASE)
        cold = resumed.run_intake_chat_turn(USER_ID)
        assert cold["session"]["router_trace"]["receipts"] == first["receipts"]
        assert _status_text(resumed._load_state(USER_ID)) == status
        assert calls == []
        stored.append(entry["request_id"])
    assert len(stored) == len(CASE_LABELS)
