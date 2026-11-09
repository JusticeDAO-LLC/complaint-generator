"""Bounded inference progress renders observed lifecycle only.

Retries stay finite and idempotent. A partial provider payload cannot mark
legal requirements supported or turn revoked remote processing back on.
WS/SSE streaming is not claimed.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_unconsented_model_click_shows_refusal_revision_and_no_percent(tmp_path, monkeypatch):
    from tests.test_cimp_gui_15 import _page

    with _page(tmp_path, monkeypatch) as (_world, page):
        root = page.locator("#bounded-inference-progress")
        assert root.get_attribute("data-task") == "CIMP-GUI-35"
        assert root.get_attribute("data-lifecycle") == "idle"
        assert root.get_attribute("data-percent") == ""
        assert root.get_attribute("data-fabricated-progress") == "false"
        assert root.get_attribute("data-requirements-supported") == "false"
        assert root.get_attribute("data-streaming") == "false"
        assert "percent" not in root.inner_text().lower()
        page.fill("#adaptive-model-fragment", "supervisor Alex Rivera fired me")
        page.click("#adaptive-model-extract")
        page.wait_for_function("document.getElementById('bounded-inference-progress').dataset.lifecycle === 'refused'")
        assert page.get_attribute("#bounded-inference-progress", "data-percent") == ""
        assert page.get_attribute("#bounded-inference-progress", "data-requirements-supported") == "false"
        assert page.get_attribute("#bounded-inference-status", "data-code") == "case_purpose_consent_required"
        assert "unobserved" in page.locator("#bounded-inference-revision").inner_text()
        assert page.get_attribute("#adaptive-model-status", "data-model-dispatched") == "false"
        assert page.evaluate("window.adaptiveModelAttempts") == 0
        page.click("#bounded-inference-cancel")
        assert page.get_attribute("#bounded-inference-progress", "data-lifecycle") == "refused"
        page.click("#bounded-inference-retry")
        assert page.get_attribute("#bounded-inference-status", "data-code") == "retry_not_applicable"


def test_sdk_cancel_rate_limit_timeout_retry_cap_partial_and_revision(tmp_path, monkeypatch):
    from tests.test_cimp_gui_15 import _page

    with _page(tmp_path, monkeypatch) as (_world, page):
        observed = page.evaluate("""async () => {
            const classic = window.ComplaintMcpSdk;
            const esm = await import('/static/complaint_mcp_sdk.mjs');
            const runs = [];
            for (const sdk of [classic, esm]) {
                let release = null;
                const gate = new Promise((resolve) => { release = resolve; });
                const calls = [];
                const responses = [
                    () => new Promise(() => {}),
                    () => ({ok: false, status: 429, json: async () => ({})}),
                    () => ({ok: true, status: 200, json: async () => ({status: 'timeout', code: 'deadline_expired', bound_session_revision: 4, requirements_satisfied: true})}),
                    () => ({ok: true, status: 200, json: async () => ({status: 'unavailable', code: 'model_transport_unavailable', session_revision: 4})}),
                    () => ({ok: true, status: 200, json: async () => ({status: 'refused', code: 'consent_revoked', remote_processing_revoked: true, bound_session_revision: 5})}),
                    () => ({ok: true, status: 200, json: async () => ({status: 'partial', partial: true, code: 'partial_response', requirements_satisfied: true, remote_processing_enabled: true, reenable_remote_processing: true, bound_session_revision: 9, output: 'not-support'})}),
                ];
                const client = new sdk.ComplaintMcpClient({
                    origin: location.origin,
                    fetchImpl: async (_path, options) => {
                        calls.push(options && options.body);
                        const signal = options && options.signal;
                        if (calls.length === 1) {
                            return await new Promise((_resolve, reject) => {
                                const abort = () => {
                                    const error = new Error('aborted');
                                    error.name = 'AbortError';
                                    reject(error);
                                };
                                if (signal && signal.aborted) abort();
                                else if (signal) signal.addEventListener('abort', abort, {once: true});
                                release();
                            });
                        }
                        const next = responses[calls.length - 1];
                        return await next();
                    },
                });
                const seen = [];
                const body = {purpose: 'extract_facts', inputs: {source_text: 'fragment', target_ref: 'entity-1'}};
                const pending = client.dispatchBoundedGuiInference(body, {onView: (view) => seen.push(view.lifecycle)});
                await gate;
                assertDispatching(seen);
                const cancelled = await client.cancelBoundedGuiInference();
                const settled = await pending;
                const limited = await client.dispatchBoundedGuiInference(body);
                const again = await client.dispatchBoundedGuiInference(body);
                const timed = await client.dispatchBoundedGuiInference(body, {retry: true});
                const unavailable = await client.dispatchBoundedGuiInference(body, {retry: true});
                const exhausted = await client.dispatchBoundedGuiInference(body, {retry: true});
                const blocked = await client.dispatchBoundedGuiInference(body, {retry: true});
                const callsAfterCap = calls.length;
                const revoked = await client.dispatchBoundedGuiInference({purpose: 'extract_facts', inputs: {source_text: 'other', target_ref: 'entity-1'}});
                const partial = await client.dispatchBoundedGuiInference({purpose: 'extract_facts', inputs: {source_text: 'partial-fragment', target_ref: 'entity-1'}});
                const repeated = await client.dispatchBoundedGuiInference({purpose: 'extract_facts', inputs: {source_text: 'partial-fragment', target_ref: 'entity-1'}});
                runs.push({
                    seen, cancelled, settled, limited, again, timed, unavailable, exhausted, blocked, revoked, partial, repeated,
                    calls: calls.length, callsAfterCap,
                });
            }
            function assertDispatching(seen) {
                if (!seen.includes('dispatching')) throw new Error('missing dispatching');
            }
            return runs;
        }""")
        assert len(observed) == 2
        for item in observed:
            assert item["seen"][0] == "dispatching"
            assert item["cancelled"]["lifecycle"] == "cancelled"
            assert item["settled"]["lifecycle"] == "cancelled"
            assert item["cancelled"]["percent"] is None
            assert item["cancelled"]["requirements_supported"] is False
            assert item["cancelled"]["fabricated_progress"] is False
            assert item["limited"]["lifecycle"] == "rate_limited"
            assert item["limited"]["retryable"] is True
            assert item["again"] == item["limited"]
            assert item["timed"]["lifecycle"] == "timeout"
            assert item["timed"]["revision"] == 4
            assert item["timed"]["requirements_supported"] is False
            assert item["timed"]["retry_count"] == 1
            assert item["unavailable"]["lifecycle"] == "unavailable"
            assert item["unavailable"]["revision"] == 4
            assert item["unavailable"]["retry_count"] == 2
            assert item["exhausted"]["lifecycle"] == "retry_exhausted"
            assert item["blocked"]["code"] == "retry_not_applicable"
            assert item["callsAfterCap"] == 4
            assert item["revoked"]["lifecycle"] == "refused"
            assert item["revoked"]["remote_processing"] == "revoked"
            assert item["revoked"]["revision"] == 5
            assert item["partial"]["lifecycle"] == "partial"
            assert item["partial"]["requirements_supported"] is False
            assert item["partial"]["remote_processing"] == "revoked"
            assert item["partial"]["revision"] == 9
            assert "not-support" not in str(item["partial"])
            assert item["repeated"]["lifecycle"] == "partial"
            assert item["calls"] == 6
            page.evaluate("""view => window.renderBoundedInferenceProgress(view)""", item["partial"])
            assert page.get_attribute("#bounded-inference-progress", "data-lifecycle") == "partial"
            assert page.get_attribute("#bounded-inference-progress", "data-revision") == "9"
            assert page.get_attribute("#bounded-inference-progress", "data-requirements-supported") == "false"
            assert page.get_attribute("#bounded-inference-progress", "data-remote-processing") == "revoked"
            assert page.get_attribute("#bounded-inference-progress", "data-percent") == ""
            assert page.get_attribute("#bounded-inference-progress", "data-streaming") == "false"
