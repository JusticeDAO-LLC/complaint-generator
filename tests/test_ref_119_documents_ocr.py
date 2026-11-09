import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from integrations.ipfs_datasets.documents import parse_pdf_to_record


pytestmark = pytest.mark.no_auto_network


def _baseline_parse(text: str = "Baseline PDF text") -> dict:
    return {
        "status": "available-fallback",
        "text": text,
        "metadata": {
            "mime_type": "application/pdf",
            "extraction_method": "pdf_text_fallback",
            "parse_quality": {"quality_flags": ["pdf_binary_fallback"]},
        },
    }


def test_parse_pdf_reports_expected_ocr_exception_and_retains_baseline(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 sample")
    ocr_temp_dir = tmp_path / "ocr-work"

    with (
        patch("integrations.ipfs_datasets.documents.parse_document_file", return_value=_baseline_parse()),
        patch("integrations.ipfs_datasets.documents.shutil.which", return_value="/usr/bin/ocrmypdf"),
        patch("integrations.ipfs_datasets.documents.tempfile.mkdtemp", return_value=str(ocr_temp_dir)),
        patch(
            "integrations.ipfs_datasets.documents.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ocrmypdf", timeout=300),
        ),
    ):
        ocr_temp_dir.mkdir()
        payload = parse_pdf_to_record(pdf_path, output_dir=tmp_path / "parsed")

    assert payload["status"] == "success"
    assert payload["text"] == "Baseline PDF text"
    assert payload["ocr_attempted"] is True
    assert payload["ocr_used"] is False
    assert payload["needs_ocr"] is True
    assert payload["ocr_error"]["error_type"] == "TimeoutExpired"
    assert "300 seconds" in payload["ocr_error"]["message"]
    assert not ocr_temp_dir.exists()

    persisted_metadata = json.loads(Path(payload["metadata_path"]).read_text(encoding="utf-8"))
    assert persisted_metadata["ocr_error"] == payload["ocr_error"]
    assert persisted_metadata["needs_ocr"] is True


def test_parse_pdf_reports_nonzero_ocr_exit(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 sample")

    with (
        patch("integrations.ipfs_datasets.documents.parse_document_file", return_value=_baseline_parse()),
        patch("integrations.ipfs_datasets.documents.shutil.which", return_value="/usr/bin/ocrmypdf"),
        patch(
            "integrations.ipfs_datasets.documents.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["ocrmypdf"],
                returncode=2,
                stdout="",
                stderr="input PDF is encrypted",
            ),
        ),
    ):
        payload = parse_pdf_to_record(pdf_path, output_dir=tmp_path / "parsed")

    assert payload["status"] == "success"
    assert payload["ocr_error"] == {
        "error_type": "OCRProcessError",
        "message": "input PDF is encrypted",
        "returncode": 2,
    }
    assert payload["needs_ocr"] is True


def test_parse_pdf_reports_missing_ocr_output(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 sample")

    with (
        patch("integrations.ipfs_datasets.documents.parse_document_file", return_value=_baseline_parse()),
        patch("integrations.ipfs_datasets.documents.shutil.which", return_value="/usr/bin/ocrmypdf"),
        patch(
            "integrations.ipfs_datasets.documents.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["ocrmypdf"],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ),
    ):
        payload = parse_pdf_to_record(pdf_path, output_dir=tmp_path / "parsed")

    assert payload["ocr_error"] == {
        "error_type": "OCROutputMissing",
        "message": "ocrmypdf completed without creating an output PDF",
    }
    assert payload["needs_ocr"] is True


def test_parse_pdf_does_not_swallow_unexpected_ocr_parser_failures(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 sample")
    parse_results = [_baseline_parse(), RuntimeError("unexpected OCR parser defect")]
    ocr_temp_dir = tmp_path / "unexpected-ocr-work"

    with (
        patch("integrations.ipfs_datasets.documents.parse_document_file", side_effect=parse_results),
        patch("integrations.ipfs_datasets.documents.shutil.which", return_value="/usr/bin/ocrmypdf"),
        patch("integrations.ipfs_datasets.documents.tempfile.mkdtemp", return_value=str(ocr_temp_dir)),
        patch("integrations.ipfs_datasets.documents.subprocess.run") as run_ocr,
    ):
        def create_ocr_output(command, **kwargs):
            Path(command[-1]).write_bytes(b"%PDF-1.7 OCR output")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        run_ocr.side_effect = create_ocr_output
        ocr_temp_dir.mkdir()
        with pytest.raises(RuntimeError, match="unexpected OCR parser defect"):
            parse_pdf_to_record(pdf_path, output_dir=tmp_path / "parsed")

    assert not ocr_temp_dir.exists()
