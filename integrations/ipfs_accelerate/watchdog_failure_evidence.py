"""Bounded private first-failure metadata, never recovery authority.

Healthy ticks cannot replace an archived failure. No provider text, command,
path, token or private payload hash is accepted by this closed projection.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from .auto_rescue_activity import summary as rescue_summary

MAX_RECORDS = 16
MAX_BYTES = 16384
_SCHEMA = "complaint-watchdog-first-failure@1"
_CID = re.compile(r"(?:b[a-z2-7]{16,255}|sha256:[0-9a-f]{64})\Z")
_TASK = re.compile(r"[A-Z][A-Z0-9_-]{0,127}\Z")
_NAME = re.compile(r"[0-9a-f]{64}\.json\Z")
_FAILURES = frozenset({"stalled", "no_progress", "daemon_failed", "stop_incomplete",
    "identity_mismatch", "state_error", "board_error", "budget_exhausted", "unknown", "stopped", "blocked"})
_PHASES = frozenset({"implementing", "implementation", "provider", "validating",
    "validating_reconciled_candidate", "merging", "merge", "preparing_worktree", "worktree",
    "selected", "setup", "awaiting_user", "waiting_for_user", "manual_hold", "paused", "cancelled", "unknown"})
_LIVENESS = frozenset({"alive", "dead", "absent", "pid_reuse", "unknown", "missing"})
_PREFLIGHT_FLAGS = ("grok_binary_present", "auth_material_present", "private_runtime_ready",
    "worktree_capacity_sufficient", "resource_capacity_ready")
_FRAME_KINDS = ("usage", "tool_call", "tool_call_update", "thought", "text")
# Exact codes from the bounded metadata readers, never exception messages.
# State-only codes cannot be attributed to an unrelated file reader.
_FILE_READ_ERRORS = frozenset({"size_limit", "not_object", "JSONDecodeError", "UnicodeDecodeError",
    "OSError", "PermissionError", "IsADirectoryError", "NotADirectoryError", "BlockingIOError",
    "TimeoutError", "ValueError"})
_STATE_READ_ERRORS = _FILE_READ_ERRORS | frozenset({"native_state_read_timeout", "native_state_reader_failed",
    "PortalTaskStateControlPlaneError"})


def _encoded(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()


def _number(value):
    return type(value) in (int,float) and math.isfinite(value) and 0 <= value < 2**53


def _counts(value):
    value = value if type(value) is dict else {}
    return {key:value[key] for key in _FRAME_KINDS
        if type(value.get(key)) is int and 0 <= value[key] < 1_000_000_000}


def _read_errors(value):
    if type(value) is not dict:
        return {}
    result = {}
    # Iterate only this closed set, regardless of the supplied mapping size.
    for source in ("launcher", "state", "heartbeat", "strategy"):
        code = value.get(source)
        allowed = _STATE_READ_ERRORS if source == "state" else _FILE_READ_ERRORS
        if type(code) is str and len(code) <= 64 and code in allowed:
            result[source] = code
    return result


def _snapshot(scope, observation, status, preflight, observed_at):
    if not all(type(item) is dict for item in (scope,observation,status,preflight)):
        raise ValueError("capture_input_invalid")
    scope_keys = {"repository_root_cid","policy_root","run_cid"}
    if set(scope) != scope_keys or any(type(v) is not str or not _CID.fullmatch(v) for v in scope.values()):
        raise ValueError("capture_scope_invalid")
    scope = dict(scope)
    state = observation.get("status")
    hold = observation.get("hold_reason")
    dependency_hold = observation.get("manual_hold") is True and hold == "dependency_unavailable"
    if (observation.get("completion_verified") is True
            or observation.get("manual_hold") is True and not dependency_hold
            or not dependency_hold and (state not in _FAILURES or observation.get("healthy") is True)):
        return None
    native = status.get("native_state")
    native = native if type(native) is dict else {}
    task, cid, attempt = (observation.get(k) for k in ("active_task_id","active_task_cid","attempt"))
    if task in (None,"") and cid in (None,"") and attempt in (None,0):
        binding = {"task_id":None,"task_cid":None,"attempt":0}
    elif (type(task) is str and _TASK.fullmatch(task) and type(cid) is str and _CID.fullmatch(cid)
            and type(attempt) is int and 0 <= attempt <= 3
            and native.get("active_task_id") == task and native.get("active_task_cid") == cid
            and type(native.get("active_attempt")) is int and native["active_attempt"] == attempt):
        binding = {"task_id":task,"task_cid":cid,"attempt":attempt}
    else:
        raise ValueError("capture_task_binding_invalid")
    phase = native.get("active_phase")
    binding["phase"] = phase if type(phase) is str and phase in _PHASES else "unknown"
    rescue = rescue_summary(status.get("auto_rescue_activity_evidence"))
    reason = "dependency_unavailable" if dependency_hold else rescue["reason"]
    failure_class = "dependency_unavailable" if dependency_hold else state
    key_body = {"scope":scope,"binding":binding,"failure_class":failure_class,"reason":reason}
    read_errors = _read_errors(status.get("native_read_errors"))
    # Preserve old keys/records when no closed diagnosis exists. A newly
    # diagnosed cause can be retained without overwriting an earlier opaque
    # state_error with the same empty claim. The archive remains capped.
    key = hashlib.sha256(_encoded({**key_body, **({"native_read_errors":read_errors} if read_errors else {})})).hexdigest()
    provider = status.get("provider_execution_evidence")
    provider = provider if type(provider) is dict else {}
    validation = status.get("validation_activity_evidence")
    validation = validation if type(validation) is dict else {}
    evidence = {"auto_rescue":rescue,"provider_frame_counts":_counts(provider.get("frame_counts")),
        "provider_terminal_observed":provider.get("provider_terminal_observed") is True,
        **{k:status.get(k) is True for k in ("owned_process_alive","claim_progress_verified",
            "provider_progress_verified","validation_activity_verified","auto_rescue_activity_verified")}}
    if read_errors:
        evidence["native_read_errors"] = read_errors
    if _number(validation.get("deadline_at")):
        evidence["validation_deadline_at"] = validation["deadline_at"]
    if _number(status.get("native_heartbeat_age_seconds")):
        evidence["native_heartbeat_age_seconds"] = status["native_heartbeat_age_seconds"]
    worker = status.get("worker_liveness")
    evidence["worker_liveness"] = worker if type(worker) is str and worker in _LIVENESS else "unknown"
    native_status = status.get("status")
    evidence["native_status"] = native_status if type(native_status) is str and native_status in _FAILURES else "unknown"
    record = {"schema":_SCHEMA,"capture_stage":"initial_observation_before_recovery","key":key,**key_body,
        "observed_at":observed_at if _number(observed_at) else None,
        "observation":{k:observation.get(k) is True for k in
            ("healthy","manual_hold","progress_verified","owner_binding_verified","recovery_permitted")},
        "activity_evidence":evidence,"preflight":{k:preflight[k] for k in _PREFLIGHT_FLAGS
            if type(preflight.get(k)) is bool},"completion_authority":False}
    if len(_encoded(record)) > MAX_BYTES:
        raise ValueError("capture_size_limit")
    return record


def _close(descriptor):
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except OSError:
            pass  # Optional capture failure cannot replace the real verdict.


def _directory(path, *, parent_fd=None):
    if (not path.is_absolute() or path.parent==path or path.parent.resolve(strict=True)!=path.parent):
        raise ValueError("capture_parent_not_canonical")
    owned_parent = parent_fd is None
    parent = descriptor = -1
    fields = ('st_dev','st_ino','st_uid','st_mode')
    try:
        parent = (os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            if owned_parent else parent_fd)
        info = os.fstat(parent)
        named = path.parent.lstat()
        if (any(getattr(info,k)!=getattr(named,k) for k in fields)
                or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022):
            raise ValueError("capture_parent_custody_invalid")
        try:
            os.mkdir(path.name,mode=0o700,dir_fd=parent)
        except FileExistsError:
            pass
        descriptor = os.open(path.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        actual = os.fstat(descriptor)
        named = os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        if (path.resolve(strict=True)!=path or actual.st_uid!=os.getuid()
                or stat.S_IMODE(actual.st_mode)!=0o700
                or any(getattr(actual,k)!=getattr(named,k) for k in fields)
                or any(getattr(info,k)!=getattr(path.parent.lstat(),k) for k in fields)):
            raise ValueError("capture_directory_custody_invalid")
        result,descriptor = descriptor,-1
        return result
    finally:
        _close(descriptor)
        if owned_parent:
            _close(parent)


def _file_custody(info):
    return (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1)


def _identity(info):
    return tuple(getattr(info,k) for k in
        ('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))


def _closed_existing(value, expected):
    if type(value) is not dict or set(value)!=set(expected):
        return False
    if any(value.get(k)!=expected[k] for k in
            ('schema','capture_stage','key','scope','binding','failure_class','reason','completion_authority')):
        return False
    if value['observed_at'] is not None and not _number(value['observed_at']):
        return False
    flags = value['observation']
    if type(flags) is not dict or set(flags)!=set(expected['observation']) or any(type(v) is not bool for v in flags.values()):
        return False
    preflight = value['preflight']
    if (type(preflight) is not dict or set(preflight)-set(_PREFLIGHT_FLAGS)
            or any(type(v) is not bool for v in preflight.values())):
        return False
    evidence = value['activity_evidence']
    required = {'auto_rescue','provider_frame_counts','provider_terminal_observed','owned_process_alive',
        'claim_progress_verified','provider_progress_verified','validation_activity_verified',
        'auto_rescue_activity_verified','worker_liveness','native_status'}
    numeric_optional = {'validation_deadline_at','native_heartbeat_age_seconds'}
    optional = numeric_optional | {'native_read_errors'}
    if type(evidence) is not dict or set(evidence)-required-optional or required-set(evidence):
        return False
    if (evidence['auto_rescue']!=rescue_summary(evidence['auto_rescue'])
            or evidence['provider_frame_counts']!=_counts(evidence['provider_frame_counts'])
            or type(evidence['worker_liveness']) is not str or evidence['worker_liveness'] not in _LIVENESS
            or type(evidence['native_status']) is not str or evidence['native_status'] not in _FAILURES):
        return False
    if 'native_read_errors' in evidence:
        errors = evidence['native_read_errors']
        if (type(errors) is not dict or not errors or errors != _read_errors(errors)
                or errors != expected['activity_evidence'].get('native_read_errors')):
            return False
    elif 'native_read_errors' in expected['activity_evidence']:
        return False
    return (all(type(evidence[k]) is bool for k in required-{'auto_rescue','provider_frame_counts','worker_liveness','native_status'})
        and all(_number(evidence[k]) for k in numeric_optional&set(evidence)))


def capture(directory, *, scope, observation, status, preflight, observed_at):
    """Retain at most sixteen first observations; never change a verdict.

    A nonblocking independent lock bounds concurrent capture. Atomic link
    publication never overwrites an existing record. An interrupted staging
    file is retained as a finite capture_pending/custody diagnostic for operator
    review, rather than deleted or mistaken for new recovery/attempt authority.
    """
    parent = archive = lock = temporary = -1
    try:
        record = _snapshot(scope,observation,status,preflight,observed_at)
        if record is None:
            return {"status":"not_failure"}
        directory = Path(directory)
        parent = _directory(directory)
        archive_path = directory/'failure-evidence'
        archive = _directory(archive_path,parent_fd=parent)
        lock = os.open('capture.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,0o600,dir_fd=archive)
        lock_info = os.fstat(lock)
        named = os.stat('capture.lock',dir_fd=archive,follow_symlinks=False)
        if not _file_custody(lock_info) or (lock_info.st_dev,lock_info.st_ino) != (named.st_dev,named.st_ino):
            raise ValueError('capture_lock_custody_invalid')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status":"capture_busy"}
        if _identity(os.fstat(lock)) != _identity(os.stat('capture.lock',dir_fd=archive,follow_symlinks=False)):
            raise ValueError('capture_lock_changed')
        names = []
        with os.scandir(archive) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names)>MAX_RECORDS+2:
                    raise ValueError('capture_inventory_limit')
        if any(n not in {'capture.lock','.pending'} and not _NAME.fullmatch(n) for n in names):
            raise ValueError('capture_inventory_invalid')
        for name in names:
            if not _file_custody(os.stat(name,dir_fd=archive,follow_symlinks=False)):
                raise ValueError('capture_record_custody_invalid')
        name = record['key']+'.json'
        if name in names:
            descriptor = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=archive)
            try:
                info = os.fstat(descriptor)
                raw = os.read(descriptor,MAX_BYTES+1)
                existing = json.loads(raw)
                if (not _file_custody(info) or len(raw)>MAX_BYTES or len(raw)!=info.st_size
                        or _identity(info)!=_identity(os.fstat(descriptor))
                        or _identity(info)!=_identity(os.stat(name,dir_fd=archive,follow_symlinks=False))
                        or not _closed_existing(existing,record)):
                    raise ValueError('capture_existing_invalid')
            finally:
                _close(descriptor)
            return {"status":"already_captured","record":name}
        if '.pending' in names:
            return {"status":"capture_pending"}
        if sum(bool(_NAME.fullmatch(n)) for n in names) >= MAX_RECORDS:
            return {"status":"archive_full","capacity":MAX_RECORDS}
        temporary = os.open('.pending',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=archive)
        raw = _encoded(record)
        offset = 0
        while offset < len(raw):
            written = os.write(temporary,raw[offset:])
            if written <= 0:
                raise OSError('capture_write_incomplete')
            offset += written
        os.fsync(temporary)
        info = os.fstat(temporary)
        if (not _file_custody(info) or info.st_size != len(raw)
                or _identity(info)!=_identity(os.stat('.pending',dir_fd=archive,follow_symlinks=False))):
            raise ValueError('capture_staging_changed')
        os.link('.pending',name,src_dir_fd=archive,dst_dir_fd=archive,follow_symlinks=False)
        named = os.stat(name,dir_fd=archive,follow_symlinks=False)
        pending = os.stat('.pending',dir_fd=archive,follow_symlinks=False)
        if any((value.st_dev,value.st_ino)!=(info.st_dev,info.st_ino) for value in (named,pending)):
            raise ValueError('capture_publication_changed')
        os.unlink('.pending',dir_fd=archive)
        os.fsync(archive)
        fields = ('st_dev','st_ino','st_uid','st_mode')
        if (any(getattr(os.stat('failure-evidence',dir_fd=parent,follow_symlinks=False),k)!=getattr(os.fstat(archive),k)
                    or getattr(directory.lstat(),k)!=getattr(os.fstat(parent),k) for k in fields)
                or directory.resolve(strict=True)!=directory):
            raise ValueError('capture_directory_changed')
        return {"status":"captured","record":name}
    except Exception:
        # Capture is optional evidence, not authority to retry, suppress or
        # replace the SDK's real effect/result or its persistent budgets.
        return {"status":"capture_unavailable"}
    finally:
        _close(temporary)
        # Retain a failed staging record; never delete potential first-failure
        # evidence on a later healthy tick or unknown publication failure.
        for descriptor in (lock,archive,parent):
            _close(descriptor)
