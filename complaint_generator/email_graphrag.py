from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from complaint_phases.knowledge_graph import KnowledgeGraphBuilder


TEXT_ATTACHMENT_SUFFIXES = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".xml",
    ".log",
}


def _read_text_attachment(path: Path, *, max_bytes: int = 200_000) -> str:
    if path.suffix.lower() not in TEXT_ATTACHMENT_SUFFIXES:
        return ""
    try:
        raw = path.read_bytes()[:max_bytes]
        return raw.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _email_record_to_corpus_text(record: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"Email subject: {record.get('subject') or ''}")
    lines.append(f"From: {record.get('from') or ''}")
    lines.append(f"To: {record.get('to') or ''}")
    lines.append(f"Cc: {record.get('cc') or ''}")
    lines.append(f"Date: {record.get('date') or ''}")
    participants = ", ".join(record.get("participants") or [])
    if participants:
        lines.append(f"Participants: {participants}")
    if record.get("message_id_header"):
        lines.append(f"Message-ID: {record.get('message_id_header')}")
    for path_str in record.get("attachment_paths") or []:
        path = Path(path_str)
        lines.append(f"Attachment filename: {path.name}")
        attachment_text = _read_text_attachment(path)
        if attachment_text:
            lines.append(f"Attachment text from {path.name}: {attachment_text}")
    return "\n".join(line for line in lines if line.strip()).strip()


def build_email_graphrag_artifacts(
    *,
    manifest_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    records = list(manifest.get("emails") or [])
    run_dir = manifest_file.parent
    graphrag_dir = Path(output_dir).expanduser().resolve() if output_dir else run_dir / "graphrag"
    graphrag_dir.mkdir(parents=True, exist_ok=True)

    email_corpus_records: list[dict[str, Any]] = []
    combined_sections: list[str] = []
    for index, record in enumerate(records, start=1):
        corpus_text = _email_record_to_corpus_text(record)
        entry = {
            "index": index,
            "subject": record.get("subject", ""),
            "from": record.get("from", ""),
            "to": record.get("to", ""),
            "date": record.get("date"),
            "bundle_dir": record.get("bundle_dir"),
            "attachment_paths": list(record.get("attachment_paths") or []),
            "corpus_text": corpus_text,
        }
        email_corpus_records.append(entry)
        if corpus_text:
            combined_sections.append(f"Email record {index}\n{corpus_text}")

    combined_corpus = "\n\n".join(section for section in combined_sections if section.strip())
    graph = KnowledgeGraphBuilder().build_from_text(combined_corpus)

    graph_path = graphrag_dir / "email_knowledge_graph.json"
    graph.to_json(str(graph_path))

    corpus_path = graphrag_dir / "email_corpus_records.json"
    corpus_path.write_text(json.dumps(email_corpus_records, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "manifest_path": str(manifest_file),
        "graphrag_dir": str(graphrag_dir),
        "email_count": len(records),
        "attachment_total": sum(len(record.get("attachment_paths") or []) for record in records),
        "knowledge_graph_summary": graph.summary(),
        "graph_path": str(graph_path),
        "corpus_records_path": str(corpus_path),
    }
    summary_path = graphrag_dir / "email_graphrag_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    return summary


__all__ = ["build_email_graphrag_artifacts"]
