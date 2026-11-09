"""Authenticated private case manifests and conflict-safe head publication.

Synthetic repositories only. Upstream Iroh manifest fixtures are a separate
compatibility qualification and do not replace these assertions. Offline tests
do not start Iroh.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from integrations.ipfs_datasets.graphs import persist_graph_snapshot
from integrations.private_storage import (
    CaseManifestConflict,
    PrivateRevisionError,
    publish_case_manifest,
    read_case_manifest,
    recover_case_manifest,
)

SENTINEL = "SENTINEL-DUR004-whistleblower-filename"
KEY = bytes(range(1, 33))
KEY_ID = "k-opaque"
TENANT = "tenant-a"
CASE = "case-a"
PRINCIPAL = "tenant-a"
UPSTREAM_MANIFEST_SUITES = (
    "tests/test_iroh_manifest.py",
    "tests/test_iroh_operations_docs.py",
)


def _roles(marker: str, revision: str) -> dict:
    return {
        "answer": {"body": f"answer:{marker}".encode(), "revision": f"ans-{revision}"},
        "fact_graph": {"body": f"graph:{marker}".encode(), "revision": f"graph-{revision}"},
        "legal_rule_source": {"body": f"rule:{marker}".encode(), "revision": f"rule-{revision}"},
        "evaluation": {"body": f"eval:{marker}".encode(), "revision": f"eval-{revision}"},
        "proof": {"body": f"proof:{marker}".encode(), "revision": f"proof-{revision}"},
    }


def _names(marker: str) -> dict:
    return {
        "filename": f"{marker}.txt",
        "labels": [marker, "unsafe conditions"],
        "provenance": {"source_span": marker, "rule": "retaliation"},
    }


def _publish(root: Path, marker: str = SENTINEL, *, expected_head="", expected_hash="", revision="1", **kwargs):
    return publish_case_manifest(
        root,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        key=KEY,
        key_id=KEY_ID,
        expected_head=expected_head,
        expected_hash=expected_hash,
        artifacts=_roles(marker, revision),
        private_names=_names(marker),
        **kwargs,
    )


def _scan(root: Path) -> list[str]:
    hits = []
    needle = SENTINEL.encode()
    for path in root.rglob("*"):
        if SENTINEL in path.name:
            hits.append(path.name)
        if path.is_file() and not path.is_symlink() and needle in path.read_bytes():
            hits.append(str(path.relative_to(root)))
    return hits


def test_manifest_binds_five_roles_to_opaque_parent_generation(tmp_path: Path) -> None:
    root = tmp_path / "case"
    first = _publish(root)
    opened = read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert first.committed is True and first.minted_completion is True
    assert first.parent_generation is None and first.generation and len(first.generation) == 64
    assert opened["roles"]["answer"] == b"answer:" + SENTINEL.encode()
    assert opened["roles"]["fact_graph"].startswith(b"graph:")
    assert opened["roles"]["legal_rule_source"].startswith(b"rule:")
    assert opened["roles"]["evaluation"].startswith(b"eval:")
    assert opened["roles"]["proof"].startswith(b"proof:")
    assert opened["private_names"]["filename"].endswith(".txt")
    assert opened["manifest"]["parent_generation"] == ""
    second = _publish(
        root,
        marker="second-synthetic",
        expected_head=first.generation,
        expected_hash=first.manifest_hash,
        revision="2",
    )
    reopened = read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert second.parent_generation == first.generation
    assert reopened["parent_generation"] == first.generation
    assert reopened["roles"]["proof"] == b"proof:second-synthetic"
    assert _scan(root) == []


def test_concurrent_publish_conflicts_instead_of_losing_an_update(tmp_path: Path) -> None:
    root = tmp_path / "cas"
    first = _publish(root, marker="base")
    barrier = threading.Barrier(2)
    results = []

    def attempt(marker: str) -> None:
        barrier.wait()
        try:
            publication = _publish(
                root,
                marker=marker,
                expected_head=first.generation,
                expected_hash=first.manifest_hash,
                revision=marker,
            )
            results.append(("ok", publication))
        except CaseManifestConflict as exc:
            results.append(("conflict", exc.code))

    threads = [threading.Thread(target=attempt, args=(marker,)) for marker in ("left", "right")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(item[0] for item in results) == ["conflict", "ok"]
    winner = next(item[1] for item in results if item[0] == "ok")
    opened = read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    bodies = b"".join(opened["roles"].values())
    assert winner.generation == opened["generation"]
    assert bodies.count(b"left") + bodies.count(b"right") == 5
    assert (b"left" in bodies) ^ (b"right" in bodies)


def test_stale_expected_hash_does_not_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "stale-expect"
    first = _publish(root)
    with pytest.raises(CaseManifestConflict):
        _publish(root, expected_head=first.generation, expected_hash="ab" * 32, revision="nope")
    opened = read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert opened["generation"] == first.generation
    assert opened["roles"]["answer"] == b"answer:" + SENTINEL.encode()


def test_missing_or_stale_blob_recovers_without_minting_completion(tmp_path: Path) -> None:
    root = tmp_path / "recover"
    first = _publish(root, marker="kept")
    second = _publish(
        root,
        marker=SENTINEL,
        expected_head=first.generation,
        expected_hash=first.manifest_hash,
        revision="2",
    )
    blob = root / "case-manifest" / "o" / second.generation
    blob.unlink()
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(PrivateRevisionError) as missing:
        read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert missing.value.code == "stale_head"
    assert missing.value.state == "recoverable"
    after_read = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert after_read == before
    recovered = recover_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert recovered.minted_completion is False
    assert recovered.committed is False
    assert recovered.state == "recovered"
    assert recovered.generation == first.generation
    opened = read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert opened["generation"] == first.generation
    assert opened["roles"]["answer"] == b"answer:kept"
    objects = sorted((root / "case-manifest" / "o").iterdir())
    assert second.generation not in {path.name for path in objects}
    stale = root / "case-manifest" / "o" / first.generation
    stale.write_bytes(stale.read_bytes() + b"x")
    with pytest.raises(PrivateRevisionError) as stale_error:
        read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert stale_error.value.code == "stale_head"
    untouched = recover_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert untouched.minted_completion is False
    assert untouched.committed is False
    assert untouched.generation is None


def test_private_graph_names_stay_inside_the_envelope(tmp_path: Path) -> None:
    root = tmp_path / "graph-case"
    destination = tmp_path / "graphs"
    context = {
        "tenant_id": TENANT,
        "case_id": CASE,
        "principal_id": PRINCIPAL,
        "key": KEY,
        "key_id": KEY_ID,
        "case_manifest_repository": root,
        "expected_head": "",
        "expected_hash": "",
        "filename": SENTINEL + ".pdf",
        "labels": [SENTINEL],
        "provenance": {"quote": SENTINEL},
        "destination_dir": destination,
        "case_artifacts": _roles("sibling", "1"),
    }
    graph = {"entities": [{"label": SENTINEL, "text": SENTINEL}], "provenance": {"quote": SENTINEL}}
    result = persist_graph_snapshot(graph, private_context=context)
    assert result["status"] == "stored-private"
    assert result["persisted"] is True
    assert "filename" not in result and SENTINEL not in str(result)
    files = list(destination.glob("*.bin"))
    assert len(files) == 1
    assert SENTINEL not in files[0].name
    assert SENTINEL.encode() not in files[0].read_bytes()
    opened = read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert opened["private_names"]["filename"] == SENTINEL + ".pdf"
    assert SENTINEL in opened["private_names"]["labels"]
    assert opened["private_names"]["provenance"]["quote"] == SENTINEL
    assert SENTINEL.encode() in opened["roles"]["fact_graph"]
    assert _scan(root) == []
    conflict = persist_graph_snapshot(graph, private_context=context)
    assert conflict["status"] == "conflict"
    assert conflict["minted_completion"] is False
    assert conflict["code"] == "manifest_conflict"


def test_iroh_backend_is_optional_and_does_not_start_a_sidecar(tmp_path: Path) -> None:
    root = tmp_path / "iroh"
    try:
        from ipfs_kit_py.iroh.manifest import IrohManifestStore
    except Exception:
        IrohManifestStore = None
    if IrohManifestStore is None:
        with pytest.raises(PrivateRevisionError) as unavailable:
            _publish(root, backend="iroh", iroh_store=object())
        assert unavailable.value.code == "iroh_unavailable"
        assert unavailable.value.state == "unavailable"
        assert not (root / "case-manifest" / "case-head").exists()
        return
    from ipfs_kit_py.iroh.errors import IrohConflictError, IrohNotFoundError

    class Client:
        def __init__(self) -> None:
            self.calls = []
            self.head = None
            self.manifest = None

        async def request(self, method, params, timeout=None):
            self.calls.append(method)
            if method == "manifests.create":
                self.manifest = params["manifest"]
                self.head = {
                    "namespace_id": params["namespace_id"],
                    "revision": 0,
                    "manifest_hash": params["manifest_hash"],
                }
                return {"manifest": self.manifest, "head": self.head}
            if method == "manifests.compare_and_swap":
                if (
                    self.head is None
                    or params["expected_revision"] != self.head["revision"]
                    or params["expected_manifest_hash"] != self.head["manifest_hash"]
                ):
                    raise IrohConflictError("conflict")
                self.manifest = params["manifest"]
                self.head = {
                    "namespace_id": params["namespace_id"],
                    "revision": self.manifest["revision"],
                    "manifest_hash": params["manifest_hash"],
                }
                return {"manifest": self.manifest, "head": self.head}
            if method == "manifests.open":
                if self.head is None:
                    raise IrohNotFoundError("missing")
                return {"head": self.head}
            raise AssertionError(method)

    client = Client()
    store = IrohManifestStore(client)
    first = _publish(root, backend="iroh", iroh_store=store)
    assert "manifests.create" in client.calls
    assert SENTINEL not in str(client.manifest)
    second_client_methods_before = list(client.calls)
    second = _publish(
        root,
        marker="iroh-next",
        expected_head=first.generation,
        expected_hash=first.manifest_hash,
        revision="2",
        backend="iroh",
        iroh_store=store,
    )
    assert "manifests.compare_and_swap" in client.calls[len(second_client_methods_before):]
    assert second.committed is True
    assert SENTINEL.encode() not in str(client.calls).encode()
    client.head = {"namespace_id": client.head["namespace_id"], "revision": 99, "manifest_hash": "cd" * 32}
    with pytest.raises(CaseManifestConflict):
        _publish(
            root,
            marker="lost",
            expected_head=second.generation,
            expected_hash=second.manifest_hash,
            revision="3",
            backend="iroh",
            iroh_store=store,
        )
    opened = read_case_manifest(root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert opened["generation"] == second.generation


def test_upstream_manifest_fixtures_are_a_separate_qualification() -> None:
    root = Path(__file__).resolve().parents[1] / "external" / "ipfs_kit_py"
    report = []
    for relative in UPSTREAM_MANIFEST_SUITES:
        path = root / relative
        report.append({
            "suite": relative,
            "counts_as_passed": False,
            "status": "available_unexecuted" if path.is_file() else "missing",
        })
    assert [item["suite"] for item in report] == list(UPSTREAM_MANIFEST_SUITES)
    assert all(item["counts_as_passed"] is False for item in report)
    assert all(item["status"] in {"available_unexecuted", "missing"} for item in report)
