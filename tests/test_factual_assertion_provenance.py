"""Provenance contract for user assertions, suggestions, and legal text."""

from copy import deepcopy
import pytest

from complaint_phases.intake_case_file import (
    build_canonical_fact_edges,
    build_canonical_facts,
    restore_entity_from_canonical_fact,
)
from complaint_phases.knowledge_graph import (
    Entity,
    KnowledgeGraph,
    KnowledgeGraphBuilder,
    Relationship,
    entity_to_graph_entity,
    graph_entity_to_entity,
    graph_relationship_to_relationship,
    relationship_to_graph_relationship,
)
from integrations.ipfs_datasets.types import (
    DEFAULT_USER_ASSERTION_EXTRACTOR_VERSION,
    USER_SOURCE_KINDS,
    build_user_assertion_envelope,
    graph_entity_from_payload,
    graph_relationship_from_payload,
    source_byte_hash,
    user_assertion_from_mapping,
)


STATEMENT = "On March 3, 2024, I complained to HR about discrimination."
MESSAGE_ID = "msg-100"
DOCUMENT_ID = "doc-200"
EXTRACTOR_VERSION = "fixture-extractor.v1"


def _statement_context(**overrides):
    context = {
        "source_kind": "user_statement",
        "message_id": MESSAGE_ID,
        "source_id": MESSAGE_ID,
        "assertion_status": "asserted",
        "extractor_version": EXTRACTOR_VERSION,
        "source_hash": source_byte_hash(STATEMENT),
    }
    context.update(overrides)
    return context


def _asserted_facts(graph):
    facts = []
    for entity in graph.get_entities_by_type("fact"):
        envelope = user_assertion_from_mapping(entity.provenance.get("user_assertion") or {})
        if envelope.is_asserted_user_fact:
            facts.append(entity)
    return facts


def test_validated_user_statement_carries_span_hash_identity_and_stable_id():
    builder = KnowledgeGraphBuilder()
    graph = builder.build_from_text(STATEMENT, source_context=_statement_context())

    asserted = _asserted_facts(graph)
    assert asserted
    entity = asserted[0]
    envelope = user_assertion_from_mapping(entity.provenance["user_assertion"])
    source_bytes = STATEMENT.encode("utf-8")
    sliced = source_bytes[envelope.source_span_start:envelope.source_span_end].decode("utf-8")

    assert envelope.contract_version == "user_assertion.v1"
    assert envelope.source_kind == "user_statement"
    assert envelope.source_kind in USER_SOURCE_KINDS
    assert envelope.message_id == MESSAGE_ID
    assert envelope.source_identity == MESSAGE_ID
    assert sliced == envelope.source_span_text
    assert envelope.source_span_text in STATEMENT
    assert envelope.source_hash == source_byte_hash(STATEMENT)
    assert envelope.assertion_status == "asserted"
    assert envelope.extractor_version == EXTRACTOR_VERSION
    assert envelope.stable_id.startswith("assertion:")
    assert envelope.jurisdiction == ""
    assert envelope.actor == ""
    assert envelope.name == ""
    assert envelope.event_date == ""
    assert entity.id != MESSAGE_ID

    restored_graph = KnowledgeGraph.from_dict(graph.to_dict())
    restored = restored_graph.get_entity(entity.id)
    assert restored.provenance["user_assertion"]["stable_id"] == envelope.stable_id
    assert user_assertion_from_mapping(restored.provenance["user_assertion"]).is_asserted_user_fact

    graph_entity = entity_to_graph_entity(entity)
    round_tripped = graph_entity_to_entity(graph_entity_from_payload(graph_entity.as_dict()))
    assert round_tripped.provenance["user_assertion"]["stable_id"] == envelope.stable_id
    assert round_tripped.id == entity.id


