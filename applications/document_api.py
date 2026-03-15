from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from document_pipeline import DEFAULT_OUTPUT_DIR


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


def _normalize_intake_contradiction(contradiction: Any) -> Dict[str, Any]:
    candidate = contradiction if isinstance(contradiction, dict) else {}
    left_text = str(
        candidate.get("left_text")
        or candidate.get("left_fact_text")
        or candidate.get("statement_a")
        or ""
    ).strip()
    right_text = str(
        candidate.get("right_text")
        or candidate.get("right_fact_text")
        or candidate.get("statement_b")
        or ""
    ).strip()
    summary = str(candidate.get("summary") or "").strip()
    if not summary:
        if left_text and right_text:
            summary = f"{left_text} <> {right_text}"
        else:
            summary = left_text or right_text or "Unresolved contradiction"
    return {
        "summary": summary,
        "left_text": left_text,
        "right_text": right_text,
        "question": str(candidate.get("question") or candidate.get("question_text") or "").strip(),
        "severity": str(candidate.get("severity") or "").strip(),
        "category": str(candidate.get("category") or candidate.get("type") or "").strip(),
    }


def _build_intake_status_summary(mediator: Any) -> Dict[str, Any]:
    get_three_phase_status = getattr(mediator, "get_three_phase_status", None)
    if not callable(get_three_phase_status):
        return {}

    raw_status = get_three_phase_status()
    if not isinstance(raw_status, dict):
        return {}

    readiness = raw_status.get("intake_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    contradictions = raw_status.get("intake_contradictions")
    if not isinstance(contradictions, list):
        contradictions = (
            readiness.get("contradictions")
            if isinstance(readiness.get("contradictions"), list)
            else []
        )
    blockers = readiness.get("blockers")
    blocker_list = [str(item).strip() for item in blockers] if isinstance(blockers, list) else []
    normalized_contradictions = [
        _normalize_intake_contradiction(item)
        for item in contradictions
        if isinstance(item, dict)
    ]

    try:
        score = float(readiness.get("score"))
    except (TypeError, ValueError):
        score = 0.0
    try:
        remaining_gap_count = int(readiness.get("remaining_gap_count"))
    except (TypeError, ValueError):
        remaining_gap_count = 0
    try:
        contradiction_count = int(readiness.get("contradiction_count"))
    except (TypeError, ValueError):
        contradiction_count = len(normalized_contradictions)

    return {
        "current_phase": str(raw_status.get("current_phase") or "").strip(),
        "ready_to_advance": bool(readiness.get("ready_to_advance", False)),
        "score": score,
        "remaining_gap_count": remaining_gap_count,
        "contradiction_count": contradiction_count,
        "blockers": blocker_list,
        "contradictions": normalized_contradictions,
    }


def _build_checklist_intake_status(intake_status: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_status, dict) or not intake_status:
        return {}
    blockers = intake_status.get("blockers")
    blocker_list = [str(item).strip() for item in blockers] if isinstance(blockers, list) else []
    contradictions = intake_status.get("contradictions")
    contradiction_list = contradictions if isinstance(contradictions, list) else []
    return {
        "score": float(intake_status.get("score") or 0.0),
        "ready_to_advance": bool(intake_status.get("ready_to_advance", False)),
        "remaining_gap_count": int(intake_status.get("remaining_gap_count") or 0),
        "contradiction_count": int(intake_status.get("contradiction_count") or len(contradiction_list)),
        "blockers": blocker_list,
        "contradictions": contradiction_list[:2],
    }


def _build_intake_warning_entries(intake_status: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(intake_status, dict) or not intake_status:
        return []
    warnings: List[Dict[str, Any]] = []
    blockers = intake_status.get("blockers")
    blocker_list = blockers if isinstance(blockers, list) else []
    for blocker in blocker_list:
        blocker_text = str(blocker).strip()
        if not blocker_text:
            continue
        warnings.append(
            {
                "severity": "warning",
                "code": "intake_blocker",
                "message": f"Intake blocker: {blocker_text}",
            }
        )
    contradictions = intake_status.get("contradictions")
    contradiction_list = contradictions if isinstance(contradictions, list) else []
    for contradiction in contradiction_list[:2]:
        if not isinstance(contradiction, dict):
            continue
        summary = str(contradiction.get("summary") or "").strip() or "Unresolved intake contradiction"
        question = str(contradiction.get("question") or "").strip()
        message = summary if not question else f"{summary}. Clarify: {question}"
        warnings.append(
            {
                "severity": "warning",
                "code": "intake_contradiction",
                "message": message,
            }
        )
    return warnings


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


def _annotate_review_links(payload: Dict[str, Any], *, user_id: Optional[str]) -> Dict[str, Any]:
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
    intake_status = _build_intake_status_summary(mediator)
    intake_warning_entries = _build_intake_warning_entries(intake_status)

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

    payload["review_links"] = {
        "dashboard_url": dashboard_url,
        "claims": claim_links,
        "sections": section_links,
        "intake_status": intake_status,
    }
    payload["review_intent"] = _build_review_intent(
        user_id=resolved_user_id,
        claim_type=preferred_claim_type,
        section=preferred_section,
        follow_up_support_kind=_default_support_kind_for_section(preferred_section),
    )
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
        return _annotate_review_links(payload, user_id=request.user_id)

    @router.get("/api/documents/download")
    async def download_generated_document(path: str = Query(...)) -> FileResponse:
        file_path = Path(path).resolve()
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Generated document not found")
        if not _is_allowed_download_path(file_path):
            raise HTTPException(status_code=403, detail="Requested path is outside the generated documents directory")
        return FileResponse(path=str(file_path), filename=file_path.name)

    return router


def attach_document_routes(app: FastAPI, mediator: Any) -> FastAPI:
    app.include_router(create_document_router(mediator))
    return app
