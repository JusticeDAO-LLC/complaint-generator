"""Privacy stays local until a case owner persists purpose consent.

Grok 4.7 receives only the minimized fields named for that purpose. Unlock,
a staff role, development-provider authorization, and omitted flags do not
create consent. Revocation and cancellation are read again before a late
result is shown or admitted.
"""
from __future__ import annotations

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

LATE_WORDING = "SYNTHETIC-LATE-GROK-WORDING"
RESULT_ID = "late-extract-1"


def _csrf(client, credential="synthetic-owner-credential"):
    token = _composed_login(client, credential)
    return {"x-csrf-token": token}


def _read(client, case_id):
    response = client.get(f"/api/cases/{case_id}/processing-consent")
    assert response.status_code == 200, response.text
    return response.json()


def _authorize(client, case_id, generation):
    saved = client.post(
        f"/api/cases/{case_id}/processing-consent",
        headers=_csrf(client),
        json={"purpose": "extract_facts", "mode": "grok_cloud", "explicit_case_purpose": True, "expected_generation": generation},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def _admit(client, case_id, *, generation, consent_generation, result_id=RESULT_ID, extra=None):
    body = {
        "purpose": "extract_facts",
        "consent_generation": consent_generation,
        "result_id": result_id,
        "expected_generation": generation,
    }
    if extra:
        body.update(extra)
    return client.post(
        f"/api/cases/{case_id}/processing-consent/late-result",
        headers=_csrf(client),
        json=body,
    )


def test_local_default_names_minimized_grok_fields_and_rejects_implied_consent(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "api")
    case_id = world.case.case_id
    with TestClient(world.app, base_url="https://testserver") as client:
        _csrf(client)
        initial = _read(client, case_id)
        assert initial["default_processing"] == "local_private"
        assert initial["egress_authorized"] is False
        assert initial["does_not_create_consent"] == {
            "key_unlock": False,
            "staff_role": False,
            "development_provider_authorization": False,
            "omitted_flags": False,
        }
        leaves = initial["minimized_egress"]["extract_facts"]["leaves_the_machine"]
        assert "bounded source_text fragment for this purpose" in leaves
        assert "target_ref for that fragment" in leaves
        assert initial["minimized_egress"]["public_law_citation"]["leaves_the_machine"] == ["public citation text only"]
        assert "complaint text is not copied" in initial["minimized_egress"]["citation_acquisition"]["stays_on_the_machine"][0]

        implied = {
            "key_unlock": {"key_unlocked": True},
            "development_provider_authorization": {"development_provider_authorization": True},
            "staff_role": {"staff_role": "operator"},
        }
        for name, flag in implied.items():
            refused = client.post(
                f"/api/cases/{case_id}/processing-consent",
                headers=_csrf(client),
                json={"purpose": "extract_facts", "mode": "grok_cloud", "explicit_case_purpose": True, "expected_generation": 0, **flag},
            )
            assert refused.status_code == 403, name
            assert refused.json()["error"] in {"consent_not_implied", "request_cannot_mint_authority"}
            assert _read(client, case_id)["egress_authorized"] is False
            assert _read(client, case_id)["generation"] == 0

        omitted = client.post(
            f"/api/cases/{case_id}/processing-consent",
            headers=_csrf(client),
            json={"purpose": "extract_facts", "expected_generation": 0},
        )
        assert omitted.status_code == 403
        assert omitted.json()["error"] == "mode_required"
        assert _read(client, case_id)["egress_authorized"] is False

        with TestClient(world.app, base_url="https://testserver") as lawyer:
            lawyer_headers = _csrf(lawyer, "synthetic-lawyer-credential")
            lawyer_try = lawyer.post(
            f"/api/cases/{case_id}/processing-consent",
            headers=lawyer_headers,
            json={"purpose": "extract_facts", "mode": "grok_cloud", "explicit_case_purpose": True, "expected_generation": 0},
            )
            assert lawyer_try.status_code == 404
            assert lawyer_try.json()["error"] == "missing_case"
        assert _read(client, case_id)["egress_authorized"] is False

        saved = _authorize(client, case_id, 0)
        assert saved["generation"] == 1
        assert saved["decisions"][0]["purpose"] == "extract_facts" or any(
            item["purpose"] == "extract_facts" and item["egress_authorized"] is True for item in saved["decisions"]
        )
        admitted = _admit(client, case_id, generation=1, consent_generation=1)
        assert admitted.status_code == 200, admitted.text
        assert admitted.json()["admitted"] is True
        assert admitted.json()["display_allowed"] is True
        assert admitted.json()["code"] == "current_consent"
        assert "source_text" in " ".join(admitted.json()["minimized_egress"]["leaves_the_machine"])

        revoked = client.post(
            f"/api/cases/{case_id}/processing-consent/revoke",
            headers=_csrf(client),
            json={"purpose": "extract_facts", "expected_generation": 1},
        )
        assert revoked.status_code == 200, revoked.text
        late = _admit(client, case_id, generation=2, consent_generation=1)
        assert late.status_code == 200, late.text
        assert late.json()["admitted"] is False
        assert late.json()["display_allowed"] is False
        assert late.json()["code"] == "consent_revoked"

        again = _authorize(client, case_id, 2)
        generation = again["generation"]
        cancelled = client.post(
            f"/api/cases/{case_id}/processing-consent/late-result/cancel",
            headers=_csrf(client),
            json={"purpose": "extract_facts", "result_id": RESULT_ID, "expected_generation": generation},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["code"] == "consent_cancelled"
        assert cancelled.json()["display_allowed"] is False
        replay = _admit(client, case_id, generation=generation, consent_generation=generation)
        assert replay.status_code == 200, replay.text
        assert replay.json()["admitted"] is False
        assert replay.json()["code"] == "consent_cancelled"
        assert _read(client, case_id)["egress_authorized"] is True

        bare = client.post(
            f"/api/cases/{case_id}/processing-consent/late-result",
            headers=_csrf(client),
            json={"purpose": "extract_facts", "result_id": "late-extract-2", "expected_generation": generation},
        )
        assert bare.status_code == 403
        assert bare.json()["error"] == "consent_not_implied"


def _launch(tmp_path, monkeypatch, world, profile_name):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / profile_name
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
    return page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def test_workspace_explains_egress_and_withholds_late_results(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "browser")
    case_id = world.case.case_id
    page, playwright, context, node, profile, observed = _launch(tmp_path, monkeypatch, world, "ux12-profile")
    try:
        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        page.fill("#case-credential", "synthetic-owner-credential")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/complaint-workspace/auth/login")):
            page.click("#case-login button[type=submit]")
        page.click("#case-list button")
        page.wait_for_function("""() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'owner'""")
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        page.wait_for_selector("#conversation-privacy")
        page.wait_for_function("""() => {
            const actor = document.getElementById('complaint-case-shell-actor');
            const client = window.workspaceClient;
            const shell = window.complaintCaseShell;
            const binding = shell && typeof shell.binding === 'function' ? shell.binding() : null;
            return actor && actor.dataset.relationship === 'owner' && client && client.csrfToken
                && binding && binding.case_id;
        }""")
        privacy = page.locator("#conversation-privacy-default").inner_text()
        minimized = page.locator("#conversation-privacy-minimized").inner_text()
        nonconsent = page.locator("#conversation-privacy-nonconsent").inner_text()
        assert "local private" in privacy.lower()
        assert "source_text" in minimized
        assert "public citation" in minimized
        assert "staff role" in nonconsent.lower()
        assert page.locator("#conversation-late-result").get_attribute("data-display-allowed") == "false"
        assert page.evaluate("() => typeof window.mockApi") == "undefined"

        page.locator("#case-processing-consent").scroll_into_view_if_needed()
        page.fill("#consent-case-id", case_id)
        page.select_option("#consent-purpose", "extract_facts")
        page.click("#consent-refresh")
        page.wait_for_function("""() => document.getElementById('consent-decision-display').dataset.verification === 'verified'
            && document.getElementById('consent-decision-display').dataset.egressAuthorized === 'false'""")
        shown = page.locator("#consent-minimized-egress").inner_text()
        assert "source_text" in shown
        assert "nothing leaves" in shown.lower()
        server = page.evaluate("""async (caseId) => {
            const response = await fetch('/api/cases/' + encodeURIComponent(caseId) + '/processing-consent', {credentials: 'same-origin'});
            const body = await response.json();
            return {status: response.status, egress: body.egress_authorized, generation: body.generation,
                leaves: body.minimized_egress.extract_facts.leaves_the_machine};
        }""", case_id)
        assert server["status"] == 200
        assert server["egress"] is False
        assert "bounded source_text fragment for this purpose" in server["leaves"]

        page.click("#consent-authorize-grok")
        page.wait_for_function("""() => document.getElementById('consent-decision-display').dataset.egressAuthorized === 'true'""")
        authorized = page.locator("#consent-minimized-egress").inner_text()
        assert "Grok 4.7" in authorized
        assert "source_text" in authorized

        payload = {
            "session": {
                "case_id": case_id,
                "original_complaint": {"text": "On May 3 the warehouse denied the accessible-schedule request."},
                "shared_interview": {"pending_inquiry": {
                    "inquiry_id": "inq-ux12",
                    "question": "What happened next?",
                    "revision": 1,
                    "model_proposal": {
                        "record_type": "model_suggestion",
                        "late_result": True,
                        "purpose": "extract_facts",
                        "consent_generation": 1,
                        "result_id": RESULT_ID,
                        "wording": LATE_WORDING,
                    },
                }},
            }
        }
        page.evaluate("""(payload) => window.complaintConversation.project(payload)""", payload)
        withheld = page.locator("#mediator-conversation-log").inner_text()
        assert LATE_WORDING not in withheld
        assert "withheld" in withheld.lower()
        decision = page.evaluate("""async (proposal) => window.complaintConversation.considerLateResult(proposal)""", payload["session"]["shared_interview"]["pending_inquiry"]["model_proposal"])
        assert decision["displayAllowed"] is True
        assert decision["code"] == "current_consent"
        assert LATE_WORDING in page.locator("#mediator-conversation-log").inner_text()
        assert page.locator("#conversation-late-result").get_attribute("data-admission") == "admitted"

        page.evaluate("""() => {
            const pending = window.complaintConversation.refresh();
            window.complaintConversation.cancel();
            if (pending && typeof pending.catch === 'function') pending.catch(() => {});
        }""")
        cancelled = page.evaluate("""async (proposal) => window.complaintConversation.considerLateResult(proposal)""", payload["session"]["shared_interview"]["pending_inquiry"]["model_proposal"])
        assert cancelled["displayAllowed"] is False
        assert cancelled["code"] == "consent_cancelled"
        assert LATE_WORDING not in page.locator("#mediator-conversation-log").inner_text()
        persisted = page.evaluate("""async (caseId) => {
            const response = await fetch('/api/cases/' + encodeURIComponent(caseId) + '/processing-consent/late-result', {
                method: 'POST', credentials: 'same-origin',
                headers: {'content-type': 'application/json', 'x-csrf-token': window.workspaceClient.csrfToken},
                body: JSON.stringify({purpose: 'extract_facts', consent_generation: 1, result_id: 'late-extract-1', expected_generation: 1}),
            });
            return response.json();
        }""", case_id)
        assert persisted["admitted"] is False
        assert persisted["code"] == "consent_cancelled"
    finally:
        _close(playwright, context, node, profile, observed)
