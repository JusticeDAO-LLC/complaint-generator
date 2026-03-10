from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

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

COMMON_CRAWL_AVAILABLE = CommonCrawlSearchEngine is not None
BRAVE_SEARCH_AVAILABLE = BraveSearchAPI is not None or _search_brave is not None
SEARCH_ERROR = _common_crawl_error or _brave_api_error or _brave_search_error


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


__all__ = [
    "CommonCrawlSearchEngine",
    "BraveSearchAPI",
    "COMMON_CRAWL_AVAILABLE",
    "BRAVE_SEARCH_AVAILABLE",
    "SEARCH_ERROR",
    "search_brave_web",
]