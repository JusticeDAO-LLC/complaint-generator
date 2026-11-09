#!/usr/bin/env python3
"""Complaint-generator refactor supervisor wrapper.

This script keeps the repo-specific scan and initial refactor objectives here,
but delegates objective scanning, backlog refill, bundle queue submission, and
implementation supervision to ``ipfs_accelerate_py.agent_supervisor``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACCELERATE_REPO = PROJECT_ROOT / "ipfs_datasets_py" / "ipfs_accelerate_py"
STATE_ROOT = PROJECT_ROOT / "data" / "refactor_supervisor"
QUEUE_PATH = STATE_ROOT / "refactor_taskboard.duckdb"
GOALS_PATH = STATE_ROOT / "refactor_goals.json"
OBJECTIVE_PATH = STATE_ROOT / "refactor_objective_heap.md"
TODO_PATH = STATE_ROOT / "refactor_todo.md"
BUNDLE_DIR = STATE_ROOT / "objective_bundles"
DATASET_DIR = STATE_ROOT / "objective_datasets"
DISCOVERY_DIR = STATE_ROOT / "discovery"
GRAPH_PATH = STATE_ROOT / "objective_graph.json"
STRATEGY_PATH = STATE_ROOT / "strategy.json"
EVENTS_PATH = STATE_ROOT / "events.jsonl"
REFILL_STATE_PATH = STATE_ROOT / "refill_state.json"
SUPERVISOR_STATE_DIR = STATE_ROOT / "supervisor_state"
TASK_STATE_PATH = SUPERVISOR_STATE_DIR / "complaint_generator_refactor_task_state.json"
MANAGED_DAEMON_PID_PATH = SUPERVISOR_STATE_DIR / "complaint_generator_refactor_managed_daemon.pid"
WORKTREE_ROOT = STATE_ROOT / "worktrees"
BUNDLE_LANE_ROOT = STATE_ROOT / "bundle_lanes"
BUNDLE_LANE_MANIFEST = BUNDLE_LANE_ROOT / "bundle_lanes.json"
BUNDLE_COORDINATION_PATH = BUNDLE_LANE_ROOT / "coordination.duckdb"
BUNDLE_SCHEDULER_PID_PATH = BUNDLE_LANE_ROOT / "bundle_scheduler.pid"
BUNDLE_SCHEDULER_LOG_PATH = BUNDLE_LANE_ROOT / "bundle_scheduler.log"
MERGE_RESOLVER_PID_PATH = STATE_ROOT / "merge_resolver_watchdog.pid"
MERGE_RESOLVER_STATUS_PATH = STATE_ROOT / "merge_resolver_watchdog_status.json"
MERGE_RESOLVER_LOG_PATH = STATE_ROOT / "merge_resolver_watchdog.log"
MERGE_RESOLVER_REGISTRY_DIR = STATE_ROOT / "merge_resolver_registry"
STATUS_PATH = STATE_ROOT / "refactor_supervisor_status.json"
PID_PATH = STATE_ROOT / "refactor_supervisor.pid"
LOG_PATH = STATE_ROOT / "refactor_supervisor.log"
UPSTREAM_SUPERVISOR_STATUS_PATH = SUPERVISOR_STATE_DIR / "complaint_generator_refactor_supervisor_status.json"
TASKBOARD_DOC_PATH = PROJECT_ROOT / "docs" / "REFACTOR_SUPERVISOR_TASKBOARD.md"
IPFS_EXECUTION_BACKLOG_PATH = PROJECT_ROOT / "docs" / "IPFS_DATASETS_PY_EXECUTION_BACKLOG.md"

IPFS_P0_CROSS_LINKS_START = "<!-- refactor-supervisor:p0-cross-links:start -->"
IPFS_P0_CROSS_LINKS_END = "<!-- refactor-supervisor:p0-cross-links:end -->"

TASK_PREFIX = "REF-"
TASK_HEADER_PREFIX = "## REF-"
TASK_TYPES = ("codex.todo_bundle",)
MODEL_NAME = "complaint-generator-refactor-supervisor"
STATUS_SCHEMA = "complaint_generator.refactor_supervisor.status.v1"
TASK_PAYLOAD_SCHEMA = "complaint_generator.refactor_supervisor.task.v1"
BUNDLE_TASK_PAYLOAD_SCHEMA = "complaint_generator.refactor_supervisor.bundle_task.v1"
STOP_TIMEOUT_SECONDS = 20.0
STOP_POLL_SECONDS = 0.1
DEFAULT_PARALLEL_RECONCILE_INTERVAL_SECONDS = 15.0
DEFAULT_PARALLEL_DAEMON_INTERVAL_SECONDS = 15.0


def _ensure_accelerate_import_path() -> None:
    path = str(ACCELERATE_REPO)
    if path not in sys.path:
        sys.path.insert(0, path)


def _task_queue_class():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.p2p_tasks import TaskQueue

    return TaskQueue


def _upstream_objective_runner():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.objective_daemon import (
        build_arg_parser,
        run_objective_daemon,
    )

    return build_arg_parser, run_objective_daemon


def _upstream_backlog_runner():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.backlog_refinery import (
        build_arg_parser,
        run_backlog_refinery,
    )

    return build_arg_parser, run_backlog_refinery


def _upstream_task_board_helpers():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.engine import parse_markdown_tasks
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.task_board import task_status_counts

    return parse_markdown_tasks, task_status_counts


def _upstream_portal_task_parser():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import parse_task_file

    return parse_task_file


def _upstream_bundle_runner():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.bundle_supervisor import build_arg_parser, run_bundle_supervisor

    return build_arg_parser, run_bundle_supervisor


def _upstream_bundle_payload_builder():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.objective_graph import build_bundle_task_payloads

    return build_bundle_task_payloads


def _upstream_bundle_completion_receipt_loader():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.bundle_supervisor import (
        bundle_member_completion_receipts,
    )

    return bundle_member_completion_receipts


def _upstream_artifact_store():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor import artifact_store

    return artifact_store


def merge_resolver_command() -> str:
    return shlex.join(
        (
            "env",
            f"PYTHONPATH={ACCELERATE_REPO}{os.pathsep}{PROJECT_ROOT}",
            "AGENT_MERGE_LLM_ROUTER_CONFIG=config.llm_router.json",
            "AGENT_MERGE_LLM_ROUTER_BACKEND_ID=llm-router-codex",
            "AGENT_MERGE_LLM_ROUTER_MAX_TOKENS=4096",
            "CODEX_MERGE_RESOLVER_TIMEOUT_SECONDS=300",
            "COPILOT_MERGE_RESOLVER_TIMEOUT_SECONDS=300",
            "AGENT_RESOLVER_LOCK_TIMEOUT_SECONDS=60",
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "llm_router_merge_resolver.py"),
        )
    )


@dataclass(frozen=True)
class RefactorTask:
    goal_id: str
    subgoal_id: str
    title: str
    priority: str
    files: tuple[str, ...]
    rationale: str
    acceptance: tuple[str, ...]
    validation: tuple[str, ...]
    task_id: str = ""
    depends_on: tuple[str, ...] = ()

    @property
    def stable_key(self) -> str:
        return f"{self.goal_id}:{self.subgoal_id}:{self.title}".lower()

    def payload(self) -> dict[str, Any]:
        payload = {
            "schema": TASK_PAYLOAD_SCHEMA,
            "supervisor": "refactor_agent_supervisor",
            "objective": "Refactor complaint-generator safely and incrementally.",
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "title": self.title,
            "priority": self.priority,
            "files": list(self.files),
            "rationale": self.rationale,
            "acceptance": list(self.acceptance),
            "validation": list(self.validation),
            "task_id": self.task_id,
            "depends_on": list(self.depends_on),
            "stable_key": self.stable_key,
            "created_by": "ipfs_accelerate_py.p2p_tasks.TaskQueue",
        }
        _validate_task_payload_fields(payload, context=f"refactor task {self.task_id or self.title!r}")
        return payload


def _payload_strings(value: Any) -> list[str]:
    """Normalize a scalar or sequence payload field without splitting strings."""

    values = value if isinstance(value, (list, tuple)) else [value]
    return list(
        dict.fromkeys(
            str(item).strip()
            for item in values
            if item is not None and str(item).strip()
        )
    )


def _validate_task_payload_fields(payload: dict[str, Any], *, context: str) -> None:
    """Reject task payloads that cannot provide an actionable work contract."""

    errors: list[str] = []
    for field in ("goal_id", "subgoal_id"):
        value = payload.get(field)
        valid = (isinstance(value, str) and bool(value.strip())) or (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(item, str) and bool(item.strip()) for item in value)
        )
        if not valid:
            errors.append(f"{field} must be a non-empty string or list")
    if not isinstance(payload.get("priority"), str) or not str(payload["priority"]).strip():
        errors.append("priority must be a non-empty string")
    for field in ("acceptance", "validation"):
        value = payload.get(field)
        if not (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(item, str) and bool(item.strip()) for item in value)
        ):
            errors.append(f"{field} must be a non-empty list")
    if errors:
        raise ValueError(f"Malformed {context} payload: " + "; ".join(errors))


def _iter_py_files() -> list[Path]:
    roots = [
        "applications",
        "backends",
        "complaint_analysis",
        "complaint_generator",
        "complaint_phases",
        "integrations",
        "lib",
        "mediator",
        "scripts",
        "tests",
    ]
    files: list[Path] = []
    for root_name in roots:
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in {".venv", "__pycache__"} for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def scan_codebase() -> dict[str, Any]:
    py_files = _iter_py_files()
    line_counts: list[tuple[int, str]] = []
    direct_ipfs_imports: list[str] = []
    sys_path_mutations: list[str] = []
    broad_exceptions: list[str] = []
    wildcard_imports: list[str] = []
    silent_passes: list[str] = []

    for path in py_files:
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel == "scripts/refactor_agent_supervisor.py":
            continue
        text = _read_text(path)
        lines = text.splitlines()
        line_counts.append((len(lines), rel))
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if "from ipfs_datasets_py" in stripped or "import ipfs_datasets_py" in stripped:
                direct_ipfs_imports.append(f"{rel}:{idx}")
            if "sys.path.insert" in stripped or "sys.path.append" in stripped:
                sys_path_mutations.append(f"{rel}:{idx}")
            if stripped.startswith("except Exception"):
                broad_exceptions.append(f"{rel}:{idx}")
            if stripped.endswith("import *"):
                wildcard_imports.append(f"{rel}:{idx}")
            if stripped == "pass":
                silent_passes.append(f"{rel}:{idx}")

    return {
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python_file_count": len(py_files),
        "python_total_lines": sum(n for n, _ in line_counts),
        "largest_python_files": [
            {"path": rel, "lines": count} for count, rel in sorted(line_counts, reverse=True)[:25]
        ],
        "signals": {
            "direct_ipfs_imports": direct_ipfs_imports[:200],
            "direct_ipfs_import_count": len(direct_ipfs_imports),
            "sys_path_mutations": sys_path_mutations[:200],
            "sys_path_mutation_count": len(sys_path_mutations),
            "broad_exception_count": len(broad_exceptions),
            "wildcard_imports": wildcard_imports[:100],
            "wildcard_import_count": len(wildcard_imports),
            "silent_pass_count": len(silent_passes),
        },
        "test_file_count": len([p for p in py_files if p.relative_to(PROJECT_ROOT).parts[0] == "tests"]),
        "packaging": {
            "pyproject": (PROJECT_ROOT / "pyproject.toml").exists(),
            "pytest_ini": (PROJECT_ROOT / "pytest.ini").exists(),
            "package_json": (PROJECT_ROOT / "package.json").exists(),
        },
    }


def build_goals(scan: dict[str, Any]) -> list[dict[str, Any]]:
    largest = [item["path"] for item in scan.get("largest_python_files", [])[:8]]
    direct_imports = scan.get("signals", {}).get("direct_ipfs_imports", [])
    sys_path = scan.get("signals", {}).get("sys_path_mutations", [])

    return [
        {
            "id": "G1",
            "title": "Stabilize repository boundaries",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G1.S1",
                    "title": "Map package ownership and runtime entrypoints",
                    "tasks": [
                        _task(
                            "G1",
                            "G1.S1",
                            "Create an entrypoint and ownership map for the largest runtime modules",
                            "P0",
                            tuple(largest[:6]),
                            "Large modules dominate change risk and need explicit boundaries before extraction.",
                            ("A short module ownership map exists.", "Entrypoints are grouped by CLI, web, mediator, and workflow role."),
                            ("python -m pytest tests/test_package_imports.py -q",),
                        ),
                        _task(
                            "G1",
                            "G1.S1",
                            "Document allowed dependency direction between applications, mediator, phases, integrations, and lib",
                            "P0",
                            ("docs/ARCHITECTURE.md", "pyproject.toml"),
                            "Refactors need a clear import direction to avoid moving complexity around.",
                            ("Architecture docs identify allowed imports.", "New work has a simple rule for where shared code belongs."),
                            ("python -m pytest tests/test_package_imports.py -q",),
                        ),
                    ],
                },
                {
                    "id": "G1.S2",
                    "title": "Remove ad hoc import path behavior from production surfaces",
                    "tasks": [
                        _task(
                            "G1",
                            "G1.S2",
                            "Replace production sys.path mutation with package-level imports or adapter loader calls",
                            "P0",
                            tuple(_paths_from_locations(sys_path[:12])),
                            "The scan found production-style sys.path mutation that makes runtime behavior environment-sensitive.",
                            ("No production entrypoint mutates sys.path for normal imports.", "Explicit exceptions are isolated to scripts/tests."),
                            ("python -m pytest tests/test_package_imports.py -q",),
                        ),
                        _task(
                            "G1",
                            "G1.S2",
                            "Route direct ipfs_datasets_py imports through integrations/ipfs_datasets adapters where production-facing",
                            "P0",
                            tuple(_paths_from_locations(direct_imports[:16])),
                            "Optional dependency behavior should stay behind the adapter boundary.",
                            ("Production direct imports are replaced or documented.", "Degraded mode still imports cleanly."),
                            ("python -m pytest tests/test_ipfs_adapter_layer.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G2",
            "title": "Decompose oversized orchestration modules",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G2.S1",
                    "title": "Extract mediator service seams",
                    "tasks": [
                        _task(
                            "G2",
                            "G2.S1",
                            "Split mediator/mediator.py by workflow service while preserving public API compatibility",
                            "P0",
                            ("mediator/mediator.py", "mediator/__init__.py"),
                            "The mediator is the largest runtime file and carries high regression risk.",
                            ("One cohesive service is extracted.", "Existing imports continue to resolve."),
                            ("python -m pytest tests/test_mediator.py tests/test_mediator_three_phase.py -q",),
                        ),
                        _task(
                            "G2",
                            "G2.S1",
                            "Move claim support orchestration helpers into focused private modules",
                            "P0",
                            ("mediator/claim_support_hooks.py",),
                            "Claim support hooks are large enough to hide unrelated concerns.",
                            ("At least one cohesive helper group moves behind a stable import.", "No payload contract changes without tests."),
                            ("python -m pytest tests/test_claim_support_hooks.py tests/test_claim_support_review_dashboard_flow.py -q",),
                        ),
                    ],
                },
                {
                    "id": "G2.S2",
                    "title": "Reduce application surface coupling",
                    "tasks": [
                        _task(
                            "G2",
                            "G2.S2",
                            "Extract complaint workspace request handlers from UI state helpers",
                            "P1",
                            ("applications/complaint_workspace.py",),
                            "The workspace module mixes UI routing, state shaping, and workflow calls.",
                            ("One handler group is isolated.", "Routes keep the same response shape."),
                            ("python -m pytest tests/test_review_api.py -q",),
                        ),
                        _task(
                            "G2",
                            "G2.S2",
                            "Separate dashboard fixture data from live route logic",
                            "P1",
                            ("applications/dashboard_ui.py", "playwright/server.js"),
                            "Dashboard behavior is harder to test when fixtures and live assembly are interleaved.",
                            ("Fixture builders are named and reusable.", "Playwright smoke tests remain stable."),
                            ("python -m pytest tests/test_claim_support_review_playwright_smoke.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G3",
            "title": "Harden adapter contracts and degraded mode",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G3.S1",
                    "title": "Normalize IPFS datasets adapter payloads",
                    "tasks": [
                        _task(
                            "G3",
                            "G3.S1",
                            "Standardize capability status and degraded-reason payloads across adapters",
                            "P0",
                            ("integrations/ipfs_datasets/capabilities.py", "integrations/ipfs_datasets/loader.py"),
                            "The existing backlog identifies adapter capability reporting as incomplete.",
                            ("All adapter groups report stable keys.", "Missing optional extras produce actionable reasons."),
                            ("python -m pytest tests/test_ipfs_adapter_layer.py -q",),
                        ),
                        _task(
                            "G3",
                            "G3.S1",
                            "Promote document parsing into a shared ingestion contract",
                            "P0",
                            ("integrations/ipfs_datasets/documents.py", "mediator/evidence_hooks.py"),
                            "Document parsing is still fallback-oriented and should be reusable across ingestion paths.",
                            ("Evidence, authority, and web ingestion can call one parse contract.", "Fallback mode preserves current behavior."),
                            ("python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q",),
                        ),
                    ],
                },
                {
                    "id": "G3.S2",
                    "title": "Clarify graph, GraphRAG, and logic adapter boundaries",
                    "tasks": [
                        _task(
                            "G3",
                            "G3.S2",
                            "Define graph persistence and query interfaces before moving support scoring",
                            "P1",
                            ("integrations/ipfs_datasets/graphs.py", "complaint_phases/knowledge_graph.py"),
                            "Graph support currently lacks a durable query plane.",
                            ("Interfaces specify persistence, query, and provenance fields.", "Fallback graph behavior remains covered."),
                            ("python -m pytest tests/test_complaint_phases.py tests/test_ipfs_adapter_layer.py -q",),
                        ),
                        _task(
                            "G3",
                            "G3.S2",
                            "Turn not_implemented logic paths into explicit capability-gated contracts",
                            "P1",
                            ("integrations/ipfs_datasets/logic.py", "lib/formal_logic"),
                            "Formal validation should fail predictably when unavailable.",
                            ("Logic status distinguishes unavailable, degraded, and implemented.", "Callers do not branch on fragile strings."),
                            ("python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G4",
            "title": "Improve validation speed and confidence",
            "priority": "P1",
            "subgoals": [
                {
                    "id": "G4.S1",
                    "title": "Create focused test lanes for refactor work",
                    "tasks": [
                        _task(
                            "G4",
                            "G4.S1",
                            "Define smoke, adapter, mediator, document, and UI test lanes",
                            "P1",
                            ("pytest.ini", "Makefile", "docs/VERIFICATION_SUMMARY.md"),
                            "The repo has many tests; refactor agents need fast confidence lanes.",
                            ("A documented test lane map exists.", "Each P0 workstream has a named validation command."),
                            ("python -m pytest --collect-only -q",),
                        ),
                        _task(
                            "G4",
                            "G4.S1",
                            "Add import and dependency-boundary tests for production modules",
                            "P1",
                            ("tests", "pyproject.toml"),
                            "Dependency drift is a recurring refactor risk.",
                            ("Tests catch direct production imports where adapters are required.", "Tests avoid blocking intentional test-only imports."),
                            ("python -m pytest tests/test_package_imports.py -q",),
                        ),
                    ],
                }
            ],
        },
        {
            "id": "G5",
            "title": "Make automation observable and refillable",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G5.S1",
                    "title": "Operate a durable refactor taskboard",
                    "tasks": [
                        _task(
                            "G5",
                            "G5.S1",
                            "Keep the refactor taskboard synchronized with generated goals and subgoals",
                            "P0",
                            ("scripts/refactor_agent_supervisor.py", "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"),
                            "The requested supervisor needs a refill loop and visible board state.",
                            ("Queued task count is maintained above the configured floor.", "Docs and JSON state are regenerated each cycle."),
                            ("python scripts/refactor_agent_supervisor.py seed --once",),
                        ),
                        _task(
                            "G5",
                            "G5.S1",
                            "Record supervisor status, scan metrics, and queue counts for handoff",
                            "P0",
                            ("data/refactor_supervisor",),
                            "Long-running automation needs inspectable state and a clean stop path.",
                            ("Status JSON includes pid, heartbeat, scan summary, and counts.", "Stop command terminates the daemon cleanly."),
                            ("python scripts/refactor_agent_supervisor.py status",),
                        ),
                    ],
                }
            ],
        },
        {
            "id": "G6",
            "title": "Pay down error-handling and observability debt",
            "priority": "P1",
            "subgoals": [
                {
                    "id": "G6.S1",
                    "title": "Replace silent failures with typed outcomes",
                    "tasks": [
                        _task(
                            "G6",
                            "G6.S1",
                            "Audit broad exception handlers in mediator and adapter paths",
                            "P1",
                            ("mediator/mediator.py", "mediator/evidence_hooks.py", "integrations/ipfs_datasets/search.py"),
                            "The scan found many broad exception handlers; refactors need predictable failure semantics.",
                            ("Top production broad-exception clusters are documented.", "At least one cluster returns a typed degraded result."),
                            ("python -m pytest tests/test_mediator.py tests/test_ipfs_adapter_layer.py -q",),
                        ),
                        _task(
                            "G6",
                            "G6.S1",
                            "Convert silent pass blocks in user-facing workflows into debug logs or explicit fallbacks",
                            "P1",
                            ("applications/ui_review.py", "complaint_generator/ui_optimizer_daemon.py", "mediator/state.py"),
                            "Silent failures hide regressions during long-running automation.",
                            ("Intentional ignores are named.", "Unexpected failures leave diagnostic breadcrumbs."),
                            ("python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_review_api.py -q",),
                        ),
                    ],
                },
                {
                    "id": "G6.S2",
                    "title": "Unify runtime status payloads",
                    "tasks": [
                        _task(
                            "G6",
                            "G6.S2",
                            "Standardize daemon status payload shape across UI, scraper, Gmail, and refactor supervisors",
                            "P1",
                            ("complaint_generator/ui_optimizer_daemon.py", "integrations/ipfs_datasets/scraper_daemon.py", "scripts/gmail_duckdb_daemon.py"),
                            "Multiple daemon surfaces should be inspectable with the same status fields.",
                            ("Status payloads include status, pid, updated_at, artifacts, and last_error where applicable.", "Existing CLI tests remain compatible."),
                            ("python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_gmail_duckdb_daemon_cli.py -q",),
                        ),
                        _task(
                            "G6",
                            "G6.S2",
                            "Add queue count and last-cycle metrics to long-running automation docs",
                            "P2",
                            ("docs/OBSERVABILITY_INDEX.md", "docs/observability/TROUBLESHOOTING.md"),
                            "Operators need consistent guidance for stalled background workflows.",
                            ("Docs explain where to find pid, log, status, and queue files.", "Troubleshooting includes stale running task recovery."),
                            ("python scripts/refactor_agent_supervisor.py status",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G7",
            "title": "Rationalize frontend and review surfaces",
            "priority": "P1",
            "subgoals": [
                {
                    "id": "G7.S1",
                    "title": "Separate review API contracts from display assembly",
                    "tasks": [
                        _task(
                            "G7",
                            "G7.S1",
                            "Move review payload normalization behind explicit DTO helpers",
                            "P1",
                            ("applications/review_api.py", "applications/ui_review.py", "mediator/claim_support_hooks.py"),
                            "Review screens depend on stable payloads that should not be assembled ad hoc in route handlers.",
                            ("DTO helpers cover coverage, follow-up, and support-path summaries.", "Route response snapshots stay stable."),
                            ("python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py -q",),
                        ),
                        _task(
                            "G7",
                            "G7.S1",
                            "Create fixture builders for Playwright review and dashboard smoke tests",
                            "P1",
                            ("tests/test_claim_support_review_playwright_smoke.py", "tests/test_review_surface_site_playwright.py"),
                            "Large Playwright tests should share fixture setup before UI refactors.",
                            ("Shared builders remove repeated setup.", "Screenshots still render with representative support states."),
                            ("python -m pytest tests/test_claim_support_review_playwright_smoke.py tests/test_review_surface_site_playwright.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G8",
            "title": "Prepare incremental implementation slices",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G8.S1",
                    "title": "Convert existing roadmaps into executable slices",
                    "tasks": [
                        _task(
                            "G8",
                            "G8.S1",
                            "Cross-link IPFS datasets execution backlog tasks to refactor supervisor goals",
                            "P0",
                            ("docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md", "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"),
                            "Existing roadmap work should feed the automated taskboard rather than drift separately.",
                            ("Each P0 backlog workstream maps to at least one refactor goal.", "Duplicated tasks are merged or explicitly scoped."),
                            ("python scripts/refactor_agent_supervisor.py seed --once",),
                        ),
                        _task(
                            "G8",
                            "G8.S1",
                            "Define first three implementation claims from the queued taskboard",
                            "P0",
                            ("data/refactor_supervisor/refactor_goals.json",),
                            "A robust board still needs a practical starting order.",
                            ("The first three claims are small, testable, and dependency-ordered.", "Each claim names exact validation commands."),
                            ("python scripts/refactor_agent_supervisor.py status",),
                        ),
                    ],
                },
                {
                    "id": "G8.S2",
                    "title": "Keep generated artifacts reviewable",
                    "tasks": [
                        _task(
                            "G8",
                            "G8.S2",
                            "Add a taskboard inspection command that prints queued refactor tasks compactly",
                            "P1",
                            ("scripts/refactor_agent_supervisor.py",),
                            "Agents need a simple way to see the next work without opening DuckDB manually.",
                            ("Status output or a new command lists next tasks by priority.", "Output is stable enough for automation."),
                            ("python scripts/refactor_agent_supervisor.py status",),
                        ),
                        _task(
                            "G8",
                            "G8.S2",
                            "Create tests for refactor supervisor seed idempotence and task payload schema",
                            "P1",
                            ("tests/test_refactor_agent_supervisor.py", "scripts/refactor_agent_supervisor.py"),
                            "The supervisor itself should not duplicate tasks or emit malformed payloads.",
                            ("Running seed twice does not duplicate active tasks.", "Payloads include goal, subgoal, priority, acceptance, and validation."),
                            ("python -m pytest tests/test_refactor_agent_supervisor.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G9",
            "title": "Increase agent-supervisor planning quality and throughput",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G9.S1",
                    "title": "Establish canonical coordination and merge flow",
                    "tasks": [
                        _task(
                            "G9",
                            "G9.S1",
                            "Introduce canonical task identity and a durable supervisor task ledger",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py",
                            ),
                            "Bundle-local numeric task ids currently collide across boards and make global reconciliation ambiguous.",
                            (
                                "Every task has a stable canonical key or CID independent of board path and display id.",
                                "Legacy markdown tasks migrate idempotently with board namespace provenance.",
                                "Branches, events, retries, cooldowns, leases, and receipts carry canonical identity.",
                                "Refill cannot create a second active task for the same canonical work item.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q",
                            ),
                            task_id="REF-036",
                        ),
                        _task(
                            "G9",
                            "G9.S1",
                            "Replace static bundle launch with a dynamic leased worker pool",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py",
                            ),
                            "The current bundle supervisor starts the first N lexical bundles once and cannot reclaim idle lanes or discover refilled work.",
                            (
                                "A persistent scheduler discovers new and refilled tasks without restart.",
                                "Workers claim ready tasks, release drained or blocked leases, and steal conflict-safe work.",
                                "Lane count remains within configured capacity and no task executes under two accepted leases.",
                                "The manifest is an authoritative live projection rather than a launch-time snapshot.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q",
                            ),
                            task_id="REF-037",
                            depends_on=("REF-036",),
                        ),
                        _task(
                            "G9",
                            "G9.S1",
                            "Integrate a deduplicating single-consumer merge train",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py",
                            ),
                            "Independent lanes currently race to merge and repeatedly retry the same failed branches.",
                            (
                                "All implementation lanes enqueue merge candidates instead of racing the target checkout.",
                                "The train deduplicates by canonical task and commit, rebases on the latest target, and preserves priority plus age fairness.",
                                "One conflict fingerprint invokes at most one active resolver attempt.",
                                "Bounded failures enter quarantine with a durable receipt instead of a polling retry loop.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q",
                            ),
                            task_id="REF-038",
                            depends_on=("REF-037",),
                        ),
                    ],
                },
                {
                    "id": "G9.S2",
                    "title": "Plan from dependencies, conflicts, and objective value",
                    "tasks": [
                        _task(
                            "G9",
                            "G9.S2",
                            "Materialize a task dependency DAG and schedule its critical path",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py",
                            ),
                            "Goal parents are currently sorting hints while generated Profile G tasks carry no dependency task CIDs.",
                            (
                                "Goal, import, interface, output-input, migration, and validation prerequisites become explicit DAG edges with provenance.",
                                "Only tasks whose prerequisite merge receipts succeeded are claimable.",
                                "Priority includes critical-path length, slack, downstream unlock value, age, and configured objective priority.",
                                "Cycles and missing dependencies produce bounded repair evidence rather than deadlock.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q",
                            ),
                            task_id="REF-039",
                            depends_on=("REF-037",),
                        ),
                        _task(
                            "G9",
                            "G9.S2",
                            "Build an AST and changed-path conflict graph for lane coloring",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py",
                            ),
                            "The current conflict domain uses one path root and lightweight semantic similarity, which misses multi-file and symbol overlap.",
                            (
                                "Conflict surfaces include all predicted files, AST symbols, interfaces, submodules, and generated artifacts.",
                                "Lane planning colors the conflict graph so overlapping tasks do not run concurrently unless explicitly allowed.",
                                "Actual branch diffs and conflict receipts update future conflict weights.",
                                "Planner output explains every co-location or separation decision.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q",
                            ),
                            task_id="REF-040",
                            depends_on=("REF-039",),
                        ),
                        _task(
                            "G9",
                            "G9.S2",
                            "Use llm_router to generate and evaluate structured plan branches",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py",
                            ),
                            "Profile G currently records a single constant-scored plan branch and the LLM proposal router is not part of scheduler decisions.",
                            (
                                "Each eligible subgoal can produce multiple schema-validated plan branches through llm_router.",
                                "Candidates declare predicted files and symbols, dependencies, validation proof, cost, risk, and expected objective delta.",
                                "A deterministic evaluator selects a branch and retains rejected alternatives plus rationale.",
                                "Router failure falls back to deterministic planning without blocking ready work.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q",
                            ),
                            task_id="REF-041",
                            depends_on=("REF-039",),
                        ),
                        _task(
                            "G9",
                            "G9.S2",
                            "Recover structured plan branch implementation in the nested supervisor",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py",
                            ),
                            "REF-041 validated nested changes in a lane that did not forward managed submodule paths, so its root merge recorded only taskboard documentation.",
                            (
                                "The structured plan router, evaluator, objective-daemon integration, and focused tests are tracked in the nested ipfs_accelerate_py repository.",
                                "Selected and rejected branches remain visible to the scheduler with deterministic fallback when llm_router fails.",
                                "The implementation receipt records nested commits and the parent gitlink chain instead of completing from documentation alone.",
                                "A prior lane state cannot settle the recovery generation unless its recorded task identities include REF-063.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q",
                            ),
                            task_id="REF-063",
                            depends_on=("REF-041",),
                        ),
                    ],
                },
                {
                    "id": "G9.S3",
                    "title": "Adapt execution capacity and validation cost",
                    "tasks": [
                        _task(
                            "G9",
                            "G9.S3",
                            "Schedule lanes from live resources and llm_router provider capacity",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py",
                            ),
                            "Resource class, capability fit, and lane capacity are currently static even when workers are idle or providers are rate-limited.",
                            (
                                "Heartbeats report measured CPU, memory, disk, active phase, and available worker capacity.",
                                "Scheduler honors llm_router health, quota, latency, context, and token-budget constraints.",
                                "Concurrency scales within configured limits and applies backpressure before provider or host exhaustion.",
                                "Idle lanes advertise zero occupied capacity and can be reassigned.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py -q",
                            ),
                            task_id="REF-042",
                            depends_on=("REF-037", "REF-041"),
                        ),
                        _task(
                            "G9",
                            "G9.S3",
                            "Add impact-selected cached and parallel validation stages",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py",
                            ),
                            "Validation commands currently run serially without changed-file impact selection or reusable baseline results.",
                            (
                                "Cheap deterministic checks run before expensive tests and fail fast.",
                                "Independent validations run in parallel under a bounded resource budget.",
                                "Cache keys include target commit, command, relevant environment, and dependency state.",
                                "Impact selection is conservative, explainable, and escalates to broader validation before merge completion.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py -q",
                            ),
                            task_id="REF-043",
                            depends_on=("REF-038",),
                        ),
                    ],
                },
                {
                    "id": "G9.S4",
                    "title": "Close the scheduler feedback and lifecycle loop",
                    "tasks": [
                        _task(
                            "G9",
                            "G9.S4",
                            "Publish authoritative throughput metrics and scheduler state",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py",
                            ),
                            "Status is split across launch manifests, wrapper files, lane state, and event logs, so planners cannot measure useful capacity.",
                            (
                                "One event-derived snapshot reports ready, active, idle, blocked, validation, merge, and resolver phases.",
                                "Metrics include queue wait, implementation and validation duration, merge wait, conflict and retry rate, completions, tokens, and cost.",
                                "Every metric is keyed by canonical goal, subgoal, task, lane, and provider identity.",
                                "Scheduler decisions consume the same snapshot exposed to operators.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py -q",
                            ),
                            task_id="REF-044",
                            depends_on=("REF-037", "REF-038", "REF-039"),
                        ),
                        _task(
                            "G9",
                            "G9.S4",
                            "Make AST scans and implementation workspaces incremental and reusable",
                            "P2",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py",
                            ),
                            "Refill scans reread the tracked codebase and each implementation creates fresh worktree and submodule setup even when inputs are unchanged.",
                            (
                                "AST and evidence records are reused by blob hash and only changed files are reparsed.",
                                "Deleted and renamed files invalidate stale evidence deterministically.",
                                "Clean worktrees and dependency setups can be pooled without sharing task-local mutations.",
                                "Cold and warm paths produce equivalent plans and validation results with measured warm-path savings.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q",
                            ),
                            task_id="REF-045",
                            depends_on=("REF-040", "REF-042", "REF-043", "REF-044"),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G10",
            "title": "Make goal completion evidence-backed and analyzer-auditable",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G10.S1",
                    "title": "Distinguish every refill and analysis outcome",
                    "tasks": [
                        _task(
                            "G10",
                            "G10.S1",
                            "Define a typed refill scan result and terminal reason taxonomy",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py",
                            ),
                            "Refill callbacks currently collapse skipped, deduplicated, exhausted, failed, and timed-out scans into the same empty collection.",
                            (
                                "A versioned result contract distinguishes generated, exhausted, duplicate-only, threshold-satisfied, cooldown, disabled, partial, failed, and timed-out outcomes.",
                                "The contract records scan mode, analyzer version, repository and tree identity, start and finish timestamps, and whether the result is safe for completion reasoning.",
                                "Legacy list-returning callbacks remain supported through an explicit compatibility adapter rather than implicit truthiness.",
                                "No empty result is interpreted as goal completion without a typed terminal reason.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py -q",
                            ),
                            task_id="REF-200",
                        ),
                        _task(
                            "G10",
                            "G10.S1",
                            "Instrument scan inventory, parser coverage, exclusions, and candidate accounting",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py",
                            ),
                            "A zero novel-finding count is not diagnosable without knowing what the analyzer discovered, parsed, skipped, rejected, or failed to inspect.",
                            (
                                "Receipts count git roots, tracked files, eligible files, parsed files, cache hits, excluded files, parser failures, raw candidates, seen candidates, deduplicated candidates, and appended tasks.",
                                "Every skipped file and parser failure has a bounded reason code plus representative paths, with full details available as a durable artifact.",
                                "Candidate accounting balances from raw detection through filtering and task materialization.",
                                "Incremental and exhaustive scans report equivalent coverage dimensions.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q",
                            ),
                            task_id="REF-201",
                            depends_on=("REF-200",),
                        ),
                        _task(
                            "G10",
                            "G10.S1",
                            "Persist scan receipts in events, strategy state, status, and scheduler metrics",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/implementation_supervisor_runner.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py",
                            ),
                            "Operators and schedulers currently see only refill counts, so they cannot distinguish healthy exhaustion from an analyzer failure.",
                            (
                                "Each refill attempt emits one canonical receipt CID and a compact event projection regardless of outcome.",
                                "Strategy and status payloads expose the latest successful scan, latest attempted scan, terminal reason, freshness, health, and candidate funnel.",
                                "Large per-file details are referenced by artifact path or CID rather than embedded repeatedly in heartbeat files.",
                                "Metrics distinguish skipped, duplicate-only, exhausted, partial, and failed scans without breaking older consumers.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py -q",
                            ),
                            task_id="REF-202",
                            depends_on=("REF-200",),
                        ),
                    ],
                },
                {
                    "id": "G10.S2",
                    "title": "Prove analyzer health and genuine exhaustion",
                    "tasks": [
                        _task(
                            "G10",
                            "G10.S2",
                            "Add analyzer canaries, parser failure budgets, and fail-closed health classification",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/analyzer_health.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analyzer_health.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py",
                            ),
                            "A scanner that silently stops recognizing syntax can otherwise report the same zero findings as a complete repository.",
                            (
                                "Deterministic fixtures exercise every supported finding kind and parser path on each analyzer version.",
                                "Missing canaries, excessive skips, parser failures, incomplete git-root discovery, and impossible candidate funnels classify the scan as unhealthy or partial.",
                                "Health thresholds are configurable, recorded in the receipt, and cannot silently downgrade a failed scan to exhausted.",
                                "The daemon continues safe implementation work while preventing unhealthy analysis from closing goals.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analyzer_health.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py -q",
                            ),
                            task_id="REF-203",
                            depends_on=("REF-201",),
                        ),
                        _task(
                            "G10",
                            "G10.S2",
                            "Implement fingerprint-independent audit scans and exhaustion quorum",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_audit_scanner.py",
                            ),
                            "A saturated or corrupt seen-fingerprint set can make normal refill scans appear exhausted without independently re-evaluating the codebase.",
                            (
                                "Audit mode scans without mutating or trusting the normal seen set and reports known, stale, changed, and novel findings separately.",
                                "Exhaustion requires a configurable quorum of healthy exhaustive receipts tied to repository tree, analyzer version, configuration, and objective revision.",
                                "Relevant code, configuration, analyzer, or objective changes invalidate prior quorum members deterministically.",
                                "Repeated scans of an unchanged tree are deduplicated and cannot manufacture quorum confidence.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_audit_scanner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q",
                            ),
                            task_id="REF-204",
                            depends_on=("REF-201", "REF-202"),
                        ),
                        _task(
                            "G10",
                            "G10.S2",
                            "Escalate low-backlog analysis through AST and llm_router planning before declaring exhaustion",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/analyzer_health.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analysis_escalation.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py",
                            ),
                            "Static pattern exhaustion should trigger bounded semantic and goal-directed analysis rather than leave the board below its configured floor without explanation.",
                            (
                                "A policy escalates from incremental static scan to exhaustive AST coverage and then schema-constrained llm_router proposals when healthy backlog remains below target.",
                                "Each escalation records cost, scope, novelty, confidence, rejected candidates, and the objective terms it attempted to cover.",
                                "Router failure or low-confidence output produces an analysis-inconclusive result and deterministic fallback, never a false completion.",
                                "Rate, token, retry, and novelty limits prevent an unbounded task-generation loop.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analysis_escalation.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q",
                            ),
                            task_id="REF-205",
                            depends_on=("REF-203", "REF-204"),
                        ),
                    ],
                },
                {
                    "id": "G10.S3",
                    "title": "Gate goal completion on fresh evidence and coverage",
                    "tasks": [
                        _task(
                            "G10",
                            "G10.S3",
                            "Define an evidence-backed goal lifecycle and completion state machine",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_tracker.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py",
                            ),
                            "The objective graph currently treats completed task statuses as sufficient even when completion evidence and validation receipts are absent.",
                            (
                                "Goals distinguish active, provisionally complete, verified complete, analysis inconclusive, blocked, and reopened states with legal transitions.",
                                "Completion evidence names acceptance criterion, producing task or scan, validation receipt, repository tree, freshness, and provenance CID.",
                                "Task completion alone can make a goal provisional but cannot make it verified.",
                                "Missing, stale, failed, or contradictory evidence fails closed with an actionable reason.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q",
                            ),
                            task_id="REF-206",
                            depends_on=("REF-200",),
                        ),
                        _task(
                            "G10",
                            "G10.S3",
                            "Build goal-to-task, code, AST, acceptance, and validation coverage maps",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_coverage.py",
                            ),
                            "Goal completion cannot be assessed when acceptance criteria are not mapped to implementation surfaces and proof-producing validations.",
                            (
                                "Every acceptance criterion maps to tasks, predicted and changed files, AST symbols or interfaces, validation commands, and resulting receipts with provenance.",
                                "The graph reports uncovered, weakly inferred, stale, contradicted, and verified surfaces separately.",
                                "Dynamic codebase findings attach to the most relevant registered goals while preserving a clearly labeled unmapped bucket.",
                                "Coverage calculations are deterministic and explain the evidence behind each edge.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_coverage.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q",
                            ),
                            task_id="REF-207",
                            depends_on=("REF-201", "REF-206"),
                        ),
                        _task(
                            "G10",
                            "G10.S3",
                            "Enforce a completion gate using validation, coverage, health, freshness, and exhaustion proof",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_task_janitor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py",
                            ),
                            "Goal reconciliation must require proof of the stated objective rather than infer success from a drained or deduplicated task list.",
                            (
                                "Verified completion requires all mandatory acceptance criteria covered, required validations successful, evidence fresh, analyzer healthy, and configured exhaustion quorum satisfied.",
                                "Partial, skipped, failed, timed-out, duplicate-only, or unsupported analysis cannot satisfy the gate.",
                                "The gate emits machine-readable pass and fail reasons plus the exact evidence set it evaluated.",
                                "Parent goals aggregate child proof without hiding an inconclusive or reopened descendant.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py -q",
                            ),
                            task_id="REF-208",
                            depends_on=("REF-204", "REF-207"),
                        ),
                        _task(
                            "G10",
                            "G10.S3",
                            "Detect contradictory evidence and automatically reopen affected goals",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_task_janitor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py",
                            ),
                            "A completed goal currently remains completed even when a later codebase scan creates directly relevant work or validation regresses.",
                            (
                                "Novel mapped findings, failed required validations, changed evidence surfaces, and invalidated audit receipts reopen verified or provisional goals deterministically.",
                                "Reopening records the contradiction, impacted criteria, invalidated evidence, source receipt, and newly scheduled work.",
                                "Unrelated findings do not churn completed goals, and repeated identical contradictions are idempotent.",
                                "Parent and dependent goal states are recalculated without erasing historical completion receipts.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py -q",
                            ),
                            task_id="REF-209",
                            depends_on=("REF-208",),
                        ),
                    ],
                },
                {
                    "id": "G10.S4",
                    "title": "Close the autonomous goal-management loop",
                    "tasks": [
                        _task(
                            "G10",
                            "G10.S4",
                            "Generate bounded goals, subgoals, and tasks from uncovered or inconclusive evidence",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_generation.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py",
                            ),
                            "Uncovered acceptance criteria and inconclusive analysis should become reviewable, dependency-linked work instead of silently draining the board.",
                            (
                                "Deterministic rules and llm_router proposals can create bounded child goals, subgoals, and tasks from uncovered criteria, unsupported surfaces, or contradiction receipts.",
                                "Generated work records parent objective terms, expected evidence delta, dependencies, predicted files and symbols, validation, confidence, cost, and novelty.",
                                "Canonical identity and semantic deduplication prevent equivalent goals or tasks from being regenerated across cycles.",
                                "Depth, breadth, token, retry, and open-work limits keep autonomous refinement finite and scheduler-aware.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_generation.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q",
                            ),
                            task_id="REF-210",
                            depends_on=("REF-205", "REF-207", "REF-209"),
                        ),
                        _task(
                            "G10",
                            "G10.S4",
                            "Migrate existing goals and expose trustworthy completion diagnostics",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_tracker.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/implementation_supervisor_runner.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py",
                            ),
                            "Existing completed goals need a safe migration path and operators need to see confidence and missing proof without reading raw event logs.",
                            (
                                "Legacy completed goals migrate idempotently to provisional or verified state based on available evidence, never by optimistic default.",
                                "Status and manifest projections show lifecycle state, confidence, uncovered criteria, stale evidence, analyzer health, exhaustion quorum, and reopen reasons.",
                                "Schema versioning and compatibility readers preserve existing boards, events, and automation during rollout.",
                                "The migration can be previewed and resumed safely after interruption.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py -q",
                            ),
                            task_id="REF-211",
                            depends_on=("REF-202", "REF-206", "REF-208", "REF-209", "REF-210"),
                        ),
                        _task(
                            "G10",
                            "G10.S4",
                            "Add end-to-end regression tests for truthful goal completion and autonomous refill",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_lifecycle_e2e.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py",
                            ),
                            "The completion and refill contract needs system-level regression coverage across restart, concurrency, stale evidence, analyzer failure, and contradiction scenarios.",
                            (
                                "Tests distinguish threshold skip, cooldown, duplicate-only, healthy exhaustion, parser failure, timeout, partial coverage, and successful generation.",
                                "Scenarios prove that stale fingerprints cannot certify completion and that later relevant findings reopen goals and refill the board.",
                                "Concurrent serial and bundle supervisors emit one canonical receipt and do not duplicate generated goals or tasks.",
                                "Restart and migration preserve evidence lineage, quorum state, dependencies, and truthful operator projections.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_lifecycle_e2e.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py -q",
                            ),
                            task_id="REF-212",
                            depends_on=("REF-203", "REF-204", "REF-205", "REF-208", "REF-209", "REF-210", "REF-211"),
                        ),
                    ],
                },
            ],
        },
        *_formal_verification_goals(),
        *_formal_planning_goals(),
    ]


def _task(
    goal_id: str,
    subgoal_id: str,
    title: str,
    priority: str,
    files: tuple[str, ...],
    rationale: str,
    acceptance: tuple[str, ...],
    validation: tuple[str, ...],
    *,
    task_id: str = "",
    depends_on: tuple[str, ...] = (),
) -> RefactorTask:
    clean_files = tuple(dict.fromkeys(f for f in files if f))
    clean_dependencies = tuple(dict.fromkeys(item for item in depends_on if item))
    return RefactorTask(
        goal_id,
        subgoal_id,
        title,
        priority,
        clean_files,
        rationale,
        acceptance,
        validation,
        task_id,
        clean_dependencies,
    )


def _formal_verification_goals() -> list[dict[str, Any]]:
    """Return the proof-aware supervisor implementation program.

    The goal is kept in one helper because its tasks form an independently
    reviewable dependency graph and intentionally live in the nested
    ``ipfs_accelerate_py`` repository.
    """

    module_root = (
        "ipfs_datasets_py/ipfs_accelerate_py/"
        "ipfs_accelerate_py/agent_supervisor"
    )
    test_root = "ipfs_datasets_py/ipfs_accelerate_py/test/api"
    plan_path = (
        "ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/"
        "AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md"
    )

    def module(name: str) -> str:
        return f"{module_root}/{name}"

    def test(name: str) -> str:
        return f"{test_root}/test_agent_supervisor_{name}.py"

    def validate(name: str) -> tuple[str, ...]:
        return (
            "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py "
            f"python -m pytest {test(name)} -q",
        )

    return [
        {
            "id": "G11",
            "title": "Make agent-supervisor proof-aware and context-efficient",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G11.S1",
                    "title": "Establish proof contracts, capabilities, and trust policy",
                    "tasks": [
                        _task(
                            "G11",
                            "G11.S1",
                            "Probe formal-logic providers, toolchains, and optional dependency health",
                            "P0",
                            (
                                plan_path,
                                module("formal_verification_capabilities.py"),
                                test("formal_verification_capabilities"),
                            ),
                            "The supervisor needs a truthful runtime capability matrix before it can route or require proof work.",
                            (
                                "A versioned capability report covers Hammer, TDFOL, external provers, Lean, Leanstral, frame logic, knowledge graphs, and ZKP backends.",
                                "Provider, executable, package, model, circuit, and optional dependency health are reported separately.",
                                "Missing spaCy, model weights, Python bindings, or prover executables produce explicit degraded or unavailable reasons without breaking supervisor import.",
                                "Capability probes are bounded, cacheable, and never count availability as proof success.",
                            ),
                            validate("formal_verification_capabilities"),
                            task_id="REF-244",
                        ),
                        _task(
                            "G11",
                            "G11.S1",
                            "Define canonical proof obligations, plans, receipts, and assurance levels",
                            "P0",
                            (
                                module("formal_verification_contracts.py"),
                                test("formal_verification_contracts"),
                            ),
                            "Proof-aware scheduling needs one versioned contract and a sound trust lattice shared by providers, caches, merge gates, and goal evidence.",
                            (
                                "CodeProofObligation, ProofPlan, ProofAttempt, ProofReceipt, and assurance enums have deterministic JSON encodings and content identities.",
                                "Receipts bind repository trees, AST scopes, premises, translators, solvers, kernels, toolchains, policy, and resource budgets.",
                                "Authoritative assurance is derived from evidence and cannot be asserted directly by a provider.",
                                "LLM output, ATP or SMT candidates, stale cache entries, and simulated ZKP cannot become kernel-verified or attested.",
                            ),
                            validate("formal_verification_contracts"),
                            task_id="REF-245",
                        ),
                        _task(
                            "G11",
                            "G11.S1",
                            "Introduce an optional isolated proof-provider protocol",
                            "P0",
                            (
                                module("formal_verification_provider.py"),
                                module("formal_verification_capabilities.py"),
                                test("formal_verification_provider"),
                            ),
                            "A mandatory import from the acceleration submodule into its parent datasets package would create a brittle package and submodule cycle.",
                            (
                                "A versioned provider protocol supports capability, translate, prove, reconstruct, verify, and attest operations.",
                                "Providers can be discovered lazily in process or invoked through a bounded subprocess JSON protocol.",
                                "Timeout, cancellation, resource, network, and malformed-response failures are explicit and fail closed.",
                                "The supervisor imports and runs with no ipfs_datasets_py proof provider installed.",
                            ),
                            validate("formal_verification_provider"),
                            task_id="REF-246",
                            depends_on=("REF-244", "REF-245"),
                        ),
                        _task(
                            "G11",
                            "G11.S1",
                            "Define risk-selected proof and rollout policy",
                            "P0",
                            (
                                module("formal_verification_policy.py"),
                                test("formal_verification_policy"),
                            ),
                            "Formal verification should protect modeled high-risk invariants without blocking unrelated or unsupported Python changes.",
                            (
                                "Policy maps changed paths, AST scopes, risk, and invariant classes to required assurance and fallback validation.",
                                "Disabled, shadow, canary, and enforcement modes have explicit promotion and override behavior.",
                                "Unsupported, unavailable, timed-out, and inconclusive results cannot silently satisfy an enforcement gate.",
                                "Overrides require bounded scope, actor, reason, expiration, and a durable receipt.",
                            ),
                            validate("formal_verification_policy"),
                            task_id="REF-247",
                            depends_on=("REF-245",),
                        ),
                    ],
                },
                {
                    "id": "G11.S2",
                    "title": "Compile AST changes into obligations and bounded graph context",
                    "tasks": [
                        _task(
                            "G11",
                            "G11.S2",
                            "Compile candidate diffs into typed AST proof scopes",
                            "P0",
                            (
                                module("code_proof_obligations.py"),
                                module("conflict_graph.py"),
                                test("code_proof_scopes"),
                            ),
                            "Proof planning must start from deterministic changed symbols and contracts rather than sending repository-wide source or AST records to a model.",
                            (
                                "Python diffs produce qualified symbols, imports, calls, state transitions, interfaces, source hashes, and changed-path scopes.",
                                "Renames, deletes, generated files, syntax failures, and non-Python changes have explicit conservative handling.",
                                "Scopes reuse existing AST and conflict-graph records by blob identity.",
                                "Equivalent cold and warm scans produce the same canonical scope identities.",
                            ),
                            validate("code_proof_scopes"),
                            task_id="REF-248",
                            depends_on=("REF-245",),
                        ),
                        _task(
                            "G11",
                            "G11.S2",
                            "Build a reviewed code-invariant obligation template registry",
                            "P0",
                            (
                                module("proof_obligation_templates.py"),
                                module("code_proof_obligations.py"),
                                test("proof_obligation_templates"),
                            ),
                            "Arbitrary Python cannot be made formally verified by translating free-form model claims; enforcement needs reviewed templates with explicit semantics.",
                            (
                                "Initial templates cover legal state transitions, lease uniqueness and fencing, DAG acyclicity, merge idempotence, cache-key completeness, evidence freshness, projection equivalence, and unsupported-proof fail-closed behavior.",
                                "Every template declares a Python reference predicate, canonical statement, supported backends, assumptions, mutation cases, and fallback tests.",
                                "Template versions and semantic hashes participate in obligation and cache identity.",
                                "Unknown or ambiguous code shapes remain unsupported instead of selecting a similar template heuristically.",
                            ),
                            validate("proof_obligation_templates"),
                            task_id="REF-249",
                            depends_on=("REF-247", "REF-248"),
                        ),
                        _task(
                            "G11",
                            "G11.S2",
                            "Materialize a deterministic code and proof evidence graph in JSON and DuckDB",
                            "P0",
                            (
                                module("code_evidence_graph.py"),
                                module("artifact_store.py"),
                                test("code_evidence_graph"),
                            ),
                            "Goals, tasks, symbols, obligations, attempts, receipts, validations, and merges need a query plane that does not require parsing a full graph into a model context.",
                            (
                                "The graph uses deterministic nodes and provenance edges derived from AST, task, validation, merge, and proof records.",
                                "Paired JSON and DuckDB artifacts expose indexed task, tree, symbol, obligation, assurance, freshness, and dependency queries.",
                                "JSON and DuckDB projections round-trip to equivalent canonical graph records.",
                                "LLM or GraphRAG enrichment cannot create authoritative proof, merge, coverage, or completion edges.",
                            ),
                            validate("code_evidence_graph"),
                            task_id="REF-250",
                            depends_on=("REF-245", "REF-248"),
                        ),
                        _task(
                            "G11",
                            "G11.S2",
                            "Index proof scopes and invalidate stale dependent evidence incrementally",
                            "P0",
                            (
                                module("proof_scope_index.py"),
                                module("dataset_store.py"),
                                test("proof_scope_index"),
                            ),
                            "Proof reuse is useful only when every changed semantic input invalidates the affected obligations and receipts.",
                            (
                                "Scope indexes map files, qualified symbols, interfaces, assumptions, templates, toolchains, and policies to dependent obligations and receipts.",
                                "Blob reuse avoids reparsing unchanged scopes while deletes and renames invalidate stale records.",
                                "Invalidation is transitive across proof-plan dependencies and records a bounded reason chain.",
                                "Incremental and exhaustive rebuilds produce equivalent active evidence sets.",
                            ),
                            validate("proof_scope_index"),
                            task_id="REF-251",
                            depends_on=("REF-248", "REF-250"),
                        ),
                        _task(
                            "G11",
                            "G11.S2",
                            "Generate bounded proof context capsules for Codex and Leanstral",
                            "P0",
                            (
                                module("proof_context.py"),
                                module("artifact_store.py"),
                                test("proof_context"),
                            ),
                            "Models should receive only task-relevant invariants, trusted prior evidence, counterexamples, and source excerpts.",
                            (
                                "Context queries select exact task, symbol, dependency, obligation, receipt, and contradiction neighborhoods.",
                                "Row, byte, token, graph-hop, source-excerpt, and proof-transcript limits are enforced before prompt assembly.",
                                "Capsules distinguish trusted facts, untrusted suggestions, unsupported semantics, and required fallback checks.",
                                "Repository-wide AST records, full graphs, hidden witnesses, and unrelated transcripts never enter a capsule.",
                            ),
                            validate("proof_context"),
                            task_id="REF-252",
                            depends_on=("REF-249", "REF-250", "REF-251"),
                        ),
                    ],
                },
                {
                    "id": "G11.S3",
                    "title": "Integrate Hammer, kernel reconstruction, and trusted caching",
                    "tasks": [
                        _task(
                            "G11",
                            "G11.S3",
                            "Adapt code obligations to the ipfs_datasets_py Hammer portfolio",
                            "P0",
                            (
                                module("ipfs_datasets_logic_provider.py"),
                                module("formal_verification_provider.py"),
                                test("ipfs_datasets_logic_provider"),
                            ),
                            "The mature Hammer portfolio should be consumed through the provider boundary rather than copied into the supervisor.",
                            (
                                "Supported obligations translate deterministically into Hammer requests with explicit premises and environment locks.",
                                "Solver allowlists, timeouts, CPU, memory, network denial, and maximum premise counts flow from supervisor policy.",
                                "Portfolio attempts and candidate proofs preserve upstream receipt provenance.",
                                "Unsupported translation families return a typed unsupported result and configured fallback checks.",
                            ),
                            validate("ipfs_datasets_logic_provider"),
                            task_id="REF-253",
                            depends_on=("REF-246", "REF-249"),
                        ),
                        _task(
                            "G11",
                            "G11.S3",
                            "Add trust-aware proof caching and single-flight execution",
                            "P0",
                            (
                                module("formal_verification_cache.py"),
                                module("ipfs_datasets_logic_provider.py"),
                                test("formal_verification_cache"),
                            ),
                            "Parallel lanes must reuse sound results without executing the same expensive obligation or trusting a stale or weaker cache entry.",
                            (
                                "Cache keys bind obligation, premises, translator, solver, kernel, toolchain, theorem registry, policy, resource budget, and candidate tree.",
                                "Only results meeting the requested assurance and freshness can satisfy a lookup.",
                                "A cross-thread and cross-process single-flight lease deduplicates active proof work.",
                                "Poisoned, malformed, stale, partial, solver-only, and simulated-attestation cache entries are rejected with reason codes.",
                            ),
                            validate("formal_verification_cache"),
                            task_id="REF-254",
                            depends_on=("REF-245", "REF-253"),
                        ),
                        _task(
                            "G11",
                            "G11.S3",
                            "Enforce independent kernel reconstruction and verdict derivation",
                            "P0",
                            (
                                module("kernel_verification.py"),
                                module("formal_verification_contracts.py"),
                                test("kernel_verification"),
                            ),
                            "A solver candidate or LLM proof draft is not formal verification until an allowed target kernel accepts the exact reconstructed obligation.",
                            (
                                "Lean, Coq, and Isabelle reconstruction records are mapped without weakening upstream trust semantics.",
                                "Kernel unavailability, timeout, mismatch, forbidden declarations, sorry or admit, and changed theorem statements fail closed.",
                                "The authoritative verdict is derived from reconstruction evidence and cannot be upgraded by provider status text.",
                                "Negative and corrupt proof fixtures never produce kernel-verified receipts.",
                            ),
                            validate("kernel_verification"),
                            task_id="REF-255",
                            depends_on=("REF-245", "REF-253"),
                        ),
                        _task(
                            "G11",
                            "G11.S3",
                            "Route counterexamples and unsupported obligations into focused validation",
                            "P0",
                            (
                                module("proof_fallbacks.py"),
                                module("validation_commands.py"),
                                test("proof_fallbacks"),
                            ),
                            "Disproved, unsupported, or inconclusive obligations should reduce model search and trigger actionable checks instead of becoming generic failures.",
                            (
                                "Counterexamples and unsat cores are normalized into bounded task diagnostics and regression fixtures.",
                                "Unsupported obligations map to declared focused tests, static checks, or manual-review requirements.",
                                "Shadow mode can continue through fallback validation while enforcement mode honors required assurance.",
                                "Repeated equivalent failures deduplicate by obligation, tree, and counterexample identity.",
                            ),
                            validate("proof_fallbacks"),
                            task_id="REF-256",
                            depends_on=("REF-247", "REF-249", "REF-255"),
                        ),
                    ],
                },
                {
                    "id": "G11.S4",
                    "title": "Schedule proof work under shared CPU budgets",
                    "tasks": [
                        _task(
                            "G11",
                            "G11.S4",
                            "Execute proof-plan DAGs with bounded parallelism and cancellation",
                            "P0",
                            (
                                module("proof_scheduler.py"),
                                module("formal_verification_contracts.py"),
                                test("proof_scheduler"),
                            ),
                            "Independent obligations should run concurrently, but proof dependencies and conclusive portfolio results must bound unnecessary work.",
                            (
                                "The scheduler executes ready proof-plan nodes in dependency order and exposes critical-path and downstream-unlock priority.",
                                "Independent translator, solver, kernel, validation, and artifact nodes can overlap within configured limits.",
                                "Conclusive results cancel redundant portfolio attempts and propagate blocked or unsupported dependencies explicitly.",
                                "Restarts recover from durable plan, lease, attempt, and receipt state without duplicate authoritative receipts.",
                            ),
                            validate("proof_scheduler"),
                            task_id="REF-257",
                            depends_on=("REF-252", "REF-253", "REF-254", "REF-255"),
                        ),
                        _task(
                            "G11",
                            "G11.S4",
                            "Unify proof, validation, model, and artifact resource admission",
                            "P0",
                            (
                                module("resource_scheduler.py"),
                                module("proof_scheduler.py"),
                                test("proof_resource_scheduler"),
                            ),
                            "Nested solver, kernel, test, and model pools can otherwise oversubscribe CPU and memory while each believes it is within its own limit.",
                            (
                                "Resource classes distinguish translation, solver, kernel, validation, model-draft, and artifact work.",
                                "One supervisor-level lease budget is propagated into child portfolio and kernel limits.",
                                "CPU, process, memory, disk, provider quota, context, token, and latency backpressure remain authoritative.",
                                "Model concurrency is accounted separately from CPU proof concurrency and idle capacity is reclaimable.",
                            ),
                            validate("proof_resource_scheduler"),
                            task_id="REF-258",
                            depends_on=("REF-244", "REF-257"),
                        ),
                        _task(
                            "G11",
                            "G11.S4",
                            "Integrate staged proof checks with the validation scheduler",
                            "P0",
                            (
                                module("validation_commands.py"),
                                module("validation_scheduler.py"),
                                module("proof_scheduler.py"),
                                test("proof_validation_scheduler"),
                            ),
                            "Proof checks and tests need one impact-selected, cached, fail-fast pipeline before merge.",
                            (
                                "Cheap deterministic checks precede translation, solver candidates, kernel reconstruction, focused tests, and broad tests.",
                                "Independent checks run in parallel under the shared resource budget.",
                                "Impact selection explains every included, omitted, escalated, and fallback check.",
                                "Validation reports retain separate deterministic, solver, kernel, test, and attestation verdicts.",
                            ),
                            validate("proof_validation_scheduler"),
                            task_id="REF-259",
                            depends_on=("REF-256", "REF-257", "REF-258"),
                        ),
                        _task(
                            "G11",
                            "G11.S4",
                            "Persist proof scheduler metrics and queryable receipts",
                            "P0",
                            (
                                module("proof_metrics.py"),
                                module("artifact_store.py"),
                                module("scheduler_metrics.py"),
                                test("proof_metrics"),
                            ),
                            "Operators and planning policy need proof throughput, trust, cache, context, and resource measurements without loading raw event logs.",
                            (
                                "JSON and DuckDB tables expose obligations, attempts, receipts, dependencies, cache outcomes, resource samples, and assurance counts.",
                                "Metrics include queue, solver, kernel, model, validation, merge, cancellation, and cache latency.",
                                "Every metric is keyed by canonical goal, subgoal, task, tree, provider, template, and resource class.",
                                "Queryable aggregates do not include hidden witnesses or unbounded proof transcripts.",
                            ),
                            validate("proof_metrics"),
                            task_id="REF-260",
                            depends_on=("REF-250", "REF-254", "REF-257"),
                        ),
                    ],
                },
                {
                    "id": "G11.S5",
                    "title": "Use Leanstral as a kernel-checked shadow assistant",
                    "tasks": [
                        _task(
                            "G11",
                            "G11.S5",
                            "Expose Leanstral through a capability-isolated llm_router provider",
                            "P1",
                            (
                                module("leanstral_proof_provider.py"),
                                module("formal_verification_capabilities.py"),
                                test("leanstral_proof_provider"),
                            ),
                            "Leanstral can draft useful Lean proof text, but its legal-modal implementation has optional model and spaCy dependencies that cannot become supervisor startup requirements.",
                            (
                                "Leanstral inference is invoked through llm_router with explicit provider, model, timeout, and token budgets.",
                                "Missing spaCy, model service, codec, or Leanstral dependencies produce degraded capability rather than import failure.",
                                "Model output is always marked unverified and cannot mutate canonical source or obligations.",
                                "Inference runs in the model resource class, separate from local kernel checking.",
                            ),
                            validate("leanstral_proof_provider"),
                            task_id="REF-261",
                            depends_on=("REF-244", "REF-246"),
                        ),
                        _task(
                            "G11",
                            "G11.S5",
                            "Generate fixed-theorem Leanstral prompts from proof context capsules",
                            "P1",
                            (
                                module("leanstral_proof_provider.py"),
                                module("proof_context.py"),
                                test("leanstral_proof_context"),
                            ),
                            "Leanstral should solve a verifier-generated theorem with bounded premises instead of rediscovering repository structure in its context window.",
                            (
                                "Prompts contain a fixed theorem identity, allowed premises, trusted prior receipts, compact failures, and output schema.",
                                "The model may propose proof text or decomposition but cannot change assumptions, conclusion, template, or source scope.",
                                "Prompt and response sizes obey context-capsule and token budgets.",
                                "Equivalent tasks reuse untrusted draft artifacts without treating them as checked evidence.",
                            ),
                            validate("leanstral_proof_context"),
                            task_id="REF-262",
                            depends_on=("REF-252", "REF-261"),
                        ),
                        _task(
                            "G11",
                            "G11.S5",
                            "Kernel-check Leanstral drafts and constrain patch proposals",
                            "P0",
                            (
                                module("leanstral_proof_provider.py"),
                                module("kernel_verification.py"),
                                test("leanstral_proof_gate"),
                            ),
                            "Leanstral output is useful only after deterministic schema, theorem-integrity, source-scope, patch, and local kernel checks.",
                            (
                                "Forbidden imports, axioms, unsafe declarations, sorry, admit, theorem substitution, and source-copy attacks are rejected.",
                                "Accepted proof text passes the same independent kernel reconstruction path as non-LLM candidates.",
                                "Patch proposals are restricted to task-declared paths and must pass git apply check plus configured validation.",
                                "Model and kernel artifacts retain separate provenance and assurance.",
                            ),
                            validate("leanstral_proof_gate"),
                            task_id="REF-263",
                            depends_on=("REF-255", "REF-262"),
                        ),
                    ],
                },
                {
                    "id": "G11.S6",
                    "title": "Attest trusted receipts with production-safe ZKP",
                    "tasks": [
                        _task(
                            "G11",
                            "G11.S6",
                            "Define ZKP receipt-attestation statements and trust semantics",
                            "P1",
                            (
                                module("proof_attestation.py"),
                                module("formal_verification_contracts.py"),
                                test("proof_attestation_contracts"),
                            ),
                            "A ZKP can bind a trusted proof receipt or protect private premises, but it does not independently prove arbitrary Python correctness.",
                            (
                                "The public statement binds tree, obligation, policy, kernel, receipt, circuit, backend, and verification-key identities.",
                                "Attestation is available only for an existing kernel-verified receipt.",
                                "Simulated ZKP is labeled non-authoritative and cannot satisfy production or completion gates.",
                                "Hidden witness fields are excluded from logs, context capsules, caches, and public artifacts.",
                            ),
                            validate("proof_attestation_contracts"),
                            task_id="REF-264",
                            depends_on=("REF-245",),
                        ),
                        _task(
                            "G11",
                            "G11.S6",
                            "Gate cryptographic backends on health, circuit, key, and no-leak evidence",
                            "P1",
                            (
                                module("proof_attestation.py"),
                                module("formal_verification_capabilities.py"),
                                test("proof_attestation_backends"),
                            ),
                            "ProveKit or Groth16 must fail closed when binaries, circuits, verification keys, schemas, or witness protections are unavailable or stale.",
                            (
                                "Backend health distinguishes simulated, configured, available, verified, degraded, and unavailable states.",
                                "Circuit, public-input schema, verification-key, and backend versions are pinned in policy and receipt identity.",
                                "Golden, negative, stale-key, malformed-proof, and witness no-leak cases gate production eligibility.",
                                "A cryptographic failure cannot fall back to simulated success.",
                            ),
                            validate("proof_attestation_backends"),
                            task_id="REF-265",
                            depends_on=("REF-244", "REF-264"),
                        ),
                        _task(
                            "G11",
                            "G11.S6",
                            "Persist optional ZKP envelopes beside trusted proof receipts",
                            "P1",
                            (
                                module("proof_attestation.py"),
                                module("formal_verification_cache.py"),
                                module("artifact_store.py"),
                                test("proof_attestation_store"),
                            ),
                            "Verified envelopes should be queryable and optionally content-addressed without changing the underlying proof verdict or exposing witnesses.",
                            (
                                "Attestation envelopes preserve a reference to the immutable kernel receipt and public-input digest.",
                                "Cache and optional IPFS records bind backend, circuit, key, policy, and expiration.",
                                "Verifier results are reproducible from public artifacts and fail when any bound identity changes.",
                                "Attestation loss or expiration leaves kernel assurance intact but removes attested assurance.",
                            ),
                            validate("proof_attestation_store"),
                            task_id="REF-266",
                            depends_on=("REF-254", "REF-255", "REF-265"),
                        ),
                    ],
                },
                {
                    "id": "G11.S7",
                    "title": "Enforce proof-aware merge and goal completion",
                    "tasks": [
                        _task(
                            "G11",
                            "G11.S7",
                            "Map trusted proof receipts into goal completion evidence",
                            "P0",
                            (
                                module("goal_completion.py"),
                                module("formal_verification_contracts.py"),
                                test("proof_goal_completion"),
                            ),
                            "A successful implementation or test receipt should not satisfy a proof-required acceptance criterion without fresh trusted proof evidence.",
                            (
                                "CompletionEvidence can reference obligation, proof receipt, assurance, tree, freshness, and provenance identities.",
                                "Required assurance is evaluated independently from validation success and task status.",
                                "Parent goals aggregate child proof requirements without hiding unsupported, inconclusive, stale, or contradicted descendants.",
                                "Legacy evidence remains readable but cannot be optimistically upgraded.",
                            ),
                            validate("proof_goal_completion"),
                            task_id="REF-267",
                            depends_on=("REF-245", "REF-255", "REF-260"),
                        ),
                        _task(
                            "G11",
                            "G11.S7",
                            "Apply risk-selected proof gates before merge promotion",
                            "P0",
                            (
                                module("merge_train.py"),
                                module("formal_verification_policy.py"),
                                module("todo_daemon/implementation_daemon.py"),
                                test("proof_merge_gate"),
                            ),
                            "Protected supervisor invariants need a durable promotion decision after implementation and before the merge train advances the candidate.",
                            (
                                "Changed scopes select proof requirements, fallback checks, and rollout mode deterministically.",
                                "Shadow records outcomes, canary blocks configured paths, and enforcement fails closed for missing required assurance.",
                                "The merge receipt identifies the exact proof plan, receipts, validations, policy, tree, and any operator override.",
                                "Retries reuse valid cache evidence and do not weaken policy after a timeout or provider failure.",
                            ),
                            validate("proof_merge_gate"),
                            task_id="REF-268",
                            depends_on=("REF-247", "REF-259", "REF-267"),
                        ),
                        _task(
                            "G11",
                            "G11.S7",
                            "Invalidate proof evidence and reopen goals after semantic change",
                            "P0",
                            (
                                module("goal_completion.py"),
                                module("objective_task_janitor.py"),
                                module("proof_scope_index.py"),
                                test("proof_invalidation"),
                            ),
                            "A changed symbol, premise, template, toolchain, policy, or contradiction must revoke affected proof coverage and schedule bounded replacement work.",
                            (
                                "Transitive invalidation records the changed input, affected obligations, receipts, criteria, goals, and source tree.",
                                "Affected provisional or verified goals reopen deterministically while unrelated goals remain stable.",
                                "Repeated identical invalidations are idempotent and historical receipts remain auditable.",
                                "Replacement tasks retain dependency and conflict edges to the invalidated scope.",
                            ),
                            validate("proof_invalidation"),
                            task_id="REF-269",
                            depends_on=("REF-251", "REF-267"),
                        ),
                        _task(
                            "G11",
                            "G11.S7",
                            "Make planning proof-aware without expanding model context",
                            "P0",
                            (
                                module("objective_graph.py"),
                                module("plan_evaluator.py"),
                                module("proof_context.py"),
                                test("proof_aware_planning"),
                            ),
                            "The planner should prioritize proof-critical work, reuse trusted evidence, and generate bounded repair tasks from unsupported or contradicted obligations.",
                            (
                                "Plan candidates declare obligation impact, required assurance, proof cost, cache likelihood, dependencies, and expected evidence delta.",
                                "Priority accounts for proof critical path, downstream unlock value, risk, freshness, and available resource classes.",
                                "The router receives only a bounded proof context capsule and rejected alternatives retain rationale.",
                                "Unsupported or failed obligations generate finite template, test, premise, or manual-review work with semantic deduplication.",
                            ),
                            validate("proof_aware_planning"),
                            task_id="REF-270",
                            depends_on=("REF-252", "REF-257", "REF-267"),
                        ),
                    ],
                },
                {
                    "id": "G11.S8",
                    "title": "Validate rollout security, context savings, and throughput",
                    "tasks": [
                        _task(
                            "G11",
                            "G11.S8",
                            "Add adversarial tests for every proof trust boundary",
                            "P0",
                            (
                                test("proof_adversarial"),
                                module("formal_verification_contracts.py"),
                                module("formal_verification_cache.py"),
                            ),
                            "Formal-looking artifacts are a new attack surface and must be unable to forge assurance, poison caches, leak witnesses, or bypass merge policy.",
                            (
                                "Tests cover forged verified status, solver-only success, stale trees, changed premises, cache poisoning, malformed receipts, and toolchain drift.",
                                "Tests reject sorry or admit, theorem substitution, malicious prover output, simulated ZKP promotion, stale verification keys, and hidden-witness leakage.",
                                "Timeout, cancellation, crash, restart, and duplicate single-flight cases preserve fail-closed verdicts.",
                                "Every rejected artifact emits a bounded actionable reason without exposing secrets.",
                            ),
                            validate("proof_adversarial"),
                            task_id="REF-271",
                            depends_on=("REF-263", "REF-266", "REF-268", "REF-269"),
                        ),
                        _task(
                            "G11",
                            "G11.S8",
                            "Exercise an end-to-end parallel proof-aware implementation workflow",
                            "P0",
                            (
                                test("proof_workflow_e2e"),
                                module("proof_scheduler.py"),
                                module("todo_daemon/implementation_daemon.py"),
                            ),
                            "The complete task, AST, proof, validation, merge, evidence, and reopen lifecycle must work under concurrent lanes and restart.",
                            (
                                "Fixtures cover cache hit, proof success, counterexample, unsupported fallback, kernel rejection, provider outage, and stale evidence.",
                                "Independent obligations and implementation lanes run concurrently without duplicate leases, receipts, merges, or goal transitions.",
                                "Shared resource limits remain respected across solver, kernel, test, model, and artifact work.",
                                "Restart preserves proof-plan dependencies, single-flight ownership, receipt lineage, and truthful operator state.",
                            ),
                            validate("proof_workflow_e2e"),
                            task_id="REF-272",
                            depends_on=("REF-260", "REF-270", "REF-271"),
                        ),
                        _task(
                            "G11",
                            "G11.S8",
                            "Expose shadow, canary, enforcement, and override diagnostics",
                            "P0",
                            (
                                module("formal_verification_policy.py"),
                                module("scheduler_metrics.py"),
                                module("todo_daemon/implementation_supervisor.py"),
                                test("proof_rollout"),
                            ),
                            "Operators need to know whether proof work is advisory or blocking and why a task, merge, or goal advanced.",
                            (
                                "Status and query artifacts show rollout mode, protected scopes, capability health, active plans, assurance, failures, fallbacks, and overrides.",
                                "Canary expansion and rollback are configuration changes with durable policy identity.",
                                "Overrides are visible, expiring, scope-bounded, and never rewrite the underlying proof verdict.",
                                "A provider outage cannot silently switch an enforcement scope to shadow mode.",
                            ),
                            validate("proof_rollout"),
                            task_id="REF-273",
                            depends_on=("REF-268", "REF-272"),
                        ),
                        _task(
                            "G11",
                            "G11.S8",
                            "Benchmark context reduction, cache reuse, and CPU proof throughput",
                            "P1",
                            (
                                module("proof_metrics.py"),
                                test("proof_benchmarks"),
                                plan_path,
                            ),
                            "Enforcement should expand only when proof evidence reduces model work without unacceptable host or implementation throughput regressions.",
                            (
                                "Benchmarks compare raw repository context with bounded proof capsules by bytes, tokens, retrieval precision, and accepted-task cost.",
                                "Cold and warm runs report translation, solver, kernel, cache, model, validation, and merge latency plus CPU and memory use.",
                                "Parallel runs detect nested oversubscription and quantify cancellation and single-flight savings.",
                                "Documented thresholds gate rollout expansion and identify unsupported or low-value obligation templates.",
                            ),
                            validate("proof_benchmarks"),
                            task_id="REF-274",
                            depends_on=("REF-260", "REF-272"),
                        ),
                    ],
                },
            ],
        },
    ]


def _formal_planning_goals() -> list[dict[str, Any]]:
    """Extend proof-aware execution with formally checked work planning.

    G12 depends on the contracts and execution primitives in G11, but remains a
    separate goal so active G11 task identities and bundle ownership stay
    stable while the broader prover-matrix program is appended.
    """

    module_root = (
        "ipfs_datasets_py/ipfs_accelerate_py/"
        "ipfs_accelerate_py/agent_supervisor"
    )
    test_root = "ipfs_datasets_py/ipfs_accelerate_py/test/api"
    plan_path = (
        "ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/"
        "AGENT_SUPERVISOR_FORMAL_PLANNING_PROVER_MATRIX_PLAN.md"
    )

    def module(name: str) -> str:
        return f"{module_root}/{name}"

    def test(name: str) -> str:
        return f"{test_root}/test_agent_supervisor_{name}.py"

    def validate(name: str) -> tuple[str, ...]:
        return (
            "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py "
            f"python -m pytest {test(name)} -q",
        )

    return [
        {
            "id": "G12",
            "title": "Formally plan supervisor work across the prover matrix",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G12.S1",
                    "title": "Represent and verify intended work with DCEC and TDFOL",
                    "tasks": [
                        _task(
                            "G12",
                            "G12.S1",
                            "Define a canonical formal work-plan contract and logic vocabulary",
                            "P0",
                            (
                                plan_path,
                                module("formal_planning_contracts.py"),
                                module("formal_logic_vocabulary.py"),
                                test("formal_planning_contracts"),
                            ),
                            "The supervisor needs a deterministic semantic model of intended work before a language model is asked to implement it.",
                            (
                                "FormalWorkPlan records actors, goals, subgoals, tasks, events, fluents, preconditions, effects, norms, temporal constraints, evidence requirements, and deterministic identities.",
                                "A reviewed DCEC vocabulary models belief, knowledge, intention, obligation, permission, prohibition, delegation, and execution events without deriving formulas from free-form model text.",
                                "A reviewed TDFOL vocabulary models dependency ordering, deadlines, liveness, safety, and goal satisfaction over finite supervisor traces.",
                                "A versioned frame-logic projection derives bounded worlds, accessibility relations, and relevant evidence-graph neighborhoods without treating graph reachability as code proof.",
                                "Plan consistency, plan conformance, and generated-code assurance are separate levels; no plan proof is promoted into a code proof.",
                            ),
                            validate("formal_planning_contracts"),
                            task_id="REF-275",
                            depends_on=("REF-245",),
                        ),
                        _task(
                            "G12",
                            "G12.S1",
                            "Compile objective, taskboard, AST, and policy records into formal plans",
                            "P0",
                            (
                                module("formal_plan_compiler.py"),
                                test("formal_plan_compiler"),
                            ),
                            "Formal plans must be derived from canonical supervisor and AST records rather than reconstructed by an LLM inside its context window.",
                            (
                                "The compiler maps goals, task dependencies, leases, resource needs, changed AST scopes, acceptance criteria, and proof policy into canonical plan predicates and events.",
                                "Compilation preserves task, goal, tree, symbol, policy, and evidence CIDs and records every abstraction or unsupported field.",
                                "Equivalent JSON and DuckDB inputs produce the same plan identity and graph projection.",
                                "Syntax failures, cycles, ambiguous effects, and missing semantics produce explicit unsupported or invalid plan results.",
                            ),
                            validate("formal_plan_compiler"),
                            task_id="REF-276",
                            depends_on=("REF-250", "REF-275"),
                        ),
                        _task(
                            "G12",
                            "G12.S1",
                            "Check formal plans for temporal, deontic, and dependency consistency",
                            "P0",
                            (
                                module("formal_plan_validator.py"),
                                test("formal_plan_validator"),
                            ),
                            "The supervisor should reject contradictory, unauthorized, impossible, or non-terminating plans before spending model tokens on implementation.",
                            (
                                "Bounded DCEC and TDFOL checks cover dependency readiness, actor authority, unique leases, fencing, required evidence, legal transitions, eventual terminal outcomes, and forbidden merge states.",
                                "Contradictions, countermodels, unsupported operators, timeout, and incomplete search remain distinct outcomes.",
                                "Native DCEC or TDFOL success is plan-check evidence only unless the exact obligation is reconstructed by an accepted kernel or model checker.",
                                "Validation is deterministic, resource bounded, cancellable, and records all assumptions and finite bounds.",
                            ),
                            validate("formal_plan_validator"),
                            task_id="REF-277",
                            depends_on=("REF-247", "REF-276"),
                        ),
                        _task(
                            "G12",
                            "G12.S1",
                            "Give Codex and Leanstral proof-carrying formal plan capsules",
                            "P0",
                            (
                                module("formal_plan_context.py"),
                                test("formal_plan_context"),
                            ),
                            "Language models should receive the verified slice of intended work, not rediscover task semantics and repository-wide dependencies in every prompt.",
                            (
                                "Capsules contain the selected task transition, assumptions, required preconditions and effects, relevant AST symbols, trusted evidence, counterexamples, allowed paths, tests, and unresolved obligations.",
                                "Graph queries enforce row, hop, byte, token, and source-excerpt limits before model invocation.",
                                "Model responses bind the plan and task CIDs and cannot alter the theorem, acceptance policy, or authoritative evidence.",
                                "Measurements compare capsule size and implementation outcomes against the existing unbounded planning prompt.",
                            ),
                            validate("formal_plan_context"),
                            task_id="REF-278",
                            depends_on=("REF-252", "REF-277"),
                        ),
                    ],
                },
                {
                    "id": "G12.S2",
                    "title": "Make the full prover matrix executable and trust-aware",
                    "tasks": [
                        _task(
                            "G12",
                            "G12.S2",
                            "Build an executable, self-testing prover capability matrix",
                            "P0",
                            (
                                module("prover_matrix_registry.py"),
                                test("prover_matrix_registry"),
                            ),
                            "Source files, installers, and executable discovery do not establish that a prover can soundly check a supervisor obligation.",
                            (
                                "The registry covers Z3, CVC5, TLA+/TLC, Apalache, Datalog/SecPAL, Tamarin, ProVerif, HyperLTL/AutoHyper/MCHyper, Lean, Coq, runtime MTL, DCEC, TDFOL, Hammer, Vampire, E, Isabelle, ShadowProver, Leanstral, and ZKP backends.",
                                "Each entry distinguishes absent, discovered, versioned, smoke-tested, translation-conformant, reconstruction-capable, and authoritative-for states.",
                                "Bounded self-tests bind executable, package, model, translator, semantic profile, and fixture identities.",
                                "The repository prover matrix is projected into queryable JSON and DuckDB without treating documentation claims as runtime evidence.",
                            ),
                            validate("prover_matrix_registry"),
                            task_id="REF-279",
                            depends_on=("REF-246",),
                        ),
                        _task(
                            "G12",
                            "G12.S2",
                            "Conformance-test and quarantine logic translations and legacy prover paths",
                            "P0",
                            (
                                module("prover_conformance.py"),
                                module("logic_translation_validation.py"),
                                test("prover_conformance"),
                            ),
                            "A solver is only as sound as the translation and semantic abstraction used to invoke it.",
                            (
                                "Translation contracts label exact, equisatisfiable, bounded abstraction, conservative approximation, and heuristic mappings and define permitted assurance for each.",
                                "Round-trip, differential, metamorphic, mutation, and negative fixtures cover AST, DCEC, TDFOL, FOL, TPTP, SMT-LIB, TLA+, protocol, and hyperproperty forms.",
                                "Known CEC deontic API drift and timing-sensitive cache tests keep affected paths degraded until semantic conformance fixtures pass.",
                                "Dropped agents, times, quantifiers, modal operators, bounds, or premises are detected and cannot silently promote a result.",
                            ),
                            validate("prover_conformance"),
                            task_id="REF-280",
                            depends_on=("REF-275", "REF-279"),
                        ),
                        _task(
                            "G12",
                            "G12.S2",
                            "Route obligations through property-specific multi-prover portfolios",
                            "P0",
                            (
                                module("multi_prover_router.py"),
                                test("multi_prover_router"),
                            ),
                            "Different supervisor claims require different semantics; one generic solver-success flag cannot verify them all.",
                            (
                                "Routing selects SMT for finite constraints, TLA tools for state machines, Datalog/SecPAL for authorization, Tamarin/ProVerif for protocols, HyperLTL tools for hyperproperties, runtime MTL for traces, and Lean/Coq/Isabelle for kernel checking.",
                                "DCEC and TDFOL provide typed planning and temporal-deontic reasoning while Hammer coordinates premise selection, ATP/SMT candidates, and kernel reconstruction.",
                                "Disagreement, unknown, unsupported, timeout, and malformed output fail closed according to property policy and retain every attempt.",
                                "Conclusive counterexamples cancel redundant attempts while successful solver candidates still require the configured reconstruction or model-checking authority.",
                            ),
                            validate("multi_prover_router"),
                            task_id="REF-281",
                            depends_on=("REF-255", "REF-280"),
                        ),
                        _task(
                            "G12",
                            "G12.S2",
                            "Persist conformance-bound prover receipts, caches, and matrix projections",
                            "P0",
                            (
                                module("prover_evidence_store.py"),
                                test("prover_evidence_store"),
                            ),
                            "Multi-prover reuse must bind every semantic, model, bound, toolchain, and trust dimension and remain queryable without loading raw transcripts.",
                            (
                                "Receipt and cache identities include property class, normalized model, translator profile, assumptions, finite bounds, prover and kernel versions, policy, tree, and conformance fixture set.",
                                "Stale, lower-assurance, model-only, or non-conformant results cannot satisfy a stronger request.",
                                "JSON and DuckDB projections expose capabilities, attempts, disagreements, counterexamples, assurance, freshness, and invalidation lineage.",
                                "Single-flight ownership deduplicates equivalent heavy prover requests across serial and parallel supervisors.",
                            ),
                            validate("prover_evidence_store"),
                            task_id="REF-282",
                            depends_on=("REF-260", "REF-281"),
                        ),
                    ],
                },
                {
                    "id": "G12.S3",
                    "title": "Verify scheduler state, authority, protocols, and information flow",
                    "tasks": [
                        _task(
                            "G12",
                            "G12.S3",
                            "Model-check supervisor state machines with TLA+, TLC, and Apalache",
                            "P0",
                            (
                                module("supervisor_state_model.py"),
                                test("supervisor_state_model"),
                            ),
                            "Leases, retries, merges, refill, cancellation, and resource scheduling are concurrent state machines suited to bounded model checking.",
                            (
                                "A deterministic generator emits a finite TLA+ model from the supervisor transition schema rather than a domain-specific hard-coded workflow.",
                                "Safety covers unique acceptance, fencing, dependency order, idempotent merge, capacity, and evidence gates; liveness covers bounded progress and terminal outcomes.",
                                "TLC and Apalache execution receipts record exact model, configuration, bounds, versions, output, and counterexample traces.",
                                "Bounded model-check success is labeled by its explored bounds and is never described as an unbounded proof.",
                            ),
                            validate("supervisor_state_model"),
                            task_id="REF-283",
                            depends_on=("REF-277", "REF-279"),
                        ),
                        _task(
                            "G12",
                            "G12.S3",
                            "Formalize task authority and delegation with Datalog and SecPAL-style policy",
                            "P0",
                            (
                                module("authorization_logic.py"),
                                test("authorization_logic"),
                            ),
                            "Claims, leases, merge authority, proof promotion, and overrides need explicit delegation and revocation semantics.",
                            (
                                "Rules model principals, capabilities, delegation depth, lease scope, fencing epoch, proof authority, override scope, expiration, and revocation.",
                                "The reference evaluator and any external Datalog or SecPAL lane agree on positive, negative, revocation, confused-deputy, and stale-lease fixtures.",
                                "Missing engines remain unsupported while deterministic policy checks continue in shadow mode.",
                                "Authorization evidence can permit an action but cannot establish generated-code correctness.",
                            ),
                            validate("authorization_logic"),
                            task_id="REF-284",
                            depends_on=("REF-277", "REF-279"),
                        ),
                        _task(
                            "G12",
                            "G12.S3",
                            "Verify claim, fencing, receipt, and attestation protocols with Tamarin and ProVerif",
                            "P0",
                            (
                                module("protocol_verification.py"),
                                test("protocol_verification"),
                            ),
                            "Supervisor coordination and evidence exchange have protocol properties that unit tests and state invariants alone do not cover.",
                            (
                                "Versioned models cover claimant authentication, lease grants, fencing freshness, replay resistance, receipt binding, merge authorization, and optional attestation exchange.",
                                "Tamarin and ProVerif lanes expose secrecy, authenticity, correspondence, and replay queries with exact model and toolchain receipts.",
                                "Attack traces become canonical counterexamples and model abstractions are documented per query.",
                                "Executable presence or installer success cannot satisfy protocol verification without a passing end-to-end model fixture.",
                            ),
                            validate("protocol_verification"),
                            task_id="REF-285",
                            depends_on=("REF-264", "REF-284"),
                        ),
                        _task(
                            "G12",
                            "G12.S3",
                            "Check cross-lane information-flow hyperproperties",
                            "P0",
                            (
                                module("hyperproperty_verification.py"),
                                test("hyperproperty_verification"),
                            ),
                            "Single-trace checks cannot establish that secrets, witnesses, or unrelated lane data do not affect observable prompts, logs, or artifacts.",
                            (
                                "Hyperproperty models cover prompt isolation, worktree isolation, log redaction, provider routing, ZKP witness noninterference, and cross-task cache separation.",
                                "HyperLTL, AutoHyper, and MCHyper adapters are capability-gated and report unavailable until executable conformance fixtures pass.",
                                "Bounded self-composition tests provide non-authoritative fallback evidence when no hyperproperty engine is available.",
                                "Counterexample hypertraces are redacted, minimized, and bound to the exact observation policy.",
                            ),
                            validate("hyperproperty_verification"),
                            task_id="REF-286",
                            depends_on=("REF-252", "REF-265", "REF-279"),
                        ),
                    ],
                },
                {
                    "id": "G12.S4",
                    "title": "Monitor execution and replan from formal counterexamples",
                    "tasks": [
                        _task(
                            "G12",
                            "G12.S4",
                            "Generalize runtime MTL monitoring to supervisor event traces",
                            "P0",
                            (
                                module("runtime_temporal_monitor.py"),
                                test("runtime_temporal_monitor"),
                            ),
                            "Offline plans and proofs need a bounded runtime conformance layer for actual daemon, lane, proof, validation, and merge events.",
                            (
                                "Versioned temporal properties cover event ordering, lease expiration, no action after revocation or cancellation, proof-before-merge, bounded retry, eventual terminal status, and resource-release deadlines.",
                                "The monitor handles rotated logs, restart epochs, duplicate events, missing timestamps, and bounded out-of-order windows explicitly.",
                                "Violations emit durable counterexamples and reopen affected work; absence of observed violations is not promoted into a proof.",
                                "Streaming state is bounded and partitioned by task, lane, tree, and policy identity.",
                            ),
                            validate("runtime_temporal_monitor"),
                            task_id="REF-287",
                            depends_on=("REF-277", "REF-279"),
                        ),
                        _task(
                            "G12",
                            "G12.S4",
                            "Normalize proof failures and traces into a counterexample knowledge graph",
                            "P0",
                            (
                                module("formal_counterexamples.py"),
                                test("formal_counterexamples"),
                            ),
                            "Models should receive compact actionable counterexamples instead of raw solver, model-checker, or runtime transcripts.",
                            (
                                "A canonical IR represents SMT models and unsat cores, DCEC or TDFOL contradictions, TLA traces, protocol attacks, hypertraces, kernel errors, and runtime MTL violations.",
                                "Graph edges bind each counterexample to plans, tasks, AST scopes, assumptions, obligations, providers, receipts, and invalidated evidence.",
                                "Minimization, semantic deduplication, redaction, and byte limits run before persistence or prompt assembly.",
                                "Hidden witnesses, credentials, unrelated source, and unbounded prover output never enter a context capsule.",
                            ),
                            validate("formal_counterexamples"),
                            task_id="REF-288",
                            depends_on=("REF-256", "REF-280", "REF-283", "REF-287"),
                        ),
                        _task(
                            "G12",
                            "G12.S4",
                            "Generate bounded counterexample-guided plan repairs",
                            "P0",
                            (
                                module("formal_replanner.py"),
                                test("formal_replanner"),
                            ),
                            "A failed formal plan should yield focused repair work instead of another repository-wide language-model analysis.",
                            (
                                "Typed repair rules can add missing dependencies, split effects, tighten authority, add tests or proof templates, change resource bounds, or request scoped human review.",
                                "Every candidate repair is recompiled and rechecked against the original goal and counterexample before taskboard admission.",
                                "Semantic identities, retry budgets, refinement depth, and progress measures prevent duplicate or infinite repair generation.",
                                "Codex receives only the selected repair transition and bounded counterexample capsule.",
                            ),
                            validate("formal_replanner"),
                            task_id="REF-289",
                            depends_on=("REF-270", "REF-278", "REF-288"),
                        ),
                        _task(
                            "G12",
                            "G12.S4",
                            "Bind plan conformance and formal evidence into goal completion",
                            "P0",
                            (
                                module("formal_plan_conformance.py"),
                                test("formal_plan_conformance"),
                            ),
                            "A goal should close only when intended transitions occurred and all required implementation, validation, and proof evidence remains fresh.",
                            (
                                "Conformance compares canonical execution events with the accepted plan and distinguishes skipped, reordered, unauthorized, failed, overridden, and superseded transitions.",
                                "Plan consistency alone never verifies code; completion policy independently requires configured code, test, kernel, model-check, protocol, and runtime evidence.",
                                "Plan, policy, AST, premise, or counterexample changes invalidate affected conformance and reopen the goal.",
                                "Restart and replay reproduce the same conformance verdict from JSON or DuckDB evidence.",
                            ),
                            validate("formal_plan_conformance"),
                            task_id="REF-290",
                            depends_on=("REF-289",),
                        ),
                    ],
                },
                {
                    "id": "G12.S5",
                    "title": "Scale formal planning safely under parallel execution",
                    "tasks": [
                        _task(
                            "G12",
                            "G12.S5",
                            "Admit every prover family through one shared CPU and process budget",
                            "P0",
                            (
                                module("multi_prover_resources.py"),
                                test("multi_prover_resources"),
                            ),
                            "JVM model checkers, SMT solvers, ATPs, kernels, protocol tools, tests, and models must not create nested pools that oversubscribe the host.",
                            (
                                "Resource classes cover translation, SMT, ATP, ITP kernels, JVM model checking, protocol verification, hyperproperty checking, runtime monitors, LLM inference, and artifact IO.",
                                "One top-level lease accounts for child processes, threads, memory, disk, provider quota, and model concurrency across serial and bundle supervisors.",
                                "Bundle admission launches dependency-closed ready-member slices so a later blocked member cannot idle earlier work, and mixed-readiness lanes retain task dependency enforcement.",
                                "Timeout and cancellation terminate process groups, release capacity, and preserve bounded diagnostics and partial receipts.",
                                "Portfolio width adapts to host pressure and critical-path value while deterministic cache hits bypass execution safely.",
                            ),
                            validate("multi_prover_resources"),
                            task_id="REF-291",
                            depends_on=("REF-258", "REF-281", "REF-283", "REF-285", "REF-286", "REF-287"),
                        ),
                        _task(
                            "G12",
                            "G12.S5",
                            "Adversarially test formal plans and every prover-matrix trust boundary",
                            "P0",
                            (
                                test("formal_planning_adversarial"),
                                module("formal_planning_adversarial.py"),
                            ),
                            "The expanded planner must resist forged plans, unsound translations, stale evidence, malicious tool output, and cross-lane leakage.",
                            (
                                "Tests mutate actor authority, temporal bounds, task dependencies, formulas, models, premises, tool versions, cache keys, receipts, traces, and assurance labels.",
                                "Fixtures cover unavailable tools, fake executable versions, solver disagreement, incomplete exploration, protocol false positives, hypertrace leakage, and monitor gaps.",
                                "No path promotes model text, native heuristic proofs, bounded results without bounds, simulated ZKP, or stale cache entries beyond policy.",
                                "Parallel crash, cancellation, restart, and duplicate claims preserve single-flight and fail-closed behavior.",
                            ),
                            validate("formal_planning_adversarial"),
                            task_id="REF-292",
                            depends_on=("REF-271", "REF-282", "REF-290", "REF-291"),
                        ),
                        _task(
                            "G12",
                            "G12.S5",
                            "Exercise an end-to-end proof-carrying planning and implementation workflow",
                            "P0",
                            (
                                module("proof_carrying_planner.py"),
                                test("proof_carrying_planner_e2e"),
                            ),
                            "Formal planning, bounded model context, implementation, verification, runtime monitoring, and replanning must work as one restartable workflow.",
                            (
                                "The workflow compiles and verifies a plan, dispatches independent Codex tasks, verifies changed scopes, merges accepted work, monitors execution, and repairs a seeded counterexample.",
                                "It exercises Hammer reconstruction, Lean or Coq checking, Leanstral shadow proposals, optional ZKP attestation, matrix-specific lanes, and test fallbacks without conflating assurance.",
                                "Independent plan and proof nodes execute concurrently while conflict, dependency, and shared-resource constraints remain authoritative.",
                                "All decisions are reproducible from paired JSON and DuckDB artifacts after restart.",
                            ),
                            validate("proof_carrying_planner_e2e"),
                            task_id="REF-293",
                            depends_on=("REF-292",),
                        ),
                        _task(
                            "G12",
                            "G12.S5",
                            "Benchmark and gate formal-planning rollout by assurance and throughput",
                            "P1",
                            (
                                module("formal_planning_metrics.py"),
                                module("formal_planning_rollout.py"),
                                test("formal_planning_benchmarks"),
                            ),
                            "The broader prover matrix should expand only when it reduces model work and improves defect detection without unacceptable CPU or scheduling regressions.",
                            (
                                "Cold and warm benchmarks measure context tokens, plan defects found before LLM dispatch, proof support, counterexample quality, cache reuse, queue latency, CPU saturation, memory, and accepted-task throughput.",
                                "Metrics separate property class, translator profile, prover, kernel, finite bound, rollout mode, task risk, and authoritative assurance.",
                                "Shadow, canary, and enforcement thresholds are explicit; unavailable or low-value lanes remain advisory and operator overrides remain durable and scoped.",
                                "Operator projections expose the executable matrix, degraded reasons, active formal plans, unmet obligations, trace violations, and rollout decisions without raw context dumps.",
                            ),
                            validate("formal_planning_benchmarks"),
                            task_id="REF-294",
                            depends_on=("REF-273", "REF-274", "REF-293"),
                        ),
                    ],
                },
            ],
        },
    ]


def _paths_from_locations(locations: list[str]) -> list[str]:
    paths: list[str] = []
    for item in locations:
        path = str(item).split(":", 1)[0].strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def flatten_tasks(goals: list[dict[str, Any]]) -> list[RefactorTask]:
    tasks: list[RefactorTask] = []
    for goal in goals:
        for subgoal in goal.get("subgoals", []):
            for task in subgoal.get("tasks", []):
                if isinstance(task, RefactorTask):
                    tasks.append(task)
    return tasks


def _resolved_seed_task_ids(goals: list[dict[str, Any]]) -> dict[int, str]:
    return {
        id(task): task.task_id or f"{TASK_PREFIX}{index:03d}"
        for index, task in enumerate(flatten_tasks(goals), start=1)
    }


def _json_goal_tree(
    goals: list[dict[str, Any]],
    scan: dict[str, Any],
    *,
    synchronization: dict[str, Any] | None = None,
    taskboard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_task_ids = _resolved_seed_task_ids(goals)
    statuses = {
        str(item.get("task_id")): str(item.get("status"))
        for item in (taskboard or {}).get("tasks", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    out_goals: list[dict[str, Any]] = []
    for goal in goals:
        goal_out = {k: v for k, v in goal.items() if k != "subgoals"}
        goal_out["subgoals"] = []
        for subgoal in goal.get("subgoals", []):
            subgoal_out = {k: v for k, v in subgoal.items() if k != "tasks"}
            subgoal_out["tasks"] = []
            for task in subgoal.get("tasks", []):
                task_payload = task.payload()
                task_id = resolved_task_ids[id(task)]
                task_payload["task_id"] = task_id
                task_payload["status"] = statuses.get(task_id, "unknown")
                subgoal_out["tasks"].append(task_payload)
            goal_out["subgoals"].append(subgoal_out)
        out_goals.append(goal_out)
    payload = {
        "schema": "complaint_generator.refactor_supervisor.goals.v1",
        "objective": "Refactor complaint-generator safely and incrementally.",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_supervisor_module": "ipfs_accelerate_py.agent_supervisor",
        "objective_path": str(OBJECTIVE_PATH.relative_to(PROJECT_ROOT)),
        "todo_path": str(TODO_PATH.relative_to(PROJECT_ROOT)),
        "bundle_dir": str(BUNDLE_DIR.relative_to(PROJECT_ROOT)),
        "queue_path": str(QUEUE_PATH.relative_to(PROJECT_ROOT)),
        "scan": scan,
        "goals": out_goals,
    }
    if synchronization is not None:
        payload["synchronization"] = dict(synchronization)
    if taskboard is not None:
        payload["taskboard"] = dict(taskboard)
    return payload


def _merge_goal_tree_extensions(
    generated: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    """Keep planning extensions that are not owned by the seed renderer.

    Follow-on planning tasks may add durable top-level data such as
    ``implementation_claims`` to the generated goal tree.  A fast seed owns and
    refreshes its standard fields, but must not erase those adjacent artifacts.
    """

    extensions = {key: value for key, value in existing.items() if key not in generated}
    return {**extensions, **generated}


def _goal_evidence(task: RefactorTask) -> str:
    evidence = [*task.files, *task.acceptance, *task.validation]
    return ", ".join(dict.fromkeys(item for item in evidence if item)) or task.title


def _render_objective_heap(goals: list[dict[str, Any]]) -> str:
    lines = [
        "# Complaint Generator Refactor Objective Heap",
        "",
        "Ultimate objective: Refactor complaint-generator safely and incrementally while preserving behavior.",
        "",
    ]
    for goal in goals:
        tasks = flatten_tasks([goal])
        lines.extend(
            [
                f"## {goal['id']} {goal['title']}",
                "",
                "- Status: active",
                f"- Priority: {goal['priority']}",
                f"- Bundle: refactor/{goal['id'].lower()}",
                "- Goal: " + goal["title"],
                "- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, "
                + ", ".join(dict.fromkeys(path for task in tasks for path in task.files[:3])),
                "- Validation: python -m pytest --collect-only -q",
                "",
            ]
        )
        for subgoal in goal.get("subgoals", []):
            subgoal_tasks = [task for task in subgoal.get("tasks", []) if isinstance(task, RefactorTask)]
            lines.extend(
                [
                    f"## {subgoal['id']} {subgoal['title']}",
                    "",
                    "- Status: active",
                    f"- Parent: {goal['id']}",
                    f"- Priority: {goal['priority']}",
                    f"- Bundle: refactor/{goal['id'].lower()}/{subgoal['id'].replace('.', '-').lower()}",
                    "- Goal: " + subgoal["title"],
                    "- Evidence: " + ", ".join(_goal_evidence(task) for task in subgoal_tasks),
                    "- Validation: " + "; ".join(
                        dict.fromkeys(command for task in subgoal_tasks for command in task.validation)
                    ),
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_seed_todo(goals: list[dict[str, Any]]) -> str:
    lines = [
        "# Complaint Generator Refactor Todo Board",
        "",
        "Generated by `scripts/refactor_agent_supervisor.py` from a codebase scan.",
        "This board is consumed by `ipfs_accelerate_py.agent_supervisor`.",
        "",
    ]
    index = 1
    for task in flatten_tasks(goals):
        task_id = task.task_id or f"{TASK_PREFIX}{index:03d}"
        lines.append(_task_block(task, task_id, _task_checkbox_index(task_id, index)))
        lines.append("")
        index += 1
    return "\n".join(lines).rstrip() + "\n"


def _task_checkbox_index(task_id: str, fallback: int) -> int:
    match = re.fullmatch(rf"{re.escape(TASK_PREFIX)}(\d+)", task_id)
    return int(match.group(1)) if match else fallback


def _synchronize_explicit_task_blocks(path: Path, tasks: list[RefactorTask]) -> bool:
    """Upsert explicit seed blocks while preserving their durable status."""

    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8", errors="replace")
    header_pattern = re.compile(
        rf"^##\s+({re.escape(TASK_PREFIX)}\d+)\s+(.+?)\s*$",
        re.MULTILINE,
    )
    checkbox_pattern = re.compile(
        rf"^\s*[-*]\s+\[([^\]])\]\s+Task checkbox-\d+:\s+"
        rf"({re.escape(TASK_PREFIX)}\d+)\b"
    )
    explicit = {task.task_id: task for task in tasks if task.task_id}
    if not explicit:
        return False

    lines = text.splitlines(keepends=True)
    headers: list[tuple[int, str, str]] = []
    for index, raw_line in enumerate(lines):
        match = header_pattern.match(raw_line.rstrip("\r\n"))
        if match:
            headers.append((index, match.group(1), match.group(2).strip()))

    starts: list[int] = []
    for header_index, task_id, _title in headers:
        start = header_index
        candidate = header_index - 1
        if candidate >= 0 and not lines[candidate].strip():
            candidate -= 1
        if candidate >= 0:
            checkbox = checkbox_pattern.match(lines[candidate].rstrip("\r\n"))
            if checkbox and checkbox.group(2) == task_id:
                start = candidate
        starts.append(start)

    output = list(lines[: starts[0]]) if starts else list(lines)
    seen: set[str] = set()
    for position, ((header_index, task_id, title), start) in enumerate(zip(headers, starts)):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        task = explicit.get(task_id)
        if task is None:
            output.extend(lines[start:end])
            continue
        if title != task.title:
            raise RuntimeError(
                f"Explicit seed id {task_id} already names {title!r}, not {task.title!r}"
            )

        existing_block = "".join(lines[start:end])
        checkbox = checkbox_pattern.match(lines[start].rstrip("\r\n"))
        checkbox_mark = checkbox.group(1) if checkbox else " "
        status_match = re.search(r"(?m)^- Status:\s*(\S+)\s*$", existing_block)
        status = status_match.group(1) if status_match else "todo"
        rendered = _task_block(
            task,
            task_id,
            _task_checkbox_index(task_id, position + 1),
        )
        rendered = rendered.replace("- [ ] Task", f"- [{checkbox_mark}] Task", 1)
        rendered = rendered.replace("- Status: todo", f"- Status: {status}", 1)
        output.append(rendered.rstrip() + "\n\n")
        seen.add(task_id)

    additions = [
        _task_block(
            task,
            task.task_id,
            _task_checkbox_index(task.task_id, fallback),
        )
        for fallback, task in enumerate(tasks, start=1)
        if task.task_id and task.task_id not in seen
    ]
    if additions:
        if output and "".join(output).strip():
            output.append("\n")
        output.append("\n\n".join(additions) + "\n")

    rendered_text = "".join(output).rstrip() + "\n"
    if rendered_text == text:
        return False
    path.write_text(rendered_text, encoding="utf-8")
    return True


def _append_missing_explicit_seed_tasks(path: Path, goals: list[dict[str, Any]]) -> bool:
    return _synchronize_explicit_task_blocks(path, flatten_tasks(goals))


def _safe_bundle_key(value: str) -> str:
    cleaned = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in {"/", "-", "_", "."}:
            cleaned.append("-")
    key = "".join(cleaned).strip("-")
    while "--" in key:
        key = key.replace("--", "-")
    return key or "refactor-general"


def _task_ast_symbols(files: tuple[str, ...], *, limit: int = 80) -> list[str]:
    symbols: list[str] = []
    for rel in files:
        path = PROJECT_ROOT / rel
        if path.suffix != ".py" or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            name = ""
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        break
            if name and name not in symbols:
                symbols.append(name)
            if len(symbols) >= limit:
                return symbols
    return symbols


def _task_block(task: RefactorTask, task_id: str, index: int) -> str:
    outputs = ", ".join(task.files) or str(TASKBOARD_DOC_PATH.relative_to(PROJECT_ROOT))
    validation = "; ".join(task.validation) or "python -m pytest --collect-only -q"
    bundle_key = f"refactor/{task.goal_id.lower()}/{task.subgoal_id.replace('.', '-').lower()}"
    symbols = ", ".join(_task_ast_symbols(task.files)[:30])
    return "\n".join(
        [
            f"- [ ] Task checkbox-{index}: {task_id} {task.title}",
            "",
            f"## {task_id} {task.title}",
            "",
            "- Status: todo",
            "- Completion: manual",
            f"- Priority: {task.priority}",
            f"- Track: {task.goal_id}",
            "- Depends on:" + (" " + ", ".join(task.depends_on) if task.depends_on else ""),
            f"- Outputs: {outputs}",
            f"- Validation: {validation}",
            f"- Bundle: {bundle_key}",
            "- Bundle strategy: goal/subgoal bundle with AST-symbol locality",
            f"- Goal id: {task.subgoal_id}",
            f"- Missing evidence: {task.rationale}",
            f"- AST symbols: {symbols}",
            f"- Merge key: {bundle_key}",
            "- Candidate kind: seed",
            f"- Todo vector key: {task_id.lower()}-{_safe_bundle_key(task.title)[:48]}",
            "- Acceptance: " + "; ".join(task.acceptance),
        ]
    )


def _prune_seed_bundle_shard(path: Path, tasks: list[dict[str, Any]]) -> list[str]:
    """Remove task blocks that are no longer members of a static seed bundle."""

    if not path.exists():
        return []
    expected = {
        (str(task.get("task_id") or ""), str(task.get("title") or "").strip())
        for task in tasks
        if task.get("task_id") and task.get("title")
    }
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    header_pattern = re.compile(rf"^##\s+({re.escape(TASK_PREFIX)}\d+)\s+(.+?)\s*$")
    checkbox_pattern = re.compile(
        rf"^\s*[-*]\s+\[[^\]]\]\s+Task checkbox-\d+:\s+({re.escape(TASK_PREFIX)}\d+)\b"
    )
    headers: list[tuple[int, str, str]] = []
    for index, raw_line in enumerate(lines):
        match = header_pattern.match(raw_line.rstrip("\r\n"))
        if match:
            headers.append((index, match.group(1), match.group(2).strip()))
    if not headers:
        return []

    starts: list[int] = []
    for header_index, task_id, _title in headers:
        start = header_index
        candidate = header_index - 1
        if candidate >= 0 and not lines[candidate].strip():
            candidate -= 1
        if candidate >= 0:
            checkbox = checkbox_pattern.match(lines[candidate].rstrip("\r\n"))
            if checkbox and checkbox.group(1) == task_id:
                start = candidate
        starts.append(start)

    output = list(lines[: starts[0]])
    removed: list[str] = []
    for position, ((header_index, task_id, title), start) in enumerate(zip(headers, starts)):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        if (task_id, title) in expected:
            output.extend(lines[start:end])
        else:
            removed.append(task_id)
    rendered = "".join(output)
    existing = "".join(lines)
    if rendered != existing:
        path.write_text(rendered.rstrip() + "\n", encoding="utf-8")
    return removed


def write_seed_bundle_index(
    goals: list[dict[str, Any]],
    *,
    exclude_bundle_keys: set[str] | None = None,
    task_statuses: dict[str, str] | None = None,
) -> dict[str, Any]:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    excluded = exclude_bundle_keys or set()
    statuses = task_statuses or {}
    index_path = BUNDLE_DIR / "index.json"
    existing_index = _load_json_object(index_path)
    existing_bundles = existing_index.get("bundles")
    if not isinstance(existing_bundles, dict):
        existing_bundles = {}
    seed_task_ids = set(_resolved_seed_task_ids(goals).values())
    seed_bundle_keys: set[str] = set()
    bundles: dict[str, dict[str, Any]] = {}
    dynamic_task_count = 0
    for bundle_key, raw_info in existing_bundles.items():
        if not isinstance(raw_info, dict):
            continue
        dynamic_tasks: list[dict[str, Any]] = []
        for raw_task in raw_info.get("tasks", []):
            if not isinstance(raw_task, dict):
                continue
            task_id = str(raw_task.get("task_id") or "")
            if not task_id or task_id in seed_task_ids:
                continue
            task = dict(raw_task)
            if task_id in statuses:
                task["status"] = statuses[task_id]
            dynamic_tasks.append(task)
        if not dynamic_tasks:
            continue
        info = dict(raw_info)
        info["tasks"] = dynamic_tasks
        bundles[str(bundle_key)] = info
        dynamic_task_count += len(dynamic_tasks)

    task_index = 1
    for task in flatten_tasks(goals):
        task_id = task.task_id or f"{TASK_PREFIX}{task_index:03d}"
        bundle_key = f"refactor/{task.goal_id.lower()}/{task.subgoal_id.replace('.', '-').lower()}"
        seed_bundle_keys.add(bundle_key)
        safe_key = _safe_bundle_key(bundle_key)
        shard_path = BUNDLE_DIR / f"{safe_key}.todo.md"
        if bundle_key not in excluded:
            if not shard_path.exists():
                shard_path.write_text(
                    f"# Objective Bundle: {bundle_key}\n\n"
                    f"Source todo: {TODO_PATH.relative_to(PROJECT_ROOT)}\n"
                    "Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.\n"
                    "Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.\n",
                    encoding="utf-8",
                )
            _synchronize_explicit_task_blocks(shard_path, [task])

        info = bundles.setdefault(bundle_key, {})
        info.update(
            {
                "bundle_key": bundle_key,
                "shard_path": shard_path.relative_to(PROJECT_ROOT).as_posix(),
                "parallel_lane": bundle_key,
                "bundle_strategy": str(info.get("bundle_strategy") or "goal_subgoal_ast"),
                "conflict_policy": str(
                    info.get("conflict_policy")
                    or "prefer bundle-local changes; reconcile generated worktrees before merge"
                ),
            }
        )
        info["tasks"] = [
            item
            for item in info.get("tasks", [])
            if isinstance(item, dict) and str(item.get("task_id") or "") != task_id
        ]
        info["tasks"].append(
            {
                "task_id": task_id,
                "status": statuses.get(task_id, "todo"),
                "title": task.title,
                "priority": task.priority,
                "goal_id": task.subgoal_id,
                "parent_goal_id": task.goal_id,
                "subgoal_id": task.subgoal_id,
                "rationale": task.rationale,
                "acceptance": list(task.acceptance),
                "graph_depth": 1,
                "parent_goal_ids": [task.goal_id],
                "missing_evidence": [task.rationale, *task.acceptance],
                "discovery_path": TASKBOARD_DOC_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "bundle_strategy": "goal_subgoal_ast",
                "surplus_group": bundle_key,
                "merge_key": bundle_key,
                "merge_family": task.goal_id,
                "merge_role": "seed",
                "work_item_count": max(1, len(task.files)),
                "work_scope": "goal_subgoal_ast_locality",
                "goal_packet_key": task.subgoal_id,
                "goal_packet_role": "seed",
                "goal_packet_goal_ids": [task.goal_id, task.subgoal_id],
                "goal_packet_task_count": 1,
                "goal_packet_work_item_count": max(1, len(task.files)),
                "candidate_kind": "seed",
                "todo_vector_key": f"{task_id.lower()}-{_safe_bundle_key(task.title)[:48]}",
                "ast_symbols": _task_ast_symbols(task.files),
                "paths": list(task.files),
                "validation": list(task.validation),
                "depends_on": list(task.depends_on),
            }
        )
        task_index += 1

    for info in bundles.values():
        info["tasks"] = sorted(
            (item for item in info.get("tasks", []) if isinstance(item, dict)),
            key=lambda item: str(item.get("task_id") or ""),
        )

    pruned_task_ids: dict[str, list[str]] = {}
    for bundle_key in sorted(seed_bundle_keys - excluded):
        info = bundles.get(bundle_key, {})
        shard_path = PROJECT_ROOT / str(info.get("shard_path") or "")
        removed = _prune_seed_bundle_shard(shard_path, list(info.get("tasks") or []))
        if removed:
            pruned_task_ids[bundle_key] = removed

    completed_task_ids = {
        task_id
        for task_id, status in statuses.items()
        if str(status).strip().lower() in {"complete", "completed", "done", "succeeded"}
    }
    completed_task_ids.update(
        str(item.get("task_id"))
        for info in bundles.values()
        for item in info.get("tasks", [])
        if str(item.get("status") or "").strip().lower()
        in {"complete", "completed", "done", "succeeded"}
        and str(item.get("task_id") or "")
    )

    index_payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_todo": TODO_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "schema": "complaint_generator.refactor_seed_bundle_index",
        "bundle_strategy": "goal_subgoal_ast",
        "completed_task_ids": sorted(completed_task_ids),
        "excluded_bundle_keys": sorted(excluded),
        "bundles": bundles,
    }
    _upstream_artifact_store().write_bundle_index_artifact(index_path, index_payload)
    return {
        "bundle_index_path": str(index_path),
        "bundle_index_duckdb_path": str(index_path.with_suffix(".duckdb")),
        "bundle_count": len(bundles),
        "task_count": sum(len(bundle.get("tasks", [])) for bundle in bundles.values()),
        "dynamic_task_count": dynamic_task_count,
        "pruned_task_ids": pruned_task_ids,
        "excluded_bundle_keys": sorted(excluded),
    }


def _taskboard_snapshot() -> dict[str, Any]:
    """Return the complete markdown board projection used by JSON and docs."""

    if not TODO_PATH.exists():
        return {"task_count": 0, "tasks": []}
    text = TODO_PATH.read_text(encoding="utf-8", errors="replace")
    headers = list(
        re.finditer(
            rf"^##\s+({re.escape(TASK_PREFIX)}\d+)\s+(.+?)\s*$",
            text,
            flags=re.MULTILINE,
        )
    )
    if not headers:
        parse_markdown_tasks, _task_status_counts = _upstream_task_board_helpers()
        tasks = []
        for task in parse_markdown_tasks(text):
            match = re.match(rf"({re.escape(TASK_PREFIX)}\d+)\b\s*(.*)", task.title)
            if match:
                tasks.append(
                    {
                        "task_id": match.group(1),
                        "checkbox_id": task.checkbox_id,
                        "title": match.group(2).strip(),
                        "status": task.status,
                    }
                )
        return {"task_count": len(tasks), "tasks": tasks}
    status_aliases = {
        "todo": "needed",
        "needed": "needed",
        "in_progress": "in-progress",
        "in-progress": "in-progress",
        "in progress": "in-progress",
        "running": "in-progress",
        "completed": "complete",
        "complete": "complete",
        "done": "complete",
        "blocked": "blocked",
    }
    tasks: list[dict[str, Any]] = []
    for index, header in enumerate(headers):
        block_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        block = text[header.end() : block_end]
        status_match = re.search(r"^- Status:\s*(\S+)", block, flags=re.MULTILINE)
        raw_status = status_match.group(1).strip().lower() if status_match else "todo"
        task_id = header.group(1)
        numeric_id = re.fullmatch(rf"{re.escape(TASK_PREFIX)}(\d+)", task_id)
        tasks.append(
            {
                "task_id": task_id,
                "checkbox_id": int(numeric_id.group(1)) if numeric_id else index + 1,
                "title": header.group(2).strip(),
                "status": status_aliases.get(raw_status, raw_status),
            }
        )
    return {"task_count": len(tasks), "tasks": tasks}


def _active_todo_task_ids() -> set[str]:
    """Return task ids that still represent runnable work on the markdown board."""

    return {
        str(item["task_id"])
        for item in _taskboard_snapshot()["tasks"]
        if item["status"] in {"needed", "in-progress"}
    }


def _task_ids_from_queue_payload(payload: dict[str, Any]) -> set[str]:
    task_ids = {
        str(item.get("task_id"))
        for item in payload.get("tasks", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    if not task_ids and payload.get("task_id"):
        task_ids.add(str(payload["task_id"]))
    return task_ids


def _queue_payload_contract(payload: dict[str, Any], active_task_ids: set[str]) -> dict[str, Any]:
    """Project an upstream bundle payload into the stable refactor queue contract."""

    tasks: list[dict[str, Any]] = []
    for raw_item in payload.get("tasks", []):
        if not isinstance(raw_item, dict) or str(raw_item.get("task_id") or "") not in active_task_ids:
            continue
        item = dict(raw_item)
        item["priority"] = str(item.get("priority") or "P2").strip()
        item["acceptance"] = _payload_strings(
            item.get("acceptance") or item.get("acceptance_criteria")
        )
        item["validation"] = _payload_strings(
            item.get("validation") or item.get("validation_commands")
        )
        goal_values = _payload_strings(
            item.get("parent_goal_id") or item.get("parent_goal_ids") or item.get("goal_id")
        )
        subgoal_values = _payload_strings(item.get("subgoal_id") or item.get("goal_packet_key"))
        _validate_task_payload_fields(
            {
                **item,
                "goal_id": goal_values,
                "subgoal_id": subgoal_values,
            },
            context=f"queue task {item.get('task_id') or '<unknown>'!r}",
        )
        tasks.append(item)
    task_ids = [str(item["task_id"]) for item in tasks]
    goal_ids = list(
        dict.fromkeys(
            value
            for item in tasks
            for value in _payload_strings(
                item.get("parent_goal_id") or item.get("parent_goal_ids") or item.get("goal_id")
            )[:1]
        )
    )
    subgoal_ids = list(
        dict.fromkeys(
            value
            for item in tasks
            for value in _payload_strings(item.get("subgoal_id") or item.get("goal_packet_key"))[:1]
        )
    )
    priorities = [str(item.get("priority") or "P2") for item in tasks]
    acceptance = list(
        dict.fromkeys(
            value
            for item in tasks
            for value in _payload_strings(item.get("acceptance"))
        )
    )
    validation = list(
        dict.fromkeys(
            value
            for item in tasks
            for value in _payload_strings(item.get("validation"))
        )
    )
    files = list(
        dict.fromkeys(
            str(value)
            for item in tasks
            for value in item.get("paths", [])
            if value
        )
    )
    titles = [str(item.get("title") or item["task_id"]) for item in tasks]
    contracted = dict(payload)
    contracted.update(
        {
            "schema": BUNDLE_TASK_PAYLOAD_SCHEMA,
            "supervisor": "refactor_agent_supervisor",
            "bundle_key": str(payload.get("bundle_key") or ""),
            "task_ids": task_ids,
            "tasks": tasks,
            "work_item_count": len(task_ids),
            "goal_id": goal_ids[0] if len(goal_ids) == 1 else goal_ids,
            "subgoal_id": subgoal_ids[0] if len(subgoal_ids) == 1 else subgoal_ids,
            "priority": min(priorities, key=lambda value: int(value[1:]) if value[1:].isdigit() else 99)
            if priorities
            else "P2",
            "title": "; ".join(titles),
            "acceptance": acceptance,
            "validation": validation,
            "files": files,
        }
    )
    if tasks:
        _validate_task_payload_fields(contracted, context=f"bundle {contracted['bundle_key']!r}")
    return contracted


def refill_bundle_queue(*, refill_floor: int, enabled: bool = True) -> dict[str, Any]:
    """Keep enough unique, runnable generated work items represented in the queue.

    Queue rows are goal/subgoal bundles, so the configured floor is measured in
    unique active taskboard work items rather than raw rows. This prevents the
    refiller from duplicating a cohesive active bundle merely to inflate a row
    count.
    """

    floor = max(0, int(refill_floor))
    result: dict[str, Any] = {
        "enabled": bool(enabled),
        "configured_floor": floor,
        "floor_unit": "active_taskboard_work_items",
        "submitted_bundle_count": 0,
        "submitted_task_ids": [],
        "queued_work_items_before": 0,
        "queued_work_items_after": 0,
        "floor_satisfied": floor == 0,
        "available_work_items": 0,
    }
    index_path = BUNDLE_DIR / "index.json"
    if not enabled:
        result["reason"] = "bundle submission disabled"
        return result
    if not index_path.exists():
        result["reason"] = "bundle index is missing"
        return result

    active_task_ids = _active_todo_task_ids()
    result["available_work_items"] = len(active_task_ids)
    if not active_task_ids or floor == 0:
        result["floor_satisfied"] = floor == 0
        result["reason"] = "no active taskboard work" if active_task_ids == set() else "floor is zero"
        return result

    TaskQueue = _task_queue_class()
    queue = TaskQueue(str(QUEUE_PATH))
    try:
        queued = queue.list(status="queued", limit=1000, task_types=TASK_TYPES)
        running = queue.list(status="running", limit=1000, task_types=TASK_TYPES)
        active_queue_items = [*queued, *running]
        active_bundle_keys = {
            str(item.get("payload", {}).get("bundle_key") or "")
            for item in active_queue_items
            if isinstance(item.get("payload"), dict)
        }
        covered_task_ids: set[str] = set()
        for item in active_queue_items:
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            covered_task_ids.update(_task_ids_from_queue_payload(payload) & active_task_ids)
        result["queued_work_items_before"] = len(covered_task_ids)

        build_bundle_task_payloads = _upstream_bundle_payload_builder()
        candidates: list[dict[str, Any]] = []
        rejected_payloads: list[dict[str, str]] = []
        for payload in build_bundle_task_payloads(index_path):
            try:
                candidates.append(_queue_payload_contract(dict(payload), active_task_ids))
            except (TypeError, ValueError) as exc:
                rejected_payloads.append(
                    {
                        "bundle_key": str(payload.get("bundle_key") or "")
                        if isinstance(payload, dict)
                        else "",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        result["rejected_bundle_count"] = len(rejected_payloads)
        if rejected_payloads:
            result["rejected_payloads"] = rejected_payloads
        candidates = [candidate for candidate in candidates if candidate["task_ids"]]
        candidates.sort(
            key=lambda item: (
                int(str(item.get("priority") or "P9")[1:])
                if str(item.get("priority") or "P9")[1:].isdigit()
                else 9,
                str(item.get("bundle_key") or ""),
            )
        )
        result["available_bundle_count"] = len(candidates)
        submitted_queue_ids: list[str] = []
        submitted_task_ids: list[str] = []
        for payload in candidates:
            if len(covered_task_ids) >= floor:
                break
            bundle_key = str(payload["bundle_key"])
            if bundle_key in active_bundle_keys:
                continue
            task_ids = set(payload["task_ids"]) & active_task_ids
            if not task_ids or task_ids <= covered_task_ids:
                continue
            submitted_queue_ids.append(
                queue.submit(
                    task_type=TASK_TYPES[0],
                    model_name=MODEL_NAME,
                    payload=payload,
                )
            )
            active_bundle_keys.add(bundle_key)
            covered_task_ids.update(task_ids)
            submitted_task_ids.extend(sorted(task_ids))

        result.update(
            {
                "submitted_bundle_count": len(submitted_queue_ids),
                "submitted_queue_ids": submitted_queue_ids,
                "submitted_task_ids": submitted_task_ids,
                "queued_work_items_after": len(covered_task_ids),
                "floor_satisfied": len(covered_task_ids) >= floor,
            }
        )
        if not result["floor_satisfied"]:
            result["reason"] = "fewer unique active generated work items are available than the configured floor"
        return result
    finally:
        close = getattr(queue, "close", None)
        if callable(close):
            close()


def _ensure_text(path: Path, text: str, *, overwrite: bool = True) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
    if existing == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _canonical_projection_status(value: Any) -> str:
    status = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if status in {"done", "complete", "completed"}:
        return "completed"
    if status in {"blocked", "on_hold"}:
        return "blocked"
    if status in {"active", "in_progress"}:
        return "in_progress"
    if status in {"ready", "todo", "queued", "needed", ""}:
        return "todo"
    return ""


def _durable_task_statuses() -> dict[str, str]:
    statuses: dict[str, str] = {}
    tasks: list[Any] = []
    if TODO_PATH.exists():
        parse_task_file = _upstream_portal_task_parser()
        tasks = list(parse_task_file(TODO_PATH, TASK_HEADER_PREFIX))
        for task in tasks:
            statuses[task.task_id] = _canonical_projection_status(task.status)
    state = _load_json_object(TASK_STATE_PATH)
    for task_id in state.get("blocked_task_ids", []) or []:
        task_id = str(task_id)
        if statuses.get(task_id) != "completed":
            statuses[task_id] = "blocked"
    for task_id in state.get("completed_task_ids", []) or []:
        statuses[str(task_id)] = "completed"
    active_task_id = str(state.get("active_task_id") or "").strip()
    if (
        active_task_id
        and (state.get("implementation_in_progress") or state.get("active_phase"))
        and statuses.get(active_task_id) != "completed"
    ):
        statuses[active_task_id] = "in_progress"
    try:
        receipts = _upstream_bundle_completion_receipt_loader()(BUNDLE_LANE_ROOT)
    except (ImportError, OSError, TypeError, ValueError):
        receipts = {}
    task_id_by_cid = {
        str(task.canonical_task_cid): str(task.task_id)
        for task in tasks
        if getattr(task, "canonical_task_cid", "") and getattr(task, "task_id", "")
    }
    for canonical_task_cid in receipts:
        task_id = task_id_by_cid.get(str(canonical_task_cid))
        if task_id:
            statuses[task_id] = "completed"
    return statuses


def _durable_canonical_task_statuses(statuses: dict[str, str]) -> dict[str, str]:
    status_rank = {"todo": 0, "in_progress": 1, "blocked": 2, "completed": 3}
    state = _load_json_object(TASK_STATE_PATH)
    identities = state.get("task_identities")
    identity_by_task_id = identities if isinstance(identities, dict) else {}
    parsed_by_task_id: dict[str, Any] = {}
    if TODO_PATH.exists():
        parse_task_file = _upstream_portal_task_parser()
        parsed_by_task_id = {
            task.task_id: task
            for task in parse_task_file(TODO_PATH, TASK_HEADER_PREFIX)
        }

    canonical_statuses: dict[str, str] = {}
    for task_id, status in statuses.items():
        status = _canonical_projection_status(status)
        if status not in status_rank:
            continue
        identity = identity_by_task_id.get(task_id)
        canonical_task_cid = (
            str(identity.get("canonical_task_cid") or "")
            if isinstance(identity, dict)
            else ""
        )
        if not canonical_task_cid:
            task = parsed_by_task_id.get(task_id)
            canonical_task_cid = str(getattr(task, "canonical_task_cid", "") or "")
        if not canonical_task_cid:
            continue
        previous = canonical_statuses.get(canonical_task_cid)
        if previous is None or status_rank[status] > status_rank[previous]:
            canonical_statuses[canonical_task_cid] = status
    return canonical_statuses


def _task_projection_signature(task: Any) -> tuple[Any, ...]:
    metadata = getattr(task, "metadata", {})
    return (
        str(getattr(task, "title", "") or "").strip().lower(),
        tuple(sorted(str(item) for item in (getattr(task, "depends_on", []) or []))),
        tuple(sorted(str(item) for item in (getattr(task, "outputs", []) or []))),
        tuple(sorted(str(item) for item in (getattr(task, "validation", []) or []))),
        str(getattr(task, "acceptance", "") or "").strip(),
        str(metadata.get("dedupe key") or "") if isinstance(metadata, dict) else "",
    )


def _statuses_for_canonical_tasks(
    path: Path,
    canonical_statuses: dict[str, str],
    *,
    direct_statuses: dict[str, str] | None = None,
    source_tasks_by_id: dict[str, list[Any]] | None = None,
) -> dict[str, str]:
    if not path.exists() or not (canonical_statuses or direct_statuses):
        return {}
    parse_task_file = _upstream_portal_task_parser()
    tasks_by_id: dict[str, list[Any]] = {}
    for task in parse_task_file(path, TASK_HEADER_PREFIX):
        tasks_by_id.setdefault(task.task_id, []).append(task)

    statuses: dict[str, str] = {}
    for task_id, tasks in tasks_by_id.items():
        matched = {
            canonical_statuses.get(str(task.canonical_task_cid or ""), "")
            for task in tasks
        }
        if len(matched) == 1 and "" not in matched:
            statuses[task_id] = matched.pop()
            continue
        source_tasks = (source_tasks_by_id or {}).get(task_id, [])
        if (
            direct_statuses
            and task_id in direct_statuses
            and len(tasks) == 1
            and len(source_tasks) == 1
            and _task_projection_signature(tasks[0])
            == _task_projection_signature(source_tasks[0])
        ):
            # Board namespaces intentionally alter canonical CIDs. A unique
            # task ID plus the same semantic signature is a safe fallback.
            statuses[task_id] = direct_statuses[task_id]
    return statuses


def _project_task_statuses(path: Path, statuses: dict[str, str]) -> list[str]:
    if not path.exists() or not statuses:
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    checkbox_pattern = re.compile(
        rf"^(?P<prefix>\s*[-*]\s+\[)(?P<mark>[^\]])(?P<suffix>\]\s+Task checkbox-\d+:\s+(?P<task_id>{re.escape(TASK_PREFIX)}\d+)\b.*)$"
    )
    header_pattern = re.compile(rf"^##\s+(?P<task_id>{re.escape(TASK_PREFIX)}\d+)\b")
    status_pattern = re.compile(r"^(?P<prefix>\s*-\s+Status:\s*).*$", re.IGNORECASE)
    current_task_id = ""
    updated: set[str] = set()
    output: list[str] = []
    for raw_line in lines:
        newline = "\n" if raw_line.endswith("\n") else ""
        line = raw_line[:-1] if newline else raw_line
        checkbox = checkbox_pattern.match(line)
        if checkbox:
            task_id = checkbox.group("task_id")
            status = _canonical_projection_status(statuses.get(task_id, ""))
            marks = {"todo": " ", "in_progress": "~", "completed": "x", "blocked": "!"}
            mark = marks.get(status, checkbox.group("mark"))
            if mark != checkbox.group("mark"):
                line = f"{checkbox.group('prefix')}{mark}{checkbox.group('suffix')}"
                updated.add(task_id)
        header = header_pattern.match(line)
        if header:
            current_task_id = header.group("task_id")
        status_line = status_pattern.match(line)
        status = _canonical_projection_status(statuses.get(current_task_id, ""))
        if status_line and status:
            projected = f"{status_line.group('prefix')}{status}"
            if projected != line:
                line = projected
                updated.add(current_task_id)
        output.append(line + newline)
    rendered = "".join(output)
    existing = "".join(lines)
    if rendered != existing:
        path.write_text(rendered, encoding="utf-8")
    return sorted(updated)


def synchronize_taskboard_statuses(
    *,
    include_primary: bool = True,
    protected_bundle_paths: set[Path] | None = None,
) -> dict[str, Any]:
    statuses = _durable_task_statuses()
    canonical_statuses = _durable_canonical_task_statuses(statuses)
    protected_paths = {
        path.resolve()
        for path in (protected_bundle_paths or set())
    }
    source_tasks_by_id: dict[str, list[Any]] = {}
    if TODO_PATH.exists():
        for task in _upstream_portal_task_parser()(TODO_PATH, TASK_HEADER_PREFIX):
            source_tasks_by_id.setdefault(task.task_id, []).append(task)
    updated: dict[str, list[str]] = {}
    if include_primary:
        primary_updates = _project_task_statuses(TODO_PATH, statuses)
        if primary_updates:
            updated[str(TODO_PATH)] = primary_updates
    if BUNDLE_DIR.exists():
        for path in sorted(BUNDLE_DIR.glob("*.todo.md")):
            if path.resolve() in protected_paths:
                continue
            task_updates = _project_task_statuses(
                path,
                _statuses_for_canonical_tasks(
                    path,
                    canonical_statuses,
                    direct_statuses=statuses,
                    source_tasks_by_id=source_tasks_by_id,
                ),
            )
            if task_updates:
                updated[str(path)] = task_updates
    return {
        "task_count": len(statuses),
        "completed_count": sum(status == "completed" for status in statuses.values()),
        "blocked_count": sum(status == "blocked" for status in statuses.values()),
        "updated_file_count": len(updated),
        "updated": updated,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _project_goal_tree_statuses(statuses: dict[str, str]) -> dict[str, Any]:
    if not GOALS_PATH.exists():
        return {"updated": False, "reason": "goals_missing", "updated_task_ids": []}
    payload = _load_json_object(GOALS_PATH)
    projected_status = {
        "todo": "needed",
        "in_progress": "in-progress",
        "blocked": "blocked",
        "completed": "complete",
    }
    updated_task_ids: list[str] = []
    for goal in payload.get("goals", []) or []:
        if not isinstance(goal, dict):
            continue
        for subgoal in goal.get("subgoals", []) or []:
            if not isinstance(subgoal, dict):
                continue
            for task in subgoal.get("tasks", []) or []:
                if not isinstance(task, dict):
                    continue
                task_id = str(task.get("task_id") or "")
                status = projected_status.get(statuses.get(task_id, ""))
                if status and task.get("status") != status:
                    task["status"] = status
                    updated_task_ids.append(task_id)

    taskboard = _taskboard_snapshot()
    taskboard_changed = payload.get("taskboard") != taskboard
    if taskboard_changed:
        payload["taskboard"] = taskboard
    if not updated_task_ids and not taskboard_changed:
        return {"updated": False, "reason": "current", "updated_task_ids": []}
    payload["status_projected_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_write_json(GOALS_PATH, payload)
    return {
        "updated": True,
        "reason": "projected",
        "updated_task_ids": sorted(set(updated_task_ids)),
        "taskboard_updated": taskboard_changed,
    }


def _project_bundle_index_statuses(statuses: dict[str, str]) -> dict[str, Any]:
    index_path = BUNDLE_DIR / "index.json"
    if not index_path.exists():
        return {"updated": False, "reason": "index_missing", "updated_task_ids": []}
    payload = _load_json_object(index_path)
    updated_task_ids: list[str] = []
    completed: set[str] = set()
    bundles = payload.get("bundles")
    bundle_values = bundles.values() if isinstance(bundles, dict) else bundles or []
    for bundle in bundle_values:
        if not isinstance(bundle, dict):
            continue
        for task in bundle.get("tasks", []) or []:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("task_id") or "")
            status = statuses.get(task_id)
            if status and task.get("status") != status:
                task["status"] = status
                updated_task_ids.append(task_id)
            if str(task.get("status") or "").strip().lower() in {
                "complete",
                "completed",
                "done",
                "succeeded",
            }:
                completed.add(task_id)
    projected_completed = sorted(completed)
    completed_changed = payload.get("completed_task_ids") != projected_completed
    if completed_changed:
        payload["completed_task_ids"] = projected_completed
    if not updated_task_ids and not completed_changed:
        return {"updated": False, "reason": "current", "updated_task_ids": []}
    payload["status_projected_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _upstream_artifact_store().write_bundle_index_artifact(index_path, payload)
    return {
        "updated": True,
        "reason": "projected",
        "updated_task_ids": sorted(set(updated_task_ids)),
        "completed_task_ids_updated": completed_changed,
        "duckdb_path": str(index_path.with_suffix(".duckdb")),
    }


def reconcile_task_projection_artifacts(*, skip_while_active: bool = True) -> dict[str, Any]:
    task_state = _load_json_object(TASK_STATE_PATH)
    active_phase = str(task_state.get("active_phase") or "").strip()
    active_task_id = str(task_state.get("active_task_id") or "").strip()
    manifest: dict[str, Any] = {}
    if BUNDLE_LANE_MANIFEST.exists():
        try:
            manifest = _upstream_artifact_store().read_artifact_fields(
                BUNDLE_LANE_MANIFEST,
                ("running_count", "lanes"),
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            manifest = {}
    parallel_running = int(manifest.get("running_count") or 0)
    if skip_while_active and (active_phase or parallel_running):
        statuses = _durable_task_statuses()
        protected_bundle_paths: set[Path] = set()
        for lane in manifest.get("lanes", []) or []:
            if not isinstance(lane, dict):
                continue
            todo_path = str(lane.get("todo_path") or "").strip()
            if not todo_path:
                continue
            path = Path(todo_path)
            protected_bundle_paths.add(
                path if path.is_absolute() else PROJECT_ROOT / path
            )
        bundle_shards = synchronize_taskboard_statuses(
            include_primary=False,
            protected_bundle_paths=protected_bundle_paths,
        )
        bundle_index = _project_bundle_index_statuses(statuses)
        return {
            "updated": bool(bundle_shards["updated_file_count"] or bundle_index["updated"]),
            "reason": "active_projection_reconciled",
            "active_task_id": active_task_id,
            "active_phase": active_phase,
            "parallel_running_count": parallel_running,
            "taskboard": {"updated": False, "reason": "active_implementation"},
            "bundle_shards": bundle_shards,
            "goals": {"updated": False, "reason": "active_implementation"},
            "bundle_index": bundle_index,
        }

    taskboard = synchronize_taskboard_statuses()
    statuses = _durable_task_statuses()
    goals = _project_goal_tree_statuses(statuses)
    bundle_index = _project_bundle_index_statuses(statuses)
    return {
        "updated": bool(taskboard["updated_file_count"] or goals["updated"] or bundle_index["updated"]),
        "reason": "reconciled",
        "taskboard": taskboard,
        "goals": goals,
        "bundle_index": bundle_index,
    }


def _todo_counts() -> dict[str, int]:
    if not TODO_PATH.exists():
        return {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0}
    counts = {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0}
    count_keys = {
        "needed": "needed",
        "in-progress": "in_progress",
        "complete": "complete",
        "blocked": "blocked",
    }
    for item in _taskboard_snapshot()["tasks"]:
        key = count_keys.get(str(item.get("status") or ""))
        if key:
            counts[key] += 1
    return counts


def _queue_counts() -> dict[str, int]:
    statuses = ("queued", "running", "completed", "failed")
    counts = {
        **{status: 0 for status in statuses},
        **{f"{status}_work_items": 0 for status in statuses},
    }
    if not QUEUE_PATH.exists():
        return counts
    TaskQueue = _task_queue_class()
    queue = TaskQueue(str(QUEUE_PATH))
    try:
        active_task_ids = _active_todo_task_ids()
        for status in statuses:
            items = queue.list(status=status, limit=1000, task_types=TASK_TYPES)
            counts[status] = queue.count(status=status, task_types=TASK_TYPES)
            task_ids: set[str] = set()
            for item in items:
                payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                task_ids.update(_task_ids_from_queue_payload(payload))
            if status in {"queued", "running"}:
                task_ids &= active_task_ids
            counts[f"{status}_work_items"] = len(task_ids)
        return counts
    finally:
        close = getattr(queue, "close", None)
        if callable(close):
            close()


def _priority_sort_key(value: Any) -> tuple[int, int, str]:
    """Return a deterministic ordering key for taskboard priority values."""

    priority = str(value or "").strip().upper()
    match = re.fullmatch(r"P(\d+)", priority)
    if match:
        return (0, int(match.group(1)), priority)
    return (1, 0, priority)


def _compact_string_list(value: Any) -> list[str]:
    """Normalize a queue payload collection into a stable compact JSON list."""

    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = list(value)
    else:
        values = []
    return sorted(
        {
            str(item).strip()
            for item in values
            if item is not None and str(item).strip()
        }
    )


def _queued_task_summaries(*, limit: int = 10) -> list[dict[str, Any]]:
    """List queued refactor work compactly in stable priority order.

    ``TaskQueue.list`` ordering is a storage detail and is not guaranteed to be
    priority-aware. Read a bounded board snapshot, normalize the fields useful
    to agents and automation, and apply explicit tie-breakers before limiting
    the result.
    """

    result_limit = max(0, int(limit))
    if result_limit == 0 or not QUEUE_PATH.exists():
        return []

    TaskQueue = _task_queue_class()
    queue = TaskQueue(str(QUEUE_PATH))
    try:
        summaries: list[dict[str, Any]] = []
        for item in queue.list(status="queued", limit=1000, task_types=TASK_TYPES):
            if not isinstance(item, dict):
                continue
            raw_payload = item.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            files = _compact_string_list(payload.get("files") or payload.get("paths"))
            summaries.append(
                {
                    "task_id": str(item.get("task_id") or ""),
                    "priority": str(payload.get("priority") or "").strip().upper() or None,
                    "goal_id": payload.get("goal_id"),
                    "subgoal_id": payload.get("subgoal_id"),
                    "title": str(payload.get("title") or "").strip() or None,
                    "files": files,
                }
            )

        summaries.sort(
            key=lambda item: (
                _priority_sort_key(item["priority"]),
                str(item["goal_id"] or ""),
                str(item["subgoal_id"] or ""),
                str(item["task_id"] or ""),
                str(item["title"] or ""),
            )
        )
        return summaries[:result_limit]
    finally:
        close = getattr(queue, "close", None)
        if callable(close):
            close()


def _collect_counts() -> tuple[dict[str, dict[str, int]], dict[str, str]]:
    """Return current board counts without making status reporting brittle."""

    errors: dict[str, str] = {}
    try:
        todo_counts = _todo_counts()
    except Exception as exc:
        todo_counts = {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0}
        errors["todo_counts_error"] = f"{type(exc).__name__}: {exc}"
    try:
        queue_counts = _queue_counts()
    except Exception as exc:
        queue_counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
        errors["queue_counts_error"] = f"{type(exc).__name__}: {exc}"
    return {"todo": todo_counts, "queue": queue_counts}, errors


def _scan_summary(scan: dict[str, Any] | None) -> dict[str, Any]:
    """Compact a full codebase scan into the durable handoff metrics."""

    if not isinstance(scan, dict):
        return {}
    signals = scan.get("signals") if isinstance(scan.get("signals"), dict) else {}
    summary = {
        "scanned_at": scan.get("scanned_at"),
        "python_file_count": int(scan.get("python_file_count") or 0),
        "python_total_lines": int(scan.get("python_total_lines") or 0),
        "test_file_count": int(scan.get("test_file_count") or 0),
        "direct_ipfs_import_count": int(signals.get("direct_ipfs_import_count") or 0),
        "sys_path_mutation_count": int(signals.get("sys_path_mutation_count") or 0),
        "broad_exception_count": int(signals.get("broad_exception_count") or 0),
        "wildcard_import_count": int(signals.get("wildcard_import_count") or 0),
        "silent_pass_count": int(signals.get("silent_pass_count") or 0),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _status_scan_summary(payload: dict[str, Any]) -> dict[str, Any]:
    direct = payload.get("scan_summary")
    if isinstance(direct, dict) and direct:
        return dict(direct)
    for seed_key in ("last_seed", "seed"):
        seed = payload.get(seed_key)
        if not isinstance(seed, dict):
            continue
        nested_summary = seed.get("scan_summary")
        if isinstance(nested_summary, dict) and nested_summary:
            return dict(nested_summary)
        summary = _scan_summary(seed.get("scan"))
        if summary:
            return summary
    return _scan_summary(payload.get("scan"))


def _status_counts(payload: dict[str, Any]) -> dict[str, Any]:
    direct = payload.get("counts")
    if isinstance(direct, dict) and direct:
        return dict(direct)
    for seed_key in ("last_seed", "seed"):
        seed = payload.get(seed_key)
        if isinstance(seed, dict) and isinstance(seed.get("counts"), dict):
            return dict(seed["counts"])
    return {}


def _seed_status_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Keep runtime status useful without embedding a complete source scan."""

    return {
        "counts": dict(result.get("counts") or {}),
        "scan_summary": _scan_summary(result.get("scan")),
        "objective_result": dict(result.get("objective_result") or {}),
        "backlog_result": dict(result.get("backlog_result") or {}),
        "bundle_seed": dict(result.get("bundle_seed") or {}),
        "status_projection": dict(result.get("status_projection") or {}),
        "queue_refill": dict(result.get("queue_refill") or {}),
    }


