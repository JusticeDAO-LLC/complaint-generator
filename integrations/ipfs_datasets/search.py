from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

from .loader import import_attr_optional, run_async_compat


CommonCrawlSearchEngine, _common_crawl_error = import_attr_optional(
    "ipfs_datasets_py.processors.web_archiving.common_crawl_integration",
    "CommonCrawlSearchEngine",
)
BraveSearchAPI, _brave_api_error = import_attr_optional(
    "ipfs_datasets_py.web_archiving",
    "BraveSearchAPI",
)
_search_brave, _brave_search_error = import_attr_optional(
    "ipfs_datasets_py.web_archiving.brave_search_engine",
    "search_brave",
)
UnifiedWebScraper, _unified_scraper_error = import_attr_optional(
    "ipfs_datasets_py.processors.web_archiving.unified_web_scraper",
    "UnifiedWebScraper",
)
ScraperConfig, _scraper_config_error = import_attr_optional(
    "ipfs_datasets_py.processors.web_archiving.unified_web_scraper",
    "ScraperConfig",
)
ScraperMethod, _scraper_method_error = import_attr_optional(
    "ipfs_datasets_py.processors.web_archiving.unified_web_scraper",
    "ScraperMethod",
)
MultiEngineOrchestrator, _orchestrator_error = import_attr_optional(
    "ipfs_datasets_py.processors.web_archiving.search_engines.orchestrator",
    "MultiEngineOrchestrator",
)
OrchestratorConfig, _orchestrator_config_error = import_attr_optional(
    "ipfs_datasets_py.processors.web_archiving.search_engines.orchestrator",
    "OrchestratorConfig",
)
ScraperValidator, _scraper_validator_error = import_attr_optional(
    "ipfs_datasets_py.processors.web_archiving.scraper_testing_framework",
    "ScraperValidator",
)
ScraperDomain, _scraper_domain_error = import_attr_optional(
    "ipfs_datasets_py.processors.web_archiving.scraper_testing_framework",
    "ScraperDomain",
)

COMMON_CRAWL_AVAILABLE = CommonCrawlSearchEngine is not None
BRAVE_SEARCH_AVAILABLE = BraveSearchAPI is not None or _search_brave is not None
UNIFIED_WEB_SCRAPER_AVAILABLE = (
    UnifiedWebScraper is not None and ScraperConfig is not None and ScraperMethod is not None
)
MULTI_ENGINE_SEARCH_AVAILABLE = MultiEngineOrchestrator is not None and OrchestratorConfig is not None
SCRAPER_VALIDATION_AVAILABLE = ScraperValidator is not None and ScraperDomain is not None
SEARCH_ERROR = (
    _common_crawl_error
    or _brave_api_error
    or _brave_search_error
    or _unified_scraper_error
    or _scraper_config_error
    or _scraper_method_error
    or _orchestrator_error
    or _orchestrator_config_error
    or _scraper_validator_error
    or _scraper_domain_error
)


def _coerce_value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _normalize_domain(url: str) -> str:
    parsed = urlparse(url or "")
    return parsed.netloc or ""


