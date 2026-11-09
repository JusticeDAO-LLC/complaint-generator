"""Closed diagnostics preserve the existing behavioral-definition refusal."""
from pathlib import Path
import ast
import json
import pytest

from integrations.ipfs_accelerate import improvement_runner as runner

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _world(tmp_path, original, candidate):
    trusted, root = tmp_path / 'installed', tmp_path / 'candidate'
    relative = 'tests/test_guarded.py'
    for place in (trusted, root):
        (place / 'tests').mkdir(parents=True)
    (trusted / relative).write_text(original)
    if candidate is not None:
        (root / relative).write_text(candidate)
    return root, trusted, relative


def test_changed_definition_names_are_visible_without_source_or_absolute_paths(tmp_path):
    root, trusted, relative = _world(tmp_path, 'def _wait_for_cleanup(pids):\n return False\n',
        'def _wait_for_cleanup(pids):\n return True\n')
    with pytest.raises(ValueError, match='^existing_behavioral_definition_changed$') as caught:
        runner._preserve_existing_behavioral_definitions(root, [relative], trusted_root=trusted)
    detail = caught.value.diagnostics
    assert detail['issues'] == [{'path': relative, 'definition': '_wait_for_cleanup', 'change': 'changed'}]
    rendered = json.dumps(detail)
    assert str(tmp_path) not in rendered and 'return True' not in rendered and 'return False' not in rendered
    assert detail['candidate_executed'] is False and detail['completion_authority'] is False


@pytest.mark.parametrize('kind,body,name', [
    ('missing', 'def added(): pass\n', 'TestOriginal.test_keep'),
    ('duplicate', 'class TestOriginal:\n def test_keep(self): pass\n def test_keep(self): pass\n', 'TestOriginal.test_keep'),
    ('parse_failed', 'def invalid(:\n', ''),
    ('source_unavailable', None, ''),
])
def test_closed_missing_duplicate_and_unreadable_codes(tmp_path, kind, body, name):
    root, trusted, relative = _world(tmp_path, 'class TestOriginal:\n def test_keep(self): pass\n', body)
    with pytest.raises(ValueError, match='^existing_behavioral_definition_changed$') as caught:
        runner._preserve_existing_behavioral_definitions(root, [relative], trusted_root=trusted)
    issues = caught.value.diagnostics['issues']
    assert any(i['change'] == kind and (not name or i['definition'] == name) for i in issues)
    assert all(set(i) == {'path', 'definition', 'change'} for i in issues)


def test_many_changes_are_bounded_and_additions_still_pass(tmp_path):
    original = ''.join(f'def test_case_{i}():\n return {i}\n' for i in range(40))
    root, trusted, relative = _world(tmp_path, original, original.replace(' return ', ' assert '))
    with pytest.raises(ValueError) as caught:
        runner._preserve_existing_behavioral_definitions(root, [relative], trusted_root=trusted)
    assert len(caught.value.diagnostics['issues']) == 16 and caught.value.diagnostics['truncated'] is True
    (root / relative).write_text(original + 'def test_added():\n assert True\n')
    assert runner._preserve_existing_behavioral_definitions(root, [relative], trusted_root=trusted)[0]['preserved_definition_count'] == 40


