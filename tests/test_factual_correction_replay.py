"""Append-only factual corrections, retractions, conflicts, and answer-event replay."""

import copy
import json

import pytest

from complaint_phases.dependency_graph import DependencyGraphBuilder, DependencyNode, NodeType
from complaint_phases.knowledge_graph import (
    AnswerEventConflict,
    Entity,
    KnowledgeGraph,
    Relationship,
    assertion_from_provenance,
)
from complaint_phases.phase_manager import ComplaintPhase
from integrations.ipfs_datasets.types import (
    build_user_assertion_envelope,
    source_byte_hash,
    user_assertion_from_mapping,
)
from mediator.mediator import Mediator


class MockBackend:
    id = "mock_backend"

    def __call__(self, prompt):
        return "Mock response"


def _context(text, message_id, confidence=None, subject_key="employment-date"):
    payload = {
        "source_text": text,
        "source_kind": "user_statement",
        "source_id": message_id,
        "message_id": message_id,
        "assertion_status": "asserted",
        "extractor_version": "fact03-test",
        "source_hash": source_byte_hash(text),
        "source_span": {"start": 0, "end": len(text.encode("utf-8")), "text": text},
        "subject_key": subject_key,
    }
    if confidence is not None:
        payload["confidence"] = confidence
    return payload


def _asserted_fact(entity_id, text, message_id, confidence):
    envelope = build_user_assertion_envelope(**{
        key: value for key, value in _context(text, message_id, confidence).items() if key != "confidence"
    }, confidence=confidence)
    assert envelope.is_asserted_user_fact
    return Entity(
        id=entity_id,
        type="fact",
        name=text,
        attributes={"description": text, "fact_type": "timeline"},
        confidence=confidence,
        source="complaint",
        provenance={"user_assertion": envelope.as_dict()},
    ), envelope


def _mediator_with_fact(text, message_id, confidence=0.4):
    mediator = Mediator([MockBackend()])
    graph = KnowledgeGraph()
    fact, envelope = _asserted_fact("fact_original", text, message_id, confidence)
    claim = Entity(
        id="claim_1",
        type="claim",
        name="Termination",
        attributes={
            "claim_type": "employment",
            "satisfied_requirements": [fact.id],
            "satisfied_fact_bundle": [fact.id],
        },
        confidence=0.9,
    )
    graph.add_entity(claim)
    graph.add_entity(fact)
    graph.register_assertion(fact, envelope, status="active")
    graph.add_relationship(Relationship(
        id="rel_support",
        source_id=fact.id,
        target_id=claim.id,
        relation_type="supports",
        attributes={},
        confidence=0.9,
    ))
    dependency_graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Termination", "type": "employment"}]
    )
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", dependency_graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", {
        "canonical_facts": [],
        "candidate_claims": [],
    })
    return mediator, fact, envelope


def _question():
    return {
        "type": "clarification",
        "question": "What date were you fired?",
        "context": {"fact_type": "timeline"},
    }


def test_correction_keeps_both_sources_and_supersedes_the_prior_assertion():
    original = "I was fired on January 1, 2020."
    corrected = "I was fired on January 2, 2020."
    mediator, fact, envelope = _mediator_with_fact(original, "msg-original", confidence=0.95)
    original_proof = copy.deepcopy(fact.provenance["user_assertion"])
    result = mediator.process_denoising_answer(
        _question(),
        corrected,
        answer_event_id="answer-event-correction",
        source_context=_context(corrected, "msg-correction", confidence=0.2),
        factual_action="correct",
        supersedes_stable_id=envelope.stable_id,
    )
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert fact.provenance["user_assertion"] == original_proof
    assert user_assertion_from_mapping(original_proof).is_asserted_user_fact
    assert graph.assertion_state(envelope.stable_id)["status"] == "superseded"
    new_state = graph.assertion_state(result["updates"]["stable_id"])
    assert new_state["status"] == "active"
    assert user_assertion_from_mapping(new_state["envelope"]).is_asserted_user_fact
    assert new_state["envelope"]["source_identity"] == "msg-correction"
    assert graph.assertion_state(envelope.stable_id)["envelope"]["source_identity"] == "msg-original"
    identities = {
        graph.assertion_state(envelope.stable_id)["source_identity"],
        new_state["source_identity"],
    }
    assert identities == {"msg-original", "msg-correction"}
    assert fact.id not in {item.id for item in graph.effective_fact_entities()}
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    assert fact.id not in {item.get("fact_id") for item in case_file["canonical_facts"]}
    historical = case_file["historical_canonical_facts"]
    assert any(item.get("fact_id") == fact.id and item.get("activity_status") == "superseded" for item in historical)
    assert any(item.get("activity_status") == "invalidated" and item.get("effective") is False for item in case_file["support_links"])
    assert "fact_original" not in claim_satisfied(graph)
    assert result["next_questions"][0]["context"]["regenerated"] is True
    assert graph.metadata["revision"] > 0


