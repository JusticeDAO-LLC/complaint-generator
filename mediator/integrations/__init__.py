"""Integration primitives for ipfs_datasets_py enhancements."""

from .adapter import IPFSDatasetsAdapter, detect_ipfs_datasets_capabilities
from .contracts import (
    CapabilityCatalog,
    CapabilityStatus,
    NormalizedRetrievalBundle,
    NormalizedRetrievalRecord,
)
from .settings import IntegrationFeatureFlags
from .retrieval_orchestrator import RetrievalOrchestrator
from .provenance import ProvenanceRecord, build_provenance_record
from .caching import TTLCache
from .vector_tools import VectorRetrievalAugmentor
from .graph_tools import GraphRetrievalAugmentor, GraphAwareRetrievalReranker

__all__ = [
    "IPFSDatasetsAdapter",
    "detect_ipfs_datasets_capabilities",
    "CapabilityCatalog",
    "CapabilityStatus",
    "NormalizedRetrievalBundle",
    "NormalizedRetrievalRecord",
    "IntegrationFeatureFlags",
    "RetrievalOrchestrator",
    "ProvenanceRecord",
    "build_provenance_record",
    "TTLCache",
    "VectorRetrievalAugmentor",
    "GraphRetrievalAugmentor",
    "GraphAwareRetrievalReranker",
]