def test_real_host_gate_refuses_changed_cleanup_before_execution_and_publishes_only_closed_diagnostic(tmp_path):
    import hashlib, os, shlex, subprocess
    from types import SimpleNamespace
    from tests.test_improvement_evidence_gate import _task, _gate, _spec, _observation, _write_output, COMMAND
    from tests.test_validation_python_globals import _git
    from ipfs_accelerate_py.agent_supervisor.validation.proposal_validation import (
        ImplementationProposal, ProposalValidationPolicy, validate_implementation_proposal)
    from ipfs_accelerate_py.agent_supervisor.proof.code_proof_obligations import collect_git_candidate_diff
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalTask
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler, build_declared_validation_plan_graph
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import sealed_validation_python_runner
    task = _task(); _write_output(tmp_path, task['id'])
    _, executor, environment = _gate(tmp_path, task, _observation(tmp_path, task['id']), _return_measurement=True)
    relative = 'tests/gui_native_browser.py'
    original = (Path(runner.__file__).resolve().parents[2] / relative).read_text()
    path = tmp_path / relative; path.write_text(original)
    _git(tmp_path, 'add', '.')
    _git(tmp_path, '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'Synthetic trusted baseline')
    baseline = _git(tmp_path, 'rev-parse', 'HEAD')
    task['targets'].append(relative)
    node = next(n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef) and n.name == '_wait_for_cleanup')
    lines = original.splitlines(keepends=True)
    altered = ''.join(lines[:node.lineno]) + '    return {"cleaned": True}\n' + ''.join(lines[node.end_lineno:])
    calls = []
    @sealed_validation_python_runner
    def executor_spy(**kwargs):
        calls.append(kwargs['spec'].command)
        spec = kwargs['spec']
        kwargs['spec'] = SimpleNamespace(command=spec.command.replace(' -m pytest ', ' -m pytest -p complaint_fixture_guard ', 1), raw_command=spec.raw_command)
        return executor(**kwargs)
    def run(body, nonce):
        path.write_text(body)
        common = Path(_git(tmp_path, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
        entries = tuple(e for e in collect_git_candidate_diff(tmp_path, base_revision=baseline) if e.new_path == relative)
        assert len(entries) == 1
        proposal = ImplementationProposal(task_id=task['id'], accepted_plan_id='plan:synthetic',
            repository_id='repository:sha256:' + hashlib.sha256(str(common).encode()).hexdigest(),
            repository_tree_id=baseline, baseline_id=baseline, objective_id='objective:synthetic',
            context_id='context:synthetic', replay_nonce=nonce, declared_paths=(relative,), candidate_diff=entries)
        accepted = validate_implementation_proposal(proposal, policy=ProposalValidationPolicy(allowed_paths=(relative,)))
        assert accepted.accepted
        commands, graph = build_declared_validation_plan_graph(['PYTHONPATH=' + shlex.quote(environment['PYTHONPATH']) + ' ' + COMMAND], repository_tree_id=baseline, changed_paths=(relative,))
        scheduler = runner.EvidenceValidationScheduler(ValidationScheduler(max_workers=1), state_dir=tmp_path / ('evidence-' + nonce), spec=_spec(task), defer_readiness=True)
        native_task = PortalTask(task['id'], 'Synthetic definition diagnostic fixture', 'todo', '', 'P0', 'synthetic', outputs=tuple(task['targets']), validation=[COMMAND], canonical_task_cid='synthetic-task-cid')
        scheduler.bind_task(native_task, tmp_path)
        return scheduler.run_validated(accepted, commands, workspace_path=tmp_path, runner=executor_spy, environment=environment, impact_graph=graph, require_impact_graph=True, require_full_validation=True, scope='pre_merge')
    refused = run(altered, 'changed')
    assert refused['passed'] is False and refused['returncode'] == 78 and calls == [], {k:refused.get(k) for k in ('reason','error','returncode','results')}
    receipt = refused['behavioral_evidence'][0]
    assert receipt['reason'] == 'existing_behavioral_definition_changed'
    detail = receipt['behavioral_definition_diagnostic']
    saved = json.loads((tmp_path / 'evidence-changed' / 'evidence' / task['id'] / 'local_node_integration.json').read_text())
    assert saved['behavioral_definition_diagnostic'] == detail
    measurement = next((tmp_path / 'evidence-changed' / 'evidence-runs').glob('measured-*/measurement.json'))
    assert json.loads(measurement.read_text())['behavioral_definition_diagnostic'] == detail
    assert {'path': relative, 'definition': '_wait_for_cleanup', 'change': 'changed'} in detail['issues']
    native_output = refused['results'][0]['output']
    assert relative in native_output and '_wait_for_cleanup' in native_output and len(native_output) < 8192
    assert str(tmp_path) not in native_output and 'return {"cleaned"' not in native_output
    assert refused['results'][0]['preflight_only'] is True
    fixed = run(original + '\ndef _new_bounded_cleanup_probe():\n return None\n', 'additive')
    assert fixed['passed'] is True and fixed['returncode'] == 0 and len(calls) == 2
    assert fixed['behavioral_evidence'][0]['host_measurement']['behavioral_definition_diagnostic'] is None


@pytest.mark.parametrize('kind', ['invalid_path', 'alias'])
def test_refused_source_locators_do_not_expose_foreign_paths(tmp_path, kind):
    root, trusted, relative = _world(tmp_path, 'def kept(): pass\n', 'def kept(): pass\n')
    if kind == 'invalid_path':
        relative = 'tests/../../outside_namespace.py'
    else:
        (root / relative).unlink()
        (root / relative).symlink_to(trusted / relative)
    with pytest.raises(ValueError) as caught:
        runner._preserve_existing_behavioral_definitions(root, [relative], trusted_root=trusted)
    detail = caught.value.diagnostics
    assert str(trusted) not in json.dumps(detail)
    assert detail['issues'][0]['change'] == ('invalid_path' if kind == 'invalid_path' else 'source_unavailable')
    if kind == 'invalid_path':
        assert detail['issues'][0]['path'] == '<unavailable>'


def test_diagnostic_projection_rejects_freeform_paths_names_and_codes():
    detail = runner._BehavioralDefinitionError([{'path': '/private/foreign.py', 'definition': 'x' * 500,
                                               'change': 'arbitrary raw exception content'}]).diagnostics
    assert detail['issues'] == [{'path': '<unavailable>', 'definition': '<unavailable>', 'change': 'unavailable'}]
