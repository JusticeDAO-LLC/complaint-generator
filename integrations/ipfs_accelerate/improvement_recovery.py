"""Prepare a fresh epoch after a proven false capacity hold, without releasing it.

The old quarantine remains immutable. This helper transfers only consumed retry
accounting into a new native control plane; it grants no completion, callback,
cleanup, candidate-adoption or evidence-reuse authority.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping


SCHEMA = "complaint-improvement-recovery-epoch@1"
POINTER_SCHEMA = "complaint-improvement-active-epoch@1"
RECEIPT_NAME = "recovery_epoch.json"
_EPOCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _owned_bytes(path: Path, maximum: int = 2_000_000, *, legacy_group_write: bool = False) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or before.st_mode & (0o002 if legacy_group_write else 0o022)
                or not 0 < before.st_size <= maximum):
            raise ValueError("recovery evidence must be a bounded owned regular file")
        raw = os.read(fd, maximum + 1)
        after = os.fstat(fd)
        current = path.lstat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (len(raw) != before.st_size or any(getattr(before, k) != getattr(other, k)
                for other in (after, current) for k in fields)):
            raise ValueError("recovery evidence changed while being read")
        return raw
    finally:
        os.close(fd)


def _object(path: Path, *, legacy_group_write: bool = False) -> dict[str, Any]:
    value = json.loads(_owned_bytes(path, legacy_group_write=legacy_group_write))
    if not isinstance(value, dict):
        raise ValueError("recovery evidence is not an object")
    return value


def _plan_id(repo_root: Path, spec_path: Path) -> str:
    from .improvement_plan import build_improvement_work_plan, load_spec
    return build_improvement_work_plan(load_spec(spec_path)).plan_id


def _epoch_path(base: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.startswith("epochs/"):
        raise ValueError("active epoch must be a bounded epochs/name path")
    name = relative[len("epochs/"):]
    if _EPOCH.fullmatch(name) is None:
        raise ValueError("invalid recovery epoch name")
    result = base / "epochs" / name
    if result.resolve() != result or (base / "epochs").is_symlink():
        raise ValueError("recovery epoch cannot traverse symlinks")
    return result


def resolve_active_epoch(repo_root: Path, spec_path: Path, base_state_dir: Path) -> Path:
    """Resolve only a repo/plan/receipt-bound pointer; malformed pointers fail closed."""

    base = base_state_dir.resolve()
    pointer_path = base / "active_epoch.json"
    if not os.path.lexists(pointer_path):
        return base
    pointer = _object(pointer_path)
    plan_id = _plan_id(repo_root, spec_path)
    from . import improvement_amendment as amendment
    from . import improvement_release_amendment as release_amendment
    if (pointer.get("schema") not in {POINTER_SCHEMA, amendment.POINTER_SCHEMA, release_amendment.POINTER_SCHEMA}
            or pointer.get("repo_root") != str(repo_root.resolve())
            or pointer.get("plan_id") != plan_id):
        raise ValueError("active epoch repository or plan binding changed")
    if pointer["schema"] == amendment.POINTER_SCHEMA:
        return amendment.resolve_amended_epoch(repo_root, spec_path, base, pointer, plan_id)
    if pointer["schema"] == release_amendment.POINTER_SCHEMA:
        return release_amendment.resolve_release_amended_epoch(repo_root, spec_path, base, pointer, plan_id)
    target = _epoch_path(base, pointer.get("epoch"))
    raw = _owned_bytes(target / RECEIPT_NAME)
    receipt = json.loads(raw)
    if (not isinstance(receipt, dict)
            or pointer.get("recovery_receipt_sha256") != _digest(raw)
            or receipt.get("schema") != SCHEMA
            or receipt.get("repo_root") != str(repo_root.resolve())
            or receipt.get("plan_id") != plan_id
            or receipt.get("new_state_dir") != str(target)
            or any(receipt.get(k) is not False for k in (
                "old_quarantine_released", "completion_authority", "attempt_refunded",
                "candidate_adoption_authority", "evidence_reuse_authority"))):
        raise ValueError("active epoch recovery receipt binding changed")
    return target


def _validated_quarantine(repo_root: Path, path: Path) -> dict[str, Any]:
    from ipfs_accelerate_py.agent_supervisor.merge.worktree_lifecycle import WorktreeLifecycleStore
    value = _object(path)
    workspace = (value.get("lifecycle_record") or {}).get("workspace_path")
    if not isinstance(workspace, str):
        raise ValueError("quarantine workspace missing")
    store = WorktreeLifecycleStore(repo_root=repo_root)
    if store.quarantine_path_for(workspace).resolve() != path.resolve():
        raise ValueError("quarantine is outside the native repository lifecycle store")
    verified = store.load_quarantine(workspace)
    if verified != value:
        raise ValueError("native quarantine identity verification failed")
    return value


def _nonquota_terminal(native: Any, raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="strict")
    helper = getattr(native, "_grok_capacity_diagnostic_text", None)
    if not callable(helper):
        raise ValueError("fixed native capacity classifier is unavailable")
    diagnostics = helper(text)
    if native.classify_provider_capacity_failure(diagnostics, provider_labels=("grok",)).get("exhausted"):
        raise ValueError("actual provider capacity failure cannot open a recovery epoch")
    frames = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("type") in {"error", "max_turns_reached", "end"}:
            frames.append(value)
    errors = [v for v in frames if v.get("type") == "error"]
    endings = [v for v in frames if v.get("type") == "end"]
    if (errors or not any(v.get("type") == "max_turns_reached" for v in frames)
            or not endings or frames[-1].get("type") != "end"
            or endings[-1].get("stopReason") != "max_turn_requests"
            or type(endings[-1].get("num_turns")) is not int
            or endings[-1]["num_turns"] < 1):
        raise ValueError("complete nonquota max-turn terminal evidence is required")
    return {"reason": "max_turns_reached", "turns": endings[-1]["num_turns"],
            "returncode": 1, "capacity_exhausted": False}


def _assert_processes_absent(old_state: Path, workspace: Path, launcher: Mapping[str, Any],
                             lifecycle: Mapping[str, Any], heartbeat: Mapping[str, Any]) -> dict[str, Any]:
    from .improvement_runner import process_identity
    captured = [launcher.get("identity") or {}, lifecycle.get("owner") or {}]
    for identity in captured:
        current = process_identity(identity.get("pid"))
        ticks = identity.get("start_ticks", identity.get("start_time_ticks"))
        if current and current.get("boot_id") == identity.get("boot_id") and current.get("start_ticks") == ticks:
            raise ValueError("an old campaign owner is still alive")
    sealed_fallback = None
    if (launcher.get("status") != "stopped" or heartbeat.get("status") != "stopped"
            or (heartbeat.get("managed_daemon_cleanup") or {}).get("quiesced") is not True):
        if launcher.get("status") != "stopped" or heartbeat.get("status") not in {"termination_blocked", "running"}:
            raise ValueError("native owned shutdown evidence is required")
        from .improvement_shutdown import _context, _parent_closed
        paths = (old_state / "launcher.json", old_state / "complaint_intake_supervisor_status.json")
        before = {path: _owned_bytes(path, legacy_group_write=path == paths[1]) for path in paths}
        if json.loads(before[paths[0]]) != launcher or json.loads(before[paths[1]]) != heartbeat:
            raise ValueError("native shutdown files differ from supplied observations")
        context = _context(old_state, launcher)
        if context is None:
            raise ValueError("full owned native shutdown context is required")
        _parent_closed(old_state, launcher, context, False)
        sealed_fallback = (before, context)
    matches = []
    for directory in Path("/proc").iterdir():
        if not directory.name.isdecimal() or int(directory.name) == os.getpid():
            continue
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            raw = (directory / "cmdline").read_bytes()
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            raise ValueError("owned process inventory is unavailable") from exc
        if len(raw) > 131072:
            raise ValueError("owned process argv exceeds recovery inspection bound")
        argv = raw.decode(errors="replace").split("\0")
        joined = " ".join(argv)
        raw_repo = launcher.get('repo_root')
        repo_root = Path(raw_repo) if isinstance(raw_repo, str) and Path(raw_repo).is_absolute() else None
        relevant = _campaign_process_argv(argv, repo_root=repo_root, state_dir=old_state)
        if relevant and (str(old_state) in joined or str(workspace) in joined):
            matches.append(int(directory.name))
    if matches:
        raise ValueError("old campaign daemon/provider processes remain")
    if sealed_fallback is not None:
        before, context = sealed_fallback
        if any(_owned_bytes(path, legacy_group_write=path == paths[1]) != raw for path, raw in before.items()):
            raise ValueError("native shutdown files changed during process inventory")
        _parent_closed(old_state, launcher, context, False)
    return {"old_births_alive": False, "matching_processes": 0, "native_shutdown_quiesced": True}


def _campaign_process_argv(argv: list[str], *, repo_root: Path | None = None,
                           state_dir: Path | None = None) -> bool:
    """Match executable/module tokens, never Python text inside a parent shell."""
    modules = {
        "ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon",
        "ipfs_accelerate_py.agent_supervisor.runtime.grok_cli_runner",
        "ipfs_accelerate_py.agent_supervisor.grok_cli_runner",
    }
    if repo_root is not None and state_dir is not None and len(argv) > 2:
        from .improvement_plan import BOARD_RELATIVE
        if (re.fullmatch(r'python(?:\d+(?:\.\d+)*)?', Path(argv[0]).name)
                and argv[1] == str(repo_root / 'integrations/ipfs_accelerate/improvement_runner.py')):
            board = str(repo_root / BOARD_RELATIVE)
            launcher = state_dir / 'launcher.json'
            if os.path.lexists(launcher):
                # This only detects a potentially related process for the
                # negative quiescence census; it grants no signal authority.
                # Unknown full-launch custody must refuse, never hide a child.
                from .improvement_shutdown import _context
                record = json.loads(_owned_bytes(launcher))
                context = _context(state_dir, record)
                if context is not None:
                    if context['repo_root'] != str(repo_root):
                        raise ValueError('campaign process launcher repository differs')
                    board = record['board_path']
            expected = {'--todo-path': board, '--state-dir': str(state_dir)}
            if all(argv.count(flag) == 1 and argv.index(flag) + 1 < len(argv)
                    and argv[argv.index(flag) + 1] == value
                    and not any(item.startswith(flag + '=') for item in argv)
                    for flag, value in expected.items()):
                return True
    return bool(argv and (Path(argv[0]).name in {"grok", "grok-build"}
        or any(item in modules for item in argv)
        or ("_run" in argv and "--owner-token" in argv)))


def _assert_containers_absent(workspace: Path) -> dict[str, Any]:
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    docker = grok_cli_runner._docker_isolation_binary()
    if not docker:
        raise ValueError("trusted local Docker inspection is unavailable")
    command = [docker, "--host=unix:///var/run/docker.sock"]
    ids = subprocess.run(command + ["ps", "-a", "--no-trunc", "--filter",
        "label=ipfs_accelerate.grok_isolation=true", "--format", "{{.ID}}"],
        text=True, capture_output=True, timeout=10, check=True).stdout.splitlines()
    if len(ids) > 256 or any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in ids):
        raise ValueError("Docker recovery inventory is invalid or exceeds bound")
    for identifier in ids:
        result = subprocess.run(command + ["inspect", "--format", "{{json .Mounts}}", identifier],
                                text=True, capture_output=True, timeout=10, check=True)
        if len(result.stdout) > 262144:
            raise ValueError("Docker mount inventory exceeds bound")
        mounts = json.loads(result.stdout)
        if not isinstance(mounts, list) or len(mounts) > 256:
            raise ValueError("Docker mount inventory is invalid")
        for mount in mounts:
            if not isinstance(mount, dict):
                raise ValueError("Docker mount record is invalid")
            if mount.get("Type") != "bind":
                continue
            raw_source = mount.get("Source")
            if not isinstance(raw_source, str) or not Path(raw_source).is_absolute():
                raise ValueError("Docker bind source is invalid")
            source = Path(raw_source)
            if source == workspace or source.is_relative_to(workspace) or workspace.is_relative_to(source):
                raise ValueError("an old workspace container still exists")
    return {"matching_workspace_containers": 0, "native_containers_inspected": len(ids)}


@contextmanager
def _native_environment(state_dir: Path):
    keys = ("IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR", "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB",
            "IPFS_ACCELERATE_AGENT_CONTROL_DUCKLAKE", "IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ.pop(key, None)
        os.environ[keys[0]] = str(state_dir / "control-plane")
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def prepare_false_capacity_epoch(repo_root: Path, spec_path: Path, quarantine_path: Path,
                                 epoch_name: str, *, base_state_dir: Path | None = None) -> dict[str, Any]:
    """Publish a reviewed fresh epoch only after all old execution is absent."""
    from . import improvement_runner as runner
    from .improvement_plan import BOARD_RELATIVE
    repo_root = repo_root.resolve()
    base = (base_state_dir or runner.default_state_dir(repo_root)).resolve()
    target = _epoch_path(base, "epochs/" + epoch_name)
    _supervisor, native = runner._native_modules(repo_root)
    from ipfs_accelerate_py.agent_supervisor.runtime import provider_capacity_custody
    plan_id = _plan_id(repo_root, spec_path)
    with runner._lock(base):
        if target.exists() or os.path.lexists(base / "active_epoch.json"):
            raise ValueError("recovery epoch or active pointer already exists")
        quarantine_raw = _owned_bytes(quarantine_path)
        quarantine = _validated_quarantine(repo_root, quarantine_path)
        hold = quarantine["fence_authority"]
        lifecycle = quarantine["lifecycle_record"]
        old_state = Path(hold["state_path"]).parent.resolve()
        workspace = Path(hold["worktree_path"]).resolve(strict=True)
        launcher = _object(old_state / "launcher.json")
        # The native supervisor historically writes this diagnostic projection
        # with the caller's 0664 umask. It grants no recovery authority by itself;
        # owned births and live process/container inventory are checked below.
        heartbeat = _object(old_state / f"{runner.STATE_PREFIX}_supervisor_status.json", legacy_group_write=True)
        if (launcher.get("repo_root") != str(repo_root) or launcher.get("plan_id") != plan_id
                or lifecycle.get("repo_root") != str(repo_root)
                or lifecycle.get("workspace_path") != str(workspace)
                or quarantine.get("reason") != provider_capacity_custody.REASON
                or hold.get("schema") != provider_capacity_custody.SCHEMA
                or hold.get("returncode") != 1 or hold.get("attempt_consumed") is not True
                or any(quarantine.get(key) is not False for key in
                       ("cleanup_allowed", "reuse_allowed", "evidence_reuse_allowed", "terminalized"))):
            raise ValueError("recovery requires the exact consumed false-capacity quarantine")
        task_id, cid, spent = hold["task_id"], hold["canonical_task_cid"], hold["attempt"]
        if type(spent) is not int or not 1 <= spent < 3:
            raise ValueError("recovery cannot refund or extend the native three-attempt budget")
        tasks = native.parse_task_file(repo_root / BOARD_RELATIVE, runner.TASK_PREFIX)
        matches = [task for task in tasks if task.task_id == task_id and task.canonical_task_cid == cid]
        if len(matches) != 1 or matches[0].status != "todo":
            raise ValueError("recovery task revision or pending status changed")
        log_path = Path(hold["log_path"])
        log_identity = provider_capacity_custody.log_identity(log_path)
        if log_identity != hold.get("log_identity") or log_identity.get("complete_digest") is not True:
            raise ValueError("retained log identity/hash/size changed")
        terminal = _nonquota_terminal(native, _owned_bytes(log_path, 16_000_000))
        absence = _assert_processes_absent(old_state, workspace, launcher, lifecycle, heartbeat)
        containers = _assert_containers_absent(workspace)
        old_payload, authority = runner._read_native_state(repo_root, Path(hold["state_path"]), timeout_seconds=10)
        if old_payload.get("read_error"):
            raise ValueError("old native retry accounting is unavailable")
        old_spent = max(old_payload.get("implementation_attempts", {}).get(task_id, 0),
                        old_payload.get("implementation_attempts_by_cid", {}).get(cid, 0))
        if (old_spent != spent or any(count for key, count in old_payload.get("implementation_attempts", {}).items() if key != task_id)
                or any(count for key, count in old_payload.get("implementation_attempts_by_cid", {}).items() if key != cid)):
            raise ValueError("old native consumed-attempt accounting differs")
        # Recheck immutable evidence after all potentially slow observations.
        if (_owned_bytes(quarantine_path) != quarantine_raw
                or provider_capacity_custody.log_identity(log_path) != log_identity):
            raise ValueError("old evidence changed before epoch publication")
        (base / "epochs").mkdir(mode=0o700, exist_ok=True)
        target.mkdir(mode=0o700)
        state_path = target / f"{runner.STATE_PREFIX}_task_state.json"
        with _native_environment(target):
            seeded = native.PortalTaskState(
                implementation_attempts={task_id: spent},
                implementation_attempts_by_cid={cid: spent},
                task_identities={task_id: {"canonical_task_cid": cid}},
            )
            seeded.save(state_path)
            observed = native.PortalTaskState.load(state_path)
            if (observed.implementation_attempts != {task_id: spent}
                    or observed.implementation_attempts_by_cid != {cid: spent}
                    or observed.completed_task_ids or observed.active_task_id):
                raise ValueError("new native accounting seed did not persist exactly")
        receipt = {
            "schema": SCHEMA, "repo_root": str(repo_root), "plan_id": plan_id,
            "old_state_dir": str(old_state), "new_state_dir": str(target),
            "quarantine_path": str(quarantine_path), "quarantine_id": quarantine["quarantine_id"],
            "quarantine_sha256": _digest(quarantine_raw), "task_id": task_id, "canonical_task_cid": cid,
            "spent_attempts": spent, "next_attempt": spent + 1,
            "old_log_identity": log_identity, "old_native_authority": authority,
            "terminal_diagnostic": terminal, "process_absence": absence, "container_absence": containers,
            "old_quarantine_released": False, "attempt_refunded": False, "completion_authority": False,
            "candidate_adoption_authority": False, "evidence_reuse_authority": False,
            "old_callback_outcome": "unknown", "old_workspace_preserved": str(workspace),
            "new_native_state_path": str(state_path), "provider_started": False,
        }
        runner._atomic_json(target / RECEIPT_NAME, receipt)
        receipt_raw = _owned_bytes(target / RECEIPT_NAME)
        runner._atomic_json(base / "active_epoch.json", {
            "schema": POINTER_SCHEMA, "repo_root": str(repo_root), "plan_id": plan_id,
            "epoch": "epochs/" + epoch_name, "recovery_receipt_sha256": _digest(receipt_raw),
        })
        for directory in (target, base):
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return receipt
