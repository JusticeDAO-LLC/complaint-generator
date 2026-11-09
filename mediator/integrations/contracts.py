import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence


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


# Cross-hook handoff only. User-assertion envelopes, the dependency graph,
# and interview stop behavior stay on their existing contracts.
GROUNDING_ROLE_CONTRACT_VERSION = "mediator.grounding.role_handoff.v1"
PRESERVED_ASSERTION_CONTRACT_REF = "user_assertion.v1"
PRESERVED_DEPENDENCY_CONTRACT_REF = "complaint_phases.dependency_graph.v1.0"
PRESERVED_STOP_CONTRACT_REF = "mediator.inquiries.unresolved_target.v1"

ROLE_USER_ASSERTION = "user_assertion"
ROLE_EXTRACTED_CANDIDATE = "extracted_candidate"
ROLE_RETRIEVED_PUBLIC_LAW = "retrieved_public_law"
ROLE_APPLICABLE_REQUIREMENT = "applicable_requirement"
ROLE_CORROBORATING_EVIDENCE = "corroborating_evidence"
ROLE_CONDITIONAL_IR = "conditional_ir"
ROLE_PROOF_RESULT = "proof_result"
GROUNDING_ROLES = (
    ROLE_USER_ASSERTION,
    ROLE_EXTRACTED_CANDIDATE,
    ROLE_RETRIEVED_PUBLIC_LAW,
    ROLE_APPLICABLE_REQUIREMENT,
    ROLE_CORROBORATING_EVIDENCE,
    ROLE_CONDITIONAL_IR,
    ROLE_PROOF_RESULT,
)

DECISION_UNKNOWN = "unknown"
SOURCE_DECISIONS = frozenset({DECISION_UNKNOWN, "admitted", "withheld", "rejected"})
EDITION_DECISIONS = frozenset({DECISION_UNKNOWN, "pinned", "superseded"})
APPLICABILITY_DECISIONS = frozenset({DECISION_UNKNOWN, "applicable", "inapplicable"})
MEANING_DECISIONS = frozenset({DECISION_UNKNOWN, "unresolved", "recorded"})
PROOF_OUTCOMES = frozenset({"unavailable", "not_run", "failed", "proved"})
CONDITIONAL_IR_STATUSES = frozenset({"unavailable", "not_compiled", "conditional", "failed"})

_SPOOF_FLAGS = frozenset({
    "verified",
    "satisfied",
    "is_verified",
    "is_satisfied",
    "proof_verified",
    "node_satisfied",
    "legally_verified",
    "legally_satisfied",
})
_REPLACEMENT_KEYS = frozenset({
    "assertion_contract",
    "assertion_envelope",
    "dependency_graph",
    "dependency_contract",
    "stop_policy",
    "stop_contract",
    "supervisor",
})
_PRIVATE_TEXT_KEYS = frozenset({
    "text",
    "source_text",
    "prompt",
    "passage",
    "snippet",
    "content",
})
_ALLOWED_KEYS = frozenset({
    "contract_version",
    "role",
    "owner_id",
    "case_id",
    "source_id",
    "source_version",
    "span_start",
    "span_end",
    "content_hash",
    "graph_revision",
    "source_decision",
    "edition_decision",
    "applicability_decision",
    "meaning_decision",
    "retrieval_score",
    "assertion_contract_ref",
    "dependency_contract_ref",
    "stop_contract_ref",
    "actual_proof_outcome",
    "proof_receipt_ref",
    "conditional_ir_status",
    "corroborates_ref",
    "candidate_extractor_ref",
    "governs_law",
})
_SCORE_ROLES = frozenset({ROLE_EXTRACTED_CANDIDATE, ROLE_RETRIEVED_PUBLIC_LAW})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _decision(payload: Dict[str, Any], key: str, allowed: frozenset) -> tuple[str, str]:
    if key not in payload or payload.get(key) is None:
        return DECISION_UNKNOWN, ""
    text = _text(payload.get(key))
    if text == "":
        return DECISION_UNKNOWN, ""
    if text not in allowed:
        return "", "invalid_" + key
    return text, ""


