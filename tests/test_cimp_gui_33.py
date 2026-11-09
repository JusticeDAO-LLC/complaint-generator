"""Case processing consent is explicit, persisted, and revocable.

Local private is the default. Grok egress exists only after the owner
authorizes one case and one purpose. Lawyer membership, an admin role,
development Grok authorization, and message receipt do not create that consent.
"""

from __future__ import annotations

import os
from pathlib import Path

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
from applications.case_consent_api import CaseConsentService
from applications.case_directory import CaseDirectory
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
ADMIN_CREDENTIAL = "synthetic-access-token"
ROOT = Path(__file__).resolve().parents[1]


def _world(tmp_path):
    now = {"t": 1_700_000_100}

    def clock():
        now["t"] += 1
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            ADMIN_CREDENTIAL: admin.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=120,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    consent = CaseConsentService(
        tmp_path / "consent", cases=cases, key=os.urandom(32), key_id="consent-key", clock=clock,
    )
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_consent=consent, include_workspace=False, include_review=False, include_document=False,
    )
    return app, owner, lawyer, admin, consent


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _create_case(client, token, label="owned"):
    created = client.post("/api/cases", headers=_csrf(token), json={"label": label})
    assert created.status_code == 201, created.text
    return created.json()


def _decision(payload, purpose):
    return next(item for item in payload["decisions"] if item["purpose"] == purpose)


def test_owner_persists_displays_and_revokes_purpose_consent(tmp_path):
    app, _owner, _lawyer, _admin, consent = _world(tmp_path)
    page = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    assert 'id="case-processing-consent"' in page
    assert "Local private: this purpose never calls a remote provider." in page
    assert "Explicitly authorized Grok processing: grok_cli / grok-4.7 for this case and purpose." in page
    assert "Revoked: Grok processing for this purpose is not authorized." in page
    assert "development Grok authorization" in page
    assert "/processing-consent" in page

    with TestClient(app, base_url="https://testserver") as client:
        token = _login(client, OWNER_CREDENTIAL)
        case = _create_case(client, token)
        other = _create_case(client, token, label="other")
        initial = client.get(f"/api/cases/{case['case_id']}/processing-consent")
        assert initial.status_code == 200, initial.text
        body = initial.json()
        assert body["egress_authorized"] is False
        assert body["implications"] == {
            "lawyer_membership": False,
            "admin_role": False,
            "development_grok_authorization": False,
            "message_receipt": False,
        }
        assert _decision(body, "extract_facts")["display"].startswith("Local private")
        assert _decision(body, "propose_questions")["egress_authorized"] is False

        refused = client.post(
            f"/api/cases/{case['case_id']}/processing-consent",
            headers=_csrf(token),
            json={"purpose": "extract_facts", "mode": "grok_cloud", "expected_generation": 0},
        )
        assert refused.status_code == 403
        assert refused.json()["error"] == "explicit_case_purpose_required"

        authorized = client.post(
            f"/api/cases/{case['case_id']}/processing-consent",
            headers=_csrf(token),
            json={
                "purpose": "extract_facts",
                "mode": "grok_cloud",
                "explicit_case_purpose": True,
                "expected_generation": 0,
            },
        )
        assert authorized.status_code == 200, authorized.text
        saved = authorized.json()
        assert saved["generation"] == 1
        assert saved["egress_authorized"] is True
        chosen = _decision(saved, "extract_facts")
        assert chosen["egress_authorized"] is True
        assert chosen["provider"] == "grok_cli"
        assert chosen["model"] == "grok-4.7"
        assert chosen["display"].startswith("Explicitly authorized Grok")
        assert _decision(saved, "propose_questions")["egress_authorized"] is False
        assert saved["operation_consent"]["grants"] == [{
            "purpose": "extract_facts",
            "provider_kind": "grok_inference",
            "provider": "grok_cli",
            "model": "grok-4.7",
            "data_class": "raw_intake",
            "explicit": True,
            "tools": False,
        }]

        reloaded = consent.read(saved["owner_principal_id"], case["case_id"])
        assert _decision(reloaded, "extract_facts")["egress_authorized"] is True
        isolated = client.get(f"/api/cases/{other['case_id']}/processing-consent")
        assert isolated.status_code == 200
        assert isolated.json()["egress_authorized"] is False

        stale = client.post(
            f"/api/cases/{case['case_id']}/processing-consent/revoke",
            headers=_csrf(token),
            json={"purpose": "extract_facts", "expected_generation": 0},
        )
        assert stale.status_code == 409
        assert stale.json()["error"] == "revision_conflict"

        revoked = client.post(
            f"/api/cases/{case['case_id']}/processing-consent/revoke",
            headers=_csrf(token),
            json={"purpose": "extract_facts", "expected_generation": 1},
        )
        assert revoked.status_code == 200, revoked.text
        after = revoked.json()
        assert after["generation"] == 2
        assert after["egress_authorized"] is False
        assert after["operation_consent"]["revoked"] is True
        shown = _decision(after, "extract_facts")
        assert shown["revoked"] is True
        assert shown["display"].startswith("Revoked")
        assert consent.read(after["owner_principal_id"], case["case_id"])["egress_authorized"] is False


