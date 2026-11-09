#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from integrations.ipfs_datasets.legal_data import load_legal_symbol
from integrations.ipfs_datasets.loader import import_failure_message


def _require_ipfs_attr(module_name: str, attr_name: str, label: str):
    try:
        return load_legal_symbol(attr_name, module=module_name)
    except ImportError as error:
        raise ImportError(
            f"Unable to import ipfs_datasets_py {label}: "
            f"{import_failure_message(error) or f'missing {attr_name}'}"
        ) from error


async def run_gmail_duckdb_pipeline(**kwargs):
    """Load the upstream-owned pipeline only when a daemon cycle runs."""
    pipeline = _require_ipfs_attr(
        "email_pipeline",
        "run_gmail_duckdb_pipeline",
        "Gmail DuckDB pipeline",
    )
    return await pipeline(**kwargs)


_STOP_REQUESTED = False


def _default_evidence_root(user_id: str) -> Path:
    return PROJECT_ROOT / "output" / "gmail_evidence" / str(user_id or "gmail-daemon")


def _default_duckdb_root(user_id: str) -> Path:
    return PROJECT_ROOT / "output" / "email_duckdb" / str(user_id or "gmail-daemon")


def _default_pid_file(duckdb_output_dir: Path) -> Path:
    return duckdb_output_dir / "gmail_duckdb_daemon.pid"


def _default_status_file(duckdb_output_dir: Path) -> Path:
    return duckdb_output_dir / "gmail_duckdb_daemon_status.json"


def _default_log_file(duckdb_output_dir: Path) -> Path:
    return duckdb_output_dir / "gmail_duckdb_daemon.log"


