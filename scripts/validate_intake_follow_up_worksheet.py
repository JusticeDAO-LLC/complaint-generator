#!/usr/bin/env python3
"""Validate and normalize an intake follow-up worksheet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Worksheet payload must be a JSON object")
    return payload


def _normalize_item_status(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(item)
    question = " ".join(str(normalized.get("question") or "").split()).strip()
    answer = " ".join(str(normalized.get("answer") or "").split()).strip()
    current_status = " ".join(str(normalized.get("status") or "").split()).strip().lower()

    if not question:
        status = "invalid"
    elif answer:
        status = "answered"
    elif current_status in {"skipped", "not_applicable"}:
        status = current_status
    else:
        status = "open"

    normalized["question"] = question
    normalized["answer"] = answer
    normalized["status"] = status
    return normalized


def normalize_worksheet(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    items = list(payload.get("follow_up_items") or [])
    normalized_items: List[Dict[str, Any]] = []
    status_counts: Dict[str, int] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        normalized_item = _normalize_item_status(item)
        normalized_items.append(normalized_item)
        status = str(normalized_item.get("status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1

    normalized["follow_up_items"] = normalized_items
    normalized["validation_summary"] = {
        "item_count": len(normalized_items),
        "status_counts": status_counts,
        "all_answered": bool(normalized_items) and status_counts.get("answered", 0) == len(normalized_items),
        "open_question_count": status_counts.get("open", 0),
        "invalid_question_count": status_counts.get("invalid", 0),
    }
    return normalized


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and normalize intake follow-up worksheet JSON.")
    parser.add_argument("worksheet_json", help="Path to intake_follow_up_worksheet.json")
    parser.add_argument("--output", default=None, help="Optional output path for the normalized worksheet JSON.")
    parser.add_argument("--in-place", action="store_true", help="Rewrite the input worksheet file in place.")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Exit nonzero unless all worksheet items are answered and none are invalid.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    worksheet_path = Path(args.worksheet_json).resolve()
    payload = _load_json(worksheet_path)
    normalized = normalize_worksheet(payload)

    output_path: Path | None = None
    if args.in_place:
        output_path = worksheet_path
    elif args.output:
        output_path = Path(args.output).resolve()

    if output_path is not None:
        output_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = dict(normalized.get("validation_summary") or {})
    print("Intake worksheet validation passed")
    print(f"- worksheet: {worksheet_path}")
    print(f"- item_count: {summary.get('item_count', 0)}")
    print(f"- answered: {dict(summary.get('status_counts') or {}).get('answered', 0)}")
    print(f"- open: {summary.get('open_question_count', 0)}")
    print(f"- invalid: {summary.get('invalid_question_count', 0)}")
    if output_path is not None:
        print(f"- wrote: {output_path}")
    if args.require_complete and (
        not bool(summary.get("all_answered"))
        or int(summary.get("invalid_question_count", 0) or 0) > 0
    ):
        print("Worksheet is not complete enough for rerun preflight", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
