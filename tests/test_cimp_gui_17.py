"""Inquiry explanations name the factual target and a separate legal source.

Why and Review do not store an answer or change the legal dependency graph.
The explanation id and revision survive a new session read and a browser reload.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

USER_ID = "synthetic-gui-17"
PASSPHRASE = "synthetic-gui-17-passphrase"
NARRATIVE = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns. I worked at Northwind Tools."


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
    return started.json()


def _explanation(body):
    pending = body["session"]["shared_interview"]["pending_inquiry"]
    explanation = pending["inquiry_explanation"]
    assert explanation["schema"] == "inquiry-explanation-v1"
    return pending, explanation


def _law_fingerprint(body):
    graph = body["session"]["shared_interview"]["dependency_graph"]
    nodes = graph.get("nodes") or {}
    rows = []
    for node_id in sorted(nodes):
        node = nodes[node_id] or {}
        attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        rows.append((node_id, node.get("name"), node.get("satisfied"), attributes.get("citation"), attributes.get("source_passage_id")))
    return rows


def _history_answers(body):
    history = body["session"].get("intake_history") or []
    return [item.get("answer") for item in history if isinstance(item, dict)]


def test_pending_question_explains_target_and_distinct_graph_sources(tmp_path):
    body = _start(_client(_service(tmp_path)))
    pending, explanation = _explanation(body)
    factual = explanation["factual_target"]
    law = explanation["sourced_legal_requirement"]
    assert explanation["why_asked"]
    assert explanation["inquiry_id"] == pending["inquiry_id"]
    assert explanation["revision"] == pending["revision"]
    assert factual["kind"] == "factual"
    assert factual["graph_kind"] == "factual_knowledge_graph"
    assert factual["target_id"]
    assert law["graph_kind"] == "legal_dependency_graph"
    assert law["law_derived"] is (law["provenance"]["status"] == "sourced")
    assert explanation["stores_answer"] is False
    assert explanation["changes_law"] is False
    assert explanation["legal_sufficiency"] is False
    sources = explanation["graph_sources"]
    assert [item["graph_kind"] for item in sources] == ["factual_knowledge_graph", "legal_dependency_graph"]
    assert sources[0]["role"] == "factual_target"
    assert sources[1]["role"] == "sourced_legal_requirement"
    assert sources[0]["graph_kind"] != sources[1]["graph_kind"]
    provenance = law["provenance"]
    assert provenance["inspectable"] is True
    assert provenance["changes_law"] is False
    assert provenance["graph_kind"] == "legal_dependency_graph"
    graph_nodes = body["session"]["shared_interview"]["dependency_graph"].get("nodes") or {}
    if provenance["status"] == "sourced":
        matched = graph_nodes[provenance["node_id"]]
        attributes = matched.get("attributes") or {}
        assert provenance["citation"] == (attributes.get("citation") or "unknown")
        assert provenance["model_authored"] is False
        assert NARRATIVE not in json.dumps(provenance)
    else:
        assert provenance["status"] == "unknown"
        assert provenance["citation"] == "unknown"
        assert law["law_derived"] is False
        assert law["requirement_id"] == "unknown" or provenance["node_id"] in {"unknown", law["requirement_id"]}


def test_why_and_review_do_not_store_an_answer_or_change_law(tmp_path):
    service = _service(tmp_path)
    client = _client(service)
    started = _start(client)
    pending, explanation = _explanation(started)
    law_before = _law_fingerprint(started)
    answers_before = _history_answers(started)
    why = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": "/why", "question_id": pending["inquiry_id"]},
    )
    assert why.status_code == 200, why.text
    why_body = why.json()
    assert why_body["command"] == "/why"
    assert why_body["stored_as_answer"] is False
    assert why_body["legal_sufficiency"] is False
    why_pending, why_explanation = _explanation(why_body)
    assert why_explanation["explanation_id"] == explanation["explanation_id"]
    assert why_explanation["revision"] == explanation["revision"]
    assert why_pending["inquiry_id"] == pending["inquiry_id"]
    assert _law_fingerprint(why_body) == law_before
    assert _history_answers(why_body) == answers_before
    assert "/why" not in _history_answers(why_body)
    support = why_body["question_support"]
    assert support["legal_sufficiency"] is False
    assert support["factual_target"]["target_id"] == why_explanation["factual_target"]["target_id"]
    review = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": "", "interview_action": "review"},
    )
    assert review.status_code == 200, review.text
    review_body = review.json()
    assert review_body.get("stored_as_answer") is not True
    assert review_body.get("accepted_answer") in (None, {})
    reviewed, review_explanation = _explanation(review_body)
    assert review_explanation["explanation_id"] == explanation["explanation_id"]
    assert review_explanation["revision"] == explanation["revision"]
    assert reviewed["revision"] == pending["revision"]
    assert _law_fingerprint(review_body) == law_before
    assert _history_answers(review_body) == answers_before
    assert review_body["session"]["shared_interview"]["dependency_graph"]["nodes"].keys() == started["session"]["shared_interview"]["dependency_graph"]["nodes"].keys()
    reloaded = client.get("/api/complaint-workspace/session", params={"user_id": USER_ID})
    assert reloaded.status_code == 200, reloaded.text
    _reloaded_pending, reloaded_explanation = _explanation(reloaded.json())
    assert reloaded_explanation["explanation_id"] == explanation["explanation_id"]
    assert reloaded_explanation["revision"] == explanation["revision"]
    assert _law_fingerprint(reloaded.json()) == law_before


def test_unasked_session_has_no_explanation_identity(tmp_path):
    client = _client(_service(tmp_path))
    session = client.get("/api/complaint-workspace/session", params={"user_id": USER_ID})
    assert session.status_code == 200, session.text
    body = session.json()
    shared = (body.get("session") or {}).get("shared_interview")
    assert not shared or not (shared.get("pending_inquiry") or {}).get("inquiry_explanation")
    assert body["adaptive_inquiry"]["pending"] is False
    refused = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": "/why"},
    )
    assert refused.status_code == 200, refused.text
    payload = refused.json()
    assert payload["stored_as_answer"] is False
    assert payload["command"] == "/why"
    assert _history_answers(payload) == []
    assert "inquiry_explanation" not in json.dumps(payload.get("session") or {}) or not (
        ((payload.get("session") or {}).get("shared_interview") or {}).get("pending_inquiry") or {}
    ).get("inquiry_explanation")


def test_browser_keeps_explanation_identity_across_why_review_and_reload(tmp_path, monkeypatch):
    from tests.test_cimp_gui_15 import _page

    with _page(tmp_path, monkeypatch) as (_world, page):
        assert page.locator("#inquiry-explanation").get_attribute("data-task") == "CIMP-GUI-17"
        assert page.get_attribute("#inquiry-explanation", "data-explanation-id") == ""
        page.fill("#adaptive-narrative", NARRATIVE)
        page.click("#adaptive-enter-narrative")
        page.wait_for_function("document.getElementById('inquiry-explanation').dataset.explanationId.startsWith('exp-')")
        explanation_id = page.get_attribute("#inquiry-explanation", "data-explanation-id")
        revision = page.get_attribute("#inquiry-explanation", "data-revision")
        kinds = page.get_attribute("#inquiry-explanation", "data-graph-kinds")
        assert kinds == "factual_knowledge_graph,legal_dependency_graph"
        assert page.locator("#inquiry-explanation-sources li").count() == 2
        assert "Factual target" in page.text_content("#inquiry-explanation-factual")
        assert "Legal requirement" in page.text_content("#inquiry-explanation-law")
        assert page.text_content("#inquiry-explanation-why")
        page.click("#inquiry-why")
        page.wait_for_function("document.getElementById('inquiry-explanation-status').dataset.action === 'why'")
        assert page.get_attribute("#inquiry-explanation-status", "data-stored-as-answer") == "false"
        assert page.get_attribute("#inquiry-explanation-status", "data-changes-law") == "false"
        assert page.get_attribute("#inquiry-explanation-status", "data-identity-preserved") == "true"
        assert page.get_attribute("#inquiry-explanation", "data-explanation-id") == explanation_id
        assert page.get_attribute("#inquiry-explanation", "data-revision") == revision
        assert page.input_value("#adaptive-answer") == ""
        page.click("#inquiry-review")
        page.wait_for_function("document.getElementById('inquiry-explanation-status').dataset.action === 'review'")
        assert page.get_attribute("#inquiry-explanation-status", "data-stored-as-answer") == "false"
        assert page.get_attribute("#inquiry-explanation-status", "data-identity-preserved") == "true"
        assert page.get_attribute("#inquiry-explanation", "data-explanation-id") == explanation_id
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("['ready', 'partial', 'denied', 'error'].includes(document.body.dataset.workspaceHydrated)")
        page.wait_for_function(
            "(id) => document.getElementById('inquiry-explanation').dataset.explanationId === id",
            arg=explanation_id,
        )
        assert page.get_attribute("#inquiry-explanation", "data-revision") == revision
        assert page.get_attribute("#inquiry-explanation", "data-changes-law") == "false"
        assert page.get_attribute("#inquiry-explanation", "data-stores-answer") == "false"
