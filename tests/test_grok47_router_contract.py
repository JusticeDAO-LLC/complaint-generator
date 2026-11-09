"""Pinned Grok 4.7 route contract.

Deterministic tests inject the provider and a fresh router trace. They never
treat that injection, or a response-cache trace, as a live canary.
"""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import integrations.ipfs_datasets.llm as llm
from integrations.ipfs_accelerate.routers import (
    INFERENCE_OWNER,
    PINNED_GROK_CANARY_PROMPT,
    PINNED_GROK_MODEL,
    PINNED_GROK_PROVIDER,
    pinned_grok47_dispatch_kwargs,
)

MARKER = "synthetic-prompt-marker-route01"
TOKEN = "synthetic-secret-token-route01"


@pytest.fixture(autouse=True)
def offline_boundaries(monkeypatch, tmp_path):
    """No deterministic test may open a socket or start a real CLI."""
    def forbidden(*_args, **_kwargs):
        raise AssertionError("external I/O is forbidden in router contract tests")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("GROK_HOME", str(tmp_path / "synthetic-grok-home"))
    for name in ("XAI_API_KEY", "ipfs_accelerate_py_XAI_API_KEY", "IPFS_ACCELERATE_PY_XAI_API_KEY",
                 "IPFS_DATASETS_PY_XAI_API_KEY", "GROK_AUTH_PROVIDER_COMMAND"):
        monkeypatch.delenv(name, raising=False)


def _dumps(payload: dict) -> str:
    return json.dumps(payload, default=str)


def _assert_quiet(payload: dict) -> None:
    encoded = _dumps(payload)
    assert MARKER not in encoded
    assert TOKEN not in encoded
    assert "prompt" not in payload or payload.get("prompt") in ("", None)
    request_id = str(payload.get("request_id") or "")
    assert request_id
    assert request_id != hashlib.sha256(MARKER.encode("utf-8")).hexdigest()
    assert MARKER not in request_id


def _ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "grok_cli_binary_present", lambda: True)
    monkeypatch.setattr(llm, "grok_cli_auth_present", lambda: True)


def _trace(provider: str = PINNED_GROK_PROVIDER, model: str = PINNED_GROK_MODEL) -> dict[str, str]:
    return {"effective_provider_name": provider, "effective_model_name": model, "prompt": MARKER, "secret": TOKEN}


@pytest.fixture
def external_io(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"socket": 0, "process": 0, "prepare": 0, "generate": 0}

    def _socket(*_args, **_kwargs):
        calls["socket"] += 1
        raise AssertionError("network")

    def _popen(*_args, **_kwargs):
        calls["process"] += 1
        raise AssertionError("process")

    def _prepare(*_args, **_kwargs):
        calls["prepare"] += 1
        raise AssertionError("prepare")

    monkeypatch.setattr(socket, "socket", _socket)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    monkeypatch.setattr(llm, "_prepare_generate_text_call", _prepare)
    return calls


def test_static_capability_and_status_do_not_dispatch(monkeypatch, external_io):
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: external_io.__setitem__("generate", external_io["generate"] + 1))
    status = llm.llm_router_status(
        provider="hf_router",
        model_name="arch-router",
        prompt=MARKER,
        perform_probe=False,
        base_url="hf-router.local",
        arch_router_routes=[{"name": "other", "model": "other-model"}],
    )
    receipt = llm.grok47_route_capability(include_canary=False, canary_transport=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("canary")))
    assert status["static_capability_only"] is True
    assert status["dispatch"] == "none"
    assert status["probe_performed"] is False
    assert receipt["static_capability_only"] is True
    assert receipt["canary_enabled"] is False
    assert receipt["live_canary"] is False
    assert receipt["dispatch"] == "none"
    assert receipt["inference_owner"] == INFERENCE_OWNER
    assert external_io == {"socket": 0, "process": 0, "prepare": 0, "generate": 0}
    _assert_quiet(receipt)


