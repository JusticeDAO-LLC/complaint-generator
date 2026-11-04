"""Finite interview stops, pause, and cold resume stay distinct.

No actionable question, pause, cancellation, cap, saturation, an unavailable
source, and legal or evidence gaps each name an honest next action. A new
browser resumes the same encrypted question. An empty question list, a filled
form, and a completed software task are not legal sufficiency.
"""
from __future__ import annotations

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On May 3 the warehouse denied the accessible-schedule request after I asked for it in writing."


def _launch(tmp_path, monkeypatch, world, profile_name):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / profile_name
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
    return page, playwright, context, node, profile, observed, bridge


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _reopen(playwright, node, chromium_path, profile, bridge):
    context = browser._launch_context(playwright, chromium_path, profile, bridge)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    # The first browser is 1440x1000. A shorter window lets the sticky case
    # shell cover Sign in, so the cold browser keeps that same viewport.
    page.set_viewport_size({"width": 1440, "height": 1000})
    return page, context


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
        assert pending["inquiry_id"].startswith("inq-")
        assert pending["question"]
        return pending


def _sign_in(page):
    page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
    page.fill("#case-credential", "synthetic-owner-credential")
    with page.expect_response(lambda response: response.request.method == "POST"
            and response.url.endswith("/api/complaint-workspace/auth/login")):
        page.click("#case-login button[type=submit]")
    page.click("#case-list button")
    page.wait_for_function("""() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'owner'""")


def _open_mediator(page, inquiry_id, distinction="awaiting_answer"):
    page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
    page.wait_for_function("""([inquiryId, distinction]) => {
        const card = document.getElementById('inquiry-card');
        const stopping = document.getElementById('conversation-stopping');
        return card && card.dataset.pending === 'true' && card.dataset.inquiryId === inquiryId
            && stopping && stopping.dataset.distinction === distinction
            && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false';
    }""", arg=[inquiry_id, distinction])
    page.locator("#finite-interview-pause").wait_for(state="visible")


def _server_interview(page):
    return page.evaluate("""async () => {
        const binding = window.complaintCaseShell.binding();
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
        const pending = (((body.session || {}).shared_interview || {}).pending_inquiry) || {};
        const head = body.encrypted_head || {};
        const outcome = body.finite_interview_outcome || {};
        return {
            status: response.status,
            caseId: (body.session || {}).case_id || '',
            inquiryId: pending.inquiry_id || '',
            revision: pending.revision === undefined || pending.revision === null ? '' : String(pending.revision),
            question: pending.question || '',
            privateRevision: head.private_revision === undefined || head.private_revision === null ? '' : String(head.private_revision),
            stop: outcome.stop || '',
            legalSufficiency: outcome.legal_sufficiency,
            completionMeansSufficiency: outcome.interview_completion_means_legal_sufficiency,
            filingReady: outcome.filing_ready,
        };
    }""")


def _stopping(page):
    return page.evaluate("""() => {
        const panel = document.getElementById('finite-interview-outcome');
        const conversation = document.getElementById('conversation-stopping');
        const resume = document.getElementById('encrypted-interview-resume-inquiry');
        return {
            distinction: panel.dataset.distinction,
            serverStop: panel.dataset.stop,
            legalSufficiency: panel.dataset.legalSufficiency,
            legalGap: panel.dataset.legalGap,
            evidentiaryGap: panel.dataset.evidentiaryGap,
            summary: document.getElementById('finite-interview-summary').textContent,
            next: document.getElementById('finite-interview-next').textContent,
            sufficiency: document.getElementById('finite-interview-sufficiency').textContent,
            conversationDistinction: conversation.dataset.distinction,
            conversationNext: document.getElementById('conversation-stopping-next').textContent,
            inquiryId: panel.dataset.inquiryId,
            revision: panel.dataset.revision,
            question: document.getElementById('inquiry-card-question').textContent,
            resumeQuestion: resume ? resume.textContent : '',
            resumeInquiry: resume ? resume.dataset.inquiryId : '',
            resumeRevision: resume ? resume.dataset.revision : '',
            resumeSufficiency: resume ? resume.dataset.legalSufficiency : '',
        };
    }""")


