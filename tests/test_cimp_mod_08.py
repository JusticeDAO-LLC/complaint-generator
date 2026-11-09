"""Tests for the ipfs_accelerate integration interface (CIMP-MOD-08).

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
INTERFACE_PATH = REPO_ROOT / "integrations" / "ipfs_accelerate" / "interface.py"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
EXPECTED_OWNERS = (
    "integrations.ipfs_accelerate.campaign",
    "integrations.ipfs_accelerate.improvement_plan",
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
    "integrations",
    "integrations.ipfs_accelerate",
    "integrations.ipfs_accelerate.interface",
)


def _load_interface():
    """Import integrations.ipfs_accelerate.interface without package __init__."""
    previous = {name: sys.modules.get(name) for name in _STUBBED}
    integrations = types.ModuleType("integrations")
    integrations.__path__ = [str(INTERFACE_PATH.parents[1])]
    integrations.__package__ = "integrations"
    package = types.ModuleType("integrations.ipfs_accelerate")
    package.__path__ = [str(INTERFACE_PATH.parent)]
    package.__package__ = "integrations.ipfs_accelerate"
    sys.modules["integrations"] = integrations
    sys.modules["integrations.ipfs_accelerate"] = package
    module_name = "integrations.ipfs_accelerate.interface"
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
    module._cimp_mod_08_previous = previous
    return module


def _restore_saved(previous: dict[str, types.ModuleType | None]) -> None:
    for name, saved in previous.items():
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved


def _restore_package_modules() -> None:
    interface = sys.modules.get("integrations.ipfs_accelerate.interface")
    previous = getattr(interface, "_cimp_mod_08_previous", None)
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


def test_interface_version_names_campaign_and_plan(interface) -> None:
    assert interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert interface.INTERFACE_VERSION == EXPECTED_VERSION
    assert interface.MODULE == "integrations.ipfs_accelerate.interface"
    assert interface.OWNER_MODULES == EXPECTED_OWNERS
    assert isinstance(interface.PUBLIC_SYMBOLS, tuple)
    assert interface.PUBLIC_SYMBOLS
    covered = set()
    for owner in interface.OWNER_MODULES:
        covered.update(interface.defined_names(owner) & set(interface.PUBLIC_SYMBOLS))
    assert "CampaignArtifacts" in covered
    assert "DEFAULT_ARTIFACTS" in covered
    assert "campaign_artifacts" in covered
    assert "validate_spec" in covered
    assert "build_improvement_work_plan" in covered
    assert "generate" in covered
    assert "EVIDENCE_SCHEMA" in covered
    assert interface.missing_public_symbols() == ()
    interface.require_public_symbols()


def test_import_does_not_start_server_or_read_private_workspace() -> None:
    opened: list[str] = []
    real_open = builtins.open
    socket_attr = "socket"
    real_socket = getattr(inet_mod, socket_attr)

    def tracing_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def rejecting_socket(*args, **kwargs):
        raise AssertionError("importing integrations.ipfs_accelerate.interface opened a listener")

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

    owners = interface.defined_names("integrations.ipfs_accelerate.campaign")
    assert "CampaignArtifacts" in owners
    assert "campaign_artifacts" in owners
    assert "symbol_absent_from_campaign" not in owners
    with pytest.raises(interface.InterfaceOwnershipError, match="symbol_absent_from_campaign"):
        interface.require_public_symbols(
            ("symbol_absent_from_campaign",),
            ("integrations.ipfs_accelerate.campaign",),
        )

    plan_names = interface.defined_names("integrations.ipfs_accelerate.improvement_plan")
    assert "validate_spec" in plan_names
    assert "generate" in plan_names
    assert "CampaignArtifacts" not in plan_names
    with pytest.raises(interface.InterfaceOwnershipError, match="CampaignArtifacts"):
        interface.require_public_symbols(
            ("CampaignArtifacts",),
            ("integrations.ipfs_accelerate.improvement_plan",),
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