def test_capability_reports_missing_binary_auth_and_router(monkeypatch):
    monkeypatch.setattr(llm, "grok_cli_binary_present", lambda: False)
    monkeypatch.setattr(llm, "grok_cli_auth_present", lambda: False)
    monkeypatch.setattr(llm, "generate_text", None)
    called = {"transport": 0}

    def transport(**_kwargs):
        called["transport"] += 1
        return "GROK47_CANARY_OK"

    receipt = llm.grok47_route_capability(include_canary=True, canary_transport=transport)
    assert called["transport"] == 0
    assert receipt["status"] == "unavailable"
    assert receipt["resumable"] is True
    assert receipt["router_symbol_available"] is False
    assert receipt["binary_available"] is False
    assert receipt["auth_present"] is False
    assert receipt["selected_provider_name"] == ""
    assert "grok binary not found on PATH" in receipt["error"]
    assert "missing authentication" in receipt["error"]
    assert "llm_router symbol is unavailable" in receipt["error"]
    assert receipt["live_canary"] is False
    _assert_quiet(receipt)


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        (PINNED_GROK_PROVIDER, ""),
        (PINNED_GROK_PROVIDER, "grok-4"),
        (PINNED_GROK_PROVIDER, "grok-4.7-latest"),
        ("grok-cli", PINNED_GROK_MODEL),
        ("grok", PINNED_GROK_MODEL),
        ("xai", PINNED_GROK_MODEL),
        ("codex_cli", PINNED_GROK_MODEL),
        ("openrouter", PINNED_GROK_MODEL),
    ],
)
def test_unpinned_routes_are_refused_before_dispatch(monkeypatch, provider, model):
    calls = []

    def provider_call(**kwargs):
        calls.append(kwargs)
        return "should-not-run"

    monkeypatch.setattr(llm, "generate_text", provider_call)
    result = llm.generate_text_with_metadata(f"{MARKER} {TOKEN}", provider=provider, model_name=model)
    assert calls == []
    assert result["status"] == "unavailable"
    assert result["resumable"] is True
    assert result["dispatch"] == "none"
    assert result["live_canary"] is False
    assert "only admitted route" in result["error"]
    _assert_quiet(result)
    with pytest.raises(RuntimeError) as raised:
        llm.generate_text_via_router(f"{MARKER} {TOKEN}", provider=provider, model_name=model)
    assert MARKER not in str(raised.value)
    assert TOKEN not in str(raised.value)


def test_injected_provider_is_exact_and_not_a_live_canary(monkeypatch):
    calls = []

    def provider_call(**kwargs):
        calls.append(kwargs)
        return "synthetic-ok"

    monkeypatch.setattr(llm, "generate_text", provider_call)
    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace())
    result = llm.generate_text_with_metadata(
        f"{MARKER} {TOKEN}",
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
        allow_local_fallback=True,
        allow_cross_provider_fallback=True,
    )
    assert result["status"] == "available"
    assert result["text"] == "synthetic-ok"
    assert len(calls) == 1
    assert calls[0]["provider"] == PINNED_GROK_PROVIDER
    assert calls[0]["model_name"] == PINNED_GROK_MODEL
    assert calls[0]["allow_local_fallback"] is False
    assert calls[0]["allow_cross_provider_fallback"] is False
    assert calls[0]["prompt"] == f"{MARKER} {TOKEN}"
    assert result["requested_provider_name"] == PINNED_GROK_PROVIDER
    assert result["effective_provider_name"] == PINNED_GROK_PROVIDER
    assert result["observed_provider_name"] == PINNED_GROK_PROVIDER
    assert result["observed_model_name"] == PINNED_GROK_MODEL
    assert result["route_observation"] == "verified"
    assert result["route_evidence_class"] == "router_selection"
    assert result["live_canary"] is False
    assert result["provider_reported_model"] == ""
    assert "secret" not in result
    assert result["inference_owner"] == INFERENCE_OWNER
    _assert_quiet(result)


