from __future__ import annotations

import argparse
import json

from integrations.ipfs_datasets.legal_data import load_legal_symbol
from integrations.ipfs_datasets.loader import import_failure_message


def _require_enrich_email_timeline_authorities():
    try:
        return load_legal_symbol("enrich_email_timeline_authorities", module="email_authority_enrichment")
    except ImportError as error:
        raise ImportError(
            "Unable to import ipfs_datasets_py email authority enrichment: "
            f"{import_failure_message(error) or 'missing enrich_email_timeline_authorities'}"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search state law and case law authorities to accompany an email timeline handoff."
    )
    parser.add_argument("--email-timeline-handoff", required=True, help="Path to email_timeline_handoff.json")
    parser.add_argument("--output-dir", help="Directory for the authority enrichment artifacts")
    parser.add_argument("--jurisdiction", default="or", help="Jurisdiction/court code for case-law search")
    parser.add_argument("--jurisdiction-label", default="Oregon", help="Human-readable jurisdiction label")
    parser.add_argument("--max-queries", type=int, default=8, help="Maximum seeded authority queries to run")
    parser.add_argument(
        "--skip-state-archives",
        action="store_true",
        help="Skip Oregon/Clackamas-focused archive domain searches",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    enrich_email_timeline_authorities = _require_enrich_email_timeline_authorities()
    payload = enrich_email_timeline_authorities(
        args.email_timeline_handoff,
        output_dir=args.output_dir,
        jurisdiction=args.jurisdiction,
        jurisdiction_label=args.jurisdiction_label,
        max_queries=args.max_queries,
        search_state_archives=not args.skip_state_archives,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
