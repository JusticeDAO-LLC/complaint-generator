"""User-owned private key unlock, wrapping, and recovery.

These tests use temporary stores and injected keyrings. They do not touch a
system keyring and they do not skip when that keyring is missing.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import stat
import sys
import traceback
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    PrivateKeyLockedError,
    PrivateKeyMaterialError,
    UserOwnedKeySession,
    assert_store_isolated_from_exports,
    open_private_artifact,
    read_unlock_passphrase,
    seal_private_artifact,
    task_key_receipt,
)

PASSPHRASE = "sentinel-passphrase-do-not-persist"
RECOVERY = "sentinel-recovery-do-not-persist"
TENANT = "tenant-a"
CASE = "case-a"
OTHER_CASE = "case-b"


class MemoryKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, account: str, password: str) -> None:
        self.values[(service, account)] = password

    def get_password(self, service: str, account: str) -> str:
        return self.values[(service, account)]


class LockedKeyring:
    def set_password(self, service: str, account: str, password: str) -> None:
        raise RuntimeError("keyring locked")

    def get_password(self, service: str, account: str) -> str | None:
        raise RuntimeError("keyring locked")


def _binding(case: str = CASE) -> PrivateArtifactBinding:
    return PrivateArtifactBinding(
        tenant_id=TENANT,
        case_id=case,
        artifact_kind="draft",
        revision="1",
        principal_id=TENANT,
    )


def _assert_owner_only(directory: Path) -> None:
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    store = directory / "keystore.json"
    assert store.is_file()
    assert stat.S_IMODE(store.stat().st_mode) == 0o600
    assert list(directory.glob("*.key")) == []


def _disk_text(directory: Path) -> str:
    chunks: list[str] = []
    for path in directory.rglob("*"):
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="surrogateescape"))
    return "\n".join(chunks)


def test_passphrase_wrap_restart_and_permissions(tmp_path: Path) -> None:
    store = tmp_path / "keys"
    created = UserOwnedKeySession(store)
    state = created.create(protection="passphrase", passphrase=PASSPHRASE)
    assert state["unlocked"] is True
    assert state["raw_key_persisted"] is False
    assert state["unlock_is_remote_consent"] is False
    key_id = created.ensure_data_key(TENANT, CASE)
    provider = created.provider()
    resolved_id, resolved_key = provider.resolve(_binding())
    assert resolved_id == key_id
    envelope = seal_private_artifact(b"private-bytes", binding=_binding(), key=resolved_key, key_id=resolved_id)
    created.lock()
    assert created.unlocked is False
    with pytest.raises(PrivateKeyLockedError):
        created.provider()

    restarted = UserOwnedKeySession(store)
    assert restarted.unlocked is False
    assert restarted.public_state()["status"] == "unlock_needed"
    assert "passphrase_unlock" in restarted.public_state()["actions"]
    with pytest.raises(PrivateArtifactIntegrityError):
        restarted.unlock_passphrase("wrong-passphrase")
    assert restarted.unlocked is False
    restarted.unlock_passphrase(PASSPHRASE)
    again_id, again_key = restarted.provider().resolve(_binding())
    assert again_id == key_id
    assert open_private_artifact(envelope, binding=_binding(), key=again_key, expected_key_id=again_id) == b"private-bytes"
    _assert_owner_only(store)
    blob = _disk_text(store)
    assert PASSPHRASE not in blob
    assert resolved_key.hex() not in blob
    assert b"private-bytes".hex() not in blob
    receipt = json.dumps(task_key_receipt(restarted.public_state()))
    assert PASSPHRASE not in receipt
    assert "master_key" not in receipt


def test_tampered_wrapped_key_and_locked_store_is_not_overwritten(tmp_path: Path) -> None:
    store = tmp_path / "keys"
    session = UserOwnedKeySession(store)
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    session.ensure_data_key(TENANT, CASE)
    session.lock()
    before = (store / "keystore.json").read_bytes()
    with pytest.raises(PrivateKeyLockedError):
        session.ensure_data_key(TENANT, OTHER_CASE)
    assert (store / "keystore.json").read_bytes() == before

    document = json.loads(before.decode("utf-8"))
    ciphertext = document["wrapped_master"]["ciphertext"]
    flipped = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    document["wrapped_master"]["ciphertext"] = flipped
    (store / "keystore.json").write_bytes(json.dumps(document).encode("utf-8"))
    os.chmod(store / "keystore.json", 0o600)
    tampered = UserOwnedKeySession(store)
    with pytest.raises(PrivateArtifactIntegrityError):
        tampered.unlock_passphrase(PASSPHRASE)
    assert tampered.unlocked is False


def test_keyring_lock_does_not_downgrade_to_raw_file(tmp_path: Path) -> None:
    store = tmp_path / "keys"
    refused = UserOwnedKeySession(store)
    with pytest.raises(PrivateKeyLockedError) as locked:
        refused.create(protection="keyring", keyring=LockedKeyring())
    assert locked.value.public_state()["code"] == "keyring_unavailable"
    assert "create_with_passphrase" in locked.value.public_state()["actions"]
    assert not store.exists() or list(store.glob("*.key")) == []
    assert list(tmp_path.rglob("*.key")) == []

    ring = MemoryKeyring()
    created = UserOwnedKeySession(store)
    created.create(protection="keyring", keyring=ring)
    created.ensure_data_key(TENANT, CASE)
    created.lock()
    blob = _disk_text(store)
    for secret in ring.values.values():
        assert secret not in blob
    restarted = UserOwnedKeySession(store)
    with pytest.raises(PrivateKeyLockedError) as unavailable:
        restarted.unlock_keyring(LockedKeyring())
    state = unavailable.value.public_state()
    assert state["status"] == "unlock_needed"
    assert state["protection_downgrade"] is False
    assert "recovery_import" in state["actions"]
    assert list(store.glob("*.key")) == []
    restarted.unlock_keyring(ring)
    assert restarted.provider().resolve(_binding())[0].startswith("d-")


def test_recovery_roundtrip_and_foreign_case_denial(tmp_path: Path) -> None:
    store = tmp_path / "keys"
    session = UserOwnedKeySession(store)
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    destination = tmp_path / "recovery" / "case-recovery.json"
    exported = session.export_recovery(TENANT, CASE, RECOVERY, destination)
    assert exported["deliberate_export"] is True
    assert exported["automatic_backup"] is False
    assert RECOVERY not in destination.read_text(encoding="utf-8")
    with pytest.raises(Exception):
        session.export_recovery(TENANT, CASE, RECOVERY, tmp_path / "backups" / "case.json")

    session.lock()
    before = (store / "keystore.json").read_bytes()
    with pytest.raises(PrivateKeyLockedError):
        session.import_recovery(
            exported["bytes"],
            tenant_id=TENANT,
            case_id=CASE,
            recovery_passphrase=RECOVERY,
        )
    assert (store / "keystore.json").read_bytes() == before

    fresh = UserOwnedKeySession(tmp_path / "imported")
    with pytest.raises(PrivateArtifactBindingError):
        fresh.import_recovery(
            exported["bytes"],
            tenant_id=TENANT,
            case_id=OTHER_CASE,
            recovery_passphrase=RECOVERY,
            store_passphrase=PASSPHRASE,
        )
    assert not (tmp_path / "imported").exists()
    with pytest.raises(PrivateArtifactIntegrityError):
        fresh.import_recovery(
            exported["bytes"],
            tenant_id=TENANT,
            case_id=CASE,
            recovery_passphrase="not-the-recovery-passphrase",
            store_passphrase=PASSPHRASE,
        )
    imported = fresh.import_recovery(
        exported["bytes"],
        tenant_id=TENANT,
        case_id=CASE,
        recovery_passphrase=RECOVERY,
        store_passphrase="another-store-passphrase",
    )
    assert imported["unlocked"] is True
    assert imported["automatic_backup"] is False
    source = UserOwnedKeySession(store)
    source.unlock_passphrase(PASSPHRASE)
    source_id, source_key = source.provider().resolve(_binding())
    imported_session = UserOwnedKeySession(tmp_path / "imported")
    imported_session.unlock_passphrase("another-store-passphrase")
    imported_id, imported_key = imported_session.provider().resolve(_binding())
    assert imported_id == source_id
    assert imported_key == source_key


def test_passphrase_prompt_rejects_argv_and_receipts(tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["complaint", "--passphrase", PASSPHRASE])
    with pytest.raises(Exception):
        read_unlock_passphrase(getpass_fn=lambda prompt: PASSPHRASE)
    monkeypatch.setattr(sys, "argv", ["complaint", "keys-unlock", "--store-dir", str(tmp_path)])
    captured: list[str] = []

    def _capture(prompt: str) -> str:
        captured.append(prompt)
        assert PASSPHRASE not in prompt
        return PASSPHRASE

    assert read_unlock_passphrase(getpass_fn=_capture) == PASSPHRASE
    assert captured and captured[0].endswith(": ")
    caplog.set_level("DEBUG")
    session = UserOwnedKeySession(tmp_path / "keys")
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    assert PASSPHRASE not in caplog.text
    assert "sentinel-passphrase" not in json.dumps(task_key_receipt(session.public_state()))


def test_workspace_unlock_is_not_remote_consent_and_supervisor_can_continue(tmp_path: Path) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService

    service = ComplaintWorkspaceService(tmp_path / "workspace")
    created = service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created["unlocked"] is True
    assert created["cloud_processing_enabled"] is False
    assert created["unlock_is_remote_consent"] is False
    service.ensure_private_case_key("user-a", "user-a")
    before = service.get_privacy_policy("user-a")
    after = service.get_privacy_policy("user-a")
    assert after["policy"] == before["policy"]
    assert after["policy"].get("cloud_processing_enabled") in {False, None} or after["load"].get("cloud_processing_enabled") is False

    locked = service.lock_private_keys()
    assert locked["unlocked"] is False
    continued = service.continue_without_private_keys()
    assert continued["status"] == "awaiting_user"
    assert continued["worker_state"] == "ready_for_independent_tasks"
    assert continued["invented_key"] is False
    assert continued["privacy_bypassed"] is False
    with pytest.raises(PrivateKeyLockedError):
        service.private_key_provider()

    restarted = ComplaintWorkspaceService(tmp_path / "workspace")
    assert restarted.private_key_status()["status"] == "unlock_needed"
    opened = restarted.unlock_private_keys(passphrase=PASSPHRASE)
    assert opened["unlocked"] is True
    assert opened["unlock_is_remote_consent"] is False
    assert restarted.get_privacy_policy("user-a")["policy"] == before["policy"]
    ensured = restarted.ensure_private_case_key(TENANT, CASE)
    assert ensured["data_key_id"].startswith("d-")
    assert PASSPHRASE not in json.dumps({key: value for key, value in ensured.items() if key != "data_key_id"})
    provider = restarted.private_key_provider()
    assert provider.resolve(_binding())[0] == ensured["data_key_id"]


def test_export_directory_cannot_hold_the_key_store(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    with pytest.raises(Exception):
        assert_store_isolated_from_exports(exports, exports)
    with pytest.raises(Exception):
        assert_store_isolated_from_exports(exports / "nested", exports)
    hostname = Path("/etc/hostname")
    if hostname.exists():
        assert hostname.read_text(encoding="utf-8").strip() not in PASSPHRASE


@pytest.fixture
def private_key_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Resolve the real lazy CLI service inside an explicit fixture workspace."""
    import applications
    import complaint_generator
    import applications.complaint_workspace as workspace

    missing = object()
    names = ("applications.complaint_cli", "complaint_generator.cli")
    previous_modules = {name: sys.modules.get(name, missing) for name in names}
    parents = ((applications, "complaint_cli"), (complaint_generator, "cli"))
    previous_attributes = [(package, name, getattr(package, name, missing)) for package, name in parents]
    with monkeypatch.context() as isolated:
        private_directory = tmp_path / "isolated-cli-workspace"
        isolated.setattr(workspace, "_SESSION_DIR", private_directory)
        isolated.setenv("COMPLAINT_WORKSPACE_SESSION_DIR", str(private_directory))
        for name in names:
            sys.modules.pop(name, None)
        for package, name in parents:
            if hasattr(package, name):
                delattr(package, name)
        try:
            cli = importlib.import_module("complaint_generator.cli")
            implementation = importlib.import_module("applications.complaint_cli")
            assert implementation.session_dir_from_environment() == private_directory
            # The public handler owns the concrete workspace behind the lazy
            # proxy. Keep the ownership/isolation assertions on that instance.
            concrete_service = implementation.service.request_handlers.workspace
            assert isinstance(concrete_service, implementation.TerminalComplaintWorkspaceService)
            assert concrete_service._session_dir == private_directory
            assert concrete_service.request_handlers.workspace is concrete_service
            isolated.setattr(implementation, "service", concrete_service)
            assert Path(cli.__file__).resolve() == Path(__file__).resolve().parents[1] / "complaint_generator/cli.py"
            yield cli
        finally:
            for name in names:
                sys.modules.pop(name, None)
            for name, value in previous_modules.items():
                if value is not missing:
                    sys.modules[name] = value
            for package, name, value in previous_attributes:
                if value is missing:
                    if hasattr(package, name):
                        delattr(package, name)
                else:
                    setattr(package, name, value)


