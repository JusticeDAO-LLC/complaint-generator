import json
import os
import socket
import tempfile
import threading
import time
from urllib.parse import unquote
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
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import attach_complaint_workspace_routes
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
LAYOUT_AUDIT_VIEWPORT = {"width": 1440, "height": 1200}


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


def _build_fixture_app(
    mediator,
    profile_store: _FixtureProfileStore,
    workspace_service: ComplaintWorkspaceService,
) -> FastAPI:
    app = FastAPI(title="Website Cohesion Browser Fixture")

    attach_complaint_workspace_routes(app, workspace_service)
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

    @app.get("/workspace", response_class=HTMLResponse)
    async def workspace_page() -> str:
        return _load_template("workspace.html")

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

    @app.post("/api/chat/fallback")
    async def chat_fallback(request: Request) -> JSONResponse:
        payload = await request.json()
        sender = str(payload.get("sender") or FIXTURE_HASHED_USERNAME)
        message = str(payload.get("message") or "").strip()
        if not message:
            return JSONResponse({"messages": []})

        user_message = {"sender": sender, "message": message}
        bot_message = {
            "sender": "Bot:",
            "message": "Recorded your latest intake note for the complaint workflow.",
            "explanation": {
                "summary": "This keeps the chat, dashboard, and document builder working from the same complaint record.",
            },
        }
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
        return JSONResponse({"messages": [user_message, bot_message]})

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
    workspace_root = Path(tempfile.mkdtemp(prefix="complaint-workspace-browser-"))

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
    workspace_service = ComplaintWorkspaceService(root_dir=workspace_root)
    app = _build_fixture_app(mediator, profile_store, workspace_service)
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


def _create_account_from_root_iframe(page) -> None:
    page.click("#homepage-open-intake")
    page.wait_for_url("**/home")
    page.click("#create-form button")
    page.fill("#create-form .username_input", "ExampleUser1")
    page.fill("#create-form .password_input", "StrongPass1!")
    page.fill("#create-form .password_verify_input", "StrongPass1!")
    page.fill("#create-form .email_input", "jordan@example.com")
    page.click("#create-form button")


def _artifact_dir(target_dir: Path) -> Path:
    configured = os.environ.get("COMPLAINT_UI_SCREENSHOT_DIR", "").strip()
    if configured:
        return Path(configured)
    return target_dir


