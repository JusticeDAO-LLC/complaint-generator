"""Archive checks for historical root markdown (CIMP-MOD-19).

The repository module map lists root session, batch, old-README, and
completion-summary markdown. docs/archive/sessions/INDEX.md links each of
those files once, relative to the archive directory. README.md,
DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md stay at
the repository root. README.md and DOCUMENTATION_INDEX.md do not link the
archived names as root files. Plan files and architecture records stay out
of the session archive.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
ARCHIVE_DIR = REPO_ROOT / "docs" / "archive" / "sessions"
INDEX_PATH = ARCHIVE_DIR / "INDEX.md"
README_PATH = REPO_ROOT / "README.md"
DOCUMENTATION_INDEX_PATH = REPO_ROOT / "DOCUMENTATION_INDEX.md"

KEEP_AT_ROOT = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
AUTOLINK_RE = re.compile(r"<([^>\s]+\.md)>", re.IGNORECASE)


def load_module_map() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def is_session_or_batch_report(name: str) -> bool:
    upper = name.upper()
    if not upper.endswith(".MD"):
        return False
    if "SESSION" in upper:
        return True
    if "BATCH" in upper and any(token in upper for token in ("SUMMARY", "REPORT", "HANDLING", "RETURN")):
        return True
    return False


def is_old_readme(name: str) -> bool:
    return name.upper().startswith("README_OLD") and name.upper().endswith(".MD")


def is_completion_summary(name: str) -> bool:
    upper = name.upper()
    if not upper.endswith(".MD"):
        return False
    if "COMPLETION_SUMMARY" in upper or upper.endswith("_COMPLETION.MD"):
        return True
    return False


def is_historical_root_markdown(name: str) -> bool:
    if name in KEEP_AT_ROOT:
        return False
    return is_session_or_batch_report(name) or is_old_readme(name) or is_completion_summary(name)


# Names the repository module map recorded as root session, batch, old-README,
# or completion-summary markdown before they moved out of the repository root.
ARCHIVED_ROOT_MARKDOWN = (
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


def archived_names() -> list[str]:
    return list(ARCHIVED_ROOT_MARKDOWN)


def relative_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in LINK_RE.finditer(text):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1].strip()
        lowered = raw.lower()
        if lowered.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = raw.split("#", 1)[0].split("?", 1)[0]
        if path:
            targets.append(path)
    for match in AUTOLINK_RE.finditer(text):
        targets.append(match.group(1).strip())
    return targets


def root_links_to_archived(text: str, archived: set[str]) -> list[str]:
    """Markdown links whose target is an archived file at the repository root."""
    found: list[str] = []
    for target in relative_link_targets(text):
        normalized = target.replace("\\", "/")
        if normalized.startswith(("/", "./")):
            normalized = normalized[1:] if normalized.startswith("/") else normalized
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if "/" in normalized:
            continue
        name = Path(normalized).name
        if name in archived:
            found.append(target)
    return found


def unresolved_index_links(index_text: str, archive_dir: Path) -> list[str]:
    missing: list[str] = []
    for target in relative_link_targets(index_text):
        candidate = (archive_dir / target).resolve()
        try:
            candidate.relative_to(archive_dir.resolve())
        except ValueError:
            missing.append(target)
            continue
        if not candidate.is_file():
            missing.append(target)
    return missing


def test_keep_list_stays_at_repository_root() -> None:
    for name in KEEP_AT_ROOT:
        assert (REPO_ROOT / name).is_file(), name
        assert not (ARCHIVE_DIR / name).exists(), name


def historical_names_from_module_map(module_map: dict) -> list[str]:
    names = [
        Path(item["path"]).name
        for item in module_map["root_markdown"]
        if is_historical_root_markdown(Path(item["path"]).name)
    ]
    return names


def test_module_map_historical_markdown_is_archived() -> None:
    archived = archived_names()
    module_map = load_module_map()
    recorded = {item["path"] for item in module_map["root_markdown"]}
    assert module_map["source_files_moved"] is True
    assert module_map["source_files_rewritten"] is False
    assert archived
    for name in archived:
        assert is_historical_root_markdown(name) is True
        assert name not in recorded
        assert f"docs/archive/sessions/{name}" in recorded
        assert not (REPO_ROOT / name).exists(), name
        assert (ARCHIVE_DIR / name).is_file(), name
    for item in module_map["session_or_batch_reports"]:
        name = Path(item["path"]).name
        assert is_historical_root_markdown(name) is True
        assert name in archived
        assert item["path"] == f"docs/archive/sessions/{name}"
        assert not (REPO_ROOT / name).exists(), name
    for name in KEEP_AT_ROOT:
        assert name in recorded
        assert is_historical_root_markdown(name) is False
        assert (REPO_ROOT / name).is_file(), name
        assert not (ARCHIVE_DIR / name).exists(), name


def test_archive_index_lists_each_moved_file_once() -> None:
    archived = archived_names()
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    targets = relative_link_targets(index_text)
    assert targets == list(archived)
    assert len(targets) == len(set(targets))
    assert all("/" not in target and not target.startswith(".") for target in targets)
    present = {
        path.name
        for path in ARCHIVE_DIR.glob("*.md")
        if path.name != "INDEX.md" and path.is_file()
    }
    assert present <= set(archived)
    assert all((ARCHIVE_DIR / name).is_file() for name in archived)
    assert unresolved_index_links(index_text, ARCHIVE_DIR) == []
    assert unresolved_index_links("[index](INDEX.md)\n", ARCHIVE_DIR) == []


def test_readme_and_documentation_index_do_not_link_moved_root_files() -> None:
    archived = set(archived_names())
    readme_hits = root_links_to_archived(README_PATH.read_text(encoding="utf-8"), archived)
    index_hits = root_links_to_archived(DOCUMENTATION_INDEX_PATH.read_text(encoding="utf-8"), archived)
    assert readme_hits == []
    assert index_hits == []


def test_plan_and_architecture_records_stay_out_of_the_session_archive() -> None:
    reports = (
        "BATCH_202_PLAN.md",
        "AUDIT_DICT_RETURNS_REPORT.md",
        "plan-mcpPlusPlusIntegration.prompt.md",
    )
    stayed = (
        "docs/task_boards/complaint_repository_reorganization_task_board.md",
        "docs/architecture/repository_module_map.json",
    )
    for name in reports:
        assert not (REPO_ROOT / name).exists(), name
        assert (REPO_ROOT / "docs" / "archive" / "reports" / name).is_file(), name
        assert not (ARCHIVE_DIR / name).exists(), name
    for relative in stayed:
        assert (REPO_ROOT / relative).is_file(), relative
        assert not (ARCHIVE_DIR / Path(relative).name).exists()
    assert not (ARCHIVE_DIR / "repository_module_map.json").exists()
    assert not (ARCHIVE_DIR / "complaint_repository_reorganization_task_board.md").exists()


def test_negative_keep_and_plan_names_are_not_historical() -> None:
    for name in KEEP_AT_ROOT:
        assert is_historical_root_markdown(name) is False
    assert is_historical_root_markdown("BATCH_202_PLAN.md") is False
    assert is_historical_root_markdown("AUDIT_DICT_RETURNS_REPORT.md") is False
    assert is_historical_root_markdown("UNIFIED_PERFORMANCE_ANALYSIS.md") is False
    assert is_historical_root_markdown("EXTRACTION_PIPELINE_PROFILE_FINAL.md") is False


def test_negative_historical_names_are_selected() -> None:
    assert is_historical_root_markdown("SESSION_84_PROGRESS.md") is True
    assert is_historical_root_markdown("BATCH_329_EXCEPTION_HANDLING_SUMMARY.md") is True
    assert is_historical_root_markdown("README_OLD_FULL.md") is True
    assert is_historical_root_markdown("ITEM_7_COMPLETION_SUMMARY.md") is True
    assert is_historical_root_markdown("QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md") is True
    assert is_historical_root_markdown("PHASE_2_COMPLETION_SUMMARY.md") is True


def test_negative_root_link_to_archived_file_is_detected() -> None:
    archived = {"SESSION_84_PROGRESS.md", "README_OLD.md"}
    sample = "\n".join(
        [
            "See [session](SESSION_84_PROGRESS.md) and [old](./README_OLD.md).",
            "Keep [archive](docs/archive/sessions/SESSION_84_PROGRESS.md).",
            "Keep [plan](docs/task_boards/complaint_repository_reorganization_task_board.md).",
            "Autolink <BATCH_328_API_RETURN_TYPES_SUMMARY.md> is a root link.",
        ]
    )
    assert root_links_to_archived(sample, archived) == [
        "SESSION_84_PROGRESS.md",
        "./README_OLD.md",
    ]
    assert root_links_to_archived(sample, {"BATCH_328_API_RETURN_TYPES_SUMMARY.md"}) == [
        "BATCH_328_API_RETURN_TYPES_SUMMARY.md",
    ]


def test_negative_unresolved_and_extra_index_links_are_detected() -> None:
    archived = archived_names()
    text = INDEX_PATH.read_text(encoding="utf-8")
    broken = text.replace("(SESSION_84_PROGRESS.md)", "(MISSING_SESSION.md)", 1)
    assert "MISSING_SESSION.md" in unresolved_index_links(broken, ARCHIVE_DIR)
    targets = relative_link_targets(text)
    assert targets != archived + ["BATCH_202_PLAN.md"]
    assert "BATCH_202_PLAN.md" not in targets


def test_positive_archive_link_is_not_a_root_link() -> None:
    archived = {"SESSION_84_PROGRESS.md"}
    sample = "See [archive](docs/archive/sessions/SESSION_84_PROGRESS.md)."
    assert root_links_to_archived(sample, archived) == []
    assert relative_link_targets(sample) == ["docs/archive/sessions/SESSION_84_PROGRESS.md"]
