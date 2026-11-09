"""Cloud opt-in, minimal prompts, and remote egress spies for private turns."""

from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
from pathlib import Path

import pytest

SECRET = "SYNTHETIC_PARTY_SECRET_priv006"
TOKEN = "sk-synthetic-egress-token-priv006"
UNRELATED = "UNRELATED_WITNESS_NOTE_priv006"
NECESSARY = "notice-date-2020-01-02"


class _Spy:
    def __init__(self) -> None:
        self.prepare = 0
        self.architecture = 0
        self.provider = 0
        self.socket = 0
        self.process = 0
        self.prompts: list[str] = []
        self.kwargs: list[dict] = []


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    import integrations.ipfs_datasets.llm as llm

    if importlib.util.find_spec("urllib3") is not None:
        import urllib3.util.connection

    spy = _Spy()
    original_prepare = llm._prepare_generate_text_call
    original_architecture = llm._select_huggingface_arch_route

    def _prepare(*args, **kwargs):
        spy.prepare += 1
        return original_prepare(*args, **kwargs)

    def _architecture(*args, **kwargs):
        spy.architecture += 1
        return original_architecture(*args, **kwargs)

    def _provider(*args, **kwargs):
        spy.provider += 1
        prompt = kwargs.get("prompt", args[0] if args else "")
        spy.prompts.append(str(prompt))
        spy.kwargs.append(dict(kwargs))
        return "synthetic-provider-ok"

    def _socket(*args, **kwargs):
        spy.socket += 1
        raise AssertionError("socket opened")

    def _popen(*args, **kwargs):
        spy.process += 1
        raise AssertionError("process spawned")

    monkeypatch.setattr(llm, "_prepare_generate_text_call", _prepare)
    monkeypatch.setattr(llm, "_select_huggingface_arch_route", _architecture)
    monkeypatch.setattr(llm, "generate_text", _provider)
    monkeypatch.setattr(socket, "socket", _socket)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    llm.clear_private_llm_request_cache()
    llm.clear_case_private_caches()
    return spy


def _facts():
    return [{
        "fact_id": "fact-notice",
        "text": f"{SECRET} received the notice on {NECESSARY}",
        "supports_rules": ["rule-notice"],
    }]


def _gaps():
    return [{"rule_id": "rule-notice", "missing": "method of service"}]


def _service(tmp_path: Path):
    from applications.complaint_workspace import ComplaintWorkspaceService

    service = ComplaintWorkspaceService(root_dir=tmp_path)
    if service.private_key_status()["status"] == "absent":
        service.initialize_private_keys(protection="passphrase", passphrase="synthetic egress phrase")
    else:
        service.unlock_private_keys(passphrase="synthetic egress phrase")
    service.ensure_private_case_key("egress-user", "egress-user")
    return service


def _quiet(spy: _Spy, payload: object) -> None:
    encoded = json.dumps(payload, default=str)
    assert SECRET not in encoded
    assert TOKEN not in encoded
    assert UNRELATED not in encoded
    assert spy.prepare == 0
    assert spy.architecture == 0
    assert spy.provider == 0
    assert spy.socket == 0
    assert spy.process == 0


def test_campaign_grok_setting_does_not_authorize_stored_complaints(spies: _Spy) -> None:
    import integrations.ipfs_datasets.llm as llm
    from integrations.ipfs_accelerate.routers import development_campaign_authorizes_user_complaint_egress

    campaign = {"provider": "grok_cli", "model": "grok-4.7", "source": "supervisor_campaign"}
    assert development_campaign_authorizes_user_complaint_egress(campaign) is False
    context = llm.build_complaint_privacy_context(
        llm.privacy_policy_for_mode("egress-user", "case-egress", "local"),
        user_id="egress-user",
        case_id="case-egress",
        data_class="raw_intake",
    )
    denied = llm.dispatch_private_turn(
        privacy_context=context,
        relevant_facts=_facts(),
        rule_gaps=_gaps(),
        unrelated_evidence=[UNRELATED],
        sensitive_literals=[SECRET, TOKEN],
        key=b"k" * 32,
        key_id="synthetic-key",
        campaign_settings=campaign,
        stored_user_complaint=True,
        provider="grok_cli",
        model_name="grok-4.7",
        timeout=15,
    )
    _quiet(spies, denied)
    assert denied["error"] == "privacy_denied:cloud_processing_disabled"
    assert denied["campaign_authorizes_stored_complaints"] is False
    assert denied["dispatch"] == "none"
    assert llm.private_llm_request_cache() == []
    assert llm.private_llm_request_traces() == []


