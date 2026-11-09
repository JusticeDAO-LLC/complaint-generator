"""Focused regression coverage for REF-227's daemon PID cleanup boundary."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_auto_heavy

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "refactor_agent_supervisor.py"
SPEC = importlib.util.spec_from_file_location("ref_227_refactor_agent_supervisor", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
supervisor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = supervisor
SPEC.loader.exec_module(supervisor)


class _UnlinkFailingPath:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __str__(self) -> str:
        return str(self.path)

    def write_text(self, *args, **kwargs):
        return self.path.write_text(*args, **kwargs)

    def exists(self) -> bool:
        return self.path.exists()

    def read_text(self, *args, **kwargs):
        return self.path.read_text(*args, **kwargs)

    def unlink(self) -> None:
        raise PermissionError("read-only supervisor state")


def test_run_daemon_persists_owned_pid_cleanup_failure(tmp_path, monkeypatch) -> None:
    pid_path = _UnlinkFailingPath(tmp_path / "supervisor.pid")
    status_path = tmp_path / "status.json"
    counts = {
        "todo": {"needed": 0, "in_progress": 0, "complete": 1, "blocked": 0},
        "queue": {"queued": 0, "running": 0, "completed": 1, "failed": 0},
    }
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "STATUS_PATH", status_path)
    monkeypatch.setattr(supervisor, "PID_PATH", pid_path)
    monkeypatch.setattr(supervisor.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        supervisor,
        "seed_taskboard",
        lambda **_kwargs: {"counts": counts, "scan": {}},
    )

    supervisor.run_daemon(interval_s=5.0, refill_floor=1, once=True)

    persisted = json.loads(status_path.read_text(encoding="utf-8"))
    expected = (
        f"Could not remove owned PID file {pid_path}: PermissionError: "
        "read-only supervisor state"
    )
    assert persisted["status"] == "stopped"
    assert persisted["pid_cleanup_error"] == expected
    assert persisted["last_error"] == expected
    assert pid_path.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_run_daemon_clears_prior_pid_cleanup_failure_after_success(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "supervisor.pid"
    status_path = tmp_path / "status.json"
    prior_error = "Could not remove a PID file during the prior run"
    status_path.write_text(
        json.dumps({"pid_cleanup_error": prior_error, "last_error": prior_error}),
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "STATUS_PATH", status_path)
    monkeypatch.setattr(supervisor, "PID_PATH", pid_path)
    monkeypatch.setattr(supervisor.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        supervisor,
        "seed_taskboard",
        lambda **_kwargs: {"counts": {"todo": {}, "queue": {}}, "scan": {}},
    )

    supervisor.run_daemon(interval_s=5.0, refill_floor=1, once=True)

    persisted = json.loads(status_path.read_text(encoding="utf-8"))
    assert persisted["pid_cleanup_error"] is None
    assert persisted["last_error"] is None
    assert not pid_path.exists()


def test_owned_pid_cleanup_does_not_swallow_non_filesystem_errors(tmp_path) -> None:
    class InvalidPidPath(_UnlinkFailingPath):
        def unlink(self) -> None:
            raise RuntimeError("invalid cleanup state")

    pid_path = InvalidPidPath(tmp_path / "supervisor.pid")
    pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="invalid cleanup state"):
        supervisor._remove_owned_pid_file(pid_path, pid=os.getpid())
