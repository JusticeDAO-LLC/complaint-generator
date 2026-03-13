import os

import pytest

from integrations.ipfs_datasets import llm


pytestmark = pytest.mark.no_auto_network


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