from __future__ import annotations

from copy import deepcopy
import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from intake_status import (
    build_intake_case_review_summary,
    build_intake_status_summary,
    build_intake_warning_entries,
)
from claim_support_review import summarize_claim_reasoning_review

try:
    from integrations.ipfs_datasets.llm import generate_text_with_metadata
except Exception:
    def generate_text_with_metadata(*args, **kwargs):
        return {"status": "unavailable", "text": ""}

try:
    from integrations.ipfs_datasets.storage import IPFS_AVAILABLE, store_bytes
except Exception:
    IPFS_AVAILABLE = False

    def store_bytes(data: bytes, *, pin_content: bool = True):
        return {"status": "disabled", "cid": "", "size": len(data), "pinned": False}

try:
    from integrations.ipfs_datasets.vector_store import EMBEDDINGS_AVAILABLE, get_embeddings_router
except Exception:
    EMBEDDINGS_AVAILABLE = False

    def get_embeddings_router(*args, **kwargs):
        return None

try:
    from integrations.ipfs_datasets.loader import import_attr_optional
except Exception:
    def import_attr_optional(*args, **kwargs):
        return None, None


OptimizerLLMRouter, _optimizer_router_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.agentic",
    "OptimizerLLMRouter",
)
ControlLoopConfig, _control_loop_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.agentic",
    "ControlLoopConfig",
)
OptimizationMethod, _optimization_method_error = import_attr_optional(
    "ipfs_datasets_py.optimizers.agentic",
    "OptimizationMethod",
)

