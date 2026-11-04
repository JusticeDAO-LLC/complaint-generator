"""Honest readiness lists open work and does not treat a finished interview as a filing.

Unanswered factual questions, missing evidence, unreviewed sources, and draft
blockers come from the live outline and workflow stage. Links open chat or the
rich workspace. No further actionable interview question is an interview
outcome, not legal sufficiency, court readiness, or a successful filing.
"""
from __future__ import annotations

import os
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
from integrations.private_storage import UserOwnedKeySession
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PASSPHRASE = "synthetic-readiness-passphrase"


def _domains(*, unanswered=True, evidence_missing=True, source_unreviewed=True):
    factual = {
        "status": "current",
        "revision": 1,
        "complete": True,
        "assertions": [{
            "id": "fact-wages",
            "text": "The employer did not pay the final wages.",
            "bound": not unanswered,
            "revision": 1,
        }],
    }
    legal = {
        "status": "unreviewed" if source_unreviewed else "admitted",
        "revision": 2,
        "factual_revision": 1,
        "authority_id": "auth-synthetic",
    }
    evidence = {
        "status": "missing" if evidence_missing else "bound",
        "revision": 3,
        "factual_revision": 1,
        "legal_revision": 2,
        "exhibits": [] if evidence_missing else [{
            "id": "exhibit-1",
            "artifact_id": "artifact-wages",
            "artifact_version": 3,
            "fact_id": "fact-wages",
            "requirement_id": "req-wages",
            "supports_factual_revision": 1,
            "span": {"start": 4, "end": 12, "text": "wages"},
        }],
    }
    proof = {
        "status": "not_executed",
        "result": "unverified",
        "revision": 4,
        "factual_revision": 1,
        "evidence_revision": 3,
    }
    return {"factual": factual, "legal": legal, "evidence": evidence, "proof": proof}


def _requirements(source_unreviewed=True):
    stored = {"requirements": [{
        "requirement_id": "req-wages",
        "passage_id": "pass-wages",
        "admitted_law": not source_unreviewed,
        "citation": "Wage statute",
        "authority_id": "auth-synthetic",
        "source_span": {"start": 1, "end": 4, "text": "pay"},
        "fact_support": [{"fact_id": "fact-wages"}],
    }]}
    if source_unreviewed:
        stored["unresolved_research"] = [{"reason": "unresolved_research", "passage_id": "pass-open"}]
    return stored


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {"synthetic-owner-credential": owner.principal_id}),
        signing_key=os.urandom(32), ttl_seconds=300,
    ))
    keys = UserOwnedKeySession(tmp_path / "owner-keys")
    keys.create(protection="passphrase", passphrase=PASSPHRASE)
    keys.ensure_data_key(case.tenant_id, case.case_id)
    mediator = SimpleNamespace(
        intake_case_file={
            "workflow_domains": _domains(),
            "derived_dependency_requirements": _requirements(),
            "case_id": case.case_id,
        },
        owner_key_session=keys,
    )
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id), authorize_delegated=lambda decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers, include_workspace=False, include_review=False, include_document=True)
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    app.state.owner_key_sessions = {owner.principal_id: keys}
    return SimpleNamespace(case=case, app=app, mediator=mediator, owner=owner, keys=keys)


def _client(app):
    return TestClient(app, base_url="https://testserver")


def _login(client):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _headers(case, csrf, revision=None):
    return {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision if revision is None else revision),
        "x-csrf-token": csrf,
    }


def _use(world, **flags):
    world.mediator.intake_case_file["workflow_domains"] = _domains(**flags)
    world.mediator.intake_case_file["derived_dependency_requirements"] = _requirements(flags.get("source_unreviewed", True))


def test_live_outline_and_stage_keep_gaps_and_refuse_filing(tmp_path):
    world = _world(tmp_path)
    owner = _client(world.app)
    csrf = _login(owner)
    headers = _headers(world.case, csrf)
    outline = owner.get(f"/api/documents/{world.case.case_id}/complaint-outline", headers=headers)
    stage = owner.get(f"/api/documents/{world.case.case_id}/workflow-stage", headers=headers)
    assert outline.status_code == 200, outline.text
    assert stage.status_code == 200, stage.text
    body = outline.json()
    assert any(fact["fact_id"] == "fact-wages" and fact["bound"] is False for fact in body["facts"])
    reasons = {gap["reason"] for gap in body["gaps"]}
    assert "missing_evidence_span" in reasons
    assert "missing_admitted_authority" in reasons or body["unresolved_research"]
    assert "missing_draft_text" in reasons
    assert body["legal_sufficiency"] is False
    readiness = stage.json()["readiness"]
    assert readiness["legal_sufficiency"] is False
    assert readiness["automatic_court_filing"] is False
    assert stage.json()["court_filed"] is False
    assert "file_with_court" in stage.json()["refused_actions"]
    stale = owner.get(f"/api/documents/{world.case.case_id}/complaint-outline", headers=_headers(world.case, csrf, world.case.revision + 4))
    assert stale.status_code == 409, stale.text
    stale_body = stale.json()
    stale_code = stale_body.get("detail") or stale_body.get("error") or stale_body.get("code")
    assert stale_code in {"revision_conflict", "stale_revision"}
    stranger = _client(world.app)
    refused = stranger.get(f"/api/documents/{world.case.case_id}/complaint-outline", headers=headers)
    assert refused.status_code in {401, 403}


