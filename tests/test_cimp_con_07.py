"""CIMP-CON-07: root checks and tracked debug snapshots leave the root."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "scripts" / "legacy_root_checks"
SNAPSHOTS = ROOT / "docs" / "archive" / "debug_snapshots"

LEGACY_CHECKS = (
    "test_complaint_mcp_protocol.py",
    "test_criticscor_comparisons.py",
    "test_extraction_config_validation.py",
    "test_main_app_surface.py",
    "test_parallel_validation_fix.py",
    "test_pipeline_error_recovery.py",
    "test_probate_integration.py",
)

SNAPSHOT_SIZES = {
    "tmp_validation_llm_draft/validation-user.json": 9642,
    "tmp_validation_llm_enabled/llm-user.json": 9602,
    "tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json": 330,
    "workspace/improve_temporary_session_complaint.py": 554,
    "workspace/temporary-cli-session-migration/README.md": 3963,
}


def test_legacy_root_checks_are_outside_pytest_collection() -> None:
    for name in LEGACY_CHECKS:
        assert not (ROOT / name).exists(), name
        destination = CHECKS / name
        assert destination.is_file(), name
        assert destination.stat().st_size > 0, name
    testpaths: list[str] = []
    in_testpaths = False
    for line in (ROOT / "pytest.ini").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("testpaths"):
            in_testpaths = True
            continue
        if in_testpaths:
            if stripped and not line.startswith((" ", "\t")):
                break
            if stripped:
                testpaths.append(stripped)
    assert testpaths == ["tests"]
    assert "scripts/legacy_root_checks" not in testpaths
    assert (ROOT / "artifacts").exists()


def test_tracked_debug_snapshots_keep_their_byte_sizes() -> None:
    for relative, size in SNAPSHOT_SIZES.items():
        assert not (ROOT / relative).exists(), relative
        destination = SNAPSHOTS / relative
        assert destination.is_file(), relative
        assert destination.stat().st_size == size, relative
