"""
Tests for enhanced denoising across all three phases and synthesis
"""

import pytest
from complaint_phases import (
    KnowledgeGraphBuilder,
    DependencyGraphBuilder,
    ComplaintDenoiser
)


class TestPhase2Denoising:
    """Test denoising in evidence phase."""
    
    def test_evidence_denoising_questions(self):
        """Test generating evidence denoising questions."""
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        denoiser = ComplaintDenoiser()
        
        # Build initial graphs
        complaint = "I was fired unfairly by TechCorp."
        kg = kg_builder.build_from_text(complaint)
        claims = [{'name': 'Wrongful Termination', 'type': 'employment'}]
        dg = dg_builder.build_from_claims(claims)
        
        # Create evidence gaps
        evidence_gaps = [
            {'id': 'gap1', 'name': 'termination letter', 'related_claim': 'claim_1'},
            {'id': 'gap2', 'name': 'performance reviews', 'related_claim': 'claim_1'}
        ]
        
        # Generate evidence questions
        questions = denoiser.generate_evidence_questions(kg, dg, evidence_gaps, max_questions=5)
        
        assert len(questions) > 0
        assert any(q['type'] == 'evidence_clarification' for q in questions)
        assert all('context' in q for q in questions)
    
    def test_evidence_quality_questions(self):
        """Test questions about evidence quality."""
        from complaint_phases.knowledge_graph import Entity
        
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        denoiser = ComplaintDenoiser()
        
        complaint = "I was fired."
        kg = kg_builder.build_from_text(complaint)
        
        # Add low-confidence evidence
        evidence = Entity(
            id='evidence_1',
            type='evidence',
            name='Email from boss',
            confidence=0.5,  # Low confidence
            attributes={'description': 'Vague email'}
        )
        kg.add_entity(evidence)
        
        dg = dg_builder.build_from_claims([])
        
        questions = denoiser.generate_evidence_questions(kg, dg, [], max_questions=5)
        
        # Should generate quality questions for low-confidence evidence
        quality_questions = [q for q in questions if q['type'] == 'evidence_quality']
        assert len(quality_questions) > 0

    def test_evidence_questions_use_alignment_task_preferences(self):
        """Alignment tasks should produce task-aware evidence questions and context."""
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        denoiser = ComplaintDenoiser()

        kg = kg_builder.build_from_text("I complained to HR and was later terminated.")
        dg = dg_builder.build_from_claims([{'name': 'Retaliation', 'type': 'retaliation'}])

        questions = denoiser.generate_evidence_questions(
            kg,
            dg,
            [],
            alignment_evidence_tasks=[
                {
                    'action': 'fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'claim_element_label': 'Protected activity',
                    'support_status': 'unsupported',
                    'blocking': True,
                    'preferred_support_kind': 'evidence',
                    'preferred_evidence_classes': ['email', 'hr_complaint', 'text_message'],
                    'missing_fact_bundle': ['who received the complaint'],
                    'success_criteria': ['Element Protected activity reaches supported status'],
                    'recommended_queries': ['"retaliation" "Protected activity" who received the complaint'],
                }
            ],
            max_questions=3,
        )

        assert questions
        assert 'email, hr complaint, text message' in questions[0]['question'].lower()
        assert 'who received the complaint' in questions[0]['question'].lower()
        assert questions[0]['context']['preferred_support_kind'] == 'evidence'
        assert questions[0]['context']['preferred_evidence_classes'] == ['email', 'hr_complaint', 'text_message']
        assert questions[0]['context']['missing_fact_bundle'] == ['who received the complaint']

    def test_question_candidate_carries_workflow_routing_metadata_for_graph_blockers(self):
        denoiser = ComplaintDenoiser()

        candidate = denoiser._question_candidate(
            question_text="When did you request the hearing, and when did HACC respond?",
            question_type="timeline",
            source="dependency_graph_requirement",
            context={"gap_type": "missing_hearing_timing"},
            priority="high",
        )

        assert candidate["workflow_phase"] == "graph_analysis"
        assert candidate["workflow_phase_rank"] == 0
        assert "exact_dates" in candidate["follow_up_tags"]
        assert "exact_dates" in candidate["extraction_targets"]
        assert "event_order" in candidate["extraction_targets"]
        assert "chronology_patch_anchor" in candidate["patchability_markers"]


