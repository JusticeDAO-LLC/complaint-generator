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

    def test_start_three_phase_process_persists_intake_case_file(self):
        """Starting intake should persist a structured intake case file."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        complaint_text = (
            "My employer fired me on January 20, 2026 after I complained about discrimination. "
            "I have emails and a termination letter, and I lost wages."
        )

        result = mediator.start_three_phase_process(complaint_text)
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')

        assert result['intake_case_file'] == intake_case_file
        assert intake_case_file['candidate_claims']
        assert intake_case_file['canonical_facts']
        assert intake_case_file['proof_leads']
        assert result['question_candidates']
        assert intake_case_file['intake_sections']['chronology']['status'] == 'complete'
        assert intake_case_file['intake_sections']['proof_leads']['status'] == 'complete'
        status = mediator.get_three_phase_status()
        assert status['candidate_claims'] == intake_case_file['candidate_claims']
        assert status['canonical_fact_summary']['count'] == len(intake_case_file['canonical_facts'])
        assert status['proof_lead_summary']['count'] == len(intake_case_file['proof_leads'])
        assert status['question_candidate_summary']['count'] >= 1
        assert status['question_candidate_summary']['source_counts']
        assert status['question_candidate_summary']['phase1_section_counts']

    def test_initialize_intake_case_file_extracts_claims_facts_and_proof_leads(self):
        """The intake case file helper should normalize graph state into structured sections."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        kg = mediator.kg_builder.build_from_text(
            "I faced discrimination at work, I have emails, and I am seeking compensation for lost wages."
        )

        intake_case_file = mediator._initialize_intake_case_file(kg, "Initial complaint text")

        assert intake_case_file['source_complaint_text'] == 'Initial complaint text'
        assert any(claim['claim_type'] == 'employment_discrimination' for claim in intake_case_file['candidate_claims'])
        assert any(claim['required_elements'] for claim in intake_case_file['candidate_claims'])
        assert any(fact['fact_type'] == 'impact' for fact in intake_case_file['canonical_facts'])
        assert any(lead['lead_type'] == 'email communication' for lead in intake_case_file['proof_leads'])

    def test_process_denoising_answer_updates_timeline_fact_in_intake_case_file(self):
        """Timeline answers should update canonical facts and section coverage in the intake case file."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("My employer discriminated against me.")

        result = mediator.process_denoising_answer(
            {'type': 'timeline', 'question': 'When did this happen?', 'context': {}},
            'It happened on January 20, 2026.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')

        assert any(fact['fact_type'] == 'timeline' for fact in intake_case_file['canonical_facts'])
        assert intake_case_file['intake_sections']['chronology']['status'] == 'complete'
        assert result['intake_readiness']['canonical_fact_count'] >= 1
        assert result['question_candidates']
        assert mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'question_candidates')

    def test_process_denoising_answer_updates_proof_leads_in_intake_case_file(self):
        """Evidence answers should create proof leads in the structured intake record."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("I was fired after discrimination.")

        mediator.process_denoising_answer(
            {'type': 'evidence', 'question': 'What evidence supports this?', 'context': {}},
            'I have emails and a termination letter.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')

        assert intake_case_file['proof_leads']
        assert intake_case_file['intake_sections']['proof_leads']['status'] == 'complete'
        assert any('emails' in lead['description'].lower() for lead in intake_case_file['proof_leads'])

    def test_process_denoising_answer_tracks_conflicting_timeline_answers(self):
        """Conflicting timeline answers should create a structured contradiction entry."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("I was fired after discrimination.")

        question = {'type': 'timeline', 'question': 'When did this happen?', 'context': {}}
        mediator.process_denoising_answer(question, 'It happened on January 20, 2026.')
        result = mediator.process_denoising_answer(question, 'It happened on February 2, 2026.')
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')

        assert intake_case_file['contradiction_queue']
        assert intake_case_file['contradiction_queue'][0]['topic'] == 'timeline'
        assert 'blocking_contradiction' in result['intake_readiness']['blockers']

    def test_advance_to_evidence_phase_builds_claim_support_packets(self):
        """Evidence phase initialization should normalize claim-support validation into packets."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process(
            "I was fired after I complained about discrimination and I have a termination letter."
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_gap_types', [])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'candidate_claims': [{'claim_type': 'employment_discrimination'}],
                'canonical_facts': [{'fact_id': 'fact_001'}],
                'proof_leads': [{'lead_id': 'lead_001'}],
                'contradiction_queue': [],
                'intake_sections': {
                    'chronology': {'status': 'complete', 'missing_items': []},
                    'actors': {'status': 'complete', 'missing_items': []},
                    'conduct': {'status': 'complete', 'missing_items': []},
                    'harm': {'status': 'complete', 'missing_items': []},
                    'remedy': {'status': 'complete', 'missing_items': []},
                    'proof_leads': {'status': 'complete', 'missing_items': []},
                    'claim_elements': {'status': 'complete', 'missing_items': []},
                },
            },
        )
        mediator.get_claim_support_validation = Mock(return_value={
            'claims': {
                'employment_discrimination': {
                    'claim_type': 'employment_discrimination',
                    'validation_status': 'incomplete',
                    'elements': [
                        {
                            'element_id': 'adverse_action',
                            'element_text': 'Adverse action',
                            'validation_status': 'supported',
                            'recommended_action': '',
                            'missing_support_kinds': [],
                            'contradiction_candidate_count': 0,
                            'proof_diagnostics': {},
                            'gap_context': {
                                'support_facts': [{'fact_id': 'fact_001'}],
                                'support_traces': [{'source_ref': 'artifact_001', 'source_family': 'evidence'}],
                            },
                        },
                        {
                            'element_id': 'causation',
                            'element_text': 'Causation',
                            'validation_status': 'missing',
                            'recommended_action': 'collect_documentary_support',
                            'missing_support_kinds': ['evidence'],
                            'contradiction_candidate_count': 0,
                            'proof_diagnostics': {},
                            'gap_context': {
                                'support_facts': [],
                                'support_traces': [],
                            },
                        },
                    ],
                }
            }
        })
        mediator.get_claim_support_gaps = Mock(return_value={
            'claims': {
                'employment_discrimination': {
                    'claim_type': 'employment_discrimination',
                    'unresolved_count': 1,
                    'unresolved_elements': [
                        {
                            'element_id': 'causation',
                            'element_text': 'Causation',
                            'recommended_action': 'collect_documentary_support',
                            'missing_support_kinds': ['evidence'],
                        }
                    ],
                }
            }
        })

        result = mediator.advance_to_evidence_phase()

        packets = result['claim_support_packets']
        assert 'employment_discrimination' in packets
        assert packets['employment_discrimination']['elements'][0]['support_status'] == 'supported'
        assert packets['employment_discrimination']['elements'][1]['support_status'] == 'unsupported'
        status = mediator.get_three_phase_status()
        assert status['claim_support_packet_summary']['claim_count'] == 1
        assert status['claim_support_packet_summary']['status_counts']['unsupported'] == 1

    def test_requirement_answer_can_satisfy_registry_backed_claim_element(self):
        """Requirement answers should tag and satisfy registry-backed claim elements when the requirement name is recognizable."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("My employer engaged in discrimination against me because of my race.")

        result = mediator.process_denoising_answer(
            {
                'type': 'requirement',
                'question': 'What protected class are you in?',
                'context': {
                    'requirement_id': 'req_protected_class',
                    'requirement_name': 'Protected trait or class',
                },
            },
            'I am Black.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
        discrimination_claim = next(
            claim for claim in intake_case_file['candidate_claims']
            if claim['claim_type'] == 'employment_discrimination'
        )
        protected_trait = next(
            element for element in discrimination_claim['required_elements']
            if element['element_id'] == 'protected_trait'
        )

        assert protected_trait['status'] == 'present'
        assert any('protected_trait' in (fact.get('element_tags') or []) for fact in intake_case_file['canonical_facts'])
        assert result['intake_readiness']['intake_sections']['claim_elements']['status'] in {'partial', 'complete'}

    def test_initialize_intake_case_file_specializes_housing_discrimination(self):
        """Landlord and lease context should produce a housing discrimination candidate claim."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        kg = mediator.kg_builder.build_from_text(
            "My landlord discriminated against me because of my disability and refused to renew my lease."
        )

        intake_case_file = mediator._initialize_intake_case_file(kg, "Housing complaint")

        assert any(claim['claim_type'] == 'housing_discrimination' for claim in intake_case_file['candidate_claims'])

    def test_start_three_phase_process_includes_registry_backed_claim_element_question(self):
        """Initial intake questions should include prompts for missing registry-backed claim elements."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        result = mediator.start_three_phase_process(
            "My employer engaged in discrimination against me after I was fired."
        )

        requirement_questions = [
            question for question in result['initial_questions']
            if question.get('type') == 'requirement'
        ]

        assert requirement_questions
        assert any(question.get('phase1_section') == 'claim_elements' for question in requirement_questions)

    def test_start_three_phase_process_uses_domain_specific_employment_question_text(self):
        """Employment discrimination intake should ask workplace-specific claim-element questions."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        result = mediator.start_three_phase_process(
            "My employer discriminated against me because of my race."
        )

        employment_questions = [
            question for question in result['initial_questions']
            if question.get('type') == 'requirement'
            and question.get('target_element_id') == 'adverse_action'
        ]

        assert employment_questions
        assert 'adverse job action' in employment_questions[0]['question'].lower()
        assert employment_questions[0]['question_intent']['question_goal'] == 'establish_element'
        assert employment_questions[0]['question_intent']['claim_type'] == 'employment_discrimination'
        assert employment_questions[0]['ranking_explanation']['blocking_level'] == 'blocking'
        assert any(candidate.get('candidate_source') == 'intake_claim_element_gap' for candidate in result['question_candidates'])

    def test_start_three_phase_process_uses_domain_specific_housing_proof_prompt_text(self):
        """Housing discrimination intake should ask for tenancy-specific proof leads."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        result = mediator.start_three_phase_process(
            "My landlord discriminated against me because of my disability."
        )

        housing_evidence_questions = [
            question for question in result['initial_questions']
            if question.get('type') == 'evidence'
            and question.get('target_claim_type') == 'housing_discrimination'
        ]

        assert housing_evidence_questions
        question_text = housing_evidence_questions[0]['question'].lower()
        assert 'lease' in question_text
        assert 'landlord messages' in question_text
        assert housing_evidence_questions[0]['question_intent']['question_goal'] == 'identify_supporting_proof'
        assert housing_evidence_questions[0]['question_intent']['claim_type'] == 'housing_discrimination'
        assert housing_evidence_questions[0]['ranking_explanation']['phase1_section'] == 'proof_leads'
        assert any(candidate.get('candidate_source') == 'intake_proof_gap' for candidate in result['question_candidates'])
    
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
