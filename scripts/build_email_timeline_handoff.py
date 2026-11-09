#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from complaint_generator.email_timeline_handoff import build_email_timeline_handoff_from_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a complaint-ready chronology handoff from agentic email timeline candidates.")
    parser.add_argument("timeline_path", help="Path to timeline_candidates.json or combined timeline JSON.")
    parser.add_argument("--output-path", default=None, help="Optional output path for the generated chronology handoff JSON.")
    parser.add_argument("--claim-type", default="retaliation", help="Claim type to stamp into the temporal handoff.")
    parser.add_argument("--claim-element-id", default="causation", help="Claim element id to stamp into the temporal handoff.")
    parser.add_argument(
        "--temporal-proof-objective",
        default="establish_clackamas_email_sequence",
        help="Temporal proof objective label to include in the handoff.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON payload.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = build_email_timeline_handoff_from_file(
        Path(args.timeline_path),
        output_path=Path(args.output_path).expanduser().resolve() if args.output_path else None,
        claim_type=str(args.claim_type or "retaliation"),
        claim_element_id=str(args.claim_element_id or "causation"),
        temporal_proof_objective=str(args.temporal_proof_objective or "establish_clackamas_email_sequence"),
    )
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Built chronology handoff: {payload['output_path']}")
        print(f"Events: {payload['source_event_count']}")
        print(f"Anchors: {len(payload.get('timeline_anchors') or [])}")
        print(f"Relations: {len(payload.get('timeline_relations') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
