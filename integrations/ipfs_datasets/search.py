from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import time

from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

import requests

from .loader import import_attr_optional, run_async_compat
from .types import with_adapter_metadata


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


@dataclass(frozen=True)
class QuerySpec:
    sites: list[str]
    phrases: list[str]
    tokens: list[str]


def _looks_like_pdf_bytes(data: bytes) -> bool:
    return bytes(data[:5]) == b"%PDF-"


def normalize_site(site: str) -> str:
    value = (site or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/", 1)[0]
    if value.startswith("www."):
        value = value[4:]
    return value


def parse_seeded_query(query: str) -> QuerySpec:
    normalized = re.sub(r"\s+", " ", (query or "").strip())
    sites = [normalize_site(site) for site in re.findall(r"\bsite:([^\s)]+)", normalized, flags=re.I)]
    phrases = [phrase.strip() for phrase in re.findall(r"\"([^\"]+)\"", normalized) if phrase.strip()]
    stripped = re.sub(r"\"[^\"]+\"", " ", normalized)
    stripped = re.sub(r"\([^)]*\)", " ", stripped)
    raw_tokens = [token for token in re.split(r"\s+", stripped) if token]
    drop = {"or", "and", "policy", "rule", "statute", "complaint", "nondiscrimination"}
    tokens: list[str] = []
    for token in raw_tokens:
        lowered = token.lower()
        if lowered.startswith("site:") or lowered in drop:
            continue
        if not re.search(r"[a-z0-9]", lowered):
            continue
        if len(token) <= 2 and lowered not in {"vi", "ii"}:
            continue
        tokens.append(token)
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        lowered = token.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(token)
    return QuerySpec(sites=[site for site in sites if site], phrases=phrases, tokens=deduped)


def load_seeded_queries(path: str | Path) -> list[str]:
    queries: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            queries.append(stripped)
    return queries


def score_archive_url(url: str, terms: list[str]) -> int:
    lowered_url = (url or "").lower()
    score = 0
    for term in terms:
        lowered_term = (term or "").lower()
        if not lowered_term:
            continue
        if lowered_term in lowered_url:
            score += 3
            continue
        parts = [part for part in re.split(r"\s+", lowered_term) if part]
        if len(parts) > 1 and all(part in lowered_url for part in parts):
            score += 2
    return score


def fetch_commoncrawl_latest_index(session: requests.Session) -> str:
    response = session.get("https://index.commoncrawl.org/collinfo.json", timeout=30)
    response.raise_for_status()
    indexes = response.json()
    if not indexes:
        raise RuntimeError("CommonCrawl collinfo.json returned no indexes")
    return str(indexes[0]["cdx-api"])


def fetch_commoncrawl_index_candidates(session: requests.Session) -> list[str]:
    response = session.get("https://index.commoncrawl.org/collinfo.json", timeout=30)
    response.raise_for_status()
    indexes = response.json()
    if not indexes:
        raise RuntimeError("CommonCrawl collinfo.json returned no indexes")
    candidates: list[str] = []
    seen: set[str] = set()
    for item in indexes:
        candidate = str(item.get("cdx-api") or "").strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def commoncrawl_list_urls(session: requests.Session, cdx_api: str, site: str, limit: int) -> list[dict[str, Any]]:
    response = session.get(cdx_api, params={"url": f"{site}/*", "output": "json", "limit": int(limit)}, timeout=60)
    response.raise_for_status()
    rows: list[dict[str, Any]] = []
    for line in (response.text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except Exception:
            continue
    return rows


def fetch_archive_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    response.raise_for_status()
    html = response.text or ""
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def discover_seeded_commoncrawl(
    queries_file: str | Path,
    *,
    cc_limit: int = 1000,
    top_per_site: int = 50,
    fetch_top: int = 0,
    sleep_seconds: float = 0.5,
) -> Dict[str, Any]:
    query_path = Path(queries_file)
    if not query_path.exists():
        return with_adapter_metadata(
            {"status": "error", "error": f"missing queries file: {query_path}", "queries_file": str(query_path)},
            operation="discover_seeded_commoncrawl",
            backend_available=True,
            implementation_status="error",
        )

    queries = load_seeded_queries(query_path)
    specs = [parse_seeded_query(query) for query in queries]
    site_terms: dict[str, list[str]] = defaultdict(list)
    for spec in specs:
        terms = [term for term in [*spec.phrases, *spec.tokens] if term and len(term) <= 60]
        for site in spec.sites:
            if site:
                site_terms[site].extend(terms)
    for site, terms in list(site_terms.items()):
        seen: set[str] = set()
        deduped: list[str] = []
        for term in terms:
            lowered = term.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(term)
        site_terms[site] = deduped[:200]

    session = requests.Session()
    cdx_api_candidates = fetch_commoncrawl_index_candidates(session)
    cdx_api = cdx_api_candidates[0]
    candidates: Dict[str, Any] = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "cdx_api": cdx_api,
        "cdx_api_candidates": cdx_api_candidates[:10],
        "queries_file": str(query_path),
        "sites": {},
    }
    fetched: Dict[str, Any] = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "queries_file": str(query_path),
        "sites": {},
    }

    for site, terms in sorted(site_terms.items()):
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        rows: list[dict[str, Any]] | None = None
        selected_cdx_api = cdx_api
        last_error: Exception | None = None
        for candidate_cdx_api in cdx_api_candidates:
            try:
                rows = commoncrawl_list_urls(session, candidate_cdx_api, site, limit=cc_limit)
                selected_cdx_api = candidate_cdx_api
                break
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                last_error = exc
                if status_code in {404, 429, 500, 502, 503, 504}:
                    continue
                raise
        if rows is None:
            raise last_error or RuntimeError(f"CommonCrawl query failed for {site}")
        scored: list[Dict[str, Any]] = []
        for row in rows:
            url = str(row.get("url") or "")
            score = score_archive_url(url, terms)
            if score <= 0:
                continue
            scored.append(
                {
                    "url": url,
                    "score": score,
                    "timestamp": row.get("timestamp"),
                    "mime": row.get("mime"),
                    "status": row.get("status"),
                }
            )
        scored.sort(key=lambda item: (item["score"], item.get("url", "")), reverse=True)
        candidates["sites"][site] = {
            "terms": terms[:50],
            "cdx_api": selected_cdx_api,
            "total_cc_rows": len(rows),
            "scored_rows": len(scored),
            "top": scored[:top_per_site],
        }

        if fetch_top > 0:
            fetched_rows: list[Dict[str, Any]] = []
            for item in scored[:fetch_top]:
                url = item.get("url")
                if not url:
                    continue
                try:
                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)
                    text = fetch_archive_text(session, str(url))
                except Exception as exc:
                    fetched_rows.append({"url": url, "error": str(exc)})
                    continue
                hits: list[str] = []
                lowered_text = text.lower()
                for term in terms[:50]:
                    if term.lower() in lowered_text:
                        hits.append(term)
                fetched_rows.append({"url": url, "hits": hits[:25], "text_snippet": text[:500]})
            fetched["sites"][site] = {"requested": fetch_top, "fetched": len(fetched_rows), "rows": fetched_rows}

    return with_adapter_metadata(
        {
            "status": "success",
            "queries_file": str(query_path),
            "candidates": candidates,
            "fetched": fetched if fetch_top > 0 else None,
        },
        operation="discover_seeded_commoncrawl",
        backend_available=True,
        implementation_status="implemented",
    )