def claim_satisfied(graph):
    claim = graph.get_entity("claim_1")
    return list((claim.attributes or {}).get("satisfied_requirements") or [])


def test_retraction_preserves_the_original_proof_and_drops_active_support():
    statement = "My employer fired me on March 3, 2024."
    retraction = "I retract the March 3, 2024 firing date."
    mediator, fact, envelope = _mediator_with_fact(statement, "msg-statement", confidence=0.99)
    original_proof = copy.deepcopy(fact.provenance["user_assertion"])
    mediator.process_denoising_answer(
        _question(),
        retraction,
        answer_event_id="answer-event-retract",
        source_context=_context(retraction, "msg-retract", subject_key="retraction"),
        factual_action="retract",
        retracts_stable_id=envelope.stable_id,
    )
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert fact.provenance["user_assertion"] == original_proof
    assert user_assertion_from_mapping(fact.provenance["user_assertion"]).is_asserted_user_fact
    assert graph.assertion_state(envelope.stable_id)["status"] == "retracted"
    assert fact.id not in {item.id for item in graph.effective_fact_entities()}
    assert graph._support_facts("claim_1", "Termination") == []
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    assert all(item.get("fact_id") != fact.id for item in case_file["canonical_facts"])
    assert any(item.get("activity_status") == "retracted" for item in case_file["historical_canonical_facts"])
    assert any(not item["effective"] for item in case_file["support_links"] if item["relationship_id"] == "rel_support")
    assert case_file["reopened_questions"]


def test_contradictions_stay_unresolved_when_confidence_differs():
    low_text = "I was fired on January 1, 2020."
    high_text = "I was fired on June 1, 2020."
    low_graph = KnowledgeGraph()
    low_entity, low_envelope = _asserted_fact("entity_1", low_text, "msg-low", 0.2)
    low_graph.add_entity(low_entity)
    high_graph = KnowledgeGraph()
    high_entity, high_envelope = _asserted_fact("entity_1", high_text, "msg-high", 0.99)
    high_graph.add_entity(high_entity)
    low_graph.merge_with(high_graph)
    kept = low_graph.entities["entity_1"]
    assert kept.name == low_text
    assert kept.confidence == 0.2
    assert kept.provenance["user_assertion"]["stable_id"] == low_envelope.stable_id
    incoming = next(entity for entity in low_graph.entities.values() if entity.name == high_text)
    assert incoming.confidence == 0.99
    assert {low_graph.assertion_state(low_envelope.stable_id)["status"],
            low_graph.assertion_state(high_envelope.stable_id)["status"]} == {"conflict"}
    assert low_graph._support_facts("entity_1", low_text) == []

    reverse_low = KnowledgeGraph()
    reverse_high_entity, _ = _asserted_fact("entity_1", high_text, "msg-high", 0.99)
    reverse_low.add_entity(reverse_high_entity)
    reverse_incoming_graph = KnowledgeGraph()
    reverse_low_entity, _ = _asserted_fact("entity_1", low_text, "msg-low", 0.2)
    reverse_incoming_graph.add_entity(reverse_low_entity)
    reverse_low.merge_with(reverse_incoming_graph)
    assert reverse_low.entities["entity_1"].name == high_text
    assert reverse_low.entities["entity_1"].confidence == 0.99
    assert any(entity.name == low_text for entity in reverse_low.entities.values())


