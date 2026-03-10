from __future__ import annotations

from typing import Any, Dict, List, Optional

from .loader import import_attr_optional, run_async_compat


_search_us_code_async, _us_code_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.us_code_scraper",
    "search_us_code",
)
_search_federal_register_async, _federal_register_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.federal_register_scraper",
    "search_federal_register",
)
_search_recap_documents_async, _recap_error = import_attr_optional(
    "ipfs_datasets_py.processors.legal_scrapers.recap_archive_scraper",
    "search_recap_documents",
)

LEGAL_SCRAPERS_AVAILABLE = any(
    value is not None
    for value in (
        _search_us_code_async,
        _search_federal_register_async,
        _search_recap_documents_async,
    )
)
LEGAL_SCRAPERS_ERROR = _us_code_error or _federal_register_error or _recap_error


def _normalize_authority(
    item: Dict[str, Any],
    authority_type: str,
    source: str,
) -> Dict[str, Any]:
    url = item.get("url") or item.get("html_url") or item.get("pdf_url") or ""
    citation = (
        item.get("citation")
        or item.get("document_number")
        or item.get("id")
        or item.get("title")
        or ""
    )
    title = item.get("title") or item.get("case_name") or citation
    content = (
        item.get("content")
        or item.get("text")
        or item.get("snippet")
        or item.get("summary")
        or ""
    )
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    normalized = dict(item)
    normalized.update(
        {
            "type": item.get("type", authority_type),
            "source": item.get("source", source),
            "citation": citation,
            "title": title,
            "content": content,
            "url": url,
            "metadata": metadata,
            "relevance_score": item.get("relevance_score", 0.5),
        }
    )
    return normalized


def search_us_code(query: str, title: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
    if _search_us_code_async is None:
        return []
    payload = run_async_compat(
        _search_us_code_async(
            query=query,
            titles=[title] if title else None,
            max_results=max_results,
        )
    )
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    return [
        _normalize_authority(item, "statute", "us_code")
        for item in (payload.get("results", []) or [])[:max_results]
        if isinstance(item, dict)
    ]


def search_federal_register(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    if _search_federal_register_async is None:
        return []
    payload = run_async_compat(
        _search_federal_register_async(
            keywords=query,
            start_date=start_date,
            end_date=end_date,
            limit=max_results,
        )
    )
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    return [
        _normalize_authority(item, "regulation", "federal_register")
        for item in (payload.get("documents", []) or [])[:max_results]
        if isinstance(item, dict)
    ]


def search_recap_documents(
    query: str,
    court: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    if _search_recap_documents_async is None:
        return []
    payload = run_async_compat(
        _search_recap_documents_async(
            query=query,
            court=court,
            limit=max_results,
        )
    )
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    return [
        _normalize_authority(item, "case_law", "recap")
        for item in (payload.get("documents", []) or [])[:max_results]
        if isinstance(item, dict)
    ]


__all__ = [
    "LEGAL_SCRAPERS_AVAILABLE",
    "LEGAL_SCRAPERS_ERROR",
    "search_us_code",
    "search_federal_register",
    "search_recap_documents",
]