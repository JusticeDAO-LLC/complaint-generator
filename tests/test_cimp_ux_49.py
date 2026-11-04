"""Pinned Grok 4.7 application inference through the canonical router.

Synthetic transports stand in for the provider process. They record the
kwargs the real adapters bind. They do not open sockets or start a CLI.
"""

from __future__ import annotations

import inspect
import json
import os
import socket
import threading
from types import SimpleNamespace

import pytest

import backends.llm_router_backend as backend_module
import integrations.ipfs_datasets.llm as llm
from applications.complaint_workspace import ComplaintWorkspaceService
from integrations.ipfs_accelerate.routers import (
    PINNED_GROK_MODEL,
    PINNED_GROK_PROVIDER,
    development_campaign_authorizes_user_complaint_egress,
    pinned_grok47_adapter_binding,
    pinned_grok47_dispatch_kwargs,
)
from tests.test_cimp_gui_34 import FRAGMENT, NARRATIVE, choose, dispatch, admit

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


class _Observed:
    def __init__(self, request_id, reported="grok-4.7"):
        self.invocation_id = "ab" * 16
        self.request_id = request_id
        self.native_dispatch_count = 1
        self.invocation_scope = "current_call"
        self.schema = "native-grok-invocation-observation@1"
        self.observation_only = True
        self.raw_provider_data_exported = False
        self.process_returncode = 0
        self.stream_complete = True
        self.wire_model_observed = True
        self.evidence_class = "native_final_end_model_usage"
        self.selected_provider_name = PINNED_GROK_PROVIDER
        self.selected_model_name = PINNED_GROK_MODEL
        self.provider_reported_model = reported


class _Result:
    def __init__(self, text, observation):
        self.text = text
        self.observation = observation


def _adapter(**kwargs):
    return kwargs.get("prompt")


def test_pinned_binding_uses_the_adapter_signature_and_refuses_fallback():
    binding = pinned_grok47_adapter_binding(_adapter)
    assert binding == pinned_grok47_dispatch_kwargs()
    signature = inspect.signature(llm.generate_text_via_router)
    bound = signature.bind("synthetic", provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL,
                            allow_local_fallback=False, allow_cross_provider_fallback=False)
    assert bound.arguments["provider"] == PINNED_GROK_PROVIDER
    assert bound.arguments["model_name"] == PINNED_GROK_MODEL

    def positional_only(prompt, provider, model_name, allow_local_fallback, allow_cross_provider_fallback, /):
        del prompt, provider, model_name, allow_local_fallback, allow_cross_provider_fallback

    assert pinned_grok47_adapter_binding(positional_only) is None
    assert pinned_grok47_adapter_binding(lambda prompt: prompt) is None


def test_metadata_adapter_forces_pinned_route_on_a_synthetic_transport(monkeypatch):
    seen = []

    def transport(prompt, *, provider=None, model_name=None, allow_local_fallback=None,
                  allow_cross_provider_fallback=None, **kwargs):
        seen.append({
            "prompt": prompt,
            "provider": provider,
            "model_name": model_name,
            "allow_local_fallback": allow_local_fallback,
            "allow_cross_provider_fallback": allow_cross_provider_fallback,
            "extra": kwargs,
        })
        if "quota" in prompt:
            raise RuntimeError("quota exceeded for synthetic route")
        if "cancel" in prompt:
            raise type("RequestCancelled", (Exception,), {})("stop")
        return "synthetic-ok"

    monkeypatch.setattr(llm, "generate_text", transport)
    assert pinned_grok47_adapter_binding(transport) == pinned_grok47_dispatch_kwargs()
    ok = llm.generate_text_with_metadata(
        "bounded synthetic prompt",
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
        allow_local_fallback=True,
        allow_cross_provider_fallback=True,
    )
    quota = llm.generate_text_with_metadata("quota marker", provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL)
    cancelled = llm.generate_text_with_metadata("cancel marker", provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL)
    assert ok["status"] == "available" and ok["text"] == "synthetic-ok"
    assert quota["failure_kind"] == "quota" and quota["status"] == "quota"
    assert cancelled["failure_kind"] == "cancelled" and cancelled["status"] == "cancelled"
    assert [row["provider"] for row in seen] == [PINNED_GROK_PROVIDER] * 3
    assert [row["model_name"] for row in seen] == [PINNED_GROK_MODEL] * 3
    assert all(row["allow_local_fallback"] is False and row["allow_cross_provider_fallback"] is False for row in seen)
    assert "quota exceeded" not in json.dumps(quota)


