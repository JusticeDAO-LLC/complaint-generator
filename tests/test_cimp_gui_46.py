"""Owners inspect and change participant grants.

Scope, expiry, and revocation use the current revision and an explicit
confirmation. Repeating the same change is idempotent and audited once.
The live grant is enforced on API content, download, inference, and browser
resume.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_assignment_api import CaseAssignmentService
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.case_routes import GRANT_CONTROL_PATH, compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
STRANGER_CREDENTIAL = "synthetic-access-token"
FULL_SCOPE = ["case.read", "case.review", "case.download", "case.message.send"]


def _world(tmp_path):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=clock,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
        principals=principals, cases=cases, memberships=memberships,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    assignments = CaseAssignmentService(
        principals=principals, cases=cases, memberships=memberships, key_grants=key_grants,
        sessions={}, clock=clock,
    )
    app = FastAPI()
    from applications.review_ui import attach_static_asset_routes
    attach_static_asset_routes(app)
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, stranger=stranger, authorizer=authorizer,
        assignments=assignments, now=now,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _accepted(world):
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "grants"})
        assert created.status_code == 201, created.text
        case = created.json()
        invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": list(FULL_SCOPE),
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "grant-invite",
        })
        assert invited.status_code == 201, invited.text
        grant_id = invited.json()["grant_id"]
        accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": list(FULL_SCOPE),
            "expected_version": 1,
            "idempotency_key": "grant-accept",
        })
        assert accepted.status_code == 200, accepted.text
        policy = world.authorizer.grant_assigned_lawyer(
            owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id,
            case_id=case["case_id"],
            resource_id=case["resource_id"],
            tenant_id=case["tenant_id"],
            actions=set(FULL_SCOPE),
            expected_case_revision=case["directory_revision"],
        )
        return SimpleNamespace(
            case=case, grant_id=grant_id, version=accepted.json()["version"],
            policy_revision=policy.revision, owner_token=owner_token, lawyer_token=lawyer_token,
            owner_client=owner_client, lawyer_client=lawyer_client,
        )


def _use(client, token, seed, surface, version=None):
    return client.post(f"/api/cases/assignments/{seed.grant_id}/use", headers=_csrf(token), json={
        "surface": surface,
        "expected_version": seed.version if version is None else version,
    })


def _protected(client, token, seed, path, *, method, body=None):
    params = {
        "tenant_id": seed.case["tenant_id"],
        "case_id": seed.case["case_id"],
        "resource_id": seed.case["resource_id"],
        "expected_revision": seed.case["directory_revision"],
        "expected_membership_revision": seed.policy_revision,
        "membership_grant_id": seed.grant_id,
        "membership_version": seed.version,
    }
    headers = _csrf(token)
    if method == "GET":
        return client.get(path, headers=headers, params=params)
    payload = dict(body or {})
    payload.update(params)
    return client.post(path, headers=headers, json=payload)


def test_owner_changes_are_confirmed_idempotent_and_audited(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client, TestClient(world.app, base_url="https://testserver") as stranger_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        stranger_token = _login(stranger_client, STRANGER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "control"})
        assert created.status_code == 201, created.text
        case = created.json()
        invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": list(FULL_SCOPE),
            "expires_at": world.now["t"] + 800,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "inspect-invite",
        })
        assert invited.status_code == 201, invited.text
        grant_id = invited.json()["grant_id"]
        accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": list(FULL_SCOPE),
            "expected_version": 1,
            "idempotency_key": "inspect-accept",
        })
        assert accepted.status_code == 200, accepted.text
        version = accepted.json()["version"]
        hidden = stranger_client.get(f"/api/cases/assignments/{grant_id}", headers=_csrf(stranger_token))
        assert hidden.status_code == 404
        assert hidden.json()["error"] == "missing_grant"
        anonymous = TestClient(world.app, base_url="https://testserver").get(f"/api/cases/assignments/{grant_id}")
        assert anonymous.status_code == 401
        inspected = owner_client.get(f"/api/cases/assignments/{grant_id}")
        assert inspected.status_code == 200, inspected.text
        body = inspected.json()
        assert body["effective"] is True
        assert body["revoked"] is False
        assert body["revision"] == version
        assert body["scope"] == sorted(FULL_SCOPE)
        assert body["expires_at"] == world.now["t"] + 800
        assert body["audit"] == []
        assert body["actor_is_encrypted_owner"] is False
        assert body["canonical_owner_principal_id"] == case["tenant_id"]
        unconfirmed = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "scope": ["case.read"],
            "expected_version": version,
            "idempotency_key": "narrow-scope",
        })
        assert unconfirmed.status_code == 403
        assert unconfirmed.json()["error"] == "confirmation_required"
        assert owner_client.get(f"/api/cases/assignments/{grant_id}").json()["revision"] == version
        stale = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "scope": ["case.read"],
            "expected_version": version - 1,
            "idempotency_key": "stale-scope",
        })
        assert stale.status_code == 409
        assert stale.json()["error"] == "revision_conflict"
        recipient = lawyer_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(lawyer_token), json={
            "confirm_grant_change": True,
            "scope": ["case.read"],
            "expected_version": version,
            "idempotency_key": "lawyer-change",
        })
        assert recipient.status_code == 404
        assert recipient.json()["error"] == "missing_grant"
        changed = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "scope": ["case.read", "case.download"],
            "expires_at": world.now["t"] + 50,
            "expected_version": version,
            "idempotency_key": "narrow-scope",
        })
        assert changed.status_code == 200, changed.text
        first = changed.json()
        assert first["idempotent_replay"] is False
        assert first["effective"] is True
        assert first["scope"] == ["case.download", "case.read"]
        assert first["revision"] == version + 1
        assert first["change"]["operation"] == "scope_and_expiry"
        assert first["change"]["confirmed"] is True
        assert first["change"]["from_revision"] == version
        assert len(first["audit"]) == 1
        assert first["audit"][0]["operation"] == "scope_and_expiry"
        replay = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "scope": ["case.read", "case.download"],
            "expires_at": world.now["t"] + 50,
            "expected_version": version,
            "idempotency_key": "narrow-scope",
        })
        assert replay.status_code == 200, replay.text
        assert replay.json()["idempotent_replay"] is True
        assert replay.json()["revision"] == first["revision"]
        assert len(replay.json()["audit"]) == 1
        mismatch = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "scope": ["case.read"],
            "expected_version": version,
            "idempotency_key": "narrow-scope",
        })
        assert mismatch.status_code == 409
        assert mismatch.json()["error"] == "replay_mismatch"
        assert owner_client.get(f"/api/cases/assignments/{grant_id}").json()["revision"] == first["revision"]
        lawyer_view = lawyer_client.get(f"/api/cases/assignments/{grant_id}")
        assert lawyer_view.status_code == 200
        assert lawyer_view.json()["scope"] == ["case.download", "case.read"]
        assert lawyer_view.json()["audit"] == []


def test_grant_changes_are_enforced_on_api_download_inference_and_resume(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "enforce"})
        assert created.status_code == 201, created.text
        case = created.json()
        invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": list(FULL_SCOPE),
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "enforce-invite",
        })
        grant_id = invited.json()["grant_id"]
        accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": list(FULL_SCOPE),
            "expected_version": 1,
            "idempotency_key": "enforce-accept",
        })
        policy = world.authorizer.grant_assigned_lawyer(
            owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id,
            case_id=case["case_id"],
            resource_id=case["resource_id"],
            tenant_id=case["tenant_id"],
            actions=set(FULL_SCOPE),
            expected_case_revision=case["directory_revision"],
        )
        seed = SimpleNamespace(
            case=case, grant_id=grant_id, version=accepted.json()["version"], policy_revision=policy.revision,
        )
        missing = lawyer_client.post("/api/cases/assignments/not-a-grant/use", headers=_csrf(lawyer_token), json={
            "surface": "api", "expected_version": seed.version,
        })
        assert missing.status_code == 404
        assert missing.json()["error"] == "missing_grant"
        for surface, action in (
            ("api", "case.read"),
            ("download", "case.download"),
            ("inference", "case.review"),
            ("browser_resume", "case.read"),
        ):
            allowed = _use(lawyer_client, lawyer_token, seed, surface)
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["admitted"] is True
            assert allowed.json()["surface"] == surface
            assert allowed.json()["action"] == action
            assert allowed.json()["actor_is_encrypted_owner"] is False
        stale_use = _use(lawyer_client, lawyer_token, seed, "api", version=seed.version - 1)
        assert stale_use.status_code == 409
        assert stale_use.json()["error"] == "revision_conflict"
        unknown = _use(lawyer_client, lawyer_token, seed, "stream")
        assert unknown.status_code == 403
        assert unknown.json()["error"] == "surface_required"
        narrowed = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "scope": ["case.read"],
            "expected_version": seed.version,
            "idempotency_key": "drop-review-download",
        })
        assert narrowed.status_code == 200, narrowed.text
        seed.version = narrowed.json()["revision"]
        assert _use(lawyer_client, lawyer_token, seed, "api").json()["admitted"] is True
        assert _use(lawyer_client, lawyer_token, seed, "browser_resume").json()["admitted"] is True
        for surface in ("download", "inference"):
            denied = _use(lawyer_client, lawyer_token, seed, surface)
            assert denied.status_code == 403
            assert denied.json()["error"] == "action_not_permitted"
        download = _protected(lawyer_client, lawyer_token, seed, "/api/documents/generated-document", method="GET")
        assert download.status_code == 403
        assert download.json()["error"] == "action_not_permitted"
        restored = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "scope": list(FULL_SCOPE),
            "expected_version": seed.version,
            "idempotency_key": "restore-scope",
        })
        assert restored.status_code == 200, restored.text
        seed.version = restored.json()["revision"]
        opened = _protected(lawyer_client, lawyer_token, seed, "/api/documents/generated-document", method="GET")
        assert opened.status_code == 503
        assert opened.json()["error"] == "case_handler_unavailable"
        inference = _protected(
            lawyer_client, lawyer_token, seed, "/api/complaint-workspace/inference/dispatch",
            method="POST", body={"purpose": "synthetic"},
        )
        assert inference.status_code == 503
        assert inference.json()["error"] == "case_handler_unavailable"
        resume = _protected(
            lawyer_client, lawyer_token, seed, "/api/complaint-workspace/intake-chat",
            method="POST", body={"interview_action": "resume"},
        )
        assert resume.status_code == 503
        assert resume.json()["error"] == "case_handler_unavailable"
        expired = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "expires_at": world.now["t"] + 5,
            "expected_version": seed.version,
            "idempotency_key": "short-expiry",
        })
        assert expired.status_code == 200, expired.text
        seed.version = expired.json()["revision"]
        world.now["t"] += 5
        for surface in ("api", "download", "inference", "browser_resume"):
            late = _use(lawyer_client, lawyer_token, seed, surface)
            assert late.status_code == 403
            assert late.json()["error"] == "grant_expired"
        late_download = _protected(lawyer_client, lawyer_token, seed, "/api/documents/generated-document", method="GET")
        assert late_download.status_code == 403
        assert late_download.json()["error"] == "grant_expired"
        world.now["t"] -= 5
        revoked = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "revoke": True,
            "expected_version": seed.version,
            "idempotency_key": "revoke-grant",
        })
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["revoked"] is True
        assert revoked.json()["effective"] is False
        assert revoked.json()["change"]["operation"] == "revocation"
        seed.version = revoked.json()["revision"]
        replay = owner_client.post(f"/api/cases/assignments/{grant_id}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "revoke": True,
            "expected_version": seed.version - 1,
            "idempotency_key": "revoke-grant",
        })
        assert replay.status_code == 200
        assert replay.json()["idempotent_replay"] is True
        assert len(owner_client.get(f"/api/cases/assignments/{grant_id}").json()["audit"]) == 4
        for surface in ("api", "download", "inference", "browser_resume"):
            blocked = _use(lawyer_client, lawyer_token, seed, surface)
            assert blocked.status_code == 403
            assert blocked.json()["error"] == "membership_removed"
        for path, method, body in (
            ("/api/documents/generated-document", "GET", None),
            ("/api/complaint-workspace/inference/dispatch", "POST", {"purpose": "synthetic"}),
            ("/api/complaint-workspace/intake-chat", "POST", {"interview_action": "resume"}),
        ):
            blocked_route = _protected(lawyer_client, lawyer_token, seed, path, method=method, body=body)
            assert blocked_route.status_code == 403
            assert blocked_route.json()["error"] == "membership_removed"


def test_workspace_grant_controls_confirm_and_resume(tmp_path):
    page_text = open("templates/workspace.html", encoding="utf-8").read()
    assert 'id="owner-grant-control"' in page_text
    assert "confirm_grant_change" in page_text
    assert "browser_resume" in page_text
    assert "new WebSocket" not in page_text[page_text.find('id="owner-grant-control"'):]
    assert "EventSource" not in page_text[page_text.find('id="owner-grant-control"'):]
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        shell = client.get(GRANT_CONTROL_PATH)
        assert shell.status_code == 200
        assert 'id="grant-confirm"' in shell.text
        assert "WebSocket and SSE are not used" in shell.text
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "browser"})
        case = created.json()
        invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read", "case.review", "case.download"],
            "expires_at": world.now["t"] + 400,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "browser-invite",
        })
        grant_id = invited.json()["grant_id"]
        accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": ["case.read", "case.review", "case.download"],
            "expected_version": 1,
            "idempotency_key": "browser-accept",
        })
        version = accepted.json()["version"]
        with _browser(tmp_path, world.app) as page:
            page.goto(browser.SAME_ORIGIN + GRANT_CONTROL_PATH, wait_until="domcontentloaded")
            page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
            assert page.get_attribute("#owner-grant-control", "data-task") == "CIMP-GUI-46"

            def sign_in(credential):
                page.evaluate(
                    """async (credential) => {
                        const response = await fetch('/api/complaint-workspace/auth/login', {
                            method: 'POST', credentials: 'same-origin',
                            headers: {'content-type': 'application/json'},
                            body: JSON.stringify({credential})
                        });
                        const payload = await response.json();
                        if (!payload.csrf_token) throw new Error('login failed');
                        document.getElementById('grant-csrf').value = payload.csrf_token;
                    }""",
                    credential,
                )

            sign_in(OWNER_CREDENTIAL)
            page.fill("#grant-id", grant_id)
            page.fill("#grant-revision", str(version))
            page.click("#grant-inspect")
            page.wait_for_function("document.getElementById('grant-status').textContent === 'inspected'")
            assert page.inner_text("#grant-effective-flag") == "yes"
            assert page.inner_text("#grant-revoked") == "no"
            page.fill("#grant-scope", "case.read")
            page.fill("#grant-idempotency", "browser-narrow")
            page.click("#grant-change")
            page.wait_for_function("document.getElementById('grant-status').textContent === 'confirmation_required'")
            assert page.inner_text("#grant-effective-revision") == str(version)
            page.check("#grant-confirm")
            page.click("#grant-change")
            page.wait_for_function("document.getElementById('grant-status').textContent === 'scope'")
            assert page.inner_text("#grant-effective-scope") == "case.read"
            sign_in(LAWYER_CREDENTIAL)
            page.click("#grant-use-resume")
            page.wait_for_function("document.getElementById('grant-status').textContent === 'admitted browser_resume'")
            sign_in(OWNER_CREDENTIAL)
            page.fill("#grant-idempotency", "browser-revoke")
            page.check("#grant-revoke")
            page.click("#grant-change")
            page.wait_for_function("document.getElementById('grant-status').textContent === 'revocation'")
            assert page.inner_text("#grant-revoked") == "yes"
            sign_in(LAWYER_CREDENTIAL)
            page.click("#grant-use-inference")
            page.wait_for_function("document.getElementById('grant-status').textContent === 'membership_removed'")
            page.click("#grant-use-download")
            page.wait_for_function("document.getElementById('grant-status').textContent === 'membership_removed'")


@contextmanager
def _browser(tmp_path, app):
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix_only"], "the trusted executor must fence this child"
    bridge = browser.SameOriginAsgiBridge(app)
    node, chromium = browser.pin_executables()
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = node.path
    profile = tmp_path / "grant-browser-profile"
    profile.mkdir(mode=0o700)
    playwright = None
    context = None
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        browser._assert_process_custody(node, chromium, profile)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        yield page
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
