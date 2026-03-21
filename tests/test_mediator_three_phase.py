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

    def test_phase_status_exposes_temporal_cycle_contradictions(self):
        """Temporal ordering cycles should surface through the intake contradiction pipeline."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        dg = mediator.dg_builder.build_from_claims([])
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)

        fact_a = DependencyNode('fact_a', NodeType.FACT, 'Complaint made')
        fact_b = DependencyNode('fact_b', NodeType.FACT, 'Termination issued')
        dg.add_node(fact_a)
        dg.add_node(fact_b)
        dg.add_dependency(Dependency('dep_before_1', 'fact_a', 'fact_b', DependencyType.BEFORE, required=False))
        dg.add_dependency(Dependency('dep_before_2', 'fact_b', 'fact_a', DependencyType.BEFORE, required=False))

        mediator._update_intake_contradiction_state(dg)
        status = mediator.get_three_phase_status()

        assert status['intake_contradictions']['candidate_count'] >= 1
        assert status['intake_readiness']['contradiction_count'] >= 1
        assert 'contradiction_unresolved' in status['intake_readiness']['blockers']
        assert any(
            candidate.get('category') in {'temporal_cycle', 'temporal_reverse_before'}
            for candidate in status['intake_contradictions']['candidates']
        )

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
        assert intake_case_file['intake_sections']['chronology']['status'] in {'partial', 'complete'}
        assert intake_case_file['intake_sections']['proof_leads']['status'] == 'complete'
        status = mediator.get_three_phase_status()
        assert status['candidate_claims'] == intake_case_file['candidate_claims']
        assert status['canonical_fact_summary']['count'] == len(intake_case_file['canonical_facts'])
        assert status['proof_lead_summary']['count'] == len(intake_case_file['proof_leads'])
        assert status['intake_matching_summary']['claim_count'] >= 1
        assert status['intake_legal_targeting_summary']['claim_count'] >= 1
        assert status['question_candidate_summary']['count'] >= 1
        assert status['question_candidate_summary']['source_counts']
        assert status['question_candidate_summary']['phase1_section_counts']

    def test_status_summary_counts_claim_temporal_gap_candidates(self):
        """Mediator status should summarize native temporal-gap candidates separately."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process('My supervisor acted after I complained about discrimination.')

        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
        intake_case_file['candidate_claims'] = [
            {
                'claim_type': 'retaliation',
                'label': 'Retaliation',
                'required_elements': [],
            }
        ]
        intake_case_file['temporal_issue_registry'] = [
            {
                'issue_id': 'temporal_issue:relative_only_ordering:fact_3',
                'issue_type': 'relative_only_ordering',
                'category': 'relative_only_ordering',
                'summary': 'Timeline fact fact_3 only has relative ordering (after) and still needs anchoring.',
                'severity': 'blocking',
                'blocking': True,
                'recommended_resolution_lane': 'clarify_with_complainant',
                'fact_ids': ['fact_3'],
                'claim_types': ['retaliation'],
                'element_tags': ['causation'],
                'left_node_name': 'Supervisor acted after the complaint.',
                'right_node_name': None,
                'status': 'open',
                'relative_markers': ['after'],
            }
        ]
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)

        kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
        dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
        question_candidates = mediator.denoiser.collect_question_candidates(
            kg,
            dg,
            max_questions=10,
            intake_case_file=intake_case_file,
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'question_candidates', question_candidates)

        status = mediator.get_three_phase_status()
        summary = status['question_candidate_summary']
        temporal_issue_summary = status['temporal_issue_registry_summary']

        assert summary['temporal_gap_candidate_count'] >= 1
        assert summary['temporal_gap_claim_counts']['retaliation'] >= 1
        assert summary['temporal_gap_issue_type_counts']['relative_only_ordering'] >= 1
        assert summary['temporal_gap_resolution_lane_counts']['clarify_with_complainant'] >= 1
        assert temporal_issue_summary['status_counts']['open'] >= 1
        assert temporal_issue_summary['issue_type_counts']['relative_only_ordering'] >= 1
        assert temporal_issue_summary['claim_type_counts']['retaliation'] >= 1
        assert temporal_issue_summary['element_tag_counts']['causation'] >= 1
        assert temporal_issue_summary['resolved_count'] == 0
        assert temporal_issue_summary['unresolved_count'] >= 1

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
        assert intake_case_file['open_items']
        assert intake_case_file['summary_snapshots']
        assert intake_case_file['complainant_summary_confirmation']['confirmed'] is False
        assert intake_case_file['summary_snapshots'][0]['candidate_claim_count'] >= 1

    def test_confirm_intake_summary_marks_latest_snapshot_confirmed(self):
        """Confirming intake summary should persist complainant confirmation against the latest snapshot."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("My employer discriminated against me and I have emails.")

        status = mediator.confirm_intake_summary("summary reviewed with complainant")
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')

        assert status['complainant_summary_confirmation']['confirmed'] is True
        assert status['intake_readiness']['criteria']['complainant_summary_confirmed'] is True
        assert status['intake_summary_handoff']['current_phase'] == ComplaintPhase.INTAKE.value
        assert status['intake_summary_handoff']['ready_to_advance'] == status['intake_readiness']['ready_to_advance']
        assert status['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
        assert intake_case_file['complainant_summary_confirmation']['confirmation_note'] == 'summary reviewed with complainant'
        assert intake_case_file['complainant_summary_confirmation']['confirmed_summary_snapshot'] == intake_case_file['summary_snapshots'][-1]

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
            {
                'type': 'timeline',
                'question': 'When did this happen?',
                'question_objective': 'establish_chronology',
                'expected_update_kind': 'timeline_anchor',
                'target_claim_type': 'employment_discrimination',
                'target_element_id': 'adverse_action',
                'context': {'target_element_id': 'adverse_action'},
            },
            'It happened on January 20, 2026 at the Dallas office.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
        timeline_fact = next(fact for fact in intake_case_file['canonical_facts'] if fact['fact_type'] == 'timeline')

        assert any(fact['fact_type'] == 'timeline' for fact in intake_case_file['canonical_facts'])
        assert timeline_fact['event_date_or_range'] == 'January 20, 2026'
        assert timeline_fact['temporal_context']['start_date'] == '2026-01-20'
        assert timeline_fact['temporal_context']['end_date'] == '2026-01-20'
        assert timeline_fact['temporal_context']['granularity'] == 'day'
        assert timeline_fact['location'] == 'Dallas office'
        assert timeline_fact['fact_participants']['location'] == 'Dallas office'
        assert timeline_fact['intake_question_intent']['question_objective'] == 'establish_chronology'
        assert timeline_fact['intake_question_intent']['expected_update_kind'] == 'timeline_anchor'
        assert timeline_fact['intake_question_intent']['target_claim_type'] == 'employment_discrimination'
        assert timeline_fact['intake_question_intent']['target_element_id'] == 'adverse_action'
        assert intake_case_file['timeline_anchors'][0]['anchor_text'] == 'January 20, 2026'
        assert intake_case_file['timeline_anchors'][0]['start_date'] == '2026-01-20'
        assert intake_case_file['timeline_anchors'][0]['granularity'] == 'day'
        dependency_graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
        temporal_fact_nodes = [
            node for node in dependency_graph.nodes.values()
            if node.node_type == NodeType.FACT and node.attributes.get('timeline_fact_node')
        ]
        assert len(temporal_fact_nodes) >= 1
        assert any(node.attributes.get('source_fact_id') == timeline_fact['fact_id'] for node in temporal_fact_nodes)
        assert intake_case_file['intake_sections']['chronology']['status'] in {'partial', 'complete'}
        assert result['intake_readiness']['canonical_fact_count'] >= 1
        assert result['question_candidates']
        assert mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'question_candidates')

    def test_process_denoising_answer_authors_temporal_state_before_refresh(self, monkeypatch):
        """Timeline answers should populate authored chronology objects before the full case-file refresh runs."""
        import mediator.mediator as mediator_module
        from mediator.mediator import Mediator
        from complaint_phases.intake_case_file import refresh_intake_case_file as real_refresh_intake_case_file

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        captured_payloads = []

        def _capturing_refresh(case_file, knowledge_graph, *, append_snapshot=False):
            captured_payloads.append(
                {
                    'canonical_facts': [dict(item) for item in (case_file.get('canonical_facts') or []) if isinstance(item, dict)],
                    'timeline_anchors': [dict(item) for item in (case_file.get('timeline_anchors') or []) if isinstance(item, dict)],
                    'timeline_relations': [dict(item) for item in (case_file.get('timeline_relations') or []) if isinstance(item, dict)],
                    'temporal_fact_registry': [dict(item) for item in (case_file.get('temporal_fact_registry') or []) if isinstance(item, dict)],
                    'event_ledger': [dict(item) for item in (case_file.get('event_ledger') or []) if isinstance(item, dict)],
                    'temporal_relation_registry': [dict(item) for item in (case_file.get('temporal_relation_registry') or []) if isinstance(item, dict)],
                }
            )
            return real_refresh_intake_case_file(case_file, knowledge_graph, append_snapshot=append_snapshot)

        monkeypatch.setattr(mediator_module, 'refresh_intake_case_file', _capturing_refresh)

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("I was fired after I complained about discrimination.")

        question = {
            'type': 'timeline',
            'question': 'When did this happen?',
            'question_objective': 'establish_chronology',
            'expected_update_kind': 'timeline_anchor',
            'target_claim_type': 'employment_discrimination',
        }
        mediator.process_denoising_answer(question, 'I complained on March 1, 2025.')
        mediator.process_denoising_answer(question, 'I was fired on April 15, 2025.')

        assert len(captured_payloads) >= 2
        first_refresh_payload = captured_payloads[0]
        second_refresh_payload = captured_payloads[-1]

        first_timeline_fact = next(
            fact
            for fact in first_refresh_payload['canonical_facts']
            if str(fact.get('fact_type') or '').strip().lower() == 'timeline'
            and 'March 1, 2025' in str(fact.get('text') or '')
        )

        assert first_timeline_fact['temporal_context']['start_date'] == '2025-03-01'
        assert first_refresh_payload['timeline_anchors']
        assert first_refresh_payload['event_ledger']
        assert any(item.get('temporal_status') == 'anchored' for item in first_refresh_payload['temporal_fact_registry'])
        assert second_refresh_payload['timeline_relations']
        assert second_refresh_payload['temporal_relation_registry']
        assert second_refresh_payload['temporal_relation_registry'][0]['relation_type'] == 'before'

    def test_process_denoising_answer_marks_temporal_issue_resolved_for_temporal_gap_candidate(self):
        """Answering a native temporal-gap question should resolve the matching temporal issue in the intake case file."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process('My supervisor acted after I complained about discrimination.')

        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
        intake_case_file['candidate_claims'] = [
            {
                'claim_type': 'retaliation',
                'label': 'Retaliation',
                'required_elements': [],
            }
        ]
        intake_case_file['temporal_issue_registry'] = [
            {
                'issue_id': 'temporal_issue:relative_only_ordering:fact_3',
                'issue_type': 'relative_only_ordering',
                'category': 'relative_only_ordering',
                'summary': 'Timeline fact fact_3 only has relative ordering (after) and still needs anchoring.',
                'severity': 'blocking',
                'blocking': True,
                'recommended_resolution_lane': 'clarify_with_complainant',
                'fact_ids': ['fact_3'],
                'claim_types': ['retaliation'],
                'element_tags': ['causation'],
                'left_node_name': 'Supervisor acted after the complaint.',
                'right_node_name': None,
                'status': 'open',
                'relative_markers': ['after'],
            }
        ]
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)

        question = mediator.denoiser._question_candidate(
            source='intake_claim_temporal_gap',
            question_type='timeline',
            question_text='For your retaliation claim, what is the most specific date or timeframe for the complaint and the action that followed?',
            context={
                'claim_type': 'retaliation',
                'claim_name': 'Retaliation',
                'gap_id': 'temporal_issue:relative_only_ordering:fact_3',
                'gap_type': 'relative_only_ordering',
                'temporal_issue_id': 'temporal_issue:relative_only_ordering:fact_3',
                'requirement_id': 'causation',
                'target_element_id': 'causation',
                'workflow_phase': 'graph_analysis',
                'recommended_resolution_lane': 'clarify_with_complainant',
                'extraction_targets': ['exact_dates', 'event_order', 'protected_activity', 'adverse_action'],
                'patchability_markers': ['chronology_patch_anchor', 'adverse_action_patch_anchor'],
            },
            priority='high',
        )
        question['question_objective'] = 'establish_causation'
        question['ranking_explanation']['question_objective'] = 'establish_causation'

        mediator.process_denoising_answer(
            question,
            'I complained on March 1, 2025, and my supervisor fired me on March 20, 2025 after that complaint.',
        )

        refreshed_intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
        resolved_issue = next(
            issue
            for issue in refreshed_intake_case_file['temporal_issue_registry']
            if issue['issue_id'] == 'temporal_issue:relative_only_ordering:fact_3'
        )

        assert resolved_issue['status'] == 'resolved'
        assert resolved_issue['current_resolution_status'] == 'resolved'
        assert resolved_issue['answered_by_question_type'] == 'timeline'
        assert resolved_issue['answered_by_candidate_source'] == 'intake_claim_temporal_gap'
        assert 'March 1, 2025' in resolved_issue['resolution']

    def test_relative_only_temporal_gap_question_uses_adverse_action_specific_wording(self):
        denoiser = ComplaintDenoiser()

        question = denoiser._build_claim_temporal_gap_question_text(
            'relative_only_ordering',
            claim_label='Retaliation',
            summary='Timeline fact still needs anchoring after a complaint and adverse action sequence.',
            left_node_name='I complained and then HACC acted after the complaint.',
            right_node_name='Housing-status change',
            relative_markers=['after'],
        )

        assert 'what protected activity happened first' in question.lower()
        assert 'what exact adverse action followed' in question.lower()
        assert 'what notice, message, or decision record proves that action' in question.lower()
        assert 'retaliation' in question.lower()

    def test_process_denoising_answer_syncs_temporal_relations_into_dependency_graph(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'ok'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("I was fired after I complained about discrimination.")

        question = {
            'type': 'timeline',
            'question': 'When did this happen?',
            'question_objective': 'establish_chronology',
            'expected_update_kind': 'timeline_anchor',
            'target_claim_type': 'employment_discrimination',
        }
        mediator.process_denoising_answer(question, 'I complained on March 1, 2025.')
        mediator.process_denoising_answer(question, 'I was fired on April 15, 2025.')

        dependency_graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
        before_edges = [
            dep for dep in dependency_graph.dependencies.values()
            if dep.dependency_type == DependencyType.BEFORE
        ]
        assert len(before_edges) >= 1

    def test_process_denoising_answer_extracts_actor_target_and_location_for_responsible_party(self):
        """Responsible-party answers should populate actor, target, and location-oriented fact fields."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("My employer discriminated against me.")

        mediator.process_denoising_answer(
            {'type': 'responsible_party', 'question': 'Who did this?', 'context': {}},
            'My supervisor John Smith fired me at the Dallas office.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
        responsible_party_fact = next(
            fact for fact in intake_case_file['canonical_facts']
            if fact['fact_type'] == 'responsible_party'
        )

        assert responsible_party_fact['actor_ids'] == ['My supervisor John Smith']
        assert responsible_party_fact['target_ids'] == ['complainant']
        assert responsible_party_fact['location'] == 'Dallas office'
        assert responsible_party_fact['fact_participants']['actor'] == 'My supervisor John Smith'
        assert responsible_party_fact['fact_participants']['target'] == 'complainant'

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

    def test_process_denoising_answer_updates_harm_and_remedy_profiles(self):
        """Impact and remedy answers should populate structured harm and remedy profiles in the intake case file."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("I was fired after discrimination.")

        mediator.process_denoising_answer(
            {'type': 'impact', 'question': 'What harm did you suffer?', 'context': {}},
            'I lost wages, my job, and suffered severe stress.',
        )
        mediator.process_denoising_answer(
            {'type': 'remedy', 'question': 'What do you want?', 'context': {}},
            'I want damages and reinstatement.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')

        assert 'economic' in intake_case_file['harm_profile']['categories']
        assert 'professional' in intake_case_file['harm_profile']['categories']
        assert 'emotional' in intake_case_file['harm_profile']['categories']
        assert 'monetary' in intake_case_file['remedy_profile']['categories']
        assert 'reinstatement' in intake_case_file['remedy_profile']['categories']

    def test_process_denoising_answer_enriches_proof_lead_metadata_for_targeted_element(self):
        """Evidence answers should preserve claim-element targeting and retrieval metadata on proof leads."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("I was fired after I complained about discrimination.")

        mediator.process_denoising_answer(
            {
                'type': 'evidence',
                'question': 'What evidence do you have to support protected activity?',
                'priority': 'high',
                'context': {
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'target_element_id': 'protected_activity',
                },
            },
            'I have emails to HR and text messages from my supervisor.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
        matching_lead = next(
            lead for lead in intake_case_file['proof_leads']
            if 'emails to hr' in lead['description'].lower()
        )

        assert 'protected_activity' in matching_lead['element_targets']
        assert matching_lead['expected_format'] == 'email'
        assert matching_lead['retrieval_path'] == 'complainant_email_account'
        assert matching_lead['priority'] == 'high'
        assert matching_lead['intake_question_intent']['target_claim_type'] == 'retaliation'
        assert matching_lead['intake_question_intent']['target_element_id'] == 'protected_activity'
        assert matching_lead['intake_question_intent']['question_type'] == 'evidence'

    def test_process_denoising_answer_marks_witness_support_as_testimony_lane(self):
        """Witness-oriented evidence answers should set testimony-oriented proof lead metadata."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("I was fired after I complained about discrimination.")

        mediator.process_denoising_answer(
            {
                'type': 'evidence',
                'question': 'Who can support this?',
                'context': {
                    'claim_type': 'retaliation',
                    'claim_element_id': 'causation',
                    'target_element_id': 'causation',
                },
            },
            'My coworker Jane Doe witnessed the retaliation and can confirm the timeline.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
        witness_lead = next(
            lead for lead in intake_case_file['proof_leads']
            if 'coworker jane doe' in lead['description'].lower()
        )

        assert witness_lead['recommended_support_kind'] == 'testimony'
        assert witness_lead['source_quality_target'] == 'credible_testimony'
        assert witness_lead['custodian'] == 'witness_follow_up'

    def test_process_denoising_answer_refreshes_open_items_and_summary_snapshots(self):
        """Structured intake refresh should keep unresolved work and snapshots current after answers."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("My employer discriminated against me because of my race.")

        mediator.process_denoising_answer(
            {
                'type': 'requirement',
                'question': 'What protected class are you in?',
                'context': {
                    'claim_type': 'employment_discrimination',
                    'requirement_id': 'protected_trait',
                    'target_element_id': 'protected_trait',
                    'requirement_name': 'Protected trait or class',
                },
            },
            'I am Black.',
        )
        intake_case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
        open_item_ids = {item['open_item_id'] for item in intake_case_file['open_items']}

        assert 'element:employment_discrimination:protected_trait' not in open_item_ids
        assert intake_case_file['summary_snapshots']
        assert intake_case_file['summary_snapshots'][-1]['open_item_count'] == len(intake_case_file['open_items'])

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
        assert intake_case_file['contradiction_queue'][0]['recommended_resolution_lane'] == 'clarify_with_complainant'
        assert intake_case_file['contradiction_queue'][0]['external_corroboration_required'] is False
        assert intake_case_file['contradiction_queue'][0]['current_resolution_status'] == 'open'
        assert 'blocking_contradiction' in result['intake_readiness']['blockers']

    def test_get_three_phase_status_summarizes_intake_intent_metadata_for_facts_and_leads(self):
        """Three-phase status should expose compact intent counts for stored facts and proof leads."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process("I was fired after I complained about discrimination.")

        mediator.process_denoising_answer(
            {
                'type': 'requirement',
                'question': 'What protected activity did you engage in?',
                'question_objective': 'satisfy_claim_requirement',
                'expected_update_kind': 'claim_element_fact',
                'target_claim_type': 'retaliation',
                'target_element_id': 'protected_activity',
                'context': {
                    'claim_type': 'retaliation',
                    'requirement_id': 'protected_activity',
                    'target_element_id': 'protected_activity',
                    'requirement_name': 'Protected activity',
                },
            },
            'I complained to HR about discrimination.',
        )
        mediator.process_denoising_answer(
            {
                'type': 'evidence',
                'question': 'What evidence supports that complaint?',
                'question_objective': 'identify_supporting_evidence',
                'expected_update_kind': 'proof_lead',
                'target_claim_type': 'retaliation',
                'target_element_id': 'protected_activity',
                'context': {
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'target_element_id': 'protected_activity',
                },
            },
            'I have emails to HR confirming the complaint.',
        )

        status = mediator.get_three_phase_status()

        assert status['canonical_fact_intent_summary']['question_objective_counts']['satisfy_claim_requirement'] >= 1
        assert status['canonical_fact_intent_summary']['expected_update_kind_counts']['claim_element_fact'] >= 1
        assert status['canonical_fact_intent_summary']['target_claim_type_counts']['retaliation'] >= 1
        assert status['canonical_fact_intent_summary']['target_element_id_counts']['protected_activity'] >= 1
        assert status['proof_lead_intent_summary']['question_objective_counts']['identify_supporting_evidence'] >= 1
        assert status['proof_lead_intent_summary']['expected_update_kind_counts']['proof_lead'] >= 1
        assert status['proof_lead_intent_summary']['target_claim_type_counts']['retaliation'] >= 1
        assert status['proof_lead_intent_summary']['target_element_id_counts']['protected_activity'] >= 1

    def test_get_three_phase_status_includes_alignment_task_update_summary(self):
        """Three-phase status should expose promoted testimony/document counts for alignment updates."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_update_history',
            [
                {
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'resolution_status': 'promoted_to_testimony',
                    'status': 'resolved',
                    'evidence_sequence': 1,
                },
                {
                    'claim_type': 'retaliation',
                    'claim_element_id': 'adverse_action',
                    'resolution_status': 'promoted_to_document',
                    'status': 'resolved',
                    'evidence_sequence': 2,
                },
            ],
        )

        status = mediator.get_three_phase_status()

        assert status['alignment_task_update_summary']['count'] == 2
        assert status['alignment_task_update_summary']['promoted_testimony_count'] == 1
        assert status['alignment_task_update_summary']['promoted_document_count'] == 1
        assert status['alignment_task_update_summary']['resolution_status_counts']['promoted_to_testimony'] == 1
        assert status['alignment_validation_focus_summary']['count'] == 2
        assert status['alignment_validation_focus_summary']['claim_type_counts']['retaliation'] == 2
        assert status['alignment_validation_focus_summary']['primary_target']['claim_element_id'] == 'adverse_action'
        assert status['alignment_validation_focus_summary']['targets'][0]['promotion_kind'] == 'document'
        assert status['alignment_promotion_drift_summary']['promoted_count'] == 2
        assert status['alignment_promotion_drift_summary']['pending_conversion_count'] == 2
        assert status['alignment_promotion_drift_summary']['drift_flag'] is True

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
                'candidate_claims': [
                    {
                        'claim_type': 'employment_discrimination',
                        'required_elements': [
                            {'element_id': 'adverse_action', 'label': 'Adverse action', 'blocking': True},
                            {'element_id': 'causation', 'label': 'Causation', 'blocking': True},
                        ],
                    }
                ],
                'canonical_facts': [{'fact_id': 'fact_001'}],
                'proof_leads': [
                    {
                        'lead_id': 'lead_001',
                        'element_targets': ['causation'],
                    }
                ],
                'contradiction_queue': [],
                'complainant_summary_confirmation': {
                    'status': 'confirmed',
                    'confirmed': True,
                    'confirmed_at': '2026-03-17T18:00:00+00:00',
                    'confirmation_note': 'ready for evidence handoff',
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
                'open_items': [
                    {
                        'open_item_id': 'element:employment_discrimination:causation',
                        'target_claim_type': 'employment_discrimination',
                        'target_element_id': 'causation',
                    }
                ],
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
                            'reasoning_diagnostics': {
                                'hybrid_reasoning': {
                                    'status': 'success',
                                    'result': {
                                        'compiler_bridge_available': True,
                                        'tdfol_formulas': [
                                            'Before(fact_1,fact_2)',
                                            'forall t (AtTime(t,t_2026_03_10) -> Fact(fact_1,t))',
                                        ],
                                        'dcec_formulas': [
                                            'Happens(fact_1,t_2026_03_10)',
                                        ],
                                    },
                                },
                                'temporal_summary': {
                                    'fact_count': 2,
                                    'proof_lead_count': 1,
                                    'relation_count': 1,
                                    'issue_count': 1,
                                    'partial_order_ready': False,
                                    'warning_count': 1,
                                    'warnings': ['Some timeline facts only express relative ordering and still need anchoring.'],
                                    'relation_type_counts': {'before': 1},
                                    'relation_preview': ['fact_001 before fact_termination'],
                                },
                            },
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
        assert result['intake_summary_handoff']['current_phase'] == ComplaintPhase.EVIDENCE.value
        assert result['intake_summary_handoff']['ready_to_advance'] is True
        assert result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
        assert 'employment_discrimination' in packets
        assert packets['employment_discrimination']['elements'][0]['support_status'] == 'supported'
        assert packets['employment_discrimination']['elements'][0]['support_quality'] == 'draft_ready'
        assert packets['employment_discrimination']['elements'][0]['hybrid_bridge_used'] is True
        assert packets['employment_discrimination']['elements'][0]['hybrid_bridge_available'] is True
        assert packets['employment_discrimination']['elements'][0]['hybrid_tdfol_formula_count'] == 2
        assert packets['employment_discrimination']['elements'][0]['hybrid_dcec_formula_count'] == 1
        assert packets['employment_discrimination']['elements'][0]['temporal_fact_count'] == 2
        assert packets['employment_discrimination']['elements'][0]['temporal_relation_count'] == 1
        assert packets['employment_discrimination']['elements'][0]['temporal_issue_count'] == 1
        assert packets['employment_discrimination']['elements'][0]['temporal_partial_order_ready'] is False
        assert packets['employment_discrimination']['elements'][0]['temporal_warning_count'] == 1
        assert packets['employment_discrimination']['elements'][1]['support_status'] == 'unsupported'
        assert packets['employment_discrimination']['elements'][1]['support_quality'] == 'unsupported'
        assert packets['employment_discrimination']['elements'][1]['missing_fact_bundle']
        assert packets['employment_discrimination']['elements'][1]['preferred_evidence_classes'] == []
        assert result['alignment_evidence_tasks']
        assert result['alignment_evidence_tasks'][0]['preferred_support_kind'] == 'evidence'
        assert result['alignment_evidence_tasks'][0]['missing_fact_bundle']
        assert 'open_item:element:employment_discrimination:causation' in result['alignment_evidence_tasks'][0]['intake_origin_refs']
        assert 'proof_lead:lead_001' in result['alignment_evidence_tasks'][0]['intake_origin_refs']
        assert result['alignment_evidence_tasks'][0]['recommended_queries']
        assert result['alignment_evidence_tasks'][0]['recommended_witness_prompts']
        assert result['alignment_evidence_tasks'][0]['success_criteria']
        assert result['alignment_evidence_tasks'][0]['source_quality_target'] == 'high_quality_document'
        assert result['alignment_evidence_tasks'][0]['fallback_lanes']
        assert 'authority' in result['alignment_evidence_tasks'][0]['fallback_lanes']
        assert result['alignment_evidence_tasks'][0]['resolution_notes'] == ''
        assert result['next_action']['action'] == 'fill_evidence_gaps'
        assert result['next_action']['claim_element_id'] == 'causation'
        status = mediator.get_three_phase_status()
        assert status['intake_summary_handoff']['current_phase'] == ComplaintPhase.EVIDENCE.value
        assert status['alignment_evidence_tasks']
        assert status['alignment_evidence_tasks'][0]['claim_element_id'] == 'causation'
        assert 'fallback_lanes' in status['alignment_evidence_tasks'][0]
        assert status['claim_support_packet_summary']['claim_count'] == 1
        assert status['claim_support_packet_summary']['status_counts']['unsupported'] == 1
        assert 'proof_readiness_score' in status['claim_support_packet_summary']
        assert status['claim_support_packet_summary']['hybrid_bridge_element_count'] == 1
        assert status['claim_support_packet_summary']['hybrid_bridge_available_element_count'] == 1
        assert status['claim_support_packet_summary']['hybrid_tdfol_formula_count'] == 2
        assert status['claim_support_packet_summary']['hybrid_dcec_formula_count'] == 1
        assert status['claim_support_packet_summary']['temporal_fact_count'] == 2
        assert status['claim_support_packet_summary']['temporal_relation_count'] == 1
        assert status['claim_support_packet_summary']['temporal_issue_count'] == 1
        assert status['claim_support_packet_summary']['temporal_partial_order_ready_element_count'] == 0
        assert status['claim_support_packet_summary']['temporal_warning_count'] == 1
        alignment = status['intake_evidence_alignment_summary']['claims']['employment_discrimination']
        assert 'adverse_action' in alignment['packet_element_statuses']
        assert isinstance(alignment['shared_elements'], list)
        assert alignment['shared_elements'][0]['support_quality'] == 'draft_ready'

    def test_advance_to_evidence_phase_prefers_testimony_for_testimony_only_elements(self):
        """Evidence-phase tasks should start in the testimony lane when the element only points to witness testimony."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process(
            "I was retaliated against after complaining, and only my coworker witnessed the timeline."
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_gap_types', [])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'candidate_claims': [
                    {
                        'claim_type': 'retaliation',
                        'required_elements': [
                            {
                                'element_id': 'causation',
                                'label': 'Causation',
                                'blocking': True,
                                'evidence_classes': ['witness_testimony'],
                            },
                        ],
                    }
                ],
                'canonical_facts': [{'fact_id': 'fact_001'}],
                'proof_leads': [
                    {
                        'lead_id': 'lead_witness_001',
                        'lead_type': 'witness_testimony',
                        'description': 'Coworker witness can confirm the retaliation timeline.',
                        'element_targets': ['causation'],
                        'recommended_support_kind': 'testimony',
                        'source_quality_target': 'credible_testimony',
                    }
                ],
                'contradiction_queue': [],
                'open_items': [
                    {
                        'open_item_id': 'element:retaliation:causation',
                        'target_claim_type': 'retaliation',
                        'target_element_id': 'causation',
                    }
                ],
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
                'retaliation': {
                    'claim_type': 'retaliation',
                    'validation_status': 'incomplete',
                    'elements': [
                        {
                            'element_id': 'causation',
                            'element_text': 'Causation',
                            'validation_status': 'missing',
                            'recommended_action': 'collect_witness_support',
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
                'retaliation': {
                    'claim_type': 'retaliation',
                    'unresolved_count': 1,
                    'unresolved_elements': [
                        {
                            'element_id': 'causation',
                            'element_text': 'Causation',
                            'recommended_action': 'collect_witness_support',
                            'missing_support_kinds': ['evidence'],
                        }
                    ],
                }
            }
        })

        result = mediator.advance_to_evidence_phase()

        assert result['alignment_evidence_tasks']
        assert result['alignment_evidence_tasks'][0]['preferred_support_kind'] == 'testimony'
        assert result['alignment_evidence_tasks'][0]['resolution_status'] == 'awaiting_testimony'
        assert result['alignment_evidence_tasks'][0]['source_quality_target'] == 'credible_testimony'
        assert result['alignment_evidence_tasks'][0]['preferred_evidence_classes'] == ['witness_testimony']
        assert result['alignment_evidence_tasks'][0]['intake_proof_leads'][0]['lead_id'] == 'lead_witness_001'
        assert result['alignment_evidence_tasks'][0]['recommended_witness_prompts']
        assert result['next_action']['action'] == 'complete_evidence'

    def test_advance_to_evidence_phase_marks_complainant_owned_document_tasks_as_awaiting_record(self):
        """Evidence-phase tasks should mark complainant-controlled records as explicit follow-up escalations."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process(
            "I was fired after complaining, and I have the email chain but have not uploaded it yet."
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_gap_types', [])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'candidate_claims': [
                    {
                        'claim_type': 'retaliation',
                        'required_elements': [
                            {
                                'element_id': 'protected_activity',
                                'label': 'Protected activity',
                                'blocking': True,
                                'evidence_classes': ['email'],
                            },
                        ],
                    }
                ],
                'canonical_facts': [{'fact_id': 'fact_001'}],
                'proof_leads': [
                    {
                        'lead_id': 'lead_email_001',
                        'lead_type': 'email',
                        'description': 'The complainant has the HR complaint email.',
                        'element_targets': ['protected_activity'],
                        'recommended_support_kind': 'evidence',
                        'source_quality_target': 'high_quality_document',
                        'owner': 'complainant',
                        'custodian': 'complainant',
                        'availability': 'available_from_complainant',
                    }
                ],
                'contradiction_queue': [],
                'open_items': [
                    {
                        'open_item_id': 'element:retaliation:protected_activity',
                        'target_claim_type': 'retaliation',
                        'target_element_id': 'protected_activity',
                    }
                ],
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
                'retaliation': {
                    'claim_type': 'retaliation',
                    'validation_status': 'incomplete',
                    'elements': [
                        {
                            'element_id': 'protected_activity',
                            'element_text': 'Protected activity',
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
                'retaliation': {
                    'claim_type': 'retaliation',
                    'unresolved_count': 1,
                    'unresolved_elements': [
                        {
                            'element_id': 'protected_activity',
                            'element_text': 'Protected activity',
                            'recommended_action': 'collect_documentary_support',
                            'missing_support_kinds': ['evidence'],
                        }
                    ],
                }
            }
        })

        result = mediator.advance_to_evidence_phase()

        assert result['alignment_evidence_tasks']
        assert result['alignment_evidence_tasks'][0]['preferred_support_kind'] == 'evidence'
        assert result['alignment_evidence_tasks'][0]['resolution_status'] == 'awaiting_complainant_record'
        assert result['alignment_evidence_tasks'][0]['intake_proof_leads'][0]['availability'] == 'available_from_complainant'
        assert result['next_action']['action'] == 'complete_evidence'

    def test_advance_to_evidence_phase_marks_temporal_rule_gaps_as_chronology_tasks(self):
        """Temporal-rule blockers should become chronology-specific evidence tasks with testimony escalation."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process(
            'I complained, then I was disciplined later, but I need help organizing the dates.'
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_gap_types', [])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'candidate_claims': [
                    {
                        'claim_type': 'retaliation',
                        'required_elements': [
                            {
                                'element_id': 'causation',
                                'label': 'Causal connection',
                                'blocking': True,
                                'evidence_classes': ['witness_testimony'],
                            },
                        ],
                    }
                ],
                'canonical_facts': [{'fact_id': 'fact_001'}],
                'event_ledger': [
                    {
                        'event_id': 'fact_001',
                        'temporal_fact_id': 'fact_001',
                        'claim_types': ['retaliation'],
                        'element_tags': ['causation'],
                        'timeline_anchor_ids': ['anchor_001'],
                    },
                    {
                        'event_id': 'fact_termination',
                        'temporal_fact_id': 'fact_termination',
                        'claim_types': ['retaliation'],
                        'element_tags': ['causation'],
                        'timeline_anchor_ids': ['anchor_termination'],
                    },
                ],
                'timeline_anchors': [
                    {
                        'anchor_id': 'anchor_001',
                        'fact_id': 'fact_001',
                        'anchor_text': 'March 1, 2025',
                    },
                    {
                        'anchor_id': 'anchor_termination',
                        'fact_id': 'fact_termination',
                        'anchor_text': 'March 20, 2025',
                    },
                ],
                'temporal_relation_registry': [
                    {
                        'relation_id': 'timeline_relation_001',
                        'source_fact_id': 'fact_001',
                        'target_fact_id': 'fact_termination',
                        'relation_type': 'before',
                    }
                ],
                'proof_leads': [
                    {
                        'lead_id': 'lead_001',
                        'lead_type': 'testimony',
                        'description': 'Complainant can clarify the chronology of the protected activity and discipline.',
                    }
                ],
                'contradiction_queue': [],
                'open_items': [
                    {
                        'open_item_id': 'element:retaliation:causation',
                        'target_claim_type': 'retaliation',
                        'target_element_id': 'causation',
                    }
                ],
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
                'retaliation': {
                    'claim_type': 'retaliation',
                    'validation_status': 'incomplete',
                    'elements': [
                        {
                            'element_id': 'causation',
                            'element_text': 'Causal connection',
                            'validation_status': 'incomplete',
                            'recommended_action': 'collect_missing_support_kind',
                            'missing_support_kinds': ['evidence'],
                            'contradiction_candidate_count': 0,
                            'proof_gaps': [{'gap_type': 'temporal_rule_partial'}],
                            'proof_gap_count': 1,
                            'proof_decision_trace': {
                                'decision_source': 'temporal_rule_partial',
                                'temporal_rule_status': 'partial',
                            },
                            'reasoning_diagnostics': {
                                'temporal_rule_profile': {
                                    'profile_id': 'retaliation_temporal_profile_v1',
                                    'status': 'partial',
                                    'blocking_reasons': [
                                        'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.',
                                    ],
                                    'recommended_follow_ups': [
                                        {
                                            'lane': 'clarify_with_complainant',
                                            'reason': 'Clarify whether the protected activity occurred before the adverse action.',
                                        }
                                    ],
                                },
                                'temporal_proof_bundle': {
                                    'proof_bundle_id': 'retaliation:causation:retaliation_temporal_profile_v1',
                                    'temporal_fact_ids': ['fact_001', 'fact_termination'],
                                    'temporal_relation_ids': ['timeline_relation_001'],
                                    'temporal_issue_ids': ['temporal_issue_001'],
                                },
                                'temporal_summary': {
                                    'fact_count': 2,
                                    'relation_count': 0,
                                    'issue_count': 1,
                                    'partial_order_ready': False,
                                    'warning_count': 1,
                                },
                            },
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
                'retaliation': {
                    'claim_type': 'retaliation',
                    'unresolved_count': 1,
                    'unresolved_elements': [
                        {
                            'element_id': 'causation',
                            'element_text': 'Causal connection',
                            'recommended_action': 'collect_missing_support_kind',
                            'missing_support_kinds': ['evidence'],
                        }
                    ],
                }
            }
        })

        result = mediator.advance_to_evidence_phase()

        assert result['alignment_evidence_tasks']
        assert result['alignment_evidence_tasks'][0]['action'] == 'fill_temporal_chronology_gap'
        assert result['alignment_evidence_tasks'][0]['preferred_support_kind'] == 'testimony'
        assert result['alignment_evidence_tasks'][0]['resolution_status'] == 'awaiting_testimony'
        assert result['alignment_evidence_tasks'][0]['temporal_rule_status'] == 'partial'
        assert 'event_ids' in result['alignment_evidence_tasks'][0]
        assert result['alignment_evidence_tasks'][0]['anchor_ids'] == ['anchor_001', 'anchor_termination']
        assert 'temporal_relation_ids' in result['alignment_evidence_tasks'][0]
        assert 'timeline_issue_ids' in result['alignment_evidence_tasks'][0]
        assert result['alignment_evidence_tasks'][0]['missing_temporal_predicates'] == ['Before(fact_001,fact_termination)']
        assert result['alignment_evidence_tasks'][0]['required_provenance_kinds'] == [
            'testimony_record',
            'document_artifact',
            'legal_authority',
        ]
        assert 'temporal_proof_bundle_id' in result['alignment_evidence_tasks'][0]
        assert any(
            'Establish chronology:' in item
            for item in result['alignment_evidence_tasks'][0]['success_criteria']
        )

        status = mediator.get_three_phase_status()

        assert status['alignment_evidence_tasks'][0]['action'] == 'fill_temporal_chronology_gap'
        assert status['alignment_evidence_tasks'][0]['anchor_ids'] == ['anchor_001', 'anchor_termination']
        assert status['alignment_task_summary'] == {
            'count': 1,
            'status_counts': {'partially_supported': 1},
            'resolution_status_counts': {'awaiting_testimony': 1},
            'temporal_gap_task_count': 1,
            'temporal_gap_targeted_task_count': 1,
            'temporal_rule_status_counts': {'partial': 1},
            'temporal_rule_blocking_reason_counts': {
                'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.': 1,
            },
            'temporal_resolution_status_counts': {'awaiting_testimony': 1},
        }
        assert status['claim_support_packet_summary']['temporal_gap_task_count'] == 1
        assert status['claim_support_packet_summary']['temporal_gap_targeted_task_count'] == 1
        assert status['claim_support_packet_summary']['temporal_rule_status_counts'] == {'partial': 1}
        assert status['claim_support_packet_summary']['temporal_rule_blocking_reason_counts'] == {
            'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.': 1,
        }
        assert status['claim_support_packet_summary']['temporal_resolution_status_counts'] == {'awaiting_testimony': 1}

    def test_build_claim_support_packets_tracks_partial_fact_bundle_coverage(self):
        """Packet construction should only clear the bundle prompts actually covered by support facts."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'candidate_claims': [
                    {
                        'claim_type': 'retaliation',
                        'required_elements': [
                            {
                                'element_id': 'protected_activity',
                                'label': 'Protected activity',
                                'blocking': True,
                                'evidence_classes': ['email'],
                            }
                        ],
                    }
                ]
            },
        )
        mediator.get_claim_support_validation = Mock(return_value={
            'claims': {
                'retaliation': {
                    'elements': [
                        {
                            'element_id': 'protected_activity',
                            'element_text': 'Protected activity',
                            'validation_status': 'incomplete',
                            'recommended_action': 'collect_documentary_support',
                            'missing_support_kinds': ['evidence'],
                            'contradiction_candidate_count': 0,
                            'proof_diagnostics': {},
                            'gap_context': {
                                'support_facts': [
                                    {
                                        'fact_id': 'fact-pa-1',
                                        'text': 'I complained about discrimination on March 3.',
                                        'support_kind': 'evidence',
                                        'source_family': 'evidence',
                                    }
                                ],
                                'support_traces': [
                                    {
                                        'source_ref': 'artifact:complaint-note',
                                        'support_ref': 'artifact:complaint-note',
                                        'support_label': 'Complaint note',
                                        'support_kind': 'evidence',
                                        'source_family': 'evidence',
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        })
        mediator.get_claim_support_gaps = Mock(return_value={
            'claims': {
                'retaliation': {
                    'unresolved_elements': [
                        {
                            'element_id': 'protected_activity',
                            'element_text': 'Protected activity',
                            'recommended_action': 'collect_documentary_support',
                            'missing_support_kinds': ['evidence'],
                        }
                    ]
                }
            }
        })

        packets = mediator._build_claim_support_packets(user_id='test-user')
        protected_activity = packets['retaliation']['elements'][0]

        assert protected_activity['support_status'] == 'partially_supported'
        assert protected_activity['support_quality'] == 'credible'
        assert protected_activity['required_fact_bundle'] == [
            'What protected activity occurred',
            'When the protected activity occurred',
            'Who received or observed the protected activity',
            'How the protected activity was documented or can be corroborated',
        ]
        assert protected_activity['satisfied_fact_bundle'] == [
            'What protected activity occurred',
            'When the protected activity occurred',
            'How the protected activity was documented or can be corroborated',
        ]
        assert protected_activity['missing_fact_bundle'] == [
            'Who received or observed the protected activity',
        ]

    def test_build_claim_support_packets_clears_supported_bundle_without_fact_text(self):
        """Supported elements should not retain a missing fact bundle just because the trace text is sparse."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'candidate_claims': [
                    {
                        'claim_type': 'employment_discrimination',
                        'required_elements': [
                            {
                                'element_id': 'adverse_action',
                                'label': 'Adverse action',
                                'blocking': True,
                                'evidence_classes': ['termination_letter'],
                            }
                        ],
                    }
                ]
            },
        )
        mediator.get_claim_support_validation = Mock(return_value={
            'claims': {
                'employment_discrimination': {
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
                                'support_facts': [
                                    {
                                        'fact_id': 'fact-aa-1',
                                    }
                                ],
                                'support_traces': [
                                    {
                                        'source_ref': 'artifact:termination-letter',
                                        'support_ref': 'artifact:termination-letter',
                                        'support_label': 'Termination letter',
                                        'support_kind': 'evidence',
                                        'source_family': 'evidence',
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        })
        mediator.get_claim_support_gaps = Mock(return_value={'claims': {}})

        packets = mediator._build_claim_support_packets(user_id='test-user')
        adverse_action = packets['employment_discrimination']['elements'][0]

        assert adverse_action['support_status'] == 'supported'
        assert adverse_action['support_quality'] == 'draft_ready'
        assert adverse_action['missing_fact_bundle'] == []
        assert adverse_action['satisfied_fact_bundle'] == adverse_action['required_fact_bundle']

    def test_process_evidence_denoising_prioritizes_alignment_tasks_in_next_questions(self):
        """Evidence denoising should ask about unresolved shared ontology elements first."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', mediator.kg_builder.build_from_text("I was fired after I complained to HR."))
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', mediator.dg_builder.build_from_claims([{'name': 'Retaliation', 'type': 'retaliation'}], {}))
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_evidence_tasks',
            [
                {
                    'action': 'fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'claim_element_label': 'Protected activity',
                    'support_status': 'unsupported',
                    'blocking': True,
                }
            ],
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gaps', [])

        result = mediator.process_evidence_denoising(
            {'type': 'evidence_clarification', 'question': 'What evidence do you have?', 'context': {}},
            'HR email.',
        )

        assert result['alignment_evidence_tasks'][0]['claim_element_id'] == 'protected_activity'
        assert result['evidence_workflow_action_queue']
        assert result['evidence_workflow_action_summary']['count'] >= 1
        assert result['next_questions']
        assert result['next_questions'][0]['context']['alignment_task'] is True
        assert result['next_questions'][0]['context']['claim_element_id'] == 'protected_activity'

    def test_evidence_status_exposes_workflow_action_queue(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_evidence_tasks',
            [
                {
                    'action': 'fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'causation',
                    'claim_element_label': 'Causal connection',
                    'support_status': 'unsupported',
                    'blocking': True,
                }
            ],
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'evidence_workflow_action_queue',
            [
                {
                    'rank': 1,
                    'phase_name': 'graph_analysis',
                    'status': 'warning',
                    'action': 'fill evidence gaps',
                    'focus_areas': ['causation', 'retaliation'],
                }
            ],
        )

        status = mediator.get_three_phase_status()

        assert status['evidence_workflow_action_queue']
        assert status['evidence_workflow_action_queue'][0]['phase_name'] == 'graph_analysis'
        assert status['evidence_workflow_action_summary']['count'] == 1

    def test_process_evidence_denoising_retires_answered_alignment_task_without_refresh(self):
        """Short answers to alignment-driven evidence prompts should retire the matching task immediately."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', mediator.kg_builder.build_from_text("I complained to HR."))
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', mediator.dg_builder.build_from_claims([{'name': 'Retaliation', 'type': 'retaliation'}], {}))
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_evidence_tasks',
            [
                {
                    'action': 'fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'claim_element_label': 'Protected activity',
                    'support_status': 'unsupported',
                    'blocking': True,
                }
            ],
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gaps', [])

        result = mediator.process_evidence_denoising(
            {
                'type': 'evidence_clarification',
                'question': 'What evidence do you have for protected activity?',
                'context': {
                    'alignment_task': True,
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                },
            },
            'HR email',
        )

        assert result['alignment_evidence_tasks'] == []
        assert result['alignment_task_updates']
        assert result['alignment_task_updates'][0]['resolution_status'] == 'answered_pending_review'
        assert result['alignment_task_updates'][0]['status'] == 'resolved'
        assert result['alignment_task_update_history']
        assert result['alignment_task_update_history'][0]['evidence_sequence'] >= 1
        assert mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks') == []

    def test_evidence_workflow_queue_includes_document_grounding_recovery_action(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'claim_support_packets',
            {'retaliation': {'elements': [{'support_status': 'supported'}]}},
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_provenance_summary',
            {'fact_backed_ratio': 0.25, 'low_grounding_flag': True},
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_grounding_recovery_action',
            {
                'action': 'recover_document_grounding',
                'phase_name': 'document_generation',
                'description': 'Strengthen draft grounding for protected_activity before formalization.',
                'claim_type': 'retaliation',
                'claim_element_id': 'protected_activity',
                'focus_section': 'factual_allegations',
                'preferred_support_kind': 'authority',
                'fact_backed_ratio': 0.25,
                'missing_fact_bundle': ['Complaint timing'],
                'recovery_source': 'alignment_evidence_task',
            },
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks', [])
        mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gaps', [])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'evidence_workflow_action_queue',
            mediator._build_evidence_workflow_action_queue([], []),
        )

        status = mediator.get_three_phase_status()

        assert status['document_grounding_recovery_action']['claim_element_id'] == 'protected_activity'
        assert status['evidence_workflow_action_queue'][0]['action_code'] == 'recover_document_grounding'
        assert status['next_action']['action'] == 'recover_document_grounding'
        assert status['next_action']['claim_element_id'] == 'protected_activity'

    def test_process_evidence_denoising_accepts_short_grounding_recovery_answer(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', mediator.kg_builder.build_from_text("I complained to HR."))
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', mediator.dg_builder.build_from_claims([{'name': 'Retaliation', 'type': 'retaliation'}], {}))
        mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_packets', {'retaliation': {'elements': [{'support_status': 'supported'}]}})
        mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks', [])
        mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gaps', [])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_provenance_summary',
            {'fact_backed_ratio': 0.2, 'low_grounding_flag': True},
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_grounding_recovery_action',
            {
                'action': 'recover_document_grounding',
                'phase_name': 'document_generation',
                'description': 'Strengthen draft grounding for protected_activity before formalization.',
                'claim_type': 'retaliation',
                'claim_element_id': 'protected_activity',
                'focus_section': 'factual_allegations',
                'preferred_support_kind': 'authority',
                'fact_backed_ratio': 0.2,
                'missing_fact_bundle': ['Complaint timing'],
                'recovery_source': 'alignment_evidence_task',
            },
        )

        calls = []

        def fake_add_evidence(evidence_data):
            calls.append(evidence_data)
            return {'added': True}

        mediator.add_evidence_to_graphs = fake_add_evidence

        result = mediator.process_evidence_denoising(
            {
                'type': 'evidence_clarification',
                'question': 'What legal authority, policy, or official document can ground Protected activity for retaliation?',
                'context': {
                    'workflow_action': True,
                    'document_grounding_recovery': True,
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'preferred_support_kind': 'authority',
                },
            },
            'HR email',
        )

        assert calls
        assert calls[0]['claim_element_id'] == 'protected_activity'
        assert calls[0]['preferred_support_kind'] == 'authority'
        assert result['document_grounding_recovery_action']['claim_element_id'] == 'protected_activity'

    def test_grounding_improvement_action_drives_alternate_support_lane_in_evidence_queue(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_provenance_summary',
            {'fact_backed_ratio': 0.25, 'low_grounding_flag': True},
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_grounding_recovery_action',
            {
                'action': 'recover_document_grounding',
                'phase_name': 'document_generation',
                'description': 'Strengthen draft grounding for protected_activity before formalization.',
                'claim_type': 'retaliation',
                'claim_element_id': 'protected_activity',
                'focus_section': 'factual_allegations',
                'preferred_support_kind': 'authority',
                'fact_backed_ratio': 0.25,
                'missing_fact_bundle': ['Complaint timing'],
                'recovery_source': 'alignment_evidence_task',
            },
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_grounding_improvement_summary',
            {
                'initial_fact_backed_ratio': 0.25,
                'final_fact_backed_ratio': 0.25,
                'fact_backed_ratio_delta': 0.0,
                'stalled_flag': True,
                'targeted_claim_elements': ['protected_activity'],
                'preferred_support_kinds': ['authority'],
                'recovery_attempted_flag': True,
            },
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_grounding_lane_outcome_summary',
            {
                'recommended_future_support_kind': 'testimony',
            },
        )

        queue = mediator._build_evidence_workflow_action_queue([], [])

        assert queue[0]['action_code'] == 'refine_document_grounding_strategy'
        assert queue[0]['preferred_support_kind'] == 'authority'
        assert queue[0]['learned_support_kind'] == 'testimony'
        assert queue[0]['learned_support_lane_priority'] is True
        assert queue[0]['suggested_support_kind'] == 'testimony'

    def test_evidence_workflow_queue_retargets_after_failed_learned_grounding_lane(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'claim_support_packets',
            {'retaliation': {'elements': [{'support_status': 'supported'}]}},
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_provenance_summary',
            {'fact_backed_ratio': 0.25, 'low_grounding_flag': True},
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_grounding_recovery_action',
            {
                'action': 'recover_document_grounding',
                'phase_name': 'document_generation',
                'description': 'Strengthen draft grounding for protected_activity before formalization.',
                'claim_type': 'retaliation',
                'claim_element_id': 'protected_activity',
                'focus_section': 'factual_allegations',
                'preferred_support_kind': 'authority',
                'fact_backed_ratio': 0.25,
                'missing_fact_bundle': ['Complaint timing'],
                'recovery_source': 'alignment_evidence_task',
            },
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_grounding_improvement_summary',
            {
                'initial_fact_backed_ratio': 0.25,
                'final_fact_backed_ratio': 0.24,
                'fact_backed_ratio_delta': -0.01,
                'regressed_flag': True,
                'targeted_claim_elements': ['protected_activity', 'causation'],
                'preferred_support_kinds': ['authority'],
                'recovery_attempted_flag': True,
            },
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.FORMALIZATION,
            'document_grounding_lane_outcome_summary',
            {
                'recommended_future_support_kind': 'testimony',
                'learned_support_lane_attempted_flag': True,
                'learned_support_lane_effective_flag': False,
            },
        )

        queue = mediator._build_evidence_workflow_action_queue([], [])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'evidence_workflow_action_queue',
            queue,
        )
        status = mediator.get_three_phase_status()

        assert queue[0]['action_code'] == 'retarget_document_grounding'
        assert queue[0]['claim_element_id'] == 'protected_activity'
        assert queue[0]['suggested_claim_element_id'] == 'causation'
        assert queue[0]['preferred_support_kind'] == 'authority'
        assert queue[0]['learned_support_kind'] == 'testimony'
        assert queue[0]['learned_support_lane_priority'] is True
        assert status['next_action']['action'] == 'retarget_document_grounding'
        assert status['next_action']['claim_element_id'] == 'protected_activity'
        assert status['next_action']['suggested_claim_element_id'] == 'causation'

    def test_process_evidence_denoising_uses_suggested_support_lane_for_grounding_refinement(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', mediator.kg_builder.build_from_text("I complained to HR."))
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', mediator.dg_builder.build_from_claims([{'name': 'Retaliation', 'type': 'retaliation'}], {}))

        calls = []

        def fake_add_evidence(evidence_data):
            calls.append(evidence_data)
            return {'added': True}

        mediator.add_evidence_to_graphs = fake_add_evidence

        mediator.process_evidence_denoising(
            {
                'type': 'evidence_clarification',
                'question': 'The last grounding pass did not improve enough. What first-hand testimony or witness detail can better ground Protected activity for retaliation?',
                'context': {
                    'workflow_action': True,
                    'document_grounding_strategy_refinement': True,
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'preferred_support_kind': 'authority',
                    'suggested_support_kind': 'testimony',
                },
            },
            'I told HR directly on January 5.',
        )

        assert calls
        assert calls[0]['claim_element_id'] == 'protected_activity'
        assert calls[0]['preferred_support_kind'] == 'testimony'
        assert calls[0]['original_preferred_support_kind'] == 'authority'
        assert calls[0]['suggested_support_kind'] == 'testimony'

    def test_process_evidence_denoising_prefers_learned_support_lane_for_grounding_refinement(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', mediator.kg_builder.build_from_text("I complained to HR."))
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', mediator.dg_builder.build_from_claims([{'name': 'Retaliation', 'type': 'retaliation'}], {}))

        calls = []

        def fake_add_evidence(evidence_data):
            calls.append(evidence_data)
            return {'added': True}

        mediator.add_evidence_to_graphs = fake_add_evidence

        mediator.process_evidence_denoising(
            {
                'type': 'evidence_clarification',
                'question': 'The last grounding pass did not improve enough. What first-hand testimony or witness detail can better ground Protected activity for retaliation?',
                'context': {
                    'workflow_action': True,
                    'document_grounding_strategy_refinement': True,
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'preferred_support_kind': 'authority',
                    'learned_support_kind': 'testimony',
                    'suggested_support_kind': 'evidence',
                },
            },
            'I told HR directly on January 5.',
        )

        assert calls
        assert calls[0]['claim_element_id'] == 'protected_activity'
        assert calls[0]['preferred_support_kind'] == 'testimony'
        assert calls[0]['original_preferred_support_kind'] == 'authority'
        assert calls[0]['learned_support_kind'] == 'testimony'
        assert calls[0]['suggested_support_kind'] == 'evidence'

    def test_process_evidence_denoising_uses_learned_lane_for_grounding_retargeting(self):
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', mediator.kg_builder.build_from_text("I complained to HR."))
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', mediator.dg_builder.build_from_claims([{'name': 'Retaliation', 'type': 'retaliation'}], {}))

        calls = []

        def fake_add_evidence(evidence_data):
            calls.append(evidence_data)
            return {'added': True}

        mediator.add_evidence_to_graphs = fake_add_evidence

        mediator.process_evidence_denoising(
            {
                'type': 'evidence_clarification',
                'question': 'The learned testimony lane still did not improve grounding enough. What more specific fact, date, witness detail, or document can narrow the grounding gap for Protected activity in retaliation?',
                'context': {
                    'workflow_action': True,
                    'document_grounding_retargeting': True,
                    'claim_type': 'retaliation',
                    'claim_element_id': 'causation',
                    'original_claim_element_id': 'protected_activity',
                    'suggested_claim_element_id': 'causation',
                    'preferred_support_kind': 'authority',
                    'learned_support_kind': 'testimony',
                    'suggested_support_kind': 'evidence',
                },
            },
            'My coworker heard me complain to HR on March 3.',
        )

        assert calls
        assert calls[0]['claim_element_id'] == 'causation'
        assert calls[0]['preferred_support_kind'] == 'testimony'
        assert calls[0]['original_preferred_support_kind'] == 'authority'
        assert calls[0]['learned_support_kind'] == 'testimony'
        assert calls[0]['suggested_support_kind'] == 'evidence'

    def test_process_evidence_and_legal_denoising_include_confirmed_intake_handoff(self):
        """Evidence and formalization workflow payloads should preserve the confirmed intake handoff."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.start_three_phase_process(
            'I was fired after I complained about discrimination and I have emails and a termination letter.'
        )
        mediator.confirm_intake_summary('summary reviewed with complainant')
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])
        mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_gap_types', [])
        mediator.phase_manager._phase_completion_checks[ComplaintPhase.EVIDENCE] = lambda: True

        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_evidence_tasks',
            [
                {
                    'action': 'fill_evidence_gaps',
                    'claim_type': 'employment_discrimination',
                    'claim_element_id': 'adverse_action',
                    'claim_element_label': 'Adverse action',
                    'support_status': 'unsupported',
                    'blocking': True,
                }
            ],
        )
        mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gaps', [])
        evidence_result = mediator.process_evidence_denoising(
            {
                'type': 'evidence_clarification',
                'question': 'What documents support the complaint?',
                'context': {
                    'alignment_task': True,
                    'claim_type': 'employment_discrimination',
                    'claim_element_id': 'adverse_action',
                },
            },
            'Emails.',
        )

        assert evidence_result['intake_summary_handoff']['current_phase'] == ComplaintPhase.EVIDENCE.value
        assert evidence_result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True

        formalization_result = mediator.advance_to_formalization_phase()

        assert formalization_result['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
        assert formalization_result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True

        legal_result = mediator.process_legal_denoising(
            {
                'type': 'legal_requirement',
                'question': 'What law supports this claim?',
                'context': {},
            },
            'Title VII supports the discrimination claim.',
        )

        assert legal_result['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
        assert legal_result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True

    def test_save_claim_testimony_record_promotes_answered_pending_review_update(self):
        """Saving testimony should advance matching answered-pending-review alignment updates."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_updates',
            [
                {
                    'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'action': 'fill_evidence_gaps',
                    'resolution_status': 'answered_pending_review',
                    'status': 'resolved',
                    'answer_preview': 'HR email',
                }
            ],
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_update_history',
            [
                {
                    'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'resolution_status': 'answered_pending_review',
                    'status': 'resolved',
                    'evidence_sequence': 1,
                    'answer_preview': 'HR email',
                }
            ],
        )
        mediator.claim_support.save_testimony_record = Mock(return_value={
            'recorded': True,
            'testimony_id': 'testimony:retaliation:1',
        })

        result = mediator.save_claim_testimony_record(
            claim_type='retaliation',
            claim_element_id='protected_activity',
            claim_element_text='Protected activity',
            raw_narrative='HR email',
        )

        assert result['recorded'] is True
        current_updates = mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates')
        assert current_updates[0]['resolution_status'] == 'promoted_to_testimony'
        assert current_updates[0]['promotion_ref'] == 'testimony:retaliation:1'
        history = mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history')
        assert history[-1]['resolution_status'] == 'promoted_to_testimony'
        assert history[-1]['evidence_sequence'] == 2

    def test_save_claim_support_document_promotes_answered_pending_review_update(self):
        """Saving a document should advance matching answered-pending-review alignment updates."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_updates',
            [
                {
                    'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'action': 'fill_evidence_gaps',
                    'resolution_status': 'answered_pending_review',
                    'status': 'resolved',
                    'answer_preview': 'HR email attachment',
                }
            ],
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_update_history',
            [
                {
                    'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'resolution_status': 'answered_pending_review',
                    'status': 'resolved',
                    'evidence_sequence': 3,
                    'answer_preview': 'HR email attachment',
                }
            ],
        )
        mediator.submit_evidence = Mock(return_value={
            'record_id': 'doc-record-1',
            'artifact_id': 'artifact-1',
            'claim_element_id': 'protected_activity',
        })

        result = mediator.save_claim_support_document(
            claim_type='retaliation',
            claim_element_id='protected_activity',
            claim_element_text='Protected activity',
            document_text='HR email attachment',
            document_label='HR email',
        )

        assert result['recorded'] is True
        current_updates = mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates')
        assert current_updates[0]['resolution_status'] == 'promoted_to_document'
        assert current_updates[0]['promotion_ref'] == 'doc-record-1'
        history = mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history')
        assert history[-1]['resolution_status'] == 'promoted_to_document'
        assert history[-1]['evidence_sequence'] == 4

    def test_save_claim_support_document_promotes_answered_pending_review_update(self):
        """Saving a document should advance matching answered-pending-review alignment updates."""
        from mediator.mediator import Mediator
        from unittest.mock import Mock

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_updates',
            [
                {
                    'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'action': 'fill_evidence_gaps',
                    'resolution_status': 'answered_pending_review',
                    'status': 'resolved',
                    'answer_preview': 'Complaint email attachment',
                }
            ],
        )
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_update_history',
            [
                {
                    'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'resolution_status': 'answered_pending_review',
                    'status': 'resolved',
                    'evidence_sequence': 3,
                    'answer_preview': 'Complaint email attachment',
                }
            ],
        )
        mediator.submit_evidence = Mock(return_value={
            'record_id': 'doc:retaliation:1',
            'artifact_id': 'artifact:retaliation:1',
            'claim_element_id': 'protected_activity',
        })

        result = mediator.save_claim_support_document(
            claim_type='retaliation',
            claim_element_id='protected_activity',
            claim_element_text='Protected activity',
            document_text='Complaint email attachment',
            document_label='Complaint email',
        )

        assert result['recorded'] is True
        current_updates = mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates')
        assert current_updates[0]['resolution_status'] == 'promoted_to_document'
        assert current_updates[0]['promotion_ref'] == 'doc:retaliation:1'
        history = mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history')
        assert history[-1]['resolution_status'] == 'promoted_to_document'
        assert history[-1]['evidence_sequence'] == 4

    def test_get_three_phase_status_includes_recent_validation_outcome(self):
        """Status should expose the latest promoted or validated outcome for non-browser consumers."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_update_history',
            [
                {
                    'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'resolution_status': 'promoted_to_document',
                    'current_support_status': 'partially_supported',
                    'promotion_kind': 'document',
                    'promotion_ref': 'doc:retaliation:1',
                    'evidence_sequence': 3,
                },
                {
                    'task_id': 'retaliation:protected_activity:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'resolution_status': 'resolved_supported',
                    'current_support_status': 'resolved_supported',
                    'promotion_kind': 'document',
                    'promotion_ref': 'doc:retaliation:1',
                    'evidence_sequence': 4,
                },
            ],
        )

        status = mediator.get_three_phase_status()

        assert status['recent_validation_outcome']['claim_type'] == 'retaliation'
        assert status['recent_validation_outcome']['claim_element_id'] == 'protected_activity'
        assert status['recent_validation_outcome']['resolution_status'] == 'resolved_supported'
        assert status['recent_validation_outcome']['evidence_sequence'] == 4
        assert status['recent_validation_outcome']['improved'] is True

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

    def test_start_three_phase_process_allows_selector_override_to_reorder_questions(self):
        """Mediator should expose a selector seam so an upstream router can choose among candidates."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])

        def selector(candidates, max_questions=10):
            evidence_first = [candidate for candidate in candidates if candidate.get('type') == 'evidence']
            remainder = [candidate for candidate in candidates if candidate.get('type') != 'evidence']
            return (evidence_first + remainder)[:max_questions]

        mediator.select_intake_question_candidates = selector
        result = mediator.start_three_phase_process(
            "My employer discriminated against me because of my race."
        )

        assert result['initial_questions']
        assert result['initial_questions'][0]['type'] == 'evidence'

    def test_default_selector_attaches_reasoning_scores_to_selected_questions(self):
        """Default mediator selection should annotate chosen intake questions with reasoning signals."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        result = mediator.start_three_phase_process(
            "My employer discriminated against me because of my race."
        )

        assert result['initial_questions']
        first_question = result['initial_questions'][0]
        assert 'selector_score' in first_question
        assert 'selector_signals' in first_question
        assert 'selector_score' in first_question['ranking_explanation']
        assert first_question['selector_signals']['proof_priority'] == first_question['proof_priority']
        assert 'matcher_missing_requirement_count' in first_question['selector_signals']
        assert 'matcher_confidence' in first_question['selector_signals']
        assert 'matcher_missing_requirement_element_ids' in first_question['selector_signals']
        assert result['intake_matching_summary']['claim_count'] >= 1

    def test_default_selector_prioritizes_contradiction_candidates(self):
        """Reasoning-backed selection should keep contradiction resolution ahead of lower-pressure prompts."""
        from mediator.mediator import Mediator
        from complaint_phases.knowledge_graph import KnowledgeGraph, Entity
        from complaint_phases.dependency_graph import DependencyGraph, DependencyNode, Dependency, NodeType, DependencyType

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        kg = KnowledgeGraph()
        kg.add_entity(Entity("claim1", "claim", "Retaliation Claim", attributes={"claim_type": "retaliation"}))

        dg = DependencyGraph()
        left_fact = DependencyNode("n1", NodeType.FACT, "Complaint happened first")
        right_fact = DependencyNode("n2", NodeType.FACT, "Termination happened first")
        claim = DependencyNode("n3", NodeType.CLAIM, "Retaliation Claim", attributes={"claim_type": "retaliation"})
        dg.add_node(left_fact)
        dg.add_node(right_fact)
        dg.add_node(claim)
        dg.add_dependency(Dependency("d1", "n1", "n2", DependencyType.CONTRADICTS, required=False))

        intake_case_file = {
            "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "required_elements": []}],
            "proof_leads": [],
        }

        questions = mediator.denoiser.generate_questions(kg, dg, max_questions=5, intake_case_file=intake_case_file)

        assert questions
        assert questions[0]['type'] == 'contradiction'
        assert questions[0]['selector_signals']['candidate_source'] == 'dependency_graph_contradiction'
        assert 'matcher_missing_requirement_count' in questions[0]['selector_signals']

    def test_default_selector_marks_direct_legal_target_match_for_missing_element_question(self):
        """A question that targets an unresolved legal element should carry a direct-match selector signal."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        result = mediator.start_three_phase_process(
            "My employer discriminated against me."
        )

        matching_summary = result['intake_matching_summary']
        employment_summary = matching_summary['claims'].get('employment_discrimination', {})
        assert employment_summary['missing_requirement_element_ids']

        direct_match_questions = [
            question for question in result['initial_questions']
            if question.get('selector_signals', {}).get('direct_legal_target_match')
        ]

        assert direct_match_questions
        assert direct_match_questions[0]['target_element_id'] in employment_summary['missing_requirement_element_ids']
        legal_targeting_summary = result['intake_legal_targeting_summary']
        employment_targeting = legal_targeting_summary['claims'].get('employment_discrimination', {})
        assert employment_targeting['mapped_candidates']
        assert employment_targeting['mapped_candidates'][0]['target_element_id'] in employment_summary['missing_requirement_element_ids']

    def test_default_selector_prefers_graph_blocker_closure_question_when_scores_are_close(self):
        """Graph-blocker closure questions should outrank generic intake prompts when other pressure signals are similar."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        candidates = [
            {
                'question': 'What remedy are you seeking now?',
                'type': 'remedy',
                'question_objective': 'identify_requested_relief',
                'proof_priority': 2,
                'candidate_source': 'intake_proof_gap',
                'ranking_explanation': {
                    'blocking_level': 'important',
                    'question_goal': 'identify_supporting_proof',
                    'phase1_section': 'intake_questioning',
                    'candidate_source': 'intake_proof_gap',
                },
            },
            {
                'question': 'On what exact date did you request the hearing, and on what date did HACC respond?',
                'type': 'timeline',
                'question_objective': 'establish_chronology',
                'proof_priority': 2,
                'candidate_source': 'dependency_graph_requirement',
                'ranking_explanation': {
                    'blocking_level': 'important',
                    'question_goal': 'establish_element',
                    'phase1_section': 'graph_analysis',
                    'candidate_source': 'dependency_graph_requirement',
                },
            },
        ]

        selected = mediator.select_intake_question_candidates(candidates, max_questions=2)

        assert selected[0]['question'].startswith('On what exact date')
        assert selected[0]['selector_signals']['phase_focus_rank'] == 0
        assert selected[0]['selector_signals']['exact_dates_closure_match'] is True
        assert selected[0]['selector_signals']['hearing_request_timing_closure_match'] is True
        assert selected[0]['selector_signals']['response_dates_closure_match'] is True
        assert selected[0]['selector_signals']['blocker_closure_match_count'] >= 2

    def test_collect_question_candidates_adds_claim_temporal_gap_candidates_from_intake_registry(self):
        """Temporal issue registry entries should produce mediator-native claim chronology questions."""
        from complaint_phases.knowledge_graph import KnowledgeGraph
        from complaint_phases.dependency_graph import DependencyGraph

        denoiser = ComplaintDenoiser()
        intake_case_file = {
            'candidate_claims': [
                {
                    'claim_type': 'retaliation',
                    'label': 'Retaliation',
                    'required_elements': [],
                }
            ],
            'proof_leads': [],
            'temporal_issue_registry': [
                {
                    'issue_id': 'temporal_issue:relative_only_ordering:fact_3',
                    'issue_type': 'relative_only_ordering',
                    'category': 'relative_only_ordering',
                    'summary': 'Timeline fact fact_3 only has relative ordering (after) and still needs anchoring.',
                    'severity': 'blocking',
                    'blocking': True,
                    'recommended_resolution_lane': 'clarify_with_complainant',
                    'fact_ids': ['fact_3'],
                    'claim_types': ['retaliation'],
                    'element_tags': ['causation'],
                    'left_node_name': 'Supervisor acted after the complaint.',
                    'right_node_name': None,
                    'status': 'open',
                    'relative_markers': ['after'],
                }
            ],
        }

        candidates = denoiser.collect_question_candidates(
            KnowledgeGraph(),
            DependencyGraph(),
            max_questions=5,
            intake_case_file=intake_case_file,
        )

        temporal_candidates = [
            candidate for candidate in candidates
            if candidate.get('candidate_source') == 'intake_claim_temporal_gap'
        ]

        assert temporal_candidates
        first_candidate = temporal_candidates[0]
        assert first_candidate['type'] == 'timeline'
        assert first_candidate['target_claim_type'] == 'retaliation'
        assert first_candidate['target_element_id'] == 'causation'
        assert first_candidate['workflow_phase'] == 'graph_analysis'
        assert (
            'chronology_gap' in first_candidate['follow_up_tags']
            or 'exact_dates' in first_candidate['follow_up_tags']
        )
        assert 'exact date' in first_candidate['question'].lower() or 'timeframe' in first_candidate['question'].lower()

    def test_default_selector_prefers_claim_temporal_gap_candidate_over_generic_prompt(self):
        """Claim-temporal-gap prompts should outrank generic intake prompts when chronology and causation remain unresolved."""
        from mediator.mediator import Mediator

        class MockBackend:
            id = 'mock_backend'

        mediator = Mediator([MockBackend()])
        chronology_candidate = mediator.denoiser._question_candidate(
            source='intake_claim_temporal_gap',
            question_type='timeline',
            question_text=(
                'For your retaliation claim, what protected activity happened first, what adverse action followed, '
                'who was involved in each step, and on what exact dates did those events occur?'
            ),
            context={
                'claim_type': 'retaliation',
                'claim_name': 'Retaliation',
                'target_element_id': 'causation',
                'workflow_phase': 'graph_analysis',
            },
            priority='high',
        )
        chronology_candidate['question_objective'] = 'establish_causation'
        chronology_candidate['question_goal'] = 'establish_element'
        chronology_candidate['ranking_explanation']['question_objective'] = 'establish_causation'
        chronology_candidate['ranking_explanation']['question_goal'] = 'establish_element'

        generic_candidate = mediator.denoiser._question_candidate(
            source='intake_proof_gap',
            question_type='remedy',
            question_text='What outcome are you hoping for?',
            context={
                'claim_type': 'retaliation',
                'claim_name': 'Retaliation',
                'workflow_phase': 'intake_questioning',
            },
            priority='high',
        )

        selected = mediator.select_intake_question_candidates(
            [generic_candidate, chronology_candidate],
            max_questions=2,
        )

        assert selected[0]['candidate_source'] == 'intake_claim_temporal_gap'
        assert selected[0]['question_goal'] == 'establish_element'
        assert selected[0]['selector_score'] > selected[1]['selector_score']

    def test_intake_selector_uses_workflow_action_queue_to_boost_graph_priority(self):
        from mediator.mediator import Mediator

        class MockBackend:
            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.INTAKE,
            'adversarial_intake_priority_summary',
            {
                'expected_objectives': ['causation_sequence'],
                'covered_objectives': [],
                'uncovered_objectives': ['causation_sequence'],
            },
        )
        chronology_candidate = mediator.denoiser._question_candidate(
            source='intake_claim_temporal_gap',
            question_type='timeline',
            question_text=(
                'For your retaliation claim, what protected activity happened first, what adverse action followed, '
                'who was involved in each step, and on what exact dates did those events occur?'
            ),
            context={
                'claim_type': 'retaliation',
                'claim_name': 'Retaliation',
                'gap_id': 'retaliation:causation',
                'gap_type': 'retaliation_missing_causation_link',
                'requirement_id': 'causation',
                'target_element_id': 'causation',
                'workflow_phase': 'graph_analysis',
                'recommended_resolution_lane': 'clarify_with_complainant',
                'extraction_targets': ['protected_activity', 'adverse_action', 'causation_link', 'exact_dates', 'event_order'],
                'patchability_markers': ['chronology_patch_anchor', 'adverse_action_patch_anchor'],
            },
            priority='high',
        )
        chronology_candidate['question_objective'] = 'establish_causation'
        chronology_candidate['question_goal'] = 'establish_element'
        chronology_candidate['ranking_explanation']['question_objective'] = 'establish_causation'
        chronology_candidate['ranking_explanation']['question_goal'] = 'establish_element'

        generic_candidate = mediator.denoiser._question_candidate(
            source='intake_proof_gap',
            question_type='remedy',
            question_text='What outcome are you hoping for?',
            context={
                'claim_type': 'retaliation',
                'claim_name': 'Retaliation',
                'workflow_phase': 'intake_questioning',
            },
            priority='high',
        )

        selected = mediator.select_intake_question_candidates(
            [generic_candidate, chronology_candidate],
            max_questions=2,
        )

        assert selected[0]['candidate_source'] == 'intake_claim_temporal_gap'
        assert selected[0]['selector_signals']['causation_sequence_match'] is True
        assert selected[0]['selector_signals']['exact_dates_closure_match'] is True
        assert selected[0]['selector_signals']['intake_priority_match_count'] >= 1
        assert selected[0]['selector_score'] > selected[1]['selector_score']

    def test_intake_selector_uses_partial_intake_case_file_to_boost_graph_priority(self):
        from mediator.mediator import Mediator

        class MockBackend:
            def __call__(self, prompt):
                return 'Mock response'

        mediator = Mediator([MockBackend()])
        mediator.phase_manager.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'intake_sections': {
                    'chronology': {'status': 'partial'},
                    'proof_leads': {'status': 'partial'},
                },
            },
        )
        candidates = [
            {
                'question': 'What documents do you have to support your complaint?',
                'type': 'evidence',
                'question_objective': 'identify_supporting_evidence',
                'proof_priority': 1,
                'candidate_source': 'intake_proof_gap',
                'ranking_explanation': {
                    'blocking_level': 'important',
                    'question_goal': 'identify_supporting_proof',
                    'phase1_section': 'proof_leads',
                    'candidate_source': 'intake_proof_gap',
                },
            },
            {
                'question': 'On what exact date did the supervisor deny your request, and when did the response arrive?',
                'type': 'timeline',
                'question_objective': 'establish_chronology',
                'proof_priority': 3,
                'candidate_source': 'dependency_graph_requirement',
                'ranking_explanation': {
                    'blocking_level': 'important',
                    'question_goal': 'establish_element',
                    'phase1_section': 'graph_analysis',
                    'candidate_source': 'dependency_graph_requirement',
                    'target_claim_type': 'retaliation',
                },
            },
        ]

        selected = mediator.select_intake_question_candidates(candidates, max_questions=2)

        assert selected[0]['type'] == 'timeline'
        assert selected[0]['selector_signals']['workflow_action_match_count'] >= 1
        assert selected[0]['selector_signals']['workflow_action_phase'] == 'graph_analysis'
        assert selected[0]['selector_signals']['workflow_action_rank'] == 1
    
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
