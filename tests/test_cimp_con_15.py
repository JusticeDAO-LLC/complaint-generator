"""CIMP-CON-15: CLI and phase manager use lazy complaint_phases.interface exports."""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CALLERS = (
    "applications/complaint_cli.py",
    "complaint_phases/phase_manager.py",
)

INTERFACE_IMPORTS = {
    "applications/complaint_cli.py": {"redact_diagnostic_value"},
    "complaint_phases/phase_manager.py": {
        "project_stopping_policy",
        "format_terminal_why",
    },
}


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


def test_callers_do_not_import_denoiser() -> None:
    for relative in CALLERS:
        path = REPO_ROOT / relative
        imported = _import_from_modules(path)
        modules = [module for module, _names in imported]
        assert "complaint_phases.denoiser" not in modules, relative
        assert not any(name == "complaint_phases.denoiser" or name.startswith("complaint_phases.denoiser.") for name in modules), relative
        interface_names = {
            name
            for module, names in imported
            if module == "complaint_phases.interface"
            for name in names
        }
        assert INTERFACE_IMPORTS[relative] <= interface_names, relative


def test_complaint_denoiser_is_lazy_export_of_owner_class() -> None:
    script = textwrap.dedent(
        """
        import importlib.util
        import pathlib
        import sys
        import types
        from pathlib import Path

        _exists = pathlib.Path.exists

        def _exists_or_missing(self, *, follow_symlinks=True):
            try:
                return _exists(self, follow_symlinks=follow_symlinks)
            except PermissionError:
                return False

        pathlib.Path.exists = _exists_or_missing

        root = Path.cwd()
        package_name = "complaint_phases"
        module_name = "complaint_phases.interface"
        package = types.ModuleType(package_name)
        package.__path__ = [str(root / package_name)]
        package.__package__ = package_name
        sys.modules[package_name] = package
        path = root / package_name / "interface.py"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise SystemExit(f"cannot load {path}")
        interface = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = interface
        spec.loader.exec_module(interface)

        assert "complaint_phases.denoiser" not in sys.modules
        from complaint_phases.interface import ComplaintDenoiser
        import complaint_phases.denoiser as owner

        assert ComplaintDenoiser is owner.ComplaintDenoiser
        assert interface.ComplaintDenoiser is owner.ComplaintDenoiser
        assert interface.project_stopping_policy is owner.project_stopping_policy
        assert interface.publish_authorized_dependency_action is owner.publish_authorized_dependency_action
        assert interface.format_terminal_why is owner.format_terminal_why
        assert interface.redact_diagnostic_value is owner.redact_diagnostic_value
        try:
            interface.missing_attribute_for_cimp_con_15
        except AttributeError:
            pass
        else:
            raise SystemExit("missing attribute did not raise AttributeError")
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
    assert result.returncode == 0, result.stderr
