"""Facts and timeline read one interview projection.

List, timeline, and graph are display modes. A mode change does not write a
second graph, drop an unanswered question, or mark a fact corroborated.
Corrections and unknown answers go through the current interview owner.
"""
from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import quote

import pytest

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On March 4, 2024 supervisor Alex Rivera ended my assignment after I reported a safety concern."
ANSWER = "The safety report was an email sent on March 3, 2024."
REPLACEMENT = "The safety report was a written email sent on March 3, 2024."


def _case_payload(world):
    case = world.journey_case
    return {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "revision": case.revision,
        "expected_revision": case.revision,
    }


@contextmanager
def _browser(tmp_path, monkeypatch, app):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux24-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    page.set_viewport_size({"width": 1440, "height": 1000})
    try:
        yield page
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []


def _arm(page, world):
    page.goto(browser.SAME_ORIGIN + "/workspace?user_id=" + quote(world.journey_case.tenant_id), wait_until="domcontentloaded")
    page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
    issued = page.evaluate(
        """async credential => {
            const response = await fetch('/api/complaint-workspace/auth/login', {
                method: 'POST', credentials: 'same-origin', headers: {'content-type': 'application/json'},
                body: JSON.stringify({credential})});
            if (!response.ok) throw new Error('login_' + response.status);
            return await response.json();
        }""",
        "synthetic-owner-credential",
    )
    assert issued["authenticated"] is True
    assert issued["principal_id"] == world.owner.principal_id
    page.evaluate(
        """async data => {
            window.workspaceClient.setBrowserSession(data.issued);
            window.workspaceClient.setCaseContext(data.case);
            await window.workspaceClient.bootstrapWorkspace(data.case.tenant_id);
        }""",
        {"issued": issued, "case": _case_payload(world)},
    )


def _snapshot(page):
    return page.evaluate(
        """async () => {
            const binding = window.workspaceClient.caseContext;
            const response = await fetch('/api/complaint-workspace/session?case_id=' + encodeURIComponent(binding.case_id), {
                credentials: 'same-origin',
                headers: {
                    'x-tenant-id': binding.tenant_id,
                    'x-case-id': binding.case_id,
                    'x-resource-id': binding.resource_id,
                    'x-expected-revision': String(binding.expected_revision || ''),
                },
            });
            const body = await response.json();
            const interview = (body.session || {}).shared_interview || {};
            const pending = interview.pending_inquiry || {};
            const graph = await fetch('/api/complaint-workspace/factual-graph?case_id=' + encodeURIComponent(binding.case_id), {
                credentials: 'same-origin',
                headers: {
                    'x-tenant-id': binding.tenant_id,
                    'x-case-id': binding.case_id,
                    'x-resource-id': binding.resource_id,
                    'x-expected-revision': String(binding.expected_revision || ''),
                },
            });
            const projected = await graph.json();
            return {
                sessionStatus: response.status,
                graphStatus: graph.status,
                inquiryId: pending.inquiry_id || '',
                question: pending.question || '',
                graphId: projected.graph_id || (projected.status === 'projected' ? (projected.case_id || '') : ''),
                stored: JSON.stringify(interview.knowledge_graph || {}),
                corroborated: (projected.user_statements || []).filter(item => item.explicitly_adopted_evidence === true).length,
                statements: (projected.user_statements || []).map(item => ({
                    id: item.assertion_id || '',
                    text: (item.source_provenance && item.source_provenance.source_span && item.source_provenance.source_span.text) || item.text || '',
                    version: (item.source_provenance && item.source_provenance.extractor_version) || '',
                    source: (item.source_provenance && item.source_provenance.source_id) || '',
                })),
            };
        }"""
    )


def _posts_during(page, action):
    seen = []

    def remember(request):
        if request.method == "POST":
            seen.append(request.url)

    page.on("request", remember)
    try:
        action()
    finally:
        page.remove_listener("request", remember)
    return seen


