"""Chat, split context, and full workspace are views of one encrypted session.

Switching the view keeps the server session, the pending inquiry id and
revision, the selected evidence item, and the draft text. The switch reads
the existing workspace session through the SDK and does not start another
interview or store the complaint in browser storage.
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
DRAFT_TITLE = "Voucher denial complaint"
DRAFT_BODY = "The office denied the two-bedroom voucher on March 1."
UNSAVED = " The draft still includes this unsaved sentence."


def _open(tmp_path, monkeypatch, *, world=None):
    world = world or owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux07-profile"
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
        saved = evidence.json()["saved"]
        draft = client.post(
            "/api/complaint-workspace/update-draft",
            headers=headers,
            json={"title": DRAFT_TITLE, "body": DRAFT_BODY, "requested_relief": ["Restore the voucher review"]},
        )
        assert draft.status_code == 200, draft.text
        session = client.get("/api/complaint-workspace/session", headers=headers, params={"case_id": world.case.case_id})
        assert session.status_code == 200, session.text
        body = session.json()
        shared = body["session"]["shared_interview"]
        assert shared["pending_inquiry"]["inquiry_id"] == pending["inquiry_id"]
        assert shared["pending_inquiry"]["revision"] == pending["revision"]
        assert body["session"]["draft"]["body"] == DRAFT_BODY
        return pending["inquiry_id"], pending["revision"], saved["id"]


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
        const draft = document.getElementById('draft-body');
        const shell = document.getElementById('complaint-case-shell');
        return pending && pending.dataset.inquiryId === inquiryId && draft && draft.value
            && shell && shell.getAttribute('aria-busy') === 'false' && shell.dataset.sessionKey;
    }""", arg=inquiry_id)


def _view(page):
    return page.evaluate("""() => {
        const pending = document.getElementById('adaptive-pending');
        const list = document.getElementById('evidence-list');
        return {
            mode: document.documentElement.dataset.workspacePresentation,
            sessionKey: document.getElementById('complaint-case-shell').dataset.sessionKey,
            inquiryId: pending.dataset.inquiryId,
            revision: pending.dataset.revision,
            evidenceId: list.dataset.selectedId || '',
            draft: document.getElementById('draft-body').value,
            title: document.getElementById('draft-title').value,
        };
    }""")


