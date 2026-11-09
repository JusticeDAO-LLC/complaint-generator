"""CIMP-CON-02: session reports group B leave the repository root."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "archive" / "sessions"

GROUP_B = {
    "PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md": 10410,
    "PHASE_2_COMPLETION_SUMMARY.md": 5565,
    "QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md": 7895,
    "QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md": 15427,
    "README_OLD.md": 817,
    "README_OLD_BACKUP.md": 16697,
    "README_OLD_FULL.md": 30925,
    "SESSION_3_COMPLETE_SUMMARY.md": 12676,
    "SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md": 8397,
}


def test_group_b_session_reports_are_archived_with_recorded_sizes() -> None:
    for name, size in GROUP_B.items():
        assert not (ROOT / name).exists(), name
        destination = ARCHIVE / name
        assert destination.is_file(), name
        assert destination.stat().st_size == size, name


def test_readme_stays_at_repository_root() -> None:
    assert (ROOT / "README.md").is_file()
    assert not (ARCHIVE / "README.md").exists()
