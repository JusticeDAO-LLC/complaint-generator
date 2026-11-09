"""Real directory/key/browser boundaries for authored attachment bytes only."""
import base64
import json
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from applications.browser_sessions import (BrowserSessionConfiguration, BrowserSessionService,
    PrincipalStoreCredentialAdapter, SESSION_COOKIE)
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory, legacy_owner_only_binding
from applications.case_membership import CaseMembershipStore
from applications.case_routes import compose_case_routes
from applications.case_attachment_api import CaseAttachmentService
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore, SharedAttachmentStore
from integrations.private_storage import UserOwnedKeySession, seal_private_artifact
from tests.test_cimp_gui_37 import _world, _owner_body, _pdf, _Kit

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _legacy(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    envelope = seal_private_artifact(json.dumps({"user_id": owner.principal_id, "synthetic": True}).encode(),
        binding=legacy_owner_only_binding(owner.principal_id), key=case_key, key_id="case-key")
    case, _ = cases.adopt_owner_only_case(actor_principal_id=owner.principal_id, envelope=envelope)
    assert case.tenant_id == owner.principal_id and case.owner_principal_id == owner.principal_id
    memberships = CaseMembershipStore(tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=lambda: 1_700_000_000)
    grants = CaseResourceKeyGrantStore(tmp_path / "grants", key=os.urandom(32), key_id="grant-key",
        principals=principals, cases=cases, memberships=memberships)
    session = UserOwnedKeySession(tmp_path / "owner-keys")
    session.create(protection="passphrase", passphrase="synthetic-passphrase")
    session.ensure_data_key(case.tenant_id, case.case_id)
    backend = _Kit()  # Deliberate local byte-storage I/O boundary; encryption/grants remain real.
    store = SharedAttachmentStore(tmp_path / "attachments", grants, backend=backend)
    service = CaseAttachmentService(store, {owner.principal_id: session})
    return {"owner": owner, "case": case, "service": service}


def test_verified_legacy_owner_attachment_roundtrip_is_not_impersonation(tmp_path):
    world = _legacy(tmp_path)
    stored = world["service"].store_attachment(world["owner"].principal_id, _owner_body(world, _pdf()))
    downloaded = world["service"].download_attachment(world["owner"].principal_id,
        stored["attachment_id"], _owner_body(world, _pdf()))
    assert base64.b64decode(downloaded["content_base64"]) == _pdf()
    assert downloaded["actor_is_encrypted_owner"] is True


def test_legacy_encrypted_owner_flag_reports_actual_verified_identity(tmp_path):
    world = _legacy(tmp_path)
    stored = world["service"].store_attachment(world["owner"].principal_id, _owner_body(world, _pdf()))
    assert stored["actor_is_encrypted_owner"] is True


@pytest.mark.parametrize("change", ["logout", "rotate", "expiry"])
def test_real_browser_session_is_reproved_after_ciphertext_read_before_plaintext_delivery(tmp_path, monkeypatch, change):
    world = _world(tmp_path)
    case, owner = world["case"], world["owner"]
    clock = {"now": 1_700_000_000}
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(world["principals"], {"synthetic-owner-credential": owner.principal_id}),
        signing_key=os.urandom(32), ttl_seconds=300), clock=lambda: clock["now"])
    app = FastAPI()
    compose_case_routes(app, authorizer=CaseActionAuthorizer(world["principals"], world["cases"]),
        browser_sessions=sessions, case_attachments=world["service"],
        include_workspace=False, include_review=False, include_document=False)
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
        assert login.status_code == 200
        token, csrf = client.cookies.get(SESSION_COOKIE), login.json()["csrf_token"]
        created = client.post("/api/cases/attachments", headers={"x-csrf-token": csrf}, json=_owner_body(world, _pdf()))
        assert created.status_code == 201, created.text
        old_cat = world["kit"].cat
        observed = []
        def actual_read_then_invalidate(cid):
            ciphertext = old_cat(cid)
            if not observed:
                observed.append(cid)
                if change == "logout": sessions.logout(token, csrf_token=csrf)
                elif change == "rotate": sessions.rotate(token, csrf_token=csrf)
                else: clock["now"] += 301
            return ciphertext
        monkeypatch.setattr(world["kit"], "cat", actual_read_then_invalidate)
        response = client.post(f"/api/cases/attachments/{created.json()['attachment_id']}/download",
            headers={"x-csrf-token": csrf}, json=_owner_body(world, _pdf()))
        assert observed
        assert response.status_code in {401, 403}, "stale_browser_session_received_attachment_plaintext"
        assert "content_base64" not in response.json()


def test_owner_key_lock_during_actual_payload_decode_prevents_delivery(tmp_path, monkeypatch):
    from integrations.private_collaboration import SharedAttachmentError
    world = _world(tmp_path)
    stored = world["service"].store_attachment(world["owner"].principal_id, _owner_body(world, _pdf()))
    actual = world["store"]._payload
    def decode_then_lock(*args):
        decoded = actual(*args)
        world["owner_session"].lock()
        return decoded
    monkeypatch.setattr(world["store"], "_payload", decode_then_lock)
    with pytest.raises(SharedAttachmentError):
        world["service"].download_attachment(world["owner"].principal_id,
            stored["attachment_id"], _owner_body(world, _pdf()))


