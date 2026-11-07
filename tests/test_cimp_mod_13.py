"""Ownership record for CLI entry points (CIMP-MOD-13).

Public callables are read with ast. The CLI modules are not imported, so the
tests do not start a server or read private workspace state.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = REPO_ROOT / "complaint_generator" / "entrypoint_ownership.json"
SCHEMA = "complaint-generator/entrypoint-ownership@1"
INTERFACE_VERSION = "1.0.0"
OWNER = "complaint_generator.entrypoints"

MODULE_PATHS = {
    "complaint_generator.entrypoints": "complaint_generator/entrypoints.py",
    "applications.cli": "applications/cli.py",
    "applications.complaint_cli": "applications/complaint_cli.py",
    "complaint_generator.cli": "complaint_generator/cli.py",
}
CALLER_MODULES = (
    "applications.cli",
    "applications.complaint_cli",
    "complaint_generator.cli",
)


class EntrypointOwnershipError(AssertionError):
    """The ownership record does not match the CLI sources."""


def function_signature(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise TypeError(f"not a function: {type(node).__name__}")
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    rendered = f"{prefix} {node.name}({ast.unparse(node.args)})"
    if node.returns is not None:
        rendered += " -> " + ast.unparse(node.returns)
    return rendered


def public_functions(path: Path) -> dict[str, str]:
    """Module-level public functions keyed by name, valued by AST signature."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            found[node.name] = function_signature(node)
    return found


