import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adversarial_harness.session import AdversarialSession
from adversarial_harness.optimizer import Optimizer
from complaint_phases import ComplaintPhase, build_intake_case_file
from complaint_phases.knowledge_graph import Entity, KnowledgeGraphBuilder


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
        question_quality = 1.0
        information_extraction = 1.0
        empathy = 1.0
        efficiency = 1.0
        coverage = 1.0
        strengths = []
        weaknesses = []
        suggestions = []

        def to_dict(self):
            return {
                "overall_score": 1.0,
                "question_quality": 1.0,
                "information_extraction": 1.0,
                "empathy": 1.0,
                "efficiency": 1.0,
                "coverage": 1.0,
                "strengths": [],
                "weaknesses": [],
                "suggestions": [],
            }

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


class _ConvergingMediator:
    def __init__(self):
        self._question_batches = [
            [
                {
                    "question": "When did the first incident happen, and what happened next?",
                    "type": "timeline",
                    "question_objective": "timeline",
                }
            ],
            [
                {
                    "question": "What concrete harms did this cause you, and what specific remedy are you requesting?",
                    "type": "harm_remedy",
                    "question_objective": "harm_remedy",
                }
            ],
            [
                {
                    "question": "Do you have any supporting records such as emails, messages, notices, or other written documents?",
                    "type": "documents",
                    "question_objective": "documents",
                }
            ],
        ]
        self._index = 0

    def start_three_phase_process(self, complaint_text):
        self._index = 0
        return {"initial_questions": list(self._question_batches[0])}

    def process_denoising_answer(self, question, answer):
        self._index += 1
        next_questions = []
        if self._index < len(self._question_batches):
            next_questions = list(self._question_batches[self._index])
        return {"next_questions": next_questions, "converged": True}

    def get_three_phase_status(self):
        return {}


class _DocumentMediator(_ConvergingMediator):
    def __init__(self):
        super().__init__()
        self.confirmed = False
        self.document_kwargs = None

    def confirm_intake_summary(self, confirmation_note="", confirmation_source="complainant"):
        self.confirmed = True
        return {}

    def build_formal_complaint_document_package(self, **kwargs):
        self.document_kwargs = dict(kwargs)
        return {
            "ready_to_file": True,
            "draft": {
                "claims_for_relief": [{"title": "Count I"}],
                "factual_allegations": ["A dated notice was uploaded."],
                "requested_relief": ["Injunctive relief."],
                "exhibits": [{"label": "Exhibit A"}],
                "draft_text": "COMPLAINT",
            },
            "document_optimization": {
                "optimization_method": "actor_critic",
            },
            "workflow_optimization_guidance": {
                "recommended_order": ["intake_questioning", "graph_analysis", "document_generation"],
            },
            "drafting_readiness": {
                "blockers": [{"code": "none"}],
            },
        }


class _FallbackDocumentMediator(_ConvergingMediator):
    def confirm_intake_summary(self, confirmation_note="", confirmation_source="complainant"):
        return {}


class _OptimizerStatusMediator(_ConvergingMediator):
    def __init__(self):
        super().__init__()
        self.phase_manager = type(
            "_PhaseManager",
            (),
            {"get_phase_data": staticmethod(lambda phase, key: None)},
        )()

    def get_three_phase_status(self):
        history = [
            {"metrics": {"entities": 1, "relationships": 0, "gaps": 4}},
            {"metrics": {"entities": 3, "relationships": 2, "gaps": 1}},
        ]
        return {
            "alignment_evidence_tasks": [
                {
                    "action": "fill_temporal_chronology_gap",
                    "claim_type": "retaliation",
                    "claim_element_id": "causation",
                    "fallback_lanes": ["authority", "testimony"],
                }
            ],
            "evidence_workflow_action_queue": [
                {
                    "phase_name": "graph_analysis",
                    "claim_type": "retaliation",
                    "claim_element_id": "causation",
                    "focus_areas": ["timeline", "chronology"],
                    "action": "Resolve chronology support for causation.",
                }
            ],
            "intake_legal_targeting_summary": {
                "claims": {
                    "retaliation": {
                        "missing_requirement_element_ids": ["protected_activity"],
                    }
                }
            },
            "loss_history": list(history),
            "convergence_history": list(history),
        }


