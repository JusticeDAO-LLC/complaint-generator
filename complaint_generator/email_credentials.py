from __future__ import annotations

import argparse
import getpass
import sys


KEYRING_SERVICE = "complaint-generator.gmail"


def _load_keyring():
    try:
        import keyring  # type: ignore
    except Exception:
        return None
    return keyring


def read_password_from_keyring(gmail_user: str) -> str:
    keyring = _load_keyring()
    if keyring is None or not gmail_user:
        return ""
    try:
        return str(keyring.get_password(KEYRING_SERVICE, gmail_user) or "").strip()
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


def resolve_gmail_credentials(
    *,
    gmail_user: str,
    gmail_app_password: str,
    prompt_for_credentials: bool,
    use_keyring: bool,
    save_to_keyring_flag: bool,
    parser: argparse.ArgumentParser,
) -> tuple[str, str]:
    resolved_user = str(gmail_user or "").strip()
    resolved_password = str(gmail_app_password or "").strip()
    can_prompt = bool(getattr(sys.stdin, "isatty", lambda: False)() and getattr(sys.stderr, "isatty", lambda: False)())

    if use_keyring and resolved_user and not resolved_password:
        resolved_password = read_password_from_keyring(resolved_user)

    if prompt_for_credentials or ((not resolved_user or not resolved_password) and can_prompt):
        if not resolved_user:
            resolved_user = input("Gmail address: ").strip()
        if use_keyring and resolved_user and not resolved_password:
            resolved_password = read_password_from_keyring(resolved_user)
        if not resolved_password:
            resolved_password = getpass.getpass("Gmail app password: ").strip()

    if not resolved_user or not resolved_password:
        parser.error(
            "Gmail credentials are required. Use --prompt-for-credentials, "
            "--use-keyring, set GMAIL_USER/GMAIL_APP_PASSWORD, or pass --gmail-user and --gmail-app-password."
        )

    if save_to_keyring_flag:
        save_password_to_keyring(resolved_user, resolved_password, parser)
    return resolved_user, resolved_password


__all__ = [
    "KEYRING_SERVICE",
    "read_password_from_keyring",
    "resolve_gmail_credentials",
    "save_password_to_keyring",
]
