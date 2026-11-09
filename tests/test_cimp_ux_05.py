"""Responsive case navigation that keeps the canonical session and drops plaintext.

The browser is the pinned Chromium. HTTP is the same-origin pipe into the
composed ASGI app. Case switches go through the catalog the server already
owns. Viewport changes must not open another interview.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from integrations.private_storage import PrivateArtifactBinding, seal_private_artifact
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

DESKTOP = {"width": 1440, "height": 1000}
TABLET = {"width": 768, "height": 1024}
MOBILE = {"width": 390, "height": 844}
NARROW = {"width": 320, "height": 700}
SECRET = "ux05-rendered-draft-secret"


def _open(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux05-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    page.set_viewport_size(DESKTOP)
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
    assert login.value.status == 200
    issued = login.value.json()
    assert issued["authenticated"] is True
    page.wait_for_function("() => document.getElementById('case-auth-status').textContent.includes('Signed in')")
    return issued


def _shell_ready(page):
    page.wait_for_function("""() => window.complaintCaseShell
        && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")


def _overflow(page):
    return page.evaluate("""() => {
        const nodes = [document.documentElement, document.body, document.getElementById('complaint-case-shell'), document.getElementById('cases-main')];
        return nodes.map(node => ({id: node.id || node.nodeName, extra: node.scrollWidth - node.clientWidth}));
    }""")


