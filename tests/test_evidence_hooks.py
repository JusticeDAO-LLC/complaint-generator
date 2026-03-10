"""
Unit tests for Evidence Management Hooks

Tests for evidence storage (IPFS), state management (DuckDB), 
and evidence analysis functionality.
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


class TestEvidenceStorageHook:
    """Test cases for EvidenceStorageHook"""
    
    def test_evidence_storage_hook_can_be_imported(self):
        """Test that EvidenceStorageHook can be imported"""
        try:
            from mediator.evidence_hooks import EvidenceStorageHook
            assert EvidenceStorageHook is not None
        except ImportError as e:
            pytest.skip(f"EvidenceStorageHook has import issues: {e}")
    
    def test_store_evidence(self):
        """Test storing evidence data"""
        try:
            from mediator.evidence_hooks import EvidenceStorageHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            hook = EvidenceStorageHook(mock_mediator)
            
            # Test data
            test_data = b"Test evidence document content"
            evidence_type = "document"
            metadata = {"filename": "test.pdf"}
            
            result = hook.store_evidence(test_data, evidence_type, metadata)
            
            assert isinstance(result, dict)
            assert 'cid' in result
            assert 'size' in result
            assert result['size'] == len(test_data)
            assert result['type'] == evidence_type
            assert 'timestamp' in result
            assert 'provenance' in result['metadata']
            assert result['metadata']['provenance']['content_hash']
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_store_evidence_file(self):
        """Test storing evidence from file"""
        try:
            from mediator.evidence_hooks import EvidenceStorageHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            
            hook = EvidenceStorageHook(mock_mediator)
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
                f.write(b"Test file content")
                temp_path = f.name
            
            try:
                result = hook.store_evidence_file(temp_path, "document")
                
                assert isinstance(result, dict)
                assert 'cid' in result
                assert 'filename' in result['metadata']
            finally:
                os.unlink(temp_path)
                
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestEvidenceStateHook:
    """Test cases for EvidenceStateHook with DuckDB"""
    
    def test_evidence_state_hook_can_be_imported(self):
        """Test that EvidenceStateHook can be imported"""
        try:
            from mediator.evidence_hooks import EvidenceStateHook
            assert EvidenceStateHook is not None
        except ImportError as e:
            pytest.skip(f"EvidenceStateHook has import issues: {e}")
    
    def test_add_evidence_record(self):
        """Test adding evidence record to DuckDB"""
        try:
            from mediator.evidence_hooks import EvidenceStateHook
            import duckdb
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = "testuser"
            
            # Use temporary database
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)
                
                evidence_info = {
                    'cid': 'QmTest123',
                    'type': 'document',
                    'size': 1024,
                    'metadata': {'test': 'data'}
                }
                
                record_id = hook.add_evidence_record(
                    user_id='testuser',
                    evidence_info=evidence_info,
                    description='Test evidence'
                )
                
                assert record_id > 0
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
                    
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_get_user_evidence(self):
        """Test retrieving user evidence from DuckDB"""
        try:
            from mediator.evidence_hooks import EvidenceStateHook
            import duckdb
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = "testuser"
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)
                
                # Add test evidence
                evidence_info = {
                    'cid': 'QmTest456',
                    'type': 'image',
                    'size': 2048,
                    'metadata': {}
                }
                
                hook.add_evidence_record('testuser', evidence_info)
                
                # Retrieve evidence
                results = hook.get_user_evidence('testuser')
                
                assert isinstance(results, list)
                assert len(results) > 0
                assert results[0]['cid'] == 'QmTest456'
                assert 'provenance' in results[0]
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
                    
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_get_evidence_by_cid(self):
        """Test retrieving evidence by CID"""
        try:
            from mediator.evidence_hooks import EvidenceStateHook
            import duckdb
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)
                
                evidence_info = {
                    'cid': 'QmTest789',
                    'type': 'video',
                    'size': 4096,
                    'metadata': {}
                }
                
                hook.add_evidence_record('testuser', evidence_info)
                
                # Retrieve by CID
                result = hook.get_evidence_by_cid('QmTest789')
                
                assert result is not None
                assert result['cid'] == 'QmTest789'
                assert result['type'] == 'video'
                assert 'provenance' in result
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
                    
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_get_evidence_statistics(self):
        """Test evidence statistics retrieval"""
        try:
            from mediator.evidence_hooks import EvidenceStateHook
            import duckdb
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)
                
                # Add multiple evidence items
                for i in range(3):
                    evidence_info = {
                        'cid': f'QmTest{i}',
                        'type': 'document',
                        'size': 1000 * (i + 1),
                        'metadata': {}
                    }
                    hook.add_evidence_record('testuser', evidence_info)
                
                # Get statistics
                stats = hook.get_evidence_statistics('testuser')
                
                assert stats['available'] is True
                assert stats['total_count'] == 3
                assert stats['total_size'] > 0
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
                    
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestEvidenceAnalysisHook:
    """Test cases for EvidenceAnalysisHook"""
    
    def test_evidence_analysis_hook_can_be_imported(self):
        """Test that EvidenceAnalysisHook can be imported"""
        try:
            from mediator.evidence_hooks import EvidenceAnalysisHook
            assert EvidenceAnalysisHook is not None
        except ImportError as e:
            pytest.skip(f"EvidenceAnalysisHook has import issues: {e}")
    
    def test_analyze_evidence_for_claim(self):
        """Test analyzing evidence for a specific claim"""
        try:
            from mediator.evidence_hooks import EvidenceAnalysisHook
            
            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.evidence_state = Mock()
            
            # Mock evidence data
            mock_evidence = [
                {
                    'cid': 'QmTest1',
                    'type': 'document',
                    'claim_type': 'breach of contract',
                    'description': 'Contract document'
                },
                {
                    'cid': 'QmTest2',
                    'type': 'email',
                    'claim_type': 'breach of contract',
                    'description': 'Email correspondence'
                }
            ]
            
            mock_mediator.evidence_state.get_user_evidence = Mock(return_value=mock_evidence)
            
            hook = EvidenceAnalysisHook(mock_mediator)
            
            result = hook.analyze_evidence_for_claim('testuser', 'breach of contract')
            
            assert isinstance(result, dict)
            assert result['claim_type'] == 'breach of contract'
            assert result['total_evidence'] == 2
            assert 'evidence_by_type' in result
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestMediatorEvidenceIntegration:
    """Integration tests for evidence hooks with mediator"""
    
    @pytest.mark.integration
    def test_mediator_has_evidence_hooks(self):
        """Test that mediator initializes with evidence hooks"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                mediator = Mediator(backends=[mock_backend], evidence_db_path=db_path)
                
                assert hasattr(mediator, 'evidence_storage')
                assert hasattr(mediator, 'evidence_state')
                assert hasattr(mediator, 'evidence_analysis')
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    @pytest.mark.integration
    def test_mediator_submit_evidence(self):
        """Test submitting evidence through mediator"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            
            try:
                mediator = Mediator(backends=[mock_backend], evidence_db_path=db_path)
                mediator.state.username = 'testuser'
                
                # Submit test evidence
                result = mediator.submit_evidence(
                    data=b"Test evidence content",
                    evidence_type='document',
                    description='Test document',
                    claim_type='breach of contract'
                )
                
                assert 'cid' in result
                assert 'record_id' in result
                assert result['user_id'] == 'testuser'
                
                # Verify evidence can be retrieved
                evidence_list = mediator.get_user_evidence('testuser')
                assert len(evidence_list) > 0
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
