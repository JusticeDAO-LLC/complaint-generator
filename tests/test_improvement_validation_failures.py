"""Failed executor outcomes stay failed, measured and precisely classified.

These portable fault cases exercise trusted Host callback handling, not success
authority. The real published SDK timeout is also reproduced in the external
acceptance record; no positive measurement or cleanup receipt is fabricated.
"""
from pathlib import Path
import json
import subprocess

import pytest

from integrations.ipfs_accelerate import improvement_runner as host
from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _world(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    test = root / 'tests/test_synthetic.py'; test.parent.mkdir()
    test.write_text('def test_synthetic():\n assert True\n')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    command = 'python -m pytest -q tests/test_synthetic.py'
    task = {'id': 'CIMP-SYNTHETIC-FAILURE', 'targets': ['tests/test_synthetic.py'], 'validation_commands': [command]}
    return root, task, command


def _fault(kind):
    def execute(**call):
        if kind in {'timeout_verified', 'timeout_unknown', 'timeout_false', 'timeout_truthy'}:
            error = subprocess.TimeoutExpired('do-not-publish-private-argv', 1, output='do-not-publish-private-output')
            if kind == 'timeout_verified': error.process_tree_quiesced = True
            elif kind == 'timeout_false': error.process_tree_quiesced = False
            elif kind == 'timeout_truthy': error.process_tree_quiesced = 1
            raise error
        return {'command': call['spec'].command, 'raw_command': call['spec'].raw_command,
                'returncode': 75, 'error': kind, 'infrastructure_failure': True,
                'validation_python_launcher': {'sealed': True}}
    return execute


@pytest.mark.parametrize('kind', ['timeout_verified', 'timeout_unknown', 'timeout_false', 'timeout_truthy',
    'validation_process_cleanup_unverified', 'validation_output_limit_exceeded'])
def test_executor_failure_produces_failed_measured_receipt_without_invented_cleanup(tmp_path, kind):
    root, task, command = _world(tmp_path)
    observed = host.measure_behavioral_command(root, tmp_path / 'runs', task, command,
        runner=_fault(kind), environment={'PATH': '/usr/bin:/bin'}, timeout_seconds=30)
    measurement = observed['host_measurement']
    timeout = kind == 'timeout_verified'
    expected = 'subprocess_timeout' if timeout else ('validation_process_cleanup_unverified' if kind.startswith('timeout') else kind)
    assert measurement['reason'] == expected
    assert observed['timed_out'] is timeout and observed['exit_status'] != 0
    assert observed.native_result['returncode'] == (124 if timeout else 75)
    assert measurement['completion_authority'] is measurement['live_node_verified'] is False
    assert measurement['cases'] == [] and measurement['required_nodeids'] == []
    persisted = Path(measurement['run_path']) / 'measurement.json'
    assert json.loads(persisted.read_text())['reason'] == measurement['reason']
    if kind == 'timeout_verified':
        assert observed.native_result['process_tree_quiesced'] is True
    else:
        assert 'process_tree_quiesced' not in observed.native_result
    assert 'do-not-publish-private-' not in json.dumps(observed.native_result)
    if not timeout:
        assert measurement['infrastructure_failure'] is True
        assert observed.native_result['infrastructure_failure'] is True
        if kind.startswith('timeout'):
            assert observed.native_result['execution_deadline_exceeded'] is True
            assert observed.native_result.get('timed_out') is not True


@pytest.mark.parametrize('kind,status', [('timeout_verified',124),
    ('timeout_unknown',75), ('timeout_false',75),
    ('validation_process_cleanup_unverified',75), ('validation_output_limit_exceeded',75)])
def test_real_native_scheduler_retains_timeout_or_infrastructure_status_through_evidence_gate(tmp_path, kind, status):
    root, task, command = _world(tmp_path)
    native = ValidationScheduler(max_workers=1, resource_budget=1,
        default_timeout_seconds=30, cache_dir=tmp_path / 'native-cache')
    wrapped = host.EvidenceValidationScheduler(native, state_dir=tmp_path / 'state',
        spec={'tasks':[task]}, defer_readiness=True)
    from types import SimpleNamespace
    wrapped.bind_task(SimpleNamespace(task_id=task['id'],canonical_task_cid='synthetic-cid',
        canonical_task_key='synthetic-key'), root)
    result = wrapped.run([command], workspace_path=root, environment={'PATH':'/usr/bin:/bin'},
        runner=_fault(kind), require_full_validation=True, changed_files=['tests/test_synthetic.py'])
    assert result['passed'] is False and result['returncode'] == status
    assert result['firstparty_completion_authority'] is False
    assert len(result['behavioral_evidence']) == 1
    assert result['behavioral_evidence'][0]['admitted'] is False
    expected = 'subprocess_timeout' if status == 124 else ('validation_process_cleanup_unverified' if kind.startswith('timeout') else kind)
    assert result['behavioral_evidence'][0]['reason'] == expected
    row = result['results'][0]
    assert row['returncode'] == status
    if status == 124: assert row['timed_out'] is True
    else: assert row['infrastructure_failure'] is True


@pytest.mark.parametrize('kind', ['timeout_verified', 'validation_process_cleanup_unverified'])
def test_source_denial_dominates_raw_executor_timeout_or_infrastructure_failure(tmp_path, kind):
    root, task, command = _world(tmp_path)
    native = ValidationScheduler(max_workers=1, resource_budget=1,
        default_timeout_seconds=30, cache_dir=tmp_path / 'native-cache')
    wrapped = host.EvidenceValidationScheduler(native, state_dir=tmp_path / 'state',
        spec={'tasks':[task]}, defer_readiness=True)
    from types import SimpleNamespace
    wrapped.bind_task(SimpleNamespace(task_id=task['id'],canonical_task_cid='synthetic-cid',
        canonical_task_key='synthetic-key'), root)
    fault = _fault(kind)
    def mutate_source_then_fail(**call):
        (root / task['targets'][0]).write_text('def test_synthetic():\n assert False\n')
        return fault(**call)
    result = wrapped.run([command], workspace_path=root, environment={'PATH':'/usr/bin:/bin'},
        runner=mutate_source_then_fail, require_full_validation=True, changed_files=task['targets'])
    assert result['passed'] is False and result['returncode'] == 78
    assert result['behavioral_evidence'][0]['reason'] == 'stale_source_hash'
    row = result['results'][0]
    assert row['error'] == 'stale_source_hash'
    assert row['timed_out'] is row['infrastructure_failure'] is False
    assert row['native_executor_failure']['returncode'] == (124 if kind == 'timeout_verified' else 75)
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import classify_validation_attempts, ValidationOutcome
    assert classify_validation_attempts([row]) is ValidationOutcome.DETERMINISTIC_FAILURE
