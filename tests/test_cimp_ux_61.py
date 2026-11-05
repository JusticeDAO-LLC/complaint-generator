"""Fresh before/after screenshots from the public complaint handlers.

One pinned Chromium session walks the synthetic owner, lawyer, and admin
surfaces. Image bytes alone do not pass: each cell checks the live DOM, the
route, the viewport, and the pinned runtime, then the owned processes exit.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from applications.case_routes import CASE_PAGE_PATH, MESSAGE_INBOX_PATH
from applications.lawyer_workspace_api import LAWYER_WORKSPACE_PAGE
from tests import gui_native_browser as browser
from tests.gui_ux_overhaul_fixtures import (
    ADMIN_CREDENTIAL,
    BASELINE_DIR,
    CHAT_FACT,
    CONTRACT_PATH,
    DRAFT_NOTE,
    LAWYER_CREDENTIAL,
    OWNER_CREDENTIAL,
    assert_png,
    file_sha256,
    load_contract,
    matrix_cells,
    refuse_invented_evidence,
    synthetic_capture_world,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

CASE_LABEL = "owner-lawyer-journey"


def test_contract_preserves_baseline_story_and_required_states():
    contract = load_contract()
    manifest = json.loads((BASELINE_DIR / "screenshot_manifest.json").read_text(encoding="utf-8"))
    assert file_sha256(BASELINE_DIR / "screenshot_manifest.json") == contract["baseline_manifest_sha256"]
    assert contract["mock_api_used"] is False
    assert contract["diagnostic_test_panels_mounted"] is False
    assert contract["invented_evidence"] is False
    assert contract["synthetic_data_only"] is True
    assert manifest["mock_api_used"] is False
    assert manifest["synthetic_data_only"] is True
    baseline_ids = {item["id"] for item in manifest["screenshots"]}
    surfaces = {item["id"] for item in contract["surfaces"]}
    assert surfaces == {"owner", "lawyer", "admin", "chat", "evidence", "draft", "correspondence"}
    assert set(contract["viewports"]) == {"desktop", "tablet", "mobile"}
    assert contract["viewports"]["desktop"] == {"width": 1440, "height": 1000}
    assert contract["viewports"]["tablet"] == {"width": 768, "height": 1024}
    assert contract["viewports"]["mobile"] == {"width": 390, "height": 844}
    linked = set()
    for surface in contract["surfaces"]:
        assert surface["route"].startswith("/")
        assert surface["before_dom"] != surface["after_dom"]
        for baseline_id in surface["baseline_ids"]:
            assert baseline_id in baseline_ids
            linked.add(baseline_id)
    assert "02-workspace-desktop" in linked
    story = " ".join(contract["preserved_baseline_story"])
    assert "No case selected" in story
    assert "Receipt is not proof" in story
    assert "not a content-review bypass" in story
    limits = " ".join(manifest["observed_limits"])
    assert "No case selected" in limits
    cells = matrix_cells(contract)
    assert len(cells) == 7 * 2 * 3
    assert {cell["phase"] for cell in cells} == {"before", "after"}
    refuse_invented_evidence({
        "source": "public_asgi_handler",
        "route": "/cases",
        "mock_api_used": False,
        "diagnostic_test_panels_mounted": False,
    })
    with pytest.raises(ValueError, match="invented_or_real_evidence_refused"):
        refuse_invented_evidence({
            "source": "public_asgi_handler",
            "route": "/cases",
            "invented_evidence": True,
            "evidence_bytes": b"forged-exhibit",
        })
    with pytest.raises(ValueError, match="screenshot_blank_or_truncated"):
        assert_png(b"\x89PNG\r\n\x1a\n" + b"x" * 10)
    assert CONTRACT_PATH.is_file()


def test_stranger_cannot_read_owner_case_before_capture(tmp_path):
    world = synthetic_capture_world(tmp_path / "closed")
    case_id = world.case.case_id
    with TestClient(world.app, base_url="https://testserver") as stranger:
        logged = stranger.post(
            "/api/complaint-workspace/auth/login",
            json={"credential": "synthetic-stranger-credential"},
        )
        assert logged.status_code == 200, logged.text
        denied = stranger.get(f"/api/cases/{case_id}")
        assert denied.status_code == 404
        assert denied.json()["error"] == "missing_case"
        listed = stranger.get("/api/cases")
        assert listed.status_code == 200
        assert all(row["case_id"] != case_id for row in listed.json()["cases"])
        admin = stranger.get("/api/admin/accounts")
        assert admin.status_code in {401, 403}
    with TestClient(world.app, base_url="https://testserver") as admin_client:
        logged = admin_client.post(
            "/api/complaint-workspace/auth/login",
            json={"credential": ADMIN_CREDENTIAL},
        )
        assert logged.status_code == 200, logged.text
        accounts = admin_client.get("/api/admin/accounts")
        assert accounts.status_code == 200, accounts.text
        body = accounts.json()
        assert body["case_content"] is None
        assert body["evidence"] == []
        assert body["accounts"]
        assert case_id not in accounts.text


def _launch(tmp_path, monkeypatch, world):
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux61-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(12000)
    return page, playwright, context, node, chromium, profile


def _close(playwright, context, node, profile):
    context.close()
    playwright.stop()
    observed = browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], cleanup
    assert cleanup["remaining_pids"] == []
    return cleanup


def _shot(page, dest, width, height, dom_expr):
    page.set_viewport_size({"width": width, "height": height})
    measured = page.evaluate(
        """(expression) => ({
            width: window.innerWidth,
            height: window.innerHeight,
            ready: Boolean(eval(expression)),
            mockApi: typeof window.mockApi !== 'undefined',
            lawPanel: document.querySelector('#diagnostic-law-panel, [data-test-only-law-panel]') !== null,
        })""",
        dom_expr,
    )
    payload = page.screenshot(type="png", animations="disabled")
    dest.write_bytes(payload)
    digest = assert_png(payload)
    assert measured["width"] == width
    assert measured["height"] == height
    assert measured["ready"] is True, dom_expr
    assert measured["mockApi"] is False
    assert measured["lawPanel"] is False
    return digest


def _login_form(page, form_selector, field_selector, credential, status_selector, expected):
    page.fill(field_selector, credential)
    page.click(f"{form_selector} button[type=submit]")
    page.wait_for_function(
        "(spec) => document.querySelector(spec.selector).textContent.indexOf(spec.expected) >= 0",
        arg={"selector": status_selector, "expected": expected},
    )


def _prepare(page, surface, phase):
    origin = browser.SAME_ORIGIN
    if surface == "owner" and phase == "before":
        opened = page.goto(origin + CASE_PAGE_PATH, wait_until="domcontentloaded")
        assert opened.status == 200
        return
    if surface == "owner" and phase == "after":
        _login_form(page, "#case-login", "#case-credential", OWNER_CREDENTIAL, "#case-auth-status", "Signed in")
        page.click("#case-list button")
        page.wait_for_function(
            """(label) => {
                const actor = document.getElementById('complaint-case-shell-actor');
                const caseNode = document.getElementById('complaint-case-shell-case');
                return actor && actor.dataset.relationship === 'owner'
                    && caseNode && caseNode.dataset.bound === 'case';
            }""",
            arg=None,
        )
        page.click("[data-case-task='overview']")
        return
    if surface == "evidence" and phase == "before":
        page.click("[data-case-task='overview']")
        return
    if surface == "evidence" and phase == "after":
        page.click("[data-case-task='evidence']")
        page.wait_for_function(
            "() => document.querySelector('[data-case-panel=\"evidence\"]').textContent.indexOf('Receipt is not proof') >= 0"
        )
        return
    if surface == "draft" and phase == "before":
        page.click("[data-case-task='overview']")
        return
    if surface == "draft" and phase == "after":
        page.click("[data-case-task='draft']")
        page.wait_for_function(
            "() => document.querySelector('[data-case-panel=\"draft\"]').textContent.indexOf('No draft is stored') >= 0"
        )
        return
    if surface == "chat" and phase == "before":
        opened = page.goto(origin + "/chat", wait_until="domcontentloaded")
        assert opened.status == 200
        return
    if surface == "chat" and phase == "after":
        page.fill("#chat-form input", CHAT_FACT)
        return
    if surface == "correspondence" and phase == "before":
        opened = page.goto(origin + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
        assert opened.status == 200
        return
    if surface == "correspondence" and phase == "after":
        page.fill("#message-text", DRAFT_NOTE)
        return
    if surface == "lawyer" and phase == "before":
        page.context.clear_cookies()
        opened = page.goto(origin + LAWYER_WORKSPACE_PAGE, wait_until="domcontentloaded")
        assert opened.status == 200
        return
    if surface == "lawyer" and phase == "after":
        signed = page.evaluate(
            """async (credential) => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential}),
                });
                const body = await response.json();
                return {status: response.status, authenticated: body.authenticated === true};
            }""",
            LAWYER_CREDENTIAL,
        )
        assert signed["status"] == 200 and signed["authenticated"] is True
        page.fill("#review-credential", LAWYER_CREDENTIAL)
        closed = page.evaluate(
            """async () => {
                const response = await fetch('/api/cases/lawyer-workspace', {credentials: 'same-origin'});
                const text = await response.text();
                return {status: response.status, text};
            }"""
        )
        assert closed["status"] in {200, 403}
        assert CASE_LABEL not in closed["text"]
        assert "synthetic-owner" not in closed["text"].lower()
        return
    if surface == "admin" and phase == "before":
        page.context.clear_cookies()
        opened = page.goto(origin + "/admin", wait_until="domcontentloaded")
        assert opened.status == 200
        return
    if surface == "admin" and phase == "after":
        _login_form(page, "#admin-login", "#admin-credential", ADMIN_CREDENTIAL, "#admin-auth-status", "Signed in")
        page.wait_for_function(
            "() => document.getElementById('directory').hidden === false && document.querySelectorAll('#account-rows tr').length > 0"
        )
        withheld = page.evaluate("() => document.body.innerText")
        assert "Case content stays withheld" in withheld
        assert CASE_LABEL not in withheld
        return
    raise AssertionError(surface)


def test_live_matrix_captures_roles_and_viewports(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix_only"], denial
    contract = load_contract()
    world = synthetic_capture_world(tmp_path / "matrix")
    out = tmp_path / "captures"
    out.mkdir()
    assert BASELINE_DIR.resolve() not in out.resolve().parents
    page, playwright, context, node, chromium, profile = _launch(tmp_path, monkeypatch, world)
    records = []
    try:
        prepared = None
        for cell in matrix_cells(contract):
            step = (cell["surface"], cell["phase"])
            if step != prepared:
                _prepare(page, cell["surface"], cell["phase"])
                prepared = step
            dest = out / f"{cell['surface']}-{cell['phase']}-{cell['viewport']}.png"
            digest = _shot(page, dest, cell["width"], cell["height"], cell["dom"])
            record = {
                "source": "pinned_chromium_pipe",
                "route": cell["route"],
                "surface": cell["surface"],
                "phase": cell["phase"],
                "viewport": {"width": cell["width"], "height": cell["height"]},
                "sha256": digest,
                "mock_api_used": False,
                "diagnostic_test_panels_mounted": False,
                "runtime": {"node_sha256": node.sha256, "chromium_sha256": chromium.sha256},
            }
            refuse_invented_evidence(record)
            records.append(record)
        pairs = {}
        for record in records:
            pairs.setdefault((record["surface"], record["viewport"]["width"]), {})[record["phase"]] = record["sha256"]
        assert len(pairs) == 21
        for key, phases in pairs.items():
            assert phases["before"] != phases["after"], key
        routes = {record["route"] for record in records}
        assert routes == {"/cases", "/chat", "/case-messages", "/lawyer-workspace", "/admin"}
        assert len({record["runtime"]["node_sha256"] for record in records}) == 1
        assert len(records) == 42
        manifest_path = out / "capture_manifest.json"
        manifest_path.write_text(json.dumps({"captures": records, "network": denial["af_unix_only"]}, indent=2), encoding="utf-8")
        assert manifest_path.stat().st_size > 0
    finally:
        cleanup = _close(playwright, context, node, profile)
    assert cleanup["remaining_pids"] == []
