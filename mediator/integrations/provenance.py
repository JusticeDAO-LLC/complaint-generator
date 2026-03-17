from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass
class ProvenanceRecord:
    source_type: str
    source_name: str
    query: str
    confidence: float
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


def build_provenance_record(
    source_type: str,
    source_name: str,
    query: str,
    confidence: float,
    metadata: Dict[str, Any] | None = None,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        source_type=source_type,
        source_name=source_name,
        query=query,
        confidence=confidence,
        metadata=metadata or {},
    )