def test_same_source_span_keeps_a_stable_id_across_builders():
    first = KnowledgeGraphBuilder().build_from_text(STATEMENT, source_context=_statement_context())
    second = KnowledgeGraphBuilder().build_from_text(STATEMENT, source_context=_statement_context())
    first_ids = sorted(
        user_assertion_from_mapping(entity.provenance["user_assertion"]).stable_id
        for entity in _asserted_facts(first)
    )
    second_ids = sorted(
        user_assertion_from_mapping(entity.provenance["user_assertion"]).stable_id
        for entity in _asserted_facts(second)
    )
    assert first_ids == second_ids
    assert len(first_ids) == len(set(first_ids))


def test_uploaded_document_assertion_and_case_file_round_trip():
    sentence = "The uploaded notice says the hearing was on March 3, 2024."
    start = sentence.index("March 3, 2024")
    end = start + len("March 3, 2024")
    context = {
        "source_kind": "user_uploaded_document",
        "document_id": DOCUMENT_ID,
        "source_id": DOCUMENT_ID,
        "assertion_status": "asserted",
        "extractor_version": EXTRACTOR_VERSION,
        "source_hash": source_byte_hash(sentence),
        "jurisdiction": "Oregon",
    }
    graph = KnowledgeGraphBuilder().build_from_text(
        sentence,
        source_context=context,
        extractor_provenance={"parser": "fixture-extractor", "document_id": DOCUMENT_ID},
        extracted_entities=[
            {
                "extractor_key": "notice-date",
                "type": "fact",
                "name": "Notice date",
                "attributes": {
                    "description": "March 3, 2024",
                    "fact_type": "timeline",
                    "event_date_or_range": "March 3, 2024",
                },
                "source_span": {"start": start, "end": end, "text": "March 3, 2024"},
                "confidence": 0.99,
            }
        ],
    )
    entity = next(item for item in graph.entities.values() if item.attributes.get("description") == "March 3, 2024")
    envelope = user_assertion_from_mapping(entity.provenance["user_assertion"])
    assert envelope.is_asserted_user_fact
    assert envelope.source_kind == "user_uploaded_document"
    assert envelope.document_id == DOCUMENT_ID
    assert envelope.jurisdiction == "Oregon"
    assert envelope.extractor_version == EXTRACTOR_VERSION
    assert entity.provenance["extractor"]["parser"] == "fixture-extractor"

    facts = build_canonical_facts(graph)
    projected = next(fact for fact in facts if fact["fact_id"] == entity.id)
    assert projected["source_kind"] == "user_uploaded_document"
    assert projected["status"] == "asserted"
    assert projected["validation_status"] == "asserted"
    assert projected["message_id"] == ""
    assert projected["document_id"] == DOCUMENT_ID
    assert projected["source_hash"] == source_byte_hash(sentence)
    assert projected["extractor_version"] == EXTRACTOR_VERSION
    assert projected["stable_id"] == envelope.stable_id
    assert projected["source_span"]["text"] == "March 3, 2024"
    assert projected["source_span_refs"][0]["start"] == start
    assert projected["actor"] == ""
    assert projected["asserted_name"] == ""

    restored = restore_entity_from_canonical_fact(projected)
    restored_graph = KnowledgeGraph()
    restored_graph.add_entity(restored)
    again = build_canonical_facts(restored_graph)[0]
    assert again["user_assertion"] == projected["user_assertion"]
    assert again["stable_id"] == projected["stable_id"]
    assert again["source_kind"] == "user_uploaded_document"


