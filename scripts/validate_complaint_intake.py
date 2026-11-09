#!/usr/bin/env python3
"""Read genuine Native history and measure the current offline release closure.

This checker has no task-completion authority. Historical callbacks and fresh
source qualification are separate inputs. The committed admission document is
an immutable source contract; measurements and the final audit live elsewhere.
The module is also the explicit first pytest plugin for its owned children.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import hashlib
from importlib.machinery import SourceFileLoader
import json
import multiprocessing
import os
import platform
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "complaint-intake-release-check@2"
REPORT_SCHEMA = "complaint-intake-release-admission-report@1"
RUNTIME_SCHEMA = "complaint-intake-release-post-completion@2"
SELF_TASK = "CIMP-REL-03"
SPEC_RELATIVE = "docs/task_boards/complaint_intake_improvement_spec.json"
REPORT_RELATIVE = "docs/task_boards/complaint_intake_completion.json"
SCRIPT_RELATIVE = "scripts/validate_complaint_intake.py"
GATE_RELATIVE = "tests/test_intake_release_gate.py"
BRIDGE_RELATIVE = "integrations/ipfs_accelerate/release_evidence.py"
GUARD_RELATIVE = "integrations/ipfs_accelerate/release_guard.py"
PUBLIC_RELATIVE = "tests/test_intake_public_release_journeys.py"
LOGIC_RELATIVE = "integrations/ipfs_datasets/logic.py"
HASH_SCOPE = "tracked_implementation_and_release_sources_excluding_report; deployed_A_Data_Kit_heads_exact; undeployed_opaque_gitlink_identities_only"
BOUND_SOURCE_PATHS = (SCRIPT_RELATIVE, GATE_RELATIVE, BRIDGE_RELATIVE, GUARD_RELATIVE, PUBLIC_RELATIVE, LOGIC_RELATIVE,
                      SPEC_RELATIVE, "integrations/ipfs_accelerate/improvement_runner.py",
                      "tests/test_release_evidence_bridge.py")
TOTAL_BUDGET_SECONDS = 900
SUITE_TIMEOUT_SECONDS = TOTAL_BUDGET_SECONDS
STATE_ENV = "COMPLAINT_INTAKE_RELEASE_CAMPAIGN_STATE_DIR"
TARGET_ENV = "COMPLAINT_INTAKE_RELEASE_TARGET_SOURCE_ROOT"
GUARD_ENV = "COMPLAINT_INTAKE_RELEASE_GUARD_DIR"
EXTRA_MODULES = (PUBLIC_RELATIVE, "tests/test_intake_router_boundary.py",
                 "tests/test_intake_router_integration.py", "tests/test_intake_router_semantics.py",
                 "tests/test_intake_router_egress.py", "tests/test_private_replica_acceptance.py",
                 "tests/test_release_evidence_bridge.py", "tests/test_improvement_container_shutdown.py",
                 "tests/test_improvement_plan_amendment.py", "tests/test_improvement_recovery_boundary.py",
                 "tests/test_improvement_release_amendment.py", "tests/test_improvement_validation_activity.py",
                 "tests/test_improvement_release_context.py")
_GUARD: dict[str, Any] = {}
_OPEN_CONTEXT = threading.local()
_ORIGINAL_OS_OPEN = os.open


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _unalias(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("path_alias_forbidden")
    if path.resolve() != path:
        raise ValueError("path_alias_forbidden")
    return path


def _owned_directory(path: Path, *, create: bool = False) -> Path:
    path = _unalias(path)
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("runtime_directory_not_private_owned")
    return path


def _kernel_network_deny() -> None:
    """An inherited seccomp filter denies every non-Unix socket, including C code."""
    architectures = {"x86_64": (0xC000003E, 41), "aarch64": (0xC00000B7, 198)}
    if sys.platform != "linux" or platform.machine() not in architectures:
        raise RuntimeError("kernel_network_guard_unavailable")
    arch, socket_number = architectures[platform.machine()]
    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                    ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]
    rows = [(0x20, 0, 0, 4), (0x15, 1, 0, arch), (0x06, 0, 0, 0x80000000),
            (0x20, 0, 0, 0), (0x15, 0, 3, socket_number), (0x20, 0, 0, 16),
            (0x15, 1, 0, 1), (0x06, 0, 0, 0x00050000 | errno.EPERM),
            (0x06, 0, 0, 0x7FFF0000)]
    filters = (Filter * len(rows))(*(Filter(*row) for row in rows))
    program = Program(len(rows), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, ctypes.byref(program), 0, 0):
        raise RuntimeError("kernel_network_guard_unavailable")


def _pid_metadata(pid: int) -> tuple[int, int, int, str] | None:
    """Read ancestry/birth metadata only; never inspect argv or environment."""
    try:
        directory = Path("/proc") / str(pid)
        raw = (directory / "stat").read_bytes()
        if len(raw) > 8192:
            return None
        fields = raw.rsplit(b")", 1)[1].split()
        return int(fields[1]), int(fields[19]), directory.stat().st_uid, fields[0].decode("ascii")
    except (OSError, ValueError, IndexError, UnicodeError):
        return None


def _owned_metadata_pid(value: str) -> bool:
    if re.fullmatch(r"[1-9][0-9]*", value) is None:
        return False
    pid = int(value)
    root = _GUARD.get("process_root")
    target = _pid_metadata(pid)
    if not isinstance(root, tuple) or len(root) != 3 or target is None or target[2] != os.getuid():
        return False
    root_pid, root_ticks, root_uid = root
    initial_root = _pid_metadata(root_pid)
    if initial_root is None or (initial_root[1], initial_root[2]) != (root_ticks, root_uid):
        return False
    current, seen = pid, set()
    for _ in range(128):
        if current in seen:
            return False
        seen.add(current)
        identity = _pid_metadata(current)
        if identity is None or identity[2] != root_uid:
            return False
        if current == root_pid:
            latest_target, latest_root = _pid_metadata(pid), _pid_metadata(root_pid)
            return (latest_target is not None and latest_root is not None
                    and latest_target[1:3] == target[1:3] and latest_root[1:3] == initial_root[1:3])
        if identity[0] <= 1:
            return False
        current = identity[0]
    return False


def _safe_local_argv(argv: Any, cwd: Any = None, *, depth: int = 0) -> bool:
    if depth > 2 or not isinstance(argv, (list, tuple)) or not argv:
        return False
    words = [os.fsdecode(item) for item in argv]
    executable = words[0]
    name = Path(executable).name
    if name == "pgrep":
        # Native treats an exited parent as an ordinary empty child census.
        # This exact form returns child IDs only, without argv/environment.
        return len(words) == 3 and words[1] == "-P" and re.fullmatch(r"[1-9][0-9]*", words[2]) is not None
    if name == "ps":
        return (len(words) == 5 and words[1] == "-o" and words[2] in {"args=", "ppid="}
                and words[3] == "-p" and _owned_metadata_pid(words[4]))
    if name == "prlimit":
        # Data's owned ProcessSupervisor supplies its existing wall deadline;
        # this native wrapper only disables cores before the reviewed Python.
        # PID-targeted limits and additional prlimit options are never admitted.
        return (len(words) > 4 and words[1:3] == ["--core=0:0", "--"]
                and Path(words[3]).resolve() == Path(_GUARD["python"]).resolve()
                and _safe_local_argv(words[3:], cwd, depth=depth + 1))
    if name in {"sh", "bash"}:
        if len(words) == 5 and words[1:4] == ["--noprofile", "--norc", "-c"]:
            # Accept only the byte-exact first-party launcher wrapper. Its
            # remaining reviewed command is still checked below.
            marker = "readonly -f "
            index = words[4].find(marker)
            end = words[4].find("; ", index)
            if index < 0 or end < 0:
                return False
            command = words[4][end + 2:]
            runtime = sys.modules.get("ipfs_accelerate_py.agent_supervisor.validation.validation_runtime")
            if runtime is None or runtime.validation_shell_command(command) != words:
                return False
            words = [words[0], "-c", command]
        if len(words) != 3 or words[1] not in {"-c", "-lc"}:
            return False
        command = words[2].replace('"${PYTHONPATH-}"', "").replace("${PYTHONPATH-}", "")
        if any(token in command for token in ("$", "`", "\n", ";", "|", "<", ">", "(", ")")):
            return False
        segments = command.split("&&")
        if len(segments) > 5:
            return False
        for segment in segments:
            tokens = shlex.split(segment)
            if not tokens:
                return False
            if tokens[0] == "export":
                tokens = tokens[1:]
                allowed = {"PYTHONPATH", "IPFS_ACCELERATE_PYTEST_SEAL_DUCKDB", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"}
                if not tokens or any("=" not in value or value.split("=", 1)[0] not in allowed for value in tokens):
                    return False
                continue
            while tokens and "=" in tokens[0] and tokens[0].split("=", 1)[0].replace("_", "").isalnum():
                if tokens.pop(0).split("=", 1)[0] not in {"PYTHONPATH", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"}:
                    return False
            if not _safe_local_argv(tokens, cwd, depth=depth + 1):
                return False
        return True
    if re.fullmatch(r"/proc/(self|[1-9][0-9]*)/fd/[0-9]+", executable):
        owner = executable.split("/")[2]
        if owner not in {"self", str(os.getpid())}:
            return False
        try:
            target = os.readlink(executable)
        except OSError:
            return False
        return "memfd:validation Python launcher" in target
    if name.startswith("python"):
        try:
            return (depth > 0 and executable in {"python", "python3", Path(_GUARD["python"]).name}
                    or Path(executable).resolve() == Path(_GUARD["python"]).resolve())
        except (OSError, KeyError):
            return False
    if name == "git":
        operation_index = 1
        while operation_index < len(words) and words[operation_index].startswith("-"):
            option = words[operation_index]
            operation_index += 2 if option in {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"} else 1
        if operation_index < len(words) and words[operation_index] == "clean":
            return (operation_index == 1 and words[1:] == ["clean", "-ffd"]
                    and _reviewed_git_cleanup_cwd(cwd))
        if "submodule" in words[1:]:
            # Native's dependency fingerprint reads recursive gitlink status.
            # Admit its exact metadata command, with no -C/config/path options
            # and only within this candidate or the owned fixture namespace.
            return (words[1:] == ["submodule", "status", "--recursive"]
                    and _reviewed_git_metadata_cwd(cwd))
        if any(value in {"fetch", "push", "pull", "clone", "send-email", "daemon", "submodule"} for value in words[1:]):
            return False
        if any("!" in value or "sshCommand" in value or "credential" in value for value in words):
            return False
        if any(value == flag or value.startswith(flag + "=") for value in words[1:]
               for flag in ("--ext-diff", "--textconv", "--exec-path", "--config-env")):
            return False
        def safe_config(key: str, value: str | None) -> bool:
            key = key.casefold()
            if key == "core.hookspath":
                return value == "/dev/null"
            if key == "core.fsmonitor":
                return value is not None and value.casefold() in {"false", "no", "off", "0"}
            return not (key in {"diff.external", "core.sshcommand", "credential"}
                        or key.startswith("credential.")
                        or key.startswith("diff.") and key.rsplit(".", 1)[-1] in {"command", "textconv"})
        for index, value in enumerate(words[1:], 1):
            if value == "-c":
                if index + 1 >= len(words):
                    return False
                setting = words[index + 1]
            elif value.startswith("-c") and len(value) > 2:
                setting = value[2:]
            else:
                continue
            if "=" not in setting or not safe_config(*setting.split("=", 1)):
                return False
        read_only = {"rev-parse", "show", "diff", "status", "ls-files", "cat-file", "merge-base", "log",
                     "ls-tree", "symbolic-ref", "for-each-ref", "rev-list"}
        local = {"init", "add", "commit", "config", "checkout", "switch", "branch", "update-index", "reset", "worktree"}
        operation = next((word for word in words[1:] if word in read_only | local), "")
        if operation == "config":
            settings = [word for word in words[words.index("config") + 1:] if not word.startswith("-")]
            if settings and not safe_config(settings[0], settings[1] if len(settings) > 1 else None):
                return False
        if operation in read_only:
            return True
        target = Path(cwd or os.getcwd())
        if "-C" in words:
            index = words.index("-C") + 1
            if index >= len(words):
                return False
            directory = Path(words[index])
            target = directory if directory.is_absolute() else target / directory
        if operation == "init":
            arguments = iter(words[words.index("init") + 1:])
            destinations = []
            for argument in arguments:
                if argument in {"-b", "--initial-branch"}:
                    if next(arguments, None) is None:
                        return False
                elif not argument.startswith("-"):
                    destinations.append(argument)
            if len(destinations) > 1:
                return False
            if destinations:
                directory = Path(destinations[0])
                target = directory if directory.is_absolute() else target / directory
        return operation in local and _within(target.resolve(), Path(_GUARD["directory"]))
    return False


def _reviewed_git_metadata_cwd(cwd: Any) -> bool:
    if not isinstance(cwd, (str, bytes, os.PathLike)):
        return False
    try:
        target = _unalias(Path(os.fsdecode(cwd)))
        info = target.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or ".git" in target.parts:
            return False
        source = Path(_GUARD["source_root"])
        if any(_within(target, prefix) for prefix in _private_prefix_paths(source)):
            return False
        return _within(target, source) or _within(target, Path(_GUARD["directory"]))
    except (OSError, ValueError, KeyError):
        return False


def _reviewed_git_cleanup_cwd(cwd: Any) -> bool:
    if not _reviewed_git_metadata_cwd(cwd):
        return False
    target = _unalias(Path(os.fsdecode(cwd)))
    return (_within(target, Path(_GUARD["directory"]))
            and not _within(target, Path(_GUARD["source_root"]))
            and (target / ".git").exists() and not (target / ".git").is_symlink())


def _resolved_executable(value: Any, environment: Mapping[str, str] | None, cwd: Any) -> Path | None:
    if not isinstance(value, (str, bytes, os.PathLike)):
        return None
    rendered = os.fsdecode(value)
    if "/" in rendered:
        candidate = Path(rendered)
        if not candidate.is_absolute():
            return None
        try:
            return candidate.resolve(strict=True)
        except OSError:
            return None
    for directory in os.get_exec_path(environment):
        if not Path(directory).is_absolute():
            return None
        candidate = Path(directory) / rendered
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve(strict=True)
    return None


def native_memfd_approved_paths(value: str, environment: Mapping[str, str], *, runtime: Any,
        python: str, approved_roots: Sequence[Path] | None = None,
        candidate_root: Path | None = None) -> tuple[Path, ...] | None:
    """Recover approved paths from exact immutable Native bytes, never env claims."""
    try:
        match = re.fullmatch(r"/proc/(self|[1-9][0-9]*)/fd/([0-9]+)", value)
        if match is None or match[1] not in {"self", str(os.getpid())}:
            return None
        descriptor = int(match[2])
        info = os.fstat(descriptor)
        if fcntl.fcntl(descriptor, getattr(fcntl, "F_GET_SEALS", 1034)) & 15 != 15 or not 0 < info.st_size <= 64 * 1024 * 1024:
            return None
        payload = os.pread(descriptor, info.st_size, 0)
        label = os.readlink(value)
        if runtime is None or "memfd:validation Python launcher" not in label:
            return None
        text = payload.decode("utf-8")
        approved_lines = [line for line in text.splitlines() if line.startswith("readonly approved=")]
        if len(approved_lines) != 1:
            return None
        approved_values = shlex.split(approved_lines[0].split("=", 1)[1])
        if len(approved_values) != 1:
            return None
        approved = approved_values[0]
        encoded_paths = []
        for raw in approved.split(os.pathsep):
            if not raw:
                if approved:
                    return None
                continue
            path = Path(raw)
            if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_dir():
                return None
            if approved_roots is not None and not any(_within(path, root) for root in approved_roots):
                return None
            encoded_paths.append(path)
        ruff = runtime._active_ruff_executable_snapshot(approved_pythonpath=approved)
        argv0 = ""
        lines = [line for line in text.splitlines() if line.startswith("readonly validation_argv0=")]
        if lines:
            if len(lines) != 1:
                return None
            values = shlex.split(lines[0].split("=", 1)[1])
            if len(values) != 1:
                return None
            argv0 = runtime._admit_validation_argv0(values[0], approved=Path(python).resolve())
        expected = runtime._validation_python_launcher_source(executable=python,
            approved_pythonpath=approved, ruff_sha256=ruff[1] if ruff is not None else "",
            no_site=runtime.validation_python_profile(environment) == "raw-no-site", argv0=argv0)
        if payload != expected:
            return None
        allowed = set(encoded_paths)
        candidate = candidate_root.resolve() if candidate_root is not None else None
        for raw in environment.get("PYTHONPATH", "").split(os.pathsep):
            if not raw:
                if environment.get("PYTHONPATH"):
                    return None
                continue
            path = Path(raw)
            if not path.is_absolute():
                if candidate is None:
                    return None
                path = candidate / path
            path = path.resolve(strict=True)
            if path not in allowed and path != candidate:
                return None
        return tuple(dict.fromkeys(encoded_paths))
    except (OSError, ValueError, KeyError, UnicodeError):
        return None


def native_memfd_matches(value: str, environment: Mapping[str, str], *, runtime: Any,
                         python: str, approved_roots: Sequence[Path] | None = None,
                         candidate_root: Path | None = None) -> bool:
    return native_memfd_approved_paths(value, environment, runtime=runtime, python=python,
        approved_roots=approved_roots, candidate_root=candidate_root) is not None


def _reviewed_memfd(value: str, environment: Mapping[str, str]) -> bool:
    return native_memfd_matches(value, environment, runtime=_GUARD.get("native_runtime"),
        python=_GUARD["python"], approved_roots=_GUARD["approved_roots"], candidate_root=Path(_GUARD["source_root"]))


def reviewed_process_dispatch(executable: Any, argv: Any, cwd: Any,
                              environment: Mapping[str, str] | None) -> bool:
    """An allowed argv cannot disguise a different executable or PATH result."""
    if not isinstance(argv, (list, tuple)) or not argv:
        return False
    effective = os.environ if environment is None else environment
    actual_text, claimed_text = os.fsdecode(executable), os.fsdecode(argv[0])
    if re.fullmatch(r"/proc/(self|[1-9][0-9]*)/fd/[0-9]+", actual_text) or re.fullmatch(r"/proc/(self|[1-9][0-9]*)/fd/[0-9]+", claimed_text):
        return actual_text == claimed_text and _reviewed_memfd(actual_text, effective)
    actual = _resolved_executable(executable, effective, cwd)
    claimed = _resolved_executable(argv[0], effective, cwd)
    if actual is None or actual != claimed:
        return False
    expected = _GUARD.get("executables", {}).get(str(actual))
    if expected is None or _hash(actual) != expected:
        return False
    if actual == Path("/bin/bash").resolve() and _reviewed_launcher_script(argv, cwd, effective):
        return True
    if actual.name == "prlimit" and _reviewed_replica_resource_probe(argv, cwd, effective):
        return True
    if actual.name == "prlimit":
        # Recheck the nested executable's bytes and claimed identity too. An
        # approved outer wrapper cannot smuggle a foreign executable inside.
        return (_safe_local_argv(argv, cwd)
                and reviewed_process_dispatch(argv[3], argv[3:], cwd, effective))
    return _safe_local_argv(argv, cwd)


_REPLICA_COMPANION_SHA256 = "6b125c8adbea59328b8d8a3cc76ba80254d4ccf5f8aed4eb68b8cefa4aefc4fe"
_REPLICA_PROBE_OPERATIONS = frozenset({
    "deadline_publish", "deadline_reconcile", "deadline_restore",
    "restart_publish", "restart_restore", "concurrent_publish", "escape_control",
})


def _reviewed_replica_probe_literal():
    """Read only the immutable companion's one literal; never import it."""
    import ast
    source = _unalias(Path(_GUARD["source_root"]) / "tests/test_private_replica_acceptance.py")
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or before.st_mode & 0o002
                or not 0 < before.st_size <= 2 * 1024 * 1024):
            return None
        raw = os.read(descriptor, before.st_size + 1)
        fields = ("st_dev", "st_ino", "st_size", "st_uid", "st_mode", "st_nlink", "st_mtime_ns", "st_ctime_ns")
        if (len(raw) != before.st_size or any(getattr(before, key) != getattr(other, key)
                for other in (os.fstat(descriptor), source.lstat()) for key in fields)
                or hashlib.sha256(raw).hexdigest() != _REPLICA_COMPANION_SHA256):
            return None
    finally:
        os.close(descriptor)
    values = [node.value for node in ast.parse(raw).body if isinstance(node, ast.Assign)
              and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id == "REPLICA_PROBE"]
    if len(values) != 1:
        return None
    value = ast.literal_eval(values[0])
    return value if isinstance(value, str) else None


