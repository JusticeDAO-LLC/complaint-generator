"""Encrypted replica durability and restore bindings.

Synthetic private fixtures only. A replica counts after authenticated
ciphertext readback matches the current object, key, case, and version.
Acknowledgements, local CIDs, and fixture providers are labeled and do not
become durability by themselves. Offline, corrupt, stale, and partial copies
leave the local commit in place. Live durability is a separate qualification
and is not executed here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService
from integrations.ipfs_datasets.storage import (
    configure_replica_policy,
    count_verified_ciphertext_replicas,
    label_ciphertext_replica_observations,
    publish_encrypted_replicas,
    reconcile_encrypted_replicas,
    restore_encrypted_replicas,
    restore_encrypted_workspace,
    select_private_storage_mode,
    upstream_replication_fixture_qualification,
)
from integrations.private_storage import PrivateRevisionError, PrivateStorageError
from tests.mgnd_fixtures import CASE_LABELS, PASSPHRASE, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-mgnd-35"
_KEY_ID = "mgnd35-replica-key"


def _key(case_id: str) -> bytes:
    return hashlib.sha256(b"mgnd35-key\x00" + case_id.encode()).digest()


def _artifacts(case) -> dict:
    text = case.narrative.text.encode("utf-8")
    return {
        "answer": {"body": b"complaint:" + text, "revision": "answer-" + case.label},
        "fact_graph": {"body": b"graph:" + case.label.encode(), "revision": "graph-" + case.label},
        "legal_rule_source": {"body": b"rule:" + case.case_id.encode(), "revision": "rule-" + case.label},
        "evaluation": {"body": b"eval:" + case.label.encode(), "revision": "eval-" + case.label},
        "proof": {"body": b"proof:" + case.label.encode(), "revision": "proof-" + case.label},
    }


class CiphertextDirectory:
    """Owned directory of ciphertext. This is a fixture, not a live provider."""

    def __init__(self, root: Path, provider_id: str, *, mode: str = "verified") -> None:
        self.root = root
        self.provider_id = provider_id
        self.mode = mode
        self.fixture_provider = True
        self.provider_class = "fixture"
        self.puts = 0
        self.gets = 0
        root.mkdir(parents=True, exist_ok=True)

    def put(self, name: str, data: bytes, *, digest: str, version: str) -> dict[str, str]:
        self.puts += 1
        if self.mode == "unavailable":
            raise TimeoutError("provider_unavailable")
        if self.mode == "partial" and name != "case-head":
            raise TimeoutError("partial_object")
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = b"\x00" + data if self.mode == "corrupt" else data
        path.write_bytes(stored)
        state = "queued" if self.mode == "queued" else "verified"
        returned_digest = "0" * 64 if self.mode == "acknowledgement" else digest
        returned_version = "stale-version" if self.mode == "stale" else version
        receipt = {"state": state, "digest": returned_digest, "version": returned_version}
        if self.mode == "local_cid":
            receipt["cid"] = "bafy" + "ab" * 20
        return receipt

    def get(self, name: str) -> bytes:
        self.gets += 1
        if self.mode == "local_cid":
            return b"local-cid-without-ciphertext"
        payload = (self.root / name).read_bytes()
        if self.mode == "stale":
            return payload
        return payload


def _publish(root: Path, case, policy, providers=(), clock=None):
    return publish_encrypted_replicas(
        root,
        policy=policy,
        providers=providers,
        clock=clock,
        tenant_id=_OWNER,
        case_id=case.case_id,
        principal_id=_OWNER,
        key=_key(case.case_id),
        key_id=_KEY_ID,
        expected_head="",
        expected_hash="",
        artifacts=_artifacts(case),
        private_names={"filename": case.label + ".txt", "labels": [case.label]},
    )


def _bound_count(receipt: dict, case, providers: tuple[CiphertextDirectory, ...]) -> dict:
    version = str(receipt.get("generation") or "")
    rows = []
    for provider_id in receipt.get("verified_providers") or []:
        for entry in receipt.get("catalog") or []:
            rows.append({
                "provider_id": provider_id,
                "name": entry["name"],
                "state": "verified",
                "digest_match": True,
                "version_match": True,
                "version": entry["version"],
                "case_id": case.case_id,
                "key_id": _KEY_ID,
                "counted": True,
                "readback": True,
                "fixture_provider": provider_id != "local-primary",
            })
    for provider in providers:
        if provider.mode in {"acknowledgement", "local_cid", "queued", "stale", "corrupt", "unavailable", "partial"}:
            rows.append({
                "provider_id": provider.provider_id,
                "name": "case-head",
                "state": "verified",
                "digest_match": True,
                "version_match": provider.mode not in {"stale"},
                "version": "stale-version" if provider.mode == "stale" else version,
                "case_id": case.case_id,
                "key_id": _KEY_ID,
                "acknowledgement": provider.mode == "acknowledgement",
                "local_cid": provider.mode == "local_cid",
                "cid": "bafyfixture" if provider.mode == "local_cid" else "",
                "fixture_provider": True,
                "counted": False,
                "readback": False,
            })
    return label_ciphertext_replica_observations(rows, case_id=case.case_id, key_id=_KEY_ID, version=version)


def test_case_list_is_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS


def test_local_commit_counts_only_bound_readback_and_labels_fixtures(tmp_path: Path):
    policy = configure_replica_policy(desired=2, minimum=1, mode="private_remote")
    for case in meaningful_cases():
        if not case.storage_available:
            continue
        root = tmp_path / case.label
        good = CiphertextDirectory(root / "providers" / "good", "fixture-good")
        queued = CiphertextDirectory(root / "providers" / "queued", "fixture-queued", mode="queued")
        acknowledged = CiphertextDirectory(root / "providers" / "ack", "fixture-ack", mode="acknowledgement")
        cid = CiphertextDirectory(root / "providers" / "cid", "fixture-cid", mode="local_cid")
        stale = CiphertextDirectory(root / "providers" / "stale", "fixture-stale", mode="stale")
        corrupt = CiphertextDirectory(root / "providers" / "corrupt", "fixture-corrupt", mode="corrupt")
        receipt = _publish(
            root / "case",
            case,
            policy,
            providers=(good, queued, acknowledged, cid, stale, corrupt),
            clock=lambda: 1_700_000_000.0,
        )
        assert receipt["verified_providers"] == ["local-primary", "fixture-good"]
        assert receipt["verified_replicas"] == 2
        assert good.gets > 0
        assert queued.gets == 0
        blob = next(path for path in (root / "providers" / "good").rglob("*") if path.is_file())
        assert case.narrative.text.encode("utf-8") not in blob.read_bytes()
        assert case.narrative.text not in json.dumps(receipt)
        labeled = _bound_count(receipt, case, (good, queued, acknowledged, cid, stale, corrupt))
        assert labeled["verified_providers"] == ["local-primary", "fixture-good"]
        labels = {item["provider_id"]: item for item in labeled["labels"]}
        assert labels["fixture-good"]["fixture_provider"] is True
        assert labels["fixture-good"]["authenticated_readback"] is True
        assert labels["fixture-ack"]["acknowledgement"] is True
        assert labels["fixture-ack"]["counted"] is False
        assert labels["fixture-cid"]["local_cid"] is True
        assert labels["fixture-cid"]["counted"] is False
        assert labels["fixture-stale"]["counted"] is False
        direct = count_verified_ciphertext_replicas([
            {"provider_id": "local-primary", "state": "verified", "digest_match": True, "version_match": True},
            {"provider_id": "fixture-ack", "state": "verified", "digest_match": False, "version_match": True},
            {"provider_id": "fixture-cid", "state": "verified", "digest_match": False, "version_match": False},
            {"provider_id": "fixture-stale", "state": "verified", "digest_match": True, "version_match": False},
        ])
        assert direct["verified_replicas"] == 1
        assert direct["verified_providers"] == ["local-primary"]
        assert labeled["live_durability"] is False


def test_offline_corrupt_stale_and_partial_keep_the_local_commit(tmp_path: Path):
    case = next(item for item in meaningful_cases() if item.label == "storage_outage")
    root = tmp_path / "durable"
    policy = configure_replica_policy(
        desired=3,
        minimum=1,
        mode="private_remote",
        max_attempts=3,
        base_backoff_seconds=3600,
        max_backoff_seconds=86400,
    )
    offline = CiphertextDirectory(root / "providers" / "offline", "fixture-offline", mode="unavailable")
    partial = CiphertextDirectory(root / "providers" / "partial", "fixture-partial", mode="partial")
    now = {"value": 5_000.0}
    receipt = _publish(root / "case", case, policy, providers=(offline, partial), clock=lambda: now["value"])
    local_files = {
        path.relative_to(root / "case" / "case-manifest").as_posix(): path.read_bytes()
        for path in (root / "case" / "case-manifest").rglob("*")
        if path.is_file()
    }
    assert receipt["status"] == "reconciliation_required"
    assert receipt["verified_replicas"] == 1
    assert receipt["verified_providers"] == ["local-primary"]
    assert receipt["meets_minimum"] is True
    assert receipt["meets_desired"] is False
    assert receipt["waited"] is False
    assert receipt["synchronous_wait_seconds"] == 0
    assert {item["provider_id"] for item in receipt["unavailable_providers"]} == {"fixture-offline", "fixture-partial"}
    early = reconcile_encrypted_replicas(
        root / "case",
        receipt,
        policy=policy,
        providers=(offline, partial),
        clock=lambda: now["value"] + 10,
    )
    assert offline.puts == 1
    assert early["verified_replicas"] == 1
    assert early["unavailable_providers"][0]["next_retry_at"] == receipt["unavailable_providers"][0]["next_retry_at"]
    held = {
        path.relative_to(root / "case" / "case-manifest").as_posix(): path.read_bytes()
        for path in (root / "case" / "case-manifest").rglob("*")
        if path.is_file()
    }
    assert held == local_files
    with pytest.raises(PrivateRevisionError):
        restore_encrypted_replicas(
            tmp_path / "unrestored",
            receipt,
            providers=(offline, partial),
            tenant_id=_OWNER,
            case_id=case.case_id,
            principal_id=_OWNER,
            key=_key(case.case_id),
            key_id=_KEY_ID,
        )
    assert not (tmp_path / "unrestored" / "case-manifest" / "case-head").exists()


def test_good_ciphertext_directory_restores_and_rejects_other_bindings(tmp_path: Path):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    root = tmp_path / "restore"
    policy = configure_replica_policy(desired=2, minimum=1, mode="private_remote")
    good = CiphertextDirectory(root / "providers" / "good", "fixture-good")
    stale = CiphertextDirectory(root / "providers" / "stale", "fixture-stale", mode="stale")
    receipt = _publish(root / "case", case, policy, providers=(stale, good), clock=lambda: 80.0)
    manifest = root / "case" / "case-manifest"

    def _catalog_bytes() -> dict[str, bytes]:
        return {
            path.relative_to(manifest).as_posix(): path.read_bytes()
            for path in manifest.rglob("*")
            if path.is_file() and path.name != ".owner.lock"
        }

    saved = _catalog_bytes()
    for path in list(manifest.rglob("*")):
        if path.is_file() and path.name != ".owner.lock":
            path.unlink()
    restored = restore_encrypted_replicas(
        root / "case",
        receipt,
        providers=(stale, good),
        tenant_id=_OWNER,
        case_id=case.case_id,
        principal_id=_OWNER,
        key=_key(case.case_id),
        key_id=_KEY_ID,
    )
    assert restored["roles"]["answer"] == b"complaint:" + case.narrative.text.encode("utf-8")
    assert restored["roles"]["proof"] == b"proof:baseline"
    assert _catalog_bytes() == saved
    with pytest.raises(PrivateRevisionError):
        restore_encrypted_replicas(
            tmp_path / "other-case",
            receipt,
            providers=(good,),
            tenant_id=_OWNER,
            case_id="other-case",
            principal_id=_OWNER,
            key=_key(case.case_id),
            key_id=_KEY_ID,
        )
    with pytest.raises(PrivateRevisionError):
        restore_encrypted_replicas(
            tmp_path / "other-key",
            receipt,
            providers=(good,),
            tenant_id=_OWNER,
            case_id=case.case_id,
            principal_id=_OWNER,
            key=bytes(range(32)),
            key_id=_KEY_ID,
        )


def test_workspace_snapshot_keeps_kit_receipt_and_local_frame(tmp_path: Path):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    service = ComplaintWorkspaceService(tmp_path / "workspace")
    created = service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    service.unlock_private_keys(passphrase=PASSPHRASE)
    assert service.ensure_private_case_key(_OWNER, _OWNER).get("data_key_id")
    state = service._load_state(_OWNER)
    narrative = state.get("original_complaint")
    if isinstance(narrative, dict):
        narrative["text"] = case.narrative.text
    service._save_state(state)
    saved = service.commit_complete_grounded_snapshot(_OWNER)
    kit = saved["kit_durability"]
    assert kit["status"] == "available"
    assert kit["schema"].endswith("durability-receipt@1")
    assert kit["durable"] is True
    assert kit["wal_file_fsync"] is False
    assert kit["counts_as_replica"] is False
    assert kit["network_durable"] is False
    assert kit["local_fsync_is_network_durability"] is False
    assert kit["live_qualification"] is False
    assert case.narrative.text not in json.dumps(kit)
    fresh = ComplaintWorkspaceService(tmp_path / "workspace")
    fresh.unlock_private_keys(passphrase=PASSPHRASE)
    loaded = fresh.load_complete_interview_snapshot(_OWNER)
    assert loaded["snapshot"]["grounding"] == saved["snapshot"]["grounding"]
    assert loaded["kit_durability"]["receipt_id"] == kit["receipt_id"]
    assert loaded["kit_durability"]["counts_as_replica"] is False

    class FrameDirectory:
        def __init__(self, directory: Path, *, mode: str = "verified") -> None:
            self.directory = directory
            self.mode = mode
            self.provider_class = "fixture"
            directory.mkdir(parents=True, exist_ok=True)

        def place(self, *, digest: str, version: str, frame: bytes, timeout_seconds: float | None = None) -> dict:
            if self.mode == "unavailable":
                raise TimeoutError("offline")
            payload = frame
            if self.mode == "corrupt":
                payload = b"\xff" + frame
            if self.mode == "partial":
                payload = frame[:8]
            (self.directory / digest).write_bytes(payload)
            (self.directory / (digest + ".version")).write_text("stale" if self.mode == "stale" else version)
            return {"status": "stored", "cid": "bafyfixtureframe"}

        def readback(self, *, digest: str, version: str, timeout_seconds: float | None = None) -> dict:
            if self.mode == "unavailable":
                return {"status": "unavailable"}
            path = self.directory / digest
            if not path.is_file():
                return {"status": "unavailable"}
            returned = (self.directory / (digest + ".version")).read_text()
            return {"status": "available", "frame": path.read_bytes(), "version": returned, "cid": "bafyfixtureframe"}

    repository = tmp_path / "replicas"
    good = FrameDirectory(repository / "good")
    offline = FrameDirectory(repository / "offline", mode="unavailable")
    corrupt = FrameDirectory(repository / "corrupt", mode="corrupt")
    stale = FrameDirectory(repository / "stale", mode="stale")
    partial = FrameDirectory(repository / "partial", mode="partial")
    from integrations.ipfs_datasets.storage import replica_policy

    policy = replica_policy(desired_replicas=2, minimum_replicas=1, mode="private_remote")
    published = service.publish_encrypted_replicas(
        _OWNER,
        repository,
        policy=policy,
        revision="r1",
        complaint=case.narrative.text.encode("utf-8"),
        fact_graph=b"graph:baseline",
        proof=b"proof:baseline",
        providers={"fixture-good": good, "fixture-offline": offline, "fixture-corrupt": corrupt, "fixture-stale": stale, "fixture-partial": partial},
        timeout_seconds=1,
    )
    assert published["primary_verified"] is True
    assert published["verified_replica_count"] == 2
    assert published["status"] == "degraded"
    assert "fixture-offline" in published["unavailable_providers"]
    primary = (repository / "replica-ledger" / "primary.frame").read_bytes()
    opened = service.restore_encrypted_workspace(_OWNER, repository, providers={
        "fixture-offline": offline,
        "fixture-corrupt": corrupt,
        "fixture-stale": stale,
        "fixture-partial": partial,
    }, timeout_seconds=1)
    assert opened["source"] == "local"
    assert opened["complaint"] == case.narrative.text.encode("utf-8")
    assert (repository / "replica-ledger" / "primary.frame").read_bytes() == primary
    (repository / "replica-ledger" / "primary.frame").unlink()
    with pytest.raises(PrivateStorageError):
        service.restore_encrypted_workspace(_OWNER, repository, providers={
            "fixture-corrupt": corrupt,
            "fixture-stale": stale,
            "fixture-partial": partial,
            "fixture-offline": offline,
        }, timeout_seconds=1)
    assert not (repository / "replica-ledger" / "primary.frame").exists()
    restored = service.restore_encrypted_workspace(_OWNER, repository, providers={"fixture-good": good}, timeout_seconds=1)
    assert restored["source"] == "replica"
    assert restored["revision"] == "r1"
    assert restored["proof"] == b"proof:baseline"
    assert (repository / "replica-ledger" / "primary.frame").read_bytes() == primary
    counted = service.count_verified_ciphertext_replicas(
        [
            {"provider_id": "local-primary", "name": "primary.frame", "state": "verified", "digest_match": True, "version_match": True, "version": "r1", "case_id": _OWNER, "key_id": "workspace", "counted": True, "readback": True},
            {"provider_id": "fixture-good", "name": "primary.frame", "state": "verified", "digest_match": True, "version_match": True, "version": "r1", "case_id": _OWNER, "key_id": "workspace", "counted": True, "readback": True, "fixture_provider": True},
            {"provider_id": "fixture-ack", "name": "primary.frame", "state": "verified", "digest_match": True, "version_match": True, "version": "r1", "case_id": _OWNER, "key_id": "workspace", "acknowledgement": True, "fixture_provider": True},
            {"provider_id": "fixture-cid", "name": "primary.frame", "state": "verified", "digest_match": True, "version_match": True, "version": "r1", "case_id": _OWNER, "key_id": "workspace", "local_cid": True, "cid": "bafyfixtureframe", "fixture_provider": True},
        ],
        case_id=_OWNER,
        key_id="workspace",
        version="r1",
    )
    assert counted["verified_providers"] == ["local-primary", "fixture-good"]
    assert counted["labels"][2]["acknowledgement"] is True
    assert counted["labels"][2]["counted"] is False
    assert counted["labels"][3]["local_cid"] is True
    reconciled = service.reconcile_encrypted_replicas(repository, providers={"fixture-good": good}, timeout_seconds=1)
    assert reconciled["primary_verified"] is True
    assert reconciled["waited"] is False


def test_live_durability_qualification_stays_separate(tmp_path: Path):
    case = next(item for item in meaningful_cases() if item.storage_available)
    local = _publish(tmp_path / "local", case, select_private_storage_mode("local_private"))
    assert local["mode"] == "local_private"
    assert local["verified_replicas"] == 1
    assert local["network_sharing_started"] is False
    qualification = upstream_replication_fixture_qualification()
    assert qualification["executed"] is False
    assert qualification["substitutes_first_party"] is False
    assert qualification["passed"] is False
    assert all(item["counts_as_passed"] is False for item in qualification["suites"])
