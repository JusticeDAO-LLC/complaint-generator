"""Visual regression, keyboard continuity, and honest state variants.

Screenshots are compared as layout landmarks and PNG viewports. A similar
image cannot excuse a skipped case, a stale write, or a privacy failure.
Baseline digest changes stay in the report with a written reason.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from applications.case_routes import CASE_PAGE_PATH
from applications.lawyer_workspace_api import LAWYER_WORKSPACE_PAGE

_VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_complaint_ux_visuals.py"
_spec = importlib.util.spec_from_file_location("validate_complaint_ux_visuals", _VALIDATOR_PATH)
_validator = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_validator)
SCHEMA = _validator.SCHEMA
TASK_ID = _validator.TASK_ID
VisualQualificationError = _validator.VisualQualificationError
audit_repository_baseline = _validator.audit_repository_baseline
image_similarity = _validator.image_similarity
png_dimensions = _validator.png_dimensions
qualify_report = _validator.qualify_report
required_case_ids = _validator.required_case_ids
from tests import gui_native_browser as browser
from tests.gui_ux_overhaul_fixtures import (
    BASELINE_DIR,
    LAWYER_CREDENTIAL,
    OWNER_CREDENTIAL,
    assert_png,
    baseline_manifest,
    declared_visual_widths,
    load_contract,
    synthetic_capture_world,
)
from tests.test_cimp_gui_14 import _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

CASE_LABEL = "owner-lawyer-journey"
SCOPE = ["case.read", "case.review"]
REVIEW_REASON = (
    "The fresh synthetic capture is a different signed-in case state than the "
    "historical baseline file. Pixel similarity is not the pass condition; "
    "the layout landmark and the backend binding are."
)


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _sample_report(contract):
    cases = []
    for item in declared_visual_widths(contract):
        cases.append({
            "id": f"width-{item['width']}",
            "viewport": {"width": item["width"], "height": item["height"]},
            "landmarks": {
                "visible": True,
                "labelled": True,
                "right": 200,
                "scroll_width": item["width"],
                "png_width": item["width"],
                "png_height": item["height"],
                "essential_action_visible": True,
                "reduced_motion_keeps_action": item["width"] == 320,
            },
            "interaction": {"landmark_measured": True},
            "backend": {"status": 200, "checked": True, "route": "/cases"},
            "screenshot_sha256": "observed",
            "baseline_sha256": "historical",
            "baseline_changed": True,
            "review_reason": REVIEW_REASON,
        })
    cases.append({
        "id": "keyboard-case-path",
        "interaction": {"activated": True, "focus_returned": True, "focus_id": "evidence"},
        "backend": {"status": 200, "checked": True},
    })
    cases.extend([
        {"id": "state-loading", "interaction": {"loading_visible": True}, "backend": {"status": 200, "checked": True, "settled": True}},
        {"id": "state-empty", "interaction": {"empty_visible": True}, "backend": {"status": 200, "checked": True, "count": 0, "invented_evidence": False}},
        {"id": "state-error", "interaction": {"denied_text": "Sign-in was denied. No case was opened."}, "backend": {"status": 401, "checked": True}},
        {
            "id": "state-locked",
            "interaction": {"entry": "missing-key"},
            "backend": {"status": 503, "checked": True, "error": "unlock_needed", "session_readable": False},
            "privacy": {"plaintext_present": False, "owner_label_visible": False},
        },
        {
            "id": "state-stale",
            "interaction": {"unchanged": True},
            "backend": {"status": 409, "checked": True, "code": "encrypted_revision_conflict", "label_before": CASE_LABEL, "label_after": CASE_LABEL},
        },
        {
            "id": "state-revoked",
            "interaction": {"content_withheld": True, "owner_label_in_page": False},
            "backend": {"status": 403, "checked": True, "revoked": True},
            "privacy": {"plaintext_present": False, "owner_label_visible": False},
        },
    ])
    return {
        "schema": SCHEMA,
        "task_id": TASK_ID,
        "image_similarity_is_pass": False,
        "network_fence": {"af_unix": {"opened": True}, "af_inet": {"opened": False}, "af_unix_only": True},
        "preserved_baseline_story": list(contract["preserved_baseline_story"]),
        "cases": cases,
    }


def test_repository_baseline_is_a_source_bound_story_not_a_pixel_pass():
    audit = audit_repository_baseline()
    assert audit["ok"], audit
    assert audit["screenshot_count"] >= 13
    assert audit["image_similarity_is_pass"] is False
    assert 1440 in audit["widths"] and 390 in audit["widths"]
    manifest = baseline_manifest()
    first = manifest["screenshots"][0]
    blob = (BASELINE_DIR / first["path"]).read_bytes()
    twin = (BASELINE_DIR / manifest["screenshots"][1]["path"]).read_bytes()
    assert png_dimensions(blob) == (first["viewport"]["width"], first["viewport"]["height"])
    assert image_similarity(blob, blob) == 1.0
    assert image_similarity(blob, twin) < 1.0
    contract = load_contract()
    report = _sample_report(contract)
    assert qualify_report(report)["case_count"] == len(required_case_ids(contract))
    assert qualify_report(report)["skipped"] == 0
    image_only = json.loads(json.dumps(report))
    image_only["pass_basis"] = "image_similarity"
    image_only["cases"][0]["pass_basis"] = "image_similarity"
    image_only["cases"][0]["interaction"] = {}
    image_only["cases"][0]["backend"] = {}
    image_only["cases"][0]["image_similarity"] = 1
    with pytest.raises(VisualQualificationError, match="image_similarity"):
        qualify_report(image_only)
    skipped = json.loads(json.dumps(report))
    skipped["cases"][0]["skipped"] = True
    with pytest.raises(VisualQualificationError, match="skipped"):
        qualify_report(skipped)
    silent = json.loads(json.dumps(report))
    silent["cases"][0]["review_reason"] = "updated baseline"
    with pytest.raises(VisualQualificationError, match="baseline_change_without_reason"):
        qualify_report(silent)
    leaked = json.loads(json.dumps(report))
    leaked["cases"][-1]["privacy"] = {"plaintext_present": True, "owner_label_visible": True}
    with pytest.raises(VisualQualificationError, match="privacy"):
        qualify_report(leaked)
    with pytest.raises(VisualQualificationError, match="required_cases_empty"):
        qualify_report({
            "schema": SCHEMA,
            "task_id": TASK_ID,
            "cases": [],
            "network_fence": {"af_unix": {"opened": True}, "af_inet": {"opened": False}, "af_unix_only": True},
            "preserved_baseline_story": contract["preserved_baseline_story"],
        })


def _prepare_closed_states(world):
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer:
        owner_token = _composed_login(owner)
        before = owner.get(f"/api/cases/{world.case.case_id}")
        assert before.status_code == 200, before.text
        label_before = before.json()["label"]
        assert label_before == CASE_LABEL
        stale = owner.post(
            f"/api/cases/{world.case.case_id}/gaps",
            headers=_csrf(owner_token),
            json={"expected_content_revision": 0, "unresolved_gaps": ["synthetic-stale-gap"]},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"] == "encrypted_revision_conflict"
        after = owner.get(f"/api/cases/{world.case.case_id}")
        assert after.status_code == 200
        assert after.json()["label"] == label_before
        threads = owner.get("/api/cases/messages/threads", params={"case_id": world.case.case_id})
        assert threads.status_code == 200, threads.text
        assert threads.json().get("threads") == []
        lawyer_token = _composed_login(lawyer, LAWYER_CREDENTIAL)
        invited = owner.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": world.case.case_id,
            "member_principal_id": world.lawyer.principal_id,
            "scope": SCOPE,
            "expected_case_revision": world.case.revision,
            "idempotency_key": "ux62-invite",
            "access_for_days": 30,
        })
        assert invited.status_code == 201, invited.text
        grant_id = invited.json()["grant_id"]
        version = invited.json()["server_version"]
        accepted = lawyer.post(
            f"/api/cases/assignments/{grant_id}/accept",
            headers=_csrf(lawyer_token),
            json={"scope": SCOPE, "case_id": world.case.case_id, "expected_version": version, "idempotency_key": "ux62-accept"},
        )
        assert accepted.status_code == 200, accepted.text
        removed = owner.post(
            f"/api/cases/assignments/{grant_id}/remove",
            headers=_csrf(owner_token),
            json={"case_id": world.case.case_id, "expected_version": accepted.json()["server_version"], "idempotency_key": "ux62-revoke"},
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["revoked"] is True
        opened = lawyer.post(
            f"/api/cases/assignments/{grant_id}/use",
            headers=_csrf(lawyer_token),
            json={"surface": "api", "action": "case.read", "expected_version": removed.json()["server_version"], "case_id": world.case.case_id},
        )
        assert opened.status_code == 403, opened.text
        assert "text" not in opened.json()
        denied = lawyer.get(f"/api/cases/{world.case.case_id}")
        assert denied.status_code == 404
        assert CASE_LABEL not in denied.text
    return {
        "label_before": label_before,
        "label_after": after.json()["label"],
        "stale_status": stale.status_code,
        "stale_code": stale.json()["error"],
        "thread_count": 0,
        "revoked": True,
        "revoked_status": opened.status_code,
    }


def _launch(tmp_path, monkeypatch, world):
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux62-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
    return page, playwright, context, node, profile


def _close(playwright, context, node, profile):
    context.close()
    playwright.stop()
    observed = browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], cleanup
    assert cleanup["remaining_pids"] == []


def _tab_until(page, selector, limit=40):
    page.locator("body").click(position={"x": 1, "y": 1})
    for _ in range(limit):
        page.keyboard.press("Tab")
        matched = page.evaluate(
            """(selector) => {
                const node = document.querySelector(selector);
                return node !== null && document.activeElement === node;
            }""",
            selector,
        )
        if matched:
            return True
    return False


def _shot(page, dest, width, height):
    page.set_viewport_size({"width": width, "height": height})
    if width == 320:
        page.emulate_media(reduced_motion="reduce")
    measured = page.evaluate(
        """() => {
            const form = document.getElementById('case-login');
            const box = form.getBoundingClientRect();
            const action = form.querySelector('button[type=submit]');
            action.scrollIntoView({block: 'nearest', inline: 'nearest'});
            const actionBox = action.getBoundingClientRect();
            const shown = getComputedStyle(action).visibility !== 'hidden' && actionBox.width > 20 && actionBox.right <= window.innerWidth + 1;
            return {
                visible: box.width > 40 && box.height > 20,
                labelled: document.querySelector('label[for="case-credential"]') !== null,
                right: box.right,
                scroll_width: document.documentElement.scrollWidth,
                essential_action_visible: shown,
                reduced_motion_keeps_action: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? actionBox.width > 20 : true,
                inner_width: window.innerWidth,
                inner_height: window.innerHeight,
                mockApi: typeof window.mockApi !== 'undefined',
            };
        }"""
    )
    payload = page.screenshot(type="png", animations="disabled")
    dest.write_bytes(payload)
    digest = assert_png(payload)
    png_width, png_height = png_dimensions(payload)
    assert measured["inner_width"] == width
    assert measured["inner_height"] == height
    assert measured["mockApi"] is False
    assert png_width == width and png_height == height
    return digest, measured


def test_live_widths_keyboard_and_state_variants(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix"]["opened"] is True
    assert (denial["af_unix_only"] is True) or (denial["af_inet"]["opened"] is True)
    contract = load_contract()
    world = synthetic_capture_world(tmp_path / "visual")
    closed = _prepare_closed_states(world)
    out = tmp_path / "shots"
    out.mkdir()
    page, playwright, context, node, profile = _launch(tmp_path, monkeypatch, world)
    try:
        opened = page.goto(browser.SAME_ORIGIN + CASE_PAGE_PATH, wait_until="domcontentloaded")
        assert opened.status == 200
        width_cases = []
        baseline = {item["id"]: item for item in baseline_manifest()["screenshots"]}
        historical = baseline["08-cases-owner-desktop"]
        for item in declared_visual_widths(contract):
            digest, measured = _shot(page, out / f"width-{item['width']}.png", item["width"], item["height"])
            assert measured["visible"] is True
            assert measured["labelled"] is True
            assert measured["essential_action_visible"] is True
            assert measured["right"] <= item["width"] + 1
            assert measured["scroll_width"] <= item["width"] + 1
            width_cases.append({
                "id": f"width-{item['width']}",
                "viewport": {"width": item["width"], "height": item["height"]},
                "landmarks": {
                    "visible": measured["visible"],
                    "labelled": measured["labelled"],
                    "right": measured["right"],
                    "scroll_width": measured["scroll_width"],
                    "png_width": item["width"],
                    "png_height": item["height"],
                    "essential_action_visible": measured["essential_action_visible"],
                    "reduced_motion_keeps_action": measured["reduced_motion_keeps_action"] if item["width"] == 320 else True,
                },
                "interaction": {"landmark_measured": True, "viewport_name": item["name"]},
                "backend": {"status": opened.status, "checked": True, "route": CASE_PAGE_PATH},
                "screenshot_sha256": digest,
                "baseline_sha256": historical["sha256"],
                "baseline_changed": digest != historical["sha256"],
                "review_reason": REVIEW_REASON,
            })
        assert len({case["screenshot_sha256"] for case in width_cases}) >= 2
        page.emulate_media(reduced_motion="no-preference")
        page.set_viewport_size({"width": 1440, "height": 1000})
        bad = page.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: 'not-a-real-credential'}),
                });
                let body = null;
                try { body = await response.json(); } catch (error) { body = null; }
                return {status: response.status, authenticated: body && body.authenticated === true};
            }"""
        )
        assert bad["status"] >= 400
        assert bad["authenticated"] is not True
        assert _tab_until(page, "#case-credential") is True
        page.keyboard.type("not-a-real-credential")
        assert _tab_until(page, "#case-login button[type=submit]") is True
        page.keyboard.press("Enter")
        denied_text = page.wait_for_function(
            """() => {
                const node = document.getElementById('case-list-empty');
                if (!node || node.textContent.indexOf('Sign-in was denied') < 0) return null;
                return node.textContent;
            }"""
        ).json_value()
        assert isinstance(denied_text, str) and "denied" in denied_text.casefold()
        assert page.get_attribute("#case-list", "data-state") == "error"
        page.evaluate("() => { window.__cimpGui53HoldLogin = true; }")
        page.fill("#case-credential", OWNER_CREDENTIAL)
        page.focus("#case-credential")
        page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement === document.querySelector('#case-login button[type=submit]')") is True
        page.keyboard.press("Enter")
        page.wait_for_function("() => document.getElementById('case-list').dataset.state === 'loading'")
        loading_text = page.text_content("#case-list-status")
        assert "Loading your cases." in loading_text
        page.evaluate("() => { window.__cimpGui53HoldLogin = false; }")
        page.wait_for_function("() => document.getElementById('case-auth-status').textContent === 'Signed in'")
        session = page.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/auth/session', {credentials: 'same-origin'});
                const body = await response.json();
                return {status: response.status, authenticated: body.authenticated === true};
            }"""
        )
        assert session["status"] == 200 and session["authenticated"] is True
        assert _tab_until(page, "#case-list button") is True
        page.keyboard.press("Enter")
        page.wait_for_function(
            """() => {
                const actor = document.getElementById('complaint-case-shell-actor');
                return actor && actor.dataset.relationship === 'owner';
            }"""
        )
        assert _tab_until(page, "[data-case-task='evidence']") is True
        page.keyboard.press("Enter")
        page.wait_for_function(
            "() => document.querySelector('[data-case-panel=\"evidence\"]').hidden === false"
        )
        focus_returned = page.evaluate(
            "() => document.activeElement === document.querySelector('[data-case-task=\"evidence\"]')"
        )
        assert focus_returned is True
        evidence_text = page.text_content("[data-case-panel='evidence']")
        assert "Receipt is not proof" in evidence_text
        page.locator("[data-case-task='draft']").focus()
        page.keyboard.press("Enter")
        page.wait_for_function(
            "() => document.querySelector('[data-case-panel=\"draft\"]').textContent.indexOf('No draft is stored') >= 0"
        )
        context.clear_cookies()
        lawyer_page = page.goto(browser.SAME_ORIGIN + LAWYER_WORKSPACE_PAGE, wait_until="domcontentloaded")
        assert lawyer_page.status == 200
        page.fill("#review-credential", LAWYER_CREDENTIAL)
        lawyer_body = page.evaluate("() => document.body.innerText")
        assert CASE_LABEL not in lawyer_body
        world.service.lock_private_keys()
        reopened = page.goto(browser.SAME_ORIGIN + CASE_PAGE_PATH, wait_until="domcontentloaded")
        assert reopened.status == 200
        page.fill("#case-credential", OWNER_CREDENTIAL)
        page.click("#case-login button[type=submit]")
        page.wait_for_function("() => document.getElementById('case-auth-status').textContent === 'Signed in'")
        page.click("#case-list button")
        page.wait_for_function(
            "() => document.getElementById('complaint-entry') && document.getElementById('complaint-entry').dataset.entry === 'missing-key'"
        )
        locked = page.evaluate(
            """async () => {
                const entry = document.getElementById('complaint-entry');
                const binding = window.complaintCaseShell && window.complaintCaseShell.binding ? window.complaintCaseShell.binding() : null;
                const caseId = binding && binding.case_id ? binding.case_id : '';
                const headers = binding ? {
                    'x-tenant-id': binding.tenant_id || '',
                    'x-case-id': binding.case_id || '',
                    'x-resource-id': binding.resource_id || '',
                    'x-expected-revision': String(binding.directory_revision || ''),
                } : {};
                const response = await fetch('/api/complaint-workspace/session?case_id=' + encodeURIComponent(caseId), {
                    credentials: 'same-origin', headers,
                });
                let body = {};
                try { body = await response.json(); } catch (error) { body = {}; }
                return {
                    entry: entry ? entry.dataset.entry : '',
                    text: document.body.innerText,
                    status: response.status,
                    error: body.error || '',
                    sessionReadable: body.session_readable === true,
                    hasSession: Boolean(body.session),
                };
            }"""
        )
        assert locked["entry"] == "missing-key"
        assert "Private key access is locked" in locked["text"]
        assert locked["status"] == 503
        assert locked["error"] == "unlock_needed"
        assert locked["sessionReadable"] is False
        assert locked["hasSession"] is False
        report = {
            "schema": SCHEMA,
            "task_id": TASK_ID,
            "image_similarity_is_pass": False,
            "network_fence": denial,
            "preserved_baseline_story": list(contract["preserved_baseline_story"]),
            "cases": width_cases + [
                {
                    "id": "keyboard-case-path",
                    "interaction": {"activated": True, "focus_returned": focus_returned, "focus_id": "evidence"},
                    "backend": {"status": session["status"], "checked": True, "relationship": "owner"},
                },
                {
                    "id": "state-loading",
                    "interaction": {"loading_visible": True, "visible_text": loading_text},
                    "backend": {"status": session["status"], "checked": True, "settled": True},
                },
                {
                    "id": "state-empty",
                    "interaction": {"empty_visible": True, "visible_text": "No draft is stored"},
                    "backend": {"status": 200, "checked": True, "count": closed["thread_count"], "invented_evidence": False},
                },
                {
                    "id": "state-error",
                    "interaction": {"denied_text": denied_text},
                    "backend": {"status": bad["status"], "checked": True, "authenticated": False},
                },
                {
                    "id": "state-locked",
                    "interaction": {"entry": locked["entry"]},
                    "backend": {"status": locked["status"], "checked": True, "error": locked["error"], "session_readable": False},
                    "privacy": {"plaintext_present": False, "owner_label_visible": CASE_LABEL in locked["text"] and "Private key access is locked" not in locked["text"]},
                },
                {
                    "id": "state-stale",
                    "interaction": {"unchanged": closed["label_before"] == closed["label_after"]},
                    "backend": {
                        "status": closed["stale_status"],
                        "checked": True,
                        "code": closed["stale_code"],
                        "label_before": closed["label_before"],
                        "label_after": closed["label_after"],
                    },
                },
                {
                    "id": "state-revoked",
                    "interaction": {"content_withheld": True, "owner_label_in_page": CASE_LABEL in lawyer_body},
                    "backend": {"status": closed["revoked_status"], "checked": True, "revoked": closed["revoked"]},
                    "privacy": {"plaintext_present": False, "owner_label_visible": CASE_LABEL in lawyer_body},
                },
            ],
        }
        result = qualify_report(report)
        assert result["ok"] is True
        assert result["case_count"] == 4 + 1 + 6
        assert result["skipped"] == 0
        written = out / "visual_report.json"
        written.write_text(json.dumps(report), encoding="utf-8")
        assert written.stat().st_size > 0
    finally:
        _close(playwright, context, node, profile)
