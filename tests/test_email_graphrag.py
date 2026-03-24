from __future__ import annotations

import json
from pathlib import Path

from complaint_generator.email_graphrag import build_email_graphrag_artifacts


def test_build_email_graphrag_artifacts(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    attachment = bundle_dir / "note.txt"
    attachment.write_text("Kati Tilton scheduled HCV orientation review.", encoding="utf-8")
    manifest_path = tmp_path / "email_import_manifest.json"
    manifest = {
        "emails": [
            {
                "subject": "RE: HCV Orientation",
                "from": '"Tilton, Kati" <KTilton@clackamas.us>',
                "to": "benjamin barber <starworks5@gmail.com>",
                "cc": "",
                "date": "2026-03-19T12:00:00-07:00",
                "participants": ["ktilton@clackamas.us", "starworks5@gmail.com"],
                "message_id_header": "<msg@example.com>",
                "bundle_dir": str(bundle_dir),
                "attachment_paths": [str(attachment)],
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    summary = build_email_graphrag_artifacts(manifest_path=manifest_path)

    assert summary["email_count"] == 1
    assert summary["attachment_total"] == 1
    assert Path(summary["graph_path"]).exists()
    assert Path(summary["corpus_records_path"]).exists()
    graph_payload = json.loads(Path(summary["graph_path"]).read_text(encoding="utf-8"))
    entity_names = " ".join(
        (entity.get("name") or "")
        for entity in (graph_payload.get("entities") or {}).values()
    ).lower()
    assert "kati" in entity_names or "tilton" in entity_names or "clackamas" in entity_names


def test_build_email_graphrag_artifacts_merges_participants_from_eml(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "message.eml").write_bytes(
        (
            b"From: \"Tilton, Kati\" <KTilton@clackamas.us>\r\n"
            b"To: benjamin barber <starworks5@gmail.com>\r\n"
            b"Subject: RE: HCV Orientation\r\n"
            b"\r\n"
            b"Orientation packet attached.\r\n"
        )
    )
    manifest_path = tmp_path / "email_import_manifest.json"
    manifest = {
        "emails": [
            {
                "subject": "RE: HCV Orientation",
                "from": "",
                "to": "",
                "cc": "",
                "date": "2026-03-19T12:00:00-07:00",
                "participants": [],
                "bundle_dir": str(bundle_dir),
                "attachment_paths": [],
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    summary = build_email_graphrag_artifacts(manifest_path=manifest_path)

    corpus_payload = json.loads(Path(summary["corpus_records_path"]).read_text(encoding="utf-8"))
    assert corpus_payload[0]["participants"] == ["ktilton@clackamas.us", "starworks5@gmail.com"]


def test_build_email_graphrag_artifacts_includes_attachment_extraction_text(tmp_path: Path, monkeypatch) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    attachment = bundle_dir / "scan.pdf"
    attachment.write_bytes(b"%PDF-1.4 fake")
    manifest_path = tmp_path / "email_import_manifest.json"
    manifest = {
        "emails": [
            {
                "subject": "RE: HCV Orientation",
                "from": '"Tilton, Kati" <KTilton@clackamas.us>',
                "to": "benjamin barber <starworks5@gmail.com>",
                "cc": "",
                "date": "2026-03-19T12:00:00-07:00",
                "participants": ["ktilton@clackamas.us", "starworks5@gmail.com"],
                "message_id_header": "<msg@example.com>",
                "bundle_dir": str(bundle_dir),
                "attachment_paths": [str(attachment)],
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(
        "complaint_generator.email_graphrag.extract_attachment_text",
        lambda _path: {"text": "Release of claim for two-bedroom accommodation", "method": "pdf-ocr"},
    )

    summary = build_email_graphrag_artifacts(manifest_path=manifest_path)

    corpus_payload = json.loads(Path(summary["corpus_records_path"]).read_text(encoding="utf-8"))
    assert "Release of claim for two-bedroom accommodation" in corpus_payload[0]["corpus_text"]
