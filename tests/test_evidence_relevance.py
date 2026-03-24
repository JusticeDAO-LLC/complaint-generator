from __future__ import annotations

from complaint_generator.evidence_relevance import (
    build_complaint_terms,
    generate_email_search_plan,
    score_email_relevance,
)


def test_build_complaint_terms_combines_query_and_keywords(tmp_path) -> None:
    keyword_file = tmp_path / "keywords.txt"
    keyword_file.write_text("# comment\ntermination notice\nretaliation\n", encoding="utf-8")

    terms = build_complaint_terms(
        complaint_query="hearing request denial after eviction notice",
        complaint_keywords=["accommodation"],
        complaint_keyword_files=[str(keyword_file)],
    )

    assert "hearing" in terms
    assert "termination" in terms
    assert "retaliation" in terms
    assert "accommodation" in terms


def test_score_email_relevance_prefers_subject_and_attachment_hits() -> None:
    score = score_email_relevance(
        complaint_terms=["termination", "hearing", "retaliation"],
        subject="Termination hearing request",
        body_text="The retaliation timeline is attached below.",
        attachment_names=["retaliation-notice.pdf"],
    )

    assert score["score"] >= 6.0
    assert "subject" in score["matched_fields"]
    assert "attachments" in score["matched_fields"]
    assert "termination" in score["matched_terms"]


def test_generate_email_search_plan_includes_subject_terms() -> None:
    payload = generate_email_search_plan(
        complaint_query="termination hearing retaliation accommodation",
        complaint_keywords=["grievance"],
        addresses=["tenant@example.com"],
        date_after="2026-01-01",
    )

    assert payload["address_filters"] == ["tenant@example.com"]
    assert payload["recommended_subject_terms"]
    assert payload["recommended_subject_phrases"]
