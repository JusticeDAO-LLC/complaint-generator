"""Reviewers can follow a requirement through passage, assertion, and evidence.

The legal dependency graph and the factual graph stay visually distinct.
Source admission, AI suggestions, and legal sufficiency stay separate labels.
A conflicting authority or a stale revision does not become current support.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from urllib.parse import quote

import pytest

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PASSAGE = "An employer must pay wages that are due."
OTHER = "An employer must keep a payroll record."
QUERY = "wage statute"
FACT = "The employer did not pay wages."
NARRATIVE = "On March 4, 2024 the employer did not pay wages after I asked."


def _cache(*texts):
    rows = [{
        "text": text,
        "snippet": text[:24],
        "citation": "29 U.S.C. 206",
        "uri": "https://example.invalid/usc-206",
        "jurisdiction": "WA",
    } for text in texts]
    return {"us_code|wage statute|wa|": rows}


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
    profile = tmp_path / "ux27-profile"
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
    page.evaluate(
        """async data => {
            window.workspaceClient.setBrowserSession(data.issued);
            window.workspaceClient.setCaseContext(data.case);
            await window.workspaceClient.bootstrapWorkspace(data.case.tenant_id);
        }""",
        {"issued": issued, "case": _case_payload(world)},
    )


def _save_context(page, world):
    page.locator("#complaint-case-shell-nav [data-case-task='mediator']").click()
    page.fill("#adaptive-narrative", NARRATIVE)
    page.click("#adaptive-enter-narrative")
    page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
    if page.locator("#adaptive-answer").count():
        page.fill("#adaptive-answer", FACT)
        page.click("#adaptive-submit-answer")
        page.wait_for_timeout(400)
    page.fill("#legal-context-case-id", world.journey_case.case_id)
    page.fill("#legal-context-jurisdiction", "Washington")
    page.fill("#legal-context-forum", "King County Superior Court")
    page.fill("#legal-context-event-date", "2024-03-04")
    page.fill("#legal-context-applicable-law-date", "2024-01-01")
    page.fill("#legal-context-filing-reference-date", "2024-04-01")
    page.select_option("#legal-context-applicability", "explicit")
    page.click("#legal-context-save")
    page.wait_for_function("document.getElementById('legal-context-display').dataset.verification === 'verified'")


def _admit(page, texts):
    page.fill("#legal-source-flow-query", QUERY)
    page.fill("#legal-source-flow-cache", json.dumps(_cache(*texts)))
    page.click("#legal-source-flow-search")
    page.wait_for_selector("#legal-source-flow-custody [data-passage-id^='sha256:']")
    passage_id = page.get_attribute("#legal-source-flow-custody [data-passage-id^='sha256:']", "data-passage-id")
    page.locator(f"#legal-source-flow-custody input[value='{passage_id}']").check()
    page.click("#legal-source-flow-review-admit")
    page.wait_for_function("document.getElementById('legal-source-flow-review').dataset.admittedLaw === 'true'")
    return passage_id


def _graph_colors(page):
    return page.evaluate(
        """() => {
            const legal = getComputedStyle(document.getElementById('legal-dependency-graph'));
            const factual = getComputedStyle(document.getElementById('factual-provenance-graph'));
            return {
                legal: legal.borderLeftColor,
                factual: factual.borderLeftColor,
                legalBackground: legal.backgroundColor,
                factualBackground: factual.backgroundColor
            };
        }"""
    )


def test_reviewer_follows_requirement_passage_assertion_and_evidence(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with _browser(tmp_path, monkeypatch, world.app) as page:
        _arm(page, world)
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        page.locator("#complaint-case-shell-nav [data-case-task='legal']").click()
        assert page.get_attribute("#legal-provenance", "data-state") == "empty"
        assert page.get_attribute("#legal-provenance-sufficiency", "data-legal-sufficiency") == "false"
        assert page.get_attribute("#legal-provenance-suggestion", "data-admitted-law") == "false"
        colors = _graph_colors(page)
        assert colors["legal"] != colors["factual"]
        assert colors["legalBackground"] != colors["factualBackground"]
        assert page.get_attribute("#legal-dependency-graph", "data-graph-kind") == "legal-dependency"
        assert page.get_attribute("#factual-provenance-graph", "data-graph-kind") == "factual"

        _save_context(page, world)
        passage_id = _admit(page, (PASSAGE,))
        page.fill("#legal-provenance-authority-version", "2024-03-04")
        page.fill("#legal-provenance-fact-id", "fact-wages")
        page.fill("#legal-provenance-fact-text", FACT)
        page.click("#legal-provenance-derive")
        page.wait_for_selector("#legal-provenance-requirements [data-role='requirement'][data-admitted-law='true']")
        assert page.get_attribute("#legal-provenance", "data-legal-sufficiency") == "false"
        assert page.get_attribute("#legal-provenance-admission", "data-admitted-law") == "true"
        assert page.get_attribute("#legal-provenance-suggestion", "data-admitted-law") == "false"
        requirement = page.locator("#legal-provenance-requirements [data-role='requirement']")
        assert requirement.get_attribute("data-graph-kind") == "legal-dependency"
        assert requirement.get_attribute("data-passage-id") == passage_id
        assert requirement.get_attribute("data-legal-sufficiency") == "false"
        assert requirement.get_attribute("data-support-state") == "fact_recorded"
        requirement.click()
        page.click("#legal-provenance-step-passage")
        assert PASSAGE in page.locator("#legal-provenance-passage").inner_text()
        assert page.get_attribute("#legal-provenance-passage", "data-admitted-law") == "true"
        page.locator("#legal-provenance-assertions [data-role='factual-assertion']").first.click()
        shown = page.locator("#legal-provenance-assertions [aria-pressed='true']").inner_text().lower()
        assert "wage" in shown or "employer" in shown
        assert page.get_attribute("#legal-provenance-assertions [aria-pressed='true']", "data-graph-kind") == "factual"
        assert page.get_attribute("#legal-provenance-assertions [aria-pressed='true']", "data-admitted-law") == "false"
        page.locator("#legal-provenance-evidence [data-role='evidence-span'], #legal-provenance-evidence [data-missing='evidence-span']").first.click()
        evidence = page.locator("#legal-provenance-evidence [data-role='evidence-span']")
        if evidence.count():
            span = evidence.first.inner_text()
            assert span.strip()
            assert page.get_attribute("#legal-provenance-evidence [data-role='evidence-span']", "data-admitted-law") == "false"
            page.click("#legal-provenance-step-evidence")
            assert page.get_attribute("#legal-provenance-step-evidence", "aria-current") == "step"
        else:
            assert page.locator("#legal-provenance-evidence [data-role='missing-input']").count() == 1
        assert page.get_attribute("#legal-provenance-support", "data-support-state") == "fact_recorded"
        assert page.locator("#legal-provenance-contradictions [data-role='contradiction']").count() >= 1
        assert page.locator("#legal-provenance [data-label='source-admission']").count() == 1
        assert page.locator("#legal-provenance [data-label='ai-suggestion']").count() == 1
        assert page.locator("#legal-provenance [data-label='legal-sufficiency']").count() == 1

        stale = page.evaluate(
            """async () => {
                const caseId = window.workspaceClient.caseContext.case_id;
                const response = await window.workspaceClient._request(
                    '/api/legal-analysis/' + encodeURIComponent(caseId) + '/dependency-requirements',
                    {method: 'POST', body: JSON.stringify({
                        request_id: 'ux27-stale', query: 'wage statute', offline_cache: {},
                        review_decision: 'admit', review_passage_id: 'sha256:not-current',
                        authority_version: '2024-03-04', expected_private_revision: '999999',
                        expected_session_revision: 999999, facts: []
                    })}
                ).then(() => ({ok: true})).catch(error => ({ok: false, code: error.code || '', status: error.status || 0}));
                return response;
            }"""
        )
        assert stale["ok"] is False
        assert stale["status"] == 409 or "revision" in stale["code"] or stale["code"] == "http_409"
        assert PASSAGE in page.locator("#legal-provenance-passage").inner_text()
        page.click("#legal-provenance-refresh")
        page.wait_for_selector("#legal-provenance-requirements [data-admitted-law='true']")
        assert PASSAGE in page.locator("#legal-provenance-passage").inner_text()


def test_conflicting_authority_and_missing_case_stay_unresolved(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with _browser(tmp_path, monkeypatch, world.app) as page:
        _arm(page, world)
        page.locator("#complaint-case-shell-nav [data-case-task='legal']").click()
        page.click("#legal-provenance-refresh")
        page.wait_for_function("document.getElementById('legal-provenance').dataset.loaded === 'true'")
        assert page.locator("#legal-provenance-requirements [data-admitted-law='true']").count() == 0
        assert page.get_attribute("#legal-provenance-sufficiency", "data-legal-sufficiency") == "false"

        _save_context(page, world)
        page.fill("#legal-source-flow-query", QUERY)
        page.fill("#legal-source-flow-cache", json.dumps(_cache(PASSAGE, OTHER)))
        page.click("#legal-source-flow-search")
        page.wait_for_selector("#legal-source-flow-custody [data-passage-id^='sha256:']")
        first = page.locator("#legal-source-flow-custody [data-passage-id^='sha256:']").first.get_attribute("data-passage-id")
        page.locator(f"#legal-source-flow-custody input[value='{first}']").check()
        page.click("#legal-source-flow-review-admit")
        page.wait_for_function("document.getElementById('legal-source-flow-review').dataset.admittedLaw === 'true'")
        page.fill("#legal-provenance-authority-version", "2024-03-04")
        page.fill("#legal-provenance-fact-text", FACT)
        page.click("#legal-provenance-derive")
        page.wait_for_selector("#legal-provenance-contradictions [data-reason='conflicting_authority']")
        assert page.locator("#legal-provenance-requirements [data-admitted-law='true']").count() == 0
        assert page.get_attribute("#legal-provenance-admission", "data-admitted-law") == "false"
        assert page.get_attribute("#legal-provenance-suggestion", "data-admitted-law") == "false"
        assert page.get_attribute("#legal-provenance", "data-legal-sufficiency") == "false"
        assert page.locator("#legal-provenance-missing [data-role='missing-input'], #legal-provenance-contradictions [data-role='contradiction']").count() >= 1
        colors = _graph_colors(page)
        assert colors["legal"] != colors["factual"]
