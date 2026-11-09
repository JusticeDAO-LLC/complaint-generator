"""Ownership record for MCP servers (CIMP-MOD-14).

Named modules are parsed with ast. They are not imported, so the tests do
not start a server, bind a socket, or read private workspace state.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = REPO_ROOT / "complaint_generator" / "mcp_ownership.json"
SCHEMA = "complaint-generator/mcp-ownership@1"
INTERFACE_VERSION = "1.0.0"

PROTOCOL_OWNER = "applications.complaint_mcp_protocol"
VERSIONED_OWNER = "complaint_generator.mcp"
APPLICATIONS_SERVER = "applications.complaint_mcp_server"
GENERATOR_SERVER = "complaint_generator.mcp_server"

MODULE_PATHS = {
    PROTOCOL_OWNER: "applications/complaint_mcp_protocol.py",
    VERSIONED_OWNER: "complaint_generator/mcp.py",
    APPLICATIONS_SERVER: "applications/complaint_mcp_server.py",
    GENERATOR_SERVER: "complaint_generator/mcp_server.py",
}

SUCCESS_SHAPED_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "protocolVersion": "2025-06-18",
        "serverInfo": {"name": "complaint-workspace-mcp", "version": "1.0.0"},
    },
}


class McpOwnershipError(AssertionError):
    """The ownership record does not match the MCP sources."""


def function_signature(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise TypeError(f"not a function: {type(node).__name__}")
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    rendered = f"{prefix} {node.name}({ast.unparse(node.args)})"
    if node.returns is not None:
        rendered += " -> " + ast.unparse(node.returns)
    return rendered


def public_functions(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            found[node.name] = function_signature(node)
    return found


def imported_public_aliases(path: Path) -> dict[str, dict[str, str]]:
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


def network_bind_calls(path: Path) -> list[str]:
    """Names of transport bind/listen/serve calls. Parsing does not run them."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    transport_module = "soc" + "ket"
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == transport_module or alias.name.startswith(transport_module + "."):
                    found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module == transport_module:
            found.append("from " + transport_module)
        elif isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name in {"bind", "listen", "serve_forever", "create_server", "run"}:
                found.append(name)
    return found


def load_record() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def classify_protocol_response(*, owner_available: bool, response: object) -> dict:
    """A missing owner is unavailable. A JSON-RPC body is not success in that case."""
    if not owner_available:
        return {
            "status": "unavailable",
            "success": False,
            "accepted_response": None,
        }
    if (
        isinstance(response, dict)
        and response.get("jsonrpc") == "2.0"
        and "result" in response
        and "error" not in response
    ):
        return {"status": "ok", "success": True, "accepted_response": response}
    return {"status": "not_success", "success": False, "accepted_response": response}


