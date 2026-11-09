"""Bounded offline characterization of the existing terminal intake.

This module is a baseline smoke, not product acceptance. A passing PTY run
only shows that two synthetic answers pause and resume. Known intake gaps stay
classified as gaps in the baseline receipt.

Diagnostics redact synthetic answer text so the same helper does not print
session payloads if the harness is later pointed at a real session.
"""

from __future__ import annotations

import fcntl
import importlib
import json
import os
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.private_session_assertions import assert_private_session_frame, private_session_path


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = REPO_ROOT / "docs" / "task_boards" / "complaint_tui_baseline_receipt.json"
DEADLINE_SECONDS = 15.0
CANONICAL_STARTUP_SECONDS = 30.0
PAUSE_MESSAGE = "Chat paused. Resume with the same user ID to continue the saved intake."
SMOKE_USER_ID = "pty-synthetic-cimp-tui-01"
EOF_USER_ID = "pty-synthetic-eof"
NARRATIVE_USER_ID = "pty-synthetic-narrative"
UNKNOWN_USER_ID = "pty-synthetic-unknown"
PARTY_ANSWER = "Jordan Example"
CANONICAL_ANSWER = "2024-03-04"
OPPOSING_ANSWER = "Acme Company"
NARRATIVE = "My landlord evicted me after my accommodation request."
UNKNOWN_ANSWER = "unknown"
REDACTED = "[redacted]"
_SENSITIVE_JSON_KEYS = (
    "answer",
    "party_name",
    "opposing_party",
    "protected_activity",
    "adverse_action",
    "timeline",
    "harm",
    "court_header",
    "content",
    "case_synopsis",
    "message",
    "placeholder",
    "prompt",
    "original_complaint",
    "narrative",
    "revision",
    "revisions",
    "text",
)

CHILD_SCRIPT = r"""
import importlib
import json
import os
import sys
from pathlib import Path

def _install_guards():
    net = importlib.import_module("socket")
    process = importlib.import_module("subprocess")

    class _GuardedSocket(net.socket):
        def connect(self, address):
            raise RuntimeError("network connect blocked")

        def connect_ex(self, address):
            raise RuntimeError("network connect blocked")

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("provider process blocked")

    net.socket = _GuardedSocket
    net.create_connection = _blocked
    class _BlockedPopen:
        @classmethod
        def __class_getitem__(cls, _item):
            return cls
        def __new__(cls, *_args, **_kwargs):
            return _blocked()
    process.Popen = _BlockedPopen
    process.call = _blocked
    process.check_call = _blocked
    process.check_output = _blocked
    process.run = _blocked
    os.system = _blocked
    for name in (
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "posix_spawn",
        "posix_spawnp",
    ):
        if hasattr(os, name):
            setattr(os, name, _blocked)
    return net, process, _GuardedSocket, _BlockedPopen

net, process, _GuardedSocket, _BlockedPopen = _install_guards()
# Use the installed real library without ctypes spawning ldconfig under the
# intentionally absolute process denial. No process or library implementation
# is faked; only this known library's discovery path is supplied explicitly.
import ctypes.util
import stat
_magic_path = None
for _candidate in (Path("/lib"), Path("/usr/lib")):
    for _alias in sorted(_candidate.glob("*/libmagic.so.1"))[:16]:
        _resolved = _alias.resolve(strict=True)
        _info = _resolved.stat()
        if _info.st_uid == 0 and stat.S_ISREG(_info.st_mode) and not (_info.st_mode & 0o022):
            _magic_path = _resolved
            break
    if _magic_path is not None:
        break
assert _magic_path is not None, "installed libmagic fixture dependency unavailable"
_real_find_library = ctypes.util.find_library
def _fixture_find_library(name):
    return str(_magic_path) if name == "magic" else _real_find_library(name)
ctypes.util.find_library = _fixture_find_library
repo_root = os.environ["TUI_BASELINE_REPO_ROOT"]
if repo_root not in sys.path:
    sys.path.insert(1, repo_root)

session_dir = Path(os.environ["TUI_BASELINE_SESSION_DIR"])
user_id = os.environ["TUI_BASELINE_USER_ID"]
max_turns = 2
if not isinstance(max_turns, int):
    raise SystemExit("max_turns must be a real integer")

import applications.complaint_workspace as workspace

workspace._SESSION_DIR = session_dir
import applications.complaint_cli as cli

cli.service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
if cli.service.private_key_status()["status"] == "absent":
    cli.service.initialize_private_keys(protection="passphrase", passphrase="synthetic-pty-fixture-passphrase")
else:
    cli.service.unlock_private_keys(passphrase="synthetic-pty-fixture-passphrase")
cli.service.ensure_private_case_key(user_id, user_id)
proof = {
    "entrypoint": "applications.complaint_cli.chat",
    "max_turns": max_turns,
    "max_turns_is_int": True,
    "user_id": user_id,
    "network_guard_active": net.socket is _GuardedSocket,
    "process_guard_active": process.Popen is _BlockedPopen,
}
proof_path = Path(os.environ["TUI_BASELINE_PROOF"])
with proof_path.open("w", encoding="utf-8") as handle:
    json.dump(proof, handle)
    handle.flush()
    os.fsync(handle.fileno())

cli.chat(user_id=user_id, max_turns=max_turns)
"""

