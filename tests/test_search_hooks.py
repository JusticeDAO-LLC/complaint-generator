"""
Tests for Search and Legal Corpus Hooks

Tests both the legal corpus RAG hooks and the adversarial harness search hooks.
"""

import sys
import os
import pytest
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mediator.legal_corpus_hooks import LegalCorpusRAGHook
from adversarial_harness.search_hooks import (
    SearchEnrichedSeedGenerator,
    DecisionTreeEnhancer,
    MediatorSearchIntegration
)


class TestLegalCorpusRAGHook:
    """Tests for LegalCorpusRAGHook."""
    
    @pytest.fixture
    def mock_mediator(self):
        """Create a mock mediator."""
        mediator = Mock()
        mediator.log = Mock()
        return mediator
    
    @pytest.fixture
    def hook(self, mock_mediator):
        """Create a LegalCorpusRAGHook instance."""
        return LegalCorpusRAGHook(mock_mediator)
    
    def test_initialization(self, hook, mock_mediator):
        """Test hook initialization."""
        assert hook.mediator == mock_mediator
        assert hasattr(hook, 'legal_patterns')
        assert hasattr(hook, 'legal_terms')
    
    def test_search_legal_corpus(self, hook):
        """Test searching the legal corpus."""
        results = hook.search_legal_corpus("discrimination", max_results=10)
        assert isinstance(results, list)
        # Results may be empty if complaint_analysis not available
        if results:
            assert 'type' in results[0]
            assert 'content' in results[0]
            assert 'score' in results[0]
    
    def test_search_with_complaint_type(self, hook):
        """Test searching with specific complaint type."""
        results = hook.search_legal_corpus(
            "employment", 
            complaint_type="employment_discrimination",
            max_results=5
        )
        assert isinstance(results, list)
    
    def test_retrieve_relevant_laws(self, hook):
        """Test retrieving relevant laws for claims."""
        claims = ["discrimination at work", "wrongful termination"]
        laws = hook.retrieve_relevant_laws(claims)
        assert isinstance(laws, list)
        # May be empty if no matches found
        if laws:
            assert 'claim' in laws[0]
            assert 'legal_reference' in laws[0]
    
    def test_enrich_decision_tree(self, hook):
        """Test enriching a decision tree."""
        tree_data = {
            'complaint_type': 'employment_discrimination',
            'category': 'employment',
            'description': 'Employment discrimination complaint',
            'questions': {
                'q1': {
                    'question': 'When did the discrimination occur?',
                    'field_name': 'date',
                    'keywords': ['discrimination', 'date']
                }
            }
        }
        
        enriched = hook.enrich_decision_tree('employment_discrimination', tree_data)
        assert isinstance(enriched, dict)
        assert 'complaint_type' in enriched
        # May have legal_context if complaint_analysis available
    
    def test_get_legal_requirements(self, hook):
        """Test getting legal requirements."""
        requirements = hook.get_legal_requirements('employment_discrimination')
        assert isinstance(requirements, dict)
        # May be empty if complaint type not found
    
    def test_suggest_questions(self, hook):
        """Test suggesting additional questions."""
        existing = ["What is your name?", "When did this happen?"]
        suggestions = hook.suggest_questions('employment_discrimination', existing)
        assert isinstance(suggestions, list)
        # May be empty if complaint type not found
        if suggestions:
            assert 'question' in suggestions[0]
            assert 'keyword' in suggestions[0]

    def test_get_capability_registry_returns_expected_shape(self, mock_mediator):
        """Test capability registry shape for Phase 1 adapter integration."""
        hook = LegalCorpusRAGHook(mock_mediator)
        registry = hook.get_capability_registry()

        assert isinstance(registry, dict)
        assert 'legal_datasets' in registry
        assert 'search_tools' in registry

        search = registry['search_tools']
        assert 'available' in search
        assert 'enabled' in search
        assert 'active' in search
        assert 'details' in search

    def test_search_legal_corpus_bundle_enhanced_adds_normalized(self, mock_mediator):
        """Enhanced mode should include normalized deduped/ranked bundle results."""
        with patch.dict(os.environ, {
            'IPFS_DATASETS_ENHANCED_SEARCH': '1',
            'IPFS_DATASETS_ENHANCED_LEGAL': '1',
        }, clear=False):
            hook = LegalCorpusRAGHook(mock_mediator)

            hook.search_legal_corpus = Mock(return_value=[
                {'type': 'legal_term', 'content': 'Title VII', 'score': 2, 'source': 'legal_terms'},
                {'type': 'legal_term', 'content': 'Title VII', 'score': 9, 'source': 'legal_terms'},
            ])

            bundle = hook.search_legal_corpus_bundle('title vii', max_results=10)

            assert isinstance(bundle, dict)
            assert 'raw' in bundle
            assert 'normalized' in bundle
            assert len(bundle['normalized']) == 1
            assert bundle['normalized'][0]['score'] == 9

    def test_search_legal_corpus_bundle_enhanced_vector_marks_metadata(self, mock_mediator):
        """Enhanced vector mode should annotate normalized bundle records."""
        with patch.dict(os.environ, {
            'IPFS_DATASETS_ENHANCED_SEARCH': '1',
            'IPFS_DATASETS_ENHANCED_LEGAL': '1',
            'IPFS_DATASETS_ENHANCED_VECTOR': '1',
        }, clear=False):
            hook = LegalCorpusRAGHook(mock_mediator)

            hook.search_legal_corpus = Mock(return_value=[
                {'type': 'legal_term', 'content': 'Employment discrimination', 'score': 2, 'source': 'legal_terms'},
            ])

            bundle = hook.search_legal_corpus_bundle('employment discrimination', max_results=10)

            assert 'normalized' in bundle
            assert len(bundle['normalized']) >= 1
            assert bundle['normalized'][0]['metadata'].get('vector_augmented') is True

    def test_search_legal_corpus_bundle_exposes_support_bundle(self, mock_mediator):
        """Enhanced legal corpus bundles should expose bucketed support for downstream drafting."""
        with patch.dict(os.environ, {
            'IPFS_DATASETS_ENHANCED_SEARCH': '1',
            'IPFS_DATASETS_ENHANCED_LEGAL': '1',
            'IPFS_DATASETS_ENHANCED_VECTOR': '1',
        }, clear=False):
            hook = LegalCorpusRAGHook(mock_mediator)

            hook.search_legal_corpus = Mock(return_value=[
                {
                    'type': 'legal_term',
                    'content': 'termination retaliation evidentiary support',
                    'score': 0.35,
                    'source': 'legal_terms',
                },
            ])

            bundle = hook.search_legal_corpus_bundle('employment retaliation', max_results=10)

            assert 'support_bundle' in bundle
            assert bundle['support_bundle']['summary']['total_records'] >= 1
            assert len(bundle['support_bundle']['top_authorities']) >= 1
            assert isinstance(bundle['support_bundle']['top_mixed'], list)

    def test_search_legal_corpus_bundle_vector_uses_state_context_to_boost_matching_record(self, mock_mediator):
        """Enhanced vector mode should use complaint context to prefer matching legal corpus content."""
        mock_mediator.state = Mock()
        mock_mediator.state.complaint_summary = 'Retaliation after reporting discrimination to HR'
        mock_mediator.state.original_complaint = 'Termination email supports the retaliation claim.'
        mock_mediator.state.complaint = None
        mock_mediator.state.last_message = 'Need legal support tied to the termination email evidence.'
        mock_mediator.state.data = {
            'chat_history': {
                '1': 'termination email from manager',
                '2': 'retaliation complaint details',
            }
        }

        with patch.dict(os.environ, {
            'IPFS_DATASETS_ENHANCED_SEARCH': '1',
            'IPFS_DATASETS_ENHANCED_LEGAL': '1',
            'IPFS_DATASETS_ENHANCED_VECTOR': '1',
        }, clear=False):
            hook = LegalCorpusRAGHook(mock_mediator)

            hook.search_legal_corpus = Mock(return_value=[
                {
                    'type': 'legal_term',
                    'content': 'termination email retaliation evidentiary support',
                    'score': 0.35,
                    'source': 'legal_terms',
                },
                {
                    'type': 'legal_term',
                    'content': 'general workplace handbook overview',
                    'score': 0.45,
                    'source': 'legal_terms',
                },
            ])

            bundle = hook.search_legal_corpus_bundle('employment retaliation', max_results=10)

            assert 'normalized' in bundle
            assert bundle['normalized'][0]['title'] == 'termination email retaliation evidentiary support'
            assert bundle['normalized'][0]['metadata'].get('evidence_similarity_applied') is True
            assert bundle['normalized'][0]['metadata'].get('evidence_similarity_score', 0.0) > 0.0

    def test_build_evidence_context_uses_structured_chat_message_text_without_helper(self, mock_mediator):
        mock_mediator.state = Mock()
        mock_mediator.state.complaint_summary = None
        mock_mediator.state.original_complaint = None
        mock_mediator.state.complaint = None
        mock_mediator.state.last_message = None
        mock_mediator.state.extract_chat_history_context_strings = lambda limit=3: 'not-a-list'
        mock_mediator.state.data = {
            'chat_history': {
                '1': {
                    'sender': 'user-123',
                    'message': 'Structured retaliation evidence detail.',
                    'question': 'Do you have the employer email?',
                }
            }
        }

        hook = LegalCorpusRAGHook(mock_mediator)
        context = hook._build_evidence_context('employment retaliation')

        assert 'Structured retaliation evidence detail.' in context
        assert 'Do you have the employer email?' in context
        assert not any('{\'sender\':' in item for item in context)

    def test_search_legal_corpus_bundle_graph_reranker_boosts_graph_aligned_record(self, mock_mediator):
        """Enhanced graph mode should rerank legal corpus bundle using graph context."""

        class _Entity:
            def __init__(self, name):
                self.name = name
                self.attributes = {}

        class _Node:
            def __init__(self, name):
                self.name = name
                self.description = ""

        class _KG:
            def get_entities_by_type(self, entity_type):
                if entity_type == 'claim':
                    return [_Entity('employment discrimination')]
                return []

        class _DG:
            def get_nodes_by_type(self, _node_type):
                return [_Node('retaliation')]

            def get_claim_readiness(self):
                return {
                    'overall_readiness': 0.0,
                    'incomplete_claim_details': [
                        {'claim_name': 'employment discrimination retaliation'}
                    ],
                }

            def find_unsatisfied_requirements(self):
                return [
                    {
                        'node_name': 'retaliation claim',
                        'missing_dependencies': [
                            {'source_name': 'witness statement'},
                        ],
                    }
                ]

        mock_mediator.phase_manager = Mock()
        mock_mediator.phase_manager.get_phase_data = Mock(
            side_effect=lambda _phase, key=None: _KG() if key == 'knowledge_graph' else (_DG() if key == 'dependency_graph' else None)
        )

        with patch.dict(os.environ, {
            'IPFS_DATASETS_ENHANCED_SEARCH': '1',
            'IPFS_DATASETS_ENHANCED_LEGAL': '1',
            'IPFS_DATASETS_ENHANCED_GRAPH': '1',
            'RETRIEVAL_RERANKER_MODE': 'graph',
        }, clear=False):
            hook = LegalCorpusRAGHook(mock_mediator)

            hook.search_legal_corpus = Mock(return_value=[
                {'type': 'legal_term', 'content': 'employment discrimination retaliation', 'score': 0.40, 'source': 'legal_terms'},
                {'type': 'legal_term', 'content': 'general filing checklist', 'score': 0.49, 'source': 'legal_terms'},
            ])

            bundle = hook.search_legal_corpus_bundle('claim requirements', max_results=10)

            assert 'normalized' in bundle
            assert bundle['normalized'][0]['title'] == 'employment discrimination retaliation'
            assert bundle['normalized'][0]['metadata'].get('graph_reranked') is True
            assert bundle['normalized'][0]['metadata'].get('graph_readiness_gap', 0) > 0

    def test_search_legal_corpus_bundle_enhanced_decomposes_query(self, mock_mediator):
        """Enhanced legal/search mode should expand legal corpus retrieval over decomposed queries."""
        with patch.dict(os.environ, {
            'IPFS_DATASETS_ENHANCED_SEARCH': '1',
            'IPFS_DATASETS_ENHANCED_LEGAL': '1',
        }, clear=False):
            hook = LegalCorpusRAGHook(mock_mediator)

            hook.search_legal_corpus = Mock(side_effect=lambda query, complaint_type=None, max_results=10: [
                {'type': 'legal_term', 'content': query, 'score': 1.0, 'source': 'legal_terms'}
            ])

            bundle = hook.search_legal_corpus_bundle(
                'employment discrimination retaliation',
                complaint_type='employment_discrimination',
                max_results=10,
            )

            assert hook.search_legal_corpus.call_count >= 2
            assert bundle['normalized'][0]['metadata'].get('query_decomposition_applied') is True
            assert bundle['normalized'][0]['metadata'].get('query_decomposition_count', 0) >= 2