class _PhaseManagerStub:
    def __init__(self, phase_data):
        self._phase_data = dict(phase_data)

    def get_phase_data(self, phase, key):
        return self._phase_data.get((phase, key))

    def update_phase_data(self, phase, key, value):
        self._phase_data[(phase, key)] = value


class _StaleFinalStateMediator:
    def __init__(self, phase_manager):
        self.phase_manager = phase_manager

    def start_three_phase_process(self, complaint_text):
        return {"initial_questions": []}

    def process_denoising_answer(self, question, answer):
        return {"next_questions": [], "converged": True}

    def get_three_phase_status(self):
        return {
            "intake_readiness": {"ready_to_advance": False},
            "intake_case_file": self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {},
        }


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


def _make_converging_session(mediator: _ConvergingMediator) -> AdversarialSession:
    return AdversarialSession(
        session_id="converging_session",
        mediator=mediator,
        complainant=_DummyComplainant(),
        critic=_DummyCritic(),
        max_turns=5,
    )


def _make_document_session(mediator: _DocumentMediator) -> AdversarialSession:
    return AdversarialSession(
        session_id="document_session",
        mediator=mediator,
        complainant=_DummyComplainant(),
        critic=_DummyCritic(),
        max_turns=5,
    )


def _make_fallback_document_session(mediator: _FallbackDocumentMediator) -> AdversarialSession:
    return AdversarialSession(
        session_id="fallback_document_session",
        mediator=mediator,
        complainant=_DummyComplainant(),
        critic=_DummyCritic(),
        max_turns=3,
    )


def _make_stale_final_state_session(mediator: _StaleFinalStateMediator) -> AdversarialSession:
    return AdversarialSession(
        session_id="stale_final_state_session",
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

    objective_by_question = {}
    for question_text, objective in candidates:
        objective_by_question.setdefault(question_text, []).append(objective)

    assert set(
        objective_by_question[
            "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?"
        ]
    ) == {"timeline", "documents", "anchor_grievance_hearing", "anchor_appeal_rights", "anchor_adverse_action", "hearing_request_timing", "response_dates"}
    assert objective_by_question[
        "Who at HACC made, communicated, or carried out each decision?"
    ] == ["actors"]
    assert set(
        objective_by_question[
            "What written notice, grievance, informal review, hearing, or appeal rights were provided, requested, denied, or ignored?"
        ]
    ) == {"documents", "anchor_grievance_hearing", "anchor_appeal_rights", "hearing_request_timing"}


def test_run_refreshes_final_intake_case_file_snapshot_from_live_knowledge_graph():
    complaint_text = "HACC retaliated against me after I used the grievance process."
    knowledge_graph = KnowledgeGraphBuilder().build_from_text(complaint_text)
    knowledge_graph.add_entity(
        Entity(
            id="fact:protected_activity",
            type="fact",
            name="Protected activity",
            attributes={
                "fact_type": "timeline",
                "predicate_family": "protected_activity",
                "event_label": "Protected activity",
                "event_id": "event_1",
                "structured_timeline_group": "group_1",
                "sequence_index": 1,
                "event_date_or_range": "",
                "source_artifact_ids": ["grievance_email.pdf"],
                "event_support_refs": ["grievance_email.pdf"],
                "description": "Me used the grievance process. Artifact: grievance_email.pdf",
            },
        )
    )
    knowledge_graph.add_entity(
        Entity(
            id="fact:adverse_action",
            type="fact",
            name="Adverse action",
            attributes={
                "fact_type": "timeline",
                "predicate_family": "adverse_action",
                "event_label": "Adverse action",
                "event_id": "event_2",
                "structured_timeline_group": "group_1",
                "sequence_index": 2,
                "event_date_or_range": "shortly after my complaint",
                "source_artifact_ids": ["termination_notice.pdf"],
                "event_support_refs": ["termination_notice.pdf"],
                "description": "HACC threatened termination. Artifact: termination_notice.pdf",
            },
        )
    )

    stale_intake_case_file = build_intake_case_file(KnowledgeGraphBuilder().build_from_text(complaint_text))
    assert stale_intake_case_file.get("timeline_relations") == []

    phase_manager = _PhaseManagerStub(
        {
            (ComplaintPhase.INTAKE, "knowledge_graph"): knowledge_graph,
            (ComplaintPhase.INTAKE, "intake_case_file"): stale_intake_case_file,
        }
    )
    mediator = _StaleFinalStateMediator(phase_manager)
    session = _make_stale_final_state_session(mediator)

    result = session.run({"summary": complaint_text, "key_facts": {}})

    refreshed = result.final_state["intake_case_file"]
    assert refreshed["timeline_relations"]
    assert any(
        relation.get("relation_type") == "before"
        and relation.get("inference_mode") == "derived_from_structured_sequence"
        for relation in refreshed["timeline_relations"]
    )
    assert any(
        (fact.get("structured_timeline_group") or "") == "group_1"
        for fact in refreshed["canonical_facts"]
    )


def test_extract_intake_prompt_candidates_supplements_seed_anchor_sections():
    seed = {
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "reasonable_accommodation"],
            "synthetic_prompts": {
                "intake_questions": [
                    "When did the key events happen?",
                ]
            },
        }
    }

    candidates = AdversarialSession._extract_intake_prompt_candidates(seed)

    assert ("What grievance or informal hearing process were you told was available, whether you requested it, and who was supposed to handle it?", "anchor_grievance_hearing") in candidates
    assert ("Did you request a reasonable accommodation or raise a disability-related need, and how did HACC respond?", "anchor_reasonable_accommodation") in candidates