def _optional_span(value: Any, name: str) -> tuple[Optional[int], str]:
    if value is None:
        return None, ""
    if isinstance(value, bool) or not isinstance(value, int):
        return None, name + "_not_integer"
    if value < 0:
        return None, name + "_negative"
    return value, ""


def _governs_law(
    role: str,
    source_decision: str,
    edition_decision: str,
    source_id: str,
    source_version: str,
    content_hash: str,
) -> bool:
    """Public law governs only after an admitted source and a pinned edition.

    Retrieval scores and user statements never flip this bit.
    """
    return (
        role == ROLE_RETRIEVED_PUBLIC_LAW
        and source_decision == "admitted"
        and edition_decision == "pinned"
        and bool(source_id)
        and bool(source_version)
        and bool(content_hash)
    )


@dataclass(frozen=True)
class GroundingRoleRecord:
    """One handoff record. Role fields do not collapse into each other."""

    contract_version: str
    role: str
    owner_id: str
    case_id: str
    source_id: str
    source_version: str
    span_start: Optional[int]
    span_end: Optional[int]
    content_hash: str
    graph_revision: str
    source_decision: str = DECISION_UNKNOWN
    edition_decision: str = DECISION_UNKNOWN
    applicability_decision: str = DECISION_UNKNOWN
    meaning_decision: str = DECISION_UNKNOWN
    retrieval_score: Optional[float] = None
    assertion_contract_ref: str = PRESERVED_ASSERTION_CONTRACT_REF
    dependency_contract_ref: str = PRESERVED_DEPENDENCY_CONTRACT_REF
    stop_contract_ref: str = PRESERVED_STOP_CONTRACT_REF
    actual_proof_outcome: str = ""
    proof_receipt_ref: str = ""
    conditional_ir_status: str = ""
    corroborates_ref: str = ""
    candidate_extractor_ref: str = ""
    governs_law: bool = False

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["retrieval_score_governs"] = False
        payload["user_statement_governs"] = False
        payload["span"] = {
            "start": self.span_start,
            "end": self.span_end,
            "unit": "byte",
            "known": self.span_start is not None and self.span_end is not None,
        }
        return payload


@dataclass(frozen=True)
class GroundingRoleAdmission:
    admitted: bool
    reason: str
    record: Optional[GroundingRoleRecord] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "admitted": self.admitted,
            "reason": self.reason,
            "record": None if self.record is None else self.record.as_dict(),
        }


def _reject(reason: str) -> GroundingRoleAdmission:
    return GroundingRoleAdmission(admitted=False, reason=reason, record=None)


