"""Encrypted local primary plus optional private ciphertext replicas.

Synthetic cases only. Upstream datasets wallet fixtures are a separate
compatibility qualification: a missing fixture is not a pass and does not
replace these assertions. Local private mode does not start remote storage.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from integrations.ipfs_datasets.storage import (
    configure_replica_policy,
    count_verified_ciphertext_replicas,
    publish_encrypted_replicas,
    reconcile_encrypted_replicas,
    remote_storage_activation_count,
    restore_encrypted_replicas,
    select_private_storage_mode,
    upstream_replica_fixture_qualification,
)
from integrations.private_storage import PrivateRevisionError, read_case_manifest

SENTINEL = "SENTINEL-DUR005-complaint-text"
KEY = bytes(range(3, 35))
KEY_ID = "k-replica"
TENANT = "tenant-r"
CASE = "case-r"
PRINCIPAL = "tenant-r"


class RemoteProvider:
    def __init__(self, provider_id: str, *, state: str = "verified", digest: str = "match", version: str = "match", body: str = "match") -> None:
        self.provider_id = provider_id
        self.state = state
        self.digest = digest
        self.version = version
        self.body = body
        self.objects: dict[str, bytes] = {}
        self.puts = 0
        self.gets = 0

    def put(self, name: str, data: bytes, *, digest: str, version: str) -> dict[str, str]:
        self.puts += 1
        if self.state == "unavailable":
            raise TimeoutError("provider_unavailable")
        stored = data if self.body == "match" else b"\x00" + data
        self.objects[name] = stored
        return {
            "state": self.state,
            "digest": digest if self.digest == "match" else "0" * 64,
            "version": version if self.version == "match" else "stale-version",
        }

    def get(self, name: str) -> bytes:
        self.gets += 1
        return self.objects[name]


def _artifacts() -> dict:
    return {
        "answer": {"body": f"complaint:{SENTINEL}".encode(), "revision": "answer-1"},
        "fact_graph": {"body": b"graph:retaliation-node", "revision": "graph-1"},
        "legal_rule_source": {"body": b"rule:protected-activity", "revision": "rule-1"},
        "evaluation": {"body": b"eval:supported", "revision": "eval-1"},
        "proof": {"body": b"proof:revision-1", "revision": "proof-1"},
    }


def _publish(root: Path, policy, providers=(), clock=None):
    return publish_encrypted_replicas(
        root,
        policy=policy,
        providers=providers,
        clock=clock,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        key=KEY,
        key_id=KEY_ID,
        expected_head="",
        expected_hash="",
        artifacts=_artifacts(),
        private_names={"filename": f"{SENTINEL}.txt", "labels": [SENTINEL]},
    )


def _open(root: Path, *, key: bytes = KEY):
    return read_case_manifest(
        root,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        key=key,
        key_id=KEY_ID,
    )


def test_import_and_local_private_mode_do_not_start_remote_storage(tmp_path: Path) -> None:
    before = remote_storage_activation_count()
    policy = select_private_storage_mode("local_private")
    remote = RemoteProvider("should-not-start")
    receipt = _publish(tmp_path / "local", policy, providers=(remote,))
    assert remote.puts == 0 and remote.gets == 0
    assert receipt["mode"] == "local_private"
    assert receipt["network_sharing_started"] is False
    assert receipt["verified_replicas"] == 1
    assert receipt["synchronous_wait_seconds"] == 0
    assert remote_storage_activation_count() == before
    opened = _open(tmp_path / "local")
    assert opened["roles"]["answer"] == f"complaint:{SENTINEL}".encode()


def test_replicas_count_only_after_digest_and_version_readback(tmp_path: Path) -> None:
    policy = configure_replica_policy(desired=2, minimum=1, mode="private_remote")
    good = RemoteProvider("remote-good")
    queued = RemoteProvider("remote-queued", state="queued")
    deferred = RemoteProvider("remote-deferred", state="deferred")
    offline = RemoteProvider("remote-offline", state="offline")
    stale = RemoteProvider("remote-stale", version="stale")
    flipped = RemoteProvider("remote-flipped", body="flip")
    receipt = _publish(
        tmp_path / "counted",
        policy,
        providers=(good, queued, deferred, offline, stale, flipped),
        clock=lambda: 1_700_000_000.0,
    )
    assert receipt["verified_providers"] == ["local-primary", "remote-good"]
    assert receipt["verified_replicas"] == 2
    assert receipt["meets_minimum"] is True
    assert receipt["meets_desired"] is True
    assert {item["state"] for item in receipt["uncounted"]} >= {"queued", "deferred", "offline", "verified"}
    assert all(item["provider_id"] != "remote-good" for item in receipt["uncounted"])
    assert queued.gets == 0 and deferred.gets == 0 and offline.gets == 0
    assert good.gets > 0
    blob = next(iter(good.objects.values()))
    assert SENTINEL.encode() not in blob
    assert SENTINEL not in json.dumps(receipt)
    direct = count_verified_ciphertext_replicas([
        {"provider_id": "local-primary", "state": "verified", "digest_match": True, "version_match": True},
        {"provider_id": "queued", "state": "queued", "digest_match": True, "version_match": True},
        {"provider_id": "deferred", "state": "deferred", "digest_match": True, "version_match": True},
        {"provider_id": "offline", "state": "offline", "digest_match": True, "version_match": True},
        {"provider_id": "bad-digest", "state": "verified", "digest_match": False, "version_match": True},
        {"provider_id": "bad-version", "state": "verified", "digest_match": True, "version_match": False},
    ])
    assert direct["verified_replicas"] == 1
    assert direct["verified_providers"] == ["local-primary"]


def test_restart_and_primary_loss_restore_complaint_graph_and_proof(tmp_path: Path) -> None:
    root = tmp_path / "restore"
    policy = configure_replica_policy(desired=2, minimum=1, mode="private_remote")
    remote = RemoteProvider("remote-a")
    receipt = _publish(root, policy, providers=(remote,), clock=lambda: 100.0)
    reopened = _open(root)
    assert reopened["roles"]["answer"] == f"complaint:{SENTINEL}".encode()
    assert reopened["roles"]["fact_graph"] == b"graph:retaliation-node"
    assert reopened["roles"]["proof"] == b"proof:revision-1"
    case_root = root / "case-manifest"
    shutil.rmtree(case_root / "o")
    (case_root / "case-head").unlink()
    (case_root / "generations").unlink()
    assert _open(root) is None
    restored = restore_encrypted_replicas(
        root,
        receipt,
        providers=(remote,),
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        key=KEY,
        key_id=KEY_ID,
    )
    assert restored["roles"]["answer"] == reopened["roles"]["answer"]
    assert restored["roles"]["fact_graph"] == reopened["roles"]["fact_graph"]
    assert restored["roles"]["proof"] == reopened["roles"]["proof"]
    assert restored["generation"] == receipt["generation"]
    with pytest.raises(PrivateRevisionError):
        restore_encrypted_replicas(
            tmp_path / "wrong-key",
            receipt,
            providers=(remote,),
            tenant_id=TENANT,
            case_id=CASE,
            principal_id=PRINCIPAL,
            key=bytes(range(32)),
            key_id=KEY_ID,
        )


def test_unavailable_provider_reconciles_without_synchronous_wait(tmp_path: Path) -> None:
    root = tmp_path / "retry"
    policy = configure_replica_policy(
        desired=2,
        minimum=1,
        mode="private_remote",
        max_attempts=3,
        base_backoff_seconds=3600,
        max_backoff_seconds=86400,
    )
    remote = RemoteProvider("remote-down", state="unavailable")
    now = {"value": 1_000.0}
    receipt = _publish(root, policy, providers=(remote,), clock=lambda: now["value"])
    assert receipt["status"] == "reconciliation_required"
    assert receipt["verified_replicas"] == 1
    assert receipt["waited"] is False
    assert receipt["synchronous_wait_seconds"] == 0
    pending = receipt["unavailable_providers"][0]
    assert pending["provider_id"] == "remote-down"
    assert pending["error_category"] == "unavailable"
    assert pending["attempts"] == 1
    assert pending["next_retry_at"] == 1_000.0 + 3600
    early = reconcile_encrypted_replicas(
        root, receipt, policy=policy, providers=(remote,), clock=lambda: 1_000.0 + 10,
    )
    assert remote.puts == 1
    assert early["unavailable_providers"][0]["attempts"] == 1
    assert early["unavailable_providers"][0]["next_retry_at"] == pending["next_retry_at"]
    remote.state = "verified"
    due = reconcile_encrypted_replicas(
        root, early, policy=policy, providers=(remote,), clock=lambda: pending["next_retry_at"],
    )
    assert remote.puts > 1
    assert due["verified_replicas"] == 2
    assert due["unavailable_providers"] == []
    assert due["meets_desired"] is True
    assert due["waited"] is False


def test_policy_bounds_and_upstream_qualification_stays_separate(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        configure_replica_policy(desired=1, minimum=2, mode="local_private")
    with pytest.raises(ValueError):
        select_private_storage_mode("private_remote")
    first_party = _publish(
        tmp_path / "first",
        configure_replica_policy(desired=1, minimum=1, mode="local_private"),
    )
    assert first_party["verified_replicas"] == 1
    qualification = upstream_replica_fixture_qualification()
    assert qualification["substitutes_first_party"] is False
    assert qualification["intended_environment"] == "ipfs_datasets_py"
    by_suite = {item["suite"]: item for item in qualification["suites"]}
    missing = by_suite["tests/unit/test_wallet_storage_replicas_optional.py"]
    assert missing["status"] == "missing"
    assert missing["passed"] is False
    assert missing["counts_as_passed"] is False
    present = by_suite["tests/unit/test_wallet_storage_factory.py"]
    assert present["status"] in {"passed", "failed", "missing"}
    if present["status"] != "passed":
        assert present["passed"] is False
        assert present["counts_as_passed"] is False
    assert _open(tmp_path / "first")["roles"]["proof"] == b"proof:revision-1"


def test_authenticated_old_frame_cannot_replace_committed_generation(tmp_path):
    from integrations import private_storage as api

    root = tmp_path / "case"
    options = dict(tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
                   key=KEY, key_id=KEY_ID)
    policy = api.replica_policy(desired_replicas=1, minimum_replicas=1)
    def publish(revision, suffix):
        return api.publish_encrypted_replicas(
            root, **options, policy=policy, revision=revision,
            complaint=b"synthetic complaint " + suffix,
            fact_graph=b"synthetic graph " + suffix, proof=b"synthetic proof " + suffix)
    publish("r1", b"one")
    primary = root / "replica-ledger" / "primary.frame"
    old_frame = primary.read_bytes()
    publish("r2", b"two")
    primary.write_bytes(old_frame)
    with pytest.raises(api.PrivateStorageError):
        api.restore_encrypted_workspace(root, **options)


def test_remote_restore_cannot_overwrite_newer_publication(tmp_path):
    import threading
    from integrations import private_storage as api

    entered, release = threading.Event(), threading.Event()
    class Provider:
        blocked = False
        frames = {}
        def place(self, *, digest, version, frame, **_deadline):
            self.frames[digest] = frame
            return {"status": "stored"}
        def readback(self, *, digest, version, **_deadline):
            if self.blocked:
                entered.set()
                assert release.wait(2)
            return {"status": "available", "frame": self.frames[digest], "version": version}
    provider = Provider()
    root = tmp_path / "case"
    options = dict(tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
                   key=KEY, key_id=KEY_ID)
    first = (b"synthetic complaint one", b"synthetic graph one", b"synthetic proof one")
    following = (b"synthetic complaint two", b"synthetic graph two", b"synthetic proof two")
    api.publish_encrypted_replicas(
        root, **options, policy=api.replica_policy(desired_replicas=2, minimum_replicas=1, mode="private_remote"),
        revision="r1", complaint=first[0], fact_graph=first[1], proof=first[2],
        providers={"fixture": provider}, timeout_seconds=1)
    (root / "replica-ledger" / "primary.frame").unlink()
    provider.blocked = True
    errors = []
    def restore_old():
        try:
            api.restore_encrypted_workspace(root, **options, providers={"fixture": provider}, timeout_seconds=1)
        except api.PrivateStorageError as error:
            errors.append(error.code)
    worker = threading.Thread(target=restore_old)
    worker.start()
    try:
        assert entered.wait(1)
        api.publish_encrypted_replicas(
            root, **options, policy=api.replica_policy(desired_replicas=1, minimum_replicas=1),
            revision="r2", complaint=following[0], fact_graph=following[1], proof=following[2])
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert errors == ["revision_conflict"]
    restored = api.restore_encrypted_workspace(root, **options)
    assert restored["revision"] == "r2"
    assert tuple(restored[name] for name in ("complaint", "fact_graph", "proof")) == following
