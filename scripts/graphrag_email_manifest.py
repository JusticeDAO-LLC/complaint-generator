#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json


from complaint_generator.email_graphrag import (
    build_email_graphrag_artifacts,
    search_email_graphrag_duckdb,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build GraphRAG artifacts for an imported email evidence manifest.")
    parser.add_argument("manifest_path", help="Path to email_import_manifest.json")
    parser.add_argument("--output-dir", default=None, help="Optional output directory for graphrag artifacts.")
    parser.add_argument("--skip-duckdb-index", action="store_true", help="Skip DuckDB email corpus indexing.")
    parser.add_argument("--append-duckdb-index", action="store_true", help="Append this manifest into an existing DuckDB corpus instead of rebuilding it.")
    parser.add_argument("--search-query", default="", help="Optional DuckDB-backed search query to run after indexing.")
    parser.add_argument("--search-limit", type=int, default=20, help="Maximum number of DuckDB search results to return.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = build_email_graphrag_artifacts(
        manifest_path=args.manifest_path,
        output_dir=args.output_dir,
        emit_duckdb_index=not args.skip_duckdb_index,
        append_duckdb_index=args.append_duckdb_index,
    )
    payload: dict[str, object] = {"graphrag_summary": summary}
    if args.search_query:
        duckdb_summary = (summary.get("duckdb_index") or {}) if isinstance(summary, dict) else {}
        duckdb_path = duckdb_summary.get("duckdb_path") if isinstance(duckdb_summary, dict) else None
        if duckdb_path:
            payload["duckdb_search"] = search_email_graphrag_duckdb(
                index_path=duckdb_path,
                query=args.search_query,
                limit=args.search_limit,
            )
        else:
            payload["duckdb_search"] = {
                "status": "duckdb_index_unavailable",
                "query": args.search_query,
            }
    else:
        payload = summary
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