class TestPhase3Denoising:
    """Test denoising in formalization phase."""
    
    def test_legal_matching_questions(self):
        """Test generating legal matching denoising questions."""
        denoiser = ComplaintDenoiser()
        
        # Simulate matching results with unmatched requirements
        matching_results = {
            'unmatched_requirements': [
                {
                    'id': 'req1',
                    'name': 'Proof of protected class',
                    'element_type': 'discrimination',
                    'missing_info': 'documentation of protected class status'
                }
            ],
            'matches': [
                {
                    'claim_id': 'claim1',
                    'claim_name': 'Discrimination',
                    'requirement_name': 'Adverse action',
                    'confidence': 0.4  # Weak match
                }
            ]
        }
        
        questions = denoiser.generate_legal_matching_questions(matching_results, max_questions=5)
        
        assert len(questions) > 0
        assert any(q['type'] == 'legal_requirement' for q in questions)
        assert any(q['type'] == 'legal_strengthening' for q in questions)
    
    def test_legal_strengthening_questions(self):
        """Test questions to strengthen weak legal matches."""
        denoiser = ComplaintDenoiser()
        
        matching_results = {
            'unmatched_requirements': [],
            'matches': [
                {'claim_id': 'c1', 'claim_name': 'Claim A', 'confidence': 0.3},
                {'claim_id': 'c2', 'claim_name': 'Claim B', 'confidence': 0.5},
                {'claim_id': 'c3', 'claim_name': 'Claim C', 'confidence': 0.9}  # Strong
            ]
        }
        
        questions = denoiser.generate_legal_matching_questions(matching_results, max_questions=5)
        
        # Should focus on weak matches
        strengthen_questions = [q for q in questions if q['type'] == 'legal_strengthening']
        assert len(strengthen_questions) >= 2  # At least 2 weak matches


class TestSynthesis:
    """Test complaint synthesis from graphs."""
    
    def test_synthesize_complaint_summary(self):
        """Test synthesizing human-readable summary."""
        from complaint_phases.knowledge_graph import Entity, Relationship
        
        kg_builder = KnowledgeGraphBuilder()
        denoiser = ComplaintDenoiser()
        
        complaint = "I was discriminated against by TechCorp."
        kg = kg_builder.build_from_text(complaint)
        
        # Add some rich data
        person = Entity('person_1', 'person', 'John Doe', {'role': 'complainant'}, 0.9)
        org = Entity('org_1', 'organization', 'TechCorp', {'role': 'employer'}, 0.9)
        claim = Entity('claim_1', 'claim', 'Discrimination', {
            'claim_type': 'employment_discrimination',
            'description': 'Age-based discrimination'
        }, 0.8)
        fact = Entity('fact_1', 'fact', 'Fired after 20 years', {}, 0.85)
        evidence = Entity('evidence_1', 'evidence', 'Termination letter', {
            'type': 'document',
            'description': 'Letter citing age'
        }, 0.9)
        
        kg.add_entity(person)
        kg.add_entity(org)
        kg.add_entity(claim)
        kg.add_entity(fact)
        kg.add_entity(evidence)
        
        # Add conversation history
        conversation = [
            {'type': 'question', 'content': 'When did this occur?'},
            {'type': 'response', 'content': 'It happened last month, after I had been with the company for 20 years. They said I was too old for the new direction.'}
        ]
        
        # Create evidence list
        evidence_list = [
            {'name': 'Termination letter', 'type': 'document'},
            {'name': 'Witness statement', 'type': 'testimony'}
        ]
        
        # Synthesize summary
        summary = denoiser.synthesize_complaint_summary(kg, conversation, evidence_list)
        
        # Verify summary content
        assert 'John Doe' in summary or 'person' in summary.lower()
        assert 'TechCorp' in summary or 'organization' in summary.lower()
        assert 'Discrimination' in summary or 'claim' in summary.lower()
        assert 'Evidence' in summary or 'evidence' in summary.lower()
        assert len(summary) > 100  # Should be substantial
    
    def test_synthesis_without_graphs(self):
        """Test synthesis handles empty graphs gracefully."""
        kg_builder = KnowledgeGraphBuilder()
        denoiser = ComplaintDenoiser()
        
        kg = kg_builder.build_from_text("Simple complaint.")
        
        summary = denoiser.synthesize_complaint_summary(kg, [], [])
        
        # Should still produce valid output
        assert isinstance(summary, str)
        assert len(summary) > 0


