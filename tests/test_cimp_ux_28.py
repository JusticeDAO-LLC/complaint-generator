"""A changed support context retires the previous conclusion.

Authority, date, jurisdiction, consent, and evidence versions each retire
support. The audit history keeps the old conclusion, and a refused refresh
does not write the encrypted case head.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from urllib.parse import quote

import pytest

from applications.legal_analysis_api import project_dependency_requirements
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PASSAGE = "An employer must pay wages that are due."
QUERY = "wage statute"
FACT = "The employer did not pay wages."
NARRATIVE = "On March 4, 2024 the employer did not pay wages after I asked."
RULE = "An employer must pay wages that are due."


def _cache(text=PASSAGE):
    return {"us_code|wage statute|wa|": [{
        "text": text,
        "snippet": text[:24],
        "citation": "29 U.S.C. 206",
        "uri": "https://example.invalid/usc-206",
        "jurisdiction": "WA",
    }]}


def _requirement(**overrides):
    row = {
        "rule_text": RULE,
        "description": RULE,
        "authority_version": "2024-03-04",
        "jurisdiction": "Washington",
        "effective_date": "2024-01-01",
        "applicable_date": "2024-03-04",
        "passage_id": "sha256:wages",
        "support_state": "fact_recorded",
        "legal_sufficiency": False,
        "proof": False,
        "admitted_law": True,
    }
    row.update(overrides)
    return row


def _stored():
    return {
        "status": "current",
        "request_id": "support-v1",
        "admitted_law": True,
        "legal_sufficiency": False,
        "proof": False,
        "requirements": [_requirement()],
        "coordinates": {
            "authority_version": "2024-03-04",
            "jurisdiction": "Washington",
            "effective_date": "2024-01-01",
            "as_of_date": "2024-03-04",
        },
        "support_binding": {"consent_generation": "1", "evidence_version": "ev-1"},
        "audit_history": [],
    }


def _case(**changes):
    stored = _stored()
    case = {
        "legal_context": {
            "jurisdiction": changes.get("jurisdiction", "Washington"),
            "applicable_law_date": {"precise_date": changes.get("effective_date", "2024-01-01")},
            "event_date": {"precise_date": changes.get("as_of_date", "2024-03-04")},
        },
        "operation_consent": {"generation": int(changes.get("consent_generation", 1))},
        "evidence_version": changes.get("evidence_version", "ev-1"),
        "derived_dependency_requirements": stored,
    }
    if "authority_version" in changes:
        case["legal_authority_admissions"] = [{
            "status": "admitted",
            "admitted_law": True,
            "version": changes["authority_version"],
        }]
    return case


def test_each_context_change_retires_support_without_writing_the_case():
    unchanged = _case()
    before = json.dumps(unchanged, sort_keys=True)
    current = project_dependency_requirements(unchanged)
    assert json.dumps(unchanged, sort_keys=True) == before
    assert current["support_retired"] is False
    assert current["requirements"][0]["support_state"] == "fact_recorded"
    assert current["requirements"][0]["rule_text"] == RULE

    expectations = {
        "authority_version": {"authority_version": "2025-01-01"},
        "effective_date": {"effective_date": "2025-01-01"},
        "as_of_date": {"as_of_date": "2025-06-01"},
        "jurisdiction": {"jurisdiction": "Oregon"},
        "consent_generation": {"consent_generation": 2},
        "evidence_version": {"evidence_version": "ev-2"},
    }
    for field, change in expectations.items():
        case = _case(**change)
        snapshot = json.dumps(case, sort_keys=True)
        retired = project_dependency_requirements(case)
        assert json.dumps(case, sort_keys=True) == snapshot
        assert retired["support_retired"] is True
        assert retired["support_current"] is False
        assert retired["requirements"] == []
        assert retired["changed_context"] == [field]
        assert retired["refresh_review"]["bounded"] is True
        assert retired["refresh_review"]["required"] is True
        prior = retired["audit_history"][-1]
        assert prior["current"] is False
        assert prior["conclusion_current"] is False
        assert prior["support_state"] == "retired"
        assert prior["requirements"][0]["rule_text"] == RULE
        assert prior["requirements"][0]["current"] is False
        assert prior["requirements"][0]["support_state"] == "retired"
        assert prior["requirements"][0]["legal_sufficiency"] is False
        assert case["derived_dependency_requirements"]["requirements"][0]["support_state"] == "fact_recorded"


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
    profile = tmp_path / "ux28-profile"
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


def _prepare(page, world):
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
    page.locator("#complaint-case-shell-nav [data-case-task='legal']").click()
    page.fill("#legal-source-flow-query", QUERY)
    page.fill("#legal-source-flow-cache", json.dumps(_cache()))
    page.click("#legal-source-flow-search")
    page.wait_for_selector("#legal-source-flow-custody [data-passage-id^='sha256:']")
    passage_id = page.get_attribute("#legal-source-flow-custody [data-passage-id^='sha256:']", "data-passage-id")
    page.locator(f"#legal-source-flow-custody input[value='{passage_id}']").check()
    page.click("#legal-source-flow-review-admit")
    page.wait_for_function("document.getElementById('legal-source-flow-review').dataset.admittedLaw === 'true'")
    page.fill("#legal-provenance-authority-version", "2024-03-04")
    page.fill("#legal-provenance-fact-id", "fact-wages")
    page.fill("#legal-provenance-fact-text", FACT)
    page.click("#legal-provenance-derive")
    page.wait_for_selector("#legal-provenance-requirements [data-role='requirement'][data-support-state='fact_recorded']")
    return passage_id


def _head(page):
    return page.evaluate(
        """async () => {
            const caseId = window.workspaceClient.caseContext.case_id;
            const session = await window.workspaceClient._request(
                '/api/complaint-workspace/session?case_id=' + encodeURIComponent(caseId),
                {method: 'GET'});
            return (session.encrypted_head || {}).private_revision || '';
        }"""
    )


def test_changed_context_retires_support_and_refused_refresh_keeps_the_head(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with _browser(tmp_path, monkeypatch, world.app) as page:
        _arm(page, world)
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        passage_id = _prepare(page, world)
        assert page.locator("#legal-provenance-requirements [data-current='false']").count() == 0
        assert RULE in page.locator("#legal-provenance-requirements").inner_text()

        page.fill("#legal-context-jurisdiction", "Oregon")
        page.fill("#legal-context-applicable-law-date", "2025-01-01")
        page.fill("#legal-context-event-date", "2025-06-01")
        page.click("#legal-context-save")
        page.wait_for_function("document.getElementById('legal-context-display').dataset.verification === 'verified'")
        shown = page.locator("#legal-context-display").inner_text()
        assert "Oregon" in shown or "OR" in shown
        page.fill("#legal-provenance-authority-version", "2025-01-01")
        consent = page.evaluate(
            """async () => {
                const caseId = window.workspaceClient.caseContext.case_id;
                const current = await window.workspaceClient._request(
                    '/api/cases/' + encodeURIComponent(caseId) + '/processing-consent', {method: 'GET'});
                const saved = await window.workspaceClient._request(
                    '/api/cases/' + encodeURIComponent(caseId) + '/processing-consent',
                    {method: 'POST', body: JSON.stringify({
                        purpose: 'extract_facts', mode: 'local_private', expected_generation: current.generation
                    })});
                return {before: current.generation, after: saved.generation};
            }"""
        )
        assert consent["after"] != consent["before"]
        head = _head(page)
        assert head
        page.locator("#complaint-case-shell-nav [data-case-task='legal']").click()
        page.click("#legal-provenance-refresh")
        page.wait_for_selector("#legal-support-retirement[data-state='stale']")
        assert page.get_attribute("#legal-support-retirement-prompt", "data-bounded") == "true"
        assert page.get_attribute("#legal-support-retirement-prompt", "data-required") == "true"
        changed = page.get_attribute("#legal-support-changed-context", "data-changed-context") or ""
        for field in ("jurisdiction", "effective_date", "as_of_date", "authority_version", "consent_generation"):
            assert field in changed.split(","), changed
        assert page.locator("#legal-provenance-requirements [data-role='requirement']").count() == 0
        assert page.get_attribute("#legal-provenance-support", "data-support-state") == "retired"
        assert page.get_attribute("#legal-provenance-support", "data-current") == "false"
        audit = page.locator("#legal-support-audit [data-role='support-audit']")
        assert audit.count() >= 1
        assert audit.first.get_attribute("data-current") == "false"
        assert audit.first.get_attribute("data-conclusion-current") == "false"
        assert audit.first.get_attribute("data-support-state") == "retired"
        assert RULE in audit.first.inner_text()
        assert page.locator("#legal-provenance-requirements").inner_text().strip() == ""

        refused = page.evaluate(
            """async () => {
                const caseId = window.workspaceClient.caseContext.case_id;
                try {
                    await window.workspaceClient._request(
                        '/api/legal-analysis/' + encodeURIComponent(caseId) + '/dependency-requirements',
                        {method: 'POST', body: JSON.stringify({
                            request_id: 'ux28-refused', query: 'wage statute', offline_cache: {},
                            review_decision: 'admit', review_passage_id: 'sha256:not-current',
                            authority_version: '2025-01-01', expected_private_revision: '999999',
                            expected_session_revision: 999999, facts: []
                        })});
                    return {ok: true};
                } catch (error) {
                    return {ok: false, status: error.status || 0, code: error.code || ''};
                }
            }"""
        )
        assert refused["ok"] is False
        assert refused["status"] == 409 or "revision" in refused["code"] or refused["code"] == "http_409"
        assert _head(page) == head
        assert page.get_attribute("#legal-provenance", "data-head-mutated") in {None, "false"}
        assert RULE in page.locator("#legal-support-audit").inner_text()
        assert page.locator("#legal-provenance-requirements [data-role='requirement']").count() == 0

        page.click("#legal-support-refresh-review")
        page.wait_for_function(
            """() => {
                const section = document.getElementById('legal-support-retirement');
                const state = document.getElementById('legal-provenance').dataset.state;
                return section && section.dataset.state === 'current' && ['ready', 'empty', 'stale'].indexOf(state) === -1
                    || state === 'ready' || state === 'empty';
            }"""
        )
        assert page.locator("#legal-provenance-requirements [data-support-state='retired']").count() == 0
        assert page.get_attribute("#legal-support-retirement", "data-state") == "current"
        assert RULE in page.locator("#legal-support-audit").inner_text()
        assert page.locator("#legal-support-audit [data-current='false']").count() >= 1
        current = page.locator("#legal-provenance-requirements [data-role='requirement']")
        if current.count():
            assert current.first.get_attribute("data-passage-id") == passage_id
            assert current.first.get_attribute("data-support-state") != "retired"
        assert _head(page) != head
