"""Executable privacy policy for complaint data classes and remote egress."""

from __future__ import annotations

import json
import importlib.util
import socket
import subprocess
import traceback
from pathlib import Path

import pytest

MARKER = "SYNTHETIC_COMPLAINT_MARKER_priv001"
TOKEN = "sk-synthetic-privacy-token-priv001"
PRIVATE_CLASS_IDS = {
    "raw_intake",
    "attachments",
    "fact_kg",
    "claim_dependency_evaluations",
    "annotations",
    "drafts_proofs",
    "embeddings",
    "exports",
    "logs",
    "caches",
    "temporary_files",
    "backups",
}


class _Spy:
    def __init__(self) -> None:
        self.prepare = 0
        self.architecture = 0
        self.provider = 0
        self.socket = 0
        self.socket_stacks: list[str] = []
        self.process = 0
        self.backend = 0
        self.prompts: list[str] = []
        self.backend_kwargs: list[dict] = []


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    import integrations.ipfs_datasets.llm as llm
    # urllib3 checks IPv6 support by binding a loopback socket at import.
    # Bootstrap that dependency before measuring the guarded call boundaries;
    # all socket/provider/preparation assertions below remain strict.
    if importlib.util.find_spec("urllib3") is not None:
        import urllib3.util.connection

    spy = _Spy()
    original_prepare = llm._prepare_generate_text_call

    def _prepare(*args, **kwargs):
        spy.prepare += 1
        return original_prepare(*args, **kwargs)

    def _architecture(*args, **kwargs):
        spy.architecture += 1
        raise AssertionError("architecture selector ran")

    def _provider(*args, **kwargs):
        spy.provider += 1
        prompt = kwargs.get("prompt", args[0] if args else "")
        spy.prompts.append(str(prompt))
        return "local-stub-response"

    def _socket(*args, **kwargs):
        spy.socket += 1
        spy.socket_stacks.append("".join(traceback.format_stack(limit=8)))
        raise AssertionError("socket opened")

    def _popen(*args, **kwargs):
        spy.process += 1
        raise AssertionError("process spawned")

    monkeypatch.setattr(llm, "_prepare_generate_text_call", _prepare)
    monkeypatch.setattr(llm, "_select_huggingface_arch_route", _architecture)
    monkeypatch.setattr(llm, "generate_text", _provider)
    monkeypatch.setattr(socket, "socket", _socket)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    return spy


def _assert_quiet(spy: _Spy, payload: object) -> None:
    encoded = json.dumps(payload, default=str)
    assert MARKER not in encoded
    assert TOKEN not in encoded
    assert spy.prepare == 0
    assert spy.architecture == 0
    assert spy.provider == 0
    assert spy.socket == 0, "\n".join(spy.socket_stacks)
    assert spy.process == 0


_FIXTURE_PASSPHRASE = "synthetic policy fixture protection phrase"


def _service(root: Path, *, users=()):
    from applications.complaint_workspace import ComplaintWorkspaceService
    service = ComplaintWorkspaceService(root_dir=root)
    if service.private_key_status()["status"] == "absent":
        service.initialize_private_keys(protection="passphrase", passphrase=_FIXTURE_PASSPHRASE)
    else:
        service.unlock_private_keys(passphrase=_FIXTURE_PASSPHRASE)
    for user_id in users:
        service.ensure_private_case_key(user_id, user_id)
    return _bind_deterministic_interview_backend(service)


def _bind_deterministic_interview_backend(service):
    """Inject only this fixture's backend; preserve the real engine and policy guard."""
    real_factory = service._mediator_for_shared_interview
    def fixture_backend(prompt, complaint_privacy_context=None, **kwargs):
        assert isinstance(complaint_privacy_context, dict)
        return '{"entities":[],"relationships":[]}'
    def factory(user_id, case_id):
        mediator = real_factory(user_id, case_id)
        mediator.backends = [fixture_backend]
        return mediator
    service._mediator_for_shared_interview = factory
    return service


def _seed_draft(service, user_id: str, body: str) -> None:
    state = service._load_state(user_id)
    state["draft"] = {"title": "Synthetic", "body": body, "requested_relief": ["Compensatory damages"]}
    state["intake_answers"] = {"party_name": MARKER}
    service._save_state(state)