def test_cli_rejects_passphrase_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], private_key_cli
) -> None:
    monkeypatch.setattr(sys, "argv", ["complaint", "keys-status", "--passphrase", PASSPHRASE])
    with pytest.raises(SystemExit):
        private_key_cli.keys_status(store_dir=str(tmp_path / "keys"))
    monkeypatch.setattr(sys, "argv", ["complaint", "keys-status", "--store-dir", str(tmp_path / "missing")])
    private_key_cli.keys_status(store_dir=str(tmp_path / "missing"))
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "absent"
    assert PASSPHRASE not in json.dumps(receipt)
    assert receipt["worker_may_continue"] is True


def test_real_cli_main_registers_and_dispatches_key_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], private_key_cli
) -> None:
    from typer.testing import CliRunner

    help_result = CliRunner().invoke(private_key_cli.app, ["--help"], color=False)
    assert help_result.exit_code == 0
    for name in (
        "keys-status", "keys-init", "keys-unlock", "keys-lock",
        "keys-recover-export", "keys-recover-import",
    ):
        assert name in help_result.stdout
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "complaint-workspace", "keys-status", "--store-dir", str(tmp_path / "absent-store"),
    ])
    with pytest.raises(SystemExit) as exited:
        private_key_cli.main()
    assert exited.value.code == 0
    captured = capsys.readouterr()
    state = json.loads(captured.out)
    assert state["status"] == "absent" and state["worker_may_continue"] is True
    assert "Traceback" not in captured.err
    assert not (tmp_path / "absent-store").exists()