class TestIntegratedDenoising:
    """Test denoising workflow across all phases."""
    
    def test_noise_calculation_across_phases(self):
        """Test noise calculation works in all phases."""
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        denoiser = ComplaintDenoiser()
        
        complaint = "I was wrongfully terminated by my employer."
        kg = kg_builder.build_from_text(complaint)
        claims = [{'name': 'Wrongful Termination', 'type': 'employment'}]
        dg = dg_builder.build_from_claims(claims)
        
        # Phase 1: Initial noise
        noise1 = denoiser.calculate_noise_level(kg, dg)
        assert 0.0 <= noise1 <= 1.0
        
        # Add some evidence (Phase 2)
        from complaint_phases.knowledge_graph import Entity
        evidence = Entity('e1', 'evidence', 'Letter', {}, 0.8)
        kg.add_entity(evidence)
        
        noise2 = denoiser.calculate_noise_level(kg, dg)
        # Noise should decrease with more information
        assert noise2 <= noise1
    
    def test_question_generation_progression(self):
        """Test that questions evolve across phases."""
        kg_builder = KnowledgeGraphBuilder()
        dg_builder = DependencyGraphBuilder()
        denoiser = ComplaintDenoiser()
        
        # More detailed complaint to ensure gaps exist
        complaint = "I was discriminated against by my employer TechCorp when they fired me last month."
        kg = kg_builder.build_from_text(complaint)
        claims = [
            {'name': 'Employment Discrimination', 'type': 'employment_discrimination'},
            {'name': 'Wrongful Termination', 'type': 'wrongful_termination'}
        ]
        dg = dg_builder.build_from_claims(claims)
        
        # Phase 1: Basic questions (should exist from unsatisfied requirements in DG)
        _phase1_questions = denoiser.generate_questions(kg, dg, max_questions=5)
        
        # Phase 2: Evidence questions with actual gaps
        evidence_gaps = [
            {'id': 'g1', 'name': 'proof of discrimination', 'related_claim': 'c1', 'type': 'missing_evidence'},
            {'id': 'g2', 'name': 'witness testimony', 'related_claim': 'c1', 'type': 'missing_evidence'}
        ]
        phase2_questions = denoiser.generate_evidence_questions(kg, dg, evidence_gaps, max_questions=5)
        
        # Phase 3: Legal questions
        matching_results = {
            'unmatched_requirements': [
                {'id': 'r1', 'name': 'Protected class proof', 'missing_info': 'documentation', 'element_type': 'discrimination'}
            ],
            'matches': [
                {'claim_id': 'c1', 'claim_name': 'Discrimination claim', 'requirement_name': 'Adverse action', 'confidence': 0.4}
            ]
        }
        phase3_questions = denoiser.generate_legal_matching_questions(matching_results, max_questions=5)
        
        # Phase 2 and 3 should always generate questions with provided gaps
        assert len(phase2_questions) > 0, "Phase 2 should generate evidence questions"
        assert len(phase3_questions) > 0, "Phase 3 should generate legal matching questions"
        
        # Questions should have different types
        phase2_types = {q['type'] for q in phase2_questions}
        phase3_types = {q['type'] for q in phase3_questions}
        
        # Phase-specific question types should exist
        assert 'evidence_clarification' in phase2_types or 'evidence_quality' in phase2_types
        assert 'legal_requirement' in phase3_types or 'legal_strengthening' in phase3_types


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
