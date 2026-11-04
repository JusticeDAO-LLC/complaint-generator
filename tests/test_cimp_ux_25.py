"""Legal context asks for forum and dates, then separates source decisions.

Search goes through the Dataset corpus lookup. A snippet or model sentence
stays a discovery gap. Review, applicability, and governing law are separate.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from urllib.parse import quote

import pytest

from applications.legal_context_api import conduct_legal_source_flow
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PASSAGE = "An employee may file a wage complaint within the stated limitation period."
SNIPPET = "A short snippet is not the statute."
MODEL = "The model concludes this statute governs."
QUERY = "wage statute"


def _cache():
    return {
        "us_code|wage statute|wa|": [
            {
                "text": PASSAGE,
                "snippet": "An employee may file",
                "citation": "29 U.S.C. § 255",
                "uri": "https://example.invalid/usc-255",
                "jurisdiction": "federal",
            },
            {"snippet": SNIPPET},
            {"model_text": MODEL, "snippet": MODEL},
        ]
    }


def _case_file():
    return {
        "legal_context": {
            "jurisdiction": "WA",
            "jurisdiction_explicit": True,
            "jurisdiction_applicability": "explicit",
            "event_date": {"raw_text": "2024-03-04", "precise_date": "2024-03-04"},
            "applicable_law_date": {"raw_text": "2024-03-04", "precise_date": "2024-03-04"},
            "filing_reference_date": {"raw_text": "2024-04-01", "precise_date": "2024-04-01"},
            "context_revision": 1,
        },
        "legal_context_forum": {"value": "King County Superior Court", "applicability": "explicit"},
        "legal_context_applicability": "explicit",
    }


def test_snippet_and_model_text_are_not_admitted_authority():
    blocked = conduct_legal_source_flow({"legal_context": {}}, {"query": QUERY, "offline_cache": _cache()})
    assert blocked["status"] == "questions_open"
    assert blocked["tool"] == "not_called"
    assert blocked["admitted_passage_ids"] == []
    assert blocked["governing_law_defaulted"] is False
    fields = {item["field"] for item in blocked["questions"]}
    assert {"jurisdiction", "forum", "event_date"} <= fields
    assert blocked["decisions"]["governing_law"]["value"] == "unknown"

    found = conduct_legal_source_flow(_case_file(), {
        "query": QUERY,
        "offline_cache": _cache(),
        "review_decision": "admit",
        "review_passage_id": SNIPPET,
        "governing_law_text": SNIPPET,
    })
    assert found["tool"] == "lookup_bounded_legal_corpus"
    kinds = {item["kind"] for item in found["decisions"]["discovery"]}
    assert {"full_text", "snippet", "model_text"} <= kinds
    assert all(item["admitted_law"] is False for item in found["decisions"]["discovery"])
    assert found["decisions"]["review_admission"]["admitted_law"] is False
    assert found["decisions"]["review_admission"]["reason"] == "snippet_or_model_text_not_authority"
    assert found["decisions"]["governing_law"]["admitted_authority"] is False
    assert found["decisions"]["applicability"]["value"] == "unknown"
    assert found["decisions"]["applicability"]["admitted_law"] is False
    passage_id = found["decisions"]["custody"][0]["passage_id"]
    assert passage_id.startswith("sha256:")
    admitted = conduct_legal_source_flow(_case_file(), {
        "query": QUERY,
        "offline_cache": _cache(),
        "review_decision": "admit",
        "review_passage_id": passage_id,
        "applicability_decision": "disputed",
        "governing_law_passage_id": passage_id,
    })
    assert admitted["admitted_passage_ids"] == [passage_id]
    assert admitted["decisions"]["review_admission"]["admitted_law"] is True
    assert admitted["decisions"]["applicability"]["value"] == "disputed"
    assert admitted["decisions"]["applicability"]["admitted_law"] is False
    assert admitted["decisions"]["governing_law"]["admitted_authority"] is True
    assert admitted["decisions"]["governing_law"]["passage_id"] == passage_id
    assert admitted["governing_law_defaulted"] is False
    refused = conduct_legal_source_flow(_case_file(), {
        "query": QUERY,
        "offline_cache": _cache(),
        "review_decision": "admit",
        "review_passage_id": passage_id,
        "governing_law_text": MODEL,
        "governing_law_passage_id": passage_id,
    })
    assert refused["decisions"]["governing_law"]["admitted_authority"] is False
    assert refused["decisions"]["governing_law"]["reason"] == "snippet_or_model_text_not_authority"


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
    profile = tmp_path / "ux25-profile"
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


def test_workspace_asks_then_separates_source_decisions(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with _browser(tmp_path, monkeypatch, world.app) as page:
        _arm(page, world)
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        page.locator("#complaint-case-shell-nav [data-case-task='mediator']").click()
        page.fill("#adaptive-narrative", "On March 4, 2024 my assignment ended after I reported a safety concern.")
        page.click("#adaptive-enter-narrative")
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        page.fill("#legal-context-case-id", world.journey_case.case_id)
        page.click("#legal-context-refresh")
        page.wait_for_selector("#legal-context-questions [data-field='jurisdiction']")
        assert page.input_value("#legal-context-jurisdiction") == ""
        assert page.input_value("#legal-context-forum") == ""
        assert page.input_value("#legal-context-event-date") == ""
        assert page.locator("#legal-context-questions [data-field='forum']").count() == 1
        assert page.input_value("#legal-context-jurisdiction") != "Oregon"
        page.fill("#legal-source-flow-query", QUERY)
        page.fill("#legal-source-flow-cache", json.dumps(_cache()))
        page.click("#legal-source-flow-search")
        page.wait_for_function("document.getElementById('legal-source-flow-status').dataset.status === 'questions_open'")
        assert page.get_attribute("#legal-source-flow-status", "data-tool") == "not_called"
        assert page.locator("#legal-source-flow-discovery [data-admitted-law='true']").count() == 0

        page.fill("#legal-context-jurisdiction", "Washington")
        page.fill("#legal-context-forum", "King County Superior Court")
        page.fill("#legal-context-event-date", "2024-03-04")
        page.fill("#legal-context-applicable-law-date", "2024-03-04")
        page.fill("#legal-context-filing-reference-date", "2024-04-01")
        page.select_option("#legal-context-applicability", "explicit")
        page.click("#legal-context-save")
        page.wait_for_function("document.getElementById('legal-context-display').dataset.verification === 'verified'")
        assert page.get_attribute("#legal-context-display", "data-governing-law-defaulted") == "false"
        assert "Washington" in page.locator("#legal-context-display").inner_text() or "WA" in page.locator("#legal-context-display").inner_text()
        assert page.locator("#legal-context-questions [data-field='jurisdiction']").count() == 0

        page.click("#legal-source-flow-search")
        page.wait_for_selector("#legal-source-flow-custody [data-passage-id^='sha256:']")
        assert page.get_attribute("#legal-source-flow-status", "data-tool") == "lookup_bounded_legal_corpus"
        assert page.locator("#legal-source-flow-discovery [data-kind='snippet']").get_attribute("data-admitted-law") == "false"
        assert page.locator("#legal-source-flow-discovery [data-kind='model_text']").get_attribute("data-admitted-law") == "false"
        assert page.get_attribute("#legal-source-flow-review", "data-admitted-law") == "false"
        passage_id = page.get_attribute("#legal-source-flow-custody [data-passage-id^='sha256:']", "data-passage-id")
        page.locator(f"#legal-source-flow-custody input[value='{passage_id}']").check()
        page.click("#legal-source-flow-review-admit")
        page.wait_for_function("document.getElementById('legal-source-flow-review').dataset.admittedLaw === 'true'")
        assert page.get_attribute("#legal-source-flow-applicability", "data-value") == "unknown"
        assert page.get_attribute("#legal-source-flow-governing", "data-admitted-authority") == "false"
        page.select_option("#legal-source-flow-applicability-choice", "disputed")
        page.click("#legal-source-flow-applicability-save")
        page.wait_for_function("document.getElementById('legal-source-flow-applicability').dataset.value === 'disputed'")
        assert page.get_attribute("#legal-source-flow-applicability", "data-admitted-law") == "false"
        assert page.get_attribute("#legal-source-flow-review", "data-admitted-law") == "true"
        page.fill("#legal-source-flow-governing-text", MODEL)
        page.fill("#legal-source-flow-governing-passage", passage_id)
        page.click("#legal-source-flow-governing-save")
        page.wait_for_function("document.getElementById('legal-source-flow-governing').dataset.reason === 'snippet_or_model_text_not_authority'")
        assert page.get_attribute("#legal-source-flow-governing", "data-admitted-authority") == "false"
        page.fill("#legal-source-flow-governing-text", "")
        page.click("#legal-source-flow-governing-save")
        page.wait_for_function("document.getElementById('legal-source-flow-governing').dataset.admittedAuthority === 'true'")
        assert page.get_attribute("#legal-source-flow-governing", "data-passage-id") == passage_id
        assert page.get_attribute("#legal-source-flow-governing", "data-defaulted") == "false"
        assert page.locator("#legal-source-flow-discovery [data-kind='model_text']").get_attribute("data-admitted-law") == "false"
