"""Campaign-only source preflight; no model, external network or Native state."""
from pathlib import Path
import json
import subprocess

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
SOURCE = Path(__file__).resolve().parents[1]
SPEC = 'docs/task_boards/complaint_gui_ux_overhaul_spec.json'
FAILED = SOURCE / 'tests/fixtures/browser_http_guard/ux06_synthetic_503.py.txt'


def _world(root, body=None, task_id='CIMP-UX-06'):
    spec = json.loads((SOURCE / SPEC).read_bytes())
    task = next(t for t in spec['tasks'] if t['id'] == task_id)
    for relative in [SPEC, *task['targets']]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((SOURCE / SPEC).read_bytes() if relative == SPEC else b'// Synthetic UI fixture\n')
    test = root / ('tests/test_cimp_ux_' + task_id.rsplit('-', 1)[1] + '.py')
    test.write_text(body or FAILED.read_text())
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    return task, spec


def test_actual_failed_ux06_construct_refuses_before_validation_executor(tmp_path):
    """The extracted 1aac3a36 browser call must never start collection."""
    task, spec = _world(tmp_path)
    calls = []
    def forbidden_executor(**kwargs):
        calls.append(kwargs)
        raise AssertionError('synthetic browser response reached validation executor')
    observed = runner.measure_behavioral_command(tmp_path, tmp_path / 'private-measurement', task,
        task['validation_commands'][0], runner=forbidden_executor, environment={}, timeout_seconds=30,
        context={'campaign_spec_relative': SPEC})
    assert calls == []
    measurement = observed['host_measurement']
    assert measurement['reason'] == 'synthetic_browser_http_response'
    assert measurement['results'] == [] and measurement['completion_authority'] is False
    detail = measurement['browser_http_preflight']
    assert detail['candidate_executed'] is False and detail['completion_authority'] is False
    assert detail['findings'] == [{'path': 'tests/test_cimp_ux_06.py', 'line': 8,
                                 'code': 'fetch_replacement_constructs_response'}]
    rendered = json.dumps(detail)
    assert str(tmp_path) not in rendered and 'catalog_unavailable' not in rendered


@pytest.mark.parametrize('task_id', ['CIMP-UX-03', 'CIMP-UX-04', 'CIMP-UX-05'])
def test_approved_real_browser_sources_remain_admissible(tmp_path, task_id):
    from integrations.ipfs_accelerate.browser_http_preflight import inspect_complaint_browser_http
    task, spec = _world(tmp_path, task_id=task_id)
    relative = next(p for p in task['targets'] if p.startswith('tests/') and p.endswith('.py'))
    (tmp_path / relative).write_bytes((SOURCE / relative).read_bytes())
    result = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)
    assert result['passed'] is True and result['findings'] == []
    assert result['candidate_executed'] is False


@pytest.mark.parametrize('body', [
    "def check(page):\n page.evaluate(\"() => { /* window.fetch = () => new Response('fake'); */ return 'new Response'; }\")\n",
    "def check(page):\n source = \"window.fetch = () => new Response('fixture');\"\n assert source\n",
    "def check(page):\n page.evaluate(\"() => { const response = new Response('ordinary object'); return response.status; }\")\n",
    "def check(page):\n page.evaluate(\"() => { const original = window.fetch.bind(window); window.fetch = async (input, options) => { const response = await original(input, options); const read = response.json.bind(response); response.json = async () => await read(); return response; }; }\")\n",
    "def check(page):\n page.evaluate(\"() => { window.fetch = (url) => original(url)\\n const copy = new Response('ordinary object'); return copy.status; }\")\n",
])
def test_comments_unit_strings_and_actual_response_instrumentation_are_not_rejected(tmp_path, body):
    from integrations.ipfs_accelerate.browser_http_preflight import inspect_complaint_browser_http
    task, spec = _world(tmp_path, body)
    assert inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)['passed']


@pytest.mark.parametrize('change', ['spec', 'task', 'command', 'alias'])
def test_scope_cannot_be_changed_by_candidate_metadata_or_path_alias(tmp_path, change):
    from integrations.ipfs_accelerate.browser_http_preflight import inspect_complaint_browser_http
    task, spec = _world(tmp_path)
    command = task['validation_commands'][0]
    if change == 'spec':
        (tmp_path / SPEC).write_text('{}')
    elif change == 'task':
        task = {**task, 'targets': ['tests/test_cimp_ux_06.py']}
    elif change == 'command':
        command = 'python -m pytest -q tests/test_unrelated.py'
    else:
        test = tmp_path / 'tests/test_cimp_ux_06.py'
        other = tmp_path / 'copied-fixture.py'
        other.write_bytes(test.read_bytes()); test.unlink(); test.symlink_to(other)
    result = inspect_complaint_browser_http(tmp_path, task, command, campaign_spec=spec)
    assert result['passed'] is False and result['reason'] == 'browser_http_preflight_unavailable'
    assert result['candidate_executed'] is False and str(tmp_path) not in json.dumps(result)