def _normalize_search_item(item: Any, source_type: str, *, query: str = "") -> Dict[str, Any]:
    title = str(_coerce_value(item, "title", "") or "")
    url = str(_coerce_value(item, "url", "") or "")
    snippet = str(
        _coerce_value(item, "snippet", _coerce_value(item, "description", _coerce_value(item, "content", ""))) or ""
    )
    metadata = _coerce_value(item, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    published_date = str(_coerce_value(item, "published_date", "") or "")
    score = _coerce_value(item, "score", 1.0)
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        score_value = 1.0

    domain = str(_coerce_value(item, "domain", "") or "") or _normalize_domain(url)
    engine = str(_coerce_value(item, "engine", "") or "")

    return {
        "title": title,
        "url": url,
        "description": snippet,
        "content": snippet,
        "source_type": source_type,
        "discovered_at": datetime.now().isoformat(),
        "metadata": {
            **metadata,
            "query": query,
            "engine": engine,
            "published_date": published_date,
            "domain": domain,
            "score": score_value,
        },
    }


def _normalize_scrape_result(result: Any, source_type: str) -> Dict[str, Any]:
    metadata = _coerce_value(result, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    method_used = _coerce_value(result, "method_used", None)
    method_name = getattr(method_used, "value", method_used)
    text = str(_coerce_value(result, "text", "") or "")
    content = text or str(_coerce_value(result, "content", "") or "")
    url = str(_coerce_value(result, "url", "") or "")

    return {
        "title": str(_coerce_value(result, "title", "") or ""),
        "url": url,
        "description": content[:400],
        "content": content,
        "html": str(_coerce_value(result, "html", "") or ""),
        "links": list(_coerce_value(result, "links", []) or []),
        "source_type": source_type,
        "success": bool(_coerce_value(result, "success", False)),
        "errors": list(_coerce_value(result, "errors", []) or []),
        "discovered_at": datetime.now().isoformat(),
        "metadata": {
            **metadata,
            "method_used": method_name,
            "domain": _normalize_domain(url),
            "extraction_time": _coerce_value(result, "extraction_time", 0.0),
        },
    }


def _coerce_scraper_methods(methods: Optional[Sequence[str]]) -> Optional[List[Any]]:
    if not methods or ScraperMethod is None:
        return None

    resolved: List[Any] = []
    for method_name in methods:
        if not method_name:
            continue
        normalized = str(method_name).strip().upper()
        if hasattr(ScraperMethod, normalized):
            resolved.append(getattr(ScraperMethod, normalized))
            continue
        for candidate in ScraperMethod:
            if candidate.value == method_name:
                resolved.append(candidate)
                break
    return resolved or None


def _deduplicate_results(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        key = url or f"{item.get('title', '')}|{item.get('source_type', '')}|{item.get('description', '')[:80]}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def search_brave_web(
    query: str,
    max_results: int = 10,
    freshness: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if _search_brave is None:
        return []

    payload = run_async_compat(
        _search_brave(
            query=query,
            api_key=api_key,
            count=min(max_results, 20),
            freshness=freshness,
        )
    )
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []

    results = payload.get("results", []) or []
    normalized: List[Dict[str, Any]] = []
    for item in results[:max_results]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "content": item.get("description", ""),
                "source_type": "brave_search",
                "discovered_at": datetime.now().isoformat(),
                "metadata": {
                    "language": item.get("language", ""),
                    "age": item.get("published_date", ""),
                },
            }
        )
    return normalized


def search_multi_engine_web(
    query: str,
    max_results: int = 10,
    engines: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if not MULTI_ENGINE_SEARCH_AVAILABLE:
        return search_brave_web(query=query, max_results=max_results)

    target_engines = engines or ["brave", "duckduckgo", "google_cse"]
    try:
        orchestrator = MultiEngineOrchestrator(OrchestratorConfig(engines=target_engines))
        response = orchestrator.search(query, max_results=max_results)
    except Exception:
        return search_brave_web(query=query, max_results=max_results)

    results = [_normalize_search_item(item, "multi_engine_search", query=query) for item in getattr(response, "results", [])]
    return _deduplicate_results(results[:max_results])


def scrape_web_content(
    url: str,
    *,
    methods: Optional[Sequence[str]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    if not UNIFIED_WEB_SCRAPER_AVAILABLE:
        return {
            "url": url,
            "title": "",
            "description": "",
            "content": "",
            "links": [],
            "source_type": "web_scrape",
            "success": False,
            "errors": ["UnifiedWebScraper unavailable"],
            "discovered_at": datetime.now().isoformat(),
            "metadata": {"domain": _normalize_domain(url)},
        }

    config = ScraperConfig(timeout=timeout)
    preferred_methods = _coerce_scraper_methods(methods)
    if preferred_methods:
        config.preferred_methods = preferred_methods

    scraper = UnifiedWebScraper(config)
    result = scraper.scrape_sync(url)
    return _normalize_scrape_result(result, "web_scrape")


def scrape_archived_domain(
    url: str,
    *,
    max_pages: int = 5,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    if not UNIFIED_WEB_SCRAPER_AVAILABLE:
        return []

    scraper = UnifiedWebScraper(ScraperConfig(timeout=timeout))
    try:
        results = scraper.scrape_domain(url, max_pages=max_pages)
    except Exception:
        return []

    normalized = [_normalize_scrape_result(item, "archived_domain_scrape") for item in results]
    return _deduplicate_results(normalized)


def evaluate_scraped_content(
    records: Sequence[Dict[str, Any]],
    *,
    scraper_name: str = "complaint_generator",
    domain: str = "caselaw",
) -> Dict[str, Any]:
    if not records:
        return {
            "scraper_name": scraper_name,
            "domain": domain,
            "status": "failed",
            "records_scraped": 0,
            "data_quality_score": 0.0,
            "quality_issues": [{"type": "empty_fields", "severity": "high", "details": ["No records"]}],
            "sample_data": [],
        }

    if not SCRAPER_VALIDATION_AVAILABLE:
        non_empty = sum(1 for record in records if str(record.get("content") or record.get("description") or "").strip())
        score = round(100.0 * (non_empty / max(1, len(records))), 2)
        return {
            "scraper_name": scraper_name,
            "domain": domain,
            "status": "success" if score >= 70.0 else "failed",
            "records_scraped": len(records),
            "data_quality_score": score,
            "quality_issues": [],
            "sample_data": list(records[:3]),
        }

    domain_value = getattr(ScraperDomain, str(domain).upper(), ScraperDomain.CASELAW)
    validator = ScraperValidator(domain_value)
    validation = validator.validate_dataset(list(records))
    payload = validation.to_dict() if hasattr(validation, "to_dict") else dict(validation)
    payload["scraper_name"] = scraper_name
    return payload


__all__ = [
    "CommonCrawlSearchEngine",
    "BraveSearchAPI",
    "COMMON_CRAWL_AVAILABLE",
    "BRAVE_SEARCH_AVAILABLE",
    "UNIFIED_WEB_SCRAPER_AVAILABLE",
    "MULTI_ENGINE_SEARCH_AVAILABLE",
    "SCRAPER_VALIDATION_AVAILABLE",
    "SEARCH_ERROR",
    "search_brave_web",
    "search_multi_engine_web",
    "scrape_web_content",
    "scrape_archived_domain",
    "evaluate_scraped_content",
]