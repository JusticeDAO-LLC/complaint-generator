"""Actual authorized private-session HTTP states, without a fabricated key flag."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from integrations.private_storage import ENVELOPE_MAGIC
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import NARRATIVE, PASSPHRASE

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
PATH = "/api/complaint-workspace/session"


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    return response.json()


def _scope(world):
    return {"x-tenant-id": world.case.tenant_id, "x-case-id": world.case.case_id,
        "x-resource-id": world.case.resource_id, "x-expected-revision": str(world.case.revision)}


def _get(client, world):
    return client.get(PATH, params={"case_id": world.case.case_id}, headers=_scope(world))


def test_current_owner_get_reports_real_lock_without_plaintext_or_overwrite(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with TestClient(world.app, base_url="https://testserver") as client:
        issued = _login(client, "synthetic-owner-credential")
        assert issued["principal_id"] == world.owner.principal_id
        fresh = _get(client, world)
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()["session"]["user_id"] == world.case.tenant_id
        forged = client.get(PATH, params={"user_id": world.case.tenant_id, "case_id": world.case.case_id}, headers=_scope(world))
        assert forged.status_code == 403 and "session" not in forged.json()
        started = client.post("/api/complaint-workspace/intake-chat",
            headers={**_scope(world), "x-csrf-token": issued["csrf_token"]},
            json={"message": NARRATIVE,
                "question_id": "original_complaint", "interview_action": "start"})
        assert started.status_code == 200
        inquiry = started.json()["adaptive_inquiry"]
        assert inquiry["source"] == "shared_mediator" and inquiry["pending"] is True
        available = _get(client, world)
        assert available.status_code == 200
        assert available.json()["session"]["user_id"] == world.case.tenant_id
        assert available.json()["session"]["shared_interview"]["pending_inquiry"]["inquiry_id"] == inquiry["inquiry_id"]
        sealed = {path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in world.service._session_dir.rglob("*")
            if path.is_file() and path.read_bytes().startswith(ENVELOPE_MAGIC)}
        assert sealed and all(NARRATIVE.encode() not in path.read_bytes() for path in sealed)
        world.owner_keys.lock()
        assert world.service.lock_private_keys()["unlocked"] is False
        locked = _get(client, world)
        assert locked.status_code == 503
        assert locked.json() == {"status": "unavailable", "error": "unlock_needed", "session_readable": False}
        assert NARRATIVE not in locked.text and PASSPHRASE not in locked.text
        assert str(tmp_path) not in locked.text and "session" not in locked.json()
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in sealed.items())
        assert world.service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
        resumed = _get(client, world)
        assert resumed.status_code == 200
        assert resumed.json()["session"]["shared_interview"]["pending_inquiry"]["inquiry_id"] == inquiry["inquiry_id"]
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in sealed.items())


def test_session_read_stays_closed_to_anonymous_and_foreign_actors(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with TestClient(world.app, base_url="https://testserver") as client:
        anonymous = _get(client, world)
        assert anonymous.status_code in {401, 403}
        issued = _login(client, "synthetic-stranger-credential")
        assert issued["principal_id"] == world.stranger.principal_id != world.owner.principal_id
        foreign = _get(client, world)
        assert foreign.status_code in {403, 404}
        assert "session" not in foreign.json()
        assert NARRATIVE not in foreign.text and PASSPHRASE not in foreign.text
        assert str(tmp_path) not in foreign.text
