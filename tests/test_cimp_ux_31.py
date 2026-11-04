"""Versioned draft edits commit through the encrypted case owner.

Saving, saved, and conflict stay visible. A stale, locked, or revoked save
cannot replace the encrypted head or another actor's revision. Browser storage
is not the draft.
"""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import BrowserSessionConfiguration, BrowserSessionService, PrincipalStoreCredentialAdapter
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from integrations.private_storage import UserOwnedKeySession
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "synthetic-draft-passphrase"


def _domains():
    return {
        "factual": {
            "status": "current",
            "revision": 1,
            "complete": True,
            "assertions": [{"id": "fact-wages", "text": "The employer did not pay wages.", "bound": True, "revision": 1}],
        },
        "legal": {
            "status": "admitted",
            "revision": 2,
            "factual_revision": 1,
            "authority_id": "auth-synthetic",
            "governing_law": True,
        },
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
            "complete": True,
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
        intake_case_file={"workflow_domains": _domains()},
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
    return SimpleNamespace(
        case=case, app=app, mediator=mediator, cases=cases, owner=owner, lawyer=lawyer,
        authorizer=authorizer, grant=grant, keys=keys,
    )


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


def _editor_path(case_id):
    return f"/api/documents/{case_id}/draft-editor"


def _head_file(world):
    directory = world.cases.owned_revision_directory(actor_principal_id=world.owner.principal_id, case_id=world.case.case_id)
    return directory / "draft-editor.json"


def _save(client, world, csrf, text, expected, request_id):
    return client.post(_editor_path(world.case.case_id), headers=_headers(world.case, csrf), json={
        "request_id": request_id,
        "draft_id": "draft-wages",
        "text": text,
        "expected_head_revision": expected,
    })


def test_owner_save_is_durable_and_revisions_differ(tmp_path):
    world = _world(tmp_path)
    client = _client(world.app)
    csrf = _login(client, "synthetic-owner-credential")
    empty = client.get(_editor_path(world.case.case_id), headers=_headers(world.case, csrf))
    assert empty.status_code == 200, empty.text
    assert empty.json()["head_revision"] == 0
    assert empty.json()["durable"] is False
    assert empty.json()["browser_storage"] is False
    first = _save(client, world, csrf, "The employer did not pay wages that were due.", 0, "save-1")
    assert first.status_code == 200, first.text
    saved = first.json()
    assert saved["save_state"] == "saved"
    assert saved["head_revision"] == 1
    assert saved["current_text"] == "The employer did not pay wages that were due."
    assert saved["revisions"][0]["actor_principal_id"] == world.owner.principal_id
    sealed = _head_file(world).read_bytes()
    assert b"The employer did not pay wages" not in sealed
    replay = _save(client, world, csrf, "The employer did not pay wages that were due.", 1, "save-1")
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["head_revision"] == 1
    assert len(replay.json()["revisions"]) == 1
    second = _save(client, world, csrf, "The employer did not pay wages that were due.\nOvertime was also withheld.", 1, "save-2")
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["head_revision"] == 2
    assert [item["revision"] for item in body["revisions"]] == [1, 2]
    ops = [item["op"] for item in body["difference"]["changes"]]
    assert "equal" in ops and "insert" in ops
    assert any(item["text"] == "Overtime was also withheld." and item["op"] == "insert" for item in body["difference"]["changes"])
    cold = _client(world.app)
    cold_csrf = _login(cold, "synthetic-owner-credential")
    world.mediator.intake_case_file["draft_workflow"] = {"versions": []}
    read = cold.get(_editor_path(world.case.case_id) + "?base_revision=1&compare_revision=2", headers=_headers(world.case, cold_csrf))
    assert read.status_code == 200, read.text
    restored = read.json()
    assert restored["current_text"].endswith("Overtime was also withheld.")
    assert restored["head_revision"] == 2
    assert any(item["op"] == "insert" and "Overtime" in item["text"] for item in restored["difference"]["changes"])
    assert world.mediator.intake_case_file["draft_workflow"]["versions"][-1]["text"].endswith("Overtime was also withheld.")


def test_stale_locked_revoked_and_other_actor_cannot_overwrite(tmp_path):
    world = _world(tmp_path)
    owner = _client(world.app)
    csrf = _login(owner, "synthetic-owner-credential")
    created = _save(owner, world, csrf, "Stored head that must survive.", 0, "save-head")
    assert created.status_code == 200, created.text
    sealed = _head_file(world).read_bytes()
    stale = _save(owner, world, csrf, "A stale editor tried to replace the head.", 0, "save-stale")
    assert stale.status_code == 409
    assert stale.json()["save_state"] == "conflict"
    assert stale.json()["code"] == "stale_revision"
    assert stale.json()["overwrote_head"] is False
    assert stale.json()["current_text"] == "Stored head that must survive."
    assert _head_file(world).read_bytes() == sealed
    world.keys.lock()
    locked = _save(owner, world, csrf, "A locked key tried to replace the head.", 1, "save-locked")
    assert locked.status_code == 409
    assert locked.json()["detail"] == "key_locked"
    assert _head_file(world).read_bytes() == sealed
    world.keys.unlock_passphrase(PASSPHRASE)
    world.keys.destroy_case_keys(world.case.tenant_id, world.case.case_id)
    revoked = _save(owner, world, csrf, "A revoked key tried to replace the head.", 1, "save-revoked")
    assert revoked.status_code == 403
    assert revoked.json()["detail"] == "key_revoked"
    assert _head_file(world).read_bytes() == sealed
    lawyer = _client(world.app)
    lawyer_csrf = _login(lawyer, "synthetic-lawyer-credential")
    denied = lawyer.post(_editor_path(world.case.case_id), headers=_headers(world.case, lawyer_csrf, world.grant.revision), json={
        "request_id": "lawyer-save",
        "draft_id": "draft-wages",
        "text": "Another actor tried to replace the head.",
        "expected_head_revision": 1,
    })
    assert denied.status_code == 403
    assert "Stored head" not in denied.text
    assert _head_file(world).read_bytes() == sealed
    removed = dataclasses.replace(world.grant, status="removed")
    world.authorizer._grants[(world.lawyer.principal_id, world.case.case_id)] = removed
    revoked_actor = lawyer.get(_editor_path(world.case.case_id), headers=_headers(world.case, lawyer_csrf, world.grant.revision))
    assert revoked_actor.status_code in {401, 403}
    assert "Stored head that must survive." not in revoked_actor.text
    assert _head_file(world).read_bytes() == sealed
    fresh = UserOwnedKeySession(world.keys.directory)
    fresh.unlock_passphrase(PASSPHRASE)
    world.mediator.owner_key_session = fresh
    world.app.state.owner_key_sessions[world.owner.principal_id] = fresh
    reread = owner.get(_editor_path(world.case.case_id), headers=_headers(world.case, csrf))
    assert reread.status_code == 403
    assert reread.json()["detail"] == "key_revoked"
    assert "Stored head that must survive." not in reread.text


def test_workspace_editor_shows_save_states_without_browser_storage(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    world = _world(tmp_path)
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux31-profile"
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
            {"caseId": world.case.case_id, "headers": headers},
        )
        assert page.locator("[data-role='draft-editor']").count() == 1
        assert page.locator("link[data-complaint-draft-style]").count() == 1
        observed_state = page.evaluate(
            """async () => {
                const field = document.querySelector("[data-role='draft-input']");
                field.value = "The employer did not pay wages that were due.";
                const original = window.fetch;
                let seen = "";
                window.fetch = function () {
                    const state = document.querySelector("[data-role='save-state']");
                    if (state && arguments[0] && String(arguments[0]).indexOf("draft-editor") >= 0) {
                        seen = state.getAttribute("data-save-state");
                    }
                    return original.apply(this, arguments);
                };
                document.querySelector("[data-role='save-draft']").click();
                for (let attempt = 0; attempt < 50; attempt += 1) {
                    const state = document.querySelector("[data-role='save-state']").getAttribute("data-save-state");
                    if (state === "saved" || state === "conflict") break;
                    await new Promise(resolve => setTimeout(resolve, 50));
                }
                window.fetch = original;
                return {
                    seen: seen,
                    state: document.querySelector("[data-role='save-state']").getAttribute("data-save-state"),
                    stored: document.querySelector("[data-role='stored-draft']").textContent,
                    browser: JSON.stringify({local: {...localStorage}, session: {...sessionStorage}})
                };
            }"""
        )
        assert observed_state["seen"] == "saving"
        assert observed_state["state"] == "saved"
        assert "did not pay wages" in observed_state["stored"]
        assert "did not pay wages" not in observed_state["browser"]
        page.evaluate(
            """() => {
                document.querySelector("[data-role='draft-input']").value = "The employer did not pay wages that were due.\\nOvertime was also withheld.";
                document.querySelector("[data-role='save-draft']").click();
            }"""
        )
        page.wait_for_function(
            "() => document.querySelector('[data-role=save-state]').getAttribute('data-save-state') === 'saved' && document.querySelectorAll('[data-op=insert]').length > 0"
        )
        assert "Overtime was also withheld." in page.locator("[data-op='insert']").inner_text()
        page.evaluate("() => { document.querySelector('#complaint-outline').dataset.headRevision = '0'; }")
        page.fill("[data-role='draft-input']", "This stale text must not become the head.")
        page.click("[data-role='save-draft']")
        page.wait_for_function(
            "() => document.querySelector('[data-role=save-state]').getAttribute('data-save-state') === 'conflict'"
        )
        assert "not overwritten" in page.locator("[data-role='save-state']").inner_text()
        assert "Overtime was also withheld." in page.locator("[data-role='stored-draft']").inner_text()
        assert "This stale text must not become the head." not in page.locator("[data-role='stored-draft']").inner_text()
        stored = page.evaluate("() => JSON.stringify({local: {...localStorage}, session: {...sessionStorage}})")
        assert "This stale text must not become the head." not in stored
        assert "Overtime was also withheld." not in stored
        assert b"This stale text" not in _head_file(world).read_bytes()
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
