"""
Legal Authority Retrieval Hooks for Mediator

This module provides hooks for:
1. Searching for relevant legal authorities using web archiving and legal scrapers
2. Storing legal authorities in DuckDB
3. Retrieving and analyzing stored legal authorities
"""

import sys
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from .integrations import (
    IPFSDatasetsAdapter,
    IntegrationFeatureFlags,
    RetrievalOrchestrator,
    VectorRetrievalAugmentor,
    GraphAwareRetrievalReranker,
)

# Add ipfs_datasets_py to path if available
ipfs_datasets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ipfs_datasets_py')
if os.path.exists(ipfs_datasets_path) and ipfs_datasets_path not in sys.path:
    sys.path.insert(0, ipfs_datasets_path)

try:
    from ipfs_datasets_py.legal_scrapers import (
        search_us_code,
        search_federal_register,
        search_recap_documents
    )
    LEGAL_SCRAPERS_AVAILABLE = True
except ImportError:
    LEGAL_SCRAPERS_AVAILABLE = False
    search_us_code = None
    search_federal_register = None
    search_recap_documents = None

try:
    from ipfs_datasets_py.web_archiving import CommonCrawlSearchEngine
    WEB_ARCHIVING_AVAILABLE = True
except ImportError:
    WEB_ARCHIVING_AVAILABLE = False
    CommonCrawlSearchEngine = None

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
        self.integration_flags = IntegrationFeatureFlags.from_env()
        self.integration_adapter = IPFSDatasetsAdapter(feature_flags=self.integration_flags)
        self.retrieval_orchestrator = RetrievalOrchestrator()
        self.vector_augmentor = VectorRetrievalAugmentor()
        self.graph_reranker = GraphAwareRetrievalReranker()
        self._check_availability()
        self._init_web_archiving()

    def get_capability_registry(self) -> Dict[str, Dict[str, object]]:
        """Get capability and feature-flag status for enhanced integrations."""
        return self.integration_adapter.capability_registry()

    def _normalize_records(
        self,
        records: List[Dict[str, Any]],
        query: str,
        source_type: str,
        source_name: str,
    ) -> List[Dict[str, Any]]:
        normalized = []
        for record in records:
            if not isinstance(record, dict):
                continue
            normalized_record = self.integration_adapter.normalize_record(
                query=query,
                source_type=source_type,
                source_name=source_name,
                record=record,
            )
            normalized.append({
                'source_type': normalized_record.source_type,
                'source_name': normalized_record.source_name,
                'query': normalized_record.query,
                'retrieved_at': normalized_record.retrieved_at,
                'title': normalized_record.title,
                'url': normalized_record.url,
                'citation': normalized_record.citation,
                'snippet': normalized_record.snippet,
                'content': normalized_record.content,
                'score': normalized_record.score,
                'confidence': normalized_record.confidence,
                'metadata': normalized_record.metadata,
            })
        return normalized

    def _merge_rank_normalized(
        self,
        normalized_records: List[Dict[str, Any]],
        max_results: int,
        query_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        model_records = []
        for item in normalized_records:
            model_records.append(self.integration_adapter.normalize_record(
                query=str(item.get('query', '')),
                source_type=str(item.get('source_type', 'unknown')),
                source_name=str(item.get('source_name', 'unknown')),
                record=item,
            ))

        ranked = self.retrieval_orchestrator.merge_and_rank(
            model_records,
            max_results=max_results,
            query_context=query_context,
        )
        return [
            {
                'source_type': r.source_type,
                'source_name': r.source_name,
                'query': r.query,
                'retrieved_at': r.retrieved_at,
                'title': r.title,
                'url': r.url,
                'citation': r.citation,
                'snippet': r.snippet,
                'content': r.content,
                'score': r.score,
                'confidence': r.confidence,
                'metadata': r.metadata,
            }
            for r in ranked
        ]

    def _build_support_bundle(self, normalized_records: List[Dict[str, Any]], max_items: int = 5) -> Dict[str, Any]:
        model_records = []
        for item in normalized_records:
            model_records.append(self.integration_adapter.normalize_record(
                query=str(item.get('query', '')),
                source_type=str(item.get('source_type', 'unknown')),
                source_name=str(item.get('source_name', 'unknown')),
                record=item,
            ))
        return self.retrieval_orchestrator.build_support_bundle(model_records, max_items_per_bucket=max_items)

    def _build_query_context(
        self,
        query: str,
        claim_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.retrieval_orchestrator.build_query_context(
            query=query,
            claim_type=claim_type,
            complaint_type=claim_type,
            jurisdiction=jurisdiction,
            max_queries=4,
        )

    def _build_evidence_context(
        self,
        query: str,
        claim_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
    ) -> List[str]:
        context: List[str] = []

        def _add(value: Any):
            text = str(value or '').strip()
            if text and text not in context:
                context.append(text)

        _add(query)
        _add(claim_type)
        _add(jurisdiction)

        state = getattr(self.mediator, 'state', None)
        if state is None:
            return context[:8]

        for attr in ('complaint_summary', 'original_complaint', 'complaint', 'last_message'):
            _add(getattr(state, attr, None))

        state_data = getattr(state, 'data', {}) or {}
        if isinstance(state_data, dict):
            context_values = []
            extractor = getattr(state, 'extract_chat_history_context_strings', None)
            if callable(extractor):
                extracted = extractor(limit=3)
                if isinstance(extracted, (list, tuple)):
                    context_values = list(extracted)
            if not context_values:
                chat_history = state_data.get('chat_history', {})
                if isinstance(chat_history, dict):
                    for _, value in list(chat_history.items())[-3:]:
                        if isinstance(value, dict):
                            for candidate in (value.get('message'), value.get('question')):
                                text = str(candidate or '').strip()
                                if text and text not in context_values:
                                    context_values.append(text)
                        else:
                            context_values.append(value)
            for value in context_values:
                _add(value)

        return context[:8]

    def _dedupe_raw_results(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        anonymous_count = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            key = str(
                record.get('url')
                or record.get('citation')
                or record.get('title')
                or record.get('content')
                or f'anonymous:{anonymous_count}'
            ).strip().lower()
            anonymous_count += 1
            existing = merged.get(key)
            if existing is None or float(record.get('score', 0.0) or 0.0) > float(existing.get('score', 0.0) or 0.0):
                merged[key] = record
        return list(merged.values())
    
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

        query_context = self._build_query_context(
            query=query,
            claim_type=claim_type,
            jurisdiction=jurisdiction,
        )
        evidence_context = self._build_evidence_context(
            query=query,
            claim_type=claim_type,
            jurisdiction=jurisdiction,
        )
        search_queries = [query]
        if self.integration_flags.enhanced_search or self.integration_flags.enhanced_legal:
            search_queries = list(query_context.get('queries', []) or [query])[:3]
        
        # Search US Code
        for subquery in search_queries:
            results['statutes'].extend(self.search_us_code(subquery, max_results=5))
        results['statutes'] = self._dedupe_raw_results(results['statutes'])
        
        # Search Federal Register
        for subquery in search_queries:
            results['regulations'].extend(self.search_federal_register(subquery, max_results=5))
        results['regulations'] = self._dedupe_raw_results(results['regulations'])
        
        # Search case law
        for subquery in search_queries:
            results['case_law'].extend(self.search_case_law(subquery, jurisdiction, max_results=5))
        results['case_law'] = self._dedupe_raw_results(results['case_law'])
        
        # Search relevant legal web archives
        legal_domains = ['law.cornell.edu', 'law.justia.com', 'findlaw.com']
        for domain in legal_domains:
            try:
                web_results = self.search_web_archives(domain, max_results=3)
                results['web_archives'].extend(web_results)
            except Exception:
                pass
        
        total_found = sum(len(v) for v in results.values())

        if self.integration_flags.enhanced_search or self.integration_flags.enhanced_legal:
            normalized_records: List[Dict[str, Any]] = []
            normalized_records.extend(self._normalize_records(
                records=results['statutes'],
                query=query,
                source_type='statute',
                source_name='us_code',
            ))
            normalized_records.extend(self._normalize_records(
                records=results['regulations'],
                query=query,
                source_type='regulation',
                source_name='federal_register',
            ))
            normalized_records.extend(self._normalize_records(
                records=results['case_law'],
                query=query,
                source_type='case_law',
                source_name='recap',
            ))
            normalized_records.extend(self._normalize_records(
                records=results['web_archives'],
                query=query,
                source_type='web_archive',
                source_name='common_crawl',
            ))

            if self.integration_flags.enhanced_vector:
                normalized_records = self.vector_augmentor.augment_normalized_records(
                    records=normalized_records,
                    query=query,
                    context_texts=evidence_context,
                )
                self.mediator.log(
                    'legal_authority_vector_augmentation',
                    query=query,
                    records=len(normalized_records),
                    evidence_context_items=len(evidence_context),
                    capabilities=self.vector_augmentor.capabilities(),
                )

            if self.integration_flags.enhanced_graph and self.integration_flags.reranker_mode in {
                'graph',
                'hybrid',
                'auto',
                'on',
            }:
                canary_enabled = self.graph_reranker.should_apply_canary(
                    seed=f"legal_authority|{query}",
                    percent=self.integration_flags.reranker_canary_percent,
                )
                if canary_enabled:
                    normalized_records = self.graph_reranker.augment_normalized_records(
                        records=normalized_records,
                        query=query,
                        mediator=self.mediator,
                        enable_optimizer=self.integration_flags.enhanced_optimizer,
                        retrieval_max_latency_ms=self.integration_flags.retrieval_max_latency_ms,
                    )
                    sample_metadata = dict((normalized_records[0] if normalized_records else {}).get('metadata', {}) or {})
                    self.mediator.log(
                        'legal_authority_graph_reranking',
                        query=query,
                        records=len(normalized_records),
                        reranker_mode=self.integration_flags.reranker_mode,
                        enhanced_optimizer=self.integration_flags.enhanced_optimizer,
                        retrieval_max_latency_ms=self.integration_flags.retrieval_max_latency_ms,
                        reranker_canary_percent=self.integration_flags.reranker_canary_percent,
                        canary_enabled=canary_enabled,
                        latency_guard=sample_metadata.get('graph_latency_guard_applied', False),
                        average_boost=sample_metadata.get('graph_run_avg_boost', 0.0),
                        elapsed_ms=sample_metadata.get('graph_run_elapsed_ms', 0.0),
                    )
                    if hasattr(self.mediator, 'update_reranker_metrics'):
                        self.mediator.update_reranker_metrics(
                            source='legal_authority',
                            applied=True,
                            metadata=sample_metadata,
                            canary_enabled=canary_enabled,
                            window_size=self.integration_flags.reranker_metrics_window,
                        )
                else:
                    self.mediator.log(
                        'legal_authority_graph_reranking_skipped',
                        query=query,
                        reranker_mode=self.integration_flags.reranker_mode,
                        reranker_canary_percent=self.integration_flags.reranker_canary_percent,
                        canary_enabled=canary_enabled,
                    )
                    if hasattr(self.mediator, 'update_reranker_metrics'):
                        self.mediator.update_reranker_metrics(
                            source='legal_authority',
                            applied=False,
                            metadata={},
                            canary_enabled=canary_enabled,
                            window_size=self.integration_flags.reranker_metrics_window,
                        )

            results['normalized'] = self._merge_rank_normalized(
                normalized_records,
                max_results=20,
                query_context=query_context,
            )
            results['support_bundle'] = self._build_support_bundle(results['normalized'])

            self.mediator.log(
                'legal_authority_normalized_results',
                query=query,
                decomposed_queries=len(query_context.get('queries', []) or []),
                raw_total=total_found,
                normalized_total=len(results['normalized']),
                enhanced_search=self.integration_flags.enhanced_search,
                enhanced_legal=self.integration_flags.enhanced_legal,
            )

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
            
            result = conn.execute("""
                INSERT INTO legal_authorities (
                    user_id, complaint_id, claim_type, authority_type,
                    source, citation, title, content, url, metadata,
                    relevance_score, search_query
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, [
                user_id,
                complaint_id,
                claim_type,
                authority_data.get('type', 'unknown'),
                authority_data.get('source', 'unknown'),
                authority_data.get('citation'),
                authority_data.get('title'),
                authority_data.get('content') or authority_data.get('text'),
                authority_data.get('url'),
                json.dumps(authority_data.get('metadata', {})),
                authority_data.get('relevance_score', 0.5),
                search_query
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
                       content, url, metadata, relevance_score, timestamp
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
                    'timestamp': row[9]
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
                       title, content, url, metadata, relevance_score, timestamp
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
                    'timestamp': row[10]
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
