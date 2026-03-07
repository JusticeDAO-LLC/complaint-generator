from mediator.integrations.contracts import NormalizedRetrievalRecord
from mediator.integrations.retrieval_orchestrator import RetrievalOrchestrator


def test_retrieval_orchestrator_cross_source_fusion_annotates_metadata():
    orchestrator = RetrievalOrchestrator()
    query_context = orchestrator.build_query_context(
        query="employment retaliation termination",
        complaint_type="employment_retaliation",
        jurisdiction="federal",
    )
    records = [
        NormalizedRetrievalRecord(
            source_type="statute",
            source_name="us_code",
            query="employment retaliation termination",
            title="Termination retaliation protections",
            citation="42 U.S.C. § 2000e-3",
            snippet="Federal retaliation protections after reporting discrimination",
            score=0.24,
            confidence=0.6,
            metadata={"jurisdiction": "federal"},
        ),
        NormalizedRetrievalRecord(
            source_type="web_archive",
            source_name="common_crawl",
            query="employment retaliation termination",
            title="Termination retaliation memo",
            url="example-dot-com/termination-retaliation-memo",
            snippet="Archived guidance discussing termination retaliation evidence",
            score=0.20,
            confidence=0.5,
        ),
    ]

    ranked = orchestrator.merge_and_rank(records, max_results=5, query_context=query_context)

    assert len(ranked) == 2
    statute = next(item for item in ranked if item.source_type == "statute")
    assert statute.metadata["cross_source_fusion_applied"] is True
    assert statute.metadata["cross_source_type_count"] >= 2
    assert statute.metadata["cross_source_hybrid_legal_evidence"] is True
    assert statute.metadata["orchestrator_fusion_weight"] > 0.0


def test_retrieval_orchestrator_cross_source_fusion_prefers_corroborated_record():
    orchestrator = RetrievalOrchestrator()
    query_context = orchestrator.build_query_context(
        query="employment retaliation termination",
        complaint_type="employment_retaliation",
        jurisdiction="federal",
    )
    records = [
        NormalizedRetrievalRecord(
            source_type="statute",
            source_name="us_code",
            query="employment retaliation termination",
            title="Termination retaliation protections",
            citation="42 U.S.C. § 2000e-3",
            snippet="Federal retaliation protections after reporting discrimination",
            score=0.24,
            confidence=0.6,
            metadata={"jurisdiction": "federal"},
        ),
        NormalizedRetrievalRecord(
            source_type="web_archive",
            source_name="common_crawl",
            query="employment retaliation termination",
            title="Termination retaliation memo",
            url="example-dot-com/termination-retaliation-memo",
            snippet="Archived guidance discussing termination retaliation evidence",
            score=0.20,
            confidence=0.5,
        ),
        NormalizedRetrievalRecord(
            source_type="statute",
            source_name="statute_store",
            query="employment retaliation termination",
            title="Employment retaliation compliance rule",
            citation="29 U.S.C. § 9999",
            snippet="General retaliation compliance summary",
            score=0.29,
            confidence=0.6,
            metadata={"jurisdiction": "federal"},
        ),
    ]

    ranked = orchestrator.merge_and_rank(records, max_results=5, query_context=query_context)

    assert ranked[0].title == "Termination retaliation protections"
    corroborated = ranked[0]
    isolated = next(item for item in ranked if item.title == "Employment retaliation compliance rule")
    assert corroborated.metadata["orchestrator_fusion_weight"] > isolated.metadata["orchestrator_fusion_weight"]


def test_retrieval_orchestrator_build_support_bundle_separates_buckets():
    orchestrator = RetrievalOrchestrator()
    query_context = orchestrator.build_query_context(
        query="employment retaliation termination",
        complaint_type="employment_retaliation",
        jurisdiction="federal",
    )
    records = [
        NormalizedRetrievalRecord(
            source_type="statute",
            source_name="us_code",
            query="employment retaliation termination",
            title="Termination retaliation protections",
            citation="42 U.S.C. § 2000e-3",
            snippet="Federal retaliation protections after reporting discrimination",
            score=0.24,
            confidence=0.6,
            metadata={"jurisdiction": "federal"},
        ),
        NormalizedRetrievalRecord(
            source_type="web_archive",
            source_name="common_crawl",
            query="employment retaliation termination",
            title="Termination retaliation memo",
            url="example-dot-com/termination-retaliation-memo",
            snippet="Archived guidance discussing termination retaliation evidence",
            score=0.20,
            confidence=0.5,
        ),
    ]

    ranked = orchestrator.merge_and_rank(records, max_results=5, query_context=query_context)
    support_bundle = orchestrator.build_support_bundle(ranked, max_items_per_bucket=3)

    assert support_bundle["summary"]["total_records"] == 2
    assert support_bundle["summary"]["authority_count"] == 1
    assert support_bundle["summary"]["evidence_count"] == 1
    assert len(support_bundle["top_authorities"]) == 1
    assert len(support_bundle["top_evidence"]) == 1
    assert len(support_bundle["cross_supported"]) >= 1
    assert len(support_bundle["hybrid_cross_supported"]) >= 1
