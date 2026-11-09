"""Observed hook purposes use the Native capture seam without a live Grok claim.

Cases are synthetic private fixtures. Observation types in this module are
explicit fakes. Process ownership uses a real child process. No test is skipped.
"""

from __future__ import annotations

import json
import subprocess
import threading
import uuid
from datetime import datetime, timezone

import pytest

import integrations.ipfs_datasets.llm as llm
from backends.llm_router_backend import LLMRouterBackend
from integrations.ipfs_datasets.llm import (
    LLM_ROUTER_AVAILABLE,
    build_complaint_privacy_context,
    clear_remote_invocation_bindings,
    privacy_policy_for_mode,
)
from mediator.hook_runtime import (
    bind_hook_execution_context,
    dispatch_observed_hook_purpose,
)
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 12, 1, tzinfo=timezone.utc)
_OWNER = "synthetic-owner"
_SECRET = "SYNTHETIC_HOOK_SECRET_TOKEN"
_PIN_PROVIDER = "grok_cli"
_PIN_MODEL = "grok-4.7"


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


def _privacy(case):
    policy = privacy_policy_for_mode(_OWNER, case.case_id, "grok")
    return build_complaint_privacy_context(policy, user_id=_OWNER, case_id=case.case_id, data_class="fact_kg")


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


def _auth(case, context, *, request_state="active", storage_available=True):
    return {
        "owner_id": context.owner_id,
        "case_id": context.case_id,
        "session_id": context.session_id,
        "session_revision": context.session_revision,
        "graph_revision": context.graph_revision,
        "legal_context": _legal_context(case),
        "source_bindings": _bindings(case),
        "privacy_context": _privacy(case),
        "now": _NOW,
        "storage_available": storage_available,
        "request_state": request_state,
    }


def _inputs(case, purpose_id: str) -> dict:
    target = f"target.{case.label}"
    if purpose_id == "extract_facts":
        return {"source_text": (case.narrative.text or "synthetic fact")[:500], "target_ref": target}
    if purpose_id == "propose_questions":
        return {"gap_code": f"gap-{case.label}", "target_ref": target}
    return {"candidate_ref": f"candidate.{case.label}", "gap_code": f"gap-{case.label}"}


def _output_text(purpose_id: str, inputs: dict) -> str:
    if purpose_id == "extract_facts":
        body = {"facts": [{"field": "act", "value": "reported", "target_ref": inputs["target_ref"]}]}
    elif purpose_id == "propose_questions":
        body = {"questions": [{"question_id": "q1", "prompt": "What date applies?", "target_ref": inputs["target_ref"]}]}
    else:
        body = {"candidate_ref": inputs["candidate_ref"], "explanation": "Candidate note."}
    return json.dumps(body)


def _consent(case) -> dict:
    grants = []
    for purpose in ("extract_facts", "propose_questions", "explain_candidate"):
        grants.append({
            "explicit": True,
            "tools": False,
            "purpose": purpose,
            "provider_kind": "grok_inference",
            "data_class": "raw_intake",
            "provider": _PIN_PROVIDER,
            "model": _PIN_MODEL,
        })
    return {
        "found": True,
        "user_id": _OWNER,
        "case_id": case.case_id,
        "case_match": True,
        "privacy_policy": privacy_policy_for_mode(_OWNER, case.case_id, "grok"),
        "operation_consent": {"generation": 1, "revoked": False, "grants": grants},
    }


def _observation(request_id: str, **changes) -> FakeObservation:
    fields = dict(
        invocation_id=uuid.uuid4().hex,
        request_id=request_id,
        native_dispatch_count=1,
        selected_provider_name=_PIN_PROVIDER,
        selected_model_name=_PIN_MODEL,
        provider_reported_model=_PIN_MODEL,
        wire_model_observed=True,
        process_returncode=0,
        stream_complete=True,
        evidence_class="native_final_end_model_usage",
        schema="native-grok-invocation-observation@1",
        invocation_scope="current_call",
        observation_only=True,
        raw_provider_data_exported=False,
    )
    fields.update(changes)
    return FakeObservation(**fields)


def _install(monkeypatch, generate):
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("plain generate fallback")))
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (generate, FakeGeneration, FakeObservation))


def _pending(context) -> dict:
    return {"revision": context.graph_revision, "body": _SECRET}


def _dispatch(case, purpose_id, generate, monkeypatch, holder=None, **extra):
    _install(monkeypatch, generate)
    context = _bind(case, purpose_id)
    pending = _pending(context)
    if holder is None:
        holder = {
            "record": _consent(case),
            "graph_revision": context.graph_revision,
            "session_revision": context.session_revision,
        }

    def reader():
        return {
            "record": holder["record"],
            "graph_revision": holder["graph_revision"],
            "session_revision": holder["session_revision"],
        }

    result = dispatch_observed_hook_purpose(
        context,
        purpose_id,
        _inputs(case, purpose_id),
        consent_record=holder["record"],
        pending_case=pending,
        revision_reader=reader,
        cancel_event=extra.pop("cancel_event", None),
        timeout=extra.pop("timeout", 2.0),
        **_auth(case, context, **extra),
    )
    return result, pending, holder


