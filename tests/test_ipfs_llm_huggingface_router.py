import os

import pytest

from integrations.ipfs_datasets import llm


pytestmark = pytest.mark.no_auto_network


def _live_hf_token() -> str:
    return (
        os.getenv("HF_TOKEN", "").strip()
        or os.getenv("HUGGINGFACE_HUB_TOKEN", "").strip()
        or os.getenv("HUGGINGFACE_API_KEY", "").strip()
        or os.getenv("HF_API_TOKEN", "").strip()
    )


def _is_provider_credit_error(payload_or_message: object) -> bool:
    text = str(payload_or_message or "")
    lowered = text.lower()
    return "402" in lowered and ("payment required" in lowered or "included credits" in lowered or "depleted" in lowered)


def _is_upstream_router_error(payload_or_message: object) -> bool:
    text = str(payload_or_message or "")
    lowered = text.lower()
    return (
        "openrouter http" in lowered
        or "payment required" in lowered
        or "included credits" in lowered
        or "depleted" in lowered
        or "access denied" in lowered
        or "browser_signature_banned" in lowered
        or "error 1010" in lowered
        or "owner_action_required" in lowered
    )


def _hf_router_smoke_models() -> list[str]:
    configured_models = [
        candidate.strip()
        for candidate in os.getenv("HF_ROUTER_SMOKE_MODELS", "").split(",")
        if candidate.strip()
    ]
    if configured_models:
        return configured_models

    configured_model = os.getenv("HF_ROUTER_SMOKE_MODEL", "").strip()
    if configured_model:
        return [configured_model]

    return [
        "meta-llama/Llama-3.1-8B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "google/gemma-2-9b-it",
    ]


def _upstream_failure_summary(payload_or_message: object) -> str:
    if isinstance(payload_or_message, dict):
        for candidate in (
            payload_or_message.get("error"),
            payload_or_message.get("arch_router_error"),
            ((payload_or_message.get("metadata") or {}).get("degraded_reason") if isinstance(payload_or_message.get("metadata"), dict) else ""),
        ):
            if candidate:
                text = str(candidate)
                compact = " ".join(text.split())
                return compact[:280]
    text = str(payload_or_message or "")
    compact = " ".join(text.split())
    return compact[:280]


def _run_live_hf_router_smoke(prompt: str, *, headers: dict[str, str], **kwargs) -> tuple[str, dict]:
    failures: list[str] = []
    for model_name in _hf_router_smoke_models():
        payload = llm.generate_text_with_metadata(
            prompt,
            provider="huggingface_router",
            model_name=model_name,
            base_url=llm.HF_ROUTER_DEFAULT_BASE_URL,
            headers=headers,
            **kwargs,
        )
        if payload.get("status") == "available":
            return model_name, payload
        if _is_upstream_router_error(payload) or (
            payload.get("status") == "error" and payload.get("effective_provider_name") == "openrouter"
        ):
            failures.append(f"{model_name}: {_upstream_failure_summary(payload)}")
            continue
        return model_name, payload

    pytest.skip("Hugging Face router live smoke unavailable after trying models: " + " | ".join(failures))


def test_generate_text_via_router_normalizes_huggingface_router(monkeypatch):
    observed = {}

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        observed["prompt"] = prompt
        observed["provider"] = provider
        observed["model_name"] = model_name
        observed["kwargs"] = dict(kwargs)
        observed["base_url"] = os.environ.get("IPFS_DATASETS_PY_OPENROUTER_BASE_URL")
        observed["api_key"] = os.environ.get("IPFS_DATASETS_PY_OPENROUTER_API_KEY")
        observed["app_title"] = os.environ.get("OPENROUTER_APP_TITLE")
        observed["bill_to"] = os.environ.get("OPENROUTER_HF_BILL_TO")
        return "ok"

    monkeypatch.setattr(llm, "generate_text", _fake_generate_text)
    monkeypatch.setenv("HF_TOKEN", "hf-test-token")

    result = llm.generate_text_via_router(
        "Test prompt",
        provider="huggingface_router",
        model_name="Qwen/Qwen3-Coder-480B-A35B-Instruct",
        base_url="https://router.huggingface.co/v1",
        headers={"X-Title": "Complaint Generator"},
        max_tokens=256,
    )

    assert result == "ok"
    assert observed["prompt"] == "Test prompt"
    assert observed["provider"] == "openrouter"
    assert observed["model_name"] == "Qwen/Qwen3-Coder-480B-A35B-Instruct"
    assert observed["kwargs"]["max_tokens"] == 256
    assert observed["base_url"] == "https://router.huggingface.co/v1"
    assert observed["api_key"] == "hf-test-token"
    assert observed["app_title"] == "Complaint Generator"
    assert observed["bill_to"] in {None, ""}


