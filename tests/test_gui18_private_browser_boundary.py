"""An actual SDK correction completion cannot repaint a cleared private view."""
import pytest
from fastapi.testclient import TestClient

from tests.test_cimp_gui_15 import _page
from tests.test_gui16_current_privacy import _bind_actual_owner
from tests.test_gui18_private_publication import ANSWER, CORRECTION
from tests.test_cimp_gui_14 import _composed_login, _composed_headers

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_actual_sdk_correction_completion_clear_cannot_repaint_private_graph(tmp_path, monkeypatch):
    with _page(tmp_path, monkeypatch, 'typed_owner') as (world, page):
        _bind_actual_owner(page, world)
        page.fill('#adaptive-narrative', 'On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns.')
        page.evaluate('async () => { await enterAdaptiveNarrative(); }')
        assert page.get_attribute('#adaptive-pending', 'data-pending') == 'true'
        page.fill('#adaptive-answer', ANSWER)
        page.evaluate("async () => { await answerAdaptiveInquiry('answer'); }")
        assert page.locator('#factual-correction-target').input_value()
        assert page.locator('#factual-correction-graph-revision').input_value()
        assert page.locator('#factual-correction-actor').input_value() == world.principal.principal_id
        page.fill('#factual-correction-replacement', CORRECTION)
        page.evaluate("""() => {
            window.clearedAtActualCorrectionCompletion = false;
            window.addEventListener('complaint-mcp-sdk-call', event => {
                const detail = event.detail || {};
                if (!window.clearedAtActualCorrectionCompletion
                        && detail.tool_name === 'complaint.run_intake_chat_turn' && detail.status === 'success') {
                    window.clearedAtActualCorrectionCompletion = true;
                    document.getElementById('workspace-clear-private-state').click();
                }
            });
        }""")
        page.evaluate('async () => { await applyFactualCorrection(); }')
        assert page.evaluate('window.clearedAtActualCorrectionCompletion') is True
        assert page.get_attribute('body', 'data-workspace-hydrated') == 'cleared'
        for field in ['replacement', 'graph-revision', 'session-revision', 'target', 'actor']:
            assert page.locator('#factual-correction-' + field).input_value() == ''
        assert page.locator('#factual-correction').get_attribute('data-prior-answer') is None
        assert page.locator('#factual-correction-status').inner_text() == 'No correction has been applied.'
        assert page.get_attribute('#adaptive-pending', 'data-pending') == 'false'
        # A fresh real authorized HTTP read proves the completion was an
        # applied encrypted correction, not an invented SDK event or packet.
        with TestClient(world.actual.app, base_url='https://testserver') as client:
            _composed_login(client)
            response = client.get('/api/complaint-workspace/session', headers=_composed_headers(world.case))
            assert response.status_code == 200, response.text
            assert CORRECTION in [row.get('answer') for row in response.json()['session']['intake_history']]