class TestSearchEnrichedSeedGenerator:
    """Tests for SearchEnrichedSeedGenerator."""
    
    @pytest.fixture
    def generator(self):
        """Create a SearchEnrichedSeedGenerator instance."""
        return SearchEnrichedSeedGenerator()
    
    @pytest.fixture
    def seed_template(self):
        """Create a sample seed template."""
        return {
            'complaint_type': 'employment_discrimination',
            'category': 'employment',
            'description': 'Discrimination in the workplace',
            'required_fields': ['employer', 'discrimination_type', 'date'],
            'optional_fields': ['witnesses', 'evidence']
        }
    
    def test_initialization(self, generator):
        """Test generator initialization."""
        assert hasattr(generator, 'mock_mediator')
        assert hasattr(generator, 'web_hook')
        assert hasattr(generator, 'legal_hook')
    
    def test_enrich_seed_with_search(self, generator, seed_template):
        """Test enriching seed with search (may not have real search)."""
        enriched = generator.enrich_seed_with_search(seed_template, use_brave=True)
        assert isinstance(enriched, dict)
        assert 'complaint_type' in enriched
        assert 'description' in enriched
    
    def test_enrich_seed_with_legal_corpus(self, generator, seed_template):
        """Test enriching seed with legal corpus."""
        enriched = generator.enrich_seed_with_legal_corpus(seed_template)
        assert isinstance(enriched, dict)
        assert 'complaint_type' in enriched
        # May have legal_context if available
    
    def test_enrich_seed_full(self, generator, seed_template):
        """Test full seed enrichment."""
        enriched = generator.enrich_seed_full(seed_template)
        assert isinstance(enriched, dict)
        assert 'enriched' in enriched
        assert enriched['enriched'] is True
        assert 'enriched_at' in enriched


