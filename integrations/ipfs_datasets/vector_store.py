from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import numpy as np
except ModuleNotFoundError as exc:
    np = None
    _numpy_error = str(exc)
else:
    _numpy_error = ""

from .loader import import_attr_optional, import_module_optional, import_failure_message
from .types import with_adapter_metadata

try:
    import numpy as np
except Exception as exc:  # pragma: no cover - depends on optional install state
    np = None
    _numpy_error = str(exc)
else:
    _numpy_error = None


_embeddings_router_module, _embeddings_module_error = import_module_optional(
    "ipfs_datasets_py.embeddings_router"
)
EmbeddingsRouter, _embeddings_error = import_attr_optional(
    "ipfs_datasets_py.embeddings_router",
    "EmbeddingsRouter",
)
embed_text, _embed_text_error = import_attr_optional(
    "ipfs_datasets_py.embeddings_router",
    "embed_text",
)
embed_texts, _embed_texts_error = import_attr_optional(
    "ipfs_datasets_py.embeddings_router",
    "embed_texts",
)
embed_texts_batched, _embed_texts_batched_error = import_attr_optional(
    "ipfs_datasets_py.embeddings_router",
    "embed_texts_batched",
)
_vector_stores_module, _vector_stores_error = import_module_optional(
    "ipfs_datasets_py.vector_stores"
)
create_vector_store, _create_vector_store_error = import_attr_optional(
    "ipfs_datasets_py.vector_stores.api",
    "create_vector_store",
)

