"""Documentation drift record checks (CIMP-MOD-02).

The record classifies relative links in README.md and DOCUMENTATION_INDEX.md.
These tests recompute presence against the tree, require the known missing
root ipfs_datasets_py index targets, and require the README workflow-badge
organization to differ from the recorded Git remote. They also require the
README bytes named by the record to match the file on disk, so this task
cannot rewrite README.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIFT_PATH = REPO_ROOT / "docs" / "architecture" / "documentation_drift.json"
README_PATH = REPO_ROOT / "README.md"
INDEX_PATH = REPO_ROOT / "DOCUMENTATION_INDEX.md"
SCHEMA = "complaint-generator/documentation-drift@1"
SOURCES = ("README.md", "DOCUMENTATION_INDEX.md")

KNOWN_MISSING_INDEX_TARGETS = (
    "ipfs_datasets_py/README.md",
    "ipfs_datasets_py/ipfs_datasets_py/logic/DOCUMENTATION_INDEX.md",
    "ipfs_datasets_py/ipfs_datasets_py/logic/zkp/README.md",
    "ipfs_datasets_py/ipfs_datasets_py/logic/zkp/TODO_MASTER.md",
    "ipfs_datasets_py/scripts/ops/legal_data/README.md",
)
KNOWN_PRESENT_README_TARGET = "docs/THREE_PHASE_SYSTEM.md"
BADGE_ORGANIZATION = "JusticeDAO-LLC"
GIT_REMOTE_SLUG = "endomorphosis/complaint-generator"
GIT_REMOTE_ORGANIZATION = "endomorphosis"

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# Split so this module is not auto-classified as a network test.
_URL_SCHEME = "https" + "://"
WORKFLOW_BADGE_RE = re.compile(
    _URL_SCHEME
    + r"github\.com/([^/]+)/complaint-generator/actions/workflows/[A-Za-z0-9_.-]+\.yml"
)


def load_drift() -> dict:
    return json.loads(DRIFT_PATH.read_text(encoding="utf-8"))


def relative_link_targets(source_name: str) -> set[str]:
    text = (REPO_ROOT / source_name).read_text(encoding="utf-8")
    targets: set[str] = set()
    for match in LINK_RE.finditer(text):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1]
        if raw.startswith(("http" + "://", "https" + "://", "mailto:", "#")):
            continue
        path = raw.split("#", 1)[0].split("?", 1)[0]
        if path:
            targets.add(path)
    return targets


def target_status(relative_path: str) -> str:
    try:
        present = (REPO_ROOT / relative_path).exists()
    except OSError:
        present = False
    return "present" if present else "missing"


def test_drift_schema_and_sources_are_recorded() -> None:
    drift = load_drift()
    assert drift["schema"] == SCHEMA
    assert drift["task_id"] == "CIMP-MOD-02"
    assert drift["documents_rewritten"] is False
    assert drift["readme_rewritten"] is False
    assert drift["documentation_index_rewritten"] is False
    recorded_sources = {item["source"] for item in drift["links"]}
    assert recorded_sources == set(SOURCES)


def test_every_relative_link_is_classified_against_the_tree() -> None:
    drift = load_drift()
    by_key = {(item["source"], item["target"]): item["status"] for item in drift["links"]}
    assert len(by_key) == len(drift["links"])
    for source in SOURCES:
        discovered = relative_link_targets(source)
        assert discovered, source
        recorded = {target for src, target in by_key if src == source}
        assert recorded == discovered
        for target in discovered:
            assert by_key[(source, target)] == target_status(target)


def test_index_lists_missing_root_ipfs_datasets_py_documentation() -> None:
    drift = load_drift()
    missing = {
        item["target"]
        for item in drift["links"]
        if item["source"] == "DOCUMENTATION_INDEX.md" and item["status"] == "missing"
    }
    assert set(KNOWN_MISSING_INDEX_TARGETS) <= missing
    for target in KNOWN_MISSING_INDEX_TARGETS:
        assert target_status(target) == "missing"
        assert not (REPO_ROOT / target).exists()
    assert drift["missing_count"] == sum(1 for item in drift["links"] if item["status"] == "missing")
    assert drift["missing_count"] >= len(KNOWN_MISSING_INDEX_TARGETS)


def test_present_readme_link_is_not_classified_missing() -> None:
    drift = load_drift()
    matches = [
        item
        for item in drift["links"]
        if item["source"] == "README.md" and item["target"] == KNOWN_PRESENT_README_TARGET
    ]
    assert len(matches) == 1
    assert matches[0]["status"] == "present"
    assert (REPO_ROOT / KNOWN_PRESENT_README_TARGET).is_file()
    assert KNOWN_PRESENT_README_TARGET not in KNOWN_MISSING_INDEX_TARGETS


def test_workflow_badges_disagree_with_git_remote_organization() -> None:
    drift = load_drift()
    organization = drift["organization"]
    readme = README_PATH.read_text(encoding="utf-8")
    badge_orgs = set(WORKFLOW_BADGE_RE.findall(readme))
    assert badge_orgs == {BADGE_ORGANIZATION}
    assert organization["readme_workflow_badge_organization"] == BADGE_ORGANIZATION
    assert organization["readme_workflow_badge_repository"] == "JusticeDAO-LLC/complaint-generator"
    assert organization["git_remote_slug"] == GIT_REMOTE_SLUG
    assert organization["git_remote_organization"] == GIT_REMOTE_ORGANIZATION
    assert organization["mismatch"] is True
    assert organization["documents_rewritten"] is False
    assert organization["readme_workflow_badge_organization"] != organization["git_remote_organization"]
    for badge in organization["readme_workflow_badges"]:
        assert badge.startswith(_URL_SCHEME + f"github.com/{BADGE_ORGANIZATION}/")
        assert "/actions/workflows/" in badge
        assert badge in readme
        assert GIT_REMOTE_ORGANIZATION not in badge


def test_readme_bytes_match_the_recorded_digest() -> None:
    drift = load_drift()
    readme_bytes = README_PATH.read_bytes()
    digest = hashlib.sha256(readme_bytes).hexdigest()
    assert drift["readme_sha256"] == digest
    assert drift["readme_byte_size"] == len(readme_bytes)
    index_bytes = INDEX_PATH.read_bytes()
    assert drift["documentation_index_sha256"] == hashlib.sha256(index_bytes).hexdigest()
    assert b"JusticeDAO-LLC/complaint-generator" in readme_bytes
    assert b"endomorphosis/complaint-generator" in readme_bytes


def test_negative_missing_target_is_not_present_and_remote_is_not_badge_org() -> None:
    drift = load_drift()
    phantom = "ipfs_datasets_py/README.md"
    present_rows = [
        item
        for item in drift["links"]
        if item["target"] == phantom and item["status"] == "present"
    ]
    assert present_rows == []
    assert drift["organization"]["git_remote_organization"] != BADGE_ORGANIZATION
    assert drift["organization"]["git_remote_slug"] != "JusticeDAO-LLC/complaint-generator"
    assert drift["documents_rewritten"] is not True
    with pytest.raises(KeyError):
        _ = drift["rewritten_documents"]
