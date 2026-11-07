"""Check one module against the versioned module-interface contract.

Usage: python scripts/check_module_interface.py <module_name>

The checker reads docs/architecture/module_interface_schema.json, parses the
requested module, and exits nonzero with a specific reason when the contract
fails. Owner modules are parsed and are not imported. A server-starting import
is rejected from the syntax tree before the interface module is executed.
"""

from __future__ import annotations

import ast
import argparse
import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs" / "architecture" / "module_interface_schema.json"
SCHEMA_ID = "complaint-generator/module-interface-schema@1"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
FACADE_ONLY = "facade-only"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

SERVER_CALLS = frozenset(
    {
        "HTTPServer",
        "ThreadingHTTPServer",
        "TCPServer",
        "ThreadingTCPServer",
        "ForkingTCPServer",
        "UDPServer",
        "ThreadingUDPServer",
        "ForkingUDPServer",
        "make_server",
        "serve_forever",
    }
)

MISSING_VERSION = "missing version"
SERVER_IMPORT = "server-starting import"
EMPTY_SURFACE = "empty public surface requires STATUS facade-only"


class InterfaceCheckError(Exception):
    """The requested module cannot be read as a source file."""


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != SCHEMA_ID:
        raise InterfaceCheckError(
            f"schema document must be {SCHEMA_ID}"
        )
    if document.get("interface_schema") != INTERFACE_SCHEMA:
        raise InterfaceCheckError(
            f"schema document must describe INTERFACE_SCHEMA {INTERFACE_SCHEMA}"
        )
    required = document.get("required")
    expected = ["schema", "module", "version", "owner_modules", "public_symbols"]
    if list(required) != expected:
        raise InterfaceCheckError(
            "schema document must require schema, module, version, owner_modules, and public_symbols"
        )
    pattern = document.get("properties", {}).get("version", {}).get("pattern")
    if not isinstance(pattern, str) or re.fullmatch(pattern, "1.0.0") is None:
        raise InterfaceCheckError("schema version pattern must accept a major.minor.patch string")
    if re.fullmatch(pattern, "1.0") is not None:
        raise InterfaceCheckError("schema version pattern must reject a partial version")
    return document


def check_module(module_name: str, schema: Mapping[str, object] | None = None) -> list[str]:
    """Return contract failures for module_name. An empty list means the module conforms."""
    if schema is None:
        schema = load_schema()
    version_pattern = re.compile(schema["properties"]["version"]["pattern"])  # type: ignore[index]
    reasons: list[str] = []
    try:
        source, origin = _read_module_source(module_name)
        tree = ast.parse(source, filename=origin)
    except InterfaceCheckError as exc:
        return [str(exc)]
    except SyntaxError as exc:
        return [f"syntax error: {exc.msg}"]

    constants = _module_constants(tree)
    reasons.extend(_contract_reasons(module_name, constants, version_pattern))

    server_import = _server_starting_import(module_name, tree)
    if server_import is not None:
        reasons.append(server_import)
        return _unique(reasons)

    imported = _import_executed_module(module_name)
    if imported is not None:
        reasons.append(imported)
        return _unique(reasons)

    runtime = sys.modules.get(module_name)
    if runtime is not None:
        reasons.extend(_runtime_reasons(module_name, runtime, constants))
    reasons.extend(_symbol_reasons(constants))
    return _unique(reasons)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a module against complaint-generator/module-interface@1."
    )
    parser.add_argument("module", help="Importable module name to check")
    args = parser.parse_args(argv)
    try:
        reasons = check_module(args.module)
    except (OSError, json.JSONDecodeError, InterfaceCheckError) as exc:
        print(f"module-interface check failed: {exc}", file=sys.stderr)
        return 1
    if reasons:
        for reason in reasons:
            print(f"module-interface check failed: {reason}", file=sys.stderr)
        return 1
    print(f"module-interface ok: {args.module}")
    return 0


