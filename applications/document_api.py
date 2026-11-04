from pathlib import Path
import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from document_pipeline import DEFAULT_OUTPUT_DIR, _build_claim_checklist_chip_labels as _pipeline_claim_chip_labels
from .fastapi_compat import attach_router_routes
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
    email_timeline_handoff_path: Optional[str] = None
    email_authority_enrichment_path: Optional[str] = None
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


def _dedupe_text_values(values: Any) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for value in values if isinstance(values, list) else []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


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
    intake_case_summary: Optional[Dict[str, Any]] = None,
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

    temporal_issue_registry_summary = (
        intake_case_summary.get("temporal_issue_registry_summary")
        if isinstance(intake_case_summary, dict) and isinstance(intake_case_summary.get("temporal_issue_registry_summary"), dict)
        else {}
    )
    unresolved_registry_temporal_issue_count = int(temporal_issue_registry_summary.get("unresolved_count") or 0)
    resolved_temporal_issue_count = int(temporal_issue_registry_summary.get("resolved_count") or 0)
    chip_labels = [
        f"workflow phase: {humanize_workflow_priority_label(prioritized_phase_name)}",
        f"phase status: {humanize_workflow_priority_label(prioritized_status)}",
        *([f"recommended action: {primary_recommended_action}"] if primary_recommended_action else []),
    ]
    prioritized_signals = dict(prioritized_phase_context.get("signals") or {})
    unresolved_temporal_issue_count = max(
        int(prioritized_signals.get("unresolved_temporal_issue_count") or 0),
        unresolved_registry_temporal_issue_count,
    )
    missing_proof_artifact_count = int(prioritized_signals.get("missing_proof_artifact_count") or 0)
    if unresolved_temporal_issue_count > 0:
        chip_labels.append(f"unresolved chronology issues: {unresolved_temporal_issue_count}")
    if resolved_temporal_issue_count > 0:
        chip_labels.append(f"resolved chronology issues: {resolved_temporal_issue_count}")
    if missing_proof_artifact_count > 0:
        chip_labels.append(f"missing proof artifacts: {missing_proof_artifact_count}")

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
        "chip_labels": chip_labels,
    }


