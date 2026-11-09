"""Constrained factual proposals, supersession, and contradiction review.

Positive cases admit a generated hypothesis only after an authorized actor
says so, supersede and contradict with an expected revision, and retract
support without deleting source history. Negative cases reject a missing
authority grant, a stale revision, a lawyer HTTP owner-key write, and a
model suggestion presented as an admitted fact.
"""

from __future__ import annotations

import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import SESSION_COOKIE
from applications.case_access import ASSIGNED_LAWYER_ACTIONS
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from complaint_phases.knowledge_graph import (
    Entity,
    FactualReviewError,
    KnowledgeGraph,
    Relationship,
)
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

CASE = "synthetic-review-case"


def _envelope(text: str, message_id: str):
    return build_user_assertion_envelope(
        source_text=text,
        source_kind="user_statement",
        source_id=message_id,
        message_id=message_id,
        assertion_status="asserted",
        extractor_version="synthetic-gui22-v1",
        source_hash=source_byte_hash(text),
        source_span={"start": 0, "end": len(text.encode("utf-8")), "text": text, "unit": "byte"},
        factual_record_class="user_fact",
    )


def _graph() -> KnowledgeGraph:
    graph = KnowledgeGraph(graph_id="synthetic-review", graph_version="1")
    graph.metadata["case_id"] = CASE
    text = "Synthetic original arrival was nine."
    envelope = _envelope(text, "synthetic-original-message")
    entity = Entity(
        id="original-fact",
        type="fact",
        name=text,
        attributes={"description": text, "factual_record_class": "user_fact"},
        confidence=1.0,
        source="complaint",
        provenance={"user_assertion": envelope.as_dict(), "case_id": CASE, "source_id": "src-original"},
    )
    graph.add_entity(entity)
    graph.register_assertion(entity, envelope)
    graph.add_entity(Entity(
        id="supported-claim",
        type="claim",
        name="Synthetic schedule claim",
        attributes={
            "description": "Synthetic schedule claim",
            "proof_cache": {"fact_id": entity.id, "satisfied": True, "reusable": True},
            "proof_cache_identity": "cache-original",
            "proof_cache_fact_ids": [entity.id],
        },
        confidence=0.4,
        source="inference",
        provenance={"source_id": "src-claim", "case_id": CASE},
    ))
    graph.add_relationship(Relationship(
        id="support-original",
        source_id=entity.id,
        target_id="supported-claim",
        relation_type="supports",
        attributes={
            "proof_cache": {"fact_id": entity.id, "satisfied": True, "reusable": True},
            "proof_cache_identity": "cache-edge",
        },
        confidence=0.4,
        source="inference",
    ))
    return graph


def _review(graph: KnowledgeGraph, **overrides):
    payload = {
        "actor_role": "lawyer",
        "actor_principal_id": "synthetic-lawyer-principal",
        "authority_granted": True,
        "expected_revision": graph.factual_review_revision(),
        "action": "propose",
        "text": "Synthetic generated schedule change.",
        "origin": "model",
        "event_id": "synthetic-event-propose",
        "case_id": CASE,
    }
    payload.update(overrides)
    return graph.apply_factual_review(**payload)


