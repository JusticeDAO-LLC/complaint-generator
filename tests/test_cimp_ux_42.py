"""Operational admin workspace: account, role, assignment, and case-count filters.

Admin status returns sealed counts and roster metadata. It does not return
narratives, evidence, private messages, exports, or keys. A case-scoped
filter requires that admin's own accepted membership, and the response still
withholds case content.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.admin_api import WORKSPACE_PATH, OperationalAdminService
from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_directory import CaseDirectory
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ADMIN_CREDENTIAL = "synthetic-admin-credential"
LAWYER_CREDENTIAL = "synthetic-lawyer-credential"
OTHER_LAWYER_CREDENTIAL = "synthetic-other-lawyer-credential"
NARRATIVE = "synthetic-narrative-orchid-ux42"
MESSAGE = "synthetic-private-message-orchid-ux42"
EVIDENCE = "synthetic-evidence-orchid-ux42"
EXPORT = "synthetic-export-orchid-ux42"
KEY = "synthetic-key-orchid-ux42"
CASE_ID = "case-ux42-sealed"


class _Grant:
    def __init__(self, member_principal_id, case_id, status):
        self.member_principal_id = member_principal_id
        self.case_id = case_id
        self.status = status
        self.expires_at = 2_000_000_000
        self.narrative = NARRATIVE
        self.evidence = EVIDENCE
        self.private_message = MESSAGE
        self.export_body = EXPORT
        self.key = KEY


class _Memberships:
    def __init__(self, grants):
        self._grants = tuple(grants)

    def recover(self):
        return self._grants


def _world(tmp_path, *, grant_admin=False):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "case-index", key=case_key, key_id="case-key")
    (cases._root / "owner.envelope").write_bytes(NARRATIVE.encode("utf-8"))
    (cases._root / "note.txt").write_text(MESSAGE, encoding="utf-8")
    admin = principals.install_server_role(role="operational_admin")
    lawyer = principals.install_server_role(role="lawyer")
    other = principals.install_server_role(role="lawyer")
    grants = [
        _Grant(lawyer.principal_id, CASE_ID, "accepted"),
        _Grant(other.principal_id, "case-ux42-other", "pending"),
    ]
    if grant_admin:
        grants.append(_Grant(admin.principal_id, CASE_ID, "accepted"))
    memberships = _Memberships(grants)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            ADMIN_CREDENTIAL: admin.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            OTHER_LAWYER_CREDENTIAL: other.principal_id,
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
        cases=cases,
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
    return SimpleNamespace(app=app, admin=admin, lawyer=lawyer, other=other, principals=principals)


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token}


def _workspace(client, token, **params):
    return client.get(WORKSPACE_PATH, headers=_csrf(token), params=params)


def _assert_content_closed(text):
    assert NARRATIVE not in text
    assert MESSAGE not in text
    assert EVIDENCE not in text
    assert EXPORT not in text
    assert KEY not in text


def test_admin_workspace_filters_counts_and_withholds_content(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as admin, TestClient(world.app, base_url="https://testserver") as lawyer:
        admin_token = _login(admin, ADMIN_CREDENTIAL)
        lawyer_token = _login(lawyer, LAWYER_CREDENTIAL)

        page = admin.get("/admin")
        assert page.status_code == 200
        assert 'src="/static/complaint_admin.js"' in page.text
        script = admin.get("/static/complaint_admin.js")
        assert script.status_code == 200
        assert "application/javascript" in script.headers["content-type"] or "text/javascript" in script.headers["content-type"]
        _assert_content_closed(page.text + script.text)

        denied = _workspace(lawyer, lawyer_token)
        assert denied.status_code == 403
        assert denied.json()["error"] == "action_not_permitted"
        _assert_content_closed(denied.text)

        listed = _workspace(admin, admin_token)
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["state"] == "ready"
        assert body["task_id"] == "CIMP-UX-42"
        assert body["case_counts"]["sealed_owner_indexes"] == 1
        assert body["case_counts"]["envelopes_opened"] is False
        assert body["case_counts"]["assigned_case_count"] == 2
        assert body["assignment_status"]["counts"]["accepted"] == 1
        assert body["assignment_status"]["counts"]["pending"] == 1
        assert body["content_review"]["exposed"] is False
        assert body["content_review"]["requires_explicit_case_grant"] is True
        assert body["content_review"]["exports"] == []
        assert body["content_review"]["keys"] == []
        assert body["case_content"] is None
        assert body["case_content_granted"] is False
        ids = {item["principal_id"]: item for item in body["accounts"]}
        assert ids[world.lawyer.principal_id]["assigned_case_count"] == 1
        assert ids[world.lawyer.principal_id]["roles"] == ["lawyer"]
        assert ids[world.other.principal_id]["assignment_counts"]["pending"] == 1
        assert body["role_counts"]["lawyer"] == 2
        assert body["role_counts"]["operational_admin"] == 1
        _assert_content_closed(listed.text)

        lawyers = _workspace(admin, admin_token, account_kind="lawyer", assignment="assigned", assignment_status="accepted")
        assert lawyers.status_code == 200, lawyers.text
        narrowed = lawyers.json()
        assert [item["principal_id"] for item in narrowed["accounts"]] == [world.lawyer.principal_id]
        assert narrowed["filtered_account_count"] == 1
        assert narrowed["role_counts"]["lawyer"] == 1
        assert narrowed["role_counts"]["operational_admin"] == 0

        empty = _workspace(admin, admin_token, status="disabled")
        assert empty.status_code == 200, empty.text
        assert empty.json()["state"] == "empty"
        assert empty.json()["accounts"] == []
        assert empty.json()["filtered_account_count"] == 0

        rejected = _workspace(admin, admin_token, account_kind="owner")
        assert rejected.status_code == 403
        assert rejected.json()["error"] == "filter_rejected"

        exported = _workspace(admin, admin_token, export="narrative")
        assert exported.status_code == 403
        assert exported.json()["error"] == "admin_case_content_denied"
        _assert_content_closed(exported.text)

        scoped = _workspace(admin, admin_token, case_id=CASE_ID)
        assert scoped.status_code == 403
        assert scoped.json()["error"] == "independent_case_grant_required"
        _assert_content_closed(scoped.text)


def test_case_filter_needs_grant_and_still_withholds_content(tmp_path):
    world = _world(tmp_path, grant_admin=True)
    with TestClient(world.app, base_url="https://testserver") as admin:
        token = _login(admin, ADMIN_CREDENTIAL)
        scoped = _workspace(admin, token, case_id=CASE_ID, account_kind="lawyer")
        assert scoped.status_code == 200, scoped.text
        body = scoped.json()
        assert [item["principal_id"] for item in body["accounts"]] == [world.lawyer.principal_id]
        assert body["content_review"]["grant_present"] is True
        assert body["content_review"]["exposed"] is False
        assert body["content_review"]["narratives"] == []
        assert body["content_review"]["evidence"] == []
        assert body["content_review"]["private_messages"] == []
        assert body["case_content_granted"] is False
        _assert_content_closed(scoped.text)


def test_admin_directory_filters_in_the_browser(tmp_path, monkeypatch):
    from tests import gui_native_browser as browser

    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    world = _world(tmp_path)
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux42-profile"
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
        assert page.locator("#directory").get_attribute("data-state") == "locked"
        page.fill("#admin-credential", ADMIN_CREDENTIAL)
        page.click("#admin-login button[type=submit]")
        page.wait_for_function("() => document.getElementById('directory').dataset.state === 'ready'")
        assert page.input_value("#admin-credential") == ""
        assert page.locator("#account-rows tr").count() >= 3
        assert NARRATIVE not in page.content()
        page.select_option("#filter-account-kind", "lawyer")
        page.select_option("#filter-assignment", "assigned")
        page.select_option("#filter-assignment-status", "accepted")
        page.click("#workspace-filters button[type=submit]")
        page.wait_for_function(
            "() => document.querySelectorAll('#account-rows tr').length === 1"
        )
        assert world.lawyer.principal_id in page.locator("#account-rows").inner_text()
        assert world.other.principal_id not in page.locator("#account-rows").inner_text()
        assert page.locator("#directory").get_attribute("data-state") == "ready"
        page.fill("#filter-case-id", CASE_ID)
        page.click("#workspace-filters button[type=submit]")
        page.wait_for_function("() => document.getElementById('directory').dataset.state === 'error'")
        assert "independent_case_grant_required" in page.locator("#admin-error").inner_text()
        assert NARRATIVE not in page.content()
        page.select_option("#filter-status", "disabled")
        page.fill("#filter-case-id", "")
        page.select_option("#filter-assignment", "any")
        page.select_option("#filter-assignment-status", "")
        page.select_option("#filter-account-kind", "")
        page.click("#workspace-filters button[type=submit]")
        page.wait_for_function("() => document.getElementById('directory').dataset.state === 'empty'")
        assert page.locator("#empty-accounts").is_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("#directory").is_visible()
        assert page.locator("#workspace-filters").is_visible()
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
