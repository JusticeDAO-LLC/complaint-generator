"""CIMP-CON-23: question-selection methods delegate to denoiser_questions."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "complaint_phases" / "denoiser.py"
QUESTIONS = REPO_ROOT / "complaint_phases" / "denoiser_questions.py"
EXTRACTED = (
    "generate_evidence_questions",
    "evaluate_interview_stop",
    "collect_question_candidates",
    "_build_history_follow_up_questions",
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_methods(tree: ast.AST) -> dict:
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ComplaintDenoiser"
    )
    return {
        node.name: node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
    }


def test_extracted_methods_are_single_return_calls():
    owner_text = OWNER.read_text(encoding="utf-8")
    questions_text = QUESTIONS.read_text(encoding="utf-8")
    owner = _parse(OWNER)
    questions = _parse(QUESTIONS)
    methods = _class_methods(owner)
    defined = {
        node.name
        for node in questions.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert len(owner_text.splitlines()) <= 7900
    assert len(questions_text.splitlines()) >= 1000
    assert "select_question_candidates" in methods
    for name in EXTRACTED:
        method = methods[name]
        assert len(method.body) == 1
        statement = method.body[0]
        assert isinstance(statement, ast.Return)
        assert isinstance(statement.value, ast.Call)
        assert name in defined


def test_select_question_candidates_stays_on_the_class():
    methods = _class_methods(_parse(OWNER))
    questions = _parse(QUESTIONS)
    moved = {
        node.name
        for node in questions.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "select_question_candidates" in methods
    assert "select_question_candidates" not in moved
    assert len(methods["select_question_candidates"].body) > 1
