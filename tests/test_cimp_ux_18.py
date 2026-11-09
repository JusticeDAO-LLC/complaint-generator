"""Desktop and mobile label, annotation, and reminder editors.

The editors save through the case evidence annotation API. A date the user
marks is an attributed reminder. It is not a filing deadline or a legal
requirement unless the user supplies admitted source, jurisdiction, date,
version, and review. A status line does not stand in for that save.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from integrations.evidence_workspace import MemoryByteBackend
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

LABEL = "housing-denial"
NOTE = "margin note on the denial sentence"
REMINDER = "check the response packet"


def _ready(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    backend = MemoryByteBackend()
    from integrations.evidence_workspace import EvidenceWorkspace
    workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend,
        tmp_path / "evidence-root",
    )
    world.app.state.evidence_workspace = workspace
    world.backend = backend
    return world


def _receive(client, case, csrf):
    response = client.post(
        "/api/cases/evidence",
        headers=_composed_headers(case, csrf),
        json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "source_filename": "denial-letter.txt",
            "original_filename": "denial-letter.txt",
            "media_type": "text/plain",
            "content_base64": base64.b64encode(b"Line alpha\nLine beta span target\n").decode("ascii"),
            "idempotency_key": "ux18-evidence",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _browser(world, tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    world.browser_bridge = bridge
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux18-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
    page.set_viewport_size({"width": 1440, "height": 1000})
    return world, page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _open(page, world):
    opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
    assert opened.status == 200
    assert page.evaluate("() => typeof window.mockApi") == "undefined"
    issued = page.evaluate(
        """async () => {
            const response = await fetch('/api/complaint-workspace/auth/login', {
                method: 'POST', credentials: 'same-origin',
                headers: {'content-type': 'application/json'},
                body: JSON.stringify({credential: 'synthetic-owner-credential'}),
            });
            const body = await response.json();
            window.workspaceClient.setBrowserSession(body);
            return body;
        }"""
    )
    assert issued["authenticated"] is True
    page.evaluate(
        """context => window.workspaceClient.setCaseContext(context)""",
        {
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "revision": world.case.revision,
            "expected_revision": world.case.revision,
        },
    )
    page.click("[data-tab-target='evidence']")
    page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'ready'")
    page.click("[data-tab-target='docket']")
    page.wait_for_selector("#docket-add-label-button")


def _wait_editor(page, state):
    page.wait_for_function(
        """expected => document.getElementById('evidence-annotation-editor').dataset.saveState === expected""",
        arg=state,
    )


def _listed(client, case, evidence_id):
    listed = client.get(
        "/api/cases/evidence/annotations",
        headers=_composed_headers(case),
        params={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "evidence_id": evidence_id,
            "artifact_version": "1",
            "expected_case_revision": str(case.revision),
        },
    )
    assert listed.status_code == 200, listed.text
    return listed.json()


def test_editors_persist_label_annotation_and_reminder(tmp_path, monkeypatch):
    world = _ready(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        evidence = _receive(client, world.case, csrf)
    evidence_id = evidence["evidence_id"]
    world, page, playwright, context, node, profile, observed = _browser(world, tmp_path, monkeypatch)
    try:
        _open(page, world)
        assert "next implementation slice" not in page.content().lower()
        page.click("#docket-add-label-button")
        _wait_editor(page, "idle")
        assert page.evaluate("() => document.activeElement.id") == "evidence-annotation-label"
        page.fill("#evidence-annotation-label", "   ")
        page.click("#evidence-annotation-save")
        _wait_editor(page, "error")
        assert page.evaluate("() => document.activeElement.id") == "evidence-annotation-label"
        assert page.locator("#evidence-annotation-saved").inner_text().strip() in {
            "",
            "No annotations saved on this artifact version yet.",
        }

        page.fill("#evidence-annotation-label", LABEL)
        page.click("#evidence-annotation-save")
        _wait_editor(page, "saved")
        saved = page.locator("#evidence-annotation-saved")
        assert LABEL in saved.inner_text()
        assert world.owner.principal_id in saved.inner_text()
        assert "Artifact version: 1" in saved.inner_text()
        assert "Record time: not provided by the annotation API." in saved.inner_text()
        assert page.evaluate("() => document.activeElement.dataset.annotationId || ''") != ""

        page.evaluate("() => { document.getElementById('evidence-annotation-form').dataset.expectedRevision = 'stale-head'; }")
        page.fill("#evidence-annotation-label", "replacement-label")
        page.click("#evidence-annotation-save")
        _wait_editor(page, "conflict")
        assert page.evaluate("() => document.activeElement.id") == "evidence-annotation-editor-state"
        assert "replacement-label" not in page.locator("#evidence-annotation-saved").inner_text()
        page.click("#evidence-annotation-save")
        _wait_editor(page, "saved")
        assert "replacement-label" in page.locator("#evidence-annotation-saved").inner_text()

        page.click("#evidence-annotation-close")
        assert page.evaluate("() => document.activeElement.id") == "docket-add-label-button"
        page.click("#docket-add-annotation-button")
        _wait_editor(page, "idle")
        assert page.evaluate("() => document.activeElement.id") == "evidence-annotation-note"
        page.fill("#evidence-annotation-note", NOTE)
        page.fill("#evidence-annotation-page", "1")
        page.fill("#evidence-annotation-span-start", "0")
        page.fill("#evidence-annotation-span-end", "4")
        page.click("#evidence-annotation-save")
        _wait_editor(page, "saved")
        assert "page-1-span-0-4" in page.locator("#evidence-annotation-saved").inner_text()
        page.click("#evidence-annotation-close")

        page.set_viewport_size({"width": 390, "height": 800})
        page.locator("#docket-mobile-step-deadline summary").click()
        page.click("#docket-mobile-deadline-button")
        _wait_editor(page, "idle")
        assert page.evaluate("() => document.activeElement.id") == "evidence-annotation-reminder-date"
        page.fill("#evidence-annotation-reminder-date", "2026-11-15")
        page.fill("#evidence-annotation-reminder-note", REMINDER)
        page.check("#evidence-annotation-claim-filing-deadline")
        page.click("#evidence-annotation-save")
        _wait_editor(page, "error")
        assert "Nothing was saved." in page.locator("#evidence-annotation-editor-state").inner_text()
        assert page.evaluate("() => document.activeElement.id") == "evidence-annotation-lineage-source"
        assert "record_class: reviewed_lineage_claim" not in page.locator("#evidence-annotation-saved").inner_text()
        page.uncheck("#evidence-annotation-claim-filing-deadline")
        page.click("#evidence-annotation-save")
        _wait_editor(page, "saved")
        reminder = page.locator("#evidence-annotation-saved").inner_text()
        assert "Attributed reminder" in reminder
        assert REMINDER in reminder
        assert "not a filing deadline" in reminder
        assert "Filing deadline:" not in reminder
        page.click("#evidence-annotation-close")
        assert "next implementation slice" not in page.locator("#workspace-status").inner_text().lower()
    finally:
        _close(playwright, context, node, profile, observed)

    with TestClient(world.app, base_url="https://testserver") as client:
        _composed_login(client)
        body = _listed(client, world.case, evidence_id)
    by_kind = {}
    for item in body["items"]:
        by_kind.setdefault(item["kind"], []).append(item)
    assert set(by_kind) == {"label", "page_span", "comment"}
    labels = [item["label"] for item in by_kind["label"]]
    assert labels == ["housing-denial", "replacement-label"] or set(labels) == {"housing-denial", "replacement-label"}
    assert all(item["actor_principal_id"] == world.owner.principal_id and item["adopted"] is False for item in by_kind["label"])
    assert by_kind["page_span"][0]["anchor"] == "page-1-span-0-4"
    assert by_kind["page_span"][0]["note"] == NOTE
    kinds = {item["kind"]: item for item in body["items"] if item["kind"] != "label"}
    assert kinds["comment"]["note"].startswith("record_class: attributed_reminder")
    assert "filing_deadline: false" in kinds["comment"]["note"]
    assert "system_derived_filing_deadline: false" in kinds["comment"]["note"]
    assert kinds["comment"]["claim_element"] == ""
    assert all(item["adopted"] is False and item["synthesized_evidence"] is False for item in body["items"])
    assert world.backend.contains(LABEL.encode()) is False
    assert world.backend.contains(REMINDER.encode()) is False
    for path in (tmp_path / "evidence-root").rglob("*"):
        if path.is_file():
            blob = path.read_bytes()
            assert LABEL.encode() not in blob
            assert REMINDER.encode() not in blob
            assert NOTE.encode() not in blob
