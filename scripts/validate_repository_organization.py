#!/usr/bin/env python3
"""Read-only acceptance command for repository organization.

Checks every published interface version, the import-boundary baseline, the
documentation index links, and the archive index. Exits 0 when every check
passes and nonzero when any check fails. This command does not edit files,
start a supervisor, or write campaign state.

Usage:
  python scripts/validate_repository_organization.py [--root ROOT]
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
BASELINE_SCHEMA = "complaint-generator/import-boundary-baseline@1"
CONTRACT_SCHEMA = "complaint-generator/repository-reorganization-completion@1"

PUBLISHED_INTERFACES = (
    "applications.interface",
    "mediator.interface",
    "complaint_phases.interface",
    "complaint_generator.interface",
    "lib.interface",
    "integrations.ipfs_accelerate.interface",
    "integrations.ipfs_datasets.interface",
    "integrations.mike.interface",
)

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

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
AUTOLINK_RE = re.compile(r"<([^>\s]+\.md)>", re.IGNORECASE)

def _load_boundary_checker():
    path = REPO_ROOT / "scripts" / "check_import_boundaries.py"
    spec = importlib.util.spec_from_file_location("check_import_boundaries", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _string_constant(path: Path, name: str) -> str | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    return None


def interface_source(module_name: str, root: Path, overlay: Path | None) -> Path:
    relative = Path(*module_name.split(".")).with_suffix(".py")
    if overlay is not None:
        candidate = overlay / relative
        if candidate.is_file():
            return candidate
    return root / relative


def check_published_interfaces(root: Path, overlay: Path | None = None) -> list[str]:
    """Return failures for published interface schema and version 1.0.0.

    Versions are read from the interface source. The parent package is not
    imported, so this check does not start a server or read campaign state.
    """
    failures: list[str] = []
    for module_name in PUBLISHED_INTERFACES:
        path = interface_source(module_name, root, overlay)
        if not path.is_file():
            failures.append(f"{module_name}: published interface file is missing")
            continue
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            failures.append(f"{module_name}: interface source cannot be parsed: {exc}")
            continue
        schema = _string_constant(path, "INTERFACE_SCHEMA")
        version = _string_constant(path, "INTERFACE_VERSION")
        if schema != INTERFACE_SCHEMA:
            failures.append(
                f"{module_name}: INTERFACE_SCHEMA must be {INTERFACE_SCHEMA}"
            )
        if version != INTERFACE_VERSION:
            failures.append(
                f"{module_name}: published interface version must be {INTERFACE_VERSION} "
                f"(found {version!r})"
            )
    return failures


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


def check_documentation_index(index_path: Path, root: Path) -> list[str]:
    """Return documentation-index links that are not files under root."""
    if not index_path.is_file():
        return [f"documentation index is missing: {index_path}"]
    try:
        text = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"documentation index cannot be read: {exc}"]
    targets = relative_link_targets(text)
    if not targets:
        return ["documentation index has no relative links"]
    failures: list[str] = []
    base = root.resolve()
    for target in targets:
        candidate = (root / target).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            failures.append(f"documentation index link escapes the repository: {target}")
            continue
        if not candidate.is_file():
            failures.append(f"documentation index link does not resolve: {target}")
    return failures


def check_archive_index(index_path: Path, archive_dir: Path) -> list[str]:
    """Return archive-index failures. Each moved file is listed once and exists."""
    if not index_path.is_file():
        return [f"archive index is missing: {index_path}"]
    if not archive_dir.is_dir():
        return [f"archive directory is missing: {archive_dir}"]
    try:
        text = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"archive index cannot be read: {exc}"]
    targets = relative_link_targets(text)
    failures: list[str] = []
    if len(targets) != len(set(targets)):
        failures.append("archive index lists a moved file more than once")
    expected = list(ARCHIVED_ROOT_MARKDOWN)
    if targets != expected:
        failures.append("archive index does not list every moved file once, in order")
    for target in targets:
        normalized = target.replace("\\", "/")
        if "/" in normalized or normalized.startswith("."):
            failures.append(f"archive index link is not a file in the archive directory: {target}")
    present = {
        path.name
        for path in archive_dir.glob("*.md")
        if path.name != "INDEX.md" and path.is_file()
    }
    extra = sorted(present - set(expected))
    if extra:
        failures.append("archive directory contains markdown that the index does not list: " + ", ".join(extra))
    return failures


def check_import_baseline(root: Path, baseline: Path) -> list[str]:
    """Return unlisted import-boundary bypasses. Read-only."""
    checker = _load_boundary_checker()
    try:
        violations = checker.unlisted_bypasses(root.resolve(), baseline.resolve())
    except checker.BoundaryCheckError as exc:
        return [f"import baseline check failed: {exc}"]
    return [
        f"unlisted bypass: {record['path']} imports {record['imported_module']}"
        for record in violations
    ]


def collect_failures(
    root: Path,
    *,
    baseline: Path,
    documentation_index: Path,
    archive_index: Path,
    archive_dir: Path,
    overlay: Path | None = None,
) -> list[str]:
    failures: list[str] = []
    failures.extend(check_published_interfaces(root, overlay))
    failures.extend(check_documentation_index(documentation_index, root))
    failures.extend(check_archive_index(archive_index, archive_dir))
    failures.extend(check_import_baseline(root, baseline))
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Import-boundary baseline JSON. Defaults to docs/architecture/import_boundary_baseline.json under --root.",
    )
    parser.add_argument(
        "--documentation-index",
        type=Path,
        default=None,
        help="Documentation index markdown. Defaults to DOCUMENTATION_INDEX.md under --root.",
    )
    parser.add_argument(
        "--archive-index",
        type=Path,
        default=None,
        help="Archive index markdown. Defaults to docs/archive/sessions/INDEX.md under --root.",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help="Archive directory. Defaults to docs/archive/sessions under --root.",
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        default=None,
        help="Optional directory whose interface sources replace published interface files for this run.",
    )
    args = parser.parse_args(argv)
    root = args.root
    baseline = args.baseline or (root / "docs" / "architecture" / "import_boundary_baseline.json")
    documentation_index = args.documentation_index or (root / "DOCUMENTATION_INDEX.md")
    archive_index = args.archive_index or (root / "docs" / "archive" / "sessions" / "INDEX.md")
    archive_dir = args.archive_dir or (root / "docs" / "archive" / "sessions")
    try:
        failures = collect_failures(
            root,
            baseline=baseline,
            documentation_index=documentation_index,
            archive_index=archive_index,
            archive_dir=archive_dir,
            overlay=args.overlay,
        )
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"repository organization check failed: {exc}", file=sys.stderr)
        return 2
    if failures:
        print(
            f"repository organization check failed: {len(failures)} problem(s)",
            file=sys.stderr,
        )
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"published interface versions ok: {len(PUBLISHED_INTERFACES)} at {INTERFACE_VERSION}")
    print("import baseline ok")
    print("documentation index links ok")
    print("archive index ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