def _reviewed_replica_resource_probe(argv, cwd, environment):
    """Admit only Data's actual resource-bounded immutable synthetic probe.

    The immutable child enforces -I/-S/-B, parent death, owner PID and a private
    release barrier before product imports. Kernel non-Unix socket denial is
    inherited from the installed guard. Python private-prefix audit hooks do
    not survive exec; this helper makes no contrary child-audit claim.
    """
    try:
        words = [os.fsdecode(item) for item in argv]
        if (len(words) != 17 or Path(words[0]).name != "prlimit"
                or words[1:5] != ["--core=0:0", "--cpu=4:4", "--as=536870912:536870912", "--"]):
            return False
        inner = words[5:]
        if inner[1:5] != ["-I", "-S", "-B", "-c"]:
            return False
        python = _resolved_executable(inner[0], environment, cwd)
        expected_python = Path(_GUARD["python"]).resolve(strict=True)
        if (python != expected_python or _GUARD["executables"].get(str(python)) != _hash(python)
                or inner[5] != _reviewed_replica_probe_literal()):
            return False
        owner, source_text, workspace_text, operation, packages_text, control_text = inner[6:]
        source = _unalias(Path(source_text))
        if owner != str(os.getpid()) or source != Path(_GUARD["source_root"]) or operation not in _REPLICA_PROBE_OPERATIONS:
            return False
        workspace = _owned_directory(Path(workspace_text))
        temporary = _owned_directory(workspace.parent)
        home = _owned_directory(temporary / "probe-home")
        control = _owned_directory(Path(control_text))
        if (workspace.name != "probe-workspace" or not _within(temporary, Path(_GUARD["directory"]))
                or _unalias(Path(cwd or os.getcwd())) != workspace
                or control != temporary / (operation + "-barrier")):
            return False
        cryptography = sys.modules.get("cryptography")
        if cryptography is None or not getattr(cryptography, "__file__", None):
            return False
        packages = _unalias(Path(packages_text))
        if (packages != Path(cryptography.__file__).resolve(strict=True).parents[1]
                or packages not in _GUARD["approved_roots"]):
            return False
        expected = {"PATH", "HOME", "TMPDIR", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE",
                    "IPFS_DATASETS_MANAGED_PROCESS_ID", "IPFS_DATASETS_PROCESS_SUPERVISOR_ID"}
        if (set(environment) != expected or environment["PATH"] != os.defpath
                or environment["HOME"] != str(home) or environment["TMPDIR"] != str(temporary)
                or environment["HF_HUB_OFFLINE"] != "1" or environment["TRANSFORMERS_OFFLINE"] != "1"):
            return False
        return all(re.fullmatch(r"[0-9a-f]{32}", environment[name]) is not None for name in
                   ("IPFS_DATASETS_MANAGED_PROCESS_ID", "IPFS_DATASETS_PROCESS_SUPERVISOR_ID"))
    except (OSError, ValueError, TypeError, KeyError, SyntaxError):
        return False


