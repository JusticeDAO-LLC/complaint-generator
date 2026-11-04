"""Evidence management hooks for mediator.

Broad-exception audit (REF-017)
---------------------------------
Broad handlers in this module guard two production boundaries: optional IPFS
storage/document tooling and DuckDB persistence.  Dependency exceptions are
not stable enough to catch by a common narrower base class.  Storage commands
therefore raise typed hook errors with their original cause.  High-traffic
list queries use :class:`DegradedEvidenceResults`, which remains list-compatible
but distinguishes a failed query from a valid empty result.  Point lookups also
raise a typed query error instead of conflating an operational failure with a
valid not-found result.  The only local filesystem preparation handler is
narrowed to ``OSError``.
"""

import os
import json
import hashlib
import mimetypes
import base64
import uuid
from typing import Dict, List, Optional, Any, BinaryIO
from datetime import datetime, timedelta, UTC
from pathlib import Path

from integrations.ipfs_datasets.provenance import (
    build_document_parse_contract,
    build_fact_lineage_metadata,
    build_storage_parse_metadata,
    build_provenance,
    merge_metadata_with_provenance,
    stable_content_hash,
)
from integrations.ipfs_datasets.documents import parse_document, should_parse_document_input
from integrations.ipfs_datasets.graphs import extract_graph_from_text, persist_graph_snapshot
from integrations.ipfs_datasets.types import CaseArtifact, CaseFact
from integrations.ipfs_datasets.storage import (
    AUTOMATIC_PRIVATE_ARTIFACT_KINDS,
    IPFS_AVAILABLE,
    PUBLIC_LEGAL_CONTENT_ORIGINS,
    PUBLIC_LEGAL_CORPUS_FAMILIES,
    add_bytes,
    cat,
    get_ipfs_backend,
    pin,
    retrieve_private_artifact,
    store_automatic_private_artifact,
    store_public_legal_corpus,
)
from claim_support_review import _merge_intake_summary_handoff_metadata

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


_CONTENT_ORIGIN_ARTIFACT_FAMILY = {
    'historical_archive_capture': 'archived_web_page',
    'live_web_capture': 'live_web_page',
    'authority_full_text': 'legal_authority_text',
    'authority_reference_fallback': 'legal_authority_reference',
}

_ARTIFACT_FAMILY_CORPUS_FAMILY = {
    'archived_web_page': 'web_page',
    'live_web_page': 'web_page',
    'legal_authority_text': 'legal_authority',
    'legal_authority_reference': 'legal_authority',
}

_EVIDENCE_FACT_DURABLE_COLUMNS = {
    'source_family': 'VARCHAR',
    'source_record_id': 'BIGINT',
    'source_ref': 'VARCHAR',
    'record_scope': 'VARCHAR',
    'artifact_family': 'VARCHAR',
    'corpus_family': 'VARCHAR',
    'content_origin': 'VARCHAR',
    'parse_source': 'VARCHAR',
    'input_format': 'VARCHAR',
    'quality_tier': 'VARCHAR',
    'quality_score': 'DOUBLE',
    'page_count': 'INTEGER',
    'chunk_id': 'VARCHAR',
    'chunk_index': 'INTEGER',
    'source_passage': 'JSON',
}

_MAX_SOURCE_PASSAGE_TEXT_LENGTH = 500


def _ensure_evidence_fact_schema(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence_facts (
            evidence_id BIGINT,
            fact_id VARCHAR,
            fact_text TEXT,
            source_artifact_id VARCHAR,
            confidence FLOAT,
            metadata JSON,
            provenance JSON
        )
    """)
    for column_name, column_type in _EVIDENCE_FACT_DURABLE_COLUMNS.items():
        conn.execute(
            f"ALTER TABLE evidence_facts ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
        )


def _list_table_columns(conn: Any, table_name: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return [str(row[1]) for row in rows]


class EvidenceHookError(RuntimeError):
    """Base error for a failed evidence hook operation."""


class EvidenceStorageError(EvidenceHookError):
    """Evidence could not be normalized or stored."""

    def __init__(self, message: str = "", *, code: str = "storage_error", public_status: str = "unavailable") -> None:
        super().__init__(message)
        self.code = code
        self.public_status = public_status


class EvidenceRetrievalError(EvidenceHookError):
    """Evidence could not be retrieved from the configured backend."""

    def __init__(self, message: str = "", *, code: str = "retrieval_error", public_status: str = "unavailable") -> None:
        super().__init__(message)
        self.code = code
        self.public_status = public_status


class EvidencePersistenceError(EvidenceHookError):
    """Evidence metadata could not be persisted."""


class PrivateDerivedIndexUnavailable(EvidenceHookError):
    """Private derived text could not be contained without a plaintext fallback."""

    def __init__(self, message: str = "", *, code: str = "persistence_unavailable") -> None:
        super().__init__(message or "Private derived index is unavailable.")
        self.code = code
        self.public_status = "unavailable"


class PrivateDerivedIndex:
    """Case-owned index for private derived text.

    Directory names and permission bits are recorded and are never treated as
    encryption. Durable mode seals through the private artifact owner. Ephemeral
    mode keeps plaintext only in this process and can be rebuilt only from that
    owner, never from a plaintext fallback file.
    """

    def __init__(self) -> None:
        self.bound = False
        self.unavailable_code = ""
        self.context: Optional[Dict[str, Any]] = None
        self.mode = "unbound"
        self.case_id = ""
        self.directory_mode_private = False
        self.entries: Dict[str, Dict[str, Any]] = {}
        self.public_law_cache: Dict[str, Dict[str, str]] = {}
        self.created_rows: List[int] = []
        self._secrets: List[str] = []
        self._counter = 0
        self._row_counter = 0
        self.closed = False
        self.plaintext_fallback_published = False

    def bind(
        self,
        context: Optional[Dict[str, Any]],
        *,
        unavailable_code: str = "",
        directory_mode_private: bool = False,
    ) -> None:
        self.bound = True
        self.closed = False
        self.directory_mode_private = bool(directory_mode_private)
        self.unavailable_code = str(unavailable_code or "")
        self.entries = {}
        self.created_rows = []
        self._secrets = []
        self.context = None
        self.case_id = ""
        if self.unavailable_code or not context:
            self.mode = "unavailable"
            return
        case_id = str(context.get("case_id") or "")
        if not case_id:
            self.mode = "unavailable"
            self.unavailable_code = self.unavailable_code or "case_unavailable"
            return
        self.case_id = case_id
        self.context = {
            "access": context.get("access"),
            "tenant_id": context.get("tenant_id"),
            "case_id": case_id,
            "principal_id": context.get("principal_id") or context.get("tenant_id"),
            "key_provider": context.get("key_provider"),
            "backend": context.get("backend"),
            "backend_name": context.get("backend_name") or "local_cache",
            "pin_content": bool(context.get("pin_content", False)),
        }
        requested = str(context.get("index_mode") or "ephemeral")
        if requested == "durable":
            if not self.context.get("key_provider"):
                self.mode = "unavailable"
                self.unavailable_code = "key_unavailable"
                return
            self.mode = "durable"
            return
        self.mode = "ephemeral"

    def status(self) -> Dict[str, Any]:
        encrypted = self.mode == "durable" and not self.unavailable_code and not self.closed
        return {
            "status": "unavailable" if self.mode in {"unavailable", "unbound"} or self.unavailable_code else "available",
            "code": self.unavailable_code,
            "index_mode": self.mode,
            "case_id": self.case_id,
            "encrypted": encrypted,
            "encryption_from_path_or_mode_bits": False,
            "directory_mode_private": self.directory_mode_private,
            "plaintext_fallback": False,
            "plaintext_fallback_published": self.plaintext_fallback_published,
            "owned": self.bound and self.mode in {"durable", "ephemeral"},
            "rebuildable": self.mode in {"durable", "ephemeral"},
            "closed": self.closed,
        }

    def accepts_writes(self) -> bool:
        return self.bound and self.mode in {"durable", "ephemeral"} and not self.closed and not self.unavailable_code

    def contain(self, text: str, *, kind: str) -> str:
        if not self.accepts_writes():
            raise PrivateDerivedIndexUnavailable(
                "Private derived index is unavailable.",
                code=self.unavailable_code or "persistence_unavailable",
            )
        payload = str(text)
        if self.mode == "ephemeral":
            self._counter += 1
            token = f"cgidx:eph:{self._counter}"
            self.entries[token] = {
                "text": payload,
                "case_id": self.case_id,
                "kind": kind,
                "durable": False,
            }
            self._secrets.append(payload)
            return token
        self._counter += 1
        revision = f"index-{uuid.uuid4().hex}"
        body = json.dumps({"text": payload, "kind": kind, "case_id": self.case_id}, sort_keys=True).encode("utf-8")
        try:
            from integrations.private_storage import (
                PrivateCryptoCapabilityError,
                PrivateKeyMaterialError,
                PrivateStorageError,
                store_private_artifact,
            )

            context = self.context or {}
            receipt = store_private_artifact(
                body,
                access=context.get("access"),
                tenant_id=str(context.get("tenant_id") or ""),
                case_id=self.case_id,
                artifact_kind="index",
                revision=revision,
                principal_id=str(context.get("principal_id") or ""),
                key_provider=context.get("key_provider"),
                backend=context.get("backend"),
                backend_name=str(context.get("backend_name") or "local_cache"),
                pin_content=bool(context.get("pin_content", False)),
            )
            cid = str(receipt.get("cid") or "")
            if not cid or str(receipt.get("status") or "") not in {"available", "degraded"}:
                raise PrivateDerivedIndexUnavailable("Private derived index is unavailable.", code="persistence_unavailable")
            entry = {"case_id": self.case_id, "kind": kind, "durable": True,
                "cid": cid, "revision": revision, "text": None}
            token = self._seal_durable_reference(entry)
        except PrivateDerivedIndexUnavailable:
            raise
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "")
            if not code:
                name = type(exc).__name__
                if "Key" in name:
                    code = "key_unavailable"
                elif "Crypto" in name:
                    code = "private_crypto_unavailable"
                else:
                    code = "persistence_unavailable"
            raise PrivateDerivedIndexUnavailable(
                "Private derived index is unavailable.",
                code=code,
            ) from exc
        self.entries[token] = entry
        self._secrets.append(payload)
        return token

    def _reference_key(self):
        """Resolve current authority; a token never supplies its own AAD or key."""
        from integrations.private_storage import (
            PrivateArtifactBinding, PrivateKeyMaterialError, assert_access_matches_binding,
        )
        context = self.context or {}
        binding = PrivateArtifactBinding(tenant_id=str(context.get("tenant_id") or ""),
            case_id=self.case_id, artifact_kind="index-reference", revision="v1",
            principal_id=str(context.get("principal_id") or ""))
        assert_access_matches_binding(context.get("access"), binding)
        provider = context.get("key_provider")
        if provider is None:
            raise PrivateKeyMaterialError("key_unavailable")
        key_id, key = provider.resolve(binding)
        return binding, key_id, key

    def _seal_durable_reference(self, entry: Dict[str, Any]) -> str:
        """Persist the reference as ciphertext, without a process-local lookup."""
        from integrations.private_storage import PrivateArtifactIntegrityError, seal_private_artifact
        binding, key_id, key = self._reference_key()
        descriptor = {name: entry[name] for name in ("cid", "revision", "kind")}
        raw = json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(raw, binding=binding, key=key, key_id=key_id)
        encoded = base64.urlsafe_b64encode(envelope).decode("ascii")
        if len(encoded) > 16384:
            raise PrivateArtifactIntegrityError("oversized")
        return "cgidx:ref:v1:" + encoded

    def _open_durable_reference(self, token: str) -> Dict[str, Any]:
        from integrations.private_storage import PrivateArtifactIntegrityError, open_private_artifact
        # A reference is small routing ciphertext, never a replacement for the
        # separately authenticated content artifact or its current key owner.
        encoded = token[len("cgidx:ref:v1:"):]
        if not encoded or len(encoded) > 16384:
            raise PrivateArtifactIntegrityError("malformed")
        try:
            envelope = base64.b64decode(encoded, altchars=b"-_", validate=True)
        except (ValueError, UnicodeEncodeError):
            raise PrivateArtifactIntegrityError("malformed") from None
        binding, key_id, key = self._reference_key()
        raw = open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id)
        try:
            descriptor = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PrivateArtifactIntegrityError("malformed") from None
        if not isinstance(descriptor, dict) or set(descriptor) != {"cid", "revision", "kind"}:
            raise PrivateArtifactIntegrityError("malformed")
        if any(not isinstance(value, str) or not value for value in descriptor.values()):
            raise PrivateArtifactIntegrityError("malformed")
        return {**descriptor, "case_id": self.case_id, "durable": True, "text": None}

    def cache_public_law(self, *, citation: str, text: str) -> str:
        digest = hashlib.sha256(f"{citation}\n{text}".encode("utf-8")).hexdigest()[:24]
        cache_id = f"pubcache:{digest}"
        self.public_law_cache[cache_id] = {
            "citation": str(citation or ""),
            "text": str(text or ""),
            "storage_class": "public_legal_corpus",
        }
        return cache_id

    def reveal(self, token: str, *, case_id: str = "") -> Dict[str, Any]:
        expected = case_id or self.case_id
        if expected and expected != self.case_id:
            return {"status": "unavailable", "code": "case_mismatch", "plaintext_fallback": False}
        if self.mode == "unavailable":
            return {
                "status": "unavailable",
                "code": self.unavailable_code or "persistence_unavailable",
                "plaintext_fallback": False,
            }
        if self.mode == "ephemeral" and self.closed:
            return {"status": "unavailable", "code": "index_closed", "plaintext_fallback": False}
        if self.mode == "durable" and isinstance(token, str) and token.startswith("cgidx:ref:v1:"):
            try:
                entry = self._open_durable_reference(token)
            except Exception as exc:
                return {"status": "unavailable", "code": str(getattr(exc, "code", "") or "persistence_unavailable"),
                    "plaintext_fallback": False}
        else:
            # Old counter-only tokens remain usable by their original warm
            # owner. Missing historical mappings cannot be reconstructed.
            entry = self.entries.get(token)
        if not entry or entry.get("case_id") != self.case_id:
            return {"status": "unavailable", "code": "case_mismatch", "plaintext_fallback": False}
        if entry.get("durable"):
            opened = self._open_durable(entry)
            if opened.get("status") != "available":
                return opened
            self.entries[token] = entry
            return {"status": "available", "text": opened["text"], "case_id": self.case_id, "encrypted": True}
        if self.closed:
            return {"status": "unavailable", "code": "index_closed", "plaintext_fallback": False}
        return {"status": "available", "text": entry.get("text") or "", "case_id": self.case_id, "encrypted": False}

    def _open_durable(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        context = self.context or {}
        try:
            from integrations.private_storage import retrieve_private_artifact

            opened = retrieve_private_artifact(
                str(entry.get("cid") or ""),
                access=context.get("access"),
                tenant_id=str(context.get("tenant_id") or ""),
                case_id=self.case_id,
                artifact_kind="index",
                revision=str(entry.get("revision") or ""),
                principal_id=str(context.get("principal_id") or ""),
                key_provider=context.get("key_provider"),
                backend=context.get("backend"),
                backend_name=str(context.get("backend_name") or "local_cache"),
            )
        except Exception as exc:
            return {
                "status": "unavailable",
                "code": str(getattr(exc, "code", "") or "persistence_unavailable"),
                "plaintext_fallback": False,
            }
        data = opened.get("data")
        if not isinstance(data, (bytes, bytearray)):
            return {"status": "unavailable", "code": "persistence_unavailable", "plaintext_fallback": False}
        try:
            payload = json.loads(bytes(data).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"status": "unavailable", "code": "persistence_unavailable", "plaintext_fallback": False}
        if str(payload.get("case_id") or "") != self.case_id:
            return {"status": "unavailable", "code": "case_mismatch", "plaintext_fallback": False}
        if payload.get("kind") != entry.get("kind"):
            return {"status": "unavailable", "code": "binding_rejected", "plaintext_fallback": False}
        return {"status": "available", "text": str(payload.get("text") or "")}

    def close(self, *, crash: bool = False) -> Dict[str, Any]:
        self.closed = True
        self._secrets = []
        if self.mode == "ephemeral":
            self.entries = {}
        else:
            for entry in self.entries.values():
                entry["text"] = None
        return {
            "status": "closed",
            "crash": bool(crash),
            "plaintext_fallback_published": False,
            "plaintext_fallback": False,
            "case_id": self.case_id,
        }

    def rebuild(self) -> Dict[str, Any]:
        if not self.bound or self.mode == "unavailable":
            return {
                "status": "unavailable",
                "code": self.unavailable_code or "persistence_unavailable",
                "rebuilt": 0,
                "plaintext_fallback": False,
            }
        if self.mode == "ephemeral":
            if self.closed or not self.entries:
                return {
                    "status": "unavailable",
                    "code": "ephemeral_closed",
                    "rebuilt": 0,
                    "plaintext_fallback": False,
                    "case_id": self.case_id,
                }
            own = [entry for entry in self.entries.values() if entry.get("case_id") == self.case_id]
            return {
                "status": "available",
                "rebuilt": len(own),
                "case_id": self.case_id,
                "plaintext_fallback": False,
                "encrypted": False,
            }
        rebuilt = 0
        for entry in list(self.entries.values()):
            if entry.get("case_id") != self.case_id or not entry.get("durable"):
                continue
            opened = self._open_durable(entry)
            if opened.get("status") != "available":
                return {
                    "status": "unavailable",
                    "code": opened.get("code") or "persistence_unavailable",
                    "rebuilt": rebuilt,
                    "plaintext_fallback": False,
                }
            entry["text"] = opened["text"]
            rebuilt += 1
        self.closed = False
        return {
            "status": "available",
            "rebuilt": rebuilt,
            "case_id": self.case_id,
            "plaintext_fallback": False,
            "encrypted": True,
        }


class PrivateDerivedIndexMixin:
    """Constructor-level private column containment shared by hook databases."""

    def _derived(self) -> PrivateDerivedIndex:
        index = getattr(self, "_derived_index_state", None)
        if index is None:
            index = PrivateDerivedIndex()
            self._derived_index_state = index
        return index

    def bind_private_derived_index(
        self,
        context: Optional[Dict[str, Any]],
        *,
        unavailable_code: str = "",
        directory_mode_private: bool = False,
    ) -> Dict[str, Any]:
        self._derived().bind(
            context,
            unavailable_code=unavailable_code,
            directory_mode_private=directory_mode_private,
        )
        return self.private_derived_index_status()

    def private_derived_index_status(self) -> Dict[str, Any]:
        return self._derived().status()

    def _private_columns_sealed(self) -> bool:
        return self._derived().accepts_writes()

    def _seal_column(self, value: Any, kind: str) -> Any:
        if not self._private_columns_sealed() or value is None:
            return value
        text = str(value)
        if text == "":
            return text
        return self._derived().contain(text, kind=kind)

    def _seal_json(self, payload: Any) -> str:
        if not self._private_columns_sealed():
            return json.dumps(payload if payload is not None else {})
        return json.dumps(self._seal_nested(payload))

    def _seal_nested(self, value: Any, *, kind: str = "nested") -> Any:
        if not self._private_columns_sealed():
            return value
        if isinstance(value, str):
            if len(value) < 8:
                return value
            return self._seal_column(value, kind)
        if isinstance(value, dict):
            return {key: self._seal_nested(item, kind=str(key)) for key, item in value.items()}
        if isinstance(value, list):
            return [self._seal_nested(item, kind=kind) for item in value]
        return value

    def cache_public_law_source(self, *, citation: str, text: str) -> Dict[str, Any]:
        cache_id = self._derived().cache_public_law(citation=citation, text=text)
        return {
            "status": "available",
            "cache_id": cache_id,
            "storage_class": "public_legal_corpus",
            "separated_from_private_associations": True,
        }

    def read_public_law_source(self, cache_id: str) -> Dict[str, Any]:
        found = self._derived().public_law_cache.get(cache_id)
        if not found:
            return {"status": "unavailable", "code": "public_cache_miss"}
        return {"status": "available", **found}

    def commit_private_derived(
        self,
        *,
        case_id: str,
        kind: str,
        text: str,
        public_cache_id: str = "",
    ) -> Dict[str, Any]:
        index = self._derived()
        if not index.bound or index.mode == "unavailable" or index.unavailable_code:
            return {
                "status": "unavailable",
                "code": index.unavailable_code or "persistence_unavailable",
                "plaintext_persisted": False,
                "plaintext_fallback": False,
                "persisted": False,
            }
        if str(case_id or "") != index.case_id:
            return {
                "status": "unavailable",
                "code": "case_mismatch",
                "plaintext_persisted": False,
                "plaintext_fallback": False,
                "persisted": False,
            }
        try:
            token = index.contain(str(text or ""), kind=kind)
        except PrivateDerivedIndexUnavailable as exc:
            return {
                "status": "unavailable",
                "code": exc.code,
                "plaintext_persisted": False,
                "plaintext_fallback": False,
                "persisted": False,
            }
        db_path = getattr(self, "db_path", None)
        if not DUCKDB_AVAILABLE or not db_path:
            return {
                "status": "unavailable" if index.mode == "durable" else "available",
                "code": "persistence_unavailable" if index.mode == "durable" else "",
                "token": token,
                "plaintext_persisted": False,
                "plaintext_fallback": False,
                "row_persisted": False,
                "index_mode": index.mode,
                "case_id": index.case_id,
            }
        try:
            conn = duckdb.connect(db_path)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS private_derived_index (
                    id BIGINT,
                    case_id VARCHAR,
                    kind VARCHAR,
                    token VARCHAR,
                    public_cache_id VARCHAR
                )
                """
            )
            index._row_counter += 1
            row_id = index._row_counter
            conn.execute(
                "INSERT INTO private_derived_index VALUES (?, ?, ?, ?, ?)",
                [row_id, index.case_id, kind, token, public_cache_id or ""],
            )
            conn.close()
        except Exception:
            return {
                "status": "unavailable",
                "code": "persistence_unavailable",
                "plaintext_persisted": False,
                "plaintext_fallback": False,
                "persisted": False,
            }
        index.created_rows.append(row_id)
        return {
            "status": "available",
            "row_id": row_id,
            "token": token,
            "case_id": index.case_id,
            "index_mode": index.mode,
            "encrypted": index.mode == "durable",
            "encryption_from_path_or_mode_bits": False,
            "plaintext_persisted": False,
            "plaintext_fallback": False,
            "row_persisted": True,
            "public_cache_id": public_cache_id or "",
        }

    def read_private_derived(self, token: str, *, case_id: str = "") -> Dict[str, Any]:
        return self._derived().reveal(token, case_id=case_id)

    def close_private_derived_index(self, *, crash: bool = False) -> Dict[str, Any]:
        return self._derived().close(crash=crash)

    def rebuild_private_derived_index(self) -> Dict[str, Any]:
        rebuilt = self._derived().rebuild()
        if rebuilt.get("status") != "available" or self._derived().mode != "durable":
            return rebuilt
        for entry in self._derived().entries.values():
            if entry.get("case_id") == self._derived().case_id and entry.get("text"):
                entry["text"] = None
        return rebuilt

    def audit_new_derived_rows(self) -> Dict[str, Any]:
        index = self._derived()
        if not index.bound:
            return {"status": "unavailable", "code": "not_bound", "scope": "newly_created", "row_count": 0}
        if not index.created_rows:
            return {
                "status": "available",
                "scope": "newly_created",
                "row_count": 0,
                "plaintext_private_columns": 0,
                "encryption_from_path_or_mode_bits": False,
            }
        db_path = getattr(self, "db_path", None)
        if not DUCKDB_AVAILABLE or not db_path:
            return {
                "status": "unavailable",
                "code": "persistence_unavailable",
                "scope": "newly_created",
                "plaintext_persisted": False,
            }
        leaked = 0
        found = 0
        try:
            conn = duckdb.connect(db_path)
            for row_id in list(index.created_rows):
                row = conn.execute(
                    "SELECT case_id, kind, token, public_cache_id FROM private_derived_index WHERE id = ?",
                    [row_id],
                ).fetchone()
                if row is None:
                    continue
                found += 1
                blob = " ".join(str(part or "") for part in row)
                if str(row[0] or "") != index.case_id:
                    leaked += 1
                for secret in index._secrets:
                    if secret and secret in blob:
                        leaked += 1
                if str(row[2] or "").startswith("cgidx:"):
                    continue
                leaked += 1
            conn.close()
        except Exception:
            return {
                "status": "unavailable",
                "code": "persistence_unavailable",
                "scope": "newly_created",
                "plaintext_fallback": False,
            }
        return {
            "status": "available",
            "scope": "newly_created",
            "row_count": found,
            "plaintext_private_columns": leaked,
            "encrypted": index.mode == "durable",
            "encryption_from_path_or_mode_bits": False,
            "directory_mode_private": index.directory_mode_private,
        }


