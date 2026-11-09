"""Key unlock, lock, rotation, and revocation stay coherent across the case UI.

A real key transition clears cached chat, evidence, graphs, draft, and messages
and tells the person how to recover. A locked, wrong, or revoked key cannot mint
an empty case. A late write and another actor's wallet are refused.
"""

from __future__ import annotations

from contextlib import ExitStack

import pytest

from applications.complaint_workspace import WorkspacePersistenceError
from integrations.private_storage import UserOwnedKeySession
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On April 2 the clerk refused the garden-level transfer."
SECRET = "synthetic-cached-plaintext-ux58"
WRONG = "wrong-passphrase-ux58"


def _ids(world):
    return world.case.tenant_id, world.case.case_id, world.owner.principal_id


def test_wrong_revoked_stale_and_foreign_wallet_do_not_open_a_case(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    tenant, case_id, actor = _ids(world)
    service = world.service
    before_key = service._existing_case_key_id(tenant, case_id)
    before_count = service.private_key_status()["case_count"]
    assert before_key

    wrong = service.synchronize_key_coherence(
        action="unlock", tenant_id=tenant, case_id=case_id, actor_id=actor, passphrase=WRONG,
    )
    assert wrong["admitted"] is False
    assert wrong["empty_case_created"] is False
    assert wrong["code"] == "authentication_failed"
    assert service._existing_case_key_id(tenant, case_id) == before_key
    assert service.private_key_status()["case_count"] == before_count
    assert SECRET not in str(wrong)
    assert PASSPHRASE not in str(wrong)

    opened = service.synchronize_key_coherence(
        action="unlock", tenant_id=tenant, case_id=case_id, actor_id=actor, passphrase=PASSPHRASE,
    )
    assert opened["admitted"] is True
    assert opened["status"] == "unlocked"
    assert opened["empty_case_created"] is False
    assert opened["data_key_id"] == before_key
    epoch = opened["epoch"]

    other = tmp_path / "other-wallet"
    UserOwnedKeySession(other).create(protection="passphrase", passphrase="synthetic-other-wallet-ux58")
    borrowed = service.synchronize_key_coherence(
        action="unlock", tenant_id=tenant, case_id=case_id, actor_id=world.lawyer.principal_id,
        passphrase="synthetic-other-wallet-ux58", wallet_directory=str(other),
    )
    assert borrowed["status"] == "foreign_wallet"
    assert borrowed["admitted"] is False
    assert borrowed["wallet_replaced"] is False
    assert borrowed["empty_case_created"] is False
    assert service._private_key_directory().resolve() != other.resolve()
    assert service._existing_case_key_id(tenant, case_id) == before_key

    rotated = service.synchronize_key_coherence(
        action="rotate", tenant_id=tenant, case_id=case_id, actor_id=actor,
        expected_epoch=epoch, captured_key_id=before_key,
    )
    assert rotated["admitted"] is True
    assert rotated["data_key_id"] != before_key
    assert rotated["empty_case_created"] is False
    assert "previous key epoch" in rotated["recovery_guidance"]
    with pytest.raises(WorkspacePersistenceError) as stale:
        service.update_draft(
            tenant, body=SECRET, case_id=case_id, actor_id=actor,
            expected_key_epoch=epoch, captured_key_id=before_key,
        )
    assert stale.value.code == "stale_key_epoch"
    with pytest.raises(WorkspacePersistenceError) as foreign_write:
        service.save_evidence(
            tenant, kind="document", claim_element_id="causation", title="late", content=SECRET,
            case_id=case_id, actor_id=world.lawyer.principal_id,
            expected_key_epoch=rotated["epoch"], captured_key_id=rotated["data_key_id"],
        )
    assert foreign_write.value.code == "foreign_wallet"

    revoked = service.synchronize_key_coherence(
        action="revoke", tenant_id=tenant, case_id=case_id, actor_id=actor,
    )
    assert revoked["status"] == "revoked"
    assert revoked["empty_case_created"] is False
    assert revoked["admitted"] is False
    assert "does not recreate" in revoked["recovery_guidance"]
    with pytest.raises(WorkspacePersistenceError) as blocked:
        service.get_session(tenant, case_id=case_id)
    assert blocked.value.code == "key_unavailable"
    with pytest.raises(WorkspacePersistenceError):
        service.ensure_private_case_key(tenant, case_id)
    assert service._existing_case_key_id(tenant, case_id) == rotated["data_key_id"]
    assert service.private_key_status()["case_count"] == before_count


def _open(tmp_path, monkeypatch, world):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux58-profile"
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
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        startup.callback(context.close)
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        browser._assert_process_custody(node, chromium, profile)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        startup.pop_all()
    return page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"] and cleanup["remaining_pids"] == []


def test_browser_key_transitions_clear_and_reload_case_surfaces(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        started = client.post(
            "/api/complaint-workspace/intake-chat",
            headers=_composed_headers(world.case, csrf),
            json={"message": NARRATIVE, "interview_action": "start"},
        )
        assert started.status_code == 200, started.text
        pending = started.json()["session"]["shared_interview"]["pending_inquiry"]
        question = pending.get("question") or pending.get("prompt")
        assert question and SECRET not in question
        session = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case, csrf))
        assert session.status_code == 200, session.text
        coherence = session.json()["key_coherence"]
        assert coherence["status"] == "unlocked"
        assert coherence["empty_case_created"] is False
        assert "passphrase" not in coherence["recovery_guidance"].lower()
    world.service.lock_private_keys()
    world.owner_keys.lock()
    page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        page.fill("#case-credential", "synthetic-owner-credential")
        page.click("#case-login button[type=submit]")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-actor').dataset.principalId")
        page.click("#case-list button")
        page.wait_for_function("""() => window.complaintCaseShell
            && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")
        page.evaluate("""(secret) => {
            const main = document.querySelector('main');
            ['draft-body', 'mediator-conversation-log', 'evidence-list', 'factual-graph-mount', 'message-list'].forEach((id) => {
                const node = document.createElement(id === 'draft-body' ? 'textarea' : 'div');
                node.id = id;
                if (id === 'draft-body') node.value = secret;
                else node.textContent = secret;
                main.appendChild(node);
            });
        }""", SECRET)
        with page.expect_response(lambda response: response.request.method == "GET"
                and "/api/complaint-workspace/session?case_id=" in response.url) as locked:
            page.evaluate("() => window.complaintCaseShell.refresh()")
        assert locked.value.status == 503
        assert locked.value.json()["error"] == "unlock_needed"
        assert locked.value.json()["session_readable"] is False
        page.wait_for_function("""() => {
            const guidance = document.getElementById('complaint-key-guidance');
            return guidance && guidance.textContent.includes('cleared') && guidance.textContent.includes('wallet');
        }""")
        assert SECRET not in page.locator("body").inner_text()
        assert page.locator("#draft-body").input_value() == ""
        assert page.evaluate("() => document.documentElement.dataset.emptyCaseCreated") == "false"
        cases_before = world.cases.list_cases(actor_principal_id=world.owner.principal_id)
        assert world.service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
        world.owner_keys.unlock_passphrase(PASSPHRASE)
        with page.expect_response(lambda response: response.request.method == "GET"
                and "/api/complaint-workspace/session?case_id=" in response.url) as resumed:
            page.click("#complaint-entry-check-key")
        assert resumed.value.status == 200
        body = resumed.value.json()
        assert body["key_coherence"]["status"] == "unlocked"
        assert body["key_coherence"]["reload"] is False
        assert question in (body["session"]["shared_interview"]["pending_inquiry"].get("question")
            or body["session"]["shared_interview"]["pending_inquiry"].get("prompt"))
        page.wait_for_function("""(inquiryId) => {
            const question = document.getElementById('complaint-entry-question');
            return question && question.dataset.inquiryId === inquiryId && question.textContent.length > 0;
        }""", arg=str(pending["inquiry_id"]))
        assert SECRET not in page.locator("body").inner_text()
        assert world.cases.list_cases(actor_principal_id=world.owner.principal_id) == cases_before
        messages = page.goto(browser.SAME_ORIGIN + "/case-messages", wait_until="domcontentloaded")
        assert messages.status == 200
        page.evaluate("""(secret) => {
            const item = document.createElement('li');
            item.textContent = secret;
            document.getElementById('message-list').appendChild(item);
        }""", SECRET)
        page.evaluate("""() => window.complaintCaseShell.applyKeyCoherence({
            status: 'locked', epoch: 9, clear_plaintext: true, reload: false, empty_case_created: false,
            recovery_guidance: 'Messages were cleared until this case wallet is unlocked again.'
        })""")
        assert page.locator("#message-list").inner_text() == ""
        assert "wallet" in page.locator("#inbox-status").inner_text()
        assert SECRET not in page.locator("body").inner_text()
    finally:
        _close(playwright, context, node, profile, observed)