def test_catalog_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS


def test_observed_proposals_use_fake_types_and_do_not_claim_live_grok(monkeypatch):
    seen = []
    for case in meaningful_cases():
        for purpose_id in ("extract_facts", "propose_questions", "explain_candidate"):
            calls = []

            def generate(**kwargs):
                calls.append(kwargs)
                assert kwargs["provider"] == _PIN_PROVIDER
                assert kwargs["model_name"] == _PIN_MODEL
                assert kwargs["allow_local_fallback"] is False
                assert kwargs["allow_cross_provider_fallback"] is False
                assert kwargs["grok_cli_cmd"] == ["grok"]
                assert kwargs["grok_tools"] == "read_file"
                assert kwargs["grok_disallowed_tools"] == "read_file,search_tool,use_tool"
                assert kwargs["grok_permission_mode"] == "dontAsk"
                assert kwargs["grok_max_turns"] == 1
                assert kwargs["grok_stream_progress"] is True
                assert "response_format" not in kwargs
                request_id = kwargs["observation_request_id"]
                text = _output_text(purpose_id, _inputs(case, purpose_id))
                return FakeGeneration(text, _observation(request_id))

            if case.label == "cancellation":
                result, pending, _holder = _dispatch(case, purpose_id, generate, monkeypatch, request_state="cancelled")
                assert calls == []
                assert result["code"] == "cancelled"
                assert result["model_dispatched"] is False
            elif case.label == "storage_outage":
                result, pending, _holder = _dispatch(case, purpose_id, generate, monkeypatch, storage_available=False)
                assert calls == []
                assert result["code"] == "storage_unavailable"
                assert result["model_dispatched"] is False
            else:
                result, pending, _holder = _dispatch(case, purpose_id, generate, monkeypatch)
                assert len(calls) == 1
                assert result["status"] == "available"
                assert result["accepted"] is True
                assert result["output"]
                assert result["synthetic_transport_invoked"] is False
                assert result["identity"]["transport_kind"] == "native_observation"
                assert result["identity"]["live_model_identity_verified"] is False
                assert result["identity"]["live_build_identity_verified"] is False
                assert result["live_canary"] is False
                assert type(calls[0]) is dict
            assert pending["body"] == _SECRET
            assert pending["revision"] == f"gr-{case.label}-1"
            assert result["pending_revision_recoverable"] is True
            assert result["case_revision_mutated"] is False
            assert result["requirements_satisfied"] is False
            assert result["tools_invoked"] is False
            encoded = json.dumps(result)
            assert _SECRET not in encoded
            assert "live Grok" not in encoded
            seen.append((case.label, purpose_id, result["code"]))
    assert len(seen) == len(CASE_LABELS) * 3


@pytest.mark.parametrize("kind", ["quota", "timeout", "malformed", "substitution_refused", "route_unverified"])
def test_failure_receipts_are_bounded_and_pending_revision_stays(monkeypatch, kind):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    purpose_id = "extract_facts"

    def generate(**kwargs):
        if kind == "quota":
            raise RuntimeError("quota exceeded " + _SECRET)
        if kind == "timeout":
            raise subprocess.TimeoutExpired(["sleep"], 1)
        if kind == "substitution_refused":
            return FakeGeneration("{}", _observation(kwargs["observation_request_id"], provider_reported_model="grok-other"))
        if kind == "route_unverified":
            return {"text": _SECRET}
        return FakeGeneration("not-json " + _SECRET, _observation(kwargs["observation_request_id"]))

    result, pending, _holder = _dispatch(case, purpose_id, generate, monkeypatch)
    assert result["accepted"] is False
    assert result["output"] is None
    assert result["code"] == ("malformed" if kind == "malformed" else kind)
    assert result["pending_revision_recoverable"] is True
    assert result["case_revision_mutated"] is False
    assert pending == {"revision": f"gr-{case.label}-1", "body": _SECRET}
    receipt = result["receipt"]
    assert receipt["pending_revision_recoverable"] is True
    assert receipt["session_retained"] is True
    assert receipt["prompt_logged"] is False
    assert receipt["tools_allowed"] is False
    assert receipt["live_canary"] is False
    assert receipt["live_model_identity_verified"] is False
    assert _SECRET not in json.dumps(result)
    assert len(json.dumps(receipt)) < 4000


