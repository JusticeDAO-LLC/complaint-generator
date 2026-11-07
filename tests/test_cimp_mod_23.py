"""Documentation checks for the integrations package (CIMP-MOD-23).

The test imports the accelerate, datasets, and mike interface modules. Parent
packages are registered first so those imports do not execute package
initializers, stat external/, or advance a pin. Empty root ipfs_datasets_py
and mike directories stay compatibility paths.
"""

from __future__ import annotations

import ast
import re
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "integrations" / "README.md"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
PIN_SENTENCE = "External/ pins are not advanced by documentation work."
CHECKOUT_SENTENCE = "Submodule checkouts are at `external/`."
COMPATIBILITY_SENTENCE = (
    "The empty root `ipfs_datasets_py` and `mike` directories are compatibility paths, "
    "not the SDK trees."
)
INTERFACE_MODULES = (
    "integrations.ipfs_accelerate.interface",
    "integrations.ipfs_datasets.interface",
    "integrations.mike.interface",
)


def _register_package(name: str) -> None:
    """Point a package name at its source directory without running __init__."""
    if name in sys.modules and getattr(sys.modules[name], "__file__", None):
        return
    package = types.ModuleType(name)
    package.__path__ = [str(REPO_ROOT.joinpath(*name.split(".")))]
    package.__package__ = name
    sys.modules[name] = package


for _package_name in (
    "integrations",
    "integrations.ipfs_accelerate",
    "integrations.ipfs_datasets",
    "integrations.mike",
):
    _register_package(_package_name)

