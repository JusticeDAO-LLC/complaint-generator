"""Real failed Native pytest/ownership; no provider or completion is fabricated."""
from dataclasses import asdict
from copy import deepcopy
import json

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate.startup_settled_validation import settled_validation_failure
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as impl
from tests.test_startup_retained_replay_rejection import _git

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture(scope='module')
def failed_world(tmp_path_factory):
    base = tmp_path_factory.mktemp('native-declared-failure')
    root, state, trees = (base / name for name in ('repo', 'state', 'worktrees'))
    for path in (root, state, trees):
        path.mkdir(mode=0o700)
    _git(root, 'init', '-q', '-b', 'main')
    _git(root, 'config', 'user.name', 'Synthetic Native failure fixture')
    _git(root, 'config', 'user.email', 'fixture@example.invalid')
    tasks = [{'id': f'CIMP-SYN-{n:02}', 'goal_id': 'goal.synthetic', 'subgoal_id': 'sub.synthetic',
        'title': 'Failed retained candidate' if n == 1 else 'Independent task', 'priority': 'P1' if n == 1 else 'P0',
        'targets': [f'out/task{n}.py', f'tests/test_task{n}.py'], 'depends_on': [],
        'acceptance': ['Synthetic local boundary only.'],
        'validation_commands': [f'python -m pytest -q tests/test_task{n}.py'],
        'implementation_prompt': 'Synthetic fixture; no model call.'} for n in (1, 2)]
    spec = {'schema_version': 'complaint-generator/improvement-spec@1', 'title': 'Synthetic startup boundary',
        'provider': {'router': 'ipfs_accelerate_py.llm_router', 'provider': 'grok_cli', 'model': 'grok-4.7', 'allow_fallback': False},
        'goals': [{'id': 'goal.synthetic', 'title': 'Synthetic', 'subgoals': [{'id': 'sub.synthetic', 'title': 'Synthetic'}]}],
        'tasks': tasks, 'execution_policy': {'synthetic_only': True}, 'findings': []}
    source = root / runner.SPEC_RELATIVE
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(spec))
    compiler.generate(source, root)
    _git(root, 'add', '.')
    _git(root, 'commit', '-qm', 'Synthetic task source')
    baseline = _git(root, 'rev-parse', 'HEAD')
    config = native.PortalSupervisorConfig(todo_path=root / compiler.BOARD_RELATIVE,
        state_path=state / 'state.json', strategy_path=state / 'strategy.json', events_path=state / 'supervisor.jsonl',
        state_dir=state, repo_root=root, state_prefix='synthetic', task_prefix='## CIMP-',
        worktree_root=trees, merge_target_branch='main', merge_queue_dir=state / 'merge-queue',
        implementation_protected_paths=(compiler.BOARD_RELATIVE,), worktree_scan_cache_enabled=False,
        worktree_reconciliation_max_merges=1, implementation_timeout=30, max_task_attempts=3, llm_merge_resolver_command='')
    supervisor = runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    daemon = native.PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
    impl.PortalTaskState().save(config.state_path)
    daemon._register_task_identities(daemon._load_tasks())
    branch, leaf = 'implementation/cimp-syn-01-declared-failure-attempt-1', trees / 'workspace_retained'
    _git(root, 'worktree', 'add', '-q', '-b', branch, str(leaf), baseline)
    (leaf / 'out').mkdir()
    (leaf / 'out/task1.py').write_text('VALUE = "synthetic failed candidate"\n')
    (leaf / 'tests').mkdir()
    (leaf / 'tests/test_task1.py').write_text('def test_retained_failure():\n    assert False\n')
    _git(leaf, 'add', '.')
    _git(leaf, 'commit', '-qm', 'Synthetic failed candidate')
    supervisor._complaint_startup_preflight_pending = True
    supervisor._complaint_startup_reconciliation_context = None
    # The actual Native maintenance pass produces the failed validator and
    # supervisor report before the wrapper observes their negative outcome.
    result = native.PortalImplementationSupervisor.run_once(supervisor, include_refill=False)
    item = result['worktree_reconciliation']['processed'][0]
    assert item['recovery_result']['validation_result']['reason'] == 'declared_validation_failed'
    assert item['recovery_result']['validation_result']['proposal_gate']['accepted'] is True
    return dict(root=root, state=state, trees=trees, leaf=leaf, branch=branch,
        supervisor=supervisor, daemon=daemon, result=result, item=item)


