"""CIMP-CON-05: archive indexes resolve and the module map records the moves."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "docs" / "archive" / "sessions"
REPORTS = ROOT / "docs" / "archive" / "reports"
MAP_PATH = ROOT / "docs" / "architecture" / "repository_module_map.json"

SESSION_NAMES = (
    "AUTONOMOUS_SESSION_REPORT.md",
    "BATCH_254_258_SESSION_SUMMARY.md",
    "BATCH_305_306_SESSION_SUMMARY.md",
    "BATCH_328_API_RETURN_TYPES_SUMMARY.md",
    "BATCH_329_EXCEPTION_HANDLING_SUMMARY.md",
    "BENCHMARK_SUITE_SESSION_SUMMARY.md",
    "ITEM_7_COMPLETION_SUMMARY.md",
    "P3_INFRASTRUCTURE_COMPLETION_SESSION.md",
    "P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md",
    "PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md",
    "PHASE_2_COMPLETION_SUMMARY.md",
    "QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md",
    "QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md",
    "README_OLD.md",
    "README_OLD_BACKUP.md",
    "README_OLD_FULL.md",
    "SESSION_3_COMPLETE_SUMMARY.md",
    "SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md",
    "SESSION_84_FINAL_SUMMARY.md",
    "SESSION_84_PHASE4_EXTENDED_SUMMARY.md",
    "SESSION_84_PHASE4_SUMMARY.md",
    "SESSION_84_PROGRESS.md",
    "SESSION_SUMMARY_2024_02_24.md",
    "SESSION_SUMMARY_2026_02_23.md",
    "SESSION_SUMMARY_2026_02_24_COMPLETE.md",
    "SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md",
    "SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md",
)

REPORT_NAMES = (
    "AUDIT_DICT_RETURNS_REPORT.md",
    "BATCH_202_PLAN.md",
    "EXTRACTION_PIPELINE_PROFILE_FINAL.md",
    "PARALLEL_VALIDATION_FIX_REPORT.md",
    "UNIFIED_PERFORMANCE_ANALYSIS.md",
    "plan-mcpPlusPlusIntegration.prompt.md",
)

KEEP_AT_ROOT = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)")


def _links(text: str) -> list[str]:
    found: list[str] = []
    for match in LINK_RE.finditer(text):
        target = match.group(1).split("#", 1)[0].split("?", 1)[0].strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        if target and "://" not in target and not target.lower().startswith("mailto:"):
            found.append(target)
    return found


def test_session_and_report_indexes_resolve_every_moved_file() -> None:
    session_index = (SESSIONS / "INDEX.md").read_text(encoding="utf-8")
    report_index = (REPORTS / "INDEX.md").read_text(encoding="utf-8")
    session_links = _links(session_index)
    report_links = _links(report_index)
    assert session_links == list(SESSION_NAMES)
    assert report_links == list(REPORT_NAMES)
    assert len(session_links) == len(set(session_links))
    assert len(report_links) == len(set(report_links))
    for name in SESSION_NAMES:
        assert not (ROOT / name).exists(), name
        destination = (SESSIONS / name).resolve()
        assert destination.is_file(), name
        assert SESSIONS.resolve() in destination.parents
    for name in REPORT_NAMES:
        assert not (ROOT / name).exists(), name
        destination = (REPORTS / name).resolve()
        assert destination.is_file(), name
        assert REPORTS.resolve() in destination.parents
    for directory, links in ((SESSIONS, session_links), (REPORTS, report_links)):
        for link in links:
            destination = (directory / link).resolve()
            assert destination.is_file(), link
            assert directory.resolve() in destination.parents
    for name in KEEP_AT_ROOT:
        assert (ROOT / name).is_file(), name


def test_module_map_records_archive_paths() -> None:
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assert document["source_files_moved"] is True
    assert document["source_files_rewritten"] is False
    recorded = {item["path"] for item in document["root_markdown"]}
    for name in SESSION_NAMES:
        assert name not in recorded
        assert f"docs/archive/sessions/{name}" in recorded
        assert (ROOT / "docs" / "archive" / "sessions" / name).is_file()
    for name in REPORT_NAMES:
        assert name not in recorded
        assert f"docs/archive/reports/{name}" in recorded
        assert (ROOT / "docs" / "archive" / "reports" / name).is_file()
    for name in KEEP_AT_ROOT:
        assert name in recorded
