"""Revocation and rotation of collaborative case key grants.

Positive cases recheck an active grant on read, write, download, and late-result
admission, then re-wrap a surviving grant above the cutoff. Negative cases show
that a revoked generation fails those same entries, including after a cold store
and a freshly unlocked session. Already downloaded plaintext and a copied wrap
remain usable outside the store, and the revocation result says so.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import (
    LIMITATIONS,
    CaseResourceKeyGrantError,
    CaseResourceKeyGrantStore,
)
from integrations.private_storage import (
    PrivateArtifactBinding,
    UserOwnedKeySession,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ARTIFACT_KIND = "case-note"
REVISION = "4"
ACTIONS = {"case.read", "case.download", "case.message.send"}


def _world(tmp_path: Path):
    store_key = os.urandom(32)
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    counsel = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
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
        key=store_key,
        key_id="resource-grant-key",
        principals=principals,
        cases=cases,
        memberships=memberships,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    lawyer_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    lawyer_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    counsel_session = UserOwnedKeySession(tmp_path / "counsel-keys")
    counsel_session.create(protection="passphrase", passphrase="counsel-passphrase")
    owner_session.ensure_data_key(case.tenant_id, case.case_id)
    return {
        "root": tmp_path,
        "store_key": store_key,
        "principals": principals,
        "cases": cases,
        "memberships": memberships,
        "grants": grants,
        "owner": owner,
        "lawyer": lawyer,
        "counsel": counsel,
        "admin": admin,
        "case": case,
        "owner_session": owner_session,
        "lawyer_session": lawyer_session,
        "counsel_session": counsel_session,
    }


def _accept(world, member, session_name: str, key: str):
    case = world["case"]
    pending = world["memberships"].invite(
        owner_principal_id=world["owner"].principal_id,
        member_principal_id=member.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=set(ACTIONS),
        expires_at=1_700_003_600,
        expected_case_revision=case.revision,
        idempotency_key=key,
    )
    accepted = world["memberships"].accept(
        member_principal_id=member.principal_id,
        grant_id=pending.grant_id,
        expected_version=pending.version,
        idempotency_key=key + "-accept",
    )
    granted = world["grants"].issue(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=member.principal_id,
        membership_grant_id=accepted.grant_id,
        membership_version=accepted.version,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION,
        owner_session=world["owner_session"],
        recipient_session=world[session_name],
        idempotency_key=key + "-grant",
    )
    return accepted, granted


def _seal(world, payload: bytes) -> bytes:
    case = world["case"]
    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=REVISION,
        principal_id=case.tenant_id,
    )
    key_id, key = world["owner_session"].provider().resolve(binding)
    from integrations.private_storage import seal_private_artifact

    return seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)


def _delegated(world, member, membership, grant, session_name: str):
    case = world["case"]
    return {
        "actor_principal_id": member.principal_id,
        "membership_grant_id": membership.grant_id,
        "membership_version": membership.version,
        "key_grant_id": grant.key_grant_id,
        "case_id": case.case_id,
        "tenant_id": case.tenant_id,
        "resource_id": case.resource_id,
        "artifact_kind": ARTIFACT_KIND,
        "artifact_revision": REVISION,
        "recipient_session": world[session_name],
    }


def _resume(world) -> CaseResourceKeyGrantStore:
    return CaseResourceKeyGrantStore(
        world["root"] / "key-grants",
        key=world["store_key"],
        key_id="resource-grant-key",
        principals=world["principals"],
        cases=world["cases"],
        memberships=world["memberships"],
    )


def test_active_grant_is_rechecked_then_revoked_under_cutoff(tmp_path: Path) -> None:
    world = _world(tmp_path)
    payload = b"synthetic-collaboration-note"
    envelope = _seal(world, payload)
    lawyer_membership, lawyer_grant = _accept(world, world["lawyer"], "lawyer_session", "lawyer")
    counsel_membership, counsel_grant = _accept(world, world["counsel"], "counsel_session", "counsel")
    assert lawyer_grant.generation == 1
    assert lawyer_grant.status == "active"
    assert counsel_grant.generation == 1
    copied_wrap = {"nonce": lawyer_grant.wrapped_nonce, "ciphertext": lawyer_grant.wrapped_ciphertext}
    lawyer_args = _delegated(world, world["lawyer"], lawyer_membership, lawyer_grant, "lawyer_session")
    counsel_args = _delegated(world, world["counsel"], counsel_membership, counsel_grant, "counsel_session")

    opened = world["grants"].read_delegated(envelope=envelope, **lawyer_args)
    assert opened["data"] == payload
    assert opened["operation"] == "read"
    assert opened["generation"] == 1
    assert LIMITATIONS[0] in opened["limitations"]

    written = world["grants"].write_delegated(plaintext=payload, **lawyer_args)
    assert written["operation"] == "write"
    assert written["envelope"] != envelope
    downloaded = world["grants"].download_delegated(envelope=envelope, **lawyer_args)
    assert downloaded["data"] == payload
    assert downloaded["downloaded_plaintext_erased"] is False
    admitted = world["grants"].admit_late_result(envelope=envelope, prepared_generation=1, **lawyer_args)
    assert admitted["data"] == payload
    assert admitted["operation"] == "late_result"

    with pytest.raises(CaseResourceKeyGrantError) as low_cutoff:
        world["grants"].revoke_and_rotate(
            actor_principal_id=world["owner"].principal_id,
            recipient_principal_id=world["lawyer"].principal_id,
            case_id=world["case"].case_id,
            tenant_id=world["case"].tenant_id,
            resource_id=world["case"].resource_id,
            cutoff=0,
            owner_session=world["owner_session"],
            recipient_sessions={world["counsel"].principal_id: world["counsel_session"]},
            idempotency_key="revoke-lawyer",
        )
    assert low_cutoff.value.code == "cutoff_invalid"

    with pytest.raises(CaseResourceKeyGrantError) as stranger:
        world["grants"].revoke_and_rotate(
            actor_principal_id=world["lawyer"].principal_id,
            recipient_principal_id=world["counsel"].principal_id,
            case_id=world["case"].case_id,
            tenant_id=world["case"].tenant_id,
            resource_id=world["case"].resource_id,
            cutoff=1,
            owner_session=world["owner_session"],
            recipient_sessions={},
            idempotency_key="lawyer-cannot-revoke",
        )
    assert stranger.value.code == "missing_case"

    with pytest.raises(CaseResourceKeyGrantError) as admin:
        world["grants"].revoke_and_rotate(
            actor_principal_id=world["admin"].principal_id,
            recipient_principal_id=world["lawyer"].principal_id,
            case_id=world["case"].case_id,
            tenant_id=world["case"].tenant_id,
            resource_id=world["case"].resource_id,
            cutoff=1,
            owner_session=world["owner_session"],
            idempotency_key="admin-revoke",
        )
    assert admin.value.code == "admin_cannot_decrypt"

    retained_key = world["lawyer_session"].unwrap_granted_resource_key(
        copied_wrap,
        tenant_id=lawyer_grant.tenant_id,
        case_id=lawyer_grant.case_id,
        canonical_principal_id=lawyer_grant.canonical_owner_principal_id,
        revision=lawyer_grant.artifact_revision,
        recipient_principal_id=lawyer_grant.recipient_principal_id,
        artifact_kind=lawyer_grant.artifact_kind,
        resource_id=lawyer_grant.resource_id,
        membership_grant_id=lawyer_grant.membership_grant_id,
        membership_version=lawyer_grant.membership_version,
        data_key_id=lawyer_grant.data_key_id,
        recipient_wrap_key_id=lawyer_grant.recipient_wrap_key_id,
    )
    revoked = world["grants"].revoke_and_rotate(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        case_id=world["case"].case_id,
        tenant_id=world["case"].tenant_id,
        resource_id=world["case"].resource_id,
        cutoff=1,
        owner_session=world["owner_session"],
        recipient_sessions={world["counsel"].principal_id: world["counsel_session"]},
        idempotency_key="revoke-lawyer",
        retained_plaintext=downloaded["data"],
        retained_key=retained_key,
    )
    assert revoked["cutoff"] == 1
    assert revoked["generation"] == 2
    assert revoked["grant_wrap_rotated"] is True
    assert revoked["future_access_revoked"] is True
    assert revoked["downloaded_plaintext_erased"] is False
    assert revoked["downloaded_keys_erased"] is False
    assert revoked["limitation"] == "revocation_cannot_erase_already_downloaded_plaintext_or_keys"
    assert downloaded["data"] == payload
    assert len(retained_key) == 32
    again = world["grants"].revoke_and_rotate(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        case_id=world["case"].case_id,
        tenant_id=world["case"].tenant_id,
        resource_id=world["case"].resource_id,
        cutoff=1,
        owner_session=world["owner_session"],
        recipient_sessions={world["counsel"].principal_id: world["counsel_session"]},
        idempotency_key="revoke-lawyer",
    )
    assert again["generation"] == 2
    assert again["revoked_key_grant_ids"] == revoked["revoked_key_grant_ids"]

    stored = world["grants"].load(lawyer_grant.key_grant_id)
    assert stored.status == "revoked"
    assert stored.wrapped_ciphertext == ""
    assert stored.generation == 1
    survived = world["grants"].load(counsel_grant.key_grant_id)
    assert survived.status == "active"
    assert survived.generation == 2
    assert survived.wrapped_ciphertext != counsel_grant.wrapped_ciphertext

    for call in (
        lambda: world["grants"].read_delegated(envelope=envelope, **lawyer_args),
        lambda: world["grants"].write_delegated(plaintext=payload, **lawyer_args),
        lambda: world["grants"].download_delegated(envelope=envelope, **lawyer_args),
    ):
        with pytest.raises(CaseResourceKeyGrantError) as denied:
            call()
        assert denied.value.code == "grant_revoked"
    with pytest.raises(CaseResourceKeyGrantError) as late:
        world["grants"].admit_late_result(envelope=envelope, prepared_generation=1, **lawyer_args)
    assert late.value.code == "late_result_after_cutoff"

    counsel_open = world["grants"].download_delegated(envelope=envelope, **counsel_args)
    assert counsel_open["data"] == payload
    assert counsel_open["generation"] == 2
    counsel_late = world["grants"].admit_late_result(
        envelope=envelope,
        prepared_generation=2,
        **counsel_args,
    )
    assert counsel_late["data"] == payload
    with pytest.raises(CaseResourceKeyGrantError) as stale:
        world["grants"].admit_late_result(envelope=envelope, prepared_generation=1, **counsel_args)
    assert stale.value.code == "late_result_after_cutoff"

    resumed = _resume(world)
    stale_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    stale_session.unlock_passphrase("lawyer-passphrase")
    lawyer_args["recipient_session"] = stale_session
    with pytest.raises(CaseResourceKeyGrantError) as cold:
        resumed.download_delegated(envelope=envelope, **lawyer_args)
    assert cold.value.code == "grant_revoked"
    with pytest.raises(CaseResourceKeyGrantError) as replay:
        resumed.issue(
            actor_principal_id=world["owner"].principal_id,
            recipient_principal_id=world["lawyer"].principal_id,
            membership_grant_id=lawyer_membership.grant_id,
            membership_version=lawyer_membership.version,
            case_id=world["case"].case_id,
            resource_id=world["case"].resource_id,
            tenant_id=world["case"].tenant_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            owner_session=world["owner_session"],
            recipient_session=stale_session,
            idempotency_key="lawyer-grant",
        )
    assert replay.value.code == "grant_revoked"

    still_unwraps = stale_session.unwrap_granted_resource_key(
        copied_wrap,
        tenant_id=lawyer_grant.tenant_id,
        case_id=lawyer_grant.case_id,
        canonical_principal_id=lawyer_grant.canonical_owner_principal_id,
        revision=lawyer_grant.artifact_revision,
        recipient_principal_id=lawyer_grant.recipient_principal_id,
        artifact_kind=lawyer_grant.artifact_kind,
        resource_id=lawyer_grant.resource_id,
        membership_grant_id=lawyer_grant.membership_grant_id,
        membership_version=lawyer_grant.membership_version,
        data_key_id=lawyer_grant.data_key_id,
        recipient_wrap_key_id=lawyer_grant.recipient_wrap_key_id,
    )
    assert still_unwraps == retained_key
    assert downloaded["data"] == payload



def _binding(world):
    case = world["case"]
    return PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND, revision=REVISION, principal_id=case.tenant_id)


def _revoke_arguments(world):
    case = world["case"]
    return dict(actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id, case_id=case.case_id,
        tenant_id=case.tenant_id, resource_id=case.resource_id, cutoff=1,
        owner_session=world["owner_session"],
        recipient_sessions={world["counsel"].principal_id: world["counsel_session"]},
        idempotency_key="exact-resource-cutoff-operation")


def _retained_key(world, grant):
    return world["lawyer_session"].unwrap_granted_resource_key(
        {"nonce": grant.wrapped_nonce, "ciphertext": grant.wrapped_ciphertext},
        tenant_id=grant.tenant_id, case_id=grant.case_id,
        canonical_principal_id=grant.canonical_owner_principal_id, revision=grant.artifact_revision,
        recipient_principal_id=grant.recipient_principal_id, artifact_kind=grant.artifact_kind,
        resource_id=grant.resource_id, membership_grant_id=grant.membership_grant_id,
        membership_version=grant.membership_version, data_key_id=grant.data_key_id,
        recipient_wrap_key_id=grant.recipient_wrap_key_id)


def test_fresh_dek_protects_future_owner_and_survivor_writes_but_preserves_history(tmp_path):
    from integrations.private_storage import (open_private_artifact, parse_private_envelope,
                                               seal_private_artifact, PrivateArtifactIntegrityError)
    world = _world(tmp_path)
    historical = _seal(world, b"historical-note")
    member, revoked = _accept(world, world["lawyer"], "lawyer_session", "revoked")
    survivor_member, survivor = _accept(world, world["counsel"], "counsel_session", "survivor")
    old_key = _retained_key(world, revoked)
    # Keep an unlocked owner session/provider from before the cutoff.
    stale_owner = UserOwnedKeySession(tmp_path / "owner-keys")
    stale_owner.unlock_passphrase("owner-passphrase")
    retained_provider = stale_owner.provider()
    summary = world["grants"].revoke_and_rotate(**_revoke_arguments(world))
    assert summary["data_key_rotated"] is True
    assert summary["previous_data_key_id"] == revoked.data_key_id
    assert summary["data_key_id"] != revoked.data_key_id
    current = world["grants"].load(survivor.key_grant_id)
    assert current.data_key_id == summary["data_key_id"]
    assert current.generation == 2
    args = _delegated(world, world["counsel"], survivor_member, survivor, "counsel_session")
    binding = _binding(world)
    owner_key_id, owner_key = retained_provider.resolve(binding)
    assert owner_key_id == summary["data_key_id"]
    assert owner_key != old_key
    owner_future = seal_private_artifact(b"future-owner-note", binding=binding, key=owner_key, key_id=owner_key_id)
    delegated_future = world["grants"].write_delegated(plaintext=b"future-survivor-note", **args)["envelope"]
    for envelope in (owner_future, delegated_future):
        key_id = parse_private_envelope(envelope)["key_id"]
        assert key_id == owner_key_id
        # Match the authenticated new key-id deliberately: this must fail AES
        # authentication with old key bytes, rather than only a header check.
        with pytest.raises(PrivateArtifactIntegrityError, match="authentication_failed"):
            open_private_artifact(envelope, binding=binding, key=old_key, expected_key_id=key_id)
    assert world["grants"].read_delegated(envelope=owner_future, **args)["data"] == b"future-owner-note"
    assert world["grants"].download_delegated(envelope=delegated_future, **args)["data"] == b"future-survivor-note"
    assert world["grants"].read_delegated(envelope=historical, **args)["data"] == b"historical-note"
    assert world["grants"].read_as_owner(actor_principal_id=world["owner"].principal_id,
        case_id=world["case"].case_id, tenant_id=world["case"].tenant_id,
        resource_id=world["case"].resource_id, artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION, envelope=historical, owner_session=stale_owner)["data"] == b"historical-note"
    assert open_private_artifact(historical, binding=binding, key=old_key) == b"historical-note"
    assert summary["downloaded_plaintext_erased"] is summary["downloaded_keys_erased"] is False
    # A cold store/session still has the same new epoch and authenticated history.
    resumed = _resume(world)
    fresh_counsel = UserOwnedKeySession(tmp_path / "counsel-keys")
    fresh_counsel.unlock_passphrase("counsel-passphrase")
    args["recipient_session"] = fresh_counsel
    assert resumed.read_delegated(envelope=historical, **args)["data"] == b"historical-note"
    assert resumed.read_delegated(envelope=owner_future, **args)["data"] == b"future-owner-note"


@pytest.mark.parametrize("operation", ["read", "write", "download", "late_result"])
@pytest.mark.parametrize("change", ["key_cutoff", "membership_remove", "membership_renew"])
def test_completed_crypto_must_recheck_actual_cutoff_and_membership_before_admission(tmp_path, monkeypatch, operation, change):
    import threading
    from integrations import private_collaboration as module
    world = _world(tmp_path)
    envelope = _seal(world, b"prepared-private-result")
    membership, grant = _accept(world, world["lawyer"], "lawyer_session", "lawyer")
    args = _delegated(world, world["lawyer"], membership, grant, "lawyer_session")
    entered, release = threading.Event(), threading.Event()
    outcome = []
    actual_name = "seal_private_artifact" if operation == "write" else "open_private_artifact"
    actual = getattr(module, actual_name)
    worker = None
    def pause_after_actual_crypto(*values, **options):
        result = actual(*values, **options)
        if threading.current_thread() is worker and options["binding"].artifact_kind == ARTIFACT_KIND:
            entered.set()
            if not release.wait(10):
                raise AssertionError("bounded crypto interleaving expired")
        return result
    monkeypatch.setattr(module, actual_name, pause_after_actual_crypto)
    def run():
        try:
            store = _resume(world)
            if operation == "write":
                value = store.write_delegated(plaintext=b"prepared-write", **args)
            elif operation == "late_result":
                value = store.admit_late_result(envelope=envelope, prepared_generation=1, **args)
            elif operation == "download":
                value = store.download_delegated(envelope=envelope, **args)
            else:
                value = store.read_delegated(envelope=envelope, **args)
            outcome.append(value)
        except BaseException as exc:
            outcome.append(exc)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        assert entered.wait(10), "the actual crypto operation never reached the admission barrier"
        if change == "key_cutoff":
            summary = world["grants"].revoke_and_rotate(**_revoke_arguments(world))
            assert summary["generation"] == 2
        elif change == "membership_remove":
            removed = world["memberships"].remove(owner_principal_id=world["owner"].principal_id,
                grant_id=membership.grant_id, expected_version=membership.version)
            assert removed.status == "removed"
        else:
            renewed = world["memberships"].update_scope(owner_principal_id=world["owner"].principal_id,
                grant_id=membership.grant_id, expected_version=membership.version,
                expires_at=1_700_007_200)
            assert renewed.version == membership.version + 1
    finally:
        release.set()
        worker.join(12)
    assert not worker.is_alive(), "owned admission worker did not terminate"
    assert len(outcome) == 1 and isinstance(outcome[0], CaseResourceKeyGrantError), "stale prepared data was admitted"
    if change == "key_cutoff":
        expected = "late_result_after_cutoff" if operation == "late_result" else "grant_revoked"
    else:
        expected = "membership_removed" if change == "membership_remove" else "revision_conflict"
    assert outcome[0].code == expected


@pytest.mark.parametrize("failure_point", ["after_keystore", "after_first_grant", "before_replay_sidecar"])
def test_interrupted_cross_store_rotation_reopens_and_resumes_same_dek(tmp_path, monkeypatch, failure_point):
    world = _world(tmp_path)
    membership, grant = _accept(world, world["lawyer"], "lawyer_session", "lawyer")
    survivor_membership, survivor = _accept(world, world["counsel"], "counsel_session", "counsel")
    envelope = _seal(world, b"historical-before-cutoff")
    request = _revoke_arguments(world)
    actual = world["owner_session"].rotate_case_grant_data_key
    committed = []
    def fail_after_keystore(*args, **kwargs):
        value = actual(*args, **kwargs)
        committed.append(value)
        if failure_point == "after_keystore":
            raise OSError("injected_rotation_interruption")
        return value
    monkeypatch.setattr(world["owner_session"], "rotate_case_grant_data_key", fail_after_keystore)
    actual_seal = world["grants"]._seal
    def fail_after_first_grant(value):
        actual_seal(value)
        raise OSError("injected_rotation_interruption")
    if failure_point == "after_first_grant":
        monkeypatch.setattr(world["grants"], "_seal", fail_after_first_grant)
    if failure_point == "before_replay_sidecar":
        def fail_replay(*args):
            raise OSError("injected_rotation_interruption")
        monkeypatch.setattr(world["grants"], "_write_revoke_replay", fail_replay)
    with pytest.raises(OSError, match="injected_rotation_interruption"):
        world["grants"].revoke_and_rotate(**request)
    assert len(committed) == 1 and committed[0]["new_data_key_id"] != grant.data_key_id
    resumed = _resume(world)
    revoked_args = _delegated(world, world["lawyer"], membership, grant, "lawyer_session")
    for call in (lambda: resumed.read_delegated(envelope=envelope, **revoked_args),
                 lambda: resumed.write_delegated(plaintext=b"blocked", **revoked_args)):
        expected = "grant_revoked" if failure_point == "before_replay_sidecar" else "case_key_rotation_incomplete"
        with pytest.raises(CaseResourceKeyGrantError, match=expected):
            call()
    reopened_owner = UserOwnedKeySession(tmp_path / "owner-keys")
    reopened_owner.unlock_passphrase("owner-passphrase")
    request["owner_session"] = reopened_owner
    completed = resumed.revoke_and_rotate(**request)
    assert completed["data_key_id"] == committed[0]["new_data_key_id"]
    assert completed["previous_data_key_id"] == grant.data_key_id
    assert completed["generation"] == 2
    assert resumed.revoke_and_rotate(**request)["data_key_id"] == completed["data_key_id"]
    args = _delegated(world, world["counsel"], survivor_membership, survivor, "counsel_session")
    assert resumed.read_delegated(envelope=envelope, **args)["data"] == b"historical-before-cutoff"
    with pytest.raises(CaseResourceKeyGrantError, match="grant_revoked"):
        resumed.download_delegated(envelope=envelope, **revoked_args)