def test_missing_or_mismatched_trace_is_not_rewritten(monkeypatch):
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: "synthetic-ok")
    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: {})
    missing = llm.generate_text_with_metadata("ok", provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL)
    assert missing["status"] == "available"
    assert missing["route_observation"] == "unverified"
    assert missing["live_canary"] is False

    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace("codex_cli", "grok-4"))
    mismatched = llm.generate_text_with_metadata("ok", provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL)
    assert mismatched["route_observation"] == "mismatched"
    assert mismatched["observed_provider_name"] == "codex_cli"
    assert mismatched["observed_model_name"] == "grok-4"
    assert mismatched["effective_provider_name"] == PINNED_GROK_PROVIDER
    assert mismatched["live_canary"] is False
    assert mismatched["text"] == "synthetic-ok"


@pytest.mark.parametrize("setup", ["preflight", "provider"])
def test_generation_error_branches_stay_unavailable_and_quiet(monkeypatch, setup):
    calls = []

    def native(**kwargs):
        calls.append(kwargs)
        raise RuntimeError(f"provider echoed {kwargs.get('prompt', '')} {TOKEN}")

    native.__module__ = "ipfs_accelerate_py.llm_router"
    monkeypatch.setattr(llm, "generate_text", native)
    _ready(monkeypatch)
    if setup == "preflight":
        monkeypatch.setattr(llm, "_provider_preflight_error", lambda **_kwargs: f"{MARKER} {TOKEN}")
    result = llm.generate_text_with_metadata(
        f"{MARKER} {TOKEN}",
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
    )
    assert result["status"] == "unavailable"
    assert result["resumable"] is True
    assert result["live_canary"] is False
    assert result["text"] == ""
    if setup == "preflight":
        assert calls == []
        assert result["dispatch"] == "none"
        assert result["error"] == "provider_exception"
    else:
        assert len(calls) == 1
        assert result["error"] == "provider_exception"
        assert result["dispatch"] == "attempted"
    _assert_quiet(result)


@pytest.mark.parametrize("gap", ["binary", "auth"])
def test_capability_blocks_canary_when_binary_or_auth_is_missing(monkeypatch, gap):
    _ready(monkeypatch)
    if gap == "binary":
        monkeypatch.setattr(llm, "grok_cli_binary_present", lambda: False)
    else:
        monkeypatch.setattr(llm, "grok_cli_auth_present", lambda: False)
    calls = {"transport": 0}

    def transport(**_kwargs):
        calls["transport"] += 1
        return {"text": PINNED_GROK_CANARY_PROMPT, "dispatch": "live", "end": {"modelUsage": {PINNED_GROK_MODEL: {}}}}

    receipt = llm.grok47_route_capability(include_canary=True, canary_transport=transport)
    assert calls["transport"] == 0
    assert receipt["status"] == "unavailable"
    assert receipt["resumable"] is True
    assert receipt["live_canary"] is False
    assert receipt["dispatch"] == "none"
    if gap == "binary":
        assert receipt["binary_available"] is False
        assert "grok binary not found on PATH" in receipt["error"]
    else:
        assert receipt["auth_present"] is False
        assert "missing authentication" in receipt["error"]
    _assert_quiet(receipt)


def test_native_router_pins_model_without_fallback(monkeypatch):
    import ipfs_accelerate_py.llm_router as router

    calls = []

    class Primary:
        def generate(self, prompt, *, model_name=None, **kwargs):
            calls.append((prompt, model_name, kwargs))
            return "native-synthetic"

    def get_provider(name, **_kwargs):
        assert name == PINNED_GROK_PROVIDER
        return Primary()

    monkeypatch.setattr(router, "get_default_router_deps", lambda: SimpleNamespace())
    monkeypatch.setattr(router, "get_llm_provider", get_provider)
    monkeypatch.setattr(router, "_iter_unpinned_optional_providers", lambda: iter([("openrouter", Primary())]))
    monkeypatch.setattr(router, "_response_cache_enabled", lambda: False)
    monkeypatch.setattr(llm, "generate_text", router.generate_text)
    _ready(monkeypatch)
    result = llm.generate_text_with_metadata(
        f"{MARKER} {TOKEN}",
        provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL,
        allow_local_fallback=True,
        allow_cross_provider_fallback=True,
    )
    assert pinned_grok47_dispatch_kwargs() == {
        "provider": PINNED_GROK_PROVIDER,
        "model_name": PINNED_GROK_MODEL,
        "allow_local_fallback": False,
        "allow_cross_provider_fallback": False,
    }
    assert len(calls) == 1
    _prompt, model_name, kwargs = calls[0]
    assert model_name == PINNED_GROK_MODEL
    assert kwargs.get("allow_local_fallback") is not True
    assert kwargs.get("allow_cross_provider_fallback") is not True
    assert _prompt == f"{MARKER} {TOKEN}"
    assert result["status"] == "available"
    assert result["route_observation"] == "verified"
    assert result["live_canary"] is False
    assert result["provider_reported_model"] == ""
    _assert_quiet(result)


