#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from integrations.ipfs_datasets.legal_data import load_legal_symbol
from integrations.ipfs_datasets.loader import import_failure_message


def _require_generate_email_search_plan():
    try:
        return load_legal_symbol("generate_email_search_plan", module="email_relevance")
    except ImportError as error:
        raise ImportError(
            "Unable to import ipfs_datasets_py email relevance planner: "
            f"{import_failure_message(error) or 'missing generate_email_search_plan'}"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate complaint-focused email search terms and scoring guidance."
    )
    parser.add_argument("--complaint-query", required=True, help="Free-text complaint description.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Repeatable complaint keyword or phrase.")
    parser.add_argument("--complaint-keyword-file", action="append", default=[], help="Path to newline-delimited complaint keywords or phrases.")
    parser.add_argument("--address", action="append", default=[], help="Address filters that will be used during import.")
    parser.add_argument("--date-after", default=None, help="Optional YYYY-MM-DD lower bound.")
    parser.add_argument("--date-before", default=None, help="Optional YYYY-MM-DD upper bound.")
    parser.add_argument("--max-subject-terms", type=int, default=6, help="Maximum number of recommended subject terms.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    generate_email_search_plan = _require_generate_email_search_plan()
    payload = generate_email_search_plan(
        complaint_query=args.complaint_query,
        complaint_keywords=args.complaint_keyword,
        complaint_keyword_files=args.complaint_keyword_file,
        addresses=args.address,
        date_after=args.date_after,
        date_before=args.date_before,
        max_subject_terms=args.max_subject_terms,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
