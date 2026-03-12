from integrations.ipfs_datasets.types import (
    CaseArtifact,
    CaseAuthority,
    CaseClaimElement,
    CaseFact,
    CaseSupportEdge,
    DocumentChunk,
    DocumentParseResult,
    DocumentParseSummary,
    DocumentTransformLineage,
    GraphEntity,
    GraphPayload,
    GraphRelationship,
    GraphSnapshotResult,
    GraphSupportMatch,
    GraphSupportResult,
    GraphSupportSummary,
    FormalPredicate,
    ProvenanceRecord,
    ValidationRun,
)


def test_case_artifact_generates_stable_identifier_and_preserves_alias():
    provenance = ProvenanceRecord(content_hash="abc123", source_url="https://example.com/file")
    artifact = CaseArtifact(
        cid="QmExample",
        artifact_type="document",
        size=12,
        timestamp="2026-03-10T00:00:00",
        content_hash="abc123",
        provenance=provenance,
    )

    payload = artifact.as_dict()
    assert payload["type"] == "document"
    assert payload["artifact_id"].startswith("artifact:")
    assert payload["content_hash"] == "abc123"


def test_case_authority_generates_stable_identifier_and_claim_links():
    authority = CaseAuthority(
        authority_type="statute",
        source="us_code",
        citation="42 U.S.C. § 1983",
        title="Civil Rights Act",
        claim_element_id="civil_rights:1",
        claim_element="Protected activity",
    )

    payload = authority.as_dict()
    assert payload["type"] == "statute"
    assert payload["authority_id"].startswith("authority:")
    assert payload["claim_element_id"] == "civil_rights:1"


def test_document_parse_types_serialize_with_nested_contract():
    chunk = DocumentChunk(
        chunk_id="chunk-0",
        index=0,
        start=0,
        end=12,
        text="Example text",
        length=12,
        metadata={"kind": "paragraph"},
    )
    summary = DocumentParseSummary(
        status="fallback",
        chunk_count=1,
        text_length=12,
        parser_version="documents-adapter:1",
        input_format="text",
        paragraph_count=1,
    )
    lineage = DocumentTransformLineage(
        source="file",
        parser_version="documents-adapter:1",
        input_format="text",
        normalization="text_normalization",
        chunking={"chunk_size": 1000, "overlap": 100, "chunk_count": 1},
    )

    payload = DocumentParseResult(
        status="fallback",
        text="Example text",
        chunks=[chunk],
        summary=summary,
        lineage=lineage,
        metadata={"source": "file"},
    ).as_dict()

    assert payload["chunks"][0]["chunk_id"] == "chunk-0"
    assert payload["summary"]["parser_version"] == "documents-adapter:1"
    assert payload["lineage"]["source"] == "file"
    assert payload["metadata"]["source"] == "file"


def test_claim_element_and_support_edge_generate_identifiers():
    claim_element = CaseClaimElement(claim_type="employment", element_text="Adverse action")
    support_edge = CaseSupportEdge(
        source_node="fact:1",
        target_node=claim_element.element_id,
        relation_type="supports",
    )

    assert claim_element.element_id.startswith("claim_element:")
    assert support_edge.edge_id.startswith("support_edge:")


def test_graph_types_serialize_with_aliases_and_nested_summary():
    entity = GraphEntity(
        entity_id="artifact:1",
        entity_type="artifact",
        name="Evidence Artifact",
        confidence=1.0,
    )
    relationship = GraphRelationship(
        relationship_id="rel:1",
        source_id="artifact:1",
        target_id="fact:1",
        relation_type="has_fact",
        confidence=1.0,
    )
    support_match = GraphSupportMatch(
        fact_id="fact:1",
        text="Employee complained to HR.",
        score=2.0,
        confidence=0.7,
        matched_claim_element=True,
        duplicate_count=2,
        cluster_size=2,
        cluster_texts=["Employee complained to HR."],
        support_kind="evidence",
        source_table="evidence",
        support_kind_set=["evidence"],
        source_table_set=["evidence"],
        claim_element_id="employment:1",
        claim_element_text="Protected activity",
        support_ref="QmEvidence",
        evidence_record_id=12,
    )

    payload = GraphSupportResult(
        status="available-fallback",
        claim_element_id="employment:1",
        claim_type="employment",
        claim_element_text="Protected activity",
        graph_id="graph:1",
        results=[support_match],
        summary=GraphSupportSummary(result_count=1, total_fact_count=2, max_score=2.0),
        metadata={"backend_available": False},
    ).as_dict()
    graph_payload = GraphPayload(
        status="available-fallback",
        source_id="artifact:1",
        entities=[entity],
        relationships=[relationship],
        metadata={"sentence_count": 1},
    ).as_dict()
    snapshot_payload = GraphSnapshotResult(
        status="noop",
        graph_id="graph:1",
        persisted=False,
        created=False,
        reused=False,
        node_count=1,
        edge_count=1,
        metadata={"source_id": "artifact:1"},
    ).as_dict()

    assert graph_payload["entities"][0]["id"] == "artifact:1"
    assert graph_payload["entities"][0]["type"] == "artifact"
    assert graph_payload["relationships"][0]["id"] == "rel:1"
    assert payload["results"][0]["evidence_record_id"] == 12
    assert payload["summary"]["result_count"] == 1
    assert snapshot_payload["node_count"] == 1


def test_formal_predicate_and_validation_run_serialize():
    predicate = FormalPredicate(
        predicate_text="adverse_action(employee)",
        grounded_fact_ids=["fact:1"],
        authority_ids=["authority:1"],
        predicate_type="fol",
        confidence=0.8,
    )
    validation = ValidationRun(
        run_id="validation:1",
        validator_name="logic",
        status="partial",
        supported_ids=[predicate.predicate_id],
        unsupported_ids=["claim_element:1"],
    )

    predicate_payload = predicate.as_dict()
    validation_payload = validation.as_dict()

    assert predicate_payload["predicate_id"].startswith("predicate:")
    assert predicate_payload["grounded_fact_ids"] == ["fact:1"]
    assert validation_payload["validator_name"] == "logic"
    assert validation_payload["status"] == "partial"


def test_case_fact_serializes_with_provenance():
    fact = CaseFact(
        fact_id="fact:1",
        text="Employee was terminated after complaint",
        source_artifact_id="artifact:1",
        confidence=0.9,
        provenance=ProvenanceRecord(source_url="https://example.com/evidence"),
    )

    payload = fact.as_dict()
    assert payload["fact_id"] == "fact:1"
    assert payload["source_artifact_id"] == "artifact:1"
    assert payload["provenance"]["source_url"] == "https://example.com/evidence"