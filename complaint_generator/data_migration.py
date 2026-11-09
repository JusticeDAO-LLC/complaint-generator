from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

try:
    import duckdb
except Exception:  # pragma: no cover - optional dependency
    duckdb = None

from integrations.ipfs_datasets.legal_data import load_legal_symbol

WorkspaceDatasetBuilder = load_legal_symbol("WorkspaceDatasetBuilder")
WorkspaceDatasetObject = load_legal_symbol("WorkspaceDatasetObject")
WorkspaceDatasetPackager = load_legal_symbol("WorkspaceDatasetPackager")
export_workspace_dataset_single_parquet = load_legal_symbol("export_workspace_dataset_single_parquet")


SCHEMA_SNAPSHOT_VERSION = "workspace_data_schema.v1"

_JSONISH_KEYS = {
    "metadata",
    "provenance",
    "payload",
    "raw",
    "parse_metadata",
    "graph_metadata",
    "config",
    "quality",
    "keywords",
    "domains",
    "coverage",
    "critique",
    "required_support_kinds",
}


def _slug(value: Any) -> str:
    text = "".join(ch.lower() if str(ch).isalnum() else "_" for ch in str(value or "")).strip("_")
    return text or "item"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return str(value)


def _parse_possible_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[:1] not in {"{", "["}:
        return value
    try:
        return json.loads(text)
    except Exception:
        return value


