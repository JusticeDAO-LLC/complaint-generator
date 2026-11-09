"""Truthful storage failure and replica recovery.

Positive cases keep a verified receipt when a later key or backend failure
hits a different attempt, and they keep storage readiness independent of
interview and legal readiness. Negative cases leave offline, unavailable,
corrupt, and truncated ciphertext unresolved, keep acknowledged states, and
omit keys from the HTTP body and logs.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    VerifiedPrincipal,
)
from applications.case_directory import CaseDirectory
from applications.case_routes import compose_case_routes, durability_readiness_boundary
from applications.case_storage_api import CaseStorageError, CaseStorageService
from applications.principal_store import PrincipalStore
from integrations.private_storage import DURABILITY_STATES, UserOwnedKeySession

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
SECRET = b"UNIQUE-CASE-CIPHER-39"
PASSPHRASE = "owner-passphrase-39"


class Kit:
    def __init__(self, *, readback: bytes | None = None, truncate: bool = False, corrupt: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[str] = []
        self._readback = readback
        self._truncate = truncate
        self._corrupt = corrupt
        self._n = 0

    def manifest(self, data: bytes) -> dict[str, object]:
        self.calls.append("manifest")
        self._n += 1
        ref = f"kit-ref-{self._n}"
        self.objects[ref] = bytes(data)
        return {"ref": ref, "state": "local_commit"}

    def queue_replication(self, ref: str) -> dict[str, object]:
        self.calls.append("queue_replication")
        return {"ref": ref, "state": "queued"}

    def pin(self, ref: str) -> dict[str, object]:
        self.calls.append("pin")
        return {"ref": ref, "pinned": True}

    def readback(self, ref: str) -> bytes:
        self.calls.append("readback")
        if self._readback is not None:
            return self._readback
        blob = self.objects[ref]
        if self._truncate:
            return blob[:8]
        if self._corrupt:
            return b"not-ciphertext"
        return blob


class _Adapter:
    def __init__(self, principals: dict[str, VerifiedPrincipal]) -> None:
        self.principals = principals

    def verify_credential(self, material: dict) -> VerifiedPrincipal:
        principal = self.principals.get(str(material.get("credential") or ""))
        if principal is None:
            raise RuntimeError("authentication_failed")
        return principal


def _world(tmp_path: Path, kit: Kit | None = None, *, with_key: bool = True):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    sessions: dict[str, UserOwnedKeySession] = {}
    session = None
    if with_key:
        session = UserOwnedKeySession(tmp_path / "owner-keys")
        session.create(protection="passphrase", passphrase=PASSPHRASE)
        session.ensure_data_key(case.tenant_id, case.case_id)
        sessions[owner.principal_id] = session
    service = CaseStorageService(cases, sessions, kit or Kit())
    return {
        "owner": owner,
        "case": case,
        "kit": service._kit,
        "service": service,
        "principals": principals,
        "session": session,
    }


def _body(world, content: bytes = SECRET, **extra) -> dict:
    case = world["case"]
    body = {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "revision": "r1",
        "idempotency_key": "dur-39",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
    body.update(extra)
    return body


def _assert_independent(receipt: dict) -> None:
    assert receipt["interview_readiness"] == "not_evaluated"
    assert receipt["legal_readiness"] == "not_evaluated"
    assert receipt["storage_sets_interview_readiness"] is False
    assert receipt["storage_sets_legal_readiness"] is False
    assert receipt["loss_of_acknowledged_work"] is False
    assert receipt["actor_is_encrypted_owner"] is False


def _assert_no_secrets(text: str, world) -> None:
    assert PASSPHRASE not in text
    assert SECRET.decode() not in text
    session = world["session"]
    if session is not None:
        key_id = session.ensure_data_key(world["case"].tenant_id, world["case"].case_id)
        data_key = session.lookup_data_key(world["case"].tenant_id, world["case"].case_id, key_id)
        assert data_key is not None
        rendered = data_key.hex() if isinstance(data_key, (bytes, bytearray)) else str(data_key)
        assert rendered not in text
        assert "data_key" not in text


def test_verified_receipt_survives_later_key_failure_and_stays_independent(tmp_path: Path, caplog) -> None:
    world = _world(tmp_path)
    with caplog.at_level(logging.INFO, logger="applications.case_storage_api"):
        receipt = world["service"].commit(world["owner"].principal_id, _body(world))
    assert receipt["durable"] is True
    assert receipt["storage_readiness"] == "ready"
    assert receipt["replica_status"] == "verified"
    assert receipt["pending_replica"] is False
    assert receipt["state_names"] == list(DURABILITY_STATES)
    _assert_independent(receipt)
    _assert_no_secrets(caplog.text, world)
    world["service"]._sessions.clear()
    with pytest.raises(CaseStorageError) as failed:
        world["service"].commit(world["owner"].principal_id, _body(world, idempotency_key="dur-39-key"))
    assert failed.value.code == "key_unavailable"
    assert failed.value.receipt["failure_kind"] == "key"
    assert failed.value.receipt["storage_readiness"] == "unresolved"
    _assert_independent(failed.value.receipt)
    retained = world["service"].read(world["owner"].principal_id, _body(world))
    assert retained == receipt
    assert retained["durable"] is True
    boundary = durability_readiness_boundary()
    assert boundary["storage_sets_interview_readiness"] is False
    assert boundary["storage_failure_clears_legal_readiness"] is False
    assert boundary["storage_readiness_owner"] == "case_storage"
    assert boundary["interview_readiness_owner"] != boundary["storage_readiness_owner"]


def test_offline_unavailable_corrupt_and_truncated_stay_unresolved(tmp_path: Path) -> None:
    offline_kit = Kit()

    def _offline(data: bytes) -> dict:
        offline_kit.calls.append("manifest")
        raise OSError("backend offline")

    offline_kit.manifest = _offline
    offline = _world(tmp_path / "offline", offline_kit)
    with pytest.raises(CaseStorageError) as offline_error:
        offline["service"].commit(offline["owner"].principal_id, _body(offline))
    assert offline_error.value.code == "kit_manifest_failed"
    assert offline_error.value.receipt["unresolved"] is True
    assert offline_error.value.receipt["storage_readiness"] == "unavailable"
    assert offline_error.value.receipt["failure_kind"] == "backend"
    assert offline_error.value.receipt["durable"] is False
    assert offline_error.value.receipt["state_names"] == []
    _assert_independent(offline_error.value.receipt)
    again = pytest.raises(CaseStorageError)
    with again:
        offline["service"].commit(offline["owner"].principal_id, _body(offline))
    assert offline_kit.calls == ["manifest"]
    listed = offline["service"].read(offline["owner"].principal_id, _body(offline))
    assert listed["unresolved"] is True
    assert listed["error"] == "kit_manifest_failed"

    unavailable_kit = Kit()
    unavailable_kit.queue_replication = None
    unavailable = _world(tmp_path / "unavailable", unavailable_kit)
    with pytest.raises(CaseStorageError) as unavailable_error:
        unavailable["service"].commit(unavailable["owner"].principal_id, _body(unavailable))
    assert unavailable_error.value.code == "kit_queue_replication_unavailable"
    assert unavailable_error.value.receipt["state_names"] == ["local_commit"]
    assert unavailable_error.value.receipt["acknowledged_work_retained"] is True
    assert unavailable_error.value.receipt["pending_replica"] is False
    assert unavailable_error.value.receipt["replica_status"] == "unresolved"
    assert unavailable_error.value.receipt["storage_readiness"] == "unavailable"
    reread = unavailable["service"].read(unavailable["owner"].principal_id, _body(unavailable))
    assert reread["state_names"] == ["local_commit"]
    assert reread["durable"] is False

    corrupt = _world(tmp_path / "corrupt", Kit(corrupt=True))
    with pytest.raises(CaseStorageError) as corrupt_error:
        corrupt["service"].commit(corrupt["owner"].principal_id, _body(corrupt))
    assert corrupt_error.value.code == "readback_mismatch"
    assert corrupt_error.value.receipt["ciphertext_condition"] == "corrupt"
    assert corrupt_error.value.receipt["unresolved"] is True
    assert corrupt_error.value.receipt["storage_readiness"] == "unresolved"
    assert corrupt_error.value.receipt["state_names"] == ["local_commit", "queued_replication", "pin"]
    assert "verified_replica" not in corrupt_error.value.receipt["state_names"]
    assert corrupt_error.value.receipt["pending_replica"] is True
    assert corrupt_error.value.receipt["replica_status"] == "pending"
    assert all(row["durable"] is False for row in corrupt_error.value.receipt["states"])
    kept = corrupt["service"].read(corrupt["owner"].principal_id, _body(corrupt))
    assert kept["state_names"] == corrupt_error.value.receipt["state_names"]
    assert kept["pending_replica"] is True

    truncated = _world(tmp_path / "truncated", Kit(truncate=True))
    with pytest.raises(CaseStorageError) as truncated_error:
        truncated["service"].commit(truncated["owner"].principal_id, _body(truncated))
    assert truncated_error.value.code == "readback_mismatch"
    assert truncated_error.value.receipt["ciphertext_condition"] == "truncated"
    assert truncated_error.value.receipt["unresolved"] is True
    assert truncated_error.value.receipt["pending_replica"] is True
    assert truncated_error.value.receipt["acknowledged_work_retained"] is True
    assert truncated_error.value.receipt["storage_readiness"] == "unresolved"
    _assert_independent(truncated_error.value.receipt)
    calls = list(truncated["kit"].calls)
    with pytest.raises(CaseStorageError) as replay:
        truncated["service"].commit(truncated["owner"].principal_id, _body(truncated))
    assert replay.value.receipt["ciphertext_condition"] == "truncated"
    assert truncated["kit"].calls == calls


def test_http_failure_keeps_other_readiness_and_hides_keys(tmp_path: Path, caplog) -> None:
    world = _world(tmp_path, Kit(truncate=True))
    case = world["case"]
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=_Adapter({
            "synthetic-owner-credential": VerifiedPrincipal(world["owner"].principal_id, case.tenant_id, ("complainant",)),
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
    app.state.interview_readiness = "ready"
    app.state.legal_readiness = "ready"
    with caplog.at_level(logging.INFO, logger="applications.case_storage_api"):
        with TestClient(app, base_url="https://testserver") as client:
            login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
            assert login.status_code == 200, login.text
            csrf = login.json()["csrf_token"]
            failed = client.post(
                "/api/cases/storage/durability",
                headers={"x-csrf-token": csrf},
                json=_body(world, idempotency_key="http-trunc", passphrase=PASSPHRASE, data_key="should-not-echo"),
            )
            assert failed.status_code == 400, failed.text
            assert failed.json()["error"] == "selector_rejected"
            created = client.post(
                "/api/cases/storage/durability",
                headers={"x-csrf-token": csrf},
                json=_body(world, idempotency_key="http-trunc"),
            )
            assert created.status_code == 409, created.text
            body = created.json()
            assert body["durable"] is False
            assert body["unresolved"] is True
            assert body["pending_replica"] is True
            assert body["ciphertext_condition"] == "truncated"
            assert body["storage_readiness"] == "unresolved"
            assert body["failure_kind"] == "storage"
            _assert_independent(body)
            assert PASSPHRASE not in created.text
            assert "data_key" not in created.text
            listed = client.get(
                "/api/cases/storage/durability",
                params={
                    "tenant_id": case.tenant_id,
                    "case_id": case.case_id,
                    "resource_id": case.resource_id,
                    "revision": "r1",
                    "idempotency_key": "http-trunc",
                },
            )
            assert listed.status_code == 200, listed.text
            assert listed.json()["state_names"] == ["local_commit", "queued_replication", "pin"]
            assert listed.json()["acknowledged_work_retained"] is True
            assert SECRET.decode() not in listed.text
    assert app.state.interview_readiness == "ready"
    assert app.state.legal_readiness == "ready"
    assert app.state.storage_readiness == "unresolved"
    assert app.state.durability_readiness_boundary["storage_sets_interview_readiness"] is False
    _assert_no_secrets(caplog.text, world)
    page = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    assert 'id="storage-durability-recovery"' in page
    assert 'data-task="CIMP-GUI-39"' in page
    assert "Storage readiness is separate from interview readiness and legal readiness" in page
    assert 'data-keys-displayed="false"' in page
    assert "truncated ciphertext stays unresolved" in page
    assert "renderStorageDurabilityRecovery" in page
    assert PASSPHRASE not in page
