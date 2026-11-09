"""PTY coverage for accessible terminal controls and recoverable resume.

Timeouts are fixed. The tests use synthetic session text only.
"""

from __future__ import annotations

import fcntl
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEADLINE_SECONDS = 90.0
PASSPHRASE = "synthetic-pty-fixture-passphrase"

CHILD = r"""
import json
import os
import signal
import sys
from pathlib import Path

signal.signal(signal.SIGHUP, signal.SIG_IGN)

repo_root = os.environ["TUI_CONTROLS_REPO_ROOT"]
if repo_root not in sys.path:
    sys.path.insert(1, repo_root)
session_dir = Path(os.environ["TUI_CONTROLS_SESSION_DIR"])
user_id = os.environ["TUI_CONTROLS_USER_ID"]
import applications.complaint_workspace as workspace
workspace._SESSION_DIR = session_dir
import applications.complaint_cli as cli
cli.service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
if cli.service.private_key_status()["status"] == "absent":
    cli.service.initialize_private_keys(protection="passphrase", passphrase=os.environ["TUI_CONTROLS_PASSPHRASE"])
else:
    cli.service.unlock_private_keys(passphrase=os.environ["TUI_CONTROLS_PASSPHRASE"])
cli.service.ensure_private_case_key(user_id, user_id)
_real_factory = cli.service._mediator_for_shared_interview
def _fixture_backend(prompt, complaint_privacy_context=None, **kwargs):
    if os.environ.get("TUI_CONTROLS_BLOCK_PROVIDER") == "1":
        assert complaint_privacy_context["policy"]["permitted_remote"] == {"provider": "grok_cli", "model": "grok-4.7"}
        print("Synthetic provider request started", flush=True)
        while True:
            signal.pause()
    return '{"entities":[],"relationships":[]}'
def _fixture_mediator(owner_id, case_id):
    mediator = _real_factory(owner_id, case_id)
    mediator.backends = [_fixture_backend]
    return mediator
cli.service._mediator_for_shared_interview = _fixture_mediator
if os.environ.get("TUI_CONTROLS_BLOCK_PROVIDER") == "1":
    cli.service.set_privacy_policy(user_id, "grok")
cli.chat(user_id=user_id, max_turns=0)
"""


def _fail(message: str, transcript: str = "") -> None:
    detail = f"\n--- transcript ---\n{transcript}" if transcript else ""
    raise AssertionError(message + detail)


def _prepare(tmp_path: Path, user_id: str) -> tuple[Path, Path, dict[str, str]]:
    fixture_root = tmp_path / user_id
    fixture_root.mkdir(parents=True, exist_ok=True)
    session_dir = fixture_root / "sessions"
    home = fixture_root / "home"
    session_dir.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)
    script = fixture_root / "_child.py"
    script.write_text(CHILD, encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "TMPDIR": str(fixture_root),
        "TUI_CONTROLS_REPO_ROOT": str(REPO_ROOT),
        "TUI_CONTROLS_SESSION_DIR": str(session_dir),
        "TUI_CONTROLS_USER_ID": user_id,
        "TUI_CONTROLS_PASSPHRASE": PASSPHRASE,
        "PYTHONPATH": str(REPO_ROOT),
        "NO_COLOR": "1",
        "TERM": "dumb",
    })
    env.pop("TUI_CONTROLS_BLOCK_PROVIDER", None)
    return session_dir, script, env


