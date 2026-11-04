"""Lawyer evidence, fact, law, and draft review workspace.

The workspace opens from the server-issued recipient grant. The owner wallet
can stay locked. A mismatched or revoked grant returns no complaint plaintext.
"""
from __future__ import annotations

from contextlib import ExitStack
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import NARRATIVE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _issued_headers(review_url):
    query = parse_qs(urlparse(review_url).query)
    return {
        "x-tenant-id": query["tenant_id"][0],
        "x-case-id": query["case_id"][0],
        "x-resource-id": query["resource_id"][0],
        "x-expected-revision": query["expected_revision"][0],
        "x-expected-membership-revision": query["expected_membership_revision"][0],
    }


def _prepare(tmp_path):
    world = owner_lawyer_journey_world(tmp_path)
    case = world.case
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer:
        owner_token = _composed_login(owner)
        lawyer_token = _composed_login(lawyer, "synthetic-lawyer-credential")
        started = owner.post(
            "/api/complaint-workspace/intake-chat",
            headers=_composed_headers(case, owner_token),
            json={"message": NARRATIVE, "interview_action": "start"},
        )
        assert started.status_code == 200, started.text
        invited = owner.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case.case_id,
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read", "case.review"],
            "expires_at": world.now["t"] + 4000,
            "expected_case_revision": case.revision,
            "idempotency_key": "ux40-invite",
        })
        assert invited.status_code == 201, invited.text
        accepted = lawyer.post(
            "/api/cases/assignments/" + invited.json()["grant_id"] + "/accept",
            headers=_csrf(lawyer_token),
            json={"scope": ["case.read", "case.review"], "expected_version": 1, "idempotency_key": "ux40-accept"},
        )
        assert accepted.status_code == 200, accepted.text
        sharing = owner.get(
            "/api/legal-analysis/" + case.case_id + "/lawyer-reviews/sharing",
            headers=_composed_headers(case),
        )
        assert sharing.status_code == 200, sharing.text
        shared = owner.post(
            "/api/legal-analysis/" + case.case_id + "/lawyer-reviews/share",
            headers=_composed_headers(case, owner_token),
            json={
                "membership_id": invited.json()["grant_id"],
                "expected_membership_version": accepted.json()["revision"],
                "expected_private_revision": sharing.json()["private_revision"],
            },
        )
        assert shared.status_code == 200, shared.text
        review_url = shared.json()["review_url"]
    world.owner_keys.lock()
    world.service.lock_private_keys()
    assert world.owner_keys.unlocked is False
    return world, review_url, invited.json()["grant_id"], accepted.json()["revision"]


def _workspace(client, case_id, headers):
    return client.get("/api/legal-analysis/" + case_id + "/lawyer-review-workspace", headers=headers)


def test_review_workspace_uses_recipient_grant_while_owner_wallet_is_locked(tmp_path):
    world, review_url, grant_id, membership_version = _prepare(tmp_path / "api")
    headers = _issued_headers(review_url)
    with TestClient(world.app, base_url="https://testserver") as lawyer, TestClient(world.app, base_url="https://testserver") as stranger:
        _composed_login(lawyer, "synthetic-lawyer-credential")
        _composed_login(stranger, "synthetic-stranger-credential")
        opened = _workspace(lawyer, world.case.case_id, headers)
        assert opened.status_code == 200, opened.text
        body = opened.json()
        assert body["status"] == "ready"
        assert body["layout"] == ["evidence", "facts", "law", "draft"]
        assert body["owner_wallet_required"] is False
        assert body["plaintext_cleared"] is False
        assert body["proof"] is False
        assert body["governing_legal_authority"] is False
        assert body["scope_labels"] == ["Read", "Review"]
        assert any(row["text"] == NARRATIVE and row["adopted_evidence"] is False for row in body["facts"])
        assert body["law_empty_label"]
        assert body["draft"]["status"] == "empty"
        assert body["draft"]["text"] == ""
        assert grant_id not in opened.text
        assert world.owner_keys.unlocked is False
        mismatched = dict(headers)
        mismatched["x-resource-id"] = "mismatched-resource"
        denied = _workspace(lawyer, world.case.case_id, mismatched)
        assert denied.status_code in {403, 409}
        assert NARRATIVE not in denied.text
        assert denied.json().get("plaintext_cleared") is True or denied.json().get("error")
        stranger_view = _workspace(stranger, world.case.case_id, headers)
        assert stranger_view.status_code in {403, 404}
        assert NARRATIVE not in stranger_view.text
        world.memberships.remove(
            owner_principal_id=world.owner.principal_id,
            grant_id=grant_id,
            expected_version=membership_version,
        )
        revoked = _workspace(lawyer, world.case.case_id, headers)
        assert revoked.status_code in {403, 409, 503}
        assert NARRATIVE not in revoked.text
        assert revoked.json().get("facts") in (None, [])
        assert revoked.json().get("draft", {}).get("text", "") == ""


