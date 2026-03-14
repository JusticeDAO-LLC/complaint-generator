"""
Adversarial Test Harness Example

Demonstrates how to use the adversarial harness to test and optimize
the mediator's question generation capabilities.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from adversarial_harness import (
    AdversarialHarness,
    Optimizer,
    SeedComplaintLibrary,
    DEFAULT_HACC_QUERY_SPECS,
    HACC_QUERY_PRESETS,
)
from mediator.mediator import Mediator


class MockLLMBackend:
    """Mock LLM backend for demonstration."""
    def __init__(self, response_type='default'):
        self.response_type = response_type
        self.call_count = 0
    
    def __call__(self, prompt):
        self.call_count += 1
        
        if 'Generate a complaint' in prompt or 'complaint' in prompt.lower():
            return """I was working at TechCorp as a senior software engineer. After 5 years of excellent 
performance reviews, I was suddenly passed over for a promotion that went to a less qualified 
male colleague. When I raised concerns about gender discrimination, I was told I was being 
"too emotional" and shortly after was terminated without cause. I believe this is wrongful 
termination and gender discrimination."""
        
        elif 'SCORES:' in prompt or 'evaluate' in prompt.lower():
            return """SCORES:
question_quality: 0.75
information_extraction: 0.70
empathy: 0.65
efficiency: 0.72
coverage: 0.68

FEEDBACK:
The mediator asked relevant questions and gathered key information. However, there's room 
for improvement in empathy and ensuring all important topics are covered thoroughly.

STRENGTHS:
- Asked clear, specific questions
- Followed up on vague responses
- Covered main legal elements

WEAKNESSES:
- Could show more empathy in responses
- Missed some timeline details
- Could explore witness information more

