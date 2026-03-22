from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:
    print("Info: claim support review pydantic is unavailable; using fallback BaseModel.")

    class _FieldSpec:
        def __init__(self, default: Any = None, default_factory: Any = None):
            self.default = default
            self.default_factory = default_factory


    def Field(default: Any = None, default_factory: Any = None, **_: Any) -> Any:
        return _FieldSpec(default=default, default_factory=default_factory)


    class BaseModel:
        def __init__(self, **kwargs: Any) -> None:
            annotations = getattr(self.__class__, "__annotations__", {})
            for name in annotations:
                if name in kwargs:
                    value = kwargs[name]
                else:
                    class_value = getattr(self.__class__, name, None)
                    if isinstance(class_value, _FieldSpec):
                        if class_value.default_factory is not None:
                            value = class_value.default_factory()
                        else:
                            value = class_value.default
                    else:
                        value = class_value
                setattr(self, name, value)

        def dict(self) -> Dict[str, Any]:
            return {
                name: getattr(self, name)
                for name in getattr(self.__class__, "__annotations__", {})
            }

from complaint_phases.denoiser import ComplaintDenoiser
from complaint_phases.phase_manager import ComplaintPhase
from intake_status import (
    build_intake_case_review_summary,
    build_intake_status_summary,
    summarize_intake_contradictions,
    summarize_temporal_issue_registry,
)
from workflow_phase_guidance import (
    build_graph_analysis_phase_guidance,
    build_review_document_generation_phase_guidance,
    build_workflow_phase_plan,
    humanize_workflow_priority_label,
    resolve_prioritized_workflow_phase,
)


DEFAULT_REQUIRED_SUPPORT_KINDS = ["evidence", "authority"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_document_focus_preview(draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    preview_rows: List[Dict[str, Any]] = []

    def _append_rows(section: str, entries: Any) -> None:
        for entry in list(entries or []):
            if not isinstance(entry, dict):
                continue
            focus = entry.get("document_focus")
            if not isinstance(focus, dict) or not focus:
                continue
            preview_rows.append(
                {
                    "section": section,
                    "text": str(entry.get("text") or "").strip(),
                    "focus_source": str(focus.get("focus_source") or "").strip(),
                    "action": str(focus.get("action") or "").strip(),
                    "target_claim_element_id": str(focus.get("target_claim_element_id") or "").strip(),
                    "original_claim_element_id": str(focus.get("original_claim_element_id") or "").strip(),
                    "preferred_support_kind": str(focus.get("preferred_support_kind") or "").strip(),
                    "priority_rank": int(entry.get("document_focus_priority_rank") or 0),
                }
            )

    _append_rows("summary_of_facts", draft.get("summary_of_fact_entries"))
    _append_rows("factual_allegations", draft.get("factual_allegation_paragraphs"))
    claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        _append_rows(
            f"claims_for_relief:{str(claim.get('claim_type') or '').strip() or 'claim'}",
            claim.get("supporting_fact_provenance"),
        )

    preview_rows.sort(
        key=lambda row: (
            int(row.get("priority_rank") or 0) or 9999,
            str(row.get("section") or ""),
            str(row.get("text") or ""),
        )
    )
    return preview_rows[:8]


def _get_formalization_document_focus_preview(mediator: Any) -> List[Dict[str, Any]]:
    phase_manager = getattr(mediator, "phase_manager", None)
    get_phase_data = getattr(phase_manager, "get_phase_data", None)
    if not callable(get_phase_data):
        return []
    formal_complaint = get_phase_data(ComplaintPhase.FORMALIZATION, "formal_complaint")
    if not isinstance(formal_complaint, dict):
        return []
    return _build_document_focus_preview(formal_complaint)


def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _classify_adaptive_retry_recency(timestamp: Any) -> Dict[str, Any]:
    parsed = _parse_iso_timestamp(timestamp)
    if not parsed:
        return {
            "recency_bucket": "unknown",
            "is_stale": False,
        }

    age_seconds = max(0.0, (_utcnow() - parsed).total_seconds())
    if age_seconds <= 6 * 3600:
        bucket = "fresh"
    elif age_seconds <= 48 * 3600:
        bucket = "recent"
    else:
        bucket = "stale"
    return {
        "recency_bucket": bucket,
        "is_stale": bucket == "stale",
    }


class ClaimSupportReviewRequest(BaseModel):
    user_id: Optional[str] = None
    claim_type: Optional[str] = None
    required_support_kinds: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )
    follow_up_cooldown_seconds: int = 3600
    include_support_summary: bool = True
    include_overview: bool = True
    include_follow_up_plan: bool = True
    execute_follow_up: bool = False
    follow_up_support_kind: Optional[str] = None
    follow_up_max_tasks_per_claim: int = 3


class ClaimSupportFollowUpExecuteRequest(BaseModel):
    user_id: Optional[str] = None
    claim_type: Optional[str] = None
    required_support_kinds: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )
    follow_up_cooldown_seconds: int = 3600
    follow_up_support_kind: Optional[str] = None
    follow_up_max_tasks_per_claim: int = 3
    follow_up_force: bool = False
    include_post_execution_review: bool = True
    include_support_summary: bool = True
    include_overview: bool = True
    include_follow_up_plan: bool = True


class ClaimSupportManualReviewResolveRequest(BaseModel):
    user_id: Optional[str] = None
    claim_type: Optional[str] = None
    claim_element_id: Optional[str] = None
    claim_element: Optional[str] = None
    resolution_status: str = "resolved"
    resolution_notes: Optional[str] = None
    related_execution_id: Optional[int] = None
    resolution_metadata: Dict[str, Any] = Field(default_factory=dict)
    required_support_kinds: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )
    include_post_resolution_review: bool = True
    include_support_summary: bool = True
    include_overview: bool = True
    include_follow_up_plan: bool = True


class ClaimSupportTestimonySaveRequest(BaseModel):
    user_id: Optional[str] = None
    claim_type: Optional[str] = None
    claim_element_id: Optional[str] = None
    claim_element: Optional[str] = None
    raw_narrative: Optional[str] = None
    event_date: Optional[str] = None
    actor: Optional[str] = None
    act: Optional[str] = None
    target: Optional[str] = None
    harm: Optional[str] = None
    firsthand_status: str = "unknown"
    source_confidence: Optional[float] = None
    testimony_metadata: Dict[str, Any] = Field(default_factory=dict)
    required_support_kinds: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )
    include_post_save_review: bool = True
    include_support_summary: bool = True
    include_overview: bool = True
    include_follow_up_plan: bool = True


class ClaimSupportDocumentSaveRequest(BaseModel):
    user_id: Optional[str] = None
    claim_type: Optional[str] = None
    claim_element_id: Optional[str] = None
    claim_element: Optional[str] = None
    document_text: Optional[str] = None
    document_label: Optional[str] = None
    source_url: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    evidence_type: str = "document"
    document_metadata: Dict[str, Any] = Field(default_factory=dict)
    required_support_kinds: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )
    include_post_save_review: bool = True
    include_support_summary: bool = True
    include_overview: bool = True
    include_follow_up_plan: bool = True


class ClaimSupportIntakeSummaryConfirmRequest(BaseModel):
    user_id: Optional[str] = None
    claim_type: Optional[str] = None
    confirmation_note: Optional[str] = None
    confirmation_source: str = "complainant"
    required_support_kinds: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )
    include_post_confirmation_review: bool = True
    include_support_summary: bool = True
    include_overview: bool = True
    include_follow_up_plan: bool = True


def _resolve_user_id(mediator: Any, user_id: Optional[str]) -> str:
    if user_id:
        return user_id
    state = getattr(mediator, "state", None)
    return (
        getattr(state, "username", None)
        or getattr(state, "hashed_username", None)
        or "anonymous"
    )


def _build_confirmed_intake_summary_handoff_metadata(mediator: Any) -> Dict[str, Any]:
    get_status = getattr(mediator, "get_three_phase_status", None)
    if not callable(get_status):
        return {}

    raw_status = get_status()
    if not isinstance(raw_status, dict):
        return {}

    confirmation = raw_status.get("complainant_summary_confirmation")
    if not isinstance(confirmation, dict) or not bool(confirmation.get("confirmed", False)):
        return {}

    confirmed_summary_snapshot = confirmation.get("confirmed_summary_snapshot")
    if not isinstance(confirmed_summary_snapshot, dict) or not confirmed_summary_snapshot:
        return {}

    readiness = raw_status.get("intake_readiness") if isinstance(raw_status.get("intake_readiness"), dict) else {}
    return {
        "intake_summary_handoff": {
            "current_phase": str(raw_status.get("current_phase") or ""),
            "ready_to_advance": bool(readiness.get("ready_to_advance", False)),
            "complainant_summary_confirmation": dict(confirmation),
        }
    }