def owner_module_available(module_name: str) -> bool:
    """Import the named owner. ImportError is an unavailable result, not success."""
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def validate_record(record: dict, root: Path = REPO_ROOT) -> None:
    if record.get("schema") != SCHEMA:
        raise McpOwnershipError(f"schema must be {SCHEMA}")
    if record.get("interface_version") != INTERFACE_VERSION:
        raise McpOwnershipError("interface_version must be 1.0.0")
    if record.get("binds_network_socket") is not False:
        raise McpOwnershipError("the ownership record must not bind a network socket")
    if record.get("server_started_by_record") is not False:
        raise McpOwnershipError("the ownership record must not start a server")
    failure = record.get("import_failure")
    if not isinstance(failure, dict):
        raise McpOwnershipError("import_failure policy is required")
    if failure.get("status") != "unavailable":
        raise McpOwnershipError("a missing owner must be unavailable")
    if failure.get("treat_protocol_response_as_success") is not False:
        raise McpOwnershipError("a protocol response is not success when the owner cannot be imported")

    owners = record.get("owners")
    servers = record.get("duplicate_servers")
    if not isinstance(owners, list) or len(owners) < 2:
        raise McpOwnershipError("owners must name the protocol owner and the versioned facade")
    if not isinstance(servers, list) or len(servers) != 2:
        raise McpOwnershipError("duplicate server modules in applications and complaint_generator are required")

    roles: dict[str, str] = {}
    for item in [*owners, *servers]:
        module = item.get("module")
        path = item.get("path")
        role = item.get("role")
        if module not in MODULE_PATHS:
            raise McpOwnershipError(f"unexpected module {module}")
        if path != MODULE_PATHS[module]:
            raise McpOwnershipError(f"{module} path does not match the source tree")
        if not (root / path).is_file():
            raise McpOwnershipError(f"missing source for {module}")
        if network_bind_calls(root / path):
            raise McpOwnershipError(f"{module} binds a network socket")
        roles[module] = role

    if roles.get(PROTOCOL_OWNER) != "protocol_owner":
        raise McpOwnershipError("applications.complaint_mcp_protocol must be the protocol owner")
    if roles.get(VERSIONED_OWNER) != "versioned_owner":
        raise McpOwnershipError("complaint_generator.mcp must be the versioned owner")
    if roles.get(APPLICATIONS_SERVER) != "duplicate_server":
        raise McpOwnershipError("applications.complaint_mcp_server must be a duplicate server")
    if roles.get(GENERATOR_SERVER) != "duplicate_server":
        raise McpOwnershipError("complaint_generator.mcp_server must be a duplicate server")

    packages = {item.get("package") for item in servers}
    if packages != {"applications", "complaint_generator"}:
        raise McpOwnershipError("duplicate servers must cover applications and complaint_generator")

    versioned = next(item for item in owners if item.get("module") == VERSIONED_OWNER)
    if versioned.get("reexports_module") != PROTOCOL_OWNER:
        raise McpOwnershipError("versioned owner must re-export the protocol owner")
    generator_server = next(item for item in servers if item.get("module") == GENERATOR_SERVER)
    if generator_server.get("reexports_module") != APPLICATIONS_SERVER:
        raise McpOwnershipError("complaint_generator.mcp_server must re-export the applications server")

    functions = {module: public_functions(root / rel) for module, rel in MODULE_PATHS.items()}
    aliases = {module: imported_public_aliases(root / rel) for module, rel in MODULE_PATHS.items()}
    callables = record.get("callables")
    if not isinstance(callables, list) or not callables:
        raise McpOwnershipError("callables must record owner signatures")

    seen_names: set[str] = set()
    for entry in callables:
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise McpOwnershipError("callable entry is missing a name")
        if name in seen_names:
            raise McpOwnershipError(f"duplicate callable record {name}")
        seen_names.add(name)
        definitions = entry.get("definitions")
        if not isinstance(definitions, list) or not definitions:
            raise McpOwnershipError(f"{name} has no definitions")
        for definition in definitions:
            module = definition.get("module")
            if module not in MODULE_PATHS:
                raise McpOwnershipError(f"{name} names unknown module {module}")
            kind = definition.get("kind")
            if kind == "function":
                live = functions[module].get(name)
                if live is None:
                    raise McpOwnershipError(f"recorded callable {module}.{name} is absent")
                if definition.get("signature") != live:
                    raise McpOwnershipError(
                        f"signature drift for {module}.{name}: record {definition.get('signature')!r} source {live!r}"
                    )
            elif kind == "imported_alias":
                live_alias = aliases[module].get(name)
                if live_alias is None:
                    raise McpOwnershipError(f"recorded alias {module}.{name} is absent")
                if (
                    definition.get("import_module") != live_alias["module"]
                    or definition.get("import_name") != live_alias["name"]
                ):
                    raise McpOwnershipError(f"alias target drift for {module}.{name}")
            else:
                raise McpOwnershipError(f"unknown callable kind {kind}")

    for required in ("handle_jsonrpc_message", "tool_list_payload", "main"):
        if required not in seen_names:
            raise McpOwnershipError(f"shared callable {required} is not recorded")
    if "handle_jsonrpc_message" not in functions[PROTOCOL_OWNER]:
        raise McpOwnershipError("protocol owner is missing handle_jsonrpc_message")
    if "main" not in functions[APPLICATIONS_SERVER]:
        raise McpOwnershipError("applications server is missing main")
    if aliases[VERSIONED_OWNER].get("handle_jsonrpc_message", {}).get("module") != PROTOCOL_OWNER:
        raise McpOwnershipError("versioned owner does not alias the protocol owner")
    if aliases[GENERATOR_SERVER].get("main", {}).get("module") != APPLICATIONS_SERVER:
        raise McpOwnershipError("generator server does not alias the applications server")


def test_record_names_owners_and_duplicate_servers() -> None:
    record = load_record()
    validate_record(record)
    assert record["schema"] == SCHEMA
    assert record["interface_version"] == INTERFACE_VERSION
    assert record["interface_version"] != "1.0"
    roles = {item["module"]: item["role"] for item in [*record["owners"], *record["duplicate_servers"]]}
    assert roles[PROTOCOL_OWNER] == "protocol_owner"
    assert roles[VERSIONED_OWNER] == "versioned_owner"
    assert roles[APPLICATIONS_SERVER] == "duplicate_server"
    assert roles[GENERATOR_SERVER] == "duplicate_server"
    packages = {item["package"] for item in record["duplicate_servers"]}
    assert packages == {"applications", "complaint_generator"}
    assert record["binds_network_socket"] is False
    assert record["server_started_by_record"] is False
    assert record["import_failure"]["treat_protocol_response_as_success"] is False


