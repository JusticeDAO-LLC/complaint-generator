import json
import socket
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

requests = pytest.importorskip("requests")
uvicorn = pytest.importorskip("uvicorn")
FastAPI = pytest.importorskip("fastapi").FastAPI
Request = pytest.importorskip("fastapi").Request
WebSocket = pytest.importorskip("fastapi").WebSocket
WebSocketDisconnect = pytest.importorskip("fastapi").WebSocketDisconnect
HTMLResponse = pytest.importorskip("fastapi.responses").HTMLResponse
JSONResponse = pytest.importorskip("fastapi.responses").JSONResponse
Response = pytest.importorskip("fastapi.responses").Response

from applications.document_api import attach_document_routes
from applications.document_ui import attach_document_ui_routes
from applications.review_api import attach_claim_support_review_routes
from applications.review_ui import attach_claim_support_review_ui_routes, attach_review_health_routes
from tests.test_claim_support_review_playwright_smoke import _build_hook_backed_browser_mediator


pytestmark = [pytest.mark.no_auto_network, pytest.mark.browser]

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
STATIC_DIR = REPO_ROOT / "static"
FIXTURE_HASHED_USERNAME = "browser-smoke-text-link"
FIXTURE_HASHED_PASSWORD = "browser-smoke-password"
FIXTURE_TOKEN = "fixture-token"


class _FixtureProfileStore:
    def __init__(self) -> None:
        self.profile_data = {
            "hashed_username": FIXTURE_HASHED_USERNAME,
            "hashed_password": FIXTURE_HASHED_PASSWORD,
            "name": "Jordan Example",
            "email": "jordan@example.com",
            "chat_history": {
                "2026-03-22 00:00:00": {
                    "sender": "Bot:",
                    "message": "Tell me what happened so we can organize your complaint.",
                    "explanation": {
                        "summary": "The intake flow starts by collecting the core complaint narrative.",
                    },
                }
            },
            "candidate_claims": [
                {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.87},
            ],
            "requested_relief": [
                "Compensatory damages",
                "Injunctive relief",
            ],
        }
        self.username = "ExampleUser1"
        self.password = "StrongPass1!"

    def create_profile(self, username: str, password: str, email: str) -> dict:
        self.username = username
        self.password = password
        self.profile_data["email"] = email
        return {
            "hashed_username": FIXTURE_HASHED_USERNAME,
            "hashed_password": FIXTURE_HASHED_PASSWORD,
            "status_code": 200,
        }

    def _matches_raw_credentials(self, username: str | None, password: str | None) -> bool:
        return bool(username) and bool(password) and (
            (username == self.username and password == self.password)
            or (username == FIXTURE_HASHED_USERNAME and password == FIXTURE_HASHED_PASSWORD)
        )

    def _matches_hashed_credentials(self, hashed_username: str | None, hashed_password: str | None) -> bool:
        return (
            hashed_username == FIXTURE_HASHED_USERNAME
            and hashed_password == FIXTURE_HASHED_PASSWORD
        )

    def load_profile(self, payload: dict) -> tuple[dict | None, bool]:
        request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else payload
        if not isinstance(request_payload, dict):
            return None, False

        hashed_username = request_payload.get("hashed_username")
        hashed_password = request_payload.get("hashed_password")
        if self._matches_hashed_credentials(hashed_username, hashed_password):
            return dict(self.profile_data), True

        username = request_payload.get("username")
        password = request_payload.get("password")
        if self._matches_raw_credentials(username, password):
            return dict(self.profile_data), False

        return None, False

    def append_chat_message(self, sender: str, message: str, explanation: str = "") -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        self.profile_data["chat_history"][timestamp] = {
            "sender": sender,
            "message": message,
            "explanation": {"summary": explanation} if explanation else {},
        }


def _load_template(template_name: str) -> str:
    template = (TEMPLATES_DIR / template_name).read_text()
    template = template.replace('hostname = "http://localhost:19000";', "hostname = window.location.origin;")
    template = template.replace('hostname = "localhost:19000";', "hostname = window.location.origin;")
    template = template.replace("alert(JSON.stringify(testdata));", "console.log(JSON.stringify(testdata));")
    return template


