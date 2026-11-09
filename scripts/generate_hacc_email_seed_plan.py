#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from integrations.ipfs_datasets.legal_data import load_legal_symbol
from integrations.ipfs_datasets.loader import import_failure_message


def _require_build_email_seed_plan():
    try:
        return load_legal_symbol("build_email_seed_plan", module="email_seed_planner")
    except ImportError as error:
        raise ImportError(
            "Unable to import ipfs_datasets_py email seed planner: "
            f"{import_failure_message(error) or 'missing build_email_seed_plan'}"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a Gmail/email evidence plan from HACC complaint artifacts.")
    parser.add_argument("grounded_run", help="Path to grounded run directory containing complaint_synthesis artifacts.")
    parser.add_argument("--write-keywords", default=None, help="Optional path to write newline-delimited email keywords.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    build_email_seed_plan = _require_build_email_seed_plan()
    grounded_run = Path(args.grounded_run).resolve()
    synthesis_dir = grounded_run / "complaint_synthesis"
    payload = build_email_seed_plan(
        complaint_package_path=synthesis_dir / "draft_complaint_package.json",
        worksheet_path=synthesis_dir / "intake_follow_up_worksheet.json",
    )
    if args.write_keywords:
        Path(args.write_keywords).write_text(
            "\n".join(payload.get("complaint_email_keywords") or []) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
