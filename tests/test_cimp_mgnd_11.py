"""Public revision-safe factual correction handoff.

Cases are synthetic private fixtures. No test is skipped. The public operation
uses process_denoising_answer and the existing supersede/retract ledger. A
missing, cross-case, or stale target does not change factual evidence. Replaying
the same correction event does not write a second assertion.
"""

from __future__ import annotations

import copy

import pytest

from complaint_phases.dependency_graph import DependencyGraphBuilder
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph, Relationship
from complaint_phases.phase_manager import ComplaintPhase
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash
from mediator.hook_runtime import graph_revision_token
from mediator.mediator import Mediator


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


class MockBackend:
    id = "mock_backend"

    def __call__(self, prompt):
        return "Mock response"


def _cases():
    return (
        {
            "label": "date-correction",
            "action": "correct",
            "original": "I was fired on January 1, 2020.",
            "replacement": "I was fired on January 2, 2020.",
        },
        {
            "label": "party-correction",
            "action": "correct",
            "original": "Alex ended the warehouse job.",
            "replacement": "Riley ended the warehouse job.",
        },
        {
            "label": "date-retraction",
            "action": "retract",
            "original": "My employer fired me on March 3, 2024.",
            "replacement": "I withdraw the March 3, 2024 firing date.",
        },
    )


def _context(text, message_id):
    return {
        "source_text": text,
        "source_kind": "user_statement",
        "source_id": message_id,
        "message_id": message_id,
        "assertion_status": "asserted",
        "extractor_version": "mgnd11-test",
        "source_hash": source_byte_hash(text),
        "source_span": {"start": 0, "end": len(text.encode("utf-8")), "text": text},
        "subject_key": "employment-fact",
    }


def _asserted_fact(entity_id, text, message_id):
    envelope = build_user_assertion_envelope(**_context(text, message_id))
    assert envelope.is_asserted_user_fact
    entity = Entity(
        id=entity_id,
        type="fact",
        name=text,
        attributes={"description": text, "fact_type": "timeline"},
        confidence=0.4,
        source="complaint",
        provenance={"user_assertion": envelope.as_dict()},
    )
    return entity, envelope


def _service(case_id, original, message_id):
    mediator = Mediator([MockBackend()])
    graph = KnowledgeGraph()
    fact, envelope = _asserted_fact("fact_original", original, message_id)
    claim = Entity(
        id="claim_1",
        type="claim",
        name="Termination",
        attributes={"claim_type": "employment", "satisfied_requirements": [fact.id]},
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
    graph.metadata["case_id"] = case_id
    dependency_graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Termination", "type": "employment"}]
    )
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", dependency_graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", {
        "canonical_facts": [],
        "candidate_claims": [],
    })
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "current_questions", [
        {"type": "clarification", "question": "Who was present?", "context": {}},
    ])
    service = mediator.workflow_actions
    service._bound_case_id = case_id
    service._interview_meta = {
        "started": True,
        "session_id": f"interview-{case_id}",
        "session_revision": 2,
        "case_id": case_id,
        "question_revision": 1,
        "pending_inquiry": {"inquiry_id": "inq-pending", "revision": 1, "question": "Who was present?"},
        "answered_inquiries": [],
        "unknown_reasons": [],
        "unavailable_reasons": [],
        "capped_reasons": [],
    }
    mediator._interview_privacy_context = {"user_id": "synthetic-owner", "case_id": case_id, "policy": {}}
    return mediator, service, fact, envelope


def _apply(service, case, *, case_id, event_id, target, **overrides):
    graph = service._mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    fields = {
        "action": case["action"],
        "target_stable_id": target,
        "replacement": case["replacement"],
        "source_context": _context(case["replacement"], f"msg-{case['label']}-next"),
        "event_id": event_id,
        "case_id": case_id,
        "expected_graph_revision": graph_revision_token(graph),
        "expected_session_revision": 2,
    }
    fields.update(overrides)
    return service.apply_factual_correction(**fields)


def _graph(mediator):
    return mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")


