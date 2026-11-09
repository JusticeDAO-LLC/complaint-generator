import logging
import sys
import types

import pytest

from integrations.ipfs_datasets import llm


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network]

_OPENAI_KEY_ENV_NAMES = ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")


def _clear_openai_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _OPENAI_KEY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_openai_vault_failure_is_observable_during_keyring_fallback(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _clear_openai_key_env(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "ipfs_datasets_py.mcp_server.secrets_vault",
        types.SimpleNamespace(
            get_secrets_vault=lambda: (_ for _ in ()).throw(
                RuntimeError("vault storage unavailable")
            )
        ),
    )

    class _FakeKeyring:
        @staticmethod
        def get_password(service: str, name: str) -> str | None:
            if service == "ipfs_datasets_py" and name == "OPENAI_API_KEY":
                return "resolved-secret-key"
            return None

    monkeypatch.setitem(sys.modules, "keyring", _FakeKeyring)

    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        token = llm._resolve_openai_api_key()

    assert token == "resolved-secret-key"
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.name == llm.__name__
    assert record.levelno == logging.WARNING
    assert "secrets vault" in record.getMessage()
    assert "trying the keyring and common-file fallbacks" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert str(record.exc_info[1]) == "vault storage unavailable"
    assert "resolved-secret-key" not in caplog.text


def test_successful_openai_vault_lookup_does_not_warn(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _clear_openai_key_env(monkeypatch)

    class _FakeVault:
        def get(self, name: str) -> str | None:
            if name == "OPENAI_KEY":
                return "vault-secret-key"
            return None

    monkeypatch.setitem(
        sys.modules,
        "ipfs_datasets_py.mcp_server.secrets_vault",
        types.SimpleNamespace(get_secrets_vault=lambda: _FakeVault()),
    )

    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        token = llm._resolve_openai_api_key()

    assert token == "vault-secret-key"
    assert caplog.records == []
