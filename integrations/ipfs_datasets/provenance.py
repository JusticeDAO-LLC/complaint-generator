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


def _merge_nonempty_values(base: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = dict(base)
    if not isinstance(extra, dict):
        return payload

    for key, value in extra.items():
        if value in (None, "", [], (), {}):
            continue
        existing = payload.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            payload[key] = _merge_nonempty_values(existing, value)
        else:
            payload[key] = value
    return payload


def merge_metadata_with_provenance(
    metadata: Optional[Dict[str, Any]],
    provenance: ProvenanceRecord,
) -> Dict[str, Any]:
    payload = dict(metadata or {})
    payload.setdefault("provenance", provenance.as_dict())
    return payload


def enrich_document_parse(
    document_parse: Optional[Dict[str, Any]],
    *,
    default_source: str = "",
    extra_summary: Optional[Dict[str, Any]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    extra_lineage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(document_parse, dict):
        return {}

    payload = dict(document_parse)
    summary = dict(payload.get("summary") or {})
    metadata = dict(payload.get("metadata") or {})
    lineage = metadata.get("transform_lineage")
    if not isinstance(lineage, dict):
        lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
    lineage = dict(lineage)

    source = str(metadata.get("source") or lineage.get("source") or summary.get("source") or default_source or "")
    if source:
        metadata["source"] = source
        summary["source"] = source
        lineage["source"] = source

    summary = _merge_nonempty_values(summary, extra_summary)
    metadata = _merge_nonempty_values(metadata, extra_metadata)
    lineage = _merge_nonempty_values(lineage, extra_lineage)
    metadata["transform_lineage"] = lineage

    payload["metadata"] = metadata
    payload["lineage"] = lineage
    if summary:
        payload["summary"] = summary
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
    transform_lineage = metadata.get("transform_lineage") if isinstance(metadata.get("transform_lineage"), dict) else {}
    source = str(metadata.get("source") or transform_lineage.get("source") or default_source or "")
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
        if not payload.get("source") and lineage.get("source"):
            payload["source"] = lineage.get("source")
    return payload


def build_document_parse_contract(
    document_parse: Optional[Dict[str, Any]],
    *,
    default_source: str = "",
    preview_length: int = 5000,
) -> Dict[str, Any]:
    if not isinstance(document_parse, dict):
        return {
            "status": "",
            "source": default_source,
            "chunk_count": 0,
            "text": "",
            "text_preview": "",
            "summary": {},
            "storage_metadata": {},
            "lineage": {},
            "parse_quality": {},
            "source_span": {},
        }

    summary = build_document_parse_summary_metadata(document_parse, default_source=default_source)
    storage_metadata = build_storage_parse_metadata(document_parse, default_source=default_source)
    text = str(document_parse.get("text") or "")
    chunk_count = int(summary.get("chunk_count", len(document_parse.get("chunks", []) or [])) or 0)
    source = str(storage_metadata.get("source") or summary.get("source") or default_source or "")
    lineage = storage_metadata.get("transform_lineage")
    if not isinstance(lineage, dict):
        lineage = {}
    parse_quality = storage_metadata.get("parse_quality") if isinstance(storage_metadata.get("parse_quality"), dict) else {}
    source_span = storage_metadata.get("source_span") if isinstance(storage_metadata.get("source_span"), dict) else {}

    return {
        "status": str(document_parse.get("status") or summary.get("status") or ""),
        "source": source,
        "chunk_count": chunk_count,
        "text": text,
        "text_preview": text[: max(preview_length, 0)] if preview_length else "",
        "summary": summary,
        "storage_metadata": storage_metadata,
        "lineage": dict(lineage),
        "parse_quality": dict(parse_quality),
        "source_span": dict(source_span),
    }


def build_fact_lineage_metadata(
    metadata: Optional[Dict[str, Any]] = None,
    *,
    parse_contract: Optional[Dict[str, Any]] = None,
    record_scope: str = "",
    source_ref: str = "",
) -> Dict[str, Any]:
    payload = dict(metadata or {})
    parse_contract = parse_contract if isinstance(parse_contract, dict) else {}
    summary = parse_contract.get("summary") if isinstance(parse_contract.get("summary"), dict) else {}
    lineage = parse_contract.get("lineage") if isinstance(parse_contract.get("lineage"), dict) else {}

    parse_lineage = {
        "status": str(parse_contract.get("status") or summary.get("status") or ""),
        "source": str(parse_contract.get("source") or summary.get("source") or ""),
        "parser_version": str(summary.get("parser_version") or lineage.get("parser_version") or ""),
        "input_format": str(summary.get("input_format") or lineage.get("input_format") or ""),
        "quality_tier": str(summary.get("quality_tier") or (parse_contract.get("parse_quality") or {}).get("quality_tier") or ""),
        "quality_score": float(summary.get("quality_score") or (parse_contract.get("parse_quality") or {}).get("quality_score") or 0.0),
        "transform_lineage": dict(lineage),
        "parse_quality": dict(parse_contract.get("parse_quality") or {}),
        "source_span": dict(parse_contract.get("source_span") or {}),
    }
    if record_scope:
        parse_lineage["record_scope"] = record_scope
    if source_ref:
        parse_lineage["source_ref"] = source_ref
    payload["parse_lineage"] = parse_lineage
    return payload


__all__ = [
    "build_provenance",
    "stable_content_hash",
    "enrich_document_parse",
    "merge_metadata_with_provenance",
    "build_document_parse_summary_metadata",
    "build_storage_parse_metadata",
    "build_document_parse_contract",
    "build_fact_lineage_metadata",
]