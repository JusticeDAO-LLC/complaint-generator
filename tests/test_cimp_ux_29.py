"""Formal checks render producer bindings and refuse caller-minted proof."""

from __future__ import annotations

import json
from contextlib import contextmanager
from urllib.parse import quote

import pytest

from applications.legal_analysis_api import run_case_formal_check
from integrations.ipfs_datasets.logic import sha256_utf8
from mediator.hook_runtime import dispatch_formal_neurosymbolic_analysis
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

STATUTE = "An employer shall not retaliate against an employee for opposing an unlawful practice."
PREMISE = "The employee opposed an unlawful practice on March 3, 2024."


def _body(**overrides):
    premise_digest = sha256_utf8(PREMISE)
    body = {
        "source_text": STATUTE,
        "source_hash": sha256_utf8(STATUTE),
        "source_version": "2024-edition",
        "current_source_version": "2024-edition",
        "definition_identity": "def-retaliation-3",
        "current_definition_identity": "def-retaliation-3",
        "requirement_id": "req-retaliation",
        "citation": "ORS 659A.030",
        "premises": [{"premise_id": "premise-opposed", "text": PREMISE, "revision": "rev-1"}],
        "current_premises": [{"premise_id": "premise-opposed", "revision": "rev-1", "text_sha256": premise_digest}],
        "parsed_formula": {"formula": "forall x. Employer(x)", "status": "proved", "legal_sufficiency": True},
        "training_metric": {"accuracy": 1.0, "status": "proved"},
        "fake_producer": {"outcome": "proved", "executed_proof": True, "substantive_trust_satisfied": True},
        "executed_proof": True,
        "proof": True,
        "proof_status": "verified",
        "claims": [{"id": "claim-retaliation", "name": "Retaliation claim", "claim_type": "retaliation"}],
        "requirements": [{
            "id": "req-protected-activity",
            "name": "protected activity notice",
            "claim_type": "retaliation",
            "satisfied": True,
            "confidence": 0.97,
            "citation": "ORS 659A.030",
            "source_version": "2024-edition",
            "definition_identity": "def-retaliation-3",
        }],
    }
    body.update(overrides)
    return body


def test_live_producer_bindings_are_not_replaced_by_a_caller_proof():
    payload = _body()
    snapshot = json.dumps(payload, sort_keys=True)
    direct = dispatch_formal_neurosymbolic_analysis(payload)
    projected = run_case_formal_check(payload)
    assert json.dumps(payload, sort_keys=True) == snapshot
    assert direct["workflow"] == "ground_formal_neurosymbolic_analysis"
    assert projected["workflow"] == direct["workflow"]
    assert projected["bindings"]["source_version"] == "2024-edition"
    assert projected["bindings"]["definition_identity"] == "def-retaliation-3"
    assert projected["bindings"]["requirement_id"] == "req-retaliation"
    assert projected["bindings"]["source_hash"] == sha256_utf8(STATUTE)
    assert projected["bindings"]["execution"] == direct["execution"]
    assert projected["premises"][0]["premise_id"] == "premise-opposed"
    assert projected["premises"][0]["text_sha256"] == sha256_utf8(PREMISE)
    assert projected["premises"][0]["executed_proof"] is False
    assert projected["parsed_ir_is_proof"] is False
    assert projected["training_metric_is_proof"] is False
    assert projected["caller_status_is_proof"] is False
    assert projected["solver_availability_is_proof"] is False
    assert projected["legal_sufficiency"] is False
    assert projected["proof"] is False
    assert projected["caller_claim_rejected"] is True
    assert projected["case_head_mutated"] is False
    assert "not accepted as proof" in projected["explanation"]
    assert projected["executed_proof"] is (
        direct["executed_proof"] is True
        and direct["producer_invoked"] is True
        and isinstance(direct.get("route"), dict)
        and direct["route"].get("outcome") == "proved"
        and direct["route"].get("executed_proof") is True
    )
    if projected["executed_proof"]:
        assert "bound producer returned a proved result" in projected["explanation"]
    else:
        assert projected["status"] in {"grounded", "unavailable", "unexecuted", "refused"}
        assert projected["explanation"]