def test_membership_admin_development_and_messages_do_not_imply_egress(tmp_path):
    app, owner, lawyer, admin, consent = _world(tmp_path)
    with TestClient(app, base_url="https://testserver") as owner_client, TestClient(app, base_url="https://testserver") as lawyer_client, TestClient(app, base_url="https://testserver") as admin_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        admin_token = _login(admin_client, ADMIN_CREDENTIAL)
        case = _create_case(owner_client, owner_token)
        path = f"/api/cases/{case['case_id']}/processing-consent"

        anonymous = TestClient(app, base_url="https://testserver")
        assert anonymous.get(path).status_code == 401

        for client, token in ((lawyer_client, lawyer_token), (admin_client, admin_token)):
            denied = client.get(path)
            assert denied.status_code == 404, denied.text
            assert denied.json()["error"] == "missing_case"
            posted = client.post(path, headers=_csrf(token), json={
                "purpose": "extract_facts",
                "mode": "grok_cloud",
                "explicit_case_purpose": True,
                "expected_generation": 0,
            })
            assert posted.status_code == 404
            assert posted.json()["error"] == "missing_case"

        for implied in (
            {"lawyer_membership": True},
            {"admin_role": True},
            {"development_grok_authorization": True},
            {"message_receipt": True},
        ):
            rejected = owner_client.post(path, headers=_csrf(owner_token), json={
                "purpose": "extract_facts",
                "mode": "grok_cloud",
                "explicit_case_purpose": True,
                "expected_generation": 0,
                **implied,
            })
            assert rejected.status_code == 403, rejected.text
            assert rejected.json()["error"] == "consent_not_implied"

        current = owner_client.get(path)
        assert current.status_code == 200
        assert current.json()["egress_authorized"] is False
        assert consent.read(owner.principal_id, case["case_id"])["egress_authorized"] is False
        assert lawyer.principal_id != owner.principal_id
        assert admin.principal_id != owner.principal_id


# Composed browser and authority regressions use the same actual case/workspace
# owners and qualified Chromium-to-ASGI pipe as Task15. No API response is canned.
from contextlib import contextmanager
import stat
import pytest
from applications.case_consent_api import CaseConsentError
from applications.principal_store import PrincipalStoreError
from tests import test_cimp_gui_15 as _gui33_browser_owner
from tests.test_cimp_gui_14 import _composed_case_world, _composed_login

_GUI33_TYPED_WORLD = _gui33_browser_owner._typed_world


def _consent_world(tmp_path):
    world = _composed_case_world(tmp_path)
    world.consent_key = os.urandom(32)
    world.consent_root = tmp_path / "processing-consent"
    world.consent = CaseConsentService(world.consent_root, cases=world.cases,
        key=world.consent_key, key_id="synthetic-consent-key", clock=lambda: 1_700_000_100)
    world.app.state.case_consent = world.consent
    return world


