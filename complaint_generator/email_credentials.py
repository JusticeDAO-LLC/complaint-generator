from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


KEYRING_SERVICE = "complaint-generator.gmail"
IPFS_VAULT_SECRET_PREFIX = "gmail-app-password"


def _load_keyring():
    try:
        import keyring  # type: ignore
    except Exception:
        return None
    return keyring


def _load_ipfs_secrets_vault():
    try:
        from ipfs_datasets_py.mcp_server.secrets_vault import SecretsVault  # type: ignore
        return SecretsVault
    except Exception:
        return None


def _vault_secret_name(gmail_user: str) -> str:
    cleaned = str(gmail_user or "").strip().lower()
    return f"{IPFS_VAULT_SECRET_PREFIX}:{cleaned}"


def read_password_from_keyring(gmail_user: str) -> str:
    keyring = _load_keyring()
    if keyring is None or not gmail_user:
        return ""
    try:
        return str(keyring.get_password(KEYRING_SERVICE, gmail_user) or "").strip()
    except Exception:
        return ""


def read_password_from_ipfs_secrets_vault(gmail_user: str) -> str:
    SecretsVault = _load_ipfs_secrets_vault()
    if SecretsVault is None or not gmail_user:
        return ""
    try:
        vault = SecretsVault()
        return str(vault.get(_vault_secret_name(gmail_user)) or "").strip()
    except Exception:
        return ""


def save_password_to_keyring(gmail_user: str, gmail_app_password: str, parser: argparse.ArgumentParser) -> None:
    keyring = _load_keyring()
    if keyring is None:
        parser.error("keyring support is not available. Install the 'keyring' package to use --save-to-keyring.")
    try:
        keyring.set_password(KEYRING_SERVICE, gmail_user, gmail_app_password)
    except Exception as exc:
        parser.error(f"failed to save Gmail app password to keyring: {exc}")


def save_password_to_ipfs_secrets_vault(
    gmail_user: str,
    gmail_app_password: str,
    parser: argparse.ArgumentParser,
) -> None:
    SecretsVault = _load_ipfs_secrets_vault()
    if SecretsVault is None:
        parser.error(
            "ipfs_datasets_py SecretsVault support is not available. Install py-ucan and ensure "
            "ipfs_datasets_py is importable to use --save-to-ipfs-secrets-vault."
        )
    try:
        vault = SecretsVault()
        vault.set(_vault_secret_name(gmail_user), gmail_app_password)
    except Exception as exc:
        parser.error(f"failed to save Gmail app password to the ipfs_datasets_py secrets vault: {exc}")


def resolve_gmail_credentials(
    *,
    gmail_user: str,
    gmail_app_password: str,
    prompt_for_credentials: bool,
    use_keyring: bool,
    save_to_keyring_flag: bool,
    use_ipfs_secrets_vault: bool,
    save_to_ipfs_secrets_vault_flag: bool,
    parser: argparse.ArgumentParser,
) -> tuple[str, str]:
    resolved_user = str(gmail_user or "").strip()
    resolved_password = str(gmail_app_password or "").strip()
    can_prompt = bool(getattr(sys.stdin, "isatty", lambda: False)() and getattr(sys.stderr, "isatty", lambda: False)())

    if use_ipfs_secrets_vault and resolved_user and not resolved_password:
        resolved_password = read_password_from_ipfs_secrets_vault(resolved_user)
    if use_keyring and resolved_user and not resolved_password:
        resolved_password = read_password_from_keyring(resolved_user)

    if prompt_for_credentials or ((not resolved_user or not resolved_password) and can_prompt):
        if not resolved_user:
            resolved_user = input("Gmail address: ").strip()
        if use_ipfs_secrets_vault and resolved_user and not resolved_password:
            resolved_password = read_password_from_ipfs_secrets_vault(resolved_user)
        if use_keyring and resolved_user and not resolved_password:
            resolved_password = read_password_from_keyring(resolved_user)
        if not resolved_password:
            resolved_password = getpass.getpass("Gmail app password: ").strip()

    if not resolved_user or not resolved_password:
        parser.error(
            "Gmail credentials are required. Use --prompt-for-credentials, "
            "--use-keyring, --use-ipfs-secrets-vault, set GMAIL_USER/GMAIL_APP_PASSWORD, "
            "or pass --gmail-user and --gmail-app-password."
        )

    if save_to_ipfs_secrets_vault_flag:
        save_password_to_ipfs_secrets_vault(resolved_user, resolved_password, parser)
    if save_to_keyring_flag:
        save_password_to_keyring(resolved_user, resolved_password, parser)
    return resolved_user, resolved_password


__all__ = [
    "IPFS_VAULT_SECRET_PREFIX",
    "KEYRING_SERVICE",
    "read_password_from_ipfs_secrets_vault",
    "read_password_from_keyring",
    "resolve_gmail_credentials",
    "save_password_to_ipfs_secrets_vault",
    "save_password_to_keyring",
]