def test_relationship_endpoints_stay_node_ids_and_round_trip():
    left = "I complained to HR on March 3, 2024."
    right = "My employer terminated me on March 18, 2024."
    text = f"{left} {right}"
    context = {
        "source_kind": "user_statement",
        "message_id": MESSAGE_ID,
        "assertion_status": "asserted",
        "extractor_version": EXTRACTOR_VERSION,
        "source_hash": source_byte_hash(text),
    }
    graph = KnowledgeGraphBuilder().build_from_text(
        text,
        source_context=context,
        extracted_entities=[
            {
                "extractor_key": "protected",
                "type": "fact",
                "name": "Protected activity",
                "attributes": {"description": left, "fact_type": "timeline", "predicate_family": "protected_activity"},
                "source_span": {"start": 0, "end": len(left.encode("utf-8")), "text": left},
            },
            {
                "extractor_key": "adverse",
                "type": "fact",
                "name": "Adverse action",
                "attributes": {"description": right, "fact_type": "timeline", "predicate_family": "adverse_action"},
                "source_span": {
                    "start": len((left + " ").encode("utf-8")),
                    "end": len(text.encode("utf-8")),
                    "text": right,
                },
            },
        ],
        extracted_relationships=[
            {
                "source_key": "adverse",
                "target_key": "protected",
                "source_id": MESSAGE_ID,
                "target_id": MESSAGE_ID,
                "type": "occurred_after",
                "source_span": {"start": 0, "end": len(text.encode("utf-8")), "text": text},
                "confidence": 0.99,
                "legal_hit": True,
            }
        ],
    )

    edged = [
        relationship
        for relationship in graph.relationships.values()
        if relationship.relation_type == "occurred_after"
        and user_assertion_from_mapping(relationship.provenance["user_assertion"]).is_asserted_user_fact
    ]
    assert len(edged) == 1
    relationship = edged[0]
    assert relationship.source_id != MESSAGE_ID
    assert relationship.target_id != MESSAGE_ID
    assert relationship.source_id in graph.entities
    assert relationship.target_id in graph.entities
    assert {relationship.source_id, relationship.target_id} != {MESSAGE_ID}
    envelope = user_assertion_from_mapping(relationship.provenance["user_assertion"])
    assert envelope.message_id == MESSAGE_ID
    assert envelope.legal_hit is True
    assert envelope.assertion_status == "asserted"

    payload = relationship_to_graph_relationship(relationship).as_dict()
    restored = graph_relationship_to_relationship(graph_relationship_from_payload(payload))
    assert restored.source_id == relationship.source_id
    assert restored.target_id == relationship.target_id
    assert restored.provenance["user_assertion"]["message_id"] == MESSAGE_ID
    assert restored.provenance["user_assertion"]["stable_id"] == envelope.stable_id

    projected = next(
        edge for edge in build_canonical_fact_edges(graph) if edge["relationship_id"] == relationship.id
    )
    assert projected["source_id"] == relationship.source_id
    assert projected["target_id"] == relationship.target_id
    assert projected["source_kind"] == "user_statement"
    assert projected["status"] == "asserted"
    assert projected["message_id"] == MESSAGE_ID
    assert MESSAGE_ID not in {projected["source_id"], projected["target_id"]}


def test_message_id_alone_cannot_create_an_edge():
    graph = KnowledgeGraphBuilder().build_from_text(
        STATEMENT,
        source_context=_statement_context(),
        extracted_relationships=[
            {
                "source_id": MESSAGE_ID,
                "target_id": MESSAGE_ID,
                "type": "occurred_after",
                "source_span": {"start": 0, "end": len(STATEMENT.encode("utf-8")), "text": STATEMENT},
            }
        ],
    )
    assert all(relationship.source_id != MESSAGE_ID for relationship in graph.relationships.values())
    assert all(relationship.target_id != MESSAGE_ID for relationship in graph.relationships.values())


