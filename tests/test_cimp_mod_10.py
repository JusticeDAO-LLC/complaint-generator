"""Tests for the mike integration interface (CIMP-MOD-10).

The interface module is loaded by file path. Package initializers are not
executed, so this import does not start a server, read a private workspace
path, or import the root mike compatibility directory or external.mike.
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
INTERFACE_PATH = REPO_ROOT / "integrations" / "mike" / "interface.py"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
EXPECTED_OWNERS = (
    "integrations.mike",
    "integrations.mike.llm_patch",
    "integrations.mike.skills",
)
CONNECTOR_SYMBOLS = (
    "apply_mike_llm_router_patch",
    "MIKE_LLM_PATCH_VERSION",
    "MIKE_LLM_PATCH_DESCRIPTOR",
    "get_router_generate_fn",
    "load_skill",
    "list_skill_ids",
    "load_all_skills",
    "SKILLS_DIR",
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
    "mike",
    "external.mike",
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
    "integrations.mike",
    "integrations.mike.interface",
)
_ROOT_MIKE_MODULES = ("mike", "external", "external.mike")


def _load_interface():
    """Import integrations.mike.interface without package __init__."""
    previous = {name: sys.modules.get(name) for name in _STUBBED}
    for name in _ROOT_MIKE_MODULES:
        previous.setdefault(name, sys.modules.get(name))
    integrations = types.ModuleType("integrations")
    integrations.__path__ = [str(INTERFACE_PATH.parents[1])]
    integrations.__package__ = "integrations"
    package = types.ModuleType("integrations.mike")
    package.__path__ = [str(INTERFACE_PATH.parent)]
    package.__package__ = "integrations.mike"
    sys.modules["integrations"] = integrations
    sys.modules["integrations.mike"] = package
    module_name = "integrations.mike.interface"
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
    module._cimp_mod_10_previous = previous
    return module


def _restore_saved(previous: dict[str, types.ModuleType | None]) -> None:
    for name, saved in previous.items():
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved


def _restore_package_modules() -> None:
    interface = sys.modules.get("integrations.mike.interface")
    previous = getattr(interface, "_cimp_mod_10_previous", None)
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


def test_interface_version_records_connector_symbols(interface) -> None:
    assert interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert interface.INTERFACE_VERSION == EXPECTED_VERSION
    assert interface.MODULE == "integrations.mike.interface"
    assert interface.OWNER_MODULES == EXPECTED_OWNERS
    assert interface.PUBLIC_SYMBOLS == CONNECTOR_SYMBOLS
    assert not hasattr(interface, "STATUS")
    covered = set()
    for owner in interface.OWNER_MODULES:
        covered.update(interface.defined_names(owner) & set(interface.PUBLIC_SYMBOLS))
    assert covered == set(CONNECTOR_SYMBOLS)
    assert interface.missing_public_symbols() == ()
    interface.require_public_symbols()


def test_import_does_not_load_root_mike_or_read_private_workspace() -> None:
    opened: list[str] = []
    real_open = builtins.open
    socket_attr = "socket"
    real_socket = getattr(inet_mod, socket_attr)
    before = {name: name in sys.modules for name in _ROOT_MIKE_MODULES}

    def tracing_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def rejecting_socket(*args, **kwargs):
        raise AssertionError("importing integrations.mike.interface opened a listener")

    builtins.open = tracing_open
    setattr(inet_mod, socket_attr, rejecting_socket)
    loaded_root: dict[str, bool] = {}
    try:
        module = _load_interface()
        loaded_root = {name: name in sys.modules for name in _ROOT_MIKE_MODULES}
    finally:
        builtins.open = real_open
        setattr(inet_mod, socket_attr, real_socket)
        _restore_package_modules()

    assert module.INTERFACE_VERSION == EXPECTED_VERSION
    assert loaded_root == before
    for path in opened:
        normalized = path.replace("\\", "/")
        assert not any(marker in normalized for marker in PRIVATE_PATH_MARKERS), path
        parts = Path(path).parts
        assert "external" not in parts
        assert parts[-1] == "interface.py"

    source = INTERFACE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(INTERFACE_PATH))
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
        assert not name.startswith("external.")
        assert name != "mike" and not name.startswith("mike.")
        assert "complaint_workspace" not in name
        assert name not in EXPECTED_OWNERS
    assert module.forbidden_import_names(tree) == ()


def test_rejects_symbol_not_defined_in_owner(interface) -> None:
    missing = interface.missing_public_symbols(("not_defined_in_any_owner",))
    assert missing == ("not_defined_in_any_owner",)
    with pytest.raises(interface.InterfaceOwnershipError, match="not_defined_in_any_owner"):
        interface.require_public_symbols(("not_defined_in_any_owner",))

    patch_names = interface.defined_names("integrations.mike.llm_patch")
    assert "apply_mike_llm_router_patch" in patch_names
    assert "get_router_generate_fn" in patch_names
    assert "load_skill" not in patch_names
    with pytest.raises(interface.InterfaceOwnershipError, match="load_skill"):
        interface.require_public_symbols(("load_skill",), ("integrations.mike.llm_patch",))

    skill_names = interface.defined_names("integrations.mike.skills")
    assert "load_skill" in skill_names
    assert "load_all_skills" in skill_names
    assert "SKILLS_DIR" in skill_names
    assert "apply_mike_llm_router_patch" not in skill_names
    with pytest.raises(interface.InterfaceOwnershipError, match="apply_mike_llm_router_patch"):
        interface.require_public_symbols(
            ("apply_mike_llm_router_patch",),
            ("integrations.mike.skills",),
        )


def test_rejects_root_mike_and_external_mike_as_owners(interface) -> None:
    with pytest.raises(interface.InterfaceOwnershipError, match="inside integrations.mike"):
        interface.defined_names("mike")
    with pytest.raises(interface.InterfaceOwnershipError, match="inside integrations.mike"):
        interface.owner_source_path("external.mike")
    with pytest.raises(interface.InterfaceOwnershipError, match="inside integrations.mike"):
        interface.missing_public_symbols(("apply_mike_llm_router_patch",), ("mike",))


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
        source = interface.owner_source_path(owner)
        assert INTERFACE_PATH.parent == source.parent or INTERFACE_PATH.parent in source.parents
        assert "external" not in source.parts