def _write_bytes(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def _default_download_path(url: str, output_dir: Optional[str | Path]) -> Path:
    target_dir = Path(output_dir) if output_dir else Path("research_results/documents/raw")
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".pdf" if ".pdf" in str(url or "").lower() else ".bin"
    filename = f"{abs(hash(url))}{suffix}"
    return target_dir / filename


def _build_pdf_search_query(url: str) -> str:
    filename = re.sub(r"[?#].*$", "", str(url or "").split("/")[-1])
    if filename:
        return f"\"{filename}\" filetype:pdf"
    domain = _normalize_domain(url)
    return f"site:{domain} filetype:pdf" if domain else "filetype:pdf"


def _try_playwright_download(url: str, dest: Path, timeout_ms: int = 90000) -> Dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {"status": "unavailable", "saved": False, "note": "playwright not available"}

    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=user_agent)
            page = context.new_page()
            try:
                response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception as exc:
                context.close()
                browser.close()
                return {"status": "error", "saved": False, "note": f"goto failed: {exc}"}

            try:
                body = response.body() if response else b""
            except Exception:
                body = b""

            content_type = (response.headers.get("content-type") if response else "") or ""
            if ("application/pdf" in content_type.lower()) or _looks_like_pdf_bytes(body):
                _write_bytes(dest, body)
                context.close()
                browser.close()
                return {"status": "success", "saved": True, "note": "saved from playwright response", "content_type": content_type}

            try:
                locator = page.locator("a[href$='.pdf'], a[href*='.pdf']").first
                if locator.count() > 0:
                    href = locator.get_attribute("href")
                    if href:
                        pdf_url = page.url.rstrip("/") + href if href.startswith("/") else href
                        response = page.goto(pdf_url, wait_until="networkidle", timeout=timeout_ms)
                        body = response.body() if response else b""
                        content_type = (response.headers.get("content-type") if response else "") or ""
                        if ("application/pdf" in content_type.lower()) or _looks_like_pdf_bytes(body):
                            _write_bytes(dest, body)
                            context.close()
                            browser.close()
                            return {"status": "success", "saved": True, "note": f"followed pdf link {pdf_url}", "content_type": content_type, "final_url": pdf_url}
            except Exception:
                pass

            if body:
                _write_bytes(dest, body)
            context.close()
            browser.close()
            return {"status": "non_pdf", "saved": False, "note": f"not a PDF ({content_type or 'unknown'})", "content_type": content_type}
    except Exception as exc:
        return {"status": "error", "saved": False, "note": f"playwright error: {exc}"}


