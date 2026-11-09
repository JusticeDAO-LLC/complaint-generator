"""Shared case shell for the owner and an assigned reviewer.

The browser is the pinned Chromium. HTTP is the same-origin pipe into the
composed ASGI app. The shell reads the live session, case catalog, and
assignments. It does not invent a second interview record.
"""
from __future__ import annotations

import hashlib

import pytest

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import NARRATIVE, PASSPHRASE
from integrations.private_storage import ENVELOPE_MAGIC

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

DESKTOP = {"width": 1440, "height": 1000}
TASKS = ["Overview", "Mediator", "Evidence", "Facts and timeline", "Legal requirements", "Draft", "Team/messages"]


def _open(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux04-profile"
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
    page.wait_for_function("principal => document.getElementById('complaint-case-shell-actor').dataset.principalId === principal",
        arg=issued["principal_id"])
    return issued


def _shell(page):
    page.wait_for_function("""() => window.complaintCaseShell && document.getElementById('complaint-case-shell-next')
        && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")
    return page.evaluate("() => window.complaintCaseShell.snapshot()")


def test_owner_and_reviewer_share_the_case_shell(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        signed_out = _shell(page)
        assert signed_out["case"] == "No case selected"
        assert signed_out["actor"] == "Not signed in"
        assert signed_out["next"] == "Sign in"
        assert signed_out["nextCount"] == 1

        issued = _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        page.wait_for_function(
            """() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'
                && document.getElementById('complaint-case-shell-actor').dataset.relationship === 'owner'"""
        )
        owner = _shell(page)
        assert owner["case"] == "owner-lawyer-journey"
        assert owner["caseId"] == world.case.case_id
        assert owner["actor"] == "Owner"
        assert owner["principalId"] == world.owner.principal_id
        assert owner["privacy"] == "Local private is the default"
        assert owner["stage"]
        assert owner["nextCount"] == 1
        nav = page.eval_on_selector_all(
            "#complaint-case-shell-nav button",
            "nodes => nodes.map(node => node.textContent.trim())",
        )
        assert nav == TASKS
        for label in TASKS:
            page.get_by_role("button", name=label, exact=True).click()
            slug = {
                "Overview": "overview",
                "Mediator": "mediator",
                "Evidence": "evidence",
                "Facts and timeline": "facts",
                "Legal requirements": "legal",
                "Draft": "draft",
                "Team/messages": "team",
            }[label]
            visible = page.evaluate(
                """name => {
                    const panels = Array.from(document.querySelectorAll('[data-case-panel]'));
                    return panels.filter(panel => !panel.hidden).map(panel => panel.getAttribute('data-case-panel'));
                }""",
                slug,
            )
            assert visible == [slug]

        page.fill("#assignment-expires", str(world.now["t"] + 3600))
        page.click("#invite-lawyer button[type=submit]")
        page.wait_for_selector("#assignment-list [data-state='pending']")

        workspace = page.goto(
            browser.SAME_ORIGIN + "/workspace?user_id=" + world.case.tenant_id,
            wait_until="domcontentloaded",
        )
        assert workspace.status == 200
        page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
        page.evaluate(
            """async data => {
                window.workspaceClient.setBrowserSession(data.issued);
                window.workspaceClient.setCaseContext(data.case);
                await window.workspaceClient.bootstrapWorkspace(data.case.tenant_id);
            }""",
            {"issued": issued, "case": {
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "revision": world.case.revision,
            }},
        )
        page.evaluate("() => window.complaintCaseShell.refresh()")
        page.wait_for_function(
            """() => document.getElementById('complaint-case-shell-case').dataset.caseId
                && document.getElementById('complaint-case-shell-stage').textContent !== 'Sign-in required'"""
        )
        owner_workspace = _shell(page)
        assert owner_workspace["case"] == owner["case"]
        assert owner_workspace["caseId"] == owner["caseId"]
        assert owner_workspace["actor"] == owner["actor"]
        assert owner_workspace["principalId"] == owner["principalId"]
        assert owner_workspace["privacy"] == owner["privacy"]
        assert owner_workspace["stage"] == owner["stage"]
        assert owner_workspace["next"] == owner["next"]
        assert page.locator("#workspace-case-context-value").inner_text().strip() == owner["case"]
        assert page.locator("[data-tab-target='integrations']").is_visible() is False
        tools = page.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/mcp/tools', {credentials: 'same-origin'});
                return {status: response.status, type: response.headers.get('content-type') || ''};
            }"""
        )
        assert tools["status"] != 404
        assert "json" in tools["type"] or tools["status"] in {401, 403}

        page.fill("#adaptive-narrative", NARRATIVE)
        page.click("#adaptive-enter-narrative")
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        page.evaluate("() => window.complaintCaseShell.refresh()")
        assert _shell(page)["stage"] == "Mediator question"
        sealed = {path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in world.service._session_dir.rglob("*")
            if path.is_file() and path.read_bytes().startswith(ENVELOPE_MAGIC)}
        assert sealed
        # These are actual operator key owners, as in the established shared
        # owner/recipient tests. No DOM field or browser boolean locks a key.
        world.owner_keys.lock()
        assert world.service.lock_private_keys()["unlocked"] is False
        unavailable = page.evaluate("""async data => {
            const response = await fetch('/api/complaint-workspace/session?case_id=' + encodeURIComponent(data.caseId), {credentials: 'same-origin',
                headers: {'x-tenant-id': data.tenant, 'x-case-id': data.caseId, 'x-resource-id': data.resource, 'x-expected-revision': String(data.revision)}});
            return {status: response.status, body: await response.json()};
        }""", {"tenant": world.case.tenant_id, "caseId": world.case.case_id, "resource": world.case.resource_id, "revision": world.case.revision})
        assert unavailable["status"] == 503 and unavailable["body"]["error"] == "unlock_needed"
        assert NARRATIVE not in str(unavailable["body"])
        page.evaluate("() => window.complaintCaseShell.refresh()")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-stage').textContent === 'Locked'")
        locked = _shell(page)
        assert locked["privacy"] == "Locked until the private key is available"
        assert locked["next"] == "Check private key access"
        assert locked["caseId"] == world.case.case_id
        assert page.locator("#adaptive-narrative").input_value() == ""
        assert page.get_attribute("#adaptive-pending", "data-pending") != "true"
        assert "Current question:" not in page.locator("#complaint-case-shell-panels").inner_text()
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in sealed.items())
        assert world.service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
        world.owner_keys.unlock_passphrase(PASSPHRASE)

        page.goto(browser.SAME_ORIGIN + "/workspace?shell_mode=operator", wait_until="domcontentloaded")
        page.wait_for_function("() => document.body.dataset.caseTaskFlow === 'operator'")
        assert page.locator("[data-tab-target='integrations']").is_visible() is True

        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        _sign_in(page, "synthetic-lawyer-credential")
        page.wait_for_function(
            """() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'reviewer'
                && document.getElementById('complaint-case-shell-stage').textContent === 'Assignment pending'"""
        )
        reviewer = _shell(page)
        assert reviewer["caseId"] == world.case.case_id
        assert reviewer["actor"] == "Assigned reviewer"
        assert reviewer["principalId"] == world.lawyer.principal_id
        assert reviewer["case"] == "Assigned case"
        assert "grant" not in reviewer["case"].lower()
        assert reviewer["next"] == "Accept the assignment"
        assert reviewer["privacy"].startswith("Locked")
        page.click("#complaint-case-shell-next")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-stage').textContent === 'Assigned review'")
        accepted = _shell(page)
        assert accepted["caseId"] == world.case.case_id
        assert accepted["actor"] == "Assigned reviewer"
        assert accepted["principalId"] == world.lawyer.principal_id
        assert accepted["next"] == "Open the assigned review"
        assert accepted["nextCount"] == 1

        _sign_in(page, "synthetic-stranger-credential")
        page.wait_for_function(
            """() => document.getElementById('complaint-case-shell-actor').textContent.trim() === 'Signed in'"""
        )
        stranger = _shell(page)
        assert stranger["case"] == "No case selected"
        assert stranger["caseId"] == ""
        assert stranger["principalId"] == world.stranger.principal_id
        assert "owner-lawyer-journey" not in page.locator("#complaint-case-shell").inner_text()
        denied = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert denied.status == 200
        page.evaluate(
            """payload => window.workspaceClient.setCaseContext(payload)""",
            {
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "revision": world.case.revision,
            },
        )
        page.evaluate("() => window.complaintCaseShell.refresh()")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-actor').dataset.principalId")
        spoofed = _shell(page)
        assert spoofed["case"] == "No case selected"
        assert spoofed["caseId"] == ""
        assert spoofed["principalId"] == world.stranger.principal_id
        assert page.locator("#workspace-case-context-value").inner_text().strip() != "owner-lawyer-journey"
    finally:
        _close(playwright, context, node, profile, observed)


