"""Encrypted append-only case audit events.

Positive cases record owner and member actions with actor, resource, revision,
grant, and purpose references, then replay the same request without a second
event. Negative cases reject cross-case use, stale revisions, removed and
revoked grants, tampered chains, and any complaint text or key material in
logs, notifications, and error payloads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from applications.case_audit import (
    SCHEMA_VERSION,
    CaseAuditError,
    CaseAuditStore,
    error_payload,
    owner_grant_reference,
)
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore
from integrations.private_storage import UserOwnedKeySession

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

COMPLAINT = "synthetic complaint narrative about a neighbor"
PURPOSE = "purpose:case-review"


def _world(tmp_path: Path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    stranger = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    other = cases.create_case(actor_principal_id=stranger.principal_id)
    memberships = CaseMembershipStore(
        tmp_path / "memberships",
        key=os.urandom(32),
        key_id="membership-key",
        principals=principals,
        cases=cases,
        clock=lambda: 1_700_000_000,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants",
        key=os.urandom(32),
        key_id="resource-grant-key",
        principals=principals,
        cases=cases,
        memberships=memberships,
    )
    audit_key = os.urandom(32)
    audit = CaseAuditStore(
        tmp_path / "audit",
        key=audit_key,
        key_id="audit-key",
        principals=principals,
        cases=cases,
        memberships=memberships,
        key_grants=key_grants,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    recipient_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    recipient_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    owner_session.ensure_data_key(case.tenant_id, case.case_id)
    return {
        "tmp": tmp_path,
        "principals": principals,
        "cases": cases,
        "memberships": memberships,
        "key_grants": key_grants,
        "audit": audit,
        "audit_key": audit_key,
        "owner": owner,
        "lawyer": lawyer,
        "admin": admin,
        "stranger": stranger,
        "case": case,
        "other": other,
        "owner_session": owner_session,
        "recipient_session": recipient_session,
    }


def _accept(world, *, actions=None):
    case = world["case"]
    pending = world["memberships"].invite(
        owner_principal_id=world["owner"].principal_id,
        member_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=set(actions or {"case.read", "case.review"}),
        expires_at=1_700_003_600,
        expected_case_revision=case.revision,
        idempotency_key="invite-1",
    )
    return world["memberships"].accept(
        member_principal_id=world["lawyer"].principal_id,
        grant_id=pending.grant_id,
        expected_version=pending.version,
        idempotency_key="accept-1",
    )


def _owner_record(world, **overrides):
    case = world["case"]
    body = {
        "actor_principal_id": world["owner"].principal_id,
        "case_id": case.case_id,
        "tenant_id": case.tenant_id,
        "resource_id": case.resource_id,
        "action": "case.review",
        "expected_revision": case.revision,
        "grant_id": owner_grant_reference(case.tenant_id),
        "grant_kind": "owner",
        "purpose_ref": PURPOSE,
        "idempotency_key": "owner-audit-1",
    }
    body.update(overrides)
    return world["audit"].record_from_request(body)


def _assert_redacted(blob: bytes, secret: bytes, complaint: str = COMPLAINT) -> None:
    assert complaint.encode("utf-8") not in blob
    assert secret not in blob
    assert secret.hex().encode("ascii") not in blob


def test_history_records_references_and_replay_is_idempotent(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    audit = world["audit"]
    first = _owner_record(world)
    replay = _owner_record(world)
    assert replay == first
    assert first.sequence == 1
    assert first.action == "case.review"
    assert first.actor_principal_id == world["owner"].principal_id
    assert first.actor_principal_id != first.canonical_owner_principal_id
    assert first.canonical_owner_principal_id == case.tenant_id
    assert first.actor_is_encrypted_owner is False
    assert first.resource_id == case.resource_id
    assert first.revision == case.revision
    assert first.grant_id == owner_grant_reference(case.tenant_id)
    assert first.grant_kind == "owner"
    assert first.purpose_ref == PURPOSE
    assert first.public_view()["schema_version"] == SCHEMA_VERSION
    assert audit.operational_logs() == (audit.operational_logs()[0],)
    assert len(audit.notifications()) == 1
    assert audit.operational_logs()[0]["grant_id"] == first.grant_id
    assert audit.notifications()[0]["template"] == "case_audit_recorded"
    assert audit.notifications()[0]["purpose_ref"] == PURPOSE

    accepted = _accept(world)
    second = audit.record(
        actor_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        action="case.review",
        expected_revision=case.revision,
        grant_id=accepted.grant_id,
        grant_kind="membership",
        purpose_ref="purpose:assigned-review",
        idempotency_key="lawyer-audit-1",
        membership_version=accepted.version,
    )
    again = audit.record(
        actor_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        action="case.review",
        expected_revision=case.revision,
        grant_id=accepted.grant_id,
        grant_kind="membership",
        purpose_ref="purpose:assigned-review",
        idempotency_key="lawyer-audit-1",
        membership_version=accepted.version,
    )
    assert again.event_id == second.event_id
    assert second.sequence == 2
    assert second.grant_id == accepted.grant_id
    assert second.membership_grant_id == accepted.grant_id
    assert second.actor_is_encrypted_owner is False
    assert len(audit.operational_logs()) == 2
    assert len(audit.notifications()) == 2

    owner_history = audit.history(
        actor_principal_id=world["owner"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        grant_id=owner_grant_reference(case.tenant_id),
        grant_kind="owner",
        expected_revision=case.revision,
    )
    member_history = audit.history(
        actor_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        grant_id=accepted.grant_id,
        grant_kind="membership",
        expected_revision=case.revision,
        membership_version=accepted.version,
    )
    assert [item.event_id for item in owner_history] == [first.event_id, second.event_id]
    assert member_history == owner_history
    first_envelope = (tmp_path / "audit" / "events" / case.case_id / "1.envelope").read_bytes()

    reopened = CaseAuditStore(
        tmp_path / "audit",
        key=world["audit_key"],
        key_id="audit-key",
        principals=world["principals"],
        cases=world["cases"],
        memberships=world["memberships"],
        key_grants=world["key_grants"],
    )
    cold = reopened.history(
        actor_principal_id=world["owner"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        grant_id=owner_grant_reference(case.tenant_id),
        grant_kind="owner",
        expected_revision=case.revision,
    )
    assert [item.event_id for item in cold] == [first.event_id, second.event_id]
    assert (tmp_path / "audit" / "events" / case.case_id / "1.envelope").read_bytes() == first_envelope

    surfaced = json.dumps({
        "logs": list(audit.operational_logs()),
        "notifications": list(audit.notifications()),
        "errors": list(audit.error_payloads()),
    }).encode("utf-8")
    disk = b"".join(path.read_bytes() for path in (tmp_path / "audit").rglob("*") if path.is_file())
    _assert_redacted(surfaced, world["audit_key"])
    _assert_redacted(disk, world["audit_key"])
    assert COMPLAINT.encode("utf-8") not in first_envelope


def test_denials_redact_complaint_text_and_key_material(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    other = world["other"]
    audit = world["audit"]
    leaked_key = os.urandom(32)
    accepted = _accept(world)
    recorded = _owner_record(world)

    with pytest.raises(CaseAuditError) as sensitive:
        audit.record_from_request({
            "actor_principal_id": world["owner"].principal_id,
            "case_id": case.case_id,
            "tenant_id": case.tenant_id,
            "resource_id": case.resource_id,
            "action": "case.update",
            "expected_revision": case.revision,
            "grant_id": owner_grant_reference(case.tenant_id),
            "grant_kind": "owner",
            "purpose_ref": PURPOSE,
            "idempotency_key": "leak-1",
            "complaint_text": COMPLAINT,
            "data_key": leaked_key.hex(),
            "narrative": COMPLAINT,
        })
    assert sensitive.value.code == "sensitive_field"
    assert str(sensitive.value) == "sensitive_field"
    assert error_payload(sensitive.value) == {"code": "sensitive_field"}
    assert audit.error_payloads()[-1] == {"code": "sensitive_field"}

    with pytest.raises(CaseAuditError) as prose:
        _owner_record(world, purpose_ref=COMPLAINT, idempotency_key="prose")
    assert prose.value.code == "purpose_ref"

    with pytest.raises(CaseAuditError) as mismatch:
        _owner_record(world, action="case.update", idempotency_key="owner-audit-1")
    assert mismatch.value.code == "replay_mismatch"

    with pytest.raises(CaseAuditError) as stranger:
        audit.record(
            actor_principal_id=world["stranger"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_revision=case.revision,
            grant_id=owner_grant_reference(case.tenant_id),
            grant_kind="owner",
            purpose_ref=PURPOSE,
            idempotency_key="stranger",
        )
    assert stranger.value.code == "missing_case"

    with pytest.raises(CaseAuditError) as admin:
        audit.history(
            actor_principal_id=world["admin"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            grant_id=owner_grant_reference(case.tenant_id),
            grant_kind="owner",
            expected_revision=case.revision,
        )
    assert admin.value.code == "missing_case"

    with pytest.raises(CaseAuditError) as cross:
        audit.record(
            actor_principal_id=world["lawyer"].principal_id,
            case_id=other.case_id,
            tenant_id=other.tenant_id,
            resource_id=other.resource_id,
            action="case.review",
            expected_revision=other.revision,
            grant_id=accepted.grant_id,
            grant_kind="membership",
            purpose_ref=PURPOSE,
            idempotency_key="cross-case",
            membership_version=accepted.version,
        )
    assert cross.value.code in {"case_mismatch", "tenant_mismatch", "actor_not_member"}

    with pytest.raises(CaseAuditError) as stale:
        audit.record(
            actor_principal_id=world["owner"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_revision=case.revision + 9,
            grant_id=owner_grant_reference(case.tenant_id),
            grant_kind="owner",
            purpose_ref=PURPOSE,
            idempotency_key="stale-revision",
        )
    assert stale.value.code == "revision_conflict"

    removed = world["memberships"].remove(
        owner_principal_id=world["owner"].principal_id,
        grant_id=accepted.grant_id,
        expected_version=accepted.version,
    )
    assert removed.status == "removed"
    with pytest.raises(CaseAuditError) as denied:
        audit.record(
            actor_principal_id=world["lawyer"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            action="case.review",
            expected_revision=case.revision,
            grant_id=accepted.grant_id,
            grant_kind="membership",
            purpose_ref=PURPOSE,
            idempotency_key="after-removal",
            membership_version=removed.version,
        )
    assert denied.value.code == "membership_removed"
    with pytest.raises(CaseAuditError) as lawyer_history:
        audit.history(
            actor_principal_id=world["lawyer"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            grant_id=accepted.grant_id,
            grant_kind="membership",
            expected_revision=case.revision,
            membership_version=removed.version,
        )
    assert lawyer_history.value.code == "membership_removed"
    still = audit.record(
        actor_principal_id=world["owner"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        action="case.review",
        expected_revision=case.revision,
        grant_id=owner_grant_reference(case.tenant_id),
        grant_kind="owner",
        purpose_ref=PURPOSE,
        idempotency_key="owner-audit-1",
    )
    assert still.event_id == recorded.event_id

    blob = json.dumps({
        "logs": list(audit.operational_logs()),
        "notifications": list(audit.notifications()),
        "errors": list(audit.error_payloads()),
    }).encode("utf-8")
    disk = b"".join(path.read_bytes() for path in (tmp_path / "audit").rglob("*") if path.is_file())
    _assert_redacted(blob, leaked_key)
    _assert_redacted(disk, leaked_key)
    _assert_redacted(disk, world["audit_key"])
    assert COMPLAINT not in str(audit.error_payloads())


def test_key_grant_reference_and_broken_chain(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    audit = world["audit"]
    accepted = _accept(world, actions={"case.read", "case.review"})
    granted = world["key_grants"].issue(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        membership_grant_id=accepted.grant_id,
        membership_version=accepted.version,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        artifact_kind="case-note",
        artifact_revision="rev-3",
        owner_session=world["owner_session"],
        recipient_session=world["recipient_session"],
        idempotency_key="key-grant-1",
    )
    event = audit.record(
        actor_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        action="case.read",
        expected_revision=case.revision,
        grant_id=granted.key_grant_id,
        grant_kind="key",
        purpose_ref="purpose:delegated-read",
        idempotency_key="key-audit-1",
        membership_version=accepted.version,
    )
    assert event.grant_kind == "key"
    assert event.grant_id == granted.key_grant_id
    assert event.grant_version == granted.version
    assert event.membership_grant_id == accepted.grant_id
    assert event.resource_revision == "rev-3"
    assert event.revision == case.revision
    view = event.public_view()
    assert "wrapped_ciphertext" not in view
    assert "data_key" not in view
    replay = audit.record(
        actor_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        action="case.read",
        expected_revision=case.revision,
        grant_id=granted.key_grant_id,
        grant_kind="key",
        purpose_ref="purpose:delegated-read",
        idempotency_key="key-audit-1",
        membership_version=accepted.version,
    )
    assert replay.event_id == event.event_id
    assert len(audit.operational_logs()) == 1

    world["key_grants"].revoke_and_rotate(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        cutoff=granted.generation,
        owner_session=world["owner_session"],
        idempotency_key="revoke-1",
    )
    with pytest.raises(CaseAuditError) as revoked:
        audit.record(
            actor_principal_id=world["lawyer"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_revision=case.revision,
            grant_id=granted.key_grant_id,
            grant_kind="key",
            purpose_ref="purpose:delegated-read",
            idempotency_key="after-revoke",
            membership_version=accepted.version,
        )
    assert revoked.value.code == "grant_revoked"
    retained = audit.record(
        actor_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        action="case.read",
        expected_revision=case.revision,
        grant_id=granted.key_grant_id,
        grant_kind="key",
        purpose_ref="purpose:delegated-read",
        idempotency_key="key-audit-1",
        membership_version=accepted.version,
    )
    assert retained.event_id == event.event_id

    envelope = tmp_path / "audit" / "events" / case.case_id / "1.envelope"
    original = envelope.read_bytes()
    envelope.write_bytes(original[:-1] + bytes([original[-1] ^ 0x01]))
    with pytest.raises(CaseAuditError) as tampered:
        audit.history(
            actor_principal_id=world["owner"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            grant_id=owner_grant_reference(case.tenant_id),
            grant_kind="owner",
            expected_revision=case.revision,
        )
    assert tampered.value.code == "integrity"
    envelope.write_bytes(original)
    pointer = tmp_path / "audit" / "events" / case.case_id / "1.event"
    pointer.unlink()
    with pytest.raises(CaseAuditError) as gap:
        audit.history(
            actor_principal_id=world["owner"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            grant_id=owner_grant_reference(case.tenant_id),
            grant_kind="owner",
            expected_revision=case.revision,
        )
    assert gap.value.code == "audit_chain_broken"

    disk = b"".join(path.read_bytes() for path in (tmp_path / "audit").rglob("*") if path.is_file())
    assert b"wrapped_ciphertext" not in disk
    assert world["audit_key"] not in disk
    assert granted.wrapped_ciphertext.encode("utf-8") not in disk