def test_module_collects_meaningful_cases_without_required_skips():
    cases = _cases()
    assert cases
    assert len({item["label"] for item in cases}) == len(cases)
    assert all(item["original"].strip() and item["replacement"].strip() for item in cases)
    assert all(item["action"] in {"correct", "retract"} for item in cases)


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["label"])
def test_public_correction_keeps_lineage_and_replays_one_event(case):
    case_id = f"case-{case['label']}"
    mediator, service, fact, envelope = _service(case_id, case["original"], f"msg-{case['label']}")
    original_proof = copy.deepcopy(fact.provenance["user_assertion"])
    pending = copy.deepcopy(service._interview_meta["pending_inquiry"])
    before_token = graph_revision_token(_graph(mediator))
    before_entities = set(_graph(mediator).entities)
    first = _apply(service, case, case_id=case_id, event_id=f"event-{case['label']}", target=envelope.stable_id)
    graph = _graph(mediator)
    assert first["status"] == "applied"
    assert first["idempotent_replay"] is False
    assert first["graph_mutated"] is True
    assert first["display_only"] is False
    assert first["legal_sufficiency"] is False
    assert first["awaiting_user"] is False
    assert first["session_revision"] == 3
    assert first["graph_revision"] == graph_revision_token(graph)
    assert first["graph_revision"] != before_token
    assert first["graph_revision_index"] == len(graph.factual_ledger()["revisions"])
    assert first["graph_revision_index"] > 0
    assert first["replacement_stable_id"]
    assert first["replacement_stable_id"] != envelope.stable_id
    assert any(item["relationship_id"] == "rel_support" and item["target_id"] == "claim_1" for item in first["affected_support_targets"])
    assert fact.provenance["user_assertion"] == original_proof
    assert graph.assertion_state(envelope.stable_id)["status"] == ("retracted" if case["action"] == "retract" else "superseded")
    assert graph.assertion_state(envelope.stable_id)["envelope"]["source_identity"] == f"msg-{case['label']}"
    replacement_state = graph.assertion_state(first["replacement_stable_id"])
    assert replacement_state["status"] == "active"
    assert replacement_state["envelope"]["source_identity"] == f"msg-{case['label']}-next"
    assert first["lineage"]["previous_envelope_retained"] is True
    assert first["lineage"]["replacement_envelope_retained"] is True
    assert fact.id in graph.entities
    assert fact.id not in {item.id for item in graph.effective_fact_entities()}
    assert service._interview_meta["pending_inquiry"] == pending
    entity_count = len(graph.entities)
    second = _apply(
        service,
        case,
        case_id=case_id,
        event_id=f"event-{case['label']}",
        target=envelope.stable_id,
        expected_graph_revision=before_token,
        expected_session_revision=2,
    )
    assert second["status"] == "applied"
    assert second["idempotent_replay"] is True
    assert second["graph_mutated"] is False
    assert second["session_revision"] == 3
    assert second["graph_revision"] == first["graph_revision"]
    assert second["replacement_stable_id"] == first["replacement_stable_id"]
    assert len(_graph(mediator).entities) == entity_count
    assert before_entities < set(_graph(mediator).entities)
    assert fact.provenance["user_assertion"] == original_proof


def test_missing_cross_case_and_stale_targets_do_not_change_evidence():
    case = _cases()[0]
    mediator, service, fact, envelope = _service("case-alpha", case["original"], "msg-alpha")
    proof = copy.deepcopy(fact.provenance["user_assertion"])
    token = graph_revision_token(_graph(mediator))
    entities = set(_graph(mediator).entities)

    missing = _apply(service, case, case_id="case-alpha", event_id="event-missing", target="missing-assertion")
    crossed = _apply(service, case, case_id="case-other", event_id="event-cross", target=envelope.stable_id)
    stale_graph = _apply(
        service,
        case,
        case_id="case-alpha",
        event_id="event-stale-graph",
        target=envelope.stable_id,
        expected_graph_revision="gr_stale",
    )
    stale_session = _apply(
        service,
        case,
        case_id="case-alpha",
        event_id="event-stale-session",
        target=envelope.stable_id,
        expected_session_revision=1,
    )
    conflict = _apply(service, case, case_id="case-alpha", event_id="event-live", target=envelope.stable_id)
    reused = _apply(
        service,
        case,
        case_id="case-alpha",
        event_id="event-live",
        target=envelope.stable_id,
        replacement="I was fired on March 9, 2020.",
        source_context=_context("I was fired on March 9, 2020.", "msg-other"),
    )

    assert missing["status"] == "refused" and missing["error"]["code"] == "missing_target"
    assert crossed["status"] == "refused" and crossed["error"]["code"] == "cross_case"
    assert stale_graph["status"] == "refused" and stale_graph["error"]["code"] == "stale_target"
    assert stale_session["status"] == "refused" and stale_session["error"]["code"] == "stale_target"
    assert conflict["status"] == "applied"
    assert reused["status"] == "refused" and reused["error"]["code"] == "event_conflict"
    assert fact.provenance["user_assertion"] == proof
    assert _graph(mediator).assertion_state(envelope.stable_id)["status"] == "superseded"
    assert graph_revision_token(_graph(mediator)) != token
    assert entities < set(_graph(mediator).entities)
    assert service._interview_meta["session_revision"] == 3
    refused_codes = {missing["error"]["code"], crossed["error"]["code"], stale_graph["error"]["code"], stale_session["error"]["code"]}
    assert refused_codes == {"missing_target", "cross_case", "stale_target"}


def test_unstarted_session_stays_unavailable_without_a_graph_write():
    mediator = Mediator([MockBackend()])
    graph = KnowledgeGraph()
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", graph)
    receipt = mediator.apply_factual_correction(
        action="correct",
        target_stable_id="missing",
        replacement="A later date.",
        source_context=_context("A later date.", "msg"),
        event_id="event-offline",
        case_id="case-offline",
        expected_graph_revision=graph_revision_token(graph),
        expected_session_revision=0,
    )
    assert receipt["status"] == "unavailable"
    assert receipt["error"]["code"] == "session_missing"
    assert receipt["worker_stalled"] is False
    assert receipt["awaiting_user"] is False
    assert graph.entities == {}
    assert graph.factual_ledger()["revisions"] == []
