from pathlib import Path
import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from document_pipeline import DEFAULT_OUTPUT_DIR
from integrations.ipfs_datasets.storage import retrieve_bytes
from intake_status import (
    build_intake_case_review_summary,
    build_intake_status_summary,
    build_intake_warning_entries,
)
from workflow_phase_guidance import (
    humanize_workflow_priority_label,
    normalize_workflow_phase_recommended_actions,
    resolve_prioritized_workflow_phase,
)


FORMAL_COMPLAINT_DOCUMENT_REQUEST_EXAMPLE = {
    "district": "Northern District of California",
    "county": "San Francisco County",
    "plaintiff_names": ["Jane Doe"],
    "defendant_names": ["Acme Corporation"],
    "enable_agentic_optimization": True,
    "optimization_max_iterations": 1,
    "optimization_target_score": 0.95,
    "optimization_provider": "huggingface_router",
    "optimization_model_name": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
    "optimization_llm_config": {
        "base_url": "https://router.huggingface.co/v1",
        "headers": {
            "X-Title": "Complaint Generator"
        },
        "arch_router": {
            "enabled": True,
            "model": "katanemo/Arch-Router-1.5B",
            "context": "Complaint drafting, legal issue spotting, and filing packet generation.",
            "routes": {
                "legal_reasoning": "meta-llama/Llama-3.3-70B-Instruct",
                "drafting": "Qwen/Qwen3-Coder-480B-A35B-Instruct"
            }
        },
        "timeout": 45
    },
    "output_formats": ["txt", "packet"]
}


