import json
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_browser_sdk_surfaces_legal_search_diagnostics_contract():
    commonjs_sdk = (REPO_ROOT / "static" / "complaint_mcp_sdk.js").read_text(encoding="utf-8")
    esm_sdk = (REPO_ROOT / "static" / "complaint_mcp_sdk.mjs").read_text(encoding="utf-8")
    shell_js = (REPO_ROOT / "static" / "complaint_app_shell.js").read_text(encoding="utf-8")

    for content in (commonjs_sdk, esm_sdk):
        assert "runIntakeChatTurn(userId, message, questionId)" in content
        assert "complaint.run_intake_chat_turn" in content
        assert "getPackagedDocketOperatorDashboard(manifestPath)" in content
        assert "loadPackagedDocketOperatorDashboardReport(manifestPath, reportFormat = 'parsed')" in content
        assert "executePackagedDocketProofRevalidationQueue(manifestPath, options = {})" in content
        assert "persistPackagedDocketProofRevalidationQueue(manifestPath, outputDir, options = {})" in content
        assert "complaint.get_packaged_docket_operator_dashboard" in content
        assert "complaint.load_packaged_docket_operator_dashboard_report" in content
        assert "complaint.execute_packaged_docket_proof_revalidation_queue" in content
        assert "complaint.persist_packaged_docket_proof_revalidation_queue" in content
        assert "_extractToolDiagnostics(payload)" in content
        assert "_buildToolDiagnosticSummary(payload)" in content
        assert "diagnostic_summary: diagnosticSummary" in content
        assert "search_diagnostics" in content
        assert "authorities_diagnostics" in content

    assert "Latest retrieval warning:" in shell_js
    assert "Retrieval warning details:" in shell_js
    assert "diagnostic_summary" in shell_js
    assert "latestToolDiagnosticSummary" in shell_js
    assert "formatToolDiagnosticMeta" in shell_js


@pytest.mark.parametrize("sdk_name", ["complaint_mcp_sdk.js", "complaint_mcp_sdk.mjs"])
def test_proof_sdk_operations_preserve_rpc_arguments_and_results(sdk_name):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the JavaScript SDK")
    script = r"""
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const sdkPath = process.argv[2];
const sdk = sdkPath.endsWith('.mjs')
    ? await import(pathToFileURL(sdkPath).href)
    : createRequire(import.meta.url)(sdkPath);
const storage = new Map();
globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
};
const calls = [];
const proofResult = {
    status: 'ok',
    user_id: 'sdk-user',
    proof_report: { proof_status: 'needs_review', metadata: { degraded_reason: 'offline' } },
    quality_score: { overall_score: 0.5 },
    rendered: '# Proof Report',
    pin_result: { pinned: false, backend: 'unavailable', report_cid: '', lean4_cid: '', coq_cid: '' },
};
let mode = 'ok';
const noDraft = { status: 'no_draft', message: 'Generate a draft first.', proof_report: null, quality_score: null };
const client = new sdk.ComplaintMcpClient({
    fetchImpl: async (url, request) => {
        const rpc = JSON.parse(request.body);
        assert.equal(url, '/api/complaint-workspace/mcp/rpc');
        assert.equal(request.method, 'POST');
        assert.equal(rpc.method, 'tools/call');
        calls.push(rpc.params);
        return {
            ok: true,
            json: async () => mode === 'error'
                ? { error: { message: 'pin refused' } }
                : { result: { structuredContent: mode === 'no_draft' ? noDraft : proofResult } },
        };
    },
});
const cases = [
    ['getDraftProofReport', 'complaint.get_draft_proof_report', { state_code: 'WA' },
        { user_id: 'sdk-user', allow_live_scrape_fallback: false, state_code: 'WA' }],
    ['renderDraftProofReport', 'complaint.render_draft_proof_report', { state_code: 'WA', claim_id: 'claim-4' },
        { user_id: 'sdk-user', state_code: 'WA', claim_id: 'claim-4' }],
    ['pinDraftProofReport', 'complaint.pin_draft_proof_report', { state_code: 'WA', claim_id: 'claim-4' },
        { user_id: 'sdk-user', state_code: 'WA', claim_id: 'claim-4' }],
    ['scoreDraftQuality', 'complaint.score_draft_quality', { state_code: 'WA', persist: false },
        { user_id: 'sdk-user', state_code: 'WA', persist: false }],
    ['improveDraft', 'complaint.improve_draft', { max_suggestions: 1, provider: 'configured-provider' },
        { user_id: 'sdk-user', max_suggestions: 1, provider: 'configured-provider' }],
    ['getProofHistory', 'complaint.get_proof_history', undefined, { user_id: 'sdk-user' }],
];
for (const [method, tool, options, expected] of cases) {
    const originalOptions = options ? { ...options } : undefined;
    const result = await client[method]('sdk-user', options);
    assert.deepEqual(calls.at(-1), { name: tool, arguments: expected });
    assert.deepEqual(result, proofResult);
    assert.deepEqual(options, originalOptions);
    assert.equal(client.getLastToolCall().tool_name, tool);
    assert.equal(client.getLastToolCall().status, 'success');
}
await client.getDraftProofReport('sdk-user');
assert.deepEqual(calls.at(-1).arguments, { user_id: 'sdk-user', allow_live_scrape_fallback: false });
mode = 'no_draft';
assert.deepEqual(await client.getDraftProofReport('sdk-user'), noDraft);
mode = 'error';
await assert.rejects(client.pinDraftProofReport('sdk-user'), /pin refused/);
assert.equal(client.getLastToolCall().tool_name, 'complaint.pin_draft_proof_report');
assert.equal(client.getLastToolCall().status, 'error');
console.log(JSON.stringify({ checked_operations: cases.length, no_draft: true, errors: true }));
"""
    result = subprocess.run(
        [node, "--input-type=module", "-", str(REPO_ROOT / "static" / sdk_name)],
        input=script, text=True, capture_output=True, check=True, timeout=30,
    )
    assert json.loads(result.stdout) == {"checked_operations": 6, "no_draft": True, "errors": True}
