"""
Example: Three-Phase Complaint Processing

Demonstrates the complete three-phase complaint processing workflow:
1. Phase 1: Initial intake and denoising
2. Phase 2: Evidence gathering
3. Phase 3: Neurosymbolic matching and formalization
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from mediator.mediator import Mediator
from complaint_phases import ComplaintPhase


class MockBackend:
    """Mock LLM backend for testing."""
    def __init__(self):
        self.id = 'mock_backend'
    
    def __call__(self, prompt):
        return "Mock response"


def _print_question(question, index):
    print(f"{index}. [{question['type']}] {question['question']}")
    question_objective = str(question.get('question_objective') or '').strip()
    question_reason = str(question.get('question_reason') or '').strip()
    expected_proof_gain = str(question.get('expected_proof_gain') or '').strip()
    if question_objective:
        print(f"   objective: {question_objective}")
    if expected_proof_gain:
        print(f"   expected_proof_gain: {expected_proof_gain}")
    if question_reason:
        print(f"   why: {question_reason}")


def main():
    print("=" * 80)
    print("THREE-PHASE COMPLAINT PROCESSING EXAMPLE")
    print("=" * 80)
    print()
    
    # Initialize mediator
    backend = MockBackend()
    mediator = Mediator([backend])
    
    # ========================================================================
    # PHASE 1: Initial Intake and Denoising
    # ========================================================================
    print("PHASE 1: INITIAL INTAKE AND DENOISING")
    print("-" * 80)
    
    initial_complaint = """
    I was fired from my job at Acme Corporation because of my race. 
    I am African American and was the only person of color in my department. 
    My supervisor made racist comments and then terminated my employment 
    without cause after I complained to HR.
    """
    
    print(f"Initial complaint: {initial_complaint.strip()}")
    print()
    
    # Start the three-phase process
    result = mediator.start_three_phase_process(initial_complaint)
    
    print(f"Phase: {result['phase']}")
    print(f"Initial noise level: {result['initial_noise_level']:.3f}")
    print(f"Knowledge graph: {result['knowledge_graph_summary']['total_entities']} entities, "
          f"{result['knowledge_graph_summary']['total_relationships']} relationships")
    print(f"Dependency graph: {result['dependency_graph_summary']['total_nodes']} nodes")
    print()
    
    # Show initial questions
    print("Initial denoising questions:")
    for i, q in enumerate(result['initial_questions'][:3], 1):
        _print_question(q, i)
    print()
    
    # Simulate answering some questions
    print("Simulating denoising answers...")
    for q in result['initial_questions'][:2]:
        answer = "Yes, I can provide more details about that."
        update = mediator.process_denoising_answer(q, answer)
        print(f"  Answered question, noise level: {update['noise_level']:.3f}, "
              f"gaps remaining: {update['gaps_remaining']}")
    
    print()
    status = mediator.get_three_phase_status()
    print(f"Intake phase complete: {status['phase_completion']['intake']}")
    print()
    
    # ========================================================================
    # PHASE 2: Evidence Gathering
    # ========================================================================
    print("PHASE 2: EVIDENCE GATHERING")
    print("-" * 80)
    
    # Force completion of Phase 1 for demo purposes
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
    
    # Advance to evidence phase
    evidence_result = mediator.advance_to_evidence_phase()
    
    print(f"Phase: {evidence_result['phase']}")
    print(f"Evidence gaps identified: {evidence_result['evidence_gaps']}")
    print(f"Knowledge gaps: {evidence_result['knowledge_gaps']}")
    print()
    
    print("Suggested evidence types:")
    for i, sugg in enumerate(evidence_result['suggested_evidence_types'][:3], 1):
        print(f"{i}. {sugg['requirement']} - Type: {sugg['suggested_type']}")
    print()
    
    # Simulate adding evidence
    print("Adding evidence to graphs...")
    evidence_items = [
        {
            'id': '1',
            'name': 'HR Complaint Email',
            'type': 'document',
            'description': 'Email to HR documenting racist comments',
            'supports_claims': ['entity_1'],  # Would be actual claim entity IDs
            'confidence': 0.9,
            'relevance': 0.85
        },
        {
            'id': '2',
            'name': 'Termination Letter',
            'type': 'document',
            'description': 'Letter of termination without stated cause',
            'supports_claims': ['entity_1'],
            'confidence': 0.95,
            'relevance': 0.9
        }
    ]
    
    for evidence in evidence_items:
        result = mediator.add_evidence_to_graphs(evidence)
        print(f"  Added: {evidence['name']}, Gap ratio: {result['gap_ratio']:.3f}")
    
    print()
    
    # ========================================================================
    # PHASE 3: Neurosymbolic Matching and Formalization
    # ========================================================================
    print("PHASE 3: NEUROSYMBOLIC MATCHING AND FORMALIZATION")
    print("-" * 80)
    
    # Force completion of Phase 2 for demo purposes
    mediator.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gap_ratio', 0.2)
    
    # Advance to formalization phase
    formal_result = mediator.advance_to_formalization_phase()
    
    print(f"Phase: {formal_result['phase']}")
    print(f"Legal graph: {formal_result['legal_graph_summary']['total_elements']} elements")
    print(f"Procedural requirements: {formal_result['procedural_requirements']}")
    print()
    
    matching = formal_result['matching_results']
    print(f"Claims matched: {matching['satisfied_claims']}/{matching['total_claims']}")
    print(f"Overall satisfaction: {matching['overall_satisfaction']:.1%}")
    print()
    
    viability = formal_result['viability_assessment']
    print(f"Claim viability: {viability['overall_viability'].upper()}")
    print(f"Viable claims: {len(viability['viable_claims'])}")
    print(f"Weak claims: {len(viability['weak_claims'])}")
    print()
    
    # Generate formal complaint
    print("Generating formal complaint...")
    complaint = mediator.generate_formal_complaint()
    
    print(f"Complaint ready: {complaint['ready_to_file']}")
    print()
    
    # Display formal complaint structure
    fc = complaint['formal_complaint']
    print("FORMAL COMPLAINT STRUCTURE:")
    print(f"Title: {fc['title']}")
    print(f"Parties: {fc['parties']}")
    print(f"Jurisdiction: {fc['jurisdiction']}")
    print(f"Statement: {fc['statement_of_claim']}")
    print(f"Legal claims: {len(fc['legal_claims'])} claims")
    print(f"Relief requested: {len(fc['prayer_for_relief'])} items")
    print()
    
    # ========================================================================
    # Save Graphs
    # ========================================================================
    print("SAVING GRAPHS TO STATEFILES")
    print("-" * 80)
    
    saved = mediator.save_graphs_to_statefiles('example_complaint')
    print("Saved files:")
    for graph_type, path in saved.items():
        print(f"  {graph_type}: {path}")
    print()
    
    # ========================================================================
    # Final Status
    # ========================================================================
    print("FINAL STATUS")
    print("-" * 80)
    
    final_status = mediator.get_three_phase_status()
    print(f"Current phase: {final_status['current_phase']}")
    print(f"Total iterations: {final_status['iteration_count']}")
    print("Phase completion:")
    for phase, complete in final_status['phase_completion'].items():
        status_icon = "✓" if complete else "✗"
        print(f"  {status_icon} {phase}: {'Complete' if complete else 'Incomplete'}")
    print()
    
    print("=" * 80)
    print("THREE-PHASE PROCESSING COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