def test_inventory_separates_private_claim_graph_from_public_law(tmp_path: Path) -> None:
    from complaint_generator.workspace import get_privacy_policy, inventory_private_data_classes

    service = _service(tmp_path, users=["user-inventory"])
    inventory = inventory_private_data_classes("user-inventory", service=service)
    private_ids = {item["id"] for item in inventory["private_claim_fact_graph"]}
    assert private_ids == PRIVATE_CLASS_IDS
    assert inventory["public_legal_source_graph"]["id"] == "public_legal_source_graph"
    assert inventory["public_legal_source_graph"]["classification"] == "public"
    assert inventory["public_legal_source_graph"]["distinct_from"] == "private_claim_fact_graph"
    assert inventory["at_rest_protection"] == "private_envelope"
    assert inventory["encryption_at_rest_blocks_remote_llm"] is False
    assert inventory["authenticates_tenant"] is False
    assert inventory["reads_existing_private_paths"] is False
    assert inventory["agent_context"]["fixtures_only"] is True
    assert inventory["agent_context"]["excluded_path_classes"] == [
        "session",
        "evidence",
        "export",
        "secret",
    ]
    policy = get_privacy_policy("user-inventory", service=service)
    assert policy["policy"]["cloud_processing_enabled"] is False
    assert policy["policy"]["processing_mode"] == "local_private"
    assert policy["authenticates_tenant"] is False
    assert "PRIV002" in policy["authorization_note"]


def test_parser_rejects_version_scope_case_and_malformed_consent() -> None:
    from integrations.ipfs_datasets.llm import (
        inspect_privacy_policy,
        privacy_policy_for_mode,
    )

    base = privacy_policy_for_mode("user-a", "case-a", "grok")
    assert inspect_privacy_policy(base, user_id="user-a", case_id="case-a")["admitted"] is True

    wrong_version = dict(base)
    wrong_version["version"] = "0"
    version = inspect_privacy_policy(wrong_version, user_id="user-a", case_id="case-a")
    assert version["admitted"] is False
    assert version["reason"] == "privacy_denied:version"
    assert version["cloud_processing_enabled"] is False

    wrong_scope = dict(base)
    wrong_scope["scope"] = "global"
    scope = inspect_privacy_policy(wrong_scope, user_id="user-a", case_id="case-a")
    assert scope["reason"] == "privacy_denied:scope"
    assert scope["cloud_processing_enabled"] is False

    wrong_case = inspect_privacy_policy(base, user_id="user-a", case_id="case-b")
    assert wrong_case["reason"] == "privacy_denied:case_binding"
    assert wrong_case["policy"]["cloud_processing_enabled"] is False

    malformed = dict(base)
    malformed["consent"] = {"status": "assumed", "cloud_processing": True, "note": MARKER}
    malformed["encryption_at_rest_blocks_remote_llm"] = True
    denied = inspect_privacy_policy(malformed, user_id="user-a", case_id="case-a")
    assert denied["admitted"] is False
    assert denied["cloud_processing_enabled"] is False
    assert MARKER not in json.dumps(denied["policy"])
    assert denied["policy"]["encryption_at_rest_blocks_remote_llm"] is False

    legacy = inspect_privacy_policy(None, user_id="user-a", case_id="case-a")
    assert legacy["reason"] == "legacy_missing"
    assert legacy["cloud_processing_enabled"] is False