def _install_observed(monkeypatch, behavior):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        request_id = kwargs["observation_request_id"]
        callback = kwargs.get("grok_progress_callback")
        if behavior == "cancel-during":
            if callback:
                callback({"phase": "synthetic"})
            return _Result("should-not-return", _Observed(request_id))
        if behavior == "quota":
            raise RuntimeError("insufficient_quota")
        if behavior == "mismatch":
            return _Result('{"ok":true}', _Observed(request_id, reported="grok-4"))
        if callable(callback):
            callback({"phase": "synthetic"})
        body = json.dumps({"purpose_id": "extract_facts", "facts": []})
        return _Result(body, _Observed(request_id))

    def loader():
        return generate, _Result, _Observed

    monkeypatch.setattr(llm, "load_observed_llm_symbols", loader)
    monkeypatch.setattr(backend_module, "load_observed_llm_symbols", loader)
    monkeypatch.setattr(llm, "LLM_ROUTER_AVAILABLE", True)
    monkeypatch.setattr(backend_module, "LLM_ROUTER_AVAILABLE", True)
    return calls


def test_observed_hook_adapter_records_pinned_kwargs_and_typed_failures(monkeypatch):
    calls = _install_observed(monkeypatch, "ok")
    request_id = "c" * 32
    result = llm.generate_observed_hook_purpose(
        purpose_id="extract_facts",
        inputs={"source_text": "synthetic fragment", "target_ref": "entity-1"},
        request_id=request_id,
        timeout=5,
    )
    assert result["status"] == "available"
    assert result["allow_local_fallback"] is False and result["allow_cross_provider_fallback"] is False
    assert result["live_model_identity_verified"] is False
    assert calls[0]["provider"] == PINNED_GROK_PROVIDER
    assert calls[0]["model_name"] == PINNED_GROK_MODEL
    assert calls[0]["allow_local_fallback"] is False
    assert calls[0]["allow_cross_provider_fallback"] is False
    assert pinned_grok47_adapter_binding(llm.load_observed_llm_symbols()[0]) == pinned_grok47_dispatch_kwargs()

    calls = _install_observed(monkeypatch, "quota")
    quota = llm.generate_observed_hook_purpose(
        purpose_id="extract_facts", inputs={"source_text": "x"}, request_id=request_id, timeout=5,
    )
    assert quota["status"] == "quota" and quota["code"] == "quota"
    assert quota["model_dispatched"] is True and quota["text"] == ""

    event = threading.Event()
    event.set()
    calls = _install_observed(monkeypatch, "ok")
    cancelled = llm.generate_observed_hook_purpose(
        purpose_id="extract_facts", inputs={"source_text": "x"}, request_id=request_id,
        timeout=5, cancel_event=event,
    )
    assert cancelled["status"] == "cancelled" and cancelled["model_dispatched"] is False
    assert calls == []

    active = threading.Event()

    def generate(**kwargs):
        calls.append(kwargs)
        active.set()
        kwargs["grok_progress_callback"]({"phase": "synthetic"})
        return _Result("late", _Observed(kwargs["observation_request_id"]))

    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (generate, _Result, _Observed))
    during = llm.generate_observed_hook_purpose(
        purpose_id="extract_facts", inputs={"source_text": "x"}, request_id=request_id,
        timeout=5, cancel_event=active,
    )
    assert during["status"] == "cancelled" and during["model_dispatched"] is True
    assert calls[-1]["allow_cross_provider_fallback"] is False


def test_backend_typed_quota_and_cancel_keep_the_session(monkeypatch):
    calls = _install_observed(monkeypatch, "quota")
    router = backend_module.LLMRouterBackend("llm-router-grok-4.7", provider=PINNED_GROK_PROVIDER, model=PINNED_GROK_MODEL, timeout_seconds=5)
    with pytest.raises(backend_module.ProviderRouteError) as quota:
        router("synthetic complaint fragment")
    assert quota.value.payload["error_code"] == "quota"
    assert router.session_retained is True
    assert calls and calls[0]["provider"] == PINNED_GROK_PROVIDER
    assert calls[0]["allow_local_fallback"] is False and calls[0]["allow_cross_provider_fallback"] is False

    _install_observed(monkeypatch, "ok")
    router.cancel()
    with pytest.raises(backend_module.ProviderRouteError) as cancelled:
        router("another fragment")
    assert cancelled.value.payload["error_code"] == "cancelled"
    assert router.session_retained is True