def test_default_getpass_refuses_non_echo_fallback_before_reading_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import getpass

    class SentinelInput(io.StringIO):
        reads = 0

        def readline(self, *args, **kwargs):
            self.reads += 1
            return super().readline(*args, **kwargs)

    stdin = SentinelInput(PASSPHRASE + "\n")
    original_open = os.open

    def no_controlling_terminal(name, *args, **kwargs):
        if str(name) == "/dev/tty":
            raise OSError("synthetic no controlling terminal")
        return original_open(name, *args, **kwargs)

    monkeypatch.setattr(sys, "argv", ["complaint-workspace", "keys-unlock"])
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(getpass.os, "open", no_controlling_terminal)
    with pytest.raises(PrivateKeyMaterialError) as refused:
        read_unlock_passphrase()
    assert refused.value.reason == "passphrase_prompt_failed"
    assert stdin.reads == 0
    captured = capsys.readouterr()
    assert PASSPHRASE not in captured.out + captured.err


def test_default_secure_getpass_reader_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    import getpass

    prompts = []

    def secure_reader(prompt):
        prompts.append(prompt)
        return PASSPHRASE

    monkeypatch.setattr(sys, "argv", ["complaint-workspace", "keys-unlock"])
    monkeypatch.setattr(getpass, "getpass", secure_reader)
    assert read_unlock_passphrase() == PASSPHRASE
    assert len(prompts) == 1 and PASSPHRASE not in prompts[0]


