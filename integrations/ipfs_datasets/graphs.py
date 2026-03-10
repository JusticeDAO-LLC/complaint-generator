from __future__ import annotations

from typing import Any, Dict, Optional

from .loader import import_module_optional


_knowledge_graphs_module, _knowledge_graphs_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs"
)
_graph_extraction_module, _graph_extraction_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.extraction"
)
_graph_query_module, _graph_query_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.query"
)
_graph_storage_module, _graph_storage_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.storage"
)
_graph_lineage_module, _graph_lineage_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.lineage"
)

KNOWLEDGE_GRAPHS_AVAILABLE = any(
    value is not None
    for value in (
        _knowledge_graphs_module,
        _graph_extraction_module,
        _graph_query_module,
        _graph_storage_module,
    )
)
GRAPHS_ERROR = (
    _knowledge_graphs_error
    or _graph_extraction_error
    or _graph_query_error
    or _graph_storage_error
    or _graph_lineage_error
)


def extract_graph_from_text(
    text: str,
    *,
    source_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "status": "available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
        "source_id": source_id or "",
        "entities": [],
        "relationships": [],
        "metadata": {
            **(metadata or {}),
            "text_length": len(text),
            "backend_available": KNOWLEDGE_GRAPHS_AVAILABLE,
        },
    }


def query_graph_support(
    claim_element_id: str,
    *,
    graph_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
        "claim_element_id": claim_element_id,
        "graph_id": graph_id or "",
        "results": [],
    }


def persist_graph_snapshot(
    graph_payload: Dict[str, Any],
    *,
    graph_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "pending" if _graph_storage_module is not None else "noop",
        "graph_id": graph_id or "",
        "persisted": False,
        "node_count": len(graph_payload.get("entities", []) or []),
        "edge_count": len(graph_payload.get("relationships", []) or []),
    }


__all__ = [
    "KNOWLEDGE_GRAPHS_AVAILABLE",
    "GRAPHS_ERROR",
    "extract_graph_from_text",
    "query_graph_support",
    "persist_graph_snapshot",
]