SUGGESTIONS:
- Begin questions with acknowledgment of complainant's experience
- Ask more specific date-related questions
- Probe deeper into evidence and witnesses
"""
        
        elif 'Response' in prompt or 'respond' in prompt.lower():
            # Complainant response
            if 'when' in prompt.lower() or 'date' in prompt.lower():
                return "This happened about 6 months ago, around September 2023."
            elif 'who' in prompt.lower() or 'witness' in prompt.lower():
                return "My colleague Sarah saw some of the incidents. Also, HR has records of my complaints."
            elif 'describe' in prompt.lower() or 'detail' in prompt.lower():
                return "My supervisor John made several comments about women not being fit for leadership roles. He said I was 'too emotional' when I pushed back on technical decisions."
            else:
                return "Yes, I can provide more information about that."
        
        return "I understand your question and will provide relevant information."


def main():
    print("=" * 80)
    print("ADVERSARIAL TEST HARNESS EXAMPLE")
    print("=" * 80)
    print()
    
    # Initialize components
    print("Initializing components...")
    print()
    
    # Create LLM backends (using mock for demonstration)
    complainant_backend = MockLLMBackend(response_type='complainant')
    critic_backend = MockLLMBackend(response_type='critic')
    mediator_backend = MockLLMBackend(response_type='mediator')
    
    # Create mediator factory
    def mediator_factory():
        """Factory to create new mediator instances."""
        return Mediator([mediator_backend])
    
    # Create seed library
    seed_library = SeedComplaintLibrary()
    
    # Create harness
    harness = AdversarialHarness(
        llm_backend_complainant=complainant_backend,
        llm_backend_critic=critic_backend,
        mediator_factory=mediator_factory,
        seed_library=seed_library,
        max_parallel=2  # Run 2 sessions in parallel
    )
    
    print("✓ Harness initialized")
    print(f"  - Max parallel sessions: {harness.max_parallel}")
    print(f"  - Seed templates available: {len(seed_library.templates)}")
    print(f"  - HACC evidence query themes: {len(DEFAULT_HACC_QUERY_SPECS)}")
    print(f"  - HACC presets available: {', '.join(sorted(HACC_QUERY_PRESETS.keys()))}")
    print()
    
    # Run batch of sessions
    print("Running adversarial sessions...")
    print("-" * 80)
    
    num_sessions = 5
    results = harness.run_batch(
        num_sessions=num_sessions,
        max_turns_per_session=5,
        include_hacc_evidence=True,
        hacc_count=3,
        hacc_preset='retaliation_focus',
    )
    
    print()
    print(f"✓ Completed {len(results)} sessions")
    print()
    
    # Display statistics
    print("SESSION STATISTICS")
    print("-" * 80)
    stats = harness.get_statistics()
    
    print(f"Total sessions: {stats['total_sessions']}")
    print(f"Successful: {stats['successful_sessions']}")
    print(f"Failed: {stats['failed_sessions']}")
    
    if stats['successful_sessions'] > 0:
        print()
        print(f"Average critic score: {stats['average_score']:.3f}")
        print(f"Score range: {stats['min_score']:.3f} - {stats['max_score']:.3f}")
        print(f"Average questions asked: {stats['average_questions']:.1f}")
        print(f"Average duration: {stats['average_duration']:.2f} seconds")
        
        print()
        print("Score distribution:")
        for range_label, count in stats['score_distribution'].items():
            bar = '█' * count
            print(f"  {range_label}: {bar} ({count})")
    
    print()
    
    # Analyze with optimizer
    print("OPTIMIZATION ANALYSIS")
    print("-" * 80)
    
    optimizer = Optimizer()
    report = optimizer.analyze(results)
    
    print(f"Sessions analyzed: {report.num_sessions_analyzed}")
    print(f"Average score: {report.average_score:.3f}")
    print(f"Trend: {report.score_trend}")
    print()
    
    print("Component scores:")
    print(f"  Question quality:       {report.question_quality_avg:.3f}")
    print(f"  Information extraction: {report.information_extraction_avg:.3f}")
    print(f"  Empathy:               {report.empathy_avg:.3f}")
    print(f"  Efficiency:            {report.efficiency_avg:.3f}")
    print(f"  Coverage:              {report.coverage_avg:.3f}")
    print()
    
    if report.common_strengths:
        print("Common strengths:")
        for strength in report.common_strengths[:3]:
            print(f"  ✓ {strength}")
        print()
    
    if report.common_weaknesses:
        print("Common weaknesses:")
        for weakness in report.common_weaknesses[:3]:
            print(f"  ✗ {weakness}")
        print()
    
    if report.priority_improvements:
        print("Priority improvements:")
        for i, improvement in enumerate(report.priority_improvements, 1):
            print(f"  {i}. {improvement}")
        print()
    
    if report.recommendations:
        print("Recommendations:")
        for i, rec in enumerate(report.recommendations[:5], 1):
            print(f"  {i}. {rec}")
        print()
    
    # Save results
    print("SAVING RESULTS")
    print("-" * 80)
    
    results_file = 'adversarial_results.json'
    harness.save_results(results_file)
    print(f"✓ Results saved to: {results_file}")
    
    # Save optimization report
    report_file = 'optimization_report.json'
    import json
    with open(report_file, 'w') as f:
        json.dump(report.to_dict(), f, indent=2)
    print(f"✓ Optimization report saved to: {report_file}")
    print()
    
    # Example: Best and worst sessions
    if report.best_session_id:
        print("BEST SESSION")
        print("-" * 80)
        best = next((r for r in results if r.session_id == report.best_session_id), None)
        if best:
            print(f"Session ID: {best.session_id}")
            print(f"Score: {best.critic_score.overall_score:.3f}")
            print(f"Questions asked: {best.num_questions}")
            print(f"Turns: {best.num_turns}")
            if best.critic_score.strengths:
                print("Strengths:")
                for strength in best.critic_score.strengths[:3]:
                    print(f"  - {strength}")
        print()
    
    if report.worst_session_id:
        print("WORST SESSION")
        print("-" * 80)
        worst = next((r for r in results if r.session_id == report.worst_session_id), None)
        if worst:
            print(f"Session ID: {worst.session_id}")
            print(f"Score: {worst.critic_score.overall_score:.3f}")
            print(f"Questions asked: {worst.num_questions}")
            print(f"Turns: {worst.num_turns}")
            if worst.critic_score.weaknesses:
                print("Weaknesses:")
                for weakness in worst.critic_score.weaknesses[:3]:
                    print(f"  - {weakness}")
        print()
    
    print("=" * 80)
    print("ADVERSARIAL TESTING COMPLETE")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Review optimization report for improvement areas")
    print("2. Adjust mediator prompts/logic based on feedback")
    print("3. Run another batch to measure improvement")
    print("4. Iterate until desired performance is achieved")
    print()


if __name__ == '__main__':
    main()
