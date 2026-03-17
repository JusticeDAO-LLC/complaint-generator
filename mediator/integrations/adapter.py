import importlib
from typing import Dict, Iterable, List, Optional

from .contracts import CapabilityCatalog, CapabilityStatus, NormalizedRetrievalRecord
from .settings import IntegrationFeatureFlags


def _module_available(module_names: Iterable[str]) -> CapabilityStatus:
    errors: List[str] = []
    for module_name in module_names:
        try:
            importlib.import_module(module_name)
            return CapabilityStatus(name=module_name, available=True)
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
    details = "; ".join(errors[:2]) if errors else "Module not found"
    return CapabilityStatus(name=next(iter(module_names), "unknown"), available=False, details=details)


def detect_ipfs_datasets_capabilities() -> CapabilityCatalog:
    return CapabilityCatalog(
        legal_datasets=_module_available([
            "ipfs_datasets_py.legal_scrapers",
            "ipfs_datasets_py.legal_research",
        ]),
        search_tools=_module_available([
            "ipfs_datasets_py.web_archiving",
            "ipfs_datasets_py.search",
        ]),
        graph_tools=_module_available([
            "ipfs_datasets_py.graphrag",
            "ipfs_datasets_py.graphrag_integration",
        ]),
        vector_tools=_module_available([
            "ipfs_datasets_py.search.search_embeddings",
            "ipfs_datasets_py.embeddings_router",
        ]),
        optimizer_tools=_module_available([
            "ipfs_datasets_py.optimizers",
            "ipfs_datasets_py.graphrag.query_optimizer",
        ]),
        mcp_tools=_module_available([
            "ipfs_datasets_py.mcp_server",
            "ipfs_datasets_py.mcp",
        ]),
    )


class IPFSDatasetsAdapter:
    def __init__(
        self,
        feature_flags: Optional[IntegrationFeatureFlags] = None,
        capabilities: Optional[CapabilityCatalog] = None,
    ):
        self.feature_flags = feature_flags or IntegrationFeatureFlags.from_env()
        self.capabilities = capabilities or detect_ipfs_datasets_capabilities()

    def capability_registry(self) -> Dict[str, Dict[str, object]]:
        enabled = {
            "legal_datasets": self.feature_flags.enhanced_legal,
            "search_tools": self.feature_flags.enhanced_search,
            "graph_tools": self.feature_flags.enhanced_graph,
            "vector_tools": self.feature_flags.enhanced_vector,
            "optimizer_tools": self.feature_flags.enhanced_optimizer,
            "mcp_tools": True,
        }
        registry: Dict[str, Dict[str, object]] = {}
        for name, status in self.capabilities.as_dict().items():
            registry[name] = {
                "available": status["available"],
                "enabled": enabled.get(name, False),
                "active": bool(status["available"] and enabled.get(name, False)),
                "details": status["details"],
            }
        return registry

    @staticmethod
    def normalize_record(query: str, source_type: str, source_name: str, record: Dict[str, object]) -> NormalizedRetrievalRecord:
        title = str(record.get("title", "") or "")
        url = str(record.get("url", "") or "")
        citation = str(record.get("citation", "") or "")
        snippet = str(record.get("description", "") or record.get("snippet", "") or "")
        content = str(record.get("content", "") or "")
        score = float(record.get("score", 0.0) or 0.0)
        confidence = float(record.get("confidence", score) or 0.0)
        input_metadata = record.get("metadata", {})
        base_metadata = input_metadata if isinstance(input_metadata, dict) else {}
        passthrough_metadata = {
            k: v
            for k, v in record.items()
            if k
            not in {
                "title",
                "url",
                "citation",
                "description",
                "snippet",
                "content",
                "score",
                "confidence",
                "metadata",
            }
        }

        merged_metadata = dict(base_metadata)
        merged_metadata.update(passthrough_metadata)

        return NormalizedRetrievalRecord(
            source_type=source_type,
            source_name=source_name,
            query=query,
            title=title,
            url=url,
            citation=citation,
            snippet=snippet,
            content=content,
            score=score,
            confidence=confidence,
            metadata=merged_metadata,
        )
