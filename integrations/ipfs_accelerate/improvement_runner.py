"""Own and observe one Grok-only native implementation supervisor campaign.

This wrapper does not implement a second task scheduler. The native supervisor
owns its daemon, implementation deadlines, retries and task completion evidence.
Launcher records only establish process ownership; a PID is not progress proof.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import math
import multiprocessing
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "integrations.ipfs_accelerate"

from .campaign import DEFAULT_ARTIFACTS, campaign_artifacts


SPEC_RELATIVE = "docs/task_boards/complaint_intake_improvement_spec.json"
STATE_PREFIX = "complaint_intake"
TASK_PREFIX = "## CIMP-"
MODEL = "grok-4.7"
STARTUP_SECONDS = 90
STALL_SECONDS = 180
TIMEOUT_SECONDS = 900
MAX_EVENT_HISTORY_BYTES = 128 * 1024 * 1024
_LOGGER = logging.getLogger(__name__)
PRIVATE_PATHS_ENV = "IPFS_ACCELERATE_AGENT_GROK_PRIVATE_PATHS_JSON"
REASONING_EFFORT_ENV = "IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"
ORCHESTRATION_DIR_ENV = "IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR"
AUTOMATIC_RETRY_REARM_ENV = "IPFS_ACCELERATE_AGENT_AUTOMATIC_RETRY_REARM"
WORKTREE_MARKER = ".complaint-worktree-root.json"
_PRIVATE_ROOT_PATHS = (".complaint_workspace", "data", "output", "statefiles", "exports", "secrets",
                       "evidence", "uploads", "attachments", ".env*", "*.key", "*.pem")
# Native basename globs apply only at their explicit parent. Keep dependency
# source available while denying its private data and Git reconstruction path.
_PRIVATE_DEPENDENCY_ROOTS = ("external/ipfs_accelerate_py", "external/ipfs_datasets_py",
                             "external/ipfs_kit_py")
_PRIVATE_PATHS = (*_PRIVATE_ROOT_PATHS, *(f"{root}/{path}"
                  for root in _PRIVATE_DEPENDENCY_ROOTS for path in (*_PRIVATE_ROOT_PATHS, ".git")))


def default_state_dir(repo_root: Path) -> Path:
    identity = hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:16]
    return Path.home() / ".cache/complaint-generator/campaigns" / identity / "intake-improvement"


def _read_json(path: Path, *, limit: int = 2_000_000) -> dict[str, Any]:
    try:
        if path.stat().st_size > limit:
            return {"read_error": "size_limit", "path": str(path)}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"read_error": "not_object"}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        return {"read_error": type(exc).__name__}


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _lock(state_dir: Path, name: str = "launcher.lock", *, blocking: bool = True):
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / name).open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)



def _worktree_directory(path: Path, repo_root: Path, state_dir: Path) -> dict[str, Any]:
    """Validate a dedicated external root without creating it or following aliases."""
    if (not path.is_absolute() or path.resolve(strict=True) != path
            or path == repo_root or path.is_relative_to(repo_root) or repo_root.is_relative_to(path)
            or path == state_dir or path.is_relative_to(state_dir) or state_dir.is_relative_to(path)):
        raise ValueError("configured worktree root must be canonical and outside repository/state")
    metadata = path.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise ValueError("configured worktree root must be an existing UID-owned0700 directory")
    return {"schema_version": "complaint-worktree-root@1", "path": str(path),
            "device": metadata.st_dev, "inode": metadata.st_ino, "uid": metadata.st_uid, "mode": 0o700,
            "repo_root": str(repo_root), "state_dir": str(state_dir)}


def _worktree_marker(path: Path) -> tuple[dict[str, Any], str] | None:
    marker = path / WORKTREE_MARKER
    try:
        descriptor = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size > 16384):
            raise ValueError("worktree root marker ownership differs")
        raw = os.read(descriptor, 16385)
        after = marker.lstat()
        if (len(raw) != before.st_size or any(getattr(before, field) != getattr(after, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))):
            raise ValueError("worktree root marker changed")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("worktree root marker must be an object")
        return value, hashlib.sha256(raw).hexdigest()
    finally:
        os.close(descriptor)


def _validate_worktree_root(repo_root: Path, state_dir: Path, path: Path, *,
                            expected: Mapping[str, Any] | None = None, claim: bool = False) -> dict[str, Any]:
    directory = _worktree_directory(path, repo_root, state_dir)
    marker = _worktree_marker(path)
    if marker is None:
        if expected is not None or any(path.iterdir()):
            raise ValueError("worktree root has no bound marker or is not a fresh dedicated directory")
        if not claim:
            return directory
        raw = (json.dumps(directory, sort_keys=True) + "\n").encode()
        try:
            descriptor = os.open(path / WORKTREE_MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            return _validate_worktree_root(repo_root, state_dir, path, expected=expected)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        marker = _worktree_marker(path)
    if marker is None or marker[0] != directory:
        raise ValueError("worktree root marker belongs to a different repository/epoch/directory")
    binding = {**directory, "marker_sha256": marker[1]}
    if expected is not None and dict(expected) != binding:
        raise ValueError("recorded worktree root identity differs")
    if _worktree_directory(path, repo_root, state_dir) != directory:
        raise ValueError("worktree root directory changed")
    return binding


def recorded_worktree_root(record: Mapping[str, Any], state_dir: Path) -> tuple[Path, dict[str, Any] | None]:
    """Legacy records keep their original root; configured records require exact custody."""
    has_root = "worktree_root" in record or "worktree_root_binding" in record
    if not has_root:
        if "--worktree-root" in (record.get("argv") or []):
            raise ValueError("launcher worktree flag has no recorded binding")
        return state_dir / "worktrees", None
    value, binding = record.get("worktree_root"), record.get("worktree_root_binding")
    argv = record.get("argv")
    if (not isinstance(value, str) or not isinstance(binding, dict) or not isinstance(argv, list)
            or argv.count("--worktree-root") != 1
            or argv[argv.index("--worktree-root") + 1:][:1] != [value]):
        raise ValueError("launcher worktree flag/binding differs")
    repo = Path(str(record.get("repo_root") or ""))
    if not repo.is_absolute() or repo.resolve() != repo or record.get("state_dir") != str(state_dir):
        raise ValueError("launcher worktree repository/epoch differs")
    return Path(value), _validate_worktree_root(repo, state_dir, Path(value), expected=binding)


def _full_launch_record(record: Mapping[str, Any]) -> bool:
    """Process-only fixtures stay process-only; any campaign binding requires closure proof."""
    if not record or record.get("read_error"):
        return False
    return record.get("schema_version") == "complaint-improvement-launcher@1" or any(
        key in record for key in ("repo_root", "spec_path", "plan_id", "state_dir")
    )


def _requested_plan_id(spec_path: Path) -> str | None:
    from .improvement_plan import build_improvement_work_plan, load_spec
    try:
        return build_improvement_work_plan(load_spec(spec_path)).plan_id
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _campaign_spec(repo_root: Path, spec_path: Path):
    from .improvement_plan import load_spec
    spec = load_spec(spec_path)
    artifacts = campaign_artifacts(spec)
    artifacts.validate_source(repo_root, spec_path)
    return spec, artifacts


def _native_campaign_spec(repo_root: Path, state_dir: Path, *, todo_path=None, board_namespace=None):
    """Resolve the specification bound to this Native launch, never a global override."""
    root = Path(repo_root).resolve()
    record = _read_json(Path(state_dir) / "launcher.json")
    bound = _full_launch_record(record)
    if bound:
        path = Path(str(record.get("spec_path") or ""))
        if not _campaign_tuple_matches(record, root, path, Path(state_dir)):
            raise ValueError("Native campaign specification is not bound to its launcher")
        spec, artifacts = _campaign_spec(root, path)
    else:
        spec, artifacts = _campaign_spec(root, root / SPEC_RELATIVE)
    expected = root / artifacts.board_relative
    if bound and todo_path is not None and Path(todo_path).resolve() != expected:
        raise ValueError("Native task board differs from its campaign specification")
    if ((board_namespace or artifacts != DEFAULT_ARTIFACTS)
            and board_namespace is not None and board_namespace != artifacts.board_namespace):
        raise ValueError("Native board namespace differs from its campaign specification")
    return spec


def _campaign_tuple_matches(record: Mapping[str, Any], repo_root: Path, spec_path: Path, state_dir: Path) -> bool:
    try:
        _, artifacts = _campaign_spec(repo_root, spec_path)
    except (OSError, ValueError, TypeError, KeyError):
        return False
    plan_id = _requested_plan_id(spec_path)
    return bool(
        plan_id and record.get("schema_version") == "complaint-improvement-launcher@1"
        and record.get("repo_root") == str(repo_root)
        and record.get("spec_path") == str(spec_path)
        and record.get("state_dir") == str(state_dir)
        and record.get("plan_id") == plan_id
        and record.get("provider") == "grok_cli"
        and record.get("model") == MODEL
        and record.get("allow_fallback") is False
        and (artifacts == DEFAULT_ARTIFACTS or record.get("board_path") == str(repo_root / artifacts.board_relative))
    )


def _stop_incomplete(state_dir: Path, reason: str) -> dict[str, Any]:
    return {"status": "stop_incomplete", "signalled": False, "reason": reason,
            "state_dir": str(state_dir), "manual_holds_preserved": True}


def _shutdown_verified(record: Mapping[str, Any], shutdown: Mapping[str, Any], repo_root: Path, state_dir: Path) -> bool:
    return bool(
        record.get("schema_version") == "complaint-improvement-launcher@1"
        and shutdown.get("schema") == "complaint-improvement-container-shutdown@1"
        and shutdown.get("repo_root") == record.get("repo_root") == str(repo_root)
        and shutdown.get("state_dir") == record.get("state_dir") == str(state_dir)
        and shutdown.get("plan_id") == record.get("plan_id")
        and shutdown.get("started_at") == record.get("started_at")
        and isinstance(record.get("owner_token"), str)
        and shutdown.get("owner_token_sha256") == hashlib.sha256(record["owner_token"].encode()).hexdigest()
        and shutdown.get("quiesced") is True and shutdown.get("status") == "stopped"
        and shutdown.get("completion_authority") is False
        and shutdown.get("provider_callback_settled") is False
        and shutdown.get("attempt_refunded") is False
        and ("worktree_root" not in record or (shutdown.get("worktree_root") == record["worktree_root"]
             and shutdown.get("worktree_root_binding") == record.get("worktree_root_binding")))
    )


def _admission_docker_runtime():
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths("ipfs_accelerate_py.agent_supervisor.runtime.grok_cli_runner")
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    return grok_cli_runner


def _observe_campaign_containers(repo_root: Path, state_dir: Path, worktree_root: Path,
                                 record: Mapping[str, Any], shutdown: Mapping[str, Any]) -> bool:
    """Observe complete Docker inventory without acquiring shutdown authority.

    A known stopped worker may remain after an explicit non-removing stop. All
    other containers touching this campaign require operator reconciliation.
    Admission never stops, removes, signals, or updates historical evidence.
    """
    from .improvement_shutdown import _CID, _INSPECT, _timestamp, MAX_INSPECT_BYTES
    deadline = time.monotonic() + 25.0
    scopes = {repo_root, state_dir, worktree_root}
    if _full_launch_record(record):
        scopes.add(recorded_worktree_root(record, state_dir)[0])
    retained = shutdown.get("containers", [])
    if not isinstance(retained, list):
        return False
    try:
        native = _admission_docker_runtime()
        docker = native._docker_isolation_binary()
        if not docker:
            return False
        with tempfile.TemporaryDirectory(prefix="complaint-docker-admission-config-") as temporary:
            command = [docker, "--host=unix:///var/run/docker.sock", "--config", temporary]

            def run(arguments):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("Docker admission deadline exceeded")
                result = subprocess.run(command + arguments, stdin=subprocess.DEVNULL, text=True,
                    capture_output=True, timeout=min(5.0, remaining), check=False, env=native._docker_control_env())
                if (len(result.stdout or "") > MAX_INSPECT_BYTES
                        or len(result.stderr or "") > MAX_INSPECT_BYTES):
                    raise ValueError("Docker admission observation exceeds bound")
                return result

            def inventory():
                result = run(["ps", "-a", "--no-trunc", "--format", "{{.ID}}"])
                identifiers = result.stdout.splitlines()
                if (result.returncode or len(identifiers) > 128 or len(set(identifiers)) != len(identifiers)
                        or any(not _CID.fullmatch(value) for value in identifiers)):
                    raise ValueError("complete Docker inventory unavailable")
                return identifiers

            def relevant(value):
                mounts, directory = value.get("Mounts"), value.get("WorkingDir")
                if (not isinstance(mounts, list) or len(mounts) > 256 or not isinstance(directory, str)
                        or any(not isinstance(mount, dict) for mount in mounts)):
                    raise ValueError("Docker workspace observation unavailable")
                # WorkingDir belongs to the container namespace; only its
                # descendants count. Bind sources are host paths and overlap
                # in either direction, including an ancestor mounted writable.
                if directory and Path(directory).is_absolute() and any(Path(directory).is_relative_to(scope) for scope in scopes):
                    return True
                for mount in mounts:
                    if not isinstance(mount.get("Type"), str) or not mount["Type"]:
                        raise ValueError("Docker mount type unavailable")
                    if mount.get("Type") != "bind":
                        continue
                    source = mount.get("Source")
                    if not isinstance(source, str) or not Path(source).is_absolute():
                        raise ValueError("Docker bind source unavailable")
                    source_path = Path(source).resolve()
                    if any(source_path.is_relative_to(scope) or scope.is_relative_to(source_path) for scope in scopes):
                        return True
                return False

            def known_stopped(value):
                image = value.get("Image")
                if (not isinstance(image, str) or not image.startswith("sha256:")
                        or not _CID.fullmatch(image[7:]) or _timestamp(value.get("Created")) > time.time()):
                    return False
                state = value.get("State")
                if (not isinstance(state, dict) or state.get("Running") is not False
                        or type(state.get("Pid")) is not int or state["Pid"] != 0
                        or state.get("Restarting") is not False or state.get("Paused") is not False
                        or state.get("Status") not in {"exited", "dead", "created"}):
                    return False
                return any(isinstance(item, dict) and item.get("container_id") == value["Id"]
                    and item.get("created") == value.get("Created") and item.get("image_id") == value.get("Image")
                    and item.get("workspace") == value.get("WorkingDir") and item.get("quiesced") is True
                    and item.get("removed") is False for item in retained)

            # Re-observe both identity and state after the first complete pass.
            # A newly arriving orphan or a retained worker restarting refuses.
            for _pass in range(2):
                for identifier in inventory():
                    result = run(["inspect", "--format", _INSPECT, identifier])
                    if result.returncode:
                        if identifier not in inventory():
                            continue
                        return False
                    value = json.loads(result.stdout)
                    if not isinstance(value, dict) or value.get("Id") != identifier:
                        return False
                    if relevant(value) and not known_stopped(value):
                        return False
        return True
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.TimeoutExpired):
        return False


def _select_worktree_root(repo_root: Path, state_dir: Path, record: Mapping[str, Any],
                          requested: Path | None) -> tuple[Path, dict[str, Any] | None]:
    previous, binding = recorded_worktree_root(record, state_dir)
    if requested is None or requested == previous:
        return previous, binding
    if record:
        identity = record.get("identity") or {}
        current = process_identity(identity.get("pid")) if isinstance(identity, dict) else None
        old_birth_alive = current and all(current.get(key) == identity.get(key) for key in ("pid", "start_ticks", "boot_id"))
        from .improvement_shutdown import _context
        if _context(state_dir, record) is None:
            raise ValueError("changing worktree root requires a full previous ownership receipt")
        if (old_birth_alive or record.get("status") != "stopped"
                or not _shutdown_verified(record, _read_json(state_dir / "container_shutdown.json"), repo_root, state_dir)):
            raise ValueError("changing worktree root requires a stopped, closure-verified previous launch")
    return requested, _validate_worktree_root(repo_root, state_dir, requested)


def process_identity(pid: int) -> dict[str, Any] | None:
    """Read Linux process birth and argv without trusting a recycled PID."""
    try:
        if type(pid) is not int or pid <= 1:
            return None
        raw = Path(f"/proc/{pid}/stat").read_text()
        fields = raw[raw.rfind(")") + 2 :].split()
        if fields[0] == "Z":
            return None
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        return {
            "pid": pid, "start_ticks": int(fields[19]),
            "ppid": int(fields[1]), "process_group": int(fields[2]),
            "session": int(fields[3]),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "argv": [part.decode(errors="replace") for part in argv if part],
        }
    except (OSError, ValueError, IndexError):
        return None


def owns_process(record: Mapping[str, Any]) -> bool:
    identity = record.get("identity")
    if not isinstance(identity, dict):
        return False
    current = process_identity(identity.get("pid"))
    token = record.get("owner_token")
    argv = record.get("argv")
    return bool(
        current and token and isinstance(argv, list)
        and "_run" in argv and "--owner-token" in argv
        and argv[argv.index("--owner-token") + 1 :][:1] == [token]
        and current["argv"] == argv
        and all(current.get(key) == identity.get(key) for key in
                ("pid", "start_ticks", "boot_id", "session", "process_group"))
        and current["session"] == current["pid"] == current["process_group"]
    )


def _context_exclusions(context_exclude: Any = None) -> list[str]:
    values = [] if context_exclude is None else context_exclude
    if not isinstance(values, list) or len(values) > 64:
        raise ValueError("context_exclude must contain at most 64 bounded repository-relative paths")
    result = list(_PRIVATE_PATHS)
    for value in values:
        if (not isinstance(value, str) or not value.strip() or len(value) > 256
                or Path(value).is_absolute() or ".." in Path(value).parts
                or value in {"*", "**", ".", "./"}):
            raise ValueError("private exclusions must be bounded repository-relative paths")
        value = value.removeprefix("./")
        # Exact mandatory directories already cover all descendant patterns.
        if any(value == item or value.startswith(item + "/") for item in result
               if "*" not in item and "?" not in item):
            continue
        if value not in result:
            result.append(value)
    if len(result) > 64:
        raise ValueError("private exclusions exceed the native 64-pattern bound")
    return result


def campaign_environment(repo_root: Path, ambient: Mapping[str, str] | None = None,
                         *, context_exclude: Any = None, state_dir: Path | None = None) -> dict[str, str]:
    """Pin routing and remove inherited campaign/fallback/command authority."""
    env = dict(os.environ if ambient is None else ambient)
    remove_exact = {
        "IMPLEMENTATION_DAEMON_COMMAND", "IPFS_ACCELERATE_AGENT_LLM_MERGE_RESOLVER_COMMAND",
        "IPFS_ACCELERATE_AGENT_PRODUCTION_PROVIDER_POLICY", "LLM_PROVIDER", "LLM_MODEL",
        "TODO_DAEMON_LLM_BACKEND", "TODO_DAEMON_LLM_PROVIDER", "TODO_DAEMON_LLM_MODEL",
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER_ATTEMPT_STORE",
        "IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT", "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB",
        "IPFS_ACCELERATE_AGENT_CONTROL_DUCKLAKE",
        "IPFS_ACCELERATE_AGENT_TASK_SOURCE_KIND", "IPFS_ACCELERATE_AGENT_EVENT_STORE_PATH",
        "IPFS_ACCELERATE_AGENT_RUNTIME_REGISTRY_PATH", "IPFS_ACCELERATE_AGENT_EXPORT_PROFILE",
    }
    for key in tuple(env):
        if key in remove_exact or key.startswith((
            "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_ROUTE_",
            "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_FALLBACK_",
            "IPFS_ACCELERATE_AGENT_PRODUCTION_PROVIDER_",
            "IPFS_ACCELERATE_AGENT_STATE_", "IPFS_ACCELERATE_AGENT_QUACK_",
            "IPFS_ACCELERATE_AGENT_DATABASE_PROGRAM_",
        )) or (key.startswith(("IPFS_ACCELERATE_", "ipfs_accelerate_py_", "TODO_DAEMON_"))
                and any(part in key.upper() for part in ("FALLBACK", "PROVIDER_POLICY"))):
            env.pop(key, None)
    env.update({
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER": "grok",
        # Once-per-recovery-revision validation rearm. Exact 0 would keep a
        # spent frontier stopped even after this supervisor repair.
        AUTOMATIC_RETRY_REARM_ENV: "1",
        "IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS": "external/ipfs_datasets_py,external/ipfs_kit_py",
        # Bound retained prepared checkouts in this campaign, without reclaiming leases.
        "IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES": "1",
        # Optional Common Crawl tooling must not clone an unrelated HEAD into
        # an intentionally uninitialized, pinned dependency during validation.
        "COMMON_CRAWL_AUTO_CLONE_SOURCE": "0",
        "IPFS_ACCELERATE_AGENT_GROK_MODEL": MODEL,
        "IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS": "64",
        "IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT": "low",
        "IPFS_ACCELERATE_PY_GROK_CLI_MODEL": MODEL,
        "ipfs_accelerate_py_GROK_CLI_MODEL": MODEL,
        "GROK_CLI_MODEL": MODEL, "GROK_MODEL": MODEL,
        "IPFS_ACCELERATE_PY_LLM_PROVIDER": "grok_cli",
        "IPFS_ACCELERATE_PY_LLM_MODEL": MODEL,
        "TODO_DAEMON_LLM_BACKEND": "llm_router",
        "TODO_DAEMON_LLM_PROVIDER": "grok_cli", "TODO_DAEMON_LLM_MODEL": MODEL,
        "TODO_DAEMON_LLM_ALLOW_LOCAL_FALLBACK": "0",
        "TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK": "0",
        PRIVATE_PATHS_ENV: json.dumps(_context_exclusions(context_exclude), separators=(",", ":")),
        ORCHESTRATION_DIR_ENV: str((state_dir or default_state_dir(repo_root)).resolve() / "control-plane"),
        "PYTHONUNBUFFERED": "1",
    })
    roots = [repo_root / "external/ipfs_accelerate_py", repo_root / "external/ipfs_datasets_py", repo_root]
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in roots)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", os.defpath)
    return env


def _native_modules(repo_root: Path):
    # Native modules discover repository defaults at import time.
    os.chdir(repo_root)
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon
    return implementation_supervisor, implementation_daemon


def _branch(repo_root: Path) -> str:
    try:
        result = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                                cwd=repo_root, text=True, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("local Git branch lookup exceeded its ten-second deadline") from exc
    if result.returncode or not result.stdout.strip():
        raise ValueError("campaign requires an explicit checked-out local Git branch")
    return result.stdout.strip()


def _private_runtime_checks(repo_root: Path, env: Mapping[str, str]) -> dict[str, Any]:
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    if env.get(AUTOMATIC_RETRY_REARM_ENV) in {"0", "1"}:
        from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
        rearm_control = getattr(native, "automatic_retry_rearm_enabled", None)
        expected = env.get(AUTOMATIC_RETRY_REARM_ENV) == "1"
        if (getattr(native, "AUTOMATIC_RETRY_REARM_ENV", None) != AUTOMATIC_RETRY_REARM_ENV
                or not callable(rearm_control) or rearm_control(env) is not expected):
            return {"ready": False, "reason": "native_retry_budget_control_unavailable"}
    supported = getattr(grok_cli_runner, "GROK_PRIVATE_PATHS_VERSION", 0) >= 1
    validator = getattr(grok_cli_runner, "validate_grok_private_path_patterns", None)
    resolver = getattr(grok_cli_runner, "_grok_private_workspace_paths", None)
    supported = supported and callable(validator) and callable(resolver)
    if not supported:
        return {"ready": False, "native_enforcement_available": False,
                "reason": "native_private_path_enforcement_unavailable"}
    if env.get(REASONING_EFFORT_ENV) and getattr(grok_cli_runner, "GROK_REASONING_EFFORT_ENV", None) != REASONING_EFFORT_ENV:
        return {"ready": False, "native_enforcement_available": True,
                "reason": "native_reasoning_effort_control_unavailable"}
    try:
        patterns = validator(env[PRIVATE_PATHS_ENV])
        resolver(base_env=dict(env), workspace=repo_root)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        # No path names or exception text enter public readiness telemetry.
        return {"ready": False, "native_enforcement_available": True,
                "reason": "native_private_path_policy_invalid"}
    # Use native root-owned Docker, fixed local socket and cached image
    # qualification; a successful ambient `docker info` is insufficient.
    docker = grok_cli_runner._docker_isolation_binary()
    base_image = ordinary_image = ""
    if docker:
        with tempfile.TemporaryDirectory(prefix="complaint-improvement-docker-config-") as directory:
            config = Path(directory)
            base_image = grok_cli_runner._docker_isolation_image_id(docker, docker_config=config)
            ordinary_image = grok_cli_runner._docker_ordinary_task_toolchain_image_id(docker, docker_config=config)
    machine = platform.machine().lower()
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(machine, machine)
    profile = getattr(grok_cli_runner, "_ordinary_task_toolchain_image_profile", None)
    image_architecture = profile()[1] if callable(profile) else ""
    architecture_matches = architecture == image_architecture
    docker_ready = bool(docker and base_image and ordinary_image and architecture_matches)
    reason = "ready"
    if not docker:
        reason = "trusted_local_docker_or_cached_base_image_unavailable"
    elif not base_image:
        reason = "cached_base_image_unavailable"
    elif not ordinary_image:
        reason = "qualified_ordinary_task_image_unavailable"
    elif not architecture_matches:
        reason = "ordinary_task_image_architecture_mismatch"
    return {"ready": docker_ready, "native_enforcement_available": True,
            "docker_ready": docker_ready, "private_path_patterns": list(patterns),
            "base_image_id": base_image, "ordinary_task_image_id": ordinary_image,
            "host_architecture": architecture, "image_architecture": image_architecture,
            "reason": reason}


def _auth_material_present(env: Mapping[str, str]) -> bool:
    """Presence only; never read credential bytes or claim provider validation."""
    if any(bool(env.get(key)) for key in (
            "XAI_API_KEY", "ipfs_accelerate_py_XAI_API_KEY", "IPFS_ACCELERATE_PY_XAI_API_KEY",
            "IPFS_DATASETS_PY_XAI_API_KEY")):
        return True
    auth_home = Path(env.get("GROK_HOME") or str(Path(env.get("HOME") or Path.home()) / ".grok"))
    try:
        entry = (auth_home / "auth.json").lstat()
        return bool(stat.S_ISREG(entry.st_mode) and entry.st_uid == os.getuid()
                    and entry.st_nlink == 1 and not entry.st_mode & 0o022
                    and 0 < entry.st_size <= 1_048_576)
    except OSError:
        return False



def _worktree_capacity(repo_root: Path, worktree_root: Path) -> dict[str, Any]:
    """Report a local pinned tracked-byte lower bound, without fetching objects."""
    probe = worktree_root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    result: dict[str, Any] = {"filesystem_path": str(probe), "free_bytes": shutil.disk_usage(probe).free,
                              "minimum_cold_checkout_bytes": None, "sufficient": None}
    minimum = 0
    try:
        repositories = [(repo_root, "HEAD")]
        for directory, revision in repositories:
            observed = subprocess.run(["git", "ls-tree", "-r", "-l", "-z", revision], cwd=directory,
                capture_output=True, check=False, timeout=10, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
            if observed.returncode or len(observed.stdout) > 16_000_000:
                raise ValueError("local pinned Git tree unavailable or exceeds bound")
            for entry in observed.stdout.split(b"\0"):
                if not entry:
                    continue
                header, name = entry.split(b"\t", 1)
                mode, kind, oid, size = header.split()
                if kind == b"blob":
                    minimum += int(size)
                elif kind == b"commit" and name == b"external/ipfs_datasets_py" and directory == repo_root:
                    repositories.append((repo_root / "external/ipfs_datasets_py", oid.decode("ascii")))
        if len(repositories) != 2:
            raise ValueError("pinned datasets tree is unavailable")
        result.update(minimum_cold_checkout_bytes=minimum, sufficient=result["free_bytes"] >= minimum,
                      reason="local_pinned_tracked_blob_lower_bound", includes_filesystem_overhead=False,
                      assumes_uncompressed_file_content=True)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result["reason"] = "local_pinned_checkout_size_unavailable"
    return result


RESOURCE_MIN_FREE_BYTES = 1_073_741_824
RESOURCE_MIN_FREE_INODES = 1024


class CampaignResourceHold(RuntimeError):
    """A local admission refusal, never a task failure/refund or live wait."""
    code = "campaign_resource_hold"

    def __init__(self, observation: Mapping[str, Any]):
        self.observation = dict(observation)
        super().__init__("campaign_resource_hold:" + str(observation.get("reason", "unavailable")))


class CampaignOperatorHold(RuntimeError):
    """Refuse the next Native pass without interrupting an active pass."""

    def __init__(self, marker: str):
        self.observation = {"schema": "complaint-campaign-operator-admission@1",
            "reason": "operator_hold_present", "marker": marker, "stage": "before_native_pass",
            "paid_dispatch": False, "accounting_changed": False, "attempt_refunded": False}
        super().__init__("campaign_operator_hold:" + marker)


def _require_no_operator_hold(state_dir: Path) -> None:
    # Any directory entry fences admission, including a dangling symlink.
    # Never read, follow, replace or retire another operator's marker.
    for name in ("HOLD", "OPERATOR_STOP"):
        try:
            (state_dir / "watchdog" / name).lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise CampaignOperatorHold(name) from None
        raise CampaignOperatorHold(name)


def _containerd_metadata_directory() -> Path:
    """Native's standard rootful containerd metadata location, independently of DockerRootDir.

    This does not discover custom/rootless/external daemon configurations.
    An absent standard directory is unavailable, never an ancestor substitute.
    """
    return Path("/var/lib/containerd")


def _native_validation_temporary_directory() -> Path:
    # Native creates each Linux validation HOME under this short root so
    # Chromium's AF_UNIX paths fit. It may differ from the profile TMPDIR.
    return Path("/tmp")


def _resource_capacity(repo_root: Path, state_dir: Path, worktree_root: Path,
                       environment: Mapping[str, str]) -> dict[str, Any]:
    """Observe each storage role without creating paths or reserving capacity.

    Free bytes/inodes and access are a point-in-time admission observation;
    other writers, quotas and subsequent IO can still fail after this check.
    """
    paths = {"repository": repo_root, "state": state_dir, "worktrees": worktree_root,
             "home": Path(environment.get("HOME") or Path.home()),
             "temporary": Path(environment.get("TMPDIR") or tempfile.gettempdir()),
             "containerd_metadata": _containerd_metadata_directory()}
    if sys.platform.startswith("linux"):
        paths["validation_temporary"] = _native_validation_temporary_directory()
    roles = {}
    timed_out = False
    for role, raw_path in paths.items():
        row: dict[str, Any] = {"path": str(raw_path), "ready": False}
        try:
            path = Path(raw_path)
            if not path.is_absolute() or path.resolve(strict=False) != path:
                raise ValueError("resource path is not canonical")
            probe = path
            daemon_metadata = role == "containerd_metadata"
            if not daemon_metadata and role != "validation_temporary":
                while not probe.exists() and probe != probe.parent:
                    probe = probe.parent
            info = probe.stat()
            if not stat.S_ISDIR(info.st_mode) or (probe != path and info.st_uid != os.getuid()):
                raise ValueError("absent resource path lacks an owned existing directory")
            available = os.statvfs(probe)
            fields = (available.f_bavail, available.f_frsize, available.f_favail, available.f_files)
            if any(type(value) is not int or value < 0 for value in fields) or fields[1] == 0 or fields[3] == 0:
                raise ValueError("resource capacity metadata is unavailable")
            free_bytes, free_inodes = fields[0] * fields[1], fields[2]
            # Rootful containerd writes its root-owned0700 metadata directory.
            # Operator access is irrelevant there; observe filesystem capacity
            # and its readonly flag without claiming daemon permission proof.
            writable = (not available.f_flag & os.ST_RDONLY and (daemon_metadata
                        or os.access(probe, os.W_OK | os.X_OK, effective_ids=True)))
            ready = bool(writable and free_bytes >= RESOURCE_MIN_FREE_BYTES and free_inodes >= RESOURCE_MIN_FREE_INODES)
            row.update(filesystem_path=str(probe), free_bytes=free_bytes, free_inodes=free_inodes,
                       writable_observed=bool(writable), ready=ready,
                       reason="observed_capacity_ready" if ready else "local_capacity_insufficient")
            if daemon_metadata:
                row.update(path_source="standard_rootful_containerd",
                           write_access_scope="filesystem_flag_for_rootful_daemon")
        except TimeoutError:
            # Native's hook alarm is an OSError subclass. Stop this observation
            # immediately; swallowing it and proceeding would lose its bound.
            timed_out = True
            row["reason"] = "resource_observation_timed_out"
            roles[role] = row
            break
        except (OSError, ValueError, TypeError, AttributeError):
            row["reason"] = "local_capacity_unavailable"
        roles[role] = row
    for role, raw_path in paths.items():
        if role not in roles:
            roles[role] = {"path": str(raw_path), "ready": False, "reason": "unobserved_after_timeout"}
    ready = all(row["ready"] for row in roles.values())
    return {"schema": "complaint-campaign-resource-admission@1", "ready": ready,
            "reason": "resource_observation_timed_out" if timed_out else ("observed_capacity_ready" if ready else "local_capacity_hold"),
            "minimum_free_bytes_per_filesystem": RESOURCE_MIN_FREE_BYTES,
            "minimum_free_inodes_per_filesystem": RESOURCE_MIN_FREE_INODES,
            "roles": roles, "capacity_reserved": False, "paid_dispatch": False,
            "attempt_refunded": False, "accounting_changed": False,
            "live_wait_or_lease_claimed": False}


def _require_resource_capacity(repo_root: Path, state_dir: Path, worktree_root: Path,
                               environment: Mapping[str, str], *, stage: str) -> None:
    observed = _resource_capacity(repo_root, state_dir, worktree_root, environment)
    if not observed["ready"]:
        raise CampaignResourceHold({**observed, "stage": stage})


def _resource_admission_hook(repo_root: Path, state_dir: Path, worktree_root: Path,
                             environment: Mapping[str, str]):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon_runner import (
        DaemonLoopHook, DaemonHookTimeoutError,
    )
    # Native's generic optional hook timeout is normally logged and ignored.
    # Convert it inside the callback so this mandatory admission check refuses
    # before run_once; every other hold also propagates through the sole loop.
    def before_pass(_context):
        _require_no_operator_hold(state_dir)
        try:
            _require_resource_capacity(repo_root, state_dir, worktree_root, environment,
                                       stage="before_native_pass")
            cold_checkout = _worktree_capacity(repo_root, worktree_root)
            if cold_checkout.get("sufficient") is not True:
                raise CampaignResourceHold({"schema": "complaint-campaign-resource-admission@1",
                    "ready": False, "reason": "cold_checkout_capacity_insufficient"
                        if cold_checkout.get("sufficient") is False else "cold_checkout_capacity_unavailable",
                    "stage": "before_native_pass", "worktree_capacity": cold_checkout,
                    "paid_dispatch": False, "accounting_changed": False, "attempt_refunded": False,
                    "capacity_reserved": False, "live_wait_or_lease_claimed": False})
        except DaemonHookTimeoutError:
            raise CampaignResourceHold({"schema": "complaint-campaign-resource-admission@1",
                "ready": False, "reason": "resource_observation_timed_out", "stage": "before_native_pass",
                "paid_dispatch": False, "accounting_changed": False, "attempt_refunded": False,
                "live_wait_or_lease_claimed": False}) from None
        # Sizing can take time. Recheck at the end of admission as well; a
        # hold created while the previous pass runs must fence the next pass.
        _require_no_operator_hold(state_dir)
    return DaemonLoopHook(phase="before", message="Campaign before-pass admission hold: %s", callback=before_pass)


def native_argv(board_path: Path, state_dir: Path, merge_target: str, *, worktree_root: Path | None = None,
                board_namespace: str = DEFAULT_ARTIFACTS.board_namespace,
                protected_paths: tuple[str, ...] = ()) -> list[str]:
    """Compile only options supported by the actual native supervisor parser."""
    return [
        "--todo-path", str(board_path), "--state-dir", str(state_dir),
        "--state-prefix", STATE_PREFIX, "--board-namespace", board_namespace,
        "--task-prefix", TASK_PREFIX, "--task-source-kind", "legacy-markdown",
        "--authority-mode", "legacy_markdown", "--explicit-legacy-task-source", "--implement",
        "--check-interval", "5", "--daemon-interval", "10",
        "--watchdog-startup-grace-seconds", str(STARTUP_SECONDS), "--stale-seconds", "120",
        "--implementation-timeout", str(TIMEOUT_SECONDS),
        "--implementation-max-timeout", str(TIMEOUT_SECONDS),
        "--implementation-log-stall-seconds", str(STALL_SECONDS),
        "--max-task-attempts", "3", "--max-restarts", "5", "--validation-max-workers", "1",
        "--worktree-reconciliation-max-merges", "2",
        "--task-shard-count", "1", "--task-shard-index", "0",
        "--worktree-root", str(worktree_root if worktree_root is not None else state_dir / "worktrees"), "--merge-target-branch", merge_target,
        # Every task validation imports datasets, and shared interviews use
        # Kit's pinned WAL even when tasks edit only first-party files.
        "--worktree-submodule-path", "external/ipfs_datasets_py",
        "--worktree-submodule-path", "external/ipfs_kit_py",
        "--merge-queue-dir", str(state_dir / "merge-queue"),
        "--llm-merge-resolver-command", "",
        # Native recovers interrupted owned proposals through the measured
        # scheduler and normal merge callback before another provider starts.
        "--no-objective-task-janitor", "--no-objective-goal-refinement",
        "--no-objective-goal-completion-reconcile", "--no-objective-goal-migration",
        "--no-objective-ast-dataset", "--no-objective-todo-vector-index",
        "--no-retry-budget-guardrail", "--no-dependency-guardrail", "--no-reconciliation-guardrail",
    ] + [argument for path in protected_paths for argument in ("--implementation-protected-path", path)]


def _board_summary(tasks: list[Any]) -> dict[str, Any]:
    completed = {task.task_id for task in tasks if task.status == "completed"}
    held = []
    ready = []
    for task in tasks:
        raw_status = str(task.metadata.get("status", task.status)).lower().replace("-", "_")
        manual = raw_status in {"paused", "waiting_user", "waiting_for_user", "on_hold", "manual_hold"}
        manual = manual or str(task.metadata.get("manual hold", "")).lower() in {"1", "true", "yes"}
        if manual:
            held.append(task.task_id)
        elif task.status in {"todo", "needed", "pending"} and set(task.depends_on) <= completed:
            ready.append(task.task_id)
    return {"count": len(tasks), "status_counts": dict(Counter(task.status for task in tasks)),
            "completed": len(completed), "ready_task_ids": ready, "manual_hold_task_ids": held}


def _validate_board(repo_root: Path, board_path: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    _, daemon = _native_modules(repo_root)
    tasks = daemon.parse_task_file(board_path, task_header_prefix=TASK_PREFIX)
    expected = {task["id"]: task for task in spec["tasks"]}
    if len(tasks) != len(expected) or {task.task_id for task in tasks} != set(expected):
        raise ValueError("native task parser did not ingest every planned task exactly once")
    for task in tasks:
        item = expected[task.task_id]
        if set(task.depends_on) != set(item["depends_on"]) or task.validation != item["validation_commands"]:
            raise ValueError(f"native task references/validation differ for {task.task_id}")
        if task.metadata.get("provider role") != "grok-only" or task.metadata.get("model") != MODEL:
            raise ValueError(f"task {task.task_id} lost its explicit Grok-only model route")
    return _board_summary(tasks)


def prepare(repo_root: Path, spec_path: Path, state_dir: Path) -> dict[str, Any]:
    os.chdir(repo_root)
    from .improvement_plan import generate, load_spec
    result = generate(spec_path, repo_root)
    result["board"] = _validate_board(repo_root, Path(result["board_path"]), load_spec(spec_path))
    result["state_dir"] = str(state_dir)
    result["execution_started"] = False
    return result


def doctor(repo_root: Path, spec_path: Path, state_dir: Path, *, merge_target: str | None = None, worktree_root: Path | None = None) -> dict[str, Any]:
    """Read-only readiness checks: never run a model, daemon, or auth command."""
    selected_root, root_binding = _select_worktree_root(repo_root, state_dir, _read_json(state_dir / "launcher.json"), worktree_root)
    resources = _resource_capacity(repo_root, state_dir, selected_root, os.environ)
    if not resources["ready"]:
        return {"status": "not_ready", "reason": CampaignResourceHold.code, "resource_capacity": resources,
                "paid_calls": 0, "native_config_validated": False, "execution_started": False}
    os.chdir(repo_root)
    from .improvement_plan import build_improvement_work_plan
    spec, artifacts = _campaign_spec(repo_root, spec_path)
    plan = build_improvement_work_plan(spec)
    branch = merge_target or _branch(repo_root)
    supervisor, _ = _native_modules(repo_root)
    args = native_argv(repo_root / artifacts.board_relative, state_dir, branch, worktree_root=selected_root,
                       board_namespace=artifacts.board_namespace, protected_paths=artifacts.protected_paths)
    parsed = supervisor.parse_args(args)
    config = supervisor.supervisor_config_from_args(parsed, repo_root=repo_root)
    board = _validate_board(repo_root, repo_root / artifacts.board_relative, spec)
    env = campaign_environment(repo_root, context_exclude=spec["execution_policy"].get("context_exclude"), state_dir=state_dir)
    grok = shutil.which(env.get("IPFS_ACCELERATE_AGENT_GROK_BIN") or "grok", path=env.get("PATH"))
    auth_present = _auth_material_present(env)
    privacy = _private_runtime_checks(repo_root, env)
    capacity = _worktree_capacity(repo_root, selected_root)
    return {"status": "ready" if grok and auth_present and privacy["ready"] and capacity["sufficient"] is not False and resources["ready"] else "not_ready",
            "provider": "grok_cli", "model": MODEL, "allow_fallback": False,
            "grok_binary_present": bool(grok), "auth_material_present": bool(auth_present),
            "auth_provider_command_supported": False,
            "auth_validated": False, "paid_calls": 0, "native_plan_id": plan.plan_id,
            "native_config_validated": True, "native_task_source": parsed.task_source_kind,
            "ephemeral_worktrees": config.use_ephemeral_worktree, "merge_target": branch,
            "privacy": privacy, "worktree_capacity": capacity, "resource_capacity": resources, "worktree_root": str(selected_root), "worktree_root_binding": root_binding,
            "board": board, "native_argv": args,
            "limitations": ["Credential presence does not verify login, quota, model access or execution progress.",
                            "Native supervisor retries are bounded per task and to five daemon restarts; manual holds are never cleared.",
                            "Cross-worktree reconciliation and dynamic guardrail/refill task generation are disabled for this fixed campaign; native dependency readiness, process fencing and implementation watchdog remain enabled."]}


def _recovery_start_admission(state_dir: Path, expected_launcher_sha256: str | None) -> str | None:
    """Keep automatic stopped recovery bound to its original launcher and holds."""
    if expected_launcher_sha256 is None:
        return None
    current = _read_json(state_dir / "launcher.json")
    digest = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if (not isinstance(expected_launcher_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_launcher_sha256) is None
            or digest != expected_launcher_sha256):
        return "launcher_changed_before_recovery"
    try:
        _require_no_operator_hold(state_dir)
        (state_dir / "implementation-protected-path-incident.json").lstat()
    except FileNotFoundError:
        return None
    except CampaignOperatorHold:
        return "watchdog_manual_hold"
    except OSError:
        return "protected_fence_unavailable"
    return "protected_incident"


def _reconcile_stopped_fence_before_start(repo_root: Path, spec_path: Path, state_dir: Path, *,
                                         expected_launcher_sha256: str | None) -> tuple[str | None, dict[str, Any] | None]:
    """Reconcile a stopped crash fence before compilation, outside start's lock.

    Marker presence only selects this admission path. The public recovery seam
    retains all Native custody, closure, accounting and callback requirements.
    """
    active = state_dir / "implementation-protected-path-active.json"
    incident = state_dir / "implementation-protected-path-incident.json"
    markers, unavailable = [], False
    for path in (active, incident):
        try:
            path.lstat()
            markers.append(path)
        except FileNotFoundError:
            pass
        except OSError:
            unavailable = True
    if not markers and not unavailable:
        return expected_launcher_sha256, None
    record = _read_json(state_dir / "launcher.json")
    # The ordinary locked route proves campaign identity and reuses this owner.
    if owns_process(record):
        return expected_launcher_sha256, None

    def refuse(reason, recovery=None):
        return expected_launcher_sha256, {"status": "not_ready", "reason": reason,
            "execution_started": False, "paid_calls": 0, "completion_authority": False,
            "prestart_recovery": recovery}

    if unavailable:
        return refuse("protected_fence_unavailable")
    if incident in markers:
        return refuse("protected_incident")
    digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    admission = _recovery_start_admission(state_dir,
        digest if expected_launcher_sha256 is None else expected_launcher_sha256)
    if admission:
        return refuse(admission)
    if (not _full_launch_record(record) or record.get("status") != "stopped"
            or not _campaign_tuple_matches(record, repo_root, spec_path, state_dir)
            or _owner_liveness(record.get("identity")) != "dead"):
        return refuse("prestart_recovery_owner_unverified")
    from .improvement_shutdown import _context, _parent_closed
    from .improvement_recovery import _owned_bytes
    try:
        snapshot = json.loads(_owned_bytes(active, 32 * 1024 * 1024, legacy_group_write=True))
        if (not isinstance(snapshot, dict)
                or snapshot.get("schema") != "implementation-protected-path-active-v1"
                or not isinstance(snapshot.get("snapshot"), dict)):
            return refuse("protected_fence_unavailable")
        before, source = _read_native_state(repo_root, state_dir / f"{STATE_PREFIX}_task_state.json")
        if not isinstance(before, dict) or not isinstance(source, dict):
            return refuse("prestart_recovery_source_unverified")
        authority = Path(str(source.get("authority_path") or ""))
        if (before.get("read_error") or source.get("source") not in {"native_control_plane", "legacy_json"}
                or not authority.is_absolute() or authority.resolve(strict=True) != authority
                or not authority.is_relative_to(state_dir) or not authority.is_file()):
            return refuse("prestart_recovery_source_unverified")
        if any(before.get(key) for key in ("manual_hold", "manual_cancellation", "capacity_quarantine", "protected_incident")):
            return refuse("prestart_recovery_native_hold")
        context = _context(state_dir, record)
        if context is None:
            return refuse("prestart_recovery_owner_unverified")
        _parent_closed(state_dir, record, context, False)
        shutdown = json.loads(_owned_bytes(state_dir / "container_shutdown.json"))
        worktrees, _ = recorded_worktree_root(record, state_dir)
        if (not _shutdown_verified(record, shutdown, repo_root, state_dir)
                or not _observe_campaign_containers(repo_root, state_dir, worktrees, record, shutdown)):
            return refuse("prestart_recovery_closure_unverified")
        admission = _recovery_start_admission(state_dir, digest)
        if admission:
            return refuse(admission)
        recovery = recover_stalled_worker(repo_root, spec_path, state_dir, expected_launcher_sha256=digest)
        if (not isinstance(recovery, dict) or recovery.get("reconciled") is not True
                or any(recovery.get(key) is not True for key in
                    ("counters_preserved", "progress_preserved", "manual_holds_preserved"))
                or any(recovery.get(key) is not False for key in
                    ("selection_performed", "paid_dispatch", "attempt_refunded", "completion_authority"))):
            return refuse("prestart_quiesced_recovery_refused", recovery)
        admission = _recovery_start_admission(state_dir, digest)
        if admission:
            return refuse(admission, recovery)
        for path in (active, incident):
            try:
                path.lstat()
                return refuse("prestart_protected_fence_retained", recovery)
            except FileNotFoundError:
                pass
        after, after_source = _read_native_state(repo_root, state_dir / f"{STATE_PREFIX}_task_state.json")
        if (not isinstance(after, dict) or after.get("read_error") or after_source != source or any(after.get(key) != before.get(key)
                for key in ("implementation_attempts", "implementation_attempts_by_cid", "completed_task_ids"))):
            return refuse("prestart_recovery_accounting_unverified", recovery)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        return refuse("prestart_recovery_evidence_unverified", {"error_type": type(error).__name__})
    # The original stopped launcher must still match under the normal start lock.
    return digest, None


def start(repo_root: Path, spec_path: Path, state_dir: Path, *, worktree_root: Path | None = None,
          expected_launcher_sha256: str | None = None) -> dict[str, Any]:
    state_dir = state_dir.resolve()
    prospective_root, _ = _select_worktree_root(repo_root, state_dir, _read_json(state_dir / "launcher.json"), worktree_root)
    resources = _resource_capacity(repo_root, state_dir, prospective_root, os.environ)
    if not resources["ready"]:
        return {"status": "not_ready", "reason": CampaignResourceHold.code, "resource_capacity": resources,
                "paid_calls": 0, "execution_started": False}
    expected_launcher_sha256, refusal = _reconcile_stopped_fence_before_start(
        repo_root, spec_path, state_dir, expected_launcher_sha256=expected_launcher_sha256)
    if refusal is not None:
        return refusal
    with _lock(state_dir):
        owner_path = state_dir / "launcher.json"
        previous = _read_json(owner_path)
        def watchdog_refusal():
            if expected_launcher_sha256 is None:
                return None
            current = _read_json(owner_path)
            digest = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_launcher_sha256) or digest != expected_launcher_sha256:
                return {"status": "stop_incomplete", "reason": "launcher_changed_before_start", "execution_started": False}
            if any(os.path.lexists(state_dir / "watchdog" / name) for name in ("HOLD", "OPERATOR_STOP")):
                return {"status": "not_ready", "reason": "watchdog_manual_hold", "execution_started": False}
            return None
        refusal = watchdog_refusal()
        if refusal is not None:
            return refusal
        if previous.get("read_error"):
            return _stop_incomplete(state_dir, "launcher_receipt_unreadable")
        selected_root, root_binding = _select_worktree_root(repo_root, state_dir, previous, worktree_root)
        full_launch = _full_launch_record(previous)
        # Compare the requested campaign before treating a live PID as this launch.
        # A matching live owner is reused; a different repo, spec, plan, or epoch is not signalled.
        if owns_process(previous):
            if full_launch and not _campaign_tuple_matches(previous, repo_root, spec_path, state_dir):
                return _stop_incomplete(state_dir, "live_campaign_mismatch")
            return {"status": "already_running", "pid": previous["identity"]["pid"], "state_dir": str(state_dir)}
        from .pending_claim_runtime import unfinished_handoff_task
        try:
            unfinished = unfinished_handoff_task(state_dir)
        except (OSError, ValueError, TypeError):
            return {"status": "not_ready", "reason": "pending_candidate_handoff_unverified",
                    "execution_started": False, "paid_calls": 0}
        if unfinished:
            return {"status": "not_ready", "reason": "pending_candidate_materialization_required",
                    "task_id": unfinished, "execution_started": False, "paid_calls": 0}
        shutdown_path = state_dir / "container_shutdown.json"
        shutdown = {}
        shutdown_raw = None
        if full_launch:
            # Campaign identity is required for stopped owners as well as live
            # ones. Cached closure never grants a different campaign ownership.
            if not _campaign_tuple_matches(previous, repo_root, spec_path, state_dir):
                return _stop_incomplete(state_dir, "stopped_campaign_mismatch")
            from .improvement_shutdown import _context, _parent_closed
            from .improvement_recovery import _owned_bytes
            try:
                context = _context(state_dir, previous)
                if context is None:
                    return _stop_incomplete(state_dir, "launcher_receipt_unverified")
                _parent_closed(state_dir, previous, context, False)
                shutdown_raw = _owned_bytes(shutdown_path)
                shutdown = json.loads(shutdown_raw)
            except (OSError, ValueError, TypeError, KeyError):
                return _stop_incomplete(state_dir, "shutdown_proof_unverified")
            if not isinstance(shutdown, dict) or not _shutdown_verified(previous, shutdown, repo_root, state_dir):
                return _stop_incomplete(state_dir, "shutdown_proof_unverified")
        # A missing owner cannot hide orphaned workers. This observation has
        # no authority to call the explicit stop helper or rewrite its receipt.
        if not _observe_campaign_containers(repo_root, state_dir, selected_root, previous, shutdown):
            return _stop_incomplete(state_dir, "container_closure_unverified")
        if _read_json(owner_path) != previous:
            return _stop_incomplete(state_dir, "ownership_changed_during_observation")
        if full_launch:
            try:
                if _owned_bytes(shutdown_path) != shutdown_raw:
                    return _stop_incomplete(state_dir, "shutdown_proof_changed_during_observation")
                _parent_closed(state_dir, previous, context, False)
                recorded_worktree_root(previous, state_dir)
            except (OSError, ValueError, TypeError, KeyError):
                return _stop_incomplete(state_dir, "ownership_changed_during_observation")
        # A missing/edited owner receipt cannot authorize a duplicate runner.
        for candidate in Path("/proc").iterdir():
            if candidate.name.isdigit():
                identity = process_identity(int(candidate.name))
                argv = identity["argv"] if identity else []
                native = any("ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_" in argument for argument in argv)
                if ("_run" in argv or native) and "--state-dir" in argv and str(state_dir) in argv:
                    raise RuntimeError("campaign runner exists without a valid owner receipt; inspect its ownership before restarting")
        initializing_cleanup = []
        if full_launch:
            from .startup_initializing_cleanup import cleanup_stopped_initializing_checkouts
            try:
                initializing_cleanup = cleanup_stopped_initializing_checkouts(sys.modules[__name__], repo_root, state_dir, previous)
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
                return {"status": "not_ready", "reason": "initializing_checkout_cleanup_unverified",
                        "error_type": type(error).__name__, "execution_started": False, "paid_calls": 0}
        prepared = prepare(repo_root, spec_path, state_dir)
        check = (doctor(repo_root, spec_path, state_dir, worktree_root=selected_root) if root_binding is not None
                 else doctor(repo_root, spec_path, state_dir))
        if check["status"] != "ready":
            return {"status": "not_ready", "doctor": check}
        if root_binding is not None:
            root_binding = _validate_worktree_root(repo_root, state_dir, selected_root, claim=True)
        token = secrets.token_hex(24)
        script = repo_root / "scripts/run_complaint_improvement_supervisor.py"
        argv = [sys.executable, str(script), "_run", "--repo-root", str(repo_root),
                "--spec", str(spec_path), "--state-dir", str(state_dir),
                "--owner-token", token, "--merge-target", check["merge_target"]]
        if root_binding is not None:
            argv.extend(["--worktree-root", str(selected_root)])
        log_path = state_dir / "launcher.log"
        from .improvement_plan import load_spec, source_generation
        launch_spec = load_spec(spec_path)
        policy = launch_spec["execution_policy"]
        refusal = watchdog_refusal()
        if refusal is not None:
            return refusal
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen(argv, cwd=repo_root, env=campaign_environment(repo_root, context_exclude=policy.get("context_exclude"), state_dir=state_dir),
                                       stdin=campaign_worker_stdin(), stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, close_fds=True)
        identity = None
        for _ in range(20):
            identity = process_identity(process.pid)
            if identity and identity["argv"] == argv:
                break
            if process.poll() is not None:
                raise RuntimeError(f"native wrapper exited before ownership registration; inspect {log_path}")
            time.sleep(0.025)
        record = {"schema_version": "complaint-improvement-launcher@1", "identity": identity,
                  "argv": argv, "owner_token": token, "started_at": time.time(),
                  "status": "starting", "repo_root": str(repo_root), "spec_path": str(spec_path),
                  "state_dir": str(state_dir), "merge_target": check["merge_target"],
                  "board_path": prepared["board_path"], "plan_id": check["native_plan_id"],
                  "source_generation": source_generation(launch_spec),
                  "provider": "grok_cli", "model": MODEL, "allow_fallback": False}
        if root_binding is not None:
            record.update(worktree_root=str(selected_root), worktree_root_binding=root_binding)
        if not owns_process(record):
            process.terminate()
            process.wait(timeout=5)
            raise RuntimeError("spawned process did not establish exact launcher ownership")
        _atomic_json(owner_path, record)
        return {"status": "starting", "pid": process.pid, "state_dir": str(state_dir),
                "initializing_checkouts_reclaimed": initializing_cleanup,
                "log_path": str(log_path), "provider": "grok_cli", "model": MODEL,
                "progress_verified": False,
                "next_check": "status must show native heartbeat and task/provider progress"}


def _tail(path: Path, *, lines: int = 12, maximum: int = 24_000) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - maximum))
            return [line[:2000] for line in handle.read(maximum).decode(errors="replace").splitlines()[-lines:]]
    except OSError:
        return []


def _age(path: Path, now: float) -> float | None:
    try:
        return max(0.0, now - path.stat().st_mtime)
    except OSError:
        return None


def _timestamp_age(value: Any, now: float) -> float | None:
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0.0, now - timestamp.timestamp())
    except (ValueError, TypeError):
        return None


def _direct_legacy_task_state(state_path: Path) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Read a JSON claim mirror when this campaign has no DuckDB authority.

    The isolated reader clears ambient Quack and DuckDB endpoints, then looks
    only beside the state file. A missing mirror still uses that reader so a
    configured control plane cannot be skipped and a deadline still applies.
    This path creates nothing and does not import the native catalog stack.
    """

    try:
        path = Path(state_path)
        if path.is_symlink() or not path.is_file():
            return None
        control = path.parent / "control-plane"
        if control.exists() and not control.is_symlink():
            for candidate in control.rglob("*"):
                if candidate.is_symlink():
                    continue
                if candidate.is_file() and candidate.suffix == ".duckdb":
                    return None
        current = path.parent
        for parent in (current, *current.parents):
            if (parent / ".git").exists() or (parent / ".git" / "agent-board-control-plane").exists():
                return None
            if parent == parent.parent:
                break
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            payload = {}
        if len(json.dumps(payload)) > 2_000_000:
            raise ValueError("native_state_size_limit")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"read_error": type(exc).__name__}, {"source": "unavailable", "completion_authority": False}
    return payload, {
        "source": "legacy_json",
        "authority_path": str(path),
        "completion_authority": False,
    }


