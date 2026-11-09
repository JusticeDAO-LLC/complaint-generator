"""
Unit tests for Legal Authority Hooks

Tests for legal authority search, storage, and analysis functionality.
"""
import json
import pytest
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


pytestmark = pytest.mark.no_auto_network


def _install_legal_passage_graph_fixture(monkeypatch):
    """Give only the requesting storage unit test an explicit legal graph.

    Extraction capability is exercised separately by the FACT02 contract.
    These rows describe supplied authority text, never complainant facts or
    a rule's applicability. Document parsing and all durable storage stay real.
    """
    from dataclasses import replace
    from mediator import legal_authority_hooks
    from integrations.ipfs_datasets.provenance import build_provenance, stable_content_hash
    from integrations.ipfs_datasets.types import (
        GraphEntity, GraphRelationship, build_user_assertion_envelope,
    )

    calls = []

    def legal_passage_graph(text, *, source_id='', metadata=None):
        assert isinstance(text, str) and text.strip()
        assert source_id.startswith('authority:') and source_id.removeprefix('authority:').isdigit()
        assert isinstance(metadata, dict) and metadata['artifact_id'] == source_id
        assert metadata['legal_passage'] is True
        assert metadata['source_family'] == metadata['record_scope'] == 'legal_authority'
        assert metadata['artifact_family'] == 'legal_authority_text'
        passage = next(line.strip() for line in text.splitlines() if line.strip())
        raw = text.encode('utf-8')
        start = raw.index(passage.encode('utf-8'))
        span = {'start': start, 'end': start + len(passage.encode('utf-8')), 'text': passage}
        envelope = build_user_assertion_envelope(
            source_text=text, source_kind='legal_text', source_id=source_id,
            source_span=span, source_hash=stable_content_hash(raw),
            record_type='legal_text', assertion_status='legal_text',
            extractor_version='authority-storage-unit-fixture.v1',
        )
        assert envelope.record_type == 'legal_text' and not envelope.is_asserted_user_fact
        assert raw[envelope.source_span_start:envelope.source_span_end].decode('utf-8') == passage
        provenance = replace(build_provenance(
            source_url=metadata.get('source_url', ''), acquisition_method='synthetic_storage_fixture',
            source_type='legal_authority', content_hash=stable_content_hash(raw),
            source_system='authority-storage-unit-fixture',
            metadata={'record_scope': 'legal_authority', 'source_span': span},
        ), assertion=envelope.as_dict()).as_dict()
        attributes = {
            **metadata, 'record_scope': 'legal_authority', 'source_family': 'legal_authority',
            'record_type': 'legal_text', 'content_origin': 'legal_authority_text',
            'source_span': span, 'assertion': envelope.as_dict(),
        }
        authority_node = GraphEntity(
            entity_id=source_id + ':source', entity_type='legal_authority',
            name=metadata.get('title', ''), attributes=dict(attributes), provenance=provenance,
            assertion=envelope.as_dict(),
        ).as_dict()
        passage_node = GraphEntity(
            entity_id=source_id + ':legal-passage:0', entity_type='fact', name=passage,
            confidence=1.0, attributes={**attributes, 'text': passage, 'sentence_index': 0},
            provenance=provenance, assertion=envelope.as_dict(),
        ).as_dict()
        relationship = GraphRelationship(
            relationship_id=source_id + ':contains-legal-passage:0',
            source_id=authority_node['id'], target_id=passage_node['id'],
            relation_type='contains_legal_passage', confidence=1.0,
            attributes=dict(attributes), provenance=provenance, assertion=envelope.as_dict(),
        ).as_dict()
        calls.append({'source_id': source_id, 'span': span, 'content_hash': stable_content_hash(raw)})
        return {'status': 'available', 'entities': [authority_node, passage_node],
                'relationships': [relationship], 'metadata': {
                    **metadata, 'fixture_scope': 'authority-storage-unit',
                    'record_scope': 'legal_authority', 'provenance': provenance,
                }}

    monkeypatch.setattr(legal_authority_hooks, 'extract_graph_from_text', legal_passage_graph)
    return calls


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
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T18:00:00+00:00',
                    'confirmation_note': 'ready for authority child artifact persistence',
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
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T18:00:00+00:00',
                    'confirmation_note': 'ready for authority record persistence',
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
            hook.search_state_laws = Mock(return_value=[])
            hook.search_federal_register = Mock(return_value=[])
            hook.search_administrative_law = Mock(return_value=[])
            hook.search_case_law = Mock(return_value=[])
            hook.search_web_archives = Mock(return_value=[])
            
            results = hook.search_all_sources('test query')
            
            assert isinstance(results, dict)
            assert 'statutes' in results
            assert 'state_statutes' in results
            assert 'regulations' in results
            assert 'administrative_rules' in results
            assert 'case_law' in results
            assert 'web_archives' in results
            assert 'search_diagnostics' in results
            assert 'source_availability' in results['search_diagnostics']
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_filters_by_authority_families(self):
        """Explicit federal discovery admits only requested bounded families."""
        from mediator.legal_authority_hooks import LegalAuthoritySearchHook
        mediator = Mock()
        hook = LegalAuthoritySearchHook(mediator)
        statute = {'source_family':'us_code','citation':'42 U.S.C. § 1983',
            'uri':'https://uscode.house.gov/example','applicability':'unknown'}
        regulation = {'source_family':'federal_register','citation':'89 FR 100',
            'uri':'https://www.federalregister.gov/example','applicability':'unknown'}
        def lookup(**options):
            row = statute if options['source_family']=='us_code' else regulation
            return {'status':'success','results':[row],'applicability':'unknown'}
        hook.lookup_bounded_corpus = Mock(side_effect=lookup)
        hook.search_case_law = Mock(side_effect=AssertionError('unrequested case search'))
        hook.search_web_archives = Mock(side_effect=AssertionError('unrequested archive search'))
        result = hook.search_all_sources('test query',jurisdiction='federal',
            authority_families=['statute','regulation'])
        assert [c.kwargs['source_family'] for c in hook.lookup_bounded_corpus.call_args_list] == ['us_code','federal_register']
        assert all(c.kwargs['retrieval_mode']=='offline' and c.kwargs['jurisdiction']=='federal'
            for c in hook.lookup_bounded_corpus.call_args_list)
        assert result['statutes']==[statute] and result['regulations']==[regulation]
        assert result['state_statutes']==result['administrative_rules']==result['case_law']==result['web_archives']==[]
        hook.search_case_law.assert_not_called();hook.search_web_archives.assert_not_called()
        assert result['search_diagnostics']['statutes']['status']=='success'
        assert result['statutes'][0]['applicability']==result['regulations'][0]['applicability']=='unknown'

    def test_search_state_laws_logs_hf_coverage_warning_when_dataset_has_no_state_rows(self):
        """Historical warning case: use current bounded capability, never stale globals."""
        from mediator.legal_authority_hooks import LegalAuthoritySearchHook
        mediator=Mock();hook=LegalAuthoritySearchHook(mediator);mediator.log.reset_mock()
        envelope={'status':'unavailable','capability':'offline_asset_missing','error_code':'offline_asset_missing',
            'retrieval_mode':'offline','results':[],'result_count':0,'source_family':'state_statute','applicability':'unknown'}
        with patch('mediator.legal_authority_hooks.lookup_bounded_legal_corpus',return_value=envelope) as bounded:
            with patch('mediator.legal_authority_hooks.get_last_legal_search_diagnostic',
                    side_effect=AssertionError('stale global diagnostic consulted')) as stale:
                result=hook.search_state_laws('tenant retaliation',state='OR',max_results=5,
                    allow_live_scrape_fallback=False)
                diagnostic=hook._collect_search_diagnostics(query='tenant retaliation',state='OR')
        assert result==[];stale.assert_not_called()
        bounded.assert_called_once_with(source_family='state_statute',query='tenant retaliation',
            max_results=5,state='OR',retrieval_mode='offline')
        assert diagnostic['state_statutes']['status']=='unavailable'
        assert diagnostic['state_statutes']['error_code']=='offline_asset_missing'
        assert diagnostic['state_statutes']['applicability']=='unknown'
        assert diagnostic['state_statutes']['warning_code']=='offline_asset_missing'
        assert any(c.args and c.args[0]=='legal_corpus_candidate_lookup'
            and c.kwargs.get('error_code')=='offline_asset_missing' for c in mediator.log.call_args_list)
        assert not any(c.kwargs.get('warning_code')=='hf_state_rows_missing' for c in mediator.log.call_args_list)

    def test_search_federal_register_uses_ecfr_fallback(self):
        """Historical fallback case: missing bounded assets cannot initiate eCFR or HTTP."""
        from mediator.legal_authority_hooks import LegalAuthoritySearchHook
        hook=LegalAuthoritySearchHook(Mock())
        hook._search_ecfr_fallback=Mock(side_effect=AssertionError('implicit eCFR fallback'))
        with patch('mediator.legal_authority_hooks.requests.get',side_effect=AssertionError('implicit HTTP')) as http:
            result=hook.search_federal_register('24 CFR 982.555 housing voucher hearing',max_results=5,
                jurisdiction='federal')
        assert result==[];http.assert_not_called();hook._search_ecfr_fallback.assert_not_called()
        diagnostic=hook._collect_search_diagnostics(query='24 CFR 982.555 housing voucher hearing',state=None)
        assert diagnostic['regulations']['status']=='unavailable'
        assert diagnostic['regulations']['error_code']=='offline_asset_missing'
        assert diagnostic['regulations']['applicability']=='unknown'

    def test_search_case_law_uses_courtlistener_fallback(self):
        """Case-law search should fall back to CourtListener when RECAP is unavailable."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            hook = LegalAuthoritySearchHook(mock_mediator)
            courtlistener_payload = {
                'results': [
                    {
                        'absolute_url': '/opinion/12345/johnson-v-philadelphia-housing-authority/',
                        'caseName': 'Johnson v. Philadelphia Housing Authority',
                        'court': 'District Court, E.D. Pennsylvania',
                        'court_citation_string': 'E.D. Pa.',
                        'dateFiled': '2024-01-10',
                        'meta': {'score': {'bm25': 42.5}},
                    }
                ]
            }
            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_response.json = Mock(return_value=courtlistener_payload)

            with patch('mediator.legal_authority_hooks.search_recap_documents', new=None):
                with patch('mediator.legal_authority_hooks.requests.get', return_value=mock_response):
                    results = hook.search_case_law('housing authority informal hearing', jurisdiction='pa', max_results=5)

            assert results
            assert results[0]['source'] == 'courtlistener'
            assert results[0]['title'] == 'Johnson v. Philadelphia Housing Authority'
            assert results[0]['url'].startswith('https://www.courtlistener.com/opinion/12345/')
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_all_sources_adds_oregon_statute_fallback(self):
        """Historical fallback case: explicit Oregon rows stay in the bounded state bucket."""
        from mediator.legal_authority_hooks import LegalAuthoritySearchHook
        hook=LegalAuthoritySearchHook(Mock())
        row={'source_family':'state_statute','citation':'ORS 659A.145',
            'uri':'https://www.oregonlegislature.gov/example','jurisdiction':'OR','applicability':'unknown'}
        hook.lookup_bounded_corpus=Mock(return_value={'status':'success','results':[row],'applicability':'unknown'})
        hook._search_oregon_statutes_fallback=Mock(side_effect=AssertionError('implicit live fallback'))
        result=hook.search_all_sources('Oregon housing authority reasonable accommodation',
            jurisdiction='or',authority_families=['statute'])
        assert result['statutes']==[] and result['state_statutes']==[row]
        hook.lookup_bounded_corpus.assert_called_once_with(source_family='state_statute',
            query='Oregon housing authority reasonable accommodation',max_results=5,retrieval_mode='offline',jurisdiction='OR',state='OR')
        hook._search_oregon_statutes_fallback.assert_not_called()
        assert result['state_statutes'][0]['applicability']=='unknown'

    def test_search_us_code_uses_federal_statute_fallback(self):
        """Historical fallback case: explicit cached source provenance needs no HTTP."""
        import hashlib
        from mediator.legal_authority_hooks import LegalAuthoritySearchHook
        hook=LegalAuthoritySearchHook(Mock())
        hook._search_federal_statutes_fallback=Mock(side_effect=AssertionError('implicit federal fallback'))
        query='fair housing reasonable accommodation voucher'
        passage='Synthetic public statutory passage concerning reasonable accommodation.'
        row={'citation':'42 U.S.C. § 3604(f)(3)(B)','uri':'https://uscode.house.gov/example',
            'text':passage,'jurisdiction':'federal','corpus_id':'synthetic-uscode'}
        with patch('mediator.legal_authority_hooks.requests.get',side_effect=AssertionError('implicit HTTP')) as http:
            result=hook.search_us_code(query,max_results=5,retrieval_mode='cache',jurisdiction='federal',
                offline_cache={'us_code|'+query+'|federal|':[row]})
        http.assert_not_called();hook._search_federal_statutes_fallback.assert_not_called()
        assert len(result)==1 and result[0]['source_family']=='us_code'
        assert result[0]['citation']=='42 U.S.C. § 3604(f)(3)(B)'
        assert result[0]['uri']==row['uri'] and result[0]['source_passage']==passage
        assert result[0]['content_hash_scope']=='source_passage'
        assert result[0]['content_hash']=='sha256:'+hashlib.sha256(passage.encode('utf-8')).hexdigest()
        assert result[0]['jurisdiction']=='federal' and result[0]['jurisdiction_status']=='source'
        assert result[0]['effective_date']is None and result[0]['effective_date_status']=='unknown'
        assert result[0]['corpus_id']=='synthetic-uscode' and result[0]['applicability']=='unknown'

    def test_search_web_archives_uses_agency_guidance_fallback(self):
        """Web-archive search should fall back to curated HUD guidance when archive search is unavailable."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            hook = LegalAuthoritySearchHook(mock_mediator)
            hook.web_search = None

            results = hook.search_web_archives(
                'hud.gov',
                query='housing choice voucher reasonable accommodation informal hearing',
                max_results=5,
            )

            assert results
            assert results[0]['source'] == 'hud_guidance_fallback'
            assert any('Guidebook' in row['title'] or 'Reasonable Accommodations' in row['title'] for row in results)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_search_web_archives_returns_clackamas_guidance_fallback(self):
        """State/local authority enrichment should be able to return Clackamas guidance pages."""
        try:
            from mediator.legal_authority_hooks import LegalAuthoritySearchHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.query_backend = Mock(return_value="test query")

            hook = LegalAuthoritySearchHook(mock_mediator)
            hook.web_search = None

            results = hook.search_web_archives(
                'clackamas.us',
                query='Clackamas housing authority administrative plan reasonable accommodation voucher',
                max_results=5,
            )

            assert results
            assert results[0]['source'] == 'clackamas_guidance_fallback'
            assert any('Clackamas' in row['title'] for row in results)
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
                time_window={
                    'time_window_start': '2024-01-01',
                    'time_window_end': '2024-12-31',
                    'query_terms': ['temporal', 'before'],
                },
                defense_themes=['temporal_prerequisite'],
                authority_families=['case_law', 'statute', 'regulation'],
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
            assert all(program['time_window_start'] == '2024-01-01' for program in programs)
            assert all(program['time_window_end'] == '2024-12-31' for program in programs)
            assert all(program['metadata']['time_window_terms'] == ['temporal', 'before'] for program in programs)
            assert all(program['metadata']['defense_themes'] == ['temporal_prerequisite'] for program in programs)
            assert all(set(program['authority_families']).issubset({'case_law', 'statute', 'regulation'}) for program in programs)
            assert next(
                program for program in programs
                if program['program_type'] == 'procedural_search'
            )['metadata']['defense_theme'] == 'procedural_prerequisite'
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
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T18:00:00+00:00',
                    'confirmation_note': 'ready for authority record persistence',
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
                authority = hook.get_authority_by_id(record_id)
                
                assert record_id > 0
                assert authority['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for authority record persistence',
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
                assert authority['provenance']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for authority record persistence',
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
                        'search_programs': [
                            {
                                'program_id': 'legal_search_program:dup',
                                'program_type': 'treatment_check_search',
                                'claim_type': 'employment retaliation',
                                'authority_intent': 'confirm_good_law',
                                'query_text': 'Smith v. Jones later treatment',
                                'claim_element_id': 'employment_retaliation:3',
                                'claim_element_text': 'Causal connection',
                                'authority_families': ['case_law'],
                                'search_terms': ['later treatment'],
                            }
                        ],
                        'treatment_records': [
                            {
                                'treatment_type': 'questioned',
                                'treated_by_authority_id': 'authority:later-case',
                                'treated_by_citation': 'Jones v. Smith, 456 F.4th 789',
                                'treatment_source': 'later_case_search',
                                'treatment_confidence': 0.82,
                                'treatment_date': '2025-02-14',
                            }
                        ],
                    },
                    user_id='testuser',
                    complaint_id='complaint-1',
                    claim_type='employment retaliation',
                )

                authority = hook.get_authority_by_id(record_id)
                treatments = hook.get_authority_treatments(record_id)
                search_programs = hook.get_authority_search_programs(record_id)

                assert reused_record_id == record_id
                assert authority is not None
                assert authority['search_program_summary']['record_count'] == 1
                assert search_programs[0]['program_type'] == 'treatment_check_search'
                assert search_programs[0]['authority_intent'] == 'confirm_good_law'
                assert authority['treatment_summary']['record_count'] == 1
                assert authority['citation_history_summary']['record_count'] == 1
                assert authority['citation_history_summary']['related_authority_ids'] == ['authority:later-case']
                assert authority['citation_history_summary']['related_citations'] == ['Jones v. Smith, 456 F.4th 789']
                assert authority['citation_history_summary']['latest_treatment_date'] == '2025-02-14'
                assert treatments[0]['treatment_type'] == 'questioned'
                assert treatments[0]['treated_authority_id'] == 'authority:later-case'
                assert treatments[0]['target_authority_id'] == 'authority:later-case'
                assert treatments[0]['treated_by_citation'] == 'Jones v. Smith, 456 F.4th 789'
                assert treatments[0]['target_citation'] == 'Jones v. Smith, 456 F.4th 789'
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_duplicate_can_persist_new_rule_candidates(self):
        """Test duplicate authority upserts can attach later parsed rule candidates."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                hook = LegalAuthorityStorageHook(mock_mediator, db_path=db_path)

                authority_data = {
                    'type': 'regulation',
                    'source': 'federal_register',
                    'citation': '91 Fed. Reg. 67890',
                    'title': 'Workplace recordkeeping',
                    'content': 'Short text.',
                    'claim_element_id': 'employment:1',
                    'claim_element': 'Protected activity',
                }

                record_id = hook.add_authority(
                    authority_data,
                    user_id='testuser',
                    complaint_id='complaint-1',
                    claim_type='employment',
                )
                assert hook.get_authority_rule_candidates(record_id) == []

                richer_authority = {
                    **authority_data,
                    'content': (
                        'Employers must preserve complaint records. '
                        'Actions must be filed within 180 days of notice.'
                    ),
                }
                reused_record_id = hook.add_authority(
                    richer_authority,
                    user_id='testuser',
                    complaint_id='complaint-1',
                    claim_type='employment',
                )
                repeated_record_id = hook.add_authority(
                    richer_authority,
                    user_id='testuser',
                    complaint_id='complaint-1',
                    claim_type='employment',
                )

                authority = hook.get_authority_by_id(record_id)
                rule_candidates = hook.get_authority_rule_candidates(record_id)

                assert reused_record_id == record_id
                assert repeated_record_id == record_id
                assert authority is not None
                assert authority['rule_candidate_summary']['record_count'] == len(rule_candidates)
                assert authority['rule_candidate_summary']['by_type']['procedural_prerequisite'] >= 1
                assert len(rule_candidates) == 2
                assert all(candidate['claim_element_id'] == 'employment:1' for candidate in rule_candidates)
                assert all(candidate['claim_element_text'] == 'Protected activity' for candidate in rule_candidates)
                assert len({candidate['rule_id'] for candidate in rule_candidates}) == len(rule_candidates)
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_get_authorities_by_claim(self, monkeypatch):
        """Test retrieving authorities by claim type"""
        fixture_calls = _install_legal_passage_graph_fixture(monkeypatch)
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
                assert fixture_calls  # This storage test uses its explicit legal-passage input.
                
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

    def test_add_authority_persists_fact_rows(self, monkeypatch):
        """Test storing an authority also persists extracted fact rows."""
        fixture_calls = _install_legal_passage_graph_fixture(monkeypatch)
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
                assert fixture_calls  # This storage test uses its explicit legal-passage input.
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

    def test_add_authority_persists_parse_summary_and_chunks(self, monkeypatch):
        """Test authority parsing stores parse summary fields and chunk rows."""
        fixture_calls = _install_legal_passage_graph_fixture(monkeypatch)
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb

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
                    'confirmed_at': '2026-03-17T18:00:00+00:00',
                    'confirmation_note': 'ready for authority child artifact persistence',
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
                assert fixture_calls  # This storage test uses its explicit legal-passage input.
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
                assert authority['parse_metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for authority child artifact persistence',
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
                assert authority['provenance']['metadata']['artifact_family'] == 'legal_authority_text'
                assert authority['provenance']['metadata']['content_origin'] == 'authority_full_text'
                assert authority['provenance']['metadata']['text_available'] is True
                assert authority['parse_metadata']['transform_lineage']['source'] == 'legal_authority'
                assert authority['parse_metadata']['transform_lineage']['content_origin'] == 'authority_full_text'
                assert len(chunks) >= 1
                assert chunks[0]['chunk_id'] == 'chunk-0'
                assert chunks[0]['metadata']['source_span']['char_start'] == chunks[0]['start']
                assert chunks[0]['metadata']['source_span']['char_end'] == chunks[0]['end']
                assert chunks[0]['metadata']['page_start'] == 1
                assert chunks[0]['metadata']['page_end'] == 1
                assert chunks[0]['metadata']['section_label'] == ''
                assert chunks[0]['metadata']['source'] == 'legal_authority'
                assert chunks[0]['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for authority child artifact persistence',
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
                assert facts[0]['chunk_id'] == 'chunk-0'
                assert facts[0]['chunk_index'] == 0
                assert facts[0]['source_passage']['chunk_id'] == 'chunk-0'
                assert facts[0]['source_passage']['start'] >= 0
                assert facts[0]['source_passage']['end'] > facts[0]['source_passage']['start']
                assert facts[0]['source_passage']['text']
                assert facts[0]['source_passage']['text'] in {
                    facts[0]['text'],
                    chunks[facts[0]['chunk_index']]['text'].strip(),
                }
                assert facts[0]['metadata']['source_passage']['chunk_id'] == 'chunk-0'
                assert facts[0]['metadata']['source_passage']['text'] == facts[0]['source_passage']['text']
                assert facts[0]['metadata']['parse_lineage']['source'] == 'legal_authority'
                conn = duckdb.connect(db_path)
                durable_row = conn.execute(
                    """
                    SELECT source_family, source_record_id, source_ref, record_scope,
                           artifact_family, corpus_family, content_origin, parse_source,
                           input_format, quality_tier, quality_score, chunk_id, chunk_index,
                           CAST(source_passage AS VARCHAR)
                    FROM legal_authority_facts
                    WHERE authority_id = ?
                    ORDER BY fact_id ASC
                    LIMIT 1
                    """,
                    [record_id],
                ).fetchone()
                conn.close()
                assert durable_row[0] == 'legal_authority'
                assert durable_row[1] == record_id
                assert durable_row[2] == f'authority:{record_id}'
                assert '"text"' in durable_row[13]
                assert durable_row[3] == 'legal_authority'
                assert durable_row[4] == 'legal_authority_text'
                assert durable_row[5] == 'legal_authority'
                assert durable_row[6] == 'authority_full_text'
                assert durable_row[7] == 'legal_authority'
                assert durable_row[8] == 'text'
                assert durable_row[9] == 'high'
                assert durable_row[10] > 0.0
                assert durable_row[11] == 'chunk-0'
                assert durable_row[12] == 0
                assert 'chunk-0' in durable_row[13]
                assert facts[0]['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for authority child artifact persistence',
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
                assert facts[0]['provenance']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for authority child artifact persistence',
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
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_get_authority_facts_reads_legacy_json_only_fact_rows(self):
        """Test old legal_authority_facts rows still expose the flattened corpus contract."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb

            fd, db_path = tempfile.mkstemp(suffix='.duckdb')
            os.close(fd)
            os.unlink(db_path)

            try:
                conn = duckdb.connect(db_path)
                conn.execute(
                    """
                    CREATE TABLE legal_authority_facts (
                        authority_id BIGINT,
                        fact_id VARCHAR,
                        fact_text TEXT,
                        source_authority_id VARCHAR,
                        confidence FLOAT,
                        metadata JSON,
                        provenance JSON
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO legal_authority_facts
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        13,
                        'fact:authority-legacy',
                        'Legacy authority fact',
                        'authority:13',
                        0.81,
                        json.dumps({
                            'parse_lineage': {
                                'source': 'legal_authority',
                                'input_format': 'text',
                                'quality_tier': 'high',
                                'quality_score': 95.0,
                                'content_origin': 'authority_full_text',
                                'artifact_family': 'legal_authority_text',
                                'corpus_family': 'legal_authority',
                            },
                            'chunk_id': 'authority-chunk-0',
                            'chunk_index': 0,
                            'source_passage': {
                                'chunk_id': 'authority-chunk-0',
                                'chunk_index': 0,
                            },
                        }),
                        json.dumps({'metadata': {}}),
                    ],
                )
                conn.close()

                mock_mediator = Mock()
                mock_mediator.log = Mock()
                hook = LegalAuthorityStorageHook.__new__(LegalAuthorityStorageHook)
                hook.mediator = mock_mediator
                hook.db_path = db_path

                facts = hook.get_authority_facts(13)

                assert len(facts) == 1
                assert facts[0]['source_authority_id'] == 'authority:13'
                assert facts[0]['source_family'] == 'legal_authority'
                assert facts[0]['source_record_id'] == 13
                assert facts[0]['source_ref'] == 'authority:13'
                assert facts[0]['record_scope'] == 'legal_authority'
                assert facts[0]['artifact_family'] == 'legal_authority_text'
                assert facts[0]['corpus_family'] == 'legal_authority'
                assert facts[0]['content_origin'] == 'authority_full_text'
                assert facts[0]['parse_source'] == 'legal_authority'
                assert facts[0]['input_format'] == 'text'
                assert facts[0]['quality_tier'] == 'high'
                assert facts[0]['chunk_id'] == 'authority-chunk-0'
                assert facts[0]['source_passage']['chunk_id'] == 'authority-chunk-0'
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_authority_preserves_html_parse_contract(self, monkeypatch):
        """Test authority HTML content is normalized through the shared parse contract."""
        fixture_calls = _install_legal_passage_graph_fixture(monkeypatch)
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb

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
                    'confirmed_at': '2026-03-17T18:00:00+00:00',
                    'confirmation_note': 'ready for authority child artifact persistence',
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
                assert fixture_calls  # This storage test uses its explicit legal-passage input.
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
                assert facts[0]['source_passage']['text']
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

    def test_add_authority_persists_graph_metadata(self, monkeypatch):
        """Test authority storage persists graph summary fields and graph rows."""
        try:
            from mediator.legal_authority_hooks import LegalAuthorityStorageHook
            import duckdb
            from integrations.ipfs_datasets import graphs
            private_extractor = Mock(side_effect=AssertionError('legal authority must not enter private extraction'))
            monkeypatch.setattr(graphs, '_run_owned_private_extractor', private_extractor)

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

                private_extractor.assert_not_called()
                assert authority['graph_metadata']['legal_passage'] is True
                assert authority['graph_metadata']['source_family'] == 'legal_authority'
                assert authority['graph_metadata']['record_scope'] == 'legal_authority'
                assert authority['graph_metadata']['artifact_family'] == 'legal_authority_text'
                assert authority['graph_metadata']['private_extraction']['diagnostic'] == 'legal_passage_not_private_extraction'
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
                assert any(
                    entity['attributes'].get('intake_summary_handoff') == {
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
                    for entity in graph['entities']
                )
                assert all(
                    rel['attributes'].get('intake_summary_handoff') == {
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
                    for rel in graph['relationships']
                )
                legal_nodes = [entity for entity in graph['entities'] if entity['type'] == 'authority_source']
                assert legal_nodes
                assert all(entity['id'].startswith('authority_source:') for entity in legal_nodes)
                assert all(entity['attributes']['about_complainant'] is False for entity in legal_nodes)
                assert not any(entity['type'] == 'fact' for entity in graph['entities'])
                assert all(rel['relation_type'] == 'cites_authority' for rel in graph['relationships'])
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
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T18:00:00+00:00',
                    'confirmation_note': 'ready for authority child artifact persistence',
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
                            'treated_by_authority_id': 'authority:later-case',
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
                search_programs = hook.get_authority_search_programs(record_id)

                assert record_id > 0
                assert authority is not None
                assert authority['metadata']['search_programs'][0]['program_type'] == 'fact_pattern_search'
                assert authority['metadata']['search_programs'][0]['claim_element_id'] == 'employment_retaliation:3'
                assert len(search_programs) == 1
                assert search_programs[0]['program_id'] == 'legal_search_program:test'
                assert search_programs[0]['program_type'] == 'fact_pattern_search'
                assert search_programs[0]['claim_type'] == 'employment retaliation'
                assert search_programs[0]['claim_element_id'] == 'employment_retaliation:3'
                assert search_programs[0]['metadata']['authority_id'] == record_id
                assert search_programs[0]['metadata']['authority_citation'] == 'Smith v. Jones, 123 F.3d 456'
                assert authority['search_program_summary']['record_count'] == 1
                assert authority['search_program_summary']['by_type']['fact_pattern_search'] == 1
                assert authority['search_program_summary']['by_intent']['support'] == 1
                assert authority['search_program_summary']['claim_element_count'] == 1
                assert len(authority['treatment_records']) == 1
                assert len(authority['authority_treatment_edges']) == 1
                assert authority['treatment_summary']['record_count'] == 1
                assert authority['treatment_summary']['by_type']['questioned'] == 1
                assert authority['citation_history_summary']['related_authority_ids'] == ['authority:later-case']
                assert authority['citation_history_summary']['related_citation_count'] == 1
                assert authority['authority_treatment_edges'][0]['relation_type'] == 'questioned'
                assert authority['authority_treatment_edges'][0]['source_authority_id'] == 'authority:later-case'
                assert authority['authority_treatment_edges'][0]['target_authority_id'] == f"authority:{authority['id']}"
                assert authority['authority_treatment_edges'][0]['source_citation'] == 'Jones v. Smith, 456 F.4th 789'
                assert authority['authority_treatment_edges'][0]['target_citation'] == 'Smith v. Jones, 123 F.3d 456'
                assert authority['authority_treatment_edges'][0]['confidence'] == pytest.approx(0.82)
                assert treatments[0]['treatment_type'] == 'questioned'
                assert treatments[0]['treated_authority_id'] == 'authority:later-case'
                assert treatments[0]['treated_by_citation'] == 'Jones v. Smith, 456 F.4th 789'
                assert treatments[0]['treatment_source'] == 'later_case_search'
                assert treatments[0]['treatment_confidence'] == pytest.approx(0.82)
                assert treatments[0]['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for authority child artifact persistence',
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
                assert treatments[0]['provenance']['metadata']['intake_summary_handoff'] == {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T18:00:00+00:00',
                        'confirmation_note': 'ready for authority child artifact persistence',
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
            mock_mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T18:00:00+00:00',
                    'confirmation_note': 'ready for authority child artifact persistence',
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
                assert all(candidate['source_passage']['text'] == candidate['rule_text'] for candidate in rule_candidates)
                assert all(candidate['metadata']['source_passage']['text'] == candidate['rule_text'] for candidate in rule_candidates)
                assert all(candidate['source_passage']['chunk_id'] == candidate['metadata']['chunk_id'] for candidate in rule_candidates)
                assert all(candidate['source_passage']['start'] == candidate['metadata']['source_span']['start'] for candidate in rule_candidates)
                assert all(candidate['source_passage']['end'] == candidate['metadata']['source_span']['end'] for candidate in rule_candidates)
                assert all(candidate['parse_lineage']['source'] == 'legal_authority' for candidate in rule_candidates)
                assert all(candidate['parse_lineage']['record_scope'] == 'legal_authority' for candidate in rule_candidates)
                assert all(candidate['parse_lineage']['source_ref'] == f'authority:{record_id}' for candidate in rule_candidates)
                assert all(candidate['grounded_rule']['premise_type'] == 'legal_rule' for candidate in rule_candidates)
                assert any(
                    candidate['grounded_rule']['deontic_operator'] == 'obligation'
                    for candidate in rule_candidates
                )
                assert authority['rule_candidate_summary']['by_deontic_operator']['obligation'] >= 1
                assert authority['rule_candidate_summary']['by_grounding_status']['grounded'] >= 1
                assert all(
                    candidate['metadata']['intake_summary_handoff'] == {
                        'current_phase': 'intake',
                        'ready_to_advance': True,
                        'complainant_summary_confirmation': {
                            'status': 'confirmed',
                            'confirmed': True,
                            'confirmed_at': '2026-03-17T18:00:00+00:00',
                            'confirmation_note': 'ready for authority child artifact persistence',
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
                    for candidate in rule_candidates
                )
                assert all(
                    candidate['provenance']['metadata']['intake_summary_handoff'] == {
                        'current_phase': 'intake',
                        'ready_to_advance': True,
                        'complainant_summary_confirmation': {
                            'status': 'confirmed',
                            'confirmed': True,
                            'confirmed_at': '2026-03-17T18:00:00+00:00',
                            'confirmation_note': 'ready for authority child artifact persistence',
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
                    for candidate in rule_candidates
                )
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_get_statistics(self, monkeypatch):
        """Test getting authority statistics"""
        fixture_calls = _install_legal_passage_graph_fixture(monkeypatch)
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
                        'title': f'Test Title {i}',
                        'content': f'Synthetic legal authority passage {i}.'
                    }
                    hook.add_authority(authority_data, 'testuser')
                
                assert len(fixture_calls) == 3
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
    def test_mediator_search_and_store_authorities(self, monkeypatch):
        """Test searching and storing legal authorities through mediator"""
        fixture_calls = _install_legal_passage_graph_fixture(monkeypatch)
        try:
            from mediator import Mediator
            from complaint_phases import ComplaintPhase
            
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
                mediator.phase_manager.update_phase_data(
                    ComplaintPhase.INTAKE,
                    'intake_case_file',
                    {
                        'candidate_claims': [{'claim_type': 'civil rights'}],
                        'canonical_facts': [{'fact_id': 'fact_001'}],
                        'proof_leads': [{'lead_id': 'lead_001'}],
                        'complainant_summary_confirmation': {
                            'status': 'confirmed',
                            'confirmed': True,
                            'confirmed_at': '2026-03-17T18:00:00+00:00',
                            'confirmation_note': 'ready for authority research',
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
                mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
                mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
                mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])
                mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_gap_types', [])
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
                            'content': 'Test content about protected activity',
                            'source': 'us_code',
                            'claim_element': 'Protected activity',
                        }
                    ],
                    'state_statutes': [
                        {
                            'citation': 'ORS 90.385',
                            'title': 'Retaliatory conduct by landlord',
                            'content': 'A landlord may not retaliate against a tenant.',
                            'source': 'state_law',
                            'claim_element': 'Protected activity',
                        }
                    ],
                    'regulations': [],
                    'administrative_rules': [
                        {
                            'citation': 'OAR 839-003-0001',
                            'title': 'Civil rights administrative enforcement',
                            'content': 'Administrative enforcement guidance for civil rights claims.',
                            'source': 'state_admin_rules',
                            'claim_element': 'Protected activity',
                        }
                    ],
                    'case_law': [],
                    'web_archives': [],
                    'search_diagnostics': {
                        'source_availability': {
                            'federal_statutes': True,
                            'federal_regulations': True,
                            'case_law': True,
                            'state_statutes': True,
                            'administrative_rules': True,
                        }
                    },
                })
                
                # Search
                results = mediator.search_legal_authorities('civil rights', search_all=True)
                assert 'statutes' in results
                assert 'state_statutes' in results
                assert 'administrative_rules' in results
                assert 'search_diagnostics' in results
                assert 'search_warning_summary' in results
                assert results['search_warning_summary'] == []
                
                # Store
                stored = mediator.store_legal_authorities(results, claim_type='civil rights')
                assert fixture_calls  # This storage test uses its explicit legal-passage input.
                assert 'statutes' in stored
                assert 'state_statutes' in stored
                assert 'administrative_rules' in stored
                assert stored['total_records'] == 3
                assert stored['total_new'] == 3
                assert stored['total_reused'] == 0
                assert stored['total_support_links_added'] == 3
                assert stored['total_support_links_reused'] == 0

                stored_duplicate = mediator.store_legal_authorities(results, claim_type='civil rights')
                assert stored_duplicate['statutes'] == 1
                assert stored_duplicate['state_statutes'] == 1
                assert stored_duplicate['administrative_rules'] == 1
                assert stored_duplicate['statutes_new'] == 0
                assert stored_duplicate['state_statutes_new'] == 0
                assert stored_duplicate['administrative_rules_new'] == 0
                assert stored_duplicate['statutes_reused'] == 1
                assert stored_duplicate['state_statutes_reused'] == 1
                assert stored_duplicate['administrative_rules_reused'] == 1
                assert stored_duplicate['statutes_support_links_added'] == 0
                assert stored_duplicate['state_statutes_support_links_added'] == 0
                assert stored_duplicate['administrative_rules_support_links_added'] == 0
                assert stored_duplicate['statutes_support_links_reused'] == 1
                assert stored_duplicate['state_statutes_support_links_reused'] == 1
                assert stored_duplicate['administrative_rules_support_links_reused'] == 1
                assert stored_duplicate['total_records'] == 3
                assert stored_duplicate['total_new'] == 0
                assert stored_duplicate['total_reused'] == 3

                support_links = mediator.get_claim_support(claim_type='civil rights')
                assert len(support_links) > 0
                assert any(link['claim_element_id'] == 'civil_rights:1' for link in support_links)

                support_summary = mediator.summarize_claim_support(claim_type='civil rights')
                assert support_summary['claims']['civil rights']['support_by_kind']['authority'] > 0
                assert support_summary['claims']['civil rights']['covered_elements'] == 1
                assert support_summary['claims']['civil rights']['total_facts'] >= 1
                authority_citations = {
                    link['record_summary']['citation']
                    for link in support_summary['claims']['civil rights']['elements'][0]['links']
                    if link.get('record_summary')
                }
                assert '42 U.S.C. § 1983' in authority_citations
                assert 'ORS 90.385' in authority_citations
                assert 'OAR 839-003-0001' in authority_citations
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
                coverage_citations = {
                    link['record_summary']['citation']
                    for link in coverage_element['links_by_kind']['authority']
                    if link.get('record_summary')
                }
                assert '42 U.S.C. § 1983' in coverage_citations
                assert 'ORS 90.385' in coverage_citations
                assert 'OAR 839-003-0001' in coverage_citations
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
                assert auto_results['intake_summary_handoff']['current_phase'] == ComplaintPhase.INTAKE.value
                assert auto_results['intake_summary_handoff']['ready_to_advance'] == mediator.get_three_phase_status()['intake_readiness']['ready_to_advance']
                assert auto_results['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
                assert 'civil rights' in auto_results['authorities_diagnostics']
                assert 'civil rights' in auto_results['authorities_warning_summary']
                assert auto_results['authorities_warning_summary']['civil rights'] == []
                assert auto_results['authorities_stored']['civil rights']['total_records'] == 3
                assert auto_results['authorities_stored']['civil rights']['total_new'] == 0
                assert auto_results['authorities_stored']['civil rights']['total_reused'] == 3
                assert auto_results['authorities_stored']['civil rights']['total_support_links_added'] == 0
                assert auto_results['authorities_stored']['civil rights']['total_support_links_reused'] == 3
                assert auto_results['claim_coverage_matrix']['civil rights']['status_counts']['partially_supported'] == 1
                assert auto_results['claim_coverage_matrix']['civil rights']['status_counts']['missing'] == 1
                assert auto_results['claim_coverage_matrix_snapshots']['civil rights']['snapshot_id'] > 0
                assert auto_results['claim_coverage_matrix_snapshots']['civil rights']['is_stale'] is False
                assert auto_results['claim_coverage_matrix_snapshot_summary']['civil rights']['total_snapshot_count'] == 1
                assert auto_results['claim_coverage_matrix_snapshot_summary']['civil rights']['fresh_snapshot_count'] == 1
                assert auto_results['claim_coverage_matrix_snapshot_summary']['civil rights']['snapshot_kinds'] == ['coverage_matrix']
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
                assert auto_results_with_execution['intake_summary_handoff']['current_phase'] == ComplaintPhase.INTAKE.value
                assert auto_results_with_execution['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
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
