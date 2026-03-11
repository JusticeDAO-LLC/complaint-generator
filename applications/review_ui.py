from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse


_CLAIM_SUPPORT_REVIEW_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "templates" / "claim_support_review.html"
)


def load_claim_support_review_html() -> str:
    return _CLAIM_SUPPORT_REVIEW_TEMPLATE.read_text()


def create_claim_support_review_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get("/claim-support-review", response_class=HTMLResponse)
    async def claim_support_review_page() -> str:
        return load_claim_support_review_html()

    return router


def attach_claim_support_review_ui_routes(app: FastAPI) -> FastAPI:
    app.include_router(create_claim_support_review_ui_router())
    return app


def create_review_dashboard_app() -> FastAPI:
    app = FastAPI(title="Complaint Generator Review Dashboard")
    attach_claim_support_review_ui_routes(app)
    return app


def create_review_surface_app(mediator: Any) -> FastAPI:
    app = FastAPI(title="Complaint Generator Review Surface")
    attach_claim_support_review_ui_routes(app)
    from .review_api import attach_claim_support_review_routes

    attach_claim_support_review_routes(app, mediator)
    return app