@contextmanager
def _consent_page(tmp_path, monkeypatch):
    def composed(path):
        world = _GUI33_TYPED_WORLD(path)
        world.consent_key = os.urandom(32)
        world.consent_root = path / "processing-consent"
        world.consent = CaseConsentService(world.consent_root, cases=world.actual.cases,
            key=world.consent_key, key_id="synthetic-consent-key", clock=lambda: 1_700_000_100)
        world.actual.app.state.case_consent = world.consent
        world.consent_calls = []
        application = world.application
        async def observed(scope, receive, send):
            status = None
            async def capture(message):
                nonlocal status
                if message.get("type") == "http.response.start":
                    status = message["status"]
                await send(message)
            await application(scope, receive, capture)
            if "/processing-consent" in scope.get("path", ""):
                world.consent_calls.append({"method": scope["method"], "path": scope["path"], "status": status,
                    "csrf_present": any(k.lower() == b"x-csrf-token" and bool(v) for k, v in scope.get("headers", []))})
        world.application = observed
        return world
    monkeypatch.setattr(_gui33_browser_owner, "_typed_world", composed)
    with _gui33_browser_owner._page(tmp_path, monkeypatch, "typed_owner") as pair:
        yield pair


def _consent_login(page, world):
    issued = page.evaluate("""async () => {
        const r = await fetch('/api/complaint-workspace/auth/login', {method:'POST', credentials:'same-origin',
            headers:{'content-type':'application/json'}, body:JSON.stringify({credential:'synthetic-owner-credential'})});
        if (!r.ok) throw new Error('actual_owner_login_' + r.status); return await r.json();
    }""")
    assert issued["principal_id"] == world.principal.principal_id != world.case.tenant_id
    page.evaluate("""data => {
        window.workspaceClient.setBrowserSession(data.issued);
        window.workspaceClient.setCaseContext(data.case);
    }""", {"issued": issued, "case": {"tenant_id": world.case.tenant_id, "case_id": world.case.case_id,
        "resource_id": world.case.resource_id, "revision": world.case.revision}})
    return issued


def _show_consent(page, world):
    page.fill("#consent-case-id", world.case.case_id)
    path = f"/api/cases/{world.case.case_id}/processing-consent"
    with page.expect_response(lambda r: r.url.endswith(path) and r.request.method == "GET") as seen:
        page.click("#consent-refresh")
    assert seen.value.status == 200
    page.wait_for_function("document.getElementById('consent-decision-display').dataset.verification === 'verified'")


def _grant_consent(page, world):
    _show_consent(page, world)
    path = f"/api/cases/{world.case.case_id}/processing-consent"
    with page.expect_response(lambda r: r.url.endswith(path) and r.request.method == "POST") as seen:
        page.click("#consent-authorize-grok")
    assert seen.value.status == 200
    page.wait_for_function("document.getElementById('consent-decision-display').dataset.egressAuthorized === 'true'")


def test_consent_http_reproves_canonical_principal_authority_before_ciphertext_access(tmp_path, monkeypatch):
    world = _consent_world(tmp_path)
    assert world.owner.principal_id != world.case.tenant_id
    calls = []
    original = world.authorizer.authorize
    def observed(**values):
        calls.append(values)
        return original(**values)
    monkeypatch.setattr(world.authorizer, "authorize", observed)
    path = f"/api/cases/{world.case.case_id}/processing-consent"
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        authorized = client.post(path, headers=_csrf(csrf), json={"purpose": "extract_facts", "mode": "grok_cloud",
            "explicit_case_purpose": True, "expected_generation": 0})
        assert authorized.status_code == 200, authorized.text
        assert calls[-1] == {"boundary": "http", "actor_principal_id": world.owner.principal_id,
            "tenant_id": world.case.tenant_id, "case_id": world.case.case_id, "resource_id": world.case.resource_id,
            "expected_revision": world.case.revision, "action": "case.processing.choose"}
        snapshot = {p.name: p.read_bytes() for p in world.consent_root.iterdir() if not p.name.startswith(".")}
        def unavailable(_principal):
            raise PrincipalStoreError("synthetic_principal_inventory_unavailable")
        with monkeypatch.context() as outage:
            outage.setattr(world.principals, "load", unavailable)
            assert client.get(path).status_code == 403
            denied = client.post(path + "/revoke", headers=_csrf(csrf), json={"purpose": "extract_facts", "expected_generation": 1})
            assert denied.status_code == 403
        assert {p.name: p.read_bytes() for p in world.consent_root.iterdir() if not p.name.startswith(".")} == snapshot
        assert world.consent.read(world.owner.principal_id, world.case.case_id)["egress_authorized"] is True
        world.app.state.case_authorizer = None
        assert client.get(path).status_code == 503


