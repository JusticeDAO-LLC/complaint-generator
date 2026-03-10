"""Legal authority retrieval hooks for mediator."""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from integrations.ipfs_datasets.provenance import build_provenance
from integrations.ipfs_datasets.types import CaseAuthority
from integrations.ipfs_datasets.legal import (
    LEGAL_SCRAPERS_AVAILABLE,
    search_federal_register,
    search_recap_documents,
    search_us_code,
)
from integrations.ipfs_datasets.search import (
    COMMON_CRAWL_AVAILABLE as WEB_ARCHIVING_AVAILABLE,
    CommonCrawlSearchEngine,
)

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


class LegalAuthoritySearchHook:
    """
    Hook for searching relevant legal authorities.
    
    Uses web archiving tools and legal scrapers to locate statutes,
    regulations, case law, and other legal authorities relevant to the case.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        self._check_availability()
        self._init_web_archiving()
    
    def _check_availability(self):
        """Check availability of legal search tools."""
        if not LEGAL_SCRAPERS_AVAILABLE:
            self.mediator.log('legal_authority_warning',
                message='Legal scrapers not fully available - some features may be limited')
        if not WEB_ARCHIVING_AVAILABLE:
            self.mediator.log('legal_authority_warning',
                message='Web archiving not available - web search disabled')
    
    def _init_web_archiving(self):
        """Initialize web archiving engine if available."""
        if WEB_ARCHIVING_AVAILABLE:
            try:
                self.web_search = CommonCrawlSearchEngine(mode='local')
                self.mediator.log('legal_authority_init', 
                    message='Web archiving search engine initialized')
            except Exception as e:
                self.web_search = None
                self.mediator.log('legal_authority_warning',
                    message=f'Failed to initialize web archiving: {e}')
        else:
            self.web_search = None
    
    def search_us_code(self, query: str, title: Optional[str] = None,
                      max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search the US Code for relevant statutes.
        
        Args:
            query: Search query (e.g., "civil rights", "employment discrimination")
            title: Optional US Code title to narrow search
            max_results: Maximum number of results to return
            
        Returns:
            List of statute dictionaries with citation, text, and metadata
        """
        if not LEGAL_SCRAPERS_AVAILABLE or search_us_code is None:
            self.mediator.log('legal_authority_unavailable', 
                search_type='us_code', query=query)
            return []
        
        try:
            # Use LLM to generate search terms if needed
            search_terms = self._generate_search_terms(query)
            
            results = []
            for term in search_terms[:3]:  # Limit to top 3 terms
                try:
                    statute_results = search_us_code(term, max_results=max_results)
                    if statute_results:
                        results.extend(statute_results)
                except Exception as e:
                    self.mediator.log('legal_authority_search_error',
                        search_type='us_code', term=term, error=str(e))
            
            self.mediator.log('legal_authority_search',
                search_type='us_code', query=query, found=len(results))
            
            return results[:max_results]
            
        except Exception as e:
            self.mediator.log('legal_authority_search_error',
                search_type='us_code', error=str(e))
            return []
    
    def search_federal_register(self, query: str, 
                               start_date: Optional[str] = None,
                               end_date: Optional[str] = None,
                               max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search the Federal Register for regulations and notices.
        
        Args:
            query: Search query
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            max_results: Maximum number of results
            
        Returns:
            List of Federal Register documents
        """
        if not LEGAL_SCRAPERS_AVAILABLE or search_federal_register is None:
            self.mediator.log('legal_authority_unavailable',
                search_type='federal_register', query=query)
            return []
        
        try:
            results = search_federal_register(
                query=query,
                start_date=start_date,
                end_date=end_date,
                max_results=max_results
            )
            
            self.mediator.log('legal_authority_search',
                search_type='federal_register', query=query, found=len(results))
            
            return results
            
        except Exception as e:
            self.mediator.log('legal_authority_search_error',
                search_type='federal_register', error=str(e))
            return []
    
    def search_case_law(self, query: str, jurisdiction: Optional[str] = None,
                       max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search case law using RECAP archive.
        
        Args:
            query: Search query
            jurisdiction: Optional jurisdiction filter
            max_results: Maximum number of results
            
        Returns:
            List of case law documents
        """
        if not LEGAL_SCRAPERS_AVAILABLE or search_recap_documents is None:
            self.mediator.log('legal_authority_unavailable',
                search_type='case_law', query=query)
            return []
        
        try:
            results = search_recap_documents(
                query=query,
                court=jurisdiction,
                max_results=max_results
            )
            
            self.mediator.log('legal_authority_search',
                search_type='case_law', query=query, found=len(results))
            
            return results
            
        except Exception as e:
            self.mediator.log('legal_authority_search_error',
                search_type='case_law', error=str(e))
            return []
    
    def search_web_archives(self, domain: str, query: Optional[str] = None,
                           max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Search web archives for legal information.
        
        Args:
            domain: Domain to search (e.g., "law.cornell.edu")
            query: Optional search query
            max_results: Maximum number of results
            
        Returns:
            List of archived web pages with legal content
        """
        if not self.web_search:
            self.mediator.log('legal_authority_unavailable',
                search_type='web_archive', domain=domain)
            return []
        
        try:
            results = self.web_search.search_domain(
                domain=domain,
                max_matches=max_results
            )
            
            self.mediator.log('legal_authority_search',
                search_type='web_archive', domain=domain, found=len(results))
            
            return results
            
        except Exception as e:
            self.mediator.log('legal_authority_search_error',
                search_type='web_archive', error=str(e))
            return []
    
    def _generate_search_terms(self, query: str) -> List[str]:
        """Generate search terms from query using LLM."""
        try:
            prompt = f"""Given the legal query: "{query}"
            
Generate 3 specific search terms for finding relevant US Code statutes.
Return only the search terms, one per line."""
            
            response = self.mediator.query_backend(prompt)
            terms = [line.strip() for line in response.split('\n') if line.strip()]
            return terms[:3] or [query]
        except Exception:
            return [query]
    
    def search_all_sources(self, query: str, claim_type: Optional[str] = None,
                          jurisdiction: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search all available legal sources for authorities.
        
        Args:
            query: Search query
            claim_type: Optional claim type to focus search
            jurisdiction: Optional jurisdiction filter
            
        Returns:
            Dictionary with results from each source type
        """
        results = {
            'statutes': [],
            'regulations': [],
            'case_law': [],
            'web_archives': []
        }
        
        # Search US Code
        results['statutes'] = self.search_us_code(query, max_results=5)
        
        # Search Federal Register
        results['regulations'] = self.search_federal_register(query, max_results=5)
        
        # Search case law
        results['case_law'] = self.search_case_law(query, jurisdiction, max_results=5)
        
        # Search relevant legal web archives
        legal_domains = ['law.cornell.edu', 'law.justia.com', 'findlaw.com']
        for domain in legal_domains:
            try:
                web_results = self.search_web_archives(domain, max_results=3)
                results['web_archives'].extend(web_results)
            except Exception:
                pass
        
        total_found = sum(len(v) for v in results.values())
        self.mediator.log('legal_authority_search_all',
            query=query, total_found=total_found)
        
        return results


class LegalAuthorityStorageHook:
    """
    Hook for storing legal authorities in DuckDB.
    
    Manages a database of legal authorities found during research,
    indexed by case, claim type, and authority type.
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
        Tests often pass a NamedTemporaryFile() path which is an empty file.
        Delete empty files so DuckDB can initialize the database.
        """
        try:
            path = Path(self.db_path)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.is_file() and path.stat().st_size == 0:
                path.unlink()
        except Exception:
            pass
    
    def _get_default_db_path(self) -> str:
        """Get default DuckDB database path."""
        state_dir = Path(__file__).parent.parent / 'statefiles'
        if not state_dir.exists():
            state_dir = Path('.')
        return str(state_dir / 'legal_authorities.duckdb')
    
    def _check_duckdb_availability(self):
        """Check if DuckDB is available."""
        if not DUCKDB_AVAILABLE:
            self.mediator.log('legal_authority_warning',
                message='DuckDB not available - legal authorities will not be persisted')
    
    def _initialize_schema(self):
        """Initialize DuckDB schema for legal authorities."""
        try:
            conn = duckdb.connect(self.db_path)
            
            # Create sequence for auto-incrementing IDs
            conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS legal_authorities_id_seq START 1
            """)
            
            # Create legal_authorities table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authorities (
                    id BIGINT PRIMARY KEY DEFAULT nextval('legal_authorities_id_seq'),
                    user_id VARCHAR,
                    complaint_id VARCHAR,
                    claim_type VARCHAR,
                    authority_type VARCHAR NOT NULL,  -- statute, regulation, case_law, web_archive
                    source VARCHAR NOT NULL,          -- us_code, federal_register, recap, web
                    citation VARCHAR,                 -- Legal citation (e.g., "42 U.S.C. § 1983")
                    title TEXT,
                    content TEXT,
                    url VARCHAR,
                    metadata JSON,
                    relevance_score FLOAT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    search_query VARCHAR
                )
            """)

            for statement in [
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS jurisdiction VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS source_system VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS provenance JSON",
            ]:
                conn.execute(statement)
            
            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authorities_user
                ON legal_authorities(user_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authorities_claim
                ON legal_authorities(claim_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_authorities_citation
                ON legal_authorities(citation)
            """)
            
            conn.close()
            self.mediator.log('legal_authority_schema_initialized',
                db_path=self.db_path)
            
        except Exception as e:
            self.mediator.log('legal_authority_schema_error', error=str(e))
    
    def add_authority(self, authority_data: Dict[str, Any],
                     user_id: str, complaint_id: Optional[str] = None,
                     claim_type: Optional[str] = None,
                     search_query: Optional[str] = None) -> int:
        """
        Add a legal authority to the database.
        
        Args:
            authority_data: Authority information from search
            user_id: User identifier
            complaint_id: Optional complaint ID
            claim_type: Optional claim type
            search_query: Original search query
            
        Returns:
            Record ID of inserted authority
        """
        if not DUCKDB_AVAILABLE:
            self.mediator.log('legal_authority_storage_unavailable')
            return -1
        
        try:
            conn = duckdb.connect(self.db_path)
            provenance = build_provenance(
                source_url=str(authority_data.get('url', '')),
                acquisition_method='legal_search',
                source_type=str(authority_data.get('type', 'unknown')),
                acquired_at=datetime.now().isoformat(),
                source_system=str(authority_data.get('source', 'unknown')),
                jurisdiction=str(authority_data.get('jurisdiction', '')),
            )
            authority = CaseAuthority(
                authority_type=authority_data.get('type', 'unknown'),
                source=authority_data.get('source', 'unknown'),
                citation=authority_data.get('citation') or '',
                title=authority_data.get('title') or '',
                content=authority_data.get('content') or authority_data.get('text') or '',
                url=authority_data.get('url') or '',
                relevance_score=authority_data.get('relevance_score', 0.5),
                metadata=authority_data.get('metadata', {}) if isinstance(authority_data.get('metadata', {}), dict) else {},
                provenance=provenance,
            )
            normalized_authority = authority.as_dict()
            
            result = conn.execute("""
                INSERT INTO legal_authorities (
                    user_id, complaint_id, claim_type, authority_type,
                    source, citation, title, content, url, metadata,
                    relevance_score, search_query, jurisdiction,
                    source_system, provenance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, [
                user_id,
                complaint_id,
                claim_type,
                normalized_authority.get('type', 'unknown'),
                normalized_authority.get('source', 'unknown'),
                normalized_authority.get('citation'),
                normalized_authority.get('title'),
                normalized_authority.get('content'),
                normalized_authority.get('url'),
                json.dumps(normalized_authority.get('metadata', {})),
                normalized_authority.get('relevance_score', 0.5),
                search_query,
                provenance.jurisdiction,
                provenance.source_system,
                json.dumps(provenance.as_dict()),
            ]).fetchone()
            
            record_id = result[0]
            conn.close()
            
            self.mediator.log('legal_authority_added',
                record_id=record_id, citation=authority_data.get('citation'))
            
            return record_id
            
        except Exception as e:
            self.mediator.log('legal_authority_storage_error', error=str(e))
            raise Exception(f'Failed to store legal authority: {str(e)}')
    
    def add_authorities_bulk(self, authorities: List[Dict[str, Any]],
                            user_id: str, complaint_id: Optional[str] = None,
                            claim_type: Optional[str] = None,
                            search_query: Optional[str] = None) -> List[int]:
        """
        Add multiple legal authorities at once.
        
        Args:
            authorities: List of authority dictionaries
            user_id: User identifier
            complaint_id: Optional complaint ID
            claim_type: Optional claim type
            search_query: Original search query
            
        Returns:
            List of record IDs
        """
        record_ids = []
        for authority in authorities:
            try:
                record_id = self.add_authority(
                    authority, user_id, complaint_id, claim_type, search_query
                )
                record_ids.append(record_id)
            except Exception as e:
                self.mediator.log('legal_authority_bulk_error',
                    error=str(e), authority=authority.get('citation'))
        
        return record_ids
    
    def get_authorities_by_claim(self, user_id: str, claim_type: str) -> List[Dict[str, Any]]:
        """
        Get all authorities for a specific claim type.
        
        Args:
            user_id: User identifier
            claim_type: Claim type
            
        Returns:
            List of authority records
        """
        if not DUCKDB_AVAILABLE:
            return []
        
        try:
            conn = duckdb.connect(self.db_path)
            
            results = conn.execute("""
                SELECT id, authority_type, source, citation, title,
                      content, url, metadata, relevance_score, timestamp,
                      jurisdiction, source_system, provenance
                FROM legal_authorities
                WHERE user_id = ? AND claim_type = ?
                ORDER BY relevance_score DESC, timestamp DESC
            """, [user_id, claim_type]).fetchall()
            
            conn.close()
            
            authorities = []
            for row in results:
                authorities.append({
                    'id': row[0],
                    'type': row[1],
                    'source': row[2],
                    'citation': row[3],
                    'title': row[4],
                    'content': row[5],
                    'url': row[6],
                    'metadata': json.loads(row[7]) if row[7] else {},
                    'relevance_score': row[8],
                    'timestamp': row[9],
                    'jurisdiction': row[10],
                    'source_system': row[11],
                    'provenance': json.loads(row[12]) if row[12] else {},
                })
            
            return authorities
            
        except Exception as e:
            self.mediator.log('legal_authority_query_error', error=str(e))
            return []
    
    def get_all_authorities(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all authorities for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of all authority records
        """
        if not DUCKDB_AVAILABLE:
            return []
        
        try:
            conn = duckdb.connect(self.db_path)
            
            results = conn.execute("""
                SELECT id, claim_type, authority_type, source, citation,
                      title, content, url, metadata, relevance_score, timestamp,
                      jurisdiction, source_system, provenance
                FROM legal_authorities
                WHERE user_id = ?
                ORDER BY timestamp DESC
            """, [user_id]).fetchall()
            
            conn.close()
            
            authorities = []
            for row in results:
                authorities.append({
                    'id': row[0],
                    'claim_type': row[1],
                    'type': row[2],
                    'source': row[3],
                    'citation': row[4],
                    'title': row[5],
                    'content': row[6],
                    'url': row[7],
                    'metadata': json.loads(row[8]) if row[8] else {},
                    'relevance_score': row[9],
                    'timestamp': row[10],
                    'jurisdiction': row[11],
                    'source_system': row[12],
                    'provenance': json.loads(row[13]) if row[13] else {},
                })
            
            return authorities
            
        except Exception as e:
            self.mediator.log('legal_authority_query_error', error=str(e))
            return []
    
    def get_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about stored legal authorities.
        
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
                        COUNT(DISTINCT authority_type) as type_count,
                        COUNT(DISTINCT claim_type) as claim_count
                    FROM legal_authorities
                    WHERE user_id = ?
                """, [user_id]).fetchone()
            else:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as total_count,
                        COUNT(DISTINCT authority_type) as type_count,
                        COUNT(DISTINCT user_id) as user_count
                    FROM legal_authorities
                """).fetchone()
            
            conn.close()
            
            stats = {
                'available': True,
                'total_count': result[0],
                'type_count': result[1]
            }
            
            if user_id:
                stats['claim_count'] = result[2]
            else:
                stats['user_count'] = result[2]
            
            return stats
            
        except Exception as e:
            self.mediator.log('legal_authority_stats_error', error=str(e))
            return {'available': False, 'error': str(e)}


class LegalAuthorityAnalysisHook:
    """
    Hook for analyzing stored legal authorities.
    
    Provides methods to analyze, rank, and generate insights from
    stored legal authorities.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
    
    def analyze_authorities_for_claim(self, user_id: str, claim_type: str) -> Dict[str, Any]:
        """
        Analyze legal authorities for a specific claim.
        
        Args:
            user_id: User identifier
            claim_type: Claim type to analyze
            
        Returns:
            Analysis with authority summary and recommendations
        """
        if not hasattr(self.mediator, 'legal_authority_storage'):
            return {'error': 'Legal authority storage not available'}
        
        try:
            authorities = self.mediator.legal_authority_storage.get_authorities_by_claim(
                user_id, claim_type
            )
            
            if not authorities:
                return {
                    'claim_type': claim_type,
                    'total_authorities': 0,
                    'recommendation': f'No legal authorities found for {claim_type}. Run a search to find relevant laws and regulations.'
                }
            
            # Group by type
            by_type = {}
            for auth in authorities:
                auth_type = auth['type']
                by_type[auth_type] = by_type.get(auth_type, 0) + 1
            
            # Generate analysis using LLM
            analysis = {
                'claim_type': claim_type,
                'total_authorities': len(authorities),
                'by_type': by_type,
                'authorities': authorities[:10],  # Top 10
                'recommendation': self._generate_authority_recommendations(
                    claim_type, authorities
                )
            }
            
            return analysis
            
        except Exception as e:
            self.mediator.log('legal_authority_analysis_error', error=str(e))
            return {'error': str(e)}
    
    def _generate_authority_recommendations(self, claim_type: str,
                                           authorities: List[Dict[str, Any]]) -> str:
        """Generate recommendations using LLM."""
        authority_summary = '\n'.join([
            f"- {a['type']}: {a.get('citation', 'N/A')} - {a.get('title', 'No title')}"
            for a in authorities[:5]
        ])
        
        prompt = f"""Based on these legal authorities for a {claim_type} claim:

{authority_summary}

Provide brief analysis of:
1. Strength of legal foundation
2. Key authorities to cite
3. Any gaps in legal research
"""
        
        try:
            response = self.mediator.query_backend(prompt)
            return response
        except Exception:
            return f'Found {len(authorities)} legal authorities. Review citations for strongest support.'
