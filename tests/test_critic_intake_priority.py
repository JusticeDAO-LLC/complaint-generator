from adversarial_harness import Critic, CriticScore


class MockLLMBackend:
    def __init__(self, response_template=None):
        self.response_template = response_template or "Mock response"
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.response_template


def test_evaluate_session_tracks_intake_priority_coverage():
    backend = MockLLMBackend(
        """SCORES:
question_quality: 0.8
information_extraction: 0.6
empathy: 0.7
efficiency: 0.7
coverage: 0.6

FEEDBACK:
Good session.

STRENGTHS:
- Covered major issues

WEAKNESSES:
- Could ask more

SUGGESTIONS:
- Add follow-up
"""
    )
    critic = Critic(backend)

    score = critic.evaluate_session(
        "Initial complaint",
        [
            {"role": "mediator", "type": "question", "content": "When did the key events happen?"},
            {"role": "complainant", "type": "response", "content": "The notice arrived last week."},
        ],
        {
            "status": "complete",
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["timeline", "documents", "harm_remedy"],
                "covered_objectives": ["timeline"],
                "uncovered_objectives": ["documents", "harm_remedy"],
            },
        },
    )

    assert isinstance(score, CriticScore)
    assert score.intake_priority_expected == ["timeline", "documents", "harm_remedy"]
    assert score.intake_priority_covered == ["timeline"]
    assert score.intake_priority_missing == ["documents", "harm_remedy"]
    assert score.information_extraction < 0.6
    assert score.coverage < 0.6
    assert "Missed intake objectives: documents, harm_remedy" in score.weaknesses
    assert "Add questions covering intake objectives: documents, harm_remedy" in score.suggestions
    assert "Intake-priority coverage was incomplete" in score.feedback
    assert any("INTAKE PRIORITY COVERAGE:" in prompt for prompt in backend.prompts)
    assert any("Objectives still uncovered: documents, harm_remedy" in prompt for prompt in backend.prompts)


def test_evaluate_session_rewards_full_intake_priority_coverage():
    critic = Critic(
        MockLLMBackend(
            """SCORES:
question_quality: 0.7
information_extraction: 0.6
empathy: 0.7
efficiency: 0.7
coverage: 0.5

FEEDBACK:
Solid session.

STRENGTHS:
- Stayed on topic

WEAKNESSES:
- None

SUGGESTIONS:
- Keep going
"""
        )
    )

    score = critic.evaluate_session(
        "Initial complaint",
        [
            {
                "role": "mediator",
                "type": "question",
                "content": "When did the events happen and what documents do you have?",
            },
            {
                "role": "complainant",
                "type": "response",
                "content": "It started in January and I have the notice letter.",
            },
        ],
        {
            "status": "complete",
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["timeline", "documents"],
                "covered_objectives": ["timeline", "documents"],
                "uncovered_objectives": [],
            },
        },
    )

    assert score.intake_priority_missing == []
    assert score.information_extraction > 0.6
    assert score.coverage > 0.5
    assert "Covered all intake-priority objectives: timeline, documents" in score.strengths