@pytest.mark.parametrize("claim", ["actor_principal_id", "user_id", "tenant_id", "case_id", "resource_id", "action"])
def test_consent_http_never_accepts_forged_actor_or_canonical_case_scope(tmp_path, claim):
    world = _consent_world(tmp_path)
    wrong = {"actor_principal_id": world.stranger.principal_id, "user_id": world.case.tenant_id,
        "tenant_id": world.foreign.tenant_id, "case_id": world.foreign.case_id,
        "resource_id": world.foreign.resource_id, "action": "case.read"}
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        path = f"/api/cases/{world.case.case_id}/processing-consent"
        denied = client.post(path, headers=_csrf(csrf), json={"purpose": "extract_facts", "mode": "grok_cloud",
            "explicit_case_purpose": True, "expected_generation": 0, claim: wrong[claim]})
        assert denied.status_code == 403, denied.text
        assert world.consent.read(world.owner.principal_id, world.case.case_id)["generation"] == 0
        assert client.post(f"/api/cases/{world.foreign.case_id}/processing-consent", headers=_csrf(csrf),
            json={"purpose": "extract_facts", "mode": "grok_cloud", "explicit_case_purpose": True,
                  "expected_generation": 0}).status_code == 404


def test_consent_ciphertext_cold_reopen_and_repeated_revoke_stay_private_under_umask_002(tmp_path):
    previous = os.umask(0o002)
    try:
        world = _consent_world(tmp_path)
        first = world.consent.choose(world.owner.principal_id, world.case.case_id,
            {"purpose": "extract_facts", "mode": "grok_cloud", "explicit_case_purpose": True, "expected_generation": 0})
        assert first["generation"] == 1
        reopened = CaseConsentService(world.consent_root, cases=world.cases, key=world.consent_key,
            key_id="synthetic-consent-key", clock=lambda: 1_700_000_101)
        assert reopened.read(world.owner.principal_id, world.case.case_id)["egress_authorized"] is True
        revoked = reopened.revoke(world.owner.principal_id, world.case.case_id,
            {"purpose": "extract_facts", "expected_generation": 1})
        again = reopened.revoke(world.owner.principal_id, world.case.case_id,
            {"purpose": "extract_facts", "expected_generation": 2})
        assert revoked["generation"] == 2 and again["generation"] == 3
        assert _decision(again, "extract_facts")["revoked"] is True
        assert again["egress_authorized"] is False
        assert stat.S_IMODE(world.consent_root.stat().st_mode) == 0o700
        blobs = [p for p in world.consent_root.iterdir() if not p.name.startswith(".")]
        assert len(blobs) == 1 and blobs[0].read_bytes().startswith(b"CGPE")
        assert stat.S_IMODE(blobs[0].stat().st_mode) == 0o600
        assert b"extract_facts" not in blobs[0].read_bytes() and b"grok_cloud" not in blobs[0].read_bytes()
        cold = CaseConsentService(world.consent_root, cases=world.cases, key=world.consent_key,
            key_id="synthetic-consent-key", clock=lambda: 1_700_000_102)
        assert _decision(cold.read(world.owner.principal_id, world.case.case_id), "extract_facts")["revoked"] is True
    finally:
        os.umask(previous)


