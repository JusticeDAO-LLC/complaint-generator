"""Bounded monitoring of one owned development-supervisor launch."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time


def _source_snapshot() -> dict[str, str]:
    from . import improvement_runner as runner, improvement_shutdown as shutdown
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), Path(runner.__file__), Path(shutdown.__file__))}


def _launch_scope(record: dict) -> dict:
    return {key: value for key, value in record.items() if key not in {'status', 'stopped_at'}}


def validate_monitor_duration(maximum_seconds: float) -> None:
    if (type(maximum_seconds) not in (int, float) or not math.isfinite(maximum_seconds)
            or not 0 < maximum_seconds <= 21600):
        raise ValueError('monitor duration must be positive and at most six hours')


def watch_owned_launch(repo_root: Path, spec_path: Path, state_dir: Path, *,
                      maximum_seconds: float = 21600) -> dict:
    """Watch one launch; explicit stop owns all fencing and closure checks.

    A launch gets one permanently recorded window of at most six hours. This
    monitor does not adopt replacement owners, start providers, reset attempts,
    reconcile task claims, or interpret application interview states.
    """
    validate_monitor_duration(maximum_seconds)
    from . import improvement_runner as runner, improvement_shutdown as shutdown
    from .improvement_recovery import _owned_bytes

    repo_root, spec_path, state_dir = map(lambda p: Path(p).resolve(strict=True),
                                        (repo_root, spec_path, state_dir))
    path = state_dir / 'launcher.json'
    def read():
        value = json.loads(_owned_bytes(path, 65536))
        if not isinstance(value, dict):
            raise ValueError('monitor launch object is unavailable')
        return value
    record = read()
    if (not runner._full_launch_record(record)
            or not runner._campaign_tuple_matches(record, repo_root, spec_path, state_dir)
            or shutdown._context(state_dir, record) is None):
        return {'status': 'monitor_refused', 'reason': 'launch_scope_unverified',
                'completion_authority': False, 'provider_dispatched': False}
    scope = _launch_scope(record)
    sources = _source_snapshot()
    key = hashlib.sha256(json.dumps({'state_dir': str(state_dir), 'identity': record['identity'],
                                    'started_at': record['started_at']},
                                   sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    folder = state_dir / 'monitor-owner-windows'
    folder.mkdir(mode=0o700, exist_ok=True)
    info = folder.lstat()
    if (folder.resolve(strict=True) != folder or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('monitor window directory custody is unavailable')
    lease = folder / (key + '.json')
    try:
        fd = os.open(lease, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return {'status': 'monitor_window_consumed', 'completion_authority': False,
                'provider_dispatched': False}
    with os.fdopen(fd, 'w') as stream:
        json.dump({'schema': 'complaint-owned-launch-monitor-window@1', 'owner_window': key,
                   'sources': sources, 'maximum_seconds': maximum_seconds,
                   'started_at': time.time(), 'completion_authority': False}, stream, sort_keys=True)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    lease_digest = hashlib.sha256(_owned_bytes(lease, 65536)).hexdigest()
    deadline = time.monotonic() + maximum_seconds
    while time.monotonic() < deadline:
        current = read()
        if _launch_scope(current) != scope:
            status = 'monitor_owner_changed'
            break
        if (_source_snapshot() != sources
                or hashlib.sha256(_owned_bytes(lease, 65536)).hexdigest() != lease_digest):
            status = 'monitor_source_changed'
            break
        if runner.owns_process(current):
            time.sleep(min(.5, max(0, deadline - time.monotonic())))
            continue
        if (Path('/proc') / str(current['identity']['pid'])).exists():
            status = 'monitor_owner_unknown'
            break
        # Source, owner and window are rechecked immediately before the public
        # stop call. Its own lock, birth checks and container custody remain the
        # authority for every effect; no outer lock is held here.
        if (_launch_scope(read()) != scope or _source_snapshot() != sources
                or hashlib.sha256(_owned_bytes(lease, 65536)).hexdigest() != lease_digest):
            status = 'monitor_source_changed'
            break
        stopped = runner.stop(state_dir)
        return {'status': 'stopped_after_launcher_exit' if stopped.get('status') == 'stopped'
                else 'monitor_stop_incomplete', 'stop_result': stopped,
                'owner_window': key, 'completion_authority': False,
                'provider_dispatched': False, 'attempt_refunded': False}
    else:
        status = 'monitor_expired'
    return {'status': status, 'owner_window': key, 'completion_authority': False,
            'provider_dispatched': False, 'attempt_refunded': False}