def test_missing_or_ambiguous_source_context_stays_unverified():
    bare = KnowledgeGraphBuilder().build_from_text(STATEMENT)
    for entity in bare.entities.values():
        envelope = user_assertion_from_mapping(entity.provenance["user_assertion"])
        assert envelope.is_asserted_user_fact is False
        assert envelope.source_kind not in USER_SOURCE_KINDS
        assert envelope.assertion_status != "asserted"
        assert envelope.jurisdiction == ""
        assert envelope.actor == ""
        assert envelope.name == ""
        assert envelope.event_date == ""

    repeated = f"{STATEMENT} {STATEMENT}"
    ambiguous = KnowledgeGraphBuilder().build_from_text(repeated, source_context={
        "source_kind": "user_statement",
        "message_id": MESSAGE_ID,
        "assertion_status": "asserted",
        "extractor_version": EXTRACTOR_VERSION,
        "source_hash": source_byte_hash(repeated),
    })
    for entity in ambiguous.get_entities_by_type("fact"):
        envelope = user_assertion_from_mapping(entity.provenance["user_assertion"])
        if "March 3, 2024" == entity.name:
            assert "ambiguous_source_span" in envelope.deficiencies
        assert envelope.is_asserted_user_fact is False

    mismatched = KnowledgeGraphBuilder().build_from_text(
        STATEMENT,
        source_context=_statement_context(source_hash="0" * 64),
    )
    for entity in mismatched.entities.values():
        envelope = user_assertion_from_mapping(entity.provenance["user_assertion"])
        assert envelope.is_asserted_user_fact is False
        assert "source_hash_mismatch" in envelope.deficiencies
        assert envelope.source_hash == source_byte_hash(STATEMENT)

    conflicting = KnowledgeGraphBuilder().build_from_text(
        STATEMENT,
        source_context=_statement_context(),
        provenance={"source_kind": "user_uploaded_document", "message_id": "msg-other"},
    )
    assert all(
        user_assertion_from_mapping(entity.provenance["user_assertion"]).is_asserted_user_fact is False
        for entity in conflicting.entities.values()
    )


def test_model_claim_and_legal_records_cannot_become_user_facts():
    span = {"start": 0, "end": len(STATEMENT.encode("utf-8")), "text": STATEMENT}
    context = _statement_context()
    graph = KnowledgeGraphBuilder().build_from_text(
        STATEMENT,
        source_context=context,
        extracted_entities=[
            {
                "type": "fact",
                "name": "Model fact",
                "origin": "model",
                "record_type": "model_suggestion",
                "confidence": 0.99,
                "legal_hit": True,
                "attributes": {"description": STATEMENT},
                "source_span": span,
            },
            {
                "type": "claim",
                "name": "Retaliation Claim",
                "confidence": 0.99,
                "attributes": {"description": STATEMENT, "claim_type": "retaliation"},
                "source_span": span,
            },
            {
                "type": "legal_text",
                "name": "Title VII citation",
                "record_type": "legal_text",
                "confidence": 0.99,
                "legal_hit": True,
                "attributes": {"description": STATEMENT},
                "source_span": span,
            },
            {
                "type": "person",
                "name": "Unknown",
                "attributes": {},
            },
        ],
    )

    def envelope_for(name):
        entity = next(item for item in graph.entities.values() if item.name == name)
        return user_assertion_from_mapping(entity.provenance["user_assertion"])

    model_envelope = envelope_for("Model fact")
    claim_envelope = envelope_for("Retaliation Claim")
    legal_envelope = envelope_for("Title VII citation")
    assert model_envelope.record_type == "model_suggestion"
    assert model_envelope.assertion_status == "suggestion"
    assert model_envelope.is_asserted_user_fact is False
    assert model_envelope.source_kind == "model_suggestion"
    assert claim_envelope.record_type == "inferred_claim_label"
    assert claim_envelope.assertion_status == "suggestion"
    assert claim_envelope.is_asserted_user_fact is False
    assert legal_envelope.record_type == "legal_text"
    assert legal_envelope.assertion_status == "legal_text"
    assert legal_envelope.is_asserted_user_fact is False
    assert legal_envelope.legal_hit is True

    facts = build_canonical_facts(graph)
    model_fact = next(fact for fact in facts if fact["text"] == STATEMENT and fact["record_type"] == "model_suggestion")
    assert model_fact["source_kind"] == "model_suggestion"
    assert model_fact["status"] == "suggestion"
    assert model_fact["status"] != "accepted"
    assert model_fact["source_kind"] not in USER_SOURCE_KINDS


