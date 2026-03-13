"""
Unit tests for Web Evidence Discovery Hooks

Tests for web evidence discovery, validation, and integration functionality.
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


class TestWebEvidenceSearchHook:
    """Test cases for WebEvidenceSearchHook"""
    
    def test_web_evidence_search_hook_can_be_imported(self):
        """Test that WebEvidenceSearchHook can be imported"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook
            assert WebEvidenceSearchHook is not None
        except ImportError as e:
            pytest.skip(f"WebEvidenceSearchHook has import issues: {e}")
    
    def test_init_search_tools(self):
        """Test initialization of search tools"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            hook = WebEvidenceSearchHook(mock_mediator)
            
            # Should have initialized with warnings if tools not available
            assert mock_mediator.log.called
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_search_brave(self):
        """Test Brave Search functionality"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            hook = WebEvidenceSearchHook(mock_mediator)
            
            # Mock Brave Search client
            mock_brave = Mock()
            mock_brave.web_search = Mock(return_value={
                'web': {
                    'results': [
                        {
                            'title': 'Test Result',
                            'url': 'https://example.com/test',
                            'description': 'Test description'
                        }
                    ]
                }
            })
            hook.brave_search = mock_brave
            
            results = hook.search_brave('employment discrimination', max_results=10)
            
            assert isinstance(results, list)
            if results:
                assert 'source_type' in results[0]
                assert results[0]['source_type'] == 'brave_search'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_search_common_crawl(self):
        """Test Common Crawl search functionality"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            hook = WebEvidenceSearchHook(mock_mediator)
            
            # Mock Common Crawl search
            mock_cc = Mock()
            mock_cc.search_domain = Mock(return_value=[
                {
                    'url': 'https://example.com/page1',
                    'content': 'Test content'
                }
            ])
            hook.cc_search = mock_cc
            
            results = hook.search_common_crawl('example.com', max_results=10)
            
            assert isinstance(results, list)
            if results:
                assert 'source_type' in results[0]
                assert results[0]['source_type'] == 'common_crawl'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_search_for_evidence(self):
        """Test searching all sources for evidence"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            hook = WebEvidenceSearchHook(mock_mediator)
            
            # Mock both search methods
            hook.search_brave = Mock(return_value=[
                {'title': 'Brave Result', 'url': 'https://example.com/1'}
            ])
            hook.search_common_crawl = Mock(return_value=[
                {'title': 'CC Result', 'url': 'https://example.com/2'}
            ])
            hook.brave_search = True  # Indicate available
            hook.cc_search = True  # Indicate available
            
            results = hook.search_for_evidence(
                keywords=['employment', 'discrimination'],
                domains=['example.com'],
                max_results=20
            )
            
            assert isinstance(results, dict)
            assert 'brave_search' in results
            assert 'common_crawl' in results
            assert 'total_found' in results
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_validate_evidence(self):
        """Test evidence validation"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="Relevance: 0.8 - Highly relevant")
            
            hook = WebEvidenceSearchHook(mock_mediator)
            
            evidence_item = {
                'title': 'Test Evidence',
                'url': 'https://example.com/evidence',
                'content': 'Test content about discrimination',
                'source_type': 'brave_search'
            }
            
            validation = hook.validate_evidence(evidence_item)
            
            assert isinstance(validation, dict)
            assert 'valid' in validation
            assert 'relevance_score' in validation
            assert validation['valid'] is True
            assert 0.0 <= validation['relevance_score'] <= 1.0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_get_capability_registry_returns_expected_shape(self):
        """Test capability registry shape for Phase 1 adapter integration."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            hook = WebEvidenceSearchHook(mock_mediator)
            registry = hook.get_capability_registry()

            assert isinstance(registry, dict)
            assert 'search_tools' in registry
            assert 'legal_datasets' in registry

            search = registry['search_tools']
            assert 'available' in search
            assert 'enabled' in search
            assert 'active' in search
            assert 'details' in search
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_for_evidence_enhanced_adds_normalized_results(self):
        """Enhanced search mode should expose normalized deduped records."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
            }, clear=False):
                hook = WebEvidenceSearchHook(mock_mediator)
                hook.search_brave = Mock(return_value=[
                    {'title': 'Result 1', 'url': 'example-dot-com/a', 'score': 0.35},
                    {'title': 'Result 1 better', 'url': 'example-dot-com/a', 'score': 0.80},
                ])
                hook.search_common_crawl = Mock(return_value=[])
                hook.brave_search = True
                hook.cc_search = True

                results = hook.search_for_evidence(
                    keywords=['employment', 'discrimination'],
                    domains=['example-dot-com'],
                    max_results=20,
                )

                assert isinstance(results, dict)
                assert 'normalized' in results
                assert isinstance(results['normalized'], list)
                assert len(results['normalized']) == 1
                assert results['normalized'][0]['score'] == 0.8
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_for_evidence_enhanced_vector_marks_normalized_metadata(self):
        """Enhanced vector mode should annotate normalized records with vector metadata."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_VECTOR': '1',
            }, clear=False):
                hook = WebEvidenceSearchHook(mock_mediator)
                hook.search_brave = Mock(return_value=[
                    {'title': 'Employment discrimination resources', 'url': 'example-dot-com/a', 'score': 0.35},
                ])
                hook.search_common_crawl = Mock(return_value=[])
                hook.brave_search = True
                hook.cc_search = True

                results = hook.search_for_evidence(
                    keywords=['employment', 'discrimination'],
                    domains=['example-dot-com'],
                    max_results=20,
                )

                assert 'normalized' in results
                assert len(results['normalized']) >= 1
                assert results['normalized'][0]['metadata'].get('vector_augmented') is True
                assert results['normalized'][0]['metadata'].get('evidence_similarity_applied') is True
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_for_evidence_vector_uses_state_context_to_boost_matching_record(self):
        """Enhanced vector mode should use complaint/evidence context to prefer matching evidence."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.complaint_summary = 'Retaliation after reporting discrimination to HR'
            mock_mediator.state.original_complaint = 'I have a termination email and retaliation evidence.'
            mock_mediator.state.complaint = None
            mock_mediator.state.last_message = 'Need proof tied to the termination email.'
            mock_mediator.state.data = {
                'chat_history': {
                    '1': 'termination email from manager',
                    '2': 'retaliation complaint details',
                }
            }

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_VECTOR': '1',
            }, clear=False):
                hook = WebEvidenceSearchHook(mock_mediator)
                hook.search_brave = Mock(return_value=[
                    {'title': 'Termination email retaliation evidence guide', 'url': 'example-dot-com/relevant', 'score': 0.35},
                    {'title': 'Generic workplace newsletter', 'url': 'example-dot-com/generic', 'score': 0.45},
                ])
                hook.search_common_crawl = Mock(return_value=[])
                hook.brave_search = True
                hook.cc_search = True

                results = hook.search_for_evidence(
                    keywords=['employment', 'discrimination'],
                    domains=['example-dot-com'],
                    max_results=20,
                )

                assert 'normalized' in results
                assert results['normalized'][0]['title'] == 'Termination email retaliation evidence guide'
                assert results['normalized'][0]['metadata'].get('evidence_similarity_score', 0.0) > 0.0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_build_evidence_context_uses_structured_chat_message_text(self):
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook
            from mediator.state import State

            mock_mediator = Mock()
            mock_mediator.log = Mock()
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
                        'message': 'Employer admitted retaliation in an email.',
                        'question': 'Do you have the employer email?',
                    }
                }
            }
            helper_state = State()
            helper_state.data = mock_mediator.state.data
            mock_mediator.state.extract_chat_history_context_strings = helper_state.extract_chat_history_context_strings

            hook = WebEvidenceSearchHook(mock_mediator)
            context = hook._build_evidence_context(['retaliation'], ['example.com'])

            assert 'Employer admitted retaliation in an email.' in context
            assert not any('{\'sender\':' in item for item in context)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_build_evidence_context_uses_structured_chat_message_text_without_helper(self):
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.complaint_summary = None
            mock_mediator.state.original_complaint = None
            mock_mediator.state.complaint = None
            mock_mediator.state.last_message = None
            mock_mediator.state.data = {
                'chat_history': {
                    '1': {
                        'sender': 'user-123',
                        'message': 'Structured retaliation email detail.',
                        'question': 'Do you have the employer email?',
                    }
                }
            }

            hook = WebEvidenceSearchHook(mock_mediator)
            context = hook._build_evidence_context(['retaliation'], ['example.com'])

            assert 'Structured retaliation email detail.' in context
            assert 'Do you have the employer email?' in context
            assert not any('{\'sender\':' in item for item in context)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_for_evidence_graph_reranker_boosts_graph_aligned_record(self):
        """Enhanced graph mode should rerank web evidence with graph context."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook

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
                                {'source_name': 'termination email'},
                            ],
                        }
                    ]

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(
                side_effect=lambda _phase, key=None: _KG() if key == 'knowledge_graph' else (_DG() if key == 'dependency_graph' else None)
            )

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_GRAPH': '1',
                'RETRIEVAL_RERANKER_MODE': 'graph',
            }, clear=False):
                hook = WebEvidenceSearchHook(mock_mediator)
                hook.search_brave = Mock(return_value=[
                    {'title': 'Employment discrimination retaliation evidence', 'url': 'example-dot-com/relevant', 'score': 0.40},
                    {'title': 'Unrelated weather blog', 'url': 'example-dot-com/generic', 'score': 0.49},
                ])
                hook.search_common_crawl = Mock(return_value=[])
                hook.brave_search = True
                hook.cc_search = True

                results = hook.search_for_evidence(
                    keywords=['proof', 'documents'],
                    domains=['example-dot-com'],
                    max_results=20,
                )

                assert 'normalized' in results
                assert results['normalized'][0]['title'] == 'Employment discrimination retaliation evidence'
                assert results['normalized'][0]['metadata'].get('graph_reranked') is True
                assert results['normalized'][0]['metadata'].get('graph_readiness_gap', 0) > 0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestWebEvidenceIntegrationHook:
    """Test cases for WebEvidenceIntegrationHook"""
    
    def test_web_evidence_integration_hook_can_be_imported(self):
        """Test that WebEvidenceIntegrationHook can be imported"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook
            assert WebEvidenceIntegrationHook is not None
        except ImportError as e:
            pytest.skip(f"WebEvidenceIntegrationHook has import issues: {e}")
    
    def test_discover_and_store_evidence(self):
        """Test discovering and storing evidence"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            
            # Mock dependencies
            mock_mediator.web_evidence_search = Mock()
            mock_mediator.web_evidence_search.search_for_evidence = Mock(return_value={
                'total_found': 2,
                'brave_search': [
                    {
                        'title': 'Evidence 1',
                        'url': 'https://example.com/1',
                        'content': 'Content 1',
                        'source_type': 'brave_search'
                    }
                ],
                'common_crawl': [
                    {
                        'title': 'Evidence 2',
                        'url': 'https://example.com/2',
                        'content': 'Content 2',
                        'source_type': 'common_crawl'
                    }
                ]
            })
            mock_mediator.web_evidence_search.validate_evidence = Mock(return_value={
                'valid': True,
                'relevance_score': 0.8
            })
            
            mock_mediator.evidence_storage = Mock()
            mock_mediator.evidence_storage.store_evidence = Mock(return_value={
                'cid': 'QmTest123',
                'size': 100
            })
            
            mock_mediator.evidence_state = Mock()
            mock_mediator.evidence_state.add_evidence_record = Mock(return_value=1)
            
            hook = WebEvidenceIntegrationHook(mock_mediator)
            
            result = hook.discover_and_store_evidence(
                keywords=['employment', 'discrimination'],
                user_id='testuser',
                min_relevance=0.5
            )
            
            assert isinstance(result, dict)
            assert 'discovered' in result
            assert 'stored' in result
            assert result['discovered'] == 2
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_generate_search_keywords(self):
        """Test search keyword generation"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="discrimination\nemployment\nwrongful termination")
            
            hook = WebEvidenceIntegrationHook(mock_mediator)
            
            keywords = hook._generate_search_keywords('employment discrimination')
            
            assert isinstance(keywords, list)
            assert len(keywords) > 0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestMediatorWebEvidenceIntegration:
    """Integration tests for web evidence hooks with mediator"""
    
    @pytest.mark.integration
    def test_mediator_has_web_evidence_hooks(self):
        """Test that mediator initializes with web evidence hooks"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            mediator = Mediator(backends=[mock_backend])
            
            assert hasattr(mediator, 'web_evidence_search')
            assert hasattr(mediator, 'web_evidence_integration')
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    @pytest.mark.integration
    def test_mediator_discover_web_evidence(self):
        """Test discovering web evidence through mediator"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            
            # Mock the integration method
            mediator.web_evidence_integration.discover_and_store_evidence = Mock(return_value={
                'discovered': 5,
                'validated': 4,
                'stored': 3,
                'skipped': 2
            })
            
            result = mediator.discover_web_evidence(
                keywords=['employment', 'discrimination'],
                min_relevance=0.6
            )
            
            assert isinstance(result, dict)
            assert 'discovered' in result
            assert 'stored' in result
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    @pytest.mark.integration
    def test_mediator_search_web_for_evidence(self):
        """Test searching web without storing"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            mediator = Mediator(backends=[mock_backend])
            
            # Mock the search method
            mediator.web_evidence_search.search_for_evidence = Mock(return_value={
                'brave_search': [],
                'common_crawl': [],
                'total_found': 0,
                'support_bundle': {
                    'top_mixed': [],
                    'top_authorities': [],
                    'top_evidence': [],
                    'cross_supported': [],
                    'hybrid_cross_supported': [],
                    'summary': {
                        'total_records': 0,
                        'authority_count': 0,
                        'evidence_count': 0,
                        'cross_supported_count': 0,
                        'hybrid_cross_supported_count': 0,
                    },
                },
            })
            
            result = mediator.search_web_for_evidence(
                keywords=['test', 'query']
            )
            
            assert isinstance(result, dict)
            assert 'total_found' in result
            assert hasattr(mediator.state, 'last_web_evidence_support_bundle')
            assert mediator.state.last_web_evidence_support_bundle['summary']['total_records'] == 0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
