from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.ipfs_datasets import create_vector_index


def _chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    chunks: List[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(cleaned):
        chunks.append(cleaned[start : start + chunk_size])
        start += step
    return chunks


def _build_text_documents(text_dir: Path) -> List[Dict[str, object]]:
    documents: List[Dict[str, object]] = []
    for path in sorted(text_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        for index, chunk in enumerate(_chunk_text(text)):
            documents.append(
                {
                    "id": f"text:{path.stem}:{index}",
                    "text": chunk,
                    "metadata": {
                        "source_type": "extracted_text_chunk",
                        "source_file": path.name,
                        "chunk_index": index,
                    },
                }
            )
    return documents


def _build_graph_documents(documents_dir: Path) -> List[Dict[str, object]]:
    graph_records: List[Dict[str, object]] = []
    for path in sorted(documents_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        document = payload.get("document", {})
        title = str(document.get("title") or path.stem)
        doc_id = str(document.get("document_id") or path.stem)
        source_file = path.name

        graph_records.append(
            {
                "id": f"graph-document:{doc_id}",
                "text": f"Policy document {title}. Source file {source_file}.",
                "metadata": {
                    "source_type": "policy_document",
                    "document_id": doc_id,
                    "source_file": source_file,
                    "title": title,
                },
            }
        )

        seen_sections = set()
        for rule in payload.get("rules", []):
            section_title = str(rule.get("section_title") or "").strip()
            section_id = str(rule.get("section_id") or "")
            if section_title and section_id and section_id not in seen_sections:
                seen_sections.add(section_id)
                graph_records.append(
                    {
                        "id": f"graph-section:{section_id}",
                        "text": f"Section {section_title} in policy document {title}.",
                        "metadata": {
                            "source_type": "policy_section",
                            "document_id": doc_id,
                            "section_id": section_id,
                            "section_title": section_title,
                            "source_file": source_file,
                        },
                    }
                )

            rule_text = str(rule.get("text") or "").strip()
            if not rule_text:
                continue
            graph_records.append(
                {
                    "id": f"graph-rule:{rule.get('rule_id')}",
                    "text": (
                        f"Rule in {section_title or 'document overview'} from {title}. "
                        f"Type: {rule.get('rule_type', '')}. "
                        f"Modality: {rule.get('modality', '')}. "
                        f"Text: {rule_text}"
                    ),
                    "metadata": {
                        "source_type": "policy_rule",
                        "document_id": doc_id,
                        "section_id": section_id,
                        "section_title": section_title,
                        "rule_id": rule.get("rule_id"),
                        "rule_type": rule.get("rule_type"),
                        "modality": rule.get("modality"),
                        "source_file": source_file,
                    },
                }
            )
    return graph_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Create vector embeddings for HACC extracted text and knowledge graph.")
    parser.add_argument(
        "--kg-dir",
        default="/home/barberb/HACC/hacc_website/knowledge_graph",
        help="Directory containing the generated knowledge graph artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        default="/home/barberb/HACC/hacc_website/knowledge_graph/embeddings",
        help="Directory where embedding indexes should be written.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Embedding batch size.",
    )
    args = parser.parse_args()

    kg_dir = Path(args.kg_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    text_documents = _build_text_documents(kg_dir / "texts")
    graph_documents = _build_graph_documents(kg_dir / "documents")

    text_result = create_vector_index(
        text_documents,
        index_name="hacc_text_chunks",
        output_dir=str(output_dir),
        batch_size=args.batch_size,
    )
    graph_result = create_vector_index(
        graph_documents,
        index_name="hacc_policy_graph",
        output_dir=str(output_dir),
        batch_size=args.batch_size,
    )

    summary = {
        "text_index": text_result,
        "graph_index": graph_result,
        "output_dir": str(output_dir),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(
        {
            "text_status": text_result.get("status"),
            "text_documents": text_result.get("document_count"),
            "graph_status": graph_result.get("status"),
            "graph_documents": graph_result.get("document_count"),
            "output_dir": str(output_dir),
        },
        indent=2,
        sort_keys=True,
    ))
    if text_result.get("status") != "success" or graph_result.get("status") != "success":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
