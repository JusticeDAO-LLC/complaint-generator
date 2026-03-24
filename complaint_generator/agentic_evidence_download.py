from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from complaint_generator.evidence_relevance import build_complaint_terms, generate_email_search_plan, score_email_relevance
from integrations.ipfs_datasets.search import evaluate_scraped_content, scrape_web_content, search_multi_engine_web


def _slugify(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return cleaned[:80] or fallback


def _default_output_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "evidence" / "agentic_downloads"


GENERIC_SEARCH_TERMS = {
    "policy",
    "response",
    "dates",
    "chronology",
    "review",
    "complaint",
    "tenant",
    "request",
    "decision",
    "action",
    "due",
    "process",
    "reasonable",
    "exact",
    "timeline",
    "housing",
    "assistance",
    "lease",
    "occupancy",
    "administrative",
    "plan",
}


def _prioritize_search_terms(terms: Sequence[str]) -> list[str]:
    prioritized: list[str] = []
    for term in terms:
        normalized = str(term or "").strip().lower()
        if not normalized or normalized in GENERIC_SEARCH_TERMS:
            continue
        if normalized not in prioritized:
            prioritized.append(normalized)
    return prioritized


def _build_domain_seed_urls(domain_seeds: Sequence[str]) -> list[str]:
    urls: list[str] = []
    for raw_domain in domain_seeds:
        domain = str(raw_domain or "").strip()
        if not domain:
            continue
        if domain.startswith("http://") or domain.startswith("https://"):
            candidates = [domain]
        else:
            candidates = [f"https://{domain}"]
            if not domain.startswith("www."):
                candidates.append(f"https://www.{domain}")
        for candidate in candidates:
            if candidate not in urls:
                urls.append(candidate)
    return urls


def generate_complaint_search_queries(
    *,
    complaint_query: str,
    complaint_keywords: Sequence[str] = (),
    complaint_keyword_files: Sequence[str] = (),
    domain_seeds: Sequence[str] = (),
    max_queries: int = 6,
) -> list[str]:
    plan = generate_email_search_plan(
        complaint_query=complaint_query,
        complaint_keywords=complaint_keywords,
        complaint_keyword_files=complaint_keyword_files,
        addresses=[],
    )
    phrases = [str(item or "").strip().lower() for item in list(plan.get("recommended_subject_phrases") or []) if str(item or "").strip()]
    terms = _prioritize_search_terms(
        list(plan.get("recommended_subject_terms") or []) + list(plan.get("complaint_terms") or [])
    )
    queries: list[str] = []
    base_domains = [str(value or "").strip() for value in domain_seeds if str(value or "").strip()]

    def _add(query: str) -> None:
        normalized = " ".join(str(query or "").split()).strip()
        if normalized and normalized not in queries:
            queries.append(normalized)

    anchor_pairs: list[str] = []
    if len(terms) >= 2:
        anchor_pairs.append(" ".join(terms[:2]))
    if len(terms) >= 4:
        anchor_pairs.append(" ".join(terms[2:4]))
    for phrase in phrases + anchor_pairs:
        _add(phrase)
        for domain in base_domains:
            _add(f"{phrase} site:{domain}")
    if terms:
        _add(" ".join(terms[:3]))
        if len(terms) >= 5:
            _add(" ".join([terms[0], terms[2], terms[4]]))
        for domain in base_domains:
            _add(" ".join([*terms[:3], f"site:{domain}"]))
    _add(" ".join(terms[:2]) if len(terms) >= 2 else complaint_query)
    return queries[:max_queries]


def score_search_candidate(
    candidate: dict[str, Any],
    *,
    complaint_terms: Sequence[str],
) -> dict[str, Any]:
    title = str(candidate.get("title") or "")
    snippet = str(candidate.get("description") or candidate.get("snippet") or "")
    url = str(candidate.get("url") or "")
    domain = urlparse(url).netloc
    relevance = score_email_relevance(
        complaint_terms=complaint_terms,
        subject=title,
        sender=domain,
        body_text=snippet,
    )
    candidate = dict(candidate)
    candidate["relevance_score"] = float(relevance["score"])
    candidate["matched_terms"] = list(relevance["matched_terms"])
    candidate["matched_fields"] = list(relevance["matched_fields"])
    return candidate


def _save_scraped_record(output_dir: Path, *, index: int, record: dict[str, Any]) -> dict[str, Any]:
    title = str(record.get("title") or record.get("url") or f"record-{index}")
    item_dir = output_dir / f"{index:03d}-{_slugify(title, fallback='record')}"
    item_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = item_dir / "record.json"
    text_path = item_dir / "content.txt"
    html_path = item_dir / "content.html"
    metadata_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    text_path.write_text(str(record.get("content") or ""), encoding="utf-8")
    html = str(record.get("html") or "")
    if html:
        html_path.write_text(html, encoding="utf-8")
    return {
        "title": title,
        "url": str(record.get("url") or ""),
        "artifact_dir": str(item_dir),
        "metadata_path": str(metadata_path),
        "content_path": str(text_path),
        "html_path": str(html_path) if html else "",
        "relevance_score": float(record.get("relevance_score", 0.0) or 0.0),
        "matched_terms": list(record.get("matched_terms") or []),
    }


def run_agentic_evidence_download(
    *,
    complaint_query: str,
    complaint_keywords: Sequence[str] = (),
    complaint_keyword_files: Sequence[str] = (),
    domain_seeds: Sequence[str] = (),
    seed_urls: Sequence[str] = (),
    output_dir: str | Path | None = None,
    max_queries: int = 6,
    max_search_results: int = 8,
    max_downloads: int = 5,
    min_search_score: float = 2.0,
    min_download_score: float = 3.0,
    scrape_timeout: int = 30,
    quality_domain: str = "caselaw",
) -> dict[str, Any]:
    complaint_terms = build_complaint_terms(
        complaint_query=complaint_query,
        complaint_keywords=complaint_keywords,
        complaint_keyword_files=complaint_keyword_files,
    )
    queries = generate_complaint_search_queries(
        complaint_query=complaint_query,
        complaint_keywords=complaint_keywords,
        complaint_keyword_files=complaint_keyword_files,
        domain_seeds=domain_seeds,
        max_queries=max_queries,
    )
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for query in queries:
        for item in search_multi_engine_web(query, max_results=max_search_results):
            scored = score_search_candidate(item, complaint_terms=complaint_terms)
            url = str(scored.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            if float(scored["relevance_score"]) < float(min_search_score):
                continue
            scored["seed_query"] = query
            candidates.append(scored)
    for url in [str(item or "").strip() for item in seed_urls if str(item or "").strip()]:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        scored = score_search_candidate(
            {
                "title": urlparse(url).netloc,
                "description": "",
                "url": url,
            },
            complaint_terms=complaint_terms,
        )
        scored["seed_query"] = "explicit_seed_url"
        candidates.append(scored)
    if not candidates and domain_seeds:
        for url in _build_domain_seed_urls(domain_seeds):
            scored = score_search_candidate(
                {
                    "title": urlparse(url).netloc,
                    "description": "",
                    "url": url,
                },
                complaint_terms=complaint_terms,
            )
            scored["seed_query"] = "domain_seed_fallback"
            candidates.append(scored)
    candidates.sort(key=lambda item: float(item.get("relevance_score", 0.0) or 0.0), reverse=True)

    output_root = Path(output_dir) if output_dir is not None else _default_output_dir()
    run_dir = output_root / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    downloads: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(downloads) >= int(max_downloads):
            break
        scraped = scrape_web_content(str(candidate.get("url") or ""), timeout=scrape_timeout)
        scored = score_search_candidate(
            {
                **scraped,
                "title": str(scraped.get("title") or candidate.get("title") or ""),
                "description": str(scraped.get("description") or candidate.get("description") or ""),
                "url": str(scraped.get("url") or candidate.get("url") or ""),
            },
            complaint_terms=complaint_terms,
        )
        if float(scored["relevance_score"]) < float(min_download_score):
            continue
        scored["seed_query"] = candidate.get("seed_query", "")
        scored["search_relevance_score"] = float(candidate.get("relevance_score", 0.0) or 0.0)
        downloads.append(scored)

    saved = [_save_scraped_record(run_dir, index=index, record=record) for index, record in enumerate(downloads, start=1)]
    quality = evaluate_scraped_content(downloads, scraper_name="agentic_complaint_evidence_scraper", domain=quality_domain)
    manifest = {
        "status": "success",
        "complaint_query": complaint_query,
        "complaint_terms": complaint_terms,
        "queries": queries,
        "seed_urls": list(seed_urls),
        "candidate_count": len(candidates),
        "downloaded_count": len(saved),
        "output_dir": str(run_dir),
        "candidates": candidates,
        "downloads": saved,
        "quality": quality,
    }
    manifest_path = run_dir / "agentic_evidence_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


__all__ = [
    "generate_complaint_search_queries",
    "run_agentic_evidence_download",
    "score_search_candidate",
]
