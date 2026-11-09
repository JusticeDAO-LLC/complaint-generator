"""CIMP-CON-16: document and review callers use versioned lazy surfaces."""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CALLERS = (
    "applications/document_api.py",
    "applications/review_api.py",
    "adversarial_harness/optimizer.py",
)

ROOT_MODULES = (
    "document_pipeline",
    "document_optimization",
    "intake_status",
    "workflow_phase_guidance",
    "claim_support_review",
)

DOCUMENT_SURFACE_IMPORTS = {
    "applications/document_api.py": {
        "DEFAULT_OUTPUT_DIR",
        "_build_claim_checklist_chip_labels",
        "build_intake_case_review_summary",
        "build_intake_status_summary",
        "build_intake_warning_entries",
        "humanize_workflow_priority_label",
        "normalize_workflow_phase_recommended_actions",
        "resolve_prioritized_workflow_phase",
    },
    "adversarial_harness/optimizer.py": {"build_workflow_phase_plan"},
}

REVIEW_SURFACE_IMPORTS = {
    "ClaimSupportDocumentSaveRequest",
    "ClaimSupportFollowUpExecuteRequest",
    "ClaimSupportIntakeSummaryConfirmRequest",
    "ClaimSupportManualReviewResolveRequest",
    "ClaimSupportReparseDocumentRequest",
    "ClaimSupportReviewRequest",
    "ClaimSupportTestimonySaveRequest",
    "build_claim_support_document_payload",
    "build_claim_support_follow_up_execution_payload",
    "build_claim_support_intake_summary_confirmation_payload",
    "build_claim_support_manual_review_resolution_payload",
    "build_claim_support_reparse_document_payload",
    "build_claim_support_review_payload",
    "build_claim_support_testimony_payload",
    "build_claim_support_uploaded_document_payload",
}


def _is_root_module(module: str) -> bool:
    return any(module == name or module.startswith(name + ".") for name in ROOT_MODULES)


def _import_from_modules(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, ()))
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = tuple(alias.name for alias in node.names)
            found.append((node.module, names))
    return found


def test_callers_do_not_import_root_document_or_review_modules() -> None:
    for relative in CALLERS:
        path = REPO_ROOT / relative
        imported = _import_from_modules(path)
        root_hits = [module for module, _names in imported if _is_root_module(module)]
        assert root_hits == [], relative


def test_document_callers_import_document_surface() -> None:
    for relative, expected in DOCUMENT_SURFACE_IMPORTS.items():
        imported = _import_from_modules(REPO_ROOT / relative)
        names = {
            name
            for module, imported_names in imported
            if module == "complaint_phases.document_surface"
            for name in imported_names
        }
        assert expected <= names, relative


def test_review_api_imports_mediator_interface() -> None:
    imported = _import_from_modules(REPO_ROOT / "applications/review_api.py")
    names = {
        name
        for module, imported_names in imported
        if module == "mediator.interface"
        for name in imported_names
    }
    assert REVIEW_SURFACE_IMPORTS <= names


def test_document_surface_version_and_lazy_owner_identity() -> None:
    script = textwrap.dedent(
        """
        import ast
        import pathlib
        import sys
        from pathlib import Path

        _exists = pathlib.Path.exists

        def _exists_or_missing(self, *, follow_symlinks=True):
            try:
                return _exists(self, follow_symlinks=follow_symlinks)
            except PermissionError:
                return False

        pathlib.Path.exists = _exists_or_missing

        root = Path.cwd()
        surface_path = root / "complaint_phases" / "document_surface.py"
        tree = ast.parse(surface_path.read_text(encoding="utf-8"), filename=str(surface_path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert "importlib" in imported
        assert "complaint_phases.document_pipeline" not in imported
        assert "complaint_phases.intake_status" not in imported
        assert "complaint_phases.workflow_phase_guidance" not in imported
        assert "document_pipeline" not in imported
        assert "intake_status" not in imported
        assert "workflow_phase_guidance" not in imported
        versions = [
            node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "INTERFACE_VERSION" for target in node.targets)
            and isinstance(node.value, ast.Constant)
        ]
        schemas = [
            node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "INTERFACE_SCHEMA" for target in node.targets)
            and isinstance(node.value, ast.Constant)
        ]
        assert versions == ["1.0.0"]
        assert schemas == ["complaint-generator/module-interface@1"]

        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import complaint_phases.document_surface as surface

        assert surface.INTERFACE_VERSION == "1.0.0"
        assert surface.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
        assert "complaint_phases.workflow_phase_guidance" not in sys.modules
        assert "complaint_phases.document_pipeline" not in sys.modules
        assert "complaint_phases.intake_status" not in sys.modules

        import complaint_phases.workflow_phase_guidance as owner

        assert surface.build_workflow_phase_plan is owner.build_workflow_phase_plan
        try:
            surface.missing_attribute_for_cimp_con_16
        except AttributeError:
            pass
        else:
            raise SystemExit("missing attribute did not raise AttributeError")

        interface_path = root / "mediator" / "interface.py"
        interface_tree = ast.parse(interface_path.read_text(encoding="utf-8"), filename=str(interface_path))
        interface_imports = []
        for node in ast.walk(interface_tree):
            if isinstance(node, ast.Import):
                interface_imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                interface_imports.append(node.module)
        assert "mediator.claim_support_review" not in interface_imports
        assert "claim_support_review" not in interface_imports
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
