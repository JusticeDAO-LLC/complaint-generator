"""
Search Hooks for Adversarial Testing

This module provides hooks for integrating search and legal corpus RAG
into the adversarial testing framework:
1. Dynamic seed enrichment using Brave search
2. Decision tree enhancement with search results
3. Legal corpus integration for better question generation
"""

import logging
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from mediator.web_evidence_hooks import WebEvidenceSearchHook, BRAVE_SEARCH_AVAILABLE
    from mediator.legal_corpus_hooks import LegalCorpusRAGHook, COMPLAINT_ANALYSIS_AVAILABLE
    HOOKS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Mediator hooks not available: {e}")
    HOOKS_AVAILABLE = False
    WebEvidenceSearchHook = None
    LegalCorpusRAGHook = None


class SearchEnrichedSeedGenerator:
    """
    Generates enriched seeds using web search and legal corpus.
    
    Takes base seed templates and enriches them with:
    - Real-world examples from Brave search
    - Legal terminology from legal corpus
    - Recent case patterns
    """
    
    def __init__(self, mock_mediator=None):
        """
        Initialize with optional mock mediator for testing.
        
        Args:
            mock_mediator: Mock mediator object for testing (optional)
        """
        self.mock_mediator = mock_mediator or self._create_mock_mediator()
        
        if HOOKS_AVAILABLE:
            self.web_hook = WebEvidenceSearchHook(self.mock_mediator)
            self.legal_hook = LegalCorpusRAGHook(self.mock_mediator)
        else:
            self.web_hook = None
            self.legal_hook = None
    
    def _create_mock_mediator(self):
        """Create a minimal mock mediator for hooks."""
        class MockMediator:
            def __init__(self):
                self.logs = []
            
            def log(self, event_type, **kwargs):
                self.logs.append({'type': event_type, 'data': kwargs})
        
        return MockMediator()
    
    def enrich_seed_with_search(self, seed_template: Dict[str, Any],
                                use_brave: bool = True) -> Dict[str, Any]:
        """
        Enrich a seed template with search results.
        
        Args:
            seed_template: Base seed template
            use_brave: Whether to use Brave search
            
        Returns:
            Enriched seed template
        """
        enriched = seed_template.copy()
        
        if not HOOKS_AVAILABLE or not self.web_hook:
            logger.warning("Web hooks not available - seed not enriched")
            return enriched
        
        complaint_type = seed_template.get('complaint_type', '')
        description = seed_template.get('description', '')
        
        # Build search query from template
        search_query = f"{complaint_type} complaint {description}"
        
        # Search using Brave if available
        if use_brave and BRAVE_SEARCH_AVAILABLE and hasattr(self.web_hook, 'brave_search') and self.web_hook.brave_search:
            try:
                results = self.web_hook.search_brave(search_query, max_results=5)
                
                # Extract useful information from results
                enriched['search_results'] = {
                    'query': search_query,
                    'results_count': len(results),
                    'examples': []
                }
                
                for result in results[:3]:
                    enriched['search_results']['examples'].append({
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'url': result.get('url', '')
                    })
                
                logger.info(f"Enriched seed with {len(results)} Brave search results")
            
            except Exception as e:
                logger.warning(f"Error enriching seed with Brave search: {e}")
        
        return enriched
    
    def enrich_seed_with_legal_corpus(self, seed_template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a seed template with legal corpus knowledge.
        
        Args:
            seed_template: Base seed template
            
        Returns:
            Enriched seed template
        """
        enriched = seed_template.copy()
        
        if not HOOKS_AVAILABLE or not self.legal_hook:
            logger.warning("Legal corpus hooks not available - seed not enriched")
            return enriched
        
        complaint_type = seed_template.get('complaint_type', '')
        
        if COMPLAINT_ANALYSIS_AVAILABLE and complaint_type:
            try:
                # Get legal requirements
                requirements = self.legal_hook.get_legal_requirements(complaint_type)
                
                if requirements:
                    enriched['legal_context'] = {
                        'keywords': requirements.get('keywords', [])[:20],
                        'requirement_patterns': requirements.get('requirement_patterns', [])[:10],
                        'category': requirements.get('category', '')
                    }
                
                # Get relevant legal patterns
                if 'description' in seed_template:
                    legal_refs = self.legal_hook.search_legal_corpus(
                        seed_template['description'],
                        complaint_type=complaint_type
                    )
                    
                    enriched['legal_references'] = [
                        {'content': ref['content'], 'type': ref['type']}
                        for ref in legal_refs[:5]
                    ]
                
                logger.info(f"Enriched seed with legal corpus knowledge for {complaint_type}")
            
            except Exception as e:
                logger.warning(f"Error enriching seed with legal corpus: {e}")
        
        return enriched
    
    def enrich_seed_full(self, seed_template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fully enrich a seed template with both search and legal corpus.
        
        Args:
            seed_template: Base seed template
            
        Returns:
            Fully enriched seed template
        """
        enriched = seed_template.copy()
        enriched = self.enrich_seed_with_search(enriched)
        enriched = self.enrich_seed_with_legal_corpus(enriched)
        enriched['enriched'] = True
        enriched['enriched_at'] = datetime.now().isoformat()
        return enriched


class DecisionTreeEnhancer:
    """
    Enhances decision trees using search and legal corpus.
    
    Improves question quality by:
    - Adding questions from legal corpus analysis
    - Validating question relevance with search
    - Enriching with legal terminology
    """
    
    def __init__(self, mock_mediator=None):
        """
        Initialize with optional mock mediator for testing.
        
        Args:
            mock_mediator: Mock mediator object for testing (optional)
        """
        self.mock_mediator = mock_mediator or self._create_mock_mediator()
        
        if HOOKS_AVAILABLE:
            self.legal_hook = LegalCorpusRAGHook(self.mock_mediator)
        else:
            self.legal_hook = None
    
    def _create_mock_mediator(self):
        """Create a minimal mock mediator for hooks."""
        class MockMediator:
            def __init__(self):
                self.logs = []
            
            def log(self, event_type, **kwargs):
                self.logs.append({'type': event_type, 'data': kwargs})
        
        return MockMediator()
    
    def enhance_decision_tree(self, tree_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance a decision tree with legal corpus knowledge.
        
        Args:
            tree_data: Decision tree data structure
            
        Returns:
            Enhanced decision tree
        """
        if not HOOKS_AVAILABLE or not self.legal_hook:
            logger.warning("Legal corpus hooks not available - tree not enhanced")
            return tree_data
        
        complaint_type = tree_data.get('complaint_type', '')
        
        if not complaint_type:
            return tree_data
        
        try:
            # Enrich tree with legal corpus
            enhanced = self.legal_hook.enrich_decision_tree(complaint_type, tree_data)
            
            logger.info(f"Enhanced decision tree for {complaint_type}")
            return enhanced
        
        except Exception as e:
            logger.warning(f"Error enhancing decision tree: {e}")
            return tree_data
    
    def suggest_additional_questions(self, tree_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Suggest additional questions for a decision tree.
        
        Args:
            tree_data: Decision tree data structure
            
        Returns:
            List of suggested questions
        """
        if not HOOKS_AVAILABLE or not self.legal_hook:
            logger.warning("Legal corpus hooks not available - no suggestions")
            return []
        
        complaint_type = tree_data.get('complaint_type', '')
        
        if not complaint_type:
            return []
        
        try:
            # Extract existing questions
            existing_questions = []
            if 'questions' in tree_data:
                for qid, question in tree_data['questions'].items():
                    if 'question' in question:
                        existing_questions.append(question['question'])
            
            # Get suggestions from legal corpus
            suggestions = self.legal_hook.suggest_questions(complaint_type, existing_questions)
            
            logger.info(f"Suggested {len(suggestions)} additional questions for {complaint_type}")
            return suggestions
        
        except Exception as e:
            logger.warning(f"Error suggesting questions: {e}")
            return []
    
    def validate_question_relevance(self, question: str, complaint_type: str) -> Dict[str, Any]:
        """
        Validate if a question is relevant using legal corpus.
        
        Args:
            question: Question text
            complaint_type: Type of complaint
            
        Returns:
            Validation result with relevance score
        """
        if not HOOKS_AVAILABLE or not self.legal_hook:
            return {
                'valid': True,
                'relevance_score': 0.5,
                'reason': 'Legal corpus not available'
            }
        
        try:
            # Search legal corpus for question terms
            results = self.legal_hook.search_legal_corpus(question, complaint_type)
            
            relevance_score = 0.0
            if results:
                # Calculate relevance based on search results
                relevance_score = min(1.0, len(results) / 10.0)
            
            return {
                'valid': relevance_score > 0.1,
                'relevance_score': relevance_score,
                'legal_references': [r['content'] for r in results[:3]],
                'reason': f"Found {len(results)} relevant legal references"
            }
        
        except Exception as e:
            logger.warning(f"Error validating question: {e}")
            return {
                'valid': True,
                'relevance_score': 0.5,
                'reason': f'Validation error: {e}'
            }


class MediatorSearchIntegration:
    """
    Integrates search capabilities into mediator during adversarial testing.
    
    Provides methods to:
    - Enhance question generation with search
    - Validate responses with legal corpus
    - Enrich knowledge graphs with search results
    """
    
    def __init__(self, mediator):
        """
        Initialize with a mediator instance.
        
        Args:
            mediator: Mediator instance to enhance
        """
        self.mediator = mediator
        
        if HOOKS_AVAILABLE:
            try:
                self.web_hook = WebEvidenceSearchHook(mediator)
                self.legal_hook = LegalCorpusRAGHook(mediator)
            except Exception as e:
                logger.warning(f"Error initializing hooks: {e}")
                self.web_hook = None
                self.legal_hook = None
        else:
            self.web_hook = None
            self.legal_hook = None
    
    def enhance_question_generation(self, complaint_type: str, 
                                   current_questions: List[str]) -> List[str]:
        """
        Enhance question generation using legal corpus.
        
        Args:
            complaint_type: Type of complaint
            current_questions: Questions already generated
            
        Returns:
            Additional suggested questions
        """
        if not self.legal_hook:
            return []
        
        try:
            suggestions = self.legal_hook.suggest_questions(complaint_type, current_questions)
            return [s['question'] for s in suggestions[:5]]
        except Exception as e:
            logger.warning(f"Error enhancing questions: {e}")
            return []
    
    def search_for_precedents(self, claim: str) -> List[Dict[str, Any]]:
        """
        Search for legal precedents using Brave search.
        
        Args:
            claim: Legal claim description
            
        Returns:
            List of relevant precedents
        """
        if not self.web_hook or not hasattr(self.web_hook, 'search_brave'):
            return []
        
        try:
            query = f"{claim} legal precedent case law"
            results = self.web_hook.search_brave(query, max_results=5)
            return results
        except Exception as e:
            logger.warning(f"Error searching precedents: {e}")
            return []
    
    def enrich_knowledge_graph(self, graph_data: Dict[str, Any],
                              complaint_type: str) -> Dict[str, Any]:
        """
        Enrich knowledge graph with legal corpus data.
        
        Args:
            graph_data: Knowledge graph data
            complaint_type: Type of complaint
            
        Returns:
            Enriched knowledge graph
        """
        if not self.legal_hook:
            return graph_data
        
        try:
            # Get legal requirements
            requirements = self.legal_hook.get_legal_requirements(complaint_type)
            
            if requirements:
                graph_data['legal_requirements'] = requirements
            
            return graph_data
        except Exception as e:
            logger.warning(f"Error enriching knowledge graph: {e}")
            return graph_data
