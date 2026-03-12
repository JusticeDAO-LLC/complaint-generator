from __future__ import annotations

from functools import lru_cache

from .loader import (
    import_failure_message,
    import_failure_type,
    import_module_optional,
)
from .types import CapabilityStatus


@lru_cache(maxsize=1)
def get_ipfs_datasets_capabilities() -> dict[str, CapabilityStatus]:
    module_map = {
        "llm_router": {
            "module_path": "ipfs_datasets_py.llm_router",
            "adapter_module": "integrations.ipfs_datasets.llm",
            "contract_family": "generation",
        },
        "ipfs_storage": {
            "module_path": "ipfs_datasets_py.ipfs_backend_router",
            "adapter_module": "integrations.ipfs_datasets.storage",
            "contract_family": "storage",
        },
        "web_archiving": {
            "module_path": "ipfs_datasets_py.web_archiving",
            "adapter_module": "integrations.ipfs_datasets.search",
            "contract_family": "acquisition",
        },
        "common_crawl": {
            "module_path": "ipfs_datasets_py.processors.web_archiving.common_crawl_integration",
            "adapter_module": "integrations.ipfs_datasets.search",
            "contract_family": "acquisition",
        },
        "documents": {
            "module_path": "ipfs_datasets_py.processors",
            "adapter_module": "integrations.ipfs_datasets.documents",
            "contract_family": "documents",
        },
        "legal_scrapers": {
            "module_path": "ipfs_datasets_py.processors.legal_scrapers",
            "adapter_module": "integrations.ipfs_datasets.legal",
            "contract_family": "legal",
        },
        "knowledge_graphs": {
            "module_path": "ipfs_datasets_py.knowledge_graphs",
            "adapter_module": "integrations.ipfs_datasets.graphs",
            "contract_family": "graphs",
        },
        "graphrag": {
            "module_path": "ipfs_datasets_py.optimizers.graphrag",
            "adapter_module": "integrations.ipfs_datasets.graphrag",
            "contract_family": "validation",
        },
        "logic_tools": {
            "module_path": "ipfs_datasets_py.logic",
            "adapter_module": "integrations.ipfs_datasets.logic",
            "contract_family": "validation",
        },
        "vector_store": {
            "module_path": "ipfs_datasets_py.vector_stores",
            "adapter_module": "integrations.ipfs_datasets.vector_store",
            "contract_family": "retrieval",
        },
        "mcp_gateway": {
            "module_path": "ipfs_datasets_py.mcp_server",
            "adapter_module": "integrations.ipfs_datasets.mcp_gateway",
            "contract_family": "mcp",
        },
    }
    capabilities: dict[str, CapabilityStatus] = {}
    for name, metadata in module_map.items():
        module_path = metadata["module_path"]
        module, error = import_module_optional(module_path)
        degraded_reason = import_failure_message(error)
        capabilities[name] = CapabilityStatus(
            status="available" if module is not None else "degraded",
            available=module is not None,
            module_path=module_path,
            degraded_reason=degraded_reason,
            details={
                "capability": name,
                "error_type": import_failure_type(error),
                "adapter_module": metadata["adapter_module"],
                "contract_family": metadata["contract_family"],
            },
        )
    return capabilities


def summarize_ipfs_datasets_capabilities() -> dict[str, str]:
    summary: dict[str, str] = {}
    for name, status in get_ipfs_datasets_capabilities().items():
        if status.available:
            summary[name] = "available"
        else:
            summary[name] = f"degraded: {status.degraded_reason or 'unavailable'}"
    return summary


def summarize_ipfs_datasets_capability_report() -> dict[str, object]:
    capabilities = get_ipfs_datasets_capabilities()
    available_capabilities = sorted(name for name, status in capabilities.items() if status.available)
    degraded_capabilities = {
        name: status.degraded_reason or "unavailable"
        for name, status in capabilities.items()
        if not status.available
    }
    family_counts: dict[str, int] = {}
    for status in capabilities.values():
        family = str(status.details.get("contract_family") or "")
        if not family:
            continue
        family_counts[family] = family_counts.get(family, 0) + 1
    return {
        "status": "available" if not degraded_capabilities else "degraded",
        "available_count": len(available_capabilities),
        "degraded_count": len(degraded_capabilities),
        "available_capabilities": available_capabilities,
        "degraded_capabilities": degraded_capabilities,
        "family_counts": family_counts,
        "capabilities": {
            name: status.as_dict()
            for name, status in capabilities.items()
        },
    }


def summarize_ipfs_datasets_startup_payload() -> dict[str, object]:
    capabilities = get_ipfs_datasets_capabilities()
    capability_report = summarize_ipfs_datasets_capability_report()
    return {
        "capability_report": capability_report,
        "capabilities": {
            name: status.as_dict()
            for name, status in capabilities.items()
        },
    }