"""Authorized case creation and selection through the composed HTTP catalog.

Synthetic principals only. Newly created cases stay owner-only; a lawyer grant
from the action authorizer does not open sealed revisions without a key grant.
"""
from __future__ import annotations

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
from applications.case_access import ASSIGNED_LAWYER_ACTIONS, CaseActionAuthorizer
from applications.case_api import CATALOG_LIMITATIONS, CaseCatalog
from applications.case_directory import MEMBERSHIP_OWNER_ONLY, CaseDirectory
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
OWNER_CREDENTIAL = "synthetic-password"
STRANGER_CREDENTIAL = "synthetic-access-token"
LAWYER_CREDENTIAL = "synthetic-auth-token"


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=60,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
                        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, stranger=stranger, lawyer=lawyer, cases=cases,
                           authorizer=authorizer, catalog=catalog, app=app)


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def test_owner_creates_lists_and_reads_only_owner_cases(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        anonymous = client.get("/api/cases")
        assert anonymous.status_code == 401
        token = _login(client, OWNER_CREDENTIAL)
        rejected = client.post("/api/cases", headers=_csrf(token), json={"collaborators": [world.lawyer.principal_id]})
        assert rejected.status_code == 403
        assert rejected.json()["error"] == "collaboration_not_available"
        assert world.cases.list_cases(actor_principal_id=world.owner.principal_id) == ()
        minted = client.post("/api/cases", headers=_csrf(token), json={"label": "synthetic-one", "user_id": world.owner.principal_id, "case_id": world.owner.principal_id})
        assert minted.status_code == 201
        body = minted.json()
        assert body["membership"] == MEMBERSHIP_OWNER_ONLY
        assert body["case_id"] != world.owner.principal_id
        assert body["tenant_id"] != world.owner.principal_id
        assert body["actor_is_encrypted_owner"] is False
        assert body["canonical_owner_principal_id"] == body["tenant_id"]
        assert body["unresolved_gaps"] == []
        assert body["directory_revision"] == 1
        assert "key_grants_are_not_issued_here" in body["limitations"]
        listed = client.get("/api/cases")
        assert listed.status_code == 200
        assert [item["case_id"] for item in listed.json()["cases"]] == [body["case_id"]]
        read = client.get(f"/api/cases/{body['case_id']}")
        assert read.status_code == 200
        assert read.json()["envelope_sha256"] == body["envelope_sha256"]
        assert read.json()["label"] == "synthetic-one"


def test_unknown_and_foreign_identifiers_do_not_enumerate_other_users(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "owned"})
        assert created.status_code == 201
        case = created.json()
    with TestClient(world.app, base_url="https://testserver") as client:
        token = _login(client, STRANGER_CREDENTIAL)
        own = client.post("/api/cases", headers=_csrf(token), json={"label": "other"})
        assert own.status_code == 201
        listed = client.get("/api/cases")
        assert listed.status_code == 200
        assert case["case_id"] not in listed.text
        assert world.owner.principal_id not in listed.text
        assert case["tenant_id"] not in listed.text
        unknown = client.get("/api/cases/does-not-exist")
        foreign = client.get(f"/api/cases/{case['case_id']}")
        assert unknown.status_code == foreign.status_code == 404
        assert unknown.json() == foreign.json() == {"error": "missing_case"}
        assert world.owner.principal_id not in foreign.text
        assert case["tenant_id"] not in foreign.text
        probed = client.get(f"/api/cases/{case['case_id']}", params={
            "tenant_id": case["tenant_id"], "resource_id": case["resource_id"], "expected_revision": case["directory_revision"],
        })
        invented = client.get("/api/cases/does-not-exist", params={
            "tenant_id": "not-a-tenant", "resource_id": "not-a-resource", "expected_revision": 1,
        })
        assert probed.status_code == invented.status_code
        assert probed.json() == invented.json()
        assert world.owner.principal_id not in probed.text
        swapped = client.get("/api/cases", params={"user_id": world.owner.principal_id})
        assert swapped.status_code == 403
        assert case["case_id"] not in swapped.text
        selected = client.post(f"/api/cases/{case['case_id']}/select", headers=_csrf(token), json={})
        assert selected.status_code == 404
        assert selected.json() == {"error": "missing_case"}


