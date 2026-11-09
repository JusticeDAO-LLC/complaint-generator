"""CIMP-CON-26: standalone consolidation ratchet.

Names, byte sizes, and line floors are hard-coded. This module does not
import helpers from tests/test_cimp_mod_19.py or earlier CIMP-CON tests.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ROOT_MARKDOWN = frozenset(
    {
        "README.md",
        "DOCUMENTATION_INDEX.md",
        "CONTRIBUTING.md",
        "TESTING.md",
        "TODO.md",
    }
)
ROOT_PYTHON = frozenset(
    {
        "main.py",
        "run.py",
        "setup.py",
        "intake_status.py",
        "workflow_phase_guidance.py",
        "document_pipeline.py",
        "document_optimization.py",
        "claim_support_review.py",
    }
)
SHIMS = frozenset(
    {
        "intake_status.py",
        "workflow_phase_guidance.py",
        "document_pipeline.py",
        "document_optimization.py",
        "claim_support_review.py",
    }
)
SESSIONS = {
    "AUTONOMOUS_SESSION_REPORT.md": 14822,
    "BATCH_254_258_SESSION_SUMMARY.md": 15081,
    "BATCH_305_306_SESSION_SUMMARY.md": 6799,
    "BATCH_328_API_RETURN_TYPES_SUMMARY.md": 11564,
    "BATCH_329_EXCEPTION_HANDLING_SUMMARY.md": 11919,
    "BENCHMARK_SUITE_SESSION_SUMMARY.md": 10574,
    "ITEM_7_COMPLETION_SUMMARY.md": 9658,
    "P3_INFRASTRUCTURE_COMPLETION_SESSION.md": 6935,
    "P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md": 8334,
    "PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md": 10410,
    "PHASE_2_COMPLETION_SUMMARY.md": 5565,
    "QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md": 7895,
    "QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md": 15427,
    "README_OLD.md": 817,
    "README_OLD_BACKUP.md": 16697,
    "README_OLD_FULL.md": 30925,
    "SESSION_3_COMPLETE_SUMMARY.md": 12676,
    "SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md": 8397,
    "SESSION_84_FINAL_SUMMARY.md": 7741,
    "SESSION_84_PHASE4_EXTENDED_SUMMARY.md": 17752,
    "SESSION_84_PHASE4_SUMMARY.md": 13483,
    "SESSION_84_PROGRESS.md": 13783,
    "SESSION_SUMMARY_2024_02_24.md": 10746,
    "SESSION_SUMMARY_2026_02_23.md": 8389,
    "SESSION_SUMMARY_2026_02_24_COMPLETE.md": 13118,
    "SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md": 5478,
    "SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md": 8261,
}
REPORTS = {
    "AUDIT_DICT_RETURNS_REPORT.md": 3979,
    "BATCH_202_PLAN.md": 4452,
    "EXTRACTION_PIPELINE_PROFILE_FINAL.md": 10708,
    "PARALLEL_VALIDATION_FIX_REPORT.md": 4095,
    "UNIFIED_PERFORMANCE_ANALYSIS.md": 12002,
    "plan-mcpPlusPlusIntegration.prompt.md": 6459,
}
DEBUG_SNAPSHOTS = {
    "tmp_validation_llm_draft/validation-user.json": 9642,
    "tmp_validation_llm_enabled/llm-user.json": 9602,
    "tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json": 330,
    "workspace/improve_temporary_session_complaint.py": 554,
    "workspace/temporary-cli-session-migration/README.md": 3963,
}
MAINTENANCE_SCRIPTS = (
    "add_dedup_factory.py",
    "add_init_vars.py",
    "add_optimization_methods.py",
    "batch_230_benchmark.py",
    "batch_231_llm_fallback_profile.py",
    "complete_optimizer_integration.py",
    "profile_generate_10k.py",
    "update_detect_graph_type.py",
)
LEGACY_CHECKS = (
    "test_complaint_mcp_protocol.py",
    "test_criticscor_comparisons.py",
    "test_extraction_config_validation.py",
    "test_main_app_surface.py",
    "test_parallel_validation_fix.py",
    "test_pipeline_error_recovery.py",
    "test_probate_integration.py",
)
LINE_FLOORS = (
    ("complaint_phases/document_pipeline.py", 10200, None),
    ("complaint_phases/document_pipeline_readiness.py", None, 950),
    ("complaint_phases/document_pipeline_guidance.py", None, 800),
    ("complaint_phases/document_optimization.py", 4200, None),
    ("complaint_phases/document_optimization_summaries.py", None, 650),
    ("mediator/claim_support_review.py", 4700, None),
    ("mediator/claim_support_review_sections.py", None, 1600),
    ("applications/complaint_workspace.py", 18300, None),
    ("applications/complaint_workspace_drafting.py", None, 1250),
    ("mediator/mediator.py", 13600, None),
    ("mediator/intake_question_flow.py", None, 1450),
    ("complaint_phases/denoiser.py", 7900, None),
    ("complaint_phases/denoiser_questions.py", None, 1000),
    ("mediator/claim_support_hooks.py", 9600, None),
    ("mediator/claim_support_diagnostics.py", None, 1050),
)
FORBIDDEN_IMPORTS = {
    "main.py": ("mediator.mediator",),
    "mediator/hook_runtime.py": ("mediator.mediator", "mediator.claim_support_hooks"),
    "mediator/workflow_service.py": ("mediator.mediator", "mediator.claim_support_hooks"),
    "applications/complaint_cli.py": ("complaint_phases.denoiser",),
    "complaint_phases/phase_manager.py": ("complaint_phases.denoiser",),
    "applications/document_api.py": (
        "document_pipeline",
        "document_optimization",
        "intake_status",
        "workflow_phase_guidance",
    ),
    "applications/review_api.py": ("claim_support_review",),
    "adversarial_harness/optimizer.py": ("workflow_phase_guidance",),
}
ARCHIVE_INDEXES = (
    "docs/archive/sessions/INDEX.md",
    "docs/archive/reports/INDEX.md",
)
_INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_DEFINITION = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:[ \t]+(\S+)")
_AUTOLINK = re.compile(r"(?<![A-Za-z0-9_])<([^>\s]+)>")


def _percent_decode(text: str) -> str:
    parts = text.split("%")
    decoded = [parts[0]]
    for part in parts[1:]:
        if len(part) >= 2:
            try:
                decoded.append(bytes.fromhex(part[:2]).decode("utf-8") + part[2:])
                continue
            except ValueError:
                pass
        decoded.append("%" + part)
    return "".join(decoded)


def _destination(raw: str) -> str | None:
    text = raw.strip()
    if text.startswith("<") and ">" in text:
        text = text[1 : text.find(">")].strip()
    elif " " in text:
        text = text.split()[0]
    if not text or text.startswith("#") or "://" in text or text.startswith("mailto:"):
        return None
    text = _percent_decode(text.split("#", 1)[0].split("?", 1)[0].strip())
    return text or None


def _unresolved_links(relative_doc: str) -> list[str]:
    document = REPO_ROOT / relative_doc
    text = document.read_text(encoding="utf-8")
    raw_targets = [match.group(1) for match in _INLINE_LINK.finditer(text)]
    raw_targets.extend(match.group(1) for match in _DEFINITION.finditer(text))
    for match in _AUTOLINK.finditer(text):
        candidate = match.group(1)
        if "://" in candidate or "@" in candidate:
            continue
        if "/" in candidate or candidate.endswith((".md", ".py", ".json", ".yml")):
            raw_targets.append(candidate)
    missing = []
    for raw in raw_targets:
        target = _destination(raw)
        if target is None:
            continue
        if not (document.parent / target).resolve().exists():
            missing.append(f"{relative_doc} -> {target}")
    return missing


def _imported_modules(relative_path: str) -> set[str]:
    path = REPO_ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = path.relative_to(REPO_ROOT).parts[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package) - (node.level - 1)
                base = package[:keep] if keep > 0 else ()
                if node.module:
                    names.add(".".join((*base, *node.module.split("."))))
                for alias in node.names:
                    names.add(".".join((*base, alias.name)))
            elif node.module:
                names.add(node.module)
                for alias in node.names:
                    names.add(f"{node.module}.{alias.name}")
    return names


def _lines(relative_path: str) -> int:
    return len((REPO_ROOT / relative_path).read_text(encoding="utf-8").splitlines())


def test_root_markdown_is_exactly_the_five_current_docs() -> None:
    found = {path.name for path in REPO_ROOT.glob("*.md") if path.is_file()}
    assert found == ROOT_MARKDOWN


def test_archived_files_keep_recorded_sizes_and_leave_the_root() -> None:
    for name, size in SESSIONS.items():
        assert not (REPO_ROOT / name).exists(), name
        archived = REPO_ROOT / "docs" / "archive" / "sessions" / name
        assert archived.is_file(), name
        assert archived.stat().st_size == size, name
    for name, size in REPORTS.items():
        assert not (REPO_ROOT / name).exists(), name
        archived = REPO_ROOT / "docs" / "archive" / "reports" / name
        assert archived.is_file(), name
        assert archived.stat().st_size == size, name
    for relative, size in DEBUG_SNAPSHOTS.items():
        assert not (REPO_ROOT / relative).exists(), relative
        archived = REPO_ROOT / "docs" / "archive" / "debug_snapshots" / relative
        assert archived.is_file(), relative
        assert archived.stat().st_size == size, relative
    for relative in ARCHIVE_INDEXES:
        assert (REPO_ROOT / relative).is_file(), relative
        assert _unresolved_links(relative) == [], relative


def test_maintenance_scripts_and_legacy_checks_left_the_root() -> None:
    for name in MAINTENANCE_SCRIPTS:
        assert not (REPO_ROOT / name).exists(), name
        assert (REPO_ROOT / "scripts" / "maintenance" / name).is_file(), name
    for name in LEGACY_CHECKS:
        assert not (REPO_ROOT / name).exists(), name
        assert (REPO_ROOT / "scripts" / "legacy_root_checks" / name).is_file(), name


def test_root_python_is_only_entrypoints_and_short_shims() -> None:
    found = {path.name for path in REPO_ROOT.glob("*.py") if path.is_file()}
    assert found == ROOT_PYTHON
    for name in SHIMS:
        path = REPO_ROOT / name
        assert _lines(name) <= 30, name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        defined = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        assert defined == [], name


def test_owner_and_sibling_line_floors() -> None:
    for relative, maximum, minimum in LINE_FLOORS:
        count = _lines(relative)
        if maximum is not None:
            assert count <= maximum, f"{relative} has {count} lines"
        if minimum is not None:
            assert count >= minimum, f"{relative} has {count} lines"


def test_production_callers_do_not_import_forbidden_modules() -> None:
    for relative, banned in FORBIDDEN_IMPORTS.items():
        imported = _imported_modules(relative)
        for name in sorted(imported):
            for ban in banned:
                assert name != ban and not name.startswith(ban + "."), f"{relative} imports {name}"


def test_interface_exports_are_the_owner_objects() -> None:
    import applications.interface as applications_interface
    import applications.server as applications_server
    import complaint_phases.denoiser as denoiser
    import complaint_phases.interface as phases_interface
    import mediator.interface as mediator_interface
    import mediator.mediator as mediator_owner

    assert applications_interface.SERVER is applications_server.SERVER
    assert mediator_interface.Mediator is mediator_owner.Mediator
    assert phases_interface.ComplaintDenoiser is denoiser.ComplaintDenoiser
