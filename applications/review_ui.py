from pathlib import Path
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .case_routes import compose_case_routes
from .dashboard_ui import attach_dashboard_ui_routes
from .document_ui import attach_document_ui_routes
from .fastapi_compat import attach_router_routes
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
    return attach_router_routes(app, create_claim_support_review_ui_router())


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
    return attach_router_routes(app, create_review_health_router(surface_name))


def attach_static_asset_routes(app: FastAPI) -> FastAPI:
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if not static_dir.is_dir():
        return app

    if any(getattr(route, "path", None) == "/static" for route in app.routes):
        return app

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


def _build_chat_payload(
    message: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    sender: str = "Bot:",
    hashed_username: Optional[str] = None,
) -> Dict[str, Any]:
    payload_dict = dict(payload or {})
    normalized_message = str(message or payload_dict.get("message") or "")
    response = {
        "sender": str(payload_dict.get("sender") or sender),
        "message": normalized_message,
        "question": str(payload_dict.get("question") or normalized_message),
        "inquiry": dict(payload_dict.get("inquiry") or {}),
        "explanation": dict(payload_dict.get("explanation") or {}),
    }
    normalized_username = str(
        payload_dict.get("hashed_username") or hashed_username or ""
    ).strip()
    if normalized_username:
        response["hashed_username"] = normalized_username
    return response


def _contextualize_chat_message(message_text: str, payload: Dict[str, Any]) -> str:
    chat_context = payload.get("chat_context")
    if not isinstance(chat_context, dict):
        return message_text
    context_kind = str(chat_context.get("kind") or chat_context.get("source_surface") or payload.get("source") or "").strip()
    labels = chat_context.get("labels") if isinstance(chat_context.get("labels"), list) else []
    excerpt = str(chat_context.get("excerpt") or "").strip()
    if "intake" in context_kind.lower() or "denois" in context_kind.lower():
        context_lines = [
            "Intake question-generation context:",
            "- Goal: ask the best next questions to clarify the legal basis of the complaint.",
            "- Cover: parties, dates, duties, adverse acts, harms, remedies, evidence, and missing facts.",
        ]
        if labels:
            context_lines.append(
                "- Focus labels: " + ", ".join(str(label).strip() for label in labels if str(label).strip())
            )
        if excerpt:
            context_lines.append("- Intake guidance: " + excerpt[:900])
        context_lines.append("")
        context_lines.append("User question:")
        context_lines.append(message_text)
        return "\n".join(context_lines)
    filing = chat_context.get("filing") if isinstance(chat_context.get("filing"), dict) else {}
    context_lines = [
        "Selected docket filing context:",
        f"- Filing title: {str(filing.get('title') or '').strip() or 'unknown'}",
        f"- Filing id: {str(filing.get('id') or '').strip() or 'unknown'}",
        f"- Suggested use: {str(filing.get('use') or '').strip() or 'not classified'}",
    ]
    if labels:
        context_lines.append(
            "- Labels: " + ", ".join(str(label).strip() for label in labels if str(label).strip())
        )
    if excerpt:
        context_lines.append("- Excerpt: " + excerpt[:900])
    context_lines.append("")
    context_lines.append("User question:")
    context_lines.append(message_text)
    return "\n".join(context_lines)


def _process_chat_message(
    mediator: Any,
    message_text: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    hashed_username: Optional[str] = None,
) -> Dict[str, Any]:
    payload_dict = dict(payload or {})
    routed_message = _contextualize_chat_message(message_text, payload_dict)
    if callable(getattr(mediator, "io_payload", None)):
        response_payload = mediator.io_payload(routed_message)
        return _build_chat_payload(
            str((response_payload or {}).get("message") or ""),
            response_payload if isinstance(response_payload, dict) else None,
            sender="Bot:",
            hashed_username=hashed_username,
        )

    if callable(getattr(mediator, "io", None)):
        reply = mediator.io(routed_message)
        return _build_chat_payload(str(reply or ""), sender="Bot:", hashed_username=hashed_username)

    return _build_chat_payload(
        "I could not reach the chat model from this review surface. The selected filing context is attached, so you can retry after the router is available.",
        sender="Bot:",
        hashed_username=hashed_username,
    )


async def _process_chat_message_bounded(
    mediator: Any,
    message_text: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    hashed_username: Optional[str] = None,
    timeout_seconds: float = 12.0,
) -> Dict[str, Any]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _process_chat_message,
                mediator,
                message_text,
                payload,
                hashed_username=hashed_username,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        pass
    except Exception as exc:
        return _build_chat_payload(
            f"The chat assistant hit an error before answering: {exc}. Your complaint or filing context is still attached. You can retry, keep answering intake questions, or continue labeling the filing.",
            {"explanation": {"summary": "Router error fallback. Context was preserved for the next attempt."}},
            sender="Bot:",
            hashed_username=hashed_username,
        )
    return _build_chat_payload(
        "The chat assistant was slow, so backup mode answered instead. Your complaint or selected filing context is still attached. Retry the question when the router is ready, or keep answering questions and labeling documents.",
        {"explanation": {"summary": "Timeout fallback. Context was preserved so the user can retry or continue."}},
        sender="Bot:",
        hashed_username=hashed_username,
    )


