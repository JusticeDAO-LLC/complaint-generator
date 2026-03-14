from __future__ import annotations

import email.policy
import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
import tempfile
import zipfile
from email.parser import BytesParser
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loader import import_attr_optional, import_module_optional
from .types import (
    DocumentChunk,
    DocumentParseResult,
    DocumentParseSummary,
    DocumentTransformLineage,
    with_adapter_metadata,
)


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

_TEXT_LIKE_MIME_PREFIXES = (
    "text/",
    "message/",
)
_PARSEABLE_MIME_TYPES = {
    "application/pdf",
    "application/rtf",
    "text/rtf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_PARSEABLE_EXTENSIONS = {
    ".txt",
    ".text",
    ".md",
    ".html",
    ".htm",
    ".xhtml",
    ".pdf",
    ".rtf",
    ".doc",
    ".docx",
    ".eml",
}


def _build_parse_summary(
    *,
    status: str,
    text: str,
    chunks: List[Dict[str, Any]],
    parser_version: str,
    input_format: str,
    paragraph_count: int,
    extraction_method: str,
    quality_tier: str,
    quality_score: float,
    page_count: int,
) -> DocumentParseSummary:
    return DocumentParseSummary(
        status=status,
        chunk_count=len(chunks),
        text_length=len(text or ""),
        parser_version=parser_version,
        input_format=input_format,
        paragraph_count=paragraph_count,
        extraction_method=extraction_method,
        quality_tier=quality_tier,
        quality_score=quality_score,
        page_count=page_count,
    )


def _build_transform_lineage(
    *,
    source: str,
    input_format: str,
    parser_version: str,
    chunk_size: int,
    overlap: int,
    chunk_count: int,
    normalization: str,
    extraction: Dict[str, Any],
    source_span: Dict[str, Any],
) -> DocumentTransformLineage:
    return DocumentTransformLineage(
        source=source,
        parser_version=parser_version,
        input_format=input_format,
        normalization=normalization,
        chunking={
            "chunk_size": chunk_size,
            "overlap": overlap,
            "chunk_count": chunk_count,
        },
        extraction=dict(extraction),
        source_span=dict(source_span),
    )


def _determine_normalization_label(input_format: str, text_present: bool) -> str:
    if input_format == "html":
        return "html_to_text"
    if input_format == "email":
        return "email_to_text"
    if input_format == "rtf":
        return "rtf_to_text"
    if input_format == "docx":
        return "docx_xml_to_text"
    if input_format == "pdf":
        return "pdf_text_fallback" if text_present else "pdf_unparsed"
    return "text_normalization"


def _estimate_page_count(input_format: str, text: str, data: Optional[bytes]) -> int:
    if input_format == "pdf":
        if isinstance(data, (bytes, bytearray)) and data:
            page_count = bytes(data).count(b"/Type /Page")
            if page_count > 0:
                return page_count
        return 1 if text else 0
    if not text:
        return 0
    return max(1, text.count("\f") + 1)


def _compute_parse_quality(
    *,
    input_format: str,
    text: str,
    data: Optional[bytes],
    raw_size: int,
) -> Dict[str, Any]:
    text_present = bool(text.strip())
    page_count = _estimate_page_count(input_format, text, data)
    extraction_method = _determine_normalization_label(input_format, text_present)
    flags: List[str] = []

    if not text_present:
        flags.append("empty_text")
    if input_format == "pdf":
        flags.append("pdf_binary_fallback" if text_present else "requires_ocr_or_binary_pdf")
    if input_format in {"docx", "rtf"} and not text_present:
        flags.append("format_extraction_empty")

    if text_present and raw_size > 0 and (len(text) / max(raw_size, 1)) < 0.05:
        flags.append("low_text_density")

    base_scores = {
        "text": 98.0,
        "html": 95.0,
        "email": 93.0,
        "docx": 88.0,
        "rtf": 82.0,
        "pdf": 68.0,
    }
    quality_score = 0.0 if not text_present else base_scores.get(input_format, 75.0)
    if "low_text_density" in flags:
        quality_score = max(quality_score - 15.0, 5.0)

    if quality_score >= 90.0:
        quality_tier = "high"
    elif quality_score >= 75.0:
        quality_tier = "medium"
    elif quality_score > 0.0:
        quality_tier = "low"
    else:
        quality_tier = "empty"

    return {
        "quality_score": round(quality_score, 2),
        "quality_tier": quality_tier,
        "quality_flags": flags,
        "page_count": page_count,
        "extraction_method": extraction_method,
        "ocr_used": False,
        "source_span": {
            "char_start": 0,
            "char_end": len(text or ""),
            "text_length": len(text or ""),
            "raw_size": int(raw_size or 0),
            "page_count": page_count,
        },
        "extraction": {
            "method": extraction_method,
            "ocr_used": False,
            "page_count": page_count,
        },
    }