def test_explicit_contradiction_does_not_let_confidence_replace_the_original():
    original = "The meeting was on Monday."
    conflict = "The meeting was on Friday."
    mediator, fact, envelope = _mediator_with_fact(original, "msg-monday", confidence=0.15)
    original_proof = copy.deepcopy(fact.provenance["user_assertion"])
    mediator.process_denoising_answer(
        _question(),
        conflict,
        answer_event_id="answer-event-conflict",
        source_context=_context(conflict, "msg-friday", confidence=0.99, subject_key="meeting-day"),
        factual_action="contradict",
        contradicts_stable_id=envelope.stable_id,
    )
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert fact.name == original
    assert fact.confidence == 0.15
    assert fact.provenance["user_assertion"] == original_proof
    assert graph.assertion_state(envelope.stable_id)["status"] == "conflict"
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    statuses = {item.get("fact_id"): item.get("activity_status") for item in case_file["canonical_facts"]}
    assert statuses.get(fact.id) == "conflict"
    assert any(status == "conflict" for status in statuses.values())
    assert graph._support_facts("claim_1", "Termination") == []


def test_answer_event_replay_is_idempotent_after_reload_and_rejects_a_changed_payload():
    original = "I complained on May 1, 2024."
    corrected = "I complained on May 2, 2024."
    mediator, _fact, envelope = _mediator_with_fact(original, "msg-may-1", confidence=0.5)
    kwargs = dict(
        answer_event_id="answer-event-replay",
        source_context=_context(corrected, "msg-may-2", confidence=0.1),
        factual_action="correct",
        supersedes_stable_id=envelope.stable_id,
    )
    first = mediator.process_denoising_answer(_question(), corrected, **kwargs)
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    revision = graph.metadata["revision"]
    iterations = mediator.phase_manager.iteration_count
    asked = len(mediator.denoiser.questions_asked)
    questions = copy.deepcopy(first["next_questions"])
    reloaded = KnowledgeGraph.from_dict(graph.to_dict())
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", reloaded)
    second = mediator.process_denoising_answer(_question(), corrected, **kwargs)
    assert second["iteration"] == first["iteration"]
    assert second["updates"]["stable_id"] == first["updates"]["stable_id"]
    assert second["next_questions"] == questions
    assert mediator.phase_manager.iteration_count == iterations
    assert len(mediator.denoiser.questions_asked) == asked
    assert reloaded.metadata["revision"] == revision
    assert len(reloaded.factual_ledger()["revisions"]) == len(graph.factual_ledger()["revisions"])
    with pytest.raises(AnswerEventConflict):
        mediator.process_denoising_answer(
            _question(),
            "I complained on May 3, 2024.",
            answer_event_id="answer-event-replay",
            source_context=_context("I complained on May 3, 2024.", "msg-may-3"),
            factual_action="correct",
            supersedes_stable_id=envelope.stable_id,
        )
    assert reloaded.metadata["revision"] == revision
    assert len(mediator.denoiser.questions_asked) == asked