def imported_public_aliases(path: Path) -> dict[str, dict[str, str]]:
    """Public import aliases, including names re-exported in ``__all__``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    exported: set[str] | None = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    exported = {
                        element.value
                        for element in node.value.elts
                        if isinstance(element, ast.Constant) and isinstance(element.value, str)
                    }
    aliases: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        for alias in node.names:
            public_name = alias.asname or alias.name
            if public_name.startswith("_"):
                continue
            if exported is not None and public_name not in exported:
                continue
            aliases[public_name] = {"module": node.module, "name": alias.name}
    return aliases


def load_record() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def _definitions_by_name(record: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in record.get("callables", []):
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise EntrypointOwnershipError("callable entry is missing a name")
        definitions = entry.get("definitions")
        if not isinstance(definitions, list) or not definitions:
            raise EntrypointOwnershipError(f"{name} has no definitions")
        grouped[name] = definitions
    return grouped


def validate_record(record: dict, root: Path = REPO_ROOT) -> None:
    """Fail when a recorded callable is missing or a signature was rewritten."""
    if record.get("schema") != SCHEMA:
        raise EntrypointOwnershipError(f"schema must be {SCHEMA}")
    if record.get("interface_version") != INTERFACE_VERSION:
        raise EntrypointOwnershipError("interface_version must be 1.0.0")
    if record.get("owner") != OWNER:
        raise EntrypointOwnershipError(f"owner must be {OWNER}")
    if record.get("merge_performed") is not False:
        raise EntrypointOwnershipError("divergent CLI bodies must stay unmerged")

    modules = record.get("modules")
    if not isinstance(modules, list):
        raise EntrypointOwnershipError("modules must be a list")
    roles = {}
    for item in modules:
        module = item.get("module")
        role = item.get("role")
        path = item.get("path")
        if module not in MODULE_PATHS:
            raise EntrypointOwnershipError(f"unexpected module {module}")
        if path != MODULE_PATHS[module]:
            raise EntrypointOwnershipError(f"{module} path does not match the source tree")
        if not (root / path).is_file():
            raise EntrypointOwnershipError(f"missing source for {module}")
        roles[module] = role
    if roles.get(OWNER) != "owner":
        raise EntrypointOwnershipError("complaint_generator.entrypoints must be the owner")
    for module in CALLER_MODULES:
        if roles.get(module) not in {"caller", "duplicate"}:
            raise EntrypointOwnershipError(f"{module} must be a caller or duplicate")

    functions = {module: public_functions(root / rel) for module, rel in MODULE_PATHS.items()}
    aliases = {module: imported_public_aliases(root / rel) for module, rel in MODULE_PATHS.items()}
    grouped = _definitions_by_name(record)

    shared: dict[str, set[str]] = {}
    for module, found in functions.items():
        for name in found:
            shared.setdefault(name, set()).add(module)
    for name, present in shared.items():
        if len(present) < 2:
            continue
        if name not in grouped:
            raise EntrypointOwnershipError(f"shared callable {name} is not recorded")

    for name, definitions in grouped.items():
        entry = next(item for item in record["callables"] if item["name"] == name)
        signatures = []
        seen_modules = set()
        for definition in definitions:
            module = definition.get("module")
            recorded_name = definition.get("name", name)
            if module not in MODULE_PATHS:
                raise EntrypointOwnershipError(f"{name} names unknown module {module}")
            if recorded_name != name:
                raise EntrypointOwnershipError(f"{module} records {recorded_name} under {name}")
            seen_modules.add(module)
            kind = definition.get("kind", "function")
            if kind == "function":
                live = functions[module].get(name)
                if live is None:
                    raise EntrypointOwnershipError(f"recorded callable {module}.{name} is absent")
                if definition.get("signature") != live:
                    raise EntrypointOwnershipError(
                        f"signature drift for {module}.{name}: record {definition.get('signature')!r} source {live!r}"
                    )
                signatures.append(live)
            elif kind == "imported_alias":
                live_alias = aliases[module].get(name)
                if live_alias is None:
                    raise EntrypointOwnershipError(f"recorded alias {module}.{name} is absent")
                if definition.get("import_module") != live_alias["module"] or definition.get("import_name") != live_alias["name"]:
                    raise EntrypointOwnershipError(f"alias target drift for {module}.{name}")
            else:
                raise EntrypointOwnershipError(f"unknown callable kind {kind}")
        merged = bool(entry.get("merged"))
        status = entry.get("status")
        if merged:
            owner_sig = functions[OWNER].get(name)
            if owner_sig is None or any(item != owner_sig for item in signatures):
                raise EntrypointOwnershipError(f"{name} is marked merged but signatures do not match the owner")
        if len(signatures) >= 2 and len(set(signatures)) > 1:
            if status != "divergent" or merged:
                raise EntrypointOwnershipError(f"{name} has divergent signatures and must stay unmerged")
        if status == "divergent" and merged:
            raise EntrypointOwnershipError(f"{name} is divergent and merged")

    owner_main = functions[OWNER].get("main")
    if owner_main is None:
        raise EntrypointOwnershipError("owner main is absent")
    recorded_owner = [
        definition
        for definition in grouped.get("main", [])
        if definition.get("module") == OWNER
    ]
    if len(recorded_owner) != 1 or recorded_owner[0].get("signature") != owner_main:
        raise EntrypointOwnershipError("owner main signature does not match the source")


def test_record_names_owner_and_cli_callers() -> None:
    record = load_record()
    validate_record(record)
    assert record["schema"] == SCHEMA
    assert record["interface_version"] == INTERFACE_VERSION
    assert record["interface_version"] != "1.0"
    assert record["owner"] == OWNER
    roles = {item["module"]: item["role"] for item in record["modules"]}
    assert roles[OWNER] == "owner"
    for module in CALLER_MODULES:
        assert roles[module] in {"caller", "duplicate"}
    assert record["merge_performed"] is False
    main_entry = next(item for item in record["callables"] if item["name"] == "main")
    assert main_entry["status"] == "divergent"
    assert main_entry["merged"] is False
    by_module = {item["module"]: item["signature"] for item in main_entry["definitions"]}
    assert by_module[OWNER] == "def main() -> int"
    assert by_module["applications.complaint_cli"] == "def main() -> None"
    assert by_module["complaint_generator.cli"] == "def main() -> None"
    assert by_module[OWNER] != by_module["applications.complaint_cli"]
    assert "applications.cli" not in by_module


def test_shared_main_stays_divergent_and_unmerged() -> None:
    functions = {module: public_functions(REPO_ROOT / rel) for module, rel in MODULE_PATHS.items()}
    assert functions[OWNER]["main"] != functions["applications.complaint_cli"]["main"]
    assert functions[OWNER]["main"] != functions["complaint_generator.cli"]["main"]
    assert functions["applications.cli"] == {}
    record = load_record()
    main_entry = next(item for item in record["callables"] if item["name"] == "main")
    assert {item["module"] for item in main_entry["definitions"]} == {
        OWNER,
        "applications.complaint_cli",
        "complaint_generator.cli",
    }
    assert main_entry["merged"] is False
    caller = next(item for item in record["modules"] if item["module"] == "applications.cli")
    assert caller["role"] == "caller"


def test_recorded_callable_must_exist() -> None:
    record = load_record()
    record["callables"] = [
        *record["callables"],
        {
            "name": "not_a_cli_callable",
            "status": "owner_only",
            "merged": False,
            "definitions": [
                {
                    "module": OWNER,
                    "name": "not_a_cli_callable",
                    "kind": "function",
                    "signature": "def not_a_cli_callable() -> None",
                }
            ],
        },
    ]
    with pytest.raises(EntrypointOwnershipError, match="not_a_cli_callable"):
        validate_record(record)


def test_shim_signature_change_fails() -> None:
    record = load_record()
    for entry in record["callables"]:
        if entry["name"] != "main":
            continue
        for definition in entry["definitions"]:
            if definition["module"] == OWNER:
                definition["signature"] = "def main(argv: list[str]) -> int"
    with pytest.raises(EntrypointOwnershipError, match="signature drift"):
        validate_record(record)


def test_divergent_signature_cannot_be_marked_merged() -> None:
    record = load_record()
    record["merge_performed"] = True
    for entry in record["callables"]:
        if entry["name"] == "main":
            entry["merged"] = True
            entry["status"] = "duplicate"
    with pytest.raises(EntrypointOwnershipError, match="unmerged|signatures do not match"):
        validate_record(record)


def test_owner_alias_remains_an_import_without_a_rewritten_body() -> None:
    aliases = imported_public_aliases(REPO_ROOT / MODULE_PATHS[OWNER])
    assert aliases["run_main"] == {"module": "run", "name": "main"}
    record = load_record()
    alias = next(item for item in record["callables"] if item["name"] == "run_main")
    assert alias["merged"] is False
    assert alias["status"] == "owner_only"
    definition = alias["definitions"][0]
    assert definition["kind"] == "imported_alias"
    assert definition["module"] == OWNER
    validate_record(record)
    source = (REPO_ROOT / MODULE_PATHS[OWNER]).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    ]
    assert [(node.module, [(alias.name, alias.asname) for alias in node.names]) for node in imports] == [
        ("run", [("main", "run_main")])
    ]
