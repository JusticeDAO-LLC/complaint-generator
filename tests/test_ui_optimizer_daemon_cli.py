from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from complaint_generator import ui_optimizer_daemon as module


def test_build_parser_exposes_daemon_commands_and_flags():
    parser = module.build_parser()
    help_text = parser.format_help()
    run_help = parser._subparsers._group_actions[0].choices["run"].format_help()

    assert "start" in help_text
    assert "run" in help_text
    assert "status" in help_text
    assert "stop" in help_text
    assert "--max-rounds" in run_help
    assert "--use-llm-draft" in run_help

    parsed = parser.parse_args(
        [
            "start",
            "--user-id",
            "sleep-user",
            "--goal",
            "make intake calmer",
            "--use-llm-draft",
        ]
    )
    assert parsed.command == "start"
    assert parsed.use_llm_draft is True
    assert parsed.goals == ["make intake calmer"]


def test_run_daemon_writes_cycle_status_and_artifacts(tmp_path, monkeypatch):
    pid_file = tmp_path / "daemon.pid"
    status_file = tmp_path / "daemon-status.json"
    log_file = tmp_path / "daemon.log"

    class FakeService:
        def __init__(self, root_dir):
            self.root_dir = Path(root_dir)

        def generate_complaint(self, user_id, **kwargs):
            assert user_id == "sleep-user"
            return {"draft": {"title": "Draft Complaint"}, "kwargs": kwargs}

        def export_complaint_markdown(self, user_id):
            assert user_id == "sleep-user"
            return {"artifact": {"filename": "complaint.md", "size_bytes": 321}}

        def export_complaint_pdf(self, user_id):
            assert user_id == "sleep-user"
            return {"artifact": {"filename": "complaint.pdf", "size_bytes": 654}}

        def review_generated_exports(self, user_id, **kwargs):
            assert user_id == "sleep-user"
            return {
                "aggregate": {
                    "average_filing_shape_score": 89,
                    "average_claim_type_alignment_score": 92,
                    "issue_findings": ["Draft still needs a clearer venue cue."],
                }
            }

    monkeypatch.setattr(module, "ComplaintWorkspaceService", FakeService)
    monkeypatch.setattr(
        module,
        "run_end_to_end_complaint_browser_audit",
        lambda **kwargs: {
            "returncode": 0,
            "artifact_count": 4,
            "screenshot_dir": str(kwargs["screenshot_dir"]),
        },
    )
    monkeypatch.setattr(
        module,
        "optimize_ui",
        lambda **kwargs: {
            "workflow_type": "ui_ux_closed_loop",
            "rounds_executed": 1,
            "stop_reason": "validation_review_stable",
            "received": {
                "user_id": kwargs["user_id"],
                "method": kwargs["method"],
                "priority": kwargs["priority"],
                "reuse_existing_screenshots": kwargs["reuse_existing_screenshots"],
            },
        },
    )

    args = argparse.Namespace(
        command="run",
        user_id="sleep-user",
        workspace_root=str(tmp_path / "sessions"),
        artifact_root=str(tmp_path / "artifacts"),
        pytest_target="playwright/tests/complaint-flow.spec.js",
        max_rounds=2,
        iterations=1,
        notes="Overnight actor/critic pass",
        goals=["make intake calmer"],
        provider="stub-provider",
        model="stub-model",
        config_path="config.llm_router.json",
        backend_id="router-backend",
        method="actor_critic",
        priority=90,
        use_llm_draft=True,
        poll_seconds=0.0,
        retry_seconds=0.0,
        max_consecutive_errors=0,
        max_cycles=1,
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )

    payload = module._run_daemon(args)

    assert payload["status"] == "success"
    assert payload["daemon_state"] == "completed"
    assert payload["cycle_count"] == 1
    assert Path(payload["status_file"]).exists()
    status_payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert status_payload["status"] == "completed"
    assert status_payload["pid"] == os.getpid()
    assert status_payload["updated_at"]
    assert status_payload["artifacts"]["status_file"] == str(status_file.resolve())
    assert status_payload["artifacts"]["cycle_manifest_path"] == status_payload["last_result"]["cycle_manifest_path"]
    assert status_payload["last_error"] is None
    assert status_payload["phase"] == "completed"
    assert status_payload["cycle_count"] == 1
    assert status_payload["last_result"]["summary"]["browser_artifact_count"] == 4
    assert status_payload["last_result"]["summary"]["filing_shape_score"] == 89
    assert status_payload["last_result"]["optimizer_result"]["workflow_type"] == "ui_ux_closed_loop"
    assert Path(status_payload["last_result"]["cycle_manifest_path"]).exists()
    assert Path(status_payload["last_result"]["export_review_path"]).exists()
    assert not pid_file.exists()


