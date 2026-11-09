"""Complaint CLI, including non-echo private-key unlock and recovery commands.

Passphrases are read with ``getpass`` inside the process. Commands reject
``--passphrase``, ``--password``, and similar process arguments. Printed
payloads are task receipts and never include key bytes.
"""

from __future__ import annotations

import json
import sys
from functools import wraps

from applications.complaint_cli import app, main as _workspace_main

__all__ = [
    "app",
    "main",
    "keys_init",
    "keys_lock",
    "keys_recover_export",
    "keys_recover_import",
    "keys_revoke_retained",
    "keys_rotate_data",
    "keys_rotate_wrapping",
    "keys_status",
    "keys_unlock",
    "workspace_export",
    "workspace_import",
]


def _reject_secret_argv() -> None:
    for token in sys.argv:
        if not token.startswith("-"):
            continue
        name = token.split("=", 1)[0].lower()
        if name in {"--passphrase", "--password", "--master-key", "--data-key", "--wrapping-key"}:
            raise SystemExit("Passphrases and key bytes must not be passed as process arguments.")


def _emit(payload: dict) -> None:
    from integrations.private_storage import task_key_receipt

    sys.stdout.write(json.dumps(task_key_receipt(payload), sort_keys=True) + "\n")


def _key_command_boundary(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            # CLI exception renderers may include callback locals. Key commands
            # hold passphrases in memory, so expose only a constant receipt.
            _emit({
                "status": "key_operation_failed",
                "code": "key_operation_failed",
                "message": "The private key operation failed. Check the selected store and unlock method, then retry.",
                "actions": ["retry", "keyring_unlock", "recovery_import"],
                "awaiting_user": True,
                "worker_may_continue": True,
                "worker_state": "ready_for_independent_tasks",
                "raw_key_persisted": False,
                "cloud_processing_enabled": False,
                "unlock_is_remote_consent": False,
            })
            raise SystemExit(2) from None

    return invoke


def _prompt(label: str) -> str:
    from integrations.private_storage import PrivateKeyMaterialError, read_unlock_passphrase

    try:
        return read_unlock_passphrase(label)
    except PrivateKeyMaterialError:
        _emit({
            "status": "unlock_needed",
            "code": "passphrase_prompt_failed",
            "message": "No passphrase was accepted. Retry in a private terminal or use keyring protection or recovery import.",
            "actions": ["retry_in_terminal", "keyring_unlock", "recovery_import"],
            "awaiting_user": True,
            "worker_may_continue": True,
            "worker_state": "ready_for_independent_tasks",
            "unlocked": False,
            "raw_key_persisted": False,
            "cloud_processing_enabled": False,
            "unlock_is_remote_consent": False,
        })
        raise SystemExit(2) from None


@_key_command_boundary
def keys_status(store_dir: str = "") -> None:
    """Print whether the wrapped key store is absent, locked, or unlocked."""

    _reject_secret_argv()
    from integrations.private_storage import UserOwnedKeySession

    if not store_dir:
        raise SystemExit("store directory is required")
    _emit(UserOwnedKeySession(store_dir).public_state())


@_key_command_boundary
def keys_init(store_dir: str = "", protection: str = "passphrase") -> None:
    """Create a passphrase- or keyring-wrapped store. Passphrase comes from getpass."""

    _reject_secret_argv()
    from integrations.private_storage import PrivateKeyLockedError, UserOwnedKeySession

    if not store_dir:
        raise SystemExit("store directory is required")
    if protection not in {"passphrase", "keyring"}:
        raise SystemExit("protection must be passphrase or keyring")
    session = UserOwnedKeySession(store_dir)
    passphrase = _prompt("New private key passphrase") if protection == "passphrase" else None
    try:
        state = session.create(protection=protection, passphrase=passphrase)
    except PrivateKeyLockedError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    _emit(state)


@_key_command_boundary
def keys_unlock(store_dir: str = "", protection: str = "") -> None:
    """Unlock an existing store. A locked keyring does not fall back to a raw key."""

    _reject_secret_argv()
    from integrations.private_storage import (
        PrivateArtifactIntegrityError,
        PrivateKeyLockedError,
        UserOwnedKeySession,
    )

    if not store_dir:
        raise SystemExit("store directory is required")
    session = UserOwnedKeySession(store_dir)
    state = session.public_state()
    chosen = protection or str(state.get("protection") or "")
    try:
        if chosen == "passphrase":
            state = session.unlock_passphrase(_prompt("Private key passphrase"))
        elif chosen == "keyring":
            state = session.unlock_keyring()
        else:
            raise PrivateKeyLockedError(
                "Choose passphrase unlock or recovery import. No key was invented.",
                actions=("passphrase_unlock", "recovery_import"),
            )
    except PrivateKeyLockedError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    except PrivateArtifactIntegrityError:
        _emit(session.public_state() | {
            "status": "unlock_needed",
            "code": "authentication_failed",
            "message": "The passphrase or wrapped key did not authenticate. Encrypted state was not overwritten.",
            "awaiting_user": True,
        })
        raise SystemExit(2) from None
    _emit(state)


@_key_command_boundary
def keys_lock(store_dir: str = "") -> None:
    """Drop unwrapped keys from the session."""

    _reject_secret_argv()
    from integrations.private_storage import UserOwnedKeySession

    if not store_dir:
        raise SystemExit("store directory is required")
    _emit(UserOwnedKeySession(store_dir).lock())


@_key_command_boundary
def keys_recover_export(store_dir: str = "", tenant_id: str = "", case_id: str = "", destination: str = "") -> None:
    """Write a deliberate recovery export. This is not an automatic case backup."""

    _reject_secret_argv()
    from integrations.private_storage import PrivateKeyLockedError, UserOwnedKeySession

    if not store_dir or not tenant_id or not case_id or not destination:
        raise SystemExit("store, tenant, case, and destination are required")
    session = UserOwnedKeySession(store_dir)
    if not session.unlocked:
        try:
            if session.public_state().get("protection") == "keyring":
                session.unlock_keyring()
            else:
                session.unlock_passphrase(_prompt("Private key passphrase"))
        except PrivateKeyLockedError as exc:
            _emit(exc.public_state())
            raise SystemExit(2) from None
    phrase = _prompt("Recovery export passphrase")
    try:
        exported = session.export_recovery(tenant_id, case_id, phrase, destination)
    except PrivateKeyLockedError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    _emit({
        **session.public_state(),
        "deliberate_export": True,
        "automatic_backup": False,
        "message": "Wrote a deliberate recovery export. It is not an automatic backup.",
        "case_count": session.public_state()["case_count"],
        "data_key_id_written": bool(exported.get("data_key_id")),
    })


@_key_command_boundary
def keys_recover_import(
    store_dir: str = "",
    tenant_id: str = "",
    case_id: str = "",
    source: str = "",
) -> None:
    """Import a deliberate recovery file. A locked store is not overwritten."""

    _reject_secret_argv()
    from pathlib import Path

    from integrations.private_storage import (
        PrivateArtifactBindingError,
        PrivateArtifactIntegrityError,
        PrivateKeyLockedError,
        UserOwnedKeySession,
    )

    if not store_dir or not tenant_id or not case_id or not source:
        raise SystemExit("store, tenant, case, and source are required")
    session = UserOwnedKeySession(store_dir)
    if session.path.exists() and not session.unlocked:
        state = session.public_state()
        state["message"] = "Locked key store was not overwritten. Unlock it or import into a new directory."
        _emit(state)
        raise SystemExit(2)
    recovery_passphrase = _prompt("Recovery import passphrase")
    store_passphrase = None if session.path.exists() else _prompt("New store passphrase")
    try:
        state = session.import_recovery(
            Path(source).read_bytes(),
            tenant_id=tenant_id,
            case_id=case_id,
            recovery_passphrase=recovery_passphrase,
            store_passphrase=store_passphrase,
        )
    except PrivateKeyLockedError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    except PrivateArtifactBindingError:
        _emit(session.public_state() | {
            "code": "foreign_case",
            "message": "Recovery material is for a different case and was not imported.",
            "awaiting_user": True,
            "status": "unlock_needed",
        })
        raise SystemExit(2) from None
    except PrivateArtifactIntegrityError:
        _emit(session.public_state() | {
            "code": "authentication_failed",
            "message": "Recovery material did not authenticate and was not imported.",
            "awaiting_user": True,
            "status": "unlock_needed",
        })
        raise SystemExit(2) from None
    _emit(state)


def _unlock_session(session, protection: str = ""):
    from integrations.private_storage import PrivateArtifactIntegrityError, PrivateKeyLockedError

    if session.unlocked:
        return session
    chosen = protection or str(session.public_state().get("protection") or "")
    try:
        if chosen == "keyring":
            session.unlock_keyring()
        else:
            session.unlock_passphrase(_prompt("Private key passphrase"))
    except PrivateKeyLockedError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    except PrivateArtifactIntegrityError:
        _emit(session.public_state() | {
            "status": "unlock_needed",
            "code": "authentication_failed",
            "message": "The passphrase or wrapped key did not authenticate. Encrypted state was not overwritten.",
            "awaiting_user": True,
            "keys_reconstructed": False,
            "data_reset": False,
        })
        raise SystemExit(2) from None
    return session


@_key_command_boundary
def workspace_export(
    store_dir: str = "",
    tenant_id: str = "",
    case_id: str = "",
    principal_id: str = "",
    repository: str = "",
    export_dir: str = "",
    recovery_destination: str = "",
) -> None:
    """Export a ciphertext archive and a separate recovery file."""

    _reject_secret_argv()
    from integrations.private_storage import PrivatePortabilityError, UserOwnedKeySession, export_encrypted_workspace

    if not all((store_dir, tenant_id, case_id, principal_id, repository, export_dir, recovery_destination)):
        raise SystemExit("store, tenant, case, principal, repository, export directory, and recovery destination are required")
    session = _unlock_session(UserOwnedKeySession(store_dir))
    try:
        receipt = export_encrypted_workspace(
            repository,
            export_dir,
            recovery_destination,
            session,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            recovery_passphrase=_prompt("Recovery export passphrase"),
        )
    except PrivatePortabilityError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    _emit(receipt)


@_key_command_boundary
def workspace_import(
    store_dir: str = "",
    tenant_id: str = "",
    case_id: str = "",
    principal_id: str = "",
    repository: str = "",
    export_dir: str = "",
    recovery_source: str = "",
) -> None:
    """Restore a ciphertext archive with a separate recovery file."""

    _reject_secret_argv()
    from integrations.private_storage import (
        PrivateKeyLockedError,
        PrivatePortabilityError,
        import_encrypted_workspace,
    )

    if not all((store_dir, tenant_id, case_id, principal_id, repository, export_dir, recovery_source)):
        raise SystemExit("store, tenant, case, principal, repository, export directory, and recovery source are required")
    recovery_passphrase = _prompt("Recovery import passphrase")
    store_passphrase = _prompt("New store passphrase")
    try:
        restored = import_encrypted_workspace(
            repository,
            export_dir,
            recovery_source,
            store_dir,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            recovery_passphrase=recovery_passphrase,
            store_passphrase=store_passphrase,
        )
    except PrivatePortabilityError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    except PrivateKeyLockedError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    _emit({
        "status": "imported",
        "code": "imported",
        "operation": "import",
        "revision": restored.get("revision"),
        "manifest_version": restored.get("manifest_version"),
        "imported": True,
        "keys_reconstructed": False,
        "data_reset": False,
        "unwrapped_master_included": False,
        "recovery_separated": True,
        "message": restored.get("message"),
        "actions": ["unlock", "lock"],
        "awaiting_user": False,
        "worker_may_continue": True,
        "worker_state": "ready_for_independent_tasks",
        "raw_key_persisted": False,
        "cloud_processing_enabled": False,
        "unlock_is_remote_consent": False,
        "deliberate_export": True,
        "automatic_backup": False,
    })


@_key_command_boundary
def keys_rotate_wrapping(store_dir: str = "", policy: str = "retain") -> None:
    """Rewrap the master key. This does not reencrypt case ciphertext."""

    _reject_secret_argv()
    from integrations.private_storage import PrivatePortabilityError, PrivateRevisionInterrupted, UserOwnedKeySession

    if not store_dir:
        raise SystemExit("store directory is required")
    session = _unlock_session(UserOwnedKeySession(store_dir))
    try:
        state = session.rotate_wrapping_key(_prompt("New wrapping passphrase"), policy=policy)
    except PrivateRevisionInterrupted as exc:
        _emit({
            "status": "interrupted",
            "code": "interrupted",
            "operation": "rewrap",
            "reencrypt": False,
            "rotation_phase": exc.boundary,
            "message": "Wrapping rotation stopped at a crash boundary. The previous generation is still readable.",
            "data_reset": False,
            "keys_reconstructed": False,
            "revoked": False,
            "awaiting_user": False,
            "worker_may_continue": True,
            "worker_state": "ready_for_independent_tasks",
            "raw_key_persisted": False,
            "cloud_processing_enabled": False,
            "unlock_is_remote_consent": False,
        })
        raise SystemExit(2) from None
    except PrivatePortabilityError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    _emit(state)


@_key_command_boundary
def keys_rotate_data(
    store_dir: str = "",
    tenant_id: str = "",
    case_id: str = "",
    principal_id: str = "",
    repository: str = "",
    policy: str = "retain",
) -> None:
    """Reencrypt the case under a new data key and retain the previous generation."""

    _reject_secret_argv()
    from integrations.private_storage import PrivatePortabilityError, PrivateRevisionInterrupted, UserOwnedKeySession

    if not all((store_dir, tenant_id, case_id, principal_id, repository)):
        raise SystemExit("store, tenant, case, principal, and repository are required")
    session = _unlock_session(UserOwnedKeySession(store_dir))
    try:
        state = session.rotate_data_key(tenant_id, case_id, repository, principal_id, policy=policy)
    except PrivateRevisionInterrupted as exc:
        _emit({
            "status": "interrupted",
            "code": "interrupted",
            "operation": "reencrypt",
            "reencrypt": True,
            "rotation_phase": exc.boundary,
            "message": "Data-key rotation stopped at a crash boundary. A valid generation is still readable.",
            "data_reset": False,
            "keys_reconstructed": False,
            "revoked": False,
            "awaiting_user": False,
            "worker_may_continue": True,
            "worker_state": "ready_for_independent_tasks",
            "raw_key_persisted": False,
            "cloud_processing_enabled": False,
            "unlock_is_remote_consent": False,
        })
        raise SystemExit(2) from None
    except PrivatePortabilityError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    _emit(state)


@_key_command_boundary
def keys_revoke_retained(
    store_dir: str = "",
    tenant_id: str = "",
    case_id: str = "",
    repository: str = "",
    export_dir: str = "",
    recovery_path: str = "",
    verified_backup_migration: str = "",
) -> None:
    """Revoke retained keys only when the caller proves a migrated backup."""

    _reject_secret_argv()
    from integrations.private_storage import PrivatePortabilityError, UserOwnedKeySession

    if not all((store_dir, tenant_id, case_id, repository, export_dir, recovery_path)):
        raise SystemExit("store, tenant, case, repository, export directory, and recovery path are required")
    verified = verified_backup_migration == "yes"
    session = _unlock_session(UserOwnedKeySession(store_dir))
    try:
        state = session.revoke_retained_keys(
            tenant_id,
            case_id,
            repository,
            policy="revoke_after_verified_migration",
            verified_backup_migration=verified,
            export_dir=export_dir,
            recovery_path=recovery_path,
        )
    except PrivatePortabilityError as exc:
        _emit(exc.public_state())
        raise SystemExit(2) from None
    _emit(state)


def _register_key_commands() -> None:
    registrar = getattr(app, "command", None)
    if registrar is None:
        return
    registrar("keys-status")(keys_status)
    registrar("keys-init")(keys_init)
    registrar("keys-unlock")(keys_unlock)
    registrar("keys-lock")(keys_lock)
    registrar("keys-recover-export")(keys_recover_export)
    registrar("keys-recover-import")(keys_recover_import)
    registrar("keys-rotate-wrapping")(keys_rotate_wrapping)
    registrar("keys-rotate-data")(keys_rotate_data)
    registrar("keys-revoke-retained")(keys_revoke_retained)
    registrar("workspace-export")(workspace_export)
    registrar("workspace-import")(workspace_import)


_register_key_commands()


def main() -> None:
    key_commands = {
        "keys-status", "keys-init", "keys-unlock", "keys-lock",
        "keys-recover-export", "keys-recover-import",
        "keys-rotate-wrapping", "keys-rotate-data", "keys-revoke-retained",
        "workspace-export", "workspace-import",
    }
    if any(token in key_commands | {"chat"} for token in sys.argv[1:]):
        # Refuse before argument-parser diagnostics can repeat an argv secret.
        _reject_secret_argv()
    _workspace_main()


if __name__ == "__main__":
    main()
