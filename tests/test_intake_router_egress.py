"""Last-hop provider egress: sanitized fields only, per-case consent, no bypass."""

from __future__ import annotations

import json

import pytest

import integrations.ipfs_datasets.llm as llm
import backends.llm_router_backend as backend_module
from backends.llm_router_backend import LLMRouterBackend, ProviderRouteError
from integrations.ipfs_accelerate.routers import PINNED_GROK_MODEL, PINNED_GROK_PROVIDER

SECRET = "SYNTHETIC_EGRESS_SECRET_route03"
TOKEN = "sk-synthetic-route03-token"
ALLOWED = {
    "schema", "provider", "model", "prompt", "timeout_seconds",
    "allow_local_fallback", "allow_cross_provider_fallback", "request_id",
    "temperature", "max_tokens", "max_output_tokens", "top_p", "top_k",
    "frequency_penalty", "presence_penalty", "seed", "stop", "response_format",
}


@pytest.fixture(autouse=True)
def _reset_egress():
    llm.clear_provider_egress_captures()
    llm.clear_case_processing_consent()
    yield
    llm.clear_provider_egress_captures()
    llm.clear_case_processing_consent()


def _grok_context(user="case-user", case="case-a", mode="grok"):
    llm.record_case_cloud_consent(user_id=user, case_id=case, mode=mode)
    return llm.recorded_case_privacy_context(user_id=user, case_id=case, data_class="raw_intake")


def _json_prompt():
    return json.dumps({
        "schema_version": "intake_request_v1",
        "operation": "extract_facts",
        "request_id": "a" * 32,
        "source_text": "notice served Tuesday",
        "prompt": "relevant fact only",
        "embedding": [0.1, SECRET],
        "embedding_cache": {"source_text": SECRET},
        "trace": {"path": "/tmp/trace.jsonl", "body": SECRET},
        "trace_jsonl_path": "/tmp/private.jsonl",
        "enrichment": {"route": "openrouter", "note": SECRET},
        "api_key": TOKEN,
        "fallback_provider": "codex",
        "authorization": TOKEN,
    })


class _Observation:
    pass


class _Result:
    def __init__(self, text, observation):
        self.text = text
        self.observation = observation


def _install_native(monkeypatch, calls):
    def native(**kwargs):
        calls.append(kwargs)
        observation = _Observation()
        observation.request_id = kwargs["observation_request_id"]
        observation.invocation_id = "b" * 32
        observation.native_dispatch_count = 1
        observation.invocation_scope = "current_call"
        observation.schema = "native-grok-invocation-observation@1"
        observation.observation_only = True
        observation.raw_provider_data_exported = False
        observation.process_returncode = 0
        observation.stream_complete = True
        observation.wire_model_observed = True
        observation.evidence_class = "native_final_end_model_usage"
        observation.selected_provider_name = PINNED_GROK_PROVIDER
        observation.selected_model_name = PINNED_GROK_MODEL
        observation.provider_reported_model = PINNED_GROK_MODEL
        return _Result("ok", observation)

    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (native, _Result, _Observation))
    monkeypatch.setattr(backend_module, "load_observed_llm_symbols", lambda: (native, _Result, _Observation))


def _assert_sealed(captured, provider_kwargs):
    diagnostic_fields = {
        "schema", "provider", "model", "prompt", "timeout_seconds",
        "allow_local_fallback", "allow_cross_provider_fallback", "request_id",
        "request_reference", "capture_kind",
    }
    assert set(captured) <= diagnostic_fields
    assert captured["schema"] == llm.PROVIDER_EGRESS_SCHEMA
    assert captured["provider"] == PINNED_GROK_PROVIDER
    assert captured["model"] == PINNED_GROK_MODEL
    assert captured["allow_local_fallback"] is False
    assert captured["allow_cross_provider_fallback"] is False
    assert captured["prompt"] == captured["request_id"] == ""
    assert captured["capture_kind"] == "metadata_only"
    assert len(captured["request_reference"]) == 32
    assert 0 < captured["timeout_seconds"] <= 60
    assert SECRET not in json.dumps(captured) and TOKEN not in json.dumps(captured)
    # Payload assertions inspect the actual provider spy, not a global copy.
    assert provider_kwargs["provider"] == PINNED_GROK_PROVIDER
    assert provider_kwargs["model_name"] == PINNED_GROK_MODEL
    assert provider_kwargs["prompt"]
    assert SECRET not in provider_kwargs["prompt"]
    assert TOKEN not in provider_kwargs["prompt"]
    assert provider_kwargs["timeout"] == captured["timeout_seconds"]
    assert provider_kwargs["allow_local_fallback"] is False
    assert provider_kwargs["allow_cross_provider_fallback"] is False