def test_legacy_and_malformed_session_permit_no_cloud(tmp_path: Path) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService

    service = _service(tmp_path, users=["legacy-user", "older-user"])
    path = service._session_path("legacy-user")
    path.write_text(
        json.dumps(
            {
                "user_id": "legacy-user",
                "intake_answers": {"party_name": "Legacy Person"},
                "privacy_policy": {
                    "version": "9",
                    "consent": {"status": "yes", "secret": TOKEN, "narrative": MARKER},
                    "cloud_processing_enabled": True,
                },
            }
        )
    )
    reloaded = _service(tmp_path)
    original = path.read_bytes()
    result = reloaded.migrate_legacy_private_session("legacy-user")
    assert result["complete"] and result["source_bytes_preserved"]
    assert path.read_bytes() == original
    state = reloaded._load_state("legacy-user")
    assert state["privacy_policy"]["cloud_processing_enabled"] is False
    assert state["privacy_policy"]["processing_mode"] == "local_private"
    assert state["privacy_policy_load"]["cloud_processing_enabled"] is False
    assert state["privacy_policy_load"]["admitted"] is False
    encoded = json.dumps(state["privacy_policy_load"])
    assert MARKER not in encoded
    assert TOKEN not in encoded
    assert state["intake_answers"]["party_name"] == "Legacy Person"

    missing = service._session_path("older-user")
    missing.write_text(json.dumps({"user_id": "older-user", "intake_answers": {"party_name": "Older"}}))
    older_service = _service(tmp_path)
    before = missing.read_bytes()
    assert older_service.migrate_legacy_private_session("older-user")["complete"]
    assert missing.read_bytes() == before
    older = older_service._load_state("older-user")
    assert older["privacy_policy_load"]["reason"] == "legacy_missing"
    assert older["privacy_policy"]["cloud_processing_enabled"] is False


def test_privacy_commands_do_not_consume_answers_and_persist(tmp_path: Path) -> None:
    from complaint_generator.workspace import get_privacy_policy, set_privacy_policy

    service = _service(tmp_path, users=["chat-user"])
    opening = service.run_intake_chat_turn("chat-user")
    assert opening["privacy_notice"]
    assert opening["inquiry"]["question_id"] == "original_complaint"
    assert opening["inquiry"]["prompt"] in opening["message"]
    assert opening["accepted_answer"] is None

    switched = service.run_intake_chat_turn("chat-user", message="/privacy grok")
    assert switched["accepted_answer"] is None
    assert switched["privacy_command"]["stored_as_answer"] is False
    assert switched["privacy_command"]["processing_mode"] == "grok_cloud"
    assert switched["inquiry"]["question_id"] == "original_complaint"
    assert "/privacy grok" not in json.dumps(switched["session"]["intake_answers"])
    assert "/privacy grok" not in json.dumps(switched["session"]["intake_history"])
    assert "/privacy grok" not in json.dumps(switched["session"]["original_complaint"])
    narrative = service.run_intake_chat_turn("chat-user", message="Synthetic original complaint narrative")
    assert narrative["accepted_answer"]["question_id"] == "original_complaint"
    assert narrative["session"]["intake_answers"] == {}
    assert narrative["legacy_inquiry"]["question_id"] == "party_name"
    assert narrative["inquiry"]["question_id"] == narrative["interview"]["inquiry"]["inquiry_id"]
    assert narrative["inquiry"]["revision"] == narrative["interview"]["expected_question_revision"]

    first = service.run_intake_chat_turn("chat-user", message="Ada Example", question_id="party_name")
    second = service.run_intake_chat_turn("chat-user", message="Opposing Example", question_id="opposing_party")
    assert first["accepted_answer"]["question_id"] == "party_name"
    assert second["accepted_answer"]["question_id"] == "opposing_party"
    assert second["session"]["intake_answers"]["party_name"] == "Ada Example"
    assert "privacy_notice" not in second or second.get("privacy_notice") in {None, ""}

    fresh = _service(tmp_path)
    persisted = get_privacy_policy("chat-user", root_dir=tmp_path, service=fresh)
    assert persisted["policy"]["cloud_processing_enabled"] is True
    assert persisted["policy"]["permitted_remote"] == {"provider": "grok_cli", "model": "grok-4.7"}

    disabled = set_privacy_policy("chat-user", "local", service=_service(tmp_path))
    assert disabled["updated"] is True
    assert disabled["policy"]["cloud_processing_enabled"] is False
    again = get_privacy_policy("chat-user", service=_service(tmp_path))
    assert again["policy"]["processing_mode"] == "local_private"
    assert again["policy"]["cloud_processing_enabled"] is False

    wrong = set_privacy_policy("chat-user", "grok", case_id="some-other-case", service=_service(tmp_path))
    assert wrong["updated"] is False
    assert wrong["load"]["cloud_processing_enabled"] is False
    assert get_privacy_policy("chat-user", service=_service(tmp_path))["policy"]["cloud_processing_enabled"] is False


