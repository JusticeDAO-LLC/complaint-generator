import json
import logging
import os
from pathlib import Path

import pytest

from tests.test_refactor_agent_supervisor import supervisor


pytestmark = pytest.mark.no_auto_heavy


def _configure_once_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    pid_path = tmp_path / "merge-watchdog.pid"
    status_path = tmp_path / "merge-watchdog-status.json"
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_PID_PATH", pid_path)
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_STATUS_PATH", status_path)
    monkeypatch.setattr(supervisor.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        supervisor,
        "resolve_merge_conflicts_once",
        lambda **_kwargs: {"status": "checked", "results": []},
    )
    monkeypatch.setattr(
        supervisor,
        "reconcile_task_projection_artifacts",
        lambda: {"updated": False, "reason": "not_needed"},
    )
    return pid_path, status_path


def test_merge_watchdog_pid_cleanup_failure_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pid_path, status_path = _configure_once_run(tmp_path, monkeypatch)
    original_unlink = Path.unlink

    def fail_pid_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == pid_path:
            raise PermissionError("PID file is read-only")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_pid_unlink)
    caplog.set_level(logging.ERROR, logger=supervisor.__name__)

    result = supervisor.run_merge_resolver_watchdog(interval_s=1, timeout_seconds=1, once=True)

    expected = {
        "path": str(pid_path),
        "error_type": "PermissionError",
        "error": "PID file is read-only",
    }
    assert result["pid_cleanup_error"] == expected
    assert json.loads(status_path.read_text(encoding="utf-8"))["pid_cleanup_error"] == expected
    assert pid_path.read_text(encoding="utf-8") == f"{os.getpid()}\n"
    assert "could not remove its PID file" in caplog.text
    assert "PID file is read-only" in caplog.text


def test_merge_watchdog_pid_cleanup_does_not_hide_programming_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_path, _status_path = _configure_once_run(tmp_path, monkeypatch)
    original_unlink = Path.unlink

    def fail_pid_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == pid_path:
            raise RuntimeError("unexpected cleanup defect")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_pid_unlink)

    with pytest.raises(RuntimeError, match="unexpected cleanup defect"):
        supervisor.run_merge_resolver_watchdog(interval_s=1, timeout_seconds=1, once=True)