def test_final_serialized_request_keeps_only_sanitized_fields(monkeypatch):
    calls = []

    def provider(**kwargs):
        calls.append(kwargs)
        return "synthetic-ok"

    monkeypatch.setattr(llm, "generate_text", provider)
    prompt = _json_prompt()
    result = llm.generate_text_with_metadata(
        prompt,
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
        complaint_privacy_context=_grok_context(),
        timeout=5,
        trace_jsonl_path="/tmp/should-not-forward.jsonl",
        embedding_cache={"blob": SECRET},
        enrichment_route="openrouter",
        api_key=TOKEN,
    )
    # Disallowed options never reach preparation.
    assert result["privacy_decision"] == "denied"
    assert result["dispatch"] == "none"
    assert calls == []
    assert llm.provider_egress_captures() == []

    result = llm.generate_text_with_metadata(
        prompt,
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
        complaint_privacy_context=_grok_context(),
        timeout=5,
    )
    assert result["status"] == "available"
    assert len(calls) == 1
    captured = llm.provider_egress_captures()
    assert len(captured) == 1
    _assert_sealed(captured[0], calls[0])
    body = json.loads(calls[0]["prompt"])
    assert set(body) <= llm._PROMPT_JSON_KEYS
    assert body["source_text"] == "notice served Tuesday"
    assert "embedding" not in body
    assert "api_key" not in body


def test_backend_dispatch_uses_the_same_sealed_prompt(monkeypatch):
    calls = []
    _install_native(monkeypatch, calls)
    backend = LLMRouterBackend(
        "egress",
        provider=PINNED_GROK_PROVIDER,
        model=PINNED_GROK_MODEL,
        timeout_seconds=5,
        retry_max_attempts=1,
    )
    text = backend(_json_prompt(), complaint_privacy_context=_grok_context())
    assert text == "ok"
    assert len(calls) == 1
    captured = llm.provider_egress_captures()
    assert len(captured) == 1
    _assert_sealed(captured[0], calls[0])
    forwarded = set(calls[0])
    assert "trace" not in forwarded
    assert "trace_jsonl_path" not in forwarded
    assert "embedding" not in forwarded
    assert "embedding_cache" not in forwarded
    assert "enrichment" not in forwarded
    assert "api_key" not in forwarded
    assert calls[0]["allow_local_fallback"] is False
    assert calls[0]["allow_cross_provider_fallback"] is False


def test_local_private_never_invokes_a_remote_provider(monkeypatch):
    calls = []

    def forbidden(**kwargs):
        calls.append(kwargs)
        raise AssertionError("remote provider invoked")

    monkeypatch.setattr(llm, "generate_text", forbidden)
    _install_native(monkeypatch, calls)
    context = _grok_context(mode="local")
    setting = llm.tui_processing_setting(context["policy"])
    assert setting["value"] == "local_private"
    assert setting["value_label"] == "Local private"
    assert "never calls a remote provider" in setting["summary"]
    metadata = llm.generate_text_with_metadata(
        _json_prompt(),
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
        complaint_privacy_context=context,
        timeout=5,
    )
    assert metadata["dispatch"] == "none"
    assert metadata["privacy_decision"] == "denied"
    backend = LLMRouterBackend(
        "local",
        provider=PINNED_GROK_PROVIDER,
        model=PINNED_GROK_MODEL,
        timeout_seconds=5,
    )
    shown = backend.apply_recorded_case_consent("case-user", "case-a")
    assert shown["value_label"] == "Local private"
    assert shown["remote_provider"] == ""
    with pytest.raises(ProviderRouteError) as caught:
        backend("hello")
    assert caught.value.payload["error_code"] == "privacy_denied"
    assert SECRET not in json.dumps(caught.value.payload)
    assert calls == []
    assert llm.provider_egress_captures() == []


def test_local_private_router_string_api_raises_without_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "generate_text", lambda **kwargs: calls.append(kwargs))
    context = _grok_context(case="case-local", mode="local")
    with pytest.raises(RuntimeError) as caught:
        llm.generate_text_via_router(
            "hello",
            provider="openrouter",
            model_name="other",
            complaint_privacy_context=context,
            trace=True,
            embedding_cache={"x": SECRET},
        )
    assert "privacy_denied" in str(caught.value)
    assert calls == []
    assert llm.provider_egress_captures() == []
    assert SECRET not in str(caught.value)