def _reviewed_launcher_script(argv: Sequence[Any], cwd: Any,
                              environment: Mapping[str, str]) -> bool:
    """Admit the source-pinned, finite launcher dry-run used by the PTY suite."""
    words = [os.fsdecode(value) for value in argv]
    if len(words) != 4 or words[2:] != ["--user-id", "synthetic"]:
        return False
    try:
        source = Path(_GUARD["source_root"]) / "scripts/run_cli_mediator.sh"
        script = _unalias(Path(words[1]))
        if script != source or _hash(script) != _GUARD.get("launcher_script_sha256"):
            return False
        allowed_keys = {"PATH", "HOME", "COMPLAINT_GENERATOR_PYTHON",
                        "COMPLAINT_GENERATOR_MEDIATOR_BACKENDS", "COMPLAINT_GENERATOR_LAUNCHER_DRY_RUN"}
        if set(environment) != allowed_keys or environment["PATH"] != "/usr/bin:/bin":
            return False
        if (environment["COMPLAINT_GENERATOR_LAUNCHER_DRY_RUN"] != "1"
                or environment["COMPLAINT_GENERATOR_PYTHON"] != "/usr/bin/false"
                or environment["COMPLAINT_GENERATOR_MEDIATOR_BACKENDS"] != "configured-backend"):
            return False
        if not _within(_unalias(Path(environment["HOME"])), Path(_GUARD["directory"])):
            return False
        if not _within(_unalias(Path(cwd or os.getcwd())), Path(_GUARD["directory"])):
            return False
        # Bash probes the deliberately failing interpreter, then the fixed
        # system Python. No user-controlled startup files or interpreter PATH
        # entries are present in this exact environment.
        for path in (Path("/usr/bin/false").resolve(), Path("/usr/bin/python3.12").resolve()):
            if _GUARD.get("launcher_probe_executables", {}).get(str(path)) != _hash(path):
                return False
        venv = source.parents[1] / ".venv/bin/python"
        if venv.exists() and venv.resolve() != Path(_GUARD["python"]).resolve():
            return False
        return True
    except (OSError, ValueError, KeyError):
        return False


def _private_prefix_paths(source_root: Path) -> tuple[Path, ...]:
    private = ("data", "output", "statefiles", "exports", ".complaint_workspace",
               "secrets", "evidence", "uploads", "attachments")
    roots = (source_root, *(source_root / "external" / package for package in
              ("ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py")))
    return tuple(source / relative for source in roots for relative in private)


def _configure_private_prefixes(source_root: Path) -> None:
    prefixes = _private_prefix_paths(source_root)
    _GUARD["private_prefixes"] = prefixes
    _GUARD["private_prefix_exact"] = frozenset(map(str, prefixes))
    _GUARD["private_prefix_text"] = tuple(str(path) + os.sep for path in prefixes)


def _private_path(path: Path) -> bool:
    text = str(path)
    return text in _GUARD["private_prefix_exact"] or text.startswith(_GUARD["private_prefix_text"])


