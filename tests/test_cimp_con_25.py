"""CIMP-CON-25: root docs describe the moved tree and their links resolve."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_DOCS = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
)
KEEPER_MARKDOWN = frozenset(ROOT_DOCS + ("TODO.md",))
BARE_ARCHIVED_NAMES = frozenset(
    {
        "AUTONOMOUS_SESSION_REPORT.md",
        "BATCH_254_258_SESSION_SUMMARY.md",
        "BATCH_305_306_SESSION_SUMMARY.md",
        "BATCH_328_API_RETURN_TYPES_SUMMARY.md",
        "BATCH_329_EXCEPTION_HANDLING_SUMMARY.md",
        "BENCHMARK_SUITE_SESSION_SUMMARY.md",
        "ITEM_7_COMPLETION_SUMMARY.md",
        "P3_INFRASTRUCTURE_COMPLETION_SESSION.md",
        "P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md",
        "PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md",
        "PHASE_2_COMPLETION_SUMMARY.md",
        "QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md",
        "QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md",
        "README_OLD.md",
        "README_OLD_BACKUP.md",
        "README_OLD_FULL.md",
        "SESSION_3_COMPLETE_SUMMARY.md",
        "SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md",
        "SESSION_84_FINAL_SUMMARY.md",
        "SESSION_84_PHASE4_EXTENDED_SUMMARY.md",
        "SESSION_84_PHASE4_SUMMARY.md",
        "SESSION_84_PROGRESS.md",
        "SESSION_SUMMARY_2024_02_24.md",
        "SESSION_SUMMARY_2026_02_23.md",
        "SESSION_SUMMARY_2026_02_24_COMPLETE.md",
        "SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md",
        "SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md",
        "AUDIT_DICT_RETURNS_REPORT.md",
        "BATCH_202_PLAN.md",
        "EXTRACTION_PIPELINE_PROFILE_FINAL.md",
        "PARALLEL_VALIDATION_FIX_REPORT.md",
        "UNIFIED_PERFORMANCE_ANALYSIS.md",
        "plan-mcpPlusPlusIntegration.prompt.md",
    }
)
REQUIRED_PHRASES = (
    "docs/archive/sessions",
    "docs/archive/reports",
    "complaint_phases",
    "root shims",
    "mediator/claim_support_review.py",
    "INTERFACE_SCHEMA",
    "complaint-generator/module-interface@1",
    "INTERFACE_VERSION",
    "1.0.0",
    "endomorphosis/complaint-generator",
)
EXTRACTED_SIBLINGS = (
    ("complaint_phases/intake_status.py", "intake_status.py"),
    ("complaint_phases/workflow_phase_guidance.py", "workflow_phase_guidance.py"),
    ("complaint_phases/document_pipeline.py", "document_pipeline.py"),
    ("complaint_phases/document_optimization.py", "document_optimization.py"),
    ("mediator/claim_support_review.py", "claim_support_review.py"),
    ("complaint_phases/document_pipeline_guidance.py", "complaint_phases/document_pipeline.py"),
    ("mediator/claim_support_review_sections.py", "mediator/claim_support_review.py"),
    ("complaint_phases/document_pipeline_readiness.py", "complaint_phases/document_pipeline.py"),
    ("complaint_phases/document_optimization_summaries.py", "complaint_phases/document_optimization.py"),
    ("applications/complaint_workspace_drafting.py", "applications/complaint_workspace.py"),
    ("mediator/intake_question_flow.py", "mediator/mediator.py"),
    ("complaint_phases/denoiser_questions.py", "complaint_phases/denoiser.py"),
    ("mediator/claim_support_diagnostics.py", "mediator/claim_support_hooks.py"),
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


def _raw_targets(text: str) -> list[str]:
    targets = [match.group(1) for match in _INLINE_LINK.finditer(text)]
    targets.extend(match.group(1) for match in _DEFINITION.finditer(text))
    for match in _AUTOLINK.finditer(text):
        candidate = match.group(1)
        if "://" in candidate or "@" in candidate:
            continue
        if "/" in candidate or candidate.endswith((".md", ".py", ".json", ".yml")):
            targets.append(candidate)
    return targets


def test_root_markdown_is_only_the_five_keepers() -> None:
    found = {path.name for path in REPO_ROOT.glob("*.md") if path.is_file()}
    assert found == KEEPER_MARKDOWN


def test_root_docs_name_the_moved_tree() -> None:
    for name in ROOT_DOCS:
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        for phrase in REQUIRED_PHRASES:
            assert phrase in text, f"{name} does not name {phrase}"
        assert "docs/architecture/consolidation_modules.md" in text, name


def test_root_doc_links_resolve_and_are_not_bare_archive_names() -> None:
    problems = []
    for name in ROOT_DOCS:
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        for raw in _raw_targets(text):
            target = _destination(raw)
            if target is None:
                continue
            leaf = Path(target).name
            if target == leaf and leaf in BARE_ARCHIVED_NAMES:
                problems.append(f"{name} links bare archived name {target}")
                continue
            candidate = ((REPO_ROOT / name).parent / target).resolve()
            if not candidate.exists():
                problems.append(f"{name} missing {target}")
    assert problems == []


def test_consolidation_modules_names_every_extracted_sibling() -> None:
    document = REPO_ROOT / "docs" / "architecture" / "consolidation_modules.md"
    text = document.read_text(encoding="utf-8")
    assert document.is_file()
    for sibling, owner in EXTRACTED_SIBLINGS:
        assert sibling in text, sibling
        assert owner in text, owner
        assert (REPO_ROOT / sibling).is_file(), sibling
        assert (REPO_ROOT / owner).is_file(), owner
