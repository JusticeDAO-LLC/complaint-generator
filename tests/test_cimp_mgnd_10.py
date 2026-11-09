"""Exact UTF-8 source spans and assertion identity for accepted facts.

Cases are synthetic private fixtures. No test is skipped. A span from another
source generation is not retargeted, and a model string cannot fill a missing
span. Unknown and refused answers stay on the revision ledger.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from complaint_phases.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeGraphBuilder,
    record_answer_graph_revision,
)
from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

MESSAGE_ID = "message-private-10"
ANSWER_ID = "answer-private-10"


def _cases():
    narrative = "José told HR the café notice was late."
    repeated = "the notice was late. the notice was late."
    legal_story = "I was told that retaliation is prohibited after I complained."
    return (
        {"label": "non-ascii-fact", "text": narrative},
        {"label": "repeated-phrase", "text": repeated},
        {"label": "unknown-answer", "text": narrative},
        {"label": "refused-answer", "text": narrative},
        {"label": "legal-narrative", "text": legal_story},
        {"label": "legal-passage-as-narrative", "text": "On Monday José lost the café shift."},
        {"label": "missing-span", "text": narrative},
        {"label": "conflicting-spans", "text": narrative},
        {"label": "foreign-generation", "text": narrative},
        {"label": "model-claim-unbound", "text": narrative},
        {"label": "relationship", "text": narrative},
        {"label": "supporting-evidence", "text": narrative},
        {"label": "extraction-hypothesis", "text": narrative},
    )


def _context(text: str, **extra) -> dict:
    payload = {
        "source_kind": "user_statement",
        "source_id": MESSAGE_ID,
        "message_id": MESSAGE_ID,
        "answer_id": ANSWER_ID,
        "assertion_status": "asserted",
        "extractor_version": "kg-span-v1",
        "source_hash": source_byte_hash(text),
    }
    payload.update(extra)
    return payload


def _span(text: str, needle: str, occurrence: int = 0, **extra) -> dict:
    source = text.encode("utf-8")
    needle_bytes = needle.encode("utf-8")
    start = -1
    for _ in range(occurrence + 1):
        start = source.find(needle_bytes, start + 1)
        assert start >= 0
    payload = {
        "start": start,
        "end": start + len(needle_bytes),
        "text": needle,
        "unit": "byte",
        "source_generation": source_byte_hash(text),
    }
    payload.update(extra)
    return payload


def _build(text: str, **kwargs):
    context = kwargs.pop("source_context", _context(text))
    return KnowledgeGraphBuilder().build_from_text(
        text,
        source_context=context,
        include_local_heuristics=False,
        **kwargs,
    )


def _marked(graph, marker: str):
    found = [entity for entity in graph.entities.values() if (entity.attributes or {}).get("marker") == marker]
    assert len(found) == 1
    return found[0]


def _envelope(record):
    return user_assertion_from_mapping((record.provenance or {}).get("user_assertion"))


def _fact(text: str, needle: str, marker: str, **extra) -> dict:
    span = extra.pop("source_span", _span(text, needle))
    attributes = {"description": needle, "marker": marker}
    attributes.update(extra.pop("attributes", {}))
    record = {
        "type": extra.pop("type", "fact"),
        "name": extra.pop("name", needle),
        "origin": extra.pop("origin", "user"),
        "source_span": span,
        "attributes": attributes,
    }
    record.update(extra)
    return record


def test_module_collects_meaningful_cases_without_required_skips():
    cases = _cases()
    assert cases
    assert len({item["label"] for item in cases}) == len(cases)
    assert all(item["text"].strip() for item in cases)
    assert Path(__file__).name == "test_cimp_mgnd_10.py"


def test_accepted_fact_keeps_exact_utf8_bytes_and_refuses_char_retarget():
    text = _cases()[0]["text"]
    needle = "José"
    graph = _build(text, extracted_entities=[_fact(text, needle, "jose")], extracted_relationships=[])
    entity = _marked(graph, "jose")
    envelope = _envelope(entity)
    source_bytes = text.encode("utf-8")
    assert envelope.is_asserted_user_fact is True
    assert envelope.factual_record_class == "user_fact"
    assert envelope.source_kind == "user_statement"
    assert envelope.message_id == MESSAGE_ID
    assert envelope.answer_id == ANSWER_ID
    assert envelope.source_text.encode("utf-8") == source_bytes
    assert envelope.source_hash == source_byte_hash(text)
    assert envelope.source_generation == envelope.source_hash
    assert envelope.source_byte_length == len(source_bytes)
    assert source_bytes[envelope.source_span_start:envelope.source_span_end].decode("utf-8") == needle
    assert envelope.source_span_text == needle
    assert envelope.stable_id == envelope.computed_stable_id()
    restored = user_assertion_from_mapping(envelope.as_dict())
    assert restored.is_asserted_user_fact is True
    assert restored.stable_id == envelope.stable_id

    char_end = text.find(" ")
    refused = _build(
        text,
        extracted_entities=[_fact(
            text,
            needle,
            "char",
            source_span={"start": 0, "end": char_end, "text": needle, "unit": "character"},
        )],
        extracted_relationships=[],
    )
    char_envelope = _envelope(_marked(refused, "char"))
    assert char_envelope.is_asserted_user_fact is False
    assert "source_span_unit_not_byte" in char_envelope.deficiencies
    assert char_envelope.source_span_text != needle


def test_repeated_phrase_stays_ambiguous_until_one_byte_span_is_named():
    text = "the notice was late. the notice was late."
    needle = "the notice was late."
    ambiguous = _build(
        text,
        extracted_entities=[{
            "type": "fact",
            "name": needle,
            "origin": "user",
            "attributes": {"description": needle, "marker": "repeated"},
        }],
        extracted_relationships=[],
    )
    ambiguous_envelope = _envelope(_marked(ambiguous, "repeated"))
    assert ambiguous_envelope.is_asserted_user_fact is False
    assert "ambiguous_source_span" in ambiguous_envelope.deficiencies

    second = _span(text, needle, occurrence=1)
    bound = _build(
        text,
        extracted_entities=[_fact(text, needle, "second", source_span=second)],
        extracted_relationships=[],
    )
    envelope = _envelope(_marked(bound, "second"))
    assert envelope.is_asserted_user_fact is True
    assert envelope.source_span_start == second["start"]
    assert envelope.source_span_start != _span(text, needle, occurrence=0)["start"]
    assert text.encode("utf-8")[envelope.source_span_start:envelope.source_span_end].decode("utf-8") == needle


def test_unknown_and_refused_answers_keep_identity_without_becoming_facts():
    text = _cases()[0]["text"]
    graph = KnowledgeGraph()
    unknown = record_answer_graph_revision(
        graph,
        answer="unknown",
        source_text=text + " unknown",
        source_context=_context(text + " unknown"),
        question={"id": "q-unknown"},
        event_id="event-unknown",
        epistemic_class="user_allegation",
        value_status="unknown",
    )
    refused = record_answer_graph_revision(
        graph,
        answer="refused",
        source_text=text + " refused",
        source_context=_context(text + " refused"),
        question={"id": "q-refused"},
        event_id="event-refused",
        epistemic_class="user_allegation",
        value_status="refused",
    )
    assert unknown["value_status"] == "unknown"
    assert refused["value_status"] == "refused"
    assert unknown["answer_id"] == ANSWER_ID
    assert refused["message_id"] == MESSAGE_ID
    assert unknown["source_kind"] == "user_statement"
    assert unknown["source_hash"] == source_byte_hash(text + " unknown")
    assert unknown["deficiency"] == ""
    assert refused["source_hash"] == source_byte_hash(text + " refused")
    assert graph.entities == {}
    assert unknown["stable_id"] == ""
    assert refused["stable_id"] == ""
    absent = record_answer_graph_revision(
        graph,
        answer="not in the source",
        source_text=text,
        source_context=_context(text),
        question={"id": "q-missing"},
        event_id="event-missing",
        epistemic_class="user_allegation",
        value_status="unknown",
    )
    assert absent["deficiency"] == "missing_source_span"
    assert absent["entity_id"] == ""
    assert graph.entities == {}


def test_legal_passage_presented_as_narrative_is_not_a_user_fact():
    story = "I was told that retaliation is prohibited after I complained."
    legal_sentence = "retaliation is prohibited"
    complaint = "I was told"
    graph = _build(
        story,
        extracted_entities=[
            _fact(story, complaint, "told"),
            _fact(
                story,
                legal_sentence,
                "law",
                record_type="legal_text",
                factual_record_class="legal_text",
                origin="legal",
            ),
        ],
        extracted_relationships=[],
    )
    told = _envelope(_marked(graph, "told"))
    law = _envelope(_marked(graph, "law"))
    assert told.is_asserted_user_fact is True
    assert told.factual_record_class == "user_fact"
    assert law.is_asserted_user_fact is False
    assert law.record_type == "legal_text"
    assert law.factual_record_class == "legal_text"
    assert law.source_hash == source_byte_hash(story)

    prose = "On Monday José lost the café shift."
    passage = _build(
        prose,
        source_context=_context(prose, legal_passage=True),
        extracted_entities=[_fact(prose, "José", "person-like", type="person", name="José")],
        extracted_relationships=[],
    )
    masked = _envelope(_marked(passage, "person-like"))
    assert masked.is_asserted_user_fact is False
    assert masked.record_type == "legal_text"
    assert masked.factual_record_class == "legal_text"


def test_missing_and_conflicting_spans_remain_deficient():
    text = _cases()[0]["text"]
    missing = _build(
        text,
        extracted_entities=[{
            "type": "fact",
            "name": "unbound label",
            "origin": "user",
            "attributes": {"marker": "missing"},
        }],
        extracted_relationships=[],
    )
    missing_envelope = _envelope(_marked(missing, "missing"))
    assert missing_envelope.is_asserted_user_fact is False
    assert "missing_source_span" in missing_envelope.deficiencies

    first = _span(text, "José")
    second = _span(text, "café")
    conflict = _build(
        text,
        extracted_entities=[{
            "type": "fact",
            "name": "José",
            "origin": "user",
            "source_span": first,
            "attributes": {"description": "José", "marker": "conflict", "source_span": second},
        }],
        extracted_relationships=[],
    )
    conflict_envelope = _envelope(_marked(conflict, "conflict"))
    assert conflict_envelope.is_asserted_user_fact is False
    assert "ambiguous_source_span" in conflict_envelope.deficiencies


def test_foreign_generation_and_model_claim_do_not_repair_the_span():
    text = "José told HR the café notice was late."
    other = "Jose told HR the cafe notice was late."
    foreign_span = {
        "start": other.encode("utf-8").find(b"cafe"),
        "end": other.encode("utf-8").find(b"cafe") + len(b"cafe"),
        "text": "cafe",
        "unit": "byte",
        "source_generation": source_byte_hash(other),
    }
    foreign = _build(
        text,
        extracted_entities=[_fact(text, "café", "foreign", source_span=foreign_span, name="café")],
        extracted_relationships=[],
    )
    foreign_envelope = _envelope(_marked(foreign, "foreign"))
    assert foreign_envelope.is_asserted_user_fact is False
    assert "source_generation_mismatch" in foreign_envelope.deficiencies
    assert foreign_envelope.source_span_start is None
    assert foreign_envelope.source_generation == source_byte_hash(text)
    assert foreign_envelope.source_text.encode("utf-8") == text.encode("utf-8")
    assert b"cafe" not in foreign_envelope.source_text.encode("utf-8")

    model = _build(
        text,
        extracted_entities=[{
            "type": "fact",
            "name": "José told HR the café notice was late.",
            "origin": "model",
            "record_type": "model_suggestion",
            "factual_record_class": "extraction_hypothesis",
            "confidence": 0.99,
            "attributes": {
                "description": text,
                "marker": "model",
            },
        }],
        extracted_relationships=[],
    )
    model_envelope = _envelope(_marked(model, "model"))
    assert model_envelope.is_asserted_user_fact is False
    assert model_envelope.factual_record_class == "extraction_hypothesis"
    assert model_envelope.record_type == "model_suggestion"
    assert "missing_source_span" in model_envelope.deficiencies


def test_relationship_and_evidence_stay_distinct_from_user_facts_and_hypotheses():
    text = "José told HR the café notice was late."
    person = _fact(text, "José", "person", type="person", name="José")
    person["extractor_key"] = "person-jose"
    event = _fact(text, "the café notice was late", "event")
    event["extractor_key"] = "event-notice"
    relation_span = _span(text, "told HR")
    graph = _build(
        text,
        extracted_entities=[person, event],
        extracted_relationships=[{
            "source_key": "person-jose",
            "target_key": "event-notice",
            "relation_type": "occurred_on",
            "origin": "user",
            "factual_record_class": "relationship",
            "source_span": relation_span,
            "attributes": {"marker": "edge"},
        }],
    )
    edge = next(item for item in graph.relationships.values() if (item.attributes or {}).get("marker") == "edge")
    edge_envelope = _envelope(edge)
    assert edge_envelope.is_asserted_user_fact is True
    assert edge_envelope.factual_record_class == "relationship"
    assert edge_envelope.role == "occurred_on"
    assert edge_envelope.message_id == MESSAGE_ID
    assert edge_envelope.answer_id == ANSWER_ID
    assert edge_envelope.source_hash == source_byte_hash(text)
    assert text.encode("utf-8")[edge_envelope.source_span_start:edge_envelope.source_span_end].decode("utf-8") == "told HR"
    assert edge.source_id == _marked(graph, "person").id
    assert edge.target_id == _marked(graph, "event").id
    assert edge.source_id != MESSAGE_ID
    assert { _envelope(_marked(graph, "person")).factual_record_class,
             _envelope(_marked(graph, "event")).factual_record_class } == {"user_fact"}
    assert edge_envelope.stable_id != _envelope(_marked(graph, "person")).stable_id

    evidence_text = "the café notice"
    evidence = _build(
        text,
        extracted_entities=[_fact(
            text,
            evidence_text,
            "evidence",
            type="evidence",
            factual_record_class="supporting_evidence",
        )],
        extracted_relationships=[],
    )
    evidence_envelope = _envelope(_marked(evidence, "evidence"))
    assert evidence_envelope.is_asserted_user_fact is True
    assert evidence_envelope.factual_record_class == "supporting_evidence"
    assert evidence_envelope.record_type == "user_assertion"
    assert evidence_envelope.source_span_text == evidence_text

    hypothesis = _build(
        text,
        extracted_entities=[{
            "type": "fact",
            "name": "José",
            "origin": "user",
            "factual_record_class": "extraction_hypothesis",
            "source_span": _span(text, "José"),
            "attributes": {"description": "José", "marker": "hypothesis"},
        }],
        extracted_relationships=[],
    )
    hypothesis_envelope = _envelope(_marked(hypothesis, "hypothesis"))
    assert hypothesis_envelope.is_asserted_user_fact is False
    assert hypothesis_envelope.factual_record_class == "extraction_hypothesis"
    assert hypothesis_envelope.record_type == "model_suggestion"
