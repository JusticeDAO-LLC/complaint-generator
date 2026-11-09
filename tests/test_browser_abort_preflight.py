"""Reject the reviewed browser-made AbortError, preserving genuine cancellation.

The fixture is the exact evaluate literal extracted from the reviewed UX06
attempt-two source, whose artifact SHA256 is
e628efab24ee13a6ecf7ed01d77ec1e518e15ebc601406163064a58154495346.
Red qualification at source 25091 reused that synthetic literal under canonical
future task UX07, whose installed test module was absent, so an existing
definition guard did not mask this rejection. No provider or candidate browser
code executes in the rejection tests.
"""
from pathlib import Path
import hashlib
import json
import subprocess

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate.browser_http_preflight import inspect_complaint_browser_http

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
SOURCE = Path(__file__).resolve().parents[1]
SPEC = 'docs/task_boards/complaint_gui_ux_overhaul_spec.json'
FIXTURE = SOURCE / 'tests/fixtures/browser_http_guard/ux06_synthetic_abort.py.txt'
CODE = 'fetch_replacement_constructs_abort_error'


def _world(root, body=None, task_id='CIMP-UX-07'):
    spec_bytes = (SOURCE / SPEC).read_bytes()
    spec = json.loads(spec_bytes)
    task = next(t for t in spec['tasks'] if t['id'] == task_id)
    for relative in [SPEC, *task['targets']]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(spec_bytes if relative == SPEC else b'// Synthetic UI fixture\n')
    relative = next(p for p in task['targets'] if p.startswith('tests/') and p.endswith('.py'))
    (root / relative).write_text(FIXTURE.read_text() if body is None else body)
    return task, spec, relative


def test_reviewed_abort_literal_is_rejected_without_executing_browser_code(tmp_path):
    task, spec, relative = _world(tmp_path, task_id='CIMP-UX-06')
    result = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)
    assert result['passed'] is False
    assert result['reason'] == 'synthetic_browser_http_response'
    assert result['findings'] == [{'path': relative, 'line': 16, 'code': CODE}]
    assert result['files'] == [{'path': relative, 'sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest()}]
    assert result['candidate_executed'] is False and result['completion_authority'] is False
    assert str(tmp_path) not in json.dumps(result) and 'The operation was aborted' not in json.dumps(result)


def test_native_adapter_rejects_reviewed_abort_literal_before_executor(tmp_path):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalTask
    from ipfs_accelerate_py.agent_supervisor.validation.proposal_validation import (
        ImplementationProposal, ProposalValidationPolicy, validate_implementation_proposal)
    from ipfs_accelerate_py.agent_supervisor.proof.code_proof_obligations import collect_git_candidate_diff
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import (
        ValidationScheduler, build_declared_validation_plan_graph)
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import sealed_validation_python_runner

    task, spec, relative = _world(tmp_path, 'def synthetic_baseline(page):\n    return page\n')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('init', '-q')
    git('add', '.')
    git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'Synthetic UX baseline')
    baseline = git('rev-parse', 'HEAD')
    (tmp_path / relative).write_bytes(FIXTURE.read_bytes())
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    proposal = ImplementationProposal(task_id=task['id'], accepted_plan_id='plan:synthetic',
        repository_id='repository:sha256:' + hashlib.sha256(str(common).encode()).hexdigest(),
        repository_tree_id=baseline, baseline_id=baseline, objective_id='objective:synthetic',
        context_id='context:synthetic', replay_nonce='synthetic-browser-abort',
        declared_paths=(relative,), candidate_diff=tuple(collect_git_candidate_diff(tmp_path, base_revision=baseline)))
    accepted = validate_implementation_proposal(proposal, policy=ProposalValidationPolicy(allowed_paths=(relative,)))
    assert accepted.accepted, json.dumps(accepted.to_dict(), indent=2)
    commands, graph = build_declared_validation_plan_graph(task['validation_commands'],
        repository_tree_id=baseline, changed_paths=(relative,))
    calls = []
    @sealed_validation_python_runner
    def forbidden_executor(**kwargs):
        calls.append(kwargs)
        pytest.fail('fabricated browser AbortError reached the Native validation executor')
    scheduler = runner.EvidenceValidationScheduler(ValidationScheduler(max_workers=1),
        state_dir=tmp_path / 'private-adapter-evidence', spec=spec, defer_readiness=True)
    scheduler.bind_task(PortalTask(task['id'], task['title'], 'todo', '', 'P0', 'synthetic',
        outputs=tuple(task['targets']), validation=task['validation_commands'],
        canonical_task_cid='synthetic-task-cid'), tmp_path)
    result = scheduler.run_validated(accepted, commands, workspace_path=tmp_path,
        runner=forbidden_executor, environment={}, impact_graph=graph, require_impact_graph=True,
        require_full_validation=True, scope='pre_merge')
    assert calls == [] and result['passed'] is False and result['returncode'] == 78
    assert result['firstparty_completion_authority'] is False
    assert not result.get('completion_authoritative') and not result.get('merge_eligible')
    receipt = result['behavioral_evidence'][0]
    assert receipt['reason'] == 'synthetic_browser_http_response'
    assert receipt['admitted'] is False and receipt['completion'] is False
    assert receipt['browser_http_preflight']['findings'] == [{'path': relative, 'line': 16, 'code': CODE}]
    assert result['results'][0]['preflight_only'] is True
    output = result['results'][0]['output']
    assert CODE in output and relative in output
    assert str(tmp_path) not in output and 'The operation was aborted' not in output
    saved = json.loads((tmp_path / 'private-adapter-evidence/evidence/CIMP-UX-07/local_node_integration.json').read_text())
    assert saved['browser_http_preflight'] == receipt['browser_http_preflight']


@pytest.mark.parametrize('task_id', ['CIMP-UX-04', 'CIMP-UX-05', 'CIMP-UX-06'])
def test_current_real_response_and_abort_instrumentation_remains_allowed(tmp_path, task_id):
    task, spec, relative = _world(tmp_path, task_id=task_id)
    (tmp_path / relative).write_bytes((SOURCE / relative).read_bytes())
    result = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)
    assert result['passed'] is True and result['findings'] == []
    assert result['candidate_executed'] is False