def _load_static_asset(asset_name: str) -> str:
    asset = (STATIC_DIR / asset_name).read_text()
    if asset_name == "chat.js":
        asset = asset.replace('const hostname = "localhost:19000";', "const hostname = window.location.host;")
    return asset


def _build_document_payload(**kwargs) -> dict:
    user_id = str(kwargs.get("user_id") or FIXTURE_HASHED_USERNAME)
    plaintiff_names = list(kwargs.get("plaintiff_names") or ["Jordan Example"])
    defendant_names = list(kwargs.get("defendant_names") or ["Acme Corporation"])
    requested_relief = list(kwargs.get("requested_relief") or ["Compensatory damages"])
    dashboard_url = f"/claim-support-review?claim_type=retaliation&user_id={user_id}"

    return {
        "generated_at": "2026-03-22T12:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": plaintiff_names,
                "defendants": defendant_names,
            },
            "summary_of_facts": [
                "Plaintiff reported workplace misconduct and then experienced retaliation."
            ],
            "factual_allegation_paragraphs": [
                "1. Plaintiff reported workplace misconduct and then experienced retaliation."
            ],
            "legal_standards": [
                "Retaliation claims require protected activity, adverse action, and causal connection."
            ],
            "claims_for_relief": [
                "Retaliation",
            ],
            "requested_relief": requested_relief,
            "draft_text": (
                "Plaintiff alleges retaliation after reporting misconduct and seeks relief for the resulting harm."
            ),
            "exhibits": [],
        },
        "drafting_readiness": {
            "status": "ready",
            "sections": {},
            "claims": [],
            "warning_count": 0,
        },
        "filing_checklist": [],
        "review_intent": {
            "user_id": user_id,
            "claim_type": "retaliation",
            "review_url": dashboard_url,
        },
        "review_links": {
            "dashboard_url": dashboard_url,
            "workflow_priority": {
                "status": "ready",
                "title": "Drafting is aligned with the complaint review flow",
                "description": "The complaint builder can hand off directly into the review dashboard for final support checks.",
                "action_label": "Open Review Dashboard",
                "action_url": dashboard_url,
                "action_kind": "link",
                "dashboard_url": dashboard_url,
                "chip_labels": [
                    "workflow phase: document generation",
                    "recommended action: generate_formal_complaint",
                    "focus claim: Retaliation",
                ],
            },
            "intake_case_summary": {
                "next_action": {
                    "action": "generate_formal_complaint",
                    "claim_type": "retaliation",
                },
                "claim_support_packet_summary": {
                    "proof_readiness_score": 0.98,
                },
            },
            "intake_status": {
                "current_phase": "document_generation",
                "ready_to_advance": True,
                "remaining_gap_count": 0,
                "contradiction_count": 0,
                "blockers": [],
                "contradictions": [],
            },
        },
    }


