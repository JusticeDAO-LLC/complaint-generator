"""Mobile and tablet continuity for the same case tasks.

Desktop, tablet, and the two phone widths keep actions, unresolved gaps,
evidence, draft text, and correspondence on screen. Changing the width or
the workspace view does not rewrite the canonical case or widen access.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from applications.case_routes import CASE_PAGE_PATH, MESSAGE_INBOX_PATH
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

WIDTHS = (1440, 768, 390, 320)
HEIGHTS = {1440: 1000, 768: 1024, 390: 844, 320: 700}
VIEWPORTS = {1440: "desktop", 768: "tablet", 390: "mobile", 320: "mobile"}
GAP = "Unresolved 42 U.S.C. § 1983 authority remains unreviewed and must stay visible at every width."
LEGAL = (
    "The complaint cites 42 U.S.C. § 1983 and a long unbroken citation token "
    "Section1983-Authority-Span-That-Must-Wrap-Inside-The-Composer-Without-Clipping-The-Send-Action."
)


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def test_screen_size_does_not_change_authorization(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "auth")
    case_id = world.case.case_id
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as lawyer, TestClient(world.app, base_url="https://testserver") as stranger:
        owner_token = _composed_login(owner)
        lawyer_token = _composed_login(lawyer, "synthetic-lawyer-credential")
        stranger_token = _composed_login(stranger, "synthetic-stranger-credential")
        opened = owner.post(f"/api/cases/{case_id}/select", headers=_csrf(owner_token), json={})
        assert opened.status_code == 200, opened.text
        canonical = opened.json()
        assert GAP not in canonical["unresolved_gaps"]
        saved = owner.post(
            f"/api/cases/{case_id}/gaps",
            headers=_csrf(owner_token),
            json={"unresolved_gaps": [GAP], "expected_content_revision": canonical["encrypted_content_revision"]},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["unresolved_gaps"] == [GAP]
        revision = saved.json()["encrypted_content_revision"]
        directory = saved.json()["directory_revision"]
        owner_flag = saved.json()["actor_is_encrypted_owner"]
        for width in WIDTHS:
            again = owner.get(f"/api/cases/{case_id}", params={"viewport": width})
            assert again.status_code == 200, again.text
            body = again.json()
            assert body["unresolved_gaps"] == [GAP]
            assert body["encrypted_content_revision"] == revision
            assert body["directory_revision"] == directory
            assert body["actor_is_encrypted_owner"] is owner_flag
            assert body["key_grant"] == "owner"
            assert body["plaintext_available"] is True
            for client in (lawyer, stranger):
                denied = client.get(
                    f"/api/cases/{case_id}",
                    params={"viewport": width},
                    headers={"x-viewport-width": str(width)},
                )
                assert denied.status_code == 404
                assert denied.json()["error"] == "missing_case"
                listed = client.get("/api/cases", params={"viewport": width})
                assert listed.status_code == 200
                assert all(row["case_id"] != case_id for row in listed.json()["cases"])
        assert lawyer_token and stranger_token


def _launch(tmp_path, monkeypatch, world):
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix_only"], "the trusted executor must fence this child"
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux46-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    return page, playwright, context, node, profile


def _close(playwright, context, node, profile):
    context.close()
    playwright.stop()
    observed = browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _measure(page, selector):
    return page.evaluate(
        """(selector) => {
            const root = document.querySelector(selector);
            if (!root) return {missing: true};
            root.scrollIntoView({block: 'nearest'});
            const view = window.innerWidth;
            const problems = [];
            const nodes = [root, ...root.querySelectorAll('button, a, input, select, textarea, summary')];
            for (const node of nodes) {
                if (node.closest('[hidden]') || node.hidden) continue;
                const style = getComputedStyle(node);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                const rect = node.getBoundingClientRect();
                if (rect.width < 1 || rect.height < 1) continue;
                if (rect.left < -1 || rect.right > view + 1) {
                    problems.push((node.id || node.getAttribute('data-case-task') || node.tagName) + ':viewport');
                }
                if (node.scrollWidth > node.clientWidth + 4 && !['TEXTAREA', 'INPUT', 'SELECT', 'PRE'].includes(node.tagName)) {
                    const wrap = style.overflowWrap;
                    if (wrap !== 'anywhere' && wrap !== 'break-word') {
                        problems.push((node.id || node.className || node.tagName) + ':overflow');
                    }
                }
            }
            return {
                missing: false,
                overflow: root.scrollWidth > root.clientWidth + 2,
                scroll: root.scrollWidth,
                client: root.clientWidth,
                problems,
            };
        }""",
        selector,
    )


def _canonical(page, case_id):
    return page.evaluate(
        """async (caseId) => {
            const response = await fetch('/api/cases/' + encodeURIComponent(caseId), {credentials: 'same-origin'});
            const body = await response.json();
            return {
                status: response.status,
                gaps: body.unresolved_gaps || [],
                revision: body.encrypted_content_revision,
                directory: body.directory_revision,
                owner: body.actor_is_encrypted_owner,
                grant: body.key_grant,
                canonical: body.canonical_owner_principal_id,
                actor: body.actor_principal_id,
                membership: body.membership,
            };
        }""",
        case_id,
    )


def test_same_case_tasks_reflow_without_changing_server_state(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "reflow")
    case_id = world.case.case_id
    with TestClient(world.app, base_url="https://testserver") as client:
        token = _composed_login(client)
        selected = client.post(f"/api/cases/{case_id}/select", headers=_csrf(token), json={})
        assert selected.status_code == 200, selected.text
        saved = client.post(
            f"/api/cases/{case_id}/gaps",
            headers=_csrf(token),
            json={
                "unresolved_gaps": [GAP],
                "expected_content_revision": selected.json()["encrypted_content_revision"],
            },
        )
        assert saved.status_code == 200, saved.text
        saved_body = saved.json()
        # A namespaced case seals under a canonical tenant that is not the actor.
        # actor_is_encrypted_owner is that equality. The directory-owner grant is
        # key_grant "owner". Width changes must keep both bits, not promote the
        # actor into the legacy encrypted principal.
        before = {
            "revision": saved_body["encrypted_content_revision"],
            "directory": saved_body["directory_revision"],
            "owner": saved_body["actor_is_encrypted_owner"],
            "grant": saved_body["key_grant"],
            "canonical": saved_body["canonical_owner_principal_id"],
            "actor": saved_body["actor_principal_id"],
            "membership": saved_body["membership"],
        }
        assert before["owner"] is (world.case.owner_principal_id == world.case.tenant_id)
        assert before["canonical"] == world.case.tenant_id
        assert before["actor"] == world.owner.principal_id
        assert before["grant"] == "owner"
        assert before["membership"] == "owner-only"
    page, playwright, context, node, profile = _launch(tmp_path, monkeypatch, world)
    try:
        page.set_viewport_size({"width": 1440, "height": 1000})
        opened = page.goto(browser.SAME_ORIGIN + CASE_PAGE_PATH, wait_until="domcontentloaded")
        assert opened.status == 200
        page.fill("#case-credential", "synthetic-owner-credential")
        page.click("#case-login button[type=submit]")
        page.wait_for_function("() => document.getElementById('case-auth-status').textContent === 'Signed in'")
        page.click("#case-list button")
        page.wait_for_function(
            """(gap) => {
                const listed = [...document.querySelectorAll('#unresolved-gaps .gap')].map(node => node.textContent);
                const actor = document.getElementById('complaint-case-shell-actor');
                return listed.includes(gap) && actor && actor.dataset.relationship === 'owner';
            }""",
            arg=GAP,
        )
        order_before = page.evaluate(
            """() => [...document.querySelectorAll('#complaint-case-shell-nav [data-case-task]')].map(node => node.getAttribute('data-case-task'))"""
        )
        assert order_before[:6] == ["overview", "mediator", "evidence", "facts", "legal", "draft"]

        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": HEIGHTS[width]})
            page.wait_for_function(
                """(expected) => document.documentElement.dataset.caseViewport === expected""",
                arg=VIEWPORTS[width],
            )
            if width <= 390:
                more = page.locator("#complaint-case-shell-more")
                if more.count():
                    more.evaluate("node => { node.open = true; node.dispatchEvent(new Event('toggle', {bubbles: true})); }")
            page.locator("[data-case-task='evidence']").click()
            page.locator("[data-case-task='draft']").click()
            page.locator("[data-presentation-mode='chat-only']").click()
            page.locator("[data-presentation-mode='full-workspace']").click()
            shell = _measure(page, "#complaint-case-shell")
            assert shell["missing"] is False
            assert shell["overflow"] is False, shell
            assert shell["problems"] == [], shell
            gap_box = page.evaluate(
                """(gap) => {
                    const node = [...document.querySelectorAll('#unresolved-gaps .gap')].find(item => item.textContent === gap);
                    if (!node) return null;
                    const style = getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return {display: style.display, wrap: style.overflowWrap, width: rect.width, text: node.textContent};
                }""",
                GAP,
            )
            assert gap_box is not None
            assert gap_box["display"] != "none"
            assert gap_box["width"] > 0
            assert gap_box["text"] == GAP
            tops = page.evaluate(
                """() => [...document.querySelectorAll('#complaint-case-shell-nav [data-case-task]')].filter(node => !node.hidden && getComputedStyle(node).display !== 'none').map(node => node.getBoundingClientRect().top)"""
            )
            assert tops == sorted(tops)
            assert page.evaluate("() => document.getElementById('complaint-case-shell-actor').dataset.relationship") == "owner"
            live = _canonical(page, case_id)
            assert live["status"] == 200
            assert live["gaps"] == [GAP]
            assert live["revision"] == before["revision"]
            assert live["directory"] == before["directory"]
            assert live["owner"] is before["owner"]
            assert live["grant"] == before["grant"]
            assert live["canonical"] == before["canonical"]
            assert live["actor"] == before["actor"]
            assert live["membership"] == before["membership"]
            assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1") is True

        page.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
        page.fill("#inbox-credential", "synthetic-owner-credential")
        page.click("#inbox-login button[type=submit]")
        page.wait_for_function("() => document.getElementById('inbox-auth-status').textContent.includes('Signed in')")
        page.fill("#message-text", LEGAL)
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": HEIGHTS[width]})
            mail = _measure(page, ".correspondence")
            assert mail["overflow"] is False, mail
            assert mail["problems"] == [], mail
            send = page.locator("#send-button")
            box = send.bounding_box()
            assert box is not None and box["width"] >= 44 and box["x"] >= 0
            assert box["x"] + box["width"] <= width + 1
            assert LEGAL in page.locator("#message-text").input_value()
        assert _canonical(page, case_id)["revision"] == before["revision"]

        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        # Intake is the active workspace tab. Evidence and draft stay in the
        # document, inside inactive panels, until the width loop opens them.
        page.wait_for_selector("#evidence-library", state="attached")
        page.wait_for_selector("#complaint-outline", state="attached")
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": HEIGHTS[width]})
            page.locator(".tab-button[data-tab-target='evidence']").click()
            page.wait_for_selector("[data-tab-panel='evidence'].is-active")
            library = _measure(page, "#evidence-library")
            assert library["overflow"] is False, library
            assert library["problems"] == [], library
            add = page.locator("#evidence-library-add")
            if add.is_visible():
                add_box = add.bounding_box()
                assert add_box is not None and add_box["width"] >= 44
                assert add_box["x"] + add_box["width"] <= width + 1
            page.locator(".tab-button[data-tab-target='draft']").click()
            page.wait_for_selector("[data-tab-panel='draft'].is-active")
            page.wait_for_selector("link[data-complaint-draft-style]", state="attached")
            page.wait_for_function(
                """() => {
                    const outline = document.getElementById('complaint-outline');
                    return outline && outline.querySelector('[data-role="gap"]');
                }""",
                timeout=20000,
            )
            outline = _measure(page, "#complaint-outline")
            assert outline["overflow"] is False, outline
            assert outline["problems"] == [], outline
            gap_visible = page.evaluate(
                """() => {
                    const node = document.querySelector('#complaint-outline [data-role="gap"]');
                    if (!node) return null;
                    const style = getComputedStyle(node);
                    return {display: style.display, hidden: node.hidden, text: node.textContent};
                }"""
            )
            assert gap_visible["display"] != "none"
            assert gap_visible["hidden"] is False
            assert "Unresolved" in gap_visible["text"]
            columns = page.evaluate(
                """() => getComputedStyle(document.querySelector('.complaint-outline__layout')).gridTemplateColumns"""
            )
            if width <= 390:
                assert columns.strip().count(" ") == 0 or "0px" not in columns
                assert len(columns.split()) == 1
        after = _canonical(page, case_id)
        assert after["gaps"] == [GAP]
        assert after["revision"] == before["revision"]
        assert after["directory"] == before["directory"]
        assert after["owner"] is before["owner"]
        assert after["grant"] == before["grant"]
        assert after["canonical"] == before["canonical"]
        assert after["actor"] == before["actor"]
        assert after["membership"] == before["membership"]
        order_after = page.evaluate(
            """() => [...document.querySelectorAll('#complaint-case-shell-nav [data-case-task]')].map(node => node.getAttribute('data-case-task'))"""
        )
        assert order_after == order_before
    finally:
        _close(playwright, context, node, profile)