def test_local_mode_blocks_architecture_router_and_cloud_fallback(spies: _Spy) -> None:
    import integrations.ipfs_datasets.llm as llm

    context = llm.build_complaint_privacy_context(
        llm.privacy_policy_for_mode("egress-user", "case-egress", "local"),
        user_id="egress-user",
        case_id="case-egress",
        data_class="drafts_proofs",
    )
    denied = llm.generate_text_with_metadata(
        f"original {SECRET} {UNRELATED}",
        provider="hf_router",
        model_name="katanemo/Arch-Router-1.5B",
        complaint_privacy_context=context,
        arch_router_enabled=True,
        routes=[{"name": "cloud", "model": "other-cloud", "description": "fallback"}],
        base_url="https://router.huggingface.co/v1",
        api_key=TOKEN,
        allow_local_fallback=True,
        allow_cross_provider_fallback=True,
    )
    _quiet(spies, denied)
    assert denied["error"] == "privacy_denied:cloud_processing_disabled"
    assert denied["dispatch"] == "none"


def test_opt_in_sends_minimal_prompt_only_to_pinned_grok(spies: _Spy) -> None:
    import integrations.ipfs_datasets.llm as llm

    policy = llm.privacy_policy_for_mode("egress-user", "case-egress", "grok")
    assert policy["cloud_processing_enabled"] is True
    assert policy["permitted_remote"] == {"provider": "grok_cli", "model": "grok-4.7"}
    assert policy["scope"] == "user_case"
    context = llm.build_complaint_privacy_context(
        policy,
        user_id="egress-user",
        case_id="case-egress",
        data_class="raw_intake",
    )
    wrong_cloud = llm.dispatch_private_turn(
        privacy_context=context,
        relevant_facts=_facts(),
        rule_gaps=_gaps(),
        sensitive_literals=[SECRET],
        unrelated_evidence=[UNRELATED],
        key=b"k" * 32,
        key_id="synthetic-key",
        provider="openrouter",
        model_name="grok-4.7",
    )
    _quiet(spies, wrong_cloud)
    assert wrong_cloud["error"] == "privacy_denied:grok_scope_mismatch"

    sent = llm.dispatch_private_turn(
        privacy_context=context,
        relevant_facts=_facts(),
        rule_gaps=_gaps(),
        sensitive_literals=[SECRET, TOKEN],
        unrelated_evidence=[UNRELATED],
        key=b"k" * 32,
        key_id="synthetic-key",
        provider="grok_cli",
        model_name="grok-4.7",
        timeout=900,
        turn_id="turn-1",
        allow_local_fallback=True,
        allow_cross_provider_fallback=True,
        arch_router_enabled=True,
        routes=[{"name": "other", "model": "secondary-cloud", "description": "nope"}],
        base_url="https://router.huggingface.co/v1",
    )
    assert spies.provider == 1
    assert spies.architecture == 0
    assert spies.socket == 0
    assert spies.process == 0
    assert spies.kwargs[0]["provider"] == "grok_cli"
    assert spies.kwargs[0]["model_name"] == "grok-4.7"
    assert spies.kwargs[0]["timeout"] <= 60
    assert spies.kwargs[0]["allow_local_fallback"] is False
    assert spies.kwargs[0]["allow_cross_provider_fallback"] is False
    prompt = spies.prompts[0]
    assert SECRET not in prompt and TOKEN not in prompt and UNRELATED not in prompt
    assert NECESSARY in prompt
    assert "fact-notice" in prompt
    assert "rule-notice" in prompt
    assert "method of service" in prompt
    assert prompt.startswith("schema: complaint-minimal-turn-prompt/v1")
    alias = [line for line in prompt.splitlines() if "fact-notice" in line][0]
    assert SECRET not in alias
    alias_token = alias.split(": ", 1)[1].split()[0]
    opened = llm.resolve_case_alias(
        user_id="egress-user",
        case_id="case-egress",
        alias=alias_token,
        key=b"k" * 32,
        key_id="synthetic-key",
    )
    assert opened["found"] is True
    assert opened["canonical"] == SECRET
    other_case = llm.resolve_case_alias(
        user_id="egress-user",
        case_id="other-case",
        alias=alias_token,
        key=b"k" * 32,
        key_id="synthetic-key",
    )
    assert other_case["found"] is False
    cache = llm.private_llm_request_cache()
    traces = llm.private_llm_request_traces()
    assert len(cache) == 1
    assert cache[0]["model"] == "grok-4.7"
    assert cache[0]["provider"] == "grok_cli"
    assert cache[0]["timeout_seconds"] <= 60
    assert cache[0]["privacy_choice"]["cloud_processing_enabled"] is True
    assert cache[0]["privacy_choice"]["provider"] == "grok_cli"
    assert cache[0]["privacy_choice"]["model"] == "grok-4.7"
    assert cache[0]["privacy_choice"]["scope"] == "user_case"
    assert SECRET not in cache[0]["prompt"]
    assert traces[0]["prompt_included"] is False
    assert "prompt" not in traces[0]
    assert SECRET not in json.dumps(traces)
    assert sent["authorized_by"] == "explicit_grok_opt_in"
    assert sent["campaign_authorizes_stored_complaints"] is False
    assert sent["timeout_seconds"] <= 60
    assert sent["status"] == "available"
    assert SECRET not in json.dumps({key: value for key, value in sent.items() if key != "prompt"})


