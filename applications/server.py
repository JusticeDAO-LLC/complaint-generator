import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from .case_routes import compose_case_routes
from .dashboard_ui import attach_dashboard_ui_routes
from .document_ui import load_document_html
from .review_ui import attach_claim_support_review_ui_routes, attach_static_asset_routes


def _read_template(filename: str) -> str:
    path = Path(__file__).resolve().parent.parent / "templates" / filename
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


class SERVER:
    def __init__(self, mediator: Any, authorizer: Any = None, workspace_service: Any = None,
                 *, browser_sessions: Any = None, case_handlers: Any = None, json_body_limits: Any = None, case_catalog: Any = None, case_consent: Any = None, gui_inference_transport: Any = None, gui_inference_route: Any = None, case_reviews: Any = None, evidence_workspace: Any = None):
        self.mediator = mediator
        self.authorizer = authorizer
        self.app = self._build_app(mediator, authorizer, workspace_service=workspace_service,
                                   browser_sessions=browser_sessions, case_handlers=case_handlers, json_body_limits=json_body_limits, case_catalog=case_catalog, case_consent=case_consent, gui_inference_transport=gui_inference_transport, gui_inference_route=gui_inference_route, case_reviews=case_reviews, evidence_workspace=evidence_workspace)

    @staticmethod
    def build_chat_payload(
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

    @classmethod
    def process_chat_message(
        cls,
        mediator: Any,
        message_text: str,
        *,
        hashed_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        if callable(getattr(mediator, "io_payload", None)):
            payload = mediator.io_payload(message_text)
            return cls.build_chat_payload(
                str((payload or {}).get("message") or ""),
                payload if isinstance(payload, dict) else None,
                sender="Bot:",
                hashed_username=hashed_username,
            )

        if callable(getattr(mediator, "io", None)):
            reply = mediator.io(message_text)
            return cls.build_chat_payload(str(reply or ""), sender="Bot:", hashed_username=hashed_username)

        return cls.build_chat_payload("", sender="Bot:", hashed_username=hashed_username)

    @classmethod
    def _build_initial_chat_payload(
        cls,
        mediator: Any,
        *,
        hashed_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        inquiry_payload: Dict[str, Any] = {}
        if callable(getattr(mediator, "get_current_inquiry_payload", None)):
            try:
                candidate = mediator.get_current_inquiry_payload()
                if isinstance(candidate, dict):
                    inquiry_payload = candidate
            except Exception:
                inquiry_payload = {}
        return cls.build_chat_payload(
            "Please state your legal complaint",
            inquiry_payload,
            sender="Bot:",
            hashed_username=hashed_username,
        )

    def _build_app(self, mediator: Any, authorizer: Any = None, workspace_service: Any = None,
                   *, browser_sessions: Any = None, case_handlers: Any = None, json_body_limits: Any = None, case_catalog: Any = None, case_consent: Any = None, gui_inference_transport: Any = None, gui_inference_route: Any = None, case_reviews: Any = None, evidence_workspace: Any = None) -> FastAPI:
        app = FastAPI()
        attach_static_asset_routes(app)
        attach_claim_support_review_ui_routes(app)
        attach_dashboard_ui_routes(app)

        @app.get("/health")
        async def health() -> Dict[str, str]:
            return {"status": "healthy"}

        @app.get("/", response_class=HTMLResponse)
        @app.get("", response_class=HTMLResponse)
        async def index() -> str:
            return _read_template("index.html")

        @app.get("/home", response_class=HTMLResponse)
        async def home() -> str:
            return _read_template("home.html")

        @app.get("/profile", response_class=HTMLResponse)
        async def profile() -> str:
            return _read_template("profile.html")

        @app.get("/document", response_class=HTMLResponse)
        async def document() -> str:
            return load_document_html()

        @app.get("/results", response_class=HTMLResponse)
        async def results() -> str:
            return _read_template("results.html")

        @app.get("/workspace", response_class=HTMLResponse)
        async def workspace() -> str:
            return _read_template("workspace.html")

        @app.get("/mlwysiwyg", response_class=HTMLResponse)
        async def mlwysiwyg() -> str:
            return _read_template("MLWYSIWYG.html")

        @app.get("/chat", response_class=HTMLResponse)
        async def chat() -> str:
            return _read_template("chat.html")

        @app.get("/cookies")
        async def cookies(request: Request) -> JSONResponse:
            del request
            return JSONResponse({"error": "legacy_route_retired"}, status_code=401)

        @app.post("/load_profile")
        async def load_profile(request: Request) -> JSONResponse:
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
            message_text = str(payload.get("message") or payload.get("content") or "").strip()
            if not message_text:
                raise HTTPException(status_code=400, detail="message is required")
            response_payload = self.process_chat_message(mediator, message_text)
            return JSONResponse(response_payload)

        @app.post("/api/chat/fallback")
        async def chat_fallback(request: Request) -> JSONResponse:
            return await post_chat(request)

        @app.websocket("/api/chat")
        async def websocket_chat(websocket: WebSocket) -> None:
            if getattr(websocket.state, "case_authorization", None) is None and getattr(websocket.app.state, "case_route_composition", None):
                await websocket.close(code=1008)
                return
            await websocket.accept()
            initial_payload = self._build_initial_chat_payload(mediator)
            await websocket.send_json(initial_payload)
            try:
                while True:
                    data = await websocket.receive_json()
                    message_text = str(data.get("message") or data.get("content") or "").strip()
                    if not message_text:
                        continue
                    user_payload = self.build_chat_payload(
                        message_text,
                        {"sender": "User:", "message": message_text, "question": message_text},
                        sender="User:",
                    )
                    await websocket.send_json(user_payload)
                    bot_payload = self.process_chat_message(mediator, message_text)
                    await websocket.send_json(bot_payload)
            except WebSocketDisconnect:
                return

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

    def run(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: bool = False,
    ) -> None:
        import uvicorn

        uvicorn.run(
            self.app,
            host=host or "0.0.0.0",
            port=port or int(os.getenv("COMPLAINT_GENERATOR_PORT", "19030")),
            reload=reload,
        )
