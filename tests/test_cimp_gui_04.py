"""Server-owned principal roster bound to the private-storage key boundary.

Positive cases persist opaque identifiers and a server-assigned staff role,
then recover them with the injected data key. Negative cases reject staff
roles supplied by a request body, deny assignment by a non-admin actor, and
fail closed when ciphertext or the key does not match.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from applications.principal_store import (
    CANONICAL_ROLE,
    DIRECTORY_CASE_ID,
    STAFF_ROLES,
    PrincipalStore,
    PrincipalStoreError,
)
from integrations.private_storage import PrivateArtifactBinding

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _store(tmp_path: Path, name: str = "roster") -> tuple[PrincipalStore, bytes]:
    key = os.urandom(32)
    return PrincipalStore(tmp_path / name, key=key, key_id="roster-key"), key


def test_request_persists_opaque_complainant_and_recovers_without_case_text(tmp_path: Path) -> None:
    store, key = _store(tmp_path)
    marker = "case-body-marker"
    record = store.register_from_request({
        "case_plaintext": marker,
        "credentials": "auth-material-marker",
        "role": CANONICAL_ROLE,
    })
    assert record.principal_id != record.tenant_id
    assert record.principal_id.isalnum() and record.tenant_id.isalnum()
    assert set(record.roles) == {CANONICAL_ROLE}
    assert record.roles[0] not in STAFF_ROLES
    assert record.role_authority == "server"
    assert "case_plaintext" in record.excluded_fields
    assert "credentials" in record.excluded_fields

    reopened = PrincipalStore(tmp_path / "roster", key=key, key_id="roster-key")
    loaded = reopened.load(record.principal_id)
    assert loaded == record
    assert reopened.recover() == (record,)

    metadata = reopened.operational_metadata(record.principal_id)
    encoded = repr(metadata)
    assert marker not in encoded
    assert "auth-material-marker" not in encoded
    assert "case_plaintext" not in metadata
    assert metadata["tenant_id"] == record.tenant_id
    assert metadata["roles"] == [CANONICAL_ROLE]

    raw = (tmp_path / "roster" / f"{record.principal_id}.envelope").read_bytes()
    assert marker.encode("utf-8") not in raw
    assert b"auth-material-marker" not in raw

    binding = PrivateArtifactBinding(
        tenant_id=record.tenant_id,
        case_id=DIRECTORY_CASE_ID,
        artifact_kind="principal-record",
        revision="1",
        principal_id=record.tenant_id,
    )
    assert binding.principal_id != record.principal_id


def test_request_body_cannot_create_staff_roles(tmp_path: Path) -> None:
    store, _key = _store(tmp_path)
    for body in (
        {"role": "operational_admin"},
        {"roles": ["lawyer"]},
        {"staff_role": "lawyer"},
        {"is_admin": True},
        {"is_lawyer": True},
    ):
        with pytest.raises(PrincipalStoreError) as caught:
            store.register_from_request(body)
        assert caught.value.code == "request_body_cannot_assign_staff_role"
    assert store.recover() == ()
    assert list((tmp_path / "roster").glob("*.envelope")) == []


def test_server_assignment_requires_existing_admin_and_revision(tmp_path: Path) -> None:
    store, key = _store(tmp_path)
    admin = store.install_server_role(role="operational_admin")
    subject = store.register_from_request({})
    assert "operational_admin" in admin.roles
    assert admin.principal_id != admin.tenant_id

    with pytest.raises(PrincipalStoreError) as denied:
        store.assign_role(
            actor_principal_id=subject.principal_id,
            subject_principal_id=admin.principal_id,
            role="lawyer",
            expected_revision=admin.revision,
        )
    assert denied.value.code == "actor_lacks_role_authority"
    assert store.load(admin.principal_id).roles == ("operational_admin",)

    with pytest.raises(PrincipalStoreError) as conflict:
        store.assign_role(
            actor_principal_id=admin.principal_id,
            subject_principal_id=subject.principal_id,
            role="lawyer",
            expected_revision=subject.revision + 3,
        )
    assert conflict.value.code == "revision_conflict"

    updated = store.assign_role(
        actor_principal_id=admin.principal_id,
        subject_principal_id=subject.principal_id,
        role="lawyer",
        expected_revision=subject.revision,
    )
    assert updated.roles == ("lawyer",)
    assert updated.revision == subject.revision + 1
    assert updated.tenant_id == subject.tenant_id
    assert updated.principal_id == subject.principal_id

    restored = PrincipalStore(tmp_path / "roster", key=key, key_id="roster-key").recover()
    by_id = {item.principal_id: item for item in restored}
    assert by_id[subject.principal_id].roles == ("lawyer",)
    assert by_id[admin.principal_id].roles == ("operational_admin",)


def test_tamper_or_wrong_key_fails_recovery(tmp_path: Path) -> None:
    store, key = _store(tmp_path)
    record = store.register_from_request({})
    path = tmp_path / "roster" / f"{record.principal_id}.envelope"
    original = path.read_bytes()
    blob = bytearray(original)
    blob[-1] ^= 0x01
    path.write_bytes(bytes(blob))
    with pytest.raises(PrincipalStoreError) as tampered:
        store.recover()
    assert tampered.value.code == "integrity"

    path.write_bytes(original)
    other = PrincipalStore(tmp_path / "roster", key=os.urandom(32), key_id="roster-key")
    with pytest.raises(PrincipalStoreError) as wrong_key:
        other.load(record.principal_id)
    assert wrong_key.value.code == "integrity"
    assert store.load(record.principal_id) == record

    # Untampered bytes open only with the original injected key.
    fresh, fresh_key = _store(tmp_path, name="other")
    created = fresh.register_from_request({})
    assert PrincipalStore(tmp_path / "other", key=fresh_key, key_id="roster-key").load(created.principal_id) == created
    assert key != fresh_key
