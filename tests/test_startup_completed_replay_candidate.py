"""Synthetic tasks through actual Native admission, completion and startup.

These private Git/queue fixtures invoke no provider or production lifecycle API.
"""
from dataclasses import asdict, replace
import json

import pytest

from tests.test_startup_retained_replay_rejection import native_replay_world, _git
from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon_native

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture(scope='module')
def completed_replay_world(native_replay_world):
    w = native_replay_world
    d, root = w['daemon'], w['root']
    second = w['trees'] / 'workspace_second'
    branch = 'implementation/private-second-attempt-0'
    _git(root, 'worktree', 'add', '-q', '-b', branch, str(second), w['baseline'])
    (second / 'out').mkdir()
    (second / 'out/task1.py').write_text('VALUE = "second retained failure"\n')
    (second / 'tests').mkdir()
    (second / 'tests/test_retained.py').write_text('def test_retained_failure():\n assert False\n')
    _git(second, 'add', '.')
    accepted = d._validate_implementation_patch(second, w['task'], baseline_ref=w['baseline'], allow_scope_adjudication=False)
    assert accepted.accepted
    _git(second, 'commit', '-qm', 'Second retained failed candidate')
    head = _git(second, 'rev-parse', 'HEAD')
    key = w['supervisor']._worktree_reconciliation_recovery_key(task_cid=w['identity'].canonical_task_cid,
        baseline_ref=w['baseline'], candidate_commit=head, target_commit=w['baseline'], mode='pre_merge')
    failed = d.reconcile_validated_worktree_candidate(worktree_path=second, branch_name=branch,
        task=w['task'], baseline_ref=w['baseline'], candidate_commit=head, recovery_key=key)
    assert failed['validation_result']['proposal_gate']['reason_codes'] == ['stale_proposal_replay']
    # Persist an authentic supervisor report joining both exact closed Native
    # invocations before the different candidate wins. No startup exemption is
    # needed while this administrative fixture pass merely records failures.
    prior_config = replace(w['config'], worktree_reconciliation_max_merges=3)
    prior = runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(prior_config)
    prior_result = prior.run_once(include_refill=False)
    assert len(prior_result['worktree_reconciliation']['processed']) == 2
    # This winner is not pre-admitted: the genuine public Native path performs
    # scope admission, actual pytest, train integration and its completion callback.
    leaf = w['trees'] / 'workspace_winner'
    winner_branch = 'implementation/private-winning-attempt-0'
    _git(root, 'worktree', 'add', '-q', '-b', winner_branch, str(leaf), w['baseline'])
    (leaf / 'out').mkdir()
    (leaf / 'out/task1.py').write_text('VALUE = "genuine winning candidate"\n')
    (leaf / 'tests').mkdir()
    (leaf / 'tests/test_retained.py').write_text('def test_retained_failure():\n assert True\n')
    _git(leaf, 'add', '.')
    _git(leaf, 'commit', '-qm', 'Passing synthetic candidate')
    winner = _git(leaf, 'rev-parse', 'HEAD')
    winner_key = w['supervisor']._worktree_reconciliation_recovery_key(task_cid=w['identity'].canonical_task_cid,
        baseline_ref=w['baseline'], candidate_commit=winner, target_commit=w['baseline'], mode='pre_merge')
    result = d.reconcile_validated_worktree_candidate(worktree_path=leaf, branch_name=winner_branch,
        task=w['task'], baseline_ref=w['baseline'], candidate_commit=winner, recovery_key=winner_key)
    assert result['returncode'] == 0, result
    assert result['validation_result']['passed'] is True and result['merge_result']['merged'] is True
    assert next(t for t in d._load_tasks() if t.task_id == w['task'].task_id).status == 'completed'
    config = replace(w['config'], worktree_reconciliation_max_merges=3)
    s = runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    return {**w, 'supervisor': s, 'second': {'branch': branch, 'path': second, 'head': head, 'key': key},
        'winner': winner, 'winner_result': result}


