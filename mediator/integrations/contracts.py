from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CapabilityStatus:
    name: str
    available: bool
    details: Optional[str] = None


@dataclass
class CapabilityCatalog:
    legal_datasets: CapabilityStatus
    search_tools: CapabilityStatus
    graph_tools: CapabilityStatus
    vector_tools: CapabilityStatus
    optimizer_tools: CapabilityStatus
    mcp_tools: CapabilityStatus

    def as_dict(self) -> Dict[str, Dict[str, Any]]:
        return {
            "legal_datasets": {
                "available": self.legal_datasets.available,
                "details": self.legal_datasets.details,
            },
            "search_tools": {
                "available": self.search_tools.available,
                "details": self.search_tools.details,
            },
            "graph_tools": {
                "available": self.graph_tools.available,
                "details": self.graph_tools.details,
            },
            "vector_tools": {
                "available": self.vector_tools.available,
                "details": self.vector_tools.details,
            },
            "optimizer_tools": {
                "available": self.optimizer_tools.available,
                "details": self.optimizer_tools.details,
            },
            "mcp_tools": {
                "available": self.mcp_tools.available,
                "details": self.mcp_tools.details,
            },
        }


@dataclass
class NormalizedRetrievalRecord:
    source_type: str
    source_name: str
    query: str
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    title: str = ""
    url: str = ""
    citation: str = ""
    snippet: str = ""
    content: str = ""
    score: float = 0.0
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> str:
        candidate = self.url or self.citation or self.title
        return candidate.strip().lower()


@dataclass
class NormalizedRetrievalBundle:
    records: List[NormalizedRetrievalRecord] = field(default_factory=list)
    query: str = ""
    provider: str = ""

    def top_k(self, k: int) -> List[NormalizedRetrievalRecord]:
        ranked = sorted(self.records, key=lambda r: (r.score, r.confidence), reverse=True)
        return ranked[:k]