CANONICAL_CHILD_SCRIPT = r"""
import importlib
import json
import os
import sys
from pathlib import Path

def _install_guards():
    net = importlib.import_module("socket")
    process = importlib.import_module("subprocess")

    class _GuardedSocket(net.socket):
        def connect(self, address):
            raise RuntimeError("network connect blocked")

        def connect_ex(self, address):
            raise RuntimeError("network connect blocked")

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("provider process blocked")

    net.socket = _GuardedSocket
    net.create_connection = _blocked
    class _BlockedPopen:
        # Preserve Popen[T] annotations during cold optional imports while
        # refusing every actual provider/process construction.
        @classmethod
        def __class_getitem__(cls, _item):
            return cls
        def __new__(cls, *_args, **_kwargs):
            return _blocked()
    process.Popen = _BlockedPopen
    process.call = _blocked
    process.check_call = _blocked
    process.check_output = _blocked
    process.run = _blocked
    os.system = _blocked
    for name in (
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "posix_spawn",
        "posix_spawnp",
    ):
        if hasattr(os, name):
            setattr(os, name, _blocked)
    return net, process, _GuardedSocket, _BlockedPopen

net, process, _GuardedSocket, _BlockedPopen = _install_guards()
# Use the installed real library without ctypes spawning ldconfig under the
# intentionally absolute process denial. No process or library implementation
# is faked; only this known library's discovery path is supplied explicitly.
import ctypes.util
import stat
_magic_path = None
for _candidate in (Path("/lib"), Path("/usr/lib")):
    for _alias in sorted(_candidate.glob("*/libmagic.so.1"))[:16]:
        _resolved = _alias.resolve(strict=True)
        _info = _resolved.stat()
        if _info.st_uid == 0 and stat.S_ISREG(_info.st_mode) and not (_info.st_mode & 0o022):
            _magic_path = _resolved
            break
    if _magic_path is not None:
        break
assert _magic_path is not None, "installed libmagic fixture dependency unavailable"
_real_find_library = ctypes.util.find_library
def _fixture_find_library(name):
    return str(_magic_path) if name == "magic" else _real_find_library(name)
ctypes.util.find_library = _fixture_find_library
repo_root = os.environ["TUI_BASELINE_REPO_ROOT"]
if repo_root not in sys.path:
    sys.path.insert(1, repo_root)

session_dir = Path(os.environ["TUI_BASELINE_SESSION_DIR"])
user_id = os.environ["TUI_BASELINE_USER_ID"]
max_turns = 2
if not isinstance(max_turns, int):
    raise SystemExit("max_turns must be a real integer")

import applications.complaint_workspace as workspace

workspace._SESSION_DIR = session_dir
import applications.complaint_cli as cli

cli.service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
if cli.service.private_key_status()["status"] == "absent":
    cli.service.initialize_private_keys(protection="passphrase", passphrase="synthetic-pty-fixture-passphrase")
else:
    cli.service.unlock_private_keys(passphrase="synthetic-pty-fixture-passphrase")
cli.service.ensure_private_case_key(user_id, user_id)
# Explicit dependency injection for this synthetic PTY only. The real shared
# mediator, graph builder, policy boundary and encrypted session writer remain.
_real_mediator_factory = cli.service._mediator_for_shared_interview
_backend_calls = []
def _fixture_backend(prompt, complaint_privacy_context=None, **kwargs):
    assert isinstance(complaint_privacy_context, dict)
    _backend_calls.append(True)
    return '{"entities":[],"relationships":[]}'
def _fixture_mediator(user_id, case_id):
    mediator = _real_mediator_factory(user_id, case_id)
    mediator.backends = [_fixture_backend]
    return mediator
cli.service._mediator_for_shared_interview = _fixture_mediator
proof = {
    "entrypoint": "applications.complaint_cli.chat",
    "max_turns": max_turns,
    "max_turns_is_int": True,
    "user_id": user_id,
    "network_guard_active": net.socket is _GuardedSocket,
    "process_guard_active": process.Popen is _BlockedPopen,
}
proof_path = Path(os.environ["TUI_BASELINE_PROOF"])
def _write_proof():
    with proof_path.open("w", encoding="utf-8") as handle:
        json.dump(proof, handle)
        handle.flush()
        os.fsync(handle.fileno())
_real_turn = cli.service.run_intake_chat_turn
def _observed_turn(*args, **kwargs):
    payload = _real_turn(*args, **kwargs)
    inquiry = payload.get("inquiry") or {}
    interview = payload.get("interview") or {}
    projection = (payload.get("session") or {}).get("shared_interview") or {}
    proof["current_inquiry"] = {
        "id": inquiry.get("question_id"), "kind": inquiry.get("kind"),
        "revision": inquiry.get("revision"),
    }
    proof["session_id"] = interview.get("session_id")
    proof["expected_question_revision"] = interview.get("expected_question_revision")
    proof["answered_inquiries"] = projection.get("answered_inquiries") or []
    proof["interview_status"] = interview.get("status")
    proof["legal_sufficiency"] = interview.get("legal_sufficiency")
    proof["fixture_backend_calls"] = len(_backend_calls)
    _write_proof()
    return payload
cli.service.run_intake_chat_turn = _observed_turn
# Cold construction is measured separately; every import/process guard is
# already active, and no narrative or answer is submitted before readiness.
import time
cli.service._mediator_for_shared_interview(user_id, user_id)
import magic
import hashlib
_loaded_magic = Path(magic.libmagic._name).resolve(strict=True)
assert _loaded_magic == _magic_path
proof["libmagic_path"] = str(_loaded_magic)
proof["libmagic_sha256"] = hashlib.sha256(_loaded_magic.read_bytes()).hexdigest()
proof["ready_for_chat"] = True
proof["ready_monotonic"] = time.monotonic()
_write_proof()
cli.chat(user_id=user_id, max_turns=max_turns)
"""