def _build_fixture_app(mediator, profile_store: _FixtureProfileStore) -> FastAPI:
    app = FastAPI(title="Website Cohesion Browser Fixture")

    attach_claim_support_review_routes(app, mediator)
    attach_claim_support_review_ui_routes(app)
    attach_document_routes(app, mediator)
    attach_document_ui_routes(app)
    attach_review_health_routes(app, "website-cohesion-browser-fixture")

    @app.get("/", response_class=HTMLResponse)
    async def index_page() -> str:
        return _load_template("index.html")

    @app.get("/home", response_class=HTMLResponse)
    @app.get("/home/", response_class=HTMLResponse)
    async def home_page() -> str:
        return _load_template("home.html")

    @app.get("/chat", response_class=HTMLResponse)
    async def chat_page() -> str:
        return _load_template("chat.html")

    @app.get("/profile", response_class=HTMLResponse)
    async def profile_page() -> str:
        return _load_template("profile.html")

    @app.get("/results", response_class=HTMLResponse)
    async def results_page() -> str:
        return _load_template("results.html")

    @app.get("/cookies")
    async def cookies_page(request: Request) -> Response:
        return Response(json.dumps(dict(request.cookies)), media_type="text/plain")

    @app.get("/static/{asset_name:path}")
    async def static_asset(asset_name: str) -> Response:
        asset_path = STATIC_DIR / asset_name
        if not asset_path.is_file():
            return Response(status_code=404)
        media_type = "application/javascript" if asset_path.suffix == ".js" else "text/plain"
        return Response(_load_static_asset(asset_name), media_type=media_type)

    @app.post("/create_profile")
    async def create_profile(request: Request) -> JSONResponse:
        payload = await request.json()
        request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        username = str(request_payload.get("username") or profile_store.username)
        password = str(request_payload.get("password") or profile_store.password)
        email = str(request_payload.get("email") or profile_store.profile_data["email"])
        result = profile_store.create_profile(username, password, email)
        response = JSONResponse(result)
        response.set_cookie("hashed_username", FIXTURE_HASHED_USERNAME)
        response.set_cookie("hashed_password", FIXTURE_HASHED_PASSWORD)
        response.set_cookie("token", FIXTURE_TOKEN)
        return response

    @app.post("/load_profile")
    async def load_profile(request: Request) -> JSONResponse:
        payload = await request.json()
        profile, hashed_request = profile_store.load_profile(payload)
        if profile is None:
            return JSONResponse({"Err": "Invalid Credentials"}, status_code=403)

        profile_json = json.dumps(profile)
        if hashed_request:
            body = {
                "hashed_username": FIXTURE_HASHED_USERNAME,
                "hashed_password": FIXTURE_HASHED_PASSWORD,
                "data": profile_json,
            }
        else:
            body = {
                "results": {
                    "hashed_username": FIXTURE_HASHED_USERNAME,
                    "hashed_password": FIXTURE_HASHED_PASSWORD,
                    "data": profile_json,
                }
            }
        response = JSONResponse(body)
        response.set_cookie("hashed_username", FIXTURE_HASHED_USERNAME)
        response.set_cookie("hashed_password", FIXTURE_HASHED_PASSWORD)
        response.set_cookie("token", FIXTURE_TOKEN)
        return response

    @app.websocket("/api/chat")
    async def chat_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                raw_message = await websocket.receive_text()
                payload = json.loads(raw_message)
                sender = str(payload.get("sender") or FIXTURE_HASHED_USERNAME)
                message = str(payload.get("message") or "").strip()
                if not message:
                    continue
                profile_store.append_chat_message(
                    sender,
                    message,
                    "The chat transcript stays attached to the complaint profile.",
                )
                profile_store.append_chat_message(
                    "Bot:",
                    "Recorded your latest intake note for the complaint workflow.",
                    "This keeps the chat, dashboard, and document builder working from the same complaint record.",
                )
                await websocket.send_text(json.dumps({"sender": sender, "message": message}))
                await websocket.send_text(
                    json.dumps(
                        {
                            "sender": "Bot:",
                            "message": "Recorded your latest intake note for the complaint workflow.",
                            "explanation": {
                                "summary": (
                                    "This keeps the chat, dashboard, and document builder working from the same complaint record."
                                )
                            },
                        }
                    )
                )
        except WebSocketDisconnect:
            return

    return app


@contextmanager
def _serve_app(app: FastAPI):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{host}:{port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=0.5)
            if response.ok:
                break
        except Exception:
            pass
        time.sleep(0.1)
    else:  # pragma: no cover - startup hard failure
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Timed out waiting for browser fixture app")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _launch_fixture_site():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    mediator, _hook = _build_hook_backed_browser_mediator(db_path)
    mediator.save_claim_testimony_record(
        user_id=FIXTURE_HASHED_USERNAME,
        claim_type="retaliation",
        claim_element_text="Protected activity",
        raw_narrative="Seeded browser fixture testimony so the dashboard can build review coverage from the same complaint profile.",
        firsthand_status="firsthand",
        source_confidence=0.9,
    )
    mediator.build_formal_complaint_document_package.side_effect = _build_document_payload
    profile_store = _FixtureProfileStore()
    app = _build_fixture_app(mediator, profile_store)
    return app, mediator


def _create_account_and_open_chat(page, base_url: str) -> None:
    page.goto(f"{base_url}/home")
    page.click("#create-form button")
    page.fill("#create-form .username_input", "ExampleUser1")
    page.fill("#create-form .password_input", "StrongPass1!")
    page.fill("#create-form .password_verify_input", "StrongPass1!")
    page.fill("#create-form .email_input", "jordan@example.com")
    page.click("#create-form button")
    page.wait_for_url(f"{base_url}/chat")
    page.wait_for_function(
        "() => document.getElementById('messages').innerText.includes('Tell me what happened')"
    )


