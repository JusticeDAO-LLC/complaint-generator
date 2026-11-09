"""Persistent claim-support coverage hooks for mediator."""

from __future__ import annotations

import json
import re
import hashlib
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from integrations.ipfs_datasets.graphrag import (
    build_ontology,
    validate_ontology,
    build_validate_score_ontology,
    score_support_path_quality,
)
from integrations.ipfs_datasets.graphs import persist_graph_snapshot, query_graph_snapshot
from integrations.ipfs_datasets.logic import (
    build_legal_ir_premise_inventory,
    check_contradictions,
    connect_definition_handoff_proof,
    generate_bound_legal_ir_proof_obligations,
    proof_cache_identity,
    replay_satisfied_element_proof,
    route_bound_legal_ir_proof,
    prove_claim_elements,
    run_hybrid_reasoning,
)
from complaint_analysis.temporal_rule_profiles import (
    enrich_follow_up,
    evaluate_temporal_rule_profile,
    rank_follow_ups,
)
from claim_support_review import _merge_intake_summary_handoff_metadata
from mediator.evidence_hooks import PrivateDerivedIndexMixin
from ._claim_support_reasoning import (
    extract_logic_contradiction_count as _extract_logic_contradiction_count_payload,
    extract_logic_proof_counts as _extract_logic_proof_counts_payload,
    extract_ontology_validation_signal as _extract_ontology_validation_signal_payload,
    summarize_adapter_result as _summarize_adapter_result_payload,
    summarize_claim_reasoning_diagnostics as _summarize_claim_reasoning_diagnostics_payload,
    summarize_claim_validation_decisions as _summarize_claim_validation_decisions_payload,
)
from ._claim_support_trace import (
    ARTIFACT_FAMILY_CORPUS_FAMILY,
    CONTENT_ORIGIN_ARTIFACT_FAMILY,
    build_graph_trace as _build_graph_trace_payload,
    build_support_packet_lineage_summary as _build_support_packet_lineage_summary_payload,
    build_support_trace as _build_support_trace_payload,
    extract_record_parse_summary as _extract_record_parse_summary_payload,
    normalize_graph_summary as _normalize_graph_summary_payload,
    resolve_artifact_identity as _resolve_artifact_identity_payload,
    summarize_graph_traces as _summarize_graph_traces_payload,
)
from .claim_support_diagnostics import (
    _build_temporal_proof_bundle,
    _get_temporal_reasoning_context,
    _run_element_reasoning_diagnostics,
)

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


@dataclass(frozen=True)
class ClaimSupportPathSummaryDTO:
    """Stable review DTO for trace, packet, and optional graph path summaries."""

    support_trace_summary: Dict[str, Any]
    support_packet_summary: Dict[str, Any]
    graph_trace_summary: Optional[Dict[str, Any]] = None

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'support_trace_summary': dict(self.support_trace_summary),
            'support_packet_summary': dict(self.support_packet_summary),
        }
        if self.graph_trace_summary is not None:
            payload['graph_trace_summary'] = dict(self.graph_trace_summary)
        return payload


_ENRICHMENT_QUEUE_DDL = """
    CREATE TABLE IF NOT EXISTS claim_enrichment_queue (
        id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
        user_id VARCHAR NOT NULL,
        claim_type VARCHAR,
        enrichment_type VARCHAR NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'pending',
        priority INTEGER DEFAULT 0,
        metadata JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""


class ClaimSupportHook(PrivateDerivedIndexMixin):
    """Track which evidence and authorities support each claim type."""

    _CONTENT_ORIGIN_ARTIFACT_FAMILY = CONTENT_ORIGIN_ARTIFACT_FAMILY
    _ARTIFACT_FAMILY_CORPUS_FAMILY = ARTIFACT_FAMILY_CORPUS_FAMILY

    def __init__(self, mediator, db_path: Optional[str] = None):
        self.mediator = mediator
        self.db_path = db_path or self._get_default_db_path()
        self._enrichment_queue_memory_conn: Optional[Any] = None
        self._memory_requirements: Dict[str, List[Dict[str, Any]]] = {}
        self._memory_support_links: List[Dict[str, Any]] = []
        self._check_duckdb_availability()
        if DUCKDB_AVAILABLE:
            self._prepare_duckdb_path()
            self._initialize_schema()

    def _get_default_db_path(self) -> str:
        state_dir = Path(__file__).parent.parent / 'statefiles'
        if not state_dir.exists():
            state_dir = Path('.')
        return str(state_dir / 'claim_support.duckdb')

    def _with_intake_summary_handoff(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized_payload = dict(payload or {})
        handoff_metadata = _merge_intake_summary_handoff_metadata({}, self.mediator)
        if handoff_metadata:
            normalized_payload.update(handoff_metadata)
        return normalized_payload

    def _resolve_artifact_identity(
        self,
        *,
        content_origin: str = '',
        artifact_family: str = '',
        corpus_family: str = '',
    ) -> Dict[str, str]:
        return _resolve_artifact_identity_payload(
            content_origin=content_origin,
            artifact_family=artifact_family,
            corpus_family=corpus_family,
            content_origin_artifact_family=self._CONTENT_ORIGIN_ARTIFACT_FAMILY,
            artifact_family_corpus_family=self._ARTIFACT_FAMILY_CORPUS_FAMILY,
        )

    def _prepare_duckdb_path(self):
        """Prepare the filesystem path used by DuckDB.

        An empty file is not a valid DuckDB database, but callers commonly
        supply a path created by ``NamedTemporaryFile``. Remove that empty
        placeholder so DuckDB can initialize the database itself. Preparation
        remains best-effort because ``_initialize_schema`` owns the connection
        error path, while filesystem failures are logged here for diagnosis.
        """
        try:
            path = Path(self.db_path)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.is_file() and path.stat().st_size == 0:
                path.unlink()
        except OSError as exc:
            self.mediator.log(
                'claim_support_db_path_prepare_error',
                db_path=self.db_path,
                error=str(exc),
                error_type=type(exc).__name__,
            )

    def _check_duckdb_availability(self):
        if not DUCKDB_AVAILABLE:
            self.mediator.log(
                'claim_support_warning',
                message='DuckDB not available - claim support links will not be persisted',
            )

    def _initialize_schema(self):
        try:
            conn = duckdb.connect(self.db_path)
            conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS claim_support_id_seq START 1
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_requirements (
                    user_id VARCHAR,
                    complaint_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    element_id VARCHAR NOT NULL,
                    element_index INTEGER,
                    element_text TEXT NOT NULL,
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_support (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    user_id VARCHAR,
                    complaint_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    claim_element_id VARCHAR,
                    claim_element_text TEXT,
                    support_kind VARCHAR NOT NULL,
                    support_ref VARCHAR NOT NULL,
                    support_label TEXT,
                    source_table VARCHAR,
                    support_strength FLOAT DEFAULT 0.5,
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_follow_up_execution (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    user_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    claim_element_id VARCHAR,
                    claim_element_text TEXT,
                    support_kind VARCHAR NOT NULL,
                    query_text TEXT NOT NULL,
                    query_hash VARCHAR NOT NULL,
                    status VARCHAR DEFAULT 'executed',
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_support_snapshot (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    user_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    snapshot_kind VARCHAR NOT NULL,
                    required_support_kinds JSON,
                    payload JSON,
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_testimony (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    testimony_id VARCHAR NOT NULL,
                    user_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    claim_element_id VARCHAR,
                    claim_element_text TEXT,
                    raw_narrative TEXT,
                    event_date VARCHAR,
                    actor_name TEXT,
                    act_text TEXT,
                    target_text TEXT,
                    harm_text TEXT,
                    firsthand_status VARCHAR,
                    source_confidence FLOAT,
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_support_user_claim
                ON claim_support(user_id, claim_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_requirements_user_claim
                ON claim_requirements(user_id, claim_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_support_ref
                ON claim_support(support_ref)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_follow_up_lookup
                ON claim_follow_up_execution(user_id, claim_type, support_kind, query_hash)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_support_snapshot_lookup
                ON claim_support_snapshot(user_id, claim_type, snapshot_kind)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_testimony_user_claim
                ON claim_testimony(user_id, claim_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_testimony_element_lookup
                ON claim_testimony(user_id, claim_type, claim_element_id)
            """)
            conn.execute("ALTER TABLE claim_support ADD COLUMN IF NOT EXISTS claim_element_id VARCHAR")
            conn.execute("ALTER TABLE claim_support ADD COLUMN IF NOT EXISTS claim_element_text TEXT")
            # M2: durable fact registry
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_facts (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    fact_id VARCHAR NOT NULL,
                    user_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    claim_element_id VARCHAR,
                    claim_element_text TEXT,
                    proposition_text TEXT NOT NULL,
                    source_artifact_id VARCHAR,
                    source_authority_id VARCHAR,
                    source_testimony_id VARCHAR,
                    chunk_ref VARCHAR,
                    span_ref VARCHAR,
                    confidence FLOAT DEFAULT 0.0,
                    validation_state VARCHAR DEFAULT 'unvalidated',
                    uncertainty_flag BOOLEAN DEFAULT FALSE,
                    contradiction_flag BOOLEAN DEFAULT FALSE,
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_claim_facts_fact_id
                ON claim_facts(fact_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_facts_user_element
                ON claim_facts(user_id, claim_type, claim_element_id)
            """)
            # M2: fact link records
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_fact_links (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    link_id VARCHAR NOT NULL,
                    fact_id VARCHAR NOT NULL,
                    link_kind VARCHAR NOT NULL,
                    target_id VARCHAR NOT NULL,
                    target_type VARCHAR,
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_claim_fact_links_link_id
                ON claim_fact_links(link_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_fact_links_fact_id
                ON claim_fact_links(fact_id)
            """)
            # M2: stable support-path records
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_support_paths (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    proof_path_id VARCHAR NOT NULL,
                    user_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    claim_element_id VARCHAR,
                    fact_ids JSON,
                    path_kind VARCHAR DEFAULT 'support',
                    metadata JSON,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_claim_support_paths_proof_path_id
                ON claim_support_paths(proof_path_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_support_paths_user_element
                ON claim_support_paths(user_id, claim_type, claim_element_id)
            """)
            # M4: claim-element-scoped retrieval sessions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_retrieval_sessions (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    session_id VARCHAR NOT NULL,
                    user_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    claim_element_id VARCHAR,
                    claim_element_text TEXT,
                    query_text TEXT NOT NULL,
                    query_hash VARCHAR NOT NULL,
                    retrieval_plane VARCHAR DEFAULT 'unified',
                    result_count INTEGER DEFAULT 0,
                    status VARCHAR DEFAULT 'pending',
                    metadata JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_claim_retrieval_sessions_session_id
                ON claim_retrieval_sessions(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_retrieval_sessions_user_element
                ON claim_retrieval_sessions(user_id, claim_type, claim_element_id)
            """)
            # M4: retrieval result records (one row per ranked chunk/document)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_retrieval_results (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    session_id VARCHAR NOT NULL,
                    user_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
                    claim_element_id VARCHAR,
                    rank INTEGER DEFAULT 0,
                    source_kind VARCHAR NOT NULL,
                    source_ref VARCHAR NOT NULL,
                    source_label TEXT,
                    chunk_text TEXT,
                    retrieval_score FLOAT DEFAULT 0.0,
                    confidence FLOAT DEFAULT 0.0,
                    explanation TEXT,
                    duplicate_cluster_id VARCHAR,
                    is_duplicate_representative BOOLEAN DEFAULT FALSE,
                    metadata JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_retrieval_results_session
                ON claim_retrieval_results(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_retrieval_results_user_element
                ON claim_retrieval_results(user_id, claim_type, claim_element_id)
            """)
            conn.close()
            self.mediator.log('claim_support_schema_initialized', db_path=self.db_path)
        except Exception as exc:
            self.mediator.log('claim_support_schema_error', error=str(exc))

    def _make_element_id(self, claim_type: str, element_index: int) -> str:
        normalized_claim = ''.join(ch.lower() if ch.isalnum() else '_' for ch in claim_type).strip('_')
        return f'{normalized_claim}:{element_index}'

    def _make_testimony_id(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: str = '',
        raw_narrative: str = '',
        created_at: str = '',
    ) -> str:
        normalized_claim = ''.join(ch.lower() if ch.isalnum() else '_' for ch in claim_type).strip('_') or 'claim'
        digest = hashlib.sha1(
            f'{user_id}|{claim_type}|{claim_element_id}|{raw_narrative}|{created_at}'.encode('utf-8')
        ).hexdigest()[:12]
        return f'testimony:{normalized_claim}:{digest}'

    def _make_fact_id(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: str = '',
        proposition_text: str = '',
        source_artifact_id: str = '',
        source_authority_id: str = '',
        source_testimony_id: str = '',
        chunk_ref: str = '',
    ) -> str:
        normalized_claim = ''.join(ch.lower() if ch.isalnum() else '_' for ch in claim_type).strip('_') or 'claim'
        digest = hashlib.sha256(
            f'{user_id}|{claim_type}|{claim_element_id}|{proposition_text}|{source_artifact_id}|{source_authority_id}|{source_testimony_id}|{chunk_ref}'.encode('utf-8')
        ).hexdigest()[:16]
        return f'fact:{normalized_claim}:{digest}'

    def _make_fact_link_id(self, fact_id: str, link_kind: str, target_id: str) -> str:
        digest = hashlib.sha256(
            f'{fact_id}|{link_kind}|{target_id}'.encode('utf-8')
        ).hexdigest()[:16]
        return f'fact_link:{digest}'

    def _make_proof_path_id(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: str = '',
        fact_ids: List[str],
        path_kind: str = 'support',
    ) -> str:
        normalized_claim = ''.join(ch.lower() if ch.isalnum() else '_' for ch in claim_type).strip('_') or 'claim'
        sorted_facts = '|'.join(sorted(fact_ids))
        digest = hashlib.sha256(
            f'{user_id}|{claim_type}|{claim_element_id}|{sorted_facts}|{path_kind}'.encode('utf-8')
        ).hexdigest()[:16]
        return f'path:{normalized_claim}:{digest}'

    def _make_trace_path_id(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: str = '',
        fact_ids: List[str],
        support_refs: List[str],
        path_kind: str = 'support',
    ) -> str:
        if fact_ids:
            return self._make_proof_path_id(
                user_id=user_id,
                claim_type=claim_type,
                claim_element_id=claim_element_id,
                fact_ids=fact_ids,
                path_kind=path_kind,
            )
        normalized_claim = ''.join(ch.lower() if ch.isalnum() else '_' for ch in claim_type).strip('_') or 'claim'
        sorted_facts = '|'.join(sorted(fid for fid in fact_ids if fid))
        sorted_refs = '|'.join(sorted(ref for ref in support_refs if ref))
        digest = hashlib.sha256(
            f'{user_id}|{claim_type}|{claim_element_id}|{sorted_facts}|{sorted_refs}|{path_kind}'.encode('utf-8')
        ).hexdigest()[:16]
        return f'path:{normalized_claim}:{digest}'

    def _summarize_testimony_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized_records = [record for record in (records or []) if isinstance(record, dict)]
        firsthand_status_counts: Dict[str, int] = {}
        confidence_bucket_counts: Dict[str, int] = {}
        linked_element_ids = set()
        actor_names = set()
        dated_records = 0

        for record in normalized_records:
            firsthand_status = str(record.get('firsthand_status') or 'unknown')
            firsthand_status_counts[firsthand_status] = firsthand_status_counts.get(firsthand_status, 0) + 1

            confidence_value = record.get('source_confidence')
            if confidence_value is None:
                bucket = 'unknown'
            else:
                try:
                    numeric_confidence = float(confidence_value)
                except (TypeError, ValueError):
                    bucket = 'unknown'
                else:
                    if numeric_confidence >= 0.75:
                        bucket = 'high'
                    elif numeric_confidence >= 0.4:
                        bucket = 'medium'
                    else:
                        bucket = 'low'
            confidence_bucket_counts[bucket] = confidence_bucket_counts.get(bucket, 0) + 1

            claim_element_id = str(record.get('claim_element_id') or '')
            if claim_element_id:
                linked_element_ids.add(claim_element_id)
            actor_name = str(record.get('actor') or '').strip()
            if actor_name:
                actor_names.add(actor_name)
            if str(record.get('event_date') or '').strip():
                dated_records += 1

        latest_timestamp = ''
        if normalized_records:
            latest_timestamp = str(normalized_records[0].get('timestamp') or '')

        return {
            'record_count': len(normalized_records),
            'linked_element_count': len(linked_element_ids),
            'firsthand_status_counts': firsthand_status_counts,
            'confidence_bucket_counts': confidence_bucket_counts,
            'actor_count': len(actor_names),
            'dated_record_count': dated_records,
            'latest_timestamp': latest_timestamp,
        }

    def _testimony_quality_summary(self, source_confidence: Any) -> Dict[str, Any]:
        if source_confidence is None:
            return {
                'quality_tier': 'unknown',
                'quality_score': 0.0,
                'support_strength': 0.5,
            }
        try:
            numeric_confidence = float(source_confidence)
        except (TypeError, ValueError):
            return {
                'quality_tier': 'unknown',
                'quality_score': 0.0,
                'support_strength': 0.5,
            }

        clamped_confidence = max(0.0, min(numeric_confidence, 1.0))
        if clamped_confidence >= 0.75:
            quality_tier = 'high'
        elif clamped_confidence >= 0.4:
            quality_tier = 'medium'
        else:
            quality_tier = 'low'
        return {
            'quality_tier': quality_tier,
            'quality_score': round(clamped_confidence * 100.0, 2),
            'support_strength': clamped_confidence,
        }

    def _build_testimony_fact_text(self, record: Dict[str, Any]) -> str:
        raw_narrative = str(record.get('raw_narrative') or '').strip()
        if raw_narrative:
            return raw_narrative

        actor = str(record.get('actor') or '').strip()
        act = str(record.get('act') or '').strip()
        target = str(record.get('target') or '').strip()
        harm = str(record.get('harm') or '').strip()
        event_date = str(record.get('event_date') or '').strip()
        claim_element_text = str(record.get('claim_element_text') or '').strip()

        clauses: List[str] = []
        actor_and_act = ' '.join(part for part in [actor, act] if part).strip()
        if actor_and_act:
            clauses.append(actor_and_act)
        if target:
            clauses.append(f'targeting {target}')
        if harm:
            clauses.append(f'causing {harm}')
        if event_date:
            clauses.append(f'on {event_date}')

        text = '; '.join(clauses).strip()
        if not text:
            text = claim_element_text or 'Testimony provided.'
        if text and not text.endswith('.'):
            text = f'{text}.'
        return text

    def _build_testimony_support_label(self, record: Dict[str, Any]) -> str:
        claim_element_text = str(record.get('claim_element_text') or '').strip()
        actor = str(record.get('actor') or '').strip()
        raw_narrative = str(record.get('raw_narrative') or '').strip()
        if claim_element_text:
            return f'Testimony for {claim_element_text}'
        if actor:
            return f'Testimony from {actor}'
        if raw_narrative:
            return raw_narrative[:80]
        return 'Claim testimony'

    def _build_testimony_support_link(self, record: Dict[str, Any]) -> Dict[str, Any]:
        quality_summary = self._testimony_quality_summary(record.get('source_confidence'))
        testimony_id = str(record.get('testimony_id') or '')
        testimony_record_id = record.get('record_id')
        testimony_fact_text = self._build_testimony_fact_text(record)
        parse_lineage = {
            'record_scope': 'claim_testimony',
            'source_ref': testimony_id,
            'source': 'claim_testimony',
            'input_format': 'structured_testimony',
            'quality_tier': quality_summary['quality_tier'],
            'quality_score': quality_summary['quality_score'],
            'transform_lineage': {
                'content_origin': 'operator_testimony_intake',
                'artifact_family': 'testimony_statement',
                'corpus_family': 'claim_testimony',
            },
        }
        if str(record.get('event_date') or '').strip():
            parse_lineage['observed_at'] = str(record.get('event_date') or '').strip()

        record_summary = {
            'id': testimony_record_id,
            'testimony_id': testimony_id,
            'event_date': str(record.get('event_date') or ''),
            'actor': str(record.get('actor') or ''),
            'act': str(record.get('act') or ''),
            'target': str(record.get('target') or ''),
            'harm': str(record.get('harm') or ''),
            'firsthand_status': str(record.get('firsthand_status') or 'unknown'),
            'timestamp': str(record.get('timestamp') or ''),
            'parse_summary': {
                'source': 'claim_testimony',
                'input_format': 'structured_testimony',
                'quality_tier': quality_summary['quality_tier'],
                'quality_score': quality_summary['quality_score'],
                'artifact_family': 'testimony_statement',
                'corpus_family': 'claim_testimony',
                'content_origin': 'operator_testimony_intake',
                'observed_at': str(record.get('event_date') or ''),
            },
        }
        graph_summary = self._normalize_graph_summary(default_status='not_available')
        graph_trace = self._build_graph_trace(
            source_table='claim_testimony',
            support_ref=testimony_id,
            record_id=testimony_record_id,
            graph_summary=graph_summary,
        )
        fact = {
            'fact_id': f'{testimony_id}:fact',
            'text': testimony_fact_text,
            'confidence': quality_summary['support_strength'],
            'source_record_id': testimony_record_id,
            'source_ref': testimony_id,
            'source_family': 'claim_testimony',
            'record_scope': 'claim_testimony',
            'artifact_family': 'testimony_statement',
            'corpus_family': 'claim_testimony',
            'content_origin': 'operator_testimony_intake',
            'parse_source': 'claim_testimony',
            'input_format': 'structured_testimony',
            'quality_tier': quality_summary['quality_tier'],
            'quality_score': quality_summary['quality_score'],
            'metadata': {
                'parse_lineage': parse_lineage,
            },
        }
        return {
            'claim_type': str(record.get('claim_type') or ''),
            'claim_element_id': str(record.get('claim_element_id') or ''),
            'claim_element_text': str(record.get('claim_element_text') or ''),
            'support_kind': 'testimony',
            'support_ref': testimony_id,
            'support_label': self._build_testimony_support_label(record),
            'source_table': 'claim_testimony',
            'support_strength': quality_summary['support_strength'],
            'metadata': dict(record.get('metadata') or {}),
            'timestamp': record.get('timestamp'),
            'testimony_record_id': testimony_record_id,
            'fact_count': 1,
            'facts': [fact],
            'record_summary': record_summary,
            'graph_summary': graph_summary,
            'graph_trace': graph_trace,
        }

    def _get_testimony_support_links(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        testimony_records = self.get_claim_testimony_records(
            user_id,
            claim_type,
            limit=10000,
        )
        claim_entries = testimony_records.get('claims', {}) if isinstance(testimony_records, dict) else {}
        links: List[Dict[str, Any]] = []
        for records in claim_entries.values():
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                links.append(self._build_testimony_support_link(record))
        return links

    def _get_enriched_claim_support_links(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        links = [self._enrich_support_link(link) for link in self.get_support_links(user_id, claim_type)]
        links.extend(self._get_testimony_support_links(user_id, claim_type))
        return links

    def _tokenize_text(self, value: Optional[str]) -> List[str]:
        if not value:
            return []
        return [token for token in re.findall(r'[a-z0-9]+', value.lower()) if len(token) > 2]

    def _extract_match_text(self, support_label: Optional[str], metadata: Optional[Dict[str, Any]]) -> str:
        metadata = metadata or {}
        parts: List[str] = []
        for field in ('title', 'description', 'summary', 'content_excerpt', 'claim_element', 'claim_element_text', 'source_url'):
            value = metadata.get(field)
            if isinstance(value, str):
                parts.append(value)
        keywords = metadata.get('keywords')
        if isinstance(keywords, list):
            parts.extend(str(item) for item in keywords if item)
        if support_label:
            parts.append(support_label)
        return ' '.join(parts)

    def _normalize_graph_summary(
        self,
        *,
        graph_payload: Optional[Dict[str, Any]] = None,
        default_status: str = '',
        default_entity_count: int = 0,
        default_relationship_count: int = 0,
    ) -> Dict[str, Any]:
        return _normalize_graph_summary_payload(
            graph_payload=graph_payload,
            default_status=default_status,
            default_entity_count=default_entity_count,
            default_relationship_count=default_relationship_count,
        )

    def _build_graph_trace(
        self,
        *,
        source_table: Optional[str],
        support_ref: Optional[str],
        record_id: Optional[int],
        graph_summary: Dict[str, Any],
        graph_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return _build_graph_trace_payload(
            source_table=source_table,
            support_ref=support_ref,
            record_id=record_id,
            graph_summary=graph_summary,
            graph_metadata=graph_metadata,
        )

    def _summarize_graph_traces(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return _summarize_graph_traces_payload(items)

    def _summarize_authority_treatment_signals(self, links: List[Dict[str, Any]]) -> Dict[str, Any]:
        authority_links = [
            link for link in (links or [])
            if isinstance(link, dict) and link.get('support_kind') == 'authority'
        ]
        adverse_types = {'adverse', 'limits', 'distinguishes', 'questioned', 'superseded'}
        uncertain_types = {'good_law_unconfirmed', 'procedural_only'}

        by_type: Dict[str, int] = {}
        supportive_count = 0
        adverse_count = 0
        uncertain_count = 0
        treated_link_count = 0
        max_confidence = 0.0

        for link in authority_links:
            summary = (
                (link.get('record_summary') or {}).get('treatment_summary', {})
                if isinstance(link.get('record_summary'), dict)
                else {}
            )
            summary = summary if isinstance(summary, dict) else {}
            by_type_summary = summary.get('by_type', {}) if isinstance(summary.get('by_type'), dict) else {}
            treatment_types = set()
            for treatment_type, count in by_type_summary.items():
                normalized_type = str(treatment_type or '')
                if not normalized_type:
                    continue
                treatment_types.add(normalized_type)
                by_type[normalized_type] = by_type.get(normalized_type, 0) + int(count or 0)

            record_count = int(summary.get('record_count', 0) or 0)
            if record_count > 0:
                treated_link_count += 1
            max_confidence = max(max_confidence, float(summary.get('max_confidence', 0.0) or 0.0))

            if treatment_types & adverse_types:
                adverse_count += 1
            elif treatment_types & uncertain_types:
                uncertain_count += 1
            else:
                supportive_count += 1

        return {
            'authority_link_count': len(authority_links),
            'treated_authority_link_count': treated_link_count,
            'supportive_authority_link_count': supportive_count,
            'adverse_authority_link_count': adverse_count,
            'uncertain_authority_link_count': uncertain_count,
            'treatment_type_counts': by_type,
            'max_treatment_confidence': max_confidence,
        }

    def _summarize_authority_rule_candidates(self, links: List[Dict[str, Any]]) -> Dict[str, Any]:
        authority_links = [
            link for link in (links or [])
            if isinstance(link, dict) and link.get('support_kind') == 'authority'
        ]
        fact_support_by_element = self._collect_fact_support_text_by_element(links)

        rule_type_counts: Dict[str, int] = {}
        deontic_operator_counts: Dict[str, int] = {}
        operator_family_counts: Dict[str, int] = {}
        grounding_status_counts: Dict[str, int] = {}
        authority_links_with_rule_candidates = 0
        total_rule_candidate_count = 0
        matched_claim_element_rule_count = 0
        fact_satisfied_rule_count = 0
        fact_unsatisfied_rule_count = 0
        fact_satisfaction_status_counts: Dict[str, int] = {}
        adverse_treatment_count = 0
        max_extraction_confidence = 0.0

        for link in authority_links:
            rule_candidates = link.get('rule_candidates', [])
            if isinstance(rule_candidates, list) and rule_candidates:
                authority_links_with_rule_candidates += 1
                link_element_id = str(link.get('claim_element_id') or '')
                link_element_text = str(link.get('claim_element_text') or '')
                for candidate in rule_candidates:
                    if not isinstance(candidate, dict):
                        continue
                    total_rule_candidate_count += 1
                    rule_type = str(candidate.get('rule_type') or '')
                    if rule_type:
                        rule_type_counts[rule_type] = rule_type_counts.get(rule_type, 0) + 1
                    grounded_rule = candidate.get('grounded_rule', {})
                    if not isinstance(grounded_rule, dict):
                        metadata = candidate.get('metadata', {}) if isinstance(candidate.get('metadata'), dict) else {}
                        grounded_rule = metadata.get('grounded_rule', {}) if isinstance(metadata.get('grounded_rule'), dict) else {}
                    deontic_operator = str(grounded_rule.get('deontic_operator') or '')
                    if deontic_operator:
                        deontic_operator_counts[deontic_operator] = deontic_operator_counts.get(deontic_operator, 0) + 1
                    operator_family = str(grounded_rule.get('operator_family') or '')
                    if operator_family:
                        operator_family_counts[operator_family] = operator_family_counts.get(operator_family, 0) + 1
                    grounding_status = str(grounded_rule.get('grounding_status') or '')
                    if grounding_status:
                        grounding_status_counts[grounding_status] = grounding_status_counts.get(grounding_status, 0) + 1
                    adverse_treatment_count += int(grounded_rule.get('adverse_treatment_count', 0) or 0)
                    candidate_element_id = str(candidate.get('claim_element_id') or '')
                    candidate_element_text = str(candidate.get('claim_element_text') or '')
                    if (
                        candidate_element_id and candidate_element_id == link_element_id
                    ) or (
                        candidate_element_text and candidate_element_text == link_element_text
                    ):
                        matched_claim_element_rule_count += 1
                        satisfaction_status = self._classify_rule_candidate_fact_satisfaction(
                            candidate,
                            fact_support_by_element.get(candidate_element_id or link_element_id, []),
                            fact_support_by_element.get(candidate_element_text or link_element_text, []),
                        )
                        fact_satisfaction_status_counts[satisfaction_status] = (
                            fact_satisfaction_status_counts.get(satisfaction_status, 0) + 1
                        )
                        if satisfaction_status == 'fact_satisfied':
                            fact_satisfied_rule_count += 1
                        elif satisfaction_status == 'fact_missing':
                            fact_unsatisfied_rule_count += 1
                    max_extraction_confidence = max(
                        max_extraction_confidence,
                        float(candidate.get('extraction_confidence', 0.0) or 0.0),
                    )
                continue

            summary = (
                (link.get('record_summary') or {}).get('rule_candidate_summary', {})
                if isinstance(link.get('record_summary'), dict)
                else {}
            )
            summary = summary if isinstance(summary, dict) else {}
            record_count = int(summary.get('record_count', 0) or 0)
            if record_count <= 0:
                continue
            authority_links_with_rule_candidates += 1
            total_rule_candidate_count += record_count
            matched_claim_element_rule_count += record_count
            by_type = summary.get('by_type', {}) if isinstance(summary.get('by_type'), dict) else {}
            for rule_type, count in by_type.items():
                normalized_type = str(rule_type or '')
                if normalized_type:
                    rule_type_counts[normalized_type] = rule_type_counts.get(normalized_type, 0) + int(count or 0)
            by_deontic = summary.get('by_deontic_operator', {}) if isinstance(summary.get('by_deontic_operator'), dict) else {}
            for deontic_operator, count in by_deontic.items():
                normalized_deontic = str(deontic_operator or '')
                if normalized_deontic:
                    deontic_operator_counts[normalized_deontic] = deontic_operator_counts.get(normalized_deontic, 0) + int(count or 0)
            by_operator_family = summary.get('by_operator_family', {}) if isinstance(summary.get('by_operator_family'), dict) else {}
            for operator_family, count in by_operator_family.items():
                normalized_family = str(operator_family or '')
                if normalized_family:
                    operator_family_counts[normalized_family] = operator_family_counts.get(normalized_family, 0) + int(count or 0)
            by_grounding_status = summary.get('by_grounding_status', {}) if isinstance(summary.get('by_grounding_status'), dict) else {}
            for grounding_status, count in by_grounding_status.items():
                normalized_status = str(grounding_status or '')
                if normalized_status:
                    grounding_status_counts[normalized_status] = grounding_status_counts.get(normalized_status, 0) + int(count or 0)
            adverse_treatment_count += int(summary.get('adverse_treatment_count', 0) or 0)
            max_extraction_confidence = max(
                max_extraction_confidence,
                float(summary.get('max_confidence', 0.0) or 0.0),
            )

        return {
            'authority_link_count': len(authority_links),
            'authority_links_with_rule_candidates': authority_links_with_rule_candidates,
            'total_rule_candidate_count': total_rule_candidate_count,
            'matched_claim_element_rule_count': matched_claim_element_rule_count,
            'fact_satisfied_rule_count': fact_satisfied_rule_count,
            'fact_unsatisfied_rule_count': fact_unsatisfied_rule_count,
            'fact_satisfaction_status_counts': fact_satisfaction_status_counts,
            'rule_type_counts': rule_type_counts,
            'deontic_operator_counts': deontic_operator_counts,
            'operator_family_counts': operator_family_counts,
            'grounding_status_counts': grounding_status_counts,
            'adverse_treatment_count': adverse_treatment_count,
            'max_extraction_confidence': max_extraction_confidence,
        }

    def _collect_fact_support_text_by_element(self, links: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        support_text_by_element: Dict[str, List[str]] = {}
        for link in links or []:
            if not isinstance(link, dict) or link.get('support_kind') == 'authority':
                continue
            texts = [
                str(link.get('support_ref') or ''),
                str(link.get('support_label') or ''),
            ]
            record_summary = link.get('record_summary') if isinstance(link.get('record_summary'), dict) else {}
            texts.extend([
                str(record_summary.get('title') or ''),
                str(record_summary.get('content') or ''),
                str(record_summary.get('parsed_text_preview') or ''),
                str(record_summary.get('source_ref') or ''),
            ])
            combined = ' '.join(text for text in texts if text).strip()
            if not combined:
                continue
            for key in [
                str(link.get('claim_element_id') or '').strip(),
                str(link.get('claim_element_text') or '').strip(),
            ]:
                if key:
                    support_text_by_element.setdefault(key, []).append(combined)
        return support_text_by_element

    def _classify_rule_candidate_fact_satisfaction(
        self,
        candidate: Dict[str, Any],
        support_texts_by_id: List[str],
        support_texts_by_text: List[str],
    ) -> str:
        support_texts = list(support_texts_by_id or []) + list(support_texts_by_text or [])
        if not support_texts:
            return 'fact_missing'
        predicate = str(candidate.get('predicate_template') or candidate.get('claim_element_text') or '').strip()
        if not predicate:
            return 'fact_unknown'
        predicate_terms = {
            term for term in re.findall(r'[a-z0-9]+', predicate.lower())
            if len(term) > 3
        }
        if not predicate_terms:
            return 'fact_unknown'
        support_terms = {
            term
            for text in support_texts
            for term in re.findall(r'[a-z0-9]+', str(text or '').lower())
            if len(term) > 3
        }
        overlap = predicate_terms & support_terms
        return 'fact_satisfied' if overlap else 'fact_missing'

    def _classify_formal_premise_failure(self, element: Dict[str, Any], proof_gap_types: List[str]) -> str:
        treatment_summary = (
            element.get('authority_treatment_summary', {})
            if isinstance(element.get('authority_treatment_summary'), dict)
            else {}
        )
        rule_summary = (
            element.get('authority_rule_candidate_summary', {})
            if isinstance(element.get('authority_rule_candidate_summary'), dict)
            else {}
        )
        if int(treatment_summary.get('adverse_authority_link_count', 0) or 0) > 0:
            return 'adverse_authority'
        if int(rule_summary.get('adverse_treatment_count', 0) or 0) > 0:
            return 'adverse_authority'
        if element.get('validation_status') == 'contradicted':
            return 'contradictory_facts'
        if 'missing_support_kind:authority' in proof_gap_types:
            return 'missing_rules'
        if int(rule_summary.get('matched_claim_element_rule_count', 0) or 0) <= 0 and element.get('validation_status') == 'missing':
            return 'missing_rules'
        if element.get('validation_status') == 'missing':
            return 'missing_facts'
        if 'logic_unprovable' in proof_gap_types:
            return 'unprovable_rules_or_facts'
        return ''

    def _recommended_support_gap_action(self, element: Dict[str, Any]) -> str:
        missing_support_kinds = list(element.get('missing_support_kinds', []) or [])
        if not element.get('total_links', 0):
            return 'collect_initial_support'

        authority_treatment_summary = (
            element.get('authority_treatment_summary', {})
            if isinstance(element.get('authority_treatment_summary'), dict)
            else {}
        )
        if int(authority_treatment_summary.get('adverse_authority_link_count', 0) or 0) > 0:
            return 'review_adverse_authority'

        authority_rule_candidate_summary = (
            element.get('authority_rule_candidate_summary', {})
            if isinstance(element.get('authority_rule_candidate_summary'), dict)
            else {}
        )
        if (
            missing_support_kinds == ['evidence']
            and int(element.get('support_by_kind', {}).get('authority', 0) or 0) > 0
            and int(authority_rule_candidate_summary.get('matched_claim_element_rule_count', 0) or 0) > 0
        ):
            return 'collect_fact_support'

        return 'collect_missing_support_kind'

    def _build_support_trace(
        self,
        *,
        link: Dict[str, Any],
        fact: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return _build_support_trace_payload(link=link, fact=fact)

    def _extract_record_parse_summary(self, record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return _extract_record_parse_summary_payload(
            record,
            artifact_identity_resolver=self._resolve_artifact_identity,
        )

    def _normalize_support_fact(self, fact: Dict[str, Any], link: Dict[str, Any]) -> Dict[str, Any]:
        payload = fact if isinstance(fact, dict) else {}
        metadata = payload.get('metadata', {}) if isinstance(payload.get('metadata'), dict) else {}
        provenance = payload.get('provenance', {}) if isinstance(payload.get('provenance'), dict) else {}
        provenance_metadata = provenance.get('metadata', {}) if isinstance(provenance.get('metadata'), dict) else {}
        parse_lineage = metadata.get('parse_lineage', {}) if isinstance(metadata.get('parse_lineage'), dict) else {}
        transform_lineage = parse_lineage.get('transform_lineage', {}) if isinstance(parse_lineage.get('transform_lineage'), dict) else {}
        parse_quality = parse_lineage.get('parse_quality', {}) if isinstance(parse_lineage.get('parse_quality'), dict) else {}
        source_span = parse_lineage.get('source_span', {}) if isinstance(parse_lineage.get('source_span'), dict) else {}
        record_summary = link.get('record_summary', {}) if isinstance(link.get('record_summary'), dict) else {}
        record_parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
        source_table = str(link.get('source_table') or '')
        source_family = str(payload.get('source_family') or parse_lineage.get('record_scope') or '')
        if not source_family:
            source_family = 'legal_authority' if source_table == 'legal_authorities' else source_table or str(link.get('support_kind') or '')
        source_record_id = payload.get('source_record_id')
        if source_record_id is None:
            if source_family == 'legal_authority':
                source_record_id = link.get('authority_record_id')
            elif source_family == 'claim_testimony':
                source_record_id = link.get('testimony_record_id')
            else:
                source_record_id = link.get('evidence_record_id')

        content_origin = str(
            payload.get('content_origin')
            or transform_lineage.get('content_origin')
            or parse_lineage.get('content_origin')
            or record_parse_summary.get('content_origin')
            or provenance_metadata.get('content_origin')
            or ''
        )
        artifact_identity = self._resolve_artifact_identity(
            content_origin=content_origin,
            artifact_family=str(
                payload.get('artifact_family')
                or transform_lineage.get('artifact_family')
                or parse_lineage.get('artifact_family')
                or record_parse_summary.get('artifact_family')
                or provenance_metadata.get('artifact_family')
                or ''
            ),
            corpus_family=str(
                payload.get('corpus_family')
                or transform_lineage.get('corpus_family')
                or parse_lineage.get('corpus_family')
                or record_parse_summary.get('corpus_family')
                or provenance_metadata.get('corpus_family')
                or ''
            ),
        )

        return {
            **payload,
            'claim_type': link.get('claim_type'),
            'claim_element_id': link.get('claim_element_id'),
            'claim_element_text': link.get('claim_element_text'),
            'support_kind': link.get('support_kind'),
            'support_ref': link.get('support_ref'),
            'support_label': link.get('support_label'),
            'source_table': source_table,
            'source_family': source_family,
            'source_record_id': source_record_id,
            'source_ref': str(
                payload.get('source_ref')
                or parse_lineage.get('source_ref')
                or payload.get('source_artifact_id')
                or payload.get('source_authority_id')
                or link.get('support_ref')
                or ''
            ),
            'record_scope': str(payload.get('record_scope') or parse_lineage.get('record_scope') or source_family),
            'artifact_family': artifact_identity['artifact_family'],
            'corpus_family': artifact_identity['corpus_family'],
            'content_origin': content_origin,
            'parse_source': str(payload.get('parse_source') or parse_lineage.get('source') or record_parse_summary.get('source') or ''),
            'input_format': str(payload.get('input_format') or parse_lineage.get('input_format') or record_parse_summary.get('input_format') or ''),
            'quality_tier': str(payload.get('quality_tier') or parse_lineage.get('quality_tier') or record_parse_summary.get('quality_tier') or ''),
            'quality_score': float(payload.get('quality_score') or parse_lineage.get('quality_score') or record_parse_summary.get('quality_score') or parse_quality.get('quality_score') or 0.0),
            'page_count': int(payload.get('page_count') or parse_lineage.get('page_count') or record_parse_summary.get('page_count') or source_span.get('page_count') or 0),
            'chunk_id': str(payload.get('chunk_id') or metadata.get('chunk_id') or ''),
            'chunk_index': int(payload.get('chunk_index') or metadata.get('chunk_index') or 0),
            'source_passage': dict(payload.get('source_passage') or metadata.get('source_passage') or {}),
            'evidence_record_id': link.get('evidence_record_id'),
            'authority_record_id': link.get('authority_record_id'),
            'testimony_record_id': link.get('testimony_record_id'),
            'graph_summary': link.get('graph_summary', {}),
            'graph_trace': link.get('graph_trace', {}),
            'record_summary': record_summary,
        }

    def _build_support_packet_lineage_summary(
        self,
        *,
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        summary = _build_support_packet_lineage_summary_payload(trace=trace)
        parse_lineage = trace.get('parse_lineage', {}) if isinstance(trace.get('parse_lineage'), dict) else {}
        record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
        record_parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
        summary.update({
            'source_url': str(parse_lineage.get('source_url') or record_parse_summary.get('source_url') or record_summary.get('source_url') or ''),
            'source_domain': str(parse_lineage.get('source_domain') or record_parse_summary.get('source_domain') or record_summary.get('source_domain') or ''),
            'content_hash': str(parse_lineage.get('content_hash') or record_parse_summary.get('content_hash') or record_summary.get('content_hash') or ''),
        })
        return summary

    def _build_support_packet(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
        lineage_summary = self._build_support_packet_lineage_summary(trace=trace)

        # --- evidence sub-object ---
        parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
        evidence = {
            'parsed_text_length': int(record_summary.get('text_length') or parse_summary.get('text_length') or 0),
            'extraction_method': str(record_summary.get('extraction_method') or parse_summary.get('extraction_method') or lineage_summary.get('artifact_family') or ''),
            'parse_quality_tier': str(parse_summary.get('quality_tier') or record_summary.get('quality_tier') or ''),
            'parse_quality_score': float(parse_summary.get('quality_score') or record_summary.get('quality_score') or 0.0),
            'chunk_count': int(parse_summary.get('chunk_count') or record_summary.get('chunk_count') or 0),
            'source_url': str(record_summary.get('source_url') or lineage_summary.get('source_url') or ''),
            'mime_type': str(record_summary.get('mime_type') or parse_summary.get('mime_type') or ''),
        }

        # --- authority sub-object ---
        graph_summary = trace.get('graph_summary', {}) if isinstance(trace.get('graph_summary'), dict) else {}
        authority = {
            'authority_id': str(trace.get('authority_id') or record_summary.get('authority_id') or ''),
            'citation': str(record_summary.get('citation') or record_summary.get('authority_citation') or ''),
            'treatment_signal': str(graph_summary.get('treatment_signal') or record_summary.get('treatment_signal') or ''),
            'rule_candidates': list(graph_summary.get('rule_candidates') or record_summary.get('rule_candidates') or []),
            'jurisdiction': str(record_summary.get('jurisdiction') or ''),
            'authority_type': str(record_summary.get('authority_type') or record_summary.get('source_type') or ''),
        }

        # --- provenance sub-object ---
        provenance = {
            'content_hash': str(lineage_summary.get('content_hash') or record_summary.get('content_hash') or ''),
            'capture_timestamp': str(lineage_summary.get('captured_at') or record_summary.get('captured_at') or ''),
            'archive_url': str(lineage_summary.get('archive_url') or record_summary.get('archive_url') or trace.get('archive_url') or ''),
            'source_domain': str(lineage_summary.get('source_domain') or record_summary.get('source_domain') or ''),
            'capture_source': str(lineage_summary.get('capture_source') or ''),
            'historical_capture': bool(lineage_summary.get('historical_capture', False)),
            'fallback_mode': str(lineage_summary.get('fallback_mode') or ''),
        }

        return {
            'trace_kind': str(trace.get('trace_kind') or 'link'),
            'support_kind': trace.get('support_kind'),
            'support_ref': trace.get('support_ref'),
            'support_label': trace.get('support_label'),
            'source_table': trace.get('source_table'),
            'source_family': trace.get('source_family', ''),
            'source_record_id': trace.get('source_record_id'),
            'source_ref': trace.get('source_ref', ''),
            'record_scope': trace.get('record_scope', ''),
            'record_id': trace.get('record_id'),
            'artifact_family': trace.get('artifact_family', ''),
            'corpus_family': trace.get('corpus_family', ''),
            'content_origin': trace.get('content_origin', ''),
            'fact': {
                'fact_id': trace.get('fact_id', ''),
                'text': trace.get('fact_text', ''),
                'confidence': trace.get('confidence', 0.0),
            },
            'proof_path_id': str(trace.get('proof_path_id') or ''),
            'evidence': evidence,
            'authority': authority,
            'provenance': provenance,
            'record_summary': record_summary,
            'lineage_summary': lineage_summary,
            'source_lineage_ref': trace.get('source_lineage_ref', ''),
            'graph_summary': graph_summary,
            'graph_trace': trace.get('graph_trace', {}),
            'graph_id': trace.get('graph_id', ''),
        }

    def _summarize_support_packets(self, packets: List[Dict[str, Any]]) -> Dict[str, Any]:
        artifact_family_counts: Dict[str, int] = {}
        content_origin_counts: Dict[str, int] = {}
        capture_source_counts: Dict[str, int] = {}
        fallback_mode_counts: Dict[str, int] = {}
        content_source_field_counts: Dict[str, int] = {}
        historical_capture_count = 0
        fact_packet_count = 0
        link_only_packet_count = 0

        for packet in packets or []:
            if not isinstance(packet, dict):
                continue
            if packet.get('trace_kind') == 'fact':
                fact_packet_count += 1
            else:
                link_only_packet_count += 1

            lineage_summary = packet.get('lineage_summary', {}) if isinstance(packet.get('lineage_summary'), dict) else {}
            artifact_family = str(lineage_summary.get('artifact_family') or '')
            content_origin = str(lineage_summary.get('content_origin') or '')
            capture_source = str(lineage_summary.get('capture_source') or '')
            fallback_mode = str(lineage_summary.get('fallback_mode') or '')
            content_source_field = str(lineage_summary.get('content_source_field') or '')
            historical_capture = bool(lineage_summary.get('historical_capture', False))

            if artifact_family:
                artifact_family_counts[artifact_family] = artifact_family_counts.get(artifact_family, 0) + 1
            if content_origin:
                content_origin_counts[content_origin] = content_origin_counts.get(content_origin, 0) + 1
            if capture_source:
                capture_source_counts[capture_source] = capture_source_counts.get(capture_source, 0) + 1
            if fallback_mode:
                fallback_mode_counts[fallback_mode] = fallback_mode_counts.get(fallback_mode, 0) + 1
            if content_source_field:
                content_source_field_counts[content_source_field] = content_source_field_counts.get(content_source_field, 0) + 1
            if historical_capture:
                historical_capture_count += 1

        return {
            'total_packet_count': len([packet for packet in packets if isinstance(packet, dict)]),
            'fact_packet_count': fact_packet_count,
            'link_only_packet_count': link_only_packet_count,
            'historical_capture_count': historical_capture_count,
            'artifact_family_counts': artifact_family_counts,
            'content_origin_counts': content_origin_counts,
            'capture_source_counts': capture_source_counts,
            'fallback_mode_counts': fallback_mode_counts,
            'content_source_field_counts': content_source_field_counts,
        }

    def _build_support_path_summary_dto(
        self,
        *,
        support_traces: List[Dict[str, Any]],
        support_packets: List[Dict[str, Any]],
        graph_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build the shared review DTO for an element or claim support path."""

        graph_trace_summary = (
            self._summarize_graph_traces(graph_items)
            if graph_items is not None
            else None
        )
        return ClaimSupportPathSummaryDTO(
            support_trace_summary=self._summarize_support_traces(support_traces),
            support_packet_summary=self._summarize_support_packets(support_packets),
            graph_trace_summary=graph_trace_summary,
        ).to_payload()

    def _collect_support_traces_from_links(self, links: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        traces: List[Dict[str, Any]] = []
        for link in links or []:
            facts = link.get('facts', []) if isinstance(link.get('facts'), list) else []
            if facts:
                traces.extend(self._build_support_trace(link=link, fact=fact) for fact in facts)
                continue
            traces.append(self._build_support_trace(link=link))
        return traces

    def _summarize_fact_registry(self, facts: List[Dict[str, Any]]) -> Dict[str, Any]:
        source_family_counts: Dict[str, int] = {}
        record_scope_counts: Dict[str, int] = {}
        artifact_family_counts: Dict[str, int] = {}
        corpus_family_counts: Dict[str, int] = {}
        content_origin_counts: Dict[str, int] = {}
        parse_source_counts: Dict[str, int] = {}
        input_format_counts: Dict[str, int] = {}
        quality_tier_counts: Dict[str, int] = {}
        support_kind_counts: Dict[str, int] = {}
        source_table_counts: Dict[str, int] = {}
        unique_fact_ids = set()
        unique_source_refs = set()
        unique_record_keys = set()
        passage_anchored_count = 0

        def _count(target: Dict[str, int], value: Any) -> None:
            text = str(value or '').strip()
            if text:
                target[text] = target.get(text, 0) + 1

        for fact in facts or []:
            if not isinstance(fact, dict):
                continue
            fact_id = str(fact.get('fact_id') or '').strip()
            if fact_id:
                unique_fact_ids.add(fact_id)
            source_ref = str(fact.get('source_ref') or '').strip()
            if source_ref:
                unique_source_refs.add(source_ref)
            source_family = str(fact.get('source_family') or '').strip()
            source_record_id = fact.get('source_record_id')
            if source_family and source_record_id not in (None, ''):
                unique_record_keys.add((source_family, str(source_record_id)))
            source_passage = fact.get('source_passage') if isinstance(fact.get('source_passage'), dict) else {}
            if source_passage.get('chunk_id') or fact.get('chunk_id'):
                passage_anchored_count += 1

            _count(source_family_counts, source_family)
            _count(record_scope_counts, fact.get('record_scope'))
            _count(artifact_family_counts, fact.get('artifact_family'))
            _count(corpus_family_counts, fact.get('corpus_family'))
            _count(content_origin_counts, fact.get('content_origin'))
            _count(parse_source_counts, fact.get('parse_source'))
            _count(input_format_counts, fact.get('input_format'))
            _count(quality_tier_counts, fact.get('quality_tier'))
            _count(support_kind_counts, fact.get('support_kind'))
            _count(source_table_counts, fact.get('source_table'))

        fact_count = len([fact for fact in facts or [] if isinstance(fact, dict)])
        return {
            'fact_count': fact_count,
            'unique_fact_count': len(unique_fact_ids),
            'unique_source_ref_count': len(unique_source_refs),
            'unique_source_record_count': len(unique_record_keys),
            'passage_anchored_count': passage_anchored_count,
            'source_family_counts': source_family_counts,
            'record_scope_counts': record_scope_counts,
            'artifact_family_counts': artifact_family_counts,
            'corpus_family_counts': corpus_family_counts,
            'content_origin_counts': content_origin_counts,
            'parse_source_counts': parse_source_counts,
            'input_format_counts': input_format_counts,
            'quality_tier_counts': quality_tier_counts,
            'support_kind_counts': support_kind_counts,
            'source_table_counts': source_table_counts,
        }

    def _summarize_support_traces(self, traces: List[Dict[str, Any]]) -> Dict[str, Any]:
        support_by_kind: Dict[str, int] = {}
        support_by_source: Dict[str, int] = {}
        parse_source_counts: Dict[str, int] = {}
        parse_input_format_counts: Dict[str, int] = {}
        parse_quality_tier_counts: Dict[str, int] = {}
        artifact_family_counts: Dict[str, int] = {}
        content_origin_counts: Dict[str, int] = {}
        fallback_mode_counts: Dict[str, int] = {}
        graph_status_counts: Dict[str, int] = {}
        unique_fact_ids = set()
        unique_graph_ids = set()
        unique_record_ids = set()
        unique_parsed_records: Dict[str, Dict[str, Any]] = {}
        fact_trace_count = 0
        link_only_trace_count = 0

        for trace in traces or []:
            if not isinstance(trace, dict):
                continue
            support_kind = str(trace.get('support_kind') or 'unknown')
            source_table = str(trace.get('source_table') or 'unknown')
            support_by_kind[support_kind] = support_by_kind.get(support_kind, 0) + 1
            support_by_source[source_table] = support_by_source.get(source_table, 0) + 1

            parse_lineage = trace.get('parse_lineage', {}) if isinstance(trace.get('parse_lineage'), dict) else {}
            record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
            parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
            parse_source = str(parse_lineage.get('source') or parse_summary.get('source') or 'unknown')
            parse_source_counts[parse_source] = parse_source_counts.get(parse_source, 0) + 1
            artifact_family = str(parse_lineage.get('artifact_family') or parse_summary.get('artifact_family') or '')
            if artifact_family:
                artifact_family_counts[artifact_family] = artifact_family_counts.get(artifact_family, 0) + 1
            content_origin = str(parse_lineage.get('content_origin') or parse_summary.get('content_origin') or '')
            if content_origin:
                content_origin_counts[content_origin] = content_origin_counts.get(content_origin, 0) + 1
            fallback_mode = str(parse_lineage.get('fallback_mode') or parse_summary.get('fallback_mode') or '')
            if fallback_mode:
                fallback_mode_counts[fallback_mode] = fallback_mode_counts.get(fallback_mode, 0) + 1

            graph_summary = trace.get('graph_summary', {}) if isinstance(trace.get('graph_summary'), dict) else {}
            graph_status = str(graph_summary.get('status') or 'unknown')
            graph_status_counts[graph_status] = graph_status_counts.get(graph_status, 0) + 1

            fact_id = str(trace.get('fact_id') or '')
            if fact_id:
                fact_trace_count += 1
                unique_fact_ids.add(fact_id)
            else:
                link_only_trace_count += 1

            graph_id = str(trace.get('graph_id') or '')
            if graph_id:
                unique_graph_ids.add(graph_id)

            record_id = trace.get('record_id')
            if record_id not in (None, ''):
                unique_record_ids.add(record_id)

            if parse_summary:
                parse_key = str(record_id or trace.get('support_ref') or trace.get('source_lineage_ref') or '')
                if parse_key:
                    unique_parsed_records[parse_key] = parse_summary

        quality_score_total = 0.0
        for parse_summary in unique_parsed_records.values():
            input_format = str(parse_summary.get('input_format') or '')
            if input_format:
                parse_input_format_counts[input_format] = parse_input_format_counts.get(input_format, 0) + 1

            quality_tier = str(parse_summary.get('quality_tier') or '')
            if quality_tier:
                parse_quality_tier_counts[quality_tier] = parse_quality_tier_counts.get(quality_tier, 0) + 1

            quality_score_total += float(parse_summary.get('quality_score', 0.0) or 0.0)

        parsed_record_count = len(unique_parsed_records)

        return {
            'trace_count': len([trace for trace in traces if isinstance(trace, dict)]),
            'fact_trace_count': fact_trace_count,
            'link_only_trace_count': link_only_trace_count,
            'unique_fact_count': len(unique_fact_ids),
            'unique_graph_id_count': len(unique_graph_ids),
            'unique_record_count': len(unique_record_ids),
            'parsed_record_count': parsed_record_count,
            'support_by_kind': support_by_kind,
            'support_by_source': support_by_source,
            'parse_source_counts': parse_source_counts,
            'parse_input_format_counts': parse_input_format_counts,
            'parse_quality_tier_counts': parse_quality_tier_counts,
            'artifact_family_counts': artifact_family_counts,
            'content_origin_counts': content_origin_counts,
            'fallback_mode_counts': fallback_mode_counts,
            'avg_parse_quality_score': round(quality_score_total / parsed_record_count, 2) if parsed_record_count else 0.0,
            'graph_status_counts': graph_status_counts,
        }

    def _build_trace_path_detail(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: Optional[str],
        traces: List[Dict[str, Any]],
        path_kind: str = 'support',
    ) -> Dict[str, Any]:
        fact_ids: List[str] = []
        support_refs: List[str] = []
        support_kinds: List[str] = []
        source_families: List[str] = []
        graph_ids: List[str] = []

        for trace in traces or []:
            if not isinstance(trace, dict):
                continue
            fact_id = str(trace.get('fact_id') or '')
            if fact_id and fact_id not in fact_ids:
                fact_ids.append(fact_id)
            support_ref = str(trace.get('support_ref') or '')
            if support_ref and support_ref not in support_refs:
                support_refs.append(support_ref)
            support_kind = str(trace.get('support_kind') or '')
            if support_kind and support_kind not in support_kinds:
                support_kinds.append(support_kind)
            source_family = str(trace.get('source_family') or trace.get('record_scope') or '')
            if source_family and source_family not in source_families:
                source_families.append(source_family)
            graph_id = str(trace.get('graph_id') or '')
            if not graph_id:
                graph_trace = trace.get('graph_trace', {}) if isinstance(trace.get('graph_trace'), dict) else {}
                snapshot = graph_trace.get('snapshot', {}) if isinstance(graph_trace.get('snapshot'), dict) else {}
                graph_id = str(snapshot.get('graph_id') or '')
            if graph_id and graph_id not in graph_ids:
                graph_ids.append(graph_id)

        support_trace_summary = self._summarize_support_traces(traces)
        support_fact_registry_summary = self._summarize_fact_registry(traces)
        graph_trace_summary = self._summarize_graph_traces(traces)
        proof_path_id = self._make_trace_path_id(
            user_id=user_id,
            claim_type=claim_type,
            claim_element_id=claim_element_id or '',
            fact_ids=fact_ids,
            support_refs=support_refs,
            path_kind=path_kind,
        )
        return {
            'proof_path_id': proof_path_id,
            'claim_element_id': claim_element_id or '',
            'fact_ids': fact_ids,
            'fact_count': len(fact_ids),
            'support_refs': support_refs,
            'support_ref_count': len(support_refs),
            'support_kinds': support_kinds,
            'source_families': source_families,
            'graph_ids': graph_ids,
            'graph_id_count': len(graph_ids),
            'graph_trace_count': int(graph_trace_summary.get('traced_link_count', 0) or 0),
            'support_fact_registry_summary': support_fact_registry_summary,
            'trace_count': len(traces or []),
            'path_kind': path_kind or 'support',
            'source': 'current_traces',
            'persisted': False,
            'metadata': {
                'support_fact_registry_summary': support_fact_registry_summary,
                'support_trace_summary': support_trace_summary,
                'graph_trace_summary': graph_trace_summary,
            },
            'timestamp': '',
        }

    def _build_support_path_drilldown_metadata(
        self,
        traces: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fact_ids: List[str] = []
        support_refs: List[str] = []
        support_kinds: List[str] = []
        source_families: List[str] = []
        graph_ids: List[str] = []

        for trace in traces or []:
            if not isinstance(trace, dict):
                continue
            fact_id = str(trace.get('fact_id') or '')
            if fact_id and fact_id not in fact_ids:
                fact_ids.append(fact_id)
            support_ref = str(trace.get('support_ref') or trace.get('source_ref') or '')
            if support_ref and support_ref not in support_refs:
                support_refs.append(support_ref)
            support_kind = str(trace.get('support_kind') or '')
            if support_kind and support_kind not in support_kinds:
                support_kinds.append(support_kind)
            source_family = str(trace.get('source_family') or trace.get('record_scope') or '')
            if source_family and source_family not in source_families:
                source_families.append(source_family)
            graph_id = str(trace.get('graph_id') or '')
            if not graph_id:
                graph_trace = trace.get('graph_trace', {}) if isinstance(trace.get('graph_trace'), dict) else {}
                snapshot = graph_trace.get('snapshot', {}) if isinstance(graph_trace.get('snapshot'), dict) else {}
                graph_id = str(snapshot.get('graph_id') or '')
            if graph_id and graph_id not in graph_ids:
                graph_ids.append(graph_id)

        graph_trace_summary = self._summarize_graph_traces(traces or [])
        return {
            'fact_ids': fact_ids,
            'fact_count': len(fact_ids),
            'support_refs': support_refs,
            'support_ref_count': len(support_refs),
            'support_kinds': support_kinds,
            'source_families': source_families,
            'graph_ids': graph_ids,
            'graph_id_count': len(graph_ids),
            'graph_trace_count': int(graph_trace_summary.get('traced_link_count', 0) or 0),
            'graph_trace_summary': graph_trace_summary,
        }

    def _score_support_path_detail(
        self,
        path: Dict[str, Any],
        *,
        required_support_kinds: Optional[List[str]] = None,
        ontology: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        scored = score_support_path_quality(
            path,
            ontology=ontology,
            required_support_kinds=required_support_kinds,
        )
        path['support_quality'] = scored
        path['support_quality_score'] = float(scored.get('support_quality_score', 0.0) or 0.0)
        path['support_quality_tier'] = str(scored.get('support_quality_tier') or 'weak_support')
        path['quality_signals'] = list(scored.get('quality_signals') or [])
        return path

    def _summarize_support_path_quality(self, paths: List[Dict[str, Any]]) -> Dict[str, Any]:
        scored_paths = [
            path for path in (paths or [])
            if isinstance(path, dict) and isinstance(path.get('support_quality'), dict)
        ]
        tier_counts: Dict[str, int] = {}
        signal_counts: Dict[str, int] = {}
        total_score = 0.0
        best_path: Dict[str, Any] = {}
        weakest_path: Dict[str, Any] = {}

        for path in scored_paths:
            score = float(path.get('support_quality_score', 0.0) or 0.0)
            total_score += score
            tier = str(path.get('support_quality_tier') or 'unknown')
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            for signal in path.get('quality_signals', []) or []:
                if not isinstance(signal, dict):
                    continue
                signal_type = str(signal.get('signal_type') or 'unknown')
                signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1
            if not best_path or score > float(best_path.get('support_quality_score', 0.0) or 0.0):
                best_path = path
            if not weakest_path or score < float(weakest_path.get('support_quality_score', 0.0) or 0.0):
                weakest_path = path

        scored_count = len(scored_paths)
        best_tier = str(best_path.get('support_quality_tier') or '') if best_path else ''
        if tier_counts.get('structurally_missing', 0):
            recommended_action = 'collect_initial_support'
        elif tier_counts.get('weak_support', 0) or tier_counts.get('duplicate_support', 0):
            recommended_action = 'strengthen_support_path'
        elif best_tier in {'strong_support', 'moderate_support'}:
            recommended_action = 'review_support_quality'
        else:
            recommended_action = 'collect_initial_support'

        return {
            'path_count': len([path for path in (paths or []) if isinstance(path, dict)]),
            'scored_path_count': scored_count,
            'avg_quality_score': round(total_score / scored_count, 4) if scored_count else 0.0,
            'best_quality_score': round(float(best_path.get('support_quality_score', 0.0) or 0.0), 4) if best_path else 0.0,
            'weakest_quality_score': round(float(weakest_path.get('support_quality_score', 0.0) or 0.0), 4) if weakest_path else 0.0,
            'best_quality_tier': best_tier,
            'tier_counts': tier_counts,
            'quality_signal_counts': signal_counts,
            'strong_support_path_count': tier_counts.get('strong_support', 0),
            'weak_support_path_count': tier_counts.get('weak_support', 0),
            'duplicate_support_path_count': tier_counts.get('duplicate_support', 0),
            'structurally_missing_path_count': tier_counts.get('structurally_missing', 0),
            'strongest_proof_path_id': str(best_path.get('proof_path_id') or '') if best_path else '',
            'weakest_proof_path_id': str(weakest_path.get('proof_path_id') or '') if weakest_path else '',
            'recommended_quality_action': recommended_action,
        }

    def _build_fact_record_trace(self, fact: Dict[str, Any], *, support_kind: str = '') -> Dict[str, Any]:
        source_ref = (
            fact.get('source_artifact_id')
            or fact.get('source_authority_id')
            or fact.get('source_testimony_id')
            or fact.get('fact_id')
            or ''
        )
        resolved_support_kind = support_kind
        if not resolved_support_kind:
            if fact.get('source_authority_id'):
                resolved_support_kind = 'authority'
            elif fact.get('source_testimony_id'):
                resolved_support_kind = 'testimony'
            else:
                resolved_support_kind = 'evidence'
        return {
            'claim_type': fact.get('claim_type'),
            'claim_element_id': fact.get('claim_element_id'),
            'claim_element_text': fact.get('claim_element_text'),
            'support_kind': resolved_support_kind,
            'support_ref': source_ref,
            'support_label': fact.get('proposition_text', ''),
            'source_table': resolved_support_kind,
            'source_family': resolved_support_kind,
            'source_record_id': None,
            'source_ref': source_ref,
            'record_scope': resolved_support_kind,
            'fact_id': fact.get('fact_id', ''),
            'fact_text': fact.get('proposition_text', ''),
            'confidence': fact.get('confidence', 0.0),
            'trace_kind': 'fact',
            'graph_summary': {},
            'graph_trace': {},
            'graph_id': '',
        }

    def _extract_logic_contradiction_count(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> int:
        return _extract_logic_contradiction_count_payload(reasoning_diagnostics)

    def _extract_logic_proof_counts(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> Dict[str, int]:
        return _extract_logic_proof_counts_payload(reasoning_diagnostics)

    def _extract_ontology_validation_signal(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> str:
        return _extract_ontology_validation_signal_payload(reasoning_diagnostics)

    def _extract_temporal_rule_profile(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
        temporal_rule_profile = reasoning.get('temporal_rule_profile', {})
        return temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}

    def _build_temporal_next_actions(
        self,
        *,
        claim_type: str,
        element: Dict[str, Any],
        temporal_context: Dict[str, Any],
        temporal_rule_profile: Dict[str, Any],
        fact_ids: List[str],
        relation_ids: List[str],
        issue_ids: List[str],
        missing_temporal_predicates: List[str],
        required_provenance_kinds: List[str],
        missing_fact_roles: List[str],
        missing_relations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        profile = temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}
        context = temporal_context if isinstance(temporal_context, dict) else {}
        issues = [issue for issue in (context.get('temporal_issues', []) or []) if isinstance(issue, dict)]
        issue_by_id = {
            str(issue.get('issue_id') or issue.get('contradiction_id') or issue.get('dependency_id') or '').strip(): issue
            for issue in issues
            if str(issue.get('issue_id') or issue.get('contradiction_id') or issue.get('dependency_id') or '').strip()
        }
        profile_id = str(profile.get('profile_id') or '').strip()
        rule_frame_id = str(profile.get('rule_frame_id') or '').strip()
        temporal_rule_status = str(profile.get('status') or '').strip()
        claim_element_id = str(element.get('element_id') or '').strip()
        claim_element_text = str(element.get('element_text') or '').strip()
        actions: List[Dict[str, Any]] = []
        seen = set()

        def _issue_category(issue: Dict[str, Any]) -> str:
            return str(issue.get('issue_type') or issue.get('category') or '').strip()

        def _issue_fact_ids(issue: Dict[str, Any]) -> List[str]:
            values = [
                str(item).strip()
                for item in (issue.get('fact_ids') if isinstance(issue.get('fact_ids'), list) else [])
                if str(item).strip()
            ]
            return values or list(fact_ids)

        def _append_action(
            follow_up: Dict[str, Any],
            *,
            reason: str = '',
            issue: Optional[Dict[str, Any]] = None,
            blocking_reason: str = '',
        ) -> None:
            issue_record = issue if isinstance(issue, dict) else {}
            issue_category = _issue_category(issue_record)
            enriched = enrich_follow_up(follow_up if isinstance(follow_up, dict) else {}, issue_category=issue_category)
            lane = str(enriched.get('follow_up_lane') or enriched.get('lane') or '').strip()
            action_reason = str(
                reason
                or enriched.get('reason')
                or blocking_reason
                or issue_record.get('summary')
                or 'Resolve the temporal proof blocker.'
            ).strip()
            affected_issue_ids = [
                str(issue_record.get('issue_id') or issue_record.get('contradiction_id') or issue_record.get('dependency_id') or '').strip()
            ] if issue_record else []
            affected_issue_ids = [item for item in affected_issue_ids if item]
            if not affected_issue_ids:
                affected_issue_ids = list(issue_ids)
            affected_fact_ids = _issue_fact_ids(issue_record) if issue_record else list(fact_ids)
            key = (
                lane,
                action_reason,
                tuple(affected_issue_ids),
                tuple(affected_fact_ids),
                profile_id,
                rule_frame_id,
            )
            if key in seen:
                return
            seen.add(key)
            actions.append({
                'action': 'resolve_temporal_blocker',
                'next_action': 'resolve_temporal_blocker',
                'follow_up_lane': lane,
                'lane': str(enriched.get('lane') or lane),
                'follow_up_target': str(enriched.get('follow_up_target') or 'clarification'),
                'proof_criticality': str(enriched.get('proof_criticality') or 'medium'),
                'question_objective': str(enriched.get('question_objective') or 'anchor_capture'),
                'reason': action_reason,
                'prompt': str(enriched.get('prompt') or enriched.get('reason') or action_reason),
                'claim_type': str(claim_type or ''),
                'claim_element_id': claim_element_id,
                'claim_element_text': claim_element_text,
                'temporal_missingness_kind': 'temporal_gap',
                'follow_up_focus': 'temporal_gap_closure',
                'query_strategy': 'temporal_gap_targeted',
                'affected_rule': {
                    'profile_id': profile_id,
                    'rule_frame_id': rule_frame_id,
                    'status': temporal_rule_status,
                    'blocking_reason': blocking_reason or action_reason,
                },
                'affected_rule_profile_id': profile_id,
                'affected_rule_frame_id': rule_frame_id,
                'affected_fact_ids': affected_fact_ids,
                'affected_relation_ids': list(relation_ids),
                'affected_issue_ids': affected_issue_ids,
                'temporal_issue_ids': affected_issue_ids,
                'missing_fact_roles': list(missing_fact_roles),
                'missing_relations': list(missing_relations),
                'missing_temporal_predicates': list(missing_temporal_predicates),
                'required_provenance_kinds': list(required_provenance_kinds),
                'issue_category': issue_category,
            })

        for issue_id in issue_ids:
            issue = issue_by_id.get(issue_id, {})
            if not issue:
                continue
            _append_action(
                {
                    'lane': str(issue.get('recommended_resolution_lane') or ''),
                    'reason': str(issue.get('summary') or issue.get('label') or '').strip(),
                },
                issue=issue,
            )

        follow_ups = [
            follow_up
            for follow_up in (profile.get('recommended_follow_ups', []) or [])
            if isinstance(follow_up, dict)
        ]
        blocking_reasons = [
            str(reason).strip()
            for reason in (profile.get('blocking_reasons', []) or [])
            if str(reason).strip()
        ]
        for index, follow_up in enumerate(follow_ups):
            _append_action(
                follow_up,
                reason=str(follow_up.get('reason') or '').strip(),
                blocking_reason=blocking_reasons[index] if index < len(blocking_reasons) else '',
            )
        if not actions:
            for reason in blocking_reasons:
                _append_action({'lane': 'clarify_with_complainant', 'reason': reason}, blocking_reason=reason)
        if not actions and (missing_temporal_predicates or missing_fact_roles or missing_relations):
            _append_action(
                {
                    'lane': 'clarify_with_complainant',
                    'reason': 'Resolve missing temporal predicates or fact roles before proof execution.',
                }
            )

        ranked = rank_follow_ups(actions)
        for index, action in enumerate(ranked, start=1):
            action['rank'] = index
            action['action_id'] = ':'.join(
                part
                for part in [
                    'temporal_next_action',
                    self._normalize_reasoning_key(claim_type) or 'claim',
                    self._normalize_reasoning_key(claim_element_id or claim_element_text) or 'element',
                    str(index),
                ]
                if part
            )
        return ranked

    def _build_temporal_proof_bundle(
        self,
        claim_type: str,
        element: Dict[str, Any],
        temporal_context: Optional[Dict[str, Any]],
        temporal_rule_profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return _build_temporal_proof_bundle(self, claim_type, element, temporal_context, temporal_rule_profile)

    def _build_claim_support_temporal_handoff(
        self,
        claim_type: str,
        element: Dict[str, Any],
        temporal_context: Optional[Dict[str, Any]],
        temporal_proof_bundle: Optional[Dict[str, Any]],
        temporal_rule_profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        context = temporal_context if isinstance(temporal_context, dict) else {}
        proof_bundle = temporal_proof_bundle if isinstance(temporal_proof_bundle, dict) else {}
        profile = temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}

        def _dedupe_text_values(values: Any) -> List[str]:
            normalized_values: List[str] = []
            for value in values if isinstance(values, list) else []:
                normalized = str(value or '').strip()
                if normalized and normalized not in normalized_values:
                    normalized_values.append(normalized)
            return normalized_values

        fact_ids = _dedupe_text_values([
            fact.get('fact_id')
            for fact in (context.get('temporal_facts', []) or [])
            if isinstance(fact, dict)
        ])
        relation_ids = _dedupe_text_values([
            relation.get('relation_id')
            for relation in (context.get('temporal_relations', []) or [])
            if isinstance(relation, dict)
        ])
        timeline_anchor_ids = _dedupe_text_values([
            anchor_id
            for fact in (context.get('temporal_facts', []) or [])
            if isinstance(fact, dict)
            for anchor_id in (fact.get('timeline_anchor_ids', []) or [])
        ])
        issue_ids = _dedupe_text_values([
            issue.get('issue_id') or issue.get('contradiction_id') or issue.get('dependency_id')
            for issue in (context.get('temporal_issues', []) or [])
            if isinstance(issue, dict)
        ])
        temporal_consistency_summary = (
            context.get('consistency_summary', {})
            if isinstance(context.get('consistency_summary'), dict)
            else {}
        )
        missing_temporal_predicates = _dedupe_text_values(
            temporal_consistency_summary.get('missing_temporal_predicates')
        )
        required_provenance_kinds = _dedupe_text_values(
            temporal_consistency_summary.get('required_provenance_kinds')
        )
        proof_bundle_id = str(proof_bundle.get('proof_bundle_id') or '').strip()
        proof_objective = str(profile.get('rule_frame_id') or '').strip()
        blocking_reasons = _dedupe_text_values(proof_bundle.get('blocking_reasons'))
        recommended_follow_ups = _dedupe_text_values([
            follow_up.get('action') or follow_up.get('prompt') or follow_up.get('label')
            for follow_up in (proof_bundle.get('recommended_follow_ups', []) or [])
            if isinstance(follow_up, dict)
        ])
        temporal_next_actions = [
            dict(action)
            for action in (proof_bundle.get('temporal_next_actions', []) or [])
            if isinstance(action, dict)
        ]

        chronology_task_count = len(temporal_next_actions) or len(recommended_follow_ups) or len(blocking_reasons) or len(issue_ids)
        temporal_handoff = {
            'claim_type': str(claim_type or '').strip(),
            'claim_element_id': str(element.get('element_id') or '').strip(),
            'unresolved_temporal_issue_count': len(issue_ids),
            'unresolved_temporal_issue_ids': issue_ids,
            'chronology_task_count': chronology_task_count,
            'temporal_next_actions': temporal_next_actions,
            'temporal_next_action_count': len(temporal_next_actions),
            'event_ids': list(fact_ids),
            'temporal_fact_ids': list(fact_ids),
            'temporal_relation_ids': relation_ids,
            'timeline_anchor_ids': timeline_anchor_ids,
            'timeline_issue_ids': list(issue_ids),
            'temporal_issue_ids': list(issue_ids),
            'missing_temporal_predicates': missing_temporal_predicates,
            'required_provenance_kinds': required_provenance_kinds,
            'temporal_proof_bundle_ids': [proof_bundle_id] if proof_bundle_id else [],
            'temporal_proof_objectives': [proof_objective] if proof_objective else [],
        }
        if not temporal_handoff['claim_type']:
            temporal_handoff.pop('claim_type')
        if not temporal_handoff['claim_element_id']:
            temporal_handoff.pop('claim_element_id')
        if not temporal_handoff['unresolved_temporal_issue_count'] and not temporal_handoff['chronology_task_count'] and not any(
            temporal_handoff[key]
            for key in (
                'unresolved_temporal_issue_ids',
                'event_ids',
                'temporal_fact_ids',
                'temporal_relation_ids',
                'timeline_anchor_ids',
                'timeline_issue_ids',
                'temporal_issue_ids',
                'missing_temporal_predicates',
                'required_provenance_kinds',
                'temporal_proof_bundle_ids',
                'temporal_proof_objectives',
            )
        ):
            return {}
        return temporal_handoff

    def _extract_graphrag_quality_signal(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Extract GraphRAG ontology quality and gap signals from *reasoning_diagnostics*.

        Returns a dict with ``quality_score``, ``grade``, ``has_gaps``,
        ``has_blocking_gaps``, and ``gaps`` (list of gap dicts).
        """
        reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
        graphrag_quality = reasoning.get('graphrag_quality', {})
        if not isinstance(graphrag_quality, dict) or not graphrag_quality:
            return {
                'quality_score': None,
                'grade': None,
                'has_gaps': False,
                'has_blocking_gaps': False,
                'gaps': [],
                'available': False,
            }
        return {
            'quality_score': graphrag_quality.get('overall_quality_score'),
            'grade': graphrag_quality.get('grade'),
            'has_gaps': bool(graphrag_quality.get('has_gaps', False)),
            'has_blocking_gaps': bool(graphrag_quality.get('has_blocking_gaps', False)),
            'gaps': list(graphrag_quality.get('gaps') or []),
            'entity_coverage_score': graphrag_quality.get('entity_coverage_score'),
            'concept_completeness_score': graphrag_quality.get('concept_completeness_score'),
            'available': True,
        }

    def _build_validation_decision_trace(
        self,
        element: Dict[str, Any],
        contradiction_candidates: List[Dict[str, Any]],
        reasoning_diagnostics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
        adapter_statuses = reasoning.get('adapter_statuses', {}) if isinstance(reasoning.get('adapter_statuses'), dict) else {}
        heuristic_contradiction_count = len(contradiction_candidates)
        logic_contradiction_count = self._extract_logic_contradiction_count(reasoning)
        logic_proof_counts = self._extract_logic_proof_counts(reasoning)
        provable_count = logic_proof_counts['provable_count']
        unprovable_count = logic_proof_counts['unprovable_count']
        ontology_validation_signal = self._extract_ontology_validation_signal(reasoning)
        temporal_rule_profile = self._extract_temporal_rule_profile(reasoning)
        temporal_rule_status = str(temporal_rule_profile.get('status') or '')
        graphrag_quality_signal = self._extract_graphrag_quality_signal(reasoning)
        graphrag_has_blocking_gaps = bool(
            reasoning.get('graphrag_quality_enforces_proof_gaps', True)
            and graphrag_quality_signal.get('has_blocking_gaps', False)
        )
        missing_support_kind_count = len(element.get('missing_support_kinds', []) or [])
        total_links = int(element.get('total_links', 0) or 0)
        coverage_status = str(element.get('status') or '')

        if heuristic_contradiction_count:
            decision_source = 'heuristic_contradictions'
            validation_status = 'contradicted'
        elif logic_contradiction_count:
            decision_source = 'logic_contradictions'
            validation_status = 'contradicted'
        elif temporal_rule_status == 'failed':
            decision_source = 'temporal_rule_failed'
            validation_status = 'incomplete'
        elif temporal_rule_status == 'partial' and total_links > 0:
            decision_source = 'temporal_rule_partial'
            validation_status = 'incomplete'
        elif unprovable_count and total_links > 0:
            decision_source = 'logic_unprovable'
            validation_status = 'incomplete'
        elif provable_count and missing_support_kind_count == 0 and ontology_validation_signal != 'invalid':
            decision_source = 'logic_proof_supported'
            validation_status = 'supported'
        elif provable_count:
            decision_source = 'logic_proof_partial'
            validation_status = 'incomplete'
        elif ontology_validation_signal == 'invalid' and total_links > 0:
            decision_source = 'ontology_validation_failed'
            validation_status = 'incomplete'
        elif coverage_status == 'covered' and total_links > 0 and self._element_has_parse_quality_gap(element):
            decision_source = 'low_quality_parse'
            validation_status = 'incomplete'
        elif graphrag_has_blocking_gaps and total_links > 0:
            decision_source = 'graphrag_quality_gap'
            validation_status = 'incomplete'
        elif ontology_validation_signal == 'valid' and coverage_status == 'covered' and missing_support_kind_count == 0:
            decision_source = 'ontology_validation_supported'
            validation_status = 'supported'
        elif coverage_status == 'covered':
            decision_source = 'covered_support'
            validation_status = 'supported'
        elif total_links > 0:
            decision_source = 'partial_support'
            validation_status = 'incomplete'
        else:
            decision_source = 'missing_support'
            validation_status = 'missing'

        notes: List[str] = []
        if heuristic_contradiction_count:
            notes.append('Heuristic contradiction candidates were found for this element.')
        if logic_contradiction_count:
            notes.append('Logic adapter reported contradiction output for this element.')
        if provable_count:
            notes.append('Logic adapter reported provable claim-element output for this element.')
        if unprovable_count:
            notes.append('Logic adapter reported unprovable claim-element output for this element.')
        if temporal_rule_status == 'failed':
            notes.append('Temporal rule evaluation found chronology that is legally insufficient for this element.')
        elif temporal_rule_status == 'partial':
            notes.append('Temporal rule evaluation found chronology that is present but still incomplete for this element.')
        if ontology_validation_signal == 'invalid':
            notes.append('Ontology validation returned an invalid or inconsistent result for this element.')
        elif ontology_validation_signal == 'valid':
            notes.append('Ontology validation reported a valid or consistent result for this element.')
        if validation_status == 'incomplete' and decision_source == 'low_quality_parse':
            notes.append('Available support was parsed with low extraction quality and should be refreshed from a better source copy.')
        if decision_source == 'graphrag_quality_gap':
            notes.append('GraphRAG ontology has blocking quality gaps that need to be resolved before this element can be fully validated.')
        if missing_support_kind_count:
            notes.append('Required support kinds are still missing for this element.')
        if reasoning.get('used_fallback_ontology'):
            notes.append('Fallback ontology was used because adapter ontology output was unavailable or empty.')

        return {
            'validation_status': validation_status,
            'decision_source': decision_source,
            'coverage_status': coverage_status,
            'heuristic_contradiction_count': heuristic_contradiction_count,
            'logic_contradiction_count': logic_contradiction_count,
            'logic_provable_count': provable_count,
            'logic_unprovable_count': unprovable_count,
            'ontology_validation_signal': ontology_validation_signal,
            'temporal_rule_profile_id': str(temporal_rule_profile.get('profile_id') or ''),
            'temporal_rule_status': temporal_rule_status,
            'temporal_rule_blocking_reason_count': len(temporal_rule_profile.get('blocking_reasons', []) or []),
            'temporal_rule_follow_up_count': len(temporal_rule_profile.get('recommended_follow_ups', []) or []),
            'graphrag_quality_signal': graphrag_quality_signal,
            'graphrag_has_blocking_gaps': graphrag_has_blocking_gaps,
            'missing_support_kind_count': missing_support_kind_count,
            'total_links': total_links,
            'used_fallback_ontology': bool(reasoning.get('used_fallback_ontology')),
            'adapter_statuses': {
                name: {
                    'status': str(summary.get('status') or ''),
                    'implementation_status': str(summary.get('implementation_status') or ''),
                    'backend_available': bool(summary.get('backend_available', False)),
                }
                for name, summary in adapter_statuses.items()
                if isinstance(summary, dict)
            },
            'notes': notes,
        }

    def _proof_gaps_for_element(
        self,
        element: Dict[str, Any],
        contradiction_candidates: List[Dict[str, Any]],
        reasoning_diagnostics: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        proof_gaps: List[Dict[str, Any]] = []
        for support_kind in element.get('missing_support_kinds', []) or []:
            proof_gaps.append(
                {
                    'gap_type': 'missing_support_kind',
                    'support_kind': support_kind,
                    'message': f'Missing required {support_kind} support.',
                }
            )
        if contradiction_candidates:
            proof_gaps.append(
                {
                    'gap_type': 'contradiction_candidates',
                    'candidate_count': len(contradiction_candidates),
                    'message': 'Conflicting support facts require operator review.',
                }
            )
        logic_contradiction_count = self._extract_logic_contradiction_count(reasoning_diagnostics)
        if logic_contradiction_count and not contradiction_candidates:
            proof_gaps.append(
                {
                    'gap_type': 'logic_contradictions',
                    'candidate_count': logic_contradiction_count,
                    'message': 'Logic adapter reported contradictions requiring operator review.',
                }
            )
        logic_proof_counts = self._extract_logic_proof_counts(reasoning_diagnostics)
        if logic_proof_counts['unprovable_count']:
            proof_gaps.append(
                {
                    'gap_type': 'logic_unprovable',
                    'candidate_count': logic_proof_counts['unprovable_count'],
                    'message': 'Logic adapter could not prove one or more predicates for this element.',
                }
            )
        temporal_rule_profile = self._extract_temporal_rule_profile(reasoning_diagnostics)
        temporal_rule_status = str(temporal_rule_profile.get('status') or '')
        if temporal_rule_status in {'failed', 'partial'}:
            proof_gaps.append(
                {
                    'gap_type': f'temporal_rule_{temporal_rule_status}',
                    'profile_id': temporal_rule_profile.get('profile_id'),
                    'message': '; '.join(temporal_rule_profile.get('blocking_reasons', []) or [])
                    or 'Temporal rule profile found unresolved chronology for this element.',
                    'follow_ups': temporal_rule_profile.get('recommended_follow_ups', []),
                }
            )
        ontology_validation_signal = self._extract_ontology_validation_signal(reasoning_diagnostics)
        if ontology_validation_signal == 'invalid':
            proof_gaps.append(
                {
                    'gap_type': 'ontology_validation_failed',
                    'message': 'Ontology validation reported an invalid or inconsistent reasoning graph for this element.',
                }
            )
        graphrag_quality_signal = self._extract_graphrag_quality_signal(reasoning_diagnostics)
        reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
        if (
            reasoning.get('graphrag_quality_enforces_proof_gaps', True)
            and graphrag_quality_signal.get('available')
            and graphrag_quality_signal.get('has_blocking_gaps')
        ):
            blocking_gaps = [
                g for g in (graphrag_quality_signal.get('gaps') or [])
                if g.get('severity') == 'blocking'
            ]
            proof_gaps.append(
                {
                    'gap_type': 'graphrag_quality_gap',
                    'gap_count': len(graphrag_quality_signal.get('gaps') or []),
                    'blocking_gap_count': len(blocking_gaps),
                    'message': 'GraphRAG ontology has blocking quality gaps for this element.',
                    'follow_up_action': blocking_gaps[0].get('follow_up_action', '') if blocking_gaps else 'improve_ontology_quality',
                }
            )
        return proof_gaps

    def _recommended_validation_action(
        self,
        validation_status: str,
        element: Dict[str, Any],
        proof_gaps: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if validation_status == 'contradicted':
            return 'resolve_contradiction'
        if validation_status == 'missing':
            return 'collect_initial_support'
        if validation_status == 'incomplete':
            proof_gap_types = self._extract_proof_gap_types(proof_gaps or [])
            decision_trace = element.get('proof_decision_trace', {}) if isinstance(element.get('proof_decision_trace'), dict) else {}
            if 'graphrag_quality_gap' in proof_gap_types or bool(decision_trace.get('graphrag_has_blocking_gaps', False)):
                return 'improve_graph_quality'
            if (
                not (element.get('missing_support_kinds', []) or [])
                and not self._has_reasoning_gap_signals(
                    proof_gap_types,
                    decision_trace,
                )
                and self._element_has_parse_quality_gap(element)
            ):
                return 'improve_parse_quality'
            if not (element.get('missing_support_kinds', []) or []):
                return 'review_existing_support'
            return self._recommended_support_gap_action(element)
        return 'review_existing_support'

    def _element_has_parse_quality_gap(self, element: Dict[str, Any]) -> bool:
        summary = element.get('support_trace_summary', {}) if isinstance(element.get('support_trace_summary'), dict) else {}
        parsed_record_count = int(summary.get('parsed_record_count', 0) or 0)
        quality_counts = summary.get('parse_quality_tier_counts', {}) if isinstance(summary.get('parse_quality_tier_counts'), dict) else {}
        low_count = int(quality_counts.get('low', 0) or 0)
        empty_count = int(quality_counts.get('empty', 0) or 0)
        if parsed_record_count > 0:
            if low_count > 0 or empty_count > 0:
                return True

            avg_quality_score = float(summary.get('avg_parse_quality_score', 0.0) or 0.0)
            return 0.0 < avg_quality_score < 75.0

        for trace in self._collect_support_traces_from_links(element.get('links', []) or []):
            if not isinstance(trace, dict):
                continue
            record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
            parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
            quality_tier = str(parse_summary.get('quality_tier') or '')
            if quality_tier in {'low', 'empty'}:
                return True
            quality_score = float(parse_summary.get('quality_score', 0.0) or 0.0)
            if 0.0 < quality_score < 75.0:
                return True
        return False

    def _extract_proof_gap_types(self, proof_gaps: List[Dict[str, Any]]) -> List[str]:
        gap_types: List[str] = []
        for gap in proof_gaps or []:
            if not isinstance(gap, dict):
                continue
            gap_type = str(gap.get('gap_type') or '').strip()
            if gap_type and gap_type not in gap_types:
                gap_types.append(gap_type)
        return gap_types

    def _has_reasoning_gap_signals(
        self,
        proof_gap_types: List[str],
        proof_decision_trace: Dict[str, Any] = None,
    ) -> bool:
        decision_trace = proof_decision_trace if isinstance(proof_decision_trace, dict) else {}
        decision_source = str(decision_trace.get('decision_source') or '')
        ontology_validation_signal = str(decision_trace.get('ontology_validation_signal') or '')
        graphrag_has_blocking_gaps = bool(decision_trace.get('graphrag_has_blocking_gaps', False))
        return (
            'logic_unprovable' in (proof_gap_types or [])
            or 'temporal_rule_failed' in (proof_gap_types or [])
            or 'temporal_rule_partial' in (proof_gap_types or [])
            or 'ontology_validation_failed' in (proof_gap_types or [])
            or 'graphrag_quality_gap' in (proof_gap_types or [])
            or decision_source in {'logic_unprovable', 'logic_proof_partial', 'ontology_validation_failed', 'temporal_rule_failed', 'temporal_rule_partial', 'graphrag_quality_gap'}
            or ontology_validation_signal == 'invalid'
            or graphrag_has_blocking_gaps
        )

    def _normalize_reasoning_key(self, value: Any) -> str:
        text = str(value or '').strip().lower()
        return ''.join(ch if ch.isalnum() else '_' for ch in text).strip('_')

    def _get_temporal_reasoning_context(
        self,
        claim_type: str,
        element: Dict[str, Any],
    ) -> Dict[str, Any]:
        return _get_temporal_reasoning_context(self, claim_type, element)

    def _build_reasoning_predicates(
        self,
        claim_type: str,
        element: Dict[str, Any],
        contradiction_candidates: List[Dict[str, Any]],
        temporal_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        predicates: List[Dict[str, Any]] = [
            {
                'predicate_id': str(element.get('element_id') or element.get('element_text') or claim_type),
                'predicate_type': 'claim_element',
                'claim_type': claim_type,
                'claim_element_id': element.get('element_id'),
                'claim_element_text': element.get('element_text'),
                'coverage_status': element.get('status'),
                'support_by_kind': element.get('support_by_kind', {}),
                'missing_support_kinds': element.get('missing_support_kinds', []),
            }
        ]

        for trace in element.get('support_traces', []) or []:
            if not isinstance(trace, dict):
                continue
            predicates.append(
                {
                    'predicate_id': str(trace.get('fact_id') or trace.get('support_ref') or ''),
                    'predicate_type': 'support_trace',
                    'claim_type': claim_type,
                    'claim_element_id': element.get('element_id'),
                    'claim_element_text': element.get('element_text'),
                    'support_kind': trace.get('support_kind'),
                    'support_ref': trace.get('support_ref'),
                    'source_table': trace.get('source_table'),
                    'text': trace.get('fact_text') or trace.get('support_label') or '',
                    'confidence': trace.get('confidence', 0.0),
                    'source_proof': self._support_trace_source_proof(trace),
                }
            )

        reasoning_temporal_context = temporal_context if isinstance(temporal_context, dict) else self._get_temporal_reasoning_context(claim_type, element)
        for fact in reasoning_temporal_context.get('temporal_facts', []) or []:
            if not isinstance(fact, dict):
                continue
            temporal_details = fact.get('temporal_context', {}) if isinstance(fact.get('temporal_context'), dict) else {}
            predicates.append(
                {
                    'predicate_id': f"temporal_fact:{fact.get('fact_id') or fact.get('text') or ''}",
                    'predicate_type': 'temporal_fact',
                    'claim_type': claim_type,
                    'claim_element_id': element.get('element_id'),
                    'claim_element_text': element.get('element_text'),
                    'fact_id': fact.get('fact_id'),
                    'text': fact.get('text') or '',
                    'fact_type': fact.get('fact_type'),
                    'event_label': fact.get('event_label') or fact.get('text') or fact.get('fact_id'),
                    'predicate_family': fact.get('predicate_family') or fact.get('fact_type') or 'timeline',
                    'claim_types': list(fact.get('claim_types', []) or []),
                    'element_tags': list(fact.get('element_tags', []) or []),
                    'actor_ids': list(fact.get('actor_ids', []) or []),
                    'target_ids': list(fact.get('target_ids', []) or []),
                    'start_date': temporal_details.get('start_date'),
                    'end_date': temporal_details.get('end_date'),
                    'granularity': temporal_details.get('granularity'),
                    'is_approximate': bool(temporal_details.get('is_approximate', False)),
                    'is_range': bool(temporal_details.get('is_range', False)),
                    'relative_markers': list(temporal_details.get('relative_markers', []) or []),
                    'timeline_anchor_ids': list(fact.get('timeline_anchor_ids', []) or []),
                    'source_artifact_ids': list(fact.get('source_artifact_ids', []) or []),
                    'testimony_record_ids': list(fact.get('testimony_record_ids', []) or []),
                    'source_span_refs': list(fact.get('source_span_refs', []) or []),
                    'validation_status': fact.get('validation_status'),
                }
            )

        for lead in reasoning_temporal_context.get('temporal_proof_leads', []) or []:
            if not isinstance(lead, dict):
                continue
            temporal_details = lead.get('temporal_context', {}) if isinstance(lead.get('temporal_context'), dict) else {}
            predicates.append(
                {
                    'predicate_id': f"temporal_proof_lead:{lead.get('lead_id') or lead.get('description') or ''}",
                    'predicate_type': 'temporal_proof_lead',
                    'claim_type': claim_type,
                    'claim_element_id': element.get('element_id'),
                    'claim_element_text': element.get('element_text'),
                    'lead_id': lead.get('lead_id'),
                    'description': lead.get('description') or '',
                    'related_fact_ids': list(lead.get('related_fact_ids', []) or []),
                    'element_targets': list(lead.get('element_targets', []) or []),
                    'temporal_scope': lead.get('temporal_scope'),
                    'start_date': temporal_details.get('start_date'),
                    'end_date': temporal_details.get('end_date'),
                    'granularity': temporal_details.get('granularity'),
                    'is_approximate': bool(temporal_details.get('is_approximate', False)),
                    'is_range': bool(temporal_details.get('is_range', False)),
                }
            )

        for relation in reasoning_temporal_context.get('temporal_relations', []) or []:
            if not isinstance(relation, dict):
                continue
            predicates.append(
                {
                    'predicate_id': str(relation.get('relation_id') or ''),
                    'predicate_type': 'temporal_relation',
                    'claim_type': claim_type,
                    'claim_element_id': element.get('element_id'),
                    'claim_element_text': element.get('element_text'),
                    'relation_type': relation.get('relation_type'),
                    'inference_mode': relation.get('inference_mode') or 'derived_from_temporal_context',
                    'inference_basis': relation.get('inference_basis') or 'normalized_temporal_context',
                    'explanation': relation.get('explanation') or (
                        f"{relation.get('source_fact_id') or 'unknown_fact'} {relation.get('relation_type') or 'related_to'} "
                        f"{relation.get('target_fact_id') or 'unknown_fact'} based on normalized temporal context."
                    ),
                    'source_fact_id': relation.get('source_fact_id'),
                    'target_fact_id': relation.get('target_fact_id'),
                    'source_start_date': relation.get('source_start_date'),
                    'source_end_date': relation.get('source_end_date'),
                    'target_start_date': relation.get('target_start_date'),
                    'target_end_date': relation.get('target_end_date'),
                    'confidence': relation.get('confidence'),
                    'source_artifact_ids': list(relation.get('source_artifact_ids', []) or []),
                    'testimony_record_ids': list(relation.get('testimony_record_ids', []) or []),
                    'source_span_refs': list(relation.get('source_span_refs', []) or []),
                }
            )

        consistency_summary = reasoning_temporal_context.get('consistency_summary', {})
        if isinstance(consistency_summary, dict) and consistency_summary:
            predicates.append(
                {
                    'predicate_id': f"temporal_consistency:{element.get('element_id') or element.get('element_text') or claim_type}",
                    'predicate_type': 'temporal_consistency',
                    'claim_type': claim_type,
                    'claim_element_id': element.get('element_id'),
                    'claim_element_text': element.get('element_text'),
                    'event_count': consistency_summary.get('event_count', 0),
                    'proof_lead_count': consistency_summary.get('proof_lead_count', 0),
                    'relation_count': consistency_summary.get('relation_count', 0),
                    'issue_count': consistency_summary.get('issue_count', 0),
                    'partial_order_ready': bool(consistency_summary.get('partial_order_ready', False)),
                    'warning_count': consistency_summary.get('warning_count', 0),
                    'warnings': list(consistency_summary.get('warnings', []) or []),
                    'relation_type_counts': dict(consistency_summary.get('relation_type_counts', {}) or {}),
                    'timeline_anchor_ids': list(consistency_summary.get('timeline_anchor_ids', []) or []),
                    'missing_temporal_predicates': list(consistency_summary.get('missing_temporal_predicates', []) or []),
                    'required_provenance_kinds': list(consistency_summary.get('required_provenance_kinds', []) or []),
                }
            )

        for issue in reasoning_temporal_context.get('temporal_issues', []) or []:
            if not isinstance(issue, dict):
                continue
            predicates.append(
                {
                    'predicate_id': str(issue.get('contradiction_id') or issue.get('dependency_id') or issue.get('issue_id') or ''),
                    'predicate_type': 'temporal_issue',
                    'claim_type': claim_type,
                    'claim_element_id': element.get('element_id'),
                    'claim_element_text': element.get('element_text'),
                    'issue_type': issue.get('category') or issue.get('issue_type'),
                    'summary': issue.get('summary') or issue.get('label') or '',
                    'severity': issue.get('severity'),
                    'left_node_name': issue.get('left_node_name'),
                    'right_node_name': issue.get('right_node_name'),
                    'recommended_resolution_lane': issue.get('recommended_resolution_lane'),
                    'source_kind': issue.get('source_kind') or 'contradiction_queue',
                    'source_ref': issue.get('source_ref'),
                    'inference_mode': issue.get('inference_mode') or 'imported_temporal_contradiction',
                }
            )

        for index, candidate in enumerate(contradiction_candidates):
            if not isinstance(candidate, dict):
                continue
            predicates.append(
                {
                    'predicate_id': f"contradiction:{element.get('element_id') or element.get('element_text') or claim_type}:{index}",
                    'predicate_type': 'contradiction_candidate',
                    'claim_type': claim_type,
                    'claim_element_id': element.get('element_id'),
                    'claim_element_text': element.get('element_text'),
                    'support_refs': candidate.get('support_refs', []),
                    'overlap_terms': candidate.get('overlap_terms', []),
                    'texts': candidate.get('texts', []),
                    'polarity': candidate.get('polarity', []),
                }
            )

        return predicates

    def _support_trace_source_proof(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        """Keep source identity from a support trace without treating it as entailment."""

        record_summary = trace.get('record_summary') if isinstance(trace.get('record_summary'), dict) else {}
        graph_trace = trace.get('graph_trace') if isinstance(trace.get('graph_trace'), dict) else {}
        passage = trace.get('source_passage') if isinstance(trace.get('source_passage'), dict) else {}
        if not passage and isinstance(record_summary.get('source_passage'), dict):
            passage = record_summary.get('source_passage') or {}
        provenance = trace.get('provenance') if isinstance(trace.get('provenance'), dict) else {}
        character_span = None
        byte_span = None
        for source in (passage, provenance, trace):
            if character_span is None and any(key in source for key in ('start_char', 'char_start', 'end_char', 'char_end')):
                character_span = {
                    'start': source.get('start_char', source.get('char_start')),
                    'end': source.get('end_char', source.get('char_end')),
                    'span_unit': 'character',
                }
            if byte_span is None and any(key in source for key in ('byte_start', 'start_byte', 'byte_end', 'end_byte')):
                byte_span = {
                    'start': source.get('byte_start', source.get('start_byte')),
                    'end': source.get('byte_end', source.get('end_byte')),
                    'span_unit': 'utf8_byte',
                }
        validation_status = str(trace.get('validation_status') or record_summary.get('validation_status') or '')
        return {
            'fact_id': str(trace.get('fact_id') or ''),
            'support_ref': str(trace.get('support_ref') or ''),
            'source_table': str(trace.get('source_table') or ''),
            'source_family': str(trace.get('source_family') or ''),
            'source_record_id': trace.get('source_record_id'),
            'source_ref': str(trace.get('source_ref') or ''),
            'proof_path_id': str(trace.get('proof_path_id') or graph_trace.get('proof_path_id') or ''),
            'graph_id': str(trace.get('graph_id') or graph_trace.get('graph_id') or ''),
            'content_hash': str(
                trace.get('content_hash')
                or provenance.get('content_hash')
                or record_summary.get('content_hash')
                or ''
            ),
            'citation': str(trace.get('citation') or record_summary.get('citation') or ''),
            'authority_id': str(trace.get('authority_id') or record_summary.get('authority_id') or ''),
            'authority_version': str(
                trace.get('authority_version')
                or record_summary.get('authority_version')
                or ''
            ),
            'revision': str(trace.get('revision') or trace.get('fact_revision') or record_summary.get('revision') or ''),
            'validation_status': validation_status,
            'disputed': bool(trace.get('disputed')) or validation_status.lower() in {'disputed', 'contested'},
            'character_span': character_span,
            'utf8_byte_span': byte_span,
            'dual_provenance': character_span is not None and byte_span is not None,
            'epistemic_status': 'disputed' if bool(trace.get('disputed')) else 'allegation',
            'axiom': False,
            'is_entailment': False,
        }

    def _legal_ir_inputs_for_element(
        self,
        claim_type: str,
        element: Dict[str, Any],
        contradiction_candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        asserted: List[Dict[str, Any]] = []
        disputed: List[Dict[str, Any]] = []
        selected_rules: List[Dict[str, Any]] = []
        explicit_rules = element.get('selected_legal_rules') or element.get('selected_rules') or []
        if isinstance(explicit_rules, list):
            selected_rules.extend(rule for rule in explicit_rules if isinstance(rule, dict))
        for trace in element.get('support_traces', []) or []:
            if not isinstance(trace, dict):
                continue
            proof = self._support_trace_source_proof(trace)
            fact = {
                'fact_id': proof['fact_id'] or proof['support_ref'],
                'text': str(trace.get('fact_text') or trace.get('support_label') or ''),
                'revision': proof['revision'] or 'unversioned',
                'support_ref': proof['support_ref'],
                'source_table': proof['source_table'],
                'content_hash': proof['content_hash'],
                'citation': proof['citation'],
                'authority_version': proof['authority_version'],
                'disputed': proof['disputed'],
                'validation_status': proof['validation_status'],
            }
            if proof['character_span']:
                fact['span_unit'] = 'character'
                fact['char_start'] = proof['character_span']['start']
                fact['char_end'] = proof['character_span']['end']
            if proof['utf8_byte_span']:
                fact['span_unit'] = 'utf8_byte' if not proof['character_span'] else fact.get('span_unit', 'character')
                fact['byte_start'] = proof['utf8_byte_span']['start']
                fact['byte_end'] = proof['utf8_byte_span']['end']
            if proof['disputed'] or str(trace.get('support_kind') or '') == 'contradiction':
                disputed.append(fact)
            elif str(trace.get('support_kind') or '') not in {'authority', 'legal_rule'}:
                asserted.append(fact)
            for candidate in trace.get('rule_candidates') or []:
                if not isinstance(candidate, dict):
                    continue
                if candidate.get('applicable') is True or candidate.get('selected') is True:
                    selected_rules.append(candidate)
        for index, candidate in enumerate(contradiction_candidates):
            if not isinstance(candidate, dict):
                continue
            texts = candidate.get('texts') or []
            statement = texts[0] if isinstance(texts, list) and texts else candidate.get('summary') or candidate.get('text') or ''
            disputed.append(
                {
                    'fact_id': str(candidate.get('contradiction_id') or candidate.get('candidate_id') or f'contradiction-{index}'),
                    'text': str(statement or ''),
                    'revision': str(candidate.get('revision') or 'unversioned'),
                    'disputed': True,
                }
            )
        assumptions = element.get('assumptions') if isinstance(element.get('assumptions'), list) else []
        missing = [
            {'fact_id': f'missing:{kind}', 'text': '', 'revision': 'missing'}
            for kind in (element.get('missing_support_kinds') or [])
        ]
        modal = element.get('modal_ir') or element.get('legal_ir') or element.get('legal_ir_document')
        return {
            'sample_or_document': modal,
            'canonical_receipt': element.get('canonical_formalization') if isinstance(element.get('canonical_formalization'), dict) else None,
            'asserted_facts': asserted,
            'disputed_facts': disputed,
            'selected_legal_rules': selected_rules,
            'assumptions': assumptions,
            'missing_facts': missing,
            'legal_context_version': str(element.get('legal_context_version') or element.get('authority_version') or ''),
            'claim_id': str(element.get('claim_id') or claim_type),
            'element_id': str(element.get('element_id') or ''),
            'coverage_status': str(element.get('coverage_status') or element.get('status') or ''),
            'max_obligations': element.get('max_obligations'),
            'source_text': element.get('source_text') if isinstance(element.get('source_text'), str) else None,
            'requirement_id': str(element.get('requirement_id') or element.get('element_id') or ''),
            'definition_handoff': element.get('definition_handoff') if isinstance(element.get('definition_handoff'), dict) else None,
            'adverse_treatment': element.get('adverse_treatment'),
        }

    def _build_reasoning_ontology_fallback(
        self,
        claim_type: str,
        element: Dict[str, Any],
        contradiction_candidates: List[Dict[str, Any]],
        temporal_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        claim_entity_id = str(element.get('element_id') or element.get('element_text') or claim_type or 'claim-element')
        entities: List[Dict[str, Any]] = [
            {
                'id': claim_entity_id,
                'label': str(element.get('element_text') or claim_type),
                'type': 'claim_element',
            }
        ]
        relationships: List[Dict[str, Any]] = []
        entity_ids = {claim_entity_id}

        for trace in element.get('support_traces', []) or []:
            if not isinstance(trace, dict):
                continue
            support_id = str(trace.get('fact_id') or trace.get('support_ref') or '')
            if not support_id:
                continue
            if support_id not in entity_ids:
                entities.append(
                    {
                        'id': support_id,
                        'label': str(trace.get('fact_text') or trace.get('support_label') or support_id),
                        'type': str(trace.get('support_kind') or 'support'),
                    }
                )
                entity_ids.add(support_id)
            relationships.append(
                {
                    'source': support_id,
                    'target': claim_entity_id,
                    'type': 'supports',
                }
            )

        reasoning_temporal_context = temporal_context if isinstance(temporal_context, dict) else self._get_temporal_reasoning_context(claim_type, element)
        for fact in reasoning_temporal_context.get('temporal_facts', []) or []:
            if not isinstance(fact, dict):
                continue
            fact_id = f"temporal_fact:{fact.get('fact_id') or fact.get('text') or ''}"
            if fact_id not in entity_ids:
                entities.append(
                    {
                        'id': fact_id,
                        'label': str(fact.get('text') or fact.get('fact_id') or fact_id),
                        'type': 'temporal_fact',
                    }
                )
                entity_ids.add(fact_id)
            relationships.append(
                {
                    'source': fact_id,
                    'target': claim_entity_id,
                    'type': 'temporally_relevant_to',
                }
            )

        for relation in reasoning_temporal_context.get('temporal_relations', []) or []:
            if not isinstance(relation, dict):
                continue
            source_fact_id = f"temporal_fact:{relation.get('source_fact_id') or ''}"
            target_fact_id = f"temporal_fact:{relation.get('target_fact_id') or ''}"
            if source_fact_id not in entity_ids:
                entities.append({'id': source_fact_id, 'label': source_fact_id, 'type': 'temporal_fact'})
                entity_ids.add(source_fact_id)
            if target_fact_id not in entity_ids:
                entities.append({'id': target_fact_id, 'label': target_fact_id, 'type': 'temporal_fact'})
                entity_ids.add(target_fact_id)
            relationships.append(
                {
                    'source': source_fact_id,
                    'target': target_fact_id,
                    'type': str(relation.get('relation_type') or 'temporal_relation'),
                }
            )

        for index, candidate in enumerate(contradiction_candidates):
            if not isinstance(candidate, dict):
                continue
            contradiction_id = f"contradiction:{claim_entity_id}:{index}"
            entities.append(
                {
                    'id': contradiction_id,
                    'label': str(element.get('element_text') or claim_type),
                    'type': 'contradiction_candidate',
                }
            )
            relationships.append(
                {
                    'source': contradiction_id,
                    'target': claim_entity_id,
                    'type': 'contradicts',
                }
            )

        return {
            'entities': entities,
            'relationships': relationships,
            'claim_type': claim_type,
        }

    def _summarize_adapter_result(self, adapter_result: Dict[str, Any], count_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        return _summarize_adapter_result_payload(adapter_result, count_fields)

    def _run_element_reasoning_diagnostics(
        self,
        claim_type: str,
        element: Dict[str, Any],
        contradiction_candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return _run_element_reasoning_diagnostics(self, claim_type, element, contradiction_candidates)

    def _summarize_claim_reasoning_diagnostics(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary = _summarize_claim_reasoning_diagnostics_payload(elements)
        summary.setdefault('adapter_status_counts', {}).setdefault(
            'ontology_workflow',
            {},
        )
        return summary

    def _summarize_claim_validation_decisions(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        return _summarize_claim_validation_decisions_payload(elements)

    def _build_claim_validation(
        self,
        claim_type: str,
        claim_matrix: Dict[str, Any],
        gap_claim: Dict[str, Any],
        contradiction_claim: Dict[str, Any],
    ) -> Dict[str, Any]:
        contradiction_by_element: Dict[str, List[Dict[str, Any]]] = {}
        for candidate in contradiction_claim.get('candidates', []) or []:
            if not isinstance(candidate, dict):
                continue
            element_key = candidate.get('claim_element_id') or candidate.get('claim_element_text')
            if not element_key:
                continue
            contradiction_by_element.setdefault(str(element_key), []).append(candidate)

        gap_by_element: Dict[str, Dict[str, Any]] = {}
        for gap in gap_claim.get('unresolved_elements', []) or []:
            if not isinstance(gap, dict):
                continue
            element_key = gap.get('element_id') or gap.get('element_text')
            if element_key:
                gap_by_element[str(element_key)] = gap

        elements: List[Dict[str, Any]] = []
        validation_status_counts = {
            'supported': 0,
            'incomplete': 0,
            'missing': 0,
            'contradicted': 0,
        }
        claim_proof_gaps: List[Dict[str, Any]] = []
        elements_requiring_follow_up: List[str] = []

        for element in claim_matrix.get('elements', []) or []:
            if not isinstance(element, dict):
                continue
            element_key = element.get('element_id') or element.get('element_text') or ''
            contradiction_candidates = contradiction_by_element.get(str(element_key), [])
            if not contradiction_candidates and element.get('element_text'):
                contradiction_candidates = contradiction_by_element.get(str(element.get('element_text')), [])
            gap_element = gap_by_element.get(str(element_key), {})
            if not gap_element and element.get('element_text'):
                gap_element = gap_by_element.get(str(element.get('element_text')), {})

            proof_diagnostics = {
                'support_trace_count': int((element.get('support_trace_summary') or {}).get('trace_count', 0) or 0),
                'fact_trace_count': int((element.get('support_trace_summary') or {}).get('fact_trace_count', 0) or 0),
                'graph_traced_link_count': int(self._summarize_graph_traces(element.get('links', [])).get('traced_link_count', 0) or 0),
                'missing_support_kind_count': len(element.get('missing_support_kinds', []) or []),
                'contradiction_candidate_count': len(contradiction_candidates),
                'total_links': int(element.get('total_links', 0) or 0),
                'fact_count': int(element.get('fact_count', 0) or 0),
            }
            reasoning_diagnostics = self._run_element_reasoning_diagnostics(
                claim_type,
                element,
                contradiction_candidates,
            )
            if isinstance(reasoning_diagnostics, dict) and 'graphrag_quality_enforces_proof_gaps' not in reasoning_diagnostics:
                reasoning_diagnostics = {
                    **reasoning_diagnostics,
                    'graphrag_quality_enforces_proof_gaps': False,
                }
            decision_trace = self._build_validation_decision_trace(
                element,
                contradiction_candidates,
                reasoning_diagnostics,
            )
            validation_status = decision_trace.get('validation_status', 'missing')
            proof_gaps = self._proof_gaps_for_element(
                element,
                contradiction_candidates,
                reasoning_diagnostics,
            )
            recommended_action = self._recommended_validation_action(
                validation_status,
                element,
                proof_gaps=proof_gaps,
            )
            proof_diagnostics.update(
                {
                    'reasoning_backend_available_count': int(reasoning_diagnostics.get('backend_available_count', 0) or 0),
                    'reasoning_predicate_count': int(reasoning_diagnostics.get('predicate_count', 0) or 0),
                    'reasoning_ontology_entity_count': int(reasoning_diagnostics.get('ontology_entity_count', 0) or 0),
                    'reasoning_ontology_relationship_count': int(reasoning_diagnostics.get('ontology_relationship_count', 0) or 0),
                    'reasoning_adapter_statuses': reasoning_diagnostics.get('adapter_statuses', {}),
                    'decision_source': decision_trace.get('decision_source', ''),
                    'logic_contradiction_count': int(decision_trace.get('logic_contradiction_count', 0) or 0),
                    'logic_provable_count': int(decision_trace.get('logic_provable_count', 0) or 0),
                    'logic_unprovable_count': int(decision_trace.get('logic_unprovable_count', 0) or 0),
                    'ontology_validation_signal': decision_trace.get('ontology_validation_signal', 'unknown'),
                }
            )
            validation_status_counts[validation_status] += 1
            if validation_status != 'supported' and element.get('element_text'):
                elements_requiring_follow_up.append(element.get('element_text'))

            support_quality_summary = (
                element.get('support_quality_summary', {})
                if isinstance(element.get('support_quality_summary'), dict)
                else {}
            )
            temporal_proof_bundle = (
                reasoning_diagnostics.get('temporal_proof_bundle')
                if isinstance(reasoning_diagnostics.get('temporal_proof_bundle'), dict)
                else {}
            )
            claim_support_temporal_handoff = (
                reasoning_diagnostics.get('claim_support_temporal_handoff')
                if isinstance(reasoning_diagnostics.get('claim_support_temporal_handoff'), dict)
                else {}
            )
            temporal_next_actions = [
                dict(action)
                for action in (
                    temporal_proof_bundle.get('temporal_next_actions')
                    or claim_support_temporal_handoff.get('temporal_next_actions')
                    or []
                )
                if isinstance(action, dict)
            ]
            element_validation = {
                'element_id': element.get('element_id'),
                'element_text': element.get('element_text'),
                'coverage_status': element.get('status'),
                'validation_status': validation_status,
                'recommended_action': recommended_action,
                'missing_support_kinds': element.get('missing_support_kinds', []),
                'total_links': element.get('total_links', 0),
                'fact_count': element.get('fact_count', 0),
                'support_by_kind': element.get('support_by_kind', {}),
                'authority_treatment_summary': element.get('authority_treatment_summary', {}),
                'authority_rule_candidate_summary': element.get('authority_rule_candidate_summary', {}),
                'support_trace_summary': element.get('support_trace_summary', {}),
                'graph_trace_summary': self._summarize_graph_traces(element.get('links', [])),
                'support_quality_summary': support_quality_summary,
                'primary_quality_signal': self._primary_quality_signal_for_summary(support_quality_summary),
                'contradiction_candidate_count': len(contradiction_candidates),
                'contradiction_candidates': contradiction_candidates,
                'proof_gap_count': len(proof_gaps),
                'proof_gaps': proof_gaps,
                'proof_diagnostics': proof_diagnostics,
                'proof_decision_trace': decision_trace,
                'reasoning_diagnostics': reasoning_diagnostics,
                'temporal_next_actions': temporal_next_actions,
                'temporal_next_action_count': len(temporal_next_actions),
                'temporal_missingness_kind': 'temporal_gap' if temporal_next_actions else '',
                'gap_context': gap_element,
            }
            elements.append(element_validation)

            for proof_gap in proof_gaps:
                claim_proof_gaps.append(
                    {
                        'element_id': element.get('element_id'),
                        'element_text': element.get('element_text'),
                        'validation_status': validation_status,
                        'recommended_action': recommended_action,
                        **proof_gap,
                    }
                )

        if validation_status_counts['contradicted']:
            claim_validation_status = 'contradicted'
        elif claim_matrix.get('total_elements', 0) and validation_status_counts['supported'] == claim_matrix.get('total_elements', 0):
            claim_validation_status = 'supported'
        elif validation_status_counts['incomplete'] or validation_status_counts['supported']:
            claim_validation_status = 'incomplete'
        else:
            claim_validation_status = 'missing'

        graph_traced_link_count = sum(
            int((element.get('graph_trace_summary') or {}).get('traced_link_count', 0) or 0)
            for element in elements
            if isinstance(element, dict)
        )

        return {
            'claim_type': claim_type,
            'required_support_kinds': claim_matrix.get('required_support_kinds', []),
            'validation_status': claim_validation_status,
            'validation_status_counts': validation_status_counts,
            'total_elements': claim_matrix.get('total_elements', 0),
            'supported_element_count': validation_status_counts['supported'],
            'incomplete_element_count': validation_status_counts['incomplete'],
            'missing_element_count': validation_status_counts['missing'],
            'contradicted_element_count': validation_status_counts['contradicted'],
            'elements_requiring_follow_up': elements_requiring_follow_up,
            'unresolved_element_count': int(gap_claim.get('unresolved_count', 0) or 0),
            'contradiction_candidate_count': int(contradiction_claim.get('candidate_count', 0) or 0),
            'proof_gap_count': len(claim_proof_gaps),
            'proof_gaps': claim_proof_gaps,
            'proof_diagnostics': {
                'support_trace_count': int((claim_matrix.get('support_trace_summary') or {}).get('trace_count', 0) or 0),
                'fact_trace_count': int((claim_matrix.get('support_trace_summary') or {}).get('fact_trace_count', 0) or 0),
                'total_links': int(claim_matrix.get('total_links', 0) or 0),
                'total_facts': int(claim_matrix.get('total_facts', 0) or 0),
                'graph_traced_link_count': graph_traced_link_count,
                'reasoning': self._summarize_claim_reasoning_diagnostics(elements),
                'decision': self._summarize_claim_validation_decisions(elements),
            },
            'support_quality_summary': dict(claim_matrix.get('support_quality_summary') or {}),
            'elements': elements,
        }

    def _fact_polarity(self, text: Optional[str]) -> str:
        lowered = str(text or '').lower()
        negative_markers = (
            ' did not ',
            " didn't ",
            ' was not ',
            " wasn't ",
            ' never ',
            ' denied ',
            ' deny ',
            ' refused ',
            ' refuse ',
            ' without ',
            ' no ',
            ' not ',
            ' lack ',
            ' lacked ',
            ' absent ',
        )
        padded = f' {lowered} '
        if any(marker in padded for marker in negative_markers):
            return 'negative'
        return 'affirmative'

    def _fact_overlap_terms(self, left: Optional[str], right: Optional[str]) -> List[str]:
        excluded = {
            'employee', 'employees', 'employer', 'employers', 'person', 'people',
            'claim', 'claims', 'fact', 'facts', 'evidence', 'authority', 'there',
            'their', 'them', 'they', 'then', 'when', 'with', 'without', 'against',
            'about', 'from', 'into', 'after', 'before', 'because', 'that', 'this',
            'was', 'were', 'did', 'does', 'have', 'has', 'had', 'been', 'being',
            'not', 'never', 'denied', 'deny', 'refused', 'refuse', 'lack', 'lacked',
            'absent',
        }
        left_terms = {term for term in self._tokenize_text(left) if term not in excluded}
        right_terms = {term for term in self._tokenize_text(right) if term not in excluded}
        return sorted(left_terms & right_terms)

    def _normalize_required_support_kinds(
        self,
        required_support_kinds: Optional[List[str]],
    ) -> List[str]:
        kinds = required_support_kinds or []
        normalized = []
        seen = set()
        for kind in kinds:
            normalized_kind = str(kind or '').strip()
            if not normalized_kind or normalized_kind in seen:
                continue
            seen.add(normalized_kind)
            normalized.append(normalized_kind)
        return sorted(normalized)

    def _normalize_snapshot_retention_limit(
        self,
        retention_limit: Optional[int],
        *,
        default: int = 3,
    ) -> int:
        try:
            normalized = int(retention_limit)
        except (TypeError, ValueError):
            normalized = default
        return max(1, normalized)

    def _summarize_coverage_matrix_for_snapshot(self, claim_matrix: Dict[str, Any]) -> Dict[str, Any]:
        """Build compact metadata for a persisted coverage-matrix payload."""
        elements = [
            element
            for element in (claim_matrix.get('elements', []) or [])
            if isinstance(element, dict)
        ]
        graph_snapshot_ref_count = sum(
            len(element.get('graph_snapshot_refs', []) or [])
            for element in elements
        )
        support_path_count = 0
        current_trace_path_count = 0
        persisted_path_count = 0
        graph_linked_path_count = 0
        support_ref_count = 0
        unique_support_refs: set = set()
        path_kind_counts: Dict[str, int] = {}
        for element in elements:
            path_summary = element.get('support_path_summary', {})
            if not isinstance(path_summary, dict):
                continue
            paths = [
                path
                for path in (path_summary.get('paths', []) or [])
                if isinstance(path, dict)
            ]
            support_path_count += int(path_summary.get('path_count', len(paths)) or 0)
            for path in paths:
                if path.get('source') == 'current_traces':
                    current_trace_path_count += 1
                if path.get('source') == 'persisted' or path.get('persisted'):
                    persisted_path_count += 1
                path_kind = str(path.get('path_kind') or 'support').strip() or 'support'
                path_kind_counts[path_kind] = path_kind_counts.get(path_kind, 0) + 1
                graph_ids = path.get('graph_ids') if isinstance(path.get('graph_ids'), list) else []
                graph_id_count = int(path.get('graph_id_count', len(graph_ids)) or 0)
                if graph_id_count:
                    graph_linked_path_count += 1
                support_refs = path.get('support_refs') if isinstance(path.get('support_refs'), list) else []
                if support_refs:
                    support_ref_count += len(support_refs)
                    unique_support_refs.update(
                        normalized_ref
                        for ref in support_refs
                        for normalized_ref in [str(ref or '').strip()]
                        if normalized_ref
                    )

        return {
            'claim_type': claim_matrix.get('claim_type', ''),
            'element_count': len(elements),
            'status_counts': dict(claim_matrix.get('status_counts') or {}),
            'support_by_kind': dict(claim_matrix.get('support_by_kind') or {}),
            'total_links': int(claim_matrix.get('total_links', 0) or 0),
            'total_facts': int(claim_matrix.get('total_facts', 0) or 0),
            'graph_snapshot_ref_count': graph_snapshot_ref_count,
            'support_path_count': support_path_count,
            'current_trace_path_count': current_trace_path_count,
            'persisted_path_count': persisted_path_count,
            'graph_linked_path_count': graph_linked_path_count,
            'support_ref_count': support_ref_count,
            'unique_support_ref_count': len(unique_support_refs),
            'path_kind_counts': path_kind_counts,
            'support_quality_summary': dict(claim_matrix.get('support_quality_summary') or {}),
        }

    def _prune_snapshot_history(
        self,
        *,
        user_id: str,
        claim_type: str,
        snapshot_kind: str,
        required_support_kinds: Optional[List[str]] = None,
        keep_latest: int = 3,
    ) -> Dict[str, Any]:
        normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
        normalized_keep_latest = self._normalize_snapshot_retention_limit(keep_latest)
        if not DUCKDB_AVAILABLE:
            return {
                'pruned_snapshot_count': 0,
                'deleted_snapshot_ids': [],
                'retention_limit': normalized_keep_latest,
            }

        required_kinds_json = json.dumps(normalized_kinds, default=str)
        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                """
                SELECT id
                FROM claim_support_snapshot
                WHERE user_id = ?
                  AND claim_type = ?
                  AND snapshot_kind = ?
                  AND required_support_kinds = ?
                ORDER BY timestamp DESC, id DESC
                """,
                [user_id, claim_type, snapshot_kind, required_kinds_json],
            ).fetchall()
            deleted_snapshot_ids = [row[0] for row in rows[normalized_keep_latest:]]
            if deleted_snapshot_ids:
                conn.execute(
                    "DELETE FROM claim_support_snapshot WHERE id IN (SELECT UNNEST(?))",
                    [deleted_snapshot_ids],
                )
            conn.close()
            return {
                'pruned_snapshot_count': len(deleted_snapshot_ids),
                'deleted_snapshot_ids': deleted_snapshot_ids,
                'retention_limit': normalized_keep_latest,
            }
        except Exception as exc:
            self.mediator.log(
                'claim_support_snapshot_prune_error',
                error=str(exc),
                claim_type=claim_type,
                snapshot_kind=snapshot_kind,
            )
            return {
                'pruned_snapshot_count': 0,
                'deleted_snapshot_ids': [],
                'retention_limit': normalized_keep_latest,
                'error': str(exc),
            }

    def _build_claim_support_state_token(
        self,
        user_id: str,
        claim_type: str,
        required_support_kinds: Optional[List[str]] = None,
    ) -> str:
        normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
        requirements = self.get_claim_requirements(user_id, claim_type).get(claim_type, [])
        links = [
            self._enrich_support_link(link)
            for link in self.get_support_links(user_id, claim_type)
        ]
        facts = self.get_claim_support_facts(user_id, claim_type)

        requirement_rows = [
            {
                'element_id': item.get('element_id'),
                'element_text': item.get('element_text'),
                'element_index': item.get('element_index'),
            }
            for item in requirements
            if isinstance(item, dict)
        ]
        link_rows = [
            {
                'id': link.get('id'),
                'claim_element_id': link.get('claim_element_id'),
                'claim_element_text': link.get('claim_element_text'),
                'support_kind': link.get('support_kind'),
                'support_ref': link.get('support_ref'),
                'source_table': link.get('source_table'),
                'fact_count': link.get('fact_count', 0),
                'graph_summary': link.get('graph_summary', {}),
                'graph_trace_summary': self._summarize_graph_traces([link]),
            }
            for link in links
            if isinstance(link, dict)
        ]
        fact_rows = [
            {
                'fact_id': fact.get('fact_id'),
                'text': fact.get('text'),
                'claim_element_id': fact.get('claim_element_id'),
                'claim_element_text': fact.get('claim_element_text'),
                'support_kind': fact.get('support_kind'),
                'support_ref': fact.get('support_ref'),
                'source_table': fact.get('source_table'),
            }
            for fact in facts
            if isinstance(fact, dict)
        ]
        payload = {
            'claim_type': claim_type,
            'required_support_kinds': normalized_kinds,
            'requirements': sorted(
                requirement_rows,
                key=lambda item: (
                    str(item.get('element_index') or ''),
                    str(item.get('element_id') or ''),
                    str(item.get('element_text') or ''),
                ),
            ),
            'links': sorted(
                link_rows,
                key=lambda item: (
                    str(item.get('id') or ''),
                    str(item.get('claim_element_id') or ''),
                    str(item.get('support_kind') or ''),
                    str(item.get('support_ref') or ''),
                ),
            ),
            'facts': sorted(
                fact_rows,
                key=lambda item: (
                    str(item.get('fact_id') or ''),
                    str(item.get('claim_element_id') or ''),
                    str(item.get('support_kind') or ''),
                    str(item.get('support_ref') or ''),
                    str(item.get('text') or ''),
                ),
            ),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode('utf-8')
        ).hexdigest()

    def _normalize_query_text(self, query_text: str) -> str:
        return ' '.join((query_text or '').strip().lower().split())

    def _hash_query_text(self, query_text: str) -> str:
        normalized = self._normalize_query_text(query_text)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def resolve_claim_element(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
        support_label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[str]]:
        requirements = self.get_claim_requirements(user_id, claim_type).get(claim_type, [])
        if not requirements:
            return {
                'claim_element_id': claim_element_id,
                'claim_element_text': claim_element_text,
            }

        normalized_element_id = str(claim_element_id or '').strip()
        if normalized_element_id:
            for requirement in requirements:
                if str(requirement.get('element_id') or '').strip() == normalized_element_id:
                    return {
                        'claim_element_id': requirement['element_id'],
                        'claim_element_text': requirement['element_text'],
                    }

        if claim_element_text:
            normalized_input = ' '.join(self._tokenize_text(claim_element_text))
            for requirement in requirements:
                normalized_requirement = ' '.join(self._tokenize_text(requirement['element_text']))
                if normalized_input and normalized_input == normalized_requirement:
                    return {
                        'claim_element_id': requirement['element_id'],
                        'claim_element_text': requirement['element_text'],
                    }

        match_text = self._extract_match_text(support_label, metadata)
        match_tokens = set(self._tokenize_text(match_text))
        if not match_tokens:
            return {
                'claim_element_id': claim_element_id,
                'claim_element_text': claim_element_text,
            }

        best_requirement: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for requirement in requirements:
            requirement_tokens = set(self._tokenize_text(requirement['element_text']))
            if not requirement_tokens:
                continue
            overlap = match_tokens & requirement_tokens
            score = len(overlap) / len(requirement_tokens)
            if score > best_score:
                best_score = score
                best_requirement = requirement

        if best_requirement and best_score >= 0.3:
            return {
                'claim_element_id': best_requirement['element_id'],
                'claim_element_text': best_requirement['element_text'],
            }

        return {
            'claim_element_id': claim_element_id,
            'claim_element_text': claim_element_text,
        }

    def register_claim_requirements(
        self,
        user_id: str,
        requirements: Dict[str, List[str]],
        complaint_id: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        requirement_metadata = _merge_intake_summary_handoff_metadata(
            {},
            self.mediator,
        )
        if not DUCKDB_AVAILABLE:
            registered: Dict[str, List[Dict[str, Any]]] = {}
            for claim_type, elements in requirements.items():
                rows: List[Dict[str, Any]] = []
                for element_index, element_text in enumerate(elements, start=1):
                    rows.append(
                        {
                            'complaint_id': complaint_id,
                            'claim_type': claim_type,
                            'element_id': self._make_element_id(claim_type, element_index),
                            'element_index': element_index,
                            'element_text': element_text,
                            'metadata': requirement_metadata,
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                        }
                    )
                self._memory_requirements[f'{user_id}:{claim_type}'] = rows
                registered[claim_type] = rows
            return registered

        registered: Dict[str, List[Dict[str, Any]]] = {}
        try:
            conn = duckdb.connect(self.db_path)
            for claim_type, elements in requirements.items():
                conn.execute(
                    "DELETE FROM claim_requirements WHERE user_id = ? AND claim_type = ?",
                    [user_id, claim_type],
                )
                registered[claim_type] = []
                for element_index, element_text in enumerate(elements, start=1):
                    element_id = self._make_element_id(claim_type, element_index)
                    conn.execute(
                        """
                        INSERT INTO claim_requirements (
                            user_id, complaint_id, claim_type, element_id,
                            element_index, element_text, metadata
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            user_id,
                            complaint_id,
                            claim_type,
                            element_id,
                            element_index,
                            element_text,
                            json.dumps(requirement_metadata),
                        ],
                    )
                    registered[claim_type].append(
                        {
                            'claim_type': claim_type,
                            'element_id': element_id,
                            'element_index': element_index,
                            'element_text': element_text,
                        }
                    )
            conn.close()
            self.mediator.log('claim_requirements_registered', claims=list(registered.keys()))
            return registered
        except Exception as exc:
            self.mediator.log('claim_requirements_registration_error', error=str(exc))
            return {}

    def get_claim_requirements(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not DUCKDB_AVAILABLE:
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for key, rows in self._memory_requirements.items():
                key_user_id, _, key_claim_type = key.partition(':')
                if key_user_id != str(user_id):
                    continue
                if claim_type and key_claim_type != str(claim_type):
                    continue
                grouped[key_claim_type] = [dict(row) for row in rows]
            return grouped

        try:
            conn = duckdb.connect(self.db_path)
            if claim_type:
                rows = conn.execute(
                    """
                    SELECT complaint_id, claim_type, element_id, element_index, element_text, metadata, timestamp
                    FROM claim_requirements
                    WHERE user_id = ? AND claim_type = ?
                    ORDER BY element_index ASC
                    """,
                    [user_id, claim_type],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT complaint_id, claim_type, element_id, element_index, element_text, metadata, timestamp
                    FROM claim_requirements
                    WHERE user_id = ?
                    ORDER BY claim_type ASC, element_index ASC
                    """,
                    [user_id],
                ).fetchall()
            conn.close()

            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(row[1], []).append(
                    {
                        'complaint_id': row[0],
                        'claim_type': row[1],
                        'element_id': row[2],
                        'element_index': row[3],
                        'element_text': row[4],
                        'metadata': json.loads(row[5]) if row[5] else {},
                        'timestamp': row[6],
                    }
                )
            return grouped
        except Exception as exc:
            self.mediator.log('claim_requirements_query_error', error=str(exc))
            return {}

    def add_support_link(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
        support_kind: str,
        support_ref: str,
        support_label: Optional[str] = None,
        source_table: Optional[str] = None,
        support_strength: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        complaint_id: Optional[str] = None,
    ) -> int:
        result = self.upsert_support_link(
            user_id=user_id,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            claim_element_text=claim_element_text,
            support_kind=support_kind,
            support_ref=support_ref,
            support_label=support_label,
            source_table=source_table,
            support_strength=support_strength,
            metadata=metadata,
            complaint_id=complaint_id,
        )
        return result['record_id']

    def upsert_support_link(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
        support_kind: str,
        support_ref: str,
        support_label: Optional[str] = None,
        source_table: Optional[str] = None,
        support_strength: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        complaint_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not DUCKDB_AVAILABLE:
            normalized_metadata = _merge_intake_summary_handoff_metadata(
                metadata,
                self.mediator,
            )
            resolved_element = self.resolve_claim_element(
                user_id,
                claim_type,
                claim_element_text=claim_element_text,
                support_label=support_label,
                metadata=normalized_metadata,
            )
            claim_element_id = claim_element_id or resolved_element['claim_element_id']
            claim_element_text = claim_element_text or resolved_element['claim_element_text']
            existing = next(
                (
                    link for link in self._memory_support_links
                    if str(link.get('user_id') or '') == str(user_id)
                    and str(link.get('claim_type') or '') == str(claim_type)
                    and str(link.get('support_kind') or '') == str(support_kind)
                    and str(link.get('support_ref') or '') == str(support_ref)
                    and str(link.get('claim_element_id') or '') == str(claim_element_id or '')
                    and str(link.get('claim_element_text') or '') == str(claim_element_text or '')
                ),
                None,
            )
            if existing is not None:
                return {'record_id': int(existing.get('id') or -1), 'created': False, 'reused': True}
            record_id = len(self._memory_support_links) + 1
            self._memory_support_links.append(
                {
                    'id': record_id,
                    'user_id': user_id,
                    'complaint_id': complaint_id,
                    'claim_type': claim_type,
                    'claim_element_id': claim_element_id,
                    'claim_element_text': claim_element_text,
                    'support_kind': support_kind,
                    'support_ref': support_ref,
                    'support_label': support_label,
                    'source_table': source_table,
                    'support_strength': support_strength,
                    'metadata': normalized_metadata or {},
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }
            )
            return {'record_id': record_id, 'created': True, 'reused': False}

        normalized_metadata = _merge_intake_summary_handoff_metadata(
            metadata,
            self.mediator,
        )

        resolved_element = self.resolve_claim_element(
            user_id,
            claim_type,
            claim_element_text=claim_element_text,
            support_label=support_label,
            metadata=normalized_metadata,
        )
        claim_element_id = claim_element_id or resolved_element['claim_element_id']
        claim_element_text = claim_element_text or resolved_element['claim_element_text']

        try:
            conn = duckdb.connect(self.db_path)
            if claim_element_id:
                existing = conn.execute(
                    """
                    SELECT id
                    FROM claim_support
                    WHERE user_id = ?
                      AND claim_type = ?
                      AND support_kind = ?
                      AND support_ref = ?
                      AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    [user_id, claim_type, support_kind, support_ref, claim_element_id],
                ).fetchone()
            else:
                existing = conn.execute(
                    """
                    SELECT id
                    FROM claim_support
                    WHERE user_id = ?
                      AND claim_type = ?
                      AND support_kind = ?
                      AND support_ref = ?
                      AND COALESCE(claim_element_text, '') = COALESCE(?, '')
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    [user_id, claim_type, support_kind, support_ref, claim_element_text],
                ).fetchone()
            if existing:
                conn.close()
                record_id = existing[0]
                self.mediator.log(
                    'claim_support_link_duplicate',
                    record_id=record_id,
                    claim_type=claim_type,
                    claim_element_id=claim_element_id,
                    support_kind=support_kind,
                    support_ref=support_ref,
                )
                return {'record_id': record_id, 'created': False, 'reused': True}

            result = conn.execute(
                """
                INSERT INTO claim_support (
                    user_id, complaint_id, claim_type, claim_element_id, claim_element_text, support_kind,
                    support_ref, support_label, source_table, support_strength, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                [
                    user_id,
                    complaint_id,
                    claim_type,
                    claim_element_id,
                    self._seal_column(claim_element_text, 'claim_element_text'),
                    support_kind,
                    support_ref,
                    self._seal_column(support_label, 'support_label'),
                    source_table,
                    support_strength,
                    self._seal_json(normalized_metadata or {}),
                ],
            ).fetchone()
            conn.close()
            record_id = result[0]
            self.mediator.log(
                'claim_support_link_added',
                record_id=record_id,
                claim_type=claim_type,
                claim_element_id=claim_element_id,
                support_kind=support_kind,
                support_ref=support_ref,
            )
            return {'record_id': record_id, 'created': True, 'reused': False}
        except Exception as exc:
            self.mediator.log('claim_support_link_error', error=str(exc))
            raise Exception(f'Failed to add claim support link: {str(exc)}')

    def get_support_links(self, user_id: str, claim_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if not DUCKDB_AVAILABLE:
            return [
                {
                    'id': link.get('id'),
                    'complaint_id': link.get('complaint_id'),
                    'claim_type': link.get('claim_type'),
                    'claim_element_id': link.get('claim_element_id'),
                    'claim_element_text': link.get('claim_element_text'),
                    'support_kind': link.get('support_kind'),
                    'support_ref': link.get('support_ref'),
                    'support_label': link.get('support_label'),
                    'source_table': link.get('source_table'),
                    'support_strength': link.get('support_strength'),
                    'metadata': dict(link.get('metadata') or {}),
                    'timestamp': link.get('timestamp'),
                }
                for link in self._memory_support_links
                if str(link.get('user_id') or '') == str(user_id)
                and (not claim_type or str(link.get('claim_type') or '') == str(claim_type))
            ]

        try:
            conn = duckdb.connect(self.db_path)
            if claim_type:
                results = conn.execute(
                    """
                      SELECT id, complaint_id, claim_type, claim_element_id, claim_element_text,
                          support_kind, support_ref, support_label, source_table,
                          support_strength, metadata, timestamp
                    FROM claim_support
                    WHERE user_id = ? AND claim_type = ?
                    ORDER BY timestamp DESC
                    """,
                    [user_id, claim_type],
                ).fetchall()
            else:
                results = conn.execute(
                    """
                      SELECT id, complaint_id, claim_type, claim_element_id, claim_element_text,
                          support_kind, support_ref, support_label, source_table,
                          support_strength, metadata, timestamp
                    FROM claim_support
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    """,
                    [user_id],
                ).fetchall()
            conn.close()
            return [
                {
                    'id': row[0],
                    'complaint_id': row[1],
                    'claim_type': row[2],
                    'claim_element_id': row[3],
                    'claim_element_text': row[4],
                    'support_kind': row[5],
                    'support_ref': row[6],
                    'support_label': row[7],
                    'source_table': row[8],
                    'support_strength': row[9],
                    'metadata': json.loads(row[10]) if row[10] else {},
                    'timestamp': row[11],
                }
                for row in results
            ]
        except Exception as exc:
            self.mediator.log('claim_support_query_error', error=str(exc))
            return []

    def _enrich_support_link(self, link: Dict[str, Any]) -> Dict[str, Any]:
        """Attach evidence or authority fact details to support links when available."""
        enriched = dict(link)
        enriched.setdefault('fact_count', 0)

        if enriched.get('source_table') == 'legal_authorities':
            authority_storage = getattr(self.mediator, 'legal_authority_storage', None)
            authority_record_id = (enriched.get('metadata') or {}).get('record_id')
            if authority_storage is None:
                return enriched

            authority_record = None
            if authority_record_id is not None and hasattr(authority_storage, 'get_authority_by_id'):
                try:
                    authority_record = authority_storage.get_authority_by_id(authority_record_id)
                except Exception as exc:
                    self.mediator.log('claim_support_authority_lookup_error', error=str(exc), authority_id=authority_record_id)
                    authority_record = None

            if not authority_record and hasattr(authority_storage, 'get_authority_by_citation'):
                try:
                    authority_record = authority_storage.get_authority_by_citation(enriched.get('support_ref'))
                except Exception as exc:
                    self.mediator.log('claim_support_authority_citation_lookup_error', error=str(exc), citation=enriched.get('support_ref'))
                    authority_record = None

            if not authority_record:
                return enriched
            if not isinstance(authority_record, dict):
                return enriched

            enriched['authority_record_id'] = authority_record.get('id')
            authority_fact_count = authority_record.get('fact_count', 0)
            enriched['fact_count'] = authority_fact_count if isinstance(authority_fact_count, (int, float)) else 0
            authority_graph_metadata = authority_record.get('graph_metadata', {}) if isinstance(authority_record.get('graph_metadata'), dict) else {}
            enriched['record_summary'] = {
                'id': authority_record.get('id'),
                'citation': authority_record.get('citation'),
                'title': authority_record.get('title'),
                'url': authority_record.get('url'),
                'parse_status': authority_record.get('parse_status'),
                'chunk_count': authority_record.get('chunk_count', 0),
                'graph_status': authority_record.get('graph_status'),
                'graph_entity_count': authority_record.get('graph_entity_count', 0),
                'graph_relationship_count': authority_record.get('graph_relationship_count', 0),
                'parse_summary': self._extract_record_parse_summary(authority_record),
                'treatment_summary': authority_record.get('treatment_summary', {}),
                'citation_history_summary': authority_record.get('citation_history_summary', {}),
                'rule_candidate_summary': authority_record.get('rule_candidate_summary', {}),
                'search_program_summary': authority_record.get('search_program_summary', {}),
                'search_program_count': int(
                    (authority_record.get('search_program_summary') or {}).get('record_count', 0)
                    if isinstance(authority_record.get('search_program_summary'), dict)
                    else len(authority_record.get('metadata', {}).get('search_programs', []) or [])
                    if isinstance(authority_record.get('metadata'), dict)
                    else 0
                ),
            }
            enriched['search_programs'] = authority_record.get('search_programs', [])
            enriched['search_program_summary'] = authority_record.get('search_program_summary', {})
            enriched['treatment_records'] = authority_record.get('treatment_records', [])
            enriched['treatment_summary'] = authority_record.get('treatment_summary', {})
            enriched['citation_history_summary'] = authority_record.get('citation_history_summary', {})
            enriched['rule_candidates'] = authority_record.get('rule_candidates', [])
            enriched['rule_candidate_summary'] = authority_record.get('rule_candidate_summary', {})

            if hasattr(authority_storage, 'get_authority_facts') and authority_record.get('id') is not None:
                try:
                    enriched['facts'] = authority_storage.get_authority_facts(authority_record['id'])
                except Exception as exc:
                    self.mediator.log('claim_support_authority_facts_error', error=str(exc), authority_id=authority_record.get('id'))
                    enriched['facts'] = []
            else:
                enriched['facts'] = []

            if hasattr(authority_storage, 'get_authority_graph') and authority_record.get('id') is not None:
                try:
                    authority_graph = authority_storage.get_authority_graph(authority_record['id'])
                except Exception as exc:
                    self.mediator.log('claim_support_authority_graph_error', error=str(exc), authority_id=authority_record.get('id'))
                    authority_graph = {'status': 'error', 'entities': [], 'relationships': []}
                if not isinstance(authority_graph, dict):
                    authority_graph = {'status': '', 'entities': [], 'relationships': []}
                enriched['graph_summary'] = self._normalize_graph_summary(graph_payload=authority_graph)
            else:
                enriched['graph_summary'] = self._normalize_graph_summary(
                    default_status=authority_record.get('graph_status', ''),
                    default_entity_count=authority_record.get('graph_entity_count', 0) or 0,
                    default_relationship_count=authority_record.get('graph_relationship_count', 0) or 0,
                )
            enriched['graph_trace'] = self._build_graph_trace(
                source_table=enriched.get('source_table'),
                support_ref=enriched.get('support_ref'),
                record_id=authority_record.get('id'),
                graph_summary=enriched['graph_summary'],
                graph_metadata=authority_graph_metadata,
            )
            return enriched

        if enriched.get('source_table') != 'evidence':
            return enriched

        evidence_state = getattr(self.mediator, 'evidence_state', None)
        if evidence_state is None or not hasattr(evidence_state, 'get_evidence_by_cid'):
            return enriched

        try:
            evidence_record = evidence_state.get_evidence_by_cid(enriched.get('support_ref'))
        except Exception as exc:
            self.mediator.log('claim_support_evidence_lookup_error', error=str(exc), support_ref=enriched.get('support_ref'))
            return enriched

        if not evidence_record:
            return enriched
        if not isinstance(evidence_record, dict):
            return enriched

        enriched['evidence_record_id'] = evidence_record.get('id')
        evidence_fact_count = evidence_record.get('fact_count', 0)
        enriched['fact_count'] = evidence_fact_count if isinstance(evidence_fact_count, (int, float)) else 0
        evidence_graph_metadata = evidence_record.get('graph_metadata', {}) if isinstance(evidence_record.get('graph_metadata'), dict) else {}
        enriched['record_summary'] = {
            'id': evidence_record.get('id'),
            'cid': evidence_record.get('cid'),
            'type': evidence_record.get('type'),
            'source_url': evidence_record.get('source_url'),
            'parse_status': evidence_record.get('parse_status'),
            'chunk_count': evidence_record.get('chunk_count', 0),
            'graph_status': evidence_record.get('graph_status'),
            'graph_entity_count': evidence_record.get('graph_entity_count', 0),
            'graph_relationship_count': evidence_record.get('graph_relationship_count', 0),
            'parse_summary': self._extract_record_parse_summary(evidence_record),
        }

        if hasattr(evidence_state, 'get_evidence_facts') and evidence_record.get('id') is not None:
            try:
                enriched['facts'] = evidence_state.get_evidence_facts(evidence_record['id'])
            except Exception as exc:
                self.mediator.log('claim_support_evidence_facts_error', error=str(exc), evidence_id=evidence_record.get('id'))
                enriched['facts'] = []
        else:
            enriched['facts'] = []

        if hasattr(evidence_state, 'get_evidence_graph') and evidence_record.get('id') is not None:
            try:
                evidence_graph = evidence_state.get_evidence_graph(evidence_record['id'])
            except Exception as exc:
                self.mediator.log('claim_support_evidence_graph_error', error=str(exc), evidence_id=evidence_record.get('id'))
                evidence_graph = {'status': 'error', 'entities': [], 'relationships': []}
            if not isinstance(evidence_graph, dict):
                evidence_graph = {'status': '', 'entities': [], 'relationships': []}
            enriched['graph_summary'] = self._normalize_graph_summary(graph_payload=evidence_graph)
        else:
            enriched['graph_summary'] = self._normalize_graph_summary(
                default_status=evidence_record.get('graph_status', ''),
                default_entity_count=evidence_record.get('graph_entity_count', 0) or 0,
                default_relationship_count=evidence_record.get('graph_relationship_count', 0) or 0,
            )
        enriched['graph_trace'] = self._build_graph_trace(
            source_table=enriched.get('source_table'),
            support_ref=enriched.get('support_ref'),
            record_id=evidence_record.get('id'),
            graph_summary=enriched['graph_summary'],
            graph_metadata=evidence_graph_metadata,
        )

        return enriched

    def _coverage_status_for_element(
        self,
        element: Dict[str, Any],
        required_support_kinds: List[str],
    ) -> str:
        kinds_present = set(element.get('support_by_kind', {}).keys())
        if element.get('total_links', 0) == 0:
            return 'missing'
        if all(kind in kinds_present for kind in required_support_kinds):
            return 'covered'
        return 'partially_supported'

    def summarize_claim_support(self, user_id: str, claim_type: Optional[str] = None) -> Dict[str, Any]:
        links = self._get_enriched_claim_support_links(user_id, claim_type)
        requirements = self.get_claim_requirements(user_id, claim_type)
        if claim_type:
            grouped = {claim_type: links}
        else:
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for link in links:
                grouped.setdefault(link['claim_type'], []).append(link)
            for requirement_claim in requirements.keys():
                grouped.setdefault(requirement_claim, [])

        summary: Dict[str, Any] = {
            'available': DUCKDB_AVAILABLE,
            'total_links': len(links),
            'claims': {},
        }
        for current_claim, claim_links in grouped.items():
            support_by_kind: Dict[str, int] = {}
            total_facts = 0
            for link in claim_links:
                support_by_kind[link['support_kind']] = support_by_kind.get(link['support_kind'], 0) + 1
                total_facts += int(link.get('fact_count', 0) or 0)

            claim_requirements = requirements.get(current_claim, [])
            links_by_element: Dict[str, List[Dict[str, Any]]] = {}
            unassigned_links: List[Dict[str, Any]] = []
            for link in claim_links:
                element_key = link.get('claim_element_id') or link.get('claim_element_text')
                if element_key:
                    links_by_element.setdefault(element_key, []).append(link)
                else:
                    unassigned_links.append(link)

            element_summaries: List[Dict[str, Any]] = []
            covered_elements = 0
            for requirement in claim_requirements:
                requirement_links = links_by_element.get(requirement['element_id'], [])
                if not requirement_links:
                    requirement_links = links_by_element.get(requirement['element_text'], [])

                element_support_by_kind: Dict[str, int] = {}
                for link in requirement_links:
                    element_support_by_kind[link['support_kind']] = (
                        element_support_by_kind.get(link['support_kind'], 0) + 1
                    )
                element_fact_count = sum(int(link.get('fact_count', 0) or 0) for link in requirement_links)
                if requirement_links:
                    covered_elements += 1
                authority_treatment_summary = self._summarize_authority_treatment_signals(requirement_links)
                authority_rule_candidate_summary = self._summarize_authority_rule_candidates(requirement_links)
                element_summaries.append(
                    {
                        **requirement,
                        'total_links': len(requirement_links),
                        'fact_count': element_fact_count,
                        'support_by_kind': element_support_by_kind,
                        'testimony_backed_count': element_support_by_kind.get('testimony', 0),
                        'authority_treatment_summary': authority_treatment_summary,
                        'authority_rule_candidate_summary': authority_rule_candidate_summary,
                        'links': requirement_links,
                    }
                )

            testimony_backed_links = sum(1 for link in claim_links if link.get('support_kind') == 'testimony')
            testimony_backed_elements = sum(
                1
                for req in claim_requirements
                for link in links_by_element.get(req['element_id'], links_by_element.get(req['element_text'], []))
                if link.get('support_kind') == 'testimony'
            )
            summary['claims'][current_claim] = {
                'total_links': len(claim_links),
                'total_facts': total_facts,
                'support_by_kind': support_by_kind,
                'testimony_backed_count': testimony_backed_links,
                'testimony_backed_elements': testimony_backed_elements,
                'total_elements': len(claim_requirements),
                'covered_elements': covered_elements,
                'uncovered_elements': max(len(claim_requirements) - covered_elements, 0),
                'authority_treatment_summary': self._summarize_authority_treatment_signals(claim_links),
                'authority_rule_candidate_summary': self._summarize_authority_rule_candidates(claim_links),
                'elements': element_summaries,
                'unassigned_links': unassigned_links,
                'links': claim_links,
            }
        return summary

    def get_claim_support_facts(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        facts: List[Dict[str, Any]] = []
        links = self._get_enriched_claim_support_links(user_id, claim_type)

        for link in links:
            if claim_element_id and link.get('claim_element_id') != claim_element_id:
                continue
            if claim_element_text and link.get('claim_element_text') != claim_element_text:
                continue

            for fact in link.get('facts', []) or []:
                facts.append(self._normalize_support_fact(fact, link))

        return facts

    def get_claim_fact_registry_summary(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return compact corpus/source counts for normalized claim-support facts."""
        facts = self.get_claim_support_facts(
            user_id,
            claim_type,
            claim_element_id=claim_element_id,
            claim_element_text=claim_element_text,
        )
        return {
            **self._summarize_fact_registry(facts),
            'claim_type': claim_type,
            'claim_element_id': claim_element_id or '',
            'claim_element_text': claim_element_text or '',
        }

    def get_claim_support_traces(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        links = self._get_enriched_claim_support_links(user_id, claim_type)
        filtered_links: List[Dict[str, Any]] = []
        for link in links:
            if claim_element_id and link.get('claim_element_id') != claim_element_id:
                continue
            if claim_element_text and link.get('claim_element_text') != claim_element_text:
                continue
            filtered_links.append(link)
        return self._collect_support_traces_from_links(filtered_links)

    def get_claim_element_summary(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        requirements = self.get_claim_requirements(user_id, claim_type).get(claim_type, [])
        resolved = self.resolve_claim_element(
            user_id,
            claim_type,
            claim_element_text=claim_element_text,
            metadata={'claim_element_text': claim_element_text} if claim_element_text else None,
        )
        target_element_id = claim_element_id or resolved.get('claim_element_id')
        target_element_text = claim_element_text or resolved.get('claim_element_text')

        requirement = None
        for item in requirements:
            if target_element_id and item['element_id'] == target_element_id:
                requirement = item
                break
            if target_element_text and item['element_text'] == target_element_text:
                requirement = item
                break

        summary = self.summarize_claim_support(user_id, claim_type)
        claim_summary = summary.get('claims', {}).get(claim_type, {})
        for element_summary in claim_summary.get('elements', []):
            if requirement and element_summary.get('element_id') == requirement.get('element_id'):
                return element_summary
            if target_element_text and element_summary.get('element_text') == target_element_text:
                return element_summary

        if requirement:
            return {
                **requirement,
                'total_links': 0,
                'fact_count': 0,
                'support_by_kind': {},
                'authority_treatment_summary': {},
                'authority_rule_candidate_summary': {},
                'links': [],
            }

        return {
            'element_id': target_element_id,
            'element_text': target_element_text,
            'total_links': 0,
            'fact_count': 0,
            'support_by_kind': {},
            'authority_treatment_summary': {},
            'authority_rule_candidate_summary': {},
            'links': [],
        }

    def get_claim_overview(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        required_support_kinds: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        required_kinds = required_support_kinds or ['evidence', 'authority']
        summary = self.summarize_claim_support(user_id, claim_type)

        overview: Dict[str, Any] = {
            'available': summary.get('available', False),
            'required_support_kinds': required_kinds,
            'claims': {},
        }

        for current_claim, claim_summary in summary.get('claims', {}).items():
            covered: List[Dict[str, Any]] = []
            partially_supported: List[Dict[str, Any]] = []
            missing: List[Dict[str, Any]] = []
            claim_quality_paths: List[Dict[str, Any]] = []

            for element in claim_summary.get('elements', []):
                element_id = element.get('element_id') or ''
                support_path_summary = self.get_support_paths_for_element(
                    user_id,
                    current_claim,
                    claim_element_id=element_id if element_id else None,
                    required_support_kinds=required_kinds,
                )
                enhanced_element = dict(element)
                enhanced_element['support_path_summary'] = support_path_summary
                enhanced_element['support_quality_summary'] = support_path_summary.get('quality_summary', {})
                claim_quality_paths.extend([
                    path for path in support_path_summary.get('paths', []) or []
                    if isinstance(path, dict)
                ])
                kinds_present = set(element.get('support_by_kind', {}).keys())
                if element.get('total_links', 0) == 0:
                    missing.append(enhanced_element)
                elif all(kind in kinds_present for kind in required_kinds):
                    covered.append(enhanced_element)
                else:
                    partially_supported.append(enhanced_element)

            overview['claims'][current_claim] = {
                'required_support_kinds': required_kinds,
                'covered': covered,
                'partially_supported': partially_supported,
                'missing': missing,
                'support_quality_summary': self._summarize_support_path_quality(claim_quality_paths),
                'covered_count': len(covered),
                'partially_supported_count': len(partially_supported),
                'missing_count': len(missing),
                'total_elements': claim_summary.get('total_elements', 0),
            }

        return self._with_intake_summary_handoff(overview)

    def get_claim_coverage_matrix(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        required_support_kinds: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return a review-oriented claim-element coverage matrix with enriched support detail."""
        required_kinds = required_support_kinds or ['evidence', 'authority']
        summary = self.summarize_claim_support(user_id, claim_type)

        matrix: Dict[str, Any] = {
            'available': summary.get('available', False),
            'required_support_kinds': required_kinds,
            'claims': {},
        }

        for current_claim, claim_summary in summary.get('claims', {}).items():
            elements: List[Dict[str, Any]] = []
            status_counts = {
                'covered': 0,
                'partially_supported': 0,
                'missing': 0,
            }
            support_link_total = 0
            fact_total = 0

            for element in claim_summary.get('elements', []):
                status = self._coverage_status_for_element(element, required_kinds)
                status_counts[status] += 1
                support_link_total += int(element.get('total_links', 0) or 0)
                fact_total += int(element.get('fact_count', 0) or 0)

                links_by_kind: Dict[str, List[Dict[str, Any]]] = {}
                for link in element.get('links', []) or []:
                    links_by_kind.setdefault(link.get('support_kind', 'unknown'), []).append(link)

                support_traces = self._collect_support_traces_from_links(element.get('links', []) or [])
                support_packets = [self._build_support_packet(trace) for trace in support_traces]
                review_path_summary = self._build_support_path_summary_dto(
                    support_traces=support_traces,
                    support_packets=support_packets,
                )

                element_id = element.get('element_id') or ''
                element_support_ledger = self.get_element_support_ledger(
                    user_id,
                    current_claim,
                    claim_element_id=element_id if element_id else None,
                    claim_element_text=element.get('element_text') if not element_id else None,
                )

                graph_snapshot_refs = self.get_graph_snapshot_refs_for_element(
                    user_id,
                    current_claim,
                    claim_element_id=element_id if element_id else None,
                )
                support_path_summary = self.get_support_paths_for_element(
                    user_id,
                    current_claim,
                    claim_element_id=element_id if element_id else None,
                    required_support_kinds=required_kinds,
                )

                elements.append(
                    {
                        'element_id': element.get('element_id'),
                        'element_text': element.get('element_text'),
                        'status': status,
                        'support_by_kind': element.get('support_by_kind', {}),
                        'authority_treatment_summary': element.get('authority_treatment_summary', {}),
                        'authority_rule_candidate_summary': element.get('authority_rule_candidate_summary', {}),
                        'total_links': element.get('total_links', 0),
                        'fact_count': element.get('fact_count', 0),
                        'missing_support_kinds': [
                            kind for kind in required_kinds
                            if element.get('support_by_kind', {}).get(kind, 0) == 0
                        ],
                        'links_by_kind': links_by_kind,
                        'support_traces': support_traces,
                        'support_packets': support_packets,
                        **review_path_summary,
                        'element_support_ledger': element_support_ledger,
                        'graph_snapshot_refs': graph_snapshot_refs,
                        'support_path_summary': support_path_summary,
                        'support_quality_summary': support_path_summary.get('quality_summary', {}),
                        'links': element.get('links', []),
                    }
                )

            claim_support_traces = self._collect_support_traces_from_links(claim_summary.get('links', []))
            claim_support_packets = [self._build_support_packet(trace) for trace in claim_support_traces]
            claim_support_path_summary = self._build_support_path_summary_dto(
                support_traces=claim_support_traces,
                support_packets=claim_support_packets,
            )
            claim_support_paths = [
                path
                for element in elements
                for path in (element.get('support_path_summary', {}).get('paths', []) or [])
                if isinstance(path, dict)
            ]
            matrix['claims'][current_claim] = {
                'claim_type': current_claim,
                'required_support_kinds': required_kinds,
                'total_elements': claim_summary.get('total_elements', 0),
                'status_counts': status_counts,
                'total_links': support_link_total,
                'total_facts': fact_total,
                'support_by_kind': claim_summary.get('support_by_kind', {}),
                'authority_treatment_summary': claim_summary.get('authority_treatment_summary', {}),
                'authority_rule_candidate_summary': claim_summary.get('authority_rule_candidate_summary', {}),
                **claim_support_path_summary,
                'support_quality_summary': self._summarize_support_path_quality(claim_support_paths),
                'elements': elements,
                'unassigned_links': claim_summary.get('unassigned_links', []),
            }

        return self._with_intake_summary_handoff(matrix)

    def persist_claim_coverage_matrix_snapshot(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        required_support_kinds: Optional[List[str]] = None,
        coverage_matrix: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        retention_limit: Optional[int] = 3,
    ) -> Dict[str, Any]:
        """Persist the current claim coverage matrix as an authoritative snapshot."""
        normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
        normalized_retention_limit = self._normalize_snapshot_retention_limit(retention_limit)
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'required_support_kinds': normalized_kinds,
                'retention_limit': normalized_retention_limit,
                'claims': {},
                'error': 'duckdb_unavailable',
            }

        matrix = coverage_matrix if isinstance(coverage_matrix, dict) else self.get_claim_coverage_matrix(
            user_id,
            claim_type=claim_type,
            required_support_kinds=normalized_kinds or None,
        )
        claim_matrices = matrix.get('claims', {}) if isinstance(matrix.get('claims'), dict) else {}
        normalized_metadata = _merge_intake_summary_handoff_metadata(
            metadata,
            self.mediator,
        )
        persisted: Dict[str, Any] = {
            'available': True,
            'required_support_kinds': normalized_kinds,
            'retention_limit': normalized_retention_limit,
            'pruned_snapshot_count': 0,
            'claims': {},
        }

        for current_claim, claim_matrix in sorted(claim_matrices.items()):
            if claim_type and current_claim != claim_type:
                continue
            if not isinstance(claim_matrix, dict) or not claim_matrix:
                continue
            support_state_token = self._build_claim_support_state_token(
                user_id,
                current_claim,
                normalized_kinds,
            )
            claim_metadata = {
                **(normalized_metadata or {}),
                'support_state_token': support_state_token,
                'snapshot_source': 'claim_coverage_matrix',
                'element_count': len(claim_matrix.get('elements', []) or []),
                'total_links': int(claim_matrix.get('total_links', 0) or 0),
                'total_facts': int(claim_matrix.get('total_facts', 0) or 0),
                'coverage_matrix_summary': self._summarize_coverage_matrix_for_snapshot(claim_matrix),
            }
            try:
                conn = duckdb.connect(self.db_path)
                result = conn.execute(
                    """
                    INSERT INTO claim_support_snapshot (
                        user_id, claim_type, snapshot_kind,
                        required_support_kinds, payload, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    RETURNING id, timestamp
                    """,
                    [
                        user_id,
                        current_claim,
                        'coverage_matrix',
                        json.dumps(normalized_kinds, default=str),
                        json.dumps(claim_matrix, default=str),
                        json.dumps(claim_metadata, default=str),
                    ],
                ).fetchone()
                conn.close()
                prune_result = self._prune_snapshot_history(
                    user_id=user_id,
                    claim_type=current_claim,
                    snapshot_kind='coverage_matrix',
                    required_support_kinds=normalized_kinds,
                    keep_latest=normalized_retention_limit,
                )
                persisted['pruned_snapshot_count'] += int(
                    prune_result.get('pruned_snapshot_count', 0) or 0
                )
                persisted['claims'][current_claim] = {
                    'coverage_matrix': claim_matrix,
                    'snapshot': {
                        'snapshot_id': result[0],
                        'timestamp': result[1].isoformat() if hasattr(result[1], 'isoformat') else result[1],
                        'required_support_kinds': normalized_kinds,
                        'metadata': claim_metadata,
                        'stored_support_state_token': support_state_token,
                        'current_support_state_token': support_state_token,
                        'is_stale': False,
                        'retention_limit': normalized_retention_limit,
                        'pruned_snapshot_count': int(prune_result.get('pruned_snapshot_count', 0) or 0),
                    },
                }
            except Exception as exc:
                self.mediator.log(
                    'claim_coverage_matrix_snapshot_persist_error',
                    error=str(exc),
                    claim_type=current_claim,
                )
                persisted['claims'][current_claim] = {
                    'coverage_matrix': claim_matrix,
                    'snapshot': {
                        'snapshot_id': -1,
                        'required_support_kinds': normalized_kinds,
                        'metadata': claim_metadata,
                        'stored_support_state_token': support_state_token,
                        'current_support_state_token': support_state_token,
                        'is_stale': True,
                        'retention_limit': normalized_retention_limit,
                        'pruned_snapshot_count': 0,
                        'error': str(exc),
                    },
                }

        return persisted

    def get_claim_coverage_matrix_snapshots(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        required_support_kinds: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return latest persisted coverage-matrix snapshots by claim."""
        normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'required_support_kinds': normalized_kinds,
                'claims': {},
                'error': 'duckdb_unavailable',
            }

        try:
            conn = duckdb.connect(self.db_path)
            if claim_type:
                rows = conn.execute(
                    """
                    SELECT claim_type, required_support_kinds, payload, metadata, timestamp, id
                    FROM claim_support_snapshot
                    WHERE user_id = ? AND claim_type = ? AND snapshot_kind = 'coverage_matrix'
                    ORDER BY claim_type ASC, timestamp DESC, id DESC
                    """,
                    [user_id, claim_type],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT claim_type, required_support_kinds, payload, metadata, timestamp, id
                    FROM claim_support_snapshot
                    WHERE user_id = ? AND snapshot_kind = 'coverage_matrix'
                    ORDER BY claim_type ASC, timestamp DESC, id DESC
                    """,
                    [user_id],
                ).fetchall()
            conn.close()
        except Exception as exc:
            self.mediator.log('claim_coverage_matrix_snapshot_query_error', error=str(exc))
            return {
                'available': False,
                'required_support_kinds': normalized_kinds,
                'claims': {},
                'error': str(exc),
            }

        snapshots: Dict[str, Any] = {
            'available': True,
            'required_support_kinds': normalized_kinds,
            'claims': {},
        }
        seen_claims = set()
        for row_claim_type, stored_required_kinds, payload_json, metadata_json, timestamp, snapshot_id in rows:
            stored_kinds = json.loads(stored_required_kinds) if stored_required_kinds else []
            if normalized_kinds and stored_kinds != normalized_kinds:
                continue
            if row_claim_type in seen_claims:
                continue
            seen_claims.add(row_claim_type)
            payload = json.loads(payload_json) if payload_json else {}
            metadata_payload = json.loads(metadata_json) if metadata_json else {}
            current_support_state_token = self._build_claim_support_state_token(
                user_id,
                row_claim_type,
                stored_kinds,
            )
            stored_support_state_token = str(metadata_payload.get('support_state_token') or '')
            is_stale = bool(stored_support_state_token) and stored_support_state_token != current_support_state_token
            snapshots['claims'][row_claim_type] = {
                'coverage_matrix': payload,
                'snapshot': {
                    'snapshot_id': snapshot_id,
                    'timestamp': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else timestamp,
                    'required_support_kinds': stored_kinds,
                    'metadata': metadata_payload,
                    'stored_support_state_token': stored_support_state_token,
                    'current_support_state_token': current_support_state_token,
                    'is_stale': is_stale,
                },
            }

        return snapshots

    def get_claim_support_validation(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        required_support_kinds: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        required_kinds = required_support_kinds or ['evidence', 'authority']
        matrix = self.get_claim_coverage_matrix(
            user_id,
            claim_type=claim_type,
            required_support_kinds=required_kinds,
        )
        gaps = self.get_claim_support_gaps(
            user_id,
            claim_type=claim_type,
            required_support_kinds=required_kinds,
        )
        contradictions = self.get_claim_contradiction_candidates(
            user_id,
            claim_type=claim_type,
        )

        validation: Dict[str, Any] = {
            'available': matrix.get('available', False),
            'required_support_kinds': required_kinds,
            'claims': {},
        }

        gap_claims = gaps.get('claims', {}) if isinstance(gaps, dict) else {}
        contradiction_claims = contradictions.get('claims', {}) if isinstance(contradictions, dict) else {}

        for current_claim, claim_matrix in matrix.get('claims', {}).items():
            validation['claims'][current_claim] = self._build_claim_validation(
                current_claim,
                claim_matrix,
                gap_claims.get(current_claim, {}),
                contradiction_claims.get(current_claim, {}),
            )

        return self._with_intake_summary_handoff(validation)

    def _build_formal_validation_element_report(self, element: Dict[str, Any]) -> Dict[str, Any]:
        reasoning = element.get('reasoning_diagnostics', {}) if isinstance(element.get('reasoning_diagnostics'), dict) else {}
        proof_diagnostics = element.get('proof_diagnostics', {}) if isinstance(element.get('proof_diagnostics'), dict) else {}
        decision_trace = element.get('proof_decision_trace', {}) if isinstance(element.get('proof_decision_trace'), dict) else {}
        logic_proof = reasoning.get('logic_proof', {}) if isinstance(reasoning.get('logic_proof'), dict) else {}
        logic_contradictions = reasoning.get('logic_contradictions', {}) if isinstance(reasoning.get('logic_contradictions'), dict) else {}
        hybrid_reasoning = reasoning.get('hybrid_reasoning', {}) if isinstance(reasoning.get('hybrid_reasoning'), dict) else {}
        hybrid_result = hybrid_reasoning.get('result', {}) if isinstance(hybrid_reasoning.get('result'), dict) else {}
        temporal_payload = hybrid_result.get('temporal_reasoning_payload', {}) if isinstance(hybrid_result.get('temporal_reasoning_payload'), dict) else {}
        reasoner_artifact = hybrid_result.get('reasoner_proof_artifact', {}) if isinstance(hybrid_result.get('reasoner_proof_artifact'), dict) else {}
        theorem_export_metadata = temporal_payload.get('theorem_export_metadata', {}) if isinstance(temporal_payload.get('theorem_export_metadata'), dict) else {}
        proof_gap_types = self._extract_proof_gap_types(element.get('proof_gaps', []) or [])

        if element.get('validation_status') == 'supported':
            formal_status = 'passed'
        elif element.get('validation_status') == 'contradicted':
            formal_status = 'contradicted'
        elif 'logic_unprovable' in proof_gap_types:
            formal_status = 'unprovable'
        elif 'ontology_validation_failed' in proof_gap_types:
            formal_status = 'invalid_ontology'
        elif element.get('validation_status') == 'missing':
            formal_status = 'missing_premises'
        else:
            formal_status = 'needs_review'

        predicate_count = int(reasoning.get('predicate_count', proof_diagnostics.get('reasoning_predicate_count', 0)) or 0)
        premise_failure_category = self._classify_formal_premise_failure(element, proof_gap_types)
        support_quality_summary = (
            element.get('support_quality_summary', {})
            if isinstance(element.get('support_quality_summary'), dict)
            else {}
        )
        primary_quality_signal = (
            element.get('primary_quality_signal')
            if isinstance(element.get('primary_quality_signal'), dict)
            else self._primary_quality_signal_for_summary(support_quality_summary)
        )
        return {
            'element_id': element.get('element_id') or '',
            'element_text': element.get('element_text') or '',
            'validation_status': element.get('validation_status') or '',
            'formal_status': formal_status,
            'recommended_action': element.get('recommended_action') or '',
            'decision_source': decision_trace.get('decision_source') or proof_diagnostics.get('decision_source') or '',
            'predicate_count': predicate_count,
            'logic_provable_count': int(decision_trace.get('logic_provable_count', 0) or 0),
            'logic_unprovable_count': int(decision_trace.get('logic_unprovable_count', 0) or 0),
            'logic_contradiction_count': int(decision_trace.get('logic_contradiction_count', 0) or 0),
            'proof_gap_types': proof_gap_types,
            'proof_gap_count': int(element.get('proof_gap_count', len(element.get('proof_gaps', []) or [])) or 0),
            'proof_gaps': list(element.get('proof_gaps', []) or []),
            'premise_failure_category': premise_failure_category,
            'authority_rule_candidate_summary': element.get('authority_rule_candidate_summary', {}),
            'authority_treatment_summary': element.get('authority_treatment_summary', {}),
            'support_quality_summary': support_quality_summary,
            'primary_quality_signal': primary_quality_signal,
            'quality_follow_up_action': primary_quality_signal.get('follow_up_action', ''),
            'adapter_statuses': dict(reasoning.get('adapter_statuses', {}) or {}),
            'logic_proof_summary': self._summarize_adapter_result(
                logic_proof,
                count_fields=['predicate_count', 'provable_elements', 'unprovable_elements'],
            ),
            'logic_contradiction_summary': self._summarize_adapter_result(
                logic_contradictions,
                count_fields=['predicate_count', 'contradictions'],
            ),
            'hybrid_reasoning_summary': self._summarize_adapter_result(
                hybrid_reasoning,
                count_fields=['predicate_count', 'result', 'temporal_reasoning_payload'],
            ),
            'tdfol_formula_count': int(temporal_payload.get('tdfol_formula_count', 0) or 0),
            'dcec_formula_count': int(temporal_payload.get('dcec_formula_count', 0) or 0),
            'theorem_export_metadata': theorem_export_metadata,
            'reasoner_proof_artifact': reasoner_artifact,
            'formalization_ready': bool(predicate_count > 0 and formal_status in {'passed', 'needs_review', 'unprovable'}),
        }

    def get_formal_validation_report(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        required_support_kinds: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return a draft-generation-ready formal validation report by claim."""
        validation = self.get_claim_support_validation(
            user_id,
            claim_type=claim_type,
            required_support_kinds=required_support_kinds,
        )
        validation_claims = validation.get('claims', {}) if isinstance(validation, dict) else {}
        report_claims: Dict[str, Any] = {}
        formal_status_counts: Counter[str] = Counter()
        total_elements = 0
        total_predicates = 0
        total_proof_gaps = 0
        theorem_ready_count = 0
        support_quality_signal_counts: Counter[str] = Counter()
        primary_quality_signal_counts: Counter[str] = Counter()
        quality_follow_up_action_counts: Counter[str] = Counter()

        for current_claim, claim_validation in validation_claims.items():
            if not isinstance(claim_validation, dict):
                continue
            element_reports = [
                self._build_formal_validation_element_report(element)
                for element in claim_validation.get('elements', []) or []
                if isinstance(element, dict)
            ]
            claim_status_counts: Counter[str] = Counter()
            claim_predicate_count = 0
            claim_proof_gap_count = 0
            claim_theorem_ready_count = 0
            claim_support_quality_signal_counts: Counter[str] = Counter()
            claim_primary_quality_signal_counts: Counter[str] = Counter()
            claim_quality_follow_up_action_counts: Counter[str] = Counter()
            for element_report in element_reports:
                status = str(element_report.get('formal_status') or 'needs_review')
                claim_status_counts[status] += 1
                formal_status_counts[status] += 1
                claim_predicate_count += int(element_report.get('predicate_count', 0) or 0)
                claim_proof_gap_count += int(element_report.get('proof_gap_count', 0) or 0)
                if element_report.get('formalization_ready'):
                    claim_theorem_ready_count += 1
                quality_summary = (
                    element_report.get('support_quality_summary', {})
                    if isinstance(element_report.get('support_quality_summary'), dict)
                    else {}
                )
                raw_signal_counts = (
                    quality_summary.get('quality_signal_counts', {})
                    if isinstance(quality_summary.get('quality_signal_counts'), dict)
                    else {}
                )
                for signal_type, signal_count in raw_signal_counts.items():
                    normalized_signal = str(signal_type or '').strip()
                    if not normalized_signal:
                        continue
                    try:
                        normalized_count = int(signal_count or 0)
                    except (TypeError, ValueError):
                        normalized_count = 0
                    if normalized_count <= 0:
                        continue
                    claim_support_quality_signal_counts[normalized_signal] += normalized_count
                    support_quality_signal_counts[normalized_signal] += normalized_count
                primary_quality_signal = (
                    element_report.get('primary_quality_signal')
                    if isinstance(element_report.get('primary_quality_signal'), dict)
                    else {}
                )
                primary_signal_type = str(primary_quality_signal.get('signal_type') or '').strip()
                if primary_signal_type:
                    claim_primary_quality_signal_counts[primary_signal_type] += 1
                    primary_quality_signal_counts[primary_signal_type] += 1
                follow_up_action = str(element_report.get('quality_follow_up_action') or '').strip()
                if follow_up_action:
                    claim_quality_follow_up_action_counts[follow_up_action] += 1
                    quality_follow_up_action_counts[follow_up_action] += 1

            total_elements += len(element_reports)
            total_predicates += claim_predicate_count
            total_proof_gaps += claim_proof_gap_count
            theorem_ready_count += claim_theorem_ready_count
            if claim_status_counts.get('contradicted', 0):
                formal_status = 'blocked'
            elif claim_status_counts.get('missing_premises', 0):
                formal_status = 'missing_premises'
            elif claim_status_counts.get('unprovable', 0) or claim_status_counts.get('invalid_ontology', 0):
                formal_status = 'needs_review'
            elif element_reports and claim_status_counts.get('passed', 0) == len(element_reports):
                formal_status = 'passed'
            else:
                formal_status = 'needs_review'

            report_claims[current_claim] = {
                'claim_type': current_claim,
                'validation_status': claim_validation.get('validation_status', ''),
                'formal_status': formal_status,
                'formal_status_counts': dict(sorted(claim_status_counts.items())),
                'element_count': len(element_reports),
                'predicate_count': claim_predicate_count,
                'proof_gap_count': claim_proof_gap_count,
                'formalization_ready_element_count': claim_theorem_ready_count,
                'theorem_export_ready': claim_theorem_ready_count > 0,
                'support_quality_summary': dict(claim_validation.get('support_quality_summary') or {}),
                'support_quality_signal_counts': dict(sorted(claim_support_quality_signal_counts.items())),
                'primary_quality_signal_counts': dict(sorted(claim_primary_quality_signal_counts.items())),
                'quality_follow_up_action_counts': dict(sorted(claim_quality_follow_up_action_counts.items())),
                'elements': element_reports,
            }

        if formal_status_counts.get('contradicted', 0):
            overall_status = 'blocked'
        elif formal_status_counts.get('missing_premises', 0):
            overall_status = 'missing_premises'
        elif formal_status_counts.get('unprovable', 0) or formal_status_counts.get('invalid_ontology', 0):
            overall_status = 'needs_review'
        elif total_elements and formal_status_counts.get('passed', 0) == total_elements:
            overall_status = 'passed'
        else:
            overall_status = 'needs_review' if total_elements else 'unavailable'

        return self._with_intake_summary_handoff({
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'required_support_kinds': validation.get('required_support_kinds', required_support_kinds or ['evidence', 'authority'])
            if isinstance(validation, dict) else (required_support_kinds or ['evidence', 'authority']),
            'overall_status': overall_status,
            'claim_count': len(report_claims),
            'element_count': total_elements,
            'predicate_count': total_predicates,
            'proof_gap_count': total_proof_gaps,
            'formalization_ready_element_count': theorem_ready_count,
            'formal_status_counts': dict(sorted(formal_status_counts.items())),
            'support_quality_signal_counts': dict(sorted(support_quality_signal_counts.items())),
            'primary_quality_signal_counts': dict(sorted(primary_quality_signal_counts.items())),
            'quality_follow_up_action_counts': dict(sorted(quality_follow_up_action_counts.items())),
            'claims': report_claims,
        })

    def get_claim_support_gaps(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        required_support_kinds: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        required_kinds = required_support_kinds or ['evidence', 'authority']
        matrix = self.get_claim_coverage_matrix(
            user_id,
            claim_type=claim_type,
            required_support_kinds=required_kinds,
        )

        gaps: Dict[str, Any] = {
            'available': matrix.get('available', False),
            'required_support_kinds': required_kinds,
            'claims': {},
        }

        for current_claim, claim_matrix in matrix.get('claims', {}).items():
            unresolved_elements: List[Dict[str, Any]] = []
            for element in claim_matrix.get('elements', []):
                if element.get('status') == 'covered':
                    continue
                support_facts = self.get_claim_support_facts(
                    user_id,
                    current_claim,
                    claim_element_id=element.get('element_id'),
                    claim_element_text=element.get('element_text'),
                )
                support_traces = self.get_claim_support_traces(
                    user_id,
                    current_claim,
                    claim_element_id=element.get('element_id'),
                    claim_element_text=element.get('element_text'),
                )
                support_packets = [self._build_support_packet(trace) for trace in support_traces]
                support_path_summary = self._build_support_path_summary_dto(
                    support_traces=support_traces,
                    support_packets=support_packets,
                    graph_items=element.get('links', []),
                )
                unresolved_elements.append(
                    {
                        'element_id': element.get('element_id'),
                        'element_text': element.get('element_text'),
                        'status': element.get('status'),
                        'missing_support_kinds': element.get('missing_support_kinds', []),
                        'total_links': element.get('total_links', 0),
                        'fact_count': element.get('fact_count', 0),
                        'support_by_kind': element.get('support_by_kind', {}),
                        'authority_treatment_summary': element.get('authority_treatment_summary', {}),
                        'authority_rule_candidate_summary': element.get('authority_rule_candidate_summary', {}),
                        'links': element.get('links', []),
                        'support_facts': support_facts,
                        'support_fact_registry_summary': self._summarize_fact_registry(support_facts),
                        'support_traces': support_traces,
                        'support_packets': support_packets,
                        **support_path_summary,
                        'support_path_summary': element.get('support_path_summary', {}),
                        'support_quality_summary': element.get('support_quality_summary', {}),
                        'recommended_action': (
                            element.get('support_quality_summary', {}).get('recommended_quality_action')
                            if isinstance(element.get('support_quality_summary'), dict)
                            and element.get('support_quality_summary', {}).get('recommended_quality_action') in {
                                'strengthen_support_path',
                                'collect_initial_support',
                            }
                            else
                            'improve_parse_quality'
                            if element.get('total_links', 0)
                            and not (element.get('missing_support_kinds', []) or [])
                            and self._element_has_parse_quality_gap(element)
                            else self._recommended_support_gap_action(element)
                        ),
                    }
                )

            gaps['claims'][current_claim] = {
                'claim_type': current_claim,
                'required_support_kinds': required_kinds,
                'unresolved_count': len(unresolved_elements),
                'unresolved_elements': unresolved_elements,
            }

        return self._with_intake_summary_handoff(gaps)

    def get_claim_contradiction_candidates(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        summary = self.summarize_claim_support(user_id, claim_type)
        contradictions: Dict[str, Any] = {
            'available': summary.get('available', False),
            'claims': {},
        }

        for current_claim, claim_summary in summary.get('claims', {}).items():
            candidates: List[Dict[str, Any]] = []
            for element in claim_summary.get('elements', []):
                support_facts = self.get_claim_support_facts(
                    user_id,
                    current_claim,
                    claim_element_id=element.get('element_id'),
                    claim_element_text=element.get('element_text'),
                )
                for index, left in enumerate(support_facts):
                    for right in support_facts[index + 1:]:
                        left_polarity = self._fact_polarity(left.get('text'))
                        right_polarity = self._fact_polarity(right.get('text'))
                        if left_polarity == right_polarity:
                            continue
                        overlap_terms = self._fact_overlap_terms(left.get('text'), right.get('text'))
                        if len(overlap_terms) < 2:
                            continue
                        candidates.append(
                            {
                                'claim_element_id': element.get('element_id'),
                                'claim_element_text': element.get('element_text'),
                                'fact_ids': [left.get('fact_id'), right.get('fact_id')],
                                'texts': [left.get('text'), right.get('text')],
                                'support_refs': [left.get('support_ref'), right.get('support_ref')],
                                'support_kinds': [left.get('support_kind'), right.get('support_kind')],
                                'source_tables': [left.get('source_table'), right.get('source_table')],
                                'polarity': [left_polarity, right_polarity],
                                'overlap_terms': overlap_terms,
                                'graph_trace_summary': self._summarize_graph_traces([left, right]),
                            }
                        )

            candidates.sort(
                key=lambda item: (
                    len(item.get('overlap_terms', [])),
                    item.get('graph_trace_summary', {}).get('traced_link_count', 0),
                ),
                reverse=True,
            )
            contradictions['claims'][current_claim] = {
                'claim_type': current_claim,
                'candidate_count': len(candidates),
                'candidates': candidates,
            }

        return self._with_intake_summary_handoff(contradictions)

    def persist_claim_support_diagnostics(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        required_support_kinds: Optional[List[str]] = None,
        gaps: Optional[Dict[str, Any]] = None,
        contradictions: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        retention_limit: Optional[int] = 3,
    ) -> Dict[str, Any]:
        normalized_retention_limit = self._normalize_snapshot_retention_limit(retention_limit)
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'required_support_kinds': self._normalize_required_support_kinds(required_support_kinds),
                'retention_limit': normalized_retention_limit,
                'pruned_snapshot_count': 0,
                'claims': {},
            }

        normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
        normalized_metadata = _merge_intake_summary_handoff_metadata(
            metadata,
            self.mediator,
        )
        gap_payload = gaps if isinstance(gaps, dict) else self.get_claim_support_gaps(
            user_id,
            claim_type=claim_type,
            required_support_kinds=normalized_kinds or None,
        )
        contradiction_payload = (
            contradictions if isinstance(contradictions, dict)
            else self.get_claim_contradiction_candidates(user_id, claim_type=claim_type)
        )

        gap_claims = gap_payload.get('claims', {}) if isinstance(gap_payload, dict) else {}
        contradiction_claims = (
            contradiction_payload.get('claims', {})
            if isinstance(contradiction_payload, dict)
            else {}
        )
        claim_names = sorted(set(gap_claims.keys()) | set(contradiction_claims.keys()))
        persisted: Dict[str, Any] = {
            'available': True,
            'required_support_kinds': normalized_kinds,
            'retention_limit': normalized_retention_limit,
            'pruned_snapshot_count': 0,
            'claims': {},
        }

        for current_claim in claim_names:
            support_state_token = self._build_claim_support_state_token(
                user_id,
                current_claim,
                normalized_kinds,
            )
            claim_metadata = {
                **(normalized_metadata or {}),
                'support_state_token': support_state_token,
            }
            claim_result = {
                'gaps': gap_claims.get(current_claim, {}),
                'contradictions': contradiction_claims.get(current_claim, {}),
                'snapshots': {},
            }
            for snapshot_kind, payload in (
                ('gaps', claim_result['gaps']),
                ('contradictions', claim_result['contradictions']),
            ):
                if not isinstance(payload, dict) or not payload:
                    continue
                try:
                    conn = duckdb.connect(self.db_path)
                    result = conn.execute(
                        """
                        INSERT INTO claim_support_snapshot (
                            user_id, claim_type, snapshot_kind,
                            required_support_kinds, payload, metadata
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        RETURNING id, timestamp
                        """,
                        [
                            user_id,
                            current_claim,
                            snapshot_kind,
                            json.dumps(normalized_kinds, default=str),
                            json.dumps(payload, default=str),
                            json.dumps(claim_metadata, default=str),
                        ],
                    ).fetchone()
                    conn.close()
                    prune_result = self._prune_snapshot_history(
                        user_id=user_id,
                        claim_type=current_claim,
                        snapshot_kind=snapshot_kind,
                        required_support_kinds=normalized_kinds,
                        keep_latest=normalized_retention_limit,
                    )
                    persisted['pruned_snapshot_count'] += int(
                        prune_result.get('pruned_snapshot_count', 0) or 0
                    )
                    claim_result['snapshots'][snapshot_kind] = {
                        'snapshot_id': result[0],
                        'timestamp': result[1].isoformat() if hasattr(result[1], 'isoformat') else result[1],
                        'required_support_kinds': normalized_kinds,
                        'metadata': claim_metadata,
                        'is_stale': False,
                        'retention_limit': normalized_retention_limit,
                        'pruned_snapshot_count': int(prune_result.get('pruned_snapshot_count', 0) or 0),
                    }
                except Exception as exc:
                    self.mediator.log(
                        'claim_support_snapshot_persist_error',
                        error=str(exc),
                        claim_type=current_claim,
                        snapshot_kind=snapshot_kind,
                    )
                    claim_result['snapshots'][snapshot_kind] = {
                        'snapshot_id': -1,
                        'required_support_kinds': normalized_kinds,
                        'metadata': claim_metadata,
                        'is_stale': True,
                        'retention_limit': normalized_retention_limit,
                        'pruned_snapshot_count': 0,
                        'error': str(exc),
                    }
            persisted['claims'][current_claim] = claim_result

        return persisted

    def prune_claim_support_diagnostic_snapshots(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        required_support_kinds: Optional[List[str]] = None,
        snapshot_kind: Optional[str] = None,
        keep_latest: Optional[int] = 3,
    ) -> Dict[str, Any]:
        normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
        normalized_keep_latest = self._normalize_snapshot_retention_limit(keep_latest)
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'required_support_kinds': normalized_kinds,
                'retention_limit': normalized_keep_latest,
                'pruned_snapshot_count': 0,
                'claims': {},
            }

        where_clauses = ['user_id = ?']
        params: List[Any] = [user_id]
        if claim_type:
            where_clauses.append('claim_type = ?')
            params.append(claim_type)
        if snapshot_kind:
            where_clauses.append('snapshot_kind = ?')
            params.append(snapshot_kind)
        if normalized_kinds:
            where_clauses.append('required_support_kinds = ?')
            params.append(json.dumps(normalized_kinds, default=str))

        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                f"""
                SELECT DISTINCT claim_type, snapshot_kind, required_support_kinds
                FROM claim_support_snapshot
                WHERE {' AND '.join(where_clauses)}
                ORDER BY claim_type ASC, snapshot_kind ASC
                """,
                params,
            ).fetchall()
            conn.close()
        except Exception as exc:
            self.mediator.log('claim_support_snapshot_query_error', error=str(exc))
            return {
                'available': False,
                'required_support_kinds': normalized_kinds,
                'retention_limit': normalized_keep_latest,
                'pruned_snapshot_count': 0,
                'claims': {},
                'error': str(exc),
            }

        pruned: Dict[str, Any] = {
            'available': True,
            'required_support_kinds': normalized_kinds,
            'retention_limit': normalized_keep_latest,
            'pruned_snapshot_count': 0,
            'claims': {},
        }
        for current_claim, current_snapshot_kind, stored_required_kinds in rows:
            stored_kinds = json.loads(stored_required_kinds) if stored_required_kinds else []
            prune_result = self._prune_snapshot_history(
                user_id=user_id,
                claim_type=current_claim,
                snapshot_kind=current_snapshot_kind,
                required_support_kinds=stored_kinds,
                keep_latest=normalized_keep_latest,
            )
            pruned['pruned_snapshot_count'] += int(
                prune_result.get('pruned_snapshot_count', 0) or 0
            )
            claim_entry = pruned['claims'].setdefault(current_claim, {'snapshots': {}})
            claim_entry['snapshots'][current_snapshot_kind] = {
                'required_support_kinds': stored_kinds,
                'retention_limit': normalized_keep_latest,
                'pruned_snapshot_count': int(
                    prune_result.get('pruned_snapshot_count', 0) or 0
                ),
                'deleted_snapshot_ids': prune_result.get('deleted_snapshot_ids', []),
            }
            if prune_result.get('error'):
                claim_entry['snapshots'][current_snapshot_kind]['error'] = prune_result['error']

        return pruned

    def get_claim_support_diagnostic_snapshots(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        required_support_kinds: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'required_support_kinds': normalized_kinds,
                'claims': {},
            }

        try:
            conn = duckdb.connect(self.db_path)
            if claim_type:
                rows = conn.execute(
                    """
                    SELECT claim_type, snapshot_kind, required_support_kinds, payload, metadata, timestamp, id
                    FROM claim_support_snapshot
                    WHERE user_id = ? AND claim_type = ?
                    ORDER BY claim_type ASC, snapshot_kind ASC, timestamp DESC, id DESC
                    """,
                    [user_id, claim_type],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT claim_type, snapshot_kind, required_support_kinds, payload, metadata, timestamp, id
                    FROM claim_support_snapshot
                    WHERE user_id = ?
                    ORDER BY claim_type ASC, snapshot_kind ASC, timestamp DESC, id DESC
                    """,
                    [user_id],
                ).fetchall()
            conn.close()
        except Exception as exc:
            self.mediator.log('claim_support_snapshot_query_error', error=str(exc))
            return {
                'available': False,
                'required_support_kinds': normalized_kinds,
                'claims': {},
                'error': str(exc),
            }

        snapshots: Dict[str, Any] = {
            'available': True,
            'required_support_kinds': normalized_kinds,
            'claims': {},
        }
        seen_keys = set()
        for row in rows:
            row_claim_type, snapshot_kind, stored_required_kinds, payload_json, metadata_json, timestamp, snapshot_id = row
            stored_kinds = json.loads(stored_required_kinds) if stored_required_kinds else []
            if normalized_kinds and stored_kinds != normalized_kinds:
                continue
            key = (row_claim_type, snapshot_kind)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            claim_entry = snapshots['claims'].setdefault(
                row_claim_type,
                {
                    'gaps': {},
                    'contradictions': {},
                    'snapshots': {},
                },
            )
            payload = json.loads(payload_json) if payload_json else {}
            metadata = json.loads(metadata_json) if metadata_json else {}
            current_support_state_token = self._build_claim_support_state_token(
                user_id,
                row_claim_type,
                stored_kinds,
            )
            stored_support_state_token = str(metadata.get('support_state_token') or '')
            is_stale = bool(stored_support_state_token) and stored_support_state_token != current_support_state_token
            if snapshot_kind == 'gaps':
                claim_entry['gaps'] = payload
            elif snapshot_kind == 'contradictions':
                claim_entry['contradictions'] = payload
            claim_entry['snapshots'][snapshot_kind] = {
                'snapshot_id': snapshot_id,
                'timestamp': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else timestamp,
                'required_support_kinds': stored_kinds,
                'metadata': metadata,
                'stored_support_state_token': stored_support_state_token,
                'current_support_state_token': current_support_state_token,
                'is_stale': is_stale,
            }

        return snapshots

    def was_follow_up_executed(
        self,
        user_id: str,
        claim_type: str,
        support_kind: str,
        query_text: str,
        cooldown_seconds: int = 3600,
    ) -> bool:
        if not DUCKDB_AVAILABLE:
            return False

        query_hash = self._hash_query_text(query_text)
        try:
            conn = duckdb.connect(self.db_path)
            row = conn.execute(
                """
                SELECT timestamp
                FROM claim_follow_up_execution
                WHERE user_id = ? AND claim_type = ? AND support_kind = ? AND query_hash = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                [user_id, claim_type, support_kind, query_hash],
            ).fetchone()
            conn.close()
            if not row or cooldown_seconds < 0:
                return False
            last_run = row[0]
            now = datetime.now(last_run.tzinfo) if hasattr(last_run, 'tzinfo') else datetime.now()
            return last_run >= now - timedelta(seconds=cooldown_seconds)
        except Exception as exc:
            self.mediator.log('claim_follow_up_lookup_error', error=str(exc))
            return False

    def record_follow_up_execution(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: Optional[str],
        claim_element_text: Optional[str],
        support_kind: str,
        query_text: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        if not DUCKDB_AVAILABLE:
            return -1

        query_hash = self._hash_query_text(query_text)
        normalized_metadata = _merge_intake_summary_handoff_metadata(
            metadata,
            self.mediator,
        )
        try:
            conn = duckdb.connect(self.db_path)
            result = conn.execute(
                """
                INSERT INTO claim_follow_up_execution (
                    user_id, claim_type, claim_element_id, claim_element_text,
                    support_kind, query_text, query_hash, status, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                [
                    user_id,
                    claim_type,
                    claim_element_id,
                    claim_element_text,
                    support_kind,
                    query_text,
                    query_hash,
                    status,
                    json.dumps(normalized_metadata or {}),
                ],
            ).fetchone()
            conn.close()
            return result[0]
        except Exception as exc:
            self.mediator.log('claim_follow_up_record_error', error=str(exc))
            return -1

    def resolve_follow_up_manual_review(
        self,
        *,
        user_id: str,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
        resolution_status: str = 'resolved',
        resolution_notes: Optional[str] = None,
        related_execution_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not DUCKDB_AVAILABLE:
            return {
                'recorded': False,
                'error': 'DuckDB not available',
            }

        related_entry: Dict[str, Any] = {}
        if related_execution_id is not None:
            try:
                conn = duckdb.connect(self.db_path)
                row = conn.execute(
                    """
                    SELECT id, claim_type, claim_element_id, claim_element_text, support_kind, status, metadata
                    FROM claim_follow_up_execution
                    WHERE id = ? AND user_id = ?
                    LIMIT 1
                    """,
                    [related_execution_id, user_id],
                ).fetchone()
                conn.close()
            except Exception as exc:
                self.mediator.log('claim_follow_up_resolution_lookup_error', error=str(exc))
                return {
                    'recorded': False,
                    'error': str(exc),
                }
            if row:
                related_entry = {
                    'execution_id': row[0],
                    'claim_type': row[1],
                    'claim_element_id': row[2],
                    'claim_element_text': row[3],
                    'support_kind': row[4],
                    'status': row[5],
                    'metadata': json.loads(row[6]) if row[6] else {},
                }

        resolved_claim_type = claim_type or related_entry.get('claim_type')
        resolved_element_id = claim_element_id or related_entry.get('claim_element_id')
        resolved_element_text = claim_element_text or related_entry.get('claim_element_text')
        if not resolved_claim_type:
            return {
                'recorded': False,
                'error': 'claim_type is required to record manual review resolution',
            }

        normalized_resolution_status = str(resolution_status or 'resolved').strip() or 'resolved'
        element_ref = resolved_element_id or resolved_element_text or 'unknown_element'
        query_text = f'manual_review_resolution::{resolved_claim_type}::{element_ref}::{normalized_resolution_status}'
        resolution_metadata = {
            'resolution_status': normalized_resolution_status,
            'resolution_notes': resolution_notes or '',
            'related_execution_id': related_entry.get('execution_id', related_execution_id),
            'related_support_kind': related_entry.get('support_kind', 'manual_review'),
            'execution_mode': 'manual_review_resolution',
            'follow_up_focus': 'contradiction_resolution',
            'query_strategy': 'manual_review_resolution',
            'validation_status': (related_entry.get('metadata', {}) or {}).get('validation_status', 'contradicted'),
        }
        if isinstance(metadata, dict):
            resolution_metadata.update(metadata)

        record_id = self.record_follow_up_execution(
            user_id=user_id,
            claim_type=resolved_claim_type,
            claim_element_id=resolved_element_id,
            claim_element_text=resolved_element_text,
            support_kind='manual_review',
            query_text=query_text,
            status='resolved_manual_review',
            metadata=resolution_metadata,
        )
        return {
            'recorded': record_id > 0,
            'execution_id': record_id,
            'claim_type': resolved_claim_type,
            'claim_element_id': resolved_element_id,
            'claim_element_text': resolved_element_text,
            'support_kind': 'manual_review',
            'status': 'resolved_manual_review',
            'query_text': query_text,
            'metadata': resolution_metadata,
        }

    def get_follow_up_execution_status(
        self,
        user_id: str,
        claim_type: str,
        support_kind: str,
        query_text: str,
        cooldown_seconds: int = 3600,
    ) -> Dict[str, Any]:
        if not DUCKDB_AVAILABLE:
            return {
                'query_text': query_text,
                'support_kind': support_kind,
                'has_history': False,
                'in_cooldown': False,
            }

        query_hash = self._hash_query_text(query_text)
        try:
            conn = duckdb.connect(self.db_path)
            row = conn.execute(
                """
                SELECT status, metadata, timestamp
                FROM claim_follow_up_execution
                WHERE user_id = ? AND claim_type = ? AND support_kind = ? AND query_hash = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                [user_id, claim_type, support_kind, query_hash],
            ).fetchone()
            conn.close()
            if not row:
                return {
                    'query_text': query_text,
                    'support_kind': support_kind,
                    'has_history': False,
                    'in_cooldown': False,
                }

            last_status = row[0]
            metadata = json.loads(row[1]) if row[1] else {}
            last_attempted_at = row[2]
            eligible_at = None
            in_cooldown = False
            if cooldown_seconds >= 0:
                eligible_at = last_attempted_at + timedelta(seconds=cooldown_seconds)
                now = datetime.now(last_attempted_at.tzinfo) if hasattr(last_attempted_at, 'tzinfo') else datetime.now()
                in_cooldown = eligible_at > now

            return {
                'query_text': query_text,
                'support_kind': support_kind,
                'has_history': True,
                'last_status': last_status,
                'last_attempted_at': last_attempted_at,
                'eligible_at': eligible_at,
                'in_cooldown': in_cooldown,
                'metadata': metadata,
            }
        except Exception as exc:
            self.mediator.log('claim_follow_up_status_error', error=str(exc))
            return {
                'query_text': query_text,
                'support_kind': support_kind,
                'has_history': False,
                'in_cooldown': False,
                'error': str(exc),
            }

    def get_recent_follow_up_execution(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        support_kind: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        if not DUCKDB_AVAILABLE:
            return self._with_intake_summary_handoff({
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': max(0, int(limit or 0)),
                'claims': {},
            })

        normalized_limit = max(0, int(limit or 0))
        if normalized_limit == 0:
            return self._with_intake_summary_handoff({
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': normalized_limit,
                'claims': {},
            })

        where_clauses = ['user_id = ?']
        parameters: List[Any] = [user_id]
        if claim_type:
            where_clauses.append('claim_type = ?')
            parameters.append(claim_type)
        if claim_element_id:
            where_clauses.append('claim_element_id = ?')
            parameters.append(claim_element_id)
        if support_kind:
            where_clauses.append('support_kind = ?')
            parameters.append(support_kind)

        parameters.append(normalized_limit)
        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    claim_type,
                    claim_element_id,
                    claim_element_text,
                    support_kind,
                    query_text,
                    status,
                    metadata,
                    timestamp
                FROM claim_follow_up_execution
                WHERE {' AND '.join(where_clauses)}
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
            conn.close()
        except Exception as exc:
            self.mediator.log('claim_follow_up_recent_history_error', error=str(exc))
            return self._with_intake_summary_handoff({
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': normalized_limit,
                'claims': {},
                'error': str(exc),
            })

        claim_entries: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            metadata = json.loads(row[7]) if row[7] else {}
            entry = {
                'execution_id': row[0],
                'claim_type': row[1],
                'claim_element_id': row[2],
                'claim_element_text': row[3],
                'support_kind': row[4],
                'query_text': row[5],
                'status': row[6],
                'timestamp': row[8].isoformat() if hasattr(row[8], 'isoformat') else row[8],
                'metadata': metadata,
                'execution_mode': metadata.get('execution_mode', ''),
                'validation_status': metadata.get('validation_status', ''),
                'follow_up_focus': metadata.get('follow_up_focus', ''),
                'query_strategy': metadata.get('query_strategy', ''),
                'source_preferences': dict(metadata.get('source_preferences', {}) or {}),
                'time_window': dict(metadata.get('time_window', {}) or {}),
                'authority_intent': metadata.get('authority_intent', ''),
                'adaptive_retry_applied': bool(metadata.get('adaptive_retry_applied', False)),
                'adaptive_retry_reason': metadata.get('adaptive_retry_reason', ''),
                'adaptive_query_strategy': metadata.get('adaptive_query_strategy', ''),
                'adaptive_priority_penalty': int(metadata.get('adaptive_priority_penalty', 0) or 0),
                'result_count': int(metadata.get('result_count', 0) or 0),
                'stored_result_count': int(metadata.get('stored_result_count', 0) or 0),
                'zero_result': bool(metadata.get('zero_result', False)),
                'resolution_applied': metadata.get('resolution_applied', ''),
                'recommended_action': metadata.get('recommended_action', ''),
                'support_quality_summary': dict(metadata.get('support_quality_summary', {}) or {}),
                'quality_signal_counts': dict(metadata.get('quality_signal_counts', {}) or {}),
                'primary_quality_signal': dict(metadata.get('primary_quality_signal', {}) or {}),
                'quality_follow_up_action': metadata.get('quality_follow_up_action', ''),
                'ontology_quality': dict(metadata.get('ontology_quality', {}) or {}),
                'ontology_gap_types': list(metadata.get('ontology_gap_types', []) or []),
                'ontology_quality_gap_count': int(metadata.get('ontology_quality_gap_count', 0) or 0),
                'ontology_has_blocking_gaps': bool(metadata.get('ontology_has_blocking_gaps', False)),
                'skip_reason': metadata.get('skip_reason', ''),
                'resolution_status': metadata.get('resolution_status', ''),
                'resolution_notes': metadata.get('resolution_notes', ''),
                'related_execution_id': metadata.get('related_execution_id'),
                'selected_search_program_id': metadata.get('selected_search_program_id', ''),
                'selected_search_program_type': metadata.get('selected_search_program_type', ''),
                'selected_search_program_bias': metadata.get('selected_search_program_bias', ''),
                'selected_search_program_rule_bias': metadata.get('selected_search_program_rule_bias', ''),
                'selected_search_program_graph_gap_bias': metadata.get('selected_search_program_graph_gap_bias', ''),
                'selected_search_program_families': list(metadata.get('selected_search_program_families', []) or []),
                'source_family': metadata.get('source_family', ''),
                'record_scope': metadata.get('record_scope', ''),
                'artifact_family': metadata.get('artifact_family', ''),
                'corpus_family': metadata.get('corpus_family', ''),
                'content_origin': metadata.get('content_origin', ''),
                'graph_support_summary': dict(metadata.get('graph_support_summary', {}) or {}),
                'graph_gap_context': dict(metadata.get('graph_gap_context', {}) or {}),
                'graph_gap_query': dict(metadata.get('graph_gap_query', {}) or {}),
            }
            current_claim = str(row[1] or '')
            claim_entries.setdefault(current_claim, []).append(entry)

        return self._with_intake_summary_handoff({
            'user_id': user_id,
            'claim_type': claim_type,
            'limit': normalized_limit,
            'claims': claim_entries,
        })

    def save_testimony_record(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
        raw_narrative: Optional[str] = None,
        event_date: Optional[str] = None,
        actor: Optional[str] = None,
        act: Optional[str] = None,
        target: Optional[str] = None,
        harm: Optional[str] = None,
        firsthand_status: Optional[str] = None,
        source_confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'recorded': False,
                'claim_type': claim_type,
                'error': 'duckdb_unavailable',
            }

        resolved_element = self.resolve_claim_element(
            user_id,
            claim_type,
            claim_element_id=claim_element_id,
            claim_element_text=claim_element_text,
            support_label=raw_narrative,
            metadata=metadata,
        )

        normalized_payload = {
            'claim_element_id': str(
                resolved_element.get('claim_element_id') or claim_element_id or ''
            ),
            'claim_element_text': str(
                resolved_element.get('claim_element_text') or claim_element_text or ''
            ),
            'raw_narrative': str(raw_narrative or '').strip(),
            'event_date': str(event_date or '').strip(),
            'actor': str(actor or '').strip(),
            'act': str(act or '').strip(),
            'target': str(target or '').strip(),
            'harm': str(harm or '').strip(),
            'firsthand_status': str(firsthand_status or 'unknown').strip() or 'unknown',
            'source_confidence': source_confidence,
            'metadata': _merge_intake_summary_handoff_metadata(
                dict(metadata or {}),
                self.mediator,
            ),
        }
        has_content = any(
            normalized_payload[field]
            for field in ('raw_narrative', 'event_date', 'actor', 'act', 'target', 'harm')
        )
        if not has_content:
            return {
                'available': True,
                'recorded': False,
                'claim_type': claim_type,
                'error': 'empty_testimony',
            }

        created_at = datetime.now(timezone.utc).isoformat()
        testimony_id = self._make_testimony_id(
            user_id=user_id,
            claim_type=claim_type,
            claim_element_id=normalized_payload['claim_element_id'],
            raw_narrative=normalized_payload['raw_narrative'],
            created_at=created_at,
        )

        try:
            conn = duckdb.connect(self.db_path)
            row = conn.execute(
                """
                INSERT INTO claim_testimony (
                    testimony_id,
                    user_id,
                    claim_type,
                    claim_element_id,
                    claim_element_text,
                    raw_narrative,
                    event_date,
                    actor_name,
                    act_text,
                    target_text,
                    harm_text,
                    firsthand_status,
                    source_confidence,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id, timestamp
                """,
                [
                    testimony_id,
                    user_id,
                    claim_type,
                    normalized_payload['claim_element_id'] or None,
                    normalized_payload['claim_element_text'] or None,
                    normalized_payload['raw_narrative'] or None,
                    normalized_payload['event_date'] or None,
                    normalized_payload['actor'] or None,
                    normalized_payload['act'] or None,
                    normalized_payload['target'] or None,
                    normalized_payload['harm'] or None,
                    normalized_payload['firsthand_status'] or None,
                    normalized_payload['source_confidence'],
                    json.dumps(normalized_payload['metadata'], default=str),
                ],
            ).fetchone()
            conn.close()
        except Exception as exc:
            self.mediator.log('claim_testimony_save_error', error=str(exc), claim_type=claim_type)
            return {
                'available': False,
                'recorded': False,
                'claim_type': claim_type,
                'error': str(exc),
            }

        return {
            'available': True,
            'recorded': True,
            'record_id': row[0],
            'timestamp': row[1].isoformat() if hasattr(row[1], 'isoformat') else row[1],
            'testimony_id': testimony_id,
            'user_id': user_id,
            'claim_type': claim_type,
            **normalized_payload,
        }

    def _resolve_testimony_claim_element(
        self,
        *,
        record_id: Optional[int],
        row_user_id: Optional[str],
        claim_type: Optional[str],
        claim_element_id: Optional[str],
        claim_element_text: Optional[str],
        raw_narrative: Optional[str],
        entry_metadata: Optional[Dict[str, Any]],
        conn=None,
        persist_updates: bool = False,
    ) -> Dict[str, Any]:
        resolved_claim_element_id = claim_element_id
        resolved_claim_element_text = claim_element_text
        backfilled = False

        if not str(resolved_claim_element_id or '').strip() and str(claim_type or '').strip():
            resolved_element = self.resolve_claim_element(
                str(row_user_id or ''),
                str(claim_type or ''),
                claim_element_text=str(claim_element_text or '').strip() or None,
                support_label=str(raw_narrative or '').strip() or None,
                metadata=entry_metadata,
            )
            candidate_element_id = str(resolved_element.get('claim_element_id') or '').strip()
            if candidate_element_id:
                resolved_claim_element_id = candidate_element_id
                resolved_claim_element_text = (
                    resolved_element.get('claim_element_text')
                    or resolved_claim_element_text
                )
                backfilled = True
                if persist_updates and conn is not None and record_id is not None:
                    conn.execute(
                        """
                        UPDATE claim_testimony
                        SET claim_element_id = ?, claim_element_text = ?
                        WHERE id = ?
                        """,
                        [
                            resolved_claim_element_id,
                            resolved_claim_element_text or None,
                            record_id,
                        ],
                    )

        return {
            'claim_element_id': resolved_claim_element_id,
            'claim_element_text': resolved_claim_element_text,
            'backfilled': backfilled,
        }

    def backfill_claim_testimony_links(
        self,
        user_id: Optional[str] = None,
        claim_type: Optional[str] = None,
        *,
        limit: int = 0,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        normalized_limit = max(0, int(limit or 0))
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': normalized_limit,
                'dry_run': bool(dry_run),
                'scanned_count': 0,
                'candidate_count': 0,
                'updated_count': 0,
                'records': [],
            }

        where_clauses = ["(claim_element_id IS NULL OR TRIM(claim_element_id) = '')"]
        parameters: List[Any] = []
        if user_id:
            where_clauses.append('user_id = ?')
            parameters.append(user_id)
        if claim_type:
            where_clauses.append('claim_type = ?')
            parameters.append(claim_type)

        limit_clause = ''
        if normalized_limit:
            limit_clause = 'LIMIT ?'
            parameters.append(normalized_limit)

        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    user_id,
                    testimony_id,
                    claim_type,
                    claim_element_id,
                    claim_element_text,
                    raw_narrative,
                    metadata,
                    timestamp
                FROM claim_testimony
                WHERE {' AND '.join(where_clauses)}
                ORDER BY timestamp DESC, id DESC
                {limit_clause}
                """,
                parameters,
            ).fetchall()
        except Exception as exc:
            self.mediator.log('claim_testimony_backfill_error', error=str(exc), claim_type=claim_type)
            return {
                'available': False,
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': normalized_limit,
                'dry_run': bool(dry_run),
                'scanned_count': 0,
                'candidate_count': 0,
                'updated_count': 0,
                'records': [],
                'error': str(exc),
            }

        updated_records: List[Dict[str, Any]] = []
        for row in rows:
            entry_metadata = json.loads(row[7]) if row[7] else {}
            resolved = self._resolve_testimony_claim_element(
                record_id=row[0],
                row_user_id=row[1],
                claim_type=row[3],
                claim_element_id=row[4],
                claim_element_text=row[5],
                raw_narrative=row[6],
                entry_metadata=entry_metadata,
                conn=conn,
                persist_updates=not dry_run,
            )
            if not resolved['backfilled']:
                continue
            updated_records.append({
                'record_id': row[0],
                'user_id': row[1],
                'testimony_id': row[2],
                'claim_type': row[3],
                'claim_element_id': resolved['claim_element_id'],
                'claim_element_text': resolved['claim_element_text'],
                'timestamp': row[8].isoformat() if hasattr(row[8], 'isoformat') else row[8],
            })

        conn.close()

        return {
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'limit': normalized_limit,
            'dry_run': bool(dry_run),
            'scanned_count': len(rows),
            'candidate_count': len(updated_records),
            'updated_count': 0 if dry_run else len(updated_records),
            'records': updated_records,
        }

    def get_claim_testimony_records(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        normalized_limit = max(0, int(limit or 0))
        if not DUCKDB_AVAILABLE:
            return self._with_intake_summary_handoff({
                'available': False,
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': normalized_limit,
                'claims': {},
                'summary': {},
            })

        where_clauses = ['user_id = ?']
        parameters: List[Any] = [user_id]
        if claim_type:
            where_clauses.append('claim_type = ?')
            parameters.append(claim_type)
        if claim_element_id:
            where_clauses.append('claim_element_id = ?')
            parameters.append(claim_element_id)
        parameters.append(normalized_limit)

        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    testimony_id,
                    claim_type,
                    claim_element_id,
                    claim_element_text,
                    raw_narrative,
                    event_date,
                    actor_name,
                    act_text,
                    target_text,
                    harm_text,
                    firsthand_status,
                    source_confidence,
                    metadata,
                    timestamp
                FROM claim_testimony
                WHERE {' AND '.join(where_clauses)}
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        except Exception as exc:
            self.mediator.log('claim_testimony_query_error', error=str(exc), claim_type=claim_type)
            return self._with_intake_summary_handoff({
                'available': False,
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': normalized_limit,
                'claims': {},
                'summary': {},
                'error': str(exc),
            })

        claim_entries: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            entry_metadata = json.loads(row[13]) if row[13] else {}
            resolved = self._resolve_testimony_claim_element(
                record_id=row[0],
                row_user_id=user_id,
                claim_type=row[2],
                claim_element_id=row[3],
                claim_element_text=row[4],
                raw_narrative=row[5],
                entry_metadata=entry_metadata,
                conn=conn,
                persist_updates=True,
            )

            entry = {
                'record_id': row[0],
                'testimony_id': row[1],
                'claim_type': row[2],
                'claim_element_id': resolved['claim_element_id'],
                'claim_element_text': resolved['claim_element_text'],
                'raw_narrative': row[5] or '',
                'event_date': row[6] or '',
                'actor': row[7] or '',
                'act': row[8] or '',
                'target': row[9] or '',
                'harm': row[10] or '',
                'firsthand_status': row[11] or '',
                'source_confidence': row[12],
                'metadata': entry_metadata,
                'timestamp': row[14].isoformat() if hasattr(row[14], 'isoformat') else row[14],
            }
            current_claim = str(row[2] or '')
            claim_entries.setdefault(current_claim, []).append(entry)

        conn.close()

        return self._with_intake_summary_handoff({
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'limit': normalized_limit,
            'claims': claim_entries,
            'summary': {
                current_claim: self._summarize_testimony_records(entries)
                for current_claim, entries in claim_entries.items()
            },
        })

    # --- M2: Fact Registry and Element Support Ledger ---

    def persist_fact_record(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
        proposition_text: str,
        source_artifact_id: str = '',
        source_authority_id: str = '',
        source_testimony_id: str = '',
        chunk_ref: str = '',
        span_ref: str = '',
        confidence: float = 0.0,
        validation_state: str = 'unvalidated',
        uncertainty_flag: bool = False,
        contradiction_flag: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Persist a durable fact record linked to a claim element.

        Returns ``{fact_id, record_id, created}`` whether or not DuckDB is
        available.  When DuckDB is unavailable the record is held in memory so
        that callers can still obtain a stable ``fact_id`` for the session.
        """
        if not proposition_text or not proposition_text.strip():
            return {
                'available': DUCKDB_AVAILABLE,
                'recorded': False,
                'claim_type': claim_type,
                'error': 'empty_proposition_text',
            }

        resolved_element = self.resolve_claim_element(
            user_id,
            claim_type,
            claim_element_id=claim_element_id,
            claim_element_text=claim_element_text,
        )
        resolved_element_id = claim_element_id or resolved_element.get('claim_element_id', '')
        resolved_element_text = claim_element_text or resolved_element.get('claim_element_text', '')

        normalized_validation_state = str(validation_state or 'unvalidated') or 'unvalidated'
        if normalized_validation_state not in (
            'unvalidated', 'confirmed', 'contradicted', 'uncertain', 'exception_barred'
        ):
            normalized_validation_state = 'unvalidated'

        fact_id = self._make_fact_id(
            user_id=user_id,
            claim_type=claim_type,
            claim_element_id=resolved_element_id,
            proposition_text=proposition_text.strip(),
            source_artifact_id=source_artifact_id,
            source_authority_id=source_authority_id,
            source_testimony_id=source_testimony_id,
            chunk_ref=chunk_ref,
        )

        normalized_metadata = _merge_intake_summary_handoff_metadata(
            dict(metadata or {}),
            self.mediator,
        )

        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'recorded': False,
                'fact_id': fact_id,
                'claim_type': claim_type,
                'error': 'duckdb_unavailable',
            }

        try:
            conn = duckdb.connect(self.db_path)
            existing = conn.execute(
                'SELECT id FROM claim_facts WHERE fact_id = ? LIMIT 1',
                [fact_id],
            ).fetchone()
            if existing:
                conn.close()
                return {
                    'available': True,
                    'recorded': False,
                    'fact_id': fact_id,
                    'record_id': existing[0],
                    'claim_type': claim_type,
                    'created': False,
                    'reused': True,
                }
            row = conn.execute(
                """
                INSERT INTO claim_facts (
                    fact_id, user_id, claim_type,
                    claim_element_id, claim_element_text,
                    proposition_text,
                    source_artifact_id, source_authority_id, source_testimony_id,
                    chunk_ref, span_ref,
                    confidence, validation_state,
                    uncertainty_flag, contradiction_flag,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id, timestamp
                """,
                [
                    fact_id,
                    user_id,
                    claim_type,
                    resolved_element_id or None,
                    resolved_element_text or None,
                    proposition_text.strip(),
                    source_artifact_id or None,
                    source_authority_id or None,
                    source_testimony_id or None,
                    chunk_ref or None,
                    span_ref or None,
                    float(confidence or 0.0),
                    normalized_validation_state,
                    bool(uncertainty_flag),
                    bool(contradiction_flag),
                    json.dumps(normalized_metadata, default=str),
                ],
            ).fetchone()
            conn.close()
            self.mediator.log(
                'claim_fact_persisted',
                fact_id=fact_id,
                claim_type=claim_type,
                claim_element_id=resolved_element_id,
                validation_state=normalized_validation_state,
            )
            return {
                'available': True,
                'recorded': True,
                'fact_id': fact_id,
                'record_id': row[0],
                'timestamp': row[1].isoformat() if hasattr(row[1], 'isoformat') else row[1],
                'claim_type': claim_type,
                'claim_element_id': resolved_element_id,
                'claim_element_text': resolved_element_text,
                'proposition_text': proposition_text.strip(),
                'validation_state': normalized_validation_state,
                'uncertainty_flag': bool(uncertainty_flag),
                'contradiction_flag': bool(contradiction_flag),
                'confidence': float(confidence or 0.0),
                'created': True,
                'reused': False,
            }
        except Exception as exc:
            self.mediator.log('claim_fact_persist_error', error=str(exc), claim_type=claim_type)
            return {
                'available': False,
                'recorded': False,
                'fact_id': fact_id,
                'claim_type': claim_type,
                'error': str(exc),
            }

    def add_fact_link(
        self,
        fact_id: str,
        link_kind: str,
        target_id: str,
        *,
        target_type: str = '',
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a link record from a fact to an element, authority, or testimony.

        ``link_kind`` should be one of ``to_element``, ``to_authority``,
        ``to_testimony``, or ``to_chunk``.
        """
        if not fact_id or not target_id:
            return {'recorded': False, 'error': 'missing_fact_id_or_target_id'}

        normalized_link_kind = str(link_kind or '').strip()
        if normalized_link_kind not in ('to_element', 'to_authority', 'to_testimony', 'to_chunk'):
            normalized_link_kind = str(link_kind or 'to_element')

        link_id = self._make_fact_link_id(fact_id, normalized_link_kind, target_id)

        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'recorded': False,
                'link_id': link_id,
                'fact_id': fact_id,
                'error': 'duckdb_unavailable',
            }

        try:
            conn = duckdb.connect(self.db_path)
            existing = conn.execute(
                'SELECT id FROM claim_fact_links WHERE link_id = ? LIMIT 1',
                [link_id],
            ).fetchone()
            if existing:
                conn.close()
                return {
                    'available': True,
                    'recorded': False,
                    'link_id': link_id,
                    'fact_id': fact_id,
                    'created': False,
                    'reused': True,
                }
            row = conn.execute(
                """
                INSERT INTO claim_fact_links (
                    link_id, fact_id, link_kind, target_id, target_type, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                [
                    link_id,
                    fact_id,
                    normalized_link_kind,
                    target_id,
                    target_type or None,
                    json.dumps(metadata or {}, default=str),
                ],
            ).fetchone()
            conn.close()
            self.mediator.log(
                'claim_fact_link_added',
                link_id=link_id,
                fact_id=fact_id,
                link_kind=normalized_link_kind,
                target_id=target_id,
            )
            return {
                'available': True,
                'recorded': True,
                'link_id': link_id,
                'record_id': row[0],
                'fact_id': fact_id,
                'link_kind': normalized_link_kind,
                'target_id': target_id,
                'target_type': target_type,
                'created': True,
                'reused': False,
            }
        except Exception as exc:
            self.mediator.log('claim_fact_link_error', error=str(exc), fact_id=fact_id)
            return {
                'available': False,
                'recorded': False,
                'link_id': link_id,
                'fact_id': fact_id,
                'error': str(exc),
            }

    def get_fact_records(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        claim_element_id: Optional[str] = None,
        include_links: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return persisted durable fact records, optionally filtered to one element.

        When ``include_links`` is True each fact entry includes a ``links``
        list of the associated link records (element, authority, testimony,
        chunk linkages).
        """
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            if claim_type and claim_element_id:
                rows = conn.execute(
                    """
                    SELECT id, fact_id, user_id, claim_type,
                           claim_element_id, claim_element_text,
                           proposition_text,
                           source_artifact_id, source_authority_id, source_testimony_id,
                           chunk_ref, span_ref,
                           confidence, validation_state,
                           uncertainty_flag, contradiction_flag,
                           metadata, timestamp
                    FROM claim_facts
                    WHERE user_id = ?
                      AND claim_type = ?
                      AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                    ORDER BY id ASC
                    """,
                    [user_id, claim_type, claim_element_id],
                ).fetchall()
            elif claim_type:
                rows = conn.execute(
                    """
                    SELECT id, fact_id, user_id, claim_type,
                           claim_element_id, claim_element_text,
                           proposition_text,
                           source_artifact_id, source_authority_id, source_testimony_id,
                           chunk_ref, span_ref,
                           confidence, validation_state,
                           uncertainty_flag, contradiction_flag,
                           metadata, timestamp
                    FROM claim_facts
                    WHERE user_id = ?
                      AND claim_type = ?
                    ORDER BY id ASC
                    """,
                    [user_id, claim_type],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, fact_id, user_id, claim_type,
                           claim_element_id, claim_element_text,
                           proposition_text,
                           source_artifact_id, source_authority_id, source_testimony_id,
                           chunk_ref, span_ref,
                           confidence, validation_state,
                           uncertainty_flag, contradiction_flag,
                           metadata, timestamp
                    FROM claim_facts
                    WHERE user_id = ?
                    ORDER BY id ASC
                    """,
                    [user_id],
                ).fetchall()

            facts: List[Dict[str, Any]] = []
            for row in rows:
                raw_meta = row[16]
                try:
                    meta = json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
                except Exception:
                    meta = {}
                entry: Dict[str, Any] = {
                    'record_id': row[0],
                    'fact_id': row[1],
                    'user_id': row[2],
                    'claim_type': row[3],
                    'claim_element_id': row[4] or '',
                    'claim_element_text': row[5] or '',
                    'proposition_text': row[6] or '',
                    'source_artifact_id': row[7] or '',
                    'source_authority_id': row[8] or '',
                    'source_testimony_id': row[9] or '',
                    'chunk_ref': row[10] or '',
                    'span_ref': row[11] or '',
                    'confidence': float(row[12] or 0.0),
                    'validation_state': row[13] or 'unvalidated',
                    'uncertainty_flag': bool(row[14]),
                    'contradiction_flag': bool(row[15]),
                    'metadata': meta,
                    'timestamp': row[17].isoformat() if hasattr(row[17], 'isoformat') else row[17],
                    'links': [],
                }
                facts.append(entry)

            if include_links and facts:
                fact_ids = [f['fact_id'] for f in facts]
                placeholders = ', '.join('?' * len(fact_ids))
                link_rows = conn.execute(
                    f"""
                    SELECT id, link_id, fact_id, link_kind, target_id, target_type, metadata, timestamp
                    FROM claim_fact_links
                    WHERE fact_id IN ({placeholders})
                    ORDER BY id ASC
                    """,
                    fact_ids,
                ).fetchall()

                links_by_fact: Dict[str, List[Dict[str, Any]]] = {}
                for lr in link_rows:
                    raw_lmeta = lr[6]
                    try:
                        lmeta = json.loads(raw_lmeta) if isinstance(raw_lmeta, str) else (raw_lmeta or {})
                    except Exception:
                        lmeta = {}
                    link_entry = {
                        'record_id': lr[0],
                        'link_id': lr[1],
                        'fact_id': lr[2],
                        'link_kind': lr[3],
                        'target_id': lr[4],
                        'target_type': lr[5] or '',
                        'metadata': lmeta,
                        'timestamp': lr[7].isoformat() if hasattr(lr[7], 'isoformat') else lr[7],
                    }
                    links_by_fact.setdefault(lr[2], []).append(link_entry)

                for fact_entry in facts:
                    fact_entry['links'] = links_by_fact.get(fact_entry['fact_id'], [])

            conn.close()
            return facts
        except Exception as exc:
            self.mediator.log('claim_fact_records_error', error=str(exc), claim_type=claim_type)
            return []

    def get_element_support_ledger(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a support ledger for an element keyed by concrete fact IDs.

        The ledger can be used to explain element status without re-parsing:
        every entry is a persisted durable fact record with its source
        provenance and link records.  Falls back to an empty ledger when
        DuckDB is unavailable.
        """
        resolved_element_id = claim_element_id
        if not resolved_element_id and claim_element_text:
            resolved = self.resolve_claim_element(
                user_id,
                claim_type,
                claim_element_text=claim_element_text,
            )
            resolved_element_id = resolved.get('claim_element_id', '')

        facts = self.get_fact_records(
            user_id,
            claim_type,
            claim_element_id=resolved_element_id,
            include_links=True,
        )

        confirmed_count = 0
        contradicted_count = 0
        uncertain_count = 0
        exception_barred_count = 0
        unvalidated_count = 0
        uncertainty_flagged_count = 0
        contradiction_flagged_count = 0
        ledger_entries: Dict[str, Dict[str, Any]] = {}

        for fact in facts:
            vs = fact.get('validation_state', 'unvalidated')
            if vs == 'confirmed':
                confirmed_count += 1
            elif vs == 'contradicted':
                contradicted_count += 1
            elif vs == 'uncertain':
                uncertain_count += 1
            elif vs == 'exception_barred':
                exception_barred_count += 1
            else:
                unvalidated_count += 1
            if fact.get('uncertainty_flag'):
                uncertainty_flagged_count += 1
            if fact.get('contradiction_flag'):
                contradiction_flagged_count += 1

            fid = fact['fact_id']
            ledger_entries[fid] = {
                'fact_id': fid,
                'proposition_text': fact.get('proposition_text', ''),
                'claim_element_id': fact.get('claim_element_id', ''),
                'claim_element_text': fact.get('claim_element_text', ''),
                'source_artifact_id': fact.get('source_artifact_id', ''),
                'source_authority_id': fact.get('source_authority_id', ''),
                'source_testimony_id': fact.get('source_testimony_id', ''),
                'chunk_ref': fact.get('chunk_ref', ''),
                'span_ref': fact.get('span_ref', ''),
                'confidence': fact.get('confidence', 0.0),
                'validation_state': vs,
                'uncertainty_flag': fact.get('uncertainty_flag', False),
                'contradiction_flag': fact.get('contradiction_flag', False),
                'links': fact.get('links', []),
                'timestamp': fact.get('timestamp', ''),
            }

        total_facts = len(facts)
        overall_status: str
        if total_facts == 0:
            overall_status = 'missing'
        elif contradicted_count > 0 or contradiction_flagged_count > 0:
            overall_status = 'contradicted'
        elif exception_barred_count > 0:
            overall_status = 'exception_barred'
        elif uncertain_count > 0 or uncertainty_flagged_count > 0:
            overall_status = 'uncertain'
        elif confirmed_count > 0:
            overall_status = 'confirmed'
        else:
            overall_status = 'unvalidated'

        return {
            'available': DUCKDB_AVAILABLE,
            'claim_type': claim_type,
            'claim_element_id': resolved_element_id or '',
            'claim_element_text': claim_element_text or '',
            'total_facts': total_facts,
            'confirmed_count': confirmed_count,
            'contradicted_count': contradicted_count,
            'uncertain_count': uncertain_count,
            'exception_barred_count': exception_barred_count,
            'unvalidated_count': unvalidated_count,
            'uncertainty_flagged_count': uncertainty_flagged_count,
            'contradiction_flagged_count': contradiction_flagged_count,
            'overall_status': overall_status,
            'facts': ledger_entries,
        }

    def persist_support_path(
        self,
        user_id: str,
        claim_type: str,
        claim_element_id: str,
        support_traces: List[Dict[str, Any]],
        *,
        path_kind: str = 'support',
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Persist a stable proof-path record for a set of support traces.

        Collects all fact IDs from the traces, generates a stable
        ``proof_path_id``, and upserts a record in ``claim_support_paths``.
        Returns ``{proof_path_id, record_id, created}``.
        """
        fact_ids: List[str] = []
        for trace in support_traces or []:
            fid = str(trace.get('fact_id') or '')
            if fid and fid not in fact_ids:
                fact_ids.append(fid)
        path_drilldown_metadata = self._build_support_path_drilldown_metadata(support_traces or [])
        support_refs = path_drilldown_metadata.get('support_refs', [])

        proof_path_id = self._make_trace_path_id(
            user_id=user_id,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            fact_ids=fact_ids,
            support_refs=support_refs if isinstance(support_refs, list) else [],
            path_kind=path_kind,
        )

        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'recorded': False,
                'proof_path_id': proof_path_id,
                'claim_type': claim_type,
                'error': 'duckdb_unavailable',
            }

        normalized_metadata = _merge_intake_summary_handoff_metadata(
            dict(metadata or {}),
            self.mediator,
        )
        support_fact_registry_summary = self._summarize_fact_registry(support_traces or [])
        normalized_metadata.setdefault('support_fact_registry_summary', support_fact_registry_summary)
        normalized_metadata.setdefault('support_trace_summary', self._summarize_support_traces(support_traces or []))
        normalized_metadata.setdefault('graph_trace_summary', path_drilldown_metadata.get('graph_trace_summary', {}))
        normalized_metadata.setdefault('path_drilldown', path_drilldown_metadata)
        for key in (
            'support_refs',
            'support_ref_count',
            'support_kinds',
            'source_families',
            'graph_ids',
            'graph_id_count',
            'graph_trace_count',
        ):
            normalized_metadata.setdefault(key, path_drilldown_metadata.get(key))

        try:
            conn = duckdb.connect(self.db_path)
            existing = conn.execute(
                'SELECT id FROM claim_support_paths WHERE proof_path_id = ? LIMIT 1',
                [proof_path_id],
            ).fetchone()
            if existing:
                conn.close()
                return {
                    'available': True,
                    'recorded': False,
                    'proof_path_id': proof_path_id,
                    'record_id': existing[0],
                    'claim_type': claim_type,
                    'claim_element_id': claim_element_id,
                    'fact_ids': fact_ids,
                    'support_refs': support_refs if isinstance(support_refs, list) else [],
                    'support_ref_count': int(path_drilldown_metadata.get('support_ref_count', 0) or 0),
                    'support_kinds': path_drilldown_metadata.get('support_kinds', []),
                    'source_families': path_drilldown_metadata.get('source_families', []),
                    'graph_ids': path_drilldown_metadata.get('graph_ids', []),
                    'graph_id_count': int(path_drilldown_metadata.get('graph_id_count', 0) or 0),
                    'graph_trace_count': int(path_drilldown_metadata.get('graph_trace_count', 0) or 0),
                    'created': False,
                    'reused': True,
                }
            row = conn.execute(
                """
                INSERT INTO claim_support_paths (
                    proof_path_id, user_id, claim_type, claim_element_id,
                    fact_ids, path_kind, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id, timestamp
                """,
                [
                    proof_path_id,
                    user_id,
                    claim_type,
                    claim_element_id or None,
                    json.dumps(fact_ids),
                    path_kind or 'support',
                    json.dumps(normalized_metadata, default=str),
                ],
            ).fetchone()
            conn.close()
            self.mediator.log(
                'claim_support_path_persisted',
                proof_path_id=proof_path_id,
                claim_type=claim_type,
                claim_element_id=claim_element_id,
                fact_count=len(fact_ids),
            )
            return {
                'available': True,
                'recorded': True,
                'proof_path_id': proof_path_id,
                'record_id': row[0],
                'timestamp': row[1].isoformat() if hasattr(row[1], 'isoformat') else row[1],
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
                'fact_ids': fact_ids,
                'support_refs': support_refs if isinstance(support_refs, list) else [],
                'support_ref_count': int(path_drilldown_metadata.get('support_ref_count', 0) or 0),
                'support_kinds': path_drilldown_metadata.get('support_kinds', []),
                'source_families': path_drilldown_metadata.get('source_families', []),
                'graph_ids': path_drilldown_metadata.get('graph_ids', []),
                'graph_id_count': int(path_drilldown_metadata.get('graph_id_count', 0) or 0),
                'graph_trace_count': int(path_drilldown_metadata.get('graph_trace_count', 0) or 0),
                'support_fact_registry_summary': support_fact_registry_summary,
                'path_kind': path_kind,
                'created': True,
                'reused': False,
            }
        except Exception as exc:
            self.mediator.log('claim_support_path_error', error=str(exc), claim_type=claim_type)
            return {
                'available': False,
                'recorded': False,
                'proof_path_id': proof_path_id,
                'claim_type': claim_type,
                'error': str(exc),
            }

    # ------------------------------------------------------------------
    # M3: Graph Snapshot Persistence and Support Path Queries
    # ------------------------------------------------------------------

    def persist_typed_graph_snapshot(
        self,
        user_id: str,
        claim_type: str,
        source_kind: str,
        graph_payload: Dict[str, Any],
        *,
        graph_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Persist a graph snapshot for a typed source (testimony, evidence, law).

        Stores the snapshot in ``claim_support_snapshot`` with a stable
        ``snapshot_kind`` derived from *source_kind* and returns the snapshot ID.
        Falls back gracefully when DuckDB is unavailable.
        """
        source_kind_clean = str(source_kind or 'unknown').strip().lower()
        snapshot_kind = f'graph:{source_kind_clean}'

        entity_count = len(graph_payload.get('entities', []) or []) if isinstance(graph_payload, dict) else 0
        relationship_count = len(graph_payload.get('relationships', []) or []) if isinstance(graph_payload, dict) else 0
        source_id = str(graph_payload.get('source_id') or '') if isinstance(graph_payload, dict) else ''
        graph_metadata = graph_payload.get('metadata') if isinstance(graph_payload, dict) and isinstance(graph_payload.get('metadata'), dict) else {}
        support_facts = graph_payload.get('support_facts') if isinstance(graph_payload, dict) and isinstance(graph_payload.get('support_facts'), list) else []
        input_metadata = metadata if isinstance(metadata, dict) else {}
        fact_registry_summary = (
            dict(input_metadata.get('fact_registry_summary'))
            if isinstance(input_metadata.get('fact_registry_summary'), dict)
            else dict(graph_payload.get('fact_registry_summary'))
            if isinstance(graph_payload, dict) and isinstance(graph_payload.get('fact_registry_summary'), dict)
            else dict(graph_metadata.get('fact_registry_summary'))
            if isinstance(graph_metadata.get('fact_registry_summary'), dict)
            else self._summarize_fact_registry(support_facts)
        )

        stable_graph_id = graph_id or (
            'graph:' + hashlib.sha256(
                '|'.join([user_id, claim_type, source_kind_clean, source_id, str(entity_count), str(relationship_count)]).encode('utf-8')
            ).hexdigest()[:16]
        )
        snapshot_metadata = dict(metadata or {})
        snapshot_metadata['graph_id'] = stable_graph_id
        snapshot_metadata.setdefault('fact_registry_summary', fact_registry_summary)
        adapter_graph_snapshot = persist_graph_snapshot(
            graph_payload if isinstance(graph_payload, dict) else {},
            graph_id=stable_graph_id,
            graph_changed=True,
            existing_graph=False,
            persistence_metadata={
                **snapshot_metadata,
                'user_id': user_id,
                'claim_type': claim_type,
                'source_kind': source_kind_clean,
                'record_scope': snapshot_metadata.get('record_scope') or source_kind_clean,
                'fact_registry_summary': fact_registry_summary,
            },
        )

        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'recorded': False,
                'graph_id': stable_graph_id,
                'snapshot_kind': snapshot_kind,
                'source_kind': source_kind_clean,
                'claim_type': claim_type,
                'error': 'duckdb_unavailable',
                'graph_snapshot': adapter_graph_snapshot,
            }

        snapshot_payload = {
            'graph_id': stable_graph_id,
            'source_kind': source_kind_clean,
            'entity_count': entity_count,
            'relationship_count': relationship_count,
            'source_id': source_id,
            'entities': graph_payload.get('entities', []) if isinstance(graph_payload, dict) else [],
            'relationships': graph_payload.get('relationships', []) if isinstance(graph_payload, dict) else [],
            'fact_registry_summary': fact_registry_summary,
            'graph_snapshot': adapter_graph_snapshot,
        }
        snapshot_metadata['graph_snapshot'] = adapter_graph_snapshot

        try:
            conn = duckdb.connect(self.db_path)
            row = conn.execute(
                """
                INSERT INTO claim_support_snapshot (
                    user_id, claim_type, snapshot_kind,
                    required_support_kinds, payload, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING id, timestamp
                """,
                [
                    user_id,
                    claim_type,
                    snapshot_kind,
                    json.dumps([], default=str),
                    json.dumps(snapshot_payload, default=str),
                    json.dumps(snapshot_metadata, default=str),
                ],
            ).fetchone()
            conn.close()
            self.mediator.log(
                'typed_graph_snapshot_persisted',
                graph_id=stable_graph_id,
                snapshot_kind=snapshot_kind,
                claim_type=claim_type,
                entity_count=entity_count,
            )
            return {
                'available': True,
                'recorded': True,
                'graph_id': stable_graph_id,
                'snapshot_kind': snapshot_kind,
                'source_kind': source_kind_clean,
                'snapshot_id': row[0] if row else None,
                'claim_type': claim_type,
                'entity_count': entity_count,
                'relationship_count': relationship_count,
                'fact_registry_summary': fact_registry_summary,
                'graph_snapshot': adapter_graph_snapshot,
                'created': True,
                'reused': False,
            }
        except Exception as exc:
            self.mediator.log('typed_graph_snapshot_error', error=str(exc), claim_type=claim_type)
            return {
                'available': False,
                'recorded': False,
                'graph_id': stable_graph_id,
                'snapshot_kind': snapshot_kind,
                'source_kind': source_kind_clean,
                'claim_type': claim_type,
                'error': str(exc),
                'graph_snapshot': adapter_graph_snapshot,
            }

    def resume_factual_graph(self, graph_id: str) -> Dict[str, Any]:
        """Reopen committed graph revisions without publishing plaintext."""
        from integrations.ipfs_datasets.graphs import resume_graph_revisions

        try:
            resumed = resume_graph_revisions(graph_id)
        except Exception as exc:
            self.mediator.log('factual_graph_resume_error', error=str(exc), graph_id=graph_id)
            return {
                'available': False,
                'graph_id': graph_id,
                'revisions': [],
                'provenance': [],
                'superseded_facts': [],
                'cross_graph_links': [],
                'plaintext_publication': False,
                'error': str(exc),
            }
        resumed['available'] = True
        resumed['plaintext_publication'] = False
        return resumed

    def persist_private_factual_graph(
        self,
        graph_payload: Dict[str, Any],
        private_context: Dict[str, Any],
        *,
        graph_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Seal graph payload, source text, embeddings, and indexes before replication.

        Plaintext publication stays disabled. The knowledge-graph client catalog
        is not used for these private bytes.
        """
        from integrations.ipfs_datasets.graphs import persist_graph_snapshot

        sealed = dict(private_context or {})
        sealed.pop('publish_plaintext', None)
        result = persist_graph_snapshot(
            graph_payload if isinstance(graph_payload, dict) else {},
            graph_id=graph_id,
            private_context=sealed,
        )
        result['plaintext_publication'] = False
        self.mediator.log(
            'private_factual_graph_sealed',
            graph_id=str(graph_id or ''),
            persisted=bool(result.get('persisted')),
            plaintext_publication=False,
        )
        return result

    def get_support_paths_for_element(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
        path_kind: Optional[str] = None,
        limit: int = 50,
        include_current_traces: bool = True,
        required_support_kinds: Optional[List[str]] = None,
        ontology: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return persisted support-path records for a claim element.

        Queries ``claim_support_paths`` and returns a structured summary
        with all matching proof-path records sorted by timestamp descending.
        Falls back gracefully when DuckDB is unavailable.
        """
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'user_id': user_id,
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
                'path_kind': path_kind,
                'paths': [],
                'path_count': 0,
                'quality_summary': self._summarize_support_path_quality([]),
            }

        paths: List[Dict[str, Any]] = []
        try:
            conn = duckdb.connect(self.db_path)
            # where_clauses contains only static column-name strings; all user
            # values are passed as parameterized bind arguments in `params`.
            where_clauses = ['user_id = ?', 'claim_type = ?']
            params: List[Any] = [user_id, claim_type]
            if claim_element_id:
                where_clauses.append('claim_element_id = ?')
                params.append(claim_element_id)
            if path_kind:
                where_clauses.append('path_kind = ?')
                params.append(path_kind)
            where_sql = ' AND '.join(where_clauses)
            rows = conn.execute(
                f"""
                SELECT proof_path_id, claim_element_id, fact_ids, path_kind, metadata, timestamp
                FROM claim_support_paths
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()
            conn.close()
            for row in rows:
                proof_path_id, elem_id, fact_ids_json, pk, meta_json, ts = row
                try:
                    fact_ids = json.loads(fact_ids_json) if fact_ids_json else []
                except Exception:
                    fact_ids = []
                try:
                    path_meta = json.loads(meta_json) if meta_json else {}
                except Exception:
                    path_meta = {}
                support_fact_registry_summary = (
                    path_meta.get('support_fact_registry_summary')
                    if isinstance(path_meta.get('support_fact_registry_summary'), dict)
                    else {}
                )
                path_drilldown = (
                    path_meta.get('path_drilldown')
                    if isinstance(path_meta.get('path_drilldown'), dict)
                    else {}
                )

                def _path_list(key: str) -> List[str]:
                    value = path_drilldown.get(key)
                    if not isinstance(value, list):
                        value = path_meta.get(key)
                    if not isinstance(value, list):
                        return []
                    normalized: List[str] = []
                    for item in value:
                        text = str(item or '').strip()
                        if text and text not in normalized:
                            normalized.append(text)
                    return normalized

                support_refs = _path_list('support_refs')
                support_kinds = _path_list('support_kinds')
                source_families = _path_list('source_families')
                graph_ids = _path_list('graph_ids')
                graph_trace_summary = (
                    path_drilldown.get('graph_trace_summary')
                    if isinstance(path_drilldown.get('graph_trace_summary'), dict)
                    else path_meta.get('graph_trace_summary')
                )
                graph_trace_summary = graph_trace_summary if isinstance(graph_trace_summary, dict) else {}
                graph_trace_count = int(
                    path_drilldown.get(
                        'graph_trace_count',
                        path_meta.get(
                            'graph_trace_count',
                            graph_trace_summary.get('traced_link_count', 0),
                        ),
                    )
                    or 0
                )
                paths.append({
                    'proof_path_id': proof_path_id or '',
                    'claim_element_id': elem_id or '',
                    'fact_ids': fact_ids,
                    'fact_count': len(fact_ids),
                    'support_refs': support_refs,
                    'support_ref_count': int(
                        path_drilldown.get('support_ref_count', path_meta.get('support_ref_count', len(support_refs)))
                        or 0
                    ),
                    'support_kinds': support_kinds,
                    'source_families': source_families,
                    'graph_ids': graph_ids,
                    'graph_id_count': int(
                        path_drilldown.get('graph_id_count', path_meta.get('graph_id_count', len(graph_ids)))
                        or 0
                    ),
                    'graph_trace_count': graph_trace_count,
                    'path_kind': pk or 'support',
                    'support_fact_registry_summary': support_fact_registry_summary,
                    'metadata': path_meta,
                    'timestamp': ts.isoformat() if hasattr(ts, 'isoformat') else str(ts or ''),
                    'source': 'persisted',
                    'persisted': True,
                })
        except Exception as exc:
            self.mediator.log('get_support_paths_error', error=str(exc), claim_type=claim_type)
            return {
                'available': False,
                'user_id': user_id,
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
                'path_kind': path_kind,
                'paths': [],
                'path_count': 0,
                'quality_summary': self._summarize_support_path_quality([]),
                'error': str(exc),
            }

        if include_current_traces and (path_kind is None or path_kind == 'support'):
            try:
                links = self._get_enriched_claim_support_links(user_id, claim_type)
                if claim_element_id:
                    links = [link for link in links if link.get('claim_element_id') == claim_element_id]
                current_traces = self._collect_support_traces_from_links(links)
                seen_fact_ids = {
                    str(trace.get('fact_id') or '')
                    for trace in current_traces
                    if isinstance(trace, dict) and str(trace.get('fact_id') or '')
                }
                fact_records = self.get_fact_records(
                    user_id,
                    claim_type,
                    claim_element_id=claim_element_id,
                    include_links=True,
                )
                for fact in fact_records:
                    fact_id = str(fact.get('fact_id') or '')
                    if not fact_id or fact_id in seen_fact_ids:
                        continue
                    current_traces.append(self._build_fact_record_trace(fact))
                    seen_fact_ids.add(fact_id)
                if current_traces:
                    current_path = self._build_trace_path_detail(
                        user_id=user_id,
                        claim_type=claim_type,
                        claim_element_id=claim_element_id,
                        traces=current_traces,
                        path_kind='support',
                    )
                    if current_path['proof_path_id'] not in {path.get('proof_path_id') for path in paths}:
                        paths.insert(0, current_path)
            except Exception as exc:
                self.mediator.log('get_current_support_paths_error', error=str(exc), claim_type=claim_type)

        if limit:
            paths = paths[:limit]

        paths = [
            self._score_support_path_detail(
                path,
                required_support_kinds=required_support_kinds,
                ontology=ontology,
            )
            for path in paths
            if isinstance(path, dict)
        ]
        quality_summary = self._summarize_support_path_quality(paths)

        return {
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'claim_element_id': claim_element_id,
            'path_kind': path_kind,
            'paths': paths,
            'path_count': len(paths),
            'quality_summary': quality_summary,
        }

    def get_contradiction_paths_for_element(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return persisted contradiction-path records for a claim element.

        Convenience wrapper around :meth:`get_support_paths_for_element`
        filtered to ``path_kind='contradiction'``.
        """
        return self.get_support_paths_for_element(
            user_id,
            claim_type,
            claim_element_id=claim_element_id,
            path_kind='contradiction',
            limit=limit,
        )

    def _compact_adapter_graph_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        metadata = snapshot.get('metadata', {}) if isinstance(snapshot.get('metadata'), dict) else {}
        return {
            'graph_id': snapshot.get('graph_id', ''),
            'source_id': snapshot.get('source_id', ''),
            'status': snapshot.get('status', ''),
            'node_count': int(snapshot.get('node_count', 0) or 0),
            'edge_count': int(snapshot.get('edge_count', 0) or 0),
            'fact_registry_summary': (
                snapshot.get('fact_registry_summary')
                if isinstance(snapshot.get('fact_registry_summary'), dict)
                else {}
            ),
            'metadata': {
                'persistence_scope': metadata.get('persistence_scope', ''),
                'backend_storage_available': bool(metadata.get('backend_storage_available', False)),
                'claim_type': metadata.get('claim_type', ''),
                'source_kind': metadata.get('source_kind', ''),
                'record_scope': metadata.get('record_scope', ''),
                'record_key': metadata.get('record_key', ''),
                'fact_registry_summary': (
                    metadata.get('fact_registry_summary')
                    if isinstance(metadata.get('fact_registry_summary'), dict)
                    else {}
                ),
            },
        }

    def _query_adapter_graph_snapshot_ref(self, graph_id: str) -> Dict[str, Any]:
        if not graph_id:
            return {
                'found': False,
                'snapshot_count': 0,
                'fact_registry_summary': {},
                'snapshot': {},
            }
        try:
            lookup = query_graph_snapshot(graph_id)
        except Exception as exc:
            self.mediator.log('graph_snapshot_ref_adapter_query_error', graph_id=graph_id, error=str(exc))
            return {
                'status': 'error',
                'found': False,
                'snapshot_count': 0,
                'fact_registry_summary': {},
                'snapshot': {},
                'error': str(exc),
            }

        snapshots = lookup.get('snapshots', []) if isinstance(lookup.get('snapshots'), list) else []
        first_snapshot = next((snapshot for snapshot in snapshots if isinstance(snapshot, dict)), {})
        return {
            'status': lookup.get('status', ''),
            'found': bool(lookup.get('found', False)),
            'snapshot_count': int(lookup.get('snapshot_count', 0) or 0),
            'fact_registry_summary': (
                lookup.get('fact_registry_summary')
                if isinstance(lookup.get('fact_registry_summary'), dict)
                else {}
            ),
            'snapshot': self._compact_adapter_graph_snapshot(first_snapshot) if first_snapshot else {},
            'metadata': lookup.get('metadata', {}) if isinstance(lookup.get('metadata'), dict) else {},
        }

    def get_graph_snapshot_refs_for_element(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return graph snapshot references relevant to a claim element.

        Queries ``claim_support_snapshot`` for snapshots with kind prefixed
        ``graph:`` and returns lightweight reference records (snapshot_id,
        graph_id, source_kind, entity_count, relationship_count, timestamp,
        and compact adapter registry drilldown fields when available).
        """
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                """
                SELECT id, snapshot_kind, payload, timestamp
                FROM claim_support_snapshot
                WHERE user_id = ? AND claim_type = ?
                  AND snapshot_kind LIKE 'graph:%'
                ORDER BY timestamp DESC
                LIMIT 200
                """,
                [user_id, claim_type],
            ).fetchall()
            conn.close()
        except Exception as exc:
            self.mediator.log('get_graph_snapshot_refs_error', error=str(exc))
            return []

        refs: List[Dict[str, Any]] = []
        for row in rows:
            snapshot_id, kind, payload_json, ts = row
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except Exception:
                payload = {}
            if claim_element_id:
                elem_ids = payload.get('claim_element_ids') or []
                if elem_ids and claim_element_id not in elem_ids:
                    continue
            graph_id = str(payload.get('graph_id') or '')
            graph_snapshot_query = self._query_adapter_graph_snapshot_ref(graph_id)
            refs.append({
                'snapshot_id': snapshot_id,
                'snapshot_kind': str(kind or ''),
                'source_kind': str(kind or '').replace('graph:', '', 1),
                'graph_id': graph_id,
                'entity_count': int(payload.get('entity_count', 0) or 0),
                'relationship_count': int(payload.get('relationship_count', 0) or 0),
                'fact_registry_summary': (
                    payload.get('fact_registry_summary')
                    if isinstance(payload.get('fact_registry_summary'), dict)
                    else {}
                ),
                'graph_snapshot_query': graph_snapshot_query,
                'graph_snapshot': graph_snapshot_query.get('snapshot', {}),
                'timestamp': ts.isoformat() if hasattr(ts, 'isoformat') else str(ts or ''),
            })
        return refs

    def get_support_timeline(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        claim_element_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Return support links sorted chronologically by capture/event date.

        Surfaces evidence, web archive captures, and authority records in a
        single timeline view ordered by ``captured_at`` then ``created_at``.
        Each entry includes a ``provenance`` sub-object, ``support_kind``, and
        ``support_label`` for operator drilldown.
        """
        links = self._get_enriched_claim_support_links(user_id, claim_type)
        if claim_element_id:
            links = [l for l in links if l.get('claim_element_id') == claim_element_id]

        timeline_entries: List[Dict[str, Any]] = []
        for link in links:
            traces = self._collect_support_traces_from_links([link])
            for trace in traces:
                record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
                lineage_summary = self._build_support_packet_lineage_summary(trace=trace)
                captured_at = str(
                    lineage_summary.get('captured_at')
                    or record_summary.get('captured_at')
                    or trace.get('captured_at')
                    or ''
                )
                timeline_entries.append({
                    'captured_at': captured_at,
                    'observed_at': str(lineage_summary.get('observed_at') or record_summary.get('observed_at') or ''),
                    'timestamp': str(trace.get('timestamp') or link.get('timestamp') or ''),
                    'support_kind': trace.get('support_kind'),
                    'support_label': trace.get('support_label'),
                    'support_ref': trace.get('support_ref'),
                    'source_family': trace.get('source_family', ''),
                    'claim_element_id': link.get('claim_element_id', ''),
                    'claim_element_text': link.get('claim_element_text', ''),
                    'fact': {
                        'fact_id': trace.get('fact_id', ''),
                        'text': trace.get('fact_text', ''),
                        'confidence': trace.get('confidence', 0.0),
                    },
                    'provenance': {
                        'archive_url': str(lineage_summary.get('archive_url') or record_summary.get('archive_url') or ''),
                        'capture_source': str(lineage_summary.get('capture_source') or ''),
                        'historical_capture': bool(lineage_summary.get('historical_capture', False)),
                        'content_hash': str(lineage_summary.get('content_hash') or record_summary.get('content_hash') or ''),
                        'source_domain': str(lineage_summary.get('source_domain') or record_summary.get('source_domain') or ''),
                    },
                })

        dated_entries = [entry for entry in timeline_entries if str(entry.get('captured_at') or entry.get('observed_at') or entry.get('timestamp') or '')]
        undated_entries = [entry for entry in timeline_entries if not str(entry.get('captured_at') or entry.get('observed_at') or entry.get('timestamp') or '')]
        dated_entries.sort(
            key=lambda entry: str(entry.get('captured_at') or entry.get('observed_at') or entry.get('timestamp') or ''),
            reverse=True,
        )
        timeline_entries = dated_entries + undated_entries
        if limit:
            timeline_entries = timeline_entries[:limit]

        return {
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'claim_element_id': claim_element_id,
            'entry_count': len(timeline_entries),
            'timeline': timeline_entries,
        }

    def get_archive_history(
        self,
        user_id: str,
        *,
        claim_type: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return archive captures associated with the user's web evidence.

        Aggregates archive captures from support links, grouped by source
        domain.  Useful for operator inspection of which web sources have
        been captured and when.
        """
        links = self._get_enriched_claim_support_links(user_id, claim_type)
        captures_by_domain: Dict[str, List[Dict[str, Any]]] = {}
        seen_archive_urls: set = set()

        for link in links:
            traces = self._collect_support_traces_from_links([link])
            for trace in traces:
                record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
                lineage_summary = self._build_support_packet_lineage_summary(trace=trace)
                archive_url = str(
                    lineage_summary.get('archive_url')
                    or record_summary.get('archive_url')
                    or trace.get('archive_url')
                    or ''
                )
                if not archive_url or archive_url in seen_archive_urls:
                    continue
                seen_archive_urls.add(archive_url)

                capture_source = str(lineage_summary.get('capture_source') or record_summary.get('capture_source') or 'unknown')
                captured_at = str(lineage_summary.get('captured_at') or record_summary.get('captured_at') or '')
                source_domain = str(lineage_summary.get('source_domain') or record_summary.get('source_domain') or '')

                if domain and source_domain and domain.lower() not in source_domain.lower():
                    continue
                if domain and not source_domain:
                    continue

                capture_entry = {
                    'archive_url': archive_url,
                    'capture_source': capture_source,
                    'captured_at': captured_at,
                    'source_domain': source_domain,
                    'support_kind': trace.get('support_kind'),
                    'support_ref': trace.get('support_ref'),
                    'historical_capture': bool(lineage_summary.get('historical_capture', False)),
                }
                captures_by_domain.setdefault(source_domain or 'unknown', []).append(capture_entry)

        all_captures = [
            entry
            for entries in captures_by_domain.values()
            for entry in entries
        ]
        all_captures.sort(key=lambda e: str(e.get('captured_at') or ''), reverse=True)
        if limit:
            all_captures = all_captures[:limit]
        limited_by_domain: Dict[str, List[Dict[str, Any]]] = {}
        for entry in all_captures:
            limited_by_domain.setdefault(str(entry.get('source_domain') or 'unknown'), []).append(entry)

        return {
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'domain_filter': domain,
            'capture_count': len(all_captures),
            'domain_count': len(limited_by_domain),
            'captures': all_captures,
            'captures_by_domain': limited_by_domain,
        }

    def get_graph_trace_drilldown(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        claim_element_id: Optional[str] = None,
        support_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return full graph trace details for a specific claim element or support reference.

        Provides complete entity/relation/graph-path context for operator
        investigation of why a particular support link was (or was not)
        matched through the knowledge graph.
        """
        links = self._get_enriched_claim_support_links(user_id, claim_type)
        if claim_element_id:
            links = [l for l in links if l.get('claim_element_id') == claim_element_id]
        if support_ref:
            links = [l for l in links if l.get('support_ref') == support_ref]

        graph_traces: List[Dict[str, Any]] = []
        for link in links:
            traces = self._collect_support_traces_from_links([link])
            for trace in traces:
                gt = trace.get('graph_trace', {}) if isinstance(trace.get('graph_trace'), dict) else {}
                gs = trace.get('graph_summary', {}) if isinstance(trace.get('graph_summary'), dict) else {}
                if not gt and not gs:
                    continue
                graph_traces.append({
                    'support_ref': trace.get('support_ref'),
                    'support_kind': trace.get('support_kind'),
                    'claim_element_id': link.get('claim_element_id', ''),
                    'claim_element_text': link.get('claim_element_text', ''),
                    'graph_id': trace.get('graph_id', ''),
                    'graph_trace': gt,
                    'graph_summary': gs,
                    'fact_id': trace.get('fact_id', ''),
                    'fact_text': trace.get('fact_text', ''),
                    'confidence': trace.get('confidence', 0.0),
                })

        graph_summary_totals = self._summarize_graph_traces(links)
        return {
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'claim_element_id': claim_element_id,
            'support_ref': support_ref,
            'graph_trace_count': len(graph_traces),
            'graph_traces': graph_traces,
            'graph_summary': graph_summary_totals,
        }

    def _ensure_enrichment_queue_table(self, conn: Any) -> None:
        """Create the enrichment queue table if it does not already exist."""
        conn.execute("CREATE SEQUENCE IF NOT EXISTS claim_support_id_seq START 1")
        conn.execute(_ENRICHMENT_QUEUE_DDL)

    def _connect_enrichment_queue_db(self) -> Any:
        if self.db_path == ":memory:":
            if self._enrichment_queue_memory_conn is None:
                self._enrichment_queue_memory_conn = duckdb.connect(self.db_path)
            return self._enrichment_queue_memory_conn
        return duckdb.connect(self.db_path)

    def _serialize_enrichment_queue_row(self, row: Any) -> Dict[str, Any]:
        try:
            metadata = json.loads(row[6]) if row[6] else {}
        except Exception:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        entry_status = str(row[4] or 'pending')
        return {
            'id': row[0],
            'job_id': row[0],
            'user_id': row[1],
            'claim_type': row[2],
            'enrichment_type': row[3],
            'status': entry_status,
            'priority': row[5],
            'metadata': metadata,
            'progress': metadata.get('progress', {}),
            'partial_results': metadata.get('partial_results', {}),
            'error': metadata.get('error', ''),
            'created_at': row[7].isoformat() if hasattr(row[7], 'isoformat') else str(row[7] or ''),
            'updated_at': row[8].isoformat() if hasattr(row[8], 'isoformat') else str(row[8] or ''),
        }

    def get_enrichment_queue_state(
        self,
        user_id: str,
        *,
        claim_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the state of pending enrichment jobs for *user_id*.

        Queries the ``claim_enrichment_queue`` table when available.  Falls
        back to a degraded-mode empty-queue response when the table does not
        exist, preserving backwards compatibility.
        """
        if not self._check_duckdb_availability():
            return {
                'available': False,
                'user_id': user_id,
                'claim_type': claim_type,
                'status_filter': status,
                'queue': [],
                'queue_count': 0,
                'pending_count': 0,
                'running_count': 0,
                'completed_count': 0,
            }

        self._prepare_duckdb_path()

        try:
            conn = self._connect_enrichment_queue_db()
            # Ensure the queue table exists (created lazily).
            self._ensure_enrichment_queue_table(conn)
            where_clauses = ['user_id = ?']
            parameters: List[Any] = [user_id]
            if claim_type:
                where_clauses.append('claim_type = ?')
                parameters.append(claim_type)
            if status:
                where_clauses.append('status = ?')
                parameters.append(status)

            rows = conn.execute(
                f"""
                SELECT id, user_id, claim_type, enrichment_type, status, priority, metadata, created_at, updated_at
                FROM claim_enrichment_queue
                WHERE {' AND '.join(where_clauses)}
                ORDER BY priority DESC, created_at ASC
                """,
                parameters,
            ).fetchall()
            if self.db_path != ":memory:":
                conn.close()
        except Exception as exc:
            self.mediator.log('enrichment_queue_query_error', error=str(exc))
            return {
                'available': False,
                'user_id': user_id,
                'claim_type': claim_type,
                'status_filter': status,
                'queue': [],
                'queue_count': 0,
                'pending_count': 0,
                'running_count': 0,
                'completed_count': 0,
                'error': str(exc),
            }

        queue: List[Dict[str, Any]] = []
        status_counts: Dict[str, int] = {}
        for row in rows:
            entry_status = str(row[4] or 'pending')
            status_counts[entry_status] = status_counts.get(entry_status, 0) + 1
            queue.append(self._serialize_enrichment_queue_row(row))

        return {
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'status_filter': status,
            'queue': queue,
            'queue_count': len(queue),
            'pending_count': status_counts.get('pending', 0),
            'running_count': status_counts.get('running', 0),
            'completed_count': status_counts.get('completed', 0),
            'failed_count': status_counts.get('failed', 0),
        }

    def get_background_enrichment_job(self, job_id: int, user_id: Optional[str] = None) -> Dict[str, Any]:
        if not self._check_duckdb_availability():
            return {'available': False, 'job_id': job_id}
        self._prepare_duckdb_path()
        try:
            conn = self._connect_enrichment_queue_db()
            self._ensure_enrichment_queue_table(conn)
            clauses = ['id = ?']
            parameters: List[Any] = [int(job_id)]
            if user_id:
                clauses.append('user_id = ?')
                parameters.append(user_id)
            row = conn.execute(
                f"""
                SELECT id, user_id, claim_type, enrichment_type, status, priority, metadata, created_at, updated_at
                FROM claim_enrichment_queue
                WHERE {' AND '.join(clauses)}
                """,
                parameters,
            ).fetchone()
            if self.db_path != ":memory:":
                conn.close()
            if not row:
                return {'available': False, 'job_id': job_id}
            return {'available': True, 'job': self._serialize_enrichment_queue_row(row)}
        except Exception as exc:
            self.mediator.log('enrichment_queue_job_query_error', error=str(exc), job_id=job_id)
            return {'available': False, 'job_id': job_id, 'error': str(exc)}

    def update_background_enrichment_job_status(
        self,
        job_id: int,
        status: str,
        *,
        progress: Optional[Dict[str, Any]] = None,
        partial_results: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._check_duckdb_availability():
            return {'updated': False, 'job_id': job_id}
        self._prepare_duckdb_path()
        try:
            conn = self._connect_enrichment_queue_db()
            self._ensure_enrichment_queue_table(conn)
            row = conn.execute(
                """
                SELECT metadata FROM claim_enrichment_queue WHERE id = ?
                """,
                [int(job_id)],
            ).fetchone()
            if not row:
                if self.db_path != ":memory:":
                    conn.close()
                return {'updated': False, 'job_id': job_id}
            merged_metadata = json.loads(row[0]) if row[0] else {}
            if isinstance(metadata, dict):
                merged_metadata.update(metadata)
            if progress is not None:
                merged_metadata['progress'] = progress
            if partial_results is not None:
                merged_metadata['partial_results'] = partial_results
            if error is not None:
                merged_metadata['error'] = error
            updated = conn.execute(
                """
                UPDATE claim_enrichment_queue
                SET status = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                RETURNING id, user_id, claim_type, enrichment_type, status, priority, metadata, created_at, updated_at
                """,
                [str(status or 'pending'), json.dumps(merged_metadata), int(job_id)],
            ).fetchone()
            if self.db_path != ":memory:":
                conn.close()
            return {
                'updated': bool(updated),
                'job': self._serialize_enrichment_queue_row(updated) if updated else {},
            }
        except Exception as exc:
            self.mediator.log('enrichment_queue_job_update_error', error=str(exc), job_id=job_id)
            return {'updated': False, 'job_id': job_id, 'error': str(exc)}

    def submit_background_enrichment_job(
        self,
        user_id: str,
        enrichment_type: str,
        *,
        claim_type: Optional[str] = None,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submit a background enrichment job for *user_id*.

        Inserts into the ``claim_enrichment_queue`` table with ``status='pending'``.
        The job can be inspected via :meth:`get_enrichment_queue_state` and
        consumed by background worker processes.
        """
        if not self._check_duckdb_availability():
            return {
                'submitted': False,
                'user_id': user_id,
                'enrichment_type': enrichment_type,
                'error': 'DuckDB not available',
            }

        self._prepare_duckdb_path()

        try:
            conn = self._connect_enrichment_queue_db()
            self._ensure_enrichment_queue_table(conn)
            next_id_row = conn.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM claim_enrichment_queue"
            ).fetchone()
            next_id = int(next_id_row[0]) if next_id_row else 1
            inserted = conn.execute(
                """
                INSERT INTO claim_enrichment_queue
                    (id, user_id, claim_type, enrichment_type, status, priority, metadata)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                RETURNING id
                """,
                [next_id, user_id, claim_type, enrichment_type, priority, json.dumps(metadata or {})],
            ).fetchone()
            if self.db_path != ":memory:":
                conn.close()
            job_id = inserted[0] if inserted else None
        except Exception as exc:
            self.mediator.log('enrichment_queue_submit_error', error=str(exc))
            return {
                'submitted': False,
                'user_id': user_id,
                'enrichment_type': enrichment_type,
                'error': str(exc),
            }

        return {
            'submitted': True,
            'job_id': job_id,
            'user_id': user_id,
            'claim_type': claim_type,
            'enrichment_type': enrichment_type,
            'priority': priority,
            'status': 'pending',
        }

    # -----------------------------------------------------------------------
    # M5: Legal Proof And Contradiction Engine
    # -----------------------------------------------------------------------

    _PROOF_STATE_NEXT_ACTIONS: Dict[str, str] = {
        'contradicted': 'resolve_contradiction',
        'exception_barred': 'address_exception',
        'missing': 'gather_evidence',
        'uncertain': 'validate_facts',
        'partially_supported': 'complete_proof',
        'supported': 'no_action_needed',
        'unvalidated': 'validate_facts',
    }

    def _derive_element_proof_state(
        self,
        ledger: Dict[str, Any],
        prove_result: Dict[str, Any],
        contradiction_result: Dict[str, Any],
        predicate: Dict[str, Any],
    ) -> str:
        """Classify the proof state of a single claim element.

        Priority order: contradicted > exception_barred > uncertain >
        partially_supported > supported > missing > unvalidated.
        """
        overall_ledger_status = str(ledger.get('overall_status') or 'missing')
        contradiction_count = int(contradiction_result.get('contradiction_count') or 0)
        has_contradictions = contradiction_count > 0 or contradiction_result.get('has_contradictions')
        total_facts = int(ledger.get('total_facts') or 0)
        confirmed_count = int(ledger.get('confirmed_count') or 0)
        exception_barred_count = int(ledger.get('exception_barred_count') or 0)
        uncertain_count = int(ledger.get('uncertain_count') or 0)
        unvalidated_count = int(ledger.get('unvalidated_count') or 0)

        # A contradiction anywhere in the element's predicates overrides other states.
        if has_contradictions or overall_ledger_status == 'contradicted':
            return 'contradicted'
        if exception_barred_count > 0 or overall_ledger_status == 'exception_barred':
            return 'exception_barred'
        if total_facts == 0:
            return 'missing'

        # Determine satisfaction from prove_result
        provable_elements: List[Dict[str, Any]] = list(prove_result.get('provable_elements') or [])
        unprovable_elements: List[Dict[str, Any]] = list(prove_result.get('unprovable_elements') or [])
        elem_id = str(predicate.get('claim_element_id') or '')
        is_provable = any(
            str(p.get('claim_element_id') or '') == elem_id for p in provable_elements
        ) or overall_ledger_status == 'confirmed'
        is_unprovable = any(
            str(p.get('claim_element_id') or '') == elem_id for p in unprovable_elements
        )

        if uncertain_count > 0 or unvalidated_count > 0:
            if confirmed_count > 0 or is_provable:
                return 'partially_supported'
            return 'uncertain'
        if is_unprovable and not is_provable and confirmed_count == 0:
            return 'missing'
        if is_provable or confirmed_count > 0:
            return 'supported'
        if unvalidated_count > 0:
            return 'unvalidated'
        return 'missing'

    def _build_element_proof_explanation(
        self,
        element_text: str,
        proof_state: str,
        missing_predicates: List[str],
        contradiction_sources: List[Dict[str, Any]],
        supporting_fact_count: int,
    ) -> str:
        """Build a concise human-readable proof explanation for an element."""
        if proof_state == 'contradicted':
            count = len(contradiction_sources)
            # If proof_state is 'contradicted', count should always be > 0; guard defensively.
            if count > 0:
                src_summary = f"{count} contradiction source{'s' if count != 1 else ''}"
            else:
                src_summary = "contradictory evidence in the record"
            return (
                f"'{element_text}' is contradicted by {src_summary}. "
                "Resolve the conflicting evidence before this element can be proved."
            )
        if proof_state == 'exception_barred':
            return (
                f"'{element_text}' may be barred by an exception or affirmative defense. "
                "Review the exception sources and address them in the complaint narrative."
            )
        if proof_state == 'missing':
            if missing_predicates:
                preds = ', '.join(missing_predicates[:3])
                return (
                    f"'{element_text}' has no supporting facts. "
                    f"Missing required predicates: {preds}."
                )
            return f"'{element_text}' has no supporting facts. Initial testimony or documentary evidence is required."
        if proof_state == 'uncertain':
            return (
                f"'{element_text}' has {supporting_fact_count} fact{'s' if supporting_fact_count != 1 else ''} "
                "with uncertain or unvalidated state. Validate these facts to confirm proof."
            )
        if proof_state == 'partially_supported':
            if missing_predicates:
                preds = ', '.join(missing_predicates[:3])
                return (
                    f"'{element_text}' is partially supported. "
                    f"Still missing: {preds}."
                )
            return f"'{element_text}' is partially supported. Additional evidence would strengthen the claim."
        if proof_state == 'supported':
            return (
                f"'{element_text}' is supported by {supporting_fact_count} "
                f"confirmed fact{'s' if supporting_fact_count != 1 else ''}."
            )
        return f"'{element_text}' proof state is {proof_state}."

    def get_element_proof_card(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
        coverage_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a proof card for a single claim element.

        The proof card includes:
        - ``proof_state`` — one of supported / partially_supported / missing /
          contradicted / uncertain / exception_barred / unvalidated
        - ``required_predicates`` — FOL/DCEC predicate names from the claim template
        - ``satisfied_predicates`` — predicates satisfied by confirmed facts
        - ``missing_predicates`` — required predicates not yet satisfied
        - ``supporting_facts`` — confirmed/unvalidated fact records from the ledger
        - ``contradiction_sources`` — contradiction dicts from check_contradictions
        - ``next_action`` — recommended operator action
        - ``explanation`` — concise human-readable explanation

        Degrades gracefully when logic tooling or DuckDB are unavailable.
        """
        from integrations.ipfs_datasets.logic import (
            map_claim_elements_to_predicates,
            prove_claim_elements,
            check_contradictions,
        )

        element_text = str(claim_element_text or claim_element_id or '')
        resolved_element_id = claim_element_id

        # Resolve element ID from text when not supplied
        if not resolved_element_id and claim_element_text:
            try:
                resolved = self.resolve_claim_element(
                    user_id,
                    claim_type,
                    claim_element_text=claim_element_text,
                )
                resolved_element_id = resolved.get('claim_element_id', '')
            except Exception:
                pass

        # 1. Fetch the support ledger for this element
        ledger = self.get_element_support_ledger(
            user_id,
            claim_type,
            claim_element_id=resolved_element_id or None,
            claim_element_text=claim_element_text or None,
        )
        total_facts = int(ledger.get('total_facts') or 0)
        confirmed_count = int(ledger.get('confirmed_count') or 0)
        supporting_facts = list(ledger.get('facts', {}).values())

        # 2. Map element to predicates using the claim template
        element_dict = {
            'element_id': resolved_element_id or '',
            'element_text': element_text,
            'coverage_status': coverage_status or ledger.get('overall_status') or 'missing',
        }
        predicate_map = map_claim_elements_to_predicates(claim_type, [element_dict])
        predicates = list(predicate_map.get('predicates') or [])
        predicate = predicates[0] if predicates else element_dict

        # Extract template fields — when a FOL template exists use it directly as
        # the single required predicate; fall back to expected_predicate_types otherwise.
        fol_template = str(predicate.get('fol_template') or '')
        dcec_template = str(predicate.get('dcec_template') or '')
        grounded_facts = list(predicate.get('grounded_facts') or [])
        if fol_template:
            required_predicates: List[str] = [fol_template]
        else:
            required_predicates = [
                str(pt) for pt in (predicate.get('expected_predicate_types') or ['claim_element'])
            ]

        # 3. Run prove_claim_elements on this element's predicates
        prove_result: Dict[str, Any] = {}
        try:
            prove_result = prove_claim_elements(predicates)
        except Exception as exc:
            self.mediator.log('get_element_proof_card_prove_error', error=str(exc))

        # 4. Run check_contradictions against the element's predicate payload
        contradiction_result: Dict[str, Any] = {}
        try:
            contradiction_result = check_contradictions(predicates)
        except Exception as exc:
            self.mediator.log('get_element_proof_card_contradiction_error', error=str(exc))
        contradiction_sources = list(contradiction_result.get('contradictions') or [])

        # 5. Classify proof state
        proof_state = self._derive_element_proof_state(
            ledger, prove_result, contradiction_result, predicate
        )

        # 6. Derive satisfied vs. missing predicates.
        # An element is fully satisfied when the reasoner flagged it as provable
        # OR all its ledger facts are confirmed.  Otherwise all required predicates
        # are treated as missing to avoid misleading partial mappings.
        provable_element_ids = {
            str(p.get('claim_element_id') or '') for p in (prove_result.get('provable_elements') or [])
        }
        elem_id = resolved_element_id or ''
        is_fully_satisfied = (
            (elem_id and elem_id in provable_element_ids)
            or (confirmed_count > 0 and confirmed_count >= total_facts and total_facts > 0)
        )
        satisfied_predicates: List[str] = required_predicates if is_fully_satisfied else []
        missing_predicates: List[str] = [
            p for p in required_predicates if p not in satisfied_predicates
        ]

        # 7. Build explanation
        explanation = self._build_element_proof_explanation(
            element_text,
            proof_state,
            missing_predicates,
            contradiction_sources,
            confirmed_count if confirmed_count > 0 else total_facts,
        )

        next_action = self._PROOF_STATE_NEXT_ACTIONS.get(proof_state, 'validate_facts')

        return {
            'claim_type': claim_type,
            'claim_element_id': resolved_element_id or '',
            'claim_element_text': element_text,
            'proof_state': proof_state,
            'required_predicates': required_predicates,
            'satisfied_predicates': satisfied_predicates,
            'missing_predicates': missing_predicates,
            'supporting_facts': supporting_facts,
            'supporting_fact_count': total_facts,
            'confirmed_fact_count': confirmed_count,
            'contradiction_sources': contradiction_sources,
            'contradiction_count': len(contradiction_sources),
            'next_action': next_action,
            'explanation': explanation,
            'fol_template': fol_template,
            'dcec_template': dcec_template,
            'grounded_facts': grounded_facts,
            'template_matched': bool(predicate.get('template_matched')),
            'ledger_overall_status': ledger.get('overall_status', 'missing'),
            'proof_engine_status': str(prove_result.get('proof_status') or 'skipped'),
            'logic_available': True,
        }

    def get_element_proof_cards(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return proof cards for all elements of *claim_type* (or all claims).

        Builds proof cards for every element in the coverage matrix and feeds
        the aggregate proof state back into a summary suitable for operator
        review and dashboard display.

        Each proof card contains the same fields as :meth:`get_element_proof_card`.
        """
        matrix = self.get_claim_coverage_matrix(user_id, claim_type=claim_type)
        all_cards: Dict[str, List[Dict[str, Any]]] = {}
        proof_state_totals: Dict[str, int] = {}
        total_elements = 0
        total_cards = 0

        for ct, claim_data in (matrix.get('claims') or {}).items():
            cards: List[Dict[str, Any]] = []
            for element in (claim_data.get('elements') or []):
                if not isinstance(element, dict):
                    continue
                element_id = str(element.get('element_id') or '')
                element_text = str(element.get('element_text') or '')
                coverage_status = str(element.get('status') or 'missing')
                try:
                    card = self.get_element_proof_card(
                        user_id,
                        ct,
                        claim_element_id=element_id or None,
                        claim_element_text=element_text or None,
                        coverage_status=coverage_status,
                    )
                except Exception as exc:
                    self.mediator.log('get_element_proof_cards_card_error', error=str(exc))
                    card = {
                        'claim_type': ct,
                        'claim_element_id': element_id,
                        'claim_element_text': element_text,
                        'proof_state': 'missing',
                        'error': str(exc),
                        'next_action': 'gather_evidence',
                        'explanation': f"Proof card generation failed for '{element_text}'.",
                        'required_predicates': [],
                        'satisfied_predicates': [],
                        'missing_predicates': [],
                        'supporting_facts': [],
                        'contradiction_sources': [],
                        'supporting_fact_count': 0,
                        'confirmed_fact_count': 0,
                        'contradiction_count': 0,
                    }
                proof_state_totals[card['proof_state']] = proof_state_totals.get(card['proof_state'], 0) + 1
                cards.append(card)
                total_cards += 1
            total_elements += len(cards)
            all_cards[ct] = cards

        # Derive overall case readiness from proof states
        contradicted_count = proof_state_totals.get('contradicted', 0)
        supported_count = proof_state_totals.get('supported', 0)
        missing_count = proof_state_totals.get('missing', 0) + proof_state_totals.get('unvalidated', 0)
        exception_barred_count = proof_state_totals.get('exception_barred', 0)
        incomplete_count = (
            proof_state_totals.get('partially_supported', 0)
            + proof_state_totals.get('uncertain', 0)
        )

        if contradicted_count > 0:
            overall_proof_readiness = 'contradicted'
        elif exception_barred_count > 0:
            overall_proof_readiness = 'exception_barred'
        elif total_cards > 0 and supported_count == total_cards:
            overall_proof_readiness = 'ready'
        elif supported_count > 0 or incomplete_count > 0:
            overall_proof_readiness = 'incomplete'
        elif missing_count > 0:
            overall_proof_readiness = 'missing'
        else:
            overall_proof_readiness = 'unknown'

        return self._with_intake_summary_handoff({
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'total_elements': total_elements,
            'total_cards': total_cards,
            'proof_state_totals': proof_state_totals,
            'overall_proof_readiness': overall_proof_readiness,
            'supported_count': supported_count,
            'missing_count': missing_count,
            'contradicted_count': contradicted_count,
            'exception_barred_count': exception_barred_count,
            'incomplete_count': incomplete_count,
            'cards': all_cards,
        })

    # -----------------------------------------------------------------------
    # M0: Question And Testimony Foundation
    # -----------------------------------------------------------------------

    _QUESTION_LANE_WEIGHTS: Dict[str, float] = {
        'contradiction_resolution': 1.0,
        'missing_element': 0.9,
        'adverse_authority': 0.85,
        'graph_quality_gap': 0.82,
        'testimony_gap': 0.8,
        'support_quality_gap': 0.76,
        'document_request': 0.7,
        'source_quality_gap': 0.68,
        'authority_gap': 0.65,
        'duplicate_support': 0.6,
        'coverage_improvement': 0.5,
    }

    def _quality_gap_lane_for_element(self, element: Dict[str, Any]) -> str:
        quality_summary = (
            element.get('support_quality_summary', {})
            if isinstance(element.get('support_quality_summary'), dict)
            else {}
        )
        signal_counts = (
            quality_summary.get('quality_signal_counts', {})
            if isinstance(quality_summary.get('quality_signal_counts'), dict)
            else {}
        )
        if int(quality_summary.get('structurally_missing_path_count', 0) or 0) > 0:
            return 'missing_element'
        if int(signal_counts.get('weak_graph_connectivity', 0) or 0) > 0:
            return 'graph_quality_gap'
        if int(signal_counts.get('weak_source_quality', 0) or 0) > 0:
            return 'source_quality_gap'
        if int(signal_counts.get('duplicate_support', 0) or 0) > 0:
            return 'duplicate_support'
        if (
            int(quality_summary.get('weak_support_path_count', 0) or 0) > 0
            or str(quality_summary.get('recommended_quality_action') or '') == 'strengthen_support_path'
        ):
            return 'support_quality_gap'
        return ''

    def _primary_quality_signal_for_summary(self, quality_summary: Dict[str, Any]) -> Dict[str, Any]:
        signal_counts = (
            quality_summary.get('quality_signal_counts', {})
            if isinstance(quality_summary.get('quality_signal_counts'), dict)
            else {}
        )
        prioritized = [
            ('structurally_missing_support', 'missing_element', 'collect_initial_support'),
            ('weak_graph_connectivity', 'graph_quality_gap', 'persist_or_query_graph_support'),
            ('weak_source_quality', 'source_quality_gap', 'improve_source_parse_quality'),
            ('duplicate_support', 'duplicate_support', 'collect_independent_support'),
            ('weak_support_path', 'support_quality_gap', 'strengthen_support_path'),
        ]
        for signal, lane, action in prioritized:
            count = int(signal_counts.get(signal, 0) or 0)
            if signal == 'structurally_missing_support':
                count = max(count, int(quality_summary.get('structurally_missing_path_count', 0) or 0))
            if signal == 'weak_support_path':
                count = max(count, int(quality_summary.get('weak_support_path_count', 0) or 0))
            if count > 0:
                return {
                    'signal_type': signal,
                    'question_lane': lane,
                    'follow_up_action': action,
                    'count': count,
                }
        recommended_action = str(quality_summary.get('recommended_quality_action') or '')
        if recommended_action:
            return {
                'signal_type': 'recommended_quality_action',
                'question_lane': 'support_quality_gap',
                'follow_up_action': recommended_action,
                'count': 1,
            }
        return {}

    def _question_lane_for_element(self, element: Dict[str, Any]) -> str:
        """Determine the most important question lane for an unresolved element."""
        action = str(element.get('recommended_action') or '')
        authority_treatment = element.get('authority_treatment_summary', {}) if isinstance(
            element.get('authority_treatment_summary'), dict
        ) else {}
        if int(authority_treatment.get('adverse_authority_link_count', 0) or 0) > 0:
            return 'adverse_authority'
        if action == 'collect_initial_support':
            return 'missing_element'
        if action == 'collect_fact_support':
            return 'testimony_gap'
        quality_lane = self._quality_gap_lane_for_element(element)
        if quality_lane:
            return quality_lane
        if action == 'collect_missing_support_kind':
            missing = list(element.get('missing_support_kinds', []) or [])
            if 'evidence' in missing or 'testimony' in missing:
                return 'document_request'
            if 'authority' in missing:
                return 'authority_gap'
        return 'coverage_improvement'

    def _question_type_for_lane(self, lane: str) -> str:
        """Map a question lane to testimony vs. document_request."""
        if lane in ('missing_element', 'testimony_gap', 'contradiction_resolution', 'graph_quality_gap', 'support_quality_gap'):
            return 'testimony'
        if lane in ('document_request', 'source_quality_gap', 'duplicate_support'):
            return 'document_request'
        if lane in ('adverse_authority', 'authority_gap'):
            return 'document_request'
        return 'testimony'

    def _question_reason_for_element(
        self, element: Dict[str, Any], lane: str, contradiction_element_ids: List[str]
    ) -> str:
        """Build a human-readable explanation for why this question is recommended."""
        element_text = str(element.get('element_text') or '')
        missing = list(element.get('missing_support_kinds', []) or [])
        if lane == 'contradiction_resolution' or element.get('element_id') in contradiction_element_ids:
            return f"Contradictory evidence has been detected for '{element_text}'. Testimony is needed to resolve the conflict."
        if lane == 'missing_element':
            return f"'{element_text}' has no supporting evidence yet. Initial testimony is required to establish this element."
        if lane == 'testimony_gap':
            return f"'{element_text}' has authority support but lacks firsthand testimony to corroborate the rule application."
        if lane == 'document_request':
            missing_str = ', '.join(missing) if missing else 'evidence'
            return f"'{element_text}' is missing {missing_str}. A document request or records request would fill this gap."
        if lane == 'adverse_authority':
            return f"'{element_text}' has adverse authority that must be distinguished. Targeted factual testimony is needed."
        if lane == 'authority_gap':
            return f"'{element_text}' has factual support but no legal authority. A legal research task or case law citation would strengthen the claim."
        if lane == 'graph_quality_gap':
            return f"'{element_text}' has support, but graph connectivity is weak. A targeted follow-up should anchor the facts to clearer entities, relationships, or source context."
        if lane == 'source_quality_gap':
            return f"'{element_text}' has support from low-quality or weakly parsed source material. A cleaner document, excerpt, or source description would strengthen the path."
        if lane == 'duplicate_support':
            return f"'{element_text}' appears to rely on duplicate or non-independent support. A distinct source would improve proof quality."
        if lane == 'support_quality_gap':
            return f"'{element_text}' has support, but the support path is weak. A targeted factual or documentary follow-up would improve proof quality."
        return f"'{element_text}' has incomplete support. Additional information would improve claim strength."

    def _expected_proof_gain_for_element(self, element: Dict[str, Any], lane: str) -> float:
        """Estimate how much proof progress a question in this lane would yield (0–1)."""
        base = self._QUESTION_LANE_WEIGHTS.get(lane, 0.5)
        total_links = int(element.get('total_links', 0) or 0)
        fact_count = int(element.get('fact_count', 0) or 0)
        # Bonus for zero-evidence elements (any answer is net-positive)
        if total_links == 0 and fact_count == 0:
            base = min(base + 0.1, 1.0)
        # Small penalty for elements that already have partial support
        elif total_links > 2 and lane not in ('contradiction_resolution', 'adverse_authority'):
            base = max(base - 0.1, 0.1)
        quality_summary = element.get('support_quality_summary', {}) if isinstance(element.get('support_quality_summary'), dict) else {}
        if lane in {'graph_quality_gap', 'support_quality_gap', 'source_quality_gap', 'duplicate_support'}:
            weakest_score = float(quality_summary.get('weakest_quality_score', quality_summary.get('avg_quality_score', 0.0)) or 0.0)
            if 0.0 < weakest_score < 0.45:
                base = min(base + 0.08, 1.0)
        return round(base, 3)

    def get_question_recommendations(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        required_support_kinds: Optional[List[str]] = None,
        max_recommendations: int = 20,
    ) -> Dict[str, Any]:
        """Return ranked question recommendations for *user_id* based on proof gaps.

        Each recommendation includes:
        - ``question_id`` — stable deterministic identifier
        - ``target_claim_element_id`` — element the question targets
        - ``question_lane`` — category of question (e.g. ``missing_element``, ``testimony_gap``)
        - ``question_type`` — ``testimony`` or ``document_request``
        - ``question_reason`` — human-readable explanation of why the question is recommended
        - ``expected_proof_gain`` — estimated improvement in proof readiness (0–1)
        - ``question_text`` — draft question text the operator can use directly
        - ``retrieval_context`` — best available retrieval results for this element (M4)
        - ``proof_state`` — current element proof state from M5 proof card
        """
        gaps = self.get_claim_support_gaps(
            user_id,
            claim_type=claim_type,
            required_support_kinds=required_support_kinds,
        )
        contradictions = self.get_claim_contradiction_candidates(user_id, claim_type=claim_type)

        # Collect element IDs that have active contradictions
        contradiction_element_ids: List[str] = []
        for claim_contradictions in (contradictions.get('claims') or {}).values():
            for candidate in (claim_contradictions.get('candidates') or []):
                for ref_id in (candidate.get('element_ids') or []):
                    contradiction_element_ids.append(str(ref_id))

        recommendations: List[Dict[str, Any]] = []
        max_int = max_recommendations if isinstance(max_recommendations, int) and max_recommendations > 0 else 20

        for current_claim, claim_gaps in (gaps.get('claims') or {}).items():
            seen_element_lanes: set[tuple[str, str]] = set()
            for element in (claim_gaps.get('unresolved_elements') or []):
                if not isinstance(element, dict):
                    continue
                element_id = str(element.get('element_id') or '')
                element_text = str(element.get('element_text') or '')
                if not element_text:
                    continue

                is_contradicted = element_id in contradiction_element_ids
                lane = 'contradiction_resolution' if is_contradicted else self._question_lane_for_element(element)
                seen_element_lanes.add((element_id, lane))
                question_type = self._question_type_for_lane(lane)
                reason = self._question_reason_for_element(element, lane, contradiction_element_ids)
                gain = self._expected_proof_gain_for_element(element, lane)

                # Build a draft question text appropriate for the lane
                question_text = self._draft_question_text(element_text, lane, element)

                # Deterministic ID from user, claim, element, and lane
                qid_src = f'{user_id}:{current_claim}:{element_id}:{lane}'
                question_id = 'qrec:' + hashlib.sha1(qid_src.encode()).hexdigest()[:12]

                # M4: Enrich with retrieval context when available
                retrieval_context = self.get_retrieval_context_for_element(
                    user_id,
                    current_claim,
                    element_id,
                    max_results=3,
                )
                has_retrieval_context = retrieval_context.get('has_retrieval_context', False)
                top_retrieval_results = retrieval_context.get('top_results', [])
                if has_retrieval_context and gain > 0:
                    # Dampen gain: existing retrieval context means some evidence is already
                    # present, so the incremental value of a new question is lower (15% reduction).
                    _RETRIEVAL_CONTEXT_GAIN_DAMPENING = 0.85
                    gain = round(gain * _RETRIEVAL_CONTEXT_GAIN_DAMPENING, 3)

                # M5: Attach proof state from element proof card
                proof_state_context: Dict[str, Any] = {}
                try:
                    proof_card = self.get_element_proof_card(
                        user_id,
                        current_claim,
                        claim_element_id=element_id or None,
                        claim_element_text=element_text or None,
                        coverage_status=element.get('status') or None,
                    )
                    proof_state_context = {
                        'proof_state': proof_card.get('proof_state', 'missing'),
                        'missing_predicates': proof_card.get('missing_predicates', []),
                        'contradiction_count': proof_card.get('contradiction_count', 0),
                        'next_action': proof_card.get('next_action', 'gather_evidence'),
                        'proof_explanation': proof_card.get('explanation', ''),
                    }
                except Exception:
                    proof_state_context = {
                        'proof_state': 'missing',
                        'missing_predicates': [],
                        'contradiction_count': 0,
                        'next_action': 'gather_evidence',
                        'proof_explanation': '',
                    }

                quality_summary = element.get('support_quality_summary', {}) if isinstance(element.get('support_quality_summary'), dict) else {}
                primary_quality_signal = self._primary_quality_signal_for_summary(quality_summary)
                recommendations.append({
                    'question_id': question_id,
                    'claim_type': current_claim,
                    'target_claim_element_id': element_id,
                    'target_claim_element_text': element_text,
                    'question_lane': lane,
                    'question_type': question_type,
                    'question_reason': reason,
                    'expected_proof_gain': gain,
                    'question_text': question_text,
                    'element_status': element.get('status', ''),
                    'element_total_links': int(element.get('total_links', 0) or 0),
                    'element_missing_support_kinds': list(element.get('missing_support_kinds', []) or []),
                    'support_quality_summary': quality_summary,
                    'quality_signal_counts': (
                        quality_summary.get('quality_signal_counts', {})
                        if isinstance(quality_summary.get('quality_signal_counts'), dict)
                        else {}
                    ),
                    'primary_quality_signal': primary_quality_signal,
                    'quality_follow_up_action': primary_quality_signal.get('follow_up_action', ''),
                    'retrieval_context': {
                        'has_retrieval_context': has_retrieval_context,
                        'result_count': retrieval_context.get('result_count', 0),
                        'top_score': retrieval_context.get('top_score', 0.0),
                        'duplicate_cluster_count': retrieval_context.get('duplicate_cluster_count', 0),
                        'top_results': top_retrieval_results,
                    },
                    'proof_state_context': proof_state_context,
                })

            claim_matrix = self.get_claim_coverage_matrix(
                user_id,
                claim_type=current_claim,
                required_support_kinds=required_support_kinds,
            ).get('claims', {}).get(current_claim, {})
            for element in (claim_matrix.get('elements') or []):
                if not isinstance(element, dict):
                    continue
                element_id = str(element.get('element_id') or '')
                element_text = str(element.get('element_text') or '')
                if not element_text:
                    continue
                lane = self._quality_gap_lane_for_element(element)
                if not lane or lane == 'missing_element' or (element_id, lane) in seen_element_lanes:
                    continue
                quality_summary = element.get('support_quality_summary', {}) if isinstance(element.get('support_quality_summary'), dict) else {}
                if str(quality_summary.get('recommended_quality_action') or '') == 'review_support_quality' and lane != 'graph_quality_gap':
                    continue
                question_type = self._question_type_for_lane(lane)
                reason = self._question_reason_for_element(element, lane, contradiction_element_ids)
                gain = self._expected_proof_gain_for_element(element, lane)
                question_text = self._draft_question_text(element_text, lane, element)
                qid_src = f'{user_id}:{current_claim}:{element_id}:{lane}'
                primary_quality_signal = self._primary_quality_signal_for_summary(quality_summary)
                recommendations.append({
                    'question_id': 'qrec:' + hashlib.sha1(qid_src.encode()).hexdigest()[:12],
                    'claim_type': current_claim,
                    'target_claim_element_id': element_id,
                    'target_claim_element_text': element_text,
                    'question_lane': lane,
                    'question_type': question_type,
                    'question_reason': reason,
                    'expected_proof_gain': gain,
                    'question_text': question_text,
                    'element_status': element.get('status', ''),
                    'element_total_links': int(element.get('total_links', 0) or 0),
                    'element_missing_support_kinds': list(element.get('missing_support_kinds', []) or []),
                    'support_quality_summary': quality_summary,
                    'quality_signal_counts': (
                        quality_summary.get('quality_signal_counts', {})
                        if isinstance(quality_summary.get('quality_signal_counts'), dict)
                        else {}
                    ),
                    'primary_quality_signal': primary_quality_signal,
                    'quality_follow_up_action': primary_quality_signal.get('follow_up_action', ''),
                    'retrieval_context': {
                        'has_retrieval_context': False,
                        'result_count': 0,
                        'top_score': 0.0,
                        'duplicate_cluster_count': 0,
                        'top_results': [],
                    },
                    'proof_state_context': {
                        'proof_state': 'quality_gap',
                        'missing_predicates': [],
                        'contradiction_count': 0,
                        'next_action': str(quality_summary.get('recommended_quality_action') or 'strengthen_support_path'),
                        'proof_explanation': reason,
                    },
                })
                seen_element_lanes.add((element_id, lane))

        # Rank by expected_proof_gain descending, then by lane priority
        recommendations.sort(key=lambda r: (-r['expected_proof_gain'], r['question_lane']))
        recommendations = recommendations[:max_int]

        return self._with_intake_summary_handoff({
            'available': True,
            'user_id': user_id,
            'claim_type': claim_type,
            'total_recommendations': len(recommendations),
            'testimony_recommendations': sum(1 for r in recommendations if r['question_type'] == 'testimony'),
            'document_request_recommendations': sum(
                1 for r in recommendations if r['question_type'] == 'document_request'
            ),
            'contradiction_resolution_count': sum(
                1 for r in recommendations if r['question_lane'] == 'contradiction_resolution'
            ),
            'recommendations': recommendations,
        })

    def _draft_question_text(self, element_text: str, lane: str, element: Dict[str, Any]) -> str:
        """Generate a draft question text for an operator to use directly."""
        if lane == 'contradiction_resolution':
            return (
                f"We have conflicting information about {element_text}. "
                "Could you describe exactly what happened, in your own words, so we can clarify the record?"
            )
        if lane == 'missing_element':
            return (
                f"To support your claim regarding {element_text}, "
                "please describe what happened, when it occurred, and who was involved."
            )
        if lane == 'testimony_gap':
            return (
                f"We have some legal authority supporting your position on {element_text}. "
                "Can you describe a specific incident or situation that directly demonstrates this in your case?"
            )
        if lane == 'document_request':
            missing = list(element.get('missing_support_kinds', []) or [])
            doc_kind = missing[0] if missing else 'documents'
            return (
                f"Do you have any {doc_kind} — such as records, correspondence, or reports — "
                f"that relate to {element_text}? If so, please provide or describe them."
            )
        if lane == 'adverse_authority':
            return (
                f"There is case law that may present a challenge to your position on {element_text}. "
                "Are there facts in your situation that you believe would distinguish your case from that precedent?"
            )
        if lane == 'authority_gap':
            return (
                f"Your factual account addresses {element_text}, "
                "but we do not yet have legal authority supporting this element. "
                "Are you aware of any prior cases, statutes, or regulations that apply to your situation?"
            )
        if lane == 'graph_quality_gap':
            return (
                f"For {element_text}, can you identify the people, documents, dates, or relationships "
                "that connect the current support to this claim element more directly?"
            )
        if lane == 'source_quality_gap':
            return (
                f"Do you have a clearer copy, excerpt, or description of the source that supports {element_text}, "
                "including where in the document the relevant facts appear?"
            )
        if lane == 'duplicate_support':
            return (
                f"Do you have an independent source, witness, or record that supports {element_text} "
                "separately from the materials already provided?"
            )
        if lane == 'support_quality_gap':
            return (
                f"What additional fact, document, or witness detail would make the support for {element_text} "
                "more direct and specific?"
            )
        return (
            f"Can you provide any additional information or documentation related to {element_text} "
            "that would help establish or strengthen this aspect of your claim?"
        )

    # ------------------------------------------------------------------
    # M4: Retrieval Sessions and Evidence Ranking
    # ------------------------------------------------------------------

    def _make_retrieval_session_id(
        self,
        *,
        user_id: str,
        claim_type: str,
        claim_element_id: str,
        query_text: str,
        created_at: str,
    ) -> str:
        src = f'{user_id}|{claim_type}|{claim_element_id}|{query_text}|{created_at}'
        return 'rsession:' + hashlib.sha1(src.encode()).hexdigest()[:16]

    def _make_duplicate_cluster_id(self, text: str) -> str:
        """Return a short cluster key for near-duplicate detection based on normalized text.

        Uses the first 12 sorted unique tokens of the normalized text as the fingerprint.
        12 tokens provides enough signal to distinguish near-duplicates (same incident described
        in slightly different words) while tolerating minor phrasing variations.
        """
        normalized = re.sub(r'\s+', ' ', str(text or '').lower().strip())
        tokens = sorted(set(re.findall(r'[a-z0-9]+', normalized)))
        _MAX_CLUSTER_TOKENS = 12  # sufficient for near-duplicate fingerprinting
        token_key = ' '.join(tokens[:_MAX_CLUSTER_TOKENS])
        return 'dc:' + hashlib.sha1(token_key.encode()).hexdigest()[:12]

    def _score_retrieval_chunk(
        self,
        chunk: Dict[str, Any],
        query_tokens: List[str],
        element_text: str,
    ) -> float:
        """Return a heuristic retrieval score [0–1] for *chunk* against *query_tokens*."""
        return self._build_retrieval_ranking_payload(chunk, query_tokens, element_text)['score']

    def _build_retrieval_ranking_payload(
        self,
        chunk: Dict[str, Any],
        query_tokens: List[str],
        element_text: str,
    ) -> Dict[str, Any]:
        text = ' '.join([
            str(chunk.get('text') or chunk.get('chunk_text') or ''),
            str(chunk.get('label') or chunk.get('source_label') or ''),
            str(chunk.get('title') or ''),
        ]).lower()
        chunk_tokens = set(re.findall(r'[a-z0-9]+', text))
        q_tokens = set(str(t).lower() for t in query_tokens)
        element_tokens = set(re.findall(r'[a-z0-9]+', str(element_text or '').lower()))
        metadata = dict(chunk.get('metadata') or {})

        overlap = len(q_tokens & chunk_tokens)
        element_overlap = len(element_tokens & chunk_tokens)
        denom = max(1, len(q_tokens) + len(element_tokens) // 2)
        query_fit_score = (overlap + element_overlap * 0.5) / denom
        existing = float(chunk.get('score') or chunk.get('retrieval_score') or 0.0)
        base_score = max(existing, query_fit_score)

        source_kind = str(chunk.get('source_kind') or chunk.get('kind') or 'chunk').strip().lower()
        source_kind_weight_map = {
            'authority': 0.10,
            'statute': 0.12,
            'regulation': 0.11,
            'case_law': 0.09,
            'evidence': 0.08,
            'document': 0.07,
            'testimony': 0.06,
            'web_archive': 0.05,
            'web': 0.03,
        }
        authority_class = str(
            metadata.get('authority_class')
            or metadata.get('authority_family')
            or metadata.get('authority_type')
            or ''
        ).strip().lower()
        authority_class_weight = 0.0
        if authority_class in {'statute', 'regulation', 'primary', 'mandatory_authority'}:
            authority_class_weight = 0.08
        elif authority_class in {'case_law', 'binding_case', 'precedent'}:
            authority_class_weight = 0.06
        elif authority_class in {'guidance', 'secondary', 'persuasive_authority'}:
            authority_class_weight = 0.03

        source_quality = metadata.get('quality_score', metadata.get('data_quality_score', metadata.get('source_quality_score', 0.0)))
        try:
            source_quality_weight = max(0.0, min(1.0, float(source_quality or 0.0))) * 0.10
        except (TypeError, ValueError):
            source_quality_weight = 0.0
        quality_tier = str(metadata.get('quality_tier') or '').strip().lower()
        if quality_tier in {'high', 'strong', 'excellent', 'verified'}:
            source_quality_weight = max(source_quality_weight, 0.08)
        elif quality_tier in {'low', 'weak'}:
            source_quality_weight = min(source_quality_weight, 0.025)

        temporal_terms = {
            token for token in q_tokens
            if token.isdigit() or token in {'before', 'after', 'during', 'within', 'deadline', 'notice', 'date'}
        }
        temporal_text = ' '.join([
            text,
            str(metadata.get('effective_date') or ''),
            str(metadata.get('published_date') or ''),
            str(metadata.get('temporal_scope') or ''),
            str(metadata.get('date') or ''),
        ]).lower()
        temporal_overlap = len(temporal_terms & set(re.findall(r'[a-z0-9]+', temporal_text)))
        temporal_relevance_weight = min(0.08, temporal_overlap * 0.025)
        if re.search(r'\b(19|20)\d{2}\b', ' '.join(q_tokens)) and re.search(r'\b(19|20)\d{2}\b', temporal_text):
            temporal_relevance_weight = max(temporal_relevance_weight, 0.04)

        graph_signal_weight = 0.0
        graph_summary = metadata.get('graph_trace_summary', {}) if isinstance(metadata.get('graph_trace_summary'), dict) else {}
        support_quality = metadata.get('support_quality_summary', {}) if isinstance(metadata.get('support_quality_summary'), dict) else {}
        if graph_summary:
            graph_signal_weight += min(0.05, int(graph_summary.get('traced_link_count', 0) or graph_summary.get('graph_count', 0) or 1) * 0.02)
        quality_tier_signal = str(metadata.get('path_quality_tier') or support_quality.get('dominant_quality_tier') or '').strip().lower()
        if quality_tier_signal in {'strong_support', 'strong', 'high'}:
            graph_signal_weight += 0.06
        elif quality_tier_signal in {'moderate_support', 'moderate'}:
            graph_signal_weight += 0.03
        elif quality_tier_signal in {'weak_support', 'structurally_missing'}:
            graph_signal_weight -= 0.025
        graph_signal_weight = max(-0.025, min(0.10, graph_signal_weight))

        content_origin = str(metadata.get('content_origin') or '').strip().lower()
        artifact_family = str(metadata.get('artifact_family') or '').strip().lower()
        archive_signal_weight = 0.0
        if source_kind == 'web_archive' or content_origin == 'historical_archive_capture' or artifact_family == 'archived_web_page':
            archive_signal_weight = 0.06
        elif content_origin == 'live_web_capture':
            archive_signal_weight = 0.025

        factors = {
            'query_fit_score': round(query_fit_score, 6),
            'base_score': round(base_score, 6),
            'source_kind_weight': round(source_kind_weight_map.get(source_kind, 0.0), 6),
            'claim_element_fit_weight': round(min(0.14, element_overlap * 0.03), 6),
            'source_quality_weight': round(source_quality_weight, 6),
            'authority_class_weight': round(authority_class_weight, 6),
            'temporal_relevance_weight': round(temporal_relevance_weight, 6),
            'graph_signal_weight': round(graph_signal_weight, 6),
            'archive_signal_weight': round(archive_signal_weight, 6),
        }
        final_score = min(1.0, base_score + sum(
            value for key, value in factors.items()
            if key not in {'query_fit_score', 'base_score'}
        ))
        explanation_parts = []
        if overlap:
            explanation_parts.append(f'matched {overlap} query term(s)')
        if element_overlap:
            explanation_parts.append(f'matched {element_overlap} claim-element term(s)')
        for key in (
            'source_kind_weight',
            'source_quality_weight',
            'authority_class_weight',
            'temporal_relevance_weight',
            'graph_signal_weight',
            'archive_signal_weight',
        ):
            value = factors.get(key, 0.0)
            if value:
                explanation_parts.append(f'{key.replace("_", " ")} {value:+.2f}')
        return {
            'score': round(final_score, 4),
            'factors': factors,
            'matched_query_terms': sorted(q_tokens & chunk_tokens),
            'matched_element_terms': sorted(element_tokens & chunk_tokens),
            'explanation_parts': explanation_parts,
        }

    def _explain_retrieval_result(
        self,
        chunk: Dict[str, Any],
        query_tokens: List[str],
        score: float,
        element_text: str,
    ) -> str:
        """Return a concise explanation for why this chunk was retrieved."""
        ranking_payload = self._build_retrieval_ranking_payload(chunk, query_tokens, element_text)
        matched = ranking_payload.get('matched_query_terms', [])
        source_kind = str(chunk.get('source_kind') or chunk.get('kind') or 'chunk')
        signal_text = '; '.join(ranking_payload.get('explanation_parts', [])[:4])
        if matched:
            terms = ', '.join(matched[:5])
            suffix = f'; {signal_text}' if signal_text else ''
            return f'Matched {source_kind} on query terms: {terms} (score {score:.2f}{suffix})'
        return f'Retrieved {source_kind} with heuristic score {score:.2f} for {element_text[:60]}'

    def _normalize_chunk_for_indexing(self, chunk: Any, source_kind: str) -> Dict[str, Any]:
        """Normalize a testimony record or document chunk to a common dict shape."""
        if not isinstance(chunk, dict):
            return {}
        normalized: Dict[str, Any] = {}
        normalized['source_kind'] = str(chunk.get('source_kind') or source_kind or 'chunk')
        normalized['source_ref'] = str(
            chunk.get('source_ref')
            or chunk.get('testimony_id')
            or chunk.get('chunk_ref')
            or chunk.get('fact_id')
            or chunk.get('support_ref')
            or ''
        )
        normalized['source_label'] = str(
            chunk.get('source_label')
            or chunk.get('label')
            or chunk.get('title')
            or ''
        )
        normalized['chunk_text'] = str(
            chunk.get('chunk_text')
            or chunk.get('text')
            or chunk.get('raw_narrative')
            or chunk.get('proposition_text')
            or ''
        )
        normalized['score'] = float(chunk.get('score') or chunk.get('retrieval_score') or 0.0)
        normalized['confidence'] = float(chunk.get('confidence') or chunk.get('source_confidence') or 0.0)
        normalized['metadata'] = dict(chunk.get('metadata') or {})
        return normalized

    def _ensure_retrieval_schema(self, conn: Any) -> None:
        """Create retrieval tables if they do not already exist (idempotent)."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claim_retrieval_sessions (
                id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                session_id VARCHAR NOT NULL,
                user_id VARCHAR,
                claim_type VARCHAR NOT NULL,
                claim_element_id VARCHAR,
                claim_element_text TEXT,
                query_text TEXT NOT NULL,
                query_hash VARCHAR NOT NULL,
                retrieval_plane VARCHAR DEFAULT 'unified',
                result_count INTEGER DEFAULT 0,
                status VARCHAR DEFAULT 'pending',
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_claim_retrieval_sessions_session_id
                ON claim_retrieval_sessions(session_id)
            """)
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claim_retrieval_results (
                id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                session_id VARCHAR NOT NULL,
                user_id VARCHAR,
                claim_type VARCHAR NOT NULL,
                claim_element_id VARCHAR,
                rank INTEGER DEFAULT 0,
                source_kind VARCHAR NOT NULL,
                source_ref VARCHAR NOT NULL,
                source_label TEXT,
                chunk_text TEXT,
                retrieval_score FLOAT DEFAULT 0.0,
                confidence FLOAT DEFAULT 0.0,
                explanation TEXT,
                duplicate_cluster_id VARCHAR,
                is_duplicate_representative BOOLEAN DEFAULT FALSE,
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_retrieval_results_session
                ON claim_retrieval_results(session_id)
            """)
        except Exception:
            pass

    def create_retrieval_session(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: str = '',
        claim_element_text: str = '',
        query_text: str = '',
        retrieval_plane: str = 'unified',
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a claim-element-scoped retrieval session and return its stable session ID.

        The session tracks the query, element scope, and (later) ranked results so that
        operators can replay or debug any retrieval pass without re-running the world.
        """
        if not DUCKDB_AVAILABLE:
            return {'created': False, 'error': 'duckdb unavailable', 'session_id': ''}
        try:
            self._prepare_duckdb_path()
            conn = duckdb.connect(self.db_path)
            self._ensure_retrieval_schema(conn)
            created_at = datetime.now(timezone.utc).isoformat()
            query_hash = hashlib.sha256(str(query_text or '').encode()).hexdigest()[:16]
            session_id = self._make_retrieval_session_id(
                user_id=user_id,
                claim_type=claim_type,
                claim_element_id=claim_element_id,
                query_text=query_text,
                created_at=created_at,
            )
            conn.execute(
                """
                INSERT INTO claim_retrieval_sessions
                    (session_id, user_id, claim_type, claim_element_id, claim_element_text,
                     query_text, query_hash, retrieval_plane, result_count, status, metadata,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    session_id, user_id, claim_type, claim_element_id, claim_element_text,
                    query_text, query_hash, retrieval_plane, 0, 'pending',
                    json.dumps(dict(metadata or {})), created_at, created_at,
                ],
            )
            conn.close()
            self.mediator.log('retrieval_session_created', session_id=session_id)
            return {
                'created': True,
                'session_id': session_id,
                'user_id': user_id,
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
                'claim_element_text': claim_element_text,
                'query_text': query_text,
                'query_hash': query_hash,
                'retrieval_plane': retrieval_plane,
                'status': 'pending',
                'created_at': created_at,
            }
        except Exception as exc:
            self.mediator.log('retrieval_session_create_error', error=str(exc))
            return {'created': False, 'error': str(exc), 'session_id': ''}

    def index_chunks_for_retrieval(
        self,
        user_id: str,
        claim_type: str,
        chunks: List[Dict[str, Any]],
        *,
        claim_element_id: str = '',
        source_kind: str = 'chunk',
        session_id: str = '',
        max_chunks: int = 200,
    ) -> Dict[str, Any]:
        """Index testimony and document chunks into the unified retrieval plane.

        Each chunk is normalized, hashed for duplicate detection, and stored so that
        retrieval sessions can query them without re-parsing.  Accepts mixed lists
        containing testimony records, document chunks, or fact records.
        """
        if not DUCKDB_AVAILABLE:
            return {'indexed': False, 'error': 'duckdb unavailable', 'indexed_count': 0}
        try:
            self._prepare_duckdb_path()
            conn = duckdb.connect(self.db_path)
            self._ensure_retrieval_schema(conn)
            # Ensure a session row exists when session_id is provided
            if session_id:
                existing = conn.execute(
                    'SELECT session_id FROM claim_retrieval_sessions WHERE session_id = ?',
                    [session_id],
                ).fetchone()
                if not existing:
                    session_id = ''  # ignore unknown session reference
            now = datetime.now(timezone.utc).isoformat()
            safe_chunks = list(chunks or [])[:max_chunks]
            indexed_count = 0
            cluster_map: Dict[str, str] = {}  # cluster_id -> first source_ref (representative)
            for chunk in safe_chunks:
                normalized = self._normalize_chunk_for_indexing(chunk, source_kind)
                if not normalized.get('source_ref') and not normalized.get('chunk_text'):
                    continue
                chunk_text = normalized['chunk_text']
                cluster_id = self._make_duplicate_cluster_id(chunk_text)
                is_representative = cluster_id not in cluster_map
                if is_representative:
                    cluster_map[cluster_id] = normalized['source_ref']
                conn.execute(
                    """
                    INSERT INTO claim_retrieval_results
                        (session_id, user_id, claim_type, claim_element_id, rank,
                         source_kind, source_ref, source_label, chunk_text,
                         retrieval_score, confidence, explanation,
                         duplicate_cluster_id, is_duplicate_representative,
                         metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        session_id or '', user_id, claim_type, claim_element_id,
                        indexed_count,
                        normalized['source_kind'],
                        normalized['source_ref'],
                        normalized['source_label'],
                        chunk_text,
                        normalized['score'],
                        normalized['confidence'],
                        '',  # explanation set during retrieval scoring
                        cluster_id,
                        is_representative,
                        json.dumps(normalized['metadata']),
                        now,
                    ],
                )
                indexed_count += 1
            if session_id and indexed_count > 0:
                conn.execute(
                    "UPDATE claim_retrieval_sessions SET result_count = ?, updated_at = ? WHERE session_id = ?",
                    [indexed_count, now, session_id],
                )
            conn.close()
            self.mediator.log('chunks_indexed_for_retrieval', indexed_count=indexed_count)
            return {
                'indexed': True,
                'indexed_count': indexed_count,
                'session_id': session_id,
                'duplicate_cluster_count': len(cluster_map),
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
            }
        except Exception as exc:
            self.mediator.log('index_chunks_error', error=str(exc))
            return {'indexed': False, 'error': str(exc), 'indexed_count': 0}

    def run_retrieval_session(
        self,
        user_id: str,
        claim_type: str,
        *,
        claim_element_id: str = '',
        claim_element_text: str = '',
        query_text: str = '',
        chunks: Optional[List[Dict[str, Any]]] = None,
        max_results: int = 20,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a retrieval session, score/rank provided chunks, and persist results.

        This is the main entry point for M4 retrieval.  It:
        1. Creates a stable session record.
        2. Scores each chunk against *query_text* and *claim_element_text*.
        3. Annotates duplicate-cluster hints.
        4. Generates a concise explanation for each ranked result.
        5. Persists all results for later replay or drilldown.

        Returns the session metadata and the ranked result list.
        """
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'error': 'duckdb unavailable',
                'session_id': '',
                'results': [],
                'result_count': 0,
            }
        session = self.create_retrieval_session(
            user_id,
            claim_type,
            claim_element_id=claim_element_id,
            claim_element_text=claim_element_text,
            query_text=query_text,
            retrieval_plane='unified',
            metadata=metadata,
        )
        if not session.get('created'):
            return {
                'available': False,
                'error': session.get('error', 'session creation failed'),
                'session_id': '',
                'results': [],
                'result_count': 0,
            }
        session_id = session['session_id']
        query_tokens = re.findall(r'[a-z0-9]+', str(query_text or '').lower())
        safe_chunks = list(chunks or [])[:max_results * 2]
        # Score and annotate
        scored: List[Dict[str, Any]] = []
        cluster_map: Dict[str, str] = {}
        for chunk in safe_chunks:
            normalized = self._normalize_chunk_for_indexing(chunk, 'chunk')
            if not normalized.get('source_ref') and not normalized.get('chunk_text'):
                continue
            ranking_payload = self._build_retrieval_ranking_payload(normalized, query_tokens, claim_element_text)
            score = ranking_payload['score']
            explanation = self._explain_retrieval_result(normalized, query_tokens, score, claim_element_text)
            cluster_id = self._make_duplicate_cluster_id(normalized['chunk_text'])
            is_representative = cluster_id not in cluster_map
            if is_representative:
                cluster_map[cluster_id] = normalized['source_ref']
            result_metadata = dict(normalized['metadata'])
            result_metadata.update({
                'retrieval_ranking_factors': ranking_payload['factors'],
                'retrieval_ranking_explanation': ranking_payload['explanation_parts'],
                'matched_query_terms': ranking_payload['matched_query_terms'],
                'matched_claim_element_terms': ranking_payload['matched_element_terms'],
            })
            scored.append({
                'source_kind': normalized['source_kind'],
                'source_ref': normalized['source_ref'],
                'source_label': normalized['source_label'],
                'chunk_text': normalized['chunk_text'],
                'retrieval_score': score,
                'confidence': normalized['confidence'],
                'explanation': explanation,
                'duplicate_cluster_id': cluster_id,
                'is_duplicate_representative': is_representative,
                'metadata': result_metadata,
            })
        # Rank by retrieval_score descending, representatives before duplicates
        scored.sort(key=lambda r: (-r['retrieval_score'], not r['is_duplicate_representative']))
        top_results = scored[:max_results]
        # Persist ranked results
        try:
            self._prepare_duckdb_path()
            conn = duckdb.connect(self.db_path)
            self._ensure_retrieval_schema(conn)
            now = datetime.now(timezone.utc).isoformat()
            for rank, result in enumerate(top_results):
                conn.execute(
                    """
                    INSERT INTO claim_retrieval_results
                        (session_id, user_id, claim_type, claim_element_id, rank,
                         source_kind, source_ref, source_label, chunk_text,
                         retrieval_score, confidence, explanation,
                         duplicate_cluster_id, is_duplicate_representative,
                         metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        session_id, user_id, claim_type, claim_element_id, rank,
                        result['source_kind'], result['source_ref'], result['source_label'],
                        result['chunk_text'], result['retrieval_score'], result['confidence'],
                        result['explanation'], result['duplicate_cluster_id'],
                        result['is_duplicate_representative'],
                        json.dumps(result['metadata']), now,
                    ],
                )
            conn.execute(
                "UPDATE claim_retrieval_sessions SET result_count = ?, status = ?, updated_at = ? WHERE session_id = ?",
                [len(top_results), 'complete', now, session_id],
            )
            conn.close()
        except Exception as exc:
            self.mediator.log('run_retrieval_session_persist_error', error=str(exc))

        duplicate_count = sum(1 for r in top_results if not r['is_duplicate_representative'])
        cluster_ids = list({r['duplicate_cluster_id'] for r in top_results})
        return {
            'available': True,
            'session_id': session_id,
            'user_id': user_id,
            'claim_type': claim_type,
            'claim_element_id': claim_element_id,
            'claim_element_text': claim_element_text,
            'query_text': query_text,
            'status': 'complete',
            'result_count': len(top_results),
            'duplicate_count': duplicate_count,
            'duplicate_cluster_count': len(cluster_ids),
            'results': top_results,
        }

    def get_retrieval_session(
        self,
        user_id: str,
        session_id: str,
        *,
        claim_type: Optional[str] = None,
        max_results: int = 50,
    ) -> Dict[str, Any]:
        """Return a persisted retrieval session and its ranked results for replay or drilldown."""
        if not DUCKDB_AVAILABLE:
            return {'available': False, 'error': 'duckdb unavailable', 'session_id': session_id, 'results': []}
        try:
            self._prepare_duckdb_path()
            conn = duckdb.connect(self.db_path)
            self._ensure_retrieval_schema(conn)
            rows = conn.execute(
                "SELECT * FROM claim_retrieval_sessions WHERE session_id = ? AND user_id = ?",
                [session_id, user_id],
            ).fetchall()
            cols = [d[0] for d in conn.description] if conn.description else []
            if not rows:
                conn.close()
                return {'available': True, 'session_id': session_id, 'found': False, 'results': []}
            session_row = dict(zip(cols, rows[0]))
            # Fetch results
            result_rows = conn.execute(
                "SELECT * FROM claim_retrieval_results WHERE session_id = ? ORDER BY rank ASC LIMIT ?",
                [session_id, max_results],
            ).fetchall()
            result_cols = [d[0] for d in conn.description] if conn.description else []
            conn.close()
            results = []
            for rrow in result_rows:
                rdict = dict(zip(result_cols, rrow))
                raw_meta = rdict.get('metadata')
                if isinstance(raw_meta, str):
                    try:
                        rdict['metadata'] = json.loads(raw_meta)
                    except Exception:
                        rdict['metadata'] = {}
                results.append(rdict)
            duplicate_count = sum(1 for r in results if not r.get('is_duplicate_representative', True))
            cluster_ids = list({str(r.get('duplicate_cluster_id') or '') for r in results if r.get('duplicate_cluster_id')})
            meta = session_row.get('metadata')
            if isinstance(meta, str):
                try:
                    session_row['metadata'] = json.loads(meta)
                except Exception:
                    session_row['metadata'] = {}
            return {
                'available': True,
                'found': True,
                'session_id': session_id,
                'user_id': user_id,
                'claim_type': str(session_row.get('claim_type') or ''),
                'claim_element_id': str(session_row.get('claim_element_id') or ''),
                'claim_element_text': str(session_row.get('claim_element_text') or ''),
                'query_text': str(session_row.get('query_text') or ''),
                'retrieval_plane': str(session_row.get('retrieval_plane') or 'unified'),
                'status': str(session_row.get('status') or ''),
                'result_count': int(session_row.get('result_count') or len(results)),
                'duplicate_count': duplicate_count,
                'duplicate_cluster_count': len(cluster_ids),
                'duplicate_cluster_ids': cluster_ids,
                'created_at': str(session_row.get('created_at') or ''),
                'updated_at': str(session_row.get('updated_at') or ''),
                'results': results,
                'session_metadata': dict(session_row.get('metadata') or {}),
            }
        except Exception as exc:
            self.mediator.log('get_retrieval_session_error', error=str(exc))
            return {'available': False, 'error': str(exc), 'session_id': session_id, 'results': []}

    def list_retrieval_sessions(
        self,
        user_id: str,
        *,
        claim_type: Optional[str] = None,
        claim_element_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """List retrieval sessions for *user_id*, optionally scoped to a claim type and element."""
        if not DUCKDB_AVAILABLE:
            return {'available': False, 'sessions': [], 'session_count': 0}
        try:
            self._prepare_duckdb_path()
            conn = duckdb.connect(self.db_path)
            self._ensure_retrieval_schema(conn)
            predicates = ['user_id = ?']
            params: List[Any] = [user_id]
            if claim_type:
                predicates.append('claim_type = ?')
                params.append(claim_type)
            if claim_element_id:
                predicates.append('claim_element_id = ?')
                params.append(claim_element_id)
            where = ' AND '.join(predicates)
            rows = conn.execute(
                f"SELECT session_id, claim_type, claim_element_id, claim_element_text, "
                f"query_text, retrieval_plane, result_count, status, created_at, updated_at "
                f"FROM claim_retrieval_sessions WHERE {where} ORDER BY created_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            cols = ['session_id', 'claim_type', 'claim_element_id', 'claim_element_text',
                    'query_text', 'retrieval_plane', 'result_count', 'status', 'created_at', 'updated_at']
            conn.close()
            sessions = [dict(zip(cols, row)) for row in rows]
            return {
                'available': True,
                'user_id': user_id,
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
                'session_count': len(sessions),
                'sessions': sessions,
            }
        except Exception as exc:
            self.mediator.log('list_retrieval_sessions_error', error=str(exc))
            return {'available': False, 'error': str(exc), 'sessions': [], 'session_count': 0}

    def get_retrieval_context_for_element(
        self,
        user_id: str,
        claim_type: str,
        claim_element_id: str,
        *,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """Return the best available retrieval results for a claim element across all sessions.

        Used by question recommendations and follow-up planning to cite retrieval context
        rather than generic gap labels alone.
        """
        if not DUCKDB_AVAILABLE:
            return {
                'available': False,
                'claim_element_id': claim_element_id,
                'top_results': [],
                'has_retrieval_context': False,
            }
        try:
            self._prepare_duckdb_path()
            conn = duckdb.connect(self.db_path)
            self._ensure_retrieval_schema(conn)
            rows = conn.execute(
                """
                SELECT source_kind, source_ref, source_label, chunk_text,
                       retrieval_score, confidence, explanation,
                       duplicate_cluster_id, is_duplicate_representative, metadata
                FROM claim_retrieval_results
                WHERE user_id = ? AND claim_type = ? AND claim_element_id = ?
                ORDER BY retrieval_score DESC
                LIMIT ?
                """,
                [user_id, claim_type, claim_element_id, max_results],
            ).fetchall()
            cols = [
                'source_kind', 'source_ref', 'source_label', 'chunk_text',
                'retrieval_score', 'confidence', 'explanation',
                'duplicate_cluster_id', 'is_duplicate_representative', 'metadata',
            ]
            conn.close()
            results = []
            for row in rows:
                result = dict(zip(cols, row))
                raw_metadata = result.get('metadata')
                if isinstance(raw_metadata, str):
                    try:
                        result['metadata'] = json.loads(raw_metadata)
                    except Exception:
                        result['metadata'] = {}
                elif not isinstance(raw_metadata, dict):
                    result['metadata'] = {}
                result['retrieval_ranking_factors'] = result['metadata'].get('retrieval_ranking_factors', {})
                result['retrieval_ranking_explanation'] = result['metadata'].get('retrieval_ranking_explanation', [])
                results.append(result)
            has_context = bool(results)
            top_score = max((r['retrieval_score'] for r in results), default=0.0)
            duplicate_cluster_ids = list({r['duplicate_cluster_id'] for r in results if r.get('duplicate_cluster_id')})
            return {
                'available': True,
                'claim_element_id': claim_element_id,
                'claim_type': claim_type,
                'has_retrieval_context': has_context,
                'result_count': len(results),
                'top_score': top_score,
                'duplicate_cluster_count': len(duplicate_cluster_ids),
                'duplicate_cluster_hints': duplicate_cluster_ids,
                'top_results': results,
            }
        except Exception as exc:
            self.mediator.log('get_retrieval_context_error', error=str(exc))
            return {
                'available': False,
                'error': str(exc),
                'claim_element_id': claim_element_id,
                'top_results': [],
                'has_retrieval_context': False,
            }

    def forward_conditional_norm_evidence(
        self,
        requirement: Dict[str, Any],
        definition_envelope: Optional[Dict[str, Any]] = None,
        scope_envelope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Forward definition and scope evidence without changing admitted text or proof.

        The requirement mapping is left as the caller supplied it. Conflicting or
        absent owner evidence stays an unresolved dependency on the returned handoff.
        """
        from integrations.ipfs_datasets.definition_evidence import forward_conditional_norm_evidence

        admitted = requirement.get('admitted_legal_text')
        proof = requirement.get('proof')
        proof_satisfied = requirement.get('proof_satisfied')
        handoff = forward_conditional_norm_evidence(requirement, definition_envelope, scope_envelope)
        if requirement.get('admitted_legal_text') != admitted or requirement.get('proof') != proof:
            handoff['admitted_legal_text_changed'] = True
            handoff['proof_changed'] = requirement.get('proof') != proof
        handoff['prior_proof_satisfied'] = proof_satisfied
        handoff['proof_satisfied'] = False
        return handoff

    def forward_independent_norm_decisions(
        self,
        requirement: Dict[str, Any],
        definition_envelope: Optional[Dict[str, Any]] = None,
        scope_envelope: Optional[Dict[str, Any]] = None,
        review_envelope: Optional[Dict[str, Any]] = None,
        bound_variable_envelope: Optional[Dict[str, Any]] = None,
        declared_prover_result: Any = None,
    ) -> Dict[str, Any]:
        """Forward review and bound-variable decisions without signing or proving them.

        Source, edition, meaning, and context permissions stay on separate records.
        An unprovided review is left absent. Generated Lean stays unbuilt unless the
        owner report and a hash-matching declared prover result both say otherwise.
        """
        from integrations.ipfs_datasets.definition_evidence import forward_independent_norm_decisions

        admitted = requirement.get('admitted_legal_text')
        proof = requirement.get('proof')
        proof_satisfied = requirement.get('proof_satisfied')
        handoff = forward_independent_norm_decisions(
            requirement,
            definition_envelope,
            scope_envelope,
            review_envelope,
            bound_variable_envelope,
            declared_prover_result,
        )
        if requirement.get('admitted_legal_text') != admitted or requirement.get('proof') != proof:
            handoff['admitted_legal_text_changed'] = True
            handoff['proof_changed'] = requirement.get('proof') != proof
        handoff['prior_proof_satisfied'] = proof_satisfied
        handoff['proof_satisfied'] = False
        handoff['reviews_synthesized'] = False
        return handoff

    def connect_definition_handoff_proof(
        self,
        requirement: Dict[str, Any],
        handoff: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Route the current definition handoff without promoting review or Lean to proof."""

        bound = connect_definition_handoff_proof(requirement, handoff)
        bound['factual_assertion_is_legal_sufficiency'] = False
        if bound.get('proof_field_supported') is not True:
            bound['proof'] = requirement.get('proof')
            bound['proof_satisfied'] = False
            bound['proof_changed'] = False
        return bound


def apply_qualified_claim_support(
    hook: "ClaimSupportHook",
    payload: Dict[str, Any],
    projections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Write support rows only from analysis projections.

    A caller ``verified_support`` flag is not consulted. Retired and unverified
    projections stay unverified. The stored rows are read back from the hook.
    """
    user_id = str(payload.get("user_id") or "actor")
    complaint_id = str(payload.get("complaint_id") or "case")
    claim_type = str(payload.get("claim_type") or "claim")
    written = []
    for projection in projections:
        verified = projection.get("verified_support") is True and projection.get("governing_authority") is True
        retired = projection.get("projection_status") == "retired"
        if not verified and not retired and projection.get("projection_status") != "unverified":
            continue
        lineage = list(projection.get("lineage") or [])
        primary = lineage[0] if lineage else {}
        kind = "admitted_lineage" if verified else ("retired_projection" if retired else "unverified_requirement")
        metadata = {
            "passage_id": projection.get("passage_id"),
            "requirement_id": projection.get("requirement_id"),
            "source_version": projection.get("source_version"),
            "definition_version": projection.get("definition_version"),
            "source_hash": projection.get("source_hash"),
            "lineage_id": primary.get("lineage_id") or "",
            "fact_id": primary.get("fact_id") or "",
            "evidence_ref": primary.get("evidence_ref") or "",
            "verified_support": verified,
            "governing_authority": verified,
            "projection_status": projection.get("projection_status"),
            "retirement_reason": projection.get("retirement_reason") or "",
            "caller_flag_ignored": True,
        }
        support_ref = str(primary.get("evidence_ref") or projection.get("passage_id") or "projection")
        result = hook.upsert_support_link(
            user_id=user_id,
            complaint_id=complaint_id,
            claim_type=claim_type,
            claim_element_id=str(projection.get("requirement_id") or ""),
            claim_element_text=str(projection.get("requirement_id") or ""),
            support_kind=kind,
            support_ref=support_ref,
            support_label=str(projection.get("citation") or projection.get("passage_id") or ""),
            source_table="admitted_passages",
            support_strength=1.0 if verified else 0.0,
            metadata=metadata,
        )
        written.append({"record_id": result.get("record_id"), "support_kind": kind, "created": result.get("created")})
    stored = hook.get_support_links(user_id, claim_type)
    verified_rows = [
        row for row in stored
        if (row.get("metadata") or {}).get("verified_support") is True
        and row.get("support_kind") == "admitted_lineage"
    ]
    retired_rows = [
        row for row in stored
        if row.get("support_kind") == "retired_projection"
        and (row.get("metadata") or {}).get("verified_support") is not True
    ]
    return {
        "owner": "ClaimSupportHook",
        "written": written,
        "stored_count": len(stored),
        "verified_support_count": len(verified_rows),
        "retired_count": len(retired_rows),
        "verified_links": [
            {
                "record_id": row.get("id"),
                "requirement_id": (row.get("metadata") or {}).get("requirement_id"),
                "passage_id": (row.get("metadata") or {}).get("passage_id"),
                "source_version": (row.get("metadata") or {}).get("source_version"),
                "definition_version": (row.get("metadata") or {}).get("definition_version"),
                "source_hash": (row.get("metadata") or {}).get("source_hash"),
                "lineage_id": (row.get("metadata") or {}).get("lineage_id"),
                "fact_id": (row.get("metadata") or {}).get("fact_id"),
                "evidence_ref": (row.get("metadata") or {}).get("evidence_ref"),
                "support_kind": row.get("support_kind"),
                "verified_support": True,
                "governing_authority": (row.get("metadata") or {}).get("governing_authority") is True,
            }
            for row in verified_rows
        ],
        "retired_links": [
            {
                "record_id": row.get("id"),
                "requirement_id": (row.get("metadata") or {}).get("requirement_id"),
                "retirement_reason": (row.get("metadata") or {}).get("retirement_reason"),
                "verified_support": False,
                "governing_authority": False,
                "projection_status": "retired",
            }
            for row in retired_rows
        ],
    }