def test_disabling_cloud_after_opt_in_stops_egress(tmp_path: Path, spies: _Spy) -> None:
    from complaint_generator.workspace import dispatch_private_llm_turn, get_privacy_policy, set_privacy_policy
    import integrations.ipfs_datasets.llm as llm

    service = _service(tmp_path)
    enabled = set_privacy_policy("egress-user", "grok", service=service)
    assert enabled["updated"] is True
    assert enabled["policy"]["permitted_remote"]["model"] == "grok-4.7"
    assert enabled["policy"]["scope"] == "user_case"
    reloaded = get_privacy_policy("egress-user", service=_service(tmp_path))
    assert reloaded["policy"]["cloud_processing_enabled"] is True
    assert reloaded["policy"]["permitted_remote"]["provider"] == "grok_cli"

    disabled = set_privacy_policy("egress-user", "local", service=_service(tmp_path))
    assert disabled["policy"]["cloud_processing_enabled"] is False
    assert disabled["policy"]["permitted_remote"] is None
    denied = dispatch_private_llm_turn(
        "egress-user",
        relevant_facts=_facts(),
        rule_gaps=_gaps(),
        unrelated_evidence=[UNRELATED],
        sensitive_literals=[SECRET, TOKEN],
        key=b"k" * 32,
        key_id="synthetic-key",
        provider="grok_cli",
        model_name="grok-4.7",
        timeout=10,
        campaign_settings={"model": "grok-4.7", "provider": "grok_cli"},
        stored_user_complaint=True,
        allow_cross_provider_fallback=True,
        arch_router_enabled=True,
        service=_service(tmp_path),
    )
    _quiet(spies, denied)
    assert denied["error"] == "privacy_denied:cloud_processing_disabled"
    assert llm.private_llm_request_cache() == []


