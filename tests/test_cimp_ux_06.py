"""First-run, sign-in, actual key-access checks, and cold-resume entry.

A new person can see how to name a complaint. An existing owner selects the
real case and, after a trusted local key owner unlocks outside the GUI, resumes
the saved server question. A denied sign-in, a missing key, and an unavailable catalog stay
explicit. The browser does not invent a case, show a ready badge, rebuild the
question from storage, or hide a consent grant.
"""
from __future__ import annotations

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On March 1 the office denied the request for the two-bedroom voucher."
CACHE_QUESTION = "browser-cache-question-ux06-must-not-appear"


def _open(tmp_path, monkeypatch, *, world=None):
    world = world or owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux06-profile"
    profile.mkdir(mode=0o700)
    observed = set()

    def verify_startup_cleanup():
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup['cleaned'] and cleanup['remaining_pids'] == [], 'failed startup left owned browser processes'

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


def _sign_in(page, credential):
    page.fill("#case-credential", credential)
    with page.expect_response(lambda response: response.request.method == "POST"
            and response.url.endswith("/api/complaint-workspace/auth/login")) as login:
        page.click("#case-login button[type=submit]")
    response = login.value
    if response.status == 200:
        page.wait_for_function("principal => document.getElementById('complaint-case-shell-actor').dataset.principalId === principal",
            arg=response.json()["principal_id"])
    else:
        page.wait_for_function("() => document.getElementById('case-error').textContent === 'authentication_failed'")
    return response