def admit_grounding_role(payload: Any) -> GroundingRoleAdmission:
    """Admit one role handoff. Spoofed proof flags fail closed.

    Omitted source, edition, applicability, and meaning decisions stay
    ``unknown``. This function does not satisfy a legal node, mint a proof
    receipt, or rewrite assertion, dependency, or stop contracts.
    """
    if not isinstance(payload, Mapping):
        return _reject("payload_not_mapping")
    data = dict(payload)
    spoofed = sorted(key for key in _SPOOF_FLAGS if key in data)
    if spoofed:
        return _reject("spoofed_" + spoofed[0] + "_flag")
    replaced = sorted(key for key in _REPLACEMENT_KEYS if key in data)
    if replaced:
        return _reject("preserved_contract_replacement")
    private = sorted(key for key in _PRIVATE_TEXT_KEYS if key in data)
    if private:
        return _reject("private_text_not_in_handoff")
    unknown_keys = sorted(key for key in data if key not in _ALLOWED_KEYS)
    if unknown_keys:
        return _reject("unknown_field")

    version = _text(data.get("contract_version")) or GROUNDING_ROLE_CONTRACT_VERSION
    if version != GROUNDING_ROLE_CONTRACT_VERSION:
        return _reject("contract_version_mismatch")
    role = _text(data.get("role"))
    if role not in GROUNDING_ROLES:
        return _reject("unknown_role")

    owner_id = _text(data.get("owner_id"))
    case_id = _text(data.get("case_id"))
    graph_revision = _text(data.get("graph_revision"))
    if not owner_id:
        return _reject("missing_owner")
    if not case_id:
        return _reject("missing_case")
    if not graph_revision:
        return _reject("missing_graph_revision")

    source_decision, source_error = _decision(data, "source_decision", SOURCE_DECISIONS)
    edition_decision, edition_error = _decision(data, "edition_decision", EDITION_DECISIONS)
    applicability_decision, applicability_error = _decision(
        data, "applicability_decision", APPLICABILITY_DECISIONS,
    )
    meaning_decision, meaning_error = _decision(data, "meaning_decision", MEANING_DECISIONS)
    for error in (source_error, edition_error, applicability_error, meaning_error):
        if error:
            return _reject(error)

    if applicability_decision == "applicable" and role != ROLE_APPLICABLE_REQUIREMENT:
        if role == ROLE_USER_ASSERTION:
            return _reject("user_assertion_cannot_decide_applicability")
        return _reject("applicability_requires_requirement_role")

    source_id = _text(data.get("source_id"))
    source_version = _text(data.get("source_version"))
    content_hash = _text(data.get("content_hash"))
    if content_hash and _HASH_RE.fullmatch(content_hash) is None:
        return _reject("content_hash_invalid")
    span_start, start_error = _optional_span(data.get("span_start"), "span_start")
    if start_error:
        return _reject(start_error)
    span_end, end_error = _optional_span(data.get("span_end"), "span_end")
    if end_error:
        return _reject(end_error)
    if (span_start is None) != (span_end is None):
        return _reject("span_incomplete")
    if span_start is not None and span_end is not None and span_end <= span_start:
        return _reject("span_not_ordered")

    if source_decision == "admitted" and not (source_id and source_version and content_hash and span_start is not None):
        return _reject("admitted_source_incomplete")
    if edition_decision == "pinned" and not source_version:
        return _reject("pinned_edition_missing_version")
    if source_decision == DECISION_UNKNOWN and edition_decision == "pinned":
        return _reject("unknown_source_cannot_pin_edition")

    retrieval_score: Optional[float] = None
    if "retrieval_score" in data and data.get("retrieval_score") is not None:
        raw_score = data.get("retrieval_score")
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            return _reject("retrieval_score_invalid")
        retrieval_score = float(raw_score)
        if retrieval_score != retrieval_score or retrieval_score in (float("inf"), float("-inf")):
            return _reject("retrieval_score_invalid")
        if role == ROLE_APPLICABLE_REQUIREMENT:
            return _reject("score_cannot_decide_applicability")
        if role not in _SCORE_ROLES:
            return _reject("retrieval_score_not_allowed_for_role")

    assertion_ref = _text(data.get("assertion_contract_ref")) or PRESERVED_ASSERTION_CONTRACT_REF
    dependency_ref = _text(data.get("dependency_contract_ref")) or PRESERVED_DEPENDENCY_CONTRACT_REF
    stop_ref = _text(data.get("stop_contract_ref")) or PRESERVED_STOP_CONTRACT_REF
    if assertion_ref != PRESERVED_ASSERTION_CONTRACT_REF:
        return _reject("preserved_assertion_contract_mismatch")
    if dependency_ref != PRESERVED_DEPENDENCY_CONTRACT_REF:
        return _reject("preserved_dependency_contract_mismatch")
    if stop_ref != PRESERVED_STOP_CONTRACT_REF:
        return _reject("preserved_stop_contract_mismatch")

    proof_outcome = ""
    proof_receipt_ref = ""
    conditional_status = ""
    corroborates_ref = ""
    candidate_extractor_ref = ""
    if role == ROLE_PROOF_RESULT:
        proof_outcome = _text(data.get("actual_proof_outcome")) or "unavailable"
        if proof_outcome not in PROOF_OUTCOMES:
            return _reject("invalid_actual_proof_outcome")
        proof_receipt_ref = _text(data.get("proof_receipt_ref"))
        if proof_outcome == "proved" and not proof_receipt_ref:
            return _reject("proof_receipt_required")
        if proof_outcome != "proved" and proof_receipt_ref and proof_outcome == "unavailable":
            return _reject("receipt_without_proof_outcome")
        if any(_text(data.get(key)) for key in ("conditional_ir_status", "corroborates_ref", "candidate_extractor_ref")):
            return _reject("role_fields_crossed")
    elif _text(data.get("actual_proof_outcome")) or _text(data.get("proof_receipt_ref")):
        return _reject("proof_fields_require_proof_role")
    elif role == ROLE_CONDITIONAL_IR:
        conditional_status = _text(data.get("conditional_ir_status")) or "unavailable"
        if conditional_status not in CONDITIONAL_IR_STATUSES:
            return _reject("invalid_conditional_ir_status")
        if conditional_status == "conditional" and source_decision == DECISION_UNKNOWN:
            conditional_status = "conditional"
        if any(_text(data.get(key)) for key in ("corroborates_ref", "candidate_extractor_ref")):
            return _reject("role_fields_crossed")
    elif _text(data.get("conditional_ir_status")):
        return _reject("conditional_ir_requires_ir_role")
    elif role == ROLE_CORROBORATING_EVIDENCE:
        corroborates_ref = _text(data.get("corroborates_ref"))
        if not corroborates_ref:
            return _reject("missing_corroborates_ref")
        if _text(data.get("candidate_extractor_ref")):
            return _reject("role_fields_crossed")
    elif _text(data.get("corroborates_ref")):
        return _reject("corroboration_requires_evidence_role")
    elif role == ROLE_EXTRACTED_CANDIDATE:
        candidate_extractor_ref = _text(data.get("candidate_extractor_ref"))
        if not candidate_extractor_ref:
            return _reject("missing_candidate_extractor_ref")
    elif _text(data.get("candidate_extractor_ref")):
        return _reject("candidate_fields_require_candidate_role")

    governs = _governs_law(
        role, source_decision, edition_decision, source_id, source_version, content_hash,
    )
    if "governs_law" in data and bool(data.get("governs_law")) != governs:
        if role == ROLE_USER_ASSERTION:
            return _reject("user_statement_cannot_govern")
        if retrieval_score is not None and bool(data.get("governs_law")):
            return _reject("retrieval_score_cannot_govern")
        return _reject("governing_law_spoof")
    if role == ROLE_USER_ASSERTION and data.get("governs_law") is True:
        return _reject("user_statement_cannot_govern")

    record = GroundingRoleRecord(
        contract_version=version,
        role=role,
        owner_id=owner_id,
        case_id=case_id,
        source_id=source_id,
        source_version=source_version,
        span_start=span_start,
        span_end=span_end,
        content_hash=content_hash,
        graph_revision=graph_revision,
        source_decision=source_decision,
        edition_decision=edition_decision,
        applicability_decision=applicability_decision,
        meaning_decision=meaning_decision,
        retrieval_score=retrieval_score,
        assertion_contract_ref=assertion_ref,
        dependency_contract_ref=dependency_ref,
        stop_contract_ref=stop_ref,
        actual_proof_outcome=proof_outcome,
        proof_receipt_ref=proof_receipt_ref,
        conditional_ir_status=conditional_status,
        corroborates_ref=corroborates_ref,
        candidate_extractor_ref=candidate_extractor_ref,
        governs_law=governs,
    )
    return GroundingRoleAdmission(admitted=True, reason="admitted", record=record)