def _build_document_review_workflow_priority(
    *,
    intake_status: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
    workflow_phase_plan: Dict[str, Any],
    document_provenance_summary: Dict[str, Any],
    user_id: Optional[str],
    default_claim_type: Optional[str],
    dashboard_url: str,
    claim_review_map: Dict[str, Dict[str, Any]],
    section_review_map: Dict[str, Dict[str, Any]],
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
        focus_section = str(document_grounding_improvement_next_action.get("focus_section") or "factual_allegations").strip() or "factual_allegations"
        claim_type = str(document_grounding_improvement_next_action.get("claim_type") or default_claim_type or "").strip()
        preferred_support_kind = str(document_grounding_improvement_next_action.get("preferred_support_kind") or "").strip()
        suggested_support_kind = str(document_grounding_improvement_next_action.get("suggested_support_kind") or "").strip()
        suggested_claim_element_id = str(document_grounding_improvement_next_action.get("suggested_claim_element_id") or "").strip()
        attempted_support_kind = str(document_grounding_lane_outcome_summary.get("attempted_support_kind") or "").strip()
        learned_support_kind = str(document_grounding_lane_outcome_summary.get("recommended_future_support_kind") or "").strip()
        if not suggested_claim_element_id:
            suggested_claim_element_id = str(document_grounding_lane_outcome_summary.get("recommended_future_claim_element") or "").strip()
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type or default_claim_type,
                section_key=focus_section,
            ),
            claim_type=claim_type,
            follow_up_support_kind=suggested_support_kind or preferred_support_kind or _default_support_kind_for_section(focus_section),
        )
        split_action_url = urlsplit(action_url)
        action_query_pairs = parse_qsl(split_action_url.query, keep_blank_values=True)
        action_query = dict(action_query_pairs)
        ordered_action_query = []
        for key in ("user_id", "claim_type", "section", "follow_up_support_kind"):
            value = str(action_query.pop(key, "") or "").strip()
            if value:
                ordered_action_query.append((key, value))
        for key, value in action_query_pairs:
            if key in {"user_id", "claim_type", "section", "follow_up_support_kind"}:
                continue
            text = str(value or "").strip()
            if text:
                ordered_action_query.append((key, text))
        action_url = urlunsplit(
            (
                split_action_url.scheme,
                split_action_url.netloc,
                split_action_url.path,
                urlencode(ordered_action_query),
                split_action_url.fragment,
            )
        )
        chip_labels = [
            f"grounding status: {humanize_workflow_priority_label(str(document_grounding_improvement_next_action.get('status') or 'stalled').strip() or 'stalled')}"
        ]
        claim_element_id = str(document_grounding_improvement_next_action.get("claim_element_id") or "").strip()
        if claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(claim_element_id)}")
        if suggested_claim_element_id and suggested_claim_element_id != claim_element_id:
            chip_labels.append(f"next target element: {humanize_workflow_priority_label(suggested_claim_element_id)}")
        if preferred_support_kind:
            chip_labels.append(f"current support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        if attempted_support_kind and attempted_support_kind != preferred_support_kind:
            chip_labels.append(f"attempted lane: {humanize_workflow_priority_label(attempted_support_kind)}")
        if learned_support_kind:
            chip_labels.append(f"learned next lane: {humanize_workflow_priority_label(learned_support_kind)}")
        elif suggested_support_kind:
            chip_labels.append(f"suggested next lane: {humanize_workflow_priority_label(suggested_support_kind)}")
        chip_labels.append(
            f"grounding delta: {float(document_grounding_improvement_next_action.get('fact_backed_ratio_delta') or 0.0):+.2f}"
        )
        description = str(
            document_grounding_improvement_next_action.get("description")
            or "Grounding recovery stalled; switch support lanes or retarget the next grounding cycle."
        ).strip()
        if learned_support_kind:
            description = (
                f"{description} Learned lane preference now favors "
                f"{humanize_workflow_priority_label(learned_support_kind)}."
            )
        if grounding_action == "retarget_document_grounding" and suggested_claim_element_id and suggested_claim_element_id != claim_element_id:
            description = (
                f"{description} Retarget the next grounding pass toward "
                f"{humanize_workflow_priority_label(suggested_claim_element_id)}."
            )
        return {
            "status": "warning",
            "title": (
                "Retarget document grounding"
                if grounding_action == "retarget_document_grounding"
                else "Refine document grounding strategy"
            ),
            "description": description,
            "action_label": (
                "Review grounding retargeting"
                if grounding_action == "retarget_document_grounding"
                else "Review grounding strategy"
            ),
            "action_url": action_url,
            "action_kind": "link",
            "dashboard_url": dashboard_url,
            "chip_labels": chip_labels,
        }

    document_grounding_recovery_action = (
        intake_case_summary.get("document_grounding_recovery_action")
        if isinstance(intake_case_summary.get("document_grounding_recovery_action"), dict)
        else {}
    )
    if str(document_grounding_recovery_action.get("action") or "").strip().lower() == "recover_document_grounding":
        focus_section = str(document_grounding_recovery_action.get("focus_section") or "factual_allegations").strip() or "factual_allegations"
        claim_type = str(document_grounding_recovery_action.get("claim_type") or default_claim_type or "").strip()
        preferred_support_kind = str(document_grounding_recovery_action.get("preferred_support_kind") or "").strip()
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type or default_claim_type,
                section_key=focus_section,
            ),
            claim_type=claim_type,
            follow_up_support_kind=preferred_support_kind or _default_support_kind_for_section(focus_section),
        )
        split_action_url = urlsplit(action_url)
        action_query_pairs = parse_qsl(split_action_url.query, keep_blank_values=True)
        action_query = dict(action_query_pairs)
        ordered_action_query = []
        for key in ("user_id", "claim_type", "section", "follow_up_support_kind"):
            value = str(action_query.pop(key, "") or "").strip()
            if value:
                ordered_action_query.append((key, value))
        for key, value in action_query_pairs:
            if key in {"user_id", "claim_type", "section", "follow_up_support_kind"}:
                continue
            text = str(value or "").strip()
            if text:
                ordered_action_query.append((key, text))
        action_url = urlunsplit(
            (
                split_action_url.scheme,
                split_action_url.netloc,
                split_action_url.path,
                urlencode(ordered_action_query),
                split_action_url.fragment,
            )
        )
        chip_labels = [f"fact-backed ratio: {float(document_grounding_recovery_action.get('fact_backed_ratio') or 0.0):.2f}"]
        claim_element_id = str(document_grounding_recovery_action.get("claim_element_id") or "").strip()
        if claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(claim_element_id)}")
        if preferred_support_kind:
            chip_labels.append(f"support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        missing_fact_bundle = [
            str(item).strip()
            for item in list(document_grounding_recovery_action.get("missing_fact_bundle") or [])
            if str(item).strip()
        ]
        if missing_fact_bundle:
            chip_labels.append(f"missing facts: {', '.join(missing_fact_bundle[:2])}")
        return {
            "status": "warning",
            "title": "Recover document grounding before formalization",
            "description": str(
                document_grounding_recovery_action.get("description")
                or "Strengthen the draft with more fact-backed and artifact-backed support before formalization."
            ).strip(),
            "action_label": "Collect grounding support",
            "action_url": action_url,
            "action_kind": "link",
            "dashboard_url": dashboard_url,
            "chip_labels": chip_labels,
        }

    if isinstance(document_provenance_summary, dict) and document_provenance_summary:
        ratio_present = "fact_backed_ratio" in document_provenance_summary
        fact_backed_ratio = float(document_provenance_summary.get("fact_backed_ratio") or 0.0)
        low_grounding_flag = bool(document_provenance_summary.get("low_grounding_flag"))
        if low_grounding_flag or (ratio_present and fact_backed_ratio < 0.6):
            action_url = _append_review_query_params(
                _resolve_document_review_url(
                    user_id=user_id,
                    dashboard_url=dashboard_url,
                    claim_review_map=claim_review_map,
                    section_review_map=section_review_map,
                    claim_type=default_claim_type,
                    section_key="factual_allegations",
                ),
                follow_up_support_kind=_default_support_kind_for_section("factual_allegations"),
            )
            return {
                "status": "warning",
                "title": "Strengthen document grounding before further revisions",
                "description": (
                    "Increase canonical-fact and artifact-backed support in the draft before broadening revisions."
                ),
                "action_label": "Review factual allegations grounding",
                "action_url": action_url,
                "action_kind": "link",
                "dashboard_url": dashboard_url,
                "chip_labels": [
                    f"fact-backed ratio: {fact_backed_ratio:.2f}",
                    f"summary facts grounded: {int(document_provenance_summary.get('summary_fact_backed_count') or 0)}/{int(document_provenance_summary.get('summary_fact_count') or 0)}",
                    f"claim support grounded: {int(document_provenance_summary.get('claim_supporting_fact_backed_count') or 0)}/{int(document_provenance_summary.get('claim_supporting_fact_count') or 0)}",
                ],
            }

    document_drafting_next_action = (
        intake_case_summary.get("document_drafting_next_action")
        if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
        else {}
    )
    if str(document_drafting_next_action.get("action") or "").strip().lower() == "realign_document_drafting":
        target_claim_element_id = str(document_drafting_next_action.get("claim_element_id") or "").strip()
        executed_claim_element_id = str(document_drafting_next_action.get("executed_claim_element_id") or "").strip()
        focus_section = str(document_drafting_next_action.get("focus_section") or "claims_for_relief").strip() or "claims_for_relief"
        preferred_support_kind = str(document_drafting_next_action.get("preferred_support_kind") or "").strip()
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=default_claim_type,
                section_key=focus_section,
            ),
            follow_up_support_kind=_default_support_kind_for_section(focus_section),
        )
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
            "title": "Realign drafting before further revisions",
            "description": str(
                document_drafting_next_action.get("description")
                or "Realign drafting to the top targeted claim element before further revisions."
            ).strip(),
            "action_label": "Open formal complaint builder",
            "action_url": action_url,
            "action_kind": "link",
            "dashboard_url": dashboard_url,
            "chip_labels": chip_labels,
        }

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
            intake_case_summary=intake_case_summary,
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
    document_drafting_next_action = (
        intake_status.get("document_drafting_next_action")
        if isinstance(intake_status.get("document_drafting_next_action"), dict)
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
        "document_drafting_next_action": document_drafting_next_action,
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


def _merge_chip_labels(existing: Any, additions: Any) -> List[str]:
    merged: List[str] = []
    seen = set()
    for source in (existing, additions):
        if not isinstance(source, list):
            continue
        for item in source:
            label = str(item or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)
            merged.append(label)
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


def _build_document_builder_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    drafting_readiness = payload.get("drafting_readiness") if isinstance(payload.get("drafting_readiness"), dict) else {}
    sections = drafting_readiness.get("sections") if isinstance(drafting_readiness.get("sections"), dict) else {}
    claims = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []
    guardrails = (
        drafting_readiness.get("drafting_guardrails")
        if isinstance(drafting_readiness.get("drafting_guardrails"), dict)
        else {}
    )
    document_provenance_summary = (
        dict(payload.get("document_provenance_summary") or draft.get("document_provenance_summary") or {})
        if isinstance(payload.get("document_provenance_summary") or draft.get("document_provenance_summary"), dict)
        else {}
    )

    support_status_counts: Dict[str, int] = {}
    section_support: List[Dict[str, Any]] = []
    support_source_refs: List[str] = []
    for section_key, section in sections.items():
        if not isinstance(section, dict):
            continue
        support_status = str(section.get("support_status") or section.get("status") or "ready").strip().lower() or "ready"
        support_status_counts[support_status] = support_status_counts.get(support_status, 0) + 1
        source_refs = [
            str(item or "").strip()
            for item in list(section.get("source_refs") or [])
            if str(item or "").strip()
        ]
        support_source_refs.extend(source_refs)
        section_support.append(
            {
                "section_key": str(section_key or "").strip(),
                "title": section.get("title") or str(section_key or "").replace("_", " ").title(),
                "status": str(section.get("status") or "ready").strip().lower() or "ready",
                "support_status": support_status,
                "claim_element_count": int(section.get("claim_element_count") or len(section.get("claim_elements") or [])),
                "source_ref_count": len(source_refs),
                "explicit_gap_count": len(section.get("explicit_gaps") or []),
                "review_url": section.get("review_url"),
            }
        )

    source_family_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        for source_key, target in (
            ("source_family_counts", source_family_counts),
            ("artifact_family_counts", artifact_family_counts),
            ("content_origin_counts", content_origin_counts),
        ):
            counts = claim.get(source_key) if isinstance(claim.get(source_key), dict) else {}
            for label, count in counts.items():
                normalized_label = str(label or "").strip()
                if not normalized_label:
                    continue
                target[normalized_label] = target.get(normalized_label, 0) + int(count or 0)

    guardrail_warnings = [
        warning
        for warning in list(guardrails.get("warnings") or [])
        if isinstance(warning, dict)
    ]
    warning_type_counts: Dict[str, int] = {}
    for warning in guardrail_warnings:
        warning_type = str(warning.get("warning_type") or warning.get("code") or "drafting_warning").strip()
        if warning_type:
            warning_type_counts[warning_type] = warning_type_counts.get(warning_type, 0) + 1

    artifact_entries = []
    for format_name, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        artifact_entries.append(
            {
                "format": str(format_name or "").strip(),
                "filename": artifact.get("filename"),
                "size_bytes": int(artifact.get("size_bytes") or 0),
                "download_url": artifact.get("download_url"),
                "managed_download": bool(artifact.get("download_url")),
            }
        )

    return {
        "status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
        "warning_count": int(drafting_readiness.get("warning_count") or 0),
        "guardrail_warning_count": int(guardrails.get("warning_count") or len(guardrail_warnings)),
        "guardrail_blocker_count": int(guardrails.get("blocker_count") or 0),
        "support_status_counts": support_status_counts,
        "section_support": section_support,
        "source_ref_count": len(_dedupe_text_values(support_source_refs)),
        "source_family_counts": source_family_counts,
        "artifact_family_counts": artifact_family_counts,
        "content_origin_counts": content_origin_counts,
        "warning_type_counts": warning_type_counts,
        "artifact_provenance": {
            "managed_output_dir": str(_default_generated_documents_root()),
            "artifact_count": len(artifact_entries),
            "downloadable_count": len([entry for entry in artifact_entries if entry.get("managed_download")]),
            "artifacts": artifact_entries,
        },
        "document_provenance_summary": document_provenance_summary,
    }


def _section_claim_types(section_key: str, claim_types: List[str]) -> List[str]:
    claim_oriented_sections = {
        "summary_of_facts",
        "claims_for_relief",
        "exhibits",
        "requested_relief",
    }
    return claim_types if section_key in claim_oriented_sections else []


def _build_claim_review_chip_labels(claim: Dict[str, Any]) -> List[str]:
    """Build chip labels for claim review using the canonical pipeline implementation.

    Delegates to ``_pipeline_claim_chip_labels`` so that the application layer
    stays in sync with the richer set of chip signals maintained by
    ``document_pipeline`` (temporal predicates, provenance kinds, authority
    treatment, etc.) rather than duplicating a simplified version here.
    """
    return _pipeline_claim_chip_labels(claim)


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
                merged_chip_labels = _merge_chip_labels(item.get("chip_labels"), target.get("chip_labels"))
                if merged_chip_labels:
                    item["chip_labels"] = merged_chip_labels
                else:
                    item.pop("chip_labels", None)
            else:
                item["review_url"] = dashboard_url
                item["review_context"] = {"user_id": default_review_intent.get("user_id")}
                item["review_intent"] = dict(default_review_intent)
            if str(item.get("status") or "").strip().lower() in {"warning", "blocked"}:
                checklist_intake_status = _build_checklist_intake_status(intake_status)
                if checklist_intake_status:
                    item["intake_status"] = checklist_intake_status
    return payload


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
        claim["chip_labels"] = _build_claim_review_chip_labels(claim)
        if str(claim.get("status") or "").strip().lower() in {"warning", "blocked"}:
            claim["warnings"] = _merge_warning_entries(claim.get("warnings"), intake_warning_entries)
        claim_review_map[claim_type] = {
            "review_url": claim_review_url,
            "review_context": claim["review_context"],
            "review_intent": claim_review_intent,
            "chip_labels": list(claim.get("chip_labels") or []),
        }
        claim_links.append(
            {
                "claim_type": claim_type,
                "review_url": claim_review_url,
                "review_intent": claim_review_intent,
                "chip_labels": list(claim.get("chip_labels") or []),
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
        intake_case_summary=intake_case_summary,
    )
    workflow_priority = _build_document_review_workflow_priority(
        intake_status=intake_status,
        intake_case_summary=intake_case_summary,
        workflow_phase_plan=workflow_phase_plan,
        document_provenance_summary=(
            dict(payload.get("document_provenance_summary") or draft.get("document_provenance_summary") or {})
            if isinstance(payload.get("document_provenance_summary") or draft.get("document_provenance_summary"), dict)
            else {}
        ),
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
        "document_provenance_summary": (
            dict(payload.get("document_provenance_summary") or draft.get("document_provenance_summary") or {})
            if isinstance(payload.get("document_provenance_summary") or draft.get("document_provenance_summary"), dict)
            else {}
        ),
        "document_focus_preview": _build_document_focus_preview(draft),
        "document_drafting_next_action": (
            dict(intake_case_summary.get("document_drafting_next_action") or {})
            if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
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
        "document_grounding_recovery_action": (
            dict(intake_case_summary.get("document_grounding_recovery_action") or {})
            if isinstance(intake_case_summary.get("document_grounding_recovery_action"), dict)
            else {}
        ),
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
    payload["document_builder_summary"] = _build_document_builder_summary(payload)
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


OUTLINE_TASK_ID = "CIMP-UX-30"
_LABEL_KEYS = ("evidence_label", "label", "exhibit_label", "support_label")
_PROSE_KEYS = ("model_prose", "model_text", "generated_prose", "ai_suggestion")


def _outline_text(value: Any, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _outline_span(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    start = value.get("start", value.get("span_start"))
    end = value.get("end", value.get("span_end"))
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        return None
    return {
        "start": start,
        "end": end,
        "text": _outline_text(value.get("text"), 400),
        "unit": _outline_text(value.get("unit"), 40) or "utf-8-bytes",
    }


def _current_draft(case_file: Dict[str, Any]) -> Dict[str, Any]:
    store = case_file.get("draft_workflow") if isinstance(case_file.get("draft_workflow"), dict) else {}
    versions = [item for item in store.get("versions") or [] if isinstance(item, dict)]
    if not versions:
        return {"present": False, "draft_id": "", "revision": 0, "text": "", "text_digest": ""}
    current = max(versions, key=lambda item: (int(item.get("revision") or 0), str(item.get("draft_id") or "")))
    return {
        "present": True,
        "draft_id": _outline_text(current.get("draft_id"), 80),
        "revision": int(current.get("revision") or 0),
        "text": _outline_text(current.get("text"), 4000),
        "text_digest": _outline_text(current.get("text_digest"), 80),
    }


def _facts(case_file: Dict[str, Any]) -> List[Dict[str, Any]]:
    domains = case_file.get("workflow_domains") if isinstance(case_file.get("workflow_domains"), dict) else {}
    factual = domains.get("factual") if isinstance(domains.get("factual"), dict) else {}
    rows = []
    for item in factual.get("assertions") or []:
        if not isinstance(item, dict):
            continue
        fact_id = _outline_text(item.get("id") or item.get("fact_id"), 80)
        if not fact_id:
            continue
        rows.append({
            "fact_id": fact_id,
            "text": _outline_text(item.get("text"), 500),
            "bound": item.get("bound") is True,
            "revision": int(item.get("revision") or 0) if type(item.get("revision")) is int else 0,
        })
    return rows


def _exhibits(case_file: Dict[str, Any]) -> List[Dict[str, Any]]:
    domains = case_file.get("workflow_domains") if isinstance(case_file.get("workflow_domains"), dict) else {}
    evidence = domains.get("evidence") if isinstance(domains.get("evidence"), dict) else {}
    rows = []
    for item in evidence.get("exhibits") or []:
        if not isinstance(item, dict):
            continue
        span = _outline_span(item.get("span") if isinstance(item.get("span"), dict) else item)
        label = ""
        for key in _LABEL_KEYS:
            label = label or _outline_text(item.get(key), 160)
        rows.append({
            "exhibit_id": _outline_text(item.get("id") or item.get("exhibit_id"), 80),
            "artifact_id": _outline_text(item.get("artifact_id"), 120),
            "fact_id": _outline_text(item.get("fact_id"), 80),
            "requirement_id": _outline_text(item.get("requirement_id") or item.get("passage_id"), 120),
            "span": span,
            "label_only": bool(label) and span is None,
            "label": label,
        })
    return rows


def _gap(reason: str, **extra: Any) -> Dict[str, Any]:
    payload = {"reason": reason, "visible": True}
    payload.update(extra)
    return payload


def project_complaint_outline(case_file: Any) -> Dict[str, Any]:
    """Project the current draft beside facts, spans, and admitted authority.

    A model paragraph or an evidence label never completes a requirement.
    Legal sufficiency and proof stay false on this surface.
    """

    source = case_file if isinstance(case_file, dict) else {}
    draft = _current_draft(source)
    facts = _facts(source)
    exhibits = _exhibits(source)
    stored = source.get("derived_dependency_requirements") if isinstance(source.get("derived_dependency_requirements"), dict) else {}
    requirements_in = [item for item in stored.get("requirements") or [] if isinstance(item, dict)]
    unresolved = [item for item in stored.get("unresolved_research") or [] if isinstance(item, dict)]
    fact_ids = {item["fact_id"] for item in facts}
    sections = []
    gaps = []
    if not draft["present"] or not draft["text"]:
        gaps.append(_gap("missing_draft_text"))
    for item in unresolved:
        gaps.append(_gap(str(item.get("reason") or "unresolved_research"), passage_id=_outline_text(item.get("passage_id"), 120)))
    if not requirements_in and not unresolved:
        gaps.append(_gap("no_requirements"))
    for index, item in enumerate(requirements_in):
        passage_id = _outline_text(item.get("passage_id"), 120)
        span = _outline_span(item.get("source_span"))
        admitted = item.get("admitted_law") is True and bool(passage_id) and span is not None
        prose = ""
        for key in _PROSE_KEYS:
            prose = prose or _outline_text(item.get(key), 500)
        label = ""
        for key in _LABEL_KEYS:
            label = label or _outline_text(item.get(key), 160)
        linked_fact_ids = []
        for support in item.get("fact_support") or []:
            if isinstance(support, dict):
                fact_id = _outline_text(support.get("fact_id"), 80)
                if fact_id and fact_id in fact_ids and fact_id not in linked_fact_ids:
                    linked_fact_ids.append(fact_id)
        requirement_id = _outline_text(item.get("requirement_id"), 80) or passage_id or f"requirement-{index + 1}"
        linked_exhibits = []
        for exhibit in exhibits:
            matches = exhibit["requirement_id"] in {requirement_id, passage_id} or exhibit["fact_id"] in linked_fact_ids
            if matches and exhibit["artifact_id"] and exhibit["span"] is not None:
                linked_exhibits.append(exhibit)
        section_gaps = []
        if prose:
            section_gaps.append(_gap("model_prose_is_not_support"))
        if label:
            section_gaps.append(_gap("evidence_label_is_not_support"))
        if not admitted:
            section_gaps.append(_gap("missing_admitted_authority"))
        if not linked_fact_ids:
            section_gaps.append(_gap("missing_fact"))
        elif any(not next(fact["text"] for fact in facts if fact["fact_id"] == fact_id) for fact_id in linked_fact_ids):
            section_gaps.append(_gap("missing_fact_text"))
        if not linked_exhibits:
            section_gaps.append(_gap("missing_evidence_span"))
        cited = admitted and bool(linked_fact_ids) and bool(linked_exhibits) and not any(
            gap["reason"] == "missing_fact_text" for gap in section_gaps
        )
        citation = _outline_text(item.get("citation") or item.get("name"), 160)
        authority = None
        if admitted:
            authority = {
                "passage_id": passage_id,
                "citation": citation,
                "authority_id": _outline_text(item.get("authority_id"), 120),
                "source_span": span,
                "admitted_law": True,
                "href": "#admitted-authority-" + passage_id,
            }
        section = {
            "section_id": requirement_id,
            "heading": citation or "Untitled requirement",
            "draft_text": draft["text"],
            "support_cited": cited,
            "legal_sufficiency": False,
            "proof": False,
            "model_prose": prose,
            "evidence_label": label,
            "caller_satisfied_ignored": item.get("satisfied") is True or item.get("complete") is True,
            "authority": authority,
            "facts": [fact for fact in facts if fact["fact_id"] in linked_fact_ids],
            "evidence": [{
                "artifact_id": exhibit["artifact_id"],
                "exhibit_id": exhibit["exhibit_id"],
                "span": exhibit["span"],
                "fact_id": exhibit["fact_id"],
            } for exhibit in linked_exhibits],
            "gaps": section_gaps,
            "requirement_completed": False,
        }
        sections.append(section)
        gaps.extend(dict(gap, section_id=requirement_id) for gap in section_gaps)
    for exhibit in exhibits:
        if exhibit["label_only"]:
            gaps.append(_gap("evidence_label_is_not_support", exhibit_id=exhibit["exhibit_id"]))
    status = "empty" if not sections and not draft["present"] else "gaps" if gaps else "cited"
    return {
        "task_id": OUTLINE_TASK_ID,
        "status": status,
        "legal_sufficiency": False,
        "proof": False,
        "governing_law": False,
        "draft": draft,
        "facts": facts,
        "sections": sections,
        "gaps": gaps,
        "unresolved_research": [{
            "reason": str(item.get("reason") or "unresolved_research"),
            "visible": True,
            "passage_id": _outline_text(item.get("passage_id"), 120),
        } for item in unresolved],
    }


async def require_composed_document_authorizer(request: Request) -> None:
    """When production composition is active, document and download handlers require its decision."""

    from .case_routes import COMPOSITION_NAME

    if getattr(request.app.state, "case_route_composition", None) != COMPOSITION_NAME:
        raise HTTPException(status_code=401, detail="authorizer_required")
    decision = getattr(request.state, "case_authorization", None)
    if decision is None or not getattr(decision, "permits_case_content", False):
        raise HTTPException(status_code=401, detail="authorizer_required")


def create_document_router(mediator: Any) -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_composed_document_authorizer)])

    @router.post("/api/documents/formal-complaint")
    async def build_formal_complaint_document(
        request: FormalComplaintDocumentRequest,
    ) -> Dict[str, Any]:
        if not request.output_formats:
            raise HTTPException(status_code=400, detail="At least one output format is required")
        from .case_routes import case_download_root, CaseAccessError
        try:
            output_root = case_download_root()
        except CaseAccessError:
            raise HTTPException(status_code=503, detail="case_handler_unavailable") from None
        if request.output_dir is not None or request.email_timeline_handoff_path or request.email_authority_enrichment_path:
            raise HTTPException(status_code=403, detail="host_path_not_permitted")
        if request.enable_agentic_optimization or request.optimization_llm_config:
            raise HTTPException(status_code=403, detail="case_processing_not_configured")
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
            email_timeline_handoff_path=request.email_timeline_handoff_path,
            email_authority_enrichment_path=request.email_authority_enrichment_path,
            output_dir=str(output_root),
            output_formats=request.output_formats,
        )
        if request.optimization_llm_config:
            build_kwargs["optimization_llm_config"] = request.optimization_llm_config
        payload = mediator.build_formal_complaint_document_package(**build_kwargs)
        payload = _annotate_artifacts_with_download_urls(payload)
        return _annotate_review_links(payload, mediator=mediator, user_id=request.user_id)

    @router.get("/api/documents/download")
    async def download_generated_document(path: str = Query(...)) -> FileResponse:
        from .case_routes import case_download_root, CaseAccessError
        try:
            root = case_download_root()
        except CaseAccessError:
            raise HTTPException(status_code=503, detail="case_handler_unavailable") from None
        file_path = Path(path).resolve()
        if not file_path.is_relative_to(root):
            raise HTTPException(status_code=403, detail="case_download_denied")
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Generated document not found")
        return FileResponse(path=str(file_path), filename=file_path.name)

    def _workflow_case_file() -> Dict[str, Any]:
        case_file = getattr(mediator, "intake_case_file", None)
        if not isinstance(case_file, dict):
            raise HTTPException(status_code=503, detail="workflow_record_unavailable")
        return case_file

    def _workflow_scope(case_id: str, request: Request) -> Dict[str, Any]:
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or decision.case_id != case_id:
            raise HTTPException(status_code=403, detail="cross_case_id")
        return {
            "actor_principal_id": decision.actor_principal_id,
            "membership": decision.membership,
            "action": decision.action,
        }

    def _workflow_error(exc: Exception) -> HTTPException:
        from .case_review import CaseReviewError
        code = exc.code if isinstance(exc, CaseReviewError) else "workflow_unavailable"
        status = 409 if code in {"stale_domain", "stale_revision", "replay_mismatch"} else 403 if code in {
            "actor_not_permitted", "export_authorization_required", "automatic_filing_refused", "legal_sufficiency_refused", "cross_case_id",
        } else 422 if code in {
            "draft_field", "draft_bounds", "stage_not_ready", "review_required", "draft_revision_required", "review_field", "review_bounds",
        } else 503
        return HTTPException(status_code=status, detail=code)

    @router.get("/api/documents/{case_id}/complaint-outline")
    async def read_complaint_outline(case_id: str, request: Request) -> Dict[str, Any]:
        _workflow_scope(case_id, request)
        return project_complaint_outline(_workflow_case_file())

    @router.get("/api/documents/{case_id}/workflow-stage")
    async def read_workflow_stage(case_id: str, request: Request) -> Dict[str, Any]:
        from .case_review import CaseReviewError, project_workflow_stage
        _workflow_scope(case_id, request)
        try:
            return project_workflow_stage(_workflow_case_file())
        except CaseReviewError as exc:
            raise _workflow_error(exc) from None

    @router.post("/api/documents/{case_id}/draft-versions")
    async def write_draft_version(case_id: str, request: Request) -> Dict[str, Any]:
        from .case_review import CaseReviewError, version_draft
        scope = _workflow_scope(case_id, request)
        try:
            return version_draft(_workflow_case_file(), await request.json(), **scope)
        except CaseReviewError as exc:
            raise _workflow_error(exc) from None

    @router.post("/api/documents/{case_id}/draft-reviews")
    async def write_draft_review(case_id: str, request: Request) -> Dict[str, Any]:
        from .case_review import CaseReviewError, review_draft_version
        scope = _workflow_scope(case_id, request)
        try:
            return review_draft_version(_workflow_case_file(), await request.json(), **scope)
        except CaseReviewError as exc:
            raise _workflow_error(exc) from None

    @router.post("/api/documents/{case_id}/draft-exports")
    async def write_draft_export(case_id: str, request: Request) -> Dict[str, Any]:
        from .case_review import CaseReviewError, export_draft_version
        scope = _workflow_scope(case_id, request)
        try:
            return export_draft_version(_workflow_case_file(), await request.json(), **scope)
        except CaseReviewError as exc:
            raise _workflow_error(exc) from None

    @router.get("/api/documents/optimization-trace")
    async def retrieve_optimization_trace(cid: str = Query(...)) -> Dict[str, Any]:
        # A caller-selected CID has no per-case provenance. Later private
        # artifact routes may admit a scoped reference; this legacy path may not.
        raise HTTPException(status_code=403, detail="trace_reference_not_bound")

    return router


def attach_document_routes(app: FastAPI, mediator: Any) -> FastAPI:
    return attach_router_routes(app, create_document_router(mediator))
