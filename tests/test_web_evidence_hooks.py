"""
Unit tests for Web Evidence Discovery Hooks

Tests for web evidence discovery, validation, and integration functionality.
"""
import pytest
import tempfile
import os
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


pytestmark = pytest.mark.no_auto_network


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
            assert 'multi_engine_search' in results
            assert 'archived_domain_scrape' in results
            assert 'total_found' in results
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_for_evidence_includes_extended_sources(self):
        """Test that extended search sources are merged into the search payload"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceSearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            hook = WebEvidenceSearchHook(mock_mediator)
            hook.brave_search = True
            hook.cc_search = True
            hook.search_brave = Mock(return_value=[
                {'title': 'Brave Result', 'url': 'https://example.com/1', 'source_type': 'brave_search'}
            ])
            hook.search_common_crawl = Mock(return_value=[
                {'title': 'Archive Result', 'url': 'https://example.com/2', 'source_type': 'common_crawl'}
            ])

            with patch('mediator.web_evidence_hooks.MULTI_ENGINE_SEARCH_AVAILABLE', True):
                with patch('mediator.web_evidence_hooks.UNIFIED_WEB_SCRAPER_AVAILABLE', True):
                    with patch('mediator.web_evidence_hooks.search_multi_engine_web', return_value=[
                        {'title': 'Multi Result', 'url': 'https://example.com/3', 'source_type': 'multi_engine_search'}
                    ]):
                        with patch('mediator.web_evidence_hooks.scrape_archived_domain', return_value=[
                            {'title': 'Sweep Result', 'url': 'https://example.com/4', 'source_type': 'archived_domain_scrape'}
                        ]):
                            results = hook.search_for_evidence(
                                keywords=['employment', 'discrimination'],
                                domains=['example.com'],
                                max_results=10,
                            )

            assert results['total_found'] == 4
            assert len(results['multi_engine_search']) == 1
            assert len(results['archived_domain_scrape']) == 1
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
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(return_value=object())
            mock_mediator.add_evidence_to_graphs = Mock(return_value={
                'graph_projection': {
                    'projected': True,
                    'graph_changed': True,
                    'entity_count': 3,
                    'relationship_count': 2,
                    'claim_links': 1,
                    'artifact_entity_added': True,
                    'artifact_entity_already_present': False,
                    'storage_record_created': True,
                    'storage_record_reused': False,
                    'support_link_created': True,
                    'support_link_reused': False,
                }
            })
            
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
                'size': 100,
                'type': 'web_document',
                'metadata': {
                    'document_parse_summary': {
                        'status': 'fallback',
                        'chunk_count': 1,
                        'text_length': 42,
                        'parser_version': 'documents-adapter:1',
                        'input_format': 'text',
                        'paragraph_count': 1,
                        },
                        'document_parse_contract': {
                            'status': 'fallback',
                            'source': 'web_document',
                            'chunk_count': 1,
                            'summary': {
                                'status': 'fallback',
                                'chunk_count': 1,
                                'text_length': 42,
                                'parser_version': 'documents-adapter:1',
                                'input_format': 'text',
                                'paragraph_count': 1,
                            },
                            'lineage': {
                                'source': 'web_document',
                                'parser_version': 'documents-adapter:1',
                                'input_format': 'text',
                            },
                        },
                },
                'document_parse': {
                    'status': 'fallback',
                    'text': 'Title: Evidence 1\n\nURL: https://example.com/1',
                    'chunks': [
                        {
                            'chunk_id': 'chunk-0',
                            'index': 0,
                            'start': 0,
                            'end': 44,
                            'text': 'Title: Evidence 1\n\nURL: https://example.com/1',
                        }
                    ],
                    'metadata': {'filename': 'evidence-1.txt', 'mime_type': 'text/plain'},
                },
            })
            
            mock_mediator.evidence_state = Mock()
            mock_mediator.evidence_state.upsert_evidence_record = Mock(return_value={
                'record_id': 1,
                'created': True,
                'reused': False,
            })
            mock_mediator.evidence_state.persist_scraper_run = Mock(return_value={
                'persisted': True,
                'run_id': 5,
            })
            mock_mediator.claim_support = Mock()
            mock_mediator.claim_support.resolve_claim_element = Mock(return_value={
                'claim_element_id': 'employment_discrimination:1',
                'claim_element_text': 'Protected activity',
            })
            mock_mediator.claim_support.upsert_support_link = Mock(return_value={
                'record_id': 1,
                'created': True,
                'reused': False,
            })
            
            hook = WebEvidenceIntegrationHook(mock_mediator)
            
            result = hook.discover_and_store_evidence(
                keywords=['employment', 'discrimination'],
                user_id='testuser',
                claim_type='employment discrimination',
                min_relevance=0.5
            )
            
            assert isinstance(result, dict)
            assert 'discovered' in result
            assert 'stored' in result
            assert 'stored_new' in result
            assert 'reused' in result
            assert 'total_records' in result
            assert 'total_new' in result
            assert 'total_reused' in result
            assert 'support_links_added' in result
            assert 'support_links_reused' in result
            assert 'total_support_links_added' in result
            assert 'total_support_links_reused' in result
            assert result['discovered'] == 2
            assert result['stored_new'] == 2
            assert result['reused'] == 0
            assert result['total_records'] == 2
            assert result['total_new'] == 2
            assert result['total_reused'] == 0
            assert result['support_links_added'] == 2
            assert result['total_support_links_added'] == 2
            assert result['total_support_links_reused'] == 0
            assert result['parse_summary']['processed'] == 2
            assert result['parse_summary']['total_chunks'] == 2
            assert result['parse_summary']['total_paragraphs'] == 2
            assert result['parse_summary']['total_text_length'] == 84
            assert result['parse_summary']['total_pages'] == 2
            assert result['parse_summary']['status_counts']['fallback'] == 2
            assert result['parse_summary']['input_format_counts']['text'] == 2
            assert result['parse_summary']['quality_tier_counts']['high'] == 2
            assert result['parse_summary']['avg_quality_score'] > 90.0
            assert 'documents-adapter:1' in result['parse_summary']['parser_versions']
            assert len(result['parse_details']) == 2
            assert result['parse_details'][0]['parser_version'] == 'documents-adapter:1'
            assert result['parse_details'][0]['input_format'] == 'text'
            assert result['parse_details'][0]['extraction_method'] == 'text_normalization'
            assert result['parse_details'][0]['quality_tier'] == 'high'
            assert result['parse_details'][0]['quality_score'] > 90.0
            assert result['parse_details'][0]['source'] == 'web_document'
            assert result['parse_details'][0]['lineage']['source'] == 'web_document'
            assert len(result['graph_projection']) == 2
            assert result['graph_projection'][0]['graph_changed'] is True
            assert result['graph_projection'][0]['artifact_entity_added'] is True
            assert result['graph_projection'][0]['storage_record_reused'] is False
            graph_kwargs = mock_mediator.add_evidence_to_graphs.call_args.args[0]
            assert graph_kwargs['record_created'] is True
            assert graph_kwargs['record_reused'] is False
            assert graph_kwargs['support_link_created'] is True
            assert graph_kwargs['support_link_reused'] is False
            store_kwargs = mock_mediator.evidence_storage.store_evidence.call_args.kwargs
            assert store_kwargs['evidence_type'] == 'web_document'
            assert store_kwargs['metadata']['parse_document'] is True
            assert store_kwargs['metadata']['parse_source'] == 'web_document'
            assert store_kwargs['metadata']['mime_type'] == 'text/plain'
            assert store_kwargs['metadata']['filename'] == 'evidence-2.txt'
            payload_text = store_kwargs['data'].decode('utf-8')
            assert 'Title: Evidence 2' in payload_text
            assert 'URL: https://example.com/2' in payload_text
            assert 'Content:' in payload_text
            add_record_kwargs = mock_mediator.evidence_state.upsert_evidence_record.call_args.kwargs
            assert add_record_kwargs['claim_element_id'] == 'employment_discrimination:1'
            assert add_record_kwargs['claim_element'] == 'Protected activity'
            assert add_record_kwargs['evidence_info']['document_parse']['status'] == 'fallback'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_store_evidence_items_preserves_html_parse_contract(self):
        """Test discovered HTML evidence preserves HTML parse metadata through storage."""
        try:
            from mediator.evidence_hooks import EvidenceStorageHook
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.state.complaint_id = 'complaint-1'
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(return_value=None)
            mock_mediator.add_evidence_to_graphs = Mock(return_value={})
            mock_mediator.web_evidence_search = Mock()
            mock_mediator.web_evidence_search.validate_evidence = Mock(return_value={
                'valid': True,
                'relevance_score': 0.9,
            })
            mock_mediator.evidence_storage = EvidenceStorageHook(mock_mediator)
            mock_mediator.evidence_state = Mock()
            mock_mediator.evidence_state.upsert_evidence_record = Mock(return_value={
                'record_id': 1,
                'created': True,
                'reused': False,
            })
            mock_mediator.claim_support = Mock()
            mock_mediator.claim_support.resolve_claim_element = Mock(return_value={
                'claim_element_id': 'employment_discrimination:1',
                'claim_element_text': 'Protected activity',
            })
            mock_mediator.claim_support.upsert_support_link = Mock(return_value={
                'record_id': 1,
                'created': True,
                'reused': False,
            })

            hook = WebEvidenceIntegrationHook(mock_mediator)
            result = hook._store_evidence_items(
                [
                    {
                        'title': 'Policy page',
                        'url': 'https://example.com/policy',
                        'content': '<html><body><h1>Policy</h1><p>Retaliation is prohibited.</p></body></html>',
                        'source_type': 'web',
                    }
                ],
                keywords=['retaliation'],
                user_id='testuser',
                claim_type='employment discrimination',
                min_relevance=0.5,
            )

            assert result['stored'] == 1
            assert result['parse_summary']['input_format_counts']['html'] == 1
            assert result['parse_summary']['quality_tier_counts']['high'] == 1
            assert result['parse_details'][0]['input_format'] == 'html'
            assert result['parse_details'][0]['extraction_method'] == 'html_to_text'
            assert result['parse_details'][0]['lineage']['artifact_family'] == 'live_web_page'
            assert result['parse_details'][0]['lineage']['corpus_family'] == 'web_page'
            add_record_kwargs = mock_mediator.evidence_state.upsert_evidence_record.call_args.kwargs
            assert add_record_kwargs['evidence_info']['document_parse']['summary']['input_format'] == 'html'
            assert add_record_kwargs['evidence_info']['document_parse']['summary']['quality_tier'] == 'high'
            assert add_record_kwargs['evidence_info']['metadata']['document_parse_contract']['lineage']['input_format'] == 'html'
            assert add_record_kwargs['evidence_info']['metadata']['document_parse_contract']['parse_quality']['quality_tier'] == 'high'
            assert add_record_kwargs['evidence_info']['metadata']['provenance']['metadata']['artifact_family'] == 'live_web_page'
            support_kwargs = mock_mediator.claim_support.upsert_support_link.call_args.kwargs
            assert support_kwargs['metadata']['source_type'] == 'web'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_store_evidence_items_normalizes_archive_lineage(self):
        """Test archived web evidence records historical capture context in parse lineage."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.state.complaint_id = 'complaint-1'
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(return_value=None)
            mock_mediator.web_evidence_search = Mock()
            mock_mediator.web_evidence_search.validate_evidence = Mock(return_value={
                'valid': True,
                'relevance_score': 0.82,
            })
            mock_mediator.evidence_storage = Mock()
            mock_mediator.evidence_storage.store_evidence = Mock(return_value={
                'cid': 'QmArchive123',
                'size': 180,
                'type': 'web_document',
                'metadata': {
                    'document_parse_summary': {
                        'status': 'available-fallback',
                        'chunk_count': 1,
                        'text_length': 64,
                        'parser_version': 'documents-adapter:1',
                        'input_format': 'html',
                        'paragraph_count': 1,
                    },
                    'document_parse_contract': {
                        'status': 'available-fallback',
                        'source': 'web_document',
                        'chunk_count': 1,
                        'summary': {
                            'status': 'available-fallback',
                            'chunk_count': 1,
                            'text_length': 64,
                            'parser_version': 'documents-adapter:1',
                            'input_format': 'html',
                            'paragraph_count': 1,
                        },
                        'lineage': {
                            'source': 'web_document',
                            'parser_version': 'documents-adapter:1',
                            'input_format': 'html',
                            'normalization': 'html_to_text',
                        },
                    },
                },
                'document_parse': {
                    'status': 'available-fallback',
                    'text': 'Archived policy snapshot',
                    'summary': {
                        'status': 'available-fallback',
                        'chunk_count': 1,
                        'text_length': 23,
                        'parser_version': 'documents-adapter:1',
                        'input_format': 'html',
                        'paragraph_count': 1,
                        'page_count': 1,
                        'extraction_method': 'html_to_text',
                        'quality_tier': 'high',
                        'quality_score': 95.0,
                    },
                    'lineage': {
                        'source': 'web_document',
                        'parser_version': 'documents-adapter:1',
                        'input_format': 'html',
                        'normalization': 'html_to_text',
                    },
                    'chunks': [
                        {
                            'chunk_id': 'chunk-0',
                            'index': 0,
                            'start': 0,
                            'end': 23,
                            'text': 'Archived policy snapshot',
                        }
                    ],
                    'metadata': {
                        'filename': 'policy-page.html',
                        'mime_type': 'text/html',
                        'input_format': 'html',
                        'parse_quality': {
                            'quality_score': 95.0,
                            'quality_tier': 'high',
                        },
                        'source_span': {
                            'page_count': 1,
                            'text_length': 23,
                        },
                        'transform_lineage': {
                            'source': 'web_document',
                            'parser_version': 'documents-adapter:1',
                            'input_format': 'html',
                            'normalization': 'html_to_text',
                        },
                    },
                },
            })

            mock_mediator.evidence_state = Mock()
            mock_mediator.evidence_state.upsert_evidence_record = Mock(return_value={
                'record_id': 7,
                'created': True,
                'reused': False,
            })

            hook = WebEvidenceIntegrationHook(mock_mediator)
            result = hook._store_evidence_items(
                [
                    {
                        'title': 'Archived policy page',
                        'url': 'https://web.archive.org/web/20240101120000/https://example.com/policy',
                        'content': '<html><body><p>Archived policy snapshot</p></body></html>',
                        'source_type': 'archived_domain_scrape',
                        'discovered_at': '2024-01-02T00:00:00Z',
                        'metadata': {
                            'archive_url': 'https://web.archive.org/web/20240101120000/https://example.com/policy',
                            'original_url': 'https://example.com/policy',
                            'captured_at': '2024-01-01T12:00:00Z',
                            'original_source_type': 'common_crawl',
                        },
                    }
                ],
                keywords=['policy'],
                user_id='testuser',
                claim_type=None,
                min_relevance=0.5,
            )

            assert result['stored_new'] == 1
            assert result['parse_details'][0]['lineage']['content_origin'] == 'historical_archive_capture'
            assert result['parse_details'][0]['lineage']['artifact_family'] == 'archived_web_page'
            assert result['parse_details'][0]['lineage']['corpus_family'] == 'web_page'
            assert result['parse_details'][0]['lineage']['historical_capture'] is True
            assert result['parse_details'][0]['lineage']['capture_source'] == 'archived_domain_scrape'
            assert result['parse_details'][0]['lineage']['archive_url'] == 'https://web.archive.org/web/20240101120000/https://example.com/policy'
            assert result['parse_details'][0]['lineage']['version_of'] == 'https://example.com/policy'
            persisted_info = mock_mediator.evidence_state.upsert_evidence_record.call_args.kwargs['evidence_info']
            persisted_lineage = persisted_info['document_parse']['metadata']['transform_lineage']
            assert persisted_lineage['content_origin'] == 'historical_archive_capture'
            assert persisted_lineage['artifact_family'] == 'archived_web_page'
            assert persisted_lineage['captured_at'] == '2024-01-01T12:00:00Z'
            assert persisted_lineage['observed_at'] == '2024-01-02T00:00:00Z'
            persisted_provenance = persisted_info['metadata']['provenance']
            assert persisted_provenance['metadata']['artifact_family'] == 'archived_web_page'
            assert persisted_provenance['metadata']['content_origin'] == 'historical_archive_capture'
            assert persisted_provenance['metadata']['archive_url'] == 'https://web.archive.org/web/20240101120000/https://example.com/policy'
            assert persisted_provenance['metadata']['version_of'] == 'https://example.com/policy'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_store_evidence_items_persists_archived_web_fact_contract(self):
        """Test archived web evidence facts round-trip through the shared evidence fact contract."""
        try:
            from mediator.evidence_hooks import EvidenceStateHook, EvidenceStorageHook
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.state.complaint_id = 'complaint-1'
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(return_value=None)
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for archived web evidence persistence',
                    'confirmation_source': 'dashboard',
                    'summary_snapshot_index': 0,
                    'current_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 2,
                        'proof_lead_count': 1,
                    },
                    'confirmed_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 2,
                        'proof_lead_count': 1,
                    },
                },
            })
            mock_mediator.web_evidence_search = Mock()
            mock_mediator.web_evidence_search.validate_evidence = Mock(return_value={
                'valid': True,
                'relevance_score': 0.88,
            })
            mock_mediator.evidence_storage = EvidenceStorageHook(mock_mediator)

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                mock_mediator.evidence_state = EvidenceStateHook(mock_mediator, db_path=db_path)
                actual_upsert_evidence_record = mock_mediator.evidence_state.upsert_evidence_record
                mock_mediator.evidence_state.upsert_evidence_record = MagicMock(side_effect=actual_upsert_evidence_record)

                hook = WebEvidenceIntegrationHook(mock_mediator)
                result = hook._store_evidence_items(
                    [
                        {
                            'title': 'Archived discrimination policy',
                            'url': 'https://web.archive.org/web/20240101120000/https://example.com/policy',
                            'content': '<html><body><p>Employees may report discrimination to HR without retaliation.</p></body></html>',
                            'source_type': 'archived_domain_scrape',
                            'discovered_at': '2024-01-02T00:00:00Z',
                            'metadata': {
                                'archive_url': 'https://web.archive.org/web/20240101120000/https://example.com/policy',
                                'original_url': 'https://example.com/policy',
                                'captured_at': '2024-01-01T12:00:00Z',
                                'original_source_type': 'common_crawl',
                            },
                        }
                    ],
                    keywords=['discrimination', 'retaliation'],
                    user_id='testuser',
                    claim_type=None,
                    min_relevance=0.5,
                )

                assert result['stored_new'] == 1
                persisted_info = mock_mediator.evidence_state.upsert_evidence_record.call_args.kwargs['evidence_info']
                assert persisted_info['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T21:00:00+00:00',
                        'confirmation_note': 'ready for archived web evidence persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 2,
                            'proof_lead_count': 1,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 2,
                            'proof_lead_count': 1,
                        },
                    },
                }
                assert persisted_info['metadata']['provenance']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T21:00:00+00:00',
                        'confirmation_note': 'ready for archived web evidence persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 2,
                            'proof_lead_count': 1,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 2,
                            'proof_lead_count': 1,
                        },
                    },
                }
                assert persisted_info['provenance']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T21:00:00+00:00',
                        'confirmation_note': 'ready for archived web evidence persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 2,
                            'proof_lead_count': 1,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 2,
                            'proof_lead_count': 1,
                        },
                    },
                }
                record = mock_mediator.evidence_state.get_evidence_by_cid(result['evidence_cids'][0])
                assert record is not None
                facts = mock_mediator.evidence_state.get_evidence_facts(record['id'])

                assert len(facts) >= 1
                assert facts[0]['fact_id'].startswith('fact:')
                assert facts[0]['source_family'] == 'evidence'
                assert facts[0]['source_record_id'] == record['id']
                assert facts[0]['record_scope'] == 'evidence'
                assert facts[0]['source_artifact_id']
                assert facts[0]['source_ref'] == facts[0]['source_artifact_id']
                assert facts[0]['artifact_family'] == 'archived_web_page'
                assert facts[0]['corpus_family'] == 'web_page'
                assert facts[0]['content_origin'] == 'historical_archive_capture'
                assert facts[0]['parse_source'] == 'web_document'
                assert facts[0]['input_format'] == 'html'
                assert facts[0]['quality_tier'] == 'high'
                assert facts[0]['quality_score'] > 0.0
                assert facts[0]['metadata']['parse_lineage']['source'] == 'web_document'
                assert facts[0]['provenance']['metadata']['artifact_family'] == 'archived_web_page'
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_discover_and_store_evidence_reports_reuse_counts(self):
        """Test reused evidence rows and support links are surfaced in results."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(return_value=object())
            mock_mediator.add_evidence_to_graphs = Mock(return_value={
                'graph_projection': {
                    'projected': True,
                    'graph_changed': False,
                    'entity_count': 0,
                    'relationship_count': 0,
                    'claim_links': 1,
                    'artifact_entity_added': False,
                    'artifact_entity_already_present': True,
                    'storage_record_created': False,
                    'storage_record_reused': True,
                    'support_link_created': False,
                    'support_link_reused': True,
                }
            })
            mock_mediator.web_evidence_search = Mock()
            mock_mediator.web_evidence_search.search_for_evidence = Mock(return_value={
                'total_found': 1,
                'brave_search': [
                    {
                        'title': 'Evidence 1',
                        'url': 'https://example.com/1',
                        'content': 'Content 1',
                        'source_type': 'brave_search'
                    }
                ],
                'common_crawl': []
            })
            mock_mediator.web_evidence_search.validate_evidence = Mock(return_value={
                'valid': True,
                'relevance_score': 0.8
            })

            mock_mediator.evidence_storage = Mock()
            mock_mediator.evidence_storage.store_evidence = Mock(return_value={
                'cid': 'QmTest123',
                'size': 100,
                'type': 'web_document',
                'metadata': {},
            })

            mock_mediator.evidence_state = Mock()
            mock_mediator.evidence_state.upsert_evidence_record = Mock(return_value={
                'record_id': 7,
                'created': False,
                'reused': True,
            })
            mock_mediator.claim_support = Mock()
            mock_mediator.claim_support.resolve_claim_element = Mock(return_value={
                'claim_element_id': 'employment_discrimination:1',
                'claim_element_text': 'Protected activity',
            })
            mock_mediator.claim_support.upsert_support_link = Mock(return_value={
                'record_id': 11,
                'created': False,
                'reused': True,
            })

            hook = WebEvidenceIntegrationHook(mock_mediator)

            result = hook.discover_and_store_evidence(
                keywords=['employment', 'discrimination'],
                user_id='testuser',
                claim_type='employment discrimination',
                min_relevance=0.5
            )

            assert result['stored'] == 1
            assert result['stored_new'] == 0
            assert result['reused'] == 1
            assert result['total_records'] == 1
            assert result['total_new'] == 0
            assert result['total_reused'] == 1
            assert result['support_links_added'] == 0
            assert result['total_support_links_added'] == 0
            assert len(result['graph_projection']) == 1
            assert result['graph_projection'][0]['claim_links'] == 1
            assert result['graph_projection'][0]['graph_changed'] is False
            assert result['graph_projection'][0]['artifact_entity_already_present'] is True
            assert result['graph_projection'][0]['storage_record_reused'] is True
            assert result['parse_summary']['processed'] == 1
            assert result['parse_summary']['total_chunks'] == 0
            assert result['parse_summary']['status_counts'] == {}
            assert len(result['parse_details']) == 1
            assert result['parse_details'][0]['status'] == ''
            graph_kwargs = mock_mediator.add_evidence_to_graphs.call_args.args[0]
            assert graph_kwargs['record_created'] is False
            assert graph_kwargs['record_reused'] is True
            assert graph_kwargs['support_link_created'] is False
            assert graph_kwargs['support_link_reused'] is True
            assert mock_mediator.add_evidence_to_graphs.call_count == 1
            assert result['support_links_reused'] == 1
            assert result['total_support_links_reused'] == 1
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_generate_search_keywords(self):
        """Test search keyword generation"""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="discrimination\nemployment\nwrongful termination")
            mock_mediator.summarize_claim_support = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'total_links': 1,
                        'support_by_kind': {'evidence': 1},
                        'links': [],
                    }
                }
            })
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.state.complaint = 'test complaint'
            mock_mediator.state.legal_classification = {
                'claim_types': ['employment discrimination']
            }
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for case evidence discovery',
                    'confirmation_source': 'dashboard',
                    'summary_snapshot_index': 0,
                    'current_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                    'confirmed_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                },
            })
            
            hook = WebEvidenceIntegrationHook(mock_mediator)
            
            keywords = hook._generate_search_keywords('employment discrimination')
            
            assert isinstance(keywords, list)
            assert len(keywords) > 0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_get_search_hook_uses_mediator_search_hook(self):
        """Test lazy search-hook initialization reuses mediator.web_evidence_search."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.web_evidence_search = Mock()

            hook = WebEvidenceIntegrationHook(mock_mediator)

            assert hook._get_search_hook() is mock_mediator.web_evidence_search
            assert hook._get_search_hook() is mock_mediator.web_evidence_search
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_discover_evidence_for_case_includes_support_summary(self):
        """Test auto-discovery returns per-claim support summaries."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.state.complaint = 'test complaint'
            mock_mediator.state.legal_classification = {
                'claim_types': ['employment discrimination']
            }
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for case evidence discovery',
                    'confirmation_source': 'dashboard',
                    'summary_snapshot_index': 0,
                    'current_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                    'confirmed_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                },
            })
            mock_mediator.summarize_claim_support = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'total_links': 2,
                        'support_by_kind': {'evidence': 2},
                        'links': [],
                    }
                }
            })
            mock_mediator.get_claim_overview = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'required_support_kinds': ['evidence', 'authority'],
                        'covered': [],
                        'partially_supported': [
                            {'element_text': 'Protected activity'}
                        ],
                        'missing': [
                            {'element_text': 'Adverse action'}
                        ],
                        'covered_count': 0,
                        'partially_supported_count': 1,
                        'missing_count': 1,
                        'total_elements': 2,
                    }
                }
            })
            mock_mediator.get_claim_coverage_matrix = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'claim_type': 'employment discrimination',
                        'required_support_kinds': ['evidence', 'authority'],
                        'total_elements': 2,
                        'status_counts': {
                            'covered': 0,
                            'partially_supported': 1,
                            'missing': 1,
                        },
                        'total_links': 2,
                        'total_facts': 2,
                        'support_by_kind': {'evidence': 2},
                        'elements': [],
                        'unassigned_links': [],
                    }
                }
            })
            mock_mediator.get_claim_follow_up_plan = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'task_count': 2,
                        'blocked_task_count': 1,
                        'tasks': [
                            {
                                'claim_element': 'Protected activity',
                                'status': 'partially_supported',
                                'missing_support_kinds': ['authority'],
                                'has_graph_support': True,
                                'recommended_action': 'review_existing_support',
                                'should_suppress_retrieval': True,
                                'resolution_applied': 'manual_review_resolved',
                                'adaptive_retry_state': {
                                    'applied': True,
                                    'priority_penalty': 1,
                                    'adaptive_query_strategy': 'standard_gap_targeted',
                                    'reason': 'repeated_zero_result_reasoning_gap',
                                    'latest_attempted_at': '2026-03-12T10:19:00',
                                },
                                'graph_support': {
                                    'summary': {
                                        'semantic_cluster_count': 1,
                                        'semantic_duplicate_count': 2,
                                    }
                                },
                            },
                            {
                                'claim_element': 'Adverse action',
                                'status': 'missing',
                                'missing_support_kinds': ['evidence', 'authority'],
                                'has_graph_support': False,
                                'recommended_action': 'retrieve_more_support',
                                'should_suppress_retrieval': False,
                                'graph_support': {
                                    'summary': {
                                        'semantic_cluster_count': 0,
                                        'semantic_duplicate_count': 0,
                                    }
                                },
                            },
                        ],
                    }
                }
            })
            mock_mediator.get_claim_support_gaps = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'unresolved_count': 2,
                        'unresolved_elements': [
                            {
                                'element_text': 'Protected activity',
                                'recommended_action': 'collect_missing_support_kind',
                            },
                            {
                                'element_text': 'Adverse action',
                                'recommended_action': 'collect_initial_support',
                            },
                        ],
                    }
                }
            })
            mock_mediator.get_claim_contradiction_candidates = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'candidate_count': 1,
                        'candidates': [
                            {
                                'claim_element_text': 'Protected activity',
                            }
                        ],
                    }
                }
            })
            mock_mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'claim_type': 'employment discrimination',
                        'validation_status': 'contradicted',
                        'validation_status_counts': {
                            'supported': 0,
                            'incomplete': 1,
                            'missing': 1,
                            'contradicted': 1,
                        },
                        'proof_gap_count': 3,
                        'proof_diagnostics': {
                            'reasoning': {
                                'adapter_status_counts': {
                                    'logic_proof': {'implemented': 1},
                                    'logic_contradictions': {'implemented': 1},
                                    'hybrid_reasoning': {'implemented': 1},
                                    'ontology_build': {'implemented': 1},
                                    'ontology_validation': {'implemented': 1},
                                },
                                'backend_available_count': 4,
                                'predicate_count': 4,
                                'ontology_entity_count': 0,
                                'ontology_relationship_count': 0,
                                'fallback_ontology_count': 0,
                                'hybrid_bridge_available_count': 1,
                                'hybrid_tdfol_formula_count': 2,
                                'hybrid_dcec_formula_count': 1,
                            },
                            'decision': {
                                'decision_source_counts': {
                                    'logic_proof_supported': 1,
                                },
                            },
                        },
                        'elements': [
                            {
                                'element_id': 'employment discrimination:1',
                                'element_text': 'Protected activity',
                                'validation_status': 'supported',
                                'proof_diagnostics': {
                                    'decision_source': 'logic_proof_supported',
                                },
                                'reasoning_diagnostics': {
                                    'predicate_count': 4,
                                    'backend_available_count': 4,
                                    'used_fallback_ontology': False,
                                    'adapter_statuses': {
                                        'logic_proof': {
                                            'backend_available': True,
                                            'implementation_status': 'implemented',
                                        },
                                        'logic_contradictions': {
                                            'backend_available': True,
                                            'implementation_status': 'implemented',
                                        },
                                        'hybrid_reasoning': {
                                            'backend_available': True,
                                            'implementation_status': 'implemented',
                                            'operation': 'run_hybrid_reasoning',
                                        },
                                        'ontology_build': {
                                            'backend_available': True,
                                            'implementation_status': 'implemented',
                                        },
                                        'ontology_validation': {
                                            'backend_available': True,
                                            'implementation_status': 'implemented',
                                        },
                                    },
                                    'hybrid_reasoning': {
                                        'status': 'success',
                                        'result': {
                                            'compiler_bridge_available': True,
                                            'tdfol_formulas': [
                                                'Before(fact_1,fact_2)',
                                                'forall t (AtTime(t,t_2026_03_10) -> Fact(fact_1,t))',
                                            ],
                                            'dcec_formulas': [
                                                'Happens(fact_1,t_2026_03_10)',
                                            ],
                                        },
                                    },
                                },
                            }
                        ],
                    }
                }
            })
            mock_mediator.get_recent_claim_follow_up_execution = Mock(return_value={
                'claims': {
                    'employment discrimination': [
                        {
                            'support_kind': 'manual_review',
                            'status': 'skipped_manual_review',
                            'execution_mode': 'manual_review',
                            'validation_status': 'contradicted',
                            'follow_up_focus': 'contradiction_resolution',
                            'query_strategy': 'standard_gap_targeted',
                            'timestamp': '2026-03-12T10:20:00',
                        }
                    ]
                }
            })
            mock_mediator.persist_claim_support_diagnostics = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'snapshots': {
                            'gaps': {'snapshot_id': 101},
                            'contradictions': {'snapshot_id': 102},
                        }
                    }
                }
            })

            with patch(
                'claim_support_review._utcnow',
                return_value=datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc),
            ):
                hook = WebEvidenceIntegrationHook(mock_mediator)
                hook._generate_search_keywords = Mock(return_value=['employment discrimination'])
                hook.discover_and_store_evidence = Mock(return_value={
                    'discovered': 3,
                    'stored': 2,
                    'stored_new': 1,
                    'reused': 1,
                    'support_links_added': 2,
                    'support_links_reused': 0,
                    'total_records': 2,
                    'total_new': 1,
                    'total_reused': 1,
                    'total_support_links_added': 2,
                    'total_support_links_reused': 0,
                })

                result = hook.discover_evidence_for_case(user_id='testuser')

            assert result['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for case evidence discovery',
                    'confirmation_source': 'dashboard',
                    'summary_snapshot_index': 0,
                    'current_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                    'confirmed_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                },
            }
            assert result['evidence_storage_summary']['employment discrimination']['total_records'] == 2
            assert result['evidence_storage_summary']['employment discrimination']['total_new'] == 1
            assert result['evidence_storage_summary']['employment discrimination']['total_reused'] == 1
            assert result['support_summary']['employment discrimination']['total_links'] == 2
            assert result['claim_coverage_matrix']['employment discrimination']['status_counts']['partially_supported'] == 1
            assert result['claim_coverage_summary']['employment discrimination']['status_counts']['partially_supported'] == 1
            assert result['claim_coverage_summary']['employment discrimination']['status_counts']['missing'] == 1
            assert result['claim_coverage_summary']['employment discrimination']['missing_elements'] == ['Adverse action']
            assert result['claim_coverage_summary']['employment discrimination']['partially_supported_elements'] == ['Protected activity']
            assert result['claim_coverage_summary']['employment discrimination']['unresolved_element_count'] == 2
            assert result['claim_coverage_summary']['employment discrimination']['recommended_gap_actions'] == {
                'collect_missing_support_kind': 1,
                'collect_initial_support': 1,
            }
            assert result['claim_coverage_summary']['employment discrimination']['contradiction_candidate_count'] == 1
            assert result['claim_coverage_summary']['employment discrimination']['validation_status'] == 'contradicted'
            assert result['claim_support_validation']['employment discrimination']['proof_gap_count'] == 3
            assert result['claim_support_gaps']['employment discrimination']['unresolved_count'] == 2
            assert result['claim_contradiction_candidates']['employment discrimination']['candidate_count'] == 1
            assert result['claim_support_snapshots']['employment discrimination']['gaps']['snapshot_id'] == 101
            assert result['claim_support_snapshots']['employment discrimination']['contradictions']['snapshot_id'] == 102
            assert result['claim_support_snapshot_summary']['employment discrimination']['total_snapshot_count'] == 2
            assert result['claim_support_snapshot_summary']['employment discrimination']['fresh_snapshot_count'] == 2
            assert result['claim_support_snapshot_summary']['employment discrimination']['stale_snapshot_count'] == 0
            assert result['claim_reasoning_review']['employment discrimination']['total_element_count'] == len(
                result['claim_support_validation']['employment discrimination']['elements']
            )
            assert result['claim_coverage_summary']['employment discrimination']['reasoning_hybrid_bridge_available_count'] == 1
            assert result['claim_coverage_summary']['employment discrimination']['reasoning_hybrid_tdfol_formula_count'] == 2
            assert result['claim_coverage_summary']['employment discrimination']['reasoning_hybrid_dcec_formula_count'] == 1
            assert result['claim_reasoning_review']['employment discrimination']['hybrid_bridge_element_count'] == 1
            assert result['claim_reasoning_review']['employment discrimination']['hybrid_bridge_available_element_count'] == 1
            assert result['claim_reasoning_review']['employment discrimination']['hybrid_tdfol_formula_count'] == 2
            assert result['claim_reasoning_review']['employment discrimination']['hybrid_dcec_formula_count'] == 1
            assert result['claim_overview']['employment discrimination']['missing_count'] == 1
            assert result['follow_up_plan']['employment discrimination']['task_count'] == 2
            assert result['follow_up_plan_summary']['employment discrimination']['task_count'] == 2
            assert result['follow_up_plan_summary']['employment discrimination']['blocked_task_count'] == 1
            assert result['follow_up_plan_summary']['employment discrimination']['graph_supported_task_count'] == 1
            assert result['follow_up_plan_summary']['employment discrimination']['suppressed_task_count'] == 1
            assert result['follow_up_plan_summary']['employment discrimination']['contradiction_task_count'] == 0
            assert result['follow_up_plan_summary']['employment discrimination']['reasoning_gap_task_count'] == 0
            assert result['follow_up_plan_summary']['employment discrimination']['semantic_cluster_count'] == 1
            assert result['follow_up_plan_summary']['employment discrimination']['semantic_duplicate_count'] == 2
            assert result['follow_up_plan_summary']['employment discrimination']['follow_up_focus_counts'] == {
                'unknown': 2,
            }
            assert result['follow_up_plan_summary']['employment discrimination']['query_strategy_counts'] == {
                'unknown': 2,
            }
            assert result['follow_up_plan_summary']['employment discrimination']['proof_decision_source_counts'] == {
                'unknown': 2,
            }
            assert result['follow_up_plan_summary']['employment discrimination']['resolution_applied_counts'] == {
                'manual_review_resolved': 1,
            }
            assert result['follow_up_plan_summary']['employment discrimination']['adaptive_retry_task_count'] == 1
            assert result['follow_up_plan_summary']['employment discrimination']['priority_penalized_task_count'] == 1
            assert result['follow_up_plan_summary']['employment discrimination']['adaptive_query_strategy_counts'] == {
                'standard_gap_targeted': 1,
            }
            assert result['follow_up_plan_summary']['employment discrimination']['adaptive_retry_reason_counts'] == {
                'repeated_zero_result_reasoning_gap': 1,
            }
            assert result['follow_up_plan_summary']['employment discrimination']['last_adaptive_retry'] == {
                'claim_element_id': None,
                'claim_element_text': 'Protected activity',
                'timestamp': '2026-03-12T10:19:00',
                'adaptive_query_strategy': 'standard_gap_targeted',
                'reason': 'repeated_zero_result_reasoning_gap',
                'recency_bucket': 'fresh',
                'is_stale': False,
            }
            assert result['follow_up_plan_summary']['employment discrimination']['recommended_actions']['review_existing_support'] == 1
            assert result['follow_up_history']['employment discrimination'][0]['support_kind'] == 'manual_review'
            assert result['follow_up_history_summary']['employment discrimination']['manual_review_entry_count'] == 1
            assert result['follow_up_history_summary']['employment discrimination']['contradiction_related_entry_count'] == 1
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_discover_evidence_for_case_can_execute_follow_up(self):
        """Test auto-discovery can execute evidence follow-up tasks."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.state.complaint = 'test complaint'
            mock_mediator.state.legal_classification = {
                'claim_types': ['employment discrimination']
            }
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for case evidence discovery',
                    'confirmation_source': 'dashboard',
                    'summary_snapshot_index': 0,
                    'current_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                    'confirmed_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                },
            })
            mock_mediator.summarize_claim_support = Mock(return_value={'claims': {}})
            mock_mediator.get_claim_coverage_matrix = Mock(return_value={'claims': {}})
            mock_mediator.get_claim_overview = Mock(return_value={'claims': {}})
            mock_mediator.get_claim_support_gaps = Mock(return_value={'claims': {}})
            mock_mediator.get_claim_contradiction_candidates = Mock(return_value={'claims': {}})
            mock_mediator.get_claim_support_validation = Mock(return_value={'claims': {}})
            mock_mediator.persist_claim_support_diagnostics = Mock(return_value={'claims': {}})
            mock_mediator.get_claim_follow_up_plan = Mock(return_value={'claims': {}})
            mock_mediator.get_recent_claim_follow_up_execution = Mock(side_effect=[
                {'claims': {'employment discrimination': []}},
                {'claims': {'employment discrimination': [
                    {
                        'support_kind': 'evidence',
                        'status': 'executed',
                        'execution_mode': 'review_and_retrieve',
                        'validation_status': 'contradicted',
                        'follow_up_focus': 'contradiction_resolution',
                        'query_strategy': 'contradiction_targeted',
                        'claim_element_id': 'employment discrimination:2',
                        'claim_element_text': 'Adverse action',
                        'adaptive_retry_applied': True,
                        'adaptive_retry_reason': 'repeated_zero_result_reasoning_gap',
                        'adaptive_query_strategy': 'standard_gap_targeted',
                        'adaptive_priority_penalty': 1,
                        'zero_result': True,
                        'source_family': 'legal_authority',
                        'record_scope': 'legal_authority',
                        'artifact_family': 'legal_authority_reference',
                        'corpus_family': 'legal_authority',
                        'content_origin': 'authority_reference_fallback',
                        'timestamp': '2026-03-12T11:05:00',
                    },
                    {
                        'support_kind': 'manual_review',
                        'status': 'skipped_manual_review',
                        'execution_mode': 'manual_review',
                        'validation_status': 'contradicted',
                        'follow_up_focus': 'contradiction_resolution',
                        'query_strategy': 'standard_gap_targeted',
                        'timestamp': '2026-03-12T11:04:00',
                    },
                ]}},
            ])
            mock_mediator.execute_claim_follow_up_plan = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'task_count': 1,
                        'tasks': [
                            {
                                'claim_element': 'Adverse action',
                                'resolution_applied': 'manual_review_resolved',
                                'adaptive_retry_state': {
                                    'applied': True,
                                    'priority_penalty': 1,
                                    'adaptive_query_strategy': 'standard_gap_targeted',
                                    'reason': 'repeated_zero_result_reasoning_gap',
                                    'latest_attempted_at': '2026-03-12T11:05:00',
                                },
                                'graph_support': {
                                    'summary': {
                                        'semantic_cluster_count': 1,
                                        'semantic_duplicate_count': 1,
                                        'support_by_kind': {
                                            'authority': 1,
                                        },
                                    },
                                    'results': [
                                        {
                                            'source_family': 'legal_authority',
                                            'record_scope': 'legal_authority',
                                            'artifact_family': 'legal_authority_reference',
                                            'corpus_family': 'legal_authority',
                                            'content_origin': 'authority_reference_fallback',
                                        }
                                    ],
                                },
                            }
                        ],
                        'skipped_tasks': [
                            {
                                'claim_element': 'Protected activity',
                                'graph_support': {
                                    'summary': {
                                        'semantic_cluster_count': 2,
                                        'semantic_duplicate_count': 3,
                                    }
                                },
                                'skipped': {
                                    'suppressed': {
                                        'reason': 'existing_support_high_duplication'
                                    }
                                },
                            }
                        ],
                    }
                }
            })

            with patch(
                'claim_support_review._utcnow',
                return_value=datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc),
            ):
                hook = WebEvidenceIntegrationHook(mock_mediator)
                hook._generate_search_keywords = Mock(return_value=['employment discrimination'])
                hook.discover_and_store_evidence = Mock(return_value={
                    'discovered': 1,
                    'stored': 1,
                    'stored_new': 1,
                    'reused': 0,
                    'support_links_added': 1,
                    'support_links_reused': 0,
                    'total_records': 1,
                    'total_new': 1,
                    'total_reused': 0,
                    'total_support_links_added': 1,
                    'total_support_links_reused': 0,
                })

                result = hook.discover_evidence_for_case(user_id='testuser', execute_follow_up=True)

            assert result['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for case evidence discovery',
                    'confirmation_source': 'dashboard',
                    'summary_snapshot_index': 0,
                    'current_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                    'confirmed_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 1,
                    },
                },
            }
            assert result['evidence_storage_summary']['employment discrimination']['total_records'] == 1
            assert result['follow_up_execution']['employment discrimination']['task_count'] == 1
            assert result['follow_up_execution_summary']['employment discrimination']['executed_task_count'] == 1
            assert result['follow_up_execution_summary']['employment discrimination']['skipped_task_count'] == 1
            assert result['follow_up_execution_summary']['employment discrimination']['suppressed_task_count'] == 1
            assert result['follow_up_execution_summary']['employment discrimination']['semantic_cluster_count'] == 3
            assert result['follow_up_execution_summary']['employment discrimination']['semantic_duplicate_count'] == 4
            assert result['follow_up_execution_summary']['employment discrimination']['support_by_kind'] == {
                'authority': 1,
            }
            assert result['follow_up_execution_summary']['employment discrimination']['source_family_counts'] == {
                'legal_authority': 1,
            }
            assert result['follow_up_execution_summary']['employment discrimination']['artifact_family_counts'] == {
                'legal_authority_reference': 1,
            }
            assert result['follow_up_execution_summary']['employment discrimination']['contradiction_task_count'] == 0
            assert result['follow_up_execution_summary']['employment discrimination']['reasoning_gap_task_count'] == 0
            assert result['follow_up_execution_summary']['employment discrimination']['follow_up_focus_counts'] == {
                'unknown': 2,
            }
            assert result['follow_up_execution_summary']['employment discrimination']['proof_decision_source_counts'] == {
                'unknown': 2,
            }
            assert result['follow_up_execution_summary']['employment discrimination']['resolution_applied_counts'] == {
                'manual_review_resolved': 1,
            }
            assert result['follow_up_execution_summary']['employment discrimination']['adaptive_retry_task_count'] == 1
            assert result['follow_up_execution_summary']['employment discrimination']['priority_penalized_task_count'] == 1
            assert result['follow_up_execution_summary']['employment discrimination']['adaptive_query_strategy_counts'] == {
                'standard_gap_targeted': 1,
            }
            assert result['follow_up_execution_summary']['employment discrimination']['adaptive_retry_reason_counts'] == {
                'repeated_zero_result_reasoning_gap': 1,
            }
            assert result['follow_up_execution_summary']['employment discrimination']['last_adaptive_retry'] == {
                'claim_element_id': None,
                'claim_element_text': 'Adverse action',
                'timestamp': '2026-03-12T11:05:00',
                'adaptive_query_strategy': 'standard_gap_targeted',
                'reason': 'repeated_zero_result_reasoning_gap',
                'recency_bucket': 'fresh',
                'is_stale': False,
            }
            assert result['follow_up_history_summary']['employment discrimination']['total_entry_count'] == 2
            assert result['follow_up_history_summary']['employment discrimination']['manual_review_entry_count'] == 1
            assert result['follow_up_history_summary']['employment discrimination']['adaptive_retry_entry_count'] == 1
            assert result['follow_up_history_summary']['employment discrimination']['priority_penalized_entry_count'] == 1
            assert result['follow_up_history_summary']['employment discrimination']['adaptive_query_strategy_counts'] == {
                'standard_gap_targeted': 1,
            }
            assert result['follow_up_history_summary']['employment discrimination']['adaptive_retry_reason_counts'] == {
                'repeated_zero_result_reasoning_gap': 1,
            }
            assert result['follow_up_history_summary']['employment discrimination']['last_adaptive_retry'] == {
                'claim_element_id': 'employment discrimination:2',
                'claim_element_text': 'Adverse action',
                'timestamp': '2026-03-12T11:05:00',
                'adaptive_query_strategy': 'standard_gap_targeted',
                'reason': 'repeated_zero_result_reasoning_gap',
                'recency_bucket': 'fresh',
                'is_stale': False,
            }
            assert result['follow_up_history_summary']['employment discrimination']['zero_result_entry_count'] == 1
            assert result['follow_up_history_summary']['employment discrimination']['query_strategy_counts'] == {
                'contradiction_targeted': 1,
                'standard_gap_targeted': 1,
            }
            assert result['follow_up_history_summary']['employment discrimination']['source_family_counts'] == {
                'legal_authority': 1,
            }
            assert result['follow_up_history_summary']['employment discrimination']['artifact_family_counts'] == {
                'legal_authority_reference': 1,
            }
            assert result['follow_up_history']['employment discrimination'][0]['source_family'] == 'legal_authority'
            mock_mediator.execute_claim_follow_up_plan.assert_called_once()
            assert mock_mediator.execute_claim_follow_up_plan.call_args.kwargs['support_kind'] == 'evidence'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_run_agentic_scraper_cycle_stores_results_and_persists_run(self):
        """Test daemon results are stored through the normal evidence path and persisted."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(return_value=None)
            mock_mediator.web_evidence_search = Mock()
            mock_mediator.web_evidence_search.validate_evidence = Mock(return_value={
                'valid': True,
                'relevance_score': 0.82,
            })
            mock_mediator.evidence_storage = Mock()
            mock_mediator.evidence_storage.store_evidence = Mock(return_value={
                'cid': 'QmDaemon1',
                'size': 120,
                'type': 'web_document',
                'metadata': {},
            })
            mock_mediator.evidence_state = Mock()
            mock_mediator.evidence_state.upsert_evidence_record = Mock(return_value={
                'record_id': 21,
                'created': True,
                'reused': False,
            })
            mock_mediator.evidence_state.persist_scraper_run = Mock(return_value={
                'persisted': True,
                'run_id': 9,
            })
            mock_mediator.evidence_state.get_scraper_tactic_performance = Mock(return_value={
                'available': True,
                'tactics': [
                    {
                        'name': 'multi_engine_search',
                        'avg_weight': 1.1,
                        'avg_quality_score': 81.0,
                        'novelty_ratio': 0.5,
                    }
                ],
            })

            hook = WebEvidenceIntegrationHook(mock_mediator)

            with patch('mediator.web_evidence_hooks.ScraperDaemon') as daemon_cls:
                daemon_cls.return_value.run.return_value = {
                    'iterations': [
                        {
                            'iteration': 1,
                            'tactics': [
                                {
                                    'name': 'multi_engine_search',
                                    'mode': 'multi_engine_search',
                                    'query': 'employment discrimination',
                                    'weight': 1.2,
                                    'discovered_count': 1,
                                    'scraped_count': 1,
                                    'accepted_count': 1,
                                    'novelty_count': 1,
                                    'quality_score': 82.0,
                                    'quality': {'data_quality_score': 82.0},
                                }
                            ],
                            'discovered_count': 1,
                            'accepted_count': 1,
                            'scraped_count': 1,
                            'coverage': {'unique_urls': 1, 'unique_domains': 1, 'source_diversity': 1},
                            'quality': {'data_quality_score': 82.0},
                            'critique': {'quality_score': 82.0},
                        }
                    ],
                    'final_results': [
                        {
                            'title': 'Policy update',
                            'url': 'https://example.com/policy',
                            'description': 'Policy update content',
                            'content': 'Policy update content',
                            'source_type': 'multi_engine_search',
                            'metadata': {'original_source_type': 'multi_engine_search'},
                        }
                    ],
                    'coverage_ledger': {
                        'https://example.com/policy': {
                            'domain': 'example.com',
                            'source_type': 'multi_engine_search',
                            'last_seen_iteration': 1,
                        }
                    },
                    'tactic_history': {'multi_engine_search': [82.0]},
                    'final_quality': {'data_quality_score': 82.0},
                }

                result = hook.run_agentic_scraper_cycle(
                    keywords=['employment discrimination'],
                    domains=['example.com'],
                    iterations=2,
                    claim_type='employment discrimination',
                )

            assert result['storage_summary']['stored'] == 1
            assert result['storage_summary']['total_new'] == 1
            assert result['scraper_run']['persisted'] is True
            assert result['scraper_run']['run_id'] == 9
            assert result['seeded_tactics'][0]['name'] == 'multi_engine_search'
            persist_kwargs = mock_mediator.evidence_state.persist_scraper_run.call_args.kwargs
            assert persist_kwargs['claim_type'] == 'employment discrimination'
            assert persist_kwargs['stored_summary']['stored'] == 1
            assert persist_kwargs['run_result']['final_results'][0]['url'] == 'https://example.com/policy'
            daemon_run_kwargs = daemon_cls.return_value.run.call_args.kwargs
            assert daemon_run_kwargs['tactics'][0].name == 'multi_engine_search'
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
            from complaint_phases import ComplaintPhase
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.INTAKE,
                'intake_case_file',
                {
                    'candidate_claims': [{'claim_type': 'employment_discrimination'}],
                    'canonical_facts': [{'fact_id': 'fact_001'}],
                    'proof_leads': [{'lead_id': 'lead_001'}],
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for web evidence discovery',
                        'confirmation_source': 'complainant',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 1,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 1,
                        },
                    },
                },
            )
            
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
            assert result['intake_summary_handoff']['current_phase'] == ComplaintPhase.INTAKE.value
            assert result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
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

    @pytest.mark.integration
    def test_mediator_run_agentic_scraper_cycle(self):
        """Test bounded agentic scraper loop through mediator"""
        try:
            from mediator import Mediator
            from complaint_phases import ComplaintPhase

            mock_backend = Mock()
            mock_backend.id = 'test-backend'

            mediator = Mediator(backends=[mock_backend])
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.INTAKE,
                'intake_case_file',
                {
                    'candidate_claims': [{'claim_type': 'employment_discrimination'}],
                    'canonical_facts': [{'fact_id': 'fact_001'}],
                    'proof_leads': [{'lead_id': 'lead_001'}],
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for agentic scraper discovery',
                        'confirmation_source': 'complainant',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 1,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 1,
                        },
                    },
                },
            )
            mediator.web_evidence_integration.run_agentic_scraper_cycle = Mock(return_value={
                'iterations': [{'iteration': 1, 'accepted_count': 2}],
                'final_results': [{'url': 'https://example.com/policy'}],
                'coverage_ledger': {'https://example.com/policy': {'domain': 'example.com'}},
                'storage_summary': {'stored': 1},
                'scraper_run': {'persisted': True, 'run_id': 9},
            })

            result = mediator.run_agentic_scraper_cycle(
                keywords=['employment discrimination'],
                domains=['example.com'],
                iterations=2,
            )

            assert isinstance(result, dict)
            assert 'iterations' in result
            assert result['final_results'][0]['url'] == 'https://example.com/policy'
            assert result['scraper_run']['persisted'] is True
            assert result['intake_summary_handoff']['current_phase'] == ComplaintPhase.INTAKE.value
            assert result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    @pytest.mark.integration
    def test_mediator_scraper_history_helpers(self):
        """Test mediator proxies scraper run history helpers."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'

            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.evidence_state.get_scraper_runs = Mock(return_value=[{'id': 7}])
            mediator.evidence_state.get_scraper_run_details = Mock(return_value={'available': True, 'run': {'id': 7}})
            mediator.evidence_state.get_scraper_tactic_performance = Mock(return_value={'available': True, 'tactics': []})

            runs = mediator.get_scraper_runs(limit=5)
            detail = mediator.get_scraper_run_details(7)
            perf = mediator.get_scraper_tactic_performance(limit_runs=5)

            assert runs[0]['id'] == 7
            assert detail['run']['id'] == 7
            assert perf['available'] is True
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    @pytest.mark.integration
    def test_mediator_scraper_queue_helpers(self):
        """Test mediator proxies scraper queue helpers and runs claimed jobs."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'

            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.evidence_state.enqueue_scraper_job = Mock(return_value={'queued': True, 'job_id': 11})
            mediator.evidence_state.get_scraper_queue = Mock(return_value=[{'id': 11, 'status': 'queued'}])
            mediator.evidence_state.claim_next_scraper_job = Mock(return_value={
                'claimed': True,
                'job': {
                    'id': 11,
                    'user_id': 'testuser',
                    'keywords': ['employment discrimination'],
                    'domains': ['eeoc.gov'],
                    'iterations': 2,
                    'sleep_seconds': 0.0,
                    'quality_domain': 'caselaw',
                    'claim_type': 'employment discrimination',
                    'min_relevance': 0.6,
                    'store_results': True,
                },
            })
            mediator.evidence_state.complete_scraper_job = Mock(return_value={
                'updated': True,
                'job': {'id': 11, 'status': 'completed', 'run_id': 15, 'claim_type': 'employment discrimination'},
            })
            mediator.web_evidence_integration.run_agentic_scraper_cycle = Mock(return_value={
                'iterations': [{'iteration': 1, 'accepted_count': 2}],
                'final_results': [{'url': 'https://example.com/policy'}],
                'storage_summary': {'stored': 1},
                'scraper_run': {'persisted': True, 'run_id': 15},
            })

            queued = mediator.enqueue_agentic_scraper_job(
                keywords=['employment discrimination'],
                claim_type='employment discrimination',
            )
            jobs = mediator.get_scraper_queue(status='queued', limit=5)
            result = mediator.run_next_agentic_scraper_job(worker_id='worker-1', user_id='testuser')

            assert queued['queued'] is True
            assert jobs[0]['id'] == 11
            assert result['claimed'] is True
            assert result['ran'] is True
            assert result['job']['run_id'] == 15
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