def _read_json_file(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _query_duckdb(path: Path, query: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    if duckdb is None or not path.exists():
        return []
    conn = duckdb.connect(str(path), read_only=True)
    try:
        cursor = conn.execute(query, list(params))
        columns = [str(item[0]) for item in list(cursor.description or [])]
        rows: list[dict[str, Any]] = []
        for raw_row in cursor.fetchall():
            row = {columns[index]: raw_row[index] for index in range(len(columns))}
            for key in list(row.keys()):
                if key in _JSONISH_KEYS:
                    row[key] = _parse_possible_json(row.get(key))
            rows.append(row)
        return rows
    finally:
        conn.close()


def _table_exists(path: Path, table_name: str) -> bool:
    if duckdb is None or not path.exists():
        return False
    conn = duckdb.connect(str(path), read_only=True)
    try:
        rows = conn.execute("PRAGMA show_tables").fetchall()
    finally:
        conn.close()
    return table_name in {str(row[0]) for row in rows}


def _query_if_table_exists(path: Optional[str | Path], table_name: str, query: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    if path is None:
        return []
    resolved = Path(path).expanduser().resolve()
    if not _table_exists(resolved, table_name):
        return []
    return _query_duckdb(resolved, query, params)


def _summarize_json(value: Any) -> str:
    normalized = _jsonable(value)
    if normalized in (None, "", [], {}):
        return ""
    text = json.dumps(normalized, indent=2, sort_keys=True, ensure_ascii=False)
    return text[:4000]


class _WorkspaceAssembler:
    def __init__(self, *, workspace_id: str, workspace_name: str, source_type: str, base_metadata: Optional[Dict[str, Any]] = None) -> None:
        self.workspace_id = workspace_id
        self.workspace_name = workspace_name
        self.source_type = source_type
        self.metadata = dict(base_metadata or {})
        self.documents: list[dict[str, Any]] = []
        self.collections: list[dict[str, Any]] = []
        self._collection_index: dict[str, int] = {}

    def add_document(
        self,
        *,
        collection_id: str,
        collection_title: str,
        collection_source_type: str,
        title: str,
        text: str,
        document_type: str,
        source_path: str = "",
        captured_at: str = "",
        document_number: str = "",
        source_url: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        document_id: Optional[str] = None,
        parent_document_id: str = "",
    ) -> None:
        clean_text = str(text or "").strip()
        if not clean_text:
            return
        normalized_collection_id = str(collection_id or f"collection_{len(self.collections) + 1}")
        if normalized_collection_id not in self._collection_index:
            self._collection_index[normalized_collection_id] = len(self.collections)
            self.collections.append(
                {
                    "id": normalized_collection_id,
                    "title": str(collection_title or normalized_collection_id),
                    "source_type": str(collection_source_type or self.source_type),
                    "source_path": str(source_path or ""),
                    "parent_document_id": str(parent_document_id or ""),
                    "document_ids": [],
                }
            )
        doc_id = str(document_id or f"{normalized_collection_id}_doc_{len(self.documents) + 1}")
        collection = self.collections[self._collection_index[normalized_collection_id]]
        collection["document_ids"] = list(collection.get("document_ids") or []) + [doc_id]
        self.documents.append(
            {
                "id": doc_id,
                "document_id": doc_id,
                "title": str(title or doc_id),
                "text": clean_text,
                "captured_at": str(captured_at or ""),
                "document_number": str(document_number or ""),
                "source_url": str(source_url or ""),
                "document_type": str(document_type or "record"),
                "metadata": {
                    "collection_id": normalized_collection_id,
                    "document_type": str(document_type or "record"),
                    "parent_document_id": str(parent_document_id or ""),
                    **dict(metadata or {}),
                },
            }
        )

    def to_workspace_payload(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "source_type": self.source_type,
            "collections": list(self.collections),
            "documents": list(self.documents),
            "metadata": dict(self.metadata),
        }


def _build_state_documents(assembler: _WorkspaceAssembler, state: Mapping[str, Any], *, statefile_path: Optional[Path]) -> None:
    user_id = str(state.get("user_id") or assembler.workspace_id)
    intake_answers = dict(state.get("intake_answers") or {})
    intake_history = list(state.get("intake_history") or [])
    evidence = dict(state.get("evidence") or {})
    draft = dict(state.get("draft") or {})
    filing_metadata = dict(state.get("filing_metadata") or {})
    case_synopsis = str(state.get("case_synopsis") or "").strip()
    state_source = str(statefile_path) if statefile_path is not None else ""

    if intake_answers:
        assembler.add_document(
            collection_id="legacy_intake_answers",
            collection_title="Legacy Intake Answers",
            collection_source_type="legacy_session_json",
            title="Legacy intake answers",
            text=_summarize_json(intake_answers),
            document_type="intake_answers",
            source_path=state_source,
            metadata={"user_id": user_id, "record_scope": "intake_answers", "raw": dict(intake_answers)},
            document_id=f"{_slug(user_id)}_intake_answers",
        )
    for index, entry in enumerate(intake_history, start=1):
        if not isinstance(entry, Mapping):
            continue
        answer = str(entry.get("answer") or entry.get("message") or "").strip()
        question = str(entry.get("question") or entry.get("question_id") or f"intake_history_{index}")
        if not answer:
            continue
        assembler.add_document(
            collection_id="legacy_intake_history",
            collection_title="Legacy Intake History",
            collection_source_type="legacy_session_json",
            title=question,
            text=answer,
            document_type="intake_history",
            source_path=state_source,
            captured_at=str(entry.get("timestamp") or ""),
            metadata={"user_id": user_id, "record_scope": "intake_history", "raw": dict(entry)},
            document_id=f"{_slug(user_id)}_intake_history_{index}",
        )
    if case_synopsis:
        assembler.add_document(
            collection_id="legacy_case_summary",
            collection_title="Legacy Case Summary",
            collection_source_type="legacy_session_json",
            title="Legacy case synopsis",
            text=case_synopsis,
            document_type="case_synopsis",
            source_path=state_source,
            metadata={"user_id": user_id, "record_scope": "case_synopsis"},
            document_id=f"{_slug(user_id)}_case_synopsis",
        )
    if filing_metadata:
        assembler.add_document(
            collection_id="legacy_filing_metadata",
            collection_title="Legacy Filing Metadata",
            collection_source_type="legacy_session_json",
            title="Legacy filing metadata",
            text=_summarize_json(filing_metadata),
            document_type="filing_metadata",
            source_path=state_source,
            metadata={"user_id": user_id, "record_scope": "filing_metadata", "raw": dict(filing_metadata)},
            document_id=f"{_slug(user_id)}_filing_metadata",
        )
    if draft:
        draft_body = str(draft.get("body") or "").strip()
        if draft_body:
            assembler.add_document(
                collection_id="legacy_draft",
                collection_title="Legacy Complaint Draft",
                collection_source_type="legacy_session_json",
                title=str(draft.get("title") or "Legacy complaint draft"),
                text=draft_body,
                document_type="complaint_draft",
                source_path=state_source,
                captured_at=str(draft.get("updated_at") or state.get("updated_at") or ""),
                metadata={"user_id": user_id, "record_scope": "draft", "raw": dict(draft)},
                document_id=f"{_slug(user_id)}_draft",
            )
    for evidence_kind in ("testimony", "documents"):
        for index, item in enumerate(list(evidence.get(evidence_kind) or []), start=1):
            if not isinstance(item, Mapping):
                continue
            text = str(item.get("content") or item.get("text") or item.get("body") or "").strip()
            if not text:
                continue
            assembler.add_document(
                collection_id=f"legacy_session_{evidence_kind}",
                collection_title=f"Legacy Session {evidence_kind.title()}",
                collection_source_type="legacy_session_json",
                title=str(item.get("title") or f"{evidence_kind.title()} {index}"),
                text=text,
                document_type=str(item.get("kind") or evidence_kind.rstrip("s")),
                source_path=state_source,
                captured_at=str(item.get("created_at") or item.get("timestamp") or ""),
                source_url=str(item.get("source") or ""),
                metadata={"user_id": user_id, "record_scope": f"session_{evidence_kind}", "raw": dict(item)},
                document_id=f"{_slug(user_id)}_{evidence_kind}_{index}",
            )


def _build_evidence_db_documents(assembler: _WorkspaceAssembler, rows: Sequence[Mapping[str, Any]], *, db_path: Optional[str | Path]) -> None:
    source_path = str(Path(db_path).expanduser().resolve()) if db_path else ""
    for row in rows:
        metadata = dict(row.get("metadata") or {})
        preview = str(row.get("parsed_text_preview") or "").strip()
        description = str(row.get("description") or metadata.get("title") or row.get("evidence_type") or "Evidence").strip()
        text = preview or _summarize_json(metadata) or description
        assembler.add_document(
            collection_id="legacy_evidence_db",
            collection_title="Legacy Evidence DuckDB",
            collection_source_type="legacy_evidence_duckdb",
            title=description,
            text=text,
            document_type="evidence_record",
            source_path=source_path,
            captured_at=str(row.get("timestamp") or ""),
            document_number=str(row.get("id") or ""),
            source_url=str(row.get("source_url") or ""),
            metadata={
                "record_scope": "evidence",
                "evidence_cid": str(row.get("evidence_cid") or ""),
                "evidence_type": str(row.get("evidence_type") or ""),
                "claim_type": str(row.get("claim_type") or ""),
                "claim_element_id": str(row.get("claim_element_id") or ""),
                "chunk_count": row.get("chunk_count"),
                "graph_entity_count": row.get("graph_entity_count"),
                "graph_relationship_count": row.get("graph_relationship_count"),
                "metadata_payload": metadata,
                "provenance": row.get("provenance"),
            },
            document_id=f"evidence_db_{row.get('id')}",
        )


def _build_authority_documents(assembler: _WorkspaceAssembler, rows: Sequence[Mapping[str, Any]], *, db_path: Optional[str | Path]) -> None:
    source_path = str(Path(db_path).expanduser().resolve()) if db_path else ""
    for row in rows:
        title = str(row.get("title") or row.get("citation") or row.get("authority_type") or "Legal authority").strip()
        text = str(row.get("content") or row.get("parsed_text_preview") or "").strip() or _summarize_json(row.get("metadata") or {})
        assembler.add_document(
            collection_id="legacy_legal_authorities",
            collection_title="Legacy Legal Authorities",
            collection_source_type="legacy_legal_authority_duckdb",
            title=title,
            text=text,
            document_type="legal_authority",
            source_path=source_path,
            captured_at=str(row.get("timestamp") or ""),
            document_number=str(row.get("id") or ""),
            source_url=str(row.get("url") or ""),
            metadata={
                "record_scope": "legal_authority",
                "authority_type": str(row.get("authority_type") or ""),
                "source": str(row.get("source") or ""),
                "citation": str(row.get("citation") or ""),
                "claim_type": str(row.get("claim_type") or ""),
                "claim_element_id": str(row.get("claim_element_id") or ""),
                "jurisdiction": str(row.get("jurisdiction") or ""),
                "relevance_score": row.get("relevance_score"),
                "metadata_payload": row.get("metadata"),
                "provenance": row.get("provenance"),
            },
            document_id=f"legal_authority_{row.get('id')}",
        )


def _build_claim_support_documents(
    assembler: _WorkspaceAssembler,
    *,
    requirements: Sequence[Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    testimony: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    db_path: Optional[str | Path],
) -> None:
    source_path = str(Path(db_path).expanduser().resolve()) if db_path else ""
    for row in requirements:
        assembler.add_document(
            collection_id="legacy_claim_requirements",
            collection_title="Legacy Claim Requirements",
            collection_source_type="legacy_claim_support_duckdb",
            title=str(row.get("element_text") or row.get("claim_type") or "Claim requirement"),
            text=_summarize_json(row),
            document_type="claim_requirement",
            source_path=source_path,
            captured_at=str(row.get("timestamp") or ""),
            metadata={"record_scope": "claim_requirement", "raw": dict(row)},
            document_id=f"claim_requirement_{_slug(row.get('claim_type'))}_{_slug(row.get('element_id'))}",
        )
    for row in links:
        label = str(row.get("support_label") or row.get("support_ref") or row.get("support_kind") or "Claim support link")
        assembler.add_document(
            collection_id="legacy_claim_support_links",
            collection_title="Legacy Claim Support Links",
            collection_source_type="legacy_claim_support_duckdb",
            title=label,
            text=_summarize_json(row),
            document_type="claim_support_link",
            source_path=source_path,
            captured_at=str(row.get("timestamp") or ""),
            metadata={"record_scope": "claim_support_link", "raw": dict(row)},
            document_id=f"claim_support_link_{row.get('id')}",
        )
    for row in testimony:
        title = str(row.get("claim_element_text") or row.get("testimony_id") or "Claim testimony").strip()
        text = str(row.get("raw_narrative") or "").strip() or _summarize_json(row)
        assembler.add_document(
            collection_id="legacy_claim_testimony",
            collection_title="Legacy Claim Testimony",
            collection_source_type="legacy_claim_support_duckdb",
            title=title,
            text=text,
            document_type="claim_testimony",
            source_path=source_path,
            captured_at=str(row.get("timestamp") or row.get("event_date") or ""),
            metadata={"record_scope": "claim_testimony", "raw": dict(row)},
            document_id=str(row.get("testimony_id") or f"claim_testimony_{len(assembler.documents) + 1}"),
        )
    for row in snapshots:
        title = str(row.get("snapshot_kind") or row.get("claim_type") or "Claim support snapshot").strip()
        text = _summarize_json(row.get("payload") or row)
        assembler.add_document(
            collection_id="legacy_claim_support_snapshots",
            collection_title="Legacy Claim Support Snapshots",
            collection_source_type="legacy_claim_support_duckdb",
            title=title,
            text=text,
            document_type="claim_support_snapshot",
            source_path=source_path,
            captured_at=str(row.get("timestamp") or ""),
            metadata={"record_scope": "claim_support_snapshot", "raw": dict(row)},
            document_id=f"claim_support_snapshot_{row.get('id')}",
        )


def _extract_piece_fields(piece: Mapping[str, Any]) -> list[str]:
    fields = []
    for field in list(piece.get("schema") or []):
        name = str((field or {}).get("name") or "").strip()
        if name:
            fields.append(name)
    return fields


def build_workspace_schema_snapshot(
    *,
    package_result: Mapping[str, Any],
    dataset: Mapping[str, Any] | WorkspaceDatasetObject,
) -> Dict[str, Any]:
    dataset_payload = dataset.to_dict() if isinstance(dataset, WorkspaceDatasetObject) else dict(dataset)
    pieces = [dict(item) for item in list(package_result.get("pieces") or []) if isinstance(item, Mapping)]
    documents = [dict(item) for item in list(dataset_payload.get("documents") or []) if isinstance(item, Mapping)]
    collections = [dict(item) for item in list(dataset_payload.get("collections") or []) if isinstance(item, Mapping)]
    document_fields = sorted({str(key) for item in documents for key in item.keys()})
    metadata_fields = sorted(
        {
            str(key)
            for item in documents
            for key in dict(item.get("metadata") or {}).keys()
            if str(key).strip()
        }
    )
    collection_fields = sorted({str(key) for item in collections for key in item.keys()})
    piece_schemas = [
        {
            "piece_id": str(piece.get("piece_id") or ""),
            "group": str(piece.get("group") or ""),
            "row_count": int(piece.get("row_count") or 0),
            "depends_on": list(piece.get("depends_on") or []),
            "fields": _extract_piece_fields(piece),
            "schema": list(piece.get("schema") or []),
        }
        for piece in pieces
    ]
    filter_dimensions = [
        item
        for item in [
            "collection_id" if "collection_id" in metadata_fields else "",
            "document_type" if "document_type" in metadata_fields else "",
            "claim_type" if "claim_type" in metadata_fields else "",
            "claim_element_id" if "claim_element_id" in metadata_fields else "",
            "source_type",
            "captured_at" if "captured_at" in document_fields else "",
        ]
        if item
    ]
    ui_design_hints = [
        {
            "id": "workspace_summary_counts",
            "reason": "Surface dataset summary chips for documents, collections, and indexed artifacts at the top of the workspace.",
        }
    ]
    if len(collections) > 1:
        ui_design_hints.append(
            {
                "id": "collection_facet_navigation",
                "reason": "Use collection tabs or filters because the migrated workspace contains multiple source collections.",
            }
        )
    if {"bm25_documents", "vector_items"}.issubset({str(piece.get("piece_id") or "") for piece in pieces}):
        ui_design_hints.append(
            {
                "id": "dual_search_modes",
                "reason": "Expose keyword and semantic search toggles because both BM25 and vector retrieval artifacts are available.",
            }
        )
    if "claim_element_id" in metadata_fields or "claim_type" in metadata_fields:
        ui_design_hints.append(
            {
                "id": "claim_alignment_filters",
                "reason": "Show claim-type and claim-element chips so review and drafting stay aligned with the migrated support records.",
            }
        )
    if "provenance" in metadata_fields or "metadata_payload" in metadata_fields:
        ui_design_hints.append(
            {
                "id": "provenance_drilldowns",
                "reason": "Add provenance drawers or drilldowns because the records retain metadata and migration lineage.",
            }
        )
    mcp_design_hints = [
        {
            "id": "manifest_first_tooling",
            "reason": "Prefer tools that accept `manifest_path` or `user_id` and return structured summary views rather than raw row dumps.",
        }
    ]
    if filter_dimensions:
        mcp_design_hints.append(
            {
                "id": "schema_guided_filters",
                "reason": f"Add filter parameters for {', '.join(filter_dimensions)} so MCP queries can target the narrowest relevant workspace slice.",
            }
        )
    if any(str(piece.get("piece_id") or "").startswith("knowledge_graph") for piece in pieces):
        mcp_design_hints.append(
            {
                "id": "knowledge_graph_presence",
                "reason": "Expose graph-aware MCP affordances because the packaged workspace includes knowledge-graph entities and relationships.",
            }
        )
    chain_load_order = [
        str(item)
        for item in list(package_result.get("chain_load_order") or [])
        if str(item).strip()
    ] or [str(piece.get("piece_id") or "") for piece in pieces if str(piece.get("piece_id") or "")]
    return {
        "schema_version": SCHEMA_SNAPSHOT_VERSION,
        "dataset_id": str(dataset_payload.get("dataset_id") or ""),
        "workspace_id": str(dataset_payload.get("workspace_id") or ""),
        "workspace_name": str(dataset_payload.get("workspace_name") or ""),
        "source_type": str(dataset_payload.get("source_type") or "workspace"),
        "summary": dict(package_result.get("summary") or {}),
        "piece_schemas": piece_schemas,
        "chain_load_order": chain_load_order,
        "document_fields": document_fields,
        "document_metadata_fields": metadata_fields,
        "collection_fields": collection_fields,
        "filter_dimensions": filter_dimensions,
        "ui_design_hints": ui_design_hints,
        "mcp_design_hints": mcp_design_hints,
    }


def build_workspace_dataset_from_legacy_sources(
    *,
    state: Mapping[str, Any],
    statefile_path: Optional[str | Path] = None,
    evidence_db_path: Optional[str | Path] = None,
    legal_authority_db_path: Optional[str | Path] = None,
    claim_support_db_path: Optional[str | Path] = None,
    user_id: Optional[str] = None,
    vector_dimension: int = 16,
) -> tuple[WorkspaceDatasetObject, Dict[str, Any]]:
    resolved_user_id = str(user_id or state.get("user_id") or "workspace")
    statefile = Path(statefile_path).expanduser().resolve() if statefile_path else None
    synopsis = str(state.get("case_synopsis") or "").strip()
    assembler = _WorkspaceAssembler(
        workspace_id=resolved_user_id,
        workspace_name=synopsis or f"Complaint Workspace {resolved_user_id}",
        source_type="legacy_complaint_workspace",
        base_metadata={
            "migration_source": "legacy_complaint_workspace",
            "statefile_path": str(statefile) if statefile else "",
            "user_id": resolved_user_id,
        },
    )
    _build_state_documents(assembler, state, statefile_path=statefile)

    user_param = [resolved_user_id]
    evidence_rows = _query_if_table_exists(
        evidence_db_path,
        "evidence",
        "SELECT * FROM evidence WHERE user_id = ? ORDER BY timestamp ASC, id ASC",
        user_param,
    )
    authority_rows = _query_if_table_exists(
        legal_authority_db_path,
        "legal_authorities",
        "SELECT * FROM legal_authorities WHERE user_id = ? ORDER BY timestamp ASC, id ASC",
        user_param,
    )
    requirement_rows = _query_if_table_exists(
        claim_support_db_path,
        "claim_requirements",
        "SELECT * FROM claim_requirements WHERE user_id = ? ORDER BY claim_type ASC, element_index ASC",
        user_param,
    )
    support_rows = _query_if_table_exists(
        claim_support_db_path,
        "claim_support",
        "SELECT * FROM claim_support WHERE user_id = ? ORDER BY timestamp ASC, id ASC",
        user_param,
    )
    testimony_rows = _query_if_table_exists(
        claim_support_db_path,
        "claim_testimony",
        "SELECT * FROM claim_testimony WHERE user_id = ? ORDER BY timestamp ASC, id ASC",
        user_param,
    )
    snapshot_rows = _query_if_table_exists(
        claim_support_db_path,
        "claim_support_snapshot",
        "SELECT * FROM claim_support_snapshot WHERE user_id = ? ORDER BY timestamp ASC, id ASC",
        user_param,
    )

    _build_evidence_db_documents(assembler, evidence_rows, db_path=evidence_db_path)
    _build_authority_documents(assembler, authority_rows, db_path=legal_authority_db_path)
    _build_claim_support_documents(
        assembler,
        requirements=requirement_rows,
        links=support_rows,
        testimony=testimony_rows,
        snapshots=snapshot_rows,
        db_path=claim_support_db_path,
    )

    workspace_payload = assembler.to_workspace_payload()
    workspace_payload["metadata"] = {
        **dict(workspace_payload.get("metadata") or {}),
        "legacy_counts": {
            "session_documents": len([item for item in workspace_payload.get("documents") or [] if str((item.get("metadata") or {}).get("collection_id") or "").startswith("legacy_session") or str((item.get("metadata") or {}).get("record_scope") or "").startswith("intake")]),
            "evidence_db_records": len(evidence_rows),
            "legal_authority_records": len(authority_rows),
            "claim_requirement_records": len(requirement_rows),
            "claim_support_records": len(support_rows),
            "claim_testimony_records": len(testimony_rows),
            "claim_support_snapshots": len(snapshot_rows),
        },
        "legacy_sources": {
            "statefile_path": str(statefile) if statefile else "",
            "evidence_db_path": str(Path(evidence_db_path).expanduser().resolve()) if evidence_db_path else "",
            "legal_authority_db_path": str(Path(legal_authority_db_path).expanduser().resolve()) if legal_authority_db_path else "",
            "claim_support_db_path": str(Path(claim_support_db_path).expanduser().resolve()) if claim_support_db_path else "",
        },
    }
    builder = WorkspaceDatasetBuilder(vector_dimension=int(vector_dimension or 16))
    dataset = builder.build_from_workspace(workspace_payload)
    migration_summary = {
        "workspace_id": resolved_user_id,
        "workspace_name": str(workspace_payload.get("workspace_name") or ""),
        "document_count": len(list(workspace_payload.get("documents") or [])),
        "collection_count": len(list(workspace_payload.get("collections") or [])),
        "legacy_sources": dict((workspace_payload.get("metadata") or {}).get("legacy_sources") or {}),
        "legacy_counts": dict((workspace_payload.get("metadata") or {}).get("legacy_counts") or {}),
    }
    return dataset, migration_summary


def migrate_legacy_workspace_data(
    *,
    output_dir: str | Path,
    state: Optional[Mapping[str, Any]] = None,
    statefile_path: Optional[str | Path] = None,
    evidence_db_path: Optional[str | Path] = None,
    legal_authority_db_path: Optional[str | Path] = None,
    claim_support_db_path: Optional[str | Path] = None,
    user_id: Optional[str] = None,
    package_name: Optional[str] = None,
    include_car: bool = True,
    write_dataset_json: bool = True,
    write_single_parquet: bool = True,
    vector_dimension: int = 16,
) -> Dict[str, Any]:
    if state is None:
        if statefile_path is None:
            raise ValueError("Provide either state or statefile_path for migration.")
        resolved_statefile = Path(statefile_path).expanduser().resolve()
        state_payload = _read_json_file(resolved_statefile)
    else:
        state_payload = dict(state)
        resolved_statefile = Path(statefile_path).expanduser().resolve() if statefile_path else None

    dataset, migration_summary = build_workspace_dataset_from_legacy_sources(
        state=state_payload,
        statefile_path=resolved_statefile,
        evidence_db_path=evidence_db_path,
        legal_authority_db_path=legal_authority_db_path,
        claim_support_db_path=claim_support_db_path,
        user_id=user_id,
        vector_dimension=vector_dimension,
    )

    output_root = Path(output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    bundle_name = str(package_name or f"{dataset.workspace_id}_workspace_dataset_bundle")
    dataset_json_path = output_root / f"{_slug(bundle_name)}.workspace_dataset.json"
    single_parquet_path = output_root / f"{_slug(bundle_name)}.workspace_dataset.parquet"

    if write_dataset_json:
        dataset_json_path.write_text(
            json.dumps(_jsonable(dataset.to_dict()), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if write_single_parquet:
        export_workspace_dataset_single_parquet(dataset, single_parquet_path)

    packager = WorkspaceDatasetPackager()
    package_result = packager.package(
        dataset,
        output_root,
        package_name=bundle_name,
        include_car=bool(include_car),
    )
    schema_snapshot = build_workspace_schema_snapshot(package_result=package_result, dataset=dataset)

    return {
        "status": "success",
        "source": "legacy_complaint_workspace_migration",
        "user_id": str(dataset.workspace_id),
        "dataset_id": str(dataset.dataset_id),
        "workspace_name": str(dataset.workspace_name),
        "dataset_json_path": str(dataset_json_path) if write_dataset_json else "",
        "single_parquet_path": str(single_parquet_path) if write_single_parquet else "",
        "bundle_dir": str(package_result.get("bundle_dir") or ""),
        "manifest_json_path": str(package_result.get("manifest_json_path") or ""),
        "manifest_parquet_path": str(package_result.get("manifest_parquet_path") or ""),
        "manifest_car_path": str(package_result.get("manifest_car_path") or ""),
        "migration_summary": migration_summary,
        "workspace_dataset_summary": dataset.summary(),
        "package_summary": dict(package_result.get("summary") or {}),
        "schema_snapshot": schema_snapshot,
    }


def inspect_workspace_data_schema(
    *,
    state: Optional[Mapping[str, Any]] = None,
    statefile_path: Optional[str | Path] = None,
    manifest_path: Optional[str | Path] = None,
    evidence_db_path: Optional[str | Path] = None,
    legal_authority_db_path: Optional[str | Path] = None,
    claim_support_db_path: Optional[str | Path] = None,
    user_id: Optional[str] = None,
    vector_dimension: int = 16,
) -> Dict[str, Any]:
    if manifest_path is not None:
        packager = WorkspaceDatasetPackager()
        package = packager.load_package(manifest_path)
        summary_view = packager.load_summary_view(manifest_path)
        package_result = {
            "summary": summary_view,
            "pieces": list((summary_view.get("package_manifest") or {}).get("pieces") or []),
            "chain_load_order": list((summary_view.get("package_manifest") or {}).get("chain_load_order") or []),
        }
        snapshot = build_workspace_schema_snapshot(package_result=package_result, dataset=package)
        snapshot["source"] = "packaged_workspace_manifest"
        snapshot["manifest_path"] = str(Path(manifest_path).expanduser().resolve())
        return snapshot

    if state is None:
        if statefile_path is None:
            raise ValueError("Provide state, statefile_path, or manifest_path when inspecting workspace data schema.")
        state_payload = _read_json_file(Path(statefile_path).expanduser().resolve())
    else:
        state_payload = dict(state)

    dataset, _ = build_workspace_dataset_from_legacy_sources(
        state=state_payload,
        statefile_path=statefile_path,
        evidence_db_path=evidence_db_path,
        legal_authority_db_path=legal_authority_db_path,
        claim_support_db_path=claim_support_db_path,
        user_id=user_id,
        vector_dimension=vector_dimension,
    )
    with tempfile.TemporaryDirectory(prefix="workspace-schema-preview-") as temp_dir:
        package_result = WorkspaceDatasetPackager().package(
            dataset,
            Path(temp_dir),
            package_name=f"{dataset.workspace_id}_schema_preview",
            include_car=False,
        )
    snapshot = build_workspace_schema_snapshot(package_result=package_result, dataset=dataset)
    snapshot["source"] = "live_workspace_projection"
    return snapshot