def test_confidence_and_legal_hit_do_not_assert_without_user_source():
    envelope = build_user_assertion_envelope(
        source_text=STATEMENT,
        source_kind="user_statement",
        assertion_status="asserted",
        source_span={"start": 0, "end": len(STATEMENT.encode("utf-8")), "text": STATEMENT},
        confidence=0.99,
        legal_hit=True,
        role="fact",
        subject_key="fact|timeline|statement",
    )
    assert envelope.is_asserted_user_fact is False
    assert "missing_source_identity" in envelope.deficiencies
    assert envelope.legal_hit is True
    assert envelope.confidence == 0.99
    assert envelope.jurisdiction == ""
    assert envelope.actor == ""
    assert envelope.name == ""
    assert envelope.event_date == ""

    low = build_user_assertion_envelope(
        source_text=STATEMENT,
        source_kind="user_statement",
        message_id=MESSAGE_ID,
        assertion_status="asserted",
        extractor_version=EXTRACTOR_VERSION,
        source_span={"start": 0, "end": len(STATEMENT.encode("utf-8")), "text": STATEMENT},
        confidence=0.1,
        role="fact",
        subject_key="fact|same",
    )
    high = build_user_assertion_envelope(
        source_text=STATEMENT,
        source_kind="user_statement",
        message_id=MESSAGE_ID,
        assertion_status="asserted",
        extractor_version=EXTRACTOR_VERSION,
        source_span={"start": 0, "end": len(STATEMENT.encode("utf-8")), "text": STATEMENT},
        confidence=0.99,
        role="fact",
        subject_key="fact|same",
    )
    assert low.is_asserted_user_fact and high.is_asserted_user_fact
    assert low.stable_id == high.stable_id
    assert low.assertion_status == high.assertion_status == "asserted"


def test_invalid_span_and_unicode_byte_offsets_fail_closed():
    bad_span = build_user_assertion_envelope(
        source_text=STATEMENT,
        source_kind="user_statement",
        message_id=MESSAGE_ID,
        assertion_status="asserted",
        source_span={"start": 0, "end": 5, "text": "nope"},
        role="fact",
        subject_key="fact|bad-span",
    )
    assert bad_span.is_asserted_user_fact is False
    assert "source_span_mismatch" in bad_span.deficiencies
    assert bad_span.requested_source_kind == "user_statement"
    assert bad_span.source_kind not in USER_SOURCE_KINDS

    out_of_bounds = build_user_assertion_envelope(
        source_text=STATEMENT,
        source_kind="user_statement",
        message_id=MESSAGE_ID,
        assertion_status="asserted",
        source_span={"start": 0, "end": 10_000},
        role="fact",
        subject_key="fact|bounds",
    )
    assert out_of_bounds.is_asserted_user_fact is False
    assert "source_span_out_of_bounds" in out_of_bounds.deficiencies

    source = "Café fired me"
    needle = "fired"
    start = len("Café ".encode("utf-8"))
    end = start + len(needle.encode("utf-8"))
    unicode_envelope = build_user_assertion_envelope(
        source_text=source,
        source_kind="user_statement",
        message_id=MESSAGE_ID,
        assertion_status="asserted",
        extractor_version=EXTRACTOR_VERSION,
        source_span={"start": start, "end": end, "text": needle},
        role="fact",
        subject_key="fact|unicode",
    )
    assert unicode_envelope.is_asserted_user_fact
    assert unicode_envelope.source_span_text == needle
    assert source.encode("utf-8")[start:end].decode("utf-8") == needle
    char_offsets = build_user_assertion_envelope(
        source_text=source,
        source_kind="user_statement",
        message_id=MESSAGE_ID,
        assertion_status="asserted",
        source_span={"start": source.index(needle), "end": source.index(needle) + len(needle), "text": needle},
        role="fact",
        subject_key="fact|char-offsets",
    )
    assert char_offsets.is_asserted_user_fact is False


