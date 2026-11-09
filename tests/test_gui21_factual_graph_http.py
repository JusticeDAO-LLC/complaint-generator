"""Real encrypted case reads, not a cached mediator's authorization boolean."""

from __future__ import annotations

from threading import Event, Thread
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.complaint_workspace import ComplaintWorkspaceService
from complaint_phases.knowledge_graph import KnowledgeGraph
from tests.test_cimp_gui_14 import (
    NARRATIVE,
    ANSWER,
    PASSPHRASE,
    _composed_case_world,
    _composed_ciphertext_snapshot,
    _composed_headers,
    _composed_login,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _start(client, case):
    csrf = _composed_login(client)
    result = client.post("/api/complaint-workspace/intake-chat", headers=_composed_headers(case, csrf),
        json={"message": NARRATIVE, "interview_action": "start"})
    assert result.status_code == 200, result.text
    return csrf


class _CachedGraphHook:
    """Adversarial stale cache; it is never an encrypted-read authority."""

    def __init__(self, graph):
        self.phase_manager = self
        self.graph = graph

    def get_phase_data(self, _phase, key):
        return self.graph if key == "knowledge_graph" else None


def _with_workspace(world, workspace, *, mediator=None):
    registry = CaseHandlerRegistry()
    registry.bind(world.case, mediator=mediator or workspace, workspace_service=workspace)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=registry, include_review=False, include_document=False)
    return app


def test_factual_graph_reads_real_encrypted_workspace_for_distinct_actor_and_tenant(tmp_path):
    world = _composed_case_world(tmp_path)
    assert world.case.tenant_id != world.owner.principal_id
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
        before = _composed_ciphertext_snapshot(service)
        response = client.get(f"/api/graphs/{world.case.case_id}/factual",
            headers=_composed_headers(world.case))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "projected"
        assert body["case_id"] == world.case.case_id
        assert body["read_only"] is True
        assert body["user_statements"] or body["allegations"] or body["hypotheses"]
        assert _composed_ciphertext_snapshot(service) == before


def test_cached_mediator_cannot_release_graph_when_actual_private_key_is_locked(tmp_path):
    world = _composed_case_world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
        saved = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case))
        assert saved.status_code == 200, saved.text
        graph = KnowledgeGraph.from_dict(saved.json()["session"]["shared_interview"]["knowledge_graph"])
    app = _with_workspace(world, world.services[world.case.case_id], mediator=_CachedGraphHook(graph))
    service = world.services[world.case.case_id]
    with TestClient(app, base_url="https://testserver") as client:
        _composed_login(client)
        path = f"/api/graphs/{world.case.case_id}/factual"
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 200
        service.lock_private_keys()
        before = _composed_ciphertext_snapshot(service)
        response = client.get(path, headers=_composed_headers(world.case))
        assert response.status_code == 503, response.text
        assert response.json()["error"] == "unlock_needed"
        assert _composed_ciphertext_snapshot(service) == before


def test_factual_graph_requires_real_cookie_case_owner_and_matching_path(tmp_path):
    world = _composed_case_world(tmp_path)
    path = f"/api/graphs/{world.case.case_id}/factual"
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 401
        _start(client, world.case)
        before = _composed_ciphertext_snapshot(world.services[world.case.case_id])
        assert client.get(f"/api/graphs/{world.second.case_id}/factual",
            headers=_composed_headers(world.case)).status_code == 403
        assert client.get(path + "?case_id=" + world.second.case_id,
            headers=_composed_headers(world.case)).status_code == 403
        assert client.get(path, headers={**_composed_headers(world.case),
            "x-actor-principal-id": world.stranger.principal_id}).status_code == 403
        _composed_login(client, "synthetic-stranger-credential")
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 403
        assert _composed_ciphertext_snapshot(world.services[world.case.case_id]) == before


def test_policy_membership_cannot_borrow_owner_master_for_graph_read(tmp_path):
    world = _composed_case_world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
        grant = world.authorizer.grant_assigned_lawyer(owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id, tenant_id=world.case.tenant_id,
            case_id=world.case.case_id, resource_id=world.case.resource_id,
            actions={"case.read"}, expected_case_revision=world.case.revision)
        _composed_login(client, "synthetic-lawyer-credential")
        response = client.get(f"/api/graphs/{world.case.case_id}/factual",
            headers={**_composed_headers(world.case), "x-expected-membership-revision": str(grant.revision)})
        assert response.status_code == 403, response.text
        assert NARRATIVE not in response.text