def test_architecture_refusal_does_not_transmit_original_prompt(spies: _Spy) -> None:
    import integrations.ipfs_datasets.llm as llm

    token = llm._BLOCK_ARCH_CLASSIFICATION.set(True)
    try:
        _assert_architecture_refusal(llm, spies)
    finally:
        llm._BLOCK_ARCH_CLASSIFICATION.reset(token)


def _assert_architecture_refusal(llm, spies: _Spy) -> None:
    selection = llm._select_huggingface_arch_route(
        f"classify {SECRET}",
        base_url="https://router.huggingface.co/v1",
        api_key=TOKEN,
        referer="",
        app_title="",
        arch_router_config={
            "enabled": True,
            "model": "katanemo/Arch-Router-1.5B",
            "routes": [{"name": "cloud", "model": "other-cloud", "description": "remote"}],
            "context": "",
        },
        fallback_model_name="fallback-cloud",
    )
    assert selection["arch_router_status"] == "refused"
    assert selection["arch_router_error"] == llm.ARCH_CLASSIFICATION_BLOCKED
    assert SECRET not in json.dumps(selection)
    assert spies.provider == 0
    refused = llm.generate_text_with_metadata(
        f"original prompt {SECRET}",
        provider="hf_router",
        model_name="fallback-cloud",
        base_url="https://router.huggingface.co/v1",
        api_key=TOKEN,
        arch_router_enabled=True,
        routes=[{"name": "cloud", "model": "other-cloud", "description": "remote"}],
    )
    assert spies.provider == 0
    assert SECRET not in json.dumps(refused)
    assert refused["error"] == llm.ARCH_CLASSIFICATION_BLOCKED
    assert refused["dispatch"] == "none"
    assert refused.get("effective_model_name") in {"", None}
def _metadata_hardening_context(llm, user_id="metadata-user", case_id="metadata-case"):
    policy = llm.privacy_policy_for_mode(user_id, case_id, "grok")
    return llm.build_complaint_privacy_context(
        policy, user_id=user_id, case_id=case_id, data_class="raw_intake",
    )


def test_case_aliases_are_keyed_stable_and_scoped():
    import hashlib
    import integrations.ipfs_datasets.llm as llm

    llm.clear_case_private_caches()
    facts = [{"fact_id": "fact-1", "text": "Mia saw Eli receive the notice.", "supports_rules": ["rule-1"]}]
    gaps = [{"rule_id": "rule-1", "missing": "method of service"}]

    def build(key, literals, case="metadata-case"):
        return llm.build_minimal_turn_prompt(
            user_id="metadata-user", case_id=case, relevant_facts=facts,
            rule_gaps=gaps, sensitive_literals=literals, key=key,
            key_id="key-" + key[:1].hex(), principal_id="metadata-user",
        )

    def alias_for(built, literal, key, case="metadata-case"):
        for row in built["aliases"]:
            opened = llm.resolve_case_alias(
                user_id="metadata-user", case_id=case, alias=row["alias"],
                key=key, key_id="key-" + key[:1].hex(),
            )
            if opened.get("canonical") == literal:
                return row["alias"]
        raise AssertionError("encrypted reversible alias was not found")

    key = b"a" * 32
    first = build(key, ["Mia", "Eli"])
    reordered = build(key, ["Eli", "Mia"])
    alias = alias_for(first, "Mia", key)
    assert alias == alias_for(reordered, "Mia", key)
    other_key = b"b" * 32
    assert alias != alias_for(build(other_key, ["Mia", "Eli"]), "Mia", other_key)
    assert alias != alias_for(build(key, ["Mia", "Eli"], "another-case"), "Mia", key, "another-case")
    guesses = {
        "alias_" + hashlib.sha256(f"metadata-user\0metadata-case\0{index}\0Mia".encode()).hexdigest()[:12]
        for index in range(2)
    }
    assert alias not in guesses
    assert "Mia" not in first["prompt"] and "Eli" not in first["prompt"]


