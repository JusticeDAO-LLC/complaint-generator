from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ProvenanceRecord:
    source_url: str = ""
    acquisition_method: str = ""
    source_type: str = ""
    acquired_at: str = ""
    content_hash: str = ""
    source_system: str = ""
    jurisdiction: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaseArtifact:
    cid: str
    artifact_type: str
    size: int
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["type"] = payload.pop("artifact_type")
        return payload


@dataclass(frozen=True)
class CaseAuthority:
    authority_type: str
    source: str
    citation: str = ""
    title: str = ""
    content: str = ""
    url: str = ""
    relevance_score: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["type"] = payload.pop("authority_type")
        return payload


__all__ = ["ProvenanceRecord", "CaseArtifact", "CaseAuthority"]