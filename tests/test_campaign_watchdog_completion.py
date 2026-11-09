"""Synthetic boundaries with real Native callback/journal producers, never live state."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import campaign_completion as completion
from integrations.ipfs_accelerate import improvement_plan as compiler

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]


def _git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True,
                          text=True, timeout=20).stdout.strip()


@pytest.fixture
def produced_campaign(tmp_path, monkeypatch):
    """Native produces the real temporary CAS receipt, board commit and chain.

    State/queue/history readers are explicit isolated unit seams. They are not
    author JSON accepted by the public API and establish no live qualification.
    """
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths('ipfs_accelerate_py.agent_supervisor')
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.runtime import event_log
    root, state = tmp_path / 'source', tmp_path / 'campaign'
    root.mkdir(mode=0o700); state.mkdir(mode=0o700)
    _git(root, 'init', '-b', 'main')
    _git(root, 'config', 'user.email', 'fixture@example.invalid')
    _git(root, 'config', 'user.name', 'Synthetic Native Fixture')
    _git(root, 'config', 'commit.gpgsign', 'false')
    spec = compiler.load_spec(ROOT / compiler.SPEC_RELATIVE)
    goal = deepcopy(spec['goals'][0]); goal['subgoals'] = [goal['subgoals'][0]]
    task = deepcopy(spec['tasks'][0]); task['depends_on'] = []
    task['goal_id'] = goal['id']; task['subgoal_id'] = goal['subgoals'][0]['id']
    spec.update(goals=[goal], tasks=[task], campaign={
        'spec_relative': 'docs/task_boards/watchdog_fixture_spec.json',
        'plan_relative': 'docs/task_boards/watchdog_fixture_plan.json',
        'board_relative': 'docs/task_boards/watchdog_fixture_board.md',
        'board_namespace': 'watchdog-fixture'})
    spec_path = root / spec['campaign']['spec_relative']; spec_path.parent.mkdir(parents=True)
    spec_path.write_text(json.dumps(spec)); spec_path.chmod(0o600)
    generated = compiler.generate(spec_path, root)
    _git(root, 'add', '.'); _git(root, 'commit', '-m', 'Synthetic pending Native contract')
    baseline = _git(root, 'rev-parse', 'HEAD')
    board = Path(generated['board_path'])
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR', str(state / 'control-plane'))
    for key in ('IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT', 'IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB',
                'IPFS_ACCELERATE_AGENT_CONTROL_DUCKLAKE'):
        monkeypatch.delenv(key, raising=False)
    daemon = native.PortalImplementationDaemon(todo_path=board,
        state_path=state / 'complaint_intake_task_state.json', strategy_path=state / 'strategy.json',
        events_path=state / 'complaint_intake_events.jsonl', repo_root=root, implement=False,
        use_ephemeral_worktree=False, board_namespace='watchdog-fixture', task_header_prefix='## CIMP-',
        implementation_protected_paths=(spec['campaign']['board_relative'],),
        objective_path=root / 'OBJECTIVE.md', objective_bundle_dir=root / 'objectives',
        llm_merge_resolver_command='')
    task_object = native.parse_task_file(board, task_header_prefix='## CIMP-')[0]
    update = daemon._mark_task_completed_in_todo(task_object.task_id,
        expected_task_cids={task_object.task_id: task_object.canonical_task_cid})
    assert update['updated'] is True and update['durable'] is True
    assert update['completion_callback_evidence']['succeeded'] is True
    commit = _git(root, 'rev-parse', 'HEAD')
    journal = state / 'complaint_intake_events.jsonl'
    # The Native callback also records events; append the matching actual start
    # and a bounded real Python execution result as explicit fixture metadata.
    event_log.append_jsonl_event(journal, 'implementation_started', {
        'task_id': task_object.task_id, 'canonical_task_cid': task_object.canonical_task_cid,
        'canonical_task_key': task_object.canonical_task_key})
    executed = subprocess.run([sys.executable, '-I', '-B', '-c', 'assert True'], timeout=10)
    payload = {'task_id': task_object.task_id, 'canonical_task_cid': task_object.canonical_task_cid,
        'canonical_task_key': task_object.canonical_task_key, 'returncode': executed.returncode,
        'implementation_commit': baseline, 'validation_result': {
            'passed': executed.returncode == 0, 'behavioral_evidence': []},
        'merge_result': {'merged': True, 'merge_commit': commit, 'todo_update_result': update}}
    event_log.append_jsonl_event(journal, 'implementation_finished', payload)
    launcher = {'schema_version': 'complaint-improvement-launcher@1', 'repo_root': str(root),
        'state_dir': str(state), 'spec_path': str(spec_path), 'board_path': str(board),
        'plan_id': generated['receipt']['plan_id'], 'merge_target': 'main', 'provider': 'grok_cli',
        'model': 'grok-4.7', 'allow_fallback': False}
    (state / 'launcher.json').write_text(json.dumps(launcher)); (state / 'launcher.json').chmod(0o600)
    projection = {'completed_task_ids': [task_object.task_id], 'assumed_completed_task_ids': [],
        'task_identities': {task_object.task_id: {'canonical_task_cid': task_object.canonical_task_cid}},
        'task_statuses': {task_object.task_id: 'completed'}, 'blocked_task_ids': [],
        'ready_task_ids': [], 'waiting_task_ids': [], 'active_provider_runner': {},
        'implementation_in_progress': False, 'active_task_id': ''}
    queue = {'bindings': {task_object.task_id: [task_object.canonical_task_cid]},
        'open_request_ids': [], 'snapshot_digest': 'explicit-synthetic-unit-queue', 'completed_requests': 1}
    monkeypatch.setattr(completion.evidence, '_native', lambda: (native, event_log))
    monkeypatch.setattr(completion, '_state', lambda *_: deepcopy(projection))
    monkeypatch.setattr(completion, '_queue', lambda *_: deepcopy(queue))
    monkeypatch.setattr(completion.evidence, '_historical_execution', lambda *_: {
        'status': 'HISTORICAL', 'current_source_equivalence': False, 'explicit_synthetic_unit_seam': True})
    return SimpleNamespace(root=root, state=state, spec=spec_path, board=board, native=native,
        event_log=event_log, journal=journal, task=task_object, payload=payload,
        projection=projection, queue=queue)


def _verify(fixture):
    return completion.verify_campaign_completion(fixture.root, fixture.spec, fixture.state)


def test_native_produced_callback_chain_and_git_ancestry_verify_only_historical_scope(produced_campaign):
    result = _verify(produced_campaign)
    assert result['verified'] is True and result['completed'] == result['task_count'] == 1
    assert result['historical_execution_only'] is True
    assert result['current_source_qualification'] is False and result['completion_authority'] is False
    assert result['snapshot_digest'] and result['evidence_digests']['journal']


@pytest.mark.parametrize('damage', ['cid', 'active', 'provider', 'open_queue', 'missing_callback',
    'failed_finish', 'journal_tamper', 'callback_tamper', 'not_integrated', 'missing_idle_list', 'assumed_completion'])
def test_completion_refuses_incomplete_or_tampered_actual_boundaries(produced_campaign, damage):
    f = produced_campaign
    if damage == 'cid':
        f.projection['task_identities'][f.task.task_id]['canonical_task_cid'] = 'foreign'
    elif damage == 'active': f.projection['implementation_in_progress'] = True
    elif damage == 'provider': f.projection['active_provider_runner'] = {'pid': 12345}
    elif damage == 'missing_idle_list': f.projection['waiting_task_ids'] = None
    elif damage == 'assumed_completion': f.projection['assumed_completed_task_ids'] = [f.task.task_id]
    elif damage == 'open_queue': f.queue['open_request_ids'] = ['fixture-pending-request']
    elif damage == 'journal_tamper':
        raw = f.journal.read_bytes(); f.journal.write_bytes(raw.replace(b'implementation_finished', b'implementation_finisheX'))
    else:
        payload = deepcopy(f.payload)
        if damage == 'missing_callback': payload['merge_result']['todo_update_result'] = {}
        elif damage == 'failed_finish':
            payload['returncode'] = 1; payload['merge_result'] = {'merged': False}
        elif damage == 'callback_tamper':
            payload['merge_result']['todo_update_result']['completion_callback_evidence']['evidence_id'] = 'foreign'
        else: payload['merge_result']['merge_commit'] = 'f' * 40
        f.event_log.append_jsonl_event(f.journal, 'implementation_finished', payload)
    result = _verify(f)
    assert result['verified'] is False
    assert result['reason'] != 'native_campaign_completion_verified'


def test_completion_refuses_board_change_during_observation(produced_campaign, monkeypatch):
    f = produced_campaign
    def history(*_args):
        f.board.write_text(f.board.read_text() + '\nSynthetic concurrent board note\n')
        return {'status': 'HISTORICAL', 'current_source_equivalence': False}
    monkeypatch.setattr(completion.evidence, '_historical_execution', history)
    result = _verify(f)
    assert result['verified'] is False and result['reason'] == 'completion_snapshot_changed'


def test_completion_rejects_external_success_json_without_native_sources(tmp_path):
    root, state = tmp_path / 'source', tmp_path / 'state'
    root.mkdir(mode=0o700); state.mkdir(mode=0o700)
    path = root / 'claims.json'; path.write_text(json.dumps({'verified': True, 'completed': 44}))
    result = completion.verify_campaign_completion(root, path, state)
    assert result['verified'] is False and result['completion_authority'] is False


def test_completion_returns_safe_failure_for_unexpected_read_adapter_error(produced_campaign, monkeypatch):
    def unavailable(*_args):
        raise RuntimeError('private diagnostics must not enter public metadata')
    monkeypatch.setattr(completion, '_queue', unavailable)
    result = _verify(produced_campaign)
    assert result['verified'] is False and result['reason'] == 'completion_evidence_unavailable'
    assert result['error_type'] == 'RuntimeError'
    assert 'private diagnostics' not in json.dumps(result)
