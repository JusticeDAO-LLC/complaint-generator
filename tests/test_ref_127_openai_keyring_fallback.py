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


def _install_empty_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "ipfs_datasets_py.mcp_server.secrets_vault",
        types.SimpleNamespace(
            get_secrets_vault=lambda: types.SimpleNamespace(get=lambda name: None)
        ),
    )


def test_openai_keyring_failure_is_observable_during_common_file_fallback(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _clear_openai_key_env(monkeypatch)
    _install_empty_vault(monkeypatch)

    class _FailingKeyring:
        @staticmethod
        def get_password(service: str, name: str) -> str | None:
            raise RuntimeError("keyring backend unavailable")

    monkeypatch.setitem(sys.modules, "keyring", _FailingKeyring)
    monkeypatch.setattr(
        llm.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(
            _openai_key_from_common_files=lambda: "resolved-secret-key"
        ),
    )

    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        token = llm._resolve_openai_api_key()

    assert token == "resolved-secret-key"
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.name == llm.__name__
    assert record.levelno == logging.WARNING
    assert "API-key lookup through keyring failed" in record.getMessage()
    assert "falling back to common local configuration files" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert str(record.exc_info[1]) == "keyring backend unavailable"
    assert "resolved-secret-key" not in caplog.text


def test_successful_openai_keyring_lookup_does_not_warn(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _clear_openai_key_env(monkeypatch)
    _install_empty_vault(monkeypatch)

    class _WorkingKeyring:
        @staticmethod
        def get_password(service: str, name: str) -> str | None:
            if service == "ipfs_datasets_py" and name == "OPENAI_KEY":
                return "keyring-secret-key"
            return None

    monkeypatch.setitem(sys.modules, "keyring", _WorkingKeyring)

    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        token = llm._resolve_openai_api_key()

    assert token == "keyring-secret-key"
    assert caplog.records == []