def test_revocation_during_publication_drops_late_plaintext(tmp_path, monkeypatch):
    world, review_url, grant_id, membership_version = _prepare(tmp_path / "late")
    headers = _issued_headers(review_url)

    def revoke_before_return(payload):
        world.memberships.remove(
            owner_principal_id=world.owner.principal_id,
            grant_id=grant_id,
            expected_version=membership_version,
        )
        return payload

    monkeypatch.setattr(
        "applications.legal_analysis_api.confirm_review_workspace_publication",
        revoke_before_return,
    )
    with TestClient(world.app, base_url="https://testserver") as lawyer:
        _composed_login(lawyer, "synthetic-lawyer-credential")
        late = _workspace(lawyer, world.case.case_id, headers)
    assert late.status_code in {403, 409, 503}
    assert NARRATIVE not in late.text
    assert late.json().get("plaintext_cleared") is True
    assert late.json().get("facts") == []
    assert late.json().get("draft", {}).get("text") == ""


def _browser(tmp_path, monkeypatch, world):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux40-profile"
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


def test_issued_review_workspace_renders_and_clears_in_the_browser(tmp_path, monkeypatch):
    world, review_url, _grant_id, _version = _prepare(tmp_path / "browser")
    page, playwright, context, node, profile, observed = _browser(tmp_path, monkeypatch, world)
    try:
        page.goto(browser.SAME_ORIGIN + "/cases?" + urlparse(review_url).query, wait_until="domcontentloaded")
        page.fill("#case-credential", "synthetic-lawyer-credential")
        with page.expect_response(lambda response: "/lawyer-review-workspace" in response.url and response.status == 200):
            page.click("#case-login button[type=submit]")
        page.wait_for_function(
            """(narrative) => {
                const facts = document.querySelector('#review-facts');
                return facts && facts.innerText.includes(narrative)
                    && document.querySelector('#review-evidence')
                    && document.querySelector('#review-law')
                    && document.querySelector('#review-draft');
            }""",
            arg=NARRATIVE,
        )
        assert "Accepted scope: Read, Review." in page.locator("#review-workspace-scope").inner_text()
        assert "No admitted law is bound to this review." in page.locator("#review-law").inner_text()
        assert "No draft revision is shared with this review." in page.locator("#review-draft").inner_text()
        assert _grant_id not in page.locator("#lawyer-review-workspace").inner_text()
        query = parse_qs(urlparse(review_url).query)
        query["expected_membership_revision"] = ["99"]
        mismatched = "&".join(key + "=" + values[0] for key, values in query.items())
        page.evaluate("(search) => window.complaintReviewer.openIssued(search)", mismatched)
        page.wait_for_function("""(narrative) => {
            const workspace = document.getElementById('lawyer-review-workspace');
            return workspace && workspace.dataset.plaintext === 'cleared' && !workspace.innerText.includes(narrative);
        }""", arg=NARRATIVE)
        page.evaluate("() => window.complaintReviewer.openIssued(window.location.search)")
        page.wait_for_function(
            "(narrative) => document.querySelector('#review-facts').innerText.includes(narrative)",
            arg=NARRATIVE,
        )
        page.click("#case-logout")
        page.wait_for_function("""(narrative) => {
            const workspace = document.getElementById('lawyer-review-workspace');
            return workspace && workspace.dataset.plaintext === 'cleared' && !workspace.innerText.includes(narrative);
        }""", arg=NARRATIVE)
    finally:
        _close(playwright, context, node, profile, observed)