def test_extract_intake_prompt_candidates_drops_accommodation_objective_without_supported_seed():
    seed = {
        "key_facts": {
            "anchor_sections": ["grievance_hearing"],
            "synthetic_prompts": {
                "mediator_questions": [
                    "Did you request a reasonable accommodation or raise a disability-related need, and how did HACC respond?",
                    "What grievance hearing process were you told was available, whether you requested it, and who was supposed to handle it?",
                ]
            },
        }
    }

    candidates = AdversarialSession._extract_intake_prompt_candidates(seed)

    assert ("Did you request a reasonable accommodation or raise a disability-related need, and how did HACC respond?", "anchor_reasonable_accommodation") not in candidates
    assert ("What grievance hearing process were you told was available, whether you requested it, and who was supposed to handle it?", "anchor_grievance_hearing") in candidates


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
        need_causation=False,
        need_documentary_evidence=False,
        need_witness=False,
        need_exact_dates=False,
        need_staff_names_titles=False,
        need_hearing_request_timing=False,
        need_response_dates=False,
        need_causation_sequence=False,
        last_question_key=None,
        last_question_intent_key=None,
        recent_intent_keys=set(),
        missing_anchor_sections=set(),
    )

    assert probe is not None
    assert probe["question"].startswith("When did the key events happen")
    assert probe["question_objective"] == "hearing_request_timing"
    assert probe["source"] == "harness_fallback"


def test_staff_names_titles_detection_accepts_plural_title_wording():
    question = {
        "question": "Which HACC staff members handled each step, what were their full names and titles or roles, and how can you identify each person from the notices or emails?",
    }

    assert AdversarialSession._is_staff_names_titles_question(question) is True


