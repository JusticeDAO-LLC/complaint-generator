"""CIMP-MOD-15: deontic-logic ownership from AST signatures only.

The modules are parsed and never imported. One owner is recorded only when
module-level public function signatures are equal. Differing signatures keep
status ``divergent`` and leave both files in place.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = REPO_ROOT / "docs" / "architecture" / "deontic_logic_ownership.json"
LIB_PATH = REPO_ROOT / "lib" / "deontic_logic.py"
PHASE_PATH = REPO_ROOT / "complaint_phases" / "deontic_logic.py"

SCHEMA = "complaint-generator/duplicate-owner@1"
INTERFACE_VERSION = "1.0.0"
LIB_MODULE = "lib.deontic_logic"
PHASE_MODULE = "complaint_phases.deontic_logic"
LIB_REL = "lib/deontic_logic.py"
PHASE_REL = "complaint_phases/deontic_logic.py"

PATHS = {
    LIB_MODULE: LIB_REL,
    PHASE_MODULE: PHASE_REL,
}


def function_signature(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise TypeError(f"not a function: {type(node).__name__}")
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    rendered = f"{prefix} {node.name}({ast.unparse(node.args)})"
    if node.returns is not None:
        rendered += " -> " + ast.unparse(node.returns)
    return rendered


def public_functions(path: Path) -> dict[str, str]:
    """Module-level public functions keyed by name, valued by AST signature."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            found[node.name] = function_signature(node)
    return found


def ownership_decision(lib_signatures: dict[str, str], phase_signatures: dict[str, str]) -> dict[str, object]:
    """Name one owner only when the two public-function maps are equal."""
    if lib_signatures == phase_signatures:
        return {
            "status": "owned",
            "owner": LIB_MODULE,
            "merged": False,
            "signatures_match": True,
        }
    return {
        "status": "divergent",
        "owner": None,
        "merged": False,
        "signatures_match": False,
    }


def load_record() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def test_record_follows_current_public_function_signatures() -> None:
    lib_signatures = public_functions(LIB_PATH)
    phase_signatures = public_functions(PHASE_PATH)
    decision = ownership_decision(lib_signatures, phase_signatures)
    record = load_record()

    assert record["schema"] == SCHEMA
    assert record["interface_version"] == INTERFACE_VERSION
    assert record["interface_version"] != "1.0"
    assert record["executed"] is False
    assert record["merged"] is False
    assert record["status"] == decision["status"]
    assert record["owner"] == decision["owner"]
    assert record["comparison"]["method"] == "ast"
    assert record["comparison"]["signatures_match"] is decision["signatures_match"]
    assert record["comparison"]["public_functions"][LIB_REL] == lib_signatures
    assert record["comparison"]["public_functions"][PHASE_REL] == phase_signatures

    roles = {item["module"]: item for item in record["modules"]}
    assert set(roles) == {LIB_MODULE, PHASE_MODULE}
    assert roles[LIB_MODULE]["path"] == LIB_REL
    assert roles[PHASE_MODULE]["path"] == PHASE_REL
    if decision["status"] == "owned":
        assert roles[LIB_MODULE]["role"] == "owner"
        assert roles[PHASE_MODULE]["role"] != "owner"
        assert sum(item["role"] == "owner" for item in record["modules"]) == 1
    else:
        assert record["owner"] is None
        assert all(item["role"] != "owner" for item in record["modules"])


def test_matching_empty_public_functions_name_the_lib_owner() -> None:
    lib_signatures = public_functions(LIB_PATH)
    phase_signatures = public_functions(PHASE_PATH)
    assert lib_signatures == {}
    assert phase_signatures == {}
    decision = ownership_decision(lib_signatures, phase_signatures)
    assert decision == {
        "status": "owned",
        "owner": LIB_MODULE,
        "merged": False,
        "signatures_match": True,
    }
    record = load_record()
    assert record["status"] == "owned"
    assert record["owner"] == LIB_MODULE
    assert record["merged"] is False


def test_private_helpers_are_not_public_functions() -> None:
    tree = ast.parse(LIB_PATH.read_text(encoding="utf-8"), filename=str(LIB_PATH))
    private = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_")
    ]
    assert "_utc_now_isoformat" in private
    assert "_modalities_conflict" in private
    assert public_functions(LIB_PATH) == {}
    assert "_utc_now_isoformat" not in load_record()["comparison"]["public_functions"][LIB_REL]


def test_divergent_signatures_name_no_owner() -> None:
    lib_signatures = {"assess": "def assess(graph) -> dict"}
    phase_signatures = {"assess": "def assess(graph) -> list"}
    decision = ownership_decision(lib_signatures, phase_signatures)
    assert decision["status"] == "divergent"
    assert decision["owner"] is None
    assert decision["merged"] is False
    assert decision["signatures_match"] is False

    missing_on_one_side = ownership_decision({"build": "def build() -> None"}, {})
    assert missing_on_one_side["status"] == "divergent"
    assert missing_on_one_side["owner"] is None

    record = load_record()
    assert record["status"] != "divergent"
    assert record["owner"] == LIB_MODULE


def test_owned_record_is_rejected_when_signatures_differ() -> None:
    forged = load_record()
    forged["status"] = "owned"
    forged["owner"] = LIB_MODULE
    forged["comparison"]["signatures_match"] = True
    forged["comparison"]["public_functions"] = {
        LIB_REL: {"to_dict": "def to_dict(self) -> dict"},
        PHASE_REL: {},
    }
    live = ownership_decision(
        forged["comparison"]["public_functions"][LIB_REL],
        forged["comparison"]["public_functions"][PHASE_REL],
    )
    assert live["status"] == "divergent"
    assert live["owner"] is None
    assert forged["status"] != live["status"]
    assert forged["owner"] != live["owner"]
    assert forged["merged"] is False


def test_both_implementations_remain_unmerged_and_unexecuted() -> None:
    assert LIB_PATH.is_file()
    assert PHASE_PATH.is_file()

    lib_tree = ast.parse(LIB_PATH.read_text(encoding="utf-8"), filename=str(LIB_PATH))
    phase_tree = ast.parse(PHASE_PATH.read_text(encoding="utf-8"), filename=str(PHASE_PATH))

    lib_classes = {node.name for node in lib_tree.body if isinstance(node, ast.ClassDef)}
    assert {"DeonticGraph", "DeonticGraphBuilder", "DeonticRule"} <= lib_classes
    phase_classes = {node.name for node in phase_tree.body if isinstance(node, ast.ClassDef)}
    phase_functions = {
        node.name
        for node in phase_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert phase_classes == set()
    assert phase_functions == set()

    imports = [
        node
        for node in phase_tree.body
        if isinstance(node, ast.ImportFrom)
    ]
    assert len(imports) == 1
    assert imports[0].module == "lib.deontic_logic"
    imported = {alias.name for alias in imports[0].names}
    assert "DeonticGraph" in imported
    assert "DeonticGraphBuilder" in imported

    test_tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    imported_modules = set()
    for node in ast.walk(test_tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert "lib.deontic_logic" not in imported_modules
    assert "lib" not in imported_modules
    assert "complaint_phases.deontic_logic" not in imported_modules
    assert "complaint_phases" not in imported_modules
    assert load_record()["merged"] is False