@pytest.mark.parametrize("damage", ["unsafe_root", "root_alias", "lock_alias", "ciphertext_alias"])
def test_consent_store_refuses_unsafe_or_aliased_storage_without_chmod_or_foreign_writes(tmp_path, damage):
    world = _consent_world(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"synthetic-foreign-storage")
    if damage == "unsafe_root":
        world.consent_root.chmod(0o775)
        with pytest.raises(CaseConsentError):
            CaseConsentService(world.consent_root, cases=world.cases, key=world.consent_key,
                key_id="synthetic-consent-key", clock=lambda: 1)
        assert stat.S_IMODE(world.consent_root.stat().st_mode) == 0o775
    elif damage == "root_alias":
        alias = tmp_path / "root-alias"; alias.symlink_to(world.consent_root, target_is_directory=True)
        with pytest.raises(CaseConsentError):
            CaseConsentService(alias, cases=world.cases, key=world.consent_key, key_id="synthetic-consent-key", clock=lambda: 1)
    else:
        world.consent.choose(world.owner.principal_id, world.case.case_id,
            {"purpose": "extract_facts", "mode": "grok_cloud", "explicit_case_purpose": True, "expected_generation": 0})
        target = world.consent_root / ".lock" if damage == "lock_alias" else next(p for p in world.consent_root.iterdir() if not p.name.startswith("."))
        target.unlink(); target.symlink_to(outside)
        with pytest.raises(CaseConsentError):
            world.consent.read(world.owner.principal_id, world.case.case_id)
    assert outside.read_bytes() == b"synthetic-foreign-storage"


def test_real_consent_dom_uses_cookie_csrf_persists_reload_and_revokes_one_purpose(tmp_path, monkeypatch):
    with _consent_page(tmp_path, monkeypatch) as (world, page):
        _consent_login(page, world)
        _grant_consent(page, world)
        assert world.consent_calls[-1]["csrf_present"] is True
        assert world.consent.read(world.principal.principal_id, world.case.case_id)["egress_authorized"] is True
        # Typing changes the selected case before blur/change. Prior-case
        # authority must disappear immediately, without another HTTP response.
        page.fill("#consent-case-id", world.actual.second.case_id)
        assert page.locator("#consent-case-id").evaluate("node => node === document.activeElement")
        assert page.locator("#consent-decision-display").get_attribute("data-egress-authorized") == "unknown"
        assert "Explicitly authorized Grok" not in page.locator("#consent-decision-display").inner_text()
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
        _consent_login(page, world)
        _show_consent(page, world)
        assert page.locator("#consent-decision-display").get_attribute("data-egress-authorized") == "true"
        page.select_option("#consent-purpose", "propose_questions")
        assert page.locator("#consent-decision-display").get_attribute("data-egress-authorized") == "unknown"
        _show_consent(page, world)
        assert page.locator("#consent-decision-display").get_attribute("data-egress-authorized") == "false"
        page.select_option("#consent-purpose", "extract_facts")
        _show_consent(page, world)
        path = f"/api/cases/{world.case.case_id}/processing-consent/revoke"
        with page.expect_response(lambda r: r.url.endswith(path) and r.request.method == "POST") as seen:
            page.click("#consent-revoke")
        assert seen.value.status == 200
        page.wait_for_function("document.getElementById('consent-decision-display').textContent.startsWith('Revoked:')")
        persisted = world.consent.read(world.principal.principal_id, world.case.case_id)
        assert persisted["generation"] == 2 and persisted["egress_authorized"] is False


def test_real_consent_dom_failure_never_claims_local_or_confirmed_revocation(tmp_path, monkeypatch):
    with _consent_page(tmp_path, monkeypatch) as (world, page):
        _consent_login(page, world); _grant_consent(page, world)
        def unavailable(_principal):
            raise PrincipalStoreError("synthetic_principal_inventory_unavailable")
        with monkeypatch.context() as outage:
            outage.setattr(world.actual.principals, "load", unavailable)
            path = f"/api/cases/{world.case.case_id}/processing-consent/revoke"
            with page.expect_response(lambda r: r.url.endswith(path) and r.request.method == "POST") as seen:
                page.click("#consent-revoke")
            assert seen.value.status == 403
            page.wait_for_function("document.getElementById('consent-decision-display').dataset.verification === 'unavailable'")
            text = page.locator("#consent-decision-display").inner_text()
            assert "Revocation has not been confirmed" in text and "Last verified: Explicitly authorized Grok" in text
            assert page.locator("#consent-decision-display").get_attribute("data-egress-authorized") == "true"
            assert world.consent.read(world.principal.principal_id, world.case.case_id)["egress_authorized"] is True
        world.actual.app.state.case_consent = None
        with page.expect_response(lambda r: "/processing-consent" in r.url and r.request.method == "GET") as seen:
            page.click("#consent-refresh")
        assert seen.value.status == 503
        page.wait_for_function("document.getElementById('consent-decision-display').dataset.verification === 'unavailable'")
        assert "Last verified: Explicitly authorized Grok" in page.locator("#consent-decision-display").inner_text()
        page.select_option("#consent-purpose", "propose_questions")
        page.click("#consent-refresh")
        page.wait_for_function("document.getElementById('consent-decision-display').dataset.verification === 'unavailable'")
        assert page.locator("#consent-decision-display").get_attribute("data-egress-authorized") == "unknown"
        assert "No decision has been verified" in page.locator("#consent-decision-display").inner_text()