@pytest.mark.parametrize('script', [
    "() => { globalThis.fetch = async (input, options) => { throw new DOMException('cancelled', 'AbortError'); }; }",
    "() => { self.fetch = input => new DOMException(message('first', 'second'), /* actual name */ 'AbortError'); }",
    "() => { window['fetch'] = function (input) { return Promise.reject(new DOMException(JSON.stringify({a:1,b:2}), 'AbortError')); }; }",
])
def test_direct_global_fetch_abort_construction_is_rejected(tmp_path, script):
    body = 'def submitted(page):\n    page.evaluate(expression=' + repr(script) + ')\n'
    task, spec, relative = _world(tmp_path, body)
    result = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)
    assert result['reason'] == 'synthetic_browser_http_response'
    assert result['findings'] == [{'path': relative, 'line': 2, 'code': CODE}]


@pytest.mark.parametrize('script', [
    "() => { window.fetch = input => original(input); const error = new DOMException('cancelled', 'AbortError'); return error.name; }",
    "() => { window.fetch = input => { /* new DOMException('cancelled', 'AbortError') */ return original(input); }; }",
    "() => { window.fetch = input => { const label = \"new DOMException('cancelled', 'AbortError')\"; return original(input); }; }",
    "() => { window.fetch = input => { throw new DOMException('AbortError', 'TimeoutError'); }; }",
    "() => { window.fetch = input => { throw new DOMException(message('AbortError', ['AbortError']), 'TimeoutError'); }; }",
    "() => { window.fetch = async (input, options) => { const response = await original(input, options); const json = response.json.bind(response); response.json = async () => { try {return await json();} catch (error) { window.bodyError = error.name; throw error; } }; return response; }; }",
])
def test_ordinary_domexception_mentions_and_real_read_failures_remain_allowed(tmp_path, script):
    task, spec, _ = _world(tmp_path, 'def submitted(page):\n    page.evaluate(' + repr(script) + ')\n')
    result = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)
    assert result['passed'] is True and result['findings'] == []


def test_unit_fixture_string_and_other_campaign_do_not_gain_browser_policy(tmp_path):
    task, spec, _ = _world(tmp_path, 'def ordinary_unit_case():\n    script = ' + repr(FIXTURE.read_text()) + '\n    assert script\n')
    (tmp_path / 'static/complaint_case_shell.js').write_text(
        "window.fetch = () => { throw new DOMException('production fixture', 'AbortError'); };\n")
    assert inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)['passed']
    assert inspect_complaint_browser_http(tmp_path / 'absent', {'id': 'CIMP-OTHER-07'}, 'pytest tests/unit.py') is None
    changed_spec = {**spec, 'title': 'Different campaign'}
    refused = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=changed_spec)
    assert refused['passed'] is False and refused['reason'] == 'browser_http_preflight_unavailable'


def test_actual_ux06_crosses_host_preflight_and_native_browser(tmp_path):
    from tests.test_browser_http_preflight import (
        test_real_current_ui_checks_cross_host_preflight_and_native_executor as _real_host_browser)
    _real_host_browser(tmp_path, 'CIMP-UX-06')
