"""Scoped encrypted audit export.

Positive exports release only named fields for one case, actor, purpose, and
current grant. The stored bundle stays ciphertext unless the caller explicitly
decrypts it. Traversal, forged roles, mixed-tenant batches, stale grants, and
direct downloads are denied on the store, the admin service, and both HTTP
entry points.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.admin_api import OperationalAdminService
from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_audit import CaseAuditError, CaseAuditStore, owner_grant_reference
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PURPOSE = "purpose:case-review"
OPS_PURPOSE = "purpose:ops-review"
COMPLAINT = "synthetic-complaint-narrative-orchid"
FIELDS = ["event_id", "action", "actor_principal_id", "purpose_ref", "grant_id", "case_id", "tenant_id"]
ADMIN_CREDENTIAL = "synthetic-admin-credential"
OWNER_CREDENTIAL = "synthetic-owner-credential"
LAWYER_CREDENTIAL = "synthetic-lawyer-credential"


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    stranger = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    other = cases.create_case(actor_principal_id=stranger.principal_id)
    memberships = CaseMembershipStore(
        tmp_path / "memberships",
        key=os.urandom(32),
        key_id="membership-key",
        principals=principals,
        cases=cases,
        clock=lambda: 1_700_000_000,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants",
        key=os.urandom(32),
        key_id="resource-grant-key",
        principals=principals,
        cases=cases,
        memberships=memberships,
    )
    audit = CaseAuditStore(
        tmp_path / "audit",
        key=os.urandom(32),
        key_id="audit-key",
        principals=principals,
        cases=cases,
        memberships=memberships,
        key_grants=key_grants,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            ADMIN_CREDENTIAL: admin.principal_id,
            OWNER_CREDENTIAL: owner.principal_id,
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
        clock=lambda: 1_700_000_000,
        audit_principal_ids=(admin.principal_id,),
        cases=cases,
        case_audit=audit,
    )
    app = FastAPI()
    compose_case_routes(
        app,
        authorizer=authorizer,
        browser_sessions=sessions,
        case_catalog=catalog,
        operational_admin=directory,
        case_audit=audit,
        include_workspace=False,
        include_review=False,
        include_document=False,
    )
    return SimpleNamespace(
        audit=audit, cases=cases, memberships=memberships, owner=owner, lawyer=lawyer,
        admin=admin, stranger=stranger, case=case, other=other, directory=directory, app=app,
        principals=principals,
    )


def _record(world, *, purpose=PURPOSE):
    case = world.case
    return world.audit.record(
        actor_principal_id=world.owner.principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        action="case.read",
        expected_revision=case.revision,
        grant_id=owner_grant_reference(case.tenant_id),
        grant_kind="owner",
        purpose_ref=purpose,
        idempotency_key="audit-export-1",
    )


def _case_body(world, **extra):
    case = world.case
    body = {
        "actor_principal_id": world.owner.principal_id,
        "case_id": case.case_id,
        "tenant_id": case.tenant_id,
        "resource_id": case.resource_id,
        "grant_id": owner_grant_reference(case.tenant_id),
        "grant_kind": "owner",
        "grant_version": 0,
        "purpose_ref": PURPOSE,
        "expected_revision": case.revision,
        "fields": list(FIELDS),
        "artifact_ids": extra.pop("artifact_ids", []),
    }
    body.update(extra)
    return body


def _ops_body(world, **extra):
    body = {
        "actor_principal_id": world.admin.principal_id,
        "tenant_id": "operational",
        "grant_id": "audit-right:" + world.admin.principal_id,
        "grant_kind": "audit_right",
        "grant_version": world.admin.revision,
        "purpose_ref": OPS_PURPOSE,
        "fields": ["at", "action", "actor_principal_id", "detail"],
    }
    body.update(extra)
    return body


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _headers(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def test_export_releases_only_authorized_fields_and_stays_encrypted(tmp_path):
    world = _world(tmp_path)
    event = _record(world)
    sealed = world.audit.export_from_request(_case_body(world, artifact_ids=[event.event_id]), session_roles=world.owner.roles)
    assert sealed["encrypted"] is True
    assert sealed["user_decrypted"] is False
    assert sealed["records"] is None
    assert sealed["purpose_ref"] == PURPOSE
    assert sealed["grant_id"] == owner_grant_reference(world.case.tenant_id)
    assert sealed["actor_principal_id"] == world.owner.principal_id
    assert sealed["actor_is_encrypted_owner"] is False
    assert COMPLAINT not in str(sealed)
    stored = (tmp_path / "audit" / "exports" / (sealed["export_id"] + ".envelope")).read_bytes()
    assert not stored.startswith(b"{")
    assert COMPLAINT.encode() not in stored
    opened = world.audit.export_from_request(
        _case_body(world, export_id=sealed["export_id"], user_decrypt=True, decryption="user-decrypted"),
        session_roles=world.owner.roles,
    )
    assert opened["user_decrypted"] is True
    assert opened["envelope"] is None
    assert opened["records"] == [{
        "event_id": event.event_id,
        "action": "case.read",
        "actor_principal_id": world.owner.principal_id,
        "purpose_ref": PURPOSE,
        "grant_id": owner_grant_reference(world.case.tenant_id),
        "case_id": world.case.case_id,
        "tenant_id": world.case.tenant_id,
    }]
    assert "idempotency_key" not in opened["records"][0]
    with pytest.raises(CaseAuditError) as unauthorized:
        world.audit.export_from_request(
            _case_body(world, fields=FIELDS + ["idempotency_key"]),
            session_roles=world.owner.roles,
        )
    assert unauthorized.value.code == "unauthorized_field"


def test_traversal_forged_role_mixed_tenant_stale_grant_and_direct_download_are_denied(tmp_path):
    world = _world(tmp_path)
    event = _record(world)
    accepted = world.memberships.accept(
        member_principal_id=world.lawyer.principal_id,
        grant_id=world.memberships.invite(
            owner_principal_id=world.owner.principal_id,
            member_principal_id=world.lawyer.principal_id,
            case_id=world.case.case_id,
            resource_id=world.case.resource_id,
            tenant_id=world.case.tenant_id,
            actions={"case.read"},
            expires_at=1_700_003_600,
            expected_case_revision=world.case.revision,
            idempotency_key="invite-export",
        ).grant_id,
        expected_version=1,
        idempotency_key="accept-export",
    )
    world.memberships.update_scope(
        owner_principal_id=world.owner.principal_id,
        grant_id=accepted.grant_id,
        expected_version=accepted.version,
        expires_at=1_700_008_000,
    )
    denials = []

    def _deny(entry, body, **kwargs):
        with pytest.raises(CaseAuditError) as caught:
            entry(body, **kwargs)
        denials.append(caught.value.code)

    _deny(world.audit.export_from_request, _case_body(world, path="../audit-exports/secret"), session_roles=world.owner.roles)
    _deny(world.audit.export_from_request, _case_body(world, role="operational_admin"), session_roles=world.owner.roles)
    _deny(
        world.audit.export_from_request,
        _case_body(world),
        session_roles=("operational_admin",),
    )
    _deny(
        world.audit.export_from_request,
        _case_body(world, cases=[
            {"case_id": world.case.case_id, "tenant_id": world.case.tenant_id},
            {"case_id": world.other.case_id, "tenant_id": world.other.tenant_id},
        ]),
        session_roles=world.owner.roles,
    )
    _deny(
        world.audit.export_from_request,
        {
            "actor_principal_id": world.lawyer.principal_id,
            "case_id": world.case.case_id,
            "tenant_id": world.case.tenant_id,
            "resource_id": world.case.resource_id,
            "grant_id": accepted.grant_id,
            "grant_kind": "membership",
            "grant_version": accepted.version,
            "membership_version": accepted.version,
            "purpose_ref": PURPOSE,
            "expected_revision": world.case.revision,
            "fields": list(FIELDS),
            "artifact_ids": [event.event_id],
        },
        session_roles=world.lawyer.roles,
    )
    with pytest.raises(CaseAuditError) as direct_store:
        world.audit.direct_download("../exports/" + event.event_id)
    assert direct_store.value.code == "direct_download_denied"
    assert denials == ["traversal", "forged_role", "forged_role", "mixed_tenant_batch", "stale_grant"]

    ops_denials = []

    def _ops(body):
        with pytest.raises(Exception) as caught:
            world.directory.export_audit(world.admin.principal_id, world.admin.roles, body)
        ops_denials.append(caught.value.code)

    _ops(_ops_body(world, path="../audit"))
    _ops(_ops_body(world, role="lawyer"))
    _ops(_ops_body(world, cases=[
        {"case_id": world.case.case_id, "tenant_id": world.case.tenant_id},
        {"case_id": world.other.case_id, "tenant_id": world.other.tenant_id},
    ]))
    _ops(_ops_body(world, grant_version=world.admin.revision + 1))
    assert ops_denials == ["traversal", "forged_role", "mixed_tenant_batch", "stale_grant"]
    sealed_ops = world.directory.export_audit(world.admin.principal_id, world.admin.roles, _ops_body(world))
    assert sealed_ops["encrypted"] is True and sealed_ops["records"] is None

    owner_client = TestClient(world.app, base_url="https://testserver")
    admin_client = TestClient(world.app, base_url="https://testserver")
    owner_token = _login(owner_client, OWNER_CREDENTIAL)
    admin_token = _login(admin_client, ADMIN_CREDENTIAL)
    http_cases = [
        (owner_client, "/api/cases/audit-exports", _case_body(world, path="../audit-exports/secret"), owner_token, "traversal"),
        (owner_client, "/api/cases/audit-exports", _case_body(world, role="operational_admin"), owner_token, "forged_role"),
        (owner_client, "/api/cases/audit-exports", _case_body(world, cases=[
            {"case_id": world.case.case_id, "tenant_id": world.case.tenant_id},
            {"case_id": world.other.case_id, "tenant_id": world.other.tenant_id},
        ]), owner_token, "mixed_tenant_batch"),
        (owner_client, "/api/cases/audit-exports", _case_body(world, grant_version=4), owner_token, "stale_grant"),
        (admin_client, "/api/admin/audit/export", _ops_body(world, path="../audit"), admin_token, "traversal"),
        (admin_client, "/api/admin/audit/export", _ops_body(world, role="lawyer"), admin_token, "forged_role"),
        (admin_client, "/api/admin/audit/export", _ops_body(world, cases=[
            {"case_id": "operational-audit", "tenant_id": "operational"},
            {"case_id": world.other.case_id, "tenant_id": world.other.tenant_id},
        ]), admin_token, "mixed_tenant_batch"),
        (admin_client, "/api/admin/audit/export", _ops_body(world, grant_version=world.admin.revision + 3), admin_token, "stale_grant"),
    ]
    for client, path, body, token, code in http_cases:
        response = client.post(path, json=body, headers=_headers(token))
        assert response.status_code == 403, (path, str(response.request.url), response.text)
        assert response.json()["error"] == code
    positive = owner_client.post("/api/cases/audit-exports", json=_case_body(world, artifact_ids=[event.event_id]), headers=_headers(owner_token))
    assert positive.status_code == 200, positive.text
    assert positive.json()["encrypted"] is True
    assert positive.json()["records"] is None
    downloads = [
        "/api/cases/audit-exports/" + positive.json()["export_id"],
        "/api/admin/audit/exports/" + sealed_ops["export_id"],
        "/api/documents/download?path=../audit-exports/secret",
    ]
    for path in downloads:
        response = owner_client.get(path)
        assert response.status_code == 403, response.text
        assert response.json()["error"] == "direct_download_denied"
    with pytest.raises(CaseAuditError) as direct:
        world.audit.direct_download(downloads[0])
    assert direct.value.code == "direct_download_denied"


def test_actual_reopened_metadata_export_cannot_ignore_membership_removed_during_crypto(tmp_path,monkeypatch):
    import applications.case_audit as audit
    world=_world(tmp_path);event=_record(world)
    invitation=world.memberships.invite(owner_principal_id=world.owner.principal_id,
        member_principal_id=world.lawyer.principal_id,case_id=world.case.case_id,
        resource_id=world.case.resource_id,tenant_id=world.case.tenant_id,actions={'case.read'},
        expires_at=1_700_003_600,expected_case_revision=world.case.revision,idempotency_key='synthetic-late-export-invite')
    member=world.memberships.accept(member_principal_id=world.lawyer.principal_id,
        grant_id=invitation.grant_id,expected_version=invitation.version,idempotency_key='synthetic-late-export-accept')
    body=_case_body(world,actor_principal_id=world.lawyer.principal_id,grant_id=member.grant_id,
        grant_kind='membership',grant_version=member.version,membership_version=member.version,artifact_ids=[event.event_id])
    sealed=world.audit.export_from_request(body,session_roles=world.lawyer.roles)
    actual=audit.open_private_artifact;completed=[]
    def decrypt_then_remove(*args,**kwargs):
        value=actual(*args,**kwargs)
        if kwargs['binding'].artifact_kind=='case-audit-export':
            world.memberships.remove(owner_principal_id=world.owner.principal_id,
                grant_id=member.grant_id,expected_version=member.version)
            completed.append(True)
        return value
    monkeypatch.setattr(audit,'open_private_artifact',decrypt_then_remove)
    with pytest.raises(CaseAuditError):
        world.audit.export_from_request({**body,'export_id':sealed['export_id'],
            'user_decrypt':True,'decryption':'user-decrypted'},session_roles=world.lawyer.roles)
    assert completed==[True]


def test_actual_public_export_reopen_refuses_after_real_cookie_revoked_during_crypto(tmp_path,monkeypatch):
    import applications.case_audit as audit
    world=_world(tmp_path);event=_record(world)
    with TestClient(world.app,base_url='https://testserver') as client:
        csrf=_login(client,OWNER_CREDENTIAL);token=client.cookies.get(SESSION_COOKIE)
        initial=client.post('/api/cases/audit-exports',headers=_headers(csrf),json=_case_body(world,artifact_ids=[event.event_id]))
        assert initial.status_code==200
        actual=audit.open_private_artifact;completed=[]
        def decrypt_then_logout(*args,**kwargs):
            value=actual(*args,**kwargs)
            if kwargs['binding'].artifact_kind=='case-audit-export':
                world.app.state.browser_sessions.logout(token,csrf_token=csrf)
                completed.append(True)
            return value
        monkeypatch.setattr(audit,'open_private_artifact',decrypt_then_logout)
        response=client.post('/api/cases/audit-exports',headers=_headers(csrf),json=_case_body(world,
            export_id=initial.json()['export_id'],user_decrypt=True,decryption='user-decrypted'))
        assert completed==[True]
        assert response.status_code in {401,403,409,503},{'status':response.status_code}
        assert response.json().get('records') is None


@pytest.mark.parametrize('operational', [False, True])
def test_real_same_portal_logout_completes_while_export_crypto_is_pending(tmp_path, monkeypatch, operational):
    import asyncio
    import threading
    import httpx
    import applications.case_audit as audit
    world = _world(tmp_path)
    event = _record(world)
    path = '/api/admin/audit/export' if operational else '/api/cases/audit-exports'
    credential = ADMIN_CREDENTIAL if operational else OWNER_CREDENTIAL
    material = _ops_body(world) if operational else _case_body(world, artifact_ids=[event.event_id])
    entered, release = threading.Event(), threading.Event()
    actual = audit.open_private_artifact
    def decrypt_and_wait(*args, **kwargs):
        result = actual(*args, **kwargs)
        if kwargs['binding'].artifact_kind == 'case-audit-export':
            entered.set()
            assert release.wait(5), 'actual export did not permit bounded concurrent logout'
        return result
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=world.app),
                                     base_url='https://testserver') as client:
            login = await client.post('/api/complaint-workspace/auth/login', json={'credential': credential})
            assert login.status_code == 200
            csrf = login.json()['csrf_token']
            sealed = await client.post(path, json=material, headers=_headers(csrf))
            assert sealed.status_code == 200
            monkeypatch.setattr(audit, 'open_private_artifact', decrypt_and_wait)
            pending = asyncio.create_task(client.post(path, headers=_headers(csrf), json={**material,
                'export_id': sealed.json()['export_id'], 'user_decrypt': True, 'decryption': 'user-decrypted'}))
            try:
                assert await asyncio.to_thread(entered.wait, 3), 'actual export crypto did not run'
                logout = await asyncio.wait_for(client.post('/api/complaint-workspace/auth/logout',
                                                           headers=_headers(csrf), json={}), 2)
                assert logout.status_code == 200
            finally:
                release.set()
            result = await asyncio.wait_for(pending, 5)
            assert result.status_code in {401, 403, 409, 503}
            assert result.json().get('records') is None
    asyncio.run(scenario())


def test_new_export_refuses_after_logout_during_actual_ciphertext_staging(tmp_path, monkeypatch):
    import applications.case_audit as audit
    world = _world(tmp_path)
    event = _record(world)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _login(client, OWNER_CREDENTIAL)
        token = client.cookies.get(SESSION_COOKIE)
        actual = audit.os.fsync
        completed = []
        def sync_then_logout(fd):
            result = actual(fd)
            if '/audit/exports/.export-' in os.readlink('/proc/self/fd/' + str(fd)):
                world.app.state.browser_sessions.logout(token, csrf_token=csrf)
                completed.append(True)
            return result
        monkeypatch.setattr(audit.os, 'fsync', sync_then_logout)
        result = client.post('/api/cases/audit-exports', headers=_headers(csrf),
                             json=_case_body(world, artifact_ids=[event.event_id]))
        assert completed == [True]
        assert result.status_code in {401, 403, 409, 503}
        assert result.json().get('records') is None
        assert list((tmp_path / 'audit' / 'exports').iterdir()) == []


def test_operational_reopen_rechecks_actual_audit_right_after_crypto(tmp_path, monkeypatch):
    import applications.case_audit as audit
    world = _world(tmp_path)
    second = world.principals.install_server_role(role='operational_admin')
    directory = OperationalAdminService(principals=world.principals,
        sessions=world.app.state.browser_sessions, audit_principal_ids=(world.admin.principal_id, second.principal_id),
        cases=world.cases, case_audit=world.audit, clock=lambda: 1_700_000_000)
    body = _ops_body(world)
    sealed = directory.export_audit(world.admin.principal_id, world.admin.roles, body)
    actual = audit.open_private_artifact
    completed = []
    def decrypt_then_remove_right(*args, **kwargs):
        result = actual(*args, **kwargs)
        if kwargs['binding'].artifact_kind == 'case-audit-export':
            directory.set_audit_right(second.principal_id, second.roles, world.admin.principal_id,
                                      {'enabled': False, 'expected_revision': world.admin.revision})
            completed.append(True)
        return result
    monkeypatch.setattr(audit, 'open_private_artifact', decrypt_then_remove_right)
    from applications.admin_api import OperationalAdminError
    with pytest.raises(OperationalAdminError, match='audit_right_required'):
        directory.export_audit(world.admin.principal_id, world.admin.roles, {**body,
            'export_id': sealed['export_id'], 'user_decrypt': True, 'decryption': 'user-decrypted'})
    assert completed == [True]
