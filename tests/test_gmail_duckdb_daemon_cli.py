from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import io
import os
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "gmail_duckdb_daemon.py"
    spec = importlib.util.spec_from_file_location("gmail_duckdb_daemon_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_parser_exposes_daemon_commands_and_flags():
    module = _load_script_module()
    parser = module.build_parser()
    help_text = parser.format_help()

    assert "start" in help_text
    assert "run" in help_text
    assert "status" in help_text
    assert "stop" in help_text
    assert "--uid-range-span" in help_text
    assert "--duckdb-build-every-batches" in help_text

    start_help = parser.parse_args(
        ["start", "--user-id", "case-user", "--address", "hr@example.com", "--use-ipfs-secrets-vault"]
    )
    assert start_help.command == "start"
    assert start_help.use_ipfs_secrets_vault is True


def test_run_daemon_writes_status_and_pid_files(tmp_path, monkeypatch):
    module = _load_script_module()
    pid_file = tmp_path / "daemon.pid"
    status_file = tmp_path / "daemon-status.json"
    log_file = tmp_path / "daemon.log"

    async def fake_run_gmail_duckdb_pipeline(**kwargs):
        return {
            "status": "success",
            "pipeline": "gmail_duckdb_pipeline",
            "batch_count": 1,
            "total_imported_count": 10,
            "duckdb_index": {"duckdb_path": str(tmp_path / "duckdb" / "email_corpus.duckdb")},
            "received": kwargs,
        }

    monkeypatch.setattr(module, "run_gmail_duckdb_pipeline", fake_run_gmail_duckdb_pipeline)

    args = argparse.Namespace(
        command="run",
        user_id="case-user",
        addresses=["hr@example.com"],
        claim_element_id="causation",
        folder="[Gmail]/All Mail",
        scan_folder=[],
        years_back=2,
        date_after=None,
        date_before=None,
        complaint_query=None,
        complaint_keyword=[],
        min_relevance_score=0.0,
        workspace_root=str(tmp_path / "sessions"),
        evidence_root=str(tmp_path / "evidence"),
        duckdb_output_dir=str(tmp_path / "duckdb"),
        gmail_user="user@gmail.com",
        gmail_app_password="app-password",
        use_gmail_oauth=False,
        gmail_oauth_client_secrets=None,
        gmail_oauth_token_cache=None,
        no_gmail_oauth_browser=False,
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=False,
        use_ipfs_secrets_vault=False,
        save_to_ipfs_secrets_vault=False,
        checkpoint_name="gmail-duckdb-daemon",
        uid_window_size=500,
        uid_range_span=50000,
        max_batches=1,
        duckdb_build_every_batches=10,
        append_to_existing_corpus=False,
        bm25_search_query=None,
        bm25_search_limit=20,
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
    assert Path(payload["status_file"]).exists()
    status_payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert status_payload["status"] == "completed"
    assert status_payload["pid"] == os.getpid()
    assert status_payload["updated_at"] == status_payload["last_updated_at"]
    assert status_payload["artifacts"]["status_file"] == str(status_file.resolve())
    assert status_payload["last_error"] is None
    assert status_payload["cycle_count"] == 1
    assert status_payload["phase"] == "completed"
    assert status_payload["consecutive_errors"] == 0
    assert "progress_summary" in status_payload
    assert status_payload["progress_summary"]["manifest_path"].endswith("email_import_manifest.json")
    assert status_payload["last_result"]["total_imported_count"] == 10
    assert not pid_file.exists()


def test_start_status_and_stop_daemon_commands(tmp_path, monkeypatch):
    module = _load_script_module()
    duckdb_dir = tmp_path / "duckdb"
    pid_file = duckdb_dir / "gmail_duckdb_daemon.pid"
    status_file = duckdb_dir / "gmail_duckdb_daemon_status.json"
    log_file = duckdb_dir / "gmail_duckdb_daemon.log"
    duckdb_dir.mkdir(parents=True, exist_ok=True)

    class _FakePopen:
        def __init__(self, cmd, cwd, env, stdout, stderr, start_new_session):
            self.pid = 424242
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
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid == 424242)
    monkeypatch.setattr(module.os, "kill", lambda pid, sig: captured.setdefault("killed", (pid, sig)))

    args = argparse.Namespace(
        command="start",
        user_id="case-user",
        addresses=["hr@example.com", "manager@example.com"],
        claim_element_id="causation",
        folder="[Gmail]/All Mail",
        scan_folder=["INBOX"],
        years_back=2,
        date_after=None,
        date_before=None,
        complaint_query="termination retaliation",
        complaint_keyword=["termination"],
        min_relevance_score=1.0,
        workspace_root=str(tmp_path / "sessions"),
        evidence_root=str(tmp_path / "evidence"),
        duckdb_output_dir=str(duckdb_dir),
        gmail_user="user@gmail.com",
        gmail_app_password="app-password",
        use_gmail_oauth=False,
        gmail_oauth_client_secrets=None,
        gmail_oauth_token_cache=None,
        no_gmail_oauth_browser=False,
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=False,
        use_ipfs_secrets_vault=True,
        save_to_ipfs_secrets_vault=False,
        checkpoint_name="gmail-duckdb-daemon",
        uid_window_size=500,
        uid_range_span=50000,
        max_batches=5,
        duckdb_build_every_batches=10,
        append_to_existing_corpus=True,
        bm25_search_query="termination grievance",
        bm25_search_limit=10,
        poll_seconds=60.0,
        retry_seconds=30.0,
        max_consecutive_errors=0,
        max_cycles=0,
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )

    start_payload = module._start_daemon(args)
    assert start_payload["status"] == "started"
    assert "run" in captured["cmd"]
    assert "--use-ipfs-secrets-vault" in captured["cmd"]
    assert "--uid-range-span" in captured["cmd"]
    assert "--duckdb-build-every-batches" in captured["cmd"]
    assert captured["env"]["GMAIL_APP_PASSWORD"] == "app-password"

    pid_file.write_text("424242\n", encoding="utf-8")
    status_file.write_text(json.dumps({"status": "running", "cycle_count": 2}), encoding="utf-8")

    status_args = argparse.Namespace(
        command="status",
        user_id="case-user",
        duckdb_output_dir=str(duckdb_dir),
        status_file=str(status_file),
        pid_file=str(pid_file),
        json=True,
    )
    status_payload = module._status_payload(status_args)
    assert status_payload["running"] is True
    assert status_payload["status_payload"]["cycle_count"] == 2
    assert status_payload["updated_at"]
    assert status_payload["artifacts"]["status_file"] == str(status_file.resolve())
    assert status_payload["last_error"] is None

    stop_args = argparse.Namespace(
        command="stop",
        user_id="case-user",
        duckdb_output_dir=str(duckdb_dir),
        status_file=str(status_file),
        pid_file=str(pid_file),
        json=True,
    )
    stop_payload = module._stop_daemon(stop_args)
    assert stop_payload["status"] == "stopping"
    assert captured["killed"][0] == 424242


def test_build_progress_summary_reports_estimated_completion(tmp_path):
    module = _load_script_module()
    evidence_root = tmp_path / "evidence"
    artifact_root = evidence_root / "case-user" / "gmail-import"
    artifact_root.mkdir(parents=True, exist_ok=True)
    for index in range(2):
        message_dir = artifact_root / f"0000000-0000999" / f"uid_{index:010d}"
        message_dir.mkdir(parents=True, exist_ok=True)
        (message_dir / "message.eml").write_bytes(b"raw-email")

    state_dir = artifact_root / "_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = state_dir / "gmail-daemon_checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "version": 1,
                "folders": {
                    "[Gmail]/All Mail": {
                        "estimated_total_messages": 5,
                        "estimated_total_messages_exact": True,
                        "last_processed_uid": 999,
                        "next_uid_upper_bound": 777,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    progress_path = state_dir / "gmail-daemon_progress.json"
    progress_path.write_text(
        json.dumps(
            {
                "status": "running",
                "imported_count": 2,
                "searched_message_count": 2,
                "raw_email_total_bytes": 123,
                "estimated_total_messages": 5,
                "estimated_total_messages_exact": True,
            }
        ),
        encoding="utf-8",
    )

    args = argparse.Namespace(
        user_id="case-user",
        evidence_root=str(evidence_root),
        checkpoint_name="gmail-daemon",
        folder="[Gmail]/All Mail",
    )

    summary = module._build_progress_summary(args)
    assert summary["eml_file_count"] == 2
    assert summary["estimated_total_messages"] == 5
    assert summary["estimated_total_messages_exact"] is True
    assert summary["estimated_remaining_messages"] == 3
    assert summary["estimated_completion_percent"] == 40.0


def test_main_status_prints_human_readable_progress_summary(tmp_path, monkeypatch):
    module = _load_script_module()
    duckdb_dir = tmp_path / "duckdb"
    duckdb_dir.mkdir(parents=True, exist_ok=True)
    pid_file = duckdb_dir / "gmail_duckdb_daemon.pid"
    status_file = duckdb_dir / "gmail_duckdb_daemon_status.json"
    pid_file.write_text("424242\n", encoding="utf-8")
    status_file.write_text(
        json.dumps(
            {
                "status": "running",
                "phase": "running_cycle",
                "progress_summary": {
                    "eml_file_count": 5629,
                    "estimated_total_messages": 140012,
                    "estimated_completion_percent": 4.02,
                    "estimated_remaining_messages": 134383,
                    "raw_email_total_bytes": 19777974,
                    "last_processed_uid": 749419,
                    "next_uid_upper_bound": 742633,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid == 424242)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "gmail_duckdb_daemon.py",
            "status",
            "--user-id",
            "case-user",
            "--duckdb-output-dir",
            str(duckdb_dir),
        ],
    )

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = module.main()

    text = stdout.getvalue()
    assert exit_code == 0
    assert "Daemon status: running" in text
    assert "Phase: running_cycle" in text
    assert "Progress: 5629 / 140012 (4.02%)" in text
    assert "Estimated remaining: 134383" in text
