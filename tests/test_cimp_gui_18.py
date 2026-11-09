"""GUI corrections use mediator supersession.

A correction keeps the previous assertion, attributes the editor, and
invalidates support and proof that cited the corrected fact. A stale revision
or another participant's assertion is refused and does not overwrite them.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router
from complaint_phases.dependency_graph import DependencyGraph
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph, Relationship
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash
from mediator.hook_runtime import graph_revision_token


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

USER_ID = "synthetic-gui-18"
OTHER_ID = "synthetic-gui-18-other"
PASSPHRASE = "synthetic-gui-18-passphrase"
OWN_FACT = "I was fired on January 1, 2020."
OTHER_FACT = "Riley approved the warehouse schedule."
REPLACEMENT = "I was fired on January 2, 2020."


def _service(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    return service


def _client(service):
    app = __import__("fastapi").FastAPI()
    app.include_router(create_complaint_workspace_router(service, trusted_local=True))
    return TestClient(app)


def _envelope(text, message_id, actor):
    return build_user_assertion_envelope(
        source_text=text,
        source_kind="user_statement",
        source_id=message_id,
        message_id=message_id,
        assertion_status="asserted",
        extractor_version="gui18-test",
        source_hash=source_byte_hash(text),
        source_span={"start": 0, "end": len(text.encode("utf-8")), "text": text, "unit": "byte"},
        subject_key="employment-fact",
        actor=actor,
    )


def _seed(service):
    own = _envelope(OWN_FACT, "msg-own", USER_ID)
    other = _envelope(OTHER_FACT, "msg-other", OTHER_ID)
    graph = KnowledgeGraph()
    claim = Entity(id="claim-1", type="claim", name="Termination", attributes={"claim_type": "employment"}, confidence=0.8)
    own_fact = Entity(id="fact-own", type="fact", name=OWN_FACT, attributes={"description": OWN_FACT}, confidence=0.4, source="complaint",
                      provenance={"user_assertion": own.as_dict()})
    other_fact = Entity(id="fact-other", type="fact", name=OTHER_FACT, attributes={"description": OTHER_FACT}, confidence=0.4, source="complaint",
                        provenance={"user_assertion": other.as_dict()})
    graph.add_entity(claim)
    graph.add_entity(own_fact)
    graph.add_entity(other_fact)
    graph.register_assertion(own_fact, own, status="active", event_id="answer-own")
    graph.register_assertion(other_fact, other, status="active", event_id="answer-other")
    graph.add_relationship(Relationship(
        id="rel-own-support", source_id=own_fact.id, target_id=claim.id, relation_type="supports", confidence=0.9,
        attributes={"proof_cache": {"reusable": True, "satisfied": True, "fact_id": own_fact.id}, "proof_cache_entity_id": own_fact.id},
    ))
    graph.add_relationship(Relationship(
        id="rel-other-support", source_id=other_fact.id, target_id=claim.id, relation_type="supports", confidence=0.9,
        attributes={"proof_cache": {"reusable": True, "satisfied": True, "fact_id": other_fact.id}, "proof_cache_entity_id": other_fact.id},
    ))
    graph.metadata["case_id"] = USER_ID
    graph.append_revision({"action": "answer", "event_id": "answer-own", "statement": OWN_FACT, "stable_id": own.stable_id,
                           "entity_id": own_fact.id, "value_status": "stated", "audit_retained": True})
    graph.append_revision({"action": "answer", "event_id": "answer-other", "statement": OTHER_FACT, "stable_id": other.stable_id,
                           "entity_id": other_fact.id, "value_status": "stated", "audit_retained": True})
    pending = {"inquiry_id": "inq-pending", "revision": 4, "question": "Who else was present?", "question_type": "clarification",
               "kind": "graph", "objective_id": "witnesses", "target_id": "witness-gap", "target_revision": "1",
               "why_it_matters": "The pending question is separate from a correction.", "legal_sufficiency": False}
    projection = {
        "schema_version": "shared-interview-session-v1",
        "contract_version": "interview-transition-v1",
        "session_id": "interview-gui18",
        "session_revision": 2,
        "phase": "intake",
        "narrative_extraction_count": 1,
        "question_revision": 4,
        "pending_inquiry": pending,
        "answered_inquiries": [],
        "unknown_reasons": [],
        "unavailable_reasons": [],
        "capped_reasons": [],
        "legal_sufficiency": False,
        "knowledge_graph": graph.to_dict(),
        "dependency_graph": DependencyGraph().to_dict(),
        "denoiser_history": [],
        "iteration_count": 1,
        "loss_history": [],
        "phase_history": [],
        "intake_case_file": {"canonical_facts": [], "candidate_claims": []},
        "current_questions": [{"type": "clarification", "question": pending["question"], "inquiry_id": pending["inquiry_id"],
                               "target_id": pending["target_id"], "objective_id": pending["objective_id"], "context": {}}],
        "question_candidates": [],
    }
    state = service._load_state(USER_ID)
    state["case_id"] = USER_ID
    state["privacy_notice_shown"] = True
    state["original_complaint"] = {"text": "Synthetic narrative that is not the edited answer.", "revision": 1, "revisions": []}
    state["intake_answers"] = {"inq-own": OWN_FACT, "inq-other": OTHER_FACT}
    state["intake_history"] = [
        {"question_id": "inq-own", "answer": OWN_FACT, "disposition": "accepted", "target_stable_id": own.stable_id,
         "actor_principal_id": USER_ID, "audit_id": "audit-own"},
        {"question_id": "inq-other", "answer": OTHER_FACT, "disposition": "accepted", "target_stable_id": other.stable_id,
         "actor_principal_id": OTHER_ID, "audit_id": "audit-other"},
    ]
    state["shared_interview"] = projection
    service._save_state(state)
    return {"token": graph_revision_token(graph), "own": own.stable_id, "other": other.stable_id, "session_revision": 2}


def _correct(client, seeded, replacement, **overrides):
    body = {
        "schema": "gui-factual-correction-v1",
        "replacement": replacement,
        "expected_graph_revision": seeded["token"],
        "expected_session_revision": seeded["session_revision"],
        "target_stable_id": seeded["own"],
        "actor_principal_id": USER_ID,
    }
    body.update(overrides)
    response = client.post("/api/complaint-workspace/intake-chat", json={
        "user_id": USER_ID,
        "message": json.dumps(body),
        "question_id": body.get("target_stable_id") or "",
        "interview_action": "correct",
    })
    assert response.status_code == 200, response.text
    return response.json()


def _graph(payload):
    session = payload["session"]
    return KnowledgeGraph.from_dict(session["shared_interview"]["knowledge_graph"])


def test_correction_supersedes_keeps_prior_and_invalidates_support(tmp_path):
    service = _service(tmp_path)
    seeded = _seed(service)
    client = _client(service)
    payload = _correct(client, seeded, REPLACEMENT)
    receipt = payload["factual_correction"]
    assert receipt["status"] == "applied"
    assert receipt["display_only"] is False
    assert receipt["legal_sufficiency"] is False
    assert receipt["actor_principal_id"] == USER_ID
    assert receipt["canonical_owner_principal_id"] == ""
    assert receipt["actor_matches_canonical_owner"] is False
    assert receipt["graph_revision"] != seeded["token"]
    assert receipt["session_revision"] == seeded["session_revision"] + 1
    correction = receipt["correction"]
    assert correction["lineage"]["previous_status"] == "superseded"
    assert correction["lineage"]["previous_envelope_retained"] is True
    assert correction["affected_support_targets"]
    graph = _graph(payload)
    previous = graph.assertion_state(seeded["own"])
    assert previous["status"] == "superseded"
    assert previous["envelope"]["source_text"] == OWN_FACT
    assert previous["envelope"]["actor"] == USER_ID
    replacement = graph.assertion_state(correction["replacement_stable_id"])
    assert replacement["status"] == "active"
    assert replacement["envelope"]["source_text"] == REPLACEMENT
    own_edge = graph.relationships["rel-own-support"]
    assert own_edge.attributes["activity_status"] == "invalidated"
    assert own_edge.attributes["proof_cache"]["reusable"] is False
    assert own_edge.attributes["proof_cache"]["satisfied"] is False
    other = graph.assertion_state(seeded["other"])
    assert other["status"] == "active"
    assert other["envelope"]["source_text"] == OTHER_FACT
    assert other["envelope"]["actor"] == OTHER_ID
    other_edge = graph.relationships["rel-other-support"]
    assert other_edge.attributes.get("activity_status") != "invalidated"
    assert other_edge.attributes["proof_cache"]["reusable"] is True
    history = payload["session"]["intake_history"]
    assert history[0]["answer"] == OWN_FACT
    assert history[0]["audit_id"] == "audit-own"
    assert history[1]["answer"] == OTHER_FACT
    assert history[1]["actor_principal_id"] == OTHER_ID
    assert history[-1]["disposition"] == "corrected"
    assert history[-1]["actor_principal_id"] == USER_ID
    assert history[-1]["answer"] == REPLACEMENT
    pending = payload["session"]["shared_interview"]["pending_inquiry"]
    assert pending["inquiry_id"] == "inq-pending"
    assert pending["target_id"] == "witness-gap"
    assert payload["stored_as_answer"] is True
    offer = payload["adaptive_inquiry"]["factual_correction"]
    assert offer["schema"] == "gui-factual-correction-v1"
    assert offer["actor_principal_id"] == USER_ID
    assert offer["expected_graph_revision"] == receipt["graph_revision"]


def test_stale_revision_and_other_participant_are_refused(tmp_path):
    service = _service(tmp_path)
    seeded = _seed(service)
    client = _client(service)
    before = service.get_session(USER_ID)["session"]
    stale = _correct(client, seeded, REPLACEMENT, expected_graph_revision="gr_stale")
    assert stale["factual_correction"]["status"] == "refused"
    assert stale["factual_correction"]["error"]["code"] == "stale_target"
    assert stale["stored_as_answer"] is False
    unauthorized_actor = _correct(client, seeded, REPLACEMENT, actor_principal_id=OTHER_ID)
    assert unauthorized_actor["factual_correction"]["status"] == "refused"
    assert unauthorized_actor["factual_correction"]["error"]["code"] == "unauthorized_actor"
    other_target = _correct(client, seeded, "A schedule that must not replace Riley.", target_stable_id=seeded["other"])
    assert other_target["factual_correction"]["status"] == "refused"
    assert other_target["factual_correction"]["error"]["code"] == "unauthorized_actor"
    missing = _correct(client, seeded, REPLACEMENT, expected_session_revision=None)
    assert missing["factual_correction"]["error"]["code"] == "stale_target"
    after = service.get_session(USER_ID)["session"]
    assert after["intake_history"] == before["intake_history"]
    assert after["intake_answers"] == before["intake_answers"]
    graph = KnowledgeGraph.from_dict(after["shared_interview"]["knowledge_graph"])
    assert graph.assertion_state(seeded["own"])["status"] == "active"
    assert graph.assertion_state(seeded["other"])["status"] == "active"
    assert graph.assertion_state(seeded["other"])["envelope"]["source_text"] == OTHER_FACT
    assert graph.relationships["rel-own-support"].attributes["proof_cache"]["reusable"] is True
    assert graph.relationships["rel-other-support"].attributes["proof_cache"]["reusable"] is True
    assert graph_revision_token(graph) == seeded["token"]


def test_live_answer_correction_uses_the_offered_revisions(tmp_path):
    service = _service(tmp_path)
    client = _client(service)
    narrative = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns."
    started = client.post("/api/complaint-workspace/intake-chat", json={
        "user_id": USER_ID, "message": narrative, "question_id": "original_complaint", "interview_action": "start",
    })
    assert started.status_code == 200, started.text
    inquiry = started.json()["interview"]["inquiry"]
    answered = client.post("/api/complaint-workspace/intake-chat", json={
        "user_id": USER_ID,
        "message": "Alex Rivera fired me on March 4, 2024 after I reported a safety concern.",
        "question_id": inquiry["inquiry_id"],
        "expected_question_revision": inquiry["revision"],
        "interview_action": "answer",
    })
    assert answered.status_code == 200, answered.text
    offer = answered.json()["adaptive_inquiry"]["factual_correction"]
    assert offer["schema"] == "gui-factual-correction-v1"
    assert offer["actor_principal_id"] == USER_ID
    assert offer["canonical_owner_principal_id"] == ""
    assert offer["requires_expected_revision"] is True
    assert offer["target_stable_id"]
    assert str(offer["expected_graph_revision"]).startswith("gr_")
    replacement = "Alex Rivera fired me on March 5, 2024 after I reported a safety concern."
    applied = _correct(client, {
        "token": offer["expected_graph_revision"],
        "session_revision": offer["expected_session_revision"],
        "own": offer["target_stable_id"],
    }, replacement)
    receipt = applied["factual_correction"]
    assert receipt["status"] == "applied", receipt
    assert receipt["actor_principal_id"] == USER_ID
    assert receipt["actor_matches_canonical_owner"] is False
    assert receipt["correction"]["lineage"]["previous_envelope_retained"] is True
    assert receipt["correction"]["lineage"]["previous_status"] == "superseded"
    texts = [item["answer"] for item in applied["session"]["intake_history"]]
    assert offer["prior_answer"] in texts
    assert replacement in texts
    stale = _correct(client, {
        "token": offer["expected_graph_revision"],
        "session_revision": offer["expected_session_revision"],
        "own": offer["target_stable_id"],
    }, "This stale sentence must not become the fact.")
    assert stale["factual_correction"]["status"] == "refused"
    assert stale["factual_correction"]["error"]["code"] == "stale_target"
    assert "This stale sentence must not become the fact." not in [item.get("answer") for item in stale["session"]["intake_history"]]


def test_workspace_page_submits_the_mediator_correction():
    page = open("templates/workspace.html", encoding="utf-8").read()
    assert 'id="factual-correction"' in page
    assert 'data-task="CIMP-GUI-18"' in page
    assert "interview_action: 'correct'" in page
    assert "gui-factual-correction-v1" in page
    assert "expected_graph_revision" in page
    assert "actor_principal_id" in page
