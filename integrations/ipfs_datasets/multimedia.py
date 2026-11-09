"""Multimedia ingest through ipfs_datasets_py.processors.multimedia.

Missing ffmpeg or yt-dlp degrades the result. It does not raise at import.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .loader import import_attr_optional, import_module_optional
from .types import with_adapter_metadata


def _missing_tools(*names: str) -> list[str]:
    return [name for name in names if not shutil.which(name)]


def _degraded(operation: str, reason: str, *, missing_tools: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return with_adapter_metadata(
        {
            "status": "degraded",
            "text": "",
            "error": reason,
            "missing_tools": list(missing_tools or []),
            **extra,
        },
        operation=operation,
        backend_available=False,
        degraded_reason=reason,
        implementation_status="degraded",
    )


def extract_attachment_text(*args: Any, **kwargs: Any) -> Any:
    """Pass through the upstream attachment extractor when it imports."""

    extractor, error = import_attr_optional(
        "ipfs_datasets_py.processors.multimedia.attachment_text_extractor",
        "extract_attachment_text",
    )
    if extractor is None:
        return _degraded(
            "extract_attachment_text",
            str(error or "attachment_text_extractor unavailable"),
        )
    return extractor(*args, **kwargs)


def extract_transcript_or_text(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    source = Path(path)
    missing = _missing_tools("ffmpeg") if source.suffix.lower() in {".mp4", ".mov", ".mp3", ".wav", ".m4a"} else []
    if missing:
        return _degraded(
            "extract_transcript_or_text",
            f"missing tool: {', '.join(missing)}",
            missing_tools=missing,
            path=str(source),
        )
    extracted = extract_attachment_text(str(source), **kwargs)
    if isinstance(extracted, dict) and extracted.get("status") == "degraded":
        return extracted
    text = extracted if isinstance(extracted, str) else str(getattr(extracted, "text", extracted) or "")
    return with_adapter_metadata(
        {
            "status": "available",
            "text": text,
            "path": str(source),
            "missing_tools": [],
        },
        operation="extract_transcript_or_text",
        backend_available=True,
        implementation_status="available",
    )


def ingest_media_file(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    source = Path(path)
    module, error = import_module_optional("ipfs_datasets_py.processors.multimedia")
    missing = _missing_tools("ffmpeg", "yt-dlp") if source.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"} else []
    if module is None:
        return _degraded(
            "ingest_media_file",
            str(error or "processors.multimedia unavailable"),
            missing_tools=missing,
            path=str(source),
        )
    if missing and not source.exists():
        return _degraded(
            "ingest_media_file",
            f"missing tool: {', '.join(missing)}",
            missing_tools=missing,
            path=str(source),
        )
    transcript = extract_transcript_or_text(source, **kwargs)
    return with_adapter_metadata(
        {
            "status": transcript.get("status") or "available",
            "path": str(source),
            "text": transcript.get("text") or "",
            "missing_tools": list(transcript.get("missing_tools") or missing),
            "module": "ipfs_datasets_py.processors.multimedia",
        },
        operation="ingest_media_file",
        backend_available=module is not None and transcript.get("status") != "degraded",
        degraded_reason=transcript.get("error"),
        implementation_status="available" if transcript.get("status") == "available" else "degraded",
    )


def normalize_email_export(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    source = Path(path)
    normalizer, error = import_attr_optional(
        "ipfs_datasets_py.processors.multimedia",
        "normalize_email_export",
    )
    if normalizer is None:
        text_result = extract_transcript_or_text(source, **kwargs)
        if text_result.get("status") == "degraded" and not source.exists():
            return _degraded(
                "normalize_email_export",
                str(error or text_result.get("error") or "email export normalizer unavailable"),
                path=str(source),
            )
        return with_adapter_metadata(
            {
                "status": text_result.get("status") or "degraded",
                "path": str(source),
                "text": text_result.get("text") or "",
                "normalizer": "attachment_text_extractor",
            },
            operation="normalize_email_export",
            backend_available=text_result.get("status") == "available",
            degraded_reason=None if text_result.get("status") == "available" else str(error or ""),
            implementation_status="degraded",
        )
    normalized = normalizer(str(source), **kwargs)
    payload = normalized if isinstance(normalized, dict) else {"text": str(normalized or "")}
    return with_adapter_metadata(
        {
            "status": "available",
            "path": str(source),
            "normalizer": "processors.multimedia.normalize_email_export",
            **payload,
        },
        operation="normalize_email_export",
        backend_available=True,
        implementation_status="available",
    )


__all__ = [
    "extract_attachment_text",
    "extract_transcript_or_text",
    "ingest_media_file",
    "normalize_email_export",
]
