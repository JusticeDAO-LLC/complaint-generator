"""
Unit tests for Evidence Management Hooks

Tests for evidence storage (IPFS), state management (DuckDB), 
and evidence analysis functionality.
"""
import json
import pytest
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


pytestmark = pytest.mark.no_auto_network


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
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for evidence storage payload persistence',
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
            assert result['metadata']['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for evidence storage payload persistence',
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
            assert result['metadata']['provenance']['metadata']['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for evidence storage payload persistence',
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
            assert result['provenance']['metadata']['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T21:00:00+00:00',
                    'confirmation_note': 'ready for evidence storage payload persistence',
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
            assert result['document_parse']['status'] in {'fallback', 'available-fallback', 'empty'}
            assert result['metadata']['document_parse_summary']['chunk_count'] >= 1
            assert result['metadata']['document_parse_summary']['parser_version']
            assert result['metadata']['document_parse_summary']['input_format'] == 'pdf'
            assert result['metadata']['document_parse_summary']['paragraph_count'] >= 1
            assert result['document_parse']['summary']['chunk_count'] == result['metadata']['document_parse_summary']['chunk_count']
            assert result['document_parse']['metadata']['transform_lineage']['source'] == 'bytes'
            assert result['metadata']['document_parse_contract']['source'] == 'bytes'
            assert result['metadata']['document_parse_contract']['lineage']['source'] == 'bytes'
            assert result['document_graph']['status'] in {'unavailable', 'available-fallback'}
            assert result['metadata']['document_graph_summary']['entity_count'] >= 1
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_store_evidence_parses_email_mime_via_adapter(self):
        try:
            from mediator.evidence_hooks import EvidenceStorageHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            hook = EvidenceStorageHook(mock_mediator)

            payload = (
                b"Subject: Escalation\n"
                b"From: worker@example.com\n\n"
                b"I reported harassment to HR yesterday."
            )
            result = hook.store_evidence(
                payload,
                "attachment",
                {"filename": "escalation.eml", "mime_type": "message/rfc822"},
            )

            assert result['metadata']['document_parse_summary']['input_format'] == 'email'
            assert 'Subject: Escalation' in result['document_parse']['text']
            assert 'I reported harassment to HR yesterday.' in result['document_parse']['text']
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
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
                f.write(b"Test file content")
                temp_path = f.name
            
            try:
                result = hook.store_evidence_file(temp_path, "document")
                
                assert isinstance(result, dict)
                assert 'cid' in result
                assert 'filename' in result['metadata']
                assert result['metadata']['mime_type'] == 'text/plain'
                assert result['metadata']['document_parse_summary']['input_format'] == 'text'
                assert result['document_parse']['metadata']['transform_lineage']['source'] == 'file'
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
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T17:00:00+00:00',
                    'confirmation_note': 'ready for evidence record persistence',
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
                    claim_element_id='contract:1',
                    claim_element='Valid contract',
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
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T17:00:00+00:00',
                    'confirmation_note': 'ready for evidence record persistence',
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

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)

                evidence_info = {
                    'cid': 'QmTest456',
                    'type': 'image',
                    'size': 2048,
                    'metadata': {'test': 'data'},
                }

                hook.add_evidence_record(
                    'testuser',
                    evidence_info,
                    claim_element_id='employment:1',
                    claim_element='Protected activity',
                )

                results = hook.get_user_evidence('testuser')

                assert isinstance(results, list)
                assert len(results) > 0
                assert results[0]['cid'] == 'QmTest456'
                assert 'provenance' in results[0]
                assert results[0]['claim_element_id'] == 'employment:1'
                assert results[0]['claim_element'] == 'Protected activity'
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

    def test_add_evidence_record_deduplicates_same_claim_scope(self):
        """Test duplicate evidence in the same claim scope reuses the existing record."""
        try:
            from mediator.evidence_hooks import EvidenceStateHook
            import duckdb

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = "testuser"
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T17:00:00+00:00',
                    'confirmation_note': 'ready for evidence record persistence',
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

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)

                evidence_info = {
                    'cid': 'QmDuplicateEvidence',
                    'type': 'document',
                    'size': 2048,
                    'metadata': {
                        'provenance': {
                            'content_hash': 'hash-123',
                            'source_url': 'https://example.com/evidence/1',
                            'acquisition_method': 'web_discovery',
                        }
                    },
                }

                first_id = hook.add_evidence_record(
                    user_id='testuser',
                    evidence_info=evidence_info,
                    complaint_id='complaint-1',
                    claim_type='breach of contract',
                    claim_element_id='breach_of_contract:1',
                    claim_element='Valid contract',
                )
                second_id = hook.add_evidence_record(
                    user_id='testuser',
                    evidence_info=evidence_info,
                    complaint_id='complaint-1',
                    claim_type='breach of contract',
                    claim_element_id='breach_of_contract:1',
                    claim_element='Valid contract',
                )

                results = hook.get_user_evidence('testuser')

                assert first_id > 0
                assert second_id == first_id
                assert len(results) == 1
                assert results[0]['cid'] == 'QmDuplicateEvidence'
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
                assert stats['total_facts'] >= 0
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
                    
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_persists_document_parse_summary_and_chunks(self):
        """Test parsed document data is summarized on evidence rows and chunk rows are stored."""
        try:
            from mediator.evidence_hooks import EvidenceStateHook
            import duckdb

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = "testuser"
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T17:00:00+00:00',
                    'confirmation_note': 'ready for evidence record persistence',
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

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)

                evidence_info = {
                    'cid': 'QmParsed123',
                    'type': 'document',
                    'size': 64,
                    'metadata': {
                        'provenance': {'content_hash': 'hash123'},
                        'document_parse_summary': {
                            'status': 'fallback',
                            'chunk_count': 2,
                            'text_length': 24,
                            'parser_version': 'documents-adapter:1',
                            'input_format': 'text',
                            'paragraph_count': 1,
                        },
                    },
                    'document_parse': {
                        'status': 'fallback',
                        'text': 'alpha beta gamma delta',
                        'summary': {
                            'status': 'fallback',
                            'chunk_count': 2,
                            'text_length': 22,
                            'parser_version': 'documents-adapter:1',
                            'input_format': 'text',
                            'paragraph_count': 1,
                        },
                        'chunks': [
                            {'chunk_id': 'chunk-0', 'index': 0, 'start': 0, 'end': 11, 'text': 'alpha beta '},
                            {'chunk_id': 'chunk-1', 'index': 1, 'start': 11, 'end': 22, 'text': 'gamma delta'},
                        ],
                        'metadata': {
                            'filename': 'evidence.txt',
                            'transform_lineage': {
                                'source': 'bytes',
                                'parser_version': 'documents-adapter:1',
                                'input_format': 'text',
                            },
                        },
                    },
                }

                record_id = hook.add_evidence_record('testuser', evidence_info)
                record = hook.get_evidence_by_cid('QmParsed123')
                chunks = hook.get_evidence_chunks(record_id)
                graph = hook.get_evidence_graph(record_id)
                facts = hook.get_evidence_facts(record_id)

                assert record_id > 0
                assert record['parse_status'] == 'fallback'
                assert record['chunk_count'] == 2
                assert record['fact_count'] >= 1
                assert record['parsed_text_preview'].startswith('alpha beta')
                assert record['parse_metadata']['filename'] == 'evidence.txt'
                assert record['parse_metadata']['parser_version'] == 'documents-adapter:1'
                assert record['parse_metadata']['transform_lineage']['source'] == 'bytes'
                assert record['parse_metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T17:00:00+00:00',
                        'confirmation_note': 'ready for evidence record persistence',
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
                assert record['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T17:00:00+00:00',
                        'confirmation_note': 'ready for evidence record persistence',
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
                assert record['provenance']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T17:00:00+00:00',
                        'confirmation_note': 'ready for evidence record persistence',
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
                assert record['graph_metadata']['graph_snapshot']['created'] is True
                assert record['graph_metadata']['graph_snapshot']['reused'] is False
                assert record['graph_metadata']['graph_snapshot']['metadata']['record_scope'] == 'evidence'
                assert record['graph_metadata']['graph_snapshot']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T17:00:00+00:00',
                        'confirmation_note': 'ready for evidence record persistence',
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
                assert record['graph_entity_count'] >= 1
                assert record['graph_relationship_count'] >= 1
                assert len(chunks) == 2
                assert chunks[0]['chunk_id'] == 'chunk-0'
                assert chunks[0]['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T17:00:00+00:00',
                        'confirmation_note': 'ready for evidence record persistence',
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
                assert len(facts) >= 1
                assert facts[0]['fact_id'].startswith('fact:')
                assert facts[0]['source_artifact_id']
                assert facts[0]['source_family'] == 'evidence'
                assert facts[0]['source_record_id'] == record_id
                assert facts[0]['source_ref'] == facts[0]['source_artifact_id']
                assert facts[0]['record_scope'] == 'evidence'
                assert facts[0]['parse_source'] == 'bytes'
                assert facts[0]['input_format'] == 'text'
                assert facts[0]['metadata']['parse_lineage']['source'] == 'bytes'
                assert facts[0]['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T17:00:00+00:00',
                        'confirmation_note': 'ready for evidence record persistence',
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
                assert facts[0]['provenance']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T17:00:00+00:00',
                        'confirmation_note': 'ready for evidence record persistence',
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
                assert any(
                    entity['attributes'].get('intake_summary_handoff') == {
                        'current_phase': 'intake',
                        'ready_to_advance': True,
                        'complainant_summary_confirmation': {
                            'status': 'confirmed',
                            'confirmed': True,
                            'confirmed_at': '2026-03-17T17:00:00+00:00',
                            'confirmation_note': 'ready for evidence record persistence',
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
                    for entity in graph['entities']
                )
                assert all(
                    rel['attributes'].get('intake_summary_handoff') == {
                        'current_phase': 'intake',
                        'ready_to_advance': True,
                        'complainant_summary_confirmation': {
                            'status': 'confirmed',
                            'confirmed': True,
                            'confirmed_at': '2026-03-17T17:00:00+00:00',
                            'confirmation_note': 'ready for evidence record persistence',
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
                    for rel in graph['relationships']
                )
                assert any(entity['type'] == 'fact' for entity in graph['entities'])
                assert any(rel['relation_type'] == 'has_fact' for rel in graph['relationships'])
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)

        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_scraper_queue_claim_and_complete_job(self):
        """Test scraper jobs can be queued, claimed, and completed from DuckDB state."""
        try:
            from mediator.evidence_hooks import EvidenceStateHook
            import duckdb

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = "testuser"
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T15:00:00+00:00',
                    'confirmation_note': 'ready for scraper queue',
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

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)

                queued = hook.enqueue_scraper_job(
                    user_id='testuser',
                    keywords=['employment discrimination'],
                    domains=['eeoc.gov'],
                    claim_type='employment discrimination',
                    iterations=2,
                    priority=10,
                )
                queue_rows = hook.get_scraper_queue(user_id='testuser', status='queued', limit=5)
                claimed = hook.claim_next_scraper_job(worker_id='worker-1', user_id='testuser')
                completed = hook.complete_scraper_job(
                    queued['job_id'],
                    run_id=21,
                    metadata={'storage_summary': {'stored': 1}},
                )
                detail = hook.get_scraper_queue_job(queued['job_id'])

                assert queued['queued'] is True
                assert queue_rows[0]['id'] == queued['job_id']
                assert queue_rows[0]['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T15:00:00+00:00',
                        'confirmation_note': 'ready for scraper queue',
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
                assert claimed['claimed'] is True
                assert claimed['job']['status'] == 'running'
                assert completed['updated'] is True
                assert completed['job']['status'] == 'completed'
                assert completed['job']['run_id'] == 21
                assert detail['available'] is True
                assert detail['job']['metadata']['storage_summary']['stored'] == 1
                assert detail['job']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T15:00:00+00:00',
                        'confirmation_note': 'ready for scraper queue',
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
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)

        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_persist_scraper_run_stamps_confirmed_intake_handoff_metadata(self):
        """Persisted scraper runs should carry confirmed intake handoff provenance in run metadata."""
        try:
            from mediator.evidence_hooks import EvidenceStateHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.username = 'testuser'
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T16:00:00+00:00',
                    'confirmation_note': 'ready for scraper run persistence',
                    'confirmation_source': 'dashboard',
                    'summary_snapshot_index': 0,
                    'current_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 2,
                    },
                    'confirmed_summary_snapshot': {
                        'candidate_claim_count': 1,
                        'canonical_fact_count': 1,
                        'proof_lead_count': 2,
                    },
                },
            })

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = EvidenceStateHook(mock_mediator, db_path=db_path)
                persisted = hook.persist_scraper_run(
                    user_id='testuser',
                    keywords=['employment discrimination'],
                    domains=['example.com'],
                    claim_type='employment discrimination',
                    stored_summary={'stored': 1, 'total_new': 1, 'total_reused': 0},
                    run_result={
                        'iterations': [
                            {
                                'iteration': 1,
                                'discovered_count': 2,
                                'accepted_count': 1,
                                'scraped_count': 1,
                                'coverage': {'example.com': 1},
                                'quality': {'score': 0.8},
                                'critique': {},
                                'tactics': [
                                    {
                                        'name': 'multi_engine_search',
                                        'mode': 'search',
                                        'query': 'employment discrimination example.com policy',
                                        'weight': 1.0,
                                        'discovered_count': 2,
                                        'scraped_count': 1,
                                        'accepted_count': 1,
                                        'novelty_count': 1,
                                        'quality_score': 0.8,
                                        'quality': {'score': 0.8},
                                    }
                                ],
                            }
                        ],
                        'final_results': [{'url': 'https://example.com/policy'}],
                        'coverage_ledger': {
                            'https://example.com/policy': {
                                'domain': 'example.com',
                                'source_type': 'web',
                                'last_seen_iteration': 1,
                            }
                        },
                        'tactic_history': {'multi_engine_search': [80.0]},
                        'final_quality': {'data_quality_score': 80.0},
                    },
                )
                detail = hook.get_scraper_run_details(persisted['run_id'])

                assert persisted['persisted'] is True
                assert detail['available'] is True
                assert detail['run']['metadata']['tactic_history'] == {'multi_engine_search': [80.0]}
                assert detail['run']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T16:00:00+00:00',
                        'confirmation_note': 'ready for scraper run persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                    },
                }
                assert detail['iterations'][0]['coverage']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T16:00:00+00:00',
                        'confirmation_note': 'ready for scraper run persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                    },
                }
                assert detail['iterations'][0]['quality']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T16:00:00+00:00',
                        'confirmation_note': 'ready for scraper run persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                    },
                }
                assert detail['iterations'][0]['critique']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T16:00:00+00:00',
                        'confirmation_note': 'ready for scraper run persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                    },
                }
                assert detail['coverage'][0]['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T16:00:00+00:00',
                        'confirmation_note': 'ready for scraper run persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                    },
                }
                assert detail['iterations'][0]['tactics'][0]['quality']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T16:00:00+00:00',
                        'confirmation_note': 'ready for scraper run persistence',
                        'confirmation_source': 'dashboard',
                        'summary_snapshot_index': 0,
                        'current_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                        'confirmed_summary_snapshot': {
                            'candidate_claim_count': 1,
                            'canonical_fact_count': 1,
                            'proof_lead_count': 2,
                        },
                    },
                }
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
            from complaint_phases import ComplaintPhase
            from complaint_phases.knowledge_graph import Entity, KnowledgeGraph
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                claim_support_db_path = f.name
            
            try:
                mediator = Mediator(
                    backends=[mock_backend],
                    evidence_db_path=db_path,
                    claim_support_db_path=claim_support_db_path,
                )
                mediator.state.username = 'testuser'
                mediator.get_three_phase_status = Mock(return_value={
                    'current_phase': 'intake',
                    'intake_readiness': {
                        'ready_to_advance': True,
                    },
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T13:00:00+00:00',
                        'confirmation_note': 'ready for graph persistence',
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
                kg = KnowledgeGraph()
                kg.add_entity(Entity(
                    id='claim-1',
                    type='claim',
                    name='Breach of Contract Claim',
                    attributes={'claim_type': 'breach of contract'},
                    confidence=0.9,
                    source='complaint',
                ))
                mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
                mediator.claim_support.register_claim_requirements(
                    'testuser',
                    {'breach of contract': ['Valid contract', 'Breach']},
                )
                
                # Submit test evidence
                result = mediator.submit_evidence(
                    data=b"Test evidence content",
                    evidence_type='document',
                    description='Valid contract test document',
                    claim_type='breach of contract'
                )
                
                assert 'cid' in result
                assert 'record_id' in result
                assert result['user_id'] == 'testuser'
                assert result['claim_element_id'] == 'breach_of_contract:1'
                assert result['document_parse']['status'] in {'fallback', 'available-fallback', 'empty'}
                assert result['metadata']['document_parse_summary']['chunk_count'] >= 1
                assert result['metadata']['document_parse_summary']['parser_version']
                assert result['metadata']['document_parse_summary']['input_format'] == 'text'
                assert result['document_graph']['status'] in {'unavailable', 'available-fallback'}
                assert result['metadata']['document_graph_summary']['entity_count'] >= 1
                assert result['graph_projection']['claim_links'] >= 1
                assert result['graph_projection']['graph_changed'] is True
                assert result['graph_projection']['graph_snapshot']['created'] is True
                assert result['graph_projection']['graph_snapshot']['reused'] is False
                assert result['graph_projection']['graph_snapshot']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T13:00:00+00:00',
                        'confirmation_note': 'ready for graph persistence',
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
                assert result['graph_projection']['artifact_entity_added'] is True
                assert result['graph_projection']['artifact_entity_already_present'] is False
                assert result['graph_projection']['storage_record_created'] is True
                assert result['graph_projection']['storage_record_reused'] is False
                assert result['record_created'] is True
                assert result['record_reused'] is False
                assert result['support_link_created'] is True
                assert result['support_link_reused'] is False
                
                # Verify evidence can be retrieved
                evidence_list = mediator.get_user_evidence('testuser')
                assert len(evidence_list) > 0
                assert evidence_list[0]['claim_element'] == 'Valid contract'
                assert evidence_list[0]['chunk_count'] >= 1
                assert evidence_list[0]['fact_count'] >= 1
                assert evidence_list[0]['graph_entity_count'] >= 1

                graph = mediator.get_evidence_graph(result['record_id'])
                facts = mediator.get_evidence_facts(result['record_id'])
                assert any(entity['type'] == 'claim_element' for entity in graph['entities'])
                assert any(rel['relation_type'] == 'supports' for rel in graph['relationships'])
                assert len(facts) >= 1
                assert facts[0]['fact_id'].startswith('fact:')

                projected_kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
                assert result['artifact_id'] in projected_kg.entities
                assert any(rel.relation_type == 'supported_by' for rel in projected_kg.relationships.values())

                duplicate_result = mediator.submit_evidence(
                    data=b"Test evidence content",
                    evidence_type='document',
                    description='Valid contract test document',
                    claim_type='breach of contract'
                )
                assert duplicate_result['record_id'] == result['record_id']
                assert duplicate_result['record_created'] is False
                assert duplicate_result['record_reused'] is True
                assert duplicate_result['support_link_created'] is False
                assert duplicate_result['support_link_reused'] is True
                assert duplicate_result['graph_projection']['graph_changed'] is False
                assert duplicate_result['graph_projection']['graph_snapshot']['created'] is False
                assert duplicate_result['graph_projection']['graph_snapshot']['reused'] is True
                assert duplicate_result['graph_projection']['artifact_entity_added'] is False
                assert duplicate_result['graph_projection']['artifact_entity_already_present'] is True
                assert duplicate_result['graph_projection']['storage_record_created'] is False
                assert duplicate_result['graph_projection']['storage_record_reused'] is True

                element_view = mediator.get_claim_element_view(
                    claim_type='breach of contract',
                    claim_element='Valid contract',
                    user_id='testuser',
                )
                assert element_view['is_covered'] is True
                assert element_view['total_evidence'] == 1
                assert element_view['claim_element_id'] == 'breach_of_contract:1'
                assert element_view['support_summary']['fact_count'] >= 1
                assert element_view['support_summary']['links'][0]['fact_count'] >= 1
                assert len(element_view['support_summary']['links'][0]['facts']) >= 1
                assert element_view['gap_summary']['status'] == 'partially_supported'
                assert element_view['gap_summary']['missing_support_kinds'] == ['authority']
                assert element_view['gap_summary']['graph_trace_summary']['traced_link_count'] >= 1
                assert element_view['gap_summary']['graph_support']['summary']['total_fact_count'] >= 1
                assert len(element_view['gap_summary']['graph_support']['results']) >= 1
                assert element_view['graph_support']['summary']['total_fact_count'] >= 1
                assert len(element_view['graph_support']['results']) >= 1
                assert element_view['gap_summary']['graph_support']['results'][0]['source_family'] == 'evidence'
                assert element_view['gap_summary']['graph_support']['results'][0]['source_record_id'] == result['record_id']
                assert element_view['gap_summary']['graph_support']['results'][0]['support_ref'] == result['cid']
                assert element_view['gap_summary']['graph_support']['results'][0]['record_scope'] == 'evidence'
                assert element_view['contradiction_candidates'] == []
                assert element_view['total_facts'] >= 1
                assert len(element_view['support_facts']) >= 1
                assert element_view['support_facts'][0]['claim_type'] == 'breach of contract'
                assert element_view['support_facts'][0]['support_kind'] == 'evidence'
                assert len(element_view['support_packets']) >= 1
                assert element_view['support_packets'][0]['source_family'] == 'evidence'
                assert element_view['support_packets'][0]['source_record_id'] == result['record_id']
                assert element_view['support_packets'][0]['source_ref']
                assert element_view['support_packets'][0]['record_scope'] == 'evidence'

                graph_support = mediator.query_claim_graph_support(
                    claim_type='breach of contract',
                    claim_element='Valid contract',
                    user_id='testuser',
                )
                assert graph_support['claim_element_id'] == 'breach_of_contract:1'
                assert graph_support['summary']['total_fact_count'] >= 1
                assert graph_support['summary']['support_by_kind']['evidence'] >= 1
                assert len(graph_support['results']) >= 1
                assert graph_support['results'][0]['support_kind'] == 'evidence'
                assert graph_support['results'][0]['source_family'] == 'evidence'
                assert graph_support['results'][0]['source_record_id'] == result['record_id']
                assert graph_support['results'][0]['support_ref'] == result['cid']
                assert graph_support['results'][0]['source_ref']
                assert graph_support['results'][0]['record_scope'] == 'evidence'

                overview = mediator.get_claim_overview(
                    claim_type='breach of contract',
                    user_id='testuser',
                )
                assert overview['claims']['breach of contract']['partially_supported_count'] == 1
                assert overview['claims']['breach of contract']['missing_count'] == 1

                mediator.discover_web_evidence = Mock(return_value={
                    'discovered': 2,
                    'stored': 1,
                    'stored_new': 0,
                    'reused': 1,
                    'support_links_added': 1,
                    'support_links_reused': 0,
                    'total_records': 1,
                    'total_new': 0,
                    'total_reused': 1,
                    'total_support_links_added': 1,
                    'total_support_links_reused': 0,
                })
                follow_up_execution = mediator.execute_claim_follow_up_plan(
                    claim_type='breach of contract',
                    user_id='testuser',
                    support_kind='evidence',
                    max_tasks_per_claim=2,
                )
                assert follow_up_execution['claims']['breach of contract']['task_count'] == 1
                assert follow_up_execution['claims']['breach of contract']['skipped_task_count'] == 0
                assert any(
                    'summary' in task['graph_support']
                    for task in follow_up_execution['claims']['breach of contract']['tasks']
                )
                assert any(
                    task['recommended_action'] in {'retrieve_more_support', 'target_missing_support_kind', 'review_existing_support'}
                    for task in follow_up_execution['claims']['breach of contract']['tasks']
                )
                evidence_results = [
                    task['executed']['evidence']['result']
                    for task in follow_up_execution['claims']['breach of contract']['tasks']
                    if 'evidence' in task.get('executed', {})
                ]
                assert len(evidence_results) == 1
                assert all(result['total_records'] == 1 for result in evidence_results)
                assert all(result['total_new'] == 0 for result in evidence_results)
                assert all(result['total_reused'] == 1 for result in evidence_results)
                assert all(result['total_support_links_added'] == 1 for result in evidence_results)
                assert all(result['total_support_links_reused'] == 0 for result in evidence_results)

                follow_up_plan_after_execution = mediator.get_claim_follow_up_plan(
                    claim_type='breach of contract',
                    user_id='testuser',
                )
                assert follow_up_plan_after_execution['claims']['breach of contract']['blocked_task_count'] == 1
                assert any(
                    task['has_graph_support'] is True
                    for task in follow_up_plan_after_execution['claims']['breach of contract']['tasks']
                )
                assert any(
                    task['graph_support_strength'] in {'moderate', 'strong'}
                    for task in follow_up_plan_after_execution['claims']['breach of contract']['tasks']
                )
                assert all(
                    task['priority'] in {'high', 'medium', 'low'}
                    for task in follow_up_plan_after_execution['claims']['breach of contract']['tasks']
                )
                assert any(
                    task.get('execution_status', {}).get('evidence', {}).get('in_cooldown') is True
                    for task in follow_up_plan_after_execution['claims']['breach of contract']['tasks']
                )

                second_follow_up_execution = mediator.execute_claim_follow_up_plan(
                    claim_type='breach of contract',
                    user_id='testuser',
                    support_kind='evidence',
                    max_tasks_per_claim=2,
                )
                assert second_follow_up_execution['claims']['breach of contract']['task_count'] == 0
                assert second_follow_up_execution['claims']['breach of contract']['skipped_task_count'] == 1
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
                if os.path.exists(claim_support_db_path):
                    os.unlink(claim_support_db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    @pytest.mark.integration
    def test_follow_up_plan_suppresses_high_duplication_retrieval(self):
        """Strong duplicated graph support should suppress low-value follow-up retrieval unless forced."""
        try:
            from mediator import Mediator
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

        mock_backend = Mock()
        mock_backend.id = 'test-backend'

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            claim_support_db_path = f.name

        try:
            mediator = Mediator(
                backends=[mock_backend],
                claim_support_db_path=claim_support_db_path,
            )
            mediator.state.username = 'testuser'
            mediator.claim_support.register_claim_requirements(
                'testuser',
                {'breach of contract': ['Valid contract']},
            )
            mediator.claim_support.add_support_link(
                user_id='testuser',
                claim_type='breach of contract',
                claim_element_id='breach_of_contract:1',
                claim_element_text='Valid contract',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Authority support',
                source_table='legal_authorities',
            )

            mediator.query_claim_graph_support = Mock(return_value={
                'claim_element_id': 'breach_of_contract:1',
                'summary': {
                    'total_fact_count': 6,
                    'unique_fact_count': 2,
                    'duplicate_fact_count': 4,
                    'max_score': 2.5,
                    'support_by_kind': {'authority': 6},
                },
                'results': [
                    {
                        'fact_id': 'fact:1',
                        'score': 2.5,
                        'matched_claim_element': True,
                        'duplicate_count': 3,
                        'source_family': 'authority',
                        'source_record_id': 'authority:1',
                        'support_ref': '42 U.S.C. § 1983',
                        'source_ref': '42 U.S.C. § 1983',
                        'record_scope': 'legal_authority',
                        'artifact_family': 'legal_authority_reference',
                        'corpus_family': 'legal_authority',
                        'content_origin': 'legal_authority_reference',
                        'parse_source': 'authority_reference',
                        'input_format': 'text/plain',
                        'quality_tier': 'high',
                        'quality_score': 0.95,
                    },
                ],
            })
            mediator.discover_web_evidence = Mock(return_value={'total_records': 1})

            follow_up_plan = mediator.get_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
            )
            task = follow_up_plan['claims']['breach of contract']['tasks'][0]

            assert task['graph_support_strength'] == 'strong'
            assert task['should_suppress_retrieval'] is True
            assert task['suppression_reason'] == 'existing_support_high_duplication'

            follow_up_execution = mediator.execute_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
                support_kind='evidence',
                max_tasks_per_claim=1,
            )
            assert follow_up_execution['claims']['breach of contract']['task_count'] == 0
            assert follow_up_execution['claims']['breach of contract']['skipped_task_count'] == 1
            skipped_task = follow_up_execution['claims']['breach of contract']['skipped_tasks'][0]
            assert skipped_task['should_suppress_retrieval'] is True
            assert skipped_task['skipped']['suppressed']['reason'] == 'existing_support_high_duplication'
            mediator.discover_web_evidence.assert_not_called()

            forced_execution = mediator.execute_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
                support_kind='evidence',
                max_tasks_per_claim=1,
                force=True,
            )
            assert forced_execution['claims']['breach of contract']['task_count'] == 1
            mediator.discover_web_evidence.assert_called_once()
        finally:
            if os.path.exists(claim_support_db_path):
                os.unlink(claim_support_db_path)

    @pytest.mark.integration
    def test_follow_up_plan_routes_contradiction_only_tasks_to_manual_review(self):
        """Contradicted elements with no missing support kinds should become manual-review tasks, not retrieval tasks."""
        try:
            from mediator import Mediator
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

        mock_backend = Mock()
        mock_backend.id = 'test-backend'

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            claim_support_db_path = f.name

        try:
            mediator = Mediator(
                backends=[mock_backend],
                claim_support_db_path=claim_support_db_path,
            )
            mediator.state.username = 'testuser'
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'breach of contract': {
                        'required_support_kinds': ['evidence', 'authority'],
                        'elements': [
                            {
                                'element_id': 'breach_of_contract:1',
                                'element_text': 'Valid contract',
                                'coverage_status': 'covered',
                                'validation_status': 'contradicted',
                                'recommended_action': 'resolve_contradiction',
                                'support_by_kind': {'evidence': 1, 'authority': 1},
                                'proof_gap_count': 1,
                                'proof_gaps': [
                                    {
                                        'gap_type': 'contradiction_candidates',
                                        'message': 'Conflicting support facts require operator review.',
                                    }
                                ],
                                'reasoning_diagnostics': {
                                    'backend_available_count': 1,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value={
                'claim_element_id': 'breach_of_contract:1',
                'summary': {
                    'total_fact_count': 2,
                    'unique_fact_count': 2,
                    'duplicate_fact_count': 0,
                    'max_score': 1.0,
                    'support_by_kind': {'evidence': 1, 'authority': 1},
                },
                'results': [
                    {
                        'fact_id': 'fact:1',
                        'score': 1.0,
                        'matched_claim_element': True,
                        'source_family': 'mixed',
                        'source_record_id': 'support:1',
                        'support_ref': 'support:1',
                        'source_ref': 'artifact:1',
                        'record_scope': 'claim_support',
                        'artifact_family': 'support_packet',
                        'corpus_family': 'claim_support',
                        'content_origin': 'support_packet',
                        'parse_source': 'support_link_aggregation',
                        'input_format': 'application/json',
                        'quality_tier': 'medium',
                        'quality_score': 0.7,
                    },
                ],
            })
            mediator.discover_web_evidence = Mock(return_value={'total_records': 1})

            follow_up_plan = mediator.get_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
            )
            task = follow_up_plan['claims']['breach of contract']['tasks'][0]

            assert task['execution_mode'] == 'manual_review'
            assert task['requires_manual_review'] is True
            assert task['missing_support_kinds'] == []
            assert task['recommended_action'] == 'resolve_contradiction'

            follow_up_execution = mediator.execute_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
                support_kind='evidence',
                max_tasks_per_claim=1,
            )
            assert follow_up_execution['claims']['breach of contract']['task_count'] == 0
            assert follow_up_execution['claims']['breach of contract']['skipped_task_count'] == 1
            skipped_task = follow_up_execution['claims']['breach of contract']['skipped_tasks'][0]
            assert skipped_task['execution_mode'] == 'manual_review'
            assert skipped_task['skipped']['manual_review']['reason'] == 'contradiction_requires_resolution'
            import duckdb
            conn = duckdb.connect(claim_support_db_path)
            status, metadata_json = conn.execute(
                """
                SELECT status, metadata
                FROM claim_follow_up_execution
                WHERE support_kind = 'manual_review'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            conn.close()
            metadata = json.loads(metadata_json)
            assert status == 'skipped_manual_review'
            assert metadata['execution_mode'] == 'manual_review'
            assert metadata['validation_status'] == 'contradicted'
            assert metadata['skip_reason'] == 'contradiction_requires_resolution'
            assert metadata['follow_up_focus'] == 'contradiction_resolution'

            resolution = mediator.resolve_claim_follow_up_manual_review(
                claim_type='breach of contract',
                user_id='testuser',
                claim_element_id='breach_of_contract:1',
                claim_element='Valid contract',
                resolution_status='resolved_supported',
                resolution_notes='Operator reconciled the contradiction.',
                related_execution_id=1,
            )
            assert resolution['recorded'] is True

            follow_up_plan_after_resolution = mediator.get_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
            )
            assert follow_up_plan_after_resolution['claims']['breach of contract']['task_count'] == 0

            follow_up_execution_after_resolution = mediator.execute_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
                support_kind='evidence',
                max_tasks_per_claim=1,
            )
            assert follow_up_execution_after_resolution['claims']['breach of contract']['task_count'] == 0
            assert follow_up_execution_after_resolution['claims']['breach of contract']['skipped_task_count'] == 0
            mediator.discover_web_evidence.assert_not_called()
        finally:
            if os.path.exists(claim_support_db_path):
                os.unlink(claim_support_db_path)

    @pytest.mark.integration
    def test_follow_up_plan_uses_contradiction_targeted_queries_for_review_and_retrieve(self):
        """Contradicted elements with missing support kinds should use contradiction-targeted retrieval queries and persist that context."""
        try:
            from mediator import Mediator
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

        mock_backend = Mock()
        mock_backend.id = 'test-backend'

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            claim_support_db_path = f.name

        try:
            mediator = Mediator(
                backends=[mock_backend],
                claim_support_db_path=claim_support_db_path,
            )
            mediator.state.username = 'testuser'
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'breach of contract': {
                        'required_support_kinds': ['evidence', 'authority'],
                        'elements': [
                            {
                                'element_id': 'breach_of_contract:1',
                                'element_text': 'Valid contract',
                                'coverage_status': 'partially_supported',
                                'validation_status': 'contradicted',
                                'recommended_action': 'resolve_contradiction',
                                'support_by_kind': {'authority': 1},
                                'proof_gap_count': 1,
                                'proof_gaps': [
                                    {
                                        'gap_type': 'contradiction_candidates',
                                        'message': 'Conflicting support facts require operator review.',
                                    }
                                ],
                                'reasoning_diagnostics': {
                                    'backend_available_count': 1,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value={
                'claim_element_id': 'breach_of_contract:1',
                'summary': {
                    'total_fact_count': 1,
                    'unique_fact_count': 1,
                    'duplicate_fact_count': 0,
                    'max_score': 1.0,
                    'support_by_kind': {'authority': 1},
                },
                'results': [
                    {
                        'fact_id': 'fact:1',
                        'score': 1.0,
                        'matched_claim_element': True,
                        'source_family': 'authority',
                        'source_record_id': 'authority:1',
                        'support_ref': 'authority:1',
                        'source_ref': 'authority:1',
                        'record_scope': 'legal_authority',
                        'artifact_family': 'legal_authority_reference',
                        'corpus_family': 'legal_authority',
                        'content_origin': 'legal_authority_reference',
                        'parse_source': 'authority_reference',
                        'input_format': 'text/plain',
                        'quality_tier': 'high',
                        'quality_score': 0.9,
                    },
                ],
            })
            mediator.discover_web_evidence = Mock(return_value={'total_records': 1})

            follow_up_plan = mediator.get_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
            )
            task = follow_up_plan['claims']['breach of contract']['tasks'][0]

            assert task['execution_mode'] == 'review_and_retrieve'
            assert task['follow_up_focus'] == 'contradiction_resolution'
            assert task['query_strategy'] == 'contradiction_targeted'
            assert task['queries']['evidence'][0] == '"breach of contract" "Valid contract" contradictory evidence rebuttal'

            follow_up_execution = mediator.execute_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
                support_kind='evidence',
                max_tasks_per_claim=1,
            )
            executed_task = follow_up_execution['claims']['breach of contract']['tasks'][0]
            assert executed_task['execution_mode'] == 'review_and_retrieve'
            assert executed_task['query_strategy'] == 'contradiction_targeted'
            assert executed_task['follow_up_focus'] == 'contradiction_resolution'
            assert executed_task['executed']['evidence']['query'] == '"breach of contract" "Valid contract" contradictory evidence rebuttal'

            import duckdb
            conn = duckdb.connect(claim_support_db_path)
            query_text, status, metadata_json = conn.execute(
                """
                SELECT query_text, status, metadata
                FROM claim_follow_up_execution
                WHERE support_kind = 'evidence'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            conn.close()
            metadata = json.loads(metadata_json)
            assert query_text == '"breach of contract" "Valid contract" contradictory evidence rebuttal'
            assert status == 'executed'
            assert metadata['execution_mode'] == 'review_and_retrieve'
            assert metadata['query_strategy'] == 'contradiction_targeted'
            assert metadata['follow_up_focus'] == 'contradiction_resolution'
            assert metadata['proof_gap_types'] == ['contradiction_candidates']
            assert metadata['keywords'][0] == 'breach of contract'

            resolution = mediator.resolve_claim_follow_up_manual_review(
                claim_type='breach of contract',
                user_id='testuser',
                claim_element_id='breach_of_contract:1',
                claim_element='Valid contract',
                resolution_status='resolved_supported',
                resolution_notes='Operator resolved the contradiction but evidence is still incomplete.',
            )
            assert resolution['recorded'] is True

            follow_up_plan_after_resolution = mediator.get_claim_follow_up_plan(
                claim_type='breach of contract',
                user_id='testuser',
            )
            resolved_task = follow_up_plan_after_resolution['claims']['breach of contract']['tasks'][0]
            assert resolved_task['execution_mode'] == 'retrieve_support'
            assert resolved_task['requires_manual_review'] is False
            assert resolved_task['manual_review_resolved'] is True
            assert resolved_task['query_strategy'] == 'standard_gap_targeted'
            assert resolved_task['follow_up_focus'] == 'support_gap_closure'
            assert resolved_task['queries']['evidence'][0] == '"breach of contract" "Valid contract" evidence'
        finally:
            if os.path.exists(claim_support_db_path):
                os.unlink(claim_support_db_path)

    @pytest.mark.integration
    def test_follow_up_plan_clears_reasoning_gap_markers_after_resolution(self):
        """Resolved reasoning-gap review work should downgrade to ordinary retrieval with normalized support-gap metadata."""
        try:
            from mediator import Mediator
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

        mock_backend = Mock()
        mock_backend.id = 'test-backend'

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            claim_support_db_path = f.name

        try:
            mediator = Mediator(
                backends=[mock_backend],
                claim_support_db_path=claim_support_db_path,
            )
            mediator.state.username = 'testuser'
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['evidence', 'authority'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'partially_supported',
                                'validation_status': 'incomplete',
                                'recommended_action': 'collect_missing_support_kind',
                                'support_by_kind': {'evidence': 1},
                                'proof_gap_count': 2,
                                'proof_gaps': [
                                    {'gap_type': 'logic_unprovable'},
                                    {'gap_type': 'ontology_validation_failed'},
                                ],
                                'proof_decision_trace': {
                                    'decision_source': 'logic_proof_partial',
                                    'logic_provable_count': 1,
                                    'logic_unprovable_count': 1,
                                    'ontology_validation_signal': 'invalid',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 2,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value={
                'claim_element_id': 'employment:1',
                'summary': {
                    'total_fact_count': 0,
                    'unique_fact_count': 0,
                    'duplicate_fact_count': 0,
                    'max_score': 0.0,
                    'support_by_kind': {'evidence': 1},
                },
                'results': [],
            })
            mediator.search_legal_authorities = Mock(return_value={'statutes': [], 'cases': []})

            follow_up_plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
            )
            task = follow_up_plan['claims']['employment']['tasks'][0]

            assert task['execution_mode'] == 'review_and_retrieve'
            assert task['follow_up_focus'] == 'reasoning_gap_closure'
            assert task['query_strategy'] == 'reasoning_gap_targeted'
            assert task['proof_gap_types'] == ['logic_unprovable', 'ontology_validation_failed']

            resolution = mediator.resolve_claim_follow_up_manual_review(
                claim_type='employment',
                user_id='testuser',
                claim_element_id='employment:1',
                claim_element='Protected activity',
                resolution_status='resolved_supported',
                resolution_notes='Operator validated the reasoning gap manually.',
            )
            assert resolution['recorded'] is True

            follow_up_plan_after_resolution = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
            )
            resolved_task = follow_up_plan_after_resolution['claims']['employment']['tasks'][0]
            assert resolved_task['execution_mode'] == 'retrieve_support'
            assert resolved_task['requires_manual_review'] is False
            assert resolved_task['manual_review_resolved'] is True
            assert resolved_task['follow_up_focus'] == 'support_gap_closure'
            assert resolved_task['query_strategy'] == 'standard_gap_targeted'
            assert resolved_task['proof_gap_types'] == []
            assert resolved_task['proof_gap_count'] == 0
            assert resolved_task['proof_decision_source'] == 'partial_support'
            assert resolved_task['logic_provable_count'] == 0
            assert resolved_task['logic_unprovable_count'] == 0
            assert resolved_task['ontology_validation_signal'] == ''
            assert resolved_task['queries']['authority'][0] == '"employment" "Protected activity" statute'
        finally:
            if os.path.exists(claim_support_db_path):
                os.unlink(claim_support_db_path)