def test_generated_suggestion_stays_hypothesis_until_authorized_admission():
    graph = _graph()
    before = copy.deepcopy(graph.to_dict())
    with pytest.raises(FactualReviewError) as missing:
        _review(graph, authority_granted=False)
    assert missing.value.code == "actor_authority_required"
    assert graph.to_dict() == before
    proposed = _review(graph)
    assert proposed["status"] == "hypothesis"
    assert proposed["admitted"] is False
    assert proposed["actor_authority"] == "lawyer"
    hypothesis = graph.entities[proposed["entity_id"]]
    assert hypothesis.attributes["factual_record_class"] == "extraction_hypothesis"
    assert hypothesis.attributes["admitted"] is False
    assert "user_assertion" not in hypothesis.provenance
    stale = graph.factual_review_revision()
    with pytest.raises(FactualReviewError) as rejected:
        _review(graph, expected_revision="fr_stale", event_id="synthetic-event-stale")
    assert rejected.value.code == "stale_graph_revision"
    assert graph.factual_review_revision() == stale
    admitted = _review(
        graph,
        actor_role="user",
        actor_principal_id="synthetic-user-principal",
        action="admit",
        proposal_id=proposed["proposal_id"],
        source_text="Synthetic admitted schedule change.",
        message_id="synthetic-admission-message",
        event_id="synthetic-event-admit",
        text="",
    )
    assert admitted["admitted"] is True
    assert admitted["hypothesis_retained"] is True
    assert admitted["actor_authority"] == "user"
    assert graph.entities[proposed["entity_id"]].attributes["hypothesis"] is True
    admitted_entity = graph.entities[admitted["entity_id"]]
    assert admitted_entity.attributes["factual_record_class"] == "user_fact"
    assert graph.assertion_state(admitted["stable_id"])["status"] == "active"
    replay = _review(
        graph,
        actor_role="user",
        actor_principal_id="synthetic-user-principal",
        action="admit",
        proposal_id=proposed["proposal_id"],
        source_text="Synthetic admitted schedule change.",
        message_id="synthetic-admission-message",
        event_id="synthetic-event-admit",
        expected_revision="fr_ignored_on_replay",
        text="",
    )
    assert replay["idempotent_replay"] is True
    assert replay["stable_id"] == admitted["stable_id"]


def test_supersession_contradiction_and_retraction_keep_source_history():
    graph = _graph()
    original = graph.entities["original-fact"]
    original_source = copy.deepcopy(original.provenance["user_assertion"])
    original_stable = original_source["stable_id"]
    superseded = _review(
        graph,
        action="supersede",
        text="",
        source_text="Synthetic corrected arrival was ten.",
        message_id="synthetic-correction-message",
        target_stable_id=original_stable,
        event_id="synthetic-event-supersede",
    )
    assert superseded["status"] == "superseded"
    assert superseded["actor_authority"] == "lawyer"
    assert superseded["source_history_retained"] is True
    assert graph.entities["original-fact"].provenance["user_assertion"]["source_text"] == original_source["source_text"]
    assert graph.assertion_state(original_stable)["status"] == "superseded"
    assert graph.entity_activity("original-fact") == "superseded"
    replacement_stable = graph.entities[superseded["entity_id"]].provenance["user_assertion"]["stable_id"]
    conflict = _review(
        graph,
        actor_role="user",
        actor_principal_id="synthetic-user-principal",
        action="contradict",
        text="",
        source_text="Synthetic witness says the arrival was eight.",
        message_id="synthetic-conflict-message",
        target_stable_id=replacement_stable,
        event_id="synthetic-event-contradict",
    )
    assert conflict["status"] == "conflict"
    assert conflict["unresolved"] is True
    assert conflict["source_history_retained"] is True
    assert graph.entities[superseded["entity_id"]].provenance["user_assertion"]["source_text"] == "Synthetic corrected arrival was ten."
    assert graph.assertion_state(replacement_stable)["status"] == "conflict"
    assert graph.assertion_state(conflict["stable_id"])["status"] == "conflict"
    fresh = _graph()
    fresh_source = fresh.entities["original-fact"].provenance["user_assertion"]
    retracted = _review(
        fresh,
        action="retract",
        text="",
        source_text="Synthetic retraction of the nine o'clock arrival.",
        message_id="synthetic-retraction-message",
        target_stable_id=fresh_source["stable_id"],
        event_id="synthetic-event-retract",
    )
    assert retracted["source_history_retained"] is True
    assert fresh.entities["original-fact"].provenance["user_assertion"]["stable_id"] == fresh_source["stable_id"]
    assert fresh.entities["original-fact"].provenance["source_id"] == "src-original"
    claim = fresh.entities["supported-claim"].attributes
    assert claim["proof_cache"]["reusable"] is False
    assert claim["proof_cache"]["satisfied"] is False
    assert claim["proof_cache"]["invalidation_reason"] == "retracted"
    assert claim["proof_cache_reusable"] is False
    edge = fresh.relationships["support-original"].attributes
    assert edge["activity_status"] == "invalidated"
    assert edge["effective"] is False
    assert edge["proof_cache"]["reusable"] is False
    assert edge["proof_cache"]["satisfied"] is False
    assert edge.get("rejected_proof_cache_identity") == "cache-edge"
    with pytest.raises(FactualReviewError) as legal:
        _review(fresh, record_class="legal_text", event_id="synthetic-legal", text="Synthetic statute text")
    assert legal.value.code == "constrained_record"


