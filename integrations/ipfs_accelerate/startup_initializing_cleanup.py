"""Discard only proven interrupted Native pool preparation before restart.

This observes the real old dispatch claim, selection and initializing writer.
It never reconstructs an index, rescues synthetic deletions, completes a task,
or removes a dispatch claim. Native owns the checkout lease, lifecycle gates,
pool-sidecar claim and failed-initialization discard operation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import uuid

from . import release_evidence as evidence
from .startup_rejected_candidate import _journal
from .startup_terminal_candidate import _worktree_custody


def _need(value):
    if not value:
        raise ValueError('initializing_checkout_unverified')


def _file(path, *, empty=False, source=False):
    path = Path(path)
    _need(path.is_absolute() and path.resolve(strict=True) == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        _need(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid() and first.st_nlink == 1
            and not first.st_mode & (0o002 if source else 0o022)
            and (first.st_size == 0 if empty else 0 < first.st_size <= 65536))
        raw = os.read(fd, first.st_size + 1)
        fields = ('st_dev', 'st_ino', 'st_uid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        identity = tuple(getattr(first, k) for k in fields)
        _need(len(raw) == first.st_size and all(tuple(getattr(v, k) for k in fields) == identity
            for v in (os.fstat(fd), path.lstat())))
        return raw, identity
    finally:
        os.close(fd)


def _operation(path, value):
    """Publish the private unlock intent durably through held directory FDs."""
    campaign = evidence._directory(path.parent.parent, private=True)
    parent = os.open(campaign, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    directory = -1
    temporary = '.operation-' + uuid.uuid4().hex
    try:
        try:
            os.mkdir(path.parent.name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
        directory = os.open(path.parent.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        held = os.fstat(directory)
        _need(stat.S_ISDIR(held.st_mode) and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'
        _need(len(raw) <= 65536)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                _need(written > 0)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        evidence._directory(path.parent, private=True)
        current = path.parent.lstat()
        _need((current.st_dev, current.st_ino) == (held.st_dev, held.st_ino))
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        if directory >= 0:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)
        os.close(parent)


def _inventory(daemon, root, path, base):
    """Hash existing checkout bytes against Git identities without exposing them.

    Missing baseline files are normal during initial checkout. Existing new or
    changed payloads are not discarded, even when no provider event exists.
    Git filters, extdiff and the real worktree index are never used here.
    """
    result = daemon._run_git(['--no-replace-objects', '--no-optional-locks',
        'ls-tree', '-r', '-l', '-z', '--full-tree', base], cwd=root)
    _need(result.returncode == 0 and len(result.stdout.encode()) <= 8 * 1024 * 1024)
    expected, directories = {}, set()
    for entry in result.stdout.split('\0'):
        if not entry:
            continue
        header, name = entry.split('\t', 1)
        fields = header.split()
        relative = PurePosixPath(name)
        _need(len(fields) == 4 and not relative.is_absolute() and name == relative.as_posix()
            and all(part not in ('.', '..', '.git') for part in relative.parts)
            and len(name.encode()) <= 4096 and re.fullmatch(r'[0-9a-f]{40}', fields[2]) is not None)
        mode, kind, oid, size = fields
        _need((kind == 'blob' and mode in ('100644', '100755', '120000') and size.isdecimal())
            or (kind == 'commit' and mode == '160000' and size == '-'))
        expected[name] = (mode, oid, int(size) if size != '-' else None)
        directories.update(parent.as_posix() for parent in relative.parents if parent.as_posix() != '.')
    _need(0 < len(expected) <= 20000)
    observed, total = [], 0
    fields = ('st_dev', 'st_ino', 'st_uid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')

    def visit(fd, prefix):
        nonlocal total
        names = os.listdir(fd)
        _need(len(observed) + len(names) <= 40000)
        for name in sorted(names):
            relative = prefix + name
            if relative == '.git':
                observed.append((relative, hashlib.sha256(_file(path / '.git', source=True)[0]).hexdigest()))
                continue
            first = os.stat(name, dir_fd=fd, follow_symlinks=False)
            # Unix symlink permission bits are conventionally 0777; their
            # exact target bytes, owner and Git type are checked without follow.
            _need(first.st_uid == os.getuid() and (stat.S_ISLNK(first.st_mode) or not first.st_mode & 0o002))
            identity = tuple(getattr(first, k) for k in fields)
            definition = expected.get(relative)
            if stat.S_ISDIR(first.st_mode):
                _need(relative in directories or (definition is not None and definition[0] == '160000'))
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
                try:
                    _need(tuple(getattr(os.fstat(child), k) for k in fields) == identity)
                    if definition is not None:
                        _need(definition[0] == '160000' and not os.listdir(child))
                    else:
                        visit(child, relative + '/')
                finally:
                    os.close(child)
                observed.append((relative, identity))
            else:
                _need(definition is not None and definition[0] != '160000' and first.st_nlink == 1)
                mode, oid, size = definition
                # Git may create/truncate an output before its first write.
                # Such an empty regular placeholder contains no new bytes to
                # lose; its baseline identity remains explicit, not hash-equal.
                empty_placeholder = stat.S_ISREG(first.st_mode) and mode in ('100644', '100755') and first.st_size == 0 and size > 0
                _need((first.st_size == size or empty_placeholder) and total + first.st_size <= 256 * 1024 * 1024)
                total += first.st_size
                actual_size = first.st_size
                digest = hashlib.sha1(('blob ' + str(actual_size) + '\0').encode())
                if stat.S_ISLNK(first.st_mode):
                    _need(mode == '120000')
                    raw = os.fsencode(os.readlink(name, dir_fd=fd))
                    _need(len(raw) == size)
                    digest.update(raw)
                else:
                    _need(stat.S_ISREG(first.st_mode) and mode in ('100644', '100755')
                        and bool(first.st_mode & 0o111) == (mode == '100755'))
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
                    try:
                        _need(tuple(getattr(os.fstat(child), k) for k in fields) == identity)
                        count = 0
                        while count < actual_size:
                            raw = os.read(child, min(1024 * 1024, actual_size - count))
                            _need(bool(raw))
                            count += len(raw)
                            digest.update(raw)
                        _need(not os.read(child, 1) and tuple(getattr(os.fstat(child), k) for k in fields) == identity)
                    finally:
                        os.close(child)
                _need(empty_placeholder or digest.hexdigest() == oid)
                observed.append((relative, identity, 'empty_placeholder' if empty_placeholder else 'baseline_blob', oid, size))
            _need(tuple(getattr(os.stat(name, dir_fd=fd, follow_symlinks=False), k) for k in fields) == identity)

    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        visit(fd, '')
        after, current = os.fstat(fd), path.lstat()
        _need(all((v.st_dev, v.st_ino, v.st_uid, v.st_mode, v.st_mtime_ns, v.st_ctime_ns)
            == (before.st_dev, before.st_ino, before.st_uid, before.st_mode, before.st_mtime_ns, before.st_ctime_ns)
            for v in (after, current)))
    finally:
        os.close(fd)
    return hashlib.sha256(json.dumps(observed, separators=(',', ':')).encode()).hexdigest()


def _closed(runner, root, campaign, record):
    from .improvement_shutdown import _context, _parent_closed
    _need(runner._full_launch_record(record) and not runner.owns_process(record)
        and runner._campaign_tuple_matches(record, root, Path(record['spec_path']), campaign)
        and runner._read_validation_watchdog_authority(campaign / 'launcher.json') == record
        and not any(os.path.lexists(campaign / 'watchdog' / name) for name in ('HOLD', 'OPERATOR_STOP')))
    context = _context(campaign, record)
    _need(context is not None)
    closure = _parent_closed(campaign, record, context, False)
    # The stopped-heartbeat route may return None; its genuine full shutdown
    # receipt remains mandatory in that case. Never invent a census result.
    if closure is None:
        receipt = runner._read_validation_watchdog_authority(campaign / 'container_shutdown.json')
        _need(isinstance(receipt, dict) and runner._shutdown_verified(record, receipt, root, campaign))
        closure = receipt.get('process_closure')
    _need(isinstance(closure, dict) and closure.get('proc_census_complete') is True
        and type(closure.get('observations')) is int and closure['observations'] >= 2
        and closure.get('recorded_pids_absent') is True and closure.get('matching_processes') == 0
        and closure.get('all_births_group_and_session_checked') is True
        and closure.get('completion_authority') is False and closure.get('attempt_refunded') is False)
    return context


def _proof(runner, supervisor, daemon, pool, record, metadata_path):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as dn
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as sn
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import git_lock_inode_is_open
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.worktrees import WORKTREE_POOL_SCHEMA
    config = supervisor.config
    root, campaign = Path(config.repo_root), Path(config.state_dir)
    _closed(runner, root, campaign, record)
    raw, meta_pin = _file(metadata_path, source=True)
    state = evidence._object(raw)
    path = Path(str(state.get('path', '')))
    token = state.get('lease_token')
    base, cache = state.get('base_commit'), state.get('cache_key')
    _need(state.get('schema') == WORKTREE_POOL_SCHEMA and state.get('state') == 'initializing'
        and isinstance(token, str) and re.fullmatch(r'[0-9a-f]{12}-[0-9a-f]{12}', token) is not None
        and metadata_path == pool.state_root / (token + '.json')
        and path == pool.worktree_root / ('workspace_' + token.replace('-', '_'))
        and path.resolve(strict=True) == path and pool.worktree_root == config.worktree_root
        and state.get('repo_root') == str(root) and state.get('repo_common_dir') == str(pool.repo_common_dir)
        and re.fullmatch(r'[0-9a-f]{40}', str(base or '')) is not None
        and type(cache) is str and token.split('-')[0] == hashlib.sha256((cache + '\0' + base).encode()).hexdigest()[:12]
        and cache == daemon._implementation_worktree_cache_key()
        and state.get('dependency_paths') == list(daemon._effective_worktree_submodule_paths(None)))
    records = supervisor._git_worktree_records(root)
    _need(len(records) <= 256)
    matches = [r for r in records if r.get('worktree') == str(path)]
    _need(len(matches) == 1 and matches[0].get('HEAD') == base)
    branch = str(matches[0].get('branch', '')).removeprefix('refs/heads/')
    _need(_worktree_custody(supervisor, daemon, path, branch, base))
    admin = Path(evidence._git(path, 'rev-parse', '--absolute-git-dir'))
    _need(not os.path.lexists(admin / 'index'))
    _, git_lock_pin = _file(admin / 'index.lock', empty=True, source=True)
    _need(git_lock_inode_is_open(admin / 'index.lock') is False)
    inventory = _inventory(daemon, root, path, base)
    initializing = None
    if os.path.lexists(admin / 'locked'):
        initializing, initializing_pin = _file(admin / 'locked', source=True)
        _need(initializing == b'initializing\n')
    else:
        initializing_pin = None
    evidence._git(root, 'merge-base', '--is-ancestor', base, 'HEAD')
    rows, journal_pin = _journal(daemon.events_path)
    selected = [r for r in rows if r.get('type') == 'task_selected']
    _need(bool(selected))
    selected = selected[-1]
    task_id = selected.get('task_id')
    tasks = [task for task in daemon._load_tasks() if task.task_id == task_id]
    _need(len(tasks) == 1 and dn.normalize_status(tasks[0].status) == 'todo')
    task = tasks[0]
    identity = daemon._identity_for_task(task)
    binding = {'task_id': task_id, 'canonical_task_cid': identity.canonical_task_cid,
        'canonical_task_key': identity.canonical_task_key, 'board_namespace': identity.board_namespace}
    _need(all(binding.values()) and all(selected.get(k) == v for k, v in binding.items()))
    claim_path = daemon._implementation_task_claim_path(task_id, canonical_task_cid=identity.canonical_task_cid)
    # Native's existing lock publisher uses legacy group-writable modes. The
    # canonical private workroot/campaign and owned Git ancestry still apply;
    # world-write, aliases, wrong owners and hard links remain refusals.
    claim_raw, claim_pin = _file(claim_path, source=True)
    claim = evidence._object(claim_raw)
    owner = sn.ProcessBirthIdentity.from_dict(claim.get('owner_process_birth'))
    _need(owner is not None and owner.pid > 1 and owner.start_time_ticks > 0 and owner.parent_pid > 1
        and owner.pid == state.get('lease_pid') == claim.get('pid')
        and owner.boot_id == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        and sn.owner_liveness(owner) is sn.OwnerLiveness.DEAD and not os.path.lexists(Path('/proc') / str(owner.pid))
        and claim.get('kind') == dn.IMPLEMENTATION_TASK_CLAIM_LOCK_KIND
        and claim.get('lease_role') == dn.IMPLEMENTATION_DISPATCH_INTENT_LEASE_ROLE
        and claim.get('state_dir') == str(campaign) and claim.get('state_path') == str(config.state_path)
        # Native intentionally leaves legacy repo_root blank while migrating
        # cross-worktree leases. Its verified physical repository identity and
        # canonical worktree_root are the publisher's actual binding.
        and claim.get('repo_root', '') in ('', str(root)) and claim.get('worktree_root') == str(root)
        and sn.checkout_lock_repository_matches(claim, root) is True
        and all(claim.get(k) == v for k, v in binding.items())
        and type(claim.get('attempt')) is int and claim['attempt'] == 1
        and claim.get('dispatch_authority_cid') == dn.PortalImplementationDaemon._implementation_dispatch_authority_cid(claim))
    pattern = re.escape(f'implementation/{task_id.lower().replace("/", "-")}-{identity.short_id}-attempt-1-') + r'([0-9]+)'
    branch_match = re.fullmatch(pattern, branch)
    created = state.get('created_at_epoch')
    _need(branch_match is not None and type(created) in (int, float) and math.isfinite(created)
        and int(branch_match[1]) <= created < int(branch_match[1]) + runner.TIMEOUT_SECONDS)
    selection_time = runner._event_timestamp(selected)
    claim_time = runner._event_timestamp({'timestamp': claim.get('started_at')})
    _need(selection_time is not None and claim_time is not None and selection_time <= claim_time <= created)
    forbidden = {'implementation_started', 'implementation_finished', 'implementation_proposal_validated',
        'worktree_reconciliation_validation_started', 'worktree_reconciliation_validation_finished',
        'worktree_reconciliation_candidate_queued', 'merge_candidate_enqueued', 'merge_finished'}
    _need(not any(r['sequence'] > selected['sequence'] and (r.get('task_id') == task_id
        or r.get('branch') == branch or r.get('worktree_path') == str(path))
        and (r.get('type') in forbidden or 'provider' in str(r.get('type', ''))) for r in rows))
    snapshot = runner._validation_activity_snapshot(campaign)
    _need(isinstance(snapshot, dict) and isinstance(snapshot.get('body'), dict))
    cp = snapshot['body']
    _need(cp.get('implementation_in_progress') is False
        and not any(cp.get(k) for k in ('active_attempt', 'active_phase', 'active_provider_runner', 'active_worktree_path',
            'active_log_path', 'active_branch', 'manual_hold', 'manual_cancellation', 'capacity_quarantine',
            'protected_incident', 'protected_implementation_attempts'))
        and not cp.get('implementation_attempts', {}).get(task_id, 0)
        and not cp.get('implementation_attempts_by_cid', {}).get(identity.canonical_task_cid, 0))
    _need(daemon.worktree_lifecycle.load_quarantine(path) is None)
    directory = campaign / 'initializing-checkout-cleanup'
    op_id = hashlib.sha256((token + '\0' + claim['lease_id']).encode()).hexdigest()
    op_path = directory / (op_id + '.json')
    authority = {'schema': 'interrupted-native-pool-cleanup@1', 'repository_root': str(root),
        'state_dir': str(campaign), 'plan_id': record['plan_id'], 'entry_path': str(metadata_path),
        'entry_sha256': hashlib.sha256(raw).hexdigest(), 'entry_identity': list(meta_pin),
        'path': str(path), 'branch': branch, 'base': base, 'claim_sha256': hashlib.sha256(claim_raw).hexdigest(),
        'claim_identity': list(claim_pin), 'git_index_lock_identity': list(git_lock_pin),
        'existing_checkout_sha256': inventory,
        'native_journal_sha256': journal_pin, 'source_head': evidence._git(root, 'rev-parse', 'HEAD')}
    if initializing is None:
        saved = evidence._object(_file(op_path)[0])
        original_marker = saved.get('git_initializing_identity')
        _need(type(original_marker) is list and len(original_marker) == 8
            and original_marker[2] == os.getuid() and original_marker[4] == 1 and original_marker[5] == 13
            and stat.S_ISREG(original_marker[3]) and not original_marker[3] & 0o002)
        authority['git_initializing_identity'] = original_marker
        _need(saved == {**authority, 'phase': 'prepared'})
    else:
        authority['git_initializing_identity'] = list(initializing_pin)
    return {'state': state, 'path': path, 'branch': branch, 'base': base, 'claim_path': claim_path,
        'claim_raw': claim_raw, 'cp': cp, 'source': runner._read_validation_watchdog_authority(campaign / 'launcher.json'),
        'admin': admin, 'initializing_identity': initializing_pin, 'operation_path': op_path, 'authority': authority,
        'pins': (meta_pin, claim_pin, git_lock_pin, journal_pin, evidence._git(root, 'rev-parse', 'HEAD'),
            hashlib.sha256(evidence._read(config.todo_path, source=True)).hexdigest())}


def cleanup_stopped_initializing_checkouts(runner, repo_root, state_dir, record):
    """Run only after start's ordinary stopped-campaign admission checks."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    root, campaign = Path(repo_root), Path(state_dir)
    workroot, binding = runner.recorded_worktree_root(record, campaign)
    directory = workroot / '.pool-state'
    if not directory.exists():
        return []
    metadata = sorted(directory.glob('*.json'))
    _need(len(metadata) <= 256)
    candidates = []
    for path in metadata:
        raw, _ = _file(path, source=True)
        if evidence._object(raw).get('state') == 'initializing':
            candidates.append(path)
    if not candidates:
        return []
    _closed(runner, root, campaign, record)
    _need(binding is not None)
    config = runner._recovery_config(root, campaign, record)
    supervisor = native.PortalImplementationSupervisor(config)
    daemon = native.PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
    pool = daemon.worktree_pool
    _need(daemon.implement is False and pool is not None and pool.worktree_root == workroot)
    lease, reason, _ = supervisor._acquire_supervisor_checkout_lease(supervisor._repo_merge_lock_path(),
        supervisor._supervisor_checkout_lock_metadata(operation='discard_interrupted_pool_initialization'))
    _need(lease is not None)
    removed = []
    try:
        for metadata_path in candidates:
            first = _proof(runner, supervisor, daemon, pool, record, metadata_path)
            def authorize(path, branch, phase):
                # INITIALIZING metadata is published before Native adds its
                # branch field. Supply the actual independently proved Git
                # branch, so Native can find its provisional PREPARING record.
                _need(path == first['path'] and branch in ('', first['branch']) and phase in ('preflight', 'claimed'))
                return daemon._authorize_pooled_worktree_reuse(path, first['branch'], phase)
            lock, reason = pool._try_claim_authorized(first['state'], authorize_reuse=authorize)
            _need(lock is not None)
            lock_raw, lock_pin = _file(lock, source=True)
            discarded = False
            try:
                second = _proof(runner, supervisor, daemon, pool, record, metadata_path)
                _need(first == second)
                op = second['operation_path']
                prepared = {**second['authority'], 'phase': 'prepared'}
                if op.exists():
                    _need(evidence._object(_file(op)[0]) == prepared)
                else:
                    _operation(op, prepared)
                if second['initializing_identity'] is not None:
                    # The sole nonempty control marker accepted here is Git's
                    # exact captured "initializing\n", never a manual lock.
                    _need(_file(second['admin'] / 'locked', source=True)
                        == (b'initializing\n', second['initializing_identity']))
                    daemon._run_git(['worktree', 'unlock', str(second['path'])], cwd=root)
                    unmarked = _proof(runner, supervisor, daemon, pool, record, metadata_path)
                    expected = {**second, 'initializing_identity': None}
                    _need(unmarked == expected)
                pool._reject_and_discard(second['state'], reason='stale_initializing_entry', lock_path=lock)
                discarded = True
                _need(not os.path.lexists(second['path']) and not os.path.lexists(metadata_path)
                    and not os.path.lexists(second['admin'])
                    and not any(row.get('worktree') == str(second['path'])
                        for row in supervisor._git_worktree_records(root))
                    and evidence._git(root, 'rev-parse', second['branch']) == second['base']
                    and _file(second['claim_path'], source=True)[0] == second['claim_raw']
                    and runner._validation_activity_snapshot(campaign)['body'] == second['cp']
                    and evidence._git(root, 'rev-parse', 'HEAD') == second['pins'][4])
                _operation(op, {**prepared, 'phase': 'released'})
                removed.append({'path': str(second['path']), 'branch': second['branch'],
                    'base': second['base'], 'reason': 'stale_initializing_entry',
                    'attempt_consumed': False, 'provider_dispatched': False, 'completion_authority': False})
            finally:
                if not discarded:
                    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import serialized_lock_update
                    with serialized_lock_update(lock):
                        if os.path.lexists(lock):
                            _need(_file(lock, source=True) == (lock_raw, lock_pin))
                            pool._remove_lock(lock)
    finally:
        _need(supervisor._release_supervisor_checkout_lease(lease, operation='discard_interrupted_pool_initialization'))
    return removed