def test_facts_timeline_reuses_one_graph_and_keeps_uncertainty(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with _browser(tmp_path, monkeypatch, world.app) as page:
        _arm(page, world)
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        page.locator("#complaint-case-shell-nav [data-case-task='facts']").click()
        page.wait_for_function("document.getElementById('complaint-facts-status').textContent !== 'Facts have not been loaded.'")
        assert page.get_attribute("#complaint-facts", "data-state") in {"unavailable", "empty", "error", "locked"}
        assert page.locator("#complaint-facts [data-corroborated='true']").count() == 0
        assert page.get_attribute("#complaint-facts", "data-corroboration-fabricated") == "false"
        assert page.get_attribute("#complaint-facts", "data-graph-count") == "0"

        page.locator("#complaint-case-shell-nav [data-case-task='mediator']").click()
        page.fill("#adaptive-narrative", NARRATIVE)
        page.click("#adaptive-enter-narrative")
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        inquiry_id = page.get_attribute("#adaptive-pending", "data-inquiry-id")
        assert inquiry_id
        before = _snapshot(page)
        assert before["sessionStatus"] == 200
        assert before["graphStatus"] == 200
        assert before["inquiryId"] == inquiry_id
        assert before["graphId"]
        assert before["corroborated"] == 0

        page.locator("#complaint-case-shell-nav [data-case-task='facts']").click()
        page.wait_for_function("document.getElementById('complaint-facts').dataset.state === 'ready' || document.getElementById('complaint-facts').dataset.state === 'empty'")
        assert page.locator(f"#complaint-facts-questions [data-inquiry-id='{inquiry_id}']").count() == 1
        assert page.get_attribute("#complaint-facts", "data-graph-id") == before["graphId"]
        assert page.locator("[data-role='facts-graph']").count() == 1
        assert page.locator("#complaint-facts [data-corroborated='true']").count() == 0

        def switch_modes():
            page.click("#complaint-facts-mode-timeline")
            page.click("#complaint-facts-mode-graph")
            page.focus("#complaint-facts-mode-graph")
            page.keyboard.press("ArrowLeft")
            page.click("#complaint-facts-mode-list")

        posts = _posts_during(page, switch_modes)
        assert [url for url in posts if any(part in url for part in ("intake-chat", "/mcp/", "factual-graph"))] == []
        assert page.get_attribute("#complaint-facts", "data-mode") == "list"
        assert page.get_attribute("#complaint-facts-mode-timeline", "aria-pressed") == "false"
        assert page.locator(f"#complaint-facts-questions [data-inquiry-id='{inquiry_id}']").count() == 1
        assert page.locator("[data-role='facts-graph']").count() == 1
        after_switch = _snapshot(page)
        assert after_switch["stored"] == before["stored"]
        assert after_switch["graphId"] == before["graphId"]
        assert after_switch["inquiryId"] == inquiry_id
        assert after_switch["question"] == before["question"]
        assert page.get_attribute("#complaint-facts", "data-graph-writes") == "0"

        if before["statements"]:
            shown = before["statements"][0]
            page.locator(f"#complaint-facts-list [data-assertion-id='{shown['id']}']").click()
            page.wait_for_selector("#complaint-facts-provenance:not([hidden])")
            assert page.locator("#complaint-facts-span").inner_text() == shown["text"]
            assert page.locator("#complaint-facts-source").inner_text() == shown["source"]
            assert page.locator("#complaint-facts-version").inner_text() == shown["version"]
            assert page.locator("#complaint-facts-corroboration").inner_text() == "Not corroborated."
            page.click("#complaint-facts-close")
            assert page.evaluate("() => document.activeElement.dataset.assertionId") == shown["id"]

        page.locator("#complaint-case-shell-nav [data-case-task='mediator']").click()
        page.fill("#adaptive-answer", ANSWER)
        with page.expect_response(lambda response: response.request.method == "POST" and "/mcp/" in response.url) as answered:
            page.click("#adaptive-submit-answer")
        assert answered.value.status == 200
        page.wait_for_function("document.getElementById('factual-correction-target').value !== ''")
        target = page.input_value("#factual-correction-target")
        page.locator("#complaint-case-shell-nav [data-case-task='facts']").click()
        page.wait_for_function(
            "target => !!document.querySelector('#complaint-facts-list [data-assertion-id=\"' + target + '\"]')",
            arg=target,
        )
        page.locator(f"#complaint-facts-list [data-assertion-id='{target}']").click()
        page.fill("#complaint-facts-replacement", REPLACEMENT)
        with page.expect_response(lambda response: response.request.method == "POST" and "/mcp/" in response.url) as corrected:
            page.click("#complaint-facts-correct")
        assert corrected.value.status == 200
        page.wait_for_function("document.getElementById('complaint-facts-edit-status').dataset.status === 'applied'")
        assert page.get_attribute("#complaint-facts-edit-status", "data-graph-id-changed") == "false"
        corrected_graph = _snapshot(page)
        assert corrected_graph["graphId"] == before["graphId"]
        assert REPLACEMENT in corrected_graph["stored"]
        assert ANSWER in corrected_graph["stored"]
        assert page.locator("#complaint-facts [data-corroborated='true']").count() == 0

        page.locator(f"#complaint-facts-list [data-assertion-id='{target}']").click()
        page.fill("#complaint-facts-replacement", "This stale edit must not replace the recorded fact.")
        page.fill("#complaint-facts-graph-revision", "stale-ux24")
        with page.expect_response(lambda response: response.request.method == "POST" and "/mcp/" in response.url) as refused:
            page.click("#complaint-facts-correct")
        assert refused.value.status in {200, 409}
        page.wait_for_function("document.getElementById('complaint-facts-edit-status').dataset.status === 'refused'")
        kept = _snapshot(page)
        assert kept["graphId"] == before["graphId"]
        assert "This stale edit must not replace the recorded fact." not in kept["stored"]
        assert REPLACEMENT in kept["stored"]
        assert page.locator("[data-role='facts-graph']").count() == 1

        pending = page.locator("#complaint-facts-questions [data-kind='pending']")
        if pending.count():
            kept_questions = pending.count()
            with page.expect_response(lambda response: response.request.method == "POST" and ("/mcp/" in response.url or "intake-chat" in response.url)) as unknown_response:
                page.click("#complaint-facts-unknown")
            assert unknown_response.value.status in {200, 409}
            page.wait_for_function("document.getElementById('complaint-facts-edit-status').dataset.gapPreserved === 'true'")
            assert page.get_attribute("#complaint-facts-edit-status", "data-dropped-questions") == "false"
            assert page.locator("#complaint-facts [data-corroborated='true']").count() == 0
            assert page.locator("#complaint-facts-questions [data-kind='pending'], #complaint-facts-questions [data-kind='gap']").count() >= 1
            assert kept_questions >= 1

        page.set_viewport_size({"width": 390, "height": 844})
        box = page.locator("#complaint-facts-refresh").bounding_box()
        assert box and box["width"] >= 44 and box["height"] >= 44
        assert page.locator("#complaint-facts-mode-list").is_visible()

        page.evaluate(
            """() => {
                window.complaintFacts.render({
                    status: 'projected',
                    graph_id: 'synthetic-one-graph',
                    case_id: 'synthetic-case',
                    user_statements: [{
                        text: 'The notice arrived on March 3.',
                        assertion_id: 'stated-1',
                        admitted_user_fact: true,
                        explicitly_adopted_evidence: false,
                        confidence: 0.99,
                        authority_is_user_fact: true,
                        source_provenance: {verified: true, source_id: 'msg-1', extractor_version: 'v1', source_span: {text: 'The notice arrived on March 3.'}},
                    }],
                    hypotheses: [{
                        text: 'A model guessed the motive.',
                        assertion_id: 'guess-1',
                        admitted_user_fact: false,
                        authority_is_user_fact: false,
                        confidence: 1,
                    }],
                    unresolved: [{graph_entity_id: 'open-1', reason: 'missing source', kind: 'unresolved'}],
                    adopted_evidence: [],
                }, {
                    adaptive_inquiry: {
                        pending: true,
                        inquiry_id: 'inq-keep',
                        revision: 3,
                        prompt: 'Who received the notice?',
                        preserved_gaps: [{inquiry_id: 'gap-keep', question: 'Which shift was it?'}],
                        factual_correction: {target_stable_id: 'stated-1', expected_graph_revision: 'rev-1', expected_session_revision: 4, actor_principal_id: 'owner'},
                    },
                });
            }"""
        )
        assert page.locator("#complaint-facts-questions [data-inquiry-id='inq-keep']").count() == 1
        assert page.locator("#complaint-facts-questions [data-inquiry-id='gap-keep']").count() == 1
        assert page.locator("[data-assertion-id='guess-1']").first.get_attribute("data-corroborated") == "false"
        assert page.locator("[data-assertion-id='stated-1']").first.get_attribute("data-corroborated") == "false"
        page.click("#complaint-facts-mode-graph")
        page.click("#complaint-facts-mode-timeline")
        assert page.locator("#complaint-facts-questions [data-inquiry-id='inq-keep']").count() == 1
        assert page.locator("#complaint-facts-questions [data-inquiry-id='gap-keep']").count() == 1
        assert page.locator("[data-role='facts-graph']").count() == 1
        assert page.get_attribute("#complaint-facts", "data-graph-id") == "synthetic-one-graph"
        assert page.locator("[data-key='open-1']").count() >= 1
        page.click("#complaint-facts-mode-list")
        page.locator("#complaint-facts-list [data-assertion-id='guess-1']").click()
        assert page.locator("#complaint-facts-corroboration").inner_text() == "Not corroborated."
        assert page.locator("#complaint-facts-span").inner_text() == "No source span was recorded."