def _todo_task_header_count(path: Path = TODO_PATH) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(
        re.findall(
            rf"^##\s+{re.escape(TASK_PREFIX)}\d+\b",
            text,
            flags=re.MULTILINE,
        )
    )


def seed_taskboard(
    *,
    refill_floor: int = 20,
    submit_bundles: bool = True,
    force: bool = False,
    full_scan: bool = False,
    exclude_bundle_keys: set[str] | None = None,
) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    existing_goal_tree = _load_json_object(GOALS_PATH)
    scan = scan_codebase()
    goals = build_goals(scan)

    objective_changed = _ensure_text(OBJECTIVE_PATH, _render_objective_heap(goals), overwrite=True)
    existing_todo_headers = _todo_task_header_count()
    todo_changed = _ensure_text(TODO_PATH, _render_seed_todo(goals), overwrite=existing_todo_headers == 0)
    if existing_todo_headers:
        todo_changed = _append_missing_explicit_seed_tasks(TODO_PATH, goals) or todo_changed
    durable_statuses = _durable_task_statuses()
    bundle_seed = write_seed_bundle_index(
        goals,
        exclude_bundle_keys=exclude_bundle_keys,
        task_statuses=durable_statuses,
    )
    status_projection = synchronize_taskboard_statuses()
    todo_changed = bool(todo_changed or str(TODO_PATH) in status_projection["updated"])

    objective_result: dict[str, Any] = {"skipped": True, "reason": "fast_seed"}
    backlog_result: dict[str, Any] = {"skipped": True, "reason": "fast_seed"}
    if full_scan:
        objective_parser, run_objective_daemon = _upstream_objective_runner()
        objective_args = objective_parser().parse_args(
            [
                "--repo-root",
                str(PROJECT_ROOT),
                "--objective-path",
                str(OBJECTIVE_PATH),
                "--todo-path",
                str(TODO_PATH),
                "--discovery-dir",
                str(DISCOVERY_DIR),
                "--bundle-dir",
                str(BUNDLE_DIR),
                "--dataset-dir",
                str(DATASET_DIR),
                "--graph-path",
                str(GRAPH_PATH),
                "--task-prefix",
                TASK_PREFIX,
                "--objective-summary-prefix",
                "Refactor objective gap",
                "--max-findings",
                str(max(8, int(refill_floor))),
                "--surplus-findings-per-goal",
                "2",
                "--refine-objective-heap",
                "--no-reconcile-goal-completion",
                "--no-persist-ast-dataset",
                "--max-refinement-children",
                "2",
                "--max-refinement-depth",
                "3",
                "--queue-path",
                str(QUEUE_PATH),
                "--queue-task-type",
                "codex.todo_bundle",
                "--queue-model-name",
                MODEL_NAME,
            ]
        )
        objective_result = run_objective_daemon(objective_args)

        backlog_parser, run_backlog_refinery = _upstream_backlog_runner()
        backlog_argv = [
            "--repo-root",
            str(PROJECT_ROOT),
            "--todo-path",
            str(TODO_PATH),
            "--state-path",
            str(REFILL_STATE_PATH),
            "--strategy-path",
            str(STRATEGY_PATH),
            "--events-path",
            str(EVENTS_PATH),
            "--discovery-dir",
            str(DISCOVERY_DIR),
            "--objective-path",
            str(OBJECTIVE_PATH),
            "--bundle-dir",
            str(BUNDLE_DIR),
            "--dataset-dir",
            str(DATASET_DIR),
            "--task-prefix",
            TASK_PREFIX,
            "--task-header-prefix",
            TASK_HEADER_PREFIX,
            "--min-open-tasks",
            str(int(refill_floor)),
            "--max-findings",
            "8",
            "--objective-surplus-findings-per-goal",
            "2",
        ]
        if force:
            backlog_argv.append("--force")
        backlog_args = backlog_parser().parse_args(backlog_argv)
        backlog_result = run_backlog_refinery(backlog_args)

    queue_refill = refill_bundle_queue(refill_floor=refill_floor, enabled=submit_bundles)
    counts, count_errors = _collect_counts()
    taskboard = _taskboard_snapshot()
    synchronized_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    synchronization = {
        "synchronized_at": synchronized_at,
        "configured_refill_floor": max(0, int(refill_floor)),
        "goal_count": len(goals),
        "subgoal_count": sum(len(goal.get("subgoals", [])) for goal in goals),
        "task_count": len(flatten_tasks(goals)),
        "counts": counts,
        "queue_refill": queue_refill,
        "status_projection": status_projection,
        "objective_result": objective_result,
        "backlog_result": backlog_result,
    }
    goal_tree = _json_goal_tree(goals, scan, synchronization=synchronization, taskboard=taskboard)
    goal_tree = _merge_goal_tree_extensions(goal_tree, existing_goal_tree)
    GOALS_PATH.write_text(json.dumps(goal_tree, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_taskboard_doc(
        goals,
        scan,
        counts,
        objective_result,
        backlog_result,
        queue_refill=queue_refill,
        taskboard=taskboard,
    )
    _write_status(
        {
            "status": "seeded",
            "pid": 0,
            "pid_alive": False,
            "objective_path": str(OBJECTIVE_PATH),
            "todo_path": str(TODO_PATH),
            "bundle_dir": str(BUNDLE_DIR),
            "graph_path": str(GRAPH_PATH),
            "queue_path": str(QUEUE_PATH),
            "scan_summary": _scan_summary(scan),
            "counts": counts,
            **count_errors,
            "last_seed": {
                "counts": counts,
                "scan_summary": _scan_summary(scan),
                "objective_result": objective_result,
                "backlog_result": backlog_result,
                "bundle_seed": bundle_seed,
                "status_projection": status_projection,
                "queue_refill": queue_refill,
            },
        }
    )
    return {
        "objective_changed": objective_changed,
        "todo_changed": todo_changed,
        "counts": counts,
        "objective_result": objective_result,
        "backlog_result": backlog_result,
        "bundle_seed": bundle_seed,
        "status_projection": status_projection,
        "queue_refill": queue_refill,
        "scan": scan,
    }


def _write_taskboard_doc(
    goals: list[dict[str, Any]],
    scan: dict[str, Any],
    counts: dict[str, Any],
    objective_result: dict[str, Any],
    backlog_result: dict[str, Any],
    *,
    queue_refill: dict[str, Any],
    taskboard: dict[str, Any],
) -> None:
    todo_counts = counts.get("todo") or {}
    queue_counts = counts.get("queue") or {}
    task_statuses = {
        str(item.get("task_id")): str(item.get("status"))
        for item in taskboard.get("tasks", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    status_marks = {"needed": " ", "in-progress": "~", "complete": "x", "blocked": "!"}
    resolved_task_ids = _resolved_seed_task_ids(goals)
    lines = [
        "# Refactor Supervisor Taskboard",
        "",
        f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "",
        "This taskboard is generated by `scripts/refactor_agent_supervisor.py` and backed by",
        "`ipfs_accelerate_py.agent_supervisor` objective/refill/implementation supervisor modules.",
        "",
        "## Artifacts",
        "",
        f"- Objective heap: `{OBJECTIVE_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Markdown todo board: `{TODO_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Bundle dir: `{BUNDLE_DIR.relative_to(PROJECT_ROOT)}`",
        f"- Objective graph: `{GRAPH_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Queue path: `{QUEUE_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Status JSON: `{STATUS_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Daemon PID: `{PID_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Daemon log: `{LOG_PATH.relative_to(PROJECT_ROOT)}`",
        "",
        "## Counts",
        "",
        f"- Todo needed: {todo_counts.get('needed', 0)}",
        f"- Todo in progress: {todo_counts.get('in_progress', 0)}",
        f"- Todo complete: {todo_counts.get('complete', 0)}",
        f"- Todo blocked: {todo_counts.get('blocked', 0)}",
        f"- Bundle queue queued: {queue_counts.get('queued', 0)}",
        f"- Bundle queue running: {queue_counts.get('running', 0)}",
        f"- Bundle queue completed: {queue_counts.get('completed', 0)}",
        f"- Queued active work items: {queue_counts.get('queued_work_items', 0)}",
        f"- Running active work items: {queue_counts.get('running_work_items', 0)}",
        f"- Configured refill floor: {queue_refill.get('configured_floor', 0)} active work items",
        f"- Refill floor satisfied: {'yes' if queue_refill.get('floor_satisfied') else 'no'}",
        f"- Bundles submitted this cycle: {queue_refill.get('submitted_bundle_count', 0)}",
        f"- Objective tasks generated this cycle: {objective_result.get('generated_count', 0)}",
        f"- Backlog codebase tasks generated this cycle: {backlog_result.get('codebase_generated_count', 0)}",
        "",
        "## Scan Summary",
        "",
        f"- Python files scanned: {scan['python_file_count']}",
        f"- Python lines scanned: {scan['python_total_lines']}",
        f"- Test files scanned: {scan['test_file_count']}",
        f"- Direct `ipfs_datasets_py` import hits: {scan['signals']['direct_ipfs_import_count']}",
        f"- `sys.path` mutation hits: {scan['signals']['sys_path_mutation_count']}",
        f"- Broad `except Exception` hits: {scan['signals']['broad_exception_count']}",
        "",
        "## Operations",
        "",
        "- Inspect the current heartbeat, scan summary, and board/queue counts with "
        "`python scripts/refactor_agent_supervisor.py status`.",
        "- Stop the background supervisor and its managed workers cleanly with "
        "`python scripts/refactor_agent_supervisor.py stop`.",
        "- Each seed/daemon cycle regenerates this document and `refactor_goals.json` after "
        "deduplicating active goal/subgoal bundles and refilling queued work to the configured floor.",
        "",
    ]
    cross_links = _read_ipfs_p0_cross_links()
    if cross_links:
        _validate_ipfs_p0_cross_link_goals(cross_links, goals)
        lines.extend([*cross_links, ""])
    lines.extend(["## Goals", ""])
    for goal in goals:
        lines.append(f"### {goal['id']}: {goal['title']} ({goal['priority']})")
        lines.append("")
        for subgoal in goal.get("subgoals", []):
            lines.append(f"#### {subgoal['id']}: {subgoal['title']}")
            lines.append("")
            for task in subgoal.get("tasks", []):
                task_id = resolved_task_ids[id(task)]
                status = task_statuses.get(task_id, "unknown")
                lines.append(f"- [{status_marks.get(status, '?')}] [{task.priority}] {task.title}")
                if task.files:
                    lines.append(f"  - Files: {', '.join(f'`{f}`' for f in task.files)}")
                lines.append(f"  - Acceptance: {'; '.join(task.acceptance)}")
                lines.append(f"  - Validation: {'; '.join(f'`{v}`' for v in task.validation)}")
            lines.append("")
    seed_task_ids = set(resolved_task_ids.values())
    generated_tasks = [
        item
        for item in taskboard.get("tasks", [])
        if isinstance(item, dict) and item.get("task_id") not in seed_task_ids
    ]
    if generated_tasks:
        lines.extend(["## Generated and Refined Tasks", ""])
        for item in generated_tasks:
            mark = status_marks.get(str(item.get("status")), "?")
            lines.append(f"- [{mark}] {item.get('task_id')} {item.get('title')}")
        lines.append("")
    TASKBOARD_DOC_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _read_ipfs_p0_cross_links(path: Path | None = None) -> list[str]:
    """Return the canonical IPFS P0-to-refactor mapping for board projection.

    The execution backlog owns this mapping because its work-package IDs are the
    stable roadmap identifiers.  The generated taskboard projects the marked
    section verbatim so a seed cycle cannot silently discard or fork the map.
    """

    source_path = path or IPFS_EXECUTION_BACKLOG_PATH
    if not source_path.exists():
        return []

    text = source_path.read_text(encoding="utf-8")
    start_count = text.count(IPFS_P0_CROSS_LINKS_START)
    end_count = text.count(IPFS_P0_CROSS_LINKS_END)
    if start_count != 1 or end_count != 1:
        raise ValueError(
            f"{source_path} must contain exactly one P0 cross-link start/end marker pair"
        )

    before, remainder = text.split(IPFS_P0_CROSS_LINKS_START, 1)
    section, after = remainder.split(IPFS_P0_CROSS_LINKS_END, 1)
    if not before or not after or not section.strip():
        raise ValueError(f"{source_path} contains an empty or misplaced P0 cross-link section")
    section_lines = section.strip().splitlines()

    p0_workstreams: set[str] = set()
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and re.fullmatch(r"W\d+", cells[0]) and cells[3] == "P0":
            p0_workstreams.add(cells[0])

    mapped_workstreams: set[str] = set()
    for line in section_lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells:
            continue
        match = re.match(r"(W\d+)\b", cells[0])
        if not match:
            continue
        if len(cells) < 4 or not re.search(r"G\d+\.S\d+", cells[1]):
            raise ValueError(f"{source_path} has an incomplete cross-link row for {match.group(1)}")
        mapped_workstreams.add(match.group(1))

    if mapped_workstreams != p0_workstreams:
        missing = sorted(p0_workstreams - mapped_workstreams)
        unexpected = sorted(mapped_workstreams - p0_workstreams)
        raise ValueError(
            f"{source_path} P0 cross-link coverage mismatch; missing={missing}, unexpected={unexpected}"
        )
    return section_lines


def _validate_ipfs_p0_cross_link_goals(
    cross_links: list[str],
    goals: list[dict[str, Any]],
) -> None:
    referenced = set(re.findall(r"G\d+\.S\d+", "\n".join(cross_links)))
    available = {
        str(subgoal.get("id"))
        for goal in goals
        for subgoal in goal.get("subgoals", [])
        if subgoal.get("id")
    }
    unknown = sorted(referenced - available)
    if unknown:
        raise ValueError(f"IPFS P0 cross-links reference unknown refactor subgoals: {unknown}")


def _status_artifacts() -> dict[str, str]:
    """Return canonical artifact paths for the common daemon status contract."""

    return {
        "state_root": str(STATE_ROOT),
        "objective_path": str(OBJECTIVE_PATH),
        "todo_path": str(TODO_PATH),
        "bundle_dir": str(BUNDLE_DIR),
        "graph_path": str(GRAPH_PATH),
        "queue_path": str(QUEUE_PATH),
        "pid_file": str(PID_PATH),
        "status_file": str(STATUS_PATH),
        "log_file": str(LOG_PATH),
    }


def _status_last_error(payload: dict[str, Any]) -> str | None:
    if payload.get("last_error") is not None:
        return str(payload["last_error"])
    for key, value in payload.items():
        if value and (key == "error" or key.endswith("_error")):
            return str(value)
    return None


def _write_status(payload: dict[str, Any]) -> None:
    """Atomically persist a complete, stable operator handoff snapshot."""

    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    previous = _load_json_object(STATUS_PATH) if STATUS_PATH.exists() else {}
    current = {**previous, **dict(payload)}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    current["schema"] = STATUS_SCHEMA
    current["updated_at"] = now
    current["heartbeat"] = now
    current["heartbeat_at"] = now
    existing_artifacts = current.get("artifacts")
    current["artifacts"] = {
        **_status_artifacts(),
        **(dict(existing_artifacts) if isinstance(existing_artifacts, dict) else {}),
    }

    try:
        current["pid"] = int(current.get("pid") or 0)
    except (TypeError, ValueError):
        current["pid"] = 0
    if "pid_alive" not in payload:
        current["pid_alive"] = _pid_alive(current["pid"])

    scan_summary = _status_scan_summary(current)
    if not scan_summary and GOALS_PATH.exists():
        scan_summary = _scan_summary(_load_json_object(GOALS_PATH).get("scan"))
    current["scan_summary"] = scan_summary

    counts = _status_counts(current)
    if not counts:
        counts, count_errors = _collect_counts()
        current.update(count_errors)
    current["counts"] = counts
    current["todo_counts"] = dict(counts.get("todo") or {})
    current["queue_counts"] = dict(counts.get("queue") or {})
    current["last_error"] = _status_last_error(current)

    temporary_path = STATUS_PATH.with_name(f".{STATUS_PATH.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary_path, STATUS_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        stat_path = Path(f"/proc/{pid}/stat")
        if stat_path.exists():
            try:
                # A zombie has exited and only awaits parent reaping; it is not a live daemon.
                if stat_path.read_text(encoding="utf-8", errors="replace").split()[2] == "Z":
                    return False
            except (OSError, IndexError):
                pass
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _remove_owned_pid_file(pid_path: Path, *, pid: int) -> str | None:
    """Remove this process's PID file, returning an actionable filesystem error."""

    try:
        if pid_path.exists() and pid_path.read_text(encoding="utf-8").strip() == str(pid):
            pid_path.unlink()
    except OSError as exc:
        return f"Could not remove owned PID file {pid_path}: {type(exc).__name__}: {exc}"
    return None


def run_daemon(*, interval_s: float, refill_floor: int, once: bool = False) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    host = socket.gethostname()
    cycle = 0
    last_result: dict[str, Any] = {}
    stop_reason = "completed" if once else "stopped"

    def _stop(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    _write_status(
        {
            "status": "starting",
            "pid": os.getpid(),
            "pid_alive": True,
            "host": host,
            "cycle": cycle,
            "queue_path": str(QUEUE_PATH),
            "goals_path": str(GOALS_PATH),
            "taskboard_doc_path": str(TASKBOARD_DOC_PATH),
        }
    )
    try:
        while True:
            cycle += 1
            result = seed_taskboard(refill_floor=refill_floor)
            last_result = result
            seed_summary = _seed_status_summary(result)
            _write_status(
                {
                    "status": "running",
                    "pid": os.getpid(),
                    "pid_alive": True,
                    "host": host,
                    "cycle": cycle,
                    "queue_path": str(QUEUE_PATH),
                    "goals_path": str(GOALS_PATH),
                    "taskboard_doc_path": str(TASKBOARD_DOC_PATH),
                    "scan_summary": seed_summary["scan_summary"],
                    "counts": seed_summary["counts"],
                    "last_seed": seed_summary,
                }
            )
            if once:
                break
            time.sleep(max(5.0, float(interval_s)))
    except KeyboardInterrupt:
        stop_reason = "signal"
    finally:
        pid_cleanup_error = _remove_owned_pid_file(PID_PATH, pid=os.getpid())
        final_payload: dict[str, Any] = {
            "status": "stopped",
            "pid": os.getpid(),
            "pid_alive": False,
            "host": host,
            "cycle": cycle,
            "stop_reason": stop_reason,
            "stopped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid_cleanup_error": pid_cleanup_error,
            "last_error": pid_cleanup_error,
        }
        if last_result:
            seed_summary = _seed_status_summary(last_result)
            final_payload.update(
                {
                    "scan_summary": seed_summary["scan_summary"],
                    "counts": seed_summary["counts"],
                    "last_seed": seed_summary,
                }
            )
        _write_status(final_payload)
    return last_result


def start_daemon(args: argparse.Namespace) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = 0
        if _pid_alive(pid):
            return {"status": "already_running", "pid": pid, "status_path": str(STATUS_PATH)}

    seed_result = seed_taskboard(refill_floor=args.refill_floor, full_scan=False)
    SUPERVISOR_STATE_DIR.mkdir(parents=True, exist_ok=True)
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor",
        "--todo-path",
        str(TODO_PATH),
        "--state-dir",
        str(SUPERVISOR_STATE_DIR),
        "--task-prefix",
        TASK_PREFIX,
        "--state-prefix",
        "complaint_generator_refactor",
        "--external-reservation-manifest-path",
        str(BUNDLE_LANE_MANIFEST),
        "--implement",
        "--implementation-timeout",
        str(float(args.implementation_timeout)),
        "--llm-merge-resolver-command",
        merge_resolver_command(),
        "--llm-merge-resolver-timeout-seconds",
        str(float(args.merge_resolver_timeout)),
        "--merge-reconciliation-max-merges",
        str(int(args.merge_reconciliation_max_merges)),
        "--auto-commit-generated-dirty",
        "--generated-dirty-commit-subject",
        "Agent: commit refactor supervisor generated outputs",
        "--generated-dirty-max-paths",
        str(int(args.generated_dirty_max_paths)),
        "--generated-dirty-stale-lock-seconds",
        str(float(args.generated_dirty_stale_lock_seconds)),
        "--generated-dirty-path",
        str(TASKBOARD_DOC_PATH),
        "--check-interval",
        str(float(args.interval_s)),
        "--daemon-interval",
        str(float(args.daemon_interval_s)),
        "--max-restarts",
        str(int(args.max_restarts)),
        "--worktree-root",
        str(WORKTREE_ROOT),
        "--worktree-submodule-path",
        "ipfs_datasets_py/ipfs_accelerate_py",
        "--objective-refill-scan",
        "--objective-path",
        str(OBJECTIVE_PATH),
        "--objective-graph-path",
        str(GRAPH_PATH),
        "--objective-bundle-dir",
        str(BUNDLE_DIR),
        "--objective-dataset-dir",
        str(DATASET_DIR),
        "--objective-discovery-dir",
        str(DISCOVERY_DIR),
        "--objective-scan-min-open-tasks",
        str(int(args.refill_floor)),
        "--objective-scan-max-findings",
        "6",
        "--objective-surplus-findings-per-goal",
        "2",
        "--objective-max-refinement-children",
        "2",
        "--objective-max-refinement-depth",
        "3",
        "--objective-mission-term",
        "adversarial_harness",
        "--codebase-refill-scan",
        "--allow-codebase-refill-with-objective-work",
        "--codebase-scan-min-open-tasks",
        str(int(args.refill_floor)),
        "--codebase-scan-max-findings",
        "6",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ACCELERATE_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    log_handle = LOG_PATH.open("a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    time.sleep(1.0)
    seed_summary = _seed_status_summary(seed_result)
    started = _pid_alive(proc.pid)
    if started:
        PID_PATH.write_text(str(proc.pid) + "\n", encoding="utf-8")
    else:
        PID_PATH.unlink(missing_ok=True)
    payload = {
        "status": "started" if started else "start_failed",
        "pid": proc.pid,
        "pid_alive": started,
        "exit_code": proc.poll(),
        "status_path": str(STATUS_PATH),
        "log_path": str(LOG_PATH),
        "upstream_supervisor": True,
        "upstream_status_path": str(UPSTREAM_SUPERVISOR_STATUS_PATH),
        "scan_summary": seed_summary["scan_summary"],
        "counts": seed_summary["counts"],
        "seed": seed_summary,
        "command": cmd,
    }
    _write_status(payload)
    return payload


def run_parallel_bundle_supervisor(args: argparse.Namespace, *, start: bool) -> dict[str, Any]:
    if start and BUNDLE_SCHEDULER_PID_PATH.exists():
        try:
            existing_pid = int(BUNDLE_SCHEDULER_PID_PATH.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            existing_pid = 0
        if _pid_alive(existing_pid):
            return {
                "status": "already_running",
                "pid": existing_pid,
                "pid_alive": True,
                "manifest_path": str(BUNDLE_LANE_MANIFEST),
                "manifest_duckdb_path": str(BUNDLE_LANE_MANIFEST.with_suffix(".duckdb")),
                "log_path": str(BUNDLE_SCHEDULER_LOG_PATH),
            }
        BUNDLE_SCHEDULER_PID_PATH.unlink(missing_ok=True)

    exclude_bundle_keys = active_bundle_keys() if start and args.skip_active_bundle else set()
    seed_result = seed_taskboard(
        refill_floor=args.refill_floor,
        full_scan=bool(args.full_scan),
        exclude_bundle_keys=exclude_bundle_keys,
    )
    bundle_index_path = BUNDLE_DIR / "index.json"
    argv = [
        "--bundle-index-path",
        str(bundle_index_path),
        "--repo-root",
        str(PROJECT_ROOT),
        "--state-root",
        str(BUNDLE_LANE_ROOT),
        "--worktree-root",
        str(BUNDLE_LANE_ROOT / "worktrees"),
        "--log-dir",
        str(BUNDLE_LANE_ROOT / "logs"),
        "--manifest-path",
        str(BUNDLE_LANE_MANIFEST),
        "--external-task-state-path",
        str(TASK_STATE_PATH),
        "--task-prefix",
        TASK_PREFIX,
        "--max-lanes",
        str(int(args.max_lanes)),
        "--poll-interval",
        str(float(args.interval_s)),
        "--daemon-interval",
        str(float(args.daemon_interval_s)),
        "--check-interval",
        str(float(args.interval_s)),
        "--max-restarts",
        str(int(args.max_restarts)),
        "--implementation-timeout",
        str(float(args.implementation_timeout)),
        "--worktree-submodule-path",
        "ipfs_datasets_py/ipfs_accelerate_py",
        "--llm-merge-resolver-command",
        merge_resolver_command(),
        "--llm-merge-resolver-timeout-seconds",
        str(float(args.merge_resolver_timeout)),
        "--merge-reconciliation-max-merges",
        str(int(args.merge_reconciliation_max_merges)),
        "--auto-commit-generated-dirty",
        "--generated-dirty-commit-subject",
        "Agent: commit refactor lane generated outputs",
        "--generated-dirty-max-paths",
        str(int(args.generated_dirty_max_paths)),
        "--generated-dirty-stale-lock-seconds",
        str(float(args.generated_dirty_stale_lock_seconds)),
        "--generated-dirty-path",
        str(TASKBOARD_DOC_PATH),
        "--coordination-path",
        str(BUNDLE_COORDINATION_PATH),
        "--claimant-did",
        "did:web:complaint-generator.local",
        "--lease-ms",
        str(int(args.lease_ms)),
    ]
    argv.append("--implement" if args.implement else "--no-implement")
    seed_summary = {
        "counts": seed_result.get("counts"),
        "bundle_seed": seed_result.get("bundle_seed"),
    }

    if not start:
        parser_factory, run_bundle_supervisor = _upstream_bundle_runner()
        bundle_args = parser_factory().parse_args(argv)
        payload = run_bundle_supervisor(bundle_args)
        payload["seed"] = seed_summary
        payload["mode"] = "plan_parallel"
        _write_status(
            {
                "last_parallel": {
                    "mode": "plan_parallel",
                    "planned_count": payload.get("planned_count", 0),
                    "claimable_count": payload.get("claimable_count", 0),
                    "blocked_count": payload.get("blocked_count", 0),
                    "seed": seed_summary,
                }
            }
        )
        return payload

    BUNDLE_LANE_ROOT.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "ipfs_accelerate_py.agent_supervisor.bundle_supervisor",
        *argv,
        "--start",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ACCELERATE_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    log_handle = BUNDLE_SCHEDULER_LOG_PATH.open("ab")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    time.sleep(1.0)
    started = _pid_alive(process.pid)
    if started:
        BUNDLE_SCHEDULER_PID_PATH.write_text(f"{process.pid}\n", encoding="utf-8")
    else:
        BUNDLE_SCHEDULER_PID_PATH.unlink(missing_ok=True)
    payload = {
        "status": "started" if started else "start_failed",
        "mode": "start_parallel",
        "pid": process.pid,
        "pid_alive": started,
        "exit_code": process.poll(),
        "manifest_path": str(BUNDLE_LANE_MANIFEST),
        "manifest_duckdb_path": str(BUNDLE_LANE_MANIFEST.with_suffix(".duckdb")),
        "coordination_path": str(BUNDLE_COORDINATION_PATH),
        "log_path": str(BUNDLE_SCHEDULER_LOG_PATH),
        "seed": seed_summary,
        "command": command,
    }
    _write_status(
        {
            "parallel_scheduler": {
                "status": payload["status"],
                "pid": process.pid,
                "pid_alive": started,
                "manifest_path": str(BUNDLE_LANE_MANIFEST),
                "manifest_duckdb_path": str(BUNDLE_LANE_MANIFEST.with_suffix(".duckdb")),
                "log_path": str(BUNDLE_SCHEDULER_LOG_PATH),
            },
            "last_parallel": payload,
        }
    )
    return payload


def stop_parallel_bundle_supervisor() -> dict[str, Any]:
    if not BUNDLE_SCHEDULER_PID_PATH.exists():
        return {
            "status": "not_running",
            "pid": 0,
            "pid_alive": False,
            "manifest_path": str(BUNDLE_LANE_MANIFEST),
            "manifest_duckdb_path": str(BUNDLE_LANE_MANIFEST.with_suffix(".duckdb")),
        }
    try:
        pid = int(BUNDLE_SCHEDULER_PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = 0
    if not _pid_alive(pid):
        BUNDLE_SCHEDULER_PID_PATH.unlink(missing_ok=True)
        return {
            "status": "not_running",
            "pid": pid,
            "pid_alive": False,
            "manifest_path": str(BUNDLE_LANE_MANIFEST),
            "manifest_duckdb_path": str(BUNDLE_LANE_MANIFEST.with_suffix(".duckdb")),
        }

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(STOP_POLL_SECONDS)
    stopped = not _pid_alive(pid)
    if stopped:
        BUNDLE_SCHEDULER_PID_PATH.unlink(missing_ok=True)
    result = {
        "status": "stopped" if stopped else "stopping",
        "pid": pid,
        "pid_alive": not stopped,
        "signal": "SIGTERM",
        "manifest_path": str(BUNDLE_LANE_MANIFEST),
        "manifest_duckdb_path": str(BUNDLE_LANE_MANIFEST.with_suffix(".duckdb")),
        "log_path": str(BUNDLE_SCHEDULER_LOG_PATH),
    }
    _write_status({"parallel_scheduler": result})
    return result


def active_bundle_keys() -> set[str]:
    state_path = SUPERVISOR_STATE_DIR / "complaint_generator_refactor_task_state.json"
    if not state_path.exists() or not TODO_PATH.exists():
        return set()
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    active_task_id = str(state.get("active_task_id") or "").strip()
    if not active_task_id:
        return set()
    text = TODO_PATH.read_text(encoding="utf-8", errors="replace")
    block_pattern = re.compile(
        rf"^##\s+{re.escape(active_task_id)}\s+.*?(?=^\s*-\s+\[\s?\]\s+Task checkbox-|^##\s+{re.escape(TASK_PREFIX)}|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = block_pattern.search(text)
    if not match:
        return set()
    bundle_match = re.search(r"^-\s+Bundle:\s*(.+?)\s*$", match.group(0), flags=re.MULTILINE)
    if not bundle_match:
        return set()
    return {bundle_match.group(1).strip()}


def merge_event_paths() -> list[Path]:
    paths: list[Path] = []
    for root in (SUPERVISOR_STATE_DIR, BUNDLE_LANE_ROOT):
        if not root.exists():
            continue
        for path in root.rglob("*events.jsonl"):
            if path.is_file():
                paths.append(path)
    return sorted(dict.fromkeys(paths))


def _implementation_activity_snapshot() -> dict[str, Any]:
    task_state = _load_json_object(TASK_STATE_PATH)
    active_phase = str(task_state.get("active_phase") or "").strip()
    active_task_id = str(task_state.get("active_task_id") or "").strip()
    parallel_running_count = 0
    if BUNDLE_LANE_MANIFEST.exists():
        try:
            manifest = _upstream_artifact_store().read_artifact_fields(
                BUNDLE_LANE_MANIFEST,
                ("running_count",),
            )
            parallel_running_count = int(manifest.get("running_count") or 0)
        except Exception:
            parallel_running_count = 0
    return {
        "active": bool(active_phase or active_task_id or parallel_running_count),
        "active_task_id": active_task_id,
        "active_phase": active_phase,
        "parallel_running_count": parallel_running_count,
    }


def _taskboard_status_by_id() -> dict[str, str]:
    return {
        str(task.get("task_id") or ""): str(task.get("status") or "")
        for task in _taskboard_snapshot().get("tasks", [])
        if str(task.get("task_id") or "")
    }


def _try_acquire_watchdog_checkout_lock(
    *,
    task_id: str,
    branch: str,
) -> dict[str, Any]:
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.checkout_lock import (
        checkout_lock_metadata,
        checkout_mutation_lock_path,
    )

    lock_path = checkout_mutation_lock_path(PROJECT_ROOT)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = f"watchdog-{os.getpid()}-{time.time_ns()}"
    for _attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            existing = _load_json_object(lock_path)
            try:
                owner_pid = int(existing.get("pid") or 0)
            except (TypeError, ValueError):
                owner_pid = 0
            try:
                age_seconds = max(0.0, time.time() - lock_path.stat().st_mtime)
            except OSError:
                continue
            if (owner_pid and _pid_alive(owner_pid)) or age_seconds < 2.0:
                return {
                    "acquired": False,
                    "reason": "checkout_mutation_lock_active",
                    "lock_path": str(lock_path),
                    "owner": existing,
                }
            try:
                lock_path.unlink()
            except OSError as exc:
                return {
                    "acquired": False,
                    "reason": "stale_checkout_lock_remove_failed",
                    "lock_path": str(lock_path),
                    "error": f"{type(exc).__name__}: {exc}",
                    "owner": existing,
                }
            continue

        metadata = checkout_lock_metadata(
            kind="merge",
            repo_root=PROJECT_ROOT,
            task_id=task_id,
            branch=branch,
            extra={
                "operation": "external_merge_watchdog",
                "claim_token": token,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        try:
            os.write(descriptor, (json.dumps(metadata, sort_keys=True) + "\n").encode("utf-8"))
        finally:
            os.close(descriptor)
        return {
            "acquired": True,
            "reason": "acquired",
            "lock_path": str(lock_path),
            "claim_token": token,
        }
    return {
        "acquired": False,
        "reason": "checkout_mutation_lock_raced",
        "lock_path": str(lock_path),
    }


def _release_watchdog_checkout_lock(claim: dict[str, Any]) -> None:
    if not claim.get("acquired"):
        return
    lock_path = Path(str(claim.get("lock_path") or ""))
    if not lock_path.exists():
        return
    current = _load_json_object(lock_path)
    if current.get("claim_token") != claim.get("claim_token"):
        return
    lock_path.unlink(missing_ok=True)


def resolve_merge_conflicts_once(*, timeout_seconds: float = 900.0, max_events: int = 1) -> dict[str, Any]:
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.merge_resolver import (
        MergeResolverRegistry,
        active_merge_matches_payload,
        invoke_llm_resolver,
        iter_jsonl,
        latest_failed_merge_event,
        merge_in_progress,
        resolver_payload,
        unmerged_paths,
        validate_resolved_paths,
    )

    activity = _implementation_activity_snapshot()
    if activity["active"]:
        payload = {
            "status": "checked",
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event_log_count": 0,
            "found_count": 0,
            "applied_count": 0,
            "attempted_count": 0,
            "results": [
                {
                    "found": False,
                    "skipped": True,
                    "skip_reason": "implementation_active",
                    **activity,
                }
            ],
        }
        _atomic_write_json(MERGE_RESOLVER_STATUS_PATH, payload)
        return payload

    results: list[dict[str, Any]] = []
    attempted = 0
    task_statuses = _taskboard_status_by_id()
    registry = MergeResolverRegistry(
        MERGE_RESOLVER_REGISTRY_DIR,
        lease_timeout_seconds=max(1.0, float(timeout_seconds) + 30.0),
    )
    for events_path in merge_event_paths():
        try:
            event = latest_failed_merge_event(iter_jsonl(events_path))
            if event is None:
                results.append({"events_path": str(events_path), "found": False})
                continue
            payload = resolver_payload(
                events_path=events_path,
                repo_root=PROJECT_ROOT,
                prompt_heading="Resolve this complaint-generator autonomous refactor merge conflict.",
                completion_rule="Leave the repository merge-clean and preserve the implemented task intent.",
                extra_rules=[
                    "Prefer the smallest conflict resolution that keeps tests and task acceptance criteria meaningful.",
                    "Do not discard unrelated user changes in the main checkout.",
                    "If a generated worktree is involved, resolve inside that worktree and commit the merge there when appropriate.",
                ],
            )
            if not payload.get("found"):
                results.append({"events_path": str(events_path), "found": False})
                continue
            workspace = Path(str(payload.get("repo_root") or PROJECT_ROOT)).resolve()
            task_id = str(payload.get("task_id") or "")
            if task_statuses.get(task_id) == "complete":
                results.append(
                    {
                        "events_path": str(events_path),
                        "found": True,
                        "task_id": task_id,
                        "workspace": str(workspace),
                        "conflict_fingerprint": payload.get("conflict_fingerprint"),
                        "skipped": True,
                        "skip_reason": "task_already_completed",
                    }
                )
                continue
            if attempted >= max(1, int(max_events)):
                results.append(
                    {
                        "events_path": str(events_path),
                        "found": True,
                        "task_id": payload.get("task_id"),
                        "skipped": True,
                        "skip_reason": "max_events reached for this watchdog cycle",
                    }
                )
                continue
            checkout_claim = _try_acquire_watchdog_checkout_lock(
                task_id=task_id,
                branch=str(payload.get("branch") or ""),
            )
            if not checkout_claim.get("acquired"):
                results.append(
                    {
                        "events_path": str(events_path),
                        "found": True,
                        "task_id": task_id,
                        "workspace": str(workspace),
                        "conflict_fingerprint": payload.get("conflict_fingerprint"),
                        "skipped": True,
                        "skip_reason": str(checkout_claim.get("reason") or "checkout_lock_unavailable"),
                        "checkout_lock": checkout_claim,
                    }
                )
                continue
            try:
                live_unmerged_paths = unmerged_paths(workspace)
                live_merge = merge_in_progress(workspace)
                if not live_merge and not live_unmerged_paths:
                    results.append(
                        {
                            "events_path": str(events_path),
                            "found": True,
                            "task_id": task_id,
                            "workspace": str(workspace),
                            "conflict_fingerprint": payload.get("conflict_fingerprint"),
                            "skipped": True,
                            "skip_reason": "merge_not_active",
                        }
                    )
                    continue
                operation_match = active_merge_matches_payload(payload, workspace)
                if not operation_match.get("matches"):
                    results.append(
                        {
                            "events_path": str(events_path),
                            "found": True,
                            "task_id": task_id,
                            "workspace": str(workspace),
                            "conflict_fingerprint": payload.get("conflict_fingerprint"),
                            "skipped": True,
                            "skip_reason": str(operation_match.get("reason") or "merge_identity_mismatch"),
                            "operation_match": operation_match,
                        }
                    )
                    continue
                claim = registry.acquire(
                    event,
                    owner_id=f"complaint-generator-watchdog-{os.getpid()}",
                    lease_seconds=max(1.0, float(timeout_seconds) + 30.0),
                )
                if claim is None:
                    results.append(
                        {
                            "events_path": str(events_path),
                            "found": True,
                            "task_id": payload.get("task_id"),
                            "workspace": str(workspace),
                            "conflict_fingerprint": payload.get("conflict_fingerprint"),
                            "skipped": True,
                            "skip_reason": "resolver_claim_unavailable",
                        }
                    )
                    continue
                attempted += 1
                try:
                    applied = invoke_llm_resolver(
                        payload,
                        command_template=merge_resolver_command(),
                        timeout_seconds=timeout_seconds,
                    )
                    remaining_unmerged_paths = unmerged_paths(workspace)
                    merge_still_active = merge_in_progress(workspace)
                    resolution_validation = validate_resolved_paths(workspace, live_unmerged_paths)
                    resolved = bool(
                        applied.get("applied")
                        and not remaining_unmerged_paths
                        and not merge_still_active
                        and resolution_validation.get("valid")
                    )
                    error = "" if resolved else str(
                        applied.get("apply_error")
                        or applied.get("llm_stderr")
                        or (
                            "resolved paths failed marker or Python syntax validation"
                            if not resolution_validation.get("valid")
                            else ""
                        )
                        or "resolver returned without completing the merge"
                    )
                    receipt_path = registry.release(
                        claim,
                        succeeded=resolved,
                        outcome={
                            "applied": resolved,
                            "llm_returncode": applied.get("llm_returncode"),
                            "remaining_unmerged_paths": remaining_unmerged_paths,
                            "merge_still_active": merge_still_active,
                            "resolution_validation": resolution_validation,
                        },
                        error=error,
                    )
                except Exception as exc:
                    registry.release(claim, succeeded=False, error=str(exc))
                    raise
                results.append(
                    {
                        "events_path": str(events_path),
                        "found": True,
                        "task_id": applied.get("task_id"),
                        "workspace": str(workspace),
                        "conflict_fingerprint": payload.get("conflict_fingerprint"),
                        "applied": resolved,
                        "llm_returncode": applied.get("llm_returncode"),
                        "apply_error": applied.get("apply_error", ""),
                        "remaining_unmerged_paths": remaining_unmerged_paths,
                        "merge_still_active": merge_still_active,
                        "resolution_validation": resolution_validation,
                        "quarantine_receipt": str(receipt_path) if receipt_path else "",
                    }
                )
            finally:
                _release_watchdog_checkout_lock(checkout_claim)
        except Exception as exc:
            results.append({"events_path": str(events_path), "error": str(exc)})
    payload = {
        "status": "checked",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_log_count": len(results),
        "found_count": sum(1 for item in results if item.get("found")),
        "applied_count": sum(1 for item in results if item.get("applied")),
        "attempted_count": attempted,
        "results": results,
    }
    _atomic_write_json(MERGE_RESOLVER_STATUS_PATH, payload)
    return payload


def run_merge_resolver_watchdog(*, interval_s: float, timeout_seconds: float, once: bool = False) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    MERGE_RESOLVER_PID_PATH.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    cycle = 0
    last: dict[str, Any] = {}

    def _stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        while True:
            cycle += 1
            last = resolve_merge_conflicts_once(timeout_seconds=timeout_seconds, max_events=1)
            try:
                last["task_projection"] = reconcile_task_projection_artifacts()
            except Exception as exc:
                last["task_projection"] = {
                    "updated": False,
                    "reason": "projection_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            last["cycle"] = cycle
            last["status"] = "running" if not once else "checked"
            MERGE_RESOLVER_STATUS_PATH.write_text(json.dumps(last, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if once:
                break
            time.sleep(max(10.0, float(interval_s)))
    except KeyboardInterrupt:
        last = {"status": "stopped", "cycle": cycle, "last": last}
        MERGE_RESOLVER_STATUS_PATH.write_text(json.dumps(last, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        try:
            if MERGE_RESOLVER_PID_PATH.exists() and MERGE_RESOLVER_PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                MERGE_RESOLVER_PID_PATH.unlink()
        except OSError as exc:
            cleanup_error = {
                "path": str(MERGE_RESOLVER_PID_PATH),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            last["pid_cleanup_error"] = cleanup_error
            LOGGER.error(
                "merge resolver watchdog could not remove its PID file %s: %s: %s",
                MERGE_RESOLVER_PID_PATH,
                type(exc).__name__,
                exc,
            )
            try:
                _atomic_write_json(MERGE_RESOLVER_STATUS_PATH, last)
            except OSError as status_exc:
                LOGGER.error(
                    "merge resolver watchdog could not persist its PID cleanup error to %s: %s: %s",
                    MERGE_RESOLVER_STATUS_PATH,
                    type(status_exc).__name__,
                    status_exc,
                )
    return last


def start_merge_resolver_watchdog(args: argparse.Namespace) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if MERGE_RESOLVER_PID_PATH.exists():
        try:
            pid = int(MERGE_RESOLVER_PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = 0
        if _pid_alive(pid):
            return {"status": "already_running", "pid": pid, "status_path": str(MERGE_RESOLVER_STATUS_PATH)}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ACCELERATE_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "merge-watchdog-run",
        "--interval-s",
        str(float(args.interval_s)),
        "--timeout-seconds",
        str(float(args.timeout_seconds)),
    ]
    log_handle = MERGE_RESOLVER_LOG_PATH.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    time.sleep(1.0)
    payload = {
        "status": "started",
        "pid": proc.pid,
        "status_path": str(MERGE_RESOLVER_STATUS_PATH),
        "log_path": str(MERGE_RESOLVER_LOG_PATH),
        "merge_resolver_command": merge_resolver_command(),
    }
    MERGE_RESOLVER_STATUS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def stop_merge_resolver_watchdog() -> dict[str, Any]:
    if not MERGE_RESOLVER_PID_PATH.exists():
        return {"status": "not_running"}
    try:
        pid = int(MERGE_RESOLVER_PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        pid = 0
    if not _pid_alive(pid):
        MERGE_RESOLVER_PID_PATH.unlink(missing_ok=True)
        return {"status": "not_running"}
    signal_scope = "process"
    try:
        process_group = os.getpgid(pid)
        os.killpg(process_group, signal.SIGTERM)
        signal_scope = "process_group"
    except (OSError, ProcessLookupError):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(20):
        if not _pid_alive(pid):
            break
        time.sleep(0.2)
    stopped = not _pid_alive(pid)
    if stopped:
        MERGE_RESOLVER_PID_PATH.unlink(missing_ok=True)
    return {
        "status": "stopped" if stopped else "stopping",
        "pid": pid,
        "signal": "SIGTERM",
        "signal_scope": signal_scope,
    }


def stop_daemon() -> dict[str, Any]:
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = 0
    try:
        managed_pid = int(MANAGED_DAEMON_PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        managed_pid = 0
    supervisor_alive = _pid_alive(pid)
    managed_alive = _pid_alive(managed_pid)
    if not supervisor_alive:
        PID_PATH.unlink(missing_ok=True)
    if not managed_alive:
        MANAGED_DAEMON_PID_PATH.unlink(missing_ok=True)
    if not supervisor_alive and not managed_alive:
        result = {
            "status": "not_running",
            "pid": pid,
            "pid_alive": False,
            "managed_daemon_pid": managed_pid,
            "managed_daemon_pid_alive": False,
            "status_path": str(STATUS_PATH),
        }
        _write_status(result)
        return result

    signal_scope = "none"
    if supervisor_alive:
        try:
            process_group_id = os.getpgid(pid)
            if process_group_id == pid:
                os.killpg(process_group_id, signal.SIGTERM)
                signal_scope = "process_group"
            else:
                os.kill(pid, signal.SIGTERM)
                signal_scope = "process"
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            return {
                "status": "stop_failed",
                "pid": pid,
                "pid_alive": True,
                "status_path": str(STATUS_PATH),
                "error": f"{type(exc).__name__}: {exc}",
            }

    managed_signal_scope = "none"
    if managed_pid and managed_pid != pid and _pid_alive(managed_pid):
        try:
            managed_process_group_id = os.getpgid(managed_pid)
            if managed_process_group_id == managed_pid:
                os.killpg(managed_process_group_id, signal.SIGTERM)
                managed_signal_scope = "process_group"
            else:
                os.kill(managed_pid, signal.SIGTERM)
                managed_signal_scope = "process"
        except ProcessLookupError:
            pass
        except PermissionError:
            managed_signal_scope = "permission_denied"

    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while (_pid_alive(pid) or _pid_alive(managed_pid)) and time.monotonic() < deadline:
        time.sleep(STOP_POLL_SECONDS)
    supervisor_stopped = not _pid_alive(pid)
    managed_stopped = not _pid_alive(managed_pid)
    stopped = supervisor_stopped and managed_stopped
    if stopped:
        PID_PATH.unlink(missing_ok=True)
        MANAGED_DAEMON_PID_PATH.unlink(missing_ok=True)
    result = {
        "status": "stopped" if stopped else "stopping",
        "pid": pid,
        "pid_alive": not supervisor_stopped,
        "signal": "SIGTERM",
        "signal_scope": signal_scope,
        "managed_daemon_pid": managed_pid,
        "managed_daemon_pid_alive": not managed_stopped,
        "managed_daemon_signal_scope": managed_signal_scope,
        "status_path": str(STATUS_PATH),
    }
    counts, count_errors = _collect_counts()
    result["counts"] = counts
    result.update(count_errors)
    if stopped:
        result["stopped_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_status(result)
    return result


def _heartbeat_age_seconds(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return round(max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds()), 3)


def status_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "status": "not_running",
        "pid": 0,
        "updated_at": None,
        "artifacts": _status_artifacts(),
        "last_error": None,
        "pid_alive": False,
        "heartbeat": None,
        "heartbeat_at": None,
        "scan_summary": {},
        "next_tasks": [],
        "counts": {
            "todo": {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0},
            "queue": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
        },
        "objective_path": str(OBJECTIVE_PATH),
        "todo_path": str(TODO_PATH),
        "bundle_dir": str(BUNDLE_DIR),
        "graph_path": str(GRAPH_PATH),
        "queue_path": str(QUEUE_PATH),
        "log_path": str(LOG_PATH),
        "bundle_lane_manifest": str(BUNDLE_LANE_MANIFEST),
        "bundle_coordination_path": str(BUNDLE_COORDINATION_PATH),
        "bundle_scheduler_pid_path": str(BUNDLE_SCHEDULER_PID_PATH),
        "bundle_scheduler_log_path": str(BUNDLE_SCHEDULER_LOG_PATH),
        "merge_resolver_command": merge_resolver_command(),
        "merge_resolver_enabled_for_new_launches": True,
        "status_path": str(STATUS_PATH),
        "upstream_status_path": str(UPSTREAM_SUPERVISOR_STATUS_PATH),
        "managed_daemon_pid_path": str(MANAGED_DAEMON_PID_PATH),
    }
    if STATUS_PATH.exists():
        try:
            payload.update(json.loads(STATUS_PATH.read_text(encoding="utf-8")))
        except Exception as exc:
            payload["status_read_error"] = str(exc)
    has_pid_file = PID_PATH.exists()
    if has_pid_file:
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = 0
        payload["pid"] = pid
        payload["pid_alive"] = _pid_alive(pid)
    else:
        try:
            payload["pid"] = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            payload["pid"] = 0
        payload["pid_alive"] = False

    if UPSTREAM_SUPERVISOR_STATUS_PATH.exists():
        upstream_status = _load_json_object(UPSTREAM_SUPERVISOR_STATUS_PATH)
        payload["upstream_supervisor_status"] = upstream_status
        if payload["pid_alive"]:
            upstream_heartbeat = upstream_status.get("heartbeat_at") or upstream_status.get("updated_at")
            if upstream_heartbeat:
                payload["heartbeat"] = upstream_heartbeat
                payload["heartbeat_at"] = upstream_heartbeat
    managed_pid = 0
    if MANAGED_DAEMON_PID_PATH.exists():
        try:
            managed_pid = int(MANAGED_DAEMON_PID_PATH.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            managed_pid = 0
    payload["managed_daemon_pid"] = managed_pid
    payload["managed_daemon_pid_alive"] = _pid_alive(managed_pid)

    counts, count_errors = _collect_counts()
    payload["counts"] = counts
    payload["todo_counts"] = counts["todo"]
    payload["queue_counts"] = counts["queue"]
    payload.update(count_errors)
    scan_summary = _status_scan_summary(payload)
    if not scan_summary and GOALS_PATH.exists():
        scan_summary = _scan_summary(_load_json_object(GOALS_PATH).get("scan"))
    payload["scan_summary"] = scan_summary

    heartbeat = payload.get("heartbeat_at") or payload.get("heartbeat")
    heartbeat_source = "status" if heartbeat else None
    if payload.get("upstream_supervisor_status") and heartbeat:
        heartbeat_source = "upstream_supervisor"
    if not heartbeat:
        # A checkout may intentionally omit ignored runtime files. The last scan time
        # is still a useful, durable indication of the latest supervisor activity.
        heartbeat = scan_summary.get("scanned_at")
        heartbeat_source = "scan" if heartbeat else None
    payload["heartbeat"] = heartbeat
    payload["heartbeat_at"] = heartbeat
    payload["heartbeat_source"] = heartbeat_source
    payload["heartbeat_age_seconds"] = _heartbeat_age_seconds(heartbeat)
    if payload["status"] in {"running", "starting", "started"} and not payload["pid_alive"]:
        payload["status"] = "stale"

    payload["next_tasks"] = []
    try:
        payload["next_tasks"] = _queued_task_summaries(limit=10)
    except Exception as exc:
        payload["queue_error"] = f"{type(exc).__name__}: {exc}"
    if TODO_PATH.exists():
        parse_markdown_tasks, _task_status_counts = _upstream_task_board_helpers()
        tasks = parse_markdown_tasks(TODO_PATH.read_text(encoding="utf-8", errors="replace"))
        payload["next_todo_tasks"] = [
            {"checkbox_id": task.checkbox_id, "status": task.status, "title": task.title}
            for task in tasks
            if task.status in {"needed", "in-progress"}
        ][:10]
    if BUNDLE_LANE_MANIFEST.exists():
        try:
            artifact_store = _upstream_artifact_store()
            manifest = artifact_store.read_artifact_fields(
                BUNDLE_LANE_MANIFEST,
                (
                    "schema",
                    "scheduler_state",
                    "cycle",
                    "planned_count",
                    "started_count",
                    "running_count",
                    "ready_count",
                    "blocked_count",
                    "completed_count",
                    "started",
                ),
            )
            dynamic = str(manifest.get("schema") or "").endswith("dynamic_bundle_scheduler@1")
            if dynamic:
                lane_rows = artifact_store.query_artifact(
                    BUNDLE_LANE_MANIFEST,
                    table="manifest_lanes",
                    columns=(
                        "bundle_key",
                        "state",
                        "pid",
                        "log_path",
                        "task_ids_json",
                        "conflict_color",
                    ),
                    limit=10,
                )["rows"]
                lane_items = []
                for item in lane_rows:
                    lane = dict(item)
                    lane["task_ids"] = json.loads(str(lane.pop("task_ids_json") or "[]"))
                    lane_items.append(lane)
            else:
                lane_items = manifest.get("started", [])
            payload["parallel_lanes"] = {
                "schema": manifest.get("schema"),
                "scheduler_state": manifest.get("scheduler_state"),
                "cycle": manifest.get("cycle"),
                "planned_count": manifest.get("planned_count", 0),
                "started_count": manifest.get("started_count", 0),
                "running_count": manifest.get("running_count", manifest.get("started_count", 0)),
                "ready_count": manifest.get("ready_count", 0),
                "blocked_count": manifest.get("blocked_count", 0),
                "completed_count": manifest.get("completed_count", 0),
                "lanes": [
                    {
                        "bundle_key": item.get("bundle_key"),
                        "state": item.get("state", "accepted" if item.get("accepted") else None),
                        "pid": item.get("pid"),
                        "log_path": item.get("log_path"),
                        "task_ids": item.get("task_ids", []),
                        "conflict_color": item.get("conflict_color"),
                    }
                    for item in lane_items[:10]
                    if isinstance(item, dict)
                ],
            }
        except Exception as exc:
            payload["parallel_lanes_error"] = str(exc)
    parallel_pid = 0
    if BUNDLE_SCHEDULER_PID_PATH.exists():
        try:
            parallel_pid = int(BUNDLE_SCHEDULER_PID_PATH.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            parallel_pid = 0
    payload["parallel_scheduler"] = {
        **dict(payload.get("parallel_scheduler") or {}),
        "pid": parallel_pid,
        "pid_alive": _pid_alive(parallel_pid),
        "manifest_path": str(BUNDLE_LANE_MANIFEST),
        "manifest_duckdb_path": str(BUNDLE_LANE_MANIFEST.with_suffix(".duckdb")),
        "log_path": str(BUNDLE_SCHEDULER_LOG_PATH),
    }
    if MERGE_RESOLVER_STATUS_PATH.exists():
        try:
            merge_payload = json.loads(MERGE_RESOLVER_STATUS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            merge_payload = {"status_read_error": str(exc)}
        if MERGE_RESOLVER_PID_PATH.exists():
            try:
                merge_pid = int(MERGE_RESOLVER_PID_PATH.read_text(encoding="utf-8").strip())
            except Exception:
                merge_pid = 0
            merge_payload["pid"] = merge_pid
            merge_payload["pid_alive"] = _pid_alive(merge_pid)
        payload["merge_resolver_watchdog"] = merge_payload
    existing_artifacts = payload.get("artifacts")
    payload["artifacts"] = {
        **_status_artifacts(),
        **(dict(existing_artifacts) if isinstance(existing_artifacts, dict) else {}),
    }
    payload["last_error"] = _status_last_error(payload)
    return payload


def add_parallel_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--refill-floor", type=int, default=24)
    parser.add_argument("--max-lanes", type=int, default=4)
    parser.add_argument(
        "--interval-s",
        type=float,
        default=DEFAULT_PARALLEL_RECONCILE_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--daemon-interval-s",
        type=float,
        default=DEFAULT_PARALLEL_DAEMON_INTERVAL_SECONDS,
    )
    parser.add_argument("--implementation-timeout", type=float, default=1800.0)
    parser.add_argument("--max-restarts", type=int, default=3)
    parser.add_argument("--merge-resolver-timeout", type=float, default=900.0)
    parser.add_argument("--merge-reconciliation-max-merges", type=int, default=2)
    parser.add_argument("--generated-dirty-max-paths", type=int, default=200)
    parser.add_argument("--generated-dirty-stale-lock-seconds", type=float, default=300.0)
    parser.add_argument("--lease-ms", type=int, default=300000)
    parser.add_argument("--full-scan", action="store_true", help="Run the expensive upstream objective AST scan before planning lanes.")
    parser.add_argument("--skip-active-bundle", action="store_true", default=True)
    implement_group = parser.add_mutually_exclusive_group()
    implement_group.add_argument("--implement", dest="implement", action="store_true")
    implement_group.add_argument("--no-implement", dest="implement", action="store_false")
    parser.set_defaults(implement=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refactor planning supervisor backed by ipfs_accelerate_py TaskQueue.")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="Scan the repo and seed/refill the taskboard once.")
    seed.add_argument("--refill-floor", type=int, default=20)
    seed.add_argument("--full-scan", action="store_true", help="Also run upstream objective/refill scans now.")
    seed.add_argument("--once", action="store_true", help="Accepted for command symmetry; seed always runs once.")

    run = sub.add_parser("run", help="Run the refill supervisor in the foreground.")
    run.add_argument("--interval-s", type=float, default=300.0)
    run.add_argument("--refill-floor", type=int, default=20)
    run.add_argument("--once", action="store_true")

    start = sub.add_parser("start", help="Start the refill supervisor as a background daemon.")
    start.add_argument("--interval-s", type=float, default=300.0)
    start.add_argument("--daemon-interval-s", type=float, default=300.0)
    start.add_argument("--refill-floor", type=int, default=20)
    start.add_argument("--implementation-timeout", type=float, default=1800.0)
    start.add_argument("--max-restarts", type=int, default=10)
    start.add_argument("--merge-resolver-timeout", type=float, default=900.0)
    start.add_argument("--merge-reconciliation-max-merges", type=int, default=2)
    start.add_argument("--generated-dirty-max-paths", type=int, default=200)
    start.add_argument("--generated-dirty-stale-lock-seconds", type=float, default=300.0)

    plan_parallel = sub.add_parser("plan-parallel", help="Plan goal/subgoal/AST bundle lanes without launching them.")
    add_parallel_args(plan_parallel)

    start_parallel = sub.add_parser("start-parallel", help="Launch upstream leased bundle supervisors for parallel task lanes.")
    add_parallel_args(start_parallel)

    sub.add_parser("stop-parallel", help="Stop the background parallel bundle scheduler and its owned lanes.")

    resolve_merges = sub.add_parser("resolve-merges", help="Run one merge-conflict resolver scan over supervisor event logs.")
    resolve_merges.add_argument("--timeout-seconds", type=float, default=900.0)

    merge_watch = sub.add_parser("start-merge-watchdog", help="Start a background watchdog that resolves failed merge events.")
    merge_watch.add_argument("--interval-s", type=float, default=120.0)
    merge_watch.add_argument("--timeout-seconds", type=float, default=900.0)

    merge_run = sub.add_parser("merge-watchdog-run", help=argparse.SUPPRESS)
    merge_run.add_argument("--interval-s", type=float, default=120.0)
    merge_run.add_argument("--timeout-seconds", type=float, default=900.0)
    merge_run.add_argument("--once", action="store_true")

    sub.add_parser("stop-merge-watchdog", help="Stop the background merge-conflict watchdog.")

    reconcile = sub.add_parser(
        "reconcile-projections",
        help="Synchronize canonical task status into checkboxes, goals, bundle shards, and the query index.",
    )
    reconcile.add_argument("--force", action="store_true", help="Run even while an implementation is active.")

    sub.add_parser("status", help="Show supervisor status.")
    sub.add_parser("stop", help="Stop the background supervisor.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seed":
        payload = seed_taskboard(refill_floor=args.refill_floor, full_scan=args.full_scan)
    elif args.command == "run":
        payload = run_daemon(interval_s=args.interval_s, refill_floor=args.refill_floor, once=args.once)
    elif args.command == "start":
        payload = start_daemon(args)
    elif args.command == "plan-parallel":
        payload = run_parallel_bundle_supervisor(args, start=False)
    elif args.command == "start-parallel":
        payload = run_parallel_bundle_supervisor(args, start=True)
    elif args.command == "stop-parallel":
        payload = stop_parallel_bundle_supervisor()
    elif args.command == "resolve-merges":
        payload = resolve_merge_conflicts_once(timeout_seconds=args.timeout_seconds)
    elif args.command == "start-merge-watchdog":
        payload = start_merge_resolver_watchdog(args)
    elif args.command == "merge-watchdog-run":
        payload = run_merge_resolver_watchdog(
            interval_s=args.interval_s,
            timeout_seconds=args.timeout_seconds,
            once=args.once,
        )
    elif args.command == "stop-merge-watchdog":
        payload = stop_merge_resolver_watchdog()
    elif args.command == "reconcile-projections":
        payload = reconcile_task_projection_artifacts(skip_while_active=not args.force)
    elif args.command == "status":
        payload = status_payload()
    elif args.command == "stop":
        payload = stop_daemon()
    else:
        raise AssertionError(args.command)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
