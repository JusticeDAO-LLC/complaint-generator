"""Long-running complaint jobs through the accelerate agent supervisor.

These operations stay off the HTTP and chat request path. Import success is
recorded separately from the capability probe.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from integrations.ipfs_datasets.loader import ensure_import_paths, import_module_optional


_SUPERVISOR_SYMBOLS = (
    "SupervisorControlService",
    "Operation",
    "OperationRequest",
    "OperationResult",
    "AGENT_SUPERVISOR_PUBLIC_API_EXPORTS",
    "agent_supervisor_cold_discovery",
)


def _load_supervisor_module() -> tuple[Any | None, Any]:
    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    return import_module_optional("ipfs_accelerate_py.agent_supervisor")


def probe_agent_supervisor() -> dict[str, Any]:
    """Discover the supervisor, then probe. Import alone does not enable jobs."""

    module, error = _load_supervisor_module()
    if module is None:
        return {
            "importable": False,
            "probed": False,
            "available": False,
            "error": str(error or "agent_supervisor unavailable"),
            "missing_symbols": list(_SUPERVISOR_SYMBOLS),
        }
    missing = [name for name in _SUPERVISOR_SYMBOLS if not hasattr(module, name)]
    discovery: dict[str, Any] = {}
    probe_error = ""
    if not missing:
        try:
            discovered = module.agent_supervisor_cold_discovery()
            discovery = dict(discovered) if isinstance(discovered, dict) else {}
        except Exception as exc:
            probe_error = str(exc)
    operations = discovery.get("operations") if isinstance(discovery.get("operations"), (list, tuple)) else ()
    probed = bool(discovery) and "capability" in operations and not probe_error
    control_service = getattr(module, "SupervisorControlService", None)
    available = probed and isinstance(control_service, type)
    return {
        "importable": not missing,
        "probed": probed,
        "available": available,
        "error": probe_error or (f"missing symbols: {', '.join(missing)}" if missing else ""),
        "missing_symbols": missing,
        "operations": list(operations),
        "public_api_count": len(tuple(getattr(module, "AGENT_SUPERVISOR_PUBLIC_API_EXPORTS", ()) or ())),
    }


def _degraded(operation: str, reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "operation": operation,
        "off_request_path": True,
        "error": reason,
        "result": {},
        "receipt": {},
    }


def _record(control_service: Any, operation: str, payload: Mapping[str, Any]) -> Any:
    if control_service is None:
        return None
    recorder = getattr(control_service, "execute", None) or getattr(control_service, "submit", None)
    if not callable(recorder):
        return None
    try:
        return recorder({"operation": operation, "payload": dict(payload)})
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _run(
    operation: str,
    payload: Mapping[str, Any] | None,
    worker: Callable[[Mapping[str, Any]], dict[str, Any]],
    *,
    control_service: Any = None,
) -> dict[str, Any]:
    status = probe_agent_supervisor()
    body = dict(payload or {})
    if control_service is None and not status["available"]:
        return _degraded(operation, status["error"] or "agent supervisor probe failed")
    try:
        result = worker(body)
    except Exception as exc:
        return _degraded(operation, str(exc))
    recorded = _record(control_service, operation, result)
    return {
        "status": "available",
        "operation": operation,
        "off_request_path": True,
        "supervisor": status,
        "result": result,
        "receipt": result.get("receipt") or {},
        "control_record": recorded,
        "error": "",
    }


def evidence_acquisition(
    payload: Mapping[str, Any] | None = None,
    *,
    control_service: Any = None,
) -> dict[str, Any]:
    """Search for evidence and store a JSON receipt through the storage adapter."""

    def _work(body: Mapping[str, Any]) -> dict[str, Any]:
        from integrations.ipfs_datasets.search import search_multi_engine_web
        from integrations.ipfs_datasets.storage import store_bytes

        query = str(body.get("query") or "").strip()
        results = search_multi_engine_web(query, max_results=int(body.get("max_results") or 5)) if query else []
        encoded = json.dumps({"query": query, "results": results}, default=str).encode("utf-8")
        stored = store_bytes(encoded, pin_content=True)
        return {
            "query": query,
            "result_count": len(list(results or [])),
            "receipt": {
                "cid": stored.get("cid") or "",
                "backend_name": stored.get("backend_name") or "",
                "status": stored.get("status") or "",
            },
        }

    return _run("evidence_acquisition", payload, _work, control_service=control_service)


def draft_repair(
    payload: Mapping[str, Any] | None = None,
    *,
    control_service: Any = None,
) -> dict[str, Any]:
    """One grounded generation followed by one logic check."""

    def _work(body: Mapping[str, Any]) -> dict[str, Any]:
        from integrations.ipfs_datasets.llm import generate_text_with_metadata
        from integrations.ipfs_datasets.logic import text_to_fol

        prompt = str(body.get("prompt") or body.get("text") or "")
        generated = generate_text_with_metadata(
            prompt,
            provider=body.get("provider"),
            model_name=body.get("model_name"),
        )
        text = str(generated.get("text") or prompt)
        logic = text_to_fol(text)
        return {
            "generation": generated,
            "logic": logic,
            "logic_path": str(((logic.get("metadata") or {}).get("logic_path") or "")),
            "receipt": {"status": generated.get("status") or "", "backend_name": "llm_router"},
        }

    return _run("draft_repair", payload, _work, control_service=control_service)


def graph_refresh(
    payload: Mapping[str, Any] | None = None,
    *,
    control_service: Any = None,
) -> dict[str, Any]:
    """Rebuild a claim-support snapshot through the knowledge-graph client."""

    def _work(body: Mapping[str, Any]) -> dict[str, Any]:
        from integrations.ipfs_datasets.graphs import extract_graph_from_text, persist_graph_snapshot

        text = str(body.get("text") or "")
        source_id = str(body.get("source_id") or "supervisor-graph")
        graph = extract_graph_from_text(text, source_id=source_id)
        persisted = persist_graph_snapshot(graph, graph_id=body.get("graph_id"), graph_changed=True)
        return {
            "graph_id": persisted.get("graph_id") or "",
            "persist_path": str((persisted.get("metadata") or {}).get("graph_persist_path") or ""),
            "receipt": {
                "graph_id": persisted.get("graph_id") or "",
                "backend_name": "knowledge_graphs.Client",
                "status": persisted.get("status") or "",
            },
        }

    return _run("graph_refresh", payload, _work, control_service=control_service)


__all__ = [
    "draft_repair",
    "evidence_acquisition",
    "graph_refresh",
    "probe_agent_supervisor",
]
