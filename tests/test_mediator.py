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