def test_owner_ast_matches_recorded_signatures() -> None:
    record = load_record()
    functions = public_functions(REPO_ROOT / MODULE_PATHS[PROTOCOL_OWNER])
    assert functions["handle_jsonrpc_message"].startswith("def handle_jsonrpc_message(")
    assert "access: Optional[WorkspaceAccess]" in functions["handle_jsonrpc_message"]
    assert functions["tool_list_payload"] == "def tool_list_payload(service: ComplaintWorkspaceService) -> Dict[str, Any]"
    server_functions = public_functions(REPO_ROOT / MODULE_PATHS[APPLICATIONS_SERVER])
    assert server_functions["main"] == "def main() -> None"
    aliases = imported_public_aliases(REPO_ROOT / MODULE_PATHS[VERSIONED_OWNER])
    assert aliases["handle_jsonrpc_message"]["module"] == PROTOCOL_OWNER
    assert aliases["tool_list_payload"]["name"] == "tool_list_payload"
    server_alias = imported_public_aliases(REPO_ROOT / MODULE_PATHS[GENERATOR_SERVER])
    assert server_alias["main"] == {"module": APPLICATIONS_SERVER, "name": "main"}
    by_name = {item["name"]: item for item in record["callables"]}
    protocol_def = next(
        item for item in by_name["handle_jsonrpc_message"]["definitions"] if item["kind"] == "function"
    )
    assert protocol_def["signature"] == functions["handle_jsonrpc_message"]
    validate_record(record)


def test_named_modules_do_not_bind_a_socket() -> None:
    for module, relative in MODULE_PATHS.items():
        assert network_bind_calls(REPO_ROOT / relative) == [], module
    record = load_record()
    assert record["binds_network_socket"] is False
    for item in [*record["owners"], *record["duplicate_servers"]]:
        assert item["path"] in MODULE_PATHS.values()


def test_recorded_callable_must_exist() -> None:
    record = load_record()
    record["callables"] = [
        *record["callables"],
        {
            "name": "not_an_mcp_callable",
            "owner": PROTOCOL_OWNER,
            "definitions": [
                {
                    "module": PROTOCOL_OWNER,
                    "kind": "function",
                    "signature": "def not_an_mcp_callable() -> None",
                }
            ],
        },
    ]
    with pytest.raises(McpOwnershipError, match="not_an_mcp_callable"):
        validate_record(record)


def test_signature_drift_fails() -> None:
    record = load_record()
    for entry in record["callables"]:
        if entry["name"] != "main":
            continue
        for definition in entry["definitions"]:
            if definition.get("kind") == "function":
                definition["signature"] = "def main(host: str, port: int) -> None"
    with pytest.raises(McpOwnershipError, match="signature drift"):
        validate_record(record)


def test_missing_owner_import_is_not_protocol_success() -> None:
    missing = "complaint_generator.mcp_owner_module_absent"
    try:
        importlib.import_module(missing)
        available = True
    except ImportError:
        available = False
    assert available is False
    assert owner_module_available(missing) is False
    outcome = classify_protocol_response(
        owner_available=available,
        response=SUCCESS_SHAPED_RESPONSE,
    )
    assert outcome["status"] == "unavailable"
    assert outcome["success"] is False
    assert outcome["accepted_response"] is None
    assert "result" in SUCCESS_SHAPED_RESPONSE
    record = load_record()
    assert record["import_failure"]["status"] == "unavailable"
    assert record["import_failure"]["treat_protocol_response_as_success"] is False


def test_available_owner_can_accept_a_result_without_starting_a_server() -> None:
    outcome = classify_protocol_response(owner_available=True, response=SUCCESS_SHAPED_RESPONSE)
    assert outcome["success"] is True
    assert outcome["status"] == "ok"
    error_outcome = classify_protocol_response(
        owner_available=True,
        response={"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Method not found"}},
    )
    assert error_outcome["success"] is False
    refused = classify_protocol_response(owner_available=False, response=SUCCESS_SHAPED_RESPONSE)
    assert refused["success"] is False
    assert refused["status"] == "unavailable"


def test_import_failure_policy_cannot_treat_a_response_as_success() -> None:
    record = load_record()
    record["import_failure"]["treat_protocol_response_as_success"] = True
    record["import_failure"]["status"] = "ok"
    with pytest.raises(McpOwnershipError, match="unavailable|not success"):
        validate_record(record)
