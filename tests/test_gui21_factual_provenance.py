"""Real source envelopes and correction-ledger semantics for factual reads.

All statements are synthetic. The legacy phase wrapper is exercised too; it
must carry the same provenance rules as the freshly decrypted HTTP projection.
"""

from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from complaint_phases.knowledge_graph import Entity, KnowledgeGraph
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash
from mediator.integrations.graph_tools import project_authorized_factual_kg


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
CASE = "synthetic-graph-case"


def _project(graph):
    mediator = SimpleNamespace(phase_manager=SimpleNamespace(get_phase_data=lambda *_args: graph))
    return project_authorized_factual_kg(mediator, case_id=CASE, graph_read_granted=True)


def _fact(entity_id, text, message_id, *, record_class="user_fact", source_kind="user_statement"):
    envelope = build_user_assertion_envelope(
        source_text=text, source_kind=source_kind, source_id=message_id,
        message_id=message_id if source_kind == "user_statement" else "",
        document_id=message_id if source_kind == "user_uploaded_document" else "",
        assertion_status="asserted", extractor_version="synthetic-gui21-v1",
        source_hash=source_byte_hash(text),
        source_span={"start": 0, "end": len(text.encode("utf-8")), "text": text, "unit": "byte"},
        factual_record_class=record_class,
    )
    entity = Entity(id=entity_id, type="fact", name=text,
        attributes={"description": text, "factual_record_class": record_class},
        confidence=0.43, source="complaint", provenance={"user_assertion": envelope.as_dict(), "case_id": CASE})
    return entity, envelope


def _graph():
    graph = KnowledgeGraph(graph_id="synthetic-factual-graph", graph_version="1")
    graph.metadata["case_id"] = CASE
    return graph


def _statement(payload, entity_id):
    return next(item for item in payload["user_statements"] if item["graph_entity_id"] == entity_id)


def test_raw_fact_and_cached_boolean_do_not_mint_verified_user_authority():
    graph = _graph()
    graph.add_entity(Entity(id="raw", type="fact", name="Synthetic raw statement", confidence=1.0,
        attributes={"factual_record_class": "user_fact"},
        provenance={"case_id": CASE, "source_id": "unverified-source",
            "user_assertion": {"source_id": "unverified-source", "is_asserted_user_fact": True}}))
    item = _statement(_project(graph), "raw")
    assert item["admitted_user_fact"] is False
    assert item["authority_is_user_fact"] is False
    assert item["provenance_status"] == "unverified"


@pytest.mark.parametrize("field,value", [
    ("source_text", "Changed synthetic source"),
    ("source_hash", "0" * 64),
    ("stable_id", "forged-stable-id"),
    ("source_span_end", 1),
    ("extractor_version", ""),
    ("source_kind", "model"),
])
def test_serialized_assertion_requires_real_source_span_hash_and_identity(field, value):
    graph = _graph()
    entity, envelope = _fact("tampered", "Synthetic statement to validate", "synthetic-message")
    assert envelope.is_asserted_user_fact is True
    entity.provenance["user_assertion"][field] = value
    entity.provenance["user_assertion"]["is_asserted_user_fact"] = True
    graph.add_entity(entity)
    item = _statement(_project(graph), "tampered")
    assert item["admitted_user_fact"] is False
    assert item["authority_is_user_fact"] is False
    assert item["provenance_status"] == "unverified"


def test_real_validated_envelope_ignores_cached_claim_and_keeps_assertion_identity():
    graph = _graph()
    entity, envelope = _fact("verified", "Synthetic unicode café statement", "synthetic-message")
    assert envelope.is_asserted_user_fact is True
    entity.provenance["user_assertion"]["is_asserted_user_fact"] = False
    graph.add_entity(entity)
    graph.register_assertion(entity, envelope)
    item = _statement(_project(graph), "verified")
    assert item["admitted_user_fact"] is True
    assert item["authority_is_user_fact"] is True
    assert item["provenance_status"] == "verified"
    assert item["assertion_id"] == envelope.stable_id
    assert item["source_identity"] == envelope.source_identity
    assert item["activity_status"] == "active"
    assert item["confidence"] == 0.43


@pytest.mark.parametrize("action", ["supersede", "retract", "conflict"])
def test_actual_correction_ledger_preserves_history_without_admitting_inactive_fact(action):
    graph = _graph()
    old, old_envelope = _fact("original", "Synthetic original source", "synthetic-original")
    new, new_envelope = _fact("replacement", "Synthetic replacement source", "synthetic-replacement")
    for entity, envelope in ((old, old_envelope), (new, new_envelope)):
        graph.add_entity(entity)
        graph.register_assertion(entity, envelope)
    if action == "supersede":
        graph.supersede_assertion(old_envelope.stable_id, new, new_envelope, event_id="synthetic-event")
    elif action == "retract":
        graph.retract_assertion(old_envelope.stable_id, new, new_envelope, event_id="synthetic-event")
    else:
        graph.record_assertion_conflict(old_envelope.stable_id, new_envelope.stable_id,
            event_id="synthetic-event", left_entity_id=old.id, right_entity_id=new.id)
    snapshot = deepcopy(graph.to_dict())
    payload = _project(graph)
    item = _statement(payload, old.id)
    assert item["admitted_user_fact"] is False
    assert item["activity_status"] == {"supersede": "superseded", "retract": "retracted", "conflict": "conflict"}[action]
    assert payload["revisions"][0]["action"] == action
    assert payload["revisions"][0]["event_id"] == "synthetic-event"
    if action in {"supersede", "retract"}:
        assert payload["revisions"][0]["previous_assertion_id"] == old_envelope.stable_id
        assert payload["revisions"][0]["new_assertion_id"] == new_envelope.stable_id
        assert _statement(payload, new.id)["admitted_user_fact"] is True
    else:
        assert _statement(payload, new.id)["admitted_user_fact"] is False
        assert payload["unresolved_conflicts"][0]["assertion_ids"] == [old_envelope.stable_id, new_envelope.stable_id]
    assert payload["evidence_revisions"] == []
    assert graph.to_dict() == snapshot


