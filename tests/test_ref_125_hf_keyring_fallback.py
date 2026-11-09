import logging
import sys
import types

from integrations.ipfs_datasets import llm


_HF_TOKEN_ENV_NAMES = (
    "IPFS_DATASETS_PY_HF_API_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN",
    "HF_TOKEN",
    "HUGGINGFACE_HUB_TOKEN",
    "HUGGINGFACE_API_KEY",
    "HUGGINGFACE_API_TOKEN",
    "HF_API_TOKEN",
)


def _clear_hf_token_environment(monkeypatch):
    for name in _HF_TOKEN_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _disable_vault(monkeypatch):
    vault_module = types.SimpleNamespace(
        get_secrets_vault=lambda: (_ for _ in ()).throw(
            RuntimeError("secrets vault unavailable")
        )
    )
    monkeypatch.setitem(
        sys.modules,
        "ipfs_datasets_py.mcp_server.secrets_vault",
        vault_module,
    )


def test_keyring_failure_is_logged_before_huggingface_cache_fallback(
    monkeypatch,
    caplog,
):
    _clear_hf_token_environment(monkeypatch)
    _disable_vault(monkeypatch)

    class FailingKeyring:
        @staticmethod
        def get_password(service, name):
            raise RuntimeError("keyring backend unavailable")

    monkeypatch.setitem(sys.modules, "keyring", FailingKeyring)
    monkeypatch.setattr(
        llm.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(get_token=lambda: "cached-hf-token"),
    )

    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        token = llm._resolve_hf_token()

    assert token == "cached-hf-token"
    assert "token lookup through keyring failed" in caplog.text
    assert "falling back to the Hugging Face client token cache" in caplog.text
    assert "RuntimeError: keyring backend unavailable" in caplog.text
    assert "cached-hf-token" not in caplog.text


def test_successful_keyring_lookup_does_not_emit_fallback_warning(
    monkeypatch,
    caplog,
):
    _clear_hf_token_environment(monkeypatch)
    _disable_vault(monkeypatch)

    class WorkingKeyring:
        @staticmethod
        def get_password(service, name):
            if service == "ipfs_datasets_py" and name == "HF_TOKEN":
                return "keyring-hf-token"
            return None

    monkeypatch.setitem(sys.modules, "keyring", WorkingKeyring)
    monkeypatch.setattr(
        llm.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(get_token=lambda: "cached-hf-token"),
    )

    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        token = llm._resolve_hf_token()

    assert token == "keyring-hf-token"
    assert "token lookup through keyring failed" not in caplog.text
    assert "keyring-hf-token" not in caplog.text
