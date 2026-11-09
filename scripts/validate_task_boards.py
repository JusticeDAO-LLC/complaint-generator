#!/usr/bin/env python3
"""Validate supervisor task boards and backlog docs.

The checks are intentionally lightweight so they can run in local dev,
CI, or an external ipfs_accelerate_py worker before claiming implementation
tasks from the board.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = REPO_ROOT / "docs/task_boards/ipfs_supervisor_task_board.json"
BOARD_MARKDOWN_PATH = REPO_ROOT / "docs/task_boards/ipfs_supervisor_task_board.md"
PAYLOAD_CONTRACTS = REPO_ROOT / "docs/PAYLOAD_CONTRACTS.md"
DOCS_TO_LINT = [
    REPO_ROOT / "docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md",
    REPO_ROOT / "docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md",
    REPO_ROOT / "docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md",
    REPO_ROOT / "docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md",
    PAYLOAD_CONTRACTS,
    REPO_ROOT / "docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md",
]
VALID_STATUSES = {
    "complete",
    "validation_required",
    "in_progress",
    "planned",
    "deferred",
    "blocked",
}
VALID_PRIORITIES = {"P0", "P1", "P2"}
DAEMON_STATUS_BY_CANONICAL = {
    "complete": "completed",
    "validation_required": "todo",
    "in_progress": "in-progress",
    "planned": "todo",
    "deferred": "blocked",
    "blocked": "blocked",
}
STALE_ABSOLUTE_PREFIX = "/home/barberb/complaint-generator"
TASK_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
FENCED_CODE_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})(?P<info>[^\n]*)\n(?P<body>.*?)(?:\n(?P=fence)[ \t]*$)",
    re.M | re.S,
)
REQUIRED_TASK_FIELDS = (
    "task_id",
    "title",
    "source_doc",
    "status",
    "priority",
    "target_files",
    "acceptance_criteria",
    "validation_commands",
)


@dataclass(frozen=True)
class JsonFence:
    path: Path
    index: int
    start_line: int
    body: str


def _display_path(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return payload


def _line_number(text: str, offset: int) -> int:
    return text[:offset].count("\n") + 1


def _iter_json_fences(path: Path) -> Iterable[JsonFence]:
    text = path.read_text(encoding="utf-8")
    index = 0
    for match in FENCED_CODE_RE.finditer(text):
        info = match.group("info").strip().lower()
        language = info.split()[0] if info else ""
        if language != "json":
            continue
        index += 1
        yield JsonFence(
            path=path,
            index=index,
            start_line=_line_number(text, match.start()),
            body=match.group("body"),
        )


def _validate_json_fences(
    path: Path,
    *,
    repo_root: Path = REPO_ROOT,
    require_json_fence: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{_display_path(path, repo_root)}: document does not exist"]

    fences = list(_iter_json_fences(path))
    if require_json_fence and not fences:
        errors.append(f"{_display_path(path, repo_root)}: expected at least one json fence")

    for fence in fences:
        try:
            json.loads(fence.body)
        except json.JSONDecodeError as exc:
            errors.append(
                f"{_display_path(path, repo_root)}: json fence {fence.index} starting "
                f"at line {fence.start_line} is invalid: {exc}"
            )
    return errors


def _validate_no_stale_absolute_links(
    paths: Iterable[Path],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            errors.append(f"{_display_path(path, repo_root)}: document does not exist")
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if STALE_ABSOLUTE_PREFIX in line:
                errors.append(
                    f"{_display_path(path, repo_root)}:{line_number}: stale absolute link "
                    f"uses {STALE_ABSOLUTE_PREFIX}"
                )
    return errors


def _section_status_conflicts(path: Path, *, repo_root: Path = REPO_ROOT) -> list[str]:
    """Find sections marked planned even though every checklist item is checked."""

    errors: list[str] = []
    if not path.exists():
        return [f"{_display_path(path, repo_root)}: document does not exist"]

    current_heading = ""
    current_status = ""
    checked = 0
    unchecked = 0
    status_line = 0

    def flush() -> None:
        nonlocal checked, unchecked, current_heading, current_status, status_line
        if current_status == "Planned" and checked > 0 and unchecked == 0:
            errors.append(
                f"{_display_path(path, repo_root)}:{status_line}: section "
                f"{current_heading!r} is Planned but all checklist items are checked"
            )

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("## "):
            flush()
            current_heading = line.removeprefix("## ").strip()
            current_status = ""
            checked = 0
            unchecked = 0
            status_line = 0
        elif line.startswith("Status: "):
            current_status = line.removeprefix("Status: ").strip()
            status_line = line_number
        elif line.startswith("- [x] "):
            checked += 1
        elif line.startswith("- [ ] "):
            unchecked += 1
    flush()
    return errors


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _is_repo_relative_path(value: str) -> bool:
    path = Path(value)
    if not value.strip() or path.is_absolute():
        return False
    return ".." not in path.parts


def _validate_non_empty_string_list(
    task_id: str,
    field_name: str,
    value: Any,
    *,
    repo_relative_paths: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, list) or not value:
        return [f"{task_id}: {field_name} must be a non-empty list"]

    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{task_id}: {field_name}[{index}] must be a non-empty string")
            continue
        strings.append(item)
        if repo_relative_paths and not _is_repo_relative_path(item):
            errors.append(f"{task_id}: {field_name}[{index}] must be a repo-relative path: {item}")

    for duplicate in _duplicates(strings):
        errors.append(f"{task_id}: {field_name} contains duplicate entry {duplicate!r}")
    return errors


def _validate_board(board: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    if board.get("schema_version") != "complaint-generator.supervisor_task_board.v1":
        errors.append("task board schema_version must be complaint-generator.supervisor_task_board.v1")

    source_documents = board.get("source_documents")
    if not isinstance(source_documents, list) or not source_documents:
        errors.append("task board must contain a non-empty source_documents array")
        source_documents = []
    else:
        source_document_strings: list[str] = []
        for index, source_doc in enumerate(source_documents):
            if not isinstance(source_doc, str) or not source_doc.strip():
                errors.append(f"source_documents[{index}] must be a non-empty string")
                continue
            source_document_strings.append(source_doc)
            if not _is_repo_relative_path(source_doc):
                errors.append(f"source_documents[{index}] must be repo-relative: {source_doc}")
            elif not (repo_root / source_doc).exists():
                errors.append(f"source_documents[{index}] does not exist: {source_doc}")
        for duplicate in _duplicates(source_document_strings):
            errors.append(f"source_documents contains duplicate entry {duplicate!r}")

    if set(board.get("status_values", [])) != VALID_STATUSES:
        errors.append("task board status_values must match validator status contract")
    if set(board.get("priority_values", [])) != VALID_PRIORITIES:
        errors.append("task board priority_values must match validator priority contract")

    supervisor = board.get("supervisor")
    if not isinstance(supervisor, dict):
        errors.append("task board supervisor must be an object")
        supervisor = {}
    payload_requirements = supervisor.get("task_payload_requirements", [])
    if not isinstance(payload_requirements, list):
        errors.append("supervisor.task_payload_requirements must be a list")
        payload_requirements = []
    missing_requirements = [
        field for field in REQUIRED_TASK_FIELDS if field not in payload_requirements
    ]
    if missing_requirements:
        errors.append(
            "supervisor.task_payload_requirements missing required fields: "
            + ", ".join(missing_requirements)
        )

    tasks = board.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("task board must contain a non-empty tasks array")
        return errors

    task_ids: set[str] = set()
    task_source_docs: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object")
            continue
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"tasks[{index}].task_id is required")
            continue
        if not TASK_ID_RE.match(task_id):
            errors.append(f"{task_id}: task_id must be uppercase hyphen-delimited")
        if task_id in task_ids:
            errors.append(f"duplicate task_id: {task_id}")
        task_ids.add(task_id)

        for required in REQUIRED_TASK_FIELDS:
            if required not in task:
                errors.append(f"{task_id}: missing required field {required}")

        title = task.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{task_id}: title must be a non-empty string")

        status = task.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{task_id}: invalid status {status!r}")
        priority = task.get("priority")
        if priority not in VALID_PRIORITIES:
            errors.append(f"{task_id}: invalid priority {priority!r}")

        source_doc = task.get("source_doc")
        if not isinstance(source_doc, str) or not source_doc.strip():
            errors.append(f"{task_id}: source_doc must be a non-empty string")
        elif not _is_repo_relative_path(source_doc):
            errors.append(f"{task_id}: source_doc must be repo-relative: {source_doc}")
        elif not (repo_root / source_doc).exists():
            errors.append(f"{task_id}: source_doc does not exist: {source_doc}")
        else:
            task_source_docs.add(source_doc)

        errors.extend(
            _validate_non_empty_string_list(
                task_id,
                "target_files",
                task.get("target_files"),
                repo_relative_paths=True,
            )
        )
        errors.extend(
            _validate_non_empty_string_list(
                task_id,
                "acceptance_criteria",
                task.get("acceptance_criteria"),
            )
        )
        errors.extend(
            _validate_non_empty_string_list(
                task_id,
                "validation_commands",
                task.get("validation_commands"),
            )
        )

        depends_on = task.get("depends_on", [])
        if depends_on is None:
            depends_on = []
        if not isinstance(depends_on, list):
            errors.append(f"{task_id}: depends_on must be a list when present")
        else:
            for dep_index, dependency in enumerate(depends_on):
                if not isinstance(dependency, str) or not dependency.strip():
                    errors.append(f"{task_id}: depends_on[{dep_index}] must be a non-empty string")
            for duplicate in _duplicates([dep for dep in depends_on if isinstance(dep, str)]):
                errors.append(f"{task_id}: depends_on contains duplicate entry {duplicate!r}")

    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("task_id", "<unknown>")
        depends_on = task.get("depends_on", [])
        if not isinstance(depends_on, list):
            continue
        for dependency in depends_on:
            if dependency == task_id:
                errors.append(f"{task_id}: task cannot depend on itself")
                continue
            if dependency not in task_ids:
                errors.append(f"{task_id}: unknown dependency {dependency}")

    declared_source_docs = {doc for doc in source_documents if isinstance(doc, str)}
    for source_doc in sorted(task_source_docs - declared_source_docs):
        errors.append(f"task source_doc is not declared in source_documents: {source_doc}")
    return errors


def _validate_markdown_projection(
    board: dict[str, Any],
    markdown_path: Path = BOARD_MARKDOWN_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    if not markdown_path.exists():
        return [f"{_display_path(markdown_path, repo_root)}: markdown task board does not exist"]

    errors: list[str] = []
    text = markdown_path.read_text(encoding="utf-8")
    tasks = board.get("tasks", [])
    if not isinstance(tasks, list):
        return []

    def daemon_task_id(task_id: str) -> str:
        task_id = str(task_id).strip()
        return task_id if task_id.startswith("SUP-") else f"SUP-{task_id}"

    expected_ids = {daemon_task_id(task["task_id"]) for task in tasks
                    if isinstance(task, dict) and isinstance(task.get("task_id"), str)}
    for extra in sorted(set(re.findall(r"^## (SUP-\S+)(?:[ \t]|$)", text, re.M)) - expected_ids):
        errors.append(f"{_display_path(markdown_path, repo_root)}: unexpected markdown task {extra}")

    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("task_id")
        if not isinstance(task_id, str):
            continue
        rendered_task_id = daemon_task_id(task_id)
        sections = list(re.finditer(
            rf"^## {re.escape(rendered_task_id)} [^\n]*\n(?P<body>.*?)(?=^## |\Z)",
            text, re.M | re.S,
        ))
        if len(sections) != 1:
            errors.append(
                f"{_display_path(markdown_path, repo_root)}: expected exactly one "
                f"markdown section for {rendered_task_id}"
            )
        section_text = sections[0].group("body") if len(sections) == 1 else ""
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list):
            dependencies = []
        expected_dependencies = ", ".join(
            daemon_task_id(dependency)
            for dependency in dependencies
            if isinstance(dependency, str) and dependency.strip()
        )
        for field_name, expected in (
            ("Status", DAEMON_STATUS_BY_CANONICAL.get(str(task.get("status", "")), "todo")),
            ("Canonical task id", task_id),
            ("Canonical status", str(task.get("status", ""))),
            ("Source doc", str(task.get("source_doc", ""))),
            ("Depends on", expected_dependencies),
        ):
            line = f"- {field_name}: {expected}"
            field_pattern = re.compile(rf"^\s*-\s*{re.escape(field_name)}\s*:", re.I)
            actual = [value for value in section_text.splitlines() if field_pattern.match(value)]
            if actual != [line]:
                errors.append(
                    f"{_display_path(markdown_path, repo_root)}: missing line {line!r} "
                    f"for {rendered_task_id}"
                )

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("- Outputs: "):
            continue
        outputs = [
            item.strip()
            for item in line.removeprefix("- Outputs: ").split(",")
            if item.strip()
        ]
        for duplicate in _duplicates(outputs):
            errors.append(
                f"{_display_path(markdown_path, repo_root)}:{line_number}: "
                f"Outputs contains duplicate entry {duplicate!r}"
            )
    return errors


def _docs_for_json_fence_validation(
    board: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    payload_contracts_path: Path = PAYLOAD_CONTRACTS,
    board_markdown_path: Path = BOARD_MARKDOWN_PATH,
) -> list[Path]:
    docs: list[Path] = [payload_contracts_path, board_markdown_path]
    source_documents = board.get("source_documents", [])
    if isinstance(source_documents, list):
        docs.extend(repo_root / item for item in source_documents if isinstance(item, str))
    return list(dict.fromkeys(docs))


def validate(
    *,
    board_path: Path = BOARD_PATH,
    board_markdown_path: Path = BOARD_MARKDOWN_PATH,
    payload_contracts_path: Path = PAYLOAD_CONTRACTS,
    docs_to_lint: Sequence[Path] | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    errors: list[str] = []
    try:
        board = _load_json(board_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"{_display_path(board_path, repo_root)}: invalid board JSON: {exc}"]

    errors.extend(_validate_board(board, repo_root=repo_root))
    errors.extend(
        _validate_markdown_projection(
            board,
            markdown_path=board_markdown_path,
            repo_root=repo_root,
        )
    )

    docs_with_payload_examples = _docs_for_json_fence_validation(
        board,
        repo_root=repo_root,
        payload_contracts_path=payload_contracts_path,
        board_markdown_path=board_markdown_path,
    )
    for path in docs_with_payload_examples:
        errors.extend(
            _validate_json_fences(
                path,
                repo_root=repo_root,
                require_json_fence=path == payload_contracts_path,
            )
        )

    lint_paths = list(docs_to_lint) if docs_to_lint is not None else DOCS_TO_LINT
    lint_paths = list(dict.fromkeys([*lint_paths, *docs_with_payload_examples]))
    errors.extend(_validate_no_stale_absolute_links(lint_paths, repo_root=repo_root))
    for path in lint_paths:
        errors.extend(_section_status_conflicts(path, repo_root=repo_root))

    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--board",
        type=Path,
        default=BOARD_PATH,
        help="Path to the supervisor task-board JSON file.",
    )
    parser.add_argument(
        "--payload-contracts",
        type=Path,
        default=PAYLOAD_CONTRACTS,
        help="Path to the payload contract markdown file.",
    )
    parser.add_argument(
        "--markdown-board",
        type=Path,
        default=BOARD_MARKDOWN_PATH,
        help="Path to the rendered supervisor task-board markdown file.",
    )
    return parser


def main(argv: Sequence[str] | None = ()) -> int:
    args = _build_parser().parse_args(list(argv or []))
    errors = validate(
        board_path=args.board,
        board_markdown_path=args.markdown_board,
        payload_contracts_path=args.payload_contracts,
    )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    board = _load_json(args.board)
    print(
        f"Validated {_display_path(args.board)} with "
        f"{len(board.get('tasks', []))} tasks and {len(DOCS_TO_LINT)} source docs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
