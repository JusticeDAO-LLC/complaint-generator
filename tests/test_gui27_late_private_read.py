"""Actual concurrent owner/session/key/source changes refuse late law views."""
from threading import Event, Thread

from fastapi.testclient import TestClient
import pytest

from tests.test_cimp_gui_14 import (
    ANSWER, _composed_case_world, _composed_ciphertext_snapshot, _composed_headers,
)
from tests.test_gui24_private_context import _start

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.mark.parametrize("change,status", [("logout", 403), ("expire", 403), ("key_lock", 503), ("source", 409)])
def test_real_law_projection_rechecks_after_concurrent_boundary(tmp_path, monkeypatch, change, status):
    from applications import graph_api

    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    entered, release = Event(), Event()
    project = graph_api.project_law_derived_dependency_graph

    def project_then_wait(*args, **kwargs):
        result = project(*args, **kwargs)
        entered.set()
        if not release.wait(10):
            raise AssertionError("bounded current law-view interleaving did not release")
        return result

    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        session = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case)).json()["session"]
        pending = session["shared_interview"]["pending_inquiry"]
        monkeypatch.setattr(graph_api, "project_law_derived_dependency_graph", project_then_wait)
        results, errors = [], []

        def read():
            try:
                results.append(client.get(f"/api/graphs/{world.case.case_id}/legal-dependency", headers=_composed_headers(world.case)))
            except BaseException as exc:
                errors.append(exc)

        worker = Thread(target=read, daemon=True)
        worker.start()
        try:
            assert entered.wait(10), "real current private graph was not projected"
            if change == "logout":
                assert client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf}).status_code == 200
            elif change == "expire":
                world.clock["now"] += 301
            elif change == "key_lock":
                service.lock_private_keys()
            else:
                answer = client.post("/api/complaint-workspace/intake-chat", headers=_composed_headers(world.case, csrf), json={
                    "message": ANSWER, "interview_action": "answer", "question_id": pending["inquiry_id"],
                    "expected_question_revision": pending["revision"],
                })
                assert answer.status_code == 200, answer.text
            before_release = _composed_ciphertext_snapshot(service)
        finally:
            release.set()
            worker.join(10)
        assert not worker.is_alive()
        if errors:
            raise errors[0]
        assert len(results) == 1 and results[0].status_code == status, results[0].text if results else "missing result"
        assert "requirements" not in results[0].json()
        assert _composed_ciphertext_snapshot(service) == before_release
