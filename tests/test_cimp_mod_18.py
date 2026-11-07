"""Documentation index link checks (CIMP-MOD-18).

Relative links in DOCUMENTATION_INDEX.md must name files in this checkout.
The missing root ipfs_datasets_py logic index is replaced by the in-tree
datasets logic facade. The index also names the repository module map and
the versioned interface schema. These tests do not fetch external
documentation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "DOCUMENTATION_INDEX.md"
TESTS_README = REPO_ROOT / "tests" / "README.md"
MODULE_MAP = "docs/architecture/repository_module_map.json"
INTERFACE_SCHEMA = "docs/architecture/module_interface_schema.json"
LOGIC_REPLACEMENT = "integrations/ipfs_datasets/logic.py"

# Targets the CIMP-MOD-02 drift record marked missing under the root
# ipfs_datasets_py tree. They stay absent; the index must not link them.
DRIFT_MISSING_TARGETS = (
    "ipfs_datasets_py/README.md",
    "ipfs_datasets_py/ipfs_datasets_py/logic/DOCUMENTATION_INDEX.md",
    "ipfs_datasets_py/ipfs_datasets_py/logic/zkp/README.md",
    "ipfs_datasets_py/ipfs_datasets_py/logic/zkp/TODO_MASTER.md",
    "ipfs_datasets_py/scripts/ops/legal_data/README.md",
)

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
NINETEEN_FILE_CLAIM = re.compile(r"19[- ]files?(?:\s+suite)?", re.IGNORECASE)


def index_text() -> str:
    return INDEX_PATH.read_text(encoding="utf-8")


def relative_link_targets(text: str) -> list[str]:
    """Extract relative markdown link targets. External URLs are ignored."""
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
    return targets


def missing_relative_targets(text: str, root: Path | None = None) -> list[str]:
    """Return relative link targets that are not files under root."""
    base = REPO_ROOT if root is None else root
    missing: list[str] = []
    for target in relative_link_targets(text):
        candidate = (base / target).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            missing.append(target)
            continue
        if not candidate.is_file():
            missing.append(target)
    return missing


def test_every_relative_link_resolves_to_a_file() -> None:
    missing = missing_relative_targets(index_text())
    assert missing == []
    targets = relative_link_targets(index_text())
    assert targets, "DOCUMENTATION_INDEX.md has no relative links"


def test_index_points_at_module_map_schema_and_logic_replacement() -> None:
    targets = set(relative_link_targets(index_text()))
    assert MODULE_MAP in targets
    assert INTERFACE_SCHEMA in targets
    assert LOGIC_REPLACEMENT in targets
    assert (REPO_ROOT / MODULE_MAP).is_file()
    assert (REPO_ROOT / INTERFACE_SCHEMA).is_file()
    assert (REPO_ROOT / LOGIC_REPLACEMENT).is_file()
    text = index_text()
    assert "complaint-generator/module-interface@1" in text
    assert "complaint-generator/module-interface-schema@1" in text


def test_drift_missing_ipfs_datasets_targets_are_not_linked() -> None:
    targets = set(relative_link_targets(index_text()))
    still_linked = [target for target in DRIFT_MISSING_TARGETS if target in targets]
    assert still_linked == []
    for target in DRIFT_MISSING_TARGETS:
        assert not (REPO_ROOT / target).is_file()


def test_tests_readme_is_not_described_as_a_19_file_suite() -> None:
    readme = TESTS_README.read_text(encoding="utf-8")
    index = index_text()
    readme_claims_nineteen = bool(NINETEEN_FILE_CLAIM.search(readme))
    if readme_claims_nineteen:
        return
    assert NINETEEN_FILE_CLAIM.search(index) is None
    assert "tests/README.md" in relative_link_targets(index)


def test_missing_relative_target_fails_without_network(tmp_path: Path) -> None:
    present = tmp_path / "docs"
    present.mkdir()
    (present / "present.md").write_text("ok\n", encoding="utf-8")
    sample = (
        "See [present](docs/present.md), [gone](docs/missing.md), "
        "and [web](https://example.invalid/docs).\n"
    )
    assert missing_relative_targets(sample, root=tmp_path) == ["docs/missing.md"]
    assert "https://example.invalid/docs" not in relative_link_targets(sample)


def test_directory_and_escaped_targets_are_not_files(tmp_path: Path) -> None:
    (tmp_path / "only_dir").mkdir()
    outside = tmp_path.parent / "cimp_mod_18_outside.md"
    sample = (
        "[dir](only_dir) [up](../cimp_mod_18_outside.md) "
        "[anchor](#local) [mail](mailto:docs@example.invalid)\n"
    )
    missing = missing_relative_targets(sample, root=tmp_path)
    assert "only_dir" in missing
    assert "../cimp_mod_18_outside.md" in missing
    assert not outside.exists()
    extracted = relative_link_targets(sample)
    assert "#local" not in extracted
    assert all(not item.startswith("mailto:") for item in extracted)
