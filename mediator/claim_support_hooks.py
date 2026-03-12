"""Persistent claim-support coverage hooks for mediator."""

from __future__ import annotations

import json
import re
import hashlib
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from integrations.ipfs_datasets.graphrag import build_ontology, validate_ontology
from integrations.ipfs_datasets.logic import check_contradictions, prove_claim_elements

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


class ClaimSupportHook:
    """Track which evidence and authorities support each claim type."""

    def __init__(self, mediator, db_path: Optional[str] = None):
        self.mediator = mediator
        self.db_path = db_path or self._get_default_db_path()
        self._check_duckdb_availability()
        if DUCKDB_AVAILABLE:
            self._prepare_duckdb_path()
            self._initialize_schema()

    def _get_default_db_path(self) -> str:
        state_dir = Path(__file__).parent.parent / 'statefiles'
        if not state_dir.exists():
            state_dir = Path('.')
        return str(state_dir / 'claim_support.duckdb')

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
            conn.execute("ALTER TABLE claim_support ADD COLUMN IF NOT EXISTS claim_element_id VARCHAR")
            conn.execute("ALTER TABLE claim_support ADD COLUMN IF NOT EXISTS claim_element_text TEXT")
            conn.close()
            self.mediator.log('claim_support_schema_initialized', db_path=self.db_path)
        except Exception as exc:
            self.mediator.log('claim_support_schema_error', error=str(exc))

    def _make_element_id(self, claim_type: str, element_index: int) -> str:
        normalized_claim = ''.join(ch.lower() if ch.isalnum() else '_' for ch in claim_type).strip('_')
        return f'{normalized_claim}:{element_index}'

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
        fact_metadata = fact.get('metadata', {}) if isinstance(fact.get('metadata'), dict) else {}
        parse_lineage = fact_metadata.get('parse_lineage', {}) if isinstance(fact_metadata.get('parse_lineage'), dict) else {}
        snapshot = graph_trace.get('snapshot', {}) if isinstance(graph_trace.get('snapshot'), dict) else {}
        source_ref = link.get('support_ref') or parse_lineage.get('source_ref') or ''

        return {
            'claim_type': link.get('claim_type'),
            'claim_element_id': link.get('claim_element_id'),
            'claim_element_text': link.get('claim_element_text'),
            'support_kind': link.get('support_kind'),
            'support_ref': link.get('support_ref'),
            'support_label': link.get('support_label'),
            'source_table': link.get('source_table'),
            'support_strength': link.get('support_strength', 0.0),
            'record_id': graph_trace.get('record_id') or link.get('evidence_record_id') or link.get('authority_record_id'),
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
        graph_status_counts: Dict[str, int] = {}
        unique_fact_ids = set()
        unique_graph_ids = set()
        unique_record_ids = set()
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
            parse_source = str(parse_lineage.get('source') or 'unknown')
            parse_source_counts[parse_source] = parse_source_counts.get(parse_source, 0) + 1

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

        return {
            'trace_count': len([trace for trace in traces if isinstance(trace, dict)]),
            'fact_trace_count': fact_trace_count,
            'link_only_trace_count': link_only_trace_count,
            'unique_fact_count': len(unique_fact_ids),
            'unique_graph_id_count': len(unique_graph_ids),
            'unique_record_count': len(unique_record_ids),
            'support_by_kind': support_by_kind,
            'support_by_source': support_by_source,
            'parse_source_counts': parse_source_counts,
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
        missing_support_kind_count = len(element.get('missing_support_kinds', []) or [])
        total_links = int(element.get('total_links', 0) or 0)
        coverage_status = str(element.get('status') or '')

        if heuristic_contradiction_count:
            decision_source = 'heuristic_contradictions'
            validation_status = 'contradicted'
        elif logic_contradiction_count:
            decision_source = 'logic_contradictions'
            validation_status = 'contradicted'
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
        if ontology_validation_signal == 'invalid':
            notes.append('Ontology validation returned an invalid or inconsistent result for this element.')
        elif ontology_validation_signal == 'valid':
            notes.append('Ontology validation reported a valid or consistent result for this element.')
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
    ) -> str:
        if validation_status == 'contradicted':
            return 'resolve_contradiction'
        if validation_status == 'missing':
            return 'collect_initial_support'
        if validation_status == 'incomplete':
            if not (element.get('missing_support_kinds', []) or []):
                return 'review_existing_support'
            return 'collect_missing_support_kind'
        return 'review_existing_support'

    def _build_reasoning_predicates(
        self,
        claim_type: str,
        element: Dict[str, Any],
        contradiction_candidates: List[Dict[str, Any]],
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

        for trace in element.get('support_traces', []) or []:
            if not isinstance(trace, dict):
                continue
            support_id = str(trace.get('fact_id') or trace.get('support_ref') or '')
            if not support_id:
                continue
            entities.append(
                {
                    'id': support_id,
                    'label': str(trace.get('fact_text') or trace.get('support_label') or support_id),
                    'type': str(trace.get('support_kind') or 'support'),
                }
            )
            relationships.append(
                {
                    'source': support_id,
                    'target': claim_entity_id,
                    'type': 'supports',
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
        predicates = self._build_reasoning_predicates(claim_type, element, contradiction_candidates)
        ontology_build = build_ontology(ontology_seed_text)
        fallback_ontology = self._build_reasoning_ontology_fallback(claim_type, element, contradiction_candidates)
        ontology_payload = ontology_build.get('ontology') if isinstance(ontology_build, dict) else None
        ontology_for_validation = ontology_payload if ontology_payload not in (None, '') else fallback_ontology
        logic_proof = prove_claim_elements(predicates)
        logic_contradictions = check_contradictions(predicates)
        ontology_validation = validate_ontology(ontology_for_validation)

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
            'ontology_validation': ontology_validation,
        }

    def _summarize_claim_reasoning_diagnostics(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        adapter_status_counts: Dict[str, Dict[str, int]] = {
            'ontology_build': {},
            'logic_proof': {},
            'logic_contradictions': {},
            'ontology_validation': {},
        }
        backend_available_count = 0
        predicate_count = 0
        ontology_entity_count = 0
        ontology_relationship_count = 0
        fallback_ontology_count = 0

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
        }

    def _summarize_claim_validation_decisions(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        decision_source_counts: Counter[str] = Counter()
        adapter_contradicted_element_count = 0
        fallback_ontology_element_count = 0
        proof_supported_element_count = 0
        logic_unprovable_element_count = 0
        ontology_invalid_element_count = 0

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

        return {
            'decision_source_counts': dict(sorted(decision_source_counts.items())),
            'adapter_contradicted_element_count': adapter_contradicted_element_count,
            'fallback_ontology_element_count': fallback_ontology_element_count,
            'proof_supported_element_count': proof_supported_element_count,
            'logic_unprovable_element_count': logic_unprovable_element_count,
            'ontology_invalid_element_count': ontology_invalid_element_count,
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
            recommended_action = self._recommended_validation_action(validation_status, element)
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
        claim_element_text: Optional[str] = None,
        support_label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[str]]:
        requirements = self.get_claim_requirements(user_id, claim_type).get(claim_type, [])
        if not requirements:
            return {'claim_element_id': None, 'claim_element_text': claim_element_text}

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
            return {'claim_element_id': None, 'claim_element_text': claim_element_text}

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

        return {'claim_element_id': None, 'claim_element_text': claim_element_text}

    def register_claim_requirements(
        self,
        user_id: str,
        requirements: Dict[str, List[str]],
        complaint_id: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not DUCKDB_AVAILABLE:
            return {}

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
                            json.dumps({}),
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
            return {}

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
            self.mediator.log('claim_support_unavailable')
            return {'record_id': -1, 'created': False, 'reused': False}

        resolved_element = self.resolve_claim_element(
            user_id,
            claim_type,
            claim_element_text=claim_element_text,
            support_label=support_label,
            metadata=metadata,
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
                    json.dumps(metadata or {}),
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
            return []

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
            }

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
        links = [self._enrich_support_link(link) for link in self.get_support_links(user_id, claim_type)]
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
                element_summaries.append(
                    {
                        **requirement,
                        'total_links': len(requirement_links),
                        'fact_count': element_fact_count,
                        'support_by_kind': element_support_by_kind,
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
        links = [self._enrich_support_link(link) for link in self.get_support_links(user_id, claim_type)]

        for link in links:
            if claim_element_id and link.get('claim_element_id') != claim_element_id:
                continue
            if claim_element_text and link.get('claim_element_text') != claim_element_text:
                continue

            for fact in link.get('facts', []) or []:
                facts.append(
                    {
                        **fact,
                        'claim_type': link.get('claim_type'),
                        'claim_element_id': link.get('claim_element_id'),
                        'claim_element_text': link.get('claim_element_text'),
                        'support_kind': link.get('support_kind'),
                        'support_ref': link.get('support_ref'),
                        'support_label': link.get('support_label'),
                        'source_table': link.get('source_table'),
                        'evidence_record_id': link.get('evidence_record_id'),
                        'authority_record_id': link.get('authority_record_id'),
                        'graph_summary': link.get('graph_summary', {}),
                        'graph_trace': link.get('graph_trace', {}),
                        'record_summary': link.get('record_summary', {}),
                    }
                )

        return facts

    def get_claim_support_traces(
        self,
        user_id: str,
        claim_type: Optional[str] = None,
        *,
        claim_element_id: Optional[str] = None,
        claim_element_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        links = [self._enrich_support_link(link) for link in self.get_support_links(user_id, claim_type)]
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
                'links': [],
            }

        return {
            'element_id': target_element_id,
            'element_text': target_element_text,
            'total_links': 0,
            'fact_count': 0,
            'support_by_kind': {},
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

        return overview

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

                elements.append(
                    {
                        'element_id': element.get('element_id'),
                        'element_text': element.get('element_text'),
                        'status': status,
                        'support_by_kind': element.get('support_by_kind', {}),
                        'total_links': element.get('total_links', 0),
                        'fact_count': element.get('fact_count', 0),
                        'missing_support_kinds': [
                            kind for kind in required_kinds
                            if element.get('support_by_kind', {}).get(kind, 0) == 0
                        ],
                        'links_by_kind': links_by_kind,
                        'support_traces': support_traces,
                        'support_trace_summary': support_trace_summary,
                        'links': element.get('links', []),
                    }
                )

            claim_support_traces = self._collect_support_traces_from_links(claim_summary.get('links', []))
            matrix['claims'][current_claim] = {
                'claim_type': current_claim,
                'required_support_kinds': required_kinds,
                'total_elements': claim_summary.get('total_elements', 0),
                'status_counts': status_counts,
                'total_links': support_link_total,
                'total_facts': fact_total,
                'support_by_kind': claim_summary.get('support_by_kind', {}),
                'support_trace_summary': self._summarize_support_traces(claim_support_traces),
                'elements': elements,
                'unassigned_links': claim_summary.get('unassigned_links', []),
            }

        return matrix

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

        return validation

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
                unresolved_elements.append(
                    {
                        'element_id': element.get('element_id'),
                        'element_text': element.get('element_text'),
                        'status': element.get('status'),
                        'missing_support_kinds': element.get('missing_support_kinds', []),
                        'total_links': element.get('total_links', 0),
                        'fact_count': element.get('fact_count', 0),
                        'support_by_kind': element.get('support_by_kind', {}),
                        'links': element.get('links', []),
                        'support_facts': support_facts,
                        'support_traces': support_traces,
                        'support_trace_summary': self._summarize_support_traces(support_traces),
                        'graph_trace_summary': self._summarize_graph_traces(element.get('links', [])),
                        'recommended_action': (
                            'collect_missing_support_kind'
                            if element.get('total_links', 0)
                            else 'collect_initial_support'
                        ),
                    }
                )

            gaps['claims'][current_claim] = {
                'claim_type': current_claim,
                'required_support_kinds': required_kinds,
                'unresolved_count': len(unresolved_elements),
                'unresolved_elements': unresolved_elements,
            }

        return gaps

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

        return contradictions

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
                **(metadata or {}),
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
                    json.dumps(metadata or {}),
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
            return {
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': max(0, int(limit or 0)),
                'claims': {},
            }

        normalized_limit = max(0, int(limit or 0))
        if normalized_limit == 0:
            return {
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': normalized_limit,
                'claims': {},
            }

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
            return {
                'user_id': user_id,
                'claim_type': claim_type,
                'limit': normalized_limit,
                'claims': {},
                'error': str(exc),
            }

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
            }
            current_claim = str(row[1] or '')
            claim_entries.setdefault(current_claim, []).append(entry)

        return {
            'user_id': user_id,
            'claim_type': claim_type,
            'limit': normalized_limit,
            'claims': claim_entries,
        }
