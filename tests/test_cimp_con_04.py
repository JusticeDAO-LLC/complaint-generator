"""CIMP-CON-04: stale plans and profile reports leave the repository root."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "archive" / "reports"

REPORTS = {
    "AUDIT_DICT_RETURNS_REPORT.md": 3979,
    "BATCH_202_PLAN.md": 4452,
    "EXTRACTION_PIPELINE_PROFILE_FINAL.md": 10708,
    "PARALLEL_VALIDATION_FIX_REPORT.md": 4095,
    "UNIFIED_PERFORMANCE_ANALYSIS.md": 12002,
    "plan-mcpPlusPlusIntegration.prompt.md": 6459,
}

KEEP_AT_ROOT = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)


def test_stale_plans_and_profile_reports_are_archived_with_recorded_sizes() -> None:
    for name, size in REPORTS.items():
        assert not (ROOT / name).exists(), name
        destination = ARCHIVE / name
        assert destination.is_file(), name
        assert destination.stat().st_size == size, name


def test_current_root_docs_stay_at_repository_root() -> None:
    for name in KEEP_AT_ROOT:
        assert (ROOT / name).is_file(), name
        assert not (ARCHIVE / name).exists(), name