class EvidenceQueryError(EvidenceHookError):
    """Evidence metadata could not be queried from the configured backend."""


class DegradedEvidenceResults(list[Dict[str, Any]]):
    """List-compatible result identifying a failed best-effort query."""

    status: str
    operation: str
    degraded_reason: str
    error_type: str

    def __init__(self, *, operation: str, error: BaseException) -> None:
        super().__init__()
        self.status = 'degraded'
        self.operation = operation
        self.degraded_reason = str(error) or type(error).__name__
        self.error_type = type(error).__name__

    def as_dict(self) -> Dict[str, Any]:
        return {
            'status': self.status,
            'operation': self.operation,
            'degraded_reason': self.degraded_reason,
            'error_type': self.error_type,
            'result_count': len(self),
            'results': list(self),
        }


def _resolve_artifact_identity(*, content_origin: str = '', artifact_family: str = '', corpus_family: str = '') -> Dict[str, str]:
    resolved_artifact_family = artifact_family or _CONTENT_ORIGIN_ARTIFACT_FAMILY.get(content_origin, '')
    resolved_corpus_family = corpus_family or _ARTIFACT_FAMILY_CORPUS_FAMILY.get(resolved_artifact_family, '')
    return {
        'artifact_family': resolved_artifact_family,
        'corpus_family': resolved_corpus_family,
    }


def _ensure_fact_id_prefix(entity_id: str, artifact_id: str, text: str) -> str:
    """Return a stable ``fact:``-prefixed identifier for a graph entity.

    Entity IDs generated by :func:`extract_graph_from_text` already carry a
    ``fact:`` prefix.  This helper keeps those IDs unchanged while providing a
    safe fallback when the entity comes from an external source that may not
    use the same ID scheme.
    """
    if entity_id.startswith('fact:'):
        return entity_id
    if entity_id:
        return f'fact:{entity_id}'
    # No usable entity ID — derive a deterministic one from content.
    digest = hashlib.sha256(f'{artifact_id}|{text}'.encode()).hexdigest()[:16]
    return f'fact:{digest}'


def _normalize_lineage_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _clip_source_passage_text(value: str) -> str:
    text = str(value or '').strip()
    if len(text) <= _MAX_SOURCE_PASSAGE_TEXT_LENGTH:
        return text
    return text[:_MAX_SOURCE_PASSAGE_TEXT_LENGTH].rstrip()