LLM_ROUTER_AVAILABLE = callable(generate_text_with_metadata)
UPSTREAM_AGENTIC_AVAILABLE = any(
    value is not None for value in (OptimizerLLMRouter, ControlLoopConfig, OptimizationMethod)
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _unique_preserving_order(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(text)
    return ordered


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _dedupe_text_values(values: Iterable[Any]) -> List[str]:
    seen = set()
    normalized_values: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        normalized_values.append(text)
    return normalized_values


_DATE_ANCHOR_PATTERN = re.compile(
    r"\b(?:"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s+\d{2,4})?"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|(?:on|by|around|about|before|after)\s+(?:or\s+about\s+)?(?:\d{1,2}/\d{1,2}/\d{2,4}|\w+\s+\d{1,2}(?:,\s+\d{2,4})?)"
    r"|(?:in|during)\s+(?:19|20)\d{2}"
    r")\b",
    re.IGNORECASE,
)


def _contains_date_anchor(text: Any) -> bool:
    return bool(_DATE_ANCHOR_PATTERN.search(str(text or "")))


def _contains_actor_marker(text: Any) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    actor_markers = (
        "who at hacc",
        "caseworker",
        "housing specialist",
        "program manager",
        "hearing officer",
        "staff",
        "supervisor",
        "director",
        "coordinator",
        "agent",
        "decision maker",
        "name",
        "title",
    )
    return any(marker in lowered for marker in actor_markers)


def _contains_causation_link(text: Any) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    causation_markers = (
        "because",
        "as a result",
        "as a direct result",
        "after",
        "following",
        "days after",
        "weeks after",
        "shortly after",
        "in retaliation",
        "retaliat",
        "led to",
        "resulted in",
        "triggered",
    )
    protected_markers = (
        "reported",
        "complained",
        "grievance",
        "appeal",
        "requested accommodation",
        "requested a hearing",
        "protected activity",
    )
    adverse_markers = (
        "adverse action",
        "termination",
        "denial",
        "suspension",
        "loss of assistance",
        "retaliat",
        "disciplined",
    )
    return (
        any(marker in lowered for marker in causation_markers)
        and any(marker in lowered for marker in protected_markers)
        and any(marker in lowered for marker in adverse_markers)
    )


_INTAKE_OBJECTIVE_ALIASES = {
    "timeline": "timeline",
    "timeline_dates": "timeline",
    "actors": "actors",
    "staff_names_titles": "staff_names_titles",
    "staff_names": "staff_names_titles",
    "staff_titles": "staff_names_titles",
    "causation_link": "causation_link",
    "causation": "causation_link",
    "anchor_adverse_action": "anchor_adverse_action",
    "adverse_action": "anchor_adverse_action",
    "anchor_appeal_rights": "anchor_appeal_rights",
    "appeal_rights": "anchor_appeal_rights",
    "hearing_request_timing": "hearing_request_timing",
    "hearing_timing": "hearing_request_timing",
    "response_dates": "response_dates",
    "response_timing": "response_dates",
}

_INTAKE_OBJECTIVE_PRIORITY = {
    "timeline": 1.0,
    "staff_names_titles": 1.0,
    "actors": 0.9,
    "causation_link": 1.0,
    "anchor_adverse_action": 1.0,
    "anchor_appeal_rights": 0.9,
    "hearing_request_timing": 0.9,
    "response_dates": 0.9,
}

_OBJECTIVE_PROMPTS = {
    "timeline": "Capture exact event dates or anchored date ranges for each key intake, complaint, and adverse-action event.",
    "actors": "Identify the HACC actor-by-actor sequence for who made, communicated, and carried out each decision.",
    "staff_names_titles": "Lock specific HACC staff names and titles (or best-known titles) tied to each step.",
    "causation_link": "Document facts that tie protected activity to the adverse treatment using timing, statements, and sequence changes.",
    "anchor_adverse_action": "Confirm the exact adverse action (denial, termination, threatened loss) and its communication date.",
    "anchor_appeal_rights": "Confirm written notice, hearing/review request timing, and whether those requests were accepted, denied, or ignored.",
    "hearing_request_timing": "Capture when hearing or review was requested, when HACC responded, and any gaps between request and response.",
    "response_dates": "Capture exact response dates for notices, review decisions, hearing outcomes, and communications.",
}


def _normalize_intake_objective(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return _INTAKE_OBJECTIVE_ALIASES.get(text, text)


def _normalize_intake_objectives(values: Any) -> List[str]:
    return _dedupe_text_values(_normalize_intake_objective(item) for item in list(values or []))


def _build_claim_support_temporal_handoff(intake_case_summary: Any) -> Dict[str, Any]:
    summary = intake_case_summary if isinstance(intake_case_summary, dict) else {}
    packet_summary = summary.get("claim_support_packet_summary")
    packet_summary = packet_summary if isinstance(packet_summary, dict) else {}
    alignment_tasks = summary.get("alignment_evidence_tasks")
    alignment_tasks = alignment_tasks if isinstance(alignment_tasks, list) else []

    unresolved_temporal_issue_ids = _dedupe_text_values(
        packet_summary.get("claim_support_unresolved_temporal_issue_ids") or []
    )
    event_ids: List[str] = []
    temporal_fact_ids: List[str] = []
    temporal_relation_ids: List[str] = []
    timeline_issue_ids: List[str] = []
    temporal_issue_ids: List[str] = []
    temporal_proof_bundle_ids: List[str] = []
    temporal_proof_objectives: List[str] = []

    for task in alignment_tasks:
        if not isinstance(task, dict):
            continue
        event_ids.extend(_dedupe_text_values(task.get("event_ids") or []))
        temporal_fact_ids.extend(_dedupe_text_values(task.get("temporal_fact_ids") or []))
        temporal_relation_ids.extend(_dedupe_text_values(task.get("temporal_relation_ids") or []))
        timeline_issue_ids.extend(_dedupe_text_values(task.get("timeline_issue_ids") or []))
        temporal_issue_ids.extend(_dedupe_text_values(task.get("temporal_issue_ids") or []))
        proof_bundle_id = str(task.get("temporal_proof_bundle_id") or "").strip()
        if proof_bundle_id:
            temporal_proof_bundle_ids.append(proof_bundle_id)
        proof_objective = str(task.get("temporal_proof_objective") or "").strip()
        if proof_objective:
            temporal_proof_objectives.append(proof_objective)

    temporal_handoff = {
        "unresolved_temporal_issue_count": int(
            packet_summary.get("claim_support_unresolved_temporal_issue_count", 0) or 0
        ),
        "unresolved_temporal_issue_ids": unresolved_temporal_issue_ids,
        "chronology_task_count": int(packet_summary.get("temporal_gap_task_count", 0) or 0),
        "event_ids": _dedupe_text_values(event_ids),
        "temporal_fact_ids": _dedupe_text_values(temporal_fact_ids),
        "temporal_relation_ids": _dedupe_text_values(temporal_relation_ids),
        "timeline_issue_ids": _dedupe_text_values(timeline_issue_ids),
        "temporal_issue_ids": _dedupe_text_values(temporal_issue_ids),
        "temporal_proof_bundle_ids": _dedupe_text_values(temporal_proof_bundle_ids),
        "temporal_proof_objectives": _dedupe_text_values(temporal_proof_objectives),
    }
    if not temporal_handoff["unresolved_temporal_issue_count"] and not any(
        temporal_handoff[key]
        for key in (
            "unresolved_temporal_issue_ids",
            "event_ids",
            "temporal_fact_ids",
            "temporal_relation_ids",
            "timeline_issue_ids",
            "temporal_issue_ids",
            "temporal_proof_bundle_ids",
            "temporal_proof_objectives",
        )
    ):
        return {}
    return temporal_handoff


class AgenticDocumentOptimizer:
    CRITIC_PROMPT_TAG = "[DOC_OPT_CRITIC]"
    ACTOR_PROMPT_TAG = "[DOC_OPT_ACTOR]"
    VALID_FOCUS_SECTIONS = {
        "factual_allegations",
        "claims_for_relief",
        "requested_relief",
        "affidavit",
        "certificate_of_service",
    }
    WORKFLOW_PHASE_FOCUS_ORDER = ("graph_analysis", "document_generation", "intake_questioning")
    WORKFLOW_PHASE_SECTION_CANDIDATES = {
        "graph_analysis": ("factual_allegations", "claims_for_relief"),
        "document_generation": ("claims_for_relief", "requested_relief", "affidavit", "certificate_of_service"),
        "intake_questioning": ("factual_allegations", "claims_for_relief", "requested_relief"),
    }
    _ACTOR_FIELD_TO_DRAFT_FIELD = {
        "factual_allegations": "factual_allegations",
        "claim_supporting_facts": "claim_supporting_facts",
        "claims_for_relief": "claims_for_relief",
        "requested_relief": "requested_relief",
        "affidavit_intro": "affidavit",
        "affidavit_facts": "affidavit",
        "affidavit_supporting_exhibits": "affidavit",
        "service_text": "certificate_of_service",
        "service_recipients": "certificate_of_service",
        "service_recipient_details": "certificate_of_service",
    }

    def __init__(
        self,
        mediator: Any,
        builder: Any = None,
        *,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        max_iterations: int = 2,
        target_score: float = 0.9,
        persist_artifacts: bool = False,
    ) -> None:
        self.mediator = mediator
        self.builder = builder
        self.provider = provider
        self.model_name = model_name
        self.max_iterations = max(1, int(max_iterations or 1))
        self.target_score = float(target_score or 0.9)
        self.persist_artifacts = bool(persist_artifacts)
        self.llm_config: Dict[str, Any] = {}
        self._embeddings_router = None
        self._embedding_cache: Dict[str, List[float]] = {}
        self._upstream_llm_router = None
        self._router_usage: Dict[str, Any] = {}
        self._stage_provider_selection: Dict[str, Dict[str, Any]] = {}

    def optimize(self, draft: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        result = self.optimize_draft(draft=draft, user_id=None, drafting_readiness={}, config={})
        return result.get("draft") or deepcopy(draft), result

    def optimize_draft(
        self,
        *,
        draft: Dict[str, Any],
        user_id: Optional[str] = None,
        drafting_readiness: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._reset_runtime_state()
        self._apply_config(config or {})
        working_draft = self._refresh_dependent_sections(deepcopy(draft))
        readiness = drafting_readiness or {}
        support_context = self._build_support_context(
            user_id=user_id,
            draft=working_draft,
            drafting_readiness=readiness,
        )
        initial_review = self._run_critic(
            draft=working_draft,
            drafting_readiness=readiness,
            support_context=support_context,
        )
        current_review = initial_review
        iterations: List[Dict[str, Any]] = []
        accepted_iterations = 0
        optimized_sections: List[str] = []

        for iteration in range(1, self.max_iterations + 1):
            if float(current_review.get("overall_score") or 0.0) >= self.target_score:
                break

            focus_section = self._choose_focus_section(
                current_review=current_review,
                draft=working_draft,
                drafting_readiness=readiness,
                support_context=support_context,
            )
            actor_payload = self._run_actor(
                draft=working_draft,
                critic_review=current_review,
                support_context=support_context,
                focus_section=focus_section,
            )
            candidate_draft = self._apply_actor_payload(
                draft=working_draft,
                actor_payload=actor_payload,
                focus_section=focus_section,
            )
            change_manifest = self._build_iteration_change_manifest(
                before_draft=working_draft,
                after_draft=candidate_draft,
                actor_payload=actor_payload,
                focus_section=focus_section,
            )
            candidate_review = self._run_critic(
                draft=candidate_draft,
                drafting_readiness=readiness,
                support_context=support_context,
            )
            accepted = float(candidate_review.get("overall_score") or 0.0) > float(current_review.get("overall_score") or 0.0)
            selected_support_context = self._select_support_context(
                focus_section=focus_section,
                draft=working_draft,
                support_context=support_context,
            )
            iterations.append(
                {
                    "iteration": iteration,
                    "focus_section": focus_section,
                    "accepted": accepted,
                    "critic": candidate_review,
                    "actor_payload": actor_payload,
                    "change_manifest": change_manifest,
                    "selected_support_context": selected_support_context,
                    "packet_projection": dict(support_context.get("packet_projection") or {}),
                }
            )
            if accepted:
                working_draft = candidate_draft
                current_review = candidate_review
                accepted_iterations += 1
                if focus_section not in optimized_sections:
                    optimized_sections.append(focus_section)

        upstream_optimizer = self._build_upstream_optimizer_metadata()
        intake_status = build_intake_status_summary(self.mediator)
        intake_constraints = build_intake_warning_entries(intake_status)
        intake_case_summary = build_intake_case_review_summary(self.mediator)
        claim_support_temporal_handoff = _build_claim_support_temporal_handoff(intake_case_summary)
        claim_reasoning_review = self._build_claim_reasoning_review(
            intake_case_summary=intake_case_summary,
            support_context=support_context,
            user_id=user_id,
        )
        intake_summary_handoff = {}
        if isinstance(intake_status.get("intake_summary_handoff"), dict) and intake_status.get("intake_summary_handoff"):
            intake_summary_handoff = dict(intake_status["intake_summary_handoff"])
        elif isinstance(intake_case_summary.get("intake_summary_handoff"), dict) and intake_case_summary.get("intake_summary_handoff"):
            intake_summary_handoff = dict(intake_case_summary["intake_summary_handoff"])
        trace_storage = self._store_trace(
            {
                "user_id": user_id or "",
                "config": {
                    "provider": self.provider or "",
                    "model_name": self.model_name or "",
                    "llm_config": self._sanitized_llm_config(),
                    "max_iterations": self.max_iterations,
                    "target_score": self.target_score,
                    "persist_artifacts": self.persist_artifacts,
                    "upstream_optimizer": upstream_optimizer,
                    "router_usage": self._router_usage_summary(),
                },
                "intake_status": intake_status,
                "intake_constraints": intake_constraints,
                "intake_case_summary": intake_case_summary,
                "intake_summary_handoff": intake_summary_handoff,
                "claim_support_temporal_handoff": claim_support_temporal_handoff,
                "claim_reasoning_review": claim_reasoning_review,
                "support_context": support_context,
                "initial_review": initial_review,
                "final_review": current_review,
                "iterations": iterations,
            }
        )
        return {
            "status": "optimized" if accepted_iterations else "completed",
            "method": "actor_mediator_critic_optimizer",
            "optimization_method": "actor_critic",
            "phase_focus_order": ["graph_analysis", "document_generation", "intake_questioning"],
            "optimizer_backend": "upstream_agentic" if UPSTREAM_AGENTIC_AVAILABLE else "local_fallback",
            "initial_score": float(initial_review.get("overall_score") or 0.0),
            "final_score": float(current_review.get("overall_score") or 0.0),
            "iteration_count": len(iterations),
            "accepted_iterations": accepted_iterations,
            "optimized_sections": optimized_sections,
            "artifact_cid": str(trace_storage.get("cid") or ""),
            "trace_storage": trace_storage,
            "router_status": self._router_status(),
            "router_usage": self._router_usage_summary(),
            "upstream_optimizer": upstream_optimizer,
            "intake_status": intake_status,
            "intake_constraints": intake_constraints,
            "intake_case_summary": intake_case_summary,
            "intake_summary_handoff": intake_summary_handoff,
            "claim_support_temporal_handoff": claim_support_temporal_handoff,
            "claim_reasoning_review": claim_reasoning_review,
            "packet_projection": dict(support_context.get("packet_projection") or {}),
            "section_history": [
                {
                    "iteration": int(entry.get("iteration") or 0),
                    "focus_section": str(entry.get("focus_section") or ""),
                    "accepted": bool(entry.get("accepted")),
                    "overall_score": float((entry.get("critic") or {}).get("overall_score") or 0.0),
                    "critic_llm_metadata": dict((entry.get("critic") or {}).get("llm_metadata") or {}),
                    "actor_llm_metadata": dict((entry.get("actor_payload") or {}).get("llm_metadata") or {}),
                    "change_manifest": list(entry.get("change_manifest") or []),
                    "selected_support_context": dict(entry.get("selected_support_context") or {}),
                }
                for entry in iterations
            ],
            "initial_review": self._serialize_review(initial_review),
            "final_review": self._serialize_review(current_review),
            "draft": working_draft,
        }

    def _reset_runtime_state(self) -> None:
        self._embeddings_router = None
        self._embedding_cache = {}
        self._upstream_llm_router = None
        self._stage_provider_selection = {}
        self._router_usage = {
            "llm_calls": 0,
            "critic_calls": 0,
            "actor_calls": 0,
            "embedding_requests": 0,
            "embedding_cache_hits": 0,
            "embedding_rankings": 0,
            "ranked_candidate_count": 0,
            "ipfs_store_attempted": False,
            "ipfs_store_succeeded": False,
            "llm_providers_used": [],
        }

    def _apply_config(self, config: Dict[str, Any]) -> None:
        provider = config.get("llm_provider") or config.get("provider")
        model_name = config.get("llm_model_name") or config.get("model_name")
        max_iterations = config.get("max_iterations")
        target_score = config.get("target_score")
        persist_artifacts = config.get("use_ipfs")
        if persist_artifacts is None:
            persist_artifacts = config.get("persist_artifacts")
        llm_config = config.get("llm_config") or config.get("optimization_llm_config")

        if provider is not None:
            self.provider = str(provider or "").strip() or None
        if model_name is not None:
            self.model_name = str(model_name or "").strip() or None
        if max_iterations is not None:
            self.max_iterations = max(1, int(max_iterations or 1))
        if target_score is not None:
            self.target_score = float(target_score or self.target_score)
        if persist_artifacts is not None:
            self.persist_artifacts = bool(persist_artifacts)
        if isinstance(llm_config, dict):
            self.llm_config = {str(key): value for key, value in llm_config.items()}

    def _build_support_context(
        self,
        *,
        user_id: Optional[str],
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
    ) -> Dict[str, Any]:
        claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
        claim_entries = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []
        readiness_by_claim = {}
        for entry in claim_entries:
            if not isinstance(entry, dict):
                continue
            claim_type = str(entry.get("claim_type") or "").strip()
            if claim_type:
                readiness_by_claim[claim_type] = entry

        support_summary_payload = self._call_mediator("summarize_claim_support", user_id=user_id) or {}
        support_summary_claims = support_summary_payload.get("claims") if isinstance(support_summary_payload, dict) else {}
        support_summary_claims = support_summary_claims if isinstance(support_summary_claims, dict) else {}

        evidence_rows = self._call_mediator("get_user_evidence", user_id=user_id) or []
        evidence_summaries = []
        for row in evidence_rows if isinstance(evidence_rows, list) else []:
            if not isinstance(row, dict):
                continue
            text = str(row.get("parsed_text_preview") or row.get("description") or row.get("title") or "").strip()
            if not text:
                continue
            evidence_summaries.append(
                {
                    "claim_type": str(row.get("claim_type") or "").strip(),
                    "text": text,
                    "cid": str(row.get("cid") or "").strip(),
                    "type": str(row.get("type") or "").strip(),
                }
            )

        claim_contexts = []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get("claim_type") or claim.get("count_title") or "").strip()
            support_facts = self._call_mediator("get_claim_support_facts", claim_type=claim_type, user_id=user_id) or []
            overview = self._call_mediator("get_claim_overview", claim_type=claim_type, user_id=user_id) or {}
            overview_claim = {}
            if isinstance(overview, dict):
                overview_claims = overview.get("claims") if isinstance(overview.get("claims"), dict) else {}
                overview_claim = overview_claims.get(claim_type) if isinstance(overview_claims.get(claim_type), dict) else {}
            support_summary = support_summary_claims.get(claim_type) if isinstance(support_summary_claims.get(claim_type), dict) else {}
            readiness_entry = readiness_by_claim.get(claim_type, {})
            support_texts = self._extract_support_texts(support_facts)
            claim_contexts.append(
                {
                    "claim_type": claim_type,
                    "missing_elements": self._extract_element_texts(overview_claim.get("missing")),
                    "partially_supported_elements": self._extract_element_texts(overview_claim.get("partially_supported")),
                    "support_summary": {
                        "total_elements": int(support_summary.get("total_elements") or claim.get("support_summary", {}).get("total_elements") or 0),
                        "covered_elements": int(support_summary.get("covered_elements") or claim.get("support_summary", {}).get("covered_elements") or 0),
                        "uncovered_elements": int(support_summary.get("uncovered_elements") or claim.get("support_summary", {}).get("uncovered_elements") or 0),
                        "source_family_counts": dict(support_summary.get("support_packet_summary", {}).get("source_family_counts") or claim.get("support_summary", {}).get("source_family_counts") or {}),
                    },
                    "support_facts": support_texts[:8],
                    "readiness_warnings": [
                        str(item.get("message") or "").strip()
                        for item in readiness_entry.get("warnings", [])
                        if isinstance(item, dict) and str(item.get("message") or "").strip()
                    ],
                }
            )

        intake_status = build_intake_status_summary(self.mediator)
        intake_handoff = intake_status.get("intake_summary_handoff") if isinstance(intake_status, dict) else {}
        intake_handoff = intake_handoff if isinstance(intake_handoff, dict) else {}
        confirmation = (
            intake_handoff.get("complainant_summary_confirmation")
            if isinstance(intake_handoff.get("complainant_summary_confirmation"), dict)
            else {}
        )
        confirmation_snapshot = (
            confirmation.get("confirmed_summary_snapshot")
            if isinstance(confirmation.get("confirmed_summary_snapshot"), dict)
            else {}
        )
        intake_priority_summary = (
            confirmation_snapshot.get("adversarial_intake_priority_summary")
            if isinstance(confirmation_snapshot.get("adversarial_intake_priority_summary"), dict)
            else {}
        )

        covered_objectives = _normalize_intake_objectives(intake_priority_summary.get("covered_objectives") or [])
        uncovered_objectives = _normalize_intake_objectives(intake_priority_summary.get("uncovered_objectives") or [])
        objective_question_counts = {
            _normalize_intake_objective(key): int(value or 0)
            for key, value in dict(intake_priority_summary.get("objective_question_counts") or {}).items()
            if _normalize_intake_objective(key)
        }
        objective_question_counts = {
            key: value
            for key, value in objective_question_counts.items()
            if key
        }
        unresolved_objectives = _dedupe_text_values(
            list(uncovered_objectives)
            + [key for key, count in objective_question_counts.items() if count <= 0]
        )
        critical_unresolved = [
            objective
            for objective in _INTAKE_OBJECTIVE_PRIORITY
            if objective in unresolved_objectives
        ]

        return {
            "claims": claim_contexts,
            "evidence": evidence_summaries[:10],
            "sections": dict(drafting_readiness.get("sections") or {}) if isinstance(drafting_readiness, dict) else {},
            "packet_projection": self._build_packet_projection(draft),
            "intake_priorities": {
                "covered_objectives": covered_objectives,
                "uncovered_objectives": uncovered_objectives,
                "objective_question_counts": objective_question_counts,
                "unresolved_objectives": unresolved_objectives,
                "critical_unresolved_objectives": critical_unresolved,
                "recommended_follow_up_prompts": [
                    _OBJECTIVE_PROMPTS[objective]
                    for objective in critical_unresolved
                    if objective in _OBJECTIVE_PROMPTS
                ],
            },
            "capabilities": self._router_status(),
        }

    def _build_claim_reasoning_review(
        self,
        *,
        intake_case_summary: Dict[str, Any],
        support_context: Dict[str, Any],
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        existing_review = intake_case_summary.get("claim_reasoning_review")
        if isinstance(existing_review, dict) and existing_review:
            return dict(existing_review)

        claim_types = _unique_preserving_order(
            [
                *[
                    str((claim or {}).get("claim_type") or "")
                    for claim in (intake_case_summary.get("candidate_claims") or [])
                    if isinstance(claim, dict)
                ],
                *[
                    str((claim or {}).get("claim_type") or "")
                    for claim in (support_context.get("claims") or [])
                    if isinstance(claim, dict)
                ],
            ]
        )
        review_by_claim: Dict[str, Any] = {}
        for claim_type in claim_types:
            validation_payload = self._call_mediator(
                "get_claim_support_validation",
                claim_type=claim_type,
                user_id=user_id,
            )
            if not isinstance(validation_payload, dict):
                continue
            validation_claims = validation_payload.get("claims")
            validation_claims = validation_claims if isinstance(validation_claims, dict) else {}
            validation_claim = validation_claims.get(claim_type)
            if not isinstance(validation_claim, dict) or not validation_claim:
                continue
            review_by_claim[claim_type] = summarize_claim_reasoning_review(validation_claim)
        return review_by_claim

    def _run_critic(
        self,
        *,
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        heuristic_review = self._heuristic_review(
            draft=draft,
            drafting_readiness=drafting_readiness,
            support_context=support_context,
        )
        if not LLM_ROUTER_AVAILABLE:
            return heuristic_review

        payload, provider_selection = self._generate_llm_payload(
            prompt=(
                f"{self.CRITIC_PROMPT_TAG}\n"
                f"{json.dumps({'draft': draft, 'drafting_readiness': drafting_readiness, 'support_context': support_context, 'heuristic_review': heuristic_review}, ensure_ascii=True, default=str)}"
            ),
            role="critic",
            focus_section=str(heuristic_review.get("recommended_focus") or "factual_allegations"),
        )
        text = payload.get("text") if isinstance(payload, dict) else payload
        parsed = self._parse_json_payload(text)
        merged = self._merge_review_payload(parsed, heuristic_review)
        llm_metadata = self._extract_llm_metadata(payload)
        if provider_selection:
            llm_metadata.update(
                {
                    "optimizer_provider_source": provider_selection.get("source") or "",
                    "optimizer_provider_name": provider_selection.get("resolved_provider") or "",
                    "optimizer_task_complexity": provider_selection.get("complexity") or "",
                }
            )
        if llm_metadata:
            merged["llm_metadata"] = llm_metadata
        return merged

    def _run_actor(
        self,
        *,
        draft: Dict[str, Any],
        critic_review: Dict[str, Any],
        support_context: Dict[str, Any],
        focus_section: str,
    ) -> Dict[str, Any]:
        selected_support_context = self._select_support_context(
            focus_section=focus_section,
            draft=draft,
            support_context=support_context,
        )
        fallback_payload = self._build_fallback_actor_payload(
            draft=draft,
            focus_section=focus_section,
            support_context=selected_support_context,
        )
        if not LLM_ROUTER_AVAILABLE:
            return fallback_payload

        payload, provider_selection = self._generate_llm_payload(
            prompt=(
                f"{self.ACTOR_PROMPT_TAG}\n"
                f"{json.dumps({'focus_section': focus_section, 'draft': draft, 'critic_review': critic_review, 'support_context': selected_support_context, 'fallback_payload': fallback_payload}, ensure_ascii=True, default=str)}"
            ),
            role="actor",
            focus_section=focus_section,
        )
        text = payload.get("text") if isinstance(payload, dict) else payload
        parsed = self._parse_json_payload(text) or {}
        if "focus_section" not in parsed:
            parsed["focus_section"] = focus_section
        merged = {**fallback_payload, **parsed}
        llm_metadata = self._extract_llm_metadata(payload)
        if provider_selection:
            llm_metadata.update(
                {
                    "optimizer_provider_source": provider_selection.get("source") or "",
                    "optimizer_provider_name": provider_selection.get("resolved_provider") or "",
                    "optimizer_task_complexity": provider_selection.get("complexity") or "",
                }
            )
        if llm_metadata:
            merged["llm_metadata"] = llm_metadata
        return merged

    def _generate_llm_payload(
        self,
        *,
        prompt: str,
        role: str,
        focus_section: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        provider_name, provider_selection = self._resolve_stage_provider(
            role=role,
            focus_section=focus_section,
        )
        self._router_usage["llm_calls"] = int(self._router_usage.get("llm_calls") or 0) + 1
        counter_key = f"{role}_calls"
        self._router_usage[counter_key] = int(self._router_usage.get(counter_key) or 0) + 1
        providers_used = list(self._router_usage.get("llm_providers_used") or [])
        if provider_name and provider_name not in providers_used:
            providers_used.append(provider_name)
        self._router_usage["llm_providers_used"] = providers_used
        payload = generate_text_with_metadata(
            prompt,
            provider=provider_name,
            model_name=self.model_name,
            **self.llm_config,
        )
        return payload if isinstance(payload, dict) else {"text": str(payload or "")}, provider_selection

    def _resolve_stage_provider(self, *, role: str, focus_section: str) -> Tuple[Optional[str], Dict[str, Any]]:
        explicit_provider = str(self.provider or "").strip()
        complexity = self._stage_complexity(role=role, focus_section=focus_section)
        if explicit_provider and explicit_provider.lower() not in {"auto", "optimizer_auto", "upstream_agentic"}:
            selection = {
                "source": "user_config",
                "resolved_provider": explicit_provider,
                "complexity": complexity,
                "role": role,
                "focus_section": focus_section,
            }
            self._stage_provider_selection[role] = selection
            return explicit_provider, selection

        router = self._get_upstream_llm_router()
        method = getattr(OptimizationMethod, "ACTOR_CRITIC", None)
        if router is None or method is None:
            selection = {
                "source": "default",
                "resolved_provider": explicit_provider,
                "complexity": complexity,
                "role": role,
                "focus_section": focus_section,
            }
            self._stage_provider_selection[role] = selection
            return explicit_provider or None, selection

        try:
            selected_provider = router.select_provider(method, complexity=complexity)
        except Exception:
            selection = {
                "source": "default",
                "resolved_provider": explicit_provider,
                "complexity": complexity,
                "role": role,
                "focus_section": focus_section,
            }
            self._stage_provider_selection[role] = selection
            return explicit_provider or None, selection

        resolved_provider = self._normalize_optimizer_provider(getattr(selected_provider, "value", selected_provider))
        selection = {
            "source": "upstream_optimizer",
            "resolved_provider": resolved_provider,
            "complexity": complexity,
            "role": role,
            "focus_section": focus_section,
        }
        self._stage_provider_selection[role] = selection
        return resolved_provider, selection

    def _stage_complexity(self, *, role: str, focus_section: str) -> str:
        if role == "critic":
            return "complex"
        if focus_section in {"claims_for_relief", "affidavit"}:
            return "complex"
        if focus_section == "certificate_of_service":
            return "simple"
        return "medium"

    def _normalize_optimizer_provider(self, value: Any) -> Optional[str]:
        text = str(value or "").strip().lower()
        if not text:
            return None
        mapping = {
            "claude": "anthropic",
            "gpt4": "openai",
            "codex": "codex",
            "copilot": "copilot",
            "gemini": "gemini",
            "local": "accelerate",
            "accelerate": "accelerate",
            "openai": "openai",
            "anthropic": "anthropic",
        }
        return mapping.get(text, text)

    def _get_upstream_llm_router(self) -> Any:
        if not UPSTREAM_AGENTIC_AVAILABLE or OptimizerLLMRouter is None:
            return None
        if self._upstream_llm_router is None:
            try:
                self._upstream_llm_router = OptimizerLLMRouter(enable_tracking=False, enable_caching=True)
            except Exception:
                self._upstream_llm_router = None
        return self._upstream_llm_router

    def _apply_actor_payload(
        self,
        *,
        draft: Dict[str, Any],
        actor_payload: Dict[str, Any],
        focus_section: str,
    ) -> Dict[str, Any]:
        updated = deepcopy(draft)
        factual_allegations = actor_payload.get("factual_allegations")
        if isinstance(factual_allegations, list):
            updated["factual_allegations"] = self._normalize_lines(factual_allegations)

        claims_for_relief = actor_payload.get("claims_for_relief")
        if isinstance(claims_for_relief, list):
            existing_claims = updated.get("claims_for_relief") if isinstance(updated.get("claims_for_relief"), list) else []
            updated["claims_for_relief"] = self._normalize_claims_for_relief(claims_for_relief, existing_claims)

        claim_supporting_facts = actor_payload.get("claim_supporting_facts")
        if isinstance(claim_supporting_facts, dict):
            claims = updated.get("claims_for_relief") if isinstance(updated.get("claims_for_relief"), list) else []
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                claim_type = str(claim.get("claim_type") or "").strip()
                payload_facts = claim_supporting_facts.get(claim_type)
                if isinstance(payload_facts, list):
                    claim["supporting_facts"] = self._normalize_lines(payload_facts)

        requested_relief = actor_payload.get("requested_relief")
        if isinstance(requested_relief, list):
            updated["requested_relief"] = self._normalize_lines(requested_relief)

        if focus_section == "affidavit" or any(
            key in actor_payload for key in ("affidavit_intro", "affidavit_facts", "affidavit_supporting_exhibits")
        ):
            overrides = updated.get("affidavit_overrides") if isinstance(updated.get("affidavit_overrides"), dict) else {}
            updated["affidavit_overrides"] = overrides
            if actor_payload.get("affidavit_intro"):
                overrides["intro"] = str(actor_payload.get("affidavit_intro") or "").strip()
            if isinstance(actor_payload.get("affidavit_facts"), list):
                overrides["facts"] = self._normalize_affidavit_facts(actor_payload.get("affidavit_facts") or [])
            if isinstance(actor_payload.get("affidavit_supporting_exhibits"), list):
                overrides["supporting_exhibits"] = self._normalize_exhibits(actor_payload.get("affidavit_supporting_exhibits") or [])

        if focus_section == "certificate_of_service" or any(
            key in actor_payload for key in ("service_text", "service_recipients", "service_recipient_details")
        ):
            certificate = updated.get("certificate_of_service") if isinstance(updated.get("certificate_of_service"), dict) else {}
            updated["certificate_of_service"] = certificate
            if actor_payload.get("service_text"):
                certificate["text"] = str(actor_payload.get("service_text") or "").strip()
            if isinstance(actor_payload.get("service_recipients"), list):
                certificate["recipients"] = self._normalize_lines(actor_payload.get("service_recipients") or [])
            if isinstance(actor_payload.get("service_recipient_details"), list):
                details = self._normalize_service_recipient_details(actor_payload.get("service_recipient_details") or [])
                certificate["recipient_details"] = details
                certificate["detail_lines"] = [self._format_service_recipient_detail(detail) for detail in details]
                if details and not certificate.get("recipients"):
                    certificate["recipients"] = _unique_preserving_order(detail.get("recipient") for detail in details)

        return self._refresh_dependent_sections(updated)

    def _build_iteration_change_manifest(
        self,
        *,
        before_draft: Dict[str, Any],
        after_draft: Dict[str, Any],
        actor_payload: Dict[str, Any],
        focus_section: str,
    ) -> List[Dict[str, Any]]:
        tracked_fields = self._resolve_tracked_fields(focus_section=focus_section, actor_payload=actor_payload)
        manifest: List[Dict[str, Any]] = []
        for field_name in tracked_fields:
            before_value = self._extract_manifest_value(before_draft, field_name)
            after_value = self._extract_manifest_value(after_draft, field_name)
            if _stable_json(before_value) == _stable_json(after_value):
                continue
            before_count, before_preview = self._summarize_manifest_value(field_name, before_value)
            after_count, after_preview = self._summarize_manifest_value(field_name, after_value)
            manifest.append(
                {
                    "field": field_name,
                    "change_type": self._classify_manifest_change(before_count, after_count),
                    "before_count": before_count,
                    "after_count": after_count,
                    "before_preview": before_preview,
                    "after_preview": after_preview,
                    **self._build_manifest_delta_details(field_name, before_value, after_value),
                }
            )

        if manifest:
            return manifest

        fallback_count, fallback_preview = self._summarize_manifest_value(
            focus_section,
            self._extract_manifest_value(after_draft, focus_section),
        )
        return [
            {
                "field": focus_section,
                "change_type": "no_effect",
                "before_count": fallback_count,
                "after_count": fallback_count,
                "before_preview": fallback_preview,
                "after_preview": fallback_preview,
            }
        ]

    def _resolve_tracked_fields(self, *, focus_section: str, actor_payload: Dict[str, Any]) -> List[str]:
        tracked_fields: List[str] = []
        if focus_section in self.VALID_FOCUS_SECTIONS:
            tracked_fields.append(focus_section)
        for key in actor_payload:
            mapped_field = self._ACTOR_FIELD_TO_DRAFT_FIELD.get(key)
            if mapped_field and mapped_field not in tracked_fields:
                tracked_fields.append(mapped_field)
        return tracked_fields

    def _extract_manifest_value(self, draft: Dict[str, Any], field_name: str) -> Any:
        if field_name == "claim_supporting_facts":
            claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
            supporting_facts: Dict[str, List[str]] = {}
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                claim_type = str(claim.get("claim_type") or "").strip()
                if not claim_type:
                    continue
                supporting_facts[claim_type] = self._normalize_lines(claim.get("supporting_facts") or [])
            return supporting_facts
        if field_name in {"affidavit", "certificate_of_service"}:
            return deepcopy(draft.get(field_name) or {})
        if field_name in {"factual_allegations", "requested_relief"}:
            return list(draft.get(field_name) or []) if isinstance(draft.get(field_name), list) else []
        if field_name == "claims_for_relief":
            claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
            return [deepcopy(claim) for claim in claims if isinstance(claim, dict)]
        return deepcopy(draft.get(field_name))

    def _build_manifest_delta_details(self, field_name: str, before_value: Any, after_value: Any) -> Dict[str, List[str]]:
        if field_name == "claims_for_relief":
            return self._build_claims_for_relief_delta(before_value, after_value)
        if field_name == "claim_supporting_facts":
            return self._build_claim_supporting_facts_delta(before_value, after_value)
        if field_name == "requested_relief":
            return self._build_list_delta(before_value, after_value)
        return self._build_generic_delta(before_value, after_value)

    def _summarize_manifest_value(self, field_name: str, value: Any) -> Tuple[int, List[str]]:
        if field_name == "claim_supporting_facts":
            if not isinstance(value, dict):
                return 0, []
            total = 0
            preview: List[str] = []
            for claim_type, facts in value.items():
                normalized_facts = self._normalize_lines(facts or []) if isinstance(facts, list) else []
                total += len(normalized_facts)
                if normalized_facts:
                    preview.append(f"{claim_type}: {normalized_facts[0]}")
                else:
                    preview.append(f"{claim_type}: 0 facts")
            return total, preview[:3]
        if field_name == "claims_for_relief":
            claims = value if isinstance(value, list) else []
            preview = []
            for claim in claims[:3]:
                if not isinstance(claim, dict):
                    continue
                claim_label = str(claim.get("claim_type") or claim.get("title") or "Claim").strip() or "Claim"
                fact_count = len(self._normalize_lines(claim.get("supporting_facts") or []))
                preview.append(f"{claim_label} ({fact_count} facts)")
            return len(claims), preview
        if field_name == "affidavit":
            affidavit = value if isinstance(value, dict) else {}
            facts = self._normalize_lines(affidavit.get("facts") or [])
            exhibits = self._normalize_lines(affidavit.get("supporting_exhibits") or [])
            preview = []
            if str(affidavit.get("intro") or "").strip():
                preview.append("intro updated")
            preview.extend(facts[:2])
            if exhibits:
                preview.append(f"{len(exhibits)} exhibits")
            count = len(facts) + len(exhibits) + int(bool(str(affidavit.get("intro") or "").strip()))
            return count, preview[:3]
        if field_name == "certificate_of_service":
            certificate = value if isinstance(value, dict) else {}
            recipients = self._normalize_lines(certificate.get("recipients") or [])
            details = certificate.get("recipient_details") if isinstance(certificate.get("recipient_details"), list) else []
            preview = list(recipients[:2])
            if details:
                preview.append(f"{len(details)} recipient details")
            count = len(recipients) + len(details) + int(bool(str(certificate.get("text") or "").strip()))
            return count, preview[:3]
        if isinstance(value, list):
            preview = []
            for entry in value[:3]:
                if isinstance(entry, dict):
                    preview.append(
                        str(entry.get("title") or entry.get("claim_type") or entry.get("label") or entry.get("summary") or entry.get("text") or "").strip()
                    )
                else:
                    preview.append(str(entry or "").strip())
            return len(value), [entry for entry in preview if entry]
        if isinstance(value, dict):
            preview = []
            for inner_key, inner_value in list(value.items())[:3]:
                if isinstance(inner_value, list):
                    preview.append(f"{inner_key}: {len(inner_value)}")
                else:
                    preview.append(f"{inner_key}: updated")
            return len(value), preview
        text = str(value or "").strip()
        return (1, [text[:120]]) if text else (0, [])

    def _classify_manifest_change(self, before_count: int, after_count: int) -> str:
        if before_count <= 0 and after_count > 0:
            return "added"
        if before_count > 0 and after_count <= 0:
            return "removed"
        if after_count > before_count:
            return "expanded"
        if after_count < before_count:
            return "trimmed"
        return "updated"

    def _build_claims_for_relief_delta(self, before_value: Any, after_value: Any) -> Dict[str, List[str]]:
        before_claims = before_value if isinstance(before_value, list) else []
        after_claims = after_value if isinstance(after_value, list) else []
        before_by_key = {self._claim_key(claim): claim for claim in before_claims if isinstance(claim, dict) and self._claim_key(claim)}
        after_by_key = {self._claim_key(claim): claim for claim in after_claims if isinstance(claim, dict) and self._claim_key(claim)}
        added_items = [self._summarize_claim_entry(after_by_key[key]) for key in sorted(after_by_key.keys() - before_by_key.keys())]
        removed_items = [self._summarize_claim_entry(before_by_key[key]) for key in sorted(before_by_key.keys() - after_by_key.keys())]
        changed_items: List[str] = []
        for key in sorted(before_by_key.keys() & after_by_key.keys()):
            before_claim = before_by_key[key]
            after_claim = after_by_key[key]
            if _stable_json(before_claim) == _stable_json(after_claim):
                continue
            changed_items.append(
                f"{self._claim_label(after_claim)} supporting facts {len(self._normalize_lines(before_claim.get('supporting_facts') or []))} -> {len(self._normalize_lines(after_claim.get('supporting_facts') or []))}"
            )
        return {
            "added_items": added_items[:4],
            "removed_items": removed_items[:4],
            "changed_items": changed_items[:4],
        }

    def _build_claim_supporting_facts_delta(self, before_value: Any, after_value: Any) -> Dict[str, List[str]]:
        before_map = before_value if isinstance(before_value, dict) else {}
        after_map = after_value if isinstance(after_value, dict) else {}
        added_items: List[str] = []
        removed_items: List[str] = []
        changed_items: List[str] = []
        for claim_type in sorted(after_map.keys() - before_map.keys()):
            added_items.append(f"{claim_type}: {len(self._normalize_lines(after_map.get(claim_type) or []))} facts")
        for claim_type in sorted(before_map.keys() - after_map.keys()):
            removed_items.append(f"{claim_type}: {len(self._normalize_lines(before_map.get(claim_type) or []))} facts")
        for claim_type in sorted(before_map.keys() & after_map.keys()):
            before_facts = self._normalize_lines(before_map.get(claim_type) or [])
            after_facts = self._normalize_lines(after_map.get(claim_type) or [])
            if _stable_json(before_facts) == _stable_json(after_facts):
                continue
            changed_items.append(f"{claim_type}: facts {len(before_facts)} -> {len(after_facts)}")
        return {
            "added_items": added_items[:4],
            "removed_items": removed_items[:4],
            "changed_items": changed_items[:4],
        }

    def _build_list_delta(self, before_value: Any, after_value: Any) -> Dict[str, List[str]]:
        before_items = self._normalize_lines(before_value or []) if isinstance(before_value, list) else []
        after_items = self._normalize_lines(after_value or []) if isinstance(after_value, list) else []
        before_lookup = {item.lower(): item for item in before_items}
        after_lookup = {item.lower(): item for item in after_items}
        added_items = [after_lookup[key] for key in sorted(after_lookup.keys() - before_lookup.keys())]
        removed_items = [before_lookup[key] for key in sorted(before_lookup.keys() - after_lookup.keys())]
        return {
            "added_items": added_items[:4],
            "removed_items": removed_items[:4],
            "changed_items": [],
        }

    def _build_generic_delta(self, before_value: Any, after_value: Any) -> Dict[str, List[str]]:
        if isinstance(before_value, list) and isinstance(after_value, list):
            return self._build_list_delta(before_value, after_value)
        return {
            "added_items": [],
            "removed_items": [],
            "changed_items": [],
        }

    def _claim_key(self, claim: Dict[str, Any]) -> str:
        return str(claim.get("claim_type") or claim.get("count_title") or "").strip().lower()

    def _claim_label(self, claim: Dict[str, Any]) -> str:
        return str(claim.get("claim_type") or claim.get("count_title") or "Claim").strip() or "Claim"

    def _summarize_claim_entry(self, claim: Dict[str, Any]) -> str:
        label = self._claim_label(claim)
        fact_count = len(self._normalize_lines(claim.get("supporting_facts") or []))
        return f"{label} ({fact_count} facts)"

    def _heuristic_review(
        self,
        *,
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        factual_allegations = self._normalize_lines(draft.get("factual_allegations") or draft.get("summary_of_facts") or [])
        claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
        affidavit = draft.get("affidavit") if isinstance(draft.get("affidavit"), dict) else {}
        certificate = draft.get("certificate_of_service") if isinstance(draft.get("certificate_of_service"), dict) else {}
        exhibits = draft.get("exhibits") if isinstance(draft.get("exhibits"), list) else []

        section_scores = {
            "factual_allegations": self._score_factual_allegations(factual_allegations, claims),
            "claims_for_relief": self._score_claims_section(claims, support_context),
            "requested_relief": self._score_requested_relief_section(
                self._normalize_lines(draft.get("requested_relief") or []),
                claims,
                drafting_readiness,
            ),
            "affidavit": self._score_affidavit_section(affidavit, exhibits),
            "certificate_of_service": self._score_certificate_section(certificate),
            "packet_projection": self._score_packet_projection(
                support_context.get("packet_projection") if isinstance(support_context.get("packet_projection"), dict) else {}
            ),
            "intake_questioning": self._score_intake_questioning(
                factual_allegations=factual_allegations,
                support_context=support_context,
            ),
        }
        ordered_sections = sorted(
            ((name, score) for name, score in section_scores.items() if name in self.VALID_FOCUS_SECTIONS),
            key=lambda item: item[1],
        )
        workflow_phase_targeting = self._build_workflow_phase_targeting(
            section_scores=section_scores,
            support_context=support_context,
        )
        phase_focus_order = list(workflow_phase_targeting.get("phase_focus_order") or self.WORKFLOW_PHASE_FOCUS_ORDER)
        phase_target_sections = dict(workflow_phase_targeting.get("phase_target_sections") or {})
        prioritized_phase = str(phase_focus_order[0] if phase_focus_order else "graph_analysis")
        recommended_focus = str(
            phase_target_sections.get(prioritized_phase)
            or (ordered_sections[0][0] if ordered_sections else "factual_allegations")
        )

        weaknesses: List[str] = []
        suggestions: List[str] = []
        for section_name, score in ordered_sections:
            if score >= 0.8:
                continue
            if section_name == "factual_allegations":
                weaknesses.append("Factual allegations should read like pleading-ready declarative paragraphs grounded in the support record.")
                suggestions.append("Rewrite factual allegations into short declarative prose anchored to the support packet.")
            elif section_name == "claims_for_relief":
                weaknesses.append("Claims for relief still contain support gaps or thin claim-specific fact statements.")
                suggestions.append("Backfill claim-specific support facts for the weakest claim before rendering artifacts.")
            elif section_name == "requested_relief":
                weaknesses.append("Requested relief is incomplete or does not yet reflect the remedies supported by the current claim record.")
                suggestions.append("Confirm the prayer for relief includes the concrete damages, equitable remedies, and injunctive terms supported by the packet.")
            elif section_name == "affidavit":
                weaknesses.append("The affidavit is missing completeness or exhibit-consistency signals needed for a filing-ready packet.")
                suggestions.append("Revise affidavit facts and mirrored exhibit support so the affidavit matches the complaint record.")
            elif section_name == "certificate_of_service":
                weaknesses.append("The certificate of service is thin on recipient detail or service metadata.")
                suggestions.append("Add structured recipient details and method-specific service language before export.")

        intake_questioning_score = float(section_scores.get("intake_questioning") or 0.0)
        intake_priorities = support_context.get("intake_priorities") if isinstance(support_context.get("intake_priorities"), dict) else {}
        unresolved_objectives = [
            str(item).strip()
            for item in list(intake_priorities.get("critical_unresolved_objectives") or [])
            if str(item).strip()
        ]
        if intake_questioning_score < 0.75:
            weaknesses.append(
                "Intake follow-up detail is missing closure on key blockers (exact dates, staff names/titles, hearing-request timing, response dates, and protected-activity-to-adverse-action causation)."
            )
            if unresolved_objectives:
                objective_labels = ", ".join(unresolved_objectives[:5])
                suggestions.append(
                    f"Ask targeted follow-up questions to close unresolved intake objectives: {objective_labels}."
                )
            suggestions.append(
                "Ask targeted follow-up questions to lock dates, each HACC actor decision, hearing and response timing, and direct causation facts linking protected activity to adverse treatment."
            )

        readiness_status = str(drafting_readiness.get("status") or "ready").strip().lower()
        procedural_score = 0.95 if readiness_status == "ready" else 0.75 if readiness_status == "warning" else 0.45
        completeness_score = sum(section_scores.values()) / max(len(section_scores), 1)
        grounding_score = self._score_grounding(support_context)
        coherence_score = self._score_coherence(factual_allegations)
        renderability_score = (
            section_scores["affidavit"]
            + section_scores["certificate_of_service"]
            + section_scores["packet_projection"]
        ) / 3.0

        overall_score = _clamp(
            (completeness_score * 0.35)
            + (grounding_score * 0.2)
            + (coherence_score * 0.2)
            + (procedural_score * 0.15)
            + (renderability_score * 0.1)
        )
        strengths = []
        if support_context.get("claims"):
            strengths.append("Support packets are available.")
        if section_scores["affidavit"] >= 0.85:
            strengths.append("Affidavit content is structurally complete.")
        if section_scores["certificate_of_service"] >= 0.85:
            strengths.append("Service metadata is present for export.")
        if section_scores["packet_projection"] >= 0.85:
            strengths.append("Render-target packet projection is structurally complete.")
        if section_scores["intake_questioning"] >= 0.85:
            strengths.append("Intake questioning captures timeline, actor, and causation anchors.")

        return {
            "overall_score": overall_score,
            "dimension_scores": {
                "completeness": completeness_score,
                "grounding": grounding_score,
                "coherence": coherence_score,
                "procedural": procedural_score,
                "renderability": renderability_score,
            },
            "section_scores": section_scores,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "suggestions": suggestions,
            "recommended_focus": recommended_focus,
            "workflow_phase_order": phase_focus_order,
            "workflow_phase_scores": dict(workflow_phase_targeting.get("phase_scores") or {}),
            "workflow_phase_target_sections": phase_target_sections,
            "prioritized_workflow_phase": prioritized_phase,
        }

    def _score_factual_allegations(self, allegations: List[str], claims: List[Dict[str, Any]]) -> float:
        base = min(len(allegations), 4) / 4.0
        claim_support_count = 0
        for claim in claims:
            if isinstance(claim, dict) and claim.get("supporting_facts"):
                claim_support_count += 1
        support_bonus = min(claim_support_count, 3) / 6.0
        variety_bonus = 0.15 if len({text.lower() for text in allegations}) == len(allegations) else 0.0
        date_anchor_bonus = 0.08 if any(_contains_date_anchor(text) for text in allegations) else 0.0
        actor_bonus = 0.07 if any(_contains_actor_marker(text) for text in allegations) else 0.0
        causation_bonus = 0.1 if any(_contains_causation_link(text) for text in allegations) else 0.0
        lowered_allegations = " ".join(text.lower() for text in allegations)
        hearing_timing_bonus = 0.04 if any(token in lowered_allegations for token in ("hearing request", "review request", "requested a hearing")) else 0.0
        response_date_bonus = 0.04 if any(token in lowered_allegations for token in ("response date", "responded on", "decision date", "hearing outcome date")) else 0.0
        sequencing_bonus = 0.04 if any(token in lowered_allegations for token in ("days after", "weeks after", "shortly after", "within")) else 0.0
        return _clamp(
            base * 0.5
            + support_bonus
            + variety_bonus
            + date_anchor_bonus
            + actor_bonus
            + causation_bonus
            + hearing_timing_bonus
            + response_date_bonus
            + sequencing_bonus
        )

    def _score_claims_section(self, claims: List[Dict[str, Any]], support_context: Dict[str, Any]) -> float:
        if not claims:
            return 0.0
        supported_claims = 0
        unresolved_penalty = 0.0
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            facts = self._normalize_lines(claim.get("supporting_facts") or [])
            if facts:
                supported_claims += 1
            claim_type = str(claim.get("claim_type") or "").strip()
            for context in support_context.get("claims", []):
                if isinstance(context, dict) and str(context.get("claim_type") or "").strip() == claim_type:
                    unresolved_penalty += 0.08 * len(context.get("missing_elements") or [])
        coverage = supported_claims / max(len(claims), 1)
        return _clamp(coverage - unresolved_penalty + 0.2)

    def _score_requested_relief_section(
        self,
        requested_relief: List[str],
        claims: List[Dict[str, Any]],
        drafting_readiness: Dict[str, Any],
    ) -> float:
        if not requested_relief:
            return 0.0
        section_readiness = drafting_readiness.get("sections") if isinstance(drafting_readiness.get("sections"), dict) else {}
        relief_readiness = section_readiness.get("requested_relief") if isinstance(section_readiness.get("requested_relief"), dict) else {}
        readiness_status = str(relief_readiness.get("status") or "").strip().lower()
        count_score = min(len(requested_relief), 3) / 3.0
        variety_score = 0.2 if len({item.lower() for item in requested_relief}) == len(requested_relief) else 0.0
        claim_bonus = 0.15 if claims else 0.0
        readiness_bonus = 0.2 if readiness_status == "ready" else 0.05 if readiness_status == "warning" else 0.0
        return _clamp((count_score * 0.45) + variety_score + claim_bonus + readiness_bonus)

    def _score_affidavit_section(self, affidavit: Dict[str, Any], exhibits: List[Dict[str, Any]]) -> float:
        facts = self._normalize_lines(affidavit.get("facts") or [])
        intro_score = 0.2 if str(affidavit.get("intro") or "").strip() else 0.0
        jurat_score = 0.15 if str(affidavit.get("jurat") or "").strip() else 0.0
        fact_score = min(len(facts), 4) / 4.0 * 0.45
        supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
        exhibit_score = 0.2 if supporting_exhibits or exhibits else 0.0
        return _clamp(intro_score + jurat_score + fact_score + exhibit_score)

    def _score_certificate_section(self, certificate: Dict[str, Any]) -> float:
        recipients = self._normalize_lines(certificate.get("recipients") or [])
        recipient_details = certificate.get("recipient_details") if isinstance(certificate.get("recipient_details"), list) else []
        text_score = 0.3 if str(certificate.get("text") or "").strip() else 0.0
        recipient_score = min(len(recipients), 2) / 2.0 * 0.25
        detail_score = min(len(recipient_details), 2) / 2.0 * 0.3
        dated_score = 0.15 if str(certificate.get("dated") or "").strip() else 0.0
        return _clamp(text_score + recipient_score + detail_score + dated_score)

    def _score_packet_projection(self, packet_projection: Dict[str, Any]) -> float:
        section_presence = packet_projection.get("section_presence") if isinstance(packet_projection.get("section_presence"), dict) else {}
        section_counts = packet_projection.get("section_counts") if isinstance(packet_projection.get("section_counts"), dict) else {}
        required_sections = ("nature_of_action", "summary_of_facts", "factual_allegations", "claims_for_relief", "requested_relief")
        required_score = sum(1.0 for key in required_sections if section_presence.get(key)) / max(len(required_sections), 1)
        affidavit_score = 1.0 if packet_projection.get("has_affidavit") else 0.0
        certificate_score = 1.0 if packet_projection.get("has_certificate_of_service") else 0.0
        allegation_depth = min(int(section_counts.get("factual_allegations") or 0), 4) / 4.0
        claim_depth = min(int(section_counts.get("claims_for_relief") or 0), 2) / 2.0
        relief_depth = min(int(section_counts.get("requested_relief") or 0), 3) / 3.0
        return _clamp((required_score * 0.3) + (affidavit_score * 0.2) + (certificate_score * 0.2) + (allegation_depth * 0.15) + (claim_depth * 0.1) + (relief_depth * 0.05))

    def _score_grounding(self, support_context: Dict[str, Any]) -> float:
        claim_contexts = support_context.get("claims") if isinstance(support_context.get("claims"), list) else []
        evidence = support_context.get("evidence") if isinstance(support_context.get("evidence"), list) else []
        claim_bonus = min(len(claim_contexts), 3) / 4.0
        evidence_bonus = min(len(evidence), 3) / 6.0
        return _clamp(claim_bonus + evidence_bonus)

    def _score_coherence(self, allegations: List[str]) -> float:
        if not allegations:
            return 0.0
        dedup_ratio = len({value.lower() for value in allegations}) / max(len(allegations), 1)
        punctuation_ratio = sum(1 for value in allegations if value.endswith((".", "!", "?"))) / max(len(allegations), 1)
        return _clamp((dedup_ratio * 0.6) + (punctuation_ratio * 0.4))

    def _score_intake_questioning(
        self,
        *,
        factual_allegations: List[str],
        support_context: Dict[str, Any],
    ) -> float:
        priorities = support_context.get("intake_priorities") if isinstance(support_context.get("intake_priorities"), dict) else {}
        uncovered = {
            _normalize_intake_objective(item)
            for item in list(priorities.get("uncovered_objectives") or [])
            if _normalize_intake_objective(item)
        }
        covered = {
            _normalize_intake_objective(item)
            for item in list(priorities.get("covered_objectives") or [])
            if _normalize_intake_objective(item)
        }
        unresolved = {
            _normalize_intake_objective(item)
            for item in list(priorities.get("unresolved_objectives") or [])
            if _normalize_intake_objective(item)
        }
        objective_counts = {
            _normalize_intake_objective(key): int(value or 0)
            for key, value in dict(priorities.get("objective_question_counts") or {}).items()
            if _normalize_intake_objective(key)
        }
        score = 0.35
        if any(_contains_date_anchor(text) for text in factual_allegations):
            score += 0.2
        if any(_contains_actor_marker(text) for text in factual_allegations):
            score += 0.2
        if any(_contains_causation_link(text) for text in factual_allegations):
            score += 0.25
        lowered_allegations = " ".join(str(item).lower() for item in factual_allegations)
        if any(token in lowered_allegations for token in ("hearing request", "review request", "requested a hearing")):
            score += 0.06
        if any(token in lowered_allegations for token in ("response date", "responded on", "decision date", "hearing outcome date")):
            score += 0.06
        if any(token in lowered_allegations for token in ("name and title", "names and titles", "name or title", "staff names", "staff titles")):
            score += 0.05
        if covered:
            score += min(len(covered), 4) * 0.03
        weighted_gap_penalty = 0.0
        for objective, weight in _INTAKE_OBJECTIVE_PRIORITY.items():
            if objective in uncovered or objective in unresolved or int(objective_counts.get(objective, 0)) <= 0:
                weighted_gap_penalty += 0.03 * float(weight)
        score -= min(weighted_gap_penalty, 0.3)
        if {"timeline", "actors", "causation_link", "staff_names_titles", "hearing_request_timing", "response_dates"}.intersection(uncovered):
            score -= 0.08
        return _clamp(score)

    def _build_workflow_phase_targeting(
        self,
        *,
        section_scores: Dict[str, float],
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        priorities = support_context.get("intake_priorities") if isinstance(support_context.get("intake_priorities"), dict) else {}
        unresolved_objectives = {
            _normalize_intake_objective(item)
            for item in list(priorities.get("unresolved_objectives") or [])
            if _normalize_intake_objective(item)
        }
        critical_unresolved = {
            _normalize_intake_objective(item)
            for item in list(priorities.get("critical_unresolved_objectives") or [])
            if _normalize_intake_objective(item)
        }
        graph_blockers = unresolved_objectives.intersection(
            {
                "timeline",
                "actors",
                "staff_names_titles",
                "causation_link",
                "anchor_adverse_action",
                "anchor_appeal_rights",
                "hearing_request_timing",
                "response_dates",
            }
        )
        document_blockers = unresolved_objectives.intersection(
            {
                "documents",
                "harm_remedy",
                "anchor_adverse_action",
                "anchor_appeal_rights",
                "staff_names_titles",
                "hearing_request_timing",
                "response_dates",
            }
        )

        factual_pressure = max(0.0, 1.0 - float(section_scores.get("factual_allegations") or 0.0))
        claims_pressure = max(0.0, 1.0 - float(section_scores.get("claims_for_relief") or 0.0))
        requested_relief_pressure = max(0.0, 1.0 - float(section_scores.get("requested_relief") or 0.0))
        affidavit_pressure = max(0.0, 1.0 - float(section_scores.get("affidavit") or 0.0))
        certificate_pressure = max(0.0, 1.0 - float(section_scores.get("certificate_of_service") or 0.0))
        packet_pressure = max(0.0, 1.0 - float(section_scores.get("packet_projection") or 0.0))
        intake_pressure = max(0.0, 1.0 - float(section_scores.get("intake_questioning") or 0.0))

        phase_scores = {
            "graph_analysis": _clamp(
                factual_pressure * 0.55
                + claims_pressure * 0.15
                + min(len(graph_blockers) * 0.08, 0.28)
                + min(len(critical_unresolved.intersection(graph_blockers)) * 0.05, 0.15)
            ),
            "document_generation": _clamp(
                claims_pressure * 0.2
                + requested_relief_pressure * 0.2
                + affidavit_pressure * 0.2
                + certificate_pressure * 0.15
                + packet_pressure * 0.15
                + min(len(document_blockers) * 0.06, 0.18)
            ),
            "intake_questioning": _clamp(
                intake_pressure
                + min(len(unresolved_objectives) * 0.05, 0.2)
                + min(len(critical_unresolved) * 0.04, 0.12)
            ),
        }

        phase_focus_order = [
            name
            for name, _score in sorted(
                phase_scores.items(),
                key=lambda item: (-float(item[1]), self.WORKFLOW_PHASE_FOCUS_ORDER.index(item[0])),
            )
        ]
        phase_target_sections = {
            phase_name: self._select_phase_target_section(
                phase_name=phase_name,
                section_scores=section_scores,
                unresolved_objectives=unresolved_objectives,
            )
            for phase_name in phase_focus_order
        }
        return {
            "phase_scores": phase_scores,
            "phase_focus_order": phase_focus_order,
            "phase_target_sections": phase_target_sections,
        }

    def _select_phase_target_section(
        self,
        *,
        phase_name: str,
        section_scores: Dict[str, float],
        unresolved_objectives: set[str],
    ) -> str:
        candidates = [
            section_name
            for section_name in self.WORKFLOW_PHASE_SECTION_CANDIDATES.get(phase_name, ())
            if section_name in self.VALID_FOCUS_SECTIONS
        ]
        if not candidates:
            return "factual_allegations"
        if phase_name == "graph_analysis" and unresolved_objectives.intersection(
            {
                "timeline",
                "actors",
                "staff_names_titles",
                "causation_link",
                "anchor_adverse_action",
                "anchor_appeal_rights",
                "hearing_request_timing",
                "response_dates",
            }
        ):
            return "factual_allegations"
        if phase_name == "intake_questioning" and unresolved_objectives:
            return "factual_allegations"
        return min(candidates, key=lambda section_name: float(section_scores.get(section_name) or 0.0))

    def _merge_review_payload(self, parsed: Optional[Dict[str, Any]], heuristic_review: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(parsed, dict):
            return heuristic_review
        merged = deepcopy(heuristic_review)
        for key in ("overall_score", "strengths", "weaknesses", "suggestions"):
            if key in parsed:
                merged[key] = parsed[key]
        if isinstance(parsed.get("dimension_scores"), dict):
            merged["dimension_scores"] = {**merged.get("dimension_scores", {}), **parsed["dimension_scores"]}
        if isinstance(parsed.get("section_scores"), dict):
            merged["section_scores"] = {**merged.get("section_scores", {}), **parsed["section_scores"]}
        recommended_focus = str(parsed.get("recommended_focus") or "").strip()
        if recommended_focus in self.VALID_FOCUS_SECTIONS:
            merged["recommended_focus"] = recommended_focus
        merged["overall_score"] = _clamp(float(merged.get("overall_score") or 0.0))
        return merged

    def _serialize_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(review, dict):
            return {}
        serialized = {
            "overall_score": float(review.get("overall_score") or 0.0),
            "dimension_scores": dict(review.get("dimension_scores") or {}),
            "section_scores": dict(review.get("section_scores") or {}),
            "strengths": list(review.get("strengths") or []),
            "weaknesses": list(review.get("weaknesses") or []),
            "suggestions": list(review.get("suggestions") or []),
            "recommended_focus": str(review.get("recommended_focus") or ""),
            "workflow_phase_order": list(review.get("workflow_phase_order") or []),
            "workflow_phase_scores": dict(review.get("workflow_phase_scores") or {}),
            "workflow_phase_target_sections": dict(review.get("workflow_phase_target_sections") or {}),
            "prioritized_workflow_phase": str(review.get("prioritized_workflow_phase") or ""),
        }
        llm_metadata = dict(review.get("llm_metadata") or {})
        if llm_metadata:
            serialized["llm_metadata"] = llm_metadata
        return serialized

    def _extract_llm_metadata(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        allowed_keys = (
            "status",
            "provider_name",
            "model_name",
            "effective_provider_name",
            "effective_model_name",
            "router_base_url",
            "hf_bill_to",
            "arch_router_status",
            "arch_router_selected_route",
            "arch_router_selected_model",
            "arch_router_model_name",
            "arch_router_error",
            "error",
        )
        metadata = {}
        for key in allowed_keys:
            value = payload.get(key)
            if value in (None, "", []):
                continue
            metadata[key] = value
        return metadata

    def _choose_focus_section(
        self,
        *,
        current_review: Dict[str, Any],
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
        support_context: Dict[str, Any],
    ) -> str:
        workflow_phase_order = [
            str(value)
            for value in list(current_review.get("workflow_phase_order") or [])
            if str(value)
        ]
        phase_target_sections = dict(current_review.get("workflow_phase_target_sections") or {})
        for phase_name in workflow_phase_order:
            target_section = str(phase_target_sections.get(phase_name) or "").strip()
            if target_section in self.VALID_FOCUS_SECTIONS:
                return target_section
        recommended_focus = str(current_review.get("recommended_focus") or "").strip()
        if recommended_focus in self.VALID_FOCUS_SECTIONS:
            return recommended_focus
        return self._heuristic_review(
            draft=draft,
            drafting_readiness=drafting_readiness,
            support_context=support_context,
        ).get("recommended_focus", "factual_allegations")

    def _select_support_context(
        self,
        *,
        focus_section: str,
        draft: Dict[str, Any],
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        query = self._focus_query_text(focus_section, draft)
        claim_rows = support_context.get("claims") if isinstance(support_context.get("claims"), list) else []
        candidate_rows = []
        for claim_row in claim_rows:
            if not isinstance(claim_row, dict):
                continue
            claim_type = str(claim_row.get("claim_type") or "").strip()
            for text in claim_row.get("support_facts") or []:
                candidate_rows.append({"claim_type": claim_type, "text": str(text)})
            for text in claim_row.get("missing_elements") or []:
                candidate_rows.append({"claim_type": claim_type, "text": str(text), "kind": "missing_element"})
        for evidence_row in support_context.get("evidence") or []:
            if isinstance(evidence_row, dict) and evidence_row.get("text"):
                candidate_rows.append(dict(evidence_row))
        intake_priorities = support_context.get("intake_priorities") if isinstance(support_context.get("intake_priorities"), dict) else {}
        for prompt_text in intake_priorities.get("recommended_follow_up_prompts") or []:
            normalized_prompt = str(prompt_text or "").strip()
            if not normalized_prompt:
                continue
            candidate_rows.append(
                {
                    "claim_type": "intake_follow_up",
                    "text": normalized_prompt,
                    "kind": "intake_objective_prompt",
                }
            )

        ranked_rows = self._rank_candidates(query=query, candidates=candidate_rows)
        return {
            "focus_section": focus_section,
            "query": query,
            "top_support": ranked_rows[:6],
        }

    def _build_fallback_actor_payload(
        self,
        *,
        draft: Dict[str, Any],
        focus_section: str,
        support_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"focus_section": focus_section}
        top_support = support_context.get("top_support") if isinstance(support_context.get("top_support"), list) else []
        support_texts = self._normalize_lines([row.get("text") for row in top_support if isinstance(row, dict)])

        if focus_section == "factual_allegations":
            factual_candidates = self._normalize_lines(draft.get("summary_of_facts") or [])
            factual_candidates.extend(support_texts)
            for claim in draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []:
                if isinstance(claim, dict):
                    factual_candidates.extend(self._normalize_lines(claim.get("supporting_facts") or []))
            normalized_candidates = self._normalize_lines(factual_candidates)
            if not any(_contains_date_anchor(item) for item in normalized_candidates):
                normalized_candidates.append(
                    "On or about [date], HACC communicated the adverse action identified in this complaint."
                )
            if not any(_contains_actor_marker(item) for item in normalized_candidates):
                normalized_candidates.append(
                    "HACC staff members involved in each intake, review, hearing, and denial decision should be identified by name or title."
                )
            if not any(_contains_causation_link(item) for item in normalized_candidates):
                normalized_candidates.append(
                    "After Plaintiff engaged in protected activity, HACC took adverse action, and the factual timeline supports a causal connection."
                )
            normalized_lower = " ".join(item.lower() for item in normalized_candidates)
            if not any(token in normalized_lower for token in ("hearing request", "review request", "requested a hearing")):
                normalized_candidates.append(
                    "Plaintiff requested an informal review or hearing on [date], and the timing of that request should be documented in relation to each adverse-action step."
                )
            if not any(token in normalized_lower for token in ("response date", "responded on", "review decision date", "hearing outcome date")):
                normalized_candidates.append(
                    "HACC response dates for notice, hearing/review requests, and final decision communications should be identified with exact dates."
                )
            if not any(token in normalized_lower for token in ("name or title", "staff name", "staff title")):
                normalized_candidates.append(
                    "For each key event, the complaint should identify the HACC staff member by name and title, or by the best-known title if the name is not yet confirmed."
                )
            if not any(token in normalized_lower for token in ("shortly after", "within", "days after", "weeks after")):
                normalized_candidates.append(
                    "The complaint should state the sequencing between protected activity and adverse treatment using concrete timing (for example, days or weeks after the protected activity)."
                )
            payload["factual_allegations"] = self._normalize_lines(normalized_candidates)[:12]
        elif focus_section == "claims_for_relief":
            updated_claims: List[Dict[str, Any]] = []
            claim_supporting_facts: Dict[str, List[str]] = {}
            for claim in draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []:
                if not isinstance(claim, dict):
                    continue
                claim_type = str(claim.get("claim_type") or "").strip()
                merged_supporting_facts = self._normalize_lines(
                    list(claim.get("supporting_facts") or []) + support_texts
                )[:6]
                claim_supporting_facts[claim_type] = merged_supporting_facts
                updated_claim = deepcopy(claim)
                updated_claim["supporting_facts"] = merged_supporting_facts
                updated_claims.append(updated_claim)
            payload["claim_supporting_facts"] = claim_supporting_facts
            payload["claims_for_relief"] = updated_claims
            relief_candidates = self._normalize_lines(list(draft.get("requested_relief") or []) + support_texts)[:6]
            if relief_candidates:
                payload["requested_relief"] = relief_candidates
        elif focus_section == "requested_relief":
            relief_candidates = list(draft.get("requested_relief") or [])
            if self.builder is not None:
                extract_relief = getattr(self.builder, "_extract_requested_relief_from_facts", None)
                if callable(extract_relief):
                    try:
                        relief_candidates.extend(extract_relief(support_texts))
                    except Exception:
                        pass
            if not relief_candidates:
                for claim in draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []:
                    if not isinstance(claim, dict):
                        continue
                    claim_type = str(claim.get("claim_type") or "").strip().lower()
                    if "retaliation" in claim_type or "termination" in claim_type:
                        relief_candidates.extend([
                            "Back pay, front pay, and lost benefits.",
                            "Reinstatement or front pay in lieu of reinstatement.",
                        ])
                    if "discrimination" in claim_type:
                        relief_candidates.append("Injunctive relief to prevent continuing violations.")
            payload["requested_relief"] = self._normalize_lines(relief_candidates)[:6]
        elif focus_section == "affidavit":
            affidavit = draft.get("affidavit") if isinstance(draft.get("affidavit"), dict) else {}
            payload["affidavit_intro"] = str(
                affidavit.get("intro")
                or f"I, {affidavit.get('declarant_name') or 'Plaintiff'}, make this affidavit from personal knowledge and the supporting records assembled for this complaint."
            ).strip()
            affidavit_facts = self._normalize_affidavit_facts(
                list(affidavit.get("facts") or []) + list(draft.get("factual_allegations") or []) + support_texts
            )[:8]
            payload["affidavit_facts"] = affidavit_facts
            supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
            if not supporting_exhibits:
                supporting_exhibits = self._normalize_exhibits(draft.get("exhibits") or [])[:4]
            payload["affidavit_supporting_exhibits"] = supporting_exhibits
        elif focus_section == "certificate_of_service":
            certificate = draft.get("certificate_of_service") if isinstance(draft.get("certificate_of_service"), dict) else {}
            recipients = self._normalize_lines(certificate.get("recipients") or [])
            method = "promptly after filing"
            details = certificate.get("recipient_details") if isinstance(certificate.get("recipient_details"), list) else []
            if not details and recipients:
                details = [{"recipient": recipient, "method": "Service method to be confirmed", "address": "", "notes": ""} for recipient in recipients]
            payload["service_recipients"] = recipients
            payload["service_recipient_details"] = details
            payload["service_text"] = str(
                certificate.get("text")
                or f"I certify that a true and correct copy of this Complaint will be served on the following recipients {method}."
            ).strip()
        return payload

    def _focus_query_text(self, focus_section: str, draft: Dict[str, Any]) -> str:
        if focus_section == "factual_allegations":
            return (
                "factual allegations pleading-ready support record date anchors "
                "actor-by-actor decision timeline protected activity causation adverse action "
                "staff names titles hearing request timing response dates sequence of protected activity and adverse action"
            )
        if focus_section == "claims_for_relief":
            claim_titles = []
            for claim in draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []:
                if isinstance(claim, dict):
                    claim_titles.append(str(claim.get("claim_type") or claim.get("count_title") or ""))
            return (
                "claims for relief causal linkage protected activity adverse action "
                "decision-makers timeline hearing request timing response dates staff names titles "
                + " ".join(title for title in claim_titles if title)
            )
        if focus_section == "requested_relief":
            return "requested relief remedies damages injunction reinstatement back pay front pay"
        if focus_section == "affidavit":
            return "affidavit facts exhibits personal knowledge"
        if focus_section == "certificate_of_service":
            return "certificate of service recipients method address"
        return focus_section.replace("_", " ")

    def _rank_candidates(self, *, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        self._router_usage["ranked_candidate_count"] = int(self._router_usage.get("ranked_candidate_count") or 0) + len(candidates)
        query_terms = set(query.lower().split())
        router = self._get_embeddings_router()
        if router is None:
            ranked = []
            for row in candidates:
                text = str(row.get("text") or "")
                lexical_score = self._lexical_overlap_score(query_terms, text)
                ranked.append({**row, "score": lexical_score, "lexical_score": lexical_score, "ranking_method": "lexical_fallback"})
            return sorted(ranked, key=lambda row: row.get("score", 0.0), reverse=True)

        query_vector = self._embed_text(router, query)
        self._router_usage["embedding_rankings"] = int(self._router_usage.get("embedding_rankings") or 0) + 1
        ranked = []
        for row in candidates:
            text = str(row.get("text") or "")
            candidate_vector = self._embed_text(router, text)
            semantic_score = self._cosine_similarity(query_vector, candidate_vector)
            lexical_score = self._lexical_overlap_score(query_terms, text)
            score = _clamp((semantic_score * 0.8) + (lexical_score * 0.2), 0.0, 1.0)
            ranked.append(
                {
                    **row,
                    "score": score,
                    "semantic_score": semantic_score,
                    "lexical_score": lexical_score,
                    "ranking_method": "embeddings_router_hybrid",
                }
            )
        return sorted(ranked, key=lambda row: row.get("score", 0.0), reverse=True)

    def _get_embeddings_router(self) -> Any:
        if not EMBEDDINGS_AVAILABLE:
            return None
        if self._embeddings_router is None:
            try:
                embeddings_config = self.llm_config.get("embeddings") if isinstance(self.llm_config.get("embeddings"), dict) else None
                if embeddings_config is None and isinstance(self.llm_config.get("embeddings_config"), dict):
                    embeddings_config = self.llm_config.get("embeddings_config")
                if embeddings_config:
                    self._embeddings_router = get_embeddings_router(**dict(embeddings_config))
                else:
                    self._embeddings_router = get_embeddings_router()
            except Exception:
                self._embeddings_router = None
        return self._embeddings_router

    def _embed_text(self, router: Any, text: str) -> List[float]:
        cache_key = str(text or "")
        cached = self._embedding_cache.get(cache_key)
        if cached is not None:
            self._router_usage["embedding_cache_hits"] = int(self._router_usage.get("embedding_cache_hits") or 0) + 1
            return list(cached)
        for method_name in ("embed_text", "encode", "embed"):
            method = getattr(router, method_name, None)
            if callable(method):
                try:
                    self._router_usage["embedding_requests"] = int(self._router_usage.get("embedding_requests") or 0) + 1
                    vector = method(text)
                except Exception:
                    continue
                if isinstance(vector, dict):
                    for key in ("embedding", "vector", "values"):
                        if isinstance(vector.get(key), (list, tuple)):
                            vector = vector.get(key)
                            break
                if isinstance(vector, list):
                    normalized = [float(value) for value in vector]
                    self._embedding_cache[cache_key] = normalized
                    return list(normalized)
                if isinstance(vector, tuple):
                    normalized = [float(value) for value in vector]
                    self._embedding_cache[cache_key] = normalized
                    return list(normalized)
        return []

    def _lexical_overlap_score(self, query_terms: set[str], text: str) -> float:
        text_terms = set(str(text or "").lower().split())
        if not query_terms or not text_terms:
            return 0.0
        return len(query_terms & text_terms) / max(len(query_terms), 1)

    def _cosine_similarity(self, left: List[float], right: List[float]) -> float:
        if not left or not right:
            return 0.0
        length = min(len(left), len(right))
        if length <= 0:
            return 0.0
        dot = sum(float(left[index]) * float(right[index]) for index in range(length))
        left_norm = math.sqrt(sum(float(left[index]) ** 2 for index in range(length)))
        right_norm = math.sqrt(sum(float(right[index]) ** 2 for index in range(length)))
        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0
        return dot / (left_norm * right_norm)

    def _refresh_dependent_sections(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        refreshed = deepcopy(draft)
        if self.builder is not None:
            build_affidavit = getattr(self.builder, "_build_affidavit", None)
            if callable(build_affidavit):
                refreshed["affidavit"] = build_affidavit(refreshed)
            render_draft_text = getattr(self.builder, "_render_draft_text", None)
            if callable(render_draft_text):
                refreshed["draft_text"] = render_draft_text(refreshed)
        return refreshed

    def _router_status(self) -> Dict[str, str]:
        return {
            "llm_router": "available" if LLM_ROUTER_AVAILABLE else "unavailable",
            "embeddings_router": "available" if EMBEDDINGS_AVAILABLE else "unavailable",
            "ipfs_router": "available" if IPFS_AVAILABLE else "unavailable",
            "optimizers_agentic": "available" if UPSTREAM_AGENTIC_AVAILABLE else "unavailable",
        }

    def _router_usage_summary(self) -> Dict[str, Any]:
        return {
            "llm_calls": int(self._router_usage.get("llm_calls") or 0),
            "critic_calls": int(self._router_usage.get("critic_calls") or 0),
            "actor_calls": int(self._router_usage.get("actor_calls") or 0),
            "embedding_requests": int(self._router_usage.get("embedding_requests") or 0),
            "embedding_cache_hits": int(self._router_usage.get("embedding_cache_hits") or 0),
            "embedding_rankings": int(self._router_usage.get("embedding_rankings") or 0),
            "ranked_candidate_count": int(self._router_usage.get("ranked_candidate_count") or 0),
            "ipfs_store_attempted": bool(self._router_usage.get("ipfs_store_attempted")),
            "ipfs_store_succeeded": bool(self._router_usage.get("ipfs_store_succeeded")),
            "llm_providers_used": list(self._router_usage.get("llm_providers_used") or []),
        }

    def _build_packet_projection(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        if self.builder is not None:
            build_packet = getattr(self.builder, "_build_filing_packet_payload", None)
            if callable(build_packet):
                try:
                    packet = build_packet(draft, artifacts={})
                except Exception:
                    packet = {}
                if isinstance(packet, dict):
                    sections = packet.get("sections") if isinstance(packet.get("sections"), dict) else {}
                    return {
                        "title": str(packet.get("title") or draft.get("title") or "").strip(),
                        "section_presence": {
                            key: bool(sections.get(key))
                            for key in ("nature_of_action", "summary_of_facts", "factual_allegations", "claims_for_relief", "requested_relief")
                        },
                        "section_counts": {
                            key: len(sections.get(key) or []) if isinstance(sections.get(key), list) else int(bool(sections.get(key)))
                            for key in ("nature_of_action", "summary_of_facts", "factual_allegations", "claims_for_relief", "requested_relief")
                        },
                        "has_affidavit": bool(packet.get("affidavit")),
                        "has_certificate_of_service": bool(packet.get("certificate_of_service")),
                        "exhibit_count": len(packet.get("exhibits") or []) if isinstance(packet.get("exhibits"), list) else 0,
                        "checklist_item_count": len(packet.get("filing_checklist") or []) if isinstance(packet.get("filing_checklist"), list) else 0,
                        "preview": {
                            "factual_allegations": list(sections.get("factual_allegations") or [])[:4],
                            "affidavit_facts": list((packet.get("affidavit") or {}).get("facts") or [])[:4] if isinstance(packet.get("affidavit"), dict) else [],
                            "service_recipients": list((packet.get("certificate_of_service") or {}).get("recipients") or [])[:4] if isinstance(packet.get("certificate_of_service"), dict) else [],
                        },
                    }
        return {
            "title": str(draft.get("title") or "").strip(),
            "section_presence": {
                "nature_of_action": bool(draft.get("nature_of_action")),
                "summary_of_facts": bool(draft.get("summary_of_facts")),
                "factual_allegations": bool(draft.get("factual_allegations")),
                "claims_for_relief": bool(draft.get("claims_for_relief")),
                "requested_relief": bool(draft.get("requested_relief")),
            },
            "section_counts": {
                "nature_of_action": len(draft.get("nature_of_action") or []) if isinstance(draft.get("nature_of_action"), list) else int(bool(draft.get("nature_of_action"))),
                "summary_of_facts": len(draft.get("summary_of_facts") or []) if isinstance(draft.get("summary_of_facts"), list) else int(bool(draft.get("summary_of_facts"))),
                "factual_allegations": len(draft.get("factual_allegations") or []) if isinstance(draft.get("factual_allegations"), list) else int(bool(draft.get("factual_allegations"))),
                "claims_for_relief": len(draft.get("claims_for_relief") or []) if isinstance(draft.get("claims_for_relief"), list) else int(bool(draft.get("claims_for_relief"))),
                "requested_relief": len(draft.get("requested_relief") or []) if isinstance(draft.get("requested_relief"), list) else int(bool(draft.get("requested_relief"))),
            },
            "has_affidavit": bool(draft.get("affidavit")),
            "has_certificate_of_service": bool(draft.get("certificate_of_service")),
            "exhibit_count": len(draft.get("exhibits") or []) if isinstance(draft.get("exhibits"), list) else 0,
            "checklist_item_count": len(draft.get("filing_checklist") or []) if isinstance(draft.get("filing_checklist"), list) else 0,
            "preview": {
                "factual_allegations": list(draft.get("factual_allegations") or [])[:4] if isinstance(draft.get("factual_allegations"), list) else [],
                "affidavit_facts": list((draft.get("affidavit") or {}).get("facts") or [])[:4] if isinstance(draft.get("affidavit"), dict) else [],
                "service_recipients": list((draft.get("certificate_of_service") or {}).get("recipients") or [])[:4] if isinstance(draft.get("certificate_of_service"), dict) else [],
            },
        }

    def _build_upstream_optimizer_metadata(self) -> Dict[str, Any]:
        metadata = {
            "available": bool(UPSTREAM_AGENTIC_AVAILABLE),
            "selected_provider": "",
            "selected_method": "",
            "phase_focus_order": list(current_review.get("workflow_phase_order") or self.WORKFLOW_PHASE_FOCUS_ORDER),
            "control_loop": {},
        }
        if not UPSTREAM_AGENTIC_AVAILABLE:
            return metadata
        metadata["stage_provider_selection"] = {
            role: dict(selection)
            for role, selection in self._stage_provider_selection.items()
            if isinstance(selection, dict)
        }
        try:
            method_name = "ACTOR_CRITIC"
            selected_method = getattr(OptimizationMethod, method_name, None)
            metadata["selected_method"] = getattr(selected_method, "value", "actor_critic")
            if ControlLoopConfig is not None:
                config = ControlLoopConfig(
                    max_iterations=self.max_iterations,
                    target_score=self.target_score,
                )
                metadata["control_loop"] = {
                    "max_iterations": int(getattr(config, "max_iterations", self.max_iterations)),
                    "target_score": float(getattr(config, "target_score", self.target_score)),
                }
            if OptimizerLLMRouter is not None and selected_method is not None:
                router = OptimizerLLMRouter(enable_tracking=False, enable_caching=False)
                selected_provider = router.select_provider(selected_method, complexity="complex")
                metadata["selected_provider"] = str(getattr(selected_provider, "value", selected_provider) or "")
        except Exception:
            return metadata
        return metadata

    def _store_trace(self, trace_payload: Dict[str, Any]) -> Dict[str, Any]:
        self._router_usage["ipfs_store_attempted"] = bool(self.persist_artifacts)
        if not self.persist_artifacts or not IPFS_AVAILABLE:
            return {"status": "disabled", "cid": "", "size": 0, "pinned": False}
        encoded = json.dumps(trace_payload, ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")
        result = store_bytes(encoded, pin_content=True)
        self._router_usage["ipfs_store_succeeded"] = str(result.get("status") or "") == "available" and bool(result.get("cid"))
        return {
            "status": result.get("status") or "",
            "cid": result.get("cid") or "",
            "size": int(result.get("size") or len(encoded)),
            "pinned": bool(result.get("pinned")),
        }

    def _sanitized_llm_config(self) -> Dict[str, Any]:
        sanitized: Dict[str, Any] = {}
        for key, value in self.llm_config.items():
            lowered = str(key).lower()
            if lowered in {"api_key", "token", "access_token", "authorization"}:
                sanitized[str(key)] = "[redacted]"
            elif lowered == "headers" and isinstance(value, dict):
                sanitized[str(key)] = {
                    str(header_key): ("[redacted]" if str(header_key).lower() == "authorization" else header_value)
                    for header_key, header_value in value.items()
                }
            else:
                sanitized[str(key)] = value
        return sanitized

    def _call_mediator(self, method_name: str, **kwargs: Any) -> Any:
        method = getattr(self.mediator, method_name, None)
        if not callable(method):
            return None
        try:
            return method(**kwargs)
        except Exception:
            return None

    def _extract_support_texts(self, values: Any) -> List[str]:
        texts: List[str] = []
        for value in values if isinstance(values, list) else []:
            if isinstance(value, str):
                texts.append(value)
                continue
            if not isinstance(value, dict):
                continue
            for key in ("fact_text", "summary", "text", "description", "parsed_text_preview", "title"):
                if value.get(key):
                    texts.append(str(value.get(key)))
        return self._normalize_lines(texts)

    def _extract_element_texts(self, values: Any) -> List[str]:
        elements = []
        for value in values if isinstance(values, list) else []:
            if isinstance(value, dict) and value.get("element_text"):
                elements.append(str(value.get("element_text")))
            elif isinstance(value, str):
                elements.append(value)
        return self._normalize_lines(elements)

    def _normalize_lines(self, values: Any) -> List[str]:
        if isinstance(values, list):
            iterable = values
        elif isinstance(values, tuple):
            iterable = list(values)
        else:
            iterable = [values]
        normalized = []
        for value in iterable:
            text = " ".join(str(value or "").strip().split())
            if not text:
                continue
            if text[-1] not in ".!?":
                text = f"{text}."
            normalized.append(text)
        return _unique_preserving_order(normalized)

    def _normalize_claims_for_relief(self, values: Any, existing_claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        existing_by_key = {
            self._claim_key(claim): deepcopy(claim)
            for claim in existing_claims
            if isinstance(claim, dict) and self._claim_key(claim)
        }
        normalized_claims: List[Dict[str, Any]] = []
        seen_keys = set()
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            claim_key = str(item.get("claim_type") or item.get("count_title") or "").strip().lower()
            base_claim = deepcopy(existing_by_key.get(claim_key) or {})
            claim_type = str(item.get("claim_type") or base_claim.get("claim_type") or item.get("count_title") or "Claim").strip() or "Claim"
            normalized = {
                **base_claim,
                **item,
                "claim_type": claim_type,
                "count_title": str(item.get("count_title") or base_claim.get("count_title") or claim_type.title()).strip(),
                "legal_standards": self._normalize_lines(item.get("legal_standards") if "legal_standards" in item else base_claim.get("legal_standards") or []),
                "supporting_facts": self._normalize_lines(item.get("supporting_facts") if "supporting_facts" in item else base_claim.get("supporting_facts") or []),
                "missing_elements": self._normalize_lines(item.get("missing_elements") if "missing_elements" in item else base_claim.get("missing_elements") or []),
                "partially_supported_elements": self._normalize_lines(item.get("partially_supported_elements") if "partially_supported_elements" in item else base_claim.get("partially_supported_elements") or []),
                "supporting_exhibits": self._normalize_exhibits(item.get("supporting_exhibits") if "supporting_exhibits" in item else base_claim.get("supporting_exhibits") or []),
                "support_summary": {
                    **(base_claim.get("support_summary") if isinstance(base_claim.get("support_summary"), dict) else {}),
                    **(item.get("support_summary") if isinstance(item.get("support_summary"), dict) else {}),
                },
            }
            normalized_claims.append(normalized)
            seen_keys.add(self._claim_key(normalized))
        for claim in existing_claims:
            if not isinstance(claim, dict):
                continue
            claim_key = self._claim_key(claim)
            if claim_key and claim_key not in seen_keys:
                normalized_claims.append(deepcopy(claim))
        return normalized_claims

    def _normalize_affidavit_facts(self, values: Any) -> List[str]:
        sanitized: List[str] = []
        for value in values if isinstance(values, list) else []:
            text = " ".join(str(value or "").strip().split())
            if not text:
                continue
            if text.lower().startswith("as to ") and "," in text:
                text = text.split(",", 1)[1].strip()
            if len(text) < 12:
                continue
            if text[-1] not in ".!?":
                text = f"{text}."
            sanitized.append(text)
        return _unique_preserving_order(sanitized)

    def _normalize_exhibits(self, values: Any) -> List[Dict[str, str]]:
        exhibits: List[Dict[str, str]] = []
        seen = set()
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            normalized = {
                "label": str(item.get("label") or "Exhibit").strip(),
                "title": str(item.get("title") or item.get("summary") or "Supporting exhibit").strip(),
                "link": str(item.get("link") or item.get("reference") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
            }
            key = (normalized["label"], normalized["title"], normalized["link"], normalized["summary"])
            if key in seen:
                continue
            seen.add(key)
            exhibits.append(normalized)
        return exhibits

    def _normalize_service_recipient_details(self, values: Any) -> List[Dict[str, str]]:
        details: List[Dict[str, str]] = []
        seen = set()
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            detail = {
                "recipient": str(item.get("recipient") or "").strip(),
                "method": str(item.get("method") or "").strip(),
                "address": str(item.get("address") or "").strip(),
                "notes": str(item.get("notes") or "").strip(),
            }
            key = (detail["recipient"], detail["method"], detail["address"], detail["notes"])
            if key in seen or not any(detail.values()):
                continue
            seen.add(key)
            details.append(detail)
        return details

    def _format_service_recipient_detail(self, detail: Dict[str, str]) -> str:
        segments = [detail.get("recipient") or "Unknown recipient"]
        if detail.get("method"):
            segments.append(f"Method: {detail['method']}")
        if detail.get("address"):
            segments.append(f"Address: {detail['address']}")
        if detail.get("notes"):
            segments.append(f"Notes: {detail['notes']}")
        return " | ".join(segment for segment in segments if segment)

    def _parse_json_payload(self, text: Any) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None
        candidates = [raw]
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(raw[start : end + 1])
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
        return None


__all__ = [
    "AgenticDocumentOptimizer",
    "LLM_ROUTER_AVAILABLE",
    "EMBEDDINGS_AVAILABLE",
    "IPFS_AVAILABLE",
    "UPSTREAM_AGENTIC_AVAILABLE",
    "generate_text_with_metadata",
    "get_embeddings_router",
    "store_bytes",
]