def test_read_projection_never_initializes_or_mutates_factual_ledger():
    graph = _graph()
    entity, _envelope = _fact("verified", "Synthetic ledger-free fact", "synthetic-message")
    graph.add_entity(entity)
    assert "factual_ledger" not in graph.metadata
    before = deepcopy(graph.to_dict())
    payload = _project(graph)
    assert graph.to_dict() == before
    assert payload["read_only"] is True
    assert _statement(payload, entity.id)["admitted_user_fact"] is True


def test_confidence_and_non_user_classes_cannot_become_user_facts():
    graph = _graph()
    evidence, evidence_envelope = _fact("evidence", "Synthetic uploaded exhibit", "synthetic-document",
        record_class="supporting_evidence", source_kind="user_uploaded_document")
    hypothesis, _ = _fact("hypothesis", "Synthetic possible explanation", "synthetic-model",
        record_class="extraction_hypothesis")
    legal, _ = _fact("legal", "Synthetic legal text", "synthetic-legal", record_class="legal_text")
    for entity in (evidence, hypothesis, legal):
        entity.confidence = float("inf")
        graph.add_entity(entity)
    payload = _project(graph)
    assert evidence_envelope.is_asserted_user_fact is True
    assert payload["evidence_revisions"][0]["admitted_user_fact"] is False
    assert payload["evidence_revisions"][0]["assertion_id"] == evidence_envelope.stable_id
    assert payload["hypotheses"][0]["admitted_user_fact"] is False
    assert payload["withheld_legal_text"]
    assert payload["user_statements"] == []
    json.dumps(payload, allow_nan=False)


def test_reused_message_identity_does_not_hide_different_source_classes():
    graph = _graph()
    fact, _ = _fact("fact", "Synthetic asserted statement", "synthetic-shared-message")
    hypothesis, _ = _fact("hypothesis", "Synthetic possible explanation", "synthetic-shared-message",
        record_class="extraction_hypothesis")
    for entity in (fact, hypothesis):
        graph.add_entity(entity)
    payload = _project(graph)
    assert len(payload["user_statements"]) == 1
    assert len(payload["hypotheses"]) == 1
    assert not any(item.get("reason") == "source_id_authority_conflict" for item in payload["unresolved"])


def test_multiple_exact_spans_keep_distinct_assertion_ids_for_one_message():
    graph = _graph()
    text = "Synthetic morning fact. Synthetic evening fact."
    for index, span in enumerate(("Synthetic morning fact.", "Synthetic evening fact.")):
        start = text.index(span)
        envelope = build_user_assertion_envelope(source_text=text, source_kind="user_statement",
            message_id="synthetic-shared-message", assertion_status="asserted",
            extractor_version="synthetic-gui21-v1", source_hash=source_byte_hash(text),
            source_span={"start": start, "end": start + len(span), "text": span, "unit": "byte"})
        assert envelope.is_asserted_user_fact
        entity = Entity(id=f"span-{index}", type="fact", name=span,
            provenance={"user_assertion": envelope.as_dict()})
        graph.add_entity(entity)
        graph.register_assertion(entity, envelope)
    rows = _project(graph)["user_statements"]
    assert len(rows) == 2
    assert all(row["admitted_user_fact"] for row in rows)
    assert len({row["assertion_id"] for row in rows}) == 2
    assert len({row["immutable_source_id"] for row in rows}) == 2
    assert {row["source_identity"] for row in rows} == {"synthetic-shared-message"}


@pytest.mark.parametrize("damage", ["wrong_entity", "wrong_envelope", "missing_envelope", "unknown_status"])
def test_unbound_or_unknown_activity_state_cannot_restore_fact_authority(damage):
    graph = _graph()
    entity, envelope = _fact("verified", "Synthetic ledger binding", "synthetic-message")
    graph.add_entity(entity)
    graph.register_assertion(entity, envelope)
    state = graph.metadata["factual_ledger"]["assertion_states"][envelope.stable_id]
    if damage == "wrong_entity":
        state["entity_id"] = "another-entity"
    elif damage == "wrong_envelope":
        state["envelope"]["source_text"] = "Changed synthetic source"
    elif damage == "missing_envelope":
        state.pop("envelope")
    else:
        state["status"] = "unknown"
    row = _statement(_project(graph), entity.id)
    assert row["admitted_user_fact"] is False
    assert row["activity_status"] == "unverified"
