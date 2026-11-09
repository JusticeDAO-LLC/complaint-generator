"""Recipient-bound case resource key grants.

Positive cases wrap a case data key to an accepted member and open the
artifact under the canonical tenant/case/principal/revision binding. Negative
cases reject membership without a grant, a grant without membership, browser
keys, admin master decryption, owner impersonation, and a changed revision.
Existing owner-only associated-data denial and schema version 2 stay in force.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import (
    SCHEMA_VERSION,
    CaseResourceKeyGrantError,
    CaseResourceKeyGrantStore,
)
from integrations.private_storage import (
    KEY_STORE_VERSION,
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    UserOwnedKeySession,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ARTIFACT_KIND = "case-note"
REVISION = "3"


class _Access:
    def __init__(self, principal_id: str, case_id: str, trust: str = "authenticated") -> None:
        self.principal_id = principal_id
        self.case_id = case_id
        self.trust = trust


def _world(tmp_path: Path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    stranger = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    memberships = CaseMembershipStore(
        tmp_path / "memberships",
        key=os.urandom(32),
        key_id="membership-key",
        principals=principals,
        cases=cases,
        clock=lambda: 1_700_000_000,
    )
    grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants",
        key=os.urandom(32),
        key_id="resource-grant-key",
        principals=principals,
        cases=cases,
        memberships=memberships,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    recipient_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    recipient_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    owner_session.ensure_data_key(case.tenant_id, case.case_id)
    return {
        "principals": principals,
        "cases": cases,
        "memberships": memberships,
        "grants": grants,
        "owner": owner,
        "lawyer": lawyer,
        "admin": admin,
        "stranger": stranger,
        "case": case,
        "owner_session": owner_session,
        "recipient_session": recipient_session,
    }


def _accept(world, *, actions=None, key: str = "invite-1"):
    pending = world["memberships"].invite(
        owner_principal_id=world["owner"].principal_id,
        member_principal_id=world["lawyer"].principal_id,
        case_id=world["case"].case_id,
        resource_id=world["case"].resource_id,
        tenant_id=world["case"].tenant_id,
        actions=set(actions or {"case.read"}),
        expires_at=1_700_003_600,
        expected_case_revision=world["case"].revision,
        idempotency_key=key,
    )
    return world["memberships"].accept(
        member_principal_id=world["lawyer"].principal_id,
        grant_id=pending.grant_id,
        expected_version=pending.version,
        idempotency_key=key + "-accept",
    )


def _seal(world, payload: bytes = b"synthetic-case-note", *, revision: str = REVISION) -> bytes:
    case = world["case"]
    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=revision,
        principal_id=case.tenant_id,
    )
    key_id, key = world["owner_session"].provider().resolve(binding)
    return seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)


def _issue(world, membership, *, revision: str = REVISION, key: str = "grant-1"):
    case = world["case"]
    return world["grants"].issue(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        membership_grant_id=membership.grant_id,
        membership_version=membership.version,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=revision,
        owner_session=world["owner_session"],
        recipient_session=world["recipient_session"],
        idempotency_key=key,
    )


def test_delegated_read_requires_membership_and_recipient_grant(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    payload = b"synthetic-case-note"
    envelope = _seal(world, payload)
    pending = world["memberships"].invite(
        owner_principal_id=world["owner"].principal_id,
        member_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions={"case.read"},
        expires_at=1_700_003_600,
        expected_case_revision=case.revision,
        idempotency_key="pending-invite",
    )
    with pytest.raises(CaseResourceKeyGrantError) as pending_grant:
        _issue(world, pending, key="pending-grant")
    assert pending_grant.value.code == "membership_pending"

    accepted = _accept(world)
    with pytest.raises(CaseResourceKeyGrantError) as browser:
        world["grants"].issue_from_request({
            "actor_principal_id": world["owner"].principal_id,
            "recipient_principal_id": world["lawyer"].principal_id,
            "browser_key": "raw-browser-key",
            "data_key": "aa" * 32,
            "trusted_local": True,
        })
    assert browser.value.code == "browser_key_rejected"
    with pytest.raises(CaseResourceKeyGrantError) as bare:
        world["grants"].issue_from_request({"actor_principal_id": world["owner"].principal_id})
    assert bare.value.code == "request_cannot_mint_key_grant"

    with pytest.raises(CaseResourceKeyGrantError) as missing_grant:
        world["grants"].read_delegated(
            actor_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id="missing-grant",
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            recipient_session=world["recipient_session"],
        )
    assert missing_grant.value.code == "key_grant_required"

    granted = _issue(world, accepted)
    again = _issue(world, accepted)
    assert again.key_grant_id == granted.key_grant_id
    assert granted.owner_principal_id == world["owner"].principal_id
    assert granted.canonical_owner_principal_id == case.tenant_id
    assert granted.owner_principal_id != granted.canonical_owner_principal_id
    assert granted.recipient_principal_id == world["lawyer"].principal_id
    view = granted.public_view()
    assert view["schema_version"] == SCHEMA_VERSION
    assert view["envelope_schema_version"] == 2
    assert view["actor_is_encrypted_owner"] is False
    assert "wrapped_ciphertext" not in view
    assert "data_key" not in view
    assert "browser_keys_are_rejected" in view["limitations"]
    stored = (tmp_path / "key-grants" / "grants" / f"{granted.key_grant_id}.envelope").read_bytes()
    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=REVISION,
        principal_id=case.tenant_id,
    )
    _key_id, data_key = world["owner_session"].provider().resolve(binding)
    assert data_key not in stored
    assert stat.S_IMODE((tmp_path / "key-grants" / "grants" / f"{granted.key_grant_id}.envelope").stat().st_mode) == 0o600
    keystore = json.loads((tmp_path / "lawyer-keys" / "keystore.json").read_text(encoding="utf-8"))
    assert keystore["schema_version"] == KEY_STORE_VERSION
    assert keystore["raw_key_persisted"] is False

    opened = world["grants"].read_delegated(
        actor_principal_id=world["lawyer"].principal_id,
        membership_grant_id=accepted.grant_id,
        membership_version=accepted.version,
        key_grant_id=granted.key_grant_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION,
        envelope=envelope,
        recipient_session=world["recipient_session"],
    )
    assert opened["data"] == payload
    assert opened["actor_principal_id"] == world["lawyer"].principal_id
    assert opened["canonical_owner_principal_id"] == case.tenant_id
    assert opened["actor_is_encrypted_owner"] is False
    assert opened["artifact_revision"] == REVISION
    assert opened["key_grant_id"] == granted.key_grant_id

    owner_opened = world["grants"].read_as_owner(
        actor_principal_id=world["owner"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION,
        envelope=envelope,
        owner_session=world["owner_session"],
    )
    assert owner_opened["data"] == payload
    assert owner_opened["actor_principal_id"] != owner_opened["canonical_owner_principal_id"]
    assert owner_opened["membership"] == "owner"
    assert owner_opened["key_grant_id"] is None


def test_owner_only_denial_impersonation_and_version_stay_closed(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    payload = b"owner-only-bytes"
    envelope = _seal(world, payload)
    accepted = _accept(world)
    granted = _issue(world, accepted)

    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=REVISION,
        principal_id=case.tenant_id,
    )
    lawyer_access = _Access(world["lawyer"].principal_id, case.case_id)
    with pytest.raises(PrivateArtifactBindingError) as mismatch:
        assert_access_matches_binding(lawyer_access, binding)
    assert mismatch.value.reason == "principal_mismatch"
    owner_actor_binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=REVISION,
        principal_id=world["owner"].principal_id,
    )
    key_id, key = world["owner_session"].provider().resolve(binding)
    with pytest.raises(PrivateArtifactIntegrityError) as aad:
        open_private_artifact(envelope, binding=owner_actor_binding, key=key, expected_key_id=key_id)
    assert aad.value.reason == "authentication_failed"

    stale = bytearray(envelope)
    assert stale[4] == 2
    stale[4] = 1
    with pytest.raises(PrivateArtifactIntegrityError) as version:
        open_private_artifact(bytes(stale), binding=binding, key=key, expected_key_id=key_id)
    assert version.value.reason == "unsupported_version"
    with pytest.raises(CaseResourceKeyGrantError) as owner_version:
        world["grants"].read_as_owner(
            actor_principal_id=world["owner"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=bytes(stale),
            owner_session=world["owner_session"],
        )
    assert owner_version.value.code == "unsupported_version"
    still = open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id)
    assert still == payload

    with pytest.raises(CaseResourceKeyGrantError) as impersonate:
        world["grants"].read_as_owner(
            actor_principal_id=world["owner"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            owner_session=world["owner_session"],
            aad_principal_id=world["owner"].principal_id,
        )
    assert impersonate.value.code == "owner_impersonation"
    with pytest.raises(CaseResourceKeyGrantError) as delegate_as_actor:
        world["grants"].read_delegated(
            actor_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id=granted.key_grant_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            recipient_session=world["recipient_session"],
            aad_principal_id=world["lawyer"].principal_id,
        )
    assert delegate_as_actor.value.code == "owner_impersonation"

    with pytest.raises(CaseResourceKeyGrantError) as lawyer_owner:
        world["grants"].read_as_owner(
            actor_principal_id=world["lawyer"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            owner_session=world["owner_session"],
        )
    assert lawyer_owner.value.code == "missing_case"
    with pytest.raises(CaseResourceKeyGrantError) as admin_read:
        world["grants"].read_as_owner(
            actor_principal_id=world["admin"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            owner_session=world["owner_session"],
        )
    assert admin_read.value.code == "admin_cannot_decrypt"
    with pytest.raises(CaseResourceKeyGrantError) as admin_master:
        world["grants"].decrypt_with_admin_master(master_key=os.urandom(32), envelope=envelope)
    assert admin_master.value.code == "admin_cannot_decrypt"
    with pytest.raises(CaseResourceKeyGrantError) as same_session:
        world["grants"].issue(
            actor_principal_id=world["owner"].principal_id,
            recipient_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            case_id=case.case_id,
            resource_id=case.resource_id,
            tenant_id=case.tenant_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            owner_session=world["owner_session"],
            recipient_session=world["owner_session"],
            idempotency_key="impersonated-session",
        )
    assert same_session.value.code == "owner_impersonation"

    with pytest.raises(CaseResourceKeyGrantError) as stranger:
        world["grants"].read_delegated(
            actor_principal_id=world["stranger"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id=granted.key_grant_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            recipient_session=world["recipient_session"],
        )
    assert stranger.value.code == "actor_not_member"
    with pytest.raises(CaseResourceKeyGrantError) as wrong_revision:
        world["grants"].read_delegated(
            actor_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id=granted.key_grant_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision="4",
            envelope=envelope,
            recipient_session=world["recipient_session"],
        )
    assert wrong_revision.value.code == "revision_mismatch"
    with pytest.raises(CaseResourceKeyGrantError) as replay:
        _issue(world, accepted, revision="9", key="grant-1")
    assert replay.value.code == "replay_mismatch"

    world["recipient_session"].lock()
    with pytest.raises(CaseResourceKeyGrantError) as locked:
        world["grants"].read_delegated(
            actor_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id=granted.key_grant_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            recipient_session=world["recipient_session"],
        )
    assert locked.value.code == "key_grant_rejected"
    owner_still = world["grants"].read_as_owner(
        actor_principal_id=world["owner"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION,
        envelope=envelope,
        owner_session=world["owner_session"],
    )
    assert owner_still["data"] == payload


"""Verified adopted owners keep their original canonical encrypted binding."""

from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from applications.case_directory import CaseDirectory, legacy_owner_only_binding
from applications.case_membership import CaseMembershipStore
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantError, CaseResourceKeyGrantStore
from integrations.private_storage import UserOwnedKeySession, PrivateArtifactBinding, seal_private_artifact

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _gui11_legacy_world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="synthetic-owner-passphrase")
    recipient_session = UserOwnedKeySession(tmp_path / "recipient-keys")
    recipient_session.create(protection="passphrase", passphrase="synthetic-recipient-passphrase")
    owner_session.ensure_data_key(owner.principal_id, owner.principal_id)
    legacy_binding = legacy_owner_only_binding(owner.principal_id)
    key_id, key = owner_session.provider().resolve(legacy_binding)
    cases = CaseDirectory(tmp_path / "cases", key=key, key_id=key_id)
    payload = json.dumps({"user_id": owner.principal_id, "synthetic": "legacy-session"}).encode()
    legacy_envelope = seal_private_artifact(payload, binding=legacy_binding, key=key, key_id=key_id)
    legacy, opened = cases.adopt_owner_only_case(actor_principal_id=owner.principal_id,
        envelope=legacy_envelope)
    assert opened == json.loads(payload)
    additional = cases.create_case(actor_principal_id=owner.principal_id)
    foreign = cases.create_case(actor_principal_id=stranger.principal_id)
    memberships = CaseMembershipStore(tmp_path / "memberships", key=os.urandom(32),
        key_id="membership-key", principals=principals, cases=cases, clock=lambda: 1_700_000_000)
    grants = CaseResourceKeyGrantStore(tmp_path / "key-grants", key=os.urandom(32),
        key_id="grant-key", principals=principals, cases=cases, memberships=memberships)
    return dict(owner=owner, lawyer=lawyer, stranger=stranger, principals=principals,
        cases=cases, memberships=memberships, grants=grants, owner_session=owner_session,
        recipient_session=recipient_session, legacy=legacy, additional=additional,
        foreign=foreign, legacy_envelope=legacy_envelope, legacy_payload=payload)


def _gui11_legacy_accept(world, case):
    pending = world["memberships"].invite(owner_principal_id=world["owner"].principal_id,
        member_principal_id=world["lawyer"].principal_id, case_id=case.case_id,
        resource_id=case.resource_id, tenant_id=case.tenant_id,
        actions={"case.read", "case.download", "case.message.send"},
        expires_at=1_700_003_600, expected_case_revision=case.revision,
        idempotency_key="invite-" + case.case_id)
    return world["memberships"].accept(member_principal_id=world["lawyer"].principal_id,
        grant_id=pending.grant_id, expected_version=pending.version,
        idempotency_key="accept-" + case.case_id)


def _gui11_legacy_artifact(world, case):
    if case == world["legacy"]:
        return "session", "session-v1", world["legacy_envelope"], world["legacy_payload"]
    binding = PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case.case_id,
        artifact_kind="case-note", revision="3", principal_id=case.tenant_id)
    world["owner_session"].ensure_data_key(case.tenant_id, case.case_id)
    key_id, key = world["owner_session"].provider().resolve(binding)
    payload = b"synthetic-additional-case"
    return "case-note", "3", seal_private_artifact(payload, binding=binding, key=key, key_id=key_id), payload


def _gui11_legacy_issue(world, case, membership, kind, revision, **changes):
    arguments = dict(actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        membership_grant_id=membership.grant_id, membership_version=membership.version,
        case_id=case.case_id, resource_id=case.resource_id, tenant_id=case.tenant_id,
        artifact_kind=kind, artifact_revision=revision, owner_session=world["owner_session"],
        recipient_session=world["recipient_session"], idempotency_key="issue-" + case.case_id)
    arguments.update(changes)
    return world["grants"].issue(**arguments)


def _gui11_legacy_read(world, case, membership, grant, kind, revision, envelope, **changes):
    arguments = dict(actor_principal_id=world["lawyer"].principal_id,
        membership_grant_id=membership.grant_id, membership_version=membership.version,
        key_grant_id=grant.key_grant_id, case_id=case.case_id, tenant_id=case.tenant_id,
        resource_id=case.resource_id, artifact_kind=kind, artifact_revision=revision,
        envelope=envelope, recipient_session=world["recipient_session"])
    arguments.update(changes)
    return world["grants"].read_delegated(**arguments)


@pytest.mark.parametrize("selection", ["legacy", "additional"])
def test_gui11_verified_legacy_owner_reads_and_delegates_without_rebinding(tmp_path, selection):
    world = _gui11_legacy_world(tmp_path)
    case = world[selection]
    assert case.owner_principal_id == case.tenant_id == world["owner"].principal_id
    if selection == "additional":
        assert case.case_id != case.tenant_id
        assert case.resource_id != world["legacy"].resource_id
    kind, revision, envelope, payload = _gui11_legacy_artifact(world, case)
    owner_read = world["grants"].read_as_owner(actor_principal_id=world["owner"].principal_id,
        case_id=case.case_id, tenant_id=case.tenant_id, resource_id=case.resource_id,
        artifact_kind=kind, artifact_revision=revision, envelope=envelope,
        owner_session=world["owner_session"], aad_principal_id=case.tenant_id)
    assert owner_read["data"] == payload
    assert owner_read["actor_is_encrypted_owner"] is True
    assert owner_read["actor_principal_id"] == owner_read["canonical_owner_principal_id"]
    membership = _gui11_legacy_accept(world, case)
    grant = _gui11_legacy_issue(world, case, membership, kind, revision)
    assert _gui11_legacy_issue(world, case, membership, kind, revision) == grant
    assert world["grants"].load(grant.key_grant_id) == grant
    assert grant.owner_principal_id == grant.canonical_owner_principal_id == case.tenant_id
    assert grant.public_view()["actor_is_encrypted_owner"] is True
    delegated = _gui11_legacy_read(world, case, membership, grant, kind, revision, envelope)
    assert delegated["data"] == payload
    assert delegated["actor_principal_id"] == world["lawyer"].principal_id
    assert delegated["canonical_owner_principal_id"] == case.tenant_id
    assert delegated["actor_is_encrypted_owner"] is False
    assert delegated["envelope_schema_version"] == 2
    delegated_arguments = dict(actor_principal_id=world["lawyer"].principal_id,
        membership_grant_id=membership.grant_id, membership_version=membership.version,
        key_grant_id=grant.key_grant_id, case_id=case.case_id, tenant_id=case.tenant_id,
        resource_id=case.resource_id, artifact_kind=kind, artifact_revision=revision,
        recipient_session=world["recipient_session"])
    downloaded = world["grants"].download_delegated(**delegated_arguments, envelope=envelope)
    assert downloaded["data"] == payload
    assert downloaded["actor_is_encrypted_owner"] is False
    written = world["grants"].write_delegated(**delegated_arguments, plaintext=b"synthetic-late-write")
    assert written["operation"] == "write"
    assert written["actor_is_encrypted_owner"] is False
    admitted = world["grants"].admit_late_result(**delegated_arguments,
        prepared_generation=grant.generation, envelope=written["envelope"])
    assert admitted["data"] == b"synthetic-late-write"
    assert admitted["actor_is_encrypted_owner"] is False


def test_gui11_legacy_equality_does_not_allow_spoofed_or_cross_case_owners(tmp_path):
    world = _gui11_legacy_world(tmp_path)
    case = world["additional"]
    kind, revision, envelope, _payload = _gui11_legacy_artifact(world, case)
    membership = _gui11_legacy_accept(world, case)
    grant = _gui11_legacy_issue(world, case, membership, kind, revision)
    with pytest.raises(CaseResourceKeyGrantError) as stranger_issue:
        _gui11_legacy_issue(world, case, membership, kind, revision,
            actor_principal_id=world["stranger"].principal_id)
    assert stranger_issue.value.code == "missing_case"
    with pytest.raises(CaseResourceKeyGrantError) as stranger_read:
        world["grants"].read_as_owner(actor_principal_id=world["stranger"].principal_id,
            case_id=case.case_id, tenant_id=case.tenant_id, resource_id=case.resource_id,
            artifact_kind=kind, artifact_revision=revision, envelope=envelope,
            owner_session=world["owner_session"])
    assert stranger_read.value.code == "missing_case"
    with pytest.raises(CaseResourceKeyGrantError) as tenant_recipient:
        _gui11_legacy_issue(world, case, membership, kind, revision,
            recipient_principal_id=world["owner"].principal_id)
    assert tenant_recipient.value.code == "owner_impersonation"
    for changes, code in (({"actor_principal_id": world["owner"].principal_id}, "owner_impersonation"),
            ({"aad_principal_id": world["lawyer"].principal_id}, "owner_impersonation"),
            ({"case_id": world["foreign"].case_id}, "case_mismatch"),
            ({"tenant_id": world["foreign"].tenant_id}, "tenant_mismatch"),
            ({"resource_id": world["foreign"].resource_id}, "case_mismatch")):
        with pytest.raises(CaseResourceKeyGrantError) as denied:
            _gui11_legacy_read(world, case, membership, grant, kind, revision, envelope, **changes)
        assert denied.value.code == code
    # A synthetically authenticated stored record still must name the actual
    # CaseDirectory owner; possession of a key-grant record alone is not proof.
    with world["grants"]._locked():
        world["grants"]._seal(replace(grant, owner_principal_id=world["stranger"].principal_id))
    with pytest.raises(CaseResourceKeyGrantError) as forged_owner:
        _gui11_legacy_read(world, case, membership, grant, kind, revision, envelope)
    assert forged_owner.value.code == "missing_case"


"""Synthetic durable recipient-session and active-DEK regression cases."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest

