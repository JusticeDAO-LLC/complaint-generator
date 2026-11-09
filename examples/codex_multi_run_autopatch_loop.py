import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _run(cmd: list[str], *, cwd: Optional[str] = None, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
    )


def _run_streaming(cmd: list[str], *, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        lines.append(line)

        if "Codex usage-limit:" in line and "sleeping" in line:
            artifact_path = None
            reset_at = None
            reset_source = None
            provider_reset_at = None
            sleep_s = None
            attempt = None

            # Child line format includes: "(wrote /abs/path/to/codex_rate_limit_*.json);"
            m = re.search(r"\(wrote\s+([^\)]+)\)", line)
            if m:
                artifact_path = m.group(1).strip()
                # Some outputs include a trailing ';' before ')'
                artifact_path = artifact_path.rstrip("; ")

            if artifact_path and os.path.isfile(artifact_path):
                try:
                    with open(artifact_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    reset_at = data.get("reset_at")
                    reset_source = data.get("reset_source")
                    provider_reset_at = data.get("provider_reset_at")
                except Exception:
                    reset_at = None

            if not reset_at:
                m2 = re.search(r"reset_at=([^\s]+)", line)
                if m2:
                    reset_at = m2.group(1).strip()

            ms = re.search(r"sleeping\s+(\d+)s", line)
            if ms:
                try:
                    sleep_s = int(ms.group(1))
                except Exception:
                    sleep_s = None

            ma = re.search(r"attempt=(\d+)", line)
            if ma:
                try:
                    attempt = int(ma.group(1))
                except Exception:
                    attempt = None

            # Prefer provider reset time when available (credits reset), otherwise treat as backoff next-retry time.
            effective_reset_at = provider_reset_at or reset_at
            if effective_reset_at and reset_source in {"try_again_at", "reset_at"}:
                msg = f"[loop] Codex credits reset at {effective_reset_at}"
            elif effective_reset_at:
                msg = f"[loop] waiting to retry Codex until {effective_reset_at}"
            else:
                msg = "[loop] waiting to retry Codex (reset ETA unknown)"

            details: list[str] = []
            if sleep_s is not None:
                details.append(f"sleep_s={sleep_s}")
            if attempt is not None:
                details.append(f"attempt={attempt}")
            if details:
                msg += " (" + ", ".join(details) + ")"

            if artifact_path:
                msg += f" (artifact={artifact_path})"
            print(msg)
    rc = proc.wait()
    return subprocess.CompletedProcess(cmd, rc, "".join(lines), None)


def _git_has_changes() -> bool:
    proc = _run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, capture=True)
    return bool((proc.stdout or "").strip())


def _extract_summary_path(output: str) -> Optional[str]:
    lines = (output or "").splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("[done] summary="):
            return line.split("=", 1)[1].strip()
    return None


def _load_orchestrator_id(summary_path: str) -> Optional[str]:
    """Load an orchestrator id from an advertised summary artifact.

    The child process prints the summary path only after writing the artifact.
    Read and decode failures therefore indicate a broken artifact and must remain
    visible instead of being confused with an omitted ``orchestrator_id`` field.
    """

    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object in {summary_path!r}, got {type(data).__name__}"
        )
    orchestrator_id = data.get("orchestrator_id")
    if orchestrator_id is not None and not isinstance(orchestrator_id, str):
        raise ValueError(
            f"Expected 'orchestrator_id' in {summary_path!r} to be a string, "
            f"got {type(orchestrator_id).__name__}"
        )
    return orchestrator_id


def _load_json_or_none(path: str) -> Optional[dict]:
    """Load an optional JSON object, returning ``None`` only when it is absent."""

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object in {path!r}, got {type(data).__name__}"
        )
    return data


