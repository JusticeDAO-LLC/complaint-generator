"""
Shared bootstrap helpers for candidate extraction and outbound document discovery.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urldefrag, urljoin, urlparse

TEXT_FILE_EXTS = {".txt", ".md", ".html", ".htm", ".aspx"}
ASSET_EXTS = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".map"}
RELATIONSHIP_TERMS = [
    "partner",
    "partnership",
    "in partnership",
    "in coordination",
    "collaborat",
    "administered by",
    "managed by",
    "operated by",
    "run by",
    "contractor",
    "vendor",
    "consultant",
    "provider",
    "service provider",
    "subrecipient",
    "sub-recipient",
    "subaward",
    "sub-award",
    "pass-through",
    "grant agreement",
    "mou",
    "memorandum of understanding",
    "training vendor",
    "facilitated by",
    "curriculum",
    "application portal",
    "intake",
    "screening",
    "waitlist",
    "wait list",
]
ORG_SUFFIXES = [
    "Inc",
    "Incorporated",
    "LLC",
    "L.L.C",
    "Ltd",
    "Limited",
    "Co",
    "Company",
    "Corporation",
    "Corp",
    "Foundation",
    "Association",
    "Coalition",
    "Council",
    "Network",
    "Partners",
    "Partnership",
    "Services",
    "Service",
    "Center",
    "Centre",
    "Institute",
    "Initiative",
    "Alliance",
    "Agency",
    "Authority",
]
IGNORE_DOMAINS_SUBSTR = [
    "google-analytics",
    "googletagmanager",
    "gtranslate",
    "fontawesome",
    "cloudflare",
    "cdnjs",
    "code.jquery.com",
    "ns.adobe.com",
    "w3.org",
    "purl.org",
    "siteimprove",
    "getsitecontrol",
    "bestvpn.org",
    "browsehappy.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "gstatic.com",
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "goo.gl",
    "t.co",
    "google.com",
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
KEEP_GOV_DOMAINS = {"oregonbuys.gov", "sos.oregon.gov", "www.hud.gov", "hud.gov"}
GOV_NAME_HINTS = [
    "department of",
    "state of",
    "oregon",
    "county",
    "housing authority",
    "bureau of",
    "division of",
    "administrative services",
    "secretary of state",
]
DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".txt", ".csv"}
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
HREF_SRC_RE = re.compile(r"(?i)\b(?:href|src)\s*=\s*['\"]([^'\"]+)['\"]")
RAW_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


@dataclass
class Candidate:
    candidate_type: str
    candidate: str
    domain: str
    score: int
    mentions: int
    sources: list[str]
    evidence: list[dict]


@dataclass(frozen=True)
class EvidenceRow:
    source_saved_path: str
    source_url: str
    candidate_url: str
    reason: str
    score: int


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join(self._chunks)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()


def normalize_url(url: str) -> str:
    cleaned = (url or "").strip().replace("\x00", "").strip("\"'()[]{}<>.,;\n\r\t ")
    cleaned, _fragment = urldefrag(cleaned)
    return cleaned


def is_asset_url(url: str) -> bool:
    try:
        ext = Path(urlparse(url).path.lower()).suffix
    except Exception:
        return True
    return ext in ASSET_EXTS


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("\x00", "").strip()
    except Exception:
        return ""


def looks_like_ignored_domain(domain: str) -> bool:
    return any(item in (domain or "").lower() for item in IGNORE_DOMAINS_SUBSTR)


def is_government_domain(domain: str) -> bool:
    d = (domain or "").lower()
    return d.endswith(".gov") or d.endswith(".us") or d.endswith(".state.or.us") or d.endswith(".oregon.gov")


def org_name_is_noise(name: str) -> bool:
    normalized = normalize_whitespace(name)
    lowered = normalized.lower()
    if len(normalized) < 6 or len(normalized) > 80:
        return True
    return any(hint in lowered for hint in ["menu", "home", "address", "skip to", "explore", "search"])


def org_name_is_gov_like(name: str) -> bool:
    lowered = normalize_whitespace(name).lower()
    return any(hint in lowered for hint in GOV_NAME_HINTS)


def extract_urls(raw: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in URL_RE.findall(raw or ""):
        normalized = normalize_url(match)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def extract_text_from_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".html", ".htm", ".aspx"}:
        parser = TextExtractor()
        try:
            parser.feed(raw)
            return parser.text()
        except Exception:
            return raw
    return raw


def find_org_name_candidates(text: str) -> list[str]:
    suffix_group = "|".join(re.escape(item) for item in ORG_SUFFIXES)
    pattern = re.compile(rf"\b([A-Z][A-Za-z&.,'\-]+(?:\s+[A-Z][A-Za-z&.,'\-]+){{0,6}}\s+(?:{suffix_group})\.?)\b")
    seen: set[str] = set()
    out: list[str] = []
    for match in pattern.findall(text or ""):
        candidate = normalize_whitespace(match.strip().rstrip(",.;"))
        if org_name_is_noise(candidate):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def context_snippets(text: str, needle: str, window: int = 160, max_snips: int = 3) -> list[str]:
    out: list[str] = []
    start = 0
    haystack = text or ""
    while len(out) < max_snips:
        idx = haystack.lower().find((needle or "").lower(), start)
        if idx == -1:
            break
        left = max(0, idx - window)
        right = min(len(haystack), idx + len(needle) + window)
        snippet = re.sub(r"\s+", " ", haystack[left:right].replace("\n", " ").replace("\r", " ")).strip()
        out.append(snippet)
        start = idx + len(needle)
    return out


def relationship_score(text_lower: str) -> int:
    return sum(1 for term in RELATIONSHIP_TERMS if term in (text_lower or ""))


def iter_corpus_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in TEXT_FILE_EXTS or path.suffix == "":
                yield path


def extract_third_party_candidates_from_corpus(roots: Iterable[Path]) -> dict:
    domain_mentions: Counter[str] = Counter()
    domain_sources: defaultdict[str, set[str]] = defaultdict(set)
    domain_evidence: defaultdict[str, list[dict]] = defaultdict(list)
    name_mentions: Counter[str] = Counter()
    name_sources: defaultdict[str, set[str]] = defaultdict(set)
    name_evidence: defaultdict[str, list[dict]] = defaultdict(list)

    processed = 0
    for path in iter_corpus_files(roots):
        try:
            text_raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        processed += 1
        urls = extract_urls(text_raw)
        text = extract_text_from_file(path)
        text_lower = text.lower()
        rel_sig = relationship_score(text_lower)

        for url in urls:
            if not url.lower().startswith(("http://", "https://")) or is_asset_url(url):
                continue
            domain = domain_of(url)
            if not domain or looks_like_ignored_domain(domain):
                continue
            domain_mentions[domain] += 1
            domain_sources[domain].add(str(path))
            if len(domain_evidence[domain]) < 8:
                domain_evidence[domain].append(
                    {
                        "source": str(path),
                        "url": url,
                        "relationship_signal_count": rel_sig,
                        "snippets": context_snippets(text, domain, window=140, max_snips=2),
                    }
                )

        for name in find_org_name_candidates(text):
            key = name.lower()
            name_mentions[key] += 1
            name_sources[key].add(str(path))
            if len(name_evidence[key]) < 8:
                name_evidence[key].append(
                    {
                        "source": str(path),
                        "name": name,
                        "relationship_signal_count": rel_sig,
                        "snippets": context_snippets(text, name, window=160, max_snips=2),
                    }
                )

    candidates: list[Candidate] = []
    for domain, mentions in domain_mentions.most_common():
        if looks_like_ignored_domain(domain):
            continue
        gov = is_government_domain(domain)
        if gov and domain not in KEEP_GOV_DOMAINS:
            continue
        sources = sorted(domain_sources[domain])
        score = min(mentions, 30) + min(len(sources) * 2, 40)
        if not gov:
            score += 10
        score += sum(min(item.get("relationship_signal_count", 0), 5) for item in domain_evidence[domain])
        candidates.append(Candidate("domain", domain, domain, score, mentions, sources[:50], domain_evidence[domain]))

    for key, mentions in name_mentions.most_common():
        display = name_evidence[key][0]["name"] if name_evidence[key] else key
        if org_name_is_noise(display):
            continue
        sources = sorted(name_sources[key])
        score = min(mentions, 20) + min(len(sources) * 2, 30)
        score += sum(min(item.get("relationship_signal_count", 0), 5) for item in name_evidence[key])
        if org_name_is_gov_like(display):
            score -= 10
        candidates.append(Candidate("org_name", display, "", score, mentions, sources[:50], name_evidence[key]))

    candidates.sort(key=lambda item: item.score, reverse=True)
    return {
        "scanned_files": processed,
        "candidate_count": len(candidates),
        "notes": "Candidates are leads for due diligence; verify using source evidence.",
        "candidates": [asdict(item) for item in candidates],
    }


def write_candidates_csv(payload: dict, output_csv: Path) -> None:
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["candidate_type", "candidate", "domain", "score", "mentions", "source_count", "sample_sources"])
        for item in payload.get("candidates", [])[:500]:
            writer.writerow(
                [
                    item.get("candidate_type", ""),
                    item.get("candidate", ""),
                    item.get("domain", ""),
                    item.get("score", 0),
                    item.get("mentions", 0),
                    len(item.get("sources", []) or []),
                    " | ".join((item.get("sources", []) or [])[:5]),
                ]
            )


def load_manifest_rows(manifest_path: Path) -> list[dict]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    raise ValueError("Unsupported manifest format (expected a JSON list)")


def maybe_unwrap_google(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    host = (parsed.netloc or "").lower()
    if host not in {"www.google.com", "google.com"}:
        return url
    qs = parse_qs(parsed.query or "")
    candidate = qs.get("q", [""])[0] or qs.get("url", [""])[0]
    candidate = unquote(candidate or "")
    return candidate if candidate.startswith(("http://", "https://")) else url


def normalize_external_url(raw: str, base_url: str) -> str | None:
    raw = (raw or "").strip()
    if not raw or raw.lower().startswith(("mailto:", "tel:", "javascript:")):
        return None
    try:
        absolute = urljoin(base_url, raw)
        absolute, _fragment = urldefrag(absolute)
        absolute = maybe_unwrap_google(absolute)
        parsed = urlparse(absolute)
    except Exception:
        return None
    return absolute if parsed.scheme in {"http", "https"} else None


def is_quantum_domain(domain: str) -> bool:
    d = (domain or "").lower().strip()
    return d == "quantumresidential.com" or d.endswith(".quantumresidential.com")


def score_candidate_url(url: str) -> tuple[int, str] | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    path = (parsed.path or "").lower()
    qs = parse_qs(parsed.query or "")
    suffix = Path(path).suffix
    if suffix in DOC_EXTENSIONS:
        return (100, f"extension:{suffix}")
    joined_qs = "&".join(f"{key}={vals[0] if vals else ''}" for key, vals in qs.items()).lower()
    if "pdf" in path or "pdf" in joined_qs:
        return (80, "contains:pdf")
    if any(token in path for token in ["/download", "download/", "/attachment", "/uploads/"]):
        return (60, "path:downloadish")
    if any(key in qs for key in ["download", "attachment", "file", "filename", "document", "doc"]):
        return (60, "query:downloadish")
    return None


def extract_links(html_text: str) -> Iterable[str]:
    for match in HREF_SRC_RE.finditer(html_text or ""):
        yield match.group(1)
    for match in RAW_URL_RE.finditer(html_text or ""):
        yield match.group(0)


def extract_external_document_queue(rows: list[dict], *, max_candidates: int = 800) -> tuple[dict, dict]:
    evidence: list[EvidenceRow] = []
    candidates_by_domain: dict[str, dict[str, tuple[int, str]]] = defaultdict(dict)
    total_files = 0
    total_links_seen = 0

    for row in rows:
        if row.get("status") != "ok":
            continue
        saved_path = row.get("saved_path")
        base_url = row.get("final_url") or row.get("url")
        if not saved_path or not base_url:
            continue
        path = Path(saved_path)
        if not path.exists():
            continue
        content_type = (row.get("content_type") or "").lower()
        if "text/html" not in content_type and path.suffix.lower() not in {".html", ".htm"}:
            continue
        html = path.read_text("utf-8", errors="ignore")
        total_files += 1
        for raw in extract_links(html):
            total_links_seen += 1
            normalized = normalize_external_url(raw, str(base_url))
            if not normalized:
                continue
            domain = (urlparse(normalized).netloc or "").lower()
            if not domain or is_quantum_domain(domain):
                continue
            scored = score_candidate_url(normalized)
            if not scored:
                continue
            score, reason = scored
            existing = candidates_by_domain[domain].get(normalized)
            if existing is None or score > existing[0]:
                candidates_by_domain[domain][normalized] = (score, reason)
            evidence.append(EvidenceRow(str(saved_path), str(base_url), str(normalized), reason, score))

    unique_rows: list[tuple[str, str, int, str]] = []
    for domain, urls in candidates_by_domain.items():
        for url, (score, reason) in urls.items():
            unique_rows.append((domain, url, score, reason))
    unique_rows.sort(key=lambda row: (-row[2], row[0], row[1]))
    unique_rows = unique_rows[: max(0, int(max_candidates))]

    capped_by_domain: dict[str, list[str]] = defaultdict(list)
    for domain, url, _score, _reason in unique_rows:
        capped_by_domain[domain].append(url)

    queue = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "html_files_scanned": total_files,
            "raw_links_seen": total_links_seen,
            "unique_candidate_urls": sum(len(urls) for urls in capped_by_domain.values()),
            "candidate_domains": len(capped_by_domain),
        },
        "items": [
            {
                "domain": domain,
                "score": 100,
                "evidence_urls": urls,
                "seed_urls": [],
                "guessed_urls": [],
                "notes": "Extracted from Quantum Residential pages (outbound doc-like links)",
            }
            for domain, urls in sorted(capped_by_domain.items())
        ],
    }
    evidence_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": [asdict(item) for item in evidence],
    }
    return queue, evidence_payload


__all__ = [
    "Candidate",
    "EvidenceRow",
    "extract_external_document_queue",
    "extract_third_party_candidates_from_corpus",
    "iter_corpus_files",
    "load_manifest_rows",
    "write_candidates_csv",
]
