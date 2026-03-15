"""
Integration test for three-phase complaint processing in mediator.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from complaint_phases import (
    PhaseManager,
    ComplaintPhase,
    KnowledgeGraphBuilder,
    DependencyGraphBuilder,
    ComplaintDenoiser,
    LegalGraphBuilder,
    LegalGraph,
    LegalElement,
    NeurosymbolicMatcher,
    DependencyNode,
    Dependency,
    NodeType,
    DependencyType,
)


class TestMediatorThreePhaseIntegration:
    """Integration tests for three-phase processing without full mediator."""
    
    def test_phase_1_intake_workflow(self):
        """Test Phase 1: Initial intake and denoising."""
        # Initialize components
        phase_manager = PhaseManager()
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        denoiser = ComplaintDenoiser()
        
        # Build initial graphs
        text = "I was discriminated against by my employer because of my race."
        kg = kg_builder.build_from_text(text)
        
        claims = [{'name': 'Discrimination', 'type': 'employment_discrimination'}]
        dg = dg_builder.build_from_claims(claims, {})
        
        # Store in phase manager
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
        
        # Generate questions
        questions = denoiser.generate_questions(kg, dg)
        assert len(questions) > 0
        
        # Calculate noise
        noise = denoiser.calculate_noise_level(kg, dg)
        assert 0.0 <= noise <= 1.0
        
        phase_manager.record_iteration(noise, {'entities': len(kg.entities)})
        
        # Mark as complete
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        
        assert phase_manager.is_phase_complete(ComplaintPhase.INTAKE)
    
    def test_phase_2_evidence_workflow(self):
        """Test Phase 2: Evidence gathering."""
        # Setup from Phase 1
        phase_manager = PhaseManager()
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        
        text = "I was fired by Acme Corp."
        kg = kg_builder.build_from_text(text)
        
        claims = [{'name': 'Wrongful Termination', 'type': 'employment'}]
        dg = dg_builder.build_from_claims(claims, {})
        
        # Complete Phase 1
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        
        # Advance to evidence phase
        assert phase_manager.advance_to_phase(ComplaintPhase.EVIDENCE)
        assert phase_manager.get_current_phase() == ComplaintPhase.EVIDENCE
        
        # Add evidence
        from complaint_phases.knowledge_graph import Entity, Relationship
        evidence = Entity('ev1', 'evidence', 'Termination Letter', confidence=0.9)
        kg.add_entity(evidence)
        
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count', 1)
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'knowledge_graph_enhanced', True)
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gap_ratio', 0.2)
        
        assert phase_manager.is_phase_complete(ComplaintPhase.EVIDENCE)
    
    def test_phase_3_formalization_workflow(self):
        """Test Phase 3: Neurosymbolic matching and formalization."""
        # Setup from Phases 1 and 2
        phase_manager = PhaseManager()
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        legal_graph_builder = LegalGraphBuilder()
        matcher = NeurosymbolicMatcher()
        
        text = "I was discriminated against."
        kg = kg_builder.build_from_text(text)
        
        claims = [{'name': 'Discrimination', 'type': 'discrimination'}]
        dg = dg_builder.build_from_claims(claims, {})
        
        # Complete previous phases
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        phase_manager.advance_to_phase(ComplaintPhase.EVIDENCE)
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gap_ratio', 0.2)
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count', 1)
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'knowledge_graph_enhanced', True)
        
        # Advance to formalization
        assert phase_manager.advance_to_phase(ComplaintPhase.FORMALIZATION)
        assert phase_manager.get_current_phase() == ComplaintPhase.FORMALIZATION
        
        # Build legal graph with actual requirements (not just procedural)
        # Create requirements that match the claim type in dependency graph
        legal_graph = LegalGraph()
        
        # Add a substantive requirement for discrimination claims
        req_element = LegalElement(
            id='req_1',
            element_type='requirement',
            name='Protected Class Membership',
            description='Plaintiff must be a member of a protected class',
            citation='Title VII, 42 U.S.C. § 2000e',
            jurisdiction='federal',
            required=True,
            attributes={'applicable_claim_types': ['discrimination', 'employment_discrimination']}
        )
        legal_graph.add_element(req_element)
        
        # Add procedural requirements with applicable_claim_types
        proc_req = LegalElement(
            id='req_2',
            element_type='procedural_requirement',
            name='Statement of Claim',
            description='Must state the claim showing entitlement to relief',
            citation='FRCP 8(a)(2)',
            jurisdiction='federal',
            required=True,
            attributes={'applicable_claim_types': ['discrimination', 'employment_discrimination']}
        )
        legal_graph.add_element(proc_req)
        
        phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph', legal_graph)
        
        # Perform matching - should now find requirements
        matching_results = matcher.match_claims_to_law(kg, dg, legal_graph)
        phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_results', matching_results)
        
        # Assert that matching actually found requirements
        assert 'matched_requirements' in matching_results, "Matching should find requirements"
        assert len(matching_results.get('matched_requirements', [])) > 0, "Should match at least one requirement"
        
        phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_complete', True)
        
        # Generate formal complaint (simplified)
        formal_complaint = {
            'title': 'Plaintiff v. Defendant',
            'parties': {'plaintiffs': ['John Doe'], 'defendants': ['Acme Corp']},
            'jurisdiction': 'federal',
            'statement_of_claim': 'Discrimination claim'
        }
        phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint', formal_complaint)
        
        assert phase_manager.is_phase_complete(ComplaintPhase.FORMALIZATION)
    
    def test_complete_three_phase_workflow(self):
        """Test complete workflow through all three phases."""
        phase_manager = PhaseManager()
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        denoiser = ComplaintDenoiser()
        legal_graph_builder = LegalGraphBuilder()
        matcher = NeurosymbolicMatcher()
        
        # Phase 1: Intake
        assert phase_manager.get_current_phase() == ComplaintPhase.INTAKE
        
        text = "I was discriminated against by my employer."
        kg = kg_builder.build_from_text(text)
        
        claims = [{'name': 'Discrimination', 'type': 'employment_discrimination'}]
        dg = dg_builder.build_from_claims(claims, {})
        
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
        
        questions = denoiser.generate_questions(kg, dg, max_questions=3)
        assert len(questions) > 0
        
        # Simulate answering questions
        for q in questions[:2]:
            denoiser.process_answer(q, "Yes, I have more information.", kg, dg)
        
        noise = denoiser.calculate_noise_level(kg, dg)
        phase_manager.record_iteration(noise, {})
        
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 1)
        phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        
        # Phase 2: Evidence
        assert phase_manager.advance_to_phase(ComplaintPhase.EVIDENCE)
        
        from complaint_phases.knowledge_graph import Entity
        evidence = Entity('ev1', 'evidence', 'Document', confidence=0.9)
        kg.add_entity(evidence)
        
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count', 1)
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'knowledge_graph_enhanced', True)
        phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gap_ratio', 0.25)
        
        # Phase 3: Formalization
        assert phase_manager.advance_to_phase(ComplaintPhase.FORMALIZATION)
        
        legal_graph = legal_graph_builder.build_rules_of_procedure()
        phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph', legal_graph)
        
        matching_results = matcher.match_claims_to_law(kg, dg, legal_graph)
        phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_results', matching_results)
        phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_complete', True)
        
        formal_complaint = {'title': 'Test Complaint'}
        phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint', formal_complaint)
        
        # Verify all phases complete
        assert phase_manager.is_phase_complete(ComplaintPhase.INTAKE)
        assert phase_manager.is_phase_complete(ComplaintPhase.EVIDENCE)
        assert phase_manager.is_phase_complete(ComplaintPhase.FORMALIZATION)
    
    def test_convergence_tracking(self):
        """Test that convergence is tracked across iterations."""
        phase_manager = PhaseManager()
        
        # Simulate improving noise levels with smaller changes
        for i in range(10):
            noise = 0.5 - (i * 0.001)  # Very small decreasing noise
            phase_manager.record_iteration(noise, {'iteration': i})
        
        assert len(phase_manager.loss_history) == 10
        # The change should be very small, so convergence should be detected
        assert phase_manager.has_converged(window=5, threshold=0.01)

    def test_phase_status_exposes_intake_contradiction_details(self):
        """Mediator status should include concrete intake contradiction diagnostics."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        dg = mediator.dg_builder.build_from_claims([])
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)

        left_fact = DependencyNode('fact_left', NodeType.FACT, 'Complaint before termination')
        right_fact = DependencyNode('fact_right', NodeType.FACT, 'Termination before complaint')
        dg.add_node(left_fact)
        dg.add_node(right_fact)
        dg.add_dependency(Dependency('dep_contradiction', 'fact_left', 'fact_right', DependencyType.CONTRADICTS, required=False))

        mediator._update_intake_contradiction_state(dg)
        status = mediator.get_three_phase_status()

        assert status['intake_contradictions']['candidate_count'] == 1
        assert status['intake_readiness']['contradiction_count'] == 1
        assert status['intake_contradictions']['candidates'][0]['left_node_name'] == 'Complaint before termination'
    
    def test_graph_serialization(self):
        """Test that graphs can be serialized for storage."""
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        
        text = "Test complaint text."
        kg = kg_builder.build_from_text(text)
        
        claims = [{'name': 'Test Claim', 'type': 'test'}]
        dg = dg_builder.build_from_claims(claims, {})
        
        # Serialize
        kg_dict = kg.to_dict()
        dg_dict = dg.to_dict()
        
        assert 'entities' in kg_dict
        assert 'nodes' in dg_dict
        
        # Deserialize
        from complaint_phases.knowledge_graph import KnowledgeGraph
        from complaint_phases.dependency_graph import DependencyGraph
        
        kg2 = KnowledgeGraph.from_dict(kg_dict)
        dg2 = DependencyGraph.from_dict(dg_dict)
        
        assert len(kg2.entities) == len(kg.entities)
        assert len(dg2.nodes) == len(dg.nodes)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