def _signal_stop(_signum, _frame) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def _pid_is_running(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def _build_progress_summary(args: argparse.Namespace) -> dict[str, Any]:
    evidence_root = Path(args.evidence_root).expanduser().resolve()
    artifact_root = evidence_root / str(args.user_id or "gmail-daemon") / "gmail-import"
    manifest_path = artifact_root / "email_import_manifest.json"
    checkpoint_path = artifact_root / "_state" / f"{str(args.checkpoint_name or 'default').strip() or 'default'}_checkpoint.json"
    progress_path = artifact_root / "_state" / f"{str(args.checkpoint_name or 'default').strip() or 'default'}_progress.json"

    summary: dict[str, Any] = {
        "artifact_root": str(artifact_root),
        "manifest_path": str(manifest_path),
        "checkpoint_path": str(checkpoint_path),
        "progress_path": str(progress_path),
        "manifest_exists": manifest_path.exists(),
        "checkpoint_exists": checkpoint_path.exists(),
        "progress_exists": progress_path.exists(),
        "imported_count": 0,
        "searched_message_count": 0,
        "raw_email_total_bytes": 0,
        "last_processed_uid": 0,
        "next_uid_upper_bound": 0,
        "folder_last_run_searched_message_count": 0,
        "checkpoint_strategy": "",
        "historical_backfill_complete": False,
        "artifact_directory_count": 0,
        "eml_file_count": 0,
        "estimated_total_messages": None,
        "estimated_total_messages_exact": False,
        "estimated_remaining_messages": None,
        "estimated_completion_ratio": None,
        "estimated_completion_percent": None,
    }

    if artifact_root.exists():
        try:
            summary["artifact_directory_count"] = sum(1 for item in artifact_root.rglob("*") if item.is_dir() and item.name != "_state" and item.parent != artifact_root / "_state")
        except Exception:
            summary["artifact_directory_count"] = 0
        try:
            summary["eml_file_count"] = sum(1 for item in artifact_root.rglob("message.eml") if item.is_file())
        except Exception:
            summary["eml_file_count"] = 0

    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            summary["imported_count"] = int(progress.get("imported_count") or 0)
            summary["searched_message_count"] = int(progress.get("searched_message_count") or 0)
            summary["raw_email_total_bytes"] = int(progress.get("raw_email_total_bytes") or 0)
            if progress.get("estimated_total_messages") is not None:
                summary["estimated_total_messages"] = int(progress.get("estimated_total_messages") or 0)
                summary["estimated_total_messages_exact"] = bool(progress.get("estimated_total_messages_exact"))
            summary["progress_status"] = str(progress.get("status") or "")
            summary["progress_updated_at"] = str(progress.get("updated_at") or "")
            summary["progress_skipped_count"] = int(progress.get("skipped_count") or 0)
            summary["progress_relevance_filtered_count"] = int(progress.get("relevance_filtered_count") or 0)
        except Exception as exc:
            summary["progress_error"] = str(exc)

    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not progress_path.exists():
                summary["imported_count"] = int(manifest.get("imported_count") or 0)
                summary["searched_message_count"] = int(manifest.get("searched_message_count") or 0)
                summary["raw_email_total_bytes"] = int(manifest.get("raw_email_total_bytes") or 0)
            summary["manifest_updated_at"] = datetime.fromtimestamp(manifest_path.stat().st_mtime, tz=UTC).isoformat()
        except Exception as exc:
            summary["manifest_error"] = str(exc)

    if checkpoint_path.exists():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            folder_state = (
                (checkpoint.get("folders") or {}).get(str(args.folder or ""))
                or {}
            )
            summary["last_processed_uid"] = int(folder_state.get("last_processed_uid") or 0)
            summary["next_uid_upper_bound"] = int(folder_state.get("next_uid_upper_bound") or 0)
            summary["folder_last_run_searched_message_count"] = int(folder_state.get("last_run_searched_message_count") or 0)
            summary["checkpoint_strategy"] = str(folder_state.get("checkpoint_strategy") or "")
            summary["historical_backfill_complete"] = bool(folder_state.get("historical_backfill_complete"))
            if folder_state.get("estimated_total_messages") is not None:
                summary["estimated_total_messages"] = int(folder_state.get("estimated_total_messages") or 0)
                summary["estimated_total_messages_exact"] = bool(folder_state.get("estimated_total_messages_exact"))
            summary["checkpoint_updated_at"] = str(folder_state.get("updated_at") or "")
        except Exception as exc:
            summary["checkpoint_error"] = str(exc)

    estimated_total = summary.get("estimated_total_messages")
    if isinstance(estimated_total, int) and estimated_total > 0:
        downloaded_count = int(summary.get("eml_file_count") or 0)
        remaining = max(0, estimated_total - downloaded_count)
        ratio = min(1.0, max(0.0, downloaded_count / float(estimated_total)))
        summary["estimated_remaining_messages"] = remaining
        summary["estimated_completion_ratio"] = ratio
        summary["estimated_completion_percent"] = round(ratio * 100.0, 2)

    return summary


def _status_artifacts(
    *,
    args: argparse.Namespace,
    pid_file: Path,
    status_file: Path,
    log_file: Path,
    progress_summary: dict[str, Any],
    last_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable artifact manifest used by daemon status consumers."""

    artifacts: dict[str, Any] = {
        "evidence_root": str(Path(args.evidence_root).expanduser().resolve()),
        "duckdb_output_dir": str(Path(args.duckdb_output_dir).expanduser().resolve()),
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
    }
    for key in ("artifact_root", "manifest_path", "checkpoint_path", "progress_path"):
        value = progress_summary.get(key)
        if value:
            artifacts[key] = str(value)

    if isinstance(last_result, dict):
        duckdb_index = last_result.get("duckdb_index")
        if isinstance(duckdb_index, dict):
            for key, value in duckdb_index.items():
                if value and (key.endswith("_path") or key.endswith("_dir")):
                    artifacts[key] = str(value)
    return artifacts


def _write_status(
    *,
    status_file: Path,
    pid_file: Path,
    log_file: Path,
    state: str,
    args: argparse.Namespace,
    last_result: dict[str, Any] | None = None,
    error: str | None = None,
    cycle_count: int = 0,
    phase: str | None = None,
    consecutive_errors: int = 0,
) -> dict[str, Any]:
    pid = None
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            pid = None
    now = datetime.now(UTC).isoformat()
    progress_summary = _build_progress_summary(args)
    artifacts = _status_artifacts(
        args=args,
        pid_file=pid_file,
        status_file=status_file,
        log_file=log_file,
        progress_summary=progress_summary,
        last_result=last_result,
    )
    payload = {
        "status": state,
        "pid": pid,
        "updated_at": now,
        "artifacts": artifacts,
        "last_error": error,
        "user_id": args.user_id,
        "gmail_user": str(args.gmail_user or ""),
        "addresses": list(args.addresses or []),
        "collect_all_messages": bool(getattr(args, "collect_all_messages", False)),
        "folder": args.folder,
        "scan_folders": list(args.scan_folder or []),
        "years_back": args.years_back,
        "checkpoint_name": args.checkpoint_name,
        "uid_window_size": args.uid_window_size,
        "uid_range_span": getattr(args, "uid_range_span", None),
        "max_batches": args.max_batches,
        "duckdb_build_every_batches": getattr(args, "duckdb_build_every_batches", None),
        "poll_seconds": args.poll_seconds,
        "retry_seconds": getattr(args, "retry_seconds", None),
        "cycle_count": int(cycle_count),
        "phase": str(phase or state),
        "consecutive_errors": int(consecutive_errors or 0),
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
        "duckdb_output_dir": str(Path(args.duckdb_output_dir).expanduser().resolve()),
        "evidence_root": str(Path(args.evidence_root).expanduser().resolve()),
        "last_updated_at": now,
        "last_result": last_result,
        "error": error,
        "progress_summary": progress_summary,
    }
    _write_json(status_file, payload)
    return payload


def _cleanup_pid_file(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    try:
        recorded = int(pid_file.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        recorded = 0
    if recorded == os.getpid():
        try:
            pid_file.unlink()
        except OSError:
            pass


def _resolve_runtime_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    duckdb_output_dir = Path(getattr(args, "duckdb_output_dir", None) or _default_duckdb_root(args.user_id)).expanduser().resolve()
    duckdb_output_dir.mkdir(parents=True, exist_ok=True)
    args.duckdb_output_dir = str(duckdb_output_dir)
    if hasattr(args, "evidence_root"):
        args.evidence_root = str(Path(getattr(args, "evidence_root", None) or _default_evidence_root(args.user_id)).expanduser().resolve())
    pid_file = Path(getattr(args, "pid_file", None) or _default_pid_file(duckdb_output_dir)).expanduser().resolve()
    status_file = Path(getattr(args, "status_file", None) or _default_status_file(duckdb_output_dir)).expanduser().resolve()
    log_file = Path(getattr(args, "log_file", None) or _default_log_file(duckdb_output_dir)).expanduser().resolve()
    return pid_file, status_file, log_file


def _add_shared_pipeline_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user-id", required=True, help="Complaint workspace user id.")
    parser.add_argument("--address", action="append", dest="addresses", default=[], help="Target address to match in From/To/Cc headers. Repeat for multiple addresses.")
    parser.add_argument("--collect-all-messages", action="store_true", help="Import the whole mailbox slice instead of requiring address matches.")
    parser.add_argument("--claim-element-id", default="causation", help="Claim element to attach imported emails to.")
    parser.add_argument("--folder", default='[Gmail]/All Mail', help="Primary Gmail IMAP folder to scan.")
    parser.add_argument("--scan-folder", action="append", default=[], help="Additional Gmail IMAP folder to scan.")
    parser.add_argument("--years-back", type=int, default=2, help="Broad collection window when --date-after is omitted.")
    parser.add_argument("--date-after", default=None, help="Only search messages on/after this date (YYYY-MM-DD).")
    parser.add_argument("--date-before", default=None, help="Only search messages before this date (YYYY-MM-DD).")
    parser.add_argument("--complaint-query", default=None, help="Free-text complaint description used to rank/filter likely relevant emails.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Repeatable complaint keyword or phrase.")
    parser.add_argument("--min-relevance-score", type=float, default=0.0, help="Minimum complaint relevance score required to import a message.")
    parser.add_argument("--workspace-root", default=".complaint_workspace/sessions", help="Workspace session root.")
    parser.add_argument("--evidence-root", default=None, help="Directory to write imported email artifacts to.")
    parser.add_argument("--duckdb-output-dir", default=None, help="Directory for DuckDB/parquet email index artifacts.")
    parser.add_argument("--gmail-user", default=os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER"), help="Gmail address.")
    parser.add_argument("--gmail-app-password", default=os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASS"), help="Gmail app password.")
    parser.add_argument("--use-gmail-oauth", action="store_true", help="Authenticate to Gmail IMAP with OAuth/XOAUTH2 instead of an app password.")
    parser.add_argument("--gmail-oauth-client-secrets", default=os.environ.get("GMAIL_OAUTH_CLIENT_SECRETS"), help="Google OAuth client-secrets JSON path.")
    parser.add_argument("--gmail-oauth-token-cache", default=os.environ.get("GMAIL_OAUTH_TOKEN_CACHE"), help="Optional Gmail OAuth token-cache path.")
    parser.add_argument("--no-gmail-oauth-browser", action="store_true", help="Do not automatically open the browser during the Gmail OAuth flow.")
    parser.add_argument("--prompt-for-credentials", action="store_true", help="Prompt interactively for Gmail credentials. Password input is hidden.")
    parser.add_argument("--use-keyring", action="store_true", help="Load the Gmail app password from the OS keyring when available.")
    parser.add_argument("--save-to-keyring", action="store_true", help="Save the resolved Gmail app password to the OS keyring when available.")
    parser.add_argument("--use-ipfs-secrets-vault", action="store_true", help="Load the Gmail app password from the ipfs_datasets_py DID-derived secrets vault.")
    parser.add_argument("--save-to-ipfs-secrets-vault", action="store_true", help="Save the resolved Gmail app password to the ipfs_datasets_py DID-derived secrets vault.")
    parser.add_argument("--checkpoint-name", default="gmail-duckdb-daemon", help="Checkpoint name for resumable mailbox collection.")
    parser.add_argument("--uid-window-size", type=int, default=500, help="Maximum number of newly discovered UID messages to import per batch.")
    parser.add_argument("--uid-range-span", type=int, default=50000, help="UID range span to search per IMAP backfill chunk so very large mailboxes do not require one giant UID SEARCH result.")
    parser.add_argument("--max-batches", type=int, default=10, help="Maximum number of checkpointed Gmail batches to ingest per daemon cycle.")
    parser.add_argument("--duckdb-build-every-batches", type=int, default=10, help="How many Gmail import batches to accumulate before refreshing DuckDB/parquet artifacts. Higher values reduce index-write pressure on huge crawls.")
    parser.add_argument("--append-to-existing-corpus", action="store_true", help="Append the first batch into an existing DuckDB corpus instead of rebuilding it.")
    parser.add_argument("--bm25-search-query", default=None, help="Optional keyword query to run against the final DuckDB BM25 email index.")
    parser.add_argument("--bm25-search-limit", type=int, default=20, help="Maximum number of BM25 hits to return.")
    parser.add_argument("--poll-seconds", type=float, default=900.0, help="Delay between daemon cycles.")
    parser.add_argument("--retry-seconds", type=float, default=60.0, help="Delay before retrying after a failed cycle.")
    parser.add_argument("--max-consecutive-errors", type=int, default=0, help="Maximum consecutive cycle errors before exit. 0 means retry indefinitely.")
    parser.add_argument("--max-cycles", type=int, default=0, help="Maximum daemon cycles before exit. 0 means run until stopped.")
    parser.add_argument("--pid-file", default=None, help="Optional PID file path.")
    parser.add_argument("--status-file", default=None, help="Optional daemon status JSON path.")
    parser.add_argument("--log-file", default=None, help="Optional daemon log file path.")
    parser.add_argument("--json", action="store_true", help="Print JSON output for start/status/stop commands.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a resumable Gmail-to-DuckDB daemon.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ingestion options for run/start include:\n"
            "  --uid-range-span\n"
            "  --duckdb-build-every-batches\n"
            "Use run --help or start --help for the full option list."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the Gmail DuckDB daemon in the foreground.")
    _add_shared_pipeline_args(run_parser)

    start_parser = subparsers.add_parser("start", help="Start the Gmail DuckDB daemon in the background.")
    _add_shared_pipeline_args(start_parser)

    status_parser = subparsers.add_parser("status", help="Show Gmail DuckDB daemon status.")
    status_parser.add_argument("--user-id", required=True, help="Complaint workspace user id.")
    status_parser.add_argument("--duckdb-output-dir", default=None, help="Directory for DuckDB/parquet email index artifacts.")
    status_parser.add_argument("--status-file", default=None, help="Optional daemon status JSON path.")
    status_parser.add_argument("--pid-file", default=None, help="Optional PID file path.")
    status_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    stop_parser = subparsers.add_parser("stop", help="Stop the Gmail DuckDB daemon.")
    stop_parser.add_argument("--user-id", required=True, help="Complaint workspace user id.")
    stop_parser.add_argument("--duckdb-output-dir", default=None, help="Directory for DuckDB/parquet email index artifacts.")
    stop_parser.add_argument("--status-file", default=None, help="Optional daemon status JSON path.")
    stop_parser.add_argument("--pid-file", default=None, help="Optional PID file path.")
    stop_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    return parser


def _resolve_credentials(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[str, str]:
    if getattr(args, "use_gmail_oauth", False):
        gmail_user = str(args.gmail_user or "").strip()
        if not gmail_user:
            parser.error("--gmail-user is required when --use-gmail-oauth is enabled.")
        if not getattr(args, "gmail_oauth_client_secrets", None):
            parser.error("--gmail-oauth-client-secrets is required when --use-gmail-oauth is enabled.")
        return gmail_user, ""
    resolve_gmail_credentials = _require_ipfs_attr(
        "email_auth",
        "resolve_gmail_credentials",
        "Gmail credential resolver",
    )
    return resolve_gmail_credentials(
        gmail_user=str(args.gmail_user or ""),
        gmail_app_password=str(args.gmail_app_password or ""),
        prompt_for_credentials=bool(args.prompt_for_credentials),
        use_keyring=bool(args.use_keyring),
        save_to_keyring_flag=bool(args.save_to_keyring),
        use_ipfs_secrets_vault=bool(getattr(args, "use_ipfs_secrets_vault", False)),
        save_to_ipfs_secrets_vault_flag=bool(getattr(args, "save_to_ipfs_secrets_vault", False)),
        parser=parser,
    )


async def _run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    return await run_gmail_duckdb_pipeline(
        user_id=args.user_id,
        addresses=args.addresses,
        collect_all_messages=bool(getattr(args, "collect_all_messages", False)),
        claim_element_id=args.claim_element_id,
        folder=args.folder,
        folders=args.scan_folder,
        years_back=args.years_back,
        date_after=args.date_after,
        date_before=args.date_before,
        complaint_query=args.complaint_query,
        complaint_keywords=args.complaint_keyword,
        min_relevance_score=args.min_relevance_score,
        workspace_root=Path(args.workspace_root),
        evidence_root=Path(args.evidence_root),
        gmail_user=args.gmail_user,
        gmail_app_password=args.gmail_app_password,
        use_gmail_oauth=args.use_gmail_oauth,
        gmail_oauth_client_secrets=args.gmail_oauth_client_secrets,
        gmail_oauth_token_cache=args.gmail_oauth_token_cache,
        gmail_oauth_open_browser=not bool(args.no_gmail_oauth_browser),
        checkpoint_name=args.checkpoint_name,
        uid_window_size=args.uid_window_size,
        uid_range_span=args.uid_range_span,
        max_batches=args.max_batches,
        duckdb_build_every_batches=args.duckdb_build_every_batches,
        duckdb_output_dir=args.duckdb_output_dir,
        append_to_existing_corpus=bool(args.append_to_existing_corpus),
        bm25_search_query=args.bm25_search_query,
        bm25_search_limit=args.bm25_search_limit,
    )


def _run_daemon(args: argparse.Namespace) -> dict[str, Any]:
    global _STOP_REQUESTED
    _STOP_REQUESTED = False
    signal.signal(signal.SIGTERM, _signal_stop)
    signal.signal(signal.SIGINT, _signal_stop)

    pid_file, status_file, log_file = _resolve_runtime_paths(args)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")

    cycle_count = 0
    consecutive_errors = 0
    last_result: dict[str, Any] | None = None
    status_state: dict[str, Any] = {
        "phase": "starting",
        "cycle_count": cycle_count,
        "last_result": None,
        "error": None,
        "consecutive_errors": consecutive_errors,
    }

    def _heartbeat() -> None:
        while not _STOP_REQUESTED:
            _write_status(
                status_file=status_file,
                pid_file=pid_file,
                log_file=log_file,
                state="running",
                args=args,
                last_result=status_state.get("last_result"),
                error=status_state.get("error"),
                cycle_count=int(status_state.get("cycle_count") or 0),
                phase=str(status_state.get("phase") or "running"),
                consecutive_errors=int(status_state.get("consecutive_errors") or 0),
            )
            time.sleep(15.0)

    heartbeat = threading.Thread(target=_heartbeat, name="gmail-duckdb-daemon-heartbeat", daemon=True)
    _write_status(
        status_file=status_file,
        pid_file=pid_file,
        log_file=log_file,
        state="running",
        args=args,
        cycle_count=cycle_count,
        phase="starting",
        consecutive_errors=consecutive_errors,
    )
    heartbeat.start()
    try:
        while not _STOP_REQUESTED:
            cycle_count += 1
            status_state["cycle_count"] = cycle_count
            status_state["phase"] = "running_cycle"
            try:
                last_result = anyio.run(_run_cycle, args)
                consecutive_errors = 0
                status_state["last_result"] = last_result
                status_state["error"] = None
                status_state["consecutive_errors"] = consecutive_errors
                status_state["phase"] = "sleeping"
                _write_status(
                    status_file=status_file,
                    pid_file=pid_file,
                    log_file=log_file,
                    state="running",
                    args=args,
                    last_result=last_result,
                    cycle_count=cycle_count,
                    phase="sleeping",
                    consecutive_errors=consecutive_errors,
                )
            except Exception as exc:
                consecutive_errors += 1
                status_state["error"] = str(exc)
                status_state["consecutive_errors"] = consecutive_errors
                status_state["phase"] = "error"
                _write_status(
                    status_file=status_file,
                    pid_file=pid_file,
                    log_file=log_file,
                    state="error",
                    args=args,
                    last_result=last_result,
                    error=str(exc),
                    cycle_count=cycle_count,
                    phase="error",
                    consecutive_errors=consecutive_errors,
                )
                if _STOP_REQUESTED:
                    break
                max_consecutive_errors = int(args.max_consecutive_errors or 0)
                if max_consecutive_errors > 0 and consecutive_errors >= max_consecutive_errors:
                    raise
                status_state["phase"] = "retrying_after_error"
                _write_status(
                    status_file=status_file,
                    pid_file=pid_file,
                    log_file=log_file,
                    state="running",
                    args=args,
                    last_result=last_result,
                    error=str(exc),
                    cycle_count=cycle_count,
                    phase="retrying_after_error",
                    consecutive_errors=consecutive_errors,
                )
                time.sleep(max(float(args.retry_seconds or 0.0), 0.0))
                continue
            if _STOP_REQUESTED:
                break
            if int(args.max_cycles or 0) > 0 and cycle_count >= int(args.max_cycles):
                break
            time.sleep(max(float(args.poll_seconds or 0.0), 0.0))
    finally:
        final_state = "stopped" if _STOP_REQUESTED else "completed"
        status_state["phase"] = final_state
        _write_status(
            status_file=status_file,
            pid_file=pid_file,
            log_file=log_file,
            state=final_state,
            args=args,
            last_result=last_result,
            error=status_state.get("error"),
            cycle_count=cycle_count,
            phase=final_state,
            consecutive_errors=consecutive_errors,
        )
        _cleanup_pid_file(pid_file)
    return {
        "status": "success",
        "daemon_state": final_state,
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
        "cycle_count": cycle_count,
        "last_result": last_result,
    }


def _build_run_command(args: argparse.Namespace, *, pid_file: Path, status_file: Path, log_file: Path) -> tuple[list[str], dict[str, str]]:
    cmd = [
        sys.executable,
        "-m",
        "scripts.gmail_duckdb_daemon",
        "run",
        "--user-id",
        args.user_id,
    ]
    for address in list(args.addresses or []):
        cmd.extend(["--address", address])
    if getattr(args, "collect_all_messages", False):
        cmd.append("--collect-all-messages")
    cmd.extend(["--claim-element-id", args.claim_element_id])
    cmd.extend(["--folder", args.folder])
    for folder_name in list(args.scan_folder or []):
        cmd.extend(["--scan-folder", folder_name])
    if args.years_back is not None:
        cmd.extend(["--years-back", str(args.years_back)])
    if args.date_after:
        cmd.extend(["--date-after", str(args.date_after)])
    if args.date_before:
        cmd.extend(["--date-before", str(args.date_before)])
    if args.complaint_query:
        cmd.extend(["--complaint-query", str(args.complaint_query)])
    for keyword in list(args.complaint_keyword or []):
        cmd.extend(["--complaint-keyword", keyword])
    cmd.extend(["--min-relevance-score", str(args.min_relevance_score)])
    cmd.extend(["--workspace-root", str(args.workspace_root)])
    cmd.extend(["--evidence-root", str(args.evidence_root)])
    if args.gmail_user:
        cmd.extend(["--gmail-user", str(args.gmail_user)])
    if args.use_gmail_oauth:
        cmd.append("--use-gmail-oauth")
    if args.gmail_oauth_client_secrets:
        cmd.extend(["--gmail-oauth-client-secrets", str(args.gmail_oauth_client_secrets)])
    if args.gmail_oauth_token_cache:
        cmd.extend(["--gmail-oauth-token-cache", str(args.gmail_oauth_token_cache)])
    if args.no_gmail_oauth_browser:
        cmd.append("--no-gmail-oauth-browser")
    if args.use_keyring:
        cmd.append("--use-keyring")
    if args.save_to_keyring:
        cmd.append("--save-to-keyring")
    if args.use_ipfs_secrets_vault:
        cmd.append("--use-ipfs-secrets-vault")
    if args.save_to_ipfs_secrets_vault:
        cmd.append("--save-to-ipfs-secrets-vault")
    cmd.extend(["--checkpoint-name", str(args.checkpoint_name)])
    cmd.extend(["--uid-window-size", str(args.uid_window_size)])
    cmd.extend(["--uid-range-span", str(args.uid_range_span)])
    cmd.extend(["--max-batches", str(args.max_batches)])
    cmd.extend(["--duckdb-build-every-batches", str(args.duckdb_build_every_batches)])
    cmd.extend(["--duckdb-output-dir", str(args.duckdb_output_dir)])
    if args.append_to_existing_corpus:
        cmd.append("--append-to-existing-corpus")
    if args.bm25_search_query:
        cmd.extend(["--bm25-search-query", str(args.bm25_search_query)])
    cmd.extend(["--bm25-search-limit", str(args.bm25_search_limit)])
    cmd.extend(["--poll-seconds", str(args.poll_seconds)])
    cmd.extend(["--max-cycles", str(args.max_cycles)])
    cmd.extend(["--pid-file", str(pid_file), "--status-file", str(status_file), "--log-file", str(log_file)])

    env = dict(os.environ)
    if args.gmail_app_password:
        env["GMAIL_APP_PASSWORD"] = str(args.gmail_app_password)
    return cmd, env


def _start_daemon(args: argparse.Namespace) -> dict[str, Any]:
    pid_file, status_file, log_file = _resolve_runtime_paths(args)
    if pid_file.exists():
        try:
            current_pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            current_pid = 0
        if _pid_is_running(current_pid):
            return {
                "status": "already_running",
                "pid": current_pid,
                "pid_file": str(pid_file),
                "status_file": str(status_file),
                "log_file": str(log_file),
            }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    cmd, env = _build_run_command(args, pid_file=pid_file, status_file=status_file, log_file=log_file)
    with log_file.open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=handle,
            stderr=handle,
            start_new_session=True,
        )
    time.sleep(0.5)
    payload = {
        "status": "started",
        "pid": int(process.pid),
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
        "command": cmd,
    }
    return payload


def _status_payload(args: argparse.Namespace) -> dict[str, Any]:
    pid_file, status_file, log_file = _resolve_runtime_paths(args)
    payload: dict[str, Any] = {
        "status": "missing",
        "updated_at": datetime.now(UTC).isoformat(),
        "artifacts": {
            "duckdb_output_dir": str(Path(args.duckdb_output_dir).expanduser().resolve()),
            "pid_file": str(pid_file),
            "status_file": str(status_file),
            "log_file": str(log_file),
        },
        "last_error": None,
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
        "pid": None,
        "running": False,
        "status_payload": None,
    }
    if pid_file.exists():
        try:
            payload["pid"] = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            payload["pid"] = None
    payload["running"] = _pid_is_running(int(payload["pid"] or 0))
    if status_file.exists():
        payload["status"] = "ok"
        status_payload = json.loads(status_file.read_text(encoding="utf-8"))
        payload["status_payload"] = status_payload
        if isinstance(status_payload, dict):
            payload["updated_at"] = str(
                status_payload.get("updated_at")
                or status_payload.get("last_updated_at")
                or payload["updated_at"]
            )
            payload["artifacts"] = dict(status_payload.get("artifacts") or payload["artifacts"])
            payload["last_error"] = status_payload.get("last_error", status_payload.get("error"))
    return payload


def _stop_daemon(args: argparse.Namespace) -> dict[str, Any]:
    pid_file, status_file, log_file = _resolve_runtime_paths(args)
    pid = 0
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            pid = 0
    if not _pid_is_running(pid):
        return {
            "status": "not_running",
            "pid": pid or None,
            "pid_file": str(pid_file),
            "status_file": str(status_file),
            "log_file": str(log_file),
        }
    os.kill(pid, signal.SIGTERM)
    return {
        "status": "stopping",
        "pid": pid,
        "pid_file": str(pid_file),
        "status_file": str(status_file),
        "log_file": str(log_file),
    }


def _format_status_payload_text(payload: dict[str, Any]) -> str:
    status_payload = payload.get("status_payload") or {}
    progress = status_payload.get("progress_summary") or {}
    lines = [
        f"Daemon status: {status_payload.get('status') or payload.get('status') or 'unknown'}",
        f"Running: {'yes' if payload.get('running') else 'no'}",
        f"Phase: {status_payload.get('phase') or 'unknown'}",
    ]
    completion_percent = progress.get("estimated_completion_percent")
    downloaded = progress.get("eml_file_count")
    estimated_total = progress.get("estimated_total_messages")
    if completion_percent is not None and estimated_total:
        lines.append(
            f"Progress: {int(downloaded or 0)} / {int(estimated_total)} ({float(completion_percent):.2f}%)"
        )
    elif downloaded is not None:
        lines.append(f"Downloaded emails: {int(downloaded)}")
    remaining = progress.get("estimated_remaining_messages")
    if remaining is not None:
        lines.append(f"Estimated remaining: {int(remaining)}")
    if progress.get("raw_email_total_bytes") is not None:
        lines.append(f"Raw email bytes: {int(progress.get('raw_email_total_bytes') or 0)}")
    if progress.get("last_processed_uid") is not None:
        lines.append(f"Last processed UID: {int(progress.get('last_processed_uid') or 0)}")
    if progress.get("next_uid_upper_bound") is not None:
        lines.append(f"Next UID upper bound: {int(progress.get('next_uid_upper_bound') or 0)}")
    lines.append(f"Status file: {payload.get('status_file')}")
    return "\n".join(lines)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {"run", "start"}:
        if not getattr(args, "collect_all_messages", False) and not list(getattr(args, "addresses", []) or []):
            parser.error("Provide at least one --address or use --collect-all-messages.")
        args.gmail_user, args.gmail_app_password = _resolve_credentials(args, parser)
        _resolve_runtime_paths(args)

    if args.command == "run":
        payload = _run_daemon(args)
    elif args.command == "start":
        payload = _start_daemon(args)
    elif args.command == "status":
        payload = _status_payload(args)
    elif args.command == "stop":
        payload = _stop_daemon(args)
    else:
        parser.error(f"Unsupported command: {args.command}")
        return 2

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if args.command == "status":
            print(_format_status_payload_text(payload))
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
