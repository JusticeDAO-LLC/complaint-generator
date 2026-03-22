from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_main_readme_documents_grounded_history_helper() -> None:
    readme = REPO_ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")

    assert "scripts/show_hacc_grounded_history.py" in text
    assert "--list-runs" in text
    assert "--output-dir previous" in text
    assert "--output-dir last-successful" in text
    assert "grounded pipeline rerun for pre-follow-up runs" in text
    assert "switches to complaint synthesis" in text
    assert "--synthesize-complaint" in text
    assert "--completed-grounded-intake-worksheet" in text


def test_tests_readme_documents_grounded_history_helper() -> None:
    readme = REPO_ROOT / "tests" / "README.md"
    text = readme.read_text(encoding="utf-8")

    assert "scripts/show_hacc_grounded_history.py" in text
    assert "--list-runs" in text
    assert "--output-dir previous" in text
    assert "--output-dir last-successful" in text
    assert "grounded pipeline rerun for pre-follow-up runs" in text
    assert "switching to synthesis once a worksheet-backed resume is ready" in text
    assert "--synthesize-complaint" in text
    assert "--completed-grounded-intake-worksheet" in text
