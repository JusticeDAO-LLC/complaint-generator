"""Current factual graph projection for the workspace.

User assertions and explicitly adopted evidence keep source, version, and span
provenance. Hydration must leave the caller document unchanged. A cached
boolean, a role label, or a model inference is not a user assertion.
"""
from __future__ import annotations

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from complaint_phases.knowledge_graph import Entity, KnowledgeGraph, Relationship, project_current_factual_graph
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash
from tests.test_cimp_gui_14 import NARRATIVE, _composed_case_world, _composed_ciphertext_snapshot, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

CASE = "synthetic-ux23-case"


def _envelope(text, source_id, *, source_kind="user_statement", record_class="user_fact"):
    return build_user_assertion_envelope(
        source_text=text,
        source_kind=source_kind,
        source_id=source_id,
        message_id=source_id if source_kind == "user_statement" else "",
        document_id=source_id if source_kind == "user_uploaded_document" else "",
        assertion_status="asserted",
        extractor_version="synthetic-ux23-v1",
        source_hash=source_byte_hash(text),
        source_span={"start": 0, "end": len(text.encode("utf-8")), "text": text, "unit": "byte"},
        factual_record_class=record_class,
    )


def _entity(entity_id, text, source_id, **kwargs):
    record_class = kwargs.pop("record_class", "user_fact")
    source_kind = kwargs.pop("source_kind", "user_statement")
    envelope = _envelope(text, source_id, source_kind=source_kind, record_class=record_class)
    attributes = {"description": text, "factual_record_class": record_class, "case_id": CASE}
    attributes.update(kwargs.pop("attributes", {}))
    entity = Entity(
        id=entity_id, type=kwargs.pop("type", "fact"), name=text, attributes=attributes,
        confidence=0.2, source=kwargs.pop("source", "complaint"),
        provenance={"user_assertion": envelope.as_dict(), "case_id": CASE, **kwargs.pop("provenance", {})},
    )
    return entity, envelope


def _graph(*entities, relationships=()):
    graph = KnowledgeGraph(graph_id="synthetic-ux23-graph", graph_version="3")
    graph.metadata["case_id"] = CASE
    for entity in entities:
        graph.add_entity(entity)
    for relationship in relationships:
        graph.add_relationship(relationship)
    return graph


def _project(graph):
    return project_current_factual_graph(graph.to_dict(), case_id=CASE)


def test_hydration_does_not_mutate_caller_json():
    entity, envelope = _entity("stated", "The notice arrived on March 3.", "msg-ux23-stated")
    graph = _graph(entity)
    caller = graph.to_dict()
    caller["entities"]["stated"]["cached_authority"] = True
    caller["entities"]["stated"]["attributes"]["authority_is_user_fact"] = True
    caller["entities"]["stated"]["attributes"]["role"] = "complainant"
    before = json.dumps(caller, sort_keys=True)
    restored = KnowledgeGraph.from_dict(caller)
    restored.entities["stated"].attributes["description"] = "rewritten by hydration"
    restored.entities["stated"].provenance["user_assertion"]["source_text"] = "rewritten"
    restored.entities["stated"].provenance["case_id"] = "other-case"
    projected = project_current_factual_graph(caller, case_id=CASE)
    assert json.dumps(caller, sort_keys=True) == before
    assert caller["entities"]["stated"]["cached_authority"] is True
    assert projected["caller_json_mutated"] is False
    assert projected["user_statements"][0]["assertion_id"] == envelope.stable_id
    assert "rewritten" not in json.dumps(caller)


def test_user_assertion_keeps_source_version_and_span_and_cached_boolean_does_not():
    entity, envelope = _entity("stated", "The notice arrived on March 3.", "msg-ux23-stated")
    raw = Entity(
        id="cached", type="fact", name="Cached boolean is not a fact",
        attributes={"description": "Cached boolean is not a fact", "factual_record_class": "user_fact",
            "authority_is_user_fact": True, "role": "complainant", "case_id": CASE},
        source="complaint",
        provenance={"case_id": CASE, "user_assertion": {
            "is_asserted_user_fact": True, "admitted_user_fact": True, "role": "user",
            "source_id": "cached-source", "extractor_version": "synthetic-ux23-v1",
        }},
    )
    payload = _project(_graph(entity, raw))
    stated = next(item for item in payload["user_statements"] if item["graph_entity_id"] == "stated")
    provenance = stated["source_provenance"]
    assert stated["admitted_user_fact"] is True
    assert provenance["verified"] is True
    assert provenance["source_id"] == "msg-ux23-stated"
    assert provenance["extractor_version"] == "synthetic-ux23-v1"
    assert provenance["source_hash"] == envelope.source_hash
    assert provenance["source_span"]["text"] == "The notice arrived on March 3."
    assert provenance["source_span"]["end"] == len("The notice arrived on March 3.".encode())
    assert all(item["graph_entity_id"] != "cached" for item in payload["user_statements"])
    withheld = [item for item in payload["unresolved"] if item.get("graph_entity_id") == "cached"]
    assert withheld
    assert withheld[0]["admitted_user_fact"] is False
    assert withheld[0]["authority_is_user_fact"] is False
    assert withheld[0]["source_provenance"]["verified"] is False