def test_generate_text_with_metadata_propagates_hf_bill_to(monkeypatch):
    observed = {}

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        observed["provider"] = provider
        observed["model_name"] = model_name
        observed["bill_to"] = os.environ.get("OPENROUTER_HF_BILL_TO")
        return "metadata-ok"

    monkeypatch.setattr(llm, "generate_text", _fake_generate_text)
    monkeypatch.setenv("HF_TOKEN", "hf-test-token")

    payload = llm.generate_text_with_metadata(
        "Prompt",
        provider="huggingface_router",
        model_name="meta-llama/Llama-3.3-70B-Instruct",
        base_url="https://router.huggingface.co/v1",
        headers={"X-HF-Bill-To": "Publicus"},
    )

    assert payload["status"] == "available"
    assert payload["hf_bill_to"] == "Publicus"
    assert observed["provider"] == "openrouter"
    assert observed["bill_to"] == "Publicus"


def test_generate_text_with_metadata_treats_huggingface_base_url_as_remote(monkeypatch):
    observed = {}

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        observed["provider"] = provider
        observed["model_name"] = model_name
        observed["base_url"] = os.environ.get("IPFS_DATASETS_PY_OPENROUTER_BASE_URL")
        observed["api_key"] = os.environ.get("IPFS_DATASETS_PY_OPENROUTER_API_KEY")
        return "metadata-ok"

    monkeypatch.setattr(llm, "generate_text", _fake_generate_text)
    monkeypatch.setenv("HUGGINGFACE_HUB_TOKEN", "hub-token")

    payload = llm.generate_text_with_metadata(
        "Prompt",
        provider="huggingface",
        model_name="meta-llama/Llama-3.3-70B-Instruct",
        base_url="https://router.huggingface.co/v1",
    )

    assert payload["status"] == "available"
    assert payload["text"] == "metadata-ok"
    assert payload["provider_name"] == "huggingface"
    assert payload["effective_provider_name"] == "openrouter"
    assert payload["effective_model_name"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert payload["router_base_url"] == "https://router.huggingface.co/v1"
    assert observed["provider"] == "openrouter"
    assert observed["model_name"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert observed["base_url"] == "https://router.huggingface.co/v1"
    assert observed["api_key"] == "hub-token"


def test_generate_text_with_metadata_uses_arch_router_to_select_model(monkeypatch):
    observed_calls = []

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        observed_calls.append(
            {
                "prompt": prompt,
                "provider": provider,
                "model_name": model_name,
                "kwargs": dict(kwargs),
                "base_url": os.environ.get("IPFS_DATASETS_PY_OPENROUTER_BASE_URL"),
            }
        )
        if model_name == llm.HF_ARCH_ROUTER_MODEL:
            assert "legal_reasoning" in prompt
            assert "drafting" in prompt
            return '{"route":"legal_reasoning"}'
        return "chosen-model-output"

    monkeypatch.setattr(llm, "generate_text", _fake_generate_text)
    monkeypatch.setenv("HF_TOKEN", "hf-test-token")

    payload = llm.generate_text_with_metadata(
        "Draft a complaint section using the strongest legal theory.",
        provider="huggingface_router",
        model_name="Qwen/Qwen3-Coder-480B-A35B-Instruct",
        base_url=llm.HF_ROUTER_DEFAULT_BASE_URL,
        arch_router={
            "enabled": True,
            "routes": [
                {
                    "name": "legal_reasoning",
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "description": "Use for legal analysis, issue spotting, and argument selection.",
                },
                {
                    "name": "drafting",
                    "model": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
                    "description": "Use for structured drafting and revision.",
                },
            ],
        },
        max_tokens=512,
    )

    assert payload["status"] == "available"
    assert payload["text"] == "chosen-model-output"
    assert payload["effective_provider_name"] == "openrouter"
    assert payload["effective_model_name"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert payload["arch_router_status"] == "selected"
    assert payload["arch_router_selected_route"] == "legal_reasoning"
    assert payload["arch_router_selected_model"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert payload["arch_router_model_name"] == llm.HF_ARCH_ROUTER_MODEL
    assert len(observed_calls) == 2
    assert observed_calls[0]["provider"] == "openrouter"
    assert observed_calls[0]["model_name"] == llm.HF_ARCH_ROUTER_MODEL
    assert observed_calls[1]["provider"] == "openrouter"
    assert observed_calls[1]["model_name"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert observed_calls[1]["kwargs"]["max_tokens"] == 512
    assert observed_calls[1]["base_url"] == llm.HF_ROUTER_DEFAULT_BASE_URL


def test_generate_text_via_router_falls_back_when_arch_router_returns_unknown_route(monkeypatch):
    observed_calls = []

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        observed_calls.append({
            "prompt": prompt,
            "provider": provider,
            "model_name": model_name,
            "kwargs": dict(kwargs),
        })
        if model_name == llm.HF_ARCH_ROUTER_MODEL:
            return '{"route":"unknown_path"}'
        return "fallback-output"

    monkeypatch.setattr(llm, "generate_text", _fake_generate_text)
    monkeypatch.setenv("HF_TOKEN", "hf-test-token")

    result = llm.generate_text_via_router(
        "Summarize the filing packet.",
        provider="huggingface_router",
        model_name="Qwen/Qwen3-Coder-480B-A35B-Instruct",
        base_url=llm.HF_ROUTER_DEFAULT_BASE_URL,
        arch_router={
            "enabled": True,
            "routes": {
                "drafting": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
                "reasoning": "meta-llama/Llama-3.3-70B-Instruct",
            },
        },
    )

    assert result == "fallback-output"
    assert len(observed_calls) == 2
    assert observed_calls[1]["provider"] == "openrouter"
    assert observed_calls[1]["model_name"] == "Qwen/Qwen3-Coder-480B-A35B-Instruct"


@pytest.mark.llm
@pytest.mark.network
def test_generate_text_with_metadata_live_huggingface_router_smoke():
    if not llm.LLM_ROUTER_AVAILABLE:
        pytest.skip(f"llm_router unavailable: {llm.LLM_ROUTER_ERROR}")

    if not _live_hf_token():
        pytest.skip("Set HF_TOKEN or HUGGINGFACE_HUB_TOKEN to run the live Hugging Face router smoke test")

    model_name, payload = _run_live_hf_router_smoke(
        "Reply with exactly OK.",
        headers={
            "X-Title": "Complaint Generator Smoke Test",
            **({"X-HF-Bill-To": os.getenv("IPFS_DATASETS_PY_HF_BILL_TO", "").strip()} if os.getenv("IPFS_DATASETS_PY_HF_BILL_TO", "").strip() else {}),
        },
        max_tokens=8,
        temperature=0.0,
        timeout=45,
    )

    assert payload["status"] == "available", payload
    assert payload["effective_provider_name"] == "openrouter"
    assert payload["effective_model_name"] == model_name
    assert payload["router_base_url"] == llm.HF_ROUTER_DEFAULT_BASE_URL
    assert payload["text"].strip(), payload