def _initial_chat_payload(mediator: Any, *, hashed_username: Optional[str] = None) -> Dict[str, Any]:
    inquiry_payload: Dict[str, Any] = {}
    if callable(getattr(mediator, "get_current_inquiry_payload", None)):
        try:
            candidate = mediator.get_current_inquiry_payload()
            if isinstance(candidate, dict):
                inquiry_payload = candidate
        except Exception:
            inquiry_payload = {}
    return _build_chat_payload(
        "Please state your legal complaint",
        inquiry_payload,
        sender="Bot:",
        hashed_username=hashed_username,
    )


def attach_review_surface_chat_routes(app: FastAPI, mediator: Any) -> FastAPI:
    @app.post("/load_profile")
    async def load_profile(request: Request) -> JSONResponse:
        del request
        return JSONResponse({"error": "legacy_route_retired"}, status_code=401)

    @app.get("/cookies")
    async def cookies(request: Request) -> JSONResponse:
        del request
        return JSONResponse({"error": "legacy_route_retired"}, status_code=401)

    @app.post("/create_profile")
    async def create_profile() -> JSONResponse:
        return JSONResponse({"error": "legacy_route_retired"}, status_code=401)

    @app.post("/api/chat")
    async def post_chat(request: Request) -> JSONResponse:
        if getattr(request.state, "case_authorization", None) is None and getattr(request.app.state, "case_route_composition", None):
            return JSONResponse({"error": "authorizer_required"}, status_code=401)
        payload = await request.json()
        payload_dict = payload if isinstance(payload, dict) else {}
        message_text = str(payload_dict.get("message") or payload_dict.get("content") or "").strip()
        if not message_text:
            raise HTTPException(status_code=400, detail="message is required")
        response_payload = await _process_chat_message_bounded(
            mediator,
            message_text,
            payload_dict,
        )
        return JSONResponse({"messages": [response_payload], "context_attached": bool(payload_dict.get("chat_context"))})

    @app.post("/api/chat/fallback")
    async def chat_fallback(request: Request) -> JSONResponse:
        return await post_chat(request)

    @app.websocket("/api/chat")
    async def websocket_chat(websocket: WebSocket) -> None:
        if getattr(websocket.state, "case_authorization", None) is None and getattr(websocket.app.state, "case_route_composition", None):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        await websocket.send_json(_initial_chat_payload(mediator))
        try:
            while True:
                payload = await websocket.receive_json()
                payload_dict = payload if isinstance(payload, dict) else {}
                message_text = str(payload_dict.get("message") or payload_dict.get("content") or "").strip()
                if not message_text:
                    continue
                user_payload = _build_chat_payload(
                    message_text,
                    {
                        "sender": payload_dict.get("sender") or "User:",
                        "message": message_text,
                        "question": message_text,
                    },
                    sender="User:",
                )
                await websocket.send_json(user_payload)
                await websocket.send_json(
                    await _process_chat_message_bounded(
                        mediator,
                        message_text,
                        payload_dict,
                    )
                )
        except WebSocketDisconnect:
            return

    return app


def create_review_dashboard_app(authorizer: Any = None, *, browser_sessions: Any = None,
                                case_handlers: Any = None, json_body_limits: Any = None, case_catalog: Any = None, case_consent: Any = None, gui_inference_transport: Any = None, gui_inference_route: Any = None, case_reviews: Any = None, evidence_workspace: Any = None) -> FastAPI:
    app = FastAPI(title="Complaint Generator Review Dashboard")
    attach_static_asset_routes(app)
    attach_claim_support_review_ui_routes(app)
    attach_review_health_routes(app, "review-dashboard")
    compose_case_routes(
        app,
        authorizer=authorizer,
        mediator=None,
        include_workspace=False,
        include_review=False,
        include_document=False,
        browser_sessions=browser_sessions,
        case_handlers=case_handlers,
        json_body_limits=json_body_limits,
        case_catalog=case_catalog,
        case_consent=case_consent,
        gui_inference_transport=gui_inference_transport,
        gui_inference_route=gui_inference_route,
        case_reviews=case_reviews,
        evidence_workspace=evidence_workspace,
    )
    return app


def create_review_surface_app(mediator: Any, authorizer: Any = None, workspace_service: Any = None,
                              *, browser_sessions: Any = None, case_handlers: Any = None, json_body_limits: Any = None, case_catalog: Any = None, case_consent: Any = None, gui_inference_transport: Any = None, gui_inference_route: Any = None, case_reviews: Any = None, evidence_workspace: Any = None) -> FastAPI:
    app = FastAPI(title="Complaint Generator Review Surface")
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    attach_dashboard_ui_routes(app)
    attach_claim_support_review_ui_routes(app)
    attach_document_ui_routes(app)
    attach_review_health_routes(app, "review-surface")
    attach_review_surface_chat_routes(app, mediator)
    compose_case_routes(
        app,
        authorizer=authorizer,
        mediator=mediator,
        workspace_service=workspace_service,
        browser_sessions=browser_sessions,
        case_handlers=case_handlers,
        json_body_limits=json_body_limits,
        case_catalog=case_catalog,
        case_consent=case_consent,
        gui_inference_transport=gui_inference_transport,
        gui_inference_route=gui_inference_route,
        case_reviews=case_reviews,
        evidence_workspace=evidence_workspace,
    )
    return app
