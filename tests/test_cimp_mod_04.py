"""Tests for the applications package interface (CIMP-MOD-04).

The interface module is loaded by file path. The package initializer is not
executed, so this import does not pull complaint_workspace, mediator, or
server code.
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
INTERFACE_PATH = REPO_ROOT / "applications" / "interface.py"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
EXPECTED_OWNERS = (
    "applications.server",
    "applications.case_routes",
    "applications.launcher",
)
ROUTE_SYMBOLS = ("SERVER", "CASE_ROUTE_KINDS", "compose_case_routes")
WORKSPACE_ENTRY_SYMBOLS = (
    "launch_application",
    "start_configured_applications",
    "create_uvicorn_app_for_type",
)
SERVER_CALLS = frozenset(
    {
        "HTTPServer",
        "ThreadingHTTPServer",
        "TCPServer",
        "ThreadingTCPServer",
        "make_server",
        "serve_forever",
        "uvicorn",
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
    """Import applications.interface without running package __init__."""
    package_name = "applications"
    module_name = "applications.interface"
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
    sys.modules.pop("applications.interface", None)
    existing = sys.modules.get("applications")
    if existing is not None and not hasattr(existing, "__file__"):
        sys.modules.pop("applications", None)


@pytest.fixture
def interface():
    module = _load_interface()
    try:
        yield module
    finally:
        _restore_package_modules()


def test_interface_version_names_route_and_workspace_entries(interface) -> None:
    assert interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert interface.INTERFACE_VERSION == EXPECTED_VERSION
    assert interface.MODULE == "applications.interface"
    assert interface.OWNER_MODULES == EXPECTED_OWNERS
    assert isinstance(interface.PUBLIC_SYMBOLS, tuple)
    for symbol in ROUTE_SYMBOLS + WORKSPACE_ENTRY_SYMBOLS:
        assert symbol in interface.PUBLIC_SYMBOLS
    assert "complaint_workspace" not in interface.OWNER_MODULES
    assert interface.missing_public_symbols() == ()
    interface.require_public_symbols()

    server_names = interface.defined_names("applications.server")
    route_names = interface.defined_names("applications.case_routes")
    launcher_names = interface.defined_names("applications.launcher")
    assert "SERVER" in server_names
    assert "compose_case_routes" in route_names
    assert "CASE_ROUTE_KINDS" in route_names
    assert "launch_application" in launcher_names
    assert "start_configured_applications" in launcher_names
    assert "create_uvicorn_app_for_type" in launcher_names


def test_import_does_not_start_server_or_read_private_workspace() -> None:
    opened: list[str] = []
    real_open = builtins.open
    socket_attr = "socket"
    real_socket = getattr(inet_mod, socket_attr)

    def tracing_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def rejecting_socket(*args, **kwargs):
        raise AssertionError("importing applications.interface opened a listener")

    before_modules = set(sys.modules)
    builtins.open = tracing_open
    setattr(inet_mod, socket_attr, rejecting_socket)
    try:
        module = _load_interface()
    finally:
        builtins.open = real_open
        setattr(inet_mod, socket_attr, real_socket)
        loaded = set(sys.modules) - before_modules
        _restore_package_modules()

    assert module.INTERFACE_VERSION == EXPECTED_VERSION
    forbidden_loaded = {
        "applications.complaint_workspace",
        "applications.server",
        "applications.case_routes",
        "applications.launcher",
        "mediator.mediator",
        "document_pipeline",
    }
    assert forbidden_loaded.isdisjoint(loaded)
    for path in opened:
        normalized = path.replace("\\", "/")
        assert not any(marker in normalized for marker in PRIVATE_PATH_MARKERS), path
        assert "complaint_workspace" not in normalized
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
        assert "complaint_workspace" not in name
        assert name not in {"applications.server", "applications.case_routes", "applications.launcher"}
    assert module.forbidden_import_names(tree) == ()


def test_rejects_symbol_not_defined_in_owner(interface) -> None:
    missing = interface.missing_public_symbols(("not_defined_in_any_owner",))
    assert missing == ("not_defined_in_any_owner",)
    with pytest.raises(interface.InterfaceOwnershipError, match="not_defined_in_any_owner"):
        interface.require_public_symbols(("not_defined_in_any_owner",))

    owners = interface.defined_names("applications.server")
    assert "SERVER" in owners
    assert "symbol_absent_from_server" not in owners
    with pytest.raises(interface.InterfaceOwnershipError, match="symbol_absent_from_server"):
        interface.require_public_symbols(
            ("symbol_absent_from_server",),
            ("applications.server",),
        )

    route_only = interface.missing_public_symbols(
        ("launch_application",),
        ("applications.case_routes",),
    )
    assert route_only == ("launch_application",)


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


def test_unknown_owner_module_is_rejected(interface) -> None:
    with pytest.raises(interface.InterfaceOwnershipError, match="owner module must be inside"):
        interface.defined_names("mediator.mediator")
    with pytest.raises(interface.InterfaceOwnershipError, match="source was not found"):
        interface.defined_names("applications.does_not_exist")
