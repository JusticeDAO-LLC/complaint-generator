"""Independent case namespaces for an authenticated principal.

Positive cases mint two owner-only cases with distinct case and resource ids,
and reopen a legacy owner-only envelope under the declared storage version.
Negative cases reject attacker-controlled user_id selection, unauthenticated
callers, and missing keys that would otherwise create an empty case.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from applications.case_directory import (
    LEGACY_OWNER_ONLY_VERSION,
    MIGRATION_RULES,
    NAMESPACED_CASE_VERSION,
    CaseDirectory,
    CaseDirectoryError,
    legacy_owner_only_binding,
)
from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    WorkspaceAccess,
    WorkspaceAuthorizationDenied,
    WorkspacePersistenceError,
    workspace_access_scope,
)
from integrations.private_storage import seal_private_artifact

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ACTOR = "principal-owner-aaa"
OTHER = "principal-owner-bbb"
KEY_ID = "case-namespace-key"
MARKER = "legacy-narrative-marker"


def _service(tmp_path: Path, principal: str) -> ComplaintWorkspaceService:
    return ComplaintWorkspaceService(
        tmp_path / "sessions",
        access=WorkspaceAccess.authenticated(principal),
    )


def _open(service: ComplaintWorkspaceService, key: bytes) -> None:
    service.open_case_directory(key=key, key_id=KEY_ID)


def _legacy_envelope(principal: str, key: bytes, narrative: str = MARKER) -> bytes:
    payload = json.dumps({"user_id": principal, "narrative": narrative}, sort_keys=True).encode("utf-8")
    return seal_private_artifact(
        payload,
        binding=legacy_owner_only_binding(principal),
        key=key,
        key_id=KEY_ID,
    )


def _directory_bytes(tmp_path: Path) -> dict[str, bytes]:
    root = tmp_path / "sessions" / "case-namespaces"
    if not root.exists():
        return {}
    return {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}


def test_new_directory_is_private_under_shared_umask_and_unsafe_existing_root_is_refused(tmp_path: Path) -> None:
    key = os.urandom(32)
    root = tmp_path / "new-private-directory"
    previous = os.umask(0o002)
    try:
        directory = CaseDirectory(root, key=key, key_id=KEY_ID)
        created = directory.create_case(actor_principal_id=ACTOR)
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert directory.list_cases(actor_principal_id=ACTOR) == (created,)
        reopened = CaseDirectory(root, key=key, key_id=KEY_ID)
        assert reopened.select_case(actor_principal_id=ACTOR, case_id=created.case_id) == created
        unsafe = tmp_path / "existing-shared-directory"
        unsafe.mkdir(mode=0o775)
        os.chmod(unsafe, 0o775)
        existing = CaseDirectory(unsafe, key=key, key_id=KEY_ID)
        with pytest.raises(CaseDirectoryError) as refused:
            existing.create_case(actor_principal_id=ACTOR)
        assert refused.value.code == "unexpected_path"
        assert stat.S_IMODE(unsafe.stat().st_mode) == 0o775
        assert list(unsafe.iterdir()) == []
    finally:
        os.umask(previous)


def test_two_cases_are_independent_and_ignore_user_id(tmp_path: Path) -> None:
    key = os.urandom(32)
    service = _service(tmp_path, ACTOR)
    _open(service, key)
    first = service.create_independent_case(supplied_user_id=ACTOR)
    second = service.create_independent_case(supplied_user_id=ACTOR)
    assert first["owner_principal_id"] == ACTOR
    assert second["owner_principal_id"] == ACTOR
    assert first["tenant_id"] == second["tenant_id"]
    assert first["tenant_id"] != ACTOR
    assert first["case_id"] != second["case_id"]
    assert first["resource_id"] != second["resource_id"]
    assert first["membership"] == "owner-only"
    assert first["storage_version"] == NAMESPACED_CASE_VERSION
    assert first["actor_is_encrypted_owner"] is False
    assert "user_id" not in first

    listed = service.list_independent_cases(supplied_user_id=ACTOR)
    assert [item["case_id"] for item in listed] == [first["case_id"], second["case_id"]]
    assert service.select_independent_case(second["case_id"], supplied_user_id=ACTOR) == second

    with pytest.raises(CaseDirectoryError) as rejected:
        service.select_independent_case(first["case_id"], supplied_user_id=OTHER)
    assert rejected.value.code == "user_id_not_a_selector"
    assert service.list_independent_cases() == listed

    raw = b"".join(_directory_bytes(tmp_path).values())
    assert MARKER.encode("utf-8") not in raw
    assert b"user_id" not in raw


def test_legacy_owner_only_case_stays_readable_and_can_gain_a_second_case(tmp_path: Path) -> None:
    key = os.urandom(32)
    service = _service(tmp_path, ACTOR)
    _open(service, key)
    envelope = _legacy_envelope(ACTOR, key)
    adopted = service.adopt_owner_only_case(envelope, supplied_user_id=ACTOR)
    case = adopted["case"]
    assert adopted["persisted_session_plaintext"] is False
    assert adopted["legacy_session"]["narrative"] == MARKER
    assert case["storage_version"] == LEGACY_OWNER_ONLY_VERSION
    assert case["tenant_id"] == case["case_id"] == ACTOR
    assert case["membership"] == "owner-only"
    assert case["actor_is_encrypted_owner"] is True
    assert "storage_version_1_owner_only_readable" in MIGRATION_RULES

    extra = service.create_independent_case()
    assert extra["case_id"] != case["case_id"]
    assert extra["resource_id"] != case["resource_id"]
    assert extra["tenant_id"] == ACTOR
    assert extra["storage_version"] == NAMESPACED_CASE_VERSION

    reread = service.read_owner_only_case(envelope)
    assert reread["narrative"] == MARKER
    assert service.select_independent_case(case["case_id"])["resource_id"] == case["resource_id"]
    raw = b"".join(_directory_bytes(tmp_path).values())
    assert MARKER.encode("utf-8") not in raw


def test_other_principal_case_is_not_selected_by_user_id(tmp_path: Path) -> None:
    key = os.urandom(32)
    service = _service(tmp_path, ACTOR)
    _open(service, key)
    owned = service.create_independent_case()
    with workspace_access_scope(WorkspaceAccess.authenticated(OTHER)):
        foreign = service.create_independent_case()
        listed = service.list_independent_cases(supplied_user_id=OTHER)
        assert [item["case_id"] for item in listed] == [foreign["case_id"]]
        with pytest.raises(CaseDirectoryError) as missing:
            service.select_independent_case(owned["case_id"], supplied_user_id=ACTOR)
        assert missing.value.code == "user_id_not_a_selector"
        with pytest.raises(CaseDirectoryError) as absent:
            service.select_independent_case(owned["case_id"])
        assert absent.value.code == "missing_case"
    assert service.select_independent_case(owned["case_id"])["tenant_id"] == owned["tenant_id"]
    assert owned["tenant_id"] != foreign["tenant_id"]


def test_missing_key_does_not_create_an_empty_case(tmp_path: Path) -> None:
    key = os.urandom(32)
    other_key = os.urandom(32)
    service = _service(tmp_path, ACTOR)
    _open(service, key)
    created = service.create_independent_case()
    before = _directory_bytes(tmp_path)
    assert before

    wrong = _service(tmp_path, ACTOR)
    wrong.open_case_directory(key=other_key, key_id=KEY_ID)
    with pytest.raises(CaseDirectoryError) as listed:
        wrong.list_independent_cases()
    assert listed.value.code == "missing_key"
    assert _directory_bytes(tmp_path) == before

    envelope = _legacy_envelope(ACTOR, key, narrative="must-remain")
    with pytest.raises(CaseDirectoryError) as adopted:
        wrong.adopt_owner_only_case(envelope)
    assert adopted.value.code == "missing_key"
    with pytest.raises(CaseDirectoryError) as created_over:
        wrong.create_independent_case(unreadable_legacy_envelope=envelope)
    assert created_over.value.code == "missing_key"
    assert _directory_bytes(tmp_path) == before
    assert service.select_independent_case(created["case_id"]) == created

    fresh = _service(tmp_path / "fresh", ACTOR)
    fresh.open_case_directory(key=other_key, key_id=KEY_ID)
    with pytest.raises(CaseDirectoryError) as blocked:
        fresh.create_independent_case(unreadable_legacy_envelope=envelope)
    assert blocked.value.code == "missing_key"
    assert _directory_bytes(tmp_path / "fresh") == {}


def test_unauthenticated_and_closed_directory_fail_closed(tmp_path: Path) -> None:
    key = os.urandom(32)
    closed = _service(tmp_path, ACTOR)
    with pytest.raises(WorkspacePersistenceError) as not_open:
        closed.list_independent_cases()
    assert not_open.value.code == "case_directory_closed"

    local = ComplaintWorkspaceService(tmp_path / "local", access=WorkspaceAccess.trusted_local(ACTOR, ACTOR))
    with pytest.raises(WorkspaceAuthorizationDenied):
        local.open_case_directory(key=key, key_id=KEY_ID)
    anonymous = ComplaintWorkspaceService(tmp_path / "anon", access=WorkspaceAccess.unauthenticated())
    with pytest.raises(WorkspaceAuthorizationDenied):
        anonymous.open_case_directory(key=key, key_id=KEY_ID)

    readable = _legacy_envelope(ACTOR, key)
    reader = _service(tmp_path / "reader", OTHER)
    reader.open_case_directory(key=key, key_id=KEY_ID)
    with pytest.raises(CaseDirectoryError) as foreign:
        reader.read_owner_only_case(readable)
    assert foreign.value.code == "missing_key"