def test_actual_completed_winner_leaves_both_failed_conflicting_candidates_nonblocking(completed_replay_world):
    w = completed_replay_world
    s, d = w['supervisor'], w['daemon']
    s._complaint_startup_preflight_pending = True
    s._complaint_startup_reconciliation_context = None
    before = asdict(daemon_native.PortalTaskState.load(s.config.state_path))
    # Preflight occurs before Native builds its captured task context. Exercise
    # that exact constructor-free caller state, including the helper's real
    # disabled Native constructor, and prove the observer itself writes nothing.
    items = s.reconcile_backlogged_worktrees()['processed']
    assert s._complaint_startup_reconciliation_context is None
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.portal_task_state_control_plane import read_task_state_payload
    # state_path is the Native control-plane address, not a JSON-file promise.
    state_before = read_task_state_payload(d.state_path)
    paths = (d.events_path, s.config.events_path, s.config.todo_path)
    observed = {p: p.read_bytes() for p in paths}
    refs = _git(w['root'], 'show-ref')
    assert all(runner._startup_candidate_is_completed(s, item) for item in items)
    assert observed == {p: p.read_bytes() for p in paths} and refs == _git(w['root'], 'show-ref')
    assert read_task_state_payload(d.state_path) == state_before
    heads = [(_git(p, 'rev-parse', 'HEAD'), (p / 'out/task1.py').read_bytes())
        for p in (w['leaf'], w['second']['path'])]
    result = s.run_once(include_refill=False)
    items = result['worktree_reconciliation']['processed']
    assert len(items) == 2 and all(item['merge_result']['reason'] == 'preflight_merge_conflict' for item in items)
    assert all(item['merged'] is False and item['merge_result']['attempted'] is False for item in items)
    assert s._complaint_startup_preflight_pending is False
    assert heads == [(_git(p, 'rev-parse', 'HEAD'), (p / 'out/task1.py').read_bytes())
        for p in (w['leaf'], w['second']['path'])]
    after = asdict(daemon_native.PortalTaskState.load(s.config.state_path))
    for name in ('implementation_attempts', 'implementation_attempts_by_cid') + tuple(k for k in before if k.startswith('completed')):
        assert after[name] == before[name]
    w['maintenance_result'] = result
    d.run_once()
    current = daemon_native.PortalTaskState.load(s.config.state_path)
    assert current.active_task_id == 'CIMP-SYN-02' and current.implementation_in_progress is False
    assert current.implementation_attempts.get('CIMP-SYN-02', 0) == 0


@pytest.mark.parametrize('damage', ['unfinished', 'changed_definition', 'missing_terminal', 'missing_admission',
    'missing_winner', 'wrong_scope', 'bad_winner_proof', 'unclosed_invocation', 'dirty', 'changed_head',
    'foreign_worktree', 'private_hold', 'live_claim', 'live_lease', 'pending_queue'])
