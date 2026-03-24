from __future__ import annotations

import argparse
import importlib
import importlib.util
from pathlib import Path

import pytest


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_gmail_evidence.py"
    spec = importlib.util.spec_from_file_location("import_gmail_evidence_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_credentials_can_prompt_securely(monkeypatch):
    module = _load_script_module()
    credentials_module = importlib.import_module("complaint_generator.email_credentials")
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="",
        gmail_app_password="",
        prompt_for_credentials=True,
        use_keyring=False,
        save_to_keyring=False,
    )

    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(module.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(credentials_module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(credentials_module.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "user@gmail.com")
    monkeypatch.setattr(credentials_module.getpass, "getpass", lambda prompt="": "app-password")

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == "app-password"


def test_resolve_credentials_requires_non_interactive_credentials():
    module = _load_script_module()
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="",
        gmail_app_password="",
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=False,
    )

    with pytest.raises(SystemExit):
        module._resolve_credentials(args, parser)


def test_resolve_credentials_can_load_password_from_keyring(monkeypatch):
    module = _load_script_module()
    credentials_module = importlib.import_module("complaint_generator.email_credentials")
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="user@gmail.com",
        gmail_app_password="",
        prompt_for_credentials=False,
        use_keyring=True,
        save_to_keyring=False,
    )

    monkeypatch.setattr(credentials_module, "read_password_from_keyring", lambda user: "stored-app-password")

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == "stored-app-password"


def test_resolve_credentials_can_save_password_to_keyring(monkeypatch):
    module = _load_script_module()
    credentials_module = importlib.import_module("complaint_generator.email_credentials")
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="user@gmail.com",
        gmail_app_password="provided-app-password",
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=True,
    )
    captured = {}

    monkeypatch.setattr(credentials_module, "save_password_to_keyring", lambda user, password, parser_obj: captured.update({"user": user, "password": password}))

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == "provided-app-password"
    assert captured == {"user": "user@gmail.com", "password": "provided-app-password"}