def _audit_private_access(event: str, args: tuple[Any, ...]) -> None:
    if event not in {"open", "os.listdir", "os.scandir"} or not args:
        return
    raw = args[0]
    if isinstance(raw, int):
        try:
            raw = os.readlink(f"/proc/self/fd/{raw}")
        except OSError as exc:
            if exc.errno in {errno.EBADF, errno.ENOENT}:
                return  # Preserve the original invalid-descriptor behavior.
            raise
    if not isinstance(raw, (str, bytes, os.PathLike)):
        return
    path = Path(os.fsdecode(raw))
    context = getattr(_OPEN_CONTEXT, "active", None) if event == "open" else None
    if not path.is_absolute() and context is not None and os.fsdecode(raw) == context[0]:
        # The Python open audit event omits dir_fd. The wrapper records the
        # descriptor for this thread only, without changing the actual call.
        descriptor = context[1]
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                return  # Preserve the original kernel ENOTDIR error.
            target = os.readlink(f"/proc/self/fd/{descriptor}")
            if not target.startswith("/") or target.endswith(" (deleted)"):
                raise OSError("directory_descriptor_unresolved")
            base = Path(target).resolve(strict=True)
            actual = base.stat()
            if (actual.st_dev, actual.st_ino) != (info.st_dev, info.st_ino):
                raise OSError("directory_descriptor_changed")
            if _private_path(base):
                _GUARD["denied_private"] += 1
                raise PermissionError("release_existing_private_data_denied")
            path = base / path
        except PermissionError:
            raise
        except OSError as exc:
            if exc.errno == errno.EBADF:
                return  # Preserve os.open's original invalid-descriptor error.
            raise PermissionError("release_directory_descriptor_unverified") from None
    # Check the lexical location as well as a fresh resolution: a private path
    # aliased outward and a temporary path aliased inward are both refused.
    lexical = Path(os.path.abspath(path))
    resolved = path.resolve()
    if _private_path(lexical) or _private_path(resolved):
        _GUARD["denied_private"] += 1
        raise PermissionError("release_existing_private_data_denied")


