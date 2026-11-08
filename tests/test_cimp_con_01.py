"""CIMP-CON-01: session reports group A leave the repository root."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "archive" / "sessions"

GROUP_A = {
    "AUTONOMOUS_SESSION_REPORT.md": 14822,
    "BATCH_254_258_SESSION_SUMMARY.md": 15081,
    "BATCH_305_306_SESSION_SUMMARY.md": 6799,
    "BATCH_328_API_RETURN_TYPES_SUMMARY.md": 11564,
    "BATCH_329_EXCEPTION_HANDLING_SUMMARY.md": 11919,
    "BENCHMARK_SUITE_SESSION_SUMMARY.md": 10574,
    "ITEM_7_COMPLETION_SUMMARY.md": 9658,
    "P3_INFRASTRUCTURE_COMPLETION_SESSION.md": 6935,
    "P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md": 8334,
}


def test_group_a_session_reports_are_archived_with_recorded_sizes() -> None:
    for name, size in GROUP_A.items():
        assert not (ROOT / name).exists(), name
        destination = ARCHIVE / name
        assert destination.is_file(), name
        assert destination.stat().st_size == size, name


def test_readme_stays_at_repository_root() -> None:
    assert (ROOT / "README.md").is_file()
    assert not (ARCHIVE / "README.md").exists()
