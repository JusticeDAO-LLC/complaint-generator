from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List

import anyio
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.ipfs_datasets import create_vector_index
from ipfs_datasets_py.vector_stores.api import create_vector_store


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


def _load_saved_index(index_dir: Path, index_name: str) -> tuple[list[dict], np.ndarray]:
    records_path = index_dir / f"{index_name}.records.jsonl"
    vectors_path = index_dir / f"{index_name}.vectors.npy"
    records = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    vectors = np.load(vectors_path)
    return records, vectors


async def _build_native_ipld_snapshot(
    *,
    index_name: str,
    index_dir: Path,
    output_dir: Path,
) -> Dict[str, object]:
    records, vectors = _load_saved_index(index_dir, index_name)
    if len(records) != len(vectors):
        raise ValueError(f"Record/vector count mismatch for {index_name}: {len(records)} records vs {len(vectors)} vectors")
    if len(vectors) == 0:
        raise ValueError(f"No vectors available for {index_name}")

    store = await create_vector_store(
        "ipld",
        index_name,
        dimension=int(vectors.shape[1]),
        use_embeddings_router=False,
        use_ipfs_router=False,
    )
    await store.create_collection()
    embeddings = [
        SimpleNamespace(
            vector=vectors[i].tolist(),
            text=records[i]["text"],
            metadata=records[i].get("metadata", {}),
            id=records[i]["id"],
        )
        for i in range(len(records))
    ]
    ids = await store.add_embeddings(embeddings, index_name)
    info = await store.get_collection_info(index_name)
    export_attempted = bool(getattr(store, "router", None) and store.router.is_ipfs_available())
    export_cid = await store.export_to_ipld(index_name) if export_attempted else None
    export_status = "exported" if export_cid else "ipfs_unavailable" if not export_attempted else "export_failed"

    output_dir.mkdir(parents=True, exist_ok=True)
    vectors_out = output_dir / f"{index_name}.native.vectors.npy"
    records_out = output_dir / f"{index_name}.native.records.jsonl"
    manifest_out = output_dir / f"{index_name}.native.manifest.json"

    np.save(vectors_out, np.asarray(store.vectors[index_name], dtype=np.float32))
    with records_out.open("w", encoding="utf-8") as handle:
        for vector_id, metadata in zip(store.vector_ids[index_name], store.metadata[index_name]):
            handle.write(
                json.dumps(
                    {
                        "id": vector_id,
                        "text": metadata.get("text", ""),
                        "metadata": metadata.get("metadata", {}),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    manifest = {
        "index_name": index_name,
        "store_type": "IPLDVectorStore",
        "document_count": len(ids),
        "dimension": int(vectors.shape[1]),
        "root_cid": export_cid,
        "export_attempted": export_attempted,
        "export_status": export_status,
        "collection_info": info,
        "vectors_path": str(vectors_out),
        "records_path": str(records_out),
    }
    manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "status": "success",
        "index_name": index_name,
        "document_count": len(ids),
        "dimension": int(vectors.shape[1]),
        "root_cid": export_cid,
        "export_attempted": export_attempted,
        "export_status": export_status,
        "manifest_path": str(manifest_out),
        "records_path": str(records_out),
        "vectors_path": str(vectors_out),
    }


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
    parser.add_argument(
        "--native-ipld-store",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Load the saved embeddings into the patched ipfs_datasets_py IPLDVectorStore and write a native snapshot.",
    )
    parser.add_argument(
        "--native-output-dir",
        default="",
        help="Directory for native IPLD vector store snapshots. Defaults to <output-dir>/native_ipld.",
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

    native_summary: Dict[str, object] = {}
    if args.native_ipld_store and text_result.get("status") == "success" and graph_result.get("status") == "success":
        native_output_dir = Path(args.native_output_dir).resolve() if args.native_output_dir else output_dir / "native_ipld"
        native_summary = anyio.run(
            partial(_run_native_exports, output_dir=output_dir, native_output_dir=native_output_dir)
        )

    summary = {
        "text_index": text_result,
        "graph_index": graph_result,
        "output_dir": str(output_dir),
        "native_ipld": native_summary,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(
        {
            "text_status": text_result.get("status"),
            "text_documents": text_result.get("document_count"),
            "graph_status": graph_result.get("status"),
            "graph_documents": graph_result.get("document_count"),
            "native_ipld_status": native_summary.get("status", "not_requested"),
            "output_dir": str(output_dir),
        },
        indent=2,
        sort_keys=True,
    ))
    if text_result.get("status") != "success" or graph_result.get("status") != "success":
        return 1
    return 0


async def _run_native_exports(*, output_dir: Path, native_output_dir: Path) -> Dict[str, object]:
    text_native = await _build_native_ipld_snapshot(
        index_name="hacc_text_chunks",
        index_dir=output_dir,
        output_dir=native_output_dir,
    )
    graph_native = await _build_native_ipld_snapshot(
        index_name="hacc_policy_graph",
        index_dir=output_dir,
        output_dir=native_output_dir,
    )
    return {
        "status": "success",
        "output_dir": str(native_output_dir),
        "text_index": text_native,
        "graph_index": graph_native,
    }


if __name__ == "__main__":
    raise SystemExit(main())