def test_local_mode_blocks_three_egresses_and_status(
    tmp_path: Path,
    spies: _Spy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.ipfs_datasets.llm as llm
    from applications.complaint_workspace import _llm_router_status_snapshot

    monkeypatch.setenv("IPFS_DATASETS_PY_LLM_PROVIDER", "hf_router")
    monkeypatch.setenv("COMPLAINT_LLM_PROVIDER", "hf_router")
    monkeypatch.setenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "openrouter")
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    monkeypatch.setenv("COMPLAINT_USE_IPFS_LLM_ROUTER_STATUS", "1")

    service = _service(tmp_path, users=["egress-user"])
    user_id = "egress-user"
    _seed_draft(service, user_id, f"Draft body that must stay local. {MARKER}")

    grounded = service.generate_grounded_text(
        user_id,
        prompt=f"Rewrite {MARKER}",
        provider="hf_router",
        model_name="katanemo/Arch-Router-1.5B",
    )
    _assert_quiet(spies, grounded)
    assert grounded["generation"]["error"] == "privacy_denied:cloud_processing_disabled"
    assert grounded["text"] == ""

    def _score(*_args, **_kwargs):
        return {
            "grade": "C",
            "overall_score": 10,
            "suggestions": [{"priority": "high", "action": f"tighten {MARKER}", "dimension": "form"}],
        }

    monkeypatch.setattr("integrations.ipfs_datasets.quality.score_draft_quality", _score)
    improved = service.improve_draft(user_id, provider="openrouter", model="other-model")
    _assert_quiet(spies, {"errors": improved["llm_errors"], "improved": improved["improved"]})
    assert improved["improved"] is False
    assert improved["llm_errors"] == ["privacy_denied:cloud_processing_disabled"]
    assert MARKER not in json.dumps(improved["llm_errors"])

    class _Backend:
        def __init__(self, **kwargs):
            spies.backend += 1
            spies.backend_kwargs.append(kwargs)

        def __call__(self, prompt: str) -> str:
            spies.prompts.append(prompt)
            return "unused"

    monkeypatch.setattr("backends.LLMRouterBackend", _Backend)
    draft = service.generate_complaint(user_id, use_llm=True, provider="hf_router", model="some-model")
    assert spies.backend == 0
    _assert_quiet(spies, {"reason": draft["draft"].get("draft_fallback_reason")})
    assert draft["draft"]["draft_fallback_reason"] == "privacy_denied:cloud_processing_disabled"

    status = llm.llm_router_status(
        provider="hf_router",
        model_name="katanemo/Arch-Router-1.5B",
        prompt=MARKER,
        perform_probe=False,
        base_url="https://router.huggingface.co/v1",
    )
    snapshot = _llm_router_status_snapshot()
    _assert_quiet(spies, {"status": status, "snapshot": snapshot})
    assert status["static_capability_only"] is True
    assert status["dispatch"] == "none"
    assert status["probe_performed"] is False
    assert snapshot["probe_performed"] is False

    probed = llm.llm_router_status(
        provider="hf_router",
        model_name="katanemo/Arch-Router-1.5B",
        prompt=MARKER,
        perform_probe=True,
        complaint_privacy_context=llm.build_complaint_privacy_context(
            service.get_privacy_policy(user_id)["policy"],
            user_id=user_id,
            case_id=user_id,
            data_class="raw_intake",
        ),
    )
    _assert_quiet(spies, probed)
    assert probed["error"] == "privacy_denied:cloud_processing_disabled"
    assert probed["probe_performed"] is False


