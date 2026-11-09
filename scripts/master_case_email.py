#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


from complaint_generator.email_agentic_search import search_email_corpus_agentic
from integrations.ipfs_datasets.legal_data import load_legal_symbol

build_email_graphrag_artifacts = load_legal_symbol("build_email_workspace_corpus", module="email_workspace")
canonical_email_corpus_paths = load_legal_symbol("canonical_email_corpus_paths", module="email_workspace")
search_email_graphrag_duckdb = load_legal_symbol("search_email_workspace_corpus", module="email_workspace")


REPO_ROOT = Path(__file__).resolve().parents[2]
MASTER_CORPUS = canonical_email_corpus_paths(repo_root=REPO_ROOT, case_slug="starworks5-master-case-email-import")
MASTER_MANIFEST_PATH = MASTER_CORPUS.manifest_path
MASTER_GRAPHRAG_DIR = MASTER_CORPUS.graphrag_dir
MASTER_DUCKDB_PATH = MASTER_CORPUS.duckdb_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search or rebuild the canonical merged case email corpus.")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild GraphRAG and DuckDB for the canonical merged master manifest.")
    parser.add_argument("--search-query", default="", help="BM25 search query to run against the canonical DuckDB index.")
    parser.add_argument("--search-limit", type=int, default=20, help="Maximum number of BM25 results to return.")
    parser.add_argument("--agentic-query", default="", help="Optional higher-level complaint query for agentic search over the canonical corpus.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Repeatable complaint keyword for agentic search.")
    parser.add_argument("--seed-term", action="append", default=[], help="Repeatable explicit seed phrase for agentic search.")
    parser.add_argument("--seed-participant", action="append", default=[], help="Repeatable participant or email address seed for agentic search.")
    parser.add_argument("--required-participant-domain", action="append", default=[], help="Repeatable participant domain filter for agentic search.")
    parser.add_argument("--result-limit", type=int, default=150, help="Maximum matched emails to keep in agentic search.")
    parser.add_argument("--chain-limit", type=int, default=20, help="Maximum thread summaries to keep in agentic search.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload: dict[str, object] = {
        "master_manifest_path": str(MASTER_MANIFEST_PATH),
        "master_duckdb_path": str(MASTER_DUCKDB_PATH),
    }
    if args.rebuild:
        payload["graphrag_summary"] = build_email_graphrag_artifacts(
            manifest_path=MASTER_MANIFEST_PATH,
            include_attachment_text_in_search=True,
        )
    if args.search_query:
        payload["duckdb_search"] = search_email_graphrag_duckdb(
            index_path=MASTER_DUCKDB_PATH,
            query=str(args.search_query or ""),
            limit=int(args.search_limit or 20),
        )
    if args.agentic_query:
        payload["agentic_search"] = search_email_corpus_agentic(
            index_path=MASTER_DUCKDB_PATH,
            complaint_query=str(args.agentic_query or ""),
            complaint_keywords=list(args.complaint_keyword or []),
            seed_terms=list(args.seed_term or []),
            seed_participants=list(args.seed_participant or []),
            required_participant_domains=list(args.required_participant_domain or []),
            result_limit=int(args.result_limit or 150),
            chain_limit=int(args.chain_limit or 20),
            emit_graphrag=True,
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
