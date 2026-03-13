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

    model_name = os.getenv("HF_ROUTER_SMOKE_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    payload = llm.generate_text_with_metadata(
        "Reply with exactly OK.",
        provider="huggingface_router",
        model_name=model_name,
        base_url=llm.HF_ROUTER_DEFAULT_BASE_URL,
        headers={"X-Title": "Complaint Generator Smoke Test"},
        max_tokens=8,
        temperature=0.0,
        timeout=45,
    )

    assert payload["status"] == "available", payload
    assert payload["effective_provider_name"] == "openrouter"
    assert payload["effective_model_name"] == model_name
    assert payload["router_base_url"] == llm.HF_ROUTER_DEFAULT_BASE_URL
    assert payload["text"].strip(), payload