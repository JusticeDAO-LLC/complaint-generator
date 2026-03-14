from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, File, Form, Response, UploadFile
from claim_support_review import (
    ClaimSupportDocumentSaveRequest,
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportManualReviewResolveRequest,
    ClaimSupportReviewRequest,
    ClaimSupportTestimonySaveRequest,
    build_claim_support_document_payload,
    build_claim_support_follow_up_execution_payload,
    build_claim_support_manual_review_resolution_payload,
    build_claim_support_review_payload,
    build_claim_support_testimony_payload,
    build_claim_support_uploaded_document_payload,
)
from .document_api import attach_document_routes


REVIEW_EXECUTION_COMPATIBILITY_NOTICE = {
    "deprecated": True,
    "field": "execute_follow_up",
    "route": "/api/claim-support/review",
    "replacement_route": "/api/claim-support/execute-follow-up",
    "message": (
        "execute_follow_up on /api/claim-support/review is deprecated; "
        "use /api/claim-support/execute-follow-up for side effects."
    ),
}
REVIEW_EXECUTION_SUNSET = "Wed, 30 Sep 2026 23:59:59 GMT"


def _apply_review_execution_compatibility_notice(
    payload: Dict[str, Any],
    response: Response,
) -> Dict[str, Any]:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = REVIEW_EXECUTION_SUNSET
    response.headers["Link"] = (
        '</api/claim-support/execute-follow-up>; rel="successor-version"'
    )
    response.headers["Warning"] = (
        '299 - "execute_follow_up on /api/claim-support/review is deprecated; '
        'use /api/claim-support/execute-follow-up"'
    )
    payload["compatibility_notice"] = dict(REVIEW_EXECUTION_COMPATIBILITY_NOTICE)
    return payload


def _normalize_required_support_kinds_form(
    raw_value: Optional[str],
) -> List[str]:
    if not raw_value:
        return []
    return [item.strip() for item in str(raw_value).split(",") if item.strip()]


def create_claim_support_review_router(mediator: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/api/claim-support/review")
    async def claim_support_review(
        request: ClaimSupportReviewRequest,
        response: Response,
    ) -> Dict[str, Any]:
        payload = build_claim_support_review_payload(mediator, request)
        if request.execute_follow_up:
            return _apply_review_execution_compatibility_notice(payload, response)
        return payload

    @router.post("/api/claim-support/execute-follow-up")
    async def claim_support_execute_follow_up(
        request: ClaimSupportFollowUpExecuteRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_follow_up_execution_payload(mediator, request)

    @router.post("/api/claim-support/resolve-manual-review")
    async def claim_support_resolve_manual_review(
        request: ClaimSupportManualReviewResolveRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_manual_review_resolution_payload(mediator, request)

    @router.post("/api/claim-support/save-testimony")
    async def claim_support_save_testimony(
        request: ClaimSupportTestimonySaveRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_testimony_payload(mediator, request)

    @router.post("/api/claim-support/save-document")
    async def claim_support_save_document(
        request: ClaimSupportDocumentSaveRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_document_payload(mediator, request)

    @router.post("/api/claim-support/upload-document")
    async def claim_support_upload_document(
        file: UploadFile = File(...),
        user_id: Optional[str] = Form(default=None),
        claim_type: Optional[str] = Form(default=None),
        claim_element_id: Optional[str] = Form(default=None),
        claim_element: Optional[str] = Form(default=None),
        document_label: Optional[str] = Form(default=None),
        source_url: Optional[str] = Form(default=None),
        mime_type: Optional[str] = Form(default=None),
        evidence_type: str = Form(default="document"),
        required_support_kinds: Optional[str] = Form(default=None),
        include_post_save_review: bool = Form(default=True),
        include_support_summary: bool = Form(default=True),
        include_overview: bool = Form(default=True),
        include_follow_up_plan: bool = Form(default=True),
    ) -> Dict[str, Any]:
        file_bytes = await file.read()
        return build_claim_support_uploaded_document_payload(
            mediator,
            user_id=user_id,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            claim_element=claim_element,
            file_bytes=file_bytes,
            filename=file.filename,
            document_label=document_label,
            source_url=source_url,
            mime_type=mime_type or file.content_type,
            evidence_type=evidence_type,
            document_metadata={},
            required_support_kinds=_normalize_required_support_kinds_form(required_support_kinds),
            include_post_save_review=include_post_save_review,
            include_support_summary=include_support_summary,
            include_overview=include_overview,
            include_follow_up_plan=include_follow_up_plan,
        )

    return router


def attach_claim_support_review_routes(app: FastAPI, mediator: Any) -> FastAPI:
    app.include_router(create_claim_support_review_router(mediator))
    return app


def create_review_api_app(mediator: Any) -> FastAPI:
    app = FastAPI(title="Complaint Generator Review API")
    attach_claim_support_review_routes(app, mediator)
    attach_document_routes(app, mediator)
    return app