def test_recorded_cloud_consent_is_per_case_and_reusable():
    first = llm.record_case_cloud_consent(user_id="user-1", case_id="case-1", mode="grok")
    again = llm.record_case_cloud_consent(user_id="user-1", case_id="case-1", mode="grok")
    other = llm.record_case_cloud_consent(user_id="user-1", case_id="case-2", mode="local")
    assert first["reusable"] is True and first["scope"] == "per_case"
    assert first["value_label"] == "Grok 4.7 for this case"
    assert "reused" in first["summary"]
    assert first["remote_provider"] == PINNED_GROK_PROVIDER
    assert first["remote_model"] == PINNED_GROK_MODEL
    assert again == first
    reused = llm.recorded_case_privacy_context(user_id="user-1", case_id="case-1", data_class="fact_kg")
    reused_again = llm.recorded_case_privacy_context(user_id="user-1", case_id="case-1", data_class="fact_kg")
    assert reused["policy"]["cloud_processing_enabled"] is True
    assert reused_again["policy"] == reused["policy"]
    assert reused["policy"]["case_id"] == "case-1"
    assert other["value"] == "local_private"
    assert "Local private" in other["value_label"]
    blocked = llm.recorded_case_privacy_context(user_id="user-1", case_id="case-2", data_class="fact_kg")
    assert blocked["policy"]["cloud_processing_enabled"] is False
    missing = llm.recorded_case_privacy_context(user_id="user-1", case_id="case-3", data_class="raw_intake")
    assert missing["policy"]["processing_mode"] == "local_private"
    assert missing["load"]["cloud_processing_enabled"] is False
    backend = LLMRouterBackend("setting", provider=PINNED_GROK_PROVIDER, model=PINNED_GROK_MODEL, timeout_seconds=5)
    shown = backend.apply_recorded_case_consent("user-1", "case-1", data_class="annotations")
    assert shown["label"] == "Processing"
    assert shown["summary"].startswith("Grok 4.7 for this case")
    assert backend.processing_setting()["value"] == "grok_cloud"


def test_bypass_routes_do_not_reach_the_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "generate_text", lambda **kwargs: calls.append(kwargs) or "nope")
    context = _grok_context()
    payload = {
        "provider": "codex",
        "model": "gpt-5.3-codex",
        "prompt": SECRET,
        "api_key": TOKEN,
        "embedding_cache": {"vector": [SECRET]},
        "trace_jsonl_path": "/tmp/leak.jsonl",
        "enrichment_route": "https://example.invalid/enrich",
        "fallback_provider": "openrouter",
        "allow_local_fallback": True,
        "allow_cross_provider_fallback": True,
    }
    for kind in ("enrichment", "trace", "embedding_cache", "fallback", "alternate_provider"):
        result = llm.attempt_remote_bypass(kind, privacy_context=context, payload=payload)
        assert result["provider_invoked"] is False
        assert result["dispatch"] == "none"
        assert result["error"] == f"privacy_denied:bypass_{kind}"
        assert SECRET not in json.dumps(result)
        assert TOKEN not in json.dumps(result)
    assert calls == []
    assert llm.provider_egress_captures() == []
    with pytest.raises(RuntimeError, match="privacy_denied"):
        llm.intercept_final_provider_request({
            "schema": llm.PROVIDER_EGRESS_SCHEMA,
            "provider": "codex",
            "model": PINNED_GROK_MODEL,
            "prompt": SECRET,
            "timeout_seconds": 1,
            "allow_local_fallback": False,
            "allow_cross_provider_fallback": False,
            "request_id": "c" * 32,
            "trace": SECRET,
        })
    assert llm.provider_egress_captures() == []
    assert calls == []
def test_last_dispatch_boundary_drops_unknown_options_and_caps_timeout(monkeypatch):
    import time

    calls = []
    _install_native(monkeypatch, calls)
    backend = LLMRouterBackend(
        "last-boundary", provider=PINNED_GROK_PROVIDER, model=PINNED_GROK_MODEL,
        timeout_seconds=600, retry_max_attempts=1,
    )
    generate, result_type, observation_type = backend_module.load_observed_llm_symbols()
    result = backend._dispatch_observed(
        _json_prompt(),
        {"unapproved_option": SECRET, "temperature": 0.25, "stop": ["END"]},
        time.monotonic() + 600, "c" * 32,
        generate, result_type, observation_type, lambda value: None,
    )
    assert result["text"] == "ok"
    assert len(calls) == 1
    assert "unapproved_option" not in calls[0]
    assert calls[0]["temperature"] == 0.25 and calls[0]["stop"] == ["END"]
    assert 0 < calls[0]["timeout"] <= 60
    assert calls[0]["allow_local_fallback"] is False
    assert calls[0]["allow_cross_provider_fallback"] is False


def test_existing_backend_rechecks_recorded_consent_after_revocation(monkeypatch):
    calls = []
    _install_native(monkeypatch, calls)
    llm.record_case_cloud_consent(user_id="revoke-user", case_id="revoke-case", mode="grok")
    backend = LLMRouterBackend(
        "revocation", provider=PINNED_GROK_PROVIDER, model=PINNED_GROK_MODEL,
        timeout_seconds=5, retry_max_attempts=1,
    )
    backend.apply_recorded_case_consent("revoke-user", "revoke-case")
    llm.record_case_cloud_consent(user_id="revoke-user", case_id="revoke-case", mode="local")
    with pytest.raises(ProviderRouteError):
        backend(_json_prompt())
    assert calls == []
    assert backend.processing_setting()["value"] == "local_private"
