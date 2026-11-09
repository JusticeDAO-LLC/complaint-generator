"""Browser narrative entry follows the shared mediator inquiry.

Fixed intake fields do not select the next question. Unknown and deferred
answers keep the graph gap. Model extraction and question generation wait
for persisted per-case consent and a minimized purpose.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from applications.case_consent_api import CaseConsentService
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router
from applications.server import SERVER
from tests.test_cimp_gui_14 import _composed_case_world, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

USER_ID = "synthetic-gui-16"
PASSPHRASE = "synthetic-gui-16-passphrase"
NARRATIVE = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns. I worked at Northwind Tools."
ANSWER = "Alex Rivera was my supervisor at Northwind Tools and fired me on March 4, 2024."
FRAGMENT = "supervisor Alex Rivera fired me after I reported safety concerns"
FIXED_ANSWERS = {
    "party_name": "Ada Example",
    "opposing_party": "Northwind Tools",
    "protected_activity": "I reported a safety concern.",
    "adverse_action": "I was fired.",
    "timeline": "The report was March 1 and the firing was March 4.",
    "harm": "I lost wages.",
}


def _service(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    return service


def _client(service):
    app = __import__("fastapi").FastAPI()
    app.include_router(create_complaint_workspace_router(service, trusted_local=True))
    return TestClient(app)


def _start(client):
    started = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": NARRATIVE, "question_id": "original_complaint", "interview_action": "start"},
    )
    assert started.status_code == 200, started.text
    body = started.json()
    inquiry = body["interview"]["inquiry"]
    assert body["pending_inquiry_id"] == inquiry["inquiry_id"]
    assert str(inquiry["inquiry_id"]).startswith("inq-")
    view = body["adaptive_inquiry"]
    assert view["schema"] == "adaptive-inquiry-v1"
    assert view["source"] == "shared_mediator"
    assert view["pending"] is True
    assert view["from_fixed_intake_fields"] is False
    assert view["inquiry_id"] == inquiry["inquiry_id"]
    assert view["prompt"] == inquiry["question"]
    assert view["inquiry_id"] not in view["fixed_intake_question_ids"]
    assert view["legal_sufficiency"] is False
    return body


def _answer(client, body, message):
    inquiry = body["interview"]["inquiry"]
    answered = client.post(
        "/api/complaint-workspace/intake-chat",
        json={
            "user_id": USER_ID,
            "message": message,
            "question_id": inquiry["inquiry_id"],
            "expected_question_revision": inquiry["revision"],
            "interview_action": "answer",
        },
    )
    assert answered.status_code == 200, answered.text
    return answered.json()


def test_fixed_intake_does_not_enter_the_mediator_inquiry(tmp_path):
    client = _client(_service(tmp_path))
    saved = client.post("/api/complaint-workspace/intake", json={"user_id": USER_ID, "answers": FIXED_ANSWERS})
    assert saved.status_code == 200, saved.text
    view = saved.json()["adaptive_inquiry"]
    assert view["pending"] is False
    assert view["inquiry_id"] is None
    assert view["from_fixed_intake_fields"] is False
    assert view["source"] == "shared_mediator"
    session = saved.json()["session"]
    assert "shared_interview" not in session or not (session.get("shared_interview") or {}).get("pending_inquiry")


def test_narrative_then_answer_follows_mediator_gaps_not_fixed_fields(tmp_path):
    client = _client(_service(tmp_path))
    started = _start(client)
    answered = _answer(client, started, ANSWER)
    nxt = answered["adaptive_inquiry"]
    assert nxt["pending"] is True
    assert nxt["inquiry_id"].startswith("inq-")
    assert nxt["inquiry_id"] != started["pending_inquiry_id"]
    assert nxt["inquiry_id"] not in nxt["fixed_intake_question_ids"]
    assert nxt["from_fixed_intake_fields"] is False
    assert nxt["prompt"]
    assert (nxt["target_id"], nxt["revision"]) != (
        started["adaptive_inquiry"]["target_id"], started["adaptive_inquiry"]["revision"])
    assert answered["interview"]["session_revision"] > started["interview"]["session_revision"]
    assert nxt["preserved_gaps"] == []


@pytest.mark.parametrize("message,marker,disposition", [
    ("unknown", "user_answer_unknown", "unknown"),
    ("deferred", "user_answer_deferred", "deferred"),
])
def test_unknown_and_deferred_answers_preserve_the_graph_gap(tmp_path, message, marker, disposition):
    client = _client(_service(tmp_path))
    started = _start(client)
    answered = _answer(client, started, message)
    view = answered["adaptive_inquiry"]
    assert answered["gap_preserved"] is True
    assert marker in view["unknown_reasons"]
    gap = view["preserved_gaps"][-1]
    assert gap["inquiry_id"] == started["pending_inquiry_id"]
    assert gap["target_id"] == started["adaptive_inquiry"]["target_id"]
    assert gap["disposition"] == disposition
    assert gap["preserved"] is True
    assert gap["creates_fact"] is False
    assert gap["satisfies_requirement"] is False
    if view["pending"]:
        assert view["inquiry_id"].startswith("inq-")
        assert view["inquiry_id"] not in view["fixed_intake_question_ids"]
    session = answered["session"]["shared_interview"]
    assert session["preserved_gaps"][-1]["inquiry_id"] == started["pending_inquiry_id"]


def test_model_extraction_waits_for_persisted_consent_and_a_minimized_fragment(tmp_path):
    world = _composed_case_world(tmp_path)
    seen = []

    def transport(call):
        seen.append(call)
        return {"status": "available", "output": {"facts": [{"field": "act", "value": "fired", "target_ref": call["inputs"]["target_ref"]}]},
                "live_model_identity_verified": True, "observed_provider": "grok_cli", "observed_model": "grok-4.7"}

    world.consent = CaseConsentService(tmp_path / "consent", cases=world.cases, key=os.urandom(32),
        key_id="consent-key", clock=lambda: 1700000100)
    world.app = SERVER(None, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=world.handlers, case_consent=world.consent, gui_inference_transport=transport).app
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        headers = _composed_headers(world.case, csrf)
        started = client.post("/api/complaint-workspace/intake-chat", headers=headers,
            json={"message": NARRATIVE, "interview_action": "start"})
        assert started.status_code == 200, started.text
        body = started.json()
        target = body["graph_targets"]["target_id"]
        assert target
        blocked = client.post("/api/complaint-workspace/inference/dispatch", headers=headers,
            json={"purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": target}})
        assert blocked.json()["model_dispatched"] is False
        assert blocked.json()["code"] == "case_purpose_consent_required"
        assert seen == []
        endpoint = f"/api/cases/{world.case.case_id}/processing-consent"
        current = client.get(endpoint)
        assert current.status_code == 200, current.text
        chosen = client.post(endpoint, headers={"x-csrf-token": csrf}, json={
            "purpose": "extract_facts", "mode": "grok_cloud", "explicit_case_purpose": True,
            "expected_generation": current.json()["generation"],
        })
        assert chosen.status_code == 200, chosen.text
        whole = client.post("/api/complaint-workspace/inference/dispatch", headers=headers,
            json={"purpose": "extract_facts", "inputs": {"source_text": NARRATIVE, "target_ref": target}})
        assert whole.json()["model_dispatched"] is False
        assert whole.json()["code"] == "query_not_minimized"
        assert seen == []
        other = client.post("/api/complaint-workspace/inference/dispatch", headers=headers,
            json={"purpose": "propose_questions", "inputs": {"gap_code": "user_answer_unknown", "target_ref": target}})
        assert other.json()["code"] == "case_purpose_consent_required"
        assert seen == []
        held = client.post("/api/complaint-workspace/inference/dispatch", headers=headers,
            json={"purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": target}})
        assert held.status_code == 200, held.text
        assert held.json()["status"] == "held"
        assert len(seen) == 1
        assert seen[0]["inputs"] == {"source_text": FRAGMENT, "target_ref": target}
        assert NARRATIVE not in __import__("json").dumps(seen[0])
        assert seen[0]["purpose_id"] == "extract_facts"


def test_browser_renders_the_mediator_inquiry_and_blocks_unconsented_model(tmp_path, monkeypatch):
    from tests.test_cimp_gui_15 import _page
    with _page(tmp_path, monkeypatch) as (_world, page):
        assert page.locator("#adaptive-inquiry").get_attribute("data-task") == "CIMP-GUI-16"
        page.fill("#adaptive-narrative", NARRATIVE)
        page.click("#adaptive-enter-narrative")
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        inquiry_id = page.get_attribute("#adaptive-pending", "data-inquiry-id")
        prompt = page.text_content("#adaptive-pending-prompt")
        assert inquiry_id.startswith("inq-")
        assert prompt and "Complaint narrative" not in prompt
        assert page.get_attribute("#adaptive-pending", "data-from-fixed-intake") == "false"
        page.click("#adaptive-unknown")
        page.wait_for_function("document.getElementById('adaptive-gap-status').dataset.gapPreserved === 'true'")
        assert "unknown" in page.text_content("#adaptive-gap-status")
        assert inquiry_id in page.text_content("#adaptive-gap-status")
        page.fill("#adaptive-model-fragment", FRAGMENT)
        page.click("#adaptive-model-extract")
        page.wait_for_function("document.getElementById('adaptive-model-status').dataset.modelDispatched === 'false'")
        assert page.get_attribute("#adaptive-model-status", "data-code") == "case_purpose_consent_required"
        assert page.evaluate("window.adaptiveModelAttempts") == 0