class ServiceRecipientDetail(BaseModel):
    recipient: Optional[str] = None
    method: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class AdditionalSignerDetail(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    firm: Optional[str] = None
    bar_number: Optional[str] = None
    contact: Optional[str] = None


class AffidavitExhibitDetail(BaseModel):
    label: Optional[str] = None
    title: Optional[str] = None
    link: Optional[str] = None
    summary: Optional[str] = None


class FormalComplaintDocumentRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": FORMAL_COMPLAINT_DOCUMENT_REQUEST_EXAMPLE})

    user_id: Optional[str] = None
    court_name: str = "United States District Court"
    district: str = ""
    county: Optional[str] = None
    division: Optional[str] = None
    court_header_override: Optional[str] = None
    case_number: Optional[str] = None
    lead_case_number: Optional[str] = None
    related_case_number: Optional[str] = None
    assigned_judge: Optional[str] = None
    courtroom: Optional[str] = None
    title_override: Optional[str] = None
    plaintiff_names: List[str] = Field(default_factory=list)
    defendant_names: List[str] = Field(default_factory=list)
    requested_relief: List[str] = Field(default_factory=list)
    jury_demand: bool = False
    jury_demand_text: Optional[str] = None
    signer_name: Optional[str] = None
    signer_title: Optional[str] = None
    signer_firm: Optional[str] = None
    signer_bar_number: Optional[str] = None
    signer_contact: Optional[str] = None
    additional_signers: List[AdditionalSignerDetail] = Field(default_factory=list)
    declarant_name: Optional[str] = None
    service_method: Optional[str] = None
    service_recipients: List[str] = Field(default_factory=list)
    service_recipient_details: List[ServiceRecipientDetail] = Field(default_factory=list)
    signature_date: Optional[str] = None
    verification_date: Optional[str] = None
    service_date: Optional[str] = None
    affidavit_title: Optional[str] = None
    affidavit_intro: Optional[str] = None
    affidavit_facts: List[str] = Field(default_factory=list)
    affidavit_supporting_exhibits: List[AffidavitExhibitDetail] = Field(default_factory=list)
    affidavit_include_complaint_exhibits: Optional[bool] = None
    affidavit_venue_lines: List[str] = Field(default_factory=list)
    affidavit_jurat: Optional[str] = None
    affidavit_notary_block: List[str] = Field(default_factory=list)
    enable_agentic_optimization: bool = False
    optimization_max_iterations: int = 2
    optimization_target_score: float = 0.9
    optimization_provider: Optional[str] = None
    optimization_model_name: Optional[str] = None
    optimization_llm_config: Dict[str, Any] = Field(default_factory=dict)
    optimization_persist_artifacts: bool = False
    output_dir: Optional[str] = None
    output_formats: List[str] = Field(default_factory=lambda: ["docx", "pdf"])


def _default_generated_documents_root() -> Path:
    return DEFAULT_OUTPUT_DIR.resolve()


def _is_allowed_download_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(_default_generated_documents_root())
        return True
    except ValueError:
        return False


def _build_download_url(path: str) -> Optional[str]:
    resolved = Path(path).resolve()
    if not _is_allowed_download_path(resolved):
        return None
    return f"/api/documents/download?path={resolved}"


def _build_optimization_trace_url(cid: str) -> str:
    return f"/api/documents/optimization-trace?cid={cid}"


def _build_optimization_trace_view_url(cid: str) -> str:
    return f"/document/optimization-trace?cid={cid}"


def _build_review_url(
    *,
    user_id: Optional[str] = None,
    claim_type: Optional[str] = None,
    section: Optional[str] = None,
) -> str:
    params = {}
    if user_id:
        params["user_id"] = user_id
    if claim_type:
        params["claim_type"] = claim_type
    if section:
        params["section"] = section
    query = urlencode(params)
    return f"/claim-support-review?{query}" if query else "/claim-support-review"


def _default_support_kind_for_section(section_key: Optional[str]) -> Optional[str]:
    mapping = {
        "summary_of_facts": "evidence",
        "exhibits": "evidence",
        "jurisdiction_and_venue": "authority",
        "claims_for_relief": "authority",
    }
    normalized = str(section_key or "").strip().lower()
    return mapping.get(normalized)


def _build_review_intent(
    *,
    user_id: Optional[str] = None,
    claim_type: Optional[str] = None,
    section: Optional[str] = None,
    follow_up_support_kind: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "claim_type": claim_type,
        "section": section,
        "follow_up_support_kind": follow_up_support_kind,
        "review_url": _build_review_url(user_id=user_id, claim_type=claim_type, section=section),
    }


def _append_review_query_params(review_url: str, **params: Optional[str]) -> str:
    normalized_url = str(review_url or "").strip() or "/claim-support-review"
    split = urlsplit(normalized_url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    for key, value in params.items():
        text = str(value or "").strip()
        if text:
            query[key] = text
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _resolve_document_review_url(
    *,
    user_id: Optional[str],
    dashboard_url: str,
    claim_review_map: Dict[str, Dict[str, Any]],
    section_review_map: Dict[str, Dict[str, Any]],
    claim_type: Optional[str] = None,
    section_key: Optional[str] = None,
) -> str:
    normalized_claim_type = str(claim_type or "").strip()
    normalized_section_key = str(section_key or "").strip()

    if normalized_section_key:
        section_target = section_review_map.get(normalized_section_key) or {}
        section_context = section_target.get("review_context") if isinstance(section_target.get("review_context"), dict) else {}
        return str(
            section_target.get("review_url")
            or _build_review_url(
                user_id=user_id,
                claim_type=normalized_claim_type or section_context.get("claim_type"),
                section=normalized_section_key,
            )
        )

    if normalized_claim_type:
        claim_target = claim_review_map.get(normalized_claim_type) or {}
        return str(
            claim_target.get("review_url")
            or _build_review_url(user_id=user_id, claim_type=normalized_claim_type)
        )

    return dashboard_url


def _claim_type_in_case_summary_queue(
    intake_case_summary: Dict[str, Any],
    *,
    claim_type: Optional[str],
    summary_key: str,
) -> bool:
    normalized_claim_type = str(claim_type or "").strip()
    if not normalized_claim_type:
        return False
    summary = intake_case_summary.get(summary_key) if isinstance(intake_case_summary.get(summary_key), dict) else {}
    for item in summary.get("claims") or []:
        if str((item or {}).get("claim_type") or "").strip() == normalized_claim_type:
            return True
    return False


def _build_document_review_workflow_phase_priority(
    workflow_phase_plan: Dict[str, Any],
    *,
    user_id: Optional[str],
    default_claim_type: Optional[str],
    dashboard_url: str,
    section_review_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    prioritized_phase_context = resolve_prioritized_workflow_phase(workflow_phase_plan)
    prioritized_phase_name = str(prioritized_phase_context.get("phase_name") or "").strip()
    prioritized_phase = dict(prioritized_phase_context.get("phase") or {})
    if not prioritized_phase_name or not prioritized_phase:
        return {}

    prioritized_status = str(prioritized_phase_context.get("status") or "ready").strip().lower() or "ready"
    recommended_actions = list(prioritized_phase_context.get("recommended_actions") or [])
    primary_recommended_action = recommended_actions[0] if recommended_actions else ""

    if prioritized_phase_name == "graph_analysis":
        section_key = "summary_of_facts"
        section_target = section_review_map.get(section_key) or {}
        section_context = section_target.get("review_context") if isinstance(section_target.get("review_context"), dict) else {}
        action_url = _append_review_query_params(
            str(
                section_target.get("review_url")
                or _build_review_url(
                    user_id=user_id,
                    claim_type=section_context.get("claim_type") or default_claim_type,
                    section=section_key,
                )
            ),
            follow_up_support_kind=_default_support_kind_for_section(section_key),
        )
        title = (
            "Graph analysis is aligned for drafting"
            if prioritized_status == "ready"
            else "Resolve graph analysis before drafting"
        )
        action_label = "Review graph inputs"
    elif prioritized_phase_name == "document_generation":
        section_key = "claims_for_relief"
        section_target = section_review_map.get(section_key) or {}
        section_context = section_target.get("review_context") if isinstance(section_target.get("review_context"), dict) else {}
        title = (
            "Drafting is aligned with workflow guidance"
            if prioritized_status == "ready"
            else "Resolve drafting readiness before filing"
        )
        action_label = "Open Review Dashboard" if prioritized_status == "ready" else "Review drafting readiness"
        action_url = dashboard_url if prioritized_status == "ready" else _append_review_query_params(
            str(
                section_target.get("review_url")
                or _build_review_url(
                    user_id=user_id,
                    claim_type=section_context.get("claim_type") or default_claim_type,
                    section=section_key,
                )
            ),
            follow_up_support_kind=_default_support_kind_for_section(section_key),
        )
    else:
        return {}

    return {
        "phase_name": prioritized_phase_name,
        "status": prioritized_status,
        "title": title,
        "description": str(prioritized_phase.get("summary") or "").strip()
        or "Workflow phase guidance still identifies a higher-priority step before drafting.",
        "action_label": action_label,
        "action_url": action_url,
        "action_kind": "link",
        "dashboard_url": dashboard_url,
        "recommended_actions": recommended_actions,
        "chip_labels": [
            f"workflow phase: {humanize_workflow_priority_label(prioritized_phase_name)}",
            f"phase status: {humanize_workflow_priority_label(prioritized_status)}",
            *([f"recommended action: {primary_recommended_action}"] if primary_recommended_action else []),
        ],
    }


def _build_document_review_workflow_priority(
    *,
    intake_status: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
    workflow_phase_plan: Dict[str, Any],
    user_id: Optional[str],
    default_claim_type: Optional[str],
    dashboard_url: str,
    claim_review_map: Dict[str, Dict[str, Any]],
    section_review_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    next_action = intake_status.get("next_action") if isinstance(intake_status.get("next_action"), dict) else {}
    if not next_action and isinstance(intake_case_summary.get("next_action"), dict):
        next_action = intake_case_summary.get("next_action") or {}

    action = str(next_action.get("action") or "").strip().lower()
    if not action:
        return _build_document_review_workflow_phase_priority(
            workflow_phase_plan,
            user_id=user_id,
            default_claim_type=default_claim_type,
            dashboard_url=dashboard_url,
            section_review_map=section_review_map,
        )

    claim_type = str(next_action.get("claim_type") or default_claim_type or "").strip()
    claim_element_id = str(next_action.get("claim_element_id") or "").strip()
    blockers = next_action.get("intake_blockers") if isinstance(next_action.get("intake_blockers"), list) else []
    contradictions = int((intake_case_summary.get("contradiction_summary") or {}).get("count") or 0)
    question_candidates = int((intake_case_summary.get("question_candidate_summary") or {}).get("count") or 0)
    packet_summary = (
        intake_case_summary.get("claim_support_packet_summary")
        if isinstance(intake_case_summary.get("claim_support_packet_summary"), dict)
        else {}
    )
    base_claim_url = _resolve_document_review_url(
        user_id=user_id,
        dashboard_url=dashboard_url,
        claim_review_map=claim_review_map,
        section_review_map=section_review_map,
        claim_type=claim_type,
    )

    status = "warning"
    title = "Review workflow priority before drafting"
    description = "The review dashboard still has a higher-priority step than drafting for this matter."
    action_label = "Open Review Dashboard"
    action_url = dashboard_url
    action_kind = "link"

    if action == "confirm_intake_summary":
        title = "Confirm intake summary before drafting"
        description = "The current intake summary snapshot still needs complainant confirmation before drafting should continue."
        action_label = "Confirm intake summary"
        action_kind = "button"
    elif action == "validate_promoted_support":
        title = "Validate promoted support before drafting"
        description = "Promoted testimony or document support still needs validation before the draft can rely on it."
        action_label = "Review promoted updates"
        action_url = _append_review_query_params(
            base_claim_url,
            alignment_task_update_filter="pending_review",
            alignment_task_update_sort="pending_review_first",
        )
    elif action == "resolve_support_conflicts":
        title = "Resolve support conflicts before drafting"
        description = "Manual-review conflicts are still blocking evidence confidence for a draft-ready complaint."
        action_label = "Review manual conflicts"
        claim_queue_url = base_claim_url
        if _claim_type_in_case_summary_queue(
            intake_case_summary,
            claim_type=claim_type,
            summary_key="manual_review_claim_summary",
        ):
            claim_queue_url = _append_review_query_params(
                claim_queue_url,
                alignment_task_update_filter="manual_review",
                alignment_task_update_sort="manual_review_first",
            )
        elif _claim_type_in_case_summary_queue(
            intake_case_summary,
            claim_type=claim_type,
            summary_key="pending_review_claim_summary",
        ):
            claim_queue_url = _append_review_query_params(
                claim_queue_url,
                alignment_task_update_filter="pending_review",
                alignment_task_update_sort="pending_review_first",
            )
        action_url = _append_review_query_params(
            claim_queue_url,
            alignment_task_update_filter="manual_review",
            alignment_task_update_sort="manual_review_first",
        )
    elif action == "fill_evidence_gaps":
        title = "Fill evidence gaps before drafting"
        description = "The current backend priority still points to missing support for a claim element in this complaint."
        action_label = "Review evidence task"
        action_url = _append_review_query_params(
            base_claim_url,
            follow_up_support_kind="evidence",
            alignment_task_update_filter="active",
        )
    elif action in {"address_gaps", "continue_denoising", "build_knowledge_graph"}:
        if action == "address_gaps":
            title = "Resolve intake gaps before drafting"
            description = "Intake still has unresolved factual gaps that can weaken the document if drafting continues too early."
            action_label = "Review intake gaps"
        elif action == "continue_denoising":
            title = "Continue intake denoising before drafting"
            description = "Contradictions or unanswered intake questions still need another denoising pass before the document stabilizes."
            action_label = "Review denoising queue"
        else:
            title = "Review intake graph inputs before drafting"
            description = "The intake graph inputs are not complete enough to support a stable draft handoff yet."
            action_label = "Review intake graph inputs"
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type,
                section_key="summary_of_facts",
            ),
            follow_up_support_kind=_default_support_kind_for_section("summary_of_facts"),
            alignment_task_update_filter="active",
        )
    elif action == "build_dependency_graph":
        title = "Review dependency inputs before drafting"
        description = "Cross-section dependency mapping is still incomplete, so the case theory may not be stable enough for drafting."
        action_label = "Review dependency inputs"
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type,
                section_key="chronology",
            ),
            follow_up_support_kind="evidence",
            alignment_task_update_filter="active",
        )
    elif action in {"build_legal_graph", "perform_neurosymbolic_matching"}:
        title = (
            "Review legal graph inputs before drafting"
            if action == "build_legal_graph"
            else "Review matching inputs before drafting"
        )
        description = (
            "Formalization still needs the legal graph that organizes statutes and requirements for this complaint."
            if action == "build_legal_graph"
            else "Formal claim-to-law matching is still pending, so the draft may outrun the current legal targeting."
        )
        action_label = (
            "Review legal graph inputs"
            if action == "build_legal_graph"
            else "Review matching inputs"
        )
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type,
                section_key="claims_for_relief",
            ),
            follow_up_support_kind=_default_support_kind_for_section("claims_for_relief"),
            alignment_task_update_filter="manual_review",
            alignment_task_update_sort="manual_review_first",
        )
    elif action == "build_claim_support_packets":
        title = "Build support packets before drafting"
        description = "Evidence has been collected, but the packet-building step still needs to run before the draft can rely on those signals."
        action_label = "Build support packets"
        action_url = _append_review_query_params(
            base_claim_url,
            follow_up_support_kind="evidence",
            alignment_task_update_filter="active",
        )
    elif action == "complete_evidence":
        status = "ready"
        title = "Evidence is ready for formal drafting"
        description = "The backend priority has advanced to document drafting, so continuing here is consistent with the current workflow."
    elif action == "generate_formal_complaint":
        status = "ready"
        title = "Drafting is the current workflow priority"
        description = "The backend priority already points to formal complaint generation, so you can continue drafting here."
    elif action == "complete_formalization":
        status = "ready"
        title = "Formalization is complete"
        description = "Current workflow signals do not show a higher-priority review step blocking this draft."

    chip_labels = [f"recommended action: {action}"]
    if claim_type:
        chip_labels.append(f"focus claim: {humanize_workflow_priority_label(claim_type)}")
    if claim_element_id:
        chip_labels.append(f"focus element: {claim_element_id}")
    if blockers:
        chip_labels.append(f"blockers: {len([item for item in blockers if str(item).strip()])}")
    if contradictions > 0:
        chip_labels.append(f"contradictions: {contradictions}")
    if question_candidates > 0:
        chip_labels.append(f"question candidates: {question_candidates}")
    if action == "resolve_support_conflicts":
        chip_labels.append(
            f"packet escalations: {int(packet_summary.get('claim_support_reviewable_escalation_count') or 0)}"
        )
    if action in {"generate_formal_complaint", "complete_evidence"}:
        chip_labels.append(
            f"proof readiness: {float(packet_summary.get('proof_readiness_score') or 0):.2f}"
        )

    return {
        "status": status,
        "title": title,
        "description": description,
        "action_label": action_label,
        "action_url": action_url,
        "action_kind": action_kind,
        "dashboard_url": dashboard_url,
        "chip_labels": chip_labels,
    }


