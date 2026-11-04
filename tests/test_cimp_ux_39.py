"""Scoped lawyer case and review queue.

Assigned lawyers see only their memberships. Filter, sort, and pagination are
server-owned. Grant ids are not queue controls. Pending, locked, revoked, and
empty states stay honest, and complaint text stays out of the queue.
"""
from __future__ import annotations

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from integrations.private_storage import PrivateArtifactBinding, seal_private_artifact
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

SECRET = "secret-complaint-narrative-ux39"
TASK = "Check the denial date"
ACTION = "Record current facts"
KIND = "queue-artifact"
REVISION = "queue-rev-1"


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _create(client, token, label):
    created = client.post("/api/cases", headers=_csrf(token), json={"label": label})
    assert created.status_code == 201, created.text
    return created.json()


def _invite(client, token, world, case, key, scope):
    invited = client.post("/api/cases/assignments", headers=_csrf(token), json={
        "case_id": case["case_id"],
        "member_principal_id": world.lawyer.principal_id,
        "scope": scope,
        "expires_at": world.now["t"] + 4000,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": key,
    })
    assert invited.status_code == 201, invited.text
    assert "grant_id" in invited.json()
    return invited.json()


def _seal(world, case):
    world.owner_keys.ensure_data_key(case["tenant_id"], case["case_id"])
    binding = PrivateArtifactBinding(
        tenant_id=case["tenant_id"], case_id=case["case_id"], artifact_kind=KIND,
        revision=REVISION, principal_id=case["tenant_id"],
    )
    key_id, key = world.owner_keys.provider().resolve(binding)
    envelope = seal_private_artifact(b"sealed-artifact-not-queue-text", binding=binding, key=key, key_id=key_id)
    world.assignments.bind_artifact(
        case_id=case["case_id"], artifact_kind=KIND, artifact_revision=REVISION, envelope=envelope,
    )


def _queue(client, **params):
    response = client.get("/api/cases/lawyer-queue", params=params)
    return response


def test_lawyer_queue_is_assignment_scoped_and_paginated(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "queue")
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer, TestClient(world.app, base_url="https://testserver") as stranger:
        owner_token = _composed_login(owner)
        lawyer_token = _composed_login(lawyer, "synthetic-lawyer-credential")
        _composed_login(stranger, "synthetic-stranger-credential")
        first = _create(owner, owner_token, "owner-only-label")
        second = _create(owner, owner_token, "second-label")
        third = _create(owner, owner_token, "third-label")
        hidden = _create(owner, owner_token, "unshared-case")
        published = owner.post("/api/cases/" + first["case_id"] + "/queue-work", headers=_csrf(owner_token), json={
            "label": "Voucher review",
            "review_tasks": [TASK],
            "owner_actions": [ACTION],
        })
        assert published.status_code == 200, published.text
        assert published.json()["published_to_unassigned_lawyers"] is False
        denied = lawyer.post("/api/cases/" + first["case_id"] + "/queue-work", headers=_csrf(lawyer_token), json={
            "label": "Stolen",
            "review_tasks": ["Nope"],
        })
        assert denied.status_code == 404
        empty = _queue(lawyer)
        assert empty.status_code == 200, empty.text
        assert empty.json()["items"] == []
        assert empty.json()["empty"] is True
        assert empty.json()["role_alone_grants_cases"] is False
        assert empty.json()["unassigned_complaints_included"] is False
        assert SECRET not in empty.text
        assert _queue(lawyer, state="nope").status_code == 422
        assert _queue(lawyer, page="0").status_code == 422
        invites = [
            _invite(owner, owner_token, world, first, "invite-one", ["case.read", "case.review"]),
            _invite(owner, owner_token, world, second, "invite-two", ["case.read"]),
            _invite(owner, owner_token, world, third, "invite-three", ["case.download"]),
        ]
        pending = _queue(lawyer, page_size=2, sort="label", direction="asc")
        assert pending.status_code == 200, pending.text
        body = pending.json()
        assert body["page"]["total"] == 3
        assert body["page"]["page_count"] == 2
        assert len(body["items"]) == 2
        assert {item["state"] for item in body["items"]} == {"pending"}
        assert all(item["review_tasks"] == [] and item["pending_owner_actions"] == [] for item in body["items"])
        assert all("grant_id" not in item and "control" in item for item in body["items"])
        assert SECRET not in pending.text
        assert hidden["case_id"] not in {item["case_id"] for item in body["items"]}
        assert _queue(stranger).json()["items"] == []
        assert hidden["case_id"] not in _queue(stranger).text
        later = _queue(lawyer, page=2, page_size=2, sort="label", direction="asc")
        assert later.status_code == 200
        assert len(later.json()["items"]) == 1
        assert _queue(lawyer, page=3, page_size=2).status_code == 422
        declined = lawyer.post(
            "/api/cases/assignments/" + invites[2]["grant_id"] + "/decline",
            headers=_csrf(lawyer_token),
            json={"expected_version": 1, "idempotency_key": "decline-three"},
        )
        assert declined.status_code == 200, declined.text
        revoked = _queue(lawyer, state="revoked")
        assert revoked.status_code == 200, revoked.text
        assert len(revoked.json()["items"]) == 1
        assert revoked.json()["items"][0]["state"] == "revoked"
        assert revoked.json()["items"][0]["state_label"] == "Declined"
        assert TASK not in revoked.text
        accepted = lawyer.post(
            "/api/cases/assignments/" + invites[0]["grant_id"] + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": ["case.read", "case.review"], "expected_version": 1, "idempotency_key": "accept-one"},
        )
        assert accepted.status_code == 200, accepted.text
        locked = _queue(lawyer, state="locked")
        assert locked.status_code == 200, locked.text
        assert len(locked.json()["items"]) == 1
        assert locked.json()["items"][0]["case_id"] == first["case_id"]
        assert locked.json()["items"][0]["review_tasks"] == []
        assert "Voucher review" not in locked.text
        _seal(world, first)
        issued = owner.post(
            "/api/cases/assignments/" + invites[0]["grant_id"] + "/key-grant",
            headers=_csrf(owner_token),
            json={"artifact_kind": KIND, "artifact_revision": REVISION, "idempotency_key": "queue-key"},
        )
        assert issued.status_code == 201, issued.text
        authorized = _queue(lawyer, state="authorized")
        assert authorized.status_code == 200, authorized.text
        item = authorized.json()["items"][0]
        assert item["display_label"].startswith("Voucher review")
        assert item["control"]["label"] == item["display_label"]
        assert item["review_tasks"] == [{"label": TASK, "status_label": "Open"}]
        assert item["pending_owner_actions"] == [{"label": ACTION, "status_label": "Waiting on owner"}]
        assert item["priority_label"] == "High"
        assert "grant_id" not in item
        assert invites[0]["grant_id"] not in authorized.text
        assert SECRET not in authorized.text
        world.recipient.lock()
        relocked = _queue(lawyer, state="authorized")
        assert relocked.json()["items"] == []
        hidden_again = _queue(lawyer, state="locked")
        assert hidden_again.json()["items"][0]["review_tasks"] == []
        assert TASK not in hidden_again.text
        assert "Voucher review" not in hidden_again.text
        owned = lawyer.get("/api/cases")
        assert owned.status_code == 200
        assert owned.json()["cases"] == []
        assert first["case_id"] not in owned.text
        saved = world.app.state.case_assignments
        world.app.state.case_assignments = None
        unavailable = _queue(lawyer)
        assert unavailable.status_code == 503
        assert unavailable.json()["error"] == "lawyer_queue_unavailable"
        world.app.state.case_assignments = saved
        restored = _queue(lawyer, state="pending")
        assert restored.status_code == 200
        assert restored.json()["page"]["total"] == 1
        assert hidden["case_id"] not in restored.text
        assert SECRET not in restored.text


