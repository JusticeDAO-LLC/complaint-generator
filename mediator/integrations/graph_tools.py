import hashlib
import logging
import math
import re
import time
from typing import Any, Dict, List, Set


logger = logging.getLogger(__name__)

_CANDIDATE_NOMINATION = "candidate_nomination"
_SPAN_KEYS = ("start", "end", "text")


def _exact_source_span(left: Any, right: Any) -> bool:
    """Byte-span binding is exact. A missing or partial span is not a match."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if any(left.get(key) in (None, "") or right.get(key) in (None, "") for key in _SPAN_KEYS):
        return False
    if any(left.get(key) != right.get(key) for key in _SPAN_KEYS):
        return False
    if "unit" in left and "unit" in right and left.get("unit") != right.get("unit"):
        return False
    return True


def _payload_source_span(payload: Dict[str, Any]) -> Any:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return payload.get("source_span") or metadata.get("source_span")


def _payload_requirement_id(payload: Dict[str, Any]) -> str:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return str(payload.get("requirement_id") or metadata.get("requirement_id") or "").strip()


class GraphRetrievalAugmentor:
    """Builds graph-ingestable evidence payloads from normalized retrieval artifacts.

    Claim ids and retrieval confidence are candidate nominations. They become
    bound support only after ``recheck_support_binding`` sees the same claim,
    requirement, and source span. Retrieval confidence never satisfies a legal
    requirement by itself.
    """

    def build_evidence_payloads(
        self,
        legal_normalized: List[Dict[str, Any]],
        web_normalized: List[Dict[str, Any]],
        claim_ids: List[str],
        max_items: int = 20,
    ) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        seen_ids = set()

        def _make_id(prefix: str, value: str, index: int) -> str:
            cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)[:48]
            return f"{prefix}_{cleaned}_{index}"

        for index, item in enumerate(legal_normalized[:max_items]):
            title = str(item.get("title", "") or item.get("citation", "") or "Legal authority")
            record_id = _make_id("legal", title, index)
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)

            confidence = float(item.get("confidence", item.get("score", 0.6)) or 0.6)
            metadata = dict(item.get("metadata", {}) or {})
            payloads.append(
                {
                    "id": record_id,
                    "name": title,
                    "type": "legal_authority",
                    "description": str(item.get("snippet", "") or item.get("content", "") or ""),
                    "confidence": confidence,
                    "relevance": confidence,
                    "confidence_role": "retrieval_candidate",
                    "retrieval_confidence": confidence,
                    "supports_claims": list(claim_ids),
                    "support_status": _CANDIDATE_NOMINATION,
                    "binding_status": "unbound",
                    "bound_support": False,
                    "satisfied_support": False,
                    "satisfied_legal_requirement": False,
                    "source_type": "normalized_legal_authority",
                    "requirement_id": str(item.get("requirement_id") or metadata.get("requirement_id") or ""),
                    "source_span": item.get("source_span") or metadata.get("source_span"),
                    "metadata": metadata,
                }
            )

        remaining = max(0, max_items - len(payloads))
        for index, item in enumerate(web_normalized[:remaining]):
            title = str(item.get("title", "") or item.get("url", "") or "Web evidence")
            record_id = _make_id("web", title, index)
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)

            confidence = float(item.get("confidence", item.get("score", 0.5)) or 0.5)
            metadata = dict(item.get("metadata", {}) or {})
            payloads.append(
                {
                    "id": record_id,
                    "name": title,
                    "type": "web_evidence",
                    "description": str(item.get("snippet", "") or item.get("content", "") or ""),
                    "confidence": confidence,
                    "relevance": confidence,
                    "confidence_role": "retrieval_candidate",
                    "retrieval_confidence": confidence,
                    "supports_claims": list(claim_ids),
                    "support_status": _CANDIDATE_NOMINATION,
                    "binding_status": "unbound",
                    "bound_support": False,
                    "satisfied_support": False,
                    "satisfied_legal_requirement": False,
                    "source_type": "normalized_web_evidence",
                    "requirement_id": str(item.get("requirement_id") or metadata.get("requirement_id") or ""),
                    "source_span": item.get("source_span") or metadata.get("source_span"),
                    "metadata": metadata,
                }
            )

        return payloads

    def recheck_support_binding(
        self,
        payload: Dict[str, Any],
        *,
        claim_id: str,
        requirement_id: str,
        source_span: Any,
    ) -> Dict[str, Any]:
        """Promote a nomination only when claim, requirement, and span all match.

        A failed recheck stays a candidate nomination. Retrieval confidence is
        not rewritten into legal satisfaction.
        """
        source = dict(payload or {})
        nominated = [str(item) for item in (source.get("supports_claims") or []) if str(item).strip()]
        retrieval_confidence = source.get("retrieval_confidence", source.get("confidence"))
        result = dict(source)
        result["supports_claims"] = list(nominated)
        result["support_status"] = _CANDIDATE_NOMINATION
        result["binding_status"] = "unbound"
        result["bound_support"] = False
        result["satisfied_support"] = False
        result["satisfied_legal_requirement"] = False
        result["confidence_role"] = "retrieval_candidate"
        result["retrieval_confidence"] = retrieval_confidence
        result["bound_claim_id"] = ""
        result["bound_requirement_id"] = ""
        result["bound_source_span"] = None

        reasons = []
        if not claim_id or claim_id not in nominated:
            reasons.append("claim_not_nominated")
        recorded_requirement = _payload_requirement_id(source)
        if not requirement_id or not recorded_requirement or recorded_requirement != requirement_id:
            reasons.append("requirement_not_exact")
        if not _exact_source_span(_payload_source_span(source), source_span):
            reasons.append("source_span_not_exact")
        if reasons:
            result["binding_reason"] = ",".join(reasons)
            return result

        result["support_status"] = "bound_allegation_support"
        result["binding_status"] = "exact"
        result["bound_support"] = True
        result["satisfied_support"] = True
        result["satisfied_legal_requirement"] = False
        result["binding_reason"] = "exact_claim_requirement_source_span"
        result["bound_claim_id"] = claim_id
        result["bound_requirement_id"] = requirement_id
        result["bound_source_span"] = {
            "start": source_span["start"],
            "end": source_span["end"],
            "text": source_span["text"],
        }
        if "unit" in source_span:
            result["bound_source_span"]["unit"] = source_span["unit"]
        result["supports_claims"] = [claim_id]
        return result


class GraphAwareRetrievalReranker:
    """Applies graph-context-aware score adjustments to normalized retrieval records."""

    _TOKEN_RE = re.compile(r"[a-z0-9_]+")

    def _tokenize(self, text: str) -> Set[str]:
        return {tok for tok in self._TOKEN_RE.findall((text or "").lower()) if len(tok) > 2}

    def should_apply_canary(self, seed: str, percent: int) -> bool:
        pct = max(0, min(100, int(percent)))
        if pct <= 0:
            return False
        if pct >= 100:
            return True

        digest = hashlib.sha256((seed or "").encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return bucket < pct

    def _extract_readiness_context(self, mediator: Any) -> Dict[str, Any]:
        phase_manager = getattr(mediator, "phase_manager", None)
        if phase_manager is None:
            return {
                "overall_readiness": 1.0,
                "priority_terms": [],
            }

        try:
            from complaint_phases import ComplaintPhase
        except Exception:
            return {
                "overall_readiness": 1.0,
                "priority_terms": [],
            }

        dg = None
        try:
            dg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
        except Exception:
            dg = None

        if dg is None:
            return {
                "overall_readiness": 1.0,
                "priority_terms": [],
            }

        overall_readiness = 1.0
        priority_terms: List[str] = []

        try:
            readiness_priority_terms: List[str] = []
            readiness = dg.get_claim_readiness() if hasattr(dg, "get_claim_readiness") else {}
            if isinstance(readiness, dict):
                readiness_value = readiness.get("overall_readiness", 1.0)
                parsed_readiness = 1.0 if readiness_value is None else float(readiness_value)
                for claim in readiness.get("incomplete_claim_details", []) or []:
                    if not isinstance(claim, dict):
                        continue
                    claim_name = str(claim.get("claim_name", "") or "")
                    if claim_name:
                        readiness_priority_terms.append(claim_name)
                overall_readiness = parsed_readiness
                priority_terms.extend(readiness_priority_terms)
        except Exception:
            logger.warning(
                "Failed to extract dependency-graph claim readiness; "
                "using neutral readiness defaults",
                exc_info=True,
            )

        try:
            unsatisfied_priority_terms: List[str] = []
            unsatisfied = (
                dg.find_unsatisfied_requirements()
                if hasattr(dg, "find_unsatisfied_requirements")
                else []
            )
            for item in unsatisfied or []:
                if not isinstance(item, dict):
                    continue
                node_name = str(item.get("node_name", "") or "")
                if node_name:
                    unsatisfied_priority_terms.append(node_name)
                for missing in item.get("missing_dependencies", []) or []:
                    if not isinstance(missing, dict):
                        continue
                    source_name = str(missing.get("source_name", "") or "")
                    if source_name and source_name.lower() != "unknown":
                        unsatisfied_priority_terms.append(source_name)
            priority_terms.extend(unsatisfied_priority_terms)
        except Exception:
            logger.warning(
                "Failed to extract unsatisfied dependency-graph requirements; "
                "continuing without requirement priority terms",
                exc_info=True,
            )

        return {
            "overall_readiness": max(0.0, min(1.0, overall_readiness)),
            "priority_terms": priority_terms,
        }

    def extract_graph_terms(self, mediator: Any, max_terms: int = 200) -> List[str]:
        phase_manager = getattr(mediator, "phase_manager", None)
        if phase_manager is None:
            return []

        try:
            from complaint_phases import ComplaintPhase, NodeType
        except ImportError:
            logger.warning(
                "Complaint phase graph types are unavailable; "
                "continuing without graph-derived retrieval terms",
                exc_info=True,
            )
            return []

        terms: List[str] = []

        try:
            knowledge_graph_terms: List[str] = []
            kg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
            if kg is not None and hasattr(kg, "get_entities_by_type"):
                for entity_type in ("claim", "fact", "organization"):
                    entities = kg.get_entities_by_type(entity_type) or []
                    for entity in entities:
                        name = str(getattr(entity, "name", "") or "")
                        if name:
                            knowledge_graph_terms.append(name)
                        attrs = getattr(entity, "attributes", {}) or {}
                        for value in attrs.values():
                            if isinstance(value, str):
                                knowledge_graph_terms.append(value)
            terms.extend(knowledge_graph_terms)
        except Exception:
            logger.warning(
                "Failed to extract knowledge-graph retrieval terms; "
                "continuing with other graph sources",
                exc_info=True,
            )

        try:
            dependency_graph_terms: List[str] = []
            dg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
            if dg is not None and hasattr(dg, "get_nodes_by_type"):
                claim_nodes = dg.get_nodes_by_type(NodeType.CLAIM) or []
                for node in claim_nodes:
                    node_name = str(getattr(node, "name", "") or "")
                    node_description = str(getattr(node, "description", "") or "")
                    if node_name:
                        dependency_graph_terms.append(node_name)
                    if node_description:
                        dependency_graph_terms.append(node_description)
            terms.extend(dependency_graph_terms)
        except Exception:
            logger.warning(
                "Failed to extract dependency-graph retrieval terms; "
                "continuing without dependency-graph terms",
                exc_info=True,
            )

        try:
            legal_graph_terms: List[str] = []
            legal_graph = phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, "legal_graph")
            if legal_graph is not None and hasattr(legal_graph, "elements"):
                for element in list(getattr(legal_graph, "elements", {}).values())[:50]:
                    element_name = str(getattr(element, "name", "") or "")
                    element_description = str(getattr(element, "description", "") or "")
                    if element_name:
                        legal_graph_terms.append(element_name)
                    if element_description:
                        legal_graph_terms.append(element_description)
            terms.extend(legal_graph_terms)
        except Exception:
            logger.warning(
                "Failed to extract legal-graph retrieval terms; "
                "continuing with other graph sources",
                exc_info=True,
            )

        deduped: List[str] = []
        seen = set()
        for term in terms:
            cleaned = " ".join(term.strip().split())
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(cleaned)
            if len(deduped) >= max_terms:
                break

        return deduped

    def augment_normalized_records(
        self,
        records: List[Dict[str, Any]],
        query: str,
        mediator: Any,
        max_boost: float = 0.12,
        enable_optimizer: bool = False,
        retrieval_max_latency_ms: int = 1500,
    ) -> List[Dict[str, Any]]:
        started = time.perf_counter()
        graph_terms = self.extract_graph_terms(mediator=mediator)
        if not graph_terms:
            return records

        graph_tokens = set()
        for term in graph_terms:
            graph_tokens.update(self._tokenize(term))

        if not graph_tokens:
            return records

        query_tokens = self._tokenize(query)
        effective_graph_tokens = graph_tokens | query_tokens
        readiness_context = self._extract_readiness_context(mediator=mediator)
        readiness_value = readiness_context.get("overall_readiness", 1.0)
        overall_readiness = 1.0 if readiness_value is None else float(readiness_value)
        readiness_gap = max(0.0, min(1.0, 1.0 - overall_readiness))

        priority_tokens = set()
        for term in readiness_context.get("priority_terms", []) or []:
            priority_tokens.update(self._tokenize(str(term)))

        effective_priority_tokens = priority_tokens | query_tokens if priority_tokens else query_tokens
        effective_max_boost = max_boost
        if enable_optimizer:
            priority_term_count = len(readiness_context.get("priority_terms", []) or [])
            tuned = max_boost * (1.0 + (0.5 * readiness_gap))
            tuned += min(0.04, priority_term_count * 0.002)
            effective_max_boost = min(0.2, tuned)

        latency_guard_applied = False
        latency_scale = 1.0
        if retrieval_max_latency_ms <= 100:
            latency_scale = 0.5
            latency_guard_applied = True
        elif retrieval_max_latency_ms <= 250:
            latency_scale = 0.7
            latency_guard_applied = True
        elif retrieval_max_latency_ms <= 500 and len(records) > 20:
            latency_scale = 0.85
            latency_guard_applied = True

        effective_max_boost *= latency_scale

        boost_values: List[float] = []

        augmented: List[Dict[str, Any]] = []
        for record in records:
            merged_text = " ".join(
                [
                    str(record.get("title", "") or ""),
                    str(record.get("snippet", "") or ""),
                    str(record.get("content", "") or ""),
                    str(record.get("citation", "") or ""),
                ]
            )
            text_tokens = self._tokenize(merged_text)
            overlap = len(text_tokens & effective_graph_tokens)
            overlap_ratio = overlap / max(1, len(effective_graph_tokens))
            priority_overlap = len(text_tokens & effective_priority_tokens)
            priority_ratio = priority_overlap / max(1, len(effective_priority_tokens))

            graph_boost = overlap_ratio * effective_max_boost * 3
            readiness_boost = priority_ratio * effective_max_boost * (1.0 + readiness_gap)
            boost = min(effective_max_boost, graph_boost + readiness_boost)
            boost_values.append(boost)

            candidate = dict(record)
            base_score = float(candidate.get("score", 0.0) or 0.0)
            base_confidence = float(candidate.get("confidence", base_score) or 0.0)
            candidate["score"] = min(1.0, base_score + boost)
            candidate["confidence"] = min(1.0, max(base_confidence, candidate["score"]))

            metadata = dict(candidate.get("metadata", {}) or {})
            metadata.update(
                {
                    "graph_reranked": True,
                    "graph_overlap": overlap,
                    "graph_overlap_ratio": round(overlap_ratio, 4),
                    "graph_terms_count": len(graph_terms),
                    "graph_priority_overlap": priority_overlap,
                    "graph_priority_ratio": round(priority_ratio, 4),
                    "graph_priority_terms_count": len(readiness_context.get("priority_terms", []) or []),
                    "graph_readiness_gap": round(readiness_gap, 4),
                    "graph_optimizer_tuned": bool(enable_optimizer),
                    "graph_effective_max_boost": round(effective_max_boost, 4),
                    "graph_applied_boost": round(boost, 4),
                    "graph_latency_budget_ms": int(retrieval_max_latency_ms),
                    "graph_latency_guard_applied": latency_guard_applied,
                }
            )
            candidate["metadata"] = metadata
            augmented.append(candidate)

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        avg_boost = (sum(boost_values) / len(boost_values)) if boost_values else 0.0
        boosted_count = sum(1 for value in boost_values if value > 0.0)
        for candidate in augmented:
            metadata = dict(candidate.get("metadata", {}) or {})
            metadata.update(
                {
                    "graph_run_elapsed_ms": round(elapsed_ms, 3),
                    "graph_run_avg_boost": round(avg_boost, 4),
                    "graph_run_boosted_count": boosted_count,
                }
            )
            candidate["metadata"] = metadata

        return augmented


class FactualGraphProjectionError(Exception):
    """Fail-closed factual projection error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


