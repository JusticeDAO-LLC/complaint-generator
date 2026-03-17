"""
Legal Corpus RAG Hooks for Mediator

This module provides hooks for RAG (Retrieval-Augmented Generation) over the legal corpus:
1. Search legal patterns and keywords from complaint_analysis
2. Retrieve relevant laws and regulations
3. Enrich decision trees with legal knowledge
4. Support legal research during mediation
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from mediator.state import extract_chat_history_context_strings_from_state

from .integrations import (
    IPFSDatasetsAdapter,
    IntegrationFeatureFlags,
    RetrievalOrchestrator,
    VectorRetrievalAugmentor,
    GraphAwareRetrievalReranker,
)

logger = logging.getLogger(__name__)

try:
    from complaint_analysis.keywords import get_type_specific_keywords
    from complaint_analysis.legal_patterns import get_legal_terms, COMPLAINT_LEGAL_TERMS
    from complaint_analysis.complaint_types import get_registered_types, get_complaint_type
    COMPLAINT_ANALYSIS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"complaint_analysis not available: {e}")
    COMPLAINT_ANALYSIS_AVAILABLE = False


class LegalCorpusRAGHook:
    """
    Hook for RAG over legal corpus using complaint_analysis data.
    
    Provides methods to:
    - Search legal patterns and keywords
    - Retrieve relevant laws and regulations
    - Enrich decision trees with legal knowledge
    - Support legal research during mediation
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        self.integration_flags = IntegrationFeatureFlags.from_env()
        self.integration_adapter = IPFSDatasetsAdapter(feature_flags=self.integration_flags)
        self.retrieval_orchestrator = RetrievalOrchestrator()
        self.vector_augmentor = VectorRetrievalAugmentor()
        self.graph_reranker = GraphAwareRetrievalReranker()
        self._init_legal_corpus()

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
                record={
                    'title': record.get('content', ''),
                    'content': record.get('content', ''),
                    'snippet': record.get('content', ''),
                    'score': record.get('score', 0.0),
                    'metadata': {
                        'type': record.get('type'),
                        'source': record.get('source'),
                        'complaint_type': record.get('complaint_type'),
                    },
                },
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
        complaint_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.retrieval_orchestrator.build_query_context(
            query=query,
            complaint_type=complaint_type,
            claim_type=complaint_type,
            max_queries=4,
        )

    def _build_evidence_context(
        self,
        query: str,
        complaint_type: Optional[str] = None,
    ) -> List[str]:
        context: List[str] = []

        def _add(value: Any):
            text = str(value or '').strip()
            if text and text not in context:
                context.append(text)

        _add(query)
        _add(complaint_type)

        state = getattr(self.mediator, 'state', None)
        if state is None:
            return context[:8]

        for attr in ('complaint_summary', 'original_complaint', 'complaint', 'last_message'):
            _add(getattr(state, attr, None))

        for value in extract_chat_history_context_strings_from_state(state, limit=3):
            _add(value)

        return context[:8]

    def _dedupe_raw_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        anonymous_count = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            key = str(
                record.get('content')
                or record.get('title')
                or record.get('citation')
                or f'anonymous:{anonymous_count}'
            ).strip().lower()
            anonymous_count += 1
            existing = merged.get(key)
            if existing is None or float(record.get('score', 0.0) or 0.0) > float(existing.get('score', 0.0) or 0.0):
                merged[key] = record
        return list(merged.values())

    def search_legal_corpus_bundle(
        self,
        query: str,
        complaint_type: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """Return raw legal corpus results plus optional normalized/reranked results."""
        query_context = self._build_query_context(query=query, complaint_type=complaint_type)
        evidence_context = self._build_evidence_context(query=query, complaint_type=complaint_type)

        raw = self.search_legal_corpus(
            query=query,
            complaint_type=complaint_type,
            max_results=max_results,
        )

        if self.integration_flags.enhanced_search or self.integration_flags.enhanced_legal:
            expanded_raw: List[Dict[str, Any]] = []
            for subquery in list(query_context.get('queries', []) or [query])[:3]:
                expanded_raw.extend(self.search_legal_corpus(
                    query=subquery,
                    complaint_type=complaint_type,
                    max_results=max_results,
                ))
            raw = self._dedupe_raw_records(expanded_raw)

        bundle: Dict[str, Any] = {
            'query': query,
            'complaint_type': complaint_type,
            'raw': raw,
        }

        if self.integration_flags.enhanced_search or self.integration_flags.enhanced_legal:
            normalized = self._normalize_records(
                records=raw,
                query=query,
                source_type='legal_corpus',
                source_name='complaint_analysis',
            )

            if self.integration_flags.enhanced_vector:
                normalized = self.vector_augmentor.augment_normalized_records(
                    records=normalized,
                    query=query,
                    context_texts=evidence_context,
                )
                self.mediator.log(
                    'legal_corpus_vector_augmentation',
                    query=query,
                    records=len(normalized),
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
                    seed=f"legal_corpus|{query}",
                    percent=self.integration_flags.reranker_canary_percent,
                )
                if canary_enabled:
                    normalized = self.graph_reranker.augment_normalized_records(
                        records=normalized,
                        query=query,
                        mediator=self.mediator,
                        enable_optimizer=self.integration_flags.enhanced_optimizer,
                        retrieval_max_latency_ms=self.integration_flags.retrieval_max_latency_ms,
                    )
                    sample_metadata = dict((normalized[0] if normalized else {}).get('metadata', {}) or {})
                    self.mediator.log(
                        'legal_corpus_graph_reranking',
                        query=query,
                        records=len(normalized),
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
                            source='legal_corpus',
                            applied=True,
                            metadata=sample_metadata,
                            canary_enabled=canary_enabled,
                            window_size=self.integration_flags.reranker_metrics_window,
                        )
                else:
                    self.mediator.log(
                        'legal_corpus_graph_reranking_skipped',
                        query=query,
                        reranker_mode=self.integration_flags.reranker_mode,
                        reranker_canary_percent=self.integration_flags.reranker_canary_percent,
                        canary_enabled=canary_enabled,
                    )
                    if hasattr(self.mediator, 'update_reranker_metrics'):
                        self.mediator.update_reranker_metrics(
                            source='legal_corpus',
                            applied=False,
                            metadata={},
                            canary_enabled=canary_enabled,
                            window_size=self.integration_flags.reranker_metrics_window,
                        )

            bundle['normalized'] = self._merge_rank_normalized(
                normalized_records=normalized,
                max_results=max_results,
                query_context=query_context,
            )
            bundle['support_bundle'] = self._build_support_bundle(bundle['normalized'])
            self.mediator.log(
                'legal_corpus_normalized_results',
                query=query,
                complaint_type=complaint_type,
                decomposed_queries=len(query_context.get('queries', []) or []),
                raw_total=len(raw),
                normalized_total=len(bundle['normalized']),
                enhanced_search=self.integration_flags.enhanced_search,
                enhanced_legal=self.integration_flags.enhanced_legal,
            )

        return bundle
        
    def _init_legal_corpus(self):
        """Initialize legal corpus from complaint_analysis."""
        if not COMPLAINT_ANALYSIS_AVAILABLE:
            self.mediator.log('legal_corpus_warning',
                message='complaint_analysis not available - legal corpus limited')
            self.legal_patterns = []
            self.legal_terms = []
            return
        
        # Load legal patterns and terms
        try:
            self.legal_patterns = COMPLAINT_LEGAL_TERMS if COMPLAINT_LEGAL_TERMS else []
            self.legal_terms = get_legal_terms()
            
            self.mediator.log('legal_corpus_init',
                message=f'Initialized legal corpus with {len(self.legal_patterns)} patterns, '
                        f'{len(self.legal_terms)} terms')
        except Exception as e:
            self.mediator.log('legal_corpus_error', error=str(e))
            self.legal_patterns = []
            self.legal_terms = []
    
    def search_legal_corpus(self, query: str, complaint_type: Optional[str] = None,
                           max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search the legal corpus for relevant information.
        
        Args:
            query: Search query (keywords, phrases)
            complaint_type: Optional complaint type to scope search
            max_results: Maximum number of results
            
        Returns:
            List of relevant legal patterns, terms, and keywords
        """
        if not COMPLAINT_ANALYSIS_AVAILABLE:
            return []
        
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        # Search legal patterns
        for pattern in self.legal_patterns:
            pattern_lower = pattern.lower()
            # Simple relevance scoring
            score = 0
            if query_lower in pattern_lower:
                score += 10
            common_words = query_words & set(pattern_lower.split())
            score += len(common_words)
            
            if score > 0:
                results.append({
                    'type': 'legal_pattern',
                    'content': pattern,
                    'score': score,
                    'source': 'complaint_legal_terms'
                })
        
        # Search legal terms
        for term in self.legal_terms:
            term_lower = term.lower()
            score = 0
            if query_lower in term_lower or term_lower in query_lower:
                score += 10
            common_words = query_words & set(term_lower.split())
            score += len(common_words)
            
            if score > 0:
                results.append({
                    'type': 'legal_term',
                    'content': term,
                    'score': score,
                    'source': 'legal_terms'
                })
        
        # Search type-specific keywords if complaint_type provided
        if complaint_type:
            try:
                type_info = get_complaint_type(complaint_type)
                if type_info:
                    keywords = get_type_specific_keywords(type_info['category'], complaint_type)
                    for keyword in keywords:
                        keyword_lower = keyword.lower()
                        score = 0
                        if query_lower in keyword_lower or keyword_lower in query_lower:
                            score += 5
                        common_words = query_words & set(keyword_lower.split())
                        score += len(common_words)
                        
                        if score > 0:
                            results.append({
                                'type': 'keyword',
                                'content': keyword,
                                'score': score,
                                'source': f'{complaint_type}_keywords',
                                'complaint_type': complaint_type
                            })
            except Exception as e:
                logger.warning(f"Error searching type-specific keywords: {e}")
        
        # Sort by score and limit results
        results.sort(key=lambda x: x['score'], reverse=True)
        results = results[:max_results]
        
        self.mediator.log('legal_corpus_search',
            query=query, complaint_type=complaint_type, results_count=len(results))
        
        return results
    
    def retrieve_relevant_laws(self, claims: List[str], complaint_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve relevant laws and regulations for given claims.
        
        Args:
            claims: List of legal claims
            complaint_type: Optional complaint type for context
            
        Returns:
            List of relevant legal references
        """
        all_laws = []
        
        for claim in claims:
            results = self.search_legal_corpus(claim, complaint_type)
            for result in results:
                if result['type'] in ['legal_pattern', 'legal_term']:
                    all_laws.append({
                        'claim': claim,
                        'legal_reference': result['content'],
                        'type': result['type'],
                        'relevance_score': result['score'],
                        'source': result['source']
                    })
        
        # Remove duplicates
        seen = set()
        unique_laws = []
        for law in all_laws:
            key = (law['legal_reference'], law['type'])
            if key not in seen:
                seen.add(key)
                unique_laws.append(law)
        
        self.mediator.log('retrieve_laws',
            claims_count=len(claims), laws_count=len(unique_laws))
        
        return unique_laws
    
    def enrich_decision_tree(self, complaint_type: str, tree_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a decision tree with legal corpus knowledge.
        
        Args:
            complaint_type: Type of complaint
            tree_data: Decision tree data structure
            
        Returns:
            Enriched decision tree with legal references
        """
        if not COMPLAINT_ANALYSIS_AVAILABLE:
            return tree_data
        
        enriched = tree_data.copy()
        
        # Get type-specific information
        try:
            type_info = get_complaint_type(complaint_type)
            if not type_info:
                return tree_data
            
            keywords = get_type_specific_keywords(type_info['category'], complaint_type)
            
            # Add legal context to the tree
            enriched['legal_context'] = {
                'keywords': keywords[:20],  # Top 20 keywords
                'legal_patterns': [],
                'relevant_terms': []
            }
            
            # Search for relevant legal patterns
            for keyword in keywords[:10]:  # Use top 10 keywords
                results = self.search_legal_corpus(keyword, complaint_type)
                for result in results[:3]:  # Top 3 results per keyword
                    if result['type'] == 'legal_pattern':
                        if result['content'] not in enriched['legal_context']['legal_patterns']:
                            enriched['legal_context']['legal_patterns'].append(result['content'])
                    elif result['type'] == 'legal_term':
                        if result['content'] not in enriched['legal_context']['relevant_terms']:
                            enriched['legal_context']['relevant_terms'].append(result['content'])
            
            # Enrich individual questions with legal context
            if 'questions' in enriched:
                for qid, question in enriched['questions'].items():
                    if 'keywords' in question and question['keywords']:
                        # Find relevant legal terms for this question
                        question_legal_refs = []
                        for kw in question['keywords'][:3]:
                            results = self.search_legal_corpus(kw, complaint_type)
                            for result in results[:2]:
                                question_legal_refs.append({
                                    'term': result['content'],
                                    'type': result['type']
                                })
                        
                        if question_legal_refs:
                            question['legal_references'] = question_legal_refs
            
            self.mediator.log('decision_tree_enriched',
                complaint_type=complaint_type,
                patterns_count=len(enriched['legal_context']['legal_patterns']),
                terms_count=len(enriched['legal_context']['relevant_terms']))
        
        except Exception as e:
            self.mediator.log('tree_enrichment_error', error=str(e))
        
        return enriched
    
    def get_legal_requirements(self, complaint_type: str) -> Dict[str, Any]:
        """
        Get legal requirements for a complaint type.
        
        Args:
            complaint_type: Type of complaint
            
        Returns:
            Dictionary of legal requirements
        """
        if not COMPLAINT_ANALYSIS_AVAILABLE:
            return {}
        
        try:
            type_info = get_complaint_type(complaint_type)
            if not type_info:
                return {}
            
            keywords = get_type_specific_keywords(type_info['category'], complaint_type)
            
            # Search for requirement-related patterns
            requirement_patterns = []
            requirement_keywords = ['requirement', 'must', 'shall', 'required', 'necessary', 
                                   'element', 'proof', 'establish', 'demonstrate']
            
            for keyword in keywords[:20]:
                for req_kw in requirement_keywords:
                    query = f"{keyword} {req_kw}"
                    results = self.search_legal_corpus(query, complaint_type)
                    for result in results[:2]:
                        if result['type'] == 'legal_pattern':
                            requirement_patterns.append(result['content'])
            
            return {
                'complaint_type': complaint_type,
                'category': type_info['category'],
                'description': type_info['description'],
                'keywords': keywords[:30],
                'requirement_patterns': list(set(requirement_patterns)),
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error getting legal requirements: {e}")
            return {}
    
    def suggest_questions(self, complaint_type: str, existing_questions: List[str]) -> List[Dict[str, str]]:
        """
        Suggest additional questions based on legal corpus analysis.
        
        Args:
            complaint_type: Type of complaint
            existing_questions: Questions already in the decision tree
            
        Returns:
            List of suggested questions with justification
        """
        if not COMPLAINT_ANALYSIS_AVAILABLE:
            return []
        
        suggestions = []
        
        try:
            type_info = get_complaint_type(complaint_type)
            if not type_info:
                return []
            
            keywords = get_type_specific_keywords(type_info['category'], complaint_type)
            
            # Analyze existing questions to find gaps
            existing_lower = ' '.join(existing_questions).lower()
            
            # Check important keywords not covered
            for keyword in keywords[:30]:
                if keyword.lower() not in existing_lower:
                    # This keyword might indicate a gap
                    results = self.search_legal_corpus(keyword, complaint_type)
                    if results:
                        suggestions.append({
                            'question': f"Can you provide details about {keyword}?",
                            'keyword': keyword,
                            'justification': f"Important legal keyword '{keyword}' not covered",
                            'legal_basis': results[0]['content'] if results else None
                        })
            
            # Limit suggestions
            suggestions = suggestions[:10]
            
            self.mediator.log('questions_suggested',
                complaint_type=complaint_type,
                suggestions_count=len(suggestions))
        
        except Exception as e:
            logger.error(f"Error suggesting questions: {e}")
        
        return suggestions
