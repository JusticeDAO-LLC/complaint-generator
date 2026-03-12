"""
Unit tests for the mediator module

Note: Some tests require backend dependencies. Tests will skip if dependencies are missing.
"""
import os
import tempfile

import pytest
from unittest.mock import Mock, MagicMock, patch


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
            mediator.query_claim_graph_support = Mock(return_value={
                'summary': {
                    'total_fact_count': 6,
                    'unique_fact_count': 2,
                    'duplicate_fact_count': 4,
                    'semantic_cluster_count': 2,
                    'semantic_duplicate_count': 4,
                    'max_score': 2.5,
                },
                'results': [
                    {'fact_id': 'fact:1', 'score': 2.5, 'matched_claim_element': True},
                ],
            })

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
            mediator.query_claim_graph_support = Mock(return_value={
                'summary': {
                    'total_fact_count': 0,
                    'unique_fact_count': 0,
                    'duplicate_fact_count': 0,
                    'semantic_cluster_count': 0,
                    'semantic_duplicate_count': 0,
                    'max_score': 0.0,
                },
                'results': [],
            })

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
            assert task['recommended_action'] == 'retrieve_more_support'
            assert task['proof_decision_source'] == 'logic_proof_partial'
            assert task['logic_provable_count'] == 1
            assert task['logic_unprovable_count'] == 1
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
            mediator.query_claim_graph_support = Mock(return_value={
                'summary': {
                    'total_fact_count': 0,
                    'unique_fact_count': 0,
                    'duplicate_fact_count': 0,
                    'semantic_cluster_count': 0,
                    'semantic_duplicate_count': 0,
                    'max_score': 0.0,
                },
                'results': [],
            })

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
            mediator.query_claim_graph_support = Mock(return_value={
                'summary': {
                    'total_fact_count': 0,
                    'unique_fact_count': 0,
                    'duplicate_fact_count': 0,
                    'semantic_cluster_count': 0,
                    'semantic_duplicate_count': 0,
                    'max_score': 0.0,
                },
                'results': [],
            })

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
            mediator.query_claim_graph_support = Mock(return_value={
                'summary': {
                    'total_fact_count': 0,
                    'unique_fact_count': 0,
                    'duplicate_fact_count': 0,
                    'semantic_cluster_count': 0,
                    'semantic_duplicate_count': 0,
                    'max_score': 0.0,
                },
                'results': [],
            })
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

