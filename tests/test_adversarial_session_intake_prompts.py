import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adversarial_harness.session import AdversarialSession


class _DummyMediator:
    def start_three_phase_process(self, complaint_text):
        return {"initial_questions": []}

    def process_denoising_answer(self, question, answer):
        return {"next_questions": [], "converged": False}

    def get_three_phase_status(self):
        return {}


class _DummyComplainant:
    def generate_initial_complaint(self, seed_data):
        return "Initial complaint"

    def respond_to_question(self, question):
        return "Answer"

    def get_conversation_history(self):
        return []

    def reset_conversation(self):
        return None


class _DummyCritic:
    class _Score:
        overall_score = 1.0

        def to_dict(self):
            return {"overall_score": 1.0}

    def evaluate_session(self, *args, **kwargs):
        return self._Score()


class _SelectorMediator:
    def __init__(self):
        self.selector_calls = 0
        self.selector_restored_marker = None
        self.selected_initial_questions = []
        self.phase_updates = []
        self.phase_manager = self

    def select_intake_question_candidates(self, candidates, *, max_questions=10):
        self.selector_calls += 1
        return list(candidates or [])[:max_questions]

    def start_three_phase_process(self, complaint_text):
        candidates = [
            {
                "question": "Do you have any emails, notices, or other written documents about this?",
                "type": "evidence",
                "question_objective": "identify_supporting_evidence",
                "selector_score": 50.0,
                "proof_priority": 1,
            },
            {
                "question": "What happened, and what adverse action did HACC take or threaten to take?",
                "type": "requirement",
                "question_objective": "establish_element",
                "selector_score": 10.0,
                "proof_priority": 5,
            },
        ]
        questions = self.select_intake_question_candidates(candidates, max_questions=2)
        self.selected_initial_questions = list(questions)
        self.selector_restored_marker = self.select_intake_question_candidates
        return {"initial_questions": questions}

    def process_denoising_answer(self, question, answer):
        return {"next_questions": [], "converged": True}

    def get_three_phase_status(self):
        return {}

    def update_phase_data(self, phase, key, value):
        self.phase_updates.append((phase, key, value))


def _make_session() -> AdversarialSession:
    return AdversarialSession(
        session_id="test_session",
        mediator=_DummyMediator(),
        complainant=_DummyComplainant(),
        critic=_DummyCritic(),
        max_turns=1,
    )


def _make_selector_session(mediator: _SelectorMediator) -> AdversarialSession:
    return AdversarialSession(
        session_id="selector_session",
        mediator=mediator,
        complainant=_DummyComplainant(),
        critic=_DummyCritic(),
        max_turns=0,
    )


def test_extract_intake_prompt_candidates_classifies_missing_fact_questions():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
                    "Who at HACC made, communicated, or carried out each decision?",
                    "What written notice, grievance, informal review, hearing, or appeal rights were provided, requested, denied, or ignored?",
                ]
            }
        }
    }

    candidates = AdversarialSession._extract_intake_prompt_candidates(seed)

    assert candidates[0][1] == "timeline"
    assert candidates[1][1] == "actors"
    assert candidates[2][1] == "anchor_appeal_rights"


def test_build_fallback_probe_prefers_intake_questionnaire_prompt():
    session = _make_session()
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
                    "Who at HACC made, communicated, or carried out each decision?",
                ]
            }
        }
    }

    probe = session._build_fallback_probe(
        seed,
        asked_question_counts={},
        asked_intent_counts={},
        need_timeline=True,
        need_harm_remedy=False,
        need_actor_decisionmaker=True,
        need_documentary_evidence=False,
        need_witness=False,
        last_question_key=None,
        last_question_intent_key=None,
        recent_intent_keys=set(),
        missing_anchor_sections=set(),
    )

    assert probe is not None
    assert probe["question"].startswith("When did the key events happen")
    assert probe["question_objective"] == "timeline"
    assert probe["source"] == "harness_fallback"


def test_inject_intake_prompt_questions_prepends_prioritized_candidates():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "What remedy are you seeking now?",
                    "Who at HACC made, communicated, or carried out each decision?",
                    "What happened, and what adverse action did HACC take or threaten to take?",
                ]
            }
        }
    }

    merged = AdversarialSession._inject_intake_prompt_questions(
        seed,
        [{"question": "Can you describe what documents you still have?", "type": "documents"}],
    )

    assert merged[0]["question"].startswith("What happened, and what adverse action")
    assert merged[0]["source"] == "synthetic_intake_prompt"
    assert merged[1]["question"].startswith("Who at HACC made")
    assert merged[2]["question"].startswith("What remedy are you seeking now")
    assert merged[3]["question"] == "Can you describe what documents you still have?"


def test_inject_intake_prompt_questions_skips_semantic_duplicate_mediator_question():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
                ]
            }
        }
    }

    merged = AdversarialSession._inject_intake_prompt_questions(
        seed,
        [
            {
                "question": "Can you walk me through when the complaint, notice, hearing request, and denial happened?",
                "type": "timeline",
                "question_objective": "timeline",
            }
        ],
    )

    assert len(merged) == 1
    assert merged[0]["question"].startswith("Can you walk me through when the complaint")


def test_run_temporarily_prioritizes_mediator_selector_for_intake_objectives():
    mediator = _SelectorMediator()
    session = _make_selector_session(mediator)
    original_selector = mediator.select_intake_question_candidates
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "What happened, and what adverse action did HACC take or threaten to take?",
                    "When did the key events happen?",
                ]
            }
        }
    }

    result = session.run(seed)

    assert mediator.selector_calls == 1
    assert mediator.select_intake_question_candidates == original_selector
    assert mediator.selected_initial_questions[0]["question"].startswith("What happened, and what adverse action")
    assert mediator.selected_initial_questions[0]["selector_signals"]["intake_priority_match"] == ["anchor_adverse_action"]
    persisted = {
        key: value
        for _, key, value in mediator.phase_updates
    }
    assert "adversarial_intake_priority_summary" in persisted
    assert persisted["adversarial_intake_priority_summary"]["expected_objectives"] == [
        "anchor_adverse_action",
        "timeline",
    ]
    assert persisted["adversarial_intake_priority_summary"]["covered_objectives"] == [
        "anchor_adverse_action",
        "timeline",
    ]
    assert persisted["adversarial_intake_priority_summary"]["uncovered_objectives"] == []
    assert result.conversation_history == []
    assert result.success is True
    assert result.final_state == {}
    assert result.num_questions == 0
    assert result.initial_complaint_text == "Initial complaint"
    assert result.conversation_history == []
