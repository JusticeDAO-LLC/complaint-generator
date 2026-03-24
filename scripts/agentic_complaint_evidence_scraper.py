#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from complaint_generator.agentic_evidence_download import run_agentic_evidence_download


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Agentically search and download complaint-relevant web evidence."
    )
    parser.add_argument("--complaint-query", required=True, help="Free-text complaint description.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Repeatable complaint keyword or phrase.")
    parser.add_argument("--complaint-keyword-file", action="append", default=[], help="Path to newline-delimited complaint keywords or phrases.")
    parser.add_argument("--domain-seed", action="append", default=[], help="Optional site/domain to prioritize.")
    parser.add_argument("--seed-url", action="append", default=[], help="Explicit URL seed to scrape directly.")
    parser.add_argument("--output-dir", default=None, help="Directory to store downloaded evidence artifacts.")
    parser.add_argument("--max-queries", type=int, default=6, help="Maximum generated query variants.")
    parser.add_argument("--max-search-results", type=int, default=8, help="Maximum search hits per query.")
    parser.add_argument("--max-downloads", type=int, default=5, help="Maximum scraped/downloaded artifacts to keep.")
    parser.add_argument("--min-search-score", type=float, default=2.0, help="Minimum score required to keep a search hit.")
    parser.add_argument("--min-download-score", type=float, default=3.0, help="Minimum score required after scraping.")
    parser.add_argument("--scrape-timeout", type=int, default=30, help="Per-page scrape timeout in seconds.")
    parser.add_argument("--quality-domain", default="caselaw", help="Validation domain for scrape quality scoring.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run_agentic_evidence_download(
        complaint_query=args.complaint_query,
        complaint_keywords=args.complaint_keyword,
        complaint_keyword_files=args.complaint_keyword_file,
        domain_seeds=args.domain_seed,
        seed_urls=args.seed_url,
        output_dir=args.output_dir,
        max_queries=args.max_queries,
        max_search_results=args.max_search_results,
        max_downloads=args.max_downloads,
        min_search_score=args.min_search_score,
        min_download_score=args.min_download_score,
        scrape_timeout=args.scrape_timeout,
        quality_domain=args.quality_domain,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
