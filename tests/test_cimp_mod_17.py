"""README checks for the current modules and remote (CIMP-MOD-17).

The README must name every current package, the external submodule
checkouts, and the endomorphosis/complaint-generator remote. It must describe
versioned package interfaces and tell readers not to import giant
implementation modules. These tests fail when the README presents
JusticeDAO-LLC workflow badges as status, omits or invents a package, or
links to a root SESSION_ or BATCH_ file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Checkout paths and remote URLs are documentation fixtures. They must not
# trip the repository's content-based network or heavy-test gates.
pytestmark = [
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
GITMODULES_PATH = REPO_ROOT / ".gitmodules"

REMOTE = "endomorphosis/complaint-generator"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
EXTERNAL_CHECKOUTS = (
    "external/ipfs_accelerate_py",
    "external/ipfs_datasets_py",
    "external/ipfs_kit_py",
    "external/mike",
)
GIANT_IMPLEMENTATION_MODULES = (
    "applications/complaint_workspace.py",
    "mediator/mediator.py",
    "document_pipeline.py",
    "mediator/claim_support_hooks.py",
    "complaint_phases/denoiser.py",
)
VERSIONED_INTERFACE_MODULES = (
    "applications.interface",
    "mediator.interface",
    "complaint_phases.interface",
    "complaint_generator.interface",
    "lib.interface",
    "integrations.ipfs_accelerate.interface",
    "integrations.ipfs_datasets.interface",
    "integrations.mike.interface",
)

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)|<([^>\s]+)>")
_BADGE_URL_RE = re.compile(
    r"https?://github\.com/JusticeDAO-LLC/[^\s)]+/badge\.svg",
    re.IGNORECASE,
)
_PACKAGE_ROW_RE = re.compile(r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|", re.MULTILINE)
_SECTION_RE = re.compile(r"^## Current packages\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


def current_package_names() -> list[str]:
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    return [entry["name"] for entry in document["packages"]]


def justice_dao_badge_urls(text: str) -> list[str]:
    """Return JusticeDAO-LLC workflow badge URLs presented in markdown."""
    return _BADGE_URL_RE.findall(text)


def markdown_link_targets(text: str) -> list[str]:
    targets = []
    for match in _LINK_RE.finditer(text):
        targets.append(match.group(1) or match.group(2))
    return targets


def root_session_or_batch_links(text: str) -> list[str]:
    """Return markdown links whose path is a root SESSION_ or BATCH_ file."""
    found = []
    for target in markdown_link_targets(text):
        path = target.split("#", 1)[0].split("?", 1)[0]
        if "://" in path:
            continue
        normalized = path[2:] if path.startswith("./") else path
        if "/" in normalized.strip("/"):
            continue
        name = normalized.strip("/")
        if name.startswith("SESSION_") or name.startswith("BATCH_"):
            found.append(target)
    return found


def packages_named_in_current_packages(text: str) -> list[str]:
    match = _SECTION_RE.search(text)
    if match is None:
        return []
    return _PACKAGE_ROW_RE.findall(match.group(1))


def missing_package_claims(text: str, known_packages: list[str]) -> list[str]:
    """Packages the Current packages section claims that the module map lacks, plus map packages the section omits."""
    claimed = packages_named_in_current_packages(text)
    known = set(known_packages)
    invented = [name for name in claimed if name not in known]
    omitted = [name for name in known_packages if name not in claimed]
    return invented + omitted


def test_readme_names_current_packages_external_checkouts_and_remote():
    text = readme_text()
    packages = current_package_names()
    assert packages, "module map must list current packages"
    assert missing_package_claims(text, packages) == []
    for checkout in EXTERNAL_CHECKOUTS:
        assert checkout in text
    assert REMOTE in text
    assert "https://github.com/endomorphosis/complaint-generator" in text
    gitmodules = GITMODULES_PATH.read_text(encoding="utf-8")
    for checkout in EXTERNAL_CHECKOUTS:
        assert f"path = {checkout}" in gitmodules


def test_readme_describes_versioned_interfaces_and_refuses_giant_imports():
    text = readme_text()
    assert INTERFACE_SCHEMA in text
    assert INTERFACE_VERSION in text
    for module in VERSIONED_INTERFACE_MODULES:
        assert module in text
    lowered = text.lower()
    assert "does not import giant implementation modules" in lowered
    assert "do not import" in lowered
    for path in GIANT_IMPLEMENTATION_MODULES:
        assert path in text
    assert "applications.complaint_workspace" in text
    assert "mediator.mediator" in text
    assert "complaint_phases.denoiser" in text


def test_readme_has_no_justice_dao_badge_urls():
    badges = justice_dao_badge_urls(readme_text())
    assert badges == []


def test_readme_does_not_link_root_session_or_batch_files():
    links = root_session_or_batch_links(readme_text())
    assert links == []


def test_negative_justice_dao_badge_url_is_detected():
    sample = (
        "[![Standard Regression](https://github.com/JusticeDAO-LLC/complaint-generator/"
        "actions/workflows/standard-regression.yml/badge.svg)]"
        "(https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/standard-regression.yml)"
    )
    found = justice_dao_badge_urls(sample)
    assert found == [
        "https://github.com/JusticeDAO-LLC/complaint-generator/actions/workflows/standard-regression.yml/badge.svg"
    ]
    assert justice_dao_badge_urls("Remote: endomorphosis/complaint-generator") == []


def test_negative_missing_package_claim_is_detected():
    known = ["applications", "mediator"]
    invented = "## Current packages\n\n| `applications` | surface |\n| `not_a_package` | invented |\n\n## Next\n"
    omitted = "## Current packages\n\n| `applications` | surface |\n\n## Next\n"
    assert "not_a_package" in missing_package_claims(invented, known)
    assert "mediator" in missing_package_claims(omitted, known)
    complete = (
        "## Current packages\n\n| `applications` | surface |\n| `mediator` | orchestration |\n\n## Next\n"
    )
    assert missing_package_claims(complete, known) == []


def test_negative_root_session_and_batch_links_are_detected():
    sample = "\n".join(
        [
            "See [session](SESSION_84_PROGRESS.md) and [batch](./BATCH_328_API_RETURN_TYPES_SUMMARY.md).",
            "Keep [archive](docs/archive/sessions/SESSION_84_PROGRESS.md).",
            "Keep [plan](docs/task_boards/complaint_repository_reorganization_task_board.md).",
            "Autolink <BATCH_202_PLAN.md> stays a root link.",
        ]
    )
    assert root_session_or_batch_links(sample) == [
        "SESSION_84_PROGRESS.md",
        "./BATCH_328_API_RETURN_TYPES_SUMMARY.md",
        "BATCH_202_PLAN.md",
    ]


def test_complaint_preparation_names_three_phases_from_the_package():
    text = readme_text()
    assert "initial intake and denoising" in text.lower()
    assert "evidence gathering" in text.lower()
    assert "formal complaint" in text.lower()
    assert "python -m complaint_generator.cli chat --user-id USER_ID" in text


@pytest.mark.parametrize(
    "snippet",
    [
        "https://github.com/endomorphosis/complaint-generator",
        "external/ipfs_kit_py",
        "complaint-generator/module-interface@1",
    ],
)
def test_positive_required_phrases_are_not_badge_or_root_report_links(snippet: str):
    assert justice_dao_badge_urls(snippet) == []
    assert root_session_or_batch_links(f"See [{snippet}]({snippet}).") == []