def test_opt_in_canary_keeps_injected_wire_claims_unverified(monkeypatch):
    _ready(monkeypatch)
    seen = {}

    def transport(**kwargs):
        seen.update(kwargs)
        return {
            "text": PINNED_GROK_CANARY_PROMPT,
            "dispatch": "live",
            "end": {"modelUsage": {PINNED_GROK_MODEL: {"outputTokens": 1, "prompt": MARKER}}},
            "prompt": MARKER,
            "secret": TOKEN,
        }

    receipt = llm.grok47_route_capability(include_canary=True, canary_transport=transport)
    assert seen["prompt"] == PINNED_GROK_CANARY_PROMPT
    assert seen["provider"] == PINNED_GROK_PROVIDER
    assert seen["model_name"] == PINNED_GROK_MODEL
    assert seen["allow_local_fallback"] is False
    assert seen["allow_cross_provider_fallback"] is False
    assert seen["max_tokens"] == 16
    assert seen["grok_max_turns"] == 1
    assert "tools" not in seen
    assert receipt["status"] == "unverified"
    assert receipt["live_canary"] is False
    assert receipt["provider_reported_model"] == ""
    assert receipt["canary_transport"] == "injected"
    assert receipt["canary_token_matched"] is True
    assert receipt["static_capability_only"] is False
    _assert_quiet(receipt)

    def injected(**_kwargs):
        return PINNED_GROK_CANARY_PROMPT

    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace())
    injected_receipt = llm.grok47_route_capability(include_canary=True, canary_transport=injected)
    assert injected_receipt["status"] == "unverified"
    assert injected_receipt["live_canary"] is False
    assert injected_receipt["provider_reported_model"] == ""
    assert injected_receipt["route_observation"] == "unverified"
    assert injected_receipt["route_evidence_class"] == "absent"
    assert injected_receipt["selected_provider_name"] == ""

    def cached(**_kwargs):
        return {
            "text": PINNED_GROK_CANARY_PROMPT,
            "dispatch": "live",
            "cache_hit": True,
            "end": {"modelUsage": {PINNED_GROK_MODEL: {"outputTokens": 1}}},
        }

    cached_receipt = llm.grok47_route_capability(include_canary=True, canary_transport=cached)
    assert cached_receipt["live_canary"] is False
    assert cached_receipt["response_cache_hit"] is True
    assert cached_receipt["provider_reported_model"] == ""
    assert cached_receipt["status"] == "unverified"

    def wrong_model(**_kwargs):
        return {
            "text": PINNED_GROK_CANARY_PROMPT,
            "dispatch": "live",
            "end": {"modelUsage": {"grok-4": {"outputTokens": 1}}},
        }

    refused = llm.grok47_route_capability(include_canary=True, canary_transport=wrong_model)
    assert refused["status"] == "unverified"
    assert refused["resumable"] is True
    assert refused["live_canary"] is False
    assert refused["provider_reported_model"] == ""
    assert refused["canary_token_matched"] is True

    def explode(**kwargs):
        raise RuntimeError(kwargs["prompt"] + TOKEN)

    exploded = llm.grok47_route_capability(include_canary=True, canary_transport=explode)
    assert exploded["status"] == "unavailable"
    assert exploded["error"] == "provider_exception"
    assert exploded["resumable"] is True
    assert exploded["live_canary"] is False
    _assert_quiet(exploded)


