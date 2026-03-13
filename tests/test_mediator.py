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

            mediator.execute_claim_follow_up_plan(
                claim_type='employment',
                user_id='testuser',
                support_kind='evidence',
                max_tasks_per_claim=1,
            )

            executed_call = mediator.claim_support.record_follow_up_execution.call_args_list[0]
            assert executed_call.kwargs['status'] == 'executed'
            assert executed_call.kwargs['metadata']['result_count'] == 0
            assert executed_call.kwargs['metadata']['stored_result_count'] == 0
            assert executed_call.kwargs['metadata']['zero_result'] is True
            assert executed_call.kwargs['metadata']['follow_up_focus'] == 'reasoning_gap_closure'
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