def _run_pty(script: Path, env: dict[str, str], steps: list[tuple[bytes, bytes]], *, interrupt: bytes | None = None) -> tuple[int, str]:
    """Drive a PTY child. Each step is (wait_for, reply). Fixed deadline."""

    master, slave = os.openpty()
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        cwd=str(REPO_ROOT),
        start_new_session=True,
    )
    os.close(slave)
    flags = fcntl.fcntl(master, fcntl.F_GETFL)
    fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    transcript = bytearray()
    started = time.monotonic()
    cursor = 0
    sent_interrupt = interrupt is None
    try:
        while True:
            elapsed = time.monotonic() - started
            if elapsed > DEADLINE_SECONDS:
                _fail(f"PTY exceeded {DEADLINE_SECONDS:.0f}s", transcript.decode("utf-8", "replace"))
            remaining = DEADLINE_SECONDS - elapsed
            ready, _, _ = select.select([master], [], [], min(0.1, remaining))
            if ready:
                try:
                    chunk = os.read(master, 8192)
                except (BlockingIOError, OSError):
                    chunk = b""
                if chunk:
                    transcript += chunk
            text = bytes(transcript)
            if cursor < len(steps) and steps[cursor][0] in text:
                os.write(master, steps[cursor][1])
                cursor += 1
            if interrupt is not None and not sent_interrupt and interrupt in text:
                os.killpg(proc.pid, signal.SIGINT)
                sent_interrupt = True
            if proc.poll() is not None:
                while True:
                    try:
                        chunk = os.read(master, 8192)
                    except (BlockingIOError, OSError):
                        break
                    if not chunk:
                        break
                    transcript += chunk
                break
    finally:
        os.close(master)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
    return int(proc.returncode if proc.returncode is not None else 1), bytes(transcript).decode("utf-8", "replace")