def test_request_inspection_keeps_only_bounded_metadata(spies: _Spy):
    import integrations.ipfs_datasets.llm as llm

    context = _metadata_hardening_context(llm)
    for number in range(20):
        result = llm.dispatch_private_turn(
            privacy_context=context, relevant_facts=_facts(), rule_gaps=_gaps(),
            sensitive_literals=[SECRET, TOKEN], unrelated_evidence=[UNRELATED],
            key=b"c" * 32, key_id="metadata-key", turn_id=f"turn-{number}",
        )
        assert result["status"] == "available"
    assert spies.provider == 20
    assert all(NECESSARY in prompt for prompt in spies.prompts)
    assert all(SECRET not in prompt and TOKEN not in prompt for prompt in spies.prompts)
    cache, traces = llm.private_llm_request_cache(), llm.private_llm_request_traces()
    assert len(cache) == len(traces) == 8
    serialized = json.dumps([cache, traces])
    for literal in (SECRET, TOKEN, UNRELATED, NECESSARY):
        assert literal not in serialized
    assert all(row.get("prompt", "") == "" for row in cache)
    cache[0]["privacy_choice"]["provider"] = "caller-injected-value"
    assert llm.private_llm_request_cache()[0]["privacy_choice"]["provider"] == "grok_cli"


def test_declared_development_campaign_cannot_send_opted_in_stored_case(spies: _Spy):
    import integrations.ipfs_datasets.llm as llm

    denied = llm.dispatch_private_turn(
        privacy_context=_metadata_hardening_context(llm),
        relevant_facts=_facts(), rule_gaps=_gaps(), sensitive_literals=[SECRET],
        key=b"d" * 32, key_id="campaign-key",
        campaign_settings={"provider": "grok_cli", "model": "grok-4.7"},
        stored_user_complaint=True,
    )
    assert denied["error"] == "privacy_denied:supervisor_fixtures_only"
    assert denied["dispatch"] == "none"
    _quiet(spies, denied)
    assert llm.private_llm_request_cache() == []
    assert llm.private_llm_request_traces() == []


@pytest.mark.parametrize("key", [None, b"", b"short"])
def test_minimal_prompt_requires_case_key_even_without_alias_literals(key):
    import integrations.ipfs_datasets.llm as llm

    with pytest.raises(ValueError, match="privacy_denied:malformed_key"):
        llm.build_minimal_turn_prompt(
            user_id="metadata-user", case_id="metadata-case",
            relevant_facts=_facts(), rule_gaps=_gaps(), sensitive_literals=[],
            key=key, key_id="missing-key",
        )
def test_public_request_inspection_apis_do_not_expose_private_content(spies: _Spy):
    import inspect
    import integrations.ipfs_datasets.llm as llm

    if hasattr(llm, "clear_provider_egress_captures"):
        llm.clear_provider_egress_captures()
    result = llm.dispatch_private_turn(
        privacy_context=_metadata_hardening_context(llm), relevant_facts=_facts(),
        rule_gaps=_gaps(), sensitive_literals=[SECRET, TOKEN], unrelated_evidence=[UNRELATED],
        key=b"e" * 32, key_id="inspection-key",
    )
    assert result["status"] == "available" and spies.provider == 1
    assert NECESSARY in spies.prompts[0]
    inspected = set()
    for name, function in vars(llm).items():
        if name.startswith("_") or name.startswith("clear_"):
            continue
        if not any(word in name.lower() for word in ("cache", "trace", "capture", "snapshot")):
            continue
        if not inspect.isfunction(function) or function.__module__ != llm.__name__:
            continue
        required = [
            parameter for parameter in inspect.signature(function).parameters.values()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        ]
        if required:
            continue
        serialized = json.dumps(function(), default=str)
        for literal in (SECRET, TOKEN, UNRELATED, NECESSARY):
            assert literal not in serialized, name
        inspected.add(name)
    assert {"private_llm_request_cache", "private_llm_request_traces"} <= inspected
    if hasattr(llm, "provider_egress_captures"):
        assert "provider_egress_captures" in inspected
