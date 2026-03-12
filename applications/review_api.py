from typing import Any, Dict

from fastapi import APIRouter, FastAPI, Response
from claim_support_review import (
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportManualReviewResolveRequest,
    ClaimSupportReviewRequest,
    build_claim_support_follow_up_execution_payload,
    build_claim_support_manual_review_resolution_payload,
    build_claim_support_review_payload,
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

    return router


def attach_claim_support_review_routes(app: FastAPI, mediator: Any) -> FastAPI:
    app.include_router(create_claim_support_review_router(mediator))
    return app


def create_review_api_app(mediator: Any) -> FastAPI:
    app = FastAPI(title="Complaint Generator Review API")
    attach_claim_support_review_routes(app, mediator)
    attach_document_routes(app, mediator)
    return app