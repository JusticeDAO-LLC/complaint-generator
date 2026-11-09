"""Finite interview stops stay visible and do not invent support.

Saturation, cap, pause, cancellation, and an unavailable capability stop with
unresolved reasons. Waiting for the user is not a development worker stall.
Claim elements become supported only from source-bound factual or legal
evidence. A finished interview is not legal sufficiency.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]
USER_ID = "synthetic-gui-19"
PASSPHRASE = "synthetic-gui-19-passphrase"
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
    app = FastAPI()
    app.include_router(create_complaint_workspace_router(service, trusted_local=True))
    return TestClient(app)


def _codes(outcome):
    return [item.get("code") for item in outcome.get("unresolved_reasons") or []]


def test_fixed_form_answers_do_not_promote_claim_elements_to_supported(tmp_path):
    client = _client(_service(tmp_path))
    saved = client.post("/api/complaint-workspace/intake", json={"user_id": USER_ID, "answers": FIXED_ANSWERS})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    review = body["review"]
    matrix = review["support_matrix"]
    assert len(matrix) == 5
    assert review["legal_sufficiency"] is False
    assert review["interview_completion_means_legal_sufficiency"] is False
    assert review["overview"]["supported_elements"] == 0
    assert review["overview"]["missing_elements"] == 5
    for item in matrix:
        assert item["intake_asserted"] is True
        assert item["intake_supported"] is False
        assert item["supported"] is False
        assert item["legal_sufficiency"] is False
        assert item["source_bound_count"] == 0
        assert item["status"] == "needs_source_bound_evidence"
    outcome = body["finite_interview_outcome"]
    assert outcome["legal_sufficiency"] is False
    assert outcome["interview_completion_means_legal_sufficiency"] is False
    assert outcome["user_waiting_is_worker_stall"] is False
    assert outcome["stop"] != "saturated"
    assert "interview_completion_is_not_legal_sufficiency" in _codes(outcome)
    assert outcome["reasons_visible"] is True


def test_only_source_bound_evidence_supports_a_claim_element(tmp_path):
    client = _client(_service(tmp_path))
    client.post("/api/complaint-workspace/intake", json={"user_id": USER_ID, "answers": FIXED_ANSWERS})
    bare = client.post(
        "/api/complaint-workspace/evidence",
        json={
            "user_id": USER_ID,
            "kind": "testimony",
            "claim_element_id": "harm",
            "title": "Unsourced account",
            "content": "I lost wages.",
            "source": "intake",
        },
    )
    assert bare.status_code == 200, bare.text
    bare_row = next(item for item in bare.json()["review"]["support_matrix"] if item["id"] == "harm")
    assert bare_row["testimony_count"] == 1
    assert bare_row["supported"] is False
    assert bare_row["legal_sufficiency"] is False

    sourced = client.post(
        "/api/complaint-workspace/evidence",
        json={
            "user_id": USER_ID,
            "kind": "document",
            "claim_element_id": "adverse_action",
            "title": "Termination letter",
            "content": "Employment ended March 4.",
            "source": "personnel-file:termination-letter-2024-03-04",
        },
    )
    assert sourced.status_code == 200, sourced.text
    review = sourced.json()["review"]
    rows = {item["id"]: item for item in review["support_matrix"]}
    assert rows["adverse_action"]["supported"] is True
    assert rows["adverse_action"]["source_bound_count"] == 1
    assert rows["adverse_action"]["legal_sufficiency"] is False
    assert rows["harm"]["supported"] is False
    assert rows["protected_activity"]["supported"] is False
    assert review["overview"]["supported_elements"] == 1
    assert review["legal_sufficiency"] is False
    assert review["interview_completion_means_legal_sufficiency"] is False


def test_user_waiting_is_not_a_development_worker_stall(tmp_path):
    service = _service(tmp_path)
    client = _client(service)
    client.post("/api/complaint-workspace/intake", json={"user_id": USER_ID, "answers": {"party_name": "Ada Example"}})
    state = service._load_state(USER_ID)
    state["worker_stalled"] = True
    service._save_state(state)
    session = client.get("/api/complaint-workspace/session", params={"user_id": USER_ID})
    assert session.status_code == 200, session.text
    outcome = session.json()["finite_interview_outcome"]
    assert outcome["user_waiting"] is True
    assert outcome["worker_stalled"] is False
    assert outcome["user_waiting_is_worker_stall"] is False
    assert outcome["stop"] == "awaiting_user"
    assert outcome["legal_sufficiency"] is False
    assert any(item["code"] == "awaiting_user" for item in outcome["unresolved_reasons"])


@pytest.mark.parametrize("action,stop,reason", [
    ("pause", "paused", "user_pause"),
    ("cancel", "cancelled", "cancellation"),
    ("cap", "capped", "cap"),
    ("unavailable", "unavailable", "capability_unavailable"),
    ("saturate", "saturated", "source_research"),
])
def test_finite_stops_keep_unresolved_reasons_visible(tmp_path, action, stop, reason):
    client = _client(_service(tmp_path))
    client.post("/api/complaint-workspace/intake", json={"user_id": USER_ID, "answers": FIXED_ANSWERS})
    stopped = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": "", "interview_action": action},
    )
    assert stopped.status_code == 200, stopped.text
    body = stopped.json()
    outcome = body["finite_interview_outcome"]
    assert outcome["schema"] == "finite-interview-outcome-v1"
    assert outcome["stop"] == stop
    assert outcome["reasons_visible"] is True
    assert outcome["legal_sufficiency"] is False
    assert outcome["interview_completion_means_legal_sufficiency"] is False
    assert outcome["filing_ready"] is False
    assert outcome["core_facts_complete"] is False
    assert outcome["user_waiting_is_worker_stall"] is False
    assert outcome["worker_stalled"] is False
    assert body["legal_sufficiency"] is False
    assert body["stored_as_answer"] is False
    codes = _codes(outcome)
    assert reason in codes
    assert "interview_completion_is_not_legal_sufficiency" in codes
    assert outcome["unresolved_reasons"]
    if action == "pause":
        assert outcome["user_waiting"] is True
        assert outcome["stop"] != "no_progress"
    if action == "saturate":
        assert outcome["interview_complete"] is False or outcome["legal_sufficiency"] is False
        matrix = body["review"]["support_matrix"]
        assert all(item["supported"] is False for item in matrix)


def test_workspace_template_renders_finite_stops_without_false_support():
    html = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    assert 'id="finite-interview-outcome"' in html
    assert "Waiting for the user is not a development worker stall." in html
    assert "Interview completion is not legal sufficiency." in html
    assert "source-bound factual or legal evidence" in html
    assert "finite-interview-pause" in html
    assert "finite-interview-cancel" in html
    assert "renderFiniteInterviewOutcome" in html
    assert "intake_supported" not in html.split("function describeSupportStrength")[1].split("function renderReview")[0]