def test_other_campaigns_and_non_ui_tasks_keep_ordinary_unit_fixtures(tmp_path):
    from integrations.ipfs_accelerate.browser_http_preflight import inspect_complaint_browser_http
    assert inspect_complaint_browser_http(tmp_path, {'id': 'CIMP-OTHER-06'}, 'pytest tests/unit.py') is None
    task, spec = _world(tmp_path, task_id='CIMP-UX-65')
    assert inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec) is None


@pytest.mark.parametrize('script', [
    "() => { globalThis.fetch = async (url, opts) => new Response('fake', {status:503}); }",
    "() => { window['fetch'] = (url) => { return new Response('fake'); }; }",
    "() => { self.fetch = function (url) { /* new Promise() */ return new Response('fake'); }; }",
])
def test_direct_function_and_arrow_response_replacements_are_found(tmp_path, script):
    from integrations.ipfs_accelerate.browser_http_preflight import inspect_complaint_browser_http
    task, spec = _world(tmp_path, 'def browser_case(page):\n page.add_init_script(' + repr(script) + ')\n')
    result = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)
    assert result['reason'] == 'synthetic_browser_http_response'
    assert len(result['findings']) == 1 and result['findings'][0]['line'] == 2


@pytest.mark.parametrize('method,keyword', [('evaluate', 'expression'), ('evaluate_handle', 'expression'),
                                         ('wait_for_function', 'expression'), ('add_init_script', 'script')])
def test_real_browser_keyword_argument_and_finding_bound(tmp_path, method, keyword):
    from integrations.ipfs_accelerate.browser_http_preflight import inspect_complaint_browser_http
    script = "() => { window.fetch = () => new Response('synthetic'); }"
    body = 'def browser_case(page):\n' + ''.join(
        ' page.' + method + '(' + keyword + '=' + repr(script) + ')\n' for _ in range(20))
    task, spec = _world(tmp_path, body)
    result = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)
    assert result['reason'] == 'synthetic_browser_http_response' and len(result['findings']) == 16
    assert result['findings'][0]['line'] == 2 and result['findings'][-1]['line'] == 17


def test_escaped_script_newlines_keep_diagnostic_within_the_python_literal(tmp_path):
    from integrations.ipfs_accelerate.browser_http_preflight import inspect_complaint_browser_http
    script = "() => {\n window.fetch = () => {\n return new Response('synthetic'); }; }"
    task, spec = _world(tmp_path, 'def browser_case(page):\n page.evaluate(' + repr(script) + ')\n')
    result = inspect_complaint_browser_http(tmp_path, task, task['validation_commands'][0], campaign_spec=spec)
    assert result['reason'] == 'synthetic_browser_http_response'
    assert result['findings'] == [{'path': 'tests/test_cimp_ux_06.py', 'line': 2,
                                 'code': 'fetch_replacement_constructs_response'}]


@pytest.mark.parametrize('spec_state', ['missing', 'changed'])
def test_unrelated_actual_native_workflow_does_not_depend_on_ux_spec(tmp_path, monkeypatch, spec_state):
    from integrations.ipfs_accelerate import browser_http_preflight as guard
    from tests.test_improvement_evidence_gate import _task, _gate, _observation, _write_output
    installed = tmp_path / 'synthetic-installed-root'
    installed.mkdir()
    if spec_state == 'changed':
        spec_path = installed / SPEC
        spec_path.parent.mkdir(parents=True)
        spec_path.write_bytes((SOURCE / SPEC).read_bytes() + b'\n')
    monkeypatch.setattr(guard, '_SOURCE_ROOT', installed)
    legacy = tmp_path / 'other-campaign'
    task = _task()
    _write_output(legacy, task['id'])
    observed, _, _ = _gate(legacy, task, _observation(legacy), _return_measurement=True)
    measured = observed['host_measurement']
    assert measured['reason'] == '' and measured['browser_http_preflight'] is None
    assert len(measured['cases']) == 2 and all(c['outcome'] == 'passed' for c in measured['cases'])
    assert len(measured['kernel_network_guard']['proofs']) == 2
    assert measured['source_unchanged'] is True and measured['completion_authority'] is False
    assert not any(p.endswith('/' + SPEC) for p in measured['validation_bootstrap']['before'])
    ui_task, ui_spec = _world(tmp_path / 'ux-campaign')
    refused = guard.inspect_complaint_browser_http(tmp_path / 'ux-campaign', ui_task,
        ui_task['validation_commands'][0], campaign_spec=ui_spec)
    assert refused['passed'] is False and refused['reason'] == 'browser_http_preflight_unavailable'