def test_missing_observation_seam_stays_unavailable(monkeypatch):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("fallback")))
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (None, None, None))
    context = _bind(case, "explain_candidate")
    pending = _pending(context)
    result = dispatch_observed_hook_purpose(
        context, "explain_candidate", _inputs(case, "explain_candidate"),
        consent_record=_consent(case), pending_case=pending, **_auth(case, context),
    )
    assert result["code"] == "route_unverified"
    assert result["model_dispatched"] is False
    assert result["status"] == "unavailable"
    assert pending["revision"] == context.graph_revision
    assert _SECRET not in json.dumps(result)


@pytest.mark.parametrize("change", ["revoked", "revision", "session"])
def test_late_answer_is_not_accepted_after_revocation_or_revision_change(monkeypatch, change):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    purpose_id = "propose_questions"
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        if change == "revoked":
            holder["record"]["operation_consent"]["revoked"] = True
        elif change == "revision":
            holder["graph_revision"] = "gr-other"
        else:
            holder["session_revision"] = 9
        text = _output_text(purpose_id, _inputs(case, purpose_id))
        return FakeGeneration(text, _observation(kwargs["observation_request_id"]))

    holder = {}
    context = _bind(case, purpose_id)
    holder.update(record=_consent(case), graph_revision=context.graph_revision, session_revision=context.session_revision)
    result, pending, holder = _dispatch(case, purpose_id, generate, monkeypatch, holder=holder)
    assert len(calls) == 1
    assert result["accepted"] is False
    assert result["output"] is None
    assert result["code"] == ("consent_revoked" if change == "revoked" else "stale_revision")
    assert result["pending_revision_recoverable"] is True
    assert pending["body"] == _SECRET
    assert result["identity"]["live_model_identity_verified"] is False


def test_cancellation_reaps_only_the_owned_child(monkeypatch):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    from ipfs_accelerate_py.cli_runtime import grok_stream_capture as capture

    sibling = subprocess.Popen(["/bin/sleep", "30"])
    owned = {}
    real_popen = subprocess.Popen

    def popen(command, **kwargs):
        assert command[0] == "/bin/sleep"
        proc = real_popen(command, **kwargs)
        owned["proc"] = proc
        return proc

    monkeypatch.setattr(capture.subprocess, "Popen", popen)

    def generate(**kwargs):
        kwargs["usage_cancel_event"].set()
        capture.capture_grok_stream(
            ["/bin/sleep", "30"],
            env={"PATH": "/usr/bin:/bin"},
            timeout=kwargs["timeout"],
            progress_callback=kwargs["grok_progress_callback"],
        )
        raise AssertionError("cancelled capture returned text")

    try:
        result, pending, _holder = _dispatch(
            case, "extract_facts", generate, monkeypatch, timeout=5.0, cancel_event=threading.Event(),
        )
        assert result["code"] == "cancelled"
        assert result["accepted"] is False
        assert result["output"] is None
        assert result["pending_revision_recoverable"] is True
        assert pending["body"] == _SECRET
        assert owned["proc"].poll() is not None
        assert owned["proc"].pid != sibling.pid
        assert sibling.poll() is None
        assert result["identity"]["live_model_identity_verified"] is False
        assert result["live_canary"] is False
        assert _SECRET not in json.dumps(result)
    finally:
        if sibling.poll() is None:
            sibling.kill()
            sibling.wait(timeout=5)
        proc = owned.get("proc")
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_backend_records_bounded_receipt_without_a_live_claim(monkeypatch):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    if not LLM_ROUTER_AVAILABLE:
        with pytest.raises(ImportError) as caught:
            LLMRouterBackend("observed-hook", provider=_PIN_PROVIDER, model=_PIN_MODEL)
        assert "llm_router not available" in str(caught.value)
        return

    def generate(**kwargs):
        text = _output_text("explain_candidate", _inputs(case, "explain_candidate"))
        return FakeGeneration(text, _observation(kwargs["observation_request_id"]))

    _install(monkeypatch, generate)
    context = _bind(case, "explain_candidate")
    pending = _pending(context)
    backend = LLMRouterBackend("observed-hook", provider=_PIN_PROVIDER, model=_PIN_MODEL, timeout_seconds=2)
    result = backend.run_observed_hook_purpose(
        context, "explain_candidate", _inputs(case, "explain_candidate"),
        consent_record=_consent(case), pending_case=pending, **_auth(case, context),
    )
    assert result["status"] == "available"
    assert result["identity"]["live_model_identity_verified"] is False
    receipt = result["backend_receipt"]
    assert receipt["live_canary"] is False
    assert receipt["provider_supported_identity"] is False
    assert receipt["pending_revision_recoverable"] is True
    assert receipt["transport_kind"] == "native_observation"
    assert pending["body"] == _SECRET
    assert _SECRET not in json.dumps(backend.task_receipts)