def test_seed_supports_selection_criteria_only_for_selection_focused_seed():
    selection_seed = {
        "key_facts": {
            "anchor_sections": ["selection_criteria"],
            "theory_labels": ["selection_criteria"],
        }
    }
    retaliation_seed = {
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "appeal_rights", "adverse_action"],
            "theory_labels": ["retaliation", "due_process_failure"],
        }
    }

    assert AdversarialSession._seed_supports_selection_criteria(selection_seed) is True
    assert AdversarialSession._seed_supports_selection_criteria(retaliation_seed) is False


def test_build_fallback_probe_can_emit_causation_question_when_needed():
    session = _make_session()
    seed = {
        "summary": "Retaliation complaint after grievance activity and denial of assistance.",
        "key_facts": {
            "incident_summary": "Plaintiff complained through the grievance process and then HACC denied assistance.",
            "synthetic_prompts": {
                "intake_questions": []
            },
        },
    }

    probe = session._build_fallback_probe(
        seed,
        asked_question_counts={},
        asked_intent_counts={},
        need_timeline=False,
        need_harm_remedy=False,
        need_actor_decisionmaker=False,
        need_causation=True,
        need_documentary_evidence=False,
        need_witness=False,
        need_exact_dates=False,
        need_staff_names_titles=False,
        need_hearing_request_timing=False,
        need_response_dates=False,
        need_causation_sequence=False,
        last_question_key=None,
        last_question_intent_key=None,
        recent_intent_keys=set(),
        missing_anchor_sections=set(),
    )

    assert probe is not None
    assert "protected activity" in probe["question"].lower()
    assert probe["question_objective"] == "causation"
    assert probe["source"] == "harness_fallback"


def test_extract_intake_prompt_candidates_classifies_graph_blocker_prompts():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "What exact date did you request the hearing or review, and on what date did HACC respond?",
                    "What are the names and titles of the HACC staff members who handled the notice, hearing, and denial?",
                    "Please walk me through what happened before and after your protected complaint so we can understand the sequence leading to the denial.",
                ]
            }
        }
    }

    candidates = AdversarialSession._extract_intake_prompt_candidates(seed)

    objective_pairs = {(question_text, objective) for question_text, objective in candidates}

    assert (
        "What exact date did you request the hearing or review, and on what date did HACC respond?",
        "exact_dates",
    ) in objective_pairs
    assert (
        "What exact date did you request the hearing or review, and on what date did HACC respond?",
        "hearing_request_timing",
    ) in objective_pairs
    assert (
        "What exact date did you request the hearing or review, and on what date did HACC respond?",
        "response_dates",
    ) in objective_pairs
    assert (
        "What are the names and titles of the HACC staff members who handled the notice, hearing, and denial?",
        "staff_names_titles",
    ) in objective_pairs
    assert (
        "Please walk me through what happened before and after your protected complaint so we can understand the sequence leading to the denial.",
        "causation_sequence",
    ) in objective_pairs


def test_extract_intake_prompt_candidates_adds_claim_temporal_gap_prompts_from_optimizer_context():
    seed = {
        "document_optimization": {
            "intake_priorities": {
                "claim_temporal_gap_summary": [
                    {
                        "claim_type": "retaliation",
                        "gap_count": 2,
                        "gaps": [
                            "Chronology gap: Timeline fact fact:2 only has relative ordering and still needs anchoring.",
                            "Chronology gap: Protected activity and adverse action still need tighter causation sequencing.",
                        ],
                    }
                ]
            }
        },
        "key_facts": {"synthetic_prompts": {"intake_questions": []}},
    }

    candidates = AdversarialSession._extract_intake_prompt_candidates(seed)

    assert (
        "For your retaliation claim, what exact dates or best available date anchors do you have for each key event in sequence?",
        "exact_dates",
    ) in candidates
    assert (
        "For your retaliation claim, please walk through the sequence from protected activity to adverse action, including who knew what and when.",
        "causation_sequence",
    ) in candidates


