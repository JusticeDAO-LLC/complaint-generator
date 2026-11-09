"""Evidence library master/detail reads the authorized catalog.

Desktop and mobile views show the same server artifact. Search and status
filters do not invent records. Empty, failed, and locked catalogs stay
actionable and do not present receipt as a complaint link or legal conclusion.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

LINKED_SOURCE = "denial-letter.txt"
LINKED_ORIGINAL = "Housing denial scan.tiff"
OTHER_SOURCE = "witness-note.txt"
OTHER_ORIGINAL = "Witness memo.docx"
LINK_ID = "paragraph-4"
EXTRACT = b"synthetic extracted denial sentence"


def _ready(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    backend = MemoryByteBackend()
    workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        backend,
        tmp_path / "evidence-root",
    )
    world.app.state.evidence_workspace = workspace
    return world


def _receive(client, case, csrf, source, original, key):
    response = client.post(
        "/api/cases/evidence",
        headers=_composed_headers(case, csrf),
        json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "source_filename": source,
            "original_filename": original,
            "media_type": "text/plain",
            "content_base64": base64.b64encode(f"synthetic {source}".encode()).decode("ascii"),
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _link(client, case, csrf, evidence_id):
    extracted = client.post(
        "/api/cases/evidence/lifecycle",
        headers=_composed_headers(case, csrf),
        json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "evidence_id": evidence_id,
            "action": "extract",
            "expected_artifact_version": 1,
            "extracted_content_base64": base64.b64encode(EXTRACT).decode("ascii"),
            "idempotency_key": "ux15-extract",
        },
    )
    assert extracted.status_code == 200, extracted.text
    linked = client.post(
        "/api/cases/evidence/lifecycle",
        headers=_composed_headers(case, csrf),
        json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "evidence_id": evidence_id,
            "action": "link",
            "complaint_link_id": LINK_ID,
            "expected_artifact_version": 2,
            "idempotency_key": "ux15-link",
        },
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["complaint_link_id"] == LINK_ID
    assert linked.json()["claim_support"] == "not_established"
    return linked.json()


def _receive_from_browser(page, case, source, original, key):
    result = page.evaluate(
        """async payload => {
            const response = await fetch('/api/cases/evidence', {
                method: 'POST', credentials: 'same-origin',
                headers: Object.assign({}, payload.headers, {
                    'content-type': 'application/json',
                    'x-csrf-token': window.workspaceClient.csrfToken,
                }),
                body: JSON.stringify(payload.body),
            });
            return {status: response.status, body: await response.json()};
        }""",
        {
            "headers": _composed_headers(case),
            "body": {
                "tenant_id": case.tenant_id,
                "case_id": case.case_id,
                "resource_id": case.resource_id,
                "source_filename": source,
                "original_filename": original,
                "media_type": "text/plain",
                "content_base64": base64.b64encode(f"synthetic {source}".encode()).decode("ascii"),
                "idempotency_key": key,
            },
        },
    )
    assert result["status"] == 201, result
    return result["body"]


def _browser(tmp_path, monkeypatch):
    world = _ready(tmp_path)
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    world.browser_bridge = bridge
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux15-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
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
        },
    )
    page.click("[data-tab-target='evidence']")
    page.wait_for_selector("#evidence-library")


def _detail(page):
    return page.evaluate(
        """() => {
            const host = document.getElementById('evidence-library');
            const text = (id) => document.getElementById(id).textContent;
            return {
                state: host.dataset.state,
                layout: host.dataset.layout,
                pane: host.dataset.pane,
                selectedId: host.dataset.selectedId,
                status: text('evidence-detail-status'),
                source: text('evidence-detail-source'),
                dates: text('evidence-detail-dates'),
                notes: text('evidence-detail-notes'),
                classification: text('evidence-detail-classification'),
                links: text('evidence-detail-links'),
                summary: text('evidence-library-summary'),
                pressed: Array.from(document.querySelectorAll('#evidence-library-list [aria-pressed="true"]')).map(node => node.getAttribute('data-evidence-id')),
            };
        }"""
    )


def test_library_filters_catalog_and_keeps_selection_on_mobile(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch)
    try:
        with TestClient(world.app, base_url="https://testserver") as client:
            csrf = _composed_login(client)
            linked = _link(client, world.case, csrf, _receive(client, world.case, csrf, LINKED_SOURCE, LINKED_ORIGINAL, "ux15-linked")["evidence_id"])
            other = _receive(client, world.case, csrf, OTHER_SOURCE, OTHER_ORIGINAL, "ux15-other")
        _open(page, world)
        page.wait_for_function(
            """() => document.getElementById('evidence-library').dataset.state === 'ready'
                && document.querySelectorAll('#evidence-library-list [data-evidence-id]').length === 2"""
        )
        page.click(f"#evidence-library-list [data-evidence-id='{other['evidence_id']}']")
        page.wait_for_function(
            """id => document.getElementById('evidence-library').dataset.state === 'ready'
                && document.getElementById('evidence-library').dataset.selectedId === id""",
            arg=other["evidence_id"],
        )
        desktop = _detail(page)
        assert desktop["layout"] == "master-detail"
        assert desktop["selectedId"] == other["evidence_id"]
        assert desktop["pressed"] == [other["evidence_id"]]
        assert "Status: received" in desktop["status"]
        assert f"Recorded by: {world.owner.principal_id}" in desktop["status"]
        assert f"Source file: {OTHER_SOURCE}" in desktop["source"]
        assert f"Original file: {OTHER_ORIGINAL}" in desktop["source"]
        assert "Source date: Not recorded" in desktop["dates"]
        assert "Version date: Not recorded" in desktop["dates"]
        assert "Catalog read: " in desktop["dates"]
        assert "No attributed note is stored for this artifact." == desktop["notes"]
        assert "authenticity: not_established" in desktop["classification"]
        assert "claim_support: not_established" in desktop["classification"]
        assert "not verified support" in desktop["classification"]
        assert desktop["links"] == "No current complaint link."
        assert EXTRACT.decode() not in desktop["source"]
        assert page.locator("#evidence-library-list").is_visible()
        assert page.locator("#evidence-library-detail").is_visible()

        page.fill("#evidence-library-search", "witness")
        page.wait_for_function(
            """() => document.querySelectorAll('#evidence-library-list [data-evidence-id]').length === 1"""
        )
        assert _detail(page)["selectedId"] == other["evidence_id"]
        page.select_option("#evidence-library-status-filter", "linked")
        page.wait_for_selector("#evidence-library-filter-empty")
        hidden = _detail(page)
        assert hidden["selectedId"] == other["evidence_id"]
        assert OTHER_SOURCE in hidden["source"]
        assert page.locator("#evidence-library-list [data-evidence-id]").count() == 0

        page.click("#evidence-library-clear")
        page.click(f"#evidence-library-list [data-evidence-id='{linked['evidence_id']}']")
        page.wait_for_function(
            """id => document.getElementById('evidence-library').dataset.state === 'ready'
                && document.getElementById('evidence-library').dataset.selectedId === id""",
            arg=linked["evidence_id"],
        )
        chosen = _detail(page)
        assert chosen["selectedId"] == linked["evidence_id"]
        assert "Status: linked" in chosen["status"]
        assert LINKED_SOURCE in chosen["source"]
        assert chosen["links"] == LINK_ID
        assert "claim_support: not_established" in chosen["classification"]

        page.set_viewport_size({"width": 390, "height": 844})
        page.click("#evidence-library-show-detail")
        mobile = _detail(page)
        assert mobile["layout"] == "list-detail"
        assert mobile["pane"] == "detail"
        assert mobile["selectedId"] == linked["evidence_id"]
        assert mobile["links"] == chosen["links"]
        assert mobile["source"] == chosen["source"]
        assert mobile["classification"] == chosen["classification"]
        assert page.locator("#evidence-library-list").is_hidden()
        assert page.locator("#evidence-library-detail").is_visible()
        page.click("#evidence-library-show-list")
        listed = _detail(page)
        assert listed["pane"] == "list"
        assert listed["selectedId"] == linked["evidence_id"]
        assert page.locator("#evidence-library-detail").is_hidden()
        page.set_viewport_size({"width": 320, "height": 700})
        narrow = _detail(page)
        assert narrow["layout"] == "list-detail"
        assert narrow["selectedId"] == linked["evidence_id"]
        page.set_viewport_size({"width": 1440, "height": 1000})
        restored = _detail(page)
        assert restored["layout"] == "master-detail"
        assert restored["selectedId"] == linked["evidence_id"]
        assert restored["links"] == LINK_ID
        assert page.locator("#evidence-library-list").is_visible()
        assert page.locator("#evidence-library-detail").is_visible()
    finally:
        _close(playwright, context, node, profile, observed)


def test_same_case_rebind_reads_catalog_again_before_restoring_selection(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch)
    try:
        with TestClient(world.app, base_url="https://testserver") as client:
            csrf = _composed_login(client)
            created = [
                _receive(client, world.case, csrf, name, name, "ux15-rebind-" + name)
                for name in ("first-note.txt", "second-note.txt")
            ]
        _open(page, world)
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'ready'")
        selected = _detail(page)["selectedId"]
        desired = next(item["evidence_id"] for item in created if item["evidence_id"] != selected)
        page.click(f"#evidence-library-list [data-evidence-id='{desired}']")
        page.wait_for_function(
            "id => document.getElementById('evidence-library').dataset.selectedId === id", arg=desired
        )
        page.evaluate("() => window.workspaceClient.setCaseContext(window.workspaceClient.caseContext)")
        with page.expect_response(lambda response: response.request.method == "GET"
                and response.url.startswith(browser.SAME_ORIGIN + "/api/cases/evidence?")) as reauthorized:
            page.click(f"#evidence-library-list [data-evidence-id='{desired}']")
        assert reauthorized.value.status == 200
        assert desired in [item["evidence_id"] for item in reauthorized.value.json()["items"]]
        page.wait_for_function(
            """id => document.getElementById('evidence-library').dataset.state === 'ready'
                && document.getElementById('evidence-library').dataset.selectedId === id""", arg=desired
        )
        assert _detail(page)["selectedId"] == desired
    finally:
        _close(playwright, context, node, profile, observed)


def test_empty_error_and_locked_library_states_are_actionable(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch)
    try:
        _open(page, world)
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'empty'")
        assert page.locator("#evidence-library-add").is_visible()
        page.click("#evidence-library-add")
        assert page.evaluate("() => document.activeElement.id") == "evidence-attachment"
        assert "No artifacts are in this case catalog." in page.locator("#evidence-library-summary").inner_text()

        created = _receive_from_browser(
            page, world.case, OTHER_SOURCE, OTHER_ORIGINAL, "ux15-empty-then"
        )
        page.click("#evidence-library-refresh")
        page.wait_for_function(
            """id => document.getElementById('evidence-library').dataset.selectedId === id""",
            arg=created["evidence_id"],
        )
        selected = created["evidence_id"]
        assert OTHER_SOURCE in _detail(page)["source"]

        backend = world.app.state.evidence_workspace._backend
        saved = dict(backend._blobs)
        backend._blobs.clear()
        try:
            page.click("#evidence-library-refresh")
            page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'error'")
            failed = _detail(page)
            assert failed["selectedId"] == selected
            assert "ciphertext_unavailable" in failed["summary"]
            assert page.locator("#evidence-library-retry").is_visible()
        finally:
            backend._blobs.update(saved)
        page.click("#evidence-library-retry")
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'ready'")
        assert _detail(page)["selectedId"] == selected
        assert OTHER_SOURCE in _detail(page)["source"]

        world.owner_keys.lock()
        page.click("#evidence-library-refresh")
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'locked'")
        locked = page.locator("#evidence-library").inner_text()
        assert OTHER_SOURCE not in locked
        assert OTHER_ORIGINAL not in locked
        assert page.locator("#evidence-library-unlock").is_visible()
        assert _detail(page)["selectedId"] == selected
        world.owner_keys.unlock_passphrase(PASSPHRASE)
        page.click("#evidence-library-unlock")
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'ready'")
        assert _detail(page)["selectedId"] == selected
        assert OTHER_SOURCE in _detail(page)["source"]

        page.evaluate(
            """() => window.workspaceClient.setCaseContext({
                tenant_id: window.workspaceClient.caseContext.tenant_id,
                case_id: 'case-does-not-belong',
                resource_id: window.workspaceClient.caseContext.resource_id,
                revision: 1,
            })"""
        )
        page.click("#evidence-library-refresh")
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'locked'")
        denied = page.locator("#evidence-library").inner_text()
        assert "cannot open" in denied
        assert OTHER_SOURCE not in denied
        assert page.locator("#evidence-library-list [data-evidence-id]").count() == 0
    finally:
        _close(playwright, context, node, profile, observed)


@pytest.mark.parametrize("boundary", ["clear", "case"])
def test_delayed_catalog_cannot_restore_retired_evidence(tmp_path, monkeypatch, boundary):
    world, page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch)
    other_case = world.cases.create_case(actor_principal_id=world.owner.principal_id)
    returned_counts = []
    try:
        with TestClient(world.app, base_url="https://testserver") as client:
            csrf = _composed_login(client)
            _receive(client, world.case, csrf, OTHER_SOURCE, OTHER_ORIGINAL, "ux15-retired-read")
        _open(page, world)
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'ready'")
        assert OTHER_SOURCE in _detail(page)["source"]
        original = world.browser_bridge.handle

        def retire_before_response(request):
            # Preserve the real application's status, headers, and bytes. Move
            # the local privacy boundary between its read and HTTP delivery.
            result = original(request)
            if (request.method == "GET" and not returned_counts
                    and request.url.startswith(browser.SAME_ORIGIN + "/api/cases/evidence?")):
                assert result.status == 200
                body = result.body
                returned_counts.append(len(json.loads(body)["items"]))
                page.evaluate(
                    """payload => {
                        if (payload.boundary === 'clear') {
                            document.getElementById('workspace-clear-private-state').click();
                        } else window.workspaceClient.setCaseContext(payload.context);
                    }""",
                    {"boundary": boundary, "context": {
                        "tenant_id": other_case.tenant_id, "case_id": other_case.case_id,
                        "resource_id": other_case.resource_id, "revision": other_case.revision}},
                )
                assert result.body == body
            return result

        monkeypatch.setattr(world.browser_bridge, "handle", retire_before_response)
        page.evaluate("() => window.complaintEvidenceLibrary.refresh()")
        assert returned_counts == [1], "the original real catalog did not return its artifact"
        library_text = page.locator("#evidence-library").text_content()
        assert OTHER_SOURCE not in library_text
        assert OTHER_ORIGINAL not in library_text
        assert page.locator("#evidence-library-list [data-evidence-id]").count() == 0
        assert page.locator("#evidence-library-detail").get_attribute("data-evidence-id") in (None, "")
        assert page.evaluate("() => window.complaintEvidenceLibrary.selectedId()") == ""
    finally:
        _close(playwright, context, node, profile, observed)