def _headers(case, csrf=None, *, membership=None):
    headers = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
    }
    if csrf is not None:
        headers["x-csrf-token"] = csrf
    if membership is not None:
        headers["x-expected-membership-revision"] = str(membership)
    return headers


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def test_http_owner_review_persists_and_denies_lawyer_and_stale_revision(tmp_path):
    from tests.test_cimp_gui_14 import NARRATIVE, _composed_case_world

    world = _composed_case_world(tmp_path)
    handlers = CaseHandlerRegistry()
    for selected in (world.case, world.second, world.foreign):
        service = world.services[selected.case_id]
        handlers.bind(selected, mediator=service, workspace_service=service, authorize_delegated=lambda _decision: False)
    app = FastAPI()
    compose_case_routes(
        app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=handlers, include_review=False, include_document=False,
    )
    case = world.case
    path = f"/api/graphs/{case.case_id}/factual"
    review_path = path + "/reviews"
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, "synthetic-owner-credential")
        started = client.post(
            "/api/complaint-workspace/intake-chat",
            headers=_headers(case, csrf),
            json={"message": NARRATIVE, "interview_action": "start"},
        )
        assert started.status_code == 200, started.text
        current = client.get(path, headers=_headers(case, csrf))
        assert current.status_code == 200, current.text
        revision = current.json()["factual_review_revision"]
        assert revision.startswith("fr_")
        stale = client.post(
            review_path,
            headers=_headers(case, csrf),
            json={"review_action": "propose", "text": "Synthetic owner hypothesis.", "origin": "model",
                  "event_id": "synthetic-http-stale", "expected_graph_revision": "fr_stale"},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"] == "stale_graph_revision"
        proposed = client.post(
            review_path,
            headers=_headers(case, csrf),
            json={"review_action": "propose", "text": "Synthetic owner hypothesis about the schedule.",
                  "origin": "model", "event_id": "synthetic-http-propose", "expected_graph_revision": revision},
        )
        assert proposed.status_code == 200, proposed.text
        body = proposed.json()
        assert body["status"] == "hypothesis"
        assert body["admitted"] is False
        assert body["actor_authority"] == "user"
        assert body["task_id"] == "CIMP-GUI-22"
        again = client.get(path, headers=_headers(case, csrf))
        assert again.status_code == 200, again.text
        hypotheses = again.json()["hypotheses"]
        assert any(item["text"] == "Synthetic owner hypothesis about the schedule." for item in hypotheses)
        assert all(item["admitted_user_fact"] is False for item in hypotheses)
        grant = world.authorizer.grant_assigned_lawyer(
            owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            tenant_id=case.tenant_id,
            actions=set(ASSIGNED_LAWYER_ACTIONS),
            expected_case_revision=case.revision,
        )
        lawyer_csrf = _login(client, "synthetic-lawyer-credential")
        denied = client.post(
            review_path,
            headers=_headers(case, lawyer_csrf, membership=grant.revision),
            json={"review_action": "propose", "text": "Synthetic lawyer hypothesis.", "origin": "actor",
                  "event_id": "synthetic-http-lawyer", "expected_graph_revision": body["graph_revision"]},
        )
        assert denied.status_code == 403
        _login(client, "synthetic-stranger-credential")
        stranger = client.post(
            review_path,
            headers=_headers(case),
            json={"review_action": "propose", "text": "Synthetic stranger hypothesis.", "event_id": "synthetic-http-stranger",
                  "expected_graph_revision": revision},
        )
        assert stranger.status_code == 403