def test_disabled_canary_does_not_use_a_ready_transport(monkeypatch):
    _ready(monkeypatch)

    def transport(**_kwargs):
        raise AssertionError("canary dispatched")

    receipt = llm.grok47_route_capability(include_canary=False, canary_transport=transport)
    assert receipt["status"] == "available"
    assert receipt["canary_enabled"] is False
    assert receipt["live_canary"] is False
    assert receipt["static_capability_only"] is True
    assert receipt["selected_provider_name"] == ""
    assert receipt["selected_model_name"] == ""


@pytest.mark.parametrize("reported", [PINNED_GROK_MODEL, "grok-4"])
def test_untrusted_transport_cannot_self_attest_live_execution(monkeypatch, reported):
    _ready(monkeypatch)
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: "unused")
    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace())
    receipt = llm.grok47_route_capability(include_canary=True, canary_transport=lambda **_kwargs: {
        "text": PINNED_GROK_CANARY_PROMPT, "dispatch": "live",
        "end": {"modelUsage": {reported: {"outputTokens": 1}}},
    })
    assert receipt["live_canary"] is False
    assert receipt["provider_reported_model"] == ""
    assert receipt["status"] == "unverified"


def test_static_discovery_does_not_assert_a_selected_identity(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: "unused")
    receipt = llm.grok47_route_capability()
    assert receipt["requested_provider_name"] == PINNED_GROK_PROVIDER
    assert receipt["requested_model_name"] == PINNED_GROK_MODEL
    assert receipt["selected_provider_name"] == ""
    assert receipt["selected_model_name"] == ""


@pytest.mark.parametrize("stage", ["import", "preflight"])
def test_unavailable_receipts_drop_partial_secret_diagnostics(monkeypatch, stage):
    if stage == "import":
        monkeypatch.setattr(llm, "generate_text", None)
        monkeypatch.setattr(llm, "LLM_ROUTER_ERROR", "credential=" + TOKEN)
    else:
        monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: "unused")
        monkeypatch.setattr(llm, "_provider_preflight_error", lambda **_kwargs: "credential=" + TOKEN)
    receipt = llm.generate_text_with_metadata(MARKER, provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL)
    assert receipt["status"] == "unavailable"
    assert TOKEN not in _dumps(receipt)
    if stage == "import":
        status = llm.llm_router_status(perform_probe=False)
        assert TOKEN not in _dumps(status)


def test_canary_overrides_ambient_tools_and_bounds_timeout(monkeypatch):
    _ready(monkeypatch)
    seen = {}
    monkeypatch.setenv("IPFS_ACCELERATE_PY_GROK_CLI_TOOLS", "run_terminal_cmd,read_file")
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: "unused")
    receipt = llm.grok47_route_capability(include_canary=True, canary_transport=lambda **kwargs: (
        seen.update(kwargs) or PINNED_GROK_CANARY_PROMPT))
    assert seen.get("grok_tools") == ""
    assert set(seen.get("grok_disallowed_tools", "").split(",")) >= {"search_tool", "use_tool"}
    assert type(seen.get("timeout")) is int and 0 < seen["timeout"] <= 60
    assert receipt["live_canary"] is False


@pytest.mark.parametrize("opt_in", ["false", 1, None])
def test_canary_requires_a_boolean_opt_in_before_any_discovery(monkeypatch, opt_in):
    def forbidden():
        raise AssertionError("discovery or dispatch before explicit opt-in validation")
    monkeypatch.setattr(llm, "grok_cli_binary_present", forbidden)
    monkeypatch.setattr(llm, "grok_cli_auth_present", forbidden)
    with pytest.raises(ValueError, match="explicit boolean"):
        llm.grok47_route_capability(include_canary=opt_in)


