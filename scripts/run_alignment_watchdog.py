#!/usr/bin/env python3
"""Repair the alignment execution board and finish ready tasks.

Use --watch --max-cycles 0 to monitor until completion. It stays off the
HTTP request path and records only local source-check evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.ipfs_accelerate.alignment_plan import (  # noqa: E402
    BOARD_RELATIVE,
    PLAN_RELATIVE,
    STATE_RELATIVE,
    publish_alignment_execution_board,
)
from integrations.ipfs_accelerate.watchdog import run_watchdog  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair and advance the complaint alignment board.")
    parser.add_argument("--plan", default=str(ROOT / PLAN_RELATIVE))
    parser.add_argument(
        "--state",
        default=str(ROOT / STATE_RELATIVE),
    )
    parser.add_argument("--max-cycles", type=int, default=64)
    parser.add_argument("--stall-seconds", type=int, default=120)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--watch", action="store_true", help="Keep polling incomplete or held work.")
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--checker-timeout-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    summary = run_watchdog(
        plan_path=Path(args.plan),
        state_path=Path(args.state),
        repo_root=ROOT,
        max_cycles=args.max_cycles,
        stall_seconds=args.stall_seconds,
        max_attempts=args.max_attempts,
        monitor=args.watch,
        poll_seconds=args.poll_seconds,
        checker_timeout_seconds=args.checker_timeout_seconds,
    )
    published = publish_alignment_execution_board(
        ROOT, plan_path=Path(args.plan), state_path=Path(args.state),
    )
    public = {
        "status": summary["status"],
        "completed": summary["completed"],
        "cycles": summary["cycles"],
        "plan_id": summary["plan_id"],
        "last_action": summary["last_action"],
        "task_counts": summary["task_counts"],
        "supervisor_status": summary["supervisor_status"],
        "repair_count": len(summary["repairs"]),
        "off_request_path": summary["off_request_path"],
        "seed_board": BOARD_RELATIVE,
        "execution_board": str(published) if published else None,
        "state_path": str(Path(args.state).resolve()),
        "evidence_kind": summary["evidence_kind"],
        "pending_tasks": summary["pending_tasks"],
    }
    json.dump(public, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if summary["completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