def test_completed_observation_refuses_uncertain_provenance_and_live_effects(completed_replay_world, damage):
    from copy import deepcopy
    import shutil
    from integrations.ipfs_accelerate.startup_completed_replay_candidate import completed_replay_conflict
    w = completed_replay_world
    s, d = w['supervisor'], w['daemon']
    s._complaint_startup_preflight_pending = True
    s._complaint_startup_reconciliation_context = None
    item = deepcopy(w['maintenance_result']['worktree_reconciliation']['processed'][0])
    assert completed_replay_conflict(s, item) is True
    native_raw, board = d.events_path.read_bytes(), s.config.todo_path.read_bytes()
    rows = [json.loads(line) for line in native_raw.splitlines()]
    old = (w['leaf'] / 'out/task1.py').read_bytes()
    hold = w['state'] / 'watchdog/HOLD'
    claim = lease = pending = foreign = None
    try:
        if damage == 'unfinished':
            s.config.todo_path.write_bytes(board.replace(b'- Status: completed', b'- Status: ready', 1))
        elif damage == 'changed_definition':
            s.config.todo_path.write_bytes(board.replace(b'Synthetic local boundary only.', b'Changed private task definition.', 1))
        elif damage in {'missing_terminal', 'missing_admission', 'missing_winner', 'wrong_scope', 'bad_winner_proof'}:
            old_terminal = next(r for r in reversed(rows) if r.get('type') == 'worktree_reconciliation_validation_finished' and r.get('branch') == w['branch'])
            if damage == 'missing_terminal':
                rows = [r for r in rows if not (r.get('type') == 'worktree_reconciliation_validation_finished' and r.get('branch') == w['branch'])]
            elif damage == 'missing_admission':
                proposal = old_terminal['validation_result']['proposal_gate']['proposal_id']
                rows = [r for r in rows if not (r.get('type') == 'implementation_proposal_validated' and r.get('proposal_id') == proposal)]
            elif damage == 'missing_winner':
                rows = [r for r in rows if r.get('type') != 'implementation_finished']
            elif damage == 'wrong_scope':
                old_terminal['canonical_task_key'] = 'task/v1/' + 'e' * 64
            else:
                next(r for r in rows if r.get('type') == 'implementation_finished')['merge_result']['integration_commit_proof']['implementation_commit'] = 'e' * 40
            d.events_path.unlink()
            for row in rows:
                payload = {k: v for k, v in row.items() if k not in {'type', 'timestamp', 'event_id', 'previous_event_id', 'sequence', 'stream_id', 'snapshot_id'}}
                native.append_jsonl_event(d.events_path, row['type'], payload)
        elif damage == 'unclosed_invocation':
            d._record_event('worktree_reconciliation_validation_started', {'task_id': w['task'].task_id,
                'task_cid': w['identity'].canonical_task_cid, 'branch': w['branch'], 'worktree_path': str(w['leaf']),
                'implementation_commit': w['head'], 'baseline_ref': w['baseline'], 'recovery_key': w['key'],
                'attempt': 1, 'provider_dispatched': False, 'attempt_consumed': False})
        elif damage in {'dirty', 'changed_head'}:
            (w['leaf'] / 'out/task1.py').write_bytes(old + b'# changed retained source\n')
            if damage == 'changed_head':
                _git(w['leaf'], 'add', '.'); _git(w['leaf'], 'commit', '-qm', 'Changed immutable candidate')
        elif damage == 'foreign_worktree':
            foreign = w['leaf'].with_name('retained-original')
            w['leaf'].rename(foreign)
            import subprocess
            subprocess.run(['git', 'clone', '--quiet', '--shared', str(w['root']), str(w['leaf'])], check=True)
            _git(w['leaf'], 'checkout', '-q', '-b', w['branch'], w['head'])
        elif damage == 'private_hold':
            hold.parent.mkdir(exist_ok=True); hold.write_text('Synthetic retained operator hold\n')
        elif damage == 'live_claim':
            metadata = d._build_implementation_task_claim_metadata(w['task'], 1, daemon_native.utc_now())
            claim = d._implementation_task_claim_path(w['task'].task_id, canonical_task_cid=w['identity'].canonical_task_cid)
            acquired, reason, _ = d._try_acquire_implementation_task_claim(claim, metadata)
            assert acquired, reason
        elif damage == 'live_lease':
            lease = d._build_implementation_lock_metadata(w['task'], 1, daemon_native.utc_now())
            fd, reason, _ = d._try_acquire_lock(d._implementation_lock_path(), lock_kind='implementation', owner_active=d._implementation_lock_owner_is_active)
            assert fd is not None, reason
            d._write_lock_metadata(fd, lease)
        else:
            pending = d.merge_queue.enqueue(branch_name=w['branch'], task_id=w['task'].task_id,
                canonical_task_id=w['identity'].canonical_task_cid, canonical_task_key=w['identity'].canonical_task_key,
                commit_sha=w['head'], metadata={'synthetic_pending_effect': True},
                target_repository_id=d.merge_target_repository_id, target_branch='main')
        assert completed_replay_conflict(s, item) is False
    finally:
        if foreign is not None:
            shutil.rmtree(w['leaf']); foreign.rename(w['leaf'])
        if damage == 'changed_head':
            _git(w['leaf'], 'reset', '--hard', w['head'])
        (w['leaf'] / 'out/task1.py').write_bytes(old)
        d.events_path.write_bytes(native_raw); s.config.todo_path.write_bytes(board)
        hold.unlink(missing_ok=True)
        if claim is not None:
            d._release_implementation_task_claim(claim, metadata)
        if lease is not None:
            d._release_implementation_lock(d._implementation_lock_path(), lease)
        if pending is not None:
            assert d.merge_queue.cancel(pending, reason='Synthetic negative fixture cleanup') is not None