def _normalize_handoff_identity(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _dedupe_handoff_ids(values: Any) -> List[str]:
    normalized_values: List[str] = []
    for value in values if isinstance(values, list) else []:
        normalized = str(value or "").strip()
        if normalized and normalized not in normalized_values:
            normalized_values.append(normalized)
    return normalized_values


def _build_claim_support_temporal_handoff_metadata(
    mediator: Any,
    *,
    claim_type: Optional[str] = None,
    claim_element_id: Optional[str] = None,
) -> Dict[str, Any]:
    get_status = getattr(mediator, "get_three_phase_status", None)
    if not callable(get_status):
        return {}

    raw_status = get_status()
    if not isinstance(raw_status, dict):
        return {}

    claim_support_packet_summary = raw_status.get("claim_support_packet_summary")
    claim_support_packet_summary = (
        claim_support_packet_summary
        if isinstance(claim_support_packet_summary, dict)
        else {}
    )
    temporal_issue_registry_summary = summarize_temporal_issue_registry(
        raw_status.get("temporal_issue_registry_summary")
    )
    alignment_evidence_tasks = raw_status.get("alignment_evidence_tasks")
    alignment_evidence_tasks = (
        alignment_evidence_tasks
        if isinstance(alignment_evidence_tasks, list)
        else []
    )

    normalized_claim_type = _normalize_handoff_identity(claim_type)
    normalized_claim_element_id = _normalize_handoff_identity(claim_element_id)
    matching_tasks = [
        task for task in alignment_evidence_tasks
        if isinstance(task, dict)
        and (
            not normalized_claim_type
            or _normalize_handoff_identity(task.get("claim_type")) == normalized_claim_type
        )
        and (
            not normalized_claim_element_id
            or _normalize_handoff_identity(task.get("claim_element_id")) == normalized_claim_element_id
        )
    ]

    unresolved_temporal_issue_count = max(
        int(claim_support_packet_summary.get("claim_support_unresolved_temporal_issue_count", 0) or 0),
        int(temporal_issue_registry_summary.get("unresolved_count") or 0),
    )
    chronology_task_count = int(claim_support_packet_summary.get("temporal_gap_task_count", 0) or 0)

    temporal_handoff: Dict[str, Any] = {
        "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
        "unresolved_temporal_issue_ids": _dedupe_handoff_ids(
            claim_support_packet_summary.get("claim_support_unresolved_temporal_issue_ids")
        ),
    }
    if chronology_task_count > 0:
        temporal_handoff["chronology_task_count"] = chronology_task_count
    resolved_temporal_issue_count = int(temporal_issue_registry_summary.get("resolved_count") or 0)
    if resolved_temporal_issue_count > 0:
        temporal_handoff["resolved_temporal_issue_count"] = resolved_temporal_issue_count

    status_counts = dict(temporal_issue_registry_summary.get("status_counts") or {})
    if status_counts:
        temporal_handoff["temporal_issue_status_counts"] = status_counts

    total_temporal_issue_count = int(temporal_issue_registry_summary.get("count") or 0)
    if total_temporal_issue_count > 0:
        temporal_handoff["temporal_issue_count"] = total_temporal_issue_count

    if claim_type:
        temporal_handoff["claim_type"] = claim_type
    if claim_element_id:
        temporal_handoff["claim_element_id"] = claim_element_id

    for field_name in (
        "event_ids",
        "temporal_fact_ids",
        "temporal_relation_ids",
        "timeline_issue_ids",
        "temporal_issue_ids",
        "missing_temporal_predicates",
        "required_provenance_kinds",
    ):
        values: List[str] = []
        for task in matching_tasks:
            values.extend(_dedupe_handoff_ids(task.get(field_name)))
        if values:
            temporal_handoff[field_name] = _dedupe_handoff_ids(values)

    timeline_anchor_values: List[str] = []
    for task in matching_tasks:
        timeline_anchor_values.extend(
            _dedupe_handoff_ids(task.get("anchor_ids") or task.get("timeline_anchor_ids"))
        )
    if timeline_anchor_values:
        temporal_handoff["timeline_anchor_ids"] = _dedupe_handoff_ids(timeline_anchor_values)

    temporal_proof_bundle_ids: List[str] = []
    temporal_proof_objectives: List[str] = []
    for task in matching_tasks:
        proof_bundle_id = str(task.get("temporal_proof_bundle_id") or "").strip()
        if proof_bundle_id:
            temporal_proof_bundle_ids.append(proof_bundle_id)
        proof_objective = str(task.get("temporal_proof_objective") or "").strip()
        if proof_objective:
            temporal_proof_objectives.append(proof_objective)
    if temporal_proof_bundle_ids:
        temporal_handoff["temporal_proof_bundle_ids"] = _dedupe_handoff_ids(temporal_proof_bundle_ids)
    if temporal_proof_objectives:
        temporal_handoff["temporal_proof_objectives"] = _dedupe_handoff_ids(temporal_proof_objectives)

    for field_name in ("temporal_proof_bundle_id", "temporal_proof_objective"):
        for task in matching_tasks:
            value = str(task.get(field_name) or "").strip()
            if value:
                temporal_handoff[field_name] = value
                break

    if len(temporal_handoff) <= (2 + int(bool(claim_type)) + int(bool(claim_element_id))) and not temporal_handoff.get("unresolved_temporal_issue_count"):
        return {}

    return {"claim_support_temporal_handoff": temporal_handoff}


def _build_claim_temporal_registry_summary(
    intake_case_summary: Dict[str, Any],
    *,
    claim_type: Optional[str],
) -> Dict[str, Any]:
    normalized_claim_type = _normalize_handoff_identity(claim_type)
    if not normalized_claim_type:
        return {}

    temporal_issue_registry_summary = summarize_temporal_issue_registry(
        intake_case_summary.get("temporal_issue_registry_summary")
    )
    issues = temporal_issue_registry_summary.get("issues") or []
    matching_issues = [
        issue for issue in issues
        if isinstance(issue, dict)
        and normalized_claim_type in {
            _normalize_handoff_identity(item)
            for item in list(issue.get("claim_types") or []) + [issue.get("claim_type")]
            if _normalize_handoff_identity(item)
        }
    ]
    if not matching_issues:
        return {}

    return summarize_temporal_issue_registry(
        {
            "count": len(matching_issues),
            "issues": matching_issues,
        }
    )


def _merge_claim_temporal_registry_into_reasoning_review(
    review: Dict[str, Any],
    *,
    intake_case_summary: Dict[str, Any],
    claim_type: Optional[str],
) -> Dict[str, Any]:
    merged_review = dict(review or {})
    claim_temporal_registry_summary = _build_claim_temporal_registry_summary(
        intake_case_summary,
        claim_type=claim_type,
    )
    if not claim_temporal_registry_summary:
        return merged_review

    merged_review["claim_temporal_issue_count"] = int(
        claim_temporal_registry_summary.get("count") or 0
    )
    merged_review["claim_unresolved_temporal_issue_count"] = int(
        claim_temporal_registry_summary.get("unresolved_count") or 0
    )
    merged_review["claim_resolved_temporal_issue_count"] = int(
        claim_temporal_registry_summary.get("resolved_count") or 0
    )
    merged_review["claim_temporal_issue_status_counts"] = dict(
        claim_temporal_registry_summary.get("status_counts") or {}
    )
    merged_review["claim_temporal_issue_ids"] = list(
        claim_temporal_registry_summary.get("issue_ids") or []
    )
    merged_review["claim_missing_temporal_predicates"] = list(
        claim_temporal_registry_summary.get("missing_temporal_predicates") or []
    )
    merged_review["claim_required_provenance_kinds"] = list(
        claim_temporal_registry_summary.get("required_provenance_kinds") or []
    )
    return merged_review


def _merge_intake_summary_handoff_metadata(
    metadata: Optional[Dict[str, Any]],
    mediator: Any,
    *,
    claim_type: Optional[str] = None,
    claim_element_id: Optional[str] = None,
) -> Dict[str, Any]:
    merged_metadata = dict(metadata or {})
    handoff_metadata = _build_confirmed_intake_summary_handoff_metadata(mediator)
    temporal_handoff_metadata = _build_claim_support_temporal_handoff_metadata(
        mediator,
        claim_type=claim_type,
        claim_element_id=claim_element_id,
    )
    if handoff_metadata:
        merged_metadata.update(handoff_metadata)
    if temporal_handoff_metadata:
        merged_metadata.update(temporal_handoff_metadata)
    return merged_metadata


def _build_review_workflow_phase_plan(
    mediator: Any,
    *,
    intake_status: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
) -> Dict[str, Any]:
    phase_manager = getattr(mediator, "phase_manager", None)
    phases: Dict[str, Dict[str, Any]] = {}

    graph_phase = build_graph_analysis_phase_guidance(phase_manager, audience="review")
    if graph_phase:
        phases["graph_analysis"] = graph_phase

    document_phase = build_review_document_generation_phase_guidance(
        intake_status=intake_status,
        intake_case_summary=intake_case_summary,
    )
    if document_phase:
        phases["document_generation"] = document_phase

    return build_workflow_phase_plan(phases)


def _build_review_workflow_phase_priority(
    workflow_phase_plan: Dict[str, Any],
) -> Dict[str, Any]:
    prioritized_phase_context = resolve_prioritized_workflow_phase(workflow_phase_plan)
    prioritized_phase_name = str(prioritized_phase_context.get("phase_name") or "").strip()
    if not prioritized_phase_name:
        return {}
    prioritized_phase = dict(prioritized_phase_context.get("phase") or {})
    prioritized_status = str(prioritized_phase_context.get("status") or "warning").strip().lower() or "warning"
    prioritized_signals = dict(prioritized_phase_context.get("signals") or {})
    recommended_actions = list(prioritized_phase_context.get("recommended_actions") or [])

    if prioritized_phase_name == "graph_analysis":
        knowledge_graph_available = bool(prioritized_signals.get("knowledge_graph_available"))
        dependency_graph_available = bool(prioritized_signals.get("dependency_graph_available"))
        remaining_gap_count = int(prioritized_signals.get("remaining_gap_count") or 0)
        current_gap_count = int(prioritized_signals.get("current_gap_count") or 0)
        chip_labels = [
            f"workflow phase: {humanize_workflow_priority_label(prioritized_phase_name)}",
            f"phase status: {humanize_workflow_priority_label(prioritized_status)}",
        ]
        if not knowledge_graph_available:
            chip_labels.extend(
                [
                    "knowledge graph available: no",
                    f"dependency graph available: {'yes' if dependency_graph_available else 'no'}",
                ]
            )
            action_id = "review_knowledge_graph_inputs"
            button_id = "intake-next-action-review-knowledge-graph"
            action_label = "Review intake graph inputs"
            status_message = "Showing timeline and canonical fact inputs for intake graph building."
        elif not dependency_graph_available:
            chip_labels.extend(
                [
                    "knowledge graph available: yes",
                    "dependency graph available: no",
                ]
            )
            action_id = "review_dependency_inputs"
            button_id = "intake-next-action-review-dependencies"
            action_label = "Review dependency inputs"
            status_message = "Showing alignment and contradiction inputs for dependency graph review."
        else:
            chip_labels.extend(
                [
                    f"remaining gap count: {remaining_gap_count}",
                    f"current gap count: {current_gap_count}",
                ]
            )
            unresolved_temporal_issue_count = int(prioritized_signals.get("unresolved_temporal_issue_count") or 0)
            resolved_temporal_issue_count = int(prioritized_signals.get("resolved_temporal_issue_count") or 0)
            if unresolved_temporal_issue_count > 0:
                chip_labels.append(f"unresolved chronology issues: {unresolved_temporal_issue_count}")
            if resolved_temporal_issue_count > 0:
                chip_labels.append(f"resolved chronology issues: {resolved_temporal_issue_count}")
            if "knowledge_graph_enhanced" in prioritized_signals:
                chip_labels.append(
                    f"knowledge graph enhanced: {'yes' if bool(prioritized_signals.get('knowledge_graph_enhanced')) else 'no'}"
                )
            action_id = "review_intake_gaps"
            button_id = "intake-next-action-review-gaps"
            action_label = "Review intake gaps"
            status_message = "Showing unresolved intake gaps and targeted questions."

        return {
            "phase_name": prioritized_phase_name,
            "status": prioritized_status,
            "title": "Resolve graph analysis before drafting",
            "summary": str(prioritized_phase.get("summary") or "").strip(),
            "recommended_actions": recommended_actions,
            "chip_labels": chip_labels,
            "action_id": action_id,
            "button_id": button_id,
            "action_label": action_label,
            "status_message": status_message,
            "signals": prioritized_signals,
        }

    if prioritized_phase_name == "document_generation":
        proof_readiness_score = float(prioritized_signals.get("proof_readiness_score") or 0.0)
        chronology_blocked = bool(prioritized_signals.get("chronology_blocked"))
        temporal_gap_task_count = int(prioritized_signals.get("temporal_gap_task_count") or 0)
        unresolved_temporal_issue_count = int(prioritized_signals.get("unresolved_temporal_issue_count") or 0)
        unresolved_without_review_path_count = int(
            prioritized_signals.get("unresolved_without_review_path_count") or 0
        )
        recommended_next_action = str(prioritized_signals.get("recommended_next_action") or "").strip()
        chip_labels = [
            f"workflow phase: {humanize_workflow_priority_label(prioritized_phase_name)}",
            f"phase status: {humanize_workflow_priority_label(prioritized_status)}",
            f"proof readiness: {proof_readiness_score:.2f}",
            f"unresolved temporal issues: {unresolved_temporal_issue_count}",
            f"unresolved without review path: {unresolved_without_review_path_count}",
        ]
        missing_proof_artifact_count = int(prioritized_signals.get("missing_proof_artifact_count") or 0)
        if missing_proof_artifact_count > 0:
            chip_labels.append(f"missing proof artifacts: {missing_proof_artifact_count}")
        if chronology_blocked:
            chip_labels.append("chronology blocked: Yes")
        if temporal_gap_task_count > 0:
            chip_labels.append(f"chronology gap tasks: {temporal_gap_task_count}")
        if recommended_next_action:
            chip_labels.append(f"recommended action: {recommended_next_action}")
        return {
            "phase_name": prioritized_phase_name,
            "status": prioritized_status,
            "title": "Resolve drafting readiness before filing",
            "summary": str(prioritized_phase.get("summary") or "").strip(),
            "recommended_actions": recommended_actions,
            "chip_labels": chip_labels,
            "action_id": "review_packet_readiness",
            "button_id": "intake-next-action-review-packet-readiness",
            "action_label": "Review packet readiness",
            "status_message": "Showing packet readiness summary and evidence blockers before drafting.",
            "signals": prioritized_signals,
        }

    return {}


def _build_review_workflow_priority_button(
    button_id: str,
    label: str,
    *,
    style: str = "secondary",
    data_attrs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": button_id,
        "label": label,
        "style": style,
        "data_attrs": {
            key: value
            for key, value in dict(data_attrs or {}).items()
            if str(value or "").strip()
        },
    }


def _build_review_workflow_priority_from_phase(
    workflow_phase_priority: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(workflow_phase_priority, dict) or not workflow_phase_priority:
        return {}

    action_id = str(workflow_phase_priority.get("action_id") or "workflow_phase_priority").strip()
    button_id = str(workflow_phase_priority.get("button_id") or "").strip()
    action_label = str(workflow_phase_priority.get("action_label") or "Review workflow priority").strip()
    notes = [str(workflow_phase_priority.get("summary") or "").strip()]
    signals = dict(workflow_phase_priority.get("signals") or {})
    chronology_blocked = bool(signals.get("chronology_blocked"))
    unresolved_temporal_issue_count = int(signals.get("unresolved_temporal_issue_count") or 0)
    temporal_gap_task_count = int(signals.get("temporal_gap_task_count") or 0)
    if chronology_blocked or unresolved_temporal_issue_count > 0 or temporal_gap_task_count > 0:
        chronology_note_parts: List[str] = []
        if temporal_gap_task_count > 0:
            task_label = "task" if temporal_gap_task_count == 1 else "tasks"
            chronology_note_parts.append(f"{temporal_gap_task_count} pending chronology gap {task_label}")
        if unresolved_temporal_issue_count > 0:
            issue_label = "issue ID" if unresolved_temporal_issue_count == 1 else "issue IDs"
            chronology_note_parts.append(
                f"{unresolved_temporal_issue_count} unresolved temporal {issue_label}"
            )
        if chronology_note_parts:
            notes.append(f"Chronology blockers: {'; '.join(chronology_note_parts)}.")
    recommended_actions = [
        str(item).strip()
        for item in (workflow_phase_priority.get("recommended_actions") or [])
        if str(item or "").strip()
    ]
    if recommended_actions:
        notes.append(f"Recommended actions: {' | '.join(recommended_actions)}")

    return {
        "status": str(workflow_phase_priority.get("status") or "warning").strip().lower() or "warning",
        "status_id": f"workflow_phase_{action_id}",
        "title": str(workflow_phase_priority.get("title") or "Review workflow priority before drafting").strip(),
        "chip_labels": list(workflow_phase_priority.get("chip_labels") or []),
        "notes": [note for note in notes if note],
        "buttons": [
            _build_review_workflow_priority_button(button_id, action_label)
            if button_id
            else _build_review_workflow_priority_button(
                f"intake-next-action-{action_id}",
                action_label,
            )
        ],
        "action_id": action_id,
        "status_message": str(workflow_phase_priority.get("status_message") or "").strip(),
    }


def _build_review_workflow_priority(
    *,
    intake_status: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
    workflow_phase_priority: Dict[str, Any],
) -> Dict[str, Any]:
    document_grounding_lane_outcome_summary = (
        intake_case_summary.get("document_grounding_lane_outcome_summary")
        if isinstance(intake_case_summary.get("document_grounding_lane_outcome_summary"), dict)
        else {}
    )
    document_grounding_improvement_next_action = (
        intake_case_summary.get("document_grounding_improvement_next_action")
        if isinstance(intake_case_summary.get("document_grounding_improvement_next_action"), dict)
        else {}
    )
    grounding_action = str(document_grounding_improvement_next_action.get("action") or "").strip().lower()
    if grounding_action in {"refine_document_grounding_strategy", "retarget_document_grounding"}:
        claim_element_id = str(document_grounding_improvement_next_action.get("claim_element_id") or "").strip()
        suggested_claim_element_id = str(document_grounding_improvement_next_action.get("suggested_claim_element_id") or "").strip()
        preferred_support_kind = str(document_grounding_improvement_next_action.get("preferred_support_kind") or "").strip()
        suggested_support_kind = str(document_grounding_improvement_next_action.get("suggested_support_kind") or "").strip()
        focus_section = str(document_grounding_improvement_next_action.get("focus_section") or "").strip()
        status = str(document_grounding_improvement_next_action.get("status") or "stalled").strip().lower() or "stalled"
        attempted_support_kind = str(document_grounding_lane_outcome_summary.get("attempted_support_kind") or "").strip()
        learned_support_kind = str(document_grounding_lane_outcome_summary.get("recommended_future_support_kind") or "").strip()
        chip_labels = [f"grounding status: {humanize_workflow_priority_label(status)}"]
        if claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(claim_element_id)}")
        if suggested_claim_element_id and suggested_claim_element_id != claim_element_id:
            chip_labels.append(f"next target element: {humanize_workflow_priority_label(suggested_claim_element_id)}")
        if focus_section:
            chip_labels.append(f"focus section: {humanize_workflow_priority_label(focus_section)}")
        if preferred_support_kind:
            chip_labels.append(f"current support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        if attempted_support_kind and attempted_support_kind != preferred_support_kind:
            chip_labels.append(f"attempted lane: {humanize_workflow_priority_label(attempted_support_kind)}")
        if learned_support_kind:
            chip_labels.append(f"learned next lane: {humanize_workflow_priority_label(learned_support_kind)}")
        elif suggested_support_kind:
            chip_labels.append(f"suggested next lane: {humanize_workflow_priority_label(suggested_support_kind)}")
        notes = [
            str(
                document_grounding_improvement_next_action.get("description")
                or "Grounding recovery stalled; switch support lanes or retarget the next grounding cycle."
            ).strip(),
            "Review the factual allegations and try a different support lane or narrower claim-element target before continuing broad document revisions.",
        ]
        if learned_support_kind:
            notes.append(
                f"Recent grounding cycles suggest {humanize_workflow_priority_label(learned_support_kind)} is the stronger lane for the next recovery pass."
            )
        if grounding_action == "retarget_document_grounding" and suggested_claim_element_id and suggested_claim_element_id != claim_element_id:
            notes.append(
                f"Shift the next grounding pass from {humanize_workflow_priority_label(claim_element_id)} to {humanize_workflow_priority_label(suggested_claim_element_id)}."
            )
        return {
            "status": "warning",
            "status_id": grounding_action,
            "title": (
                "Retarget document grounding"
                if grounding_action == "retarget_document_grounding"
                else "Refine document grounding strategy"
            ),
            "chip_labels": chip_labels,
            "notes": notes,
            "buttons": [
                _build_review_workflow_priority_button(
                    "intake-next-action-review-grounding-strategy",
                    "Review grounding strategy",
                )
            ],
            "action_id": grounding_action,
            "status_message": (
                "Reviewing document grounding strategy, support-lane targeting, and next claim-element focus."
                if grounding_action == "retarget_document_grounding"
                else "Reviewing document grounding strategy and support-lane targeting."
            ),
        }

    document_drafting_next_action = (
        intake_case_summary.get("document_drafting_next_action")
        if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
        else {}
    )
    if str(document_drafting_next_action.get("action") or "").strip().lower() == "realign_document_drafting":
        target_claim_element_id = str(document_drafting_next_action.get("claim_element_id") or "").strip()
        executed_claim_element_id = str(document_drafting_next_action.get("executed_claim_element_id") or "").strip()
        focus_section = str(document_drafting_next_action.get("focus_section") or "").strip()
        preferred_support_kind = str(document_drafting_next_action.get("preferred_support_kind") or "").strip()
        chip_labels = []
        if target_claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(target_claim_element_id)}")
        if executed_claim_element_id:
            chip_labels.append(f"executed first: {humanize_workflow_priority_label(executed_claim_element_id)}")
        if focus_section:
            chip_labels.append(f"focus section: {humanize_workflow_priority_label(focus_section)}")
        if preferred_support_kind:
            chip_labels.append(f"support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        return {
            "status": "warning",
            "status_id": "realign_document_drafting",
            "title": "Realign drafting before further revisions",
            "chip_labels": chip_labels,
            "notes": [
                str(
                    document_drafting_next_action.get("description")
                    or "Realign drafting to the top targeted claim element before further revisions."
                ).strip(),
                "Open the formal complaint builder and redirect the next draft revision toward the targeted legal element before broadening further edits.",
            ],
            "buttons": [
                _build_review_workflow_priority_button(
                    "intake-next-action-open-document-builder",
                    "Open formal complaint builder",
                )
            ],
            "action_id": "realign_document_drafting",
            "status_message": "Opening the formal complaint builder for drafting realignment.",
        }

    next_action = intake_case_summary.get("next_action") if isinstance(intake_case_summary.get("next_action"), dict) else {}
    if not next_action and isinstance(intake_status.get("next_action"), dict):
        next_action = dict(intake_status.get("next_action") or {})

    action = str(next_action.get("action") or "").strip().lower()
    if not action:
        return _build_review_workflow_priority_from_phase(workflow_phase_priority)

    contradiction_summary = (
        intake_case_summary.get("contradiction_summary")
        if isinstance(intake_case_summary.get("contradiction_summary"), dict)
        else {}
    )
    question_candidate_summary = (
        intake_case_summary.get("question_candidate_summary")
        if isinstance(intake_case_summary.get("question_candidate_summary"), dict)
        else {}
    )
    timeline_anchor_summary = (
        intake_case_summary.get("timeline_anchor_summary")
        if isinstance(intake_case_summary.get("timeline_anchor_summary"), dict)
        else {}
    )
    canonical_fact_summary = (
        intake_case_summary.get("canonical_fact_summary")
        if isinstance(intake_case_summary.get("canonical_fact_summary"), dict)
        else {}
    )
    candidate_claim_summary = (
        intake_case_summary.get("candidate_claim_summary")
        if isinstance(intake_case_summary.get("candidate_claim_summary"), dict)
        else {}
    )
    intake_matching_summary = (
        intake_case_summary.get("intake_matching_summary")
        if isinstance(intake_case_summary.get("intake_matching_summary"), dict)
        else {}
    )
    intake_legal_targeting_summary = (
        intake_case_summary.get("intake_legal_targeting_summary")
        if isinstance(intake_case_summary.get("intake_legal_targeting_summary"), dict)
        else {}
    )
    intake_evidence_alignment_summary = (
        intake_case_summary.get("intake_evidence_alignment_summary")
        if isinstance(intake_case_summary.get("intake_evidence_alignment_summary"), dict)
        else {}
    )
    claim_support_packet_summary = (
        intake_case_summary.get("claim_support_packet_summary")
        if isinstance(intake_case_summary.get("claim_support_packet_summary"), dict)
        else {}
    )
    temporal_issue_registry_summary = (
        intake_case_summary.get("temporal_issue_registry_summary")
        if isinstance(intake_case_summary.get("temporal_issue_registry_summary"), dict)
        else {}
    )
    summary_confirmation = (
        intake_case_summary.get("complainant_summary_confirmation")
        if isinstance(intake_case_summary.get("complainant_summary_confirmation"), dict)
        else {}
    )
    alignment_promotion_drift_summary = (
        intake_case_summary.get("alignment_promotion_drift_summary")
        if isinstance(intake_case_summary.get("alignment_promotion_drift_summary"), dict)
        else {}
    )
    alignment_validation_focus_summary = (
        intake_case_summary.get("alignment_validation_focus_summary")
        if isinstance(intake_case_summary.get("alignment_validation_focus_summary"), dict)
        else {}
    )
    alignment_evidence_tasks = [
        item for item in (intake_case_summary.get("alignment_evidence_tasks") or []) if isinstance(item, dict)
    ]
    alignment_task_updates = [
        item for item in (intake_case_summary.get("alignment_task_updates") or []) if isinstance(item, dict)
    ]
    alignment_task_update_history = [
        item for item in (intake_case_summary.get("alignment_task_update_history") or []) if isinstance(item, dict)
    ]
    visible_alignment_task_updates = alignment_task_update_history or alignment_task_updates

    focused_claim_type = str(next_action.get("claim_type") or "").strip().lower()
    focused_element_id = str(next_action.get("claim_element_id") or "").strip().lower()
    focused_element_label = str(next_action.get("claim_element_label") or "").strip()
    recommended_actions = [
        str(item).strip()
        for item in (next_action.get("recommended_actions") or [])
        if str(item or "").strip()
    ]

    def humanize(value: Any) -> str:
        return humanize_workflow_priority_label(value)

    def build_priority(
        *,
        status: str = "warning",
        title: str,
        status_id: str,
        chip_labels: List[str],
        notes: List[str],
        buttons: List[Dict[str, Any]],
        status_message: str,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "title": title,
            "status_id": status_id,
            "chip_labels": [item for item in chip_labels if item],
            "notes": [item for item in notes if item],
            "buttons": [item for item in buttons if isinstance(item, dict) and item.get("id")],
            "action_id": action,
            "status_message": status_message,
        }

    if action == "validate_promoted_support":
        drift_summary = dict(next_action.get("drift_summary") or {}) if isinstance(next_action.get("drift_summary"), dict) else dict(alignment_promotion_drift_summary)
        primary_validation_target = (
            dict(intake_status.get("primary_validation_target") or {})
            if isinstance(intake_status.get("primary_validation_target"), dict)
            else {}
        )
        if not primary_validation_target and isinstance(next_action.get("primary_validation_target"), dict):
            primary_validation_target = dict(next_action.get("primary_validation_target") or {})
        if not primary_validation_target and isinstance(alignment_validation_focus_summary.get("primary_target"), dict):
            primary_validation_target = dict(alignment_validation_focus_summary.get("primary_target") or {})
        pending_conversion_count = int(next_action.get("pending_conversion_count") or drift_summary.get("pending_conversion_count") or 0)
        promoted_count = int(next_action.get("promoted_count") or drift_summary.get("promoted_count") or 0)
        validation_target_count = int(
            next_action.get("validation_target_count")
            or alignment_validation_focus_summary.get("count")
            or len(alignment_validation_focus_summary.get("targets") or [])
            or 0
        )
        drift_ratio = float(drift_summary.get("drift_ratio") or 0.0)
        proof_readiness_score = float(drift_summary.get("proof_readiness_score") or 0.0)
        chip_labels = [
            f"recommended action: {action}",
            f"pending conversion: {pending_conversion_count}",
            f"promoted updates: {promoted_count}",
            f"validation targets: {validation_target_count}",
            f"drift ratio: {drift_ratio:.2f}",
            f"proof readiness: {proof_readiness_score:.2f}",
        ]
        if focused_claim_type:
            chip_labels.append(f"focus claim: {humanize(focused_claim_type)}")
        if focused_element_id:
            chip_labels.append(f"focus element: {humanize(focused_element_id)}")
        primary_target_claim_type = str(primary_validation_target.get("claim_type") or focused_claim_type or "").strip()
        primary_target_element_id = str(primary_validation_target.get("claim_element_id") or focused_element_id or "").strip()
        if primary_target_element_id:
            chip_labels.append(f"primary target: {humanize(primary_target_element_id)}")
        primary_target_kind = str(primary_validation_target.get("promotion_kind") or "").strip()
        if primary_target_kind:
            chip_labels.append(f"primary promotion kind: {humanize(primary_target_kind)}")
        primary_target_ref = str(primary_validation_target.get("promotion_ref") or "").strip()
        if primary_target_ref:
            chip_labels.append(f"primary promotion ref: {primary_target_ref}")
        notes = [
            "Promoted testimony or document support is accumulating faster than packet validation is reaching resolved supported status.",
        ]
        if primary_target_element_id:
            notes.append(f"Primary validation target: {humanize(primary_target_element_id)}.")
        if primary_target_ref:
            notes.append(f"Primary promotion ref: {primary_target_ref}.")
        notes.append("Review and validate saved support before treating the evidence phase as truly settled.")
        buttons = [
            _build_review_workflow_priority_button(
                "intake-next-action-open-promoted",
                "Review promoted updates",
                data_attrs={
                    "claim_type": primary_target_claim_type,
                    "claim_element_id": primary_target_element_id,
                },
            ),
        ]
        if primary_target_element_id:
            buttons.extend(
                [
                    _build_review_workflow_priority_button(
                        "intake-next-action-prefill-testimony",
                        "Prefill testimony validation",
                        style="tertiary",
                        data_attrs={
                            "claim_type": primary_target_claim_type,
                            "claim_element_id": primary_target_element_id,
                        },
                    ),
                    _build_review_workflow_priority_button(
                        "intake-next-action-prefill-document",
                        "Prefill document validation",
                        style="tertiary",
                        data_attrs={
                            "claim_type": primary_target_claim_type,
                            "claim_element_id": primary_target_element_id,
                        },
                    ),
                ]
            )
        return build_priority(
            title="Validate promoted support",
            status_id=action,
            chip_labels=chip_labels,
            notes=notes,
            buttons=buttons,
            status_message="Showing promoted alignment updates that still need validation.",
        )

    if action == "build_knowledge_graph":
        timeline_anchor_count = int(timeline_anchor_summary.get("count") or 0)
        canonical_fact_count = int(canonical_fact_summary.get("count") or 0)
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        readiness_score = float(next_action.get("intake_readiness_score") or 0.0)
        chip_labels = [
            "recommended action: build_knowledge_graph",
            f"timeline anchors: {timeline_anchor_count}",
            f"canonical facts: {canonical_fact_count}",
            f"question candidates: {question_candidate_count}",
        ]
        if readiness_score > 0:
            chip_labels.append(f"readiness score: {readiness_score:.2f}")
        return build_priority(
            title="Build intake knowledge graph",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Intake facts and timeline anchors are present, but the knowledge graph has not been built into an operator-reviewable structure yet.",
                "Focus the timeline and canonical fact diagnostics before advancing graph-dependent intake work.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-knowledge-graph", "Review intake graph inputs")],
            status_message="Showing timeline and canonical fact inputs for intake graph building.",
        )

    if action == "build_dependency_graph":
        aligned_element_count = int(intake_evidence_alignment_summary.get("aligned_element_count") or 0)
        contradiction_count = int(contradiction_summary.get("count") or 0)
        alignment_task_count = len(alignment_evidence_tasks)
        readiness_score = float(next_action.get("intake_readiness_score") or 0.0)
        chip_labels = [
            "recommended action: build_dependency_graph",
            f"aligned elements: {aligned_element_count}",
            f"alignment tasks: {alignment_task_count}",
            f"contradictions: {contradiction_count}",
        ]
        if readiness_score > 0:
            chip_labels.append(f"readiness score: {readiness_score:.2f}")
        return build_priority(
            title="Build intake dependency graph",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Intake sections are populated enough to map cross-section dependencies, but the dependency graph has not been built yet.",
                "Review contradictions and alignment summaries before dependency-driven intake routing continues.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-dependencies", "Review dependency inputs")],
            status_message="Showing alignment and contradiction inputs for dependency graph review.",
        )

    if action == "continue_denoising":
        intake_blockers = [item for item in (next_action.get("intake_blockers") or []) if str(item or "").strip()]
        contradiction_count = int(contradiction_summary.get("count") or 0)
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        readiness_score = float(next_action.get("intake_readiness_score") or 0.0)
        chip_labels = [
            "recommended action: continue_denoising",
            f"blockers: {len(intake_blockers)}",
            f"contradictions: {contradiction_count}",
            f"question candidates: {question_candidate_count}",
        ]
        if readiness_score > 0:
            chip_labels.append(f"readiness score: {readiness_score:.2f}")
        return build_priority(
            title="Continue intake denoising",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Intake contradictions or open clarification paths still need another denoising pass before the case theory can settle.",
                "Review the contradiction queue and targeted questions that should drive the next intake refinement pass.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-denoising", "Review denoising queue")],
            status_message="Showing contradictions and targeted questions for continued intake denoising.",
        )

    if action == "build_legal_graph":
        candidate_claim_count = int(candidate_claim_summary.get("count") or 0)
        targeted_claims = intake_legal_targeting_summary.get("claims") if isinstance(intake_legal_targeting_summary.get("claims"), dict) else intake_matching_summary.get("claims") if isinstance(intake_matching_summary.get("claims"), dict) else {}
        targeted_claim_entries = list(targeted_claims.items())
        open_legal_element_count = sum(
            int((claim or {}).get("missing_requirement_count") or 0)
            for _, claim in targeted_claim_entries
            if isinstance(claim, dict)
        )
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        return build_priority(
            title="Build legal graph",
            status_id=action,
            chip_labels=[
                "recommended action: build_legal_graph",
                f"candidate claims: {candidate_claim_count}",
                f"targeted claims: {len(targeted_claim_entries)}",
                f"open legal elements: {open_legal_element_count}",
                f"question candidates: {question_candidate_count}",
            ],
            notes=[
                "Claim targeting is available, but the legal graph that organizes statutes and requirements has not been built yet.",
                "Review unresolved legal elements and mapped question targets before building the formalization graph.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-legal-graph", "Review legal graph inputs")],
            status_message="Showing unresolved legal elements and question targets for legal graph review.",
        )

    if action == "perform_neurosymbolic_matching":
        targeted_claims = intake_legal_targeting_summary.get("claims") if isinstance(intake_legal_targeting_summary.get("claims"), dict) else intake_matching_summary.get("claims") if isinstance(intake_matching_summary.get("claims"), dict) else {}
        targeted_claim_entries = list(targeted_claims.items())
        open_legal_element_count = sum(
            int((claim or {}).get("missing_requirement_count") or 0)
            for _, claim in targeted_claim_entries
            if isinstance(claim, dict)
        )
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        return build_priority(
            title="Perform neurosymbolic matching",
            status_id=action,
            chip_labels=[
                "recommended action: perform_neurosymbolic_matching",
                f"targeted claims: {len(targeted_claim_entries)}",
                f"open legal elements: {open_legal_element_count}",
                f"question candidates: {question_candidate_count}",
            ],
            notes=[
                "The legal graph is available, but formal claim-to-law matching still needs operator review support.",
                "Review unresolved legal elements and matching questions before running the neurosymbolic matcher.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-matching", "Review matching inputs")],
            status_message="Showing unresolved legal elements and question targets for neurosymbolic matching.",
        )

    if action == "generate_formal_complaint":
        claim_count = int(claim_support_packet_summary.get("claim_count") or 0)
        element_count = int(claim_support_packet_summary.get("element_count") or 0)
        proof_readiness_score = float(claim_support_packet_summary.get("proof_readiness_score") or 0.0)
        draft_ready_ratio = float(claim_support_packet_summary.get("draft_ready_element_ratio") or 0.0)
        return build_priority(
            title="Generate formal complaint",
            status_id=action,
            chip_labels=[
                "recommended action: generate_formal_complaint",
                f"claims: {claim_count}",
                f"elements: {element_count}",
                f"packet draft ready: {draft_ready_ratio:.2f}",
                f"proof readiness: {proof_readiness_score:.2f}",
            ],
            notes=[
                "Formalization is ready to move from matching outputs into a draft complaint package.",
                "Open the formal complaint builder with the current claim and user context preserved.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-open-formal-generator", "Open formal complaint builder")],
            status_message="Opening the formal complaint builder.",
        )

    if action == "build_claim_support_packets":
        packet_element_count = int(claim_support_packet_summary.get("element_count") or 0)
        packet_claim_count = int(claim_support_packet_summary.get("claim_count") or 0)
        chip_labels = [
            "recommended action: build_claim_support_packets",
            f"claims: {packet_claim_count}",
            f"elements: {packet_element_count}",
        ]
        for item in recommended_actions[:2]:
            chip_labels.append(f"recommended lane: {humanize(item)}")
        return build_priority(
            title="Build claim support packets",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Evidence records exist, but the claim support packet still needs an explicit packet build before evidence review can be trusted.",
                "Execute the packet-building follow-up to refresh packet statuses and downstream review surfaces.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-build-packets", "Build claim support packets")],
            status_message="Executing claim support packet follow-up.",
        )

    if action == "resolve_support_conflicts":
        manual_review_blocker_count = sum(
            1
            for update in visible_alignment_task_updates
            if str((update or {}).get("resolution_status") or "").strip().lower() == "needs_manual_review"
        )
        reviewable_escalations = int(
            claim_support_packet_summary.get("claim_support_reviewable_escalation_count")
            or manual_review_blocker_count
            or 0
        )
        unresolved_without_review_path = int(
            claim_support_packet_summary.get("claim_support_unresolved_without_review_path_count") or 0
        )
        claim_type = str(next_action.get("claim_type") or "").strip()
        claim_element_id = str(next_action.get("claim_element_id") or "").strip()
        claim_element_text = focused_element_label or claim_element_id
        chip_labels = [
            "recommended action: resolve_support_conflicts",
            f"manual review blockers: {manual_review_blocker_count}",
            f"packet escalations: {reviewable_escalations}",
        ]
        if unresolved_without_review_path > 0:
            chip_labels.append(f"without review path: {unresolved_without_review_path}")
        if focused_claim_type:
            chip_labels.append(f"focus claim: {humanize(focused_claim_type)}")
        if focused_element_id:
            chip_labels.append(f"focus element: {humanize(focused_element_id)}")
        support_status = str(next_action.get("support_status") or "").strip()
        if support_status:
            chip_labels.append(f"support status: {humanize(support_status)}")
        for item in recommended_actions[:2]:
            chip_labels.append(f"recommended lane: {humanize(item)}")
        return build_priority(
            title="Resolve support conflicts",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Contradicted or escalated support is blocking evidence completion for a priority element.",
                "Open the manual-review queue and resolve the focused conflict before evidence drift expands.",
            ],
            buttons=[
                _build_review_workflow_priority_button(
                    "intake-next-action-review-conflicts",
                    "Review manual conflicts",
                    data_attrs={
                        "claim_type": claim_type,
                        "claim_element_id": claim_element_id,
                        "claim_element_text": claim_element_text,
                    },
                ),
                _build_review_workflow_priority_button(
                    "intake-next-action-prefill-resolution",
                    "Load into resolution form",
                    style="tertiary",
                    data_attrs={
                        "claim_element_id": claim_element_id,
                        "claim_element_text": claim_element_text,
                    },
                ),
            ],
            status_message="Showing manual-review conflicts that are blocking evidence completion.",
        )

    if action in {"fill_temporal_chronology_gap", "fill_evidence_gaps"}:
        prioritized_alignment_tasks = [item for item in (next_action.get("alignment_tasks") or []) if isinstance(item, dict)]
        focused_alignment_task = next(
            (
                task for task in prioritized_alignment_tasks
                if (
                    not focused_claim_type
                    or str(task.get("claim_type") or "").strip().lower() == focused_claim_type
                )
                and (
                    not focused_element_id
                    or str(task.get("claim_element_id") or "").strip().lower() == focused_element_id
                )
            ),
            {},
        )
        if not focused_alignment_task:
            focused_alignment_task = next(
                (
                    task for task in alignment_evidence_tasks
                    if (
                        not focused_claim_type
                        or str(task.get("claim_type") or "").strip().lower() == focused_claim_type
                    )
                    and (
                        not focused_element_id
                        or str(task.get("claim_element_id") or "").strip().lower() == focused_element_id
                    )
                ),
                {},
            )
        preferred_support_kind = str(focused_alignment_task.get("preferred_support_kind") or "").strip().lower()
        fallback_lanes = [str(item).strip() for item in (focused_alignment_task.get("fallback_lanes") or []) if str(item or "").strip()]
        claim_type = str(next_action.get("claim_type") or "").strip()
        claim_element_id = str(next_action.get("claim_element_id") or "").strip()
        claim_element_text = focused_element_label or claim_element_id
        chip_labels = [f"recommended action: {action}"]
        if action == "fill_temporal_chronology_gap":
            unresolved_issue_ids = []
            for field_name in ("temporal_issue_ids", "timeline_issue_ids"):
                unresolved_issue_ids.extend(
                    [str(item).strip() for item in (focused_alignment_task.get(field_name) or []) if str(item or "").strip()]
                )
            unresolved_issue_ids = list(dict.fromkeys(unresolved_issue_ids))
            unresolved_issue_count = int(
                temporal_issue_registry_summary.get("unresolved_count")
                or len(unresolved_issue_ids)
                or 0
            )
            resolved_issue_count = int(temporal_issue_registry_summary.get("resolved_count") or 0)
            chip_labels.append(f"chronology issues: {unresolved_issue_count}")
            if resolved_issue_count > 0:
                chip_labels.append(f"resolved chronology issues: {resolved_issue_count}")
            title = "Resolve chronology blockers"
            notes = [
                "Temporal ordering is still unresolved for a shared intake-to-packet element.",
                "Review the chronology task, inspect the unresolved issue IDs, and collect support that clears the temporal blocker before advancing evidence completion.",
                f"Unresolved chronology issue IDs: {', '.join(unresolved_issue_ids) if unresolved_issue_ids else 'none recorded'}",
            ]
            if resolved_issue_count > 0:
                notes.append(
                    f"Resolved chronology history retained: {resolved_issue_count} issue(s)."
                )
            button_id = "intake-next-action-review-chronology-task"
            button_label = "Review chronology task"
            status = "blocked"
            status_message = "Showing chronology blocker task and unresolved issue IDs."
        else:
            title = "Fill evidence gaps"
            notes = [
                "Priority evidence is still missing for a shared intake-to-packet element.",
                "Review the focused evidence task and preferred support lane before advancing the packet.",
            ]
            button_id = "intake-next-action-review-evidence-task"
            button_label = "Review evidence task"
            status = "warning"
            status_message = "Showing priority evidence task and preferred support lane."
        if focused_claim_type:
            chip_labels.append(f"focus claim: {humanize(focused_claim_type)}")
        if focused_element_id:
            chip_labels.append(f"focus element: {humanize(focused_element_id)}")
        support_status = str(next_action.get("support_status") or "").strip()
        if support_status:
            chip_labels.append(f"support status: {humanize(support_status)}")
        temporal_objective = str(focused_alignment_task.get("temporal_proof_objective") or "").strip()
        if temporal_objective:
            chip_labels.append(f"chronology objective: {humanize(temporal_objective)}")
        if preferred_support_kind:
            chip_labels.append(f"preferred lane: {humanize(preferred_support_kind)}")
        quality_target = str(focused_alignment_task.get("source_quality_target") or "").strip()
        if quality_target:
            chip_labels.append(f"quality target: {humanize(quality_target)}")
        for lane in fallback_lanes[:2]:
            chip_labels.append(f"fallback lane: {humanize(lane)}")
        return build_priority(
            status=status,
            title=title,
            status_id=action,
            chip_labels=chip_labels,
            notes=notes,
            buttons=[
                _build_review_workflow_priority_button(
                    button_id,
                    button_label,
                    data_attrs={
                        "claim_type": claim_type,
                        "claim_element_id": claim_element_id,
                        "claim_element_text": claim_element_text,
                        "support_kind": preferred_support_kind,
                    },
                )
            ],
            status_message=status_message,
        )

    if action == "complete_evidence":
        proof_readiness_score = float(claim_support_packet_summary.get("proof_readiness_score") or 0.0)
        evidence_completion_ready = bool(claim_support_packet_summary.get("evidence_completion_ready"))
        chip_labels = [
            "recommended action: complete_evidence",
            f"packet completion ready: {'yes' if evidence_completion_ready else 'no'}",
            f"proof readiness: {proof_readiness_score:.2f}",
        ]
        for item in recommended_actions[:2]:
            chip_labels.append(f"recommended lane: {humanize(item)}")
        return build_priority(
            title="Begin formal complaint drafting",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Evidence support is sufficiently assembled to move from packet review into formal complaint drafting.",
                "Open the formal complaint builder with the current claim and user context preserved.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-open-document-builder", "Open formal complaint builder")],
            status_message="Opening the formal complaint builder.",
        )

    if action == "address_gaps":
        action_gaps = [str(item).strip() for item in (next_action.get("gaps") or []) if str(item or "").strip()]
        intake_blockers = [str(item).strip() for item in (next_action.get("intake_blockers") or []) if str(item or "").strip()]
        contradiction_count = int(contradiction_summary.get("count") or 0)
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        readiness_score = float(next_action.get("intake_readiness_score") or 0.0)
        chip_labels = [
            "recommended action: address_gaps",
            f"gap count: {len(action_gaps)}",
            f"blockers: {len(intake_blockers)}",
            f"contradictions: {contradiction_count}",
            f"question candidates: {question_candidate_count}",
        ]
        if readiness_score > 0:
            chip_labels.append(f"readiness score: {readiness_score:.2f}")
        for gap in action_gaps[:2]:
            chip_labels.append(f"gap: {humanize(gap)}")
        return build_priority(
            title="Review intake gaps",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Intake still has unresolved proof or chronology gaps that should be clarified before handoff quality degrades.",
                "Review the unresolved intake matching diagnostics and targeted questions.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-gaps", "Review intake gaps")],
            status_message="Showing unresolved intake gaps and targeted questions.",
        )

    if action == "confirm_intake_summary":
        current_summary_snapshot = (
            summary_confirmation.get("current_summary_snapshot")
            if isinstance(summary_confirmation.get("current_summary_snapshot"), dict)
            else {}
        )
        chip_labels = [
            "recommended action: confirm_intake_summary",
            f"candidate claims: {int(current_summary_snapshot.get('candidate_claim_count') or 0)}",
            f"canonical facts: {int(current_summary_snapshot.get('canonical_fact_count') or 0)}",
            f"proof leads: {int(current_summary_snapshot.get('proof_lead_count') or 0)}",
        ]
        open_item_count = int(current_summary_snapshot.get("open_item_count") or 0)
        if open_item_count > 0:
            chip_labels.append(f"open items: {open_item_count}")
        return build_priority(
            title="Confirm intake summary",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "The latest intake summary snapshot is still waiting for complainant confirmation before the intake phase can fully settle.",
                "Add an optional confirmation note above if needed, then confirm the intake summary.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-confirm-summary", "Confirm intake summary")],
            status_message="Confirming the current intake summary snapshot.",
        )

    return _build_review_workflow_priority_from_phase(workflow_phase_priority)


