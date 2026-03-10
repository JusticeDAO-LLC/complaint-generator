from integrations.ipfs_datasets.types import (
    CaseArtifact,
    CaseAuthority,
    CaseClaimElement,
    CaseFact,
    CaseSupportEdge,
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


def test_claim_element_and_support_edge_generate_identifiers():
    claim_element = CaseClaimElement(claim_type="employment", element_text="Adverse action")
    support_edge = CaseSupportEdge(
        source_node="fact:1",
        target_node=claim_element.element_id,
        relation_type="supports",
    )

    assert claim_element.element_id.startswith("claim_element:")
    assert support_edge.edge_id.startswith("support_edge:")


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