def test_real_consent_dom_discards_late_actual_response_at_existing_privacy_boundary(tmp_path, monkeypatch):
    with _consent_page(tmp_path, monkeypatch) as (world, page):
        _consent_login(page, world); _grant_consent(page, world)
        page.evaluate("""() => {
            const c=window.workspaceClient, actual=c.fetchImpl;
            c.fetchImpl=(url,options) => actual(url,options).then(response => {
                if (String(url).includes('/processing-consent') && (!options.method || options.method==='GET')) {
                    return new Promise(resolve => { window.releaseActualConsent=()=>resolve(response); });
                }
                return response;
            });
            window.pendingActualConsent=refreshCaseProcessingConsent();
        }""")
        page.wait_for_function("typeof window.releaseActualConsent === 'function'")
        page.click("#workspace-clear-private-state")
        page.evaluate("async()=>{window.releaseActualConsent();await window.pendingActualConsent;delete window.releaseActualConsent;}")
        assert page.input_value("#consent-case-id") == ""
        assert page.locator("#consent-decision-display").get_attribute("data-egress-authorized") == "unknown"
        assert not page.locator("#consent-decision-display").get_attribute("data-generation")
        assert "Explicitly authorized Grok" not in page.locator("#consent-decision-display").inner_text()
        assert world.consent.read(world.principal.principal_id, world.case.case_id)["egress_authorized"] is True


@pytest.mark.parametrize("boundary", ["clear", "switch", "logout"])
def test_real_consent_dom_participates_in_existing_clear_switch_and_logout(tmp_path, monkeypatch, boundary):
    with _consent_page(tmp_path, monkeypatch) as (world, page):
        _consent_login(page, world); _grant_consent(page, world)
        if boundary == "switch":
            page.fill("#workspace-switch-user-id", "synthetic-next-user")
            page.click("#workspace-switch-user")
        elif boundary == "logout":
            page.click("#workspace-logout")
        else:
            page.click("#workspace-clear-private-state")
        page.wait_for_function("document.getElementById('consent-case-id').value === ''")
        assert page.locator("#consent-decision-display").get_attribute("data-egress-authorized") == "unknown"
        assert not page.locator("#consent-decision-display").get_attribute("data-generation")
        assert "Explicitly authorized Grok" not in page.locator("#consent-decision-display").inner_text()


def test_consent_cookie_expiry_at_actual_ciphertext_admission_cannot_persist_a_grant(tmp_path, monkeypatch):
    from applications import case_consent_api as owner
    world = _consent_world(tmp_path)
    real_seal = owner.seal_private_artifact
    def expires_after_real_encryption(*args, **kwargs):
        envelope = real_seal(*args, **kwargs)
        world.clock["now"] += 400
        return envelope
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        monkeypatch.setattr(owner, "seal_private_artifact", expires_after_real_encryption)
        denied = client.post(f"/api/cases/{world.case.case_id}/processing-consent", headers=_csrf(csrf),
            json={"purpose": "extract_facts", "mode": "grok_cloud", "explicit_case_purpose": True,
                  "expected_generation": 0})
        assert denied.status_code == 401, denied.text
        stored = world.consent.read(world.owner.principal_id, world.case.case_id)
        assert stored["generation"] == 0 and stored["egress_authorized"] is False
        assert not [p for p in world.consent_root.iterdir() if p.name != ".lock"]
