"""Mediator conversation provenance, actions, and bounded refresh.

The conversation is a projection of the canonical workspace session. It keeps
user statements, mediator questions, model suggestions, and system outcomes
distinct, and it does not show prompts, credentials, or actor ids as the
primary text.
"""
from __future__ import annotations

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On March 1 the office denied the request for the two-bedroom voucher."
EVIDENCE_TITLE = "March voucher denial email"
SECRET_PROMPT = "system-prompt-do-not-render-9f3a"
SECRET_CREDENTIAL = "credential-do-not-render-9f3a"


def _open(tmp_path, monkeypatch, *, world=None):
    world = world or owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux08-profile"
    profile.mkdir(mode=0o700)
    observed = set()

    def verify_startup_cleanup():
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"] and cleanup["remaining_pids"] == [], "failed startup left owned browser processes"

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
    return world, page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _seed(world):
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        headers = _composed_headers(world.case, csrf)
        started = client.post(
            "/api/complaint-workspace/intake-chat",
            headers=headers,
            json={"message": NARRATIVE, "interview_action": "start"},
        )
        assert started.status_code == 200, started.text
        pending = started.json()["session"]["shared_interview"]["pending_inquiry"]
        evidence = client.post(
            "/api/complaint-workspace/evidence",
            headers=headers,
            json={
                "kind": "document",
                "claim_element_id": "adverse_action",
                "title": EVIDENCE_TITLE,
                "content": "The written denial arrived by email on March 1.",
                "source": "inbox",
            },
        )
        assert evidence.status_code == 200, evidence.text
        return pending["inquiry_id"], pending["question"]


def _sign_in(page):
    page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
    page.fill("#case-credential", "synthetic-owner-credential")
    with page.expect_response(lambda response: response.request.method == "POST"
            and response.url.endswith("/api/complaint-workspace/auth/login")):
        page.click("#case-login button[type=submit]")
    page.click("#case-list button")
    page.wait_for_function("""() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'owner'""")


def _workspace(page, inquiry_id):
    page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
    page.wait_for_function("""(inquiryId) => {
        const pending = document.getElementById('adaptive-pending');
        const log = document.querySelector('#mediator-conversation-log [data-message-type="ai-question"]');
        const shell = document.getElementById('complaint-case-shell');
        return pending && pending.dataset.inquiryId === inquiryId && log && shell
            && shell.getAttribute('aria-busy') === 'false';
    }""", arg=inquiry_id)


def _conversation(page):
    return page.evaluate("""() => {
        const root = document.getElementById('mediator-conversation');
        const actor = document.getElementById('complaint-case-shell-actor');
        const rows = Array.from(document.querySelectorAll('#mediator-conversation-log [data-message-type]')).map((node) => ({
            type: node.dataset.messageType,
            kind: node.querySelector('.mediator-conversation__kind').textContent,
            body: node.querySelector('.mediator-conversation__body').textContent,
            why: node.querySelector('.mediator-conversation__why').textContent,
            availability: node.dataset.availability,
            label: node.getAttribute('role'),
        }));
        return {
            lifecycle: root.dataset.lifecycle,
            retryCount: root.dataset.retryCount,
            busy: root.getAttribute('aria-busy'),
            context: document.getElementById('mediator-conversation-context').textContent,
            status: document.getElementById('mediator-conversation-status').textContent,
            text: root.innerText,
            actions: Array.from(document.querySelectorAll('#mediator-conversation-actions button')).map((node) => node.textContent),
            rows,
            principalId: actor.dataset.principalId || '',
        };
    }""")


