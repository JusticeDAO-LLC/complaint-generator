from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from intake_status import (
    build_intake_case_review_summary,
    build_intake_status_summary,
    build_intake_warning_entries,
    summarize_temporal_issue_registry,
)
from complaint_phases import ComplaintPhase
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
DEFAULT_OPTIMIZER_LLM_TIMEOUT_SECONDS = 45


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)
def _build_workflow_targeting_summary(
    *,
    existing_summary: Any,
    document_evidence_targeting_summary: Any,
) -> Dict[str, Any]:
    existing = existing_summary if isinstance(existing_summary, dict) else {}
    document = (
        document_evidence_targeting_summary
        if isinstance(document_evidence_targeting_summary, dict)
        else {}
    )
    phase_summaries = {
        "intake_questioning": dict((existing.get("phase_summaries") or {}).get("intake_questioning") or {}),
        "graph_analysis": dict((existing.get("phase_summaries") or {}).get("graph_analysis") or {}),
        "document_generation": dict(document),
    }
    phase_counts = {
        phase_name: int((payload or {}).get("count") or 0)
        for phase_name, payload in phase_summaries.items()
    }
    total_target_count = sum(phase_counts.values())
    prioritized_phases = [
        phase_name
        for phase_name, count in sorted(
            phase_counts.items(),
            key=lambda item: (-int(item[1] or 0), item[0]),
        )
        if int(count or 0) > 0
    ]

    shared_claim_element_counts: Dict[str, int] = {}
    shared_focus_area_counts: Dict[str, int] = {}
    for payload in phase_summaries.values():
        for claim_element_id, count in dict(payload.get("claim_element_counts") or {}).items():
            normalized = str(claim_element_id or "").strip()
            if not normalized:
                continue
            shared_claim_element_counts[normalized] = (
                shared_claim_element_counts.get(normalized, 0) + int(count or 0)
            )
        focus_counts = {}
        if "focus_area_counts" in payload:
            focus_counts = dict(payload.get("focus_area_counts") or {})
        elif "objective_counts" in payload:
            focus_counts = dict(payload.get("objective_counts") or {})
        elif "focus_section_counts" in payload:
            focus_counts = dict(payload.get("focus_section_counts") or {})
        for focus_area, count in focus_counts.items():
            normalized = str(focus_area or "").strip()
            if not normalized:
                continue
            shared_focus_area_counts[normalized] = (
                shared_focus_area_counts.get(normalized, 0) + int(count or 0)
            )

    return {
        "count": total_target_count,
        "phase_counts": phase_counts,
        "prioritized_phases": prioritized_phases,
        "shared_claim_element_counts": shared_claim_element_counts,
        "shared_focus_area_counts": shared_focus_area_counts,
        "phase_summaries": phase_summaries,
    }


def _build_document_execution_drift_summary(
    *,
    workflow_targeting_summary: Any,
    document_workflow_execution_summary: Any,
) -> Dict[str, Any]:
    targeting = workflow_targeting_summary if isinstance(workflow_targeting_summary, dict) else {}
    execution = (
        document_workflow_execution_summary
        if isinstance(document_workflow_execution_summary, dict)
        else {}
    )
    targeted_counts = (
        targeting.get("shared_claim_element_counts")
        if isinstance(targeting.get("shared_claim_element_counts"), dict)
        else {}
    )
    top_targeted_element = ""
    top_targeted_count = 0
    if targeted_counts:
        top_targeted_element, top_targeted_count = sorted(
            (
                (str(name or "").strip(), int(count or 0))
                for name, count in targeted_counts.items()
                if str(name or "").strip()
            ),
            key=lambda item: (-item[1], item[0]),
        )[0]
    first_executed_element = str(execution.get("first_targeted_claim_element") or "").strip()
    first_focus_section = str(execution.get("first_focus_section") or "").strip()
    first_support_kind = str(execution.get("first_preferred_support_kind") or "").strip()
    drift_flag = bool(
        top_targeted_element
        and first_executed_element
        and top_targeted_element != first_executed_element
    )
    return {
        "drift_flag": drift_flag,
        "top_targeted_claim_element": top_targeted_element,
        "top_targeted_claim_element_count": top_targeted_count,
        "first_executed_claim_element": first_executed_element,
        "first_focus_section": first_focus_section,
        "first_preferred_support_kind": first_support_kind,
        "iteration_count": int(execution.get("iteration_count") or 0),
        "accepted_iteration_count": int(execution.get("accepted_iteration_count") or 0),
    }


def _build_document_grounding_improvement_summary(
    *,
    initial_document_provenance_summary: Any,
    final_document_provenance_summary: Any,
    workflow_optimization_guidance: Any = None,
) -> Dict[str, Any]:
    initial_summary = (
        initial_document_provenance_summary
        if isinstance(initial_document_provenance_summary, dict)
        else {}
    )
    final_summary = (
        final_document_provenance_summary
        if isinstance(final_document_provenance_summary, dict)
        else {}
    )
    guidance = workflow_optimization_guidance if isinstance(workflow_optimization_guidance, dict) else {}
    if not initial_summary and not final_summary:
        return {}

    initial_ratio = float(initial_summary.get("fact_backed_ratio") or 0.0)
    final_ratio = float(final_summary.get("fact_backed_ratio") or 0.0)
    delta = round(final_ratio - initial_ratio, 4)
    evidence_workflow_action_queue = (
        guidance.get("evidence_workflow_action_queue")
        if isinstance(guidance.get("evidence_workflow_action_queue"), list)
        else []
    )
    workflow_action_queue = (
        guidance.get("workflow_action_queue")
        if isinstance(guidance.get("workflow_action_queue"), list)
        else []
    )
    recovery_actions = [
        action
        for action in [*evidence_workflow_action_queue, *workflow_action_queue]
        if isinstance(action, dict)
        and (
            bool(action.get("document_grounding_recovery"))
            or str(action.get("action_code") or "").strip().lower() == "recover_document_grounding"
            or str(action.get("action") or "").strip().lower() == "recover document grounding"
        )
    ]
    targeted_claim_elements = _unique_preserving_order(
        str((action or {}).get("claim_element_id") or "").strip()
        for action in recovery_actions
        if isinstance(action, dict)
    )
    preferred_support_kinds = _unique_preserving_order(
        str((action or {}).get("preferred_support_kind") or "").strip()
        for action in recovery_actions
        if isinstance(action, dict)
    )
    improved_flag = delta > 0.02
    regressed_flag = delta < -0.02
    stalled_flag = not improved_flag and not regressed_flag
    low_grounding_resolved_flag = bool(
        initial_summary.get("low_grounding_flag") and not final_summary.get("low_grounding_flag")
    )
    return {
        "initial_fact_backed_ratio": round(initial_ratio, 4),
        "final_fact_backed_ratio": round(final_ratio, 4),
        "fact_backed_ratio_delta": delta,
        "initial_low_grounding_flag": bool(initial_summary.get("low_grounding_flag")),
        "final_low_grounding_flag": bool(final_summary.get("low_grounding_flag")),
        "recovery_action_count": len(recovery_actions),
        "recovery_attempted_flag": bool(recovery_actions),
        "targeted_claim_elements": targeted_claim_elements,
        "preferred_support_kinds": preferred_support_kinds,
        "improved_flag": improved_flag,
        "regressed_flag": regressed_flag,
        "stalled_flag": stalled_flag,
        "low_grounding_resolved_flag": low_grounding_resolved_flag,
    }


def _build_document_grounding_lane_outcome_summary(
    *,
    document_grounding_improvement_summary: Any,
    document_workflow_execution_summary: Any,
) -> Dict[str, Any]:
    improvement_summary = (
        document_grounding_improvement_summary
        if isinstance(document_grounding_improvement_summary, dict)
        else {}
    )
    execution_summary = (
        document_workflow_execution_summary
        if isinstance(document_workflow_execution_summary, dict)
        else {}
    )
    if not improvement_summary and not execution_summary:
        return {}

    preferred_support_kinds = (
        improvement_summary.get("preferred_support_kinds")
        if isinstance(improvement_summary.get("preferred_support_kinds"), list)
        else []
    )
    attempted_support_kind = str(
        execution_summary.get("first_preferred_support_kind")
        or (preferred_support_kinds[0] if preferred_support_kinds else "")
        or ""
    ).strip()
    targeted_claim_elements = _unique_preserving_order(
        str(item).strip()
        for item in (improvement_summary.get("targeted_claim_elements") or [])
        if str(item).strip()
    )
    if bool(improvement_summary.get("improved_flag")):
        outcome_status = "improved"
    elif bool(improvement_summary.get("regressed_flag")):
        outcome_status = "regressed"
    else:
        outcome_status = "stalled"
    return {
        "attempted_support_kind": attempted_support_kind,
        "outcome_status": outcome_status,
        "fact_backed_ratio_delta": float(improvement_summary.get("fact_backed_ratio_delta") or 0.0),
        "targeted_claim_elements": targeted_claim_elements,
        "recommended_future_support_kind": attempted_support_kind if outcome_status == "improved" else "",
        "improved_flag": bool(improvement_summary.get("improved_flag")),
        "regressed_flag": bool(improvement_summary.get("regressed_flag")),
        "stalled_flag": bool(improvement_summary.get("stalled_flag")),
    }


def _sorted_count_items(values: Any) -> List[Tuple[str, int]]:
    return [
        (str(name), int(count or 0))
        for name, count in sorted(
            dict(values or {}).items(),
            key=lambda item: (-int(item[1] or 0), str(item[0])),
        )
        if str(name)
    ]


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
    "exact_dates": "exact_dates",
    "timeline": "timeline",
    "timeline_dates": "timeline",
    "actors": "actors",
    "staff_names_titles": "staff_names_titles",
    "staff_names": "staff_names_titles",
    "staff_titles": "staff_names_titles",
    "causation_link": "causation_link",
    "causation": "causation_link",
    "causation_sequence": "causation_sequence",
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
    "exact_dates": 1.0,
    "timeline": 1.0,
    "staff_names_titles": 1.0,
    "actors": 0.9,
    "causation_link": 1.0,
    "causation_sequence": 1.0,
    "anchor_adverse_action": 1.0,
    "anchor_appeal_rights": 0.9,
    "hearing_request_timing": 0.9,
    "response_dates": 0.9,
}

