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
                # Store in IPFS
                cid = add_bytes(data, pin=True)
                self.mediator.log('evidence_stored', 
                    cid=cid, size=len(data), type=evidence_type)
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
                metadata=normalized_metadata,
                provenance=provenance,
            )
            result = artifact.as_dict()
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
            ]:
                conn.execute(statement)
            
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
    
    def add_evidence_record(self, user_id: str, evidence_info: Dict[str, Any],
                          complaint_id: Optional[str] = None,
                          claim_type: Optional[str] = None,
                          description: Optional[str] = None) -> int:
        """
        Add evidence record to DuckDB.
        
        Args:
            user_id: User identifier
            evidence_info: Evidence information (from EvidenceStorageHook)
            complaint_id: Optional complaint ID this evidence relates to
            claim_type: Optional claim type this evidence supports
            description: Optional description of the evidence
            
        Returns:
            Record ID of the inserted evidence
        """
        if not DUCKDB_AVAILABLE:
            self.mediator.log('evidence_state_unavailable')
            return -1
        
        try:
            conn = duckdb.connect(self.db_path)
            
            # Get username from mediator state if available
            state = getattr(self.mediator, 'state', None)
            username = getattr(state, 'username', None) if state is not None else None
            if not isinstance(username, str) or not username:
                username = user_id
            
            result = conn.execute("""
                INSERT INTO evidence (
                    user_id, username, evidence_cid, evidence_type, 
                    evidence_size, metadata, complaint_id, claim_type, description,
                    content_hash, source_url, acquisition_method, provenance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ]).fetchone()
            
            record_id = result[0]
            conn.close()
            
            self.mediator.log('evidence_record_added', 
                record_id=record_id, cid=evidence_info['cid'])
            
            return record_id
            
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
                      acquisition_method, provenance
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
                      acquisition_method, provenance
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
                }
            
            return None
            
        except Exception as e:
            self.mediator.log('evidence_query_error', error=str(e), cid=cid)
            return None
    
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