def test_missing_source_and_unavailable_producer_stay_unverified(monkeypatch):
    refused = run_case_formal_check(_body(source_text="  ", executed_proof=True, proof_status="verified"))
    assert refused["status"] == "refused"
    assert refused["code"] == "missing_source_text"
    assert refused["execution"] == "unexecuted"
    assert refused["executed_proof"] is False
    assert refused["producer_invoked"] is False
    assert "refused" in refused["explanation"].lower()
    assert "not" in refused["explanation"].lower()

    from integrations.ipfs_datasets import logic
    monkeypatch.setattr(logic, "canonical_compiler_identities", lambda: None)
    unavailable = run_case_formal_check(_body())
    assert unavailable["status"] == "unavailable"
    assert unavailable["code"] == "missing_producer"
    assert unavailable["executed_proof"] is False
    assert unavailable["route"]["outcome"] == "unavailable"
    assert unavailable["route"]["executed_proof"] is False
    assert "unavailable" in unavailable["explanation"].lower()
    assert "not a proof" in unavailable["explanation"].lower()

    stale = run_case_formal_check(_body(current_definition_identity="def-other"))
    assert stale["status"] == "unexecuted"
    assert stale["code"] == "stale_binding"
    assert stale["executed_proof"] is False
    assert "unexecuted" in stale["explanation"].lower()


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
    profile = tmp_path / "ux29-profile"
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


def test_formal_panel_renders_bindings_and_rejects_a_caller_proof(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with _browser(tmp_path, monkeypatch, world.app) as page:
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
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        page.locator("#complaint-case-shell-nav [data-case-task='legal']").click()
        page.wait_for_selector("#legal-formal-run")
        head_before = page.evaluate(
            """async caseId => {
                const response = await fetch('/api/complaint-workspace/session?case_id=' + encodeURIComponent(caseId), {credentials: 'same-origin'});
                const payload = await response.json();
                return payload.encrypted_head || {};
            }""",
            world.journey_case.case_id,
        )
        page.fill("#legal-formal-source", "")
        page.fill("#legal-formal-source-version", "2024-edition")
        page.fill("#legal-formal-definition", "def-retaliation-3")
        page.click("#legal-formal-run")
        page.wait_for_function("document.getElementById('legal-formal-panel').dataset.state === 'refused'")
        assert page.get_attribute("#legal-formal-proof", "data-executed-proof") == "false"
        assert page.get_attribute("#legal-formal-caller", "data-executed-proof") == "false"
        assert page.get_attribute("#legal-formal-caller", "data-rejected") == "true"
        assert "refused" in page.locator("#legal-formal-explanation").inner_text().lower()

        page.fill("#legal-formal-source", STATUTE)
        page.fill("#legal-formal-source-version", "2024-edition")
        page.fill("#legal-formal-definition", "def-retaliation-3")
        page.fill("#legal-formal-requirement", "req-retaliation")
        page.fill("#legal-formal-premise", PREMISE)
        page.click("#legal-formal-run")
        page.wait_for_function("document.getElementById('legal-formal-panel').dataset.sourceVersion === '2024-edition'")
        assert page.get_attribute("#legal-formal-panel", "data-definition-identity") == "def-retaliation-3"
        assert page.get_attribute("#legal-formal-panel", "data-requirement-id") == "req-retaliation"
        assert page.get_attribute("#legal-formal-panel", "data-source-hash") == sha256_utf8(STATUTE)
        assert page.get_attribute("#legal-formal-caller", "data-executed-proof") == "false"
        assert "not a proof" in page.locator("#legal-formal-caller").inner_text().lower()
        premise = page.locator("#legal-formal-premises [data-role='formal-premise']")
        assert premise.get_attribute("data-premise-id") == "premise-panel"
        assert premise.get_attribute("data-text-sha256") == sha256_utf8(PREMISE)
        assert premise.get_attribute("data-executed-proof") == "false"
        explanation = page.locator("#legal-formal-explanation").inner_text().lower()
        assert "proof" in explanation
        executed = page.get_attribute("#legal-formal-proof", "data-executed-proof")
        assert executed in {"true", "false"}
        if executed == "true":
            assert "bound producer" in page.locator("#legal-formal-proof").inner_text().lower()
        else:
            assert "not verified" in page.locator("#legal-formal-proof").inner_text().lower()
        head_after = page.evaluate(
            """async caseId => {
                const response = await fetch('/api/complaint-workspace/session?case_id=' + encodeURIComponent(caseId), {credentials: 'same-origin'});
                const payload = await response.json();
                return payload.encrypted_head || {};
            }""",
            world.journey_case.case_id,
        )
        assert head_after == head_before
