"""Import-boundary ratchet tests (CIMP-MOD-12).

Fixtures are temporary Python files. These tests do not import application
packages. They prove an unlisted bypass fails, a published interface import
passes, and baseline entries for the large owner modules stay allowed.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_import_boundaries.py"
BASELINE_PATH = REPO_ROOT / "docs" / "architecture" / "import_boundary_baseline.json"
SCHEMA = "complaint-generator/import-boundary-baseline@1"

LARGE_MODULE_BYPASSES = (
    ("applications/complaint_workspace.py", "complaint_phases.denoiser"),
    ("applications/complaint_workspace.py", "mediator.mediator"),
    ("mediator/mediator.py", "complaint_phases.denoiser"),
    ("mediator/mediator.py", "document_pipeline"),
)


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_import_boundaries", CHECKER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CHECKER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")


def _run_checker(root: Path, baseline: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--root",
            str(root),
            "--baseline",
            str(baseline),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def _baseline(path: Path, rows: list[dict[str, str]]) -> None:
    checker = _load_checker()
    document = checker.baseline_document(rows)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def test_baseline_records_current_bypasses_including_large_modules() -> None:
    checker = _load_checker()
    document = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert document["schema"] == SCHEMA
    assert document["task_id"] == "CIMP-MOD-12"
    recorded = {
        (row["path"], row["imported_module"]) for row in document["bypasses"]
    }
    for pair in LARGE_MODULE_BYPASSES:
        assert pair in recorded
    scanned = {
        (row["path"], row["imported_module"])
        for row in checker.scan_bypasses(REPO_ROOT)
    }
    assert scanned == recorded

    result = _run_checker(REPO_ROOT, BASELINE_PATH)
    assert result.returncode == 0, result.stderr
    assert "import boundary check ok" in result.stdout


def test_owner_package_import_is_not_a_bypass(tmp_path: Path) -> None:
    checker = _load_checker()
    _write(
        tmp_path / "mediator" / "helper.py",
        """
        from mediator.mediator import Mediator
        import mediator.mediator as mediator_module
        """,
    )
    _write(
        tmp_path / "applications" / "local_use.py",
        """
        from applications.complaint_workspace import ComplaintWorkspaceService
        """,
    )
    _write(
        tmp_path / "complaint_phases" / "phase_manager.py",
        """
        from complaint_phases.denoiser import project_stopping_policy
        """,
    )
    _write(
        tmp_path / "document_pipeline.py",
        """
        import document_pipeline
        """,
    )
    assert checker.scan_bypasses(tmp_path) == []


@pytest.mark.parametrize(
    "source",
    [
        "from mediator.mediator import Mediator\n",
        "import applications.complaint_workspace\n",
        "from complaint_phases.denoiser import ComplaintDenoiser\n",
        "import document_pipeline\n",
        "from applications import complaint_workspace\n",
    ],
)
def test_synthetic_new_bypass_fails(tmp_path: Path, source: str) -> None:
    baseline = tmp_path / "baseline.json"
    _baseline(baseline, [])
    root = tmp_path / "tree"
    _write(root / "fresh_feature.py", source)
    result = _run_checker(root, baseline)
    assert result.returncode != 0
    assert "unlisted bypass: fresh_feature.py imports" in result.stderr


def test_interface_import_passes(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _baseline(baseline, [])
    root = tmp_path / "tree"
    _write(
        root / "fresh_feature.py",
        """
        from mediator.interface import INTERFACE_SCHEMA, INTERFACE_VERSION
        from applications.interface import PUBLIC_SYMBOLS
        from complaint_phases.interface import MODULE
        """,
    )
    result = _run_checker(root, baseline)
    assert result.returncode == 0, result.stderr
    assert "import boundary check ok" in result.stdout


def test_baselined_large_module_stays_allowed_and_new_bypass_does_not(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    _baseline(
        baseline,
        [
            {
                "path": "applications/complaint_workspace.py",
                "imported_module": "mediator.mediator",
            }
        ],
    )
    root = tmp_path / "tree"
    _write(
        root / "applications" / "complaint_workspace.py",
        """
        from mediator.mediator import Mediator
        """,
    )
    allowed = _run_checker(root, baseline)
    assert allowed.returncode == 0, allowed.stderr

    _write(
        root / "applications" / "complaint_workspace.py",
        """
        from mediator.mediator import Mediator
        from document_pipeline import FormalComplaintDocumentBuilder
        """,
    )
    added = _run_checker(root, baseline)
    assert added.returncode != 0
    assert (
        "unlisted bypass: applications/complaint_workspace.py imports document_pipeline"
        in added.stderr
    )
    assert "imports mediator.mediator" not in added.stderr