def test_builder_local_ids_and_rewired_relationships_do_not_overwrite_history():
    current = KnowledgeGraph()
    current.add_entity(Entity(id="entity_1", type="person", name="Alice", attributes={"description": "Alice"}))
    current.add_entity(Entity(id="entity_2", type="organization", name="Acme", attributes={"description": "Acme"}))
    incoming = KnowledgeGraph()
    incoming.add_entity(Entity(id="entity_1", type="person", name="Bob", attributes={"description": "Bob"}))
    incoming.add_entity(Entity(id="entity_2", type="organization", name="Acme", attributes={"description": "Acme"}))
    statement = "Bob worked for Acme."
    envelope = build_user_assertion_envelope(
        source_text=statement,
        source_kind="user_statement",
        source_id="msg-rel",
        message_id="msg-rel",
        assertion_status="asserted",
        extractor_version="fact03-test",
        source_hash=source_byte_hash(statement),
        source_span={"start": 0, "end": len(statement.encode("utf-8")), "text": statement},
        role="worked_for",
        subject_key="employment",
        graph_source_id="entity_1",
        graph_target_id="entity_2",
    )
    assert envelope.is_asserted_user_fact
    relationship = Relationship(
        id="rel_1",
        source_id="entity_1",
        target_id="entity_2",
        relation_type="worked_for",
        attributes={},
        confidence=0.4,
        provenance={"user_assertion": envelope.as_dict()},
    )
    incoming.add_relationship(relationship)
    original_proof = copy.deepcopy(relationship.provenance["user_assertion"])
    current.merge_with(incoming)
    assert current.entities["entity_1"].name == "Alice"
    assert any(entity.name == "Bob" for entity in current.entities.values())
    assert relationship.provenance["user_assertion"] == original_proof
    rewired = [item for item in current.relationships.values() if item.relation_type == "worked_for"]
    assert rewired
    assert all("user_assertion" not in (item.provenance or {}) for item in rewired)
    for entity in current.entities.values():
        restored = assertion_from_provenance(entity.provenance)
        assert restored is None or not restored.is_asserted_user_fact


def test_prior_graph_snapshot_is_immutable_after_correction():
    old = "I was fired on January 1, 2020."
    new = "I was fired on January 2, 2020."
    mediator, fact, proof = _mediator_with_fact(old, "audit-snapshot-original")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    snapshot = graph.to_dict()
    before = json.dumps(snapshot, sort_keys=True)
    mediator.process_denoising_answer(_question(), new,
        answer_event_id="audit-snapshot-correction",
        source_context=_context(new, "audit-snapshot-new"),
        factual_action="correct", supersedes_stable_id=proof.stable_id)
    assert json.dumps(snapshot, sort_keys=True) == before


def test_retracted_fact_does_not_reenter_effective_factual_allegations():
    old = "My employer fired me on March 3, 2024."
    withdrawal = "I retract the March 3, 2024 firing date."
    mediator, fact, proof = _mediator_with_fact(old, "audit-allegation-original")
    mediator.process_denoising_answer(_question(), withdrawal,
        answer_event_id="audit-allegation-retract",
        source_context=_context(withdrawal, "audit-allegation-retraction"),
        factual_action="retract", retracts_stable_id=proof.stable_id)
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert graph.assertion_state(proof.stable_id)["status"] == "retracted"
    assert old not in "\n".join(mediator._generate_factual_allegations(graph))


def test_unknown_correction_target_does_not_partially_insert_an_active_fact():
    old = "I was fired on January 1, 2020."
    new = "I was fired on January 2, 2020."
    mediator, fact, proof = _mediator_with_fact(old, "audit-atomic-original")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    graph.factual_ledger()
    before = copy.deepcopy(graph.to_dict())
    with pytest.raises((KeyError, ValueError)):
        mediator.process_denoising_answer(_question(), new,
            answer_event_id="audit-unknown-target",
            source_context=_context(new, "audit-atomic-new"),
            factual_action="correct", supersedes_stable_id="missing-source-assertion")
    assert graph.to_dict() == before


def test_retraction_reopens_a_real_denoiser_satisfied_dependency():
    old = "My employer fired me on March 3, 2024."
    withdrawal = "I retract the March 3, 2024 firing date."
    mediator, fact, proof = _mediator_with_fact(old, "audit-dependency-original")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    requirement = DependencyNode(id="audit-timeline-requirement", node_type=NodeType.REQUIREMENT,
        name="Date of adverse action", satisfied=False)
    dg.add_node(requirement)
    question = {"type": "requirement", "question": "When did the firing occur?",
        "context": {"requirement_id": requirement.id, "fact_type": "timeline"}}
    mediator.denoiser.process_answer(question, old, graph, dg)
    assert requirement.satisfied is True
    assert requirement.attributes["satisfied_via_denoiser"] is True
    assert requirement.attributes["satisfied_answer_text"] == old
    mediator.process_denoising_answer(question, withdrawal,
        answer_event_id="audit-dependency-retraction",
        source_context=_context(withdrawal, "audit-dependency-retract"),
        factual_action="retract", retracts_stable_id=proof.stable_id)
    assert requirement.satisfied is False


