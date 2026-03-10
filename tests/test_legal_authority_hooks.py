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
                if results:
                    assert results[0]['source'] == 'us_code'
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
                assert 'provenance' in results[0]
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

                support_links = mediator.get_claim_support(claim_type='civil rights')
                assert len(support_links) > 0

                support_summary = mediator.summarize_claim_support(claim_type='civil rights')
                assert support_summary['claims']['civil rights']['support_by_kind']['authority'] > 0
                
                # Retrieve
                authorities = mediator.get_legal_authorities(claim_type='civil rights')
                assert len(authorities) > 0
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