def _native_state_reader(connection: Any, state_path: Path) -> None:
    """Read a real native projection without opening/creating a new catalog."""
    try:
        for name in ("IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT", "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB",
                     "IPFS_ACCELERATE_AGENT_CONTROL_DUCKLAKE"):
            os.environ.pop(name, None)
        from integrations.ipfs_datasets.loader import ensure_import_paths
        ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
        # Match the launcher's explicit native root; neither observation nor
        # execution may adopt global catalogs from unrelated campaigns.
        os.environ[ORCHESTRATION_DIR_ENV] = str(state_path.parent / "control-plane")
        from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
        payload = plane.read_task_state_payload(state_path)
        if payload is None and state_path.is_file():
            payload = _read_json(state_path)
        authority = plane.task_state_authority_file(state_path)
        if len(json.dumps(payload or {})) > 2_000_000:
            raise ValueError("native_state_size_limit")
        connection.send((payload or {}, {
            "source": "native_control_plane" if authority and authority != state_path else "legacy_json",
            "authority_path": str(authority) if authority else None,
            "completion_authority": False,
        }))
    except Exception as exc:
        connection.send(({"read_error": type(exc).__name__}, {"source": "unavailable", "completion_authority": False}))
    finally:
        connection.close()


def _read_native_state(repo_root: Path, state_path: Path, *, timeout_seconds: float = 3.0) -> tuple[dict[str, Any], dict[str, Any]]:
    direct = _direct_legacy_task_state(state_path)
    if direct is not None:
        return direct
    _native_modules(repo_root)
    # Native file-lock/transport timeouts can be much longer than a status
    # check. Isolate this read, enforce a deadline, and never call .load(),
    # whose default create=True may initialize a catalog.
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(target=_native_state_reader, args=(send, state_path), daemon=True)
    original_path = list(sys.path)
    try:
        # Editable installs can still point at the user's primary checkout.
        # The spawned observer must import this exact wrapper revision.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        child.start()
    finally:
        sys.path[:] = original_path
    send.close()
    try:
        if receive.poll(timeout_seconds):
            return receive.recv()
        return {"read_error": "native_state_read_timeout"}, {"source": "unavailable", "completion_authority": False}
    except (EOFError, OSError):
        return {"read_error": "native_state_reader_failed"}, {"source": "unavailable", "completion_authority": False}
    finally:
        receive.close()
        if child.is_alive():
            child.terminate()
        child.join(timeout=1)
        if child.is_alive():
            child.kill()
            child.join(timeout=1)


_PROVIDER_START_TYPES = {"implementation_provider_started", "provider_runner_started", "provider_runner_birth"}
_VALIDATION_EVENT_TYPES = {"validation_started", "validation_command_started", "validation_activity"}
_INTERVIEW_PHASES = {"waiting_for_user", "waiting_user", "awaiting_user", "manual_hold", "paused", "cancelled", "canceled"}
_COOLDOWN_NAME = "recovery_cooldown.json"


