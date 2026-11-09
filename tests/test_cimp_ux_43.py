"""Content-access decisions stay separate from operational administration.

Assignment and access actions are attributed in an audit record. A role,
approval label, or cached case in the body cannot authorize content or skip
a key grant. Tenant, case, and actor crossings are denied.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.admin_api import CONTENT_ACCESS_PATH, OperationalAdminService
from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_directory import CaseDirectory
from applications.case_review import CaseReviewError, assess_content_access, guard_mounted_review
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ADMIN_CREDENTIAL = "synthetic-admin-credential-ux43"
LAWYER_CREDENTIAL = "synthetic-lawyer-credential-ux43"
NARRATIVE = "synthetic-narrative-orchid-ux43"
MESSAGE = "synthetic-private-message-orchid-ux43"
EVIDENCE = "synthetic-evidence-orchid-ux43"
EXPORT = "synthetic-export-orchid-ux43"
KEY = "synthetic-key-orchid-ux43"
CASE_ID = "case-ux43-sealed"
TENANT_ID = "tenant-ux43"
RESOURCE_ID = "resource-ux43"
KEY_GRANT_ID = "server-key-grant-ux43"


class _Grant:
    def __init__(self, member_principal_id, case_id, status, *, tenant_id, revision, key_grant_id=None):
        self.member_principal_id = member_principal_id
        self.case_id = case_id
        self.status = status
        self.tenant_id = tenant_id
        self.revision = revision
        self.key_grant_id = key_grant_id
        self.expires_at = 2_000_000_000
        self.narrative = NARRATIVE
        self.evidence = EVIDENCE
        self.private_message = MESSAGE
        self.export_body = EXPORT
        self.key = KEY


class _Memberships:
    def __init__(self, grants):
        self._grants = list(grants)

    def recover(self):
        return tuple(self._grants)


class _SealedCase:
    def __init__(self, owner_principal_id):
        self.tenant_id = TENANT_ID
        self.case_id = CASE_ID
        self.resource_id = RESOURCE_ID
        self.owner_principal_id = owner_principal_id
        self.revision = 4
        self.narrative = NARRATIVE
        self.key = KEY


class _Catalog:
    def __init__(self, case):
        self.case = case

    def sealed_case(self, case_id):
        if case_id == self.case.case_id:
            return self.case
        return None


def _world(tmp_path):
    now = {"t": 1_700_000_100}

    def clock():
        now["t"] += 1
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "case-index", key=case_key, key_id="case-key")
    (cases._root / "owner.envelope").write_bytes(NARRATIVE.encode("utf-8"))
    admin = principals.install_server_role(role="operational_admin")
    lawyer = principals.install_server_role(role="lawyer")
    sealed = _SealedCase("owner-ux43")
    grants = [
        _Grant(lawyer.principal_id, CASE_ID, "accepted", tenant_id=TENANT_ID, revision=2, key_grant_id=KEY_GRANT_ID),
        _Grant(admin.principal_id, CASE_ID, "pending", tenant_id=TENANT_ID, revision=5, key_grant_id=None),
    ]
    memberships = _Memberships(grants)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            ADMIN_CREDENTIAL: admin.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    directory = OperationalAdminService(
        principals=principals,
        sessions=sessions,
        clock=clock,
        audit_principal_ids=(admin.principal_id,),
        memberships=memberships,
        cases=_Catalog(sealed),
    )
    app = FastAPI()
    compose_case_routes(
        app,
        authorizer=authorizer,
        browser_sessions=sessions,
        case_catalog=catalog,
        operational_admin=directory,
        include_workspace=False,
        include_review=False,
        include_document=False,
    )
    return SimpleNamespace(
        app=app,
        admin=admin,
        lawyer=lawyer,
        sealed=sealed,
        grants=grants,
        directory=directory,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token}


def _post(client, token, body):
    return client.post(CONTENT_ACCESS_PATH, headers=_csrf(token), json=body)


def _closed(text):
    assert NARRATIVE not in text
    assert MESSAGE not in text
    assert EVIDENCE not in text
    assert EXPORT not in text
    assert KEY not in text
    assert KEY_GRANT_ID not in text


def _live():
    return {
        "tenant_id": TENANT_ID,
        "case_id": CASE_ID,
        "resource_id": RESOURCE_ID,
        "owner_principal_id": "owner-ux43",
        "revision": 4,
    }


def test_operational_decision_is_not_legal_review_and_is_audited(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as admin, TestClient(world.app, base_url="https://testserver") as lawyer:
        admin_token = _login(admin, ADMIN_CREDENTIAL)
        lawyer_token = _login(lawyer, LAWYER_CREDENTIAL)
        blocked = _post(lawyer, lawyer_token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.lawyer.principal_id,
            "purpose": "legal_content_review",
        })
        assert blocked.status_code == 403
        assert blocked.json()["error"] == "action_not_permitted"
        _closed(blocked.text)

        recorded = _post(admin, admin_token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.admin.principal_id,
            "purpose": "operational_administration",
        })
        assert recorded.status_code == 201, recorded.text
        decision = recorded.json()["decision"]
        assert decision["task_id"] == "CIMP-UX-43"
        assert decision["decision"] == "operational_administration"
        assert decision["operational_administration"] is True
        assert decision["legal_review_authorized"] is False
        assert decision["content_permitted"] is False
        assert decision["key_access_used"] is False
        assert decision["key_bypassed"] is False
        assert decision["actor_principal_id"] == world.admin.principal_id
        assert decision["tenant_id"] == TENANT_ID
        assert decision["case_id"] == CASE_ID
        assert decision["case_revision"] == 4
        assert decision["authority"] == "server_operational_admin"
        assert recorded.json()["case_content"] is None
        assert recorded.json()["keys"] == []
        _closed(recorded.text)

        observed = _post(admin, admin_token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.lawyer.principal_id,
            "purpose": "assignment_observation",
        })
        assert observed.status_code == 201, observed.text
        assignment = observed.json()["decision"]
        assert assignment["decision"] == "assignment_observation"
        assert assignment["assignment_status"] == "accepted"
        assert assignment["membership_revision"] == 2
        assert assignment["content_permitted"] is False
        assert assignment["legal_review_authorized"] is False
        assert assignment["actor_principal_id"] == world.admin.principal_id
        assert assignment["subject_principal_id"] == world.lawyer.principal_id
        _closed(observed.text)

        trail = admin.get(CONTENT_ACCESS_PATH, headers=_csrf(admin_token))
        assert trail.status_code == 200, trail.text
        reasons = [item["reason"] for item in trail.json()["decisions"]]
        assert reasons == ["operational_metadata_only", "assignment_observed"]
        assert trail.json()["decisions"][1]["tenant_id"] == TENANT_ID
        _closed(trail.text)

        audit = admin.get("/api/admin/audit", headers=_csrf(admin_token))
        assert audit.status_code == 200
        actions = [item["action"] for item in audit.json()["events"]]
        assert "operational_administration" in actions
        assert "assignment_observation" in actions
        _closed(audit.text)


def test_body_authority_and_crossings_cannot_open_content(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as admin:
        token = _login(admin, ADMIN_CREDENTIAL)
        forged_role = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.admin.principal_id,
            "purpose": "legal_content_review",
            "roles": ["lawyer"],
            "approval_label": "approved",
        })
        assert forged_role.status_code == 403
        assert forged_role.json()["error"] == "request_cannot_mint_authority"
        _closed(forged_role.text)

        forged_approval = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.admin.principal_id,
            "purpose": "legal_content_review",
            "approval_label": "approved",
            "cached_case_object": {"permits_case_content": True, "narrative": NARRATIVE, "key": KEY},
        })
        assert forged_approval.status_code == 403
        assert forged_approval.json()["error"] == "body_authority_rejected"
        _closed(forged_approval.text)

        cached = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.lawyer.principal_id,
            "purpose": "legal_content_review",
            "case": {"case_id": CASE_ID, "permits_case_content": True, "key": KEY},
        })
        assert cached.status_code == 403
        assert cached.json()["error"] == "cached_case_rejected"

        key_body = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.admin.principal_id,
            "purpose": "legal_content_review",
            "bypass_key": KEY,
        })
        assert key_body.status_code == 403
        assert key_body.json()["error"] == "body_authority_rejected"

        tenant = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.lawyer.principal_id,
            "purpose": "assignment_observation",
            "tenant_id": "tenant-other-ux43",
        })
        assert tenant.status_code == 403
        assert tenant.json()["error"] == "tenant_crossing_denied"

        resource = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.lawyer.principal_id,
            "purpose": "operational_administration",
            "resource_id": "resource-other-ux43",
        })
        assert resource.status_code == 403
        assert resource.json()["error"] == "case_crossing_denied"

        actor = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.lawyer.principal_id,
            "purpose": "legal_content_review",
        })
        assert actor.status_code == 403
        assert actor.json()["error"] == "actor_crossing_denied"

        missing = _post(admin, token, {
            "case_id": "case-missing-ux43",
            "subject_principal_id": world.admin.principal_id,
            "purpose": "operational_administration",
        })
        assert missing.status_code == 403
        assert missing.json()["error"] == "missing_case"

        world.grants[1].status = "accepted"
        world.grants[1].key_grant_id = KEY_GRANT_ID
        still_admin = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.admin.principal_id,
            "purpose": "legal_content_review",
        })
        assert still_admin.status_code == 403
        assert still_admin.json()["error"] == "content_grant_required"
        _closed(still_admin.text)

        world.grants[1].status = "accepted"
        world.grants[1].key_grant_id = None
        needs_key = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.admin.principal_id,
            "purpose": "legal_content_review",
        })
        assert needs_key.status_code == 403
        assert needs_key.json()["error"] == "key_access_required"

        world.grants[1].status = "pending"
        no_grant = _post(admin, token, {
            "case_id": CASE_ID,
            "subject_principal_id": world.admin.principal_id,
            "purpose": "legal_content_review",
        })
        assert no_grant.status_code == 403
        assert no_grant.json()["error"] == "operational_admin_cannot_review_content"

        trail = admin.get(CONTENT_ACCESS_PATH, headers=_csrf(token))
        assert trail.status_code == 200
        decisions = trail.json()["decisions"]
        assert decisions
        assert all(item["content_permitted"] is False for item in decisions)
        assert all(item["key_bypassed"] is False for item in decisions)
        assert all(item["legal_review_authorized"] is False for item in decisions)
        assert {item["reason"] for item in decisions} >= {
            "body_authority_rejected",
            "cached_case_rejected",
            "tenant_crossing_denied",
            "case_crossing_denied",
            "actor_crossing_denied",
            "content_grant_required",
            "key_access_required",
            "operational_admin_cannot_review_content",
        }
        _closed(trail.text)


def test_separate_lawyer_grant_uses_server_key_and_rejects_cache(tmp_path):
    live = _live()
    membership = {
        "member_principal_id": "lawyer-ux43",
        "case_id": CASE_ID,
        "tenant_id": TENANT_ID,
        "status": "accepted",
        "revision": 2,
        "key_grant_id": KEY_GRANT_ID,
        "key": KEY,
        "narrative": NARRATIVE,
    }
    allowed = assess_content_access(
        actor_principal_id="lawyer-ux43",
        session_roles=("lawyer",),
        purpose="legal_content_review",
        body={"case_id": CASE_ID, "subject_principal_id": "lawyer-ux43", "purpose": "legal_content_review"},
        live_case=live,
        subject_membership=membership,
        key_grant_present=True,
        at=50,
    )
    assert allowed["legal_review_authorized"] is True
    assert allowed["content_permitted"] is True
    assert allowed["key_access_used"] is True
    assert allowed["key_bypassed"] is False
    assert allowed["operational_administration"] is False
    assert allowed["authority"] == "server_membership_and_key_grant"
    assert "key" not in allowed
    assert KEY not in repr(allowed)
    assert NARRATIVE not in repr(allowed)

    without_key = assess_content_access(
        actor_principal_id="lawyer-ux43",
        session_roles=("lawyer",),
        purpose="legal_content_review",
        body={"case_id": CASE_ID, "subject_principal_id": "lawyer-ux43", "purpose": "legal_content_review"},
        live_case=live,
        subject_membership=membership,
        key_grant_present=False,
        at=51,
    )
    assert without_key["reason"] == "key_access_required"
    assert without_key["content_permitted"] is False
    assert without_key["key_bypassed"] is False

    crossed = assess_content_access(
        actor_principal_id="lawyer-ux43",
        session_roles=("lawyer",),
        purpose="legal_content_review",
        body={
            "case_id": CASE_ID,
            "subject_principal_id": "lawyer-ux43",
            "purpose": "legal_content_review",
            "tenant_id": "other-tenant",
        },
        live_case=live,
        subject_membership={**membership, "tenant_id": "other-tenant"},
        key_grant_present=True,
        at=52,
    )
    assert crossed["reason"] == "tenant_crossing_denied"
    assert crossed["content_permitted"] is False

    request = SimpleNamespace(state=SimpleNamespace(
        browser_principal=SimpleNamespace(principal_id="lawyer-ux43"),
        cached_case_object={"permits_case_content": True, "key": KEY},
    ))
    decision = SimpleNamespace(
        case_id=CASE_ID,
        permits_case_content=True,
        membership="assigned-lawyer",
        actor_principal_id="lawyer-ux43",
        tenant_id=TENANT_ID,
    )
    authority = SimpleNamespace(
        case_id=CASE_ID,
        actor_principal_id="lawyer-ux43",
        canonical_owner_principal_id=TENANT_ID,
    )
    with pytest.raises(CaseReviewError) as cached_case:
        guard_mounted_review(request, CASE_ID, decision, authority)
    assert cached_case.value.code == "cached_case_rejected"

    request.state.cached_case_object = None
    admin_decision = SimpleNamespace(
        case_id=CASE_ID,
        permits_case_content=False,
        membership="operational-admin",
        actor_principal_id="admin-ux43",
        tenant_id=TENANT_ID,
    )
    with pytest.raises(CaseReviewError) as admin_review:
        guard_mounted_review(request, CASE_ID, admin_decision, authority)
    assert admin_review.value.code == "operational_admin_cannot_review_content"


def test_content_access_controls_record_a_real_decision(tmp_path, monkeypatch):
    from tests import gui_native_browser as browser

    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    world = _world(tmp_path)
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux43-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
    try:
        page.set_viewport_size({"width": 1440, "height": 1000})
        opened = page.goto(browser.SAME_ORIGIN + "/admin", wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        assert page.locator("#content-access-decision").count() == 1
        page.fill("#admin-credential", ADMIN_CREDENTIAL)
        page.click("#admin-login button[type=submit]")
        page.wait_for_function("() => document.getElementById('directory').dataset.state === 'ready'")
        page.fill("#content-access-case", CASE_ID)
        page.fill("#content-access-subject", world.lawyer.principal_id)
        page.select_option("#content-access-purpose", "assignment_observation")
        page.click("#content-access-decision button[type=submit]")
        page.wait_for_function(
            "() => document.getElementById('content-access-result').textContent.indexOf('assignment_observed') >= 0"
        )
        text = page.locator("#content-access-events").inner_text()
        assert world.admin.principal_id in text
        assert world.lawyer.principal_id in text
        assert "accepted" in text
        assert "content=false" in text
        assert "key_bypassed=false" in text
        assert TENANT_ID in text
        assert NARRATIVE not in page.content()
        assert KEY not in page.content()
        page.select_option("#content-access-purpose", "legal_content_review")
        page.fill("#content-access-subject", world.admin.principal_id)
        page.click("#content-access-decision button[type=submit]")
        page.wait_for_function("() => document.getElementById('directory').dataset.state === 'error'")
        assert "operational_admin_cannot_review_content" in page.locator("#admin-error").inner_text()
        page.click("#load-content-access")
        page.wait_for_function(
            "() => document.getElementById('content-access-events').textContent.indexOf('operational_admin_cannot_review_content') >= 0"
        )
        assert NARRATIVE not in page.content()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("#content-access-decision").is_visible()
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