def test_key_rotation_during_ciphertext_add_cannot_publish_new_attachment_under_old_key(tmp_path, monkeypatch):
    from integrations.private_collaboration import SharedAttachmentError
    world = _world(tmp_path)
    case = world["case"]
    kid = world["owner_session"].ensure_data_key(case.tenant_id, case.case_id)
    actual_add = world["kit"].add_bytes
    changed = []
    def add_then_rotate(data, pin=True):
        result = actual_add(data, pin=pin)
        if not changed:
            changed.append(True)
            world["owner_session"].rotate_case_grant_data_key(case.tenant_id, case.case_id,
                resource_id=case.resource_id, expected_data_key_id=kid, operation_id="synthetic-rotate-during-upload")
        return result
    monkeypatch.setattr(world["kit"], "add_bytes", add_then_rotate)
    with pytest.raises(SharedAttachmentError):
        world["service"].store_attachment(world["owner"].principal_id, _owner_body(world, _pdf()))
    assert changed and not list((world["store"]._root / "records").glob("*.json"))


def test_delegated_download_reports_actual_recipient_separately_from_uploader(tmp_path):
    from tests.test_cimp_gui_37 import _accept, _grant, _lawyer_body
    world = _world(tmp_path)
    stored = world["service"].store_attachment(world["owner"].principal_id, _owner_body(world, _pdf()))
    membership = _accept(world, "current-member")
    grant = _grant(world, membership, "current-grant")
    opened = world["service"].download_attachment(world["lawyer"].principal_id,
        stored["attachment_id"], _lawyer_body(world, membership, grant))
    assert opened["actor_principal_id"] == world["lawyer"].principal_id
    assert opened["uploaded_by_principal_id"] == world["owner"].principal_id
    assert opened["key_grant_id"] == grant.key_grant_id
    assert opened["canonical_owner_principal_id"] == world["case"].tenant_id
    assert opened["actor_is_encrypted_owner"] is False


def _browser(world):
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(world["principals"], {"synthetic-owner-credential": world["owner"].principal_id}),
        signing_key=os.urandom(32), ttl_seconds=300))
    app = FastAPI()
    compose_case_routes(app, authorizer=CaseActionAuthorizer(world["principals"], world["cases"]),
        browser_sessions=sessions, case_attachments=world["service"],
        include_workspace=False, include_review=False, include_document=False)
    return app, sessions


def test_same_asgi_loop_can_process_logout_while_actual_backend_read_is_pending(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    world = _world(tmp_path)
    stored = world["service"].store_attachment(world["owner"].principal_id, _owner_body(world, _pdf()))
    app, _sessions = _browser(world)
    reached, release = Event(), Event()
    actual = world["kit"].cat
    def paused(cid):
        ciphertext = actual(cid)
        reached.set()
        assert release.wait(20), "test_backend_read_barrier_expired"
        return ciphertext
    monkeypatch.setattr(world["kit"], "cat", paused)
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, f"/api/cases/attachments/{stored['attachment_id']}/download",
                headers={"x-csrf-token": csrf}, json=_owner_body(world, _pdf()))
            try:
                assert reached.wait(20)
                # The same TestClient portal dispatches the genuine logout;
                # this would block behind the old synchronous route handler.
                logout = client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf})
                assert logout.status_code == 200
            finally:
                release.set()
            response = pending.result(timeout=20)
        assert response.status_code in {401, 403} and "content_base64" not in response.json()


def test_browser_revocation_during_upload_does_not_publish_reachable_attachment_metadata(tmp_path, monkeypatch):
    world = _world(tmp_path)
    app, sessions = _browser(world)
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
        assert login.status_code == 200
        token, csrf = client.cookies.get(SESSION_COOKIE), login.json()["csrf_token"]
        actual = world["kit"].add_bytes
        changed = []
        def add_then_logout(data, pin=True):
            value = actual(data, pin=pin)
            if not changed:
                changed.append(True)
                sessions.logout(token, csrf_token=csrf)
            return value
        monkeypatch.setattr(world["kit"], "add_bytes", add_then_logout)
        response = client.post("/api/cases/attachments", headers={"x-csrf-token": csrf}, json=_owner_body(world, _pdf()))
        assert response.status_code in {401, 403}
        assert changed and not list((world["store"]._root / "records").glob("*.json"))
        assert not list((world["store"]._root / "idem").iterdir())
        # The attempted object already handed to the I/O boundary is opaque
        # ciphertext; revocation does not claim to recall such orphan bytes.
        from integrations.private_storage import ENVELOPE_MAGIC
        assert all(blob.startswith(ENVELOPE_MAGIC) for blob in world["kit"].added)
