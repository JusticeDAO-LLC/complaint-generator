import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


# This module exercises mocked supervisor orchestration only. Its references to
# the vendored accelerate package are paths, not heavy runtime dependencies.
pytestmark = pytest.mark.no_auto_heavy


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "refactor_agent_supervisor.py"
SPEC = importlib.util.spec_from_file_location("complaint_generator_refactor_agent_supervisor", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
supervisor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = supervisor
SPEC.loader.exec_module(supervisor)

ROUTER_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "llm_router_merge_resolver.py"
ROUTER_SPEC = importlib.util.spec_from_file_location("complaint_generator_llm_router_merge_resolver", ROUTER_SCRIPT_PATH)
assert ROUTER_SPEC is not None and ROUTER_SPEC.loader is not None
router_resolver = importlib.util.module_from_spec(ROUTER_SPEC)
sys.modules[ROUTER_SPEC.name] = router_resolver
ROUTER_SPEC.loader.exec_module(router_resolver)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def test_renderers_use_supervisor_validation_command_delimiter() -> None:
    task = supervisor.RefactorTask(
        goal_id="G9",
        subgoal_id="G9.S1",
        title="Validate command rendering",
        priority="P0",
        files=("scripts/refactor_agent_supervisor.py",),
        rationale="Keep generated validation commands independently executable.",
        acceptance=("Both commands remain distinct.",),
        validation=(
            "python -m pytest tests/test_first.py -q",
            "python -m pytest tests/test_second.py -q",
        ),
    )
    goals = [
        {
            "id": "G9",
            "title": "Supervisor throughput",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G9.S1",
                    "title": "Validation routing",
                    "tasks": [task],
                }
            ],
        }
    ]
    expected = (
        "- Validation: python -m pytest tests/test_first.py -q; "
        "python -m pytest tests/test_second.py -q"
    )

    assert expected in supervisor._render_objective_heap(goals)
    assert expected in supervisor._task_block(task, "REF-900", 900)


def test_synchronize_explicit_task_blocks_preserves_status_and_refreshes_contract(
    tmp_path,
) -> None:
    old_task = supervisor.RefactorTask(
        goal_id="G12",
        subgoal_id="G12.S2",
        title="Refresh an existing task",
        priority="P1",
        files=("old.py",),
        rationale="Old rationale.",
        acceptance=("Old acceptance.",),
        validation=("python -m pytest old_test.py -q",),
        task_id="REF-279",
        depends_on=("REF-246",),
    )
    new_task = supervisor.RefactorTask(
        goal_id="G12",
        subgoal_id="G12.S2",
        title="Refresh an existing task",
        priority="P0",
        files=("new.py",),
        rationale="New rationale.",
        acceptance=("New acceptance.",),
        validation=("python -m pytest new_test.py -q",),
        task_id="REF-279",
        depends_on=("REF-275",),
    )
    board = tmp_path / "todo.md"
    existing = supervisor._task_block(old_task, "REF-279", 279)
    existing = existing.replace("- [ ] Task", "- [x] Task", 1)
    existing = existing.replace("- Status: todo", "- Status: completed", 1)
    board.write_text("# Board\n\n" + existing + "\n", encoding="utf-8")

    assert supervisor._synchronize_explicit_task_blocks(board, [new_task])
    refreshed = board.read_text(encoding="utf-8")

    assert "- [x] Task checkbox-279: REF-279 Refresh an existing task" in refreshed
    assert "- Status: completed" in refreshed
    assert "- Priority: P0" in refreshed
    assert "- Depends on: REF-275" in refreshed
    assert "- Outputs: new.py" in refreshed
    assert "- Validation: python -m pytest new_test.py -q" in refreshed
    assert "Old rationale." not in refreshed
    assert "old.py" not in refreshed
    assert not supervisor._synchronize_explicit_task_blocks(board, [new_task])


def test_refactor_task_payload_has_actionable_schema_fields() -> None:
    task = supervisor.RefactorTask(
        goal_id="G8",
        subgoal_id="G8.S2",
        title="Verify the seed contract",
        priority="P1",
        files=("scripts/refactor_agent_supervisor.py",),
        rationale="Agents need complete work instructions.",
        acceptance=("The payload is complete.",),
        validation=("python -m pytest tests/test_refactor_agent_supervisor.py -q",),
        task_id="REF-026",
    )

    payload = task.payload()

    assert payload["schema"] == supervisor.TASK_PAYLOAD_SCHEMA
    assert payload["goal_id"] == "G8"
    assert payload["subgoal_id"] == "G8.S2"
    assert payload["priority"] == "P1"
    assert payload["acceptance"] == ["The payload is complete."]
    assert payload["validation"] == [
        "python -m pytest tests/test_refactor_agent_supervisor.py -q"
    ]


def test_refactor_task_payload_rejects_missing_acceptance_or_validation() -> None:
    task = supervisor.RefactorTask(
        goal_id="G8",
        subgoal_id="G8.S2",
        title="Malformed task",
        priority="P1",
        files=(),
        rationale="Malformed work must not reach the queue.",
        acceptance=(),
        validation=(),
    )

    with pytest.raises(ValueError, match="acceptance must be a non-empty list"):
        task.payload()