def test_genuine_failed_validator_is_nonblocking_without_writes_or_budget_changes(failed_world):
    w = failed_world
    s, d = w['supervisor'], w['daemon']
    before = asdict(impl.PortalTaskState.load(s.config.state_path))
    files = (d.events_path, s.config.events_path, s.config.todo_path)
    saved = {p: p.read_bytes() for p in files}
    refs = _git(w['root'], 'show-ref')
    assert settled_validation_failure(s, w['item'], maintenance_result=w['result'])
    assert saved == {p: p.read_bytes() for p in files}
    assert refs == _git(w['root'], 'show-ref') and w['leaf'].is_dir()
    assert asdict(impl.PortalTaskState.load(s.config.state_path)) == before


@pytest.mark.parametrize('damage', ['key', 'head', 'path', 'unknown_effect', 'hold', 'journal', 'dirty'])
def test_unknown_or_changed_evidence_remains_blocking(failed_world, damage):
    w = failed_world
    s, d = w['supervisor'], w['daemon']
    item, result = deepcopy(w['item']), deepcopy(w['result'])
    cleanup = []
    if damage in {'key', 'head'}:
        item['recovery_key' if damage == 'key' else 'head'] = 'f' * 40
    elif damage == 'path':
        item['path'] = str(w['trees'] / 'foreign')
    elif damage == 'unknown_effect':
        result['maintenance_blocked'] = True
    elif damage == 'hold':
        path = w['state'] / 'watchdog/HOLD'
        path.parent.mkdir(exist_ok=True)
        path.write_text('Synthetic manual hold')
        cleanup.append(lambda: path.unlink())
    elif damage == 'journal':
        raw = d.events_path.read_bytes()
        d.events_path.write_bytes(raw.replace(b'declared_validation_failed', b'changed_validation_failure', 1))
        cleanup.append(lambda: d.events_path.write_bytes(raw))
    else:
        path = w['leaf'] / 'out/task1.py'
        raw = path.read_bytes()
        path.write_bytes(raw + b'# dirty\n')
        cleanup.append(lambda: path.write_bytes(raw))
    try:
        assert not settled_validation_failure(s, item, maintenance_result=result)
    finally:
        for action in cleanup:
            action()


def test_cached_view_reproves_actual_failure_without_captured_context(failed_world):
    w = failed_world
    s, d = w['supervisor'], w['daemon']
    # The caller's cached view carries no execution receipt. Only the genuine
    # Native terminal and supervisor report can prove the failed validation.
    cached = {k: v for k, v in w['item'].items() if k not in {'recovery_result', 'validated_before_merge', 'cleanup_result'}}
    cached['merge_result'] = dict(attempted=False, merged=False, reason='reconciliation_candidate_validation_already_settled')
    context = s._complaint_startup_reconciliation_context
    before = asdict(impl.PortalTaskState.load(s.config.state_path))
    files = (d.events_path, s.config.events_path, s.config.todo_path)
    saved = {p: p.read_bytes() for p in files}
    try:
        s._complaint_startup_reconciliation_context = None
        assert settled_validation_failure(s, cached, maintenance_result=w['result'])
        assert saved == {p: p.read_bytes() for p in files}
        assert asdict(impl.PortalTaskState.load(s.config.state_path)) == before
    finally:
        s._complaint_startup_reconciliation_context = context


@pytest.fixture
def pending_world(tmp_path_factory):
    # Queue cancellation remains durable evidence in its own disposable world.
    return failed_world.__wrapped__(tmp_path_factory)


def test_pending_native_merge_remains_blocking(pending_world):
    w = pending_world
    d = w['daemon']
    task = d._load_tasks()[0]
    identity = d._identity_for_task(task)
    pending = d.merge_queue.enqueue(branch_name=w['branch'], task_id=task.task_id,
        canonical_task_id=identity.canonical_task_cid, canonical_task_key=identity.canonical_task_key,
        commit_sha=w['item']['head'], metadata={'synthetic_pending_effect': True},
        target_repository_id=d.merge_target_repository_id, target_branch='main')
    try:
        assert not settled_validation_failure(w['supervisor'], w['item'], maintenance_result=w['result'])
    finally:
        assert d.merge_queue.cancel(pending, reason='Synthetic refusal fixture cleanup') is not None


def test_public_startup_continues_and_native_selects_independent_task(failed_world):
    w = failed_world
    s, d = w['supervisor'], w['daemon']
    before = asdict(impl.PortalTaskState.load(s.config.state_path))
    s._complaint_startup_preflight_pending = True
    s._complaint_startup_reconciliation_context = None
    result = s.run_once(include_refill=False)
    assert result.get('maintenance_blocked') is not True
    assert s._complaint_startup_preflight_pending is False
    after = asdict(impl.PortalTaskState.load(s.config.state_path))
    assert all(after[k] == before[k] for k in before if k.startswith('completed') or k.startswith('implementation_attempts'))
    d.run_once()
    selected = impl.PortalTaskState.load(s.config.state_path)
    assert selected.active_task_id == 'CIMP-SYN-02' and selected.implementation_in_progress is False