def test_viewports_keep_one_interview_and_reflow_at_320(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'")
        _shell_ready(page)
        page.evaluate("""() => {
            window.__sessionPosts = 0;
            const original = window.fetch.bind(window);
            window.fetch = function (input, options) {
                const method = ((options && options.method) || (input && input.method) || 'GET').toUpperCase();
                const raw = typeof input === 'string' ? input : input.url;
                const path = new URL(raw, location.origin).pathname;
                if (method === 'POST' && path === '/api/complaint-workspace/session') window.__sessionPosts += 1;
                return original(input, options);
            };
        }""")
        identity = page.evaluate("""() => ({
            caseId: document.getElementById('complaint-case-shell-case').dataset.caseId,
            sessionKey: document.getElementById('complaint-case-shell').dataset.sessionKey || ''
        })""")
        assert identity["caseId"] == world.case.case_id
        assert identity["sessionKey"]
        posted = page.evaluate("() => window.__sessionPosts")
        for viewport, mode in ((DESKTOP, "desktop"), (TABLET, "tablet"), (MOBILE, "mobile"), (NARROW, "mobile")):
            page.set_viewport_size(viewport)
            page.evaluate("() => window.complaintCaseShell.applyViewport()")
            assert page.evaluate("() => document.documentElement.dataset.caseViewport") == mode
            assert page.evaluate("() => document.getElementById('complaint-case-shell-case').dataset.caseId") == world.case.case_id
            overflow = _overflow(page)
            assert all(item["extra"] <= 1 for item in overflow), overflow
        assert page.locator(".case-shell__task[data-tier='secondary']").first.is_hidden()
        page.locator("#complaint-case-shell-more summary").click()
        page.locator(".case-shell__task[data-case-task='facts']").click()
        assert page.locator("[data-case-panel='facts']").is_visible()
        assert page.evaluate("() => window.__sessionPosts") == posted
        again = page.evaluate("""() => ({
            caseId: document.getElementById('complaint-case-shell-case').dataset.caseId,
            sessionKey: document.getElementById('complaint-case-shell').dataset.sessionKey || ''
        })""")
        assert again == identity
        assert page.evaluate("() => window.__sessionPosts") == posted
        page.set_viewport_size(DESKTOP)
        page.evaluate("() => window.complaintCaseShell.applyViewport()")
        page.fill("#case-label", "second-catalog-case")
        page.click("#create-case button[type=submit]")
        page.wait_for_function("""() => Array.from(document.querySelectorAll('#complaint-case-shell-catalog option'))
            .some(option => option.textContent === 'second-catalog-case')""")
        page.fill("#case-draft", SECRET)
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/transient")) as saved:
            page.click("#save-draft")
        assert saved.value.status == 200
        page.evaluate("""() => {
            window.__heldSelect = {aborted: false, bodyError: null};
            const original = window.fetch.bind(window);
            let armed = true;
            window.fetch = async function (input, options) {
                const method = ((options && options.method) || 'GET').toUpperCase();
                const raw = typeof input === 'string' ? input : input.url;
                const path = new URL(raw, location.origin).pathname;
                if (armed && method === 'POST' && path.endsWith('/select')) {
                    armed = false;
                    window.__heldSelect.signal = options.signal;
                    options.signal.addEventListener('abort', () => {
                        window.__heldSelect.aborted = true;
                    }, {once: true});
                    const response = await original(input, options);
                    const json = response.json.bind(response);
                    response.json = async function () {
                        try { return await json(); }
                        catch (error) { window.__heldSelect.bodyError = error.name; throw error; }
                    };
                    await new Promise(resolve => { window.__releaseHeldSelect = resolve; });
                    return response;
                }
                return original(input, options);
            };
            window.complaintCasesSelect(document.getElementById('complaint-case-shell-case').dataset.caseId);
        }""")
        page.wait_for_function("() => typeof window.__releaseHeldSelect === 'function'")
        assert page.evaluate("() => window.__heldSelect.signal instanceof AbortSignal")
        assert page.evaluate("() => window.__heldSelect.signal.aborted") is False
        page.select_option("#complaint-case-shell-catalog", label="second-catalog-case")
        page.wait_for_function("() => window.__heldSelect.aborted && window.__heldSelect.signal.aborted")
        assert page.input_value("#case-draft") == ""
        page.evaluate("() => window.__releaseHeldSelect()")
        page.wait_for_function("() => window.__heldSelect.bodyError === 'AbortError'")
        page.wait_for_function("""() => {
            const selected = document.getElementById('complaint-case-shell-catalog');
            return selected.options[selected.selectedIndex] && selected.options[selected.selectedIndex].textContent === 'second-catalog-case';
        }""")
        _shell_ready(page)
        assert SECRET not in page.locator("#complaint-case-shell").inner_text()
        assert SECRET not in page.locator("#cases-main").inner_text()
        catalog = page.evaluate("""async () => {
            const response = await fetch('/api/cases/session', {credentials: 'same-origin'});
            return response.json();
        }""")
        labels = [item["label"] for item in catalog["cases"]]
        assert "second-catalog-case" in labels
        assert catalog["selected_case_id"] != world.case.case_id
    finally:
        _close(playwright, context, node, profile, observed)


@pytest.mark.parametrize("transition", ["actor", "case"])
def test_refresh_discovered_boundary_clears_previous_rendered_plaintext(tmp_path, monkeypatch, transition):
    """A real HTTP change elsewhere must retire this view's previous fields."""
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        issued = _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'")
        _shell_ready(page)
        page.fill("#case-draft", SECRET)
        page.fill("#gap-input", "ux05-private-gap")
        assert page.locator("#selected-case").is_visible()
        if transition == "actor":
            changed = page.evaluate("""async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: 'synthetic-stranger-credential'})
                });
                return {status: response.status, body: await response.json()};
            }""")
            assert changed["status"] == 200 and changed["body"]["principal_id"] == world.stranger.principal_id
        else:
            changed = page.evaluate("""async csrf => {
                const options = {method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json', 'x-csrf-token': csrf}};
                const created = await fetch('/api/cases', {...options, body: JSON.stringify({label: 'other-view-case'})});
                const record = await created.json();
                if (created.status !== 201) return {status: created.status, body: record};
                const selected = await fetch('/api/cases/' + encodeURIComponent(record.case_id) + '/select',
                    {...options, body: '{}'});
                return {status: selected.status, body: await selected.json()};
            }""", issued["csrf_token"])
            assert changed["status"] == 200 and changed["body"]["case_id"] != world.case.case_id
        # The HTTP operation above did not invoke this document's local
        # login/select handlers, which would have cleared the fields already.
        assert page.input_value("#case-draft") == SECRET
        assert page.input_value("#gap-input") == "ux05-private-gap"
        page.evaluate("() => window.complaintCaseShell.refresh()")
        _shell_ready(page)
        assert page.input_value("#case-draft") == ""
        assert page.input_value("#gap-input") == ""
        assert page.locator("#selected-case").is_hidden()
        assert page.locator("#selected-case-label").inner_text() == ""
        current = page.evaluate("""async () => {
            const auth = await fetch('/api/complaint-workspace/auth/session', {credentials: 'same-origin'});
            const catalog = await fetch('/api/cases/session', {credentials: 'same-origin'});
            return {auth: await auth.json(), catalog: await catalog.json()};
        }""")
        expected_actor = world.stranger.principal_id if transition == "actor" else world.owner.principal_id
        assert current["auth"]["principal_id"] == expected_actor
        assert current["catalog"]["actor_principal_id"] == expected_actor
        if transition == "case":
            assert current["catalog"]["selected_case_id"] == changed["body"]["case_id"]
    finally:
        _close(playwright, context, node, profile, observed)


def test_refresh_of_same_binding_keeps_unsaved_draft(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'")
        _shell_ready(page)
        page.fill("#case-draft", SECRET)
        page.fill("#gap-input", "ux05-current-unsaved-gap")
        page.evaluate("() => window.complaintCaseShell.refresh()")
        _shell_ready(page)
        assert page.input_value("#case-draft") == SECRET
        assert page.input_value("#gap-input") == "ux05-current-unsaved-gap"
        assert page.locator("#selected-case").is_visible()
    finally:
        _close(playwright, context, node, profile, observed)


def test_logout_lock_and_revocation_clear_rendered_plaintext(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        # Bind an actual encrypted synthetic artifact through the operator
        # fixture, then use the real membership/key-grant/content HTTP routes.
        binding = PrivateArtifactBinding(tenant_id=world.case.tenant_id, case_id=world.case.case_id,
            principal_id=world.case.tenant_id, artifact_kind="ux05-note", revision="1")
        key_id, key = world.owner_keys.provider().resolve(binding)
        envelope = seal_private_artifact(SECRET.encode(), binding=binding, key=key, key_id=key_id)
        world.assignments.bind_artifact(case_id=world.case.case_id, artifact_kind="ux05-note",
            artifact_revision="1", envelope=envelope)
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        page.wait_for_function("() => document.getElementById('selected-case').hidden === false")
        page.fill("#case-draft", SECRET)
        page.click("#case-logout")
        page.wait_for_function("""async () => {
            const response = await fetch('/api/complaint-workspace/auth/session', {credentials: 'same-origin'});
            return response.status === 401;
        }""")
        _shell_ready(page)
        assert page.input_value("#case-draft") == ""
        assert SECRET not in page.locator("body").inner_text()

        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'")
        page.fill("#case-draft", SECRET)
        world.service.lock_private_keys()
        page.evaluate("() => window.complaintCaseShell.refresh()")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-privacy').textContent.includes('Locked')")
        _shell_ready(page)
        assert page.input_value("#case-draft") == ""
        assert SECRET not in page.locator("#complaint-case-shell").inner_text()

        assert world.service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
        page.click("#case-list button")
        page.wait_for_function("() => document.getElementById('selected-case').hidden === false")
        _shell_ready(page)
        page.fill("#assignment-expires", str(world.now["t"] + 3600))
        page.click("#invite-lawyer button[type=submit]")
        page.wait_for_selector("#assignment-list [data-state='pending']")
        _sign_in(page, "synthetic-lawyer-credential")
        page.locator("#assignment-list button", has_text="Accept scope").click()
        page.wait_for_function("() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'reviewer'")
        assert page.locator("#selected-case").is_hidden()  # A reviewer has no owner catalog draft.
        with TestClient(world.app, base_url="https://testserver") as owner_client:
            login = owner_client.post("/api/complaint-workspace/auth/login", json={"credential":"synthetic-owner-credential"})
            assert login.status_code == 200
            headers = {"x-csrf-token":login.json()["csrf_token"]}
            listed = owner_client.get("/api/cases/assignments")
            assert listed.status_code == 200
            grant = next(item for item in listed.json()["assignments"] if item["state"] == "accepted")
            admitted = owner_client.post("/api/cases/assignments/" + grant["grant_id"] + "/key-grant",
                headers=headers, json={"artifact_kind":"ux05-note", "artifact_revision":"1", "idempotency_key":"ux05-admit-key"})
            assert admitted.status_code == 201 and admitted.json()["plaintext_available"] is False
            _sign_in(page, "synthetic-lawyer-credential")
            with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/content")) as opened:
                page.locator("#assignment-list button", has_text="Open content").click()
            assert opened.value.status == 200
            assert opened.value.json()["text"] == SECRET
            assert opened.value.json()["actor_is_encrypted_owner"] is False
            assert opened.value.json()["canonical_owner_principal_id"] == world.case.tenant_id
            page.wait_for_function("() => document.getElementById('assignment-content').textContent === " + repr(SECRET))
            # Hold a second real response before its body is read, revoke via
            # the actual owner route, then release it after this view refreshes.
            page.evaluate("""() => {
                const original = window.fetch.bind(window);
                let armed = true;
                window.__revokedRead = {aborted: false, bodyError: null};
                window.fetch = async function (input, options) {
                    const path = new URL(typeof input === 'string' ? input : input.url, location.origin).pathname;
                    if (armed && path.endsWith('/content') && options.method === 'POST') {
                        armed = false;
                        window.__revokedRead.signal = options.signal;
                        options.signal.addEventListener('abort', () => {window.__revokedRead.aborted = true;}, {once: true});
                        const response = await original(input, options);
                        const json = response.json.bind(response);
                        response.json = async function () {
                            try {return await json();}
                            catch (error) {window.__revokedRead.bodyError = error.name; throw error;}
                        };
                        await new Promise(resolve => {window.__releaseRevokedRead = resolve;});
                        return response;
                    }
                    return original(input, options);
                };
                Array.from(document.querySelectorAll('#assignment-list button'))
                    .find(button => button.textContent === 'Open content').click();
            }""")
            page.wait_for_function("() => typeof window.__releaseRevokedRead === 'function'")
            removed = owner_client.post("/api/cases/assignments/" + grant["grant_id"] + "/remove",
                headers=headers, json={"expected_version":grant["version"]})
            assert removed.status_code == 200 and removed.json()["state"] == "removed"
            page.evaluate("() => window.complaintCaseShell.refresh()")
            page.wait_for_function("() => document.getElementById('complaint-case-shell-actor').dataset.relationship !== 'reviewer'")
            _shell_ready(page)
            assert page.locator("#assignment-content").inner_text() == ""
            assert page.evaluate("() => window.__revokedRead.aborted && window.__revokedRead.signal.aborted") is True
            page.evaluate("() => window.__releaseRevokedRead()")
            page.wait_for_function("() => window.__revokedRead.bodyError === 'AbortError'")
            assert page.locator("#assignment-content").inner_text() == ""
            assert page.input_value("#case-draft") == ""
            assert SECRET not in page.locator("#complaint-case-shell").inner_text()
            assert "Assigned case" not in page.locator("#complaint-case-shell-case").inner_text()
    finally:
        _close(playwright, context, node, profile, observed)