def test_invalid_injected_transport_cannot_fall_through_to_native_dispatch(monkeypatch):
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("native dispatch")))
    with pytest.raises(ValueError, match="callable"):
        llm.grok47_route_capability(include_canary=True, canary_transport=False)


def test_native_canary_command_disables_tools_and_exposes_evidence_gap(monkeypatch):
    import ipfs_accelerate_py.llm_router as router
    calls = []
    _ready(monkeypatch)
    monkeypatch.setenv("IPFS_ACCELERATE_PY_GROK_CLI_TOOLS", "run_terminal_cmd,read_file")
    monkeypatch.setenv("IPFS_ACCELERATE_PY_GROK_CLI_CMD", "grok --tools run_terminal_cmd --resume unsafe-session")
    monkeypatch.setattr(router, "_cli_available", lambda _command: True)
    @contextmanager
    def sampling(environment, **_kwargs):
        yield environment
    monkeypatch.setattr(router, "_grok_zero_temperature_environment", sampling)
    def execute(argv, **kwargs):
        calls.append((argv, kwargs))
        assert Path(argv[argv.index("--prompt-file") + 1]).read_text() == PINNED_GROK_CANARY_PROMPT
        return SimpleNamespace(returncode=0, stdout=json.dumps({"type": "end", "stopReason": "end_turn",
            "text": PINNED_GROK_CANARY_PROMPT, "modelUsage": {PINNED_GROK_MODEL: {"outputTokens": 1}}}), stderr="")
    monkeypatch.setattr(router.subprocess, "run", execute)
    provider = router._get_grok_cli_provider()
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (None, None, None))
    monkeypatch.setattr(router, "get_default_router_deps", lambda: SimpleNamespace())
    monkeypatch.setattr(router, "get_llm_provider", lambda name, **_kwargs: provider)
    monkeypatch.setattr(router, "_response_cache_enabled", lambda: False)
    monkeypatch.setattr(llm, "generate_text", router.generate_text)
    monkeypatch.setattr(llm, "get_last_generation_trace", router.get_last_generation_trace)
    receipt = llm.grok47_route_capability(include_canary=True)
    assert len(calls) == 1
    argv, options = calls[0]
    assert argv[0] == "grok"
    assert "--resume" not in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert set(argv[argv.index("--disallowed-tools") + 1].split(",")) >= {"search_tool", "use_tool"}
    assert argv[argv.index("--max-turns") + 1] == "1"
    assert options["timeout"] == 60
    assert receipt["status"] == "unverified"
    assert receipt["route_observation"] == "unverified"
    assert receipt["selected_provider_name"] == ""
    assert receipt["selected_model_name"] == ""
    assert receipt["live_canary"] is False and receipt["provider_reported_model"] == ""
    assert receipt["canary_token_matched"] is True
    assert receipt["probe_performed"] is True
    _assert_quiet(receipt)


def test_public_native_grok_failure_never_retries_model_or_provider(monkeypatch):
    import ipfs_accelerate_py.llm_router as router
    calls = []
    class Primary:
        def generate(self, prompt, *, model_name=None, **kwargs):
            calls.append(("grok_cli", model_name))
            raise RuntimeError(TOKEN)
    def get_provider(name, **_kwargs):
        assert name == PINNED_GROK_PROVIDER
        return Primary()
    def optional():
        calls.append(("fallback-discovery", ""))
        raise AssertionError("provider fallback")
    monkeypatch.setattr(router, "get_default_router_deps", lambda: SimpleNamespace())
    monkeypatch.setattr(router, "get_llm_provider", get_provider)
    monkeypatch.setattr(router, "_iter_unpinned_optional_providers", optional)
    monkeypatch.setattr(router, "_response_cache_enabled", lambda: False)
    monkeypatch.setattr(llm, "generate_text", router.generate_text)
    result = llm.generate_text_with_metadata(MARKER, provider=PINNED_GROK_PROVIDER,
        model_name=PINNED_GROK_MODEL, allow_local_fallback=True, allow_cross_provider_fallback=True)
    assert calls == [(PINNED_GROK_PROVIDER, PINNED_GROK_MODEL)]
    assert result["status"] == "unavailable" and result["error"] == "provider_exception"
    _assert_quiet(result)
    calls.clear()
    with pytest.raises(RuntimeError, match="^provider_exception$"):
        llm.generate_text_via_router(MARKER, provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL)
    assert calls == [(PINNED_GROK_PROVIDER, PINNED_GROK_MODEL)]


