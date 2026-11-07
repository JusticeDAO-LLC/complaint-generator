"""Versioned public surface for the mike integration.

Importing this module records owner modules and connector symbol names. It
does not import those owners, the root ``mike`` compatibility directory, or
``external.mike``. It does not start a server or read a private workspace
path. Call ``missing_public_symbols`` to confirm each name by parsing owner
source.
"""

from __future__ import annotations

import ast
from pathlib import Path

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
MODULE = "integrations.mike.interface"

OWNER_MODULES = (
    "integrations.mike",
    "integrations.mike.llm_patch",
    "integrations.mike.skills",
)

# Names already defined at import scope in the owner modules above.
# integrations.mike re-exports the connector surface.
# llm_patch: MIKE_LLM_PATCH_VERSION, MIKE_LLM_PATCH_DESCRIPTOR,
#   apply_mike_llm_router_patch, get_router_generate_fn
# skills: SKILLS_DIR, list_skill_ids, load_skill, load_all_skills
PUBLIC_SYMBOLS = (
    "apply_mike_llm_router_patch",
    "MIKE_LLM_PATCH_VERSION",
    "MIKE_LLM_PATCH_DESCRIPTOR",
    "get_router_generate_fn",
    "load_skill",
    "list_skill_ids",
    "load_all_skills",
    "SKILLS_DIR",
)

_PACKAGE = "integrations.mike"
_FORBIDDEN_IMPORT_PREFIXES = (
    "mike",
    "external.mike",
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

    Owner modules are parsed with ``ast``. They are not imported, and neither
    the root ``mike`` package nor ``external.mike`` is imported.
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
    if not path.is_file() and relative.endswith(".py"):
        package_init = path.with_suffix("") / "__init__.py"
        if package_init.is_file():
            path = package_init
    if not path.is_file():
        raise InterfaceOwnershipError(f"owner module source was not found: {module_name}")
    return path


def interface_import_tree() -> ast.Module:
    """Parse this module's own source. Does not execute owner modules."""
    path = Path(__file__).resolve()
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def forbidden_import_names(tree: ast.AST | None = None) -> tuple[str, ...]:
    """Import targets this facade must not load, including the root mike tree."""
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
