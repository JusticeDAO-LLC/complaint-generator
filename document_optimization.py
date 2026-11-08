"""Compatibility shim. Implementation lives in complaint_phases.document_optimization."""

from complaint_phases.document_optimization import (
    EMBEDDINGS_AVAILABLE,
    IPFS_AVAILABLE,
    LLM_ROUTER_AVAILABLE,
    UPSTREAM_AGENTIC_AVAILABLE,
    AgenticDocumentOptimizer,
    _build_claim_reasoning_theorem_export_metadata,
    _build_claim_support_temporal_handoff,
    _build_document_execution_drift_summary,
    _build_document_grounding_improvement_summary,
    _build_document_grounding_lane_outcome_summary,
    _build_workflow_targeting_summary,
    generate_text_with_metadata,
    get_embeddings_router,
    store_bytes,
)

__all__ = [
    "AgenticDocumentOptimizer",
    "LLM_ROUTER_AVAILABLE",
    "EMBEDDINGS_AVAILABLE",
    "IPFS_AVAILABLE",
    "UPSTREAM_AGENTIC_AVAILABLE",
    "generate_text_with_metadata",
    "get_embeddings_router",
    "store_bytes",
]
