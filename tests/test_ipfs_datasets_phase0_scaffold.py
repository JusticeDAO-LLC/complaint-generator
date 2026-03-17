from mediator.integrations.adapter import IPFSDatasetsAdapter
from mediator.integrations.contracts import (
    CapabilityCatalog,
    CapabilityStatus,
    NormalizedRetrievalRecord,
)
from mediator.integrations.retrieval_orchestrator import RetrievalOrchestrator
from mediator.integrations.settings import IntegrationFeatureFlags


def test_integration_feature_flags_from_config_defaults():
    flags = IntegrationFeatureFlags.from_config({"MEDIATOR": {}})
    assert flags.enhanced_legal is False
    assert flags.enhanced_search is False
    assert flags.reranker_mode == "off"
    assert flags.retrieval_max_latency_ms == 1500


def test_retrieval_orchestrator_merges_by_dedupe_key_and_keeps_best_score():
    orchestrator = RetrievalOrchestrator()
    records = [
        NormalizedRetrievalRecord(
            source_type="web",
            source_name="brave",
            query="title vii",
            title="A",
            url="example-dot-com/a",
            score=0.45,
            confidence=0.3,
        ),
        NormalizedRetrievalRecord(
            source_type="legal",
            source_name="us_code",
            query="title vii",
            title="A newer",
            url="example-dot-com/a",
            score=0.82,
            confidence=0.7,
        ),
    ]

    ranked = orchestrator.merge_and_rank(records, max_results=5)
    assert len(ranked) == 1
    assert ranked[0].score == 0.82


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
            source_name="llm_statute_retrieval",
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


def test_adapter_registry_respects_availability_and_flags():
    capabilities = CapabilityCatalog(
        legal_datasets=CapabilityStatus(name="legal", available=True),
        search_tools=CapabilityStatus(name="search", available=False, details="missing"),
        graph_tools=CapabilityStatus(name="graph", available=True),
        vector_tools=CapabilityStatus(name="vector", available=True),
        optimizer_tools=CapabilityStatus(name="optimizer", available=False),
        mcp_tools=CapabilityStatus(name="mcp", available=True),
    )
    flags = IntegrationFeatureFlags(
        enhanced_legal=True,
        enhanced_search=True,
        enhanced_graph=False,
        enhanced_vector=False,
        enhanced_optimizer=True,
        reranker_mode="off",
        retrieval_max_latency_ms=1500,
    )
    adapter = IPFSDatasetsAdapter(feature_flags=flags, capabilities=capabilities)

    registry = adapter.capability_registry()
    assert registry["legal_datasets"]["active"] is True
    assert registry["search_tools"]["active"] is False
    assert registry["search_tools"]["details"] == "missing"