def test_readiness_links_open_chat_or_workspace_and_interview_end_is_not_filing(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    world = _world(tmp_path)
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux34-profile"
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
        assert page.locator("#complaint-readiness").get_attribute("data-legal-sufficiency") == "false"
        page.evaluate("() => window.ComplaintDraft.load({})")
        assert page.locator("#complaint-readiness").get_attribute("data-state") == "empty"
        assert page.locator("#complaint-readiness").get_attribute("data-court-ready") == "false"
        refused = page.evaluate(
            """async (caseId) => {
                await window.ComplaintDraft.load({caseId: caseId, headers: {'x-case-id': caseId}});
                const host = document.getElementById('complaint-readiness');
                return {state: host.dataset.state, filing: host.dataset.filingSucceeded, court: host.dataset.courtReady};
            }""",
            world.case.case_id,
        )
        assert refused["state"] == "denied"
        assert refused["filing"] == "false"
        assert refused["court"] == "false"
        issued = page.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin', headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: 'synthetic-owner-credential'})});
                if (!response.ok) throw new Error('login_' + response.status);
                return await response.json();
            }"""
        )
        headers = _headers(world.case, issued["csrf_token"])
        page.evaluate(
            "async data => { await window.ComplaintDraft.load(data); }",
            {"caseId": world.case.case_id, "headers": headers, "membership": "owner"},
        )
        host = page.locator("#complaint-readiness")
        assert host.get_attribute("data-state") == "gaps"
        assert host.get_attribute("data-interview-outcome") == "actionable_question"
        assert host.get_attribute("data-legal-sufficiency") == "false"
        assert host.get_attribute("data-court-ready") == "false"
        assert host.get_attribute("data-filing-succeeded") == "false"
        assert page.locator("#complaint-readiness-outcome").is_hidden()
        for kind in ("unanswered_question", "missing_evidence", "unreviewed_source", "draft_blocker"):
            assert page.locator(f"[data-kind='{kind}']").count() >= 1
        assert "final wages" in page.locator("[data-kind='unanswered_question']").first.inner_text()
        page.locator("[data-kind='unanswered_question'] [data-readiness-link]").first.click()
        page.wait_for_function("() => document.getElementById('complaint-case-shell').dataset.presentation === 'chat-only'")
        assert page.locator("[data-case-panel='mediator']").is_visible()
        assert page.locator("#complaint-readiness").get_attribute("data-last-destination") == "chat"
        page.locator("[data-kind='missing_evidence'] [data-readiness-link]").first.click()
        page.wait_for_function("() => document.getElementById('complaint-case-shell').dataset.presentation === 'full-workspace'")
        assert page.locator("[data-case-panel='evidence']").is_visible()
        assert page.locator("#complaint-readiness").get_attribute("data-last-task") == "evidence"
        page.locator("[data-kind='draft_blocker'] [data-readiness-link]").first.click()
        assert page.locator("[data-case-panel='draft']").is_visible()
        _use(world, unanswered=False, evidence_missing=True, source_unreviewed=True)
        page.evaluate(
            "async data => { await window.ComplaintDraft.load(data); }",
            {"caseId": world.case.case_id, "headers": headers, "membership": "owner"},
        )
        assert page.locator("[data-kind='unanswered_question']").count() == 0
        assert page.locator("[data-kind='missing_evidence']").count() >= 1
        assert page.locator("[data-kind='unreviewed_source']").count() >= 1
        assert page.locator("[data-kind='draft_blocker']").count() >= 1
        assert host.get_attribute("data-interview-outcome") == "no_actionable_question"
        assert "not legal sufficiency, court readiness, or a successful filing" in page.locator("#complaint-readiness-outcome").inner_text()
        assert host.get_attribute("data-legal-sufficiency") == "false"
        assert host.get_attribute("data-filing-succeeded") == "false"
        page.evaluate(
            "async data => { await window.ComplaintDraft.load(data); }",
            {"caseId": world.case.case_id, "headers": _headers(world.case, issued["csrf_token"], world.case.revision + 4), "membership": "owner"},
        )
        assert host.get_attribute("data-state") == "stale"
        assert host.get_attribute("data-court-ready") == "false"
        assert page.locator("[data-kind='unanswered_question']").count() == 0
        assert "stale" in page.locator("#complaint-readiness-summary").inner_text().lower()
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