def test_conversation_distinguishes_provenance_and_offers_case_actions(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, question = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        shown = _conversation(page)
        types = [row["type"] for row in shown["rows"]]
        assert types[:4] == ["user-statement", "ai-question", "model-suggestion", "system-outcome"]
        assert all(row["label"] == "article" for row in shown["rows"])
        assert {row["kind"] for row in shown["rows"]} == {
            "Your statement", "Mediator question", "Model suggestion", "System outcome"
        }
        user = shown["rows"][0]
        assert user["body"] == NARRATIVE
        assert "legal conclusion" in user["why"]
        assert shown["rows"][1]["body"] == question
        assert shown["rows"][2]["availability"] == "unavailable"
        assert "not a fact" in shown["rows"][2]["why"]
        assert "The mediator is waiting for your answer. Answer the current question to continue." in shown["rows"][3]["body"]
        assert "owner-lawyer-journey" in shown["context"]
        assert EVIDENCE_TITLE in shown["context"]
        assert "Answer the current question" in shown["actions"]
        assert "Review the case evidence" in shown["actions"]
        assert shown["principalId"]
        assert shown["principalId"] not in shown["text"]
        assert inquiry_id not in shown["text"]
        assert SECRET_PROMPT not in shown["text"]
        page.locator("#mediator-conversation-actions").get_by_role("button", name="Answer the current question").click()
        assert page.evaluate("() => document.activeElement.id") == "adaptive-answer"
        page.locator("#mediator-conversation-actions").get_by_role("button", name="Review the case evidence").click()
        assert page.locator("#evidence-list").is_visible()
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        assert page.evaluate("() => typeof window.localComplaintStore") == "undefined"
    finally:
        _close(playwright, context, node, profile, observed)


def test_refresh_cancel_ignores_a_late_session_and_retry_stops_at_three(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, question = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    held = []
    mode = {"value": "pass"}

    def route(request):
        url = request.request.url
        if request.request.method == "GET" and "/api/complaint-workspace/session" in url and mode["value"] != "pass":
            if mode["value"] == "hold":
                held.append(request)
                return
            request.fulfill(status=503, body='{"error":"unavailable"}', headers={"content-type": "application/json"})
            return
        request.continue_()

    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        page.route("**/*", route)
        mode["value"] = "hold"
        page.click("#mediator-conversation-refresh")
        page.wait_for_function("""() => document.getElementById('mediator-conversation').dataset.lifecycle === 'pending'
            && document.getElementById('mediator-conversation').getAttribute('aria-busy') === 'true'""")
        assert page.locator("#mediator-conversation-cancel").is_enabled()
        page.click("#mediator-conversation-cancel")
        page.wait_for_function("""() => document.getElementById('mediator-conversation').dataset.lifecycle === 'cancelled'""")
        assert question in page.locator("#mediator-conversation").inner_text()
        if held:
            held[0].fulfill(status=200, body='{"session":{"original_complaint":{"text":"LATE NARRATIVE SHOULD NOT REPLACE"}}}',
                            headers={"content-type": "application/json"})
        page.wait_for_timeout(300)
        assert "LATE NARRATIVE SHOULD NOT REPLACE" not in page.locator("#mediator-conversation").inner_text()
        assert NARRATIVE in page.locator("#mediator-conversation").inner_text()

        mode["value"] = "fail"
        for expected in ("1", "2", "3"):
            page.click("#mediator-conversation-retry")
            page.wait_for_function(
                """(count) => document.getElementById('mediator-conversation').dataset.retryCount === count
                    && document.getElementById('mediator-conversation').dataset.lifecycle === 'error'""",
                arg=expected,
            )
        assert page.locator("#mediator-conversation-retry").is_disabled()
        page.evaluate("() => window.complaintConversation.retry()")
        assert page.locator("#mediator-conversation").get_attribute("data-lifecycle") == "retry-exhausted"
        assert NARRATIVE in page.locator("#mediator-conversation").inner_text()
        assert question in page.locator("#mediator-conversation").inner_text()
    finally:
        _close(playwright, context, node, profile, observed)


def test_locked_case_and_sensitive_fields_are_not_primary_conversation_text(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, _question = _seed(world)
    world.service.lock_private_keys()
    world.owner_keys.lock()
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        page.wait_for_function("""() => document.getElementById('complaint-entry').dataset.entry === 'missing-key'
            && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")
        locked = page.locator("#mediator-conversation").inner_text()
        assert NARRATIVE not in locked
        assert inquiry_id not in locked
        assert page.locator("#mediator-conversation-log [data-message-type='user-statement']").count() == 0
    finally:
        _close(playwright, context, node, profile, observed)


def test_sensitive_session_fields_do_not_become_visible_messages(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, question = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        principal = page.evaluate("() => document.getElementById('complaint-case-shell-actor').dataset.principalId")
        page.evaluate("""({prompt, credential, principal, narrative}) => {
            window.complaintConversation.project({
                session: {
                    original_complaint: {text: narrative},
                    shared_interview: {
                        pending_inquiry: {
                            question: 'What date did the office deny the voucher?',
                            inquiry_id: 'inq-hidden',
                            model_proposal: {record_type: 'model_suggestion', wording: 'Possible date: March 1.', prompt, request_id: prompt},
                            actor_principal_id: principal,
                        },
                        knowledge_graph: {entities: [{record_type: 'model_suggestion', name: 'Possible place: the office.', prompt: prompt}]}
                    },
                    intake_history: [{answer: narrative, actor_principal_id: principal, prompt: prompt}],
                    operation_consent: {credential: credential},
                    evidence: {documents: [{id: 'doc-1', title: 'March voucher denial email', prompt: prompt}]}
                },
                finite_interview_outcome: {stop: 'unresolved', prompt: prompt}
            });
        }""", {"prompt": SECRET_PROMPT, "credential": SECRET_CREDENTIAL, "principal": principal, "narrative": NARRATIVE})
        shown = _conversation(page)
        assert SECRET_PROMPT not in shown["text"]
        assert SECRET_CREDENTIAL not in shown["text"]
        assert principal not in shown["text"]
        assert "inq-hidden" not in shown["text"]
        assert "Possible date: March 1." in shown["text"]
        assert "Possible place: the office." in shown["text"]
        kinds = [row["kind"] for row in shown["rows"]]
        assert kinds.count("Model suggestion") == 2
        assert "Your statement" in kinds
        assert "Mediator question" in kinds
        assert "System outcome" in kinds
    finally:
        _close(playwright, context, node, profile, observed)