def _reviewed_os_open(path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
    # os.fspath is evaluated exactly once, as with the original builtin.
    rendered = os.fspath(path)
    previous = getattr(_OPEN_CONTEXT, "active", None)
    _OPEN_CONTEXT.active = ((os.fsdecode(rendered), dir_fd) if dir_fd is not None else None)
    try:
        return _ORIGINAL_OS_OPEN(rendered, flags, mode, dir_fd=dir_fd)
    finally:
        _OPEN_CONTEXT.active = previous


def _install_guard(directory: Path) -> None:
    if _GUARD:
        return
    directory = _owned_directory(directory)
    temporary = _owned_directory(directory / "tmp", create=True)
    control = _owned_directory(directory / "control-plane", create=True)
    os.environ.update({"TMPDIR": str(temporary), "IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR": str(control),
                       "IPFS_ACCELERATE_META_INDEX_DUCKDB": "", "IPFS_ACCELERATE_META_INDEX_DUCKLAKE": "",
                       "IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD": "0", "COMMON_CRAWL_AUTO_CLONE_SOURCE": "0",
                       "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    tempfile.tempdir = str(temporary)
    _GUARD.update(directory=str(directory), python=os.environ.get("IPFS_ACCELERATE_VALIDATION_PYTHON_EXECUTABLE", sys.executable),
                  source_root=str(Path.cwd().resolve()), denied_private=0,
                  denied_network=0, denied_process=0, allowed_local_process=0)
    identity = _pid_metadata(os.getpid())
    if identity is None:
        raise RuntimeError("release_guard_process_identity_unavailable")
    _GUARD["process_root"] = (os.getpid(), identity[1], identity[2])
    _kernel_network_deny()
    from ipfs_accelerate_py.agent_supervisor.validation import validation_runtime
    _GUARD["native_runtime"] = validation_runtime
    executable_paths = [Path(_GUARD["python"]).resolve(), Path("/bin/bash").resolve(), Path("/usr/bin/prlimit").resolve()]
    git = shutil.which("git", path=os.defpath)
    if git is None:
        raise RuntimeError("canonical_git_unavailable")
    executable_paths.append(Path(git).resolve())
    for name in ("pgrep", "ps"):
        metadata = shutil.which(name, path=os.defpath)
        if metadata is None:
            raise RuntimeError("canonical_process_metadata_helper_unavailable:" + name)
        executable_paths.append(Path(metadata).resolve())
    _GUARD["executables"] = {str(path): _hash(path) for path in executable_paths}
    _GUARD["launcher_script_sha256"] = _hash(Path(_GUARD["source_root"]) / "scripts/run_cli_mediator.sh")
    _GUARD["launcher_probe_executables"] = {str(path): _hash(path) for path in
        (Path("/usr/bin/false").resolve(), Path("/usr/bin/python3.12").resolve())}
    _GUARD["approved_roots"] = [directory, *[Path(value).resolve() for value in sys.path if value and Path(value).is_absolute()]]
    _configure_private_prefixes(Path(_GUARD["source_root"]))
    os.open = _reviewed_os_open
    if _ORIGINAL_OS_OPEN in os.supports_dir_fd:
        os.supports_dir_fd.add(_reviewed_os_open)
    def audit(event: str, args: tuple[Any, ...]) -> None:
        _audit_private_access(event, args)
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"}:
            _GUARD["denied_network"] += 1
            raise PermissionError("release_network_denied")
        if event == "socket.__new__" and args[1] != 1:
            _GUARD["denied_network"] += 1
            raise PermissionError("release_network_denied")
        if event == "subprocess.Popen":
            if not reviewed_process_dispatch(args[0], args[1], args[2], args[3]):
                _GUARD["denied_process"] += 1
                raise PermissionError("release_provider_or_unknown_process_denied")
            _GUARD["allowed_local_process"] += 1
        elif event in {"os.system", "os.exec", "os.posix_spawn", "os.spawn"}:
            _GUARD["denied_process"] += 1
            raise PermissionError("release_provider_or_unknown_process_denied")
    sys.addaudithook(audit)


# The host's -p argument places this import before phase/AST plugins and product
# conftests. Kernel denies remain inherited by local Python/PTY descendants.
if __name__ != "__main__" and os.environ.get(GUARD_ENV):
    _install_guard(Path(os.environ[GUARD_ENV]))


def _imported_source_hashes(source_root: Path, *, modules: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Hash only actual imported Python source metadata; never scan a tree."""
    source_root = _unalias(source_root)
    modules = sys.modules if modules is None else modules
    if len(modules) > 20000:
        raise RuntimeError("release_imported_source_population_unbounded")
    prefixes = _private_prefix_paths(source_root)
    private_exact = frozenset(map(str, prefixes))
    private_text = tuple(str(path) + os.sep for path in prefixes)
    sources, total = {}, 0
    for module in tuple(modules.values()):
        value = getattr(module, "__file__", None)
        if not isinstance(value, (str, bytes, os.PathLike)):
            continue
        path = Path(os.fsdecode(value))
        if path.suffix != ".py":
            continue
        if not path.is_absolute():
            # Dynamic module namespaces (for example torch.ops) may advertise
            # a relative __file__ marker without loading that filesystem path.
            # Resolve relative source only with actual loader/spec provenance;
            # never reinterpret an unlocated virtual marker against our cwd.
            specification = getattr(module, "__spec__", None)
            origin = getattr(specification, "origin", None)
            if (not isinstance(origin, (str, bytes, os.PathLike))
                    or os.fsdecode(origin) in {"built-in", "frozen"}
                    or not (getattr(specification, "has_location", False) is True
                            or isinstance(getattr(specification, "loader", None), SourceFileLoader))):
                continue
            if os.path.abspath(os.fsdecode(origin)) != os.path.abspath(path):
                raise RuntimeError("release_imported_source_origin_mismatch")
        lexical = Path(os.path.abspath(path))
        resolved = lexical.resolve()
        if not (_within(lexical, source_root) or _within(resolved, source_root)):
            continue
        text = str(lexical)
        if text in private_exact or text.startswith(private_text):
            raise RuntimeError("release_imported_private_source_denied")
        path = _unalias(lexical)
        if str(path) in sources:
            continue
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1
                or not 0 <= before.st_size <= 8 * 1024 * 1024):
            raise RuntimeError("release_imported_source_not_owned_or_bounded")
        total += before.st_size
        if total > 128 * 1024 * 1024:
            raise RuntimeError("release_imported_source_bytes_unbounded")
        digest = _hash(path)
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise RuntimeError("release_imported_source_changed")
        sources[str(path)] = digest
    return dict(sorted(sources.items()))


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    if not _GUARD:
        raise RuntimeError("release_guard_missing")
    manifest = Path(session.config.getoption("--complaint-evidence-path"))
    path = manifest.with_suffix(".guard.json")
    path.write_text(json.dumps({"schema": "complaint-release-effect-guard@1", "exitstatus": int(exitstatus),
        "network_process_dispatch_permitted": False, "kernel_network_deny": True,
        "provider_process_deny": True, "provider_process_deny_scope": "pytest_dispatch; reviewed_local_helpers_inherit_kernel_network_deny",
        "guard_load_order": "explicit_first_plugin_before_product_imports",
        "allowed_local_helpers": "pinned_python_git_bash; fixture_git_clean; scoped_process_metadata; core_zero_prlimit_python; immutable_bounded_replica_probe; source_pinned_launcher_dry_run",
        "denied_attempts": {key: _GUARD[key] for key in ("denied_network", "denied_process", "denied_private")},
        "imported_source_hashes": _imported_source_hashes(Path(_GUARD["source_root"])),
        "private_namespace": _GUARD["directory"]}, sort_keys=True) + "\n")
    path.chmod(0o600)


def repo_root_from(start: Path | None = None) -> Path:
    return (start or Path(__file__)).resolve().parents[1]


def parse_phase(argv: Sequence[str]) -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--phase", choices=("pre-admission", "post-completion"), default="post-completion")
    if sum(value == "--phase" or value.startswith("--phase=") for value in argv) > 1:
        raise ValueError("duplicate_phase")
    try:
        parsed, _ = parser.parse_known_args(argv)
    except SystemExit as exc:
        raise ValueError("phase_argument") from exc
    return parsed.phase


def _load_spec(root: Path) -> dict[str, Any]:
    from integrations.ipfs_accelerate.improvement_plan import load_spec
    spec = load_spec(root / SPEC_RELATIVE)
    if len(spec["tasks"]) != 58 or len(spec["goals"]) != 10 or sum(len(g["subgoals"]) for g in spec["goals"]) != 29:
        raise ValueError("reviewed_plan_population_changed")
    return spec


def mandatory_manifest(root: Path) -> dict[str, list[str]]:
    paths: set[str] = set(EXTRA_MODULES)
    for task in _load_spec(root)["tasks"]:
        if task["id"] == SELF_TASK:
            continue
        for command in task["validation_commands"]:
            tokens = shlex.split(command)
            if "pytest" not in tokens or any(token in tokens for token in (";", "|", "&&")):
                raise ValueError("unsupported_mandatory_command")
            selectors = [token.split("::", 1)[0] for token in tokens if token.startswith("tests/") and ".py" in token]
            if not selectors:
                raise ValueError("mandatory_population_missing")
            paths.update(selectors)
    if GATE_RELATIVE in paths or SCRIPT_RELATIVE in paths:
        raise ValueError("recursive_self_validation")
    for relative in paths:
        if Path(relative).is_absolute() or ".." in Path(relative).parts or not relative.endswith(".py"):
            raise ValueError("mandatory_path_invalid")
        path = _unalias(root / relative)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("mandatory_module_missing:" + relative)
    replica = {p for p in paths if p in {"tests/test_private_workspace_replication.py", "tests/test_private_replica_acceptance.py"}}
    lifecycle = {p for p in paths if p.startswith("tests/test_improvement_") or p == "tests/test_alignment_watchdog.py"}
    return {"application": sorted(paths - lifecycle - replica), "lifecycle": sorted(lifecycle), "replica": sorted(replica)}


def source_bindings(root: Path) -> dict[str, str]:
    from integrations.ipfs_accelerate.improvement_runner import _source_freeze
    from integrations.ipfs_accelerate.improvement_plan import _digest
    for relative in BOUND_SOURCE_PATHS:
        path = _unalias(root / relative)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("release_source_missing:" + relative)
    explicit = set(BOUND_SOURCE_PATHS)
    explicit.update(path for group in mandatory_manifest(root).values() for path in group)
    frozen = _source_freeze(root, sorted(explicit))
    deployed = {"external/ipfs_accelerate_py", "external/ipfs_datasets_py", "external/ipfs_kit_py"}
    if not deployed.issubset(frozen["dependencies"]):
        raise ValueError("deployed_dependency_source_unavailable")
    dependencies = {}
    opaque = {}
    for relative, binding in frozen["dependencies"].items():
        gitlink = binding.get("gitlink")
        if not isinstance(gitlink, str) or re.fullmatch(r"[0-9a-f]{40}", gitlink) is None:
            raise ValueError("dependency_gitlink_identity_unavailable")
        if relative in deployed:
            if binding.get("head") != gitlink:
                raise ValueError("deployed_dependency_head_changed:" + relative)
            dependencies[relative] = dict(binding)
        else:
            # Opaque undeployed gitlinks have no physical checkout/HEAD claim.
            # Preserve their committed identities without initializing, fetching,
            # resetting, or qualifying Mike/Common Crawl or another dependency.
            dependencies[relative] = {"gitlink": gitlink, "scope": "opaque_gitlink_identity_only"}
            opaque[relative] = gitlink
    normalized = {"files": frozen["files"], "dependencies": dependencies}
    return {**{relative: _hash(root / relative) for relative in BOUND_SOURCE_PATHS},
            "implementation_scope_digest": _digest(normalized),
            "opaque_gitlink_identity_scope_digest": _digest(opaque)}


def committed_report_payload(root: Path) -> dict[str, Any]:
    return {"schema": REPORT_SCHEMA, "phase": "pre-admission", "task_id": SELF_TASK,
            "release_qualified": False, "self_completion_pending": True, "pending_task_ids": [SELF_TASK],
            "completion_authority": False, "native_completion_claimed": False,
            "required_task_count": 58, "other_task_count": 57, "hash_scope": HASH_SCOPE,
            "source_bindings": source_bindings(root), "mandatory_manifest": mandatory_manifest(root),
            "current_qualification_protocol": {
                "schema": "complaint-release-current-source-qualification@1",
                "binding": "owned_campaign_state/host-acceptance/complaint-release-current-qualification.json",
                "producer": "fresh_serial_native_whole_module_shards_and_independent_global_collection",
                "maximum_modules_per_shard": 4, "maximum_seconds_per_shard": TOTAL_BUDGET_SECONDS,
                "pool_size": 1, "retries": 0, "mandatory_skips": 0,
                "canonical_checker": "live_native_completion_reader_and_current_source_artifact_reverification",
                "bound_producer_cases_executed_by_checker_invocation": 0,
                "binding_absent": "direct_native_closure_with_existing_total_budget",
                "binding_invalid": "fail_closed_without_direct_fallback",
                "completion_authority": False}}


def committed_report_contract(root: Path) -> tuple[str, str]:
    path = _unalias(root / REPORT_RELATIVE)
    raw = path.read_bytes()
    actual = json.loads(raw)
    return ("" if actual == committed_report_payload(root) else "committed_pre_admission_contract_changed", _digest_bytes(raw))


def _process_table() -> dict[int, tuple[int, int, int]]:
    rows = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            rows[int(entry.name)] = (int(fields[1]), int(fields[19]), int(fields[2]))
        except (OSError, ValueError, IndexError):
            continue
    return rows


def _descendants(parent: int, rows: Mapping[int, tuple[int, int, int]]) -> set[int]:
    owned = {parent}
    while True:
        added = {pid for pid, row in rows.items() if row[0] in owned} - owned
        if not added:
            return owned - {parent}
        owned.update(added)


def _reap_owned(before: set[int], worker_pid: int) -> bool:
    # This dedicated checker becomes a subreaper before spawning its one worker.
    # Only new descendants, with their birth ticks rechecked, are signalled.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        rows = _process_table()
        owned = _descendants(os.getpid(), rows) - before
        if worker_pid in owned and rows[worker_pid][2] == worker_pid:
            current = _process_table().get(worker_pid)
            if current is not None and current[1] == rows[worker_pid][1]:
                try:
                    os.killpg(worker_pid, sig)
                except ProcessLookupError:
                    pass
        for pid in sorted(owned, reverse=True):
            current = _process_table().get(pid)
            if current is not None and current[1] == rows[pid][1]:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            for pid in owned:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            if not (_descendants(os.getpid(), _process_table()) - before):
                return True
            time.sleep(0.02)
    return not (_descendants(os.getpid(), _process_table()) - before)


def _native_worker(send: Any, call: Mapping[str, Any]) -> None:
    try:
        os.setsid()
        from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
        result = PortalImplementationDaemon._validation_command_runner(**dict(call))
        if len(json.dumps(result)) > 8_000_000:
            raise ValueError("native_output_limit")
        send.send(result)
    except subprocess.TimeoutExpired as exc:
        parts = [item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item or "")
                 for item in (exc.stdout, exc.stderr)]
        send.send({"returncode": 124, "timed_out": True, "error": "subprocess_timeout",
                   "output": "\n".join(parts)[-2_000_000:]})
    except BaseException as exc:
        send.send({"returncode": 78, "error": type(exc).__name__, "reason": "owned_native_worker_failed"})
    finally:
        send.close()


def _owned_native_runner(*, spec: Any, workspace_path: Path, timeout_seconds: float,
                         environment: dict[str, str]) -> dict[str, Any]:
    if sys.platform != "linux":
        raise RuntimeError("owned_native_cleanup_unavailable")
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) or libc.prctl(36, 1, 0, 0, 0):
        raise RuntimeError("owned_native_subreaper_unavailable")
    before = _descendants(os.getpid(), _process_table())
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    worker = context.Process(target=_native_worker, args=(send, {"spec": spec, "workspace_path": workspace_path,
        "timeout_seconds": max(0.001, timeout_seconds - min(2.0, timeout_seconds / 4)),
        "environment": environment}))
    result: dict[str, Any] = {}
    try:
        worker.start()
        send.close()
        if receive.poll(max(0.001, timeout_seconds)):
            result = receive.recv()
        else:
            result = {"returncode": 124, "timed_out": True, "error": "subprocess_timeout"}
    except (OSError, EOFError) as exc:
        result = {"returncode": 78, "reason": "owned_native_worker_unavailable", "error": type(exc).__name__}
    finally:
        receive.close()
        cleaned = _reap_owned(before, worker.pid or 0)
        worker.join(timeout=1)
        libc.prctl(36, previous.value, 0, 0, 0)
    result["owned_process_cleanup"] = {"quiescent": cleaned, "canonical_native_delegate": True}
    if not cleaned:
        result.update(returncode=78, error="owned_children_not_quiescent")
    return result


def _validation_environment(root: Path, guard_dir: Path) -> dict[str, str]:
    from integrations.ipfs_accelerate.improvement_runner import _native_modules
    _native_modules(root)
    from ipfs_accelerate_py.agent_supervisor.validation import validation_runtime as runtime
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import build_validation_environment, validation_environment_for_runner
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    source = dict(os.environ)
    environment = build_validation_environment(source)
    roots = [root]
    for package in ("ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py"):
        dependency = root / "external" / package
        if not (dependency / ".git").exists() or not (dependency / package / "__init__.py").is_file():
            raise ValueError("qualified_dependency_source_unavailable:" + package)
        roots.append(dependency.resolve(strict=True))
    if Path(native.__file__).resolve().parents[3] != roots[1]:
        raise ValueError("native_source_origin_mismatch")
    # Preserve approved installed SDK/Data/Kit dependencies selected by the
    # existing Native environment builder; never graft a package from elsewhere.
    roots += [Path(p) for p in environment.get("PYTHONPATH", "").split(os.pathsep) if p]
    inherited_launcher = source.get("PYTHON", "")
    inherited_paths = native_memfd_approved_paths(inherited_launcher, source, runtime=runtime,
        python=environment["IPFS_ACCELERATE_VALIDATION_PYTHON_EXECUTABLE"], candidate_root=root)
    if inherited_paths is not None:
        # A raw-no-site child cannot rediscover its producer's approved SDK
        # distribution roots. Retain them only after independently comparing
        # the immutable inherited launcher with Native's actual source recipe.
        roots.extend(inherited_paths)
    environment["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(str(p.resolve(strict=True)) for p in roots))
    environment.update({GUARD_ENV: str(guard_dir), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                        "COMMON_CRAWL_AUTO_CLONE_SOURCE": "0", "PYTHONDONTWRITEBYTECODE": "1"})
    return validation_environment_for_runner(environment, native.PortalImplementationDaemon._validation_command_runner)


def module_case_population(paths: Sequence[str], nodeids: Sequence[str]) -> tuple[dict[str, list[str]], str]:
    """Each selected full module needs its own nonempty measured population."""
    population: dict[str, list[str]] = {path: [] for path in paths}
    if any(not isinstance(node, str) for node in nodeids):
        return population, "module_case_identity_malformed"
    if len(population) != len(paths) or len(set(nodeids)) != len(nodeids):
        return population, "module_case_identity_malformed"
    for node in nodeids:
        if not isinstance(node, str) or "::" not in node:
            return population, "module_case_identity_malformed"
        module = node.split("::", 1)[0]
        if module not in population:
            return population, "unselected_module_case:" + module
        population[module].append(node)
    missing = sorted(path for path, members in population.items() if not members)
    return population, "selected_module_zero_cases:" + ",".join(missing) if missing else ""


def measure_current_closure(root: Path, runtime_dir: Path, *, timeout_seconds: float = TOTAL_BUDGET_SECONDS) -> dict[str, Any]:
    if not 0 < timeout_seconds <= TOTAL_BUDGET_SECONDS:
        raise ValueError("mandatory_budget_out_of_range")
    from integrations.ipfs_accelerate.improvement_runner import measure_behavioral_command
    from integrations.ipfs_accelerate.improvement_plan import _host_evidence_reason
    manifest = mandatory_manifest(root)
    start = time.monotonic()
    outcomes = {}
    all_nodes: set[str] = set()
    issues = []
    for group, paths in manifest.items():
        remaining = timeout_seconds - (time.monotonic() - start)
        if remaining <= 0:
            issues.append("mandatory_budget_exhausted:" + group)
            continue
        owned = _owned_directory(Path(tempfile.mkdtemp(prefix=group + "-", dir=runtime_dir)))
        environment = _validation_environment(root, owned)
        # Full modules are measured independently; no -k filtering or copied counts.
        command = "python -m pytest -q --run-llm --run-network --run-heavy --basetemp=" + shlex.quote(str(owned / "cases")) + " " + shlex.join(paths)
        task = {"id": "CIMP-RELEASE-CURRENT", "targets": [*BOUND_SOURCE_PATHS, *paths],
                "validation_commands": [command], "depends_on": []}
        prefixed = "PYTHONPATH=" + shlex.quote(environment["PYTHONPATH"]) + " " + command
        observation = measure_behavioral_command(root, owned / "measurements", task, prefixed,
            runner=_owned_native_runner, environment=environment, timeout_seconds=max(0.001, remaining - 3),
            declared_command=command, context={"require_child_guard": True,
                "pytest_guard_plugin": "integrations.ipfs_accelerate.release_guard"})
        reason = _host_evidence_reason(observation, task)
        measured = observation["host_measurement"]
        for item in measured.get("results", []):
            native_path = Path(measured["run_path"]) / (item["mode"] + "-native-result.json")
            native_result = json.loads(native_path.read_text())
            if native_result.get("owned_process_cleanup", {}).get("quiescent") is not True:
                reason = "owned_children_not_quiescent"
        guards = [a for a in measured["artifacts"] if a["path"].endswith(".guard.json")]
        if (not reason and (len(guards) != 2 or any(
                json.loads(Path(a["path"]).read_text()).get("kernel_network_deny") is not True for a in guards))):
            reason = "kernel_effect_guard_unverified"
        nodes = observation.get("required_nodeids", [])
        module_population, module_reason = module_case_population(paths, nodes)
        reason = reason or module_reason
        if set(nodes) & all_nodes:
            reason = "duplicate_cross_group_case"
        all_nodes.update(nodes)
        if reason:
            issues.append(group + ":" + reason)
        outcomes[group] = {"status": "VERIFIED" if not reason else "UNVERIFIED", "reason": reason,
            "manifest": paths, "required_nodeids": nodes, "cases": observation.get("cases", []),
            "module_case_population": module_population,
            "measurement_record": observation.measurement_record, "source_digest": measured["source_after"]["digest"],
            "artifact_bindings": measured["artifacts"], "completion_authority": False}
    if set(outcomes) != set(manifest) or not all_nodes:
        issues.append("incomplete_mandatory_population")
    return {"status": "VERIFIED" if not issues else "UNVERIFIED", "issues": issues,
            "groups": outcomes, "required_case_count": len(all_nodes), "completion_authority": False,
            "budget_seconds": timeout_seconds, "execution_mode": "direct_native_measurement",
            "verification_this_invocation": {
                "mandatory_case_execution_count": sum(len(row["cases"]) for row in outcomes.values()),
                "execution_count_basis": "returned_measured_case_outcomes; unrecorded_partial_execution_not_claimed",
                "completion_authority": False}}


def _global_current_collection(root: Path, runtime_dir: Path, manifest: Mapping[str, Sequence[str]],
                               source: Mapping[str, Any]) -> dict[str, Any]:
    """Independently collect the entire closure with the real Native executor."""
    from types import SimpleNamespace
    from integrations.ipfs_accelerate.improvement_runner import _atomic_json, _pytest_instrument, _read_catalog
    from integrations.ipfs_accelerate.release_evidence import _current_source_identity
    owned = _owned_directory(runtime_dir / "global-collect", create=True)
    environment = _validation_environment(root, owned)
    modules = sorted(path for paths in manifest.values() for path in paths)
    command = ("python -m pytest -q --run-llm --run-network --run-heavy --basetemp="
               + shlex.quote(str(owned / "cases")) + " " + shlex.join(modules))
    phase, catalog = owned / "collect.json", owned / "collect.duckdb"
    options = ["-p", "integrations.ipfs_accelerate.release_guard", "-p", "integrations.ipfs_accelerate.improvement_plan",
               "-p", "ipfs_accelerate_py.testing.pytest_ast_seal", "--complaint-evidence-path=" + str(phase), "--collect-only"]
    instrumented = _pytest_instrument(command, options,
        pythonpath=(root, root / "external/ipfs_accelerate_py"))
    instrumented = ("export IPFS_ACCELERATE_PYTEST_SEAL_DUCKDB=" + shlex.quote(str(catalog))
        + " PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS='' PYTEST_PLUGINS='' && " + instrumented)
    result = _owned_native_runner(spec=SimpleNamespace(command=instrumented, raw_command=command),
        workspace_path=root, timeout_seconds=TOTAL_BUDGET_SECONDS, environment=environment)
    _atomic_json(owned / "collect-native-result.json", result)
    if (result.get("returncode") != 0 or result.get("timed_out")
            or result.get("validation_python_launcher", {}).get("sealed") is not True
            or result.get("owned_process_cleanup", {}).get("quiescent") is not True):
        raise ValueError("qualification_global_native_collection_failed")
    collection = json.loads(phase.read_bytes())
    guard_path = owned / "collect.guard.json"
    guard = json.loads(guard_path.read_bytes())
    if (collection.get("exitstatus") != 0 or guard.get("exitstatus") != 0
            or guard.get("kernel_network_deny") is not True
            or guard.get("network_process_dispatch_permitted") is not False):
        raise ValueError("qualification_global_collection_guard_unverified")
    nodes = collection.get("nodeids", [])
    _, reason = module_case_population(modules, nodes)
    seals, imported = _read_catalog(catalog, repo_root=root)
    if reason or seals or not imported:
        raise ValueError("qualification_global_collection_population_unverified:" + reason)
    after = _current_source_identity(root, sys.modules[__name__])
    if after != source:
        raise ValueError("qualification_source_changed_during_global_collection")
    return {"required_nodeids": nodes,
        "artifacts": [{"path": str(path), "sha256": _hash(path)} for path in
            (phase, catalog, guard_path, owned / "collect-native-result.json")],
        "source_bindings_before": dict(source), "source_bindings_after": after, "completion_authority": False}


def produce_current_release_qualification(root: Path, runtime_dir: Path, *,
                                           producer_path: Path, producer_sha256: str) -> dict[str, Any]:
    """Execute a finite serial source qualification; never publish its binding."""
    from integrations.ipfs_accelerate.improvement_runner import _atomic_json, measure_behavioral_command
    from integrations.ipfs_accelerate.improvement_plan import _host_evidence_reason
    from integrations.ipfs_accelerate.release_evidence import _current_shard_plan, _current_source_identity
    root, runtime_dir = _unalias(root), _owned_directory(runtime_dir)
    producer_path = _unalias(producer_path)
    if (".git" in runtime_dir.parts or _within(runtime_dir, root)
            or not producer_path.is_file() or _hash(producer_path) != producer_sha256):
        raise ValueError("qualification_producer_scope_unverified")
    if any(runtime_dir.iterdir()):
        raise ValueError("qualification_runtime_must_be_fresh")
    contract, _ = committed_report_contract(root)
    if contract:
        raise ValueError(contract)
    checker = sys.modules[__name__]
    source = _current_source_identity(root, checker)
    manifest = mandatory_manifest(root)
    plan = _current_shard_plan(manifest, runtime_dir)
    targets = sorted({*BOUND_SOURCE_PATHS, REPORT_RELATIVE, SPEC_RELATIVE,
                      *(path for paths in manifest.values() for path in paths)})
    executions, union = [], set()
    old_umask = os.umask(0o077)
    try:
        global_collection = _global_current_collection(root, runtime_dir, manifest, source)
        for shard in plan["shards"]:
            if _current_source_identity(root, checker) != source:
                raise ValueError("qualification_source_changed_before_shard:" + shard["id"])
            owned = _owned_directory(runtime_dir / shard["id"], create=True)
            environment = _validation_environment(root, owned)
            command = shard["command"]
            task = {"id": "CIMP-RELEASE-CURRENT", "targets": targets,
                    "validation_commands": [command], "depends_on": []}
            observation = measure_behavioral_command(root, owned / "measurements", task,
                "PYTHONPATH=" + shlex.quote(environment["PYTHONPATH"]) + " " + command,
                runner=_owned_native_runner, environment=environment, timeout_seconds=shard["budget_seconds"],
                declared_command=command, context={"require_child_guard": True,
                    "pytest_guard_plugin": "integrations.ipfs_accelerate.release_guard"})
            reason = _host_evidence_reason(observation, task)
            measured = observation["host_measurement"]
            guards = [row for row in measured["artifacts"] if row["path"].endswith(".guard.json")]
            if (not reason and (len(guards) != 2 or any(
                    json.loads(Path(row["path"]).read_bytes()).get("kernel_network_deny") is not True for row in guards))):
                reason = "kernel_effect_guard_unverified"
            for item in measured.get("results", []):
                actual = json.loads((Path(measured["run_path"]) / (item["mode"] + "-native-result.json")).read_bytes())
                if actual.get("owned_process_cleanup", {}).get("quiescent") is not True:
                    reason = reason or "owned_children_not_quiescent"
            nodes = observation.get("required_nodeids", [])
            _, population_reason = module_case_population(shard["modules"], nodes)
            reason = reason or population_reason
            if union.intersection(nodes):
                reason = reason or "duplicate_cross_shard_case"
            if _current_source_identity(root, checker) != source:
                reason = reason or "qualification_source_changed_after_shard"
            if reason:
                raise ValueError("qualification_shard_failed:" + shard["id"] + ":" + reason)
            union.update(nodes)
            executions.append({"id": shard["id"], "measurement": observation.measurement_record})
        if not union or union != set(global_collection["required_nodeids"]):
            raise ValueError("qualification_global_shard_population_mismatch")
        git = {}
        for field, revision in (("head", "HEAD"), ("tree", "HEAD^{tree}")):
            actual = subprocess.run(["git", "--no-optional-locks", "rev-parse", revision], cwd=root,
                                    capture_output=True, timeout=10, check=True, text=True)
            git[field] = actual.stdout.strip()
        payload = {"schema": "complaint-release-current-source-qualification@1", "execution_root": str(root),
            "execution_git": git, "source": source, "plan": plan, "executions": executions,
            "global_collection": global_collection, "producer": {"path": str(producer_path), "sha256": producer_sha256},
            "completion_authority": False, "provider_dispatched": False, "native_task_completion_claimed": False}
        path = runtime_dir / "qualification.json"
        _atomic_json(path, payload)
        return {"path": str(path), "sha256": _hash(path), "producer_execution_count": len(executions),
                "required_case_count": len(union), "completion_authority": False,
                "fixed_binding_published": False, "native_task_completion_claimed": False}
    finally:
        os.umask(old_umask)


def current_release_coverage(root: Path, runtime_dir: Path, *, phase: str, campaign_state_dir: Path,
                             timeout_seconds: float) -> dict[str, Any]:
    from integrations.ipfs_accelerate.release_evidence import read_current_release_qualification
    coverage = read_current_release_qualification(root, root / SPEC_RELATIVE, campaign_state_dir, phase=phase)
    if coverage is None:
        return measure_current_closure(root, runtime_dir, timeout_seconds=timeout_seconds)
    return coverage


def _context(root: Path, state: Path | None, target: Path | None) -> tuple[Path, Path]:
    state_value = state or (Path(os.environ[STATE_ENV]) if os.environ.get(STATE_ENV) else None)
    target_value = target or (Path(os.environ[TARGET_ENV]) if os.environ.get(TARGET_ENV) else None)
    if state_value is None or target_value is None:
        raise ValueError("owned_campaign_context_missing")
    state_dir = _owned_directory(state_value)
    target_root = _unalias(target_value)
    launcher = json.loads((state_dir / "launcher.json").read_text())
    if Path(str(launcher.get("repo_root", ""))).resolve() != target_root:
        raise ValueError("campaign_target_launcher_mismatch")
    # The bridge further checks plan, source identities, callback commits and
    # the actual existing Native store. Locator strings are never authority.
    return state_dir, target_root


def _assess_requirements(native: Mapping[str, Any], coverage: Mapping[str, Any], *, phase: str) -> dict[str, Any]:
    current = coverage.get("status") == "VERIFIED"
    assessments = {}
    for kind, count in (("goals", 10), ("subgoals", 29)):
        raw = native.get(kind)
        if not isinstance(raw, Mapping) or len(raw) != count:
            raise ValueError("native_requirement_population_unavailable")
        rows = {}
        for identifier, row in raw.items():
            pending = SELF_TASK in row["task_ids"] and phase == "pre-admission"
            other_native = all(native["tasks"][task_id].get("native_completed") is True
                and native["tasks"][task_id].get("callback_verified") is True
                and native["tasks"][task_id].get("integration_verified") is True
                for task_id in row["task_ids"] if not (pending and task_id == SELF_TASK))
            rows[identifier] = {"evidence_requirement_ids": row["evidence_requirement_ids"],
                "task_ids": row["task_ids"], "status": "SELF_PENDING" if pending and other_native and current else
                    "COVERED" if row.get("native_completion_satisfied") is True and current else "UNVERIFIED",
                "assessment_kind": "historical_native_and_current_semantic_requirement_coverage",
                "formal_lifecycle_completion_claimed": False, "completion_authority": False}
        assessments[kind] = rows
    return assessments


def evaluate_release(native: Mapping[str, Any], coverage: Mapping[str, Any], *, phase: str,
                     report_sha256: str, source: Mapping[str, str]) -> dict[str, Any]:
    if phase not in {"pre-admission", "post-completion"}:
        raise ValueError("phase_argument")
    issues = list(native.get("issues", []))
    if native.get("schema") != "complaint-native-release-evidence@1" or native.get("completion_authority") is not False:
        issues.append({"code": "native_reader_contract_unavailable", "kind": "unknown"})
    if native.get("native_completion_satisfied") is not True:
        issues.append({"code": "native_completion_not_satisfied", "kind": "missing"})
    if coverage.get("status") != "VERIFIED" or coverage.get("issues"):
        issues.append({"code": "current_source_closure_unverified", "kind": "missing"})
    rows = native.get("tasks", {})
    if len(rows) != 58:
        issues.append({"code": "native_task_population", "kind": "unknown"})
    if phase == "pre-admission" and rows.get(SELF_TASK, {}).get("native_completed") is True:
        issues.append({"code": "self_already_completed_requires_post_completion", "kind": "unknown"})
    if phase == "post-completion" and native.get("integration_proof", {}).get("verified") is not True:
        issues.append({"code": "real_integration_proof_unverified", "kind": "missing"})
    for task_id, row in rows.items():
        if phase == "pre-admission" and task_id == SELF_TASK:
            continue
        if (not row.get("canonical_task_cid") or row.get("native_completed") is not True
                or row.get("callback_verified") is not True or row.get("integration_verified") is not True
                or row.get("historical_evidence", {}).get("status") != "HISTORICAL"):
            issues.append({"code": "required_native_proof_incomplete", "kind": "missing", "task_id": task_id})
    assessments = _assess_requirements(native, coverage, phase=phase)
    unresolved = sorted(task_id for task_id, row in rows.items() if row.get("native_completed") is not True)
    if phase == "pre-admission" and unresolved != [SELF_TASK]:
        issues.append({"code": "pre_admission_pending_population", "kind": "missing"})
    if phase == "post-completion" and unresolved:
        issues.append({"code": "post_completion_unresolved_required_work", "kind": "missing"})
    passed = not issues
    return {"schema": SCHEMA, "phase": phase, "passed": passed,
        "release_qualified": passed and phase == "post-completion", "self_completion_pending": phase == "pre-admission" or not all(
            rows.get(SELF_TASK, {}).get(field) is True for field in ("native_completed", "callback_verified", "integration_verified")),
        "pending_task_ids": [SELF_TASK] if phase == "pre-admission" else unresolved,
        "completion_authority": False, "issues": issues, "source_bindings": dict(source), "hash_scope": HASH_SCOPE,
        "committed_report_sha256": report_sha256, "historical_native_evidence": dict(native),
        "current_source_semantic_coverage": dict(coverage), "requirement_assessments": assessments,
        "optional_live": [{"name": name, "status": "not_run", "executed": False} for name in ("grok", "local-node", "replica")]}


def write_runtime_report(path: Path, result: Mapping[str, Any], *, source_roots: Sequence[Path], runtime_root: Path | None = None) -> None:
    path = _unalias(path)
    if (".git" in path.parts or any(_within(path, _unalias(root)) for root in source_roots)):
        raise ValueError("runtime_report_inside_source")
    if runtime_root is not None and not _within(path, _owned_directory(runtime_root)):
        raise ValueError("runtime_report_outside_owned_runtime")
    parent = _owned_directory(path.parent, create=True)
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("runtime_report_not_owned")
        if json.loads(path.read_text()).get("schema") != RUNTIME_SCHEMA:
            raise ValueError("runtime_report_foreign_artifact")
    descriptor, temporary = tempfile.mkstemp(prefix=".release-", dir=parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump({**dict(result), "schema": RUNTIME_SCHEMA}, handle, indent=2, sort_keys=True)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def build_result(root: Path, *, phase: str, campaign_state_dir: Path, target_source_root: Path,
                 runtime_dir: Path, suite_timeout: float = TOTAL_BUDGET_SECONDS) -> dict[str, Any]:
    started = time.monotonic()
    from integrations.ipfs_accelerate.release_evidence import collect_native_release_evidence
    before = (root / REPORT_RELATIVE).read_bytes()
    contract, report_sha = committed_report_contract(root)
    if contract:
        raise ValueError(contract)
    bindings = source_bindings(root)
    native = collect_native_release_evidence(root, root / SPEC_RELATIVE, campaign_state_dir, phase=phase)
    if phase == "post-completion":
        # A self-asserted report hash is insufficient. The actual committed
        # report bytes must occur in REL03's genuine Native integration chain.
        proof = native.get("integration_proof", {})
        commits = native.get("tasks", {}).get(SELF_TASK, {}).get("historical_integration_commits", [])
        valid_commits = [value for value in commits if isinstance(value, str) and len(value) == 40
                         and all(char in "0123456789abcdef" for char in value)]
        current = subprocess.run(["git", "--no-optional-locks", "show", "HEAD:" + REPORT_RELATIVE],
            cwd=root, capture_output=True, timeout=10, check=False)
        matched = False
        if proof.get("verified") is True and proof.get("campaign_repo_root") == str(target_source_root):
            for commit in valid_commits:
                observed = subprocess.run(["git", "--no-optional-locks", "show", commit + ":" + REPORT_RELATIVE],
                    cwd=target_source_root, capture_output=True, timeout=10, check=False)
                matched = matched or observed.returncode == 0 and observed.stdout == before
        if current.returncode != 0 or current.stdout != before or not matched:
            native = {**native, "native_completion_satisfied": False,
                "issues": [*native.get("issues", []), {"code": "committed_pre_report_not_bound_to_native_rel03_integration", "kind": "missing"}]}
    remaining = suite_timeout - (time.monotonic() - started) - 5
    if remaining <= 0:
        raise ValueError("mandatory_budget_exhausted_before_measurement")
    coverage = current_release_coverage(root, runtime_dir, phase=phase,
        campaign_state_dir=campaign_state_dir, timeout_seconds=remaining)
    if (root / REPORT_RELATIVE).read_bytes() != before or source_bindings(root) != bindings:
        raise ValueError("source_or_committed_report_mutated")
    return evaluate_release(native, coverage, phase=phase, report_sha256=report_sha, source=bindings)


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("pre-admission", "post-completion"), default="post-completion")
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--campaign-state-dir", type=Path)
    parser.add_argument("--target-source-root", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--runtime-report", type=Path)
    parser.add_argument("--suite-timeout", type=float, default=TOTAL_BUDGET_SECONDS)
    parser.add_argument("--produce-current-qualification", action="store_true",
        help="execute the finite serial qualification plan; do not publish the fixed host binding")
    args = parser.parse_args(args_list)
    root = (args.repo_root or repo_root_from()).resolve()
    # Direct script execution must import this candidate, not an editable install.
    sys.path.insert(0, str(root))
    fenced = False
    try:
        phase = parse_phase(args_list)
        if not 0 < args.suite_timeout <= TOTAL_BUDGET_SECONDS:
            raise ValueError("mandatory_budget_out_of_range")
        state, target = _context(root, args.campaign_state_dir, args.target_source_root)
        runtime_base = args.runtime_dir or (Path(os.environ["COMPLAINT_INTAKE_RELEASE_RUNTIME_DIR"])
            if os.environ.get("COMPLAINT_INTAKE_RELEASE_RUNTIME_DIR") else
            Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "complaint-intake-release")
        runtime_base = _unalias(runtime_base)
        if ".git" in runtime_base.parts:
            raise ValueError("runtime_directory_inside_source")
        if any(_within(runtime_base, item) for item in (root, target)):
            raise ValueError("runtime_directory_inside_source")
        runtime = _owned_directory(runtime_base, create=True)
        # Fence this checker independently of its producer. The development
        # worker's provider routing is untouched; descendants inherit the deny.
        _kernel_network_deny()
        fenced = True
        if args.produce_current_qualification:
            if args.suite_timeout != TOTAL_BUDGET_SECONDS:
                raise ValueError("producer_uses_fixed_per_shard_budget")
            owned = _owned_directory(Path(tempfile.mkdtemp(prefix="current-qualification-", dir=runtime)))
            pin = produce_current_release_qualification(root, owned,
                producer_path=Path(__file__).resolve(), producer_sha256=_hash(Path(__file__).resolve()))
            result = {"schema": "complaint-release-current-qualification-production@1", "phase": phase,
                      "passed": True, "release_qualified": False, "completion_authority": False,
                      "qualification": pin, "fixed_binding_published": False,
                      "native_task_completion_claimed": False}
        else:
            result = build_result(root, phase=phase, campaign_state_dir=state, target_source_root=target,
                                  runtime_dir=runtime, suite_timeout=args.suite_timeout)
        result["offline_checker_fence"] = {"kernel_network_deny": True,
            "inherited_by_children": True, "completion_authority": False}
        if result["release_qualified"]:
            write_runtime_report(args.runtime_report or runtime / "post-completion.json", result,
                                 source_roots=(root, target), runtime_root=runtime)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(json.dumps({"schema": SCHEMA, "phase": args.phase, "passed": False, "release_qualified": False,
                          "completion_authority": False, "offline_checker_fence_applied": fenced,
                          "reason": type(exc).__name__ + ":" + str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