def test_modes_keep_the_same_session_inquiry_evidence_and_draft(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, revision, evidence_id = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    posted = []
    page.on("request", lambda request: posted.append((request.method, request.url)) if request.method == "POST" else None)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        page.evaluate("""({evidenceId, draft}) => {
            const evidenceTab = document.querySelector('.tab-button[data-tab-target="evidence"]');
            if (evidenceTab) evidenceTab.click();
            const item = document.querySelector('#evidence-list button[data-evidence-id="' + evidenceId + '"]');
            if (!item) throw new Error('evidence item missing');
            item.click();
            const body = document.getElementById('draft-body');
            body.value = draft;
            body.dispatchEvent(new Event('input', {bubbles: true}));
        }""", {"evidenceId": evidence_id, "draft": DRAFT_BODY + UNSAVED})
        before_keys = page.evaluate("() => Object.keys(localStorage).sort()")
        before = _view(page)
        client_handle = page.evaluate_handle('() => window.workspaceClient')
        before_epoch = client_handle.evaluate('client => client._privacyEpoch')
        server_before = page.evaluate("""async () => (await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding())).continuity""")
        assert before["mode"] == "full-workspace"
        assert before["revision"] == str(revision)
        assert before["evidenceId"] == evidence_id
        assert before["draft"] == DRAFT_BODY + UNSAVED
        page.evaluate('() => window.complaintCaseShell.refresh()')
        refreshed = _view(page)
        assert refreshed['draft'] == before['draft'] and refreshed['evidenceId'] == evidence_id
        for mode, context_visible, intake_visible in (
            ("chat-only", False, True),
            ("chat-plus-context", True, True),
            ("full-workspace", False, True),
        ):
            page.locator('[data-presentation-mode="' + mode + '"]').click()
            label = {"chat-only": "Chat", "chat-plus-context": "Chat and context", "full-workspace": "Full workspace"}[mode]
            page.wait_for_function("""({mode, label}) => document.documentElement.dataset.workspacePresentation === mode
                && document.getElementById('complaint-presentation-status').textContent === label + ' uses the same encrypted session.'""",
                arg={"mode": mode, "label": label})
            current = _view(page)
            assert current["mode"] == mode
            assert current["sessionKey"] == before["sessionKey"]
            assert current["inquiryId"] == inquiry_id
            assert current["revision"] == str(revision)
            assert current["evidenceId"] == evidence_id
            assert current["draft"] == DRAFT_BODY + UNSAVED
            assert current["title"] == DRAFT_TITLE
            assert client_handle.evaluate('(client, expected) => client === window.workspaceClient && client._privacyEpoch === expected', before_epoch)
            assert page.locator("#complaint-presentation-context").is_visible() is context_visible
            visibility = page.evaluate("""() => {
                const intake = document.querySelector('[data-tab-panel="intake"]');
                return {mode: document.documentElement.dataset.workspacePresentation,
                    display: getComputedStyle(intake).display, hidden: intake.hidden,
                    active: intake.classList.contains('is-active'),
                    activeTabs: Array.from(document.querySelectorAll('[data-tab-panel].is-active')).map(node => node.dataset.tabPanel)};
            }""")
            assert page.locator("[data-tab-panel='intake']").is_visible() is intake_visible, visibility
            if mode != "full-workspace":
                assert page.locator("[data-tab-panel='draft']").is_hidden()
                assert page.locator("[data-tab-panel='evidence']").is_hidden()
            if mode == "chat-plus-context":
                context_text = page.locator("#complaint-presentation-context").inner_text()
                assert inquiry_id in context_text
                assert str(revision) in context_text
                assert EVIDENCE_TITLE in context_text
                assert DRAFT_BODY + UNSAVED in context_text
        continuity = page.evaluate("""async () => {
            const read = await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding());
            return read.continuity;
        }""")
        assert continuity["transport"] == "complaint-workspace-session"
        assert continuity["inquiry_id"] == inquiry_id
        assert continuity["inquiry_revision"] == revision
        assert evidence_id in continuity["evidence_ids"]
        assert continuity["draft_body"] == DRAFT_BODY
        assert continuity["draft_title"] == DRAFT_TITLE
        assert continuity == server_before
        stored = page.evaluate("() => Object.entries(localStorage).map(([key, value]) => key + '=' + value).join('\\n')")
        assert DRAFT_BODY not in stored
        assert inquiry_id not in stored
        assert "complaint-entry-question" not in stored
        after_keys = page.evaluate("() => Object.keys(localStorage).sort()")
        assert after_keys == before_keys
        assert not any(url.endswith("/api/complaint-workspace/intake-chat") for _method, url in posted)
        focused = page.evaluate("""async () => {
            document.getElementById('adaptive-answer').focus();
            await window.complaintCaseShell.setPresentationMode('chat-only');
            return document.activeElement.id;
        }""")
        assert focused == "adaptive-answer"
    finally:
        _close(playwright, context, node, profile, observed)


def test_unknown_mode_and_locked_case_do_not_invent_a_session(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, _revision, _evidence_id = _seed(world)
    world.service.lock_private_keys()
    world.owner_keys.lock()
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        page.wait_for_function("""() => document.getElementById('complaint-entry').dataset.entry === 'missing-key'
            && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")
        refused = page.evaluate("""async () => window.complaintCaseShell.setPresentationMode('client-interview')""")
        assert refused is False
        assert page.locator("#complaint-presentation-status").inner_text() == "That workspace view is not available."
        assert page.evaluate("() => document.documentElement.dataset.workspacePresentation") == "full-workspace"
        switched = page.evaluate("""async () => window.complaintCaseShell.setPresentationMode('chat-plus-context')""")
        assert switched is True
        assert page.locator("#complaint-presentation-context").is_visible()
        context_text = page.locator("#complaint-presentation-context").inner_text()
        assert inquiry_id not in context_text
        assert DRAFT_BODY not in context_text
        assert NARRATIVE not in context_text
        assert page.locator("#complaint-entry-question").inner_text() == ""
        stored = page.evaluate("() => Object.entries(localStorage).map(([key, value]) => key + '=' + value).join('\\n')")
        assert inquiry_id not in stored
        assert DRAFT_BODY not in stored
        assert page.evaluate("() => typeof window.localComplaintStore") == "undefined"
    finally:
        _close(playwright, context, node, profile, observed)


def test_loaded_case_uses_the_actual_mcp_conversation_transport(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / 'world')
    inquiry_id, _revision, _evidence_id = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        actual = page.evaluate("""async tenant => {
            try {
                const result = await window.workspaceClient.runIntakeChatTurn(tenant, '', '', {interview_action:'status'});
                return {ok:true, result, caseContext:window.workspaceClient.caseContext};
            } catch (error) {return {ok:false, status:error.status, code:error.code, caseContext:window.workspaceClient.caseContext};}
        }""", world.case.tenant_id)
        assert actual['ok'], actual
        assert actual['result']['session']['shared_interview']['pending_inquiry']['inquiry_id'] == inquiry_id
    finally:
        _close(playwright, context, node, profile, observed)


@pytest.mark.parametrize('boundary', ['key-lock', 'logout', 'actor-change'])
def test_loaded_canonical_case_is_retired_after_actual_access_boundary(tmp_path, monkeypatch, boundary):
    world = owner_lawyer_journey_world(tmp_path / 'world')
    inquiry_id, _revision, _evidence_id = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        before = page.evaluate("""async () => {
            const read = await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding());
            return {read: read.continuity, alias: window.complaintCanonicalSession && window.complaintCanonicalSession.session.draft.body};
        }""")
        assert before['read']['inquiry_id'] == inquiry_id and before['read']['draft_body'] == DRAFT_BODY
        assert before['alias'] == DRAFT_BODY
        page.locator('[data-case-task="draft"]').click()
        page.fill('#draft-body', DRAFT_BODY + ' Unsaved before the actual access change.')
        assert page.locator('#draft-body').get_attribute('data-user-edited') == 'true'

        if boundary == 'key-lock':
            # Trusted local key-owner lifecycle; there is no browser unlock API.
            world.service.lock_private_keys()
            world.owner_keys.lock()
        else:
            changed = page.evaluate("""async (boundary) => {
                if (boundary === 'actor-change') {
                    const response = await fetch('/api/complaint-workspace/auth/login', {method:'POST', credentials:'same-origin',
                        headers:{'content-type':'application/json'}, body:JSON.stringify({credential:'synthetic-stranger-credential'})});
                    return {status:response.status, body:await response.json()};
                }
                const session = await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'});
                const auth = await session.json();
                const response = await fetch('/api/complaint-workspace/auth/logout', {method:'POST', credentials:'same-origin',
                    headers:{'x-csrf-token':auth.csrf_token || window.workspaceClient.csrfToken}});
                return {status:response.status, body:await response.json()};
            }""", boundary)
            assert changed['status'] == 200
            if boundary == 'actor-change':
                assert changed['body']['principal_id'] == world.stranger.principal_id

        with page.expect_response(lambda response: response.request.method == 'GET'
                and '/api/complaint-workspace/session?case_id=' in response.url) as refused:
            denial = page.evaluate("""async () => {
                try {
                    await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding());
                    return {resolved:true};
                } catch (error) {return {resolved:false, status:error.status, code:error.code};}
            }""")
        actual = refused.value
        assert denial['resolved'] is False and denial['status'] == actual.status
        if boundary == 'key-lock':
            assert actual.status == 503 and actual.json()['error'] in {'unlock_needed', 'key_unavailable'}
        else:
            assert actual.status in {401, 403}
        page.evaluate('() => window.complaintCaseShell.refresh()')
        page.wait_for_function("() => document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'")
        assert page.input_value('#draft-body') == ''
        assert DRAFT_BODY not in page.locator('body').inner_text()
        retired = page.evaluate("""() => ({
            aliasRetired: window.complaintCanonicalSession == null,
            aliasText: JSON.stringify(window.complaintCanonicalSession || null),
            entry: document.getElementById('complaint-entry').dataset.entry
        })""")
        assert retired['aliasRetired'] and DRAFT_BODY not in retired['aliasText'], retired
    finally:
        _close(playwright, context, node, profile, observed)


def test_title_only_dirty_draft_survives_same_verified_case_refresh(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / 'world')
    inquiry_id, _revision, _evidence_id = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        page.locator('[data-case-task="draft"]').click()
        edited = DRAFT_TITLE + ' — unsaved title only'
        page.fill('#draft-title', edited)
        assert page.input_value('#draft-body') == DRAFT_BODY
        page.evaluate('() => window.complaintCaseShell.refresh()')
        assert page.input_value('#draft-title') == edited
        assert page.input_value('#draft-body') == DRAFT_BODY
        actual = page.evaluate("""async () => (await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding())).continuity""")
        assert actual['draft_title'] == DRAFT_TITLE and actual['draft_body'] == DRAFT_BODY
    finally:
        _close(playwright, context, node, profile, observed)


@pytest.mark.parametrize('boundary', ['key-lock', 'actor-change'])
def test_mode_read_denial_retires_current_private_view_without_manual_refresh(tmp_path, monkeypatch, boundary):
    world = owner_lawyer_journey_world(tmp_path / 'world')
    inquiry_id, _revision, _evidence_id = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        control = page.evaluate("""async () => (await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding())).continuity""")
        assert control['draft_body'] == DRAFT_BODY
        page.evaluate("""() => {
            window.__observedModeFailure = null;
            const status = document.getElementById('complaint-presentation-status');
            const observer = new MutationObserver(() => {
                if (!status.textContent.startsWith('The workspace session could not')) return;
                window.__observedModeFailure = {
                    aliasRetired: window.complaintCanonicalSession == null,
                    draft: document.getElementById('draft-body').value,
                    entry: document.getElementById('complaint-entry').dataset.entry
                };
                observer.disconnect();
            });
            observer.observe(status, {subtree:true, childList:true, characterData:true});
        }""")
        if boundary == 'key-lock':
            world.service.lock_private_keys()
            world.owner_keys.lock()
        else:
            changed = page.evaluate("""async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {method:'POST',credentials:'same-origin',
                    headers:{'content-type':'application/json'}, body:JSON.stringify({credential:'synthetic-stranger-credential'})});
                return {status:response.status, body:await response.json()};
            }""")
            assert changed['status'] == 200 and changed['body']['principal_id'] == world.stranger.principal_id
        with page.expect_response(lambda response: response.request.method == 'GET'
                and '/api/complaint-workspace/session?case_id=' in response.url) as actual:
            page.locator('[data-presentation-mode="chat-plus-context"]').click()
        assert actual.value.status == (503 if boundary == 'key-lock' else 403)
        page.wait_for_function('() => window.__observedModeFailure !== null')
        observed_failure = page.evaluate('() => window.__observedModeFailure')
        assert observed_failure['aliasRetired'] and observed_failure['draft'] == '', observed_failure
        assert DRAFT_BODY not in page.locator('body').inner_text()
    finally:
        _close(playwright, context, node, profile, observed)


def test_keyboard_radio_modes_preserve_actual_case_and_unsaved_work(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / 'world')
    inquiry_id, revision, evidence_id = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        page.evaluate("""({evidenceId, body}) => {
            document.querySelector('.tab-button[data-tab-target="evidence"]').click();
            document.querySelector('#evidence-list button[data-evidence-id="' + evidenceId + '"]').click();
            const draft = document.getElementById('draft-body');
            draft.value = body;
            draft.dispatchEvent(new Event('input', {bubbles:true}));
        }""", {'evidenceId':evidence_id, 'body':DRAFT_BODY + UNSAVED})
        before = _view(page)
        continuity = page.evaluate("""async () =>
            (await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding())).continuity""")
        client = page.evaluate_handle('() => window.workspaceClient')
        epoch = client.evaluate('value => value._privacyEpoch')
        group = page.locator('#complaint-presentation-modes')
        page.locator('[data-presentation-mode="full-workspace"]').focus()
        for key, mode in [('ArrowRight','chat-only'), ('ArrowRight','chat-plus-context'),
                ('ArrowDown','full-workspace'), ('ArrowLeft','chat-plus-context'),
                ('ArrowUp','chat-only'), ('ArrowLeft','full-workspace'),
                ('Home','chat-only'), ('End','full-workspace')]:
            page.keyboard.press(key)
            page.wait_for_function("""mode =>
                document.documentElement.dataset.workspacePresentation === mode
                && document.activeElement.dataset.presentationMode === mode""", arg=mode, timeout=5000)
            current = _view(page)
            assert current == {**before, 'mode':mode}
            assert current['inquiryId'] == inquiry_id and current['revision'] == str(revision)
            assert current['evidenceId'] == evidence_id and current['draft'] == DRAFT_BODY + UNSAVED
            assert group.locator('[aria-checked="true"]').count() == 1
            assert group.locator('[tabindex="0"]').count() == 1
            assert group.locator('[aria-checked="true"][tabindex="0"]').get_attribute('data-presentation-mode') == mode
            assert client.evaluate('(value, epoch) => value === window.workspaceClient && value._privacyEpoch === epoch', epoch)
        page.keyboard.press('Tab')
        assert not page.evaluate("() => document.getElementById('complaint-presentation-modes').contains(document.activeElement)")
        page.keyboard.press('Shift+Tab')
        assert page.evaluate("() => document.activeElement.dataset.presentationMode") == 'full-workspace'
        after = page.evaluate("""async () =>
            (await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding())).continuity""")
        assert after == continuity and after['draft_body'] == DRAFT_BODY
        stored = page.evaluate("() => Object.entries(localStorage).map(pair => pair.join('=')).join('\\n')")
        assert DRAFT_BODY not in stored and inquiry_id not in stored
    finally:
        _close(playwright, context, node, profile, observed)


def test_keyboard_mode_controls_do_not_open_a_locked_case(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / 'world')
    inquiry_id, _revision, _evidence_id = _seed(world)
    world.service.lock_private_keys()
    world.owner_keys.lock()
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        page.goto(browser.SAME_ORIGIN + '/workspace', wait_until='domcontentloaded')
        page.wait_for_function("""() => document.getElementById('complaint-entry').dataset.entry === 'missing-key'
            && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")
        page.locator('[data-presentation-mode="full-workspace"]').focus()
        page.keyboard.press('ArrowLeft')
        page.wait_for_function("""() => document.documentElement.dataset.workspacePresentation === 'chat-plus-context'
            && document.activeElement.dataset.presentationMode === 'chat-plus-context'""", timeout=5000)
        assert page.locator('#complaint-presentation-status').inner_text() == 'The view changed without opening case content.'
        assert page.locator('#complaint-presentation-context').is_visible()
        assert page.locator('#complaint-entry-question').inner_text() == ''
        assert page.input_value('#draft-body') == ''
        assert DRAFT_BODY not in page.locator('body').inner_text()
        assert inquiry_id not in page.locator('#complaint-presentation-context').inner_text()
        page.keyboard.press('Space')
        assert page.evaluate("() => document.documentElement.dataset.workspacePresentation") == 'chat-plus-context'
        assert page.locator('#complaint-presentation-modes [aria-checked="true"]').count() == 1
    finally:
        _close(playwright, context, node, profile, observed)