if EmbeddingsRouter is None and _embeddings_router_module is not None:
    class EmbeddingsRouter:  # type: ignore[no-redef]
        """Compatibility facade for vendored embeddings_router modules without a class export."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = dict(kwargs)

        def _merged_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
            merged = dict(self.kwargs)
            merged.update(kwargs)
            return merged

        def embed_text(self, text: str, **kwargs: Any) -> Any:
            if embed_text is None:
                raise RuntimeError(_embed_text_error or "embed_text unavailable")
            return embed_text(text, **self._merged_kwargs(kwargs))

        def embed_texts(self, texts: Iterable[str], **kwargs: Any) -> Any:
            if embed_texts is None:
                raise RuntimeError(_embed_texts_error or "embed_texts unavailable")
            return embed_texts(list(texts), **self._merged_kwargs(kwargs))

        def embed_texts_batched(self, texts: Iterable[str], **kwargs: Any) -> Any:
            if embed_texts_batched is None:
                raise RuntimeError(_embed_texts_batched_error or "embed_texts_batched unavailable")
            return embed_texts_batched(list(texts), **self._merged_kwargs(kwargs))


def _error_message(value: Any) -> str:
    return str(import_failure_message(value) or "").strip()


def _first_error(*errors: Any) -> str:
    for error in errors:
        message = _error_message(error)
        if message:
            return message
    return ""


EMBEDDINGS_AVAILABLE = any(
    value is not None
    for value in (embed_text, embed_texts, embed_texts_batched, EmbeddingsRouter)
)
EMBEDDINGS_ERROR = "" if EMBEDDINGS_AVAILABLE else _first_error(
    _embeddings_error,
    _embed_text_error,
    _embed_texts_error,
    _embed_texts_batched_error,
    _embeddings_module_error,
)
VECTOR_STORE_AVAILABLE = EMBEDDINGS_AVAILABLE or _vector_stores_module is not None
VECTOR_STORE_ERROR = _first_error(
    EMBEDDINGS_ERROR,
    _create_vector_store_error,
    _vector_stores_error,
    _numpy_error,
)


def _numpy_required_error(operation: str) -> Dict[str, Any]:
    return with_adapter_metadata(
        {
            "status": "unavailable",
            "error": "numpy is required for local vector persistence and search",
        },
        operation=operation,
        backend_available=False,
        degraded_reason=_numpy_error or "numpy unavailable",
        implementation_status="unavailable",
    )


def get_embeddings_router(*args: Any, **kwargs: Any) -> Any:
    if EmbeddingsRouter is None:
        return None
    return EmbeddingsRouter(*args, **kwargs)


async def create_vector_store_async(*args: Any, **kwargs: Any) -> Any:
    if create_vector_store is None:
        raise RuntimeError(str(_create_vector_store_error or "create_vector_store unavailable"))
    return await create_vector_store(*args, **kwargs)


def embeddings_backend_status(
    *args: Any,
    probe_text: str = "",
    perform_probe: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    if not EMBEDDINGS_AVAILABLE:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "router_name": "",
                "router_present": False,
                "available_methods": [],
                "probe_performed": False,
                "error": VECTOR_STORE_ERROR or "embeddings router unavailable",
            },
            operation="embeddings_backend_status",
            backend_available=False,
            degraded_reason=VECTOR_STORE_ERROR,
            implementation_status="unavailable",
        )

    router = None
    router_error = ""
    try:
        router = get_embeddings_router(*args, **kwargs)
    except Exception as exc:
        router_error = str(exc)

    available_methods: List[str] = []
    if callable(embed_text):
        available_methods.append("embed_text")
    if callable(embed_texts):
        available_methods.append("embed_texts")
    if callable(embed_texts_batched):
        available_methods.append("embed_texts_batched")

    payload: Dict[str, Any] = {
        "status": "available" if not router_error else "degraded",
        "router_name": type(router).__name__ if router is not None else "",
        "router_present": router is not None,
        "router_factory": getattr(EmbeddingsRouter, "__name__", ""),
        "available_methods": available_methods,
        "probe_performed": False,
        "error": router_error,
    }

    if perform_probe:
        payload["probe_performed"] = True
        candidate_text = probe_text or "HACC embeddings router health check"
        try:
            vector: Any = None
            if router is not None and callable(getattr(router, "embed_text", None)):
                vector = router.embed_text(candidate_text)
            elif callable(embed_text):
                vector = embed_text(candidate_text, **dict(kwargs))
            payload["probe_status"] = "available"
            payload["vector_length"] = len(vector) if isinstance(vector, (list, tuple)) else 0
        except Exception as exc:
            payload["status"] = "error"
            payload["probe_status"] = "error"
            payload["error"] = str(exc)

    return with_adapter_metadata(
        payload,
        operation="embeddings_backend_status",
        backend_available=payload["status"] == "available",
        degraded_reason=payload.get("error") or None,
        implementation_status="available" if payload["status"] != "unavailable" else "unavailable",
    )


def vector_index_backend_status(
    *,
    require_local_persistence: bool = True,
) -> Dict[str, Any]:
    if not callable(embed_texts_batched):
        error = _first_error(_embed_texts_batched_error, EMBEDDINGS_ERROR, VECTOR_STORE_ERROR) or "embed_texts_batched unavailable"
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "index_backend_present": False,
                "local_persistence_ready": False,
                "available_methods": [],
                "error": error,
            },
            operation="vector_index_backend_status",
            backend_available=False,
            degraded_reason=error,
            implementation_status="unavailable",
        )

    if require_local_persistence and np is None:
        unavailable = _numpy_required_error("vector_index_backend_status")
        unavailable.update(
            {
                "index_backend_present": True,
                "local_persistence_ready": False,
                "available_methods": ["embed_texts_batched"],
            }
        )
        return unavailable

    return with_adapter_metadata(
        {
            "status": "available",
            "index_backend_present": True,
            "local_persistence_ready": np is not None,
            "available_methods": ["embed_texts_batched"],
            "error": "",
        },
        operation="vector_index_backend_status",
        backend_available=True,
        implementation_status="available",
    )


def _normalize_documents(documents: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, document in enumerate(documents):
        text = str(document.get("text") or document.get("content") or "").strip()
        if not text:
            continue
        normalized.append(
            {
                "id": str(document.get("id") or document.get("chunk_id") or f"doc-{index}"),
                "text": text,
                "metadata": dict(document.get("metadata") or {}),
            }
        )
    return normalized


def _write_index_payload(
    *,
    output_dir: Path,
    index_name: str,
    documents: List[Dict[str, Any]],
    vectors: List[List[float]],
    model_name: Optional[str],
    provider: Optional[str],
) -> Dict[str, str]:
    if np is None:
        raise RuntimeError("numpy is required for local vector persistence")

    output_dir.mkdir(parents=True, exist_ok=True)

    vectors_path = output_dir / f"{index_name}.vectors.npy"
    records_path = output_dir / f"{index_name}.records.jsonl"
    manifest_path = output_dir / f"{index_name}.manifest.json"

    np.save(vectors_path, np.asarray(vectors, dtype=np.float32))
    with records_path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=False) + "\n")

    manifest = {
        "index_name": index_name,
        "document_count": len(documents),
        "dimension": len(vectors[0]) if vectors else 0,
        "provider": provider or "ipfs_datasets_py.auto",
        "model_name": model_name or "",
        "vectors_path": str(vectors_path),
        "records_path": str(records_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "vectors_path": str(vectors_path),
        "records_path": str(records_path),
        "manifest_path": str(manifest_path),
    }


def create_vector_index(
    documents: Iterable[Dict[str, Any]],
    *,
    index_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    batch_size: int = 32,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    document_list = _normalize_documents(documents)
    resolved_index_name = index_name or "vector_index"

    if np is None or embed_texts_batched is None:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "index_name": resolved_index_name,
                "document_count": len(document_list),
            },
            operation="create_vector_index",
            backend_available=False,
            degraded_reason=VECTOR_STORE_ERROR,
            implementation_status="unavailable",
        )

    if not document_list:
        return with_adapter_metadata(
            {
                "status": "error",
                "index_name": resolved_index_name,
                "document_count": 0,
                "error": "No non-empty documents were provided for indexing",
            },
            operation="create_vector_index",
            backend_available=True,
            implementation_status="error",
        )

    texts = [document["text"] for document in document_list]
    try:
        vectors = embed_texts_batched(
            texts,
            batch_size=batch_size,
            provider=provider,
            model_name=model_name,
        )
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "index_name": resolved_index_name,
                "document_count": len(document_list),
                "error": str(exc),
            },
            operation="create_vector_index",
            backend_available=True,
            implementation_status="error",
        )

    payload: Dict[str, Any] = {
        "status": "success",
        "index_name": resolved_index_name,
        "document_count": len(document_list),
        "dimension": len(vectors[0]) if vectors else 0,
        "provider": provider or "ipfs_datasets_py.auto",
        "model_name": model_name or "",
    }
    if output_dir:
        if np is None:
            unavailable = _numpy_required_error("create_vector_index")
            unavailable.update(
                {
                    "index_name": resolved_index_name,
                    "document_count": len(document_list),
                }
            )
            return unavailable
        payload["files"] = _write_index_payload(
            output_dir=Path(output_dir),
            index_name=resolved_index_name,
            documents=document_list,
            vectors=vectors,
            model_name=model_name,
            provider=provider,
        )

    return with_adapter_metadata(
        payload,
        operation="create_vector_index",
        backend_available=True,
        implementation_status="implemented",
        extra_metadata={"batch_size": batch_size},
    )


def search_vector_index(
    query: str,
    *,
    index_name: Optional[str] = None,
    index_dir: Optional[str] = None,
    top_k: int = 10,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_index_name = index_name or "vector_index"
    if np is None or embed_texts_batched is None:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "index_name": resolved_index_name,
                "query": query,
                "top_k": top_k,
                "results": [],
            },
            operation="search_vector_index",
            backend_available=False,
            degraded_reason=VECTOR_STORE_ERROR,
            implementation_status="unavailable",
        )

    if np is None:
        unavailable = _numpy_required_error("search_vector_index")
        unavailable.update(
            {
                "index_name": resolved_index_name,
                "query": query,
                "top_k": top_k,
                "results": [],
            }
        )
        return unavailable

    if not index_dir:
        return with_adapter_metadata(
            {
                "status": "error",
                "index_name": resolved_index_name,
                "query": query,
                "top_k": top_k,
                "results": [],
                "error": "index_dir is required for local vector index search",
            },
            operation="search_vector_index",
            backend_available=True,
            implementation_status="error",
        )

    base_dir = Path(index_dir)
    vectors_path = base_dir / f"{resolved_index_name}.vectors.npy"
    records_path = base_dir / f"{resolved_index_name}.records.jsonl"
    if not vectors_path.exists() or not records_path.exists():
        return with_adapter_metadata(
            {
                "status": "error",
                "index_name": resolved_index_name,
                "query": query,
                "top_k": top_k,
                "results": [],
                "error": f"Missing index files for {resolved_index_name} in {base_dir}",
            },
            operation="search_vector_index",
            backend_available=True,
            implementation_status="error",
        )

    try:
        vectors = np.load(vectors_path)
        records = [
            json.loads(line)
            for line in records_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        query_vector = np.asarray(
            embed_texts_batched(
                [query],
                batch_size=1,
                provider=provider,
                model_name=model_name,
            )[0],
            dtype=np.float32,
        )
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "index_name": resolved_index_name,
                "query": query,
                "top_k": top_k,
                "results": [],
                "error": str(exc),
            },
            operation="search_vector_index",
            backend_available=True,
            implementation_status="error",
        )

    vector_norms = np.linalg.norm(vectors, axis=1)
    query_norm = np.linalg.norm(query_vector)
    safe_denominator = np.maximum(vector_norms * max(query_norm, 1e-12), 1e-12)
    scores = np.dot(vectors, query_vector) / safe_denominator
    ranked_indices = np.argsort(-scores)[: max(0, int(top_k))]

    results = []
    for idx in ranked_indices:
        if idx >= len(records):
            continue
        results.append(
            {
                "id": records[idx]["id"],
                "text": records[idx]["text"],
                "metadata": records[idx].get("metadata", {}),
                "score": float(scores[idx]),
            }
        )

    return with_adapter_metadata(
        {
            "status": "success",
            "index_name": resolved_index_name,
            "query": query,
            "top_k": top_k,
            "results": results,
        },
        operation="search_vector_index",
        backend_available=True,
        implementation_status="implemented",
    )


__all__ = [
    "EmbeddingsRouter",
    "EMBEDDINGS_AVAILABLE",
    "EMBEDDINGS_ERROR",
    "VECTOR_STORE_AVAILABLE",
    "VECTOR_STORE_ERROR",
    "get_embeddings_router",
    "create_vector_store_async",
    "embeddings_backend_status",
    "vector_index_backend_status",
    "create_vector_index",
    "search_vector_index",
]
