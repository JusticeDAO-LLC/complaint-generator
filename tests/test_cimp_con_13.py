"""CIMP-CON-13: Mediator is a lazy export of mediator.interface."""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CALLERS = (
    "main.py",
    "examples/three_phase_example.py",
    "examples/adversarial_harness_example.py",
    "scripts/run_hacc_adversarial_report.py",
    "scripts/run_hacc_preset_matrix.py",
)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_callers_import_mediator_from_interface() -> None:
    for relative in CALLERS:
        path = REPO_ROOT / relative
        imported = _imported_modules(path)
        assert "mediator.interface" in imported, relative
        assert "mediator.mediator" not in imported, relative
        assert not any(name.startswith("mediator.mediator.") for name in imported), relative


def test_mediator_is_lazy_export_of_owner_class() -> None:
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
        package_name = "mediator"
        module_name = "mediator.interface"
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

        assert "mediator.mediator" not in sys.modules
        from mediator.interface import Mediator
        import mediator.mediator as owner

        assert Mediator is owner.Mediator
        assert interface.Mediator is owner.Mediator
        try:
            interface.missing_attribute_for_cimp_con_13
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
