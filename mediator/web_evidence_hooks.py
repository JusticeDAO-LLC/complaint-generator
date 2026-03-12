"""Web evidence discovery hooks for mediator."""

import os
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from claim_support_review import summarize_claim_support_snapshot_lifecycle
from integrations.ipfs_datasets.provenance import build_document_parse_contract
from integrations.ipfs_datasets.search import (
    BRAVE_SEARCH_AVAILABLE,
    COMMON_CRAWL_AVAILABLE,
    MULTI_ENGINE_SEARCH_AVAILABLE,
    UNIFIED_WEB_SCRAPER_AVAILABLE,
    BraveSearchAPI,
    CommonCrawlSearchEngine,
    evaluate_scraped_content,
    scrape_archived_domain,
    scrape_web_content,
    search_brave_web,
    search_multi_engine_web,
)
from integrations.ipfs_datasets.scraper_daemon import ScraperDaemon, ScraperDaemonConfig, ScraperTactic


class WebEvidenceSearchHook:
    """
    Hook for discovering evidence from web sources.
    
    Uses multiple web archiving and search tools to automatically
    find relevant evidence for legal cases.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        self._init_search_tools()
    
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
                    self.brave_search = BraveSearchAPI(api_key=api_key) if BraveSearchAPI else None
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
            if hasattr(self.brave_search, 'web_search'):
                search_params = {'count': min(max_results, 20)}
                if freshness:
                    search_params['freshness'] = freshness
                results = self.brave_search.web_search(query, **search_params)
                formatted_results = []
                if results and 'web' in results and 'results' in results['web']:
                    for item in results['web']['results'][:max_results]:
                        formatted_results.append({
                            'title': item.get('title', ''),
                            'url': item.get('url', ''),
                            'description': item.get('description', ''),
                            'content': item.get('description', ''),
                            'source_type': 'brave_search',
                            'discovered_at': datetime.now().isoformat(),
                            'metadata': {
                                'age': item.get('age', ''),
                                'language': item.get('language', '')
                            }
                        })
            else:
                formatted_results = search_brave_web(
                    query=query,
                    max_results=max_results,
                    freshness=freshness,
                    api_key=getattr(self.brave_search, 'api_key', None),
                )
            
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
            'multi_engine_search': [],
            'archived_domain_scrape': [],
            'total_found': 0
        }
        
        # Build search query from keywords
        search_query = ' '.join(keywords)
        
        # Search Brave for current web content
        if self.brave_search:
            brave_results = self.search_brave(search_query, max_results=max_results)
            results['brave_search'] = brave_results
            results['total_found'] += len(brave_results)

        if MULTI_ENGINE_SEARCH_AVAILABLE:
            multi_engine_results = search_multi_engine_web(
                query=search_query,
                max_results=max_results,
            )
            results['multi_engine_search'] = multi_engine_results
            results['total_found'] += len(multi_engine_results)
        
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

        if UNIFIED_WEB_SCRAPER_AVAILABLE and domains:
            for domain in domains[:3]:
                try:
                    archive_results = scrape_archived_domain(domain, max_pages=min(max_results, 5))
                    results['archived_domain_scrape'].extend(archive_results)
                    results['total_found'] += len(archive_results)
                except Exception as e:
                    self.mediator.log('web_evidence_domain_error',
                        domain=domain, error=str(e))
        
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
        elif evidence_item.get('source_type') == 'multi_engine_search':
            validation['relevance_score'] = 0.72
        elif evidence_item.get('source_type') == 'archived_domain_scrape':
            validation['relevance_score'] = 0.68
        elif evidence_item.get('source_type') == 'web_scrape':
            validation['relevance_score'] = 0.66
        
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
        self._search_hook = None

    def _aggregate_graph_support_metrics(self, tasks: List[Dict[str, Any]]) -> Dict[str, int]:
        semantic_cluster_count = 0
        semantic_duplicate_count = 0
        for task in tasks:
            graph_summary = (task.get('graph_support') or {}).get('summary', {})
            semantic_cluster_count += int(graph_summary.get('semantic_cluster_count', 0) or 0)
            semantic_duplicate_count += int(graph_summary.get('semantic_duplicate_count', 0) or 0)
        return {
            'semantic_cluster_count': semantic_cluster_count,
            'semantic_duplicate_count': semantic_duplicate_count,
        }

    def _summarize_follow_up_plan_claim(self, claim_plan: Dict[str, Any]) -> Dict[str, Any]:
        tasks = claim_plan.get('tasks', []) if isinstance(claim_plan, dict) else []
        recommended_actions: Dict[str, int] = {}
        for task in tasks:
            action = str(task.get('recommended_action') or 'unspecified')
            recommended_actions[action] = recommended_actions.get(action, 0) + 1
        graph_support_metrics = self._aggregate_graph_support_metrics(tasks)
        return {
            'task_count': len(tasks),
            'blocked_task_count': claim_plan.get('blocked_task_count', 0),
            'graph_supported_task_count': len([task for task in tasks if task.get('has_graph_support')]),
            'suppressed_task_count': len([task for task in tasks if task.get('should_suppress_retrieval')]),
            'semantic_cluster_count': graph_support_metrics['semantic_cluster_count'],
            'semantic_duplicate_count': graph_support_metrics['semantic_duplicate_count'],
            'recommended_actions': recommended_actions,
        }

    def _summarize_follow_up_execution_claim(self, claim_execution: Dict[str, Any]) -> Dict[str, Any]:
        executed_tasks = claim_execution.get('tasks', []) if isinstance(claim_execution, dict) else []
        skipped_tasks = claim_execution.get('skipped_tasks', []) if isinstance(claim_execution, dict) else []
        suppressed = [task for task in skipped_tasks if 'suppressed' in task.get('skipped', {})]
        cooldown_skips = [
            task for task in skipped_tasks
            if any(value.get('reason') == 'duplicate_within_cooldown' for value in task.get('skipped', {}).values() if isinstance(value, dict))
        ]
        graph_support_metrics = self._aggregate_graph_support_metrics(executed_tasks + skipped_tasks)
        return {
            'executed_task_count': len(executed_tasks),
            'skipped_task_count': len(skipped_tasks),
            'suppressed_task_count': len(suppressed),
            'cooldown_skipped_task_count': len(cooldown_skips),
            'semantic_cluster_count': graph_support_metrics['semantic_cluster_count'],
            'semantic_duplicate_count': graph_support_metrics['semantic_duplicate_count'],
        }

    def _summarize_claim_coverage_claim(
        self,
        claim_type: str,
        coverage_claim: Dict[str, Any],
        overview_claim: Dict[str, Any] = None,
        gap_claim: Dict[str, Any] = None,
        contradiction_claim: Dict[str, Any] = None,
        validation_claim: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        if not isinstance(coverage_claim, dict):
            coverage_claim = {}
        if not isinstance(overview_claim, dict):
            overview_claim = {}
        if not isinstance(gap_claim, dict):
            gap_claim = {}
        if not isinstance(contradiction_claim, dict):
            contradiction_claim = {}
        if not isinstance(validation_claim, dict):
            validation_claim = {}
        reasoning_summary = (
            (validation_claim.get('proof_diagnostics') or {}).get('reasoning', {})
            if isinstance(validation_claim.get('proof_diagnostics'), dict)
            else {}
        )
        elements = coverage_claim.get('elements', []) if isinstance(coverage_claim.get('elements', []), list) else []
        if elements:
            missing_elements = [
                element.get('element_text')
                for element in elements
                if element.get('status') == 'missing' and element.get('element_text')
            ]
            partially_supported_elements = [
                element.get('element_text')
                for element in elements
                if element.get('status') == 'partially_supported' and element.get('element_text')
            ]
        else:
            missing_elements = [
                element.get('element_text')
                for element in overview_claim.get('missing', [])
                if isinstance(element, dict) and element.get('element_text')
            ]
            partially_supported_elements = [
                element.get('element_text')
                for element in overview_claim.get('partially_supported', [])
                if isinstance(element, dict) and element.get('element_text')
            ]
        unresolved_elements = []
        recommended_gap_actions: Dict[str, int] = {}
        for element in gap_claim.get('unresolved_elements', []):
            if not isinstance(element, dict):
                continue
            element_text = element.get('element_text')
            if element_text:
                unresolved_elements.append(element_text)
            action = str(element.get('recommended_action') or 'unspecified')
            recommended_gap_actions[action] = recommended_gap_actions.get(action, 0) + 1
        contradicted_elements = []
        contradiction_candidate_count = int(contradiction_claim.get('candidate_count', 0) or 0)
        seen_contradicted_elements = set()
        for candidate in contradiction_claim.get('candidates', []):
            if not isinstance(candidate, dict):
                continue
            element_text = candidate.get('claim_element_text')
            if element_text and element_text not in seen_contradicted_elements:
                seen_contradicted_elements.add(element_text)
                contradicted_elements.append(element_text)
        traced_link_count = 0
        snapshot_created_count = 0
        snapshot_reused_count = 0
        source_table_counts: Dict[str, int] = {}
        graph_status_counts: Dict[str, int] = {}
        graph_id_count = 0
        seen_graph_ids = set()
        for element in elements:
            if not isinstance(element, dict):
                continue
            for link in element.get('links', []):
                if not isinstance(link, dict):
                    continue
                graph_trace = link.get('graph_trace', {})
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
                    if graph_id and graph_id not in seen_graph_ids:
                        seen_graph_ids.add(graph_id)
                        graph_id_count += 1
        return {
            'claim_type': claim_type,
            'validation_status': validation_claim.get('validation_status', ''),
            'validation_status_counts': validation_claim.get('validation_status_counts', {}),
            'proof_gap_count': int(validation_claim.get('proof_gap_count', 0) or 0),
            'elements_requiring_follow_up': validation_claim.get('elements_requiring_follow_up', []),
            'reasoning_adapter_status_counts': reasoning_summary.get('adapter_status_counts', {}),
            'reasoning_backend_available_count': int(reasoning_summary.get('backend_available_count', 0) or 0),
            'reasoning_predicate_count': int(reasoning_summary.get('predicate_count', 0) or 0),
            'reasoning_ontology_entity_count': int(reasoning_summary.get('ontology_entity_count', 0) or 0),
            'reasoning_ontology_relationship_count': int(reasoning_summary.get('ontology_relationship_count', 0) or 0),
            'reasoning_fallback_ontology_count': int(reasoning_summary.get('fallback_ontology_count', 0) or 0),
            'total_elements': coverage_claim.get('total_elements', 0),
            'total_links': coverage_claim.get('total_links', 0),
            'total_facts': coverage_claim.get('total_facts', 0),
            'support_by_kind': coverage_claim.get('support_by_kind', {}),
            'support_trace_summary': coverage_claim.get('support_trace_summary', {}),
            'status_counts': coverage_claim.get(
                'status_counts',
                {'covered': 0, 'partially_supported': 0, 'missing': 0},
            ),
            'missing_elements': missing_elements,
            'partially_supported_elements': partially_supported_elements,
            'unresolved_element_count': int(gap_claim.get('unresolved_count', 0) or 0),
            'unresolved_elements': unresolved_elements,
            'recommended_gap_actions': recommended_gap_actions,
            'contradiction_candidate_count': contradiction_candidate_count,
            'contradicted_elements': contradicted_elements,
            'graph_trace_summary': {
                'traced_link_count': traced_link_count,
                'snapshot_created_count': snapshot_created_count,
                'snapshot_reused_count': snapshot_reused_count,
                'source_table_counts': source_table_counts,
                'graph_status_counts': graph_status_counts,
                'graph_id_count': graph_id_count,
            },
        }
    
    def _get_search_hook(self):
        """Lazy initialization of search hook."""
        if self._search_hook is None:
            if hasattr(self.mediator, 'web_evidence_search'):
                self._search_hook = self.mediator.web_evidence_search
            else:
                self._search_hook = WebEvidenceSearchHook(self.mediator)
        return self._search_hook

    def _build_web_evidence_payload(self, evidence_item: Dict[str, Any]) -> bytes:
        """Build a text payload so web evidence can be chunked and indexed like uploaded documents."""
        sections: List[str] = []
        title = str(evidence_item.get('title') or '').strip()
        url = str(evidence_item.get('url') or '').strip()
        description = str(evidence_item.get('description') or '').strip()
        content = str(evidence_item.get('content') or '').strip()

        if title:
            sections.append(f"Title: {title}")
        if url:
            sections.append(f"URL: {url}")
        if description:
            sections.append(f"Description: {description}")
        if content:
            sections.append("Content:")
            sections.append(content)

        if not sections:
            sections.append(json.dumps(evidence_item, sort_keys=True))

        return "\n\n".join(sections).encode('utf-8', errors='ignore')

    def _build_web_evidence_filename(self, evidence_item: Dict[str, Any]) -> str:
        """Create a stable filename-like label for document parsing metadata."""
        title = str(evidence_item.get('title') or '').strip().lower()
        slug = re.sub(r'[^a-z0-9]+', '-', title).strip('-')
        if not slug:
            slug = 'web-evidence'
        return f"{slug}.txt"

    def _extract_parse_detail(self, storage_result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parse metadata from stored web evidence for reporting."""
        metadata = storage_result.get('metadata', {}) if isinstance(storage_result.get('metadata'), dict) else {}
        parse_contract = metadata.get('document_parse_contract') if isinstance(metadata.get('document_parse_contract'), dict) else {}
        if not parse_contract:
            parse_contract = build_document_parse_contract(
                storage_result.get('document_parse') if isinstance(storage_result.get('document_parse'), dict) else {},
                default_source=str(metadata.get('parse_source') or 'web_document'),
            )
        parse_summary = parse_contract.get('summary', {}) if isinstance(parse_contract.get('summary'), dict) else {}
        return {
            'cid': storage_result.get('cid', ''),
            'status': parse_contract.get('status', ''),
            'source': parse_contract.get('source', ''),
            'chunk_count': int(parse_contract.get('chunk_count', 0) or 0),
            'text_length': int(parse_summary.get('text_length', 0) or 0),
            'parser_version': parse_summary.get('parser_version', ''),
            'input_format': parse_summary.get('input_format', ''),
            'paragraph_count': int(parse_summary.get('paragraph_count', 0) or 0),
            'lineage': parse_contract.get('lineage', {}) if isinstance(parse_contract.get('lineage'), dict) else {},
        }

    def _accumulate_parse_detail(self, aggregate: Dict[str, Any], detail: Dict[str, Any]) -> None:
        """Accumulate parse detail into request-level web evidence parse stats."""
        aggregate['processed'] += 1
        aggregate['total_chunks'] += detail.get('chunk_count', 0)
        aggregate['total_paragraphs'] += detail.get('paragraph_count', 0)
        aggregate['total_text_length'] += detail.get('text_length', 0)

        status = detail.get('status', '')
        if status:
            aggregate['status_counts'][status] = aggregate['status_counts'].get(status, 0) + 1

        input_format = detail.get('input_format', '')
        if input_format:
            aggregate['input_format_counts'][input_format] = aggregate['input_format_counts'].get(input_format, 0) + 1

        parser_version = detail.get('parser_version', '')
        if parser_version and parser_version not in aggregate['parser_versions']:
            aggregate['parser_versions'].append(parser_version)

    def _empty_storage_summary(self, discovered_count: int = 0) -> Dict[str, Any]:
        return {
            'discovered': discovered_count,
            'validated': 0,
            'stored': 0,
            'stored_new': 0,
            'reused': 0,
            'skipped': 0,
            'total_records': 0,
            'total_new': 0,
            'total_reused': 0,
            'evidence_cids': [],
            'support_links_added': 0,
            'support_links_reused': 0,
            'total_support_links_added': 0,
            'total_support_links_reused': 0,
            'parse_details': [],
            'parse_summary': {
                'processed': 0,
                'total_chunks': 0,
                'total_paragraphs': 0,
                'total_text_length': 0,
                'status_counts': {},
                'input_format_counts': {},
                'parser_versions': [],
            },
        }

    def _store_evidence_items(self,
                              evidence_items: List[Dict[str, Any]],
                              *,
                              keywords: List[str],
                              user_id: str,
                              claim_type: Optional[str],
                              min_relevance: float) -> Dict[str, Any]:
        stored_evidence = self._empty_storage_summary(discovered_count=len(evidence_items))
        seen_urls = set()

        for evidence_item in evidence_items:
            evidence_url = evidence_item.get('url')
            if evidence_url and evidence_url in seen_urls:
                continue
            if evidence_url:
                seen_urls.add(evidence_url)

            source_type = evidence_item.get('source_type')
            if source_type in {'brave_search', 'multi_engine_search'} and evidence_url:
                scraped = scrape_web_content(evidence_url)
                if scraped.get('success') and scraped.get('content'):
                    evidence_item = {
                        **evidence_item,
                        'content': scraped.get('content') or evidence_item.get('content', ''),
                        'description': evidence_item.get('description') or scraped.get('description', ''),
                        'metadata': {
                            **(evidence_item.get('metadata', {}) if isinstance(evidence_item.get('metadata'), dict) else {}),
                            'original_source_type': source_type,
                            'scrape': scraped.get('metadata', {}),
                            'scrape_errors': scraped.get('errors', []),
                        },
                    }

            validation = self.mediator.web_evidence_search.validate_evidence(evidence_item)

            if not validation['valid']:
                stored_evidence['skipped'] += 1
                continue

            stored_evidence['validated'] += 1

            if validation['relevance_score'] < min_relevance:
                stored_evidence['skipped'] += 1
                continue

            try:
                evidence_data = self._build_web_evidence_payload(evidence_item)

                storage_result = self.mediator.evidence_storage.store_evidence(
                    data=evidence_data,
                    evidence_type='web_document',
                    metadata={
                        'source_type': evidence_item.get('source_type'),
                        'source_url': evidence_item.get('url'),
                        'acquisition_method': 'web_discovery',
                        'source_system': 'ipfs_datasets_py',
                        'filename': self._build_web_evidence_filename(evidence_item),
                        'mime_type': 'text/plain',
                        'parse_source': 'web_document',
                        'parse_document': True,
                        'auto_discovered': True,
                        'relevance_score': validation['relevance_score'],
                        'keywords': keywords,
                        'title': evidence_item.get('title', ''),
                        'description': evidence_item.get('description', ''),
                        'discovered_at': evidence_item.get('discovered_at', ''),
                        'search_metadata': evidence_item.get('metadata', {}),
                    }
                )

                resolved_element = {'claim_element_id': None, 'claim_element_text': None}
                if claim_type and hasattr(self.mediator, 'claim_support'):
                    resolved_element = self.mediator.claim_support.resolve_claim_element(
                        user_id,
                        claim_type,
                        support_label=evidence_item.get('title') or evidence_item.get('url'),
                        metadata={
                            'source_url': evidence_item.get('url'),
                            'title': evidence_item.get('title'),
                            'description': evidence_item.get('description') or evidence_item.get('content'),
                            'content_excerpt': evidence_item.get('content'),
                            'keywords': keywords,
                        },
                    )

                record_result = self.mediator.evidence_state.upsert_evidence_record(
                    user_id=user_id,
                    evidence_info=storage_result,
                    description=f"Auto-discovered: {evidence_item.get('title', 'Web evidence')}",
                    claim_type=claim_type,
                    claim_element_id=resolved_element.get('claim_element_id') if claim_type and hasattr(self.mediator, 'claim_support') else None,
                    claim_element=resolved_element.get('claim_element_text') if claim_type and hasattr(self.mediator, 'claim_support') else None,
                )
                record_id = record_result['record_id']
                support_link_result = {'created': False, 'reused': False}

                if claim_type and hasattr(self.mediator, 'claim_support'):
                    support_link_result = self.mediator.claim_support.upsert_support_link(
                        user_id=user_id,
                        complaint_id=getattr(self.mediator.state, 'complaint_id', None),
                        claim_type=claim_type,
                        claim_element_id=resolved_element.get('claim_element_id'),
                        claim_element_text=resolved_element.get('claim_element_text'),
                        support_kind='evidence',
                        support_ref=storage_result['cid'],
                        support_label=evidence_item.get('title') or evidence_item.get('url') or 'Web evidence',
                        source_table='evidence',
                        support_strength=float(validation['relevance_score']),
                        metadata={
                            'record_id': record_id,
                            'source_url': evidence_item.get('url'),
                            'source_type': evidence_item.get('source_type', 'web'),
                            'keywords': keywords,
                            'auto_discovered': True,
                        },
                    )
                    stored_evidence['support_links_added'] += 1 if support_link_result.get('created') else 0
                    stored_evidence['support_links_reused'] += 1 if support_link_result.get('reused') else 0

                stored_evidence['stored'] += 1
                stored_evidence['stored_new'] += 1 if record_result.get('created') else 0
                stored_evidence['reused'] += 1 if record_result.get('reused') else 0
                stored_evidence['total_records'] += 1
                stored_evidence['total_new'] += 1 if record_result.get('created') else 0
                stored_evidence['total_reused'] += 1 if record_result.get('reused') else 0
                stored_evidence['total_support_links_added'] += 1 if support_link_result.get('created') else 0
                stored_evidence['total_support_links_reused'] += 1 if support_link_result.get('reused') else 0
                stored_evidence['evidence_cids'].append(storage_result['cid'])

                parse_detail = self._extract_parse_detail(storage_result)
                stored_evidence['parse_details'].append(parse_detail)
                self._accumulate_parse_detail(stored_evidence['parse_summary'], parse_detail)

                current_kg = None
                if hasattr(self.mediator, 'phase_manager'):
                    from complaint_phases import ComplaintPhase
                    current_kg = self.mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
                if hasattr(self.mediator, 'add_evidence_to_graphs') and current_kg:
                    graph_result = self.mediator.add_evidence_to_graphs({
                        **storage_result,
                        'record_id': record_id,
                        'record_created': record_result.get('created', False),
                        'record_reused': record_result.get('reused', False),
                        'support_link_created': support_link_result.get('created', False),
                        'support_link_reused': support_link_result.get('reused', False),
                        'name': evidence_item.get('title') or evidence_item.get('url') or 'Web evidence',
                        'description': evidence_item.get('description') or evidence_item.get('content') or '',
                        'claim_type': claim_type,
                        'claim_element_id': resolved_element.get('claim_element_id'),
                        'claim_element': resolved_element.get('claim_element_text'),
                        'confidence': float(validation['relevance_score']),
                    })
                    stored_evidence.setdefault('graph_projection', []).append(graph_result.get('graph_projection', {}))

                self.mediator.log('web_evidence_stored',
                    cid=storage_result['cid'],
                    url=evidence_item.get('url'),
                    relevance=validation['relevance_score'])

            except Exception as e:
                self.mediator.log('web_evidence_storage_error',
                    url=evidence_item.get('url'), error=str(e))
                stored_evidence['skipped'] += 1

        return stored_evidence

    def _seed_daemon_tactics(self, user_id: str) -> Optional[List[ScraperTactic]]:
        """Seed daemon tactic weights from recent persisted scraper performance."""
        evidence_state = getattr(self.mediator, 'evidence_state', None)
        if evidence_state is None or not hasattr(evidence_state, 'get_scraper_tactic_performance'):
            return None

        performance = evidence_state.get_scraper_tactic_performance(user_id=user_id, limit_runs=10)
        tactic_rows = performance.get('tactics', []) if isinstance(performance, dict) else []
        if not tactic_rows:
            return None

        default_tactics = {
            tactic.name: tactic
            for tactic in [
                ScraperTactic(
                    name='multi_engine_search',
                    mode='multi_engine_search',
                    query_template='{keywords}',
                    max_results=5,
                    scrape_top_results=True,
                    weight=1.2,
                ),
                ScraperTactic(
                    name='brave_search_fresh',
                    mode='brave_search',
                    query_template='{keywords}',
                    max_results=5,
                    freshness='pw',
                    scrape_top_results=True,
                    weight=1.0,
                ),
                ScraperTactic(
                    name='domain_archive_sweep',
                    mode='archived_domain_scrape',
                    max_results=5,
                    weight=0.9,
                ),
            ]
        }
        seeded: List[ScraperTactic] = []
        for tactic_name, tactic in default_tactics.items():
            learned = next((row for row in tactic_rows if row.get('name') == tactic_name), None)
            if learned is None:
                seeded.append(tactic)
                continue

            learned_weight = float(learned.get('avg_weight', tactic.weight) or tactic.weight)
            quality_bonus = 0.15 if float(learned.get('avg_quality_score', 0.0) or 0.0) >= 60.0 else -0.05
            novelty_bonus = min(0.2, float(learned.get('novelty_ratio', 0.0) or 0.0) * 0.2)
            seeded.append(
                ScraperTactic(
                    name=tactic.name,
                    mode=tactic.mode,
                    query_template=tactic.query_template,
                    max_results=tactic.max_results,
                    freshness=tactic.freshness,
                    scrape_top_results=tactic.scrape_top_results,
                    weight=max(0.1, round(learned_weight + quality_bonus + novelty_bonus, 2)),
                )
            )
        return sorted(seeded, key=lambda tactic: tactic.weight, reverse=True)
    
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

        all_results = (
            search_results.get('brave_search', []) +
            search_results.get('common_crawl', []) +
            search_results.get('multi_engine_search', []) +
            search_results.get('archived_domain_scrape', [])
        )

        stored_evidence = self._store_evidence_items(
            all_results,
            keywords=keywords,
            user_id=user_id,
            claim_type=claim_type,
            min_relevance=min_relevance,
        )
        stored_evidence['discovered'] = search_results['total_found']
        
        self.mediator.log('web_evidence_discovery_complete',
            discovered=stored_evidence['discovered'],
            stored=stored_evidence['stored'])
        
        return stored_evidence

    def run_agentic_scraper_cycle(self,
                                  keywords: List[str],
                                  domains: Optional[List[str]] = None,
                                  iterations: int = 1,
                                  sleep_seconds: float = 0.0,
                                  quality_domain: str = 'caselaw',
                                  user_id: Optional[str] = None,
                                  claim_type: Optional[str] = None,
                                  min_relevance: float = 0.5,
                                  store_results: bool = True) -> Dict[str, Any]:
        """Run the agentic scraper loop for a bounded number of iterations."""
        if user_id is None:
            user_id = getattr(self.mediator.state, 'username', None) or \
                     getattr(self.mediator.state, 'hashed_username', 'anonymous')

        daemon = ScraperDaemon(
            config=ScraperDaemonConfig(
                iterations=iterations,
                sleep_seconds=sleep_seconds,
                quality_domain=quality_domain,
            )
        )
        seeded_tactics = self._seed_daemon_tactics(user_id)
        daemon_result = daemon.run(keywords=keywords, domains=domains, tactics=seeded_tactics)
        final_results = list(daemon_result.get('final_results', []) or [])
        storage_summary = self._empty_storage_summary(discovered_count=len(final_results))
        if store_results and final_results:
            storage_summary = self._store_evidence_items(
                final_results,
                keywords=keywords,
                user_id=user_id,
                claim_type=claim_type,
                min_relevance=min_relevance,
            )

        persistence = {'persisted': False, 'run_id': -1}
        if hasattr(self.mediator, 'evidence_state') and hasattr(self.mediator.evidence_state, 'persist_scraper_run'):
            persistence = self.mediator.evidence_state.persist_scraper_run(
                user_id=user_id,
                run_result=daemon_result,
                keywords=keywords,
                domains=domains,
                claim_type=claim_type,
                stored_summary=storage_summary,
                config={
                    'iterations': iterations,
                    'sleep_seconds': sleep_seconds,
                    'quality_domain': quality_domain,
                    'min_relevance': min_relevance,
                    'store_results': store_results,
                },
            )

        return {
            **daemon_result,
            'storage_summary': storage_summary,
            'scraper_run': persistence,
            'seeded_tactics': [
                {
                    'name': tactic.name,
                    'mode': tactic.mode,
                    'weight': tactic.weight,
                }
                for tactic in (seeded_tactics or [])
            ],
        }
    
    def discover_evidence_for_case(self, user_id: Optional[str] = None,
                                  execute_follow_up: bool = False) -> Dict[str, Any]:
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
            'evidence_stored': {},
            'evidence_storage_summary': {},
            'support_summary': {},
            'claim_coverage_summary': {},
            'claim_support_gaps': {},
            'claim_contradiction_candidates': {},
            'claim_support_validation': {},
            'claim_support_snapshots': {},
            'claim_support_snapshot_summary': {},
            'claim_overview': {},
            'follow_up_plan': {},
            'follow_up_plan_summary': {},
            'follow_up_execution': {},
            'follow_up_execution_summary': {},
            'claim_coverage_matrix': {},
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
            results['evidence_storage_summary'][claim_type] = discovery_result
            if hasattr(self.mediator, 'summarize_claim_support'):
                support_summary = self.mediator.summarize_claim_support(user_id, claim_type)
                results['support_summary'][claim_type] = support_summary.get('claims', {}).get(
                    claim_type,
                    {
                        'total_links': 0,
                        'support_by_kind': {},
                        'links': [],
                    },
                )
            if hasattr(self.mediator, 'get_claim_overview'):
                claim_overview = self.mediator.get_claim_overview(claim_type=claim_type, user_id=user_id)
                results['claim_overview'][claim_type] = claim_overview.get('claims', {}).get(
                    claim_type,
                    {
                        'required_support_kinds': ['evidence', 'authority'],
                        'covered': [],
                        'partially_supported': [],
                        'missing': [],
                        'covered_count': 0,
                        'partially_supported_count': 0,
                        'missing_count': 0,
                        'total_elements': 0,
                    },
                )
            if hasattr(self.mediator, 'get_claim_coverage_matrix'):
                coverage_matrix = self.mediator.get_claim_coverage_matrix(claim_type=claim_type, user_id=user_id)
                results['claim_coverage_matrix'][claim_type] = coverage_matrix.get('claims', {}).get(
                    claim_type,
                    {
                        'claim_type': claim_type,
                        'required_support_kinds': ['evidence', 'authority'],
                        'total_elements': 0,
                        'status_counts': {
                            'covered': 0,
                            'partially_supported': 0,
                            'missing': 0,
                        },
                        'total_links': 0,
                        'total_facts': 0,
                        'support_by_kind': {},
                        'elements': [],
                        'unassigned_links': [],
                    },
                )
            if hasattr(self.mediator, 'get_claim_support_gaps'):
                claim_support_gaps = self.mediator.get_claim_support_gaps(claim_type=claim_type, user_id=user_id)
                results['claim_support_gaps'][claim_type] = claim_support_gaps.get('claims', {}).get(
                    claim_type,
                    {
                        'claim_type': claim_type,
                        'required_support_kinds': ['evidence', 'authority'],
                        'unresolved_count': 0,
                        'unresolved_elements': [],
                    },
                )
            if hasattr(self.mediator, 'get_claim_contradiction_candidates'):
                claim_contradictions = self.mediator.get_claim_contradiction_candidates(claim_type=claim_type, user_id=user_id)
                results['claim_contradiction_candidates'][claim_type] = claim_contradictions.get('claims', {}).get(
                    claim_type,
                    {
                        'claim_type': claim_type,
                        'candidate_count': 0,
                        'candidates': [],
                    },
                )
            if hasattr(self.mediator, 'get_claim_support_validation'):
                claim_validation = self.mediator.get_claim_support_validation(claim_type=claim_type, user_id=user_id)
                results['claim_support_validation'][claim_type] = claim_validation.get('claims', {}).get(
                    claim_type,
                    {
                        'claim_type': claim_type,
                        'validation_status': 'missing',
                        'validation_status_counts': {
                            'supported': 0,
                            'incomplete': 0,
                            'missing': 0,
                            'contradicted': 0,
                        },
                        'proof_gap_count': 0,
                        'proof_gaps': [],
                        'elements': [],
                    },
                )
            if hasattr(self.mediator, 'persist_claim_support_diagnostics'):
                persisted_diagnostics = self.mediator.persist_claim_support_diagnostics(
                    claim_type=claim_type,
                    user_id=user_id,
                    required_support_kinds=['evidence', 'authority'],
                    gaps={'claims': {claim_type: results['claim_support_gaps'].get(claim_type, {})}},
                    contradictions={'claims': {claim_type: results['claim_contradiction_candidates'].get(claim_type, {})}},
                    metadata={'source': 'discover_evidence_for_case'},
                )
                results['claim_support_snapshots'][claim_type] = persisted_diagnostics.get('claims', {}).get(
                    claim_type,
                    {},
                ).get('snapshots', {})
                results['claim_support_snapshot_summary'][claim_type] = summarize_claim_support_snapshot_lifecycle(
                    results['claim_support_snapshots'][claim_type]
                )
            if hasattr(self.mediator, 'get_claim_follow_up_plan'):
                follow_up_plan = self.mediator.get_claim_follow_up_plan(claim_type=claim_type, user_id=user_id)
                claim_plan = follow_up_plan.get('claims', {}).get(
                    claim_type,
                    {
                        'task_count': 0,
                        'tasks': [],
                    },
                )
                results['follow_up_plan'][claim_type] = claim_plan
                results['follow_up_plan_summary'][claim_type] = self._summarize_follow_up_plan_claim(claim_plan)
            if execute_follow_up and hasattr(self.mediator, 'execute_claim_follow_up_plan'):
                follow_up_execution = self.mediator.execute_claim_follow_up_plan(
                    claim_type=claim_type,
                    user_id=user_id,
                    support_kind='evidence',
                )
                claim_execution = follow_up_execution.get('claims', {}).get(
                    claim_type,
                    {
                        'task_count': 0,
                        'tasks': [],
                    },
                )
                results['follow_up_execution'][claim_type] = claim_execution
                results['follow_up_execution_summary'][claim_type] = self._summarize_follow_up_execution_claim(claim_execution)
            results['claim_coverage_summary'][claim_type] = self._summarize_claim_coverage_claim(
                claim_type,
                results['claim_coverage_matrix'].get(claim_type, {}),
                results['claim_overview'].get(claim_type, {}),
                results['claim_support_gaps'].get(claim_type, {}),
                results['claim_contradiction_candidates'].get(claim_type, {}),
                results['claim_support_validation'].get(claim_type, {}),
            )
        
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
