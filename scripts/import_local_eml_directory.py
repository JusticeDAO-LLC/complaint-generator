#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json


from complaint_generator.email_graphrag import build_email_graphrag_artifacts
from integrations.ipfs_datasets.legal_data import load_legal_symbol

import_local_eml_directory = load_legal_symbol("import_local_eml_directory", module="email_workspace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import a local directory of .eml files into an email evidence manifest.")
    parser.add_argument("source_dir", help="Directory containing .eml files.")
    parser.add_argument("--output-dir", default="evidence/email_imports", help="Output root for imported email bundles.")
    parser.add_argument("--case-slug", required=True, help="Folder name for this import run.")
    parser.add_argument("--recursive", action="store_true", help="Recursively import .eml files under the source directory.")
    parser.add_argument("--complaint-query", default="", help="Free-text query used to derive complaint relevance terms.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Additional complaint keyword. Repeat to add more.")
    parser.add_argument("--min-relevance-score", type=float, default=1.0, help="Skip local .eml messages scoring below this threshold when complaint terms are provided.")
    parser.add_argument("--build-graphrag", action="store_true", help="Build GraphRAG and DuckDB artifacts immediately after import.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = import_local_eml_directory(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        case_slug=args.case_slug,
        recursive=args.recursive,
        complaint_query=args.complaint_query,
        complaint_keywords=list(args.complaint_keyword or []),
        min_relevance_score=float(args.min_relevance_score),
    )
    if args.build_graphrag:
        payload["graphrag_summary"] = build_email_graphrag_artifacts(
            manifest_path=payload["manifest_path"],
            include_attachment_text_in_search=True,
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