import integrations.ipfs_accelerate.interface as accelerate_interface
import integrations.ipfs_datasets.interface as datasets_interface
import integrations.mike.interface as mike_interface

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
OWNER_ROW_RE = re.compile(
    r"^\|\s*`(?P<module>integrations\.[^`]+)`\s*\|\s*\[[^\]]+\]\((?P<link>[^)]+)\)\s*\|\s*(?P<symbols>.+?)\s*\|",
    re.MULTILINE,
)
SYMBOL_RE = re.compile(r"`([^`]+)`")
_REMOTE_LINK_PREFIXES = ("http" + "://", "https" + "://", "mailto:")
_INTERFACES = (
    accelerate_interface,
    datasets_interface,
    mike_interface,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _readme() -> str:
    return README_PATH.read_text(encoding="utf-8")


def _relative_links(text: str) -> list[str]:
    links: list[str] = []
    for match in LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith(_REMOTE_LINK_PREFIXES):
            continue
        links.append(target.split("#", 1)[0].strip())
    return links


def _owner_rows(text: str) -> list[tuple[str, str, tuple[str, ...]]]:
    rows: list[tuple[str, str, tuple[str, ...]]] = []
    for match in OWNER_ROW_RE.finditer(text):
        symbols = tuple(SYMBOL_RE.findall(match.group("symbols")))
        rows.append((match.group("module"), match.group("link"), symbols))
    return rows


def _import_names() -> list[str]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    return imported


def test_imports_the_three_integration_interface_modules() -> None:
    loaded = {
        "integrations.ipfs_accelerate.interface": accelerate_interface,
        "integrations.ipfs_datasets.interface": datasets_interface,
        "integrations.mike.interface": mike_interface,
    }
    for module_name, interface in loaded.items():
        assert interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
        assert interface.INTERFACE_VERSION == EXPECTED_VERSION
        assert interface.MODULE == module_name
        assert interface.missing_public_symbols() == ()
        interface.require_public_symbols()
        assert sys.modules[module_name] is interface

    assert accelerate_interface.OWNER_MODULES == (
        "integrations.ipfs_accelerate.campaign",
        "integrations.ipfs_accelerate.improvement_plan",
    )
    assert datasets_interface.OWNER_MODULES == (
        "integrations.ipfs_datasets.loader",
        "integrations.ipfs_datasets.documents",
    )
    assert mike_interface.OWNER_MODULES == (
        "integrations.mike",
        "integrations.mike.llm_patch",
        "integrations.mike.skills",
    )
    assert "ipfs_datasets_py" not in datasets_interface.OWNER_MODULES
    assert "mike" not in mike_interface.OWNER_MODULES
    assert "external.mike" not in mike_interface.OWNER_MODULES
    imported = _import_names()
    assert [name for name in imported if name in INTERFACE_MODULES] == list(INTERFACE_MODULES)


def test_readme_names_interface_versions_and_does_not_advance_external_pins() -> None:
    text = _readme()
    assert PIN_SENTENCE in text
    assert CHECKOUT_SENTENCE in text
    assert COMPATIBILITY_SENTENCE in text
    assert "external/ipfs_accelerate_py" in text
    assert "external/ipfs_datasets_py" in text
    assert "external/mike" in text
    assert "The accelerate interface version is `1.0.0`." in text
    assert "The datasets interface version is `1.0.0`." in text
    assert "The mike interface version is `1.0.0`." in text
    assert "INTERFACE_VERSION" in text

    rows = _owner_rows(text)
    by_module = {module: (link, symbols) for module, link, symbols in rows}
    for interface in _INTERFACES:
        for owner in interface.OWNER_MODULES:
            assert owner in by_module
            link, _symbols = by_module[owner]
            assert (README_PATH.parent / link).is_file()
        owner_symbols = tuple(
            symbol
            for module, _link, symbols in rows
            if module in interface.OWNER_MODULES
            for symbol in symbols
        )
        assert set(owner_symbols) == set(interface.PUBLIC_SYMBOLS)
        assert len(owner_symbols) == len(interface.PUBLIC_SYMBOLS)


def test_every_relative_link_resolves() -> None:
    text = _readme()
    links = _relative_links(text)
    assert links, "README has no relative links"
    missing = [
        link
        for link in links
        if not (README_PATH.parent / link).resolve().is_file()
    ]
    assert missing == []
    for module_name in INTERFACE_MODULES:
        relative = "/".join(module_name.split(".")[1:]) + ".py"
        assert relative in links
    assert "__init__.py" in links
    assert "../.gitmodules" in links
    assert "../docs/architecture/repository_module_map.json" in links
    assert "ipfs_accelerate/campaign.py" in links
    assert "ipfs_datasets/loader.py" in links
    assert "ipfs_datasets/documents.py" in links
    assert "mike/llm_patch.py" in links
    assert "mike/skills/__init__.py" in links
    assert "ipfs_datasets_py" not in links
    assert "mike" not in links


def test_rejects_symbol_version_and_sdk_claim_the_interfaces_do_not_make() -> None:
    text = _readme()
    for interface in _INTERFACES:
        missing = interface.missing_public_symbols(("not_defined_in_any_owner",))
        assert missing == ("not_defined_in_any_owner",)
        with pytest.raises(interface.InterfaceOwnershipError, match="not_defined_in_any_owner"):
            interface.require_public_symbols(("not_defined_in_any_owner",))

    with pytest.raises(datasets_interface.InterfaceOwnershipError, match="inside integrations.ipfs_datasets"):
        datasets_interface.owner_source_path("ipfs_datasets_py")
    with pytest.raises(mike_interface.InterfaceOwnershipError, match="inside integrations.mike"):
        mike_interface.owner_source_path("mike")
    with pytest.raises(
        accelerate_interface.InterfaceOwnershipError,
        match="inside integrations.ipfs_accelerate",
    ):
        accelerate_interface.owner_source_path("external.ipfs_accelerate_py")

    assert "interface version 2.0.0" not in text.lower()
    assert "INTERFACE_VERSION` is `2.0.0`" not in text
    assert "pins are advanced by documentation" not in text.lower()
    assert "root `ipfs_datasets_py` and `mike` directories are the SDK trees" not in text
    assert "compatibility paths, not the SDK trees" in text
    rows = _owner_rows(text)
    documented = {symbol for _module, _link, symbols in rows for symbol in symbols}
    assert "not_defined_in_any_owner" not in documented
    owners = {module for module, _link, _symbols in rows}
    assert "ipfs_datasets_py" not in owners
    assert "mike" not in owners
    assert "external.mike" not in owners
    for interface in _INTERFACES:
        assert interface.INTERFACE_VERSION == EXPECTED_VERSION
        assert interface.INTERFACE_VERSION != "2.0.0"
