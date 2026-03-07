#!/usr/bin/env python3
"""Validate canary-ops task wiring and summarizer CLI availability.

This script is CI-safe: it does not run `run.py` or start the server.
It verifies:
1) `.vscode/tasks.json` exists and is valid JSON.
2) Required canary task labels are present.
3) Task command strings include expected script/flag fragments.
4) Root `Makefile` exposes required canary targets.
5) GitHub Actions workflow exists and runs `make canary-validate`.
6) `scripts/summarize_reranker_metrics.py --help` executes successfully.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = REPO_ROOT / ".vscode" / "tasks.json"
SUMMARIZER_PATH = REPO_ROOT / "scripts" / "summarize_reranker_metrics.py"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "canary-ops-validation.yml"

REQUIRED_TASKS = {
    "Canary: Run + Export + Summarize Reranker Metrics": [
        "run.py",
        "--export-reranker-metrics",
        "scripts/summarize_reranker_metrics.py",
        "--summary-out",
    ],
    "Canary: Summarize Latest Reranker Metrics Export": [
        "scripts/summarize_reranker_metrics.py",
        "--input",
        "--summary-out",
    ],
    "Canary: Generate Sample + Summarize Reranker Metrics": [
        "Mediator",
        "update_reranker_metrics",
        "scripts/summarize_reranker_metrics.py",
        "--summary-out",
    ],
}

REQUIRED_MAKE_TARGETS = {
    "canary-validate": [
        "scripts/validate_canary_ops.py",
        "tests/test_canary_ops_validation.py -q",
    ],
    "canary-smoke": [
        "tests/test_graph_phase2_integration.py -q --run-network --run-llm",
    ],
    "canary-sample": [
        "scripts/summarize_reranker_metrics.py",
        "update_reranker_metrics",
    ],
}

REQUIRED_WORKFLOW_FRAGMENTS = [
    "name: Canary Ops Validation",
    "pull_request:",
    "push:",
    "actions/checkout@v4",
    "actions/setup-python@v5",
    "python-version: '3.12'",
    "run: make canary-validate",
]


def _load_tasks(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing tasks file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("tasks.json must be a JSON object")
    return payload


def _task_lookup(tasks_payload: Dict) -> Dict[str, Dict]:
    tasks = tasks_payload.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("tasks.json field 'tasks' must be a list")

    lookup: Dict[str, Dict] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        label = task.get("label")
        if isinstance(label, str):
            lookup[label] = task
    return lookup


def _command_text(task: Dict) -> str:
    parts: List[str] = []
    command = task.get("command")
    if isinstance(command, str):
        parts.append(command)
    args = task.get("args", [])
    if isinstance(args, list):
        for item in args:
            if isinstance(item, str):
                parts.append(item)
    return " ".join(parts)


def _validate_required_tasks(tasks_payload: Dict) -> None:
    lookup = _task_lookup(tasks_payload)

    missing = [label for label in REQUIRED_TASKS if label not in lookup]
    if missing:
        raise ValueError("Missing required canary tasks: " + ", ".join(missing))

    for label, fragments in REQUIRED_TASKS.items():
        task = lookup[label]
        command_text = _command_text(task)
        if not command_text:
            raise ValueError(f"Task has no command content: {label}")

        for fragment in fragments:
            if fragment not in command_text:
                raise ValueError(
                    f"Task '{label}' is missing required fragment: {fragment}"
                )


def _check_summarizer_help(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing summarizer script: {path}")

    result = subprocess.run(
        [sys.executable, str(path), "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "summarize_reranker_metrics.py --help failed with code "
            f"{result.returncode}: {result.stderr.strip()}"
        )

    help_text = result.stdout + "\n" + result.stderr
    for token in ("--input", "--summary-out", "--top-sources"):
        if token not in help_text:
            raise RuntimeError(f"Summarizer help output missing token: {token}")


def _validate_makefile(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing Makefile: {path}")

    text = path.read_text(encoding="utf-8")
    for target, fragments in REQUIRED_MAKE_TARGETS.items():
        target_marker = f"{target}:"
        if target_marker not in text:
            raise ValueError(f"Makefile missing required target: {target}")
        for fragment in fragments:
            if fragment not in text:
                raise ValueError(
                    f"Makefile target '{target}' missing required fragment: {fragment}"
                )


def _validate_workflow(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing workflow file: {path}")

    text = path.read_text(encoding="utf-8")
    for fragment in REQUIRED_WORKFLOW_FRAGMENTS:
        if fragment not in text:
            raise ValueError(f"Workflow missing required fragment: {fragment}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate canary ops task wiring")
    parser.add_argument(
        "--skip-help-check",
        action="store_true",
        help="Skip summarizer --help subprocess validation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    tasks_payload = _load_tasks(TASKS_PATH)
    _validate_required_tasks(tasks_payload)
    _validate_makefile(MAKEFILE_PATH)
    _validate_workflow(WORKFLOW_PATH)

    if not args.skip_help_check:
        _check_summarizer_help(SUMMARIZER_PATH)

    print("Canary ops validation passed")
    print(f"- tasks: {TASKS_PATH}")
    print(f"- makefile: {MAKEFILE_PATH}")
    print(f"- workflow: {WORKFLOW_PATH}")
    print(f"- summarizer: {SUMMARIZER_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
