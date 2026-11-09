#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from complaint_generator.email_agentic_search import search_email_corpus_agentic


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an agentic search over the Gmail DuckDB/Parquet corpus.")
    parser.add_argument("--index-path", required=True, help="Path to email_corpus.duckdb, email_messages.parquet, or the containing index directory.")
    parser.add_argument("--complaint-query", default="", help="Primary complaint-oriented search prompt.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Repeatable complaint keyword or phrase.")
    parser.add_argument("--seed-term", action="append", default=[], help="Repeatable explicit search seed, for example 'clackamas county'.")
    parser.add_argument("--seed-participant", action="append", default=[], help="Repeatable participant or email address seed.")
    parser.add_argument("--required-participant-domain", action="append", default=[], help="Repeatable required participant domain filter, for example 'clackamas.us'.")
    parser.add_argument("--min-seed-phrase-matches", type=int, default=1, help="Require at least this many distinct seed phrase matches per email.")
    parser.add_argument("--result-limit", type=int, default=150, help="Maximum ranked email hits to keep.")
    parser.add_argument("--chain-limit", type=int, default=20, help="Maximum thread/chain summaries to keep.")
    parser.add_argument("--output-dir", default=None, help="Optional output directory for search artifacts.")
    parser.add_argument("--no-graphrag", action="store_true", help="Skip the focused GraphRAG bundle for matched emails.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = search_email_corpus_agentic(
        index_path=Path(args.index_path),
        complaint_query=str(args.complaint_query or ""),
        complaint_keywords=list(args.complaint_keyword or []),
        seed_terms=list(args.seed_term or []),
        seed_participants=list(args.seed_participant or []),
        required_participant_domains=list(args.required_participant_domain or []),
        min_seed_phrase_matches=int(args.min_seed_phrase_matches or 1),
        result_limit=int(args.result_limit or 150),
        chain_limit=int(args.chain_limit or 20),
        output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
        emit_graphrag=not bool(args.no_graphrag),
    )
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
