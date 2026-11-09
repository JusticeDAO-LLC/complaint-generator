"""Review comments bind to evidence spans and complaint sections.

Exact artifact/version/span targets stay distinct from a qualified equivalent
and from fact, answer, legal-admission, and draft targets. Comment, accept,
and reject keep the acting principal, scope, revision, and audit lineage.
A reviewer cannot supply or borrow the owner's master key.
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
from applications.case_review import CaseReviewError, bound_review_targets, record_section_review
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from integrations.private_storage import UserOwnedKeySession
from tests import gui_native_browser as browser
from tests.test_gui32_private_review_http import _headers as _lawyer_headers
from tests.test_gui32_private_review_http import _world as _review_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PASSPHRASE = "synthetic-section-review-passphrase"
ORIGINAL = "The employer did not pay the wages that were due."


def _domains():
    return {
        "factual": {
            "status": "current",
            "revision": 1,
            "complete": True,
            "assertions": [{"id": "fact-wages", "text": "The employer did not pay wages.", "bound": True, "revision": 1}],
        },
        "legal": {"status": "admitted", "revision": 2, "factual_revision": 1, "authority_id": "auth-synthetic"},
        "evidence": {
            "status": "bound",
            "revision": 3,
            "factual_revision": 1,
            "legal_revision": 2,
            "exhibits": [{
                "id": "exhibit-1",
                "artifact_id": "artifact-wages",
                "artifact_version": 3,
                "fact_id": "fact-wages",
                "requirement_id": "req-wages",
                "supports_factual_revision": 1,
                "span": {"start": 4, "end": 12, "text": "wages"},
            }],
        },
        "proof": {
            "status": "executed",
            "result": "verified",
            "revision": 4,
            "factual_revision": 1,
            "evidence_revision": 3,
        },
    }


def _case_file():
    return {
        "case_id": "case-synthetic",
        "canonical_owner_principal_id": "owner-1",
        "workflow_domains": _domains(),
        "derived_dependency_requirements": {"requirements": [{
            "requirement_id": "req-wages",
            "passage_id": "pass-wages",
            "admitted_law": True,
            "citation": "Wage statute",
            "authority_id": "auth-synthetic",
            "source_span": {"start": 1, "end": 4, "text": "pay"},
            "fact_support": [{"fact_id": "fact-wages"}],
        }]},
        "draft_workflow": {"versions": [{
            "draft_id": "draft-wages", "revision": 2, "text": ORIGINAL, "text_digest": "digest-original",
            "actor_principal_id": "owner-1",
        }], "reviews": [], "exports": []},
        "review_case_state": {"answers": {"answer-wages": {"id": "answer-wages", "revision": 5, "text": "Wages were unpaid."}}},
    }


def _comment(case_file, **extra):
    body = {
        "operation": "comment_review_target",
        "request_id": "comment-span",
        "body": "The wage amount is not in this span.",
        "target_kind": "evidence_span",
        "artifact_id": "artifact-wages",
        "artifact_version": 3,
        "span_start": 4,
        "span_end": 12,
        "expected_target_revision": 3,
    }
    body.update(extra)
    return record_section_review(
        case_file, body, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1",
        membership="assigned-lawyer", action="case.review", case_id="case-synthetic",
    )


def test_exact_span_comment_accept_and_reject_keep_lineage_without_changing_draft():
    case_file = _case_file()
    kinds = {item["target_kind"] for item in bound_review_targets(case_file)}
    assert {"fact", "answer", "legal_admission", "draft_revision", "evidence_span", "complaint_section"} <= kinds
    commented = _comment(case_file)
    record = commented["record"]
    assert record["qualification"] == "exact"
    assert record["exact_span"] is True
    assert record["artifact_version"] == 3
    assert record["span_start"] == 4 and record["span_end"] == 12
    assert record["actor_principal_id"] == "lawyer-1"
    assert record["action_scope"] == "case.review"
    assert record["uses_owner_master_key"] is False
    assert record["updates_case_state"] is False
    assert case_file["draft_workflow"]["versions"][0]["text"] == ORIGINAL
    replay = _comment(case_file)
    assert replay["replayed"] is True
    assert len(case_file["section_review_records"]) == 1
    with pytest.raises(CaseReviewError) as mismatch:
        _comment(case_file, body="A different comment.")
    assert mismatch.value.code == "replay_mismatch"
    accepted = record_section_review(case_file, {
        "operation": "accept_review_target", "request_id": "accept-span", "comment_id": record["record_id"],
        "target_kind": "evidence_span", "artifact_id": "artifact-wages", "artifact_version": 3,
        "span_start": 4, "span_end": 12, "expected_target_revision": 3,
    }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review", case_id="case-synthetic")
    assert accepted["record"]["previous_record_id"] == record["record_id"]
    assert accepted["record"]["lineage"] == [record["record_id"]]
    assert accepted["record"]["status"] == "accepted"
    assert case_file["section_review_records"][0]["status"] == "accepted"
    other = _case_file()
    rejected_source = _comment(other, request_id="comment-for-reject")
    rejected = record_section_review(other, {
        "operation": "reject_review_target", "request_id": "reject-span", "comment_id": rejected_source["record"]["record_id"],
        "target_kind": "evidence_span", "artifact_id": "artifact-wages", "artifact_version": 3,
        "span_start": 4, "span_end": 12, "expected_target_revision": 3,
    }, actor_principal_id="owner-1", canonical_owner_principal_id="owner-1", membership="owner", action="case.review", case_id="case-synthetic")
    assert rejected["record"]["decision"] == "reject"
    assert rejected["record"]["actor_principal_id"] == "owner-1"
    assert other["draft_workflow"]["versions"][0]["text"] == ORIGINAL
    with pytest.raises(CaseReviewError) as stale:
        _comment(_case_file(), request_id="stale-span", artifact_version=2, expected_target_revision=2)
    assert stale.value.code == "stale_revision"
    with pytest.raises(CaseReviewError) as key:
        _comment(_case_file(), request_id="key-span", passphrase=PASSPHRASE)
    assert key.value.code == "actor_not_permitted"
    with pytest.raises(CaseReviewError) as borrowed:
        record_section_review(_case_file(), {
            "operation": "comment_review_target", "request_id": "borrowed-actor", "body": "Borrowed.",
            "actor_principal_id": "owner-1", "target_kind": "fact", "target_id": "fact-wages", "expected_target_revision": 1,
        }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    assert borrowed.value.code == "actor_not_permitted"


def test_qualified_evidence_and_complaint_section_targets():
    case_file = _case_file()
    qualified = record_section_review(case_file, {
        "operation": "comment_review_target", "request_id": "qualified-span",
        "body": "The page image has no verified byte span.",
        "target_kind": "qualified_evidence_span", "qualification": "qualified",
        "qualification_reason": "span_not_verified_against_artifact_bytes",
        "artifact_id": "artifact-wages", "artifact_version": 3, "expected_target_revision": 3,
    }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    assert qualified["record"]["qualification"] == "qualified"
    assert qualified["record"]["exact_span"] is False
    with pytest.raises(CaseReviewError) as exact_disguised:
        record_section_review(case_file, {
            "operation": "comment_review_target", "request_id": "disguised-span",
            "body": "This span is already exact.",
            "target_kind": "qualified_evidence_span", "qualification": "qualified",
            "qualification_reason": "span_not_verified_against_artifact_bytes",
            "artifact_id": "artifact-wages", "artifact_version": 3, "span_start": 4, "span_end": 12,
            "expected_target_revision": 3,
        }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    assert exact_disguised.value.code == "review_field"
    section = record_section_review(case_file, {
        "operation": "comment_review_target", "request_id": "section-comment",
        "body": "This section cites the wage span.",
        "target_kind": "complaint_section", "section_id": "req-wages", "draft_id": "draft-wages",
        "expected_target_revision": 2,
    }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    assert section["record"]["section_id"] == "req-wages"
    assert section["record"]["target_revision"] == 2
    assert case_file["draft_workflow"]["versions"][0]["revision"] == 2
    with pytest.raises(CaseReviewError) as wrong_section:
        record_section_review(case_file, {
            "operation": "accept_review_target", "request_id": "accept-wrong-target",
            "comment_id": section["record"]["record_id"], "target_kind": "fact", "target_id": "fact-wages",
            "expected_target_revision": 1,
        }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    assert wrong_section.value.code == "review_field"


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id, lawyer_principal_id=lawyer.principal_id,
        case_id=case.case_id, resource_id=case.resource_id, tenant_id=case.tenant_id,
        actions=frozenset({"case.read", "case.review", "case.download"}), expected_case_revision=case.revision,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-lawyer-credential": lawyer.principal_id,
        }),
        signing_key=os.urandom(32), ttl_seconds=300,
    ))
    keys = UserOwnedKeySession(tmp_path / "owner-keys")
    keys.create(protection="passphrase", passphrase=PASSPHRASE)
    keys.ensure_data_key(case.tenant_id, case.case_id)
    mediator = SimpleNamespace(
        intake_case_file={"workflow_domains": _domains(), "derived_dependency_requirements": _case_file()["derived_dependency_requirements"], "case_id": case.case_id},
        owner_key_session=keys,
    )
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id), authorize_delegated=lambda decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers, include_workspace=False, include_review=False, include_document=True)
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    app.state.owner_key_sessions = {owner.principal_id: keys}
    return SimpleNamespace(case=case, app=app, mediator=mediator, owner=owner, lawyer=lawyer, grant=grant, keys=keys)


def _client(app):
    return TestClient(app, base_url="https://testserver")


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _headers(case, csrf, membership_revision=None):
    headers = {
        "x-tenant-id": case.tenant_id, "x-case-id": case.case_id, "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision), "x-csrf-token": csrf,
    }
    if membership_revision is not None:
        headers["x-expected-membership-revision"] = str(membership_revision)
    return headers


def test_owner_http_comment_binds_the_span_and_lawyer_cannot_use_the_document_key(tmp_path):
    world = _world(tmp_path)
    owner = _client(world.app)
    csrf = _login(owner, "synthetic-owner-credential")
    saved = owner.post(f"/api/documents/{world.case.case_id}/draft-editor", headers=_headers(world.case, csrf), json={
        "request_id": "draft-original", "draft_id": "draft-wages", "text": ORIGINAL, "expected_head_revision": 0,
    })
    assert saved.status_code == 200, saved.text
    stage = owner.get(f"/api/documents/{world.case.case_id}/workflow-stage", headers=_headers(world.case, csrf))
    assert stage.status_code == 200, stage.text
    targets = stage.json()["draft_review_actions"]["bound_review_targets"]
    assert any(item["target_kind"] == "evidence_span" and item["artifact_version"] == 3 for item in targets)
    comment = owner.post(f"/api/documents/{world.case.case_id}/draft-reviews", headers=_headers(world.case, csrf), json={
        "operation": "comment_review_target", "request_id": "http-span",
        "body": "Tie this comment to the wage span.",
        "target_kind": "evidence_span", "artifact_id": "artifact-wages", "artifact_version": 3,
        "span_start": 4, "span_end": 12, "expected_target_revision": 3,
    })
    assert comment.status_code == 200, comment.text
    assert comment.json()["record"]["uses_owner_master_key"] is False
    replay = owner.post(f"/api/documents/{world.case.case_id}/draft-reviews", headers=_headers(world.case, csrf), json={
        "operation": "comment_review_target", "request_id": "http-span",
        "body": "Tie this comment to the wage span.",
        "target_kind": "evidence_span", "artifact_id": "artifact-wages", "artifact_version": 3,
        "span_start": 4, "span_end": 12, "expected_target_revision": 3,
    })
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    section = owner.post(f"/api/documents/{world.case.case_id}/draft-reviews", headers=_headers(world.case, csrf), json={
        "operation": "comment_review_target", "request_id": "http-section",
        "body": "The complaint section should cite the span.",
        "target_kind": "complaint_section", "section_id": "req-wages", "draft_id": "draft-wages",
        "expected_target_revision": saved.json()["current_revision"],
    })
    assert section.status_code == 200, section.text
    assert section.json()["record"]["section_id"] == "req-wages"
    lawyer = _client(world.app)
    lawyer_csrf = _login(lawyer, "synthetic-lawyer-credential")
    denied = lawyer.post(f"/api/documents/{world.case.case_id}/draft-reviews", headers=_headers(world.case, lawyer_csrf, world.grant.revision), json={
        "operation": "comment_review_target", "request_id": "lawyer-document",
        "body": "A reviewer must not open the owner draft key.",
        "target_kind": "evidence_span", "artifact_id": "artifact-wages", "artifact_version": 3,
        "span_start": 4, "span_end": 12, "expected_target_revision": 3, "passphrase": PASSPHRASE,
    })
    assert denied.status_code == 403
    current = owner.get(f"/api/documents/{world.case.case_id}/draft-editor", headers=_headers(world.case, csrf))
    assert current.json()["current_text"] == ORIGINAL


def test_reviewer_store_comment_does_not_call_the_owner_key(tmp_path, monkeypatch):
    world = _review_world(tmp_path)
    calls = {"owner": 0}
    original = UserOwnedKeySession.provider

    def guarded(self):
        if self is world.owner_keys:
            calls["owner"] += 1
        return original(self)

    monkeypatch.setattr(UserOwnedKeySession, "provider", guarded)
    with TestClient(world.review_app, base_url="https://testserver") as lawyer:
        csrf = lawyer.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-lawyer-credential"})
        assert csrf.status_code == 200, csrf.text
        token = csrf.json()["csrf_token"]
        view = lawyer.get(f"/api/legal-analysis/{world.case.case_id}/review-items", headers=_lawyer_headers(world))
        assert view.status_code == 200, view.text
        live = view.json()["live_revisions"]
        payload = {
            "operation": "comment_review_target", "request_id": "store-qualified",
            "body": "Qualified because the shared ledger has no exact span.",
            "target_kind": "qualified_evidence_span", "qualification": "qualified",
            "qualification_reason": "artifact_span_absent_from_shared_ledger",
            "artifact_id": "artifact-wages", "artifact_version": 3, "expected_target_revision": 3,
            "expected_review_revision": view.json()["review_revision"],
            **{f"expected_{name}": live[name] for name in ("case_revision", "source_revision", "fact_revision", "proof_revision")},
        }
        commented = lawyer.post(f"/api/legal-analysis/{world.case.case_id}/review-items", headers=_lawyer_headers(world, token), json=payload)
        assert commented.status_code == 200, commented.text
        record = commented.json()["record"]
        assert record["actor_principal_id"] == world.lawyer.principal_id
        assert record["uses_owner_master_key"] is False
        assert record["qualification"] == "qualified"
        assert record["seen_review_revision"] == view.json()["review_revision"]
        stolen = dict(payload)
        stolen["request_id"] = "store-stolen-key"
        stolen["passphrase"] = PASSPHRASE
        stolen["expected_review_revision"] = commented.json()["review_revision"]
        refused = lawyer.post(f"/api/legal-analysis/{world.case.case_id}/review-items", headers=_lawyer_headers(world, token), json=stolen)
        assert refused.status_code == 422
        assert refused.json()["error"] == "lawyer_review_field"
        assert calls["owner"] == 0
        accepted = lawyer.post(f"/api/legal-analysis/{world.case.case_id}/review-items", headers=_lawyer_headers(world, token), json={
            "operation": "accept_review_target", "request_id": "store-accept", "comment_id": record["record_id"],
            "target_kind": "qualified_evidence_span", "qualification": "qualified",
            "qualification_reason": "artifact_span_absent_from_shared_ledger",
            "artifact_id": "artifact-wages", "artifact_version": 3, "expected_target_revision": 3,
            "expected_review_revision": commented.json()["review_revision"],
            **{f"expected_{name}": live[name] for name in ("case_revision", "source_revision", "fact_revision", "proof_revision")},
        })
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["record"]["previous_record_id"] == record["record_id"]
        assert accepted.json()["record"]["actor_principal_id"] == world.lawyer.principal_id
        assert calls["owner"] == 0


def test_outline_comment_controls_record_the_span(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    world = _world(tmp_path)
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux33-profile"
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
        page.evaluate("async data => { await window.ComplaintDraft.load(data); }", {"caseId": world.case.case_id, "headers": headers, "membership": "owner"})
        page.fill("[data-role='draft-input']", ORIGINAL)
        page.click("[data-role='save-draft']")
        page.wait_for_function("() => document.querySelector('[data-role=save-state]').getAttribute('data-save-state') === 'saved'")
        page.evaluate("async data => { await window.ComplaintDraft.load(data); }", {"caseId": world.case.case_id, "headers": headers, "membership": "owner"})
        span = page.locator("[data-role='evidence-span']")
        assert span.get_attribute("data-artifact-version") == "3"
        assert span.get_attribute("data-target-qualification") == "exact"
        page.fill("[data-role='evidence-comment']", "The span does not state the dollar amount.")
        page.click("[data-role='comment-evidence']")
        page.wait_for_selector("[data-role='bound-review']")
        card = page.locator("[data-role='bound-review']").first
        assert card.get_attribute("data-target-kind") == "evidence_span"
        assert card.get_attribute("data-artifact-version") == "3"
        assert card.get_attribute("data-span-start") == "4"
        assert card.get_attribute("data-qualification") == "exact"
        assert page.locator("[data-role='stored-draft']").inner_text() == ORIGINAL
        page.fill("[data-role='section-comment']", "Cite the wage span in this section.")
        page.click("[data-role='comment-section']")
        page.wait_for_selector("[data-target-kind='complaint_section']")
        assert page.locator("[data-target-kind='complaint_section']").get_attribute("data-section-id") == "req-wages"
        page.click("[data-role='accept-bound-review']")
        page.wait_for_selector("[data-decision='accept']")
        assert page.locator("[data-decision='accept']").get_attribute("data-actor") == world.owner.principal_id
        reread = _client(world.app)
        csrf = _login(reread, "synthetic-owner-credential")
        current = reread.get(f"/api/documents/{world.case.case_id}/draft-editor", headers=_headers(world.case, csrf))
        assert current.status_code == 200
        assert current.json()["current_text"] == ORIGINAL
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
