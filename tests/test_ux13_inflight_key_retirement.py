"""Physical UX13 boundary probe: actual ciphertext, keys, sessions and ASGI.

The sole fault injection is a bounded gate that delegates the production
ciphertext backend unchanged. It does not manufacture an HTTP response,
plaintext, key, cryptographic receipt, session, or authorizer outcome.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import threading
import hmac

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from applications.case_message_api import CaseMessageService
from applications.case_routes import compose_case_routes
from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
from integrations.private_storage import UserOwnedKeySession, PrivateArtifactBinding, PrivateArtifactIntegrityError
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login
from tests.test_cimp_ux_13 import _receive, ORIGINAL, SOURCE

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


class _GatedCiphertextBackend:
    """Delegate authentic ciphertext unchanged; hold only one requested read."""
    def __init__(self):
        self.actual = MemoryByteBackend()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.armed = False
        self.ciphertext_read = False
        self.reads_until_gate = 1

    def add(self, data, pin=True):
        return self.actual.add(data, pin=pin)

    def cat(self, cid):
        payload = self.actual.cat(cid)
        if self.armed:
            self.reads_until_gate -= 1
        if self.armed and self.reads_until_gate == 0:
            self.armed = False
            assert isinstance(payload, bytes)
            assert ORIGINAL.encode() not in payload and SOURCE.encode() not in payload
            self.ciphertext_read = True
            self.entered.set()
            if not self.release.wait(10):
                raise AssertionError("private test ciphertext gate timed out")
        return payload


def _actual_world(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    backend = _GatedCiphertextBackend()
    workspace = EvidenceWorkspace(world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend, tmp_path / "evidence-root")
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_assignments=world.assignments, case_messages=CaseMessageService(world.messages),
        case_reviews=world.reviews, case_consent=world.consent, evidence_workspace=workspace,
        include_review=False, include_document=False)
    return world, app, backend


def test_actual_http_catalog_retires_key_locked_during_ciphertext_read(tmp_path):
    world, app, backend = _actual_world(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        created = _receive(client, world.case, csrf, idempotency_key="private-probe-receive")
        assert created.status_code == 201
        assert created.json()["receipt"]["ciphertext_readback"] is True
        headers = _composed_headers(world.case, csrf)
        before = client.get("/api/cases/evidence", headers=headers)
        assert before.status_code == 200
        assert len(before.json()["items"]) == 1
        assert before.json()["items"][0]["original_filename"] == ORIGINAL
        backend.armed = True
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.get, "/api/cases/evidence", headers=headers)
            try:
                assert backend.entered.wait(10), "real encrypted catalog read did not reach gate"
                assert backend.ciphertext_read is True
                assert not pending.done()
                state = world.owner_keys.lock()
                assert state["unlocked"] is False
                assert world.owner_keys.unlocked is False
            finally:
                backend.release.set()
            response = pending.result(timeout=10)
        body = response.json()
        rows = body.get("items", [])
        observed = {"http_status": response.status_code,
            "key_unlocked_after_lock": world.owner_keys.unlocked,
            "catalog_item_count": len(rows),
            "private_filename_visible": any(row.get("original_filename") == ORIGINAL for row in rows),
            "actual_ciphertext_read": backend.ciphertext_read,
            "completion_authority": False}
        (tmp_path / "closed_observation.json").write_text(json.dumps(observed, sort_keys=True))
        # A new request is genuinely refused by the same actual owner service.
        following = client.get("/api/cases/evidence", headers=headers)
        assert following.status_code == 503
        assert following.json()["items"] == []
        assert response.status_code == 503, observed
        assert rows == [], observed
        assert body.get("ingestion_status") == "unavailable", observed



def _retire(world, mode):
    if mode in {"lock", "lock_unlock"}:
        state = world.owner_keys.lock()
        assert state["unlocked"] is False
        if mode == "lock_unlock":
            state = world.owner_keys.unlock_passphrase(PASSPHRASE)
            assert state["unlocked"] is True
    elif mode in {"rekey", "other_handle_rekey"}:
        session = world.owner_keys
        if mode == "other_handle_rekey":
            session = UserOwnedKeySession(world.owner_keys.directory)
            assert session.unlock_passphrase(PASSPHRASE)["unlocked"] is True
        old_id = session.ensure_data_key(world.case.tenant_id, world.case.case_id)
        changed = session.rotate_case_grant_data_key(world.case.tenant_id, world.case.case_id,
            resource_id=world.case.resource_id, expected_data_key_id=old_id,
            operation_id="private-real-key-rotation")
        assert changed["rotated"] is True
        assert changed["new_data_key_id"] != old_id
    else:
        raise AssertionError("unknown private test retirement mode")


@pytest.mark.parametrize("retirement", ["lock_unlock", "rekey", "other_handle_rekey"])
def test_actual_http_catalog_retires_changed_key_scope_during_read(tmp_path, retirement):
    world, app, backend = _actual_world(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        assert _receive(client, world.case, csrf).status_code == 201
        headers = _composed_headers(world.case, csrf)
        backend.armed = True
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.get, "/api/cases/evidence", headers=headers)
            try:
                assert backend.entered.wait(10)
                assert backend.ciphertext_read is True and not pending.done()
                _retire(world, retirement)
            finally:
                backend.release.set()
            response = pending.result(timeout=10)
        rows = response.json().get("items", [])
        observed = {"mode": retirement, "http_status": response.status_code,
            "catalog_item_count": len(rows),
            "private_filename_visible": any(row.get("original_filename") == ORIGINAL for row in rows),
            "actual_ciphertext_read": backend.ciphertext_read, "completion_authority": False}
        (tmp_path / "closed_observation.json").write_text(json.dumps(observed, sort_keys=True))
        assert response.status_code == 503, observed
        assert rows == [], observed


@pytest.mark.parametrize("retirement", ["lock", "lock_unlock", "rekey", "other_handle_rekey"])
def test_actual_http_catalog_does_not_publish_after_late_key_retirement(tmp_path, retirement):
    world, app, backend = _actual_world(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        assert _receive(client, world.case, csrf).status_code == 201
        pointers = list((tmp_path / "evidence-root").glob("*/pointer.json"))
        assert len(pointers) == 1
        before = pointers[0].read_bytes()
        backend.reads_until_gate = 3  # load catalog, actual new artifact readback, actual new catalog readback
        backend.armed = True
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(_receive, client, world.case, csrf,
                idempotency_key="private-second-evidence")
            try:
                assert backend.entered.wait(10)
                assert backend.ciphertext_read is True and not pending.done()
                _retire(world, retirement)
            finally:
                backend.release.set()
            response = pending.result(timeout=10)
        observed = {"mode": retirement, "http_status": response.status_code,
            "pointer_changed_after_retirement": pointers[0].read_bytes() != before,
            "operation_succeeded": response.json().get("operation_succeeded") is True,
            "actual_ciphertext_read": backend.ciphertext_read, "completion_authority": False}
        (tmp_path / "closed_observation.json").write_text(json.dumps(observed, sort_keys=True))
        assert response.status_code == 503, observed
        assert pointers[0].read_bytes() == before, observed



def test_actual_http_boundary_rechecks_key_after_service_thread_returns(tmp_path, monkeypatch):
    world, app, _backend = _actual_world(tmp_path)
    service = app.state.evidence_workspace
    actual_list = service.list_catalog
    entered, release = threading.Event(), threading.Event()
    def held_actual_list(*args, **kwargs):
        result = actual_list(*args, **kwargs)
        assert len(result["items"]) == 1
        entered.set()
        if not release.wait(10):
            raise AssertionError("private test actual service return gate timed out")
        return result
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        assert _receive(client, world.case, csrf).status_code == 201
        monkeypatch.setattr(service, "list_catalog", held_actual_list)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.get, "/api/cases/evidence",
                headers=_composed_headers(world.case, csrf))
            try:
                assert entered.wait(10)
                assert not pending.done()
                assert world.owner_keys.lock()["unlocked"] is False
            finally:
                release.set()
            response = pending.result(timeout=10)
        assert response.status_code == 503
        assert response.json()["items"] == []
        assert response.json()["operation_succeeded"] is False


def test_actual_key_session_epoch_changes_only_for_explicit_lifetimes(tmp_path):
    world, _app, _backend = _actual_world(tmp_path)
    session, case = world.owner_keys, world.case
    epoch = session.session_epoch
    key_id = session.ensure_data_key(case.tenant_id, case.case_id)
    key = session.lookup_data_key(case.tenant_id, case.case_id, key_id)
    binding = PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case.case_id,
        principal_id=case.tenant_id, artifact_kind="private-test", revision="one")
    for _ in range(3):
        current_id, current_key = session.provider().resolve(binding)
        assert current_id == key_id
        assert hmac.compare_digest(current_key, key)
        assert session.session_epoch == epoch
    assert session.unlock_passphrase(PASSPHRASE)["unlocked"] is True
    assert session.session_epoch > epoch
    epoch = session.session_epoch
    assert session.lock()["unlocked"] is False
    assert session.session_epoch > epoch
    epoch = session.session_epoch
    assert session.lock()["unlocked"] is False
    assert session.session_epoch > epoch
    epoch = session.session_epoch
    with pytest.raises(PrivateArtifactIntegrityError):
        session.unlock_passphrase("synthetic incorrect passphrase")
    assert session.unlocked is False
    assert session.session_epoch > epoch
    epoch = session.session_epoch
    assert session.unlock_passphrase(PASSPHRASE)["unlocked"] is True
    assert session.session_epoch > epoch



def test_actual_http_does_not_publish_if_api_scope_retired_before_worker_starts(tmp_path, monkeypatch):
    world, app, _backend = _actual_world(tmp_path)
    service = app.state.evidence_workspace
    actual_receive = service.receive
    entered, release = threading.Event(), threading.Event()
    def held_before_actual_receive(*args, **kwargs):
        entered.set()
        if not release.wait(10):
            raise AssertionError("private test actual worker entry gate timed out")
        return actual_receive(*args, **kwargs)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        assert _receive(client, world.case, csrf).status_code == 201
        pointers = list((tmp_path / "evidence-root").glob("*/pointer.json"))
        assert len(pointers) == 1
        before = pointers[0].read_bytes()
        monkeypatch.setattr(service, "receive", held_before_actual_receive)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(_receive, client, world.case, csrf,
                idempotency_key="private-stale-api-capture")
            try:
                assert entered.wait(10)
                assert not pending.done()
                _retire(world, "lock_unlock")
            finally:
                release.set()
            response = pending.result(timeout=10)
        assert response.status_code == 503
        assert response.json()["items"] == []
        observed = {"http_status": response.status_code,
            "pointer_changed_after_retirement": pointers[0].read_bytes() != before,
            "completion_authority": False}
        (tmp_path / "closed_observation.json").write_text(json.dumps(observed, sort_keys=True))
        assert pointers[0].read_bytes() == before, observed