class TestDecisionTreeEnhancer:
    """Tests for DecisionTreeEnhancer."""
    
    @pytest.fixture
    def enhancer(self):
        """Create a DecisionTreeEnhancer instance."""
        return DecisionTreeEnhancer()
    
    @pytest.fixture
    def tree_data(self):
        """Create sample tree data."""
        return {
            'complaint_type': 'employment_discrimination',
            'category': 'employment',
            'description': 'Employment discrimination complaint',
            'root_questions': ['q1', 'q2'],
            'questions': {
                'q1': {
                    'id': 'q1',
                    'question': 'What type of discrimination occurred?',
                    'field_name': 'discrimination_type',
                    'required': True,
                    'keywords': ['discrimination', 'type']
                },
                'q2': {
                    'id': 'q2',
                    'question': 'When did this occur?',
                    'field_name': 'date',
                    'required': True,
                    'keywords': ['date', 'when']
                }
            }
        }
    
    def test_initialization(self, enhancer):
        """Test enhancer initialization."""
        assert hasattr(enhancer, 'mock_mediator')
        assert hasattr(enhancer, 'legal_hook')
    
    def test_enhance_decision_tree(self, enhancer, tree_data):
        """Test enhancing a decision tree."""
        enhanced = enhancer.enhance_decision_tree(tree_data)
        assert isinstance(enhanced, dict)
        assert 'complaint_type' in enhanced
        assert 'questions' in enhanced
    
    def test_suggest_additional_questions(self, enhancer, tree_data):
        """Test suggesting additional questions."""
        suggestions = enhancer.suggest_additional_questions(tree_data)
        assert isinstance(suggestions, list)
        # May be empty if no suggestions
    
    def test_validate_question_relevance(self, enhancer):
        """Test validating question relevance."""
        result = enhancer.validate_question_relevance(
            "What type of discrimination occurred?",
            "employment_discrimination"
        )
        assert isinstance(result, dict)
        assert 'valid' in result
        assert 'relevance_score' in result
        assert isinstance(result['valid'], bool)
        assert isinstance(result['relevance_score'], float)