def test_extract_intake_prompt_candidates_uses_evidence_upload_questions():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [],
                "evidence_upload_questions": [
                    "Please upload the denial notice if you have it, and explain when you received it and who sent it.",
                ],
            }
        }
    }

    candidates = AdversarialSession._extract_intake_prompt_candidates(seed)

    assert (
        "Please upload the denial notice if you have it, and explain when you received it and who sent it.",
        "timeline",
    ) in candidates
    assert (
        "Please upload the denial notice if you have it, and explain when you received it and who sent it.",
        "documents",
    ) in candidates


def test_inject_intake_prompt_questions_prioritizes_claim_temporal_gap_prompts():
    seed = {
        "document_optimization": {
            "intake_priorities": {
                "claim_temporal_gap_summary": [
                    {
                        "claim_type": "retaliation",
                        "gap_count": 1,
                        "gaps": [
                            "Chronology gap: Protected activity and adverse action still need tighter causation sequencing.",
                        ],
                    }
                ]
            }
        },
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "What remedy are you seeking now?",
                ]
            }
        },
    }

    merged = AdversarialSession._inject_intake_prompt_questions(seed, [])

    assert merged[0]["question"] == (
        "For your retaliation claim, please walk through the sequence from protected activity to adverse action, including who knew what and when."
    )
    assert merged[0]["question_objective"] == "causation_sequence"
    assert merged[0]["source"] == "synthetic_intake_prompt"


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


def test_extract_latest_batch_priority_flags_reads_document_chronology_hints():
    seed = {
        "workflow_optimization_guidance": {
            "claim_support_temporal_handoff": {
                "claim_element_id": "causation",
                "unresolved_temporal_issue_count": 2,
                "chronology_task_count": 1,
                "temporal_proof_objectives": ["response_timeline", "protected_activity_causation"],
            },
            "claim_reasoning_review": {
                "retaliation": {
                    "proof_artifact_element_count": 2,
                    "proof_artifact_available_element_count": 1,
                    "proof_artifact_status_counts": {"missing": 1, "available": 1},
                }
            },
            "document_provenance_summary": {
                "avg_exhibit_backed_ratio": 0.25,
            },
        }
    }

    flags = AdversarialSession._extract_latest_batch_priority_flags(seed)

    assert flags["needs_chronology_closure"] is True
    assert flags["needs_decision_document_precision"] is True
    assert flags["needs_exhibit_grounding"] is True


def test_reprioritize_candidates_uses_document_chronology_hints_to_frontload_timeline_and_documents():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "When did the first incident happen, and what happened next?",
                    "Do you have any emails, notices, or other written documents about this?",
                    "What remedy are you seeking now?",
                ]
            }
        },
        "workflow_optimization_guidance": {
            "claim_support_temporal_handoff": {
                "claim_element_id": "causation",
                "unresolved_temporal_issue_count": 1,
                "chronology_task_count": 1,
                "temporal_proof_objectives": ["response_timeline", "protected_activity_causation"],
            },
            "claim_reasoning_review": {
                "retaliation": {
                    "proof_artifact_element_count": 1,
                    "proof_artifact_available_element_count": 0,
                    "proof_artifact_status_counts": {"missing": 1},
                }
            },
            "document_provenance_summary": {
                "avg_exhibit_backed_ratio": 0.2,
            },
        },
    }
    candidates = [
        {
            "question": "What remedy are you seeking now?",
            "type": "harm_remedy",
            "question_objective": "harm_remedy",
            "selector_score": 100.0,
            "proof_priority": 1,
        },
        {
            "question": "Do you have any emails, notices, or other written documents about this?",
            "type": "documents",
            "question_objective": "documents",
            "selector_score": 20.0,
            "proof_priority": 2,
        },
        {
            "question": "When did the first incident happen, and what happened next?",
            "type": "timeline",
            "question_objective": "timeline",
            "selector_score": 10.0,
            "proof_priority": 3,
        },
    ]

    ranked = AdversarialSession._reprioritize_candidates_for_intake_objectives(
        candidates,
        seed,
        max_questions=3,
    )

    assert "When did the first incident happen" in ranked[0]["question"]
    assert ranked[0]["selector_signals"]["intake_priority_match"] == ["timeline"]
    assert ranked[1]["question"].startswith("Do you have any emails, notices")
    assert ranked[1]["selector_signals"]["intake_priority_match"] == ["documents"]