def _contract_reasons(
    module_name: str,
    constants: Mapping[str, object],
    version_pattern: re.Pattern[str],
) -> list[str]:
    reasons: list[str] = []
    schema_value = constants.get("INTERFACE_SCHEMA", _MISSING)
    if schema_value is _MISSING:
        reasons.append("missing schema")
    elif schema_value != INTERFACE_SCHEMA:
        reasons.append(f"schema must be {INTERFACE_SCHEMA}")

    version = constants.get("INTERFACE_VERSION", _MISSING)
    if version is _MISSING or version is None or version == "":
        reasons.append(MISSING_VERSION)
    elif not isinstance(version, str) or version_pattern.fullmatch(version) is None:
        reasons.append("version must be a major.minor.patch string")

    if "OWNER_MODULES" not in constants:
        reasons.append("missing owner_modules")
        owners: object = ()
    else:
        owners = constants["OWNER_MODULES"]
        if not _is_string_sequence(owners):
            reasons.append("owner_modules must be a list of module names")
            owners = ()

    if "PUBLIC_SYMBOLS" not in constants:
        reasons.append("missing public_symbols")
        symbols: object = None
    else:
        symbols = constants["PUBLIC_SYMBOLS"]
        if not _is_string_sequence(symbols):
            reasons.append("public_symbols must be a list of symbol names")
            symbols = None

    status = constants.get("STATUS", _MISSING)
    if symbols == () or symbols == []:
        if status != FACADE_ONLY:
            reasons.append(EMPTY_SURFACE)
    elif status not in (_MISSING, FACADE_ONLY) and "PUBLIC_SYMBOLS" in constants:
        reasons.append(f"STATUS must be {FACADE_ONLY} when it is set")

    module_constant = constants.get("MODULE", _MISSING)
    if module_constant is not _MISSING and module_constant != module_name:
        reasons.append(f"module must be {module_name}")
    return reasons


def _runtime_reasons(module_name: str, runtime: object, constants: Mapping[str, object]) -> list[str]:
    reasons: list[str] = []
    actual_name = getattr(runtime, "__name__", None)
    if actual_name != module_name:
        reasons.append(f"module must be {module_name}")
    for attribute, key in (
        ("INTERFACE_SCHEMA", "INTERFACE_SCHEMA"),
        ("INTERFACE_VERSION", "INTERFACE_VERSION"),
        ("OWNER_MODULES", "OWNER_MODULES"),
        ("PUBLIC_SYMBOLS", "PUBLIC_SYMBOLS"),
        ("STATUS", "STATUS"),
    ):
        if key not in constants:
            continue
        if getattr(runtime, attribute, _MISSING) != constants[key]:
            reasons.append(f"{attribute} changed while the module was imported")
    return reasons


def _symbol_reasons(constants: Mapping[str, object]) -> list[str]:
    symbols = constants.get("PUBLIC_SYMBOLS", _MISSING)
    owners = constants.get("OWNER_MODULES", _MISSING)
    if not _is_string_sequence(symbols) or not _is_string_sequence(owners):
        return []
    if len(symbols) == 0:
        return []
    defined: dict[str, set[str]] = {}
    reasons: list[str] = []
    for owner in owners:
        try:
            defined[owner] = _defined_names(owner)
        except InterfaceCheckError as exc:
            reasons.append(str(exc))
    if reasons:
        return reasons
    available = set().union(*defined.values()) if defined else set()
    for symbol in symbols:
        if symbol not in available:
            reasons.append(f"public symbol '{symbol}' is not defined in an owner module")
    return reasons


def _defined_names(module_name: str) -> set[str]:
    source, origin = _read_module_source(module_name)
    try:
        tree = ast.parse(source, filename=origin)
    except SyntaxError as exc:
        raise InterfaceCheckError(f"owner module '{module_name}' syntax error: {exc.msg}") from exc
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


def _server_starting_import(module_name: str, tree: ast.AST) -> str | None:
    if _starts_server(tree):
        return f"{SERVER_IMPORT}: {module_name}"
    for imported in _imported_module_names(tree, _package_name(module_name)):
        if _import_starts_server(imported, seen=set()):
            return f"{SERVER_IMPORT}: {imported}"
    return None


def _import_starts_server(module_name: str, seen: set[str]) -> bool:
    if module_name in seen:
        return False
    seen.add(module_name)
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError):
        return False
    if spec is None or not spec.origin or spec.origin in {"built-in", "frozen"}:
        return False
    origin = Path(spec.origin)
    if not origin.is_file() or _is_stdlib(origin):
        return False
    try:
        source = origin.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(origin))
    except (OSError, SyntaxError, UnicodeError):
        return False
    if _starts_server(tree):
        return True
    package = spec.name.rpartition(".")[0] if spec.name else _package_name(module_name)
    for imported in _imported_module_names(tree, package):
        if _import_starts_server(imported, seen):
            return True
    return False