def summarize_claim_support_snapshot_lifecycle(
    snapshots: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    snapshot_map = snapshots if isinstance(snapshots, dict) else {}
    snapshot_kinds = sorted(
        kind for kind, snapshot in snapshot_map.items() if isinstance(snapshot, dict)
    )
    stale_snapshot_kinds = sorted(
        kind
        for kind in snapshot_kinds
        if bool((snapshot_map.get(kind) or {}).get("is_stale"))
    )
    fresh_snapshot_kinds = [
        kind for kind in snapshot_kinds if kind not in stale_snapshot_kinds
    ]
    retention_limits = sorted(
        {
            int(snapshot.get("retention_limit"))
            for snapshot in snapshot_map.values()
            if isinstance(snapshot, dict) and snapshot.get("retention_limit") is not None
        }
    )
    total_pruned_snapshot_count = sum(
        int((snapshot.get("pruned_snapshot_count", 0) or 0))
        for snapshot in snapshot_map.values()
        if isinstance(snapshot, dict)
    )
    return {
        "total_snapshot_count": len(snapshot_kinds),
        "fresh_snapshot_count": len(fresh_snapshot_kinds),
        "stale_snapshot_count": len(stale_snapshot_kinds),
        "snapshot_kinds": snapshot_kinds,
        "fresh_snapshot_kinds": fresh_snapshot_kinds,
        "stale_snapshot_kinds": stale_snapshot_kinds,
        "retention_limits": retention_limits,
        "total_pruned_snapshot_count": total_pruned_snapshot_count,
    }


def summarize_claim_reasoning_review(
    validation_claim: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    preview_limit = 3

    claim_validation = validation_claim if isinstance(validation_claim, dict) else {}
    elements = claim_validation.get("elements", [])
    if not isinstance(elements, list):
        elements = []
    claim_temporal_issue_count = int(
        claim_validation.get("claim_temporal_issue_count", 0) or 0
    )
    claim_unresolved_temporal_issue_count = int(
        claim_validation.get("claim_unresolved_temporal_issue_count", 0) or 0
    )
    claim_resolved_temporal_issue_count = int(
        claim_validation.get("claim_resolved_temporal_issue_count", 0) or 0
    )
    claim_temporal_issue_status_counts = (
        dict(claim_validation.get("claim_temporal_issue_status_counts") or {})
        if isinstance(claim_validation.get("claim_temporal_issue_status_counts"), dict)
        else {}
    )
    claim_temporal_issue_ids = [
        str(item).strip()
        for item in (claim_validation.get("claim_temporal_issue_ids") or [])
        if str(item).strip()
    ]
    claim_missing_temporal_predicates = [
        str(item).strip()
        for item in (claim_validation.get("claim_missing_temporal_predicates") or [])
        if str(item).strip()
    ]
    claim_required_provenance_kinds = [
        str(item).strip()
        for item in (claim_validation.get("claim_required_provenance_kinds") or [])
        if str(item).strip()
    ]

    flagged_elements: List[Dict[str, Any]] = []
    fallback_ontology_element_count = 0
    unavailable_backend_element_count = 0
    degraded_adapter_element_count = 0
    hybrid_bridge_element_count = 0
    hybrid_bridge_available_element_count = 0
    hybrid_tdfol_formula_count = 0
    hybrid_dcec_formula_count = 0
    hybrid_tdfol_formula_preview: List[str] = []
    hybrid_dcec_formula_preview: List[str] = []
    hybrid_formalism = ""
    hybrid_reasoning_mode = ""
    hybrid_compiler_bridge_path = ""
    temporal_element_count = 0
    temporal_fact_count = 0
    temporal_relation_count = 0
    temporal_issue_count = 0
    temporal_partial_order_ready_element_count = 0
    temporal_warning_count = 0
    temporal_warning_preview: List[str] = []
    temporal_relation_type_counts: Dict[str, int] = {}
    temporal_relation_preview: List[str] = []
    temporal_rule_profile_available_element_count = 0
    temporal_rule_profile_satisfied_element_count = 0
    temporal_rule_profile_partial_element_count = 0
    temporal_rule_profile_failed_element_count = 0
    temporal_proof_bundle_count = 0
    temporal_proof_bundle_status_counts: Dict[str, int] = {}
    theorem_export_blocked_element_count = 0
    theorem_export_chronology_task_count = 0
    proof_artifact_element_count = 0
    proof_artifact_available_element_count = 0
    proof_artifact_status_counts: Dict[str, int] = {}
    proof_artifact_explanation_element_count = 0
    proof_artifact_preview: List[str] = []

    for element in elements:
        if not isinstance(element, dict):
            continue
        reasoning = element.get("reasoning_diagnostics", {})
        if not isinstance(reasoning, dict):
            reasoning = {}
        adapter_statuses = reasoning.get("adapter_statuses", {})
        if not isinstance(adapter_statuses, dict):
            adapter_statuses = {}

        unavailable_adapters = sorted(
            name
            for name, summary in adapter_statuses.items()
            if isinstance(summary, dict) and not bool(summary.get("backend_available", False))
        )
        degraded_adapters = sorted(
            name
            for name, summary in adapter_statuses.items()
            if isinstance(summary, dict)
            and str(
                summary.get("implementation_status") or summary.get("status") or ""
            )
            in {"unavailable", "error", "not_implemented"}
        )
        used_fallback_ontology = bool(reasoning.get("used_fallback_ontology"))
        hybrid_reasoning = reasoning.get("hybrid_reasoning", {})
        if not isinstance(hybrid_reasoning, dict):
            hybrid_reasoning = {}
        hybrid_result = hybrid_reasoning.get("result", {})
        if not isinstance(hybrid_result, dict):
            hybrid_result = {}
        hybrid_bridge_used = bool(hybrid_reasoning)
        hybrid_bridge_available = bool(hybrid_result.get("compiler_bridge_available", False))
        element_formalism = str(hybrid_result.get("formalism") or "").strip()
        element_reasoning_mode = str(hybrid_result.get("reasoning_mode") or "").strip()
        element_compiler_bridge_path = str(
            hybrid_result.get("compiler_bridge_path") or ""
        ).strip()
        hybrid_tdfol_formulas = [
            str(formula)
            for formula in (hybrid_result.get("tdfol_formulas", []) or [])
            if str(formula).strip()
        ]
        hybrid_dcec_formulas = [
            str(formula)
            for formula in (hybrid_result.get("dcec_formulas", []) or [])
            if str(formula).strip()
        ]
        proof_artifact = hybrid_result.get("proof_artifact", {})
        if not isinstance(proof_artifact, dict):
            proof_artifact = {}
        element_proof_artifact_available = bool(proof_artifact.get("available", False))
        element_proof_artifact_status = str(
            proof_artifact.get("status") or ""
        ).strip()
        element_proof_artifact_proof_id = str(
            proof_artifact.get("proof_id") or ""
        ).strip()
        element_proof_artifact_proof_status = str(
            proof_artifact.get("proof_status") or ""
        ).strip()
        element_proof_artifact_sentence = str(
            proof_artifact.get("sentence") or ""
        ).strip()
        element_proof_artifact_reason = str(
            proof_artifact.get("reason") or ""
        ).strip()
        element_proof_artifact_violation_count = int(
            proof_artifact.get("violation_count", 0) or 0
        )
        proof_artifact_explanation = proof_artifact.get("explanation", {})
        if not isinstance(proof_artifact_explanation, dict):
            proof_artifact_explanation = {}
        element_proof_artifact_explanation_format = str(
            proof_artifact_explanation.get("format") or ""
        ).strip()
        element_proof_artifact_explanation_steps = list(
            proof_artifact_explanation.get("steps", []) or []
        )
        element_proof_artifact_explanation_text = str(
            proof_artifact_explanation.get("text") or ""
        ).strip()
        element_proof_artifact_theorem_export_metadata = proof_artifact.get(
            "theorem_export_metadata", {}
        )
        if not isinstance(element_proof_artifact_theorem_export_metadata, dict):
            element_proof_artifact_theorem_export_metadata = {}
        temporal_summary = reasoning.get("temporal_summary", {})
        if not isinstance(temporal_summary, dict):
            temporal_summary = {}
        element_temporal_fact_count = int(temporal_summary.get("fact_count", 0) or 0)
        element_temporal_relation_count = int(temporal_summary.get("relation_count", 0) or 0)
        element_temporal_issue_count = int(temporal_summary.get("issue_count", 0) or 0)
        element_temporal_warning_count = int(temporal_summary.get("warning_count", 0) or 0)
        element_temporal_partial_order_ready = bool(
            temporal_summary.get("partial_order_ready", False)
        )
        element_temporal_warnings = [
            str(warning)
            for warning in (temporal_summary.get("warnings", []) or [])
            if str(warning).strip()
        ]
        element_temporal_relation_preview = [
            str(relation)
            for relation in (temporal_summary.get("relation_preview", []) or [])
            if str(relation).strip()
        ]
        element_temporal_relation_type_counts = {
            str(name): int(count or 0)
            for name, count in (temporal_summary.get("relation_type_counts", {}) or {}).items()
            if str(name).strip()
        }
        temporal_rule_profile = reasoning.get("temporal_rule_profile", {})
        if not isinstance(temporal_rule_profile, dict):
            temporal_rule_profile = {}
        element_temporal_rule_profile_id = str(
            temporal_rule_profile.get("profile_id") or ""
        ).strip()
        element_temporal_rule_frame_id = str(
            temporal_rule_profile.get("rule_frame_id") or ""
        ).strip()
        element_temporal_rule_status = str(
            temporal_rule_profile.get("status") or ""
        ).strip()
        element_temporal_rule_blocking_reasons = [
            str(reason)
            for reason in (temporal_rule_profile.get("blocking_reasons", []) or [])
            if str(reason).strip()
        ]
        element_temporal_rule_warnings = [
            str(warning)
            for warning in (temporal_rule_profile.get("warnings", []) or [])
            if str(warning).strip()
        ]
        element_temporal_rule_follow_ups = [
            follow_up
            for follow_up in (temporal_rule_profile.get("recommended_follow_ups", []) or [])
            if isinstance(follow_up, dict)
        ]
        element_temporal_rule_available = bool(temporal_rule_profile.get("available", False))
        temporal_proof_bundle = reasoning.get("temporal_proof_bundle", {})
        if not isinstance(temporal_proof_bundle, dict):
            temporal_proof_bundle = {}
        element_temporal_proof_bundle_id = str(
            temporal_proof_bundle.get("proof_bundle_id") or ""
        ).strip()
        element_temporal_proof_bundle_status = str(
            temporal_proof_bundle.get("status") or ""
        ).strip()
        element_temporal_proof_bundle_fact_ids = [
            str(fact_id)
            for fact_id in (temporal_proof_bundle.get("temporal_fact_ids", []) or [])
            if str(fact_id).strip()
        ]
        element_temporal_proof_bundle_relation_ids = [
            str(relation_id)
            for relation_id in (temporal_proof_bundle.get("temporal_relation_ids", []) or [])
            if str(relation_id).strip()
        ]
        element_temporal_proof_bundle_issue_ids = [
            str(issue_id)
            for issue_id in (temporal_proof_bundle.get("temporal_issue_ids", []) or [])
            if str(issue_id).strip()
        ]
        theorem_exports = temporal_proof_bundle.get("theorem_exports", {})
        if not isinstance(theorem_exports, dict):
            theorem_exports = {}
        element_theorem_export_metadata = theorem_exports.get("theorem_export_metadata", {})
        if not isinstance(element_theorem_export_metadata, dict):
            element_theorem_export_metadata = {}
        element_temporal_proof_bundle_tdfol_preview = [
            str(formula)
            for formula in (theorem_exports.get("tdfol_formulas", []) or [])
            if str(formula).strip()
        ][:preview_limit]
        element_temporal_proof_bundle_dcec_preview = [
            str(formula)
            for formula in (theorem_exports.get("dcec_formulas", []) or [])
            if str(formula).strip()
        ][:preview_limit]
        hybrid_tdfol_count = len(hybrid_tdfol_formulas)
        hybrid_dcec_count = len(hybrid_dcec_formulas)
        element_tdfol_preview = hybrid_tdfol_formulas[:preview_limit]
        element_dcec_preview = hybrid_dcec_formulas[:preview_limit]

        if used_fallback_ontology:
            fallback_ontology_element_count += 1
        if unavailable_adapters:
            unavailable_backend_element_count += 1
        if degraded_adapters:
            degraded_adapter_element_count += 1
        if hybrid_bridge_used:
            hybrid_bridge_element_count += 1
        if hybrid_bridge_available:
            hybrid_bridge_available_element_count += 1
        hybrid_tdfol_formula_count += hybrid_tdfol_count
        hybrid_dcec_formula_count += hybrid_dcec_count
        if (
            element_temporal_fact_count
            or element_temporal_relation_count
            or element_temporal_issue_count
            or element_temporal_warning_count
            or element_temporal_relation_type_counts
            or element_temporal_relation_preview
        ):
            temporal_element_count += 1
        temporal_fact_count += element_temporal_fact_count
        temporal_relation_count += element_temporal_relation_count
        temporal_issue_count += element_temporal_issue_count
        temporal_warning_count += element_temporal_warning_count
        if element_temporal_partial_order_ready:
            temporal_partial_order_ready_element_count += 1
        if element_temporal_rule_available:
            temporal_rule_profile_available_element_count += 1
            if element_temporal_rule_status == "satisfied":
                temporal_rule_profile_satisfied_element_count += 1
            elif element_temporal_rule_status == "partial":
                temporal_rule_profile_partial_element_count += 1
            elif element_temporal_rule_status == "failed":
                temporal_rule_profile_failed_element_count += 1
        if element_temporal_proof_bundle_id:
            temporal_proof_bundle_count += 1
            temporal_proof_bundle_status_counts[element_temporal_proof_bundle_status or "unknown"] = (
                temporal_proof_bundle_status_counts.get(
                    element_temporal_proof_bundle_status or "unknown", 0
                )
                + 1
            )
        if bool(element_theorem_export_metadata.get("chronology_blocked", False)):
            theorem_export_blocked_element_count += 1
        theorem_export_chronology_task_count += int(
            element_theorem_export_metadata.get("chronology_task_count", 0) or 0
        )
        if proof_artifact:
            proof_artifact_element_count += 1
            proof_artifact_status_counts[element_proof_artifact_status or "unknown"] = (
                proof_artifact_status_counts.get(element_proof_artifact_status or "unknown", 0)
                + 1
            )
        if element_proof_artifact_available:
            proof_artifact_available_element_count += 1
        if element_proof_artifact_explanation_steps or element_proof_artifact_explanation_text:
            proof_artifact_explanation_element_count += 1
        for preview_value in (
            element_proof_artifact_proof_id,
            element_proof_artifact_sentence,
            element_proof_artifact_reason,
        ):
            if preview_value and preview_value not in proof_artifact_preview:
                proof_artifact_preview.append(preview_value)
            if len(proof_artifact_preview) >= preview_limit:
                break
        for warning in element_temporal_warnings:
            if warning not in temporal_warning_preview:
                temporal_warning_preview.append(warning)
            if len(temporal_warning_preview) >= preview_limit:
                break
        for relation_preview in element_temporal_relation_preview:
            if relation_preview not in temporal_relation_preview:
                temporal_relation_preview.append(relation_preview)
            if len(temporal_relation_preview) >= preview_limit:
                break
        for relation_type, count in element_temporal_relation_type_counts.items():
            temporal_relation_type_counts[relation_type] = (
                temporal_relation_type_counts.get(relation_type, 0) + int(count or 0)
            )
        if element_formalism and not hybrid_formalism:
            hybrid_formalism = element_formalism
        if element_reasoning_mode and not hybrid_reasoning_mode:
            hybrid_reasoning_mode = element_reasoning_mode
        if element_compiler_bridge_path and not hybrid_compiler_bridge_path:
            hybrid_compiler_bridge_path = element_compiler_bridge_path
        for formula in hybrid_tdfol_formulas:
            if formula not in hybrid_tdfol_formula_preview:
                hybrid_tdfol_formula_preview.append(formula)
            if len(hybrid_tdfol_formula_preview) >= preview_limit:
                break
        for formula in hybrid_dcec_formulas:
            if formula not in hybrid_dcec_formula_preview:
                hybrid_dcec_formula_preview.append(formula)
            if len(hybrid_dcec_formula_preview) >= preview_limit:
                break

        if not (
            used_fallback_ontology
            or unavailable_adapters
            or degraded_adapters
            or str(element.get("validation_status") or "") == "contradicted"
            or hybrid_bridge_used
            or proof_artifact
            or element_temporal_fact_count
            or element_temporal_relation_count
            or element_temporal_issue_count
            or element_temporal_warning_count
            or element_temporal_rule_status in {"partial", "failed"}
        ):
            continue

        flagged_elements.append(
            {
                "element_id": element.get("element_id"),
                "element_text": element.get("element_text"),
                "validation_status": element.get("validation_status", ""),
                "predicate_count": int(reasoning.get("predicate_count", 0) or 0),
                "used_fallback_ontology": used_fallback_ontology,
                "backend_available_count": int(
                    reasoning.get("backend_available_count", 0) or 0
                ),
                "unavailable_adapters": unavailable_adapters,
                "degraded_adapters": degraded_adapters,
                "hybrid_bridge_used": hybrid_bridge_used,
                "hybrid_bridge_available": hybrid_bridge_available,
                "hybrid_tdfol_formula_count": hybrid_tdfol_count,
                "hybrid_dcec_formula_count": hybrid_dcec_count,
                "hybrid_tdfol_formula_preview": element_tdfol_preview,
                "hybrid_dcec_formula_preview": element_dcec_preview,
                "hybrid_formalism": element_formalism,
                "hybrid_reasoning_mode": element_reasoning_mode,
                "hybrid_compiler_bridge_path": element_compiler_bridge_path,
                "proof_artifact_available": element_proof_artifact_available,
                "proof_artifact_status": element_proof_artifact_status,
                "proof_artifact_proof_id": element_proof_artifact_proof_id,
                "proof_artifact_proof_status": element_proof_artifact_proof_status,
                "proof_artifact_sentence": element_proof_artifact_sentence,
                "proof_artifact_reason": element_proof_artifact_reason,
                "proof_artifact_violation_count": element_proof_artifact_violation_count,
                "proof_artifact_explanation_format": element_proof_artifact_explanation_format,
                "proof_artifact_explanation_step_count": len(element_proof_artifact_explanation_steps),
                "proof_artifact_explanation_text": element_proof_artifact_explanation_text,
                "proof_artifact_theorem_export_metadata": element_proof_artifact_theorem_export_metadata,
                "temporal_fact_count": element_temporal_fact_count,
                "temporal_relation_count": element_temporal_relation_count,
                "temporal_issue_count": element_temporal_issue_count,
                "temporal_partial_order_ready": element_temporal_partial_order_ready,
                "temporal_warning_count": element_temporal_warning_count,
                "temporal_warnings": element_temporal_warnings,
                "temporal_relation_type_counts": element_temporal_relation_type_counts,
                "temporal_relation_preview": element_temporal_relation_preview,
                "temporal_rule_profile_id": element_temporal_rule_profile_id,
                "temporal_rule_frame_id": element_temporal_rule_frame_id,
                "temporal_rule_status": element_temporal_rule_status,
                "temporal_rule_blocking_reasons": element_temporal_rule_blocking_reasons,
                "temporal_rule_warnings": element_temporal_rule_warnings,
                "temporal_rule_follow_ups": element_temporal_rule_follow_ups,
                "temporal_proof_bundle_id": element_temporal_proof_bundle_id,
                "temporal_proof_bundle_status": element_temporal_proof_bundle_status,
                "temporal_proof_bundle_fact_ids": element_temporal_proof_bundle_fact_ids,
                "temporal_proof_bundle_relation_ids": element_temporal_proof_bundle_relation_ids,
                "temporal_proof_bundle_issue_ids": element_temporal_proof_bundle_issue_ids,
                "temporal_proof_bundle_tdfol_preview": element_temporal_proof_bundle_tdfol_preview,
                "temporal_proof_bundle_dcec_preview": element_temporal_proof_bundle_dcec_preview,
                "theorem_export_metadata": element_theorem_export_metadata,
            }
        )

    return {
        "claim_type": claim_validation.get("claim_type", ""),
        "total_element_count": len(
            [element for element in elements if isinstance(element, dict)]
        ),
        "flagged_element_count": len(flagged_elements),
        "fallback_ontology_element_count": fallback_ontology_element_count,
        "unavailable_backend_element_count": unavailable_backend_element_count,
        "degraded_adapter_element_count": degraded_adapter_element_count,
        "hybrid_bridge_element_count": hybrid_bridge_element_count,
        "hybrid_bridge_available_element_count": hybrid_bridge_available_element_count,
        "hybrid_tdfol_formula_count": hybrid_tdfol_formula_count,
        "hybrid_dcec_formula_count": hybrid_dcec_formula_count,
        "hybrid_tdfol_formula_preview": hybrid_tdfol_formula_preview,
        "hybrid_dcec_formula_preview": hybrid_dcec_formula_preview,
        "hybrid_formalism": hybrid_formalism,
        "hybrid_reasoning_mode": hybrid_reasoning_mode,
        "hybrid_compiler_bridge_path": hybrid_compiler_bridge_path,
        "temporal_element_count": temporal_element_count,
        "temporal_fact_count": temporal_fact_count,
        "temporal_relation_count": temporal_relation_count,
        "temporal_issue_count": temporal_issue_count,
        "temporal_partial_order_ready_element_count": temporal_partial_order_ready_element_count,
        "temporal_warning_count": temporal_warning_count,
        "temporal_warning_preview": temporal_warning_preview,
        "temporal_relation_type_counts": temporal_relation_type_counts,
        "temporal_relation_preview": temporal_relation_preview,
        "temporal_rule_profile_available_element_count": temporal_rule_profile_available_element_count,
        "temporal_rule_profile_satisfied_element_count": temporal_rule_profile_satisfied_element_count,
        "temporal_rule_profile_partial_element_count": temporal_rule_profile_partial_element_count,
        "temporal_rule_profile_failed_element_count": temporal_rule_profile_failed_element_count,
        "temporal_proof_bundle_count": temporal_proof_bundle_count,
        "temporal_proof_bundle_status_counts": temporal_proof_bundle_status_counts,
        "claim_temporal_issue_count": claim_temporal_issue_count,
        "claim_unresolved_temporal_issue_count": claim_unresolved_temporal_issue_count,
        "claim_resolved_temporal_issue_count": claim_resolved_temporal_issue_count,
        "claim_temporal_issue_status_counts": claim_temporal_issue_status_counts,
        "claim_temporal_issue_ids": claim_temporal_issue_ids,
        "claim_missing_temporal_predicates": claim_missing_temporal_predicates,
        "claim_required_provenance_kinds": claim_required_provenance_kinds,
        "theorem_export_blocked_element_count": theorem_export_blocked_element_count,
        "theorem_export_chronology_task_count": theorem_export_chronology_task_count,
        "proof_artifact_element_count": proof_artifact_element_count,
        "proof_artifact_available_element_count": proof_artifact_available_element_count,
        "proof_artifact_status_counts": proof_artifact_status_counts,
        "proof_artifact_explanation_element_count": proof_artifact_explanation_element_count,
        "proof_artifact_preview": proof_artifact_preview,
        "flagged_elements": flagged_elements,
    }


def summarize_follow_up_history_claim(
    history_entries: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    entries = history_entries if isinstance(history_entries, list) else []
    status_counts: Dict[str, int] = {}
    support_kind_counts: Dict[str, int] = {}
    execution_mode_counts: Dict[str, int] = {}
    query_strategy_counts: Dict[str, int] = {}
    follow_up_focus_counts: Dict[str, int] = {}
    resolution_status_counts: Dict[str, int] = {}
    resolution_applied_counts: Dict[str, int] = {}
    temporal_rule_status_counts: Dict[str, int] = {}
    temporal_rule_blocking_reason_counts: Dict[str, int] = {}
    temporal_resolution_status_counts: Dict[str, int] = {}
    adaptive_query_strategy_counts: Dict[str, int] = {}
    adaptive_retry_reason_counts: Dict[str, int] = {}
    selected_authority_program_type_counts: Dict[str, int] = {}
    selected_authority_program_bias_counts: Dict[str, int] = {}
    selected_authority_program_rule_bias_counts: Dict[str, int] = {}
    source_family_counts: Dict[str, int] = {}
    record_scope_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    adaptive_retry_entry_count = 0
    priority_penalized_entry_count = 0
    zero_result_entry_count = 0
    last_adaptive_retry: Optional[Dict[str, Any]] = None
    fact_targeting_metrics = _aggregate_fact_targeting_metrics(entries)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "unknown")
        support_kind = str(entry.get("support_kind") or "unknown")
        execution_mode = str(entry.get("execution_mode") or "unknown")
        query_strategy = str(entry.get("query_strategy") or "unknown")
        follow_up_focus = str(entry.get("follow_up_focus") or "unknown")
        resolution_status = str(entry.get("resolution_status") or "")
        resolution_applied = str(entry.get("resolution_applied") or "")
        temporal_rule_status = str(entry.get("temporal_rule_status") or "")
        adaptive_retry_applied = bool(entry.get("adaptive_retry_applied", False))
        adaptive_query_strategy = str(entry.get("adaptive_query_strategy") or "")
        adaptive_retry_reason = str(entry.get("adaptive_retry_reason") or "")
        adaptive_priority_penalty = int(entry.get("adaptive_priority_penalty", 0) or 0)
        zero_result = bool(entry.get("zero_result", False))
        selected_search_program_type = str(entry.get("selected_search_program_type") or "")
        selected_search_program_bias = str(entry.get("selected_search_program_bias") or "")
        selected_search_program_rule_bias = str(entry.get("selected_search_program_rule_bias") or "")
        source_family = str(entry.get("source_family") or "")
        record_scope = str(entry.get("record_scope") or "")
        artifact_family = str(entry.get("artifact_family") or "")
        corpus_family = str(entry.get("corpus_family") or "")
        content_origin = str(entry.get("content_origin") or "")

        status_counts[status] = status_counts.get(status, 0) + 1
        support_kind_counts[support_kind] = support_kind_counts.get(support_kind, 0) + 1
        execution_mode_counts[execution_mode] = execution_mode_counts.get(execution_mode, 0) + 1
        query_strategy_counts[query_strategy] = query_strategy_counts.get(query_strategy, 0) + 1
        follow_up_focus_counts[follow_up_focus] = follow_up_focus_counts.get(follow_up_focus, 0) + 1
        if resolution_status:
            resolution_status_counts[resolution_status] = resolution_status_counts.get(resolution_status, 0) + 1
        if resolution_applied:
            resolution_applied_counts[resolution_applied] = (
                resolution_applied_counts.get(resolution_applied, 0) + 1
            )
        if temporal_rule_status:
            temporal_rule_status_counts[temporal_rule_status] = (
                temporal_rule_status_counts.get(temporal_rule_status, 0) + 1
            )
        for reason in (entry.get("temporal_rule_blocking_reasons") or []):
            normalized_reason = str(reason or "").strip()
            if not normalized_reason:
                continue
            temporal_rule_blocking_reason_counts[normalized_reason] = (
                temporal_rule_blocking_reason_counts.get(normalized_reason, 0) + 1
            )
        if follow_up_focus == "temporal_gap_closure" and resolution_status:
            temporal_resolution_status_counts[resolution_status] = (
                temporal_resolution_status_counts.get(resolution_status, 0) + 1
            )
        if adaptive_retry_applied:
            adaptive_retry_entry_count += 1
        if adaptive_priority_penalty > 0:
            priority_penalized_entry_count += 1
        if adaptive_query_strategy:
            adaptive_query_strategy_counts[adaptive_query_strategy] = (
                adaptive_query_strategy_counts.get(adaptive_query_strategy, 0) + 1
            )
        if adaptive_retry_reason:
            adaptive_retry_reason_counts[adaptive_retry_reason] = (
                adaptive_retry_reason_counts.get(adaptive_retry_reason, 0) + 1
            )
        if selected_search_program_type:
            selected_authority_program_type_counts[selected_search_program_type] = (
                selected_authority_program_type_counts.get(selected_search_program_type, 0) + 1
            )
        if selected_search_program_bias:
            selected_authority_program_bias_counts[selected_search_program_bias] = (
                selected_authority_program_bias_counts.get(selected_search_program_bias, 0) + 1
            )
        if selected_search_program_rule_bias:
            selected_authority_program_rule_bias_counts[selected_search_program_rule_bias] = (
                selected_authority_program_rule_bias_counts.get(selected_search_program_rule_bias, 0) + 1
            )
        if source_family:
            source_family_counts[source_family] = source_family_counts.get(source_family, 0) + 1
        if record_scope:
            record_scope_counts[record_scope] = record_scope_counts.get(record_scope, 0) + 1
        if artifact_family:
            artifact_family_counts[artifact_family] = artifact_family_counts.get(artifact_family, 0) + 1
        if corpus_family:
            corpus_family_counts[corpus_family] = corpus_family_counts.get(corpus_family, 0) + 1
        if content_origin:
            content_origin_counts[content_origin] = content_origin_counts.get(content_origin, 0) + 1
        if zero_result:
            zero_result_entry_count += 1
        if adaptive_retry_applied:
            last_adaptive_retry = _select_last_adaptive_retry(
                last_adaptive_retry,
                timestamp=entry.get("timestamp"),
                claim_element_id=entry.get("claim_element_id"),
                claim_element_text=entry.get("claim_element_text"),
                adaptive_query_strategy=adaptive_query_strategy,
                reason=adaptive_retry_reason,
            )

    return {
        "total_entry_count": len([entry for entry in entries if isinstance(entry, dict)]),
        "status_counts": status_counts,
        "support_kind_counts": support_kind_counts,
        "execution_mode_counts": execution_mode_counts,
        "query_strategy_counts": query_strategy_counts,
        "follow_up_focus_counts": follow_up_focus_counts,
        "resolution_status_counts": resolution_status_counts,
        "resolution_applied_counts": resolution_applied_counts,
        "temporal_gap_task_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and entry.get("follow_up_focus") == "temporal_gap_closure"
            ]
        ),
        "temporal_gap_targeted_task_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and entry.get("query_strategy") == "temporal_gap_targeted"
            ]
        ),
        "temporal_rule_status_counts": temporal_rule_status_counts,
        "temporal_rule_blocking_reason_counts": temporal_rule_blocking_reason_counts,
        "temporal_resolution_status_counts": temporal_resolution_status_counts,
        "adaptive_retry_entry_count": adaptive_retry_entry_count,
        "priority_penalized_entry_count": priority_penalized_entry_count,
        "adaptive_query_strategy_counts": adaptive_query_strategy_counts,
        "adaptive_retry_reason_counts": adaptive_retry_reason_counts,
        "selected_authority_program_type_counts": selected_authority_program_type_counts,
        "selected_authority_program_bias_counts": selected_authority_program_bias_counts,
        "selected_authority_program_rule_bias_counts": selected_authority_program_rule_bias_counts,
        "source_family_counts": source_family_counts,
        "record_scope_counts": record_scope_counts,
        "artifact_family_counts": artifact_family_counts,
        "corpus_family_counts": corpus_family_counts,
        "content_origin_counts": content_origin_counts,
        "primary_missing_fact_counts": fact_targeting_metrics["primary_missing_fact_counts"],
        "missing_fact_bundle_counts": fact_targeting_metrics["missing_fact_bundle_counts"],
        "satisfied_fact_bundle_counts": fact_targeting_metrics["satisfied_fact_bundle_counts"],
        "zero_result_entry_count": zero_result_entry_count,
        "last_adaptive_retry": last_adaptive_retry,
        "manual_review_entry_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict) and entry.get("support_kind") == "manual_review"
            ]
        ),
        "resolved_entry_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and (
                    entry.get("status") == "resolved_manual_review"
                    or bool(entry.get("resolution_status"))
                )
            ]
        ),
        "contradiction_related_entry_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and (
                    entry.get("follow_up_focus") == "contradiction_resolution"
                    or entry.get("validation_status") == "contradicted"
                )
            ]
        ),
        "latest_attempted_at": (
            entries[0].get("timestamp")
            if entries and isinstance(entries[0], dict)
            else None
        ),
    }