def test_build_fallback_probe_asks_for_exhibit_ready_document_details_when_exhibit_grounding_is_weak():
    session = AdversarialSession(
        session_id="test-exhibit-grounding",
        mediator=_DummyMediator(),
        complainant=_DummyComplainant(),
        critic=_DummyCritic(),
        max_turns=3,
    )
    seed = {
        "workflow_optimization_guidance": {
            "document_provenance_summary": {
                "avg_exhibit_backed_ratio": 0.1,
            }
        }
    }

    probe = session._build_fallback_probe(
        seed,
        asked_question_counts={},
        asked_intent_counts={},
        need_timeline=False,
        need_harm_remedy=False,
        need_actor_decisionmaker=False,
        need_causation=False,
        need_documentary_evidence=True,
        need_witness=False,
        need_exact_dates=False,
        need_staff_names_titles=False,
        need_hearing_request_timing=False,
        need_response_dates=False,
        need_causation_sequence=False,
        last_question_key=None,
        last_question_intent_key=None,
        recent_intent_keys=set(),
        missing_anchor_sections=set(),
    )

    assert probe["question_objective"] == "documents"
    assert "treated as exhibits" in probe["question"]
    assert "date, sender or source" in probe["question"]


def test_summarize_intake_priority_coverage_does_not_force_selection_criteria_for_non_selection_seed():
    seed = {
        "actor_critic_optimizer": {
            "weak_complaint_types": ["housing_discrimination", "hacc_research_engine"],
            "weak_evidence_modalities": ["policy_document", "file_evidence"],
        },
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "appeal_rights", "adverse_action"],
            "theory_labels": ["retaliation", "due_process_failure"],
            "synthetic_prompts": {
                "intake_questions": [
                    "What happened, and what adverse action did HACC take or threaten to take?",
                    "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
                    "Who at HACC made, communicated, or carried out each decision?",
                    "What written notice, grievance, informal review, hearing, or appeal rights were provided, requested, denied, or ignored?",
                ]
            },
        },
    }

    summary = AdversarialSession._summarize_intake_priority_coverage([], seed)

    assert "anchor_selection_criteria" not in summary["forced_objectives"]
    assert "anchor_selection_criteria" not in summary["expected_objectives"]


def test_summarize_intake_priority_coverage_marks_adverse_action_as_priority_when_uncovered():
    seed = {
        "actor_critic_optimizer": {
            "weak_complaint_types": ["housing_discrimination", "hacc_research_engine"],
            "weak_evidence_modalities": ["file_evidence"],
        },
        "key_facts": {
            "anchor_sections": ["adverse_action"],
            "synthetic_prompts": {
                "intake_questions": [
                    "What exact adverse action did HACC take or threaten to take, on what date did it happen, who made or communicated it, and what notice, message, or decision record shows that action?",
                    "When did the key events happen?",
                ]
            },
        },
    }

    summary = AdversarialSession._summarize_intake_priority_coverage(
        [{"question": "When did the key events happen?", "type": "timeline"}],
        seed,
    )

    assert "anchor_adverse_action" in summary["expected_objectives"]
    assert "anchor_adverse_action" in summary["priority_uncovered_objectives"]
    assert "anchor_adverse_action" in summary["forced_uncovered_objectives"]


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


def test_inject_intake_prompt_questions_frontloads_adverse_action_anchor_in_recovery_mode():
    seed = {
        "actor_critic_optimizer": {
            "weak_complaint_types": ["housing_discrimination", "hacc_research_engine"],
            "question_quality": 0.0,
            "empathy": 0.0,
            "efficiency": 0.0,
        },
        "key_facts": {
            "anchor_sections": ["adverse_action"],
            "synthetic_prompts": {
                "intake_questions": []
            },
        },
    }

    merged = AdversarialSession._inject_intake_prompt_questions(
        seed,
        [{"question": "Can you describe what happened overall?", "type": "timeline"}],
    )

    assert merged[0]["question"].startswith("For the unresolved anchor adverse action")
    assert merged[0]["question_objective"] == "anchor_adverse_action"
    assert "what notice, message, or decision record shows that action" in merged[0]["question"].lower()


