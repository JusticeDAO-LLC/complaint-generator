from __future__ import annotations

from pathlib import Path

from ipfs_datasets_py.processors.multimedia import attachment_text_extractor as module


def test_extract_attachment_text_reads_plain_text(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("Clackamas County Housing Authority notice", encoding="utf-8")

    result = module.extract_attachment_text(path)

    assert result["method"] == "text"
    assert "Clackamas County Housing Authority notice" in result["text"]


def test_extract_attachment_text_uses_pdf_native_text(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "notice.pdf"
    path.write_bytes(b"%PDF-1.4 fake")

    class _FakePage:
        def extract_text(self) -> str:
            return "Voucher issuance notice"

    class _FakePDF:
        pages = [_FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakePdfPlumber:
        @staticmethod
        def open(_path: str) -> _FakePDF:
            return _FakePDF()

    monkeypatch.setattr(module, "pdfplumber", _FakePdfPlumber)

    result = module.extract_attachment_text(path, use_ocr=False)

    assert result["method"] == "pdf-text"
    assert "Voucher issuance notice" in result["text"]


def test_extract_attachment_text_uses_image_ocr(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "notice.png"
    path.write_bytes(b"fake-image-bytes")

    monkeypatch.setattr(
        module,
        "_ocr_image_bytes",
        lambda _image_bytes: {"text": "reasonable accommodation request", "engine": "tesseract", "confidence": 0.91},
    )

    result = module.extract_attachment_text(path)

    assert result["method"] == "image-ocr"
    assert result["ocr_used"] is True
    assert result["ocr_engine"] == "tesseract"
    assert "reasonable accommodation request" in result["text"]