def test_role_label_and_ai_inference_cannot_become_user_assertions_or_verified_facts():
    inferred, _envelope = _entity(
        "inferred", "A model guessed the motive.", "model-ux23",
        source="inference", attributes={"role": "complainant", "authority_is_user_fact": True},
    )
    labeled = Entity(
        id="labeled", type="person", name="Alex Example",
        attributes={"role": "user", "authority_is_user_fact": True, "case_id": CASE, "description": "Alex Example"},
        source="complaint",
        provenance={"case_id": CASE, "origin": "llm", "user_assertion": {"is_asserted_user_fact": True, "role": "witness"}},
    )
    payload = _project(_graph(inferred, labeled))
    assert payload["user_statements"] == []
    assert payload["adopted_evidence"] == []
    assert payload["corrections"] == []
    identities = {item.get("graph_entity_id") for item in payload["hypotheses"]}
    identities |= {item.get("graph_entity_id") for item in payload["unresolved"]}
    assert {"inferred", "labeled"} <= identities
    for item in payload["hypotheses"] + payload["unresolved"]:
        assert item.get("admitted_user_fact") is not True
        assert item.get("authority_is_user_fact") is not True


def test_explicit_adopted_evidence_projects_span_and_boolean_adoption_does_not():
    text = "Exhibit span: the written denial."
    adopted, envelope = _entity(
        "exhibit", text, "doc-ux23",
        source_kind="user_uploaded_document", record_class="supporting_evidence", type="evidence",
        attributes={"adoption": "explicit"},
    )
    adopted.attributes["adoption_assertion_id"] = envelope.stable_id
    flagged, flagged_envelope = _entity(
        "flagged", "A checkbox does not adopt this exhibit.", "doc-ux23-flag",
        source_kind="user_uploaded_document", record_class="supporting_evidence", type="evidence",
        attributes={"adopted": True, "adoption": True, "authority_is_user_fact": True,
            "adoption_assertion_id": "pending"},
    )
    flagged.attributes["adoption_assertion_id"] = flagged_envelope.stable_id
    payload = _project(_graph(adopted, flagged))
    assert payload["user_statements"] == []
    assert [item["graph_entity_id"] for item in payload["adopted_evidence"]] == ["exhibit"]
    shown = payload["adopted_evidence"][0]
    assert shown["admitted_user_fact"] is False
    assert shown["explicitly_adopted_evidence"] is True
    assert shown["source_provenance"]["verified"] is True
    assert shown["source_provenance"]["extractor_version"] == "synthetic-ux23-v1"
    assert shown["source_provenance"]["source_span"]["text"] == text
    assert shown["source_provenance"]["source_id"] == "doc-ux23"
    assert all(item["graph_entity_id"] != "flagged" for item in payload["adopted_evidence"])
    flagged_row = next(item for item in payload["evidence_revisions"] if item["graph_entity_id"] == "flagged")
    assert flagged_row["explicitly_adopted_evidence"] is False
    assert flagged_row["admitted_user_fact"] is False


def test_corrections_and_contradictions_come_from_the_graph_adapter():
    old, old_envelope = _entity("original", "The meeting was on Monday.", "msg-ux23-old")
    new, new_envelope = _entity("replacement", "The meeting was on Tuesday.", "msg-ux23-new")
    left, left_envelope = _entity("left", "The letter was mailed.", "msg-ux23-left")
    right, right_envelope = _entity("right", "The letter was handed over.", "msg-ux23-right")
    graph = _graph(old, new, left, right)
    for entity, envelope in ((old, old_envelope), (new, new_envelope), (left, left_envelope), (right, right_envelope)):
        graph.register_assertion(entity, envelope)
    graph.supersede_assertion(old_envelope.stable_id, new, new_envelope, event_id="ux23-correction")
    graph.record_assertion_conflict(
        left_envelope.stable_id, right_envelope.stable_id,
        event_id="ux23-conflict", left_entity_id=left.id, right_entity_id=right.id,
    )
    caller = deepcopy(graph.to_dict())
    payload = project_current_factual_graph(caller, case_id=CASE)
    assert caller == graph.to_dict()
    correction = payload["corrections"][0]
    assert correction["action"] == "supersede"
    assert correction["event_id"] == "ux23-correction"
    assert correction["previous_assertion_id"] == old_envelope.stable_id
    assert correction["new_assertion_id"] == new_envelope.stable_id
    assert correction["provenance_status"] == "verified"
    contradiction = payload["contradictions"][0]
    assert contradiction["action"] == "conflict"
    assert contradiction["event_id"] == "ux23-conflict"
    assert contradiction["assertion_ids"] == [left_envelope.stable_id, right_envelope.stable_id]
    assert contradiction["provenance_status"] == "verified"
    original = next(item for item in payload["user_statements"] if item["graph_entity_id"] == "original")
    assert original["admitted_user_fact"] is False
    assert original["activity_status"] == "superseded"
    assert original["source_provenance"]["source_span"]["text"] == "The meeting was on Monday."
    active = next(item for item in payload["user_statements"] if item["graph_entity_id"] == "replacement")
    assert active["admitted_user_fact"] is True


