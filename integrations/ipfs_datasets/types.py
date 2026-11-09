from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


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


USER_ASSERTION_CONTRACT_VERSION = "user_assertion.v1"
DEFAULT_USER_ASSERTION_EXTRACTOR_VERSION = "knowledge_graph_builder.user_assertion.v1"
USER_ASSERTION_RECORD_TYPE = "user_assertion"
USER_SOURCE_KINDS = frozenset({"user_statement", "user_uploaded_document"})
NON_USER_RECORD_TYPES = frozenset({"model_suggestion", "inferred_claim_label", "legal_text"})
ASSERTED_USER_STATUS = "asserted"
UNVERIFIED_ASSERTION_STATUS = "unverified"
SUGGESTION_ASSERTION_STATUS = "suggestion"
LEGAL_TEXT_ASSERTION_STATUS = "legal_text"


def _clean_supplied_text(value: Any) -> str:
    """Return a caller-supplied string without inventing a placeholder."""
    if value is None:
        return ""
    return str(value).strip()


def source_byte_hash(source_text: str) -> str:
    """Hash the exact UTF-8 bytes of a user source."""
    if not isinstance(source_text, str):
        return ""
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _user_assertion_stable_id(**fields: Any) -> str:
    """Bind complete source coordinates without delimiter or prefix collisions."""
    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "assertion:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceSpanLookup:
    """Result of an exact byte-span lookup. Ambiguous matches stay unresolved."""

    start: Optional[int] = None
    end: Optional[int] = None
    text: str = ""
    deficiency: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "deficiency": self.deficiency,
        }


def locate_unique_byte_span(source_text: str, needle: str) -> SourceSpanLookup:
    """Find one exact UTF-8 occurrence of needle. Repeated matches are ambiguous."""
    if not isinstance(source_text, str) or not isinstance(needle, str) or needle == "":
        return SourceSpanLookup(deficiency="missing_source_span")
    source_bytes = source_text.encode("utf-8")
    needle_bytes = needle.encode("utf-8")
    start = source_bytes.find(needle_bytes)
    if start < 0:
        return SourceSpanLookup(deficiency="missing_source_span")
    if source_bytes.find(needle_bytes, start + 1) != -1:
        return SourceSpanLookup(deficiency="ambiguous_source_span")
    return SourceSpanLookup(start=start, end=start + len(needle_bytes), text=needle)


_CHAR_SPAN_UNITS = frozenset({"char", "chars", "character", "characters"})


