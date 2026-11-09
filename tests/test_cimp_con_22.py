"""CIMP-CON-22: mediator intake-question methods delegate to intake_question_flow."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "mediator" / "mediator.py"
FLOW = REPO_ROOT / "mediator" / "intake_question_flow.py"
EXTRACTED = (
    "_summarize_intake_evidence_alignment",
    "_annotate_intake_question_candidate",
    "select_intake_question_candidates",
    "process_denoising_answer",
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _mediator_methods(tree: ast.AST) -> dict:
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Mediator"
    )
    return {
        node.name: node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
    }


def test_extracted_intake_methods_are_single_return_calls():
    owner_text = OWNER.read_text(encoding="utf-8")
    flow_text = FLOW.read_text(encoding="utf-8")
    methods = _mediator_methods(_parse(OWNER))
    defined = {
        node.name
        for node in _parse(FLOW).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert len(owner_text.splitlines()) <= 13600
    assert len(flow_text.splitlines()) >= 1450
    assert "research_case_automatically" in methods
    for name in EXTRACTED:
        method = methods[name]
        assert len(method.body) == 1, name
        statement = method.body[0]
        assert isinstance(statement, ast.Return), name
        assert isinstance(statement.value, ast.Call), name
        assert name in defined


def test_research_case_automatically_stays_on_the_mediator():
    methods = _mediator_methods(_parse(OWNER))
    moved = {
        node.name
        for node in _parse(FLOW).body
        if isinstance(node, ast.FunctionDef)
    }
    assert "research_case_automatically" in methods
    assert "research_case_automatically" not in moved
    assert len(methods["research_case_automatically"].body) > 1
