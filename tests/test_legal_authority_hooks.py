"""
Unit tests for Legal Authority Hooks

Tests for legal authority search, storage, and analysis functionality.
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


pytestmark = pytest.mark.no_auto_network


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

    def test_search_all_sources_filters_by_authority_families(self):
        """Authority-family filtering should skip unrelated source searches."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            hook = LegalAuthoritySearchHook(mock_mediator)
            hook.search_us_code = Mock(return_value=[{'citation': '42 U.S.C. § 1983'}])
            hook.search_federal_register = Mock(return_value=[{'title': 'EEOC rule'}])
            hook.search_case_law = Mock(return_value=[{'citation': 'Smith v. Example'}])
            hook.search_web_archives = Mock(return_value=[{'url': 'https://law.cornell.edu/example'}])

            results = hook.search_all_sources(
                'test query',
                authority_families=['statute', 'regulation'],
            )

            hook.search_us_code.assert_called_once_with('test query', max_results=5)
            hook.search_federal_register.assert_called_once_with('test query', max_results=5)
            hook.search_case_law.assert_not_called()
            hook.search_web_archives.assert_not_called()
            assert results['statutes'] == [{'citation': '42 U.S.C. § 1983'}]
            assert results['regulations'] == [{'title': 'EEOC rule'}]
            assert results['case_law'] == []
            assert results['web_archives'] == []
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_build_search_programs_creates_claim_aware_program_bundle(self):
        """Test claim-aware legal search program generation."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(
                return_value="retaliation causation\nprotected activity\ntemporal proximity"
            )

            hook = LegalAuthoritySearchHook(mock_mediator)

            programs = hook.build_search_programs(
                query="employment retaliation",
                claim_type="employment retaliation",
                claim_elements=[
                    {
                        'claim_element_id': 'employment_retaliation:3',
                        'claim_element_text': 'Causal connection',
                    }
                ],
                jurisdiction='9th Circuit',
                forum='federal',
            )

            assert len(programs) == 5
            assert {program['program_type'] for program in programs} == {
                'element_definition_search',
                'fact_pattern_search',
                'procedural_search',
                'adverse_authority_search',
                'treatment_check_search',
            }
            assert {program['authority_intent'] for program in programs} == {
                'support',
                'procedural',
                'oppose',
                'confirm_good_law',
            }
            assert all(program['claim_element_id'] == 'employment_retaliation:3' for program in programs)
            assert all(program['jurisdiction'] == '9th Circuit' for program in programs)
            assert all(program['forum'] == 'federal' for program in programs)
            assert all(program['program_id'].startswith('legal_search_program:') for program in programs)
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

    def test_add_authority_resolves_claim_element(self):
        """Test authority storage enriches claim element metadata when available"""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.claim_support = Mock()
            mock_mediator.claim_support.resolve_claim_element = Mock(return_value={
                'claim_element_id': 'civil_rights:1',
                'claim_element_text': 'Protected activity',
            })

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)
                mock_mediator.get_three_phase_status = Mock(return_value={
                    'current_phase': 'intake',
                    'intake_readiness': {
                        'ready_to_advance': True,
                    },
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T14:00:00+00:00',
                        'confirmation_note': 'ready for authority graph persistence',
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

                authority_data = {
                    'type': 'statute',
                    'source': 'us_code',
                    'citation': '42 U.S.C. § 1983',
                    'title': 'Protected activity protections',
                    'content': 'Test statute content...',
                }

                record_id = hook.add_authority(
                    authority_data,
                    user_id='testuser',
                    claim_type='civil rights',
                )
                results = hook.get_authorities_by_claim('testuser', 'civil rights')

                assert record_id > 0
                assert results[0]['claim_element_id'] == 'civil_rights:1'
                assert results[0]['claim_element'] == 'Protected activity'
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_deduplicates_same_claim_scope(self):
        """Test duplicate authorities in the same claim scope reuse the existing record."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                mock_mediator.get_three_phase_status = Mock(return_value={
                    'current_phase': 'intake',
                    'intake_readiness': {
                        'ready_to_advance': True,
                    },
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T14:00:00+00:00',
                        'confirmation_note': 'ready for authority graph persistence',
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
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)

                authority_data = {
                    'type': 'statute',
                    'source': 'us_code',
                    'citation': '42 U.S.C. § 1983',
                    'title': 'Civil Rights Act',
                    'content': 'Test statute content...',
                    'url': 'https://example.com/usc/42/1983',
                    'metadata': {'test': 'data'},
                    'relevance_score': 0.9,
                }

                first_id = hook.add_authority(
                    authority_data,
                    user_id='testuser',
                    complaint_id='complaint-1',
                    claim_type='civil rights violation',
                )
                second_id = hook.add_authority(
                    authority_data,
                    user_id='testuser',
                    complaint_id='complaint-1',
                    claim_type='civil rights violation',
                )

                results = hook.get_authorities_by_claim('testuser', 'civil rights violation')

                assert first_id > 0
                assert second_id == first_id
                assert len(results) == 1
                assert results[0]['citation'] == '42 U.S.C. § 1983'
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_duplicate_can_persist_new_treatment_records(self):
        """Test duplicate authority upserts can attach treatment records to the reused row."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)

                authority_data = {
                    'type': 'case_law',
                    'source': 'recap',
                    'citation': 'Smith v. Jones, 123 F.3d 456',
                    'title': 'Smith v. Jones',
                    'content': 'Courts require a causal connection.',
                }

                record_id = hook.add_authority(
                    authority_data,
                    user_id='testuser',
                    complaint_id='complaint-1',
                    claim_type='employment retaliation',
                )

                reused_record_id = hook.add_authority(
                    {
                        **authority_data,
                        'treatment_records': [
                            {
                                'treatment_type': 'questioned',
                                'treated_by_citation': 'Jones v. Smith, 456 F.4th 789',
                                'treatment_source': 'later_case_search',
                                'treatment_confidence': 0.82,
                            }
                        ],
                    },
                    user_id='testuser',
                    complaint_id='complaint-1',
                    claim_type='employment retaliation',
                )

                authority = hook.get_authority_by_id(record_id)
                treatments = hook.get_authority_treatments(record_id)

                assert reused_record_id == record_id
                assert authority is not None
                assert authority['treatment_summary']['record_count'] == 1
                assert treatments[0]['treatment_type'] == 'questioned'
                assert treatments[0]['treated_by_citation'] == 'Jones v. Smith, 456 F.4th 789'
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
                assert results[0]['fact_count'] >= 1
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_persists_fact_rows(self):
        """Test storing an authority also persists extracted fact rows."""
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
                    'content': 'Protected activity is covered. Retaliation is prohibited.',
                }

                record_id = hook.add_authority(authority_data, 'testuser', claim_type='civil rights')
                authorities = hook.get_authorities_by_claim('testuser', 'civil rights')
                facts = hook.get_authority_facts(record_id)

                assert record_id > 0
                assert authorities[0]['fact_count'] >= 1
                assert len(facts) >= 1
                assert 'Protected activity' in facts[0]['text'] or 'Retaliation' in facts[0]['text']
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_persists_parse_summary_and_chunks(self):
        """Test authority parsing stores parse summary fields and chunk rows."""
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
                    'type': 'regulation',
                    'source': 'federal_register',
                    'citation': '91 Fed. Reg. 12345',
                    'title': 'Workplace protections',
                    'content': 'Employers must preserve records.\n\nRetaliation is prohibited when workers report violations.',
                }

                record_id = hook.add_authority(authority_data, 'testuser', claim_type='employment')
                authority = hook.get_authority_by_id(record_id)
                chunks = hook.get_authority_chunks(record_id)

                assert record_id > 0
                assert authority is not None
                assert authority['parse_status'] in {'fallback', 'available-fallback'}
                assert authority['chunk_count'] >= 1
                assert authority['parsed_text_preview'].startswith('Employers must preserve records.')
                assert authority['parse_metadata']['parser_version'] == 'documents-adapter:1'
                assert authority['parse_metadata']['source'] == 'legal_authority'
                assert authority['parse_metadata']['content_origin'] == 'authority_full_text'
                assert authority['parse_metadata']['content_source_field'] == 'content'
                assert authority['provenance']['metadata']['artifact_family'] == 'legal_authority_text'
                assert authority['provenance']['metadata']['content_origin'] == 'authority_full_text'
                assert authority['provenance']['metadata']['text_available'] is True
                assert authority['parse_metadata']['transform_lineage']['source'] == 'legal_authority'
                assert authority['parse_metadata']['transform_lineage']['content_origin'] == 'authority_full_text'
                assert len(chunks) >= 1
                assert chunks[0]['chunk_id'] == 'chunk-0'
                assert chunks[0]['metadata']['source'] == 'legal_authority'
                facts = hook.get_authority_facts(record_id)
                assert len(facts) >= 1
                assert facts[0]['source_authority_id'] == f'authority:{record_id}'
                assert facts[0]['source_family'] == 'legal_authority'
                assert facts[0]['source_record_id'] == record_id
                assert facts[0]['source_ref'] == f'authority:{record_id}'
                assert facts[0]['record_scope'] == 'legal_authority'
                assert facts[0]['artifact_family'] == 'legal_authority_text'
                assert facts[0]['corpus_family'] == 'legal_authority'
                assert facts[0]['content_origin'] == 'authority_full_text'
                assert facts[0]['parse_source'] == 'legal_authority'
                assert facts[0]['metadata']['parse_lineage']['source'] == 'legal_authority'
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_preserves_html_parse_contract(self):
        """Test authority HTML content is normalized through the shared parse contract."""
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
                    'type': 'regulation',
                    'source': 'federal_register',
                    'citation': '92 Fed. Reg. 67890',
                    'title': 'Workplace investigations',
                    'html_body': '<html><body><h1>Investigation duties</h1><p>Employers must investigate complaints promptly.</p></body></html>',
                }

                record_id = hook.add_authority(authority_data, 'testuser', claim_type='employment')
                authority = hook.get_authority_by_id(record_id)
                chunks = hook.get_authority_chunks(record_id)
                facts = hook.get_authority_facts(record_id)

                assert record_id > 0
                assert authority['parse_metadata']['input_format'] == 'html'
                assert authority['parse_metadata']['content_origin'] == 'authority_full_text'
                assert authority['parse_metadata']['content_source_field'] == 'html_body'
                assert authority['parse_metadata']['transform_lineage']['input_format'] == 'html'
                assert authority['parse_metadata']['transform_lineage']['normalization'] == 'html_to_text'
                assert authority['parsed_text_preview'].startswith('Investigation duties')
                assert chunks[0]['metadata']['input_format'] == 'html'
                assert facts[0]['metadata']['parse_lineage']['input_format'] == 'html'
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_marks_reference_fallback_lineage(self):
        """Test citation-only authority records expose fallback parse lineage."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)

                authority_data = {
                    'type': 'case_law',
                    'source': 'recap',
                    'citation': 'Smith v. Jones, 123 F.3d 456',
                    'title': 'Smith v. Jones',
                }

                record_id = hook.add_authority(authority_data, 'testuser', claim_type='employment')
                authority = hook.get_authority_by_id(record_id)

                assert record_id > 0
                assert authority['parse_metadata']['content_origin'] == 'authority_reference_fallback'
                assert authority['parse_metadata']['content_source_field'] == 'citation_title_fallback'
                assert authority['parse_metadata']['fallback_mode'] == 'citation_title_only'
                assert authority['provenance']['metadata']['artifact_family'] == 'legal_authority_reference'
                assert authority['provenance']['metadata']['content_origin'] == 'authority_reference_fallback'
                assert authority['provenance']['metadata']['fallback_mode'] == 'citation_title_only'
                assert authority['provenance']['metadata']['text_available'] is False
                assert authority['parse_metadata']['transform_lineage']['content_origin'] == 'authority_reference_fallback'
                assert authority['parse_metadata']['transform_lineage']['fallback_mode'] == 'citation_title_only'
                assert authority['parsed_text_preview'].startswith('Smith v. Jones')
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_persists_graph_metadata(self):
        """Test authority storage persists graph summary fields and graph rows."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                mock_mediator.get_three_phase_status = Mock(return_value={
                    'current_phase': 'intake',
                    'intake_readiness': {
                        'ready_to_advance': True,
                    },
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T14:00:00+00:00',
                        'confirmation_note': 'ready for authority graph persistence',
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
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)

                authority_data = {
                    'type': 'statute',
                    'source': 'us_code',
                    'citation': '42 U.S.C. § 1983',
                    'title': 'Civil Rights Act',
                    'content': 'Protected activity is covered. Retaliation is prohibited.',
                }

                record_id = hook.add_authority(authority_data, 'testuser', claim_type='civil rights')
                authority = hook.get_authority_by_id(record_id)
                graph = hook.get_authority_graph(record_id)

                assert record_id > 0
                assert authority is not None
                assert authority['graph_status'] in {'unavailable', 'available-fallback'}
                assert authority['graph_entity_count'] >= 1
                assert authority['graph_relationship_count'] >= 1
                assert authority['graph_metadata']['graph_snapshot']['created'] is True
                assert authority['graph_metadata']['graph_snapshot']['reused'] is False
                assert authority['graph_metadata']['graph_snapshot']['metadata']['record_scope'] == 'legal_authority'
                assert authority['graph_metadata']['graph_snapshot']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T14:00:00+00:00',
                        'confirmation_note': 'ready for authority graph persistence',
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
                assert graph['status'] == 'available'
                assert any(entity['type'] == 'fact' for entity in graph['entities'])
                assert len(graph['relationships']) >= 1
                assert all('relation_type' in rel for rel in graph['relationships'])
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_persists_treatment_records_and_search_program_metadata(self):
        """Test authority storage keeps search-program metadata and typed treatment records."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)

                authority_data = {
                    'type': 'case_law',
                    'source': 'recap',
                    'citation': 'Smith v. Jones, 123 F.3d 456',
                    'title': 'Smith v. Jones',
                    'content': 'Courts require a causal connection. Prior decisions have questioned broad employer defenses.',
                    'search_programs': [
                        {
                            'program_id': 'legal_search_program:test',
                            'program_type': 'fact_pattern_search',
                            'authority_intent': 'support',
                            'query_text': 'employment retaliation causal connection fact pattern',
                            'claim_element_id': 'employment_retaliation:3',
                            'claim_element_text': 'Causal connection',
                            'jurisdiction': '9th Circuit',
                            'forum': 'federal',
                            'authority_families': ['case_law'],
                            'search_terms': ['causal connection', 'retaliation'],
                            'metadata': {'base_query': 'employment retaliation'},
                        }
                    ],
                    'treatment_records': [
                        {
                            'treatment_type': 'questioned',
                            'treated_by_citation': 'Jones v. Smith, 456 F.4th 789',
                            'treatment_source': 'later_case_search',
                            'treatment_confidence': 0.82,
                            'treatment_date': '2025-02-14',
                            'treatment_explanation': 'Later panel questioned whether the earlier rule extends beyond direct evidence cases.',
                            'metadata': {'program_type': 'treatment_check_search'},
                        }
                    ],
                }

                record_id = hook.add_authority(authority_data, 'testuser', claim_type='employment retaliation')
                authority = hook.get_authority_by_id(record_id)
                treatments = hook.get_authority_treatments(record_id)

                assert record_id > 0
                assert authority is not None
                assert authority['metadata']['search_programs'][0]['program_type'] == 'fact_pattern_search'
                assert authority['metadata']['search_programs'][0]['claim_element_id'] == 'employment_retaliation:3'
                assert len(authority['treatment_records']) == 1
                assert authority['treatment_summary']['record_count'] == 1
                assert authority['treatment_summary']['by_type']['questioned'] == 1
                assert treatments[0]['treatment_type'] == 'questioned'
                assert treatments[0]['treated_by_citation'] == 'Jones v. Smith, 456 F.4th 789'
                assert treatments[0]['treatment_source'] == 'later_case_search'
                assert treatments[0]['treatment_confidence'] == pytest.approx(0.82)
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_persists_rule_candidates(self):
        """Test authority storage extracts and persists first-pass rule candidates from parsed authority text."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.claim_support = Mock()
            mock_mediator.claim_support.resolve_claim_element = Mock(return_value={
                'claim_element_id': 'employment:1',
                'claim_element_text': 'Protected activity',
            })

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)

                authority_data = {
                    'type': 'regulation',
                    'source': 'federal_register',
                    'citation': '91 Fed. Reg. 12345',
                    'title': 'Workplace protections',
                    'content': (
                        'Employers must preserve complaint records. '
                        'Actions must be filed within 180 days of notice. '
                        'Except where notice is impossible, the deadline still applies.'
                    ),
                }

                record_id = hook.add_authority(authority_data, 'testuser', claim_type='employment')
                authority = hook.get_authority_by_id(record_id)
                rule_candidates = hook.get_authority_rule_candidates(record_id)

                assert record_id > 0
                assert authority is not None
                assert authority['rule_candidate_summary']['record_count'] >= 2
                assert authority['rule_candidate_summary']['by_type']['procedural_prerequisite'] >= 1
                assert len(rule_candidates) >= 2
                assert any(candidate['rule_type'] == 'procedural_prerequisite' for candidate in rule_candidates)
                assert any(candidate['rule_type'] == 'exception' for candidate in rule_candidates)
                assert all(candidate['claim_element_id'] == 'employment:1' for candidate in rule_candidates)
                assert all(candidate['claim_element_text'] == 'Protected activity' for candidate in rule_candidates)
                assert all(candidate['provenance']['source_system'] == 'federal_register' for candidate in rule_candidates)
                assert all('chunk_index' in candidate['metadata'] for candidate in rule_candidates)
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
                assert stats['total_facts'] >= 3
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
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                claim_support_db_path = f.name
            
            try:
                mediator = Mediator(
                    backends=[mock_backend],
                    legal_authority_db_path=db_path,
                    claim_support_db_path=claim_support_db_path,
                )
                mediator.state.username = 'testuser'
                mediator.state.legal_classification = {
                    'claim_types': ['civil rights']
                }
                mediator.claim_support.register_claim_requirements(
                    'testuser',
                    {'civil rights': ['Protected activity', 'Adverse action']},
                )
                
                # Mock search results
                mediator.legal_authority_search.search_all_sources = Mock(return_value={
                    'statutes': [
                        {
                            'citation': '42 U.S.C. § 1983',
                            'title': 'Protected activity under the Civil Rights Act',
                            'content': 'Test content about protected activity'
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
                assert stored['total_records'] == 1
                assert stored['total_new'] == 1
                assert stored['total_reused'] == 0
                assert stored['total_support_links_added'] == 1
                assert stored['total_support_links_reused'] == 0

                stored_duplicate = mediator.store_legal_authorities(results, claim_type='civil rights')
                assert stored_duplicate['statutes'] == 1
                assert stored_duplicate['statutes_new'] == 0
                assert stored_duplicate['statutes_reused'] == 1
                assert stored_duplicate['statutes_support_links_added'] == 0
                assert stored_duplicate['statutes_support_links_reused'] == 1
                assert stored_duplicate['total_records'] == 1
                assert stored_duplicate['total_new'] == 0
                assert stored_duplicate['total_reused'] == 1

                support_links = mediator.get_claim_support(claim_type='civil rights')
                assert len(support_links) > 0
                assert support_links[0]['claim_element_id'] == 'civil_rights:1'

                support_summary = mediator.summarize_claim_support(claim_type='civil rights')
                assert support_summary['claims']['civil rights']['support_by_kind']['authority'] > 0
                assert support_summary['claims']['civil rights']['covered_elements'] == 1
                assert support_summary['claims']['civil rights']['total_facts'] >= 1
                authority_link = support_summary['claims']['civil rights']['elements'][0]['links'][0]
                assert authority_link['authority_record_id'] >= 1
                assert authority_link['fact_count'] >= 1
                assert len(authority_link['facts']) >= 1

                claim_overview = mediator.get_claim_overview(claim_type='civil rights')
                assert claim_overview['claims']['civil rights']['partially_supported_count'] == 1
                assert claim_overview['claims']['civil rights']['missing_count'] == 1

                coverage_matrix = mediator.get_claim_coverage_matrix(claim_type='civil rights')
                assert coverage_matrix['claims']['civil rights']['status_counts']['partially_supported'] == 1
                assert coverage_matrix['claims']['civil rights']['status_counts']['missing'] == 1
                coverage_element = coverage_matrix['claims']['civil rights']['elements'][0]
                assert coverage_element['status'] == 'partially_supported'
                assert coverage_element['missing_support_kinds'] == ['evidence']
                assert coverage_element['links_by_kind']['authority'][0]['record_summary']['citation'] == '42 U.S.C. § 1983'
                assert coverage_element['links_by_kind']['authority'][0]['graph_summary']['entity_count'] >= 0

                follow_up_plan = mediator.get_claim_follow_up_plan(claim_type='civil rights')
                assert follow_up_plan['claims']['civil rights']['task_count'] == 2
                protected_activity_task = next(
                    task for task in follow_up_plan['claims']['civil rights']['tasks']
                    if task['claim_element_id'] == 'civil_rights:1'
                )
                adverse_action_task = next(
                    task for task in follow_up_plan['claims']['civil rights']['tasks']
                    if task['claim_element_id'] == 'civil_rights:2'
                )
                assert protected_activity_task['missing_support_kinds'] == ['evidence']
                assert protected_activity_task['has_graph_support'] is True
                assert protected_activity_task['graph_support']['summary']['support_by_kind']['authority'] >= 1
                assert protected_activity_task['graph_support_strength'] in {'moderate', 'strong'}
                assert protected_activity_task['recommended_action'] in {
                    'collect_fact_support',
                    'target_missing_support_kind',
                    'collect_missing_support_kind',
                    'review_existing_support',
                }
                assert protected_activity_task['priority'] in {'medium', 'low'}
                assert adverse_action_task['missing_support_kinds'] == ['evidence', 'authority']

                mediator.query_claim_graph_support = Mock(return_value={
                    'claim_element_id': 'civil_rights:1',
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
                            'support_ref': 'support:authority:1',
                            'source_ref': 'authority:1',
                            'record_scope': 'legal_authority',
                            'artifact_family': 'legal_authority_text',
                            'corpus_family': 'legal_authority',
                            'content_origin': 'legal_authority_text',
                            'parse_source': 'authority_document_parse',
                            'input_format': 'text/html',
                            'quality_tier': 'high',
                            'quality_score': 0.94,
                        },
                    ],
                })
                mediator.discover_web_evidence = Mock(return_value={'total_records': 1})
                suppressed_plan = mediator.get_claim_follow_up_plan(claim_type='civil rights')
                suppressed_task = next(
                    task for task in suppressed_plan['claims']['civil rights']['tasks']
                    if task['claim_element_id'] == 'civil_rights:1'
                )
                assert suppressed_task['should_suppress_retrieval'] is True
                assert suppressed_task['suppression_reason'] == 'existing_support_high_duplication'
                suppressed_execution = mediator.execute_claim_follow_up_plan(
                    claim_type='civil rights',
                    user_id='testuser',
                    support_kind='evidence',
                    max_tasks_per_claim=1,
                )
                assert suppressed_execution['claims']['civil rights']['task_count'] == 0
                assert suppressed_execution['claims']['civil rights']['skipped_task_count'] == 1
                assert suppressed_execution['claims']['civil rights']['skipped_tasks'][0]['skipped']['suppressed']['reason'] == 'existing_support_high_duplication'
                mediator.discover_web_evidence.assert_not_called()
                
                # Retrieve
                authorities = mediator.get_legal_authorities(claim_type='civil rights')
                assert len(authorities) > 0
                assert authorities[0]['claim_element'] == 'Protected activity'
                assert authorities[0]['fact_count'] >= 1
                authority_facts = mediator.get_authority_facts(authorities[0]['id'])
                assert len(authority_facts) >= 1

                auto_results = mediator.research_case_automatically(user_id='testuser')
                assert auto_results['authorities_stored']['civil rights']['total_records'] == 1
                assert auto_results['authorities_stored']['civil rights']['total_new'] == 0
                assert auto_results['authorities_stored']['civil rights']['total_reused'] == 1
                assert auto_results['authorities_stored']['civil rights']['total_support_links_added'] == 0
                assert auto_results['authorities_stored']['civil rights']['total_support_links_reused'] == 1
                assert auto_results['claim_coverage_matrix']['civil rights']['status_counts']['partially_supported'] == 1
                assert auto_results['claim_coverage_matrix']['civil rights']['status_counts']['missing'] == 1
                assert auto_results['claim_coverage_summary']['civil rights']['status_counts']['partially_supported'] == 1
                assert auto_results['claim_coverage_summary']['civil rights']['status_counts']['missing'] == 1
                assert auto_results['claim_coverage_summary']['civil rights']['missing_elements'] == ['Adverse action']
                assert auto_results['claim_coverage_summary']['civil rights']['partially_supported_elements'] == ['Protected activity']
                assert auto_results['claim_coverage_summary']['civil rights']['unresolved_element_count'] == 2
                assert auto_results['claim_coverage_summary']['civil rights']['recommended_gap_actions'] == {
                    'collect_initial_support': 1,
                    'collect_fact_support': 1,
                }
                assert auto_results['claim_coverage_summary']['civil rights']['contradiction_candidate_count'] == 0
                assert auto_results['claim_coverage_summary']['civil rights']['validation_status'] == 'incomplete'
                assert auto_results['claim_support_validation']['civil rights']['validation_status_counts']['incomplete'] == 1
                assert auto_results['claim_support_validation']['civil rights']['proof_gap_count'] == 3
                assert auto_results['claim_support_gaps']['civil rights']['unresolved_count'] == 2
                assert auto_results['claim_contradiction_candidates']['civil rights']['candidate_count'] == 0
                assert auto_results['claim_support_snapshots']['civil rights']['gaps']['snapshot_id'] > 0
                assert auto_results['claim_support_snapshots']['civil rights']['contradictions']['snapshot_id'] > 0
                assert auto_results['claim_support_snapshot_summary']['civil rights']['total_snapshot_count'] == 2
                assert auto_results['claim_support_snapshot_summary']['civil rights']['fresh_snapshot_count'] == 2
                assert auto_results['claim_support_snapshot_summary']['civil rights']['stale_snapshot_count'] == 0
                assert auto_results['claim_reasoning_review']['civil rights']['total_element_count'] == len(
                    auto_results['claim_support_validation']['civil rights']['elements']
                )
                assert auto_results['follow_up_history']['civil rights'] == []
                assert auto_results['follow_up_history_summary']['civil rights']['total_entry_count'] == 0
                assert auto_results['claim_overview']['civil rights']['partially_supported_count'] == 1
                assert auto_results['claim_overview']['civil rights']['missing_count'] == 1
                assert auto_results['follow_up_plan']['civil rights']['task_count'] == 2
                assert auto_results['follow_up_plan_summary']['civil rights']['task_count'] == 2
                assert auto_results['follow_up_plan_summary']['civil rights']['contradiction_task_count'] == 0
                assert auto_results['follow_up_plan_summary']['civil rights']['reasoning_gap_task_count'] == 0
                assert auto_results['follow_up_plan_summary']['civil rights']['follow_up_focus_counts'] == {
                    'fact_gap_closure': 1,
                    'support_gap_closure': 1,
                }
                assert auto_results['follow_up_plan_summary']['civil rights']['query_strategy_counts'] == {
                    'rule_fact_targeted': 1,
                    'standard_gap_targeted': 1,
                }
                assert auto_results['follow_up_plan_summary']['civil rights']['proof_decision_source_counts'] == {
                    'missing_support': 1,
                    'partial_support': 1,
                }
                assert auto_results['follow_up_plan_summary']['civil rights']['resolution_applied_counts'] == {}

                mediator.search_legal_authorities = Mock(return_value={
                    'statutes': [],
                    'regulations': [],
                    'case_law': [],
                    'web_archives': [],
                })
                mediator.store_legal_authorities = Mock(return_value={
                    'statutes': 0,
                    'regulations': 0,
                    'case_law': 0,
                    'web_archives': 0,
                })
                follow_up_execution = mediator.execute_claim_follow_up_plan(
                    claim_type='civil rights',
                    user_id='testuser',
                    support_kind='authority',
                    max_tasks_per_claim=2,
                )
                assert follow_up_execution['claims']['civil rights']['task_count'] == 0

                auto_results_with_execution = mediator.research_case_automatically(
                    user_id='testuser',
                    execute_follow_up=True,
                )
                assert auto_results_with_execution['follow_up_execution']['civil rights']['task_count'] == 0
                assert auto_results_with_execution['follow_up_execution_summary']['civil rights']['executed_task_count'] == 0
                assert auto_results_with_execution['follow_up_execution_summary']['civil rights']['contradiction_task_count'] == 0
                assert auto_results_with_execution['follow_up_execution_summary']['civil rights']['reasoning_gap_task_count'] == 0
                assert auto_results_with_execution['follow_up_execution_summary']['civil rights']['resolution_applied_counts'] == {}
                assert auto_results_with_execution['follow_up_history_summary']['civil rights']['total_entry_count'] == 0
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
                if os.path.exists(claim_support_db_path):
                    os.unlink(claim_support_db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