def test_actual_native_adapter_refuses_accepted_candidate_without_starting_executor(tmp_path):
    import hashlib
    from integrations.ipfs_accelerate.improvement_runner import EvidenceValidationScheduler
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalTask
    from ipfs_accelerate_py.agent_supervisor.validation.proposal_validation import (
        ImplementationProposal, ProposalValidationPolicy, validate_implementation_proposal)
    from ipfs_accelerate_py.agent_supervisor.proof.code_proof_obligations import collect_git_candidate_diff
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import (
        ValidationScheduler, build_declared_validation_plan_graph)
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import sealed_validation_python_runner
    task, spec = _world(tmp_path, 'def rejected_browser_case(page):\n return page\n')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'Synthetic UX baseline')
    baseline = git('rev-parse', 'HEAD')
    relative = 'tests/test_cimp_ux_06.py'
    (tmp_path / relative).write_bytes(FAILED.read_bytes())
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    entries = tuple(collect_git_candidate_diff(tmp_path, base_revision=baseline))
    proposal = ImplementationProposal(task_id=task['id'], accepted_plan_id='plan:synthetic',
        repository_id='repository:sha256:' + hashlib.sha256(str(common).encode()).hexdigest(),
        repository_tree_id=baseline, baseline_id=baseline, objective_id='objective:synthetic',
        context_id='context:synthetic', replay_nonce='synthetic-browser-response',
        declared_paths=(relative,), candidate_diff=entries)
    accepted = validate_implementation_proposal(proposal, policy=ProposalValidationPolicy(allowed_paths=(relative,)))
    assert accepted.accepted, json.dumps(accepted.to_dict(), indent=2)
    commands, graph = build_declared_validation_plan_graph(task['validation_commands'],
        repository_tree_id=baseline, changed_paths=(relative,))
    calls = []
    @sealed_validation_python_runner
    def forbidden_executor(**kwargs):
        calls.append(kwargs)
        raise AssertionError('Native validation Popen boundary must not be entered')
    scheduler = EvidenceValidationScheduler(ValidationScheduler(max_workers=1),
        state_dir=tmp_path / 'private-adapter-evidence', spec=spec, defer_readiness=True)
    scheduler.bind_task(PortalTask(task['id'], task['title'], 'todo', '', 'P0', 'synthetic',
        outputs=tuple(task['targets']), validation=task['validation_commands'],
        canonical_task_cid='synthetic-task-cid'), tmp_path)
    result = scheduler.run_validated(accepted, commands, workspace_path=tmp_path,
        runner=forbidden_executor, environment={}, impact_graph=graph, require_impact_graph=True,
        require_full_validation=True, scope='pre_merge')
    assert result['passed'] is False and result['returncode'] == 78 and calls == []
    assert result['firstparty_completion_authority'] is False
    assert not result.get('completion_authoritative') and not result.get('merge_eligible')
    receipt = result['behavioral_evidence'][0]
    assert receipt['reason'] == 'synthetic_browser_http_response'
    assert receipt['admitted'] is False and receipt['completion'] is False
    assert result['results'][0]['preflight_only'] is True
    output = result['results'][0]['output']
    assert relative in output and 'fetch_replacement_constructs_response' in output
    assert str(tmp_path) not in output and 'catalog_unavailable' not in output
    saved = json.loads((tmp_path / 'private-adapter-evidence/evidence/CIMP-UX-06/local_node_integration.json').read_text())
    assert saved['browser_http_preflight'] == receipt['browser_http_preflight']


@pytest.mark.parametrize('task_id', ['CIMP-UX-04', 'CIMP-UX-05'])
def test_real_current_ui_checks_cross_host_preflight_and_native_executor(tmp_path, task_id):
    """Real ASGI/Chromium cases retain their cancellation/body-reader probes."""
    import os
    import shlex
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import (
        build_validation_environment, validation_environment_for_runner)
    spec = json.loads((SOURCE / SPEC).read_bytes())
    task = next(t for t in spec['tasks'] if t['id'] == task_id)
    sdk = Path(native.__file__).resolve().parents[3]
    gitlink = subprocess.check_output(['git', '-C', str(SOURCE), 'ls-tree', 'HEAD',
        'external/ipfs_accelerate_py'], text=True).split()[2]
    actual_head = subprocess.check_output(['git', '-C', str(sdk), 'rev-parse', 'HEAD'], text=True).strip()
    assert gitlink == actual_head
    executor = native.PortalImplementationDaemon._validation_command_runner
    env = build_validation_environment(dict(os.environ))
    roots = [SOURCE, sdk, sdk.parent / 'ipfs_datasets_py', sdk.parent / 'ipfs_kit_py',
             Path(pytest.__file__).resolve().parents[1]]
    env['PYTHONPATH'] = os.pathsep.join(map(str, roots))
    env = validation_environment_for_runner(env, executor)
    command = ('PYTHONPATH=' + shlex.quote(env['PYTHONPATH']) + ' ' + task['validation_commands'][0]
               + ' --basetemp=' + shlex.quote(str(tmp_path / 'private-nested-pytest')))
    observed = runner.measure_behavioral_command(SOURCE, tmp_path / 'actual-host-run', task, command,
        runner=executor, environment=env, timeout_seconds=300,
        declared_command=task['validation_commands'][0], campaign_spec=spec)
    measured = observed['host_measurement']
    assert measured['reason'] == '', measured['run_path']
    assert measured['browser_http_preflight']['passed'] is True
    assert measured['source_unchanged'] is True
    assert measured['cases'] and all(c['outcome'] == 'passed' for c in measured['cases'])
    assert len(measured['kernel_network_guard']['proofs']) == 2
    assert measured['trusted_executor']['canonical_native_identity'] is True
    assert measured['completion_authority'] is False
