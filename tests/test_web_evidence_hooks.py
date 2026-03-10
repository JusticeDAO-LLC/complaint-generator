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
                    'entity_count': 3,
                    'relationship_count': 2,
                    'claim_links': 1,
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
                    }
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
            assert 'support_links_added' in result
            assert 'support_links_reused' in result
            assert result['discovered'] == 2
            assert result['stored_new'] == 2
            assert result['reused'] == 0
            assert result['support_links_added'] == 2
            store_kwargs = mock_mediator.evidence_storage.store_evidence.call_args.kwargs
            assert store_kwargs['evidence_type'] == 'web_document'
            assert store_kwargs['metadata']['parse_document'] is True
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

    def test_discover_and_store_evidence_reports_reuse_counts(self):
        """Test reused evidence rows and support links are surfaced in results."""
        try:
            from mediator.web_evidence_hooks import WebEvidenceIntegrationHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
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
            assert result['support_links_added'] == 0
            assert len(result['graph_projection']) == 2
            assert result['graph_projection'][0]['claim_links'] == 1
            assert mock_mediator.add_evidence_to_graphs.call_count == 2
            assert result['support_links_reused'] == 1
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
            
            hook = WebEvidenceIntegrationHook(mock_mediator)
            
            keywords = hook._generate_search_keywords('employment discrimination')
            
            assert isinstance(keywords, list)
            assert len(keywords) > 0
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
            mock_mediator.get_claim_follow_up_plan = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'task_count': 2,
                        'tasks': [
                            {
                                'claim_element': 'Protected activity',
                                'status': 'partially_supported',
                                'missing_support_kinds': ['authority'],
                            },
                            {
                                'claim_element': 'Adverse action',
                                'status': 'missing',
                                'missing_support_kinds': ['evidence', 'authority'],
                            },
                        ],
                    }
                }
            })

            hook = WebEvidenceIntegrationHook(mock_mediator)
            hook._generate_search_keywords = Mock(return_value=['employment discrimination'])
            hook.discover_and_store_evidence = Mock(return_value={
                'discovered': 3,
                'stored': 2,
                'support_links_added': 2,
            })

            result = hook.discover_evidence_for_case(user_id='testuser')

            assert result['support_summary']['employment discrimination']['total_links'] == 2
            assert result['claim_overview']['employment discrimination']['missing_count'] == 1
            assert result['follow_up_plan']['employment discrimination']['task_count'] == 2
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
            mock_mediator.summarize_claim_support = Mock(return_value={'claims': {}})
            mock_mediator.get_claim_overview = Mock(return_value={'claims': {}})
            mock_mediator.get_claim_follow_up_plan = Mock(return_value={'claims': {}})
            mock_mediator.execute_claim_follow_up_plan = Mock(return_value={
                'claims': {
                    'employment discrimination': {
                        'task_count': 1,
                        'tasks': [
                            {'claim_element': 'Adverse action'}
                        ],
                    }
                }
            })

            hook = WebEvidenceIntegrationHook(mock_mediator)
            hook._generate_search_keywords = Mock(return_value=['employment discrimination'])
            hook.discover_and_store_evidence = Mock(return_value={
                'discovered': 1,
                'stored': 1,
                'support_links_added': 1,
            })

            result = hook.discover_evidence_for_case(user_id='testuser', execute_follow_up=True)

            assert result['follow_up_execution']['employment discrimination']['task_count'] == 1
            mock_mediator.execute_claim_follow_up_plan.assert_called_once()
            assert mock_mediator.execute_claim_follow_up_plan.call_args.kwargs['support_kind'] == 'evidence'
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
                'total_found': 0
            })
            
            result = mediator.search_web_for_evidence(
                keywords=['test', 'query']
            )
            
            assert isinstance(result, dict)
            assert 'total_found' in result
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
