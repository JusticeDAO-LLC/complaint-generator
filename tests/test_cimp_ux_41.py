"""Owner invitations, recipient acceptance, and revocation.

Dialogs post the server-issued membership version and the stored scope.
Replay of the same invitation is the same grant. Expired, wrong-case,
scope-mismatched, and revoked requests stay denied. A role or a request
body cannot mint ownership or a key grant.
"""
from __future__ import annotations

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

SCOPE = ["case.read", "case.review"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _world(tmp_path):
    return owner_lawyer_journey_world(tmp_path)


def _invite(owner, token, world, *, key, scope=None, days=None, expires_at=None, extra=None):
    body = {
        "case_id": world.case.case_id,
        "member_principal_id": world.lawyer.principal_id,
        "scope": scope or SCOPE,
        "expected_case_revision": world.case.revision,
        "idempotency_key": key,
    }
    if days is not None:
        body["access_for_days"] = days
    if expires_at is not None:
        body["expires_at"] = expires_at
    if extra:
        body.update(extra)
    return owner.post("/api/cases/assignments", headers=_csrf(token), json=body)


def test_owner_invite_and_recipient_accept_replay_the_server_version(tmp_path):
    world = _world(tmp_path / "replay")
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer:
        owner_token = _composed_login(owner)
        lawyer_token = _composed_login(lawyer, "synthetic-lawyer-credential")
        minted = _invite(owner, owner_token, world, key="mint", days=30, extra={"accepted": True, "grant_id": "fabricated"})
        assert minted.status_code == 403
        assert minted.json()["error"] == "request_cannot_mint_authority"
        ambient = lawyer.post("/api/cases/assignments", headers=_csrf(lawyer_token), json={
            "case_id": world.case.case_id,
            "member_principal_id": world.lawyer.principal_id,
            "scope": SCOPE,
            "access_for_days": 30,
            "expected_case_revision": world.case.revision,
            "idempotency_key": "lawyer-invite",
        })
        assert ambient.status_code == 404
        assert ambient.json()["error"] == "missing_case"
        first = _invite(owner, owner_token, world, key="ux41-invite", days=30)
        assert first.status_code == 201, first.text
        issued = first.json()
        assert issued["version_source"] == "server"
        assert issued["server_version"] == 1
        assert issued["state"] == "pending"
        assert issued["scope_labels"] == ["Read", "Review"]
        assert "server version 1" in issued["acceptance_prompt"]
        assert issued["key_grant"] == "required"
        again = _invite(owner, owner_token, world, key="ux41-invite", days=30)
        assert again.status_code == 201, again.text
        assert again.json()["grant_id"] == issued["grant_id"]
        assert again.json()["server_version"] == 1
        changed = _invite(owner, owner_token, world, key="ux41-invite", days=30, scope=["case.read"])
        assert changed.status_code == 409
        assert changed.json()["error"] == "replay_mismatch"
        mismatch = lawyer.post(
            "/api/cases/assignments/" + issued["grant_id"] + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": ["case.read"], "case_id": world.case.case_id, "expected_version": 1, "idempotency_key": "ux41-accept"},
        )
        assert mismatch.status_code == 403
        assert mismatch.json()["error"] == "scope_mismatch"
        wrong_case = lawyer.post(
            "/api/cases/assignments/" + issued["grant_id"] + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": SCOPE, "case_id": "other-case", "expected_version": 1, "idempotency_key": "ux41-accept"},
        )
        assert wrong_case.status_code == 404
        assert wrong_case.json()["error"] == "missing_grant"
        accepted = lawyer.post(
            "/api/cases/assignments/" + issued["grant_id"] + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": SCOPE, "case_id": world.case.case_id, "expected_version": issued["server_version"], "idempotency_key": "ux41-accept"},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["state"] == "accepted"
        assert accepted.json()["server_version"] == 2
        replay = lawyer.post(
            "/api/cases/assignments/" + issued["grant_id"] + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": SCOPE, "case_id": world.case.case_id, "expected_version": 1, "idempotency_key": "ux41-accept"},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["grant_id"] == issued["grant_id"]
        assert replay.json()["server_version"] == 2
        listed = lawyer.get("/api/cases/assignments")
        assert listed.status_code == 200
        row = listed.json()["assignments"][0]
        assert row["party"] == "recipient"
        assert row["server_version"] == 2
        assert "Read" in row["acceptance_prompt"]


def test_expired_and_revoked_invitations_do_not_open_content(tmp_path):
    world = _world(tmp_path / "deny")
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer, TestClient(world.app, base_url="https://testserver") as stranger:
        owner_token = _composed_login(owner)
        lawyer_token = _composed_login(lawyer, "synthetic-lawyer-credential")
        stranger_token = _composed_login(stranger, "synthetic-stranger-credential")
        short = _invite(owner, owner_token, world, key="ux41-short", expires_at=world.now["t"] + 5)
        assert short.status_code == 201, short.text
        grant_id = short.json()["grant_id"]
        world.now["t"] += 10
        expired = lawyer.post(
            "/api/cases/assignments/" + grant_id + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": SCOPE, "case_id": world.case.case_id, "expected_version": 1, "idempotency_key": "ux41-expired"},
        )
        assert expired.status_code == 403
        assert expired.json()["error"] == "grant_expired"
        durable = _invite(owner, owner_token, world, key="ux41-durable", expires_at=world.now["t"] + 4000)
        assert durable.status_code == 201, durable.text
        durable_id = durable.json()["grant_id"]
        accepted = lawyer.post(
            "/api/cases/assignments/" + durable_id + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": SCOPE, "case_id": world.case.case_id, "expected_version": 1, "idempotency_key": "ux41-durable-accept"},
        )
        assert accepted.status_code == 200, accepted.text
        version = accepted.json()["server_version"]
        stranger_accept = stranger.post(
            "/api/cases/assignments/" + durable_id + "/accept",
            headers=_csrf(stranger_token),
            json={"scope": SCOPE, "case_id": world.case.case_id, "expected_version": version, "idempotency_key": "stranger"},
        )
        assert stranger_accept.status_code == 404
        removed = owner.post(
            "/api/cases/assignments/" + durable_id + "/remove",
            headers=_csrf(owner_token),
            json={"case_id": world.case.case_id, "expected_version": version, "idempotency_key": "ux41-revoke"},
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["revoked"] is True
        assert removed.json()["state"] == "removed"
        late = lawyer.post(
            "/api/cases/assignments/" + durable_id + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": SCOPE, "case_id": world.case.case_id, "expected_version": version, "idempotency_key": "ux41-late"},
        )
        assert late.status_code == 403
        opened = lawyer.post(
            "/api/cases/assignments/" + durable_id + "/use",
            headers=_csrf(lawyer_token),
            json={"surface": "api", "action": "case.read", "expected_version": removed.json()["server_version"], "case_id": world.case.case_id},
        )
        assert opened.status_code == 403
        assert "text" not in opened.json()
        wrong_remove = owner.post(
            "/api/cases/assignments/" + durable_id + "/remove",
            headers=_csrf(owner_token),
            json={"case_id": "other-case", "expected_version": removed.json()["server_version"], "idempotency_key": "ux41-revoke-wrong"},
        )
        assert wrong_remove.status_code == 404


def _browser(tmp_path, monkeypatch, world):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux41-profile"
    profile.mkdir(mode=0o700)
    observed = set()

    def verify_startup_cleanup():
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"] and cleanup["remaining_pids"] == []

    with ExitStack() as startup:
        startup.callback(verify_startup_cleanup)
        playwright = browser._load_sync_playwright()().start()
        startup.callback(playwright.stop)
        observed.update(browser._with_descendants(browser._matching_pids((node.argv[1],))))
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        startup.callback(context.close)
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        browser._assert_process_custody(node, chromium, profile)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        page.set_viewport_size({"width": 1440, "height": 1000})
        startup.pop_all()
    return page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"] and cleanup["remaining_pids"] == []


def _sign_in(page, credential):
    page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
    page.fill("#case-credential", credential)
    page.click("#case-login button[type=submit]")
    page.wait_for_function("() => document.getElementById('case-auth-status').textContent === 'Signed in'")


def _click_clear_of_shell(page, locator):
    """Scroll the control below the sticky case shell, then click it."""
    locator.wait_for(state="visible")
    locator.evaluate("""(node) => {
        const shell = document.getElementById('complaint-case-shell');
        const limit = shell ? shell.getBoundingClientRect().height : 0;
        node.style.scrollMarginTop = (limit + 24) + 'px';
        node.scrollIntoView({block: 'start', inline: 'nearest'});
    }""")
    locator.click()


def test_invitation_dialogs_accept_and_revoke_server_versions(tmp_path, monkeypatch):
    world = _world(tmp_path / "browser")
    page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch, world)
    try:
        _sign_in(page, "synthetic-owner-credential")
        _click_clear_of_shell(page, page.locator("#case-list button", has_text="owner-lawyer-journey"))
        page.wait_for_function("() => document.getElementById('selected-case-label').textContent === 'owner-lawyer-journey'")
        _click_clear_of_shell(page, page.locator("#invite-lawyer input[value='case.review']"))
        _click_clear_of_shell(page, page.locator("#invite-lawyer button[type=submit]"))
        page.wait_for_selector("#invitation-dialog[open]")
        summary = page.locator("#invitation-dialog-summary").inner_text()
        assert "owner-lawyer-journey" in summary
        assert "Read, Review" in summary
        assert "30 days" in summary
        assert "server will issue the version" in summary.lower() or "The server will issue the version" in summary
        page.click("#invitation-dialog-confirm")
        page.wait_for_function("""() => {
            const row = document.querySelector('#assignment-list .assignment-state');
            return row && row.textContent.includes('pending') && row.textContent.includes('Server version 1');
        }""")
        assert page.locator("#invitation-dialog[open]").count() == 0
        page.click("#case-logout")
        _sign_in(page, "synthetic-lawyer-credential")
        page.wait_for_selector("#lawyer-queue-list .lawyer-queue-open")
        _click_clear_of_shell(page, page.locator("#lawyer-queue-list .lawyer-queue-open"))
        page.wait_for_selector("#acceptance-dialog[open]")
        assert "server version 1" in page.locator("#acceptance-dialog-summary").inner_text().lower()
        page.click("#acceptance-dialog-accept")
        assert page.locator("#acceptance-dialog[open]").count() == 1
        assert "exact case and scope" in page.locator("#acceptance-dialog-error").inner_text()
        page.check("#acceptance-dialog-confirm-scope")
        page.click("#acceptance-dialog-accept")
        page.wait_for_function("""() => {
            const row = document.querySelector('#assignment-list .assignment-state');
            return row && row.textContent.includes('accepted') && row.textContent.includes('Server version 2');
        }""")
        _click_clear_of_shell(page, page.locator("#lawyer-queue-list .lawyer-queue-open"))
        page.wait_for_function("""() => {
            const workspace = document.getElementById('lawyer-review-workspace');
            return !workspace || workspace.dataset.plaintext !== 'shown';
        }""")
        page.click("#case-logout")
        _sign_in(page, "synthetic-owner-credential")
        _click_clear_of_shell(page, page.locator("#assignment-list button", has_text="Revoke access"))
        page.wait_for_selector("#revocation-dialog[open]")
        assert "server version 2" in page.locator("#revocation-dialog-summary").inner_text().lower()
        page.click("#revocation-dialog-confirm")
        page.wait_for_function("""() => {
            const row = document.querySelector('#assignment-list .assignment-state');
            return row && row.textContent.includes('removed');
        }""")
        assert page.locator("#assignment-content").inner_text() == ""
    finally:
        _close(playwright, context, node, profile, observed)