def test_cached_graph_without_real_private_workspace_is_unavailable(tmp_path):
    world = _composed_case_world(tmp_path)
    app = _with_workspace(world, SimpleNamespace(case_id=world.case.case_id),
        mediator=_CachedGraphHook(KnowledgeGraph()))
    with TestClient(app, base_url="https://testserver") as client:
        _composed_login(client)
        response = client.get(f"/api/graphs/{world.case.case_id}/factual",
            headers=_composed_headers(world.case))
        assert response.status_code == 503
        assert response.json()["error"] == "workspace_graph_read_unavailable"


def test_cold_workspace_uses_persisted_graph_only_after_real_key_unlock(tmp_path):
    world = _composed_case_world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
    reopened = ComplaintWorkspaceService(root_dir=tmp_path / "workspaces" / world.case.case_id)
    app = _with_workspace(world, reopened)
    before = _composed_ciphertext_snapshot(reopened)
    with TestClient(app, base_url="https://testserver") as client:
        _composed_login(client)
        path = f"/api/graphs/{world.case.case_id}/factual"
        response = client.get(path, headers=_composed_headers(world.case))
        assert response.status_code == 503 and response.json()["error"] == "unlock_needed"
        reopened.unlock_private_keys(passphrase="synthetic-wrong-passphrase")
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 503
        reopened.unlock_private_keys(passphrase=PASSPHRASE)
        response = client.get(path, headers=_composed_headers(world.case))
        assert response.status_code == 200, response.text
        assert response.json()["case_id"] == world.case.case_id
        assert _composed_ciphertext_snapshot(reopened) == before


@pytest.mark.parametrize("change,expected_status,expected_code", [
    ("logout", 403, "graph_read_ungranted"),
    ("rotate", 403, "graph_read_ungranted"),
    ("expire", 403, "graph_read_ungranted"),
    ("key_lock", 503, "unlock_needed"),
    ("source_revision", 409, "graph_revision_changed"),
])
def test_late_live_authority_key_or_source_change_refuses_graph_publication(
        tmp_path, monkeypatch, change, expected_status, expected_code):
    from applications import graph_api

    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    entered, release = Event(), Event()
    original = graph_api.project_factual_kg

    def wait_after_real_projection(graph, *, case_id):
        result = original(graph, case_id=case_id)
        entered.set()
        if not release.wait(10):
            raise AssertionError("bounded graph projection interleaving did not release")
        return result

    monkeypatch.setattr(graph_api, "project_factual_kg", wait_after_real_projection)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        saved = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case))
        inquiry = saved.json()["session"]["shared_interview"]["pending_inquiry"]
        before = _composed_ciphertext_snapshot(service)
        results, errors = [], []

        def read():
            try:
                results.append(client.get(f"/api/graphs/{world.case.case_id}/factual",
                    headers=_composed_headers(world.case)))
            except BaseException as exc:
                errors.append(exc)

        worker = Thread(target=read, daemon=True)
        worker.start()
        try:
            assert entered.wait(10), "actual graph projection was not reached"
            if change in {"logout", "rotate"}:
                changed = client.post("/api/complaint-workspace/auth/" + change,
                    headers={"x-csrf-token": csrf})
                assert changed.status_code == 200, changed.text
            elif change == "expire":
                world.clock["now"] += 301
            elif change == "key_lock":
                service.lock_private_keys()
            else:
                changed = client.post("/api/complaint-workspace/intake-chat",
                    headers=_composed_headers(world.case, csrf), json={"message": ANSWER,
                        "interview_action": "answer", "question_id": inquiry["inquiry_id"],
                        "expected_question_revision": inquiry["revision"]})
                assert changed.status_code == 200, changed.text
                assert changed.json()["interview"]["session_revision"] > saved.json()["session"]["shared_interview"]["session_revision"]
                before = _composed_ciphertext_snapshot(service)
        finally:
            release.set()
            worker.join(10)
        assert not worker.is_alive(), "owned read thread did not terminate"
        if errors:
            raise errors[0]
        assert len(results) == 1
        response = results[0]
        assert response.status_code == expected_status, response.text
        assert response.json()["error"] == expected_code
        assert NARRATIVE not in response.text
        assert not any(key in response.json() for key in ("user_statements", "evidence_revisions", "allegations", "hypotheses"))
        assert _composed_ciphertext_snapshot(service) == before