def test_loaded_graph_revision_does_not_mutate_its_input_or_original_graph():
    old = "I was fired on January 1, 2020."
    new = "I was fired on January 2, 2020."
    mediator, _fact, proof = _mediator_with_fact(old, "roundtrip-original")
    original = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    payload = original.to_dict()
    before = copy.deepcopy(payload)
    loaded = KnowledgeGraph.from_dict(payload)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", loaded)
    mediator.process_denoising_answer(_question(), new,
        answer_event_id="roundtrip-correction",
        source_context=_context(new, "roundtrip-new"),
        factual_action="correct", supersedes_stable_id=proof.stable_id)
    assert payload == before
    assert original.to_dict() == before
    assert loaded.assertion_state(proof.stable_id)["status"] == "superseded"


def test_targeted_retraction_preserves_unrelated_dependency_satisfaction():
    old = "My employer fired me on March 3, 2024."
    withdrawal = "I retract the March 3, 2024 firing date."
    unrelated = "I paid the filing fee on April 4, 2024."
    mediator, _fact, proof = _mediator_with_fact(old, "targeted-original")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    requirements = [DependencyNode(id=name, node_type=NodeType.REQUIREMENT,
        name=name, satisfied=False) for name in ("targeted-date", "independent-filing-fee")]
    for node, answer in zip(requirements, (old, unrelated)):
        dg.add_node(node)
        question = {"type": "requirement", "question": node.name,
            "context": {"requirement_id": node.id, "fact_type": "timeline"}}
        mediator.denoiser.process_answer(question, answer, graph, dg)
        assert node.satisfied is True
    preserved = copy.deepcopy(requirements[1].to_dict())
    mediator.process_denoising_answer(
        {"type": "requirement", "question": "Correct the firing date",
         "context": {"requirement_id": requirements[0].id, "fact_type": "timeline"}},
        withdrawal, answer_event_id="targeted-retraction",
        source_context=_context(withdrawal, "targeted-retraction-source"),
        factual_action="retract", retracts_stable_id=proof.stable_id)
    assert requirements[0].satisfied is False
    assert requirements[1].to_dict() == preserved


def test_invalidated_support_link_cannot_support_an_otherwise_current_fact():
    text = "My employer fired me on March 3, 2024."
    mediator, _fact, _proof = _mediator_with_fact(text, "invalidated-link-source")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert graph._support_facts("claim_1", "Termination")
    graph.relationships["rel_support"].attributes.update(
        activity_status="invalidated", effective=False)
    assert graph._support_facts("claim_1", "Termination") == []


# Additional durable Client and ciphertext transport regression checks.
import hashlib
import os

import pytest

from applications.complaint_workspace import WorkspaceAccess
from integrations.ipfs_datasets import graphs
from integrations.private_storage import ENVELOPE_MAGIC




