"""CIMP-CON-03: session reports group C leave the repository root."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "archive" / "sessions"

GROUP_C = {
    "SESSION_84_FINAL_SUMMARY.md": 7741,
    "SESSION_84_PHASE4_EXTENDED_SUMMARY.md": 17752,
    "SESSION_84_PHASE4_SUMMARY.md": 13483,
    "SESSION_84_PROGRESS.md": 13783,
    "SESSION_SUMMARY_2024_02_24.md": 10746,
    "SESSION_SUMMARY_2026_02_23.md": 8389,
    "SESSION_SUMMARY_2026_02_24_COMPLETE.md": 13118,
    "SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md": 5478,
    "SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md": 8261,
}


def test_group_c_session_reports_are_archived_with_recorded_sizes() -> None:
    for name, size in GROUP_C.items():
        assert not (ROOT / name).exists(), name
        destination = ARCHIVE / name
        assert destination.is_file(), name
        assert destination.stat().st_size == size, name


def test_readme_stays_at_repository_root() -> None:
    assert (ROOT / "README.md").is_file()
    assert not (ARCHIVE / "README.md").exists()