def _capture_screenshot(page, target_dir: Path, name: str) -> Path:
    target_dir = _artifact_dir(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = target_dir / f"{name}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    assert screenshot_path.exists()
    assert screenshot_path.stat().st_size > 0
    metadata_path = target_dir / f"{name}.json"
    metadata_path.write_text(
        json.dumps(
            {
                "name": name,
                "url": page.url,
                "title": page.title(),
                "viewport": dict(page.viewport_size or LAYOUT_AUDIT_VIEWPORT),
                "text_excerpt": page.locator("body").inner_text()[:4000],
                "screenshot_path": str(screenshot_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return screenshot_path


def _assert_surface_layout(page, *, min_content_height: int = 160) -> None:
    metrics = page.evaluate(
        """() => {
            const body = document.body;
            const root = document.documentElement;
            const navLinks = Array.from(document.querySelectorAll('a[href]'))
                .map((node) => String(node.textContent || '').trim())
                .filter(Boolean);
            const mainLike = document.querySelector('main, .shell, .workspace, .hero, .container, body');
            const primaryAction = document.querySelector('button, a[href="/document"], a[href="/claim-support-review"]');
            const rect = mainLike ? mainLike.getBoundingClientRect() : null;
            return {
                viewportWidth: window.innerWidth,
                scrollWidth: Math.max(body.scrollWidth, root.scrollWidth),
                scrollHeight: Math.max(body.scrollHeight, root.scrollHeight),
                renderedWidth: Math.max(body.clientWidth, root.clientWidth),
                navCount: navLinks.length,
                hasBuilderLink: navLinks.includes('Builder') || !!document.querySelector('a[href="/document"]'),
                hasReviewLink: navLinks.includes('Review') || !!document.querySelector('a[href="/claim-support-review"]'),
                hasPrimaryAction: !!primaryAction,
                contentHeight: Math.max(rect ? rect.height : 0, body.scrollHeight, root.scrollHeight),
                contentWidth: Math.max(rect ? rect.width : 0, body.scrollWidth, root.scrollWidth),
            };
        }"""
    )
    assert metrics["navCount"] >= 2
    assert metrics["hasBuilderLink"]
    assert metrics["hasReviewLink"]
    assert metrics["hasPrimaryAction"]
    assert metrics["contentHeight"] >= min_content_height
    assert metrics["contentWidth"] >= 300
    assert metrics["renderedWidth"] <= metrics["viewportWidth"] + 4


def _wait_for_surface(page, path: str) -> None:
    if path == "/":
        page.wait_for_function(
            """() => {
                const bodyText = document.body ? document.body.innerText.toLowerCase() : '';
                return bodyText.includes('lex publicus complaint generator')
                    && bodyText.includes('three simple steps')
                    && bodyText.includes('choose your next step');
            }"""
        )
        return
    if path == "/home":
        page.wait_for_function("() => document.body && document.body.innerText.trim().length > 20")
        return
    if path == "/chat":
        page.wait_for_function(
            "() => document.getElementById('messages').innerText.includes('Tell me what happened')"
        )
        return
    if path == "/profile":
        page.wait_for_function(
            "() => document.getElementById('profile_data').innerText.includes('browser-smoke-text-link')"
        )
        return
    if path == "/results":
        page.wait_for_function(
            "() => document.getElementById('profile_data').innerText.includes('browser-smoke-text-link')"
        )
        return
    if path == "/workspace":
        page.wait_for_function(
            "() => document.getElementById('sdk-server-info').innerText.includes('complaint-workspace-mcp')"
        )
        return
    if path.startswith("/claim-support-review"):
        page.wait_for_function(
            "() => document.getElementById('raw-output').textContent.includes('retaliation')"
        )
        return
    if path.startswith("/document"):
        page.wait_for_function(
            "() => document.body.innerText.includes('Generate Formal Complaint')"
        )
        return


def test_legacy_site_pages_share_profile_state_and_navigation():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, _mediator = _launch_fixture_site()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()

            page.goto(base_url)
            page.wait_for_function(
                """() => {
                    const bodyText = document.body ? document.body.innerText.toLowerCase() : '';
                    return bodyText.includes('lex publicus complaint generator')
                        && bodyText.includes('three simple steps');
                }"""
            )
            assert page.locator("a[href='/claim-support-review']").count() >= 1
            assert page.locator("a[href='/document']").count() >= 1
            assert page.locator("a[href='/workspace']").count() >= 1
            assert page.locator("#homepage-open-intake").count() == 1
            assert page.locator("a[href='/home']").count() >= 1
            body_text = page.locator("body").inner_text()
            assert "Build your complaint one step at a time." in body_text
            assert "A guided path through the complaint process" in body_text

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


def test_root_landing_routes_into_secure_intake_and_connected_surfaces_after_signup():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, _mediator = _launch_fixture_site()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()

            page.goto(base_url)
            page.wait_for_function(
                """() => {
                    const bodyText = document.body ? document.body.innerText.toLowerCase() : '';
                    return bodyText.includes('lex publicus complaint generator')
                        && bodyText.includes('three simple steps')
                        && bodyText.includes('choose your next step');
                }"""
            )
            assert page.locator("#homepage-open-intake").count() == 1
            assert page.locator("a[href='/home']").count() >= 1
            assert page.locator("a[href='/workspace']").count() >= 1
            assert page.locator("a[href='/claim-support-review']").count() >= 1
            assert page.locator("a[href='/document']").count() >= 1
            assert page.locator("#homepage-resume-review").count() == 1
            assert page.locator("#homepage-open-workspace").count() == 1

            _create_account_from_root_iframe(page)

            page.wait_for_url(f"{base_url}/chat")
            assert page.locator("a[href='/claim-support-review']").count() >= 1
            assert page.locator("a[href='/document']").count() >= 1

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


def test_review_dashboard_banner_routes_back_to_document_builder_with_claim_context():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, mediator = _launch_fixture_site()
    status_payload = mediator.get_three_phase_status.return_value
    status_payload["next_action"] = {"action": "generate_formal_complaint"}
    status_payload["claim_support_packet_summary"] = {
        **dict(status_payload.get("claim_support_packet_summary") or {}),
        "claim_count": 1,
        "element_count": 3,
        "draft_ready_element_ratio": 1.0,
        "proof_readiness_score": 0.98,
    }

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()

            _create_account_and_open_chat(page, base_url)
            page.goto(
                f"{base_url}/claim-support-review?claim_type=retaliation&user_id={FIXTURE_HASHED_USERNAME}"
            )
            page.wait_for_function(
                "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
            )

            next_action_banner = page.locator("#intake-next-action-banner").inner_text()
            assert "Generate formal complaint" in next_action_banner
            assert "recommended action: generate_formal_complaint" in next_action_banner
            assert "claims: 1" in next_action_banner
            assert "elements: 3" in next_action_banner
            assert "proof readiness: 0.98" in next_action_banner

            page.click("#intake-next-action-open-formal-generator")
            page.wait_for_url(
                f"{base_url}/document?claim_type=retaliation&user_id={FIXTURE_HASHED_USERNAME}"
            )

            document_text = page.locator("body").inner_text()
            assert "Formal Complaint Builder" in document_text
            assert "Generate Formal Complaint" in document_text

            browser.close()


def test_shared_builder_and_review_shortcuts_connect_the_site_surfaces():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, _mediator = _launch_fixture_site()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()

            _create_account_and_open_chat(page, base_url)

            pages_with_shared_shortcuts = [
                "/",
                "/chat",
                "/results",
                "/document",
                f"/claim-support-review?claim_type=retaliation&user_id={FIXTURE_HASHED_USERNAME}",
            ]

            for path in pages_with_shared_shortcuts:
                page.goto(f"{base_url}{path}")
                if path.startswith("/claim-support-review"):
                    page.wait_for_function(
                        "() => document.getElementById('raw-output').textContent.includes('retaliation')"
                    )
                elif path == "/results":
                    page.wait_for_function(
                        "() => document.getElementById('profile_data').innerText.includes('browser-smoke-text-link')"
                    )
                elif path == "/chat":
                    page.wait_for_function(
                        "() => document.getElementById('messages').innerText.includes('Tell me what happened')"
                    )
                elif path == "/":
                    page.wait_for_function(
                        """() => {
                            const bodyText = document.body ? document.body.innerText.toLowerCase() : '';
                            return bodyText.includes('lex publicus complaint generator')
                                && bodyText.includes('three simple steps')
                                && bodyText.includes('choose your next step');
                        }"""
                    )

                assert page.locator("a[href='/document']").count() >= 1
                assert page.locator("a[href='/claim-support-review']").count() >= 1

            page.goto(f"{base_url}/document")
            page.click("a[href='/claim-support-review']")
            page.wait_for_url(f"{base_url}/claim-support-review")

            page.click("a[href='/document']")
            page.wait_for_url(f"{base_url}/document")

            browser.close()


def test_workspace_page_uses_mcp_sdk_tools_for_connected_complaint_flow():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, _mediator = _launch_fixture_site()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()

            page.goto(f"{base_url}/workspace")
            page.wait_for_function(
                "() => document.getElementById('sdk-server-info').innerText.includes('complaint-workspace-mcp')"
            )
            page.wait_for_function(
                "() => document.getElementById('tool-list').innerText.includes('complaint.generate_complaint')"
            )

            page.fill("#intake-party_name", "Jordan Example")
            page.fill("#intake-opposing_party", "Acme Corporation")
            page.fill("#intake-protected_activity", "Reported discrimination to HR")
            page.fill("#intake-adverse_action", "Terminated two days later")
            page.fill("#intake-timeline", "Complaint on March 8, termination on March 10")
            page.fill("#intake-harm", "Lost wages and emotional distress")
            page.click("#save-intake-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Intake answers saved.')"
            )
            page.wait_for_function(
                "() => document.getElementById('supported-count').innerText !== '0'"
            )
            page.wait_for_function(
                "() => document.getElementById('progress-percent-chip').innerText !== '0% ready'"
            )
            assert "intake questionnaire has been answered" in page.locator("#progress-step-intake").inner_text().lower()
            page.wait_for_function(
                "() => document.getElementById('action-button').innerText.includes('Go to draft')"
            )
            assert "Generate the complaint draft" in page.locator("#action-title").inner_text()
            page.fill(
                "#case-synopsis",
                "Jordan Example alleges retaliation after reporting discrimination to HR, with the strongest current support on timeline and the biggest remaining question around corroboration.",
            )
            page.click("#save-synopsis-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Shared case synopsis saved.')"
            )
            workspace_user_id = page.locator("#did-chip").inner_text().replace("did: ", "").strip()
            page.click("#action-button")
            assert "is-active" in page.locator("button[data-tab-target='draft']").get_attribute("class")
            assert "Jordan Example alleges retaliation" in page.locator("#draft-synopsis-preview").inner_text()
            assert page.locator("#draft-title").evaluate("(node) => document.activeElement === node") is True

            page.click("button[data-tab-target='integrations']")
            integrations_text = page.locator("[data-tab-panel='integrations']").inner_text()
            assert "complaint-generator-workspace session" in integrations_text
            assert "complaint-generator-mcp" in integrations_text
            assert "window.ComplaintMcpSdk.ComplaintMcpClient" in integrations_text

            page.click("button[data-tab-target='review']")
            assert "Jordan Example alleges retaliation" in page.locator("#review-synopsis-preview").inner_text()

            page.click("button[data-tab-target='evidence']")
            page.select_option("#evidence-kind", "testimony")
            page.select_option("#evidence-claim-element", "causation")
            page.fill("#evidence-title", "Timeline statement")
            page.fill("#evidence-source", "Witness interview")
            page.fill(
                "#evidence-content",
                "A witness confirmed the termination followed immediately after the HR report.",
            )
            page.click("#save-evidence-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Evidence saved')"
            )
            assert "Timeline statement" in page.locator("#evidence-list").inner_text()

            page.click("button[data-tab-target='draft']")
            page.fill("#requested-relief", "Back pay\nInjunctive relief")
            page.click("#generate-draft-button")
            page.wait_for_function(
                "() => document.getElementById('draft-preview').innerText.includes('Jordan Example brings this retaliation complaint against Acme Corporation.')"
            )
            draft_text = page.locator("#draft-preview").inner_text()
            assert "Reported discrimination to HR" in draft_text
            assert "Back pay; Injunctive relief." in draft_text

            page.fill("#draft-title", "Custom retaliation complaint")
            page.fill("#draft-body", "Custom revised complaint body.")
            page.click("#save-draft-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Draft edits saved.')"
            )
            assert page.locator("#draft-preview").inner_text() == "Custom revised complaint body."

            page.goto(f"{base_url}/claim-support-review?claim_type=retaliation&workspace_user_id={workspace_user_id}")
            page.wait_for_function(
                "() => document.getElementById('shared-case-synopsis-text').innerText.includes('Jordan Example alleges retaliation')"
            )
            review_edit_href = page.locator("#shared-case-synopsis-edit-link").get_attribute("href")
            assert review_edit_href is not None
            assert f"user_id={workspace_user_id}" in unquote(review_edit_href)
            page.click("#shared-case-synopsis-edit-link")
            page.wait_for_url(f"{base_url}/workspace**")
            page.wait_for_function(
                "() => document.activeElement && document.activeElement.id === 'case-synopsis'"
            )
            assert "Jordan Example alleges retaliation" in page.locator("#case-synopsis").input_value()

            page.goto(f"{base_url}/document?user_id={workspace_user_id}")
            page.wait_for_function(
                "() => document.getElementById('builder-synopsis-text').innerText.includes('Jordan Example alleges retaliation')"
            )
            builder_edit_href = page.locator("#builder-synopsis-edit-link").get_attribute("href")
            assert builder_edit_href is not None
            assert f"user_id={workspace_user_id}" in unquote(builder_edit_href)

            browser.close()


def test_user_interfaces_capture_screenshots_and_preserve_coherent_layout(tmp_path):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, _mediator = _launch_fixture_site()
    screenshot_dir = tmp_path / "playwright-ui-snapshots"

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page(viewport=LAYOUT_AUDIT_VIEWPORT)

            _create_account_and_open_chat(page, base_url)

            page.goto(f"{base_url}/document")
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

            audited_surfaces = [
                ("/", "landing"),
                ("/home", "account"),
                ("/chat", "chat"),
                ("/profile", "profile"),
                ("/results", "results"),
                ("/workspace", "workspace"),
                (f"/claim-support-review?claim_type=retaliation&user_id={FIXTURE_HASHED_USERNAME}", "review"),
                ("/document", "document"),
            ]

            screenshot_paths = []
            for path, name in audited_surfaces:
                page.goto(f"{base_url}{path}")
                _wait_for_surface(page, path)
                _assert_surface_layout(page)
                screenshot_paths.append(_capture_screenshot(page, screenshot_dir, name))

            assert len(screenshot_paths) == len(audited_surfaces)
            assert all(path.exists() and path.stat().st_size > 0 for path in screenshot_paths)

            browser.close()


def test_workspace_feature_flow_captures_screenshots_for_full_complaint_generator_journey(tmp_path):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, _mediator = _launch_fixture_site()
    screenshot_dir = tmp_path / "playwright-complaint-feature-snapshots"

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page(viewport=LAYOUT_AUDIT_VIEWPORT)

            _create_account_and_open_chat(page, base_url)

            feature_screenshots = []

            page.goto(f"{base_url}/")
            _wait_for_surface(page, "/")
            _assert_surface_layout(page)
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "landing"))

            page.goto(f"{base_url}/chat")
            _wait_for_surface(page, "/chat")
            _assert_surface_layout(page)
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "chat"))

            page.goto(f"{base_url}/profile")
            _wait_for_surface(page, "/profile")
            _assert_surface_layout(page)
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "profile"))

            page.goto(f"{base_url}/workspace")
            _wait_for_surface(page, "/workspace")
            _assert_surface_layout(page, min_content_height=320)
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "workspace-intake"))

            page.fill("#intake-party_name", "Jordan Example")
            page.fill("#intake-opposing_party", "Acme Corporation")
            page.fill("#intake-protected_activity", "Reported discrimination to HR")
            page.fill("#intake-adverse_action", "Termination two days later")
            page.fill("#intake-timeline", "Reported discrimination on March 8 and was terminated on March 10")
            page.fill("#intake-harm", "Lost wages and benefits")
            page.click("#save-intake-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Intake answers saved.')"
            )

            page.get_by_role("button", name="Evidence", exact=True).click()
            page.select_option("#evidence-kind", "document")
            page.select_option("#evidence-claim-element", "causation")
            page.fill("#evidence-title", "Termination email")
            page.fill("#evidence-source", "Inbox export")
            page.fill("#evidence-content", "Termination followed within two days of the HR complaint.")
            page.click("#save-evidence-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Evidence saved and support review refreshed.')"
            )
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "workspace-evidence"))

            page.get_by_role("button", name="Draft", exact=True).click()
            page.fill("#draft-title", "Jordan Example v. Acme Corporation Complaint")
            page.fill("#requested-relief", "Back pay\nInjunctive relief")
            page.click("#generate-draft-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Complaint draft generated from intake and evidence.')"
            )
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "workspace-draft"))

            page.get_by_role("button", name="CLI + MCP", exact=True).click()
            page.wait_for_function(
                "() => document.getElementById('tool-list').innerText.includes('complaint.generate_complaint')"
            )
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "workspace-cli-mcp"))

            page.get_by_role("button", name="UX Audit", exact=True).click()
            page.wait_for_function(
                "() => document.getElementById('ux-review-pytest-target').value.includes('test_dashboard_end_to_end_complaint_journey_uses_chat_review_builder_and_optimizer')"
            )
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "workspace-ux-review"))

            review_path = f"/claim-support-review?claim_type=retaliation&user_id={FIXTURE_HASHED_USERNAME}"
            page.goto(f"{base_url}{review_path}")
            _wait_for_surface(page, review_path)
            _assert_surface_layout(page)
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "review"))

            page.goto(f"{base_url}/document")
            _wait_for_surface(page, "/document")
            _assert_surface_layout(page)
            feature_screenshots.append(_capture_screenshot(page, screenshot_dir, "builder"))

            assert len(feature_screenshots) == 10
            assert all(path.exists() and path.stat().st_size > 0 for path in feature_screenshots)

            browser.close()