def test_relationship_adoption_is_explicit_only_with_the_evidence_assertion():
    text = "The signed roster lists March 3."
    exhibit, envelope = _entity(
        "roster", text, "doc-ux23-roster",
        source_kind="user_uploaded_document", record_class="supporting_evidence", type="evidence",
    )
    fact, _fact_envelope = _entity("stated", "I was on the roster.", "msg-ux23-roster")
    link = Relationship(
        id="rel-ux23", source_id="roster", target_id="stated", relation_type="supports",
        attributes={"adoption": "explicit", "adoption_assertion_id": envelope.stable_id, "case_id": CASE},
        provenance={"case_id": CASE},
    )
    payload = _project(_graph(exhibit, fact, relationships=(link,)))
    assert payload["adopted_evidence"][0]["graph_entity_id"] == "roster"
    assert payload["adopted_evidence"][0]["source_provenance"]["source_span"]["text"] == text
    assert payload["user_statements"][0]["graph_entity_id"] == "stated"
    assert payload["user_statements"][0]["admitted_user_fact"] is True


def test_workspace_route_projects_the_live_session_without_rewriting_it(tmp_path):
    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        missing = client.get(
            "/api/complaint-workspace/factual-graph",
            headers=_composed_headers(world.case),
            params={"case_id": world.case.case_id},
        )
        assert missing.status_code == 401
        csrf = _composed_login(client)
        started = client.post(
            "/api/complaint-workspace/intake-chat",
            headers=_composed_headers(world.case, csrf),
            json={"message": NARRATIVE, "interview_action": "start", "question_id": "original_complaint"},
        )
        assert started.status_code == 200, started.text
        before = _composed_ciphertext_snapshot(service)
        saved = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case, csrf))
        assert saved.status_code == 200, saved.text
        raw_graph = saved.json()["session"]["shared_interview"]["knowledge_graph"]
        fingerprint = json.dumps(raw_graph, sort_keys=True)
        projected = client.get(
            "/api/complaint-workspace/factual-graph",
            headers=_composed_headers(world.case, csrf),
            params={"case_id": world.case.case_id},
        )
        assert projected.status_code == 200, projected.text
        body = projected.json()
        assert body["status"] == "projected"
        assert body["case_id"] == world.case.case_id
        assert body["projection_kind"] == "current_factual_graph"
        assert body["read_only"] is True
        assert body["caller_json_mutated"] is False
        assert body["user_statements"] or body["allegations"] or body["hypotheses"] or body["unresolved"]
        for item in body["user_statements"]:
            assert item["source_provenance"]["verified"] is True
            assert item["source_provenance"]["source_span"]["text"]
            assert item["source_provenance"]["extractor_version"]
        again = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case, csrf))
        assert json.dumps(again.json()["session"]["shared_interview"]["knowledge_graph"], sort_keys=True) == fingerprint
        assert _composed_ciphertext_snapshot(service) == before
        foreign = client.get(
            "/api/complaint-workspace/factual-graph",
            headers=_composed_headers(world.case, csrf),
            params={"case_id": world.second.case_id},
        )
        assert foreign.status_code == 403
        assert foreign.json().get("user_statements", []) == []
        mismatched = deepcopy(raw_graph)
        mismatched.setdefault("metadata", {})["case_id"] = "synthetic-other-case"
        with pytest.raises(Exception) as refused:
            project_current_factual_graph(mismatched, case_id=world.case.case_id)
        assert getattr(refused.value, "code", "") == "cross_case_id"
        assert json.dumps(mismatched, sort_keys=True) == json.dumps(
            {**raw_graph, "metadata": {**(raw_graph.get("metadata") or {}), "case_id": "synthetic-other-case"}},
            sort_keys=True,
        )
