"""CIMP-MOD-16: legal-document facade keeps the three owners separate."""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FACADE_PATH = REPO_ROOT / "complaint_phases" / "legal_document_facade.py"
OWNERS_PATH = REPO_ROOT / "docs" / "architecture" / "legal_document_owners.json"
PHASE_PATH = REPO_ROOT / "complaint_phases" / "legal_document.py"
LIB_PATH = REPO_ROOT / "lib" / "legal_document.py"
FORMAL_PATH = REPO_ROOT / "mediator" / "formal_document.py"

OWNER_SCHEMA = "complaint-generator/duplicate-owner@1"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"

PHASE_PUBLIC = (
    "DocumentSection",
    "ParsedLegalDocument",
    "PleadingCaption",
    "PleadingHeader",
    "build_pleading_caption",
    "extract_pleading_header",
    "paginate_pleading_lines",
    "parse_legal_document",
    "render_pleading_caption_block",
)
FORMAL_ONLY = "ComplaintDocumentBuilder"
SEPARATE_OWNER_PATHS = (
    "lib/legal_document.py",
    "mediator/formal_document.py",
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _assigned_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_assigned_names(element))
        return names
    return set()


def defined_names(path: Path) -> set[str]:
    """Import-time public names bound in a module body."""
    names: set[str] = set()
    for node in _parse(path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(name for name in _assigned_names(target) if not name.startswith("_"))
        elif isinstance(node, ast.AnnAssign):
            names.update(name for name in _assigned_names(node.target) if not name.startswith("_"))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                if not bound.startswith("_"):
                    names.add(bound)
    return names


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _tuple_strings(node: ast.AST) -> tuple[str, ...] | None:
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    values: list[str] = []
    for element in node.elts:
        text = _string_constant(element)
        if text is None:
            return None
        values.append(text)
    return tuple(values)


def facade_assignments() -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for node in _parse(FACADE_PATH).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            found[node.target.id] = node.value
    return found


def facade_public_symbols() -> tuple[str, ...]:
    symbols = _tuple_strings(facade_assignments()["PUBLIC_SYMBOLS"])
    assert symbols is not None
    return symbols


def imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_owner_record_keeps_lib_and_formal_document_separate() -> None:
    document = json.loads(OWNERS_PATH.read_text(encoding="utf-8"))
    assert document["schema"] == OWNER_SCHEMA
    assert document["interface_version"] == INTERFACE_VERSION
    assert document["status"] == "separate"
    assert document["merged"] is False
    assert document["facade"]["version"] == INTERFACE_VERSION
    assert document["facade"]["interface_schema"] == INTERFACE_SCHEMA
    assert document["facade"]["reexports_from"] == "complaint_phases/legal_document.py"
    assert tuple(document["facade"]["public_symbols"]) == PHASE_PUBLIC

    by_path = {owner["path"]: owner for owner in document["owners"]}
    assert set(by_path) == {
        "complaint_phases/legal_document.py",
        "lib/legal_document.py",
        "mediator/formal_document.py",
    }
    for path in SEPARATE_OWNER_PATHS:
        assert by_path[path]["role"] == "separate_owner"
        assert by_path[path]["separate"] is True
        assert by_path[path]["merged"] is False
    phase = by_path["complaint_phases/legal_document.py"]
    assert phase["role"] == "reexport_source"
    assert phase["merged"] is False
    assert phase["separate"] is False


def test_three_owners_parse_and_facade_symbols_stay_inside_phase_module() -> None:
    phase_names = defined_names(PHASE_PATH)
    lib_names = defined_names(LIB_PATH)
    formal_names = defined_names(FORMAL_PATH)

    assert set(PHASE_PUBLIC) <= phase_names
    assert set(PHASE_PUBLIC) <= lib_names
    assert FORMAL_ONLY in formal_names
    assert FORMAL_ONLY not in phase_names

    exposed = set(facade_public_symbols())
    unexpected = exposed - phase_names
    assert unexpected == set()
    assert exposed == set(PHASE_PUBLIC)


def test_facade_rejects_a_symbol_the_phase_module_does_not_define() -> None:
    phase_names = defined_names(PHASE_PATH)
    polluted = set(facade_public_symbols()) | {FORMAL_ONLY}
    unexpected = polluted - phase_names
    assert unexpected == {FORMAL_ONLY}
    assert FORMAL_ONLY not in facade_public_symbols()
    assert FORMAL_ONLY not in defined_names(PHASE_PATH)


def test_facade_contract_does_not_import_mediator_or_copy_bodies() -> None:
    assignments = facade_assignments()
    assert _string_constant(assignments["INTERFACE_SCHEMA"]) == INTERFACE_SCHEMA
    assert _string_constant(assignments["INTERFACE_VERSION"]) == INTERFACE_VERSION
    separate = _tuple_strings(assignments["SEPARATE_OWNERS"])
    assert separate == ("lib.legal_document", "mediator.formal_document")

    imports = imported_modules(FACADE_PATH)
    assert "mediator" not in imports
    assert "mediator.mediator" not in imports
    assert "mediator.formal_document" not in imports
    assert "lib.legal_document" not in imports

    tree = _parse(FACADE_PATH)
    class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    function_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    }
    assert "PleadingHeader" not in class_names
    assert "ComplaintDocumentBuilder" not in class_names
    assert "parse_legal_document" not in function_names
    assert class_names == set()

    for path in (PHASE_PATH, LIB_PATH, FORMAL_PATH):
        source = path.read_text(encoding="utf-8")
        assert "INTERFACE_SCHEMA" not in source
        assert path.name != "legal_document_facade.py"


def test_importing_facade_does_not_import_mediator_mediator() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys\n"
                "import complaint_phases.legal_document_facade as facade\n"
                "payload = {\n"
                "  'modules': sorted(sys.modules),\n"
                "  'version': facade.INTERFACE_VERSION,\n"
                "  'schema': facade.INTERFACE_SCHEMA,\n"
                "  'symbols': list(facade.__all__),\n"
                "  'header': facade.PleadingHeader.__name__,\n"
                "}\n"
                "json.dump(payload, sys.stdout)\n"
            ),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr
    payload = json.loads(probe.stdout)
    modules = set(payload["modules"])
    assert "mediator.mediator" not in modules
    assert "mediator" not in modules
    assert "mediator.formal_document" not in modules
    assert payload["version"] == INTERFACE_VERSION
    assert payload["schema"] == INTERFACE_SCHEMA
    assert tuple(payload["symbols"]) == PHASE_PUBLIC
    assert payload["header"] == "PleadingHeader"


def test_facade_module_object_matches_phase_symbols() -> None:
    facade = importlib.import_module("complaint_phases.legal_document_facade")
    phase_names = defined_names(PHASE_PATH)
    exposed = set(facade.PUBLIC_SYMBOLS)
    assert exposed - phase_names == set()
    assert facade.INTERFACE_SCHEMA == INTERFACE_SCHEMA
    assert facade.INTERFACE_VERSION == INTERFACE_VERSION
    for name in PHASE_PUBLIC:
        assert hasattr(facade, name)
    assert not hasattr(facade, FORMAL_ONLY)
