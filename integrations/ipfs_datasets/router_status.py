from __future__ import annotations

from typing import Any, Dict, Mapping

from .llm import llm_router_status
from .storage import storage_backend_status
from .vector_store import embeddings_backend_status


def get_router_status_report(
    *,
    llm_config: Mapping[str, Any] | None = None,
    embeddings_config: Mapping[str, Any] | None = None,
    probe_llm: bool = False,
    probe_embeddings: bool = False,
    probe_text: str = "",
) -> Dict[str, Any]:
    resolved_llm_config = dict(llm_config or {})
    resolved_embeddings_config = dict(embeddings_config or {})

    llm_status = llm_router_status(
        perform_probe=probe_llm,
        prompt=probe_text,
        **resolved_llm_config,
    )
    ipfs_status = storage_backend_status()
    embeddings_status = embeddings_backend_status(
        perform_probe=probe_embeddings,
        probe_text=probe_text,
        **resolved_embeddings_config,
    )

    components = {
        "llm_router": llm_status,
        "ipfs_router": ipfs_status,
        "embeddings_router": embeddings_status,
    }
    unavailable = {
        name: str(payload.get("error") or payload.get("metadata", {}).get("degraded_reason") or "unavailable")
        for name, payload in components.items()
        if str(payload.get("status") or "").lower() not in {"available"}
    }

    return {
        "status": "available" if not unavailable else "degraded",
        "components": components,
        "unavailable_components": unavailable,
    }


__all__ = ["get_router_status_report"]