def test_start_status_and_stop_daemon_commands(tmp_path, monkeypatch):
    artifact_root = tmp_path / "artifacts"
    pid_file = artifact_root / "ui_optimizer_daemon.pid"
    status_file = artifact_root / "ui_optimizer_daemon_status.json"
    log_file = artifact_root / "ui_optimizer_daemon.log"
    artifact_root.mkdir(parents=True, exist_ok=True)

    class _FakePopen:
        def __init__(self, cmd, cwd, env, stdout, stderr, start_new_session):
            self.pid = 515151
            self.cmd = cmd
            self.cwd = cwd
            self.env = env
            self.stdout = stdout
            self.stderr = stderr
            self.start_new_session = start_new_session

    captured = {}

    def fake_popen(cmd, cwd, env, stdout, stderr, start_new_session):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        return _FakePopen(cmd, cwd, env, stdout, stderr, start_new_session)

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid == 515151)
    monkeypatch.setattr(module.os, "kill", lambda pid, sig: captured.setdefault("killed", (pid, sig)))

    args = argparse.Namespace(
        command="start",
        user_id="sleep-user",
        workspace_root=str(tmp_path / "sessions"),
        artifact_root=str(artifact_root),
        pytest_target="playwright/tests/complaint-flow.spec.js",
        max_rounds=3,
        iterations=2,
        notes="Nightly pass",
        goals=["keep export visible", "improve testimony cues"],
        provider="stub-provider",
        model="stub-model",
        config_path="config.llm_router.json",
        backend_id="router-backend",
        method="adversarial",
        priority=91,
        use_llm_draft=True,
        poll_seconds=60.0,
        retry_seconds=10.0,
        max_consecutive_errors=4,
        max_cycles=0,
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )

    start_payload = module._start_daemon(args)
    assert start_payload["status"] == "started"
    assert captured["cmd"][0]
    assert "complaint_generator.ui_optimizer_daemon" in captured["cmd"]
    assert "--use-llm-draft" in captured["cmd"]
    assert "--goal" in captured["cmd"]

    pid_file.write_text("515151\n", encoding="utf-8")
    status_file.write_text(json.dumps({"status": "running", "cycle_count": 3}), encoding="utf-8")

    status_args = argparse.Namespace(
        command="status",
        user_id="sleep-user",
        workspace_root=str(tmp_path / "sessions"),
        artifact_root=str(artifact_root),
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )
    status_payload = module._status_payload(status_args)
    assert status_payload["running"] is True
    assert status_payload["status_payload"]["cycle_count"] == 3
    assert status_payload["updated_at"]
    assert status_payload["artifacts"]["status_file"] == str(status_file.resolve())
    assert status_payload["last_error"] is None

    stop_args = argparse.Namespace(
        command="stop",
        user_id="sleep-user",
        workspace_root=str(tmp_path / "sessions"),
        artifact_root=str(artifact_root),
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )
    stop_payload = module._stop_daemon(stop_args)
    assert stop_payload["status"] == "stopping"
    assert captured["killed"][0] == 515151
