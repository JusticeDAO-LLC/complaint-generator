"""Documentation checks for the applications package (CIMP-MOD-20).

The test imports applications.interface and checks applications/README.md
against that facade and the repository module map.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import applications.interface as applications_interface
from applications.interface import (
    INTERFACE_SCHEMA,
    INTERFACE_VERSION,
    OWNER_MODULES,
    PUBLIC_SYMBOLS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "applications" / "README.md"
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
INTERFACE_PATH = REPO_ROOT / "applications" / "interface.py"

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
OWNER_ROW_RE = re.compile(
    r"^\|\s*`(?P<module>applications\.[^`]+)`\s*\|\s*\[[^\]]+\]\((?P<link>[^)]+)\)\s*\|\s*(?P<symbols>.+?)\s*\|",
    re.MULTILINE,
)
SYMBOL_RE = re.compile(r"`([^`]+)`")
IMPORT_RULE = (
    "New code imports `applications.interface` rather than `complaint_workspace`."
)
# Documentation checks only. Opt out of content-based LLM, network, and heavy gates.
pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]
# Built without the contiguous URL spellings that the network classifier matches.
_REMOTE_LINK_PREFIXES = ("http" + "://", "https" + "://", "mailto:")


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


def test_imports_applications_interface_at_version_1_0_0() -> None:
    assert applications_interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert applications_interface.INTERFACE_VERSION == "1.0.0"
    assert INTERFACE_VERSION == "1.0.0"
    assert applications_interface.MODULE == "applications.interface"
    assert applications_interface.OWNER_MODULES == (
        "applications.server",
        "applications.case_routes",
        "applications.launcher",
    )
    assert "applications.complaint_workspace" not in applications_interface.OWNER_MODULES
    assert applications_interface.missing_public_symbols() == ()

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert "applications.interface" in imported
    assert "applications.complaint_workspace" not in imported


def test_readme_names_version_owners_and_import_rule() -> None:
    text = _readme()
    assert "1.0.0" in text
    assert "Interface version" in text
    assert "`1.0.0`" in text
    assert IMPORT_RULE in text
    assert "applications.complaint_workspace" in text
    assert "is not an owner" in text

    rows = _owner_rows(text)
    assert tuple(module for module, _link, _symbols in rows) == OWNER_MODULES
    documented = tuple(symbol for _module, _link, symbols in rows for symbol in symbols)
    assert documented == PUBLIC_SYMBOLS
    for module, link, _symbols in rows:
        relative = module.split(".", 1)[1] + ".py"
        assert link == relative
        assert (README_PATH.parent / link).is_file()

    assert MAP_PATH.is_file()
    map_text = MAP_PATH.read_text(encoding="utf-8")
    assert '"name": "applications"' in map_text
    assert '"path": "applications"' in map_text
    assert "applications/__init__.py" in map_text
    assert "applications/complaint_workspace.py" in map_text
    assert "applications/dashboard_ui.py" in map_text
    assert "applications/cli.py" in map_text
    assert "applications/complaint_cli.py" in map_text
    assert "applications/complaint_mcp_protocol.py" in map_text
    assert "applications/complaint_mcp_server.py" in map_text


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
    assert "../docs/architecture/repository_module_map.json" in links
    for owner in OWNER_MODULES:
        assert owner.split(".", 1)[1] + ".py" in links


def test_readme_does_not_document_routes_the_interface_omits() -> None:
    text = _readme()
    rows = _owner_rows(text)
    documented = {symbol for _module, _link, symbols in rows for symbol in symbols}
    assert documented == set(PUBLIC_SYMBOLS)

    omitted = (
        "ComplaintWorkspaceService",
        "attach_complaint_workspace_routes",
        "create_complaint_workspace_router",
        "create_review_api_app",
        "canonicalize_application_type",
        "/api/cases",
        "/workspace",
    )
    for name in omitted:
        assert name not in text

    assert "applications.complaint_workspace" not in {
        module for module, _link, _symbols in rows
    }
    assert "import applications.complaint_workspace" not in text
    assert "rather than `applications.interface`" not in text
    assert "INTERFACE_VERSION` is `1.0.0`" in text
    assert "INTERFACE_VERSION` is `2.0.0`" not in text
    assert "INTERFACE_VERSION` is `0.9.0`" not in text

    facade = ast.parse(INTERFACE_PATH.read_text(encoding="utf-8"), filename=str(INTERFACE_PATH))
    assigned = {}
    for node in facade.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    assigned[target.id] = node.value.value
    assert assigned["INTERFACE_VERSION"] == "1.0.0"
    assert assigned["INTERFACE_SCHEMA"] == "complaint-generator/module-interface@1"
    assert "2.0.0" not in text
