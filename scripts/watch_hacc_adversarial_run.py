#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _truncate(text: str, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _print_report(run_dir: Path) -> None:
    summary_path = run_dir / "run_summary.json"
    optimization_path = run_dir / "optimization_report.json"
    best_bundle_path = run_dir / "best_complaint_bundle.json"

    summary = _load_json(summary_path)
    optimization = _load_json(optimization_path)
    best_bundle = _load_json(best_bundle_path)

    runtime = summary.get("runtime", {})
    stats = summary.get("statistics", {})
    best = summary.get("best_complaint", {})
    critic_score = best_bundle.get("critic_score") or {}

    print(f"Run directory: {run_dir}")
    print(f"Mode: {runtime.get('mode')} | Provider: {runtime.get('provider')} | Model: {runtime.get('model')}")
    print(
        "Sessions: "
        f"{stats.get('successful_sessions', 0)}/{stats.get('total_sessions', 0)} successful | "
        f"Average score: {stats.get('average_score')} | "
        f"Average duration: {stats.get('average_duration')}"
    )
    print(f"Best session: {optimization.get('best_session_id')}")
    print(f"Best complaint score: {best.get('score')}")
    print("Best complaint:")
    print(_truncate(best_bundle.get("initial_complaint_text", ""), 1200))

    feedback = critic_score.get("feedback")
    if feedback:
        print("\nCritic feedback:")
        print(_truncate(feedback, 800))

    recommendations = optimization.get("recommendations") or []
    if recommendations:
        print("\nTop recommendations:")
        for item in recommendations[:5]:
            print(f"- {item}")

    print("\nArtifacts:")
    for name in (
        "run_summary.json",
        "optimization_report.json",
        "best_complaint_bundle.json",
        "adversarial_results.json",
        "anchor_section_coverage.csv",
    ):
        path = run_dir / name
        if path.exists():
            print(f"- {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait for a HACC adversarial run to finish and print a concise report."
    )
    parser.add_argument("run_dir", help="Path to the adversarial run output directory")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=0.0, help="Seconds to wait before giving up; 0 means no timeout")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        print(f"Run directory does not exist: {run_dir}", file=sys.stderr)
        return 1

    required = [
        run_dir / "run_summary.json",
        run_dir / "optimization_report.json",
        run_dir / "best_complaint_bundle.json",
    ]

    start = time.monotonic()
    while True:
        if all(path.exists() and path.stat().st_size > 0 for path in required):
            _print_report(run_dir)
            return 0

        if args.timeout and (time.monotonic() - start) >= args.timeout:
            missing = [str(path) for path in required if not path.exists() or path.stat().st_size == 0]
            print("Timed out waiting for run artifacts:", file=sys.stderr)
            for item in missing:
                print(f"- {item}", file=sys.stderr)
            return 2

        time.sleep(max(0.5, args.poll_interval))


if __name__ == "__main__":
    raise SystemExit(main())
