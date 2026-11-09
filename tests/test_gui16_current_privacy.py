"""Current adaptive GUI through real encrypted owner and Chromium boundaries."""
from urllib.parse import quote
import os

import pytest

from tests import gui_native_browser as browser
from tests.test_cimp_gui_15 import _page
from tests.test_cimp_gui_16 import NARRATIVE
from tests.test_cimp_gui_33 import _consent_login
from applications.case_consent_api import CaseConsentService

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _bind_actual_owner(page, world):
    issued = _consent_login(page, world)
    # Observe the real async click handler's completion, not an arbitrary sleep
    # or a fabricated response. The real handler is called exactly once.
    page.add_init_script("""(() => {
        const add = EventTarget.prototype.addEventListener;
        EventTarget.prototype.addEventListener = function(type, listener, ...options) {
            if (this.id === 'adaptive-enter-narrative' && type === 'click' && typeof listener === 'function') {
                const observed = async function(event) {
                    try { return await listener.call(this, event); }
                    finally { window.actualAdaptiveEnterSettled = true; }
                };
                return add.call(this, type, observed, ...options);
            }
            return add.call(this, type, listener, ...options);
        };
    })();""")
    page.goto(browser.SAME_ORIGIN + "/workspace?user_id=" + quote(world.case.tenant_id), wait_until="domcontentloaded")
    page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
    page.evaluate("""async data => {
        window.workspaceClient.setBrowserSession(data.issued);
        window.workspaceClient.setCaseContext(data.case);
        await window.workspaceClient.bootstrapWorkspace(data.case.tenant_id);
    }""", {"issued": issued, "case": {"tenant_id": world.case.tenant_id, "case_id": world.case.case_id,
        "resource_id": world.case.resource_id, "revision": world.case.revision}})
    assert issued["principal_id"] == world.principal.principal_id != world.case.tenant_id


def _enter(page):
    page.fill("#adaptive-narrative", NARRATIVE)
    page.evaluate("window.actualAdaptiveEnterSettled = false")
    page.click("#adaptive-enter-narrative")
    page.wait_for_function("window.actualAdaptiveEnterSettled === true")


def _assert_closed(page, old_inquiry=None):
    assert page.locator("#adaptive-narrative").input_value() == ""
    assert page.locator("#adaptive-answer").input_value() == ""
    assert page.locator("#adaptive-model-fragment").input_value() == ""
    assert page.locator("#adaptive-pending").get_attribute("data-pending") == "false"
    assert not page.locator("#adaptive-pending").get_attribute("data-inquiry-id")
    if old_inquiry:
        assert old_inquiry not in page.locator("#adaptive-pending-meta").inner_text()
        assert old_inquiry not in page.locator("#adaptive-gap-status").inner_text()


@pytest.mark.parametrize("boundary", ["clear", "switch", "logout"])
def test_real_owner_adaptive_dom_is_closed_at_actual_private_boundary(tmp_path, monkeypatch, boundary):
    with _page(tmp_path, monkeypatch, "typed_owner") as (world, page):
        _bind_actual_owner(page, world)
        _enter(page)
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        inquiry = page.locator("#adaptive-pending").get_attribute("data-inquiry-id")
        assert inquiry.startswith("inq-")
        page.fill("#adaptive-answer", "Synthetic private unsent answer")
        page.fill("#adaptive-model-fragment", "Synthetic private unsent fragment")
        if boundary == "switch":
            page.fill("#workspace-switch-user-id", "synthetic-next-user")
            page.click("#workspace-switch-user")
        elif boundary == "logout":
            page.click("#workspace-logout")
        else:
            page.click("#workspace-clear-private-state")
        page.wait_for_function("['cleared','switched','logged-out'].includes(document.body.dataset.workspaceHydrated)")
        _assert_closed(page, inquiry)
        if boundary == "logout":
            assert page.evaluate("async () => (await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'})).status") == 401


def test_real_sdk_completion_clear_cannot_repaint_adaptive_question(tmp_path, monkeypatch):
    """Actual SDK completion event schedules a real clear before GUI admission."""
    with _page(tmp_path, monkeypatch, "typed_owner") as (world, page):
        _bind_actual_owner(page, world)
        page.evaluate("""() => {
            window.clearedAtActualIntakeCompletion = false;
            window.addEventListener('complaint-mcp-sdk-call', event => {
                const detail = event.detail || {};
                if (!window.clearedAtActualIntakeCompletion
                        && detail.tool_name === 'complaint.run_intake_chat_turn' && detail.status === 'success') {
                    window.clearedAtActualIntakeCompletion = true;
                    document.getElementById('workspace-clear-private-state').click();
                }
            });
        }""")
        _enter(page)
        assert page.evaluate("window.clearedAtActualIntakeCompletion") is True
        assert page.get_attribute("body", "data-workspace-hydrated") == "cleared"
        _assert_closed(page)


def test_actual_http_body_cancellation_keeps_dispatch_outcome_unknown(tmp_path, monkeypatch):
    """Cancel a real browser response body; no provider/response is invented."""
    with _page(tmp_path, monkeypatch, "typed_owner") as (world, page):
        world.actual.app.state.case_consent = CaseConsentService(tmp_path / "consent",
            cases=world.actual.cases, key=os.urandom(32), key_id="synthetic-consent-key",
            clock=lambda: 1_700_000_100)
        _bind_actual_owner(page, world)
        _enter(page)
        assert page.get_attribute("#adaptive-pending", "data-pending") == "true"
        choice = page.evaluate("""async caseId => {
            const path='/api/cases/'+encodeURIComponent(caseId)+'/processing-consent';
            const current=await (await fetch(path,{credentials:'same-origin'})).json();
            const response=await fetch(path,{method:'POST',credentials:'same-origin',
                headers:{'content-type':'application/json','x-csrf-token':window.workspaceClient.csrfToken},
                body:JSON.stringify({purpose:'extract_facts',mode:'grok_cloud',explicit_case_purpose:true,
                    expected_generation:current.generation})});
            return {status:response.status,body:await response.json()};
        }""", world.case.case_id)
        assert choice["status"] == 200
        assert any(item["purpose"] == "extract_facts" and item["egress_authorized"] is True
            for item in choice["body"]["decisions"])
        page.fill("#adaptive-model-fragment", "supervisor Alex Rivera fired me")
        page.evaluate("""() => {
            const actual=window.workspaceClient.fetchImpl;
            window.actualDispatchReceipt=null;
            window.workspaceClient.fetchImpl=async (...args) => {
                const response=await actual(...args);
                if(new URL(String(args[0]),location.href).pathname.endsWith('/inference/dispatch')) {
                    const receipt=await response.clone().json();
                    window.actualDispatchReceipt={status:response.status,code:receipt.code,
                        model_dispatched:receipt.model_dispatched};
                    await response.body.cancel();
                }
                return response;
            };
        }""")
        page.click("#adaptive-model-extract")
        page.wait_for_function("document.getElementById('adaptive-model-status').dataset.code === 'inference_unavailable'")
        receipt = page.evaluate("window.actualDispatchReceipt")
        # This control deliberately configures no model transport. The real
        # ASGI receipt proves no provider was invoked; the UI could not read it.
        assert receipt == {"status": 200, "code": "model_transport_unavailable", "model_dispatched": False}
        assert page.get_attribute("#adaptive-model-status", "data-model-dispatched") == "unknown"
        assert "Model not called" not in page.locator("#adaptive-model-status").inner_text()
        assert "not been verified" in page.locator("#adaptive-model-status").inner_text()
