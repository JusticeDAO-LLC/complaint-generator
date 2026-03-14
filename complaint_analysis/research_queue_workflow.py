"""
Shared queue-building, filtering, and downloading helpers for research workflows.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from integrations.ipfs_datasets.search import download_with_recovery

EXCLUDE_DOMAIN_SUBSTR = [
    "myworkdayjobs.com",
    "govdelivery.com",
    "employeesearch.",
    "google.com",
    "youtu.be",
    "youtube.com",
    "t.co",
    "goo.gl",
    "berkeley.edu",
    "schema.org",
    "ogp.me",
    "wikipedia.org",
    "api.w.org",
    "s.w.org",
    "rdfs.org",
    "gmpg.org",
    "drupal.org",
    "github.com",
    "cloudfront.net",
    "tinyurl.com",
    "example.com",
    "x.com",
]

MANUAL_INCLUDE_DOMAINS = [
    "quantumresidential.com",
    "www.quantumresidential.com",
]

COMMON_PATHS = [
    "/about",
    "/about-us",
    "/who-we-are",
    "/mission",
    "/leadership",
    "/programs",
    "/services",
    "/resources",
    "/publications",
    "/reports",
    "/documents",
    "/policies",
    "/policy",
    "/nondiscrimination",
    "/non-discrimination",
    "/civil-rights",
    "/fair-housing",
    "/fairhousing",
    "/complaints",
    "/grants",
    "/contracts",
    "/rfp",
    "/rfq",
    "/procurement",
]

NOISE_DOMAIN_SUBSTR = [
    "tiktok.com",
    "tiktokv.",
    "instagram.com",
    "facebook.com",
    "fbcdn.",
    "linkedin.com",
    "threads.net",
    "bsky.app",
    "twitter.com",
    "t.co",
    "twimg.com",
    "x.com",
    "youtu.be",
    "youtube.com",
    "google.com",
    "gstatic.com",
    "googleusercontent.com",
    "googletagmanager",
    "google-analytics",
    "doubleclick.net",
    "googleapis.com",
    "schema.org",
    "ogp.me",
    "rdfs.org",
    "gmpg.org",
    "xmlns.com",
    "w3.org",
    "api.w.org",
    "s.w.org",
    "wordpress.org",
    "wordpress.com",
    "cloudfront.net",
    "fastly.net",
    "akamai",
    "jsdelivr.net",
    "stripe.com",
    "learnworlds.com",
    "thrillshare.com",
    "mycourse.app",
    "mouseflow.com",
    "heapanalytics.com",
    "adobedtm.com",
    "licdn.com",
    "confiant-integrations.net",
    "slideshare.net",
    "bonfire.com",
    "cbs8.com",
    "wnycstudios.org",
    "flickr.com",
    "wikimedia.org",
    "wikipedia.org",
    "cdn.",
    "static.",
    "assets.",
    "tinyurl.com",
    "goo.gl",
    "bit.ly",
    "example.com",
]

DEFAULT_KEEP_DOMAINS = {
    "oregonbuys.gov",
    "sos.oregon.gov",
}


@dataclass(frozen=True)
class QueueItem:
    domain: str
    score: int
    seed_urls: list[str]
    guessed_urls: list[str]
    evidence_urls: list[str]


@dataclass(frozen=True)
class FilterDecision:
    keep: bool
    reason: str


@dataclass
class ManifestRow:
    domain: str
    url: str
    final_url: str
    status: str
    http_status: int
    content_type: str
    bytes: int
    saved_path: str
    error: str


def uniq(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _norm_domain(domain: str) -> str:
    d = (domain or "").strip().lower().replace("\x00", "")
    if "://" in d:
        try:
            d = urlparse(d).netloc.lower()
        except Exception:
            return ""
    return d.split("/")[0].strip()


def domain_is_valid(domain: str) -> bool:
    d = _norm_domain(domain)
    if not d or len(d) > 253:
        return False
    if any(ch for ch in d if not (ch.isalnum() or ch in {".", "-"})):
        return False
    labels = d.split(".")
    if any((not lab) or len(lab) > 63 for lab in labels):
        return False
    tld = labels[-1]
    common_gtlds = {"com", "org", "net", "edu", "gov", "us", "info", "io", "co", "biz", "me"}
    return (len(tld) == 2 and tld.isalpha()) or tld in common_gtlds


def domain_ok(domain: str, exclude_domain_substr: list[str] | None = None) -> bool:
    d = _norm_domain(domain)
    if not d or not domain_is_valid(d):
        return False
    blocked = exclude_domain_substr or EXCLUDE_DOMAIN_SUBSTR
    return not any(part in d for part in blocked)


def is_non_gov(domain: str) -> bool:
    d = _norm_domain(domain)
    return not (d.endswith(".gov") or d.endswith(".us") or d.endswith(".state.or.us") or d.endswith(".oregon.gov"))


def is_govish(domain: str) -> bool:
    d = _norm_domain(domain)
    return d.endswith(".gov") or d.endswith(".us") or d.endswith(".state.or.us") or d.endswith(".oregon.gov")


def decide_keep(domain: str, *, keep_domains: set[str], keep_gov: bool) -> FilterDecision:
    d = _norm_domain(domain)
    if not d:
        return FilterDecision(False, "empty_domain")
    if d in keep_domains:
        return FilterDecision(True, "allowlist")
    if not keep_gov and is_govish(d):
        return FilterDecision(False, "gov_filtered")
    for item in NOISE_DOMAIN_SUBSTR:
        if item in d:
            return FilterDecision(False, f"noise:{item}")
    if d.startswith("www.") and any(item in d for item in ["static", "assets", "cdn"]):
        return FilterDecision(False, "asset_host_pattern")
    return FilterDecision(True, "ok")


def safe_folder_name(name: str) -> str:
    normalized = _norm_domain(name)
    safe = "".join(ch for ch in normalized if ch.isalnum() or ch in {".", "-"})
    return safe[:200]


def safe_filename_from_url(url: str, content_type: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        base = parsed.netloc
    else:
        base = f"{parsed.netloc}_{path.replace('/', '_')}"
    base = base.replace("%", "_")
    if len(base) > 120:
        base = base[:120]
    suffix = Path(parsed.path).suffix
    if suffix:
        return base
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return base + ".pdf"
    if "msword" in ct:
        return base + ".doc"
    if "officedocument.wordprocessingml" in ct:
        return base + ".docx"
    if "officedocument.spreadsheetml" in ct:
        return base + ".xlsx"
    if "html" in ct:
        return base + ".html"
    return base + ".bin"


def same_domain(url: str, domain: str) -> bool:
    try:
        return _norm_domain(urlparse(url).netloc) == _norm_domain(domain)
    except Exception:
        return False


def build_download_queue(
    candidates_payload: dict[str, Any],
    *,
    manual_include_domains: list[str] | None = None,
    common_paths: list[str] | None = None,
) -> dict[str, Any]:
    candidates = candidates_payload.get("candidates", [])
    domain_candidates = [item for item in candidates if item.get("candidate_type") == "domain"]
    queue: list[QueueItem] = []
    queued_domains: set[str] = set()

    for item in domain_candidates:
        domain = _norm_domain(str(item.get("domain") or item.get("candidate") or ""))
        if not domain_ok(domain):
            continue
        if domain in queued_domains:
            continue
        score = int(item.get("score", 0) or 0)
        if not is_non_gov(domain) and score < 35:
            continue
        evidence_urls = [str(ev.get("url")) for ev in (item.get("evidence") or []) if isinstance(ev, dict) and ev.get("url")]
        seed_urls = uniq([f"https://{domain}", f"http://{domain}"])
        guessed_urls: list[str] = []
        for base in seed_urls:
            for path in (common_paths or COMMON_PATHS):
                guessed_urls.append(base.rstrip("/") + path)
        queue.append(
            QueueItem(
                domain=domain,
                score=score,
                seed_urls=seed_urls,
                guessed_urls=uniq(guessed_urls),
                evidence_urls=uniq(evidence_urls),
            )
        )
        queued_domains.add(domain)

    for domain in manual_include_domains or MANUAL_INCLUDE_DOMAINS:
        normalized = _norm_domain(domain)
        if normalized in queued_domains or not domain_ok(normalized):
            continue
        seed_urls = uniq([f"https://{normalized}", f"http://{normalized}"])
        guessed_urls: list[str] = []
        for base in seed_urls:
            for path in (common_paths or COMMON_PATHS):
                guessed_urls.append(base.rstrip("/") + path)
        queue.append(
            QueueItem(
                domain=normalized,
                score=50,
                seed_urls=seed_urls,
                guessed_urls=uniq(guessed_urls),
                evidence_urls=[],
            )
        )
        queued_domains.add(normalized)

    queue.sort(key=lambda item: item.score, reverse=True)
    return {
        "domain_count": len(queue),
        "notes": "Queue is conservative; verify relevance before large-scale crawling.",
        "items": [asdict(item) for item in queue],
    }


def filter_download_queue(
    queue_payload: dict[str, Any],
    *,
    keep_domains: set[str] | None = None,
    keep_gov: bool = False,
    min_score: int = 50,
    max_domains: int = 150,
) -> tuple[dict[str, Any], dict[str, Any]]:
    items = queue_payload.get("items", [])
    kept: list[dict[str, Any]] = []
    dropped_by_reason: Counter[str] = Counter()
    dropped_examples: dict[str, list[str]] = defaultdict(list)
    allowlist = set(DEFAULT_KEEP_DOMAINS)
    allowlist.update({_norm_domain(item) for item in (keep_domains or set()) if _norm_domain(item)})

    for item in items:
        if not isinstance(item, dict):
            dropped_by_reason["bad_item"] += 1
            continue
        domain = str(item.get("domain") or "")
        decision = decide_keep(domain, keep_domains=allowlist, keep_gov=keep_gov)
        if not decision.keep:
            dropped_by_reason[decision.reason] += 1
            if len(dropped_examples[decision.reason]) < 10:
                dropped_examples[decision.reason].append(_norm_domain(domain))
            continue
        score = int(item.get("score") or 0)
        if score < int(min_score):
            dropped_by_reason["score_below_min"] += 1
            if len(dropped_examples["score_below_min"]) < 10:
                dropped_examples["score_below_min"].append(_norm_domain(domain))
            continue
        kept.append(item)

    kept.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    kept = kept[: int(max_domains)]

    queue_out = {
        "domain_count": len(kept),
        "notes": "Filtered to reduce obvious social/media/CDN/tech-noise domains; verify relevance before crawling.",
        "filters": {
            "keep_gov": bool(keep_gov),
            "min_score": int(min_score),
            "max_domains": int(max_domains),
            "allowlist": sorted(allowlist),
            "noise_domain_substr": NOISE_DOMAIN_SUBSTR,
        },
        "items": kept,
    }
    summary = {
        "input_domain_count": len(items),
        "output_domain_count": len(kept),
        "dropped_domain_count": len(items) - len(kept),
        "dropped_by_reason": dict(dropped_by_reason.most_common()),
        "dropped_examples": dict(dropped_examples),
    }
    return queue_out, summary


def write_manifest(json_path: Path, csv_path: Path, rows: list[ManifestRow]) -> None:
    json_path.write_text(json.dumps([asdict(row) for row in rows], indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["domain", "url", "final_url", "status", "http_status", "content_type", "bytes", "saved_path", "error"])
        for row in rows:
            writer.writerow(
                [row.domain, row.url, row.final_url, row.status, row.http_status, row.content_type, row.bytes, row.saved_path, row.error]
            )


def download_queue(
    queue_payload: dict[str, Any],
    *,
    out_dir: str | Path,
    manifest_json: str | Path,
    manifest_csv: str | Path,
    max_domains: int = 15,
    max_urls_per_domain: int = 25,
    include_guessed: bool = False,
    timeout: int = 30,
) -> dict[str, Any]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    json_path = Path(manifest_json)
    csv_path = Path(manifest_csv)

    rows: list[ManifestRow] = []
    seen_urls: set[str] = set()
    downloads_ok = 0
    domains_processed = 0

    for item in queue_payload.get("items", []):
        if domains_processed >= max_domains:
            break
        domain = _norm_domain(str(item.get("domain") or ""))
        if not domain:
            continue
        evidence_urls = list(item.get("evidence_urls", []) or [])
        urls: list[str] = []
        urls.extend(evidence_urls)
        urls.extend(item.get("seed_urls", []) or [])
        if include_guessed:
            urls.extend(item.get("guessed_urls", []) or [])
        deduped = uniq([str(url) for url in urls if url])
        to_fetch = deduped[:max_urls_per_domain]
        if not to_fetch:
            continue

        domain_dir = out_path / (safe_folder_name(domain) or "unknown")
        domain_dir.mkdir(parents=True, exist_ok=True)
        domains_processed += 1

        for url in to_fetch:
            if url in seen_urls:
                continue
            if include_guessed and (url not in evidence_urls) and not same_domain(url, domain):
                rows.append(ManifestRow(domain, url, url, "skipped", 0, "", 0, "", "cross_domain"))
                seen_urls.add(url)
                continue

            result = download_with_recovery(url, output_path=domain_dir / safe_filename_from_url(url, ""), timeout=timeout)
            final_url = str(result.get("final_url") or url)
            status = str(result.get("status") or "error")
            content_type = str(result.get("content_type") or "")
            saved_path = str(result.get("saved_path") or "")
            file_size = int(result.get("file_size") or 0)
            http_status = int(result.get("http_status") or 0)
            error = str(result.get("error") or "")

            if status == "success":
                downloads_ok += 1
            rows.append(ManifestRow(domain, url, final_url, status, http_status, content_type, file_size, saved_path, error))
            seen_urls.add(url)

    write_manifest(json_path, csv_path, rows)
    return {
        "domains_processed": domains_processed,
        "ok_downloads": downloads_ok,
        "manifest_rows": len(rows),
        "manifest_json": str(json_path),
        "manifest_csv": str(csv_path),
    }


__all__ = [
    "COMMON_PATHS",
    "DEFAULT_KEEP_DOMAINS",
    "EXCLUDE_DOMAIN_SUBSTR",
    "FilterDecision",
    "MANUAL_INCLUDE_DOMAINS",
    "ManifestRow",
    "NOISE_DOMAIN_SUBSTR",
    "QueueItem",
    "build_download_queue",
    "decide_keep",
    "domain_is_valid",
    "domain_ok",
    "download_queue",
    "filter_download_queue",
    "is_govish",
    "is_non_gov",
    "safe_filename_from_url",
    "safe_folder_name",
    "same_domain",
    "uniq",
    "write_manifest",
]
