import io
import json
from unittest.mock import patch


def test_unpinned_optional_provider_order_prefers_codex_then_openai_then_copilot_then_hf():
    from ipfs_datasets_py.llm_router import _UNPINNED_OPTIONAL_PROVIDER_ORDER

    assert _UNPINNED_OPTIONAL_PROVIDER_ORDER[:4] == [
        "codex_cli",
        "openai",
        "copilot_cli",
        "hf_inference_api",
    ]


def test_get_llm_provider_prefers_openai_when_codex_is_unavailable(monkeypatch):
    from ipfs_datasets_py import llm_router

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.delenv("IPFS_DATASETS_PY_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(llm_router, "_get_accelerate_provider", lambda deps=None: None)
    monkeypatch.setattr(llm_router, "_get_local_hf_provider", lambda deps=None: None)
    monkeypatch.setattr(llm_router.shutil, "which", lambda name: None if name == "codex" else "")

    provider = llm_router.get_llm_provider(use_cache=False)
    assert provider.__class__.__name__ == "_OpenAIProvider"


def test_generate_text_with_openai_provider_uses_api_key(monkeypatch):
    from ipfs_datasets_py.llm_router import generate_text

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "OpenAI provider response",
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    observed = {}

    def _fake_urlopen(req, timeout=0):
        observed["authorization"] = req.headers.get("Authorization")
        observed["url"] = req.full_url
        observed["body"] = json.loads(req.data.decode("utf-8"))
        observed["timeout"] = timeout
        return _FakeResponse()

    with patch("ipfs_datasets_py.llm_router.urllib.request.urlopen", side_effect=_fake_urlopen):
        result = generate_text(
            "Draft a complaint caption.",
            provider="openai",
            model_name="gpt-4.1-mini",
            timeout=15,
        )

    assert result == "OpenAI provider response"
    assert observed["authorization"] == "Bearer sk-test-openai"
    assert observed["url"] == "https://api.openai.com/v1/chat/completions"
    assert observed["body"]["model"] == "gpt-4.1-mini"
    assert observed["body"]["messages"][0]["content"] == "Draft a complaint caption."
    assert observed["timeout"] == 15