def test_prompt_reader_failure_is_typed_and_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = "SYNTHETIC_PRIVATE_READER_FAILURE /private/key-location"

    def failed_reader(_prompt):
        raise OSError(marker)

    monkeypatch.setattr(sys, "argv", ["complaint-workspace", "keys-unlock"])
    with pytest.raises(PrivateKeyMaterialError) as failed:
        read_unlock_passphrase(getpass_fn=failed_reader)
    assert failed.value.reason == "passphrase_prompt_failed"
    assert marker not in str(failed.value)
    assert marker not in "".join(traceback.format_exception(failed.value))


def test_real_cli_prompt_failure_is_actionable_without_traceback_or_store_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], private_key_cli
) -> None:
    import getpass

    marker = "SYNTHETIC_PRIVATE_CLI_FAILURE"

    def failed_reader(_prompt):
        raise OSError(marker)

    monkeypatch.setattr(getpass, "getpass", failed_reader)
    target = tmp_path / "refused-key-store"
    monkeypatch.setattr(sys, "argv", [
        "complaint-workspace", "keys-init", "--store-dir", str(target),
    ])
    capsys.readouterr()
    with pytest.raises(SystemExit) as exited:
        private_key_cli.main()
    assert exited.value.code == 2
    captured = capsys.readouterr()
    state = json.loads(captured.out)
    assert state["status"] == "unlock_needed"
    assert state["code"] == "passphrase_prompt_failed"
    assert state["awaiting_user"] is True and state["worker_may_continue"] is True
    assert state["unlocked"] is False and state["raw_key_persisted"] is False
    assert marker not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err
    assert not target.exists()


