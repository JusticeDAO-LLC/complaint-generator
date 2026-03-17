"""
Unit tests for the mediator module

Note: Some tests require backend dependencies. Tests will skip if dependencies are missing.
"""
import os
import tempfile

import pytest
from unittest.mock import Mock, MagicMock, patch


def _make_graph_support_result(
    *,
    fact_id='fact:1',
    score=1.0,
    matched_claim_element=True,
    source_family='evidence',
    source_record_id='record:1',
    support_ref='support:1',
    source_ref='artifact:1',
    record_scope='evidence',
    artifact_family='archived_web_page',
    corpus_family='web_page',
    content_origin='archived_web_page',
    parse_source='document_parse_pipeline',
    input_format='text/html',
    quality_tier='high',
    quality_score=0.92,
):
    return {
        'fact_id': fact_id,
        'score': score,
        'matched_claim_element': matched_claim_element,
        'source_family': source_family,
        'source_record_id': source_record_id,
        'support_ref': support_ref,
        'source_ref': source_ref,
        'record_scope': record_scope,
        'artifact_family': artifact_family,
        'corpus_family': corpus_family,
        'content_origin': content_origin,
        'parse_source': parse_source,
        'input_format': input_format,
        'quality_tier': quality_tier,
        'quality_score': quality_score,
    }


def _make_graph_support_payload(
    *,
    total_fact_count=0,
    unique_fact_count=0,
    duplicate_fact_count=0,
    semantic_cluster_count=0,
    semantic_duplicate_count=0,
    max_score=0.0,
    results=None,
):
    return {
        'summary': {
            'total_fact_count': total_fact_count,
            'unique_fact_count': unique_fact_count,
            'duplicate_fact_count': duplicate_fact_count,
            'semantic_cluster_count': semantic_cluster_count,
            'semantic_duplicate_count': semantic_duplicate_count,
            'max_score': max_score,
        },
        'results': [] if results is None else results,
    }


class TestMediatorBasics:
    """Basic test cases for Mediator functionality"""
    
    def test_mediator_module_exists(self):
        """Test that the mediator module exists"""
        try:
            from mediator import mediator
            assert mediator is not None
        except ImportError as e:
            pytest.skip(f"Mediator module has dependency issues: {e}")


