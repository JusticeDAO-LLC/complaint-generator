"""The complaint outline stays beside cited facts, spans, and admitted authority.

Model prose and an evidence label do not complete a requirement. Missing
support and unresolved research stay visible.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import BrowserSessionConfiguration, BrowserSessionService, PrincipalStoreCredentialAdapter
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {"synthetic-owner-credential": owner.principal_id}),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    mediator = SimpleNamespace(intake_case_file={})
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
                  authorize_delegated=lambda decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
                        include_workspace=False, include_review=False, include_document=True)
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    return SimpleNamespace(case=case, app=app, mediator=mediator)


def _client(app):
    return TestClient(app, base_url="https://testserver")


def _login(client):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _headers(case, csrf):
    return {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
        "x-csrf-token": csrf,
    }


def _cited_case():
    return {
        "draft_workflow": {"versions": [{
            "draft_id": "draft-wages",
            "revision": 1,
            "text": "The employer did not pay wages that were due.",
            "text_digest": "digest-wages",
        }]},
        "workflow_domains": {
            "factual": {"status": "current", "revision": 1, "assertions": [{
                "id": "fact-wages", "text": "The employer did not pay wages.", "bound": True, "revision": 1,
            }]},
            "evidence": {"status": "bound", "revision": 1, "exhibits": [{
                "id": "exhibit-stub",
                "artifact_id": "artifact-paystub",
                "fact_id": "fact-wages",
                "span_start": 12,
                "span_end": 28,
                "text": "wages were unpaid",
            }]},
        },
        "derived_dependency_requirements": {
            "requirements": [{
                "requirement_id": "req-wages",
                "name": "29 U.S.C. 206",
                "citation": "29 U.S.C. 206",
                "passage_id": "sha256:wage-passage",
                "authority_id": "29 U.S.C. 206",
                "admitted_law": True,
                "satisfied": True,
                "rule_text": "An employer must pay wages that are due.",
                "source_span": {"start": 0, "end": 38, "text": "An employer must pay wages that are due."},
                "fact_support": [{"fact_id": "fact-wages", "affects": "support"}],
                "legal_sufficiency": True,
                "proof": True,
            }],
            "unresolved_research": [],
        },
    }


def _prose_case():
    return {
        "draft_workflow": {"versions": [{
            "draft_id": "draft-prose",
            "revision": 2,
            "text": "The narrative says the claim is complete.",
        }]},
        "workflow_domains": {"factual": {"assertions": []}, "evidence": {"exhibits": [{
            "id": "label-only",
            "evidence_label": "pay stub",
        }]}},
        "derived_dependency_requirements": {
            "requirements": [{
                "name": "Unpaid wages",
                "model_prose": "This requirement is satisfied because the draft says so.",
                "evidence_label": "pay stub",
                "satisfied": True,
                "complete": True,
                "admitted_law": False,
            }],
            "unresolved_research": [{"reason": "no_admitted_passage", "visible": True}],
        },
    }


def test_outline_cites_artifact_span_and_admitted_authority(tmp_path):
    world = _world(tmp_path)
    world.mediator.intake_case_file = _cited_case()
    client = _client(world.app)
    csrf = _login(client)
    response = client.get(f"/api/documents/{world.case.case_id}/complaint-outline", headers=_headers(world.case, csrf))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["legal_sufficiency"] is False
    assert body["proof"] is False
    assert body["draft"]["text"].startswith("The employer did not pay")
    section = body["sections"][0]
    assert section["support_cited"] is True
    assert section["requirement_completed"] is False
    assert section["authority"]["passage_id"] == "sha256:wage-passage"
    assert section["authority"]["source_span"]["start"] == 0
    assert section["authority"]["source_span"]["end"] == 38
    assert section["authority"]["admitted_law"] is True
    assert section["facts"][0]["fact_id"] == "fact-wages"
    assert section["evidence"][0]["artifact_id"] == "artifact-paystub"
    assert section["evidence"][0]["span"] == {"start": 12, "end": 28, "text": "wages were unpaid", "unit": "utf-8-bytes"}
    assert section["caller_satisfied_ignored"] is True
    assert "missing_admitted_authority" not in {gap["reason"] for gap in section["gaps"]}


def test_model_prose_and_evidence_label_leave_the_requirement_open(tmp_path):
    world = _world(tmp_path)
    world.mediator.intake_case_file = _prose_case()
    client = _client(world.app)
    csrf = _login(client)
    response = client.get(f"/api/documents/{world.case.case_id}/complaint-outline", headers=_headers(world.case, csrf))
    assert response.status_code == 200, response.text
    body = response.json()
    section = body["sections"][0]
    assert section["support_cited"] is False
    assert section["requirement_completed"] is False
    assert section["authority"] is None
    assert section["evidence"] == []
    reasons = {gap["reason"] for gap in body["gaps"]}
    assert "model_prose_is_not_support" in reasons
    assert "evidence_label_is_not_support" in reasons
    assert "missing_admitted_authority" in reasons
    assert "missing_evidence_span" in reasons
    assert "no_admitted_passage" in reasons
    assert body["status"] == "gaps"


def test_empty_case_and_cross_case_do_not_invent_support(tmp_path):
    world = _world(tmp_path)
    client = _client(world.app)
    csrf = _login(client)
    empty = client.get(f"/api/documents/{world.case.case_id}/complaint-outline", headers=_headers(world.case, csrf))
    assert empty.status_code == 200, empty.text
    body = empty.json()
    assert body["sections"] == []
    assert body["draft"]["present"] is False
    assert {gap["reason"] for gap in body["gaps"]} >= {"missing_draft_text", "no_requirements"}
    assert body["legal_sufficiency"] is False
    other = dict(_headers(world.case, csrf))
    other["x-case-id"] = "case-not-this-one"
    denied = client.get("/api/documents/case-not-this-one/complaint-outline", headers=other)
    assert denied.status_code == 403
    assert denied.json()["error"] == "missing_case"
    assert "sections" not in denied.json()
    anonymous = _client(world.app)
    unsigned = anonymous.get(f"/api/documents/{world.case.case_id}/complaint-outline")
    assert unsigned.status_code == 401
    assert unsigned.json()["error"] in {"authentication_required", "authorizer_required", "session_required"}
    assert "sections" not in unsigned.json()


def test_workspace_shows_outline_beside_facts_and_keeps_gaps(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    world = _world(tmp_path)
    world.mediator.intake_case_file = _cited_case()
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux30-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    page.set_viewport_size({"width": 1440, "height": 1000})
    try:
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        assert page.locator("#complaint-outline").count() == 1
        issued = page.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin', headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: 'synthetic-owner-credential'})});
                if (!response.ok) throw new Error('login_' + response.status);
                return await response.json();
            }"""
        )
        assert issued["authenticated"] is True
        headers = _headers(world.case, issued["csrf_token"])
        page.evaluate(
            """async data => { await window.ComplaintDraft.load(data); }""",
            {"caseId": world.case.case_id, "headers": headers},
        )
        draft = page.locator("#complaint-outline [data-role='draft-text']")
        support = page.locator("#complaint-outline [data-role='support-column']")
        assert "did not pay wages" in draft.inner_text()
        assert draft.bounding_box()["x"] < support.bounding_box()["x"]
        authority = page.locator("#complaint-outline [data-role='admitted-authority']")
        assert authority.get_attribute("data-passage-id") == "sha256:wage-passage"
        assert authority.get_attribute("data-admitted-law") == "true"
        assert authority.get_attribute("href") == "#admitted-authority-sha256:wage-passage"
        span = page.locator("#complaint-outline [data-role='authority-span']")
        assert span.get_attribute("data-span-start") == "0"
        assert span.get_attribute("data-span-end") == "38"
        evidence = page.locator("#complaint-outline [data-role='evidence-span']")
        assert evidence.get_attribute("data-artifact-id") == "artifact-paystub"
        assert evidence.get_attribute("data-span-start") == "12"
        assert evidence.get_attribute("data-span-end") == "28"
        assert "wages were unpaid" in evidence.inner_text()
        assert page.locator("#complaint-outline [data-role='fact']").inner_text() == "The employer did not pay wages."
        assert page.get_attribute("#complaint-outline [data-role='outline-section']", "data-requirement-completed") == "false"
        page.click("#complaint-outline [data-role='open-section']")
        assert page.get_attribute("#complaint-outline [data-role='section-body']", "hidden") is None

        world.mediator.intake_case_file = _prose_case()
        page.evaluate(
            """async data => { await window.ComplaintDraft.load(data); }""",
            {"caseId": world.case.case_id, "headers": headers},
        )
        assert page.locator("#complaint-outline [data-role='admitted-authority']").count() == 0
        assert page.locator("#complaint-outline [data-role='evidence-span']").count() == 0
        assert page.get_attribute("#complaint-outline [data-role='model-prose']", "data-completes-requirement") == "false"
        assert page.get_attribute("#complaint-outline [data-role='evidence-label']", "data-completes-requirement") == "false"
        reasons = page.locator("#complaint-outline [data-role='gap']").evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('data-reason'))"
        )
        assert "model_prose_is_not_support" in reasons
        assert "missing_admitted_authority" in reasons
        assert "no_admitted_passage" in reasons
        assert page.get_attribute("#complaint-outline", "data-legal-sufficiency") == "false"
        page.click("#complaint-outline [data-role='open-section']")
        assert "Model prose, not support" in page.locator("#complaint-outline [data-role='model-prose']").inner_text()
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []


def test_workspace_template_loads_the_outline_script():
    html = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "complaint_draft.js").read_text(encoding="utf-8")
    assert 'id="complaint-outline"' in html
    assert 'src="/static/complaint_draft.js"' in html
    assert "data-requirement-completed" in script
    assert "data-completes-requirement" in script
    assert "/complaint-outline" in script
