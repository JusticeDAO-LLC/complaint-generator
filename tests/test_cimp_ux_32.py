"""Human review and model suggestions stay distinct from the owner's draft.

A reviewer can see the exact target revision, author, and provenance and can
record a bounded proposal. Messages, model suggestions, and machine proof stay
in separate records. Only an explicit owner acceptance is followed by a draft
save. Recording a suggestion does not change the encrypted draft.
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
from applications.case_review import (
    CaseReviewError,
    accept_draft_suggestion,
    project_draft_review_actions,
    submit_draft_suggestion,
)
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from integrations.private_storage import UserOwnedKeySession
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PASSPHRASE = "synthetic-suggestion-passphrase"
ORIGINAL = "The employer did not pay the wages that were due."
PROPOSAL = "The employer did not pay the wages that were due. The shortage was $400."


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
            "exhibits": [{"id": "exhibit-1", "supports_factual_revision": 1}],
        },
        "proof": {
            "status": "executed",
            "result": "verified",
            "revision": 4,
            "factual_revision": 1,
            "evidence_revision": 3,
        },
    }


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=frozenset({"case.read", "case.review", "case.download"}),
        expected_case_revision=case.revision,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-lawyer-credential": lawyer.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    keys = UserOwnedKeySession(tmp_path / "owner-keys")
    keys.create(protection="passphrase", passphrase=PASSPHRASE)
    keys.ensure_data_key(case.tenant_id, case.case_id)
    mediator = SimpleNamespace(
        intake_case_file={"workflow_domains": _domains(), "case_messages": [{
            "record_kind": "case_message",
            "author": "synthetic-correspondent",
            "body": "Please review the wage sentence.",
        }]},
        owner_key_session=keys,
    )
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
                  authorize_delegated=lambda decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
                        include_workspace=False, include_review=False, include_document=True)
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    app.state.owner_key_sessions = {owner.principal_id: keys}
    return SimpleNamespace(case=case, app=app, mediator=mediator, cases=cases, owner=owner, lawyer=lawyer,
                           grant=grant, keys=keys)


def _client(app):
    return TestClient(app, base_url="https://testserver")


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _headers(case, csrf, membership_revision=None):
    headers = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
        "x-csrf-token": csrf,
    }
    if membership_revision is not None:
        headers["x-expected-membership-revision"] = str(membership_revision)
    return headers


def _save_original(client, world, csrf):
    response = client.post(f"/api/documents/{world.case.case_id}/draft-editor", headers=_headers(world.case, csrf), json={
        "request_id": "draft-original",
        "draft_id": "draft-wages",
        "text": ORIGINAL,
        "expected_head_revision": 0,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_records_stay_separate_and_do_not_change_the_draft():
    case_file = {"workflow_domains": _domains(), "draft_workflow": {"versions": [{
        "draft_id": "draft-wages", "revision": 2, "text": ORIGINAL, "text_digest": "digest-original",
        "actor_principal_id": "owner-principal",
    }], "reviews": [], "exports": []}, "case_messages": [{"body": "A correspondence message.", "author": "correspondent"}]}
    common = {
        "draft_id": "draft-wages",
        "expected_revision": 2,
        "expected_text_digest": "digest-original",
    }
    human = submit_draft_suggestion(case_file, {
        "operation": "propose_bounded_change", "request_id": "human-1", "provenance": "human",
        "proposed_text": PROPOSAL, **common,
    }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    model = submit_draft_suggestion(case_file, {
        "operation": "record_draft_model_suggestion", "request_id": "model-1", "provenance": "model",
        "model_id": "synthetic-model", "proposed_text": "Model wording that is not adopted.", **common,
    }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    proof = submit_draft_suggestion(case_file, {
        "operation": "record_draft_machine_proof", "request_id": "proof-1", "provenance": "machine",
        "engine_name": "synthetic-engine", **common,
    }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    assert human["record"]["author"] == "lawyer-1"
    assert human["record"]["target_revision"] == 2
    assert human["record"]["target_author"] == "owner-principal"
    assert human["record"]["provenance"] == "human"
    assert model["record"]["provenance"] == "model"
    assert model["record"]["author"] == "synthetic-model"
    assert proof["record"]["record_kind"] == "machine_proof"
    assert proof["record"]["proof_status"] == "not_executed"
    assert case_file["draft_workflow"]["versions"][0]["text"] == ORIGINAL
    assert len(case_file["draft_workflow"]["versions"]) == 1
    projected = project_draft_review_actions(case_file, draft_id="draft-wages")
    assert projected["target_revision"] == 2
    assert projected["target_author"] == "owner-principal"
    assert len(projected["human_reviews"]) == 1
    assert len(projected["model_suggestions"]) == 1
    assert len(projected["machine_proofs"]) == 1
    assert projected["messages"][0]["body"] == "A correspondence message."
    assert all(item.get("record_kind") != "case_message" for item in projected["model_suggestions"])
    assert projected["suggestions_change_owner_draft"] is False
    with pytest.raises(CaseReviewError) as refused:
        submit_draft_suggestion(case_file, {
            "operation": "record_draft_model_suggestion", "request_id": "model-approve", "provenance": "model",
            "model_id": "synthetic-model", "proposed_text": "Adopt me silently.", "decision": "approved", **common,
        }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    assert refused.value.code == "draft_field"
    with pytest.raises(CaseReviewError) as stale:
        submit_draft_suggestion(case_file, {
            "operation": "propose_bounded_change", "request_id": "stale-1", "provenance": "human",
            "proposed_text": "Stale wording.", "draft_id": "draft-wages", "expected_revision": 1,
            "expected_text_digest": "digest-original",
        }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.review")
    assert stale.value.code == "stale_revision"
    with pytest.raises(CaseReviewError):
        accept_draft_suggestion(case_file, {
            "operation": "accept_draft_suggestion", "request_id": "accept-lawyer",
            "proposal_id": human["record"]["record_id"], "draft_id": "draft-wages",
            "expected_revision": 2, "expected_text_digest": "digest-original", "proposed_text": PROPOSAL,
        }, actor_principal_id="lawyer-1", canonical_owner_principal_id="owner-1", membership="assigned-lawyer", action="case.update")
    accepted = accept_draft_suggestion(case_file, {
        "operation": "accept_draft_suggestion", "request_id": "accept-owner",
        "proposal_id": model["record"]["record_id"], "draft_id": "draft-wages",
        "expected_revision": 2, "expected_text_digest": "digest-original",
        "proposed_text": "Model wording that is not adopted.",
    }, actor_principal_id="owner-1", canonical_owner_principal_id="owner-1", membership="owner", action="case.update")
    assert accepted["record"]["status"] == "accepted_for_draft"
    assert accepted["adopted_text"] == "Model wording that is not adopted."
    assert case_file["draft_workflow"]["versions"][0]["text"] == ORIGINAL
    with pytest.raises(CaseReviewError) as proof_accept:
        accept_draft_suggestion(case_file, {
            "operation": "accept_draft_suggestion", "request_id": "accept-proof",
            "proposal_id": proof["record"]["record_id"], "draft_id": "draft-wages",
            "expected_revision": 2, "expected_text_digest": "digest-original", "proposed_text": "not-proof",
        }, actor_principal_id="owner-1", canonical_owner_principal_id="owner-1", membership="owner", action="case.update")
    assert proof_accept.value.code == "draft_field"


def test_http_suggestion_does_not_replace_the_encrypted_draft(tmp_path):
    world = _world(tmp_path)
    owner = _client(world.app)
    owner_csrf = _login(owner, "synthetic-owner-credential")
    saved = _save_original(owner, world, owner_csrf)
    sealed_before = (world.cases.owned_revision_directory(actor_principal_id=world.owner.principal_id, case_id=world.case.case_id) / "draft-editor.json").read_bytes()
    stage = owner.get(f"/api/documents/{world.case.case_id}/workflow-stage", headers=_headers(world.case, owner_csrf))
    assert stage.status_code == 200, stage.text
    actions = stage.json()["draft_review_actions"]
    assert actions["target_revision"] == saved["current_revision"]
    assert actions["target_author"] == world.owner.principal_id
    assert actions["messages"][0]["body"] == "Please review the wage sentence."
    assert actions["messages"][0]["record_kind"] == "case_message"
    lawyer = _client(world.app)
    lawyer_csrf = _login(lawyer, "synthetic-lawyer-credential")
    lawyer_headers = _headers(world.case, lawyer_csrf, world.grant.revision)
    denied = lawyer.post(f"/api/documents/{world.case.case_id}/draft-reviews", headers=lawyer_headers, json={
        "operation": "propose_bounded_change",
        "request_id": "lawyer-without-grant",
        "draft_id": "draft-wages",
        "expected_revision": actions["target_revision"],
        "expected_text_digest": actions["target_text_digest"],
        "provenance": "human",
        "proposed_text": "This must not become the owner draft.",
    })
    assert denied.status_code == 403
    assert denied.json()["error"] == "case_key_grant_required"
    proposal = owner.post(f"/api/documents/{world.case.case_id}/draft-reviews", headers=_headers(world.case, owner_csrf), json={
        "operation": "propose_bounded_change",
        "request_id": "lawyer-proposal",
        "draft_id": "draft-wages",
        "expected_revision": actions["target_revision"],
        "expected_text_digest": actions["target_text_digest"],
        "provenance": "human",
        "proposed_text": PROPOSAL,
    })
    assert proposal.status_code == 200, proposal.text
    assert proposal.json()["record"]["changes_owner_draft"] is False
    model = owner.post(f"/api/documents/{world.case.case_id}/draft-reviews", headers=_headers(world.case, owner_csrf), json={
        "operation": "record_draft_model_suggestion",
        "request_id": "lawyer-model",
        "draft_id": "draft-wages",
        "expected_revision": actions["target_revision"],
        "expected_text_digest": actions["target_text_digest"],
        "provenance": "model",
        "model_id": "synthetic-model",
        "proposed_text": "A model sentence that stays a suggestion.",
    })
    assert model.status_code == 200, model.text
    proof = owner.post(f"/api/documents/{world.case.case_id}/draft-reviews", headers=_headers(world.case, owner_csrf), json={
        "operation": "record_draft_machine_proof",
        "request_id": "lawyer-proof",
        "draft_id": "draft-wages",
        "expected_revision": actions["target_revision"],
        "expected_text_digest": actions["target_text_digest"],
        "provenance": "machine",
        "engine_name": "synthetic-engine",
    })
    assert proof.status_code == 200, proof.text
    silent = lawyer.post(f"/api/documents/{world.case.case_id}/draft-versions", headers=lawyer_headers, json={
        "operation": "accept_draft_suggestion",
        "request_id": "lawyer-accept",
        "proposal_id": proposal.json()["record"]["record_id"],
        "draft_id": "draft-wages",
        "expected_revision": actions["target_revision"],
        "expected_text_digest": actions["target_text_digest"],
        "proposed_text": PROPOSAL,
    })
    assert silent.status_code == 403
    sealed_after = (world.cases.owned_revision_directory(actor_principal_id=world.owner.principal_id, case_id=world.case.case_id) / "draft-editor.json").read_bytes()
    assert sealed_after == sealed_before
    current = owner.get(f"/api/documents/{world.case.case_id}/draft-editor", headers=_headers(world.case, owner_csrf))
    assert current.json()["current_text"] == ORIGINAL
    accepted = owner.post(f"/api/documents/{world.case.case_id}/draft-versions", headers=_headers(world.case, owner_csrf), json={
        "operation": "accept_draft_suggestion",
        "request_id": "owner-accept",
        "proposal_id": proposal.json()["record"]["record_id"],
        "draft_id": "draft-wages",
        "expected_revision": actions["target_revision"],
        "expected_text_digest": actions["target_text_digest"],
        "proposed_text": PROPOSAL,
    })
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["adopted_text"] == PROPOSAL
    assert owner.get(f"/api/documents/{world.case.case_id}/draft-editor", headers=_headers(world.case, owner_csrf)).json()["current_text"] == ORIGINAL
    saved = owner.post(f"/api/documents/{world.case.case_id}/draft-editor", headers=_headers(world.case, owner_csrf), json={
        "request_id": "owner-adopt-save",
        "draft_id": "draft-wages",
        "text": accepted.json()["adopted_text"],
        "expected_head_revision": current.json()["head_revision"],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["current_text"] == PROPOSAL
    visible = owner.get(f"/api/documents/{world.case.case_id}/workflow-stage", headers=_headers(world.case, owner_csrf)).json()["draft_review_actions"]
    assert {item["provenance"] for item in visible["human_reviews"]} == {"human"}
    assert {item["provenance"] for item in visible["model_suggestions"]} == {"model"}
    assert {item["provenance"] for item in visible["machine_proofs"]} == {"machine"}
    assert visible["messages"][0]["record_kind"] == "case_message"
    assert all(item["record_kind"] != "case_message" for item in visible["model_suggestions"] + visible["machine_proofs"] + visible["human_reviews"])


def test_workspace_keeps_suggestion_actions_distinct(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    world = _world(tmp_path)
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux32-profile"
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
        page.evaluate(
            """async data => { await window.ComplaintDraft.load(data); }""",
            {"caseId": world.case.case_id, "headers": headers, "membership": "owner"},
        )
        assert page.locator("[data-role='human-reviews']").count() == 1
        assert page.locator("[data-role='model-suggestions']").count() == 1
        assert page.locator("[data-role='machine-proofs']").count() == 1
        assert page.locator("[data-role='review-messages']").count() == 1
        assert page.locator("[data-role='case-message']").inner_text() == "Please review the wage sentence."
        assert page.locator("[data-role='accept-suggestion']").count() == 0
        page.fill("[data-role='draft-input']", ORIGINAL)
        page.click("[data-role='save-draft']")
        page.wait_for_function("() => document.querySelector('[data-role=save-state]').getAttribute('data-save-state') === 'saved'")
        page.evaluate(
            """async data => { await window.ComplaintDraft.load(data); }""",
            {"caseId": world.case.case_id, "headers": headers, "membership": "owner"},
        )
        author = page.locator("[data-role='target-version']").get_attribute("data-target-author")
        assert author == world.owner.principal_id
        assert page.locator("[data-role='target-version']").get_attribute("data-target-revision") == "1"
        page.fill("[data-role='proposal-input']", PROPOSAL)
        page.click("[data-role='propose-change']")
        page.wait_for_selector("[data-role='human-review']")
        assert page.locator("[data-role='stored-draft']").inner_text() == ORIGINAL
        assert page.locator("[data-role='human-review']").get_attribute("data-provenance") == "human"
        assert page.locator("[data-role='human-review']").get_attribute("data-target-revision") == "1"
        page.click("[data-role='accept-suggestion']")
        page.wait_for_function(
            "() => document.querySelector('[data-role=stored-draft]').textContent.indexOf('$400') >= 0"
        )
        assert "$400" in page.locator("[data-role='stored-draft']").inner_text()
        reread = _client(world.app)
        csrf = _login(reread, "synthetic-owner-credential")
        current = reread.get(f"/api/documents/{world.case.case_id}/draft-editor", headers=_headers(world.case, csrf))
        assert current.status_code == 200
        assert "$400" in current.json()["current_text"]
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
