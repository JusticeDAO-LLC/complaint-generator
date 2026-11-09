"""Production factories preserve the existing authorized evidence owner."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_ux_14 import _upload, _composed_headers, _composed_login
from tests.test_cimp_gui_14 import PASSPHRASE

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
FACTORIES = ("server", "review-api", "review-surface", "review-dashboard")


def _factory(name, world, evidence):
    from applications.server import SERVER
    from applications.review_api import create_review_api_app
    from applications.review_ui import create_review_surface_app, create_review_dashboard_app
    options = dict(authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=world.app.state.case_handlers, case_catalog=world.app.state.case_catalog,
        case_consent=world.consent, case_reviews=world.reviews, evidence_workspace=evidence)
    if name == "server":
        return SERVER(world.service, workspace_service=world.service, **options).app
    if name == "review-api":
        return create_review_api_app(world.service, workspace_service=world.service, **options)
    if name == "review-surface":
        return create_review_surface_app(world.service, workspace_service=world.service, **options)
    if name == "review-dashboard":
        return create_review_dashboard_app(**options)
    raise AssertionError("unknown actual production factory")


@pytest.mark.parametrize("factory", FACTORIES)
def test_production_factory_forwards_the_explicit_existing_owner(tmp_path, factory):
    world = owner_lawyer_journey_world(tmp_path / "world")
    # Explicit inherited memory owner tests only the factory compatibility seam.
    # It is neither an automatic fallback nor durability qualification.
    evidence = EvidenceWorkspace(world.cases, {world.owner.principal_id: world.owner_keys},
        MemoryByteBackend(), tmp_path / "catalog")
    app = _factory(factory, world, evidence)
    assert app.state.evidence_workspace is evidence
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/cases/evidence", headers=_composed_headers(world.case)).status_code == 401
        csrf = _composed_login(client)
        _, _, uploaded = _upload(client, world.case, csrf)
        catalog = client.get("/api/cases/evidence", headers=_composed_headers(world.case))
        assert catalog.status_code == 200, catalog.text
        assert [item["evidence_id"] for item in catalog.json()["items"]] == [uploaded["evidence_id"]]


def _kit_owner(tmp_path):
    from integrations.private_storage import KitLocalCiphertextBackend
    world = owner_lawyer_journey_world(tmp_path / "world")
    backend = KitLocalCiphertextBackend(tmp_path / "kit-bytes")
    evidence = EvidenceWorkspace(world.cases, {world.owner.principal_id: world.owner_keys},
        backend, tmp_path / "catalog")
    return world, backend, evidence


def _snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("factory", FACTORIES)
def test_missing_configured_owner_never_constructs_a_memory_fallback(tmp_path, factory):
    world = owner_lawyer_journey_world(tmp_path / "world")
    app = _factory(factory, world, None)
    assert app.state.evidence_workspace is None
    with TestClient(app, base_url="https://testserver") as client:
        _composed_login(client)
        denied = client.get("/api/cases/evidence", headers=_composed_headers(world.case))
        assert denied.status_code == 503
        assert denied.json()["error"] == "evidence_unavailable" and denied.json()["items"] == []
        assert app.state.evidence_workspace is None


def test_actual_production_upload_and_fresh_wallet_backend_owner_reopen(tmp_path):
    from integrations.private_storage import KitLocalCiphertextBackend, UserOwnedKeySession
    world, backend, evidence = _kit_owner(tmp_path)
    app = _factory("server", world, evidence)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        _, _, uploaded = _upload(client, world.case, csrf)
        before = client.get("/api/cases/evidence", headers=_composed_headers(world.case))
        assert before.status_code == 200, before.text
        original = before.json()["items"]
        assert len(original) == 1 and original[0]["integrity_verified"] is True
        assert original[0]["evidence_id"] == uploaded["evidence_id"]
    pointers = list(evidence._root.rglob("pointer.json"))
    assert len(pointers) == 1
    saved_pointer = pointers[0].read_bytes()
    assert json.loads((backend._root / "manifest.json").read_text())["effect_count"] == 2
    assert not hasattr(backend, "_blobs")
    backend.close()
    world.owner_keys.lock()
    fresh_wallet = UserOwnedKeySession(world.owner_keys.directory)
    assert fresh_wallet.unlock_passphrase(PASSPHRASE)["unlocked"] is True
    fresh_backend = KitLocalCiphertextBackend.reopen(backend._root)
    fresh_owner = EvidenceWorkspace(world.cases, {world.owner.principal_id: fresh_wallet},
        fresh_backend, evidence._root)
    assert fresh_owner is not evidence and fresh_backend is not backend and fresh_wallet is not world.owner_keys
    assert world.owner_keys.unlocked is False
    cold_app = _factory("server", world, fresh_owner)
    with TestClient(cold_app, base_url="https://testserver") as client:
        _composed_login(client)
        cold = client.get("/api/cases/evidence", headers=_composed_headers(world.case))
        assert cold.status_code == 200, cold.text
        assert cold.json()["items"] == original
        assert pointers[0].read_bytes() == saved_pointer
        assert fresh_wallet.lock()["unlocked"] is False
        closed = client.get("/api/cases/evidence", headers=_composed_headers(world.case))
        assert closed.status_code == 503 and closed.json()["items"] == []
        assert uploaded["evidence"]["original_filename"] not in closed.text
    fresh_backend.close()


@pytest.mark.parametrize("damage", ["catalog-sidecar", "wrong-wallet"])
def test_production_cold_read_refuses_missing_digest_or_wrong_case_key(tmp_path, damage):
    from integrations.private_storage import KitLocalCiphertextBackend, UserOwnedKeySession
    world, backend, evidence = _kit_owner(tmp_path)
    with TestClient(_factory("server", world, evidence), base_url="https://testserver") as client:
        csrf = _composed_login(client)
        _, _, uploaded = _upload(client, world.case, csrf)
    pointer = next(evidence._root.rglob("pointer.json"))
    cid = json.loads(pointer.read_text())["cid"]
    backend.close()
    if damage == "catalog-sidecar":
        matching = [p for p in backend._root.rglob("*.cid") if p.read_text() == cid]
        assert len(matching) == 1
        matching[0].unlink()
        wallet = UserOwnedKeySession(world.owner_keys.directory)
        wallet.unlock_passphrase(PASSPHRASE)
    else:
        wallet = UserOwnedKeySession(tmp_path / "unrelated-wallet")
        wallet.create(protection="passphrase", passphrase=PASSPHRASE)
    world.owner_keys.lock()
    fresh = KitLocalCiphertextBackend.reopen(backend._root)
    owner = EvidenceWorkspace(world.cases, {world.owner.principal_id: wallet}, fresh, evidence._root)
    before = (_snapshot(backend._root), _snapshot(evidence._root))
    with TestClient(_factory("server", world, owner), base_url="https://testserver", raise_server_exceptions=False) as client:
        _composed_login(client)
        denied = client.get("/api/cases/evidence", headers=_composed_headers(world.case))
        assert denied.status_code == 503
        assert denied.json()["items"] == [] and denied.json()["ingestion_status"] == "unavailable"
        assert denied.json()["error"] == "ciphertext_unavailable"
        assert denied.json().get("operation_succeeded") is not True
        assert uploaded["evidence"]["original_filename"] not in denied.text
        assert (_snapshot(backend._root), _snapshot(evidence._root)) == before
    fresh.close()


def test_actual_kit_byte_adapter_is_local_only_and_rejects_plaintext(tmp_path):
    from integrations.private_storage import (KitLocalCiphertextBackend, PrivateStorageError,
        seal_private_artifact)
    from integrations.ipfs_datasets.storage import store_bytes
    from tests.test_cimp_ux_57 import _binding, KEY, SECRET
    backend = KitLocalCiphertextBackend(tmp_path / "kit-bytes")
    with pytest.raises(PrivateStorageError):
        backend.add(SECRET)
    envelope = seal_private_artifact(SECRET, binding=_binding("evidence"), key=KEY, key_id="key-byte-api")
    stored = store_bytes(envelope, backend=backend, backend_name=backend.backend_name, pin_content=True)
    assert stored["status"] == "available", stored
    assert stored["stored_local"] is True and stored["verified"] is True
    assert stored["uploaded"] is False and stored["pinned"] is False and stored["network_durable"] is False
    cid = stored["cid"]
    assert backend.cat(cid) == envelope
    backend.close()
    reopened = KitLocalCiphertextBackend.reopen(tmp_path / "kit-bytes")
    assert reopened.cat(cid) == envelope
    assert SECRET not in b"".join(p.read_bytes() for p in reopened._root.rglob("*") if p.is_file())
    reopened.close()
