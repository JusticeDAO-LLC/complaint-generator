"""Inventory checks for the repository module map (CIMP-MOD-01).

The map is a record of the current tree. These tests recompute the same
observations and fail when a recorded package directory is missing, when a
recorded byte size drifts, or when a compatibility directory is not the empty
root shim the map describes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
SCHEMA = "complaint-generator/repository-module-map@1"

WALK_SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "artifacts",
        "complaint_generator.egg-info",
        "data",
        "external",
        "node_modules",
        "output",
        "statefiles",
        "workspace",
    }
)
LARGEST_PYTHON_MODULE_LIMIT = 15
DUPLICATE_CONCERNS = ("cli", "mcp", "deontic_logic", "legal_document")
COMPATIBILITY_DIRECTORIES = ("ipfs_datasets_py", "mike")


def is_session_or_batch_report(name: str) -> bool:
    upper = name.upper()
    if not upper.endswith(".MD"):
        return False
    if "SESSION" in upper:
        return True
    if "BATCH" in upper and any(token in upper for token in ("SUMMARY", "REPORT", "HANDLING", "RETURN")):
        return True
    return False


def report_kind(name: str) -> str:
    upper = name.upper()
    has_session = "SESSION" in upper
    has_batch = "BATCH" in upper
    if has_session and has_batch:
        return "session_and_batch_report"
    if has_session:
        return "session_report"
    return "batch_report"


def discover_packages(root: Path) -> list[dict]:
    packages = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        init = child / "__init__.py"
        try:
            is_package = init.is_file()
        except OSError:
            continue
        if not is_package:
            continue
        packages.append(
            {
                "name": child.name,
                "path": child.name,
                "init_path": f"{child.name}/__init__.py",
                "init_byte_size": init.stat().st_size,
            }
        )
    return packages


def discover_root_files(root: Path, suffix: str) -> list[dict]:
    records = []
    for path in sorted(root.glob(f"*{suffix}")):
        if path.is_file():
            records.append({"path": path.name, "byte_size": path.stat().st_size})
    return records


def discover_root_markdown(root: Path) -> list[dict]:
    records = []
    for item in discover_root_files(root, ".md"):
        records.append(
            {
                "path": item["path"],
                "byte_size": item["byte_size"],
                "session_or_batch_report": is_session_or_batch_report(item["path"]),
            }
        )
    return records


def discover_session_or_batch_reports(markdown: list[dict]) -> list[dict]:
    return [
        {
            "path": item["path"],
            "byte_size": item["byte_size"],
            "kind": report_kind(item["path"]),
        }
        for item in markdown
        if item["session_or_batch_report"]
    ]


def discover_largest_python_modules(root: Path, limit: int = LARGEST_PYTHON_MODULE_LIMIT) -> list[dict]:
    found: list[tuple[int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        relative = Path(dirpath).relative_to(root)
        parts = relative.parts
        if parts and (parts[0] in WALK_SKIP_DIRECTORIES or parts[0].startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = [
            name
            for name in dirnames
            if name not in WALK_SKIP_DIRECTORIES and not name.startswith(".") and name != "__pycache__"
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            file_path = Path(dirpath) / filename
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            found.append((size, file_path.relative_to(root).as_posix()))
    found.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"rank": index, "path": path, "byte_size": size}
        for index, (size, path) in enumerate(found[:limit], start=1)
    ]


def require_package_directories(root: Path, packages: list[dict]) -> None:
    missing = []
    for package in packages:
        path = root / package["path"]
        init = root / package["init_path"]
        if not path.is_dir() or not init.is_file():
            missing.append(package["path"])
    if missing:
        raise AssertionError(f"recorded package directory missing: {missing}")


def require_byte_sizes(root: Path, records: list[dict]) -> None:
    mismatches = []
    for record in records:
        path = root / record["path"]
        if not path.is_file():
            mismatches.append(f"{record['path']} missing")
            continue
        actual = path.stat().st_size
        if actual != record["byte_size"]:
            mismatches.append(f"{record['path']} map={record['byte_size']} tree={actual}")
    if mismatches:
        raise AssertionError("recorded byte sizes do not match the tree: " + "; ".join(mismatches))


def require_empty_compatibility_directories(root: Path, records: list[dict]) -> None:
    if not records:
        raise AssertionError("compatibility directories are required")
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts or "external" in relative.parts:
            raise AssertionError(f"{record['path']} is not a root compatibility directory")
        if record.get("external_submodule"):
            raise AssertionError(f"{record['path']} is an external submodule checkout")
        path = root / relative
        if not path.is_dir():
            raise AssertionError(f"compatibility directory missing: {record['path']}")
        if record.get("empty") and any(path.iterdir()):
            raise AssertionError(f"compatibility directory is not empty: {record['path']}")


def require_duplicate_owners(root: Path, groups: list[dict]) -> None:
    concerns = [group["concern"] for group in groups]
    if concerns != list(DUPLICATE_CONCERNS):
        raise AssertionError(f"duplicate owner concerns must be {DUPLICATE_CONCERNS}, got {concerns}")
    for group in groups:
        modules = group["modules"]
        if len(modules) < 2:
            raise AssertionError(f"{group['concern']} needs at least two owner modules")
        paths = [module["path"] for module in modules]
        if len(paths) != len(set(paths)):
            raise AssertionError(f"{group['concern']} repeats an owner path")
        require_byte_sizes(root, modules)


def require_inventory_flags(document: dict) -> None:
    if document.get("source_files_moved") is not False:
        raise AssertionError("source files must stay in place")
    if document.get("source_files_rewritten") is not False:
        raise AssertionError("source files must not be rewritten")
    if document.get("schema") != SCHEMA:
        raise AssertionError(f"schema must be {SCHEMA}")


def load_map() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def module_map() -> dict:
    return load_map()


def test_map_schema_and_inventory_flags(module_map: dict) -> None:
    require_inventory_flags(module_map)
    policy = module_map["inventory_policy"]
    assert policy["largest_python_module_limit"] == LARGEST_PYTHON_MODULE_LIMIT
    assert policy["walk_skip_directories"] == sorted(WALK_SKIP_DIRECTORIES)
    assert module_map["task_id"] == "CIMP-MOD-01"


def test_recorded_packages_match_top_level_tree(module_map: dict) -> None:
    discovered = discover_packages(REPO_ROOT)
    assert module_map["packages"] == discovered
    require_package_directories(REPO_ROOT, module_map["packages"])
    names = [package["name"] for package in module_map["packages"]]
    assert "complaint_generator" in names
    assert "applications" in names
    assert "external" not in names


def test_missing_recorded_package_directory_fails(tmp_path: Path) -> None:
    present = tmp_path / "present_pkg"
    present.mkdir()
    (present / "__init__.py").write_text("", encoding="utf-8")
    packages = [
        {"name": "present_pkg", "path": "present_pkg", "init_path": "present_pkg/__init__.py"},
        {"name": "missing_pkg", "path": "missing_pkg", "init_path": "missing_pkg/__init__.py"},
    ]
    with pytest.raises(AssertionError, match="recorded package directory missing"):
        require_package_directories(tmp_path, packages)


def test_package_path_that_is_a_file_fails(tmp_path: Path) -> None:
    (tmp_path / "not_a_package").write_text("x", encoding="utf-8")
    packages = [
        {
            "name": "not_a_package",
            "path": "not_a_package",
            "init_path": "not_a_package/__init__.py",
        }
    ]
    with pytest.raises(AssertionError, match="recorded package directory missing"):
        require_package_directories(tmp_path, packages)


def test_root_scripts_and_markdown_match_tree(module_map: dict) -> None:
    scripts = discover_root_files(REPO_ROOT, ".py")
    markdown = discover_root_markdown(REPO_ROOT)
    assert module_map["root_scripts"] == scripts
    assert module_map["root_markdown"] == markdown
    require_byte_sizes(REPO_ROOT, module_map["root_scripts"])
    require_byte_sizes(REPO_ROOT, module_map["root_markdown"])
    assert any(item["path"] == "document_pipeline.py" for item in scripts)
    assert any(item["path"] == "README.md" for item in markdown)


def test_session_and_batch_reports_are_the_classified_root_markdown(module_map: dict) -> None:
    reports = discover_session_or_batch_reports(module_map["root_markdown"])
    assert module_map["session_or_batch_reports"] == reports
    assert reports
    assert all(is_session_or_batch_report(item["path"]) for item in reports)
    recorded_paths = {item["path"] for item in reports}
    assert "README.md" not in recorded_paths
    assert "BATCH_202_PLAN.md" not in recorded_paths
    assert "AUTONOMOUS_SESSION_REPORT.md" in recorded_paths
    assert "BATCH_328_API_RETURN_TYPES_SUMMARY.md" in recorded_paths
    kinds = {item["kind"] for item in reports}
    assert "session_report" in kinds
    assert "batch_report" in kinds
    assert "session_and_batch_report" in kinds


def test_non_report_markdown_is_not_classified_as_session_or_batch() -> None:
    assert is_session_or_batch_report("README.md") is False
    assert is_session_or_batch_report("CONTRIBUTING.md") is False
    assert is_session_or_batch_report("BATCH_202_PLAN.md") is False
    assert is_session_or_batch_report("AUDIT_DICT_RETURNS_REPORT.md") is False
    assert is_session_or_batch_report("SESSION_84_PROGRESS.md") is True
    assert is_session_or_batch_report("BATCH_329_EXCEPTION_HANDLING_SUMMARY.md") is True


def test_compatibility_directories_are_empty_root_shims(module_map: dict) -> None:
    records = module_map["compatibility_directories"]
    assert [record["path"] for record in records] == list(COMPATIBILITY_DIRECTORIES)
    require_empty_compatibility_directories(REPO_ROOT, records)
    for record in records:
        assert record["empty"] is True
        assert record["external_submodule"] is False
        assert (REPO_ROOT / record["path"]).is_dir()
        assert list((REPO_ROOT / record["path"]).iterdir()) == []
    assert not any(record["path"].startswith("external/") for record in records)
    assert (REPO_ROOT / "integrations" / "ipfs_datasets").is_dir()
    assert (REPO_ROOT / "integrations" / "mike").is_dir()


def test_non_empty_or_external_compatibility_directory_fails(tmp_path: Path) -> None:
    shim = tmp_path / "ipfs_datasets_py"
    shim.mkdir()
    (shim / "marker.txt").write_text("occupied", encoding="utf-8")
    with pytest.raises(AssertionError, match="not empty"):
        require_empty_compatibility_directories(
            tmp_path,
            [{"path": "ipfs_datasets_py", "empty": True, "external_submodule": False}],
        )
    with pytest.raises(AssertionError, match="external submodule"):
        require_empty_compatibility_directories(
            tmp_path,
            [{"path": "mike", "empty": True, "external_submodule": True}],
        )
    with pytest.raises(AssertionError, match="not a root compatibility directory"):
        require_empty_compatibility_directories(
            tmp_path,
            [{"path": "external/ipfs_datasets_py", "empty": True, "external_submodule": False}],
        )


def test_duplicate_owners_name_paths_and_byte_sizes(module_map: dict) -> None:
    require_duplicate_owners(REPO_ROOT, module_map["duplicate_owners"])
    by_concern = {group["concern"]: group for group in module_map["duplicate_owners"]}
    cli_paths = {module["path"] for module in by_concern["cli"]["modules"]}
    assert cli_paths == {
        "applications/cli.py",
        "applications/complaint_cli.py",
        "complaint_generator/cli.py",
    }
    mcp_paths = {module["path"] for module in by_concern["mcp"]["modules"]}
    assert "applications/complaint_mcp_protocol.py" in mcp_paths
    assert "complaint_generator/mcp.py" in mcp_paths
    assert "complaint_generator/mcp_server.py" in mcp_paths
    deontic_paths = {module["path"] for module in by_concern["deontic_logic"]["modules"]}
    assert deontic_paths == {
        "lib/deontic_logic.py",
        "complaint_phases/deontic_logic.py",
    }
    legal_paths = {module["path"] for module in by_concern["legal_document"]["modules"]}
    assert "lib/legal_document.py" in legal_paths
    assert "complaint_phases/legal_document.py" in legal_paths
    assert "mediator/formal_document.py" in legal_paths
    for group in module_map["duplicate_owners"]:
        for module in group["modules"]:
            assert module["byte_size"] > 0
            assert (REPO_ROOT / module["path"]).is_file()


def test_single_owner_is_not_a_duplicate(tmp_path: Path) -> None:
    owner = tmp_path / "only.py"
    owner.write_text("x", encoding="utf-8")
    groups = [
        {
            "concern": concern,
            "modules": [
                {"path": "only.py", "byte_size": 1, "role": "only"},
                {"path": "only.py", "byte_size": 1, "role": "repeat"},
            ]
            if concern == "cli"
            else [
                {"path": "only.py", "byte_size": 1, "role": "a"},
                {"path": "missing.py", "byte_size": 1, "role": "b"},
            ],
        }
        for concern in DUPLICATE_CONCERNS
    ]
    with pytest.raises(AssertionError, match="repeats an owner path"):
        require_duplicate_owners(tmp_path, groups)


def test_byte_size_mismatch_fails(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("abcd", encoding="utf-8")
    with pytest.raises(AssertionError, match="byte sizes"):
        require_byte_sizes(tmp_path, [{"path": "module.py", "byte_size": 1}])
    with pytest.raises(AssertionError, match="missing"):
        require_byte_sizes(tmp_path, [{"path": "gone.py", "byte_size": 1}])


def test_largest_python_modules_match_the_tree(module_map: dict) -> None:
    largest = discover_largest_python_modules(REPO_ROOT)
    assert module_map["largest_python_modules"] == largest
    assert len(largest) == LARGEST_PYTHON_MODULE_LIMIT
    assert largest[0]["path"] == "applications/complaint_workspace.py"
    recorded_paths = [item["path"] for item in largest]
    assert recorded_paths == sorted(recorded_paths, key=lambda path: (-next(item["byte_size"] for item in largest if item["path"] == path), path))
    require_byte_sizes(REPO_ROOT, largest)
    sizes = [item["byte_size"] for item in largest]
    assert sizes == sorted(sizes, reverse=True)


def test_rewritten_or_moved_inventory_flags_fail() -> None:
    with pytest.raises(AssertionError, match="stay in place"):
        require_inventory_flags({"schema": SCHEMA, "source_files_moved": True, "source_files_rewritten": False})
    with pytest.raises(AssertionError, match="not be rewritten"):
        require_inventory_flags({"schema": SCHEMA, "source_files_moved": False, "source_files_rewritten": True})
    with pytest.raises(AssertionError, match="schema"):
        require_inventory_flags({"schema": "other", "source_files_moved": False, "source_files_rewritten": False})
