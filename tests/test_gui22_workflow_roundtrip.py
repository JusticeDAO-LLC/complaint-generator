"""Factual-review persistence through the actual shared interview owner."""
from fastapi.testclient import TestClient
import pytest

from tests.test_cimp_gui_14 import ANSWER, _composed_case_world, _composed_headers
from tests.test_gui24_private_context import _start

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_review_replay_is_read_only_and_next_intake_answer_retains_saved_hypothesis(tmp_path):
    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _start(client, world.case)
        headers = _composed_headers(world.case, csrf)
        path = f"/api/graphs/{world.case.case_id}/factual"
        before = client.get(path, headers=headers)
        assert before.status_code == 200, before.text
        session = client.get("/api/complaint-workspace/session", headers=headers).json()["session"]
        pending = session["shared_interview"]["pending_inquiry"]
        body = {"review_action": "propose", "origin": "model", "event_id": "synthetic-roundtrip-review",
                "text": "Synthetic persistent factual hypothesis.",
                "expected_graph_revision": before.json()["factual_review_revision"]}
        saved = client.post(path + "/reviews", headers=headers, json=body)
        assert saved.status_code == 200 and saved.json()["graph_mutated"] is True, saved.text
        repository = service.joined_revision_repository(world.case.tenant_id, world.case.case_id)
        head = (repository / "head.cgpe").read_bytes()
        replay = client.post(path + "/reviews", headers=headers, json=body)
        assert replay.status_code == 200 and replay.json()["idempotent_replay"] is True, replay.text
        assert replay.json()["graph_mutated"] is False
        assert replay.json()["proposal_id"] == saved.json()["proposal_id"]
        assert (repository / "head.cgpe").read_bytes() == head
        answer = client.post("/api/complaint-workspace/intake-chat", headers=headers, json={
            "message": ANSWER, "interview_action": "answer", "question_id": pending["inquiry_id"],
            "expected_question_revision": pending["revision"],
        })
        assert answer.status_code == 200, answer.text
        current = client.get(path, headers=headers)
        assert current.status_code == 200, current.text
        assert any(item["text"] == body["text"] for item in current.json()["hypotheses"])
        assert all(item["admitted_user_fact"] is False for item in current.json()["hypotheses"])
