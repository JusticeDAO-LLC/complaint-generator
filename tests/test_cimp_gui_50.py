"""Operational account administration over the composed ASGI app.

Admins provision accounts and change server-owned roles. Audit read is a
separate right. Directory payloads omit case narratives. Disabling an account
or demoting staff drops the live session for an already-open client and for a
forged replay of that cookie. The Playwright driver used by the Task02
Chromium harness is not installed in this environment, so those clients are
real ASGI sessions rather than a Chromium DOM.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.admin_api import ADMIN_PAGE_PATH, LEAST_PRIVILEGE_FIELDS, OperationalAdminService
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
PLAIN_ADMIN_CREDENTIAL = "synthetic-plain-admin-credential"
LAWYER_CREDENTIAL = "synthetic-lawyer-credential"
OWNER_CREDENTIAL = "synthetic-owner-credential"
NARRATIVE = "synthetic-narrative-orchid"
MESSAGE = "synthetic-message-orchid"
EVIDENCE = "synthetic-evidence-orchid"
SUMMARY = "synthetic-summary-orchid"


def _world(tmp_path, *, grants=None):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    admin = principals.install_server_role(role="operational_admin")
    plain = principals.install_server_role(role="operational_admin")
    lawyer = principals.install_server_role(role="lawyer")
    owner = principals.register_from_request({})
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            ADMIN_CREDENTIAL: admin.principal_id,
            PLAIN_ADMIN_CREDENTIAL: plain.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            OWNER_CREDENTIAL: owner.principal_id,
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
        memberships=grants,
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
        app=app, admin=admin, plain=plain, lawyer=lawyer, owner=owner, now=now, principals=principals,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    body = response.json()
    assert client.cookies.get(SESSION_COOKIE)
    return body["csrf_token"], body


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _accounts(client, token, **params):
    response = client.get("/api/admin/accounts", headers=_csrf(token), params=params)
    return response


def test_admin_lifecycle_is_server_owned_and_audit_is_separate(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as admin, TestClient(world.app, base_url="https://testserver") as plain, TestClient(world.app, base_url="https://testserver") as lawyer:
        admin_token, admin_session = _login(admin, ADMIN_CREDENTIAL)
        plain_token, _plain_session = _login(plain, PLAIN_ADMIN_CREDENTIAL)
        lawyer_token, _lawyer_session = _login(lawyer, LAWYER_CREDENTIAL)
        assert admin_session["roles"] == ["operational_admin"]

        page = admin.get(ADMIN_PAGE_PATH)
        assert page.status_code == 200
        assert "least-privilege" in page.text
        assert "separate right" in page.text
        assert "new WebSocket" not in page.text
        assert NARRATIVE not in page.text

        denied = _accounts(lawyer, lawyer_token)
        assert denied.status_code == 403
        assert denied.json()["error"] == "action_not_permitted"
        assert NARRATIVE not in denied.text

        minted = admin.post("/api/admin/accounts", headers=_csrf(admin_token), json={
            "account_kind": "lawyer",
            "role": "operational_admin",
        })
        assert minted.status_code == 403
        assert minted.json()["error"] == "request_cannot_mint_authority"

        created = admin.post("/api/admin/accounts", headers=_csrf(admin_token), json={"account_kind": "lawyer"})
        assert created.status_code == 201, created.text
        account = created.json()
        assert list(account) == list(LEAST_PRIVILEGE_FIELDS)
        assert account["roles"] == ["lawyer"]
        assert account["role_authority"] == "server"
        assert account["audit_right"] is False
        assert "tenant_id" not in account

        listed = _accounts(admin, admin_token)
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["fields"] == list(LEAST_PRIVILEGE_FIELDS)
        assert body["narratives"] == [] and body["messages"] == [] and body["evidence"] == []
        assert body["keys"] == [] and body["summaries"] == [] and body["case_content"] is None
        assert NARRATIVE not in listed.text and MESSAGE not in listed.text

        changed = admin.post(
            f"/api/admin/accounts/{world.lawyer.principal_id}/role",
            headers=_csrf(admin_token),
            json={"account_kind": "complainant", "expected_revision": world.lawyer.revision},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["roles"] == ["complainant"]
        assert changed.json()["revision"] == world.lawyer.revision + 1

        audit_denied = plain.get("/api/admin/audit", headers=_csrf(plain_token))
        assert audit_denied.status_code == 403
        assert audit_denied.json()["error"] == "audit_right_required"

        audit = admin.get("/api/admin/audit", headers=_csrf(admin_token))
        assert audit.status_code == 200, audit.text
        actions = [item["action"] for item in audit.json()["events"]]
        assert "provision" in actions and "role_change" in actions
        assert NARRATIVE not in audit.text

        granted = admin.post(
            f"/api/admin/accounts/{world.plain.principal_id}/audit",
            headers=_csrf(admin_token),
            json={"enabled": True, "expected_revision": world.plain.revision},
        )
        assert granted.status_code == 200, granted.text
        assert granted.json()["audit_right"] is True
        assert granted.json()["roles"] == ["operational_admin"]
        opened = plain.get("/api/admin/audit", headers=_csrf(plain_token))
        assert opened.status_code == 200, opened.text


def test_admin_search_does_not_enumerate_case_content(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as admin, TestClient(world.app, base_url="https://testserver") as owner:
        admin_token, _session = _login(admin, ADMIN_CREDENTIAL)
        owner_token, _owner_session = _login(owner, OWNER_CREDENTIAL)
        created = owner.post("/api/cases", headers=_csrf(owner_token), json={"label": NARRATIVE})
        assert created.status_code == 201, created.text
        case_id = created.json()["case_id"]
        assert NARRATIVE in created.text

        searched = _accounts(admin, admin_token, case_id=case_id, narrative=NARRATIVE, message=MESSAGE, evidence=EVIDENCE, summary=SUMMARY)
        assert searched.status_code == 403
        assert searched.json()["error"] == "request_cannot_mint_authority"
        assert NARRATIVE not in searched.text
        assert MESSAGE not in searched.text

        without_grant = _accounts(admin, admin_token, case_id=case_id)
        assert without_grant.status_code == 403
        assert without_grant.json()["error"] == "independent_case_grant_required"
        assert case_id not in without_grant.text
        assert NARRATIVE not in without_grant.text

    class _Matching:
        def __init__(self, principal_id, selected_case):
            self.principal_id = principal_id
            self.selected_case = selected_case

        def recover(self):
            return [SimpleNamespace(member_principal_id=self.principal_id, case_id=self.selected_case, status="accepted")]

    granted_world = _world(tmp_path / "granted-admin")
    granted_world.app.state.operational_admin._memberships = _Matching(granted_world.admin.principal_id, case_id)
    with TestClient(granted_world.app, base_url="https://testserver") as admin:
        admin_token, _session = _login(admin, ADMIN_CREDENTIAL)
        allowed = _accounts(admin, admin_token, case_id=case_id)
        assert allowed.status_code == 200, allowed.text
        payload = allowed.json()
        assert payload["case_id"] == case_id
        assert payload["narratives"] == []
        assert payload["messages"] == []
        assert payload["evidence"] == []
        assert payload["keys"] == []
        assert payload["summaries"] == []
        assert NARRATIVE not in allowed.text
        assert EVIDENCE not in allowed.text
        assert SUMMARY not in allowed.text


def test_disable_and_demotion_invalidate_open_and_forged_sessions(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as admin, TestClient(world.app, base_url="https://testserver") as lawyer, TestClient(world.app, base_url="https://testserver") as forged:
        admin_token, _admin_session = _login(admin, ADMIN_CREDENTIAL)
        lawyer_token, lawyer_session = _login(lawyer, LAWYER_CREDENTIAL)
        assert lawyer_session["roles"] == ["lawyer"]
        stolen = lawyer.cookies.get(SESSION_COOKIE)
        forged.cookies.set(SESSION_COOKIE, stolen)
        still_open = lawyer.get("/api/cases", headers=_csrf(lawyer_token))
        assert still_open.status_code == 200

        disabled = admin.post(
            f"/api/admin/accounts/{world.lawyer.principal_id}/status",
            headers=_csrf(admin_token),
            json={"status": "disabled", "expected_revision": world.lawyer.revision},
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["status"] == "disabled"

        open_again = lawyer.get("/api/cases", headers=_csrf(lawyer_token))
        assert open_again.status_code == 401
        forged_again = forged.get("/api/cases", headers=_csrf(lawyer_token))
        assert forged_again.status_code == 401
        assert NARRATIVE not in open_again.text
        replay = lawyer.post("/api/complaint-workspace/auth/login", json={"credential": LAWYER_CREDENTIAL})
        assert replay.status_code == 401

        restored = admin.post(
            f"/api/admin/accounts/{world.lawyer.principal_id}/status",
            headers=_csrf(admin_token),
            json={"status": "active", "expected_revision": disabled.json()["revision"]},
        )
        assert restored.status_code == 200, restored.text
        lawyer_token, lawyer_session = _login(lawyer, LAWYER_CREDENTIAL)
        assert lawyer_session["roles"] == ["lawyer"]
        demoted = admin.post(
            f"/api/admin/accounts/{world.lawyer.principal_id}/role",
            headers=_csrf(admin_token),
            json={"account_kind": "complainant", "expected_revision": restored.json()["revision"]},
        )
        assert demoted.status_code == 200, demoted.text
        stolen = lawyer.cookies.get(SESSION_COOKIE)
        forged.cookies.set(SESSION_COOKIE, stolen)
        assert lawyer.get("/api/cases", headers=_csrf(lawyer_token)).status_code == 401
        assert forged.post("/api/admin/accounts", headers=_csrf(lawyer_token), json={"account_kind": "operational_admin"}).status_code == 401
        rebound_token, rebound = _login(lawyer, LAWYER_CREDENTIAL)
        assert rebound["roles"] == ["complainant"]
        assert lawyer.get("/api/admin/accounts", headers=_csrf(rebound_token)).status_code == 403


def test_admin_page_contract_withholds_case_content(tmp_path):
    """The admin document is served by the app and does not embed case content.

    Chromium could not be driven here: the qualified Task02 harness imports
    Playwright, and that driver is not installed. Already-open clients and
    forged cookies are covered by the session test above.
    """

    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        page = client.get(ADMIN_PAGE_PATH)
        assert page.status_code == 200
        text = page.text
        assert 'data-case-content="withheld"' in text
        assert "WebSocket and server-sent events are not used" in text
        assert "/api/admin/accounts" in text
        assert "/api/admin/audit" in text
        assert NARRATIVE not in text
        assert "textContent" in text
