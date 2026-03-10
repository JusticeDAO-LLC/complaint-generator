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


__all__ = ["build_provenance", "stable_content_hash", "merge_metadata_with_provenance"]