def _event_timestamp(event: Mapping[str, Any]) -> float | None:
    try:
        timestamp = datetime.fromisoformat(str(event.get("timestamp", "")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def _attempt_binding(native_state: Mapping[str, Any]) -> dict[str, Any]:
    attempt = native_state.get("active_attempt")
    if attempt in (None, "", 0, "0"):
        attempt = None
    elif isinstance(attempt, bool) or not isinstance(attempt, int):
        try:
            attempt = int(attempt)
        except (TypeError, ValueError):
            attempt = None
    log_path = native_state.get("active_log_path")
    execution_start = None
    if (native_state.get("active_task_id") and native_state.get("active_task_cid")
            and native_state.get("last_implementation_task_id") == native_state.get("active_task_id")
            and native_state.get("last_implementation_task_cid") == native_state.get("active_task_cid")
            and native_state.get("last_implementation_log_path") == log_path
            and native_state.get("last_implementation_worktree_path") == native_state.get("active_worktree_path")):
        execution_start = native_state.get("last_implementation_started_at")
    return {
        "execution_started_at": execution_start,
        "task_id": str(native_state.get("active_task_id") or native_state.get("last_implementation_task_id") or ""),
        "task_cid": str(native_state.get("active_task_cid") or native_state.get("last_implementation_task_cid") or ""),
        "attempt": attempt,
        "worktree": str(native_state.get("active_worktree_path") or native_state.get("last_implementation_worktree_path") or ""),
        "log_prefix": str(log_path) if isinstance(log_path, str) else "",
        "attempt_started_at": native_state.get("active_task_started_at") or native_state.get("last_implementation_started_at"),
    }


def _event_matches_attempt(event: Mapping[str, Any], binding: Mapping[str, Any], *, started_at: float,
                           require_log: bool) -> bool:
    """Bind one frame to this attempt. Task id alone never qualifies."""
    observed = _event_timestamp(event)
    if observed is None or observed < started_at:
        return False
    if binding.get("attempt_started_at"):
        started = _event_timestamp({"timestamp": binding.get("attempt_started_at")})
        if started is None or observed < started:
            return False
    task_id = binding.get("task_id") or ""
    if not task_id or event.get("task_id") != task_id:
        return False
    event_cid = event.get("canonical_task_cid") or event.get("task_cid")
    claim_cid = binding.get("task_cid") or ""
    if claim_cid:
        if event_cid != claim_cid:
            return False
    elif event_cid:
        return False
    event_attempt = event.get("attempt")
    claim_attempt = binding.get("attempt")
    if claim_attempt:
        if event_attempt != claim_attempt:
            return False
    elif event_attempt not in (None, ""):
        return False
    event_worktree = event.get("worktree_path") or event.get("worktree")
    claim_worktree = binding.get("worktree") or ""
    if claim_worktree:
        if event_worktree != claim_worktree:
            return False
    elif event_worktree:
        return False
    event_log = event.get("log_path") or event.get("log_prefix")
    claim_log = binding.get("log_prefix") or ""
    if claim_log and require_log:
        if not isinstance(event_log, str) or not (event_log == claim_log):
            return False
    elif event_log and claim_log and not (isinstance(event_log, str) and (event_log == claim_log)):
        return False
    elif event_log and not claim_log:
        return False
    invocation = event.get("invocation_started_at") or event.get("owned_invocation_started_at")
    if invocation is not None:
        invoked = _event_timestamp({"timestamp": invocation})
        if invoked is None or invoked < started_at:
            return False
    return True


def _grok_frame(event: Mapping[str, Any]) -> bool:
    model = str(event.get("model") or event.get("provider_model") or "")
    provider = str(event.get("provider") or "")
    if "grok" not in model.lower() and provider not in {"grok", "grok_cli"}:
        return False
    if event.get("type") in {"grok_usage", "grok_tool_call", "grok_tool_frame", "provider_usage", "provider_tool_frame"}:
        return True
    return any(event.get(key) for key in ("usage", "tool_calls", "tool_frames", "tool_frame"))


def _matching_event(path: Path, binding: Mapping[str, Any], *, started_at: float, kind: str) -> dict[str, Any] | None:
    for line in reversed(_tail(path, lines=80, maximum=256_000)):
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        provider_start = event.get("type") in _PROVIDER_START_TYPES
        validation = event.get("type") in _VALIDATION_EVENT_TYPES
        grok = _grok_frame(event)
        if kind == "provider" and not (provider_start or grok):
            continue
        if kind == "validation" and not validation:
            continue
        if not _event_matches_attempt(event, binding, started_at=started_at, require_log=provider_start or validation):
            continue
        evidence_kind = "grok_frame" if grok and not provider_start else str(event.get("type"))
        return {"type": evidence_kind, "timestamp": event.get("timestamp"), "task_id": binding.get("task_id"),
                "task_cid": binding.get("task_cid") or None, "attempt": binding.get("attempt"),
                "source": "native_daemon_events", "completion_authority": False}
    return None


def _owned_attempt_log_evidence(events_path: Path, state_dir: Path, binding: Mapping[str, Any],
                                *, started_at: float, now: float) -> dict[str, Any] | None:
    """Observe native Grok NDJSON through this exact attempt's start and log.

    Frames do not contain task/CID/time fields. The native start event and
    native text headers provide those bindings; frame contents grant no task
    completion or recovery authority. File freshness is an observation only.
    """
    from .improvement_recovery import _owned_bytes
    try:
        log = Path(str(binding.get("log_prefix") or ""))
        attempt_start = _event_timestamp({"timestamp": binding.get("execution_started_at")})
        selection_start = _event_timestamp({"timestamp": binding.get("attempt_started_at")})
        if (attempt_start is None or selection_start is None or attempt_start < selection_start or not log.is_absolute() or log.resolve(strict=True) != log
                or not log.is_relative_to(state_dir.resolve()) or not binding.get("task_cid")
                or type(binding.get("attempt")) is not int or binding["attempt"] <= 0):
            return None
        events = _owned_bytes(events_path, MAX_EVENT_HISTORY_BYTES, legacy_group_write=True)
        if not events.endswith(b"\n"):
            return None
        start = None
        repair_starts = 0
        for line in reversed(events.splitlines()):
            event = json.loads(line)
            if not isinstance(event, dict):
                return None
            if event.get("type") == "implementation_auto_rescue_provider_started":
                # Native's repair event carries task/CID/attempt, but its
                # workspace and log are inherited from the primary start.
                # That exact start is independently verified below.
                repair_binding = dict(binding)
                if not (event.get("worktree_path") or event.get("worktree")):
                    repair_binding.pop("worktree", None)
                if (_event_matches_attempt(event, repair_binding, started_at=started_at, require_log=False)
                        and event.get("strategy_changed") is True
                        and type(event.get("provider_pid")) is int and event["provider_pid"] > 1
                        and _event_timestamp(event) <= now + 2):
                    repair_starts += 1
            if event.get("type") == "implementation_started":
                # A later attempt/selection cannot borrow an earlier log.
                if not _event_matches_attempt(event, binding, started_at=started_at, require_log=True):
                    return None
                start = event
                break
            if (event.get("type") == "implementation_finished"
                    and _event_matches_attempt(event, binding, started_at=started_at, require_log=False)):
                return None
        if (start is None or start.get("execution_mode") != "model-assisted"
                or _event_timestamp(start) < attempt_start):
            return None
        before = log.lstat()
        raw = _owned_bytes(log, 32 * 1024 * 1024)
        after = log.lstat()
        if (len(raw) != before.st_size or any(getattr(before, field) != getattr(after, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))):
            return None
        if (before.st_mtime < attempt_start or now - before.st_mtime > STALL_SECONDS
                or before.st_mtime > now + 2):
            return None
        lines = raw.splitlines()
        headers = {}
        for line in lines[:8]:
            name, sep, value = line.partition(b": ")
            if sep and name in {b"Task", b"Started", b"Workspace"}:
                if name in headers:
                    return None
                headers[name] = value.decode("utf-8")
        if (headers.get(b"Task", "").split(" ", 1)[0] != binding["task_id"]
                or headers.get(b"Started") != binding.get("execution_started_at")
                or headers.get(b"Workspace") != binding.get("worktree")):
            return None
        complete = raw[:raw.rfind(b"\n") + 1]
        counts = Counter()
        terminal = False
        repair_markers = 0
        repair_open = False
        repair_progress = False
        for line in complete.splitlines():
            if line == b"[auto-rescue] inline_provider_rescue start":
                repair_markers += 1
                repair_open = True
                repair_progress = False
            elif (line.startswith(b"[auto-rescue] inline_provider_rescue returncode=")
                    or line.startswith(b"[auto-rescue] inline_provider_rescue error:")):
                repair_open = False
                repair_progress = False
            if not line.startswith(b"{"):
                continue
            try:
                frame = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(frame, dict):
                continue
            kind = frame.get("type")
            if type(kind) is not str:
                continue
            if kind == "usage" and isinstance(frame.get("usage"), dict):
                counts["usage"] += 1
                # A native repair round can append to this same owned log.
                terminal = False
                repair_progress = repair_open
            elif kind in {"tool_call", "tool_call_update"}:
                counts[kind] += 1
                terminal = False
                repair_progress = repair_open
            elif kind in {"end", "error", "max_turns_reached"}:
                terminal = True
                repair_progress = False
        if not counts:
            return None
        return {"type": "grok_frame", "source": "owned_attempt_log", "task_id": binding["task_id"],
                "task_cid": binding["task_cid"], "attempt": binding["attempt"],
                "log_path": str(log), "log_bytes": len(raw), "log_mtime_ns": before.st_mtime_ns,
                "frame_counts": dict(counts), "provider_terminal_observed": terminal,
                "provider_repair_in_flight": bool(repair_starts and repair_markers == repair_starts
                    and repair_open and repair_progress and not terminal),
                "progress_fresh": not terminal, "completion_authority": False}
    except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError):
        return None


def _provider_event_evidence(path: Path, *, task_id: str, started_at: float,
                             binding: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    resolved = dict(binding or {})
    resolved.setdefault("task_id", task_id)
    return _matching_event(path, resolved, started_at=started_at, kind="provider")


def _validation_event_evidence(path: Path, binding: Mapping[str, Any], *, started_at: float) -> dict[str, Any] | None:
    return _matching_event(path, binding, started_at=started_at, kind="validation")


def campaign_worker_stdin():
    """Campaign workers never read a complaint or interview answer from stdin."""
    return subprocess.DEVNULL


def _campaign_scope_liveness(native_state: Mapping[str, Any], *, phase: str, interview_state: str | None,
                             worker_liveness: str, active: bool, attempt_age: float | None,
                             active_age: float | None, heartbeat_fresh: bool,
                             provider_fresh: bool, provider_terminal: bool,
                             validation_fresh: bool, now: float, provider_repair: bool = False,
                             canonical_validation_active: bool = False) -> dict[str, Any]:
    """Project five execution scopes without folding in an application interview.

    Typed stall classification comes from the existing native progress and
    worktree monitors. This projection does not edit claims, refund attempts,
    complete tasks, or retry a provider.
    """
    interview_hold = interview_state in {"awaiting_user", "paused", "manual_hold", "cancelled"}
    claim_id = str(native_state.get("active_task_id") or "")
    if not claim_id:
        claim = "absent"
    elif (attempt_age is not None and attempt_age > TIMEOUT_SECONDS
            # A verified repair keeps Native's original execution-event and
            # phase deadlines; its earlier selection clock is not expiry.
            and not ((canonical_validation_active or provider_repair) and active and not interview_hold
                     and phase.startswith("valid") and worker_liveness == "alive")):
        claim = "expired"
    elif worker_liveness in {"dead", "pid_reuse"}:
        claim = "owner_dead"
    elif worker_liveness == "alive":
        claim = "held"
    else:
        claim = "unknown"
    provider_phase = active and not interview_hold and (provider_repair or phase in {"", "implementing", "implementation", "provider"})
    validation_phase = active and not interview_hold and phase.startswith("valid") and not provider_repair
    merge_phase = active and not interview_hold and "merge" in phase
    monitors: dict[str, Any] = {"completion_authority": False, "progress": {}, "worktree_worker": None,
                                "dependency_error": None}
    try:
        from ipfs_accelerate_py.agent_supervisor.rescue.supervisor_watchdog import classify_progress_stall
        from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor import worktree_phase_worker_status
    except Exception as exc:
        monitors["dependency_error"] = type(exc).__name__
        unavailable = "unavailable"
        return {"claim": claim if monitors["dependency_error"] is None else unavailable,
                "worker": worker_liveness, "provider": unavailable, "validation": unavailable,
                "merge": unavailable, "monitors": monitors, "completion_authority": False}

    def progress(scope: str, in_scope: bool) -> dict[str, Any]:
        report = classify_progress_stall(
            process_alive=worker_liveness == "alive",
            heartbeat_stale=not heartbeat_fresh,
            active_task_id="" if interview_hold or not in_scope else claim_id,
            log_age_seconds=active_age,
            task_transition_age_seconds=attempt_age,
            quiet_seconds=float(STALL_SECONDS),
        )
        monitors["progress"][scope] = report
        return report

    for name, enabled in (("provider", provider_phase), ("validation", validation_phase), ("merge", merge_phase)):
        progress(name, enabled)
    started = native_state.get("active_phase_started_at") or native_state.get("active_task_started_at")
    worktree = worktree_phase_worker_status(
        {"active_phase": phase, "active_phase_started_at": started},
        daemon_pid=0, threshold_seconds=float(STALL_SECONDS), descendants=[],
        now=datetime.fromtimestamp(now, timezone.utc),
    )
    monitors["worktree_worker"] = {
        "phase": worktree.get("phase"),
        "required": worktree.get("required"),
        "stalled_without_active_worker": worktree.get("stalled_without_active_worker"),
        "stall_evidence_unavailable_reason": worktree.get("stall_evidence_unavailable_reason"),
        "completion_authority": False,
    }

    def activity(scope: str, in_scope: bool, fresh: bool, terminal: bool) -> str:
        if interview_hold:
            return "excluded_interview"
        if not in_scope:
            return "idle"
        if fresh:
            return "fresh"
        if terminal:
            return "terminal"
        report = monitors["progress"][scope]
        if report.get("progress_stalled") or worktree.get("stalled_without_active_worker") is True:
            return "stalled"
        if attempt_age is not None and attempt_age > TIMEOUT_SECONDS:
            return "expired"
        if worker_liveness in {"dead", "pid_reuse"}:
            return "owner_dead"
        if not heartbeat_fresh:
            return "heartbeat_stale"
        return "quiet"

    return {
        "claim": claim,
        "worker": worker_liveness,
        "provider": activity("provider", provider_phase, provider_fresh, provider_terminal),
        "validation": activity("validation", validation_phase, validation_fresh, False),
        "merge": activity("merge", merge_phase, False, False),
        "monitors": monitors,
        "completion_authority": False,
    }


def _owner_liveness(birth: Any) -> str:
    if not isinstance(birth, dict) or not birth.get("pid"):
        return "missing"
    try:
        current = process_identity(int(birth["pid"]))
    except (OSError, ValueError, TypeError):
        return "unknown"
    if not isinstance(current, dict):
        return "dead"
    if current.get("unknown") or current.get("start_ticks") is None or current.get("boot_id") is None:
        return "unknown"
    if (current.get("start_ticks") != birth.get("start_ticks", birth.get("start_time_ticks"))
            or current.get("boot_id") != birth.get("boot_id")):
        return "pid_reuse"
    return "alive"


_NATIVE_CLOSE_KINDS = ("validation_accepted", "merge_accepted", "completion_callback_accepted")


def _artifact_digest(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            return {"present": False, "sha256": None, "reason": "unavailable"}
        raw = path.read_bytes()
    except OSError as exc:
        return {"present": False, "sha256": None, "reason": type(exc).__name__}
    return {"present": True, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _accepted_native_closures(events_path: Path, *, plan_id: str, source_generation: str,
                              task_cids: Mapping[str, str]) -> dict[str, Any]:
    """Close a task only from accepted validation, merge, and callback events.

    Characterization frames and manual metadata never count, and a frame for a
    different plan, CID, or source generation cannot close this campaign.
    """

    satisfied = {task_id: set() for task_id in task_cids}
    report: dict[str, Any] = {"status": "absent", "closed_task_ids": [],
                              "ignored_characterization": 0, "ignored_manual": 0}
    try:
        if not events_path.is_file() or events_path.is_symlink():
            return report
        if events_path.stat().st_size > MAX_EVENT_HISTORY_BYTES:
            report["status"] = "size_limit"
            return report
        raw = events_path.read_bytes()
    except OSError as exc:
        report["status"] = type(exc).__name__
        return report
    report["status"] = "read"
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("counts_as_characterization_pass") is True or event.get("type") == "characterization":
            report["ignored_characterization"] += 1
            continue
        if event.get("manual") is True or event.get("type") in {"manual_completion", "manual_metadata"}:
            report["ignored_manual"] += 1
            continue
        kind = event.get("type")
        if kind not in _NATIVE_CLOSE_KINDS or event.get("accepted") is not True:
            continue
        if event.get("skipped") is True or event.get("outcome") in {"skipped", "failed", "error", "xfailed"}:
            continue
        task_id = event.get("task_id")
        if not isinstance(task_id, str) or task_cids.get(task_id) != event.get("canonical_task_cid"):
            continue
        if event.get("plan_id") != plan_id or event.get("source_generation") != source_generation:
            continue
        satisfied[task_id].add(kind)
    report["closed_task_ids"] = sorted(
        task_id for task_id, kinds in satisfied.items() if set(kinds) == set(_NATIVE_CLOSE_KINDS)
    )
    return report


def observe_separate_campaign(repo_root: Path, spec_path: Path, state_dir: Path) -> dict[str, Any]:
    """Read one separate campaign through the public Native status seam.

    The completed intake spec, plan, and board are hashed before and after and
    are never rewritten. This observation does not start a provider or grant
    completion authority.
    """

    from .improvement_plan import BOARD_RELATIVE, PLAN_RELATIVE, campaign_observation_binding

    repo_root = Path(repo_root).resolve()
    spec_path = Path(spec_path)
    state_dir = Path(state_dir)
    spec, artifacts = _campaign_spec(repo_root, spec_path)
    if artifacts == DEFAULT_ARTIFACTS:
        raise ValueError("separate campaign observation requires a distinct artifact namespace")
    historical_names = (SPEC_RELATIVE, PLAN_RELATIVE, BOARD_RELATIVE)
    before = {relative: _artifact_digest(repo_root / relative) for relative in historical_names}
    binding = campaign_observation_binding(spec)
    observed = status(repo_root, spec_path, state_dir)
    after = {relative: _artifact_digest(repo_root / relative) for relative in historical_names}
    identity_error = None
    identities: list[Any] = []
    try:
        _, daemon = _native_modules(repo_root)
        identities = list(daemon.parse_task_file(repo_root / artifacts.board_relative, task_header_prefix=TASK_PREFIX))
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        identity_error = type(exc).__name__
    task_cids = {task.task_id: task.canonical_task_cid for task in identities}
    markdown_completed = sorted(task.task_id for task in identities if task.status == "completed")
    characterization = sorted(
        task.task_id for task in identities
        if str(task.metadata.get("counts as characterization pass", "")).lower() in {"1", "true", "yes"}
        or str(task.metadata.get("characterization", "")).lower() in {"pass", "passed", "complete", "completed"}
    )
    manual = sorted(
        task.task_id for task in identities
        if str(task.metadata.get("manual completion", "")).lower() in {"1", "true", "yes", "allowed"}
        or str(task.metadata.get("completion", "")).lower() == "manual"
    )
    record = _read_json(state_dir / "launcher.json")
    recorded_plan = record.get("plan_id")
    recorded_generation = record.get("source_generation")
    if record.get("read_error"):
        plan_bound = generation_bound = False
    elif record.get("schema_version"):
        plan_bound = recorded_plan == binding["plan_id"]
        generation_bound = recorded_generation == binding["source_generation"]
    else:
        plan_bound = recorded_plan in (None, binding["plan_id"])
        generation_bound = recorded_generation in (None, "", binding["source_generation"])
    closures = _accepted_native_closures(
        state_dir / f"{STATE_PREFIX}_events.jsonl",
        plan_id=binding["plan_id"], source_generation=binding["source_generation"], task_cids=task_cids,
    )
    if not plan_bound or not generation_bound:
        closures = {**closures, "closed_task_ids": [], "rejected_reason": "plan_or_source_generation_mismatch"}
    env = campaign_environment(repo_root, state_dir=state_dir)
    merge_target = record.get("merge_target") if isinstance(record.get("merge_target"), str) else "campaign-test"
    argv = native_argv(
        repo_root / artifacts.board_relative, state_dir, merge_target,
        board_namespace=artifacts.board_namespace, protected_paths=artifacts.protected_paths,
    )
    workers = argv[argv.index("--validation-max-workers") + 1] if "--validation-max-workers" in argv else None
    timeout = argv[argv.index("--implementation-timeout") + 1] if "--implementation-timeout" in argv else None
    historical_tasks = None
    historical_error = None
    if before[BOARD_RELATIVE]["present"]:
        try:
            _, daemon = _native_modules(repo_root)
            historical = list(daemon.parse_task_file(repo_root / BOARD_RELATIVE, task_header_prefix=TASK_PREFIX))
            historical_tasks = {
                "count": len(historical),
                "markdown_completed": sum(task.status == "completed" for task in historical),
                "remapped": False, "completion_authority": False,
            }
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            historical_error = type(exc).__name__
    else:
        historical_error = "unavailable"
    active_cid = (observed.get("native_state") or {}).get("active_task_cid")
    return {
        "schema": "complaint-campaign-health-observation@1",
        "status": observed.get("status"),
        "healthy": bool(observed.get("healthy") and plan_bound and generation_bound),
        "native_state_source": observed.get("native_state_source"),
        "native_read_errors": observed.get("native_read_errors"),
        "binding": binding,
        "plan_bound": bool(plan_bound),
        "source_generation_bound": bool(generation_bound),
        "task_cids": task_cids,
        "active_task_cid": active_cid,
        "active_task_cid_bound": active_cid in (None, "") or active_cid in set(task_cids.values()),
        "identity_error": identity_error,
        "markdown_completed_task_ids": markdown_completed,
        "characterization_task_ids": characterization,
        "manual_metadata_task_ids": manual,
        "native_closed_task_ids": list(closures["closed_task_ids"]),
        "native_closure": closures,
        "markdown_or_characterization_grants_completion": False,
        "provider_started": False,
        "paid_calls": 0,
        "completion_authority": False,
        "route": {
            "provider": "grok_cli", "model": MODEL, "allow_fallback": False,
            "router": env.get("TODO_DAEMON_LLM_BACKEND"),
            "pool_max_entries": env.get("IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES"),
            "implementation_timeout_seconds": TIMEOUT_SECONDS,
            "argv_implementation_timeout": timeout,
            "max_agent_turns": env.get("IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"),
            "validation_max_workers": workers,
            "implement": "--implement" in argv,
            "fallback_disabled": env.get("TODO_DAEMON_LLM_ALLOW_LOCAL_FALLBACK") == "0"
            and env.get("TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK") == "0",
            "resource_min_free_bytes": RESOURCE_MIN_FREE_BYTES,
            "resource_min_free_inodes": RESOURCE_MIN_FREE_INODES,
        },
        "historical_baseline": {
            **binding["historical_baseline"],
            "before": before, "after": after, "unchanged": before == after,
            "tasks": historical_tasks, "read_error": historical_error,
        },
    }


_HISTORICAL_CAMPAIGN_RELATIVES = (
    "docs/task_boards/complaint_intake_improvement_spec.json",
    "docs/task_boards/complaint_intake_formal_work_plan.json",
    "docs/task_boards/complaint_intake_task_board.md",
    "docs/task_boards/complaint_mediator_grounding_spec.json",
    "docs/task_boards/complaint_mediator_grounding_formal_work_plan.json",
    "docs/task_boards/complaint_mediator_grounding_task_board.md",
    "docs/task_boards/complaint_gui_collaboration_spec.json",
    "docs/task_boards/complaint_gui_collaboration_formal_work_plan.json",
    "docs/task_boards/complaint_gui_collaboration_task_board.md",
)
_HISTORICAL_NAMESPACES = frozenset({
    "complaint-intake-improvement", "complaint-mediator-grounding", "complaint-gui-collaboration",
})
_PRESERVED_STATE_NAMES = ("budget.json", "receipts.jsonl", "accounting.json")
_BOUNDED_PHASES = frozenset({"implementing", "validating"})


def _snapshot_paths(paths: Sequence[Path]) -> dict[str, str | None]:
    digest: dict[str, str | None] = {}
    for path in paths:
        key = str(path)
        try:
            if path.is_symlink() or not path.is_file():
                digest[key] = None
            else:
                digest[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest[key] = None
    return digest


def _daemon_birth_owned(record: Mapping[str, Any], state_dir: Path) -> bool:
    """Observe Native's managed birth and exact command, never heartbeat PID fields alone."""
    try:
        from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
        heartbeat = _read_validation_watchdog_authority(state_dir / f"{STATE_PREFIX}_supervisor_status.json")
        identity_path = state_dir / f"{STATE_PREFIX}_managed_daemon.identity.json"
        if heartbeat is None or _read_validation_watchdog_authority(identity_path) is None:
            return False
        parent = record.get("identity") or {}
        pid = heartbeat.get("daemon_pid")
        if (type(pid) is not int or pid <= 1 or heartbeat.get("status") != "running"
                or heartbeat.get("supervisor_pid") != parent.get("pid")
                or heartbeat.get("daemon_pid_alive") is False
                or (age := _timestamp_age(heartbeat.get("updated_at"), time.time())) is None
                or not 0 <= age <= 120):
            return False
        child = native.load_supervised_child_identity(identity_path)
        current = process_identity(pid)
        scope = {"repo_root": record["repo_root"], "state_dir": str(state_dir), "state_prefix": STATE_PREFIX,
                 "todo_path": record["board_path"], "daemon_entrypoint": str(Path(__file__).resolve())}
        if (child is None or not current or current.get("ppid") != parent.get("pid")
                or child.process_birth.pid != pid or child.process_birth.parent_pid != parent.get("pid")
                or native.read_process_birth(pid) != child.process_birth
                or native.supervised_child_identity_liveness(child) is not native.OwnerLiveness.ALIVE
                or dict(child.owner_scope) != scope
                or native.read_process_command_argv(pid) != child.command):
            return False
        # Native's ordinary wrapper command has an exact entrypoint and one
        # occurrence of each campaign option. A python -c marker is not a daemon.
        command = tuple(child.command)
        if len(command) < 2 or command[1] != scope["daemon_entrypoint"]:
            return False
        for option, value in (("--state-dir", str(state_dir)), ("--state-prefix", STATE_PREFIX),
                              ("--todo-path", record["board_path"])):
            if [command[i + 1] for i, part in enumerate(command[:-1]) if part == option] != [value]:
                return False
        return native.read_process_birth(pid) == child.process_birth
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _startup_provider_evidence(repo_root: Path, state_dir: Path, record: Mapping[str, Any],
                               state: Mapping[str, Any], *, now: float) -> dict[str, Any] | None:
    """Join Native's current claim, live provider process and owned work frames."""
    from types import SimpleNamespace
    from .improvement_recovery import _owned_bytes
    try:
        daemon, native, _ = _validation_activity_modules()
        binding = _attempt_binding(state)
        owner = native.load_supervised_child_identity(state_dir / f"{STATE_PREFIX}_managed_daemon.identity.json")
        if owner is None:
            return None
        expected = {"task_id": binding["task_id"], "canonical_task_cid": binding["task_cid"],
                    "canonical_task_key": state.get("active_task_key"), "attempt": binding["attempt"]}
        claim_path = daemon.PortalImplementationDaemon._implementation_task_claim_path(
            SimpleNamespace(repo_root=repo_root), binding["task_id"], canonical_task_cid=binding["task_cid"])
        claim = _read_validation_watchdog_authority(claim_path)
        lease = _read_validation_watchdog_authority(state_dir / "implementation.lock")
        if (claim is None or lease is None or not expected["canonical_task_key"]
                or claim.get("kind") != native.IMPLEMENTATION_TASK_CLAIM_LOCK_KIND
                or claim.get("lease_role") != native.IMPLEMENTATION_DISPATCH_INTENT_LEASE_ROLE
                or lease.get("kind") != "implementation" or lease.get("lease_role") == "supervisor_maintenance"
                or native.ProcessBirthIdentity.from_dict(claim.get("owner_process_birth")) != owner.process_birth
                or not native.checkout_lock_repository_matches(claim, repo_root)
                or claim.get("dispatch_authority_cid") != daemon.PortalImplementationDaemon._implementation_dispatch_authority_cid(claim)
                or any(not value.get("lease_id") or value.get("pid") != owner.process_birth.pid
                       or value.get("state_dir") != str(state_dir)
                       or any(value.get(key) != item for key, item in expected.items()) for value in (claim, lease))
                or claim.get("state_path") != str(state_dir / f"{STATE_PREFIX}_task_state.json")
                or lease.get("repo_root") != str(repo_root)):
            return None
        started = float(record["started_at"])
        event_path = state_dir / f"{STATE_PREFIX}_events.jsonl"
        log_evidence = _owned_attempt_log_evidence(event_path, state_dir, binding, started_at=started, now=now)
        if not log_evidence or not log_evidence.get("progress_fresh") or log_evidence.get("provider_terminal_observed"):
            return None
        rows = [json.loads(line) for line in _owned_bytes(event_path, MAX_EVENT_HISTORY_BYTES,
                                                        legacy_group_write=True).splitlines()]
        primary = next(row for row in reversed(rows) if row.get("type") == "implementation_started")
        command = primary.get("command")
        event_time = _event_timestamp(primary)
        if (not _event_matches_attempt(primary, binding, started_at=started, require_log=True)
                or not isinstance(command, list) or not command or not all(type(item) is str and item for item in command)
                or event_time is None or not 0 <= now - event_time < float(TIMEOUT_SECONDS)):
            return None
        workspace = Path(binding["worktree"])
        selected_root, _ = recorded_worktree_root(record, state_dir)
        if workspace.resolve(strict=True) != workspace or workspace == selected_root or not workspace.is_relative_to(selected_root):
            return None
        log_info = Path(binding["log_prefix"]).lstat()
        boot_time = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines() if line.startswith("btime "))
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            birth = native.read_process_birth(int(entry.name))
            if (birth is None or birth.parent_pid != owner.process_birth.pid or birth.boot_id != owner.process_birth.boot_id
                    or native.read_process_command_argv(birth.pid) != tuple(command)):
                continue
            born_at = boot_time + birth.start_time_ticks / os.sysconf("SC_CLK_TCK")
            if (not event_time - 2 <= born_at <= now or entry.stat().st_uid != os.getuid()
                    or Path(os.readlink(entry / "cwd")) != workspace
                    or os.getsid(birth.pid) != birth.pid or os.getpgid(birth.pid) != birth.pid):
                continue
            if any((info.st_dev, info.st_ino) != (log_info.st_dev, log_info.st_ino)
                   for info in ((entry / "fd" / str(number)).stat() for number in (1, 2))):
                continue
            if native.read_process_birth(birth.pid) == birth and native.read_process_birth(owner.process_birth.pid) == owner.process_birth:
                return {"source": "owned_native_provider_and_work_frames", "task_id": expected["task_id"],
                        "task_cid": expected["canonical_task_cid"], "attempt": expected["attempt"],
                        "owner_birth": owner.process_birth.to_dict(), "provider_birth": birth.to_dict(),
                        "deadline_at": event_time + TIMEOUT_SECONDS, "completion_authority": False}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration):
        return None
    return None


def _bounded_provider_validation(repo_root: Path, state_dir: Path, task_cids: Mapping[str, str],
                                 native_tasks: Sequence[Any]) -> dict[str, Any]:
    """Observe real current work; phase metadata alone cannot grant execution."""
    native_state, source = _read_native_state(repo_root, state_dir / f"{STATE_PREFIX}_task_state.json")
    now = time.time()
    attempt = native_state.get("active_attempt")
    phase = str(native_state.get("active_phase") or "")
    task_id = native_state.get("active_task_id")
    age = _timestamp_age(native_state.get("active_phase_started_at"), now)
    known = isinstance(task_id, str) and task_cids.get(task_id) == native_state.get("active_task_cid")
    declared = next((task for task in native_tasks if task.task_id == task_id), None)
    commands = list(getattr(declared, "validation", ()) or ()) if declared is not None else []
    bounded = bool(native_state.get("implementation_in_progress") is True and phase in _BOUNDED_PHASES and known
                   and type(attempt) is int and 1 <= attempt <= 3
                   and age is not None and 0 <= age < float(TIMEOUT_SECONDS) and commands
                   and declared.canonical_task_key == native_state.get("active_task_key")
                   and not any(native_state.get(key) for key in
                               ("manual_hold", "manual_cancellation", "capacity_quarantine", "protected_incident")))
    evidence = None
    record = _read_json(state_dir / "launcher.json")
    if bounded and owns_process(record) and _daemon_birth_owned(record, state_dir):
        if phase == "validating":
            from .reconciliation_activity import evidence as executor_evidence
            evidence = executor_evidence(sys.modules[__name__], repo_root, state_dir, record, native_state, now_ts=now)
            if evidence is None:
                from .auto_rescue_activity import observe
                rescue = observe(sys.modules[__name__], repo_root, state_dir, native_state, now_ts=now)
                if rescue.get("activity_verified") is True and rescue.get("work_progress_verified") is True:
                    evidence = rescue
        else:
            evidence = _startup_provider_evidence(repo_root, state_dir, record, native_state, now=now)
    # A racing settlement/new attempt cannot borrow the previous work proof.
    if evidence is not None:
        current, _ = _read_native_state(repo_root, state_dir / f"{STATE_PREFIX}_task_state.json")
        keys = ("implementation_in_progress", "active_task_id", "active_task_cid", "active_task_key", "active_attempt",
                "active_phase", "active_phase_started_at", "active_log_path", "active_worktree_path")
        final_age = _timestamp_age(current.get("active_phase_started_at"), time.time())
        deadline = evidence.get("deadline_at")
        if (any(current.get(key) != native_state.get(key) for key in keys)
                or final_age is None or not 0 <= final_age < float(TIMEOUT_SECONDS)
                or type(deadline) not in (int, float) or not math.isfinite(deadline) or time.time() >= deadline
                or not _daemon_birth_owned(record, state_dir)):
            evidence = None
    return {
        "active": bool(bounded and evidence is not None),
        "phase_metadata_bounded": bounded,
        "work_evidence": evidence,
        "phase": phase,
        "attempt": attempt if type(attempt) is int else None,
        "task_id": task_id if isinstance(task_id, str) else None,
        "phase_age_seconds": age,
        "attempt_cap": 3,
        "timeout_seconds": TIMEOUT_SECONDS,
        "validation_commands": commands,
        "native_state_source": source,
        "completion_authority": False,
    }


def qualify_new_campaign_startup(repo_root: Path, spec_path: Path, state_dir: Path, *,
                                 worktree_root: Path) -> dict[str, Any]:
    """Observe a new campaign's published bindings without treating readiness as execution.

    Ingestion, a live PID, and a ready doctor report do not execute provider or
    validation work. Execution is admitted only for an owned launcher birth, its
    daemon child, and a bounded in-progress provider or validation phase. This
    read does not rewrite historical campaigns, task status, receipts, or budgets.
    """

    from .improvement_plan import campaign_observation_binding

    started = Path.cwd()
    repo_root = Path(repo_root).resolve()
    spec_path = Path(spec_path).resolve()
    state_dir = Path(state_dir).resolve()
    worktree_root = Path(worktree_root).resolve()
    import_root = Path(__file__).resolve().parents[2]
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))
    try:
        _native_modules(import_root)
        spec, artifacts = _campaign_spec(repo_root, spec_path)
        binding = campaign_observation_binding(spec)
        plan_path = repo_root / artifacts.plan_relative
        board_path = repo_root / artifacts.board_relative
        historical_paths = [repo_root / relative for relative in _HISTORICAL_CAMPAIGN_RELATIVES]
        preserved_paths = [state_dir / name for name in _PRESERVED_STATE_NAMES]
        watched = [*historical_paths, *preserved_paths, board_path, plan_path, spec_path]
        before = _snapshot_paths(watched)
        locations = {
            "repository": repo_root, "spec": spec_path, "plan": plan_path,
            "board": board_path, "state": state_dir, "worktree": worktree_root,
        }
        distinct_paths = len({path.resolve() for path in locations.values()}) == len(locations)
        outside = (not state_dir.is_relative_to(repo_root) and not repo_root.is_relative_to(state_dir)
                   and not worktree_root.is_relative_to(repo_root) and not repo_root.is_relative_to(worktree_root)
                   and not worktree_root.is_relative_to(state_dir) and not state_dir.is_relative_to(worktree_root))
        historical_collision = (artifacts.board_namespace in _HISTORICAL_NAMESPACES
                                or bool(set(artifacts.protected_paths) & set(_HISTORICAL_CAMPAIGN_RELATIVES))
                                or artifacts == DEFAULT_ARTIFACTS)
        identities_independent = bool(distinct_paths and outside and not historical_collision
                                      and binding["distinct_from_historical_intake"])
        worktree_error = None
        worktree_identity = None
        try:
            worktree_identity = _worktree_directory(worktree_root, repo_root, state_dir)
        except (OSError, ValueError) as exc:
            worktree_error = type(exc).__name__
            identities_independent = False
        publisher: dict[str, Any] = {"bound": False, "plan_id": None, "source_generation": None, "task_ids": []}
        try:
            document = json.loads(plan_path.read_text(encoding="utf-8"))
            from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan
            restored = FormalWorkPlan.from_dict(document)
            metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
            published_ids = {task.task_id for task in restored.tasks}
            publisher = {
                "bound": (restored.plan_id == document.get("plan_id") == binding["plan_id"]
                          and metadata.get("spec_sha256") == binding["source_generation"]
                          and restored.events == () and published_ids == {task["id"] for task in spec["tasks"]}),
                "plan_id": document.get("plan_id"),
                "source_generation": metadata.get("spec_sha256"),
                "task_ids": sorted(published_ids),
                "event_count": len(restored.events),
            }
        except (OSError, ValueError, TypeError, KeyError) as exc:
            publisher["error"] = type(exc).__name__
        identity_error = None
        native_tasks: list[Any] = []
        try:
            _, daemon = _native_modules(import_root)
            native_tasks = list(daemon.parse_task_file(board_path, task_header_prefix=TASK_PREFIX))
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            identity_error = type(exc).__name__
        task_cids = {task.task_id: task.canonical_task_cid for task in native_tasks}
        task_bindings = {
            task.task_id: {
                "canonical_task_cid": task.canonical_task_cid,
                "canonical_task_key": task.canonical_task_key,
                "depends_on": list(task.depends_on),
                "validation": list(task.validation),
                "status": task.status,
            }
            for task in native_tasks
        }
        expected = {task["id"]: task for task in spec["tasks"]}
        try:
            from .improvement_plan import _require_matching_projection
            _require_matching_projection(board_path.read_text(encoding="utf-8"), spec, binding["plan_id"], repo_root)
            semantic_match = True
        except (OSError, ValueError, TypeError, KeyError):
            semantic_match = False
        tasks_match_publisher = bool(publisher["bound"] and semantic_match and set(task_cids) == set(expected)
                                     and all(task_bindings[task_id]["depends_on"] == list(expected[task_id]["depends_on"])
                                             and task_bindings[task_id]["validation"] == list(expected[task_id]["validation_commands"])
                                             for task_id in expected))
        record = _read_json(state_dir / "launcher.json")
        plan_bound = record.get("plan_id") == binding["plan_id"]
        generation_bound = record.get("source_generation") == binding["source_generation"]
        launcher_birth = bool(owns_process(record) and plan_bound and generation_bound
                              and _campaign_tuple_matches(record, repo_root, spec_path, state_dir))
        if launcher_birth and worktree_identity is not None:
            try:
                recorded_root, recorded_binding = recorded_worktree_root(record, state_dir)
                launcher_birth = recorded_root == worktree_root and recorded_binding is not None
            except (OSError, ValueError, TypeError):
                launcher_birth = False
        elif worktree_identity is None:
            launcher_birth = False
        daemon_birth = _daemon_birth_owned(record, state_dir) if launcher_birth else False
        bounded = _bounded_provider_validation(repo_root, state_dir, task_cids, native_tasks)
        pid = (record.get("identity") or {}).get("pid") if isinstance(record.get("identity"), dict) else None
        pid_alive = process_identity(pid) is not None if type(pid) is int else False
        doctor_report: dict[str, Any]
        try:
            doctor_report = doctor(repo_root, spec_path, state_dir, worktree_root=worktree_root)
        except Exception as exc:
            doctor_report = {"status": "not_ready", "error": type(exc).__name__, "paid_calls": 0, "execution_started": False}
        doctor_ready = doctor_report.get("status") == "ready"
        after = _snapshot_paths(watched)
        preserved = before == after
        markdown_completed = sorted(task_id for task_id, item in task_bindings.items() if item["status"] == "completed")
        execution_admitted = bool(identities_independent and publisher["bound"] and tasks_match_publisher
                                  and launcher_birth and daemon_birth and bounded["active"] and preserved
                                  and worktree_error is None)
        return {
            "schema": "complaint-new-campaign-startup-observation@1",
            "identities_independent": identities_independent,
            "identity_scopes": {name: str(path) for name, path in locations.items()},
            "worktree_identity": worktree_identity,
            "worktree_error": worktree_error,
            "binding": binding,
            "publisher": publisher,
            "publisher_bound": bool(publisher["bound"] and tasks_match_publisher),
            "task_bindings": task_bindings,
            "task_cids": task_cids,
            "identity_error": identity_error,
            "plan_bound": bool(plan_bound),
            "source_generation_bound": bool(generation_bound),
            "ingestion_is_execution": False,
            "tasks_completed_by_ingestion": 0,
            "pid_alive": pid_alive,
            "pid_alive_is_execution": False,
            "launcher_birth": launcher_birth,
            "daemon_birth": daemon_birth,
            "doctor_ready": doctor_ready,
            "doctor_ready_is_execution": False,
            "doctor_status": doctor_report.get("status"),
            "paid_calls": 0,
            "bounded_work": bounded,
            "execution_admitted": execution_admitted,
            "markdown_completed_task_ids": markdown_completed,
            "markdown_status_grants_execution": False,
            "historical_and_budget_unchanged": preserved,
            "completion_authority": False,
        }
    finally:
        os.chdir(started)



def _attempt_budget_block(native_state: Mapping[str, Any], board: Mapping[str, Any]) -> dict[str, Any] | None:
    """Report Native's exhausted ready set without changing retry accounting."""
    reason = "all_selectable_ready_tasks_reached_max_task_attempts"
    ready = board.get("ready_task_ids")
    if (native_state.get("selection_idle_reason") != reason
            or native_state.get("selectable_ready_task_ids") != []
            or not isinstance(ready, list) or not ready
            or any(type(task_id) is not str for task_id in ready)
            or native_state.get("ready_task_ids") != ready):
        return None
    attempts = native_state.get("implementation_attempts")
    by_cid = native_state.get("implementation_attempts_by_cid")
    identities = native_state.get("task_identities")
    if not all(isinstance(value, Mapping) for value in (attempts, by_cid, identities)):
        return None
    counts = {}
    for task_id in ready:
        identity = identities.get(task_id)
        cid = identity.get("canonical_task_cid") if isinstance(identity, Mapping) else None
        count = by_cid.get(cid) if isinstance(cid, str) and cid else None
        if type(count) is not int or count < 3 or attempts.get(task_id) != count:
            return None
        counts[task_id] = count
    return {"reason": reason, "max_task_attempts": 3, "task_ids": list(ready),
            "attempts": counts, "completion_authority": False}


def status(repo_root: Path, spec_path: Path, state_dir: Path) -> dict[str, Any]:
    record = _read_json(state_dir / "launcher.json")
    owned = owns_process(record)
    identity = record.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    state_path = state_dir / f"{STATE_PREFIX}_task_state.json"
    heartbeat_path = state_dir / f"{STATE_PREFIX}_supervisor_status.json"
    strategy_path = state_dir / f"{STATE_PREFIX}_strategy.json"
    events_path = state_dir / f"{STATE_PREFIX}_events.jsonl"
    supervisor_events = state_dir / f"{STATE_PREFIX}_supervisor_events.jsonl"
    native_state, state_source = _read_native_state(repo_root, state_path)
    heartbeat, strategy = (_read_json(path) for path in (heartbeat_path, strategy_path))
    now = time.time()
    heartbeat_age = _age(heartbeat_path, now)
    try:
        spec, artifacts = _campaign_spec(repo_root, spec_path)
        board = _validate_board(repo_root, repo_root / artifacts.board_relative, spec)
    except Exception as exc:
        board = {"read_error": str(exc), "count": 0, "completed": 0, "ready_task_ids": [], "manual_hold_task_ids": []}
    # Native selection sets active_task_id before an attempt or worker exists.
    # Only the execution flag identifies an active implementation/validation.
    active = bool(native_state.get("implementation_in_progress"))
    # Native clears these current execution/selection fields on settlement.
    # Inspect the raw row: stale timestamps must not hide an unfinished claim.
    # Lane owner births and last_implementation_* survive legitimate settlement.
    native_execution_unsettled = any(native_state.get(key) for key in (
        "implementation_in_progress", "active_task_id", "active_task_key", "active_task_cid",
        "active_task_title", "active_task_track", "active_task_started_at", "active_attempt",
        "active_phase", "active_phase_started_at", "active_phase_detail", "active_log_path",
        "active_worktree_path", "active_branch", "active_provider_runner",
    ))
    try:
        since_start = max(0.0, now - float(record.get("started_at", now)))
    except (TypeError, ValueError):
        since_start = 0.0
    phase = str(native_state.get("active_phase", "")).lower()
    intentional_wait = phase in _INTERVIEW_PHASES or bool(native_state.get("manual_hold") or native_state.get("manual_cancellation"))
    if state_source["source"] == "native_control_plane":
        row_ages = [age for key in ("heartbeat_at", "last_progress_at")
                    if (age := _timestamp_age(native_state.get(key), now)) is not None]
        state_age = min(row_ages) if row_ages else None
    else:
        state_age = _age(state_path, now)
    current_state = state_age is not None and state_age <= since_start
    active = active and current_state
    selected = current_state and bool(native_state.get("active_task_id")) and not active
    progress_paths = [events_path, supervisor_events]
    # A previous attempt's log is historical evidence, never this claim's
    # progress clock. Observe only a current execution's explicitly active log.
    log_name = native_state.get("active_log_path") if active else None
    if isinstance(log_name, str) and log_name:
        candidate = Path(log_name)
        if candidate.resolve().is_relative_to(state_dir.resolve()):
            progress_paths.append(candidate)
    ages = [age for path in progress_paths if (age := _age(path, now)) is not None]
    progress_age = min(ages) if ages else None
    # A previous run's task claim is never evidence this launch made progress.
    if heartbeat_age is not None and heartbeat_age > since_start:
        heartbeat_age = None
    active_age = _age(progress_paths[-1], now) if log_name and len(progress_paths) > 2 else None
    attempt_age = _timestamp_age(native_state.get("active_task_started_at"), now)
    if active_age is None:
        active_age = attempt_age
    heartbeat_status = str(heartbeat.get("status", ""))
    heartbeat_owner = heartbeat.get("supervisor_pid")
    daemon_identity = process_identity(heartbeat.get("daemon_pid"))
    daemon_alive = bool(daemon_identity and daemon_identity.get("ppid") == identity.get("pid"))
    startup_maintenance = (
        heartbeat_status in {"agentic_maintenance_started", "agentic_maintenance_completed"}
        and since_start <= STARTUP_SECONDS and not heartbeat.get("daemon_pid")
        and not heartbeat.get("last_agentic_maintenance_error")
    )
    from .startup_maintenance_activity import observe as observe_startup_maintenance
    startup_activity = (observe_startup_maintenance(sys.modules[__name__], repo_root, spec_path, state_dir,
        record, heartbeat, native_state, now_ts=now) if owned else None)
    maintenance_ready = False
    if heartbeat_status in {"agentic_maintenance_started", "agentic_maintenance_completed"} and daemon_alive:
        from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_activity import observe_supervisor_activity
        maintenance_ready = observe_supervisor_activity(
            heartbeat, now=datetime.fromtimestamp(now, timezone.utc), heartbeat_max_age_seconds=120,
        ).phase_ready
    last_started_age = _timestamp_age(native_state.get("last_implementation_started_at"), now)
    claim_verified = owned and current_state and bool(native_state.get("active_task_id") or
        (last_started_age is not None and last_started_age <= since_start))
    binding = _attempt_binding(native_state)
    invocation_start = now - since_start
    provider_evidence = _provider_event_evidence(
        events_path, task_id=binding["task_id"], started_at=invocation_start, binding=binding,
    ) if claim_verified else None
    if claim_verified:
        log_evidence = _owned_attempt_log_evidence(events_path, state_dir, binding, started_at=invocation_start, now=now)
        provider_evidence = log_evidence or provider_evidence
    provider_progress = bool(provider_evidence and provider_evidence.get("progress_fresh", True))
    rescue_activity = None
    rescue_active = False
    if owned and current_state and claim_verified and phase == "validating":
        from .auto_rescue_activity import observe as observe_rescue_activity
        rescue_activity = observe_rescue_activity(sys.modules[__name__], repo_root, state_dir, native_state, now_ts=now)
        rescue_active = rescue_activity.get("activity_verified") is True
        # Native's original terminal log and an integer repair PID alone do
        # not prove a current repair. Thought/text are liveness only: they
        # never become verified work or reset a recovery incident budget.
        provider_progress = rescue_active and rescue_activity.get("work_progress_verified") is True
        if rescue_active:
            provider_evidence = {**rescue_activity, "type": "grok_frame",
                "provider_repair_in_flight": True, "provider_terminal_observed": False,
                "progress_fresh": provider_progress}
        elif provider_evidence:
            provider_evidence = {**provider_evidence, "provider_repair_in_flight": False, "progress_fresh": False}
    validation_evidence = _validation_event_evidence(events_path, binding, started_at=invocation_start) if claim_verified else None
    from .reconciliation_activity import evidence as owned_executor_activity_evidence
    canonical_activity_evidence = (owned_executor_activity_evidence(sys.modules[__name__], repo_root, state_dir,
        record, native_state, now_ts=now) if owned and current_state else None)
    if canonical_activity_evidence is not None:
        validation_evidence = canonical_activity_evidence
    worker_liveness = _owner_liveness(native_state.get("owner_process_birth"))
    if canonical_activity_evidence is not None or startup_activity is not None:
        worker_liveness = "alive"  # Exact live maintenance birth, re-proved above.
    if worker_liveness == "missing":
        worker_liveness = "alive" if daemon_alive else ("absent" if not owned else "unknown")
    shutdown = _read_json(state_dir / "container_shutdown.json")
    full_launch = record.get("schema_version") == "complaint-improvement-launcher@1"
    try:
        selected_root, root_binding = recorded_worktree_root(record, state_dir)
        worktree_error = None
    except (OSError, ValueError, TypeError) as error:
        selected_root, root_binding, worktree_error = None, None, str(error)
    shutdown_verified = _shutdown_verified(record, shutdown, repo_root, state_dir) and worktree_error is None
    from .retry_cooldown_activity import observe as observe_retry_cooldown
    retry_cooldown = (observe_retry_cooldown(sys.modules[__name__], repo_root, state_dir,
        record, native_state, heartbeat, board, spec=spec, artifacts=artifacts,
        current_state=current_state, now_ts=now)
        if owned and current_state and not board.get("read_error")
        and not provider_progress and not validation_evidence else {"verified": False})
    attempt_budget = (_attempt_budget_block(native_state, board)
        if owned and current_state and not native_execution_unsettled and not intentional_wait else None)
    if not owned:
        if identity and process_identity(identity.get("pid")):
            health = "identity_mismatch"
        else:
            health = "stop_incomplete" if full_launch and not shutdown_verified else "stopped"
    elif board.get("read_error"):
        health = "board_error"
    elif native_state.get("read_error") or heartbeat.get("read_error"):
        health = "state_error"
    elif heartbeat_age is not None and heartbeat_owner != identity.get("pid"):
        health = "heartbeat_identity_mismatch"
    elif heartbeat_age is not None and heartbeat_age > 120:
        health = "stalled"
    elif retry_cooldown.get("verified") is True:
        health = "retry_cooldown"
    elif (board["count"] and board["completed"] == board["count"]
            and not native_execution_unsettled and canonical_activity_evidence is None
            and not rescue_active and startup_activity is None):
        health = "complete"
    elif canonical_activity_evidence is not None:
        # The exact canonical executor has its existing fixed validation
        # deadline. Its pulse/finalization proof never renews the provider.
        health = "active"
    elif rescue_active:
        # Selection can precede checkout. The exact owned repair has already
        # proved its unique execution-event deadline and unchanged phase cap.
        health = "active"
    elif active and attempt_age is not None and attempt_age > TIMEOUT_SECONDS:
        health = "stalled"
    elif attempt_budget is not None and since_start > STARTUP_SECONDS:
        # Repeated bounded maintenance and backpressure events cannot turn
        # exhausted ready tasks into healthy work. Actual validation/rescue
        # above retains its existing deadline; no paid attempt is rearmed.
        health = "budget_exhausted"
    elif startup_activity is not None:
        health = "maintenance"  # Liveness only, within Native's fixed window/handoff.
    elif heartbeat_age is not None and startup_maintenance:
        health = "starting"
    elif heartbeat_age is not None and maintenance_ready:
        health = "active" if active else "maintenance"
    elif heartbeat_age is not None and heartbeat_status not in {"running", "starting", "restarting", "recycling"}:
        health = "daemon_failed"
    elif heartbeat_age is not None and heartbeat_status == "running" and (heartbeat.get("daemon_pid_alive") is False or not daemon_alive):
        health = "daemon_failed"
    elif intentional_wait and current_state:
        health = "waiting_for_user"
    elif not board["ready_task_ids"] and not active and board["manual_hold_task_ids"]:
        health = "waiting_for_user"
    elif heartbeat_age is None and since_start <= STARTUP_SECONDS:
        health = "starting"
    elif heartbeat_age is None or heartbeat_age > TIMEOUT_SECONDS + 30:
        health = "stalled"
    elif heartbeat_owner != identity.get("pid"):
        health = "heartbeat_identity_mismatch"
    elif heartbeat_status in {"starting", "restarting", "recycling"}:
        health = heartbeat_status
    elif heartbeat_status != "running" or heartbeat.get("daemon_pid_alive") is False or not daemon_alive:
        health = "daemon_failed"
    elif heartbeat_age > 120:
        health = "stalled"
    elif active:
        hard_expired = attempt_age is not None and attempt_age > TIMEOUT_SECONDS
        log_stale = active_age is not None and active_age > STALL_SECONDS
        silent_window = attempt_age is not None and attempt_age > STALL_SECONDS
        in_validation = phase.startswith("valid")
        provider_repair = rescue_active
        # Fresh generic log lines and a live PID are not provider or validation progress.
        silent = silent_window and (not (validation_evidence or provider_repair) if in_validation else not provider_progress)
        post_provider = bool(not in_validation and provider_evidence and provider_evidence.get("provider_terminal_observed"))
        health = ("stalled" if hard_expired or log_stale else "post_provider" if post_provider
                  else "stalled" if silent else "active")
    elif selected:
        health = "no_progress" if (attempt_age if attempt_age is not None else since_start) > STALL_SECONDS else "selected"
    elif not current_state and since_start > STARTUP_SECONDS:
        # Supervisor heartbeats and watchdog events prove liveness only. An
        # early native deferral can otherwise look healthy indefinitely while
        # it leaves the task-state row untouched from the previous launch.
        health = "no_progress"
    elif current_state and native_state.get("blocked_task_ids") and not native_state.get("selectable_ready_task_ids"):
        health = "blocked"
    elif not board["ready_task_ids"]:
        health = "blocked"
    elif progress_age is not None and progress_age > STALL_SECONDS:
        health = "no_progress"
    else:
        health = "running"
    if worktree_error is not None:
        health = "identity_mismatch" if owned else "stop_incomplete"
    keys = ("heartbeat_at", "last_progress_at", "active_task_id", "active_task_cid", "active_task_started_at", "active_phase", "active_phase_detail",
            "implementation_in_progress", "active_attempt", "active_worktree_path", "active_log_path", "owner_process_birth",
            "last_implementation_returncode", "implementation_attempts", "implementation_attempts_by_cid",
            "recommended_task_id", "ready_task_ids", "selectable_ready_task_ids", "blocked_task_ids", "selection_idle_reason",
            "manual_hold", "manual_cancellation", "capacity_quarantine", "protected_incident", "dependency_status",
            "claim_task_cid", "claim_attempt", "proof_task_cid", "proof_stale", "stale_proof")
    interview_state = None
    if phase in {"waiting_for_user", "waiting_user", "awaiting_user"}:
        interview_state = "awaiting_user"
    elif phase == "manual_hold" or native_state.get("manual_hold") or (not active and board.get("manual_hold_task_ids")):
        interview_state = "manual_hold"
    elif phase == "paused":
        interview_state = "paused"
    elif phase in {"cancelled", "canceled"} or native_state.get("manual_cancellation"):
        interview_state = "cancelled"
    heartbeat_fresh = heartbeat_age is not None and heartbeat_age <= 120
    provider_terminal = bool(provider_evidence and provider_evidence.get("provider_terminal_observed"))
    scope_liveness = _campaign_scope_liveness(
        native_state, phase=phase, interview_state=interview_state, worker_liveness=worker_liveness,
        active=active, attempt_age=attempt_age, active_age=active_age, heartbeat_fresh=heartbeat_fresh,
        provider_fresh=bool(provider_progress or rescue_active), provider_terminal=provider_terminal,
        validation_fresh=bool(validation_evidence), now=now, provider_repair=rescue_active,
        canonical_validation_active=canonical_activity_evidence is not None,
    )
    identity_ok = worker_liveness == "alive" and health not in {"identity_mismatch", "heartbeat_identity_mismatch", "state_error"}
    activity_ok = (not active) or bool(provider_progress or validation_evidence or rescue_active
        or (not phase.startswith("valid") and provider_evidence and provider_evidence.get("provider_terminal_observed"))) or not (
        attempt_age is not None and attempt_age > STALL_SECONDS
    )
    healthy = bool(identity_ok and heartbeat_fresh and activity_ok and health in {
        "active", "post_provider", "running", "maintenance", "waiting_for_user", "selected", "complete", "retry_cooldown",
    })
    return {"status": health, "healthy": healthy, "owned_process_alive": owned,
            "attempt_budget": attempt_budget,
            "worker_liveness": worker_liveness,
            "scope_liveness": {key: scope_liveness[key] for key in ("claim", "worker", "provider", "validation", "merge")},
            "scope_monitors": scope_liveness["monitors"],
            "application_interview_state": interview_state,
            "pid": identity.get("pid"), "state_dir": str(state_dir),
            "worktree_root": str(selected_root) if selected_root is not None else None,
            "worktree_root_binding": root_binding, "worktree_root_error": worktree_error,
            "provider": "grok_cli", "model": MODEL, "allow_fallback": False,
            "native_heartbeat_age_seconds": heartbeat_age, "observed_activity_age_seconds": progress_age,
            "native_read_errors": {key: value.get("read_error") for key, value in
                                   (("launcher", record), ("state", native_state), ("heartbeat", heartbeat), ("strategy", strategy))
                                   if value.get("read_error")},
            "native_state": {key: native_state[key] for key in keys if key in native_state},
            "native_state_source": state_source,
            "container_shutdown_verified": shutdown_verified,
            "container_shutdown": {key: shutdown[key] for key in ("status", "quiesced", "reason") if key in shutdown},
            "native_heartbeat": {key: heartbeat[key] for key in ("status", "updated_at", "supervisor_pid", "daemon_pid", "supervisor_pid_alive", "daemon_pid_alive", "restart_count", "last_recycle_reason", "last_exit_code", "worker_phase", "worker_phase_age_seconds", "last_agentic_maintenance_phase", "supervisor_maintenance") if key in heartbeat},
            "native_strategy": {key: strategy[key] for key in ("blocked_tasks", "deprioritized_tasks", "focus_tracks") if key in strategy},
            "board": board, "events_tail": _tail(events_path), "supervisor_events_tail": _tail(supervisor_events),
            "launcher_log_tail": _tail(state_dir / "launcher.log"),
            "claim_progress_verified": claim_verified,
            "runner_progress_verified": bool(claim_verified and heartbeat_fresh and worker_liveness == "alive"),
            "provider_execution_verified": bool(owned and provider_evidence),
            "provider_progress_verified": bool(owned and provider_progress),
            "provider_execution_evidence": provider_evidence,
            "auto_rescue_activity_verified": rescue_active,
            "auto_rescue_activity_evidence": rescue_activity,
            "retry_cooldown_verified": health == "retry_cooldown" and retry_cooldown.get("verified") is True,
            "retry_cooldown_evidence": retry_cooldown,
            "startup_activity_verified": startup_activity is not None,
            "startup_activity_evidence": startup_activity,
            "validation_activity_verified": bool(owned and validation_evidence),
            "validation_activity_evidence": validation_evidence,
            "progress_verified": bool(owned and (provider_progress or canonical_activity_evidence)),
            "completion_authority": False}


def _refusal(reason: str, observed: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    """Recovery refusal keeps counters, evidence and holds exactly as observed."""
    return {"recovery": "blocked", "eligible": False, "reconciled": False, "reason": reason,
            "status": observed.get("status"), "healthy": observed.get("healthy"),
            "worker_liveness": observed.get("worker_liveness"),
            "application_interview_state": observed.get("application_interview_state"),
            "diagnostics": extra.get("diagnostics") or [reason],
            "observed_attempts": (observed.get("native_state") or {}).get("implementation_attempts"),
            "observed_attempts_by_cid": (observed.get("native_state") or {}).get("implementation_attempts_by_cid"),
            "selection_performed": False, "paid_dispatch": False, "attempt_refunded": False,
            "completion_authority": False, "counters_preserved": True, "progress_preserved": True,
            "manual_holds_preserved": True, "provider_execution_evidence": observed.get("provider_execution_evidence"),
            "validation_activity_evidence": observed.get("validation_activity_evidence"),
            **{key: value for key, value in extra.items() if key != "diagnostics"}}


def _arm_cooldown(state_dir: Path, reason: str, observed: Mapping[str, Any], *, now: float, scope: str,
                  diagnostics: list[Any] | None = None) -> dict[str, Any]:
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_runtime import RestartPolicy
    path = state_dir / _COOLDOWN_NAME
    previous = _read_json(path)
    if previous.get("until") and float(previous.get("until") or 0) > now and previous.get("reason") == reason:
        return _refusal(reason, observed, recovery="cooldown", cooldown_until=previous["until"],
                        cooldown_seconds=previous.get("cooldown_seconds"), cooldown_scope=scope,
                        diagnostics=list(previous.get("diagnostics") or [reason]),
                        spinning_prevented=True)
    policy = RestartPolicy()
    try:
        object.__setattr__(policy, "_consecutive_failures", int(previous.get("attempts") or 0))
    except (TypeError, ValueError):
        object.__setattr__(policy, "_consecutive_failures", 0)
    delay = min(policy.delay_for_status("blocked"), policy.max_backoff_seconds)
    diagnostics = [reason, f"cooldown_seconds={delay}", f"scope={scope}",
                   "progress_and_attempt_counters_retained", *(diagnostics or [])]
    payload = {"reason": reason, "scope": scope, "attempts": int(policy._consecutive_failures),
               "cooldown_seconds": delay, "until": now + delay, "diagnostics": diagnostics,
               "progress_preserved": True, "attempt_refunded": False, "completion_authority": False}
    _atomic_json(path, payload)
    return _refusal(reason, observed, recovery="cooldown", cooldown_until=payload["until"],
                    cooldown_seconds=delay, cooldown_scope=scope, diagnostics=diagnostics,
                    spinning_prevented=True)


def _fence_owned_tree(record: Mapping[str, Any]) -> dict[str, Any]:
    """Observe closure only; a recovery request never signals a live parent."""
    identity = record.get("identity")
    if not isinstance(identity, dict) or _owner_liveness(identity) != "dead":
        return {"fenced": False, "signalled": False, "remaining_pids": [], "reason": "launcher_not_dead"}
    return {"fenced": True, "signalled": False, "remaining_pids": []}


def _recovery_config(repo_root: Path, state_dir: Path, record: Mapping[str, Any]):
    """Derive the native paths/options from the first-party compiler only."""
    supervisor, _ = _native_modules(repo_root)
    selected_root, _ = recorded_worktree_root(record, state_dir)
    spec = _native_campaign_spec(repo_root, state_dir, todo_path=record["board_path"])
    artifacts = campaign_artifacts(spec)
    args = native_argv(Path(record["board_path"]), state_dir, record["merge_target"], worktree_root=selected_root,
                       board_namespace=artifacts.board_namespace, protected_paths=artifacts.protected_paths)
    return supervisor.supervisor_config_from_args(supervisor.parse_args(args), repo_root=repo_root)


def _open_recovery_daemon(repo_root: Path, state_dir: Path, record: Mapping[str, Any], *, merge_queue=None,
                          common_checkout_owner: bool = False):
    """Native quiesced reconciliation has no implementation/selection authority."""
    _, native = _native_modules(repo_root)
    config = _recovery_config(repo_root, state_dir, record)
    return native.PortalImplementationDaemon(
        todo_path=config.todo_path, state_path=config.state_path, strategy_path=config.strategy_path,
        events_path=state_dir / f"{STATE_PREFIX}_events.jsonl", repo_root=repo_root,
        task_header_prefix=config.task_prefix,
        # Native supervisor recovery owns the common checkout journal; the
        # remaining Host recovery keeps its separate board-scoped lease.
        board_namespace="" if common_checkout_owner else config.board_namespace, implement=False,
        implementation_command=config.implementation_command,
        implementation_timeout=config.implementation_timeout, max_task_attempts=config.max_task_attempts,
        use_ephemeral_worktree=False, worktree_root=config.worktree_root,
        merge_target_branch=config.merge_target_branch, merge_queue_dir=config.merge_queue_dir,
        merge_queue=merge_queue, worktree_submodule_paths=config.worktree_submodule_paths,
        implementation_protected_paths=config.implementation_protected_paths,
        objective_path=config.objective_path, objective_bundle_dir=config.objective_bundle_dir,
        generated_status_paths=config.generated_dirty_repair_paths,
        llm_merge_resolver_command=config.llm_merge_resolver_command,
        llm_merge_resolver_timeout_seconds=config.llm_merge_resolver_timeout_seconds,
        task_shard_count=config.task_shard_count, task_shard_index=config.task_shard_index,
        strict_task_sharding=config.strict_task_sharding,
    )


@contextmanager
def _recovery_checkout_lease(repo_root: Path, *, board_namespace: str = "complaint-intake-improvement"):
    # Exclude merges/checkout mutation, while leaving the protected-path
    # reconciler free to acquire and revalidate its own crash-fence lease.
    from ipfs_accelerate_py.agent_supervisor.merge import checkout_lock as locks
    if re.fullmatch(r"[a-z][a-z0-9-]{0,63}", board_namespace) is None:
        raise ValueError("recovery board namespace is not canonical")
    path = locks.board_scoped_checkout_mutation_lock_path(repo_root, board_namespace)
    metadata = locks.checkout_lock_metadata(kind="merge", repo_root=repo_root,
        owner_script="", extra={"lease_id": secrets.token_hex(16), "operation": "quiesced_stalled_worker_reconciliation"})
    lease, _, _, _ = locks.acquire_checkout_mutation_lease(path, metadata, owner_active=lambda _: True)
    if lease is None:
        raise BlockingIOError("native checkout mutation owner is present")
    try:
        yield lease
    finally:
        if not locks.release_checkout_mutation_lease(lease, require_exact_metadata=True):
            raise RuntimeError("native recovery checkout lease changed; retained")


def _recovery_preimage(repo_root: Path, state_dir: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    from .improvement_recovery import _owned_bytes
    files = [state_dir / name for name in ("launcher.json", "container_shutdown.json",
        f"{STATE_PREFIX}_supervisor_status.json", f"{STATE_PREFIX}_task_state.json",
        f"{STATE_PREFIX}_strategy.json", f"{STATE_PREFIX}_events.jsonl")]
    files += [Path(record["board_path"]), Path(record["spec_path"])]
    result = {}
    for path in files:
        # Current native state is a control-plane row; a JSON mirror is optional.
        if path.name == f"{STATE_PREFIX}_task_state.json" and not os.path.lexists(path):
            result[str(path)] = None
            continue
        if path.resolve(strict=True) != path:
            raise ValueError("recovery evidence path is aliased")
        raw = _owned_bytes(path, MAX_EVENT_HISTORY_BYTES if path == state_dir / f"{STATE_PREFIX}_events.jsonl" else 32 * 1024 * 1024, legacy_group_write=True)
        info = path.lstat()
        result[str(path)] = (info.st_dev, info.st_ino, info.st_mode, hashlib.sha256(raw).hexdigest())
    payload, source = _read_native_state(repo_root, state_dir / f"{STATE_PREFIX}_task_state.json")
    if payload.get("read_error") or source.get("source") == "unavailable":
        raise ValueError("native recovery state observation unavailable")
    result["native_payload"] = payload
    result["native_source"] = source
    authority = source.get("authority_path")
    if authority:
        path = Path(authority)
        if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_relative_to(state_dir):
            raise ValueError("native state authority is outside this epoch")
        raw = _owned_bytes(path, 128 * 1024 * 1024, legacy_group_write=True)
        info = path.lstat()
        result["native_authority"] = (str(path), info.st_dev, info.st_ino, info.st_mode,
                                      hashlib.sha256(raw).hexdigest())
    return result


def _claim_proof_conflict(native_state: Mapping[str, Any]) -> str | None:
    claim_cid = native_state.get("claim_task_cid") or native_state.get("proof_task_cid")
    active_cid = native_state.get("active_task_cid")
    if claim_cid and active_cid and claim_cid != active_cid:
        return "stale_cid"
    claim_attempt = native_state.get("claim_attempt")
    active_attempt = native_state.get("active_attempt")
    if claim_attempt not in (None, "") and active_attempt not in (None, "", 0) and claim_attempt != active_attempt:
        return "stale_attempt_proof"
    if native_state.get("proof_stale") or native_state.get("stale_proof"):
        return "stale_proof"
    return None


def _settle_obsolete_checkout_journal(daemon, state_dir: Path, lease,
                                      preimage: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Settle Native metadata before holding the queue's separate writer FD.

    The typed owner API reads completed queue requests. Holding the external
    writer guard during that read would lock this process against itself.
    Only its one proved settlement event may refresh recovery evidence.
    """
    from .improvement_recovery import _owned_bytes
    from ipfs_accelerate_py.agent_supervisor.proof.formal_verification_contracts import content_identity
    from ipfs_accelerate_py.agent_supervisor.runtime.event_log import _event_identity, _event_stream_binding
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import read_checkout_mutation_lease
    event_path = state_dir / f"{STATE_PREFIX}_events.jsonl"
    if _recovery_preimage(daemon.repo_root, state_dir, _read_json(state_dir / "launcher.json")) != preimage:
        raise ValueError("native_completion_journal_settlement_preimage_changed")
    events_before = _owned_bytes(event_path, MAX_EVENT_HISTORY_BYTES, legacy_group_write=True)
    if hashlib.sha256(events_before).hexdigest() != preimage[str(event_path)][3]:
        raise ValueError("native_completion_journal_settlement_event_preimage_changed")
    journal_before = _owned_bytes(lease.lock_path, 32 * 1024 * 1024, legacy_group_write=True)
    if read_checkout_mutation_lease(lease.lock_path) != lease:
        raise ValueError("native_completion_journal_settlement_lease_changed")
    result = daemon.reconcile_obsolete_protected_completion_journal()
    if (result.get("checkout_mutation_lease_recovered") is not True
            or result.get("reason") != "obsolete_completion_journal_settled"
            or any(result.get(key) is not False for key in ("completion_authority", "attempt_refunded", "old_guard_trusted"))):
        raise ValueError("native_completion_journal_settlement_required")
    archive_path = Path(str(result.get("settlement_path") or ""))
    if (not archive_path.is_absolute() or archive_path.resolve(strict=True) != archive_path
            or archive_path.parent != state_dir / "protected-checkout-settlements"):
        raise ValueError("native_completion_journal_settlement_path_changed")
    archive = json.loads(_owned_bytes(archive_path, 64 * 1024 * 1024))
    if not isinstance(archive, dict) or not isinstance(archive.get("proof"), dict):
        raise ValueError("native_completion_journal_settlement_archive_invalid")
    proof = archive.get("proof") or {}
    if (archive.get("retired") is not True or archive.get("settlement_id") != result.get("settlement_id")
            or content_identity(proof) != result.get("settlement_id")
            or proof.get("old_lease_id") != lease.lease_id
            or proof.get("old_lease_device") != lease.device or proof.get("old_lease_inode") != lease.inode
            or proof.get("old_journal") != dict(lease.metadata)
            or proof.get("old_journal_raw_hex") != journal_before.hex()
            or proof.get("completion_authority") is not False or proof.get("attempt_refunded") is not False
            or os.path.lexists(lease.lock_path)):
        raise ValueError("native_completion_journal_settlement_proof_changed")
    events_after = _owned_bytes(event_path, MAX_EVENT_HISTORY_BYTES, legacy_group_write=True)
    appended = events_after[len(events_before):].splitlines() if events_after.startswith(events_before) else []
    event = json.loads(appended[0]) if len(appended) == 1 else {}
    previous = json.loads(events_before.splitlines()[-1]) if events_before.strip() else {}
    stream, snapshot = _event_stream_binding(event_path)
    if (not isinstance(event, dict) or not isinstance(previous, dict)
            or type(previous.get("sequence", 0)) is not int
            or event.get("type") != "obsolete_completion_journal_settled"
            or not event.get("timestamp") or any(event.get(key) != value for key, value in result.items())
            or type(event.get("sequence")) is not int or event["sequence"] != previous.get("sequence", 0) + 1
            or event.get("previous_event_id") != previous.get("event_id", "")
            or event.get("stream_id") != stream or event.get("snapshot_id") != snapshot
            or event.get("event_id") != _event_identity(event)):
        raise ValueError("native_completion_journal_settlement_event_changed")
    current = _recovery_preimage(daemon.repo_root, state_dir, _read_json(state_dir / "launcher.json"))
    old_events = preimage[str(event_path)]
    if (current[str(event_path)][:3] != old_events[:3]
            or {key: value for key, value in current.items() if key != str(event_path)}
            != {key: value for key, value in preimage.items() if key != str(event_path)}):
        raise ValueError("native_completion_journal_settlement_changed_recovery_evidence")
    return result, current


def _recover_stalled_worker(repo_root: Path, spec_path: Path, state_dir: Path, *, now: float | None = None,
                            expected_launcher_sha256: str | None = None) -> dict[str, Any]:
    """Fence a proven-dead ordinary attempt and reconcile it through native APIs.

    A live PID, stale heartbeat, or missing birth is not permission to refund an
    attempt, reset a cap, release quarantine, fabricate an interview answer, or
    dispatch another paid provider call. Lock contention and a temporarily
    unavailable dependency wait on a capped cooldown.
    """
    admission = _recovery_start_admission(state_dir, expected_launcher_sha256)
    if admission:
        return _refusal(admission, {})
    observed = status(repo_root, spec_path, state_dir)
    moment = time.time() if now is None else now
    native_state = observed.get("native_state") if isinstance(observed.get("native_state"), dict) else {}
    errors = observed.get("native_read_errors") or {}
    if errors:
        if any(str(value) in {"native_state_read_timeout", "BlockingIOError", "TimeoutError"} for value in errors.values()):
            return _arm_cooldown(state_dir, "lock_contention", observed, now=moment, scope="runner")
        return _refusal("observation_error", observed, diagnostics=[f"{key}:{value}" for key, value in errors.items()])
    interview = observed.get("application_interview_state")
    if interview:
        return _refusal(f"interview_or_manual_{interview}", observed)
    if native_state.get("manual_hold") or native_state.get("manual_cancellation"):
        return _refusal("manual_hold", observed)
    if native_state.get("capacity_quarantine") or str(native_state.get("active_phase") or "").lower() == "capacity_quarantine":
        return _refusal("capacity_quarantine", observed)
    if native_state.get("protected_incident") or str(native_state.get("active_phase") or "").lower() == "protected_incident":
        return _refusal("protected_incident", observed)
    conflict = _claim_proof_conflict(native_state)
    if conflict:
        return _refusal(conflict, observed)
    dependency = str(native_state.get("dependency_status") or "").lower()
    if dependency in {"unavailable", "temporary_unavailable", "degraded"}:
        return _arm_cooldown(state_dir, "dependency_unavailable", observed, now=moment, scope="runner")
    liveness = _owner_liveness(native_state.get("owner_process_birth"))
    if liveness == "missing":
        liveness = observed.get("worker_liveness") or "missing"
    phase = str(native_state.get("active_phase") or "").lower()
    active = bool(native_state.get("implementation_in_progress"))
    if liveness in {"alive", "pid_reuse", "unknown"}:
        if liveness != "alive":
            return _refusal(liveness, observed)
        if observed.get("status") in {"stalled", "no_progress", "daemon_failed"}:
            scope = "validation" if phase.startswith("valid") else "provider" if active else "runner"
            if phase.startswith("complet"):
                scope = "completion"
            reason = "validation_stall" if scope == "validation" else "silent_provider" if scope == "provider" else "log_or_heartbeat_stall"
            return _arm_cooldown(state_dir, reason, observed, now=moment, scope=scope)
        return _refusal("worker_alive", observed)
    record = _read_json(state_dir / "launcher.json")
    if liveness != "dead" and not (liveness in {"absent", "missing"}
            and not owns_process(record) and _full_launch_record(record)):
        return _refusal("unknown_owner", observed)
    try:
        # Only a stopped, full campaign can enter the operator seam. A dead
        # worker never grants authority over its still-live native supervisor.
        from .improvement_shutdown import _context, _parent_closed
        if not _campaign_tuple_matches(record, repo_root, spec_path, state_dir):
            return _refusal("campaign_binding_unverified", observed)
        context = _context(state_dir, record)
        if context is None:
            return _refusal("campaign_binding_unverified", observed)
        _parent_closed(state_dir, record, context, False)
        if _owner_liveness(record.get("identity")) != "dead":
            return _refusal("launcher_not_dead", observed)
        preimage = _recovery_preimage(repo_root, state_dir, record)
        with ExitStack() as stack:
            for name in ("recovery.lock", "launcher.lock", "runner.lock"):
                stack.enter_context(_lock(state_dir, name, blocking=False))
            admission = _recovery_start_admission(state_dir, expected_launcher_sha256)
            if admission:
                return _refusal(admission, observed)
            if _recovery_preimage(repo_root, state_dir, record) != preimage:
                return _refusal("recovery_preimage_changed", observed)
            _parent_closed(state_dir, record, context, False)
            _, recovery_artifacts = _campaign_spec(repo_root, spec_path)
            checkout_lease = stack.enter_context(_recovery_checkout_lease(repo_root,
                board_namespace=recovery_artifacts.board_namespace))
            # Even preparing an existing queue can touch its schema/import
            # projection. Prove current process/container closure first.
            _parent_closed(state_dir, record, context, False)
            fence = _fence_owned_tree(record)
            containers = _read_json(state_dir / "container_shutdown.json")
            selected_root, _ = recorded_worktree_root(record, state_dir)
            if (not fence["fenced"] or not _shutdown_verified(record, containers, repo_root, state_dir)
                    or not _observe_campaign_containers(repo_root, state_dir, selected_root, record, containers)):
                return _refusal("container_or_process_closure_unverified", observed)
            if _recovery_preimage(repo_root, state_dir, record) != preimage:
                return _refusal("recovery_preimage_changed", observed)
            from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import (
                MergeQueue, hold_merge_queue_settlement, read_merge_queue_settlement,
            )
            from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
            queue_args = {"target_repository_id": checkout_repository_id(repo_root),
                          "target_branch": record["merge_target"], "lock_timeout_seconds": 0.01}
            queue_before = read_merge_queue_settlement(state_dir / "merge-queue", **queue_args)
            if not queue_before.get("settled"):
                return _refusal("merge_queue_unsettled", observed)
            # MergeQueue opens its own store during construction. Construct the
            # genuine existing queue before retaining its writer guard, then
            # inject that same instance into the non-implementing reconciler.
            _parent_closed(state_dir, record, context, False)
            admission = _recovery_start_admission(state_dir, expected_launcher_sha256)
            if admission:
                return _refusal(admission, observed)
            queue_instance = MergeQueue(state_dir / "merge-queue")
            if read_merge_queue_settlement(state_dir / "merge-queue", **queue_args) != queue_before:
                return _refusal("merge_queue_changed_during_preparation", observed)
            from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import (
                checkout_mutation_lock_path, read_checkout_mutation_lease,
            )
            daemon = None
            checkout_settlement = None
            native_lease = read_checkout_mutation_lease(checkout_mutation_lock_path(repo_root))
            if (native_lease is not None and native_lease.metadata.get("protected_recovery_required") is True
                    and native_lease.metadata.get("protected_recovery_owner") == "implementation_daemon"
                    and native_lease.metadata.get("operation") == "mark_tasks_completed"):
                native_owner = _open_recovery_daemon(repo_root, state_dir, record, merge_queue=queue_instance,
                    common_checkout_owner=True)
                if native_owner._repo_merge_lock_path() != native_lease.lock_path:
                    return _refusal("native_completion_journal_owner_path_mismatch", observed)
                try:
                    checkout_settlement, preimage = _settle_obsolete_checkout_journal(
                        native_owner, state_dir, native_lease, preimage)
                except (OSError, ValueError, RuntimeError, TypeError) as error:
                    return _refusal("native_completion_journal_settlement_unverified", observed,
                        diagnostics=[str(error)[:500]], effects_uncertain=True,
                        counters_preserved=None, progress_preserved=None)
                _parent_closed(state_dir, record, context, False)
                admission = _recovery_start_admission(state_dir, expected_launcher_sha256)
                if admission:
                    return _refusal(admission, observed)
                containers = _read_json(state_dir / "container_shutdown.json")
                if (not _fence_owned_tree(record).get("fenced")
                        or not _shutdown_verified(record, containers, repo_root, state_dir)
                        or not _observe_campaign_containers(repo_root, state_dir, selected_root, record, containers)):
                    return _refusal("container_or_process_closure_unverified", observed)
                if read_merge_queue_settlement(state_dir / "merge-queue", **queue_args) != queue_before:
                    return _refusal("merge_queue_changed_during_checkout_settlement", observed)
            queue = stack.enter_context(hold_merge_queue_settlement(state_dir / "merge-queue",
                target_repository_id=checkout_repository_id(repo_root), target_branch=record["merge_target"],
                lock_timeout_seconds=0.01))
            if not queue.get("settled"):
                return _refusal("merge_queue_unsettled", observed)
            if queue != queue_before:
                return _refusal("merge_queue_changed_before_reconciliation", observed)
            _parent_closed(state_dir, record, context, False)
            fence = _fence_owned_tree(record)
            containers = _read_json(state_dir / "container_shutdown.json")
            selected_root, _ = recorded_worktree_root(record, state_dir)
            if (not fence["fenced"] or not _shutdown_verified(record, containers, repo_root, state_dir)
                    or not _observe_campaign_containers(repo_root, state_dir, selected_root, record, containers)):
                return _refusal("container_or_process_closure_unverified", observed)
            if _recovery_preimage(repo_root, state_dir, record) != preimage:
                return _refusal("recovery_preimage_changed", observed)
            fresh = status(repo_root, spec_path, state_dir)
            if (fresh.get("native_state") != observed.get("native_state")
                    or fresh.get("application_interview_state") or fresh.get("native_read_errors")
                    or _owner_liveness(fresh.get("native_state", {}).get("owner_process_birth")) not in {"dead", "missing"}):
                return _refusal("recovery_observation_changed", fresh)
            if _recovery_preimage(repo_root, state_dir, record) != preimage:
                return _refusal("recovery_preimage_changed", observed)
            _parent_closed(state_dir, record, context, False)
            admission = _recovery_start_admission(state_dir, expected_launcher_sha256)
            if admission:
                return _refusal(admission, observed)
            if daemon is None:
                daemon = _open_recovery_daemon(repo_root, state_dir, record, merge_queue=queue_instance)
            attempt_result = daemon.reconcile_quiesced_active_attempt()
            claim_result = None
            pending_claim_result = None
            completed_claim_result = None
            blocked = bool(attempt_result.get("blocked"))
            reason = str(attempt_result.get("reason") or "")
            terminal_claim_ok = (not blocked) or reason == "task_claim_reconciliation_blocked"
            unsafe = reason in {
                "implementation_worker_still_active", "implementation_lock_owner_still_active",
                "protected_path_reconciliation_blocked", "worktree_lifecycle_reconciliation_blocked",
                "implementation_lock_malformed",
            }
            if terminal_claim_ok and not unsafe:
                claim_result = daemon.reconcile_quiesced_implementation_task_claim()
            if (terminal_claim_ok and not unsafe and isinstance(claim_result, dict)
                    and claim_result.get("blocked") is True
                    and claim_result.get("reason") == "task_claim_worktree_lifecycle_missing"):
                from .completed_claim_recovery import completed_claim_daemon, reconcile_completed_claim
                from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import read_checkout_mutation_lease
                def completed_claim_closed():
                    _parent_closed(state_dir, record, context, False)
                    if read_checkout_mutation_lease(checkout_lease.lock_path) != checkout_lease:
                        raise ValueError("completed_claim_checkout_guard_changed")
                    current_containers = _read_json(state_dir / "container_shutdown.json")
                    if (not _fence_owned_tree(record).get("fenced")
                            or not _shutdown_verified(record, current_containers, repo_root, state_dir)
                            or not _observe_campaign_containers(repo_root, state_dir, selected_root,
                                record, current_containers)):
                        raise ValueError("completed_claim_process_or_container_closure_unverified")
                completed_claim_closed()
                daemon = completed_claim_daemon(_recovery_config(repo_root, state_dir, record),
                    merge_queue=queue_instance)
                completed_claim_result = reconcile_completed_claim(daemon, reprove_closure=completed_claim_closed)
                attempt_result = daemon.reconcile_quiesced_active_attempt()
                claim_result = daemon.reconcile_quiesced_implementation_task_claim()
                reason = str(attempt_result.get("reason") or "")
                completed_claim_closed()
            from .pending_claim_runtime import reconcile_pending_claim, unfinished_handoff_task
            unfinished = unfinished_handoff_task(state_dir)
            nonterminal_claim = (isinstance(claim_result, dict) and claim_result.get("blocked") is True
                and claim_result.get("reason") == "canonical_task_not_terminal")
            if terminal_claim_ok and not unsafe and (nonterminal_claim or unfinished):
                if unfinished and nonterminal_claim and unfinished != claim_result.get("task_id"):
                    raise ValueError("pending_candidate_handoff_conflicts_with_current_claim")
                _, native = _native_modules(repo_root)
                try:
                    pending_claim_result = reconcile_pending_claim(repo_root, spec_path, state_dir,
                        record, native, daemon, unfinished or str(claim_result.get("task_id") or ""))
                except ValueError as error:
                    if str(error) != "latest_exact_start_required":
                        raise
                    # Waiting cannot supply missing attempt provenance. Retain
                    # the claim refusal and run the accounting checks below;
                    # this classification grants no recovery or retry authority.
                    pending_claim_result = {"reconciled": False, "blocked": True,
                        "reason": "latest_exact_start_required", "completion_authority": False,
                        "attempt_refunded": False, "provider_callback_settled": False,
                        "new_attempt_authority": False}
                if pending_claim_result.get("reconciled") is True and not pending_claim_result.get("blocked"):
                    # The companion releases only the exact claim. Let the
                    # unchanged Native API finish its ordinary stale-lock cleanup.
                    attempt_result = daemon.reconcile_quiesced_active_attempt()
                    claim_result = daemon.reconcile_quiesced_implementation_task_claim()
                    reason = str(attempt_result.get("reason") or "")
            after_state, _ = _read_native_state(repo_root, state_dir / f"{STATE_PREFIX}_task_state.json")
            count_keys = ("implementation_attempts", "implementation_attempts_by_cid")
            before_state = preimage["native_payload"]
            if completed_claim_result is not None and after_state != before_state:
                return _refusal("completed_claim_native_payload_changed", observed,
                    counters_preserved=False, progress_preserved=False, effects_uncertain=True,
                    completed_claim_reconciliation=completed_claim_result)
            if (after_state.get("read_error") or any(after_state.get(key) != before_state.get(key) for key in count_keys)
                    or after_state.get("completed_task_ids") != before_state.get("completed_task_ids")):
                return _refusal("native_accounting_or_completion_changed", observed,
                    counters_preserved=False, progress_preserved=False,
                    attempt_refunded=None, diagnostics=["native invariant observation changed; no rollback attempted"],
                    attempt_reconciliation=attempt_result, claim_reconciliation=claim_result,
                    pending_claim_reconciliation=pending_claim_result,
                    completed_claim_reconciliation=completed_claim_result)
            reconciled = (not attempt_result.get("blocked") and
                not (isinstance(claim_result, dict) and claim_result.get("blocked"))) and (bool(attempt_result.get("reconciled")) or (
                isinstance(claim_result, dict) and bool(claim_result.get("reconciled")) and not claim_result.get("blocked")
            ) or (isinstance(completed_claim_result, dict)
                and completed_claim_result.get("reconciled") is True and not completed_claim_result.get("blocked")))
            if not reconciled:
                return _refusal(reason or "native_reconciliation_blocked", observed,
                                diagnostics=[reason or "native_reconciliation_blocked"],
                                attempt_reconciliation=attempt_result, claim_reconciliation=claim_result,
                                pending_claim_reconciliation=pending_claim_result,
                                completed_claim_reconciliation=completed_claim_result,
                                fence=fence, container_shutdown=containers)
            return {"recovery": "reconciled", "eligible": True, "reconciled": True,
                    "reason": reason or "quiesced_active_attempt_reconciled", "status": observed.get("status"),
                    "healthy": False, "worker_liveness": "dead",
                    "application_interview_state": None,
                    "diagnostics": [reason or "quiesced_active_attempt_reconciled"],
                    "attempt_reconciliation": attempt_result, "claim_reconciliation": claim_result,
                    "pending_claim_reconciliation": pending_claim_result,
                    "completed_claim_reconciliation": completed_claim_result,
                    "checkout_journal_settlement": checkout_settlement,
                    "fence": fence, "container_shutdown": containers,
                    "selection_performed": False, "paid_dispatch": False, "attempt_refunded": False,
                    "completion_authority": False, "counters_preserved": True, "progress_preserved": True,
                    "manual_holds_preserved": True, "provider_execution_evidence": observed.get("provider_execution_evidence"),
                    "validation_activity_evidence": observed.get("validation_activity_evidence")}
    except BlockingIOError:
        return _arm_cooldown(state_dir, "lock_contention", observed, now=moment, scope="runner")
    except (OSError, ValueError, RuntimeError) as exc:
        return _arm_cooldown(state_dir, "dependency_unavailable", observed, now=moment, scope="runner",
                             diagnostics=[type(exc).__name__, str(exc)[:500]])


def recover_stalled_worker(repo_root: Path, spec_path: Path, state_dir: Path, *, now: float | None = None,
                           expected_launcher_sha256: str | None = None) -> dict[str, Any]:
    """Explicit stopped-only operator seam; the native watchdog owns live work."""
    previous = dict(os.environ)
    try:
        effective = campaign_environment(repo_root, state_dir=state_dir)
        os.environ.clear()
        os.environ.update(effective)
        return _recover_stalled_worker(repo_root, spec_path, state_dir, now=now,
            expected_launcher_sha256=expected_launcher_sha256)
    finally:
        os.environ.clear()
        os.environ.update(previous)


def _signal_birth(identity: Mapping[str, Any], signum: int) -> bool:
    current = process_identity(identity.get("pid"))
    if not current or any(current.get(key) != identity.get(key) for key in ("pid", "start_ticks", "boot_id")):
        return False
    try:
        if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
            fd = os.pidfd_open(current["pid"])
            try:
                again = process_identity(current["pid"])
                if not again or again["start_ticks"] != identity["start_ticks"]:
                    return False
                signal.pidfd_send_signal(fd, signum)
            finally:
                os.close(fd)
        else:
            os.kill(current["pid"], signum)
        return True
    except ProcessLookupError:
        return False


def _descendants(root: Mapping[str, Any]) -> list[dict[str, Any]]:
    current = process_identity(root.get("pid"))
    if not current or any(current.get(key) != root.get(key) for key in ("start_ticks", "boot_id")):
        return []
    identities = [item for path in Path("/proc").iterdir() if path.name.isdigit()
                  if (item := process_identity(int(path.name))) is not None]
    owned = {root["pid"]}
    while True:
        additions = {item["pid"] for item in identities if item["ppid"] in owned}
        if additions <= owned:
            break
        owned.update(additions)
    current = process_identity(root.get("pid"))
    if not current or any(current.get(key) != root.get(key) for key in ("start_ticks", "boot_id")):
        return []
    return [item for item in identities if item["pid"] in owned and item["pid"] != root["pid"]]


def stop(state_dir: Path, *, timeout: float = 15.0,
         retained_native_child_proof: Mapping[str, Any] | None = None,
         expected_launcher_sha256: str | None = None) -> dict[str, Any]:
    with _lock(state_dir):
        path = state_dir / "launcher.json"
        record = _read_json(path)
        if expected_launcher_sha256 is not None:
            current_digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if (not re.fullmatch(r"[0-9a-f]{64}", expected_launcher_sha256)
                    or current_digest != expected_launcher_sha256):
                return {"status": "stop_incomplete", "signalled": False,
                        "reason": "launcher_changed_before_stop", "manual_holds_preserved": True}
        from .improvement_shutdown import close_campaign_containers
        try:
            recorded_worktree_root(record, state_dir)
        except (OSError, ValueError, TypeError) as error:
            return {"status": "stop_incomplete", "signalled": False, "reason": str(error), "manual_holds_preserved": True}
        if not owns_process(record):
            orphan_fence = None
            if retained_native_child_proof is None:
                from .improvement_shutdown import fence_owned_orphan_native_child
                try:
                    orphan_fence = fence_owned_orphan_native_child(state_dir, record)
                except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                    return {"status": "stop_incomplete", "signalled": False,
                            "reason": "owned_orphan_native_fence_refused", "manual_holds_preserved": True}
            containers = close_campaign_containers(state_dir, record, retained_native_child_proof=retained_native_child_proof)
            if not containers["applicable"]:
                return {"status": "not_owned_or_stopped", "signalled": False}
            if containers["quiesced"]:
                record.update(status="stopped", stopped_at=time.time())
                _atomic_json(path, record)
            return {"status": containers["status"], "signalled": False,
                    "container_shutdown": containers, "orphan_native_fence": orphan_fence,
                    "manual_holds_preserved": True}
        if retained_native_child_proof is not None:
            return {"status": "stop_incomplete", "signalled": False,
                    "reason": "retained native observation cannot authorize live fencing", "manual_holds_preserved": True}
        identity = record["identity"]
        children = _descendants(identity)
        _signal_birth(identity, signal.SIGTERM)
        deadline = time.monotonic() + max(0.0, min(timeout, 30.0))
        while owns_process(record) and time.monotonic() < deadline:
            time.sleep(0.1)
        captured = {child["pid"]: child for child in children}
        # Include children born during graceful native cleanup only through
        # parents whose original process birth still matches our receipt.
        for parent in [identity, *children]:
            for child in _descendants(parent):
                captured.setdefault(child["pid"], child)
        children = list(captured.values())
        # Native run_forever first fences its managed daemon. Only force the
        # birth-bound descendants captured from our actual process tree.
        for child in reversed(children):
            _signal_birth(child, signal.SIGTERM)
        if owns_process(record):
            _signal_birth(identity, signal.SIGKILL)
        for child in reversed(children):
            _signal_birth(child, signal.SIGKILL)
        deadline = time.monotonic() + 1.0
        def birth_alive(item):
            current = process_identity(item["pid"])
            return bool(current and current["start_ticks"] == item["start_ticks"]
                        and current["boot_id"] == item["boot_id"])
        while any(birth_alive(item) for item in [identity, *children]) and time.monotonic() < deadline:
            time.sleep(0.05)
        remaining = [item["pid"] for item in [identity, *children] if birth_alive(item)]
        containers = close_campaign_containers(state_dir, record, parent_quiesced=not remaining)
        outcome = "stop_incomplete" if remaining or (containers["applicable"] and not containers["quiesced"]) else "stopped"
        record.update(status=outcome, stopped_at=time.time())
        _atomic_json(path, record)
        return {"status": outcome, "signalled": True, "pid": identity["pid"], "remaining_pids": remaining,
                "container_shutdown": containers, "manual_holds_preserved": True}


def _read_validation_watchdog_authority(path: Path) -> dict[str, Any] | None:
    """Read Native's ordinary lease mode with the existing legacy custody rule."""
    from .improvement_recovery import _owned_bytes

    try:
        if path.resolve(strict=True) != path:
            return None
        value = json.loads(_owned_bytes(path, 65536, legacy_group_write=True))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


_VALIDATION_ACTIVITY_INTERVAL_SECONDS = 5.0


def _validation_activity_modules():
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as supervisor
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    return daemon, supervisor, plane


def _validation_activity_directory(path: Path, *, private=False):
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("validation_activity_path_unavailable")
    value = path.lstat()
    if (not stat.S_ISDIR(value.st_mode) or value.st_uid != os.getuid()
            or value.st_mode & (0o077 if private else 0o002)):
        raise ValueError("validation_activity_directory_unavailable")
    return path


def _validation_activity_log_identity(path: Path):
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("validation_activity_log_aliased")
    value = path.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid()
            or value.st_nlink != 1 or stat.S_IMODE(value.st_mode) != 0o600):
        raise ValueError("validation_activity_log_not_private")
    return value.st_dev, value.st_ino


def _validation_activity_snapshot(campaign):
    from .reconciliation_activity import snapshot
    return snapshot(sys.modules[__name__], campaign)


def _validation_activity_binding(workspace: Path, task: Mapping[str, Any], context: Mapping[str, Any], *, now_ts: float, owner_pid=None):
    """Read one exact live Native validation owner without changing its state."""
    from types import SimpleNamespace

    try:
        daemon, native, plane = _validation_activity_modules()
        campaign = _validation_activity_directory(Path(context["campaign_state_dir"]), private=True)
        target = _validation_activity_directory(Path(context["target_source_root"]))
        workspace = _validation_activity_directory(Path(workspace))
        if target != Path(__file__).resolve().parents[2]:
            return None
        state_path = campaign / f"{STATE_PREFIX}_task_state.json"
        snapshot = _validation_activity_snapshot(campaign)
        if not isinstance(snapshot, dict) or type(snapshot.get("revision")) is not int:
            return None
        state = snapshot.get("body")
        if not isinstance(state, dict):
            return None
        if state.get("active_phase") == "validating_reconciled_candidate":
            from .reconciliation_activity import binding as reconciled_binding
            return reconciled_binding(sys.modules[__name__], daemon, native,
                campaign=campaign, target=target, workspace=workspace, state=state,
                task=task, context=context, now_ts=now_ts, owner_pid=owner_pid)
        expected = {"task_id": task["id"], "canonical_task_cid": context["task_cid"],
                    "canonical_task_key": context["task_key"], "attempt": state.get("active_attempt")}
        if (not expected["task_id"] or not expected["canonical_task_cid"] or not expected["canonical_task_key"]
                or context.get("task_id") != expected["task_id"]
                or type(expected["attempt"]) is not int or not 1 <= expected["attempt"] <= 3
                or state.get("active_phase") != "validating" or state.get("implementation_in_progress") is not True
                or state.get("active_task_id") != expected["task_id"]
                or state.get("last_implementation_task_id") != expected["task_id"]
                or state.get("active_task_cid") != expected["canonical_task_cid"]
                or state.get("active_task_key") != expected["canonical_task_key"]
                or state.get("active_worktree_path") != str(workspace)):
            return None
        started = native.parse_timestamp(state.get("active_phase_started_at"))
        provider_started = native.parse_timestamp(state.get("last_implementation_started_at"))
        finished = native.parse_timestamp(state.get("last_implementation_finished_at"))
        if (started is None or provider_started is None or started < provider_started
                or finished is not None and finished >= provider_started
                or not 0 <= now_ts - started.timestamp() < float(TIMEOUT_SECONDS)):
            return None
        lease = _read_validation_watchdog_authority(campaign / "implementation.lock")
        claim_path = daemon.PortalImplementationDaemon._implementation_task_claim_path(
            SimpleNamespace(repo_root=target), expected["task_id"], canonical_task_cid=expected["canonical_task_cid"])
        claim = _read_validation_watchdog_authority(claim_path)
        identity = native.load_supervised_child_identity(campaign / f"{STATE_PREFIX}_managed_daemon.identity.json")
        owner_pid = os.getpid() if owner_pid is None else owner_pid
        if type(owner_pid) is not int or owner_pid <= 1:
            return None
        birth = native.read_process_birth(owner_pid)
        if lease is None or claim is None or identity is None or birth is None:
            return None
        launcher = _read_validation_watchdog_authority(campaign / "launcher.json")
        if (launcher is None or launcher.get("repo_root") != str(target)
                or launcher.get("state_dir") != str(campaign)):
            return None
        artifacts = DEFAULT_ARTIFACTS
        if any(key in launcher for key in ("schema_version", "spec_path", "plan_id")):
            spec_path = Path(str(launcher.get("spec_path") or ""))
            if not _campaign_tuple_matches(launcher, target, spec_path, campaign):
                return None
            _, artifacts = _campaign_spec(target, spec_path)
        scope = {"repo_root": str(target), "state_dir": str(campaign), "state_prefix": STATE_PREFIX,
                 "todo_path": str(target / artifacts.board_relative),
                 "daemon_entrypoint": str(Path(__file__).resolve())}
        if (dict(identity.owner_scope) != scope or identity.process_birth != birth or birth.pid != owner_pid
                or native.ProcessBirthIdentity.from_dict(claim.get("owner_process_birth")) != birth
                or lease.get("kind") != "implementation" or lease.get("lease_role") == "supervisor_maintenance"
                or claim.get("kind") != native.IMPLEMENTATION_TASK_CLAIM_LOCK_KIND
                or claim.get("lease_role") != native.IMPLEMENTATION_DISPATCH_INTENT_LEASE_ROLE
                or not lease.get("lease_id") or not claim.get("lease_id")
                or type(lease.get("pid")) is not int or type(claim.get("pid")) is not int
                or lease["pid"] != birth.pid or claim["pid"] != birth.pid
                or any(lease.get(key) != value or claim.get(key) != value for key, value in expected.items())
                or lease.get("repo_root") != str(target) or lease.get("state_dir") != str(campaign)
                or claim.get("state_dir") != str(campaign) or claim.get("state_path") != str(state_path)
                or not native.checkout_lock_repository_matches(claim, target)
                or claim.get("dispatch_authority_cid") != daemon.PortalImplementationDaemon._implementation_dispatch_authority_cid(claim)):
            return None
        worktree_root, _ = recorded_worktree_root(launcher, campaign)
        if workspace == worktree_root or not workspace.is_relative_to(worktree_root):
            return None
        log_path = Path(state.get("active_log_path") or "")
        if (state.get("last_implementation_log_path") != str(log_path)
                or log_path.parent != campaign / "implementation_logs"
                or re.fullmatch(re.escape(expected["task_id"].lower()) + r"-attempt-" + str(expected["attempt"]) + r"-[0-9a-f]{32}\.log", log_path.name) is None):
            return None
        log_identity = _validation_activity_log_identity(log_path)
        return {**expected, "workspace": str(workspace), "state_dir": str(campaign), "repo_root": str(target),
                "log_path": str(log_path), "log_identity": log_identity, "owner_record_id": identity.record_id,
                "owner_birth": birth.to_dict(), "lease_id": lease["lease_id"], "claim_lease_id": claim["lease_id"],
                "dispatch_authority_cid": claim["dispatch_authority_cid"],
                "phase_started_at": state["active_phase_started_at"],
                "phase_deadline": started.timestamp() + float(TIMEOUT_SECONDS)}
    except Exception:
        return None


def _validation_activity_path(binding, *, create=False):
    campaign = _validation_activity_directory(Path(binding["state_dir"]), private=True)
    directory = campaign / "validation-activity"
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
    _validation_activity_directory(directory, private=True)
    key = hashlib.sha256((binding["task_id"] + "\0" + binding["canonical_task_cid"] + "\0" + str(binding["attempt"])).encode()).hexdigest()
    return directory / (key + ".json")


def _read_validation_activity(path):
    from .improvement_recovery import _owned_bytes
    if path.resolve(strict=True) != path:
        raise ValueError("validation_activity_record_aliased")
    if stat.S_IMODE(path.lstat().st_mode) != 0o600:
        raise ValueError("validation_activity_record_not_private")
    value = json.loads(_owned_bytes(path, 65536))
    if not isinstance(value, dict):
        raise ValueError("validation_activity_record_malformed")
    return value


def _validation_activity_record_valid(value, binding, *, now_ts):
    from .improvement_plan import _digest
    if (not isinstance(value, dict) or value.get("schema") != "complaint-owned-validation-activity@1"
            or value.get("state") != "running" or value.get("completion_authority") is not False
            or re.fullmatch(r"[0-9a-f]{32}", str(value.get("activity_id", ""))) is None
            or value.get("binding_sha256") != _digest(binding)
            or _digest(value.get("binding")) != _digest(binding)):
        return False
    numbers = [value.get(key) for key in ("started_at", "observed_at", "deadline_at")]
    if any(isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) for number in numbers):
        return False
    started, observed, deadline = numbers
    phase_started = binding["phase_deadline"] - float(TIMEOUT_SECONDS)
    return bool(phase_started <= started <= observed <= now_ts < deadline
                and deadline <= min(binding["phase_deadline"], started + float(TIMEOUT_SECONDS))
                and now_ts - observed <= 2 * _VALIDATION_ACTIVITY_INTERVAL_SECONDS + 1)


def _publish_validation_activity(binding, *, activity_id, started_at, deadline_at):
    from .improvement_plan import _digest
    path = _validation_activity_path(binding, create=True)
    if os.path.lexists(path):
        previous = _read_validation_activity(path)
        if previous.get("activity_id") != activity_id or previous.get("binding_sha256") != _digest(binding):
            return False
    value = {"schema": "complaint-owned-validation-activity@1", "state": "running",
             "activity_id": activity_id, "binding": binding, "binding_sha256": _digest(binding),
             "started_at": started_at, "observed_at": time.time(), "deadline_at": deadline_at,
             "completion_authority": False}
    if not _validation_activity_record_valid(value, binding, now_ts=value["observed_at"]):
        return False
    _atomic_json(path, value)
    return True


def _clear_validation_activity(binding, activity_id):
    from .improvement_plan import _digest
    try:
        path = _validation_activity_path(binding)
        value = _read_validation_activity(path)
        if value.get("activity_id") != activity_id or value.get("binding_sha256") != _digest(binding):
            return
        # A failed unlink must leave an explicitly closed observation.
        _atomic_json(path, {**value, "state": "closed"})
        path.unlink()
    except Exception:
        return


def _hold_validation_activity_log_inode(binding):
    """Keep the admitted inode allocated throughout the real executor call."""
    daemon, _, _ = _validation_activity_modules()
    parent, filename = daemon._open_no_follow_parent(Path(binding["log_path"]))
    descriptor = -1
    try:
        descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        opened = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid() or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600
                or (opened.st_dev, opened.st_ino) != binding["log_identity"]
                or daemon._private_file_identity(opened) != daemon._private_file_identity(named)):
            raise OSError("validation_activity_log_inode_changed")
        result, descriptor = descriptor, -1
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _owned_validation_activity(supervisor, state, *, now_ts, owner_pid):
    try:
        context = {"campaign_state_dir": str(supervisor.config.state_dir),
                   "target_source_root": str(supervisor.config.repo_root),
                   "task_id": state.active_task_id, "task_cid": state.active_task_cid,
                   "task_key": state.active_task_key}
        binding = _validation_activity_binding(Path(state.active_worktree_path), {"id": state.active_task_id},
                                               context, now_ts=now_ts, owner_pid=owner_pid)
        if (binding is None or binding["attempt"] != state.active_attempt
                or binding["phase_started_at"] != state.active_phase_started_at):
            return False
        value = _read_validation_activity(_validation_activity_path(binding))
        return _validation_activity_record_valid(value, binding, now_ts=now_ts)
    except Exception:
        return False


def _validation_activity_pulse(binding, workspace, task, context, *, deadline: float, stopped, activity_lock,
                               activity_id, started_at, deadline_at):
    """Append host activity metadata only to the same private Native log inode."""
    if time.monotonic() >= deadline:
        return False
    fresh = _validation_activity_binding(workspace, task, context, now_ts=time.time())
    if fresh != binding:
        return False
    daemon, _, _ = _validation_activity_modules()
    path = Path(binding["log_path"])
    # Use Native's private-log parent traversal, but open without O_CREAT:
    # a removed/replaced log must never be recreated by a liveness observation.
    parent, filename = daemon._open_no_follow_parent(path)
    descriptor = -1
    try:
        descriptor = os.open(filename, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        opened = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid() or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600
                or (opened.st_dev, opened.st_ino) != binding["log_identity"]
                or daemon._private_file_identity(opened) != daemon._private_file_identity(named)
                or time.monotonic() >= deadline):
            return False
        value = {"schema": "complaint-owned-validation-activity@1", "activity": "canonical_native_executor_in_flight",
                 "timestamp": datetime.now(timezone.utc).isoformat(), "task_id": binding["task_id"],
                 "canonical_task_cid": binding["canonical_task_cid"], "attempt": binding["attempt"],
                 "completion_authority": False}
        raw = ("\n[host validation activity] " + json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(raw) > 2048:
            return False
        with activity_lock:
            if stopped.is_set() or time.monotonic() >= deadline:
                return False
            if os.write(descriptor, raw) != len(raw):
                return False
            return _publish_validation_activity(binding, activity_id=activity_id,
                                                started_at=started_at, deadline_at=deadline_at)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _call_validation_with_activity(*, executor, spec, workspace_path, timeout_seconds, environment, task, context):
    """Keep quiet real validation observable, without renewing any deadline."""
    if not isinstance(context, Mapping) or any(not isinstance(context.get(key), str) or not context[key]
            for key in ("campaign_state_dir", "target_source_root", "task_id", "task_cid", "task_key")):
        return executor(spec=spec, workspace_path=workspace_path, timeout_seconds=timeout_seconds, environment=environment)
    daemon, _, _ = _validation_activity_modules()
    if executor is not daemon.PortalImplementationDaemon._validation_command_runner:
        return executor(spec=spec, workspace_path=workspace_path, timeout_seconds=timeout_seconds, environment=environment)
    binding = _validation_activity_binding(workspace_path, task, context or {}, now_ts=time.time())
    if binding is None:
        return executor(spec=spec, workspace_path=workspace_path, timeout_seconds=timeout_seconds, environment=environment)
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise TimeoutError("subprocess_timeout")
    remaining = min(float(timeout_seconds), float(TIMEOUT_SECONDS), binding["phase_deadline"] - time.time())
    if remaining <= 0:
        raise TimeoutError("subprocess_timeout")
    deadline = time.monotonic() + remaining
    started_at = time.time()
    deadline_at = min(binding["phase_deadline"], started_at + remaining)
    activity_id = secrets.token_hex(16)
    stopped = threading.Event()
    activity_lock = threading.Lock()
    try:
        inode_guard = _hold_validation_activity_log_inode(binding)
    except OSError:
        return executor(spec=spec, workspace_path=workspace_path, timeout_seconds=remaining, environment=environment)

    def heartbeat():
        while not stopped.wait(_VALIDATION_ACTIVITY_INTERVAL_SECONDS):
            try:
                if not _validation_activity_pulse(binding, workspace_path, task, context or {}, deadline=deadline,
                                                  stopped=stopped, activity_lock=activity_lock,
                                                  activity_id=activity_id, started_at=started_at, deadline_at=deadline_at):
                    return
            except Exception:
                # Losing observation never creates authority or hides the
                # canonical executor's own result/exception.
                return

    worker = threading.Thread(target=heartbeat, name="complaint-validation-activity", daemon=True)
    try:
        worker.start()
    except RuntimeError:
        try:
            remaining = min(remaining, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError("subprocess_timeout")
            return executor(spec=spec, workspace_path=workspace_path, timeout_seconds=remaining, environment=environment)
        finally:
            os.close(inode_guard)
    try:
        remaining = min(remaining, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("subprocess_timeout")
        return executor(spec=spec, workspace_path=workspace_path, timeout_seconds=remaining, environment=environment)
    finally:
        with activity_lock:
            stopped.set()
        worker.join(timeout=1.0)
        try:
            # Keep the returned executor's exact current owner observable
            # while Native writes its terminal receipt. Never renew a task or
            # executor deadline, and never mint this for another dispatch.
            now_ts = time.time()
            fresh = _validation_activity_binding(workspace_path, task, context, now_ts=now_ts)
            if fresh == binding:
                from .validation_handoff import publish
                publish(sys.modules[__name__], binding, activity_id=activity_id,
                    started_at=started_at, settled_at=now_ts, deadline_at=deadline_at)
        except Exception:
            pass  # Observation failure cannot replace the canonical result.
        finally:
            _clear_validation_activity(binding, activity_id)
            os.close(inode_guard)


def _owned_validation_child_exists(native, owner_birth) -> bool:
    """Read an exact owned descendant during the first executor pulse gap.

    Native 6af's legacy marker detector joins its scalar command text as
    characters. Use actual procfs argv, retaining its existing marker scope,
    only after the caller has proved the full current Native dispatch owner.
    """
    markers = ("playwright", "run_playwright_test.mjs", "pytest", "vitest", "npm run test",
        "npm run evidence", "release-readiness-gate", "audit-release-evidence-freshness",
        "build-virtual-desktop-release-evidence", "tsc --noemit", "run_legal_ir_10m_smoke.sh",
        "run_legal_ir_8h_canary.sh", "run_hammer_leanstral_smoke.sh", "run_hammer_leanstral_hparam.sh",
        "uscode_modal_daemon_runner")
    try:
        if native.read_process_birth(owner_birth.pid) != owner_birth:
            return False
        for row in native.descendant_processes(owner_birth.pid):
            pid = row.get("pid")
            if type(pid) is not int or pid <= 1:
                continue
            birth = native.read_process_birth(pid)
            if (birth is None or birth.start_time_ticks != row.get("start_ticks")
                    or birth.start_time_ticks < owner_birth.start_time_ticks
                    or birth.boot_id != owner_birth.boot_id
                    or os.stat(f"/proc/{pid}").st_uid != os.getuid()):
                continue
            argv = native.read_process_command_argv(pid)
            if not argv or not any(marker in " ".join(argv).lower() for marker in markers):
                continue
            current, seen = birth, set()
            for _ in range(64):
                if current == owner_birth:
                    return (native.read_process_birth(pid) == birth
                            and native.read_process_birth(owner_birth.pid) == owner_birth
                            and native.read_process_command_argv(pid) == argv)
                if current.pid in seen or current.parent_pid <= 1:
                    break
                seen.add(current.pid)
                current = native.read_process_birth(current.parent_pid)
                if current is None:
                    break
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    return False


def _owned_validation_window(supervisor, state, *, now_ts: float) -> bool:
    """Observe a fixed validation deadline without refreshing any task clock.

    The provider deadline starts before the proposal is returned. Validation
    has its own existing command timeout. Only the current Native dispatch
    owner, its matching task claims and its live test child can use that window.
    """
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native

    if (state.active_phase != "validating" or not state.implementation_in_progress
            or not state.active_task_id or not state.active_task_key or not state.active_task_cid
            or state.last_implementation_task_id != state.active_task_id
            or type(state.active_attempt) is not int or not 1 <= state.active_attempt <= 3):
        return False
    try:
        started = native.parse_timestamp(state.active_phase_started_at)
        provider_started = native.parse_timestamp(state.last_implementation_started_at)
        finished = native.parse_timestamp(state.last_implementation_finished_at)
        timeout = min(float(TIMEOUT_SECONDS), supervisor._implementation_watchdog_timeout_seconds())
        if (started is None or provider_started is None or started < provider_started
                or finished is not None and finished >= provider_started
                or not 0 <= now_ts - started.timestamp() <= timeout):
            return False
        worktree_root = Path(supervisor.config.worktree_root).resolve(strict=True)
        workspace = Path(state.active_worktree_path)
        if (not workspace.is_absolute() or workspace.resolve(strict=True) != workspace
                or workspace == worktree_root or not workspace.is_relative_to(worktree_root)):
            return False
        lease = _read_validation_watchdog_authority(supervisor._implementation_maintenance_lock_path())
        claim = _read_validation_watchdog_authority(supervisor._task_dispatch_claim_path(state))
        identity = native.load_supervised_child_identity(supervisor._managed_daemon_identity_path())
        if lease is None or claim is None or identity is None:
            return False
        birth = native.ProcessBirthIdentity.from_dict(claim.get("owner_process_birth"))
        expected = {"task_id": state.active_task_id,
                    "canonical_task_key": state.active_task_key,
                    "canonical_task_cid": state.active_task_cid,
                    "attempt": state.active_attempt}
        if (dict(identity.owner_scope) != supervisor._managed_daemon_owner_scope()
                or tuple(identity.command) != tuple(supervisor._build_daemon_command())
                or birth != identity.process_birth
                or native.read_process_birth(birth.pid) != birth
                or native.read_process_command_argv(birth.pid) != identity.command
                or native.supervised_child_identity_liveness(identity) is not native.OwnerLiveness.ALIVE
                or lease.get("kind") != "implementation"
                or lease.get("lease_role") == "supervisor_maintenance"
                or claim.get("kind") != native.IMPLEMENTATION_TASK_CLAIM_LOCK_KIND
                or claim.get("lease_role") != native.IMPLEMENTATION_DISPATCH_INTENT_LEASE_ROLE
                or not lease.get("lease_id") or not claim.get("lease_id")
                or int(lease.get("pid") or 0) != birth.pid
                or int(claim.get("pid") or 0) != birth.pid
                or any(lease.get(key) != value or claim.get(key) != value for key, value in expected.items())
                or Path(str(lease.get("repo_root") or "")).resolve() != supervisor.config.repo_root.resolve()
                or Path(str(lease.get("state_dir") or "")).resolve() != supervisor.config.state_dir.resolve()
                or Path(str(claim.get("state_dir") or "")).resolve() != supervisor.config.state_dir.resolve()
                or Path(str(claim.get("state_path") or "")).resolve() != supervisor.config.state_path.resolve()
                or not native.checkout_lock_repository_matches(claim, supervisor.config.repo_root)
                or claim.get("dispatch_authority_cid") != native.PortalImplementationDaemon._implementation_dispatch_authority_cid(claim)):
            return False
        from .validation_handoff import owned as owned_handoff
        return bool(supervisor._active_validation_subprocess_exists()
                    or _owned_validation_child_exists(native, birth)
                    or _owned_validation_activity(supervisor, state, now_ts=now_ts, owner_pid=birth.pid)
                    or owned_handoff(sys.modules[__name__], supervisor, state, now_ts=now_ts, owner_pid=birth.pid))
    except (OSError, TypeError, ValueError, AttributeError, KeyError):
        return False


def _preserve_uncommitted_reconciliation_candidates(supervisor):
    """Let Native preserve pending orphan edits before its merged-base shortcut.

    An interrupted proposal can still have the already-integrated baseline as
    HEAD. Native's ordinary reconciliation skips that HEAD before checking its
    uncommitted content. Only this owned campaign, under Native's maintenance
    lease, may ask its existing rescue helper to preserve those edits first.
    """
    config = supervisor.config
    held = getattr(supervisor, "_held_implementation_maintenance_lease", None)
    if (not getattr(config, "worktree_reconciliation_enabled", True)
            or not isinstance(held, Mapping) or held.get("lease_role") != "supervisor_maintenance"
            or held.get("pid") != os.getpid()):
        return []
    launch = _read_json(config.state_dir / "launcher.json")
    if (launch.get("status") not in {"starting", "running"}
            or launch.get("repo_root") != str(config.repo_root.resolve())
            or launch.get("state_dir") != str(config.state_dir)
            or launch.get("identity", {}).get("pid") != os.getpid()
            or not owns_process(launch)):
        return []
    root, binding = recorded_worktree_root(launch, config.state_dir)
    if binding is None or config.worktree_root != root or root.resolve(strict=True) != root:
        raise RuntimeError("owned reconciliation worktree domain is unavailable")
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import parse_task_text
    tasks = parse_task_text(config.todo_path.read_text(), path=config.todo_path, task_header_prefix=config.task_prefix)
    held_tasks = set(_board_summary(tasks)["manual_hold_task_ids"])
    pending = {task.task_id for task in tasks if task.status == "todo" and task.task_id not in held_tasks}
    records = supervisor._git_worktree_records(config.repo_root)
    if len(records) > 256:
        raise RuntimeError("owned reconciliation worktree population exceeds its bound")
    owners = supervisor._shared_active_worktree_owners(root)
    commands = supervisor._list_process_commands()
    target = config.merge_target_branch or supervisor._git_current_branch(config.repo_root) or "HEAD"
    preserved = []
    for record in records:
        path = Path(str(record.get("worktree") or ""))
        branch = str(record.get("branch") or "").removeprefix("refs/heads/")
        head = str(record.get("HEAD") or "")
        if (not path.is_absolute() or not path.is_relative_to(root) or path == root
                or not path.exists() or path.resolve(strict=True) != path or not head
                or not supervisor._worktree_branch_is_reconcilable(branch)
                or supervisor._worktree_branch_source_task_id(branch, known_task_ids=tuple(pending)) not in pending
                or not supervisor._git_ref_is_ancestor(config.repo_root, head, target)):
            continue
        dirty = supervisor._git_status_short(path)
        # An unused prepared checkout can differ only in SDK gitlinks. That
        # bootstrap state is not an uncommitted complaint-generator proposal.
        root_edits = [line for line in dirty if line[3:] not in _PRIVATE_DEPENDENCY_ROOTS]
        if (not root_edits or supervisor._active_worktree_skip_detail(path, owners) is not None
                or any(str(path) in command for command in commands)):
            continue
        result = supervisor._rescue_dirty_worktree(path, branch=branch, head=head,
            target_ref=target, status_lines=dirty, reason="reconciliation_uncommitted_integrated_base")
        if result.get("preserved") is not True:
            raise RuntimeError("uncommitted reconciliation candidate preservation is required")
        preserved.append(result)
    return preserved


def _rescue_original_branch_from_attestation(*, task_id, branch, baseline, commit, raw_commit, events):
    """Recover a Native rescue's original branch without granting admission."""
    if not branch.startswith("rescue/worktree/") or not re.fullmatch(r"[0-9a-f]{40}", commit):
        return None
    header, separator, body = raw_commit.partition("\n\n")
    if (not separator or len(raw_commit.encode()) > 65536
            or [line[7:] for line in header.splitlines() if line.startswith("parent ")] != [baseline]
            or not any(line.startswith("author ") and " <implementation-supervisor@example.invalid> " in line for line in header.splitlines())
            or not any(line.startswith("committer ") and " <implementation-supervisor@example.invalid> " in line for line in header.splitlines())):
        return None
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(lines) != 4 or not lines[1].startswith("Original branch: "):
        return None
    original = lines[1].removeprefix("Original branch: ")
    if (not original.startswith("implementation/")
            or re.search(rf"(?<![A-Za-z0-9]){re.escape(task_id)}(?![A-Za-z0-9])", original, re.IGNORECASE) is None
            or lines[0] != "Rescue dirty worktree " + original
            or lines[2] != "Original HEAD: " + baseline
            or lines[3] != "Cleanup reason: reconciliation_uncommitted_integrated_base"):
        return None
    matches = [event for event in events if event.get("type") == "dirty_worktree_rescued"
        and event.get("preserved") is True and event.get("returncode") == 0
        and event.get("branch") == original and event.get("head") == baseline
        and event.get("rescue_branch") == branch and event.get("rescue_commit") == commit]
    return original if matches else None


def _owned_rescue_original_branch(supervisor, daemon, task, branch, baseline):
    """Bind Native's existing receipt lookup to the attested original branch."""
    held = getattr(supervisor, "_held_implementation_maintenance_lease", None)
    config = supervisor.config
    if (daemon.implement is not False or not isinstance(held, Mapping)
            or held.get("lease_role") != "supervisor_maintenance" or held.get("pid") != os.getpid()):
        return None
    launch = _read_json(config.state_dir / "launcher.json")
    if (launch.get("status") not in {"starting", "running"}
            or launch.get("repo_root") != str(config.repo_root.resolve())
            or launch.get("state_dir") != str(config.state_dir)
            or launch.get("identity", {}).get("pid") != os.getpid() or not owns_process(launch)):
        return None
    root, binding = recorded_worktree_root(launch, config.state_dir)
    if binding is None or config.worktree_root != root or root.resolve(strict=True) != root:
        return None
    records = supervisor._git_worktree_records(config.repo_root)
    if len(records) > 256:
        return None
    records = [row for row in records if str(row.get("branch") or "").removeprefix("refs/heads/") == branch]
    if len(records) != 1:
        return None
    row = records[0]
    path = Path(str(row.get("worktree") or ""))
    if (not path.is_absolute() or not path.is_relative_to(root) or path == root
            or path.resolve(strict=True) != path or supervisor._git_status_short(path)):
        return None
    commit = str(row.get("HEAD") or "")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        return None
    metadata = daemon._run_git(["cat-file", "commit", commit], cwd=path)
    if metadata.returncode != 0 or len(metadata.stdout.encode()) > 65536:
        return None
    from .improvement_recovery import _owned_bytes
    raw = _owned_bytes(config.events_path, MAX_EVENT_HISTORY_BYTES, legacy_group_write=True)
    if not raw.endswith(b"\n"):
        return None
    events = [json.loads(line) for line in raw.splitlines()]
    previous = ""
    for index, event in enumerate(events, 1):
        body = {key: value for key, value in event.items() if key != "event_id"}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        if (event.get("sequence") != index or event.get("previous_event_id", "") != previous
                or event.get("event_id") != "sha256:" + digest):
            return None
        previous = event["event_id"]
    events = [event for event in events if event.get("path") == str(path)
        and event.get("target_ref") == config.merge_target_branch]
    return _rescue_original_branch_from_attestation(task_id=task.task_id, branch=branch,
        baseline=baseline, commit=commit, raw_commit=metadata.stdout, events=events)


def _rescue_receipt_daemon_class(native_class, supervisor):
    class RescueReceiptDaemon(native_class):
        __slots__ = ()

        def _reconciliation_accepted_proposal_context(self, *, task, branch_name, baseline_ref):
            ordinary = super()._reconciliation_accepted_proposal_context(
                task=task, branch_name=branch_name, baseline_ref=baseline_ref)
            if ordinary.get("segment_found") or not branch_name.startswith("rescue/worktree/"):
                return ordinary
            original = _owned_rescue_original_branch(supervisor, self, task, branch_name, baseline_ref)
            if original is None:
                return ordinary
            # Native still rederives and exactly matches the proposal, policy,
            # receipt, task identity, baseline and changed paths. It then runs
            # fresh measured validation; no consumed-token set is edited here.
            return super()._reconciliation_accepted_proposal_context(
                task=task, branch_name=original, baseline_ref=baseline_ref)
    return RescueReceiptDaemon


def _startup_candidate_is_completed(supervisor, candidate):
    """Recognize Native's retained terminal candidate without retiring it."""
    if not isinstance(candidate, Mapping):
        return False
    merge = candidate.get("merge_result")
    if isinstance(merge, Mapping) and merge.get("reason") == "preflight_merge_conflict":
        from .startup_terminal_candidate import completed_preflight_conflict
        return completed_preflight_conflict(supervisor, candidate)
    context = getattr(supervisor, "_complaint_startup_reconciliation_context", None)
    if (candidate.get("merged") is not False or not isinstance(merge, Mapping)
            or merge.get("attempted") is not False or merge.get("merged") is not False
            or merge.get("reason") != "reconciliation_candidate_task_already_completed"
            or not isinstance(context, Mapping)):
        return False
    try:
        from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
        daemon = context["daemon"]
        if not isinstance(daemon, PortalImplementationDaemon):
            return False
        # Only Native's event-derived branch mapping qualifies. Its fallback
        # branch-name parser cannot turn a reason string into task authority.
        branch = str(candidate.get("branch") or "").removeprefix("refs/heads/")
        task_id = context["task_ids_by_branch"].get(branch)
        task = context["tasks_by_id"].get(task_id)
        if not branch or not task_id or task is None:
            return False
        identity = daemon._identity_for_task(task)
        if not identity.canonical_task_cid or not identity.canonical_task_key:
            return False
        return not PortalImplementationDaemon._completed_task_binding_error(daemon, {
            "task": {"task_id": task_id},
            "completion_task_cids": {task_id: identity.canonical_task_cid},
        })
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return False


def _validation_aware_supervisor_class(native_class):
    class ValidationAwareSupervisor(native_class):
        @staticmethod
        def _read_watchdog_authority(path):
            # Native uses this reader for setup and maintenance admission as
            # well as validation. Ordinary Native leases use its legacy mode.
            return _read_validation_watchdog_authority(path)

        def _run_forever_loop(self):
            self._complaint_startup_preflight_pending = True
            self._complaint_startup_reconciliation_context = None
            return super()._run_forever_loop()

        def _reconciliation_task_context(self, daemon):
            context = super()._reconciliation_task_context(daemon)
            if getattr(self, "_complaint_startup_preflight_pending", False):
                self._complaint_startup_reconciliation_context = {
                    "daemon": daemon, "tasks_by_id": context[0], "task_ids_by_branch": context[1],
                    "provenance_by_branch": context[3] if len(context) > 3 else {},
                }
            return context

        def run_once(self, *, include_refill=True):
            result = super().run_once(include_refill=include_refill)
            if getattr(self, "_complaint_startup_preflight_pending", False):
                if result.get("maintenance_blocked") is True:
                    raise RuntimeError("Native startup preflight blocked: " + str(result.get("reason") or "maintenance unavailable"))
                if any(item.get("reason") == "reconciliation_limit_reached" for item in
                        result.get("worktree_reconciliation", {}).get("skipped", ())):
                    raise RuntimeError("Native startup candidate recovery remains unresolved")
                from .startup_integrated_scope import (
                    retained_empty_integrated_baseline, retained_integrated_scope_refusal)
                from .startup_rejected_candidate import retained_replay_rejection
                from .startup_settled_validation import settled_validation_failure
                if any(item.get("merged") is not True and not _startup_candidate_is_completed(self, item)
                        and not retained_replay_rejection(self, item, maintenance_result=result)
                        and not settled_validation_failure(self, item, maintenance_result=result)
                        and not retained_integrated_scope_refusal(self, item, maintenance_result=result)
                        and not retained_empty_integrated_baseline(self, item, maintenance_result=result) for item in
                        result.get("worktree_reconciliation", {}).get("processed", ())):
                    raise RuntimeError("Native startup candidate recovery remains unresolved")
                self._complaint_startup_preflight_pending = False
                self._complaint_startup_reconciliation_context = None
            return result

        def _implementation_attempt_is_active(self, state, *, now_ts):
            return (super()._implementation_attempt_is_active(state, now_ts=now_ts)
                    or _owned_validation_window(self, state, now_ts=now_ts))

        def _build_worktree_reconciliation_daemon(self):
            # Native owns orphan discovery, claims, validation, merge and the
            # completion callback. Recovery uses the same measured gate as a
            # newly generated proposal and dispatches no replacement provider.
            daemon = super()._build_worktree_reconciliation_daemon()
            from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
            if isinstance(daemon, PortalImplementationDaemon):
                daemon.__class__ = _rescue_receipt_daemon_class(type(daemon), self)
            from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler
            native_scheduler = daemon.validation_scheduler
            if isinstance(native_scheduler, ValidationScheduler):
                workers = getattr(self.config, "validation_max_workers", None) or 1
                budget = getattr(self.config, "validation_resource_budget", None) or workers
                native_scheduler = ValidationScheduler(
                    cache=native_scheduler.cache, max_workers=workers, resource_budget=budget,
                    default_timeout_seconds=getattr(self.config, "implementation_timeout", TIMEOUT_SECONDS),
                )
            scheduler = EvidenceValidationScheduler(
                native_scheduler, state_dir=self.config.state_dir,
                spec=_native_campaign_spec(self.config.repo_root, self.config.state_dir,
                    todo_path=getattr(self.config, "todo_path", None),
                    board_namespace=getattr(self.config, "board_namespace", None)),
                defer_readiness=True,
            )
            daemon.validation_scheduler = scheduler
            daemon.proof_workflow = scheduler.bind_task
            return daemon

        def reconcile_backlogged_worktrees(self, *, preacquired_implementation_lock=None):
            preserved = _preserve_uncommitted_reconciliation_candidates(self)
            result = super().reconcile_backlogged_worktrees(
                preacquired_implementation_lock=preacquired_implementation_lock,
            )
            result["owned_uncommitted_candidates_preserved"] = preserved
            unresolved = [candidate for candidate in preserved if not any(
                item.get("path") == candidate.get("path") and item.get("merged") is True
                for item in result.get("processed", ())) ]
            if unresolved:
                raise RuntimeError("preserved candidate requires Native recovery before provider dispatch")
            return result
    return ValidationAwareSupervisor


def _run_native_supervisor(argv, *, repo_root, logger, daemon_script_path):
    """Use Native configuration and run loop with the bounded phase predicate."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor_runner as lifecycle
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon_runner import implementation_state_artifact_paths

    parsed = native.parse_args(list(argv))
    lifecycle.configure_supervisor_logging(parsed)
    config = native.supervisor_config_from_args(
        parsed, repo_root=repo_root,
        daemon_script_path=getattr(parsed, "daemon_script_path", None) or daemon_script_path,
        worktree_submodule_paths=getattr(parsed, "worktree_submodule_path", None),
    )
    paths = implementation_state_artifact_paths(parsed.state_dir, parsed.state_prefix, supervisor_events=True)
    context = lifecycle.ImplementationSupervisorRunContext(
        parsed=parsed, config=config, state_path=config.state_path,
        strategy_path=config.strategy_path, events_path=config.events_path,
        daemon_events_path=paths["daemon_events_path"],
    )
    supervisor = _validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    return lifecycle.run_portal_implementation_supervisor(supervisor, context, logger=logger)


def run_internal(repo_root: Path, spec_path: Path, state_dir: Path, token: str, merge_target: str, *, worktree_root: Path | None = None) -> int:
    # Refuse before creating even a lock file when storage cannot be observed.
    prospective_root, _ = recorded_worktree_root(_read_json(state_dir / "launcher.json"), state_dir)
    _require_resource_capacity(repo_root, state_dir, prospective_root, os.environ, stage="before_owned_startup_lock")
    # Serialize startup against parent receipt publication and future starts.
    with _lock(state_dir):
        record = _read_json(state_dir / "launcher.json")
        if record.get("owner_token") != token or not owns_process(record) or record["identity"]["pid"] != os.getpid():
            raise RuntimeError("internal runner lacks its exact owned launch receipt")
        selected_root, root_binding = recorded_worktree_root(record, state_dir)
        if (root_binding is not None and worktree_root != selected_root) or (root_binding is None and worktree_root is not None):
            raise RuntimeError("internal worktree root differs from its owned launch")
    with _lock(state_dir, "runner.lock", blocking=False):
        os.chdir(repo_root)
        from .improvement_plan import build_improvement_work_plan
        spec, artifacts = _campaign_spec(repo_root, spec_path)
        if build_improvement_work_plan(spec).plan_id != record.get("plan_id"):
            raise RuntimeError("specification changed after the owned launch was prepared")
        effective = campaign_environment(repo_root, context_exclude=spec["execution_policy"].get("context_exclude"), state_dir=state_dir)
        if not _auth_material_present(effective):
            raise RuntimeError("auth_material_unavailable")
        os.environ.clear()
        os.environ.update(effective)
        _validate_board(repo_root, repo_root / artifacts.board_relative, spec)
        privacy = _private_runtime_checks(repo_root, effective)
        if not privacy["ready"]:
            raise RuntimeError(privacy["reason"])
        _require_resource_capacity(repo_root, state_dir, selected_root, effective, stage="before_native_supervisor")
        # Recheck the bound storage directory immediately before native admission.
        if recorded_worktree_root(record, state_dir) != (selected_root, root_binding):
            raise RuntimeError("worktree root changed before native admission")
        # No --once: this is the real native run_forever watchdog and daemon.
        _run_native_supervisor(
            native_argv(repo_root / artifacts.board_relative, state_dir, merge_target, worktree_root=selected_root,
                        board_namespace=artifacts.board_namespace, protected_paths=artifacts.protected_paths),
            repo_root=repo_root, logger=_LOGGER,
            daemon_script_path=Path(__file__).resolve(),
        )
    return 0


def _evidence_root(state_dir: Path, task_id: str) -> Path:
    if not isinstance(task_id, str) or re.fullmatch(r"CIMP-[A-Za-z0-9_.:-]+", task_id) is None:
        raise ValueError("task evidence requires a stable CIMP identifier")
    return state_dir / "evidence" / task_id


def _task_outputs(task: Mapping[str, Any]) -> list[str]:
    targets = task.get("targets", task.get("outputs"))
    if not isinstance(targets, list) or not targets:
        raise ValueError("task evidence requires declared outputs")
    return [str(item) for item in targets]


def _task_freeze_inputs(task: Mapping[str, Any], *, context=None, spec=None) -> list[str]:
    inputs = _task_outputs(task)
    relative = (context or {}).get("campaign_spec_relative")
    if relative is None and isinstance(spec, Mapping) and "campaign" in spec:
        relative = campaign_artifacts(spec).spec_relative
    return list(dict.fromkeys([*inputs, relative])) if relative else inputs


def _observed_artifacts(repo_root: Path, observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    from .improvement_plan import _hash_file, _safe_relative

    raw = observation.get("artifacts", [])
    if not isinstance(raw, list):
        return [{"present": False, "sha256": "", "relative_path": ""}]
    resolved = []
    for item in raw:
        relative = item.get("relative_path") if isinstance(item, dict) else item
        path = _safe_relative(repo_root, relative)
        record: dict[str, Any] = {
            "relative_path": relative if isinstance(relative, str) else "",
            "present": bool(path and path.is_file() and path.stat().st_size > 0),
            "sha256": _hash_file(path) if path and path.is_file() and path.stat().st_size > 0 else "",
        }
        if isinstance(item, dict) and "sha256" in item:
            record["claimed_sha256"] = item.get("sha256")
        resolved.append(record)
    return resolved


def gate_task_completion(repo_root: Path, state_dir: Path, task: Mapping[str, Any],
                         observation: Mapping[str, Any], *,
                         facts: Mapping[str, Any] | None = None,
                         model_policy: Mapping[str, Any] | None = None,
                         legal_data_version: str = "",
                         spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Persist admission evidence; native callbacks alone publish completion."""

    from .improvement_plan import COMPLETING_LANE, EVIDENCE_LANES, assess_behavioral_evidence, bind_sources, _digest

    if not isinstance(legal_data_version, str):
        raise ValueError("legal_data_version must be a string")
    root = Path(repo_root).resolve()
    state_dir = Path(state_dir).resolve()
    binding = bind_sources(root, _task_outputs(task))
    observed = observation.copy()
    from .improvement_plan import _MeasuredEvidence
    if not isinstance(observation, _MeasuredEvidence):
        observed["artifacts"] = _observed_artifacts(root, observation)
    receipt = assess_behavioral_evidence(task, observed, source_binding=binding, model_policy=model_policy)
    if isinstance(observation, _MeasuredEvidence) and receipt.get("reason") == "existing_behavioral_definition_changed":
        detail = observation["host_measurement"].get("behavioral_definition_diagnostic")
        if isinstance(detail, dict) and detail.get("schema") == "complaint-behavioral-definition-diagnostic@1":
            receipt["behavioral_definition_diagnostic"] = detail
    if isinstance(observation, _MeasuredEvidence) and receipt.get("reason") in {
            "synthetic_browser_http_response", "browser_http_preflight_unavailable"}:
        detail = observation["host_measurement"].get("browser_http_preflight")
        if isinstance(detail, dict) and detail.get("schema") == "complaint-browser-http-preflight@1":
            receipt["browser_http_preflight"] = detail
    receipt["host_task_contract"] = observation.get("host_task_contract")
    receipt["facts_digest"] = _digest(dict(facts or {}))
    receipt["legal_data_version"] = legal_data_version
    receipt["implementation_digest"] = binding.get("digest") or ""
    if receipt["completion"] and not legal_data_version.strip():
        receipt["admitted"] = False
        receipt["completion"] = False
        receipt["repairable"] = True
        receipt["reason"] = "missing_legal_data_version"
    directory = _evidence_root(state_dir, str(task.get("id") or ""))
    with _lock(state_dir, "evidence.lock"):
        directory.mkdir(parents=True, exist_ok=True)
        lane_name = receipt["lane"] if receipt["lane"] in EVIDENCE_LANES else "rejected"
        _atomic_json(directory / f"{lane_name}.json", receipt)
        if receipt["lane"] == COMPLETING_LANE:
            _atomic_json(directory / "completion.json", receipt)
    if spec is not None:
        receipt["readiness"] = recompute_dependent_readiness(
            root, state_dir, spec, facts=facts, model_policy=model_policy,
            legal_data_version=legal_data_version or None,
        )
    return receipt


def _invalidate(receipt: Mapping[str, Any], reason: str) -> dict[str, Any]:
    updated = dict(receipt)
    updated["admitted"] = False
    updated["completion"] = False
    updated["repairable"] = True
    updated["reason"] = reason
    return updated


def recompute_dependent_readiness(repo_root: Path, state_dir: Path, spec: Mapping[str, Any], *,
                                  facts: Mapping[str, Any] | None = None,
                                  model_policy: Mapping[str, Any] | None = None,
                                  legal_data_version: str | None = None) -> dict[str, Any]:
    """Drop completion that no longer matches source, facts, model policy or legal data.

    Dependents of a task whose evidence was rejected or invalidated are not ready.
    The stored reason stays explicit and repairable.
    """

    from .improvement_plan import READINESS_SCHEMA, bind_sources, canonical_model_policy, _digest

    if not isinstance(spec, dict) or not isinstance(spec.get("tasks"), list):
        raise ValueError("readiness requires the reviewed task list")
    root = Path(repo_root).resolve()
    state_dir = Path(state_dir).resolve()
    policy = canonical_model_policy() if model_policy is None else dict(model_policy)
    facts_digest = None if facts is None else _digest(dict(facts))
    tasks = spec["tasks"]
    identifiers = [item.get("id") for item in tasks]
    if any(not isinstance(item, str) for item in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("readiness requires unique task identifiers")
    dependencies = {item["id"]: list(item.get("depends_on") or []) for item in tasks}
    for task_id, upstream in dependencies.items():
        if any(item not in dependencies or item == task_id for item in upstream):
            raise ValueError(f"{task_id} has an unknown or self dependency")
    visiting: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"task dependency cycle at {task_id}")
        visiting.add(task_id)
        for upstream in dependencies[task_id]:
            if upstream in visiting and upstream not in order:
                raise ValueError(f"task dependency cycle at {upstream}")
            if upstream not in order:
                visit(upstream)
        visiting.remove(task_id)
        order.append(task_id)

    order: list[str] = []
    for task_id in dependencies:
        if task_id not in order:
            visit(task_id)
    by_id = {item["id"]: item for item in tasks}
    reports: dict[str, Any] = {}
    with _lock(state_dir, "evidence.lock"):
        for task_id in order:
            path = state_dir / "evidence" / task_id / "completion.json"
            receipt = _read_json(path)
            reason = ""
            if not receipt or receipt.get("read_error"):
                complete = False
                reason = "missing_behavioral_evidence"
            else:
                fresh = bind_sources(root, _task_outputs(by_id[task_id]))
                if (receipt.get("implementation_digest") != fresh.get("digest")
                        or not fresh.get("digest")):
                    reason = "stale_source_hash" if fresh.get("digest") or receipt.get("implementation_digest") else "missing_output"
                    if fresh.get("missing") or fresh.get("empty"):
                        reason = "missing_output"
                elif receipt.get("host_measurement") and (receipt["host_measurement"].get("source_after") != _source_freeze(root, _task_freeze_inputs(by_id[task_id], spec=spec)) or any(not Path(p).is_file() or hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in receipt["host_measurement"].get("imported_sources", {}).items())):
                    reason = "stale_source_hash"
                elif not isinstance(receipt.get("host_task_contract"), dict) or receipt["host_task_contract"].get("task") != by_id[task_id]:
                    reason = "task_contract_changed"
                elif receipt.get("model_policy") != policy:
                    reason = "model_policy_changed"
                elif legal_data_version is not None and receipt.get("legal_data_version") != legal_data_version:
                    reason = "legal_data_version_changed"
                elif facts_digest is not None and receipt.get("facts_digest") != facts_digest:
                    reason = "corrected_facts"
                elif receipt.get("completion") is not True or receipt.get("lane") != "local_node_integration":
                    reason = str(receipt.get("reason") or "behavioral_evidence_rejected")
                    complete = False
                else:
                    complete = True
                if reason:
                    complete = False
                    receipt = _invalidate(receipt, reason)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_json(path, receipt)
            blocked = [item for item in dependencies[task_id] if not reports[item]["complete"]]
            if blocked:
                complete = False
                reason = "upstream_evidence_not_current"
                if receipt:
                    receipt = _invalidate(receipt, reason)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_json(path, receipt)
            reports[task_id] = {
                "complete": complete,
                "ready": not blocked,
                "blocked_by": blocked,
                "reason": "" if complete else reason,
                "repairable": not complete,
            }
        document = {"schema_version": READINESS_SCHEMA, "tasks": reports,
                    "completion_authority": False, "native_scheduling_enforced": False,
                    "enforcement": "admission_advisory_only_no_native_ready_filter",
                    "model_policy": policy, "legal_data_version": legal_data_version,
                    "facts_digest": facts_digest}
        destination = state_dir / "evidence"
        destination.mkdir(parents=True, exist_ok=True)
        _atomic_json(destination / "readiness.json", document)
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare, run and observe the Grok-only complaint improvement campaign.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "doctor", "start", "status", "recover", "stop", "watch", "watchdog", "_run"):
        child = commands.add_parser(command, help=argparse.SUPPRESS if command == "_run" else command)
        child.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
        child.add_argument("--spec", type=Path)
        child.add_argument("--state-dir", type=Path)
        if command in {"doctor", "start", "_run"}:
            child.add_argument("--worktree-root", type=Path, help="Existing dedicated canonical UID-owned0700 external directory; persisted for future starts.")
        if command in {"start", "watch"}:
            child.add_argument("--monitor-seconds", type=float, default=21600,
                               help="One bounded monitor window, at most six hours.")
        if command == "start":
            child.add_argument("--watch", action="store_true",
                               help="Watch this launch and close its verified orphan if the launcher exits.")
        if command == "watchdog":
            mode = child.add_mutually_exclusive_group()
            mode.add_argument("--once", action="store_true", help="One durable progress/recovery check, suitable for a timer.")
            mode.add_argument("--install-user-timer", action="store_true", help="Install and enable this campaign's minutely user timer.")
            child.add_argument("--interval-seconds", type=float, default=60)
            child.add_argument("--stop-completed", action="store_true", help="Close this owned launcher after verified completion.")
            child.add_argument("--expected-spec-sha256")
            child.add_argument("--expected-plan-id")
        if command == "_run":
            child.add_argument("--owner-token", required=True)
            child.add_argument("--merge-target", required=True)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    spec = (args.spec or root / SPEC_RELATIVE).resolve()
    try:
        if args.command == "start" and args.watch:
            from .improvement_monitor import validate_monitor_duration
            validate_monitor_duration(args.monitor_seconds)
        if args.state_dir is not None:
            state = args.state_dir.resolve()
        else:
            from .improvement_recovery import resolve_active_epoch
            state = resolve_active_epoch(root, spec, default_state_dir(root))
        os.chdir(root)
        if args.command == "_run":
            return run_internal(root, spec, state, args.owner_token, args.merge_target, worktree_root=args.worktree_root)
        if args.command == "stop":
            result = stop(state)
        elif args.command == "watchdog":
            from .campaign_watchdog import install_user_timer, watch_campaign
            if args.install_user_timer:
                result = install_user_timer(root, spec, state)
            else:
                result = watch_campaign(root, spec, state, once=args.once,
                    interval_seconds=args.interval_seconds, stop_completed=args.stop_completed,
                    expected_spec_sha256=args.expected_spec_sha256, expected_plan_id=args.expected_plan_id)
        elif args.command == "watch":
            from .improvement_monitor import watch_owned_launch
            result = watch_owned_launch(root, spec, state, maximum_seconds=args.monitor_seconds)
        else:
            keywords = {"worktree_root": args.worktree_root} if getattr(args, "worktree_root", None) is not None else {}
            result = {"prepare": prepare, "doctor": doctor, "start": start, "status": status, "recover": recover_stalled_worker}[args.command](root, spec, state, **keywords)
            if args.command == "start" and args.watch and result.get("status") in {"starting", "already_running"}:
                from .improvement_monitor import watch_owned_launch
                initial = result
                result = watch_owned_launch(root, spec, state, maximum_seconds=args.monitor_seconds)
                result["start_result"] = initial
        if args.command == "watchdog":
            print(json.dumps({**{key: result.get(key) for key in
                ("status", "reason", "completed", "task_count", "active_task_id", "completion_cleanup")},
                **{key: result[key] for key in ("unit", "timer_enabled") if key in result},
                "report_path": str(state / "watchdog" / "latest.json")}, sort_keys=True))
            return 2 if result.get("status") in {"error", "refused", "exhausted"} else 0
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2 if result.get("status") in {"not_ready", "board_error", "state_error", "identity_mismatch", "stop_incomplete",
            "monitor_refused", "monitor_window_consumed", "monitor_owner_changed", "monitor_source_changed",
            "monitor_owner_unknown", "monitor_stop_incomplete"} else 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2



def _source_freeze(root: Path, extra=()):
    """Bind tracked implementation inputs, explicit outputs and dependency heads.

    Generated board/status commits do not invalidate unchanged implementation
    inputs. Existing private/untracked user directories are never inventoried.
    """
    from .improvement_plan import _hash_file, _digest, _private_binding_path, _safe_relative
    result = subprocess.run(["git", "--no-optional-locks", "ls-files", "-z", "--stage"],
                            cwd=root, capture_output=True, check=True, timeout=20)
    files, dependencies = {}, {}
    for entry in result.stdout.decode().split("\0"):
        if not entry:
            continue
        metadata, relative = entry.split("\t", 1)
        if _private_binding_path(relative):
            continue
        mode, blob, stage = metadata.split()
        if stage != "0":
            raise ValueError("unmerged_source")
        path = root / relative
        if _safe_relative(root, relative) is None:
            raise ValueError("source_alias_forbidden")
        if mode == "160000":
            if not (path / ".git").exists():
                dependencies[relative] = {"gitlink": blob, "head": "unavailable"}
                continue
            head = subprocess.run(["git", "--no-optional-locks", "-C", str(path), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, timeout=10)
            dependencies[relative] = {"gitlink": blob, "head": head.stdout.strip() if head.returncode == 0 else "unavailable"}
        elif (Path(relative).suffix in {".py", ".sh", ".toml", ".ini", ".cfg", ".json"}
              and not relative.startswith(("docs/", "data/", "output/", "statefiles/", "exports/", ".complaint_workspace/"))):
            if path.is_symlink() or not path.is_file():
                raise ValueError("source_unavailable")
            files[relative] = {"sha256": _hash_file(path), "mode": stat.S_IMODE(path.stat().st_mode), "git_mode": mode}
    for relative in extra:
        if _private_binding_path(relative):
            raise ValueError("private_source_binding_forbidden")
        path = _safe_relative(root, relative)
        if path is None:
            raise ValueError("source_alias_forbidden")
        if path.is_file() and not (root / relative).is_symlink():
            files[relative] = {"sha256": _hash_file(path), "mode": stat.S_IMODE(path.stat().st_mode)}
        elif not path.is_dir():
            raise ValueError("missing_output")
    value = {"files": files, "dependencies": dependencies}
    return {**value, "digest": _digest(value)}


_PYTEST_INVOCATION_PATTERN = r"(?<![\w-])(?:python(?:3(?:\.\d+)*)?\s+-m\s+pytest|pytest)(?=\s|$)"


def _pytest_population_filtered(command):
    """Treat caller discovery controls as unknown whole-file coverage."""
    import shlex
    matches = list(re.finditer(_PYTEST_INVOCATION_PATTERN, command))
    if len(matches) != 1:
        return True
    # Exclude the Python interpreter's -m from pytest's marker filter.
    arguments = shlex.split(command[matches[0].end():])
    controls = {"--deselect", "--ignore", "--ignore-glob", "--lf", "--last-failed",
                "--lfnf", "--last-failed-no-failures", "--sw", "--stepwise",
                "--sw-skip", "--stepwise-skip", "--override-ini", "--config-file"}
    return any(argument.startswith(("-k", "-m", "-o", "-c"))
               or argument.partition("=")[0] in controls for argument in arguments)


def _pytest_instrument(command, arguments, *, pythonpath=()):
    # Keep the original shell/environment prefix and original selectors. This
    # adapter supports one explicit pytest invocation, not arbitrary scripts.
    pattern = _PYTEST_INVOCATION_PATTERN
    matches = list(re.finditer(pattern, command))
    if len(matches) != 1 or any(flag in command for flag in ("--junit", "--collect-only", "--complaint-evidence-path", " -p no:")):
        raise ValueError("unsupported_behavioral_command")
    end = matches[0].end()
    import shlex
    original_invocation = command[matches[0].start():end]
    executable = original_invocation.split()[0] if original_invocation != "pytest" else "python"
    # Do not let cwd precede the explicitly owned bootstrap directories. The
    # canonical Native Python launcher preserves this interpreter flag.
    invocation = executable + " -P -m pytest " + shlex.join(arguments)
    if pythonpath:
        # A retained task prefix may export its own PYTHONPATH. Bind the owned
        # plugin roots at the actual invocation, after that prefix, while
        # retaining declared roots and the native sealed Python shell seam.
        owned = os.pathsep.join(map(str, pythonpath))
        invocation = "PYTHONPATH=" + shlex.quote(owned) + ':"${PYTHONPATH-}" ' + invocation
    return command[:matches[0].start()] + invocation + command[end:]


def _read_catalog(path, *, repo_root=None):
    import duckdb
    from .improvement_plan import _hash_file, _private_binding_path
    with duckdb.connect(str(path), read_only=True) as database:
        nodes = database.execute("SELECT nodeid, seal, file_count, completion_authority FROM pytest_ast_seal").fetchall()
        files = database.execute("SELECT path, content_hash FROM pytest_ast_file_hash").fetchall()
    if len(nodes) > 20000 or len(files) > 20000:
        raise ValueError("catalog_population_unbounded")
    hashes = {str(p): str(h) for p, h in files}
    if repo_root is not None:
        for name in hashes:
            relative = Path(name).resolve().relative_to(repo_root) if Path(name).resolve().is_relative_to(repo_root) else None
            if relative is not None and _private_binding_path(relative.as_posix()):
                raise ValueError("private_source_binding_forbidden")
    if len(hashes) != len(files) or any(_hash_file(Path(p)) != h for p, h in hashes.items()):
        raise ValueError("stale_source_hash")
    if (len({n for n, _, _, _ in nodes}) != len(nodes) or
            any(not isinstance(n, str) or not n or not isinstance(seal, str) or re.fullmatch(r"[0-9a-f]{64}", seal) is None
                or type(count) is not int or not 0 < count <= len(hashes) or authority is not False
                for n, seal, count, authority in nodes)):
        raise ValueError("catalog_seal_invalid")
    return [n for n, _, _, _ in nodes], hashes


class _BehavioralDefinitionError(ValueError):
    """Keep the existing refusal while exposing finite repair locators only."""
    def __init__(self, issues):
        super().__init__("existing_behavioral_definition_changed")
        projected = []
        for issue in issues[:16]:
            path = issue["path"]
            safe_path = (isinstance(path, str) and len(path) <= 256
                and re.fullmatch(r"tests/[A-Za-z0-9_./-]+\.py", path) is not None
                and ".." not in Path(path).parts and Path(path).as_posix() == path)
            name = issue["definition"]
            safe_name = (isinstance(name, str) and len(name) <= 128
                and (not name or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", name) is not None))
            projected.append({"path": path if safe_path else "<unavailable>",
                "definition": name if safe_name else "<unavailable>",
                "change": issue["change"] if issue["change"] in {"changed", "missing", "duplicate",
                    "parse_failed", "source_unavailable", "invalid_path"} else "unavailable"})
        self.diagnostics = {"schema": "complaint-behavioral-definition-diagnostic@1",
            "reason": "existing_behavioral_definition_changed", "issues": projected,
            "truncated": len(issues) > 16, "candidate_executed": False, "completion_authority": False}


def _preserve_existing_behavioral_definitions(root: Path, paths, *, trusted_root: Path | None = None):
    """Keep installed test/helper definitions when a task adds behavioral checks.

    The installed operator source supplies the baseline, outside the provider
    checkout. This catches accidental replacement of earlier regression suites;
    an intentional semantic migration requires separately reviewed maintenance.
    Existing classes may gain methods while their earlier methods stay intact.
    """
    import ast
    import copy

    installed = trusted_root if trusted_root is not None else Path(__file__).resolve().parents[2]
    records = []
    relative = ""
    def fail(change, definition=""):
        raise _BehavioralDefinitionError([{"path": relative, "definition": definition, "change": change}])
    def definitions(body, prefix=()):
        rows = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = prefix + (node.name,)
                if key in rows:
                    fail("duplicate", ".".join(key))
                rows[key] = ast.dump(node, include_attributes=False)
            elif isinstance(node, ast.ClassDef):
                key = prefix + (node.name,)
                header = copy.deepcopy(node)
                header.body = []
                if key in rows:
                    fail("duplicate", ".".join(key))
                rows[key] = ast.dump(header, include_attributes=False)
                rows.update(definitions(node.body, key))
        return rows
    for relative in sorted(set(map(str, paths))):
        name = Path(relative)
        if not relative.startswith("tests/") or name.suffix != ".py":
            continue
        if name.is_absolute() or ".." in name.parts:
            fail("invalid_path")
        baseline, candidate = installed / name, Path(root) / name
        if not baseline.exists() and not baseline.is_symlink():
            continue
        try:
            for path in (baseline, candidate):
                if path.is_symlink() or path.resolve(strict=True) != path or not path.is_file():
                    fail("source_unavailable")
            original_bytes, candidate_bytes = baseline.read_bytes(), candidate.read_bytes()
            if original_bytes == candidate_bytes:
                # Some legacy modules repeat a Python definition name. Exact
                # source equality preserves every occurrence, including code
                # shadowed at import; changed ambiguous definitions still fail.
                def count_definitions(body):
                    return sum(1 + (count_definitions(node.body) if isinstance(node, ast.ClassDef) else 0)
                        for node in body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
                count = count_definitions(ast.parse(original_bytes).body)
                digest = hashlib.sha256(original_bytes).hexdigest()
                records.append({"path": relative, "trusted_sha256": digest, "candidate_sha256": digest,
                    "preserved_definition_count": count})
                continue
            original = definitions(ast.parse(original_bytes).body)
            current = definitions(ast.parse(candidate_bytes).body)
        except SyntaxError:
            fail("parse_failed")
        except (OSError, UnicodeError):
            fail("source_unavailable")
        issues = [{"path": relative, "definition": ".".join(name),
                   "change": "missing" if name not in current else "changed"}
                  for name, value in original.items() if current.get(name) != value]
        if issues:
            raise _BehavioralDefinitionError(issues)
        records.append({"path": relative, "trusted_sha256": hashlib.sha256(original_bytes).hexdigest(),
                        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
                        "preserved_definition_count": len(original)})
    return records


_PRIVATE_REPLICA_ACCEPTANCE = "tests/test_private_replica_acceptance.py"
_PRIVATE_REPLICA_CAPABILITY_NODE = _PRIVATE_REPLICA_ACCEPTANCE + "::test_replica_api_capability_is_explicit"


def _private_replica_host_file(path, *, limit, exact_mode=None):
    """Read an immutable host/operator file, never a provider success field."""
    import stat
    path = Path(path)
    if not path.is_absolute() or str(path.resolve()) != str(path):
        raise ValueError("private_replica_compatibility_unavailable")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or before.st_mode & 0o022
                or (exact_mode is not None and stat.S_IMODE(before.st_mode) != exact_mode)
                or not 0 < before.st_size <= limit):
            raise ValueError("private_replica_compatibility_unavailable")
        chunks, remaining = [], before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                raise ValueError("private_replica_compatibility_unavailable")
            chunks.append(chunk)
            remaining -= len(chunk)
        stable = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_uid,
                               item.st_gid, item.st_nlink, item.st_size,
                               item.st_mtime_ns, item.st_ctime_ns)
        if (os.read(descriptor, 1) or stable(os.fstat(descriptor)) != stable(before)
                or str(path.resolve()) != str(path) or stable(path.stat()) != stable(before)):
            raise ValueError("private_replica_compatibility_unavailable")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _private_replica_kit_qualification(root, evidence_state_dir, task, source, *, campaign_state_dir=None):
    """Require real separately measured Kit compatibility for exact DUR005.

    The 0600 binding is privileged operator configuration outside the provider
    checkout. Its reviewed pure verifier rederives the actual qualification and
    remaps current candidate Kit bytes, retaining measured origins separately.
    This function never runs Kit tests, a provider, a subprocess or Git.
    """
    if task.get("id") != "CIMP-DUR-005":
        return None
    import types
    try:
        if campaign_state_dir is None:
            raise ValueError("private_replica_compatibility_unavailable")
        campaign = Path(campaign_state_dir)
        if (not campaign.is_absolute() or str(campaign.resolve()) != str(campaign)
                or Path(evidence_state_dir) != campaign / "evidence-runs"):
            raise ValueError("private_replica_compatibility_unavailable")
        directory = campaign / "host-acceptance"
        if (directory.is_symlink() or str(directory.resolve()) != str(directory)
                or directory.stat().st_uid != os.getuid()
                or directory.stat().st_mode & 0o077):
            raise ValueError("private_replica_compatibility_unavailable")
        binding_path = directory / "private-replica-kit.json"
        binding_bytes = _private_replica_host_file(binding_path, limit=65536, exact_mode=0o600)
        binding = json.loads(binding_bytes)
        if (set(binding) != {"schema", "reader", "qualification"}
                or binding["schema"] != "complaint-private-replica-kit-host-binding@1"):
            raise ValueError("private_replica_compatibility_unavailable")
        loaded = {}
        for name, limit in (("reader", 65536), ("qualification", 64 * 1024 * 1024)):
            row = binding[name]
            if (not isinstance(row, dict) or set(row) != {"path", "sha256"}
                    or not isinstance(row["path"], str)
                    or not isinstance(row["sha256"], str)
                    or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None
                    or Path(row["path"]).is_relative_to(root)):
                raise ValueError("private_replica_compatibility_unavailable")
            loaded[name] = _private_replica_host_file(row["path"], limit=limit)
            if hashlib.sha256(loaded[name]).hexdigest() != row["sha256"]:
                raise ValueError("private_replica_compatibility_unavailable")
        head = source["dependencies"]["external/ipfs_kit_py"]["head"]
        if re.fullmatch(r"[0-9a-f]{40}", str(head)) is None:
            raise ValueError("private_replica_compatibility_unavailable")
        name = "_complaint_replica_kit_" + binding["reader"]["sha256"]
        module = types.ModuleType(name)
        module.__file__ = binding["reader"]["path"]
        previous = sys.modules.get(name)
        sys.modules[name] = module
        try:
            exec(compile(loaded["reader"], module.__file__, "exec"), module.__dict__)
            proof = module.prove_kit_qualification(
                binding["qualification"]["path"], binding["qualification"]["sha256"],
                Path(root) / "external/ipfs_kit_py", head)
        finally:
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        if (not isinstance(proof, dict)
                or proof.get("schema") != "complaint-kit-replica-compatibility-qualification@1"
                or proof.get("status") != "passed" or proof.get("kit_head") != head):
            raise ValueError("private_replica_compatibility_unavailable")
        # Detect a replacement during the pure reproof as well as at the later
        # post-measurement call. Raw pass flags never replace the pinned reader.
        for label, limit in (("reader", 65536), ("qualification", 64 * 1024 * 1024)):
            if _private_replica_host_file(binding[label]["path"], limit=limit) != loaded[label]:
                raise ValueError("private_replica_compatibility_unavailable")
        if _private_replica_host_file(binding_path, limit=65536, exact_mode=0o600) != binding_bytes:
            raise ValueError("private_replica_compatibility_unavailable")
        return {"binding": {"path": str(binding_path),
                            "sha256": hashlib.sha256(binding_bytes).hexdigest()},
                "reader": binding["reader"], "qualification": binding["qualification"],
                "kit_head": head, "current_kit_root": str(Path(root) / "external/ipfs_kit_py"),
                "execution_root": proof.get("execution_root"),
                "schema": proof["schema"], "separate_compatibility_evidence": True}
    except Exception:
        raise ValueError("private_replica_compatibility_unavailable") from None


def _private_replica_acceptance_binding(root, task, impacted):
    """Bind the provider checkout to the installed trusted companion bytes.

    The task plan and CID stay unchanged. An API-absent baseline may be
    characterized, but cannot satisfy the exact DUR005 task capability gate.
    """
    required = task.get("id") == "CIMP-DUR-005"
    if not required and _PRIVATE_REPLICA_ACCEPTANCE not in impacted:
        return None
    installed = Path(__file__).resolve().parents[2] / _PRIVATE_REPLICA_ACCEPTANCE
    candidate = Path(root) / _PRIVATE_REPLICA_ACCEPTANCE
    for path in (installed, candidate):
        if (path.is_symlink() or str(path.resolve()) != str(path)
                or not path.is_file() or path.stat().st_nlink != 1):
            raise ValueError("trusted_replica_acceptance_changed")
    trusted = hashlib.sha256(installed.read_bytes()).hexdigest()
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != trusted:
        raise ValueError("trusted_replica_acceptance_changed")
    return {"path": _PRIVATE_REPLICA_ACCEPTANCE, "trusted_path": str(installed),
            "candidate_path": str(candidate), "sha256": trusted,
            "required_supported": required}


def _private_replica_acceptance_capability(junit, binding):
    """Consume an actual measured JUnit property; no JSON success shortcuts."""
    if binding is None:
        return None
    matches = []
    for case in junit.iter("testcase"):
        properties = case.findall("properties/property")
        identities = [p.get("value") for p in properties if p.get("name") == "complaint_nodeid"]
        if identities == [_PRIVATE_REPLICA_CAPABILITY_NODE]:
            if any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
                raise ValueError("private_replica_capability_unavailable")
            matches.append([p.get("value") for p in properties
                            if p.get("name") == "private_replica_capability"])
    if len(matches) != 1 or matches[0] not in (["supported"], ["unsupported"]):
        raise ValueError("private_replica_capability_unavailable")
    capability = matches[0][0]
    if binding["required_supported"] and capability != "supported":
        raise ValueError("private_replica_capability_unavailable")
    return capability


_FACTUAL_CORRECTION_ACCEPTANCE = ("tests/test_cimp_ux_10.py::"
    "test_answer_and_correction_update_graphs_once_and_stale_replies_do_not")
_CASE_SWITCH_ACCEPTANCE = ("tests/test_cimp_ux_10.py::"
    "test_delayed_answer_cannot_repaint_a_new_selected_case")
_INTERVIEW_BEHAVIORAL_ACCEPTANCE = (_FACTUAL_CORRECTION_ACCEPTANCE, _CASE_SWITCH_ACCEPTANCE)


_IMPACTED_BEHAVIORAL_CHECKS = {
    "integrations/ipfs_datasets/legal.py": ("tests/test_explicit_legal_context.py", "tests/test_ipfs_adapter_layer.py"),
    "integrations/ipfs_datasets/storage.py": ("tests/test_private_storage_adapter.py", "tests/test_ipfs_kit_storage_adapter.py", "tests/test_proof_report_and_pinning.py", _PRIVATE_REPLICA_ACCEPTANCE),
    "integrations/private_storage.py": ("tests/test_private_workspace_crypto.py", "tests/test_private_workspace_keys.py", "tests/test_private_storage_adapter.py", _PRIVATE_REPLICA_ACCEPTANCE),
    "applications/complaint_workspace.py": ("tests/test_private_workspace_isolation.py", "tests/test_private_workspace_policy.py", "tests/test_private_workspace_keys.py", *_INTERVIEW_BEHAVIORAL_ACCEPTANCE),
    "static/complaint_conversation.js": _INTERVIEW_BEHAVIORAL_ACCEPTANCE,
    "static/complaint_mcp_sdk.js": _INTERVIEW_BEHAVIORAL_ACCEPTANCE,
    "integrations/ipfs_datasets/llm.py": ("tests/test_grok47_router_contract.py", "tests/test_private_workspace_policy.py"),
    "mediator/mediator.py": ("tests/test_factual_correction_replay.py", "tests/test_tui_shared_interview.py"),
}


def _impacted_behavioral_checks(root, changed_paths):
    selected = set()
    for changed in changed_paths:
        selected.update(_IMPACTED_BEHAVIORAL_CHECKS.get(changed, ()))
    if any(not (root / path.partition("::")[0]).is_file() for path in selected):
        raise ValueError("impacted_check_missing")
    return sorted(selected)


def measure_behavioral_command(root: Path, state_dir: Path, task: Mapping[str, Any], command: str, *,
                               runner, environment: dict, timeout_seconds: float = TIMEOUT_SECONDS,
                               context: Mapping[str, Any] | None = None, declared_command: str | None = None,
                               candidate_proposal=None, campaign_spec: Mapping[str, Any] | None = None):
    """Execute and measure an owned command; never accept serialized success.

    Independent collection freezes the required population. The actual command
    runs with explicit phase and native AST plugins, a fresh catalog and JUnit.
    The caller-provided runner must be the native sealed executor or a test seam
    which delegates it. This callback is trusted host code, not an untrusted
    remote or JSON input; a sealed marker is not callback authentication. The
    consumed native path supplies the original canonical executor.
    """
    import shlex
    import xml.etree.ElementTree as ET
    from types import SimpleNamespace
    from .improvement_plan import (_MeasuredEvidence, _MEASURED, _pin_measurement, _digest, _hash_file,
                                   bind_sources, SEALED_ENVIRONMENT_POLICY, _safe_relative)
    root, state_dir = Path(root).resolve(), Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    run = Path(tempfile.mkdtemp(prefix="measured-", dir=state_dir)); run.chmod(0o700)
    observation_command = declared_command or command
    contract = {"task": dict(task), "context": dict(context or {}), "command": command, "declared_command": observation_command}
    extra = _task_outputs(task)
    freeze_inputs = _task_freeze_inputs(task, context=context, spec=campaign_spec)
    start = time.monotonic()
    original_command = command
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native_source
    phase_relative = "integrations/ipfs_accelerate/improvement_plan.py"
    candidate_phase = root / phase_relative
    phase_source = (candidate_phase if candidate_phase.is_file() or candidate_phase.is_symlink()
                    else Path(__file__).resolve().parents[2] / phase_relative)
    phase_root = phase_source.parents[2]
    phase_source = _safe_relative(phase_root, phase_relative)
    if phase_source is None or not phase_source.is_file():
        raise ValueError("validation_bootstrap_source_unavailable")
    native_root = Path(native_source.__file__).resolve().parents[3]
    from . import validation_network as owned_network
    from . import python_global_preflight as owned_python_globals
    from . import browser_http_preflight as owned_browser_http
    from .validation_network import prepare_validation_network_guard, verify_validation_network_proof
    network_guard = prepare_validation_network_guard(run, Path(owned_network.__file__).resolve().parents[2])
    # This private, Host-created module precedes all candidate package roots.
    # -P above also removes Python's otherwise implicit cwd precedence.
    bootstrap_roots = tuple(dict.fromkeys((run, root, phase_root, native_root)))
    bootstrap_files = (phase_source, native_root / "ipfs_accelerate_py/__init__.py",
                       native_root / "ipfs_accelerate_py/testing/pytest_ast_seal.py",
                       *(Path(path) for path in network_guard["files"]),
                       Path(owned_python_globals.__file__).resolve(),
                       Path(owned_browser_http.__file__).resolve())
    bootstrap_before = {str(path): _hash_file(path) for path in bootstrap_files}
    impacted = _impacted_behavioral_checks(root, (context or {}).get("changed_paths", ()))
    if task.get("id") == "CIMP-DUR-005" and _PRIVATE_REPLICA_ACCEPTANCE not in impacted:
        impacted.append(_PRIVATE_REPLICA_ACCEPTANCE)
        impacted.sort()
    replica_binding = _private_replica_acceptance_binding(root, task, impacted)
    replica_capability = None
    replica_kit_before = None
    release_qualification_before = None
    release_qualification_after = None
    preserved_behavioral_definitions = None
    missing_impacted_checks = []
    filtered_whole_file_companions = []
    behavioral_definition_diagnostic = None
    python_global_preflight = None
    browser_http_preflight = None
    release_script = (task.get("id") == "CIMP-REL-03" and
        observation_command == "python scripts/validate_complaint_intake.py --phase pre-admission" and
        task.get("validation_commands") in (
            ["python scripts/validate_complaint_intake.py --phase pre-admission"],
            ["python -m pytest -q --run-llm --run-network --run-heavy tests/test_intake_release_gate.py",
             "python scripts/validate_complaint_intake.py --phase pre-admission"],
        ) and
        "tests/test_intake_release_gate.py" in extra and
        command.rstrip().endswith("python scripts/validate_complaint_intake.py --phase pre-admission"))
    before = _source_freeze(root, freeze_inputs)
    artifacts, results, network_proofs = [], [], []
    required, cases, imported = [], [], {}
    reason = ""
    infrastructure_reasons = {"validation_process_cleanup_unverified", "validation_output_limit_exceeded"}
    def invoke(specification, effective_environment, remaining):
        try:
            return _call_validation_with_activity(executor=runner, spec=specification,
                workspace_path=root, timeout_seconds=remaining, environment=effective_environment,
                task=task, context=context)
        except subprocess.TimeoutExpired as exc:
            # Native's public executor raises this after its own deadline.
            # Preserve only typed facts; output/argv do not prove cleanup.
            result = {"command": str(specification.command), "raw_command": str(specification.raw_command),
                      "returncode": 124, "timed_out": True, "error": "subprocess_timeout"}
            if getattr(exc, "process_tree_quiesced", None) is True:
                result["process_tree_quiesced"] = True
            else:
                # Legacy timeout exceptions do not prove descendant closure.
                # Preserve the deadline fact without classifying an uncertain
                # process tree as a clean timeout that recovery may retry.
                result.update(returncode=75, error="validation_process_cleanup_unverified",
                              infrastructure_failure=True, execution_deadline_exceeded=True)
                result.pop("timed_out")
            return result

    def reject_executor_failure(result):
        if result.get("infrastructure_failure") is True and result.get("error") in infrastructure_reasons:
            raise ValueError(result["error"])
        if result.get("timed_out") or result.get("error") == "subprocess_timeout":
            raise TimeoutError("subprocess_timeout")

    def execute(mode):
        catalog, manifest = run / (mode + ".duckdb"), run / (mode + ".json")
        junit = run / "junit.xml"
        options = ["-p", network_guard["module"]] + (["-p", str(context["pytest_guard_plugin"])] if (context or {}).get("pytest_guard_plugin") else []) + ["-p", "integrations.ipfs_accelerate.improvement_plan", "-p", "ipfs_accelerate_py.testing.pytest_ast_seal",
                   "--complaint-evidence-path=" + str(manifest)]
        options += ["--collect-only"] if mode == "collect" else ["--junitxml=" + str(junit), "-o", "junit_family=xunit2"]
        # A bounded companion may name one node. A declared whole-file run
        # already includes it; adding both would duplicate required nodeids.
        declared_tokens = shlex.split(command)
        options += [p for p in impacted if p not in declared_tokens
                    and p.partition("::")[0] not in declared_tokens]
        instrumented = _pytest_instrument(command, options, pythonpath=bootstrap_roots)
        export = "export IPFS_ACCELERATE_PYTEST_SEAL_DUCKDB=" + shlex.quote(str(catalog))
        # Never depend on ambient pytest injection or a shared/reused catalog.
        export += " PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS='' PYTEST_PLUGINS=''"
        instrumented = export + " && " + instrumented
        remaining = timeout_seconds - (time.monotonic() - start)
        if remaining <= 0:
            raise TimeoutError("subprocess_timeout")
        result = invoke(SimpleNamespace(command=instrumented, raw_command=command), environment, remaining)
        _atomic_json(run / (mode + "-native-result.json"), result)
        results.append({"mode": mode, "original_command": command, "instrumented_command": instrumented, "executed_command": result.get("command"),
                        "returncode": result.get("returncode"), "timed_out": bool(result.get("timed_out")),
                        "error": result.get("error"), "infrastructure_failure": result.get("infrastructure_failure") is True,
                        "process_tree_quiesced": result.get("process_tree_quiesced") is True,
                        "execution_deadline_exceeded": result.get("execution_deadline_exceeded") is True,
                        "validation_python_launcher": result.get("validation_python_launcher", {})})
        reject_executor_failure(result)
        if result.get("validation_python_launcher", {}).get("sealed") is not True:
            raise ValueError("sealed_execution_unavailable")
        network_path = manifest.with_suffix(network_guard["proof_suffix"])
        try:
            proof = verify_validation_network_proof(network_path,
                expected_plugin_sha256=network_guard["plugin_sha256"],
                expected_policy_sha256=network_guard["policy_sha256"],
                expected_exitstatus=result.get("returncode"))
        except (OSError, ValueError, TypeError, KeyError):
            raise ValueError("validation_network_guard_unavailable") from None
        network_proofs.append({"mode": mode, "path": str(network_path),
            "sha256": _hash_file(network_path), "proof": proof})
        artifacts.append({"path": str(network_path), "sha256": _hash_file(network_path)})
        if not manifest.is_file():
            raise ValueError("missing_phase_manifest")
        guard_path = manifest.with_suffix(".guard.json")
        if (context or {}).get("require_child_guard") or guard_path.is_file():
            guard = _read_json(guard_path)
            if guard.get("network_process_dispatch_permitted") is not False or guard.get("exitstatus") != result.get("returncode"):
                raise ValueError("nested_fixture_guard_unavailable")
            artifacts.append({"path": str(guard_path), "sha256": _hash_file(guard_path)})
        observation = _read_json(manifest, limit=20_000_000)
        if observation.get("exitstatus") != result.get("returncode"):
            raise ValueError("exit_status_mismatch")
        for path in (manifest, catalog, run / (mode + "-native-result.json"), *([junit] if mode == "run" else [])):
            if not path.is_file():
                raise ValueError("missing_output")
            artifacts.append({"path": str(path), "sha256": _hash_file(path)})
        return result, observation, _read_catalog(catalog, repo_root=root)
    try:
        browser_http_preflight = owned_browser_http.inspect_complaint_browser_http(
            root, task, observation_command, campaign_spec=campaign_spec)
        if browser_http_preflight is not None:
            # Only an applicable preflight that read the immutable bytes adds
            # this campaign's spec to the Host bootstrap freeze. Other Native
            # campaigns do not depend on availability of the UX specification.
            if browser_http_preflight.get("spec_sha256") == owned_browser_http.SPEC_SHA256:
                browser_spec = owned_browser_http._SOURCE_ROOT / owned_browser_http.SPEC_RELATIVE
                try:
                    browser_spec_hash = _hash_file(browser_spec)
                except OSError:
                    browser_spec_hash = ""
                if browser_spec_hash != owned_browser_http.SPEC_SHA256:
                    browser_http_preflight.update(passed=False, reason="browser_http_preflight_unavailable")
                else:
                    bootstrap_files = (*bootstrap_files, browser_spec)
                    bootstrap_before[str(browser_spec)] = browser_spec_hash
            browser_preflight_path = run / "browser-http-preflight.json"
            _atomic_json(browser_preflight_path, browser_http_preflight)
            artifacts.append({"path": str(browser_preflight_path), "sha256": _hash_file(browser_preflight_path)})
            if browser_http_preflight.get("passed") is not True:
                raise ValueError(browser_http_preflight["reason"])
        if (context or {}).get("require_python_global_preflight") is True:
            python_global_preflight = owned_python_globals.inspect_changed_python_globals(
                root, candidate_proposal, expected_task_id=task["id"])
            preflight_path = run / "python-global-preflight.json"
            _atomic_json(preflight_path, python_global_preflight)
            artifacts.append({"path": str(preflight_path), "sha256": _hash_file(preflight_path)})
            if python_global_preflight.get("passed") is not True:
                raise ValueError(python_global_preflight["reason"])
        preserved_behavioral_definitions = _preserve_existing_behavioral_definitions(
            root, [*extra, *(p.partition("::")[0] for p in impacted),
                   *(context or {}).get("changed_paths", ())])
        replica_kit_before = _private_replica_kit_qualification(root, state_dir, task, before,
            campaign_state_dir=(context or {}).get("campaign_state_dir"))
        if release_script:
            if time.monotonic() - start >= timeout_seconds:
                raise TimeoutError("subprocess_timeout")
            release_environment = dict(environment)
            if (context or {}).get("campaign_state_dir"):
                # The trusted parent supplies locators, never completion data.
                campaign = Path(context["campaign_state_dir"])
                target = Path(context.get("target_source_root") or Path(__file__).resolve().parents[2])
                if (not campaign.is_absolute() or campaign.resolve() != campaign
                        or campaign.stat().st_uid != os.getuid() or stat.S_IMODE(campaign.stat().st_mode) != 0o700
                        or not target.is_absolute() or target.resolve() != target):
                    raise ValueError("release_context_unavailable")
                from .improvement_plan import SPEC_RELATIVE as release_spec_relative
                launch = _read_json(campaign / "launcher.json")
                if (not _full_launch_record(launch)
                        or not _campaign_tuple_matches(launch, target, target / release_spec_relative, campaign)):
                    raise ValueError("release_context_unavailable")
                release_environment["COMPLAINT_INTAKE_RELEASE_CAMPAIGN_STATE_DIR"] = str(campaign)
                release_environment["COMPLAINT_INTAKE_RELEASE_TARGET_SOURCE_ROOT"] = str(target)
                # Native owns and removes its temporary HOME after execution.
                # Keep nested proof under this already private measured run.
                release_runtime = run / "release-runtime"
                release_runtime.mkdir(mode=0o700)
                release_environment["COMPLAINT_INTAKE_RELEASE_RUNTIME_DIR"] = str(release_runtime)
                from .release_evidence import read_current_release_qualification
                release_qualification_before = read_current_release_qualification(
                    root, root / release_spec_relative, campaign, phase="pre-admission",
                    validation_environment=environment)
            original = invoke(SimpleNamespace(command=original_command, raw_command=original_command),
                release_environment, max(0.001, timeout_seconds - (time.monotonic() - start)))
            _atomic_json(run / "declared-script-result.json", original)
            artifacts.append({"path": str(run / "declared-script-result.json"), "sha256": _hash_file(run / "declared-script-result.json")})
            results.append({"mode": "declared_script", "original_command": original_command,
                "instrumented_command": original_command, "returncode": original.get("returncode"),
                "timed_out": bool(original.get("timed_out")), "error": original.get("error"),
                "infrastructure_failure": original.get("infrastructure_failure") is True,
                "process_tree_quiesced": original.get("process_tree_quiesced") is True,
                "execution_deadline_exceeded": original.get("execution_deadline_exceeded") is True,
                "validation_python_launcher": original.get("validation_python_launcher", {})})
            if (context or {}).get("campaign_state_dir"):
                release_qualification_after = read_current_release_qualification(
                    root, root / release_spec_relative, campaign, phase="pre-admission",
                    validation_environment=environment)
                if release_qualification_before != release_qualification_after:
                    raise ValueError("release_current_qualification_changed")
            reject_executor_failure(original)
            if original.get("validation_python_launcher", {}).get("sealed") is not True:
                raise ValueError("sealed_execution_unavailable")
            if original.get("returncode") != 0:
                raise ValueError("declared_command_failed")
            command = command[:-len("python scripts/validate_complaint_intake.py --phase pre-admission")] + "python -m pytest -q --run-llm --run-network --run-heavy tests/test_intake_release_gate.py"
        collected_result, collection, (_, collected_hashes) = execute("collect")
        required = collection.get("nodeids", [])
        if collected_result.get("returncode") != 0:
            raise ValueError("collection_failed")
        if not required:
            raise ValueError("zero_test_collection")
        if len(required) != len(set(required)) or any(not isinstance(n, str) or not n for n in required):
            raise ValueError("required_test_identity_malformed")
        # Caller filters and candidate collection hooks may omit a trusted
        # companion even when its file was already declared. Require its
        # actual frozen population before executing a passing subset.
        missing_impacted_checks = [selector for selector in impacted if not any(
            node == selector or node.startswith(selector + ("[" if "::" in selector else "::"))
            for node in required)]
        whole_files = [selector for selector in impacted if "::" not in selector]
        if whole_files and _pytest_population_filtered(command):
            # One retained test does not prove a whole companion file ran.
            # Fail closed instead of collecting its unfiltered matrix again.
            filtered_whole_file_companions = whole_files
            missing_impacted_checks = sorted(set(missing_impacted_checks) | set(whole_files))
        if missing_impacted_checks:
            raise ValueError("impacted_required_case_missing")
        if before != _source_freeze(root, freeze_inputs):
            raise ValueError("stale_source_hash")
        executed, phases, (sealed_nodes, imported) = execute("run")
        if required != phases.get("nodeids"):
            raise ValueError("collection_identity_mismatch")
        by_node = {}
        for row in phases.get("reports", []):
            by_node.setdefault(row["nodeid"], []).append(row)
        for node in required:
            reports = by_node.get(node, [])
            outcomes = [r.get("outcome") for r in reports]
            outcome = "skipped" if "skipped" in outcomes else "failed" if "failed" in outcomes else "passed"
            cases.append({"nodeid": node, "outcome": outcome})
            if outcome == "skipped":
                raise ValueError("skipped_required_case")
            if outcome == "failed":
                raise ValueError("failed_assertion")
            if sorted(r.get("when") for r in reports) != ["call", "setup", "teardown"]:
                raise ValueError("missing_required_case_phase")
        if set(by_node) != set(required) or executed.get("returncode") != 0:
            raise ValueError("failed_assertion")
        junit_nodes = []
        junit_document = ET.parse(run / "junit.xml")
        replica_capability = _private_replica_acceptance_capability(junit_document, replica_binding)
        for case in junit_document.iter("testcase"):
            identity = [p.get("value") for p in case.findall("properties/property") if p.get("name") == "complaint_nodeid"]
            if len(identity) != 1 or any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
                raise ValueError("junit_required_case_mismatch")
            junit_nodes.extend(identity)
        if len(junit_nodes) != len(required) or set(junit_nodes) != set(required):
            raise ValueError("junit_required_case_mismatch")
        if len(sealed_nodes) != len(required) or set(sealed_nodes) != set(required):
            raise ValueError("missing_current_ast_seal")
        if any(imported.get(p) != h for p, h in collected_hashes.items()):
            raise ValueError("stale_source_hash")
    except (OSError, ValueError, TypeError, KeyError, TimeoutError) as exc:
        if isinstance(exc, _BehavioralDefinitionError):
            behavioral_definition_diagnostic = exc.diagnostics
        reason = str(exc) if str(exc) in {"declared_command_failed", "zero_test_collection", "collection_failed", "required_test_identity_malformed", "impacted_required_case_missing", "collection_identity_mismatch", "subprocess_timeout", "missing_output", "missing_phase_manifest", "missing_required_case_phase", "sealed_execution_unavailable", "exit_status_mismatch", "stale_source_hash", "skipped_required_case", "failed_assertion", "junit_required_case_mismatch", "missing_current_ast_seal", "unsupported_behavioral_command", "trusted_replica_acceptance_changed", "private_replica_capability_unavailable", "private_replica_compatibility_unavailable", "existing_behavioral_definition_changed", "release_context_unavailable", "release_current_qualification_changed", "validation_network_guard_unavailable", "new_duplicate_python_module_global", "python_global_preflight_unavailable", "synthetic_browser_http_response", "browser_http_preflight_unavailable", *infrastructure_reasons} else "host_measurement_unavailable"
    try:
        if replica_binding != _private_replica_acceptance_binding(root, task, impacted):
            reason = "trusted_replica_acceptance_changed"
    except (OSError, ValueError):
        reason = "trusted_replica_acceptance_changed"
    after = _source_freeze(root, freeze_inputs)
    try:
        replica_kit_after = _private_replica_kit_qualification(root, state_dir, task, after,
            campaign_state_dir=(context or {}).get("campaign_state_dir"))
        if replica_kit_after != replica_kit_before:
            reason = "private_replica_compatibility_unavailable"
    except ValueError:
        reason = "private_replica_compatibility_unavailable"
    bootstrap_after = {str(path): _hash_file(path) for path in bootstrap_files}
    if before != after or bootstrap_before != bootstrap_after:
        reason = "stale_source_hash"
    imported.update(bootstrap_before)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    measured = {"schema": "complaint-owned-behavioral-measurement@1", "reason": reason,
                "infrastructure_failure": any(row.get("infrastructure_failure") is True for row in results),
                "preserved_behavioral_definitions": preserved_behavioral_definitions,
                "missing_impacted_checks": missing_impacted_checks,
                "filtered_whole_file_companions": filtered_whole_file_companions,
                "behavioral_definition_diagnostic": behavioral_definition_diagnostic,
                "python_global_preflight": python_global_preflight,
                "browser_http_preflight": browser_http_preflight,
                "trusted_executor": {"module": str(getattr(runner, "__module__", "")), "qualname": str(getattr(runner, "__qualname__", "")),
                    "canonical_native_identity": runner is PortalImplementationDaemon._validation_command_runner,
                    "boundary": "trusted host code; returned sealed marker alone does not authenticate arbitrary callbacks"},
                "required_nodeids": required, "cases": cases, "source_before": before, "source_after": after,
                "source_unchanged": before == after and bootstrap_before == bootstrap_after, "imported_sources": imported,
                "validation_bootstrap": {"pythonpath_roots": list(map(str, bootstrap_roots)),
                                         "before": bootstrap_before, "after": bootstrap_after},
                "kernel_network_guard": {"policy": network_guard["policy"],
                    "policy_sha256": network_guard["policy_sha256"],
                    "plugin_sha256": network_guard["plugin_sha256"],
                    "proofs": network_proofs, "validation_children_only": True},
                "task_contract_digest": _digest(contract), "results": results, "artifacts": artifacts,
                "completion_authority": False, "run_path": str(run),
                "lane_basis": "native_host_validation", "live_node_verified": False, "impacted_checks": impacted,
                "behavioral_companion": "tests/test_intake_release_gate.py" if release_script else None,
                "current_release_qualification": ({
                    "before_after_equal": release_qualification_before == release_qualification_after,
                    "host_binding": release_qualification_before.get("host_binding"),
                    "qualification": release_qualification_before.get("qualification"),
                    "producer": release_qualification_before.get("producer"),
                    "source_identity": release_qualification_before.get("source_identity"),
                    "required_case_count": release_qualification_before.get("required_case_count"),
                    "completion_authority": False,
                } if release_qualification_before is not None else None),
                "private_replica_acceptance": {"binding": replica_binding, "capability": replica_capability,
                                               "kit_compatibility": replica_kit_before},
                "environment_policy": {"effective_PATH": environment.get("PATH"), "python": environment.get("IPFS_ACCELERATE_VALIDATION_PYTHON_EXECUTABLE"),
                    "HOME": "fresh private native command directory; not operator home", "ambient_pytest_injection": False}}
    measured["workspace_path"] = str(root)
    measured["output_paths"] = extra
    if freeze_inputs != extra:
        measured["freeze_inputs"] = freeze_inputs
    artifact_rows = [{"relative_path": os.path.relpath(a["path"], root), "path": a["path"],
                      "present": True, "sha256": a["sha256"]} for a in artifacts]
    # These environment fields describe native policy, not access to the real home.
    observed_environment = {**SEALED_ENVIRONMENT_POLICY, "HOME": "native-managed-fresh-private-home"}
    measured["observation_binding"] = {"command": observation_command, "collected_count": len(required),
        "required_nodeids": required, "cases": cases, "source_binding": bind_sources(root, extra),
        "exit_status": 0 if not reason else 1, "timed_out": reason == "subprocess_timeout",
        "lane": "local_node_integration", "artifacts": artifact_rows, "environment": observed_environment}
    _atomic_json(run / "measurement.json", measured)
    observed = _MeasuredEvidence({"lane": "local_node_integration", "command": observation_command,
            "exit_status": 0 if not reason else 1, "timed_out": reason == "subprocess_timeout",
            "collected_count": len(required), "cases": cases, "required_nodeids": required,
            "environment": observed_environment, "source_binding": bind_sources(root, extra),
            "artifacts": artifact_rows, "host_measurement": measured, "host_task_contract": contract}, capability=_MEASURED)
    _pin_measurement(observed, run / "measurement.json", _hash_file(run / "measurement.json"))
    result_path = next((run / name for name in ("run-native-result.json", "collect-native-result.json", "declared-script-result.json") if (run / name).is_file()), run / "unavailable")
    observed.native_result = _read_json(result_path, limit=20_000_000)
    return observed


class EvidenceValidationScheduler:
    """Native scheduler decorator: preserve proposal/impact binding and sole loop."""
    def __init__(self, native_scheduler, *, state_dir, spec, defer_readiness=False):
        self.native_scheduler = native_scheduler
        self.state_dir, self.spec = Path(state_dir), spec
        self.defer_readiness = bool(defer_readiness)
        self.bound_task = None

    def bind_task(self, task, workspace):
        self.bound_task = (task, Path(workspace).resolve())
        return {}  # native proof_workflow has no invented proof/fallback options

    def _run(self, method, *args, **kwargs):
        from dataclasses import replace
        from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import sealed_validation_python_runner
        if self.bound_task is None or self.bound_task[1] != Path(kwargs["workspace_path"]).resolve():
            return {"attempted": False, "passed": False, "returncode": 78, "results": [], "reason": "task_evidence_binding_missing"}
        native_task, root = self.bound_task
        task = next((t for t in self.spec["tasks"] if t["id"] == native_task.task_id), None)
        if task is None:
            return {"attempted": False, "passed": False, "returncode": 78, "results": [], "reason": "task_evidence_contract_missing"}
        delegate = kwargs.get("runner")
        receipts = []
        @sealed_validation_python_runner
        def measured_runner(*, spec, workspace_path, timeout_seconds, environment):
            observed = measure_behavioral_command(root, self.state_dir / "evidence-runs", task, str(spec.command),
                runner=delegate, environment=environment, timeout_seconds=timeout_seconds,
                declared_command=task["validation_commands"][spec.ordinal] if spec.ordinal < len(task["validation_commands"]) else None,
                candidate_proposal=args[0] if method == "run_validated" else None,
                campaign_spec=self.spec,
                context={"require_python_global_preflight": method == "run_validated",
                         "campaign_state_dir": str(self.state_dir.resolve()),
                         "target_source_root": str(Path(__file__).resolve().parents[2]),
                         "task_id": native_task.task_id, "task_cid": str(getattr(native_task, "canonical_task_cid", "")),
                         "task_key": str(getattr(native_task, "canonical_task_key", "")),
                         "proposal_id": str(getattr(getattr(args[0], "proposal", None), "proposal_id", "")) if method == "run_validated" else "",
                         "proposal_context_id": str(getattr(getattr(args[0], "proposal", None), "context_id", "")) if method == "run_validated" else "",
                         "proposal_replay_nonce_sha256": hashlib.sha256(str(getattr(getattr(args[0], "proposal", None), "replay_nonce", "")).encode()).hexdigest() if method == "run_validated" else "",
                         "changed_paths": list(getattr(getattr(args[0], "proposal", None), "changed_paths", ())) if method == "run_validated" else [],
                         "attempt_ordinal": None, "attempt_binding_status": "ordinal_unavailable_from_public_task_hook; native_proposal_context_retained",
                         "repository_tree_id": str(getattr(getattr(args[0], "proposal", None), "repository_tree_id", "")) if method == "run_validated" else "",
                         **({"campaign_spec_relative": campaign_artifacts(self.spec).spec_relative}
                            if "campaign" in self.spec else {}),
                         "model_policy": {"model": MODEL, "fallback": False}})
            receipt = gate_task_completion(root, self.state_dir, task, observed,
                legal_data_version=observed["host_measurement"]["source_before"]["dependencies"].get("external/ipfs_datasets_py", {}).get("head", "unavailable"))
            receipts.append(receipt)
            result = dict(observed.native_result)
            failure_reason = str(receipt.get("reason") or "")
            rejected_status = 78
            if failure_reason == "subprocess_timeout" and result.get("timed_out") is True:
                rejected_status = 124
            elif (failure_reason in {"validation_process_cleanup_unverified", "validation_output_limit_exceeded"}
                    and result.get("infrastructure_failure") is True and result.get("error") == failure_reason):
                rejected_status = 75
            if not receipt["admitted"] and rejected_status == 78:
                # A stronger source/policy refusal must not become an
                # environment retry just because the raw command timed out.
                # The owned measurement retains the executor's original facts.
                result["native_executor_failure"] = {key: result[key] for key in
                    ("returncode", "error", "timed_out", "infrastructure_failure",
                     "process_tree_quiesced", "execution_deadline_exceeded") if key in result}
                result.update(timed_out=False, infrastructure_failure=False,
                              error=failure_reason or "current_behavioral_evidence_required")
            if failure_reason in {"new_duplicate_python_module_global", "python_global_preflight_unavailable"}:
                detail = observed["host_measurement"].get("python_global_preflight") or {}
                result["output"] = "Host Python global preflight: " + json.dumps(detail, sort_keys=True)[:8192]
                result["preflight_only"] = True
            if failure_reason == "existing_behavioral_definition_changed":
                detail = observed["host_measurement"].get("behavioral_definition_diagnostic") or {}
                result["output"] = "Host behavioral definition guard: " + json.dumps(detail, sort_keys=True)[:8192]
                result["preflight_only"] = True
            if failure_reason in {"synthetic_browser_http_response", "browser_http_preflight_unavailable"}:
                detail = observed["host_measurement"].get("browser_http_preflight") or {}
                result["output"] = "Host complaint browser HTTP preflight: " + json.dumps(detail, sort_keys=True)[:8192]
                result["preflight_only"] = True
            result.update(command=str(spec.command), raw_command=str(spec.raw_command or spec.command),
                          returncode=0 if receipt["admitted"] else rejected_status, behavioral_evidence=receipt)
            return result
        kwargs["runner"] = measured_runner
        # A previous cached return code cannot stand in for current measured cases.
        command_index = 1 if method == "run_validated" else 0
        mutable = list(args)
        from ipfs_accelerate_py.agent_supervisor.validation.validation_commands import build_validation_commands
        mutable[command_index] = tuple(replace(c, cacheable=False) for c in build_validation_commands(mutable[command_index]))
        result = getattr(self.native_scheduler, method)(*mutable, **kwargs)
        if result.get("passed") and (not receipts or any(not r["admitted"] for r in receipts)):
            result.update(passed=False, returncode=78, reason="current_behavioral_evidence_required",
                          merge_eligible=False, completion_authoritative=False, authoritative=False)
        result["behavioral_evidence"] = receipts
        result["firstparty_completion_authority"] = False
        if self.defer_readiness:
            # This full-campaign observation can scan every previous evidence
            # receipt. Keep it outside Native's current validation deadline;
            # current measured admission and Native dependency checks already
            # govern this result. Explicit standalone observations retain the
            # synchronous behavior through the default constructor option.
            result["dependent_readiness"] = {
                "available": False, "reason": "deferred_outside_validation",
                "native_scheduling_enforced": False, "completion_authority": False,
            }
            return result
        from .improvement_plan import canonical_model_policy
        try:
            dependency = _source_freeze(root).get("dependencies", {}).get("external/ipfs_datasets_py", {})
            legal_version = dependency.get("head") or dependency.get("gitlink") or "unavailable"
            result["dependent_readiness"] = recompute_dependent_readiness(
                root, self.state_dir, self.spec, model_policy=canonical_model_policy(), legal_data_version=legal_version)
        except Exception:
            # Advisory observation must not replace native validation results;
            # cancellation/SystemExit remain outside this ordinary-exception fence.
            result["dependent_readiness"] = {"available": False, "reason": "advisory_observation_unavailable",
                "native_scheduling_enforced": False, "completion_authority": False}
        return result

    def run(self, *args, **kwargs):
        return self._run("run", *args, **kwargs)

    def run_validated(self, *args, **kwargs):
        return self._run("run_validated", *args, **kwargs)

def _run_evidence_daemon_adapter(argv, *, repo_root, validation_scheduler, proof_workflow=None):
    import signal
    import threading
    from pathlib import Path
    from ipfs_accelerate_py.agent_supervisor.runtime.process_security import harden_state_authority_process
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon_runner import (
        ImplementationDaemonRunContext, implementation_state_paths,
        configure_daemon_logging, apply_merge_resolver_environment,
        run_portal_implementation_daemon_loop,
    )
    harden_state_authority_process()
    args = native.parse_args(list(argv))
    if validation_scheduler is None:
        raise ValueError("behavioral_evidence_scheduler_unavailable")
    # This adapter owns the ordinary Markdown route only. Do not demote any
    # richer authority mode or discard a requested maintenance operation.
    if (str(getattr(args, 'authority_mode', '') or '') not in {'', 'legacy_markdown'}
            or str(getattr(args, 'task_source_kind', '') or '') not in {'', 'legacy-markdown'}):
        raise ValueError("unsupported_evidence_daemon_authority")
    forbidden = (
        'database_path', 'coordination_path', 'quack_endpoint', 'owner_session_id',
        'state_owner_client_id', 'task_context_bundle_artifact', 'task_context_bundle_sha256',
        'production_provider_policy', 'production_provider_launch_authority_receipt_path',
        'production_provider_launch_authority_receipt_content_id',
        'manual_completion_authority_task_id', 'manual_completion_authority_required_task_id',
        'manual_completion_authority_epoch_id', 'manual_completion_authority_revalidation_only',
        'reset_manual_completion_authority_renewal_task_id', 'clear_protected_path_incident',
        'approve_protected_path_commit', 'operator_clearance_note',
        'approve_disposed_ephemeral_workspace', 'accepted_control_plane_pin_json',
        'configured_board_live_admission_json', 'plan_bound_revision_cid',
    )
    if any(getattr(args, name, None) for name in forbidden):
        raise ValueError("unsupported_evidence_daemon_authority")
    if int(getattr(args, 'state_owner_bootstrap_fd', -1)) != -1:
        raise ValueError("unsupported_evidence_daemon_owner_bootstrap")
    resource_worktrees = args.worktree_root or args.state_dir / "worktrees"
    resource_environment = dict(os.environ)
    _require_resource_capacity(Path(repo_root), args.state_dir, resource_worktrees,
                               resource_environment, stage="before_native_daemon")
    configure_daemon_logging(args)
    apply_merge_resolver_environment(args)
    # Preserve nativeA main's exact49 argument expressions. In particular this
    # includes validation workers/budget, generated paths, reservations, source
    # root expectations, slices, worktree/merge scope and all custody options.
    REPO_ROOT = Path(repo_root).resolve()
    from .docker_isolation_capacity import capacity_isolating_daemon
    daemon = capacity_isolating_daemon(native.PortalImplementationDaemon)(
        assumed_completed_task_ids=args.assume_completed_task_id,
        board_namespace=str(getattr(args, "board_namespace", "") or ""),
        events_path=args.state_dir / f"{args.state_prefix}_events.jsonl",
        execution_slice_task_cids=args.execution_slice_task_cid,
        execution_slice_task_ids=args.execution_slice_task_id,
        expected_task_source_repository_root_id=args.expected_task_source_repository_root,
        expected_task_source_root_id=args.expected_task_source_root,
        external_reservation_manifest_paths=args.external_reservation_manifest_path,
        generated_status_paths=args.generated_status_path,
        idle_lane_work_stealing=args.idle_lane_work_stealing,
        implement=args.implement,
        implementation_command=args.implementation_command or None,
        implementation_protected_paths=args.implementation_protected_path,
        implementation_timeout=args.implementation_timeout,
        llm_merge_resolver_command=args.llm_merge_resolver_command or None,
        llm_merge_resolver_timeout_seconds=args.llm_merge_resolver_timeout_seconds,
        maintenance_interval_seconds=args.maintenance_interval_seconds,
        manual_completion_authority_epoch_id=args.manual_completion_authority_epoch_id,
        manual_completion_authority_required_task_ids=args.manual_completion_authority_required_task_id,
        manual_completion_authority_revalidation_only=args.manual_completion_authority_revalidation_only,
        manual_completion_authority_task_ids=args.manual_completion_authority_task_id,
        max_task_attempts=args.max_task_attempts,
        merge_queue_dir=args.merge_queue_dir,
        merge_reconciliation_max_merges=args.merge_reconciliation_max_merges,
        merge_target_branch=args.merge_target_branch,
        merged_worktree_cleanup_max=args.merged_worktree_cleanup_max,
        objective_bundle_dir=args.objective_bundle_dir,
        objective_path=args.objective_path,
        production_provider_context_budget_tokens=args.production_provider_context_budget_tokens,
        production_provider_launch_authority_receipt_content_id=args.production_provider_launch_authority_receipt_content_id,
        production_provider_launch_authority_receipt_path=args.production_provider_launch_authority_receipt_path,
        production_provider_policy=args.production_provider_policy,
        production_provider_review_authority_key_path=args.production_provider_review_authority_key_path,
        production_provider_timeout_seconds=args.production_provider_timeout_seconds,
        repo_root=REPO_ROOT,
        state_path=args.state_dir / f"{args.state_prefix}_task_state.json",
        strategy_path=args.state_dir / f"{args.state_prefix}_strategy.json",
        strict_task_sharding=args.strict_task_sharding,
        task_header_prefix=args.task_prefix,
        task_shard_count=args.task_shard_count,
        task_shard_index=args.task_shard_index,
        task_source=args.todo_path
                            if args.task_source_kind in {"markdown", "duckdb"}
                            else None,
        task_source_kind=args.task_source_kind
                            if args.task_source_kind in {"markdown", "duckdb"}
                            else "",
        todo_path=args.todo_path,
        use_ephemeral_worktree=args.implement and not args.no_ephemeral_worktree,
        validation_max_workers=args.validation_max_workers,
        validation_resource_budget=args.validation_resource_budget,
        worktree_root=args.worktree_root,
        worktree_submodule_paths=args.worktree_submodule_path or None,
        validation_scheduler=validation_scheduler,
        proof_workflow=proof_workflow,
    )
    context = ImplementationDaemonRunContext(parsed=args, **implementation_state_paths(args))
    handlers_installed = threading.current_thread() is threading.main_thread()
    previous_term = previous_int = None
    def request_stop(signum, _frame):
        raise SystemExit(128 + signum)
    if handlers_installed:
        previous_term = signal.signal(signal.SIGTERM, request_stop)
        previous_int = signal.signal(signal.SIGINT, request_stop)
    try:
        # The public native loop owns run_once, bounded wait and event close.
        return run_portal_implementation_daemon_loop(daemon, context, logger=native.logger,
            hooks=(_resource_admission_hook(REPO_ROOT, args.state_dir, resource_worktrees, resource_environment),))
    finally:
        if handlers_installed:
            signal.signal(signal.SIGTERM, previous_term)
            signal.signal(signal.SIGINT, previous_int)


def evidence_daemon_main(argv):
    root = Path(__file__).resolve().parents[2]
    _native_modules(root)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler
    args = native.parse_args(list(argv))
    scheduler = EvidenceValidationScheduler(ValidationScheduler(max_workers=args.validation_max_workers,
        resource_budget=args.validation_resource_budget, default_timeout_seconds=args.implementation_timeout),
        state_dir=args.state_dir, spec=_native_campaign_spec(root, args.state_dir,
            todo_path=args.todo_path, board_namespace=getattr(args, "board_namespace", None)), defer_readiness=True)
    return _run_evidence_daemon_adapter(argv, repo_root=root, validation_scheduler=scheduler, proof_workflow=scheduler.bind_task)


if __name__ == "__main__":
    # The native supervisor executes its public daemon_script_path directly.
    raise SystemExit(evidence_daemon_main(sys.argv[1:]) if "--todo-path" in sys.argv[1:] else main())