_OBJECTIVE_PROMPTS = {
    "exact_dates": "Capture exact dates or best available day-level anchors for each notice, decision, request, and response event.",
    "timeline": "Capture exact event dates or anchored date ranges for each key intake, complaint, and adverse-action event.",
    "actors": "Identify the HACC actor-by-actor sequence for who made, communicated, and carried out each decision.",
    "staff_names_titles": "Lock specific HACC staff names and titles (or best-known titles) tied to each step.",
    "causation_link": "Document facts that tie protected activity to the adverse treatment using timing, statements, and sequence changes.",
    "causation_sequence": "Document the sequence from protected activity to adverse action, including timing, knowledge, and intervening steps.",
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


def _normalize_blocker_records(value: Any) -> List[Dict[str, Any]]:
    return [dict(item) for item in (value if isinstance(value, list) else []) if isinstance(item, dict)]


def _build_blocker_prompt(blocker: Dict[str, Any]) -> str:
    blocker_dict = blocker if isinstance(blocker, dict) else {}
    primary_objective = _normalize_intake_objective(blocker_dict.get("primary_objective"))
    extraction_targets = _dedupe_text_values(blocker_dict.get("extraction_targets") or [])
    reason = str(blocker_dict.get("reason") or "").strip()
    objective_prompt = _OBJECTIVE_PROMPTS.get(primary_objective, "") if primary_objective else ""
    target_text = f" Extraction targets: {', '.join(extraction_targets)}." if extraction_targets else ""
    if reason and objective_prompt:
        return f"Blocker follow-up: {reason} {objective_prompt}{target_text}".strip()
    if reason:
        return f"Blocker follow-up: {reason}{target_text}".strip()
    if objective_prompt:
        return f"Blocker follow-up: {objective_prompt}{target_text}".strip()
    return ""


def _format_timeline_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        return text


def _chronology_fact_label(fact: Dict[str, Any]) -> str:
    fact_dict = fact if isinstance(fact, dict) else {}
    event_label = str(fact_dict.get("event_label") or "").strip()
    if event_label:
        return event_label
    predicate_family = str(fact_dict.get("predicate_family") or "").strip().replace("_", " ")
    if predicate_family:
        return predicate_family.title()
    return "Event"


def _join_chronology_segments(segments: List[str]) -> str:
    if not segments:
        return ""
    if len(segments) == 1:
        return segments[0]
    if len(segments) == 2:
        return f"{segments[0]} and {segments[1]}"
    return f"{', '.join(segments[:-1])}, and {segments[-1]}"


def _build_anchored_chronology_summary(intake_case_file: Dict[str, Any], *, limit: int = 3) -> List[str]:
    case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
    facts = [dict(item) for item in list(case_file.get("canonical_facts") or []) if isinstance(item, dict)]
    relations = [dict(item) for item in list(case_file.get("timeline_relations") or []) if isinstance(item, dict)]
    if not facts or not relations:
        return []

    fact_by_id = {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if str(fact.get("fact_id") or "").strip()
    }
    relation_records = []
    for relation in relations:
        if str(relation.get("relation_type") or "").strip().lower() != "before":
            continue
        source_id = str(relation.get("source_fact_id") or "").strip()
        target_id = str(relation.get("target_fact_id") or "").strip()
        source_fact = fact_by_id.get(source_id)
        target_fact = fact_by_id.get(target_id)
        if not source_fact or not target_fact:
            continue
        source_date = _format_timeline_date((source_fact.get("temporal_context") or {}).get("start_date") or relation.get("source_start_date"))
        target_date = _format_timeline_date((target_fact.get("temporal_context") or {}).get("start_date") or relation.get("target_start_date"))
        if not source_date or not target_date:
            continue
        relation_records.append(
            {
                "key": (source_id, target_id),
                "source_id": source_id,
                "target_id": target_id,
                "source_fact": source_fact,
                "target_fact": target_fact,
                "source_date": source_date,
                "target_date": target_date,
            }
        )
    if not relation_records:
        return []

    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    incoming_count: Dict[str, int] = {}
    for record in relation_records:
        outgoing.setdefault(record["source_id"], []).append(record)
        incoming_count[record["target_id"]] = incoming_count.get(record["target_id"], 0) + 1
        incoming_count.setdefault(record["source_id"], incoming_count.get(record["source_id"], 0))

    lines: List[str] = []
    seen = set()
    used_keys = set()
    for record in relation_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        if incoming_count.get(record["source_id"], 0) != 0 or len(outgoing.get(record["source_id"], [])) != 1:
            continue
        chain = [record]
        next_id = record["target_id"]
        temp_used = {record["key"]}
        while len(outgoing.get(next_id, [])) == 1 and incoming_count.get(next_id, 0) == 1:
            next_record = outgoing[next_id][0]
            if next_record["key"] in temp_used:
                break
            chain.append(next_record)
            temp_used.add(next_record["key"])
            next_id = next_record["target_id"]
        if len(chain) < 2:
            continue
        segments = [
            f"{_chronology_fact_label(chain[0]['source_fact'])} on {chain[0]['source_date']}"
        ]
        segments.extend(
            f"{_chronology_fact_label(item['target_fact'])} on {item['target_date']}"
            for item in chain
        )
        line = f"{_join_chronology_segments(segments)} occurred in sequence."
        last_target = chain[-1]["target_fact"]
        target_context = last_target.get("temporal_context") if isinstance(last_target.get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f". The later date is currently derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        used_keys.update(temp_used)
        lines.append(line)

    for record in relation_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        source_label = _chronology_fact_label(record["source_fact"])
        target_label = _chronology_fact_label(record["target_fact"])
        line = f"{source_label} on {record['source_date']} preceded {target_label.lower()} on {record['target_date']}."
        target_context = record["target_fact"].get("temporal_context") if isinstance(record["target_fact"].get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f". The later date is currently derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def _build_claim_support_temporal_handoff(intake_case_summary: Any) -> Dict[str, Any]:
    summary = intake_case_summary if isinstance(intake_case_summary, dict) else {}
    packet_summary = summary.get("claim_support_packet_summary")
    packet_summary = packet_summary if isinstance(packet_summary, dict) else {}
    alignment_tasks = summary.get("alignment_evidence_tasks")
    alignment_tasks = alignment_tasks if isinstance(alignment_tasks, list) else []

    def _collect_temporal_registry_identifiers(registry: Any, *keys: str) -> List[str]:
        identifiers: List[str] = []
        for entry in registry if isinstance(registry, list) else []:
            if not isinstance(entry, dict):
                continue
            for key in keys:
                text = str(entry.get(key) or "").strip()
                if text:
                    identifiers.append(text)
                    break
        return _dedupe_text_values(identifiers)

    def _collect_unresolved_temporal_issue_identifiers(registry: Any) -> List[str]:
        issue_ids: List[str] = []
        for entry in registry if isinstance(registry, list) else []:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("current_resolution_status") or entry.get("status") or "open").strip().lower()
            if status in {"resolved", "closed", "complete", "completed"}:
                continue
            issue_id = str(
                entry.get("temporal_issue_id")
                or entry.get("issue_id")
                or entry.get("timeline_issue_id")
                or ""
            ).strip()
            if issue_id:
                issue_ids.append(issue_id)
        return _dedupe_text_values(issue_ids)

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

    raw_event_ids = _collect_temporal_registry_identifiers(
        summary.get("event_ledger"),
        "event_id",
        "temporal_fact_id",
        "fact_id",
    )
    raw_temporal_fact_ids = _collect_temporal_registry_identifiers(
        summary.get("temporal_fact_registry"),
        "temporal_fact_id",
        "fact_id",
        "event_id",
    )
    if not raw_temporal_fact_ids:
        raw_temporal_fact_ids = _collect_temporal_registry_identifiers(
            summary.get("event_ledger"),
            "temporal_fact_id",
            "event_id",
            "fact_id",
        )
    raw_temporal_relation_ids = _collect_temporal_registry_identifiers(
        summary.get("temporal_relation_registry"),
        "temporal_relation_id",
        "relation_id",
    )
    if not raw_temporal_relation_ids:
        raw_temporal_relation_ids = _collect_temporal_registry_identifiers(
            summary.get("timeline_relations"),
            "temporal_relation_id",
            "relation_id",
        )
    raw_temporal_issue_ids = _collect_temporal_registry_identifiers(
        summary.get("temporal_issue_registry"),
        "temporal_issue_id",
        "issue_id",
        "timeline_issue_id",
    )
    raw_unresolved_temporal_issue_ids = _collect_unresolved_temporal_issue_identifiers(
        summary.get("temporal_issue_registry")
    )

    unresolved_temporal_issue_count = int(
        packet_summary.get("claim_support_unresolved_temporal_issue_count", 0) or 0
    )
    if not unresolved_temporal_issue_count and raw_unresolved_temporal_issue_ids:
        unresolved_temporal_issue_count = len(raw_unresolved_temporal_issue_ids)
    if not unresolved_temporal_issue_ids:
        unresolved_temporal_issue_ids = raw_unresolved_temporal_issue_ids

    temporal_handoff = {
        "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
        "unresolved_temporal_issue_ids": unresolved_temporal_issue_ids,
        "chronology_task_count": int(packet_summary.get("temporal_gap_task_count", 0) or 0),
        "event_ids": _dedupe_text_values(event_ids) or raw_event_ids,
        "temporal_fact_ids": _dedupe_text_values(temporal_fact_ids) or raw_temporal_fact_ids,
        "temporal_relation_ids": _dedupe_text_values(temporal_relation_ids) or raw_temporal_relation_ids,
        "timeline_issue_ids": _dedupe_text_values(timeline_issue_ids) or raw_temporal_issue_ids,
        "temporal_issue_ids": _dedupe_text_values(temporal_issue_ids) or raw_temporal_issue_ids,
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


def _build_claim_reasoning_theorem_export_metadata(
    intake_case_summary: Any,
    *,
    claim_type: str,
    claim_element_id: str,
) -> Dict[str, Any]:
    summary = intake_case_summary if isinstance(intake_case_summary, dict) else {}
    packet_summary = summary.get("claim_support_packet_summary")
    packet_summary = packet_summary if isinstance(packet_summary, dict) else {}
    alignment_tasks = summary.get("alignment_evidence_tasks")
    alignment_tasks = alignment_tasks if isinstance(alignment_tasks, list) else []
    temporal_handoff = _build_claim_support_temporal_handoff(summary)
    temporal_handoff = temporal_handoff if isinstance(temporal_handoff, dict) else {}

    normalized_claim_type = str(claim_type or "").strip()
    normalized_claim_element_id = str(claim_element_id or "").strip()
    matching_task: Dict[str, Any] = {}
    fallback_task: Dict[str, Any] = {}

    for task in alignment_tasks:
        if not isinstance(task, dict):
            continue
        task_claim_type = str(task.get("claim_type") or "").strip()
        task_claim_element_id = str(task.get("claim_element_id") or "").strip()
        if normalized_claim_type and task_claim_type == normalized_claim_type and not fallback_task:
            fallback_task = task
        if (
            normalized_claim_type
            and normalized_claim_element_id
            and task_claim_type == normalized_claim_type
            and task_claim_element_id == normalized_claim_element_id
        ):
            matching_task = task
            break

    selected_task = matching_task or fallback_task
    unresolved_temporal_issue_ids = _dedupe_text_values(
        selected_task.get("temporal_issue_ids")
        or temporal_handoff.get("unresolved_temporal_issue_ids")
        or packet_summary.get("claim_support_unresolved_temporal_issue_ids")
        or []
    )
    event_ids = _dedupe_text_values(
        selected_task.get("event_ids") or temporal_handoff.get("event_ids") or []
    )
    temporal_fact_ids = _dedupe_text_values(
        selected_task.get("temporal_fact_ids") or temporal_handoff.get("temporal_fact_ids") or []
    )
    temporal_relation_ids = _dedupe_text_values(
        selected_task.get("temporal_relation_ids") or temporal_handoff.get("temporal_relation_ids") or []
    )
    timeline_issue_ids = _dedupe_text_values(
        selected_task.get("timeline_issue_ids")
        or temporal_handoff.get("timeline_issue_ids")
        or unresolved_temporal_issue_ids
    )
    temporal_issue_ids = _dedupe_text_values(
        selected_task.get("temporal_issue_ids")
        or temporal_handoff.get("temporal_issue_ids")
        or unresolved_temporal_issue_ids
    )
    temporal_proof_bundle_ids = _dedupe_text_values(
        ([selected_task.get("temporal_proof_bundle_id")] if selected_task.get("temporal_proof_bundle_id") else [])
        or temporal_handoff.get("temporal_proof_bundle_ids")
        or []
    )
    temporal_proof_objectives = _dedupe_text_values(
        ([selected_task.get("temporal_proof_objective")] if selected_task.get("temporal_proof_objective") else [])
        or temporal_handoff.get("temporal_proof_objectives")
        or []
    )
    proof_bundle_id = str(
        selected_task.get("temporal_proof_bundle_id")
        or (temporal_proof_bundle_ids[0] if temporal_proof_bundle_ids else "")
    ).strip()
    chronology_task_count = int(
        temporal_handoff.get("chronology_task_count")
        or packet_summary.get("temporal_gap_task_count", 0)
        or 0
    )

    metadata_claim_element_id = str(
        selected_task.get("claim_element_id") or normalized_claim_element_id
    ).strip()

    metadata = {
        "contract_version": "claim_support_temporal_handoff_v1",
        "claim_type": normalized_claim_type,
        "claim_element_id": metadata_claim_element_id,
        "proof_bundle_id": proof_bundle_id,
        "chronology_blocked": bool(
            chronology_task_count
            or unresolved_temporal_issue_ids
            or timeline_issue_ids
            or temporal_issue_ids
        ),
        "chronology_task_count": chronology_task_count,
        "unresolved_temporal_issue_ids": unresolved_temporal_issue_ids,
        "event_ids": event_ids,
        "temporal_fact_ids": temporal_fact_ids,
        "temporal_relation_ids": temporal_relation_ids,
        "timeline_issue_ids": timeline_issue_ids,
        "temporal_issue_ids": temporal_issue_ids,
        "temporal_proof_bundle_ids": temporal_proof_bundle_ids,
        "temporal_proof_objectives": temporal_proof_objectives,
    }
    if not any(
        metadata[key]
        for key in (
            "claim_type",
            "claim_element_id",
            "proof_bundle_id",
            "unresolved_temporal_issue_ids",
            "event_ids",
            "temporal_fact_ids",
            "temporal_relation_ids",
            "timeline_issue_ids",
            "temporal_issue_ids",
            "temporal_proof_bundle_ids",
            "temporal_proof_objectives",
        )
    ) and not metadata["chronology_task_count"]:
        return {}
    return metadata


def _claim_temporal_gap_focus(claim_type: str, claim_name: str) -> Dict[str, set[str]]:
    combined = " ".join([str(claim_type or ""), str(claim_name or "")]).strip().lower()
    issue_families = {"timeline"}
    element_tags = {"timeline"}
    objectives = {"timeline", "exact_dates"}
    if any(token in combined for token in ("retaliat", "reprisal", "protected activity")):
        issue_families.update({"causation", "protected_activity", "adverse_action"})
        element_tags.update({"causation", "protected_activity", "adverse_action"})
        objectives.update({"causation_link", "causation_sequence", "anchor_adverse_action"})
    if any(token in combined for token in ("due process", "grievance", "hearing", "appeal", "review", "notice")):
        issue_families.update({"notice_chain", "hearing_process", "response_timeline"})
        element_tags.update({"notice", "hearing", "appeal", "response", "review"})
        objectives.update({"anchor_appeal_rights", "hearing_request_timing", "response_dates"})
    if any(token in combined for token in ("accommodation", "disabil", "discrimination", "termination", "denial")):
        issue_families.update({"adverse_action", "notice_chain", "response_timeline"})
        element_tags.update({"adverse_action", "response", "notice"})
        objectives.update({"response_dates", "anchor_adverse_action"})
    return {
        "issue_families": issue_families,
        "element_tags": element_tags,
        "objectives": objectives,
    }


def _build_claim_temporal_gap_hints(
    intake_case_file: Dict[str, Any],
    *,
    claim_type: str,
    claim_name: str,
    limit: int = 3,
) -> List[str]:
    case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
    focus = _claim_temporal_gap_focus(claim_type, claim_name)
    normalized_claim_type = str(claim_type or "").strip().lower()
    hints: List[str] = []

    for issue in list(case_file.get("temporal_issue_registry") or []):
        if not isinstance(issue, dict):
            continue
        status = str(issue.get("status") or "open").strip().lower()
        if status not in {"open", "blocking", "warning"}:
            continue
        issue_claim_types = {
            str(item).strip().lower()
            for item in list(issue.get("claim_types") or [])
            if str(item).strip()
        }
        issue_element_tags = {
            str(item).strip().lower()
            for item in list(issue.get("element_tags") or [])
            if str(item).strip()
        }
        if issue_claim_types:
            if normalized_claim_type not in issue_claim_types:
                continue
        elif issue_element_tags and not (issue_element_tags & focus["element_tags"]):
            continue
        summary = str(issue.get("summary") or "").strip()
        if summary:
            hints.append(f"Chronology gap: {summary}")

    blocker_follow_up_summary = (
        case_file.get("blocker_follow_up_summary")
        if isinstance(case_file.get("blocker_follow_up_summary"), dict)
        else {}
    )
    for blocker in list(blocker_follow_up_summary.get("blocking_items") or []):
        if not isinstance(blocker, dict):
            continue
        issue_family = str(blocker.get("issue_family") or "").strip().lower()
        primary_objective = str(blocker.get("primary_objective") or "").strip().lower()
        blocker_objectives = {
            str(item).strip().lower()
            for item in list(blocker.get("blocker_objectives") or [])
            if str(item).strip()
        }
        matched_objectives = ({primary_objective} if primary_objective else set()) | blocker_objectives
        if issue_family:
            if issue_family not in focus["issue_families"] and not (matched_objectives & focus["objectives"]):
                continue
        elif not (matched_objectives & focus["objectives"]):
            continue
        reason = str(blocker.get("reason") or "").strip()
        if reason:
            hints.append(f"Chronology gap: {reason}")

    return _unique_preserving_order(hints)[:limit]


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
        self.llm_config: Dict[str, Any] = {"timeout": DEFAULT_OPTIMIZER_LLM_TIMEOUT_SECONDS}
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
        config_payload = config if isinstance(config, dict) else {}
        self._apply_config(config_payload)
        working_draft = self._refresh_dependent_sections(deepcopy(draft if isinstance(draft, dict) else {}))
        readiness = dict(drafting_readiness) if isinstance(drafting_readiness, dict) else {}
        support_context = self._build_support_context(
            user_id=user_id,
            draft=working_draft,
            drafting_readiness=readiness,
            config=config_payload,
        )
        structured_handoff = (
            support_context.get("structured_handoff")
            if isinstance(support_context.get("structured_handoff"), dict)
            else {}
        )
        document_guardrail = (
            support_context.get("document_generation_guardrail")
            if isinstance(support_context.get("document_generation_guardrail"), dict)
            else {}
        )
        evidence_rows = (
            support_context.get("evidence")
            if isinstance(support_context.get("evidence"), list)
            else []
        )
        evidence_type_counts: Dict[str, int] = {}
        modality_handoff_candidates: List[str] = []
        for row in evidence_rows:
            if not isinstance(row, dict):
                continue
            evidence_type = str(row.get("type") or "").strip().lower()
            if not evidence_type:
                continue
            evidence_type_counts[evidence_type] = evidence_type_counts.get(evidence_type, 0) + 1
            evidence_text = str(row.get("text") or "").strip()
            if evidence_text and evidence_type in {"policy_document", "file_evidence"}:
                if evidence_type == "policy_document":
                    modality_handoff_candidates.append(
                        f"Policy-document evidence anchors formalization follow-up: {evidence_text}"
                    )
                else:
                    modality_handoff_candidates.append(
                        f"File evidence anchors formalization follow-up: {evidence_text}"
                    )
        modality_handoff_lines = self._normalize_lines(modality_handoff_candidates)
        complaint_claim_types = _dedupe_text_values(
            str((claim or {}).get("claim_type") or "").strip().lower()
            for claim in list(working_draft.get("claims_for_relief") or [])
            if isinstance(claim, dict)
        )
        weak_claim_type_targets = {"housing_discrimination", "hacc_research_engine"}
        targeted_weak_claim_type_active = any(
            claim_type in weak_claim_type_targets for claim_type in complaint_claim_types
        )
        unresolved_handoff_objectives = _dedupe_text_values(
            [
                *self._normalize_lines(list(structured_handoff.get("unresolved_objectives") or [])),
                *self._normalize_lines(list(readiness.get("unresolved_objectives") or [])),
                *self._normalize_lines(list(document_guardrail.get("unresolved_objectives") or [])),
            ]
        )
        unresolved_factual_lines = self._normalize_lines(
            list(readiness.get("unresolved_factual_gaps") or [])
            + list(document_guardrail.get("unresolved_factual_gaps") or [])
            + list(structured_handoff.get("unresolved_factual_gaps") or [])
        )
        unresolved_legal_lines = self._normalize_lines(
            list(readiness.get("unresolved_legal_gaps") or [])
            + list(document_guardrail.get("unresolved_legal_gaps") or [])
            + list(structured_handoff.get("unresolved_legal_gaps") or [])
        )
        unresolved_gap_lines = self._normalize_lines(unresolved_factual_lines + unresolved_legal_lines)

        def _contains_anchor(lines: Iterable[Any], tokens: Iterable[str]) -> bool:
            lowered_lines = [str(line or "").strip().lower() for line in lines]
            normalized_tokens = [str(token or "").strip().lower() for token in tokens if str(token or "").strip()]
            for line in lowered_lines:
                if not line:
                    continue
                if any(token in line for token in normalized_tokens):
                    return True
            return False

        grievance_anchor_missing = _contains_anchor(
            unresolved_handoff_objectives + unresolved_gap_lines,
            ("grievance_hearing", "grievance hearing", "hearing request", "hearing"),
        )
        appeal_anchor_missing = _contains_anchor(
            unresolved_handoff_objectives + unresolved_gap_lines,
            ("appeal_rights", "appeal rights", "appeal deadline", "appeal"),
        )
        anchor_follow_up_lines = self._normalize_lines(
            ([
                "Follow-up needed on grievance_hearing: identify hearing request date, decision-maker, response date, and source record."
            ] if grievance_anchor_missing else [])
            + ([
                "Follow-up needed on appeal_rights: identify written notice, appeal deadline, denial/approval date, and source record."
            ] if appeal_anchor_missing else [])
        )
        if structured_handoff:
            blocker_closing_lines = self._normalize_lines(
                list(structured_handoff.get("blocker_closing_answers") or [])
            )
            chronology_anchor_lines = self._normalize_lines(
                [
                    line
                    for line in list(structured_handoff.get("factual_allegation_lines") or [])
                    if _contains_date_anchor(line) or _contains_actor_marker(line) or _contains_causation_link(line)
                ]
            )
            promoted_factual_lines = self._normalize_lines(
                list(structured_handoff.get("factual_allegation_lines") or [])
                + chronology_anchor_lines
                + blocker_closing_lines
                + modality_handoff_lines
                + anchor_follow_up_lines
                + [f"Unresolved factual gap requiring formalization follow-up: {line}" for line in unresolved_factual_lines]
                + [f"Unresolved legal gap requiring formalization follow-up: {line}" for line in unresolved_legal_lines]
                + list(working_draft.get("factual_allegations") or [])
            )
            if promoted_factual_lines:
                working_draft["factual_allegations"] = promoted_factual_lines[:16]

            promoted_summary_lines = self._normalize_lines(
                list(structured_handoff.get("summary_of_facts_lines") or [])
                + anchor_follow_up_lines
                + modality_handoff_lines
                + list(working_draft.get("summary_of_facts") or [])
            )
            if promoted_summary_lines:
                working_draft["summary_of_facts"] = promoted_summary_lines[:14]

            claim_support_by_type = (
                structured_handoff.get("claim_support_lines_by_type")
                if isinstance(structured_handoff.get("claim_support_lines_by_type"), dict)
                else {}
            )
            normalized_claim_support_by_type = {
                str(key).strip().lower(): self._normalize_lines(values or [])
                for key, values in dict(claim_support_by_type).items()
                if str(key).strip()
            }
            shared_claim_support = self._normalize_lines(
                list(structured_handoff.get("claim_support_lines_shared") or [])
                + chronology_anchor_lines
                + blocker_closing_lines
                + modality_handoff_lines
                + anchor_follow_up_lines
                + [f"Open factual gap for claim support: {line}" for line in unresolved_factual_lines]
            )
            claims_for_relief = (
                working_draft.get("claims_for_relief")
                if isinstance(working_draft.get("claims_for_relief"), list)
                else []
            )
            for claim in claims_for_relief:
                if not isinstance(claim, dict):
                    continue
                claim_type = str(claim.get("claim_type") or "").strip()
                claim_specific = self._normalize_lines(
                    normalized_claim_support_by_type.get(claim_type.lower()) or []
                )
                claim["supporting_facts"] = self._normalize_lines(
                    list(claim.get("supporting_facts") or [])
                    + claim_specific
                    + shared_claim_support
                    + blocker_closing_lines
                    + [f"Outstanding legal support issue for this claim: {line}" for line in unresolved_legal_lines]
                )[:12]

            exhibits = working_draft.get("exhibits") if isinstance(working_draft.get("exhibits"), list) else []
            exhibit_lines = self._normalize_lines(
                list(structured_handoff.get("exhibit_description_lines") or [])
                + chronology_anchor_lines
                + blocker_closing_lines
                + modality_handoff_lines
                + anchor_follow_up_lines
                + [f"Gap documented for follow-up evidence collection: {line}" for line in unresolved_factual_lines]
            )
            if exhibits and exhibit_lines:
                for index, exhibit in enumerate(exhibits):
                    if not isinstance(exhibit, dict):
                        continue
                    existing_description = str(exhibit.get("description") or exhibit.get("summary") or "").strip()
                    merged_description = self._normalize_lines(
                        [existing_description, exhibit_lines[index % len(exhibit_lines)]]
                    )
                    if merged_description:
                        exhibit["description"] = merged_description[0]
            elif exhibit_lines and not exhibits:
                working_draft["exhibits"] = [
                    {
                        "label": f"Exhibit {chr(65 + idx)}",
                        "title": (
                            "Policy/file evidence and intake handoff"
                            if modality_handoff_lines
                            else "Intake and evidence handoff"
                        ),
                        "summary": line,
                        "description": line,
                    }
                    for idx, line in enumerate(exhibit_lines[:4])
                ]
        support_context["packet_projection"] = self._build_packet_projection(working_draft)
        assessment_blocked = bool(document_guardrail.get("assessment_blocked"))
        guardrail_blockers = _dedupe_text_values(document_guardrail.get("blockers") or [])
        readiness_unresolved_factual = unresolved_factual_lines
        readiness_unresolved_legal = unresolved_legal_lines
        explicit_anchor_warnings = self._normalize_lines(
            ([
                "Explicit grievance_hearing questioning remains required before formalization."
            ] if grievance_anchor_missing else [])
            + ([
                "Explicit appeal_rights questioning remains required before formalization."
            ] if appeal_anchor_missing else [])
        )
        readiness_warning_messages = _dedupe_text_values(
            [
                str((warning or {}).get("message") or "").strip()
                for warning in list(readiness.get("warnings") or [])
                if isinstance(warning, dict) and str((warning or {}).get("message") or "").strip()
            ]
            + ([str(document_guardrail.get("summary") or "").strip()] if str(document_guardrail.get("summary") or "").strip() else [])
            + explicit_anchor_warnings
            + (
                [
                    f"Formalization gate unresolved factual gap: {line}"
                    for line in readiness_unresolved_factual
                ]
            )
            + (
                [
                    f"Formalization gate unresolved legal gap: {line}"
                    for line in readiness_unresolved_legal
                ]
            )
        )
        graph_signals = (
            dict(readiness.get("graph_completeness_signals") or {})
            if isinstance(readiness.get("graph_completeness_signals"), dict)
            else {}
        )
        if isinstance(support_context.get("graph_completeness_signals"), dict):
            graph_signals.update(dict(support_context.get("graph_completeness_signals") or {}))
        if isinstance(document_guardrail.get("graph_completeness_signals"), dict):
            graph_signals.update(dict(document_guardrail.get("graph_completeness_signals") or {}))
        graph_status = str(
            document_guardrail.get("graph_phase_status")
            or graph_signals.get("status")
            or readiness.get("graph_phase_status")
            or "ready"
        ).strip().lower()
        graph_remaining_gap_count = max(
            _safe_int(document_guardrail.get("graph_remaining_gap_count"), 0),
            _safe_int(graph_signals.get("remaining_gap_count"), 0),
            _safe_int(graph_signals.get("current_gap_count"), 0),
            _safe_int(readiness.get("graph_remaining_gap_count"), 0),
            len(readiness_unresolved_factual),
            len(readiness_unresolved_legal),
        )
        graph_gate_requested = bool(document_guardrail.get("gate_on_graph_completeness")) or bool(
            graph_signals.get("gate_on_graph_completeness")
        )
        graph_gate_active = graph_gate_requested or graph_status not in {"ready", "complete", "completed", "ok"} or graph_remaining_gap_count > 0
        if graph_gate_active:
            readiness_warning_messages = _dedupe_text_values(
                readiness_warning_messages + [
                    f"Graph completeness gate remains active (status={graph_status}, remaining_gap_count={graph_remaining_gap_count})."
                ]
            )
        missing_policy_document = bool(
            targeted_weak_claim_type_active and evidence_type_counts.get("policy_document", 0) <= 0
        )
        missing_file_evidence = bool(
            targeted_weak_claim_type_active and evidence_type_counts.get("file_evidence", 0) <= 0
        )
        if targeted_weak_claim_type_active:
            if missing_policy_document:
                readiness_warning_messages = _dedupe_text_values(
                    readiness_warning_messages
                    + [
                        "Housing-discrimination drafting requires at least one policy_document evidence anchor before formalization."
                    ]
                )
            if missing_file_evidence:
                readiness_warning_messages = _dedupe_text_values(
                    readiness_warning_messages
                    + [
                        "Housing-discrimination drafting requires at least one file_evidence anchor before formalization."
                    ]
                )
        formalization_gate_active = any(
            (
                assessment_blocked,
                graph_gate_active,
                bool(readiness_unresolved_factual),
                bool(readiness_unresolved_legal),
                grievance_anchor_missing,
                appeal_anchor_missing,
                missing_policy_document,
                missing_file_evidence,
            )
        )
        readiness_blockers = _dedupe_text_values(
            list(readiness.get("blockers") or [])
            + guardrail_blockers
            + (["graph_analysis_not_ready"] if graph_gate_active else [])
            + (["document_generation_not_ready"] if assessment_blocked else [])
            + (["unresolved_factual_gaps"] if readiness_unresolved_factual else [])
            + (["unresolved_legal_gaps"] if readiness_unresolved_legal else [])
            + (["missing_policy_document_evidence"] if missing_policy_document else [])
            + (["missing_file_evidence"] if missing_file_evidence else [])
            + (["grievance_hearing_follow_up_required"] if grievance_anchor_missing else [])
            + (["appeal_rights_follow_up_required"] if appeal_anchor_missing else [])
        )
        readiness_status = str(readiness.get("status") or "ready").strip().lower()
        if formalization_gate_active:
            readiness_status = "blocked"
        elif readiness_warning_messages or readiness_blockers:
            readiness_status = "warning"
        readiness_for_critic = dict(readiness)
        readiness_for_critic["status"] = readiness_status
        readiness_for_critic["phase_status"] = (
            str(readiness.get("phase_status") or document_guardrail.get("phase_status") or readiness_status).strip().lower()
            or readiness_status
        )
        readiness_for_critic["blockers"] = readiness_blockers
        readiness_for_critic["unresolved_factual_gaps"] = readiness_unresolved_factual
        readiness_for_critic["unresolved_legal_gaps"] = readiness_unresolved_legal
        readiness_for_critic["warnings"] = [{"message": message} for message in readiness_warning_messages]
        readiness_for_critic["warning_count"] = len(readiness_warning_messages)
        readiness_for_critic["formalization_gate"] = {
            "active": bool(formalization_gate_active),
            "assessment_blocked": bool(assessment_blocked),
            "graph_gate_active": bool(graph_gate_active),
            "grievance_anchor_missing": bool(grievance_anchor_missing),
            "appeal_anchor_missing": bool(appeal_anchor_missing),
            "missing_policy_document_evidence": bool(missing_policy_document),
            "missing_file_evidence": bool(missing_file_evidence),
            "unresolved_factual_gap_count": len(readiness_unresolved_factual),
            "unresolved_legal_gap_count": len(readiness_unresolved_legal),
            "blocker_count": len(readiness_blockers),
        }
        readiness_for_critic["evidence_modality_signals"] = {
            "policy_document_count": int(evidence_type_counts.get("policy_document") or 0),
            "file_evidence_count": int(evidence_type_counts.get("file_evidence") or 0),
            "targeted_weak_claim_type_active": bool(targeted_weak_claim_type_active),
            "missing_policy_document_evidence": bool(missing_policy_document),
            "missing_file_evidence": bool(missing_file_evidence),
        }
        readiness_for_critic["graph_completeness_signals"] = {
            **graph_signals,
            "status": graph_status,
            "remaining_gap_count": graph_remaining_gap_count,
            "current_gap_count": graph_remaining_gap_count,
            "gate_on_graph_completeness": graph_gate_active,
        }
        initial_review = self._run_critic(
            draft=working_draft,
            drafting_readiness=readiness_for_critic,
            support_context=support_context,
        )
        current_review = initial_review
        iterations: List[Dict[str, Any]] = []
        accepted_iterations = 0
        optimized_sections: List[str] = []

        for iteration in range(1, self.max_iterations + 1):
            if formalization_gate_active:
                break
            if float(current_review.get("overall_score") or 0.0) >= self.target_score:
                break

            focus_section = self._choose_focus_section(
                current_review=current_review,
                draft=working_draft,
                drafting_readiness=readiness_for_critic,
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
                drafting_readiness=readiness_for_critic,
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
                support_context["packet_projection"] = self._build_packet_projection(working_draft)
        support_context["packet_projection"] = self._build_packet_projection(working_draft)

        upstream_optimizer = self._build_upstream_optimizer_metadata(
            phase_focus_order=current_review.get("workflow_phase_order") if isinstance(current_review, dict) else None
        )
        intake_status = build_intake_status_summary(self.mediator)
        intake_constraints = build_intake_warning_entries(intake_status)
        intake_case_summary = build_intake_case_review_summary(self.mediator)
        claim_support_temporal_handoff = _build_claim_support_temporal_handoff(intake_case_summary)
        claim_reasoning_review = self._build_claim_reasoning_review(
            intake_case_summary=intake_case_summary,
            support_context=support_context,
            user_id=user_id,
        )
        initial_document_provenance_summary = (
            dict(draft.get("document_provenance_summary") or {})
            if isinstance(draft.get("document_provenance_summary"), dict)
            else {}
        )
        workflow_optimization_guidance = self._build_workflow_optimization_guidance(
            drafting_readiness=readiness_for_critic,
            support_context=support_context,
            intake_status=intake_status,
            intake_case_summary=intake_case_summary,
            claim_reasoning_review=claim_reasoning_review,
            claim_support_temporal_handoff=claim_support_temporal_handoff,
        )
        intake_summary_handoff = {}
        if isinstance(intake_status.get("intake_summary_handoff"), dict) and intake_status.get("intake_summary_handoff"):
            intake_summary_handoff = dict(intake_status["intake_summary_handoff"])
        elif isinstance(intake_case_summary.get("intake_summary_handoff"), dict) and intake_case_summary.get("intake_summary_handoff"):
            intake_summary_handoff = dict(intake_case_summary["intake_summary_handoff"])
        document_evidence_targeting_summary = self._build_document_evidence_targeting_summary(iterations)
        document_workflow_execution_summary = self._build_document_workflow_execution_summary(iterations)
        workflow_targeting_summary = _build_workflow_targeting_summary(
            existing_summary=intake_case_summary.get("workflow_targeting_summary"),
            document_evidence_targeting_summary=document_evidence_targeting_summary,
        )
        document_execution_drift_summary = _build_document_execution_drift_summary(
            workflow_targeting_summary=workflow_targeting_summary,
            document_workflow_execution_summary=document_workflow_execution_summary,
        )
        final_document_provenance_summary = (
            dict(working_draft.get("document_provenance_summary") or {})
            if isinstance(working_draft.get("document_provenance_summary"), dict)
            else {}
        )
        document_grounding_improvement_summary = _build_document_grounding_improvement_summary(
            initial_document_provenance_summary=initial_document_provenance_summary,
            final_document_provenance_summary=final_document_provenance_summary,
            workflow_optimization_guidance=workflow_optimization_guidance,
        )
        document_grounding_lane_outcome_summary = _build_document_grounding_lane_outcome_summary(
            document_grounding_improvement_summary=document_grounding_improvement_summary,
            document_workflow_execution_summary=document_workflow_execution_summary,
        )
        if workflow_targeting_summary:
            workflow_optimization_guidance["workflow_targeting_summary"] = dict(workflow_targeting_summary)
        if document_workflow_execution_summary:
            workflow_optimization_guidance["document_workflow_execution_summary"] = dict(
                document_workflow_execution_summary
            )
        if document_execution_drift_summary:
            workflow_optimization_guidance["document_execution_drift_summary"] = dict(
                document_execution_drift_summary
            )
        if document_grounding_improvement_summary:
            workflow_optimization_guidance["document_grounding_improvement_summary"] = dict(
                document_grounding_improvement_summary
            )
        if document_grounding_lane_outcome_summary:
            workflow_optimization_guidance["document_grounding_lane_outcome_summary"] = dict(
                document_grounding_lane_outcome_summary
            )
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
                "workflow_optimization_guidance": workflow_optimization_guidance,
                "workflow_targeting_summary": workflow_targeting_summary,
                "document_workflow_execution_summary": document_workflow_execution_summary,
                "document_execution_drift_summary": document_execution_drift_summary,
                "document_grounding_improvement_summary": document_grounding_improvement_summary,
                "document_grounding_lane_outcome_summary": document_grounding_lane_outcome_summary,
                "support_context": support_context,
                "drafting_readiness": readiness_for_critic,
                "initial_review": initial_review,
                "final_review": current_review,
                "iterations": iterations,
            }
        )
        final_status = "blocked" if formalization_gate_active else ("optimized" if accepted_iterations else "completed")
        return {
            "status": final_status,
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
            "workflow_optimization_guidance": workflow_optimization_guidance,
            "actor_critic_priority": int(
                (support_context.get("actor_critic") or {}).get("priority")
                if isinstance(support_context.get("actor_critic"), dict)
                else 70
            ),
            "actor_critic_metrics": dict(
                (support_context.get("actor_critic") or {}).get("metrics")
                if isinstance(support_context.get("actor_critic"), dict)
                else {}
            ),
            "baseline_metrics": dict(
                (support_context.get("actor_critic") or {}).get("baseline_metrics")
                if isinstance(support_context.get("actor_critic"), dict)
                else {}
            ),
            "adversarial_session_flow": dict(document_guardrail),
            "successful_session_count": int(document_guardrail.get("successful_session_count") or 0),
            "session_count": int(document_guardrail.get("session_count") or 0),
            "assessment_blocked": bool(document_guardrail.get("assessment_blocked")),
            "drafting_readiness": readiness_for_critic,
            "workflow_targeting_summary": workflow_targeting_summary,
            "document_workflow_execution_summary": document_workflow_execution_summary,
            "document_execution_drift_summary": document_execution_drift_summary,
            "document_grounding_improvement_summary": document_grounding_improvement_summary,
            "document_grounding_lane_outcome_summary": document_grounding_lane_outcome_summary,
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

    def _build_workflow_optimization_guidance(
        self,
        *,
        drafting_readiness: Dict[str, Any],
        support_context: Dict[str, Any],
        intake_status: Dict[str, Any],
        intake_case_summary: Dict[str, Any],
        claim_reasoning_review: Dict[str, Any],
        claim_support_temporal_handoff: Dict[str, Any],
    ) -> Dict[str, Any]:
        intake_sections = (
            intake_case_summary.get("intake_sections")
            if isinstance(intake_case_summary.get("intake_sections"), dict)
            else {}
        )
        question_summary = (
            intake_case_summary.get("question_candidate_summary")
            if isinstance(intake_case_summary.get("question_candidate_summary"), dict)
            else {}
        )
        evidence_summary = (
            intake_case_summary.get("proof_lead_summary")
            if isinstance(intake_case_summary.get("proof_lead_summary"), dict)
            else {}
        )
        evidence_workflow_action_queue = (
            intake_case_summary.get("evidence_workflow_action_queue")
            if isinstance(intake_case_summary.get("evidence_workflow_action_queue"), list)
            else []
        )
        evidence_workflow_action_summary = (
            intake_case_summary.get("evidence_workflow_action_summary")
            if isinstance(intake_case_summary.get("evidence_workflow_action_summary"), dict)
            else {}
        )
        evidence_rows = support_context.get("evidence") if isinstance(support_context.get("evidence"), list) else []
        evidence_modalities = _unique_preserving_order(
            str((row or {}).get("type") or "").strip() for row in evidence_rows if isinstance(row, dict)
        )
        temporal_issue_registry_summary = summarize_temporal_issue_registry(
            intake_case_summary.get("temporal_issue_registry_summary")
        )
        unresolved_temporal_issue_count = int(temporal_issue_registry_summary.get("unresolved_count") or 0)
        resolved_temporal_issue_count = int(temporal_issue_registry_summary.get("resolved_count") or 0)
        claim_types = _unique_preserving_order(
            [
                *[
                    str((claim or {}).get("claim_type") or "").strip()
                    for claim in (support_context.get("claims") or [])
                    if isinstance(claim, dict)
                ],
                *[
                    str((claim or {}).get("claim_type") or "").strip()
                    for claim in (intake_case_summary.get("candidate_claims") or [])
                    if isinstance(claim, dict)
                ],
            ]
        )
        uncovered_objectives = _dedupe_text_values(
            (support_context.get("intake_priorities") or {}).get("uncovered_objectives") or []
        )
        intake_focus_areas = _unique_preserving_order(
            [
                *[
                    str(section_name)
                    for section_name, section_payload in intake_sections.items()
                    if isinstance(section_payload, dict) and str(section_payload.get("status") or "").strip().lower() != "complete"
                ],
                *uncovered_objectives,
            ]
        )
        graph_focus_areas = _unique_preserving_order(
            [
                *[
                    str((claim or {}).get("claim_type") or "").strip()
                    for claim in (support_context.get("claims") or [])
                    if isinstance(claim, dict) and (
                        claim.get("missing_elements") or claim.get("partially_supported_elements")
                    )
                ],
                *[
                    str(item)
                    for item in (claim_support_temporal_handoff.get("temporal_proof_objectives") or [])
                    if str(item).strip()
                ],
                *[
                    str((action or {}).get("claim_element_label") or (action or {}).get("claim_element_id") or "").strip()
                    for action in evidence_workflow_action_queue
                    if isinstance(action, dict)
                ],
            ]
        )
        draft_warnings = [
            str((warning or {}).get("message") or "").strip()
            for warning in (drafting_readiness.get("warnings") or [])
            if isinstance(warning, dict) and str((warning or {}).get("message") or "").strip()
        ]
        document_focus_areas = _unique_preserving_order(
            [
                *[
                    str(section_name)
                    for section_name, section_payload in dict(drafting_readiness.get("sections") or {}).items()
                    if isinstance(section_payload, dict) and str(section_payload.get("status") or "").strip().lower() != "ready"
                ],
                *draft_warnings,
            ]
        )
        cross_phase_findings: List[str] = []
        if intake_focus_areas and graph_focus_areas:
            cross_phase_findings.append(
                "Unresolved intake objectives are still suppressing graph-ready claim support and should be closed before final drafting."
            )
        if graph_focus_areas and document_focus_areas:
            cross_phase_findings.append(
                "Graph support gaps are flowing through into document readiness warnings, so claim support and chronology gaps should be resolved before final complaint export."
            )
        if claim_support_temporal_handoff.get("unresolved_temporal_issue_count"):
            cross_phase_findings.append(
                "Temporal support gaps remain unresolved and may weaken both causation analysis and chronology-driven complaint allegations."
            )
        elif resolved_temporal_issue_count > 0:
            cross_phase_findings.append(
                "Resolved chronology history is retained and should still be preserved in factual allegations and claim support to maintain the causation sequence."
            )

        return {
            "phase_scorecards": {
                "intake_questioning": {
                    "status": "warning" if intake_focus_areas else "ready",
                    "focus_areas": intake_focus_areas,
                    "question_candidate_count": int(question_summary.get("count") or 0),
                    "proof_lead_count": int(evidence_summary.get("count") or 0),
                },
                "graph_analysis": {
                    "status": "warning" if graph_focus_areas else "ready",
                    "focus_areas": graph_focus_areas,
                    "claim_types": claim_types,
                    "evidence_modalities": evidence_modalities,
                    "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
                    "resolved_temporal_issue_count": resolved_temporal_issue_count,
                    "evidence_workflow_action_count": int(evidence_workflow_action_summary.get("count") or 0),
                },
                "document_generation": {
                    "status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
                    "focus_areas": document_focus_areas,
                    "warning_count": int(drafting_readiness.get("warning_count") or 0),
                },
            },
            "cross_phase_findings": cross_phase_findings,
            "workflow_action_queue": [
                *[
                    {
                        "rank": int(action.get("rank") or index + 1),
                        "phase_name": str(action.get("phase_name") or "graph_analysis").strip() or "graph_analysis",
                        "status": str(action.get("status") or "warning").strip().lower() or "warning",
                        "action": str(action.get("action") or "").strip(),
                        "focus_areas": list(action.get("focus_areas") or [])[:3],
                        "claim_type": str(action.get("claim_type") or "").strip(),
                        "claim_element_id": str(action.get("claim_element_id") or "").strip(),
                    }
                    for index, action in enumerate(evidence_workflow_action_queue[:2])
                    if isinstance(action, dict) and str(action.get("action") or "").strip()
                ],
                {
                    "rank": 100,
                    "phase_name": "graph_analysis",
                    "status": "warning" if graph_focus_areas else "ready",
                    "action": "Close graph and claim-support gaps before final drafting.",
                    "focus_areas": graph_focus_areas[:3],
                },
                {
                    "rank": 101,
                    "phase_name": "document_generation",
                    "status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
                    "action": "Revise complaint sections still flagged by drafting readiness.",
                    "focus_areas": document_focus_areas[:3],
                },
            ],
            "complaint_type_generalization_summary": {
                "complaint_types": claim_types,
                "complaint_type_count": len(claim_types),
            },
            "evidence_modality_generalization_summary": {
                "evidence_modalities": evidence_modalities,
                "evidence_modality_count": len(evidence_modalities),
            },
            "evidence_workflow_action_queue": list(evidence_workflow_action_queue),
            "evidence_workflow_action_summary": dict(evidence_workflow_action_summary),
            "document_handoff_summary": {
                "ready_for_document_optimization": str(drafting_readiness.get("status") or "").strip().lower() == "ready",
                "drafting_status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
                "blocking_warning_count": int(drafting_readiness.get("warning_count") or 0),
            },
            "intake_status": {
                "current_phase": str(intake_status.get("phase") or intake_status.get("current_phase") or "").strip(),
                "ready_to_advance": bool(intake_status.get("ready_to_advance", intake_status.get("ready", False))),
            },
            "claim_reasoning_review": dict(claim_reasoning_review or {}),
        }

    @staticmethod
    def _build_document_evidence_targeting_summary(iterations: Any) -> Dict[str, Any]:
        summary = {
            "count": 0,
            "focus_section_counts": {},
            "claim_type_counts": {},
            "claim_element_counts": {},
            "support_kind_counts": {},
            "targets": [],
        }

        for entry in iterations if isinstance(iterations, list) else []:
            if not isinstance(entry, dict):
                continue
            focus_section = str(entry.get("focus_section") or "").strip()
            selected_support_context = (
                entry.get("selected_support_context")
                if isinstance(entry.get("selected_support_context"), dict)
                else {}
            )
            top_support = selected_support_context.get("top_support")
            for row in top_support if isinstance(top_support, list) else []:
                if not isinstance(row, dict):
                    continue
                kind = str(row.get("kind") or "").strip().lower()
                if kind not in {"evidence_workflow_action", "workflow_action"}:
                    continue

                claim_type = str(row.get("claim_type") or "").strip()
                claim_element_id = str(row.get("claim_element_id") or "").strip()
                preferred_support_kind = str(row.get("preferred_support_kind") or "").strip()
                text = str(row.get("text") or "").strip()

                summary["count"] += 1
                if focus_section:
                    summary["focus_section_counts"][focus_section] = (
                        summary["focus_section_counts"].get(focus_section, 0) + 1
                    )
                if claim_type:
                    summary["claim_type_counts"][claim_type] = (
                        summary["claim_type_counts"].get(claim_type, 0) + 1
                    )
                if claim_element_id:
                    summary["claim_element_counts"][claim_element_id] = (
                        summary["claim_element_counts"].get(claim_element_id, 0) + 1
                    )
                if preferred_support_kind:
                    summary["support_kind_counts"][preferred_support_kind] = (
                        summary["support_kind_counts"].get(preferred_support_kind, 0) + 1
                    )
                summary["targets"].append(
                    {
                        "focus_section": focus_section,
                        "claim_type": claim_type,
                        "claim_element_id": claim_element_id,
                        "preferred_support_kind": preferred_support_kind,
                        "kind": kind,
                        "text": text,
                    }
                )

        return summary

    @staticmethod
    def _build_document_workflow_execution_summary(iterations: Any) -> Dict[str, Any]:
        summary = {
            "iteration_count": 0,
            "accepted_iteration_count": 0,
            "focus_section_counts": {},
            "top_support_kind_counts": {},
            "targeted_claim_element_counts": {},
            "preferred_support_kind_counts": {},
            "first_focus_section": "",
            "first_top_support_kind": "",
            "first_targeted_claim_element": "",
            "first_preferred_support_kind": "",
        }

        first_focus_section = ""
        first_top_support_kind = ""
        first_targeted_claim_element = ""
        first_preferred_support_kind = ""

        for entry in iterations if isinstance(iterations, list) else []:
            if not isinstance(entry, dict):
                continue
            summary["iteration_count"] += 1
            if bool(entry.get("accepted")):
                summary["accepted_iteration_count"] += 1
            focus_section = str(entry.get("focus_section") or "").strip()
            if focus_section:
                summary["focus_section_counts"][focus_section] = (
                    summary["focus_section_counts"].get(focus_section, 0) + 1
                )
                if not first_focus_section:
                    first_focus_section = focus_section
            selected_support_context = (
                entry.get("selected_support_context")
                if isinstance(entry.get("selected_support_context"), dict)
                else {}
            )
            top_support = selected_support_context.get("top_support")
            top_row = top_support[0] if isinstance(top_support, list) and top_support else {}
            if not isinstance(top_row, dict):
                top_row = {}
            support_kind = str(top_row.get("kind") or "").strip()
            if support_kind:
                summary["top_support_kind_counts"][support_kind] = (
                    summary["top_support_kind_counts"].get(support_kind, 0) + 1
                )
                if not first_top_support_kind:
                    first_top_support_kind = support_kind
            claim_element_id = str(top_row.get("claim_element_id") or "").strip()
            if claim_element_id:
                summary["targeted_claim_element_counts"][claim_element_id] = (
                    summary["targeted_claim_element_counts"].get(claim_element_id, 0) + 1
                )
                if not first_targeted_claim_element:
                    first_targeted_claim_element = claim_element_id
            preferred_support_kind = str(top_row.get("preferred_support_kind") or "").strip()
            if preferred_support_kind:
                summary["preferred_support_kind_counts"][preferred_support_kind] = (
                    summary["preferred_support_kind_counts"].get(preferred_support_kind, 0) + 1
                )
                if not first_preferred_support_kind:
                    first_preferred_support_kind = preferred_support_kind

        summary["first_focus_section"] = first_focus_section
        summary["first_top_support_kind"] = first_top_support_kind
        summary["first_targeted_claim_element"] = first_targeted_claim_element
        summary["first_preferred_support_kind"] = first_preferred_support_kind
        return summary

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
        self.llm_config = {"timeout": DEFAULT_OPTIMIZER_LLM_TIMEOUT_SECONDS}
        if isinstance(llm_config, dict):
            self.llm_config.update({str(key): value for key, value in llm_config.items()})

    def _build_support_context(
        self,
        *,
        user_id: Optional[str],
        draft: Dict[str, Any],
        drafting_readiness: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config_payload = config if isinstance(config, dict) else {}
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

        phase_manager = getattr(self.mediator, "phase_manager", None)
        intake_case_file = {}
        if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
            try:
                intake_case_file = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {}
            except Exception:
                intake_case_file = {}
        intake_case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
        intake_case_summary = build_intake_case_review_summary(self.mediator)
        intake_case_summary = intake_case_summary if isinstance(intake_case_summary, dict) else {}
        fallback_temporal_issue_registry_summary = summarize_temporal_issue_registry(
            intake_case_summary.get("temporal_issue_registry_summary")
        )
        fallback_packet_summary = (
            intake_case_summary.get("claim_support_packet_summary")
            if isinstance(intake_case_summary.get("claim_support_packet_summary"), dict)
            else {}
        )
        fallback_alignment_task_summary = (
            intake_case_summary.get("alignment_task_summary")
            if isinstance(intake_case_summary.get("alignment_task_summary"), dict)
            else {}
        )

        claim_contexts = []
        claim_temporal_gap_summary = []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get("claim_type") or claim.get("count_title") or "").strip()
            claim_name = str(claim.get("count_title") or claim.get("claim_type") or "").strip()
            support_facts = self._call_mediator("get_claim_support_facts", claim_type=claim_type, user_id=user_id) or []
            overview = self._call_mediator("get_claim_overview", claim_type=claim_type, user_id=user_id) or {}
            overview_claim = {}
            if isinstance(overview, dict):
                overview_claims = overview.get("claims") if isinstance(overview.get("claims"), dict) else {}
                overview_claim = overview_claims.get(claim_type) if isinstance(overview_claims.get(claim_type), dict) else {}
            support_summary = support_summary_claims.get(claim_type) if isinstance(support_summary_claims.get(claim_type), dict) else {}
            readiness_entry = readiness_by_claim.get(claim_type, {})
            support_texts = self._extract_support_texts(support_facts)
            temporal_gap_hints = _build_claim_temporal_gap_hints(
                intake_case_file,
                claim_type=claim_type,
                claim_name=claim_name,
            )
            missing_elements = _unique_preserving_order(
                [
                    *self._extract_element_texts(overview_claim.get("missing")),
                    *self._normalize_lines(claim.get("missing_elements") or []),
                    *temporal_gap_hints,
                ]
            )
            claim_contexts.append(
                {
                    "claim_type": claim_type,
                    "missing_elements": missing_elements,
                    "partially_supported_elements": self._extract_element_texts(overview_claim.get("partially_supported")),
                    "support_summary": {
                        "total_elements": int(support_summary.get("total_elements") or claim.get("support_summary", {}).get("total_elements") or 0),
                        "covered_elements": int(support_summary.get("covered_elements") or claim.get("support_summary", {}).get("covered_elements") or 0),
                        "uncovered_elements": int(support_summary.get("uncovered_elements") or claim.get("support_summary", {}).get("uncovered_elements") or 0),
                        "source_family_counts": dict(support_summary.get("support_packet_summary", {}).get("source_family_counts") or claim.get("support_summary", {}).get("source_family_counts") or {}),
                        "temporal_gap_hint_count": int(
                            claim.get("support_summary", {}).get("temporal_gap_hint_count") or len(temporal_gap_hints)
                        ),
                    },
                    "support_facts": support_texts[:8],
                    "readiness_warnings": [
                        str(item.get("message") or "").strip()
                        for item in readiness_entry.get("warnings", [])
                        if isinstance(item, dict) and str(item.get("message") or "").strip()
                    ],
                }
            )
            if temporal_gap_hints:
                claim_temporal_gap_summary.append(
                    {
                        "claim_type": claim_type,
                        "gap_count": len(temporal_gap_hints),
                        "gaps": temporal_gap_hints,
                    }
                )

        intake_status = build_intake_status_summary(self.mediator)
        workflow_guidance = (
            drafting_readiness.get("workflow_optimization_guidance")
            if isinstance(drafting_readiness.get("workflow_optimization_guidance"), dict)
            else {}
        )
        document_drafting_next_action = (
            workflow_guidance.get("document_drafting_next_action")
            if isinstance(workflow_guidance.get("document_drafting_next_action"), dict)
            else intake_status.get("document_drafting_next_action")
        )
        document_drafting_next_action = (
            dict(document_drafting_next_action)
            if isinstance(document_drafting_next_action, dict)
            else {}
        )
        document_grounding_improvement_next_action = (
            workflow_guidance.get("document_grounding_improvement_next_action")
            if isinstance(workflow_guidance.get("document_grounding_improvement_next_action"), dict)
            else intake_status.get("document_grounding_improvement_next_action")
        )
        document_grounding_improvement_next_action = (
            dict(document_grounding_improvement_next_action)
            if isinstance(document_grounding_improvement_next_action, dict)
            else {}
        )
        intake_handoff = intake_status.get("intake_summary_handoff") if isinstance(intake_status, dict) else {}
        intake_handoff = intake_handoff if isinstance(intake_handoff, dict) else {}
        blocker_follow_up_summary = intake_case_file.get("blocker_follow_up_summary") if isinstance(intake_case_file.get("blocker_follow_up_summary"), dict) else {}
        blocker_items = _normalize_blocker_records(blocker_follow_up_summary.get("blocking_items"))
        open_items = _normalize_blocker_records(intake_case_file.get("open_items"))
        blocker_open_items = [
            item for item in open_items
            if str(item.get("kind") or "").strip().lower() == "blocker_follow_up"
        ]
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
        blocker_objectives = _normalize_intake_objectives(
            list(blocker_follow_up_summary.get("blocking_objectives") or [])
            + [objective for blocker in blocker_items for objective in list(blocker.get("blocker_objectives") or [])]
            + [item.get("primary_objective") for item in blocker_open_items]
        )
        blocker_extraction_targets = _dedupe_text_values(
            list(blocker_follow_up_summary.get("extraction_targets") or [])
            + [target for blocker in blocker_items for target in list(blocker.get("extraction_targets") or [])]
            + [target for item in blocker_open_items for target in list(item.get("extraction_targets") or [])]
        )
        blocker_workflow_phases = _dedupe_text_values(
            list(blocker_follow_up_summary.get("workflow_phases") or [])
            + [phase for blocker in blocker_items for phase in list(blocker.get("workflow_phases") or [])]
            + [phase for item in blocker_open_items for phase in list(item.get("workflow_phases") or [])]
        )
        blocker_issue_families = _dedupe_text_values(
            [blocker.get("issue_family") for blocker in blocker_items]
            + [item.get("issue_family") for item in blocker_open_items]
        )
        unresolved_objectives = _dedupe_text_values(
            list(uncovered_objectives)
            + list(blocker_objectives)
            + [key for key, count in objective_question_counts.items() if count <= 0]
        )
        critical_unresolved = [
            objective
            for objective in _INTAKE_OBJECTIVE_PRIORITY
            if objective in unresolved_objectives
        ]
        blocker_follow_up_prompts = _dedupe_text_values(
            [_build_blocker_prompt(blocker) for blocker in blocker_items]
            + [_build_blocker_prompt(item) for item in blocker_open_items]
        )
        anchored_chronology_summary = _build_anchored_chronology_summary(intake_case_file)
        temporal_issue_registry = intake_case_file.get("temporal_issue_registry") if isinstance(intake_case_file.get("temporal_issue_registry"), list) else []
        case_file_temporal_issue_registry_summary = summarize_temporal_issue_registry(
            {
                "count": len(temporal_issue_registry),
                "issues": temporal_issue_registry,
            }
        )
        temporal_issue_status_counts = dict(fallback_temporal_issue_registry_summary.get("status_counts") or {})
        for status_name, count in dict(case_file_temporal_issue_registry_summary.get("status_counts") or {}).items():
            temporal_issue_status_counts[str(status_name)] = max(
                int(temporal_issue_status_counts.get(str(status_name)) or 0),
                int(count or 0),
            )
        unresolved_temporal_issue_count = max(
            int(case_file_temporal_issue_registry_summary.get("unresolved_count") or 0),
            int(fallback_temporal_issue_registry_summary.get("unresolved_count") or 0),
            int(fallback_packet_summary.get("claim_support_unresolved_temporal_issue_count") or 0),
        )
        resolved_temporal_issue_count = max(
            int(case_file_temporal_issue_registry_summary.get("resolved_count") or 0),
            int(fallback_temporal_issue_registry_summary.get("resolved_count") or 0),
        )
        temporal_issue_count = max(
            len(temporal_issue_registry),
            int(case_file_temporal_issue_registry_summary.get("count") or 0),
            int(fallback_temporal_issue_registry_summary.get("count") or 0),
            unresolved_temporal_issue_count + resolved_temporal_issue_count,
        )

        metric_aliases = {
            "empathy_avg": "empathy",
            "avg_empathy": "empathy",
            "question_quality_avg": "question_quality",
            "avg_question_quality": "question_quality",
            "information_extraction_avg": "information_extraction",
            "avg_information_extraction": "information_extraction",
            "coverage_avg": "coverage",
            "avg_coverage": "coverage",
            "efficiency_avg": "efficiency",
            "avg_efficiency": "efficiency",
        }
        raw_baseline_metrics = (
            config_payload.get("baseline_metrics")
            if isinstance(config_payload.get("baseline_metrics"), dict)
            else {}
        )
        baseline_metrics: Dict[str, float] = {}
        for raw_key, raw_value in dict(raw_baseline_metrics).items():
            key = metric_aliases.get(str(raw_key).strip().lower(), str(raw_key).strip().lower())
            if key not in {"empathy", "question_quality", "information_extraction", "coverage", "efficiency"}:
                continue
            baseline_metrics[key] = _clamp(_safe_float(raw_value, 0.0))

        actor_critic_priority = 70
        for candidate in (
            config_payload.get("priority"),
            config_payload.get("actor_critic_priority"),
            (config_payload.get("actor_critic_optimizer") or {}).get("priority")
            if isinstance(config_payload.get("actor_critic_optimizer"), dict)
            else None,
        ):
            if candidate is None:
                continue
            try:
                actor_critic_priority = max(1, min(100, int(candidate)))
                break
            except Exception:
                continue

        warning_messages = [
            str((warning or {}).get("message") or "")
            for warning in (drafting_readiness.get("warnings") or [])
            if isinstance(warning, dict)
        ]
        readiness_blockers = _dedupe_text_values(
            str(item).strip()
            for item in list(drafting_readiness.get("blockers") or [])
            if str(item).strip()
        )
        unresolved_factual_gaps = self._normalize_lines(
            list(drafting_readiness.get("unresolved_factual_gaps") or [])
        )
        unresolved_legal_gaps = self._normalize_lines(
            list(drafting_readiness.get("unresolved_legal_gaps") or [])
        )
        graph_signals = (
            dict(drafting_readiness.get("graph_completeness_signals") or {})
            if isinstance(drafting_readiness.get("graph_completeness_signals"), dict)
            else {}
        )
        graph_status = str(graph_signals.get("status") or "ready").strip().lower() or "ready"
        graph_remaining_gap_count = max(
            int(graph_signals.get("remaining_gap_count", 0) or 0),
            int(graph_signals.get("current_gap_count", 0) or 0),
        )
        graph_gate_active = any(
            (
                graph_status != "ready",
                graph_remaining_gap_count > 0,
                graph_signals and not bool(graph_signals.get("knowledge_graph_available", True)),
                graph_signals and not bool(graph_signals.get("dependency_graph_available", True)),
            )
        )
        workflow_phase_plan = (
            config_payload.get("workflow_phase_plan")
            if isinstance(config_payload.get("workflow_phase_plan"), dict)
            else {}
        )
        phase_payloads = (
            workflow_phase_plan.get("phases")
            if isinstance(workflow_phase_plan.get("phases"), dict)
            else {}
        )
        document_phase = (
            phase_payloads.get("document_generation")
            if isinstance(phase_payloads.get("document_generation"), dict)
            else {}
        )
        document_signals = (
            document_phase.get("signals")
            if isinstance(document_phase.get("signals"), dict)
            else {}
        )
        document_summary = str(document_phase.get("summary") or "").strip()
        summary_candidates = [
            document_summary,
            str(config_payload.get("phase_goal") or "").strip(),
            str(config_payload.get("document_phase_goal") or "").strip(),
            *warning_messages,
        ]
        no_success_signal = any(
            "no successful sessions" in value.lower() and "drafting handoff" in value.lower()
            for value in summary_candidates
            if value
        )

        successful_session_count = max(
            0,
            _safe_int(document_signals.get("adversarial_successful_session_count"), 0),
            _safe_int(config_payload.get("successful_session_count"), 0),
            _safe_int(config_payload.get("successful_sessions"), 0),
            _safe_int((config_payload.get("adversarial_batch") or {}).get("successful_session_count"), 0)
            if isinstance(config_payload.get("adversarial_batch"), dict)
            else 0,
        )
        session_count = max(
            0,
            _safe_int(document_signals.get("adversarial_session_count"), 0),
            _safe_int(config_payload.get("session_count"), 0),
            _safe_int(config_payload.get("sessions"), 0),
            _safe_int((config_payload.get("adversarial_batch") or {}).get("session_count"), 0)
            if isinstance(config_payload.get("adversarial_batch"), dict)
            else 0,
        )
        phase_status = (
            str(document_phase.get("status") or "").strip().lower()
            or str(drafting_readiness.get("phase_status") or drafting_readiness.get("status") or "ready").strip().lower()
        )
        coverage = max(
            0.0,
            _safe_float(document_signals.get("drafting_coverage"), -1.0),
            _safe_float(config_payload.get("coverage"), -1.0),
            _safe_float(drafting_readiness.get("coverage"), -1.0),
        )
        if coverage < 0.0:
            coverage = 0.0
        session_flow_stable = bool(document_signals.get("adversarial_session_flow_stable")) if "adversarial_session_flow_stable" in document_signals else True
        has_session_flow_signal = any(
            (
                no_success_signal,
                session_count > 0,
                phase_status == "critical",
                not session_flow_stable,
                bool(document_phase),
            )
        )
        assessment_blocked = (
            successful_session_count <= 0
            and has_session_flow_signal
            and (
                no_success_signal
                or session_count > 0
                or phase_status == "critical"
                or coverage <= 0.0
                or not session_flow_stable
            )
        )
        if graph_gate_active or unresolved_factual_gaps or unresolved_legal_gaps:
            assessment_blocked = True
        gating_blockers = _dedupe_text_values(
            list(readiness_blockers)
            + (["uncovered_intake_objectives"] if unresolved_objectives else [])
            + (["graph_analysis_not_ready"] if graph_gate_active else [])
            + (
                ["document_generation_not_ready"]
                if (
                    phase_status in {"warning", "blocked", "critical"}
                    or unresolved_objectives
                    or unresolved_factual_gaps
                    or unresolved_legal_gaps
                    or assessment_blocked
                )
                else []
            )
        )
        recommended_actions = _dedupe_text_values(
            [
                *[
                    str((action or {}).get("recommended_action") or "").strip()
                    for action in list(document_phase.get("recommended_actions") or [])
                    if isinstance(action, dict)
                ],
                *[
                    str(action).strip()
                    for action in list(config_payload.get("recommended_actions") or [])
                    if str(action).strip()
                ],
                "Promote blocker-closing intake answers into factual allegations, claim support, and exhibit descriptions before formalization."
                if unresolved_objectives
                else "",
                "Close graph completeness blockers and unresolved chronology dependencies before document-generation optimization."
                if graph_gate_active
                else "",
                "Resolve unresolved factual and legal readiness gaps before formalization."
                if (unresolved_factual_gaps or unresolved_legal_gaps)
                else "",
                "Restore a stable adversarial session flow before tuning document-generation handoffs."
                if assessment_blocked
                else "",
            ]
        )
        actor_critic_metrics = {
            "empathy": _clamp(baseline_metrics.get("empathy", 0.0)),
            "question_quality": _clamp(baseline_metrics.get("question_quality", 0.0)),
            "information_extraction": _clamp(baseline_metrics.get("information_extraction", 0.0)),
            "coverage": _clamp(baseline_metrics.get("coverage", coverage)),
            "efficiency": _clamp(baseline_metrics.get("efficiency", 0.0)),
        }
        canonical_facts = [
            dict(item)
            for item in list(intake_case_file.get("canonical_facts") or [])
            if isinstance(item, dict)
        ]
        timeline_fact_lines: List[str] = []
        claim_support_lines_by_type: Dict[str, List[str]] = {}
        claim_support_shared: List[str] = []
        blocker_closing_answers: List[str] = []
        for fact in canonical_facts:
            fact_text = str(fact.get("text") or "").strip()
            if not fact_text:
                continue
            timeline_fact_lines.append(fact_text)
            lower_text = fact_text.lower()
            if any(token in lower_text for token in ("because", "after", "as a result", "retaliat", "responded", "hearing", "review")):
                claim_support_shared.append(fact_text)
            claim_types_for_fact = _dedupe_text_values(
                list(fact.get("claim_types") or [])
                + [fact.get("claim_type")]
                + [fact.get("supports_claim_type")]
            )
            for claim_type in claim_types_for_fact:
                key = str(claim_type).strip().lower()
                if not key:
                    continue
                claim_support_lines_by_type.setdefault(key, [])
                claim_support_lines_by_type[key].append(fact_text)
        blocker_closing_answers.extend(blocker_follow_up_prompts)
        blocker_closing_answers.extend(
            str(item.get("reason") or "").strip()
            for item in blocker_items
            if str(item.get("reason") or "").strip()
        )
        blocker_closing_answers.extend(anchored_chronology_summary)
        evidence_reference_lines = self._normalize_lines(
            [
                (
                    f"Exhibit evidence ({row.get('type') or 'evidence'}; cid {row.get('cid')}) supports the chronology and actor sequence: {row.get('text')}."
                    if row.get("cid")
                    else f"Exhibit evidence ({row.get('type') or 'evidence'}) supports the chronology and actor sequence: {row.get('text')}."
                )
                for row in evidence_summaries[:8]
                if isinstance(row, dict) and str(row.get("text") or "").strip()
            ]
        )
        structured_handoff = {
            "factual_allegation_lines": self._normalize_lines(
                timeline_fact_lines + anchored_chronology_summary + blocker_closing_answers + evidence_reference_lines
            )[:14],
            "summary_of_facts_lines": self._normalize_lines(
                anchored_chronology_summary + timeline_fact_lines + evidence_reference_lines
            )[:12],
            "claim_support_lines_by_type": {
                key: self._normalize_lines(values)[:8]
                for key, values in claim_support_lines_by_type.items()
                if key
            },
            "claim_support_lines_shared": self._normalize_lines(
                claim_support_shared + anchored_chronology_summary + evidence_reference_lines
            )[:10],
            "blocker_closing_answers": self._normalize_lines(blocker_closing_answers)[:10],
            "exhibit_description_lines": evidence_reference_lines[:8],
            "unresolved_objectives": unresolved_objectives[:8],
            "unresolved_factual_gaps": unresolved_factual_gaps[:6],
            "unresolved_legal_gaps": unresolved_legal_gaps[:6],
        }

        return {
            "claims": claim_contexts,
            "evidence": evidence_summaries[:10],
            "sections": dict(drafting_readiness.get("sections") or {}) if isinstance(drafting_readiness, dict) else {},
            "packet_projection": self._build_packet_projection(draft),
            "structured_handoff": structured_handoff,
            "actor_critic": {
                "priority": actor_critic_priority,
                "baseline_metrics": baseline_metrics,
                "metrics": actor_critic_metrics,
            },
            "document_generation_guardrail": {
                "phase_status": phase_status or "ready",
                "coverage": _clamp(coverage),
                "successful_session_count": successful_session_count,
                "session_count": session_count,
                "assessment_blocked": assessment_blocked,
                "gate_on_graph_completeness": bool(graph_gate_active),
                "graph_phase_status": graph_status,
                "graph_remaining_gap_count": int(graph_remaining_gap_count),
                "blockers": gating_blockers,
                "unresolved_factual_gaps": unresolved_factual_gaps[:6],
                "unresolved_legal_gaps": unresolved_legal_gaps[:6],
                "summary": (
                    "Formalization gate is active: unresolved graph/document blockers must be closed before complaint generation."
                    if assessment_blocked
                    else ""
                ),
                "recommended_actions": recommended_actions,
                "priority": actor_critic_priority,
            },
            "workflow_targeting_summary": dict(
                (workflow_guidance.get("workflow_targeting_summary") or {})
                if isinstance(workflow_guidance, dict)
                else {}
            ),
            "evidence_workflow_action_queue": list(
                (workflow_guidance.get("evidence_workflow_action_queue") or [])
                if isinstance(workflow_guidance, dict)
                else []
            ),
            "evidence_workflow_action_summary": dict(
                (workflow_guidance.get("evidence_workflow_action_summary") or {})
                if isinstance(workflow_guidance, dict)
                else {}
            ),
            "workflow_action_queue": list(
                (workflow_guidance.get("workflow_action_queue") or [])
                if isinstance(workflow_guidance, dict)
                else []
            ),
            "document_drafting_next_action": document_drafting_next_action,
            "document_grounding_improvement_next_action": document_grounding_improvement_next_action,
            "intake_priorities": {
                "covered_objectives": covered_objectives,
                "uncovered_objectives": uncovered_objectives,
                "objective_question_counts": objective_question_counts,
                "unresolved_objectives": unresolved_objectives,
                "critical_unresolved_objectives": critical_unresolved,
                "blocker_count": int(blocker_follow_up_summary.get("blocking_item_count") or len(blocker_items) or 0),
                "blocker_items": blocker_items,
                "blocker_open_items": blocker_open_items,
                "blocking_objectives": blocker_objectives,
                "blocker_extraction_targets": blocker_extraction_targets,
                "blocker_workflow_phases": blocker_workflow_phases,
                "blocker_issue_families": blocker_issue_families,
                "anchored_chronology_summary": anchored_chronology_summary,
                "temporal_issue_count": temporal_issue_count,
                "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
                "resolved_temporal_issue_count": resolved_temporal_issue_count,
                "temporal_issue_status_counts": temporal_issue_status_counts,
                "claim_temporal_gap_count": max(
                    sum(
                    int(item.get("gap_count") or 0)
                    for item in claim_temporal_gap_summary
                    if isinstance(item, dict)
                    ),
                    int(fallback_alignment_task_summary.get("temporal_gap_task_count") or 0),
                ),
                "claim_temporal_gap_summary": claim_temporal_gap_summary,
                "recommended_follow_up_prompts": [
                    _OBJECTIVE_PROMPTS[objective]
                    for objective in critical_unresolved
                    if objective in _OBJECTIVE_PROMPTS
                ] + blocker_follow_up_prompts,
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
            claim_review = summarize_claim_reasoning_review(validation_claim)
            flagged_elements = claim_review.get("flagged_elements")
            if isinstance(flagged_elements, list):
                for flagged_element in flagged_elements:
                    if not isinstance(flagged_element, dict):
                        continue
                    theorem_export_metadata = flagged_element.get("proof_artifact_theorem_export_metadata")
                    if isinstance(theorem_export_metadata, dict) and theorem_export_metadata:
                        continue
                    fallback_metadata = _build_claim_reasoning_theorem_export_metadata(
                        intake_case_summary,
                        claim_type=claim_type,
                        claim_element_id=str(flagged_element.get("element_id") or ""),
                    )
                    if fallback_metadata:
                        flagged_element["proof_artifact_theorem_export_metadata"] = fallback_metadata
            review_by_claim[claim_type] = claim_review
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
        guardrail = (
            support_context.get("document_generation_guardrail")
            if isinstance(support_context.get("document_generation_guardrail"), dict)
            else {}
        )
        assessment_blocked = bool(guardrail.get("assessment_blocked"))
        guardrail_phase_status = str(guardrail.get("phase_status") or "").strip().lower()
        guardrail_coverage = _safe_float(guardrail.get("coverage"), 0.0)
        graph_gate_active = bool(guardrail.get("gate_on_graph_completeness"))
        guardrail_blockers = _dedupe_text_values(guardrail.get("blockers") or [])
        unresolved_factual_gaps = self._normalize_lines(guardrail.get("unresolved_factual_gaps") or [])
        unresolved_legal_gaps = self._normalize_lines(guardrail.get("unresolved_legal_gaps") or [])
        structured_handoff = (
            support_context.get("structured_handoff")
            if isinstance(support_context.get("structured_handoff"), dict)
            else {}
        )
        promoted_factual_lines = self._normalize_lines(
            list(structured_handoff.get("factual_allegation_lines") or [])
        )
        promoted_claim_support_map = (
            structured_handoff.get("claim_support_lines_by_type")
            if isinstance(structured_handoff.get("claim_support_lines_by_type"), dict)
            else {}
        )
        promoted_exhibit_lines = self._normalize_lines(
            list(structured_handoff.get("exhibit_description_lines") or [])
        )
        if promoted_factual_lines:
            section_scores["factual_allegations"] = _clamp(float(section_scores.get("factual_allegations") or 0.0) + 0.08)
        if promoted_claim_support_map:
            section_scores["claims_for_relief"] = _clamp(float(section_scores.get("claims_for_relief") or 0.0) + 0.07)
        if promoted_exhibit_lines:
            section_scores["affidavit"] = _clamp(float(section_scores.get("affidavit") or 0.0) + 0.04)
            section_scores["packet_projection"] = _clamp(float(section_scores.get("packet_projection") or 0.0) + 0.03)
        if assessment_blocked:
            document_cap = 0.4 if guardrail_phase_status == "critical" or guardrail_coverage <= 0.0 else 0.55
            for section_name in (
                "claims_for_relief",
                "requested_relief",
                "affidavit",
                "certificate_of_service",
                "packet_projection",
            ):
                section_scores[section_name] = min(float(section_scores.get(section_name) or 0.0), document_cap)
        if graph_gate_active:
            section_scores["factual_allegations"] = min(float(section_scores.get("factual_allegations") or 0.0), 0.62)
            section_scores["claims_for_relief"] = min(float(section_scores.get("claims_for_relief") or 0.0), 0.58)
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
        if assessment_blocked:
            forced_phase_order = ["graph_analysis", "intake_questioning", "document_generation"]
            phase_focus_order = forced_phase_order
            prioritized_phase = forced_phase_order[0]
            recommended_focus = str(
                phase_target_sections.get(prioritized_phase)
                or "factual_allegations"
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
        if guardrail_blockers:
            weaknesses.append(
                "Drafting readiness still has active blockers that must be reflected in formalization gating."
            )
            suggestions.append(
                "Carry unresolved blockers into drafting readiness and pause final formalization until blockers are closed."
            )
        if unresolved_factual_gaps:
            weaknesses.append("Unresolved factual gaps remain in the drafting handoff and weaken complaint specificity.")
            suggestions.append(
                "Promote structured intake facts and blocker-closing answers directly into factual allegations and claim support."
            )
        if unresolved_legal_gaps:
            weaknesses.append("Unresolved legal gaps remain in the drafting handoff and weaken claim formalization readiness.")
            suggestions.append("Address unresolved legal gaps before final complaint export.")
        if graph_gate_active:
            weaknesses.append("Graph completeness signals indicate unresolved dependencies that should block formalization.")
            suggestions.append("Close graph-analysis dependencies before running final document generation.")
        if assessment_blocked:
            weaknesses.append(
                str(guardrail.get("summary") or "No successful sessions were available to assess drafting handoff quality.")
            )
            for action in list(guardrail.get("recommended_actions") or []):
                action_text = str(action).strip()
                if not action_text:
                    continue
                suggestions.append(action_text)

        readiness_status = str(drafting_readiness.get("status") or "ready").strip().lower()
        procedural_score = 0.95 if readiness_status == "ready" else 0.75 if readiness_status == "warning" else 0.45
        if assessment_blocked:
            procedural_score = min(
                procedural_score,
                0.35 if guardrail_phase_status == "critical" or guardrail_coverage <= 0.0 else 0.6,
            )
        if graph_gate_active:
            procedural_score = min(procedural_score, 0.45)
        if unresolved_factual_gaps:
            procedural_score = max(0.0, procedural_score - min(0.18, 0.04 * len(unresolved_factual_gaps)))
        if unresolved_legal_gaps:
            procedural_score = max(0.0, procedural_score - min(0.12, 0.04 * len(unresolved_legal_gaps)))
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
        if assessment_blocked:
            overall_score = min(
                overall_score,
                0.55 if guardrail_phase_status == "critical" or guardrail_coverage <= 0.0 else 0.7,
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
            "document_generation_guardrail": dict(guardrail),
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
        unresolved_temporal_issue_count = int(
            priorities.get("unresolved_temporal_issue_count", priorities.get("temporal_issue_count", 0)) or 0
        )
        resolved_temporal_issue_count = int(priorities.get("resolved_temporal_issue_count") or 0)
        if priorities.get("anchored_chronology_summary"):
            score += 0.08
            if unresolved_temporal_issue_count <= 0:
                score += 0.03
                if resolved_temporal_issue_count > 0:
                    score += 0.02
        elif unresolved_temporal_issue_count > 0:
            score -= 0.05
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
        blocker_extraction_targets = {
            str(item).strip().lower()
            for item in list(priorities.get("blocker_extraction_targets") or [])
            if str(item).strip()
        }
        blocker_workflow_phases = {
            str(item).strip().lower()
            for item in list(priorities.get("blocker_workflow_phases") or [])
            if str(item).strip()
        }
        blocker_issue_families = {
            str(item).strip().lower()
            for item in list(priorities.get("blocker_issue_families") or [])
            if str(item).strip()
        }
        blocker_count = int(priorities.get("blocker_count") or 0)
        chronology_context_active = any(
            (
                bool(priorities.get("anchored_chronology_summary")),
                int(priorities.get("claim_temporal_gap_count") or 0) > 0,
                int(priorities.get("unresolved_temporal_issue_count", priorities.get("temporal_issue_count", 0)) or 0) > 0,
                int(priorities.get("resolved_temporal_issue_count") or 0) > 0,
            )
        )
        graph_blockers = unresolved_objectives.intersection(
            {
                "exact_dates",
                "timeline",
                "actors",
                "staff_names_titles",
                "causation_link",
                "causation_sequence",
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
                "exact_dates",
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
                + (0.08 if blocker_workflow_phases.intersection({"graph_analysis"}) else 0.0)
                + min(len(blocker_extraction_targets.intersection({"timeline_anchors", "actor_role_mapping", "retaliation_sequence", "hearing_process", "response_timeline"})) * 0.03, 0.15)
            ),
            "document_generation": _clamp(
                claims_pressure * 0.2
                + requested_relief_pressure * 0.2
                + affidavit_pressure * 0.2
                + certificate_pressure * 0.15
                + packet_pressure * 0.15
                + min(len(document_blockers) * 0.06, 0.18)
                + (0.05 if blocker_workflow_phases.intersection({"document_generation"}) else 0.0)
            ),
            "intake_questioning": _clamp(
                (intake_pressure * 0.55)
                + min(len(unresolved_objectives) * 0.05, 0.2)
                + min(len(critical_unresolved) * 0.04, 0.12)
                + min(blocker_count * 0.03, 0.12)
                + (0.04 if blocker_workflow_phases.intersection({"intake_questioning"}) else 0.0)
            ),
        }
        if blocker_issue_families.intersection({"notice_chain", "response_timeline", "hearing_process"}):
            phase_scores["document_generation"] = _clamp(float(phase_scores.get("document_generation") or 0.0) + 0.04)
        if graph_blockers and factual_pressure >= 0.35:
            phase_scores["graph_analysis"] = _clamp(
                max(
                    float(phase_scores.get("graph_analysis") or 0.0),
                    float(phase_scores.get("intake_questioning") or 0.0) + 0.05,
                )
            )

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
                chronology_context_active=chronology_context_active,
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
        chronology_context_active: bool = False,
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
        if phase_name == "graph_analysis" and chronology_context_active:
            return "factual_allegations"
        if phase_name == "intake_questioning" and unresolved_objectives:
            return "factual_allegations"
        if phase_name == "intake_questioning" and chronology_context_active:
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
        document_drafting_next_action = (
            support_context.get("document_drafting_next_action")
            if isinstance(support_context.get("document_drafting_next_action"), dict)
            else {}
        )
        document_grounding_improvement_next_action = (
            support_context.get("document_grounding_improvement_next_action")
            if isinstance(support_context.get("document_grounding_improvement_next_action"), dict)
            else {}
        )
        grounding_focus_section = str(document_grounding_improvement_next_action.get("focus_section") or "").strip()
        if (
            str(document_grounding_improvement_next_action.get("action") or "").strip().lower() == "refine_document_grounding_strategy"
            and grounding_focus_section in self.VALID_FOCUS_SECTIONS
        ):
            return grounding_focus_section
        drafting_focus_section = str(document_drafting_next_action.get("focus_section") or "").strip()
        if (
            str(document_drafting_next_action.get("action") or "").strip().lower() == "realign_document_drafting"
            and drafting_focus_section in self.VALID_FOCUS_SECTIONS
        ):
            return drafting_focus_section
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
        workflow_targeting_summary = (
            support_context.get("workflow_targeting_summary")
            if isinstance(support_context.get("workflow_targeting_summary"), dict)
            else {}
        )
        targeting_section = self._choose_focus_section_from_workflow_targeting(workflow_targeting_summary)
        if targeting_section in self.VALID_FOCUS_SECTIONS:
            return targeting_section
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
        for blocker in intake_priorities.get("blocker_items") or []:
            if not isinstance(blocker, dict):
                continue
            blocker_reason = str(blocker.get("reason") or "").strip()
            if blocker_reason:
                candidate_rows.append(
                    {
                        "claim_type": "intake_blocker",
                        "text": blocker_reason,
                        "kind": "blocker_reason",
                    }
                )
        evidence_workflow_action_queue = (
            support_context.get("evidence_workflow_action_queue")
            if isinstance(support_context.get("evidence_workflow_action_queue"), list)
            else []
        )
        for action_entry in evidence_workflow_action_queue:
            if not isinstance(action_entry, dict):
                continue
            action_text = str(action_entry.get("action") or "").strip()
            if not action_text:
                continue
            claim_element_label = str(
                action_entry.get("claim_element_label")
                or action_entry.get("claim_element_id")
                or ""
            ).strip()
            preferred_support_kind = str(action_entry.get("preferred_support_kind") or "").strip()
            evidence_focus = " ".join(
                part for part in [
                    action_text,
                    claim_element_label,
                    preferred_support_kind,
                ]
                if part
            ).strip()
            candidate_rows.append(
                {
                    "claim_type": str(action_entry.get("claim_type") or action_entry.get("phase_name") or "graph_analysis").strip(),
                    "text": evidence_focus or action_text,
                    "kind": "evidence_workflow_action",
                    "status": str(action_entry.get("status") or "").strip(),
                    "claim_element_id": str(action_entry.get("claim_element_id") or "").strip(),
                    "preferred_support_kind": preferred_support_kind,
                }
            )
        workflow_action_queue = support_context.get("workflow_action_queue") if isinstance(support_context.get("workflow_action_queue"), list) else []
        for action_entry in workflow_action_queue:
            if not isinstance(action_entry, dict):
                continue
            action_text = str(action_entry.get("action") or "").strip()
            if not action_text:
                continue
            candidate_rows.append(
                {
                    "claim_type": str(action_entry.get("phase_name") or "workflow").strip(),
                    "text": action_text,
                    "kind": "workflow_action",
                    "status": str(action_entry.get("status") or "").strip(),
                }
            )
        document_drafting_next_action = (
            support_context.get("document_drafting_next_action")
            if isinstance(support_context.get("document_drafting_next_action"), dict)
            else {}
        )
        if str(document_drafting_next_action.get("action") or "").strip().lower() == "realign_document_drafting":
            target_claim_element = str(document_drafting_next_action.get("claim_element_id") or "").strip()
            executed_claim_element = str(document_drafting_next_action.get("executed_claim_element_id") or "").strip()
            preferred_support_kind = str(document_drafting_next_action.get("preferred_support_kind") or "").strip()
            focus_section_hint = str(document_drafting_next_action.get("focus_section") or "").strip()
            candidate_rows.append(
                {
                    "claim_type": "document_generation",
                    "text": (
                        f"Realign drafting toward {target_claim_element.replace('_', ' ')}"
                        + (
                            f" instead of {executed_claim_element.replace('_', ' ')}."
                            if executed_claim_element
                            else "."
                        )
                    ),
                    "kind": "document_drafting_next_action",
                    "claim_element_id": target_claim_element,
                    "executed_claim_element_id": executed_claim_element,
                    "preferred_support_kind": preferred_support_kind,
                    "focus_section": focus_section_hint,
                }
            )
        document_grounding_improvement_next_action = (
            support_context.get("document_grounding_improvement_next_action")
            if isinstance(support_context.get("document_grounding_improvement_next_action"), dict)
            else {}
        )
        if str(document_grounding_improvement_next_action.get("action") or "").strip().lower() == "refine_document_grounding_strategy":
            target_claim_element = str(document_grounding_improvement_next_action.get("claim_element_id") or "").strip()
            current_support_kind = str(document_grounding_improvement_next_action.get("preferred_support_kind") or "").strip()
            suggested_support_kind = str(document_grounding_improvement_next_action.get("suggested_support_kind") or "").strip()
            candidate_rows.append(
                {
                    "claim_type": "document_generation",
                    "text": (
                        f"Refine grounding for {target_claim_element.replace('_', ' ')}"
                        + (
                            f" by trying {suggested_support_kind.replace('_', ' ')} instead of {current_support_kind.replace('_', ' ')}."
                            if target_claim_element and suggested_support_kind and current_support_kind
                            else "."
                        )
                    ),
                    "kind": "document_grounding_improvement_next_action",
                    "claim_element_id": target_claim_element,
                    "preferred_support_kind": suggested_support_kind or current_support_kind,
                    "focus_section": str(document_grounding_improvement_next_action.get("focus_section") or "").strip(),
                }
            )
        workflow_targeting_summary = (
            support_context.get("workflow_targeting_summary")
            if isinstance(support_context.get("workflow_targeting_summary"), dict)
            else {}
        )
        for claim_element_id, count in _sorted_count_items(
            workflow_targeting_summary.get("shared_claim_element_counts") or {}
        )[:4]:
            candidate_rows.append(
                {
                    "claim_type": "workflow_targeting",
                    "text": f"Strengthen complaint support for {claim_element_id.replace('_', ' ')}.",
                    "kind": "workflow_targeting_claim_element",
                    "claim_element_id": claim_element_id,
                    "target_count": count,
                }
            )
        for focus_area, count in _sorted_count_items(
            workflow_targeting_summary.get("shared_focus_area_counts") or {}
        )[:4]:
            candidate_rows.append(
                {
                    "claim_type": "workflow_targeting",
                    "text": f"Strengthen drafting around {focus_area.replace('_', ' ')}.",
                    "kind": "workflow_targeting_focus_area",
                    "target_focus_area": focus_area,
                    "target_count": count,
                }
            )

        ranked_rows = self._rank_candidates(query=query, candidates=candidate_rows)
        return {
            "focus_section": focus_section,
            "query": query,
            "top_support": ranked_rows[:6],
        }

    def _choose_focus_section_from_workflow_targeting(self, workflow_targeting_summary: Dict[str, Any]) -> str:
        summary = workflow_targeting_summary if isinstance(workflow_targeting_summary, dict) else {}
        prioritized_phases = [
            str(value)
            for value in list(summary.get("prioritized_phases") or [])
            if str(value)
        ]
        phase_summaries = summary.get("phase_summaries") if isinstance(summary.get("phase_summaries"), dict) else {}
        document_summary = (
            phase_summaries.get("document_generation")
            if isinstance(phase_summaries.get("document_generation"), dict)
            else {}
        )
        for section_name, _count in _sorted_count_items(document_summary.get("focus_section_counts") or {}):
            if section_name in self.VALID_FOCUS_SECTIONS:
                return section_name
        highest_phase = str(prioritized_phases[0] if prioritized_phases else "").strip()
        shared_focus_areas = dict(summary.get("shared_focus_area_counts") or {})
        shared_claim_elements = dict(summary.get("shared_claim_element_counts") or {})
        if highest_phase == "document_generation":
            return "claims_for_relief"
        if highest_phase == "graph_analysis" and shared_claim_elements:
            return "claims_for_relief"
        if highest_phase == "intake_questioning" and shared_focus_areas:
            return "factual_allegations"
        return ""

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

    def _build_upstream_optimizer_metadata(self, *, phase_focus_order: Optional[List[str]] = None) -> Dict[str, Any]:
        metadata = {
            "available": bool(UPSTREAM_AGENTIC_AVAILABLE),
            "selected_provider": "",
            "selected_method": "",
            "phase_focus_order": list(phase_focus_order or self.WORKFLOW_PHASE_FOCUS_ORDER),
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
