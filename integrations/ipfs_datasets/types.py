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


def normalize_degraded_reason(reason: Any) -> str | None:
    text = str(reason or "").strip()
    return text or None


@dataclass(frozen=True)
class CapabilityStatus:
    status: str
    available: bool
    module_path: str
    degraded_reason: str | None = None
    provider: str = "ipfs_datasets_py"
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["degraded_reason"] = normalize_degraded_reason(payload.get("degraded_reason"))
        payload["details"] = dict(payload.get("details") or {})
        return payload


def with_adapter_metadata(
    payload: Dict[str, Any],
    *,
    operation: str,
    backend_available: bool,
    degraded_reason: Any = None,
    implementation_status: str = "",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_payload = dict(payload)
    existing_metadata = normalized_payload.get("metadata")
    metadata = dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
    existing_details = metadata.get("details")
    details = dict(existing_details) if isinstance(existing_details, dict) else {}

    normalized_payload.setdefault("provider", "ipfs_datasets_py")
    metadata["operation"] = operation
    metadata["backend_available"] = bool(backend_available)
    metadata["provider"] = "ipfs_datasets_py"

    details["operation"] = operation
    details["backend_available"] = bool(backend_available)
    if implementation_status:
        metadata["implementation_status"] = implementation_status
        details["implementation_status"] = implementation_status
    normalized_reason = normalize_degraded_reason(degraded_reason)
    if normalized_reason:
        metadata["degraded_reason"] = normalized_reason
        details["degraded_reason"] = normalized_reason
        normalized_payload.setdefault("degraded_reason", normalized_reason)
    if extra_metadata:
        metadata.update(extra_metadata)
        details.update(extra_metadata)
    metadata["details"] = details
    normalized_payload["metadata"] = metadata
    return normalized_payload


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
class DocumentChunk:
    chunk_id: str
    index: int
    start: int
    end: int
    text: str
    length: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DocumentParseSummary:
    status: str = ""
    chunk_count: int = 0
    text_length: int = 0
    parser_version: str = ""
    input_format: str = ""
    paragraph_count: int = 0
    extraction_method: str = ""
    quality_tier: str = ""
    quality_score: float = 0.0
    page_count: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DocumentTransformLineage:
    source: str = ""
    parser_version: str = ""
    input_format: str = ""
    normalization: str = ""
    chunking: Dict[str, Any] = field(default_factory=dict)
    extraction: Dict[str, Any] = field(default_factory=dict)
    source_span: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DocumentParseResult:
    status: str
    text: str
    chunks: List[DocumentChunk] = field(default_factory=list)
    summary: DocumentParseSummary = field(default_factory=DocumentParseSummary)
    lineage: DocumentTransformLineage = field(default_factory=DocumentTransformLineage)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["chunks"] = [chunk.as_dict() for chunk in self.chunks]
        payload["summary"] = self.summary.as_dict()
        payload["lineage"] = self.lineage.as_dict()
        return payload


@dataclass(frozen=True)
class GraphEntity:
    entity_id: str
    entity_type: str
    name: str = ""
    confidence: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["id"] = payload.pop("entity_id")
        payload["type"] = payload.pop("entity_type")
        return payload


@dataclass(frozen=True)
class GraphRelationship:
    relationship_id: str
    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["id"] = payload.pop("relationship_id")
        return payload


@dataclass(frozen=True)
class GraphPayload:
    status: str
    source_id: str = ""
    entities: List[GraphEntity] = field(default_factory=list)
    relationships: List[GraphRelationship] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "source_id": self.source_id,
            "entities": [entity.as_dict() for entity in self.entities],
            "relationships": [relationship.as_dict() for relationship in self.relationships],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GraphSnapshotResult:
    status: str
    graph_id: str = ""
    persisted: bool = False
    created: bool = False
    reused: bool = False
    node_count: int = 0
    edge_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphSupportMatch:
    fact_id: str = ""
    text: str = ""
    score: float = 0.0
    confidence: float = 0.0
    matched_claim_element: bool = False
    duplicate_count: int = 1
    cluster_size: int = 1
    cluster_texts: List[str] = field(default_factory=list)
    support_kind: str = ""
    source_table: str = ""
    support_kind_set: List[str] = field(default_factory=list)
    source_table_set: List[str] = field(default_factory=list)
    claim_element_id: str = ""
    claim_element_text: str = ""
    support_ref: str = ""
    support_label: str = ""
    evidence_record_id: Optional[int] = None
    authority_record_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.evidence_record_id is None:
            payload.pop("evidence_record_id", None)
        if self.authority_record_id is None:
            payload.pop("authority_record_id", None)
        return payload


@dataclass(frozen=True)
class GraphSupportSummary:
    result_count: int = 0
    total_fact_count: int = 0
    unique_fact_count: int = 0
    duplicate_fact_count: int = 0
    semantic_cluster_count: int = 0
    semantic_duplicate_count: int = 0
    support_by_kind: Dict[str, int] = field(default_factory=dict)
    support_by_source: Dict[str, int] = field(default_factory=dict)
    max_score: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphSupportResult:
    status: str
    claim_element_id: str = ""
    claim_type: str = ""
    claim_element_text: str = ""
    graph_id: str = ""
    results: List[GraphSupportMatch] = field(default_factory=list)
    summary: GraphSupportSummary = field(default_factory=GraphSupportSummary)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [result.as_dict() for result in self.results]
        payload["summary"] = self.summary.as_dict()
        return payload


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
class AuthorityTreatmentRecord:
    authority_id: str
    treatment_type: str
    treatment_id: str = ""
    treated_by_authority_id: str = ""
    treated_by_citation: str = ""
    treatment_source: str = ""
    treatment_confidence: float = 0.0
    treatment_date: str = ""
    treatment_explanation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.treatment_id:
            object.__setattr__(
                self,
                "treatment_id",
                _stable_identifier(
                    "authority_treatment",
                    self.authority_id,
                    self.treatment_type,
                    self.treated_by_authority_id,
                    self.treated_by_citation,
                    self.treatment_source,
                    self.treatment_date,
                ),
            )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleCandidate:
    authority_id: str
    rule_text: str
    rule_type: str
    rule_id: str = ""
    claim_element_id: str = ""
    claim_element_text: str = ""
    predicate_template: str = ""
    jurisdiction: str = ""
    temporal_scope: str = ""
    extraction_confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.rule_id:
            object.__setattr__(
                self,
                "rule_id",
                _stable_identifier(
                    "rule_candidate",
                    self.authority_id,
                    self.rule_type,
                    self.claim_element_id,
                    self.rule_text,
                    self.predicate_template,
                ),
            )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LegalSearchProgram:
    program_type: str
    claim_type: str
    authority_intent: str
    query_text: str
    program_id: str = ""
    claim_element_id: str = ""
    claim_element_text: str = ""
    jurisdiction: str = ""
    forum: str = ""
    time_window_start: str = ""
    time_window_end: str = ""
    authority_families: List[str] = field(default_factory=list)
    search_terms: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.program_id:
            object.__setattr__(
                self,
                "program_id",
                _stable_identifier(
                    "legal_search_program",
                    self.program_type,
                    self.claim_type,
                    self.authority_intent,
                    self.claim_element_id,
                    self.claim_element_text,
                    self.jurisdiction,
                    self.forum,
                    self.query_text,
                ),
            )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
    "CapabilityStatus",
    "normalize_degraded_reason",
    "with_adapter_metadata",
    "ProvenanceRecord",
    "DocumentChunk",
    "DocumentParseSummary",
    "DocumentTransformLineage",
    "DocumentParseResult",
    "GraphEntity",
    "GraphRelationship",
    "GraphPayload",
    "GraphSnapshotResult",
    "GraphSupportMatch",
    "GraphSupportSummary",
    "GraphSupportResult",
    "CaseArtifact",
    "CaseAuthority",
    "AuthorityTreatmentRecord",
    "RuleCandidate",
    "LegalSearchProgram",
    "CaseFact",
    "CaseClaimElement",
    "CaseSupportEdge",
    "FormalPredicate",
    "ValidationRun",
]