def summarize_claim_testimony_claim(
    records: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    normalized_records = [record for record in (records or []) if isinstance(record, dict)]
    firsthand_status_counts: Dict[str, int] = {}
    confidence_bucket_counts: Dict[str, int] = {}
    linked_element_ids = set()

    for record in normalized_records:
        firsthand_status = str(record.get("firsthand_status") or "unknown")
        firsthand_status_counts[firsthand_status] = firsthand_status_counts.get(firsthand_status, 0) + 1
        claim_element_id = str(record.get("claim_element_id") or "")
        if claim_element_id:
            linked_element_ids.add(claim_element_id)
        confidence_value = record.get("source_confidence")
        if confidence_value is None:
            bucket = "unknown"
        else:
            try:
                numeric_confidence = float(confidence_value)
            except (TypeError, ValueError):
                bucket = "unknown"
            else:
                if numeric_confidence >= 0.75:
                    bucket = "high"
                elif numeric_confidence >= 0.4:
                    bucket = "medium"
                else:
                    bucket = "low"
        confidence_bucket_counts[bucket] = confidence_bucket_counts.get(bucket, 0) + 1

    return {
        "record_count": len(normalized_records),
        "linked_element_count": len(linked_element_ids),
        "firsthand_status_counts": firsthand_status_counts,
        "confidence_bucket_counts": confidence_bucket_counts,
        "latest_timestamp": str(normalized_records[0].get("timestamp") or "") if normalized_records else "",
    }


def _attach_testimony_to_claim_matrix(
    claim_matrix: Dict[str, Any],
    testimony_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(claim_matrix, dict):
        return claim_matrix

    normalized_records = [record for record in (testimony_records or []) if isinstance(record, dict)]
    for element in claim_matrix.get("elements", []) or []:
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("element_id") or "")
        element_text = str(element.get("element_text") or "")
        matching_records = []
        for record in normalized_records:
            record_element_id = str(record.get("claim_element_id") or "")
            record_element_text = str(record.get("claim_element_text") or "")
            if record_element_id and record_element_id == element_id:
                matching_records.append(record)
                continue
            if element_text and record_element_text and record_element_text == element_text:
                matching_records.append(record)
        element["testimony_records"] = matching_records
        element["testimony_record_count"] = len(matching_records)

    claim_matrix["testimony_record_count"] = len(normalized_records)
    return claim_matrix


def summarize_claim_document_artifacts_claim(
    document_records: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    normalized_records = [record for record in (document_records or []) if isinstance(record, dict)]
    parse_status_counts: Dict[str, int] = {}
    quality_tier_counts: Dict[str, int] = {}
    graph_status_counts: Dict[str, int] = {}
    linked_element_ids = set()
    total_chunks = 0
    total_facts = 0
    low_quality_count = 0
    graph_ready_count = 0

    for record in normalized_records:
        parse_status = str(record.get("parse_status") or "unknown")
        parse_status_counts[parse_status] = parse_status_counts.get(parse_status, 0) + 1

        parse_metadata = record.get("parse_metadata", {}) if isinstance(record.get("parse_metadata"), dict) else {}
        quality_tier = str(parse_metadata.get("quality_tier") or "unknown")
        quality_tier_counts[quality_tier] = quality_tier_counts.get(quality_tier, 0) + 1
        if quality_tier in {"low", "empty"}:
            low_quality_count += 1

        graph_status = str(record.get("graph_status") or "unknown")
        graph_status_counts[graph_status] = graph_status_counts.get(graph_status, 0) + 1
        if graph_status in {"ready", "available"}:
            graph_ready_count += 1

        claim_element_id = str(record.get("claim_element_id") or "")
        if claim_element_id:
            linked_element_ids.add(claim_element_id)

        total_chunks += int(record.get("chunk_count", 0) or 0)
        total_facts += int(record.get("fact_count", 0) or 0)

    return {
        "record_count": len(normalized_records),
        "linked_element_count": len(linked_element_ids),
        "total_chunk_count": total_chunks,
        "total_fact_count": total_facts,
        "low_quality_record_count": low_quality_count,
        "graph_ready_record_count": graph_ready_count,
        "parse_status_counts": parse_status_counts,
        "quality_tier_counts": quality_tier_counts,
        "graph_status_counts": graph_status_counts,
        "latest_timestamp": str(normalized_records[0].get("timestamp") or "") if normalized_records else "",
    }


def _build_document_fact_previews(
    facts: Any,
    *,
    preview_fact_limit: int,
) -> List[Dict[str, Any]]:
    if not isinstance(facts, list):
        return []

    previews: List[Dict[str, Any]] = []
    for fact in facts[:preview_fact_limit]:
        if not isinstance(fact, dict):
            continue
        metadata = fact.get("metadata", {}) if isinstance(fact.get("metadata"), dict) else {}
        provenance = fact.get("provenance", {}) if isinstance(fact.get("provenance"), dict) else {}
        parse_lineage = (
            metadata.get("parse_lineage", {})
            if isinstance(metadata.get("parse_lineage"), dict)
            else {}
        )
        provenance_metadata = (
            provenance.get("metadata", {})
            if isinstance(provenance.get("metadata"), dict)
            else {}
        )
        source_chunk_ids = fact.get("source_chunk_ids")
        if not isinstance(source_chunk_ids, list):
            source_chunk_ids = provenance_metadata.get("source_chunks")
        if not isinstance(source_chunk_ids, list):
            source_chunk_ids = []

        previews.append(
            {
                "fact_id": str(fact.get("fact_id") or ""),
                "text": str(fact.get("text") or ""),
                "confidence": fact.get("confidence"),
                "quality_tier": str(
                    fact.get("quality_tier")
                    or parse_lineage.get("quality_tier")
                    or ""
                ),
                "source_ref": str(fact.get("source_ref") or fact.get("source_artifact_id") or ""),
                "source_chunk_ids": [str(chunk_id) for chunk_id in source_chunk_ids if chunk_id],
            }
        )
    return previews


def _build_document_graph_preview(
    graph_payload: Any,
    *,
    preview_graph_limit: int,
) -> Dict[str, Any]:
    if not isinstance(graph_payload, dict):
        return {
            "status": "unknown",
            "entity_count": 0,
            "relationship_count": 0,
            "entities": [],
            "relationships": [],
        }

    entities = graph_payload.get("entities", [])
    if not isinstance(entities, list):
        entities = []
    relationships = graph_payload.get("relationships", [])
    if not isinstance(relationships, list):
        relationships = []

    return {
        "status": str(graph_payload.get("status") or "unknown"),
        "entity_count": len([entity for entity in entities if isinstance(entity, dict)]),
        "relationship_count": len(
            [relationship for relationship in relationships if isinstance(relationship, dict)]
        ),
        "entities": [
            {
                "id": str(entity.get("id") or ""),
                "type": str(entity.get("type") or ""),
                "name": str(entity.get("name") or ""),
                "confidence": entity.get("confidence"),
            }
            for entity in entities[:preview_graph_limit]
            if isinstance(entity, dict)
        ],
        "relationships": [
            {
                "id": str(relationship.get("id") or ""),
                "source_id": str(relationship.get("source_id") or ""),
                "target_id": str(relationship.get("target_id") or ""),
                "relation_type": str(relationship.get("relation_type") or ""),
                "confidence": relationship.get("confidence"),
            }
            for relationship in relationships[:preview_graph_limit]
            if isinstance(relationship, dict)
        ],
    }


def _build_support_fact_preview(fact: Any) -> Dict[str, Any]:
    payload = fact if isinstance(fact, dict) else {}
    return {
        "fact_id": str(payload.get("fact_id") or ""),
        "text": str(payload.get("fact_text") or payload.get("text") or ""),
        "support_kind": str(payload.get("support_kind") or ""),
        "source_table": str(payload.get("source_table") or ""),
        "source_family": str(payload.get("source_family") or ""),
        "source_ref": str(payload.get("source_ref") or payload.get("support_ref") or ""),
        "record_scope": str(payload.get("record_scope") or ""),
        "artifact_family": str(payload.get("artifact_family") or ""),
        "corpus_family": str(payload.get("corpus_family") or ""),
        "content_origin": str(payload.get("content_origin") or ""),
        "quality_tier": str(payload.get("quality_tier") or ""),
        "quality_score": float(payload.get("quality_score", 0.0) or 0.0),
        "confidence": payload.get("confidence"),
        "record_id": payload.get("record_id") or payload.get("source_record_id"),
    }


def _classify_fact_proof_status(
    fact: Dict[str, Any],
    *,
    validation_status: str,
    decision_source: str,
    contradiction_fact_ids: set[str],
) -> str:
    fact_id = str(fact.get("fact_id") or "")
    if fact_id and fact_id in contradiction_fact_ids:
        return "contradicting"

    if validation_status == "supported" and decision_source in {
        "logic_proof_supported",
        "ontology_validation_supported",
        "covered_support",
    }:
        return "supporting"

    if validation_status == "missing":
        return "unresolved"

    if validation_status == "contradicted":
        return "unresolved"

    if decision_source in {
        "partial_support",
        "logic_proof_partial",
        "logic_unprovable",
        "ontology_validation_failed",
        "low_quality_parse",
        "missing_support",
    }:
        return "unresolved"

    if validation_status == "supported":
        return "supporting"

    return "unresolved"


def _summarize_fact_proof_statuses(facts: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        "supporting": 0,
        "contradicting": 0,
        "unresolved": 0,
    }
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        status = str(fact.get("proof_status") or "unresolved")
        if status not in counts:
            counts[status] = 0
        counts[status] += 1
    return counts


def _build_contradiction_pair_payloads(
    support_facts: List[Dict[str, Any]],
    contradiction_candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    fact_by_id = {
        str(fact.get("fact_id") or ""): fact
        for fact in support_facts
        if isinstance(fact, dict) and str(fact.get("fact_id") or "")
    }
    pairs: List[Dict[str, Any]] = []

    for index, candidate in enumerate(contradiction_candidates):
        if not isinstance(candidate, dict):
            continue
        fact_ids = [str(fact_id) for fact_id in (candidate.get("fact_ids") or []) if fact_id]
        paired_facts = [fact_by_id[fact_id] for fact_id in fact_ids if fact_id in fact_by_id]
        left_fact = paired_facts[0] if paired_facts else None
        right_fact = paired_facts[1] if len(paired_facts) > 1 else None
        left_fact_text = str((left_fact or {}).get("text") or "").strip()
        right_fact_text = str((right_fact or {}).get("text") or "").strip()
        overlap_terms = [str(term) for term in (candidate.get("overlap_terms") or []) if term]

        resolution_prompt = "Which version of this proposition is accurate, and what testimony or document best confirms it?"
        if left_fact_text and right_fact_text:
            resolution_prompt = (
                f"These two propositions conflict for this element. Which version is accurate: \"{left_fact_text}\" "
                f"or \"{right_fact_text}\"?"
            )

        pairs.append(
            {
                "pair_id": f"contradiction-pair:{index}",
                "fact_ids": fact_ids,
                "overlap_terms": overlap_terms,
                "left_fact": left_fact,
                "right_fact": right_fact,
                "paired_fact_count": len(paired_facts),
                "resolution_prompt": resolution_prompt,
            }
        )

    return pairs


def _attach_validation_to_claim_matrix(
    mediator: Any,
    user_id: str,
    claim_type: str,
    claim_matrix: Dict[str, Any],
    validation_claim: Dict[str, Any],
    document_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(claim_matrix, dict):
        return claim_matrix

    validation_elements = (
        validation_claim.get("elements", [])
        if isinstance(validation_claim, dict) and isinstance(validation_claim.get("elements"), list)
        else []
    )
    validation_by_key: Dict[str, Dict[str, Any]] = {}
    for validation_element in validation_elements:
        if not isinstance(validation_element, dict):
            continue
        element_id = str(validation_element.get("element_id") or "")
        element_text = str(validation_element.get("element_text") or "")
        if element_id:
            validation_by_key[element_id] = validation_element
        if element_text:
            validation_by_key.setdefault(element_text, validation_element)

    get_claim_support_facts = getattr(mediator, "get_claim_support_facts", None)

    for element in claim_matrix.get("elements", []) or []:
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("element_id") or "")
        element_text = str(element.get("element_text") or "")
        validation_element = validation_by_key.get(element_id) or validation_by_key.get(element_text) or {}
        contradiction_candidates = (
            validation_element.get("contradiction_candidates", [])
            if isinstance(validation_element.get("contradiction_candidates"), list)
            else []
        )
        contradiction_fact_ids: set[str] = {
            str(fact_id)
            for candidate in contradiction_candidates
            if isinstance(candidate, dict)
            for fact_id in (candidate.get("fact_ids") or [])
            if fact_id
        }
        validation_status = str(validation_element.get("validation_status") or "")
        decision_source = str(
            ((validation_element.get("proof_decision_trace") or {}).get("decision_source") or "")
        )

        support_fact_packets: List[Dict[str, Any]] = []
        if callable(get_claim_support_facts):
            support_fact_packets = [
                _build_support_fact_preview(fact)
                for fact in get_claim_support_facts(
                    user_id=user_id,
                    claim_type=claim_type,
                    claim_element_id=element_id or None,
                    claim_element_text=element_text or None,
                )
                if isinstance(fact, dict)
            ]
        support_fact_packets = [
            {
                **fact,
                "proof_status": _classify_fact_proof_status(
                    fact,
                    validation_status=validation_status,
                    decision_source=decision_source,
                    contradiction_fact_ids=contradiction_fact_ids,
                ),
            }
            for fact in support_fact_packets
        ]

        document_record_keys = {
            str(record.get("cid") or "")
            for record in document_records
            if isinstance(record, dict) and str(record.get("cid") or "")
        }
        document_record_ids = {
            str(record.get("record_id"))
            for record in document_records
            if isinstance(record, dict) and record.get("record_id") is not None
        }
        document_fact_packets = [
            fact
            for fact in support_fact_packets
            if (
                fact.get("source_table") == "evidence"
                or fact.get("source_family") == "evidence"
                or str(fact.get("source_ref") or "") in document_record_keys
                or str(fact.get("record_id") or "") in document_record_ids
            )
        ]
        support_fact_status_counts = _summarize_fact_proof_statuses(support_fact_packets)
        document_fact_status_counts = _summarize_fact_proof_statuses(document_fact_packets)
        contradiction_pairs = _build_contradiction_pair_payloads(
            support_fact_packets,
            contradiction_candidates,
        )

        element["validation_status"] = validation_status
        element["recommended_action"] = str(validation_element.get("recommended_action") or "")
        element["proof_gap_count"] = int(validation_element.get("proof_gap_count", 0) or 0)
        element["proof_gaps"] = list(validation_element.get("proof_gaps", []) or [])
        element["proof_decision_trace"] = dict(validation_element.get("proof_decision_trace", {}) or {})
        element["proof_diagnostics"] = dict(validation_element.get("proof_diagnostics", {}) or {})
        element["contradiction_candidate_count"] = int(
            validation_element.get("contradiction_candidate_count", 0) or 0
        )
        element["support_fact_packets"] = support_fact_packets
        element["support_fact_packet_count"] = len(support_fact_packets)
        element["support_fact_status_counts"] = support_fact_status_counts
        element["document_fact_packets"] = document_fact_packets
        element["document_fact_packet_count"] = len(document_fact_packets)
        element["document_fact_status_counts"] = document_fact_status_counts
        element["contradiction_pairs"] = contradiction_pairs
        element["contradiction_pair_count"] = len(contradiction_pairs)

    return claim_matrix


def _attach_documents_to_claim_matrix(
    claim_matrix: Dict[str, Any],
    document_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(claim_matrix, dict):
        return claim_matrix

    normalized_records = [record for record in (document_records or []) if isinstance(record, dict)]
    for element in claim_matrix.get("elements", []) or []:
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("element_id") or "")
        element_text = str(element.get("element_text") or "")
        matching_records = []
        for record in normalized_records:
            record_element_id = str(record.get("claim_element_id") or "")
            record_element_text = str(record.get("claim_element_text") or "")
            if record_element_id and record_element_id == element_id:
                matching_records.append(record)
                continue
            if element_text and record_element_text and record_element_text == element_text:
                matching_records.append(record)
        element["document_records"] = matching_records
        element["document_record_count"] = len(matching_records)
        element["document_fact_count"] = sum(
            int(record.get("fact_count", 0) or 0)
            for record in matching_records
            if isinstance(record, dict)
        )

    claim_matrix["document_record_count"] = len(normalized_records)
    claim_matrix["document_fact_count"] = sum(
        int(record.get("fact_count", 0) or 0)
        for record in normalized_records
        if isinstance(record, dict)
    )
    return claim_matrix


def _collect_claim_document_records(
    mediator: Any,
    user_id: str,
    claim_type: Optional[str] = None,
    *,
    limit: int = 25,
    preview_chunk_limit: int = 3,
    preview_fact_limit: int = 5,
    preview_graph_limit: int = 5,
) -> Dict[str, List[Dict[str, Any]]]:
    get_user_evidence = getattr(mediator, "get_user_evidence", None)
    if not callable(get_user_evidence):
        return {}

    evidence_records = get_user_evidence(user_id=user_id)
    if not isinstance(evidence_records, list):
        return {}

    get_evidence_chunks = getattr(mediator, "get_evidence_chunks", None)
    get_evidence_facts = getattr(mediator, "get_evidence_facts", None)
    get_evidence_graph = getattr(mediator, "get_evidence_graph", None)
    filtered_records = []
    for record in evidence_records:
        if not isinstance(record, dict):
            continue
        record_claim_type = str(record.get("claim_type") or "")
        if claim_type and record_claim_type != claim_type:
            continue
        filtered_records.append(record)
        if len(filtered_records) >= limit:
            break

    claim_entries: Dict[str, List[Dict[str, Any]]] = {}
    for record in filtered_records:
        record_id = record.get("id")
        chunk_previews: List[Dict[str, Any]] = []
        fact_previews: List[Dict[str, Any]] = []
        graph_preview: Dict[str, Any] = {
            "status": str(record.get("graph_status") or "unknown"),
            "entity_count": int(record.get("graph_entity_count", 0) or 0),
            "relationship_count": int(record.get("graph_relationship_count", 0) or 0),
            "entities": [],
            "relationships": [],
        }
        if callable(get_evidence_chunks) and record_id is not None:
            chunks = get_evidence_chunks(int(record_id))
            if isinstance(chunks, list):
                chunk_previews = [
                    chunk for chunk in chunks[:preview_chunk_limit] if isinstance(chunk, dict)
                ]
        if callable(get_evidence_facts) and record_id is not None:
            facts = get_evidence_facts(int(record_id))
            fact_previews = _build_document_fact_previews(
                facts,
                preview_fact_limit=preview_fact_limit,
            )
        if callable(get_evidence_graph) and record_id is not None:
            graph_preview = _build_document_graph_preview(
                get_evidence_graph(int(record_id)),
                preview_graph_limit=preview_graph_limit,
            )

        entry = {
            "record_id": record_id,
            "cid": record.get("cid"),
            "evidence_type": record.get("type"),
            "claim_type": record.get("claim_type"),
            "claim_element_id": record.get("claim_element_id"),
            "claim_element_text": record.get("claim_element"),
            "description": record.get("description"),
            "timestamp": record.get("timestamp"),
            "source_url": record.get("source_url"),
            "filename": (record.get("metadata") or {}).get("filename") if isinstance(record.get("metadata"), dict) else "",
            "mime_type": (
                ((record.get("metadata") or {}).get("mime_type"))
                if isinstance(record.get("metadata"), dict)
                else ""
            ) or str((record.get("parse_metadata") or {}).get("mime_type") or ""),
            "parse_status": record.get("parse_status"),
            "chunk_count": int(record.get("chunk_count", 0) or 0),
            "fact_count": int(record.get("fact_count", 0) or 0),
            "parsed_text_preview": record.get("parsed_text_preview") or "",
            "parse_metadata": dict(record.get("parse_metadata") or {}),
            "graph_status": record.get("graph_status"),
            "graph_entity_count": int(record.get("graph_entity_count", 0) or 0),
            "graph_relationship_count": int(record.get("graph_relationship_count", 0) or 0),
            "chunk_previews": chunk_previews,
            "fact_previews": fact_previews,
            "graph_preview": graph_preview,
        }
        current_claim = str(record.get("claim_type") or "")
        claim_entries.setdefault(current_claim, []).append(entry)

    return claim_entries


def _build_claim_question_recommendations(
    claim_name: str,
    gap_claim: Optional[Dict[str, Any]],
    contradiction_claim: Optional[Dict[str, Any]],
    claim_matrix: Optional[Dict[str, Any]] = None,
    *,
    max_questions: int = 6,
) -> List[Dict[str, Any]]:
    denoiser = ComplaintDenoiser()
    recommendations = denoiser.generate_review_question_recommendations(
        claim_name,
        gap_claim=gap_claim if isinstance(gap_claim, dict) else {},
        contradiction_claim=contradiction_claim if isinstance(contradiction_claim, dict) else {},
        max_questions=max_questions,
    )
    return _augment_question_recommendations_with_fact_prompts(
        claim_name,
        recommendations,
        claim_matrix,
        max_questions=max_questions,
    )


def _augment_question_recommendations_with_fact_prompts(
    claim_name: str,
    recommendations: List[Dict[str, Any]],
    claim_matrix: Optional[Dict[str, Any]],
    *,
    max_questions: int,
) -> List[Dict[str, Any]]:
    if not isinstance(claim_matrix, dict):
        return recommendations[:max_questions]

    denoiser = ComplaintDenoiser()
    augmented = list(recommendations or [])
    seen_keys = {
        str(item.get("suppression_key") or "")
        for item in augmented
        if isinstance(item, dict) and item.get("suppression_key")
    }
    added: List[Dict[str, Any]] = []

    for element in claim_matrix.get("elements", []) or []:
        if not isinstance(element, dict):
            continue
        validation_status = str(element.get("validation_status") or element.get("status") or "missing")
        element_id = str(element.get("element_id") or "")
        element_text = str(element.get("element_text") or element_id or "this element")
        missing_support_kinds = [
            str(kind) for kind in (element.get("missing_support_kinds", []) or []) if kind
        ]

        candidate_packets = []
        for packet in element.get("document_fact_packets", []) or []:
            if isinstance(packet, dict) and str(packet.get("proof_status") or "") in {"contradicting", "unresolved"}:
                candidate_packets.append(packet)
        for packet in element.get("support_fact_packets", []) or []:
            if not isinstance(packet, dict):
                continue
            if str(packet.get("proof_status") or "") not in {"contradicting", "unresolved"}:
                continue
            packet_id = str(packet.get("fact_id") or "")
            if packet_id and any(str(existing.get("fact_id") or "") == packet_id for existing in candidate_packets if isinstance(existing, dict)):
                continue
            candidate_packets.append(packet)

        for packet in candidate_packets:
            proof_status = str(packet.get("proof_status") or "unresolved")
            fact_id = str(packet.get("fact_id") or "")
            fact_text = str(packet.get("text") or "").strip()
            fact_snippet = " ".join(fact_text.split())
            if len(fact_snippet) > 160:
                fact_snippet = fact_snippet[:157] + "..."

            if proof_status == "contradicting":
                lane = "contradiction_resolution"
                question_text = (
                    f"The proposition for {element_text} appears conflicted. Which version of this fact is correct, "
                    "and what testimony or document best confirms it?"
                )
                question_reason = (
                    f"Resolve the contradicting proposition before relying on it for {element_text}."
                )
                expected_proof_gain = "high"
            else:
                lane = "document_request" if packet.get("source_table") == "evidence" else "testimony"
                question_text = (
                    f"What additional detail, document, or testimony would confirm this proposition for {element_text}?"
                )
                question_reason = (
                    f"This proposition is still unresolved for {element_text} and needs clearer support before legal proof review."
                )
                expected_proof_gain = "high" if validation_status in {"missing", "incomplete"} else "medium"

            recommendation = denoiser._build_review_question_recommendation(
                claim_type=claim_name,
                lane=lane,
                target_claim_element_id=element_id,
                target_claim_element_text=element_text,
                question_text=question_text,
                question_reason=question_reason,
                expected_proof_gain=expected_proof_gain,
                supporting_evidence_summary=(
                    f"Fact packet: {fact_id or 'unspecified'}"
                    + (f"; {fact_snippet}" if fact_snippet else "")
                ),
                current_status=validation_status,
                missing_support_kinds=missing_support_kinds,
                contradiction_fact_ids=[fact_id] if proof_status == "contradicting" and fact_id else [],
            )
            recommendation["source_fact_ids"] = [fact_id] if fact_id else []
            recommendation["source_fact_text"] = fact_snippet
            recommendation["source_fact_status"] = proof_status
            recommendation["source_fact_table"] = str(packet.get("source_table") or "")

            suppression_key = str(recommendation.get("suppression_key") or "")
            if suppression_key and suppression_key in seen_keys:
                continue
            if suppression_key:
                seen_keys.add(suppression_key)
            added.append(recommendation)
            if len(augmented) + len(added) >= max_questions:
                return (added + augmented)[:max_questions]

    return (added + augmented)[:max_questions]


def _summarize_claim_coverage_claim(
    claim_type: str,
    coverage_claim: Dict[str, Any],
    overview_claim: Dict[str, Any],
    gap_claim: Dict[str, Any],
    contradiction_claim: Dict[str, Any],
    validation_claim: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    validation_claim = validation_claim if isinstance(validation_claim, dict) else {}
    support_trace_summary = (
        coverage_claim.get("support_trace_summary", {})
        if isinstance(coverage_claim.get("support_trace_summary"), dict)
        else {}
    )
    reasoning_summary = (
        (validation_claim.get("proof_diagnostics") or {}).get("reasoning", {})
        if isinstance(validation_claim.get("proof_diagnostics"), dict)
        else {}
    )
    decision_summary = (
        (validation_claim.get("proof_diagnostics") or {}).get("decision", {})
        if isinstance(validation_claim.get("proof_diagnostics"), dict)
        else {}
    )
    validation_elements = (
        validation_claim.get("elements", [])
        if isinstance(validation_claim.get("elements"), list)
        else []
    )
    missing_elements = []
    partially_supported_elements = []

    if isinstance(overview_claim, dict):
        missing_elements = [
            element.get("element_text")
            for element in overview_claim.get("missing", [])
            if isinstance(element, dict) and element.get("element_text")
        ]
        partially_supported_elements = [
            element.get("element_text")
            for element in overview_claim.get("partially_supported", [])
            if isinstance(element, dict) and element.get("element_text")
        ]

    unresolved_elements = []
    recommended_gap_actions: Dict[str, int] = {}
    if isinstance(gap_claim, dict):
        for element in gap_claim.get("unresolved_elements", []):
            if not isinstance(element, dict):
                continue
            element_text = element.get("element_text")
            if element_text:
                unresolved_elements.append(element_text)
            action = str(element.get("recommended_action") or "unspecified")
            recommended_gap_actions[action] = recommended_gap_actions.get(action, 0) + 1

    contradicted_elements = []
    contradiction_candidate_count = 0
    seen_contradicted_elements = set()
    if isinstance(contradiction_claim, dict):
        contradiction_candidate_count = int(
            contradiction_claim.get("candidate_count", 0) or 0
        )
        for candidate in contradiction_claim.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            element_text = candidate.get("claim_element_text")
            if element_text and element_text not in seen_contradicted_elements:
                seen_contradicted_elements.add(element_text)
                contradicted_elements.append(element_text)

    traced_link_count = 0
    snapshot_created_count = 0
    snapshot_reused_count = 0
    source_table_counts: Dict[str, int] = {}
    graph_status_counts: Dict[str, int] = {}
    graph_id_count = 0
    seen_graph_ids = set()

    for element in coverage_claim.get("elements", []):
        if not isinstance(element, dict):
            continue
        for link in element.get("links", []):
            if not isinstance(link, dict):
                continue
            graph_trace = link.get("graph_trace", {})
            if not isinstance(graph_trace, dict) or not graph_trace:
                continue
            traced_link_count += 1

            source_table = str(graph_trace.get("source_table") or "unknown")
            source_table_counts[source_table] = source_table_counts.get(source_table, 0) + 1

            summary = graph_trace.get("summary", {})
            if isinstance(summary, dict):
                graph_status = str(summary.get("status") or "unknown")
                graph_status_counts[graph_status] = graph_status_counts.get(graph_status, 0) + 1

            snapshot = graph_trace.get("snapshot", {})
            if isinstance(snapshot, dict):
                if bool(snapshot.get("created")):
                    snapshot_created_count += 1
                if bool(snapshot.get("reused")):
                    snapshot_reused_count += 1
                graph_id = str(snapshot.get("graph_id") or "")
                if graph_id and graph_id not in seen_graph_ids:
                    seen_graph_ids.add(graph_id)
                    graph_id_count += 1

    parse_quality_tier_counts = (
        support_trace_summary.get("parse_quality_tier_counts", {})
        if isinstance(support_trace_summary.get("parse_quality_tier_counts"), dict)
        else {}
    )
    low_quality_parsed_record_count = int(parse_quality_tier_counts.get("low", 0) or 0) + int(
        parse_quality_tier_counts.get("empty", 0) or 0
    )
    parse_quality_issue_elements = []
    seen_parse_quality_issue_elements = set()
    for element in validation_elements:
        if not isinstance(element, dict):
            continue
        action = str(element.get("recommended_action") or "")
        decision_source = str(
            ((element.get("proof_decision_trace") or {}).get("decision_source") or "")
        )
        if action != "improve_parse_quality" and decision_source != "low_quality_parse":
            continue
        element_text = str(element.get("element_text") or "").strip()
        if element_text and element_text not in seen_parse_quality_issue_elements:
            seen_parse_quality_issue_elements.add(element_text)
            parse_quality_issue_elements.append(element_text)

    return {
        "claim_type": claim_type,
        "validation_status": validation_claim.get("validation_status", ""),
        "validation_status_counts": validation_claim.get("validation_status_counts", {}),
        "proof_gap_count": int(validation_claim.get("proof_gap_count", 0) or 0),
        "elements_requiring_follow_up": validation_claim.get(
            "elements_requiring_follow_up", []
        ),
        "reasoning_adapter_status_counts": reasoning_summary.get(
            "adapter_status_counts", {}
        ),
        "reasoning_backend_available_count": int(
            reasoning_summary.get("backend_available_count", 0) or 0
        ),
        "reasoning_predicate_count": int(
            reasoning_summary.get("predicate_count", 0) or 0
        ),
        "reasoning_ontology_entity_count": int(
            reasoning_summary.get("ontology_entity_count", 0) or 0
        ),
        "reasoning_ontology_relationship_count": int(
            reasoning_summary.get("ontology_relationship_count", 0) or 0
        ),
        "reasoning_fallback_ontology_count": int(
            reasoning_summary.get("fallback_ontology_count", 0) or 0
        ),
        "reasoning_hybrid_bridge_available_count": int(
            reasoning_summary.get("hybrid_bridge_available_count", 0) or 0
        ),
        "reasoning_hybrid_tdfol_formula_count": int(
            reasoning_summary.get("hybrid_tdfol_formula_count", 0) or 0
        ),
        "reasoning_hybrid_dcec_formula_count": int(
            reasoning_summary.get("hybrid_dcec_formula_count", 0) or 0
        ),
        "reasoning_temporal_fact_count": int(
            reasoning_summary.get("temporal_fact_count", 0) or 0
        ),
        "reasoning_temporal_relation_count": int(
            reasoning_summary.get("temporal_relation_count", 0) or 0
        ),
        "reasoning_temporal_issue_count": int(
            reasoning_summary.get("temporal_issue_count", 0) or 0
        ),
        "reasoning_temporal_partial_order_ready_count": int(
            reasoning_summary.get("temporal_partial_order_ready_count", 0) or 0
        ),
        "reasoning_temporal_warning_count": int(
            reasoning_summary.get("temporal_warning_count", 0) or 0
        ),
        "decision_source_counts": decision_summary.get("decision_source_counts", {}),
        "adapter_contradicted_element_count": int(
            decision_summary.get("adapter_contradicted_element_count", 0) or 0
        ),
        "decision_fallback_ontology_element_count": int(
            decision_summary.get("fallback_ontology_element_count", 0) or 0
        ),
        "proof_supported_element_count": int(
            decision_summary.get("proof_supported_element_count", 0) or 0
        ),
        "logic_unprovable_element_count": int(
            decision_summary.get("logic_unprovable_element_count", 0) or 0
        ),
        "ontology_invalid_element_count": int(
            decision_summary.get("ontology_invalid_element_count", 0) or 0
        ),
        "parsed_record_count": int(support_trace_summary.get("parsed_record_count", 0) or 0),
        "parse_quality_tier_counts": parse_quality_tier_counts,
        "avg_parse_quality_score": float(
            support_trace_summary.get("avg_parse_quality_score", 0.0) or 0.0
        ),
        "low_quality_parsed_record_count": low_quality_parsed_record_count,
        "parse_quality_issue_element_count": len(parse_quality_issue_elements),
        "parse_quality_issue_elements": parse_quality_issue_elements,
        "parse_quality_recommendation": (
            "improve_parse_quality" if parse_quality_issue_elements else ""
        ),
        "total_elements": coverage_claim.get("total_elements", 0),
        "total_links": coverage_claim.get("total_links", 0),
        "total_facts": coverage_claim.get("total_facts", 0),
        "support_by_kind": coverage_claim.get("support_by_kind", {}),
        "authority_treatment_summary": coverage_claim.get(
            "authority_treatment_summary", {}
        ),
        "authority_rule_candidate_summary": coverage_claim.get(
            "authority_rule_candidate_summary", {}
        ),
        "support_trace_summary": support_trace_summary,
        "support_packet_summary": coverage_claim.get("support_packet_summary", {}),
        "status_counts": coverage_claim.get(
            "status_counts",
            {"covered": 0, "partially_supported": 0, "missing": 0},
        ),
        "missing_elements": missing_elements,
        "partially_supported_elements": partially_supported_elements,
        "unresolved_element_count": int(gap_claim.get("unresolved_count", 0) or 0)
        if isinstance(gap_claim, dict)
        else 0,
        "unresolved_elements": unresolved_elements,
        "recommended_gap_actions": recommended_gap_actions,
        "contradiction_candidate_count": contradiction_candidate_count,
        "contradicted_elements": contradicted_elements,
        "graph_trace_summary": {
            "traced_link_count": traced_link_count,
            "snapshot_created_count": snapshot_created_count,
            "snapshot_reused_count": snapshot_reused_count,
            "source_table_counts": source_table_counts,
            "graph_status_counts": graph_status_counts,
            "graph_id_count": graph_id_count,
        },
    }


def _aggregate_graph_support_metrics(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    semantic_cluster_count = 0
    semantic_duplicate_count = 0
    support_by_kind: Dict[str, int] = {}
    support_by_source: Dict[str, int] = {}
    source_family_counts: Dict[str, int] = {}
    record_scope_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}

    def _merge_counts(target: Dict[str, int], counts: Any) -> None:
        if not isinstance(counts, dict):
            return
        for key, value in counts.items():
            normalized_key = str(key or "").strip()
            if not normalized_key:
                continue
            target[normalized_key] = target.get(normalized_key, 0) + int(value or 0)

    def _increment_count(target: Dict[str, int], value: Any) -> None:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            return
        target[normalized_value] = target.get(normalized_value, 0) + 1

    for task in tasks:
        graph_support = task.get("graph_support") or {}
        graph_summary = graph_support.get("summary", {}) if isinstance(graph_support, dict) else {}
        semantic_cluster_count += int(graph_summary.get("semantic_cluster_count", 0) or 0)
        semantic_duplicate_count += int(
            graph_summary.get("semantic_duplicate_count", 0) or 0
        )
        _merge_counts(support_by_kind, graph_summary.get("support_by_kind"))
        _merge_counts(support_by_source, graph_summary.get("support_by_source"))

        graph_results = graph_support.get("results", []) if isinstance(graph_support, dict) else []
        if not isinstance(graph_results, list):
            continue
        for result in graph_results:
            if not isinstance(result, dict):
                continue
            _increment_count(source_family_counts, result.get("source_family"))
            _increment_count(record_scope_counts, result.get("record_scope"))
            _increment_count(artifact_family_counts, result.get("artifact_family"))
            _increment_count(corpus_family_counts, result.get("corpus_family"))
            _increment_count(content_origin_counts, result.get("content_origin"))

    return {
        "semantic_cluster_count": semantic_cluster_count,
        "semantic_duplicate_count": semantic_duplicate_count,
        "support_by_kind": support_by_kind,
        "support_by_source": support_by_source,
        "source_family_counts": source_family_counts,
        "record_scope_counts": record_scope_counts,
        "artifact_family_counts": artifact_family_counts,
        "corpus_family_counts": corpus_family_counts,
        "content_origin_counts": content_origin_counts,
    }


def _select_last_adaptive_retry(
    current: Optional[Dict[str, Any]],
    *,
    timestamp: Any,
    claim_element_id: Any,
    claim_element_text: Any,
    adaptive_query_strategy: Any,
    reason: Any,
) -> Dict[str, Any]:
    candidate = {
        "claim_element_id": claim_element_id,
        "claim_element_text": claim_element_text,
        "timestamp": timestamp,
        "adaptive_query_strategy": adaptive_query_strategy,
        "reason": reason,
        **_classify_adaptive_retry_recency(timestamp),
    }
    if not isinstance(current, dict):
        return candidate

    current_timestamp = str(current.get("timestamp") or "")
    candidate_timestamp = str(timestamp or "")
    if candidate_timestamp and current_timestamp:
        return candidate if candidate_timestamp >= current_timestamp else current
    if candidate_timestamp and not current_timestamp:
        return candidate
    return current


def _aggregate_adaptive_retry_metrics(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    adaptive_retry_task_count = 0
    priority_penalized_task_count = 0
    adaptive_query_strategy_counts: Dict[str, int] = {}
    adaptive_retry_reason_counts: Dict[str, int] = {}
    last_adaptive_retry: Optional[Dict[str, Any]] = None

    for task in tasks:
        adaptive_retry_state = (
            task.get("adaptive_retry_state") if isinstance(task, dict) else None
        )
        if not isinstance(adaptive_retry_state, dict):
            continue
        if not adaptive_retry_state.get("applied"):
            continue
        adaptive_retry_task_count += 1
        priority_penalty = int(adaptive_retry_state.get("priority_penalty", 0) or 0)
        if priority_penalty > 0:
            priority_penalized_task_count += 1
        adaptive_query_strategy = str(
            adaptive_retry_state.get("adaptive_query_strategy") or ""
        )
        if adaptive_query_strategy:
            adaptive_query_strategy_counts[adaptive_query_strategy] = (
                adaptive_query_strategy_counts.get(adaptive_query_strategy, 0) + 1
            )
        adaptive_retry_reason = str(adaptive_retry_state.get("reason") or "")
        if adaptive_retry_reason:
            adaptive_retry_reason_counts[adaptive_retry_reason] = (
                adaptive_retry_reason_counts.get(adaptive_retry_reason, 0) + 1
            )
        last_adaptive_retry = _select_last_adaptive_retry(
            last_adaptive_retry,
            timestamp=(
                adaptive_retry_state.get("latest_attempted_at")
                or adaptive_retry_state.get("latest_zero_result_at")
            ),
            claim_element_id=task.get("claim_element_id"),
            claim_element_text=task.get("claim_element"),
            adaptive_query_strategy=adaptive_query_strategy,
            reason=adaptive_retry_reason,
        )

    return {
        "adaptive_retry_task_count": adaptive_retry_task_count,
        "priority_penalized_task_count": priority_penalized_task_count,
        "adaptive_query_strategy_counts": adaptive_query_strategy_counts,
        "adaptive_retry_reason_counts": adaptive_retry_reason_counts,
        "last_adaptive_retry": last_adaptive_retry,
    }


def _aggregate_authority_search_program_metrics(
    tasks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    authority_search_program_task_count = 0
    authority_search_program_count = 0
    authority_search_program_type_counts: Dict[str, int] = {}
    authority_search_intent_counts: Dict[str, int] = {}
    primary_authority_program_type_counts: Dict[str, int] = {}
    primary_authority_program_bias_counts: Dict[str, int] = {}
    primary_authority_program_rule_bias_counts: Dict[str, int] = {}

    for task in tasks:
        if not isinstance(task, dict):
            continue
        summary = task.get("authority_search_program_summary")
        if not isinstance(summary, dict):
            continue
        program_count = int(summary.get("program_count", 0) or 0)
        if program_count <= 0:
            continue
        authority_search_program_task_count += 1
        authority_search_program_count += program_count

        for program_type, count in (summary.get("program_type_counts") or {}).items():
            authority_search_program_type_counts[str(program_type)] = (
                authority_search_program_type_counts.get(str(program_type), 0)
                + int(count or 0)
            )
        for intent, count in (summary.get("authority_intent_counts") or {}).items():
            authority_search_intent_counts[str(intent)] = (
                authority_search_intent_counts.get(str(intent), 0)
                + int(count or 0)
            )

        primary_program_type = str(summary.get("primary_program_type") or "")
        if primary_program_type:
            primary_authority_program_type_counts[primary_program_type] = (
                primary_authority_program_type_counts.get(primary_program_type, 0) + 1
            )
        primary_program_bias = str(summary.get("primary_program_bias") or "")
        if primary_program_bias:
            primary_authority_program_bias_counts[primary_program_bias] = (
                primary_authority_program_bias_counts.get(primary_program_bias, 0) + 1
            )
        primary_program_rule_bias = str(summary.get("primary_program_rule_bias") or "")
        if primary_program_rule_bias:
            primary_authority_program_rule_bias_counts[primary_program_rule_bias] = (
                primary_authority_program_rule_bias_counts.get(primary_program_rule_bias, 0) + 1
            )

    return {
        "authority_search_program_task_count": authority_search_program_task_count,
        "authority_search_program_count": authority_search_program_count,
        "authority_search_program_type_counts": authority_search_program_type_counts,
        "authority_search_intent_counts": authority_search_intent_counts,
        "primary_authority_program_type_counts": primary_authority_program_type_counts,
        "primary_authority_program_bias_counts": primary_authority_program_bias_counts,
        "primary_authority_program_rule_bias_counts": primary_authority_program_rule_bias_counts,
    }


def _aggregate_rule_candidate_metrics(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    rule_candidate_backed_task_count = 0
    total_rule_candidate_count = 0
    matched_claim_element_rule_count = 0
    rule_candidate_type_counts: Dict[str, int] = {}

    for task in tasks:
        if not isinstance(task, dict):
            continue
        summary = task.get("authority_rule_candidate_summary")
        if not isinstance(summary, dict):
            continue
        candidate_count = int(summary.get("total_rule_candidate_count", 0) or 0)
        if candidate_count <= 0:
            continue

        rule_candidate_backed_task_count += 1
        total_rule_candidate_count += candidate_count
        matched_claim_element_rule_count += int(
            summary.get("matched_claim_element_rule_count", 0) or 0
        )
        for rule_type, count in (summary.get("rule_type_counts") or {}).items():
            normalized_type = str(rule_type)
            rule_candidate_type_counts[normalized_type] = (
                rule_candidate_type_counts.get(normalized_type, 0) + int(count or 0)
            )

    return {
        "rule_candidate_backed_task_count": rule_candidate_backed_task_count,
        "total_rule_candidate_count": total_rule_candidate_count,
        "matched_claim_element_rule_count": matched_claim_element_rule_count,
        "rule_candidate_type_counts": rule_candidate_type_counts,
    }


def _summarize_follow_up_plan_claim(claim_plan: Dict[str, Any]) -> Dict[str, Any]:
    tasks = claim_plan.get("tasks", []) if isinstance(claim_plan, dict) else []
    recommended_actions: Dict[str, int] = {}
    follow_up_focus_counts: Dict[str, int] = {}
    query_strategy_counts: Dict[str, int] = {}
    proof_decision_source_counts: Dict[str, int] = {}
    resolution_status_counts: Dict[str, int] = {}
    resolution_applied_counts: Dict[str, int] = {}
    temporal_rule_status_counts: Dict[str, int] = {}
    temporal_rule_blocking_reason_counts: Dict[str, int] = {}
    temporal_resolution_status_counts: Dict[str, int] = {}
    for task in tasks:
        action = str(task.get("recommended_action") or "unspecified")
        recommended_actions[action] = recommended_actions.get(action, 0) + 1
        focus = str(task.get("follow_up_focus") or "unknown")
        follow_up_focus_counts[focus] = follow_up_focus_counts.get(focus, 0) + 1
        strategy = str(task.get("query_strategy") or "unknown")
        query_strategy_counts[strategy] = query_strategy_counts.get(strategy, 0) + 1
        decision_source = str(task.get("proof_decision_source") or "unknown")
        proof_decision_source_counts[decision_source] = (
            proof_decision_source_counts.get(decision_source, 0) + 1
        )
        resolution_status = str(task.get("resolution_status") or "")
        if resolution_status:
            resolution_status_counts[resolution_status] = (
                resolution_status_counts.get(resolution_status, 0) + 1
            )
        resolution_applied = str(task.get("resolution_applied") or "")
        if resolution_applied:
            resolution_applied_counts[resolution_applied] = (
                resolution_applied_counts.get(resolution_applied, 0) + 1
            )
        temporal_rule_status = str(task.get("temporal_rule_status") or "")
        if temporal_rule_status:
            temporal_rule_status_counts[temporal_rule_status] = (
                temporal_rule_status_counts.get(temporal_rule_status, 0) + 1
            )
        for reason in (task.get("temporal_rule_blocking_reasons") or []):
            normalized_reason = str(reason or "").strip()
            if not normalized_reason:
                continue
            temporal_rule_blocking_reason_counts[normalized_reason] = (
                temporal_rule_blocking_reason_counts.get(normalized_reason, 0) + 1
            )
        if focus == "temporal_gap_closure" and resolution_status:
            temporal_resolution_status_counts[resolution_status] = (
                temporal_resolution_status_counts.get(resolution_status, 0) + 1
            )
    graph_support_metrics = _aggregate_graph_support_metrics(tasks)
    adaptive_retry_metrics = _aggregate_adaptive_retry_metrics(tasks)
    authority_search_program_metrics = _aggregate_authority_search_program_metrics(tasks)
    rule_candidate_metrics = _aggregate_rule_candidate_metrics(tasks)
    fact_targeting_metrics = _aggregate_fact_targeting_metrics(tasks)
    return {
        "task_count": len(tasks),
        "blocked_task_count": claim_plan.get("blocked_task_count", 0),
        "graph_supported_task_count": len(
            [task for task in tasks if task.get("has_graph_support")]
        ),
        "manual_review_task_count": len(
            [task for task in tasks if task.get("execution_mode") == "manual_review"]
        ),
        "suppressed_task_count": len(
            [task for task in tasks if task.get("should_suppress_retrieval")]
        ),
        "contradiction_task_count": len(
            [
                task
                for task in tasks
                if task.get("follow_up_focus") == "contradiction_resolution"
            ]
        ),
        "reasoning_gap_task_count": len(
            [
                task
                for task in tasks
                if task.get("follow_up_focus") == "reasoning_gap_closure"
            ]
        ),
        "temporal_gap_task_count": len(
            [
                task
                for task in tasks
                if task.get("follow_up_focus") == "temporal_gap_closure"
            ]
        ),
        "fact_gap_task_count": len(
            [task for task in tasks if task.get("follow_up_focus") == "fact_gap_closure"]
        ),
        "adverse_authority_task_count": len(
            [
                task
                for task in tasks
                if task.get("follow_up_focus") == "adverse_authority_review"
            ]
        ),
        "parse_quality_task_count": len(
            [
                task
                for task in tasks
                if task.get("follow_up_focus") == "parse_quality_improvement"
            ]
        ),
        "quality_gap_targeted_task_count": len(
            [
                task
                for task in tasks
                if task.get("query_strategy") == "quality_gap_targeted"
            ]
        ),
        "temporal_gap_targeted_task_count": len(
            [
                task
                for task in tasks
                if task.get("query_strategy") == "temporal_gap_targeted"
            ]
        ),
        "semantic_cluster_count": graph_support_metrics["semantic_cluster_count"],
        "semantic_duplicate_count": graph_support_metrics["semantic_duplicate_count"],
        "support_by_kind": graph_support_metrics["support_by_kind"],
        "support_by_source": graph_support_metrics["support_by_source"],
        "source_family_counts": graph_support_metrics["source_family_counts"],
        "record_scope_counts": graph_support_metrics["record_scope_counts"],
        "artifact_family_counts": graph_support_metrics["artifact_family_counts"],
        "corpus_family_counts": graph_support_metrics["corpus_family_counts"],
        "content_origin_counts": graph_support_metrics["content_origin_counts"],
        "primary_missing_fact_counts": fact_targeting_metrics["primary_missing_fact_counts"],
        "missing_fact_bundle_counts": fact_targeting_metrics["missing_fact_bundle_counts"],
        "satisfied_fact_bundle_counts": fact_targeting_metrics["satisfied_fact_bundle_counts"],
        "follow_up_focus_counts": follow_up_focus_counts,
        "query_strategy_counts": query_strategy_counts,
        "proof_decision_source_counts": proof_decision_source_counts,
        "resolution_status_counts": resolution_status_counts,
        "temporal_resolution_status_counts": temporal_resolution_status_counts,
        "resolution_applied_counts": resolution_applied_counts,
        "temporal_rule_status_counts": temporal_rule_status_counts,
        "temporal_rule_blocking_reason_counts": temporal_rule_blocking_reason_counts,
        "adaptive_retry_task_count": adaptive_retry_metrics["adaptive_retry_task_count"],
        "priority_penalized_task_count": adaptive_retry_metrics[
            "priority_penalized_task_count"
        ],
        "adaptive_query_strategy_counts": adaptive_retry_metrics[
            "adaptive_query_strategy_counts"
        ],
        "adaptive_retry_reason_counts": adaptive_retry_metrics[
            "adaptive_retry_reason_counts"
        ],
        "last_adaptive_retry": adaptive_retry_metrics["last_adaptive_retry"],
        "authority_search_program_task_count": authority_search_program_metrics[
            "authority_search_program_task_count"
        ],
        "authority_search_program_count": authority_search_program_metrics[
            "authority_search_program_count"
        ],
        "authority_search_program_type_counts": authority_search_program_metrics[
            "authority_search_program_type_counts"
        ],
        "authority_search_intent_counts": authority_search_program_metrics[
            "authority_search_intent_counts"
        ],
        "primary_authority_program_type_counts": authority_search_program_metrics[
            "primary_authority_program_type_counts"
        ],
        "primary_authority_program_bias_counts": authority_search_program_metrics[
            "primary_authority_program_bias_counts"
        ],
        "primary_authority_program_rule_bias_counts": authority_search_program_metrics[
            "primary_authority_program_rule_bias_counts"
        ],
        "rule_candidate_backed_task_count": rule_candidate_metrics[
            "rule_candidate_backed_task_count"
        ],
        "total_rule_candidate_count": rule_candidate_metrics[
            "total_rule_candidate_count"
        ],
        "matched_claim_element_rule_count": rule_candidate_metrics[
            "matched_claim_element_rule_count"
        ],
        "rule_candidate_type_counts": rule_candidate_metrics[
            "rule_candidate_type_counts"
        ],
        "recommended_actions": recommended_actions,
    }


def _summarize_follow_up_execution_claim(claim_execution: Dict[str, Any]) -> Dict[str, Any]:
    executed_tasks = claim_execution.get("tasks", []) if isinstance(claim_execution, dict) else []
    skipped_tasks = (
        claim_execution.get("skipped_tasks", []) if isinstance(claim_execution, dict) else []
    )
    all_tasks = [task for task in executed_tasks + skipped_tasks if isinstance(task, dict)]
    suppressed = [task for task in skipped_tasks if "suppressed" in task.get("skipped", {})]
    manual_review_skips = [
        task for task in skipped_tasks if "manual_review" in task.get("skipped", {})
    ]
    cooldown_skips = [
        task
        for task in skipped_tasks
        if any(
            value.get("reason") == "duplicate_within_cooldown"
            for value in task.get("skipped", {}).values()
            if isinstance(value, dict)
        )
    ]
    follow_up_focus_counts: Dict[str, int] = {}
    query_strategy_counts: Dict[str, int] = {}
    proof_decision_source_counts: Dict[str, int] = {}
    resolution_status_counts: Dict[str, int] = {}
    resolution_applied_counts: Dict[str, int] = {}
    temporal_rule_status_counts: Dict[str, int] = {}
    temporal_rule_blocking_reason_counts: Dict[str, int] = {}
    temporal_resolution_status_counts: Dict[str, int] = {}
    for task in all_tasks:
        focus = str(task.get("follow_up_focus") or "unknown")
        follow_up_focus_counts[focus] = follow_up_focus_counts.get(focus, 0) + 1
        strategy = str(task.get("query_strategy") or "unknown")
        query_strategy_counts[strategy] = query_strategy_counts.get(strategy, 0) + 1
        decision_source = str(task.get("proof_decision_source") or "unknown")
        proof_decision_source_counts[decision_source] = (
            proof_decision_source_counts.get(decision_source, 0) + 1
        )
        resolution_status = str(task.get("resolution_status") or "")
        if resolution_status:
            resolution_status_counts[resolution_status] = (
                resolution_status_counts.get(resolution_status, 0) + 1
            )
        resolution_applied = str(task.get("resolution_applied") or "")
        if resolution_applied:
            resolution_applied_counts[resolution_applied] = (
                resolution_applied_counts.get(resolution_applied, 0) + 1
            )
        temporal_rule_status = str(task.get("temporal_rule_status") or "")
        if temporal_rule_status:
            temporal_rule_status_counts[temporal_rule_status] = (
                temporal_rule_status_counts.get(temporal_rule_status, 0) + 1
            )
        for reason in (task.get("temporal_rule_blocking_reasons") or []):
            normalized_reason = str(reason or "").strip()
            if not normalized_reason:
                continue
            temporal_rule_blocking_reason_counts[normalized_reason] = (
                temporal_rule_blocking_reason_counts.get(normalized_reason, 0) + 1
            )
        if focus == "temporal_gap_closure" and resolution_status:
            temporal_resolution_status_counts[resolution_status] = (
                temporal_resolution_status_counts.get(resolution_status, 0) + 1
            )
    graph_support_metrics = _aggregate_graph_support_metrics(executed_tasks + skipped_tasks)
    adaptive_retry_metrics = _aggregate_adaptive_retry_metrics(all_tasks)
    authority_search_program_metrics = _aggregate_authority_search_program_metrics(all_tasks)
    rule_candidate_metrics = _aggregate_rule_candidate_metrics(all_tasks)
    fact_targeting_metrics = _aggregate_fact_targeting_metrics(all_tasks)
    return {
        "executed_task_count": len(executed_tasks),
        "skipped_task_count": len(skipped_tasks),
        "suppressed_task_count": len(suppressed),
        "manual_review_task_count": len(manual_review_skips),
        "cooldown_skipped_task_count": len(cooldown_skips),
        "contradiction_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "contradiction_resolution"]
        ),
        "reasoning_gap_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "reasoning_gap_closure"]
        ),
        "temporal_gap_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "temporal_gap_closure"]
        ),
        "fact_gap_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "fact_gap_closure"]
        ),
        "adverse_authority_task_count": len(
            [
                task
                for task in all_tasks
                if task.get("follow_up_focus") == "adverse_authority_review"
            ]
        ),
        "parse_quality_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "parse_quality_improvement"]
        ),
        "quality_gap_targeted_task_count": len(
            [task for task in all_tasks if task.get("query_strategy") == "quality_gap_targeted"]
        ),
        "temporal_gap_targeted_task_count": len(
            [task for task in all_tasks if task.get("query_strategy") == "temporal_gap_targeted"]
        ),
        "semantic_cluster_count": graph_support_metrics["semantic_cluster_count"],
        "semantic_duplicate_count": graph_support_metrics["semantic_duplicate_count"],
        "support_by_kind": graph_support_metrics["support_by_kind"],
        "support_by_source": graph_support_metrics["support_by_source"],
        "source_family_counts": graph_support_metrics["source_family_counts"],
        "record_scope_counts": graph_support_metrics["record_scope_counts"],
        "artifact_family_counts": graph_support_metrics["artifact_family_counts"],
        "corpus_family_counts": graph_support_metrics["corpus_family_counts"],
        "content_origin_counts": graph_support_metrics["content_origin_counts"],
        "primary_missing_fact_counts": fact_targeting_metrics["primary_missing_fact_counts"],
        "missing_fact_bundle_counts": fact_targeting_metrics["missing_fact_bundle_counts"],
        "satisfied_fact_bundle_counts": fact_targeting_metrics["satisfied_fact_bundle_counts"],
        "follow_up_focus_counts": follow_up_focus_counts,
        "query_strategy_counts": query_strategy_counts,
        "proof_decision_source_counts": proof_decision_source_counts,
        "resolution_status_counts": resolution_status_counts,
        "temporal_resolution_status_counts": temporal_resolution_status_counts,
        "resolution_applied_counts": resolution_applied_counts,
        "temporal_rule_status_counts": temporal_rule_status_counts,
        "temporal_rule_blocking_reason_counts": temporal_rule_blocking_reason_counts,
        "adaptive_retry_task_count": adaptive_retry_metrics["adaptive_retry_task_count"],
        "priority_penalized_task_count": adaptive_retry_metrics[
            "priority_penalized_task_count"
        ],
        "adaptive_query_strategy_counts": adaptive_retry_metrics[
            "adaptive_query_strategy_counts"
        ],
        "adaptive_retry_reason_counts": adaptive_retry_metrics[
            "adaptive_retry_reason_counts"
        ],
        "last_adaptive_retry": adaptive_retry_metrics["last_adaptive_retry"],
        "authority_search_program_task_count": authority_search_program_metrics[
            "authority_search_program_task_count"
        ],
        "authority_search_program_count": authority_search_program_metrics[
            "authority_search_program_count"
        ],
        "authority_search_program_type_counts": authority_search_program_metrics[
            "authority_search_program_type_counts"
        ],
        "authority_search_intent_counts": authority_search_program_metrics[
            "authority_search_intent_counts"
        ],
        "primary_authority_program_type_counts": authority_search_program_metrics[
            "primary_authority_program_type_counts"
        ],
        "primary_authority_program_bias_counts": authority_search_program_metrics[
            "primary_authority_program_bias_counts"
        ],
        "primary_authority_program_rule_bias_counts": authority_search_program_metrics[
            "primary_authority_program_rule_bias_counts"
        ],
        "rule_candidate_backed_task_count": rule_candidate_metrics[
            "rule_candidate_backed_task_count"
        ],
        "total_rule_candidate_count": rule_candidate_metrics[
            "total_rule_candidate_count"
        ],
        "matched_claim_element_rule_count": rule_candidate_metrics[
            "matched_claim_element_rule_count"
        ],
        "rule_candidate_type_counts": rule_candidate_metrics[
            "rule_candidate_type_counts"
        ],
    }


def _aggregate_fact_targeting_metrics(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    primary_missing_fact_counts: Dict[str, int] = {}
    missing_fact_bundle_counts: Dict[str, int] = {}
    satisfied_fact_bundle_counts: Dict[str, int] = {}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        primary_missing_fact = str(entry.get("primary_missing_fact") or "").strip()
        if primary_missing_fact:
            primary_missing_fact_counts[primary_missing_fact] = (
                primary_missing_fact_counts.get(primary_missing_fact, 0) + 1
            )
        for item in entry.get("missing_fact_bundle", []) or []:
            normalized_item = str(item or "").strip()
            if normalized_item:
                missing_fact_bundle_counts[normalized_item] = (
                    missing_fact_bundle_counts.get(normalized_item, 0) + 1
                )
        for item in entry.get("satisfied_fact_bundle", []) or []:
            normalized_item = str(item or "").strip()
            if normalized_item:
                satisfied_fact_bundle_counts[normalized_item] = (
                    satisfied_fact_bundle_counts.get(normalized_item, 0) + 1
                )

    return {
        "primary_missing_fact_counts": primary_missing_fact_counts,
        "missing_fact_bundle_counts": missing_fact_bundle_counts,
        "satisfied_fact_bundle_counts": satisfied_fact_bundle_counts,
    }


def _summarize_execution_quality_claim(
    pre_claim_summary: Optional[Dict[str, Any]],
    post_claim_summary: Optional[Dict[str, Any]],
    execution_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    pre_summary = pre_claim_summary if isinstance(pre_claim_summary, dict) else {}
    post_summary = post_claim_summary if isinstance(post_claim_summary, dict) else {}
    execution = execution_summary if isinstance(execution_summary, dict) else {}

    pre_low_quality_count = int(pre_summary.get("low_quality_parsed_record_count", 0) or 0)
    post_low_quality_count = int(post_summary.get("low_quality_parsed_record_count", 0) or 0)
    pre_issue_elements = sorted(
        {
            str(element).strip()
            for element in (pre_summary.get("parse_quality_issue_elements", []) or [])
            if str(element).strip()
        }
    )
    post_issue_elements = sorted(
        {
            str(element).strip()
            for element in (post_summary.get("parse_quality_issue_elements", []) or [])
            if str(element).strip()
        }
    )
    parse_quality_task_count = int(execution.get("parse_quality_task_count", 0) or 0)
    quality_gap_targeted_task_count = int(
        execution.get("quality_gap_targeted_task_count", 0) or 0
    )

    resolved_issue_elements = [
        element for element in pre_issue_elements if element not in post_issue_elements
    ]
    newly_flagged_issue_elements = [
        element for element in post_issue_elements if element not in pre_issue_elements
    ]

    if parse_quality_task_count <= 0 and quality_gap_targeted_task_count <= 0:
        improvement_status = "not_targeted"
    elif (
        post_low_quality_count < pre_low_quality_count
        or len(post_issue_elements) < len(pre_issue_elements)
    ):
        improvement_status = "improved"
    elif (
        post_low_quality_count > pre_low_quality_count
        or len(post_issue_elements) > len(pre_issue_elements)
    ):
        improvement_status = "regressed"
    else:
        improvement_status = "unchanged"

    return {
        "pre_low_quality_parsed_record_count": pre_low_quality_count,
        "post_low_quality_parsed_record_count": post_low_quality_count,
        "low_quality_parsed_record_delta": post_low_quality_count - pre_low_quality_count,
        "pre_parse_quality_issue_element_count": len(pre_issue_elements),
        "post_parse_quality_issue_element_count": len(post_issue_elements),
        "parse_quality_issue_element_delta": len(post_issue_elements) - len(pre_issue_elements),
        "pre_parse_quality_issue_elements": pre_issue_elements,
        "post_parse_quality_issue_elements": post_issue_elements,
        "resolved_parse_quality_issue_elements": resolved_issue_elements,
        "remaining_parse_quality_issue_elements": post_issue_elements,
        "newly_flagged_parse_quality_issue_elements": newly_flagged_issue_elements,
        "parse_quality_task_count": parse_quality_task_count,
        "quality_gap_targeted_task_count": quality_gap_targeted_task_count,
        "quality_improvement_status": improvement_status,
        "recommended_next_action": (
            "improve_parse_quality"
            if (
                post_low_quality_count > 0
                and improvement_status in {"unchanged", "regressed"}
            )
            else ""
        ),
    }


def build_claim_support_review_payload(
    mediator: Any,
    request: ClaimSupportReviewRequest,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, request.user_id)
    required_support_kinds = (
        request.required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    matrix = mediator.get_claim_coverage_matrix(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )
    overview = mediator.get_claim_overview(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )

    coverage_claims = matrix.get("claims", {}) if isinstance(matrix, dict) else {}
    overview_claims = overview.get("claims", {}) if isinstance(overview, dict) else {}
    diagnostic_snapshots = mediator.get_claim_support_diagnostic_snapshots(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )
    snapshot_claims = (
        diagnostic_snapshots.get("claims", {})
        if isinstance(diagnostic_snapshots, dict)
        else {}
    )
    gap_claims = {
        claim_name: claim_snapshot.get("gaps", {})
        for claim_name, claim_snapshot in snapshot_claims.items()
        if isinstance(claim_snapshot, dict)
        and isinstance(claim_snapshot.get("gaps"), dict)
        and not bool(
            ((claim_snapshot.get("snapshots") or {}).get("gaps") or {}).get("is_stale")
        )
    }
    contradiction_claims = {
        claim_name: claim_snapshot.get("contradictions", {})
        for claim_name, claim_snapshot in snapshot_claims.items()
        if isinstance(claim_snapshot, dict)
        and isinstance(claim_snapshot.get("contradictions"), dict)
        and not bool(
            ((claim_snapshot.get("snapshots") or {}).get("contradictions") or {}).get("is_stale")
        )
    }
    missing_gap_claims = [
        claim_name for claim_name in coverage_claims.keys()
        if claim_name not in gap_claims or not gap_claims.get(claim_name)
    ]
    if missing_gap_claims:
        gaps = mediator.get_claim_support_gaps(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            required_support_kinds=required_support_kinds,
        )
        computed_gap_claims = gaps.get("claims", {}) if isinstance(gaps, dict) else {}
        for claim_name in missing_gap_claims:
            if isinstance(computed_gap_claims.get(claim_name), dict):
                gap_claims[claim_name] = computed_gap_claims[claim_name]
    missing_contradiction_claims = [
        claim_name for claim_name in coverage_claims.keys()
        if claim_name not in contradiction_claims or not contradiction_claims.get(claim_name)
    ]
    if missing_contradiction_claims:
        contradiction_candidates = mediator.get_claim_contradiction_candidates(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
        )
        computed_contradiction_claims = (
            contradiction_candidates.get("claims", {})
            if isinstance(contradiction_candidates, dict)
            else {}
        )
        for claim_name in missing_contradiction_claims:
            if isinstance(computed_contradiction_claims.get(claim_name), dict):
                contradiction_claims[claim_name] = computed_contradiction_claims[claim_name]
    validation = mediator.get_claim_support_validation(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )
    validation_claims = validation.get("claims", {}) if isinstance(validation, dict) else {}

    testimony_payload: Dict[str, Any] = {}
    get_claim_testimony_records = getattr(mediator, "get_claim_testimony_records", None)
    if callable(get_claim_testimony_records):
        candidate_payload = get_claim_testimony_records(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            limit=25,
        )
        if isinstance(candidate_payload, dict):
            testimony_payload = candidate_payload
    testimony_claims = testimony_payload.get("claims", {}) if isinstance(testimony_payload, dict) else {}
    testimony_summary = testimony_payload.get("summary", {}) if isinstance(testimony_payload, dict) else {}
    document_claims = _collect_claim_document_records(
        mediator,
        resolved_user_id,
        request.claim_type,
        limit=25,
        preview_chunk_limit=3,
    )

    for claim_name, claim_matrix in coverage_claims.items():
        if isinstance(claim_matrix, dict):
            _attach_testimony_to_claim_matrix(
                claim_matrix,
                testimony_claims.get(claim_name, []),
            )
            _attach_documents_to_claim_matrix(
                claim_matrix,
                document_claims.get(claim_name, []),
            )
            _attach_validation_to_claim_matrix(
                mediator,
                resolved_user_id,
                claim_name,
                claim_matrix,
                validation_claims.get(claim_name, {}),
                document_claims.get(claim_name, []),
            )

    coverage_summary = {
        claim_name: _summarize_claim_coverage_claim(
            claim_name,
            claim_matrix,
            overview_claims.get(claim_name, {}),
            gap_claims.get(claim_name, {}),
            contradiction_claims.get(claim_name, {}),
            validation_claims.get(claim_name, {}),
        )
        for claim_name, claim_matrix in coverage_claims.items()
        if isinstance(claim_matrix, dict)
    }
    for claim_name, summary in coverage_summary.items():
        if not isinstance(summary, dict):
            continue
        claim_testimony_summary = testimony_summary.get(claim_name, {}) if isinstance(testimony_summary, dict) else {}
        summary["testimony_record_count"] = int(claim_testimony_summary.get("record_count", 0) or 0)
        summary["testimony_linked_element_count"] = int(claim_testimony_summary.get("linked_element_count", 0) or 0)
        summary["testimony_firsthand_status_counts"] = dict(
            claim_testimony_summary.get("firsthand_status_counts", {}) or {}
        )
        claim_document_summary = summarize_claim_document_artifacts_claim(
            document_claims.get(claim_name, [])
        )
        summary["document_record_count"] = int(claim_document_summary.get("record_count", 0) or 0)
        summary["document_linked_element_count"] = int(claim_document_summary.get("linked_element_count", 0) or 0)
        summary["document_total_chunk_count"] = int(claim_document_summary.get("total_chunk_count", 0) or 0)
        summary["document_total_fact_count"] = int(claim_document_summary.get("total_fact_count", 0) or 0)
        summary["document_low_quality_record_count"] = int(claim_document_summary.get("low_quality_record_count", 0) or 0)
        summary["document_graph_ready_record_count"] = int(
            claim_document_summary.get("graph_ready_record_count", 0) or 0
        )

    intake_status = build_intake_status_summary(mediator, include_iteration_count=True)
    intake_case_summary = build_intake_case_review_summary(mediator)
    intake_contradiction_summary = summarize_intake_contradictions(
        intake_status.get("contradictions")
    )
    workflow_phase_plan = _build_review_workflow_phase_plan(
        mediator,
        intake_status=intake_status,
        intake_case_summary=intake_case_summary,
    )
    workflow_phase_priority = _build_review_workflow_phase_priority(workflow_phase_plan)
    workflow_priority = _build_review_workflow_priority(
        intake_status=intake_status,
        intake_case_summary=intake_case_summary,
        workflow_phase_priority=workflow_phase_priority,
    )
    handoff_metadata = _build_confirmed_intake_summary_handoff_metadata(mediator)
    document_focus_preview = _get_formalization_document_focus_preview(mediator)

    payload: Dict[str, Any] = {
        "user_id": resolved_user_id,
        "claim_type": request.claim_type,
        "required_support_kinds": required_support_kinds,
        "intake_status": intake_status,
        "intake_case_summary": intake_case_summary,
        "workflow_targeting_summary": (
            dict(intake_case_summary.get("workflow_targeting_summary") or {})
            if isinstance(intake_case_summary.get("workflow_targeting_summary"), dict)
            else {}
        ),
        "document_workflow_execution_summary": (
            dict(intake_case_summary.get("document_workflow_execution_summary") or {})
            if isinstance(intake_case_summary.get("document_workflow_execution_summary"), dict)
            else {}
        ),
        "document_grounding_improvement_summary": (
            dict(intake_case_summary.get("document_grounding_improvement_summary") or {})
            if isinstance(intake_case_summary.get("document_grounding_improvement_summary"), dict)
            else {}
        ),
        "document_grounding_lane_outcome_summary": (
            dict(intake_case_summary.get("document_grounding_lane_outcome_summary") or {})
            if isinstance(intake_case_summary.get("document_grounding_lane_outcome_summary"), dict)
            else {}
        ),
        "document_grounding_improvement_next_action": (
            dict(intake_case_summary.get("document_grounding_improvement_next_action") or {})
            if isinstance(intake_case_summary.get("document_grounding_improvement_next_action"), dict)
            else {}
        ),
        "document_drafting_next_action": (
            dict(intake_case_summary.get("document_drafting_next_action") or {})
            if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
            else {}
        ),
        "document_focus_preview": document_focus_preview,
        "recommended_next_action": (
            str((intake_status.get("next_action") or {}).get("action") or "")
            if isinstance(intake_status.get("next_action"), dict)
            else ""
        ),
        "workflow_phase_plan": workflow_phase_plan,
        "workflow_phase_priority": workflow_phase_priority,
        "workflow_priority": workflow_priority,
        "primary_validation_target": (
            dict(intake_status.get("primary_validation_target"))
            if isinstance(intake_status.get("primary_validation_target"), dict)
            else {}
        ),
        "intake_contradiction_summary": intake_contradiction_summary,
        "claim_coverage_matrix": coverage_claims,
        "claim_coverage_summary": coverage_summary,
        "claim_support_gaps": gap_claims,
        "claim_contradiction_candidates": contradiction_claims,
        "claim_support_validation": validation_claims,
        "claim_support_snapshots": {
            claim_name: claim_snapshot.get("snapshots", {})
            for claim_name, claim_snapshot in snapshot_claims.items()
            if isinstance(claim_snapshot, dict)
        },
        "claim_support_snapshot_summary": {
            claim_name: summarize_claim_support_snapshot_lifecycle(
                (snapshot_claims.get(claim_name, {}) or {}).get("snapshots", {})
            )
            for claim_name in coverage_claims.keys()
        },
        "claim_reasoning_review": {
            claim_name: _merge_claim_temporal_registry_into_reasoning_review(
                summarize_claim_reasoning_review(
                    validation_claims.get(claim_name, {})
                ),
                intake_case_summary=intake_case_summary,
                claim_type=claim_name,
            )
            for claim_name in coverage_claims.keys()
        },
        "question_recommendations": {
            claim_name: _build_claim_question_recommendations(
                claim_name,
                gap_claims.get(claim_name, {}),
                contradiction_claims.get(claim_name, {}),
                coverage_claims.get(claim_name, {}),
            )
            for claim_name in coverage_claims.keys()
        },
        "testimony_records": testimony_claims,
        "testimony_summary": {
            claim_name: summarize_claim_testimony_claim(
                testimony_claims.get(claim_name, [])
            )
            for claim_name in coverage_claims.keys()
        },
        "document_artifacts": document_claims,
        "document_summary": {
            claim_name: summarize_claim_document_artifacts_claim(
                document_claims.get(claim_name, [])
            )
            for claim_name in coverage_claims.keys()
        },
    }

    recent_follow_up_history = mediator.get_recent_claim_follow_up_execution(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        limit=10,
    )
    recent_follow_up_claims = (
        recent_follow_up_history.get("claims", {})
        if isinstance(recent_follow_up_history, dict)
        else {}
    )
    payload["follow_up_history"] = recent_follow_up_claims
    payload["follow_up_history_summary"] = {
        claim_name: summarize_follow_up_history_claim(
            recent_follow_up_claims.get(claim_name, [])
        )
        for claim_name in coverage_claims.keys()
    }

    if request.include_follow_up_plan:
        follow_up_plan = mediator.get_claim_follow_up_plan(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            required_support_kinds=required_support_kinds,
            cooldown_seconds=request.follow_up_cooldown_seconds,
        )
        follow_up_claims = (
            follow_up_plan.get("claims", {}) if isinstance(follow_up_plan, dict) else {}
        )
        payload["follow_up_plan"] = follow_up_claims
        payload["follow_up_plan_summary"] = {
            claim_name: _summarize_follow_up_plan_claim(claim_plan)
            for claim_name, claim_plan in follow_up_claims.items()
            if isinstance(claim_plan, dict)
        }

    if request.execute_follow_up:
        follow_up_execution = mediator.execute_claim_follow_up_plan(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            support_kind=request.follow_up_support_kind,
            max_tasks_per_claim=request.follow_up_max_tasks_per_claim,
            cooldown_seconds=request.follow_up_cooldown_seconds,
        )
        follow_up_execution_claims = (
            follow_up_execution.get("claims", {})
            if isinstance(follow_up_execution, dict)
            else {}
        )
        payload["follow_up_execution"] = follow_up_execution_claims
        payload["follow_up_execution_summary"] = {
            claim_name: _summarize_follow_up_execution_claim(claim_execution)
            for claim_name, claim_execution in follow_up_execution_claims.items()
            if isinstance(claim_execution, dict)
        }

    if request.include_support_summary:
        support_summary = mediator.summarize_claim_support(
            user_id=resolved_user_id,
            claim_type=request.claim_type,
        )
        payload["support_summary"] = (
            support_summary.get("claims", {}) if isinstance(support_summary, dict) else {}
        )

    if request.include_overview:
        payload["claim_overview"] = overview_claims

    if handoff_metadata:
        payload.update(handoff_metadata)

    return payload


def build_claim_support_testimony_payload(
    mediator: Any,
    request: ClaimSupportTestimonySaveRequest,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, request.user_id)
    required_support_kinds = (
        request.required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    save_claim_testimony_record = getattr(mediator, "save_claim_testimony_record", None)
    if not callable(save_claim_testimony_record):
        payload: Dict[str, Any] = {
            "user_id": resolved_user_id,
            "claim_type": request.claim_type,
            "recorded": False,
            "error": "testimony_persistence_unavailable",
        }
    else:
        testimony_metadata = _merge_intake_summary_handoff_metadata(
            request.testimony_metadata,
            mediator,
            claim_type=request.claim_type,
            claim_element_id=request.claim_element_id,
        )
        testimony_result = save_claim_testimony_record(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            claim_element_id=request.claim_element_id,
            claim_element_text=request.claim_element,
            raw_narrative=request.raw_narrative,
            event_date=request.event_date,
            actor=request.actor,
            act=request.act,
            target=request.target,
            harm=request.harm,
            firsthand_status=request.firsthand_status,
            source_confidence=request.source_confidence,
            metadata=testimony_metadata,
        )
        payload = {
            "user_id": resolved_user_id,
            "claim_type": request.claim_type,
            "testimony_result": testimony_result,
            "recorded": bool((testimony_result or {}).get("recorded", False)),
        }

    if request.include_post_save_review:
        payload["post_save_review"] = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                user_id=resolved_user_id,
                claim_type=request.claim_type,
                required_support_kinds=required_support_kinds,
                include_support_summary=request.include_support_summary,
                include_overview=request.include_overview,
                include_follow_up_plan=request.include_follow_up_plan,
                execute_follow_up=False,
            ),
        )

    return payload


def build_claim_support_document_payload(
    mediator: Any,
    request: ClaimSupportDocumentSaveRequest,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, request.user_id)
    required_support_kinds = (
        request.required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    save_claim_support_document = getattr(mediator, "save_claim_support_document", None)
    if not callable(save_claim_support_document):
        payload: Dict[str, Any] = {
            "user_id": resolved_user_id,
            "claim_type": request.claim_type,
            "recorded": False,
            "error": "document_intake_unavailable",
        }
    else:
        document_metadata = _merge_intake_summary_handoff_metadata(
            request.document_metadata,
            mediator,
            claim_type=request.claim_type,
            claim_element_id=request.claim_element_id,
        )
        document_result = save_claim_support_document(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            claim_element_id=request.claim_element_id,
            claim_element_text=request.claim_element,
            document_text=request.document_text,
            document_label=request.document_label,
            source_url=request.source_url,
            filename=request.filename,
            mime_type=request.mime_type,
            evidence_type=request.evidence_type,
            metadata=document_metadata,
        )
        payload = {
            "user_id": resolved_user_id,
            "claim_type": request.claim_type,
            "document_result": document_result,
            "recorded": bool((document_result or {}).get("record_id")),
        }

    if request.include_post_save_review:
        payload["post_save_review"] = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                user_id=resolved_user_id,
                claim_type=request.claim_type,
                required_support_kinds=required_support_kinds,
                include_support_summary=request.include_support_summary,
                include_overview=request.include_overview,
                include_follow_up_plan=request.include_follow_up_plan,
                execute_follow_up=False,
            ),
        )

    return payload


def build_claim_support_uploaded_document_payload(
    mediator: Any,
    *,
    user_id: Optional[str] = None,
    claim_type: Optional[str] = None,
    claim_element_id: Optional[str] = None,
    claim_element: Optional[str] = None,
    file_bytes: bytes,
    filename: Optional[str] = None,
    document_label: Optional[str] = None,
    source_url: Optional[str] = None,
    mime_type: Optional[str] = None,
    evidence_type: str = "document",
    document_metadata: Optional[Dict[str, Any]] = None,
    required_support_kinds: Optional[List[str]] = None,
    include_post_save_review: bool = True,
    include_support_summary: bool = True,
    include_overview: bool = True,
    include_follow_up_plan: bool = True,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, user_id)
    normalized_required_support_kinds = (
        required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    save_claim_support_document = getattr(mediator, "save_claim_support_document", None)
    if not callable(save_claim_support_document):
        payload: Dict[str, Any] = {
            "user_id": resolved_user_id,
            "claim_type": claim_type,
            "recorded": False,
            "error": "document_intake_unavailable",
        }
    else:
        merged_document_metadata = _merge_intake_summary_handoff_metadata(
            document_metadata,
            mediator,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
        )
        document_result = save_claim_support_document(
            claim_type=claim_type,
            user_id=resolved_user_id,
            claim_element_id=claim_element_id,
            claim_element_text=claim_element,
            document_text=None,
            document_bytes=file_bytes,
            document_label=document_label,
            source_url=source_url,
            filename=filename,
            mime_type=mime_type,
            evidence_type=evidence_type,
            metadata=merged_document_metadata,
        )
        payload = {
            "user_id": resolved_user_id,
            "claim_type": claim_type,
            "document_result": document_result,
            "recorded": bool((document_result or {}).get("record_id")),
        }

    if include_post_save_review:
        payload["post_save_review"] = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                user_id=resolved_user_id,
                claim_type=claim_type,
                required_support_kinds=normalized_required_support_kinds,
                include_support_summary=include_support_summary,
                include_overview=include_overview,
                include_follow_up_plan=include_follow_up_plan,
                execute_follow_up=False,
            ),
        )

    return payload


def build_claim_support_intake_summary_confirmation_payload(
    mediator: Any,
    request: ClaimSupportIntakeSummaryConfirmRequest,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, request.user_id)
    required_support_kinds = (
        request.required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    confirm_summary = getattr(mediator, "confirm_intake_summary", None)
    if not callable(confirm_summary):
        payload: Dict[str, Any] = {
            "user_id": resolved_user_id,
            "claim_type": request.claim_type,
            "confirmed": False,
            "error": "intake_summary_confirmation_unavailable",
        }
    else:
        confirmation_result = confirm_summary(
            confirmation_note=request.confirmation_note or "",
            confirmation_source=request.confirmation_source,
        )
        confirmation_record = (
            confirmation_result.get("complainant_summary_confirmation", {})
            if isinstance(confirmation_result, dict)
            else {}
        )
        payload = {
            "user_id": resolved_user_id,
            "claim_type": request.claim_type,
            "confirmation_result": confirmation_record,
            "confirmed": bool(confirmation_record.get("confirmed", False)),
        }

    if request.include_post_confirmation_review:
        payload["post_confirmation_review"] = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                user_id=resolved_user_id,
                claim_type=request.claim_type,
                required_support_kinds=required_support_kinds,
                include_support_summary=request.include_support_summary,
                include_overview=request.include_overview,
                include_follow_up_plan=request.include_follow_up_plan,
                execute_follow_up=False,
            ),
        )

    return payload


def build_claim_support_follow_up_execution_payload(
    mediator: Any,
    request: ClaimSupportFollowUpExecuteRequest,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, request.user_id)
    required_support_kinds = (
        request.required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    pre_execution_review: Optional[Dict[str, Any]] = None
    if request.include_post_execution_review:
        pre_execution_review = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                user_id=resolved_user_id,
                claim_type=request.claim_type,
                required_support_kinds=required_support_kinds,
                follow_up_cooldown_seconds=request.follow_up_cooldown_seconds,
                include_support_summary=request.include_support_summary,
                include_overview=request.include_overview,
                include_follow_up_plan=request.include_follow_up_plan,
                execute_follow_up=False,
                follow_up_support_kind=request.follow_up_support_kind,
                follow_up_max_tasks_per_claim=request.follow_up_max_tasks_per_claim,
            ),
        )

    follow_up_execution = mediator.execute_claim_follow_up_plan(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        support_kind=request.follow_up_support_kind,
        max_tasks_per_claim=request.follow_up_max_tasks_per_claim,
        cooldown_seconds=request.follow_up_cooldown_seconds,
        force=request.follow_up_force,
    )
    follow_up_execution_claims = (
        follow_up_execution.get("claims", {})
        if isinstance(follow_up_execution, dict)
        else {}
    )

    payload: Dict[str, Any] = {
        "user_id": resolved_user_id,
        "claim_type": request.claim_type,
        "required_support_kinds": required_support_kinds,
        "follow_up_support_kind": request.follow_up_support_kind,
        "follow_up_force": request.follow_up_force,
        "follow_up_execution": follow_up_execution_claims,
        "follow_up_execution_summary": {
            claim_name: _summarize_follow_up_execution_claim(claim_execution)
            for claim_name, claim_execution in follow_up_execution_claims.items()
            if isinstance(claim_execution, dict)
        },
    }
    handoff_metadata = _build_confirmed_intake_summary_handoff_metadata(mediator)
    if handoff_metadata:
        payload.update(handoff_metadata)

    if request.include_post_execution_review:
        post_execution_review = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                user_id=resolved_user_id,
                claim_type=request.claim_type,
                required_support_kinds=required_support_kinds,
                follow_up_cooldown_seconds=request.follow_up_cooldown_seconds,
                include_support_summary=request.include_support_summary,
                include_overview=request.include_overview,
                include_follow_up_plan=request.include_follow_up_plan,
                execute_follow_up=False,
                follow_up_support_kind=request.follow_up_support_kind,
                follow_up_max_tasks_per_claim=request.follow_up_max_tasks_per_claim,
            ),
        )
        payload["post_execution_review"] = post_execution_review
        pre_quality_claims = (
            (pre_execution_review or {}).get("claim_coverage_summary", {})
            if isinstance(pre_execution_review, dict)
            else {}
        )
        post_quality_claims = (
            post_execution_review.get("claim_coverage_summary", {})
            if isinstance(post_execution_review, dict)
            else {}
        )
        execution_quality_claims = payload.get("follow_up_execution_summary", {})
        payload["execution_quality_summary"] = {
            claim_name: _summarize_execution_quality_claim(
                pre_quality_claims.get(claim_name, {}),
                post_quality_claims.get(claim_name, {}),
                execution_quality_claims.get(claim_name, {}),
            )
            for claim_name in sorted(
                set(pre_quality_claims.keys())
                | set(post_quality_claims.keys())
                | set(execution_quality_claims.keys())
            )
        }

    return payload


