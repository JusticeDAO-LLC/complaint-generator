"""Evidence management hooks for mediator."""

import os
import json
import hashlib
from typing import Dict, List, Optional, Any, BinaryIO
from datetime import datetime
from pathlib import Path

from integrations.ipfs_datasets.provenance import (
    build_provenance,
    merge_metadata_with_provenance,
    stable_content_hash,
)
from integrations.ipfs_datasets.documents import parse_document_bytes
from integrations.ipfs_datasets.graphs import extract_graph_from_text
from integrations.ipfs_datasets.types import CaseArtifact
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
                )
                result['document_parse'] = document_parse
                result['metadata']['document_parse_summary'] = {
                    'status': document_parse.get('status'),
                    'chunk_count': len(document_parse.get('chunks', []) or []),
                    'text_length': len(document_parse.get('text', '') or ''),
                }
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
            file_metadata.update({
                'filename': os.path.basename(file_path),
                'original_path': file_path
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
            document_parse_summary = evidence_info.get('metadata', {}).get('document_parse_summary', {})
            document_graph = evidence_info.get('document_graph') if isinstance(evidence_info.get('document_graph'), dict) else {}
            document_graph_summary = evidence_info.get('metadata', {}).get('document_graph_summary', {})
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
                document_parse.get('status') or document_parse_summary.get('status'),
                len(document_parse.get('chunks', []) or []),
                parsed_text_preview,
                json.dumps(document_parse.get('metadata', {})),
                document_graph.get('status') or document_graph_summary.get('status'),
                len(document_graph.get('entities', []) or []),
                len(document_graph.get('relationships', []) or []),
                json.dumps(document_graph.get('metadata', {})),
            ]).fetchone()
            
            record_id = result[0]
            self._store_document_chunks(conn, record_id, document_parse)
            self._store_document_graph(conn, record_id, document_graph)
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
                    graph_status, graph_entity_count, graph_relationship_count, graph_metadata
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
                    graph_status, graph_entity_count, graph_relationship_count, graph_metadata
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
                        COUNT(DISTINCT evidence_type) as type_count
                    FROM evidence
                    WHERE user_id = ?
                """, [user_id]).fetchone()
            else:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as total_count,
                        SUM(evidence_size) as total_size,
                        COUNT(DISTINCT evidence_type) as type_count,
                        COUNT(DISTINCT user_id) as user_count
                    FROM evidence
                """).fetchone()
            
            conn.close()
            
            stats = {
                'available': True,
                'total_count': result[0],
                'total_size': result[1] or 0,
                'type_count': result[2]
            }
            
            if not user_id:
                stats['user_count'] = result[3]
            
            return stats
            
        except Exception as e:
            self.mediator.log('evidence_stats_error', error=str(e))
            return {'available': False, 'error': str(e)}


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