def test_switching_cases_clears_transient_state_and_keeps_independent_revisions(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        token = _login(client, OWNER_CREDENTIAL)
        first = client.post("/api/cases", headers=_csrf(token), json={"label": "alpha"}).json()
        second = client.post("/api/cases", headers=_csrf(token), json={"label": "beta"}).json()
        assert first["tenant_id"] == second["tenant_id"]
        assert first["case_id"] != second["case_id"]
        assert first["envelope_sha256"] != second["envelope_sha256"]
        selected = client.post(f"/api/cases/{first['case_id']}/select", headers=_csrf(token), json={})
        assert selected.status_code == 200
        assert selected.json()["transient_cleared"] is True
        draft = client.post(f"/api/cases/{first['case_id']}/transient", headers=_csrf(token), json={"draft": "unsaved-note"})
        assert draft.status_code == 200
        assert draft.json()["transient"]["draft"] == "unsaved-note"
        gaps = client.post(f"/api/cases/{first['case_id']}/gaps", headers=_csrf(token), json={
            "unresolved_gaps": ["gap-alpha"], "expected_content_revision": 1,
        })
        assert gaps.status_code == 200
        alpha_sha = gaps.json()["envelope_sha256"]
        alpha_bytes = world.catalog.sealed_envelope(world.owner.principal_id, first["case_id"])
        stale = client.post(f"/api/cases/{first['case_id']}/gaps", headers=_csrf(token), json={
            "unresolved_gaps": ["replaced"], "expected_content_revision": 1,
        })
        assert stale.status_code == 409
        assert world.catalog.sealed_envelope(world.owner.principal_id, first["case_id"]) == alpha_bytes
        switched = client.post(f"/api/cases/{second['case_id']}/select", headers=_csrf(token), json={})
        assert switched.status_code == 200
        assert switched.json()["transient_cleared"] is True
        assert switched.json()["transient"]["draft"] == ""
        assert switched.json()["unresolved_gaps"] == []
        assert switched.json()["directory_revision"] == 1
        beta_gaps = client.post(f"/api/cases/{second['case_id']}/gaps", headers=_csrf(token), json={
            "unresolved_gaps": ["gap-beta"], "expected_content_revision": 1,
        })
        assert beta_gaps.status_code == 200
        assert world.catalog.sealed_envelope(world.owner.principal_id, first["case_id"]) == alpha_bytes
        again = client.get(f"/api/cases/{first['case_id']}")
        assert again.json()["unresolved_gaps"] == ["gap-alpha"]
        assert again.json()["envelope_sha256"] == alpha_sha
        assert again.json()["encrypted_content_revision"] == 2
        beta = client.get(f"/api/cases/{second['case_id']}")
        assert beta.json()["unresolved_gaps"] == ["gap-beta"]
        assert beta.json()["envelope_sha256"] != alpha_sha
        session = client.get("/api/cases/session")
        assert session.json()["selected_case_id"] == second["case_id"]
        assert session.json()["transient"]["draft"] == ""
        assert {item["case_id"] for item in session.json()["cases"]} == {first["case_id"], second["case_id"]}


def test_explicit_membership_does_not_bypass_missing_key_grants(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={}).json()
        owner_client.post(f"/api/cases/{created['case_id']}/select", headers=_csrf(owner_token), json={})
        owner_client.post(f"/api/cases/{created['case_id']}/gaps", headers=_csrf(owner_token), json={
            "unresolved_gaps": ["sealed-gap"], "expected_content_revision": 1,
        })
    grant = world.authorizer.grant_assigned_lawyer(
        owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id,
        case_id=created["case_id"],
        resource_id=created["resource_id"],
        tenant_id=created["tenant_id"],
        actions=set(ASSIGNED_LAWYER_ACTIONS),
        expected_case_revision=created["directory_revision"],
    )
    with TestClient(world.app, base_url="https://testserver") as client:
        token = _login(client, LAWYER_CREDENTIAL)
        listed = client.get("/api/cases")
        assert listed.status_code == 200
        assert listed.json()["cases"] == []
        assert "sealed-gap" not in listed.text
        denied = client.get(f"/api/cases/{created['case_id']}")
        unknown = client.get("/api/cases/unknown-case")
        assert denied.status_code == unknown.status_code
        assert denied.json() == unknown.json()
        opened = client.get(f"/api/cases/{created['case_id']}", params={
            "tenant_id": created["tenant_id"],
            "resource_id": created["resource_id"],
            "expected_revision": created["directory_revision"],
            "expected_membership_revision": grant.revision,
        })
        assert opened.status_code == 200
        body = opened.json()
        assert body["membership"] == "assigned-lawyer"
        assert body["plaintext_available"] is False
        assert body["key_grant"] == "required"
        assert "unresolved_gaps" not in body
        assert "sealed-gap" not in opened.text
        assert "envelope_sha256" not in body
        written = client.post(f"/api/cases/{created['case_id']}/gaps", headers=_csrf(token), json={
            "unresolved_gaps": ["lawyer-gap"], "expected_content_revision": 2,
            "tenant_id": created["tenant_id"], "resource_id": created["resource_id"],
            "expected_revision": created["directory_revision"],
            "expected_membership_revision": grant.revision,
        })
        assert written.status_code == 404
        assert written.json()["error"] == "missing_case"
    owner_view = world.catalog.read(world.owner.principal_id, created["case_id"])
    assert owner_view["unresolved_gaps"] == ["sealed-gap"]
    with pytest.raises(Exception):
        world.catalog.sealed_envelope(world.lawyer.principal_id, created["case_id"])


def test_cases_page_clears_transient_ui_and_states_owner_only_limits(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        response = client.get("/cases")
    assert response.status_code == 200
    page = response.text
    assert "clearTransientState" in page
    assert "owner-only" in page
    assert "key grants" in page
    assert "other participants" in page
    assert "invite" not in page
    assert "WebSocket" not in page
    assert world.owner.principal_id not in page
    assert set(CATALOG_LIMITATIONS)


def _persistent_catalog(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    other = principals.register_from_request({})
    key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=key, key_id="case-key")
    authorizer = CaseActionAuthorizer(principals, cases)
    return SimpleNamespace(principals=principals, owner=owner.principal_id, other=other.principal_id,
                           key=key, cases=cases, authorizer=authorizer,
                           catalog=CaseCatalog(cases, authorizer, key=key, key_id="case-key"))


def test_catalog_reopens_encrypted_revisions_and_rejects_wrong_key_cross_case(tmp_path):
    from applications.case_access import CaseAccessError
    world = _persistent_catalog(tmp_path)
    first = world.catalog.create(world.owner, {"label": "private-case-label"})
    second = world.catalog.create(world.owner, {})
    world.catalog.set_gaps(world.owner, first["case_id"], {"expected_content_revision": 1,
                           "unresolved_gaps": ["private-persisted-gap"]})
    before = world.catalog.sealed_envelope(world.owner, first["case_id"])
    reopened_cases = CaseDirectory(tmp_path / "cases", key=world.key, key_id="case-key")
    reopened = CaseCatalog(reopened_cases, CaseActionAuthorizer(world.principals, reopened_cases),
                           key=world.key, key_id="case-key")
    view = reopened.read(world.owner, first["case_id"])
    assert view["unresolved_gaps"] == ["private-persisted-gap"]
    assert view["encrypted_content_revision"] == 2
    assert reopened.sealed_envelope(world.owner, first["case_id"]) == before
    assert reopened.read(world.owner, second["case_id"])["unresolved_gaps"] == []
    for path in (tmp_path / "cases").rglob("*"):
        if path.is_file():
            assert b"private-persisted-gap" not in path.read_bytes()
            assert b"private-case-label" not in path.read_bytes()
    wrong = CaseCatalog(reopened_cases, world.authorizer, key=os.urandom(32), key_id="case-key")
    with pytest.raises(CaseAccessError, match="missing_key"):
        wrong.read(world.owner, first["case_id"])
    assert reopened.sealed_envelope(world.owner, first["case_id"]) == before
    with pytest.raises(CaseAccessError, match="missing_case"):
        reopened.read(world.other, first["case_id"])
    one = reopened_cases.owned_revision_directory(actor_principal_id=world.owner, case_id=first["case_id"]) / "revision.json"
    two = reopened_cases.owned_revision_directory(actor_principal_id=world.owner, case_id=second["case_id"]) / "revision.json"
    original = two.read_bytes()
    try:
        two.write_bytes(one.read_bytes())
        with pytest.raises(CaseAccessError, match="missing_key"):
            reopened.read(world.owner, second["case_id"])
    finally:
        two.write_bytes(original)
    assert reopened.read(world.owner, second["case_id"])["unresolved_gaps"] == []


def test_distinct_catalog_instances_serialize_creation_and_compare_and_swap(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from applications.case_access import CaseAccessError
    world = _persistent_catalog(tmp_path)
    other_cases = CaseDirectory(tmp_path / "cases", key=world.key, key_id="case-key")
    other = CaseCatalog(other_cases, CaseActionAuthorizer(world.principals, other_cases),
                        key=world.key, key_id="case-key")
    barrier = threading.Barrier(2)
    def create(catalog):
        barrier.wait(timeout=5)
        return catalog.create(world.owner, {})
    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = list(pool.map(create, [world.catalog, other]))
    assert {v["case_id"] for v in other.list_cases(world.owner)["cases"]} == {one["case_id"], two["case_id"]}
    barrier = threading.Barrier(2)
    def update(item):
        catalog, gap = item
        barrier.wait(timeout=5)
        try:
            catalog.set_gaps(world.owner, one["case_id"], {"expected_content_revision": 1, "unresolved_gaps": [gap]})
            return "written"
        except CaseAccessError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(update, [(world.catalog, "one"), (other, "two")]))
    assert sorted(outcomes) == ["encrypted_revision_conflict", "written"]
    view = other.read(world.owner, one["case_id"])
    assert view["encrypted_content_revision"] == 2
    assert view["unresolved_gaps"] in (["one"], ["two"])


@pytest.mark.parametrize("alias", ["symlink", "hardlink", "public"])
def test_revision_store_rejects_aliases_and_public_ciphertext(tmp_path, alias):
    from applications.case_access import CaseAccessError
    world = _persistent_catalog(tmp_path)
    case = world.catalog.create(world.owner, {})
    directory = world.cases.owned_revision_directory(actor_principal_id=world.owner, case_id=case["case_id"])
    path = directory / "revision.json"
    if alias == "public":
        path.chmod(0o644)
    else:
        original = directory / "original.json"
        path.rename(original)
        if alias == "symlink":
            path.symlink_to(original)
        else:
            os.link(original, path)
    with pytest.raises(CaseAccessError, match="case_revision_unavailable"):
        world.catalog.read(world.owner, case["case_id"])


def test_real_cases_dom_login_create_switch_save_and_late_response(tmp_path):
    import asyncio
    import json
    from tests import gui_native_browser as browser

    assert browser.probe_inherited_network_denial()["af_unix_only"], "trusted executor fence is required"
    world = _world(tmp_path)
    from applications.server import SERVER
    world.app = SERVER(None, authorizer=world.authorizer,
                       browser_sessions=world.app.state.browser_sessions,
                       case_catalog=world.catalog).app
    delayed = {"case_id": None}
    async def application(scope, receive, send):
        if (scope.get("method") == "POST" and delayed["case_id"]
                and scope.get("path") == "/api/cases/" + delayed["case_id"] + "/gaps"):
            await asyncio.sleep(0.25)
        await world.app(scope, receive, send)

    bridge = browser.SameOriginAsgiBridge(application)
    node, chromium = browser.pin_executables()
    profile = tmp_path / "actual-case-browser"
    profile.mkdir(mode=0o700)
    prior_node = os.environ.get("PLAYWRIGHT_NODEJS_PATH")
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = node.path
    playwright, context = None, None
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        browser._assert_process_custody(node, chromium, profile)
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(10000)
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        page.fill("#case-credential", OWNER_CREDENTIAL)
        page.click("#case-login button")
        page.wait_for_function("document.querySelector('#case-auth-status').textContent === 'Signed in'")
        assert page.input_value("#case-credential") == ""
        for label in ("alpha-dom", "beta-dom"):
            page.fill("#case-label", label)
            page.click("#create-case button")
            page.wait_for_function("label => Array.from(document.querySelectorAll('#case-list button')).some(n => n.textContent === label)", arg=label)
        page.get_by_role("button", name="alpha-dom", exact=True).click()
        page.wait_for_function("document.querySelector('#selected-case-label').textContent === 'alpha-dom'")
        page.fill("#case-draft", "unsaved-alpha-draft")
        page.fill("#gap-input", "unsaved-alpha-gap")
        page.get_by_role("button", name="beta-dom", exact=True).click()
        page.wait_for_function("document.querySelector('#selected-case-label').textContent === 'beta-dom'")
        assert page.input_value("#case-draft") == page.input_value("#gap-input") == ""
        page.fill("#gap-input", "saved-beta-gap")
        page.click("#save-gaps")
        page.wait_for_function("document.querySelector('#unresolved-gaps').textContent.includes('saved-beta-gap')")
        assert page.text_content("#encrypted-revision") == "2"
        page.get_by_role("button", name="alpha-dom", exact=True).click()
        page.wait_for_function("document.querySelector('#selected-case-label').textContent === 'alpha-dom'")
        first = next(x for x in world.catalog.list_cases(world.owner.principal_id)["cases"] if x["label"] == "alpha-dom")
        delayed["case_id"] = first["case_id"]
        page.fill("#gap-input", "late-alpha-gap")
        # The sync bridge may serialize ASGI calls. This proves a client
        # delivery/selection race, not concurrent transport: both real DOM
        # clicks happen before the first real response is consumed.
        page.evaluate("""() => { window.caseResponsePaints = [];
            window.casePaintObserver = new MutationObserver(() => {
                window.caseResponsePaints.push(document.querySelector('#selected-case-label').textContent);
            });
            window.casePaintObserver.observe(document.querySelector('#selected-case-label'), {childList: true, subtree: true});
            document.querySelector('#save-gaps').click();
            Array.from(document.querySelectorAll('#case-list button')).find(n => n.textContent === 'beta-dom').click(); }""")
        page.wait_for_function("document.querySelector('#selected-case-label').textContent === 'beta-dom' && !document.querySelector('#selected-case').hidden")
        assert "late-alpha-gap" not in page.text_content("#unresolved-gaps")
        assert page.text_content("#unresolved-gaps").strip() == "saved-beta-gap"
        paints = page.evaluate("() => { window.casePaintObserver.disconnect(); return window.caseResponsePaints; }")
        assert "beta-dom" in paints and all(label in {"", "beta-dom"} for label in paints), "an older response repainted the selected case"
        assert page.input_value("#gap-input") == ""
        assert world.catalog.read(world.owner.principal_id, first["case_id"])["unresolved_gaps"] == ["late-alpha-gap"]
        # A distinct principal signs in using the real form and public session
        # adapter. Hidden DOM is still DOM: no previous case content may remain.
        page.fill("#case-label", "unsent-owner-case-label")
        page.fill("#case-credential", STRANGER_CREDENTIAL)
        page.click("#case-login button")
        page.wait_for_function("document.querySelector('#case-auth-status').textContent === 'Signed in'")
        page.wait_for_function("""async actor => {
            const response = await fetch('/api/complaint-workspace/auth/session', {credentials: 'same-origin'});
            return response.ok && (await response.json()).principal_id === actor;
        }""", arg=world.stranger.principal_id)
        assert page.locator("#case-list button").count() == 0
        assert page.locator("#selected-case").is_hidden()
        for selector in ("#selected-case-label", "#unresolved-gaps", "#directory-revision", "#encrypted-revision", "#envelope-sha256"):
            assert page.text_content(selector) == ""
        for selector in ("#case-label", "#case-draft", "#gap-input", "#case-credential"):
            assert page.input_value(selector) == ""
        text = page.locator("body").text_content()
        assert all(marker not in text for marker in ("alpha-dom", "beta-dom", "saved-beta-gap", "late-alpha-gap", "unsent-owner-case-label"))
        page.fill("#case-label", "stranger-dom")
        page.click("#create-case button")
        page.wait_for_function("document.querySelector('#case-list').textContent.includes('stranger-dom')")
        assert page.locator("#case-list button").all_text_contents() == ["stranger-dom"]
        # A new document gets no CSRF from cookies or persistent browser storage.
        page.reload(wait_until="domcontentloaded")
        assert page.text_content("#case-auth-status") == "Sign in required"
        assert page.evaluate("Object.keys(localStorage).length + Object.keys(sessionStorage).length") == 0
        assert bridge.cookie_headers_seen and bridge.asgi_calls > 10
        assert not bridge.aborted_external
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        if prior_node is None:
            os.environ.pop("PLAYWRIGHT_NODEJS_PATH", None)
        else:
            os.environ["PLAYWRIGHT_NODEJS_PATH"] = prior_node
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned browser descendants must quiesce"
    (tmp_path / "case-dom-observation.json").write_text(json.dumps({
        "actual_dom": True, "actual_asgi": True, "login_csrf_from_public_route": True,
        "unsaved_gap_cleared": True, "late_response_did_not_repaint": True,
        "race_scope": "client_delivery_and_selection; ASGI calls may be serialized",
        "concurrent_asgi_transport_qualified": False,
        "distinct_principal_login_cleared_private_dom": True,
        "reauthentication_after_navigation_required": True, "owned_cleanup": cleanup,
        "completion_authority": False}, sort_keys=True))


@pytest.mark.parametrize("variant", ["server", "review_api", "dashboard", "review_surface"])
def test_actual_app_factories_forward_catalog_and_missing_configuration_is_unavailable(tmp_path, variant):
    from applications.server import SERVER
    from applications.review_api import create_review_api_app
    from applications.review_ui import create_review_dashboard_app, create_review_surface_app
    world = _world(tmp_path)
    common = {"authorizer": world.authorizer, "browser_sessions": world.app.state.browser_sessions}
    def build(catalog):
        options = dict(common, case_catalog=catalog)
        if variant == "server":
            return SERVER(None, **options).app
        if variant == "review_api":
            return create_review_api_app(None, **options)
        if variant == "dashboard":
            return create_review_dashboard_app(**options)
        return create_review_surface_app(None, **options)
    with TestClient(build(None), base_url="https://testserver") as client:
        _login(client, OWNER_CREDENTIAL)
        denied = client.get("/api/cases")
        assert denied.status_code == 503
        assert denied.json() == {"error": "case_catalog_unavailable"}
    with TestClient(build(world.catalog), base_url="https://testserver") as client:
        token = _login(client, OWNER_CREDENTIAL)
        assert client.get("/cases").status_code == 200
        created = client.post("/api/cases", headers=_csrf(token), json={"label": "factory-case"})
        assert created.status_code == 201
        assert created.json()["membership"] == "owner-only"