def test_placeholder_labels_and_legacy_records_do_not_invent_user_facts():
    text = "My employer fired the employee after I complained."
    graph = KnowledgeGraphBuilder().build_from_text(text, source_context={
        "source_kind": "user_statement",
        "message_id": MESSAGE_ID,
        "assertion_status": "asserted",
        "extractor_version": EXTRACTOR_VERSION,
        "source_hash": source_byte_hash(text),
    })
    for name in ("Employer", "Complainant"):
        entity = next(item for item in graph.entities.values() if item.name == name)
        envelope = user_assertion_from_mapping(entity.provenance["user_assertion"])
        assert envelope.is_asserted_user_fact is False
        assert envelope.record_type == "model_suggestion"
        assert envelope.name == ""
        assert envelope.actor == ""

    legacy_graph = KnowledgeGraph()
    legacy_graph.add_entity(
        Entity(
            id="fact:legacy",
            type="fact",
            name="Termination event",
            attributes={"description": "Employer terminated Plaintiff on January 20, 2026."},
        )
    )
    legacy_graph.add_relationship(
        Relationship(
            id="rel:legacy",
            source_id="fact:legacy",
            target_id="fact:legacy",
            relation_type="associated_with",
        )
    )
    legacy_fact = build_canonical_facts(legacy_graph)[0]
    assert legacy_fact["source_kind"] == "knowledge_graph_entity"
    assert legacy_fact["status"] == "accepted"
    assert legacy_fact["validation_status"] == "accepted"
    assert legacy_fact["source_ref"] == "fact:legacy"
    assert "user_assertion" not in legacy_fact
    legacy_edge = build_canonical_fact_edges(legacy_graph)[0]
    assert legacy_edge["source_kind"] == "knowledge_graph_entity"
    assert legacy_edge["status"] == "accepted"
    assert legacy_edge["source_id"] == "fact:legacy"
    assert legacy_edge["target_id"] == "fact:legacy"


def test_extractor_version_defaults_and_envelope_serialization_round_trip():
    envelope = build_user_assertion_envelope(
        source_text=STATEMENT,
        source_kind="user_statement",
        message_id=MESSAGE_ID,
        assertion_status="asserted",
        source_span={"start": 0, "end": len(STATEMENT.encode("utf-8")), "text": STATEMENT},
        role="fact",
        subject_key="fact|default-extractor",
    )
    assert envelope.extractor_version == DEFAULT_USER_ASSERTION_EXTRACTOR_VERSION
    assert envelope.is_asserted_user_fact
    restored = user_assertion_from_mapping(envelope.as_dict())
    assert restored.as_dict() == envelope.as_dict()
    assert restored.is_asserted_user_fact

    accepted_status = build_user_assertion_envelope(
        source_text=STATEMENT,
        source_kind="user_statement",
        message_id=MESSAGE_ID,
        assertion_status="accepted",
        source_span={"start": 0, "end": len(STATEMENT.encode("utf-8")), "text": STATEMENT},
        role="fact",
        subject_key="fact|accepted-is-not-asserted",
    )
    assert accepted_status.is_asserted_user_fact is False
    assert accepted_status.assertion_status != "asserted"


@pytest.mark.parametrize("field,value", [
    ("source_hash", "0" * 64),
    ("stable_id", "assertion:made-up"),
    ("source_span_end", 100_000),
    ("source_span_text", "An invented event"),
    ("source_id", "a-different-source"),
    ("source_kind", "user_uploaded_document"),
    ("contract_version", ""),
])
def test_serialized_assertion_revalidates_hash_span_and_identity(field, value):
    envelope = build_user_assertion_envelope(
        source_text=STATEMENT, source_kind="user_statement", source_id=MESSAGE_ID,
        message_id=MESSAGE_ID, assertion_status="asserted", extractor_version=EXTRACTOR_VERSION,
        source_span={"start": 0, "end": len(STATEMENT.encode()), "text": STATEMENT},
        role="fact", subject_key="fact|serialized-integrity",
    )
    payload = deepcopy(envelope.as_dict())
    payload[field] = value
    restored = user_assertion_from_mapping(payload)
    assert not restored.is_asserted_user_fact
    graph = KnowledgeGraph()
    graph.add_entity(Entity(id="tampered", type="fact", name=STATEMENT,
        attributes={"description": STATEMENT}, provenance={"user_assertion": payload}))
    projected = build_canonical_facts(graph)[0]
    assert projected["assertion_status"] != "asserted"


