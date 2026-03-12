from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

from .types import ProvenanceRecord


def build_provenance(
    *,
    source_url: str = "",
    acquisition_method: str = "",
    source_type: str = "",
    acquired_at: Optional[str] = None,
    content_hash: str = "",
    source_system: str = "",
    jurisdiction: str = "",
) -> ProvenanceRecord:
    return ProvenanceRecord(
        source_url=source_url,
        acquisition_method=acquisition_method,
        source_type=source_type,
        acquired_at=acquired_at or datetime.now().isoformat(),
        content_hash=content_hash,
        source_system=source_system,
        jurisdiction=jurisdiction,
    )


def stable_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merge_metadata_with_provenance(
    metadata: Optional[Dict[str, Any]],
    provenance: ProvenanceRecord,
) -> Dict[str, Any]:
    payload = dict(metadata or {})
    payload.setdefault("provenance", provenance.as_dict())
    return payload


def build_document_parse_summary_metadata(
    document_parse: Optional[Dict[str, Any]],
    *,
    default_source: str = "",
) -> Dict[str, Any]:
    if not isinstance(document_parse, dict):
        return {}

    summary = document_parse.get("summary")
    payload = dict(summary) if isinstance(summary, dict) else {}
    metadata = document_parse.get("metadata") if isinstance(document_parse.get("metadata"), dict) else {}
    source = str(metadata.get("source") or default_source or "")
    if source:
        payload["source"] = source
    return payload


def build_storage_parse_metadata(
    document_parse: Optional[Dict[str, Any]],
    *,
    default_source: str = "",
) -> Dict[str, Any]:
    if not isinstance(document_parse, dict):
        return {}

    metadata = dict(document_parse.get("metadata") or {})
    summary = build_document_parse_summary_metadata(document_parse, default_source=default_source)
    payload = {
        **metadata,
        **{key: value for key, value in summary.items() if value not in (None, "")},
    }
    transform_lineage = payload.get("transform_lineage")
    if isinstance(transform_lineage, dict):
        lineage = dict(transform_lineage)
        if default_source and not lineage.get("source"):
            lineage["source"] = default_source
        payload["transform_lineage"] = lineage
    return payload


__all__ = [
    "build_provenance",
    "stable_content_hash",
    "merge_metadata_with_provenance",
    "build_document_parse_summary_metadata",
    "build_storage_parse_metadata",
]