def test_inject_intake_prompt_questions_keeps_hearing_request_timing_in_strict_recovery_mode():
    seed = {
        "actor_critic_optimizer": {
            "question_quality": 0.0,
            "empathy": 0.0,
            "efficiency": 0.0,
        },
        "document_optimization": {
            "intake_priorities": {
                "unresolved_intake_objectives": ["hearing_request_timing"],
            },
        },
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": []
            },
            "actor_critic_session_stability": {
                "mode": "recovery",
            },
        },
    }

    merged = AdversarialSession._inject_intake_prompt_questions(seed, [])

    assert any(
        item.get("question_objective") == "hearing_request_timing"
        and "when was the hearing or review requested" in item.get("question", "").lower()
        for item in merged
        if isinstance(item, dict)
    )


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
    assert "anchor_adverse_action" in persisted["adversarial_intake_priority_summary"]["covered_objectives"]
    assert "timeline" in persisted["adversarial_intake_priority_summary"]["expected_objectives"]
    assert result.conversation_history == []
    assert result.success is True
    assert "grounding_summary" in result.final_state
    assert result.final_state["grounding_summary"]["repository_evidence_candidate_count"] == 0
    assert result.final_state["grounding_summary"]["preloaded_mediator_evidence_count"] == 0
    assert result.num_questions == 0
    assert result.initial_complaint_text == "Initial complaint"
    assert result.conversation_history == []


def test_staff_names_titles_question_requires_title_signal():
    generic_actor_question = {
        "question": "Who specifically made each decision or statement, and what exactly was said or done?",
        "question_objective": "actors",
    }
    explicit_staff_title_question = {
        "question": "Who specifically made each decision, and what were their names and titles or roles?",
        "question_objective": "staff_names_titles",
    }

    assert not AdversarialSession._is_staff_names_titles_question(generic_actor_question)
    assert AdversarialSession._is_staff_names_titles_question(explicit_staff_title_question)


def test_run_does_not_require_blocker_questions_when_seed_has_no_blocker_objectives():
    mediator = _ConvergingMediator()
    session = _make_converging_session(mediator)
    seed = {
        "summary": "HACC denied housing assistance after repeated paperwork issues.",
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": []
            }
        },
    }

    result = session.run(seed)

    assert result.success is True
    assert result.num_turns == 3
    assert result.num_questions == 3
    assert mediator._index == 3


def test_run_prefers_causation_sequence_fallback_over_generic_timeline_question():
    mediator = _ConvergingMediator()
    session = AdversarialSession(
        session_id="causation_fallback_session",
        mediator=mediator,
        complainant=_DummyComplainant(),
        critic=_DummyCritic(),
        max_turns=1,
    )
    seed = {
        "document_optimization": {
            "intake_priorities": {
                "claim_temporal_gap_summary": [
                    {
                        "claim_type": "retaliation",
                        "gap_count": 1,
                        "gaps": [
                            "Chronology gap: Protected activity and adverse action still need tighter causation sequencing.",
                        ],
                    }
                ]
            }
        },
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": []
            }
        },
    }

    session.run(seed)

    assert session.conversation_history[0]["role"] == "mediator"
    assert session.conversation_history[0]["content"].startswith(
        "For your retaliation claim, please walk through the sequence from protected activity to adverse action"
    )