def test_queue_refill_maintains_work_item_floor_without_duplicate_active_bundles(
    tmp_path, monkeypatch
) -> None:
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()
    (bundle_dir / "index.json").write_text("{}\n", encoding="utf-8")
    todo_path = tmp_path / "todo.md"
    todo_path.write_text(
        "\n".join(
            [
                "- [ ] Task checkbox-1: REF-001 First task",
                "- [ ] Task checkbox-2: REF-002 Second task",
                "- [ ] Task checkbox-3: REF-003 Third task",
                "- [x] Task checkbox-4: REF-004 Completed task",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", bundle_dir)
    monkeypatch.setattr(supervisor, "TODO_PATH", todo_path)
    monkeypatch.setattr(supervisor, "QUEUE_PATH", tmp_path / "queue.duckdb")

    def task(task_id: str, priority: str = "P0") -> dict[str, object]:
        return {
            "task_id": task_id,
            "title": f"Title {task_id}",
            "priority": priority,
            "goal_id": "G1",
            "subgoal_id": "G1.S1",
            "acceptance": [f"Accept {task_id}"],
            "validation": [f"validate {task_id}"],
            "paths": [f"{task_id}.py"],
        }

    payloads = [
        {"bundle_key": "refactor/g1/g1-s1", "tasks": [task("REF-001"), task("REF-002")]},
        {"bundle_key": "refactor/g1/g1-s2", "tasks": [task("REF-003", "P1"), task("REF-004")]},
    ]
    monkeypatch.setattr(supervisor, "_upstream_bundle_payload_builder", lambda: lambda _path: payloads)

    class FakeQueue:
        items: list[dict[str, object]] = []

        def __init__(self, _path: str):
            pass

        def list(self, *, status, limit, task_types):
            return [item for item in self.items if item["status"] == status][:limit]

        def submit(self, *, task_type, model_name, payload):
            task_id = f"queue-{len(self.items) + 1}"
            self.items.append(
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "model_name": model_name,
                    "payload": payload,
                    "status": "queued",
                }
            )
            return task_id

        def close(self):
            pass

    monkeypatch.setattr(supervisor, "_task_queue_class", lambda: FakeQueue)

    first = supervisor.refill_bundle_queue(refill_floor=3)
    second = supervisor.refill_bundle_queue(refill_floor=3)

    assert first["floor_satisfied"] is True
    assert first["queued_work_items_after"] == 3
    assert first["submitted_bundle_count"] == 2
    assert second["submitted_bundle_count"] == 0
    assert second["queued_work_items_before"] == 3
    assert len(FakeQueue.items) == 2
    queued_payload = FakeQueue.items[0]["payload"]
    assert queued_payload["schema"] == "complaint_generator.refactor_supervisor.bundle_task.v1"
    assert queued_payload["goal_id"] == "G1"
    assert queued_payload["subgoal_id"] == "G1.S1"
    assert queued_payload["priority"] == "P0"
    assert queued_payload["acceptance"]
    assert queued_payload["validation"]


def test_queue_refill_rejects_malformed_payload_without_submitting_it(tmp_path, monkeypatch) -> None:
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()
    (bundle_dir / "index.json").write_text("{}\n", encoding="utf-8")
    todo_path = tmp_path / "todo.md"
    todo_path.write_text("## REF-001 Incomplete task\n\n- Status: todo\n", encoding="utf-8")
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", bundle_dir)
    monkeypatch.setattr(supervisor, "TODO_PATH", todo_path)
    monkeypatch.setattr(supervisor, "QUEUE_PATH", tmp_path / "queue.duckdb")
    monkeypatch.setattr(
        supervisor,
        "_upstream_bundle_payload_builder",
        lambda: lambda _path: [
            {
                "bundle_key": "refactor/g8/g8-s2",
                "tasks": [
                    {
                        "task_id": "REF-001",
                        "title": "Incomplete task",
                        "priority": "P1",
                        "parent_goal_id": "G8",
                        "subgoal_id": "G8.S2",
                        "acceptance": [],
                        "validation": ["python -m pytest -q"],
                    }
                ],
            }
        ],
    )

    class FakeQueue:
        submitted: list[dict[str, object]] = []

        def __init__(self, _path: str):
            pass

        def list(self, **_kwargs):
            return []

        def submit(self, **kwargs):
            self.submitted.append(kwargs)
            return "queue-1"

        def close(self):
            pass

    monkeypatch.setattr(supervisor, "_task_queue_class", lambda: FakeQueue)

    result = supervisor.refill_bundle_queue(refill_floor=1)

    assert result["submitted_bundle_count"] == 0
    assert result["rejected_bundle_count"] == 1
    assert result["rejected_payloads"][0]["bundle_key"] == "refactor/g8/g8-s2"
    assert "acceptance must be a non-empty list" in result["rejected_payloads"][0]["error"]
    assert FakeQueue.submitted == []


def test_seed_taskboard_twice_keeps_one_active_copy_and_complete_queue_payloads(
    tmp_path, monkeypatch
) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "OBJECTIVE_PATH", tmp_path / "objective.md")
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "TASKBOARD_DOC_PATH", tmp_path / "taskboard.md")

    tasks = [
        supervisor.RefactorTask(
            goal_id="G8",
            subgoal_id="G8.S2",
            title="First seed task",
            priority="P1",
            files=("first.py",),
            rationale="Exercise repeat seeding.",
            acceptance=("First task is represented once.",),
            validation=("python -m py_compile first.py",),
            task_id="REF-101",
        ),
        supervisor.RefactorTask(
            goal_id="G8",
            subgoal_id="G8.S2",
            title="Second seed task",
            priority="P2",
            files=("second.py",),
            rationale="Exercise bundled repeat seeding.",
            acceptance=("Second task is represented once.",),
            validation=("python -m py_compile second.py",),
            task_id="REF-102",
        ),
    ]
    goals = [
        {
            "id": "G8",
            "title": "Reviewable artifacts",
            "priority": "P1",
            "subgoals": [
                {"id": "G8.S2", "title": "Stable seeds", "tasks": tasks},
            ],
        }
    ]
    monkeypatch.setattr(supervisor, "scan_codebase", lambda: {"signals": {}})
    monkeypatch.setattr(supervisor, "build_goals", lambda _scan: goals)
    monkeypatch.setattr(supervisor, "_durable_task_statuses", lambda: {})
    monkeypatch.setattr(
        supervisor,
        "synchronize_taskboard_statuses",
        lambda: {
            "task_count": 2,
            "completed_count": 0,
            "blocked_count": 0,
            "updated_file_count": 0,
            "updated": {},
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_collect_counts",
        lambda: (
            {
                "todo": {"needed": 2, "in_progress": 0, "complete": 0, "blocked": 0},
                "queue": {"queued": 1, "running": 0, "completed": 0, "failed": 0},
            },
            {},
        ),
    )
    monkeypatch.setattr(supervisor, "_write_taskboard_doc", lambda *_args, **_kwargs: None)

    def build_payloads(index_path: Path) -> list[dict[str, object]]:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        return [
            {"bundle_key": key, "tasks": info["tasks"]}
            for key, info in index["bundles"].items()
        ]

    monkeypatch.setattr(supervisor, "_upstream_bundle_payload_builder", lambda: build_payloads)

    class FakeQueue:
        items: list[dict[str, object]] = []

        def __init__(self, _path: str):
            pass

        def list(self, *, status, limit, task_types):
            return [item for item in self.items if item["status"] == status][:limit]

        def count(self, *, status, task_types):
            return len([item for item in self.items if item["status"] == status])

        def submit(self, *, task_type, model_name, payload):
            queue_id = f"queue-{len(self.items) + 1}"
            self.items.append(
                {
                    "task_id": queue_id,
                    "task_type": task_type,
                    "model_name": model_name,
                    "payload": payload,
                    "status": "queued",
                }
            )
            return queue_id

        def close(self):
            pass

    monkeypatch.setattr(supervisor, "_task_queue_class", lambda: FakeQueue)

    first = supervisor.seed_taskboard(refill_floor=2)
    second = supervisor.seed_taskboard(refill_floor=2)

    todo_text = supervisor.TODO_PATH.read_text(encoding="utf-8")
    shard_text = (supervisor.BUNDLE_DIR / "refactor-g8-g8-s2.todo.md").read_text(
        encoding="utf-8"
    )
    assert todo_text.count("## REF-101 First seed task") == 1
    assert todo_text.count("## REF-102 Second seed task") == 1
    assert shard_text.count("## REF-101 First seed task") == 1
    assert shard_text.count("## REF-102 Second seed task") == 1
    assert first["queue_refill"]["submitted_bundle_count"] == 1
    assert second["queue_refill"]["submitted_bundle_count"] == 0
    assert len(FakeQueue.items) == 1

    payload = FakeQueue.items[0]["payload"]
    assert payload["schema"] == supervisor.BUNDLE_TASK_PAYLOAD_SCHEMA
    assert payload["goal_id"] == "G8"
    assert payload["subgoal_id"] == "G8.S2"
    assert payload["priority"] == "P1"
    assert payload["acceptance"] == [
        "First task is represented once.",
        "Second task is represented once.",
    ]
    assert payload["validation"] == [
        "python -m py_compile first.py",
        "python -m py_compile second.py",
    ]


def test_goal_json_projects_header_statuses_and_resolves_seed_task_ids(tmp_path, monkeypatch) -> None:
    todo_path = tmp_path / "todo.md"
    todo_path.write_text(
        "\n".join(
            [
                "## REF-001 Seed task",
                "",
                "- Status: completed",
                "",
                "## REF-027 Generated task",
                "",
                "- Status: todo",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "TODO_PATH", todo_path)
    monkeypatch.setattr(supervisor, "OBJECTIVE_PATH", tmp_path / "objective.md")
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "QUEUE_PATH", tmp_path / "queue.duckdb")
    seed_task = supervisor.RefactorTask(
        goal_id="G1",
        subgoal_id="G1.S1",
        title="Seed task",
        priority="P0",
        files=("seed.py",),
        rationale="Keep projections synchronized.",
        acceptance=("Status is visible.",),
        validation=("python -m py_compile seed.py",),
    )
    goals = [
        {
            "id": "G1",
            "title": "Goal",
            "priority": "P0",
            "subgoals": [{"id": "G1.S1", "title": "Subgoal", "tasks": [seed_task]}],
        }
    ]

    taskboard = supervisor._taskboard_snapshot()
    payload = supervisor._json_goal_tree(goals, {}, taskboard=taskboard)
    projected = payload["goals"][0]["subgoals"][0]["tasks"][0]

    assert taskboard["task_count"] == 2
    assert taskboard["tasks"][1]["task_id"] == "REF-027"
    assert projected["task_id"] == "REF-001"
    assert projected["status"] == "complete"


def test_seed_goal_tree_preserves_follow_on_planning_extensions() -> None:
    generated = {
        "generated_at": "new",
        "goals": [{"id": "G1"}],
        "scan": {"python_file_count": 1},
    }
    existing = {
        "generated_at": "old",
        "goals": [{"id": "stale"}],
        "implementation_claims": [{"id": "CLAIM-001"}],
    }

    merged = supervisor._merge_goal_tree_extensions(generated, existing)

    assert merged["generated_at"] == "new"
    assert merged["goals"] == [{"id": "G1"}]
    assert merged["implementation_claims"] == [{"id": "CLAIM-001"}]


def test_taskboard_projects_canonical_ipfs_p0_cross_links(tmp_path, monkeypatch) -> None:
    backlog = tmp_path / "ipfs-backlog.md"
    taskboard = tmp_path / "taskboard.md"
    backlog.write_text(
        "# Backlog\n\n"
        "| ID | Workstream | Status | Priority | Outcome |\n"
        "|---|---|---|---|---|\n"
        "| W1 | Adapter | In Progress | P0 | Stable contracts |\n\n"
        f"{supervisor.IPFS_P0_CROSS_LINKS_START}\n"
        "## P0 Refactor Supervisor Cross-Links\n\n"
        "| IPFS workstream | Refactor goal(s) | Package coverage | Merge and scope rule |\n"
        "|---|---|---|---|\n"
        "| W1 | G3.S1 | W1.1 | Merge matching claims. |\n"
        f"{supervisor.IPFS_P0_CROSS_LINKS_END}\n\n"
        "## Workstream details\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "IPFS_EXECUTION_BACKLOG_PATH", backlog)
    monkeypatch.setattr(supervisor, "TASKBOARD_DOC_PATH", taskboard)
    scan = {
        "python_file_count": 1,
        "python_total_lines": 2,
        "test_file_count": 3,
        "signals": {
            "direct_ipfs_import_count": 0,
            "sys_path_mutation_count": 0,
            "broad_exception_count": 0,
        },
    }

    goals = [
        {
            "id": "G3",
            "subgoals": [{"id": "G3.S1", "title": "Contracts", "tasks": []}],
            "title": "Adapters",
            "priority": "P0",
        }
    ]
    supervisor._write_taskboard_doc(
        goals,
        scan,
        {},
        {},
        {},
        queue_refill={},
        taskboard={},
    )

    rendered = taskboard.read_text(encoding="utf-8")
    assert rendered.count("## P0 Refactor Supervisor Cross-Links") == 1
    assert "| W1 | G3.S1 | W1.1 | Merge matching claims. |" in rendered
    assert rendered.index("## P0 Refactor Supervisor Cross-Links") < rendered.index("## Goals")


def test_ipfs_p0_cross_link_markers_must_be_unique(tmp_path) -> None:
    backlog = tmp_path / "ipfs-backlog.md"
    backlog.write_text(
        "# Backlog\n\n"
        f"{supervisor.IPFS_P0_CROSS_LINKS_START}\n"
        "mapping\n",
        encoding="utf-8",
    )

    try:
        supervisor._read_ipfs_p0_cross_links(backlog)
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("malformed mapping markers should fail taskboard generation")


def test_repository_ipfs_p0_cross_links_cover_the_overview_and_known_goals() -> None:
    section = supervisor._read_ipfs_p0_cross_links()
    goals = supervisor.build_goals({"signals": {}})

    supervisor._validate_ipfs_p0_cross_link_goals(section, goals)

    rows = [line for line in section if re.match(r"^\| W\d+\b", line)]
    assert [re.match(r"^\| (W\d+)\b", line).group(1) for line in rows] == [
        "W1",
        "W2",
        "W3",
        "W4",
        "W9",
        "W10",
    ]
    assert all("Merge and scope rule" not in row and row.count("|") >= 5 for row in rows)


def test_goal_management_integrity_program_is_persistent_and_dependency_closed() -> None:
    goals = supervisor.build_goals({"signals": {}})
    goal = next(goal for goal in goals if goal["id"] == "G10")
    tasks = supervisor.flatten_tasks([goal])

    assert [subgoal["id"] for subgoal in goal["subgoals"]] == [
        "G10.S1",
        "G10.S2",
        "G10.S3",
        "G10.S4",
    ]
    assert [task.task_id for task in tasks] == [f"REF-{number}" for number in range(200, 213)]
    task_ids = {task.task_id for task in tasks}
    assert all(set(task.depends_on) <= task_ids for task in tasks)
    assert all(
        any(path.startswith("ipfs_datasets_py/ipfs_accelerate_py/") for path in task.files)
        for task in tasks
    )
    assert any("terminal reason taxonomy" in task.title for task in tasks)
    assert any("fingerprint-independent audit" in task.title for task in tasks)
    assert any("automatically reopen" in task.title for task in tasks)


def test_formal_verification_program_is_persistent_parallel_and_dependency_closed() -> None:
    goals = supervisor.build_goals({"signals": {}})
    goal = next(goal for goal in goals if goal["id"] == "G11")
    tasks = supervisor.flatten_tasks([goal])

    assert [subgoal["id"] for subgoal in goal["subgoals"]] == [
        "G11.S1",
        "G11.S2",
        "G11.S3",
        "G11.S4",
        "G11.S5",
        "G11.S6",
        "G11.S7",
        "G11.S8",
    ]
    assert [task.task_id for task in tasks] == [
        f"REF-{number}" for number in range(244, 275)
    ]
    task_ids = {task.task_id for task in tasks}
    assert all(set(task.depends_on) <= task_ids for task in tasks)
    assert all(
        any(path.startswith("ipfs_datasets_py/ipfs_accelerate_py/") for path in task.files)
        for task in tasks
    )
    assert sum(not task.depends_on for task in tasks) >= 2
    assert any("Hammer portfolio" in task.title for task in tasks)
    assert any("Leanstral" in task.title for task in tasks)
    assert any("ZKP" in task.title for task in tasks)
    assert any("DuckDB" in criterion for task in tasks for criterion in task.acceptance)
    assert any("shared resource" in criterion for task in tasks for criterion in task.acceptance)


def test_formal_planning_prover_matrix_program_is_additive_and_dependency_closed() -> None:
    goals = supervisor.build_goals({"signals": {}})
    goal = next(goal for goal in goals if goal["id"] == "G12")
    tasks = supervisor.flatten_tasks([goal])
    all_task_ids = {task.task_id for task in supervisor.flatten_tasks(goals)}

    assert [subgoal["id"] for subgoal in goal["subgoals"]] == [
        "G12.S1",
        "G12.S2",
        "G12.S3",
        "G12.S4",
        "G12.S5",
    ]
    assert [task.task_id for task in tasks] == [
        f"REF-{number}" for number in range(275, 295)
    ]
    assert all(set(task.depends_on) <= all_task_ids for task in tasks)
    assert all(
        any(path.startswith("ipfs_datasets_py/ipfs_accelerate_py/") for path in task.files)
        for task in tasks
    )
    declared_paths = [path for task in tasks for path in task.files]
    assert len(declared_paths) == len(set(declared_paths))
    g11_paths = {
        path
        for task in supervisor.flatten_tasks(
            [next(item for item in goals if item["id"] == "G11")]
        )
        for path in task.files
    }
    assert not g11_paths.intersection(declared_paths)

    g12_task_ids = {task.task_id for task in tasks}
    remaining = {
        task.task_id: {item for item in task.depends_on if item in g12_task_ids}
        for task in tasks
    }
    completed: set[str] = set()
    while remaining:
        ready = sorted(
            task_id
            for task_id, dependencies in remaining.items()
            if dependencies <= completed
        )
        assert ready, f"cycle in G12 task dependencies: {remaining}"
        for task_id in ready:
            completed.add(task_id)
            remaining.pop(task_id)

    task_by_id = {
        task.task_id: task
        for task in supervisor.flatten_tasks(goals)
        if task.task_id
    }

    def prerequisite_closure(task_ids: set[str]) -> set[str]:
        closure: set[str] = set()
        pending = list(task_ids)
        while pending:
            task_id = pending.pop()
            if task_id in closure:
                continue
            closure.add(task_id)
            dependency = task_by_id.get(task_id)
            if dependency is not None:
                pending.extend(dependency.depends_on)
        return closure

    for task in tasks:
        for direct_dependency in task.depends_on:
            inherited = prerequisite_closure(
                set(task.depends_on) - {direct_dependency}
            )
            assert direct_dependency not in inherited, (
                f"{task.task_id} redundantly declares transitive dependency "
                f"{direct_dependency}"
            )

    assert {"REF-275", "REF-279"} <= g12_task_ids
    assert any("DCEC" in criterion for task in tasks for criterion in task.acceptance)
    assert any("TDFOL" in criterion for task in tasks for criterion in task.acceptance)
    assert any(
        "frame-logic" in criterion and "evidence-graph" in criterion
        for task in tasks
        for criterion in task.acceptance
    )
    assert any("TLA+" in task.title for task in tasks)
    assert any("Datalog" in task.title and "SecPAL" in task.title for task in tasks)
    assert any("Tamarin" in task.title and "ProVerif" in task.title for task in tasks)
    assert any("hyperproperties" in task.title for task in tasks)
    assert any("runtime MTL" in task.title for task in tasks)
    assert any("Codex" in task.title and "Leanstral" in task.title for task in tasks)
    assert any("JSON and DuckDB" in criterion for task in tasks for criterion in task.acceptance)
    assert any("shared CPU" in task.title for task in tasks)
    assert any(
        "ready-member slices" in criterion and "dependency enforcement" in criterion
        for task in tasks
        for criterion in task.acceptance
    )


def test_merge_watchdog_skips_aborted_historical_merge(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        json.dumps(
            {
                "type": "merge_reconciled",
                "task_id": "REF-901",
                "resolved": False,
                "merge_result": {
                    "attempted": True,
                    "merged": False,
                    "branch": "implementation/ref-901",
                    "target_branch": "main",
                    "reason": "content_conflict",
                    "main_worktree_path": str(repo),
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", repo)
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_REGISTRY_DIR", tmp_path / "registry")
    monkeypatch.setattr(supervisor, "merge_event_paths", lambda: [events_path])
    monkeypatch.setattr(
        supervisor,
        "_implementation_activity_snapshot",
        lambda: {
            "active": False,
            "active_task_id": "",
            "active_phase": "",
            "parallel_running_count": 0,
        },
    )
    monkeypatch.setattr(supervisor, "_taskboard_status_by_id", lambda: {})

    result = supervisor.resolve_merge_conflicts_once(timeout_seconds=1)

    assert result["attempted_count"] == 0
    assert result["applied_count"] == 0
    assert result["results"][0]["skip_reason"] == "merge_not_active"


def test_merge_watchdog_does_not_scan_while_implementation_is_active(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(
        supervisor,
        "_implementation_activity_snapshot",
        lambda: {
            "active": True,
            "active_task_id": "REF-902",
            "active_phase": "merge_resolver",
            "parallel_running_count": 0,
        },
    )
    monkeypatch.setattr(
        supervisor,
        "merge_event_paths",
        lambda: pytest.fail("active implementations must short-circuit event scanning"),
    )

    result = supervisor.resolve_merge_conflicts_once(timeout_seconds=1)

    assert result["attempted_count"] == 0
    assert result["results"][0]["skip_reason"] == "implementation_active"
    assert result["results"][0]["active_task_id"] == "REF-902"


def test_merge_watchdog_ignores_completed_task_failure_from_another_log(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        json.dumps(
            {
                "type": "merge_finished",
                "task_id": "REF-903",
                "attempted": True,
                "merged": False,
                "branch": "implementation/ref-903",
                "target_branch": "main",
                "reason": "content_conflict",
                "main_worktree_path": str(repo),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", repo)
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_REGISTRY_DIR", tmp_path / "registry")
    monkeypatch.setattr(supervisor, "merge_event_paths", lambda: [events_path])
    monkeypatch.setattr(
        supervisor,
        "_implementation_activity_snapshot",
        lambda: {
            "active": False,
            "active_task_id": "",
            "active_phase": "",
            "parallel_running_count": 0,
        },
    )
    monkeypatch.setattr(supervisor, "_taskboard_status_by_id", lambda: {"REF-903": "complete"})

    result = supervisor.resolve_merge_conflicts_once(timeout_seconds=1)

    assert result["attempted_count"] == 0
    assert result["results"][0]["skip_reason"] == "task_already_completed"


def test_merge_watchdog_checkout_lock_is_exclusive(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", repo)

    first = supervisor._try_acquire_watchdog_checkout_lock(
        task_id="REF-904",
        branch="implementation/ref-904",
    )
    second = supervisor._try_acquire_watchdog_checkout_lock(
        task_id="REF-905",
        branch="implementation/ref-905",
    )

    assert first["acquired"] is True
    assert second["acquired"] is False
    assert second["reason"] == "checkout_mutation_lock_active"
    supervisor._release_watchdog_checkout_lock(first)
    assert not Path(first["lock_path"]).exists()


def test_router_commit_preserves_unrelated_dirty_paths(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    _git(repo, "config", "user.email", "agent@example.com")
    _git(repo, "config", "user.name", "Agent")
    intended = repo / "intended.txt"
    unrelated = repo / "unrelated.txt"
    intended.write_text("before\n", encoding="utf-8")
    unrelated.write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    intended.write_text("after\n", encoding="utf-8")
    unrelated.write_text("user change\n", encoding="utf-8")

    assert router_resolver._stage_and_commit_if_resolved(
        repo,
        paths_to_stage=["intended.txt"],
    )

    assert _git(repo, "show", "HEAD:intended.txt").stdout == "after\n"
    assert _git(repo, "show", "HEAD:unrelated.txt").stdout == "before\n"
    assert _git(repo, "status", "--short").stdout == " M unrelated.txt\n"
    assert not router_resolver._stage_and_commit_if_resolved(repo, paths_to_stage=[])


def test_router_does_not_commit_invalid_python_resolution(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    _git(repo, "config", "user.email", "agent@example.com")
    _git(repo, "config", "user.name", "Agent")
    target = repo / "resolver_target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", "resolver_target.py")
    _git(repo, "commit", "-m", "baseline")
    baseline = _git(repo, "rev-parse", "HEAD").stdout.strip()
    target.write_text("def broken(\n", encoding="utf-8")

    committed = router_resolver._stage_and_commit_if_resolved(
        repo,
        paths_to_stage=["resolver_target.py"],
    )

    assert committed is False
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == baseline
    assert _git(repo, "status", "--short").stdout == " M resolver_target.py\n"


def test_router_validation_expands_nested_repository_changes(tmp_path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    _git(nested, "init")
    _git(nested, "config", "user.email", "agent@example.com")
    _git(nested, "config", "user.name", "Agent")
    (nested / "broken.py").write_text("def broken(\n", encoding="utf-8")
    _git(nested, "add", "broken.py")
    _git(nested, "commit", "-m", "invalid resolution")

    validation = router_resolver._validate_resolution_paths(tmp_path, ["nested"])

    assert validation["valid"] is False
    assert validation["expanded_paths"] == ["nested/broken.py"]
    assert validation["syntax_errors"][0]["path"] == "nested/broken.py"


def test_merge_watchdog_has_explicit_stop_command() -> None:
    assert supervisor.build_parser().parse_args(["stop-merge-watchdog"]).command == "stop-merge-watchdog"


def test_merge_watchdog_stop_terminates_owned_process_group(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "watchdog.pid"
    pid_path.write_text("4321\n", encoding="utf-8")
    alive = iter([True, False, False])
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_PID_PATH", pid_path)
    monkeypatch.setattr(supervisor, "_pid_alive", lambda _pid: next(alive))
    monkeypatch.setattr(supervisor.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(supervisor.os, "killpg", lambda pgid, sig: signals.append((pgid, sig)))
    monkeypatch.setattr(supervisor.time, "sleep", lambda _seconds: None)

    result = supervisor.stop_merge_resolver_watchdog()

    assert result["status"] == "stopped"
    assert result["signal_scope"] == "process_group"
    assert signals == [(4321, supervisor.signal.SIGTERM)]
    assert not pid_path.exists()


def _isolate_status_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(supervisor, "PID_PATH", tmp_path / "supervisor.pid")
    monkeypatch.setattr(supervisor, "TASK_STATE_PATH", tmp_path / "task-state.json")
    monkeypatch.setattr(supervisor, "MANAGED_DAEMON_PID_PATH", tmp_path / "managed-daemon.pid")
    monkeypatch.setattr(supervisor, "GOALS_PATH", tmp_path / "goals.json")
    monkeypatch.setattr(supervisor, "TODO_PATH", tmp_path / "todo.md")
    monkeypatch.setattr(supervisor, "QUEUE_PATH", tmp_path / "queue.duckdb")
    monkeypatch.setattr(supervisor, "BUNDLE_LANE_MANIFEST", tmp_path / "lanes.json")
    monkeypatch.setattr(supervisor, "BUNDLE_LANE_ROOT", tmp_path / "bundle-lanes")
    monkeypatch.setattr(supervisor, "BUNDLE_SCHEDULER_PID_PATH", tmp_path / "bundle-scheduler.pid")
    monkeypatch.setattr(supervisor, "BUNDLE_SCHEDULER_LOG_PATH", tmp_path / "bundle-scheduler.log")
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_STATUS_PATH", tmp_path / "merge-status.json")
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_PID_PATH", tmp_path / "merge.pid")
    monkeypatch.setattr(supervisor, "UPSTREAM_SUPERVISOR_STATUS_PATH", tmp_path / "upstream-status.json")


def test_status_snapshot_has_stable_handoff_metrics(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    counts = {
        "todo": {"needed": 7, "in_progress": 2, "complete": 11, "blocked": 1},
        "queue": {"queued": 5, "running": 1, "completed": 9, "failed": 2},
    }
    monkeypatch.setattr(supervisor, "_collect_counts", lambda: (counts, {}))
    scan_summary = {
        "scanned_at": "2026-07-21T12:00:00Z",
        "python_file_count": 42,
        "python_total_lines": 9001,
        "test_file_count": 13,
        "direct_ipfs_import_count": 3,
        "sys_path_mutation_count": 2,
        "broad_exception_count": 8,
    }

    supervisor._write_status(
        {
            "status": "seeded",
            "pid": 0,
            "pid_alive": False,
            "scan_summary": scan_summary,
            "counts": counts,
        }
    )

    persisted = json.loads(supervisor.STATUS_PATH.read_text(encoding="utf-8"))
    assert persisted["schema"] == supervisor.STATUS_SCHEMA
    assert persisted["pid"] == 0
    assert persisted["pid_alive"] is False
    assert persisted["heartbeat"] == persisted["heartbeat_at"] == persisted["updated_at"]
    assert persisted["artifacts"]["status_file"] == str(supervisor.STATUS_PATH)
    assert persisted["artifacts"]["queue_path"] == str(supervisor.QUEUE_PATH)
    assert persisted["last_error"] is None
    assert persisted["scan_summary"] == scan_summary
    assert persisted["counts"] == counts
    assert persisted["todo_counts"] == counts["todo"]
    assert persisted["queue_counts"] == counts["queue"]

    inspected = supervisor.status_payload()
    assert inspected["pid"] == 0
    assert inspected["heartbeat"] == persisted["heartbeat"]
    assert inspected["updated_at"] == persisted["updated_at"]
    assert inspected["artifacts"] == persisted["artifacts"]
    assert inspected["last_error"] is None
    assert inspected["heartbeat_age_seconds"] is not None
    assert inspected["scan_summary"] == scan_summary
    assert inspected["counts"] == counts


def test_status_uses_live_upstream_heartbeat(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    counts = {
        "todo": {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0},
        "queue": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
    }
    monkeypatch.setattr(supervisor, "_collect_counts", lambda: (counts, {}))
    supervisor.STATUS_PATH.write_text(
        json.dumps({"status": "started", "pid": os.getpid(), "heartbeat": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    supervisor.PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
    supervisor.UPSTREAM_SUPERVISOR_STATUS_PATH.write_text(
        json.dumps({"status": "running", "heartbeat_at": "2026-07-21T12:34:56Z"}),
        encoding="utf-8",
    )

    payload = supervisor.status_payload()

    assert payload["pid"] == os.getpid()
    assert payload["pid_alive"] is True
    assert payload["heartbeat"] == "2026-07-21T12:34:56Z"
    assert payload["heartbeat_at"] == payload["heartbeat"]
    assert payload["upstream_supervisor_status"]["status"] == "running"


def test_durable_status_projection_repairs_primary_counts_and_bundle_shards(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    supervisor.BUNDLE_DIR.mkdir()
    supervisor.TODO_PATH.write_text(
        """- [ ] Task checkbox-1: REF-001 First task

## REF-001 First task

- Status: todo

## REF-002 Second task

- Status: completed

- [ ] Task checkbox-3: REF-003 Reopened task

## REF-003 Reopened task

- Status: todo
""",
        encoding="utf-8",
    )
    shard = supervisor.BUNDLE_DIR / "objective.todo.md"
    shard.write_text(
        """- [ ] Task checkbox-1: REF-001 First task

## REF-001 First task

- Status: todo

- [ ] Task checkbox-2: REF-002 Second task

## REF-002 Second task

- Status: todo

- [!] Task checkbox-3: REF-003 Reopened task

## REF-003 Reopened task

- Status: blocked
""",
        encoding="utf-8",
    )
    colliding_shard = supervisor.BUNDLE_DIR / "repair.todo.md"
    colliding_shard.write_text(
        """- [ ] Task checkbox-1: REF-001 Different repair task

## REF-001 Different repair task

- Status: todo
- Dedupe key: reconciliation_guardrail:different_repair
""",
        encoding="utf-8",
    )
    supervisor.TASK_STATE_PATH.write_text(
        json.dumps({"completed_task_ids": ["REF-001"], "blocked_task_ids": []}),
        encoding="utf-8",
    )

    projected = supervisor.synchronize_taskboard_statuses()

    assert projected["completed_count"] == 2
    assert supervisor._todo_counts() == {
        "needed": 1,
        "in_progress": 0,
        "complete": 2,
        "blocked": 0,
    }
    assert "- [x] Task checkbox-1: REF-001" in supervisor.TODO_PATH.read_text(encoding="utf-8")
    shard_text = shard.read_text(encoding="utf-8")
    assert "- [x] Task checkbox-1: REF-001" in shard_text
    assert "- [x] Task checkbox-2: REF-002" in shard_text
    assert "- [ ] Task checkbox-3: REF-003" in shard_text
    assert shard_text.count("- Status: completed") == 2
    assert "## REF-003 Reopened task\n\n- Status: todo" in shard_text
    colliding_text = colliding_shard.read_text(encoding="utf-8")
    assert "- [ ] Task checkbox-1: REF-001 Different repair task" in colliding_text
    assert "- Status: todo" in colliding_text


def test_durable_status_projection_promotes_matching_bundle_receipt_only(
    tmp_path, monkeypatch
) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    supervisor.BUNDLE_DIR.mkdir()
    supervisor.TODO_PATH.write_text(
        """## REF-001 Canonical implementation task

- Status: todo
- Outputs: src/runtime.py
- Acceptance: Runtime is implemented.

## REF-002 Still open

- Status: todo
- Outputs: src/other.py
- Acceptance: Other work is implemented.
""",
        encoding="utf-8",
    )
    tasks = supervisor._upstream_portal_task_parser()(
        supervisor.TODO_PATH, supervisor.TASK_HEADER_PREFIX
    )
    target_cid = next(task.canonical_task_cid for task in tasks if task.task_id == "REF-001")
    lane_state = supervisor.BUNDLE_LANE_ROOT / "objective-runtime" / "state"
    lane_state.mkdir(parents=True)
    (lane_state / "agent_objective_runtime_events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "todo_status_updated",
                        "timestamp": "2026-07-22T12:00:00+00:00",
                        "task_id": "REF-001",
                        "canonical_task_cid": target_cid,
                        "updated": True,
                        "updated_task_ids": ["REF-001"],
                    }
                ),
                json.dumps(
                    {
                        "type": "todo_status_updated",
                        "timestamp": "2026-07-22T12:01:00+00:00",
                        "task_id": "REF-002",
                        "canonical_task_cid": "different-semantic-task-cid",
                        "updated": True,
                        "updated_task_ids": ["REF-002"],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    projected = supervisor.synchronize_taskboard_statuses()

    text = supervisor.TODO_PATH.read_text(encoding="utf-8")
    assert projected["completed_count"] == 1
    assert "## REF-001 Canonical implementation task\n\n- Status: completed" in text
    assert "## REF-002 Still open\n\n- Status: todo" in text


def test_projection_reconciliation_updates_all_query_and_planning_artifacts(
    tmp_path, monkeypatch
) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    supervisor.BUNDLE_DIR.mkdir()
    supervisor.TODO_PATH.write_text(
        """- [ ] Task checkbox-1: REF-001 Completed implementation

## REF-001 Completed implementation

- Status: completed

- [ ] Task checkbox-2: REF-002 Pending implementation

## REF-002 Pending implementation

- Status: todo
""",
        encoding="utf-8",
    )
    shard = supervisor.BUNDLE_DIR / "goal.todo.md"
    shard.write_text(supervisor.TODO_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    supervisor.GOALS_PATH.write_text(
        json.dumps(
            {
                "goals": [
                    {
                        "id": "G1",
                        "subgoals": [
                            {
                                "id": "G1.S1",
                                "tasks": [
                                    {"task_id": "REF-001", "status": "needed"},
                                    {"task_id": "REF-002", "status": "needed"},
                                ],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    index_path = supervisor.BUNDLE_DIR / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema": "complaint_generator.refactor_seed_bundle_index",
                "generated_at": "2026-07-22T00:00:00Z",
                "source_todo": "todo.md",
                "completed_task_ids": ["REF-002"],
                "bundles": {
                    "g1/s1": {
                        "bundle_key": "g1/s1",
                        "tasks": [
                            {"task_id": "REF-001", "status": "todo"},
                            {"task_id": "REF-002", "status": "todo"},
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = supervisor.reconcile_task_projection_artifacts()

    assert result["updated"] is True
    assert "- [x] Task checkbox-1: REF-001" in supervisor.TODO_PATH.read_text(encoding="utf-8")
    assert "- [x] Task checkbox-1: REF-001" in shard.read_text(encoding="utf-8")
    goals = json.loads(supervisor.GOALS_PATH.read_text(encoding="utf-8"))
    assert goals["goals"][0]["subgoals"][0]["tasks"][0]["status"] == "complete"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["bundles"]["g1/s1"]["tasks"][0]["status"] == "completed"
    assert "REF-001" in index["completed_task_ids"]
    assert "REF-002" not in index["completed_task_ids"]
    assert index_path.with_suffix(".duckdb").exists()


def test_projection_reconciliation_queries_manifest_running_count(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    supervisor.BUNDLE_DIR.mkdir()
    supervisor.BUNDLE_LANE_MANIFEST.write_text("not loaded directly", encoding="utf-8")
    calls = []

    class ArtifactStore:
        @staticmethod
        def read_artifact_fields(path, fields):
            calls.append((path, fields))
            return {"running_count": 1, "lanes": []}

    monkeypatch.setattr(supervisor, "_upstream_artifact_store", lambda: ArtifactStore())

    result = supervisor.reconcile_task_projection_artifacts()

    assert result["reason"] == "active_projection_reconciled"
    assert result["updated"] is False
    assert result["parallel_running_count"] == 1
    assert result["bundle_index"]["reason"] == "index_missing"
    assert calls == [(supervisor.BUNDLE_LANE_MANIFEST, ("running_count", "lanes"))]


def test_active_projection_updates_bundle_index_without_rewriting_taskboards(
    tmp_path, monkeypatch
) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    supervisor.BUNDLE_DIR.mkdir()
    supervisor.TODO_PATH.write_text(
        """- [ ] Task checkbox-1: REF-001 Active implementation

## REF-001 Active implementation

- Status: todo

- [ ] Task checkbox-2: REF-002 Durably blocked implementation

## REF-002 Durably blocked implementation

- Status: todo
""",
        encoding="utf-8",
    )
    supervisor.TASK_STATE_PATH.write_text(
        json.dumps(
            {
                "implementation_in_progress": True,
                "active_task_id": "REF-001",
                "active_phase": "implementing",
                "blocked_task_ids": ["REF-002"],
            }
        ),
        encoding="utf-8",
    )
    index_path = supervisor.BUNDLE_DIR / "index.json"
    shard_path = supervisor.BUNDLE_DIR / "g1-s1.todo.md"
    shard_path.write_text(
        supervisor.TODO_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    index_path.write_text(
        json.dumps(
            {
                "source_todo": str(supervisor.TODO_PATH),
                "bundles": {
                    "g1/s1": {
                        "bundle_key": "g1/s1",
                        "shard_path": str(shard_path),
                        "tasks": [
                            {"task_id": "REF-001", "status": "todo"},
                            {"task_id": "REF-002", "status": "todo"},
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = supervisor.reconcile_task_projection_artifacts()

    assert result["reason"] == "active_projection_reconciled"
    assert result["updated"] is True
    assert result["bundle_index"]["updated_task_ids"] == ["REF-001", "REF-002"]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["bundles"]["g1/s1"]["tasks"][0]["status"] == "in_progress"
    assert index["bundles"]["g1/s1"]["tasks"][1]["status"] == "blocked"
    assert "- Status: todo" in supervisor.TODO_PATH.read_text(encoding="utf-8")
    shard_text = shard_path.read_text(encoding="utf-8")
    assert "- Status: in_progress" in shard_text
    assert "- Status: blocked" in shard_text
    assert result["bundle_shards"]["updated_file_count"] == 1
    assert index_path.with_suffix(".duckdb").exists()


def test_seed_bundle_index_carries_durable_member_status(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "TASKBOARD_DOC_PATH", tmp_path / "taskboard.md")
    task = supervisor.RefactorTask(
        goal_id="G1",
        subgoal_id="G1.S1",
        title="Completed member",
        priority="P0",
        files=(),
        rationale="Already merged.",
        acceptance=("Receipt exists.",),
        validation=("true",),
        task_id="REF-001",
    )
    goals = [
        {
            "id": "G1",
            "title": "Goal",
            "priority": "P0",
            "subgoals": [{"id": "G1.S1", "title": "Subgoal", "tasks": [task]}],
        }
    ]

    result = supervisor.write_seed_bundle_index(goals, task_statuses={"REF-001": "completed"})

    index = json.loads((supervisor.BUNDLE_DIR / "index.json").read_text(encoding="utf-8"))
    member = index["bundles"]["refactor/g1/g1-s1"]["tasks"][0]
    assert member["status"] == "completed"
    assert index["query_store"]["duckdb_path"] == "index.duckdb"
    assert (supervisor.BUNDLE_DIR / "index.duckdb").exists()
    assert result["bundle_index_duckdb_path"].endswith("index.duckdb")


def test_seed_bundle_index_prunes_cross_bundle_and_colliding_task_blocks(
    tmp_path, monkeypatch
) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "TASKBOARD_DOC_PATH", tmp_path / "taskboard.md")
    supervisor.BUNDLE_DIR.mkdir(parents=True)
    first = supervisor.RefactorTask(
        goal_id="G1",
        subgoal_id="G1.S1",
        title="First bundle member",
        priority="P0",
        files=(),
        rationale="First work.",
        acceptance=("First is complete.",),
        validation=("true",),
        task_id="REF-001",
    )
    second = supervisor.RefactorTask(
        goal_id="G1",
        subgoal_id="G1.S2",
        title="Second bundle member",
        priority="P0",
        files=(),
        rationale="Second work.",
        acceptance=("Second is complete.",),
        validation=("true",),
        task_id="REF-002",
    )
    first_shard = supervisor.BUNDLE_DIR / "refactor-g1-g1-s1.todo.md"
    first_shard.write_text(
        """# Objective Bundle: refactor/g1/g1-s1

## REF-002 Second bundle member

- Status: completed

## REF-003 Resolve dependency guardrail for REF-001

- Status: todo
""",
        encoding="utf-8",
    )
    goals = [
        {
            "id": "G1",
            "title": "Goal",
            "priority": "P0",
            "subgoals": [
                {"id": "G1.S1", "title": "First", "tasks": [first]},
                {"id": "G1.S2", "title": "Second", "tasks": [second]},
            ],
        }
    ]

    result = supervisor.write_seed_bundle_index(goals)

    first_text = first_shard.read_text(encoding="utf-8")
    second_text = (supervisor.BUNDLE_DIR / "refactor-g1-g1-s2.todo.md").read_text(
        encoding="utf-8"
    )
    assert "## REF-001 First bundle member" in first_text
    assert "## REF-002" not in first_text
    assert "## REF-003" not in first_text
    assert "## REF-002 Second bundle member" in second_text
    assert result["pruned_task_ids"] == {
        "refactor/g1/g1-s1": ["REF-002", "REF-003"]
    }


def test_seed_bundle_index_preserves_dynamic_bundle_members(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "TASKBOARD_DOC_PATH", tmp_path / "taskboard.md")
    supervisor.BUNDLE_DIR.mkdir(parents=True)
    dynamic_bundle = "codebase/runtime/src-runtime"
    (supervisor.BUNDLE_DIR / "index.json").write_text(
        json.dumps(
            {
                "bundles": {
                    dynamic_bundle: {
                        "bundle_key": dynamic_bundle,
                        "shard_path": "bundles/codebase-runtime-src-runtime.todo.md",
                        "parallel_lane": dynamic_bundle,
                        "bundle_strategy": "codebase_file_ast",
                        "tasks": [
                            {
                                "task_id": "REF-080",
                                "status": "todo",
                                "title": "Generated finding",
                                "candidate_kind": "codebase_scan",
                                "paths": ["src/runtime.py"],
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    task = supervisor.RefactorTask(
        goal_id="G1",
        subgoal_id="G1.S1",
        title="Seed member",
        priority="P0",
        files=(),
        rationale="Initial plan.",
        acceptance=("Seed remains present.",),
        validation=("true",),
        task_id="REF-001",
    )
    goals = [
        {
            "id": "G1",
            "title": "Goal",
            "priority": "P0",
            "subgoals": [{"id": "G1.S1", "title": "Subgoal", "tasks": [task]}],
        }
    ]

    result = supervisor.write_seed_bundle_index(
        goals,
        task_statuses={"REF-001": "completed", "REF-080": "todo"},
    )

    index = json.loads((supervisor.BUNDLE_DIR / "index.json").read_text(encoding="utf-8"))
    assert set(index["bundles"]) == {"refactor/g1/g1-s1", dynamic_bundle}
    assert index["bundles"][dynamic_bundle]["tasks"][0]["task_id"] == "REF-080"
    assert result["task_count"] == 2
    assert result["dynamic_task_count"] == 1


def test_seed_bundle_index_retains_excluded_bundle_dependency_metadata(
    tmp_path, monkeypatch
) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "TASKBOARD_DOC_PATH", tmp_path / "taskboard.md")
    prerequisite = supervisor.RefactorTask(
        goal_id="G9",
        subgoal_id="G9.S2",
        title="Completed prerequisite",
        priority="P0",
        files=(),
        rationale="Already merged.",
        acceptance=("Receipt exists.",),
        validation=("true",),
        task_id="REF-041",
    )
    dependent = supervisor.RefactorTask(
        goal_id="G9",
        subgoal_id="G9.S3",
        title="Runnable dependent",
        priority="P0",
        files=(),
        rationale="Runs after the prerequisite.",
        acceptance=("The lane remains claimable.",),
        validation=("true",),
        depends_on=("REF-041",),
        task_id="REF-042",
    )
    goals = [
        {
            "id": "G9",
            "title": "Supervisor throughput",
            "priority": "P0",
            "subgoals": [
                {"id": "G9.S2", "title": "Prerequisite", "tasks": [prerequisite]},
                {"id": "G9.S3", "title": "Dependent", "tasks": [dependent]},
            ],
        }
    ]

    supervisor.write_seed_bundle_index(
        goals,
        exclude_bundle_keys={"refactor/g9/g9-s2"},
        task_statuses={"REF-041": "completed", "REF-042": "todo"},
    )

    index_path = supervisor.BUNDLE_DIR / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["excluded_bundle_keys"] == ["refactor/g9/g9-s2"]
    assert index["completed_task_ids"] == ["REF-041"]
    assert "refactor/g9/g9-s2" in index["bundles"]
    assert not (supervisor.BUNDLE_DIR / "refactor-g9-g9-s2.todo.md").exists()
    payloads = supervisor._upstream_bundle_payload_builder()(index_path)
    dependent_payload = next(
        payload for payload in payloads if payload["bundle_key"] == "refactor/g9/g9-s3"
    )
    assert dependent_payload["claimable"] is True
    assert dependent_payload["dependency_repair_evidence"] == []


def test_start_parallel_detaches_scheduler_and_uses_requested_poll_interval(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "ACCELERATE_REPO", tmp_path / "ipfs_accelerate_py")
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "BUNDLE_LANE_ROOT", tmp_path / "bundle-lanes")
    monkeypatch.setattr(supervisor, "BUNDLE_COORDINATION_PATH", tmp_path / "coordination.duckdb")
    monkeypatch.setattr(supervisor, "active_bundle_keys", lambda: set())
    monkeypatch.setattr(
        supervisor,
        "seed_taskboard",
        lambda **_kwargs: {"counts": {"todo": {}}, "bundle_seed": {"generated": 2}},
    )
    monkeypatch.setattr(supervisor, "_pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(supervisor.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        supervisor,
        "_collect_counts",
        lambda: ({"todo": {}, "queue": {}}, {}),
    )
    captured: dict[str, object] = {}

    class Process:
        pid = 4242

        @staticmethod
        def poll():
            return None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)
    args = supervisor.build_parser().parse_args(["start-parallel", "--interval-s", "37"])

    payload = supervisor.run_parallel_bundle_supervisor(args, start=True)

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:3] == [sys.executable, "-m", "ipfs_accelerate_py.agent_supervisor.bundle_supervisor"]
    assert command[command.index("--poll-interval") + 1] == "37.0"
    assert command.count("--external-task-state-path") == 1
    assert command[command.index("--external-task-state-path") + 1] == str(
        supervisor.TASK_STATE_PATH
    )
    assert command.count("--worktree-submodule-path") == 1
    assert command[command.index("--worktree-submodule-path") + 1] == "ipfs_datasets_py/ipfs_accelerate_py"
    assert command.count("--generated-dirty-path") == 1
    assert command[command.index("--generated-dirty-path") + 1] == str(
        supervisor.TASKBOARD_DOC_PATH
    )
    assert command[command.index("--coordination-path") + 1] == str(
        supervisor.BUNDLE_COORDINATION_PATH
    )
    assert supervisor.BUNDLE_COORDINATION_PATH.suffix == ".duckdb"
    assert command[-1] == "--start"
    assert captured["kwargs"]["start_new_session"] is True
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert payload["status"] == "started"
    assert supervisor.BUNDLE_SCHEDULER_PID_PATH.read_text(encoding="utf-8") == "4242\n"


def test_parallel_defaults_minimize_idle_lane_handoff_latency() -> None:
    args = supervisor.build_parser().parse_args(["start-parallel"])

    assert args.max_lanes == 4
    assert args.interval_s == supervisor.DEFAULT_PARALLEL_RECONCILE_INTERVAL_SECONDS == 15.0
    assert args.daemon_interval_s == supervisor.DEFAULT_PARALLEL_DAEMON_INTERVAL_SECONDS == 15.0


def test_start_daemon_passes_managed_submodule_path_once(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "ACCELERATE_REPO", tmp_path / "ipfs_accelerate_py")
    monkeypatch.setattr(supervisor, "SUPERVISOR_STATE_DIR", tmp_path / "supervisor-state")
    monkeypatch.setattr(supervisor, "WORKTREE_ROOT", tmp_path / "worktrees")
    monkeypatch.setattr(supervisor, "LOG_PATH", tmp_path / "supervisor.log")
    monkeypatch.setattr(
        supervisor,
        "seed_taskboard",
        lambda **_kwargs: {"counts": {"todo": {}}, "bundle_seed": {"generated": 2}},
    )
    monkeypatch.setattr(supervisor, "_pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(supervisor.time, "sleep", lambda _seconds: None)
    captured: dict[str, object] = {}

    class Process:
        pid = 4242

        @staticmethod
        def poll():
            return None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)
    args = supervisor.build_parser().parse_args(["start"])

    payload = supervisor.start_daemon(args)

    command = captured["command"]
    assert isinstance(command, list)
    assert command.count("--worktree-submodule-path") == 1
    assert command[command.index("--worktree-submodule-path") + 1] == (
        "ipfs_datasets_py/ipfs_accelerate_py"
    )
    assert command.count("--external-reservation-manifest-path") == 1
    assert command[command.index("--external-reservation-manifest-path") + 1] == str(
        supervisor.BUNDLE_LANE_MANIFEST
    )
    assert command.count("--generated-dirty-path") == 1
    assert command[command.index("--generated-dirty-path") + 1] == str(
        supervisor.TASKBOARD_DOC_PATH
    )
    assert command.count("--allow-codebase-refill-with-objective-work") == 1
    assert command.count("--objective-mission-term") == 1
    assert command[command.index("--objective-mission-term") + 1] == "adversarial_harness"
    assert captured["kwargs"]["start_new_session"] is True
    assert payload["status"] == "started"


def test_status_projects_dynamic_parallel_scheduler_manifest(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(
        supervisor,
        "_collect_counts",
        lambda: ({"todo": {}, "queue": {}}, {}),
    )
    supervisor.BUNDLE_SCHEDULER_PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
    supervisor.BUNDLE_LANE_MANIFEST.write_text(
        json.dumps(
            {
                "schema": "ipfs_accelerate_py.agent_supervisor.dynamic_bundle_scheduler@1",
                "scheduler_state": "running",
                "cycle": 3,
                "planned_count": 8,
                "started_count": 2,
                "running_count": 2,
                "ready_count": 5,
                "blocked_count": 1,
                "completed_count": 4,
                "lanes": [
                    {
                        "bundle_key": "objective/a",
                        "state": "running",
                        "pid": 123,
                        "task_ids": ["T-1"],
                        "conflict_color": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = supervisor.status_payload()

    assert payload["parallel_scheduler"]["pid_alive"] is True
    assert payload["parallel_lanes"]["running_count"] == 2
    assert payload["parallel_lanes"]["ready_count"] == 5
    assert payload["parallel_lanes"]["lanes"][0]["task_ids"] == ["T-1"]
    assert supervisor.BUNDLE_LANE_MANIFEST.with_suffix(".duckdb").exists()


def test_parallel_scheduler_has_explicit_stop_command() -> None:
    assert supervisor.build_parser().parse_args(["stop-parallel"]).command == "stop-parallel"


def test_stop_daemon_terminates_process_group_and_cleans_pid(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    counts = {
        "todo": {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0},
        "queue": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
    }
    monkeypatch.setattr(supervisor, "_collect_counts", lambda: (counts, {}))
    monkeypatch.setattr(supervisor, "STOP_TIMEOUT_SECONDS", 5.0)
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import signal,sys,time; "
                "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
                "print('ready', flush=True); time.sleep(60)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    managed = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import signal,sys,time; "
                "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
                "print('managed-ready', flush=True); time.sleep(60)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        assert managed.stdout is not None
        assert managed.stdout.readline().strip() == "managed-ready"
        supervisor.PID_PATH.write_text(f"{child.pid}\n", encoding="utf-8")
        supervisor.MANAGED_DAEMON_PID_PATH.write_text(f"{managed.pid}\n", encoding="utf-8")

        result = supervisor.stop_daemon()

        child.wait(timeout=2)
        managed.wait(timeout=2)
        assert result["status"] == "stopped"
        assert result["pid"] == child.pid
        assert result["pid_alive"] is False
        assert result["signal_scope"] == "process_group"
        assert result["managed_daemon_pid"] == managed.pid
        assert result["managed_daemon_pid_alive"] is False
        assert result["managed_daemon_signal_scope"] == "process_group"
        assert not supervisor.PID_PATH.exists()
        assert not supervisor.MANAGED_DAEMON_PID_PATH.exists()
        persisted = json.loads(supervisor.STATUS_PATH.read_text(encoding="utf-8"))
        assert persisted["status"] == "stopped"
        assert persisted["pid"] == child.pid
        assert persisted["pid_alive"] is False
        assert persisted["counts"] == counts
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=2)
        if managed.poll() is None:
            managed.terminate()
            managed.wait(timeout=2)


def test_stop_daemon_stops_orphaned_managed_worker(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "STOP_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(
        supervisor,
        "_collect_counts",
        lambda: ({"todo": {}, "queue": {}}, {}),
    )
    managed = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal,sys,time; signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); time.sleep(60)",
        ],
        start_new_session=True,
    )
    try:
        supervisor.MANAGED_DAEMON_PID_PATH.write_text(f"{managed.pid}\n", encoding="utf-8")

        result = supervisor.stop_daemon()

        managed.wait(timeout=2)
        assert result["status"] == "stopped"
        assert result["pid"] == 0
        assert result["managed_daemon_pid"] == managed.pid
        assert result["managed_daemon_pid_alive"] is False
    finally:
        if managed.poll() is None:
            managed.terminate()
            managed.wait(timeout=2)