def _browser(tmp_path, monkeypatch, world):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux39-profile"
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


def test_lawyer_queue_page_filters_and_hides_grant_ids(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "browser")
    with TestClient(world.app, base_url="https://testserver") as owner:
        token = _composed_login(owner)
        cases = [_create(owner, token, "case-" + str(index)) for index in range(3)]
        for index, case in enumerate(cases):
            _invite(owner, token, world, case, "browser-invite-" + str(index), ["case.review"])
        grant_ids = [row["grant_id"] for row in owner.get("/api/cases/assignments").json()["assignments"]]
    page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch, world)
    try:
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert page.locator("#lawyer-review-queue").count() == 1
        page.fill("#case-credential", "synthetic-lawyer-credential")
        with page.expect_response(lambda response: response.url.endswith("/api/cases/lawyer-queue") and response.status == 200):
            page.click("#case-login button[type=submit]")
        page.wait_for_function("""() => document.querySelectorAll('#lawyer-queue-list li').length === 2""")
        listed = page.locator("#lawyer-queue-list").inner_text()
        assert "Pending acceptance" in listed
        assert "Review" in listed
        for grant_id in grant_ids:
            assert grant_id not in listed
        page.select_option("#lawyer-queue-state", "revoked")
        with page.expect_response(lambda response: "state=revoked" in response.url and response.status == 200):
            page.click("#lawyer-queue-filters button[type=submit]")
        page.wait_for_function("""() => document.getElementById('lawyer-review-queue').dataset.state === 'empty'""")
        assert "No assigned cases match this queue." in page.locator("#lawyer-queue-empty").inner_text()
        page.select_option("#lawyer-queue-state", "pending")
        with page.expect_response(lambda response: "state=pending" in response.url):
            page.click("#lawyer-queue-filters button[type=submit]")
        page.wait_for_function("""() => document.querySelectorAll('#lawyer-queue-list li').length === 2""")
        page.click("#lawyer-queue-next")
        page.wait_for_function("""() => document.getElementById('lawyer-queue-page').textContent === 'Page 2 of 2'""")
        assert page.locator("#lawyer-queue-list li").count() == 1
        page.click("#lawyer-queue-list button")
        assert "Pending acceptance" in page.locator("#lawyer-queue-status").inner_text()
        page.click("#case-logout")
        page.wait_for_function("""() => document.getElementById('lawyer-review-queue').dataset.state === 'empty'""")
    finally:
        _close(playwright, context, node, profile, observed)
