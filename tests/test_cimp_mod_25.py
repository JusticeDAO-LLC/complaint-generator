"""Operator-guide checks for module boundaries (CIMP-MOD-25).

The guide must state the package map, interface version 1.0.0, the import
ratchet, the submodule pin policy, and the files new work must not edit.
It must tell an operator how to run both boundary checkers. Relative links
must resolve. Pin and quarantine warnings must be present.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = REPO_ROOT / "docs" / "architecture" / "REPOSITORY.md"
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
SCHEMA_PATH = REPO_ROOT / "docs" / "architecture" / "module_interface_schema.json"
BASELINE_PATH = REPO_ROOT / "docs" / "architecture" / "import_boundary_baseline.json"

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
INTERFACE_CHECKER = "scripts/check_module_interface.py"
BOUNDARY_CHECKER = "scripts/check_import_boundaries.py"

GUARDED_MODULES = (
    "mediator.mediator",
    "applications.complaint_workspace",
    "complaint_phases.denoiser",
    "document_pipeline",
)
DO_NOT_EDIT = (
    "applications/complaint_workspace.py",
    "mediator/mediator.py",
    "mediator/claim_support_hooks.py",
    "complaint_phases/denoiser.py",
    "document_pipeline.py",
    "docs/task_boards/complaint_repository_reorganization_spec.json",
    "docs/task_boards/complaint_repository_reorganization_formal_work_plan.json",
    "docs/task_boards/complaint_repository_reorganization_task_board.md",
)
PINNED_CHECKOUTS = (
    "external/ipfs_accelerate_py",
    "external/ipfs_datasets_py",
    "external/ipfs_kit_py",
    "external/mike",
)
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

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_REMOTE_PREFIXES = ("http://", "https://", "mailto:")
_PACKAGE_ROW_RE = re.compile(r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|\s*\[", re.MULTILINE)


def guide_text() -> str:
    return GUIDE_PATH.read_text(encoding="utf-8")


def package_names() -> list[str]:
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    return [entry["name"] for entry in document["packages"]]


def relative_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in _LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith(_REMOTE_PREFIXES):
            continue
        targets.append(target.split("#", 1)[0].strip())
    return targets


def unresolved_links(text: str, base: Path) -> list[str]:
    missing: list[str] = []
    for target in relative_link_targets(text):
        if not target:
            missing.append(target)
            continue
        if not (base / target).resolve().is_file():
            missing.append(target)
    return missing


def pin_warning_present(text: str) -> bool:
    required = (
        "submodule pin policy",
        "Do not edit `external/`",
        "submodule gitlinks",
        "dependency pins",
        "Do not run `git submodule update`",
        "do not initialize nested submodules",
        "Do not float pins",
    )
    return all(phrase in text for phrase in required)


def quarantine_warning_present(text: str) -> bool:
    return (
        "Quarantine warning:" in text
        and "both retained quarantines stay untouched" in text
        and "quarantine records" in text
        and "Do not release, rewrite, or delete a quarantine record" in text
    )


def documented_packages(text: str) -> list[str]:
    section = text.split("## Package map", 1)[1].split("## Interface version", 1)[0]
    return _PACKAGE_ROW_RE.findall(section)


def test_guide_states_package_map_and_interface_version() -> None:
    text = guide_text()
    assert documented_packages(text) == package_names()
    assert "package map" in text.lower()
    assert MAP_PATH.is_file()
    assert "repository_module_map.json" in text

    assert "interface version" in text.lower()
    assert f"`{INTERFACE_VERSION}`" in text
    assert f"`{INTERFACE_SCHEMA}`" in text
    assert "INTERFACE_SCHEMA" in text
    assert "INTERFACE_VERSION" in text
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["interface_schema"] == INTERFACE_SCHEMA
    assert schema["checker"] == INTERFACE_CHECKER
    for module_name in PUBLISHED_INTERFACES:
        assert f"`{module_name}`" in text


def test_guide_states_import_ratchet_pin_policy_and_untouchable_files() -> None:
    text = guide_text()
    assert "import ratchet" in text.lower()
    assert "import_boundary_baseline.json" in text
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["schema"] == "complaint-generator/import-boundary-baseline@1"
    for module_name in GUARDED_MODULES:
        assert f"`{module_name}`" in text
    assert "unlisted bypass" in text

    assert pin_warning_present(text)
    for checkout in PINNED_CHECKOUTS:
        assert f"`{checkout}`" in text
    assert ".gitmodules" in text

    assert "files new work must not edit" in text.lower()
    for path in DO_NOT_EDIT:
        assert f"`{path}`" in text or path in text
    assert "DuckDB" in text
    assert "launcher files" in text
    assert "attempt counters" in text
    assert quarantine_warning_present(text)

    assert "Parallel work rule: tasks may edit only their declared targets." in text
    assert "origin/main" in text
    assert "origin/master" in text
    assert "already contain the published UX work" in text
    assert "does not reopen those boards" in text
    for board in ("intake", "mediator-grounding", "GUI collaboration", "GUI UX"):
        assert board in text


def test_operator_commands_and_every_relative_link_resolves() -> None:
    text = guide_text()
    assert f"python {INTERFACE_CHECKER} <module_name>" in text
    assert f"python {INTERFACE_CHECKER} mediator.interface" in text
    assert f"python {BOUNDARY_CHECKER}" in text
    assert f"python {BOUNDARY_CHECKER} --root ROOT --baseline PATH" in text
    assert "import boundary check ok" in text

    links = relative_link_targets(text)
    assert links, "guide has no relative links"
    assert unresolved_links(text, GUIDE_PATH.parent) == []
    for required in (
        "repository_module_map.json",
        "module_interface_schema.json",
        "import_boundary_baseline.json",
        "../../.gitmodules",
        "../../scripts/check_module_interface.py",
        "../../scripts/check_import_boundaries.py",
        "../../applications/complaint_workspace.py",
        "../../mediator/mediator.py",
        "../../document_pipeline.py",
    ):
        assert required in links


def test_rejects_missing_pin_and_quarantine_warnings_and_broken_links() -> None:
    text = guide_text()
    assert pin_warning_present(text)
    assert quarantine_warning_present(text)

    without_pin = text.replace("submodule pin policy", "submodule checkout note")
    without_pin = without_pin.replace("Do not float pins", "Pins may move")
    assert pin_warning_present(without_pin) is False

    without_quarantine = text.replace(
        "Quarantine warning: both retained quarantines stay untouched.",
        "Workspace notes stay local.",
    )
    assert quarantine_warning_present(without_quarantine) is False

    broken = text.replace(
        "(repository_module_map.json)",
        "(repository_module_map_missing.json)",
    )
    missing = unresolved_links(broken, GUIDE_PATH.parent)
    assert "repository_module_map_missing.json" in missing
    assert unresolved_links(text, GUIDE_PATH.parent) == []

    dropped_package = text.replace("| `mediator` |", "| `not_a_package` |", 1)
    assert documented_packages(dropped_package) != package_names()
    assert "mediator" in package_names()
    assert "not_a_package" not in package_names()

    wrong_version = text.replace("`1.0.0`", "`9.9.9`")
    assert f"`{INTERFACE_VERSION}`" not in wrong_version
    assert "python scripts/check_module_interface.py" not in text.replace(
        "python scripts/check_module_interface.py",
        "python scripts/skip_module_interface.py",
    )
