"""Authenticated case and workspace screens stay labeled, focusable, and narrow-safe.

Chromium renders the real templates through the Task 02 same-origin ASGI bridge.
Contrast, empty, loading, and error states come from that DOM. A missing static
asset is reported in place; the page does not invent replacement markup.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_directory import CaseDirectory
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore
from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
WRONG_CREDENTIAL = "synthetic-not-a-credential"
ROOT_STYLE = "/static/complaint_app_shell.css"
MISSING_ASSET = "/static/cimp-gui-53-mark-missing.png"

_LABEL_PROBE = """
() => {
  const controls = Array.from(document.querySelectorAll('input, textarea, select'))
    .filter((node) => (node.getAttribute('type') || '').toLowerCase() !== 'hidden');
  const unlabeled = [];
  for (const node of controls) {
    const explicit = node.id ? document.querySelector(`label[for="${CSS.escape(node.id)}"]`) : null;
    const wrapped = node.closest('label');
    const label = explicit || wrapped;
    const text = label ? label.textContent.replace(/\\s+/g, ' ').trim() : '';
    if (!text) {
      unlabeled.push(node.id || node.name || node.outerHTML.slice(0, 80));
      continue;
    }
    const visible = node.checkVisibility ? node.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) : true;
    const labelVisible = label.checkVisibility ? label.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) : true;
    if (visible && !labelVisible) unlabeled.push(node.id || 'visible-unlabeled');
  }
  return unlabeled;
}
"""

_CONTRAST = """
(selector) => {
  function channel(value) {
    const parsed = value.trim().match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
    if (!parsed) return null;
    return [parsed[1], parsed[2], parsed[3]].map(Number);
  }
  function linear(part) {
    const value = part / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  }
  function luminance(rgb) {
    return 0.2126 * linear(rgb[0]) + 0.7152 * linear(rgb[1]) + 0.0722 * linear(rgb[2]);
  }
  function ratio(foreground, background) {
    const left = luminance(foreground);
    const right = luminance(background);
    const lighter = Math.max(left, right);
    const darker = Math.min(left, right);
    return (lighter + 0.05) / (darker + 0.05);
  }
  const node = document.querySelector(selector);
  const style = getComputedStyle(node);
  const foreground = channel(style.color);
  const background = channel(style.backgroundColor);
  return {
    color: style.color,
    background: style.backgroundColor,
    ratio: foreground && background ? ratio(foreground, background) : 0,
    formulaRejectsPaleGray: ratio([203, 213, 225], [255, 255, 255]) < 4.5,
  };
}
"""


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {OWNER_CREDENTIAL: owner.principal_id}),
        signing_key=os.urandom(32),
        ttl_seconds=120,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    app = FastAPI()
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(app=app, owner=owner)


@contextmanager
def _page(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix_only"], "the trusted executor must fence this child"
    world = _world(tmp_path)
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "a11y-profile"
    profile.mkdir(mode=0o700)
    playwright = None
    context = None
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        browser._assert_process_custody(node, chromium, profile)
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        page.set_viewport_size({"width": 390, "height": 640})
        yield SimpleNamespace(page=page, world=world, bridge=bridge)
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"


def _sign_in(page, credential):
    page.fill("#case-credential", credential)
    page.locator("#case-credential").press("Enter")


def test_cases_keyboard_error_summary_and_narrow_case_context(tmp_path, monkeypatch):
    with _page(tmp_path, monkeypatch) as opened:
        page = opened.page
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        page.wait_for_function("document.body.dataset.missingAsset === 'reported'")
        assert page.locator("#case-list-empty").text_content() == "No cases are loaded yet."
        assert page.locator("#case-list").get_attribute("data-state") == "empty"
        assert page.evaluate(_LABEL_PROBE) == []
        assert page.locator("img[src^='data:']").count() == 0
        assert page.locator("style").count() == 1
        assert "No replacement image was inserted." in page.locator("#case-asset-status").text_content()
        missing = page.evaluate(
            """async (path) => {
                const response = await fetch(path, {credentials: 'same-origin'});
                return {status: response.status, type: response.headers.get('content-type') || ''};
            }""",
            MISSING_ASSET,
        )
        assert missing["status"] == 404
        assert "text/html" not in missing["type"].lower() or "mocked" not in page.content()
        sheet = page.evaluate(
            """async (path) => {
                const response = await fetch(path, {credentials: 'same-origin'});
                const text = await response.text();
                return {status: response.status, hasContext: text.includes('.cg-case-context')};
            }""",
            ROOT_STYLE,
        )
        assert sheet == {"status": 200, "hasContext": True}

        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.className") == "cg-skip-link"
        page.keyboard.press("Enter")
        assert page.evaluate("document.activeElement.id") == "case-context"

        page.evaluate("window.__cimpGui53HoldLogin = true")
        _sign_in(page, WRONG_CREDENTIAL)
        page.wait_for_function("document.querySelector('#case-list').dataset.state === 'loading'")
        assert page.locator("#case-list-status").text_content() == "Loading your cases."
        loading = page.evaluate(_CONTRAST, "#case-list-status")
        assert loading["ratio"] >= 4.5
        assert loading["formulaRejectsPaleGray"] is True
        page.evaluate("window.__cimpGui53HoldLogin = false")
        page.wait_for_function("document.querySelector('#case-error-summary').hidden === false")
        assert page.evaluate("document.activeElement.id") == "case-error-summary"
        assert page.locator("#case-error-summary a").text_content() == "authentication_failed"
        assert page.locator("#case-auth-status").text_content() == "Sign in required"
        assert page.locator("#case-list").get_attribute("data-state") == "error"
        summary = page.evaluate(_CONTRAST, "#case-error-summary")
        assert summary["ratio"] >= 4.5
        page.keyboard.press("Tab")
        page.keyboard.press("Enter")
        assert page.evaluate("document.activeElement.id") == "case-credential"
        focused = page.evaluate("() => getComputedStyle(document.activeElement).outlineStyle")
        assert focused != "none"

        _sign_in(page, OWNER_CREDENTIAL)
        page.wait_for_function("document.querySelector('#case-auth-status').textContent === 'Signed in'")
        assert page.locator("#case-error-summary").is_hidden()
        assert page.locator("#case-list-empty").text_content() == "No cases yet."
        page.fill("#case-label", "narrow-case")
        page.locator("#case-label").press("Enter")
        page.wait_for_function("document.querySelector('#case-list').dataset.state === 'ready'")
        page.get_by_role("button", name="narrow-case", exact=True).click()
        page.wait_for_function("document.querySelector('#case-context-value').textContent === 'narrow-case'")
        context = page.evaluate(_CONTRAST, "#case-context")
        assert context["ratio"] >= 4.5
        assert page.evaluate("() => getComputedStyle(document.querySelector('#case-context')).position") == "sticky"
        placed = page.evaluate(
            """() => {
                const selected = document.querySelector('#selected-case').getBoundingClientRect().top;
                window.scrollTo(0, document.body.scrollHeight);
                return {
                    scroll: window.scrollY,
                    context: document.querySelector('#case-context').getBoundingClientRect().top,
                    selected: document.querySelector('#selected-case').getBoundingClientRect().top,
                    before: selected,
                };
            }"""
        )
        assert placed["scroll"] > 0
        assert placed["context"] <= 1
        assert placed["selected"] < placed["before"]
        assert page.locator("#case-context-value").text_content() == "narrow-case"
        assert page.locator("#selected-case-label").text_content() == "narrow-case"
        assert page.evaluate(_LABEL_PROBE) == []


def test_workspace_dom_reports_real_error_without_replacing_assets(tmp_path, monkeypatch):
    with _page(tmp_path, monkeypatch) as opened:
        page = opened.page
        # Hold delivery of the real bootstrap HTTP response. DOMContentLoaded
        # alone does not promise that fast ASGI failure has not already painted
        # the final error state. No API body, status or server is replaced.
        page.add_init_script("""(() => {
            const actualFetch = window.fetch.bind(window);
            let release;
            const gate = new Promise(resolve => { release = resolve; });
            window.__task53ReleaseBootstrap = release;
            window.__task53BootstrapHeld = false;
            window.fetch = async (...args) => {
                const response = await actualFetch(...args);
                const input = args[0] && args[0].url ? args[0].url : args[0];
                const target = new URL(input, window.location.href);
                if (!window.__task53BootstrapHeld && target.origin === window.location.origin
                        && target.pathname.startsWith('/api/complaint-workspace/')) {
                    window.__task53BootstrapHeld = true;
                    window.__task53BootstrapStatus = response.status;
                    await gate;
                }
                return response;
            };
        })();""")
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        page.wait_for_function("window.__task53BootstrapHeld === true")
        assert page.evaluate("window.__task53BootstrapStatus") >= 400
        assert page.locator("#workspace-case-context-value").text_content() == "No case selected"
        assert page.locator("#workspace-case-context").get_attribute("data-state") == "empty"
        assert "Workspace booting" in page.locator("#workspace-status").text_content()
        page.evaluate("window.__task53ReleaseBootstrap()")
        page.wait_for_function("['error', 'denied', 'ready', 'partial'].includes(document.body.dataset.workspaceHydrated)")
        state = page.locator("body").get_attribute("data-workspace-hydrated")
        assert state in {"error", "denied"}
        assert page.locator("#workspace-error-summary").is_visible()
        assert page.locator("#workspace-error-summary a").get_attribute("href") == "#workspace-status"
        assert page.locator("#workspace-case-context").get_attribute("data-state") == "error"
        assert page.evaluate(_LABEL_PROBE) == []
        assert page.locator("img[src^='data:']").count() == 0
        linked = page.evaluate(
            """async () => {
                const link = document.querySelector('#workspace-shell-style');
                const response = await fetch(link.href, {credentials: 'same-origin'});
                return response.status;
            }"""
        )
        assert linked == 200
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.getAttribute('href')") == "#workspace-main"
        page.keyboard.press("Enter")
        assert page.evaluate("document.activeElement.id") == "workspace-main"
        assert page.evaluate("() => getComputedStyle(document.querySelector('#workspace-case-context')).position") == "sticky"
        placed = page.evaluate(
            """() => {
                const main = document.querySelector('#workspace-main').getBoundingClientRect().top;
                window.scrollTo(0, 2400);
                return {
                    scroll: window.scrollY,
                    context: document.querySelector('#workspace-case-context').getBoundingClientRect().top,
                    main: document.querySelector('#workspace-main').getBoundingClientRect().top,
                    before: main,
                };
            }"""
        )
        assert placed["scroll"] > 0
        assert placed["context"] <= 1
        assert placed["main"] < placed["before"]
        assert page.locator("#workspace-case-context-value").text_content() == "No case selected"
        probe = page.evaluate(
            """() => {
                const input = document.createElement('input');
                input.id = 'unlabeled-probe';
                document.body.appendChild(input);
                const controls = Array.from(document.querySelectorAll('#unlabeled-probe'));
                const unlabeled = controls.filter((node) => !document.querySelector(`label[for="${node.id}"]`) && !node.closest('label'));
                input.remove();
                return unlabeled.length;
            }"""
        )
        assert probe == 1
