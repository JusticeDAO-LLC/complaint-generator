from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from complaint_phases.knowledge_graph import KnowledgeGraphBuilder
from ipfs_datasets_py.processors.multimedia.attachment_text_extractor import extract_attachment_text


def _participants_from_eml(bundle_dir: Path) -> list[str]:
    eml_path = bundle_dir / "message.eml"
    if not eml_path.exists():
        return []
    try:
        message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    except Exception:
        return []
    participants: list[str] = []
    seen: set[str] = set()
    for header_name in ("from", "to", "cc", "bcc", "reply-to", "sender"):
        header = message.get(header_name)
        header_addresses = getattr(header, "addresses", ()) or ()
        for entry in header_addresses:
            username = str(getattr(entry, "username", "") or "").strip()
            domain = str(getattr(entry, "domain", "") or "").strip()
            if not username or not domain:
                continue
            address = f"{username}@{domain}".lower()
            if address in seen:
                continue
            seen.add(address)
            participants.append(address)
    return participants

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
        extraction = extract_attachment_text(path)
        attachment_text = str(extraction.get("text") or "").strip()
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
        bundle_dir = Path(record.get("bundle_dir") or "")
        parsed_participants = _participants_from_eml(bundle_dir) if bundle_dir else []
        merged_participants: list[str] = []
        seen_participants: set[str] = set()
        for participant in list(record.get("participants") or []) + parsed_participants:
            cleaned = str(participant or "").strip().lower()
            if not cleaned or cleaned in seen_participants:
                continue
            seen_participants.add(cleaned)
            merged_participants.append(cleaned)
        record_for_corpus = dict(record)
        record_for_corpus["participants"] = merged_participants
        corpus_text = _email_record_to_corpus_text(record_for_corpus)
        entry = {
            "index": index,
            "subject": record.get("subject", ""),
            "from": record.get("from", ""),
            "to": record.get("to", ""),
            "date": record.get("date"),
            "bundle_dir": record.get("bundle_dir"),
            "attachment_paths": list(record.get("attachment_paths") or []),
            "participants": merged_participants,
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
