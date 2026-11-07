"""Documentation checks for the mediator package (CIMP-MOD-21).

The test loads mediator.interface by file path. The package initializer is
not executed, so this import does not import mediator.mediator.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "mediator" / "readme.md"
INTERFACE_PATH = REPO_ROOT / "mediator" / "interface.py"
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
EXPECTED_VERSION = "1.0.0"
LEGACY_SENTENCE = "mediator.py remains the legacy implementation behind the interface."
EXPECTED_OWNERS = (
    "mediator.workflow_service",
    "mediator.hook_runtime",
    "mediator.state",
)

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
OWNER_ROW_RE = re.compile(
    r"^\|\s*`(?P<module>mediator\.[^`]+)`\s*\|\s*\[[^\]]+\]\((?P<link>[^)]+)\)\s*\|\s*(?P<symbols>.+?)\s*\|",
    re.MULTILINE,
)
SYMBOL_RE = re.compile(r"`([^`]+)`")
_REMOTE_LINK_PREFIXES = ("http" + "://", "https" + "://", "mailto:")

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


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
        assert module.__name__ == "mediator.interface"
        yield module
    finally:
        _restore_package_modules()


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


def test_imports_mediator_interface_without_importing_mediator_mediator(interface) -> None:
    assert interface.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert interface.INTERFACE_VERSION == EXPECTED_VERSION
    assert interface.MODULE == "mediator.interface"
    assert interface.OWNER_MODULES == EXPECTED_OWNERS
    assert "mediator.mediator" not in interface.OWNER_MODULES
    assert interface.missing_public_symbols() == ()
    interface.require_public_symbols()
    assert interface.forbidden_import_names() == ()

    imported = _test_import_names()
    assert "mediator.mediator" not in imported
    assert not any(name.startswith("mediator.mediator.") for name in imported)
    assert "mediator.interface" in sys.modules
    assert sys.modules["mediator.interface"] is interface


def test_readme_names_interface_version_and_legacy_mediator(interface) -> None:
    text = _readme()
    assert "interface version" in text.lower()
    assert "1.0.0" in text
    assert "`1.0.0`" in text
    assert "Interface version" in text
    assert LEGACY_SENTENCE in text
    assert "INTERFACE_VERSION" in text
    assert "rather than `mediator.mediator`" in text

    rows = _owner_rows(text)
    assert tuple(module for module, _link, _symbols in rows) == interface.OWNER_MODULES
    documented = tuple(symbol for _module, _link, symbols in rows for symbol in symbols)
    assert documented == interface.PUBLIC_SYMBOLS
    for module, link, _symbols in rows:
        relative = module.split(".", 1)[1] + ".py"
        assert link == relative
        assert (README_PATH.parent / link).is_file()

    map_text = MAP_PATH.read_text(encoding="utf-8")
    assert '"name": "mediator"' in map_text
    assert '"path": "mediator"' in map_text
    assert "mediator/__init__.py" in map_text


def test_every_relative_link_resolves() -> None:
    text = _readme()
    links = _relative_links(text)
    assert links, "readme has no relative links"
    missing = [
        link
        for link in links
        if not (README_PATH.parent / link).resolve().is_file()
    ]
    assert missing == []
    assert "interface.py" in links
    assert "mediator.py" in links
    assert "../docs/architecture/repository_module_map.json" in links
    assert "../docs/THREE_PHASE_SYSTEM.md" in links
    assert "../docs/LEGAL_HOOKS.md" in links
    assert "../docs/EVIDENCE_MANAGEMENT.md" in links
    assert "../docs/LEGAL_AUTHORITY_RESEARCH.md" in links
    assert "../docs/SEARCH_HOOKS.md" in links
    for owner in EXPECTED_OWNERS:
        assert owner.split(".", 1)[1] + ".py" in links


def test_rejects_symbol_and_version_the_interface_does_not_name(interface) -> None:
    text = _readme()
    missing = interface.missing_public_symbols(("not_defined_in_any_owner",))
    assert missing == ("not_defined_in_any_owner",)
    with pytest.raises(interface.InterfaceOwnershipError, match="not_defined_in_any_owner"):
        interface.require_public_symbols(("not_defined_in_any_owner",))

    with pytest.raises(interface.InterfaceOwnershipError, match="symbol_absent_from_workflow_service"):
        interface.require_public_symbols(
            ("symbol_absent_from_workflow_service",),
            ("mediator.workflow_service",),
        )

    rows = _owner_rows(text)
    documented = {symbol for _module, _link, symbols in rows for symbol in symbols}
    assert documented == set(interface.PUBLIC_SYMBOLS)
    assert "mediator.mediator" not in {module for module, _link, _symbols in rows}
    assert "import mediator.mediator" not in text
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