@pytest.mark.parametrize("phrase", [None, "", True, 42, b"not-a-string"])
def test_create_refuses_invalid_passphrase_before_rng_or_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phrase,
) -> None:
    import integrations.private_storage as private

    calls = []

    def forbidden_rng(size):
        calls.append(size)
        raise AssertionError("invalid passphrase reached RNG")

    target = tmp_path / "invalid-phrase-store"
    session = UserOwnedKeySession(target)
    monkeypatch.setattr(private.os, "urandom", forbidden_rng)
    with pytest.raises(PrivateKeyMaterialError):
        session.create(protection="passphrase", passphrase=phrase)
    assert calls == []
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_create_missing_default_passphrase_refuses_before_rng_or_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.private_storage as private

    calls = []

    def forbidden_rng(size):
        calls.append(size)
        raise AssertionError("missing passphrase reached RNG")

    target = tmp_path / "missing-phrase-store"
    session = UserOwnedKeySession(target)
    monkeypatch.setattr(private.os, "urandom", forbidden_rng)
    with pytest.raises(PrivateKeyMaterialError):
        session.create(protection="passphrase")
    assert calls == []
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("phrase", [None, "", True, 42, b"not-a-string"])
def test_invalid_recovery_phrase_preserves_wrapped_store_and_case_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phrase,
) -> None:
    import integrations.private_storage as private

    session = UserOwnedKeySession(tmp_path / "existing-store")
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    session.ensure_data_key(TENANT, CASE)
    before = session.path.read_bytes()
    count = session.public_state()["case_count"]
    calls = []

    def forbidden_rng(size):
        calls.append(size)
        raise AssertionError("invalid recovery phrase reached RNG")

    monkeypatch.setattr(private.os, "urandom", forbidden_rng)
    destination = tmp_path / "recovery-not-created" / "export.json"
    with pytest.raises(PrivateKeyMaterialError):
        session.export_recovery(TENANT, OTHER_CASE, phrase, destination)
    assert calls == []
    assert session.path.read_bytes() == before
    assert session.public_state()["case_count"] == count == 1
    assert not destination.parent.exists()


# Append to tests/test_private_workspace_keys.py; uses its existing imports/constants.

@pytest.fixture
def owner_key_workspace(tmp_path: Path):
    from applications.complaint_workspace import ComplaintWorkspaceService

    service = ComplaintWorkspaceService(tmp_path / "owner-workspace")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(TENANT, CASE)
    service.ensure_private_case_key("foreign-owner", "foreign-case")
    return service


