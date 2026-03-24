#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from complaint_generator.email_seed_planner import build_email_seed_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a Gmail/email evidence plan from HACC complaint artifacts.")
    parser.add_argument("grounded_run", help="Path to grounded run directory containing complaint_synthesis artifacts.")
    parser.add_argument("--write-keywords", default=None, help="Optional path to write newline-delimited email keywords.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
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
