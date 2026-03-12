"""Evidence management hooks for mediator."""

import os
import json
import hashlib
import mimetypes
from typing import Dict, List, Optional, Any, BinaryIO
from datetime import datetime, timedelta, UTC
from pathlib import Path

from integrations.ipfs_datasets.provenance import (
    build_storage_parse_metadata,
    build_provenance,
    merge_metadata_with_provenance,
    stable_content_hash,
)
from integrations.ipfs_datasets.documents import parse_document_bytes, summarize_document_parse
from integrations.ipfs_datasets.graphs import extract_graph_from_text, persist_graph_snapshot
from integrations.ipfs_datasets.types import CaseArtifact, CaseFact
from integrations.ipfs_datasets.storage import (
    IPFS_AVAILABLE,
    add_bytes,
    cat,
    get_ipfs_backend,
    pin,
)

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


class EvidenceStorageHook:
    """
    Hook for storing evidence in IPFS.
    
    Stores evidence files/data in IPFS and returns the CID (Content ID)
    for later retrieval and reference.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        self._check_ipfs_availability()
    
    def _check_ipfs_availability(self):
        """Check if IPFS backend is available."""
        if not IPFS_AVAILABLE:
            self.mediator.log('evidence_warning', 
                message='IPFS not available - evidence storage will be simulated')

    def _should_parse_evidence(self, evidence_type: str, metadata: Optional[Dict[str, Any]]) -> bool:
        parse_flag = (metadata or {}).get('parse_document')
        if parse_flag is not None:
            return bool(parse_flag)
        normalized_type = (evidence_type or '').lower()
        if normalized_type in {'document', 'text', 'email', 'pdf'}:
            return True
        mime_type = str((metadata or {}).get('mime_type', '')).lower()
        return mime_type.startswith('text/') or mime_type == 'application/pdf'
    
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
            normalized_metadata = merge_metadata_with_provenance(metadata, provenance)
            if IPFS_AVAILABLE:
                try:
                    # Store in IPFS
                    cid = add_bytes(data, pin=True)
                    self.mediator.log('evidence_stored', 
                        cid=cid, size=len(data), type=evidence_type)
                except Exception as ipfs_error:
                    cid = f"Qm{hashlib.sha256(data).hexdigest()[:44]}"
                    self.mediator.log(
                        'evidence_ipfs_runtime_unavailable',
                        error=str(ipfs_error),
                        cid=cid,
                        size=len(data),
                        type=evidence_type,
                    )
            else:
                # Fallback: Create a simulated CID using hash
                cid = f"Qm{hashlib.sha256(data).hexdigest()[:44]}"
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
                document_parse = parse_document_bytes(
                    data,
                    filename=str((metadata or {}).get('filename', '')),
                    mime_type=str((metadata or {}).get('mime_type', '')),
                    source=str((metadata or {}).get('parse_source', 'bytes')),
                )
                result['document_parse'] = document_parse
                result['metadata']['document_parse_summary'] = summarize_document_parse(document_parse)
                graph_payload = extract_graph_from_text(
                    document_parse.get('text', ''),
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
            return result
            
        except Exception as e:
            self.mediator.log('evidence_storage_error', error=str(e))
            raise Exception(f'Failed to store evidence: {str(e)}')
    
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
            
        except Exception as e:
            self.mediator.log('evidence_file_error', error=str(e), file=file_path)
            raise Exception(f'Failed to store evidence file: {str(e)}')
    
    def retrieve_evidence(self, cid: str) -> bytes:
        """
        Retrieve evidence data from IPFS by CID.
        
        Args:
            cid: Content ID of the evidence
            
        Returns:
            Evidence data as bytes
        """
        try:
            if IPFS_AVAILABLE:
                data = cat(cid)
                self.mediator.log('evidence_retrieved', cid=cid, size=len(data))
                return data
            else:
                self.mediator.log('evidence_retrieval_unavailable', cid=cid)
                raise Exception('IPFS not available for evidence retrieval')
                
        except Exception as e:
            self.mediator.log('evidence_retrieval_error', error=str(e), cid=cid)
            raise Exception(f'Failed to retrieve evidence: {str(e)}')


class EvidenceStateHook:
    """
    Hook for managing evidence state in DuckDB.
    
    Stores metadata about evidence submissions including user associations,
    timestamps, and references to IPFS CIDs.
    """
    
    def __init__(self, mediator, db_path: Optional[str] = None):
        self.mediator = mediator
        self.db_path = db_path or self._get_default_db_path()
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
        except Exception:
            # Best-effort only; duckdb.connect will raise a useful error if needed.
            pass
    
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
            self.mediator.log('evidence_schema_error', error=str(e))

    def _store_document_chunks(self, conn, evidence_id: int, document_parse: Dict[str, Any]) -> None:
        chunks = document_parse.get('chunks', []) or []
        if not chunks:
            return
        for chunk in chunks:
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
                    chunk.get('text'),
                    json.dumps({}),
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
                    entity.get('name'),
                    entity.get('confidence', 0.0),
                    json.dumps(entity.get('attributes', {})),
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
                    json.dumps(relationship.get('attributes', {})),
                ],
            )

    def _store_document_facts(self, conn, evidence_id: int, evidence_info: Dict[str, Any], document_graph: Dict[str, Any]) -> None:
        entities = document_graph.get('entities', []) or []
        artifact_id = evidence_info.get('artifact_id') or evidence_info.get('cid') or ''
        provenance_payload = evidence_info.get('metadata', {}).get('provenance', {})

        for entity in entities:
            if entity.get('type') != 'fact':
                continue
            attributes = entity.get('attributes', {}) if isinstance(entity.get('attributes'), dict) else {}
            fact = CaseFact(
                fact_id=str(entity.get('id') or ''),
                text=str(attributes.get('text') or entity.get('name') or ''),
                source_artifact_id=artifact_id,
                confidence=float(entity.get('confidence', 0.0) or 0.0),
                metadata=attributes,
                provenance=build_provenance(
                    source_url=str(provenance_payload.get('source_url', '')),
                    acquisition_method=str(provenance_payload.get('acquisition_method', '')),
                    source_type=str(provenance_payload.get('source_type', '')),
                    acquired_at=str(provenance_payload.get('acquired_at', '')),
                    content_hash=str(provenance_payload.get('content_hash', '')),
                    source_system=str(provenance_payload.get('source_system', '')),
                    jurisdiction=str(provenance_payload.get('jurisdiction', '')),
                ),
            )
            conn.execute(
                """
                INSERT INTO evidence_facts (
                    evidence_id, fact_id, fact_text, source_artifact_id, confidence, metadata, provenance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    evidence_id,
                    fact.fact_id,
                    fact.text,
                    fact.source_artifact_id,
                    fact.confidence,
                    json.dumps(fact.metadata),
                    json.dumps(fact.provenance.as_dict()),
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
            self.mediator.log('evidence_state_unavailable')
            return {'record_id': -1, 'created': False, 'reused': False}
        
        try:
            conn = duckdb.connect(self.db_path)
            document_parse = evidence_info.get('document_parse') if isinstance(evidence_info.get('document_parse'), dict) else {}
            document_graph = evidence_info.get('document_graph') if isinstance(evidence_info.get('document_graph'), dict) else {}
            document_graph_summary = evidence_info.get('metadata', {}).get('document_graph_summary', {})
            parse_metadata = build_storage_parse_metadata(
                document_parse,
                default_source=str(
                    document_parse.get('metadata', {}).get('source')
                    or evidence_info.get('metadata', {}).get('parse_source')
                    or ''
                ),
            )
            parsed_text = document_parse.get('text', '')
            parsed_text_preview = parsed_text[:5000] if parsed_text else ''
            if not document_graph and parsed_text:
                document_graph = extract_graph_from_text(
                    parsed_text,
                    source_id=evidence_info.get('artifact_id') or evidence_info.get('cid'),
                    metadata={
                        'artifact_id': evidence_info.get('artifact_id', ''),
                        'source_url': evidence_info.get('metadata', {}).get('provenance', {}).get('source_url', ''),
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
            graph_snapshot = persist_graph_snapshot(
                document_graph,
                graph_changed=bool(document_graph.get('entities') or document_graph.get('relationships')),
                existing_graph=False,
                persistence_metadata={
                    'record_scope': 'evidence',
                    'record_key': evidence_info.get('cid', ''),
                },
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
                json.dumps(evidence_info.get('metadata', {})),
                complaint_id,
                claim_type,
                description,
                evidence_info.get('metadata', {}).get('provenance', {}).get('content_hash'),
                evidence_info.get('metadata', {}).get('provenance', {}).get('source_url'),
                evidence_info.get('metadata', {}).get('provenance', {}).get('acquisition_method'),
                json.dumps(evidence_info.get('metadata', {}).get('provenance', {})),
                claim_element_id,
                claim_element,
                document_parse.get('status') or parse_metadata.get('status'),
                len(document_parse.get('chunks', []) or []),
                parsed_text_preview,
                json.dumps(parse_metadata),
                document_graph.get('status') or document_graph_summary.get('status'),
                len(document_graph.get('entities', []) or []),
                len(document_graph.get('relationships', []) or []),
                json.dumps(graph_metadata),
            ]).fetchone()
            
            record_id = result[0]
            self._store_document_chunks(conn, record_id, document_parse)
            self._store_document_graph(conn, record_id, document_graph)
            self._store_document_facts(conn, record_id, evidence_info, document_graph)
            conn.close()
            
            self.mediator.log('evidence_record_added', 
                record_id=record_id, cid=evidence_info['cid'])
            
            return {'record_id': record_id, 'created': True, 'reused': False}
            
        except Exception as e:
            self.mediator.log('evidence_record_error', error=str(e))
            raise Exception(f'Failed to add evidence record: {str(e)}')
    
    def get_user_evidence(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all evidence for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of evidence records
        """
        if not DUCKDB_AVAILABLE:
            return []
        
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
            return []
    
    def get_evidence_by_cid(self, cid: str) -> Optional[Dict[str, Any]]:
        """
        Get evidence record by CID.
        
        Args:
            cid: Content ID
            
        Returns:
            Evidence record or None if not found
        """
        if not DUCKDB_AVAILABLE:
            return None
        
        try:
            conn = duckdb.connect(self.db_path)
            
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
            self.mediator.log('evidence_query_error', error=str(e), cid=cid)
            return None

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
            return []

    def get_evidence_graph(self, evidence_id: int) -> Dict[str, Any]:
        """Get normalized graph entities and relationships for a stored evidence record."""
        if not DUCKDB_AVAILABLE:
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
            return []

        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                """
                SELECT fact_id, fact_text, source_artifact_id, confidence, metadata, provenance
                FROM evidence_facts
                WHERE evidence_id = ?
                ORDER BY fact_id ASC
                """,
                [evidence_id],
            ).fetchall()
            conn.close()
            return [
                {
                    'fact_id': row[0],
                    'text': row[1],
                    'source_artifact_id': row[2],
                    'confidence': row[3] or 0.0,
                    'metadata': json.loads(row[4]) if row[4] else {},
                    'provenance': json.loads(row[5]) if row[5] else {},
                }
                for row in rows
            ]
        except Exception as e:
            self.mediator.log('evidence_fact_query_error', error=str(e), evidence_id=evidence_id)
            return []
    
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
                    json.dumps({'tactic_history': run_result.get('tactic_history', {})}),
                ],
            ).fetchone()
            run_id = int(row[0])

            for iteration in iterations:
                iteration_index = int(iteration.get('iteration', 0) or 0)
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
                        json.dumps(iteration.get('coverage', {})),
                        json.dumps(iteration.get('quality', {})),
                        json.dumps(iteration.get('critique', {})),
                    ],
                )

                for tactic in iteration.get('tactics', []) or []:
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
                            json.dumps(tactic.get('quality', {})),
                        ],
                    )

            for url, coverage in coverage_ledger.items():
                coverage_metadata = coverage if isinstance(coverage, dict) else {}
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
            return []

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
                    json.dumps(metadata or {}),
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
            return []

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
                             metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Mark a claimed scraper job as completed or failed."""
        if not DUCKDB_AVAILABLE:
            return {'updated': False, 'job_id': job_id}

        try:
            conn = duckdb.connect(self.db_path)
            current = conn.execute(
                """
                SELECT metadata
                FROM scraper_queue
                WHERE id = ?
                LIMIT 1
                """,
                [int(job_id)],
            ).fetchone()
            merged_metadata = json.loads(current[0]) if current and current[0] else {}
            if metadata:
                merged_metadata.update(metadata)

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
                WHERE id = ?
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
        except Exception:
            return 'Evidence analysis available. Review submitted evidence and consider any gaps in documentation.'