def build_claim_support_manual_review_resolution_payload(
    mediator: Any,
    request: ClaimSupportManualReviewResolveRequest,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, request.user_id)
    required_support_kinds = (
        request.required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    resolution_result = mediator.resolve_claim_follow_up_manual_review(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        claim_element_id=request.claim_element_id,
        claim_element=request.claim_element,
        resolution_status=request.resolution_status,
        resolution_notes=request.resolution_notes,
        related_execution_id=request.related_execution_id,
        metadata=request.resolution_metadata,
    )

    payload: Dict[str, Any] = {
        "user_id": resolved_user_id,
        "claim_type": request.claim_type,
        "claim_element_id": request.claim_element_id,
        "claim_element": request.claim_element,
        "resolution_status": request.resolution_status,
        "resolution_notes": request.resolution_notes,
        "related_execution_id": request.related_execution_id,
        "resolution_result": resolution_result,
    }

    if request.include_post_resolution_review:
        payload["post_resolution_review"] = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                user_id=resolved_user_id,
                claim_type=request.claim_type,
                required_support_kinds=required_support_kinds,
                include_support_summary=request.include_support_summary,
                include_overview=request.include_overview,
                include_follow_up_plan=request.include_follow_up_plan,
                execute_follow_up=False,
            ),
        )

    return payload