@pytest.mark.parametrize("entity_type,name,description", [
    ("person", "Invented Person", ""),
    ("date", "January 1, 1900", ""),
    ("fact", "Unsupported event", "Someone admitted liability yesterday."),
])
def test_a_real_span_does_not_support_an_invented_extracted_value(entity_type, name, description):
    graph = KnowledgeGraphBuilder().build_from_text(STATEMENT, source_context=_statement_context(),
        extracted_entities=[{"type": entity_type, "name": name,
            "attributes": {"description": description} if description else {},
            "source_span": {"start": 0, "end": len(STATEMENT.encode()), "text": STATEMENT}}])
    entity = next(item for item in graph.entities.values() if item.name == name)
    assert not user_assertion_from_mapping(entity.provenance["user_assertion"]).is_asserted_user_fact


def test_stable_document_identity_distinguishes_attachments_to_same_message():
    def assertion(document_id):
        return build_user_assertion_envelope(source_text=STATEMENT,
            source_kind="user_uploaded_document", source_id=document_id, document_id=document_id,
            message_id="parent-message", assertion_status="asserted", extractor_version=EXTRACTOR_VERSION,
            source_span={"start": 0, "end": len(STATEMENT.encode()), "text": STATEMENT}, role="fact", subject_key="same")
    first, second = assertion("doc-first"), assertion("doc-second")
    assert first.is_asserted_user_fact and second.is_asserted_user_fact
    assert first.source_identity == "doc-first"
    assert second.source_identity == "doc-second"
    assert first.stable_id != second.stable_id


def test_legacy_temporal_acceptance_is_explicitly_not_user_assertion_admission():
    graph = KnowledgeGraph()
    graph.add_entity(Entity(id="legacy", type="fact", name=STATEMENT))
    fact = build_canonical_facts(graph)[0]
    assert fact["validation_status"] == "accepted"
    assert fact["assertion_status"] == "unverified"
    assert not user_assertion_from_mapping(fact.get("user_assertion")).is_asserted_user_fact


@pytest.mark.parametrize("entity_type,source", [("claim", "complaint"), ("fact", "model"), ("fact", "legal")])
def test_graph_adapter_cannot_launder_non_user_classification(entity_type, source):
    envelope = build_user_assertion_envelope(source_text=STATEMENT,
        source_kind="user_statement", message_id=MESSAGE_ID, assertion_status="asserted",
        source_span={"start": 0, "end": len(STATEMENT.encode()), "text": STATEMENT}, role="fact", subject_key="same")
    entity = Entity(id="reclassified", type=entity_type, name=STATEMENT,
        source=source, provenance={"user_assertion": envelope.as_dict()})
    assert not user_assertion_from_mapping(entity.provenance["user_assertion"]).is_asserted_user_fact
    round_trip = graph_entity_to_entity(entity_to_graph_entity(entity))
    assert not user_assertion_from_mapping(round_trip.provenance["user_assertion"]).is_asserted_user_fact


def test_changed_record_text_cannot_reuse_a_valid_source_envelope():
    envelope = build_user_assertion_envelope(source_text=STATEMENT,
        source_kind="user_statement", message_id=MESSAGE_ID, assertion_status="asserted",
        source_span={"start": 0, "end": len(STATEMENT.encode()), "text": STATEMENT}, role="fact", subject_key="same")
    entity = Entity(id="changed", type="fact", name=STATEMENT,
        provenance={"user_assertion": envelope.as_dict()})
    graph = KnowledgeGraph()
    graph.add_entity(entity)
    entity.attributes["description"] = "A different actor confessed yesterday."
    assert not user_assertion_from_mapping(entity.to_dict()["provenance"]["user_assertion"]).is_asserted_user_fact
    assert build_canonical_facts(graph)[0]["assertion_status"] == "unverified"