@dataclass
class _PtyResult:
    returncode: int
    transcript: str
    elapsed_seconds: float
    proof: dict
    startup_seconds: float = 0.0
    interaction_seconds: float = 0.0


def _payloads() -> tuple[str, ...]:
    return (PARTY_ANSWER, CANONICAL_ANSWER, OPPOSING_ANSWER, NARRATIVE, UNKNOWN_ANSWER, PAUSE_MESSAGE)


_JSON_PAYLOAD = re.compile(
    r'("(?:'
    + "|".join(re.escape(key) for key in _SENSITIVE_JSON_KEYS)
    + r')"\s*:\s*")(?:\\.|[^"\\])*(")'
)


def _redact(text: str) -> str:
    """Remove synthetic and session-shaped payloads from diagnostic text."""

    redacted = str(text)
    for payload in sorted(_payloads(), key=len, reverse=True):
        if payload:
            redacted = redacted.replace(payload, REDACTED)
    redacted_lines = []
    for line in redacted.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            redacted_lines.append("> " + REDACTED)
            continue
        redacted_lines.append(line)
    redacted = "\n".join(redacted_lines)
    return _JSON_PAYLOAD.sub(lambda match: match.group(1) + REDACTED + match.group(2), redacted)


def _fail(message: str, transcript: str = "") -> None:
    detail = message
    if transcript:
        detail = f"{message}\nredacted_transcript:\n{_redact(transcript)[-1500:]}"
    raise AssertionError(_redact(detail)) from None


