"""Tests for the mediator package interface (CIMP-MOD-06).

The interface module is loaded by file path. The package initializer is not
executed, so this import does not pull mediator.mediator or start a server.
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

REPO_ROOT = Path(__file__).resolve().parents[1]
INTERFACE_PATH = REPO_ROOT / "mediator" / "interface.py"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
EXPECTED_OWNERS = (
    "mediator.workflow_service",
    "mediator.hook_runtime",
    "mediator.state",
)
WORKFLOW_SYMBOLS = ("WorkflowActionService",)
HOOK_SYMBOLS = (
    "HookExecutionContext",
    "bind_hook_execution_context",
    "authorize_hook_execution",
    "hook_runtime_identity",
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


def _load_interface():
    """Import mediator.interface without running package __init__."""
    package_name = "mediator"
    module_name = "mediator.interface"
    previous_package = sys.modules.get(package_name)
    previous_module = sys.modules.get(module_name)
    package = types.ModuleType(package_name)
    package.__path__ = [str(INTERFACE_PATH.parent)]
    package.__package__ = package_name
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(module_name, INTERFACE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {INTERFACE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        if previous_package is None:
            sys.modules.pop(package_name, None)
        else:
            sys.modules[package_name] = previous_package
        raise
    return module


def _restore_package_modules() -> None:
    sys.modules.pop("mediator.interface", None)
    existing = sys.modules.get("mediator")
    if existing is not None and not hasattr(existing, "__file__"):
        sys.modules.pop("mediator", None)


@pytest.fixture
def interface():
    before = "mediator.mediator" in sys.modules
    module = _load_interface()
    try:
        assert ("mediator.mediator" in sys.modules) is before
        yield module
    finally:
        _restore_package_modules()


def test_interface_version_names_workflow_and_hook_symbols(interface) -> None:
    assert interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert interface.INTERFACE_VERSION == EXPECTED_VERSION
    assert interface.MODULE == "mediator.interface"
    assert interface.OWNER_MODULES == EXPECTED_OWNERS
    assert isinstance(interface.PUBLIC_SYMBOLS, tuple)
    assert interface.PUBLIC_SYMBOLS
    covered = set()
    for owner in interface.OWNER_MODULES:
        covered.update(interface.defined_names(owner) & set(interface.PUBLIC_SYMBOLS))
    for symbol in WORKFLOW_SYMBOLS:
        assert symbol in covered
        assert symbol in interface.defined_names("mediator.workflow_service")
    for symbol in HOOK_SYMBOLS:
        assert symbol in covered
        assert symbol in interface.defined_names("mediator.hook_runtime")
    assert "State" in interface.defined_names("mediator.state")
    assert "extract_chat_history_context_strings_from_state" in interface.defined_names(
        "mediator.state"
    )
    assert interface.missing_public_symbols() == ()
    interface.require_public_symbols()


def test_import_does_not_import_mediator_or_start_server() -> None:
    opened: list[str] = []
    real_open = builtins.open
    socket_attr = "socket"
    real_socket = getattr(inet_mod, socket_attr)
    mediator_loaded_before = "mediator.mediator" in sys.modules

    def tracing_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def rejecting_socket(*args, **kwargs):
        raise AssertionError("importing mediator.interface opened a listener")

    builtins.open = tracing_open
    setattr(inet_mod, socket_attr, rejecting_socket)
    try:
        module = _load_interface()
    finally:
        builtins.open = real_open
        setattr(inet_mod, socket_attr, real_socket)
        _restore_package_modules()

    assert ("mediator.mediator" in sys.modules) is mediator_loaded_before
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
        assert name != "mediator.mediator"
        assert not name.startswith("mediator.mediator.")
        assert "complaint_workspace" not in name
        assert name != "document_pipeline" and not name.startswith("document_pipeline.")
    assert module.forbidden_import_names(tree) == ()


def test_rejects_symbol_not_defined_in_owner(interface) -> None:
    missing = interface.missing_public_symbols(("not_defined_in_any_owner",))
    assert missing == ("not_defined_in_any_owner",)
    with pytest.raises(interface.InterfaceOwnershipError, match="not_defined_in_any_owner"):
        interface.require_public_symbols(("not_defined_in_any_owner",))

    owners = interface.defined_names("mediator.workflow_service")
    assert "WorkflowActionService" in owners
    assert "symbol_absent_from_workflow_service" not in owners
    with pytest.raises(interface.InterfaceOwnershipError, match="symbol_absent_from_workflow_service"):
        interface.require_public_symbols(
            ("symbol_absent_from_workflow_service",),
            ("mediator.workflow_service",),
        )

    hook_names = interface.defined_names("mediator.hook_runtime")
    assert "hook_runtime_identity" in hook_names
    assert "WorkflowActionService" not in hook_names
    with pytest.raises(interface.InterfaceOwnershipError, match="WorkflowActionService"):
        interface.require_public_symbols(
            ("WorkflowActionService",),
            ("mediator.hook_runtime",),
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
