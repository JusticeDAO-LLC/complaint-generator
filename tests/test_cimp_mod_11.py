"""Tests for the lib package interface (CIMP-MOD-11).

The interface module is loaded by file path. Package initializers are not
executed, so this import does not start a supervisor, mediator, or server.
"""

from __future__ import annotations

import ast
import builtins
import importlib.util
import socket as inet_mod
import sys
import types
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
INTERFACE_PATH = REPO_ROOT / "lib" / "interface.py"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
EXPECTED_OWNERS = (
    "lib.log",
    "lib.formal_logic",
    "lib.knowledge_graph_export",
)
LEGACY_OWNERS = (
    "lib.deontic_logic",
    "lib.legal_document",
)
SERVER_CALLS = frozenset(
    {
        "HTTPServer",
        "ThreadingHTTPServer",
        "TCPServer",
        "ThreadingTCPServer",
        "make_server",
        "serve_forever",
    }
)
FORBIDDEN_IMPORTS = (
    "mediator.mediator",
    "applications.complaint_workspace",
    "document_pipeline",
)
PRIVATE_PATH_MARKERS = (
    "/workspace/",
    "/.complaint",
    "complaint_workspace_data",
    "private_workspace",
)
_STUBBED = (
    "lib",
    "lib.interface",
)


def _load_interface():
    """Import lib.interface without package __init__."""
    previous = {name: sys.modules.get(name) for name in _STUBBED}
    package = types.ModuleType("lib")
    package.__path__ = [str(INTERFACE_PATH.parent)]
    package.__package__ = "lib"
    sys.modules["lib"] = package
    module_name = "lib.interface"
    spec = importlib.util.spec_from_file_location(module_name, INTERFACE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {INTERFACE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        _restore_saved(previous)
        raise
    module._cimp_mod_11_previous = previous
    return module


def _restore_saved(previous: dict[str, types.ModuleType | None]) -> None:
    for name, saved in previous.items():
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved


def _restore_package_modules() -> None:
    interface = sys.modules.get("lib.interface")
    previous = getattr(interface, "_cimp_mod_11_previous", None)
    if isinstance(previous, dict):
        _restore_saved(previous)
        return
    for name in reversed(_STUBBED):
        existing = sys.modules.get(name)
        if existing is not None and not getattr(existing, "__file__", None):
            sys.modules.pop(name, None)


@pytest.fixture
def interface():
    module = _load_interface()
    try:
        yield module
    finally:
        _restore_package_modules()


def test_interface_version_names_current_lib_owners(interface) -> None:
    assert interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert interface.INTERFACE_VERSION == EXPECTED_VERSION
    assert interface.MODULE == "lib.interface"
    assert interface.OWNER_MODULES == EXPECTED_OWNERS
    assert isinstance(interface.PUBLIC_SYMBOLS, tuple)
    assert interface.PUBLIC_SYMBOLS
    covered = set()
    for owner in interface.OWNER_MODULES:
        covered.update(interface.defined_names(owner) & set(interface.PUBLIC_SYMBOLS))
    assert "init_logging" in covered
    assert "make_logger" in covered
    assert "FormalLogicCapability" in covered
    assert "DeonticStatement" in covered
    assert "Frame" in covered
    assert "Neo4jExporter" in covered
    assert "ExportConfig" in covered
    assert "ExportResult" in covered
    assert "MigrationError" in covered
    assert interface.missing_public_symbols() == ()
    interface.require_public_symbols()


def test_legacy_owners_are_recorded_pending_ownership_tasks(interface) -> None:
    assert interface.LEGACY_OWNERS == LEGACY_OWNERS
    notes = interface.INTERFACE_NOTES
    assert "lib.deontic_logic" in notes
    assert "lib.legal_document" in notes
    assert "legacy owners pending the ownership tasks" in notes
    for legacy in LEGACY_OWNERS:
        assert legacy not in interface.OWNER_MODULES
    assert "pending the ownership tasks" in notes


def test_import_does_not_start_server_or_read_private_workspace() -> None:
    opened: list[str] = []
    real_open = builtins.open
    socket_attr = "socket"
    real_socket = getattr(inet_mod, socket_attr)

    def tracing_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def rejecting_socket(*args, **kwargs):
        raise AssertionError("importing lib.interface opened a listener")

    builtins.open = tracing_open
    setattr(inet_mod, socket_attr, rejecting_socket)
    try:
        module = _load_interface()
    finally:
        builtins.open = real_open
        setattr(inet_mod, socket_attr, real_socket)
        _restore_package_modules()

    assert module.INTERFACE_VERSION == EXPECTED_VERSION
    for path in opened:
        normalized = path.replace("\\", "/")
        assert not any(marker in normalized for marker in PRIVATE_PATH_MARKERS), path
        assert Path(path).name == "interface.py" or path.endswith("interface.py")

    tree = ast.parse(INTERFACE_PATH.read_text(encoding="utf-8"), filename=str(INTERFACE_PATH))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            assert name not in SERVER_CALLS
    for name in imported:
        assert name not in FORBIDDEN_IMPORTS
        assert not name.endswith("mcp_server")
        assert "complaint_workspace" not in name
        assert "supervisor" not in name
        assert name not in EXPECTED_OWNERS
    assert module.forbidden_import_names(tree) == ()


def test_rejects_symbol_not_defined_in_owner(interface) -> None:
    missing = interface.missing_public_symbols(("not_defined_in_any_owner",))
    assert missing == ("not_defined_in_any_owner",)
    with pytest.raises(interface.InterfaceOwnershipError, match="not_defined_in_any_owner"):
        interface.require_public_symbols(("not_defined_in_any_owner",))

    log_names = interface.defined_names("lib.log")
    assert "init_logging" in log_names
    assert "make_logger" in log_names
    assert "symbol_absent_from_log" not in log_names
    with pytest.raises(interface.InterfaceOwnershipError, match="symbol_absent_from_log"):
        interface.require_public_symbols(
            ("symbol_absent_from_log",),
            ("lib.log",),
        )

    logic_names = interface.defined_names("lib.formal_logic")
    assert "FormalLogicCapability" in logic_names
    assert "init_logging" not in logic_names
    with pytest.raises(interface.InterfaceOwnershipError, match="init_logging"):
        interface.require_public_symbols(
            ("init_logging",),
            ("lib.formal_logic",),
        )

    export_names = interface.defined_names("lib.knowledge_graph_export")
    assert "Neo4jExporter" in export_names
    assert "Frame" not in export_names
    with pytest.raises(interface.InterfaceOwnershipError, match="Frame"):
        interface.require_public_symbols(
            ("Frame",),
            ("lib.knowledge_graph_export",),
        )


def test_version_must_be_1_0_0(interface) -> None:
    assert interface.INTERFACE_VERSION == "1.0.0"
    assert interface.INTERFACE_VERSION != "1.0"
    source = INTERFACE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    versions = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "INTERFACE_VERSION" for target in node.targets)
        and isinstance(node.value, ast.Constant)
    ]
    assert versions == ["1.0.0"]


def test_each_owner_contributes_a_public_symbol(interface) -> None:
    for owner in EXPECTED_OWNERS:
        defined = interface.defined_names(owner)
        overlap = [symbol for symbol in interface.PUBLIC_SYMBOLS if symbol in defined]
        assert overlap, owner
        assert interface.missing_public_symbols(overlap, (owner,)) == ()