class TestMediatorSearchIntegration:
    """Tests for MediatorSearchIntegration."""
    
    @pytest.fixture
    def mock_mediator(self):
        """Create a mock mediator."""
        mediator = Mock()
        mediator.log = Mock()
        return mediator
    
    @pytest.fixture
    def integration(self, mock_mediator):
        """Create a MediatorSearchIntegration instance."""
        return MediatorSearchIntegration(mock_mediator)
    
    def test_initialization(self, integration, mock_mediator):
        """Test integration initialization."""
        assert integration.mediator == mock_mediator
        assert hasattr(integration, 'web_hook')
        assert hasattr(integration, 'legal_hook')
    
    def test_enhance_question_generation(self, integration):
        """Test enhancing question generation."""
        current_questions = ["What is your name?", "Where did this happen?"]
        suggestions = integration.enhance_question_generation(
            "employment_discrimination",
            current_questions
        )
        assert isinstance(suggestions, list)
    
    def test_search_for_precedents(self, integration):
        """Test searching for precedents."""
        precedents = integration.search_for_precedents("age discrimination")
        assert isinstance(precedents, list)
        # May be empty if Brave search not available
    
    def test_enrich_knowledge_graph(self, integration):
        """Test enriching knowledge graph."""
        graph_data = {
            'entities': [
                {'id': 'e1', 'type': 'person', 'name': 'John Doe'}
            ],
            'relationships': []
        }
        
        enriched = integration.enrich_knowledge_graph(
            graph_data,
            "employment_discrimination"
        )
        assert isinstance(enriched, dict)
        assert 'entities' in enriched


class TestIntegration:
    """Integration tests for all search hooks working together."""
    
    def test_full_workflow(self):
        """Test a complete workflow using all hooks."""
        # Create mock mediator
        mediator = Mock()
        mediator.log = Mock()
        
        # Initialize hooks
        legal_hook = LegalCorpusRAGHook(mediator)
        seed_gen = SearchEnrichedSeedGenerator()
        tree_enhancer = DecisionTreeEnhancer()
        med_integration = MediatorSearchIntegration(mediator)
        
        # Test workflow
        assert legal_hook is not None
        assert seed_gen is not None
        assert tree_enhancer is not None
        assert med_integration is not None
        
        # Basic operations should not raise errors
        legal_hook.search_legal_corpus("discrimination")
        
        seed_template = {
            'complaint_type': 'employment_discrimination',
            'description': 'Test complaint'
        }
        enriched_seed = seed_gen.enrich_seed_full(seed_template)
        assert isinstance(enriched_seed, dict)
        
        tree_data = {
            'complaint_type': 'employment_discrimination',
            'questions': {}
        }
        enhanced_tree = tree_enhancer.enhance_decision_tree(tree_data)
        assert isinstance(enhanced_tree, dict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