def _starts_server(tree: ast.AST) -> bool:
    for node in _import_time_statements(getattr(tree, "body", [])):
        if isinstance(node, ast.Call) and _call_name(node) in SERVER_CALLS:
            return True
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and _call_name(child) in SERVER_CALLS:
                if not _nested_in_function(node, child):
                    return True
    return False


def _nested_in_function(statement: ast.AST, target: ast.AST) -> bool:
    """True when target sits inside a function or class defined by statement."""
    for child in ast.walk(statement):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            for inner in ast.walk(child):
                if inner is target and inner is not child:
                    return True
    return False


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _import_time_statements(body: Iterable[ast.stmt]) -> Iterable[ast.stmt]:
    for node in body:
        if _is_main_guard(node):
            continue
        yield node
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            yield from _import_time_statements(node.body)
            yield from _import_time_statements(node.orelse)
        elif isinstance(node, ast.Try):
            yield from _import_time_statements(node.body)
            for handler in node.handlers:
                yield from _import_time_statements(handler.body)
            yield from _import_time_statements(node.orelse)
            yield from _import_time_statements(node.finalbody)


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    return _is_name(left, "__name__") and _is_const(right, "__main__") or _is_const(left, "__main__") and _is_name(right, "__name__")


def _imported_module_names(tree: ast.AST, package: str) -> list[str]:
    names: list[str] = []
    for node in _import_time_statements(getattr(tree, "body", [])):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_import_from(node, package)
            if base:
                names.append(base)
    return names


def _resolve_import_from(node: ast.ImportFrom, package: str) -> str | None:
    if node.level:
        parts = package.split(".") if package else []
        keep = max(len(parts) - (node.level - 1), 0) if node.level else len(parts)
        # level 1 stays in package; level 2 climbs one parent.
        climb = node.level - 1
        if climb > len(parts):
            return None
        prefix = parts[: len(parts) - climb]
        if node.module:
            prefix.append(node.module)
        return ".".join(prefix) if prefix else None
    return node.module


def _module_constants(tree: ast.AST) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in _import_time_statements(getattr(tree, "body", [])):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        try:
            literal = _literal(value)
        except ValueError:
            literal = _UNPARSEABLE
        for target in targets:
            for name in _assigned_names(target):
                values[name] = literal
    return values


def _literal(node: ast.expr | None) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        values = [_literal(elt) for elt in node.elts]
        return values if isinstance(node, ast.List) else tuple(values)
    raise ValueError("not a literal")


def _assigned_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for elt in target.elts:
            names.extend(_assigned_names(elt))
        return names
    return []


def _read_module_source(module_name: str) -> tuple[str, str]:
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError) as exc:
        raise InterfaceCheckError(f"module not found: {module_name}") from exc
    if spec is None or not spec.origin or spec.origin in {"built-in", "frozen"}:
        raise InterfaceCheckError(f"module not found: {module_name}")
    origin = Path(spec.origin)
    if not origin.is_file():
        raise InterfaceCheckError(f"module not found: {module_name}")
    try:
        return origin.read_text(encoding="utf-8"), str(origin)
    except OSError as exc:
        raise InterfaceCheckError(f"module not found: {module_name}") from exc


def _import_executed_module(module_name: str) -> str | None:
    sys.modules.pop(module_name, None)
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        return f"import failed: {type(exc).__name__}: {exc}"
    return None


def _package_name(module_name: str) -> str:
    return module_name.rpartition(".")[0]


def _is_stdlib(origin: Path) -> bool:
    stdlib = Path(sys.prefix).resolve()
    try:
        origin.resolve().relative_to(stdlib)
    except ValueError:
        return False
    return True


def _is_string_sequence(value: object) -> bool:
    return isinstance(value, (list, tuple)) and all(isinstance(item, str) and item for item in value)


def _is_name(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_const(node: ast.expr, value: object) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def _unique(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            ordered.append(reason)
    return ordered


class _Missing:
    def __repr__(self) -> str:
        return "<missing>"


class _Unparseable:
    def __repr__(self) -> str:
        return "<unparseable>"


_MISSING = _Missing()
_UNPARSEABLE = _Unparseable()


if __name__ == "__main__":
    raise SystemExit(main())