def test_grok_opt_in_is_exact_and_does_not_fall_back(
    tmp_path: Path,
    spies: _Spy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.ipfs_datasets.llm as llm

    monkeypatch.setenv("IPFS_DATASETS_PY_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    service = _service(tmp_path, users=["grok-user"])
    user_id = "grok-user"
    service.set_privacy_policy(user_id, "grok")
    _seed_draft(service, user_id, f"Filed body {MARKER}")
    policy = service.get_privacy_policy(user_id)["policy"]
    context = llm.build_complaint_privacy_context(
        policy,
        user_id=user_id,
        case_id=user_id,
        data_class="drafts_proofs",
    )

    denied = llm.generate_text_with_metadata(
        f"send {MARKER} {TOKEN}",
        provider="openrouter",
        model_name="grok-4.7",
        complaint_privacy_context=context,
    )
    _assert_quiet(spies, denied)
    assert denied["error"] == "privacy_denied:grok_scope_mismatch"

    mismatched_model = llm.generate_text_with_metadata(
        MARKER,
        provider="grok_cli",
        model_name="grok-4",
        complaint_privacy_context=context,
    )
    _assert_quiet(spies, mismatched_model)
    assert mismatched_model["error"] == "privacy_denied:grok_scope_mismatch"

    with pytest.raises(RuntimeError) as raised:
        llm.generate_text_via_router(
            f"{MARKER} {TOKEN}",
            provider="grok_cli",
            model_name="grok-4",
            complaint_privacy_context=context,
        )
    assert MARKER not in str(raised.value)
    assert TOKEN not in str(raised.value)
    assert spies.prepare == 0

    allowed = llm.generate_text_with_metadata(
        f"{MARKER} stays in the prompt argument only",
        provider="grok_cli",
        model_name="grok-4.7",
        complaint_privacy_context=context,
    )
    assert spies.provider == 1
    assert spies.architecture == 0
    assert spies.socket == 0
    assert spies.process == 0

    assert allowed["status"] == "available"
    assert MARKER not in json.dumps({key: value for key, value in allowed.items() if key != "prompt"})

    class _Backend:
        def __init__(self, **kwargs):
            spies.backend += 1
            spies.backend_kwargs.append(kwargs)
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")
            self.last_result_metadata = {}

        def __call__(self, prompt: str) -> str:
            spies.prompts.append(prompt)
            return "not-a-formal-complaint"

    monkeypatch.setattr("backends.LLMRouterBackend", _Backend)
    refused = service.generate_complaint(user_id, use_llm=True, provider="openrouter", model="grok-4.7")
    assert spies.backend == 0
    assert refused["draft"]["draft_fallback_reason"] == "privacy_denied:grok_scope_mismatch"
    assert MARKER not in str(refused["draft"]["draft_fallback_reason"])

    service.generate_complaint(user_id, use_llm=True, provider="grok_cli", model="grok-4.7")
    assert spies.backend == 1
    assert spies.backend_kwargs[0]["complaint_privacy_context"]["policy"]["permitted_remote"]["provider"] == "grok_cli"
    assert spies.architecture == 0

    probed = llm.llm_router_status(
        provider="grok_cli",
        model_name="grok-4.7",
        prompt=MARKER,
        perform_probe=True,
        complaint_privacy_context=context,
    )
    assert probed["probe_performed"] is True
    assert spies.architecture == 0
    assert spies.socket == 0
    assert spies.process == 0
    assert MARKER not in json.dumps(probed)

    bare_probe = llm.llm_router_status(provider="grok_cli", model_name="grok-4.7", prompt=MARKER, perform_probe=True)
    assert bare_probe["error"] == "privacy_denied:cloud_processing_disabled"
    assert spies.socket == 0
    assert spies.process == 0


@pytest.mark.parametrize("override", [
    {"base_url": "https://router.huggingface.co/v1", "arch_router_routes": [{"model": "other-model", "name": "other"}]},
    {"provider_instance": object()},
    {"deps": object()},
    {"allocation_path": "api"},
    {"grok_cli_cmd": ["grok", "--model", "grok-4"]},
])
def test_cloud_consent_cannot_redirect_private_dispatch(spies, monkeypatch, override):
    import integrations.ipfs_datasets.llm as llm

    monkeypatch.setenv("HF_TOKEN", TOKEN)
    context = llm.build_complaint_privacy_context(
        llm.privacy_policy_for_mode("route-user", "route-case", "grok"),
        user_id="route-user", case_id="route-case", data_class="raw_intake")
    denied = llm.generate_text_with_metadata(MARKER, provider="grok_cli",
        model_name="grok-4.7", complaint_privacy_context=context, **override)
    _assert_quiet(spies, denied)
    assert denied["privacy_decision"] == "denied"
    assert denied["dispatch"] == "none"


def test_private_grok_dispatch_explicitly_disables_both_fallbacks(monkeypatch):
    import integrations.ipfs_datasets.llm as llm

    calls = []
    def provider(**kwargs):
        calls.append(kwargs)
        return "synthetic output"
    monkeypatch.setattr(llm, "generate_text", provider)
    context = llm.build_complaint_privacy_context(
        llm.privacy_policy_for_mode("pin-user", "pin-case", "grok"),
        user_id="pin-user", case_id="pin-case", data_class="raw_intake")
    result = llm.generate_text_with_metadata(MARKER, provider="grok_cli",
        model_name="grok-4.7", complaint_privacy_context=context,
        allow_local_fallback=True, allow_cross_provider_fallback=True)
    assert result["status"] == "available"
    assert len(calls) == 1
    assert calls[0]["provider"] == "grok_cli" and calls[0]["model_name"] == "grok-4.7"
    assert calls[0]["allow_local_fallback"] is False
    assert calls[0]["allow_cross_provider_fallback"] is False


def test_private_failure_uses_native_router_without_model_or_provider_retry(monkeypatch):
    import integrations.ipfs_datasets.llm as llm
    import ipfs_accelerate_py.llm_router as router
    from types import SimpleNamespace

    calls = []
    class Primary:
        def generate(self, prompt, *, model_name=None, **kwargs):
            calls.append(("grok_cli", model_name))
            raise RuntimeError(MARKER + TOKEN)
    class Fallback:
        def generate(self, *args, **kwargs):
            calls.append(("fallback", "other-model"))
            return "fallback must not run"
    def get_provider(name, **kwargs):
        assert name == "grok_cli"
        return Primary()
    def optional():
        calls.append(("fallback-discovery", ""))
        return iter([("openrouter", Fallback())])
    monkeypatch.setattr(router, "get_default_router_deps", lambda: SimpleNamespace())
    monkeypatch.setattr(router, "get_llm_provider", get_provider)
    monkeypatch.setattr(router, "_iter_unpinned_optional_providers", optional)
    monkeypatch.setattr(router, "_response_cache_enabled", lambda: False)
    monkeypatch.setattr(llm, "generate_text", router.generate_text)
    context = llm.build_complaint_privacy_context(
        llm.privacy_policy_for_mode("native-user", "native-case", "grok"),
        user_id="native-user", case_id="native-case", data_class="raw_intake")
    result = llm.generate_text_with_metadata(MARKER, provider="grok_cli",
        model_name="grok-4.7", complaint_privacy_context=context)
    assert calls == [("grok_cli", "grok-4.7")]
    assert result["status"] == "error" and result["error"] == "private_generation_failed"
    assert MARKER not in json.dumps(result) and TOKEN not in json.dumps(result)


@pytest.mark.parametrize("failure", ["unavailable", "preflight", "provider"])
def test_private_error_receipts_never_quote_prompt_or_backend_error(monkeypatch, failure):
    import integrations.ipfs_datasets.llm as llm

    context = llm.build_complaint_privacy_context(
        llm.privacy_policy_for_mode("error-user", "error-case", "grok"),
        user_id="error-user", case_id="error-case", data_class="drafts_proofs")
    if failure == "unavailable":
        monkeypatch.setattr(llm, "generate_text", None)
        monkeypatch.setattr(llm, "LLM_ROUTER_ERROR", MARKER + TOKEN)
    else:
        def provider(**kwargs):
            raise RuntimeError("provider echoed " + kwargs["prompt"] + TOKEN)
        monkeypatch.setattr(llm, "generate_text", provider)
        if failure == "preflight":
            monkeypatch.setattr(llm, "_provider_preflight_error", lambda **kwargs: MARKER + TOKEN)
    result = llm.generate_text_with_metadata(MARKER, provider="grok_cli",
        model_name="grok-4.7", complaint_privacy_context=context)
    assert result["status"] in {"error", "unavailable"}
    assert "prompt" not in result
    assert MARKER not in json.dumps(result) and TOKEN not in json.dumps(result)


@pytest.mark.parametrize("field", ["private", "public", "excluded_path_classes"])
@pytest.mark.parametrize("malformed", [1, True, {"unexpected": "value"}])
def test_malformed_nested_consent_is_denied_without_parser_crash(field, malformed):
    from integrations.ipfs_datasets.llm import inspect_privacy_policy, privacy_policy_for_mode

    policy = privacy_policy_for_mode("bad-user", "bad-case", "grok")
    if field == "excluded_path_classes":
        policy["agent_context"][field] = malformed
    else:
        policy["data_classes"][field] = malformed
    result = inspect_privacy_policy(policy, user_id="bad-user", case_id="bad-case")
    assert result["admitted"] is False
    assert result["cloud_processing_enabled"] is False


def test_workspace_backend_config_cannot_replace_its_private_context(tmp_path, monkeypatch):
    import integrations.ipfs_datasets.llm as llm
    import applications.ui_review as review
    calls = []
    monkeypatch.setattr(llm, "generate_text", lambda **kwargs: calls.append(kwargs) or "unused")
    forged = llm.build_complaint_privacy_context(
        llm.privacy_policy_for_mode("other-user", "other-case", "grok"),
        user_id="other-user", case_id="other-case", data_class="public_legal_source_graph")
    monkeypatch.setattr(review, "_load_backend_kwargs", lambda *a, **k: {
        "id": "synthetic", "complaint_privacy_context": forged})
    service = _service(tmp_path, users=["local-user"])
    _seed_draft(service, "local-user", MARKER)
    generated = service.generate_complaint("local-user", use_llm=True,
        provider="grok_cli", model="grok-4.7")
    assert calls == []
    assert generated["draft"]["draft_fallback_reason"] == "privacy_denied:cloud_processing_disabled"


def test_loaded_foreign_identity_cannot_transfer_cloud_consent(tmp_path, spies):
    import integrations.ipfs_datasets.llm as llm

    service = _service(tmp_path, users=["selected-user"])
    state = service._load_state("selected-user")
    state["user_id"] = "foreign-user"
    state["case_id"] = "foreign-case"
    state["privacy_policy"] = llm.privacy_policy_for_mode("foreign-user", "foreign-case", "grok")
    state["draft"] = {"title": "Synthetic", "body": MARKER}
    service._session_path("selected-user").write_text(json.dumps(state))
    original = service._session_path("selected-user").read_bytes()
    from applications.complaint_workspace import WorkspaceAuthorizationDenied
    with pytest.raises(WorkspaceAuthorizationDenied, match="^authorization_denied$"):
        service._load_state("selected-user")
    with pytest.raises(WorkspaceAuthorizationDenied, match="^authorization_denied$"):
        service.set_privacy_policy("selected-user", "local")
    assert service._session_path("selected-user").read_bytes() == original
    _assert_quiet(spies, {"reason": "authorization_denied"})
    assert not service._session_path("foreign-user").exists()


def test_draft_backend_error_receipt_cannot_quote_private_case(tmp_path, monkeypatch):
    import applications.ui_review as review

    def fail(*args, **kwargs):
        raise RuntimeError(MARKER + TOKEN)
    monkeypatch.setattr(review, "_load_backend_kwargs", fail)
    service = _service(tmp_path, users=["draft-error"])
    service.set_privacy_policy("draft-error", "grok")
    state = service._load_state("draft-error")
    assert service._refine_draft_with_llm_router(state, {"body": MARKER}, provider="grok_cli", model="grok-4.7") is None
    assert service._last_draft_refinement_error == "private_generation_failed"


@pytest.mark.parametrize("entrypoint", ["string", "probe"])
def test_other_private_generation_errors_have_stable_receipts(monkeypatch, entrypoint):
    import integrations.ipfs_datasets.llm as llm

    def fail(**kwargs):
        raise RuntimeError(kwargs["prompt"] + TOKEN)
    monkeypatch.setattr(llm, "generate_text", fail)
    context = llm.build_complaint_privacy_context(
        llm.privacy_policy_for_mode("receipt-user", "receipt-case", "grok"),
        user_id="receipt-user", case_id="receipt-case", data_class="raw_intake")
    if entrypoint == "string":
        with pytest.raises(RuntimeError, match="^private_generation_failed$"):
            llm.generate_text_via_router(MARKER, provider="grok_cli", model_name="grok-4.7", complaint_privacy_context=context)
    else:
        result = llm.llm_router_status(provider="grok_cli", model_name="grok-4.7",
            perform_probe=True, prompt=MARKER, complaint_privacy_context=context)
        assert result["probe_status"] == "error"
        assert MARKER not in json.dumps(result) and TOKEN not in json.dumps(result)
