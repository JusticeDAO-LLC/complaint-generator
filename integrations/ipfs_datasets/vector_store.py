from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .loader import import_attr_optional, import_module_optional
from .types import with_adapter_metadata


EmbeddingsRouter, _embeddings_error = import_attr_optional(
    "ipfs_datasets_py.embeddings_router",
    "EmbeddingsRouter",
)
_vector_stores_module, _vector_stores_error = import_module_optional(
    "ipfs_datasets_py.vector_stores"
)

EMBEDDINGS_AVAILABLE = EmbeddingsRouter is not None
VECTOR_STORE_AVAILABLE = EMBEDDINGS_AVAILABLE or _vector_stores_module is not None
VECTOR_STORE_ERROR = _embeddings_error or _vector_stores_error


def get_embeddings_router(*args: Any, **kwargs: Any) -> Any:
    if EmbeddingsRouter is None:
        return None
    return EmbeddingsRouter(*args, **kwargs)


def create_vector_index(
    documents: Iterable[Dict[str, Any]],
    *,
    index_name: Optional[str] = None,
) -> Dict[str, Any]:
    document_list = list(documents)
    return with_adapter_metadata(
        {
            "status": "not_implemented" if VECTOR_STORE_AVAILABLE else "unavailable",
            "index_name": index_name or "",
            "document_count": len(document_list),
        },
        operation="create_vector_index",
        backend_available=VECTOR_STORE_AVAILABLE,
        degraded_reason=VECTOR_STORE_ERROR if not VECTOR_STORE_AVAILABLE else None,
        implementation_status="not_implemented" if VECTOR_STORE_AVAILABLE else "unavailable",
    )


def search_vector_index(
    query: str,
    *,
    index_name: Optional[str] = None,
    top_k: int = 10,
) -> Dict[str, Any]:
    return with_adapter_metadata(
        {
            "status": "not_implemented" if VECTOR_STORE_AVAILABLE else "unavailable",
            "index_name": index_name or "",
            "query": query,
            "top_k": top_k,
            "results": [],
        },
        operation="search_vector_index",
        backend_available=VECTOR_STORE_AVAILABLE,
        degraded_reason=VECTOR_STORE_ERROR if not VECTOR_STORE_AVAILABLE else None,
        implementation_status="not_implemented" if VECTOR_STORE_AVAILABLE else "unavailable",
    )


__all__ = [
    "EmbeddingsRouter",
    "EMBEDDINGS_AVAILABLE",
    "VECTOR_STORE_AVAILABLE",
    "VECTOR_STORE_ERROR",
    "get_embeddings_router",
    "create_vector_index",
    "search_vector_index",
]