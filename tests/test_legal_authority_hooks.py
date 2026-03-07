"""
Unit tests for Legal Authority Hooks

Tests for legal authority search, storage, and analysis functionality.
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


class TestLegalAuthoritySearchHook:
    """Test cases for LegalAuthoritySearchHook"""
    
    def test_legal_authority_search_hook_can_be_imported(self):
        """Test that LegalAuthoritySearchHook can be imported"""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook
            assert LegalAuthoritySearchHook is not None
        except ImportError as e:
            pytest.skip(f"LegalAuthoritySearchHook has import issues: {e}")
    
    def test_search_us_code(self):
        """Test searching US Code"""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="employment discrimination\ncivil rights\nequal protection")
            
            hook = LegalAuthoritySearchHook(mock_mediator)
            
            # Mock search results
            with patch('mediator.legal_authority_hooks.search_us_code') as mock_search:
                mock_search.return_value = [
                    {
                        'citation': '42 U.S.C. § 1983',
                        'title': 'Civil Rights Act',
                        'content': 'Test content...'
                    }
                ]
                
                results = hook.search_us_code('employment discrimination', max_results=5)
                
                assert isinstance(results, list)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_search_all_sources(self):
        """Test searching all legal sources"""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")
            
            hook = LegalAuthoritySearchHook(mock_mediator)
            hook.search_us_code = Mock(return_value=[])
            hook.search_federal_register = Mock(return_value=[])
            hook.search_case_law = Mock(return_value=[])
            hook.search_web_archives = Mock(return_value=[])
            
            results = hook.search_all_sources('test query')
            
            assert isinstance(results, dict)
            assert 'statutes' in results
            assert 'regulations' in results
            assert 'case_law' in results
            assert 'web_archives' in results
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_get_capability_registry_returns_expected_shape(self):
        """Test capability registry shape for Phase 1 adapter integration."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            hook = LegalAuthoritySearchHook(mock_mediator)
            registry = hook.get_capability_registry()

            assert isinstance(registry, dict)
            assert 'legal_datasets' in registry
            assert 'search_tools' in registry
            assert 'graph_tools' in registry
            assert 'vector_tools' in registry
            assert 'optimizer_tools' in registry
            assert 'mcp_tools' in registry

            legal = registry['legal_datasets']
            assert 'available' in legal
            assert 'enabled' in legal
            assert 'active' in legal
            assert 'details' in legal
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_enhanced_adds_normalized_results(self):
        """Enhanced mode should expose normalized deduped records."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
            }, clear=False):
                hook = LegalAuthoritySearchHook(mock_mediator)
                hook.search_us_code = Mock(return_value=[
                    {'title': 'Title A', 'url': 'example-dot-com/a', 'score': 0.4},
                    {'title': 'Title A better', 'url': 'example-dot-com/a', 'score': 0.9},
                ])
                hook.search_federal_register = Mock(return_value=[])
                hook.search_case_law = Mock(return_value=[])
                hook.search_web_archives = Mock(return_value=[])

                results = hook.search_all_sources('test query')

                assert isinstance(results, dict)
                assert 'normalized' in results
                assert isinstance(results['normalized'], list)
                assert len(results['normalized']) == 1
                assert results['normalized'][0]['score'] == 0.9
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_enhanced_vector_marks_normalized_metadata(self):
        """Enhanced vector mode should annotate normalized records with vector metadata."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
                'IPFS_DATASETS_ENHANCED_VECTOR': '1',
            }, clear=False):
                hook = LegalAuthoritySearchHook(mock_mediator)
                hook.search_us_code = Mock(return_value=[
                    {'title': 'Employment discrimination law', 'url': 'example-dot-com/a', 'score': 0.4},
                ])
                hook.search_federal_register = Mock(return_value=[])
                hook.search_case_law = Mock(return_value=[])
                hook.search_web_archives = Mock(return_value=[])

                results = hook.search_all_sources('employment discrimination')

                assert 'normalized' in results
                assert len(results['normalized']) >= 1
                assert results['normalized'][0]['metadata'].get('vector_augmented') is True
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_vector_uses_state_context_to_boost_matching_authority(self):
        """Enhanced vector mode should use complaint context to prefer the matching authority."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")
            mock_mediator.state = Mock()
            mock_mediator.state.complaint_summary = 'Retaliation after reporting discrimination to HR'
            mock_mediator.state.original_complaint = 'Termination email supports the retaliation claim.'
            mock_mediator.state.complaint = None
            mock_mediator.state.last_message = 'Need authority tied to the termination email evidence.'
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
                hook = LegalAuthoritySearchHook(mock_mediator)
                hook.search_us_code = Mock(return_value=[
                    {
                        'title': 'Termination email retaliation authority',
                        'url': 'https://example.com/relevant-authority',
                        'score': 0.35,
                    },
                ])
                hook.search_federal_register = Mock(return_value=[])
                hook.search_case_law = Mock(return_value=[
                    {
                        'title': 'Generic workplace policy case',
                        'url': 'https://example.com/generic-authority',
                        'score': 0.45,
                    },
                ])
                hook.search_web_archives = Mock(return_value=[])

                results = hook.search_all_sources('employment retaliation')

                assert 'normalized' in results
                assert results['normalized'][0]['title'] == 'Termination email retaliation authority'
                assert results['normalized'][0]['metadata'].get('evidence_similarity_applied') is True
                assert results['normalized'][0]['metadata'].get('evidence_similarity_score', 0.0) > 0.0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_build_evidence_context_uses_structured_chat_message_text(self):
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook
            from mediator.state import State

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")
            mock_mediator.state = Mock()
            mock_mediator.state.complaint_summary = None
            mock_mediator.state.original_complaint = None
            mock_mediator.state.complaint = None
            mock_mediator.state.last_message = None
            mock_mediator.state.data = {
                'chat_history': {
                    '1': {
                        'sender': 'user-123',
                        'message': 'Termination email from HR references my complaint.',
                        'question': 'Do you have the termination email?',
                    }
                }
            }
            helper_state = State()
            helper_state.data = mock_mediator.state.data
            mock_mediator.state.extract_chat_history_context_strings = helper_state.extract_chat_history_context_strings

            hook = LegalAuthoritySearchHook(mock_mediator)
            context = hook._build_evidence_context('employment retaliation')

            assert 'Termination email from HR references my complaint.' in context
            assert not any('{\'sender\':' in item for item in context)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_build_evidence_context_uses_structured_chat_message_text_without_helper(self):
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")
            mock_mediator.state = Mock()
            mock_mediator.state.complaint_summary = None
            mock_mediator.state.original_complaint = None
            mock_mediator.state.complaint = None
            mock_mediator.state.last_message = None
            mock_mediator.state.data = {
                'chat_history': {
                    '1': {
                        'sender': 'user-123',
                        'message': 'Structured termination email detail.',
                        'question': 'Do you have the termination email?',
                    }
                }
            }

            hook = LegalAuthoritySearchHook(mock_mediator)
            context = hook._build_evidence_context('employment retaliation')

            assert 'Structured termination email detail.' in context
            assert 'Do you have the termination email?' in context
            assert not any('{\'sender\':' in item for item in context)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_enhanced_decomposes_query_into_multiple_searches(self):
        """Enhanced legal/search mode should expand a query into multiple source searches."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
            }, clear=False):
                hook = LegalAuthoritySearchHook(mock_mediator)
                hook.search_us_code = Mock(side_effect=lambda term, max_results=5: [
                    {'title': f'US Code {term}', 'url': f'https://example.com/{term.replace(" ", "-")}', 'score': 0.3}
                ])
                hook.search_federal_register = Mock(return_value=[])
                hook.search_case_law = Mock(return_value=[])
                hook.search_web_archives = Mock(return_value=[])

                results = hook.search_all_sources(
                    'employment discrimination retaliation',
                    claim_type='employment_discrimination',
                    jurisdiction='federal',
                )

                assert hook.search_us_code.call_count >= 2
                searched_queries = [call.args[0] for call in hook.search_us_code.call_args_list]
                assert 'employment discrimination retaliation' in searched_queries
                assert any('federal' in query or 'employment discrimination' in query for query in searched_queries)
                assert results['normalized'][0]['metadata'].get('query_decomposition_applied') is True
                assert results['normalized'][0]['metadata'].get('query_decomposition_count', 0) >= 2
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_enhanced_jurisdiction_weighting_prefers_matching_authority(self):
        """Enhanced ranking should prefer authorities whose jurisdiction matches the query context."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
            }, clear=False):
                hook = LegalAuthoritySearchHook(mock_mediator)
                hook.search_us_code = Mock(return_value=[
                    {
                        'title': 'Federal retaliation statute',
                        'url': 'https://example.com/federal-statute',
                        'score': 0.40,
                        'metadata': {'jurisdiction': 'federal'},
                    },
                ])
                hook.search_federal_register = Mock(return_value=[])
                hook.search_case_law = Mock(return_value=[
                    {
                        'title': 'California retaliation case',
                        'url': 'https://example.com/california-case',
                        'score': 0.49,
                        'metadata': {'jurisdiction': 'california'},
                    },
                ])
                hook.search_web_archives = Mock(return_value=[])

                results = hook.search_all_sources('retaliation claim', jurisdiction='federal')

                assert results['normalized'][0]['title'] == 'Federal retaliation statute'
                assert results['normalized'][0]['metadata'].get('orchestrator_jurisdiction_weight', 0.0) > 0.0
                california_record = next(item for item in results['normalized'] if item['title'] == 'California retaliation case')
                assert california_record['metadata'].get('orchestrator_jurisdiction_weight', 0.0) == 0.0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_graph_reranker_boosts_graph_aligned_record(self):
        """Enhanced graph mode should rerank using phase graph context terms."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

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
                                {'source_name': 'termination letter'},
                            ],
                        }
                    ]

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(
                side_effect=lambda _phase, key=None: _KG() if key == 'knowledge_graph' else (_DG() if key == 'dependency_graph' else None)
            )

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
                'IPFS_DATASETS_ENHANCED_GRAPH': '1',
                'RETRIEVAL_RERANKER_MODE': 'graph',
                'RETRIEVAL_MAX_LATENCY_MS': '100',
            }, clear=False):
                hook = LegalAuthoritySearchHook(mock_mediator)
                hook.search_us_code = Mock(return_value=[
                    {'title': 'Employment discrimination retaliation standards', 'url': 'example-dot-com/relevant', 'score': 0.40},
                    {'title': 'Generic procedural digest', 'url': 'example-dot-com/generic', 'score': 0.49},
                ])
                hook.search_federal_register = Mock(return_value=[])
                hook.search_case_law = Mock(return_value=[])
                hook.search_web_archives = Mock(return_value=[])

                results = hook.search_all_sources('workplace claim analysis')

                assert 'normalized' in results
                target = next(
                    item for item in results['normalized']
                    if item.get('title') == 'Employment discrimination retaliation standards'
                )
                assert target['metadata'].get('graph_reranked') is True
                assert target['metadata'].get('graph_readiness_gap', 0) > 0
                assert target['metadata'].get('graph_latency_budget_ms') == 100
                assert target['metadata'].get('graph_latency_guard_applied') is True
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_graph_reranker_canary_zero_skips_reranking(self):
        """Graph reranking should be skipped when canary percent is set to 0."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

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
                                {'source_name': 'termination letter'},
                            ],
                        }
                    ]

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")
            mock_mediator.phase_manager = Mock()
            mock_mediator.phase_manager.get_phase_data = Mock(
                side_effect=lambda _phase, key=None: _KG() if key == 'knowledge_graph' else (_DG() if key == 'dependency_graph' else None)
            )

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
                'IPFS_DATASETS_ENHANCED_GRAPH': '1',
                'RETRIEVAL_RERANKER_MODE': 'graph',
                'RETRIEVAL_RERANKER_CANARY_PERCENT': '0',
            }, clear=False):
                hook = LegalAuthoritySearchHook(mock_mediator)
                hook.search_us_code = Mock(return_value=[
                    {'title': 'Employment discrimination retaliation standards', 'url': 'example-dot-com/relevant', 'score': 0.40},
                ])
                hook.search_federal_register = Mock(return_value=[])
                hook.search_case_law = Mock(return_value=[])
                hook.search_web_archives = Mock(return_value=[])

                results = hook.search_all_sources('workplace claim analysis')

                assert 'normalized' in results
                assert results['normalized'][0]['metadata'].get('graph_reranked') is not True
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestLegalAuthorityStorageHook:
    """Test cases for LegalAuthorityStorageHook"""
    
    def test_legal_authority_storage_hook_can_be_imported(self):
        """Test that LegalAuthorityStorageHook can be imported"""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            assert LegalAuthorityStorageHook is not None
        except ImportError as e:
            pytest.skip(f"LegalAuthorityStorageHook has import issues: {e}")
    
    def test_add_authority(self):
        """Test adding a legal authority to DuckDB"""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)
                
                authority_data = {
                    'type': 'statute',
                    'source': 'us_code',
                    'citation': '42 U.S.C. § 1983',
                    'title': 'Civil Rights Act',
                    'content': 'Test statute content...',
                    'url': 'https://example.com/usc/42/1983',
                    'metadata': {'test': 'data'},
                    'relevance_score': 0.9
                }
                
                record_id = hook.add_authority(
                    authority_data,
                    user_id='testuser',
                    claim_type='civil rights violation'
                )
                
                assert record_id > 0
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_get_authorities_by_claim(self):
        """Test retrieving authorities by claim type"""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)
                
                # Add test authority
                authority_data = {
                    'type': 'statute',
                    'source': 'us_code',
                    'citation': '29 U.S.C. § 2601',
                    'title': 'Family and Medical Leave Act',
                    'content': 'Test content...'
                }
                
                hook.add_authority(authority_data, 'testuser', claim_type='employment')
                
                # Retrieve by claim
                results = hook.get_authorities_by_claim('testuser', 'employment')
                
                assert isinstance(results, list)
                assert len(results) > 0
                assert results[0]['citation'] == '29 U.S.C. § 2601'
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_get_statistics(self):
        """Test getting authority statistics"""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)
                
                # Add multiple authorities
                for i in range(3):
                    authority_data = {
                        'type': 'statute',
                        'source': 'us_code',
                        'citation': f'Test § {i}',
                        'title': f'Test Title {i}'
                    }
                    hook.add_authority(authority_data, 'testuser')
                
                stats = hook.get_statistics('testuser')
                
                assert stats['available'] is True
                assert stats['total_count'] == 3
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestLegalAuthorityAnalysisHook:
    """Test cases for LegalAuthorityAnalysisHook"""
    
    def test_legal_authority_analysis_hook_can_be_imported(self):
        """Test that LegalAuthorityAnalysisHook can be imported"""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityAnalysisHook
            assert LegalAuthorityAnalysisHook is not None
        except ImportError as e:
            pytest.skip(f"LegalAuthorityAnalysisHook has import issues: {e}")
    
    def test_analyze_authorities_for_claim(self):
        """Test analyzing authorities for a claim"""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityAnalysisHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.legal_authority_storage = Mock()
            mock_mediator.query_backend = Mock(return_value="Analysis: Strong legal foundation")
            
            # Mock authorities
            mock_authorities = [
                {
                    'type': 'statute',
                    'citation': '42 U.S.C. § 1983',
                    'title': 'Civil Rights Act'
                },
                {
                    'type': 'case_law',
                    'citation': 'Smith v. Jones',
                    'title': 'Test Case'
                }
            ]
            
            mock_mediator.legal_authority_storage.get_authorities_by_claim = Mock(
                return_value=mock_authorities
            )
            
            hook = LegalAuthorityAnalysisHook(mock_mediator)
            
            result = hook.analyze_authorities_for_claim('testuser', 'civil rights')
            
            assert isinstance(result, dict)
            assert result['claim_type'] == 'civil rights'
            assert result['total_authorities'] == 2
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestMediatorLegalAuthorityIntegration:
    """Integration tests for legal authority hooks with mediator"""
    
    @pytest.mark.integration
    def test_mediator_has_legal_authority_hooks(self):
        """Test that mediator initializes with legal authority hooks"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                mediator = Mediator(
                    backends=[mock_backend],
                    legal_authority_db_path=db_path
                )
                
                assert hasattr(mediator, 'legal_authority_search')
                assert hasattr(mediator, 'legal_authority_storage')
                assert hasattr(mediator, 'legal_authority_analysis')
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    @pytest.mark.integration
    def test_mediator_search_and_store_authorities(self):
        """Test searching and storing legal authorities through mediator"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                mediator = Mediator(
                    backends=[mock_backend],
                    legal_authority_db_path=db_path
                )
                mediator.state.username = 'testuser'
                
                # Mock search results
                mediator.legal_authority_search.search_all_sources = Mock(return_value={
                    'statutes': [
                        {
                            'citation': '42 U.S.C. § 1983',
                            'title': 'Civil Rights Act',
                            'content': 'Test content'
                        }
                    ],
                    'regulations': [],
                    'case_law': [],
                    'web_archives': []
                })
                
                # Search
                results = mediator.search_legal_authorities('civil rights', search_all=True)
                assert 'statutes' in results
                
                # Store
                stored = mediator.store_legal_authorities(results, claim_type='civil rights')
                assert 'statutes' in stored
                
                # Retrieve
                authorities = mediator.get_legal_authorities(claim_type='civil rights')
                assert len(authorities) > 0
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    @pytest.mark.integration
    def test_store_legal_authorities_ignores_normalized_bucket_for_storage(self):
        """Enhanced normalized artifacts should be cached but not inserted as authority rows."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                mediator = Mediator(
                    backends=[mock_backend],
                    legal_authority_db_path=db_path
                )
                mediator.state.username = 'testuser'

                authorities = {
                    'statutes': [
                        {
                            'citation': '42 U.S.C. § 1983',
                            'title': 'Civil Rights Act',
                            'content': 'Test content'
                        }
                    ],
                    'normalized': [
                        {
                            'citation': '42 U.S.C. § 1983',
                            'score': 0.95,
                            'source_name': 'us_code'
                        }
                    ],
                    'support_bundle': {
                        'top_mixed': [
                            {
                                'citation': '42 U.S.C. § 1983',
                                'title': 'Civil Rights Act',
                                'snippet': 'Strong match',
                            }
                        ],
                        'top_authorities': [
                            {
                                'citation': '42 U.S.C. § 1983',
                                'title': 'Civil Rights Act',
                            }
                        ],
                        'top_evidence': [],
                        'cross_supported': [],
                        'hybrid_cross_supported': [],
                        'summary': {
                            'total_records': 1,
                            'authority_count': 1,
                            'evidence_count': 0,
                            'cross_supported_count': 0,
                            'hybrid_cross_supported_count': 0,
                        },
                    }
                }

                stored = mediator.store_legal_authorities(
                    authorities,
                    claim_type='civil rights',
                    search_query='civil rights violation'
                )

                assert stored.get('statutes', 0) == 1
                assert 'normalized' not in stored
                assert hasattr(mediator.state, 'last_legal_authorities_normalized')
                assert len(mediator.state.last_legal_authorities_normalized) == 1
                assert hasattr(mediator.state, 'last_legal_authorities_support_bundle')
                assert mediator.state.last_legal_authorities_support_bundle['summary']['total_records'] == 1

                all_rows = mediator.get_legal_authorities(claim_type='civil rights')
                assert len(all_rows) == 1
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