class TestMediatorWithMocks:
    """Test cases for Mediator with mocked dependencies"""
    
    def test_mediator_can_be_instantiated_with_backend(self):
        """Test that mediator can be created with a mock backend"""
        try:
            from mediator import Mediator
            
            # Create mock backend
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mock_backend.return_value = 'Test response'
            
            # Create mediator
            mediator = Mediator(backends=[mock_backend])
            
            # Verify initialization
            assert mediator.backends == [mock_backend]
            assert mediator.inquiries is not None
            assert mediator.complaint is not None
            assert mediator.state is not None
        except ImportError as e:
            pytest.skip(f"Mediator class has dependency issues: {e}")

    def test_mediator_logs_canonical_ipfs_adapter_startup_payload(self):
        """Mediator startup should log the canonical adapter capability payload without rebuilding it inline."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'

            startup_payload = {
                'capability_report': {
                    'status': 'degraded',
                    'available_count': 1,
                    'degraded_count': 1,
                    'available_capabilities': ['documents'],
                    'degraded_capabilities': {'logic_tools': 'missing dependency'},
                    'capabilities': {
                        'documents': {
                            'status': 'available',
                            'available': True,
                            'module_path': 'ipfs_datasets_py.processors',
                            'provider': 'ipfs_datasets_py',
                            'degraded_reason': None,
                            'details': {'capability': 'documents', 'error_type': ''},
                        },
                        'logic_tools': {
                            'status': 'degraded',
                            'available': False,
                            'module_path': 'ipfs_datasets_py.logic',
                            'provider': 'ipfs_datasets_py',
                            'degraded_reason': 'missing dependency',
                            'details': {'capability': 'logic_tools', 'error_type': 'ModuleNotFoundError'},
                        },
                    },
                },
                'capabilities': {
                    'documents': {
                        'status': 'available',
                        'available': True,
                        'module_path': 'ipfs_datasets_py.processors',
                        'provider': 'ipfs_datasets_py',
                        'degraded_reason': None,
                        'details': {'capability': 'documents', 'error_type': ''},
                    },
                    'logic_tools': {
                        'status': 'degraded',
                        'available': False,
                        'module_path': 'ipfs_datasets_py.logic',
                        'provider': 'ipfs_datasets_py',
                        'degraded_reason': 'missing dependency',
                        'details': {'capability': 'logic_tools', 'error_type': 'ModuleNotFoundError'},
                    },
                },
            }

            with patch('mediator.mediator.summarize_ipfs_datasets_startup_payload', return_value=startup_payload):
                mediator = Mediator(backends=[mock_backend])

            startup_log = next(
                entry for entry in mediator.state.log
                if entry.get('type') == 'ipfs_datasets_capabilities'
            )
            assert startup_log['capability_report'] == startup_payload['capability_report']
            assert startup_log['capabilities'] == startup_payload['capabilities']
        except ImportError as e:
            pytest.skip(f"Mediator class has dependency issues: {e}")
        
    def test_mediator_reset(self):
        """Test that reset creates new state"""
        try:
            from mediator import Mediator
            from mediator.state import State
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            
            old_state = mediator.state
            mediator.reset()
            assert mediator.state is not old_state
            assert isinstance(mediator.state, State)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
        
    def test_mediator_get_state(self):
        """Test that get_state returns serialized state"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            
            state = mediator.get_state()
            assert isinstance(state, dict)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_get_claim_graph_facts_returns_fact_backed_graph_bundle(self):
        """Mediator should expose persisted support facts together with graph-support ranking metadata."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.phase_manager = Mock()
            mediator.phase_manager.get_phase_data = Mock(return_value=Mock(
                entities=['entity:1'],
                relationships=['rel:1', 'rel:2'],
            ))

            support_facts = [
                {
                    'fact_id': 'fact:1',
                    'support_kind': 'evidence',
                    'source_family': 'evidence',
                },
                {
                    'fact_id': 'fact:2',
                    'support_kind': 'authority',
                    'source_family': 'legal_authority',
                },
                {
                    'fact_id': 'fact:3',
                    'support_kind': 'evidence',
                    'source_family': 'evidence',
                },
            ]
            mediator.claim_support.get_claim_element_summary = Mock(return_value={
                'element_id': 'employment:1',
                'element_text': 'Protected activity',
            })
            mediator.claim_support.get_claim_support_facts = Mock(return_value=support_facts)

            graph_payload = _make_graph_support_payload(
                total_fact_count=3,
                unique_fact_count=3,
                duplicate_fact_count=0,
                semantic_cluster_count=2,
                semantic_duplicate_count=0,
                max_score=2.1,
                results=[_make_graph_support_result(fact_id='fact:1', score=2.1)],
            )

            with patch('mediator.mediator.query_graph_support', return_value=graph_payload) as query_mock:
                result = mediator.get_claim_graph_facts(
                    claim_type='employment',
                    claim_element='Protected activity',
                    user_id='testuser',
                    max_results=5,
                )

            assert result['claim_type'] == 'employment'
            assert result['claim_element_id'] == 'employment:1'
            assert result['claim_element'] == 'Protected activity'
            assert result['exists'] is True
            assert result['support_facts'] == support_facts
            assert result['total_facts'] == 3
            assert result['support_by_kind'] == {'evidence': 2, 'authority': 1}
            assert result['support_by_source_family'] == {'evidence': 2, 'legal_authority': 1}
            assert result['graph_support']['summary']['total_fact_count'] == 3
            assert result['graph_support']['graph_context'] == {
                'knowledge_graph_available': True,
                'entity_count': 1,
                'relationship_count': 2,
            }

            query_mock.assert_called_once_with(
                'employment:1',
                graph_id='intake-knowledge-graph',
                support_facts=support_facts,
                claim_type='employment',
                claim_element_text='Protected activity',
                max_results=5,
            )
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_uses_manual_review_for_reasoning_gaps(self):
        """Reasoning-only validation gaps should create manual-review tasks instead of suppressed retrieval."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['evidence'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'covered',
                                'validation_status': 'incomplete',
                                'recommended_action': 'review_existing_support',
                                'support_by_kind': {'evidence': 1},
                                'proof_gap_count': 2,
                                'proof_gaps': [
                                    {'gap_type': 'logic_unprovable'},
                                    {'gap_type': 'ontology_validation_failed'},
                                ],
                                'proof_decision_trace': {
                                    'decision_source': 'logic_unprovable',
                                    'logic_provable_count': 0,
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
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload(
                total_fact_count=6,
                unique_fact_count=2,
                duplicate_fact_count=4,
                semantic_cluster_count=2,
                semantic_duplicate_count=4,
                max_score=2.5,
                results=[_make_graph_support_result(score=2.5)],
            ))

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['evidence'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['execution_mode'] == 'manual_review'
            assert task['follow_up_focus'] == 'reasoning_gap_closure'
            assert task['query_strategy'] == 'reasoning_gap_targeted'
            assert task['priority'] == 'high'
            assert task['should_suppress_retrieval'] is False
            assert task['recommended_action'] == 'review_existing_support'
            assert task['missing_support_kinds'] == []
            assert task['proof_decision_source'] == 'logic_unprovable'
            assert task['ontology_validation_signal'] == 'invalid'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_uses_reasoning_targeted_queries_when_support_missing(self):
        """Reasoning-backed incomplete elements with missing support should use reasoning-targeted retrieval queries."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
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
                                'proof_gap_count': 1,
                                'proof_gaps': [
                                    {'gap_type': 'logic_unprovable'},
                                ],
                                'proof_decision_trace': {
                                    'decision_source': 'logic_proof_partial',
                                    'logic_provable_count': 1,
                                    'logic_unprovable_count': 1,
                                    'ontology_validation_signal': 'valid',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 3,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.legal_authority_search.build_search_programs = Mock(return_value=[
                {
                    'program_id': 'legal_search_program:reasoning-1',
                    'program_type': 'fact_pattern_search',
                    'claim_type': 'employment',
                    'authority_intent': 'support',
                    'query_text': 'employment Protected activity fact pattern application authority',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                }
            ])

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['evidence', 'authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['execution_mode'] == 'review_and_retrieve'
            assert task['follow_up_focus'] == 'reasoning_gap_closure'
            assert task['query_strategy'] == 'reasoning_gap_targeted'
            assert task['priority'] == 'high'
            assert task['missing_support_kinds'] == ['authority']
            assert task['queries']['authority'][0] == '"employment" "Protected activity" formal proof case law logic unprovable'
            assert task['authority_search_program_summary'] == {
                'program_count': 1,
                'program_type_counts': {'fact_pattern_search': 1},
                'authority_intent_counts': {'support': 1},
                'primary_program_id': 'legal_search_program:reasoning-1',
                'primary_program_type': 'fact_pattern_search',
                'primary_program_bias': '',
                'primary_program_rule_bias': '',
            }
            assert task['authority_search_programs'][0]['metadata']['follow_up_focus'] == 'reasoning_gap_closure'
            assert task['authority_search_programs'][0]['metadata']['query_strategy'] == 'reasoning_gap_targeted'
            assert task['recommended_action'] == 'retrieve_more_support'
            assert task['proof_decision_source'] == 'logic_proof_partial'
            assert task['logic_provable_count'] == 1
            assert task['logic_unprovable_count'] == 1
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_inherits_alignment_task_preferences(self):
        """Follow-up planning should inherit preferred support lane and query hints from evidence-phase alignment tasks."""
        try:
            from mediator import Mediator
            from complaint_phases import ComplaintPhase

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['evidence', 'authority'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'missing',
                                'validation_status': 'incomplete',
                                'recommended_action': 'collect_initial_support',
                                'support_by_kind': {},
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {
                                    'decision_source': 'missing_support',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 0,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 0,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.EVIDENCE,
                'alignment_evidence_tasks',
                [
                    {
                        'claim_type': 'employment',
                        'claim_element_id': 'employment:1',
                        'preferred_support_kind': 'authority',
                        'preferred_evidence_classes': ['policy'],
                        'missing_fact_bundle': ['who received the complaint'],
                        'recommended_queries': ['"employment" "Protected activity" official policy complaint channel'],
                        'success_criteria': ['Element Protected activity reaches supported status'],
                        'intake_origin_refs': ['open_item:element:employment:1'],
                    }
                ],
            )
            mediator.legal_authority_search.build_search_programs = Mock(return_value=[])

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['evidence', 'authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['preferred_support_kind'] == 'authority'
            assert task['preferred_evidence_classes'] == ['policy']
            assert task['missing_fact_bundle'] == ['who received the complaint']
            assert task['success_criteria'] == ['Element Protected activity reaches supported status']
            assert task['intake_origin_refs'] == ['open_item:element:employment:1']
            assert task['queries']['authority'][0] == '"employment" "Protected activity" official policy complaint channel'
            assert task['queries']['authority'][1] == '"employment" "Protected activity" "who received the complaint" statute'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_uses_rule_candidate_queries_for_fact_gaps(self):
        """When the law is already structured into rule candidates, evidence retrieval should target those predicates and exceptions."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
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
                                'recommended_action': 'collect_fact_support',
                                'support_by_kind': {'authority': 1},
                                'authority_treatment_summary': {
                                    'authority_link_count': 1,
                                    'adverse_authority_link_count': 0,
                                },
                                'authority_rule_candidate_summary': {
                                    'authority_link_count': 1,
                                    'authority_links_with_rule_candidates': 1,
                                    'total_rule_candidate_count': 2,
                                    'matched_claim_element_rule_count': 2,
                                    'rule_type_counts': {
                                        'element': 1,
                                        'exception': 1,
                                    },
                                    'max_extraction_confidence': 0.78,
                                },
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {
                                    'decision_source': 'partial_support',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 0,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 0,
                                },
                                'gap_context': {
                                    'links': [
                                        {
                                            'support_kind': 'authority',
                                            'support_ref': '42 U.S.C. 2000e-3(a)',
                                            'rule_candidates': [
                                                {
                                                    'rule_id': 'rule:1',
                                                    'rule_text': 'Protected activity must precede the employer response.',
                                                    'rule_type': 'element',
                                                    'claim_element_id': 'employment:1',
                                                    'claim_element_text': 'Protected activity',
                                                    'extraction_confidence': 0.78,
                                                },
                                                {
                                                    'rule_id': 'rule:2',
                                                    'rule_text': 'Except where the employer lacked notice liability may not attach.',
                                                    'rule_type': 'exception',
                                                    'claim_element_id': 'employment:1',
                                                    'claim_element_text': 'Protected activity',
                                                    'extraction_confidence': 0.74,
                                                },
                                            ],
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['evidence', 'authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['execution_mode'] == 'retrieve_support'
            assert task['follow_up_focus'] == 'fact_gap_closure'
            assert task['query_strategy'] == 'rule_fact_targeted'
            assert task['recommended_action'] == 'collect_fact_support'
            assert task['missing_support_kinds'] == ['evidence']
            assert task['queries']['evidence'][0] == '"employment" "Protected activity" "Protected activity must precede the employer response." supporting facts evidence'
            assert task['queries']['evidence'][1] == '"Protected activity" "Except where the employer lacked notice liability may not attach." fact pattern records witness timeline employment'
            assert task['rule_candidate_context']['top_rule_types'] == ['element', 'exception']
            assert task['rule_candidate_context']['top_rule_texts'][0] == 'Protected activity must precede the employer response.'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_biases_authority_programs_for_uncertain_treatment(self):
        """Uncertain treatment signals should prioritize good-law checking ahead of ordinary support searches."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['authority'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'partially_supported',
                                'validation_status': 'incomplete',
                                'recommended_action': 'retrieve_more_support',
                                'support_by_kind': {},
                                'authority_treatment_summary': {
                                    'authority_link_count': 1,
                                    'treated_authority_link_count': 1,
                                    'supportive_authority_link_count': 0,
                                    'adverse_authority_link_count': 0,
                                    'uncertain_authority_link_count': 1,
                                    'treatment_type_counts': {'questioned': 1},
                                    'max_treatment_confidence': 0.63,
                                },
                                'proof_gap_count': 1,
                                'proof_gaps': [{'gap_type': 'logic_unprovable'}],
                                'proof_decision_trace': {
                                    'decision_source': 'logic_proof_partial',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 1,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 2,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.legal_authority_search.build_search_programs = Mock(return_value=[
                {
                    'program_id': 'legal_search_program:fact-1',
                    'program_type': 'fact_pattern_search',
                    'claim_type': 'employment',
                    'authority_intent': 'support',
                    'query_text': 'employment Protected activity fact pattern application authority',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
                {
                    'program_id': 'legal_search_program:treatment-1',
                    'program_type': 'treatment_check_search',
                    'claim_type': 'employment',
                    'authority_intent': 'confirm_good_law',
                    'query_text': 'employment Protected activity citation history later treatment good law',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
                {
                    'program_id': 'legal_search_program:adverse-1',
                    'program_type': 'adverse_authority_search',
                    'claim_type': 'employment',
                    'authority_intent': 'oppose',
                    'query_text': 'employment Protected activity adverse authority defense exception limitation',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
            ])

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['follow_up_focus'] == 'reasoning_gap_closure'
            assert task['authority_search_program_summary']['primary_program_type'] == 'treatment_check_search'
            assert task['authority_search_program_summary']['primary_program_bias'] == 'uncertain'
            assert task['authority_search_program_summary']['primary_program_rule_bias'] == ''
            assert [program['program_type'] for program in task['authority_search_programs'][:2]] == [
                'treatment_check_search',
                'adverse_authority_search',
            ]
            assert task['authority_search_programs'][0]['metadata']['authority_signal_bias'] == 'uncertain'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_uses_manual_review_for_adverse_authority(self):
        """Adverse authority signals should stay review-first and preserve treatment context in planner metadata."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['authority'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'covered',
                                'validation_status': 'incomplete',
                                'recommended_action': 'review_adverse_authority',
                                'support_by_kind': {'authority': 1},
                                'authority_treatment_summary': {
                                    'authority_link_count': 1,
                                    'treated_authority_link_count': 1,
                                    'supportive_authority_link_count': 0,
                                    'adverse_authority_link_count': 1,
                                    'uncertain_authority_link_count': 0,
                                    'treatment_type_counts': {'questioned': 1},
                                    'max_treatment_confidence': 0.81,
                                },
                                'authority_rule_candidate_summary': {
                                    'authority_link_count': 1,
                                    'authority_links_with_rule_candidates': 1,
                                    'total_rule_candidate_count': 1,
                                    'matched_claim_element_rule_count': 1,
                                    'rule_type_counts': {'element': 1},
                                    'max_extraction_confidence': 0.66,
                                },
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {
                                    'decision_source': 'heuristic_support_only',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 0,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 0,
                                },
                                'gap_context': {
                                    'links': [
                                        {
                                            'support_kind': 'authority',
                                            'support_ref': 'Smith v. Example',
                                            'rule_candidates': [
                                                {
                                                    'rule_id': 'rule:adverse',
                                                    'rule_text': 'Protected activity can support retaliation claims.',
                                                    'rule_type': 'element',
                                                    'claim_element_id': 'employment:1',
                                                    'claim_element_text': 'Protected activity',
                                                    'extraction_confidence': 0.66,
                                                }
                                            ],
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload(
                total_fact_count=4,
                unique_fact_count=2,
                duplicate_fact_count=2,
                semantic_cluster_count=2,
                semantic_duplicate_count=2,
                max_score=2.2,
                results=[_make_graph_support_result(score=2.2)],
            ))

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['execution_mode'] == 'manual_review'
            assert task['follow_up_focus'] == 'adverse_authority_review'
            assert task['query_strategy'] == 'adverse_authority_targeted'
            assert task['priority'] == 'high'
            assert task['should_suppress_retrieval'] is False
            assert task['recommended_action'] == 'review_adverse_authority'
            assert task['authority_treatment_summary']['adverse_authority_link_count'] == 1

            mediator.execute_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                support_kind='authority',
                max_tasks_per_claim=1,
            )
            recorded_call = mediator.claim_support.record_follow_up_execution.call_args
            assert recorded_call.kwargs['metadata']['skip_reason'] == 'adverse_authority_requires_review'
            assert recorded_call.kwargs['metadata']['authority_treatment_summary']['adverse_authority_link_count'] == 1
            assert recorded_call.kwargs['metadata']['rule_candidate_focus']['top_rule_types'] == ['element']
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_biases_authority_programs_for_adverse_treatment(self):
        """Adverse treatment signals should make adverse-authority review programs primary within the bundle."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['authority'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'covered',
                                'validation_status': 'incomplete',
                                'recommended_action': 'review_adverse_authority',
                                'support_by_kind': {},
                                'authority_treatment_summary': {
                                    'authority_link_count': 1,
                                    'treated_authority_link_count': 1,
                                    'supportive_authority_link_count': 0,
                                    'adverse_authority_link_count': 1,
                                    'uncertain_authority_link_count': 0,
                                    'treatment_type_counts': {'limits': 1},
                                    'max_treatment_confidence': 0.81,
                                },
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {
                                    'decision_source': 'heuristic_support_only',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 0,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 0,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload(
                total_fact_count=1,
                unique_fact_count=1,
                semantic_cluster_count=1,
                max_score=1.1,
                results=[_make_graph_support_result(score=1.1)],
            ))
            mediator.legal_authority_search.build_search_programs = Mock(return_value=[
                {
                    'program_id': 'legal_search_program:fact-1',
                    'program_type': 'fact_pattern_search',
                    'claim_type': 'employment',
                    'authority_intent': 'support',
                    'query_text': 'employment Protected activity fact pattern application authority',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
                {
                    'program_id': 'legal_search_program:treatment-1',
                    'program_type': 'treatment_check_search',
                    'claim_type': 'employment',
                    'authority_intent': 'confirm_good_law',
                    'query_text': 'employment Protected activity citation history later treatment good law',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
                {
                    'program_id': 'legal_search_program:adverse-1',
                    'program_type': 'adverse_authority_search',
                    'claim_type': 'employment',
                    'authority_intent': 'oppose',
                    'query_text': 'employment Protected activity adverse authority defense exception limitation',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
            ])

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['follow_up_focus'] == 'adverse_authority_review'
            assert task['authority_search_program_summary']['primary_program_type'] == 'adverse_authority_search'
            assert task['authority_search_program_summary']['primary_program_bias'] == 'adverse'
            assert task['authority_search_program_summary']['primary_program_rule_bias'] == ''
            assert [program['program_type'] for program in task['authority_search_programs'][:2]] == [
                'adverse_authority_search',
                'treatment_check_search',
            ]
            assert task['authority_search_programs'][0]['metadata']['authority_signal_bias'] == 'adverse'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_biases_authority_programs_for_exception_rules(self):
        """Exception rule candidates should front-load adverse-authority search even without treatment signals."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['authority'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'partially_supported',
                                'validation_status': 'incomplete',
                                'recommended_action': 'retrieve_more_support',
                                'support_by_kind': {'evidence': 1},
                                'authority_treatment_summary': {
                                    'authority_link_count': 1,
                                    'treated_authority_link_count': 0,
                                    'supportive_authority_link_count': 0,
                                    'adverse_authority_link_count': 0,
                                    'uncertain_authority_link_count': 0,
                                    'treatment_type_counts': {},
                                },
                                'authority_rule_candidate_summary': {
                                    'total_rule_candidate_count': 2,
                                    'matched_claim_element_rule_count': 2,
                                    'rule_type_counts': {'element': 1, 'exception': 1},
                                },
                                'support_by_kind_details': {
                                    'authority': [
                                        {
                                            'support_ref': 'auth:1',
                                            'rule_candidates': [
                                                {
                                                    'rule_id': 'rule:1',
                                                    'rule_text': 'Protected activity must precede the employer response.',
                                                    'rule_type': 'element',
                                                    'claim_element_id': 'employment:1',
                                                    'claim_element_text': 'Protected activity',
                                                    'extraction_confidence': 0.78,
                                                },
                                                {
                                                    'rule_id': 'rule:2',
                                                    'rule_text': 'Except where the employer lacked notice liability may not attach.',
                                                    'rule_type': 'exception',
                                                    'claim_element_id': 'employment:1',
                                                    'claim_element_text': 'Protected activity',
                                                    'extraction_confidence': 0.74,
                                                },
                                            ],
                                        }
                                    ],
                                },
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {
                                    'decision_source': 'partial_support',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 0,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 0,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.legal_authority_search.build_search_programs = Mock(return_value=[
                {
                    'program_id': 'legal_search_program:fact-1',
                    'program_type': 'fact_pattern_search',
                    'claim_type': 'employment',
                    'authority_intent': 'support',
                    'query_text': 'employment Protected activity fact pattern application authority',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
                {
                    'program_id': 'legal_search_program:treatment-1',
                    'program_type': 'treatment_check_search',
                    'claim_type': 'employment',
                    'authority_intent': 'confirm_good_law',
                    'query_text': 'employment Protected activity citation history later treatment good law',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
                {
                    'program_id': 'legal_search_program:adverse-1',
                    'program_type': 'adverse_authority_search',
                    'claim_type': 'employment',
                    'authority_intent': 'oppose',
                    'query_text': 'employment Protected activity adverse authority defense exception limitation',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
            ])

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['authority_search_program_summary']['primary_program_type'] == 'adverse_authority_search'
            assert task['authority_search_program_summary']['primary_program_bias'] == ''
            assert task['authority_search_program_summary']['primary_program_rule_bias'] == 'exception'
            assert [program['program_type'] for program in task['authority_search_programs'][:2]] == [
                'adverse_authority_search',
                'treatment_check_search',
            ]
            assert task['authority_search_programs'][0]['metadata']['rule_signal_bias'] == 'exception'
            assert task['authority_search_programs'][0]['metadata']['rule_candidate_focus_types'] == ['element', 'exception']
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_biases_authority_programs_for_procedural_rules(self):
        """Procedural prerequisite rules should move procedural authority search ahead of fact-pattern support."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['authority'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'incomplete',
                                'validation_status': 'incomplete',
                                'recommended_action': 'retrieve_more_support',
                                'support_by_kind': {},
                                'authority_treatment_summary': {
                                    'authority_link_count': 0,
                                    'treated_authority_link_count': 0,
                                    'supportive_authority_link_count': 0,
                                    'adverse_authority_link_count': 0,
                                    'uncertain_authority_link_count': 0,
                                    'treatment_type_counts': {},
                                },
                                'authority_rule_candidate_summary': {
                                    'total_rule_candidate_count': 1,
                                    'matched_claim_element_rule_count': 1,
                                    'rule_type_counts': {'procedural_prerequisite': 1},
                                },
                                'support_by_kind_details': {
                                    'authority': [
                                        {
                                            'support_ref': 'auth:1',
                                            'rule_candidates': [
                                                {
                                                    'rule_id': 'rule:1',
                                                    'rule_text': 'A retaliation claim requires timely administrative exhaustion before suit.',
                                                    'rule_type': 'procedural_prerequisite',
                                                    'claim_element_id': 'employment:1',
                                                    'claim_element_text': 'Protected activity',
                                                    'extraction_confidence': 0.82,
                                                }
                                            ],
                                        }
                                    ],
                                },
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {
                                    'decision_source': 'missing_support',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 0,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 0,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.legal_authority_search.build_search_programs = Mock(return_value=[
                {
                    'program_id': 'legal_search_program:fact-1',
                    'program_type': 'fact_pattern_search',
                    'claim_type': 'employment',
                    'authority_intent': 'support',
                    'query_text': 'employment Protected activity fact pattern application authority',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['case_law'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
                {
                    'program_id': 'legal_search_program:procedure-1',
                    'program_type': 'procedural_search',
                    'claim_type': 'employment',
                    'authority_intent': 'procedural',
                    'query_text': 'employment Protected activity timeliness exhaustion venue notice procedure',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['regulation'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
                {
                    'program_id': 'legal_search_program:definition-1',
                    'program_type': 'element_definition_search',
                    'claim_type': 'employment',
                    'authority_intent': 'support',
                    'query_text': 'employment Protected activity element definition statute regulation rule',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['statute'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {},
                },
            ])

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['authority_search_program_summary']['primary_program_type'] == 'procedural_search'
            assert task['authority_search_program_summary']['primary_program_bias'] == ''
            assert task['authority_search_program_summary']['primary_program_rule_bias'] == 'procedural_prerequisite'
            assert [program['program_type'] for program in task['authority_search_programs'][:3]] == [
                'procedural_search',
                'element_definition_search',
                'fact_pattern_search',
            ]
            assert task['authority_search_programs'][0]['metadata']['rule_signal_bias'] == 'procedural_prerequisite'
            assert task['authority_search_programs'][0]['metadata']['rule_candidate_focus_types'] == ['procedural_prerequisite']
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_clears_reasoning_markers_after_manual_review_resolution(self):
        """Resolved reasoning-gap review work should downgrade to ordinary retrieval with normalized gap metadata."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {
                    'employment': [
                        {
                            'execution_id': 9,
                            'claim_type': 'employment',
                            'claim_element_id': 'employment:1',
                            'claim_element_text': 'Protected activity',
                            'support_kind': 'manual_review',
                            'status': 'resolved_manual_review',
                            'resolution_status': 'resolved_supported',
                            'timestamp': '2026-03-12T12:00:00',
                        }
                    ]
                }
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
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
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['evidence', 'authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['execution_mode'] == 'retrieve_support'
            assert task['requires_manual_review'] is False
            assert task['manual_review_resolved'] is True
            assert task['follow_up_focus'] == 'support_gap_closure'
            assert task['query_strategy'] == 'standard_gap_targeted'
            assert task['proof_gap_types'] == []
            assert task['proof_gap_count'] == 0
            assert task['proof_decision_source'] == 'partial_support'
            assert task['logic_provable_count'] == 0
            assert task['logic_unprovable_count'] == 0
            assert task['ontology_validation_signal'] == ''
            assert task['resolution_applied'] == 'manual_review_resolved'
            assert task['queries']['authority'][0] == '"employment" "Protected activity" statute'

            mediator.search_legal_authorities = Mock(return_value={'statutes': [], 'cases': []})
            mediator.execute_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                support_kind='authority',
                max_tasks_per_claim=1,
            )
            executed_call = mediator.claim_support.record_follow_up_execution.call_args_list[0]
            assert executed_call.kwargs['metadata']['resolution_applied'] == 'manual_review_resolved'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_uses_quality_targeted_queries_for_low_quality_support(self):
        """Low-quality parsed support should trigger retrieval aimed at better source quality, not generic review-only follow-up."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['evidence'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'covered',
                                'validation_status': 'incomplete',
                                'recommended_action': 'improve_parse_quality',
                                'support_by_kind': {'evidence': 1},
                                'support_trace_summary': {
                                    'parsed_record_count': 1,
                                    'parse_quality_tier_counts': {'empty': 1},
                                    'avg_parse_quality_score': 0.0,
                                },
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {
                                    'decision_source': 'heuristic_support_only',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 0,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 0,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload(
                total_fact_count=3,
                unique_fact_count=1,
                duplicate_fact_count=2,
                semantic_cluster_count=1,
                semantic_duplicate_count=2,
                max_score=2.1,
                results=[_make_graph_support_result(score=2.1)],
            ))

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['evidence'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['execution_mode'] == 'retrieve_support'
            assert task['follow_up_focus'] == 'parse_quality_improvement'
            assert task['query_strategy'] == 'quality_gap_targeted'
            assert task['priority'] == 'high'
            assert task['should_suppress_retrieval'] is False
            assert task['recommended_action'] == 'improve_parse_quality'
            assert task['queries']['evidence'][0] == '"employment" "Protected activity" clearer copy OCR readable evidence'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_follow_up_plan_adapts_reasoning_gap_queries_after_repeated_zero_result_runs(self):
        """Repeated zero-result reasoning-gap retrievals should broaden back to standard queries and reduce urgency."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution.side_effect = [
                {'claims': {'employment': []}},
                {
                    'claims': {
                        'employment': [
                            {
                                'execution_id': 12,
                                'claim_type': 'employment',
                                'claim_element_id': 'employment:1',
                                'claim_element_text': 'Protected activity',
                                'support_kind': 'authority',
                                'status': 'executed',
                                'timestamp': '2026-03-12T11:00:00',
                                'follow_up_focus': 'reasoning_gap_closure',
                                'metadata': {
                                    'follow_up_focus': 'reasoning_gap_closure',
                                    'result_count': 0,
                                    'zero_result': True,
                                },
                            },
                            {
                                'execution_id': 11,
                                'claim_type': 'employment',
                                'claim_element_id': 'employment:1',
                                'claim_element_text': 'Protected activity',
                                'support_kind': 'authority',
                                'status': 'executed',
                                'timestamp': '2026-03-12T10:00:00',
                                'follow_up_focus': 'reasoning_gap_closure',
                                'metadata': {
                                    'follow_up_focus': 'reasoning_gap_closure',
                                    'result_count': 0,
                                    'zero_result': True,
                                },
                            },
                        ]
                    }
                },
            ]
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
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
                                'proof_gap_count': 1,
                                'proof_gaps': [
                                    {'gap_type': 'logic_unprovable'},
                                ],
                                'proof_decision_trace': {
                                    'decision_source': 'logic_proof_partial',
                                    'logic_provable_count': 1,
                                    'logic_unprovable_count': 1,
                                    'ontology_validation_signal': 'valid',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 2,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())

            plan = mediator.get_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['evidence', 'authority'],
            )
            task = plan['claims']['employment']['tasks'][0]

            assert task['execution_mode'] == 'review_and_retrieve'
            assert task['follow_up_focus'] == 'reasoning_gap_closure'
            assert task['query_strategy'] == 'standard_gap_targeted'
            assert task['priority'] == 'medium'
            assert task['queries']['authority'][0] == '"employment" "Protected activity" statute'
            assert task['adaptive_retry_state']['applied'] is True
            assert task['adaptive_retry_state']['reason'] == 'repeated_zero_result_reasoning_gap'
            assert task['adaptive_retry_state']['priority_penalty'] == 1
            assert task['adaptive_retry_state']['adaptive_query_strategy'] == 'standard_gap_targeted'
            assert task['adaptive_retry_state']['zero_result_attempt_count'] == 2
            assert task['adaptive_retry_state']['successful_result_attempt_count'] == 0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_execute_follow_up_plan_records_zero_result_metadata(self):
        """Executed follow-up retrievals should persist normalized zero-result metadata for future adaptive planning."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution.side_effect = [
                {'claims': {'employment': []}},
                {'claims': {'employment': []}},
                {'claims': {'employment': []}},
                {'claims': {'employment': []}},
            ]
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.claim_support.was_follow_up_executed = Mock(return_value=False)
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['evidence'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'missing',
                                'validation_status': 'incomplete',
                                'recommended_action': 'collect_initial_support',
                                'support_by_kind': {},
                                'missing_fact_bundle': ['Who received the complaint'],
                                'satisfied_fact_bundle': [],
                                'proof_gap_count': 1,
                                'proof_gaps': [
                                    {'gap_type': 'logic_unprovable'},
                                ],
                                'proof_decision_trace': {
                                    'decision_source': 'logic_unprovable',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 1,
                                    'ontology_validation_signal': 'valid',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 1,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.discover_web_evidence = Mock(return_value={
                'discovered': 0,
                'stored': 0,
                'total_records': 0,
            })
            mediator.get_claim_overview = Mock(return_value={'claims': {'employment': {}}})
            mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T10:00:00+00:00',
                    'confirmation_note': 'ready for follow-up handoff',
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

            mediator.execute_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                support_kind='evidence',
                max_tasks_per_claim=1,
            )

            executed_call = mediator.claim_support.record_follow_up_execution.call_args_list[0]
            assert executed_call.kwargs['status'] == 'executed'
            assert executed_call.kwargs['query_text'] == '"employment" "Protected activity" supporting evidence formal proof logic unprovable'
            assert executed_call.kwargs['metadata']['result_count'] == 0
            assert executed_call.kwargs['metadata']['stored_result_count'] == 0
            assert executed_call.kwargs['metadata']['zero_result'] is True
            assert executed_call.kwargs['metadata']['follow_up_focus'] == 'reasoning_gap_closure'
            assert executed_call.kwargs['metadata']['missing_fact_bundle'] == ['Who received the complaint']
            assert executed_call.kwargs['metadata']['satisfied_fact_bundle'] == []
            assert executed_call.kwargs['metadata']['primary_missing_fact'] == 'Who received the complaint'
            assert executed_call.kwargs['metadata']['intake_summary_handoff'] == {
                'current_phase': 'intake',
                'ready_to_advance': True,
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T10:00:00+00:00',
                    'confirmation_note': 'ready for follow-up handoff',
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
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_persist_claim_support_diagnostics_stamps_confirmed_intake_handoff_metadata(self):
        """Diagnostic snapshot persistence should carry the confirmed intake handoff provenance when available."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.persist_claim_support_diagnostics = Mock(return_value={'claims': {}})
            mediator.get_three_phase_status = Mock(return_value={
                'current_phase': 'intake',
                'intake_readiness': {
                    'ready_to_advance': True,
                },
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T11:00:00+00:00',
                    'confirmation_note': 'ready for snapshot persistence',
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

            mediator.persist_claim_support_diagnostics(
                claim_type='employment',
                user_id='testuser',
                required_support_kinds=['evidence', 'authority'],
                gaps={'claims': {'employment': {'claim_type': 'employment', 'unresolved_count': 1}}},
                contradictions={'claims': {'employment': {'claim_type': 'employment', 'candidate_count': 0}}},
                metadata={'source': 'unit_test'},
            )

            mediator.claim_support.persist_claim_support_diagnostics.assert_called_once_with(
                'testuser',
                claim_type='employment',
                required_support_kinds=['evidence', 'authority'],
                gaps={'claims': {'employment': {'claim_type': 'employment', 'unresolved_count': 1}}},
                contradictions={'claims': {'employment': {'claim_type': 'employment', 'candidate_count': 0}}},
                metadata={
                    'source': 'unit_test',
                    'intake_summary_handoff': {
                        'current_phase': 'intake',
                        'ready_to_advance': True,
                        'complainant_summary_confirmation': {
                            'status': 'confirmed',
                            'confirmed': True,
                            'confirmed_at': '2026-03-17T11:00:00+00:00',
                            'confirmation_note': 'ready for snapshot persistence',
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
                },
                retention_limit=3,
            )
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_execute_follow_up_plan_persists_authority_search_program_metadata(self):
        """Authority follow-up execution should persist and forward the claim-aware search-program bundle."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={
                'claims': {'employment': []}
            })
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={
                'in_cooldown': False,
            })
            mediator.claim_support.was_follow_up_executed = Mock(return_value=False)
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['authority'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'missing',
                                'validation_status': 'incomplete',
                                'recommended_action': 'collect_initial_support',
                                'support_by_kind': {},
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {
                                    'decision_source': 'missing_support',
                                    'logic_provable_count': 0,
                                    'logic_unprovable_count': 0,
                                    'ontology_validation_signal': 'unknown',
                                },
                                'reasoning_diagnostics': {
                                    'backend_available_count': 0,
                                },
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.legal_authority_search.build_search_programs = Mock(return_value=[
                {
                    'program_id': 'legal_search_program:authority-1',
                    'program_type': 'element_definition_search',
                    'claim_type': 'employment',
                    'authority_intent': 'support',
                    'query_text': 'employment Protected activity element definition statute regulation rule',
                    'claim_element_id': 'employment:1',
                    'claim_element_text': 'Protected activity',
                    'authority_families': ['statute', 'regulation'],
                    'search_terms': ['Protected activity', 'employment'],
                    'metadata': {'rule_signal_bias': 'element'},
                }
            ])
            mediator.search_legal_authorities = Mock(return_value={
                'statutes': [{'citation': '42 U.S.C. § 2000e-3', 'title': 'Retaliation', 'source': 'us_code'}],
                'regulations': [],
                'case_law': [],
                'web_archives': [],
            })
            mediator.store_legal_authorities = Mock(return_value={'total_records': 1})
            mediator.get_claim_overview = Mock(return_value={'claims': {'employment': {}}})

            result = mediator.execute_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                support_kind='authority',
                max_tasks_per_claim=1,
            )

            executed_task = result['claims']['employment']['tasks'][0]
            mediator.search_legal_authorities.assert_called_once_with(
                query='employment Protected activity element definition statute regulation rule',
                claim_type='employment',
                jurisdiction=None,
                search_all=True,
                authority_families=['statute', 'regulation'],
            )
            assert executed_task['executed']['authority']['query'] == 'employment Protected activity element definition statute regulation rule'
            assert executed_task['executed']['authority']['task_query'] == '"employment" "Protected activity" statute'
            assert executed_task['executed']['authority']['selected_search_program_id'] == 'legal_search_program:authority-1'
            assert executed_task['executed']['authority']['selected_search_program_type'] == 'element_definition_search'
            assert executed_task['executed']['authority']['selected_search_program_bias'] == ''
            assert executed_task['executed']['authority']['selected_search_program_rule_bias'] == 'element'
            assert executed_task['executed']['authority']['selected_search_program_families'] == ['statute', 'regulation']
            assert executed_task['executed']['authority']['search_program_summary'] == {
                'program_count': 1,
                'program_type_counts': {'element_definition_search': 1},
                'authority_intent_counts': {'support': 1},
                'primary_program_id': 'legal_search_program:authority-1',
                'primary_program_type': 'element_definition_search',
                'primary_program_bias': '',
                'primary_program_rule_bias': 'element',
            }
            assert executed_task['executed']['authority']['search_programs'][0]['program_id'] == 'legal_search_program:authority-1'
            store_call = mediator.store_legal_authorities.call_args
            assert store_call.kwargs['search_programs'][0]['program_id'] == 'legal_search_program:authority-1'
            recorded_call = mediator.claim_support.record_follow_up_execution.call_args
            assert recorded_call.kwargs['query_text'] == 'employment Protected activity element definition statute regulation rule'
            assert recorded_call.kwargs['metadata']['task_query'] == '"employment" "Protected activity" statute'
            assert recorded_call.kwargs['metadata']['effective_query'] == 'employment Protected activity element definition statute regulation rule'
            assert recorded_call.kwargs['metadata']['selected_search_program_id'] == 'legal_search_program:authority-1'
            assert recorded_call.kwargs['metadata']['selected_search_program_type'] == 'element_definition_search'
            assert recorded_call.kwargs['metadata']['selected_search_program_bias'] == ''
            assert recorded_call.kwargs['metadata']['selected_search_program_rule_bias'] == 'element'
            assert recorded_call.kwargs['metadata']['selected_search_program_families'] == ['statute', 'regulation']
            assert recorded_call.kwargs['metadata']['search_program_ids'] == ['legal_search_program:authority-1']
            assert recorded_call.kwargs['metadata']['search_program_count'] == 1
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_execute_follow_up_plan_respects_alignment_testimony_handoff(self):
        """Follow-up execution should surface awaiting_testimony as a handoff outcome instead of running retrieval lanes."""
        try:
            from mediator import Mediator
            from complaint_phases import ComplaintPhase

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={'claims': {'employment': []}})
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={'in_cooldown': False})
            mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.EVIDENCE,
                'alignment_evidence_tasks',
                [
                    {
                        'claim_type': 'employment',
                        'claim_element_id': 'employment:1',
                        'preferred_support_kind': 'testimony',
                        'resolution_status': 'awaiting_testimony',
                        'intake_proof_leads': [
                            {
                                'lead_id': 'lead:witness:1',
                                'owner': 'complainant',
                                'recommended_support_kind': 'testimony',
                            }
                        ],
                    }
                ],
            )
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['evidence'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'missing',
                                'validation_status': 'missing',
                                'recommended_action': 'collect_initial_support',
                                'support_by_kind': {},
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {},
                                'reasoning_diagnostics': {'backend_available_count': 0},
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.get_claim_overview = Mock(return_value={'claims': {'employment': {}}})

            result = mediator.execute_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                max_tasks_per_claim=1,
            )

            skipped_task = result['claims']['employment']['skipped_tasks'][0]
            assert skipped_task['resolution_applied'] == 'awaiting_testimony'
            assert skipped_task['skipped']['escalation']['reason'] == 'awaiting_testimony_collection'
            mediator.claim_support.record_follow_up_execution.assert_called_once()
            executed_call = mediator.claim_support.record_follow_up_execution.call_args
            assert executed_call.kwargs['support_kind'] == 'testimony'
            assert executed_call.kwargs['status'] == 'skipped_resolution_handoff'
            assert executed_call.kwargs['metadata']['resolution_applied'] == 'awaiting_testimony'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_execute_follow_up_plan_marks_zero_result_runs_as_insufficient_support(self):
        """When all attempted follow-up lanes return zero results, execution should end in insufficient_support_after_search."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])
            mediator.state.username = 'testuser'
            mediator.claim_support = Mock()
            mediator.claim_support.get_recent_follow_up_execution = Mock(return_value={'claims': {'employment': []}})
            mediator.claim_support.get_follow_up_execution_status = Mock(return_value={'in_cooldown': False})
            mediator.claim_support.was_follow_up_executed = Mock(return_value=False)
            mediator.get_claim_support_validation = Mock(return_value={
                'claims': {
                    'employment': {
                        'required_support_kinds': ['evidence'],
                        'elements': [
                            {
                                'element_id': 'employment:1',
                                'element_text': 'Protected activity',
                                'coverage_status': 'missing',
                                'validation_status': 'missing',
                                'recommended_action': 'collect_initial_support',
                                'support_by_kind': {},
                                'proof_gap_count': 0,
                                'proof_gaps': [],
                                'proof_decision_trace': {},
                                'reasoning_diagnostics': {'backend_available_count': 0},
                            }
                        ],
                    }
                }
            })
            mediator.query_claim_graph_support = Mock(return_value=_make_graph_support_payload())
            mediator.discover_web_evidence = Mock(return_value={
                'discovered': 0,
                'stored': 0,
                'total_records': 0,
            })
            mediator.get_claim_overview = Mock(return_value={'claims': {'employment': {}}})

            result = mediator.execute_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                support_kind='evidence',
                max_tasks_per_claim=1,
            )

            executed_task = result['claims']['employment']['tasks'][0]
            assert executed_task['resolution_applied'] == 'insufficient_support_after_search'
            executed_call = mediator.claim_support.record_follow_up_execution.call_args_list[0]
            assert executed_call.kwargs['metadata']['resolution_applied'] == 'insufficient_support_after_search'
            assert executed_call.kwargs['metadata']['resolution_status'] == 'insufficient_support_after_search'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_evidence_to_graphs_skips_duplicate_dependency_projection(self):
        """Duplicate evidence should not create duplicate dependency-graph nodes."""
        try:
            from mediator import Mediator
            from complaint_phases import ComplaintPhase
            from complaint_phases.dependency_graph import DependencyGraph, DependencyNode, NodeType
            from complaint_phases.knowledge_graph import Entity, KnowledgeGraph

            mock_backend = Mock()
            mock_backend.id = 'test-backend'

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as evidence_db:
                evidence_db_path = evidence_db.name
            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as claim_support_db:
                claim_support_db_path = claim_support_db.name

            try:
                mediator = Mediator(
                    backends=[mock_backend],
                    evidence_db_path=evidence_db_path,
                    claim_support_db_path=claim_support_db_path,
                )

                kg = KnowledgeGraph()
                kg.add_entity(Entity(
                    id='claim-1',
                    type='claim',
                    name='Breach of Contract Claim',
                    attributes={'claim_type': 'breach of contract'},
                    confidence=0.9,
                    source='complaint',
                ))

                dg = DependencyGraph()
                dg.add_node(DependencyNode(
                    id='claim-1',
                    node_type=NodeType.CLAIM,
                    name='Breach of Contract Claim',
                    satisfied=False,
                    confidence=0.9,
                ))

                mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
                mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)

                first_result = mediator.add_evidence_to_graphs({
                    'artifact_id': 'artifact-1',
                    'name': 'Signed contract',
                    'description': 'Executed employment contract',
                    'confidence': 0.9,
                    'supports_claims': ['claim-1'],
                    'record_created': True,
                    'record_reused': False,
                    'support_link_created': True,
                    'support_link_reused': False,
                })

                updated_dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
                assert first_result['graph_projection']['graph_changed'] is True
                assert first_result['graph_projection']['graph_snapshot']['created'] is True
                assert first_result['graph_projection']['graph_snapshot']['reused'] is False
                assert len(updated_dg.nodes) == 2
                assert len(updated_dg.dependencies) == 1

                duplicate_result = mediator.add_evidence_to_graphs({
                    'artifact_id': 'artifact-1',
                    'name': 'Signed contract',
                    'description': 'Executed employment contract',
                    'confidence': 0.9,
                    'supports_claims': ['claim-1'],
                    'record_created': False,
                    'record_reused': True,
                    'support_link_created': False,
                    'support_link_reused': True,
                })

                duplicate_dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
                evidence_nodes = [
                    node for node in duplicate_dg.nodes.values()
                    if node.node_type == NodeType.EVIDENCE
                ]

                assert duplicate_result['graph_projection']['graph_changed'] is False
                assert duplicate_result['graph_projection']['graph_snapshot']['created'] is False
                assert duplicate_result['graph_projection']['graph_snapshot']['reused'] is True
                assert duplicate_result['evidence_count'] == first_result['evidence_count']
                assert 'corroborates_fact' in first_result['evidence_outcomes']
                assert 'duplicates_existing_support' in duplicate_result['evidence_outcomes']
                assert len(duplicate_dg.nodes) == 2
                assert len(duplicate_dg.dependencies) == 1
                assert len(evidence_nodes) == 1
            finally:
                if os.path.exists(evidence_db_path):
                    os.unlink(evidence_db_path)
                if os.path.exists(claim_support_db_path):
                    os.unlink(claim_support_db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_evidence_to_graphs_reports_packet_driven_contradiction_and_parse_outcomes(self):
        """Evidence ingestion should surface contradiction and parse-quality outcomes from support packets."""
        try:
            from mediator import Mediator
            from complaint_phases import KnowledgeGraph, Entity, DependencyGraph, DependencyNode, NodeType, ComplaintPhase

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])

            kg = KnowledgeGraph()
            kg.add_entity(Entity(
                id='claim-1',
                type='claim',
                name='Retaliation Claim',
                attributes={'claim_type': 'retaliation'},
                confidence=0.9,
                source='complaint',
            ))
            dg = DependencyGraph()
            dg.add_node(DependencyNode(
                id='claim-1',
                node_type=NodeType.CLAIM,
                name='Retaliation Claim',
                satisfied=False,
                confidence=0.9,
            ))
            mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
            mediator._build_claim_support_packets = Mock(return_value={
                'retaliation': {
                    'claim_type': 'retaliation',
                    'elements': [
                        {
                            'element_id': 'causation',
                            'support_status': 'contradicted',
                            'parse_quality_flags': ['improve_parse_quality'],
                            'recommended_next_step': 'resolve_support_conflicts',
                            'contradiction_count': 1,
                        }
                    ],
                }
            })

            result = mediator.add_evidence_to_graphs({
                'artifact_id': 'artifact-contradiction',
                'name': 'Conflicting memo',
                'description': 'Memo with contradictory timing',
                'confidence': 0.8,
                'supports_claims': ['claim-1'],
                'record_created': True,
                'record_reused': False,
                'support_link_created': True,
                'support_link_reused': False,
            })

            assert 'contradicts_fact' in result['evidence_outcomes']
            assert 'insufficiently_parsed' in result['evidence_outcomes']
            assert result['claim_support_packet_summary']['status_counts']['contradicted'] == 1
            assert result['next_action']['action'] == 'resolve_support_conflicts'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_evidence_to_graphs_records_resolved_alignment_task_updates(self):
        """Evidence ingestion should report when a previously open alignment task is now supported."""
        try:
            from mediator import Mediator
            from complaint_phases import KnowledgeGraph, Entity, DependencyGraph, DependencyNode, NodeType, ComplaintPhase

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])

            kg = KnowledgeGraph()
            kg.add_entity(Entity(
                id='claim-1',
                type='claim',
                name='Retaliation Claim',
                attributes={'claim_type': 'retaliation'},
                confidence=0.9,
                source='complaint',
            ))
            dg = DependencyGraph()
            dg.add_node(DependencyNode(
                id='claim-1',
                node_type=NodeType.CLAIM,
                name='Retaliation Claim',
                satisfied=False,
                confidence=0.9,
            ))
            mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.EVIDENCE,
                'alignment_evidence_tasks',
                [
                    {
                        'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                        'action': 'fill_evidence_gaps',
                        'claim_type': 'retaliation',
                        'claim_element_id': 'protected_activity',
                        'claim_element_label': 'Protected activity',
                        'support_status': 'unsupported',
                        'missing_fact_bundle': ['Date of complaint'],
                        'resolution_status': 'still_open',
                    }
                ],
            )
            mediator._build_claim_support_packets = Mock(return_value={
                'retaliation': {
                    'claim_type': 'retaliation',
                    'elements': [
                        {
                            'element_id': 'protected_activity',
                            'support_status': 'supported',
                            'missing_fact_bundle': [],
                        }
                    ],
                }
            })
            mediator._summarize_intake_evidence_alignment = Mock(return_value={
                'claims': {
                    'retaliation': {
                        'shared_elements': [
                            {
                                'element_id': 'protected_activity',
                                'label': 'Protected activity',
                                'blocking': True,
                                'support_status': 'supported',
                                'preferred_evidence_classes': ['email'],
                                'required_fact_bundle': ['Date of complaint'],
                                'satisfied_fact_bundle': ['Date of complaint'],
                                'missing_fact_bundle': [],
                                'missing_support_kinds': [],
                                'recommended_next_step': '',
                                'intake_open_item_ids': [],
                                'intake_proof_lead_ids': [],
                            }
                        ],
                    }
                }
            })

            result = mediator.add_evidence_to_graphs({
                'artifact_id': 'artifact-email',
                'name': 'HR complaint email',
                'description': 'Email complaining about discrimination',
                'confidence': 0.85,
                'supports_claims': ['claim-1'],
                'record_created': True,
                'record_reused': False,
                'support_link_created': True,
                'support_link_reused': False,
            })

            assert result['alignment_evidence_tasks'] == []
            assert result['alignment_task_updates']
            assert result['alignment_task_updates'][0]['resolution_status'] == 'resolved_supported'
            assert result['alignment_task_updates'][0]['status'] == 'resolved'
            assert mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates')[0]['resolution_status'] == 'resolved_supported'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_evidence_to_graphs_marks_remaining_alignment_task_partially_addressed(self):
        """Evidence ingestion should downgrade a surviving task when the missing fact bundle shrinks."""
        try:
            from mediator import Mediator
            from complaint_phases import KnowledgeGraph, Entity, DependencyGraph, DependencyNode, NodeType, ComplaintPhase

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])

            kg = KnowledgeGraph()
            kg.add_entity(Entity(
                id='claim-1',
                type='claim',
                name='Retaliation Claim',
                attributes={'claim_type': 'retaliation'},
                confidence=0.9,
                source='complaint',
            ))
            dg = DependencyGraph()
            dg.add_node(DependencyNode(
                id='claim-1',
                node_type=NodeType.CLAIM,
                name='Retaliation Claim',
                satisfied=False,
                confidence=0.9,
            ))
            mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.EVIDENCE,
                'alignment_evidence_tasks',
                [
                    {
                        'task_id': 'retaliation:causation:fill_evidence_gaps',
                        'action': 'fill_evidence_gaps',
                        'claim_type': 'retaliation',
                        'claim_element_id': 'causation',
                        'claim_element_label': 'Causation',
                        'support_status': 'unsupported',
                        'missing_fact_bundle': ['Decision timing', 'Decision maker knowledge'],
                        'resolution_status': 'still_open',
                    }
                ],
            )
            mediator._build_claim_support_packets = Mock(return_value={
                'retaliation': {
                    'claim_type': 'retaliation',
                    'elements': [
                        {
                            'element_id': 'causation',
                            'support_status': 'partially_supported',
                            'missing_fact_bundle': ['Decision maker knowledge'],
                        }
                    ],
                }
            })
            mediator._summarize_intake_evidence_alignment = Mock(return_value={
                'claims': {
                    'retaliation': {
                        'shared_elements': [
                            {
                                'element_id': 'causation',
                                'label': 'Causation',
                                'blocking': True,
                                'support_status': 'partially_supported',
                                'preferred_evidence_classes': ['timeline', 'email'],
                                'required_fact_bundle': ['Decision timing', 'Decision maker knowledge'],
                                'satisfied_fact_bundle': ['Decision timing'],
                                'missing_fact_bundle': ['Decision maker knowledge'],
                                'missing_support_kinds': ['evidence'],
                                'recommended_next_step': 'fill_evidence_gaps',
                                'intake_open_item_ids': [],
                                'intake_proof_lead_ids': [],
                            }
                        ],
                    }
                }
            })

            result = mediator.add_evidence_to_graphs({
                'artifact_id': 'artifact-timeline',
                'name': 'Timeline note',
                'description': 'Timeline showing complaint before firing',
                'confidence': 0.8,
                'supports_claims': ['claim-1'],
                'record_created': True,
                'record_reused': False,
                'support_link_created': True,
                'support_link_reused': False,
            })

            assert result['alignment_evidence_tasks']
            assert result['alignment_evidence_tasks'][0]['resolution_status'] == 'partially_addressed'
            assert result['alignment_task_updates']
            assert result['alignment_task_updates'][0]['resolution_status'] == 'partially_addressed'
            assert result['alignment_task_updates'][0]['status'] == 'active'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_evidence_to_graphs_marks_contradicted_alignment_task_for_manual_review(self):
        """Evidence ingestion should flag contradicted alignment tasks as needing manual review."""
        try:
            from mediator import Mediator
            from complaint_phases import KnowledgeGraph, Entity, DependencyGraph, DependencyNode, NodeType, ComplaintPhase

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])

            kg = KnowledgeGraph()
            kg.add_entity(Entity(
                id='claim-1',
                type='claim',
                name='Retaliation Claim',
                attributes={'claim_type': 'retaliation'},
                confidence=0.9,
                source='complaint',
            ))
            dg = DependencyGraph()
            dg.add_node(DependencyNode(
                id='claim-1',
                node_type=NodeType.CLAIM,
                name='Retaliation Claim',
                satisfied=False,
                confidence=0.9,
            ))
            mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.EVIDENCE,
                'alignment_evidence_tasks',
                [
                    {
                        'task_id': 'retaliation:causation:resolve_support_conflicts',
                        'action': 'resolve_support_conflicts',
                        'claim_type': 'retaliation',
                        'claim_element_id': 'causation',
                        'claim_element_label': 'Causation',
                        'support_status': 'contradicted',
                        'missing_fact_bundle': ['Event sequence'],
                        'resolution_status': 'needs_manual_review',
                    }
                ],
            )
            mediator._build_claim_support_packets = Mock(return_value={
                'retaliation': {
                    'claim_type': 'retaliation',
                    'elements': [
                        {
                            'element_id': 'causation',
                            'support_status': 'contradicted',
                            'missing_fact_bundle': ['Event sequence'],
                            'parse_quality_flags': ['improve_parse_quality'],
                            'recommended_next_step': 'resolve_support_conflicts',
                            'contradiction_count': 1,
                        }
                    ],
                }
            })
            mediator._summarize_intake_evidence_alignment = Mock(return_value={
                'claims': {
                    'retaliation': {
                        'shared_elements': [
                            {
                                'element_id': 'causation',
                                'label': 'Causation',
                                'blocking': True,
                                'support_status': 'contradicted',
                                'preferred_evidence_classes': ['timeline', 'memo'],
                                'required_fact_bundle': ['Event sequence'],
                                'satisfied_fact_bundle': [],
                                'missing_fact_bundle': ['Event sequence'],
                                'missing_support_kinds': ['evidence'],
                                'recommended_next_step': 'resolve_support_conflicts',
                                'intake_open_item_ids': [],
                                'intake_proof_lead_ids': [],
                            }
                        ],
                    }
                }
            })

            result = mediator.add_evidence_to_graphs({
                'artifact_id': 'artifact-conflict',
                'name': 'Conflicting witness note',
                'description': 'Witness note conflicts on event order',
                'confidence': 0.7,
                'supports_claims': ['claim-1'],
                'record_created': True,
                'record_reused': False,
                'support_link_created': True,
                'support_link_reused': False,
                'contradicts_existing_fact': True,
            })

            assert result['alignment_evidence_tasks']
            assert result['alignment_evidence_tasks'][0]['resolution_status'] == 'needs_manual_review'
            assert result['alignment_task_updates']
            assert result['alignment_task_updates'][0]['resolution_status'] == 'needs_manual_review'
            assert result['alignment_task_updates'][0]['status'] == 'active'
            assert 'contradicts_fact' in result['evidence_outcomes']
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_add_evidence_to_graphs_keeps_bounded_alignment_task_update_history(self):
        """Evidence ingestion should append task updates to a bounded rolling history."""
        try:
            from mediator import Mediator
            from complaint_phases import KnowledgeGraph, Entity, DependencyGraph, DependencyNode, NodeType, ComplaintPhase

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mediator = Mediator(backends=[mock_backend])

            kg = KnowledgeGraph()
            kg.add_entity(Entity(
                id='claim-1',
                type='claim',
                name='Retaliation Claim',
                attributes={'claim_type': 'retaliation'},
                confidence=0.9,
                source='complaint',
            ))
            dg = DependencyGraph()
            dg.add_node(DependencyNode(
                id='claim-1',
                node_type=NodeType.CLAIM,
                name='Retaliation Claim',
                satisfied=False,
                confidence=0.9,
            ))
            mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
            mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.EVIDENCE,
                'alignment_evidence_tasks',
                [
                    {
                        'task_id': 'retaliation:causation:fill_evidence_gaps',
                        'action': 'fill_evidence_gaps',
                        'claim_type': 'retaliation',
                        'claim_element_id': 'causation',
                        'support_status': 'unsupported',
                        'missing_fact_bundle': ['Timeline'],
                    }
                ],
            )
            mediator.phase_manager.update_phase_data(
                ComplaintPhase.EVIDENCE,
                'alignment_task_update_history',
                [
                    {
                        'task_id': f'old-task-{index}',
                        'claim_type': 'retaliation',
                        'claim_element_id': f'element-{index}',
                        'resolution_status': 'still_open',
                        'status': 'active',
                        'evidence_sequence': index,
                    }
                    for index in range(1, 26)
                ],
            )
            mediator._build_claim_support_packets = Mock(return_value={
                'retaliation': {
                    'claim_type': 'retaliation',
                    'elements': [
                        {
                            'element_id': 'causation',
                            'support_status': 'supported',
                            'missing_fact_bundle': [],
                        }
                    ],
                }
            })
            mediator._summarize_intake_evidence_alignment = Mock(return_value={
                'claims': {
                    'retaliation': {
                        'shared_elements': [
                            {
                                'element_id': 'causation',
                                'label': 'Causation',
                                'blocking': True,
                                'support_status': 'supported',
                                'preferred_evidence_classes': ['timeline'],
                                'required_fact_bundle': ['Timeline'],
                                'satisfied_fact_bundle': ['Timeline'],
                                'missing_fact_bundle': [],
                                'missing_support_kinds': [],
                                'recommended_next_step': '',
                                'intake_open_item_ids': [],
                                'intake_proof_lead_ids': [],
                            }
                        ],
                    }
                }
            })

            result = mediator.add_evidence_to_graphs({
                'artifact_id': 'artifact-history',
                'name': 'Timeline exhibit',
                'description': 'Exhibit confirming timeline',
                'confidence': 0.88,
                'supports_claims': ['claim-1'],
                'record_created': True,
                'record_reused': False,
                'support_link_created': True,
                'support_link_reused': False,
            })

            history = result['alignment_task_update_history']
            assert len(history) == 25
            assert history[0]['task_id'] == 'old-task-2'
            assert history[-1]['task_id'] == 'retaliation:causation:fill_evidence_gaps'
            assert history[-1]['evidence_sequence'] == result['evidence_count']
            assert mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history')[-1]['evidence_artifact_id'] == 'artifact-history'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