_PROJECTION_LIMITATIONS = (
    "projection_is_read_only",
    "verified_source_ids_are_immutable",
    "hypothesis_is_not_a_user_fact",
    "legal_text_is_not_a_user_fact",
    "retrieval_confidence_is_not_authority",
    "evidence_revision_is_not_a_user_statement",
    "no_websocket_or_sse",
)


def pinned_data_graph_owner() -> Dict[str, Any]:
    """Identity of the pinned ipfs_datasets_py knowledge-graph owner.

    Availability is the imported owner module. Opening a graph client or
    writing a catalog is not required to name the owner, and a missing module
    stays unavailable instead of a local substitute owner.
    """
    from integrations.ipfs_datasets.graphs import GRAPHS_ERROR, _knowledge_graphs_module

    module = _knowledge_graphs_module
    available = module is not None
    return {
        "owner_id": "ipfs_datasets_py",
        "module": "ipfs_datasets_py.knowledge_graphs",
        "available": available,
        "client_api_version": str(getattr(module, "CLIENT_API_VERSION", "") or "") if available else "",
        "contract_version": str(getattr(module, "CONTRACT_VERSION", "") or "") if available else "",
        "unavailable_reason": "" if available else str(GRAPHS_ERROR or "knowledge_graphs_unavailable"),
    }


