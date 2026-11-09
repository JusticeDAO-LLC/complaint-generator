"""Versioned public surface for the applications package.

Importing this module records owner modules and symbol names. It does not
import those owners, start a server, or read a private workspace path.
Public symbols are lazy exports: the first access of each name loads that
attribute from its owner module. Call ``missing_public_symbols`` to confirm
each catalogued name by parsing owner source.

Public route symbols live on ``applications.server`` and
``applications.case_routes``. Workspace entry symbols live on
``applications.launcher``. ``applications.complaint_workspace`` is not an
owner and is not imported.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
MODULE = "applications.interface"

OWNER_MODULES = (
    "applications.server",
    "applications.case_routes",
    "applications.launcher",
)

# Names already defined at import scope in the owner modules above.
# server: SERVER
# case_routes: CASE_ROUTE_KINDS, compose_case_routes
# launcher: launch_application, start_configured_applications, create_uvicorn_app_for_type
PUBLIC_SYMBOLS = (
    "SERVER",
    "CASE_ROUTE_KINDS",
    "compose_case_routes",
    "launch_application",
    "start_configured_applications",
    "create_uvicorn_app_for_type",
)

_PACKAGE = "applications"
_FORBIDDEN_IMPORT_PREFIXES = (
    "mediator.mediator",
    "applications.complaint_workspace",
    "document_pipeline",
)


class InterfaceOwnershipError(ValueError):
    """A declared public symbol is not defined in the declared owner modules."""


def missing_public_symbols(
    symbols: tuple[str, ...] | list[str] | None = None,
    owners: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, ...]:
    """Return declared symbols that no owner module defines.

    Owner modules are parsed with ``ast``. They are not imported.
    """
    selected = tuple(PUBLIC_SYMBOLS if symbols is None else symbols)
    owner_names = tuple(OWNER_MODULES if owners is None else owners)
    defined: set[str] = set()
    for owner in owner_names:
        defined.update(defined_names(owner))
    return tuple(symbol for symbol in selected if symbol not in defined)


def require_public_symbols(
    symbols: tuple[str, ...] | list[str] | None = None,
    owners: tuple[str, ...] | list[str] | None = None,
) -> None:
    """Raise when any symbol is absent from the declared owner modules."""
    missing = missing_public_symbols(symbols, owners)
    if missing:
        joined = ", ".join(missing)
        raise InterfaceOwnershipError(
            f"public symbol not defined in an owner module: {joined}"
        )


def defined_names(module_name: str) -> set[str]:
    """Names bound while ``module_name`` would be imported, from its syntax tree."""
    source = owner_source_path(module_name).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=module_name)
    names: set[str] = set()
    for node in _import_time_statements(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(_assigned_names(target))
        elif isinstance(node, ast.AnnAssign):
            names.update(_assigned_names(node.target))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    continue
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def owner_source_path(module_name: str) -> Path:
    """Locate an owner module beside this file without importing it."""
    if module_name == _PACKAGE:
        relative = "__init__.py"
    elif module_name.startswith(_PACKAGE + "."):
        relative = module_name[len(_PACKAGE) + 1 :].replace(".", "/") + ".py"
    else:
        raise InterfaceOwnershipError(
            f"owner module must be inside {_PACKAGE}: {module_name}"
        )
    path = Path(__file__).resolve().parent.joinpath(*Path(relative).parts)
    if not path.is_file():
        raise InterfaceOwnershipError(f"owner module source was not found: {module_name}")
    return path


def interface_import_tree() -> ast.Module:
    """Parse this module's own source. Does not execute owner modules."""
    path = Path(__file__).resolve()
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def forbidden_import_names(tree: ast.AST | None = None) -> tuple[str, ...]:
    """Import targets this facade must not load, including server entry modules."""
    parsed = interface_import_tree() if tree is None else tree
    found: list[str] = []
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_module(alias.name):
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if _is_forbidden_module(base):
                found.append(base)
    return tuple(found)


def _is_forbidden_module(module_name: str) -> bool:
    if module_name in _FORBIDDEN_IMPORT_PREFIXES:
        return True
    return any(module_name.startswith(prefix + ".") for prefix in _FORBIDDEN_IMPORT_PREFIXES)


def _import_time_statements(body: list[ast.stmt]) -> list[ast.stmt]:
    statements: list[ast.stmt] = []
    for node in body:
        if _is_main_guard(node):
            continue
        statements.append(node)
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            statements.extend(_import_time_statements(node.body))
            statements.extend(_import_time_statements(node.orelse))
        elif isinstance(node, ast.Try):
            statements.extend(_import_time_statements(node.body))
            for handler in node.handlers:
                statements.extend(_import_time_statements(handler.body))
            statements.extend(_import_time_statements(node.orelse))
            statements.extend(_import_time_statements(node.finalbody))
    return statements


# Loaded only when the attribute is accessed. Importing this module does not
# import applications.complaint_workspace, mediator.mediator, or document_pipeline.
_LAZY_EXPORTS = {
    "SERVER": ("applications.server", "SERVER"),
    "CASE_ROUTE_KINDS": ("applications.case_routes", "CASE_ROUTE_KINDS"),
    "compose_case_routes": ("applications.case_routes", "compose_case_routes"),
    "launch_application": ("applications.launcher", "launch_application"),
    "start_configured_applications": (
        "applications.launcher",
        "start_configured_applications",
    ),
    "create_uvicorn_app_for_type": (
        "applications.launcher",
        "create_uvicorn_app_for_type",
    ),
}


def __getattr__(name: str):
    """Load a facade name from its owner module on first access."""
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


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and isinstance(right, ast.Constant)
        and right.value == "__main__"
    )


def _assigned_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for elt in target.elts:
            names.update(_assigned_names(elt))
        return names
    return set()
