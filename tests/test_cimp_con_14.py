"""CIMP-CON-14: hook runtime and workflow service import through mediator.interface."""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CALLERS = (
    "mediator/hook_runtime.py",
    "mediator/workflow_service.py",
)

REPLACED_NAMES = (
    "Mediator",
    "ClaimSupportHook",
    "apply_qualified_claim_support",
)

FORBIDDEN_MODULES = (
    "mediator.mediator",
    "mediator.claim_support_hooks",
)


def _import_from_modules(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, ()))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = tuple(alias.name for alias in node.names)
            found.append((module, names))
    return found


def test_callers_do_not_import_owner_modules() -> None:
    for relative in CALLERS:
        path = REPO_ROOT / relative
        imports = _import_from_modules(path)
        for module, _names in imports:
            assert module not in FORBIDDEN_MODULES, relative
            assert not any(module.startswith(prefix + ".") for prefix in FORBIDDEN_MODULES), relative


def test_replacement_imports_come_from_interface() -> None:
    seen: set[str] = set()
    for relative in CALLERS:
        path = REPO_ROOT / relative
        for module, names in _import_from_modules(path):
            for name in names:
                if name in REPLACED_NAMES:
                    assert module == "mediator.interface", (relative, name)
                    seen.add(name)
    assert seen == set(REPLACED_NAMES)


def test_one_exported_name_is_the_owner_attribute() -> None:
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
        assert "mediator.claim_support_hooks" not in sys.modules
        from mediator.interface import Mediator
        import mediator.mediator as owner

        assert Mediator is owner.Mediator
        assert interface.Mediator is owner.Mediator
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