def test_shell_refuses_a_case_label_from_the_address_bar(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        opened = page.goto(
            browser.SAME_ORIGIN + "/cases?case_id=" + world.case.case_id + "&label=owner-lawyer-journey",
            wait_until="domcontentloaded",
        )
        assert opened.status == 200
        snapshot = _shell(page)
        assert snapshot["case"] == "No case selected"
        assert snapshot["actor"] == "Not signed in"
        assert world.case.case_id not in page.locator("#complaint-case-shell-case").inner_text()
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
    finally:
        _close(playwright, context, node, profile, observed)


def test_shell_retires_an_actual_late_owner_response_during_lawyer_login(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-case').dataset.caseId")
        assert _shell(page)["principalId"] == world.owner.principal_id
        page.fill("#assignment-expires", str(world.now["t"] + 3600))
        page.click("#invite-lawyer button[type=submit]")
        page.wait_for_selector("#assignment-list [data-state='pending']")
        assert _shell(page)["caseId"] == world.case.case_id

        # Delay delivery of one genuine server response after its real ASGI
        # handler ran. No response, principal, cookie, or role is fabricated.
        page.evaluate("""() => {
            const original = window.fetch.bind(window);
            let hold = true;
            window.__ux04HeldPrincipal = null;
            window.__ux04OriginalFetch = original;
            window.fetch = async function (input, options) {
                const response = await original(input, options);
                const path = new URL(typeof input === 'string' ? input : input.url, location.origin).pathname;
                if (hold && path === '/api/complaint-workspace/auth/session') {
                    hold = false;
                    const actual = await response.clone().json();
                    window.__ux04HeldPrincipal = actual.principal_id;
                    await new Promise(resolve => { window.__ux04Release = resolve; });
                }
                return response;
            };
            document.getElementById('case-login').addEventListener('submit', () => {
                window.__ux04LoginBoundary = window.complaintCaseShell.snapshot();
            });
            window.__ux04OldRefresh = window.complaintCaseShell.refresh();
        }""")
        page.wait_for_function("() => window.__ux04HeldPrincipal !== null")
        assert page.evaluate("() => window.__ux04HeldPrincipal") == world.owner.principal_id
        lawyer = _sign_in(page, "synthetic-lawyer-credential")
        boundary = page.evaluate("() => window.__ux04LoginBoundary")
        assert boundary["caseId"] == "" and boundary["principalId"] == ""
        page.wait_for_function("() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'reviewer'")
        assert _shell(page)["principalId"] == world.lawyer.principal_id
        page.evaluate("""async () => {
            window.__ux04Release();
            await window.__ux04OldRefresh;
            window.fetch = window.__ux04OriginalFetch;
        }""")
        reviewer = _shell(page)
        assert reviewer["principalId"] == lawyer["principal_id"] == world.lawyer.principal_id
        assert reviewer["caseId"] == world.case.case_id
        assert reviewer["actor"] == "Assigned reviewer"
        assert "owner-lawyer-journey" not in page.locator("#complaint-case-shell").inner_text()
        actual = page.evaluate("""async () => {
            const response = await fetch('/api/complaint-workspace/auth/session', {credentials: 'same-origin'});
            return {status: response.status, body: await response.json()};
        }""")
        assert actual["status"] == 200 and actual["body"]["principal_id"] == reviewer["principalId"]
        logged_out = page.evaluate("""async csrf => {
            const response = await fetch('/api/complaint-workspace/auth/logout', {method: 'POST',
                credentials: 'same-origin', headers: {'x-csrf-token': csrf}});
            return response.status;
        }""", lawyer["csrf_token"])
        assert logged_out == 200
        page.evaluate("() => window.complaintCaseShell.refresh()")
        closed = _shell(page)
        assert closed["actor"] == "Not signed in" and closed["principalId"] == ""
        assert closed["caseId"] == "" and closed["case"] == "No case selected"
    finally:
        _close(playwright, context, node, profile, observed)