def _build_fact_chunk_lineage(
    fact_text: str,
    sentence_index: int,
    chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not chunks:
        return {
            'sentence_index': sentence_index,
            'source_passage': {
                'chunk_id': '',
                'chunk_index': sentence_index,
                'start': 0,
                'end': 0,
                'text': _clip_source_passage_text(fact_text),
            },
        }

    normalized_fact_text = _normalize_lineage_text(fact_text)
    selected_chunk: Dict[str, Any] = {}
    for chunk in chunks:
        chunk_text = str(chunk.get('text') or '')
        normalized_chunk_text = _normalize_lineage_text(chunk_text)
        if normalized_fact_text and normalized_fact_text in normalized_chunk_text:
            selected_chunk = chunk
            break

    if not selected_chunk:
        selected_chunk = chunks[min(max(sentence_index, 0), len(chunks) - 1)]

    chunk_start = int(selected_chunk.get('start', 0) or 0)
    chunk_text = str(selected_chunk.get('text') or '')
    local_start = chunk_text.find(fact_text) if fact_text else -1
    if local_start < 0 and normalized_fact_text:
        local_start = _normalize_lineage_text(chunk_text).find(normalized_fact_text)
    absolute_start = chunk_start + local_start if local_start >= 0 else chunk_start
    absolute_end = (
        absolute_start + len(fact_text)
        if local_start >= 0 and fact_text
        else int(selected_chunk.get('end', absolute_start) or absolute_start)
    )
    passage_text = (
        chunk_text[local_start:local_start + len(fact_text)]
        if local_start >= 0 and fact_text
        else fact_text or chunk_text
    )
    source_passage = {
        'chunk_id': str(selected_chunk.get('chunk_id') or ''),
        'chunk_index': int(selected_chunk.get('index', 0) or 0),
        'start': absolute_start,
        'end': absolute_end,
        'text': _clip_source_passage_text(passage_text),
    }
    return {
        'sentence_index': sentence_index,
        'chunk_id': source_passage['chunk_id'],
        'chunk_index': source_passage['chunk_index'],
        'source_passage': source_passage,
    }


def _normalize_evidence_fact_row(row: Any, *, evidence_id: int) -> Dict[str, Any]:
    metadata = json.loads(row[4]) if row[4] else {}
    provenance = json.loads(row[5]) if row[5] else {}
    durable_values = dict(row[6]) if len(row) > 6 and isinstance(row[6], dict) else {}
    parse_lineage = metadata.get('parse_lineage', {}) if isinstance(metadata.get('parse_lineage'), dict) else {}
    transform_lineage = parse_lineage.get('transform_lineage', {}) if isinstance(parse_lineage.get('transform_lineage'), dict) else {}
    parse_quality = parse_lineage.get('parse_quality', {}) if isinstance(parse_lineage.get('parse_quality'), dict) else {}
    source_span = parse_lineage.get('source_span', {}) if isinstance(parse_lineage.get('source_span'), dict) else {}
    provenance_metadata = provenance.get('metadata', {}) if isinstance(provenance.get('metadata'), dict) else {}
    content_origin = str(
        durable_values.get('content_origin')
        or transform_lineage.get('content_origin')
        or parse_lineage.get('content_origin')
        or provenance_metadata.get('content_origin')
        or ''
    )
    artifact_identity = _resolve_artifact_identity(
        content_origin=content_origin,
        artifact_family=str(
            durable_values.get('artifact_family')
            or transform_lineage.get('artifact_family')
            or parse_lineage.get('artifact_family')
            or provenance_metadata.get('artifact_family')
            or ''
        ),
        corpus_family=str(
            durable_values.get('corpus_family')
            or transform_lineage.get('corpus_family')
            or parse_lineage.get('corpus_family')
            or provenance_metadata.get('corpus_family')
            or ''
        ),
    )
    durable_source_passage = durable_values.get('source_passage')
    if isinstance(durable_source_passage, str) and durable_source_passage:
        try:
            durable_source_passage = json.loads(durable_source_passage)
        except json.JSONDecodeError:
            durable_source_passage = {}
    source_passage = durable_source_passage if isinstance(durable_source_passage, dict) else {}
    if not source_passage:
        source_passage = dict(metadata.get('source_passage') or {})
    source_ref = str(durable_values.get('source_ref') or row[2] or parse_lineage.get('source_ref') or '')
    return {
        'fact_id': row[0],
        'text': row[1],
        'source_artifact_id': row[2],
        'confidence': row[3] or 0.0,
        'metadata': metadata,
        'provenance': provenance,
        'source_family': str(durable_values.get('source_family') or 'evidence'),
        'source_record_id': int(durable_values.get('source_record_id') or evidence_id),
        'source_ref': source_ref,
        'record_scope': str(durable_values.get('record_scope') or parse_lineage.get('record_scope') or 'evidence'),
        'artifact_family': artifact_identity['artifact_family'],
        'corpus_family': artifact_identity['corpus_family'],
        'content_origin': content_origin,
        'parse_source': str(durable_values.get('parse_source') or parse_lineage.get('source') or ''),
        'input_format': str(durable_values.get('input_format') or parse_lineage.get('input_format') or ''),
        'quality_tier': str(durable_values.get('quality_tier') or parse_lineage.get('quality_tier') or ''),
        'quality_score': float(durable_values.get('quality_score') or parse_lineage.get('quality_score') or parse_quality.get('quality_score') or 0.0),
        'page_count': int(durable_values.get('page_count') or parse_lineage.get('page_count') or source_span.get('page_count') or 0),
        'chunk_id': str(durable_values.get('chunk_id') or metadata.get('chunk_id') or ''),
        'chunk_index': int(durable_values.get('chunk_index') or metadata.get('chunk_index') or 0),
        'source_passage': source_passage,
    }


def _normalize_evidence_fact_payload(payload: Dict[str, Any], *, evidence_id: int) -> Dict[str, Any]:
    metadata = payload.get('metadata', {}) if isinstance(payload.get('metadata'), dict) else {}
    provenance = payload.get('provenance', {}) if isinstance(payload.get('provenance'), dict) else {}
    parse_lineage = metadata.get('parse_lineage', {}) if isinstance(metadata.get('parse_lineage'), dict) else {}
    transform_lineage = parse_lineage.get('transform_lineage', {}) if isinstance(parse_lineage.get('transform_lineage'), dict) else {}
    parse_quality = parse_lineage.get('parse_quality', {}) if isinstance(parse_lineage.get('parse_quality'), dict) else {}
    source_span = parse_lineage.get('source_span', {}) if isinstance(parse_lineage.get('source_span'), dict) else {}
    provenance_metadata = provenance.get('metadata', {}) if isinstance(provenance.get('metadata'), dict) else {}
    content_origin = str(
        payload.get('content_origin')
        or transform_lineage.get('content_origin')
        or parse_lineage.get('content_origin')
        or provenance_metadata.get('content_origin')
        or ''
    )
    artifact_identity = _resolve_artifact_identity(
        content_origin=content_origin,
        artifact_family=str(
            payload.get('artifact_family')
            or transform_lineage.get('artifact_family')
            or parse_lineage.get('artifact_family')
            or provenance_metadata.get('artifact_family')
            or ''
        ),
        corpus_family=str(
            payload.get('corpus_family')
            or transform_lineage.get('corpus_family')
            or parse_lineage.get('corpus_family')
            or provenance_metadata.get('corpus_family')
            or ''
        ),
    )
    normalized = dict(payload)
    normalized.update({
        'source_family': str(payload.get('source_family') or 'evidence'),
        'source_record_id': payload.get('source_record_id') or evidence_id,
        'source_ref': str(payload.get('source_ref') or payload.get('source_artifact_id') or parse_lineage.get('source_ref') or ''),
        'record_scope': str(payload.get('record_scope') or parse_lineage.get('record_scope') or 'evidence'),
        'artifact_family': artifact_identity['artifact_family'],
        'corpus_family': artifact_identity['corpus_family'],
        'content_origin': content_origin,
        'parse_source': str(payload.get('parse_source') or parse_lineage.get('source') or ''),
        'input_format': str(payload.get('input_format') or parse_lineage.get('input_format') or ''),
        'quality_tier': str(payload.get('quality_tier') or parse_lineage.get('quality_tier') or ''),
        'quality_score': float(payload.get('quality_score') or parse_lineage.get('quality_score') or parse_quality.get('quality_score') or 0.0),
        'page_count': int(payload.get('page_count') or parse_lineage.get('page_count') or source_span.get('page_count') or 0),
        'chunk_id': str(payload.get('chunk_id') or metadata.get('chunk_id') or ''),
        'chunk_index': int(payload.get('chunk_index') or metadata.get('chunk_index') or 0),
        'source_passage': dict(payload.get('source_passage') or metadata.get('source_passage') or {}),
    })
    return normalized


class EvidenceStorageHook:
    """
    Hook for storing evidence in IPFS.
    
    Stores evidence files/data in IPFS and returns the CID (Content ID)
    for later retrieval and reference.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        self._private_context: Optional[Dict[str, Any]] = None
        self._private_route_bound = False
        self._private_unavailable_code = ""
        self._private_records: Dict[str, Dict[str, Any]] = {}
        self._public_legal_cids: Dict[str, Dict[str, Any]] = {}
        self._private_revision_counter = 0
        self._check_ipfs_availability()

    def bind_private_artifact_context(self, context: Optional[Dict[str, Any]], *, unavailable_code: str = "") -> None:
        """Attach the workspace private-artifact context. Does not mint keys."""

        self._private_route_bound = True
        self._private_unavailable_code = str(unavailable_code or "")
        if context is None:
            self._private_context = None
            return
        self._private_context = {
            "access": context.get("access"),
            "tenant_id": context.get("tenant_id"),
            "case_id": context.get("case_id"),
            "principal_id": context.get("principal_id"),
            "key_provider": context.get("key_provider"),
            "backend": context.get("backend"),
            "backend_name": context.get("backend_name") or "local_cache",
            "pin_content": bool(context.get("pin_content", False)),
        }

    def enable_public_user_evidence_ingestion(self) -> None:
        """User evidence stays on the private owner. This gate does not open a plaintext path."""

        if not self._private_route_bound or not self._private_context or self._private_unavailable_code:
            raise EvidenceStorageError(
                "Public user evidence ingestion requires the encrypted private artifact route.",
                code="private_route_required",
                public_status="unavailable",
            )
        raise EvidenceStorageError(
            "Public user evidence ingestion is disabled. Private bytes stay on the encrypted artifact owner.",
            code="public_user_evidence_disabled",
            public_status="unavailable",
        )

    def _is_public_legal_corpus(self, metadata: Optional[Dict[str, Any]]) -> bool:
        meta = metadata or {}
        if meta.get("storage_class") == "public_legal_corpus" or meta.get("classification") == "public_legal_corpus":
            return True
        origin = str(meta.get("content_origin") or "")
        corpus = str(meta.get("corpus_family") or "")
        if origin not in PUBLIC_LEGAL_CONTENT_ORIGINS:
            return False
        return not corpus or corpus in PUBLIC_LEGAL_CORPUS_FAMILIES

    def _private_artifact_kind(self, evidence_type: str) -> str:
        if evidence_type in AUTOMATIC_PRIVATE_ARTIFACT_KINDS:
            return evidence_type
        return "attachment"

    def _build_provenance(self, data: bytes, evidence_type: str, metadata: Optional[Dict[str, Any]]):
        content_hash = stable_content_hash(data)
        provenance = build_provenance(
            source_url=str((metadata or {}).get('source_url', '')),
            acquisition_method=str((metadata or {}).get('acquisition_method', 'submitted')),
            source_type=str((metadata or {}).get('source_type', evidence_type)),
            acquired_at=datetime.now().isoformat(),
            content_hash=content_hash,
            source_system=str((metadata or {}).get('source_system', 'complaint_generator')),
            jurisdiction=str((metadata or {}).get('jurisdiction', '')),
        )
        provenance = build_provenance(
            source_url=str(provenance.source_url or ''),
            acquisition_method=str(provenance.acquisition_method or ''),
            source_type=str(provenance.source_type or ''),
            acquired_at=str(provenance.acquired_at or ''),
            content_hash=str(provenance.content_hash or ''),
            source_system=str(provenance.source_system or ''),
            jurisdiction=str(provenance.jurisdiction or ''),
            metadata=_merge_intake_summary_handoff_metadata(
                dict(getattr(provenance, 'metadata', {}) or {}),
                self.mediator,
            ),
        )
        normalized_metadata = _merge_intake_summary_handoff_metadata(
            merge_metadata_with_provenance(metadata, provenance),
            self.mediator,
        )
        return provenance, normalized_metadata, content_hash

    def _attach_document_parse(self, result: Dict[str, Any], data: bytes, evidence_type: str, metadata: Optional[Dict[str, Any]], provenance) -> None:
        if not self._should_parse_evidence(evidence_type, metadata):
            return
        document_parse = parse_document(
            data=data,
            filename=str((metadata or {}).get('filename', '')),
            mime_type=str((metadata or {}).get('mime_type', '')),
            source=str((metadata or {}).get('parse_source', 'bytes')),
        )
        parse_contract = build_document_parse_contract(
            document_parse,
            default_source=str((metadata or {}).get('parse_source', 'bytes')),
        )
        result['document_parse'] = document_parse
        result['metadata']['document_parse_summary'] = parse_contract['summary']
        result['metadata']['document_parse_contract'] = parse_contract
        graph_payload = extract_graph_from_text(
            parse_contract.get('text', ''),
            source_id=result.get('artifact_id') or result.get('cid'),
            metadata={
                'artifact_id': result.get('artifact_id', ''),
                'filename': str((metadata or {}).get('filename', '')),
                'mime_type': str((metadata or {}).get('mime_type', '')),
                'source_url': provenance.source_url,
                'claim_type': str((metadata or {}).get('claim_type', '')),
                'claim_element_id': str((metadata or {}).get('claim_element_id', '')),
                'claim_element_text': str((metadata or {}).get('claim_element', '')),
                'title': str((metadata or {}).get('title', '')),
            },
        )
        result['document_graph'] = graph_payload
        result['metadata']['document_graph_summary'] = {
            'status': graph_payload.get('status'),
            'entity_count': len(graph_payload.get('entities', []) or []),
            'relationship_count': len(graph_payload.get('relationships', []) or []),
        }

    def _result_from_artifact(self, data: bytes, evidence_type: str, metadata, provenance, normalized_metadata, content_hash, cid: str) -> Dict[str, Any]:
        artifact = CaseArtifact(
            cid=cid,
            artifact_type=evidence_type,
            size=len(data),
            timestamp=datetime.now().isoformat(),
            mime_type=str((metadata or {}).get('mime_type', '')),
            source_type=provenance.source_type,
            content_hash=content_hash,
            acquisition_method=provenance.acquisition_method,
            source_url=provenance.source_url,
            metadata=normalized_metadata,
            provenance=provenance,
        )
        return artifact.as_dict()

    def _store_private_evidence(self, data: bytes, evidence_type: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Seal private bytes with the existing artifact owner before any public store."""

        from integrations.private_storage import (
            PrivateCryptoCapabilityError,
            PrivateKeyMaterialError,
            PrivateStorageError,
        )

        if self._private_unavailable_code or not self._private_context or not self._private_context.get("key_provider"):
            raise EvidenceStorageError(
                "Private evidence storage is unavailable.",
                code=self._private_unavailable_code or "key_unavailable",
                public_status="unavailable",
            )
        context = self._private_context
        kind = self._private_artifact_kind(str(evidence_type or "attachment"))
        self._private_revision_counter += 1
        revision = str((metadata or {}).get("revision") or f"{kind}-{self._private_revision_counter}")
        backend = (metadata or {}).get("backend", context.get("backend"))
        backend_name = str((metadata or {}).get("backend_name") or context.get("backend_name") or "local_cache")
        pin_content = bool((metadata or {}).get("pin_content", context.get("pin_content", False)))
        try:
            receipt = store_automatic_private_artifact(
                data,
                artifact_kind=kind,
                access=context.get("access"),
                tenant_id=str(context.get("tenant_id") or ""),
                case_id=str(context.get("case_id") or ""),
                principal_id=str(context.get("principal_id") or context.get("tenant_id") or ""),
                key_provider=context.get("key_provider"),
                revision=revision,
                backend=backend,
                backend_name=backend_name,
                pin_content=pin_content,
            )
        except PrivateKeyMaterialError as exc:
            raise EvidenceStorageError(
                "Private evidence storage is unavailable.",
                code="key_unavailable",
                public_status="unavailable",
            ) from exc
        except PrivateCryptoCapabilityError as exc:
            raise EvidenceStorageError(
                "Private evidence storage is unavailable.",
                code="private_crypto_unavailable",
                public_status="unavailable",
            ) from exc
        except (PrivateStorageError, ValueError) as exc:
            raise EvidenceStorageError(
                "Private evidence storage is unavailable.",
                code="artifact_unavailable",
                public_status="unavailable",
            ) from exc
        view = dict(receipt.get("receipt") or {})
        cid = str(receipt.get("cid") or "")
        cid_kind = str(view.get("cid_kind") or "")
        local_only = bool(receipt.get("stored_local")) or cid_kind in {"pseudo_cid", "sha256_fallback", "missing", ""}
        remote_durable = bool(view.get("network_durable")) and not local_only and bool(cid)
        if not cid or str(receipt.get("status") or "") not in {"available", "degraded"}:
            raise EvidenceStorageError(
                "Private evidence storage is unavailable.",
                code="artifact_unavailable",
                public_status="unavailable",
            )
        provenance, normalized_metadata, content_hash = self._build_provenance(data, evidence_type, metadata)
        result = self._result_from_artifact(data, evidence_type, metadata, provenance, normalized_metadata, content_hash, cid)
        self._attach_document_parse(result, data, evidence_type, metadata, provenance)
        result["private_artifact"] = True
        result["classification"] = "private_evidence"
        result["artifact_kind"] = kind
        result["revision"] = revision
        result["tenant_id"] = context.get("tenant_id")
        result["case_id"] = context.get("case_id")
        result["key_id"] = receipt.get("key_id")
        result["cid_kind"] = cid_kind
        result["network_durable"] = remote_durable
        result["remote_durable"] = remote_durable
        result["stored_local"] = bool(receipt.get("stored_local")) or local_only
        result["ipfs_available"] = remote_durable
        result["ipfs_persisted"] = remote_durable
        result["storage_status"] = "stored" if remote_durable else "local_only"
        if not remote_durable:
            result["degraded_reason"] = "local deterministic identifier is not remote durability"
            result["error_type"] = "LocalIdentifier"
        self._private_records[cid] = {
            "artifact_kind": kind,
            "revision": revision,
            "tenant_id": context.get("tenant_id"),
            "case_id": context.get("case_id"),
            "principal_id": context.get("principal_id"),
            "backend": backend,
            "backend_name": backend_name,
            "content_hash": content_hash,
            "provenance": result.get("provenance"),
        }
        self.mediator.log("evidence_stored_private", cid=cid, size=len(data), type=evidence_type, remote_durable=remote_durable)
        return result

    def _store_public_legal_evidence(self, data: bytes, evidence_type: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        meta = dict(metadata or {})
        origin = str(meta.get("content_origin") or "authority_full_text")
        corpus = str(meta.get("corpus_family") or "legal_authority")
        if origin not in PUBLIC_LEGAL_CONTENT_ORIGINS:
            origin = "authority_full_text"
        if corpus not in PUBLIC_LEGAL_CORPUS_FAMILIES:
            corpus = "legal_authority"
        backend = meta.get("backend")
        backend_name = meta.get("backend_name")
        try:
            stored = store_public_legal_corpus(
                data,
                content_origin=origin,
                corpus_family=corpus,
                backend=backend,
                backend_name=str(backend_name) if backend_name else None,
                pin_content=bool(meta.get("pin_content", True)),
            )
        except (TypeError, ValueError) as exc:
            raise EvidenceStorageError(
                "Public legal corpus storage is unavailable.",
                code="artifact_unavailable",
                public_status="unavailable",
            ) from exc
        cid = str(stored.get("cid") or "")
        if stored.get("status") not in {"available", "degraded"} or not cid:
            raise EvidenceStorageError(
                "Public legal corpus storage is unavailable.",
                code="artifact_unavailable",
                public_status="unavailable",
            )
        provenance, normalized_metadata, content_hash = self._build_provenance(data, evidence_type, meta)
        result = self._result_from_artifact(data, evidence_type, meta, provenance, normalized_metadata, content_hash, cid)
        self._attach_document_parse(result, data, evidence_type, meta, provenance)
        remote_durable = bool(stored.get("network_durable"))
        result["private_artifact"] = False
        result["classification"] = "public_legal_corpus"
        result["content_origin"] = origin
        result["corpus_family"] = corpus
        result["cid_kind"] = stored.get("cid_kind") or ""
        result["network_durable"] = remote_durable
        result["remote_durable"] = remote_durable
        result["stored_local"] = bool(stored.get("stored_local"))
        result["ipfs_available"] = stored.get("status") == "available"
        result["ipfs_persisted"] = remote_durable
        result["storage_status"] = "stored" if remote_durable else "local_only"
        if not remote_durable:
            result["degraded_reason"] = "local deterministic identifier is not remote durability"
            result["error_type"] = "LocalIdentifier"
        self._public_legal_cids[cid] = {"backend": backend, "backend_name": backend_name, "content_origin": origin}
        self.mediator.log("public_legal_corpus_stored", cid=cid, size=len(data), remote_durable=remote_durable)
        return result
    
    def _check_ipfs_availability(self):
        """Check if IPFS backend is available."""
        if not IPFS_AVAILABLE:
            self.mediator.log('evidence_warning', 
                message='IPFS not available - evidence storage will be simulated')

    def _should_parse_evidence(self, evidence_type: str, metadata: Optional[Dict[str, Any]]) -> bool:
        parse_flag = (metadata or {}).get('parse_document')
        if parse_flag is not None:
            return bool(parse_flag)
        return should_parse_document_input(
            evidence_type=evidence_type,
            filename=str((metadata or {}).get('filename', '')),
            mime_type=str((metadata or {}).get('mime_type', '')),
        )
    
    def store_evidence(self, data: bytes, evidence_type: str, 
                      metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Store evidence data in IPFS.
        
        Args:
            data: Evidence data as bytes
            evidence_type: Type of evidence (e.g., 'document', 'image', 'video', 'text')
            metadata: Optional metadata about the evidence
            
        Returns:
            Dictionary with:
            - cid: Content ID in IPFS
            - size: Size of data in bytes
            - type: Evidence type
            - timestamp: When stored
            - metadata: Any additional metadata
        """
        try:
            if self._is_public_legal_corpus(metadata):
                return self._store_public_legal_evidence(data, evidence_type, metadata)
            if self._private_route_bound:
                return self._store_private_evidence(data, evidence_type, metadata)
            storage_status = 'stored'
            storage_degraded_reason = ''
            storage_error_type = ''
            content_hash = stable_content_hash(data)
            provenance = build_provenance(
                source_url=str((metadata or {}).get('source_url', '')),
                acquisition_method=str((metadata or {}).get('acquisition_method', 'submitted')),
                source_type=str((metadata or {}).get('source_type', evidence_type)),
                acquired_at=datetime.now().isoformat(),
                content_hash=content_hash,
                source_system=str((metadata or {}).get('source_system', 'complaint_generator')),
                jurisdiction=str((metadata or {}).get('jurisdiction', '')),
            )
            provenance = build_provenance(
                source_url=str(provenance.source_url or ''),
                acquisition_method=str(provenance.acquisition_method or ''),
                source_type=str(provenance.source_type or ''),
                acquired_at=str(provenance.acquired_at or ''),
                content_hash=str(provenance.content_hash or ''),
                source_system=str(provenance.source_system or ''),
                jurisdiction=str(provenance.jurisdiction or ''),
                metadata=_merge_intake_summary_handoff_metadata(
                    dict(getattr(provenance, 'metadata', {}) or {}),
                    self.mediator,
                ),
            )
            normalized_metadata = _merge_intake_summary_handoff_metadata(
                merge_metadata_with_provenance(metadata, provenance),
                self.mediator,
            )
            if IPFS_AVAILABLE:
                try:
                    # Store in IPFS
                    cid = add_bytes(data, pin=True)
                    self.mediator.log('evidence_stored', 
                        cid=cid, size=len(data), type=evidence_type)
                except Exception as ipfs_error:
                    cid = f"Qm{hashlib.sha256(data).hexdigest()[:44]}"
                    storage_status = 'degraded'
                    storage_degraded_reason = str(ipfs_error) or type(ipfs_error).__name__
                    storage_error_type = type(ipfs_error).__name__
                    self.mediator.log(
                        'evidence_ipfs_runtime_unavailable',
                        error=str(ipfs_error),
                        error_type=type(ipfs_error).__name__,
                        operation='ipfs_add_bytes',
                        cid=cid,
                        size=len(data),
                        type=evidence_type,
                    )
            else:
                # Fallback: Create a simulated CID using hash
                cid = f"Qm{hashlib.sha256(data).hexdigest()[:44]}"
                storage_status = 'degraded'
                storage_degraded_reason = 'IPFS backend unavailable; using deterministic local identifier'
                storage_error_type = 'BackendUnavailable'
                self.mediator.log('evidence_simulated', 
                    cid=cid, size=len(data), type=evidence_type)
            
            artifact = CaseArtifact(
                cid=cid,
                artifact_type=evidence_type,
                size=len(data),
                timestamp=datetime.now().isoformat(),
                mime_type=str((metadata or {}).get('mime_type', '')),
                source_type=provenance.source_type,
                content_hash=content_hash,
                acquisition_method=provenance.acquisition_method,
                source_url=provenance.source_url,
                metadata=normalized_metadata,
                provenance=provenance,
            )
            result = artifact.as_dict()
            if self._should_parse_evidence(evidence_type, metadata):
                document_parse = parse_document(
                    data=data,
                    filename=str((metadata or {}).get('filename', '')),
                    mime_type=str((metadata or {}).get('mime_type', '')),
                    source=str((metadata or {}).get('parse_source', 'bytes')),
                )
                parse_contract = build_document_parse_contract(
                    document_parse,
                    default_source=str((metadata or {}).get('parse_source', 'bytes')),
                )
                result['document_parse'] = document_parse
                result['metadata']['document_parse_summary'] = parse_contract['summary']
                result['metadata']['document_parse_contract'] = parse_contract
                graph_payload = extract_graph_from_text(
                    parse_contract.get('text', ''),
                    source_id=result.get('artifact_id') or result.get('cid'),
                    metadata={
                        'artifact_id': result.get('artifact_id', ''),
                        'filename': str((metadata or {}).get('filename', '')),
                        'mime_type': str((metadata or {}).get('mime_type', '')),
                        'source_url': provenance.source_url,
                        'claim_type': str((metadata or {}).get('claim_type', '')),
                        'claim_element_id': str((metadata or {}).get('claim_element_id', '')),
                        'claim_element_text': str((metadata or {}).get('claim_element', '')),
                        'title': str((metadata or {}).get('title', '')),
                    },
                )
                result['document_graph'] = graph_payload
                result['metadata']['document_graph_summary'] = {
                    'status': graph_payload.get('status'),
                    'entity_count': len(graph_payload.get('entities', []) or []),
                    'relationship_count': len(graph_payload.get('relationships', []) or []),
                }
            result['ipfs_available'] = IPFS_AVAILABLE
            result['ipfs_persisted'] = storage_status == 'stored'
            result['storage_status'] = storage_status
            if storage_degraded_reason:
                result['degraded_reason'] = storage_degraded_reason
                result['error_type'] = storage_error_type
            return result
            
        except EvidenceStorageError:
            raise
        except Exception as e:
            self.mediator.log(
                'evidence_storage_error',
                error=str(e),
                error_type=type(e).__name__,
                operation='store_evidence',
            )
            raise EvidenceStorageError(f'Failed to store evidence: {str(e)}') from e
    
    def store_evidence_file(self, file_path: str, evidence_type: str,
                           metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Store evidence from a file path.
        
        Args:
            file_path: Path to the evidence file
            evidence_type: Type of evidence
            metadata: Optional metadata
            
        Returns:
            Dictionary with CID and evidence details
        """
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Add file information to metadata
            file_metadata = metadata or {}
            if 'mime_type' not in file_metadata or not file_metadata.get('mime_type'):
                file_metadata['mime_type'] = mimetypes.guess_type(file_path)[0] or ''
            file_metadata.update({
                'filename': os.path.basename(file_path),
                'original_path': file_path,
                'parse_source': 'file',
            })
            
            return self.store_evidence(data, evidence_type, file_metadata)
            
        except EvidenceStorageError as e:
            self.mediator.log(
                'evidence_file_error',
                error=str(e),
                error_type=type(e).__name__,
                operation='store_evidence_file',
                file=file_path,
            )
            raise
        except (OSError, ValueError, TypeError) as e:
            self.mediator.log(
                'evidence_file_error',
                error=str(e),
                error_type=type(e).__name__,
                operation='store_evidence_file',
                file=file_path,
            )
            raise EvidenceStorageError(f'Failed to store evidence file: {str(e)}') from e
    
    def retrieve_evidence(self, cid: str, **binding: Any) -> bytes:
        """
        Retrieve evidence data from IPFS by CID.
        
        Args:
            cid: Content ID of the evidence
            
        Returns:
            Evidence data as bytes
        """
        try:
            if cid in self._private_records or (self._private_route_bound and cid not in self._public_legal_cids and self._private_records):
                return self._retrieve_private_evidence(cid, binding)
            if cid in self._public_legal_cids:
                return self._retrieve_public_legal_evidence(cid)
            if IPFS_AVAILABLE:
                data = cat(cid)
                self.mediator.log('evidence_retrieved', cid=cid, size=len(data))
                return data
            else:
                self.mediator.log('evidence_retrieval_unavailable', cid=cid)
                raise EvidenceRetrievalError(
                    'Failed to retrieve evidence: IPFS not available for evidence retrieval'
                )
                
        except EvidenceRetrievalError:
            raise
        except Exception as e:
            # ``cat`` is an optional backend boundary with backend-specific
            # exception types.  Normalize it while retaining the cause.
            self.mediator.log(
                'evidence_retrieval_error',
                error=str(e),
                error_type=type(e).__name__,
                operation='retrieve_evidence',
                cid=cid,
            )
            raise EvidenceRetrievalError(f'Failed to retrieve evidence: {str(e)}') from e

    def _retrieve_private_evidence(self, cid: str, binding: Dict[str, Any]) -> bytes:
        from integrations.private_storage import PrivateKeyMaterialError, PrivateStorageError

        record = self._private_records.get(cid)
        context = self._private_context or {}
        if record is None or not context:
            raise EvidenceRetrievalError(
                "Private evidence storage is unavailable.",
                code="artifact_unavailable",
                public_status="unavailable",
            )
        case_id = str(binding.get("case_id") or record["case_id"])
        tenant_id = str(binding.get("tenant_id") or record["tenant_id"])
        principal_id = str(binding.get("principal_id") or record["principal_id"] or tenant_id)
        access = binding.get("access", context.get("access"))
        key_provider = binding.get("key_provider", context.get("key_provider"))
        key = binding.get("key")
        key_id = binding.get("key_id")
        if key is not None or key_id is not None:
            key_provider = None
        try:
            opened = retrieve_private_artifact(
                cid,
                access=access,
                tenant_id=tenant_id,
                case_id=case_id,
                artifact_kind=str(binding.get("artifact_kind") or record["artifact_kind"]),
                revision=str(binding.get("revision") or record["revision"]),
                principal_id=principal_id,
                key=key,
                key_id=key_id,
                key_provider=key_provider,
                backend=binding.get("backend", record.get("backend")),
                backend_name=binding.get("backend_name", record.get("backend_name")),
            )
        except PrivateKeyMaterialError as exc:
            raise EvidenceRetrievalError(
                "Private evidence storage is unavailable.",
                code="key_unavailable",
                public_status="unavailable",
            ) from exc
        except PrivateStorageError as exc:
            raise EvidenceRetrievalError(
                "Private evidence could not be opened for the expected binding.",
                code=str(getattr(exc, "code", "") or "authentication_failed"),
                public_status="recoverable",
            ) from exc
        data = opened.get("data")
        if not isinstance(data, (bytes, bytearray)):
            raise EvidenceRetrievalError(
                "Private evidence storage is unavailable.",
                code="artifact_unavailable",
                public_status="unavailable",
            )
        return bytes(data)

    def _retrieve_public_legal_evidence(self, cid: str) -> bytes:
        from integrations.ipfs_datasets.storage import retrieve_bytes

        located = self._public_legal_cids.get(cid) or {}
        loaded = retrieve_bytes(cid, backend=located.get("backend"), backend_name=located.get("backend_name"))
        data = loaded.get("data")
        if loaded.get("status") not in {"available", "degraded"} or not isinstance(data, (bytes, bytearray)):
            raise EvidenceRetrievalError(
                "Public legal corpus storage is unavailable.",
                code="artifact_unavailable",
                public_status="unavailable",
            )
        return bytes(data)


class EvidenceStateHook(PrivateDerivedIndexMixin):
    """
    Hook for managing evidence state in DuckDB.
    
    Stores metadata about evidence submissions including user associations,
    timestamps, and references to IPFS CIDs.
    """
    
    def __init__(self, mediator, db_path: Optional[str] = None):
        self.mediator = mediator
        self.db_path = db_path or self._get_default_db_path()
        self._memory_records: List[Dict[str, Any]] = []
        self._memory_graphs: Dict[int, Dict[str, Any]] = {}
        self._memory_facts: Dict[int, List[Dict[str, Any]]] = {}
        self._check_duckdb_availability()
        if DUCKDB_AVAILABLE:
            self._prepare_duckdb_path()
            self._initialize_schema()

    def _prepare_duckdb_path(self):
        """Prepare DuckDB path for connect().

        DuckDB errors if the file exists but is not a valid DuckDB database.
        Our tests create an empty temp file (0 bytes) and pass its name; in
        that case we delete the empty file so DuckDB can create the DB.
        """
        try:
            path = Path(self.db_path)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.is_file() and path.stat().st_size == 0:
                path.unlink()
        except OSError as exc:
            # Best-effort only; duckdb.connect will raise a useful error if
            # needed, but path preparation failures still leave a breadcrumb.
            self.mediator.log(
                'evidence_db_path_prepare_error',
                db_path=self.db_path,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    
    def _get_default_db_path(self) -> str:
        """Get default DuckDB database path."""
        # Use statefiles directory if it exists, otherwise current directory
        state_dir = Path(__file__).parent.parent / 'statefiles'
        if not state_dir.exists():
            state_dir = Path('.')
        return str(state_dir / 'evidence.duckdb')
    
    def _check_duckdb_availability(self):
        """Check if DuckDB is available."""
        if not DUCKDB_AVAILABLE:
            self.mediator.log('evidence_warning',
                message='DuckDB not available - evidence state will not be persisted')
    
    def _initialize_schema(self):
        """Initialize DuckDB schema for evidence tracking."""
        try:
            conn = duckdb.connect(self.db_path)
            
            # Create sequence for auto-incrementing IDs
            conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS evidence_id_seq START 1
            """)
            
            # Create evidence table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence (
                    id BIGINT PRIMARY KEY DEFAULT nextval('evidence_id_seq'),
                    user_id VARCHAR,
                    username VARCHAR,
                    evidence_cid VARCHAR NOT NULL,
                    evidence_type VARCHAR NOT NULL,
                    evidence_size INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSON,
                    complaint_id VARCHAR,
                    claim_type VARCHAR,
                    description TEXT
                )
            """)

            for statement in [
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS content_hash VARCHAR",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS source_url VARCHAR",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS acquisition_method VARCHAR",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS provenance JSON",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS claim_element_id VARCHAR",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS claim_element TEXT",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS parse_status VARCHAR",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS chunk_count INTEGER",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS parsed_text_preview TEXT",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS parse_metadata JSON",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS graph_status VARCHAR",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS graph_entity_count INTEGER",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS graph_relationship_count INTEGER",
                "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS graph_metadata JSON",
            ]:
                conn.execute(statement)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence_chunks (
                    evidence_id BIGINT,
                    chunk_id VARCHAR,
                    chunk_index INTEGER,
                    start_offset INTEGER,
                    end_offset INTEGER,
                    chunk_text TEXT,
                    metadata JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence_graph_entities (
                    evidence_id BIGINT,
                    entity_id VARCHAR,
                    entity_type VARCHAR,
                    entity_name TEXT,
                    confidence FLOAT,
                    metadata JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence_graph_relationships (
                    evidence_id BIGINT,
                    relationship_id VARCHAR,
                    source_id VARCHAR,
                    target_id VARCHAR,
                    relation_type VARCHAR,
                    confidence FLOAT,
                    metadata JSON
                )
            """)

            _ensure_evidence_fact_schema(conn)

            conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS scraper_run_id_seq START 1
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraper_runs (
                    id BIGINT PRIMARY KEY DEFAULT nextval('scraper_run_id_seq'),
                    user_id VARCHAR,
                    username VARCHAR,
                    claim_type VARCHAR,
                    keywords JSON,
                    domains JSON,
                    iteration_count INTEGER,
                    final_result_count INTEGER,
                    stored_count INTEGER,
                    new_count INTEGER,
                    reused_count INTEGER,
                    unique_url_count INTEGER,
                    quality JSON,
                    config JSON,
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraper_run_iterations (
                    run_id BIGINT,
                    iteration_index INTEGER,
                    discovered_count INTEGER,
                    accepted_count INTEGER,
                    scraped_count INTEGER,
                    coverage JSON,
                    quality JSON,
                    critique JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraper_run_tactics (
                    run_id BIGINT,
                    iteration_index INTEGER,
                    tactic_name VARCHAR,
                    tactic_mode VARCHAR,
                    query_text TEXT,
                    weight FLOAT,
                    discovered_count INTEGER,
                    scraped_count INTEGER,
                    accepted_count INTEGER,
                    novelty_count INTEGER,
                    quality_score FLOAT,
                    quality JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraper_run_coverage (
                    run_id BIGINT,
                    url TEXT,
                    domain VARCHAR,
                    source_type VARCHAR,
                    last_seen_iteration INTEGER,
                    metadata JSON
                )
            """)

            conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS scraper_queue_id_seq START 1
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraper_queue (
                    id BIGINT PRIMARY KEY DEFAULT nextval('scraper_queue_id_seq'),
                    user_id VARCHAR,
                    username VARCHAR,
                    claim_type VARCHAR,
                    keywords JSON,
                    domains JSON,
                    iterations INTEGER,
                    sleep_seconds DOUBLE,
                    quality_domain VARCHAR,
                    min_relevance DOUBLE,
                    store_results BOOLEAN,
                    priority INTEGER DEFAULT 100,
                    status VARCHAR DEFAULT 'queued',
                    available_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    claimed_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    worker_id VARCHAR,
                    run_id BIGINT,
                    error TEXT,
                    metadata JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create index on CID for fast lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evidence_cid 
                ON evidence(evidence_cid)
            """)
            
            # Create index on user_id for user-specific queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evidence_user 
                ON evidence(user_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scraper_queue_status_available
                ON scraper_queue(status, available_at)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scraper_queue_user_status
                ON scraper_queue(user_id, status)
            """)
            
            conn.close()
            self.mediator.log('evidence_schema_initialized', db_path=self.db_path)
            
        except Exception as e:
            self.mediator.log(
                'evidence_schema_error',
                operation='initialize_evidence_schema',
                error=str(e),
                error_type=type(e).__name__,
            )

    def _store_document_chunks(self, conn, evidence_id: int, document_parse: Dict[str, Any]) -> None:
        chunks = document_parse.get('chunks', []) or []
        if not chunks:
            return
        parse_contract = build_document_parse_contract(
            document_parse,
            default_source=str((document_parse.get('metadata', {}) or {}).get('source', '')),
        )
        for chunk in chunks:
            chunk_metadata = dict(chunk.get('metadata') or {})
            chunk_metadata.setdefault('length', chunk.get('length', 0))
            chunk_metadata.setdefault('parser_version', parse_contract.get('summary', {}).get('parser_version', ''))
            chunk_metadata.setdefault('source', parse_contract.get('source', ''))
            chunk_metadata.setdefault('input_format', parse_contract.get('summary', {}).get('input_format', ''))
            page_count = int(parse_contract.get('summary', {}).get('page_count') or (1 if parse_contract.get('text') else 0))
            chunk_metadata.setdefault('page_start', 1 if page_count else 0)
            chunk_metadata.setdefault('page_end', chunk_metadata.get('page_start', 0))
            chunk_metadata.setdefault('section_label', '')
            chunk_metadata.setdefault('source_span', {
                'char_start': int(chunk.get('start', 0) or 0),
                'char_end': int(chunk.get('end', 0) or 0),
                'text_length': len(str(parse_contract.get('text') or '')),
                'page_start': int(chunk_metadata.get('page_start', 0) or 0),
                'page_end': int(chunk_metadata.get('page_end', 0) or 0),
                'page_count': page_count,
            })
            conn.execute(
                """
                INSERT INTO evidence_chunks (
                    evidence_id, chunk_id, chunk_index, start_offset, end_offset, chunk_text, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    evidence_id,
                    chunk.get('chunk_id'),
                    chunk.get('index'),
                    chunk.get('start'),
                    chunk.get('end'),
                    self._seal_column(chunk.get('text'), 'chunk_text'),
                    self._seal_json(_merge_intake_summary_handoff_metadata(chunk_metadata, self.mediator)),
                ],
            )

    def _store_document_graph(self, conn, evidence_id: int, document_graph: Dict[str, Any]) -> None:
        entities = document_graph.get('entities', []) or []
        relationships = document_graph.get('relationships', []) or []

        for entity in entities:
            conn.execute(
                """
                INSERT INTO evidence_graph_entities (
                    evidence_id, entity_id, entity_type, entity_name, confidence, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    evidence_id,
                    entity.get('id'),
                    entity.get('type'),
                    self._seal_column(entity.get('name'), 'entity_name'),
                    entity.get('confidence', 0.0),
                    self._seal_json(_merge_intake_summary_handoff_metadata(
                        entity.get('attributes', {}),
                        self.mediator,
                    )),
                ],
            )

        for relationship in relationships:
            conn.execute(
                """
                INSERT INTO evidence_graph_relationships (
                    evidence_id, relationship_id, source_id, target_id, relation_type, confidence, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    evidence_id,
                    relationship.get('id'),
                    relationship.get('source_id'),
                    relationship.get('target_id'),
                    relationship.get('relation_type'),
                    relationship.get('confidence', 0.0),
                    json.dumps(_merge_intake_summary_handoff_metadata(
                        relationship.get('attributes', {}),
                        self.mediator,
                    )),
                ],
            )

    def _store_document_facts(self, conn, evidence_id: int, evidence_info: Dict[str, Any], document_graph: Dict[str, Any], document_parse: Dict[str, Any]) -> None:
        entities = document_graph.get('entities', []) or []
        artifact_id = evidence_info.get('artifact_id') or evidence_info.get('cid') or ''
        normalized_metadata = _merge_intake_summary_handoff_metadata(
            evidence_info.get('metadata', {}),
            self.mediator,
        )
        provenance_payload = (
            dict(normalized_metadata.get('provenance') or {})
            if isinstance(normalized_metadata.get('provenance'), dict)
            else {}
        )
        provenance_metadata = _merge_intake_summary_handoff_metadata(
            provenance_payload.get('metadata', {}),
            self.mediator,
        )
        parse_contract = build_document_parse_contract(
            document_parse,
            default_source=str((document_parse.get('metadata', {}) or {}).get('source', '')),
        )
        chunks = list(document_parse.get('chunks', []) or [])

        for entity in entities:
            if entity.get('type') != 'fact':
                continue
            attributes = entity.get('attributes', {}) if isinstance(entity.get('attributes'), dict) else {}
            fact_text = str(attributes.get('text') or entity.get('name') or '')
            lineage_metadata = build_fact_lineage_metadata(
                attributes,
                parse_contract=parse_contract,
                record_scope='evidence',
                source_ref=artifact_id,
            )
            lineage_metadata.update(
                _build_fact_chunk_lineage(
                    fact_text,
                    int(attributes.get('sentence_index', 0) or 0),
                    chunks,
                )
            )
            fact = CaseFact(
                fact_id=str(entity.get('id') or ''),
                text=fact_text,
                source_artifact_id=artifact_id,
                source_family='evidence',
                source_record_id=evidence_id,
                source_ref=artifact_id,
                record_scope='evidence',
                confidence=float(entity.get('confidence', 0.0) or 0.0),
                metadata=_merge_intake_summary_handoff_metadata(
                    lineage_metadata,
                    self.mediator,
                ),
                provenance=build_provenance(
                    source_url=str(provenance_payload.get('source_url', '')),
                    acquisition_method=str(provenance_payload.get('acquisition_method', '')),
                    source_type=str(provenance_payload.get('source_type', '')),
                    acquired_at=str(provenance_payload.get('acquired_at', '')),
                    content_hash=str(provenance_payload.get('content_hash', '')),
                    source_system=str(provenance_payload.get('source_system', '')),
                    jurisdiction=str(provenance_payload.get('jurisdiction', '')),
                    metadata=provenance_metadata,
                ),
            )
            conn.execute(
                """
                INSERT INTO evidence_facts (
                    evidence_id, fact_id, fact_text, source_artifact_id, confidence, metadata, provenance,
                    source_family, source_record_id, source_ref, record_scope, artifact_family,
                    corpus_family, content_origin, parse_source, input_format, quality_tier,
                    quality_score, page_count, chunk_id, chunk_index, source_passage
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    evidence_id,
                    fact.fact_id,
                    self._seal_column(fact.text, 'fact_text'),
                    fact.source_artifact_id,
                    fact.confidence,
                    self._seal_json(fact.metadata),
                    self._seal_json(fact.provenance.as_dict()),
                    fact.source_family,
                    fact.source_record_id,
                    fact.source_ref,
                    fact.record_scope,
                    fact.artifact_family,
                    fact.corpus_family,
                    fact.content_origin,
                    fact.parse_source,
                    fact.input_format,
                    fact.quality_tier,
                    fact.quality_score,
                    fact.page_count,
                    str(fact.metadata.get('chunk_id') or ''),
                    int(fact.metadata.get('chunk_index') or 0),
                    self._seal_json(fact.metadata.get('source_passage') or {}),
                ],
            )

    def _find_existing_evidence_record(
        self,
        conn,
        user_id: str,
        evidence_info: Dict[str, Any],
        complaint_id: Optional[str],
        claim_type: Optional[str],
        claim_element_id: Optional[str],
    ) -> Optional[int]:
        provenance = evidence_info.get('metadata', {}).get('provenance', {})
        evidence_cid = evidence_info.get('cid')
        content_hash = provenance.get('content_hash')
        source_url = provenance.get('source_url')

        if evidence_cid:
            existing = conn.execute(
                """
                SELECT id
                FROM evidence
                WHERE user_id = ?
                  AND evidence_cid = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, evidence_cid, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        if content_hash:
            existing = conn.execute(
                """
                SELECT id
                FROM evidence
                WHERE user_id = ?
                  AND content_hash = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, content_hash, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        if source_url:
            existing = conn.execute(
                """
                SELECT id
                FROM evidence
                WHERE user_id = ?
                  AND source_url = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, source_url, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        return None
    
    def add_evidence_record(self, user_id: str, evidence_info: Dict[str, Any],
                          complaint_id: Optional[str] = None,
                          claim_type: Optional[str] = None,
                          claim_element_id: Optional[str] = None,
                          claim_element: Optional[str] = None,
                          description: Optional[str] = None) -> int:
        result = self.upsert_evidence_record(
            user_id=user_id,
            evidence_info=evidence_info,
            complaint_id=complaint_id,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            claim_element=claim_element,
            description=description,
        )
        return result['record_id']

    def upsert_evidence_record(self, user_id: str, evidence_info: Dict[str, Any],
                             complaint_id: Optional[str] = None,
                             claim_type: Optional[str] = None,
                             claim_element_id: Optional[str] = None,
                             claim_element: Optional[str] = None,
                             description: Optional[str] = None) -> Dict[str, Any]:
        """
        Add evidence record to DuckDB.
        
        Args:
            user_id: User identifier
            evidence_info: Evidence information (from EvidenceStorageHook)
            complaint_id: Optional complaint ID this evidence relates to
            claim_type: Optional claim type this evidence supports
            description: Optional description of the evidence
            
        Returns:
            Dictionary describing whether the record was newly inserted or reused.
        """
        if not DUCKDB_AVAILABLE:
            normalized_evidence_metadata = _merge_intake_summary_handoff_metadata(
                evidence_info.get('metadata', {}),
                self.mediator,
            )
            provenance_payload = (
                dict(normalized_evidence_metadata.get('provenance') or {})
                if isinstance(normalized_evidence_metadata.get('provenance'), dict)
                else {}
            )
            provenance_metadata = _merge_intake_summary_handoff_metadata(
                provenance_payload.get('metadata', {}),
                self.mediator,
            )
            document_parse = evidence_info.get('document_parse') if isinstance(evidence_info.get('document_parse'), dict) else {}
            document_graph = evidence_info.get('document_graph') if isinstance(evidence_info.get('document_graph'), dict) else {}
            parse_contract = build_document_parse_contract(
                document_parse,
                default_source=str(
                    document_parse.get('metadata', {}).get('source')
                    or normalized_evidence_metadata.get('parse_source')
                    or ''
                ),
            )
            parse_metadata = _merge_intake_summary_handoff_metadata(
                parse_contract['storage_metadata'],
                self.mediator,
            )
            parsed_text = parse_contract['text']
            parsed_text_preview = parse_contract['text_preview']
            if not document_graph and parsed_text:
                document_graph = extract_graph_from_text(
                    parsed_text,
                    source_id=evidence_info.get('artifact_id') or evidence_info.get('cid'),
                    metadata={
                        'artifact_id': evidence_info.get('artifact_id', ''),
                        'source_url': evidence_info.get('source_url', ''),
                        'claim_type': claim_type or '',
                        'claim_element_id': claim_element_id or '',
                        'claim_element_text': claim_element or '',
                        'filename': document_parse.get('metadata', {}).get('filename', ''),
                        'mime_type': document_parse.get('metadata', {}).get('mime_type', ''),
                    },
                )
            existing_record = next(
                (
                    record for record in self._memory_records
                    if str(record.get('user_id') or '') == str(user_id)
                    and str(record.get('cid') or '') == str(evidence_info.get('cid') or '')
                    and str(record.get('claim_type') or '') == str(claim_type or '')
                    and str(record.get('claim_element_id') or '') == str(claim_element_id or '')
                ),
                None,
            )
            if existing_record is not None:
                return {'record_id': int(existing_record.get('id') or -1), 'created': False, 'reused': True}

            record_id = len(self._memory_records) + 1
            state = getattr(self.mediator, 'state', None)
            username = getattr(state, 'username', None) if state is not None else None
            if not isinstance(username, str) or not username:
                username = user_id
            record = {
                'id': record_id,
                'user_id': user_id,
                'username': username,
                'cid': evidence_info.get('cid'),
                'type': evidence_info.get('type'),
                'size': evidence_info.get('size'),
                'timestamp': evidence_info.get('timestamp'),
                'metadata': normalized_evidence_metadata,
                'complaint_id': complaint_id,
                'claim_type': claim_type,
                'description': description,
                'content_hash': evidence_info.get('content_hash'),
                'source_url': evidence_info.get('source_url'),
                'acquisition_method': evidence_info.get('acquisition_method'),
                'provenance': evidence_info.get('provenance') or {},
                'claim_element_id': claim_element_id,
                'claim_element': claim_element,
                'parse_status': parse_contract.get('status') or parse_metadata.get('status'),
                'chunk_count': parse_contract.get('chunk_count', 0),
                'parsed_text_preview': parsed_text_preview,
                'parse_metadata': parse_metadata,
                'graph_status': document_graph.get('status', ''),
                'graph_entity_count': len(document_graph.get('entities', []) or []),
                'graph_relationship_count': len(document_graph.get('relationships', []) or []),
                'graph_metadata': document_graph.get('metadata', {}) if isinstance(document_graph.get('metadata'), dict) else {},
                'fact_count': 0,
            }
            memory_facts: List[Dict[str, Any]] = []
            artifact_id = str(evidence_info.get('artifact_id') or evidence_info.get('cid') or '')
            cid = str(evidence_info.get('cid') or '')
            chunks = list(document_parse.get('chunks', []) or [])
            # Iterate over graph entities with type='fact' (same approach as _store_document_facts)
            for entity in list(document_graph.get('entities', []) or []):
                if not isinstance(entity, dict) or entity.get('type') != 'fact':
                    continue
                attributes = entity.get('attributes', {}) if isinstance(entity.get('attributes'), dict) else {}
                text = str(attributes.get('text') or entity.get('name') or '').strip()
                if not text:
                    continue
                lineage_metadata = build_fact_lineage_metadata(
                    attributes,
                    parse_contract=parse_contract,
                    record_scope='evidence',
                    source_ref=artifact_id,
                )
                lineage_metadata.update(
                    _build_fact_chunk_lineage(
                        text,
                        int(attributes.get('sentence_index', 0) or 0),
                        chunks,
                    )
                )
                fact_metadata = _merge_intake_summary_handoff_metadata(
                    lineage_metadata,
                    self.mediator,
                )
                fact_provenance = build_provenance(
                    source_url=str(provenance_payload.get('source_url', '')),
                    acquisition_method=str(provenance_payload.get('acquisition_method', '')),
                    source_type=str(provenance_payload.get('source_type', '')),
                    acquired_at=str(provenance_payload.get('acquired_at', '')),
                    content_hash=str(provenance_payload.get('content_hash', '')),
                    source_system=str(provenance_payload.get('source_system', '')),
                    jurisdiction=str(provenance_payload.get('jurisdiction', '')),
                    metadata=provenance_metadata,
                )
                fact = CaseFact(
                    fact_id=_ensure_fact_id_prefix(str(entity.get('id') or ''), artifact_id, text),
                    text=text,
                    source_artifact_id=artifact_id,
                    source_family='evidence',
                    source_record_id=record_id,
                    source_ref=artifact_id,
                    record_scope='evidence',
                    confidence=float(entity.get('confidence', 0.0) or 0.0),
                    metadata=fact_metadata,
                    provenance=fact_provenance,
                )
                memory_facts.append(fact.as_dict())
            if not memory_facts and parsed_text_preview:
                lineage_metadata = build_fact_lineage_metadata(
                    {},
                    parse_contract=parse_contract,
                    record_scope='evidence',
                    source_ref=artifact_id,
                )
                lineage_metadata.update(
                    _build_fact_chunk_lineage(parsed_text_preview, 0, chunks)
                )
                fact = CaseFact(
                    fact_id=f'fact:{hashlib.sha256(parsed_text_preview.encode()).hexdigest()[:16]}',
                    text=parsed_text_preview,
                    source_artifact_id=artifact_id,
                    source_family='evidence',
                    source_record_id=record_id,
                    source_ref=cid,
                    record_scope='evidence',
                    confidence=0.5,
                    metadata=_merge_intake_summary_handoff_metadata(
                        lineage_metadata,
                        self.mediator,
                    ),
                    provenance=build_provenance(
                        source_url=str(provenance_payload.get('source_url', '')),
                        acquisition_method=str(provenance_payload.get('acquisition_method', '')),
                        source_type=str(provenance_payload.get('source_type', '')),
                        acquired_at=str(provenance_payload.get('acquired_at', '')),
                        content_hash=str(provenance_payload.get('content_hash', '')),
                        source_system=str(provenance_payload.get('source_system', '')),
                        jurisdiction=str(provenance_payload.get('jurisdiction', '')),
                        metadata=provenance_metadata,
                    ),
                )
                memory_facts.append(fact.as_dict())
            record['fact_count'] = len(memory_facts)
            self._memory_records.append(record)
            self._memory_graphs[record_id] = document_graph if isinstance(document_graph, dict) else {'status': 'unavailable', 'entities': [], 'relationships': []}
            self._memory_facts[record_id] = memory_facts
            self.mediator.log('evidence_record_added_memory', record_id=record_id, cid=evidence_info.get('cid'))
            return {'record_id': record_id, 'created': True, 'reused': False}
        
        try:
            conn = duckdb.connect(self.db_path)
            normalized_evidence_metadata = _merge_intake_summary_handoff_metadata(
                evidence_info.get('metadata', {}),
                self.mediator,
            )
            provenance_payload = (
                dict(normalized_evidence_metadata.get('provenance') or {})
                if isinstance(normalized_evidence_metadata.get('provenance'), dict)
                else {}
            )
            provenance_metadata = _merge_intake_summary_handoff_metadata(
                provenance_payload.get('metadata', {}),
                self.mediator,
            )
            if provenance_metadata:
                provenance_payload['metadata'] = provenance_metadata
            if provenance_payload:
                normalized_evidence_metadata['provenance'] = provenance_payload
            document_parse = evidence_info.get('document_parse') if isinstance(evidence_info.get('document_parse'), dict) else {}
            document_graph = evidence_info.get('document_graph') if isinstance(evidence_info.get('document_graph'), dict) else {}
            document_graph_summary = normalized_evidence_metadata.get('document_graph_summary', {})
            parse_contract = build_document_parse_contract(
                document_parse,
                default_source=str(
                    document_parse.get('metadata', {}).get('source')
                    or normalized_evidence_metadata.get('parse_source')
                    or ''
                ),
            )
            parse_metadata = _merge_intake_summary_handoff_metadata(
                parse_contract['storage_metadata'],
                self.mediator,
            )
            parsed_text = parse_contract['text']
            parsed_text_preview = parse_contract['text_preview']
            if not document_graph and parsed_text:
                document_graph = extract_graph_from_text(
                    parsed_text,
                    source_id=evidence_info.get('artifact_id') or evidence_info.get('cid'),
                    metadata={
                        'artifact_id': evidence_info.get('artifact_id', ''),
                        'source_url': provenance_payload.get('source_url', ''),
                        'claim_type': claim_type or '',
                        'claim_element_id': claim_element_id or '',
                        'claim_element_text': claim_element or '',
                        'filename': document_parse.get('metadata', {}).get('filename', ''),
                        'mime_type': document_parse.get('metadata', {}).get('mime_type', ''),
                    },
                )
                document_graph_summary = {
                    'status': document_graph.get('status'),
                    'entity_count': len(document_graph.get('entities', []) or []),
                    'relationship_count': len(document_graph.get('relationships', []) or []),
                }
            graph_snapshot_scope = '|'.join(
                [
                    str(Path(self.db_path).resolve()),
                    str(user_id or ''),
                    str(complaint_id or ''),
                    str(evidence_info.get('cid') or ''),
                ]
            )
            graph_snapshot = persist_graph_snapshot(
                document_graph,
                graph_id=f"evidence-record:{hashlib.sha256(graph_snapshot_scope.encode('utf-8')).hexdigest()[:16]}",
                graph_changed=bool(document_graph.get('entities') or document_graph.get('relationships')),
                existing_graph=False,
                persistence_metadata=_merge_intake_summary_handoff_metadata(
                    {
                        'record_scope': 'evidence',
                        'record_key': evidence_info.get('cid', ''),
                    },
                    self.mediator,
                ),
            )
            graph_metadata = {
                **(document_graph.get('metadata', {}) or {}),
                'graph_snapshot': graph_snapshot,
            }

            existing_record_id = self._find_existing_evidence_record(
                conn,
                user_id,
                evidence_info,
                complaint_id,
                claim_type,
                claim_element_id,
            )
            if existing_record_id is not None:
                conn.close()
                self.mediator.log(
                    'evidence_record_duplicate',
                    record_id=existing_record_id,
                    cid=evidence_info.get('cid'),
                    claim_type=claim_type,
                    claim_element_id=claim_element_id,
                )
                return {'record_id': existing_record_id, 'created': False, 'reused': True}
            
            # Get username from mediator state if available
            state = getattr(self.mediator, 'state', None)
            username = getattr(state, 'username', None) if state is not None else None
            if not isinstance(username, str) or not username:
                username = user_id
            
            result = conn.execute("""
                INSERT INTO evidence (
                    user_id, username, evidence_cid, evidence_type, 
                    evidence_size, metadata, complaint_id, claim_type, description,
                    content_hash, source_url, acquisition_method, provenance,
                    claim_element_id, claim_element, parse_status, chunk_count,
                    parsed_text_preview, parse_metadata, graph_status,
                    graph_entity_count, graph_relationship_count, graph_metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, [
                user_id,
                username,
                evidence_info['cid'],
                evidence_info['type'],
                evidence_info['size'],
                self._seal_json(normalized_evidence_metadata),
                complaint_id,
                claim_type,
                self._seal_column(description, 'description'),
                provenance_payload.get('content_hash'),
                provenance_payload.get('source_url'),
                provenance_payload.get('acquisition_method'),
                self._seal_json(provenance_payload),
                claim_element_id,
                self._seal_column(claim_element, 'claim_element'),
                parse_contract.get('status') or parse_metadata.get('status'),
                parse_contract.get('chunk_count', 0),
                self._seal_column(parsed_text_preview, 'parsed_text_preview'),
                self._seal_json(parse_metadata),
                document_graph.get('status') or document_graph_summary.get('status'),
                len(document_graph.get('entities', []) or []),
                len(document_graph.get('relationships', []) or []),
                self._seal_json(graph_metadata),
            ]).fetchone()
            
            record_id = result[0]
            self._store_document_chunks(conn, record_id, document_parse)
            self._store_document_graph(conn, record_id, document_graph)
            self._store_document_facts(conn, record_id, evidence_info, document_graph, document_parse)
            conn.close()
            
            self.mediator.log('evidence_record_added', 
                record_id=record_id, cid=evidence_info['cid'])
            
            return {'record_id': record_id, 'created': True, 'reused': False}
            
        except Exception as e:
            self.mediator.log(
                'evidence_record_error',
                operation='upsert_evidence_record',
                error=str(e),
                error_type=type(e).__name__,
            )
            raise EvidencePersistenceError(f'Failed to add evidence record: {str(e)}') from e
    
    def get_user_evidence(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all evidence for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of evidence records
        """
        if not DUCKDB_AVAILABLE:
            return [
                dict(record)
                for record in sorted(
                    self._memory_records,
                    key=lambda item: str(item.get('timestamp') or ''),
                    reverse=True,
                )
                if str(record.get('user_id') or '') == str(user_id)
            ]
        
        try:
            conn = duckdb.connect(self.db_path)
            
            results = conn.execute("""
                SELECT id, user_id, username, evidence_cid, evidence_type,
                      evidence_size, timestamp, metadata, complaint_id,
                      claim_type, description, content_hash, source_url,
                        acquisition_method, provenance, claim_element_id, claim_element,
                    parse_status, chunk_count, parsed_text_preview, parse_metadata,
                    graph_status, graph_entity_count, graph_relationship_count, graph_metadata,
                    (
                        SELECT COUNT(*) FROM evidence_facts ef WHERE ef.evidence_id = evidence.id
                    ) AS fact_count
                FROM evidence
                WHERE user_id = ?
                ORDER BY timestamp DESC
            """, [user_id]).fetchall()
            
            conn.close()
            
            evidence_list = []
            for row in results:
                evidence_list.append({
                    'id': row[0],
                    'user_id': row[1],
                    'username': row[2],
                    'cid': row[3],
                    'type': row[4],
                    'size': row[5],
                    'timestamp': row[6],
                    'metadata': json.loads(row[7]) if row[7] else {},
                    'complaint_id': row[8],
                    'claim_type': row[9],
                    'description': row[10],
                    'content_hash': row[11],
                    'source_url': row[12],
                    'acquisition_method': row[13],
                    'provenance': json.loads(row[14]) if row[14] else {},
                    'claim_element_id': row[15],
                    'claim_element': row[16],
                    'parse_status': row[17],
                    'chunk_count': row[18] or 0,
                    'parsed_text_preview': row[19] or '',
                    'parse_metadata': json.loads(row[20]) if row[20] else {},
                    'graph_status': row[21],
                    'graph_entity_count': row[22] or 0,
                    'graph_relationship_count': row[23] or 0,
                    'graph_metadata': json.loads(row[24]) if row[24] else {},
                    'fact_count': row[25] or 0,
                })
            
            return evidence_list
            
        except Exception as e:
            self.mediator.log('evidence_query_error', error=str(e))
            return DegradedEvidenceResults(operation='get_user_evidence', error=e)
    
    def get_evidence_by_cid(self, cid: str) -> Optional[Dict[str, Any]]:
        """
        Get evidence record by CID.
        
        Args:
            cid: Content ID
            
        Returns:
            Evidence record or None if not found

        Raises:
            EvidenceQueryError: If the configured evidence database cannot be
                queried or the stored record cannot be decoded.
        """
        if not DUCKDB_AVAILABLE:
            for record in self._memory_records:
                if str(record.get('cid') or '') == str(cid):
                    return dict(record)
            return None
        
        try:
            conn = duckdb.connect(self.db_path)
            try:
                result = conn.execute("""
                    SELECT id, user_id, username, evidence_cid, evidence_type,
                          evidence_size, timestamp, metadata, complaint_id,
                          claim_type, description, content_hash, source_url,
                            acquisition_method, provenance, claim_element_id, claim_element,
                        parse_status, chunk_count, parsed_text_preview, parse_metadata,
                        graph_status, graph_entity_count, graph_relationship_count, graph_metadata,
                        (
                            SELECT COUNT(*) FROM evidence_facts ef WHERE ef.evidence_id = evidence.id
                        ) AS fact_count
                    FROM evidence
                    WHERE evidence_cid = ?
                """, [cid]).fetchone()
            finally:
                conn.close()
            
            if result:
                return {
                    'id': result[0],
                    'user_id': result[1],
                    'username': result[2],
                    'cid': result[3],
                    'type': result[4],
                    'size': result[5],
                    'timestamp': result[6],
                    'metadata': json.loads(result[7]) if result[7] else {},
                    'complaint_id': result[8],
                    'claim_type': result[9],
                    'description': result[10],
                    'content_hash': result[11],
                    'source_url': result[12],
                    'acquisition_method': result[13],
                    'provenance': json.loads(result[14]) if result[14] else {},
                    'claim_element_id': result[15],
                    'claim_element': result[16],
                    'parse_status': result[17],
                    'chunk_count': result[18] or 0,
                    'parsed_text_preview': result[19] or '',
                    'parse_metadata': json.loads(result[20]) if result[20] else {},
                    'graph_status': result[21],
                    'graph_entity_count': result[22] or 0,
                    'graph_relationship_count': result[23] or 0,
                    'graph_metadata': json.loads(result[24]) if result[24] else {},
                    'fact_count': result[25] or 0,
                }
            
            return None
            
        except Exception as e:
            # DuckDB adapters and JSON decoders do not share a stable exception
            # hierarchy. Normalize failures at this boundary while preserving
            # the original exception for diagnostics and retry decisions.
            self.mediator.log(
                'evidence_query_error',
                operation='get_evidence_by_cid',
                error=str(e),
                error_type=type(e).__name__,
                cid=cid,
            )
            raise EvidenceQueryError(
                f'Failed to query evidence by CID {cid}: {str(e)}'
            ) from e

    def get_evidence_chunks(self, evidence_id: int) -> List[Dict[str, Any]]:
        """Get parsed chunks for a stored evidence record."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            results = conn.execute(
                """
                SELECT chunk_id, chunk_index, start_offset, end_offset, chunk_text, metadata
                FROM evidence_chunks
                WHERE evidence_id = ?
                ORDER BY chunk_index ASC
                """,
                [evidence_id],
            ).fetchall()
            conn.close()
            return [
                {
                    'chunk_id': row[0],
                    'index': row[1],
                    'start': row[2],
                    'end': row[3],
                    'text': row[4],
                    'metadata': json.loads(row[5]) if row[5] else {},
                }
                for row in results
            ]
        except Exception as e:
            self.mediator.log('evidence_chunk_query_error', error=str(e), evidence_id=evidence_id)
            return DegradedEvidenceResults(operation='get_evidence_chunks', error=e)

    def get_evidence_graph(self, evidence_id: int) -> Dict[str, Any]:
        """Get normalized graph entities and relationships for a stored evidence record."""
        if not DUCKDB_AVAILABLE:
            graph_payload = self._memory_graphs.get(int(evidence_id), {})
            if isinstance(graph_payload, dict) and graph_payload:
                return dict(graph_payload)
            return {'status': 'unavailable', 'entities': [], 'relationships': []}

        try:
            conn = duckdb.connect(self.db_path)
            entity_rows = conn.execute(
                """
                SELECT entity_id, entity_type, entity_name, confidence, metadata
                FROM evidence_graph_entities
                WHERE evidence_id = ?
                ORDER BY entity_id ASC
                """,
                [evidence_id],
            ).fetchall()
            relationship_rows = conn.execute(
                """
                SELECT relationship_id, source_id, target_id, relation_type, confidence, metadata
                FROM evidence_graph_relationships
                WHERE evidence_id = ?
                ORDER BY relationship_id ASC
                """,
                [evidence_id],
            ).fetchall()
            conn.close()
            return {
                'status': 'available',
                'entities': [
                    {
                        'id': row[0],
                        'type': row[1],
                        'name': row[2],
                        'confidence': row[3],
                        'attributes': json.loads(row[4]) if row[4] else {},
                    }
                    for row in entity_rows
                ],
                'relationships': [
                    {
                        'id': row[0],
                        'source_id': row[1],
                        'target_id': row[2],
                        'relation_type': row[3],
                        'confidence': row[4],
                        'attributes': json.loads(row[5]) if row[5] else {},
                    }
                    for row in relationship_rows
                ],
            }
        except Exception as e:
            self.mediator.log('evidence_graph_query_error', error=str(e), evidence_id=evidence_id)
            return {'status': 'error', 'entities': [], 'relationships': [], 'error': str(e)}

    def get_evidence_facts(self, evidence_id: int) -> List[Dict[str, Any]]:
        """Get persisted fact records for a stored evidence record."""
        if not DUCKDB_AVAILABLE:
            return [
                _normalize_evidence_fact_payload(dict(item), evidence_id=int(evidence_id))
                for item in list(self._memory_facts.get(int(evidence_id), []))
            ]

        try:
            conn = duckdb.connect(self.db_path)
            columns = set(_list_table_columns(conn, 'evidence_facts'))
            durable_select = []
            for column_name in _EVIDENCE_FACT_DURABLE_COLUMNS:
                if column_name == 'source_passage':
                    expression = (
                        "CASE WHEN source_passage IS NULL THEN NULL "
                        "ELSE CAST(source_passage AS VARCHAR) END AS source_passage"
                        if column_name in columns
                        else "NULL AS source_passage"
                    )
                else:
                    expression = column_name if column_name in columns else f"NULL AS {column_name}"
                durable_select.append(expression)
            durable_struct = ', '.join(
                f'{column_name} := {column_name}'
                for column_name in _EVIDENCE_FACT_DURABLE_COLUMNS
            )
            rows = conn.execute(
                f"""
                SELECT fact_id, fact_text, source_artifact_id, confidence, metadata, provenance,
                       struct_pack({durable_struct})
                FROM (
                    SELECT fact_id, fact_text, source_artifact_id, confidence, metadata, provenance,
                           {', '.join(durable_select)}
                    FROM evidence_facts
                    WHERE evidence_id = ?
                ) facts
                ORDER BY fact_id ASC
                """,
                [evidence_id],
            ).fetchall()
            conn.close()
            return [
                _normalize_evidence_fact_row(row, evidence_id=evidence_id)
                for row in rows
            ]
        except Exception as e:
            self.mediator.log('evidence_fact_query_error', error=str(e), evidence_id=evidence_id)
            return DegradedEvidenceResults(operation='get_evidence_facts', error=e)
    
    def get_evidence_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get evidence statistics.
        
        Args:
            user_id: Optional user ID to filter by
            
        Returns:
            Dictionary with statistics
        """
        if not DUCKDB_AVAILABLE:
            return {'available': False}
        
        try:
            conn = duckdb.connect(self.db_path)
            
            if user_id:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as total_count,
                        SUM(evidence_size) as total_size,
                        COUNT(DISTINCT evidence_type) as type_count,
                        COALESCE((SELECT COUNT(*) FROM evidence_facts ef JOIN evidence e2 ON ef.evidence_id = e2.id WHERE e2.user_id = ?), 0) as total_facts
                    FROM evidence
                    WHERE user_id = ?
                """, [user_id, user_id]).fetchone()
            else:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as total_count,
                        SUM(evidence_size) as total_size,
                        COUNT(DISTINCT evidence_type) as type_count,
                        COUNT(DISTINCT user_id) as user_count,
                        COALESCE((SELECT COUNT(*) FROM evidence_facts), 0) as total_facts
                    FROM evidence
                """).fetchone()
            
            conn.close()
            
            stats = {
                'available': True,
                'total_count': result[0],
                'total_size': result[1] or 0,
                'type_count': result[2],
                'total_facts': result[3] if user_id else result[4],
            }
            
            if not user_id:
                stats['user_count'] = result[3]
            
            return stats
            
        except Exception as e:
            self.mediator.log('evidence_stats_error', error=str(e))
            return {'available': False, 'error': str(e)}

    def persist_scraper_run(self,
                            user_id: str,
                            run_result: Dict[str, Any],
                            *,
                            keywords: Optional[List[str]] = None,
                            domains: Optional[List[str]] = None,
                            claim_type: Optional[str] = None,
                            stored_summary: Optional[Dict[str, Any]] = None,
                            config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Persist an agentic scraper run, its iterations, and coverage ledger."""
        if not DUCKDB_AVAILABLE:
            return {'persisted': False, 'run_id': -1}

        try:
            conn = duckdb.connect(self.db_path)
            state = getattr(self.mediator, 'state', None)
            username = getattr(state, 'username', None) if state is not None else None
            if not isinstance(username, str) or not username:
                username = user_id

            iterations = list(run_result.get('iterations', []) or [])
            final_results = list(run_result.get('final_results', []) or [])
            coverage_ledger = run_result.get('coverage_ledger', {}) if isinstance(run_result.get('coverage_ledger'), dict) else {}
            quality_payload = run_result.get('final_quality', {}) if isinstance(run_result.get('final_quality'), dict) else {}
            stored_summary = stored_summary or {}
            run_metadata = _merge_intake_summary_handoff_metadata(
                {'tactic_history': run_result.get('tactic_history', {})},
                self.mediator,
            )

            row = conn.execute(
                """
                INSERT INTO scraper_runs (
                    user_id, username, claim_type, keywords, domains,
                    iteration_count, final_result_count, stored_count, new_count, reused_count,
                    unique_url_count, quality, config, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                [
                    user_id,
                    username,
                    claim_type,
                    json.dumps(keywords or []),
                    json.dumps(domains or []),
                    len(iterations),
                    len(final_results),
                    int(stored_summary.get('stored', 0) or 0),
                    int(stored_summary.get('total_new', 0) or 0),
                    int(stored_summary.get('total_reused', 0) or 0),
                    len(coverage_ledger),
                    json.dumps(quality_payload),
                    json.dumps(config or {}),
                    json.dumps(run_metadata),
                ],
            ).fetchone()
            run_id = int(row[0])

            for iteration in iterations:
                iteration_index = int(iteration.get('iteration', 0) or 0)
                iteration_coverage = _merge_intake_summary_handoff_metadata(
                    iteration.get('coverage', {}),
                    self.mediator,
                )
                iteration_quality = _merge_intake_summary_handoff_metadata(
                    iteration.get('quality', {}),
                    self.mediator,
                )
                iteration_critique = _merge_intake_summary_handoff_metadata(
                    iteration.get('critique', {}),
                    self.mediator,
                )
                conn.execute(
                    """
                    INSERT INTO scraper_run_iterations (
                        run_id, iteration_index, discovered_count, accepted_count, scraped_count,
                        coverage, quality, critique
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_id,
                        iteration_index,
                        int(iteration.get('discovered_count', 0) or 0),
                        int(iteration.get('accepted_count', 0) or 0),
                        int(iteration.get('scraped_count', 0) or 0),
                        json.dumps(iteration_coverage),
                        json.dumps(iteration_quality),
                        json.dumps(iteration_critique),
                    ],
                )

                for tactic in iteration.get('tactics', []) or []:
                    tactic_quality = _merge_intake_summary_handoff_metadata(
                        tactic.get('quality', {}),
                        self.mediator,
                    )
                    conn.execute(
                        """
                        INSERT INTO scraper_run_tactics (
                            run_id, iteration_index, tactic_name, tactic_mode, query_text,
                            weight, discovered_count, scraped_count, accepted_count,
                            novelty_count, quality_score, quality
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            run_id,
                            iteration_index,
                            tactic.get('name'),
                            tactic.get('mode'),
                            tactic.get('query'),
                            float(tactic.get('weight', 0.0) or 0.0),
                            int(tactic.get('discovered_count', 0) or 0),
                            int(tactic.get('scraped_count', 0) or 0),
                            int(tactic.get('accepted_count', 0) or 0),
                            int(tactic.get('novelty_count', 0) or 0),
                            float(tactic.get('quality_score', 0.0) or 0.0),
                            json.dumps(tactic_quality),
                        ],
                    )

            for url, coverage in coverage_ledger.items():
                coverage_metadata = _merge_intake_summary_handoff_metadata(
                    coverage if isinstance(coverage, dict) else {},
                    self.mediator,
                )
                conn.execute(
                    """
                    INSERT INTO scraper_run_coverage (
                        run_id, url, domain, source_type, last_seen_iteration, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_id,
                        url,
                        coverage_metadata.get('domain', ''),
                        coverage_metadata.get('source_type', ''),
                        int(coverage_metadata.get('last_seen_iteration', 0) or 0),
                        json.dumps(coverage_metadata),
                    ],
                )

            conn.close()
            self.mediator.log('scraper_run_persisted', run_id=run_id, user_id=user_id)
            return {'persisted': True, 'run_id': run_id}
        except Exception as e:
            self.mediator.log('scraper_run_persist_error', error=str(e), user_id=user_id)
            return {'persisted': False, 'run_id': -1, 'error': str(e)}

    def get_scraper_runs(self, user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Return persisted scraper runs with summary metadata."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            if user_id:
                rows = conn.execute(
                    """
                    SELECT id, user_id, username, claim_type, keywords, domains,
                           iteration_count, final_result_count, stored_count, new_count,
                           reused_count, unique_url_count, quality, config, metadata, timestamp
                    FROM scraper_runs
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    [user_id, int(limit)],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, user_id, username, claim_type, keywords, domains,
                           iteration_count, final_result_count, stored_count, new_count,
                           reused_count, unique_url_count, quality, config, metadata, timestamp
                    FROM scraper_runs
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    [int(limit)],
                ).fetchall()
            conn.close()
            return [
                {
                    'id': row[0],
                    'user_id': row[1],
                    'username': row[2],
                    'claim_type': row[3],
                    'keywords': json.loads(row[4]) if row[4] else [],
                    'domains': json.loads(row[5]) if row[5] else [],
                    'iteration_count': row[6] or 0,
                    'final_result_count': row[7] or 0,
                    'stored_count': row[8] or 0,
                    'new_count': row[9] or 0,
                    'reused_count': row[10] or 0,
                    'unique_url_count': row[11] or 0,
                    'quality': json.loads(row[12]) if row[12] else {},
                    'config': json.loads(row[13]) if row[13] else {},
                    'metadata': json.loads(row[14]) if row[14] else {},
                    'timestamp': row[15],
                }
                for row in rows
            ]
        except Exception as e:
            self.mediator.log('scraper_run_query_error', error=str(e), user_id=user_id)
            return DegradedEvidenceResults(operation='get_scraper_runs', error=e)

    def get_scraper_run_details(self, run_id: int) -> Dict[str, Any]:
        """Return one persisted scraper run with iterations, tactics, and coverage rows."""
        if not DUCKDB_AVAILABLE:
            return {'available': False}

        try:
            conn = duckdb.connect(self.db_path)
            run_row = conn.execute(
                """
                SELECT id, user_id, username, claim_type, keywords, domains,
                       iteration_count, final_result_count, stored_count, new_count,
                       reused_count, unique_url_count, quality, config, metadata, timestamp
                FROM scraper_runs
                WHERE id = ?
                LIMIT 1
                """,
                [int(run_id)],
            ).fetchone()
            if not run_row:
                conn.close()
                return {'available': False, 'run_id': run_id}

            iteration_rows = conn.execute(
                """
                SELECT iteration_index, discovered_count, accepted_count, scraped_count,
                       coverage, quality, critique
                FROM scraper_run_iterations
                WHERE run_id = ?
                ORDER BY iteration_index ASC
                """,
                [int(run_id)],
            ).fetchall()
            tactic_rows = conn.execute(
                """
                SELECT iteration_index, tactic_name, tactic_mode, query_text, weight,
                       discovered_count, scraped_count, accepted_count, novelty_count,
                       quality_score, quality
                FROM scraper_run_tactics
                WHERE run_id = ?
                ORDER BY iteration_index ASC, tactic_name ASC
                """,
                [int(run_id)],
            ).fetchall()
            coverage_rows = conn.execute(
                """
                SELECT url, domain, source_type, last_seen_iteration, metadata
                FROM scraper_run_coverage
                WHERE run_id = ?
                ORDER BY last_seen_iteration ASC, url ASC
                """,
                [int(run_id)],
            ).fetchall()
            conn.close()

            tactics_by_iteration: Dict[int, List[Dict[str, Any]]] = {}
            for row in tactic_rows:
                tactics_by_iteration.setdefault(row[0], []).append({
                    'iteration': row[0],
                    'name': row[1],
                    'mode': row[2],
                    'query': row[3],
                    'weight': row[4] or 0.0,
                    'discovered_count': row[5] or 0,
                    'scraped_count': row[6] or 0,
                    'accepted_count': row[7] or 0,
                    'novelty_count': row[8] or 0,
                    'quality_score': row[9] or 0.0,
                    'quality': json.loads(row[10]) if row[10] else {},
                })

            iterations = []
            for row in iteration_rows:
                iteration_index = row[0]
                iterations.append({
                    'iteration': iteration_index,
                    'discovered_count': row[1] or 0,
                    'accepted_count': row[2] or 0,
                    'scraped_count': row[3] or 0,
                    'coverage': json.loads(row[4]) if row[4] else {},
                    'quality': json.loads(row[5]) if row[5] else {},
                    'critique': json.loads(row[6]) if row[6] else {},
                    'tactics': tactics_by_iteration.get(iteration_index, []),
                })

            return {
                'available': True,
                'run': {
                    'id': run_row[0],
                    'user_id': run_row[1],
                    'username': run_row[2],
                    'claim_type': run_row[3],
                    'keywords': json.loads(run_row[4]) if run_row[4] else [],
                    'domains': json.loads(run_row[5]) if run_row[5] else [],
                    'iteration_count': run_row[6] or 0,
                    'final_result_count': run_row[7] or 0,
                    'stored_count': run_row[8] or 0,
                    'new_count': run_row[9] or 0,
                    'reused_count': run_row[10] or 0,
                    'unique_url_count': run_row[11] or 0,
                    'quality': json.loads(run_row[12]) if run_row[12] else {},
                    'config': json.loads(run_row[13]) if run_row[13] else {},
                    'metadata': json.loads(run_row[14]) if run_row[14] else {},
                    'timestamp': run_row[15],
                },
                'iterations': iterations,
                'coverage': [
                    {
                        'url': row[0],
                        'domain': row[1],
                        'source_type': row[2],
                        'last_seen_iteration': row[3] or 0,
                        'metadata': json.loads(row[4]) if row[4] else {},
                    }
                    for row in coverage_rows
                ],
            }
        except Exception as e:
            self.mediator.log('scraper_run_detail_error', error=str(e), run_id=run_id)
            return {'available': False, 'run_id': run_id, 'error': str(e)}

    def get_scraper_tactic_performance(self, user_id: Optional[str] = None, limit_runs: int = 20) -> Dict[str, Any]:
        """Aggregate recent tactic performance from persisted scraper runs."""
        if not DUCKDB_AVAILABLE:
            return {'available': False, 'tactics': []}

        try:
            conn = duckdb.connect(self.db_path)
            if user_id:
                rows = conn.execute(
                    """
                    WITH recent_runs AS (
                        SELECT id
                        FROM scraper_runs
                        WHERE user_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                    SELECT tactic_name,
                           AVG(weight) AS avg_weight,
                           AVG(quality_score) AS avg_quality_score,
                           AVG(discovered_count) AS avg_discovered_count,
                           AVG(scraped_count) AS avg_scraped_count,
                           AVG(accepted_count) AS avg_accepted_count,
                           AVG(novelty_count) AS avg_novelty_count,
                           COUNT(*) AS observation_count
                    FROM scraper_run_tactics
                    WHERE run_id IN (SELECT id FROM recent_runs)
                    GROUP BY tactic_name
                    ORDER BY avg_quality_score DESC, observation_count DESC
                    """,
                    [user_id, int(limit_runs)],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    WITH recent_runs AS (
                        SELECT id
                        FROM scraper_runs
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                    SELECT tactic_name,
                           AVG(weight) AS avg_weight,
                           AVG(quality_score) AS avg_quality_score,
                           AVG(discovered_count) AS avg_discovered_count,
                           AVG(scraped_count) AS avg_scraped_count,
                           AVG(accepted_count) AS avg_accepted_count,
                           AVG(novelty_count) AS avg_novelty_count,
                           COUNT(*) AS observation_count
                    FROM scraper_run_tactics
                    WHERE run_id IN (SELECT id FROM recent_runs)
                    GROUP BY tactic_name
                    ORDER BY avg_quality_score DESC, observation_count DESC
                    """,
                    [int(limit_runs)],
                ).fetchall()
            conn.close()

            tactics = []
            for row in rows:
                avg_accepted = float(row[5] or 0.0)
                avg_novelty = float(row[6] or 0.0)
                novelty_ratio = (avg_novelty / avg_accepted) if avg_accepted > 0 else 0.0
                tactics.append({
                    'name': row[0],
                    'avg_weight': float(row[1] or 0.0),
                    'avg_quality_score': float(row[2] or 0.0),
                    'avg_discovered_count': float(row[3] or 0.0),
                    'avg_scraped_count': float(row[4] or 0.0),
                    'avg_accepted_count': avg_accepted,
                    'avg_novelty_count': avg_novelty,
                    'novelty_ratio': novelty_ratio,
                    'observation_count': int(row[7] or 0),
                })

            return {'available': True, 'tactics': tactics}
        except Exception as e:
            self.mediator.log('scraper_tactic_perf_error', error=str(e), user_id=user_id)
            return {'available': False, 'tactics': [], 'error': str(e)}

    def _serialize_scraper_queue_row(self, row: Any) -> Dict[str, Any]:
        return {
            'id': row[0],
            'user_id': row[1],
            'username': row[2],
            'claim_type': row[3],
            'keywords': json.loads(row[4]) if row[4] else [],
            'domains': json.loads(row[5]) if row[5] else [],
            'iterations': row[6] or 0,
            'sleep_seconds': float(row[7] or 0.0),
            'quality_domain': row[8] or 'caselaw',
            'min_relevance': float(row[9] or 0.0),
            'store_results': bool(row[10]),
            'priority': row[11] or 100,
            'status': row[12] or 'queued',
            'available_at': row[13],
            'claimed_at': row[14],
            'completed_at': row[15],
            'worker_id': row[16],
            'run_id': row[17],
            'error': row[18],
            'metadata': json.loads(row[19]) if row[19] else {},
            'created_at': row[20],
            'updated_at': row[21],
        }

    def enqueue_scraper_job(self,
                            user_id: str,
                            keywords: List[str],
                            *,
                            domains: Optional[List[str]] = None,
                            claim_type: Optional[str] = None,
                            iterations: int = 3,
                            sleep_seconds: float = 0.0,
                            quality_domain: str = 'caselaw',
                            min_relevance: float = 0.5,
                            store_results: bool = True,
                            priority: int = 100,
                            available_at: Optional[datetime] = None,
                            metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Queue a scraper job for later worker consumption."""
        if not DUCKDB_AVAILABLE:
            return {'queued': False, 'job_id': -1}

        try:
            conn = duckdb.connect(self.db_path)
            state = getattr(self.mediator, 'state', None)
            username = getattr(state, 'username', None) if state is not None else None
            if not isinstance(username, str) or not username:
                username = user_id
            queued_metadata = _merge_intake_summary_handoff_metadata(
                metadata,
                self.mediator,
            )

            row = conn.execute(
                """
                INSERT INTO scraper_queue (
                    user_id, username, claim_type, keywords, domains,
                    iterations, sleep_seconds, quality_domain, min_relevance,
                    store_results, priority, available_at, metadata, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                [
                    user_id,
                    username,
                    claim_type,
                    json.dumps(keywords or []),
                    json.dumps(domains or []),
                    int(iterations),
                    float(sleep_seconds),
                    quality_domain,
                    float(min_relevance),
                    bool(store_results),
                    int(priority),
                    available_at or datetime.now(UTC),
                    json.dumps(queued_metadata or {}),
                ],
            ).fetchone()
            conn.close()
            job_id = int(row[0])
            self.mediator.log('scraper_job_enqueued', job_id=job_id, user_id=user_id)
            return {'queued': True, 'job_id': job_id}
        except Exception as e:
            self.mediator.log('scraper_job_enqueue_error', error=str(e), user_id=user_id)
            return {'queued': False, 'job_id': -1, 'error': str(e)}

    def get_scraper_queue(self,
                          user_id: Optional[str] = None,
                          status: Optional[str] = None,
                          limit: int = 20) -> List[Dict[str, Any]]:
        """Return queued/running/completed scraper jobs."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            clauses: List[str] = []
            params: List[Any] = []
            if user_id:
                clauses.append('user_id = ?')
                params.append(user_id)
            if status:
                clauses.append('status = ?')
                params.append(status)

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
            rows = conn.execute(
                f"""
                SELECT id, user_id, username, claim_type, keywords, domains,
                       iterations, sleep_seconds, quality_domain, min_relevance,
                       store_results, priority, status, available_at, claimed_at,
                       completed_at, worker_id, run_id, error, metadata,
                       created_at, updated_at
                FROM scraper_queue
                {where_sql}
                ORDER BY
                    CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,
                    priority ASC,
                    available_at ASC,
                    created_at ASC
                LIMIT ?
                """,
                [*params, int(limit)],
            ).fetchall()
            conn.close()
            return [self._serialize_scraper_queue_row(row) for row in rows]
        except Exception as e:
            self.mediator.log('scraper_queue_query_error', error=str(e), user_id=user_id, status=status)
            return DegradedEvidenceResults(operation='get_scraper_queue', error=e)

    def get_scraper_queue_state(
        self,
        user_id: Optional[str] = None,
        *,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Return queue rows plus compact operator-facing queue state."""
        jobs = self.get_scraper_queue(user_id=user_id, status=status, limit=limit)
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'user_id': user_id,
                'status': status,
                'jobs': jobs,
                'job_count': len(jobs),
                'status_counts': {},
                'claim_type_counts': {},
                'queue_owner_counts': {},
                'ready_queued_count': 0,
                'running_count': 0,
                'completed_count': 0,
                'failed_count': 0,
                'next_available_at': None,
                'inspection_only': True,
            }

        try:
            conn = duckdb.connect(self.db_path)
            clauses: List[str] = []
            params: List[Any] = []
            if user_id:
                clauses.append('user_id = ?')
                params.append(user_id)
            if status:
                clauses.append('status = ?')
                params.append(status)
            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''

            status_counts = {
                str(row[0] or 'queued'): int(row[1] or 0)
                for row in conn.execute(
                    f"""
                    SELECT status, COUNT(*)
                    FROM scraper_queue
                    {where_sql}
                    GROUP BY status
                    """,
                    params,
                ).fetchall()
            }
            claim_type_counts = {
                str(row[0]): int(row[1] or 0)
                for row in conn.execute(
                    f"""
                    SELECT claim_type, COUNT(*)
                    FROM scraper_queue
                    {where_sql}
                    AND claim_type IS NOT NULL AND claim_type != ''
                    GROUP BY claim_type
                    """ if where_sql else """
                    SELECT claim_type, COUNT(*)
                    FROM scraper_queue
                    WHERE claim_type IS NOT NULL AND claim_type != ''
                    GROUP BY claim_type
                    """,
                    params,
                ).fetchall()
            }
            queue_owner_counts = {
                str(row[0]): int(row[1] or 0)
                for row in conn.execute(
                    f"""
                    SELECT user_id, COUNT(*)
                    FROM scraper_queue
                    {where_sql}
                    AND user_id IS NOT NULL AND user_id != ''
                    GROUP BY user_id
                    """ if where_sql else """
                    SELECT user_id, COUNT(*)
                    FROM scraper_queue
                    WHERE user_id IS NOT NULL AND user_id != ''
                    GROUP BY user_id
                    """,
                    params,
                ).fetchall()
            }

            queued_clauses = [*clauses, "status = 'queued'"]
            queued_params = [*params]
            queued_where_sql = f"WHERE {' AND '.join(queued_clauses)}"
            ready_row = conn.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE available_at <= CURRENT_TIMESTAMP),
                    MIN(available_at)
                FROM scraper_queue
                {queued_where_sql}
                """,
                queued_params,
            ).fetchone()
            conn.close()
            ready_count = int(ready_row[0] or 0) if ready_row else 0
            next_available_at = ready_row[1] if ready_row else None
        except Exception as e:
            self.mediator.log('scraper_queue_state_error', error=str(e), user_id=user_id, status=status)
            status_counts = {}
            claim_type_counts = {}
            queue_owner_counts = {}
            ready_count = 0
            next_available_at = None
            for job in jobs:
                job_status = str(job.get('status') or 'queued')
                status_counts[job_status] = status_counts.get(job_status, 0) + 1

        return {
            'available': DUCKDB_AVAILABLE,
            'user_id': user_id,
            'status': status,
            'jobs': jobs,
            'job_count': sum(status_counts.values()),
            'status_counts': status_counts,
            'claim_type_counts': claim_type_counts,
            'queue_owner_counts': queue_owner_counts,
            'ready_queued_count': ready_count,
            'running_count': status_counts.get('running', 0),
            'completed_count': status_counts.get('completed', 0),
            'failed_count': status_counts.get('failed', 0),
            'next_available_at': next_available_at,
            'inspection_only': True,
        }

    def get_scraper_queue_job(self, job_id: int) -> Dict[str, Any]:
        """Return one queued scraper job."""
        if not DUCKDB_AVAILABLE:
            return {'available': False, 'job_id': job_id}

        try:
            conn = duckdb.connect(self.db_path)
            row = conn.execute(
                """
                SELECT id, user_id, username, claim_type, keywords, domains,
                       iterations, sleep_seconds, quality_domain, min_relevance,
                       store_results, priority, status, available_at, claimed_at,
                       completed_at, worker_id, run_id, error, metadata,
                       created_at, updated_at
                FROM scraper_queue
                WHERE id = ?
                LIMIT 1
                """,
                [int(job_id)],
            ).fetchone()
            conn.close()
            if not row:
                return {'available': False, 'job_id': job_id}
            return {'available': True, 'job': self._serialize_scraper_queue_row(row)}
        except Exception as e:
            self.mediator.log('scraper_queue_job_error', error=str(e), job_id=job_id)
            return {'available': False, 'job_id': job_id, 'error': str(e)}

    def claim_next_scraper_job(self,
                               worker_id: str,
                               *,
                               user_id: Optional[str] = None) -> Dict[str, Any]:
        """Claim the next available scraper job so only queued work is processed."""
        if not DUCKDB_AVAILABLE:
            return {'claimed': False, 'job': None}

        try:
            conn = duckdb.connect(self.db_path)
            for _ in range(3):
                clauses = ["status = 'queued'", 'available_at <= CURRENT_TIMESTAMP']
                params: List[Any] = []
                if user_id:
                    clauses.append('user_id = ?')
                    params.append(user_id)

                row = conn.execute(
                    f"""
                    SELECT id
                    FROM scraper_queue
                    WHERE {' AND '.join(clauses)}
                    ORDER BY priority ASC, available_at ASC, created_at ASC
                    LIMIT 1
                    """,
                    params,
                ).fetchone()
                if not row:
                    conn.close()
                    return {'claimed': False, 'job': None}

                claimed_row = conn.execute(
                    """
                    UPDATE scraper_queue
                    SET status = 'running',
                        claimed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP,
                        worker_id = ?
                    WHERE id = ? AND status = 'queued'
                    RETURNING id, user_id, username, claim_type, keywords, domains,
                              iterations, sleep_seconds, quality_domain, min_relevance,
                              store_results, priority, status, available_at, claimed_at,
                              completed_at, worker_id, run_id, error, metadata,
                              created_at, updated_at
                    """,
                    [worker_id, int(row[0])],
                ).fetchone()
                if claimed_row:
                    conn.close()
                    job = self._serialize_scraper_queue_row(claimed_row)
                    self.mediator.log('scraper_job_claimed', job_id=job['id'], worker_id=worker_id)
                    return {'claimed': True, 'job': job}

            conn.close()
            return {'claimed': False, 'job': None}
        except Exception as e:
            self.mediator.log('scraper_job_claim_error', error=str(e), worker_id=worker_id, user_id=user_id)
            return {'claimed': False, 'job': None, 'error': str(e)}

    def complete_scraper_job(self,
                             job_id: int,
                             *,
                             run_id: Optional[int] = None,
                             error: Optional[str] = None,
                             metadata: Optional[Dict[str, Any]] = None,
                             worker_id: Optional[str] = None) -> Dict[str, Any]:
        """Mark a claimed scraper job as completed or failed."""
        if not DUCKDB_AVAILABLE:
            return {'updated': False, 'job_id': job_id}

        try:
            conn = duckdb.connect(self.db_path)
            current = conn.execute(
                """
                SELECT status, worker_id, metadata
                FROM scraper_queue
                WHERE id = ?
                LIMIT 1
                """,
                [int(job_id)],
            ).fetchone()
            if not current:
                conn.close()
                return {'updated': False, 'job_id': job_id, 'error': 'job_not_found'}
            current_status = str(current[0] or '')
            current_worker_id = str(current[1] or '')
            if current_status != 'running':
                conn.close()
                return {
                    'updated': False,
                    'job_id': job_id,
                    'error': 'job_not_running',
                    'current_status': current_status,
                }
            if worker_id and current_worker_id and str(worker_id) != current_worker_id:
                conn.close()
                return {
                    'updated': False,
                    'job_id': job_id,
                    'error': 'worker_mismatch',
                    'worker_id': worker_id,
                    'claimed_worker_id': current_worker_id,
                }

            merged_metadata = json.loads(current[2]) if current and current[2] else {}
            if metadata:
                merged_metadata.update(metadata)
            merged_metadata = _merge_intake_summary_handoff_metadata(
                merged_metadata,
                self.mediator,
            )

            status = 'failed' if error else 'completed'
            row = conn.execute(
                """
                UPDATE scraper_queue
                SET status = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    run_id = ?,
                    error = ?,
                    metadata = ?
                WHERE id = ? AND status = 'running'
                RETURNING id, user_id, username, claim_type, keywords, domains,
                          iterations, sleep_seconds, quality_domain, min_relevance,
                          store_results, priority, status, available_at, claimed_at,
                          completed_at, worker_id, run_id, error, metadata,
                          created_at, updated_at
                """,
                [status, run_id, error, json.dumps(merged_metadata), int(job_id)],
            ).fetchone()
            conn.close()
            if not row:
                return {'updated': False, 'job_id': job_id}

            job = self._serialize_scraper_queue_row(row)
            self.mediator.log('scraper_job_completed', job_id=job_id, status=status, run_id=run_id)
            return {'updated': True, 'job': job}
        except Exception as e:
            self.mediator.log('scraper_job_complete_error', error=str(e), job_id=job_id)
            return {'updated': False, 'job_id': job_id, 'error': str(e)}


class EvidenceAnalysisHook:
    """
    Hook for analyzing stored evidence.
    
    Provides methods to retrieve, analyze, and generate insights from
    evidence stored in IPFS and tracked in DuckDB.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
    
    def analyze_evidence_for_claim(self, user_id: str, claim_type: str) -> Dict[str, Any]:
        """
        Analyze evidence for a specific claim type.
        
        Args:
            user_id: User identifier
            claim_type: Type of legal claim
            
        Returns:
            Analysis results including evidence count, types, and recommendations
        """
        # Get evidence state hook from mediator
        if not hasattr(self.mediator, 'evidence_state'):
            return {'error': 'Evidence state hook not available'}
        
        try:
            # Get all user evidence
            all_evidence = self.mediator.evidence_state.get_user_evidence(user_id)
            
            # Filter by claim type
            claim_evidence = [e for e in all_evidence if e.get('claim_type') == claim_type]
            
            # Analyze evidence types
            evidence_types = {}
            for evidence in claim_evidence:
                ev_type = evidence['type']
                evidence_types[ev_type] = evidence_types.get(ev_type, 0) + 1
            
            # Generate analysis
            analysis = {
                'claim_type': claim_type,
                'total_evidence': len(claim_evidence),
                'evidence_by_type': evidence_types,
                'evidence_items': claim_evidence
            }
            
            # Use LLM to generate recommendations if available
            if claim_evidence:
                analysis['has_evidence'] = True
                analysis['recommendation'] = self._generate_evidence_recommendations(
                    claim_type, claim_evidence
                )
            else:
                analysis['has_evidence'] = False
                analysis['recommendation'] = f'No evidence found for {claim_type}. Consider gathering relevant documents, communications, or other supporting materials.'
            
            return analysis
            
        except Exception as e:
            self.mediator.log('evidence_analysis_error', error=str(e))
            return {'error': str(e)}
    
    def _generate_evidence_recommendations(self, claim_type: str, 
                                          evidence: List[Dict[str, Any]]) -> str:
        """Generate evidence recommendations using LLM."""
        evidence_summary = '\n'.join([
            f"- {e['type']}: {e.get('description', 'No description')} (CID: {e['cid']})"
            for e in evidence[:10]  # Limit to first 10 items
        ])
        
        prompt = f"""Based on the following evidence for a {claim_type} claim, provide recommendations:

Evidence:
{evidence_summary}

Provide brief recommendations for:
1. Strength of current evidence
2. Any gaps or missing evidence types
3. Next steps for evidence gathering
"""
        
        try:
            response = self.mediator.query_backend(prompt)
            return response
        except Exception as exc:
            self.mediator.log(
                'evidence_recommendation_degraded',
                operation='generate_evidence_recommendations',
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return 'Evidence analysis available. Review submitted evidence and consider any gaps in documentation.'

    def analyze_scoped_case(self, state: "EvidenceStateHook", *, case_id: str, actor_id: str, claim_type: str) -> Dict[str, Any]:
        """Count admitted evidence chunks for this case and actor.

        Annotation rows stay out of the evidence count. Model text is not consulted.
        """

        rows = [
            row for row in _scoped_rows(state)
            if row.get("case_id") == case_id and row.get("actor_id") == actor_id and row.get("claim_type") == claim_type
        ]
        evidence = [row for row in rows if row.get("kind") == "evidence" and row.get("annotation") is not True]
        annotations = [row for row in rows if row.get("kind") == "annotation"]
        return {
            "claim_type": claim_type,
            "case_id": case_id,
            "actor_id": actor_id,
            "evidence_count": len(evidence),
            "annotation_count": len(annotations),
            "chunk_count": sum(int(row.get("chunk_count") or 0) for row in evidence),
            "evidence_ids": [str(row.get("record_id") or "") for row in evidence],
            "annotation_ids": [str(row.get("record_id") or "") for row in annotations],
            "annotation_converted_to_evidence": False,
            "plaintext_fallback": False,
            "model_consulted": False,
        }


_UNSAFE_MARKERS = (b"\x00", b"<script", b"javascript:", "\u202e".encode("utf-8"))
_QUALIFY_OPERATION = "qualify_private_evidence"


def _scoped_rows(state: "EvidenceStateHook") -> List[Dict[str, Any]]:
    rows = getattr(state, "_scoped_owner_rows", None)
    if rows is None:
        state._scoped_owner_rows = []
        rows = state._scoped_owner_rows
    return rows


def _qualification_refusal(code: str, status: str, **extra: Any) -> Dict[str, Any]:
    receipt = {
        "status": status,
        "code": code,
        "plaintext_fallback": False,
        "plaintext_persisted": False,
        "annotation_converted_to_evidence": False,
        "local_durable": False,
        "remote_durable": False,
        "writes": 0,
        "evidence_count": 0,
        "annotation_count": 0,
        "chunk_count": 0,
    }
    receipt.update(extra)
    return receipt


def _consent_allows(consent: Any, *, case_id: str, actor_id: str) -> bool:
    if not isinstance(consent, dict):
        return False
    if consent.get("revoked") is True or consent.get("granted") is not True:
        return False
    if consent.get("case_id") != case_id or consent.get("actor_id") != actor_id:
        return False
    operations = consent.get("operations")
    return isinstance(operations, list) and _QUALIFY_OPERATION in operations


def _unsafe_source(payload: bytes) -> bool:
    return any(marker in payload for marker in _UNSAFE_MARKERS)


class _QualificationLog:
    def log(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def query_backend(self, _prompt: str) -> str:
        raise EvidenceHookError("model text is not evidence")


def qualify_scoped_private_evidence(
    root: str,
    *,
    case_id: str,
    actor_id: str,
    tenant_id: str,
    revision: str,
    source: bytes,
    source_sha256: str,
    key: bytes | None,
    key_id: str,
    consent: Any,
    annotation: bytes | None = None,
    annotation_sha256: str | None = None,
    claim_type: str = "synthetic-claim",
    key_locked: bool = False,
    capability_available: bool | None = None,
    db_path: str | None = None,
) -> Dict[str, Any]:
    """Qualify storage, state, and analysis for one case and actor.

    Ciphertext goes through the Kit local owner. Chunks and chunk metadata
    come from the dataset text owner. Annotations stay annotations.
    """

    from integrations.ipfs_datasets.documents import parse_document_text
    from integrations.private_storage import (
        BoundPrivateRecordError,
        PrivateArtifactBinding,
        commit_scoped_kit_record,
        open_scoped_kit_record,
        probe_kit_evidence_capability,
    )

    scope = {"case_id": case_id, "actor_id": actor_id, "revision": revision}
    if not _consent_allows(consent, case_id=case_id, actor_id=actor_id):
        return _qualification_refusal("consent_refused", "refused", **scope)
    if key_locked or key is None:
        return _qualification_refusal("key_locked", "refused", **scope)
    if not isinstance(source, (bytes, bytearray)) or _unsafe_source(bytes(source)):
        return _qualification_refusal("unsafe_content", "refused", **scope)
    if annotation is not None and _unsafe_source(bytes(annotation)):
        return _qualification_refusal("unsafe_content", "refused", **scope)
    probed = probe_kit_evidence_capability()
    if capability_available is False or probed.get("available") is not True:
        return _qualification_refusal("missing_capability", "unavailable", **scope, kit_owner=probed.get("owner", ""))
    if not isinstance(source_sha256, str) or source_sha256 != hashlib.sha256(bytes(source)).hexdigest():
        return _qualification_refusal("source_integrity", "refused", **scope)

    try:
        text = bytes(source).decode("utf-8")
    except UnicodeError:
        return _qualification_refusal("source_integrity", "refused", **scope)
    parsed = parse_document_text(text, filename="evidence.txt", mime_type="text/plain", source="scoped-evidence")
    chunks = list((parsed or {}).get("chunks") or [])
    if not chunks:
        return _qualification_refusal("source_integrity", "refused", **scope)
    chunk_meta = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            return _qualification_refusal("missing_capability", "unavailable", **scope, kit_owner="dataset-chunk-owner")
        chunk_text = str(chunk.get("text") or "")
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        chunk_meta.append({
            "chunk_id": str(chunk.get("chunk_id") or ""),
            "index": int(chunk.get("index") or 0),
            "start": int(chunk.get("start") or 0),
            "end": int(chunk.get("end") or 0),
            "sha256": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
            "extraction_method": str(metadata.get("extraction_method") or ""),
            "owner": "integrations.ipfs_datasets.documents.parse_document_text",
        })
    metadata_bytes = json.dumps({"chunks": chunk_meta, "case_id": case_id, "actor_id": actor_id}, sort_keys=True).encode("utf-8")
    evidence_binding = PrivateArtifactBinding(
        tenant_id=tenant_id, case_id=case_id, artifact_kind="evidence",
        revision=f"{revision}.evidence", principal_id=actor_id,
    )
    metadata_binding = PrivateArtifactBinding(
        tenant_id=tenant_id, case_id=case_id, artifact_kind="classification_revision",
        revision=f"{revision}.metadata", principal_id=actor_id,
    )
    try:
        stored = commit_scoped_kit_record(
            root, record_id=f"ev-{revision}", kind="evidence", plaintext=bytes(source),
            binding=evidence_binding, key=key, key_id=key_id, source_sha256=source_sha256, key_locked=key_locked,
        )
        meta_stored = commit_scoped_kit_record(
            root, record_id=f"md-{revision}", kind="classification_revision", plaintext=metadata_bytes,
            binding=metadata_binding, key=key, key_id=key_id,
            source_sha256=hashlib.sha256(metadata_bytes).hexdigest(), key_locked=key_locked,
        )
        annotation_stored = None
        if annotation is not None:
            if not isinstance(annotation_sha256, str):
                return _qualification_refusal("source_integrity", "refused", **scope)
            note_binding = PrivateArtifactBinding(
                tenant_id=tenant_id, case_id=case_id, artifact_kind="annotation",
                revision=f"{revision}.annotation", principal_id=actor_id,
            )
            annotation_stored = commit_scoped_kit_record(
                root, record_id=f"an-{revision}", kind="annotation", plaintext=bytes(annotation),
                binding=note_binding, key=key, key_id=key_id, source_sha256=annotation_sha256, key_locked=key_locked,
            )
        opened = open_scoped_kit_record(root, record_id=f"ev-{revision}", binding=evidence_binding, key=key)
        opened_meta = open_scoped_kit_record(root, record_id=f"md-{revision}", binding=metadata_binding, key=key)
    except BoundPrivateRecordError as exc:
        code = exc.code if exc.code in {"key_locked", "conflicting_revision", "source_integrity", "missing_capability"} else "source_integrity"
        status = "unavailable" if code == "missing_capability" else "refused"
        return _qualification_refusal(code, status, **scope)
    if opened != bytes(source) or opened_meta != metadata_bytes:
        return _qualification_refusal("source_integrity", "refused", **scope)
    admitted_meta = json.loads(opened_meta.decode("utf-8"))
    if admitted_meta.get("chunks") != chunk_meta:
        return _qualification_refusal("source_integrity", "refused", **scope)

    mediator = _QualificationLog()
    storage = EvidenceStorageHook(mediator)
    state = EvidenceStateHook(mediator, db_path=db_path)
    analysis = EvidenceAnalysisHook(mediator)
    state_row = {
        "case_id": case_id,
        "actor_id": actor_id,
        "kind": "evidence",
        "record_id": stored["record_id"],
        "revision": evidence_binding.revision,
        "source_sha256": stored["source_sha256"],
        "chunk_count": len(chunk_meta),
        "claim_type": claim_type,
        "annotation": False,
        "metadata_record_id": meta_stored["record_id"],
        "dataset_owner": "integrations.ipfs_datasets.documents.parse_document_text",
        "kit_owner": stored["kit_owner"],
    }
    _scoped_rows(state).append(state_row)
    if annotation_stored is not None:
        _scoped_rows(state).append({
            "case_id": case_id,
            "actor_id": actor_id,
            "kind": "annotation",
            "record_id": annotation_stored["record_id"],
            "revision": f"{revision}.annotation",
            "annotation": True,
            "claim_type": claim_type,
            "chunk_count": 0,
        })
    report = analysis.analyze_scoped_case(state, case_id=case_id, actor_id=actor_id, claim_type=claim_type)
    return {
        "status": "qualified",
        "code": "qualified",
        "plaintext_fallback": False,
        "plaintext_persisted": False,
        "annotation_converted_to_evidence": False,
        "local_durable": True,
        "remote_durable": False,
        "writes": 2 if annotation_stored is None else 3,
        "case_id": case_id,
        "actor_id": actor_id,
        "revision": revision,
        "evidence_count": report["evidence_count"],
        "annotation_count": report["annotation_count"],
        "chunk_count": report["chunk_count"],
        "analysis_evidence_ids": report["evidence_ids"],
        "analysis_annotation_ids": report["annotation_ids"],
        "metadata_record_id": meta_stored["record_id"],
        "evidence_record_id": stored["record_id"],
        "dataset_owner": state_row["dataset_owner"],
        "kit_owner": stored["kit_owner"],
        "storage_owner": type(storage).__name__,
        "state_owner": type(state).__name__,
        "analysis_owner": type(analysis).__name__,
        "source_sha256": stored["source_sha256"],
    }


def read_scoped_private_evidence(
    root: str,
    *,
    case_id: str,
    actor_id: str,
    tenant_id: str,
    revision: str,
    key: bytes | None,
    record: str = "evidence",
    key_locked: bool = False,
) -> bytes:
    from integrations.private_storage import PrivateArtifactBinding, open_scoped_kit_record

    kinds = {"evidence": "evidence", "metadata": "classification_revision", "annotation": "annotation"}
    ids = {"evidence": f"ev-{revision}", "metadata": f"md-{revision}", "annotation": f"an-{revision}"}
    if record not in kinds:
        raise EvidenceRetrievalError("record rejected", code="source_integrity")
    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=kinds[record],
        revision=f"{revision}.{record if record != 'metadata' else 'metadata'}",
        principal_id=actor_id,
    )
    try:
        return open_scoped_kit_record(root, record_id=ids[record], binding=binding, key=key, key_locked=key_locked)
    except Exception as exc:
        code = getattr(exc, "code", "source_integrity")
        raise EvidenceRetrievalError("scoped evidence is unavailable", code=code) from exc
