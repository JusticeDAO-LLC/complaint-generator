"""Documentation checks for the complaint_generator package (CIMP-MOD-24).

The test imports complaint_generator.interface and checks complaint_generator/README.md
against that facade. CLI and MCP names must match the modules the interface lists.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import complaint_generator.interface as package_interface

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "complaint_generator" / "README.md"
INTERFACE_PATH = REPO_ROOT / "complaint_generator" / "interface.py"
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
EXPECTED_OWNERS = (
    "complaint_generator.entrypoints",
    "complaint_generator.workspace",
    "complaint_generator.mcp",
)
CLI_MODULE = "complaint_generator.entrypoints"
MCP_MODULE = "complaint_generator.mcp"
BESIDE_INTERFACE = (
    "complaint_generator.cli",
    "complaint_generator.mcp_server",
)
LATER_OWNERSHIP_FILES = (
    "entrypoint_ownership.json",
    "mcp_ownership.json",
)

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
OWNER_ROW_RE = re.compile(
    r"^\|\s*`(?P<module>complaint_generator\.[^`]+)`\s*\|\s*\[[^\]]+\]\((?P<link>[^)]+)\)\s*\|\s*(?P<symbols>.+?)\s*\|",
    re.MULTILINE,
)
SYMBOL_RE = re.compile(r"`([^`]+)`")
_REMOTE_LINK_PREFIXES = ("http" + "://", "https" + "://", "mailto:")

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


def _test_import_names() -> list[str]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    return imported


def test_imports_complaint_generator_interface() -> None:
    assert package_interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert package_interface.INTERFACE_VERSION == EXPECTED_VERSION
    assert package_interface.MODULE == "complaint_generator.interface"
    assert package_interface.OWNER_MODULES == EXPECTED_OWNERS
    assert CLI_MODULE in package_interface.OWNER_MODULES
    assert MCP_MODULE in package_interface.OWNER_MODULES
    for beside in BESIDE_INTERFACE:
        assert beside not in package_interface.OWNER_MODULES
    assert package_interface.missing_public_symbols() == ()
    package_interface.require_public_symbols()
    assert package_interface.forbidden_import_names() == ()

    imported = _test_import_names()
    assert "complaint_generator.interface" in imported
    assert "complaint_generator.interface" in __import__("sys").modules


def test_readme_names_interface_version_and_listed_cli_and_mcp_modules() -> None:
    text = _readme()
    assert "interface version" in text.lower()
    assert "1.0.0" in text
    assert "`1.0.0`" in text
    assert "Interface version" in text
    assert "INTERFACE_VERSION" in text
    assert "The CLI module the interface lists is `complaint_generator.entrypoints`." in text
    assert "The MCP module the interface lists is `complaint_generator.mcp`." in text
    assert CLI_MODULE in text
    assert MCP_MODULE in text

    rows = _owner_rows(text)
    assert tuple(module for module, _link, _symbols in rows) == package_interface.OWNER_MODULES
    documented = tuple(symbol for _module, _link, symbols in rows for symbol in symbols)
    assert documented == package_interface.PUBLIC_SYMBOLS
    for module, link, _symbols in rows:
        relative = module.split(".", 1)[1] + ".py"
        assert link.endswith(relative)
        assert (README_PATH.parent / link).is_file()

    for beside in BESIDE_INTERFACE:
        assert beside in text
        assert beside not in {module for module, _link, _symbols in rows}

    for ownership_file in LATER_OWNERSHIP_FILES:
        assert ownership_file not in text

    map_text = MAP_PATH.read_text(encoding="utf-8")
    assert '"name": "complaint_generator"' in map_text
    assert '"path": "complaint_generator"' in map_text
    assert "complaint_generator/__init__.py" in map_text


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
    assert "interface.py" in links
    assert "__init__.py" in links
    assert "__main__.py" in links
    assert "entrypoints.py" in links
    assert "workspace.py" in links
    assert "mcp.py" in links
    assert "cli.py" in links
    assert "mcp_server.py" in links
    assert "../docs/architecture/repository_module_map.json" in links
    for owner in EXPECTED_OWNERS:
        assert owner.split(".", 1)[1] + ".py" in links
    for ownership_file in LATER_OWNERSHIP_FILES:
        assert ownership_file not in links
        assert all(ownership_file not in link for link in links)


def test_rejects_symbol_version_and_unlisted_cli_or_mcp_owner() -> None:
    text = _readme()
    missing = package_interface.missing_public_symbols(("not_defined_in_any_owner",))
    assert missing == ("not_defined_in_any_owner",)
    with pytest.raises(package_interface.InterfaceOwnershipError, match="not_defined_in_any_owner"):
        package_interface.require_public_symbols(("not_defined_in_any_owner",))

    with pytest.raises(
        package_interface.InterfaceOwnershipError,
        match="symbol_absent_from_mcp",
    ):
        package_interface.require_public_symbols(
            ("symbol_absent_from_mcp",),
            ("complaint_generator.mcp",),
        )

    rows = _owner_rows(text)
    documented = {symbol for _module, _link, symbols in rows for symbol in symbols}
    owners = {module for module, _link, _symbols in rows}
    assert documented == set(package_interface.PUBLIC_SYMBOLS)
    assert owners == set(package_interface.OWNER_MODULES)
    assert "complaint_generator.cli" not in owners
    assert "complaint_generator.mcp_server" not in owners
    assert "keys_unlock" not in documented
    assert "app" not in documented
    assert "INTERFACE_VERSION` is `2.0.0`" not in text
    assert "interface version 2.0.0" not in text.lower()
    assert "interface version 0.9.0" not in text.lower()
    for ownership_file in LATER_OWNERSHIP_FILES:
        assert ownership_file not in text

    facade = ast.parse(INTERFACE_PATH.read_text(encoding="utf-8"), filename=str(INTERFACE_PATH))
    assigned = {}
    for node in facade.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    assigned[target.id] = node.value.value
    assert assigned["INTERFACE_VERSION"] == "1.0.0"
    assert assigned["INTERFACE_SCHEMA"] == INTERFACE_SCHEMA
    assert "2.0.0" not in text
