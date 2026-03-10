from __future__ import annotations

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


def _decode_text_fallback(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def chunk_text(text: str, chunk_size: int = 1000) -> List[Dict[str, Any]]:
    if chunk_size <= 0:
        chunk_size = 1000
    chunks: List[Dict[str, Any]] = []
    for index, start in enumerate(range(0, len(text), chunk_size)):
        content = text[start:start + chunk_size]
        chunks.append(
            {
                "chunk_id": f"chunk-{index}",
                "index": index,
                "start": start,
                "end": start + len(content),
                "text": content,
            }
        )
    return chunks


def parse_document_bytes(
    data: bytes,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> Dict[str, Any]:
    text = _decode_text_fallback(data)
    status = "fallback" if text else "empty"
    if DOCUMENTS_AVAILABLE:
        status = "available-fallback"
    return {
        "status": status,
        "text": text,
        "chunks": chunk_text(text),
        "metadata": {
            "filename": filename or "",
            "mime_type": mime_type or "",
            "size": len(data),
            "backend_available": DOCUMENTS_AVAILABLE,
        },
    }


__all__ = [
    "InputDetector",
    "BatchProcessor",
    "DOCUMENTS_AVAILABLE",
    "DOCUMENTS_ERROR",
    "chunk_text",
    "parse_document_bytes",
]