def test_merge_retains_distinct_valid_user_source_assertions():
    first = KnowledgeGraphBuilder().build_from_text(STATEMENT,
        source_context=_statement_context(message_id="msg-first", source_id="msg-first"))
    second = KnowledgeGraphBuilder().build_from_text(STATEMENT,
        source_context=_statement_context(message_id="msg-second", source_id="msg-second"))
    first.merge_with(second)
    identities = set()
    for entity in first.get_entities_by_type("fact"):
        records = list(entity.provenance.get("user_assertions") or [])
        records.append(entity.provenance.get("user_assertion") or {})
        for record in records:
            envelope = user_assertion_from_mapping(record)
            if envelope.is_asserted_user_fact:
                identities.add(envelope.source_identity)
    assert identities == {"msg-first", "msg-second"}
    for fact in build_canonical_facts(first):
        restored = restore_entity_from_canonical_fact(fact)
        histories = [user_assertion_from_mapping(item).source_identity
                     for item in restored.provenance.get("user_assertions", [])]
        assert set(histories) == {"msg-first", "msg-second"}


@pytest.mark.parametrize("field,value", [("relation_type", "fired_by"), ("source_id", "another-node"), ("target_id", "another-node")])
def test_relationship_replay_is_bound_to_predicate_and_graph_endpoints(field, value):
    text = "Alice worked for Acme."
    graph = KnowledgeGraphBuilder().build_from_text(text,
        source_context=_statement_context(source_hash=source_byte_hash(text)),
        extracted_entities=[
            {"extractor_key": "alice", "type": "person", "name": "Alice",
             "source_span": {"start": 0, "end": 5, "text": "Alice"}},
            {"extractor_key": "acme", "type": "organization", "name": "Acme",
             "source_span": {"start": 17, "end": 21, "text": "Acme"}},
        ],
        extracted_relationships=[{"source_key": "alice", "target_key": "acme", "type": "worked_for",
            "source_span": {"start": 0, "end": len(text.encode()), "text": text}}])
    edge = next(item for item in graph.relationships.values() if item.relation_type == "worked_for")
    envelope = user_assertion_from_mapping(edge.provenance["user_assertion"])
    assert envelope.is_asserted_user_fact
    assert (envelope.graph_source_id, envelope.graph_target_id) == (edge.source_id, edge.target_id)
    unchanged = graph_relationship_to_relationship(relationship_to_graph_relationship(edge))
    assert user_assertion_from_mapping(unchanged.provenance["user_assertion"]).is_asserted_user_fact
    payload = edge.to_dict()
    payload[field] = value
    replayed = Relationship(**payload)
    assert not user_assertion_from_mapping(replayed.provenance["user_assertion"]).is_asserted_user_fact
    # The projection must also recheck a record changed after construction.
    setattr(edge, field, value)
    outbound = relationship_to_graph_relationship(edge)
    assert not user_assertion_from_mapping(outbound.assertion).is_asserted_user_fact
    projected = next(item for item in build_canonical_fact_edges(graph) if item["relationship_id"] == edge.id)
    assert projected["assertion_status"] != "asserted"


def test_relationship_without_endpoint_proof_stays_unverified():
    envelope = build_user_assertion_envelope(source_text=STATEMENT,
        source_kind="user_statement", message_id=MESSAGE_ID, assertion_status="asserted",
        source_span={"start": 0, "end": len(STATEMENT.encode()), "text": STATEMENT},
        role="worked_for", subject_key="legacy-relationship")
    assert envelope.is_asserted_user_fact
    edge = Relationship(id="legacy-edge", source_id="alice", target_id="acme", relation_type="worked_for",
        provenance={"user_assertion": envelope.as_dict()})
    assert not user_assertion_from_mapping(edge.provenance["user_assertion"]).is_asserted_user_fact
    assert "relationship_binding_mismatch" in edge.provenance["user_assertion"]["deficiencies"]