def _decode_text_fallback(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _is_mostly_text(text: str) -> bool:
    sample = text[:2000]
    visible = [char for char in sample if not char.isspace()]
    if not visible:
        return False
    printable = sum(1 for char in visible if char.isprintable() and char != "\x00")
    return printable / len(visible) >= 0.85


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


def _looks_like_rtf(text: str, mime_type: str, filename: str) -> bool:
    lowered_text = (text or "")[:128].lower().lstrip()
    lowered_mime = (mime_type or "").lower()
    lowered_name = (filename or "").lower()
    return (
        lowered_mime in {"application/rtf", "text/rtf"}
        or lowered_name.endswith(".rtf")
        or lowered_text.startswith("{\\rtf")
    )


def _looks_like_email(text: str, mime_type: str, filename: str) -> bool:
    lowered_text = (text or "")[:512].lower()
    lowered_mime = (mime_type or "").lower()
    lowered_name = (filename or "").lower()
    return (
        lowered_mime == "message/rfc822"
        or lowered_name.endswith(".eml")
        or ("subject:" in lowered_text and "from:" in lowered_text)
    )


def _detect_text_input_format(text: str, mime_type: str, filename: str) -> str:
    if _looks_like_html(text, mime_type, filename):
        return "html"
    if _looks_like_email(text, mime_type, filename):
        return "email"
    if _looks_like_rtf(text, mime_type, filename):
        return "rtf"
    return "text"


def _strip_rtf(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\\par[d]?\b", "\n", text)
    cleaned = re.sub(r"\\tab\b", " ", cleaned)
    cleaned = re.sub(r"\\'[0-9a-fA-F]{2}", " ", cleaned)
    cleaned = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", cleaned)
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    return _normalize_whitespace(unescape(cleaned))


def _extract_email_text(data: bytes) -> str:
    if not data:
        return ""
    try:
        message = BytesParser(policy=email.policy.default).parsebytes(data)
    except Exception:
        return _normalize_whitespace(_decode_text_fallback(data))

    header_lines = []
    for header in ("Subject", "From", "To", "Date"):
        value = str(message.get(header) or "").strip()
        if value:
            header_lines.append(f"{header}: {value}")

    body_parts: List[str] = []
    if message.is_multipart():
        for part in message.walk():
            content_disposition = str(part.get_content_disposition() or "")
            if content_disposition == "attachment":
                continue
            content_type = str(part.get_content_type() or "")
            try:
                payload = part.get_payload(decode=True) or b""
            except Exception:
                payload = b""
            if not payload:
                continue
            if content_type == "text/html":
                body_parts.append(_strip_html(_decode_text_fallback(payload)))
            elif content_type.startswith("text/"):
                body_parts.append(_normalize_whitespace(_decode_text_fallback(payload)))
    else:
        try:
            payload = message.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        content_type = str(message.get_content_type() or "")
        decoded = _decode_text_fallback(payload)
        if content_type == "text/html":
            body_parts.append(_strip_html(decoded))
        else:
            body_parts.append(_normalize_whitespace(decoded))

    combined = "\n\n".join(part for part in ["\n".join(header_lines)] + body_parts if part)
    return _normalize_whitespace(combined)


def _extract_docx_text(data: bytes) -> str:
    if not data:
        return ""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            xml_parts: List[str] = []
            for name in archive.namelist():
                if not name.startswith("word/"):
                    continue
                if not name.endswith(".xml"):
                    continue
                if not any(token in name for token in ("document", "header", "footer", "footnotes", "endnotes")):
                    continue
                xml_parts.append(archive.read(name).decode("utf-8", errors="ignore"))
    except (zipfile.BadZipFile, KeyError, RuntimeError, ValueError):
        return ""

    if not xml_parts:
        return ""

    text = "\n".join(xml_parts)
    text = re.sub(r"</w:p>", "\n", text)
    text = re.sub(r"</w:tr>", "\n", text)
    text = re.sub(r"<w:tab[^>]*/>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_whitespace(unescape(text))


def _extract_pdf_text_fallback(data: bytes) -> str:
    decoded = _decode_text_fallback(data)
    if not _is_mostly_text(decoded):
        return ""
    cleaned = re.sub(r"%PDF-[\d.]+", " ", decoded)
    cleaned = re.sub(r"\b(?:obj|endobj|stream|endstream)\b", " ", cleaned)
    cleaned = _normalize_whitespace(cleaned)
    alpha_chars = sum(1 for char in cleaned if char.isalpha())
    if alpha_chars < 20:
        return ""
    return cleaned


def detect_document_input_format(
    *,
    data: Optional[bytes] = None,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    text: Optional[str] = None,
) -> str:
    normalized_mime = _guess_mime_type(filename or "", mime_type or "")
    lowered_mime = normalized_mime.lower()
    lowered_name = (filename or "").lower()
    binary_prefix = data[:8] if isinstance(data, (bytes, bytearray)) else b""

    if lowered_mime == "message/rfc822" or lowered_name.endswith(".eml"):
        return "email"
    if lowered_mime in {"application/rtf", "text/rtf"} or lowered_name.endswith(".rtf"):
        return "rtf"
    if lowered_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or lowered_name.endswith(".docx"):
        return "docx"
    if lowered_mime == "application/pdf" or lowered_name.endswith(".pdf") or binary_prefix.startswith(b"%PDF-"):
        return "pdf"
    if text is not None:
        return _detect_text_input_format(text, normalized_mime, filename or "")
    if isinstance(data, (bytes, bytearray)):
        decoded = _decode_text_fallback(bytes(data))
        return _detect_text_input_format(decoded, normalized_mime, filename or "")
    return _detect_text_input_format("", normalized_mime, filename or "")


def should_parse_document_input(
    *,
    evidence_type: Optional[str] = None,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> bool:
    normalized_type = (evidence_type or "").lower()
    if normalized_type in {"document", "text", "email", "pdf"}:
        return True
    normalized_mime = _guess_mime_type(filename or "", mime_type or "")
    lowered_mime = normalized_mime.lower()
    if lowered_mime.startswith(_TEXT_LIKE_MIME_PREFIXES):
        return True
    if lowered_mime in _PARSEABLE_MIME_TYPES:
        return True
    return Path(filename or "").suffix.lower() in _PARSEABLE_EXTENSIONS


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
    input_format = detect_document_input_format(text=raw_text, filename=filename, mime_type=normalized_mime)
    if input_format == "html":
        normalized_text = _strip_html(raw_text)
    elif input_format == "rtf":
        normalized_text = _strip_rtf(raw_text)
    else:
        normalized_text = _normalize_whitespace(raw_text)
    paragraphs = _split_into_paragraphs(normalized_text)
    parse_quality = _compute_parse_quality(
        input_format=input_format,
        text=normalized_text,
        data=None,
        raw_size=len(raw_text.encode("utf-8", errors="ignore")),
    )
    chunks = chunk_text(normalized_text, chunk_size=chunk_size, overlap=overlap) if normalized_text else []
    typed_chunks = [
        DocumentChunk(
            chunk_id=str(chunk.get("chunk_id") or ""),
            index=int(chunk.get("index", 0) or 0),
            start=int(chunk.get("start", 0) or 0),
            end=int(chunk.get("end", 0) or 0),
            text=str(chunk.get("text") or ""),
            length=int(chunk.get("length", 0) or 0),
            metadata=dict(chunk.get("metadata") or {}),
        )
        for chunk in chunks
    ]
    status = "empty"
    if normalized_text:
        status = "available-fallback" if DOCUMENTS_AVAILABLE else "fallback"
    summary = _build_parse_summary(
        status=status,
        text=normalized_text,
        chunks=chunks,
        parser_version=PARSER_VERSION,
        input_format=input_format,
        paragraph_count=len(paragraphs),
        extraction_method=str(parse_quality["extraction_method"]),
        quality_tier=str(parse_quality["quality_tier"]),
        quality_score=float(parse_quality["quality_score"]),
        page_count=int(parse_quality["page_count"]),
    )
    transform_lineage = _build_transform_lineage(
        source=source,
        input_format=input_format,
        parser_version=PARSER_VERSION,
        chunk_size=chunk_size,
        overlap=overlap,
        chunk_count=len(typed_chunks),
        normalization=str(parse_quality["extraction_method"]),
        extraction=dict(parse_quality["extraction"]),
        source_span=dict(parse_quality["source_span"]),
    )
    result = DocumentParseResult(
        status=status,
        text=normalized_text,
        chunks=typed_chunks,
        summary=summary,
        lineage=transform_lineage,
        metadata={
            "filename": filename or "",
            "mime_type": normalized_mime,
            "size": len(raw_text.encode("utf-8", errors="ignore")),
            "backend_available": DOCUMENTS_AVAILABLE,
            "parser_version": PARSER_VERSION,
            "source": source,
            "chunk_count": len(typed_chunks),
            "paragraph_count": len(paragraphs),
            "text_length": len(normalized_text),
            "input_format": input_format,
            "page_count": parse_quality["page_count"],
            "extraction_method": parse_quality["extraction_method"],
            "parse_quality": {
                "quality_score": parse_quality["quality_score"],
                "quality_tier": parse_quality["quality_tier"],
                "quality_flags": list(parse_quality["quality_flags"]),
                "ocr_used": parse_quality["ocr_used"],
            },
            "source_span": dict(parse_quality["source_span"]),
            "transform_lineage": transform_lineage.as_dict(),
        },
    )
    implementation_status = "implemented" if normalized_text else "empty"
    if normalized_text and not DOCUMENTS_AVAILABLE:
        implementation_status = "fallback"
    return with_adapter_metadata(
        result.as_dict(),
        operation="parse_document_text",
        backend_available=DOCUMENTS_AVAILABLE,
        degraded_reason=DOCUMENTS_ERROR if not DOCUMENTS_AVAILABLE else None,
        implementation_status=implementation_status,
    )


def parse_document_bytes(
    data: bytes,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    source: str = "bytes",
    chunk_size: int = 1000,
    overlap: int = 100,
) -> Dict[str, Any]:
    normalized_mime = _guess_mime_type(filename or "", mime_type or "")
    input_format = detect_document_input_format(data=data, filename=filename, mime_type=normalized_mime)

    if input_format == "html":
        text = _strip_html(_decode_text_fallback(data))
    elif input_format == "email":
        text = _extract_email_text(data)
    elif input_format == "rtf":
        text = _strip_rtf(_decode_text_fallback(data))
    elif input_format == "docx":
        text = _extract_docx_text(data)
    elif input_format == "pdf":
        text = _extract_pdf_text_fallback(data)
    else:
        text = _normalize_whitespace(_decode_text_fallback(data))

    parse_quality = _compute_parse_quality(
        input_format=input_format,
        text=text,
        data=data,
        raw_size=len(data),
    )

    parsed = parse_document_text(
        text,
        filename=filename,
        mime_type=normalized_mime,
        source=source,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    parsed["summary"]["input_format"] = input_format
    parsed["summary"]["extraction_method"] = str(parse_quality["extraction_method"])
    parsed["summary"]["quality_tier"] = str(parse_quality["quality_tier"])
    parsed["summary"]["quality_score"] = float(parse_quality["quality_score"])
    parsed["summary"]["page_count"] = int(parse_quality["page_count"])
    parsed["lineage"]["input_format"] = input_format
    parsed["lineage"]["normalization"] = str(parse_quality["extraction_method"])
    parsed["lineage"]["extraction"] = dict(parse_quality["extraction"])
    parsed["lineage"]["source_span"] = dict(parse_quality["source_span"])
    parsed["metadata"]["input_format"] = input_format
    parsed["metadata"]["page_count"] = parse_quality["page_count"]
    parsed["metadata"]["extraction_method"] = parse_quality["extraction_method"]
    parsed["metadata"]["parse_quality"] = {
        "quality_score": parse_quality["quality_score"],
        "quality_tier": parse_quality["quality_tier"],
        "quality_flags": list(parse_quality["quality_flags"]),
        "ocr_used": parse_quality["ocr_used"],
    }
    parsed["metadata"]["source_span"] = dict(parse_quality["source_span"])
    parsed["metadata"]["transform_lineage"] = dict(parsed["lineage"])
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
        source="file",
        chunk_size=chunk_size,
        overlap=overlap,
    )


def _stable_record_id(source_path: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    seed_parts = [str(source_path or "").strip()]
    if isinstance(metadata, dict):
        seed_parts.extend(
            str(metadata.get(key) or "").strip()
            for key in ("url", "source_url", "title", "source")
            if metadata.get(key)
        )
    seed = "|".join(part for part in seed_parts if part)
    return hashlib.md5(seed.encode("utf-8", errors="ignore")).hexdigest()


def _ensure_output_dir(output_dir: Optional[str | Path]) -> Path:
    target = Path(output_dir) if output_dir else Path("research_results/documents/parsed")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _materialize_parse_record(
    parsed: Dict[str, Any],
    *,
    source_path: str,
    metadata: Optional[Dict[str, Any]] = None,
    output_dir: Optional[str | Path] = None,
    record_id: Optional[str] = None,
    ocr_attempted: bool = False,
    ocr_used: bool = False,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    metadata = dict(metadata or {})
    target_dir = _ensure_output_dir(output_dir)
    resolved_id = record_id or _stable_record_id(source_path, metadata)
    text = str(parsed.get("text") or "")
    parsed_text_path = target_dir / f"{resolved_id}.txt"
    metadata_path = parsed_text_path.with_suffix(".json")
    if text:
        parsed_text_path.write_text(text, encoding="utf-8")

    parse_metadata = dict(parsed.get("metadata") or {})
    content_type = str(
        metadata.get("content_type")
        or metadata.get("mime_type")
        or parse_metadata.get("mime_type")
        or _guess_mime_type(Path(source_path).name, "")
    )
    extraction_method = str(parse_metadata.get("extraction_method") or "")
    parse_quality = dict(parse_metadata.get("parse_quality") or {})
    needs_ocr = bool("requires_ocr_or_binary_pdf" in list(parse_quality.get("quality_flags") or []))
    checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest() if text else ""

    record = {
        "id": resolved_id,
        "status": "success" if text and not error else ("error" if error else "empty"),
        "source_path": str(source_path),
        "parsed_text_path": str(parsed_text_path),
        "metadata_path": str(metadata_path),
        "text": text,
        "text_length": len(text),
        "checksum": checksum,
        "content_type": content_type,
        "extraction_method": extraction_method,
        "ocr_attempted": bool(ocr_attempted),
        "ocr_used": bool(ocr_used),
        "needs_ocr": needs_ocr,
        "error": error or "",
        "metadata": {
            **metadata,
            **parse_metadata,
            "record_id": resolved_id,
            "checksum": checksum,
            "text_length": len(text),
            "source_path": str(source_path),
            "parsed_text_path": str(parsed_text_path),
            "content_type": content_type,
            "ocr_attempted": bool(ocr_attempted),
            "ocr_used": bool(ocr_used),
            "needs_ocr": needs_ocr,
        },
        "parse": parsed,
    }
    metadata_path.write_text(json.dumps(record["metadata"], indent=2), encoding="utf-8")
    return with_adapter_metadata(
        record,
        operation="document_record",
        backend_available=DOCUMENTS_AVAILABLE,
        degraded_reason=DOCUMENTS_ERROR if not DOCUMENTS_AVAILABLE else None,
        implementation_status="implemented" if text else ("error" if error else "empty"),
    )


def extract_text_content(
    path_or_bytes: str | Path | bytes,
    *,
    mime_type: Optional[str] = None,
    filename: Optional[str] = None,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> Dict[str, Any]:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        parsed = parse_document_bytes(
            bytes(path_or_bytes),
            filename=filename,
            mime_type=mime_type,
            source="bytes",
            chunk_size=chunk_size,
            overlap=overlap,
        )
        return with_adapter_metadata(
            {
                "status": parsed.get("status", ""),
                "text": parsed.get("text", ""),
                "text_length": len(str(parsed.get("text") or "")),
                "content_type": _guess_mime_type(filename or "", mime_type or ""),
                "extraction_method": ((parsed.get("metadata") or {}).get("extraction_method") or ""),
                "parse": parsed,
            },
            operation="extract_text_content",
            backend_available=DOCUMENTS_AVAILABLE,
            degraded_reason=DOCUMENTS_ERROR if not DOCUMENTS_AVAILABLE else None,
            implementation_status="implemented",
        )

    path = Path(path_or_bytes)
    parsed = parse_document_file(
        str(path),
        mime_type=mime_type,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return with_adapter_metadata(
        {
            "status": parsed.get("status", ""),
            "text": parsed.get("text", ""),
            "text_length": len(str(parsed.get("text") or "")),
            "content_type": _guess_mime_type(path.name, mime_type or ""),
            "extraction_method": ((parsed.get("metadata") or {}).get("extraction_method") or ""),
            "parse": parsed,
        },
        operation="extract_text_content",
        backend_available=DOCUMENTS_AVAILABLE,
        degraded_reason=DOCUMENTS_ERROR if not DOCUMENTS_AVAILABLE else None,
        implementation_status="implemented",
    )


def parse_pdf_to_record(
    pdf_path: str | Path,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    enable_ocr: bool = True,
    output_dir: Optional[str | Path] = None,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> Dict[str, Any]:
    path = Path(pdf_path)
    if not path.exists():
        return _materialize_parse_record(
            {"text": "", "metadata": {"mime_type": "application/pdf"}},
            source_path=str(path),
            metadata=metadata,
            output_dir=output_dir,
            error="file_not_found",
        )

    parsed = parse_document_file(
        str(path),
        mime_type="application/pdf",
        chunk_size=chunk_size,
        overlap=overlap,
    )
    text = str(parsed.get("text") or "")
    ocr_attempted = False
    ocr_used = False

    if enable_ocr and len(text.strip()) < 100 and shutil.which("ocrmypdf") is not None:
        ocr_attempted = True
        temp_dir = tempfile.mkdtemp(prefix="ipfs-doc-ocr-")
        try:
            ocr_path = Path(temp_dir) / f"{path.stem}_ocr.pdf"
            result = subprocess.run(
                ["ocrmypdf", "--skip-text", str(path), str(ocr_path)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0 and ocr_path.exists():
                ocr_parsed = parse_document_file(
                    str(ocr_path),
                    mime_type="application/pdf",
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                if len(str(ocr_parsed.get("text") or "").strip()) > len(text.strip()):
                    parsed = ocr_parsed
                    ocr_used = True
                    parsed_metadata = dict(parsed.get("metadata") or {})
                    parsed_metadata["extraction_method"] = "ocrmypdf+pdftotext"
                    parse_quality = dict(parsed_metadata.get("parse_quality") or {})
                    parse_quality["ocr_used"] = True
                    parsed_metadata["parse_quality"] = parse_quality
                    parsed["metadata"] = parsed_metadata
        except Exception:
            pass
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    return _materialize_parse_record(
        parsed,
        source_path=str(path),
        metadata=metadata,
        output_dir=output_dir,
        ocr_attempted=ocr_attempted,
        ocr_used=ocr_used,
    )


def ingest_local_document(
    path: str | Path,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    output_dir: Optional[str | Path] = None,
    enable_ocr: bool = True,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> Dict[str, Any]:
    file_path = Path(path)
    mime_type = str(metadata.get("content_type") or metadata.get("mime_type") or "") if isinstance(metadata, dict) else ""
    if detect_document_input_format(filename=file_path.name, mime_type=mime_type) == "pdf":
        return parse_pdf_to_record(
            file_path,
            metadata=metadata,
            enable_ocr=enable_ocr,
            output_dir=output_dir,
            chunk_size=chunk_size,
            overlap=overlap,
        )

    parsed = parse_document_file(
        str(file_path),
        mime_type=mime_type or None,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return _materialize_parse_record(
        parsed,
        source_path=str(file_path),
        metadata=metadata,
        output_dir=output_dir,
    )


def ingest_download_manifest(
    manifest_path: str | Path,
    *,
    output_dir: Optional[str | Path] = None,
    enable_ocr: bool = True,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> Dict[str, Any]:
    path = Path(manifest_path)
    if not path.exists():
        return with_adapter_metadata(
            {"status": "error", "error": "manifest_not_found", "manifest_path": str(path), "records": []},
            operation="ingest_download_manifest",
            backend_available=DOCUMENTS_AVAILABLE,
            degraded_reason=DOCUMENTS_ERROR if not DOCUMENTS_AVAILABLE else None,
            implementation_status="error",
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("downloads", payload) if isinstance(payload, dict) else payload
    records: List[Dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "ok")
        saved_path = row.get("saved_path") or row.get("filepath")
        if status not in {"ok", "success", ""} or not saved_path:
            continue
        saved = Path(str(saved_path))
        if not saved.exists():
            continue
        records.append(
            ingest_local_document(
                saved,
                metadata=row,
                output_dir=output_dir,
                enable_ocr=enable_ocr,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )

    return with_adapter_metadata(
        {
            "status": "success",
            "manifest_path": str(path),
            "record_count": len(records),
            "records": records,
        },
        operation="ingest_download_manifest",
        backend_available=DOCUMENTS_AVAILABLE,
        degraded_reason=DOCUMENTS_ERROR if not DOCUMENTS_AVAILABLE else None,
        implementation_status="implemented",
    )


def summarize_document_parse(document_parse: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(document_parse, dict):
        return {
            "status": "",
            "chunk_count": 0,
            "text_length": 0,
            "parser_version": "",
            "input_format": "",
            "paragraph_count": 0,
        }

    summary = document_parse.get("summary")
    if isinstance(summary, dict):
        return DocumentParseSummary(
            status=str(summary.get("status") or ""),
            chunk_count=int(summary.get("chunk_count", 0) or 0),
            text_length=int(summary.get("text_length", 0) or 0),
            parser_version=str(summary.get("parser_version") or ""),
            input_format=str(summary.get("input_format") or ""),
            paragraph_count=int(summary.get("paragraph_count", 0) or 0),
        ).as_dict()

    metadata = document_parse.get("metadata", {}) if isinstance(document_parse.get("metadata"), dict) else {}
    return _build_parse_summary(
        status=str(document_parse.get("status") or ""),
        text=str(document_parse.get("text") or ""),
        chunks=document_parse.get("chunks", []) or [],
        parser_version=str(metadata.get("parser_version") or ""),
        input_format=str(metadata.get("input_format") or ""),
        paragraph_count=int(metadata.get("paragraph_count", 0) or 0),
    ).as_dict()


__all__ = [
    "InputDetector",
    "BatchProcessor",
    "DOCUMENTS_AVAILABLE",
    "DOCUMENTS_ERROR",
    "PARSER_VERSION",
    "chunk_text",
    "detect_document_input_format",
    "extract_text_content",
    "ingest_download_manifest",
    "ingest_local_document",
    "parse_document_text",
    "parse_document_bytes",
    "parse_document_file",
    "parse_pdf_to_record",
    "should_parse_document_input",
    "summarize_document_parse",
]
