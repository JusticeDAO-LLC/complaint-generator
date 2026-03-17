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


class _DummyCritic:
    def evaluate_session(self, *args, **kwargs):
        raise AssertionError("critic should not be used in this unit test")


def _make_session() -> AdversarialSession:
    return AdversarialSession(
        session_id="test_session",
        mediator=_DummyMediator(),
        complainant=_DummyComplainant(),
        critic=_DummyCritic(),
        max_turns=1,
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
