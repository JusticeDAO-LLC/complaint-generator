"""Inquiry cards for the shared adaptive interview.

The card shows the server question, its revision, why it matters, and the
linked factual gap and legal requirement. Why and status do not save an
answer. The fixed intake form does not replace that question.
"""
from __future__ import annotations

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On April 2 the office denied the request for the accessible unit."
GENERIC_NAME = "Synthetic Neighbor"


def _open(tmp_path, monkeypatch, *, world=None):
    world = world or owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux09-profile"
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
        body = started.json()
        pending = body["session"]["shared_interview"]["pending_inquiry"]
        explanation = pending.get("inquiry_explanation") or {}
        return {
            "inquiry_id": pending["inquiry_id"],
            "revision": pending["revision"],
            "question": pending["question"],
            "why": (explanation.get("why_asked") or pending.get("why_it_matters") or ""),
            "factual": ((explanation.get("factual_target") or {}).get("label") or ""),
            "requirement": ((explanation.get("sourced_legal_requirement") or {}).get("label") or ""),
            "history": len(body["session"].get("intake_history") or []),
        }


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
        const card = document.getElementById('inquiry-card');
        return card && card.dataset.pending === 'true' && card.dataset.inquiryId === inquiryId
            && document.getElementById('inquiry-card-answer')
            && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false';
    }""", arg=inquiry_id)
    page.locator('#complaint-case-shell-nav [data-case-task="mediator"]').click()
    page.locator('[data-case-panel="mediator"] #inquiry-card').wait_for(state="visible")


def _card(page):
    return page.evaluate("""() => {
        const card = document.getElementById('inquiry-card');
        const actions = Array.from(document.querySelectorAll('#inquiry-card-actions button')).map((node) => ({
            action: node.dataset.inquiryAction,
            label: node.textContent,
        }));
        return {
            pending: card.dataset.pending,
            inquiryId: card.dataset.inquiryId,
            revision: card.dataset.revision,
            source: card.dataset.source,
            fromFixedIntake: card.dataset.fromFixedIntake,
            storesAnswer: card.dataset.storesAnswer,
            question: document.getElementById('inquiry-card-question').textContent,
            revisionText: document.getElementById('inquiry-card-revision').textContent,
            why: document.getElementById('inquiry-card-explanation').textContent,
            gaps: Array.from(document.querySelectorAll('#inquiry-card-gaps li')).map((node) => node.textContent),
            requirements: Array.from(document.querySelectorAll('#inquiry-card-requirements li')).map((node) => ({
                id: node.dataset.requirementId,
                text: node.textContent,
            })),
            actions,
            replacesInterview: document.getElementById('intake-question-grid').dataset.replacesSharedInterview,
            genericPrompt: document.querySelector('#intake-question-grid strong').textContent,
        };
    }""")


def _server_pending(page):
    return page.evaluate("""async () => {
        const binding = window.complaintCaseShell.binding();
        if (!binding || !binding.case_id) throw new Error('Selected case is unavailable');
        const response = await fetch('/api/complaint-workspace/session?case_id=' + encodeURIComponent(binding.case_id), {
            credentials: 'same-origin',
            headers: {
                'x-case-id': binding.case_id,
                'x-tenant-id': binding.tenant_id,
                'x-resource-id': binding.resource_id,
                'x-expected-revision': String(binding.directory_revision),
            },
        });
        const body = await response.json();
        const session = body.session || {};
        const pending = ((session.shared_interview || {}).pending_inquiry) || {};
        const answers = session.intake_answers || {};
        return {
            status: response.status,
            caseId: session.case_id || '',
            selectedCaseId: binding.case_id,
            inquiryId: pending.inquiry_id || '',
            revision: pending.revision,
            question: pending.question || '',
            history: (session.intake_history || []).length,
            partyName: answers.party_name || '',
            fromFixed: (body.adaptive_inquiry || {}).from_fixed_intake_fields,
            stored: body.stored_as_answer === true,
        };
    }""")


def test_inquiry_card_shows_the_server_question_and_unknown_uses_the_mediator(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    seeded = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, seeded["inquiry_id"])
        shown = _card(page)
        assert shown["source"] == "shared_mediator"
        assert shown["fromFixedIntake"] == "false"
        assert shown["storesAnswer"] == "false"
        assert shown["question"] == seeded["question"]
        assert shown["revision"] == str(seeded["revision"])
        assert f"Revision {seeded['revision']}" == shown["revisionText"]
        assert seeded["why"] and shown["why"] == seeded["why"]
        assert seeded["factual"] in shown["gaps"][0]
        assert shown["requirements"][0]["text"] == (seeded["requirement"] or "unknown")
        assert [item["action"] for item in shown["actions"]] == ["answer", "unknown", "defer", "why", "status"]
        assert shown["replacesInterview"] == "false"
        assert shown["genericPrompt"] not in shown["question"]
        assert shown["inquiryId"] not in shown["question"]
        page.locator("#inquiry-card-unknown").click()
        page.wait_for_function("""(inquiryId) => {
            const gap = document.getElementById('adaptive-gap-status');
            const card = document.getElementById('inquiry-card');
            return gap && gap.dataset.gapPreserved === 'true'
                && card && card.dataset.pending === 'true'
                && card.dataset.inquiryId.startsWith('inq-')
                && card.dataset.inquiryId !== inquiryId
                && card.dataset.fromFixedIntake === 'false';
        }""", arg=seeded["inquiry_id"])
        after = _card(page)
        server = _server_pending(page)
        assert server["status"] == 200
        assert server["caseId"] == server["selectedCaseId"] == world.case.case_id
        assert after["question"] == server["question"]
        assert after["question"] != shown["genericPrompt"]
        assert "party_name" not in after["inquiryId"]
        assert server["inquiryId"] == after["inquiryId"]
        assert server["fromFixed"] is False
        assert server["partyName"] == ""
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
    finally:
        _close(playwright, context, node, profile, observed)


def test_why_and_status_do_not_save_and_fixed_intake_does_not_replace_the_question(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    seeded = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, seeded["inquiry_id"])
        page.locator("#inquiry-card-answer").click()
        assert page.evaluate("() => document.activeElement.id") == "adaptive-answer"
        page.locator('[data-case-panel="mediator"] #adaptive-answer').click()
        page.fill("#adaptive-answer", "A draft the status action must leave in the field.")
        page.locator("#inquiry-card-why").click()
        page.wait_for_function("""() => document.getElementById('inquiry-card-note').dataset.action === 'why'""")
        assert page.get_attribute("#inquiry-card-note", "data-stored-as-answer") == "false"
        assert page.get_attribute("#inquiry-card", "data-inquiry-id") == seeded["inquiry_id"]
        assert page.get_attribute("#inquiry-card", "data-revision") == str(seeded["revision"])
        assert page.locator("#adaptive-answer").input_value() == "A draft the status action must leave in the field."
        page.locator("#inquiry-card-status").click()
        page.wait_for_function("""() => document.getElementById('inquiry-card-note').dataset.action === 'status'
            && document.getElementById('inquiry-card-note').dataset.inquiryUnchanged === 'true'""")
        assert page.get_attribute("#inquiry-card-note", "data-stored-as-answer") == "false"
        assert page.locator("#inquiry-card-question").inner_text() == seeded["question"]
        server = _server_pending(page)
        assert server["status"] == 200
        assert server["caseId"] == server["selectedCaseId"] == world.case.case_id
        assert server["inquiryId"] == seeded["inquiry_id"]
        assert server["revision"] == seeded["revision"]
        assert server["history"] == seeded["history"]
        assert server["question"] == seeded["question"]
        page.locator("#intake-show-all-button").click()
        page.fill("#intake-party_name", GENERIC_NAME)
        page.locator("#save-intake-button").click()
        page.wait_for_function("""(name) => document.getElementById('intake-party_name').value === name
            && document.getElementById('workspace-status').textContent.includes('Intake answers saved.')""", arg=GENERIC_NAME)
        persisted = _server_pending(page)
        assert persisted["status"] == 200
        assert persisted["caseId"] == world.case.case_id
        assert persisted["partyName"] == GENERIC_NAME
        assert persisted["inquiryId"] == seeded["inquiry_id"]
        assert persisted["question"] == seeded["question"]
        kept = _card(page)
        assert kept["inquiryId"] == seeded["inquiry_id"]
        assert kept["question"] == seeded["question"]
        assert kept["fromFixedIntake"] == "false"
        assert GENERIC_NAME not in kept["question"]
        assert kept["genericPrompt"] not in kept["question"]
        assert page.locator("#inquiry-card-answer").is_visible()
        assert page.locator("#inquiry-card-unknown").is_visible()
        assert page.locator("#inquiry-card-defer").is_visible()
    finally:
        _close(playwright, context, node, profile, observed)
