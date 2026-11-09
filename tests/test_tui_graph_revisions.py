"""Narrative facts and answer transitions revise the graph without erasing history."""

from complaint_phases.dependency_graph import DependencyNode, NodeType
from complaint_phases.knowledge_graph import inspect_graph_revisions
from complaint_phases.phase_manager import ComplaintPhase
from integrations.ipfs_datasets.graphs import (
    LEGAL_AUTHORITY_CLASS,
    LEGAL_REQUIREMENT_KIND,
    build_epistemic_support_edge,
    classify_epistemic_class,
    mint_graph_record_id,
)
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash


NARRATIVE = (
    "My name is Ada Lovelace. "
    "My supervisor Grace Hopper fired me on March 3, 2024 for complaining about discrimination."
)


class _MockBackend:
    id = "mock_backend"

    def __call__(self, prompt):
        return "1. A synthetic note that is not a statute."


def _mediator():
    from mediator.mediator import Mediator

    return Mediator([_MockBackend()])


def _phase_graph(mediator, key):
    return mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, key)


def _slice(source, envelope):
    return source.encode("utf-8")[envelope["source_span"]["start"]:envelope["source_span"]["end"]].decode("utf-8")


def test_narrative_creates_source_linked_people_events_and_allegations():
    mediator = _mediator()
    mediator.start_three_phase_process(NARRATIVE)
    graph = _phase_graph(mediator, "knowledge_graph")
    case_file = _phase_graph(mediator, "intake_case_file")
    linked = [entity for entity in graph.entities.values() if (entity.attributes or {}).get("narrative_source_linked")]
    kinds = {entity.attributes["narrative_kind"] for entity in linked}
    assert kinds == {"person", "event", "allegation"}
    names = {entity.name for entity in linked if entity.attributes["narrative_kind"] == "person"}
    assert names == {"Ada Lovelace", "Grace Hopper"}
    for entity in linked:
        envelope = entity.provenance["user_assertion"]
        assert envelope["is_asserted_user_fact"] is True
        assert envelope["source_kind"] == "user_statement"
        assert envelope["message_id"] == "original_complaint"
        assert _slice(NARRATIVE, envelope) == envelope["source_span_text"]
        assert envelope["source_hash"] == source_byte_hash(NARRATIVE)
        assert entity.attributes["epistemic_class"] == "user_allegation"
    projected = {node["narrative_kind"]: node for node in case_file["narrative_source_nodes"] if node["narrative_kind"] == "person"}
    assert set(projected) == {"person"}
    assert projected["person"]["statement"] in names
    narrative_revision = next(item for item in inspect_graph_revisions(graph) if item["action"] == "narrative")
    assert narrative_revision["statement"] == NARRATIVE
    assert set(narrative_revision["stable_ids"]) == {
        entity.provenance["user_assertion"]["stable_id"] for entity in linked
    }


def test_answer_revision_is_inspectable_and_transition_replay_is_idempotent():
    mediator = _mediator()
    mediator.start_three_phase_process(NARRATIVE)
    graph = _phase_graph(mediator, "knowledge_graph")
    requirement = DependencyNode(
        id="req-notice",
        node_type=NodeType.LEGAL_ELEMENT,
        name="Notice",
        description="An employer shall provide notice to an employee.",
        attributes={
            "authority_locator": "Synthetic fixture rule notice",
            "source_locator": "span:1-12",
            "epistemic_class": LEGAL_AUTHORITY_CLASS,
            "dependency_class": "legally_sourced_requirement",
        },
    )
    dependency_graph = _phase_graph(mediator, "dependency_graph")
    dependency_graph.nodes[requirement.id] = requirement
    answer = "The attached email shows Grace Hopper sent the firing notice."
    question = {
        "id": "q-evidence",
        "type": "evidence",
        "question": "What shows the notice?",
        "context": {"requirement_id": requirement.id, "epistemic_class": "corroborating_evidence"},
    }
    source = {
        "source_text": answer,
        "source_kind": "user_statement",
        "source_id": "msg-evidence",
        "message_id": "msg-evidence",
        "assertion_status": "asserted",
        "extractor_version": "tui05-test",
        "source_hash": source_byte_hash(answer),
    }
    first = mediator.process_denoising_answer(question, answer, transition_id="transition-evidence", source_context=source)
    revisions = inspect_graph_revisions(graph)
    answer_revision = first["updates"]["graph_revision"]
    assert answer_revision["statement"] == answer
    assert answer_revision["source_span"]["text"] == answer
    assert answer.encode("utf-8")[answer_revision["source_span"]["start"]:answer_revision["source_span"]["end"]].decode() == answer
    assert answer_revision["epistemic_class"] == "corroborating_evidence"
    assert answer_revision["provenance"]["statement"] == answer
    revision_count = len(revisions)
    entity_count = len(graph.entities)
    iteration = mediator.phase_manager.iteration_count
    second = mediator.process_denoising_answer(question, answer, transition_id="transition-evidence", source_context=source)
    assert second["updates"]["graph_revision"]["revision_index"] == answer_revision["revision_index"]
    assert second["iteration"] == first["iteration"]
    assert len(inspect_graph_revisions(graph)) == revision_count
    assert len(graph.entities) == entity_count
    assert mediator.phase_manager.iteration_count == iteration
    assert requirement.name == "Notice"
    assert requirement.description == "An employer shall provide notice to an employee."
    assert requirement.attributes["authority_locator"] == "Synthetic fixture rule notice"
    assert requirement.attributes["epistemic_class"] == LEGAL_AUTHORITY_CLASS
    assert requirement.attributes["element_support"][-1]["statement"] == answer
    assert requirement.attributes["element_support"][-1]["epistemic_class"] == "corroborating_evidence"
    assert requirement.attributes["element_support"][-1]["definition_unchanged"] is True


