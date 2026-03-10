from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _stable_identifier(prefix: str, *parts: str) -> str:
    normalized = "|".join(part.strip() for part in parts if part and part.strip())
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


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
    artifact_id: str = ""
    mime_type: str = ""
    source_type: str = ""
    content_hash: str = ""
    acquisition_method: str = ""
    source_url: str = ""
    parser_version: str = ""
    extraction_version: str = ""
    transform_version: str = ""
    reasoning_version: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.artifact_id:
            object.__setattr__(
                self,
                "artifact_id",
                _stable_identifier("artifact", self.content_hash, self.cid, self.source_url),
            )

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
    authority_id: str = ""
    jurisdiction: str = ""
    source_system: str = ""
    claim_element_id: str = ""
    claim_element: str = ""
    parser_version: str = ""
    extraction_version: str = ""
    reasoning_version: str = ""
    relevance_score: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.authority_id:
            object.__setattr__(
                self,
                "authority_id",
                _stable_identifier(
                    "authority",
                    self.citation,
                    self.url,
                    self.title,
                    self.source,
                    self.authority_type,
                ),
            )

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["type"] = payload.pop("authority_type")
        return payload


@dataclass(frozen=True)
class CaseFact:
    fact_id: str
    text: str
    source_artifact_id: str = ""
    source_authority_id: str = ""
    confidence: float = 0.0
    temporal_scope: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaseClaimElement:
    claim_type: str
    element_text: str
    element_id: str = ""
    required_proof_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.element_id:
            object.__setattr__(
                self,
                "element_id",
                _stable_identifier("claim_element", self.claim_type, self.element_text),
            )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaseSupportEdge:
    source_node: str
    target_node: str
    relation_type: str
    edge_id: str = ""
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.edge_id:
            object.__setattr__(
                self,
                "edge_id",
                _stable_identifier("support_edge", self.source_node, self.target_node, self.relation_type),
            )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FormalPredicate:
    predicate_text: str
    predicate_id: str = ""
    grounded_fact_ids: List[str] = field(default_factory=list)
    authority_ids: List[str] = field(default_factory=list)
    predicate_type: str = ""
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.predicate_id:
            object.__setattr__(self, "predicate_id", _stable_identifier("predicate", self.predicate_text))

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationRun:
    run_id: str
    validator_name: str
    status: str
    supported_ids: List[str] = field(default_factory=list)
    unsupported_ids: List[str] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


__all__ = [
    "ProvenanceRecord",
    "CaseArtifact",
    "CaseAuthority",
    "CaseFact",
    "CaseClaimElement",
    "CaseSupportEdge",
    "FormalPredicate",
    "ValidationRun",
]