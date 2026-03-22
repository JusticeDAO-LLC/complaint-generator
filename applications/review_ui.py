from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .dashboard_ui import attach_dashboard_ui_routes
from .complaint_workspace_api import attach_complaint_workspace_routes
from .document_ui import attach_document_ui_routes
from .site_ui import attach_core_site_ui_routes


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


def create_review_health_router(surface_name: str) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def review_health() -> dict:
        return {
            "status": "healthy",
            "surface": surface_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return router


def attach_review_health_routes(app: FastAPI, surface_name: str) -> FastAPI:
    app.include_router(create_review_health_router(surface_name))
    return app


def attach_static_asset_routes(app: FastAPI) -> FastAPI:
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if not static_dir.is_dir():
        return app

    if any(getattr(route, "path", None) == "/static" for route in app.routes):
        return app

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


def create_review_dashboard_app() -> FastAPI:
    app = FastAPI(title="Complaint Generator Review Dashboard")
    attach_static_asset_routes(app)
    attach_claim_support_review_ui_routes(app)
    attach_review_health_routes(app, "review-dashboard")
    return app


def create_review_surface_app(mediator: Any) -> FastAPI:
    app = FastAPI(title="Complaint Generator Review Surface")
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    attach_dashboard_ui_routes(app)
    attach_claim_support_review_ui_routes(app)
    attach_document_ui_routes(app)
    attach_review_health_routes(app, "review-surface")
    from .review_api import attach_claim_support_review_routes
    from .document_api import attach_document_routes

    attach_complaint_workspace_routes(app)
    attach_claim_support_review_routes(app, mediator)
    attach_document_routes(app, mediator)
    return app
