"""Evidence search is a derived chronology, not a stored index.

Filters select authorized artifacts by source, date, type, label, link, and
review state. A timeline entry opens that artifact and complaint section.
A stale, revoked, or foreign index cannot supply plaintext or permission.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from applications import evidence_workspace_api as search_api
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

FOREIGN_SECRET = "FOREIGN-SECRET-PLAINTEXT"
REVOKED_SECRET = "REVOKED-SECRET-PLAINTEXT"
CACHE_SECRET = "CACHE-SECRET-PLAINTEXT"
SECTION = "count-ii-retaliation"
ASSERTION = "notice-received"


def _ready(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "journey")
    from integrations.evidence_workspace import EvidenceWorkspace, MemoryByteBackend
    workspace = EvidenceWorkspace(
        world.cases,
        {world.owner.principal_id: world.owner_keys, world.lawyer.principal_id: world.recipient},
        MemoryByteBackend(),
        tmp_path / "evidence-root",
    )
    world.app.state.evidence_workspace = workspace
    world.evidence_root = tmp_path / "evidence-root"
    return world


def _context(case):
    return {
        "legal_context_status": "admitted",
        "context_owner": "request",
        "factual_graph_revision": "facts-22",
        "source_version": "ord-2024-22",
        "jurisdiction": "Example County",
        "authority_version": "auth-v22",
        "factual_assertions": [{
            "assertion_id": ASSERTION,
            "text": "The notice was received on 3 March.",
            "status": "current",
            "graph_revision": "facts-22",
        }],
        "admitted_requirements": [],
    }


def _files(root):
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def _seed(client, world, csrf):
    case = world.case
    notice = client.post("/api/cases/evidence", headers=_composed_headers(case, csrf), json={
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "source_filename": "notice-2024-03-03.txt",
        "original_filename": "notice-2024-03-03.txt",
        "media_type": "text/plain",
        "content_base64": base64.b64encode(b"Notice text for a synthetic case.\n").decode("ascii"),
        "idempotency_key": "ux22-notice",
    })
    assert notice.status_code == 201, notice.text
    payroll = client.post("/api/cases/evidence", headers=_composed_headers(case, csrf), json={
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "source_filename": "payroll-2024-06-01.csv",
        "original_filename": "payroll-2024-06-01.csv",
        "media_type": "text/csv",
        "content_base64": base64.b64encode(b"date,amount\n2024-06-01,10\n").decode("ascii"),
        "idempotency_key": "ux22-payroll",
    })
    assert payroll.status_code == 201, payroll.text
    notice_id = notice.json()["evidence_id"]
    payroll_id = payroll.json()["evidence_id"]
    labeled = client.post("/api/cases/evidence/annotations", headers=_composed_headers(case, csrf), json={
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "evidence_id": notice_id,
        "artifact_version": 1,
        "expected_case_revision": case.revision,
        "expected_annotation_revision": "",
        "idempotency_key": "ux22-label",
        "kind": "label",
        "label": "witness-statement",
    })
    assert labeled.status_code == 201, labeled.text
    actor = world.owner.principal_id
    workspace = world.app.state.evidence_workspace
    reviewed = workspace.transition(actor, {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "evidence_id": payroll_id,
        "idempotency_key": "ux22-review",
        "action": "needs-review",
        "expected_artifact_version": 1,
    })
    assert reviewed["ingestion_status"] == "needs-review"
    linked = workspace.transition(actor, {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "evidence_id": payroll_id,
        "idempotency_key": "ux22-link",
        "action": "link",
        "complaint_link_id": SECTION,
        "expected_artifact_version": 1,
    })
    assert linked["ingestion_status"] == "linked"
    assert linked["complaint_link_id"] == SECTION
    support = workspace.record_support_link(actor, {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "evidence_id": payroll_id,
        "artifact_version": 1,
        "idempotency_key": "ux22-support",
        "posture": "allegation",
        "origin": "human_statement",
        "target_kind": "factual_assertion",
        "target_id": ASSERTION,
        "page": 1,
        "span_start": 0,
        "span_end": 12,
        "case_context": _context(case),
    })
    assert support["status"] == "current"
    assert support["page"] == 1
    return notice_id, payroll_id


def _search(client, case, csrf, **filters):
    body = {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
    }
    body.update(filters)
    response = client.post("/api/cases/evidence/search", headers=_composed_headers(case, csrf), json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["derived_view"] is True
    assert payload["authority"] is False
    assert payload["plaintext_persisted"] is False
    assert payload["index_persisted"] is False
    assert payload["index_is_authority"] is False
    assert payload["stale_index_exposed"] is False
    return payload


def test_filters_select_authorized_evidence_and_chronology_opens_the_section(tmp_path):
    world = _ready(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        notice_id, payroll_id = _seed(client, world, csrf)
        before = _files(world.evidence_root)
        case = world.case

        by_source = _search(client, case, csrf, source="notice-2024")
        assert [item["evidence_id"] for item in by_source["items"]] == [notice_id]

        by_date = _search(client, case, csrf, date_from="2024-06-01", date_to="2024-06-01")
        assert [item["evidence_id"] for item in by_date["items"]] == [payroll_id]

        by_type = _search(client, case, csrf, type="text/csv")
        assert [item["evidence_id"] for item in by_type["items"]] == [payroll_id]

        by_label = _search(client, case, csrf, label="witness-statement")
        assert [item["evidence_id"] for item in by_label["items"]] == [notice_id]
        assert by_label["items"][0]["labels"] == ["witness-statement"]

        by_link = _search(client, case, csrf, link=SECTION)
        assert [item["evidence_id"] for item in by_link["items"]] == [payroll_id]

        by_review = _search(client, case, csrf, review_state="linked")
        assert [item["evidence_id"] for item in by_review["items"]] == [payroll_id]
        unreviewed = _search(client, case, csrf, review_state="unreviewed")
        assert [item["evidence_id"] for item in unreviewed["items"]] == [notice_id]

        opened = _search(client, case, csrf)
        assert [row["evidence_id"] for row in opened["chronology"]] == [notice_id, payroll_id]
        payroll = next(row for row in opened["chronology"] if row["evidence_id"] == payroll_id)
        assert payroll["complaint_section"] == SECTION
        assert payroll["artifact_version"] == 1
        assert payroll["page"] == 1
        assert payroll["span_start"] == 0
        assert payroll["span_end"] == 12
        assert payroll["event_date"] == "2024-06-01"
        assert payroll["authority"] is False
        assert _files(world.evidence_root) == before

        missed = _search(client, case, csrf, source="missing-source", label="witness-statement")
        assert missed["items"] == []
        assert missed["chronology"] == []


def test_stale_index_cannot_expose_revoked_or_foreign_plaintext(tmp_path):
    world = _ready(tmp_path)
    search_api._SEARCH_PLAINTEXT_CACHE = {"ev-cache-only": CACHE_SECRET}
    try:
        with TestClient(world.app, base_url="https://testserver") as client:
            csrf = _composed_login(client)
            notice_id, payroll_id = _seed(client, world, csrf)
            payload = _search(client, world.case, csrf, claimed_index=[
                {
                    "evidence_id": "ev-foreign",
                    "case_id": "foreign-case",
                    "tenant_id": "foreign-tenant",
                    "plaintext": FOREIGN_SECRET,
                    "source_filename": "secret-foreign.txt",
                },
                {
                    "evidence_id": "ev-revoked-missing",
                    "case_id": world.case.case_id,
                    "tenant_id": world.case.tenant_id,
                    "plaintext": REVOKED_SECRET,
                },
                {
                    "evidence_id": notice_id,
                    "case_id": world.case.case_id,
                    "tenant_id": world.case.tenant_id,
                    "plaintext": "INDEX-COPY-IS-NOT-AUTHORITY",
                },
            ])
            rendered = str(payload)
            assert FOREIGN_SECRET not in rendered
            assert REVOKED_SECRET not in rendered
            assert CACHE_SECRET not in rendered
            assert "INDEX-COPY-IS-NOT-AUTHORITY" not in rendered
            assert "secret-foreign.txt" not in rendered
            reasons = {(row["evidence_id"], row["reason"]) for row in payload["dropped_stale"]}
            assert ("ev-foreign", "foreign") in reasons
            assert ("ev-revoked-missing", "revoked") in reasons
            assert ("ev-cache-only", "revoked") in reasons
            assert (notice_id, "stale_not_authority") in reasons
            assert {item["evidence_id"] for item in payload["items"]} == {notice_id, payroll_id}
            assert all(item["derived"] is True and item["authority"] is False for item in payload["items"])
    finally:
        search_api._SEARCH_PLAINTEXT_CACHE = None


def test_locked_catalog_drops_the_claimed_index(tmp_path):
    world = _ready(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        notice_id, _payroll_id = _seed(client, world, csrf)
        world.owner_keys.lock()
        response = client.post("/api/cases/evidence/search", headers=_composed_headers(world.case, csrf), json={
            "tenant_id": world.case.tenant_id,
            "case_id": world.case.case_id,
            "resource_id": world.case.resource_id,
            "claimed_index": [{
                "evidence_id": notice_id,
                "case_id": world.case.case_id,
                "tenant_id": world.case.tenant_id,
                "plaintext": REVOKED_SECRET,
                "source_filename": "notice-2024-03-03.txt",
            }],
        })
        assert response.status_code in {401, 403, 409, 503}, response.text
        payload = response.json()
        assert payload["items"] == []
        assert payload["chronology"] == []
        assert payload["derived_view"] is True
        assert REVOKED_SECRET not in response.text
        assert payload["dropped_stale"] == [{"evidence_id": notice_id, "reason": "revoked"}]


def test_chronology_control_opens_the_artifact_and_complaint_section(tmp_path, monkeypatch):
    world = _ready(tmp_path)
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        _notice_id, payroll_id = _seed(client, world, csrf)
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux22-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
    try:
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
        page.evaluate(
            """section => {
                const marker = document.createElement('button');
                marker.id = 'complaint-section-marker';
                marker.dataset.complaintSection = section;
                marker.textContent = section;
                document.body.appendChild(marker);
            }""",
            SECTION,
        )
        page.click("[data-tab-target='evidence']")
        page.wait_for_selector("#evidence-filter-link")
        page.fill("#evidence-filter-link", SECTION)
        page.wait_for_function(
            """() => document.querySelectorAll('#evidence-chronology .evidence-chronology-entry').length === 1"""
        )
        page.click("#evidence-chronology .evidence-chronology-entry")
        page.wait_for_function(
            """(expected) => {
                const host = document.getElementById('evidence-library');
                const section = document.getElementById('evidence-complaint-section');
                const title = document.getElementById('evidence-detail-title');
                return host && host.dataset.complaintSection === expected.section
                    && host.dataset.selectedId === expected.evidenceId
                    && section && section.textContent.indexOf(expected.section) !== -1
                    && title && title.textContent.indexOf('payroll-2024-06-01.csv') !== -1
                    && document.activeElement && document.activeElement.id === 'complaint-section-marker';
            }""",
            arg={"section": SECTION, "evidenceId": payroll_id},
        )
        assert page.evaluate("() => window.localStorage.getItem('evidence-search-index')") is None
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
