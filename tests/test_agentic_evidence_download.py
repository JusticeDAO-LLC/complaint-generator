from __future__ import annotations

import json
from pathlib import Path

from complaint_generator.agentic_evidence_download import (
    generate_complaint_search_queries,
    run_agentic_evidence_download,
    score_search_candidate,
)


def test_generate_complaint_search_queries_includes_domain_seed() -> None:
    queries = generate_complaint_search_queries(
        complaint_query="grievance hearing retaliation",
        complaint_keywords=["appeal", "denial"],
        domain_seeds=["hud.gov"],
        max_queries=6,
    )

    assert queries
    assert any("site:hud.gov" in query for query in queries)
    assert not any("grievance hearing retaliation site:hud.gov" == query for query in queries)
    assert all(len(query.split()) <= 5 for query in queries)


def test_score_search_candidate_uses_title_and_snippet() -> None:
    scored = score_search_candidate(
        {
            "title": "Termination hearing request notice",
            "description": "Retaliation and grievance process details.",
            "url": "https://example.org/hearing",
        },
        complaint_terms=["termination", "hearing", "retaliation"],
    )

    assert scored["relevance_score"] >= 4.0
    assert "termination" in scored["matched_terms"]


def test_run_agentic_evidence_download_saves_only_relevant_scrapes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.search_multi_engine_web",
        lambda query, max_results=8: [
            {"title": "Termination hearing notice", "description": "Retaliation hearing details", "url": "https://example.org/a"},
            {"title": "Weekly deals", "description": "Shopping plan", "url": "https://example.org/b"},
        ],
    )
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.scrape_web_content",
        lambda url, timeout=30: {
            "title": "Termination hearing notice" if url.endswith("/a") else "Weekly deals",
            "url": url,
            "description": "Retaliation and grievance process details" if url.endswith("/a") else "Shopping plan",
            "content": "Retaliation grievance hearing notice denial" if url.endswith("/a") else "Coupons and sales",
            "html": "<html></html>",
        },
    )
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.evaluate_scraped_content",
        lambda records, scraper_name="x", domain="caselaw": {"status": "success", "records_scraped": len(records), "data_quality_score": 100.0},
    )

    payload = run_agentic_evidence_download(
        complaint_query="grievance hearing retaliation denial",
        output_dir=tmp_path,
        max_queries=3,
        max_search_results=4,
        max_downloads=2,
        min_search_score=2.0,
        min_download_score=3.0,
    )

    assert payload["downloaded_count"] == 1
    manifest_path = Path(payload["manifest_path"])
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["downloaded_count"] == 1
    assert manifest["downloads"][0]["url"] == "https://example.org/a"


def test_run_agentic_evidence_download_uses_domain_seed_fallback_when_search_is_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.search_multi_engine_web",
        lambda query, max_results=8: [],
    )
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.scrape_web_content",
        lambda url, timeout=30: {
            "title": "Grievance Procedures and Requirements",
            "url": url,
            "description": "hearing grievance notice denial",
            "content": "hearing grievance notice denial appeal due process",
            "html": "",
        },
    )
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.evaluate_scraped_content",
        lambda records, scraper_name="x", domain="caselaw": {"status": "success", "records_scraped": len(records), "data_quality_score": 100.0},
    )

    payload = run_agentic_evidence_download(
        complaint_query="grievance hearing denial appeal",
        domain_seeds=["hud.gov"],
        output_dir=tmp_path,
        max_queries=2,
        max_search_results=2,
        max_downloads=1,
        min_search_score=2.0,
        min_download_score=3.0,
    )

    assert payload["candidate_count"] >= 1
    assert payload["downloaded_count"] == 1


def test_run_agentic_evidence_download_uses_explicit_seed_urls(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.search_multi_engine_web",
        lambda query, max_results=8: [],
    )
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.scrape_web_content",
        lambda url, timeout=30: {
            "title": "Grievance Procedures and Requirements",
            "url": url,
            "description": "hearing grievance notice denial",
            "content": "hearing grievance notice denial appeal due process",
            "html": "",
        },
    )
    monkeypatch.setattr(
        "complaint_generator.agentic_evidence_download.evaluate_scraped_content",
        lambda records, scraper_name="x", domain="caselaw": {"status": "success", "records_scraped": len(records), "data_quality_score": 100.0},
    )

    payload = run_agentic_evidence_download(
        complaint_query="grievance hearing denial appeal",
        seed_urls=["https://example.org/grievance"],
        output_dir=tmp_path,
        max_queries=2,
        max_search_results=2,
        max_downloads=1,
        min_search_score=2.0,
        min_download_score=3.0,
    )

    assert payload["candidate_count"] >= 1
    assert payload["downloaded_count"] == 1
    assert payload["downloads"][0]["url"] == "https://example.org/grievance"
