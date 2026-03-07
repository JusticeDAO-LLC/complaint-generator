"""
Web Evidence Discovery Hooks for Mediator

This module provides hooks for automatically discovering evidence using:
1. Common Crawl Search Engine - Search archived web pages
2. Brave Search API - Search current web content
3. Web Archive tools - Find historical evidence
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
    from ipfs_datasets_py.web_archiving import CommonCrawlSearchEngine
    COMMON_CRAWL_AVAILABLE = True
except ImportError:
    COMMON_CRAWL_AVAILABLE = False
    CommonCrawlSearchEngine = None

try:
    from ipfs_datasets_py.web_archiving.brave_search_client import BraveSearchClient
    BRAVE_SEARCH_AVAILABLE = True
except ImportError:
    BRAVE_SEARCH_AVAILABLE = False
    BraveSearchClient = None


class WebEvidenceSearchHook:
    """
    Hook for discovering evidence from web sources.
    
    Uses multiple web archiving and search tools to automatically
    find relevant evidence for legal cases.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        self.integration_flags = IntegrationFeatureFlags.from_env()
        self.integration_adapter = IPFSDatasetsAdapter(feature_flags=self.integration_flags)
        self.retrieval_orchestrator = RetrievalOrchestrator()
        self.vector_augmentor = VectorRetrievalAugmentor()
        self.graph_reranker = GraphAwareRetrievalReranker()
        self._init_search_tools()

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

    def _build_query_context(self, query: str) -> Dict[str, Any]:
        return self.retrieval_orchestrator.build_query_context(
            query=query,
            max_queries=3,
        )

    def _build_evidence_context(
        self,
        keywords: List[str],
        domains: Optional[List[str]] = None,
    ) -> List[str]:
        context: List[str] = []

        def _add(value: Any):
            text = str(value or '').strip()
            if text and text not in context:
                context.append(text)

        for keyword in keywords or []:
            _add(keyword)
        for domain in domains or []:
            _add(domain)

        state = getattr(self.mediator, 'state', None)
        if state is None:
            return context

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
    
    def _init_search_tools(self):
        """Initialize web search tools."""
        # Initialize Common Crawl Search Engine
        if COMMON_CRAWL_AVAILABLE:
            try:
                self.cc_search = CommonCrawlSearchEngine(mode='local')
                self.mediator.log('web_evidence_init',
                    message='Common Crawl Search Engine initialized')
            except Exception as e:
                self.cc_search = None
                self.mediator.log('web_evidence_warning',
                    message=f'Failed to initialize Common Crawl: {e}')
        else:
            self.cc_search = None
            self.mediator.log('web_evidence_warning',
                message='Common Crawl not available')
        
        # Initialize Brave Search Client
        if BRAVE_SEARCH_AVAILABLE:
            try:
                # Check for API key
                api_key = os.environ.get('BRAVE_SEARCH_API_KEY')
                if api_key:
                    self.brave_search = BraveSearchClient(api_key=api_key)
                    self.mediator.log('web_evidence_init',
                        message='Brave Search initialized')
                else:
                    self.brave_search = None
                    self.mediator.log('web_evidence_warning',
                        message='Brave Search API key not found (set BRAVE_SEARCH_API_KEY)')
            except Exception as e:
                self.brave_search = None
                self.mediator.log('web_evidence_warning',
                    message=f'Failed to initialize Brave Search: {e}')
        else:
            self.brave_search = None
            self.mediator.log('web_evidence_warning',
                message='Brave Search client not available')
    
    def search_common_crawl(self, domain: str, keywords: Optional[List[str]] = None,
                           max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search Common Crawl archives for evidence.
        
        Args:
            domain: Domain to search (e.g., "example.com")
            keywords: Optional keywords to filter results
            max_results: Maximum number of results
            
        Returns:
            List of archived web pages with potential evidence
        """
        if not self.cc_search:
            self.mediator.log('web_evidence_unavailable',
                search_type='common_crawl', domain=domain)
            return []
        
        try:
            results = self.cc_search.search_domain(
                domain=domain,
                max_matches=max_results
            )
            
            # Filter results by keywords if provided
            if keywords:
                lowered_keywords = [k.lower() for k in keywords if k]
                if lowered_keywords:
                    filtered_results: List[Dict[str, Any]] = []
                    for result in results:
                        # Safely gather text from common fields if present
                        fields_to_check = []
                        if isinstance(result, dict):
                            for field in ("url", "title", "content", "snippet", "text"):
                                value = result.get(field)
                                if isinstance(value, str):
                                    fields_to_check.append(value)
                        combined_text = " ".join(fields_to_check).lower()
                        if any(kw in combined_text for kw in lowered_keywords):
                            filtered_results.append(result)
                    results = filtered_results
            
            # Add metadata
            for result in results:
                result['source_type'] = 'common_crawl'
                result['discovered_at'] = datetime.now().isoformat()
            
            self.mediator.log('web_evidence_search',
                search_type='common_crawl', domain=domain, found=len(results))
            
            return results
            
        except Exception as e:
            self.mediator.log('web_evidence_search_error',
                search_type='common_crawl', error=str(e))
            return []
    
    def search_brave(self, query: str, max_results: int = 10,
                    freshness: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search web using Brave Search for current evidence.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            freshness: Optional freshness filter ('pd' for past day, 'pw' for past week, etc.)
            
        Returns:
            List of web search results with potential evidence
        """
        if not self.brave_search:
            self.mediator.log('web_evidence_unavailable',
                search_type='brave_search', query=query)
            return []
        
        try:
            # Brave Search expects count parameter
            search_params = {
                'count': min(max_results, 20)  # Brave has limits
            }
            
            if freshness:
                search_params['freshness'] = freshness
            
            results = self.brave_search.web_search(query, **search_params)
            
            # Extract and format results
            formatted_results = []
            if results and 'web' in results and 'results' in results['web']:
                for item in results['web']['results'][:max_results]:
                    formatted_results.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'description': item.get('description', ''),
                        'content': item.get('description', ''),  # Use description as content preview
                        'source_type': 'brave_search',
                        'discovered_at': datetime.now().isoformat(),
                        'metadata': {
                            'age': item.get('age', ''),
                            'language': item.get('language', '')
                        }
                    })
            
            self.mediator.log('web_evidence_search',
                search_type='brave_search', query=query, found=len(formatted_results))
            
            return formatted_results
            
        except Exception as e:
            self.mediator.log('web_evidence_search_error',
                search_type='brave_search', error=str(e))
            return []
    
    def search_for_evidence(self, keywords: List[str], domains: Optional[List[str]] = None,
                           max_results: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search all available sources for evidence.
        
        Args:
            keywords: List of keywords to search for
            domains: Optional specific domains to search
            max_results: Maximum results per source
            
        Returns:
            Dictionary with results from each source
        """
        results = {
            'common_crawl': [],
            'brave_search': [],
            'total_found': 0
        }
        
        # Build search query from keywords
        search_query = ' '.join(keywords)
        query_context = self._build_query_context(search_query)
        evidence_context = self._build_evidence_context(keywords=keywords, domains=domains)
        
        # Search Brave for current web content
        if self.brave_search:
            brave_results = self.search_brave(search_query, max_results=max_results)
            results['brave_search'] = brave_results
            results['total_found'] += len(brave_results)
        
        # Search Common Crawl for specific domains if provided
        if self.cc_search and domains:
            for domain in domains[:3]:  # Limit to top 3 domains
                try:
                    cc_results = self.search_common_crawl(domain, keywords, max_results=5)
                    results['common_crawl'].extend(cc_results)
                    results['total_found'] += len(cc_results)
                except Exception as e:
                    self.mediator.log('web_evidence_domain_error',
                        domain=domain, error=str(e))

        if self.integration_flags.enhanced_search:
            normalized_records: List[Dict[str, Any]] = []
            normalized_records.extend(self._normalize_records(
                records=results['brave_search'],
                query=search_query,
                source_type='web',
                source_name='brave_search',
            ))
            normalized_records.extend(self._normalize_records(
                records=results['common_crawl'],
                query=search_query,
                source_type='web_archive',
                source_name='common_crawl',
            ))

            if self.integration_flags.enhanced_vector:
                normalized_records = self.vector_augmentor.augment_normalized_records(
                    records=normalized_records,
                    query=search_query,
                    context_texts=evidence_context,
                )
                self.mediator.log(
                    'web_evidence_vector_augmentation',
                    query=search_query,
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
                    seed=f"web_evidence|{search_query}",
                    percent=self.integration_flags.reranker_canary_percent,
                )
                if canary_enabled:
                    normalized_records = self.graph_reranker.augment_normalized_records(
                        records=normalized_records,
                        query=search_query,
                        mediator=self.mediator,
                        enable_optimizer=self.integration_flags.enhanced_optimizer,
                        retrieval_max_latency_ms=self.integration_flags.retrieval_max_latency_ms,
                    )
                    sample_metadata = dict((normalized_records[0] if normalized_records else {}).get('metadata', {}) or {})
                    self.mediator.log(
                        'web_evidence_graph_reranking',
                        query=search_query,
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
                            source='web_evidence',
                            applied=True,
                            metadata=sample_metadata,
                            canary_enabled=canary_enabled,
                            window_size=self.integration_flags.reranker_metrics_window,
                        )
                else:
                    self.mediator.log(
                        'web_evidence_graph_reranking_skipped',
                        query=search_query,
                        reranker_mode=self.integration_flags.reranker_mode,
                        reranker_canary_percent=self.integration_flags.reranker_canary_percent,
                        canary_enabled=canary_enabled,
                    )
                    if hasattr(self.mediator, 'update_reranker_metrics'):
                        self.mediator.update_reranker_metrics(
                            source='web_evidence',
                            applied=False,
                            metadata={},
                            canary_enabled=canary_enabled,
                            window_size=self.integration_flags.reranker_metrics_window,
                        )

            results['normalized'] = self._merge_rank_normalized(
                normalized_records,
                max_results=max_results,
                query_context=query_context,
            )
            results['support_bundle'] = self._build_support_bundle(results['normalized'])
            self.mediator.log(
                'web_evidence_normalized_results',
                query=search_query,
                decomposed_queries=len(query_context.get('queries', []) or []),
                raw_total=results['total_found'],
                normalized_total=len(results['normalized']),
                enhanced_search=self.integration_flags.enhanced_search,
            )
        
        self.mediator.log('web_evidence_search_all',
            keywords=keywords, total_found=results['total_found'])
        
        return results
    
    def validate_evidence(self, evidence_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and score discovered evidence.
        
        Args:
            evidence_item: Evidence item from search results
            
        Returns:
            Validation result with relevance score
        """
        validation = {
            'valid': True,
            'relevance_score': 0.5,
            'issues': [],
            'recommendations': []
        }
        
        # Check for required fields
        if not evidence_item.get('url'):
            validation['valid'] = False
            validation['issues'].append('Missing URL')
        
        if not evidence_item.get('title') and not evidence_item.get('content'):
            validation['valid'] = False
            validation['issues'].append('Missing content')
        
        # Increase relevance for certain sources
        if evidence_item.get('source_type') == 'brave_search':
            validation['relevance_score'] = 0.7
        elif evidence_item.get('source_type') == 'common_crawl':
            validation['relevance_score'] = 0.6
        
        # Use LLM to assess relevance if available
        try:
            prompt = f"""Assess the relevance of this web evidence for a legal case:
Title: {evidence_item.get('title', 'N/A')}
URL: {evidence_item.get('url', 'N/A')}
Content preview: {evidence_item.get('description', '')[:200]}

Rate relevance from 0.0 to 1.0 and briefly explain why."""
            
            response = self.mediator.query_backend(prompt)
            
            # Try to extract score from response
            if '0.' in response or '1.0' in response:
                # Simple extraction - look for decimal numbers
                import re
                scores = re.findall(r'0\.\d+|1\.0', response)
                if scores:
                    validation['relevance_score'] = float(scores[0])
                    validation['recommendations'].append(response.split('\n')[0])
        except Exception as e:
            # If LLM not available or errors, use default score
            pass
        
        return validation


class WebEvidenceIntegrationHook:
    """
    Hook for integrating discovered web evidence with evidence storage.
    
    Manages the workflow of discovering, validating, and storing
    web evidence alongside user-submitted evidence.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        # Create a search hook for convenience methods
        self._search_hook = None
    
    def _get_search_hook(self):
        """Lazy initialization of search hook."""
        if self._search_hook is None:
            if hasattr(self.mediator, 'web_evidence_search'):
                self._search_hook = self.mediator.web_evidence_search
            else:
                self._search_hook = WebEvidenceSearchHook(self.mediator)
        return self._search_hook
    
    def discover_and_store_evidence(self, keywords: List[str],
                                    domains: Optional[List[str]] = None,
                                    user_id: Optional[str] = None,
                                    claim_type: Optional[str] = None,
                                    min_relevance: float = 0.5) -> Dict[str, Any]:
        """
        Discover evidence from web sources and store in evidence database.
        
        Args:
            keywords: Keywords to search for
            domains: Optional specific domains
            user_id: User identifier
            claim_type: Associated claim type
            min_relevance: Minimum relevance score to store (0.0 to 1.0)
            
        Returns:
            Dictionary with discovered and stored evidence counts
        """
        if not hasattr(self.mediator, 'web_evidence_search'):
            return {'error': 'Web evidence search not available'}
        
        if user_id is None:
            user_id = getattr(self.mediator.state, 'username', None) or \
                     getattr(self.mediator.state, 'hashed_username', 'anonymous')
        
        # Search for evidence
        search_results = self.mediator.web_evidence_search.search_for_evidence(
            keywords=keywords,
            domains=domains,
            max_results=20
        )
        
        stored_evidence = {
            'discovered': search_results['total_found'],
            'validated': 0,
            'stored': 0,
            'skipped': 0,
            'evidence_cids': []
        }
        
        # Process each result
        all_results = (
            search_results.get('brave_search', []) +
            search_results.get('common_crawl', [])
        )
        
        for evidence_item in all_results:
            # Validate evidence
            validation = self.mediator.web_evidence_search.validate_evidence(evidence_item)
            
            if not validation['valid']:
                stored_evidence['skipped'] += 1
                continue
            
            stored_evidence['validated'] += 1
            
            if validation['relevance_score'] < min_relevance:
                stored_evidence['skipped'] += 1
                continue
            
            # Store evidence
            try:
                # Convert evidence to bytes (JSON representation)
                evidence_data = json.dumps({
                    'title': evidence_item.get('title', ''),
                    'url': evidence_item.get('url', ''),
                    'content': evidence_item.get('content', ''),
                    'description': evidence_item.get('description', ''),
                    'source_type': evidence_item.get('source_type', 'web'),
                    'discovered_at': evidence_item.get('discovered_at', ''),
                    'metadata': evidence_item.get('metadata', {})
                }).encode('utf-8')
                
                # Store in IPFS via evidence storage hook
                storage_result = self.mediator.evidence_storage.store_evidence(
                    data=evidence_data,
                    evidence_type='web_document',
                    metadata={
                        'source_type': evidence_item.get('source_type'),
                        'source_url': evidence_item.get('url'),
                        'auto_discovered': True,
                        'relevance_score': validation['relevance_score'],
                        'keywords': keywords
                    }
                )
                
                # Add to evidence state database
                record_id = self.mediator.evidence_state.add_evidence_record(
                    user_id=user_id,
                    evidence_info=storage_result,
                    description=f"Auto-discovered: {evidence_item.get('title', 'Web evidence')}",
                    claim_type=claim_type
                )
                
                stored_evidence['stored'] += 1
                stored_evidence['evidence_cids'].append(storage_result['cid'])
                
                self.mediator.log('web_evidence_stored',
                    cid=storage_result['cid'],
                    url=evidence_item.get('url'),
                    relevance=validation['relevance_score'])
                
            except Exception as e:
                self.mediator.log('web_evidence_storage_error',
                    url=evidence_item.get('url'), error=str(e))
                stored_evidence['skipped'] += 1
        
        self.mediator.log('web_evidence_discovery_complete',
            discovered=stored_evidence['discovered'],
            stored=stored_evidence['stored'])
        
        return stored_evidence
    
    def discover_evidence_for_case(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Automatically discover evidence for all claims in the case.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with discovery results for each claim
        """
        if user_id is None:
            user_id = getattr(self.mediator.state, 'username', None) or \
                     getattr(self.mediator.state, 'hashed_username', 'anonymous')
        
        # First, analyze the complaint if not already done
        if not hasattr(self.mediator.state, 'legal_classification'):
            if not self.mediator.state.complaint:
                return {'error': 'No complaint available. Generate complaint first.'}
            self.mediator.analyze_complaint_legal_issues()
        
        classification = self.mediator.state.legal_classification
        results = {
            'claim_types': classification.get('claim_types', []),
            'evidence_discovered': {},
            'evidence_stored': {}
        }
        
        # Discover evidence for each claim type
        for claim_type in classification.get('claim_types', []):
            self.mediator.log('auto_evidence_discovery', claim_type=claim_type)
            
            # Generate search keywords for this claim
            keywords = self._generate_search_keywords(claim_type)
            
            # Discover and store evidence
            discovery_result = self.discover_and_store_evidence(
                keywords=keywords,
                user_id=user_id,
                claim_type=claim_type,
                min_relevance=0.6  # Higher threshold for auto-discovery
            )
            
            results['evidence_discovered'][claim_type] = discovery_result['discovered']
            results['evidence_stored'][claim_type] = discovery_result['stored']
        
        self.mediator.log('auto_evidence_discovery_complete', results=results)
        
        return results
    
    def _generate_search_keywords(self, claim_type: str) -> List[str]:
        """Generate search keywords for a claim type."""
        # Use LLM to generate targeted keywords
        try:
            prompt = f"""Generate 3-5 specific search keywords for finding evidence related to a "{claim_type}" legal claim.
Return only the keywords, one per line, focused on finding factual evidence."""
            
            response = self.mediator.query_backend(prompt)
            keywords = [line.strip() for line in response.split('\n') if line.strip()]
            return keywords[:5] or [claim_type]
        except Exception:
            # Fallback to claim type
            return [claim_type, f"{claim_type} evidence", f"{claim_type} documentation"]
    
    # Convenience methods for legal research
    
    def search_legal_precedents(self, claim: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for legal precedents related to a claim.
        
        Args:
            claim: Legal claim description
            max_results: Maximum number of results
            
        Returns:
            List of relevant legal precedents
        """
        query = f"{claim} legal precedent case law"
        return self._get_search_hook().search_brave(query, max_results=max_results)
    
    def search_case_law(self, complaint_type: str, jurisdiction: Optional[str] = None,
                       max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for case law related to complaint type.
        
        Args:
            complaint_type: Type of complaint
            jurisdiction: Optional jurisdiction (e.g., "federal", "California")
            max_results: Maximum number of results
            
        Returns:
            List of relevant case law
        """
        query = f"{complaint_type} case law"
        if jurisdiction:
            query += f" {jurisdiction}"
        return self._get_search_hook().search_brave(query, max_results=max_results)
    
    def search_legal_definitions(self, term: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for legal definitions of a term.
        
        Args:
            term: Legal term to define
            max_results: Maximum number of results
            
        Returns:
            List of definition sources
        """
        query = f'legal definition of "{term}"'
        return self._get_search_hook().search_brave(query, max_results=max_results)
    
    def search_statute_text(self, statute_name: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for the text of a statute or regulation.
        
        Args:
            statute_name: Name of statute (e.g., "Fair Housing Act")
            max_results: Maximum number of results
            
        Returns:
            List of statute sources
        """
        query = f'"{statute_name}" full text statute'
        return self._get_search_hook().search_brave(query, max_results=max_results)
