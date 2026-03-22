"""Persistent claim-support coverage hooks for mediator."""

from __future__ import annotations

import json
import re
import hashlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from integrations.ipfs_datasets.graphrag import build_ontology, validate_ontology
from integrations.ipfs_datasets.logic import check_contradictions, prove_claim_elements, run_hybrid_reasoning
from complaint_analysis.temporal_rule_profiles import evaluate_temporal_rule_profile
from claim_support_review import _merge_intake_summary_handoff_metadata

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


class ClaimSupportHook:
    """Track which evidence and authorities support each claim type."""

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

    def __init__(self, mediator, db_path: Optional[str] = None):
        self.mediator = mediator
        self.db_path = db_path or self._get_default_db_path()
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
        resolved_artifact_family = artifact_family or self._CONTENT_ORIGIN_ARTIFACT_FAMILY.get(content_origin, '')
        resolved_corpus_family = corpus_family or self._ARTIFACT_FAMILY_CORPUS_FAMILY.get(resolved_artifact_family, '')
        return {
            'artifact_family': resolved_artifact_family,
            'corpus_family': resolved_corpus_family,
        }

    def _prepare_duckdb_path(self):
        try:
            path = Path(self.db_path)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.is_file() and path.stat().st_size == 0:
                path.unlink()
        except Exception:
            pass

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
        if isinstance(graph_payload, dict):
            return {
                'status': graph_payload.get('status', default_status),
                'entity_count': len(graph_payload.get('entities', []) or []),
                'relationship_count': len(graph_payload.get('relationships', []) or []),
            }
        return {
            'status': default_status,
            'entity_count': default_entity_count,
            'relationship_count': default_relationship_count,
        }

    def _build_graph_trace(
        self,
        *,
        source_table: Optional[str],
        support_ref: Optional[str],
        record_id: Optional[int],
        graph_summary: Dict[str, Any],
        graph_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_metadata = graph_metadata if isinstance(graph_metadata, dict) else {}
        snapshot = normalized_metadata.get('graph_snapshot', {})
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        adapter_metadata = {
            key: value
            for key, value in normalized_metadata.items()
            if key != 'graph_snapshot'
        }
        lineage = snapshot.get('metadata', {}) if isinstance(snapshot.get('metadata'), dict) else {}
        return {
            'source_table': source_table or '',
            'support_ref': support_ref or '',
            'record_id': record_id,
            'summary': graph_summary,
            'snapshot': snapshot,
            'metadata': adapter_metadata,
            'lineage': lineage.get('lineage', {}) if isinstance(lineage.get('lineage'), dict) else {},
        }

    def _summarize_graph_traces(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        traced_link_count = 0
        snapshot_created_count = 0
        snapshot_reused_count = 0
        source_table_counts: Dict[str, int] = {}
        graph_status_counts: Dict[str, int] = {}
        seen_graph_ids = set()

        for item in items or []:
            if not isinstance(item, dict):
                continue
            graph_trace = item.get('graph_trace', {})
            if not isinstance(graph_trace, dict) or not graph_trace:
                continue
            traced_link_count += 1

            source_table = str(graph_trace.get('source_table') or 'unknown')
            source_table_counts[source_table] = source_table_counts.get(source_table, 0) + 1

            summary = graph_trace.get('summary', {})
            if isinstance(summary, dict):
                graph_status = str(summary.get('status') or 'unknown')
                graph_status_counts[graph_status] = graph_status_counts.get(graph_status, 0) + 1

            snapshot = graph_trace.get('snapshot', {})
            if isinstance(snapshot, dict):
                if bool(snapshot.get('created')):
                    snapshot_created_count += 1
                if bool(snapshot.get('reused')):
                    snapshot_reused_count += 1
                graph_id = str(snapshot.get('graph_id') or '')
                if graph_id:
                    seen_graph_ids.add(graph_id)

        return {
            'traced_link_count': traced_link_count,
            'snapshot_created_count': snapshot_created_count,
            'snapshot_reused_count': snapshot_reused_count,
            'source_table_counts': source_table_counts,
            'graph_status_counts': graph_status_counts,
            'graph_id_count': len(seen_graph_ids),
        }

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

        rule_type_counts: Dict[str, int] = {}
        authority_links_with_rule_candidates = 0
        total_rule_candidate_count = 0
        matched_claim_element_rule_count = 0
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
                    candidate_element_id = str(candidate.get('claim_element_id') or '')
                    candidate_element_text = str(candidate.get('claim_element_text') or '')
                    if (
                        candidate_element_id and candidate_element_id == link_element_id
                    ) or (
                        candidate_element_text and candidate_element_text == link_element_text
                    ):
                        matched_claim_element_rule_count += 1
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
            max_extraction_confidence = max(
                max_extraction_confidence,
                float(summary.get('max_confidence', 0.0) or 0.0),
            )

        return {
            'authority_link_count': len(authority_links),
            'authority_links_with_rule_candidates': authority_links_with_rule_candidates,
            'total_rule_candidate_count': total_rule_candidate_count,
            'matched_claim_element_rule_count': matched_claim_element_rule_count,
            'rule_type_counts': rule_type_counts,
            'max_extraction_confidence': max_extraction_confidence,
        }

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
        fact = fact if isinstance(fact, dict) else {}
        graph_trace = link.get('graph_trace', {}) if isinstance(link.get('graph_trace'), dict) else {}
        graph_summary = link.get('graph_summary', {}) if isinstance(link.get('graph_summary'), dict) else {}
        record_summary = link.get('record_summary', {}) if isinstance(link.get('record_summary'), dict) else {}
        record_parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
        fact_metadata = fact.get('metadata', {}) if isinstance(fact.get('metadata'), dict) else {}
        parse_lineage = fact_metadata.get('parse_lineage', {}) if isinstance(fact_metadata.get('parse_lineage'), dict) else {}
        snapshot = graph_trace.get('snapshot', {}) if isinstance(graph_trace.get('snapshot'), dict) else {}
        source_ref = link.get('support_ref') or parse_lineage.get('source_ref') or ''
        source_table = str(link.get('source_table') or '')
        source_family = str(fact.get('source_family') or parse_lineage.get('record_scope') or '')
        if not source_family:
            source_family = 'legal_authority' if source_table == 'legal_authorities' else source_table or str(link.get('support_kind') or '')
        source_record_id = fact.get('source_record_id')
        if source_record_id is None:
            if source_family == 'legal_authority':
                source_record_id = link.get('authority_record_id')
            elif source_family == 'claim_testimony':
                source_record_id = link.get('testimony_record_id')
            else:
                source_record_id = link.get('evidence_record_id')
        artifact_family = str(fact.get('artifact_family') or parse_lineage.get('artifact_family') or record_parse_summary.get('artifact_family') or '')
        corpus_family = str(fact.get('corpus_family') or parse_lineage.get('corpus_family') or record_parse_summary.get('corpus_family') or '')
        content_origin = str(fact.get('content_origin') or parse_lineage.get('content_origin') or record_parse_summary.get('content_origin') or '')
        parse_quality = parse_lineage.get('parse_quality', {}) if isinstance(parse_lineage.get('parse_quality'), dict) else {}
        source_span = parse_lineage.get('source_span', {}) if isinstance(parse_lineage.get('source_span'), dict) else {}

        return {
            'claim_type': link.get('claim_type'),
            'claim_element_id': link.get('claim_element_id'),
            'claim_element_text': link.get('claim_element_text'),
            'support_kind': link.get('support_kind'),
            'support_ref': link.get('support_ref'),
            'support_label': link.get('support_label'),
            'source_table': link.get('source_table'),
            'source_family': source_family,
            'source_record_id': source_record_id,
            'source_ref': str(fact.get('source_ref') or parse_lineage.get('source_ref') or source_ref),
            'record_scope': str(fact.get('record_scope') or parse_lineage.get('record_scope') or source_family),
            'artifact_family': artifact_family,
            'corpus_family': corpus_family,
            'content_origin': content_origin,
            'parse_source': str(fact.get('parse_source') or parse_lineage.get('source') or record_parse_summary.get('source') or ''),
            'input_format': str(fact.get('input_format') or parse_lineage.get('input_format') or record_parse_summary.get('input_format') or ''),
            'quality_tier': str(fact.get('quality_tier') or parse_lineage.get('quality_tier') or record_parse_summary.get('quality_tier') or ''),
            'quality_score': float(fact.get('quality_score') or parse_lineage.get('quality_score') or record_parse_summary.get('quality_score') or parse_quality.get('quality_score') or 0.0),
            'page_count': int(fact.get('page_count') or parse_lineage.get('page_count') or record_parse_summary.get('page_count') or source_span.get('page_count') or 0),
            'support_strength': link.get('support_strength', 0.0),
            'record_id': graph_trace.get('record_id') or link.get('evidence_record_id') or link.get('authority_record_id') or link.get('testimony_record_id'),
            'fact_id': fact.get('fact_id', ''),
            'fact_text': fact.get('text', ''),
            'confidence': fact.get('confidence', 0.0),
            'trace_kind': 'fact' if fact.get('fact_id') else 'link',
            'parse_lineage': parse_lineage,
            'source_lineage_ref': source_ref,
            'record_summary': record_summary,
            'graph_summary': graph_summary,
            'graph_trace': graph_trace,
            'graph_id': snapshot.get('graph_id', ''),
            'evidence_record_id': link.get('evidence_record_id'),
            'authority_record_id': link.get('authority_record_id'),
            'testimony_record_id': link.get('testimony_record_id'),
        }

    def _extract_record_parse_summary(self, record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = record if isinstance(record, dict) else {}
        parse_metadata = payload.get('parse_metadata', {}) if isinstance(payload.get('parse_metadata'), dict) else {}
        transform_lineage = parse_metadata.get('transform_lineage', {}) if isinstance(parse_metadata.get('transform_lineage'), dict) else {}
        provenance_payload = payload.get('provenance', {}) if isinstance(payload.get('provenance'), dict) else {}
        if not provenance_payload and isinstance(payload.get('metadata'), dict):
            metadata_provenance = payload['metadata'].get('provenance')
            if isinstance(metadata_provenance, dict):
                provenance_payload = metadata_provenance
        provenance_metadata = provenance_payload.get('metadata', {}) if isinstance(provenance_payload.get('metadata'), dict) else {}
        source_span = parse_metadata.get('source_span', {}) if isinstance(parse_metadata.get('source_span'), dict) else {}
        parse_quality = parse_metadata.get('parse_quality', {}) if isinstance(parse_metadata.get('parse_quality'), dict) else {}

        input_format = str(parse_metadata.get('input_format') or transform_lineage.get('input_format') or provenance_metadata.get('input_format') or '')
        extraction_method = str(parse_metadata.get('extraction_method') or transform_lineage.get('normalization') or '')
        quality_tier = str(parse_metadata.get('quality_tier') or parse_quality.get('quality_tier') or '')
        quality_score = float(parse_metadata.get('quality_score') or parse_quality.get('quality_score') or 0.0)
        page_count = int(parse_metadata.get('page_count', source_span.get('page_count', 0)) or 0)
        content_origin = str(parse_metadata.get('content_origin') or transform_lineage.get('content_origin') or provenance_metadata.get('content_origin') or '')
        artifact_family = str(parse_metadata.get('artifact_family') or transform_lineage.get('artifact_family') or provenance_metadata.get('artifact_family') or '')
        corpus_family = str(parse_metadata.get('corpus_family') or transform_lineage.get('corpus_family') or provenance_metadata.get('corpus_family') or '')

        artifact_identity = self._resolve_artifact_identity(
            content_origin=content_origin,
            artifact_family=artifact_family,
            corpus_family=corpus_family,
        )
        artifact_family = artifact_identity['artifact_family']
        corpus_family = artifact_identity['corpus_family']

        return {
            'parse_status': payload.get('parse_status'),
            'chunk_count': int(payload.get('chunk_count', 0) or 0),
            'corpus_family': corpus_family,
            'artifact_family': artifact_family,
            'input_format': input_format,
            'extraction_method': extraction_method,
            'quality_tier': quality_tier,
            'quality_score': quality_score,
            'page_count': page_count,
            'source': str(parse_metadata.get('source') or transform_lineage.get('source') or ''),
            'content_origin': content_origin,
            'historical_capture': bool(parse_metadata.get('historical_capture', transform_lineage.get('historical_capture', provenance_metadata.get('historical_capture', False)))),
            'capture_source': str(parse_metadata.get('capture_source') or transform_lineage.get('capture_source') or provenance_metadata.get('capture_source') or ''),
            'archive_url': str(parse_metadata.get('archive_url') or transform_lineage.get('archive_url') or provenance_metadata.get('archive_url') or ''),
            'original_url': str(parse_metadata.get('original_url') or transform_lineage.get('original_url') or provenance_metadata.get('original_url') or ''),
            'version_of': str(parse_metadata.get('version_of') or transform_lineage.get('version_of') or provenance_metadata.get('version_of') or ''),
            'captured_at': str(parse_metadata.get('captured_at') or transform_lineage.get('captured_at') or provenance_metadata.get('captured_at') or ''),
            'observed_at': str(parse_metadata.get('observed_at') or transform_lineage.get('observed_at') or provenance_metadata.get('observed_at') or ''),
            'content_source_field': str(parse_metadata.get('content_source_field') or transform_lineage.get('content_source_field') or provenance_metadata.get('content_source_field') or ''),
            'fallback_mode': str(parse_metadata.get('fallback_mode') or transform_lineage.get('fallback_mode') or provenance_metadata.get('fallback_mode') or ''),
            'parsed_text_preview': str(payload.get('parsed_text_preview') or ''),
            'source_span': dict(source_span),
        }

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
            transform_lineage.get('content_origin')
            or parse_lineage.get('content_origin')
            or record_parse_summary.get('content_origin')
            or provenance_metadata.get('content_origin')
            or ''
        )
        artifact_identity = self._resolve_artifact_identity(
            content_origin=content_origin,
            artifact_family=str(
                transform_lineage.get('artifact_family')
                or parse_lineage.get('artifact_family')
                or record_parse_summary.get('artifact_family')
                or provenance_metadata.get('artifact_family')
                or ''
            ),
            corpus_family=str(
                transform_lineage.get('corpus_family')
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
            'record_scope': str(parse_lineage.get('record_scope') or source_family),
            'artifact_family': artifact_identity['artifact_family'],
            'corpus_family': artifact_identity['corpus_family'],
            'content_origin': content_origin,
            'parse_source': str(parse_lineage.get('source') or record_parse_summary.get('source') or ''),
            'input_format': str(parse_lineage.get('input_format') or record_parse_summary.get('input_format') or ''),
            'quality_tier': str(parse_lineage.get('quality_tier') or record_parse_summary.get('quality_tier') or ''),
            'quality_score': float(parse_lineage.get('quality_score') or record_parse_summary.get('quality_score') or parse_quality.get('quality_score') or 0.0),
            'page_count': int(parse_lineage.get('page_count') or record_parse_summary.get('page_count') or source_span.get('page_count') or 0),
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
        parse_lineage = trace.get('parse_lineage', {}) if isinstance(trace.get('parse_lineage'), dict) else {}
        record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
        record_parse_summary = record_summary.get('parse_summary', {}) if isinstance(record_summary.get('parse_summary'), dict) else {}
        source_span = parse_lineage.get('source_span') if isinstance(parse_lineage.get('source_span'), dict) else record_parse_summary.get('source_span', {}) if isinstance(record_parse_summary.get('source_span'), dict) else {}

        return {
            'corpus_family': str(parse_lineage.get('corpus_family') or record_parse_summary.get('corpus_family') or ''),
            'artifact_family': str(parse_lineage.get('artifact_family') or record_parse_summary.get('artifact_family') or ''),
            'source': str(parse_lineage.get('source') or record_parse_summary.get('source') or ''),
            'input_format': str(parse_lineage.get('input_format') or record_parse_summary.get('input_format') or ''),
            'parser_version': str(parse_lineage.get('parser_version') or ''),
            'content_origin': str(parse_lineage.get('content_origin') or record_parse_summary.get('content_origin') or ''),
            'historical_capture': bool(parse_lineage.get('historical_capture', record_parse_summary.get('historical_capture', False))),
            'capture_source': str(parse_lineage.get('capture_source') or record_parse_summary.get('capture_source') or ''),
            'archive_url': str(parse_lineage.get('archive_url') or record_parse_summary.get('archive_url') or ''),
            'original_url': str(parse_lineage.get('original_url') or record_parse_summary.get('original_url') or ''),
            'version_of': str(parse_lineage.get('version_of') or record_parse_summary.get('version_of') or ''),
            'captured_at': str(parse_lineage.get('captured_at') or record_parse_summary.get('captured_at') or ''),
            'observed_at': str(parse_lineage.get('observed_at') or record_parse_summary.get('observed_at') or ''),
            'content_source_field': str(parse_lineage.get('content_source_field') or record_parse_summary.get('content_source_field') or ''),
            'fallback_mode': str(parse_lineage.get('fallback_mode') or record_parse_summary.get('fallback_mode') or ''),
            'quality_tier': str(record_parse_summary.get('quality_tier') or parse_lineage.get('quality_tier') or ''),
            'quality_score': float(record_parse_summary.get('quality_score') or parse_lineage.get('quality_score') or 0.0),
            'page_count': int(record_parse_summary.get('page_count', 0) or 0),
            'source_span': dict(source_span),
        }

    def _build_support_packet(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        record_summary = trace.get('record_summary', {}) if isinstance(trace.get('record_summary'), dict) else {}
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
            'record_summary': record_summary,
            'lineage_summary': self._build_support_packet_lineage_summary(trace=trace),
            'source_lineage_ref': trace.get('source_lineage_ref', ''),
            'graph_summary': trace.get('graph_summary', {}),
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

    def _collect_support_traces_from_links(self, links: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        traces: List[Dict[str, Any]] = []
        for link in links or []:
            facts = link.get('facts', []) if isinstance(link.get('facts'), list) else []
            if facts:
                traces.extend(self._build_support_trace(link=link, fact=fact) for fact in facts)
                continue
            traces.append(self._build_support_trace(link=link))
        return traces

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

    def _extract_logic_contradiction_count(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> int:
        reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
        logic_contradictions = reasoning.get('logic_contradictions', {})
        if not isinstance(logic_contradictions, dict):
            return 0
        contradictions = logic_contradictions.get('contradictions', [])
        if isinstance(contradictions, list):
            return len(contradictions)
        if contradictions:
            return 1
        summary = (reasoning.get('adapter_statuses') or {}).get('logic_contradictions', {})
        if isinstance(summary, dict):
            return int(summary.get('contradictions_count', 0) or 0)
        return 0

    def _extract_logic_proof_counts(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> Dict[str, int]:
        reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
        logic_proof = reasoning.get('logic_proof', {})
        if not isinstance(logic_proof, dict):
            return {
                'provable_count': 0,
                'unprovable_count': 0,
            }
        provable_elements = logic_proof.get('provable_elements', [])
        unprovable_elements = logic_proof.get('unprovable_elements', [])
        return {
            'provable_count': len(provable_elements) if isinstance(provable_elements, list) else int(bool(provable_elements)),
            'unprovable_count': len(unprovable_elements) if isinstance(unprovable_elements, list) else int(bool(unprovable_elements)),
        }

    def _extract_ontology_validation_signal(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> str:
        reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
        ontology_validation = reasoning.get('ontology_validation', {})
        if not isinstance(ontology_validation, dict):
            return 'unknown'
        result = ontology_validation.get('result')

        def _normalize_validation_value(value: Any) -> Optional[str]:
            if isinstance(value, bool):
                return 'valid' if value else 'invalid'
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {'valid', 'validated', 'consistent', 'passed', 'pass', 'success', 'ok'}:
                    return 'valid'
                if lowered in {'invalid', 'inconsistent', 'failed', 'fail', 'error'}:
                    return 'invalid'
                return None
            if isinstance(value, dict):
                for key in ('valid', 'is_valid', 'consistent', 'passed', 'success'):
                    if key in value:
                        nested = _normalize_validation_value(value.get(key))
                        if nested:
                            return nested
                for key in ('status', 'result', 'state', 'validation_status'):
                    if key in value:
                        nested = _normalize_validation_value(value.get(key))
                        if nested:
                            return nested
            return None

        normalized = _normalize_validation_value(result)
        if normalized:
            return normalized
        status = str(ontology_validation.get('status') or '').strip().lower()
        if status == 'success':
            return 'valid'
        if status in {'error', 'failed'}:
            return 'invalid'
        return 'unknown'

    def _extract_temporal_rule_profile(
        self,
        reasoning_diagnostics: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
        temporal_rule_profile = reasoning.get('temporal_rule_profile', {})
        return temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}

    def _build_temporal_proof_bundle(
        self,
        claim_type: str,
        element: Dict[str, Any],
        temporal_context: Optional[Dict[str, Any]],
        temporal_rule_profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        profile = temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}
        if not bool(profile.get('available', False)):
            return {}

        context = temporal_context if isinstance(temporal_context, dict) else {}
        facts = [fact for fact in (context.get('temporal_facts', []) or []) if isinstance(fact, dict)]
        relations = [relation for relation in (context.get('temporal_relations', []) or []) if isinstance(relation, dict)]
        issues = [issue for issue in (context.get('temporal_issues', []) or []) if isinstance(issue, dict)]

        fact_ids = [
            str(fact.get('fact_id') or '').strip()
            for fact in facts
            if str(fact.get('fact_id') or '').strip()
        ]
        timeline_anchor_ids: List[str] = []
        for fact in facts:
            for anchor_id in fact.get('timeline_anchor_ids', []) or []:
                normalized_anchor_id = str(anchor_id or '').strip()
                if normalized_anchor_id and normalized_anchor_id not in timeline_anchor_ids:
                    timeline_anchor_ids.append(normalized_anchor_id)
        relation_ids = [
            str(relation.get('relation_id') or '').strip()
            for relation in relations
            if str(relation.get('relation_id') or '').strip()
        ]
        issue_ids = [
            str(issue.get('issue_id') or issue.get('contradiction_id') or issue.get('dependency_id') or '').strip()
            for issue in issues
            if str(issue.get('issue_id') or issue.get('contradiction_id') or issue.get('dependency_id') or '').strip()
        ]

        matched_fact_ids = [
            str(fact_id).strip()
            for fact_id in (profile.get('matched_fact_ids', []) or [])
            if str(fact_id).strip()
        ]
        matched_relation_ids = [
            str(relation_id).strip()
            for relation_id in (profile.get('matched_relation_ids', []) or [])
            if str(relation_id).strip()
        ]
        temporal_consistency_summary = (
            context.get('consistency_summary', {})
            if isinstance(context.get('consistency_summary'), dict)
            else {}
        )
        missing_temporal_predicates = [
            str(predicate).strip()
            for predicate in (temporal_consistency_summary.get('missing_temporal_predicates', []) or [])
            if str(predicate).strip()
        ]
        required_provenance_kinds = [
            str(kind).strip()
            for kind in (temporal_consistency_summary.get('required_provenance_kinds', []) or [])
            if str(kind).strip()
        ]

        source_artifact_ids: List[str] = []
        testimony_record_ids: List[str] = []
        for fact in facts:
            for artifact_id in fact.get('source_artifact_ids', []) or []:
                normalized_artifact_id = str(artifact_id or '').strip()
                if normalized_artifact_id and normalized_artifact_id not in source_artifact_ids:
                    source_artifact_ids.append(normalized_artifact_id)
            for testimony_record_id in fact.get('testimony_record_ids', []) or []:
                normalized_testimony_record_id = str(testimony_record_id or '').strip()
                if normalized_testimony_record_id and normalized_testimony_record_id not in testimony_record_ids:
                    testimony_record_ids.append(normalized_testimony_record_id)

        relation_formula_map = {
            'before': 'Before',
            'after': 'After',
            'same_time': 'SameTime',
            'overlaps': 'Overlaps',
            'during': 'During',
            'meets': 'Meets',
        }
        tdfol_formulas: List[str] = []
        dcec_formulas: List[str] = []
        role = str(profile.get('element_role') or '').strip()

        for fact in facts:
            fact_id = str(fact.get('fact_id') or '').strip()
            if not fact_id:
                continue
            if 'protected_activity' in [self._normalize_reasoning_key(tag) for tag in (fact.get('element_tags', []) or [])]:
                formula = f'ProtectedActivity({fact_id})'
                if formula not in tdfol_formulas:
                    tdfol_formulas.append(formula)
            if 'adverse_action' in [self._normalize_reasoning_key(tag) for tag in (fact.get('element_tags', []) or [])]:
                formula = f'AdverseAction({fact_id})'
                if formula not in tdfol_formulas:
                    tdfol_formulas.append(formula)
            temporal_context = fact.get('temporal_context', {}) if isinstance(fact.get('temporal_context'), dict) else {}
            start_date = str(temporal_context.get('start_date') or '').strip()
            if start_date:
                time_symbol = f"t_{start_date.replace('-', '_')}"
                formula = f'Happens({fact_id},{time_symbol})'
                if formula not in dcec_formulas:
                    dcec_formulas.append(formula)

        for relation in relations:
            source_fact_id = str(relation.get('source_fact_id') or '').strip()
            target_fact_id = str(relation.get('target_fact_id') or '').strip()
            relation_type = self._normalize_reasoning_key(relation.get('relation_type'))
            if not source_fact_id or not target_fact_id:
                continue
            relation_predicate = relation_formula_map.get(relation_type)
            if relation_predicate:
                formula = f'{relation_predicate}({source_fact_id},{target_fact_id})'
                if formula not in tdfol_formulas:
                    tdfol_formulas.append(formula)

        proof_bundle_id = ':'.join(
            part
            for part in [
                self._normalize_reasoning_key(claim_type) or 'claim',
                self._normalize_reasoning_key(element.get('element_id') or element.get('element_text')) or 'element',
                self._normalize_reasoning_key(profile.get('profile_id')) or 'temporal_rule_profile',
            ]
            if part
        )
        theorem_export_metadata = {
            'contract_version': 'claim_support_temporal_handoff_v1',
            'claim_type': str(claim_type or ''),
            'claim_element_id': str(element.get('element_id') or ''),
            'proof_bundle_id': proof_bundle_id,
            'rule_frame_id': str(profile.get('rule_frame_id') or ''),
            'chronology_blocked': bool(issue_ids or profile.get('blocking_reasons')),
            'chronology_task_count': len([
                follow_up
                for follow_up in (profile.get('recommended_follow_ups', []) or [])
                if isinstance(follow_up, dict)
            ]) or len([
                str(reason).strip()
                for reason in (profile.get('blocking_reasons', []) or [])
                if str(reason).strip()
            ]) or len(issue_ids),
            'unresolved_temporal_issue_ids': list(issue_ids),
            'event_ids': list(fact_ids),
            'temporal_fact_ids': list(fact_ids),
            'temporal_relation_ids': list(relation_ids),
            'timeline_anchor_ids': list(timeline_anchor_ids),
            'timeline_issue_ids': list(issue_ids),
            'temporal_issue_ids': list(issue_ids),
            'missing_temporal_predicates': list(missing_temporal_predicates),
            'required_provenance_kinds': list(required_provenance_kinds),
            'temporal_proof_bundle_ids': [proof_bundle_id] if proof_bundle_id else [],
            'temporal_proof_objectives': [str(profile.get('rule_frame_id') or '').strip()] if str(profile.get('rule_frame_id') or '').strip() else [],
        }

        return {
            'proof_bundle_id': proof_bundle_id,
            'claim_type': str(claim_type or ''),
            'claim_element_id': str(element.get('element_id') or ''),
            'claim_element_text': str(element.get('element_text') or ''),
            'profile_id': str(profile.get('profile_id') or ''),
            'rule_frame_id': str(profile.get('rule_frame_id') or ''),
            'element_role': role,
            'status': str(profile.get('status') or ''),
            'available': bool(profile.get('available', False)),
            'matched_fact_ids': matched_fact_ids,
            'matched_relation_ids': matched_relation_ids,
            'temporal_fact_ids': fact_ids,
            'temporal_relation_ids': relation_ids,
            'timeline_anchor_ids': timeline_anchor_ids,
            'temporal_issue_ids': issue_ids,
            'source_artifact_ids': source_artifact_ids,
            'testimony_record_ids': testimony_record_ids,
            'missing_temporal_predicates': missing_temporal_predicates,
            'required_provenance_kinds': required_provenance_kinds,
            'blocking_reasons': [
                str(reason).strip()
                for reason in (profile.get('blocking_reasons', []) or [])
                if str(reason).strip()
            ],
            'warnings': [
                str(warning).strip()
                for warning in (profile.get('warnings', []) or [])
                if str(warning).strip()
            ],
            'recommended_follow_ups': [
                follow_up
                for follow_up in (profile.get('recommended_follow_ups', []) or [])
                if isinstance(follow_up, dict)
            ],
            'theorem_exports': {
                'tdfol_formulas': tdfol_formulas[:10],
                'dcec_formulas': dcec_formulas[:10],
                'theorem_export_metadata': theorem_export_metadata,
            },
            'theorem_export_counts': {
                'tdfol_formula_count': len(tdfol_formulas),
                'dcec_formula_count': len(dcec_formulas),
            },
        }

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

        chronology_task_count = len(recommended_follow_ups) or len(blocking_reasons) or len(issue_ids)
        temporal_handoff = {
            'claim_type': str(claim_type or '').strip(),
            'claim_element_id': str(element.get('element_id') or '').strip(),
            'unresolved_temporal_issue_count': len(issue_ids),
            'unresolved_temporal_issue_ids': issue_ids,
            'chronology_task_count': chronology_task_count,
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
            if (
                not (element.get('missing_support_kinds', []) or [])
                and not self._has_reasoning_gap_signals(
                    self._extract_proof_gap_types(proof_gaps or []),
                    element.get('proof_decision_trace', {}) if isinstance(element.get('proof_decision_trace'), dict) else {},
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
        return (
            'logic_unprovable' in (proof_gap_types or [])
            or 'temporal_rule_failed' in (proof_gap_types or [])
            or 'temporal_rule_partial' in (proof_gap_types or [])
            or 'ontology_validation_failed' in (proof_gap_types or [])
            or decision_source in {'logic_unprovable', 'logic_proof_partial', 'ontology_validation_failed', 'temporal_rule_failed', 'temporal_rule_partial'}
            or ontology_validation_signal == 'invalid'
        )

    def _normalize_reasoning_key(self, value: Any) -> str:
        text = str(value or '').strip().lower()
        return ''.join(ch if ch.isalnum() else '_' for ch in text).strip('_')

    def _get_temporal_reasoning_context(
        self,
        claim_type: str,
        element: Dict[str, Any],
    ) -> Dict[str, Any]:
        status_getter = getattr(self.mediator, 'get_three_phase_status', None)
        if not callable(status_getter):
            return {}

        try:
            status = status_getter()
        except Exception:
            return {}
        if not isinstance(status, dict):
            return {}

        canonical_fact_summary = status.get('canonical_fact_summary', {})
        proof_lead_summary = status.get('proof_lead_summary', {})
        temporal_fact_registry_summary = status.get('temporal_fact_registry_summary', {})
        temporal_relation_registry_summary = status.get('temporal_relation_registry_summary', {})
        timeline_relation_summary = status.get('timeline_relation_summary', {})
        timeline_consistency_summary = status.get('timeline_consistency_summary', {})
        temporal_issue_registry_summary = status.get('temporal_issue_registry_summary', {})
        intake_contradictions = status.get('intake_contradictions', {})

        canonical_facts = temporal_fact_registry_summary.get('facts', []) if isinstance(temporal_fact_registry_summary, dict) else []
        if not isinstance(canonical_facts, list) or not canonical_facts:
            canonical_facts = canonical_fact_summary.get('facts', []) if isinstance(canonical_fact_summary, dict) else []
        proof_leads = proof_lead_summary.get('proof_leads', []) if isinstance(proof_lead_summary, dict) else []
        timeline_relations = temporal_relation_registry_summary.get('relations', []) if isinstance(temporal_relation_registry_summary, dict) else []
        if not isinstance(timeline_relations, list) or not timeline_relations:
            timeline_relations = timeline_relation_summary.get('relations', []) if isinstance(timeline_relation_summary, dict) else []
        contradiction_candidates = temporal_issue_registry_summary.get('issues', []) if isinstance(temporal_issue_registry_summary, dict) else []
        if not isinstance(contradiction_candidates, list) or not contradiction_candidates:
            contradiction_candidates = intake_contradictions.get('candidates', []) if isinstance(intake_contradictions, dict) else []

        claim_key = self._normalize_reasoning_key(claim_type)
        element_keys = {
            self._normalize_reasoning_key(element.get('element_id')),
            self._normalize_reasoning_key(element.get('element_text')),
        }
        element_keys.discard('')

        def _extract_temporal_context(record: Dict[str, Any]) -> Dict[str, Any]:
            return record.get('temporal_context', {}) if isinstance(record.get('temporal_context'), dict) else {}

        def _has_temporal_context(record: Dict[str, Any]) -> bool:
            temporal_context = _extract_temporal_context(record)
            return bool(
                temporal_context.get('start_date')
                or temporal_context.get('end_date')
                or temporal_context.get('relative_markers')
            )

        def _matches_claim(record: Dict[str, Any]) -> bool:
            if not claim_key or not isinstance(record, dict):
                return False
            intent = record.get('intake_question_intent', {}) if isinstance(record.get('intake_question_intent'), dict) else {}
            values: List[Any] = []
            values.extend(record.get('claim_types', []) if isinstance(record.get('claim_types'), list) else [])
            values.append(record.get('claim_type'))
            values.append(intent.get('target_claim_type'))
            normalized_values = {
                self._normalize_reasoning_key(item)
                for item in values
                if str(item or '').strip()
            }
            return claim_key in normalized_values

        def _matches_element(record: Dict[str, Any], field_names: List[str]) -> bool:
            if not element_keys or not isinstance(record, dict):
                return False
            intent = record.get('intake_question_intent', {}) if isinstance(record.get('intake_question_intent'), dict) else {}
            values: List[Any] = []
            for field_name in field_names:
                field_value = record.get(field_name)
                if isinstance(field_value, list):
                    values.extend(field_value)
                elif str(field_value or '').strip():
                    values.append(field_value)
            values.append(intent.get('target_element_id'))
            normalized_values = {
                self._normalize_reasoning_key(item)
                for item in values
                if str(item or '').strip()
            }
            return bool(element_keys & normalized_values)

        def _is_temporal_issue(record: Dict[str, Any]) -> bool:
            category = self._normalize_reasoning_key(record.get('category') or record.get('issue_type'))
            return category.startswith('temporal') or category in {
                'missing_anchor',
                'relative_only_ordering',
                'contradictory_dates',
                'limitations_risk',
            }

        element_temporal_facts: List[Dict[str, Any]] = []
        claim_temporal_facts: List[Dict[str, Any]] = []
        claim_fact_map: Dict[str, Dict[str, Any]] = {}
        for fact in canonical_facts if isinstance(canonical_facts, list) else []:
            if not isinstance(fact, dict) or not _has_temporal_context(fact):
                continue
            fact_id = str(fact.get('fact_id') or '').strip()
            if fact_id:
                claim_fact_map[fact_id] = fact
            if _matches_element(fact, ['element_tags']):
                element_temporal_facts.append(fact)
            elif _matches_claim(fact):
                claim_temporal_facts.append(fact)

        selected_temporal_facts = element_temporal_facts or claim_temporal_facts
        selected_fact_ids = {
            str(fact.get('fact_id') or '').strip()
            for fact in selected_temporal_facts
            if isinstance(fact, dict) and str(fact.get('fact_id') or '').strip()
        }

        element_temporal_leads: List[Dict[str, Any]] = []
        claim_temporal_leads: List[Dict[str, Any]] = []
        for lead in proof_leads if isinstance(proof_leads, list) else []:
            if not isinstance(lead, dict) or not _has_temporal_context(lead):
                continue
            if _matches_element(lead, ['element_targets', 'fact_targets']):
                element_temporal_leads.append(lead)
            elif _matches_claim(lead):
                claim_temporal_leads.append(lead)

        selected_temporal_leads = element_temporal_leads or claim_temporal_leads
        for lead in selected_temporal_leads:
            for fact_id in lead.get('related_fact_ids', []) if isinstance(lead.get('related_fact_ids'), list) else []:
                normalized_fact_id = str(fact_id or '').strip()
                if normalized_fact_id:
                    selected_fact_ids.add(normalized_fact_id)

        selected_temporal_relations: List[Dict[str, Any]] = []
        for relation in timeline_relations if isinstance(timeline_relations, list) else []:
            if not isinstance(relation, dict):
                continue
            source_fact_id = str(relation.get('source_fact_id') or '').strip()
            target_fact_id = str(relation.get('target_fact_id') or '').strip()
            if selected_fact_ids and (source_fact_id in selected_fact_ids or target_fact_id in selected_fact_ids):
                selected_temporal_relations.append(relation)
                if source_fact_id:
                    selected_fact_ids.add(source_fact_id)
                if target_fact_id:
                    selected_fact_ids.add(target_fact_id)

        if selected_fact_ids:
            selected_temporal_facts = [
                fact for fact in claim_fact_map.values()
                if str(fact.get('fact_id') or '').strip() in selected_fact_ids
            ]

        selected_fact_labels = {
            str(fact.get('text') or '').strip()
            for fact in selected_temporal_facts
            if isinstance(fact, dict) and str(fact.get('text') or '').strip()
        }
        selected_temporal_issues: List[Dict[str, Any]] = []
        for candidate in contradiction_candidates if isinstance(contradiction_candidates, list) else []:
            if not isinstance(candidate, dict):
                continue
            if not _is_temporal_issue(candidate):
                continue
            issue_fact_ids = {
                str(item or '').strip()
                for item in candidate.get('fact_ids', [])
                if str(item or '').strip()
            } if isinstance(candidate.get('fact_ids'), list) else set()
            node_names = {
                str(candidate.get('left_node_name') or '').strip(),
                str(candidate.get('right_node_name') or '').strip(),
            }
            if _matches_element(candidate, ['element_tags', 'affected_element_ids']):
                selected_temporal_issues.append(candidate)
                continue
            if _matches_claim(candidate):
                selected_temporal_issues.append(candidate)
                continue
            if selected_fact_ids and issue_fact_ids and (selected_fact_ids & issue_fact_ids):
                selected_temporal_issues.append(candidate)
                continue
            if selected_fact_labels and not (selected_fact_labels & node_names):
                continue
            selected_temporal_issues.append(candidate)

        if not selected_temporal_facts and not selected_temporal_leads and not selected_temporal_relations and not selected_temporal_issues:
            return {}

        relation_type_counts: Dict[str, int] = {}
        for relation in selected_temporal_relations:
            relation_type = str(relation.get('relation_type') or '').strip()
            if relation_type:
                relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1

        timeline_anchor_ids: List[str] = []
        for fact in selected_temporal_facts:
            if not isinstance(fact, dict):
                continue
            for anchor_id in fact.get('timeline_anchor_ids', []) or []:
                normalized_anchor_id = str(anchor_id or '').strip()
                if normalized_anchor_id and normalized_anchor_id not in timeline_anchor_ids:
                    timeline_anchor_ids.append(normalized_anchor_id)

        relation_formula_map = {
            'before': 'Before',
            'after': 'After',
            'same_time': 'SameTime',
            'overlaps': 'Overlaps',
            'during': 'During',
            'meets': 'Meets',
        }
        derived_missing_temporal_predicates: List[str] = []
        for relation in selected_temporal_relations:
            if not isinstance(relation, dict):
                continue
            source_fact_id = str(relation.get('source_fact_id') or '').strip()
            target_fact_id = str(relation.get('target_fact_id') or '').strip()
            relation_type = relation_formula_map.get(self._normalize_reasoning_key(relation.get('relation_type')))
            if not source_fact_id or not target_fact_id or not relation_type:
                continue
            formula = f'{relation_type}({source_fact_id},{target_fact_id})'
            if formula not in derived_missing_temporal_predicates:
                derived_missing_temporal_predicates.append(formula)

        consistency_payload = timeline_consistency_summary if isinstance(timeline_consistency_summary, dict) else {}
        missing_temporal_predicates = [
            str(predicate).strip()
            for predicate in (consistency_payload.get('missing_temporal_predicates', []) or [])
            if str(predicate).strip()
        ]
        if not missing_temporal_predicates:
            missing_temporal_predicates = list(derived_missing_temporal_predicates)
        required_provenance_kinds = [
            str(kind).strip()
            for kind in (consistency_payload.get('required_provenance_kinds', []) or [])
            if str(kind).strip()
        ]
        if not required_provenance_kinds:
            for issue in selected_temporal_issues:
                if str((issue or {}).get('recommended_resolution_lane') or '').strip().lower() == 'request_document':
                    required_provenance_kinds.append('document_artifact')
                    break
        consistency_summary = {
            'event_count': len(selected_temporal_facts),
            'proof_lead_count': len(selected_temporal_leads),
            'relation_count': len(selected_temporal_relations),
            'issue_count': len(selected_temporal_issues),
            'partial_order_ready': bool(consistency_payload.get('partial_order_ready', not selected_temporal_issues)),
            'warnings': list(consistency_payload.get('warnings', []) if isinstance(consistency_payload.get('warnings'), list) else []),
            'relation_type_counts': relation_type_counts,
            'timeline_anchor_ids': timeline_anchor_ids,
            'missing_temporal_predicates': missing_temporal_predicates,
            'required_provenance_kinds': required_provenance_kinds,
        }
        consistency_summary['warning_count'] = len(consistency_summary['warnings'])

        return {
            'temporal_facts': selected_temporal_facts,
            'temporal_proof_leads': selected_temporal_leads,
            'temporal_relations': selected_temporal_relations,
            'temporal_issues': selected_temporal_issues,
            'consistency_summary': consistency_summary,
        }

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
        adapter_result = adapter_result if isinstance(adapter_result, dict) else {}
        metadata = adapter_result.get('metadata', {}) if isinstance(adapter_result.get('metadata'), dict) else {}
        summary = {
            'status': str(adapter_result.get('status') or ''),
            'operation': str(metadata.get('operation') or ''),
            'implementation_status': str(metadata.get('implementation_status') or ''),
            'backend_available': bool(metadata.get('backend_available', False)),
            'degraded_reason': str(metadata.get('degraded_reason') or adapter_result.get('degraded_reason') or ''),
        }
        for field in count_fields or []:
            if field in adapter_result:
                value = adapter_result.get(field)
                if isinstance(value, list):
                    summary[f'{field}_count'] = len(value)
                elif isinstance(value, dict):
                    summary[f'{field}_key_count'] = len(value)
                elif value is not None:
                    summary[field] = value
        return summary

    def _run_element_reasoning_diagnostics(
        self,
        claim_type: str,
        element: Dict[str, Any],
        contradiction_candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        support_texts = [
            str(trace.get('fact_text') or trace.get('support_label') or '')
            for trace in element.get('support_traces', []) or []
            if isinstance(trace, dict) and (trace.get('fact_text') or trace.get('support_label'))
        ]
        ontology_seed_text = '\n'.join(
            part for part in [
                f"Claim type: {claim_type}",
                f"Claim element: {element.get('element_text') or ''}",
                'Support facts:',
                *support_texts,
            ]
            if part
        )
        temporal_context = self._get_temporal_reasoning_context(claim_type, element)
        temporal_seed_lines: List[str] = []
        for fact in temporal_context.get('temporal_facts', []) or []:
            if not isinstance(fact, dict):
                continue
            temporal_details = fact.get('temporal_context', {}) if isinstance(fact.get('temporal_context'), dict) else {}
            temporal_seed_lines.append(
                f"Timeline fact: {fact.get('text') or fact.get('fact_id') or 'timeline_fact'} [{temporal_details.get('start_date') or '?'} -> {temporal_details.get('end_date') or '?'}]"
            )
        for relation in temporal_context.get('temporal_relations', []) or []:
            if not isinstance(relation, dict):
                continue
            temporal_seed_lines.append(
                f"Timeline relation: {relation.get('source_fact_id') or '?'} {relation.get('relation_type') or 'related_to'} {relation.get('target_fact_id') or '?'}"
            )
        consistency_summary = temporal_context.get('consistency_summary', {}) if isinstance(temporal_context.get('consistency_summary'), dict) else {}
        if consistency_summary:
            temporal_seed_lines.append(
                f"Timeline consistency: partial_order_ready={bool(consistency_summary.get('partial_order_ready', False))}, warnings={int(consistency_summary.get('warning_count', 0) or 0)}"
            )
        for issue in temporal_context.get('temporal_issues', []) or []:
            if not isinstance(issue, dict):
                continue
            temporal_seed_lines.append(
                f"Temporal issue: {issue.get('summary') or issue.get('label') or issue.get('category') or 'temporal_issue'}"
            )
        if temporal_seed_lines:
            ontology_seed_text = '\n'.join([ontology_seed_text, *temporal_seed_lines]) if ontology_seed_text else '\n'.join(temporal_seed_lines)

        predicates = self._build_reasoning_predicates(
            claim_type,
            element,
            contradiction_candidates,
            temporal_context=temporal_context,
        )
        ontology_build = build_ontology(ontology_seed_text)
        fallback_ontology = self._build_reasoning_ontology_fallback(
            claim_type,
            element,
            contradiction_candidates,
            temporal_context=temporal_context,
        )
        ontology_payload = ontology_build.get('ontology') if isinstance(ontology_build, dict) else None
        ontology_for_validation = ontology_payload if ontology_payload not in (None, '') else fallback_ontology
        temporal_rule_profile = evaluate_temporal_rule_profile(claim_type, element, temporal_context)
        temporal_proof_bundle = self._build_temporal_proof_bundle(
            claim_type,
            element,
            temporal_context,
            temporal_rule_profile,
        )
        claim_support_temporal_handoff = self._build_claim_support_temporal_handoff(
            claim_type,
            element,
            temporal_context,
            temporal_proof_bundle,
            temporal_rule_profile,
        )
        reasoning_payload = {
            'predicates': predicates,
            'claim_support_temporal_handoff': claim_support_temporal_handoff,
        }
        logic_proof = prove_claim_elements(reasoning_payload)
        logic_contradictions = check_contradictions(reasoning_payload)
        hybrid_reasoning = run_hybrid_reasoning(reasoning_payload)
        ontology_validation = validate_ontology(ontology_for_validation)

        temporal_summary: Dict[str, Any] = {}
        if temporal_context:
            temporal_consistency_summary = (
                temporal_context.get('consistency_summary', {})
                if isinstance(temporal_context.get('consistency_summary'), dict)
                else {}
            )
            temporal_relation_type_counts = dict(
                temporal_consistency_summary.get('relation_type_counts', {}) or {}
            )
            temporal_warnings = list(temporal_consistency_summary.get('warnings', []) or [])
            temporal_relation_preview = []
            for relation in temporal_context.get('temporal_relations', []) or []:
                if not isinstance(relation, dict):
                    continue
                source_fact_id = str(relation.get('source_fact_id') or '').strip()
                target_fact_id = str(relation.get('target_fact_id') or '').strip()
                relation_type = str(relation.get('relation_type') or '').strip().replace('_', ' ')
                preview = ' '.join(part for part in [source_fact_id, relation_type, target_fact_id] if part).strip()
                if preview and preview not in temporal_relation_preview:
                    temporal_relation_preview.append(preview)
                if len(temporal_relation_preview) >= 3:
                    break
            temporal_summary = {
                'fact_count': len(temporal_context.get('temporal_facts', []) or []),
                'proof_lead_count': len(temporal_context.get('temporal_proof_leads', []) or []),
                'relation_count': len(temporal_context.get('temporal_relations', []) or []),
                'issue_count': len(temporal_context.get('temporal_issues', []) or []),
                'partial_order_ready': bool(
                    temporal_consistency_summary.get('partial_order_ready', False)
                ),
                'warning_count': int(temporal_consistency_summary.get('warning_count', 0) or 0),
                'warnings': temporal_warnings,
                'relation_type_counts': temporal_relation_type_counts,
                'relation_preview': temporal_relation_preview,
            }

        adapter_statuses = {
            'ontology_build': self._summarize_adapter_result(
                ontology_build,
                count_fields=['ontology'],
            ),
            'logic_proof': self._summarize_adapter_result(
                logic_proof,
                count_fields=['predicate_count', 'provable_elements', 'unprovable_elements'],
            ),
            'logic_contradictions': self._summarize_adapter_result(
                logic_contradictions,
                count_fields=['predicate_count', 'contradictions'],
            ),
            'hybrid_reasoning': self._summarize_adapter_result(
                hybrid_reasoning,
                count_fields=['predicate_count', 'result', 'temporal_reasoning_payload'],
            ),
            'ontology_validation': self._summarize_adapter_result(
                ontology_validation,
                count_fields=['result'],
            ),
        }

        return {
            'predicate_count': len(predicates),
            'ontology_entity_count': len(fallback_ontology.get('entities', []) or []),
            'ontology_relationship_count': len(fallback_ontology.get('relationships', []) or []),
            'used_fallback_ontology': ontology_payload in (None, ''),
            'adapter_statuses': adapter_statuses,
            'backend_available_count': len(
                [summary for summary in adapter_statuses.values() if summary.get('backend_available')]
            ),
            'ontology_build': ontology_build,
            'logic_proof': logic_proof,
            'logic_contradictions': logic_contradictions,
            'hybrid_reasoning': hybrid_reasoning,
            'ontology_validation': ontology_validation,
            'temporal_summary': temporal_summary,
            'temporal_rule_profile': temporal_rule_profile,
            'temporal_proof_bundle': temporal_proof_bundle,
            'claim_support_temporal_handoff': claim_support_temporal_handoff,
        }

    def _summarize_claim_reasoning_diagnostics(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        adapter_status_counts: Dict[str, Dict[str, int]] = {
            'ontology_build': {},
            'logic_proof': {},
            'logic_contradictions': {},
            'hybrid_reasoning': {},
            'ontology_validation': {},
        }
        backend_available_count = 0
        predicate_count = 0
        ontology_entity_count = 0
        ontology_relationship_count = 0
        fallback_ontology_count = 0
        hybrid_bridge_available_count = 0
        hybrid_tdfol_formula_count = 0
        hybrid_dcec_formula_count = 0
        temporal_fact_count = 0
        temporal_relation_count = 0
        temporal_issue_count = 0
        temporal_partial_order_ready_count = 0
        temporal_warning_count = 0
        temporal_rule_profile_available_count = 0
        temporal_rule_profile_satisfied_count = 0
        temporal_rule_profile_partial_count = 0
        temporal_rule_profile_failed_count = 0
        temporal_proof_bundle_count = 0

        for element in elements:
            if not isinstance(element, dict):
                continue
            reasoning = element.get('reasoning_diagnostics', {})
            if not isinstance(reasoning, dict):
                continue
            predicate_count += int(reasoning.get('predicate_count', 0) or 0)
            ontology_entity_count += int(reasoning.get('ontology_entity_count', 0) or 0)
            ontology_relationship_count += int(reasoning.get('ontology_relationship_count', 0) or 0)
            backend_available_count += int(reasoning.get('backend_available_count', 0) or 0)
            if reasoning.get('used_fallback_ontology'):
                fallback_ontology_count += 1
            hybrid_reasoning = reasoning.get('hybrid_reasoning', {})
            if isinstance(hybrid_reasoning, dict):
                hybrid_result = hybrid_reasoning.get('result', {}) if isinstance(hybrid_reasoning.get('result'), dict) else {}
                if bool(hybrid_result.get('compiler_bridge_available', False)):
                    hybrid_bridge_available_count += 1
                hybrid_tdfol_formula_count += len(hybrid_result.get('tdfol_formulas', []) or [])
                hybrid_dcec_formula_count += len(hybrid_result.get('dcec_formulas', []) or [])
            temporal_summary = reasoning.get('temporal_summary', {})
            if isinstance(temporal_summary, dict):
                temporal_fact_count += int(temporal_summary.get('fact_count', 0) or 0)
                temporal_relation_count += int(temporal_summary.get('relation_count', 0) or 0)
                temporal_issue_count += int(temporal_summary.get('issue_count', 0) or 0)
                temporal_warning_count += int(temporal_summary.get('warning_count', 0) or 0)
                if bool(temporal_summary.get('partial_order_ready', False)):
                    temporal_partial_order_ready_count += 1
            temporal_rule_profile = reasoning.get('temporal_rule_profile', {})
            if isinstance(temporal_rule_profile, dict) and bool(temporal_rule_profile.get('available', False)):
                temporal_rule_profile_available_count += 1
                temporal_rule_status = str(temporal_rule_profile.get('status') or '')
                if temporal_rule_status == 'satisfied':
                    temporal_rule_profile_satisfied_count += 1
                elif temporal_rule_status == 'partial':
                    temporal_rule_profile_partial_count += 1
                elif temporal_rule_status == 'failed':
                    temporal_rule_profile_failed_count += 1
            temporal_proof_bundle = reasoning.get('temporal_proof_bundle', {})
            if isinstance(temporal_proof_bundle, dict) and temporal_proof_bundle:
                temporal_proof_bundle_count += 1
            for adapter_name, summary in (reasoning.get('adapter_statuses') or {}).items():
                if not isinstance(summary, dict):
                    continue
                status = str(summary.get('implementation_status') or summary.get('status') or 'unknown')
                adapter_counts = adapter_status_counts.setdefault(adapter_name, {})
                adapter_counts[status] = adapter_counts.get(status, 0) + 1

        return {
            'adapter_status_counts': adapter_status_counts,
            'backend_available_count': backend_available_count,
            'predicate_count': predicate_count,
            'ontology_entity_count': ontology_entity_count,
            'ontology_relationship_count': ontology_relationship_count,
            'fallback_ontology_count': fallback_ontology_count,
            'hybrid_bridge_available_count': hybrid_bridge_available_count,
            'hybrid_tdfol_formula_count': hybrid_tdfol_formula_count,
            'hybrid_dcec_formula_count': hybrid_dcec_formula_count,
            'temporal_fact_count': temporal_fact_count,
            'temporal_relation_count': temporal_relation_count,
            'temporal_issue_count': temporal_issue_count,
            'temporal_partial_order_ready_count': temporal_partial_order_ready_count,
            'temporal_warning_count': temporal_warning_count,
            'temporal_rule_profile_available_count': temporal_rule_profile_available_count,
            'temporal_rule_profile_satisfied_count': temporal_rule_profile_satisfied_count,
            'temporal_rule_profile_partial_count': temporal_rule_profile_partial_count,
            'temporal_rule_profile_failed_count': temporal_rule_profile_failed_count,
            'temporal_proof_bundle_count': temporal_proof_bundle_count,
        }

    def _summarize_claim_validation_decisions(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        decision_source_counts: Counter[str] = Counter()
        adapter_contradicted_element_count = 0
        fallback_ontology_element_count = 0
        proof_supported_element_count = 0
        logic_unprovable_element_count = 0
        ontology_invalid_element_count = 0
        temporal_rule_gap_element_count = 0

        for element in elements:
            if not isinstance(element, dict):
                continue
            trace = element.get('proof_decision_trace', {})
            if not isinstance(trace, dict):
                continue
            source = str(trace.get('decision_source') or 'unknown')
            decision_source_counts[source] += 1
            if int(trace.get('logic_contradiction_count', 0) or 0) > 0:
                adapter_contradicted_element_count += 1
            if bool(trace.get('used_fallback_ontology')):
                fallback_ontology_element_count += 1
            if source in {'logic_proof_supported', 'ontology_validation_supported'}:
                proof_supported_element_count += 1
            if source == 'logic_unprovable':
                logic_unprovable_element_count += 1
            if str(trace.get('ontology_validation_signal') or '') == 'invalid':
                ontology_invalid_element_count += 1
            if str(trace.get('temporal_rule_status') or '') in {'failed', 'partial'}:
                temporal_rule_gap_element_count += 1

        return {
            'decision_source_counts': dict(sorted(decision_source_counts.items())),
            'adapter_contradicted_element_count': adapter_contradicted_element_count,
            'fallback_ontology_element_count': fallback_ontology_element_count,
            'proof_supported_element_count': proof_supported_element_count,
            'logic_unprovable_element_count': logic_unprovable_element_count,
            'ontology_invalid_element_count': ontology_invalid_element_count,
            'temporal_rule_gap_element_count': temporal_rule_gap_element_count,
        }

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
                'contradiction_candidate_count': len(contradiction_candidates),
                'contradiction_candidates': contradiction_candidates,
                'proof_gap_count': len(proof_gaps),
                'proof_gaps': proof_gaps,
                'proof_diagnostics': proof_diagnostics,
                'proof_decision_trace': decision_trace,
                'reasoning_diagnostics': reasoning_diagnostics,
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
                    claim_element_text,
                    support_kind,
                    support_ref,
                    support_label,
                    source_table,
                    support_strength,
                    json.dumps(normalized_metadata or {}),
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
                'rule_candidate_summary': authority_record.get('rule_candidate_summary', {}),
                'search_program_count': len(authority_record.get('metadata', {}).get('search_programs', []) or [])
                if isinstance(authority_record.get('metadata'), dict)
                else 0,
            }
            enriched['treatment_records'] = authority_record.get('treatment_records', [])
            enriched['treatment_summary'] = authority_record.get('treatment_summary', {})
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
                        'authority_treatment_summary': authority_treatment_summary,
                        'authority_rule_candidate_summary': authority_rule_candidate_summary,
                        'links': requirement_links,
                    }
                )

            summary['claims'][current_claim] = {
                'total_links': len(claim_links),
                'total_facts': total_facts,
                'support_by_kind': support_by_kind,
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

            for element in claim_summary.get('elements', []):
                kinds_present = set(element.get('support_by_kind', {}).keys())
                if element.get('total_links', 0) == 0:
                    missing.append(element)
                elif all(kind in kinds_present for kind in required_kinds):
                    covered.append(element)
                else:
                    partially_supported.append(element)

            overview['claims'][current_claim] = {
                'required_support_kinds': required_kinds,
                'covered': covered,
                'partially_supported': partially_supported,
                'missing': missing,
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
                support_trace_summary = self._summarize_support_traces(support_traces)
                support_packets = [self._build_support_packet(trace) for trace in support_traces]

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
                        'support_trace_summary': support_trace_summary,
                        'support_packets': support_packets,
                        'support_packet_summary': self._summarize_support_packets(support_packets),
                        'links': element.get('links', []),
                    }
                )

            claim_support_traces = self._collect_support_traces_from_links(claim_summary.get('links', []))
            claim_support_packets = [self._build_support_packet(trace) for trace in claim_support_traces]
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
                'support_trace_summary': self._summarize_support_traces(claim_support_traces),
                'support_packet_summary': self._summarize_support_packets(claim_support_packets),
                'elements': elements,
                'unassigned_links': claim_summary.get('unassigned_links', []),
            }

        return self._with_intake_summary_handoff(matrix)

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
                        'support_traces': support_traces,
                        'support_trace_summary': self._summarize_support_traces(support_traces),
                        'support_packets': support_packets,
                        'support_packet_summary': self._summarize_support_packets(support_packets),
                        'graph_trace_summary': self._summarize_graph_traces(element.get('links', [])),
                        'recommended_action': (
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
                'adaptive_retry_applied': bool(metadata.get('adaptive_retry_applied', False)),
                'adaptive_retry_reason': metadata.get('adaptive_retry_reason', ''),
                'adaptive_query_strategy': metadata.get('adaptive_query_strategy', ''),
                'adaptive_priority_penalty': int(metadata.get('adaptive_priority_penalty', 0) or 0),
                'result_count': int(metadata.get('result_count', 0) or 0),
                'stored_result_count': int(metadata.get('stored_result_count', 0) or 0),
                'zero_result': bool(metadata.get('zero_result', False)),
                'resolution_applied': metadata.get('resolution_applied', ''),
                'recommended_action': metadata.get('recommended_action', ''),
                'skip_reason': metadata.get('skip_reason', ''),
                'resolution_status': metadata.get('resolution_status', ''),
                'resolution_notes': metadata.get('resolution_notes', ''),
                'related_execution_id': metadata.get('related_execution_id'),
                'selected_search_program_id': metadata.get('selected_search_program_id', ''),
                'selected_search_program_type': metadata.get('selected_search_program_type', ''),
                'selected_search_program_bias': metadata.get('selected_search_program_bias', ''),
                'selected_search_program_rule_bias': metadata.get('selected_search_program_rule_bias', ''),
                'selected_search_program_families': list(metadata.get('selected_search_program_families', []) or []),
                'source_family': metadata.get('source_family', ''),
                'record_scope': metadata.get('record_scope', ''),
                'artifact_family': metadata.get('artifact_family', ''),
                'corpus_family': metadata.get('corpus_family', ''),
                'content_origin': metadata.get('content_origin', ''),
                'graph_support_summary': dict(metadata.get('graph_support_summary', {}) or {}),
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