@dataclass(frozen=True)
class GroundingRoleSet:
    contract_version: str
    records: Dict[str, GroundingRoleRecord]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "roles": {role: record.as_dict() for role, record in self.records.items()},
        }


@dataclass(frozen=True)
class GroundingRoleSetAdmission:
    admitted: bool
    reason: str
    role_set: Optional[GroundingRoleSet] = None


def admit_grounding_role_set(payloads: Any) -> GroundingRoleSetAdmission:
    """Admit a set of distinct role records. Duplicate roles fail closed."""
    if not isinstance(payloads, Sequence) or isinstance(payloads, (str, bytes)):
        return GroundingRoleSetAdmission(False, "payload_not_sequence", None)
    if len(payloads) == 0:
        return GroundingRoleSetAdmission(False, "empty_role_set", None)
    records: Dict[str, GroundingRoleRecord] = {}
    for payload in payloads:
        admission = admit_grounding_role(payload)
        if not admission.admitted or admission.record is None:
            return GroundingRoleSetAdmission(False, admission.reason, None)
        role = admission.record.role
        if role in records:
            return GroundingRoleSetAdmission(False, "duplicate_role", None)
        records[role] = admission.record
    return GroundingRoleSetAdmission(
        True,
        "admitted",
        GroundingRoleSet(GROUNDING_ROLE_CONTRACT_VERSION, records),
    )


