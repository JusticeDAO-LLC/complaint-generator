"""Unit tests for claim support persistence hooks."""

import json
import os
import tempfile
from unittest.mock import Mock, patch

import pytest

duckdb = pytest.importorskip("duckdb")

from complaint_analysis.temporal_rule_profiles import evaluate_temporal_rule_profile


pytestmark = pytest.mark.no_auto_network


def _confirmed_intake_status(*, note: str) -> dict:
    return {
        'current_phase': 'intake',
        'intake_readiness': {
            'ready_to_advance': True,
        },
        'complainant_summary_confirmation': {
            'status': 'confirmed',
            'confirmed': True,
            'confirmed_at': '2026-03-17T19:00:00+00:00',
            'confirmation_note': note,
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


class TestClaimSupportHook:
    def test_get_recent_follow_up_execution_exposes_adaptive_retry_metadata(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            record_id = hook.record_follow_up_execution(
                user_id='testuser',
                claim_type='employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                support_kind='authority',
                query_text='"employment" "Protected activity" statute',
                status='executed',
                metadata={
                    'execution_mode': 'review_and_retrieve',
                    'validation_status': 'incomplete',
                    'follow_up_focus': 'reasoning_gap_closure',
                    'query_strategy': 'standard_gap_targeted',
                    'adaptive_retry_applied': True,
                    'adaptive_retry_reason': 'repeated_zero_result_reasoning_gap',
                    'adaptive_query_strategy': 'standard_gap_targeted',
                    'adaptive_priority_penalty': 1,
                    'result_count': 0,
                    'stored_result_count': 0,
                    'zero_result': True,
                },
            )

            history = hook.get_recent_follow_up_execution('testuser', 'employment', limit=5)
            entry = history['claims']['employment'][0]

            assert record_id > 0
            assert entry['execution_id'] == record_id
            assert entry['adaptive_retry_applied'] is True
            assert entry['adaptive_retry_reason'] == 'repeated_zero_result_reasoning_gap'
            assert entry['adaptive_query_strategy'] == 'standard_gap_targeted'
            assert entry['adaptive_priority_penalty'] == 1
            assert entry['result_count'] == 0
            assert entry['stored_result_count'] == 0
            assert entry['zero_result'] is True
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_recent_follow_up_execution_exposes_selected_authority_program_metadata(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.get_three_phase_status = Mock(return_value=_confirmed_intake_status(
            note='ready for follow-up execution persistence',
        ))

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            record_id = hook.record_follow_up_execution(
                user_id='testuser',
                claim_type='employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                support_kind='authority',
                query_text='employment Protected activity element definition statute regulation rule',
                status='executed',
                metadata={
                    'execution_mode': 'retrieve_support',
                    'validation_status': 'incomplete',
                    'follow_up_focus': 'parse_quality_improvement',
                    'query_strategy': 'quality_gap_targeted',
                    'selected_search_program_id': 'legal_search_program:authority-1',
                    'selected_search_program_type': 'element_definition_search',
                    'selected_search_program_bias': 'uncertain',
                    'selected_search_program_rule_bias': 'procedural_prerequisite',
                    'selected_search_program_families': ['statute', 'regulation'],
                },
            )

            history = hook.get_recent_follow_up_execution('testuser', 'employment', limit=5)
            entry = history['claims']['employment'][0]

            assert record_id > 0
            assert history['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T19:00:00+00:00',
                    'confirmation_note': 'ready for follow-up execution persistence',
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
            assert entry['execution_id'] == record_id
            assert entry['selected_search_program_id'] == 'legal_search_program:authority-1'
            assert entry['selected_search_program_type'] == 'element_definition_search'
            assert entry['selected_search_program_bias'] == 'uncertain'
            assert entry['selected_search_program_rule_bias'] == 'procedural_prerequisite'
            assert entry['selected_search_program_families'] == ['statute', 'regulation']
            assert entry['metadata']['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T19:00:00+00:00',
                    'confirmation_note': 'ready for follow-up execution persistence',
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

    def test_claim_support_hook_can_be_imported(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
            assert ClaimSupportHook is not None
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook has import issues: {e}")

    def test_add_and_summarize_support(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            registered = hook.register_claim_requirements(
                'testuser',
                {
                    'employment': [
                        'Protected activity',
                        'Adverse employment action',
                    ]
                },
            )
            first_id = hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence1',
                support_label='Email thread',
                source_table='evidence',
            )
            second_id = hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Civil Rights Act',
                source_table='legal_authorities',
            )

            links = hook.get_support_links('testuser', 'employment')
            summary = hook.summarize_claim_support('testuser', 'employment')

            assert first_id > 0
            assert second_id > 0
            assert len(registered['employment']) == 2
            assert len(links) == 2
            assert summary['claims']['employment']['support_by_kind']['evidence'] == 1
            assert summary['claims']['employment']['support_by_kind']['authority'] == 1
            assert summary['claims']['employment']['total_elements'] == 2
            assert summary['claims']['employment']['covered_elements'] == 1
            assert summary['claims']['employment']['uncovered_elements'] == 1
            assert summary['claims']['employment']['elements'][0]['total_links'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_add_support_link_stamps_confirmed_intake_handoff_metadata(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

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
                'confirmed_at': '2026-03-17T12:00:00+00:00',
                'confirmation_note': 'ready for support linking',
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
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )

            record_id = hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceHandoff',
                support_label='Email thread',
                source_table='evidence',
                metadata={'source': 'unit_test'},
            )

            links = hook.get_support_links('testuser', 'employment')

            assert record_id > 0
            assert len(links) == 1
            assert links[0]['metadata'] == {
                'source': 'unit_test',
                'intake_summary_handoff': {
                    'current_phase': 'intake',
                    'ready_to_advance': True,
                    'complainant_summary_confirmation': {
                        'status': 'confirmed',
                        'confirmed': True,
                        'confirmed_at': '2026-03-17T12:00:00+00:00',
                        'confirmation_note': 'ready for support linking',
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
                },
            }
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_register_claim_requirements_stamps_confirmed_intake_handoff_metadata(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

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
                'confirmed_at': '2026-03-17T20:00:00+00:00',
                'confirmation_note': 'ready for claim requirements persistence',
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
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )

            requirements = hook.get_claim_requirements('testuser', 'employment')

            assert requirements['employment'][0]['metadata']['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T20:00:00+00:00',
                    'confirmation_note': 'ready for claim requirements persistence',
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

    def test_summary_includes_uncovered_requirements_without_links(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'retaliation': ['Protected activity', 'Causal connection']},
            )

            summary = hook.summarize_claim_support('testuser', 'retaliation')

            assert summary['claims']['retaliation']['total_links'] == 0
            assert summary['claims']['retaliation']['total_elements'] == 2
            assert summary['claims']['retaliation']['covered_elements'] == 0
            assert summary['claims']['retaliation']['uncovered_elements'] == 2
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_add_support_link_deduplicates_same_reference(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )

            first_id = hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence1',
                support_label='Email thread',
                source_table='evidence',
            )
            second_id = hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence1',
                support_label='Email thread',
                source_table='evidence',
            )

            links = hook.get_support_links('testuser', 'employment')
            summary = hook.summarize_claim_support('testuser', 'employment')

            assert first_id == second_id
            assert len(links) == 1
            assert summary['claims']['employment']['total_links'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_add_support_link_resolves_matching_element(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {
                    'employment': [
                        'Protected activity',
                        'Adverse employment action',
                    ]
                },
            )

            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                support_kind='evidence',
                support_ref='QmEvidence2',
                support_label='Email showing protected activity complaint',
                source_table='evidence',
                metadata={'keywords': ['protected', 'activity', 'complaint']},
            )

            links = hook.get_support_links('testuser', 'employment')

            assert links[0]['claim_element_id'] == 'employment:1'
            assert links[0]['claim_element_text'] == 'Protected activity'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_element_summary(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity', 'Adverse employment action']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                support_kind='evidence',
                support_ref='QmEvidence3',
                support_label='Protected activity email',
                metadata={'keywords': ['protected', 'activity']},
            )

            summary = hook.get_claim_element_summary(
                'testuser',
                'employment',
                claim_element_text='Protected activity',
            )

            assert summary['element_id'] == 'employment:1'
            assert summary['total_links'] == 1
            assert summary['support_by_kind']['evidence'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_summarize_claim_support_enriches_evidence_links_with_facts(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 12,
            'fact_count': 2,
            'parse_metadata': {
                'content_origin': 'historical_archive_capture',
                'artifact_family': 'archived_web_page',
                'corpus_family': 'web_page',
                'input_format': 'html',
                'quality_tier': 'high',
                'quality_score': 98.0,
                'page_count': 1,
            },
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-12',
                    'created': True,
                    'reused': False,
                    'metadata': {
                        'lineage': {
                            'status': 'available-fallback',
                            'text_length': 64,
                        }
                    },
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {
                'fact_id': 'fact:1',
                'text': 'Employee complained about discrimination.',
                'source_artifact_id': 'QmEvidenceFacts',
                'metadata': {
                    'parse_lineage': {
                        'record_scope': 'evidence',
                        'source_ref': 'QmEvidenceFacts',
                        'source': 'web_document',
                        'input_format': 'html',
                        'quality_tier': 'high',
                        'quality_score': 98.0,
                        'transform_lineage': {
                            'content_origin': 'historical_archive_capture',
                            'artifact_family': 'archived_web_page',
                            'corpus_family': 'web_page',
                        },
                    },
                },
            },
            {'fact_id': 'fact:2', 'text': 'Complaint was sent to HR.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceFacts',
                support_label='HR complaint email',
                source_table='evidence',
            )

            summary = hook.summarize_claim_support('testuser', 'employment')
            element = summary['claims']['employment']['elements'][0]

            assert summary['claims']['employment']['total_facts'] == 2
            assert element['fact_count'] == 2
            assert element['links'][0]['evidence_record_id'] == 12
            assert element['links'][0]['fact_count'] == 2
            assert len(element['links'][0]['facts']) == 2
            assert element['links'][0]['facts'][0]['fact_id'] == 'fact:1'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_facts_collects_enriched_fact_rows(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 12,
            'fact_count': 2,
            'parse_metadata': {
                'source': 'web_document',
                'content_origin': 'historical_archive_capture',
                'artifact_family': 'archived_web_page',
                'corpus_family': 'web_page',
                'input_format': 'html',
                'quality_tier': 'high',
                'quality_score': 98.0,
                'page_count': 1,
            },
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-12',
                    'created': True,
                    'reused': False,
                    'metadata': {
                        'lineage': {
                            'status': 'available-fallback',
                            'text_length': 64,
                        }
                    },
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {
                'fact_id': 'fact:1',
                'text': 'Employee complained about discrimination.',
                'source_artifact_id': 'QmEvidenceFacts',
                'metadata': {
                    'parse_lineage': {
                        'record_scope': 'evidence',
                        'source_ref': 'QmEvidenceFacts',
                        'source': 'web_document',
                        'input_format': 'html',
                        'quality_tier': 'high',
                        'quality_score': 98.0,
                        'transform_lineage': {
                            'content_origin': 'historical_archive_capture',
                            'artifact_family': 'archived_web_page',
                            'corpus_family': 'web_page',
                        },
                    },
                },
            },
            {'fact_id': 'fact:2', 'text': 'Complaint was sent to HR.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceFacts',
                support_label='HR complaint email',
                source_table='evidence',
            )

            facts = hook.get_claim_support_facts(
                'testuser',
                'employment',
                claim_element_text='Protected activity',
            )

            assert len(facts) == 2
            assert facts[0]['claim_type'] == 'employment'
            assert facts[0]['claim_element_text'] == 'Protected activity'
            assert facts[0]['support_kind'] == 'evidence'
            assert facts[0]['evidence_record_id'] == 12
            assert facts[0]['source_family'] == 'evidence'
            assert facts[0]['source_record_id'] == 12
            assert facts[0]['source_ref'] == 'QmEvidenceFacts'
            assert facts[0]['record_scope'] == 'evidence'
            assert facts[0]['artifact_family'] == 'archived_web_page'
            assert facts[0]['corpus_family'] == 'web_page'
            assert facts[0]['content_origin'] == 'historical_archive_capture'
            assert facts[0]['parse_source'] == 'web_document'
            assert facts[0]['input_format'] == 'html'
            assert facts[0]['quality_tier'] == 'high'
            assert facts[0]['graph_summary']['entity_count'] == 1
            assert facts[0]['graph_trace']['snapshot']['graph_id'] == 'graph:evidence-12'
            assert facts[0]['graph_trace']['lineage']['text_length'] == 64
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_facts_normalizes_authority_fact_rows(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value={
            'id': 41,
            'citation': '42 U.S.C. § 1983',
            'fact_count': 1,
            'parse_metadata': {
                'content_origin': 'authority_reference_fallback',
                'content_source_field': 'citation_title_fallback',
                'fallback_mode': 'citation_title_only',
            },
            'provenance': {
                'metadata': {
                    'artifact_family': 'legal_authority_reference',
                    'corpus_family': 'legal_authority',
                    'content_origin': 'authority_reference_fallback',
                },
            },
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:authority-41',
                    'created': False,
                    'reused': True,
                },
            },
        })
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[
            {
                'fact_id': 'fact:authority-1',
                'text': 'Protected activity is recognized by statute.',
                'source_authority_id': 'authority:41',
                'metadata': {
                    'parse_lineage': {
                        'record_scope': 'legal_authority',
                        'source_ref': 'authority:41',
                        'source': 'legal_authority',
                        'input_format': 'text',
                        'quality_tier': 'fallback',
                        'quality_score': 0.0,
                        'transform_lineage': {
                            'content_origin': 'authority_reference_fallback',
                        },
                    },
                },
            },
        ])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Protected activity authority',
                source_table='legal_authorities',
            )

            facts = hook.get_claim_support_facts(
                'testuser',
                'employment',
                claim_element_text='Protected activity',
            )

            assert len(facts) == 1
            assert facts[0]['support_kind'] == 'authority'
            assert facts[0]['source_family'] == 'legal_authority'
            assert facts[0]['source_record_id'] == 41
            assert facts[0]['source_ref'] == 'authority:41'
            assert facts[0]['record_scope'] == 'legal_authority'
            assert facts[0]['artifact_family'] == 'legal_authority_reference'
            assert facts[0]['corpus_family'] == 'legal_authority'
            assert facts[0]['content_origin'] == 'authority_reference_fallback'
            assert facts[0]['parse_source'] == 'legal_authority'
            assert facts[0]['input_format'] == 'text'
            assert facts[0]['authority_record_id'] == 41
            assert facts[0]['graph_trace']['snapshot']['graph_id'] == 'graph:authority-41'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_overview_classifies_elements(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {
                    'employment': [
                        'Protected activity',
                        'Adverse employment action',
                        'Causal connection',
                    ]
                },
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence4',
                support_label='Protected activity email',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Protected activity authority',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Adverse employment action',
                support_kind='evidence',
                support_ref='QmEvidence5',
                support_label='Termination notice',
            )

            overview = hook.get_claim_overview('testuser', 'employment')
            claim_overview = overview['claims']['employment']

            assert claim_overview['covered_count'] == 1
            assert claim_overview['partially_supported_count'] == 1
            assert claim_overview['missing_count'] == 1
            assert claim_overview['covered'][0]['element_text'] == 'Protected activity'
            assert claim_overview['partially_supported'][0]['element_text'] == 'Adverse employment action'
            assert claim_overview['missing'][0]['element_text'] == 'Causal connection'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_gaps_returns_unresolved_elements_with_graph_trace_summary(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 21,
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-21',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:1', 'text': 'Employee complained to HR about discrimination.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceGap',
                support_label='HR complaint email',
                source_table='evidence',
            )

            gaps = hook.get_claim_support_gaps('testuser', 'employment')
            gap = gaps['claims']['employment']['unresolved_elements'][0]

            assert gaps['claims']['employment']['unresolved_count'] == 1
            assert gap['status'] == 'partially_supported'
            assert gap['missing_support_kinds'] == ['authority']
            assert gap['graph_trace_summary']['traced_link_count'] == 1
            assert gap['graph_trace_summary']['snapshot_created_count'] == 1
            assert gap['recommended_action'] == 'collect_missing_support_kind'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_contradiction_candidates_detects_conflicting_facts(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 31,
            'cid': 'QmEvidenceConflict',
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-31',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:pos', 'text': 'Employee submitted a discrimination complaint to management.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value={
            'id': 41,
            'citation': 'Contrary Source',
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:authority-41',
                    'created': False,
                    'reused': True,
                }
            },
        })
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[
            {'fact_id': 'fact:neg', 'text': 'Employee did not submit a discrimination complaint to management.'},
        ])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceConflict',
                support_label='HR complaint email',
                source_table='evidence',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='Contrary Source',
                support_label='Contrary Source',
                source_table='legal_authorities',
            )

            contradictions = hook.get_claim_contradiction_candidates('testuser', 'employment')
            candidate = contradictions['claims']['employment']['candidates'][0]

            assert contradictions['claims']['employment']['candidate_count'] == 1
            assert candidate['claim_element_text'] == 'Protected activity'
            assert sorted(candidate['polarity']) == ['affirmative', 'negative']
            assert 'complaint' in candidate['overlap_terms']
            assert candidate['graph_trace_summary']['traced_link_count'] == 2
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_coverage_matrix_summarizes_authority_treatment_signals(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.legal_authority_storage = Mock()

        authority_records = {
            'Supportive Source': {
                'id': 51,
                'citation': 'Supportive Source',
                'title': 'Supportive Source',
                'fact_count': 1,
                'metadata': {},
                'treatment_records': [],
                'treatment_summary': {
                    'record_count': 0,
                    'by_type': {},
                    'max_confidence': 0.0,
                },
                'graph_metadata': {
                    'graph_snapshot': {'graph_id': 'graph:authority-51', 'created': True, 'reused': False}
                },
            },
            'Questioned Source': {
                'id': 52,
                'citation': 'Questioned Source',
                'title': 'Questioned Source',
                'fact_count': 1,
                'metadata': {},
                'treatment_records': [
                    {'treatment_type': 'questioned', 'treatment_confidence': 0.82}
                ],
                'treatment_summary': {
                    'record_count': 1,
                    'by_type': {'questioned': 1},
                    'max_confidence': 0.82,
                },
                'graph_metadata': {
                    'graph_snapshot': {'graph_id': 'graph:authority-52', 'created': False, 'reused': True}
                },
            },
            'Unconfirmed Source': {
                'id': 53,
                'citation': 'Unconfirmed Source',
                'title': 'Unconfirmed Source',
                'fact_count': 1,
                'metadata': {},
                'treatment_records': [
                    {'treatment_type': 'good_law_unconfirmed', 'treatment_confidence': 0.4}
                ],
                'treatment_summary': {
                    'record_count': 1,
                    'by_type': {'good_law_unconfirmed': 1},
                    'max_confidence': 0.4,
                },
                'graph_metadata': {
                    'graph_snapshot': {'graph_id': 'graph:authority-53', 'created': False, 'reused': True}
                },
            },
        }

        def _get_authority_by_citation(citation):
            return authority_records.get(citation)

        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(side_effect=_get_authority_by_citation)
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a', 'relation_type': 'supports'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            for citation in authority_records:
                hook.add_support_link(
                    user_id='testuser',
                    claim_type='employment',
                    claim_element_text='Protected activity',
                    support_kind='authority',
                    support_ref=citation,
                    support_label=citation,
                    source_table='legal_authorities',
                )

            matrix = hook.get_claim_coverage_matrix('testuser', 'employment')
            claim = matrix['claims']['employment']
            element = claim['elements'][0]

            assert claim['authority_treatment_summary']['authority_link_count'] == 3
            assert claim['authority_treatment_summary']['supportive_authority_link_count'] == 1
            assert claim['authority_treatment_summary']['adverse_authority_link_count'] == 1
            assert claim['authority_treatment_summary']['uncertain_authority_link_count'] == 1
            assert claim['authority_treatment_summary']['treatment_type_counts'] == {
                'questioned': 1,
                'good_law_unconfirmed': 1,
            }
            assert element['authority_treatment_summary']['authority_link_count'] == 3
            assert element['links_by_kind']['authority'][1]['record_summary']['treatment_summary']['by_type'] == {
                'questioned': 1,
            }
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_gaps_distinguishes_fact_gaps_from_adverse_authority(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.legal_authority_storage = Mock()

        authority_records = {
            '42 U.S.C. 2000e-3(a)': {
                'id': 61,
                'citation': '42 U.S.C. 2000e-3(a)',
                'title': 'Retaliation provision',
                'fact_count': 0,
                'metadata': {},
                'treatment_records': [],
                'treatment_summary': {
                    'record_count': 0,
                    'by_type': {},
                    'max_confidence': 0.0,
                },
                'rule_candidates': [
                    {
                        'rule_id': 'rule:retaliation-element',
                        'rule_text': 'Protected activity must precede the employer response.',
                        'rule_type': 'element',
                        'claim_element_id': 'employment:1',
                        'claim_element_text': 'Protected activity',
                        'predicate_template': 'Protected activity',
                        'extraction_confidence': 0.78,
                    },
                    {
                        'rule_id': 'rule:retaliation-exception',
                        'rule_text': 'Except where the employer lacked notice, liability may not attach.',
                        'rule_type': 'exception',
                        'claim_element_id': 'employment:1',
                        'claim_element_text': 'Protected activity',
                        'predicate_template': 'Protected activity',
                        'extraction_confidence': 0.71,
                    },
                ],
                'rule_candidate_summary': {
                    'record_count': 2,
                    'by_type': {'element': 1, 'exception': 1},
                    'max_confidence': 0.78,
                },
                'graph_metadata': {
                    'graph_snapshot': {'graph_id': 'graph:authority-61', 'created': False, 'reused': True}
                },
            },
            'Smith v. Example': {
                'id': 62,
                'citation': 'Smith v. Example',
                'title': 'Adverse treatment decision',
                'fact_count': 0,
                'metadata': {},
                'treatment_records': [
                    {'treatment_type': 'questioned', 'treatment_confidence': 0.81}
                ],
                'treatment_summary': {
                    'record_count': 1,
                    'by_type': {'questioned': 1},
                    'max_confidence': 0.81,
                },
                'rule_candidates': [
                    {
                        'rule_id': 'rule:adverse-element',
                        'rule_text': 'Protected activity can support retaliation claims.',
                        'rule_type': 'element',
                        'claim_element_id': 'employment:1',
                        'claim_element_text': 'Protected activity',
                        'predicate_template': 'Protected activity',
                        'extraction_confidence': 0.66,
                    }
                ],
                'rule_candidate_summary': {
                    'record_count': 1,
                    'by_type': {'element': 1},
                    'max_confidence': 0.66,
                },
                'graph_metadata': {
                    'graph_snapshot': {'graph_id': 'graph:authority-62', 'created': False, 'reused': True}
                },
            },
        }

        def _get_authority_by_citation(citation):
            return authority_records.get(citation)

        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(side_effect=_get_authority_by_citation)
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a', 'relation_type': 'supports'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )

            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. 2000e-3(a)',
                support_label='42 U.S.C. 2000e-3(a)',
                source_table='legal_authorities',
            )

            matrix = hook.get_claim_coverage_matrix('testuser', 'employment')
            claim = matrix['claims']['employment']
            element = claim['elements'][0]
            gaps = hook.get_claim_support_gaps('testuser', 'employment')
            gap = gaps['claims']['employment']['unresolved_elements'][0]

            assert claim['authority_rule_candidate_summary']['authority_link_count'] == 1
            assert claim['authority_rule_candidate_summary']['authority_links_with_rule_candidates'] == 1
            assert claim['authority_rule_candidate_summary']['total_rule_candidate_count'] == 2
            assert claim['authority_rule_candidate_summary']['matched_claim_element_rule_count'] == 2
            assert claim['authority_rule_candidate_summary']['rule_type_counts'] == {
                'element': 1,
                'exception': 1,
            }
            assert element['links_by_kind']['authority'][0]['record_summary']['rule_candidate_summary']['by_type'] == {
                'element': 1,
                'exception': 1,
            }
            assert gap['recommended_action'] == 'collect_fact_support'

            adverse_hook = ClaimSupportHook(mock_mediator, db_path=f'{db_path}.adverse')
            adverse_hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            adverse_hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='Smith v. Example',
                support_label='Smith v. Example',
                source_table='legal_authorities',
            )

            adverse_gaps = adverse_hook.get_claim_support_gaps('testuser', 'employment')
            adverse_gap = adverse_gaps['claims']['employment']['unresolved_elements'][0]

            assert adverse_gap['authority_treatment_summary']['adverse_authority_link_count'] == 1
            assert adverse_gap['recommended_action'] == 'review_adverse_authority'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
            adverse_db_path = f'{db_path}.adverse'
            if os.path.exists(adverse_db_path):
                os.unlink(adverse_db_path)

    def test_persist_claim_support_diagnostics_stores_and_returns_latest_snapshots(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.get_three_phase_status = Mock(return_value=_confirmed_intake_status(
            note='ready for support diagnostics persistence',
        ))

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidencePersist',
                support_label='HR complaint email',
                source_table='evidence',
            )

            persisted = hook.persist_claim_support_diagnostics(
                'testuser',
                'employment',
                required_support_kinds=['authority', 'evidence'],
                metadata={'source': 'unit_test'},
            )
            snapshots = hook.get_claim_support_diagnostic_snapshots(
                'testuser',
                'employment',
                required_support_kinds=['evidence', 'authority'],
            )

            assert persisted['claims']['employment']['snapshots']['gaps']['snapshot_id'] > 0
            assert persisted['claims']['employment']['snapshots']['contradictions']['snapshot_id'] > 0
            assert snapshots['claims']['employment']['gaps']['unresolved_count'] == 1
            assert snapshots['claims']['employment']['contradictions']['candidate_count'] == 0
            assert snapshots['claims']['employment']['snapshots']['gaps']['metadata']['source'] == 'unit_test'
            assert snapshots['claims']['employment']['snapshots']['gaps']['metadata']['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T19:00:00+00:00',
                    'confirmation_note': 'ready for support diagnostics persistence',
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
            assert snapshots['claims']['employment']['snapshots']['gaps']['required_support_kinds'] == [
                'authority',
                'evidence',
            ]
            assert snapshots['claims']['employment']['snapshots']['gaps']['is_stale'] is False
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_diagnostic_snapshots_marks_stale_after_support_changes(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidencePersist',
                support_label='HR complaint email',
                source_table='evidence',
            )
            hook.persist_claim_support_diagnostics(
                'testuser',
                'employment',
                required_support_kinds=['evidence', 'authority'],
                metadata={'source': 'unit_test'},
            )

            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Civil Rights Act',
                source_table='legal_authorities',
            )

            snapshots = hook.get_claim_support_diagnostic_snapshots(
                'testuser',
                'employment',
                required_support_kinds=['evidence', 'authority'],
            )

            assert snapshots['claims']['employment']['snapshots']['gaps']['is_stale'] is True
            assert snapshots['claims']['employment']['snapshots']['contradictions']['is_stale'] is True
            assert snapshots['claims']['employment']['snapshots']['gaps']['stored_support_state_token'] != (
                snapshots['claims']['employment']['snapshots']['gaps']['current_support_state_token']
            )
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_persist_claim_support_diagnostics_prunes_older_snapshot_history(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidencePersist',
                support_label='HR complaint email',
                source_table='evidence',
            )

            persisted = {}
            for run_number in range(3):
                persisted = hook.persist_claim_support_diagnostics(
                    'testuser',
                    'employment',
                    required_support_kinds=['evidence', 'authority'],
                    metadata={'run_number': run_number},
                    retention_limit=2,
                )

            conn = duckdb.connect(db_path)
            rows = conn.execute(
                """
                SELECT snapshot_kind, COUNT(*)
                FROM claim_support_snapshot
                WHERE user_id = ? AND claim_type = ?
                GROUP BY snapshot_kind
                ORDER BY snapshot_kind ASC
                """,
                ['testuser', 'employment'],
            ).fetchall()
            conn.close()

            row_counts = {row[0]: row[1] for row in rows}
            assert row_counts['contradictions'] == 2
            assert row_counts['gaps'] == 2
            assert persisted['retention_limit'] == 2
            assert persisted['pruned_snapshot_count'] == 2
            assert persisted['claims']['employment']['snapshots']['gaps']['pruned_snapshot_count'] == 1
            assert persisted['claims']['employment']['snapshots']['contradictions']['pruned_snapshot_count'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_prune_claim_support_diagnostic_snapshots_removes_older_rows(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidencePersist',
                support_label='HR complaint email',
                source_table='evidence',
            )

            for run_number in range(3):
                hook.persist_claim_support_diagnostics(
                    'testuser',
                    'employment',
                    required_support_kinds=['evidence', 'authority'],
                    metadata={'run_number': run_number},
                    retention_limit=6,
                )

            pruned = hook.prune_claim_support_diagnostic_snapshots(
                'testuser',
                'employment',
                required_support_kinds=['authority', 'evidence'],
                keep_latest=1,
            )

            conn = duckdb.connect(db_path)
            rows = conn.execute(
                """
                SELECT snapshot_kind, COUNT(*)
                FROM claim_support_snapshot
                WHERE user_id = ? AND claim_type = ?
                GROUP BY snapshot_kind
                ORDER BY snapshot_kind ASC
                """,
                ['testuser', 'employment'],
            ).fetchall()
            conn.close()

            row_counts = {row[0]: row[1] for row in rows}
            assert row_counts['contradictions'] == 1
            assert row_counts['gaps'] == 1
            assert pruned['retention_limit'] == 1
            assert pruned['pruned_snapshot_count'] == 4
            assert pruned['claims']['employment']['snapshots']['gaps']['pruned_snapshot_count'] == 2
            assert pruned['claims']['employment']['snapshots']['contradictions']['pruned_snapshot_count'] == 2
            assert len(pruned['claims']['employment']['snapshots']['gaps']['deleted_snapshot_ids']) == 2
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_validation_returns_normalized_statuses(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        evidence_records = {
            'QmEvidenceConflict': {
                'id': 31,
                'cid': 'QmEvidenceConflict',
                'fact_count': 1,
                'graph_metadata': {
                    'graph_snapshot': {
                        'graph_id': 'graph:evidence-31',
                        'created': True,
                        'reused': False,
                    }
                },
            },
            'QmEvidenceOnly': {
                'id': 32,
                'cid': 'QmEvidenceOnly',
                'fact_count': 1,
                'graph_metadata': {
                    'graph_snapshot': {
                        'graph_id': 'graph:evidence-32',
                        'created': True,
                        'reused': False,
                    }
                },
            },
        }
        evidence_facts = {
            31: [
                {'fact_id': 'fact:pos', 'text': 'Employee submitted a discrimination complaint to management.'},
            ],
            32: [
                {'fact_id': 'fact:only', 'text': 'Employer terminated the employee after the complaint.'},
            ],
        }
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(
            side_effect=lambda cid: evidence_records.get(cid)
        )
        mock_mediator.evidence_state.get_evidence_facts = Mock(
            side_effect=lambda record_id: evidence_facts.get(record_id, [])
        )
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value={
            'id': 41,
            'citation': 'Contrary Source',
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:authority-41',
                    'created': False,
                    'reused': True,
                }
            },
        })
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[
            {'fact_id': 'fact:neg', 'text': 'Employee did not submit a discrimination complaint to management.'},
        ])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity', 'Adverse action', 'Causal connection']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceConflict',
                support_label='HR complaint email',
                source_table='evidence',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='Contrary Source',
                support_label='Contrary Source',
                source_table='legal_authorities',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Adverse action',
                support_kind='evidence',
                support_ref='QmEvidenceOnly',
                support_label='Termination notice',
                source_table='evidence',
            )

            validation = hook.get_claim_support_validation('testuser', 'employment')
            claim_validation = validation['claims']['employment']
            element_statuses = {
                element['element_text']: element['validation_status']
                for element in claim_validation['elements']
            }

            assert claim_validation['validation_status'] == 'contradicted'
            assert claim_validation['validation_status_counts'] == {
                'supported': 0,
                'incomplete': 1,
                'missing': 1,
                'contradicted': 1,
            }
            assert claim_validation['proof_gap_count'] == 4
            assert claim_validation['proof_diagnostics']['reasoning']['predicate_count'] >= 3
            assert 'logic_proof' in claim_validation['proof_diagnostics']['reasoning']['adapter_status_counts']
            assert claim_validation['proof_diagnostics']['reasoning']['temporal_fact_count'] == 0
            assert claim_validation['proof_diagnostics']['reasoning']['temporal_relation_count'] == 0
            assert claim_validation['proof_diagnostics']['reasoning']['temporal_issue_count'] == 0
            assert claim_validation['proof_diagnostics']['reasoning']['temporal_partial_order_ready_count'] == 0
            assert claim_validation['proof_diagnostics']['reasoning']['temporal_warning_count'] == 0
            protected_activity = next(
                element for element in claim_validation['elements']
                if element['element_text'] == 'Protected activity'
            )
            assert protected_activity['reasoning_diagnostics']['adapter_statuses']['logic_proof']['operation'] == 'prove_claim_elements'
            assert protected_activity['reasoning_diagnostics']['adapter_statuses']['logic_contradictions']['operation'] == 'check_contradictions'
            assert protected_activity['reasoning_diagnostics']['adapter_statuses']['hybrid_reasoning']['operation'] == 'run_hybrid_reasoning'
            assert protected_activity['reasoning_diagnostics']['adapter_statuses']['ontology_build']['operation'] == 'build_ontology'
            assert protected_activity['reasoning_diagnostics']['adapter_statuses']['ontology_validation']['operation'] == 'validate_ontology'
            assert protected_activity['proof_decision_trace']['decision_source'] == 'heuristic_contradictions'
            assert claim_validation['proof_diagnostics']['decision']['decision_source_counts']['heuristic_contradictions'] == 1
            assert element_statuses['Protected activity'] == 'contradicted'
            assert element_statuses['Adverse action'] == 'incomplete'
            assert element_statuses['Causal connection'] == 'missing'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_validation_uses_logic_contradictions_when_available(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 77,
            'cid': 'QmEvidenceLogic',
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-77',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:logic', 'text': 'Employee submitted a discrimination complaint to management.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:logic'}],
            'relationships': [{'id': 'rel:logic'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value=None)
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={})

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceLogic',
                support_label='HR complaint email',
                source_table='evidence',
            )

            with patch('mediator.claim_support_hooks.check_contradictions', return_value={
                'status': 'success',
                'contradictions': [{'predicate_id': 'contradiction:1'}],
                'predicate_count': 2,
                'metadata': {
                    'operation': 'check_contradictions',
                    'backend_available': True,
                    'implementation_status': 'implemented',
                },
            }):
                validation = hook.get_claim_support_validation('testuser', 'employment')

            protected_activity = validation['claims']['employment']['elements'][0]
            assert protected_activity['validation_status'] == 'contradicted'
            assert protected_activity['proof_decision_trace']['decision_source'] == 'logic_contradictions'
            assert protected_activity['proof_decision_trace']['logic_contradiction_count'] == 1
            assert validation['claims']['employment']['proof_diagnostics']['decision']['adapter_contradicted_element_count'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_validation_uses_logic_proof_for_supported_elements(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 88,
            'cid': 'QmEvidenceProvable',
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-88',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:provable', 'text': 'Employee submitted a discrimination complaint to management.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:provable'}],
            'relationships': [{'id': 'rel:provable'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value=None)
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={})

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceProvable',
                support_label='HR complaint email',
                source_table='evidence',
            )

            with patch('mediator.claim_support_hooks.prove_claim_elements', return_value={
                'status': 'success',
                'provable_elements': [{'predicate_id': 'employment:protected-activity'}],
                'unprovable_elements': [],
                'predicate_count': 2,
                'metadata': {
                    'operation': 'prove_claim_elements',
                    'backend_available': True,
                    'implementation_status': 'implemented',
                },
            }), patch('mediator.claim_support_hooks.validate_ontology', return_value={
                'status': 'success',
                'result': {'valid': True},
                'metadata': {
                    'operation': 'validate_ontology',
                    'backend_available': True,
                    'implementation_status': 'implemented',
                },
            }):
                validation = hook.get_claim_support_validation(
                    'testuser',
                    'employment',
                    required_support_kinds=['evidence'],
                )

            protected_activity = validation['claims']['employment']['elements'][0]
            assert protected_activity['validation_status'] == 'supported'
            assert protected_activity['proof_decision_trace']['decision_source'] == 'logic_proof_supported'
            assert protected_activity['proof_decision_trace']['logic_provable_count'] == 1
            assert protected_activity['proof_decision_trace']['ontology_validation_signal'] == 'valid'
            assert validation['claims']['employment']['proof_diagnostics']['decision']['proof_supported_element_count'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_validation_downgrades_supported_element_when_logic_unprovable(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 89,
            'cid': 'QmEvidenceUnprovable',
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-89',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:unprovable', 'text': 'Employee submitted a discrimination complaint to management.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:unprovable'}],
            'relationships': [{'id': 'rel:unprovable'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value=None)
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={})

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceUnprovable',
                support_label='HR complaint email',
                source_table='evidence',
            )

            with patch('mediator.claim_support_hooks.prove_claim_elements', return_value={
                'status': 'success',
                'provable_elements': [],
                'unprovable_elements': [{'predicate_id': 'employment:protected-activity'}],
                'predicate_count': 2,
                'metadata': {
                    'operation': 'prove_claim_elements',
                    'backend_available': True,
                    'implementation_status': 'implemented',
                },
            }), patch('mediator.claim_support_hooks.validate_ontology', return_value={
                'status': 'success',
                'result': {'valid': False},
                'metadata': {
                    'operation': 'validate_ontology',
                    'backend_available': True,
                    'implementation_status': 'implemented',
                },
            }):
                validation = hook.get_claim_support_validation(
                    'testuser',
                    'employment',
                    required_support_kinds=['evidence'],
                )

            protected_activity = validation['claims']['employment']['elements'][0]
            assert protected_activity['validation_status'] == 'incomplete'
            assert protected_activity['recommended_action'] == 'review_existing_support'
            assert protected_activity['proof_decision_trace']['decision_source'] == 'logic_unprovable'
            assert protected_activity['proof_decision_trace']['logic_unprovable_count'] == 1
            assert protected_activity['proof_decision_trace']['ontology_validation_signal'] == 'invalid'
            assert {gap['gap_type'] for gap in protected_activity['proof_gaps']} == {
                'logic_unprovable',
                'ontology_validation_failed',
            }
            assert validation['claims']['employment']['proof_diagnostics']['decision']['logic_unprovable_element_count'] == 1
            assert validation['claims']['employment']['proof_diagnostics']['decision']['ontology_invalid_element_count'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_validation_recommends_parse_quality_improvement_for_low_quality_support(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 91,
            'cid': 'QmEvidenceLowQuality',
            'type': 'document',
            'parse_status': 'fallback',
            'chunk_count': 1,
            'parsed_text_preview': '',
            'parse_metadata': {
                'source': 'bytes',
                'input_format': 'pdf',
                'extraction_method': 'pdf_unparsed',
                'quality_tier': 'empty',
                'quality_score': 0.0,
                'page_count': 1,
                'parse_quality': {'quality_tier': 'empty', 'quality_score': 0.0, 'quality_flags': ['requires_ocr_or_binary_pdf']},
                'source_span': {'char_start': 0, 'char_end': 0, 'text_length': 0, 'raw_size': 4096, 'page_count': 1},
                'transform_lineage': {'source': 'bytes', 'input_format': 'pdf', 'normalization': 'pdf_unparsed'},
            },
            'fact_count': 1,
            'graph_metadata': {'graph_snapshot': {'graph_id': 'graph:evidence-91', 'created': True, 'reused': False}},
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:1', 'text': 'Complaint appears in a low-quality PDF exhibit.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value=None)
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={})

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook._run_element_reasoning_diagnostics = Mock(return_value={
                'backend_available_count': 0,
                'predicate_count': 0,
                'ontology_entity_count': 0,
                'ontology_relationship_count': 0,
                'adapter_statuses': {},
                'used_fallback_ontology': True,
            })
            hook.register_claim_requirements('testuser', {'employment': ['Protected activity']})
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceLowQuality',
                support_label='Unreadable PDF exhibit',
                source_table='evidence',
            )

            validation = hook.get_claim_support_validation(
                'testuser',
                'employment',
                required_support_kinds=['evidence'],
            )

            protected_activity = validation['claims']['employment']['elements'][0]
            assert protected_activity['validation_status'] == 'incomplete'
            assert protected_activity['recommended_action'] == 'improve_parse_quality'
            assert protected_activity['support_trace_summary']['parse_quality_tier_counts']['empty'] == 1
            assert protected_activity['support_trace_summary']['avg_parse_quality_score'] == 0.0
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_run_element_reasoning_diagnostics_includes_temporal_timeline_predicates(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.get_three_phase_status = Mock(return_value={
            'canonical_fact_summary': {
                'facts': [
                    {
                        'fact_id': 'fact_1',
                        'text': 'Employee complained to HR.',
                        'fact_type': 'timeline',
                        'claim_types': ['retaliation'],
                        'element_tags': ['protected_activity'],
                        'temporal_context': {
                            'start_date': '2025-03-01',
                            'end_date': '2025-03-01',
                            'granularity': 'day',
                            'is_approximate': False,
                            'is_range': False,
                            'relative_markers': [],
                        },
                    },
                    {
                        'fact_id': 'fact_2',
                        'text': 'Employee was terminated.',
                        'fact_type': 'timeline',
                        'claim_types': ['retaliation'],
                        'element_tags': ['adverse_action'],
                        'temporal_context': {
                            'start_date': '2025-04-15',
                            'end_date': '2025-04-15',
                            'granularity': 'day',
                            'is_approximate': False,
                            'is_range': False,
                            'relative_markers': [],
                        },
                    },
                ],
            },
            'proof_lead_summary': {
                'proof_leads': [
                    {
                        'lead_id': 'lead_1',
                        'description': 'HR complaint email',
                        'claim_type': 'retaliation',
                        'element_targets': ['protected_activity'],
                        'related_fact_ids': ['fact_1'],
                        'temporal_scope': 'March 2025',
                        'temporal_context': {
                            'start_date': '2025-03-01',
                            'end_date': '2025-03-31',
                            'granularity': 'month',
                            'is_approximate': False,
                            'is_range': False,
                            'relative_markers': [],
                        },
                    },
                ],
            },
            'timeline_relation_summary': {
                'relations': [
                    {
                        'relation_id': 'timeline_relation_001',
                        'source_fact_id': 'fact_1',
                        'target_fact_id': 'fact_2',
                        'relation_type': 'before',
                        'source_start_date': '2025-03-01',
                        'source_end_date': '2025-03-01',
                        'target_start_date': '2025-04-15',
                        'target_end_date': '2025-04-15',
                        'confidence': 'medium',
                    },
                ],
            },
            'timeline_consistency_summary': {
                'event_count': 2,
                'relation_count': 1,
                'partial_order_ready': False,
                'warnings': ['Timeline needs corroboration.'],
            },
            'intake_contradictions': {
                'candidates': [
                    {
                        'contradiction_id': 'temporal_reverse_before_001',
                        'category': 'temporal_reverse_before',
                        'summary': 'Complaint and termination are ordered inconsistently.',
                        'left_node_name': 'Employee complained to HR.',
                        'right_node_name': 'Employee was terminated.',
                        'severity': 'blocking',
                        'recommended_resolution_lane': 'request_document',
                    },
                ],
            },
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            element = {
                'element_id': 'retaliation:1',
                'element_text': 'Protected activity',
                'status': 'supported',
                'support_by_kind': {'evidence': 1},
                'missing_support_kinds': [],
                'support_traces': [
                    {
                        'fact_id': 'fact:support',
                        'support_ref': 'QmEvidenceTemporal',
                        'support_kind': 'evidence',
                        'source_table': 'evidence',
                        'fact_text': 'HR complaint email confirms the report.',
                        'confidence': 0.91,
                    },
                ],
            }
            captured = {}

            def _capture_build_ontology(seed_text):
                captured['seed_text'] = seed_text
                return {
                    'status': 'not_implemented',
                    'ontology': None,
                    'metadata': {
                        'operation': 'build_ontology',
                        'backend_available': False,
                        'implementation_status': 'not_implemented',
                    },
                }
            def _capture_prove(payload):
                captured['proof_payload'] = payload
                predicates = payload.get('predicates', []) if isinstance(payload, dict) else []
                captured['predicates'] = predicates
                return {
                    'status': 'not_implemented',
                    'provable_elements': [],
                    'unprovable_elements': [],
                    'predicate_count': len(predicates),
                    'temporal_reasoning_payload': {
                        'claim_support_temporal_handoff': payload.get('claim_support_temporal_handoff', {}) if isinstance(payload, dict) else {},
                    },
                    'metadata': {
                        'operation': 'prove_claim_elements',
                        'backend_available': False,
                        'implementation_status': 'not_implemented',
                    },
                }

            def _capture_contradictions(payload):
                captured['contradiction_payload'] = payload
                predicates = payload.get('predicates', []) if isinstance(payload, dict) else []
                captured['contradiction_predicates'] = predicates
                return {
                    'status': 'not_implemented',
                    'contradictions': [],
                    'predicate_count': len(predicates),
                    'temporal_reasoning_payload': {
                        'claim_support_temporal_handoff': payload.get('claim_support_temporal_handoff', {}) if isinstance(payload, dict) else {},
                    },
                    'metadata': {
                        'operation': 'check_contradictions',
                        'backend_available': False,
                        'implementation_status': 'not_implemented',
                    },
                }

            def _capture_hybrid_reasoning(payload):
                captured['hybrid_payload'] = payload
                predicates = payload.get('predicates', []) if isinstance(payload, dict) else []
                return {
                    'status': 'success',
                    'result': {
                        'formalism': 'tdfol_dcec_bridge_v1',
                        'tdfol_formulas': ['Before(fact_1,fact_2)'],
                        'dcec_formulas': ['Conflicts(employee_complained_to_hr,employee_was_terminated)'],
                    },
                    'predicate_count': len(predicates),
                    'temporal_reasoning_payload': {
                        'formalism': 'tdfol_dcec_bridge_v1',
                        'tdfol_formulas': ['Before(fact_1,fact_2)'],
                        'dcec_formulas': ['Conflicts(employee_complained_to_hr,employee_was_terminated)'],
                    },
                    'metadata': {
                        'operation': 'run_hybrid_reasoning',
                        'backend_available': True,
                        'implementation_status': 'implemented',
                    },
                }

            with patch('mediator.claim_support_hooks.build_ontology', side_effect=_capture_build_ontology), patch(
                'mediator.claim_support_hooks.prove_claim_elements', side_effect=_capture_prove
            ), patch(
                'mediator.claim_support_hooks.check_contradictions', side_effect=_capture_contradictions
            ), patch(
                'mediator.claim_support_hooks.run_hybrid_reasoning', side_effect=_capture_hybrid_reasoning
            ), patch(
                'mediator.claim_support_hooks.validate_ontology', return_value={
                    'status': 'not_implemented',
                    'result': {},
                    'metadata': {
                        'operation': 'validate_ontology',
                        'backend_available': False,
                        'implementation_status': 'not_implemented',
                    },
                }
            ):
                diagnostics = hook._run_element_reasoning_diagnostics('retaliation', element, [])

            predicate_types = {
                predicate['predicate_type']
                for predicate in captured['predicates']
                if isinstance(predicate, dict)
            }

            assert diagnostics['predicate_count'] == len(captured['predicates'])
            assert len(captured['contradiction_predicates']) == len(captured['predicates'])
            assert captured['proof_payload']['predicates'] == captured['predicates']
            assert captured['contradiction_payload']['predicates'] == captured['predicates']
            assert captured['hybrid_payload']['predicates'] == captured['predicates']
            assert captured['proof_payload']['claim_support_temporal_handoff'] == captured['hybrid_payload']['claim_support_temporal_handoff']
            assert captured['contradiction_payload']['claim_support_temporal_handoff'] == captured['hybrid_payload']['claim_support_temporal_handoff']
            assert {'claim_element', 'support_trace', 'temporal_fact', 'temporal_proof_lead', 'temporal_relation', 'temporal_consistency', 'temporal_issue'} <= predicate_types
            assert 'Timeline fact: Employee complained to HR.' in captured['seed_text']
            assert 'Timeline relation: fact_1 before fact_2' in captured['seed_text']
            assert 'Temporal issue: Complaint and termination are ordered inconsistently.' in captured['seed_text']
            assert diagnostics['ontology_entity_count'] >= 4
            assert diagnostics['ontology_relationship_count'] >= 4
            assert diagnostics['adapter_statuses']['hybrid_reasoning']['operation'] == 'run_hybrid_reasoning'
            assert diagnostics['adapter_statuses']['hybrid_reasoning']['implementation_status'] == 'implemented'
            assert diagnostics['temporal_summary'] == {
                'fact_count': 2,
                'proof_lead_count': 1,
                'relation_count': 1,
                'issue_count': 1,
                'partial_order_ready': False,
                'warning_count': 1,
                'warnings': ['Timeline needs corroboration.'],
                'relation_type_counts': {'before': 1},
                'relation_preview': ['fact_1 before fact_2'],
            }
            assert diagnostics['temporal_rule_profile'] == {
                'available': True,
                'evaluated': True,
                'profile_id': 'retaliation_temporal_profile_v1',
                'rule_frame_id': 'retaliation_temporal_frame',
                'claim_type': 'retaliation',
                'element_role': 'protected_activity',
                'status': 'satisfied',
                'matched_fact_ids': ['fact_1'],
                'matched_relation_ids': [],
                'blocking_reasons': [],
                'warnings': [],
                'recommended_follow_ups': [],
            }
            assert diagnostics['temporal_proof_bundle'] == {
                'proof_bundle_id': 'retaliation:retaliation_1:retaliation_temporal_profile_v1',
                'claim_type': 'retaliation',
                'claim_element_id': 'retaliation:1',
                'claim_element_text': 'Protected activity',
                'profile_id': 'retaliation_temporal_profile_v1',
                'rule_frame_id': 'retaliation_temporal_frame',
                'element_role': 'protected_activity',
                'status': 'satisfied',
                'available': True,
                'matched_fact_ids': ['fact_1'],
                'matched_relation_ids': [],
                'temporal_fact_ids': ['fact_1', 'fact_2'],
                'temporal_relation_ids': ['timeline_relation_001'],
                'temporal_issue_ids': ['temporal_reverse_before_001'],
                'source_artifact_ids': [],
                'testimony_record_ids': [],
                'blocking_reasons': [],
                'warnings': [],
                'recommended_follow_ups': [],
                'theorem_exports': {
                    'tdfol_formulas': ['ProtectedActivity(fact_1)', 'AdverseAction(fact_2)', 'Before(fact_1,fact_2)'],
                    'dcec_formulas': ['Happens(fact_1,t_2025_03_01)', 'Happens(fact_2,t_2025_04_15)'],
                    'theorem_export_metadata': {
                        'contract_version': 'claim_support_temporal_handoff_v1',
                        'claim_type': 'retaliation',
                        'claim_element_id': 'retaliation:1',
                        'proof_bundle_id': 'retaliation:retaliation_1:retaliation_temporal_profile_v1',
                        'rule_frame_id': 'retaliation_temporal_frame',
                        'chronology_blocked': True,
                        'chronology_task_count': 1,
                        'unresolved_temporal_issue_ids': ['temporal_reverse_before_001'],
                        'event_ids': ['fact_1', 'fact_2'],
                        'temporal_fact_ids': ['fact_1', 'fact_2'],
                        'temporal_relation_ids': ['timeline_relation_001'],
                        'timeline_issue_ids': ['temporal_reverse_before_001'],
                        'temporal_issue_ids': ['temporal_reverse_before_001'],
                        'temporal_proof_bundle_ids': ['retaliation:retaliation_1:retaliation_temporal_profile_v1'],
                        'temporal_proof_objectives': ['retaliation_temporal_frame'],
                    },
                },
                'theorem_export_counts': {
                    'tdfol_formula_count': 3,
                    'dcec_formula_count': 2,
                },
            }
            assert diagnostics['claim_support_temporal_handoff'] == {
                'claim_type': 'retaliation',
                'claim_element_id': 'retaliation:1',
                'unresolved_temporal_issue_count': 1,
                'unresolved_temporal_issue_ids': ['temporal_reverse_before_001'],
                'chronology_task_count': 1,
                'event_ids': ['fact_1', 'fact_2'],
                'temporal_fact_ids': ['fact_1', 'fact_2'],
                'temporal_relation_ids': ['timeline_relation_001'],
                'timeline_issue_ids': ['temporal_reverse_before_001'],
                'temporal_issue_ids': ['temporal_reverse_before_001'],
                'temporal_proof_bundle_ids': ['retaliation:retaliation_1:retaliation_temporal_profile_v1'],
                'temporal_proof_objectives': ['retaliation_temporal_frame'],
            }
            assert captured['hybrid_payload']['claim_support_temporal_handoff'] == diagnostics['claim_support_temporal_handoff']
            temporal_fact_predicate = next(
                predicate for predicate in captured['predicates']
                if isinstance(predicate, dict) and predicate.get('predicate_type') == 'temporal_fact'
            )
            assert temporal_fact_predicate['event_label'] == 'Employee complained to HR.'
            assert temporal_fact_predicate['predicate_family'] == 'timeline'
            assert temporal_fact_predicate['source_artifact_ids'] == []
            assert temporal_fact_predicate['testimony_record_ids'] == []
            assert temporal_fact_predicate['source_span_refs'] == []
            temporal_relation_predicate = next(
                predicate for predicate in captured['predicates']
                if isinstance(predicate, dict) and predicate.get('predicate_type') == 'temporal_relation'
            )
            assert temporal_relation_predicate['inference_mode'] == 'derived_from_temporal_context'
            assert temporal_relation_predicate['inference_basis'] == 'normalized_temporal_context'
            assert temporal_relation_predicate['explanation'] == 'fact_1 before fact_2 based on normalized temporal context.'
            temporal_issue_predicate = next(
                predicate for predicate in captured['predicates']
                if isinstance(predicate, dict) and predicate.get('predicate_type') == 'temporal_issue'
            )
            assert temporal_issue_predicate['source_kind'] == 'contradiction_queue'
            assert temporal_issue_predicate['inference_mode'] == 'imported_temporal_contradiction'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_evaluate_temporal_rule_profile_for_retaliation_causation_reports_partial_order_gap(self):
        profile = evaluate_temporal_rule_profile(
            'retaliation',
            {
                'element_id': 'retaliation:3',
                'element_text': 'Causal connection',
            },
            {
                'temporal_facts': [
                    {
                        'fact_id': 'fact_1',
                        'element_tags': ['protected_activity'],
                        'temporal_context': {'start_date': '2025-03-01'},
                    },
                    {
                        'fact_id': 'fact_2',
                        'element_tags': ['adverse_action'],
                        'temporal_context': {'start_date': '2025-04-15'},
                    },
                ],
                'temporal_relations': [],
                'temporal_issues': [],
            },
        )

        assert profile == {
            'available': True,
            'evaluated': True,
            'profile_id': 'retaliation_temporal_profile_v1',
            'rule_frame_id': 'retaliation_temporal_frame',
            'claim_type': 'retaliation',
            'element_role': 'causal_connection',
            'status': 'partial',
            'matched_fact_ids': ['fact_1', 'fact_2'],
            'matched_relation_ids': [],
            'blocking_reasons': [
                'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.'
            ],
            'warnings': [
                'Protected activity and adverse action are both present but lack an ordering relation.'
            ],
            'recommended_follow_ups': [
                {
                    'lane': 'clarify_with_complainant',
                    'reason': 'Clarify whether the protected activity occurred before the adverse action.',
                }
            ],
        }

    def test_get_temporal_reasoning_context_prefers_temporal_registries(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.get_three_phase_status = Mock(return_value={
            'canonical_fact_summary': {'count': 0, 'facts': []},
            'proof_lead_summary': {
                'proof_leads': [
                    {
                        'lead_id': 'lead_1',
                        'description': 'Timeline email',
                        'claim_type': 'retaliation',
                        'element_targets': ['protected_activity'],
                        'related_fact_ids': ['fact_1'],
                        'temporal_scope': 'March 2025',
                        'temporal_context': {
                            'start_date': '2025-03-01',
                            'end_date': '2025-03-31',
                            'granularity': 'month',
                            'is_approximate': False,
                            'is_range': False,
                            'relative_markers': [],
                        },
                    },
                ],
            },
            'temporal_fact_registry_summary': {
                'count': 1,
                'facts': [
                    {
                        'fact_id': 'fact_1',
                        'temporal_fact_id': 'fact_1',
                        'text': 'Employee complained to HR.',
                        'fact_type': 'timeline',
                        'claim_types': ['retaliation'],
                        'element_tags': ['protected_activity'],
                        'temporal_context': {
                            'start_date': '2025-03-01',
                            'end_date': '2025-03-01',
                            'granularity': 'day',
                            'is_approximate': False,
                            'is_range': False,
                            'relative_markers': [],
                        },
                    },
                ],
            },
            'timeline_relation_summary': {'count': 0, 'relations': []},
            'temporal_relation_registry_summary': {
                'count': 1,
                'relations': [
                    {
                        'relation_id': 'timeline_relation_001',
                        'source_fact_id': 'fact_1',
                        'target_fact_id': 'fact_1',
                        'relation_type': 'same_time',
                        'source_start_date': '2025-03-01',
                        'source_end_date': '2025-03-01',
                        'target_start_date': '2025-03-01',
                        'target_end_date': '2025-03-01',
                        'claim_types': ['retaliation'],
                        'element_tags': ['protected_activity'],
                        'confidence': 'high',
                    },
                ],
            },
            'timeline_consistency_summary': {
                'event_count': 1,
                'relation_count': 1,
                'partial_order_ready': False,
                'warnings': ['Need date corroboration.'],
            },
            'temporal_issue_registry_summary': {
                'count': 1,
                'issues': [
                    {
                        'issue_id': 'temporal_issue:relative_only_ordering:fact_1',
                        'issue_type': 'relative_only_ordering',
                        'category': 'relative_only_ordering',
                        'summary': 'Timeline fact fact_1 only has relative ordering and still needs anchoring.',
                        'severity': 'blocking',
                        'recommended_resolution_lane': 'clarify_with_complainant',
                        'fact_ids': ['fact_1'],
                        'claim_types': ['retaliation'],
                        'element_tags': ['protected_activity'],
                    },
                ],
            },
            'intake_contradictions': {'candidates': []},
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            context = hook._get_temporal_reasoning_context(
                'retaliation',
                {
                    'element_id': 'protected_activity',
                    'element_text': 'Protected activity',
                },
            )
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

        assert [fact['fact_id'] for fact in context['temporal_facts']] == ['fact_1']
        assert [relation['relation_id'] for relation in context['temporal_relations']] == ['timeline_relation_001']
        assert [issue['issue_type'] for issue in context['temporal_issues']] == ['relative_only_ordering']
        assert context['consistency_summary']['warning_count'] == 1

    def test_retaliation_temporal_rule_profile_requires_ordering_for_causation(self):
        profile = evaluate_temporal_rule_profile(
            'retaliation',
            {
                'element_id': 'causation',
                'element_text': 'Causal connection',
            },
            {
                'temporal_facts': [
                    {
                        'fact_id': 'fact_1',
                        'element_tags': ['protected_activity'],
                        'temporal_context': {'start_date': '2025-03-01'},
                    },
                    {
                        'fact_id': 'fact_2',
                        'element_tags': ['adverse_action'],
                        'temporal_context': {'start_date': '2025-04-15'},
                    },
                ],
                'temporal_relations': [],
                'temporal_issues': [],
            },
        )

        assert profile['available'] is True
        assert profile['evaluated'] is True
        assert profile['profile_id'] == 'retaliation_temporal_profile_v1'
        assert profile['status'] == 'partial'
        assert profile['blocking_reasons'] == [
            'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.'
        ]
        assert profile['recommended_follow_ups'][0]['lane'] == 'clarify_with_complainant'

    def test_get_claim_support_validation_uses_temporal_rule_profile_for_retaliation_causation(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.get_three_phase_status = Mock(return_value={
            'canonical_fact_summary': {'count': 0, 'facts': []},
            'proof_lead_summary': {'count': 0, 'proof_leads': []},
            'temporal_fact_registry_summary': {
                'count': 2,
                'facts': [
                    {
                        'fact_id': 'fact_1',
                        'temporal_fact_id': 'fact_1',
                        'text': 'Employee complained to HR.',
                        'fact_type': 'timeline',
                        'claim_types': ['retaliation'],
                        'element_tags': ['protected_activity'],
                        'temporal_context': {
                            'start_date': '2025-03-01',
                            'end_date': '2025-03-01',
                            'granularity': 'day',
                            'is_approximate': False,
                            'is_range': False,
                            'relative_markers': [],
                        },
                    },
                    {
                        'fact_id': 'fact_2',
                        'temporal_fact_id': 'fact_2',
                        'text': 'Employee was terminated.',
                        'fact_type': 'timeline',
                        'claim_types': ['retaliation'],
                        'element_tags': ['adverse_action'],
                        'temporal_context': {
                            'start_date': '2025-04-15',
                            'end_date': '2025-04-15',
                            'granularity': 'day',
                            'is_approximate': False,
                            'is_range': False,
                            'relative_markers': [],
                        },
                    },
                ],
            },
            'temporal_relation_registry_summary': {'count': 0, 'relations': []},
            'timeline_relation_summary': {'count': 0, 'relations': []},
            'timeline_consistency_summary': {
                'event_count': 2,
                'relation_count': 0,
                'partial_order_ready': False,
                'warnings': ['Timeline ordering is incomplete.'],
            },
            'temporal_issue_registry_summary': {'count': 0, 'issues': []},
            'intake_contradictions': {'candidates': []},
        })
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 144,
            'cid': 'QmRetaliationEvidence',
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-144',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:retaliation', 'text': 'Email and termination notice confirm the retaliation timeline.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:retaliation'}],
            'relationships': [{'id': 'rel:retaliation'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value=None)
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={})

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements('testuser', {'retaliation': ['Causal connection']})
            hook.add_support_link(
                user_id='testuser',
                claim_type='retaliation',
                claim_element_text='Causal connection',
                support_kind='evidence',
                support_ref='QmRetaliationEvidence',
                support_label='HR complaint and termination records',
                source_table='evidence',
            )

            with patch('mediator.claim_support_hooks.prove_claim_elements', return_value={
                'status': 'not_implemented',
                'provable_elements': [],
                'unprovable_elements': [],
                'predicate_count': 0,
                'metadata': {
                    'operation': 'prove_claim_elements',
                    'backend_available': False,
                    'implementation_status': 'not_implemented',
                },
            }), patch('mediator.claim_support_hooks.check_contradictions', return_value={
                'status': 'not_implemented',
                'contradictions': [],
                'predicate_count': 0,
                'metadata': {
                    'operation': 'check_contradictions',
                    'backend_available': False,
                    'implementation_status': 'not_implemented',
                },
            }), patch('mediator.claim_support_hooks.build_ontology', return_value={
                'status': 'not_implemented',
                'ontology': None,
                'metadata': {
                    'operation': 'build_ontology',
                    'backend_available': False,
                    'implementation_status': 'not_implemented',
                },
            }), patch('mediator.claim_support_hooks.run_hybrid_reasoning', return_value={
                'status': 'not_implemented',
                'result': {},
                'predicate_count': 0,
                'metadata': {
                    'operation': 'run_hybrid_reasoning',
                    'backend_available': False,
                    'implementation_status': 'not_implemented',
                },
            }), patch('mediator.claim_support_hooks.validate_ontology', return_value={
                'status': 'not_implemented',
                'result': {},
                'metadata': {
                    'operation': 'validate_ontology',
                    'backend_available': False,
                    'implementation_status': 'not_implemented',
                },
            }):
                validation = hook.get_claim_support_validation(
                    'testuser',
                    'retaliation',
                    required_support_kinds=['evidence'],
                )
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

        causation = validation['claims']['retaliation']['elements'][0]
        assert causation['validation_status'] == 'incomplete'
        assert causation['proof_decision_trace']['decision_source'] == 'temporal_rule_partial'
        assert causation['proof_decision_trace']['temporal_rule_status'] == 'partial'
        assert {gap['gap_type'] for gap in causation['proof_gaps']} == {'temporal_rule_partial'}
        assert validation['claims']['retaliation']['proof_diagnostics']['decision']['temporal_rule_gap_element_count'] == 1

    def test_resolve_follow_up_manual_review_appends_resolution_event(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            initial_id = hook.record_follow_up_execution(
                user_id='testuser',
                claim_type='employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                support_kind='manual_review',
                query_text='manual_review::employment::employment:1::resolve_contradiction',
                status='skipped_manual_review',
                metadata={
                    'execution_mode': 'manual_review',
                    'validation_status': 'contradicted',
                    'follow_up_focus': 'contradiction_resolution',
                    'query_strategy': 'standard_gap_targeted',
                },
            )

            resolution = hook.resolve_follow_up_manual_review(
                user_id='testuser',
                related_execution_id=initial_id,
                resolution_status='resolved_supported',
                resolution_notes='Operator confirmed the contradictory evidence was reconciled.',
                metadata={'reviewer': 'case-analyst'},
            )
            history = hook.get_recent_follow_up_execution('testuser', 'employment', limit=5)

            assert resolution['recorded'] is True
            assert resolution['status'] == 'resolved_manual_review'
            assert resolution['metadata']['resolution_status'] == 'resolved_supported'
            assert resolution['metadata']['reviewer'] == 'case-analyst'
            assert history['claims']['employment'][0]['status'] == 'resolved_manual_review'
            assert history['claims']['employment'][0]['resolution_status'] == 'resolved_supported'
            assert history['claims']['employment'][0]['related_execution_id'] == initial_id
            assert history['claims']['employment'][1]['status'] == 'skipped_manual_review'

            conn = duckdb.connect(db_path)
            rows = conn.execute(
                """
                SELECT status, metadata
                FROM claim_follow_up_execution
                WHERE user_id = ? AND claim_type = ?
                ORDER BY id ASC
                """,
                ['testuser', 'employment'],
            ).fetchall()
            conn.close()

            assert len(rows) == 2
            assert rows[1][0] == 'resolved_manual_review'
            assert json.loads(rows[1][1])['resolution_notes'] == (
                'Operator confirmed the contradictory evidence was reconciled.'
            )
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_coverage_matrix_groups_links_by_support_kind(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 18,
            'cid': 'QmEvidence6',
            'type': 'document',
            'source_url': 'https://example.com/evidence',
            'parse_status': 'parsed',
            'chunk_count': 2,
            'parsed_text_preview': 'Subject: HR complaint\n\nI reported discrimination.',
            'parse_metadata': {
                'source': 'bytes',
                'input_format': 'email',
                'extraction_method': 'email_to_text',
                'quality_tier': 'high',
                'quality_score': 96.0,
                'page_count': 1,
                'content_origin': 'historical_archive_capture',
                'historical_capture': True,
                'capture_source': 'archived_domain_scrape',
                'archive_url': 'https://web.archive.org/web/20240101120000/https://example.com/evidence',
                'version_of': 'https://example.com/evidence',
                'source_span': {'char_start': 0, 'char_end': 52, 'text_length': 52, 'raw_size': 64, 'page_count': 1},
                'transform_lineage': {
                    'source': 'bytes',
                    'input_format': 'email',
                    'normalization': 'email_to_text',
                    'content_origin': 'historical_archive_capture',
                    'historical_capture': True,
                    'capture_source': 'archived_domain_scrape',
                    'archive_url': 'https://web.archive.org/web/20240101120000/https://example.com/evidence',
                    'version_of': 'https://example.com/evidence',
                },
            },
            'graph_status': 'ready',
            'graph_entity_count': 3,
            'graph_relationship_count': 2,
            'fact_count': 2,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-18',
                    'created': True,
                    'reused': False,
                    'metadata': {'lineage': {'status': 'ready'}},
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:1', 'text': 'Employee complained to HR.'},
            {'fact_id': 'fact:2', 'text': 'Complaint referenced discrimination.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}, {'id': 'entity:2'}, {'id': 'entity:3'}],
            'relationships': [{'id': 'rel:1'}, {'id': 'rel:2'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value={
            'id': 7,
            'citation': '42 U.S.C. § 1983',
            'title': 'Civil Rights Act',
            'url': 'https://example.com/usc/1983',
            'parse_status': 'parsed',
            'chunk_count': 1,
            'parsed_text_preview': 'Civil Rights Act\n\nSection 1983 authorizes relief.',
            'parse_metadata': {
                'source': 'legal_authority',
                'input_format': 'html',
                'extraction_method': 'html_to_text',
                'quality_tier': 'high',
                'quality_score': 95.0,
                'page_count': 1,
                'content_origin': 'authority_reference_fallback',
                'content_source_field': 'citation_title_fallback',
                'fallback_mode': 'citation_title_only',
                'source_span': {'char_start': 0, 'char_end': 48, 'text_length': 48, 'raw_size': 60, 'page_count': 1},
                'transform_lineage': {
                    'source': 'legal_authority',
                    'input_format': 'html',
                    'normalization': 'html_to_text',
                    'content_origin': 'authority_reference_fallback',
                    'content_source_field': 'citation_title_fallback',
                    'fallback_mode': 'citation_title_only',
                },
            },
            'graph_status': 'ready',
            'graph_entity_count': 1,
            'graph_relationship_count': 1,
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:authority-7',
                    'created': True,
                    'reused': False,
                    'metadata': {'lineage': {'status': 'ready'}},
                }
            },
        })
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[
            {'fact_id': 'auth:1', 'text': 'Section 1983 authorizes relief.'},
        ])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity', 'Adverse employment action']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence6',
                support_label='HR complaint email',
                source_table='evidence',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Civil Rights Act',
                source_table='legal_authorities',
            )

            matrix = hook.get_claim_coverage_matrix('testuser', 'employment')
            claim_matrix = matrix['claims']['employment']
            protected_activity = claim_matrix['elements'][0]

            assert claim_matrix['status_counts']['covered'] == 1
            assert claim_matrix['status_counts']['missing'] == 1
            assert claim_matrix['total_links'] == 2
            assert claim_matrix['total_facts'] == 3
            assert protected_activity['status'] == 'covered'
            assert protected_activity['missing_support_kinds'] == []
            assert len(protected_activity['links_by_kind']['evidence']) == 1
            assert len(protected_activity['links_by_kind']['authority']) == 1
            assert protected_activity['links_by_kind']['evidence'][0]['record_summary']['cid'] == 'QmEvidence6'
            assert protected_activity['links_by_kind']['authority'][0]['record_summary']['citation'] == '42 U.S.C. § 1983'
            assert protected_activity['links_by_kind']['evidence'][0]['record_summary']['parse_summary']['input_format'] == 'email'
            assert protected_activity['links_by_kind']['authority'][0]['record_summary']['parse_summary']['input_format'] == 'html'
            assert protected_activity['links_by_kind']['evidence'][0]['graph_summary']['entity_count'] == 3
            assert protected_activity['links_by_kind']['authority'][0]['graph_summary']['relationship_count'] == 1
            assert protected_activity['links_by_kind']['evidence'][0]['graph_trace']['snapshot']['graph_id'] == 'graph:evidence-18'
            assert protected_activity['links_by_kind']['authority'][0]['graph_trace']['snapshot']['graph_id'] == 'graph:authority-7'
            assert claim_matrix['support_trace_summary']['trace_count'] == 3
            assert claim_matrix['support_trace_summary']['unique_fact_count'] == 3
            assert claim_matrix['support_trace_summary']['parsed_record_count'] == 2
            assert claim_matrix['support_trace_summary']['parse_input_format_counts']['email'] == 1
            assert claim_matrix['support_trace_summary']['parse_input_format_counts']['html'] == 1
            assert claim_matrix['support_trace_summary']['parse_quality_tier_counts']['high'] == 2
            assert claim_matrix['support_trace_summary']['avg_parse_quality_score'] == 95.5
            assert claim_matrix['support_trace_summary']['artifact_family_counts'] == {
                'archived_web_page': 2,
                'legal_authority_reference': 1,
            }
            assert claim_matrix['support_packet_summary']['historical_capture_count'] == 2
            assert claim_matrix['support_packet_summary']['artifact_family_counts'] == {
                'archived_web_page': 2,
                'legal_authority_reference': 1,
            }
            assert claim_matrix['support_packet_summary']['content_origin_counts'] == {
                'historical_archive_capture': 2,
                'authority_reference_fallback': 1,
            }
            assert claim_matrix['support_packet_summary']['fallback_mode_counts'] == {
                'citation_title_only': 1,
            }
            assert protected_activity['support_trace_summary']['trace_count'] == 3
            assert protected_activity['support_trace_summary']['parse_source_counts'] == {
                'bytes': 2,
                'legal_authority': 1,
            }
            assert protected_activity['support_trace_summary']['parse_input_format_counts']['email'] == 1
            assert protected_activity['support_traces'][0]['record_summary']['parse_summary']['quality_tier'] == 'high'
            assert protected_activity['support_traces'][0]['trace_kind'] == 'fact'
            assert protected_activity['support_traces'][0]['graph_id']
            historical_packet = next(
                packet for packet in protected_activity['support_packets']
                if packet['lineage_summary']['content_origin'] == 'historical_archive_capture'
            )
            fallback_packet = next(
                packet for packet in protected_activity['support_packets']
                if packet['lineage_summary']['fallback_mode'] == 'citation_title_only'
            )
            assert historical_packet['source_family'] == 'evidence'
            assert historical_packet['source_record_id'] == 18
            assert historical_packet['record_scope'] == 'evidence'
            assert historical_packet['artifact_family'] == 'archived_web_page'
            assert historical_packet['corpus_family'] == 'web_page'
            assert historical_packet['content_origin'] == 'historical_archive_capture'
            assert historical_packet['source_ref'] == historical_packet['source_lineage_ref']
            assert historical_packet['lineage_summary']['archive_url'] == 'https://web.archive.org/web/20240101120000/https://example.com/evidence'
            assert historical_packet['lineage_summary']['artifact_family'] == 'archived_web_page'
            assert fallback_packet['source_family'] == 'legal_authority'
            assert fallback_packet['record_scope'] == 'legal_authority'
            assert fallback_packet['artifact_family'] == 'legal_authority_reference'
            assert fallback_packet['corpus_family'] == 'legal_authority'
            assert fallback_packet['lineage_summary']['fallback_mode'] == 'citation_title_only'
            assert fallback_packet['lineage_summary']['artifact_family'] == 'legal_authority_reference'
            assert protected_activity['support_packet_summary']['historical_capture_count'] == 2
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_coverage_matrix_support_packets_fall_back_to_provenance_metadata(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 18,
            'cid': 'QmEvidence6',
            'type': 'document',
            'source_url': 'https://example.com/evidence',
            'parse_status': 'parsed',
            'chunk_count': 2,
            'parsed_text_preview': 'Subject: HR complaint\n\nI reported discrimination.',
            'parse_metadata': {
                'source': 'bytes',
                'input_format': 'email',
                'extraction_method': 'email_to_text',
                'quality_tier': 'high',
                'quality_score': 96.0,
                'page_count': 1,
                'source_span': {'char_start': 0, 'char_end': 52, 'text_length': 52, 'raw_size': 64, 'page_count': 1},
                'transform_lineage': {
                    'source': 'bytes',
                    'input_format': 'email',
                    'normalization': 'email_to_text',
                },
            },
            'provenance': {
                'source_url': 'https://web.archive.org/web/20240101120000/https://example.com/evidence',
                'metadata': {
                    'artifact_family': 'archived_web_page',
                    'corpus_family': 'web_page',
                    'content_origin': 'historical_archive_capture',
                    'historical_capture': True,
                    'capture_source': 'archived_domain_scrape',
                    'archive_url': 'https://web.archive.org/web/20240101120000/https://example.com/evidence',
                    'version_of': 'https://example.com/evidence',
                    'captured_at': '2024-01-01T12:00:00Z',
                    'observed_at': '2024-01-02T00:00:00Z',
                },
            },
            'graph_status': 'ready',
            'graph_entity_count': 1,
            'graph_relationship_count': 1,
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-18',
                    'created': True,
                    'reused': False,
                    'metadata': {'lineage': {'status': 'ready'}},
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value={
            'id': 7,
            'citation': '42 U.S.C. § 1983',
            'title': 'Civil Rights Act',
            'url': 'https://example.com/usc/1983',
            'parse_status': 'parsed',
            'chunk_count': 1,
            'parsed_text_preview': 'Civil Rights Act\n\nSection 1983 authorizes relief.',
            'parse_metadata': {
                'source': 'legal_authority',
                'quality_tier': 'high',
                'quality_score': 95.0,
                'page_count': 1,
                'source_span': {'char_start': 0, 'char_end': 48, 'text_length': 48, 'raw_size': 60, 'page_count': 1},
                'transform_lineage': {
                    'source': 'legal_authority',
                    'input_format': 'html',
                    'normalization': 'html_to_text',
                },
            },
            'provenance': {
                'source_url': 'https://example.com/usc/1983',
                'metadata': {
                    'artifact_family': 'legal_authority_reference',
                    'corpus_family': 'legal_authority',
                    'content_origin': 'authority_reference_fallback',
                    'content_source_field': 'citation_title_fallback',
                    'fallback_mode': 'citation_title_only',
                    'input_format': 'html',
                },
            },
            'graph_status': 'ready',
            'graph_entity_count': 1,
            'graph_relationship_count': 1,
            'fact_count': 0,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:authority-7',
                    'created': True,
                    'reused': False,
                    'metadata': {'lineage': {'status': 'ready'}},
                }
            },
            'treatment_summary': {},
            'rule_candidate_summary': {},
        })
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements('testuser', {'employment': ['Protected activity']})
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence6',
                support_label='Archived complaint email',
                source_table='evidence',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Civil Rights Act',
                source_table='legal_authorities',
            )

            matrix = hook.get_claim_coverage_matrix('testuser', 'employment')
            claim_matrix = matrix['claims']['employment']
            protected_activity = claim_matrix['elements'][0]

            assert claim_matrix['support_packet_summary']['historical_capture_count'] == 1
            assert claim_matrix['support_packet_summary']['artifact_family_counts'] == {
                'archived_web_page': 1,
                'legal_authority_reference': 1,
            }
            assert claim_matrix['support_packet_summary']['content_origin_counts'] == {
                'historical_archive_capture': 1,
                'authority_reference_fallback': 1,
            }
            assert claim_matrix['support_packet_summary']['capture_source_counts'] == {
                'archived_domain_scrape': 1,
            }
            assert claim_matrix['support_packet_summary']['fallback_mode_counts'] == {
                'citation_title_only': 1,
            }
            assert claim_matrix['support_packet_summary']['content_source_field_counts'] == {
                'citation_title_fallback': 1,
            }
            historical_packet = next(
                packet for packet in protected_activity['support_packets']
                if packet['lineage_summary']['content_origin'] == 'historical_archive_capture'
            )
            fallback_packet = next(
                packet for packet in protected_activity['support_packets']
                if packet['lineage_summary']['fallback_mode'] == 'citation_title_only'
            )
            assert historical_packet['lineage_summary']['archive_url'] == 'https://web.archive.org/web/20240101120000/https://example.com/evidence'
            assert historical_packet['lineage_summary']['captured_at'] == '2024-01-01T12:00:00Z'
            assert historical_packet['lineage_summary']['artifact_family'] == 'archived_web_page'
            assert fallback_packet['lineage_summary']['content_source_field'] == 'citation_title_fallback'
            assert fallback_packet['lineage_summary']['artifact_family'] == 'legal_authority_reference'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_coverage_matrix_support_trace_summary_falls_back_to_record_parse_summary(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 18,
            'cid': 'QmEvidence6',
            'type': 'document',
            'source_url': 'https://example.com/evidence',
            'parse_status': 'parsed',
            'chunk_count': 1,
            'parsed_text_preview': 'Subject: HR complaint\n\nI reported discrimination.',
            'parse_metadata': {
                'source': 'bytes',
                'input_format': 'email',
                'extraction_method': 'email_to_text',
                'quality_tier': 'high',
                'quality_score': 96.0,
                'page_count': 1,
                'source_span': {'char_start': 0, 'char_end': 52, 'text_length': 52, 'raw_size': 64, 'page_count': 1},
                'transform_lineage': {
                    'source': 'bytes',
                    'input_format': 'email',
                    'normalization': 'email_to_text',
                },
            },
            'provenance': {
                'source_url': 'https://web.archive.org/web/20240101120000/https://example.com/evidence',
                'metadata': {
                    'artifact_family': 'archived_web_page',
                    'content_origin': 'historical_archive_capture',
                },
            },
            'graph_status': 'ready',
            'graph_entity_count': 1,
            'graph_relationship_count': 1,
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-18',
                    'created': True,
                    'reused': False,
                    'metadata': {'lineage': {'status': 'ready'}},
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {
                'fact_id': 'fact:1',
                'text': 'Employee complained to HR.',
                'metadata': {
                    'parse_lineage': {
                        'source': 'bytes',
                    }
                },
            }
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })
        mock_mediator.legal_authority_storage = Mock()
        mock_mediator.legal_authority_storage.get_authority_by_citation = Mock(return_value={
            'id': 7,
            'citation': '42 U.S.C. § 1983',
            'title': 'Civil Rights Act',
            'url': 'https://example.com/usc/1983',
            'parse_status': 'parsed',
            'chunk_count': 1,
            'parsed_text_preview': 'Civil Rights Act\n\nSection 1983 authorizes relief.',
            'parse_metadata': {
                'source': 'legal_authority',
                'input_format': 'html',
                'quality_tier': 'high',
                'quality_score': 95.0,
                'page_count': 1,
                'source_span': {'char_start': 0, 'char_end': 48, 'text_length': 48, 'raw_size': 60, 'page_count': 1},
                'transform_lineage': {
                    'source': 'legal_authority',
                    'input_format': 'html',
                    'normalization': 'html_to_text',
                },
            },
            'provenance': {
                'source_url': 'https://example.com/usc/1983',
                'metadata': {
                    'artifact_family': 'legal_authority_reference',
                    'content_origin': 'authority_reference_fallback',
                    'fallback_mode': 'citation_title_only',
                },
            },
            'graph_status': 'ready',
            'graph_entity_count': 1,
            'graph_relationship_count': 1,
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:authority-7',
                    'created': True,
                    'reused': False,
                    'metadata': {'lineage': {'status': 'ready'}},
                }
            },
            'treatment_summary': {},
            'rule_candidate_summary': {},
        })
        mock_mediator.legal_authority_storage.get_authority_facts = Mock(return_value=[
            {
                'fact_id': 'fact:a',
                'text': 'Section 1983 authorizes relief.',
                'metadata': {
                    'parse_lineage': {
                        'source': 'legal_authority',
                    }
                },
            }
        ])
        mock_mediator.legal_authority_storage.get_authority_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:a'}],
            'relationships': [{'id': 'rel:a'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements('testuser', {'employment': ['Protected activity']})
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidence6',
                support_label='Archived complaint email',
                source_table='evidence',
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='authority',
                support_ref='42 U.S.C. § 1983',
                support_label='Civil Rights Act',
                source_table='legal_authorities',
            )

            matrix = hook.get_claim_coverage_matrix('testuser', 'employment')
            trace_summary = matrix['claims']['employment']['support_trace_summary']

            assert trace_summary['parse_source_counts'] == {
                'bytes': 1,
                'legal_authority': 1,
            }
            assert trace_summary['artifact_family_counts'] == {
                'archived_web_page': 1,
                'legal_authority_reference': 1,
            }
            assert trace_summary['content_origin_counts'] == {
                'historical_archive_capture': 1,
                'authority_reference_fallback': 1,
            }
            assert trace_summary['fallback_mode_counts'] == {
                'citation_title_only': 1,
            }
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_support_traces_returns_fact_and_lineage_rows(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 52,
            'cid': 'QmTrace1',
            'fact_count': 1,
            'parse_metadata': {
                'source': 'web_document',
                'input_format': 'email',
                'quality_tier': 'high',
                'quality_score': 96.0,
                'page_count': 1,
            },
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-52',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {
                'fact_id': 'fact:trace-1',
                'text': 'Employee complained to HR.',
                'confidence': 0.7,
                'metadata': {
                    'parse_lineage': {
                        'source': 'bytes',
                        'parser_version': 'documents-adapter:1',
                    }
                },
            }
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements('testuser', {'employment': ['Protected activity']})
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmTrace1',
                support_label='HR complaint email',
                source_table='evidence',
            )

            traces = hook.get_claim_support_traces(
                'testuser',
                'employment',
                claim_element_text='Protected activity',
            )

            assert len(traces) == 1
            assert traces[0]['fact_id'] == 'fact:trace-1'
            assert traces[0]['trace_kind'] == 'fact'
            assert traces[0]['source_family'] == 'evidence'
            assert traces[0]['source_record_id'] == 52
            assert traces[0]['source_ref'] == 'QmTrace1'
            assert traces[0]['record_scope'] == 'evidence'
            assert traces[0]['parse_source'] == 'bytes'
            assert traces[0]['input_format'] == 'email'
            assert traces[0]['quality_tier'] == 'high'
            assert traces[0]['quality_score'] == 96.0
            assert traces[0]['page_count'] == 1
            assert traces[0]['parse_lineage']['source'] == 'bytes'
            assert traces[0]['graph_id'] == 'graph:evidence-52'
            assert traces[0]['record_id'] == 52
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_testimony_records_contribute_to_support_summary_facts_and_traces(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements('testuser', {'employment': ['Protected activity']})
            saved = hook.save_testimony_record(
                'testuser',
                'employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                raw_narrative='Employee reported discrimination to HR.',
                event_date='2026-03-10',
                actor='Employee',
                act='reported discrimination',
                target='HR',
                firsthand_status='firsthand',
                source_confidence=0.85,
                metadata={'source': 'dashboard'},
            )

            summary = hook.summarize_claim_support('testuser', 'employment')
            claim_summary = summary['claims']['employment']
            element = claim_summary['elements'][0]

            assert claim_summary['total_links'] == 1
            assert claim_summary['total_facts'] == 1
            assert claim_summary['support_by_kind'] == {'testimony': 1}
            assert element['fact_count'] == 1
            assert element['support_by_kind'] == {'testimony': 1}
            assert element['links'][0]['source_table'] == 'claim_testimony'
            assert element['links'][0]['testimony_record_id'] == saved['record_id']

            facts = hook.get_claim_support_facts(
                'testuser',
                'employment',
                claim_element_text='Protected activity',
            )

            assert len(facts) == 1
            assert facts[0]['support_kind'] == 'testimony'
            assert facts[0]['source_table'] == 'claim_testimony'
            assert facts[0]['source_family'] == 'claim_testimony'
            assert facts[0]['source_record_id'] == saved['record_id']
            assert facts[0]['source_ref'] == saved['testimony_id']
            assert facts[0]['record_scope'] == 'claim_testimony'
            assert facts[0]['artifact_family'] == 'testimony_statement'
            assert facts[0]['corpus_family'] == 'claim_testimony'
            assert facts[0]['content_origin'] == 'operator_testimony_intake'
            assert facts[0]['parse_source'] == 'claim_testimony'
            assert facts[0]['input_format'] == 'structured_testimony'
            assert facts[0]['quality_tier'] == 'high'
            assert facts[0]['testimony_record_id'] == saved['record_id']
            assert facts[0]['text'] == 'Employee reported discrimination to HR.'

            traces = hook.get_claim_support_traces(
                'testuser',
                'employment',
                claim_element_text='Protected activity',
            )

            assert len(traces) == 1
            assert traces[0]['trace_kind'] == 'fact'
            assert traces[0]['source_family'] == 'claim_testimony'
            assert traces[0]['source_record_id'] == saved['record_id']
            assert traces[0]['source_ref'] == saved['testimony_id']
            assert traces[0]['record_scope'] == 'claim_testimony'
            assert traces[0]['parse_source'] == 'claim_testimony'
            assert traces[0]['input_format'] == 'structured_testimony'
            assert traces[0]['quality_tier'] == 'high'
            assert traces[0]['record_id'] == saved['record_id']
            assert traces[0]['testimony_record_id'] == saved['record_id']
            assert traces[0]['graph_summary']['status'] == 'not_available'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_contradiction_candidates_detects_testimony_conflicts(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 61,
            'cid': 'QmEvidenceConflict2',
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-61',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:pos-2', 'text': 'Discrimination complaint email to HR exists.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements('testuser', {'employment': ['Protected activity']})
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceConflict2',
                support_label='HR complaint email',
                source_table='evidence',
            )
            hook.save_testimony_record(
                'testuser',
                'employment',
                claim_element_id='employment:1',
                claim_element_text='Protected activity',
                raw_narrative='Discrimination complaint email to HR does not exist.',
                firsthand_status='firsthand',
                source_confidence=0.9,
                metadata={'source': 'dashboard'},
            )

            contradictions = hook.get_claim_contradiction_candidates('testuser', 'employment')
            candidate = contradictions['claims']['employment']['candidates'][0]

            assert contradictions['claims']['employment']['candidate_count'] == 1
            assert sorted(candidate['support_kinds']) == ['evidence', 'testimony']
            assert sorted(candidate['source_tables']) == ['claim_testimony', 'evidence']
            assert sorted(candidate['polarity']) == ['affirmative', 'negative']
            assert 'complaint' in candidate['overlap_terms']
            assert candidate['graph_trace_summary']['traced_link_count'] == 2
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_claim_testimony_records_persist_and_summarize(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.get_three_phase_status = Mock(return_value=_confirmed_intake_status(
            note='ready for claim testimony persistence',
        ))

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            saved = hook.save_testimony_record(
                'testuser',
                'employment discrimination',
                claim_element_id='employment_discrimination:1',
                claim_element_text='Protected activity',
                raw_narrative='I reported discrimination to HR and my supervisor reduced my shifts two days later.',
                event_date='2026-03-10',
                actor='Supervisor',
                act='reduced shifts',
                target='work schedule',
                harm='lost pay',
                firsthand_status='firsthand',
                source_confidence=0.9,
                metadata={'source': 'dashboard'},
            )

            assert saved['recorded'] is True
            assert saved['testimony_id'].startswith('testimony:employment_discrimination:')

            records = hook.get_claim_testimony_records('testuser', 'employment discrimination')

            assert records['available'] is True
            assert records['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T19:00:00+00:00',
                    'confirmation_note': 'ready for claim testimony persistence',
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
            assert len(records['claims']['employment discrimination']) == 1
            record = records['claims']['employment discrimination'][0]
            assert record['claim_element_id'] == 'employment_discrimination:1'
            assert record['claim_element_text'] == 'Protected activity'
            assert record['actor'] == 'Supervisor'
            assert record['harm'] == 'lost pay'
            assert record['metadata']['source'] == 'dashboard'
            assert record['metadata']['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T19:00:00+00:00',
                    'confirmation_note': 'ready for claim testimony persistence',
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
            assert records['summary']['employment discrimination']['record_count'] == 1
            assert records['summary']['employment discrimination']['linked_element_count'] == 1
            assert records['summary']['employment discrimination']['firsthand_status_counts'] == {
                'firsthand': 1,
            }
            assert records['summary']['employment discrimination']['confidence_bucket_counts'] == {
                'high': 1,
            }
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_claim_support_read_payloads_surface_confirmed_intake_handoff(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()
        mock_mediator.get_three_phase_status = Mock(return_value=_confirmed_intake_status(
            note='ready for claim support read payloads',
        ))
        mock_mediator.evidence_state = Mock()
        mock_mediator.evidence_state.get_evidence_by_cid = Mock(return_value={
            'id': 21,
            'fact_count': 1,
            'graph_metadata': {
                'graph_snapshot': {
                    'graph_id': 'graph:evidence-21',
                    'created': True,
                    'reused': False,
                }
            },
        })
        mock_mediator.evidence_state.get_evidence_facts = Mock(return_value=[
            {'fact_id': 'fact:1', 'text': 'Employee complained to HR about discrimination.'},
        ])
        mock_mediator.evidence_state.get_evidence_graph = Mock(return_value={
            'status': 'ready',
            'entities': [{'id': 'entity:1'}],
            'relationships': [{'id': 'rel:1'}],
        })

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'employment': ['Protected activity']},
            )
            hook.add_support_link(
                user_id='testuser',
                claim_type='employment',
                claim_element_text='Protected activity',
                support_kind='evidence',
                support_ref='QmEvidenceGap',
                support_label='HR complaint email',
                source_table='evidence',
            )

            overview = hook.get_claim_overview('testuser', 'employment')
            matrix = hook.get_claim_coverage_matrix('testuser', 'employment')
            gaps = hook.get_claim_support_gaps('testuser', 'employment')
            validation = hook.get_claim_support_validation('testuser', 'employment')
            contradictions = hook.get_claim_contradiction_candidates('testuser', 'employment')

            expected_handoff = {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T19:00:00+00:00',
                    'confirmation_note': 'ready for claim support read payloads',
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

            assert overview['intake_summary_handoff'] == expected_handoff
            assert matrix['intake_summary_handoff'] == expected_handoff
            assert gaps['intake_summary_handoff'] == expected_handoff
            assert validation['intake_summary_handoff'] == expected_handoff
            assert contradictions['intake_summary_handoff'] == expected_handoff
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_save_testimony_record_resolves_text_only_claim_element_to_registered_id(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'retaliation': ['Protected activity', 'Adverse action']},
            )

            saved = hook.save_testimony_record(
                'testuser',
                'retaliation',
                claim_element_text='Protected activity',
                raw_narrative='The HR complaint email does not exist.',
                firsthand_status='firsthand',
                source_confidence=0.92,
                metadata={'source': 'dashboard'},
            )

            records = hook.get_claim_testimony_records('testuser', 'retaliation')
            record = records['claims']['retaliation'][0]

            assert saved['recorded'] is True
            assert saved['claim_element_id'] == 'retaliation:1'
            assert saved['claim_element_text'] == 'Protected activity'
            assert record['claim_element_id'] == 'retaliation:1'
            assert record['claim_element_text'] == 'Protected activity'
            assert records['summary']['retaliation']['linked_element_count'] == 1
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_claim_testimony_records_backfills_legacy_unlinked_rows(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'retaliation': ['Protected activity', 'Adverse action']},
            )

            conn = duckdb.connect(db_path)
            conn.execute(
                """
                INSERT INTO claim_testimony (
                    testimony_id,
                    user_id,
                    claim_type,
                    claim_element_id,
                    claim_element_text,
                    raw_narrative,
                    firsthand_status,
                    source_confidence,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    'testimony:retaliation:legacy',
                    'testuser',
                    'retaliation',
                    None,
                    'Protected activity',
                    'The HR complaint email does not exist.',
                    'firsthand',
                    0.92,
                    json.dumps({'source': 'legacy'}),
                ],
            )
            conn.close()

            records = hook.get_claim_testimony_records('testuser', 'retaliation')
            record = records['claims']['retaliation'][0]

            assert record['claim_element_id'] == 'retaliation:1'
            assert record['claim_element_text'] == 'Protected activity'
            assert records['summary']['retaliation']['linked_element_count'] == 1

            conn = duckdb.connect(db_path)
            persisted = conn.execute(
                "SELECT claim_element_id, claim_element_text FROM claim_testimony WHERE testimony_id = ?",
                ['testimony:retaliation:legacy'],
            ).fetchone()
            conn.close()

            assert persisted[0] == 'retaliation:1'
            assert persisted[1] == 'Protected activity'
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_backfill_claim_testimony_links_updates_legacy_rows_proactively(self):
        try:
            from mediator.claim_support_hooks import ClaimSupportHook
        except ImportError as e:
            pytest.skip(f"ClaimSupportHook requires dependencies: {e}")

        mock_mediator = Mock()
        mock_mediator.log = Mock()

        with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
            db_path = f.name

        try:
            hook = ClaimSupportHook(mock_mediator, db_path=db_path)
            hook.register_claim_requirements(
                'testuser',
                {'retaliation': ['Protected activity', 'Adverse action']},
            )

            conn = duckdb.connect(db_path)
            conn.execute(
                """
                INSERT INTO claim_testimony (
                    testimony_id,
                    user_id,
                    claim_type,
                    claim_element_id,
                    claim_element_text,
                    raw_narrative,
                    firsthand_status,
                    source_confidence,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    'testimony:retaliation:legacy-proactive',
                    'testuser',
                    'retaliation',
                    None,
                    'Protected activity',
                    'Discrimination complaint email to HR does not exist.',
                    'firsthand',
                    0.9,
                    json.dumps({'source': 'legacy-proactive'}),
                    'testimony:retaliation:legacy-unmatched',
                    'testuser',
                    'retaliation',
                    None,
                    'Unknown element',
                    'A narrative that does not match a registered element.',
                    'firsthand',
                    0.6,
                    json.dumps({'source': 'legacy-unmatched'}),
                ],
            )
            conn.close()

            dry_run = hook.backfill_claim_testimony_links('testuser', 'retaliation', dry_run=True)
            assert dry_run['scanned_count'] == 2
            assert dry_run['candidate_count'] == 1
            assert dry_run['updated_count'] == 0
            assert dry_run['records'][0]['claim_element_id'] == 'retaliation:1'

            result = hook.backfill_claim_testimony_links('testuser', 'retaliation')
            assert result['scanned_count'] == 2
            assert result['candidate_count'] == 1
            assert result['updated_count'] == 1
            assert result['records'][0]['testimony_id'] == 'testimony:retaliation:legacy-proactive'

            conn = duckdb.connect(db_path)
            persisted = conn.execute(
                "SELECT testimony_id, claim_element_id, claim_element_text FROM claim_testimony ORDER BY testimony_id"
            ).fetchall()
            conn.close()

            assert persisted == [
                ('testimony:retaliation:legacy-proactive', 'retaliation:1', 'Protected activity'),
                ('testimony:retaliation:legacy-unmatched', None, 'Unknown element'),
            ]
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
