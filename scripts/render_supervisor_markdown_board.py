#!/usr/bin/env python3
"""Render the canonical JSON supervisor board as daemon-readable markdown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = REPO_ROOT / "docs/task_boards/ipfs_supervisor_task_board.json"
OUTPUT_PATH = REPO_ROOT / "docs/task_boards/ipfs_supervisor_task_board.md"


STATUS_MAP = {
    "complete": "completed",
    "validation_required": "todo",
    "in_progress": "in-progress",
    "planned": "todo",
    "deferred": "blocked",
    "blocked": "blocked",
}


def _csv(values: list[str]) -> str:
    return ", ".join(str(value) for value in values if str(value).strip())


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(normalized)
    return unique_values


def _task_status(task: dict[str, Any]) -> str:
    return STATUS_MAP.get(str(task.get("status") or "planned"), "todo")


def _daemon_task_id(task_id: str) -> str:
    task_id = str(task_id).strip()
    return task_id if task_id.startswith("SUP-") else f"SUP-{task_id}"


def render_board(board: dict[str, Any]) -> str:
    lines = [
        "# IPFS Supervisor Daemon Task Board",
        "",
        "Generated from `docs/task_boards/ipfs_supervisor_task_board.json`.",
        "Edit the JSON board first, then regenerate this markdown projection.",
        "",
    ]

    for task in board.get("tasks", []):
        canonical_task_id = str(task["task_id"])
        task_id = _daemon_task_id(canonical_task_id)
        title = str(task["title"])
        target_files = [str(item) for item in task.get("target_files", [])]
        validation = [str(item) for item in task.get("validation_commands", [])]
        dependencies = [_daemon_task_id(str(item)) for item in task.get("depends_on", [])]
        acceptance = " ".join(str(item).strip() for item in task.get("acceptance_criteria", []) if str(item).strip())
        outputs = target_files[:]
        if task.get("source_doc"):
            outputs.append(str(task["source_doc"]))
        outputs = _unique(outputs)

        lines.extend(
            [
                f"## {task_id} {title}",
                "",
                f"- Status: {_task_status(task)}",
                "- Completion: validation",
                f"- Priority: {task.get('priority', 'P2')}",
                f"- Track: {str(task_id).split('-', 1)[0].lower()}",
                f"- Depends on: {_csv(dependencies)}",
                f"- Outputs: {_csv(outputs)}",
                f"- Validation: {'; '.join(validation)}",
                f"- Acceptance: {acceptance}",
                f"- Source doc: {task.get('source_doc', '')}",
                f"- Canonical task id: {canonical_task_id}",
                f"- Canonical status: {task.get('status', '')}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    OUTPUT_PATH.write_text(render_board(board), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
