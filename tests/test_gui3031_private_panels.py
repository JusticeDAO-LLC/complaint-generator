"""Real encrypted source owners and Chromium panels; no provider or proof claims."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from tests import test_cimp_gui_15 as owner_browser
from tests.test_gui25_26_private_owner_http import _world, _login, _headers
from tests.test_gui31_private_proof_trace import _compiled
from tests.test_cimp_gui_33 import _consent_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@contextmanager
def _private_page(tmp_path, monkeypatch, *, definition=False):
    actual = _world(tmp_path)
    with TestClient(actual.app, base_url="https://testserver") as client:
        csrf = _login(client)
        if definition:
            from pathlib import Path
            import ipfs_datasets_py
            from tests import test_cimp_gui_30 as definition_fixtures
            # Use fixtures beside the actual imported, pinned SDK when the
            # offline controller supplies proper SDK roots explicitly.
            monkeypatch.setattr(definition_fixtures, '_FIXTURE_DIR',
                Path(ipfs_datasets_py.__file__).resolve().parents[1] / 'tests/unit/logic/autoformal')
            from tests.test_gui30_private_owner import _source, _request
            source = _source(client, actual, csrf)
            response = client.post('/api/legal-analysis/' + actual.case.case_id + '/definition-correspondence',
                headers=_headers(actual, csrf), json=_request(client, actual, source))
            assert response.status_code == 200, response.text
            compiled = response.json()
            assert compiled['status'] == 'bound' and compiled['proof'] is False
        else:
            compiled = _compiled(client, actual, csrf)
    attach_static_asset_routes(actual.app)
    attach_core_site_ui_routes(actual.app)
    world = SimpleNamespace(application=actual.app, case=actual.case, principal=actual.owner,
        service=actual.service, actual=actual)
    monkeypatch.setattr(owner_browser, "_typed_world", lambda _path: world)
    with owner_browser._page(tmp_path, monkeypatch, "typed_owner") as (_, page):
        _consent_login(page, world)
        yield world, page, compiled


def _refresh_proof(page, case_id):
    page.fill("#proof-trace-case-id", case_id)
    # A real refresh-button click blurs the edited input before its click
    # handler. Observe that same change event before awaiting the real handler.
    page.locator("#proof-trace-refresh").focus()
    page.evaluate("async () => { await refreshProofTraces(); }")


def test_real_proof_rows_clear_when_actual_encrypted_key_is_locked(tmp_path, monkeypatch):
    with _private_page(tmp_path, monkeypatch) as (world, page, compiled):
        _refresh_proof(page, world.case.case_id)
        assert page.locator(".proof-trace-row").count() == len(compiled["typed_obligations"])
        assert page.locator("[data-green-checkmark='true']").count() == 0
        assert world.service.lock_private_keys()["unlocked"] is False
        page.evaluate("async () => { await refreshProofTraces(); }")
        assert page.get_attribute("#proof-trace-summary", "data-verification") == "unavailable"
        assert page.locator(".proof-trace-row").count() == 0
        assert page.locator("#proof-trace-counterexamples").inner_text() == ""
        assert page.locator("#proof-trace-engines").inner_text() == ""


def test_real_dom_does_not_promote_unissued_executed_label_to_green(tmp_path, monkeypatch):
    """Adversarial label mutation is a negative, never a positive proof fixture."""
    with _private_page(tmp_path, monkeypatch) as (world, page, _):
        _refresh_proof(page, world.case.case_id)
        page.evaluate("""async caseId => {
            const payload=await window.workspaceClient._request('/api/legal-analysis/'+caseId+'/proof-traces',{method:'GET'});
            payload.obligations[0].proof_status='executed';
            payload.obligations[0].green_checkmark=true;
            payload.obligations[0].executed_proof=true;
            renderProofTraces(payload,proofTraceCapture());
        }""", world.case.case_id)
        assert page.locator(".proof-trace-row[data-green-checkmark='true']").count() == 0
        assert page.get_attribute("#proof-trace-summary", "data-proof") == "false"


def test_definition_panel_selects_current_reviewed_source_and_reports_missing_owner_inputs(tmp_path, monkeypatch):
    with _private_page(tmp_path, monkeypatch) as (world, page, _):
        assert page.locator("#definition-correspondence-panel").count() == 1
        page.fill("#definition-case-id", world.case.case_id)
        page.evaluate("async () => { await refreshDefinitionCorrespondence(); }")
        choices = page.locator("#definition-source option").all()
        assert len(choices) >= 1
        source_hash = choices[0].get_attribute("value")
        assert source_hash.startswith("sha256:")
        page.evaluate("async () => { await checkDefinitionCorrespondence(); }")
        summary = page.locator("#definition-summary")
        assert summary.get_attribute("data-proof") == "false"
        assert summary.get_attribute("data-status") in {"incomplete", "failed", "unavailable"}
        assert "input" in summary.inner_text().lower()
        assert page.locator("#definition-source-text").count() == 0


def test_real_recorded_definition_cannot_describe_a_different_selected_source(tmp_path, monkeypatch):
    with _private_page(tmp_path, monkeypatch, definition=True) as (world, page, bound):
        page.fill("#definition-case-id", world.case.case_id)
        page.locator("#definition-refresh").focus()
        page.evaluate("async () => { await refreshDefinitionCorrespondence(); }")
        assert page.locator("#definition-source").input_value() == bound['source_binding']['content_hash']
        assert page.get_attribute("#definition-summary", "data-status") == "recorded"
        assert page.get_attribute("#definition-summary", "data-proof") == "false"
        # Adversarial selection is only a negative: the receipt remains the
        # genuine current Data-owner receipt from the actual encrypted API.
        page.evaluate("""async caseId => {
            const actual=await window.workspaceClient._request('/api/legal-analysis/'+caseId+'/definition-correspondence',{method:'GET'});
            const source=document.getElementById('definition-source');
            const other=document.createElement('option');
            other.value='sha256:'+'f'.repeat(64); other.textContent='Unverified selection';
            source.appendChild(other); source.value=other.value;
            source.dispatchEvent(new Event('change',{bubbles:true}));
            window.definitionStatusImmediatelyAfterChange=document.getElementById('definition-summary').dataset.status;
            definitionSummary(actual,definitionCapture());
        }""", world.case.case_id)
        assert page.evaluate("window.definitionStatusImmediatelyAfterChange") == "unknown"
        assert page.get_attribute("#definition-summary", "data-status") != "recorded"
        assert "No proof or governing law has been established." in page.locator("#definition-summary").inner_text()


@pytest.mark.parametrize("boundary", ["clear", "switch", "logout"])
def test_actual_privacy_boundary_clears_proof_and_definition_private_dom(tmp_path, monkeypatch, boundary):
    with _private_page(tmp_path, monkeypatch) as (world, page, _):
        _refresh_proof(page, world.case.case_id)
        page.fill("#definition-case-id", world.case.case_id)
        page.evaluate("async () => { await refreshDefinitionCorrespondence(); }")
        assert page.locator(".proof-trace-row").count() > 0
        assert page.locator("#definition-source option").count() > 0
        if boundary == "switch":
            page.fill("#workspace-switch-user-id", "synthetic-next-user")
            page.click("#workspace-switch-user")
        else:
            page.click("#workspace-logout" if boundary == "logout" else "#workspace-clear-private-state")
        page.wait_for_function("['cleared','switched','logged-out'].includes(document.body.dataset.workspaceHydrated)")
        assert page.locator(".proof-trace-row").count() == 0
        assert page.locator("#proof-trace-counterexamples").inner_text() == ""
        assert page.locator("#proof-trace-engines").inner_text() == ""
        assert page.locator("#definition-source option").count() == 0
        assert page.locator("#definition-case-id").input_value() == ""
        assert page.locator("#definition-check").is_disabled()
        if boundary == "logout":
            assert page.evaluate("async () => (await fetch('/api/complaint-workspace/auth/session',{credentials:'same-origin'})).status") == 401
