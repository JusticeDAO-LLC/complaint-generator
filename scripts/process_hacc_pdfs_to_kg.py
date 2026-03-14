from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.ipfs_datasets import build_policy_rule_corpus


def _is_pdf(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        return path.read_bytes()[:4] == b"%PDF"
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Process HACC PDFs into a rules-focused knowledge graph.")
    parser.add_argument(
        "--input-dir",
        default="/home/barberb/HACC/hacc_website",
        help="Directory containing the source PDFs.",
    )
    parser.add_argument(
        "--output-dir",
        default="/home/barberb/HACC/hacc_website/knowledge_graph",
        help="Directory where extracted text and graph JSON should be written.",
    )
    parser.add_argument(
        "--backend",
        default="markitdown",
        help="ipfs_datasets_py file conversion backend to use.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    pdf_paths = sorted(str(path) for path in input_dir.iterdir() if _is_pdf(path))

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "documents").mkdir(parents=True, exist_ok=True)
    (output_dir / "texts").mkdir(parents=True, exist_ok=True)

    result = build_policy_rule_corpus(pdf_paths, backend=args.backend, include_text=True)

    for document in result.get("documents", []):
        source_path = Path(document.get("document", {}).get("source_path", "unknown"))
        stem = source_path.name or "unknown"
        with (output_dir / "documents" / f"{stem}.json").open("w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
        text = str(document.get("text", "") or "")
        if text:
            (output_dir / "texts" / f"{stem}.txt").write_text(text, encoding="utf-8")

    with (output_dir / "corpus_graph.json").open("w", encoding="utf-8") as handle:
        json.dump(result.get("corpus_graph", {}), handle, indent=2, sort_keys=True)

    summary = {
        "status": result.get("status"),
        "document_count": len(result.get("documents", [])),
        "error_count": len(result.get("errors", [])),
        "output_dir": str(output_dir),
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