def test_dashboard_end_to_end_complaint_journey_uses_chat_review_builder_and_optimizer(tmp_path):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    app, _mediator = _launch_fixture_site()
    screenshot_dir = tmp_path / "playwright-dashboard-e2e"

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page(viewport=LAYOUT_AUDIT_VIEWPORT)

            _create_account_and_open_chat(page, base_url)
            _assert_surface_layout(page, min_content_height=320)
            _capture_screenshot(page, screenshot_dir, "chat-initial")

            page.fill("#chat-form input", "My supervisor threatened termination after I reported discrimination to HR.")
            page.click("#send")
            page.wait_for_function(
                "() => document.getElementById('messages').innerText.includes('My supervisor threatened termination after I reported discrimination to HR.')"
            )
            page.wait_for_function(
                "() => document.getElementById('messages').innerText.includes('Recorded your latest intake note for the complaint workflow.')"
            )
            _capture_screenshot(page, screenshot_dir, "chat-testimony")

            page.goto(f"{base_url}/workspace")
            _wait_for_surface(page, "/workspace")
            _assert_surface_layout(page, min_content_height=320)
            page.fill("#intake-party_name", "Jordan Example")
            page.fill("#intake-opposing_party", "Acme Corporation")
            page.fill("#intake-protected_activity", "Reported discrimination to HR")
            page.fill("#intake-adverse_action", "Termination two days later")
            page.fill("#intake-timeline", "Reported discrimination on March 8 and the termination came on March 10")
            page.fill("#intake-harm", "Lost wages, benefits, and emotional distress")
            page.click("#save-intake-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Intake answers saved.')"
            )
            page.fill(
                "#case-synopsis",
                "Jordan Example alleges retaliation after reporting discrimination, with direct testimony in chat, a targeted review record, and a timeline-supported draft path.",
            )
            page.click("#save-synopsis-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Shared case synopsis saved.')"
            )
            workspace_user_id = page.locator("#did-chip").inner_text().replace("did: ", "").strip()
            page.click("#handoff-chat-button")
            page.wait_for_url(f"{base_url}/chat**")
            page.wait_for_function(
                "() => !document.getElementById('chat-context-card').hidden"
            )
            page.wait_for_function(
                "() => document.getElementById('chat-context-summary').innerText.includes('Jordan Example alleges retaliation')"
            )
            page.wait_for_function(
                "() => document.querySelector('#chat-form input').value.includes('Mediator, help turn this into testimony-ready narrative')"
            )
            page.wait_for_function(
                "() => document.getElementById('chat-context-return-link').getAttribute('href').includes('/workspace')"
            )
            _capture_screenshot(page, screenshot_dir, "chat-handoff")

            page.goto(f"{base_url}/workspace?user_id={workspace_user_id}")
            page.wait_for_function(
                "() => document.getElementById('case-synopsis').value.includes('Jordan Example alleges retaliation')"
            )
            _capture_screenshot(page, screenshot_dir, "workspace-intake")

            page.get_by_role("button", name="Review", exact=True).click()
            page.wait_for_function(
                "() => document.getElementById('support-grid').innerText.toLowerCase().includes('causal link')"
            )
            page.click("#shortcut-evidence-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Opened Evidence so support can be attached to the case theory.')"
            )
            assert "is-active" in page.locator("button[data-tab-target='evidence']").get_attribute("class")
            page.select_option("#evidence-claim-element", "causation")
            page.fill("#evidence-title", "Termination email")
            page.select_option("#evidence-kind", "document")
            page.fill("#evidence-source", "Inbox export")
            page.fill("#evidence-content", "Termination email sent within two days of the HR complaint.")
            page.click("#save-evidence-button")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').innerText.includes('Evidence saved and support review refreshed.')"
            )
            page.wait_for_function(
                "() => document.getElementById('evidence-list').innerText.includes('Termination email')"
            )
            _capture_screenshot(page, screenshot_dir, "workspace-evidence")

            page.goto(
                f"{base_url}/claim-support-review?claim_type=retaliation&user_id={FIXTURE_HASHED_USERNAME}&workspace_user_id={workspace_user_id}"
            )
            _wait_for_surface(page, f"/claim-support-review?claim_type=retaliation&user_id={FIXTURE_HASHED_USERNAME}")
            _assert_surface_layout(page, min_content_height=320)
            page.fill("#testimony-element-id", "retaliation:1")
            page.fill("#testimony-element-text", "Protected activity")
            page.fill("#testimony-event-date", "2026-03-08")
            page.fill("#testimony-actor", "Supervisor")
            page.fill("#testimony-act", "Threatened termination")
            page.fill("#testimony-target", "Jordan Example")
            page.fill("#testimony-harm", "Retaliatory pressure and job loss")
            page.fill("#testimony-confidence", "0.92")
            page.select_option("#testimony-firsthand-status", "firsthand")
            page.fill(
                "#testimony-narrative",
                "I reported discrimination to HR, and my supervisor threatened termination before I was fired two days later.",
            )
            page.click("#save-testimony-button")
            page.wait_for_function(
                "() => document.getElementById('testimony-list').innerText.includes('Protected activity')"
            )
            page.wait_for_function(
                "() => document.getElementById('raw-output').innerText.includes('retaliation:1')"
            )
            assert page.locator("#shared-case-synopsis-card").count() == 1
            _capture_screenshot(page, screenshot_dir, "review-testimony")

            page.goto(f"{base_url}/workspace?user_id={workspace_user_id}&target_tab=draft")
            page.wait_for_function(
                "() => document.getElementById('draft-synopsis-preview').innerText.includes('Jordan Example alleges retaliation')"
            )
            page.fill("#draft-title", "Jordan Example v. Acme Corporation Complaint")
            page.fill("#requested-relief", "Back pay\nCompensatory damages\nInjunctive relief")
            page.click("#generate-draft-button")
            page.wait_for_function(
                "() => document.getElementById('draft-preview').innerText.includes('Jordan Example brings this retaliation complaint against Acme Corporation.')"
            )
            page.wait_for_function(
                "() => document.getElementById('draft-preview').innerText.includes('Working case synopsis: Jordan Example alleges retaliation')"
            )
            _capture_screenshot(page, screenshot_dir, "workspace-draft")

            page.get_by_role("button", name="UX Audit", exact=True).click()
            page.wait_for_function(
                "() => document.getElementById('ux-review-pytest-target').value.includes('test_dashboard_end_to_end_complaint_journey_uses_chat_review_builder_and_optimizer')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-method').value === 'actor_critic'"
            )
            _capture_screenshot(page, screenshot_dir, "workspace-optimizer")

            page.goto(f"{base_url}/document?user_id={workspace_user_id}")
            _wait_for_surface(page, "/document")
            _assert_surface_layout(page)
            page.fill("#district", "Northern District of California")
            page.fill("#plaintiffs", "Jordan Example")
            page.fill("#defendants", "Acme Corporation")
            page.fill("#requestedRelief", "Back pay\nCompensatory damages")
            page.fill("#signerName", "Jordan Example")
            page.fill("#signerTitle", "Plaintiff, Pro Se")
            page.click("#generateButton")
            page.wait_for_function(
                "() => document.getElementById('previewRoot').innerText.includes('Plaintiff alleges retaliation')"
            )
            page.wait_for_function(
                "() => document.getElementById('builder-synopsis-text').innerText.includes('Jordan Example alleges retaliation')"
            )
            _capture_screenshot(page, screenshot_dir, "builder-generated")

            artifact_paths = sorted(screenshot_dir.glob("*.png"))
            assert len(artifact_paths) >= 7
            assert all(path.exists() and path.stat().st_size > 0 for path in artifact_paths)

            browser.close()
