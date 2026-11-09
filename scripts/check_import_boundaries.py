"""Ratchet direct imports of unpublished owner modules.

A bypass is an import of one of these modules from a file that is not in
that module's owner package:

- mediator.mediator (owner package: mediator)
- applications.complaint_workspace (owner package: applications)
- complaint_phases.denoiser (owner package: complaint_phases)
- document_pipeline (owner file: document_pipeline.py)

docs/architecture/import_boundary_baseline.json records each current bypass
as a file path plus imported module. This checker exits nonzero when a
Python file adds a bypass that the baseline does not list. Imports of a
published package interface are not bypasses. Existing entries stay allowed,
including the large owner modules.

Usage:
  python scripts/check_import_boundaries.py [--root ROOT] [--baseline PATH]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = REPO_ROOT / "docs" / "architecture" / "import_boundary_baseline.json"
SCHEMA = "complaint-generator/import-boundary-baseline@1"
TASK_ID = "CIMP-MOD-12"

# Guarded module -> owner package. None means the owner is the root module file.
GUARDED_MODULES: dict[str, str | None] = {
    "mediator.mediator": "mediator",
    "applications.complaint_workspace": "applications",
    "complaint_phases.denoiser": "complaint_phases",
    "document_pipeline": None,
}
ROOT_MODULE_OWNERS = {
    "document_pipeline": "document_pipeline.py",
}

SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "external",
        "artifacts",
        "output",
        "workspace",
        "data",
        "statefiles",
        ".complaint_workspace",
        "complaint_generator.egg-info",
    }
)


class BoundaryCheckError(Exception):
    """The baseline or a source tree cannot be read."""


def _posix(path: Path) -> str:
    return path.as_posix()


def owner_exempt(relative_path: str, guarded_module: str) -> bool:
    """Return True when relative_path belongs to the guarded module's owner."""
    owner_package = GUARDED_MODULES[guarded_module]
    if owner_package is None:
        return relative_path == ROOT_MODULE_OWNERS[guarded_module]
    prefix = owner_package + "/"
    return relative_path == owner_package or relative_path.startswith(prefix)


def guarded_module_for(module_name: str) -> str | None:
    """Return the guarded module that module_name imports, if any."""
    for guarded in GUARDED_MODULES:
        if module_name == guarded or module_name.startswith(guarded + "."):
            return guarded
    return None


def _package_parts(relative_path: Path) -> tuple[str, ...]:
    parts = relative_path.parts
    if not parts or not parts[-1].endswith(".py"):
        return ()
    return parts[:-1]


def imported_module_names(tree: ast.AST, relative_path: Path) -> list[str]:
    """Return absolute module names referenced by import statements."""
    package = _package_parts(relative_path)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        base = _resolve_import_from(node, package)
        if base:
            names.append(base)
        for alias in node.names:
            if alias.name == "*":
                continue
            names.append(f"{base}.{alias.name}" if base else alias.name)
    return names


def _resolve_import_from(node: ast.ImportFrom, package: tuple[str, ...]) -> str:
    if node.level == 0:
        return node.module or ""
    climb = node.level - 1
    if climb > len(package):
        parent: tuple[str, ...] = ()
    else:
        parent = package[: len(package) - climb]
    if node.module:
        return ".".join((*parent, node.module)) if parent else node.module
    return ".".join(parent)


def bypasses_in_source(source: str, relative_path: str) -> list[str]:
    """Return sorted guarded modules imported by source outside the owner."""
    rel = Path(relative_path)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: set[str] = set()
    for module_name in imported_module_names(tree, rel):
        guarded = guarded_module_for(module_name)
        if guarded is None or owner_exempt(relative_path, guarded):
            continue
        found.add(guarded)
    return sorted(found)


def iter_python_files(root: Path) -> Iterable[Path]:
    """Yield Python files under root, skipping dependency and runtime trees."""
    if not root.is_dir():
        raise BoundaryCheckError(f"root is not a directory: {root}")

    def _on_error(error: OSError) -> None:
        if isinstance(error, PermissionError):
            return
        raise error

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_error, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in SKIP_DIRECTORIES and not (Path(dirpath) / name).is_symlink()
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = Path(dirpath) / filename
            if path.is_symlink():
                continue
            yield path


def scan_bypasses(root: Path) -> list[dict[str, str]]:
    """Return sorted {path, imported_module} bypasses under root."""
    records: list[dict[str, str]] = []
    for path in iter_python_files(root):
        relative = _posix(path.relative_to(root))
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for module in bypasses_in_source(source, relative):
            records.append({"path": relative, "imported_module": module})
    records.sort(key=lambda item: (item["path"], item["imported_module"]))
    return records


def baseline_document(bypasses: Iterable[Mapping[str, str]]) -> dict:
    """Build the versioned baseline document for the given bypass records."""
    rows = [
        {"path": str(item["path"]), "imported_module": str(item["imported_module"])}
        for item in bypasses
    ]
    rows.sort(key=lambda item: (item["path"], item["imported_module"]))
    return {
        "schema": SCHEMA,
        "task_id": TASK_ID,
        "guarded_modules": [
            {
                "module": module,
                "owner_package": owner,
                "owner_path": ROOT_MODULE_OWNERS.get(module),
            }
            for module, owner in GUARDED_MODULES.items()
        ],
        "bypasses": rows,
    }


def load_baseline(path: Path) -> set[tuple[str, str]]:
    """Load allowed (path, imported_module) pairs from a baseline file."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BoundaryCheckError(f"baseline not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BoundaryCheckError(f"baseline is not JSON: {path}") from exc
    if not isinstance(document, dict):
        raise BoundaryCheckError("baseline must be a JSON object")
    if document.get("schema") != SCHEMA:
        raise BoundaryCheckError(f"baseline schema must be {SCHEMA}")
    rows = document.get("bypasses")
    if not isinstance(rows, list):
        raise BoundaryCheckError("baseline bypasses must be a list")
    allowed: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise BoundaryCheckError("each baseline bypass must be an object")
        file_path = row.get("path")
        module = row.get("imported_module")
        if not isinstance(file_path, str) or not file_path:
            raise BoundaryCheckError("each baseline bypass needs a path")
        if not isinstance(module, str) or module not in GUARDED_MODULES:
            raise BoundaryCheckError(
                "each baseline bypass needs a guarded imported_module"
            )
        allowed.add((file_path, module))
    return allowed


def unlisted_bypasses(root: Path, baseline: Path) -> list[dict[str, str]]:
    """Return bypasses present in root and absent from the baseline."""
    allowed = load_baseline(baseline)
    violations: list[dict[str, str]] = []
    for record in scan_bypasses(root):
        key = (record["path"], record["imported_module"])
        if key not in allowed:
            violations.append(record)
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)
    try:
        violations = unlisted_bypasses(args.root.resolve(), args.baseline.resolve())
    except BoundaryCheckError as exc:
        print(f"import boundary check failed: {exc}", file=sys.stderr)
        return 2
    if violations:
        print(
            f"import boundary check failed: {len(violations)} unlisted bypass(es)",
            file=sys.stderr,
        )
        for record in violations:
            print(
                f"unlisted bypass: {record['path']} imports {record['imported_module']}",
                file=sys.stderr,
            )
        return 1
    print("import boundary check ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
