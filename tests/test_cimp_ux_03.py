"""Computed experience tokens on the real workspace.

Chromium is the inherited pinned binary. HTTP is the same-origin pipe into
the composed ASGI app. The page under test is the actual workspace template,
including its intake form, consent copy, and case-authorization session.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "templates" / "workspace.html"
FINDINGS = ROOT / "docs" / "ux" / "complaint_ux_overhaul" / "screenshot_driven_findings.json"
CONTRACT = ROOT / "docs" / "ux" / "complaint_ux_overhaul" / "experience_contract.md"
DESKTOP = {"width": 1440, "height": 1000}

_METER = r"""
() => {
  const parse = (value) => {
    const parts = String(value).match(/[\d.]+/g);
    if (!parts || parts.length < 3) return null;
    return parts.slice(0, 3).map(Number);
  };
  const channel = (c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const lum = (value) => {
    const rgb = parse(value);
    if (!rgb) return null;
    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  };
  const contrast = (foreground, background) => {
    const a = lum(foreground);
    const b = lum(background);
    if (a === null || b === null) return 0;
    const hi = Math.max(a, b);
    const lo = Math.min(a, b);
    return (hi + 0.05) / (lo + 0.05);
  };
  const paint = (node) => {
    const style = getComputedStyle(node);
    let background = style.backgroundColor;
    let current = node;
    while (current && (background === 'transparent' || /rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0\s*\)/.test(background))) {
      current = current.parentElement;
      background = current ? getComputedStyle(current).backgroundColor : background;
    }
    const size = parseFloat(style.fontSize);
    const weight = parseInt(style.fontWeight, 10) || 400;
    return {
      color: style.color,
      background,
      fontSize: size,
      fontWeight: weight,
      fontFamily: style.fontFamily,
      lineHeight: style.lineHeight,
      paddingTop: style.paddingTop,
      paddingLeft: style.paddingLeft,
      outlineStyle: style.outlineStyle,
      outlineWidth: parseFloat(style.outlineWidth) || 0,
      outlineColor: style.outlineColor,
      contrast: contrast(style.color, background),
      large: size >= 24 || (weight >= 700 && size >= 18.66),
    };
  };
  return {contrast, paint};
}
"""


def _open(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux03-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    page.set_viewport_size(DESKTOP)
    return world, page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def test_workspace_uses_token_hierarchy_contrast_focus_and_states(tmp_path, monkeypatch):
    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))
    shell_finding = next(row for row in findings["findings"] if row["id"] == "UX-08")
    assert "typography/spacing/token" in shell_finding["plan_requirement"]
    assert "contrast" in CONTRACT.read_text(encoding="utf-8").lower()
    assert 'id="complaint-experience-tokens"' in WORKSPACE.read_text(encoding="utf-8")
    assert "Local private is the default" in WORKSPACE.read_text(encoding="utf-8")

    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        asset = page.goto(browser.SAME_ORIGIN + "/static/complaint_experience_tokens.css", wait_until="domcontentloaded")
        assert asset.status == 200
        assert "--cx-color-ink" in asset.text()
        opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert opened.status == 200
        page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
        assert page.evaluate("() => typeof window.mockApi") == "undefined"

        styles = page.evaluate(
            """() => {
                const root = getComputedStyle(document.documentElement);
                const body = getComputedStyle(document.body);
                const display = getComputedStyle(document.querySelector('h1.cx-display'));
                const title = getComputedStyle(document.querySelector('h2.cx-title'));
                const lede = getComputedStyle(document.querySelector('p.cx-lede'));
                const shell = getComputedStyle(document.querySelector('#workspace-main'));
                const field = document.querySelector('#adaptive-narrative');
                return {
                    space4: root.getPropertyValue('--cx-space-4').trim(),
                    displaySize: root.getPropertyValue('--cx-font-display').trim(),
                    bodyFamily: body.fontFamily,
                    bodySize: parseFloat(body.fontSize),
                    displayPx: parseFloat(display.fontSize),
                    titlePx: parseFloat(title.fontSize),
                    ledePx: parseFloat(lede.fontSize),
                    displayLeading: parseFloat(display.lineHeight) / parseFloat(display.fontSize),
                    shellPad: shell.paddingTop,
                    fieldPresent: Boolean(field),
                    consent: document.getElementById('consent-implication-notice').textContent,
                    header: document.getElementById('workspace-case-context-value').textContent.trim(),
                    evidence: Boolean(document.getElementById('evidence-title')),
                };
            }"""
        )
        assert styles["space4"] == "16px"
        assert styles["displaySize"] == "2.25rem"
        assert "Public Sans" in styles["bodyFamily"] or "Segoe UI" in styles["bodyFamily"]
        assert styles["displayPx"] > styles["titlePx"] > styles["ledePx"] >= 16
        assert styles["displayLeading"] >= 1.2
        assert styles["shellPad"] == "32px"
        assert styles["fieldPresent"] is True
        assert styles["evidence"] is True
        assert "Local private is the default" in styles["consent"]
        assert styles["header"] == "No case selected"

        measured = page.evaluate(
            """meter => {
                const api = (0, eval)('(' + meter + ')')();
                const display = api.paint(document.querySelector('h1.cx-display'));
                const lede = api.paint(document.querySelector('p.cx-lede'));
                const body = api.paint(document.body);
                const bad = document.createElement('span');
                bad.textContent = 'insufficient';
                bad.style.color = '#969696';
                bad.style.background = '#ffffff';
                document.body.appendChild(bad);
                const insufficient = api.paint(bad);
                bad.remove();
                return {display, lede, body, insufficient, badPair: api.contrast('rgb(150, 150, 150)', 'rgb(255, 255, 255)')};
            }""",
            _METER,
        )
        assert measured["display"]["large"] is True
        assert measured["display"]["contrast"] >= 3
        assert measured["lede"]["large"] is False
        assert measured["lede"]["contrast"] >= 4.5
        assert measured["body"]["contrast"] >= 4.5
        assert measured["insufficient"]["contrast"] < 4.5
        assert measured["badPair"] < 4.5

        page.focus("#adaptive-narrative")
        focus = page.evaluate(
            """meter => {
                const api = (0, eval)('(' + meter + ')')();
                const field = document.querySelector('#adaptive-narrative');
                const style = getComputedStyle(field);
                const host = api.paint(field.parentElement);
                return {
                    outlineStyle: style.outlineStyle,
                    outlineWidth: parseFloat(style.outlineWidth) || 0,
                    outlineOffset: parseFloat(style.outlineOffset) || 0,
                    contrast: api.contrast(style.outlineColor, host.background),
                };
            }""",
            _METER,
        )
        assert focus["outlineStyle"] == "solid"
        assert focus["outlineWidth"] >= 3
        assert focus["outlineOffset"] >= 2
        assert focus["contrast"] >= 3

        page.evaluate(
            """() => {
                const status = document.getElementById('workspace-status');
                status.textContent = 'The private key remains locked. Case content was not rebuilt.';
                document.body.dataset.workspaceHydrated = 'denied';
                const summary = document.getElementById('workspace-error-summary');
                const list = document.getElementById('workspace-error-summary-list');
                list.replaceChildren();
                const item = document.createElement('li');
                const link = document.createElement('a');
                link.href = '#workspace-status';
                link.textContent = status.textContent;
                item.appendChild(link);
                list.appendChild(item);
                summary.hidden = false;
                document.getElementById('workspace-locked-state').hidden = false;
            }"""
        )
        states = page.evaluate(
            """meter => {
                const api = (0, eval)('(' + meter + ')')();
                const error = api.paint(document.getElementById('workspace-error-summary'));
                const locked = api.paint(document.getElementById('workspace-locked-state'));
                const errorText = document.getElementById('workspace-error-summary').innerText;
                const lockedText = document.getElementById('workspace-locked-state').innerText;
                return {error, locked, errorText, lockedText,
                    errorVisible: !document.getElementById('workspace-error-summary').hidden,
                    lockedVisible: !document.getElementById('workspace-locked-state').hidden};
            }""",
            _METER,
        )
        assert states["errorVisible"] is True
        assert states["lockedVisible"] is True
        assert "private key remains locked" in states["errorText"]
        assert "not replaced" in states["lockedText"] or "not rebuilt" in states["lockedText"] or "stays locked" in states["lockedText"]
        assert states["error"]["contrast"] >= 4.5
        assert states["locked"]["contrast"] >= 4.5
        assert states["error"]["background"] != states["locked"]["background"]

        page.emulate_media(reduced_motion="reduce")
        motion = page.evaluate(
            """() => getComputedStyle(document.querySelector('button, .surface-link')).transitionDuration"""
        )
        assert motion in {"0s", "0ms"}

        anonymous = page.evaluate(
            """async () => (await fetch('/api/complaint-workspace/auth/session', {credentials: 'same-origin'})).status"""
        )
        assert anonymous == 401

        stranger = page.evaluate(
            """async () => {
                const login = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: 'synthetic-stranger-credential'})});
                const issued = await login.json();
                window.workspaceClient.setBrowserSession(issued);
                const catalog = await fetch('/api/cases', {credentials: 'same-origin'});
                const body = await catalog.json();
                const serialized = JSON.stringify(body);
                return {login: login.status, authenticated: issued.authenticated, principal: issued.principal_id,
                    catalog: catalog.status, serialized};
            }"""
        )
        assert stranger["login"] == 200
        assert stranger["authenticated"] is True
        assert stranger["principal"] == world.stranger.principal_id
        assert stranger["principal"] != world.owner.principal_id
        assert stranger["catalog"] == 200
        assert world.case.case_id not in stranger["serialized"]
        assert world.case.tenant_id not in stranger["serialized"]
    finally:
        _close(playwright, context, node, profile, observed)