def test_default_legacy_or_cached_canary_does_not_inherit_previous_selection(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (None, None, None))
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: PINNED_GROK_CANARY_PROMPT)
    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace())
    receipt = llm.grok47_route_capability(include_canary=True)
    assert receipt["selected_provider_name"] == receipt["selected_model_name"] == ""
    assert receipt["route_observation"] == "unverified"
    assert receipt["live_canary"] is False


def test_native_api_cache_or_injected_provider_has_no_invocation_evidence(monkeypatch):
    from ipfs_accelerate_py import llm_router as router
    from ipfs_accelerate_py.cli_runtime.grok_invocation_observation import ObservedTextGeneration, GrokInvocationObservation
    _ready(monkeypatch)
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: "router symbol only")
    monkeypatch.setattr(router, "generate_text", lambda *_args, **_kwargs: PINNED_GROK_CANARY_PROMPT)
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (router.generate_text_with_observation, ObservedTextGeneration, GrokInvocationObservation))
    monkeypatch.setattr(llm, "get_last_generation_trace", lambda: _trace())
    receipt = llm.grok47_route_capability(include_canary=True)
    assert receipt["selected_provider_name"] == receipt["selected_model_name"] == ""
    assert receipt["live_canary"] is False and receipt["status"] == "unverified"


def test_old_typed_observation_cannot_be_replayed_for_a_new_canary_request(monkeypatch):
    from ipfs_accelerate_py.cli_runtime.grok_invocation_observation import ObservedTextGeneration, GrokInvocationObservation
    _ready(monkeypatch)
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: "router symbol only")
    old = ObservedTextGeneration(text=PINNED_GROK_CANARY_PROMPT, observation=GrokInvocationObservation(
        invocation_id="a" * 32, request_id="b" * 32, native_dispatch_count=1,
        selected_provider_name=PINNED_GROK_PROVIDER, selected_model_name=PINNED_GROK_MODEL,
        provider_reported_model="grok-4.7-build", process_returncode=0, stream_complete=True,
        wire_model_observed=True, evidence_class="native_final_end_model_usage"))
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (lambda **_kwargs: old, ObservedTextGeneration, GrokInvocationObservation))
    receipt = llm.grok47_route_capability(include_canary=True)
    assert receipt["request_id"] != old.observation.request_id
    assert receipt["selected_provider_name"] == receipt["provider_reported_model"] == ""
    assert receipt["live_canary"] is False and receipt["status"] == "unverified"
    injected = llm.grok47_route_capability(include_canary=True, canary_transport=lambda **_kwargs: old)
    assert injected["live_canary"] is False and injected["status"] == "unverified"


