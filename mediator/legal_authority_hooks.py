"""Legal authority retrieval hooks for mediator."""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from integrations.ipfs_datasets.provenance import (
    build_document_parse_contract,
    build_fact_lineage_metadata,
    build_provenance,
    enrich_document_parse,
)
from integrations.ipfs_datasets.documents import detect_document_input_format, parse_document_text
from integrations.ipfs_datasets.graphs import extract_graph_from_text, persist_graph_snapshot
from integrations.ipfs_datasets.types import CaseAuthority, CaseFact
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
                        results.extend(
                            {
                                **statute,
                                'source': statute.get('source', 'us_code'),
                            }
                            for statute in statute_results
                            if isinstance(statute, dict)
                        )
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

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_facts (
                    authority_id BIGINT,
                    fact_id VARCHAR,
                    fact_text TEXT,
                    source_authority_id VARCHAR,
                    confidence FLOAT,
                    metadata JSON,
                    provenance JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_chunks (
                    authority_id BIGINT,
                    chunk_id VARCHAR,
                    chunk_index INTEGER,
                    start_offset INTEGER,
                    end_offset INTEGER,
                    chunk_text TEXT,
                    metadata JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_graph_entities (
                    authority_id BIGINT,
                    entity_id VARCHAR,
                    entity_type VARCHAR,
                    entity_name TEXT,
                    confidence FLOAT,
                    metadata JSON
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_authority_graph_relationships (
                    authority_id BIGINT,
                    relationship_id VARCHAR,
                    source_id VARCHAR,
                    target_id VARCHAR,
                    relation_type VARCHAR,
                    confidence FLOAT,
                    metadata JSON
                )
            """)

            for statement in [
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS jurisdiction VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS source_system VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS provenance JSON",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS claim_element_id VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS claim_element TEXT",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parse_status VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS chunk_count INTEGER",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parsed_text_preview TEXT",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parse_metadata JSON",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_status VARCHAR",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_entity_count INTEGER",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_relationship_count INTEGER",
                "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_metadata JSON",
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

    def _parse_authority_text(self, authority: Dict[str, Any]) -> Dict[str, Any]:
        authority_metadata = authority.get('metadata', {}) if isinstance(authority.get('metadata'), dict) else {}
        content_field = ''
        authority_text = ''
        for candidate in ('content', 'text', 'html_body', 'raw_html'):
            candidate_value = str(authority.get(candidate) or '')
            if candidate_value:
                content_field = candidate
                authority_text = candidate_value
                break
        used_reference_fallback = False
        if not authority_text:
            used_reference_fallback = True
            content_field = 'citation_title_fallback'
            authority_text = '\n\n'.join(
                part for part in [authority.get('title') or '', authority.get('citation') or ''] if part
            )

        filename = str(authority.get('citation') or authority.get('title') or authority.get('url') or 'authority.txt')
        input_format = detect_document_input_format(
            text=str(authority_text),
            filename=filename,
            mime_type=str(authority_metadata.get('mime_type') or authority.get('mime_type') or ''),
        )
        mime_type_map = {
            'html': 'text/html',
            'text': 'text/plain',
            'email': 'message/rfc822',
            'rtf': 'application/rtf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pdf': 'application/pdf',
        }

        parsed = parse_document_text(
            str(authority_text),
            filename=filename,
            mime_type=mime_type_map.get(input_format, 'text/plain'),
            source='legal_authority',
        )
        content_origin = 'authority_reference_fallback' if used_reference_fallback else 'authority_full_text'
        fallback_mode = 'citation_title_only' if used_reference_fallback else ''
        parsed = enrich_document_parse(
            parsed,
            default_source='legal_authority',
            extra_metadata={
                'content_origin': content_origin,
                'content_source_field': content_field,
                'authority_type': str(authority.get('type') or ''),
                'authority_source': str(authority.get('source') or ''),
                'citation': str(authority.get('citation') or ''),
                'title': str(authority.get('title') or ''),
                'source_url': str(authority.get('url') or ''),
                'fallback_mode': fallback_mode,
            },
            extra_lineage={
                'content_origin': content_origin,
                'content_source_field': content_field,
                'authority_type': str(authority.get('type') or ''),
                'authority_source': str(authority.get('source') or ''),
                'citation': str(authority.get('citation') or ''),
                'title': str(authority.get('title') or ''),
                'source_url': str(authority.get('url') or ''),
                'fallback_mode': fallback_mode,
            },
        )
        parse_contract = build_document_parse_contract(parsed, default_source='legal_authority')
        authority_metadata['document_parse_summary'] = parse_contract['summary']
        authority_metadata['document_parse_contract'] = parse_contract
        authority['metadata'] = authority_metadata
        return parsed

    def _store_authority_chunks(self, conn, authority_id: int, document_parse: Dict[str, Any]) -> None:
        chunks = document_parse.get('chunks', []) or []
        if not chunks:
            return

        parse_contract = build_document_parse_contract(document_parse, default_source='legal_authority')
        for chunk in chunks:
            conn.execute(
                """
                INSERT INTO legal_authority_chunks (
                    authority_id, chunk_id, chunk_index, start_offset, end_offset, chunk_text, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    chunk.get('chunk_id'),
                    chunk.get('index'),
                    chunk.get('start'),
                    chunk.get('end'),
                    chunk.get('text'),
                    json.dumps({
                        'length': chunk.get('length', 0),
                        'parser_version': parse_contract.get('summary', {}).get('parser_version', ''),
                        'source': parse_contract.get('source', 'legal_authority'),
                        'input_format': parse_contract.get('summary', {}).get('input_format', ''),
                    }),
                ],
            )

    def _store_authority_facts(
        self,
        conn,
        authority_id: int,
        graph_payload: Dict[str, Any],
        provenance,
        document_parse: Dict[str, Any],
    ) -> None:
        parse_contract = build_document_parse_contract(document_parse, default_source='legal_authority')
        for entity in graph_payload.get('entities', []) or []:
            if entity.get('type') != 'fact':
                continue
            attributes = entity.get('attributes', {}) if isinstance(entity.get('attributes'), dict) else {}
            fact = CaseFact(
                fact_id=str(entity.get('id') or ''),
                text=str(attributes.get('text') or entity.get('name') or ''),
                source_authority_id=f'authority:{authority_id}',
                confidence=float(entity.get('confidence', 0.0) or 0.0),
                metadata=build_fact_lineage_metadata(
                    attributes,
                    parse_contract=parse_contract,
                    record_scope='legal_authority',
                    source_ref=f'authority:{authority_id}',
                ),
                provenance=build_provenance(
                    source_url=str(provenance.source_url or ''),
                    acquisition_method=str(provenance.acquisition_method or ''),
                    source_type=str(provenance.source_type or ''),
                    acquired_at=str(provenance.acquired_at or ''),
                    content_hash=str(provenance.content_hash or ''),
                    source_system=str(provenance.source_system or ''),
                    jurisdiction=str(provenance.jurisdiction or ''),
                ),
            )
            conn.execute(
                """
                INSERT INTO legal_authority_facts (
                    authority_id, fact_id, fact_text, source_authority_id, confidence, metadata, provenance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    fact.fact_id,
                    fact.text,
                    fact.source_authority_id,
                    fact.confidence,
                    json.dumps(fact.metadata),
                    json.dumps(fact.provenance.as_dict()),
                ],
            )

    def _extract_authority_graph(
        self,
        authority_id: int,
        authority: Dict[str, Any],
        claim_type: Optional[str],
        document_parse: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        parsed_text = ''
        if isinstance(document_parse, dict):
            parsed_text = document_parse.get('text', '') or ''
        authority_text = parsed_text or authority.get('content') or authority.get('title') or authority.get('citation') or ''
        if not authority_text:
            return {'status': 'unavailable', 'entities': [], 'relationships': [], 'metadata': {}}

        return extract_graph_from_text(
            authority_text,
            source_id=f'authority:{authority_id}',
            metadata={
                'artifact_id': f'authority:{authority_id}',
                'title': authority.get('title', ''),
                'source_url': authority.get('url', ''),
                'claim_type': claim_type or '',
                'claim_element_id': authority.get('claim_element_id', ''),
                'claim_element_text': authority.get('claim_element', ''),
                'parse_status': document_parse.get('status', '') if isinstance(document_parse, dict) else '',
            },
        )

    def _store_authority_graph(self, conn, authority_id: int, graph_payload: Dict[str, Any]) -> None:
        for entity in graph_payload.get('entities', []) or []:
            conn.execute(
                """
                INSERT INTO legal_authority_graph_entities (
                    authority_id, entity_id, entity_type, entity_name, confidence, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    entity.get('id'),
                    entity.get('type'),
                    entity.get('name'),
                    entity.get('confidence', 0.0),
                    json.dumps(entity.get('attributes', {})),
                ],
            )

        for relationship in graph_payload.get('relationships', []) or []:
            conn.execute(
                """
                INSERT INTO legal_authority_graph_relationships (
                    authority_id, relationship_id, source_id, target_id, relation_type, confidence, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    authority_id,
                    relationship.get('id'),
                    relationship.get('source_id'),
                    relationship.get('target_id'),
                    relationship.get('relation_type'),
                    relationship.get('confidence', 0.0),
                    json.dumps(relationship.get('attributes', {})),
                ],
            )

    def _authority_record_from_row(self, row, *, include_claim_type: bool = False) -> Dict[str, Any]:
        offset = 1 if include_claim_type else 0
        record = {
            'id': row[0],
            'type': row[1 + offset],
            'source': row[2 + offset],
            'citation': row[3 + offset],
            'title': row[4 + offset],
            'content': row[5 + offset],
            'url': row[6 + offset],
            'metadata': json.loads(row[7 + offset]) if row[7 + offset] else {},
            'relevance_score': row[8 + offset],
            'timestamp': row[9 + offset],
            'jurisdiction': row[10 + offset],
            'source_system': row[11 + offset],
            'provenance': json.loads(row[12 + offset]) if row[12 + offset] else {},
            'claim_element_id': row[13 + offset],
            'claim_element': row[14 + offset],
            'parse_status': row[15 + offset],
            'chunk_count': row[16 + offset] or 0,
            'parsed_text_preview': row[17 + offset] or '',
            'parse_metadata': json.loads(row[18 + offset]) if row[18 + offset] else {},
            'graph_status': row[19 + offset],
            'graph_entity_count': row[20 + offset] or 0,
            'graph_relationship_count': row[21 + offset] or 0,
            'graph_metadata': json.loads(row[22 + offset]) if row[22 + offset] else {},
            'fact_count': row[23 + offset] or 0,
        }
        if include_claim_type:
            record['claim_type'] = row[1]
        return record

    def _resolve_claim_element(
        self,
        user_id: str,
        claim_type: Optional[str],
        authority_data: Dict[str, Any],
    ) -> Dict[str, Optional[str]]:
        claim_support = getattr(self.mediator, 'claim_support', None)
        if not claim_type or claim_support is None:
            return {
                'claim_element_id': authority_data.get('claim_element_id'),
                'claim_element': authority_data.get('claim_element'),
            }

        metadata = authority_data.get('metadata', {})
        if not isinstance(metadata, dict):
            metadata = {}
        resolution = claim_support.resolve_claim_element(
            user_id,
            claim_type,
            claim_element_text=authority_data.get('claim_element'),
            support_label=authority_data.get('title') or authority_data.get('citation'),
            metadata={
                **metadata,
                'title': authority_data.get('title'),
                'description': authority_data.get('content') or authority_data.get('text'),
                'summary': authority_data.get('summary'),
                'content_excerpt': authority_data.get('content') or authority_data.get('text'),
                'source_url': authority_data.get('url'),
            },
        )
        if not isinstance(resolution, dict):
            resolution = {}
        return {
            'claim_element_id': authority_data.get('claim_element_id') or resolution.get('claim_element_id'),
            'claim_element': authority_data.get('claim_element') or resolution.get('claim_element_text'),
        }

    def _find_existing_authority_record(
        self,
        conn,
        user_id: str,
        complaint_id: Optional[str],
        claim_type: Optional[str],
        authority: Dict[str, Any],
    ) -> Optional[int]:
        citation = authority.get('citation')
        url = authority.get('url')
        title = authority.get('title')
        authority_type = authority.get('type')
        source = authority.get('source')
        claim_element_id = authority.get('claim_element_id')

        if citation:
            existing = conn.execute(
                """
                SELECT id
                FROM legal_authorities
                WHERE user_id = ?
                  AND citation = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, citation, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        if url:
            existing = conn.execute(
                """
                SELECT id
                FROM legal_authorities
                WHERE user_id = ?
                  AND url = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, url, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        if authority_type and source and title:
            existing = conn.execute(
                """
                SELECT id
                FROM legal_authorities
                WHERE user_id = ?
                  AND authority_type = ?
                  AND source = ?
                  AND title = ?
                  AND COALESCE(complaint_id, '') = COALESCE(?, '')
                  AND COALESCE(claim_type, '') = COALESCE(?, '')
                  AND COALESCE(claim_element_id, '') = COALESCE(?, '')
                ORDER BY id ASC
                LIMIT 1
                """,
                [user_id, authority_type, source, title, complaint_id, claim_type, claim_element_id],
            ).fetchone()
            if existing:
                return existing[0]

        return None
    
    def add_authority(self, authority_data: Dict[str, Any],
                     user_id: str, complaint_id: Optional[str] = None,
                     claim_type: Optional[str] = None,
                     search_query: Optional[str] = None) -> int:
        result = self.upsert_authority(
            authority_data,
            user_id,
            complaint_id=complaint_id,
            claim_type=claim_type,
            search_query=search_query,
        )
        return result['record_id']

    def upsert_authority(self, authority_data: Dict[str, Any],
                        user_id: str, complaint_id: Optional[str] = None,
                        claim_type: Optional[str] = None,
                        search_query: Optional[str] = None) -> Dict[str, Any]:
        """
        Add a legal authority to the database.
        
        Args:
            authority_data: Authority information from search
            user_id: User identifier
            complaint_id: Optional complaint ID
            claim_type: Optional claim type
            search_query: Original search query
            
        Returns:
            Dictionary describing whether the authority was newly inserted or reused.
        """
        if not DUCKDB_AVAILABLE:
            self.mediator.log('legal_authority_storage_unavailable')
            return {'record_id': -1, 'created': False, 'reused': False}
        
        try:
            conn = duckdb.connect(self.db_path)
            claim_element = self._resolve_claim_element(user_id, claim_type, authority_data)
            document_parse = self._parse_authority_text(authority_data)
            parse_contract = build_document_parse_contract(document_parse, default_source='legal_authority')
            parsed_text = parse_contract.get('text', '')
            parsed_text_preview = parse_contract.get('text_preview', '')
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
                content=(
                    authority_data.get('content')
                    or authority_data.get('text')
                    or authority_data.get('html_body')
                    or authority_data.get('raw_html')
                    or ''
                ),
                url=authority_data.get('url') or '',
                jurisdiction=provenance.jurisdiction,
                source_system=provenance.source_system,
                claim_element_id=claim_element.get('claim_element_id') or '',
                claim_element=claim_element.get('claim_element') or '',
                relevance_score=authority_data.get('relevance_score', 0.5),
                metadata={
                    **(authority_data.get('metadata', {}) if isinstance(authority_data.get('metadata', {}), dict) else {}),
                    'claim_element_id': claim_element.get('claim_element_id'),
                    'claim_element': claim_element.get('claim_element'),
                },
                provenance=provenance,
            )
            normalized_authority = authority.as_dict()

            existing_record_id = self._find_existing_authority_record(
                conn,
                user_id,
                complaint_id,
                claim_type,
                normalized_authority,
            )
            if existing_record_id is not None:
                conn.close()
                self.mediator.log(
                    'legal_authority_duplicate',
                    record_id=existing_record_id,
                    citation=normalized_authority.get('citation'),
                    url=normalized_authority.get('url'),
                    claim_type=claim_type,
                    claim_element_id=normalized_authority.get('claim_element_id'),
                )
                return {'record_id': existing_record_id, 'created': False, 'reused': True}
            
            result = conn.execute("""
                INSERT INTO legal_authorities (
                    user_id, complaint_id, claim_type, authority_type,
                    source, citation, title, content, url, metadata,
                    relevance_score, search_query, jurisdiction,
                    source_system, provenance, claim_element_id, claim_element,
                    parse_status, chunk_count, parsed_text_preview, parse_metadata,
                    graph_status, graph_entity_count, graph_relationship_count, graph_metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                claim_element.get('claim_element_id'),
                claim_element.get('claim_element'),
                parse_contract.get('status'),
                parse_contract.get('chunk_count', 0),
                parsed_text_preview,
                json.dumps(parse_contract.get('storage_metadata', {})),
                None,
                0,
                0,
                json.dumps({}),
            ]).fetchone()
            
            record_id = result[0]
            graph_payload = self._extract_authority_graph(
                record_id,
                normalized_authority,
                claim_type,
                document_parse=document_parse,
            )
            conn.execute(
                """
                UPDATE legal_authorities
                SET graph_status = ?,
                    graph_entity_count = ?,
                    graph_relationship_count = ?,
                    graph_metadata = ?
                WHERE id = ?
                """,
                [
                    graph_payload.get('status'),
                    len(graph_payload.get('entities', []) or []),
                    len(graph_payload.get('relationships', []) or []),
                    json.dumps({
                        **(graph_payload.get('metadata', {}) or {}),
                        'graph_snapshot': persist_graph_snapshot(
                            graph_payload,
                            graph_changed=bool(graph_payload.get('entities') or graph_payload.get('relationships')),
                            existing_graph=False,
                            persistence_metadata={
                                'record_scope': 'legal_authority',
                                'record_key': str(record_id),
                            },
                        ),
                    }),
                    record_id,
                ],
            )
            self._store_authority_chunks(conn, record_id, document_parse)
            self._store_authority_graph(conn, record_id, graph_payload)
            self._store_authority_facts(
                conn,
                record_id,
                graph_payload,
                provenance,
                document_parse,
            )
            conn.close()
            
            self.mediator.log('legal_authority_added',
                record_id=record_id, citation=authority_data.get('citation'))
            
            return {'record_id': record_id, 'created': True, 'reused': False}
            
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
                        jurisdiction, source_system, provenance, claim_element_id, claim_element,
                                                parse_status, chunk_count, parsed_text_preview, parse_metadata,
                                                graph_status, graph_entity_count, graph_relationship_count, graph_metadata,
                      (
                          SELECT COUNT(*) FROM legal_authority_facts laf WHERE laf.authority_id = legal_authorities.id
                      ) AS fact_count
                FROM legal_authorities
                WHERE user_id = ? AND claim_type = ?
                ORDER BY relevance_score DESC, timestamp DESC
            """, [user_id, claim_type]).fetchall()
            
            conn.close()
            
            return [self._authority_record_from_row(row) for row in results]
            
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
                        jurisdiction, source_system, provenance, claim_element_id, claim_element,
                                                parse_status, chunk_count, parsed_text_preview, parse_metadata,
                                                graph_status, graph_entity_count, graph_relationship_count, graph_metadata,
                      (
                          SELECT COUNT(*) FROM legal_authority_facts laf WHERE laf.authority_id = legal_authorities.id
                      ) AS fact_count
                FROM legal_authorities
                WHERE user_id = ?
                ORDER BY timestamp DESC
            """, [user_id]).fetchall()
            
            conn.close()
            
            return [self._authority_record_from_row(row, include_claim_type=True) for row in results]
            
        except Exception as e:
            self.mediator.log('legal_authority_query_error', error=str(e))
            return []

    def get_authority_by_id(self, authority_id: int) -> Optional[Dict[str, Any]]:
        """Get a single authority record by its DuckDB ID."""
        if not DUCKDB_AVAILABLE:
            return None

        try:
            conn = duckdb.connect(self.db_path)
            row = conn.execute(
                """
                SELECT id, claim_type, authority_type, source, citation,
                      title, content, url, metadata, relevance_score, timestamp,
                        jurisdiction, source_system, provenance, claim_element_id, claim_element,
                                                parse_status, chunk_count, parsed_text_preview, parse_metadata,
                                                graph_status, graph_entity_count, graph_relationship_count, graph_metadata,
                      (
                          SELECT COUNT(*) FROM legal_authority_facts laf WHERE laf.authority_id = legal_authorities.id
                      ) AS fact_count
                FROM legal_authorities
                WHERE id = ?
                LIMIT 1
                """,
                [authority_id],
            ).fetchone()
            conn.close()
            if row is None:
                return None
            return self._authority_record_from_row(row, include_claim_type=True)
        except Exception as e:
            self.mediator.log('legal_authority_query_error', error=str(e), authority_id=authority_id)
            return None

    def get_authority_facts(self, authority_id: int) -> List[Dict[str, Any]]:
        """Get persisted fact records for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                """
                SELECT fact_id, fact_text, source_authority_id, confidence, metadata, provenance
                FROM legal_authority_facts
                WHERE authority_id = ?
                ORDER BY fact_id ASC
                """,
                [authority_id],
            ).fetchall()
            conn.close()
            return [
                {
                    'fact_id': row[0],
                    'text': row[1],
                    'source_authority_id': row[2],
                    'confidence': row[3] or 0.0,
                    'metadata': json.loads(row[4]) if row[4] else {},
                    'provenance': json.loads(row[5]) if row[5] else {},
                }
                for row in rows
            ]
        except Exception as e:
            self.mediator.log('legal_authority_fact_query_error', error=str(e), authority_id=authority_id)
            return []

    def get_authority_chunks(self, authority_id: int) -> List[Dict[str, Any]]:
        """Get parsed chunk records for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return []

        try:
            conn = duckdb.connect(self.db_path)
            rows = conn.execute(
                """
                SELECT chunk_id, chunk_index, start_offset, end_offset, chunk_text, metadata
                FROM legal_authority_chunks
                WHERE authority_id = ?
                ORDER BY chunk_index ASC
                """,
                [authority_id],
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
                for row in rows
            ]
        except Exception as e:
            self.mediator.log('legal_authority_chunk_query_error', error=str(e), authority_id=authority_id)
            return []

    def get_authority_graph(self, authority_id: int) -> Dict[str, Any]:
        """Get normalized graph entities and relationships for a stored legal authority."""
        if not DUCKDB_AVAILABLE:
            return {'status': 'unavailable', 'entities': [], 'relationships': []}

        try:
            conn = duckdb.connect(self.db_path)
            entity_rows = conn.execute(
                """
                SELECT entity_id, entity_type, entity_name, confidence, metadata
                FROM legal_authority_graph_entities
                WHERE authority_id = ?
                ORDER BY entity_id ASC
                """,
                [authority_id],
            ).fetchall()
            relationship_rows = conn.execute(
                """
                SELECT relationship_id, source_id, target_id, relation_type, confidence, metadata
                FROM legal_authority_graph_relationships
                WHERE authority_id = ?
                ORDER BY relationship_id ASC
                """,
                [authority_id],
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
            self.mediator.log('legal_authority_graph_query_error', error=str(e), authority_id=authority_id)
            return {'status': 'error', 'entities': [], 'relationships': [], 'error': str(e)}
    
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
                        COUNT(DISTINCT claim_type) as claim_count,
                        COALESCE((SELECT COUNT(*) FROM legal_authority_facts laf JOIN legal_authorities la ON laf.authority_id = la.id WHERE la.user_id = ?), 0) as total_facts
                    FROM legal_authorities
                    WHERE user_id = ?
                """, [user_id, user_id]).fetchone()
            else:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as total_count,
                        COUNT(DISTINCT authority_type) as type_count,
                        COUNT(DISTINCT user_id) as user_count,
                        COALESCE((SELECT COUNT(*) FROM legal_authority_facts), 0) as total_facts
                    FROM legal_authorities
                """).fetchone()
            
            conn.close()
            
            stats = {
                'available': True,
                'total_count': result[0],
                'type_count': result[1],
                'total_facts': result[3] if user_id else result[3],
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
