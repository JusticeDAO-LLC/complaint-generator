#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from complaint_generator.email_graphrag import build_email_graphrag_artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build GraphRAG artifacts for an imported email evidence manifest.")
    parser.add_argument("manifest_path", help="Path to email_import_manifest.json")
    parser.add_argument("--output-dir", default=None, help="Optional output directory for graphrag artifacts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = build_email_graphrag_artifacts(
        manifest_path=args.manifest_path,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
