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

from .loader import import_attr_optional, import_module_optional
from .types import with_adapter_metadata

try:
    import numpy as np
except Exception as exc:  # pragma: no cover - depends on optional install state
    np = None
    _numpy_error = str(exc)
else:
    _numpy_error = None


EmbeddingsRouter, _embeddings_error = import_attr_optional(
    "ipfs_datasets_py.embeddings_router",
    "EmbeddingsRouter",
)
embed_texts_batched, _embed_texts_batched_error = import_attr_optional(
    "ipfs_datasets_py.embeddings_router",
    "embed_texts_batched",
)
_vector_stores_module, _vector_stores_error = import_module_optional(
    "ipfs_datasets_py.vector_stores"
)

EMBEDDINGS_AVAILABLE = embed_texts_batched is not None or EmbeddingsRouter is not None
VECTOR_STORE_AVAILABLE = EMBEDDINGS_AVAILABLE or _vector_stores_module is not None
VECTOR_STORE_ERROR = _embeddings_error or _embed_texts_batched_error or _vector_stores_error or _numpy_error


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
    "VECTOR_STORE_AVAILABLE",
    "VECTOR_STORE_ERROR",
    "get_embeddings_router",
    "create_vector_index",
    "search_vector_index",
]
