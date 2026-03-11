from __future__ import annotations

import mimetypes
import re
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loader import import_attr_optional, import_module_optional


InputDetector, _input_detector_error = import_attr_optional(
    "ipfs_datasets_py.processors",
    "InputDetector",
)
BatchProcessor, _batch_processor_error = import_attr_optional(
    "ipfs_datasets_py.processors",
    "BatchProcessor",
)
_processors_module, _processors_error = import_module_optional("ipfs_datasets_py.processors")
_text_extractors_module, _text_extractors_error = import_module_optional(
    "ipfs_datasets_py.processors.file_converter.text_extractors"
)

DOCUMENTS_AVAILABLE = any(
    value is not None
    for value in (
        InputDetector,
        BatchProcessor,
        _processors_module,
        _text_extractors_module,
    )
)
DOCUMENTS_ERROR = (
    _input_detector_error
    or _batch_processor_error
    or _processors_error
    or _text_extractors_error
)

PARSER_VERSION = "documents-adapter:1"


def _decode_text_fallback(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in (text or "").splitlines()]
    normalized = "\n".join(line for line in lines if line)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style\b[^>]*>.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</(p|div|section|article|li|tr|h[1-6])>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return _normalize_whitespace(unescape(cleaned))


def _looks_like_html(text: str, mime_type: str, filename: str) -> bool:
    lowered_text = (text or "")[:512].lower()
    lowered_mime = (mime_type or "").lower()
    lowered_name = (filename or "").lower()
    return (
        "html" in lowered_mime
        or lowered_name.endswith((".html", ".htm", ".xhtml"))
        or "<html" in lowered_text
        or "<!doctype html" in lowered_text
        or ("<body" in lowered_text and "</" in lowered_text)
    )


def _split_into_paragraphs(text: str) -> List[str]:
    if not text:
        return []
    return [part.strip() for part in re.split(r"\n\s*\n+", text) if part and part.strip()]


def _guess_mime_type(filename: str, mime_type: str) -> str:
    if mime_type:
        return mime_type
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed or "text/plain"


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[Dict[str, Any]]:
    if chunk_size <= 0:
        chunk_size = 1000
    overlap = max(0, min(overlap, max(0, chunk_size // 2)))
    normalized_text = text or ""
    chunks: List[Dict[str, Any]] = []
    start = 0
    index = 0
    while start < len(normalized_text):
        end = min(len(normalized_text), start + chunk_size)
        if end < len(normalized_text):
            boundary = normalized_text.rfind("\n", start, end)
            sentence_boundary = max(
                normalized_text.rfind(". ", start, end),
                normalized_text.rfind("? ", start, end),
                normalized_text.rfind("! ", start, end),
            )
            split_at = max(boundary, sentence_boundary)
            if split_at > start + (chunk_size // 2):
                end = split_at + (0 if split_at == boundary else 1)
        content = normalized_text[start:end]
        content = content.strip()
        if not content:
            start = end if end > start else start + chunk_size
            continue
        chunks.append(
            {
                "chunk_id": f"chunk-{index}",
                "index": index,
                "start": start,
                "end": start + len(content),
                "text": content,
                "length": len(content),
            }
        )
        if end >= len(normalized_text):
            break
        next_start = max(end - overlap, start + 1)
        start = next_start
        index += 1
    return chunks


def parse_document_text(
    text: str,
    *,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    source: str = "text",
    chunk_size: int = 1000,
    overlap: int = 100,
) -> Dict[str, Any]:
    normalized_mime = _guess_mime_type(filename or "", mime_type or "")
    raw_text = text or ""
    normalized_text = _strip_html(raw_text) if _looks_like_html(raw_text, normalized_mime, filename or "") else _normalize_whitespace(raw_text)
    paragraphs = _split_into_paragraphs(normalized_text)
    chunks = chunk_text(normalized_text, chunk_size=chunk_size, overlap=overlap) if normalized_text else []
    status = "empty"
    if normalized_text:
        status = "available-fallback" if DOCUMENTS_AVAILABLE else "fallback"
    return {
        "status": status,
        "text": normalized_text,
        "chunks": chunks,
        "metadata": {
            "filename": filename or "",
            "mime_type": normalized_mime,
            "size": len(raw_text.encode("utf-8", errors="ignore")),
            "backend_available": DOCUMENTS_AVAILABLE,
            "parser_version": PARSER_VERSION,
            "source": source,
            "chunk_count": len(chunks),
            "paragraph_count": len(paragraphs),
            "text_length": len(normalized_text),
            "input_format": "html" if _looks_like_html(raw_text, normalized_mime, filename or "") else "text",
        },
    }


def parse_document_bytes(
    data: bytes,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> Dict[str, Any]:
    parsed = parse_document_text(
        _decode_text_fallback(data),
        filename=filename,
        mime_type=mime_type,
        source="bytes",
        chunk_size=chunk_size,
        overlap=overlap,
    )
    parsed["metadata"]["size"] = len(data)
    return parsed


def parse_document_file(
    file_path: str,
    *,
    mime_type: Optional[str] = None,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> Dict[str, Any]:
    path = Path(file_path)
    data = path.read_bytes()
    return parse_document_bytes(
        data,
        filename=path.name,
        mime_type=_guess_mime_type(path.name, mime_type or ""),
        chunk_size=chunk_size,
        overlap=overlap,
    )


__all__ = [
    "InputDetector",
    "BatchProcessor",
    "DOCUMENTS_AVAILABLE",
    "DOCUMENTS_ERROR",
    "PARSER_VERSION",
    "chunk_text",
    "parse_document_text",
    "parse_document_bytes",
    "parse_document_file",
]