def test_incompatible_adapter_signature_does_not_dispatch(monkeypatch):
    def generate(prompt, /):
        raise AssertionError(prompt)

    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (generate, _Result, _Observed))
    result = llm.generate_observed_hook_purpose(
        purpose_id="extract_facts", inputs={"source_text": "x"}, request_id="d" * 32, timeout=5,
    )
    assert result["status"] == "unavailable" and result["code"] == "route_unverified"
    assert result["model_dispatched"] is False


def test_development_agent_permission_is_not_complaint_consent(monkeypatch, tmp_path):
    campaign = {"provider": "grok_cli", "model": "grok-4.7", "fallback": False, "development_agent": True}
    assert development_campaign_authorizes_user_complaint_egress(campaign) is False
    monkeypatch.setenv("GROK_AUTHORIZED", "1")
    monkeypatch.setenv("IPFS_ACCELERATE_AGENT_MODEL", "grok-4.7")
    service = ComplaintWorkspaceService(tmp_path / "no-case")
    refused = service.dispatch_bounded_gui_inference(
        "synthetic-owner",
        purpose="extract_facts",
        inputs={"source_text": FRAGMENT, "target_ref": "caller"},
    )
    assert refused["model_dispatched"] is False
    assert refused["code"] == "server_case_authority_required"
    assert refused["output"] is None


@pytest.fixture
def world(tmp_path):
    from applications.case_consent_api import CaseConsentService
    from applications.server import SERVER
    from tests.test_cimp_gui_14 import _composed_case_world, _composed_headers, _composed_login
    from fastapi.testclient import TestClient

    w = _composed_case_world(tmp_path)
    w.seen = []

    def transport(call):
        w.seen.append(call)
        return {"status": "available", "output": {"facts": [{"field": "act", "value": "fired", "target_ref": call["inputs"]["target_ref"]}]},
                "live_model_identity_verified": True, "observed_provider": "grok_cli", "observed_model": "grok-4.7"}

    w.consent = CaseConsentService(tmp_path / "consent", cases=w.cases, key=os.urandom(32), key_id="consent-key", clock=lambda: 1700000100)
    w.app = SERVER(None, authorizer=w.authorizer, browser_sessions=w.sessions, case_handlers=w.handlers,
                   case_consent=w.consent, gui_inference_transport=transport).app
    with TestClient(w.app, base_url="https://testserver") as client:
        w.client = client
        w.csrf = _composed_login(client)
        w.headers = _composed_headers(w.case, w.csrf)
        started = client.post("/api/complaint-workspace/intake-chat", headers=w.headers,
                              json={"message": NARRATIVE, "interview_action": "start"})
        assert started.status_code == 200, started.text
        w.started = started.json()
        w.target = w.started["graph_targets"]["target_id"]
        yield w


def test_case_purpose_membership_minimization_and_revision_govern_admission(world, monkeypatch):
    monkeypatch.setenv("GROK_AUTHORIZED", "1")
    w = world
    denied = dispatch(w).json()
    assert denied["model_dispatched"] is False
    assert denied["code"] == "case_purpose_consent_required"
    assert w.seen == []
    choose(w)
    whole = dispatch(w, inputs={"source_text": NARRATIVE, "target_ref": w.target}).json()
    assert whole["code"] == "query_not_minimized" and whole["model_dispatched"] is False
    held = dispatch(w).json()
    assert held["status"] == "held" and held["accepted"] is False
    assert held["development_grok_authorization_ignored"] is True
    assert held["development_agent_grok_permission_is_complaint_consent"] is False
    call = w.seen[0]
    assert call["provider"] == PINNED_GROK_PROVIDER and call["model"] == PINNED_GROK_MODEL
    assert call["allow_local_fallback"] is False and call["allow_cross_provider_fallback"] is False
    assert NARRATIVE not in json.dumps(call["inputs"])
    inquiry = w.started["interview"]["inquiry"]
    updated = w.client.post("/api/complaint-workspace/intake-chat", headers=w.headers, json={
        "message": "Federal law applies to this synthetic employment matter.",
        "question_id": inquiry["inquiry_id"],
        "expected_question_revision": inquiry["revision"],
        "interview_action": "answer",
    })
    assert updated.status_code == 200, updated.text
    stale = admit(w, held["invocation_id"]).json()
    assert stale["accepted"] is False and stale["output"] is None
    assert str(stale["code"]).startswith("stale_")


def test_socket_constructor_stays_unused_by_the_synthetic_router(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(socket, "socket", forbidden)
    binding = pinned_grok47_adapter_binding(_adapter)
    assert binding["provider"] == "grok_cli"
    assert binding["model_name"] == "grok-4.7"
    assert binding["allow_local_fallback"] is False
    assert SimpleNamespace(**binding).allow_cross_provider_fallback is False