def resolve_source_span(source_text: str, source_span: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Bind a span to one UTF-8 generation. Offsets from another generation are not applied.

    Character offsets convert only when the span names this source generation.
    A mismatched generation or an unbound character span stays deficient and
    does not borrow bytes from the current text.
    """
    if not isinstance(source_span, Mapping) or not source_span:
        return {"start": None, "end": None, "text": "", "deficiencies": ["missing_source_span"]}
    actual = source_byte_hash(source_text) if isinstance(source_text, str) and source_text != "" else ""
    claimed = _clean_supplied_text(source_span.get("source_generation"))
    if claimed and claimed != actual:
        return {"start": None, "end": None, "text": "", "deficiencies": ["source_generation_mismatch"]}
    unit = _clean_supplied_text(source_span.get("unit")).lower() or "byte"
    start = source_span.get("start")
    end = source_span.get("end")
    if unit in _CHAR_SPAN_UNITS:
        if not claimed or claimed != actual or not isinstance(source_text, str):
            return {"start": None, "end": None, "text": "", "deficiencies": ["source_span_unit_not_byte"]}
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
            return {"start": None, "end": None, "text": "", "deficiencies": ["source_span_not_integers"]}
        if start < 0 or end <= start or end > len(source_text):
            return {"start": None, "end": None, "text": "", "deficiencies": ["source_span_out_of_bounds"]}
        start = len(source_text[:start].encode("utf-8"))
        end = len(source_text[:end].encode("utf-8"))
    sliced, span_deficiency = _slice_source_bytes(source_text, start, end)
    if span_deficiency:
        return {"start": None, "end": None, "text": "", "deficiencies": [span_deficiency]}
    deficiencies: List[str] = []
    supplied = source_span.get("text")
    if supplied is not None and str(supplied) != sliced:
        deficiencies.append("source_span_mismatch")
    return {"start": start, "end": end, "text": sliced, "deficiencies": deficiencies}


def _slice_source_bytes(source_text: str, start: Any, end: Any) -> tuple[str, str]:
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        return "", "source_span_not_integers"
    if start < 0 or end <= start:
        return "", "source_span_out_of_bounds"
    if not isinstance(source_text, str):
        return "", "missing_source_span"
    source_bytes = source_text.encode("utf-8")
    if end > len(source_bytes):
        return "", "source_span_out_of_bounds"
    try:
        sliced = source_bytes[start:end].decode("utf-8")
    except UnicodeDecodeError:
        return "", "source_span_mismatch"
    return sliced, ""


@dataclass(frozen=True)
class UserAssertionEnvelope:
    """Versioned provenance for one factual record.

    User-asserted facts require an explicit user source kind, message or
    document identity, an exact source-byte span, the source-byte hash, an
    assertion status, an extractor version, and a stable id. Model suggestions,
    inferred claim labels, and legal text keep separate record types and cannot
    satisfy that gate. Name, date, actor, and jurisdiction stay empty unless
    the caller supplied them.
    """

    contract_version: str = USER_ASSERTION_CONTRACT_VERSION
    record_type: str = ""
    source_kind: str = ""
    requested_source_kind: str = ""
    source_id: str = ""
    message_id: str = ""
    document_id: str = ""
    source_span_start: Optional[int] = None
    source_span_end: Optional[int] = None
    source_span_text: str = ""
    source_hash: str = ""
    # Private original source permits independent hash/span checks on replay.
    # This requires private storage; encryption/retention integration is pending.
    source_text: str = ""
    assertion_status: str = ""
    extractor_version: str = ""
    stable_id: str = ""
    jurisdiction: str = ""
    actor: str = ""
    name: str = ""
    event_date: str = ""
    answer_id: str = ""
    source_generation: str = ""
    factual_record_class: str = ""
    confidence: Optional[float] = None
    legal_hit: bool = False
    role: str = ""
    subject_key: str = ""
    graph_source_id: str = ""
    graph_target_id: str = ""
    deficiencies: Tuple[str, ...] = ()

    @property
    def source_identity(self) -> str:
        kind = self.source_kind if self.source_kind in USER_SOURCE_KINDS else self.requested_source_kind
        if kind == "user_uploaded_document":
            return self.document_id or self.source_id
        if kind == "user_statement":
            return self.message_id or self.source_id
        return self.message_id or self.document_id or self.source_id

    def computed_stable_id(self) -> str:
        endpoint_binding = {}
        if self.graph_source_id or self.graph_target_id:
            endpoint_binding = {"graph_source_id": self.graph_source_id,
                                "graph_target_id": self.graph_target_id}
        return _user_assertion_stable_id(
            contract_version=self.contract_version, record_type=self.record_type, source_kind=self.source_kind,
            requested_source_kind=self.requested_source_kind,
            assertion_status=self.assertion_status, source_id=self.source_id, message_id=self.message_id,
            document_id=self.document_id, start=self.source_span_start, end=self.source_span_end,
            source_hash=self.source_hash, extractor_version=self.extractor_version,
            role=self.role, subject_key=self.subject_key, jurisdiction=self.jurisdiction,
            actor=self.actor, name=self.name, event_date=self.event_date,
            **endpoint_binding,
            **({"answer_id": self.answer_id} if self.answer_id else {}),
            **({"source_generation": self.source_generation} if self.source_generation else {}),
            **({"factual_record_class": self.factual_record_class} if self.factual_record_class else {}),
        )

    @property
    def is_asserted_user_fact(self) -> bool:
        coordinates_valid = (
            isinstance(self.source_text, str)
            and self.source_text != ""
            and self.source_hash == source_byte_hash(self.source_text)
            and _slice_source_bytes(self.source_text, self.source_span_start, self.source_span_end)
                == (self.source_span_text, "")
        )
        return (
            self.contract_version == USER_ASSERTION_CONTRACT_VERSION
            and self.record_type == USER_ASSERTION_RECORD_TYPE
            and self.source_kind in USER_SOURCE_KINDS
            and self.requested_source_kind == self.source_kind
            and self.assertion_status == ASSERTED_USER_STATUS
            and bool(self.source_identity)
            and isinstance(self.source_span_start, int)
            and not isinstance(self.source_span_start, bool)
            and isinstance(self.source_span_end, int)
            and not isinstance(self.source_span_end, bool)
            and self.source_span_start >= 0
            and self.source_span_end > self.source_span_start
            and bool(self.source_span_text)
            and bool(self.source_hash)
            and bool(self.extractor_version)
            and bool(self.stable_id)
            and coordinates_valid
            and self.stable_id == self.computed_stable_id()
            and (not self.source_generation or self.source_generation == self.source_hash)
            and self.factual_record_class not in {"extraction_hypothesis", "legal_text"}
            and not self.deficiencies
        )

    @property
    def source_byte_length(self) -> int:
        if not isinstance(self.source_text, str) or self.source_text == "":
            return 0
        return len(self.source_text.encode("utf-8"))

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["deficiencies"] = list(self.deficiencies)
        payload["source_identity"] = self.source_identity
        payload["source_span"] = {
            "start": self.source_span_start,
            "end": self.source_span_end,
            "text": self.source_span_text,
            "unit": "byte",
        }
        payload["is_asserted_user_fact"] = self.is_asserted_user_fact
        payload["source_byte_length"] = self.source_byte_length
        return payload


def user_assertion_from_mapping(payload: Optional[Mapping[str, Any]]) -> UserAssertionEnvelope:
    """Rebuild an envelope from its serialized mapping without filling gaps."""
    data = dict(payload or {})
    span = data.get("source_span") if isinstance(data.get("source_span"), Mapping) else {}
    start = data.get("source_span_start", span.get("start"))
    end = data.get("source_span_end", span.get("end"))
    span_text = data.get("source_span_text", span.get("text", ""))
    raw_deficiencies = data.get("deficiencies") or ()
    if isinstance(raw_deficiencies, str):
        deficiency_values: Sequence[Any] = (raw_deficiencies,)
    elif isinstance(raw_deficiencies, Sequence):
        deficiency_values = raw_deficiencies
    else:
        deficiency_values = ()
    confidence = data.get("confidence")
    parsed_confidence: Optional[float]
    if confidence is None or confidence == "":
        parsed_confidence = None
    else:
        parsed_confidence = float(confidence)
    envelope = UserAssertionEnvelope(
        contract_version=_clean_supplied_text(data.get("contract_version")),
        record_type=_clean_supplied_text(data.get("record_type")),
        source_kind=_clean_supplied_text(data.get("source_kind")),
        requested_source_kind=_clean_supplied_text(data.get("requested_source_kind")),
        source_id=_clean_supplied_text(data.get("source_id")),
        message_id=_clean_supplied_text(data.get("message_id")),
        document_id=_clean_supplied_text(data.get("document_id")),
        source_span_start=start if isinstance(start, int) and not isinstance(start, bool) else None,
        source_span_end=end if isinstance(end, int) and not isinstance(end, bool) else None,
        source_span_text="" if span_text is None else str(span_text),
        source_hash=_clean_supplied_text(data.get("source_hash")),
        source_text=data.get("source_text") if isinstance(data.get("source_text"), str) else "",
        assertion_status=_clean_supplied_text(data.get("assertion_status")),
        extractor_version=_clean_supplied_text(data.get("extractor_version")),
        stable_id=_clean_supplied_text(data.get("stable_id")),
        jurisdiction=_clean_supplied_text(data.get("jurisdiction")),
        actor=_clean_supplied_text(data.get("actor")),
        name=_clean_supplied_text(data.get("name")),
        event_date=_clean_supplied_text(data.get("event_date")),
        answer_id=_clean_supplied_text(data.get("answer_id")),
        source_generation=_clean_supplied_text(data.get("source_generation")),
        factual_record_class=_clean_supplied_text(data.get("factual_record_class")),
        confidence=parsed_confidence,
        legal_hit=bool(data.get("legal_hit", False)),
        role=_clean_supplied_text(data.get("role")),
        subject_key=_clean_supplied_text(data.get("subject_key")),
        graph_source_id=_clean_supplied_text(data.get("graph_source_id")),
        graph_target_id=_clean_supplied_text(data.get("graph_target_id")),
        deficiencies=tuple(str(item) for item in deficiency_values if str(item).strip()),
    )
    if envelope.assertion_status == ASSERTED_USER_STATUS and not envelope.is_asserted_user_fact:
        envelope = replace(envelope, record_type="unverified_candidate", source_kind="unverified",
            assertion_status=UNVERIFIED_ASSERTION_STATUS,
            deficiencies=tuple(sorted(set(envelope.deficiencies) | {"serialized_source_proof_invalid"})))
    return envelope


def build_user_assertion_envelope(
    *,
    source_text: str,
    source_kind: str = "",
    source_id: str = "",
    message_id: str = "",
    document_id: str = "",
    assertion_status: str = "",
    extractor_version: str = "",
    source_hash: str = "",
    source_span: Optional[Mapping[str, Any]] = None,
    record_type: str = "",
    origin: str = "",
    role: str = "",
    subject_key: str = "",
    graph_source_id: str = "",
    graph_target_id: str = "",
    confidence: Optional[float] = None,
    legal_hit: bool = False,
    jurisdiction: str = "",
    actor: str = "",
    name: str = "",
    event_date: str = "",
    answer_id: str = "",
    factual_record_class: str = "",
    extra_deficiencies: Sequence[str] = (),
) -> UserAssertionEnvelope:
    """Validate one record against the user-assertion contract.

    Confidence and a legal hit never promote a record to an asserted user fact.
    Missing or conflicting source context stays unverified or a non-user type.
    """
    deficiencies = {item for item in extra_deficiencies if _clean_supplied_text(item)}
    requested_kind = _clean_supplied_text(source_kind)
    requested_status = _clean_supplied_text(assertion_status).lower()
    origin_norm = _clean_supplied_text(origin).lower()
    explicit_record_type = _clean_supplied_text(record_type)
    forced_record_type = ""
    class_norm = _clean_supplied_text(factual_record_class)
    if class_norm == "legal_text" and not forced_record_type:
        forced_record_type = "legal_text"
    elif class_norm == "extraction_hypothesis" and not forced_record_type:
        forced_record_type = "model_suggestion"
    if explicit_record_type in NON_USER_RECORD_TYPES:
        forced_record_type = explicit_record_type
    elif origin_norm in {"model", "llm"}:
        forced_record_type = "model_suggestion"
    if forced_record_type:
        deficiencies.add(forced_record_type)

    resolved = resolve_source_span(source_text if isinstance(source_text, str) else "", source_span)
    for item in resolved["deficiencies"]:
        deficiencies.add(item)
    span_start = resolved["start"]
    span_end = resolved["end"]
    sliced_text = resolved["text"]

    computed_hash = source_byte_hash(source_text) if isinstance(source_text, str) and source_text != "" else ""
    supplied_hash = _clean_supplied_text(source_hash)
    if not computed_hash:
        deficiencies.add("missing_source_hash")
    elif supplied_hash and supplied_hash != computed_hash:
        deficiencies.add("source_hash_mismatch")
    effective_hash = computed_hash

    identity_source_id = _clean_supplied_text(source_id)
    identity_message_id = _clean_supplied_text(message_id)
    identity_document_id = _clean_supplied_text(document_id)
    if not (identity_message_id or identity_document_id or identity_source_id):
        deficiencies.add("missing_source_identity")
    primary_identity = identity_document_id if requested_kind == "user_uploaded_document" else identity_message_id
    if requested_kind in USER_SOURCE_KINDS and not (primary_identity or identity_source_id):
        deficiencies.add("missing_typed_source_identity")
    if primary_identity and identity_source_id and primary_identity != identity_source_id:
        deficiencies.add("conflicting_source_identity")
    if not requested_kind:
        deficiencies.add("missing_user_source_kind")
    elif requested_kind not in USER_SOURCE_KINDS:
        deficiencies.add("invalid_user_source_kind")
    if requested_status == "":
        deficiencies.add("missing_assertion_status")
    elif requested_status != ASSERTED_USER_STATUS:
        deficiencies.add("assertion_status_not_user_asserted")

    effective_extractor = _clean_supplied_text(extractor_version) or DEFAULT_USER_ASSERTION_EXTRACTOR_VERSION
    supplied_jurisdiction = _clean_supplied_text(jurisdiction)
    supplied_actor = _clean_supplied_text(actor)
    supplied_name = _clean_supplied_text(name)
    supplied_event_date = _clean_supplied_text(event_date)
    stored_confidence = None if confidence is None else float(confidence)

    blocking = set(deficiencies)
    can_assert = (
        not blocking
        and not forced_record_type
        and requested_kind in USER_SOURCE_KINDS
        and requested_status == ASSERTED_USER_STATUS
        and bool(identity_message_id or identity_document_id or identity_source_id)
        and isinstance(span_start, int)
        and isinstance(span_end, int)
        and bool(sliced_text)
        and bool(effective_hash)
        and bool(effective_extractor)
    )
    if can_assert:
        final_record_type = USER_ASSERTION_RECORD_TYPE
        final_kind = requested_kind
        final_status = ASSERTED_USER_STATUS
        final_deficiencies: Tuple[str, ...] = ()
    else:
        if forced_record_type == "legal_text":
            final_record_type = "legal_text"
            final_kind = "legal_text"
            final_status = LEGAL_TEXT_ASSERTION_STATUS
        elif forced_record_type == "inferred_claim_label":
            final_record_type = "inferred_claim_label"
            final_kind = "inferred_claim_label"
            final_status = SUGGESTION_ASSERTION_STATUS
        elif forced_record_type == "model_suggestion":
            final_record_type = "model_suggestion"
            final_kind = "model_suggestion"
            final_status = SUGGESTION_ASSERTION_STATUS
        else:
            final_record_type = "unverified_candidate"
            final_kind = "unverified"
            final_status = (
                SUGGESTION_ASSERTION_STATUS
                if requested_status == SUGGESTION_ASSERTION_STATUS
                else UNVERIFIED_ASSERTION_STATUS
            )
        final_deficiencies = tuple(sorted(deficiencies))

    envelope = UserAssertionEnvelope(
        contract_version=USER_ASSERTION_CONTRACT_VERSION,
        record_type=final_record_type,
        source_kind=final_kind,
        requested_source_kind=requested_kind,
        source_id=identity_source_id,
        message_id=identity_message_id,
        document_id=identity_document_id,
        source_span_start=span_start if isinstance(span_start, int) and not isinstance(span_start, bool) else None,
        source_span_end=span_end if isinstance(span_end, int) and not isinstance(span_end, bool) else None,
        source_span_text=sliced_text,
        source_hash=effective_hash,
        source_text=source_text if isinstance(source_text, str) else "",
        assertion_status=final_status,
        extractor_version=effective_extractor,
        jurisdiction=supplied_jurisdiction,
        actor=supplied_actor,
        name=supplied_name,
        event_date=supplied_event_date,
        answer_id=_clean_supplied_text(answer_id),
        source_generation=effective_hash,
        factual_record_class=class_norm,
        confidence=stored_confidence,
        legal_hit=bool(legal_hit),
        role=_clean_supplied_text(role),
        subject_key=_clean_supplied_text(subject_key),
        graph_source_id=_clean_supplied_text(graph_source_id),
        graph_target_id=_clean_supplied_text(graph_target_id),
        deficiencies=final_deficiencies,
    )
    return replace(envelope, stable_id=envelope.computed_stable_id())


@dataclass(frozen=True)
class ProvenanceRecord:
    source_url: str = ""
    acquisition_method: str = ""
    source_type: str = ""
    acquired_at: str = ""
    content_hash: str = ""
    source_system: str = ""
    jurisdiction: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    assertion: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        payload["assertion"] = dict(self.assertion)
        return payload

    def assertion_envelope(self) -> UserAssertionEnvelope:
        return user_assertion_from_mapping(self.assertion)


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
    provenance: Dict[str, Any] = field(default_factory=dict)
    assertion: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["id"] = payload.pop("entity_id")
        payload["type"] = payload.pop("entity_type")
        payload["attributes"] = dict(self.attributes)
        payload["provenance"] = dict(self.provenance)
        payload["assertion"] = dict(self.assertion)
        return payload


def graph_entity_from_payload(payload: Mapping[str, Any]) -> GraphEntity:
    """Rebuild a graph node. Endpoint identity stays the node id, not a message id."""
    data = dict(payload or {})
    provenance = dict(data.get("provenance") or {}) if isinstance(data.get("provenance"), Mapping) else {}
    assertion = data.get("assertion") if isinstance(data.get("assertion"), Mapping) else {}
    if not assertion:
        nested = provenance.get("user_assertion")
        assertion = dict(nested) if isinstance(nested, Mapping) else {}
    attributes = dict(data.get("attributes") or {}) if isinstance(data.get("attributes"), Mapping) else {}
    confidence = data.get("confidence", 0.0)
    return GraphEntity(
        entity_id=str(data.get("entity_id") or data.get("id") or ""),
        entity_type=str(data.get("entity_type") or data.get("type") or ""),
        name=str(data.get("name") or ""),
        confidence=float(0.0 if confidence is None else confidence),
        attributes=attributes,
        provenance=provenance,
        assertion=dict(assertion),
    )


@dataclass(frozen=True)
class GraphRelationship:
    relationship_id: str
    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    assertion: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["id"] = payload.pop("relationship_id")
        payload["attributes"] = dict(self.attributes)
        payload["provenance"] = dict(self.provenance)
        payload["assertion"] = dict(self.assertion)
        return payload


def graph_relationship_from_payload(payload: Mapping[str, Any]) -> GraphRelationship:
    """Rebuild an edge. source_id and target_id remain graph node endpoints."""
    data = dict(payload or {})
    provenance = dict(data.get("provenance") or {}) if isinstance(data.get("provenance"), Mapping) else {}
    assertion = data.get("assertion") if isinstance(data.get("assertion"), Mapping) else {}
    if not assertion:
        nested = provenance.get("user_assertion")
        assertion = dict(nested) if isinstance(nested, Mapping) else {}
    attributes = dict(data.get("attributes") or {}) if isinstance(data.get("attributes"), Mapping) else {}
    confidence = data.get("confidence", 0.0)
    return GraphRelationship(
        relationship_id=str(data.get("relationship_id") or data.get("id") or ""),
        source_id=str(data.get("source_id") or ""),
        target_id=str(data.get("target_id") or ""),
        relation_type=str(data.get("relation_type") or data.get("type") or ""),
        confidence=float(0.0 if confidence is None else confidence),
        attributes=attributes,
        provenance=provenance,
        assertion=dict(assertion),
    )


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
    source_family: str = ""
    source_record_id: Optional[int] = None
    source_ref: str = ""
    record_scope: str = ""
    artifact_family: str = ""
    corpus_family: str = ""
    content_origin: str = ""
    parse_source: str = ""
    input_format: str = ""
    quality_tier: str = ""
    quality_score: float = 0.0
    evidence_record_id: Optional[int] = None
    authority_record_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.source_record_id is None:
            payload.pop("source_record_id", None)
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
    unique_source_ref_count: int = 0
    unique_source_record_count: int = 0
    passage_anchored_count: int = 0
    support_by_kind: Dict[str, int] = field(default_factory=dict)
    support_by_source: Dict[str, int] = field(default_factory=dict)
    source_family_counts: Dict[str, int] = field(default_factory=dict)
    record_scope_counts: Dict[str, int] = field(default_factory=dict)
    artifact_family_counts: Dict[str, int] = field(default_factory=dict)
    corpus_family_counts: Dict[str, int] = field(default_factory=dict)
    content_origin_counts: Dict[str, int] = field(default_factory=dict)
    parse_source_counts: Dict[str, int] = field(default_factory=dict)
    input_format_counts: Dict[str, int] = field(default_factory=dict)
    quality_tier_counts: Dict[str, int] = field(default_factory=dict)
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
class AuthorityTreatmentEdge:
    target_authority_id: str
    relation_type: str
    edge_id: str = ""
    source_authority_id: str = ""
    source_citation: str = ""
    target_citation: str = ""
    confidence: float = 0.0
    treatment_source: str = ""
    treatment_date: str = ""
    explanation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        if not self.edge_id:
            object.__setattr__(
                self,
                "edge_id",
                _stable_identifier(
                    "authority_treatment_edge",
                    self.source_authority_id,
                    self.source_citation,
                    self.target_authority_id,
                    self.target_citation,
                    self.relation_type,
                    self.treatment_source,
                    self.treatment_date,
                ),
            )

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["treatment_id"] = self.edge_id
        payload["treatment_type"] = self.relation_type
        payload["treated_by_authority_id"] = self.source_authority_id
        payload["treated_authority_id"] = self.target_authority_id
        payload["treated_by_citation"] = self.source_citation
        payload["treatment_confidence"] = self.confidence
        payload["treatment_explanation"] = self.explanation
        return payload


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
    source_family: str = ""
    source_record_id: Optional[int] = None
    source_ref: str = ""
    record_scope: str = ""
    artifact_family: str = ""
    corpus_family: str = ""
    content_origin: str = ""
    parse_source: str = ""
    input_format: str = ""
    quality_tier: str = ""
    quality_score: float = 0.0
    page_count: int = 0
    confidence: float = 0.0
    temporal_scope: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)

    def __post_init__(self) -> None:
        parse_lineage = self.metadata.get("parse_lineage") if isinstance(self.metadata.get("parse_lineage"), dict) else {}
        transform_lineage = parse_lineage.get("transform_lineage") if isinstance(parse_lineage.get("transform_lineage"), dict) else {}
        parse_quality = parse_lineage.get("parse_quality") if isinstance(parse_lineage.get("parse_quality"), dict) else {}
        source_span = parse_lineage.get("source_span") if isinstance(parse_lineage.get("source_span"), dict) else {}
        provenance_metadata = self.provenance.metadata if isinstance(self.provenance.metadata, dict) else {}

        if not self.source_family:
            inferred_source_family = "legal_authority" if self.source_authority_id else "evidence" if self.source_artifact_id else ""
            if inferred_source_family:
                object.__setattr__(self, "source_family", inferred_source_family)

        if not self.source_ref:
            source_ref = self.source_artifact_id or self.source_authority_id or str(parse_lineage.get("source_ref") or "")
            if source_ref:
                object.__setattr__(self, "source_ref", source_ref)

        if not self.record_scope:
            record_scope = str(parse_lineage.get("record_scope") or self.source_family or "")
            if record_scope:
                object.__setattr__(self, "record_scope", record_scope)

        content_origin = self.content_origin or str(
            transform_lineage.get("content_origin")
            or parse_lineage.get("content_origin")
            or provenance_metadata.get("content_origin")
            or ""
        )
        if content_origin and not self.content_origin:
            object.__setattr__(self, "content_origin", content_origin)

        artifact_family = self.artifact_family or str(
            transform_lineage.get("artifact_family")
            or parse_lineage.get("artifact_family")
            or provenance_metadata.get("artifact_family")
            or {
                "historical_archive_capture": "archived_web_page",
                "live_web_capture": "live_web_page",
                "authority_full_text": "legal_authority_text",
                "authority_reference_fallback": "legal_authority_reference",
            }.get(content_origin, "")
        )
        if artifact_family and not self.artifact_family:
            object.__setattr__(self, "artifact_family", artifact_family)

        corpus_family = self.corpus_family or str(
            transform_lineage.get("corpus_family")
            or parse_lineage.get("corpus_family")
            or provenance_metadata.get("corpus_family")
            or {
                "archived_web_page": "web_page",
                "live_web_page": "web_page",
                "legal_authority_text": "legal_authority",
                "legal_authority_reference": "legal_authority",
            }.get(artifact_family, "")
        )
        if corpus_family and not self.corpus_family:
            object.__setattr__(self, "corpus_family", corpus_family)

        if not self.parse_source:
            parse_source = str(parse_lineage.get("source") or "")
            if parse_source:
                object.__setattr__(self, "parse_source", parse_source)
        if not self.input_format:
            input_format = str(parse_lineage.get("input_format") or "")
            if input_format:
                object.__setattr__(self, "input_format", input_format)
        if not self.quality_tier:
            quality_tier = str(parse_lineage.get("quality_tier") or parse_quality.get("quality_tier") or "")
            if quality_tier:
                object.__setattr__(self, "quality_tier", quality_tier)
        if not self.quality_score:
            quality_score = float(parse_lineage.get("quality_score") or parse_quality.get("quality_score") or 0.0)
            if quality_score:
                object.__setattr__(self, "quality_score", quality_score)
        if not self.page_count:
            page_count = int(parse_lineage.get("page_count") or source_span.get("page_count") or 0)
            if page_count:
                object.__setattr__(self, "page_count", page_count)

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
    "USER_ASSERTION_CONTRACT_VERSION",
    "DEFAULT_USER_ASSERTION_EXTRACTOR_VERSION",
    "USER_ASSERTION_RECORD_TYPE",
    "USER_SOURCE_KINDS",
    "NON_USER_RECORD_TYPES",
    "ASSERTED_USER_STATUS",
    "UNVERIFIED_ASSERTION_STATUS",
    "SUGGESTION_ASSERTION_STATUS",
    "LEGAL_TEXT_ASSERTION_STATUS",
    "SourceSpanLookup",
    "UserAssertionEnvelope",
    "source_byte_hash",
    "locate_unique_byte_span",
    "resolve_source_span",
    "build_user_assertion_envelope",
    "user_assertion_from_mapping",
    "graph_entity_from_payload",
    "graph_relationship_from_payload",
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
    "AuthorityTreatmentEdge",
    "RuleCandidate",
    "LegalSearchProgram",
    "CaseFact",
    "CaseClaimElement",
    "CaseSupportEdge",
    "FormalPredicate",
    "ValidationRun",
]