_gui11_existing_world = _world
_gui11_existing_accept = _accept
_gui11_existing_seal = _seal
_gui11_existing_issue = _issue
from integrations.private_collaboration import CaseResourceKeyGrantError, CaseResourceKeyGrantStore
from integrations.private_storage import (PrivateArtifactBinding, PrivateArtifactBindingError,
    PrivateArtifactIntegrityError, PrivateKeyMaterialError, UserOwnedKeySession,
    open_private_artifact, seal_private_artifact)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _gui11_reopen_grants(world, *, key=None):
    original = world["grants"]
    return CaseResourceKeyGrantStore(original._root, key=original._key if key is None else key,
        key_id=original._key_id, principals=world["principals"], cases=world["cases"],
        memberships=world["memberships"])


def _gui11_read_grant(world, store, session, membership, grant, envelope):
    case = world["case"]
    return store.read_delegated(actor_principal_id=world["lawyer"].principal_id,
        membership_grant_id=membership.grant_id, membership_version=membership.version,
        key_grant_id=grant.key_grant_id, case_id=case.case_id, tenant_id=case.tenant_id,
        resource_id=case.resource_id, artifact_kind="case-note", artifact_revision="3",
        envelope=envelope, recipient_session=session)


def test_gui11_independent_recipient_sessions_preserve_both_persisted_grants(tmp_path):
    world = _gui11_existing_world(tmp_path)
    membership = _gui11_existing_accept(world)
    envelope = _gui11_existing_seal(world)
    second = UserOwnedKeySession(world["recipient_session"].directory)
    second.unlock_passphrase("lawyer-passphrase")
    barrier = threading.Barrier(2)
    def issue(item):
        session, key = item
        barrier.wait(timeout=5)
        return _gui11_existing_issue({**world, "recipient_session": session}, membership, key=key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        grants = list(pool.map(issue, [(world["recipient_session"], "concurrent-a"), (second, "concurrent-b")]))
    assert grants[0].recipient_wrap_key_id == grants[1].recipient_wrap_key_id
    world["recipient_session"].lock()
    second.lock()
    reopened = UserOwnedKeySession(second.directory)
    reopened.unlock_passphrase("lawyer-passphrase")
    store = _gui11_reopen_grants(world)
    for grant in grants:
        assert _gui11_read_grant(world, store, reopened, membership, grant, envelope)["data"] == b"synthetic-case-note"
    before = reopened.path.read_bytes()
    wrong_unlock = UserOwnedKeySession(reopened.directory)
    with pytest.raises(PrivateArtifactIntegrityError):
        wrong_unlock.unlock_passphrase("not-the-passphrase")
    assert not wrong_unlock.unlocked and reopened.path.read_bytes() == before
    wrong_recipient = UserOwnedKeySession(tmp_path / "wrong-recipient")
    wrong_recipient.create(protection="passphrase", passphrase="synthetic-password")
    wrong_recipient.ensure_recipient_wrap_key()
    with pytest.raises(CaseResourceKeyGrantError):
        _gui11_read_grant(world, store, wrong_recipient, membership, grants[0], envelope)
    with pytest.raises(CaseResourceKeyGrantError):
        _gui11_read_grant(world, _gui11_reopen_grants(world, key=os.urandom(32)), reopened, membership, grants[0], envelope)
    assert reopened.path.read_bytes() == before


@pytest.mark.parametrize("operation", ["new_case", "recovery", "rewrap", "destroy_other"])
def test_gui11_stale_read_modify_write_cannot_remove_recipient_wrap(tmp_path, operation):
    world = _gui11_existing_world(tmp_path)
    recipient = world["recipient_session"]
    recipient.ensure_data_key("aux-tenant", "aux-case")
    stale = UserOwnedKeySession(recipient.directory)
    stale.unlock_passphrase("lawyer-passphrase")
    membership = _gui11_existing_accept(world)
    envelope = _gui11_existing_seal(world)
    grant = _gui11_existing_issue(world, membership)
    if operation == "new_case":
        stale.ensure_data_key("another-tenant", "another-case")
    elif operation == "recovery":
        source = UserOwnedKeySession(tmp_path / "recovery-source")
        source.create(protection="passphrase", passphrase="synthetic-password")
        payload = source.export_recovery("recovered-tenant", "recovered-case", "recovery-password")["bytes"]
        stale.import_recovery(payload, tenant_id="recovered-tenant", case_id="recovered-case",
                              recovery_passphrase="recovery-password")
    elif operation == "rewrap":
        stale.rotate_wrapping_key("replacement-passphrase")
    else:
        stale.destroy_case_keys("aux-tenant", "aux-case")
    reopened = UserOwnedKeySession(recipient.directory)
    reopened.unlock_passphrase("replacement-passphrase" if operation == "rewrap" else "lawyer-passphrase")
    assert _gui11_read_grant(world, _gui11_reopen_grants(world), reopened, membership, grant, envelope)["data"] == b"synthetic-case-note"
    assert reopened.recipient_wrap_key()[0] == grant.recipient_wrap_key_id


@pytest.mark.parametrize("alias", ["symlink", "hardlink", "public"])
def test_gui11_shared_keystore_lock_refuses_aliases_and_public_mode(tmp_path, alias):
    session = UserOwnedKeySession(tmp_path / "keys")
    session.create(protection="passphrase", passphrase="synthetic-password")
    before = session.path.read_bytes()
    lock = session.directory / ".keystore.lock"
    if alias == "symlink":
        lock.unlink()
        target = tmp_path / "lock-target"
        target.write_bytes(b"")
        target.chmod(0o600)
        lock.symlink_to(target)
    elif alias == "hardlink":
        os.link(lock, tmp_path / "lock-alias")
    else:
        lock.chmod(0o644)
    with pytest.raises((OSError, PrivateKeyMaterialError)):
        session.ensure_recipient_wrap_key()
    assert session.path.read_bytes() == before


def test_gui11_case_dek_rotation_replays_durably_and_updates_normal_owner_writes(tmp_path):
    world = _gui11_existing_world(tmp_path)
    case = world["case"]
    owner = world["owner_session"]
    membership = _gui11_existing_accept(world)
    _gui11_existing_issue(world, membership)
    binding = PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case.case_id,
        principal_id=case.tenant_id, artifact_kind="case-note", revision="3")
    old_id, old_key = owner.provider().resolve(binding)
    historic = seal_private_artifact(b"historical-owner-data", binding=binding, key=old_key, key_id=old_id)
    other_id = owner.ensure_data_key("unrelated-tenant", "unrelated-case")
    other_binding = PrivateArtifactBinding(tenant_id="unrelated-tenant", case_id="unrelated-case",
        principal_id="unrelated-tenant", artifact_kind="case-note", revision="3")
    other_key_id, other_key = owner.provider().resolve(other_binding)
    other_envelope = seal_private_artifact(b"unrelated-case-data", binding=other_binding,
        key=other_key, key_id=other_key_id)
    stale_owner = UserOwnedKeySession(owner.directory)
    stale_owner.unlock_passphrase("owner-passphrase")
    receipt = owner.rotate_case_grant_data_key(case.tenant_id, case.case_id,
        resource_id=case.resource_id, expected_data_key_id=old_id, operation_id="revoke-stable-operation")
    assert receipt["rotated"] is True and receipt["new_data_key_id"] != old_id
    new_id, new_key = stale_owner.provider().resolve(binding)
    assert new_id == receipt["new_data_key_id"] and new_key != old_key
    future = seal_private_artifact(b"future-owner-data", binding=binding, key=new_key, key_id=new_id)
    with pytest.raises(PrivateArtifactIntegrityError):
        open_private_artifact(future, binding=binding, key=old_key, expected_key_id=new_id)
    assert owner.lookup_data_key(case.tenant_id, case.case_id, old_id) == old_key
    assert open_private_artifact(historic, binding=binding, key=old_key, expected_key_id=old_id) == b"historical-owner-data"
    owner.lock()
    reopened = UserOwnedKeySession(owner.directory)
    reopened.unlock_passphrase("owner-passphrase")
    before = reopened.path.read_bytes()
    replay = reopened.rotate_case_grant_data_key(case.tenant_id, case.case_id,
        resource_id=case.resource_id, expected_data_key_id=old_id, operation_id="revoke-stable-operation")
    assert replay["replayed"] is True and replay["rotated"] is False
    assert replay["new_data_key_id"] == new_id and reopened.path.read_bytes() == before
    assert reopened.ensure_data_key("unrelated-tenant", "unrelated-case") == other_id
    reopened_id, reopened_key = reopened.provider().resolve(binding)
    assert reopened_id == new_id
    assert open_private_artifact(future, binding=binding, key=reopened_key, expected_key_id=new_id) == b"future-owner-data"
    historical_key = reopened.lookup_data_key(case.tenant_id, case.case_id, old_id)
    assert historical_key == old_key
    assert open_private_artifact(historic, binding=binding, key=historical_key, expected_key_id=old_id) == b"historical-owner-data"
    assert reopened.provider().resolve(other_binding) == (other_key_id, other_key)
    assert open_private_artifact(other_envelope, binding=other_binding, key=other_key,
        expected_key_id=other_key_id) == b"unrelated-case-data"
    for changes in ({"operation_id": "different-operation"}, {"resource_id": "forged-resource"},
                    {"expected_data_key_id": new_id}):
        kwargs = {"resource_id": case.resource_id, "expected_data_key_id": old_id,
                  "operation_id": "revoke-stable-operation", **changes}
        with pytest.raises((PrivateKeyMaterialError, PrivateArtifactBindingError)):
            reopened.rotate_case_grant_data_key(case.tenant_id, case.case_id, **kwargs)
        assert reopened.path.read_bytes() == before


def test_gui11_authenticated_refresh_rejects_changed_rotation_receipt(tmp_path):
    session = UserOwnedKeySession(tmp_path / "keys")
    session.create(protection="passphrase", passphrase="synthetic-password")
    old = session.ensure_data_key("tenant", "case")
    session.rotate_case_grant_data_key("tenant", "case", resource_id="resource",
        expected_data_key_id=old, operation_id="durable-operation")
    document = json.loads(session.path.read_text())
    encoded = document["case_grant_state"]
    index = len(encoded) // 2
    document["case_grant_state"] = encoded[:index] + ("A" if encoded[index] != "A" else "B") + encoded[index + 1:]
    session.path.write_text(json.dumps(document))
    before = session.path.read_bytes()
    with pytest.raises(PrivateArtifactIntegrityError):
        session.ensure_data_key("unrelated", "case")
    assert not session.unlocked and session.path.read_bytes() == before
