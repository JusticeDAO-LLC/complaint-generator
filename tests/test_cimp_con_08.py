"""CIMP-CON-08: intake status and workflow guidance live under complaint_phases."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INTAKE_BODY = ROOT / "complaint_phases" / "intake_status.py"
INTAKE_SHIM = ROOT / "intake_status.py"
WORKFLOW_BODY = ROOT / "complaint_phases" / "workflow_phase_guidance.py"
WORKFLOW_SHIM = ROOT / "workflow_phase_guidance.py"


def _function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]


def _assert_reexport_shim(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 30
    tree = ast.parse(text, filename=str(path))
    assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree)
    )


def test_intake_status_body_defines_summary_builder() -> None:
    text = INTAKE_BODY.read_text(encoding="utf-8")
    assert len(text.splitlines()) >= 1600
    assert "build_intake_status_summary" in _function_names(INTAKE_BODY)


def test_workflow_phase_guidance_body_defines_plan_builder() -> None:
    text = WORKFLOW_BODY.read_text(encoding="utf-8")
    assert len(text.splitlines()) >= 500
    assert "build_workflow_phase_plan" in _function_names(WORKFLOW_BODY)


def test_root_intake_status_and_workflow_guidance_are_reexport_shims() -> None:
    _assert_reexport_shim(INTAKE_SHIM)
    _assert_reexport_shim(WORKFLOW_SHIM)


def test_root_imports_reach_relocated_builders() -> None:
    import intake_status
    import workflow_phase_guidance
    from intake_status import build_intake_status_summary
    from workflow_phase_guidance import build_workflow_phase_plan

    assert build_intake_status_summary is intake_status.build_intake_status_summary
    assert build_intake_status_summary.__module__ == "complaint_phases.intake_status"
    assert build_workflow_phase_plan is workflow_phase_guidance.build_workflow_phase_plan
    assert build_workflow_phase_plan.__module__ == "complaint_phases.workflow_phase_guidance"
