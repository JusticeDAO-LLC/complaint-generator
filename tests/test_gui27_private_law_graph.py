"""Current encrypted law-graph reads use the actual issued case owner."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.complaint_workspace import ComplaintWorkspaceService
from tests.test_cimp_gui_14 import (
    PASSPHRASE, _composed_case_world, _composed_ciphertext_snapshot,
    _composed_headers, _composed_login,
)
from tests.test_gui24_private_context import _start

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _app(world, service, mediator=None):
    registry = CaseHandlerRegistry()
    registry.bind(world.case, mediator=service if mediator is None else mediator,
                  workspace_service=service)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
                        case_handlers=registry, include_review=False, include_document=False)
    return app


def test_actual_owner_reads_saved_dependency_graph_without_writing(tmp_path):
    world = _composed_case_world(tmp_path)
    assert world.owner.principal_id != world.case.tenant_id
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
        before = _composed_ciphertext_snapshot(world.services[world.case.case_id])
        response = client.get(f"/api/graphs/{world.case.case_id}/legal-dependency", headers=_composed_headers(world.case))
        assert response.status_code == 200, response.text
        assert response.json()["case_id"] == world.case.case_id
        assert response.json()["admitted_count"] == 0
        assert response.json()["research_gap"] == "unresolved_current_legal_context"
        assert response.json()["proof"] is False
        assert _composed_ciphertext_snapshot(world.services[world.case.case_id]) == before


def test_real_cached_mediator_cannot_bypass_current_workspace_key_lock(tmp_path):
    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
    cached = service._interview_mediators[(world.case.tenant_id, world.case.case_id)]
    with TestClient(_app(world, service, cached), base_url="https://testserver") as client:
        _composed_login(client)
        path = f"/api/graphs/{world.case.case_id}/legal-dependency"
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 200
        service.lock_private_keys()
        before = _composed_ciphertext_snapshot(service)
        denied = client.get(path, headers=_composed_headers(world.case))
        assert denied.status_code == 503, denied.text
        assert denied.json()["error"] == "unlock_needed"
        assert denied.json()["task_id"] == "CIMP-GUI-27"
        assert _composed_ciphertext_snapshot(service) == before


def test_saved_dependency_graph_cold_reopens_only_after_actual_owner_unlock(tmp_path):
    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        _start(client, world.case)
    fresh = ComplaintWorkspaceService(root_dir=service._session_dir)
    before = _composed_ciphertext_snapshot(fresh)
    with TestClient(_app(world, fresh), base_url="https://testserver") as client:
        _composed_login(client)
        path = f"/api/graphs/{world.case.case_id}/legal-dependency"
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 503
        fresh.unlock_private_keys(passphrase=PASSPHRASE)
        current = client.get(path, headers=_composed_headers(world.case))
        assert current.status_code == 200, current.text
        assert current.json()["admitted_count"] == 0
        assert _composed_ciphertext_snapshot(fresh) == before
