#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from complaint_generator.email_graphrag import build_email_graphrag_artifacts
from integrations.ipfs_datasets.legal_data import load_legal_symbol

merge_email_manifests = load_legal_symbol("merge_email_manifests", module="email_workspace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge existing email import manifests into one deduplicated manifest.")
    parser.add_argument("manifest_paths", nargs="+", help="Input email_import_manifest.json files.")
    parser.add_argument("--output-dir", default="evidence/email_imports", help="Output root for the merged manifest.")
    parser.add_argument("--case-slug", required=True, help="Folder name for this merged run.")
    parser.add_argument("--build-graphrag", action="store_true", help="Build GraphRAG and DuckDB artifacts after merge.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = merge_email_manifests(
        manifest_paths=list(args.manifest_paths),
        output_dir=args.output_dir,
        case_slug=args.case_slug,
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
