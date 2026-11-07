"""Documentation checks for the complaint_phases package (CIMP-MOD-22).

The test imports complaint_phases.interface and checks complaint_phases/README.md
against that facade. Legal and deontic modules stay separate owners.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import complaint_phases.interface as phase_interface

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "complaint_phases" / "README.md"
INTERFACE_PATH = REPO_ROOT / "complaint_phases" / "interface.py"
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
EXPECTED_OWNERS = (
    "complaint_phases.phase_manager",
    "complaint_phases.knowledge_graph",
    "complaint_phases.intake_case_file",
)
SEPARATE_OWNERS = (
    "complaint_phases.legal_document",
    "complaint_phases.legal_document_facade",
    "complaint_phases.deontic_logic",
)
DISTINCTION = (
    "The phase pipeline is distinct from the separate legal and deontic owners."
)

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
OWNER_ROW_RE = re.compile(
    r"^\|\s*`(?P<module>complaint_phases\.[^`]+)`\s*\|\s*\[[^\]]+\]\((?P<link>[^)]+)\)\s*\|\s*(?P<symbols>.+?)\s*\|",
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


def test_imports_complaint_phases_interface() -> None:
    assert phase_interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert phase_interface.INTERFACE_VERSION == EXPECTED_VERSION
    assert phase_interface.MODULE == "complaint_phases.interface"
    assert phase_interface.OWNER_MODULES == EXPECTED_OWNERS
    for separate in SEPARATE_OWNERS:
        assert separate not in phase_interface.OWNER_MODULES
    assert "complaint_phases.legal_graph" not in phase_interface.OWNER_MODULES
    assert phase_interface.missing_public_symbols() == ()
    phase_interface.require_public_symbols()
    assert phase_interface.forbidden_import_names() == ()

    imported = _test_import_names()
    assert "complaint_phases.interface" in imported
    assert "complaint_phases.interface" in __import__("sys").modules


def test_readme_names_interface_version_and_separates_legal_and_deontic() -> None:
    text = _readme()
    assert "interface version" in text.lower()
    assert "1.0.0" in text
    assert "`1.0.0`" in text
    assert "Interface version" in text
    assert "INTERFACE_VERSION" in text
    assert DISTINCTION in text
    assert "phase pipeline" in text
    assert "separate legal and deontic owners" in text
    assert "not a phase-pipeline owner" in text

    rows = _owner_rows(text)
    assert tuple(module for module, _link, _symbols in rows) == phase_interface.OWNER_MODULES
    documented = tuple(symbol for _module, _link, symbols in rows for symbol in symbols)
    assert documented == phase_interface.PUBLIC_SYMBOLS
    for module, link, _symbols in rows:
        relative = module.split(".", 1)[1] + ".py"
        assert link == relative
        assert (README_PATH.parent / link).is_file()

    for separate in SEPARATE_OWNERS:
        assert separate in text
        assert separate not in {module for module, _link, _symbols in rows}

    map_text = MAP_PATH.read_text(encoding="utf-8")
    assert '"name": "complaint_phases"' in map_text
    assert '"path": "complaint_phases"' in map_text
    assert "complaint_phases/__init__.py" in map_text


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
    assert "legal_document.py" in links
    assert "legal_document_facade.py" in links
    assert "deontic_logic.py" in links
    assert "legal_graph.py" in links
    assert "../docs/architecture/repository_module_map.json" in links
    for owner in EXPECTED_OWNERS:
        assert owner.split(".", 1)[1] + ".py" in links


def test_rejects_symbol_version_and_diffusion_claim_the_interface_does_not_expose() -> None:
    text = _readme()
    missing = phase_interface.missing_public_symbols(("not_defined_in_any_owner",))
    assert missing == ("not_defined_in_any_owner",)
    with pytest.raises(phase_interface.InterfaceOwnershipError, match="not_defined_in_any_owner"):
        phase_interface.require_public_symbols(("not_defined_in_any_owner",))

    with pytest.raises(
        phase_interface.InterfaceOwnershipError,
        match="symbol_absent_from_phase_manager",
    ):
        phase_interface.require_public_symbols(
            ("symbol_absent_from_phase_manager",),
            ("complaint_phases.phase_manager",),
        )

    rows = _owner_rows(text)
    documented = {symbol for _module, _link, symbols in rows for symbol in symbols}
    assert documented == set(phase_interface.PUBLIC_SYMBOLS)
    for separate in SEPARATE_OWNERS:
        assert separate not in {module for module, _link, _symbols in rows}
    assert "ComplaintDenoiser" not in documented
    assert "DeonticGraph" not in documented
    assert "LegalGraph" not in documented
    assert "diffusion" not in text.lower()
    assert "three-phase" not in text.lower()
    assert "denoising diffusion" not in text.lower()
    assert "INTERFACE_VERSION` is `2.0.0`" not in text
    assert "interface version 2.0.0" not in text.lower()
    assert "interface version 0.9.0" not in text.lower()

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
