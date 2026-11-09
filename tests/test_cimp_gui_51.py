"""Administrative inspection of assignment and campaign operations.

Counts, assignment status, storage and worker states, and bounded diagnostic
codes are visible to an operational admin. The inspection does not open owner
envelopes. Incident handling does not impersonate a case owner and does not
grant case content. Playwright is not installed here, so the page contract is
checked through the composed ASGI app.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.admin_api import OPERATIONS_PATH, OPERATIONS_TASK_ID, SUPPORT_DIAGNOSTIC_CODES
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
OWNER_CREDENTIAL = "synthetic-owner-credential"
NARRATIVE = "synthetic-narrative-orchid"
MESSAGE = "synthetic-message-orchid"
EVIDENCE = "synthetic-evidence-orchid"


def _world(tmp_path):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    admin = principals.install_server_role(role="operational_admin")
    lawyer = principals.install_server_role(role="lawyer")
    owner = principals.register_from_request({})
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            ADMIN_CREDENTIAL: admin.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            OWNER_CREDENTIAL: owner.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")

    def workers():
        return [{"worker_id": "campaign-worker", "state": "stalled", "queue_depth": 2}]

    from applications.admin_api import OperationalAdminService
    directory = OperationalAdminService(
        principals=principals,
        sessions=sessions,
        clock=clock,
        audit_principal_ids=(admin.principal_id,),
        cases=cases,
        workers=workers,
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
        app=app, admin=admin, lawyer=lawyer, owner=owner, now=now, cases=cases, directory=directory,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _guard_owner_methods(cases):
    def _blocked(*_args, **_kwargs):
        raise AssertionError("operational admin impersonated a case owner")

    cases.list_cases = _blocked
    cases.select_case = _blocked
    cases.create_case = _blocked
    cases.read_owner_only_case = _blocked


def test_admin_sees_counts_status_and_bounded_diagnostics(tmp_path):
    world = _world(tmp_path)
    storage = SimpleNamespace(_receipts={
        "receipt-1": {
            "durable": False,
            "pending_replica": True,
            "storage_readiness": "unresolved",
            "failure_kind": "readback_mismatch",
            "error": NARRATIVE,
            "ref": EVIDENCE,
            "ciphertext_sha256": MESSAGE,
            "case_id": "sealed-case",
            "states": [{"note": NARRATIVE}],
        }
    })
    world.app.state.case_storage = storage
    world.directory._memberships = SimpleNamespace(recover=lambda: [
        SimpleNamespace(status="pending", expires_at=world.now["t"] + 100, case_id="sealed-case"),
        SimpleNamespace(status="accepted", expires_at=world.now["t"] + 100, case_id="sealed-case"),
        SimpleNamespace(status="pending", expires_at=world.now["t"] - 1, case_id="other-case"),
    ])
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as admin, TestClient(world.app, base_url="https://testserver") as lawyer:
        owner_token = _login(owner, OWNER_CREDENTIAL)
        created = owner.post("/api/cases", headers=_csrf(owner_token), json={"label": NARRATIVE})
        assert created.status_code == 201, created.text
        case_id = created.json()["case_id"]
        assert NARRATIVE in created.text
        _guard_owner_methods(world.cases)

        admin_token = _login(admin, ADMIN_CREDENTIAL)
        page = admin.get("/admin")
        assert page.status_code == 200
        assert "/api/admin/operations" in page.text
        assert "does not impersonate a case owner" in page.text
        assert 'data-case-content="withheld"' in page.text
        assert NARRATIVE not in page.text

        denied = lawyer.get(OPERATIONS_PATH, headers=_csrf(_login(lawyer, LAWYER_CREDENTIAL)))
        assert denied.status_code == 403
        assert denied.json()["error"] == "action_not_permitted"
        assert NARRATIVE not in denied.text

        inspected = admin.get(OPERATIONS_PATH, headers=_csrf(admin_token))
        assert inspected.status_code == 200, inspected.text
        body = inspected.json()
        assert body["task_id"] == OPERATIONS_TASK_ID
        assert body["case_counts"]["sealed_owner_indexes"] == 1
        assert body["case_counts"]["assigned_case_count"] == 2
        assert body["case_counts"]["exact_case_count_available"] is False
        assert body["case_counts"]["envelopes_opened"] is False
        assert body["case_counts"]["owner_impersonated"] is False
        assert body["assignment_status"]["counts"] == {
            "pending": 1,
            "accepted": 1,
            "declined": 0,
            "expired": 1,
            "removed": 0,
        }
        assert body["storage"]["readiness"] == "unresolved"
        assert body["storage"]["receipt_count"] == 1
        assert body["storage"]["pending_replica_count"] == 1
        assert body["storage"]["durable_count"] == 0
        assert body["workers"]["state"] == "stalled"
        assert body["workers"]["queue_depth"] == 2
        codes = [item["code"] for item in body["support_diagnostics"]]
        assert codes == ["storage_unresolved", "readback_mismatch", "worker_stalled", "assignment_backlog"]
        assert set(codes) <= SUPPORT_DIAGNOSTIC_CODES
        assert all(set(item) == {"code", "count"} for item in body["support_diagnostics"])
        assert body["case_content"] is None
        assert body["case_content_granted"] is False
        assert body["impersonated_case_owner"] is False
        assert body["opened_case_ids"] == []
        assert case_id not in inspected.text
        assert NARRATIVE not in inspected.text
        assert MESSAGE not in inspected.text
        assert EVIDENCE not in inspected.text
        assert "sealed-case" not in inspected.text


def test_incident_does_not_impersonate_or_grant_case_content(tmp_path):
    world = _world(tmp_path)
    grants = []
    world.directory._memberships = SimpleNamespace(recover=lambda: list(grants))
    _guard_owner_methods(world.cases)
    with TestClient(world.app, base_url="https://testserver") as admin:
        token = _login(admin, ADMIN_CREDENTIAL)
        impersonated = admin.post(OPERATIONS_PATH + "/incidents", headers=_csrf(token), json={
            "code": "worker_stalled",
            "scope": "worker",
            "owner_principal_id": world.owner.principal_id,
            "grant_case_content": True,
        })
        assert impersonated.status_code == 403
        assert impersonated.json()["error"] == "incident_cannot_impersonate_owner"
        assert grants == []
        assert NARRATIVE not in impersonated.text

        scoped = admin.post(OPERATIONS_PATH + "/incidents", headers=_csrf(token), json={
            "code": "storage_unresolved",
            "scope": "storage",
            "case_id": "sealed-case",
        })
        assert scoped.status_code == 403
        assert scoped.json()["error"] == "operations_case_scope_denied"
        assert grants == []

        narrative = admin.post(OPERATIONS_PATH + "/incidents", headers=_csrf(token), json={
            "code": "support_unobserved",
            "scope": "support",
            "narrative": NARRATIVE,
        })
        assert narrative.status_code == 403
        assert narrative.json()["error"] == "request_cannot_mint_authority"
        assert NARRATIVE not in narrative.text

        recorded = admin.post(OPERATIONS_PATH + "/incidents", headers=_csrf(token), json={
            "code": "worker_stalled",
            "scope": "worker",
        })
        assert recorded.status_code == 201, recorded.text
        body = recorded.json()
        assert body["incident"]["impersonated_case_owner"] is False
        assert body["incident"]["case_content_granted"] is False
        assert body["case_content"] is None
        assert body["opened_case_ids"] == []
        assert grants == []
        assert NARRATIVE not in recorded.text

        again = admin.get(OPERATIONS_PATH, headers=_csrf(token))
        assert again.status_code == 200
        assert again.json()["incidents"][0]["code"] == "worker_stalled"
        assert again.json()["incidents"][0]["case_content_granted"] is False

        forged = TestClient(world.app, base_url="https://testserver")
        forged.cookies.set(SESSION_COOKIE, "forged-session")
        rejected = forged.get(OPERATIONS_PATH, headers=_csrf(token))
        assert rejected.status_code == 401
        forged.close()