@pytest.mark.parametrize("operation", [
    "private_key_status", "initialize_private_keys", "unlock_private_keys",
    "lock_private_keys", "export_private_key_recovery",
    "import_private_key_recovery", "continue_without_private_keys",
])
def test_scoped_user_cannot_operate_shared_key_store(
    owner_key_workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    from applications.complaint_workspace import (
        WorkspaceAccess, WorkspaceAuthorizationDenied, workspace_access_scope,
    )

    service = owner_key_workspace
    store = service._private_key_directory() / "keystore.json"
    before = store.read_bytes()
    destination = tmp_path / "should-not-exist.recovery"
    arguments = {
        "initialize_private_keys": {"protection": "passphrase", "passphrase": PASSPHRASE},
        "unlock_private_keys": {"passphrase": PASSPHRASE},
        "export_private_key_recovery": {
            "tenant_id": "foreign-owner", "case_id": "foreign-case",
            "recovery_passphrase": RECOVERY, "destination": str(destination),
        },
        "import_private_key_recovery": {
            "tenant_id": TENANT, "case_id": CASE,
            "recovery_passphrase": RECOVERY, "payload": b"not-consulted",
        },
    }
    def no_key_lookup():
        pytest.fail("unauthorized operation consulted the shared key session")
    monkeypatch.setattr(service, "_private_key_session", no_key_lookup)
    with workspace_access_scope(WorkspaceAccess.authenticated(TENANT, case_id=CASE)):
        with pytest.raises(WorkspaceAuthorizationDenied):
            getattr(service, operation)(**arguments.get(operation, {}))
    assert store.read_bytes() == before
    assert not destination.exists()


def test_scoped_user_uses_own_case_without_foreign_count_or_consent_change(owner_key_workspace) -> None:
    from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope

    service = owner_key_workspace
    with workspace_access_scope(WorkspaceAccess.authenticated(TENANT, case_id=CASE)):
        before = service.get_privacy_policy(TENANT)
        receipt = service.ensure_private_case_key(TENANT, CASE)
        assert "case_count" not in receipt
        provider = service.private_key_provider()
        key_id, key = provider.resolve(_binding())
        assert key_id == receipt["data_key_id"]
        sealed = seal_private_artifact(b"owned-private-bytes", binding=_binding(), key=key, key_id=key_id)
        assert open_private_artifact(sealed, binding=_binding(), key=key, expected_key_id=key_id) == b"owned-private-bytes"
        assert service.get_privacy_policy(TENANT)["policy"] == before["policy"]


def test_retained_workspace_provider_rechecks_request_before_any_lookup(
    owner_key_workspace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from applications.complaint_workspace import (
        WorkspaceAccess, WorkspaceAuthorizationDenied, workspace_access_scope,
    )

    service = owner_key_workspace
    # A local handle must not retain the operator's access in a later request.
    provider = service.private_key_provider()
    store = service._private_key_directory() / "keystore.json"
    before = store.read_bytes()
    foreign_binding = PrivateArtifactBinding(
        tenant_id="foreign-owner", principal_id="foreign-owner", case_id="foreign-case",
        artifact_kind="draft", revision="1",
    )
    mismatched_principal = PrivateArtifactBinding(
        tenant_id=TENANT, principal_id="foreign-owner", case_id=CASE,
        artifact_kind="draft", revision="1",
    )
    def no_key_lookup():
        pytest.fail("foreign provider resolution consulted the shared key session")
    monkeypatch.setattr(service, "_private_key_session", no_key_lookup)
    with workspace_access_scope(WorkspaceAccess.authenticated(TENANT, case_id=CASE)):
        with pytest.raises(WorkspaceAuthorizationDenied):
            service.ensure_private_case_key("foreign-owner", "foreign-case")
        with pytest.raises(WorkspaceAuthorizationDenied):
            provider.resolve(foreign_binding)
        with pytest.raises(WorkspaceAuthorizationDenied):
            provider.resolve(mismatched_principal)
    assert store.read_bytes() == before


@pytest.mark.parametrize("access_kind", ["unauthenticated", "principal_without_case", "scoped_local_without_case"])
def test_workspace_provider_requires_bound_case_before_lookup(
    owner_key_workspace, monkeypatch: pytest.MonkeyPatch, access_kind: str,
) -> None:
    from applications.complaint_workspace import (
        WorkspaceAccess, WorkspaceAuthorizationDenied, workspace_access_scope,
    )

    service = owner_key_workspace
    contexts = {
        "unauthenticated": WorkspaceAccess.unauthenticated(),
        "principal_without_case": WorkspaceAccess.authenticated(TENANT),
        "scoped_local_without_case": WorkspaceAccess.trusted_local(TENANT),
    }
    def no_key_lookup():
        pytest.fail("unbound provider construction consulted the shared key session")
    monkeypatch.setattr(service, "_private_key_session", no_key_lookup)
    with workspace_access_scope(contexts[access_kind]):
        with pytest.raises(WorkspaceAuthorizationDenied):
            service.private_key_provider()
        with pytest.raises(WorkspaceAuthorizationDenied):
            service.ensure_private_case_key(TENANT, CASE)


def test_retained_workspace_provider_honors_operator_lock(owner_key_workspace) -> None:
    from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope

    service = owner_key_workspace
    with workspace_access_scope(WorkspaceAccess.authenticated(TENANT, case_id=CASE)):
        provider = service.private_key_provider()
        key_id = provider.resolve(_binding())[0]
    service.lock_private_keys()
    with workspace_access_scope(WorkspaceAccess.authenticated(TENANT, case_id=CASE)):
        with pytest.raises(PrivateKeyLockedError):
            provider.resolve(_binding())
        with pytest.raises(PrivateKeyLockedError):
            service.private_key_provider()
        assert "case_count" not in service.ensure_private_case_key(TENANT, CASE)
    service.unlock_private_keys(passphrase=PASSPHRASE)
    with workspace_access_scope(WorkspaceAccess.authenticated(TENANT, case_id=CASE)):
        assert provider.resolve(_binding())[0] == key_id

@pytest.mark.parametrize("failure_kind", ["crypto_capability", "os_error"])
def test_real_cli_operation_exception_is_sanitized_after_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    private_key_cli, failure_kind: str,
) -> None:
    import getpass
    import integrations.private_storage as private

    calls = {"prompt": 0, "create": 0}
    observed_create_arguments = []
    marker = PASSPHRASE + " /synthetic/private/operation"

    def synthetic_prompt(_prompt):
        calls["prompt"] += 1
        return PASSPHRASE

    def unavailable(self, *, protection, passphrase=None, keyring=None):
        calls["create"] += 1
        observed_create_arguments.append((protection, passphrase, keyring))
        if failure_kind == "crypto_capability":
            raise private.PrivateCryptoCapabilityError(marker)
        raise OSError(marker)

    monkeypatch.setattr(getpass, "getpass", synthetic_prompt)
    monkeypatch.setattr(private.UserOwnedKeySession, "create", unavailable)
    target = tmp_path / "operation-failed-store"
    monkeypatch.setattr(sys, "argv", [
        "complaint-workspace", "keys-init", "--store-dir", str(target),
    ])
    capsys.readouterr()
    with pytest.raises(SystemExit) as exited:
        private_key_cli.main()
    assert exited.value.code == 2
    captured = capsys.readouterr()
    assert calls == {"prompt": 1, "create": 1}
    assert observed_create_arguments == [("passphrase", PASSPHRASE, None)]
    receipt = json.loads(captured.out)
    assert receipt["status"] == receipt["code"] == "key_operation_failed"
    assert receipt["awaiting_user"] is True and receipt["worker_may_continue"] is True
    assert receipt["raw_key_persisted"] is False
    assert PASSPHRASE not in captured.out + captured.err
    assert marker not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err
    assert not target.exists()


def test_real_cli_rejects_secret_argv_before_parser_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], private_key_cli,
) -> None:
    import getpass

    prompt_calls = []

    def forbidden_prompt(prompt):
        prompt_calls.append(prompt)
        raise AssertionError("secret argv reached the passphrase prompt")

    monkeypatch.setattr(getpass, "getpass", forbidden_prompt)
    for secret_args in (["--passphrase", PASSPHRASE], ["--passphrase=" + PASSPHRASE]):
        target = tmp_path / "secret-argument-refused"
        monkeypatch.setattr(sys, "argv", [
            "complaint-workspace", "keys-init", "--store-dir", str(target), *secret_args,
        ])
        capsys.readouterr()
        with pytest.raises(SystemExit) as exited:
            private_key_cli.main()
        assert exited.value.code != 0
        captured = capsys.readouterr()
        assert PASSPHRASE not in str(exited.value)
        assert PASSPHRASE not in captured.out + captured.err
        assert "Traceback" not in captured.out + captured.err
        assert prompt_calls == []
        assert not target.exists()


def test_retained_raw_session_provider_honors_lock_and_explicit_unlock(tmp_path: Path) -> None:
    session = UserOwnedKeySession(tmp_path / "raw-provider-store")
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    session.ensure_data_key(TENANT, CASE)
    provider = session.provider()
    key_id, key = provider.resolve(_binding())
    stored = session.path.read_bytes()
    session.lock()
    with pytest.raises(PrivateKeyLockedError):
        provider.resolve(_binding())
    assert session.path.read_bytes() == stored
    session.unlock_passphrase(PASSPHRASE)
    assert provider.resolve(_binding()) == (key_id, key)
    assert session.path.read_bytes() == stored
