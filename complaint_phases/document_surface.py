"""Versioned public surface for document, intake, and workflow-phase entry points.

Importing this module records symbol names. It does not import the owner
modules, start a pipeline, start a server, or read a private workspace path.
Each public name is a lazy export: the first access loads that attribute from
its ``complaint_phases`` owner.
"""

from __future__ import annotations

import importlib

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
MODULE = "complaint_phases.document_surface"

# Loaded only when the attribute is accessed. Importing this module does not
# import complaint_phases.document_pipeline, complaint_phases.intake_status,
# or complaint_phases.workflow_phase_guidance.
_LAZY_EXPORTS = {
    "DEFAULT_OUTPUT_DIR": ("complaint_phases.document_pipeline", "DEFAULT_OUTPUT_DIR"),
    "_build_claim_checklist_chip_labels": (
        "complaint_phases.document_pipeline",
        "_build_claim_checklist_chip_labels",
    ),
    "build_intake_case_review_summary": (
        "complaint_phases.intake_status",
        "build_intake_case_review_summary",
    ),
    "build_intake_status_summary": (
        "complaint_phases.intake_status",
        "build_intake_status_summary",
    ),
    "build_intake_warning_entries": (
        "complaint_phases.intake_status",
        "build_intake_warning_entries",
    ),
    "build_workflow_phase_plan": (
        "complaint_phases.workflow_phase_guidance",
        "build_workflow_phase_plan",
    ),
    "humanize_workflow_priority_label": (
        "complaint_phases.workflow_phase_guidance",
        "humanize_workflow_priority_label",
    ),
    "normalize_workflow_phase_recommended_actions": (
        "complaint_phases.workflow_phase_guidance",
        "normalize_workflow_phase_recommended_actions",
    ),
    "resolve_prioritized_workflow_phase": (
        "complaint_phases.workflow_phase_guidance",
        "resolve_prioritized_workflow_phase",
    ),
}


def __getattr__(name: str):
    """Load a facade name from its complaint_phases owner on first access."""
    spec = _LAZY_EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = spec
    owner = importlib.import_module(module_name)
    value = getattr(owner, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
