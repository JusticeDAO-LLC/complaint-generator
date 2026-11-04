"""Keyboard, focus, screen-reader structure, contrast, and motion.

Real case, conversation, and workspace pages expose labelled headings,
keyboard dialogs that return focus, polite announcements, and readable
error and locked states. Hidden duplicates stay out of the tab order.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_assignment_api import CaseAssignmentService
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.case_message_api import CaseMessageService
from applications.case_messages import CaseMessageStore
from applications.case_routes import CASE_PAGE_PATH, MESSAGE_INBOX_PATH, CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "static"
PRIVATE = "synthetic-private-narrative-orchid-ux45"
STACK = 'Traceback (most recent call last):\n  File "/tmp/secret_case_ux45.py", line 2, in hidden\nNameError: private'


def _world(tmp_path):
    now = {"t": 1_700_000_450}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    principals.install_server_role(role="lawyer")
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=clock,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
        principals=principals, cases=cases, memberships=memberships,
    )
    messages = CaseMessageStore(
        tmp_path / "messages", key=os.urandom(32), key_id="message-key",
        principals=principals, cases=cases, memberships=memberships, clock=clock,
    )
    assignments = CaseAssignmentService(
        principals=principals, cases=cases, memberships=memberships, key_grants=key_grants,
        sessions={}, clock=clock,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {"synthetic-owner-credential-ux45": owner.principal_id}),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    app = FastAPI()

    @app.get("/api/ux45/locked-probe")
    async def locked_probe():
        return JSONResponse(status_code=423, content={
            "error": "locked",
            "stack": STACK,
            "narrative": PRIVATE,
        })

    @app.get("/api/ux45/broken-probe")
    async def broken_probe():
        return JSONResponse(status_code=500, content={
            "error": "draft_failed",
            "stack": STACK,
            "narrative": PRIVATE,
        })

    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, case_messages=CaseMessageService(messages),
        case_handlers=CaseHandlerRegistry(),
        include_workspace=False, include_review=False, include_document=False,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="ux45-static")
    return SimpleNamespace(app=app, owner=owner)


def _contrast(rgb_a, rgb_b):
    def channel(value):
        value = value / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def luminance(color):
        red, green, blue = [channel(part) for part in color]
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    lighter = max(luminance(rgb_a), luminance(rgb_b))
    darker = min(luminance(rgb_a), luminance(rgb_b))
    return (lighter + 0.05) / (darker + 0.05)


def test_pages_name_chat_evidence_draft_review_and_invitations():
    workspace = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    cases = (ROOT / "templates" / "cases.html").read_text(encoding="utf-8")
    messages = (ROOT / "templates" / "case_messages.html").read_text(encoding="utf-8")
    style = (STATIC_ROOT / "complaint_case_shell.css").read_text(encoding="utf-8")
    script = (STATIC_ROOT / "complaint_case_shell.js").read_text(encoding="utf-8")
    assert 'id="evidence-library"' in workspace
    assert 'for="evidence-annotation-note"' in workspace
    assert 'id="evidence-source-review-title"' in workspace
    assert 'id="draft-heading"' in workspace
    assert 'id="invitation-dialog"' in cases
    assert 'for="message-text"' in messages
    assert "prefers-reduced-motion" in style
    assert "prefers-contrast" in style
    assert "openQualifiedDialog" in script
    assert cases.count('id="invitation-dialog"') == 1
    assert 'id="review-invitation"' in cases
    assert "complaint-a11y-live" in script


def test_browser_keyboard_focus_contrast_and_locked_states(tmp_path, monkeypatch):
    world = _world(tmp_path)
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix_only"], "the trusted executor must fence this child"
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux45-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
    try:
        opened = page.goto(browser.SAME_ORIGIN + CASE_PAGE_PATH, wait_until="domcontentloaded")
        assert opened.status == 200
        page.wait_for_selector("#complaint-case-shell-next")
        page.wait_for_function(
            "() => document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'",
            timeout=8000,
        )
        structure = page.evaluate(
            """() => {
                const heading = document.querySelector('main h1');
                const label = document.querySelector('label[for="case-credential"]');
                const field = document.getElementById('case-credential');
                const duplicates = document.querySelectorAll('#invitation-dialog').length;
                const hiddenTasks = [...document.querySelectorAll('.case-shell__task[hidden]')];
                return {
                    heading: heading ? heading.textContent.trim() : '',
                    labelled: !!(label && field && label.htmlFor === field.id),
                    duplicates,
                    hiddenTab: hiddenTasks.map(node => node.tabIndex),
                    live: !!document.getElementById('complaint-a11y-live'),
                };
            }"""
        )
        assert structure["heading"] == "Your cases"
        assert structure["labelled"] is True
        assert structure["duplicates"] == 1
        assert structure["live"] is True
        assert all(index < 0 for index in structure["hiddenTab"])

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function(
            "() => document.documentElement.dataset.caseViewport === 'mobile'",
            timeout=4000,
        )
        mobile_hidden = page.evaluate(
            """() => [...document.querySelectorAll('.case-shell__task[hidden]')].every(node => node.tabIndex < 0)"""
        )
        assert mobile_hidden is True
        page.set_viewport_size({"width": 1280, "height": 900})

        opener = page.locator("#review-invitation")
        opener.focus()
        opened_dialog = page.evaluate(
            """() => window.complaintCaseShell.openQualifiedDialog('invitation-dialog', document.getElementById('review-invitation'))"""
        )
        assert opened_dialog is True
        assert page.evaluate("() => document.getElementById('invitation-dialog').open") is True
        assert "Invite a participant" in page.evaluate("() => document.getElementById('complaint-a11y-live').textContent")
        page.keyboard.press("Tab")
        inside = page.evaluate(
            """() => {
                const dialog = document.getElementById('invitation-dialog');
                return dialog.open && dialog.contains(document.activeElement);
            }"""
        )
        assert inside is True
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.getElementById('invitation-dialog').open", timeout=4000)
        assert page.evaluate("() => document.activeElement && document.activeElement.id") == "review-invitation"
        assert "Closed" in page.evaluate("() => document.getElementById('complaint-a11y-live').textContent")

        page.emulate_media(reduced_motion="reduce", contrast="more")
        motion = page.evaluate(
            """() => {
                const shell = document.querySelector('.case-shell');
                const button = document.getElementById('complaint-case-shell-next');
                const shellStyle = getComputedStyle(shell);
                const buttonStyle = getComputedStyle(button);
                const parse = (value) => value.match(/\\d+/g).map(Number);
                return {
                    transition: shellStyle.transitionDuration,
                    animation: shellStyle.animationName,
                    color: parse(buttonStyle.color),
                    background: parse(buttonStyle.backgroundColor),
                };
            }"""
        )
        assert motion["transition"].startswith("0s")
        assert motion["animation"] in ("none", "")
        assert _contrast(motion["color"][:3], motion["background"][:3]) >= 4.5

        zoom = page.evaluate(
            """() => {
                document.documentElement.style.fontSize = '200%';
                const button = document.getElementById('complaint-case-shell-next');
                const rect = button.getBoundingClientRect();
                const label = document.querySelector('label[for="lawyer-select"]');
                return {
                    height: rect.height,
                    visible: rect.width > 0 && rect.height > 0,
                    label: label ? label.textContent.trim() : '',
                    clipped: button.closest('[hidden]') !== null,
                };
            }"""
        )
        assert zoom["visible"] is True
        assert zoom["height"] >= 44
        assert zoom["label"] == "Lawyer"
        assert zoom["clipped"] is False

        messages = page.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
        assert messages.status == 200
        page.wait_for_selector("#message-text")
        page.fill("#message-text", "synthetic-unsent-chat-ux45")
        locked = page.evaluate(
            """async () => {
                const response = await fetch('/api/ux45/locked-probe', {credentials: 'same-origin'});
                await new Promise(resolve => setTimeout(resolve, 40));
                const surface = document.getElementById('complaint-state-surface');
                return {
                    status: response.status,
                    kind: surface.dataset.kind,
                    text: surface.innerText,
                    composer: document.getElementById('message-text').value,
                    keyVisible: !document.getElementById('complaint-state-check-key').hidden,
                };
            }"""
        )
        assert locked["status"] == 423
        assert locked["kind"] == "locked"
        assert "Private key access is locked" in locked["text"]
        assert "Traceback" not in locked["text"]
        assert PRIVATE not in locked["text"]
        assert locked["composer"] == "synthetic-unsent-chat-ux45"
        assert locked["keyVisible"] is True
        page.locator("#complaint-state-check-key").focus()
        assert page.evaluate("() => document.activeElement.id") == "complaint-state-check-key"

        failed = page.evaluate(
            """async () => {
                const response = await fetch('/api/ux45/broken-probe', {credentials: 'same-origin'});
                await new Promise(resolve => setTimeout(resolve, 40));
                const surface = document.getElementById('complaint-state-surface');
                return {status: response.status, kind: surface.dataset.kind, text: surface.innerText};
            }"""
        )
        assert failed["status"] == 500
        assert failed["kind"] == "error"
        assert "did not finish" in failed["text"]
        assert "Traceback" not in failed["text"]

        workspace = page.goto(browser.SAME_ORIGIN + "/case-grants", wait_until="domcontentloaded")
        assert workspace.status == 200
        landmarks = page.evaluate(
            """() => ({
                evidence: !!document.getElementById('evidence-library'),
                annotation: !!document.querySelector('label[for="evidence-annotation-note"]'),
                source: (document.getElementById('evidence-source-review-title') || {}).textContent || '',
                draft: (document.getElementById('draft-heading') || {}).textContent || '',
                dialogs: document.querySelectorAll('#evidence-annotation-editor').length,
                shellNext: document.querySelectorAll('#complaint-case-shell-next').length,
            })"""
        )
        assert landmarks["evidence"] is True
        assert landmarks["annotation"] is True
        assert landmarks["source"] == "Source review"
        assert landmarks["draft"] == "Draft and Edit"
        assert landmarks["dialogs"] == 1
        assert landmarks["shellNext"] == 1
        page.evaluate(
            """() => window.complaintCaseShell.openQualifiedDialog('evidence-annotation-editor', document.getElementById('complaint-case-shell-next'))"""
        )
        assert page.evaluate("() => document.getElementById('evidence-annotation-editor').contains(document.activeElement)") is True
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.getElementById('evidence-annotation-editor').open", timeout=4000)
        assert page.evaluate("() => document.activeElement.id") == "complaint-case-shell-next"
    finally:
        context.close()
        playwright.stop()