def _build_checklist_intake_status(intake_status: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_status, dict) or not intake_status:
        return {}
    blockers = intake_status.get("blockers")
    blocker_list = [str(item).strip() for item in blockers] if isinstance(blockers, list) else []
    contradictions = intake_status.get("contradictions")
    contradiction_list = contradictions if isinstance(contradictions, list) else []
    next_action = intake_status.get("next_action") if isinstance(intake_status.get("next_action"), dict) else {}
    primary_validation_target = (
        intake_status.get("primary_validation_target")
        if isinstance(intake_status.get("primary_validation_target"), dict)
        else {}
    )
    return {
        "score": float(intake_status.get("score") or 0.0),
        "ready_to_advance": bool(intake_status.get("ready_to_advance", False)),
        "remaining_gap_count": int(intake_status.get("remaining_gap_count") or 0),
        "contradiction_count": int(intake_status.get("contradiction_count") or len(contradiction_list)),
        "blockers": blocker_list,
        "contradictions": contradiction_list[:2],
        "next_action": next_action,
        "primary_validation_target": primary_validation_target,
    }


def _merge_claim_temporal_gap_summary(
    intake_case_summary: Dict[str, Any],
    document_optimization: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = dict(intake_case_summary or {}) if isinstance(intake_case_summary, dict) else {}
    optimization_payload = document_optimization if isinstance(document_optimization, dict) else {}
    intake_priorities = (
        optimization_payload.get("intake_priorities")
        if isinstance(optimization_payload.get("intake_priorities"), dict)
        else {}
    )
    claim_temporal_gap_summary = intake_priorities.get("claim_temporal_gap_summary")
    if not isinstance(claim_temporal_gap_summary, list) or not claim_temporal_gap_summary:
        return merged
    merged["claim_temporal_gap_count"] = int(intake_priorities.get("claim_temporal_gap_count") or 0)
    merged["claim_temporal_gap_summary"] = [
        dict(item)
        for item in claim_temporal_gap_summary
        if isinstance(item, dict)
    ]
    return merged


def _annotate_workflow_priority_with_temporal_gap_summary(
    workflow_priority: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(workflow_priority, dict) or not workflow_priority:
        return workflow_priority
    claim_temporal_gap_count = int(intake_case_summary.get("claim_temporal_gap_count") or 0)
    claim_temporal_gap_summary = (
        intake_case_summary.get("claim_temporal_gap_summary")
        if isinstance(intake_case_summary.get("claim_temporal_gap_summary"), list)
        else []
    )
    if claim_temporal_gap_count <= 0 or not claim_temporal_gap_summary:
        return workflow_priority
    chip_labels = list(workflow_priority.get("chip_labels") or [])
    chip_labels.append(f"claim chronology gaps: {claim_temporal_gap_count}")
    first_claim_type = str((claim_temporal_gap_summary[0] or {}).get("claim_type") or "").strip()
    if first_claim_type:
        chip_labels.append(f"chronology focus: {humanize_workflow_priority_label(first_claim_type)}")
    workflow_priority["chip_labels"] = chip_labels
    return workflow_priority


def _merge_warning_entries(existing: Any, additions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    base = existing if isinstance(existing, list) else []
    merged: List[Dict[str, Any]] = [item for item in base if isinstance(item, dict)]
    seen = {
        (
            str(item.get("code") or "").strip(),
            str(item.get("message") or "").strip(),
            str(item.get("severity") or "").strip(),
        )
        for item in merged
    }
    for item in additions:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("code") or "").strip(),
            str(item.get("message") or "").strip(),
            str(item.get("severity") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _annotate_artifacts_with_download_urls(payload: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(artifacts, dict):
        return payload
    for artifact in artifacts.values():
        if not isinstance(artifact, dict):
            continue
        artifact_path = artifact.get("path")
        if artifact_path:
            download_url = _build_download_url(str(artifact_path))
            if download_url:
                artifact["download_url"] = download_url
    return payload


def _section_claim_types(section_key: str, claim_types: List[str]) -> List[str]:
    claim_oriented_sections = {
        "summary_of_facts",
        "claims_for_relief",
        "exhibits",
        "requested_relief",
    }
    return claim_types if section_key in claim_oriented_sections else []


def _annotate_checklist_review_links(
    payload: Dict[str, Any],
    *,
    dashboard_url: str,
    claim_review_map: Dict[str, Dict[str, Any]],
    section_review_map: Dict[str, Dict[str, Any]],
    default_review_intent: Dict[str, Any],
    intake_status: Dict[str, Any],
) -> Dict[str, Any]:
    checklist_targets = []
    top_level = payload.get("filing_checklist") if isinstance(payload.get("filing_checklist"), list) else []
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    draft_level = draft.get("filing_checklist") if isinstance(draft.get("filing_checklist"), list) else []
    if top_level:
        checklist_targets.append(top_level)
    if draft_level and draft_level is not top_level:
        checklist_targets.append(draft_level)

    for checklist in checklist_targets:
        for item in checklist:
            if not isinstance(item, dict):
                continue
            scope = str(item.get("scope") or "").strip().lower()
            key = str(item.get("key") or "").strip()
            target = None
            if scope == "claim":
                target = claim_review_map.get(key)
            elif scope == "section":
                target = section_review_map.get(key)
            if target:
                item["review_url"] = target.get("review_url")
                item["review_context"] = target.get("review_context")
                item["review_intent"] = target.get("review_intent")
            else:
                item["review_url"] = dashboard_url
                item["review_context"] = {"user_id": default_review_intent.get("user_id")}
                item["review_intent"] = dict(default_review_intent)
            if str(item.get("status") or "").strip().lower() in {"warning", "blocked"}:
                checklist_intake_status = _build_checklist_intake_status(intake_status)
                if checklist_intake_status:
                    item["intake_status"] = checklist_intake_status
    return payload


def _annotate_review_links(payload: Dict[str, Any], *, mediator: Any, user_id: Optional[str]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    source_context = draft.get("source_context") if isinstance(draft.get("source_context"), dict) else {}
    resolved_user_id = user_id or source_context.get("user_id")
    drafting_readiness = payload.get("drafting_readiness") if isinstance(payload.get("drafting_readiness"), dict) else {}
    claim_entries = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []
    section_entries = drafting_readiness.get("sections") if isinstance(drafting_readiness.get("sections"), dict) else {}
    dashboard_url = _build_review_url(user_id=resolved_user_id)
    default_review_intent = _build_review_intent(user_id=resolved_user_id)
    intake_status = build_intake_status_summary(mediator)
    intake_case_summary = build_intake_case_review_summary(mediator)
    intake_warning_entries = build_intake_warning_entries(intake_status)
    intake_summary_handoff = {}
    if isinstance(intake_status.get("intake_summary_handoff"), dict) and intake_status.get("intake_summary_handoff"):
        intake_summary_handoff = dict(intake_status["intake_summary_handoff"])
    elif isinstance(intake_case_summary.get("intake_summary_handoff"), dict) and intake_case_summary.get("intake_summary_handoff"):
        intake_summary_handoff = dict(intake_case_summary["intake_summary_handoff"])

    claim_links = []
    claim_types = []
    claim_review_map: Dict[str, Dict[str, Any]] = {}
    for claim in claim_entries:
        if not isinstance(claim, dict):
            continue
        claim_type = str(claim.get("claim_type") or "").strip()
        if not claim_type:
            continue
        claim_types.append(claim_type)
        claim_review_url = _build_review_url(user_id=resolved_user_id, claim_type=claim_type)
        claim_review_intent = _build_review_intent(
            user_id=resolved_user_id,
            claim_type=claim_type,
        )
        claim["review_url"] = claim_review_url
        claim["review_context"] = {
            "user_id": resolved_user_id,
            "claim_type": claim_type,
        }
        claim["review_intent"] = claim_review_intent
        if str(claim.get("status") or "").strip().lower() in {"warning", "blocked"}:
            claim["warnings"] = _merge_warning_entries(claim.get("warnings"), intake_warning_entries)
        claim_review_map[claim_type] = {
            "review_url": claim_review_url,
            "review_context": claim["review_context"],
            "review_intent": claim_review_intent,
        }
        claim_links.append(
            {
                "claim_type": claim_type,
                "review_url": claim_review_url,
                "review_intent": claim_review_intent,
            }
        )

    section_links = []
    section_review_map: Dict[str, Dict[str, Any]] = {}
    for section_key, section in section_entries.items():
        if not isinstance(section, dict):
            continue
        resolved_section_key = str(section_key or "").strip()
        if not resolved_section_key:
            continue
        related_claim_types = _section_claim_types(resolved_section_key, claim_types)
        primary_claim_type = related_claim_types[0] if len(related_claim_types) == 1 else None
        section_review_url = _build_review_url(
            user_id=resolved_user_id,
            claim_type=primary_claim_type,
            section=resolved_section_key,
        )
        section_review_intent = _build_review_intent(
            user_id=resolved_user_id,
            claim_type=primary_claim_type,
            section=resolved_section_key,
            follow_up_support_kind=_default_support_kind_for_section(resolved_section_key),
        )
        section_claim_links = [
            {
                "claim_type": claim_type,
                "review_url": _build_review_url(
                    user_id=resolved_user_id,
                    claim_type=claim_type,
                    section=resolved_section_key,
                ),
                "review_intent": _build_review_intent(
                    user_id=resolved_user_id,
                    claim_type=claim_type,
                    section=resolved_section_key,
                    follow_up_support_kind=_default_support_kind_for_section(resolved_section_key),
                ),
            }
            for claim_type in related_claim_types
        ]
        review_context = {
            "user_id": resolved_user_id,
            "section": resolved_section_key,
            "claim_type": primary_claim_type,
        }
        section["review_url"] = section_review_url
        section["review_context"] = review_context
        section["review_intent"] = section_review_intent
        if str(section.get("status") or "").strip().lower() in {"warning", "blocked"}:
            section["warnings"] = _merge_warning_entries(section.get("warnings"), intake_warning_entries)
        if section_claim_links:
            section["claim_links"] = section_claim_links
        section_review_map[resolved_section_key] = {
            "review_url": section_review_url,
            "review_context": review_context,
            "review_intent": section_review_intent,
        }
        section_links.append(
            {
                "section_key": resolved_section_key,
                "title": section.get("title") or resolved_section_key,
                "review_url": section_review_url,
                "review_context": review_context,
                "review_intent": section_review_intent,
                "claim_links": section_claim_links,
            }
        )

    preferred_section = None
    for section_key, section in section_entries.items():
        if not isinstance(section, dict):
            continue
        if str(section.get("status") or "").lower() in {"warning", "blocked"}:
            preferred_section = str(section_key or "").strip() or None
            break

    preferred_claim_type = None
    for claim in claim_entries:
        if not isinstance(claim, dict):
            continue
        if str(claim.get("status") or "").lower() in {"warning", "blocked"}:
            preferred_claim_type = str(claim.get("claim_type") or "").strip() or None
            break

    if str(drafting_readiness.get("status") or "").strip().lower() in {"warning", "blocked"}:
        drafting_readiness["warnings"] = _merge_warning_entries(
            drafting_readiness.get("warnings"),
            intake_warning_entries,
        )

    document_optimization = payload.get("document_optimization")
    intake_case_summary = _merge_claim_temporal_gap_summary(intake_case_summary, document_optimization)
    if isinstance(document_optimization, dict):
        optimization_intake_status = document_optimization.get("intake_status")
        if isinstance(optimization_intake_status, dict) and optimization_intake_status and not intake_status:
            document_optimization["intake_status"] = dict(optimization_intake_status)
        else:
            document_optimization["intake_status"] = dict(intake_status)

        optimization_case_summary = document_optimization.get("intake_case_summary")
        if intake_case_summary:
            document_optimization["intake_case_summary"] = dict(intake_case_summary)
        elif isinstance(optimization_case_summary, dict) and optimization_case_summary:
            document_optimization["intake_case_summary"] = dict(optimization_case_summary)

        optimization_constraints = document_optimization.get("intake_constraints")
        if intake_warning_entries:
            document_optimization["intake_constraints"] = list(intake_warning_entries)
        elif isinstance(optimization_constraints, list) and optimization_constraints:
            document_optimization["intake_constraints"] = list(optimization_constraints)

        trace_storage = document_optimization.get("trace_storage")
        trace_storage = trace_storage if isinstance(trace_storage, dict) else {}
        trace_cid = str(trace_storage.get("cid") or document_optimization.get("artifact_cid") or "").strip()
        if trace_cid:
            document_optimization["trace_download_url"] = _build_optimization_trace_url(trace_cid)
            document_optimization["trace_view_url"] = _build_optimization_trace_view_url(trace_cid)

    workflow_phase_plan = (
        drafting_readiness.get("workflow_phase_plan")
        if isinstance(drafting_readiness.get("workflow_phase_plan"), dict)
        else {}
    )
    workflow_phase_priority = _build_document_review_workflow_phase_priority(
        workflow_phase_plan,
        user_id=resolved_user_id,
        default_claim_type=preferred_claim_type,
        dashboard_url=dashboard_url,
        section_review_map=section_review_map,
    )
    workflow_priority = _build_document_review_workflow_priority(
        intake_status=intake_status,
        intake_case_summary=intake_case_summary,
        workflow_phase_plan=workflow_phase_plan,
        user_id=resolved_user_id,
        default_claim_type=preferred_claim_type,
        dashboard_url=dashboard_url,
        claim_review_map=claim_review_map,
        section_review_map=section_review_map,
    )
    workflow_priority = _annotate_workflow_priority_with_temporal_gap_summary(
        workflow_priority,
        intake_case_summary,
    )

    payload["review_links"] = {
        "dashboard_url": dashboard_url,
        "claims": claim_links,
        "sections": section_links,
        "intake_status": intake_status,
        "intake_case_summary": intake_case_summary,
        "recommended_next_action": (
            str((intake_status.get("next_action") or {}).get("action") or "")
            if isinstance(intake_status.get("next_action"), dict)
            else ""
        ),
        "workflow_priority": workflow_priority,
        "workflow_phase_priority": workflow_phase_priority,
        "primary_validation_target": (
            dict(intake_status.get("primary_validation_target"))
            if isinstance(intake_status.get("primary_validation_target"), dict)
            else {}
        ),
    }
    payload["review_intent"] = _build_review_intent(
        user_id=resolved_user_id,
        claim_type=preferred_claim_type,
        section=preferred_section,
        follow_up_support_kind=_default_support_kind_for_section(preferred_section),
    )
    if intake_summary_handoff:
        payload["intake_summary_handoff"] = intake_summary_handoff
        document_optimization = payload.get("document_optimization")
        if isinstance(document_optimization, dict):
            document_optimization["intake_summary_handoff"] = dict(intake_summary_handoff)
    return _annotate_checklist_review_links(
        payload,
        dashboard_url=dashboard_url,
        claim_review_map=claim_review_map,
        section_review_map=section_review_map,
        default_review_intent=payload["review_intent"],
        intake_status=payload["review_links"]["intake_status"],
    )


def create_document_router(mediator: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/api/documents/formal-complaint")
    async def build_formal_complaint_document(
        request: FormalComplaintDocumentRequest,
    ) -> Dict[str, Any]:
        if not request.output_formats:
            raise HTTPException(status_code=400, detail="At least one output format is required")
        build_kwargs = dict(
            user_id=request.user_id,
            court_name=request.court_name,
            district=request.district,
            county=request.county,
            division=request.division,
            court_header_override=request.court_header_override,
            case_number=request.case_number,
            lead_case_number=request.lead_case_number,
            related_case_number=request.related_case_number,
            assigned_judge=request.assigned_judge,
            courtroom=request.courtroom,
            title_override=request.title_override,
            plaintiff_names=request.plaintiff_names,
            defendant_names=request.defendant_names,
            requested_relief=request.requested_relief,
            jury_demand=request.jury_demand,
            jury_demand_text=request.jury_demand_text,
            signer_name=request.signer_name,
            signer_title=request.signer_title,
            signer_firm=request.signer_firm,
            signer_bar_number=request.signer_bar_number,
            signer_contact=request.signer_contact,
            additional_signers=[detail.model_dump(exclude_none=True) for detail in request.additional_signers],
            declarant_name=request.declarant_name,
            service_method=request.service_method,
            service_recipients=request.service_recipients,
            service_recipient_details=[detail.model_dump(exclude_none=True) for detail in request.service_recipient_details],
            signature_date=request.signature_date,
            verification_date=request.verification_date,
            service_date=request.service_date,
            affidavit_title=request.affidavit_title,
            affidavit_intro=request.affidavit_intro,
            affidavit_facts=request.affidavit_facts,
            affidavit_supporting_exhibits=[detail.model_dump(exclude_none=True) for detail in request.affidavit_supporting_exhibits],
            affidavit_include_complaint_exhibits=request.affidavit_include_complaint_exhibits,
            affidavit_venue_lines=request.affidavit_venue_lines,
            affidavit_jurat=request.affidavit_jurat,
            affidavit_notary_block=request.affidavit_notary_block,
            enable_agentic_optimization=request.enable_agentic_optimization,
            optimization_max_iterations=request.optimization_max_iterations,
            optimization_target_score=request.optimization_target_score,
            optimization_provider=request.optimization_provider,
            optimization_model_name=request.optimization_model_name,
            optimization_persist_artifacts=request.optimization_persist_artifacts,
            output_dir=request.output_dir,
            output_formats=request.output_formats,
        )
        if request.optimization_llm_config:
            build_kwargs["optimization_llm_config"] = request.optimization_llm_config
        payload = mediator.build_formal_complaint_document_package(**build_kwargs)
        payload = _annotate_artifacts_with_download_urls(payload)
        return _annotate_review_links(payload, mediator=mediator, user_id=request.user_id)

    @router.get("/api/documents/download")
    async def download_generated_document(path: str = Query(...)) -> FileResponse:
        file_path = Path(path).resolve()
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Generated document not found")
        if not _is_allowed_download_path(file_path):
            raise HTTPException(status_code=403, detail="Requested path is outside the generated documents directory")
        return FileResponse(path=str(file_path), filename=file_path.name)

    @router.get("/api/documents/optimization-trace")
    async def retrieve_optimization_trace(cid: str = Query(...)) -> Dict[str, Any]:
        trace_result = retrieve_bytes(cid)
        status = str(trace_result.get("status") or "")
        if status == "unavailable":
            raise HTTPException(
                status_code=503,
                detail=trace_result.get("error") or "Optimization trace backend unavailable",
            )
        if status != "available":
            error_text = str(trace_result.get("error") or "Optimization trace could not be retrieved")
            status_code = 404 if "not found" in error_text.lower() or "unknown cid" in error_text.lower() else 502
            raise HTTPException(status_code=status_code, detail=error_text)

        data = trace_result.get("data")
        payload_bytes = data if isinstance(data, (bytes, bytearray)) else bytes(str(data or ""), "utf-8")
        try:
            trace_payload = json.loads(payload_bytes.decode("utf-8")) if payload_bytes else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=f"Optimization trace is not valid JSON: {exc}") from exc

        return {
            "status": "available",
            "cid": cid,
            "size": int(trace_result.get("size") or len(payload_bytes)),
            "trace": trace_payload,
        }

    return router


def attach_document_routes(app: FastAPI, mediator: Any) -> FastAPI:
    app.include_router(create_document_router(mediator))
    return app