def download_url(
    url: str,
    *,
    output_path: Optional[str | Path] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    destination = Path(output_path) if output_path else _default_download_path(url, None)
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        data = response.content
        _write_bytes(destination, data)
        content_type = (response.headers.get("content-type") or "").lower()
        is_pdf = ("application/pdf" in content_type) or _looks_like_pdf_bytes(data)
        return with_adapter_metadata(
            {
                "url": url,
                "final_url": response.url,
                "saved_path": str(destination),
                "content_type": content_type or "unknown",
                "file_size": len(data),
                "status": "success" if is_pdf else "non_pdf",
                "recovery_strategy": "direct",
                "error": "",
                "is_pdf": is_pdf,
            },
            operation="download_url",
            backend_available=True,
            implementation_status="implemented",
        )
    except Exception as exc:
        return with_adapter_metadata(
            {
                "url": url,
                "final_url": url,
                "saved_path": str(destination),
                "content_type": "",
                "file_size": 0,
                "status": "error",
                "recovery_strategy": "direct",
                "error": str(exc),
                "is_pdf": False,
            },
            operation="download_url",
            backend_available=True,
            implementation_status="error",
        )


def download_with_recovery(
    url: str,
    *,
    output_path: Optional[str | Path] = None,
    timeout: int = 30,
    use_playwright: bool = True,
    use_search_fallback: bool = True,
) -> Dict[str, Any]:
    destination = Path(output_path) if output_path else _default_download_path(url, None)
    direct = download_url(url, output_path=destination, timeout=timeout)
    if direct.get("status") == "success" and direct.get("is_pdf"):
        return direct

    if use_playwright:
        playwright_result = _try_playwright_download(url, destination)
        if playwright_result.get("saved"):
            payload = {
                **direct,
                "saved_path": str(destination),
                "status": "success",
                "recovery_strategy": "playwright",
                "content_type": playwright_result.get("content_type") or direct.get("content_type") or "application/pdf",
                "file_size": destination.stat().st_size if destination.exists() else 0,
                "error": "",
            }
            return with_adapter_metadata(payload, operation="download_with_recovery", backend_available=True, implementation_status="implemented")

    if use_search_fallback:
        query = _build_pdf_search_query(url)
        candidates = search_brave_web(query, max_results=10)
        rate_limit_delay = float(os.environ.get("BRAVE_RATE_LIMIT_DELAY", "0.5"))
        for candidate in candidates[:6]:
            candidate_url = str(candidate.get("url") or "")
            if not candidate_url:
                continue
            recovered = download_url(candidate_url, output_path=destination, timeout=timeout)
            if recovered.get("status") == "success" and recovered.get("is_pdf"):
                payload = {
                    **recovered,
                    "url": url,
                    "recovery_strategy": "search_fallback",
                }
                return with_adapter_metadata(payload, operation="download_with_recovery", backend_available=True, implementation_status="implemented")
            try:
                time.sleep(rate_limit_delay)
            except Exception:
                pass

    payload = {
        **direct,
        "saved_path": str(destination),
        "status": "error" if direct.get("status") == "error" else "unrecovered",
        "recovery_strategy": "none",
    }
    return with_adapter_metadata(payload, operation="download_with_recovery", backend_available=True, implementation_status="implemented")


def recover_manifest_downloads(
    manifest_path: str | Path,
    *,
    min_pdf_size: int = 512,
    output_dir: Optional[str | Path] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    path = Path(manifest_path)
    if not path.exists():
        return with_adapter_metadata(
            {"status": "error", "error": "manifest_not_found", "manifest_path": str(path), "recovered": 0, "results": []},
            operation="recover_manifest_downloads",
            backend_available=True,
            implementation_status="error",
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    downloads = payload.get("downloads", []) if isinstance(payload, dict) else []
    results: List[Dict[str, Any]] = []
    recovered = 0
    raw_output_dir = Path(output_dir) if output_dir else path.parent / "raw"
    raw_output_dir.mkdir(parents=True, exist_ok=True)

    for item in downloads:
        if not isinstance(item, dict):
            continue
        filepath = item.get("filepath") or item.get("saved_path")
        url = str(item.get("url") or "")
        content_type = str(item.get("content_type") or "").lower()
        file_size = int(item.get("file_size") or 0)
        file_exists = bool(filepath) and Path(str(filepath)).exists()
        needs_recovery = (not file_exists) or ("pdf" not in content_type) or file_size < min_pdf_size
        if not needs_recovery or not url:
            continue

        dest = Path(str(filepath)) if filepath else _default_download_path(url, raw_output_dir)
        result = download_with_recovery(url, output_path=dest, timeout=timeout)
        results.append(result)
        if result.get("status") == "success":
            item["filepath"] = str(dest)
            item["saved_path"] = str(dest)
            item["download_date"] = datetime.now().isoformat()
            item["file_size"] = dest.stat().st_size if dest.exists() else 0
            item["content_type"] = str(result.get("content_type") or "application/pdf")
            recovered += 1

    if isinstance(payload, dict):
        payload["downloads"] = downloads
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return with_adapter_metadata(
        {
            "status": "success",
            "manifest_path": str(path),
            "recovered": recovered,
            "results": results,
        },
        operation="recover_manifest_downloads",
        backend_available=True,
        implementation_status="implemented",
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

    normalized = {
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
    return with_adapter_metadata(
        normalized,
        operation=f"search_{source_type}",
        backend_available=True,
        implementation_status="normalized",
        extra_metadata={
            "query": query,
            "source_type": source_type,
            "engine": engine,
            "published_date": published_date,
            "domain": domain,
            "score": score_value,
        },
    )


def _normalize_scrape_result(result: Any, source_type: str) -> Dict[str, Any]:
    metadata = _coerce_value(result, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    method_used = _coerce_value(result, "method_used", None)
    method_name = getattr(method_used, "value", method_used)
    text = str(_coerce_value(result, "text", "") or "")
    content = text or str(_coerce_value(result, "content", "") or "")
    url = str(_coerce_value(result, "url", "") or "")

    normalized = {
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
    return with_adapter_metadata(
        normalized,
        operation=f"scrape_{source_type}",
        backend_available=True,
        implementation_status="normalized",
        extra_metadata={
            "source_type": source_type,
            "domain": _normalize_domain(url),
            "success": bool(_coerce_value(result, "success", False)),
        },
    )


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
            _normalize_search_item(
                {
                    **item,
                    "snippet": item.get("description", ""),
                    "engine": item.get("engine", "brave"),
                    "published_date": item.get("published_date", item.get("age", "")),
                    "metadata": {
                        "language": item.get("language", ""),
                        "age": item.get("published_date", item.get("age", "")),
                    },
                },
                "brave_search",
                query=query,
            )
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
        return with_adapter_metadata(
            {
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
            },
            operation="scrape_web_scrape",
            backend_available=False,
            degraded_reason="UnifiedWebScraper unavailable",
            implementation_status="unavailable",
            extra_metadata={
                "source_type": "web_scrape",
                "domain": _normalize_domain(url),
                "success": False,
            },
        )

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

    if inspect.isawaitable(results):
        try:
            results = asyncio.run(results)
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
    "discover_seeded_commoncrawl",
    "fetch_archive_text",
    "fetch_commoncrawl_latest_index",
    "load_seeded_queries",
    "normalize_site",
    "parse_seeded_query",
    "QuerySpec",
    "score_archive_url",
    "search_multi_engine_web",
    "scrape_web_content",
    "scrape_archived_domain",
    "evaluate_scraped_content",
]