def _shell_ready(page):
    page.wait_for_function("""() => window.complaintCaseShell
        && document.getElementById('complaint-entry')
        && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")


def _pending_question(world):
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
        assert question and question != CACHE_QUESTION
        assert NARRATIVE not in question
        consent = client.get("/api/cases/" + world.case.case_id + "/processing-consent")
        assert consent.status_code == 200
        return pending["inquiry_id"], question, started.json()["session"], consent.json()


def _lock(world):
    world.service.lock_private_keys()
    world.owner_keys.lock()


def _unlock_by_trusted_local_owner(world):
    """Explicit external lifecycle: this is never a browser unlock operation."""
    assert world.service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
    world.owner_keys.unlock_passphrase(PASSPHRASE)


def test_new_user_can_identify_and_begin_a_complaint(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        _shell_ready(page)
        assert page.locator("#workspace-begin-complaint").inner_text() == "Begin a complaint"
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "first-run"
        assert page.locator("#complaint-entry").get_attribute("data-ready-badge") == "false"
        assert page.locator("#complaint-entry input[type=password]").count() == 0
        assert "does not grant remote processing" in page.locator("#complaint-entry-consent").inner_text()
        page.click("#workspace-begin-complaint")
        page.wait_for_url("**/cases#create-case")
        assert page.locator("#case-label").is_visible()
        _shell_ready(page)
        denied = _sign_in(page, "not-a-real-credential")
        assert denied.status == 401
        assert page.locator("#case-error").inner_text() == "authentication_failed"
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "denied"
        assert page.locator("#complaint-entry").get_attribute("data-ready-badge") == "false"
        assert "No replacement case" in page.locator("#complaint-entry-boundary").inner_text()
        assert page.locator("#case-list").get_attribute("data-state") == "error"
        issued = _sign_in(page, "synthetic-stranger-credential")
        assert issued.status == 200
        _shell_ready(page)
        page.wait_for_function("() => document.getElementById('complaint-entry').dataset.entry === 'first-run'")
        page.click("#complaint-entry-begin")
        assert page.evaluate("() => document.activeElement.id") == "case-label"
        page.fill("#case-label", "First complaint from the new account")
        page.click("#create-case button[type=submit]")
        page.wait_for_function("""() => Array.from(document.querySelectorAll('#case-list button'))
            .some(button => button.textContent.includes('First complaint from the new account'))""")
        labels = page.locator("#case-list button").all_inner_texts()
        assert labels == ["First complaint from the new account"]
        assert page.locator("#case-list").get_attribute("data-ready-badge") == "false"
        assert world.case.case_id not in " ".join(labels)
    finally:
        _close(playwright, context, node, profile, observed)


def test_local_owner_lifecycle_then_real_gui_probe_resumes_cold_persisted_inquiry(tmp_path, monkeypatch):
    seed = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, question, saved, consent_before = _pending_question(seed)
    _lock(seed)
    # New workspace and wallet objects read the same encrypted roots. Neither
    # a decrypted session nor a rendered response is copied to this reader.
    cold = owner_lawyer_journey_world(tmp_path / "world", previous=seed)
    assert cold.service is not seed.service and cold.owner_keys is not seed.owner_keys
    _lock(cold)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=cold)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert opened.status == 200
        page.evaluate("""(cached) => {
            localStorage.setItem('complaint-entry-question', cached);
            sessionStorage.setItem('complaint-entry-question', cached);
            localStorage.setItem('complaint-entry-passphrase', 'obsolete-fixture-secret');
            sessionStorage.setItem('complaint-entry-passphrase', 'obsolete-fixture-secret');
            localStorage.setItem('ux06-unrelated-setting', 'preserved');
            sessionStorage.setItem('ux06-unrelated-setting', 'preserved');
        }""", CACHE_QUESTION)
        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        _shell_ready(page)
        page.wait_for_function("""(caseId) => document.getElementById('complaint-entry').dataset.entry === 'missing-key'
            && document.getElementById('complaint-entry').dataset.caseId === caseId""", arg=world.case.case_id)
        entry_text = page.locator("#complaint-entry").inner_text()
        assert question not in entry_text
        assert CACHE_QUESTION not in entry_text
        assert page.locator("#complaint-case-shell").get_attribute("data-ready-badge") == "false"
        assert page.locator("#complaint-case-shell").get_attribute("data-state") == "missing-key"
        assert page.locator("#case-context").get_attribute("data-state") == "locked"
        before = [item["case_id"] for item in page.evaluate("""async () => {
            const response = await fetch('/api/cases', {credentials: 'same-origin', headers: {accept: 'application/json'}});
            const body = await response.json();
            return body.cases || [];
        }""")]
        posted = []
        page.on("request", lambda request: posted.append((request.method, request.url, request.post_data or "")))
        assert page.locator("#complaint-entry input[type=password]").count() == 0
        with page.expect_response(lambda response: response.request.method == "GET"
                and '/api/complaint-workspace/session?case_id=' in response.url) as locked:
            page.click("#complaint-entry-check-key")
        assert locked.value.status == 503
        assert locked.value.json()["error"] == "unlock_needed"
        assert locked.value.json()["session_readable"] is False
        assert locked.value.request.header_value("x-case-id") == world.case.case_id
        assert locked.value.request.header_value("x-tenant-id") == world.case.tenant_id
        page.wait_for_function("""() => {
            const result = document.getElementById('complaint-entry-key-result').textContent;
            return result.includes('still locked') && result.includes('authorized local key owner');
        }""")
        assert all(PASSPHRASE not in body for _method, _url, body in posted)
        assert CACHE_QUESTION not in page.evaluate("() => JSON.stringify({...localStorage, ...sessionStorage})")
        assert page.evaluate("() => [localStorage.getItem('complaint-entry-passphrase'), sessionStorage.getItem('complaint-entry-passphrase')]") == [None, None]
        assert page.evaluate("() => [localStorage.getItem('ux06-unrelated-setting'), sessionStorage.getItem('ux06-unrelated-setting')]") == ['preserved', 'preserved']
        still = [item["case_id"] for item in page.evaluate("""async () => {
            const response = await fetch('/api/cases', {credentials: 'same-origin', headers: {accept: 'application/json'}});
            const body = await response.json();
            return body.cases || [];
        }""")]
        assert still == before
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "missing-key"
        _unlock_by_trusted_local_owner(world)
        with page.expect_response(lambda response: response.request.method == "GET"
                and '/api/complaint-workspace/session?case_id=' in response.url) as opened:
            page.click("#complaint-entry-check-key")
        assert opened.value.status == 200
        resumed = opened.value.json()["session"]
        assert resumed["shared_interview"]["pending_inquiry"] == saved["shared_interview"]["pending_inquiry"]
        assert resumed.get("draft") == saved.get("draft")
        assert resumed["shared_interview"]["knowledge_graph"] == saved["shared_interview"]["knowledge_graph"]
        page.wait_for_function("""(inquiryId) => {
            const entry = document.getElementById('complaint-entry');
            const question = document.getElementById('complaint-entry-question');
            return entry.dataset.entry === 'resume' && question.dataset.inquiryId === inquiryId && !question.hidden;
        }""", arg=str(inquiry_id))
        assert page.locator("#complaint-entry-question").inner_text() == question
        assert CACHE_QUESTION not in page.locator("#complaint-case-shell").inner_text()
        assert page.locator("#complaint-entry").get_attribute("data-consent") == "not-modified"
        consent_after = page.evaluate("""async caseId => {
            const response = await fetch('/api/cases/' + encodeURIComponent(caseId) + '/processing-consent', {credentials:'same-origin'});
            return {status:response.status, body:await response.json()};
        }""", world.case.case_id)
        assert consent_after["status"] == 200 and consent_after["body"] == consent_before
        consent_posts = [item for item in posted if "processing-consent" in item[1] and item[0] == "POST"]
        assert consent_posts == []
        page.locator("[data-case-panel='mediator']").wait_for(state="visible")
        assert question in page.locator("[data-case-panel='mediator']").inner_text()
    finally:
        _close(playwright, context, node, profile, observed)


def test_unavailable_catalog_is_explicit_and_opens_no_replacement_case(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    catalog = world.app.state.case_catalog
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert opened.status == 200
        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        _shell_ready(page)
        page.wait_for_function("() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'")
        case_id = page.locator("#complaint-case-shell-case").get_attribute("data-case-id")
        assert case_id == world.case.case_id
        before = world.cases.list_cases(actor_principal_id=world.owner.principal_id)
        world.app.state.case_catalog = None
        with page.expect_response(lambda response: response.request.method == 'GET'
                and response.url.endswith('/api/cases/session')) as unavailable:
            page.evaluate("() => window.complaintCaseShell.refresh()")
        assert unavailable.value.status == 503 and unavailable.value.json()['error'] == 'case_catalog_unavailable'
        page.wait_for_function("() => document.getElementById('complaint-entry').dataset.entry === 'unavailable'")
        assert page.locator("#complaint-case-shell").get_attribute("data-ready-badge") == "false"
        assert page.locator("#complaint-case-shell").get_attribute("data-state") != "ready"
        assert page.locator("#complaint-entry-question").is_hidden()
        assert "unavailable" in page.locator("#complaint-entry-title").inner_text().lower()
        assert page.locator("#complaint-case-shell-case").get_attribute("data-bound") == "empty"
        listed = page.locator("#case-list button").all_inner_texts()
        assert listed == []
        assert world.cases.list_cases(actor_principal_id=world.owner.principal_id) == before
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
    finally:
        world.app.state.case_catalog = catalog
        _close(playwright, context, node, profile, observed)


@pytest.mark.parametrize('race', ['request-pending', 'json-completed'])
def test_actual_catalog_failure_after_actor_change_scrubs_and_fences_previous_view(tmp_path, monkeypatch, race):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    catalog = world.app.state.case_catalog
    pending = {}
    failed_requests = []
    try:
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert _sign_in(page, "synthetic-owner-credential").status == 200
        page.wait_for_function("principal => document.getElementById('complaint-case-shell-actor').dataset.principalId === principal",
            arg=world.owner.principal_id)
        page.click("#case-list button")
        _shell_ready(page)
        page.wait_for_function("() => !document.getElementById('selected-case').hidden")
        page.fill("#case-draft", "ux06-previous-owner-private-draft")
        page.fill("#gap-input", "ux06-previous-owner-private-gap")
        page.on('requestfailed', lambda request: failed_requests.append(
            {'url': request.url, 'error': request.failure}) if request.url.endswith('/transient') else None)
        if race == 'request-pending':
            # Hold a real intercepted HTTP request before forwarding it. The
            # browser, rather than this route, must produce the abort failure.
            def hold_actual_request(route):
                pending['route'] = route
                page.evaluate('() => {window.__ux06PendingRoute = true;}')

            page.route('**/api/cases/*/transient', hold_actual_request)
        # The other mode fully reads actual server JSON, then defers only its
        # return to the caller. A buffered body is never claimed to be aborted.
        page.evaluate("""race => {
            const original = window.fetch.bind(window);
            let armed = true;
            window.__ux06OldRead = {aborted: false, fetchError: null, jsonError: null,
                responseReceived: false, jsonRead: false, returned: false};
            window.fetch = async function (input, options) {
                const path = new URL(typeof input === 'string' ? input : input.url, location.origin).pathname;
                if (armed && path.endsWith('/transient') && options.method === 'POST') {
                    armed = false;
                    window.__ux06OldRead.signal = options.signal;
                    options.signal.addEventListener('abort', () => {window.__ux06OldRead.aborted = true;}, {once:true});
                    let response;
                    try {response = await original(input, options);}
                    catch (error) {window.__ux06OldRead.fetchError = error.name; throw error;}
                    window.__ux06OldRead.responseReceived = true;
                    window.__ux06OldRead.responseStatus = response.status;
                    if (race === 'request-pending') return response;
                    const json = response.json.bind(response);
                    response.json = async function () {
                        let payload;
                        try {payload = await json();}
                        catch (error) {window.__ux06OldRead.jsonError = error.name; throw error;}
                        window.__ux06OldRead.jsonRead = true;
                        await new Promise(resolve => {window.__ux06Release = resolve;});
                        window.__ux06OldRead.returned = true;
                        return payload;
                    };
                    return response;
                }
                return original(input, options);
            };
            document.getElementById('save-draft').click();
        }""", race)
        if race == 'request-pending':
            page.wait_for_function('() => window.__ux06PendingRoute === true')
        else:
            page.wait_for_function("() => window.__ux06OldRead.jsonRead && typeof window.__ux06Release === 'function'")
            assert page.evaluate('() => window.__ux06OldRead.responseStatus') == 200
        assert page.evaluate('() => window.__ux06OldRead.signal instanceof AbortSignal && !window.__ux06OldRead.signal.aborted')
        changed = page.evaluate("""async () => {
            const response = await fetch('/api/complaint-workspace/auth/login', {method:'POST',credentials:'same-origin',
                headers:{'content-type':'application/json'},body:JSON.stringify({credential:'synthetic-stranger-credential'})});
            return {status:response.status, body:await response.json()};
        }""")
        assert changed["status"] == 200 and changed["body"]["principal_id"] == world.stranger.principal_id
        world.app.state.case_catalog = None  # Real missing capability in this private app only.
        with page.expect_response(lambda response: response.request.method == "GET"
                and response.url.endswith("/api/cases/session")) as unavailable:
            page.evaluate("() => window.complaintCaseShell.refresh()")
        assert unavailable.value.status == 503
        assert unavailable.value.json()["error"] == "case_catalog_unavailable"
        _shell_ready(page)
        assert page.input_value("#case-draft") == ""
        assert page.input_value("#gap-input") == ""
        assert page.locator("#selected-case").is_hidden()
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "unavailable"
        assert page.evaluate("() => window.__ux06OldRead.aborted && window.__ux06OldRead.signal.aborted") is True
        if race == 'request-pending':
            page.wait_for_function("() => window.__ux06OldRead.fetchError === 'AbortError'")
            assert page.evaluate('() => window.__ux06OldRead.responseReceived') is False
            assert len(failed_requests) == 1 and failed_requests[0]['error'] == 'net::ERR_ABORTED'
            pending['route'].fallback()
            pending['released'] = True
        else:
            assert page.evaluate('() => window.__ux06OldRead.jsonError') is None
            page.evaluate('() => window.__ux06Release()')
            page.wait_for_function('() => window.__ux06OldRead.returned === true')
            assert failed_requests == []
            assert page.evaluate('() => window.__ux06OldRead.jsonRead && window.__ux06OldRead.jsonError === null')
        assert page.input_value('#case-draft') == ''
        assert page.input_value('#gap-input') == ''
        assert page.locator('#selected-case').is_hidden()
        assert "ux06-previous-owner" not in page.locator("body").inner_text()
        actual = page.evaluate("""async () => {
            const response = await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'});
            return {status:response.status, body:await response.json()};
        }""")
        assert actual["status"] == 200 and actual["body"]["principal_id"] == world.stranger.principal_id
    finally:
        world.app.state.case_catalog = catalog
        if 'route' in pending and not pending.get('released'):
            pending['route'].fallback()
        page.evaluate("() => {if (window.__ux06Release) window.__ux06Release();}")
        _close(playwright, context, node, profile, observed)


def test_existing_case_without_pending_is_continue_instead_of_first_run(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert _sign_in(page, "synthetic-owner-credential").status == 200
        page.wait_for_function("principal => document.getElementById('complaint-case-shell-actor').dataset.principalId === principal",
            arg=world.owner.principal_id)
        page.click("#case-list button")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'")
        _shell_ready(page)
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "continue"
        assert page.locator("#complaint-entry-begin").is_hidden()
        assert page.locator("#complaint-entry-title").inner_text() == "Continue this case"
        assert page.locator("#complaint-case-shell-case").get_attribute("data-case-id") == world.case.case_id
    finally:
        _close(playwright, context, node, profile, observed)


def test_real_private_session_unavailable_retires_same_owner_case_fields(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    registry = world.app.state.case_handlers
    key = (world.case.tenant_id, world.case.case_id, world.case.resource_id)
    binding = None
    try:
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert _sign_in(page, "synthetic-owner-credential").status == 200
        page.click("#case-list button")
        page.wait_for_function("() => !document.getElementById('selected-case').hidden")
        _shell_ready(page)
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "continue"
        page.fill("#case-draft", "ux06-unverified-private-session-draft")
        page.fill("#gap-input", "ux06-unverified-private-session-gap")
        # Withdraw the actual operator binding only in this owned app. The
        # unchanged middleware produces the real non-key session-read failure.
        binding = registry._bindings.pop(key)
        with page.expect_response(lambda response: response.request.method == "GET"
                and '/api/complaint-workspace/session?case_id=' in response.url) as unavailable:
            page.evaluate("() => window.complaintCaseShell.refresh()")
        assert unavailable.value.status == 503
        assert unavailable.value.json()["error"] == "case_handler_unavailable"
        _shell_ready(page)
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "unavailable"
        assert page.input_value("#case-draft") == ""
        assert page.input_value("#gap-input") == ""
        assert page.locator("#selected-case").is_hidden()
        catalog = page.evaluate("""async () => {
            const response = await fetch('/api/cases/session', {credentials:'same-origin'});
            return {status:response.status, body:await response.json()};
        }""")
        assert catalog["status"] == 200
        assert catalog["body"]["actor_principal_id"] == world.owner.principal_id
        assert catalog["body"]["selected_case_id"] == world.case.case_id
        assert page.locator("#complaint-case-shell-case").get_attribute("data-case-id") == world.case.case_id
    finally:
        if binding is not None:
            registry._bindings[key] = binding
        _close(playwright, context, node, profile, observed)
