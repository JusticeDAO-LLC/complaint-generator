"""Declared Grok purposes stay pinned, bounded, and distinct from local checks.

Cases are synthetic private fixtures. No test is skipped. A synthetic
transport never verifies a live Grok model or build.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backends.llm_router_backend import LLMRouterBackend
from integrations.ipfs_datasets.llm import (
    LLM_ROUTER_AVAILABLE,
    generate_text_with_metadata,
    pinned_hook_inference_route,
    route_identity_diagnostics,
)
from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
from mediator.hook_runtime import (
    LOCAL_ONLY_PURPOSE_IDS,
    MODEL_PURPOSE_IDS,
    bind_hook_execution_context,
    dispatch_declared_hook_purpose,
    inference_purpose_catalog,
)
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 12, 1, tzinfo=timezone.utc)
_PIN_OWNER = "ipfs_accelerate_py.llm_router"
_PIN_PROVIDER = "grok_cli"
_PIN_MODEL = "grok-4.7"


def _privacy(owner_id: str, case_id: str, mode: str):
    policy = privacy_policy_for_mode(owner_id, case_id, mode)
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
    }


def _bindings(case) -> list[dict]:
    return [{"source_id": source.authority_id, "content_hash": source.source_sha256} for source in case.sources]


def _bind(case, purpose_id: str, mode: str):
    owner_id = "synthetic-owner"
    return bind_hook_execution_context(
        operation="refresh_grounding",
        owner_id=owner_id,
        case_id=case.case_id,
        session_id=f"session-{case.label}",
        session_revision=2,
        graph_revision=f"gr-{case.label}-1",
        legal_context=_legal_context(case),
        purpose=purpose_id,
        deadline=_DEADLINE,
        source_bindings=_bindings(case) or [{"source_id": f"src-{case.label}", "content_hash": "a" * 64}],
        privacy_context=_privacy(owner_id, case.case_id, mode),
    )


def _auth(case, context):
    return {
        "owner_id": context.owner_id,
        "case_id": context.case_id,
        "session_id": context.session_id,
        "session_revision": context.session_revision,
        "graph_revision": context.graph_revision,
        "legal_context": _legal_context(case),
        "source_bindings": _bindings(case) or [{"source_id": f"src-{case.label}", "content_hash": "a" * 64}],
        "privacy_context": _privacy(context.owner_id, context.case_id, "grok" if context.provider_call_allowed else "local"),
        "now": _NOW,
        "storage_available": case.storage_available,
        "request_state": "cancelled" if case.label == "cancellation" else "active",
    }


def _local_inputs(case, purpose_id: str) -> dict:
    text = case.narrative.text or "synthetic local source"
    excerpt = text[:24]
    source = case.sources[0] if case.sources else None
    if purpose_id == "local_extraction":
        return {"source_text": text, "excerpt": excerpt}
    if purpose_id == "citation_acquisition":
        citation = source.citation if source is not None else "Synthetic Code 1"
        authority = source.authority_id if source is not None else f"auth-{case.label}"
        return {"citation": citation[:160], "authority_id": authority}
    return {
        "graph_revision": f"gr-{case.label}-1",
        "source_id": source.authority_id if source is not None else f"src-{case.label}",
        "expected_revision": f"gr-{case.label}-1",
    }


def _model_inputs(case, purpose_id: str) -> dict:
    target = f"target.{case.label}"
    if purpose_id == "extract_facts":
        return {"source_text": (case.narrative.text or "synthetic fact")[:500], "target_ref": target}
    if purpose_id == "propose_questions":
        return {"gap_code": f"gap-{case.label}", "target_ref": target}
    return {"candidate_ref": f"candidate.{case.label}", "gap_code": f"gap-{case.label}"}


def _synthetic_output(case, purpose_id: str, inputs: dict) -> dict:
    if purpose_id == "extract_facts":
        return {"facts": [{"field": "act", "value": "reported", "target_ref": inputs["target_ref"]}]}
    if purpose_id == "propose_questions":
        return {"questions": [{"question_id": "q1", "prompt": "What date applies?", "target_ref": inputs["target_ref"]}]}
    return {"candidate_ref": inputs["candidate_ref"], "explanation": f"Candidate note for {case.label}."}


def _transport_factory(case, purpose_id: str, inputs: dict, *, status="available", extra=None):
    calls = []

    def transport(payload):
        calls.append(payload)
        body = {
            "status": status,
            "selected_model": "grok-other",
            "observed_router": "synthetic-transport",
            "observed_provider": "grok_cli",
            "observed_model": "grok-4.7",
            "observed_build": "grok-4.7-build",
            "evidence_class": "native_final_end_model_usage",
            "live_model_identity_verified": True,
            "output": _synthetic_output(case, purpose_id, inputs),
        }
        if extra:
            body.update(extra)
        return body

    return calls, transport


def test_catalog_pins_route_and_bounds_every_declared_purpose():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    route = pinned_hook_inference_route()
    assert route["inference_owner"] == _PIN_OWNER
    assert route["provider"] == _PIN_PROVIDER
    assert route["model"] == _PIN_MODEL
    assert route["allow_local_fallback"] is False
    assert route["allow_cross_provider_fallback"] is False
    assert route["tools_allowed"] is False
    assert route["may_mark_requirements_satisfied"] is False
    catalog = inference_purpose_catalog()
    assert catalog
    ids = {item["purpose_id"] for item in catalog}
    assert ids == MODEL_PURPOSE_IDS | LOCAL_ONLY_PURPOSE_IDS
    for item in catalog:
        assert item["tools_allowed"] is False
        assert item["may_mark_requirements_satisfied"] is False
        assert item["allowed_inputs"] and item["allowed_outputs"]
        assert item["max_input_bytes"] > 0
        if item["purpose_id"] in MODEL_PURPOSE_IDS:
            assert item["dispatch"] == "model"
            assert item["provider"] == _PIN_PROVIDER
            assert item["model"] == _PIN_MODEL
            assert item["inference_owner"] == _PIN_OWNER
            assert item["allow_local_fallback"] is False
            assert item["allow_cross_provider_fallback"] is False
        else:
            assert item["dispatch"] == "local"
            assert item["model_dispatch"] is False


def test_local_purposes_do_not_dispatch_across_cases():
    seen = []
    for case in meaningful_cases():
        for purpose_id in ("local_extraction", "citation_acquisition", "source_graph_check"):
            context = _bind(case, purpose_id, "local")
            inputs = _local_inputs(case, purpose_id)
            calls, transport = _transport_factory(case, "explain_candidate", {"candidate_ref": "candidate.x", "gap_code": "gap"})
            result = dispatch_declared_hook_purpose(context, purpose_id, inputs, model_transport=transport, **_auth(case, context))
            assert calls == []
            assert result["model_dispatched"] is False
            assert result["model_dispatch_count"] == 0
            assert result["provider_invoked"] is False
            assert result["requirements_satisfied"] is False
            assert result["tools_invoked"] is False
            if case.label == "cancellation":
                assert result["code"] == "cancelled"
            elif case.label == "storage_outage":
                assert result["code"] == "storage_unavailable"
            else:
                assert result["status"] == "local_only"
                assert result["output"]
                if purpose_id == "source_graph_check":
                    assert result["output"]["consistent"] is True
                if purpose_id == "citation_acquisition":
                    assert result["output"]["acquired_locally"] is True
                    assert result["output"]["citation"]
            seen.append((case.label, purpose_id, result["code"]))
    assert len(seen) == len(CASE_LABELS) * 3


def test_model_proposals_are_bounded_and_cannot_satisfy_or_use_tools():
    for case in meaningful_cases():
        for purpose_id in ("extract_facts", "propose_questions", "explain_candidate"):
            context = _bind(case, purpose_id, "grok")
            inputs = _model_inputs(case, purpose_id)
            if case.label in {"cancellation", "storage_outage"}:
                calls, transport = _transport_factory(case, purpose_id, inputs)
                result = dispatch_declared_hook_purpose(context, purpose_id, inputs, model_transport=transport, **_auth(case, context))
                assert calls == []
                assert result["model_dispatched"] is False
                assert result["code"] in {"cancelled", "storage_unavailable"}
                continue
            calls, transport = _transport_factory(case, purpose_id, inputs)
            result = dispatch_declared_hook_purpose(context, purpose_id, inputs, model_transport=transport, **_auth(case, context))
            assert len(calls) == 1
            assert calls[0]["provider"] == _PIN_PROVIDER
            assert calls[0]["model"] == _PIN_MODEL
            assert calls[0]["router"] == _PIN_OWNER
            assert calls[0]["allow_local_fallback"] is False
            assert calls[0]["allow_cross_provider_fallback"] is False
            assert calls[0]["tools_allowed"] is False
            assert calls[0]["grok_tools"] == ""
            assert result["status"] == "available"
            assert result["requirements_satisfied"] is False
            assert result["requirements_satisfied_by_model"] is False
            assert result["tools_invoked"] is False
            identity = result["identity"]
            assert identity["requested"]["model"] == _PIN_MODEL
            assert identity["selected"]["model"] == _PIN_MODEL
            assert identity["selected"]["provider"] == _PIN_PROVIDER
            assert identity["observed"]["build"] == "grok-4.7-build"
            assert identity["observed"]["router"] == "synthetic-transport"
            assert identity["requested"] is not identity["selected"]
            assert identity["selected"] is not identity["observed"]
            assert identity["selected"]["build"] == ""
            assert identity["live_model_identity_verified"] is False
            assert identity["live_build_identity_verified"] is False
            assert identity["transport_kind"] == "synthetic"
            blocked, blocked_transport = _transport_factory(
                case, purpose_id, inputs, extra={"output": {"requirements_satisfied": True, "tools": ["search"]}},
            )
            refused = dispatch_declared_hook_purpose(context, purpose_id, inputs, model_transport=blocked_transport, **_auth(case, context))
            assert blocked
            assert refused["status"] == "refused"
            assert refused["code"] in {"model_cannot_invoke_tools", "model_cannot_satisfy_requirements"}
            assert refused["requirements_satisfied"] is False
            assert refused["tools_invoked"] is False


def test_unpinned_route_and_missing_transport_stay_truthful():
    case = meaningful_cases()[0]
    context = _bind(case, "explain_candidate", "grok")
    inputs = _model_inputs(case, "explain_candidate")
    calls, transport = _transport_factory(case, "explain_candidate", inputs)
    refused = dispatch_declared_hook_purpose(
        context, "explain_candidate", inputs, model_transport=transport,
        requested_model="grok-3", allow_local_fallback=True, **_auth(case, context),
    )
    assert calls == []
    assert refused["code"] == "unpinned_route"
    assert refused["model_dispatched"] is False
    assert refused["identity"]["requested"]["model"] == "grok-3"
    assert refused["identity"]["selected"]["model"] == ""
    assert refused["identity"]["observed"]["model"] == ""
    assert refused["identity"]["live_model_identity_verified"] is False
    missing = dispatch_declared_hook_purpose(context, "explain_candidate", inputs, model_transport=None, **_auth(case, context))
    assert missing["status"] == "unavailable"
    assert missing["code"] == "model_transport_unavailable"
    assert missing["model_dispatched"] is False
    calls, failing = _transport_factory(case, "explain_candidate", inputs, status="quota")
    quota = dispatch_declared_hook_purpose(context, "explain_candidate", inputs, model_transport=failing, **_auth(case, context))
    assert len(calls) == 1
    assert quota["status"] == "unavailable"
    assert quota["code"] == "quota"
    assert quota["requirements_satisfied"] is False

    def explode(_payload):
        raise RuntimeError("synthetic boom with secret sk-test")

    failed = dispatch_declared_hook_purpose(context, "explain_candidate", inputs, model_transport=explode, **_auth(case, context))
    assert failed["code"] == "provider_exception"
    assert "sk-test" not in json.dumps(failed)
    local_only = generate_text_with_metadata("do-not-send", inference_purpose="citation_acquisition", provider="grok_cli", model_name="grok-4.7")
    assert local_only["model_dispatched"] is False
    assert local_only["dispatch"] == "none"
    assert local_only["status"] == "local_only"
    held = generate_text_with_metadata("do-not-send", inference_purpose="explain_candidate", provider="grok_cli", model_name="grok-4.7")
    assert held["model_dispatched"] is False
    assert held["error"] == "use_declared_hook_boundary"
    unknown = generate_text_with_metadata("do-not-send", inference_purpose="draft_the_complaint", provider="openai", model_name="other")
    assert unknown["model_dispatched"] is False
    assert unknown["error"] == "undeclared_purpose"


def test_synthetic_diagnostics_never_verify_live_identity():
    spoofed = route_identity_diagnostics(
        requested={"router": _PIN_OWNER, "provider": _PIN_PROVIDER, "model": _PIN_MODEL},
        selected={"router": _PIN_OWNER, "provider": _PIN_PROVIDER, "model": _PIN_MODEL},
        observed={"router": _PIN_OWNER, "provider": _PIN_PROVIDER, "model": _PIN_MODEL, "build": "grok-4.7-build"},
        transport_kind="synthetic",
        native_observation_bound=True,
        evidence_class="native_final_end_model_usage",
    )
    assert spoofed["live_model_identity_verified"] is False
    assert spoofed["live_build_identity_verified"] is False
    assert spoofed["requested"]["model"] == spoofed["observed"]["model"]
    assert spoofed["observed"]["build"] != spoofed["selected"]["model"]


def test_backend_purpose_receipt_keeps_identities_distinct():
    if not LLM_ROUTER_AVAILABLE:
        backend_error = None
        try:
            LLMRouterBackend("purpose-test", provider=_PIN_PROVIDER, model=_PIN_MODEL)
        except ImportError as exc:
            backend_error = str(exc)
        assert backend_error
        assert "llm_router not available" in backend_error
        return
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    context = _bind(case, "explain_candidate", "grok")
    inputs = _model_inputs(case, "explain_candidate")
    calls, transport = _transport_factory(case, "explain_candidate", inputs)
    backend = LLMRouterBackend("purpose-test", provider="openai", model="gpt-other")
    result = backend.run_declared_purpose(context, "explain_candidate", inputs, model_transport=transport, **_auth(case, context))
    assert len(calls) == 1
    assert calls[0]["provider"] == _PIN_PROVIDER
    assert calls[0]["model"] == _PIN_MODEL
    receipt = result["backend_receipt"]
    assert receipt["requested_model"] == _PIN_MODEL
    assert receipt["selected_model"] == _PIN_MODEL
    assert receipt["observed_build"] == "grok-4.7-build"
    assert receipt["observed_model"] == _PIN_MODEL
    assert receipt["live_model_identity_verified"] is False
    assert receipt["live_build_identity_verified"] is False
    assert receipt["provider_supported_identity"] is False
    assert receipt["transport_kind"] == "synthetic"
    direct = json.loads(backend(inputs["gap_code"], inference_purpose="local_extraction"))
    assert direct["model_dispatched"] is False
    assert direct["provider_invoked"] is False
    assert backend.get_retry_stats()["attempts_total"] == 0
