from __future__ import annotations

import argparse
import getpass
import sys

from integrations.ipfs_datasets.legal_data import legal_module

_email_auth = legal_module("email_auth")


KEYRING_SERVICE = _email_auth.KEYRING_SERVICE
IPFS_VAULT_SECRET_PREFIX = _email_auth.IPFS_VAULT_SECRET_PREFIX

read_password_from_keyring = _email_auth.read_password_from_keyring
read_password_from_ipfs_secrets_vault = _email_auth.read_password_from_ipfs_secrets_vault
save_password_to_keyring = _email_auth.save_password_to_keyring
save_password_to_ipfs_secrets_vault = _email_auth.save_password_to_ipfs_secrets_vault


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
    original_read_keyring = _email_auth.read_password_from_keyring
    original_read_vault = _email_auth.read_password_from_ipfs_secrets_vault
    original_save_keyring = _email_auth.save_password_to_keyring
    original_save_vault = _email_auth.save_password_to_ipfs_secrets_vault
    original_sys = _email_auth.sys
    original_getpass = _email_auth.getpass
    _email_auth.read_password_from_keyring = read_password_from_keyring
    _email_auth.read_password_from_ipfs_secrets_vault = read_password_from_ipfs_secrets_vault
    _email_auth.save_password_to_keyring = save_password_to_keyring
    _email_auth.save_password_to_ipfs_secrets_vault = save_password_to_ipfs_secrets_vault
    _email_auth.sys = sys
    _email_auth.getpass = getpass
    try:
        return _email_auth.resolve_gmail_credentials(
            gmail_user=gmail_user,
            gmail_app_password=gmail_app_password,
            prompt_for_credentials=prompt_for_credentials,
            use_keyring=use_keyring,
            save_to_keyring_flag=save_to_keyring_flag,
            use_ipfs_secrets_vault=use_ipfs_secrets_vault,
            save_to_ipfs_secrets_vault_flag=save_to_ipfs_secrets_vault_flag,
            parser=parser,
        )
    finally:
        _email_auth.read_password_from_keyring = original_read_keyring
        _email_auth.read_password_from_ipfs_secrets_vault = original_read_vault
        _email_auth.save_password_to_keyring = original_save_keyring
        _email_auth.save_password_to_ipfs_secrets_vault = original_save_vault
        _email_auth.sys = original_sys
        _email_auth.getpass = original_getpass


__all__ = [
    "IPFS_VAULT_SECRET_PREFIX",
    "KEYRING_SERVICE",
    "read_password_from_ipfs_secrets_vault",
    "read_password_from_keyring",
    "resolve_gmail_credentials",
    "save_password_to_ipfs_secrets_vault",
    "save_password_to_keyring",
]