_SYNTHETIC_HASH = "ab" * 32


def grounding_role_examples() -> List[Dict[str, Any]]:
    """Compact synthetic examples. Spoofed flags are included so callers can reject them."""
    base = {
        "owner_id": "owner-synthetic",
        "case_id": "case-synthetic",
        "graph_revision": "graph-rev-1",
        "assertion_contract_ref": PRESERVED_ASSERTION_CONTRACT_REF,
        "dependency_contract_ref": PRESERVED_DEPENDENCY_CONTRACT_REF,
        "stop_contract_ref": PRESERVED_STOP_CONTRACT_REF,
    }
    return [
        {
            "name": "user_assertion_unknown_decisions",
            "expect": "admitted",
            "payload": {
                **base,
                "role": ROLE_USER_ASSERTION,
                "source_id": "msg-1",
            },
        },
        {
            "name": "spoofed_verified",
            "expect": "spoofed_verified_flag",
            "payload": {**base, "role": ROLE_USER_ASSERTION, "verified": True},
        },
        {
            "name": "spoofed_satisfied",
            "expect": "spoofed_satisfied_flag",
            "payload": {**base, "role": ROLE_APPLICABLE_REQUIREMENT, "satisfied": True},
        },
        {
            "name": "score_does_not_govern_unknown_edition",
            "expect": "admitted",
            "payload": {
                **base,
                "role": ROLE_RETRIEVED_PUBLIC_LAW,
                "source_id": "statute-1",
                "source_version": "",
                "content_hash": _SYNTHETIC_HASH,
                "retrieval_score": 0.99,
                "governs_law": False,
            },
        },
        {
            "name": "admitted_pinned_public_law",
            "expect": "admitted",
            "payload": {
                **base,
                "role": ROLE_RETRIEVED_PUBLIC_LAW,
                "source_id": "statute-1",
                "source_version": "ed-2024",
                "span_start": 0,
                "span_end": 12,
                "content_hash": _SYNTHETIC_HASH,
                "source_decision": "admitted",
                "edition_decision": "pinned",
                "retrieval_score": 0.2,
            },
        },
        {
            "name": "user_statement_cannot_govern",
            "expect": "user_statement_cannot_govern",
            "payload": {**base, "role": ROLE_USER_ASSERTION, "governs_law": True},
        },
        {
            "name": "proof_unavailable",
            "expect": "admitted",
            "payload": {**base, "role": ROLE_PROOF_RESULT},
        },
        {
            "name": "conditional_ir_not_proof",
            "expect": "admitted",
            "payload": {
                **base,
                "role": ROLE_CONDITIONAL_IR,
                "conditional_ir_status": "conditional",
            },
        },
    ]