def test_correction_supersedes_without_losing_audit_history():
    mediator = _mediator()
    mediator.start_three_phase_process("My name is Ada Lovelace.")
    original = "I was fired on March 1, 2024."
    corrected = "I was fired on March 2, 2024."
    question = {"id": "q-date", "type": "timeline", "question": "When were you fired?"}
    first = mediator.process_denoising_answer(
        question,
        original,
        answer_event_id="assert-date",
        source_context={
            "source_text": original,
            "source_kind": "user_statement",
            "source_id": "msg-march-1",
            "message_id": "msg-march-1",
            "assertion_status": "asserted",
            "extractor_version": "tui05-test",
            "source_hash": source_byte_hash(original),
        },
        factual_action="assert",
    )
    graph = _phase_graph(mediator, "knowledge_graph")
    original_stable_id = first["updates"]["stable_id"]
    original_proof = graph.assertion_state(original_stable_id)["envelope"]
    mediator.process_denoising_answer(
        question,
        corrected,
        answer_event_id="correct-date",
        source_context={
            "source_text": corrected,
            "source_kind": "user_statement",
            "source_id": "msg-march-2",
            "message_id": "msg-march-2",
            "assertion_status": "asserted",
            "extractor_version": "tui05-test",
            "source_hash": source_byte_hash(corrected),
        },
        factual_action="correct",
        supersedes_stable_id=original_stable_id,
    )
    assert graph.assertion_state(original_stable_id)["status"] == "superseded"
    assert graph.assertion_state(original_stable_id)["envelope"] == original_proof
    current = graph.assertion_state(graph.factual_ledger()["assertion_states"][original_stable_id]["superseded_by"])
    assert current["status"] == "active"
    assert current["envelope"]["source_span_text"] == corrected
    actions = [item["action"] for item in graph.factual_ledger()["revisions"]]
    assert "supersede" in actions
    assert "assert" in actions
    replay = mediator.process_denoising_answer(
        question,
        corrected,
        answer_event_id="correct-date",
        source_context={
            "source_text": corrected,
            "source_kind": "user_statement",
            "source_id": "msg-march-2",
            "message_id": "msg-march-2",
            "assertion_status": "asserted",
            "extractor_version": "tui05-test",
            "source_hash": source_byte_hash(corrected),
        },
        factual_action="correct",
        supersedes_stable_id=original_stable_id,
    )
    assert replay["updates"]["stable_id"] == current["stable_id"]
    assert [item["action"] for item in graph.factual_ledger()["revisions"]] == actions


