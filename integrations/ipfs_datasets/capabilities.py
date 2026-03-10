from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache

from .loader import ensure_import_paths, import_module_optional


@dataclass(frozen=True)
class CapabilityStatus:
    available: bool
    module_path: str
    degraded_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@lru_cache(maxsize=1)
def get_ipfs_datasets_capabilities() -> dict[str, CapabilityStatus]:
    ensure_import_paths()
    module_map = {
        "llm_router": "ipfs_datasets_py.llm_router",
        "ipfs_storage": "ipfs_datasets_py.ipfs_backend_router",
        "web_archiving": "ipfs_datasets_py.web_archiving",
        "common_crawl": "ipfs_datasets_py.processors.web_archiving.common_crawl_integration",
        "legal_scrapers": "ipfs_datasets_py.processors.legal_scrapers",
        "graphrag": "ipfs_datasets_py.optimizers.graphrag",
        "logic_tools": "ipfs_datasets_py.logic",
    }
    capabilities: dict[str, CapabilityStatus] = {}
    for name, module_path in module_map.items():
        module, error = import_module_optional(module_path)
        capabilities[name] = CapabilityStatus(
            available=module is not None,
            module_path=module_path,
            degraded_reason=error,
        )
    return capabilities