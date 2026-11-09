"""Bind the synthetic screenshot baseline to the live owner and staff app.

Chromium is the inherited pinned binary. HTTP is the same-origin pipe into
the composed ASGI handlers. Cases are new synthetic encrypted workspaces.
A canned mockApi and a diagnostic-only mount are not the subject.

The immutable source-bound screenshots record the original UX-01 split:
a real pending inquiry beside a stale case header or access-denied status.
The current live journey proves actual case/auth/inquiry bindings and accepts
a corrected coherent header without requiring that historical defect to stay.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import struct
from pathlib import Path

import pytest

from applications.admin_api import OperationalAdminService
from applications.case_routes import MESSAGE_INBOX_PATH
from applications.lawyer_workspace_api import LAWYER_WORKSPACE_API, LAWYER_WORKSPACE_PAGE
from integrations.private_storage import ENVELOPE_MAGIC
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "ux" / "complaint_ux_overhaul"
MANIFEST_PATH = DOC / "baseline" / "screenshot_manifest.json"
FINDINGS_PATH = DOC / "screenshot_driven_findings.json"
SOURCE_COMMIT = "6f27c60c3b49b8bad49088bd46e788fa31c646eb"
NARRATIVE = "On March 4, 2024 supervisor Alex Rivera fired me after I reported a safety concern at Northwind Tools."
MESSAGE = "Synthetic owner note for the assigned lawyer about the March 4 safety report."
ADMIN_CREDENTIAL = "synthetic-admin-credential"
DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}
ACTOR_BY_SCREEN = {
    "01-home-desktop": "public",
    "02-workspace-desktop": "owner",
    "03-mediator-question-desktop": "owner",
    "04-mediator-question-mobile": "owner",
    "05-evidence-composer-desktop": "owner",
    "06-evidence-composer-mobile": "owner",
    "07-draft-desktop": "owner",
    "08-cases-owner-desktop": "owner",
    "09-lawyer-workspace-desktop": "lawyer",
    "10-correspondence-owner-desktop": "owner",
    "11-correspondence-lawyer-mobile": "lawyer",
    "12-admin-accounts-desktop": "operational_admin",
    "13-admin-accounts-mobile": "operational_admin",
}


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _png_size(raw: bytes) -> tuple[int, int]:
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", raw[16:24])


@contextmanager
def _browser(tmp_path, monkeypatch, app):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    root = tmp_path / "ux01-profiles"
    root.mkdir(mode=0o700)
    playwright = None
    contexts = []
    observed = set()

    def open_page(name, viewport):
        profile = root / name
        profile.mkdir(mode=0o700)
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        contexts.append(context)
        browser._assert_process_custody(node, chromium, profile)
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        page.set_viewport_size(viewport)
        return page

    try:
        playwright = browser._load_sync_playwright()().start()
        yield open_page, bridge, node, chromium, denial
    finally:
        for context in contexts:
            context.close()
        if playwright is not None:
            playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(root), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []


def _arm_admin(world):
    admin = world.principals.install_server_role(role="operational_admin")
    world.sessions._adapter._credentials[ADMIN_CREDENTIAL] = admin.principal_id
    world.app.state.operational_admin = OperationalAdminService(
        principals=world.principals,
        sessions=world.sessions,
        clock=lambda: world.now["t"],
        audit_principal_ids=(admin.principal_id,),
        cases=world.cases,
        assignments=world.assignments,
        memberships=world.memberships,
    )
    world.admin = admin
    return world


def _login_fetch(page, credential):
    issued = page.evaluate(
        """async credential => {
            const response = await fetch('/api/complaint-workspace/auth/login', {
                method: 'POST', credentials: 'same-origin',
                headers: {'content-type': 'application/json'},
                body: JSON.stringify({credential})});
            const body = await response.json();
            return {ok: response.ok, status: response.status, body};
        }""",
        credential,
    )
    assert issued["ok"] is True, issued
    assert issued["body"]["authenticated"] is True
    page.evaluate("issued => window.workspaceClient.setBrowserSession(issued)", issued["body"])
    assert page.evaluate("() => typeof window.mockApi") == "undefined"
    return issued["body"]


def _case_payload(world):
    case = world.case
    return {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "revision": case.revision,
        "expected_revision": case.revision,
    }


def _is_intake_turn(response):
    if response.request.method != "POST":
        return False
    path = response.url.split("?")[0].rstrip("/")
    if path.endswith("/api/complaint-workspace/intake-chat"):
        return True
    if not path.endswith("/api/complaint-workspace/mcp/rpc") and not path.endswith("/api/complaint-workspace/mcp/call"):
        return False
    posted = response.request.post_data or ""
    return "complaint.run_intake_chat_turn" in posted and '"interview_action":"start"' in posted.replace(" ", "")


def _intake_payload(response):
    payload = response.json()
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        result = payload["result"]
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        return result
    return payload


def _header_snapshot(page):
    return page.evaluate(
        """() => {
            const header = document.getElementById('workspace-case-context-value');
            const status = document.getElementById('workspace-status');
            const summary = document.getElementById('workspace-error-summary');
            const pending = document.getElementById('adaptive-pending');
            return {
                header: header ? header.textContent.trim() : '',
                headerState: document.getElementById('workspace-case-context')?.dataset.state || '',
                status: status ? status.textContent.trim() : '',
                summaryHidden: summary ? summary.hidden : true,
                summaryText: summary ? summary.textContent.trim() : '',
                hydrated: document.body.dataset.workspaceHydrated || '',
                pending: pending ? pending.dataset.pending : '',
                inquiryId: pending ? (pending.dataset.inquiryId || '') : '',
                prompt: (document.getElementById('adaptive-pending-prompt') || {}).textContent || '',
                mockApi: typeof window.mockApi,
                diagnosticMounts: document.querySelectorAll('[data-fixture-owned-component]').length,
            };
        }"""
    )


def test_baseline_screenshots_bind_source_runtime_viewport_actor_and_state():
    manifest = _manifest()
    findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
    denial = browser.probe_inherited_network_denial()
    node, chromium = browser.pin_executables()
    assert denial["af_unix_only"] is True
    assert manifest["application_base_commit"] == SOURCE_COMMIT
    assert findings["application_base_commit"] == SOURCE_COMMIT
    assert hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest() == findings["screenshot_manifest_sha256"]
    assert manifest["synthetic_data_only"] is True
    assert manifest["mock_api_used"] is False
    assert manifest["provider_invoked"] is False
    assert manifest["runtime"]["transport"] == "actual_same_origin_http_to_asgi_over_pinned_cdp_pipe"
    assert manifest["runtime"]["inherited_network_denial"]["af_unix_only"] is True
    assert manifest["actual_route_counts"]["external_aborted"] == 0
    assert all(row["cleaned"] and row["remaining_pids"] == [] for row in manifest["cleanup"])
    assert {row["id"] for row in manifest["screenshots"]} == set(ACTOR_BY_SCREEN)
    stale = next(row for row in findings["findings"] if row["id"] == "UX-01")
    assert "No case selected" in stale["observed"]
    assert "access-denied" in stale["observed"] or "access denied" in stale["observed"]
    assert any("No case selected" in limit for limit in manifest["observed_limits"])
    historical_chromium = Path(manifest["runtime"]["chromium"]["path"])
    if historical_chromium.is_file():
        assert hashlib.sha256(historical_chromium.read_bytes()).hexdigest() == manifest["runtime"]["chromium"]["sha256"]
    historical_node = Path(manifest["runtime"]["node"]["path"])
    if historical_node.is_file():
        assert hashlib.sha256(historical_node.read_bytes()).hexdigest() == manifest["runtime"]["node"]["sha256"]
    assert Path(node.path).is_file() and Path(chromium.path).is_file()
    assert node.sha256 == hashlib.sha256(Path(node.path).read_bytes()).hexdigest()
    assert chromium.sha256 == hashlib.sha256(Path(chromium.path).read_bytes()).hexdigest()
    for row in manifest["screenshots"]:
        raw = (DOC / "baseline" / row["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        assert len(raw) == row["bytes"]
        assert _png_size(raw) == (row["viewport"]["width"], row["viewport"]["height"])
        assert row["viewport"]["width"] in {DESKTOP["width"], MOBILE["width"]}
        assert row["synthetic"] is True
        assert row["diagnostic_test_panels_mounted"] is False
        assert row["state"] and row["route"] and row["dom_checks"]
        assert ACTOR_BY_SCREEN[row["id"]]
    assert {ACTOR_BY_SCREEN[row["id"]] for row in manifest["screenshots"]} >= {
        "public", "owner", "lawyer", "operational_admin",
    }
    assert {row["viewport"]["width"] for row in manifest["screenshots"]} == {MOBILE["width"], DESKTOP["width"]}


def test_live_routes_bind_authenticated_inquiry_to_current_case(tmp_path, monkeypatch):
    world = _arm_admin(owner_lawyer_journey_world(tmp_path / "world"))
    with _browser(tmp_path, monkeypatch, world.app) as (open_page, bridge, node, chromium, denial):
        page = open_page("owner", DESKTOP)
        home = page.goto(browser.SAME_ORIGIN + "/", wait_until="domcontentloaded")
        assert home.status == 200
        assert page.locator("main, body").first.is_visible()
        assert page.evaluate("() => typeof window.mockApi") == "undefined"

        opened = page.goto(
            browser.SAME_ORIGIN + "/workspace?user_id=" + world.case.tenant_id,
            wait_until="domcontentloaded",
        )
        assert opened.status == 200
        page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
        before = _header_snapshot(page)
        assert before["mockApi"] == "undefined"
        assert before["diagnosticMounts"] == 0
        assert before["header"] == "No case selected"

        issued = _login_fetch(page, "synthetic-owner-credential")
        assert issued["principal_id"] == world.owner.principal_id
        page.evaluate(
            """async payload => {
                window.workspaceClient.setCaseContext(payload);
                await window.workspaceClient.bootstrapWorkspace(payload.tenant_id);
            }""",
            _case_payload(world),
        )
        page.fill("#adaptive-narrative", NARRATIVE)
        page.wait_for_function("() => typeof window.workspaceClient?.runIntakeChatTurn === 'function'")
        observed_posts = []

        def record_post(response):
            if response.request.method != "POST":
                return
            path = response.url.split("?")[0]
            if "/api/complaint-workspace/" not in path:
                return
            try:
                posted = response.request.post_data_json or {}
            except (ValueError, TypeError):
                posted = {}
            params = posted.get("params") or {}
            arguments = params.get("arguments") or {}
            observed_posts.append({"path": path, "status": response.status,
                "tool": params.get("name", ""), "action": arguments.get("interview_action", "")})

        page.on("response", record_post)
        try:
            with page.expect_response(_is_intake_turn) as started:
                page.click("#adaptive-enter-narrative")
        except Exception as error:
            state = page.evaluate("""() => ({
                hydrated: document.body.dataset.workspaceHydrated || '',
                privateInactive: workspacePrivacyInactive,
                sdkActive: window.workspaceClient._privacyActive,
                actorConfigured: Boolean(window.workspaceClient.activePrincipalId),
                caseConfigured: Boolean(window.workspaceClient.caseContext),
                requestCurrent: adaptiveRequestCurrent(adaptiveRequestCapture()),
                narrativePresent: Boolean(document.getElementById('adaptive-narrative').value.trim())
            })""")
            raise AssertionError({"inquiry_response_missing": True,
                "current_state": state, "actual_posts": observed_posts[-8:]}) from error
        finally:
            page.remove_listener("response", record_post)
        assert started.value.status == 200, started.value.text()
        started_body = _intake_payload(started.value)
        assert started_body.get("isError") is not True
        inquiry = started_body["adaptive_inquiry"]
        assert inquiry["pending"] is True
        assert inquiry["source"] == "shared_mediator"
        assert str(inquiry["inquiry_id"]).startswith("inq-")
        assert inquiry["prompt"]
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        desktop = _header_snapshot(page)
        assert desktop["pending"] == "true"
        assert desktop["inquiryId"] == inquiry["inquiry_id"]
        assert desktop["prompt"].strip()
        assert NARRATIVE not in desktop["prompt"]
        assert desktop["diagnosticMounts"] == 0

        actual_session = page.evaluate("async () => await window.workspaceClient.getSession()")["session"]
        assert actual_session["user_id"] == world.case.tenant_id
        assert actual_session["shared_interview"]["pending_inquiry"]["inquiry_id"] == inquiry["inquiry_id"]
        actor = page.evaluate("""async () => {
            const response = await fetch('/api/complaint-workspace/auth/session', {credentials: 'same-origin'});
            return {status: response.status, body: await response.json()};
        }""")
        assert actor["status"] == 200 and actor["body"]["authenticated"] is True
        assert actor["body"]["principal_id"] == world.owner.principal_id
        current_case = page.evaluate("() => window.workspaceClient.caseContext")
        assert current_case["tenant_id"] == world.case.tenant_id
        assert current_case["case_id"] == world.case.case_id
        assert current_case["resource_id"] == world.case.resource_id
        assert page.locator("#workspace-case-context").is_visible()
        assert page.locator("#workspace-status").is_visible()

        access_denied = "access denied" in desktop["status"].lower() or (
            not desktop["summaryHidden"] and "access denied" in desktop["summaryText"].lower())
        header_stale = desktop["header"] == "No case selected"
        header_matches_case = any(value in desktop["header"] for value in (
            world.case.case_id, world.case.tenant_id, "owner-lawyer-journey"))
        if header_stale:
            # Characterize the known unrefreshed page. The real backend and
            # inquiry assertions above remain required for this legacy state.
            assert desktop["headerState"] in {"empty", "error"}
            assert desktop["hydrated"] in {"denied", "error"}
        else:
            assert header_matches_case, "Current header must identify the actual authorized case"
        if not header_stale and not access_denied:
            assert desktop["headerState"] == "ready"
            assert desktop["hydrated"] in {"ready", "partial"}
            assert desktop["summaryHidden"] is True

        observation = {
            "id": "UX-01-current-observation",
            "historical_baseline_source_commit": SOURCE_COMMIT,
            "current_workspace_source_sha256": hashlib.sha256((ROOT / "templates" / "workspace.html").read_bytes()).hexdigest(),
            "runtime": {"node_sha256": node.sha256, "chromium_sha256": chromium.sha256, "transport": "pinned_pipe_asgi"},
            "inherited_af_unix_only": denial["af_unix_only"],
            "viewport": DESKTOP,
            "actor": "owner",
            "principal_id": actor["body"]["principal_id"],
            "case_id": current_case["case_id"],
            "state": "authenticated_pending_inquiry_with_measured_header",
            "inquiry_id": desktop["inquiryId"],
            "header": desktop["header"],
            "header_state": desktop["headerState"],
            "status": desktop["status"],
            "summary_text": desktop["summaryText"],
            "hydrated": desktop["hydrated"],
            "header_stale_no_case_selected": header_stale,
            "header_matches_current_case": header_matches_case,
            "access_denied_visible": access_denied,
            "known_legacy_defect_observed": header_stale or access_denied,
            "completion_authority": False,
        }
        (tmp_path / "current-case-observation.json").write_text(json.dumps(observation, indent=2) + "\n")

        page.set_viewport_size(MOBILE)
        mobile = _header_snapshot(page)
        assert mobile["pending"] == "true"
        assert mobile["inquiryId"] == desktop["inquiryId"]
        assert mobile["header"] == desktop["header"]
        shot = page.screenshot(full_page=False)
        assert _png_size(shot) == (MOBILE["width"], MOBILE["height"])
        page.set_viewport_size(DESKTOP)
        desktop_shot = page.screenshot(full_page=False)
        assert _png_size(desktop_shot) == (DESKTOP["width"], DESKTOP["height"])

        page.click('[data-tab-target="evidence"]')
        page.locator('[data-tab-panel="evidence"]').wait_for(state="visible")
        evidence_title = page.locator("#evidence-title")
        assert evidence_title.count() == 1
        assert evidence_title.is_visible() and evidence_title.is_enabled()
        evidence_title.fill("Synthetic unsaved safety email")
        assert evidence_title.input_value() == "Synthetic unsaved safety email"
        page.click('[data-tab-target="draft"]')
        page.locator('[data-tab-panel="draft"]').wait_for(state="visible")
        assert page.locator("#draft-status").is_visible()
        assert "No draft generated" in page.locator("#draft-status").text_content()

        sealed = [path for path in world.service._session_dir.rglob("*") if path.is_file() and path.read_bytes().startswith(ENVELOPE_MAGIC)]
        assert sealed
        assert all(NARRATIVE.encode() not in path.read_bytes() for path in sealed)

        stranger_denied = page.evaluate(
            """async () => {
                const response = await fetch('/api/admin/accounts', {credentials: 'same-origin'});
                const body = await response.json();
                return {status: response.status, body};
            }"""
        )
        assert stranger_denied["status"] in {401, 403}
        assert NARRATIVE not in json.dumps(stranger_denied["body"])

        page.goto(browser.SAME_ORIGIN + LAWYER_WORKSPACE_PAGE, wait_until="domcontentloaded")
        assert page.locator("#lawyer-workspace").count() == 1
        assert NARRATIVE not in page.locator("body").inner_text()
        closed = page.evaluate(
            """async path => {
                const response = await fetch(path, {credentials: 'same-origin'});
                const text = await response.text();
                return {status: response.status, text};
            }""",
            LAWYER_WORKSPACE_API,
        )
        assert closed["status"] != 200 or NARRATIVE not in closed["text"]
        assert NARRATIVE not in closed["text"]

        page.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
        page.fill("#inbox-credential", "synthetic-owner-credential")
        page.click("#inbox-login button[type=submit]")
        page.wait_for_function("document.getElementById('inbox-auth-status').textContent === 'Signed in'")
        page.fill("#case-id", world.case.case_id)
        page.click("#create-thread")
        page.wait_for_function("document.getElementById('thread-id').value.length > 0")
        thread = page.locator("#thread-id").input_value()
        page.fill("#message-text", MESSAGE)
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/" + thread + "/messages")) as sent:
            page.click("#send-message button[type=submit]")
        assert sent.value.status == 201
        body = sent.value.json()
        assert body["disposition"] == "conversation"
        page.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 1")
        assert MESSAGE in page.locator("#message-list").inner_text()

        lawyer = open_page("lawyer", MOBILE)
        lawyer.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
        lawyer.fill("#inbox-credential", "synthetic-lawyer-credential")
        lawyer.click("#inbox-login button[type=submit]")
        lawyer.wait_for_function("document.getElementById('inbox-auth-status').textContent === 'Signed in'")
        denied_thread = lawyer.evaluate(
            """async data => {
                const response = await fetch('/api/cases/' + data.caseId + '/threads/' + data.thread + '/messages', {credentials: 'same-origin'});
                let body = null;
                try { body = await response.json(); } catch (error) { body = null; }
                return {status: response.status, body};
            }""",
            {"caseId": world.case.case_id, "thread": thread},
        )
        assert denied_thread["status"] in {403, 404}
        assert MESSAGE not in json.dumps(denied_thread["body"])

        stranger = open_page("stranger", DESKTOP)
        stranger.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
        stranger.fill("#inbox-credential", "synthetic-stranger-credential")
        stranger.click("#inbox-login button[type=submit]")
        stranger.wait_for_function("document.getElementById('inbox-auth-status').textContent === 'Signed in'")
        stranger.fill("#case-id", world.case.case_id)
        stranger.fill("#thread-id", thread)
        with stranger.expect_response(lambda response: response.request.method == "GET" and thread in response.url) as hidden:
            stranger.click("#open-thread")
        assert hidden.value.status in {403, 404}
        assert MESSAGE not in stranger.locator("body").inner_text()

        admin = open_page("admin", DESKTOP)
        admin.goto(browser.SAME_ORIGIN + "/admin", wait_until="domcontentloaded")
        unauthenticated = admin.evaluate(
            """async () => {
                const response = await fetch('/api/admin/accounts', {credentials: 'same-origin'});
                return response.status;
            }"""
        )
        assert unauthenticated in {401, 403}
        admin.fill("#admin-credential", ADMIN_CREDENTIAL)
        admin.click("#admin-login button[type=submit]")
        admin.wait_for_function("document.getElementById('admin-auth-status').textContent === 'Signed in'")
        admin.wait_for_function("document.querySelectorAll('#account-rows tr').length > 0")
        rows = admin.locator("#account-rows").inner_text()
        assert world.owner.principal_id in rows
        assert world.admin.principal_id in rows
        assert NARRATIVE not in admin.locator("body").inner_text()
        assert MESSAGE not in admin.locator("body").inner_text()
        admin.set_viewport_size(MOBILE)
        assert admin.locator("#directory").is_visible()
        clip = admin.evaluate(
            """() => {
                const table = document.querySelector('#directory table');
                const box = table.getBoundingClientRect();
                return {scrollWidth: table.scrollWidth, clientWidth: table.clientWidth, wider: table.scrollWidth > table.clientWidth + 1, top: box.top};
            }"""
        )
        assert clip["clientWidth"] > 0
        mobile_admin = admin.screenshot(full_page=False)
        assert _png_size(mobile_admin) == (MOBILE["width"], MOBILE["height"])
        admin.set_viewport_size(DESKTOP)
        desktop_admin = admin.screenshot(full_page=False)
        assert _png_size(desktop_admin) == (DESKTOP["width"], DESKTOP["height"])

        bad = admin.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: 'not-a-real-credential'})});
                return response.status;
            }"""
        )
        assert bad == 401

        assert any(path.startswith("/api/complaint-workspace/") for path in bridge.same_origin_paths)
        assert any("/threads" in path or "/messages" in path for path in bridge.same_origin_paths)
        assert any(path.startswith("/api/admin/") for path in bridge.same_origin_paths)
        assert bridge.aborted_unqualified["websocket"] == []
        assert bridge.aborted_unqualified["sse"] == []
        assert node.sha256 and chromium.sha256