def test_session_runs_document_generation_handoff_and_records_grounding_summary():
    mediator = _DocumentMediator()
    class _PhaseManager:
        def __init__(self):
            self.current_phase = None
            self._data = {
                "intake_case_file": {
                    "canonical_facts": [{"fact_id": "fact_1", "text": "A dated notice was sent.", "fact_type": "timeline"}],
                    "timeline_relations": [{"source_fact_id": "fact_1", "target_fact_id": "fact_1", "relation_type": "before"}],
                },
                "uploaded_evidence_summary": {"count": 1, "items": [{"filename": "notice.pdf"}]},
                "claim_support_packet_summary": {"claim_count": 1},
            }

        def get_phase_data(self, phase, key):
            return self._data.get(key)

        def update_phase_data(self, phase, key, value):
            self._data[key] = value

    mediator.phase_manager = _PhaseManager()
    session = _make_document_session(mediator)
    seed = {
        "summary": "Repository-grounded grievance complaint.",
        "key_facts": {
            "grounding_note": "Use repository evidence and uploaded case files together.",
            "anchor_sections": ["grievance_hearing", "appeal_rights"],
            "repository_evidence_candidates": [{"title": "HACC_INTEGRATION.md"}],
            "synthetic_prompts": {
                "intake_questions": ["What notices or hearing requests can you upload?"],
                "evidence_upload_prompt": "Upload notices and hearing requests first.",
            },
        },
        "_meta": {
            "preloaded_mediator_evidence": [{"record_id": 1}],
        },
    }

    result = session.run(seed)

    assert result.success is True
    assert mediator.confirmed is True
    assert mediator.document_kwargs["user_id"] == "document_session"
    assert result.final_state["document_generation"]["ready_to_file"] is True
    assert result.final_state["document_generation"]["document_optimization_available"] is True
    assert result.final_state["grounding_summary"]["preloaded_mediator_evidence_count"] == 1
    assert result.final_state["grounding_summary"]["has_evidence_upload_prompt"] is True
    assert result.final_state["intake_case_file"]["canonical_facts"][0]["text"] == "A dated notice was sent."
    assert result.final_state["uploaded_evidence_summary"]["count"] == 1
    assert result.final_state["claim_support_packet_summary"]["claim_count"] == 1


def test_session_builds_fallback_document_packet_when_builder_is_unavailable():
    mediator = _FallbackDocumentMediator()
    session = _make_fallback_document_session(mediator)
    seed = {
        "type": "housing_discrimination",
        "summary": "HACC denied a grievance hearing after an adverse housing decision.",
        "key_facts": {
            "theory_labels": ["retaliation", "due_process_failure"],
            "synthetic_prompts": {
                "intake_questions": ["What happened and what notices were issued?"],
            },
        },
    }

    result = session.run(seed)

    assert result.success is True
    assert result.final_state["document_generation"]["claim_count"] >= 1
    assert result.final_state["document_generation"]["factual_allegation_count"] >= 1
    assert result.final_state["document_generation"]["requested_relief_count"] >= 1
    assert result.final_state["document_generation"]["draft_text_available"] is True


def test_session_result_preserves_optimizer_graph_targets_and_kg_dynamics():
    mediator = _OptimizerStatusMediator()
    session = _make_converging_session(mediator)
    seed = {
        "summary": "Retaliation timeline needs better chronology support.",
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [],
            }
        },
    }

    result = session.run(seed)

    assert result.success is True
    assert result.final_state["evidence_workflow_action_queue"][0]["claim_element_id"] == "causation"
    assert result.final_state["alignment_evidence_tasks"][0]["claim_element_id"] == "causation"
    assert result.final_state["loss_history"][0]["metrics"]["entities"] == 1

    report = Optimizer().analyze([result])

    assert report.graph_element_targeting_summary["count"] == 3
    assert report.graph_element_targeting_summary["claim_element_counts"] == {
        "causation": 2,
        "protected_activity": 1,
    }
    assert report.kg_avg_entities_delta_per_iter == 2.0
    assert report.kg_avg_relationships_delta_per_iter == 2.0
    assert report.kg_avg_gaps_delta_per_iter == -3.0
    assert report.kg_sessions_gaps_not_reducing == 0