def test_stops_stay_distinct_and_cold_resume_returns_the_same_question(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    pending = _seed(world)
    page, playwright, context, node, profile, observed, bridge = _launch(tmp_path, monkeypatch, world, "ux11-profile")
    cold_profile = tmp_path / "ux11-cold-profile"
    cold_context = None
    try:
        _sign_in(page)
        _open_mediator(page, pending["inquiry_id"])
        shown = _stopping(page)
        server = _server_interview(page)
        assert server["status"] == 200
        assert server["caseId"] == world.case.case_id
        assert server["inquiryId"] == pending["inquiry_id"]
        assert shown["distinction"] == "awaiting_answer"
        assert shown["conversationDistinction"] == "awaiting_answer"
        assert shown["legalSufficiency"] == "false"
        assert "not legal sufficiency" in shown["sufficiency"].lower()
        assert "current question" in shown["next"].lower()
        assert shown["question"] == pending["question"] == server["question"]
        assert page.evaluate("() => typeof window.mockApi") == "undefined"

        page.locator("#finite-interview-pause").click()
        page.wait_for_function("""() => document.getElementById('finite-interview-outcome').dataset.distinction === 'user_pause'
            && document.getElementById('finite-interview-outcome').dataset.stop === 'paused'""")
        paused = _stopping(page)
        paused_server = _server_interview(page)
        assert paused["legalSufficiency"] == "false"
        assert "same saved question" in paused["next"].lower()
        assert "stalled worker" in paused["next"].lower()
        assert paused_server["stop"] == "paused"
        assert paused_server["legalSufficiency"] is False
        assert paused_server["inquiryId"] == pending["inquiry_id"]
        assert paused_server["question"] == pending["question"]
        assert paused_server["revision"] == str(pending["revision"])
        assert paused["inquiryId"] == pending["inquiry_id"]

        context.close()
        context = None
        cold_profile.mkdir(mode=0o700)
        chromium = browser.pin_executables()[1]
        cold_page, cold_context = _reopen(playwright, node, chromium.path, cold_profile, bridge)
        _sign_in(cold_page)
        _open_mediator(cold_page, pending["inquiry_id"], "user_pause")
        cold_page.locator("#encrypted-interview-resume-button").click()
        cold_page.wait_for_function("""(inquiryId) => {
            const node = document.getElementById('encrypted-interview-resume-inquiry');
            const panel = document.getElementById('encrypted-interview-resume');
            return node && node.dataset.inquiryId === inquiryId && panel.dataset.restored === 'true'
                && panel.dataset.legalSufficiency === 'false';
        }""", arg=pending["inquiry_id"])
        resumed = _stopping(cold_page)
        resumed_server = _server_interview(cold_page)
        assert resumed["resumeInquiry"] == pending["inquiry_id"]
        assert pending["question"] in resumed["resumeQuestion"]
        assert "not legal sufficiency" in resumed["resumeQuestion"].lower()
        assert resumed["resumeRevision"] == str(pending["revision"])
        assert resumed["resumeSufficiency"] == "false"
        assert resumed_server["inquiryId"] == pending["inquiry_id"]
        assert resumed_server["question"] == pending["question"]
        assert resumed_server["revision"] == str(pending["revision"])
        assert resumed_server["privateRevision"] == paused_server["privateRevision"]
        assert resumed_server["legalSufficiency"] is False
        assert resumed_server["completionMeansSufficiency"] is False
        assert cold_page.evaluate("""() => {
            const buckets = [window.localStorage, window.sessionStorage];
            return buckets.every((bucket) => {
                if (!bucket) return true;
                for (let index = 0; index < bucket.length; index += 1) {
                    const key = bucket.key(index) || '';
                    if (/inquiry|complaint|answer|narrative/i.test(key)) return false;
                }
                return true;
            });
        }""") is True

        cold_page.locator("#intake-show-all-button").click()
        cold_page.fill("#intake-party_name", "Synthetic Neighbor")
        cold_page.locator("#save-intake-button").click()
        cold_page.wait_for_function("""() => document.getElementById('workspace-status').textContent.includes('Intake answers saved.')""")
        filled = _stopping(cold_page)
        filled_server = _server_interview(cold_page)
        assert filled["legalSufficiency"] == "false"
        assert "filled intake form" in filled["sufficiency"].lower()
        assert filled_server["inquiryId"] == pending["inquiry_id"]
        assert filled_server["question"] == pending["question"]
        assert filled_server["legalSufficiency"] is False
        assert filled_server["filingReady"] is False

        expectations = [
            ("#finite-interview-cancel", "cancellation", "cancelled", "cancelled"),
            ("#finite-interview-cap", "cap", "capped", "cap"),
            ("#finite-interview-unavailable", "unavailable_source", "unavailable", "unavailable"),
            ("#finite-interview-saturate", "saturation", "saturated", "not legal sufficiency"),
        ]
        for selector, distinction, server_stop, phrase in expectations:
            cold_page.locator(selector).click()
            cold_page.wait_for_function("""([distinction, serverStop]) => {
                const panel = document.getElementById('finite-interview-outcome');
                const conversation = document.getElementById('conversation-stopping');
                return panel.dataset.distinction === distinction
                    && panel.dataset.stop === serverStop
                    && panel.dataset.legalSufficiency === 'false'
                    && conversation.dataset.distinction === distinction;
            }""", arg=[distinction, server_stop])
            view = _stopping(cold_page)
            after = _server_interview(cold_page)
            assert phrase in view["next"].lower() or phrase in view["summary"].lower()
            assert "legal sufficiency" in view["next"].lower()
            assert view["sufficiency"].lower().count("not legal sufficiency") >= 1
            assert after["stop"] == server_stop
            assert after["legalSufficiency"] is False
            assert after["completionMeansSufficiency"] is False
            assert after["filingReady"] is False
        saturated = _stopping(cold_page)
        assert saturated["legalGap"] == "true"
        assert "legal" in saturated["next"].lower()

        painted = cold_page.evaluate("""() => {
            const view = window.complaintConversation.paintStopping({
                message: 'No further answerable intake questions are waiting.',
                legal_sufficiency: true,
                stored_as_answer: true,
                conversation_state: {is_complete: true},
                finite_interview_outcome: {stop: 'unresolved', legal_sufficiency: true, unresolved_reasons: []},
                session: {shared_interview: {pending_inquiry: null}, intake_answers: {party_name: 'Filled Example'}},
            });
            const panel = document.getElementById('finite-interview-outcome');
            return {
                classified: view.distinction,
                legalSufficiency: panel.dataset.legalSufficiency,
                filledForm: panel.dataset.filledForm,
                completedTask: panel.dataset.completedTask,
                noMoreQuestions: panel.dataset.noMoreQuestions,
                next: document.getElementById('finite-interview-next').textContent,
            };
        }""")
        assert painted["classified"] == "no_actionable_question"
        assert painted["legalSufficiency"] == "false"
        assert painted["filledForm"] == "true"
        assert painted["completedTask"] == "true"
        assert painted["noMoreQuestions"] == "true"
        assert "no further actionable question" in painted["next"].lower()
        assert "not legal sufficiency" in painted["next"].lower()
        assert "filled intake" in painted["next"].lower()
    finally:
        if cold_context is not None:
            cold_context.close()
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), str(cold_profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