def _atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Loop: run 10×10 Codex multi-run autopatch repeatedly, and commit local changes after each loop."
        )
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--state-dir", default="statefiles")
    parser.add_argument("--batch-backend-id", default=None)
    parser.add_argument("--codex-backend-id", default="llm-router-codex")

    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--sessions-per-run", type=int, default=10)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--max-parallel", type=int, default=2)

    parser.add_argument(
        "--codex-wait-on-429-fallback-s",
        type=int,
        default=None,
        help=(
            "When Codex 429 does not include a reset timestamp, sleep this many seconds on the first retry and then back off. "
            "If omitted, uses the driver default."
        ),
    )
    parser.add_argument(
        "--codex-wait-on-429-fallback-max-s",
        type=int,
        default=None,
        help=(
            "Maximum sleep seconds when using fallback/exponential backoff because Codex reset timing is unknown. "
            "If omitted, uses the driver default."
        ),
    )

    parser.add_argument(
        "--codex-exit-on-429",
        action="store_true",
        help=(
            "Do not wait indefinitely through Codex 429s. If a 429 is encountered, let the orchestrator fail fast "
            "(exit code 2 from codex_autopatch_from_run.py) so finite --loops/--runs jobs can terminate."
        ),
    )

    parser.add_argument("--generate-fix-max-attempts", type=int, default=2)
    parser.add_argument("--apply-fix-max-attempts", type=int, default=2)

    parser.add_argument(
        "--loops",
        type=int,
        default=0,
        help="Number of loops to run. 0 means infinite until interrupted.",
    )
    parser.add_argument("--sleep-s", type=float, default=0.0)

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume the most recent in-progress loop iteration by reusing the saved orchestrator id and passing --resume to the orchestrator."
        ),
    )
    parser.add_argument(
        "--loop-state-path",
        default=None,
        help=(
            "Optional JSON file path used to persist loop progress for --resume. "
            "Defaults to <state-dir>/_runs/_codex_multi_run_autopatch_loop_state.json."
        ),
    )

    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit changes after each loop (default).",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Do not commit changes after each loop.",
    )

    args = parser.parse_args()

    do_commit = True
    if args.commit:
        do_commit = True
    if args.no_commit:
        do_commit = False

    python_exe = sys.executable
    state_path = (
        str(args.loop_state_path)
        if args.loop_state_path
        else os.path.join(args.state_dir, "_runs", "_codex_multi_run_autopatch_loop_state.json")
    )
    state = _load_json_or_none(state_path) or {}
    loop_index = int(state.get("loop_index", 0) or 0)
    active_orchestrator_id = state.get("active_orchestrator_id") if isinstance(state.get("active_orchestrator_id"), str) else None

    loops_target = int(args.loops or 0)
    print(
        "[loop] init "
        + f"state={os.path.abspath(state_path)} "
        + f"resume={bool(args.resume)} "
        + f"exit_on_429={bool(args.codex_exit_on_429)} "
        + f"loops_target={loops_target} "
        + f"loop_index={loop_index} "
        + f"active_orchestrator_id={(active_orchestrator_id or 'none')}"
        ,
        flush=True,
    )
    if bool(args.resume) and not active_orchestrator_id:
        print("[loop] resume requested but no active orchestrator id; starting a new iteration", flush=True)

    try:
        while True:
            if active_orchestrator_id and args.resume:
                print(f"[loop] {loop_index} resuming orchestrator_id={active_orchestrator_id}", flush=True)
                orchestrator_id = active_orchestrator_id
                is_resume = True
            else:
                next_loop_index = loop_index + 1
                if args.loops and next_loop_index > args.loops:
                    msg = (
                        "[loop] exiting (loops limit reached) "
                        + f"loop_index={loop_index} loops_target={int(args.loops)}"
                    )
                    if active_orchestrator_id and not bool(args.resume):
                        msg += (
                            "\n[loop] note: an in-progress orchestrator id is saved: "
                            + f"{active_orchestrator_id}. Re-run with --resume to continue it."
                        )
                    print(msg, flush=True)
                    break
                loop_index = next_loop_index

                orchestrator_id = f"autopatch_loop_{loop_index:04d}_{_utc_stamp()}"
                active_orchestrator_id = orchestrator_id
                is_resume = False
                print(f"[loop] {loop_index} starting orchestrator_id={orchestrator_id}", flush=True)

            state = {
                **(state if isinstance(state, dict) else {}),
                "ts": datetime.now(timezone.utc).isoformat(),
                "loop_index": int(loop_index),
                "active_orchestrator_id": str(orchestrator_id),
            }
            _atomic_write_json(state_path, state)

            cmd = [
                python_exe,
                os.path.join(PROJECT_ROOT, "examples", "codex_multi_run_autopatch.py"),
                "--config",
                args.config,
                "--state-dir",
                args.state_dir,
                "--codex-backend-id",
                args.codex_backend_id,
                "--orchestrator-id",
                str(orchestrator_id),
                "--runs",
                str(args.runs),
                "--sessions-per-run",
                str(args.sessions_per_run),
                "--max-turns",
                str(args.max_turns),
                "--max-parallel",
                str(args.max_parallel),
                "--generate-fix-max-attempts",
                str(args.generate_fix_max_attempts),
                "--apply-fix-max-attempts",
                str(args.apply_fix_max_attempts),
                "--undo-on-test-failure",
            ]

            # Default behavior is to wait indefinitely through Codex 429s.
            # For small, finite jobs (e.g. --loops 1 --runs 1), you can opt out with --codex-exit-on-429.
            if not bool(args.codex_exit_on_429):
                cmd += ["--codex-wait-forever-on-429"]
            if args.codex_wait_on_429_fallback_s is not None:
                cmd += ["--codex-wait-on-429-fallback-s", str(int(args.codex_wait_on_429_fallback_s))]
            if args.codex_wait_on_429_fallback_max_s is not None:
                cmd += ["--codex-wait-on-429-fallback-max-s", str(int(args.codex_wait_on_429_fallback_max_s))]
            if is_resume:
                cmd += ["--resume"]
            if args.batch_backend_id:
                cmd += ["--batch-backend-id", args.batch_backend_id]

            proc = _run_streaming(cmd, cwd=PROJECT_ROOT)

            summary_path = _extract_summary_path(proc.stdout or "")
            orchestrator_id = _load_orchestrator_id(summary_path) if summary_path else None

            if proc.returncode != 0:
                print(f"[loop] orchestrator failed exit={proc.returncode}", flush=True)
                # Do not auto-commit on a failed loop.
                state = {
                    **(state if isinstance(state, dict) else {}),
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "last_exit_code": int(proc.returncode),
                }
                _atomic_write_json(state_path, state)
                # Avoid a tight failure loop (especially when --resume keeps selecting the same orchestrator id).
                return int(proc.returncode)
            else:
                print(f"[loop] ok orchestrator_id={orchestrator_id or 'unknown'}", flush=True)

                # Clear active orchestrator on success.
                active_orchestrator_id = None
                state = {
                    **(state if isinstance(state, dict) else {}),
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "loop_index": int(loop_index),
                    "active_orchestrator_id": None,
                    "last_exit_code": int(proc.returncode),
                }
                _atomic_write_json(state_path, state)

                if do_commit:
                    if _git_has_changes():
                        msg_id = orchestrator_id or _utc_stamp()
                        msg = f"autopatch loop {msg_id}"
                        add = _run(["git", "add", "-A"], cwd=PROJECT_ROOT)
                        if add.returncode != 0:
                            print("[git] add failed")
                        else:
                            commit = _run(["git", "commit", "-m", msg], cwd=PROJECT_ROOT, capture=True)
                            if commit.returncode != 0:
                                out = (commit.stdout or "").strip()
                                print(f"[git] commit failed: {out}")
                            else:
                                print(f"[git] committed: {msg}")
                    else:
                        print("[git] no changes to commit")

            if args.sleep_s > 0:
                time.sleep(args.sleep_s)

    except KeyboardInterrupt:
        print("[loop] interrupted", flush=True)
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
