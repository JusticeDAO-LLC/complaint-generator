"""Persistent claim-support coverage hooks for mediator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

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
                CREATE TABLE IF NOT EXISTS claim_support (
                    id BIGINT PRIMARY KEY DEFAULT nextval('claim_support_id_seq'),
                    user_id VARCHAR,
                    complaint_id VARCHAR,
                    claim_type VARCHAR NOT NULL,
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
                CREATE INDEX IF NOT EXISTS idx_claim_support_user_claim
                ON claim_support(user_id, claim_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_claim_support_ref
                ON claim_support(support_ref)
            """)
            conn.close()
            self.mediator.log('claim_support_schema_initialized', db_path=self.db_path)
        except Exception as exc:
            self.mediator.log('claim_support_schema_error', error=str(exc))

    def add_support_link(
        self,
        *,
        user_id: str,
        claim_type: str,
        support_kind: str,
        support_ref: str,
        support_label: Optional[str] = None,
        source_table: Optional[str] = None,
        support_strength: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        complaint_id: Optional[str] = None,
    ) -> int:
        if not DUCKDB_AVAILABLE:
            self.mediator.log('claim_support_unavailable')
            return -1

        try:
            conn = duckdb.connect(self.db_path)
            result = conn.execute(
                """
                INSERT INTO claim_support (
                    user_id, complaint_id, claim_type, support_kind,
                    support_ref, support_label, source_table, support_strength, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                [
                    user_id,
                    complaint_id,
                    claim_type,
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
                support_kind=support_kind,
                support_ref=support_ref,
            )
            return record_id
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
                    SELECT id, complaint_id, claim_type, support_kind, support_ref,
                           support_label, source_table, support_strength, metadata, timestamp
                    FROM claim_support
                    WHERE user_id = ? AND claim_type = ?
                    ORDER BY timestamp DESC
                    """,
                    [user_id, claim_type],
                ).fetchall()
            else:
                results = conn.execute(
                    """
                    SELECT id, complaint_id, claim_type, support_kind, support_ref,
                           support_label, source_table, support_strength, metadata, timestamp
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
                    'support_kind': row[3],
                    'support_ref': row[4],
                    'support_label': row[5],
                    'source_table': row[6],
                    'support_strength': row[7],
                    'metadata': json.loads(row[8]) if row[8] else {},
                    'timestamp': row[9],
                }
                for row in results
            ]
        except Exception as exc:
            self.mediator.log('claim_support_query_error', error=str(exc))
            return []

    def summarize_claim_support(self, user_id: str, claim_type: Optional[str] = None) -> Dict[str, Any]:
        links = self.get_support_links(user_id, claim_type)
        if claim_type:
            grouped = {claim_type: links}
        else:
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for link in links:
                grouped.setdefault(link['claim_type'], []).append(link)

        summary: Dict[str, Any] = {
            'available': DUCKDB_AVAILABLE,
            'total_links': len(links),
            'claims': {},
        }
        for current_claim, claim_links in grouped.items():
            support_by_kind: Dict[str, int] = {}
            for link in claim_links:
                support_by_kind[link['support_kind']] = support_by_kind.get(link['support_kind'], 0) + 1
            summary['claims'][current_claim] = {
                'total_links': len(claim_links),
                'support_by_kind': support_by_kind,
                'links': claim_links,
            }
        return summary
