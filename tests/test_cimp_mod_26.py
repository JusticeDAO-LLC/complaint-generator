"""Repository-organization acceptance command (CIMP-MOD-26).

The validator checks published interface versions, the import baseline, the
documentation index links, and the archive index. It exits nonzero when any
check fails. The completion contract has no completion authority and does
not mark any CIMP-MOD task complete.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate_repository_organization.py"
CONTRACT = REPO_ROOT / "docs" / "task_boards" / "complaint_repository_reorganization_completion_contract.json"
CONTRACT_SCHEMA = "complaint-generator/repository-reorganization-completion@1"
INTERFACE_VERSION = "1.0.0"
CIMP_MOD_IDS = tuple(f"CIMP-MOD-{index:02d}" for index in range(1, 27))


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_repository_organization", VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_validator(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _walk_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_objects(child)


def test_current_tree_acceptance_exits_zero() -> None:
    result = _run_validator(["--root", str(REPO_ROOT)])
    assert result.returncode == 0, result.stderr
    assert f"published interface versions ok: 8 at {INTERFACE_VERSION}" in result.stdout
    assert "import baseline ok" in result.stdout
    assert "documentation index links ok" in result.stdout
    assert "archive index ok" in result.stdout
    assert "repository organization check failed" not in result.stderr


def test_temporary_broken_interface_version_exits_nonzero(tmp_path: Path) -> None:
    source = (REPO_ROOT / "mediator" / "interface.py").read_text(encoding="utf-8")
    broken = source.replace(
        f'INTERFACE_VERSION = "{INTERFACE_VERSION}"',
        'INTERFACE_VERSION = "0.9.0"',
        1,
    )
    assert broken != source
    destination = tmp_path / "mediator" / "interface.py"
    destination.parent.mkdir(parents=True)
    destination.write_text(broken, encoding="utf-8")
    (destination.parent / "__init__.py").write_text("", encoding="utf-8")

    result = _run_validator(["--root", str(REPO_ROOT), "--overlay", str(tmp_path)])
    assert result.returncode != 0
    assert "mediator.interface" in result.stderr
    assert "0.9.0" in result.stderr
    assert "import baseline ok" not in result.stdout


def test_partial_interface_version_exits_nonzero(tmp_path: Path) -> None:
    source = (REPO_ROOT / "lib" / "interface.py").read_text(encoding="utf-8")
    broken = source.replace(
        f'INTERFACE_VERSION = "{INTERFACE_VERSION}"',
        'INTERFACE_VERSION = "1.0"',
        1,
    )
    destination = tmp_path / "lib" / "interface.py"
    destination.parent.mkdir(parents=True)
    destination.write_text(broken, encoding="utf-8")
    (destination.parent / "__init__.py").write_text("", encoding="utf-8")
    result = _run_validator(["--root", str(REPO_ROOT), "--overlay", str(tmp_path)])
    assert result.returncode == 1
    assert "lib.interface" in result.stderr
    assert "1.0" in result.stderr


def test_missing_documentation_index_link_exits_nonzero(tmp_path: Path) -> None:
    index = tmp_path / "DOCUMENTATION_INDEX.md"
    index.write_text(
        "See [present](README.md) and [gone](docs/not-a-real-reorganization-target.md).\n",
        encoding="utf-8",
    )
    result = _run_validator(
        ["--root", str(REPO_ROOT), "--documentation-index", str(index)]
    )
    assert result.returncode == 1
    assert "docs/not-a-real-reorganization-target.md" in result.stderr


def test_broken_archive_index_exits_nonzero(tmp_path: Path) -> None:
    archive = tmp_path / "sessions"
    archive.mkdir()
    index = archive / "INDEX.md"
    index.write_text("[GONE.md](GONE.md)\n", encoding="utf-8")
    result = _run_validator(
        [
            "--root",
            str(REPO_ROOT),
            "--archive-index",
            str(index),
            "--archive-dir",
            str(archive),
        ]
    )
    assert result.returncode == 1
    assert "archive index" in result.stderr


def test_unlisted_import_bypass_exits_nonzero(tmp_path: Path) -> None:
    validator = _load_validator()
    root = tmp_path / "tree"
    package = root / "applications"
    package.mkdir(parents=True)
    (package / "new_bypass.py").write_text(
        "import mediator.mediator\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema": "complaint-generator/import-boundary-baseline@1",
                "bypasses": [],
            }
        ),
        encoding="utf-8",
    )
    failures = validator.check_import_baseline(root, baseline)
    assert failures
    assert any("applications/new_bypass.py" in item and "mediator.mediator" in item for item in failures)

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    assert validator.check_import_baseline(empty_root, baseline) == []


def test_completion_contract_has_no_authority_and_marks_no_task_complete() -> None:
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert document["schema"] == CONTRACT_SCHEMA
    assert document["completion_authority"] is False
    assert document["records_task_completion"] is False
    assert document["marks_tasks_complete"] is False
    assert document["completed_task_ids"] == []
    recorded = [item["id"] for item in document["tasks"]]
    assert recorded == list(CIMP_MOD_IDS)
    for item in document["tasks"]:
        assert item["id"].startswith("CIMP-MOD-")
        assert item["complete"] is False
    for obj in _walk_objects(document):
        assert obj.get("complete") is not True
        assert obj.get("status") != "complete"
        assert obj.get("completion_authority") is not True