def _text_of(record: Dict[str, Any]) -> str:
    assertion = record.get("assertion") if isinstance(record.get("assertion"), dict) else {}
    attributes = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
    for value in (
        assertion.get("source_span_text"),
        attributes.get("description"),
        record.get("name"),
        assertion.get("statement"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _immutable_source_id(record: Dict[str, Any]) -> str:
    envelope = _validated_assertion(record)
    if envelope is not None:
        return envelope.stable_id
    assertion = record.get("assertion") if isinstance(record.get("assertion"), dict) else {}
    provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    attributes = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
    for container in (assertion, provenance, attributes):
        for key in ("immutable_source_id", "source_identity", "source_id", "message_id", "document_id"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    source_hash = assertion.get("source_hash") or provenance.get("source_hash") or attributes.get("source_hash")
    if isinstance(source_hash, str) and source_hash.strip():
        return "src:" + source_hash.strip()
    return ""


def _record_case_id(record: Dict[str, Any]) -> str:
    provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    attributes = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
    assertion = record.get("assertion") if isinstance(record.get("assertion"), dict) else {}
    for container in (provenance, attributes, assertion):
        value = container.get("case_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _classify_projection(record: Dict[str, Any]) -> str:
    """Separate user statements, allegations, evidence, hypotheses, and legal text."""
    from integrations.ipfs_datasets.graphs import (
        CORROBORATING_EVIDENCE_CLASS,
        INFERRED_HYPOTHESIS_CLASS,
        LEGAL_AUTHORITY_CLASS,
        USER_ALLEGATION_CLASS,
        classify_epistemic_class,
    )

    assertion = record.get("assertion") if isinstance(record.get("assertion"), dict) else {}
    attributes = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
    provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    factual_class = str(
        attributes.get("factual_record_class")
        or assertion.get("factual_record_class")
        or ""
    )
    record_type = str(assertion.get("record_type") or record.get("type") or "")
    origin = str(provenance.get("origin") or attributes.get("origin") or record.get("source") or "").lower()
    if factual_class == "legal_text" or record_type == "legal_text" or origin in {"legal", "authority"}:
        return "legal_text"
    if factual_class == "extraction_hypothesis" or record_type in {"model_suggestion", "inferred_claim_label"}:
        return "hypothesis"
    if factual_class == "supporting_evidence" or record_type in {"evidence", "supporting_evidence"}:
        return "evidence_revision"
    explicit = str(attributes.get("epistemic_class") or assertion.get("epistemic_class") or "")
    epistemic = classify_epistemic_class(_text_of(record), explicit=explicit or None, legal=False)
    if epistemic == LEGAL_AUTHORITY_CLASS:
        return "legal_text"
    if epistemic == INFERRED_HYPOTHESIS_CLASS or origin in {"model", "llm", "inference"}:
        return "hypothesis"
    if epistemic == CORROBORATING_EVIDENCE_CLASS:
        return "evidence_revision"
    if record.get("type") == "allegation" or epistemic == USER_ALLEGATION_CLASS and explicit == USER_ALLEGATION_CLASS:
        return "allegation"
    if factual_class == "user_fact" or assertion.get("is_asserted_user_fact") is True or record.get("type") == "fact":
        if record.get("type") == "allegation":
            return "allegation"
        return "user_statement"
    if epistemic == USER_ALLEGATION_CLASS and record.get("type") == "allegation":
        return "allegation"
    return "unresolved"


_AUTHORITY = {
    "user_statement": ("user", "user_assertion", True),
    "allegation": ("allegation", "allegation", False),
    "evidence_revision": ("evidence", "evidence_revision", False),
    "hypothesis": ("hypothesis", "hypothesis", False),
}


def _validated_assertion(record: Dict[str, Any]) -> Any:
    """Recompute the typed source proof; a serialized success flag is no proof."""
    from integrations.ipfs_datasets.types import user_assertion_from_mapping

    raw = record.get("assertion")
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        envelope = user_assertion_from_mapping(raw)
        return envelope if envelope.is_asserted_user_fact else None
    except (TypeError, ValueError, OverflowError):
        return None


def _assertion_activity(record: Dict[str, Any], envelope: Any, states: Dict[str, Any]) -> str:
    if envelope is None:
        return "unverified"
    if envelope.stable_id not in states:
        return "active"
    state = states[envelope.stable_id]
    if not isinstance(state, dict):
        return "unverified"
    state_record = {"assertion": state.get("envelope")}
    state_envelope = _validated_assertion(state_record)
    if (state.get("stable_id") != envelope.stable_id
            or state.get("entity_id") != str(record.get("id") or "")
            or state_envelope is None
            or state_envelope.stable_id != envelope.stable_id):
        return "unverified"
    status = state.get("status")
    return status if isinstance(status, str) and status in {"active", "superseded", "retracted", "conflict"} else "unverified"


def _projection_item(
    kind: str, record: Dict[str, Any], *, case_id: str, states: Dict[str, Any]
) -> Dict[str, Any]:
    authority, confidence_role, _user_class = _AUTHORITY[kind]
    envelope = _validated_assertion(record)
    activity = _assertion_activity(record, envelope, states)
    confidence = record.get("confidence")
    try:
        parsed = None if confidence is None else float(confidence)
        if parsed is not None and not math.isfinite(parsed):
            parsed = None
    except (TypeError, ValueError, OverflowError):
        parsed = None
    verified = envelope is not None
    admitted = bool(kind == "user_statement" and verified and activity == "active")
    return {
        "kind": kind,
        # Older imported graph candidates can retain their display reference.
        # Only a recomputed envelope grants immutable/asserted authority.
        "immutable_source_id": envelope.stable_id if verified else _immutable_source_id(record),
        "source_id_mutable": not verified,
        "source_identity_verified": verified,
        "assertion_id": envelope.stable_id if verified else "",
        "source_identity": envelope.source_identity if verified else "",
        "provenance_status": "verified" if verified else "unverified",
        "activity_status": activity,
        "text": envelope.source_span_text if verified else _text_of(record),
        "confidence": parsed,
        "confidence_role": confidence_role,
        # Category labels describe the candidate's class. The two authority
        # booleans below require current, independently recomputed source proof.
        "authority": authority,
        "authority_is_user_fact": admitted,
        "admitted_user_fact": admitted,
        "case_id": case_id,
        "graph_entity_id": str(record.get("id") or ""),
        "owner_id": "ipfs_datasets_py",
    }


def _entity_records(knowledge_graph: Any) -> List[Dict[str, Any]]:
    from complaint_phases.knowledge_graph import entity_to_graph_entity

    return [
        entity_to_graph_entity(entity).as_dict()
        for entity in knowledge_graph.entities.values()
    ]


def _revision_record(revision: Dict[str, Any]) -> Dict[str, Any]:
    """Retain a legacy evidence candidate without certifying its provenance.

    Actual supersede/retract/conflict entries are handled separately and never
    relabeled as supporting evidence.
    """
    source_id = str(revision.get("immutable_source_id") or revision.get("source_id") or "")
    return {
        "id": str(revision.get("revision_id") or revision.get("id") or ""),
        "type": "evidence",
        "name": str(revision.get("text") or revision.get("statement") or ""),
        "confidence": revision.get("confidence"),
        "attributes": {
            "description": str(revision.get("text") or revision.get("statement") or ""),
            "factual_record_class": "supporting_evidence",
            "case_id": revision.get("case_id") or "",
            "immutable_source_id": source_id,
        },
        "provenance": {
            "source_id": source_id,
            "case_id": revision.get("case_id") or "",
            "origin": "evidence_revision",
        },
        "assertion": {},
        "source": "evidence",
    }


def _revision_projection(revision: Dict[str, Any], states: Dict[str, Any]) -> Dict[str, Any]:
    """Project correction metadata, excluding private original source documents."""
    action = revision.get("action")
    if not isinstance(action, str):
        action = "unrecognized"
    index = revision.get("revision_index")
    result = {
        "action": action if action in {"supersede", "retract", "conflict"} else "unrecognized",
        "event_id": str(revision.get("event_id") or ""),
        "revision_index": index if type(index) is int and index > 0 else None,
        "provenance_status": "unverified",
    }
    if action in {"supersede", "retract"}:
        previous = _validated_assertion({"assertion": revision.get("previous_envelope")})
        current = _validated_assertion({"assertion": revision.get("new_envelope")})
        bound = bool(previous is not None and current is not None
            and revision.get("previous_stable_id") == previous.stable_id
            and revision.get("new_stable_id") == current.stable_id)
        result.update({
            "previous_assertion_id": str(revision.get("previous_stable_id") or ""),
            "new_assertion_id": str(revision.get("new_stable_id") or ""),
            "previous_entity_id": str(revision.get("previous_entity_id") or ""),
            "new_entity_id": str(revision.get("new_entity_id") or ""),
            "provenance_status": "verified" if bound else "unverified",
        })
    elif action == "conflict":
        ids = revision.get("stable_ids")
        assertion_ids = [item for item in ids if isinstance(item, str)] if isinstance(ids, list) else []
        verified = bool(assertion_ids) and all(
            isinstance(states.get(item), dict)
            and (envelope := _validated_assertion({"assertion": states[item].get("envelope")})) is not None
            and envelope.stable_id == item
            for item in assertion_ids
        )
        result.update(assertion_ids=assertion_ids, provenance_status="verified" if verified else "unverified")
    return result


def project_factual_kg(knowledge_graph: Any, *, case_id: str) -> Dict[str, Any]:
    """Pure projection of a case-bound, freshly decrypted Root knowledge graph.

    This function grants no access. Its caller must obtain the graph through
    the live case/key authority and revalidate that authority before releasing
    the result. It never opens a global catalog, constructs a mediator, reads
    a cache, or initializes correction state.
    """
    from complaint_phases.knowledge_graph import KnowledgeGraph
    from integrations.ipfs_datasets.graphs import build_factual_graph_artifact

    bound_case = str(case_id or "").strip()
    if not bound_case:
        raise FactualGraphProjectionError("cross_case_id")
    if not isinstance(knowledge_graph, KnowledgeGraph):
        raise FactualGraphProjectionError("knowledge_graph_unavailable")
    owner = pinned_data_graph_owner()
    if owner["available"] is not True:
        raise FactualGraphProjectionError("data_graph_owner_unavailable")
    # Reuse the same typed Root/Data artifact owner as the encrypted factual
    # revision protocol. Unlike factual_ledger(), this normalization is pure.
    document = build_factual_graph_artifact(knowledge_graph)
    metadata = knowledge_graph.metadata
    graph_case = str(metadata.get("case_id") or "")
    if graph_case and graph_case != bound_case:
        raise FactualGraphProjectionError("cross_case_id")
    ledger = metadata.get("factual_ledger", {})
    if not isinstance(ledger, dict):
        raise FactualGraphProjectionError("factual_ledger_invalid")
    states = ledger.get("assertion_states", {})
    revisions = ledger.get("revisions", [])
    conflicts = ledger.get("conflicts", [])
    if (not isinstance(states, dict) or not isinstance(revisions, list)
            or not isinstance(conflicts, list)
            or any(not isinstance(item, dict) for item in revisions + conflicts)):
        raise FactualGraphProjectionError("factual_ledger_invalid")

    buckets: Dict[str, List[Dict[str, Any]]] = {
        "user_statements": [], "evidence_revisions": [], "allegations": [], "hypotheses": [],
    }
    withheld_legal, unresolved, denied_cross_case = [], [], []
    records = _entity_records(knowledge_graph)
    correction_revisions = []
    for revision in revisions:
        if revision.get("action") is not None:
            correction_revisions.append(_revision_projection(revision, states))
        elif revision.get("immutable_source_id") or revision.get("source_id"):
            records.append(_revision_record(revision))
        else:
            correction_revisions.append(_revision_projection(revision, states))

    for record in records:
        record_case = _record_case_id(record)
        if record_case and record_case != bound_case:
            denied_cross_case.append(record_case)
            continue
        kind = _classify_projection(record)
        candidate_source_id = _immutable_source_id(record)
        if kind == "legal_text":
            withheld_legal.append({"immutable_source_id": candidate_source_id, "authority": "legal_text"})
            continue
        if kind not in _AUTHORITY or not candidate_source_id:
            unresolved.append({"kind": kind,
                "reason": "missing_immutable_source_id" if not candidate_source_id else "unclassified"})
            continue
        field = {"user_statement": "user_statements", "allegation": "allegations",
            "evidence_revision": "evidence_revisions", "hypothesis": "hypotheses"}[kind]
        buckets[field].append(_projection_item(kind, record, case_id=bound_case, states=states))

    unresolved_conflicts = []
    for conflict in conflicts:
        if str(conflict.get("status") or "unresolved") == "unresolved":
            item = _revision_projection({**conflict, "action": "conflict"}, states)
            item["status"] = "unresolved"
            unresolved_conflicts.append(item)

    return {
        "status": "projected",
        "case_id": bound_case,
        "graph_id": document["graph_id"],
        "graph_version": document["graph_version"],
        "factual_artifact_schema": document["schema"],
        "data_graph_owner": owner,
        "read_only": True,
        **buckets,
        "revisions": correction_revisions,
        "unresolved_conflicts": unresolved_conflicts,
        "invalidations": document["invalidations"],
        "withheld_legal_text": withheld_legal,
        "unresolved": unresolved,
        "denied_cross_case_ids": sorted(set(denied_cross_case)),
        "limitations": list(_PROJECTION_LIMITATIONS) + ["unverified_source_references_are_candidates_only"],
    }


def project_authorized_factual_kg(
    mediator: Any, *, case_id: str, graph_read_granted: bool, requested_case_id: str = ""
) -> Dict[str, Any]:
    """Compatibility hook for trusted local callers, with identical provenance rules.

    HTTP reads use project_factual_kg only after decrypting the actual bound
    workspace. A phase cache and this boolean do not authorize an HTTP read.
    """
    if graph_read_granted is not True:
        raise FactualGraphProjectionError("graph_read_ungranted")
    bound_case = str(case_id or "").strip()
    if not bound_case or str(requested_case_id or bound_case).strip() != bound_case:
        raise FactualGraphProjectionError("cross_case_id")
    phase_manager = getattr(mediator, "phase_manager", None)
    if phase_manager is None or not callable(getattr(phase_manager, "get_phase_data", None)):
        raise FactualGraphProjectionError("mediator_graph_hook_unavailable")
    try:
        from complaint_phases import ComplaintPhase
        graph = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    except Exception as exc:
        raise FactualGraphProjectionError("mediator_graph_hook_unavailable") from exc
    return project_factual_kg(graph, case_id=bound_case)
