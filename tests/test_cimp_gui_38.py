"""Ciphertext durability through Kit manifest, queue, pin, and readback.

Positive cases seal before the Kit owner, keep local commit, queued
replication, pin, and verified replica distinct, and set durable only after
readback matches. Negative cases reject a mismatched readback, a public
gateway URL, CID inference, and a non-owner.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    VerifiedPrincipal,
)
from applications.case_directory import CaseDirectory
from applications.case_routes import compose_case_routes
from applications.case_storage_api import CaseStorageError, CaseStorageService
from applications.principal_store import PrincipalStore
from integrations.private_storage import (
    DURABILITY_STATES,
    ENVELOPE_MAGIC,
    UserOwnedKeySession,
    verify_ciphertext_durability,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

SECRET = b"UNIQUE-CASE-CIPHER-38"


class Kit:
    def __init__(self, *, readback: bytes | None = None, gateway: str = "", cid_only: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[str] = []
        self._readback = readback
        self._gateway = gateway
        self._cid_only = cid_only
        self._n = 0

    def manifest(self, data: bytes) -> dict[str, object]:
        self.calls.append("manifest")
        blob = bytes(data)
        self._n += 1
        ref = f"kit-ref-{self._n}"
        self.objects[ref] = blob
        if self._gateway:
            return {"ref": ref, "gateway": self._gateway}
        if self._cid_only:
            return {"cid": "bafy" + "a" * 20, "pinned": True, "durable": True, "state": "verified_replica"}
        return {"ref": ref, "state": "local_commit"}

    def queue_replication(self, ref: str) -> dict[str, object]:
        self.calls.append("queue_replication")
        return {"ref": ref, "state": "verified_replica", "durable": True}

    def pin(self, ref: str) -> dict[str, object]:
        self.calls.append("pin")
        return {"ref": ref, "pinned": True, "state": "verified_replica", "cid": "bafyignored"}

    def readback(self, ref: str) -> bytes:
        self.calls.append("readback")
        if self._readback is not None:
            return self._readback
        if self._cid_only:
            return b"bafy" + b"a" * 20
        return self.objects[ref]

    def gateway_get(self, url: str) -> bytes:
        raise AssertionError(url)


class _Adapter:
    def __init__(self, principals: dict[str, VerifiedPrincipal]) -> None:
        self.principals = principals

    def verify_credential(self, material: dict) -> VerifiedPrincipal:
        principal = self.principals.get(str(material.get("credential") or ""))
        if principal is None:
            raise RuntimeError("authentication_failed")
        return principal


def _world(tmp_path: Path, kit: Kit | None = None):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    session = UserOwnedKeySession(tmp_path / "owner-keys")
    session.create(protection="passphrase", passphrase="owner-passphrase")
    session.ensure_data_key(case.tenant_id, case.case_id)
    kit = kit or Kit()
    service = CaseStorageService(cases, {owner.principal_id: session}, kit)
    return {"owner": owner, "lawyer": lawyer, "case": case, "kit": kit, "service": service, "principals": principals}


def _body(world, content: bytes = SECRET, **extra) -> dict:
    case = world["case"]
    body = {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "revision": "r1",
        "idempotency_key": "dur-1",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
    body.update(extra)
    return body


def test_readback_sets_durable_and_keeps_states_distinct(tmp_path: Path) -> None:
    world = _world(tmp_path)
    receipt = world["service"].commit(world["owner"].principal_id, _body(world))
    assert receipt["state_names"] == list(DURABILITY_STATES)
    assert receipt["durable"] is True
    assert receipt["readback_matched"] is True
    assert receipt["public_gateway_consulted"] is False
    assert receipt["cid_inference"] is False
    assert receipt["actor_is_encrypted_owner"] is False
    assert receipt["canonical_owner_principal_id"] == world["case"].tenant_id
    assert [row["state"] for row in receipt["states"]] == list(DURABILITY_STATES)
    assert [row["durable"] for row in receipt["states"]] == [False, False, False, True]
    assert [row["counts_as_verified_replica"] for row in receipt["states"]] == [False, False, False, True]
    assert receipt["states"][1]["kit_replica_state"] == "queued"
    assert receipt["states"][3]["kit_replica_state"] == "verified"
    assert world["kit"].calls == ["manifest", "queue_replication", "pin", "readback"]
    for blob in world["kit"].objects.values():
        assert blob.startswith(ENVELOPE_MAGIC)
        assert SECRET not in blob
    again = world["service"].commit(world["owner"].principal_id, _body(world))
    assert again == receipt
    assert world["kit"].calls == ["manifest", "queue_replication", "pin", "readback"]
    listed = world["service"].read(world["owner"].principal_id, _body(world))
    assert listed["durable"] is True
    with pytest.raises(CaseStorageError) as denied:
        world["service"].commit(world["lawyer"].principal_id, _body(world, idempotency_key="other"))
    assert denied.value.code == "not_owner"


def test_mismatch_gateway_and_cid_do_not_declare_durable(tmp_path: Path) -> None:
    mismatch = _world(tmp_path, Kit(readback=b"not-the-ciphertext"))
    with pytest.raises(CaseStorageError) as failed:
        mismatch["service"].commit(mismatch["owner"].principal_id, _body(mismatch))
    assert failed.value.code == "readback_mismatch"
    assert failed.value.receipt is not None
    assert failed.value.receipt["durable"] is False
    assert failed.value.receipt["state_names"] == ["local_commit", "queued_replication", "pin"]
    assert "verified_replica" not in failed.value.receipt["state_names"]
    assert all(row["durable"] is False for row in failed.value.receipt["states"])
    for blob in mismatch["kit"].objects.values():
        assert SECRET not in blob

    gateway = _world(tmp_path / "gateway", Kit(gateway="https://ipfs.io/ipfs/bafyexample"))
    with pytest.raises(CaseStorageError) as blocked:
        gateway["service"].commit(gateway["owner"].principal_id, _body(gateway))
    assert blocked.value.code == "public_gateway_rejected"
    assert gateway["kit"].calls == ["manifest"]

    cid_kit = Kit(cid_only=True)
    cid_world = _world(tmp_path / "cid", cid_kit)
    with pytest.raises(CaseStorageError) as inferred:
        cid_world["service"].commit(cid_world["owner"].principal_id, _body(cid_world))
    assert inferred.value.code == "readback_mismatch"
    assert inferred.value.receipt["durable"] is False
    assert inferred.value.receipt["cid_inference"] is False
    assert "readback" in cid_kit.calls

    with pytest.raises(CaseStorageError) as selector:
        mismatch["service"].commit(mismatch["owner"].principal_id, _body(mismatch, cid="bafypretend", idempotency_key="cid-body"))
    assert selector.value.code == "selector_rejected"
    assert mismatch["kit"].calls == ["manifest", "queue_replication", "pin", "readback"]


def test_http_commit_and_denied_non_owner(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=_Adapter({
            "synthetic-owner-credential": VerifiedPrincipal(world["owner"].principal_id, case.tenant_id, ("complainant",)),
            "synthetic-lawyer-credential": VerifiedPrincipal(world["lawyer"].principal_id, case.tenant_id, ("lawyer",)),
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    app = FastAPI()
    compose_case_routes(
        app,
        authorizer=None,
        browser_sessions=sessions,
        case_storage=world["service"],
        include_workspace=False,
        include_review=False,
        include_document=False,
    )
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
        assert login.status_code == 200, login.text
        csrf = login.json()["csrf_token"]
        created = client.post("/api/cases/storage/durability", headers={"x-csrf-token": csrf}, json=_body(world))
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["durable"] is True
        assert body["state_names"] == list(DURABILITY_STATES)
        assert SECRET.decode() not in created.text
        assert "ipfs.io" not in created.text
        listed = client.get(
            "/api/cases/storage/durability",
            params={
                "tenant_id": case.tenant_id,
                "case_id": case.case_id,
                "resource_id": case.resource_id,
                "revision": "r1",
                "idempotency_key": "dur-1",
            },
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["readback_matched"] is True
        logout = client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf})
        assert logout.status_code == 200
        lawyer = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-lawyer-credential"})
        assert lawyer.status_code == 200, lawyer.text
        denied = client.post(
            "/api/cases/storage/durability",
            headers={"x-csrf-token": lawyer.json()["csrf_token"]},
            json=_body(world, idempotency_key="lawyer"),
        )
        assert denied.status_code == 403, denied.text
        assert denied.json()["durable"] is False
        assert SECRET.decode() not in denied.text

    bare = verify_ciphertext_durability(world["kit"], world["kit"].objects["kit-ref-1"])
    assert bare["durable"] is True
    assert bare["state_names"] == list(DURABILITY_STATES)