def test_epistemic_classes_stay_distinct_on_support_edges():
    statement = "The witness email shows the firing."
    envelope = build_user_assertion_envelope(
        source_text=statement,
        source_kind="user_statement",
        source_id="msg-witness",
        message_id="msg-witness",
        assertion_status="asserted",
        extractor_version="tui05-test",
        source_hash=source_byte_hash(statement),
        source_span={"start": 0, "end": len(statement.encode("utf-8")), "text": statement},
        role="evidence",
        subject_key="witness-email",
    )
    rule_id = mint_graph_record_id(LEGAL_REQUIREMENT_KIND, "notice")
    edge = build_epistemic_support_edge(
        factual_assertion_id="local-fact",
        rule_id=rule_id,
        epistemic_class="corroborating_evidence",
        statement=statement,
        factual_provenance={"user_assertion": envelope.as_dict(), "epistemic_class": "corroborating_evidence"},
        rule_provenance={"epistemic_class": LEGAL_AUTHORITY_CLASS, "authority_locator": "Synthetic fixture rule notice"},
    )
    assert edge["epistemic_class"] == "corroborating_evidence"
    assert edge["provenance_chains"]["rule"]["epistemic_class"] == LEGAL_AUTHORITY_CLASS
    assert edge["provenance_chains"]["factual_assertion"]["epistemic_class"] == "corroborating_evidence"
    assert edge["requirement_definition_unchanged"] is True
    assert classify_epistemic_class("I think the notice was late.") == "inferred_hypothesis"
    assert classify_epistemic_class("Grace Hopper fired me.") == "user_allegation"
    assert classify_epistemic_class("statute text", legal=True) == LEGAL_AUTHORITY_CLASS
    try:
        build_epistemic_support_edge(
            factual_assertion_id="local-fact",
            rule_id=rule_id,
            epistemic_class=LEGAL_AUTHORITY_CLASS,
            statement="A statute.",
            factual_provenance={"user_assertion": envelope.as_dict()},
            rule_provenance={"epistemic_class": LEGAL_AUTHORITY_CLASS},
        )
    except ValueError as exc:
        assert "legal authority" in str(exc)
    else:
        raise AssertionError("legal authority was accepted as a factual support endpoint")


def test_unknown_and_contradiction_values_remain_visible():
    mediator = _mediator()
    mediator.start_three_phase_process(NARRATIVE)
    dependency_graph = _phase_graph(mediator, "dependency_graph")
    requirement = DependencyNode(
        id="req-date",
        node_type=NodeType.LEGAL_ELEMENT,
        name="Timing",
        description="The adverse action date is a sourced element.",
        satisfied=False,
        attributes={"authority_locator": "Synthetic timing rule", "epistemic_class": LEGAL_AUTHORITY_CLASS},
    )
    dependency_graph.nodes[requirement.id] = requirement
    question = {
        "id": "q-unknown",
        "type": "timeline",
        "question": "What date was the firing?",
        "context": {"requirement_id": requirement.id},
    }
    unknown = "I don't know"
    mediator.process_denoising_answer(
        question,
        unknown,
        transition_id="transition-unknown",
        source_context={
            "source_text": unknown,
            "source_kind": "user_statement",
            "source_id": "msg-unknown",
            "message_id": "msg-unknown",
            "assertion_status": "asserted",
            "extractor_version": "tui05-test",
            "source_hash": source_byte_hash(unknown),
        },
    )
    assert requirement.satisfied is False
    assert requirement.attributes["unknown_value"] == unknown
    assert requirement.attributes["value_status"] == "unknown"
    assert requirement.attributes["authority_locator"] == "Synthetic timing rule"
    case_file = _phase_graph(mediator, "intake_case_file")
    assert any(item["statement"] == unknown and item["value_status"] == "unknown" for item in case_file["visible_unknowns"])

    contradiction = "That is wrong: I was not fired on March 3, 2024."
    mediator.process_denoising_answer(
        question,
        contradiction,
        transition_id="transition-contradiction",
        source_context={
            "source_text": contradiction,
            "source_kind": "user_statement",
            "source_id": "msg-contradiction",
            "message_id": "msg-contradiction",
            "assertion_status": "asserted",
            "extractor_version": "tui05-test",
            "source_hash": source_byte_hash(contradiction),
        },
    )
    graph = _phase_graph(mediator, "knowledge_graph")
    case_file = _phase_graph(mediator, "intake_case_file")
    assert requirement.attributes["contradiction_value"] == contradiction
    assert requirement.description == "The adverse action date is a sourced element."
    assert any(item.get("statement") == contradiction for item in case_file["visible_contradictions"])
    assert any(item.get("value_status") == "contradiction" for item in inspect_graph_revisions(graph))
    assert any(item.get("value_status") == "unknown" for item in inspect_graph_revisions(graph))