@pytest.fixture
def reset_graph_client(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPLAINT_GENERATOR_GRAPH_CATALOG", str(tmp_path))
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT", None)
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT_VERSIONS", {})
    monkeypatch.setattr(graphs, "_GRAPH_SNAPSHOT_REGISTRY", {})
    yield
    client = graphs._GRAPH_CLIENT
    if client is not None:
        client.close()
        graphs._GRAPH_CLIENT = None


def _payload(name: str) -> dict:
    return {
        "source_id": "statement-1",
        "entities": [
            {
                "id": "fact-1",
                "type": "person",
                "name": name,
                "provenance": {"source_id": "statement-1", "statement": name},
            },
            {"id": "rule-1", "type": "legal_requirement", "name": "Element A"},
        ],
        "relationships": [
            {
                "id": "link-1",
                "type": "support_link",
                "link_type": "support_link",
                "from": "fact-1",
                "to": "rule-1",
                "factual_assertion_id": "fact-1",
                "rule_id": "rule-1",
                "provenance": {"source_id": "statement-1", "chain": "fact-to-rule"},
            }
        ],
    }


def _reopen(monkeypatch, tmp_path):
    client = graphs._GRAPH_CLIENT
    if client is not None:
        client.close()
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT", None)
    monkeypatch.setattr(graphs, "_GRAPH_SNAPSHOT_REGISTRY", {})
    os.environ["COMPLAINT_GENERATOR_GRAPH_CATALOG"] = str(tmp_path)


@pytest.mark.usefixtures("reset_graph_client")
def test_client_reopen_keeps_same_count_change_and_idempotent_retry(monkeypatch, tmp_path):
    graph_id = "graph:factual-replay"
    first = graphs.persist_graph_snapshot(_payload("Original worker"), graph_id=graph_id)
    assert first["metadata"]["client_write_ok"] is True
    second = graphs.persist_graph_snapshot(_payload("Updated worker"), graph_id=graph_id)
    assert second["metadata"]["client_write_ok"] is True
    assert second["node_count"] == first["node_count"] == 2
    retry = graphs.persist_graph_snapshot(_payload("Updated worker"), graph_id=graph_id)
    assert retry["metadata"]["client_write_ok"] is True
    assert retry["metadata"]["idempotent_retry"] is True

    module_client = graphs._GRAPH_CLIENT
    client_id = "graph-" + hashlib.sha256(graph_id.encode()).hexdigest()[:48]
    target = module_client._service.catalog.get_graph("complaint-generator", client_id)
    assert target.graph_id == client_id
    _reopen(monkeypatch, tmp_path)
    from integrations.ipfs_datasets.loader import import_module_optional

    module, error = import_module_optional("ipfs_datasets_py.knowledge_graphs")
    assert module is not None and error is None
    with module.Client.open(tmp_path / "catalog", storage_path=tmp_path / "store") as reopened:
        queried = reopened.query(
            module.GraphTarget(tenant="complaint-generator", graph_id=client_id, branch="main"),
            params={"language": "scan"},
        )
    assert queried.ok, getattr(queried, "error", None)
    rows = {tuple(row[:3]) for row in queried.result["rows"]}
    assert ("fact-1", "person", "Updated worker") in rows
    assert ("rule-1", "legal_requirement", "Element A") in rows
    assert len(queried.result["rows"]) == 2

    resumed = graphs.resume_graph_revisions(graph_id)
    assert resumed["revision_count"] >= 2
    assert any(item.get("name") == "Original worker" for item in resumed["superseded_facts"])
    assert any(item.get("statement") == "Updated worker" for item in resumed["provenance"])
    assert any(item.get("chain") == "fact-to-rule" for item in resumed["provenance"])
    assert any(item.get("rule_id") == "rule-1" for item in resumed["cross_graph_links"])
    assert resumed["plaintext_publication"] is False


@pytest.mark.usefixtures("reset_graph_client")
def test_claim_hook_resume_matches_client_revisions(monkeypatch, tmp_path):
    from mediator.claim_support_hooks import ClaimSupportHook

    class _Mediator:
        def log(self, *args, **kwargs):
            return None

    graph_id = "graph:hook-replay"
    graphs.persist_graph_snapshot(_payload("First fact"), graph_id=graph_id)
    graphs.persist_graph_snapshot(_payload("Corrected fact"), graph_id=graph_id)
    _reopen(monkeypatch, tmp_path)
    hook = ClaimSupportHook(_Mediator(), db_path=str(tmp_path / "unused.duckdb"))
    resumed = hook.resume_factual_graph(graph_id)
    assert resumed["available"] is True
    assert resumed["revision_count"] >= 2
    assert any(item.get("name") == "First fact" for item in resumed["superseded_facts"])
    assert resumed["cross_graph_links"]
    assert resumed["plaintext_publication"] is False


class _HermeticBytes:
    measurement_label = "measured-hermetic"

    def __init__(self):
        self.blobs = {}
        self.seen = []

    def add_bytes(self, data, pin=True):
        del pin
        blob = bytes(data)
        self.seen.append(blob)
        cid = "bafyhermetic" + hashlib.sha256(blob).hexdigest()[:16]
        self.blobs[cid] = blob
        return {"success": True, "cid": cid, "pinned": False}

    def cat(self, cid):
        return self.blobs[cid]

    def pin(self, cid):
        return {"success": True, "cid": cid, "pinned": True}


@pytest.mark.usefixtures("reset_graph_client")
def test_private_graph_materials_are_sealed_before_replication():
    from mediator.claim_support_hooks import ClaimSupportHook

    class _Mediator:
        def log(self, *args, **kwargs):
            return None

    replicated = []
    backend = _HermeticBytes()
    sentinel_source = "SENTINEL-SOURCE-fact05"
    sentinel_embedding = "SENTINEL-EMBEDDING-fact05"
    sentinel_index = "SENTINEL-INDEX-fact05"
    payload = {
        "entities": [{"id": "fact-1", "name": "Synthetic worker"}],
        "relationships": [],
        "source_text": sentinel_source,
        "embeddings": [{"vector": [0.1, 0.2], "text": sentinel_embedding}],
        "indexes": {"posts": [sentinel_index]},
    }
    context = {
        "access": WorkspaceAccess.authenticated("tenant-a", case_id="case-a"),
        "tenant_id": "tenant-a",
        "case_id": "case-a",
        "principal_id": "tenant-a",
        "key": bytes(range(32)),
        "key_id": "case-key-a",
        "backend": backend,
        "backend_name": "measured-hermetic",
        "pin_content": True,
        "replicate": replicated.append,
        "publish_plaintext": True,
    }
    hook = ClaimSupportHook(_Mediator(), db_path=":memory:")
    result = hook.persist_private_factual_graph(payload, context, graph_id="graph:private")
    assert result["persisted"] is True
    assert result["plaintext_publication"] is False
    assert result["plaintext_catalog"] is False
    assert replicated, "replication must observe sealed envelopes"
    for blob in replicated:
        assert blob.startswith(ENVELOPE_MAGIC)
        assert sentinel_source.encode() not in blob
        assert sentinel_embedding.encode() not in blob
        assert sentinel_index.encode() not in blob
    for blob in backend.seen:
        assert sentinel_source.encode() not in blob
        assert sentinel_embedding.encode() not in blob
        assert sentinel_index.encode() not in blob


def test_scripted_interview_correction_and_contradictory_dates_keep_both_sources(tmp_path, monkeypatch):
    from tests.test_question_saturation_contract import (
        application_level_interview_fixture,
        scripted_turn,
    )

    session = application_level_interview_fixture(tmp_path, monkeypatch)
    correction = scripted_turn(session, "correction")
    statuses = {item["stable_id"]: item for item in correction["observation"]["assertions"]}
    assert statuses[correction["extra"]["supersedes"]]["status"] == "superseded"
    assert statuses[correction["extra"]["stable_id"]]["status"] == "active"
    assert "March 4, 2024" in statuses[correction["extra"]["supersedes"]]["statement"]
    assert "March 5, 2024" in statuses[correction["extra"]["stable_id"]]["statement"]
    assert statuses[correction["extra"]["supersedes"]]["source_id"] == "msg-complete"
    assert statuses[correction["extra"]["stable_id"]]["source_id"] == "msg-correction"

    conflict = scripted_turn(session, "contradictory_dates")
    conflicted = {
        item["stable_id"]: item
        for item in conflict["observation"]["assertions"]
        if item["stable_id"] in set(conflict["extra"]["conflict_stable_ids"])
    }
    assert len(conflicted) == 2
    assert all(item["status"] != "superseded" for item in conflicted.values())
    statements = " ".join(item["statement"] for item in conflicted.values())
    assert "March 5, 2024" in statements and "June 2, 2021" in statements

    unknown = scripted_turn(session, "unknown")
    refused = scripted_turn(session, "refused")
    assert unknown["observation"]["fact_ids"] == scripted_turn(session, "complete")["observation"]["fact_ids"]
    assert refused["observation"]["fact_ids"] == unknown["observation"]["fact_ids"]
    assert any(item["disposition"] == "unknown" and item["creates_fact"] is False for item in unknown["observation"]["dispositions"])
    assert any(item["disposition"] == "refused" and item["creates_fact"] is False for item in refused["observation"]["dispositions"])