def test_legacy_site_pages_share_profile_state_and_navigation():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, _mediator = _launch_fixture_site()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()

            page.goto(base_url)
            assert page.locator("a[href='/claim-support-review']").count() >= 1
            assert page.locator("a[href='/document']").count() >= 1
            assert page.locator("iframe[src='/home/']").count() == 1

            _create_account_and_open_chat(page, base_url)

            chat_text = page.locator("#messages").inner_text()
            assert "Tell me what happened so we can organize your complaint." in chat_text
            assert page.locator("a[href='/document']").count() >= 1
            assert page.locator("a[href='/claim-support-review']").count() >= 1

            page.goto(f"{base_url}/profile")
            page.wait_for_function(
                "() => document.getElementById('profile_data').innerText.includes('browser-smoke-text-link')"
            )
            profile_text = page.locator("#profile_data").inner_text()
            history_text = page.locator("#chat_history").inner_text()
            assert "browser-smoke-text-link" in profile_text
            assert "Tell me what happened so we can organize your complaint." in history_text

            page.goto(f"{base_url}/results")
            page.wait_for_function(
                "() => document.getElementById('profile_data').innerText.includes('browser-smoke-text-link')"
            )
            results_text = page.locator("#profile_data").inner_text()
            assert "browser-smoke-text-link" in results_text
            assert page.locator("a[href='/document']").count() >= 1
            assert page.locator("a[href='/claim-support-review']").count() >= 1

            browser.close()


def test_document_and_review_surfaces_complete_single_site_generation_flow():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, mediator = _launch_fixture_site()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()

            _create_account_and_open_chat(page, base_url)

            page.click("a[href='/document']")
            page.wait_for_url(f"{base_url}/document")

            page.fill("#district", "Northern District of California")
            page.fill("#plaintiffs", "Jordan Example")
            page.fill("#defendants", "Acme Corporation")
            page.fill("#requestedRelief", "Compensatory damages")
            page.fill("#signerName", "Jordan Example")
            page.fill("#signerTitle", "Plaintiff, Pro Se")
            page.click("#generateButton")

            page.wait_for_function(
                "() => document.getElementById('previewRoot').innerText.includes('Plaintiff alleges retaliation')"
            )
            preview_text = page.locator("#previewRoot").inner_text()
            page.wait_for_function(
                """() => Array.from(document.querySelectorAll('#previewRoot a[data-review-intent-link="true"]'))
                .some((node) => String(node.getAttribute('href') || '').includes('/claim-support-review'))"""
            )
            review_link = page.locator("#previewRoot a[data-review-intent-link='true']").first
            review_href = review_link.get_attribute("href") or ""

            assert "Plaintiff alleges retaliation" in preview_text
            assert "/claim-support-review" in review_href
            assert f"user_id={FIXTURE_HASHED_USERNAME}" in review_href

            mediator.build_formal_complaint_document_package.assert_called_once()
            call_kwargs = mediator.build_formal_complaint_document_package.call_args.kwargs
            assert call_kwargs["district"] == "Northern District of California"
            assert call_kwargs["plaintiff_names"] == ["Jordan Example"]
            assert call_kwargs["defendant_names"] == ["Acme Corporation"]
            assert call_kwargs["requested_relief"] == ["Compensatory damages"]
            assert call_kwargs["user_id"] == FIXTURE_HASHED_USERNAME

            review_link.click()
            page.wait_for_url(f"{base_url}/claim-support-review*")
            page.wait_for_function(
                "() => document.getElementById('raw-output').textContent.includes('retaliation')"
            )

            dashboard_text = page.locator("body").inner_text()
            assert "OPERATOR REVIEW SURFACE" in dashboard_text
            assert "Protected activity" in dashboard_text
            assert "Causal connection" in dashboard_text

            page.click("a[href='/document']")
            page.wait_for_url(f"{base_url}/document")
            assert "Generate Formal Complaint" in page.locator("body").inner_text()

            browser.close()