@pytest.mark.parametrize("wire_model", ["grok-4.7", "grok-4.7-build", "grok-4", "grok-4.synthetic-secret-key", None])
def test_native_canary_observation_consumer_with_authored_process_fixtures(monkeypatch, wire_model):
    """Exercise the native code path with synthetic frames; this is not a live qualification."""
    from ipfs_accelerate_py import llm_router as router
    from ipfs_accelerate_py.cli_runtime import grok_stream_capture
    from ipfs_accelerate_py.cli_runtime.grok_invocation_observation import ObservedTextGeneration, GrokInvocationObservation
    _ready(monkeypatch)
    calls = []
    monkeypatch.setattr(router, "_cli_available", lambda _command: True)
    monkeypatch.setattr(router, "_grok_cli_command", lambda: "grok")
    provider = router._get_grok_cli_provider()
    monkeypatch.setattr(router, "get_default_router_deps", lambda: SimpleNamespace())
    monkeypatch.setattr(router, "get_llm_provider", lambda name, **_kwargs: provider)
    monkeypatch.setattr(router, "_response_cache_enabled", lambda: False)
    @contextmanager
    def sampling(environment, **_kwargs):
        yield environment
    monkeypatch.setattr(router, "_grok_zero_temperature_environment", sampling)
    def capture(argv, **kwargs):
        calls.append(argv)
        assert argv[argv.index("--tools") + 1] == ""
        assert set(argv[argv.index("--disallowed-tools") + 1].split(",")) >= {"search_tool", "use_tool"}
        assert kwargs["timeout"] == 60
        parser = grok_stream_capture.GrokStreamParser()
        end = {"type": "end", "stopReason": "end_turn", "usage": {"output_tokens": 1}}
        if wire_model is not None:
            end["modelUsage"] = {wire_model: {"prompt": MARKER, "secret": TOKEN}}
        frames = [{"type": "text", "data": PINNED_GROK_CANARY_PROMPT}, end]
        parser.feed(b"".join(json.dumps(frame).encode() + b"\n" for frame in frames), elapsed_seconds=.1)
        parser.eof("stdout", elapsed_seconds=.2); parser.eof("stderr", elapsed_seconds=.2)
        parser.process_exit(0, elapsed_seconds=.2)
        return SimpleNamespace(returncode=0, timed_out=False, progress=parser.snapshot(elapsed_seconds=.2),
            final_payload=parser.final_payload, stdout=json.dumps({**end, "text": parser.response_text}), stderr="", response_text=parser.response_text)
    monkeypatch.setattr(grok_stream_capture, "capture_grok_stream", capture)
    monkeypatch.setattr(llm, "generate_text", router.generate_text)
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: (router.generate_text_with_observation, ObservedTextGeneration, GrokInvocationObservation))
    receipt = llm.grok47_route_capability(include_canary=True)
    assert len(calls) == 1
    assert receipt["selected_provider_name"] == PINNED_GROK_PROVIDER
    assert receipt["selected_model_name"] == PINNED_GROK_MODEL
    assert receipt["provider_reported_model"] == (wire_model if wire_model in ("grok-4.7", "grok-4.7-build", "grok-4") else "")
    assert receipt["route_evidence_class"] == "native_invocation"
    assert receipt["native_invocation_id"] != receipt["request_id"]
    if wire_model in ("grok-4.7", "grok-4.7-build"):
        assert receipt["status"] == "available"
    elif wire_model == "grok-4":
        assert receipt["status"] == "unavailable" and receipt["live_canary"] is False
    else:
        assert receipt["status"] == "unverified" and receipt["live_canary"] is False
    _assert_quiet(receipt)


def test_recovery_rejects_wrong_route_and_does_not_fabricate_canary(monkeypatch):
    """Offline recovery stays on the pinned route and cannot self-certify a live canary."""
    from integrations.ipfs_datasets.llm import qualify_intake_model_recovery

    calls = []
    monkeypatch.setattr(llm, "generate_text", lambda **_kwargs: calls.append("generate"))
    state = {"facts": [], "questions": [], "revision": 1}
    wrong = qualify_intake_model_recovery(
        state,
        provider=PINNED_GROK_PROVIDER,
        model_name="grok-4",
        request_id="c" * 32,
        script=["available"],
        transport=lambda **_kwargs: calls.append("transport"),
        sleeper=lambda _delay: calls.append("sleep"),
        include_live_canary=True,
        canary_transport=lambda **_kwargs: {"live_canary": True, "status": "available"},
    )
    assert calls == []
    assert wrong["disposition"] == "wrong_model"
    assert wrong["dispatch"] == "none"
    assert wrong["live_canary"] is False
    assert wrong["offline_unit_complete"] is True
    assert wrong["optional_live_canary"]["label"] == "optional_live_canary"
    assert wrong["optional_live_canary"]["live_canary"] is False
    assert state == {"facts": [], "questions": [], "revision": 1}
    _assert_quiet(wrong)