def _run_redirected(script: Path, env: dict[str, str], payload: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=payload.encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=DEADLINE_SECONDS,
        check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace")


def _session(session_dir: Path, user_id: str) -> dict:
    import applications.complaint_workspace as workspace

    service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
    service.unlock_private_keys(passphrase=PASSPHRASE)
    return service.get_session(user_id)["session"]


def test_launcher_selects_working_python_and_configured_backend(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts" / "run_cli_mediator.sh"
    text = script.read_text(encoding="utf-8")
    if "codex" in text.lower():
        _fail("launcher still hardcodes Codex")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "COMPLAINT_GENERATOR_PYTHON": "/usr/bin/false",
        "COMPLAINT_GENERATOR_MEDIATOR_BACKENDS": "configured-backend",
        "COMPLAINT_GENERATOR_LAUNCHER_DRY_RUN": "1",
    }
    completed = subprocess.run(
        ["/usr/bin/bash", str(script), "--user-id", "synthetic"],
        env=env,
        cwd=str(tmp_path),
        timeout=DEADLINE_SECONDS,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        _fail(completed.stderr.decode("utf-8", "replace"))
    lines = [line.strip() for line in completed.stdout.decode("utf-8", "replace").splitlines() if line.strip()]
    if not lines or not lines[0].endswith("python3.12"):
        _fail("launcher did not skip the broken interpreter and select python3.12", completed.stdout.decode())
    if "configured-backend" not in lines:
        _fail("launcher did not keep the configured backend", completed.stdout.decode())


def test_redirected_multiline_unicode_and_commands(tmp_path: Path) -> None:
    user_id = "controls-redirect"
    session_dir, script, env = _prepare(tmp_path, user_id)
    env["COLUMNS"] = "48"
    env["COMPLAINT_CLI_ASCII"] = "0"
    payload = "José kept the unit after the request. \\\nThe notice arrived Monday.\n\n/help\n/status\n/quit\n"
    code, transcript = _run_redirected(script, env, payload)
    if code != 0:
        _fail(f"redirected chat exited {code}", transcript)
    if "\x1b" in transcript:
        _fail("NO_COLOR still emitted ANSI", transcript)
    if "/help" not in transcript or "/resume" not in transcript:
        _fail("help did not document the controls", transcript)
    if "130" not in transcript or "Ctrl-C" not in transcript:
        _fail("help did not document the interrupt exit code", transcript)
    saved = _session(session_dir, user_id)
    narrative = (saved.get("original_complaint") or {}).get("text") or ""
    if "José" not in narrative or "Monday" not in narrative:
        _fail("multiline Unicode narrative was not stored", narrative)
    controls = saved.get("terminal_controls") or {}
    if controls.get("stop_reason") != "user_quit":
        _fail("quit did not persist the stop reason", json.dumps(controls))
    answers = saved.get("intake_answers") or {}
    if any(str(value).startswith("/") for value in answers.values()):
        _fail("a slash command was stored as an answer", json.dumps(answers))


def test_pty_narrow_width_wraps_help(tmp_path: Path) -> None:
    user_id = "controls-narrow"
    _session_dir, script, env = _prepare(tmp_path, user_id)
    env["COLUMNS"] = "16"
    code, transcript = _run_pty(script, env, [(b"plain language", b"/help\n/quit\n")])
    if code != 0:
        _fail(f"narrow chat exited {code}", transcript)
    for line in transcript.splitlines():
        if len(line) > 16:
            _fail(f"narrow line is {len(line)} characters", transcript)
            break


def test_pty_narrow_unicode_skip_and_fresh_resume(tmp_path: Path) -> None:
    user_id = "controls-resume"
    session_dir, script, env = _prepare(tmp_path, user_id)
    env["COLUMNS"] = "120"
    env.pop("NO_COLOR", None)
    env["TERM"] = "xterm-256color"
    code, transcript = _run_pty(
        script,
        env,
        [
            (b"plain language", b"/skip\n"),
            (b"Skipped the narrative", b"/status\n"),
            (b"terminal-control", b"/pause\n"),
            (b"Chat paused", b"/quit\n"),
        ],
    )
    if code != 0:
        _fail(f"control chat exited {code}", transcript)
    if "\x1b" not in transcript:
        _fail("a color terminal did not emit a prompt color", transcript)
    saved = _session(session_dir, user_id)
    controls = saved.get("terminal_controls") or {}
    pending = controls.get("pending_inquiry") or {}
    if not controls.get("skipped_answers"):
        _fail("skip was not recorded", json.dumps(controls))
    if controls["skipped_answers"][0].get("satisfies_requirement") is not False:
        _fail("skip satisfied a legal requirement", json.dumps(controls))
    if controls.get("stop_reason") != "user_quit":
        _fail("quit stop reason was lost", json.dumps(controls))
    question_id = str(pending.get("question_id") or "")
    if not question_id:
        _fail("pending inquiry was lost", json.dumps(controls))
    resume_env = dict(env)
    resume_env["NO_COLOR"] = "1"
    resume_env["TERM"] = "dumb"
    code, resumed = _run_pty(
        script,
        resume_env,
        [
            (b"Restored pending question", b"/status\n"),
            (b"terminal-control", b"/resume\n"),
            (b"skipped", b"/quit\n"),
        ],
    )
    if code != 0:
        _fail(f"resume chat exited {code}", resumed)
    if f"question_id={question_id}" not in resumed:
        _fail("fresh process did not restore the pending question", resumed)
    if "stop_reason=user_quit" not in resumed:
        _fail("fresh process did not restore the stop reason", resumed)
    if "revision=" not in resumed or "objective=" not in resumed:
        _fail("fresh process did not restore revision and objective", resumed)
    if "\x1b" in resumed:
        _fail("narrow no-color resume emitted ANSI", resumed)


def test_pty_eof_and_interrupt_keep_pending_inquiry(tmp_path: Path) -> None:
    user_id = "controls-eof"
    session_dir, script, env = _prepare(tmp_path, user_id)
    master, slave = os.openpty()
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        cwd=str(REPO_ROOT),
        start_new_session=True,
    )
    os.close(slave)
    flags = fcntl.fcntl(master, fcntl.F_GETFL)
    fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    transcript = bytearray()
    started = time.monotonic()
    sent_eof = False
    try:
        while proc.poll() is None:
            if time.monotonic() - started > DEADLINE_SECONDS:
                _fail("EOF PTY exceeded its deadline", bytes(transcript).decode("utf-8", "replace"))
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(master, 8192)
                except OSError:
                    chunk = b""
                if chunk:
                    transcript += chunk
            if not sent_eof and b"plain language" in bytes(transcript) and b"\n> " in bytes(transcript):
                os.write(master, b"\x04")
                sent_eof = True
        text = bytes(transcript).decode("utf-8", "replace")
    finally:
        os.close(master)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
    if proc.returncode != 1:
        _fail(f"EOF exited {proc.returncode}", text)
    if "Traceback" in text:
        _fail("EOF printed a traceback", text)
    if "exit 1" not in text:
        _fail("EOF did not document its exit code", text)
    saved = _session(session_dir, user_id)
    pending = (saved.get("terminal_controls") or {}).get("pending_inquiry") or {}
    if pending.get("question_id") != "original_complaint":
        _fail("EOF lost the pending inquiry", json.dumps(saved.get("terminal_controls")))
    if (saved.get("terminal_controls") or {}).get("stop_reason") != "eof":
        _fail("EOF did not persist the stop reason", json.dumps(saved.get("terminal_controls")))

    interrupt_user = "controls-interrupt"
    interrupt_dir, interrupt_script, interrupt_env = _prepare(tmp_path, interrupt_user)
    interrupt_env["TUI_CONTROLS_BLOCK_PROVIDER"] = "1"
    code, transcript = _run_pty(
        interrupt_script,
        interrupt_env,
        [(b"plain language", b"Synthetic interrupt narrative.\n")],
        interrupt=b"Synthetic provider request started",
    )
    if code != 130:
        _fail(f"interrupt exited {code}", transcript)
    if "Traceback" in transcript:
        _fail("interrupt printed a traceback", transcript)
    if "exit 130" not in transcript:
        _fail("interrupt did not document its exit code", transcript)
    interrupted = _session(interrupt_dir, interrupt_user)
    controls = interrupted.get("terminal_controls") or {}
    pending = controls.get("pending_inquiry") or {}
    if pending.get("question_id") != "original_complaint":
        _fail("interrupt lost the exact pending inquiry", json.dumps(controls))
    if controls.get("stop_reason") != "interrupted" or controls.get("paused") is not True:
        _fail("actual provider interruption did not persist a pause", json.dumps(controls))
    narrative = (interrupted.get("original_complaint") or {}).get("text") or ""
    if "Synthetic interrupt narrative" in narrative:
        _fail("interrupt committed the answer during the provider wait", narrative)


def test_stale_concurrent_answer_is_rejected(tmp_path: Path) -> None:
    import applications.complaint_workspace as workspace

    user_id = "controls-stale"
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    workspace._SESSION_DIR = session_dir
    import applications.complaint_cli as cli

    cli.service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
    cli.service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    cli.service.ensure_private_case_key(user_id, user_id)
    real_factory = cli.service._mediator_for_shared_interview

    def fixture_mediator(owner_id, case_id):
        mediator = real_factory(owner_id, case_id)
        mediator.backends = [lambda prompt, complaint_privacy_context=None, **kwargs: '{"entities":[],"relationships":[]}']
        return mediator

    cli.service._mediator_for_shared_interview = fixture_mediator
    opened = cli.service.run_intake_chat_turn(user_id)
    inquiry = opened.get("inquiry") or {}
    state = cli.load_terminal_state(user_id)
    shown = cli.answer_fingerprint(state, inquiry)
    cli.service.run_intake_chat_turn(
        user_id,
        message="A different writer stored this narrative.",
        question_id="original_complaint",
    )
    if cli.stale_answer_rejection(user_id, shown) != "stale_question":
        _fail("concurrent narrative write was accepted as current")
    current = cli.load_terminal_state(user_id)
    if "different writer" not in (current.get("original_complaint") or {}).get("text", ""):
        _fail("the concurrent answer itself was lost")