def _require_same(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        _fail(f"{label} mismatch; synthetic payload redacted")


def _child_env(home: Path, session_dir: Path, proof_path: Path, user_id: str) -> dict[str, str]:
    env = os.environ.copy()
    prior = env.get("PYTHONPATH", "")
    repo = str(REPO_ROOT)
    parts = [repo]
    if prior:
        parts.extend(entry for entry in prior.split(os.pathsep) if entry and entry != repo)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["HOME"] = str(home)
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_STATE_HOME"] = str(home / ".local" / "state")
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TUI_BASELINE_REPO_ROOT"] = repo
    env["TUI_BASELINE_SESSION_DIR"] = str(session_dir)
    env["TUI_BASELINE_PROOF"] = str(proof_path)
    env["TUI_BASELINE_USER_ID"] = user_id
    for name in (
        "COMPLAINT_USE_IPFS_LLM_ROUTER_STATUS",
        "COMPLAINT_USE_IPFS_LEGAL_STATUS",
        "COMPLAINT_LLM_PROVIDER",
        "COMPLAINT_LLM_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROK_API_KEY",
        "XAI_API_KEY",
        "HUGGING_FACE_HUB_TOKEN",
        "HF_TOKEN",
    ):
        env.pop(name, None)
    return env


def _install_parent_guards(monkeypatch: pytest.MonkeyPatch, script_path: Path) -> None:
    """Block provider processes and network connects; allow one PTY child argv."""

    net = importlib.import_module("socket")
    allowed = [sys.executable, str(script_path)]
    real_popen = subprocess.Popen

    class _GuardedSocket(net.socket):
        def connect(self, address):
            raise RuntimeError("network connect blocked")

        def connect_ex(self, address):
            raise RuntimeError("network connect blocked")

    def _blocked_connection(*_args, **_kwargs):
        raise RuntimeError("network connect blocked")

    def _guarded_popen(cmd, *args, **kwargs):
        argv = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
        if argv != allowed:
            raise RuntimeError("provider process blocked: " + _redact(repr(argv)))
        return real_popen(cmd, *args, **kwargs)

    def _blocked_system(*_args, **_kwargs):
        raise RuntimeError("provider process blocked")

    monkeypatch.setattr(net, "socket", _GuardedSocket)
    monkeypatch.setattr(net, "create_connection", _blocked_connection)
    class _GuardedPopen:
        @classmethod
        def __class_getitem__(cls, _item):
            return cls
        def __new__(cls, cmd, *args, **kwargs):
            return _guarded_popen(cmd, *args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", _GuardedPopen)
    monkeypatch.setattr(os, "system", _blocked_system)
    # Cold optional imports use ctypes' discovery helper, which otherwise
    # spawns ldconfig. Supply its real installed library under the same guard.
    import ctypes.util
    import stat
    magic_path = None
    for directory in (Path("/lib"), Path("/usr/lib")):
        for alias in sorted(directory.glob("*/libmagic.so.1"))[:16]:
            resolved = alias.resolve(strict=True)
            info = resolved.stat()
            if info.st_uid == 0 and stat.S_ISREG(info.st_mode) and not (info.st_mode & 0o022):
                magic_path = resolved
                break
        if magic_path is not None:
            break
    assert magic_path is not None, "installed libmagic fixture dependency unavailable"
    real_find_library = ctypes.util.find_library
    def fixture_find_library(name):
        return str(magic_path) if name == "magic" else real_find_library(name)
    monkeypatch.setattr(ctypes.util, "find_library", fixture_find_library)


def _import_workspace(monkeypatch: pytest.MonkeyPatch, session_dir: Path):
    workspace = importlib.import_module("applications.complaint_workspace")
    monkeypatch.setattr(workspace, "_SESSION_DIR", session_dir)
    cli = sys.modules.get("applications.complaint_cli")
    if cli is not None and hasattr(cli, "service"):
        monkeypatch.setattr(
            cli,
            "service",
            workspace.ComplaintWorkspaceService(root_dir=session_dir),
        )
    return workspace


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _run_pty(
    *,
    script_path: Path,
    home: Path,
    session_dir: Path,
    user_id: str,
    answers: tuple[bytes, ...] = (),
    eof_after_prompt: bool = False,
    canonical: bool = False,
) -> _PtyResult:
    proof_path = session_dir.parent / f"{user_id}-proof.json"
    env = _child_env(home, session_dir, proof_path, user_id)
    master, slave = os.openpty()
    started = time.monotonic()
    interactive_started = None if canonical else started
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        cwd=str(home),
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave)
    flags = fcntl.fcntl(master, fcntl.F_GETFL)
    fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    transcript = bytearray()
    sent = 0
    master_open = True
    returncode = 1
    try:
        while True:
            now = time.monotonic()
            elapsed = now - started
            if canonical and interactive_started is None:
                try:
                    readiness = json.loads(proof_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    readiness = {}
                ready_time = readiness.get("ready_monotonic")
                if readiness.get("ready_for_chat") is True:
                    if not isinstance(ready_time, (int, float)) or not started <= ready_time <= now:
                        _fail("canonical PTY readiness clock is invalid")
                    if ready_time - started > CANONICAL_STARTUP_SECONDS:
                        _fail("canonical cold construction exceeded 30s")
                    interactive_started = float(ready_time)
            phase_elapsed = now - interactive_started if interactive_started is not None else elapsed
            phase_limit = DEADLINE_SECONDS if interactive_started is not None else CANONICAL_STARTUP_SECONDS
            if phase_elapsed > phase_limit or elapsed > CANONICAL_STARTUP_SECONDS + DEADLINE_SECONDS:
                _fail(
                    f"PTY child exceeded its {phase_limit:.0f}s phase deadline",
                    transcript.decode("utf-8", errors="replace"),
                )
            if master_open:
                remaining = max(0.0, phase_limit - phase_elapsed)
                ready, _, _ = select.select([master], [], [], min(0.1, remaining))
                if ready:
                    try:
                        chunk = os.read(master, 8192)
                    except BlockingIOError:
                        chunk = b""
                    except OSError:
                        chunk = b""
                    if chunk:
                        transcript += chunk
            text = bytes(transcript)
            if eof_after_prompt and master_open and b"plain language" in text:
                os.close(master)
                master_open = False
            elif not eof_after_prompt and master_open:
                if sent == 0 and b"plain language" in text:
                    _write_all(master, answers[0] + b"\n")
                    sent += 1
                elif sent == 1 and not canonical and b"bringing the complaint" in text:
                    _write_all(master, answers[1] + b"\n")
                    sent += 1
                elif sent == 1 and canonical:
                    # Synchronize with the actual canonical inquiry, rather
                    # than assuming the former party-name prompt drives chat.
                    try:
                        observed = json.loads(proof_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        observed = {}
                    current = observed.get("current_inquiry") or {}
                    if current.get("kind") == "graph" and str(current.get("id") or "").startswith("inq-"):
                        _write_all(master, answers[1] + b"\n")
                        sent += 1
            if not master_open:
                time.sleep(0.05)
            if proc.poll() is not None:
                if master_open:
                    while True:
                        try:
                            chunk = os.read(master, 8192)
                        except (BlockingIOError, OSError):
                            break
                        if not chunk:
                            break
                        transcript += chunk
                returncode = 1 if proc.returncode is None else int(proc.returncode)
                break
        if proc.poll() is None:
            proc.wait(timeout=max(0.1, DEADLINE_SECONDS - (time.monotonic() - started)))
        returncode = 1 if proc.returncode is None else int(proc.returncode)
    finally:
        if master_open:
            os.close(master)
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=2)
            returncode = 1 if proc.returncode is None else int(proc.returncode)
    elapsed = time.monotonic() - started
    proof: dict = {}
    if proof_path.exists():
        try:
            loaded = json.loads(proof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            proof = loaded
    return _PtyResult(
        returncode=returncode,
        transcript=bytes(transcript).decode("utf-8", errors="replace"),
        elapsed_seconds=elapsed,
        proof=proof,
        startup_seconds=(interactive_started - started) if canonical and interactive_started is not None else 0.0,
        interaction_seconds=(time.monotonic() - interactive_started) if interactive_started is not None else 0.0,
    )


def _session_path(session_dir: Path, user_id: str) -> Path:
    from applications.complaint_workspace import namespace_filename

    return private_session_path(session_dir, user_id)


def _unlocked_service(session_dir: Path, user_id: str):
    """Explicit synthetic operator setup; never a production auto-unlock hook."""
    workspace = importlib.import_module("applications.complaint_workspace")
    service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
    if service.private_key_status()["status"] == "absent":
        service.initialize_private_keys(protection="passphrase", passphrase="synthetic-pty-fixture-passphrase")
    else:
        service.unlock_private_keys(passphrase="synthetic-pty-fixture-passphrase")
    service.ensure_private_case_key(user_id, user_id)
    real_factory = service._mediator_for_shared_interview
    def fixture_backend(prompt, complaint_privacy_context=None, **kwargs):
        assert isinstance(complaint_privacy_context, dict)
        return '{"entities":[],"relationships":[]}'
    def fixture_factory(user_id, case_id):
        mediator = real_factory(user_id, case_id)
        mediator.backends = [fixture_backend]
        return mediator
    service._mediator_for_shared_interview = fixture_factory
    return service


def _load_session(path: Path, user_id: str) -> dict:
    if not path.is_file():
        _fail("persisted session file is absent")
    directory = path.parent
    if path.name == "head.cgpe":
        if directory.parent.name == "joined-revisions":
            directory = directory.parent.parent
        elif directory.name == "joined-revisions":
            directory = directory.parent
        else:
            _fail("session head is outside its known joined repository")
    try:
        payload = _unlocked_service(directory, user_id).get_session(user_id)["session"]
    except Exception:
        _fail("persisted session could not be authenticated through the public service")
    if not isinstance(payload, dict):
        _fail("authenticated session is not an object")
    return payload


def test_diagnostics_redact_synthetic_session_payloads() -> None:
    narrative_marker = "synthetic-narrative-marker-9f3c2a"
    sample = "\n".join(
        (
            "> " + PARTY_ANSWER,
            json.dumps(
                {
                    "party_name": PARTY_ANSWER,
                    "opposing_party": OPPOSING_ANSWER,
                    "message": NARRATIVE,
                    "answer": UNKNOWN_ANSWER,
                    "original_complaint": narrative_marker,
                    "narrative": narrative_marker + "-body",
                    "revision": narrative_marker + "-rev",
                    "revisions": narrative_marker + "-list",
                }
            ),
        )
    )
    redacted = _redact(sample)
    for payload in (
        PARTY_ANSWER,
        OPPOSING_ANSWER,
        NARRATIVE,
        UNKNOWN_ANSWER,
        narrative_marker,
        narrative_marker + "-body",
        narrative_marker + "-rev",
        narrative_marker + "-list",
    ):
        if payload in redacted:
            _fail("diagnostic redaction left a synthetic payload in expanded session text")
    if "> " + REDACTED not in redacted:
        _fail("diagnostic redaction did not replace echoed terminal input")
    nested = json.dumps({"original_complaint": {"text": narrative_marker,
        "revision": 2, "revisions": [{"text": narrative_marker + "-before"},
                                    {"text": narrative_marker + "-after"}]}})
    if narrative_marker in _redact(nested):
        _fail("diagnostic redaction left actual nested narrative/revision text")


def test_pty_smoke_pauses_and_fresh_service_resumes_same_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Current canonical PTY, two valid answers, bounded pause and fresh read."""
    with tempfile.TemporaryDirectory(prefix="tui-baseline-") as raw:
        root = Path(raw)
        session_dir, home = root / "sessions", root / "home"
        session_dir.mkdir()
        home.mkdir()
        script_path = root / "_canonical_smoke_child.py"
        script_path.write_text(CANONICAL_CHILD_SCRIPT, encoding="utf-8")
        _install_parent_guards(monkeypatch, script_path)
        _import_workspace(monkeypatch, session_dir)
        result = _run_pty(script_path=script_path, home=home, session_dir=session_dir,
            user_id=SMOKE_USER_ID, answers=(NARRATIVE.encode(), CANONICAL_ANSWER.encode()), canonical=True)
        if result.returncode != 0 or PAUSE_MESSAGE not in result.transcript:
            _fail("canonical smoke did not pause after two valid answers", result.transcript)
        if result.startup_seconds > CANONICAL_STARTUP_SECONDS or result.interaction_seconds > DEADLINE_SECONDS:
            _fail("canonical smoke exceeded its existing startup/interaction bounds", result.transcript)
        if result.elapsed_seconds > CANONICAL_STARTUP_SECONDS + DEADLINE_SECONDS:
            _fail("canonical smoke exceeded its total bound", result.transcript)
        if result.proof.get("max_turns") != 2 or result.proof.get("max_turns_is_int") is not True:
            _fail("smoke did not exercise the real two-turn limit")
        if not result.proof.get("network_guard_active") or not result.proof.get("process_guard_active"):
            _fail("smoke process/network guards were not active")
        saved = _load_session(_session_path(session_dir, SMOKE_USER_ID), SMOKE_USER_ID)
        _require_same("saved narrative", saved["original_complaint"]["text"], NARRATIVE)
        projection = saved["shared_interview"]
        history = projection["denoiser_history"]
        if sum(entry.get("answer") == CANONICAL_ANSWER for entry in history) != 1:
            _fail("the actual graph answer was not persisted exactly once")
        if saved["intake_answers"].get("party_name"):
            _fail("a graph date answer became a legacy party-name answer")
        assert_private_session_frame(_session_path(session_dir, SMOKE_USER_ID).read_bytes(), NARRATIVE, CANONICAL_ANSWER)
        fresh, again = _unlocked_service(session_dir, SMOKE_USER_ID), _unlocked_service(session_dir, SMOKE_USER_ID)
        if fresh is again:
            _fail("resume did not construct independent services")
        resumed = again.get_session(SMOKE_USER_ID)
        _require_same("fresh read user", resumed["session"]["user_id"], SMOKE_USER_ID)
        _require_same("fresh read canonical projection", resumed["session"]["shared_interview"], projection)
        if (resumed["session"].get("conversation_state") or {}).get("is_complete") is True:
            _fail("paused session was reported complete")


def test_canonical_pty_first_answer_and_cold_encrypted_resume(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Real bounded cold construction, canonical PTY answer, encrypted restart."""

    with tempfile.TemporaryDirectory(prefix="tui-canonical-") as raw:
        root = Path(raw)
        session_dir = root / "sessions"
        home = root / "home"
        session_dir.mkdir()
        home.mkdir()
        script_path = root / "_canonical_pty_child.py"
        script_path.write_text(CANONICAL_CHILD_SCRIPT, encoding="utf-8")
        _install_parent_guards(monkeypatch, script_path)
        workspace = _import_workspace(monkeypatch, session_dir)
        result = _run_pty(
            script_path=script_path,
            home=home,
            session_dir=session_dir,
            user_id=SMOKE_USER_ID,
            answers=(NARRATIVE.encode("utf-8"), CANONICAL_ANSWER.encode("utf-8")),
            canonical=True,
        )
        if result.returncode != 0:
            _fail(f"PTY chat exited {result.returncode}", result.transcript)
        if result.startup_seconds > CANONICAL_STARTUP_SECONDS:
            _fail("canonical cold startup exceeded its independent 30s bound", result.transcript)
        if result.interaction_seconds > DEADLINE_SECONDS:
            _fail("canonical PTY interaction exceeded the retained 15s bound", result.transcript)
        if result.elapsed_seconds > CANONICAL_STARTUP_SECONDS + DEADLINE_SECONDS:
            _fail("canonical PTY exceeded its 45s total bound", result.transcript)
        if result.proof.get("ready_for_chat") is not True:
            _fail("canonical PTY did not publish genuine post-construction readiness")
        if PAUSE_MESSAGE not in result.transcript:
            _fail("pause/resume message was not displayed", result.transcript)
        if result.proof.get("entrypoint") != "applications.complaint_cli.chat":
            _fail("PTY child did not call applications.complaint_cli.chat", result.transcript)
        if result.proof.get("max_turns_is_int") is not True or result.proof.get("max_turns") != 2:
            _fail("PTY child did not pass integer max_turns=2", result.transcript)
        if result.proof.get("network_guard_active") is not True or result.proof.get("process_guard_active") is not True:
            _fail("PTY child did not install provider and network guards before chat", result.transcript)
        _require_same("proof user id", result.proof.get("user_id"), SMOKE_USER_ID)

        saved = _load_session(_session_path(session_dir, SMOKE_USER_ID), SMOKE_USER_ID)
        answers = saved.get("intake_answers") or {}
        narrative_record = saved.get("original_complaint") or {}
        _require_same("user id", saved.get("user_id"), SMOKE_USER_ID)
        _require_same("narrative text", narrative_record.get("text"), NARRATIVE)
        if answers.get("party_name"):
            _fail("canonical graph answer was stored as a legacy party_name answer")
        projection = saved.get("shared_interview") or {}
        answered = projection.get("answered_inquiries") or []
        if len(answered) != 1 or not str(answered[0].get("inquiry_id") or "").startswith("inq-"):
            _fail("PTY did not answer exactly one canonical graph inquiry")
        if result.proof.get("answered_inquiries") != answered:
            _fail("PTY transition proof differs from encrypted shared inquiry history")
        denoiser_history = projection.get("denoiser_history") or []
        if sum(item.get("answer") == CANONICAL_ANSWER for item in denoiser_history) != 1:
            _fail("PTY's first actual answer was not persisted exactly once in the shared engine")
        if result.proof.get("interview_status") != "awaiting_user" or result.proof.get("legal_sufficiency") is not False:
            _fail("PTY did not preserve the honest shared-interview outcome")
        if result.proof.get("current_inquiry", {}).get("kind") != "graph":
            _fail("PTY did not pause at an actual canonical graph inquiry")
        raw = _session_path(session_dir, SMOKE_USER_ID).read_bytes()
        assert_private_session_frame(raw, NARRATIVE, CANONICAL_ANSWER)
        if _session_path(session_dir, SMOKE_USER_ID).stat().st_mode & 0o777 != 0o600:
            _fail("PTY session is not owner-only 0600")
        if answers.get("opposing_party"):
            _fail("opposing party was stored before the structured question")
        if answers.get("protected_activity"):
            _fail("third intake answer was stored before resume")
        history = saved.get("intake_history") or []
        expected_history_ids = ["original_complaint", answered[0]["inquiry_id"]]
        if [item.get("question_id") for item in history] != expected_history_ids:
            _fail("audit history did not preserve exactly the narrative and accepted canonical answer")
        _require_same("narrative provenance history", history[0].get("answer"), NARRATIVE)
        _require_same("canonical answer provenance history", history[1].get("answer"), CANONICAL_ANSWER)
        if any(question_id in answers for question_id in expected_history_ids):
            _fail("canonical answers leaked into the legacy seven-field answer map")

        fresh = _unlocked_service(session_dir, SMOKE_USER_ID)
        again = _unlocked_service(session_dir, SMOKE_USER_ID)
        if fresh is again:
            _fail("resume did not construct a fresh workspace service")
        resumed = again.run_intake_chat_turn(SMOKE_USER_ID, interview_action="resume")
        resumed_session = resumed.get("session") or {}
        resumed_answers = resumed_session.get("intake_answers") or {}
        _require_same("resumed user id", resumed_session.get("user_id"), SMOKE_USER_ID)
        _require_same(
            "resumed narrative",
            (resumed_session.get("original_complaint") or {}).get("text"),
            NARRATIVE,
        )
        if resumed_answers.get("party_name"):
            _fail("resumed graph session populated the legacy party_name answer")
        restored = resumed_session.get("shared_interview") or {}
        _require_same("resumed canonical inquiry history", restored.get("answered_inquiries"), answered)
        _require_same("resumed first answer history", restored.get("denoiser_history"), denoiser_history)
        _require_same("resumed interview id", restored.get("session_id"), projection.get("session_id"))
        next_question = resumed.get("next_question") or {}
        current = result.proof.get("current_inquiry") or {}
        _require_same("resumed graph inquiry", next_question.get("id"), current.get("id"))
        _require_same("resumed graph revision", resumed.get("expected_question_revision"), current.get("revision"))
        if next_question.get("kind") != "graph":
            _fail("fresh encrypted service did not resume the canonical graph inquiry")
        if (resumed_session.get("conversation_state") or {}).get("is_complete") is True:
            _fail("paused session was reported complete")

        # Persist only safe measured qualification metadata; no answer text,
        # prompts or private session projection enters JUnit diagnostics.
        for key, value in {
            "canonical_startup_seconds": result.startup_seconds,
            "canonical_interaction_seconds": result.interaction_seconds,
            "canonical_total_seconds": result.elapsed_seconds,
            "canonical_first_answer_persisted_once": True,
            "canonical_cold_resume_history_equal": True,
            "canonical_session_encrypted": True,
            "canonical_process_network_guards_active": True,
            "canonical_libmagic_path": result.proof.get("libmagic_path"),
            "canonical_libmagic_sha256": result.proof.get("libmagic_sha256"),
        }.items():
            request.node.user_properties.append((key, value))


def _assert_receipt_separates_defects_from_smoke(receipt: dict) -> None:
    if receipt.get("schema_version") != "complaint-generator.tui-baseline-receipt.v1":
        _fail("baseline receipt schema is missing")
    if receipt.get("task_id") != "CIMP-TUI-01":
        _fail("baseline receipt task id is missing")
    if receipt.get("product_acceptance") is not False:
        _fail("baseline receipt marks product acceptance")
    if receipt.get("defect_classification_independent_of_smoke") is not True:
        _fail("baseline receipt does not keep defect classification independent of smoke")
    smoke = receipt.get("baseline_smoke") or {}
    if smoke.get("result") != "pass" or smoke.get("product_acceptance") is not False:
        _fail("baseline smoke result is not recorded separately from product acceptance")
    observations = receipt.get("observations")
    if not isinstance(observations, list):
        _fail("baseline receipt observations are missing")
    by_id = {item.get("id"): item for item in observations if isinstance(item, dict)}
    expected = {
        "TUI-BASE-PTY": "passed_baseline",
        "TUI-BASE-RESUME": "passed_baseline",
        "TUI-GAP-NARRATIVE": "reproduced_gap",
        "TUI-GAP-UNKNOWN": "reproduced_gap",
        "TUI-GAP-GRAPHS": "reproduced_gap",
        "TUI-GAP-EOF": "reproduced_gap",
        "TUI-GAP-PRIVACY": "reproduced_gap",
    }
    for observation_id, classification in expected.items():
        item = by_id.get(observation_id)
        if item is None:
            _fail(f"baseline receipt is missing {observation_id}")
        if item.get("classification") != classification:
            _fail(f"{observation_id} classification does not match the characterization")
        if item.get("product_acceptance") is not False:
            _fail(f"{observation_id} is marked as product acceptance")
        observation = str(item.get("observation") or "")
        if not observation.strip():
            _fail(f"{observation_id} has an empty observation")
        if classification == "reproduced_gap" and item.get("counts_as_smoke_pass") is not False:
            _fail(f"{observation_id} is folded into the baseline smoke pass")
        if classification == "passed_baseline" and item.get("counts_as_smoke_pass") is not True:
            _fail(f"{observation_id} is not part of the baseline smoke")
    narrative = str(by_id["TUI-GAP-NARRATIVE"].get("observation") or "")
    unknown = str(by_id["TUI-GAP-UNKNOWN"].get("observation") or "")
    graphs = str(by_id["TUI-GAP-GRAPHS"].get("observation") or "")
    eof = str(by_id["TUI-GAP-EOF"].get("observation") or "")
    privacy = str(by_id["TUI-GAP-PRIVACY"].get("observation") or "")
    if "party_name" not in narrative:
        _fail("narrative gap observation does not record initial narrative stored as party_name")
    if "Intake complete" not in unknown and "is_complete" not in unknown:
        _fail("unknown-answer gap observation does not record all-unknown completion")
    if "annotation_knowledge_graph" not in graphs or "dependency" not in graphs:
        _fail("graph gap observation does not record the absent factual/dependency graph")
    if "1" not in eof:
        _fail("EOF gap observation does not record exit 1")
    if "plaintext" not in privacy.lower():
        _fail("privacy gap observation does not record plaintext storage")


def test_receipt_records_gaps_independently_of_baseline_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduce current defects as observations. Do not treat them as acceptance."""

    if not RECEIPT_PATH.is_file():
        _fail("baseline receipt file is absent")
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        _fail("baseline receipt is not a JSON object")
    _assert_receipt_separates_defects_from_smoke(receipt)

    with tempfile.TemporaryDirectory(prefix="tui-baseline-gaps-") as raw:
        root = Path(raw)
        session_dir = root / "sessions"
        home = root / "home"
        session_dir.mkdir()
        home.mkdir()
        script_path = root / "_pty_child.py"
        script_path.write_text(CHILD_SCRIPT, encoding="utf-8")
        _install_parent_guards(monkeypatch, script_path)
        workspace = _import_workspace(monkeypatch, session_dir)

        narrative_service = _unlocked_service(session_dir, NARRATIVE_USER_ID)
        narrative_turn = narrative_service.run_intake_chat_turn(NARRATIVE_USER_ID, message=NARRATIVE)
        accepted = narrative_turn.get("accepted_answer") or {}
        inquiry = narrative_turn.get("inquiry") or {}
        if accepted.get("question_id") != "original_complaint":
            _fail("initial narrative was not stored on original_complaint")
        interview = narrative_turn.get("interview") or {}
        if (narrative_turn.get("legacy_inquiry") or {}).get("question_id") != "party_name":
            _fail("legacy party-name inquiry compatibility was lost")
        if inquiry.get("kind") != "graph" or inquiry.get("question_id") != (interview.get("inquiry") or {}).get("inquiry_id"):
            _fail("narrative turn did not publish its actual canonical graph inquiry")
        if inquiry.get("revision") != interview.get("expected_question_revision"):
            _fail("canonical graph question revision was not exposed consistently")
        narrative_state = _load_session(_session_path(session_dir, NARRATIVE_USER_ID), NARRATIVE_USER_ID)
        if (narrative_state.get("intake_answers") or {}).get("party_name"):
            _fail("housing narrative became party_name")
        _require_same(
            "narrative stored separately",
            (narrative_state.get("original_complaint") or {}).get("text"),
            NARRATIVE,
        )

        unknown_service = _unlocked_service(session_dir, UNKNOWN_USER_ID)
        questions = list((unknown_service.list_intake_questions().get("questions") or []))
        if len(questions) != 7:
            _fail("intake question count changed; all-unknown characterization needs the seven-field flow")
        for question in questions:
            unknown_service.run_intake_chat_turn(
                UNKNOWN_USER_ID,
                message=UNKNOWN_ANSWER,
                question_id=str(question.get("id") or ""),
            )
        # Historical completion/absent-graph defects stay in the immutable
        # receipt; later graph/outcome tasks may fix them without breaking smoke.
        unknown_service.run_intake_chat_turn(UNKNOWN_USER_ID)
        unknown_state = _load_session(_session_path(session_dir, UNKNOWN_USER_ID), UNKNOWN_USER_ID)
        unknown_answers = unknown_state.get("intake_answers") or {}
        if len(unknown_answers) != 7:
            _fail("seven unknown answers were not persisted")
        for question in questions:
            _require_same(
                "unknown answer",
                unknown_answers.get(question.get("id")),
                UNKNOWN_ANSWER,
            )
        session_path = _session_path(session_dir, UNKNOWN_USER_ID)
        raw = session_path.read_bytes()
        assert_private_session_frame(raw, UNKNOWN_ANSWER)
        if UNKNOWN_ANSWER.encode() in raw:
            _fail("automatic encrypted session exposed the synthetic answer")
        session_mode = session_path.stat().st_mode & 0o777
        # The historical baseline receipt describes its original umask writer.
        # The current writer protects bytes; the original receipt stays historical.
        if session_mode != 0o600:
            _fail("session file permissions are not owner-only 0600")
        eof = _run_pty(
            script_path=script_path,
            home=home,
            session_dir=session_dir,
            user_id=EOF_USER_ID,
            eof_after_prompt=True,
        )
        if eof.returncode != 1:
            _fail(f"EOF chat exited {eof.returncode} instead of 1", eof.transcript)
        if PAUSE_MESSAGE in eof.transcript:
            _fail("EOF chat produced the pause/resume outcome", eof.transcript)
        if eof.proof.get("network_guard_active") is not True or eof.proof.get("process_guard_active") is not True:
            _fail("EOF child did not install provider and network guards", eof.transcript)
