import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "synthesize_hacc_complaint.py"
SPEC = importlib.util.spec_from_file_location("synthesize_hacc_complaint", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_existing_optional_path_returns_none_for_missing_file(tmp_path):
    missing = tmp_path / "grounding_bundle.json"

    assert MODULE._existing_optional_path(missing) is None


def test_existing_optional_path_returns_path_for_existing_file(tmp_path):
    artifact = tmp_path / "grounding_bundle.json"
    artifact.write_text("{}", encoding="utf-8")

    assert MODULE._existing_optional_path(artifact) == artifact


def test_clean_policy_text_removes_generic_prefixes():
    text = "The strongest supporting material is 'ADMINISTRATIVE PLAN'. HACC Policy Written notice is required."

    assert MODULE._clean_policy_text(text) == "Written notice is required."


def test_clean_policy_text_strips_acop_exhibit_boilerplate():
    text = (
        "ACOP 11/1/24 EXHIBIT 14-1: SAMPLE GRIEVANCE PROCEDURE "
        "Note: The sample procedure provided below is a sample only and is designed to match up with the default policies in the model ACOP. "
        "If HACC has made policy decisions that do not reflect the default policies in the ACOP, you would need to ensure that the procedure matches those policy decisions. "
        "I. Definitions applicable to the grievance procedure [24 CFR 966.53]"
    )

    assert MODULE._clean_policy_text(text) == "I. Definitions applicable to the grievance procedure [24 CFR 966.53]"


def test_conversation_facts_excludes_irrelevant_employment_style_intake():
    facts = MODULE._conversation_facts(
        [
            {
                "role": "complainant",
                "content": (
                    "I reported discrimination to human resources after my supervisor denied a promotion and made repeated "
                    "comments about women not being fit for leadership. Two days later I was terminated."
                ),
            },
            {
                "role": "complainant",
                "content": (
                    "I tried to use the HACC grievance process after the denial of assistance and did not receive clear "
                    "notice or an informal review decision."
                ),
            },
        ]
    )

    assert len(facts) == 1
    assert "human resources" not in facts[0].lower()
    assert "hacc grievance process" in facts[0].lower()


def test_normalize_incident_summary_rewrites_hacc_scaffold_description():
    summary = MODULE._normalize_incident_summary("Retaliation complaint anchored to HACC core housing policies.")

    assert summary == "a retaliation and grievance-related housing complaint involving HACC notice and review protections"


def test_proposed_allegations_use_section_specific_housing_process_language():
    seed = {
        "description": "Retaliation complaint anchored to HACC core housing policies.",
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "appeal_rights", "adverse_action"],
            "evidence_summary": "HACC policy defines a grievance as a tenant dispute concerning HACC action or inaction.",
        },
    }

    allegations = MODULE._proposed_allegations(seed, {"conversation_history": []}, "hud")

    assert any("grievance, appeal, and due-process protections" in item for item in allegations)
    assert not any("The intake record suggests a dispute involving grievance hearing." == item for item in allegations)


def test_claims_theory_links_authority_to_hacc_retaliation_process():
    seed = {
        "description": "Retaliation complaint anchored to HACC core housing policies.",
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "appeal_rights", "adverse_action"],
            "theory_labels": ["retaliation", "due_process_failure"],
            "authority_hints": ["Fair Housing Act anti-retaliation provisions", "24 C.F.R. Part 100"],
            "evidence_summary": "HACC policy defines a grievance as a tenant dispute concerning HACC action or inaction.",
        },
    }

    claims = MODULE._claims_theory(seed, {"conversation_history": []}, "hud")

    assert any("may be implicated if HACC used grievance, review, or adverse-action procedures" in item for item in claims)
    assert any("written notice, grievance, informal review, and due-process protections" in item for item in claims)
    assert any("The policy theory is grounded in HACC language stating that" in item for item in claims)
    assert not any("Likely authority implicated by the current theory includes" in item for item in claims)
    assert not any("clearly documented and transparent adverse-action process" in item for item in claims)


def test_proposed_allegations_add_missing_case_facts_prompt_when_intake_facts_absent():
    seed = {
        "description": "Retaliation complaint anchored to HACC core housing policies.",
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "appeal_rights", "adverse_action"],
            "evidence_summary": "HACC policy defines a grievance as a tenant dispute concerning HACC action or inaction.",
        },
    }

    allegations = MODULE._proposed_allegations(seed, {"conversation_history": []}, "hud")

    assert any("Case-specific facts still need confirmation" in item for item in allegations)
    assert any("informal review, a grievance hearing, or an appeal was requested or denied" in item for item in allegations)


def test_proposed_allegations_use_uncovered_intake_priority_summary_when_available():
    seed = {
        "description": "Retaliation complaint anchored to HACC core housing policies.",
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "appeal_rights", "adverse_action"],
            "evidence_summary": "HACC policy defines a grievance as a tenant dispute concerning HACC action or inaction.",
        },
    }
    session = {
        "conversation_history": [],
        "final_state": {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["anchor_adverse_action", "timeline", "anchor_appeal_rights"],
                "covered_objectives": ["anchor_adverse_action"],
                "uncovered_objectives": ["timeline", "anchor_appeal_rights"],
                "objective_question_counts": {
                    "anchor_adverse_action": 1,
                    "timeline": 0,
                    "anchor_appeal_rights": 0,
                },
            }
        },
    }

    allegations = MODULE._proposed_allegations(seed, session, "hud")

    assert any("especially when the key events happened" in item for item in allegations)
    assert any("provided, requested, denied, or ignored" in item for item in allegations)
    assert not any("who at HACC made or communicated the decision" in item for item in allegations)


def test_grounding_prompt_summary_exposes_upload_and_document_generation_prompts():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "complaint_chatbot_prompt": "Use uploaded evidence to ground the complaint chatbot.",
                "intake_questionnaire_prompt": "Ask for dates, actors, and exhibits.",
                "mediator_evidence_review_prompt": "Review uploaded evidence against claim elements.",
                "document_generation_prompt": "Promote exhibits into the complaint draft.",
                "intake_questions": ["When did the notice arrive?"],
                "evidence_upload_questions": ["Please upload the notice if you have it."],
                "workflow_phase_priorities": ["intake_questioning", "evidence_upload", "graph_analysis", "document_generation"],
            }
        }
    }
    grounding_bundle = {}
    upload_report = {
        "upload_count": 1,
        "uploads": [{"title": "Denial Notice"}],
    }

    summary = MODULE._grounding_prompt_summary(seed, grounding_bundle, upload_report)

    assert summary["complaint_chatbot_prompt"] == "Use uploaded evidence to ground the complaint chatbot."
    assert summary["document_generation_prompt"] == "Promote exhibits into the complaint draft."
    assert summary["upload_count"] == 1
    assert summary["uploaded_titles"] == ["Denial Notice"]
    assert summary["evidence_upload_questions"] == ["Please upload the notice if you have it."]


def test_proposed_allegations_use_blocker_follow_up_summary_when_available():
    seed = {
        "description": "Retaliation complaint anchored to HACC core housing policies.",
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "appeal_rights", "adverse_action"],
            "evidence_summary": "HACC policy defines a grievance as a tenant dispute concerning HACC action or inaction.",
        },
    }
    session = {
        "conversation_history": [],
        "final_state": {
            "blocker_follow_up_summary": {
                "blocking_items": [
                    {
                        "blocker_id": "missing_response_timing",
                        "reason": "Response or non-response events are described without date anchors.",
                        "primary_objective": "response_dates",
                        "next_question_strategy": "capture_response_timeline",
                    }
                ]
            }
        },
    }

    allegations = MODULE._proposed_allegations(seed, session, "hud")

    assert any("Response or non-response events are described without date anchors." in item for item in allegations)


def test_factual_and_proposed_allegations_use_anchored_intake_chronology_when_available():
    seed = {
        "description": "Retaliation complaint anchored to HACC core housing policies.",
        "key_facts": {
            "anchor_sections": ["grievance_hearing", "appeal_rights", "adverse_action"],
            "evidence_summary": "HACC policy defines a grievance as a tenant dispute concerning HACC action or inaction.",
        },
    }
    session = {
        "conversation_history": [],
        "final_state": {
            "intake_case_file": {
                "canonical_facts": [
                    {
                        "fact_id": "fact:1",
                        "predicate_family": "protected_activity",
                        "event_label": "Protected activity",
                        "temporal_context": {"start_date": "2025-03-01"},
                    },
                    {
                        "fact_id": "fact:2",
                        "predicate_family": "adverse_action",
                        "event_label": "Adverse action",
                        "temporal_context": {
                            "start_date": "2025-03-15",
                            "derived_from_relative_anchor": True,
                            "relative_markers": ["two weeks after", "after"],
                        },
                    },
                ],
                "timeline_relations": [
                    {
                        "relation_type": "before",
                        "source_fact_id": "fact:1",
                        "target_fact_id": "fact:2",
                        "source_start_date": "2025-03-01",
                        "target_start_date": "2025-03-15",
                    }
                ],
            }
        },
    }

    factual = MODULE._factual_allegations(seed, session)
    proposed = MODULE._proposed_allegations(seed, session, "hud")

    expected = "The intake chronology places protected activity on March 1, 2025 before adverse action on March 15, 2025. The later date is derived from reported timing (two weeks after)."
    assert expected in factual
    assert expected in proposed


def test_anchored_chronology_lines_generalize_to_notice_hearing_and_response_sequences():
    session = {
        "final_state": {
            "intake_case_file": {
                "canonical_facts": [
                    {
                        "fact_id": "fact:notice",
                        "predicate_family": "notice_chain",
                        "event_label": "Notice communication",
                        "temporal_context": {"start_date": "2025-01-05"},
                    },
                    {
                        "fact_id": "fact:hearing",
                        "predicate_family": "hearing_process",
                        "event_label": "Hearing request event",
                        "temporal_context": {"start_date": "2025-01-08"},
                    },
                    {
                        "fact_id": "fact:response",
                        "predicate_family": "response_timeline",
                        "event_label": "Response event",
                        "temporal_context": {"start_date": "2025-01-20"},
                    },
                ],
                "timeline_relations": [
                    {
                        "relation_type": "before",
                        "source_fact_id": "fact:notice",
                        "target_fact_id": "fact:hearing",
                        "source_start_date": "2025-01-05",
                        "target_start_date": "2025-01-08",
                    },
                    {
                        "relation_type": "before",
                        "source_fact_id": "fact:hearing",
                        "target_fact_id": "fact:response",
                        "source_start_date": "2025-01-08",
                        "target_start_date": "2025-01-20",
                    },
                ],
            }
        },
    }

    chronology = MODULE._anchored_chronology_lines(session, limit=3)

    assert chronology == [
        "The intake chronology places notice communication on January 5, 2025, hearing request event on January 8, 2025, and response event on January 20, 2025 in sequence.",
    ]


def test_anchored_chronology_lines_fallback_to_timeline_anchors_without_relations():
    session = {
        "final_state": {
            "intake_case_file": {
                "canonical_facts": [
                    {
                        "fact_id": "fact:notice",
                        "predicate_family": "notice_chain",
                        "event_label": "Notice communication",
                    }
                ],
                "timeline_relations": [],
                "timeline_anchors": [
                    {
                        "fact_id": "fact:notice",
                        "start_date": "2025-01-05",
                        "anchor_text": "2025-01-05",
                        "relative_markers": ["after"],
                    }
                ],
            }
        },
    }

    chronology = MODULE._anchored_chronology_lines(session, limit=2)

    assert chronology == [
        "The intake chronology anchors notice communication at January 5, 2025. Reported relative timing includes after."
    ]


def test_drafting_readiness_accepts_timeline_anchors_without_explicit_relations():
    seed = {"key_facts": {"drafting_readiness": {"coverage": 0.95, "phase_status": "ready", "blockers": []}}}
    session = {
        "final_state": {
            "intake_case_file": {
                "canonical_facts": [{"fact_id": "fact:1", "text": "Notice sent", "fact_type": "timeline"}],
                "timeline_relations": [],
                "timeline_anchors": [{"fact_id": "fact:1", "start_date": "2025-01-05"}],
            }
        }
    }

    readiness = MODULE._drafting_readiness_for_formalization(seed, session)

    assert "graph_analysis_not_ready" not in readiness["blockers"]


def test_graph_and_claim_support_summaries_use_session_case_file_when_packet_is_sparse():
    session = {
        "final_state": {
            "intake_case_file": {
                "candidate_claims": [
                    {
                        "claim_type": "retaliation",
                        "required_elements": [
                            {"element_id": "protected_activity", "status": "present"},
                            {"element_id": "adverse_action", "status": "present"},
                            {"element_id": "causation", "status": "missing"},
                        ],
                    }
                ],
                "canonical_facts": [{"fact_id": "fact:1", "text": "Notice sent"}],
                "timeline_anchors": [{"fact_id": "fact:1", "start_date": "2025-01-05"}],
                "timeline_relations": [],
                "temporal_issue_registry": [{"issue_id": "temp:1", "status": "open"}],
                "blocker_follow_up_summary": {
                    "blocking_item_count": 1,
                    "blocking_items": [
                        {"blocker_id": "missing_retaliation_causation_sequence", "primary_objective": "causation_sequence"}
                    ],
                    "extraction_targets": ["retaliation_sequence"],
                },
            },
            "claim_support_packet_summary": {},
        }
    }

    graph_summary = MODULE._graph_readiness_summary(session)
    claim_support = MODULE._claim_support_summary(session)

    assert graph_summary["chronology_complete"] is True
    assert graph_summary["canonical_fact_count"] == 1
    assert graph_summary["timeline_anchor_count"] == 1
    assert graph_summary["open_temporal_issue_count"] == 1
    assert claim_support["claim_count"] == 1
    assert claim_support["element_count"] == 3
    assert claim_support["status_counts"]["supported"] == 2
    assert claim_support["status_counts"]["unsupported"] == 1
    assert claim_support["blocking_item_count"] == 1
    assert claim_support["evidence_completion_ready"] is False


def test_outstanding_intake_gaps_reflect_uncovered_intake_priority_summary():
    session = {
        "final_state": {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["anchor_adverse_action", "timeline", "actors"],
                "covered_objectives": ["anchor_adverse_action"],
                "uncovered_objectives": ["timeline", "actors"],
                "objective_question_counts": {
                    "anchor_adverse_action": 1,
                    "timeline": 0,
                    "actors": 0,
                },
            }
        }
    }

    gaps = MODULE._outstanding_intake_gaps(session)

    assert gaps == [
        "when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision",
        "who at HACC made, communicated, or carried out each decision",
    ]


def test_outstanding_intake_gaps_prefer_blocker_follow_up_summary_when_available():
    session = {
        "final_state": {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["timeline"],
                "covered_objectives": [],
                "uncovered_objectives": ["timeline"],
                "objective_question_counts": {"timeline": 0},
            },
            "blocker_follow_up_summary": {
                "blocking_items": [
                    {
                        "blocker_id": "missing_response_timing",
                        "reason": "Response or non-response events are described without date anchors.",
                        "primary_objective": "response_dates",
                    },
                    {
                        "blocker_id": "missing_staff_name_title_mapping",
                        "reason": "Named staff are present but title/role mapping is incomplete.",
                        "primary_objective": "staff_names_titles",
                    },
                ]
            },
        }
    }

    gaps = MODULE._outstanding_intake_gaps(session)

    assert gaps == [
        "Response or non-response events are described without date anchors.",
        "Named staff are present but title/role mapping is incomplete.",
        "when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision",
    ]


def test_outstanding_intake_follow_up_questions_reuse_seed_questionnaire():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "What happened, and what adverse action did HACC take or threaten to take?",
                    "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
                    "Who at HACC made, communicated, or carried out each decision?",
                ]
            }
        }
    }
    session = {
        "final_state": {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["anchor_adverse_action", "timeline", "actors"],
                "covered_objectives": ["anchor_adverse_action"],
                "uncovered_objectives": ["timeline", "actors"],
                "objective_question_counts": {
                    "anchor_adverse_action": 1,
                    "timeline": 0,
                    "actors": 0,
                },
            }
        }
    }

    questions = MODULE._outstanding_intake_follow_up_questions(seed, session)

    assert questions == [
        "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
        "Who at HACC made, communicated, or carried out each decision?",
        "Please list the key events with dates (or closest date anchors): protected activity, notices, hearing/review requests, and adverse action outcomes.",
        "Who at HACC handled each step (intake, notice, review/hearing, final decision), and what did each person decide or communicate?",
    ]


def test_outstanding_intake_follow_up_questions_use_blocker_strategies_when_available():
    seed = {
        "key_facts": {
            "synthetic_prompts": {
                "intake_questions": [
                    "When did the key events happen?",
                    "Who at HACC made the decision?",
                ]
            }
        }
    }
    session = {
        "final_state": {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["response_dates", "staff_names_titles"],
                "covered_objectives": [],
                "uncovered_objectives": ["response_dates", "staff_names_titles"],
                "objective_question_counts": {
                    "response_dates": 0,
                    "staff_names_titles": 0,
                },
            },
            "blocker_follow_up_summary": {
                "blocking_items": [
                    {
                        "blocker_id": "missing_response_timing",
                        "reason": "Response or non-response events are described without date anchors.",
                        "primary_objective": "response_dates",
                        "next_question_strategy": "capture_response_timeline",
                    },
                    {
                        "blocker_id": "missing_staff_name_title_mapping",
                        "reason": "Named staff are present but title/role mapping is incomplete.",
                        "primary_objective": "staff_names_titles",
                        "next_question_strategy": "capture_staff_identity",
                    },
                ]
            },
        }
    }

    questions = MODULE._outstanding_intake_follow_up_questions(seed, session)

    assert questions[:2] == [
        "What exact response dates did HACC provide for notices, hearing or review requests, and final decision communications?",
        "Who at HACC made or communicated each decision, and what were their names and titles?",
    ]


def test_actor_critic_follow_up_questions_include_closed_chronology_and_patchable_router_format():
    seed = {"key_facts": {"synthetic_prompts": {"intake_questions": []}}}
    session = {
        "final_state": {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["timeline", "response_dates", "staff_names_titles"],
                "covered_objectives": [],
                "uncovered_objectives": ["timeline", "response_dates", "staff_names_titles"],
                "objective_question_counts": {
                    "timeline": 0,
                    "response_dates": 0,
                    "staff_names_titles": 0,
                },
            }
        }
    }
    metrics = {
        "empathy": 0.6,
        "question_quality": 0.55,
        "information_extraction": 0.45,
        "coverage": 0.5,
        "efficiency": 0.6,
    }

    questions = MODULE._outstanding_intake_follow_up_questions(
        seed,
        session,
        limit=8,
        actor_critic_metrics=metrics,
        phase_focus_order=["graph_analysis", "document_generation", "intake_questioning"],
        router_backed_question_quality=True,
    )

    assert any("closed chronology" in question.lower() for question in questions)
    assert any("event_id | exact/estimated date" in question for question in questions)


def test_actor_critic_ranking_prefers_graph_analysis_for_chronology_objectives():
    questions = [
        "Who at HACC made or communicated each decision, and what were their names and titles?",
        "Please list the key events with dates (or closest date anchors): protected activity, notices, hearing/review requests, and adverse action outcomes.",
    ]
    ranked = MODULE._rank_actor_critic_follow_up_questions(
        questions,
        uncovered=["timeline", "actors"],
        metrics={
            "empathy": 0.6,
            "question_quality": 0.7,
            "information_extraction": 0.7,
            "coverage": 0.7,
            "efficiency": 0.8,
        },
        phase_focus_order=["graph_analysis", "document_generation", "intake_questioning"],
        router_backed_question_quality=False,
        limit=2,
    )

    assert "key events with dates" in ranked[0].lower()


def test_render_markdown_includes_outstanding_intake_gaps_section():
    package = {
        "generated_at": "2026-03-17T00:00:00+00:00",
        "preset": "notice_retaliation",
        "session_id": "session-1",
        "critic_score": 0.91,
        "summary": "Summary text.",
        "selection_rationale": {},
        "caption": {},
        "parties": {},
        "filing_forum": "hud",
        "jurisdiction_and_venue": [],
        "factual_allegations": [],
        "claims_theory": [],
        "policy_basis": [],
        "causes_of_action": [],
        "proposed_allegations": ["Narrative line."],
        "anchored_chronology_summary": [
            "The intake chronology places notice communication on January 5, 2025, hearing request event on January 8, 2025, and response event on January 20, 2025 in sequence.",
        ],
        "intake_blocker_summary": {
            "blocking_items": [
                {
                    "blocker_id": "missing_response_timing",
                    "reason": "Response or non-response events are described without date anchors.",
                    "primary_objective": "response_dates",
                }
            ]
        },
        "outstanding_intake_gaps": [
            "when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision"
        ],
        "outstanding_intake_follow_up_questions": [
            "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?"
        ],
        "anchor_sections": [],
        "anchor_passages": [],
        "supporting_evidence": [],
        "requested_relief": [],
        "grounded_evidence_summary": [],
        "grounding_overview": {
            "evidence_summary": "HACC policy language supporting grievance, appeal, and adverse-action protections.",
            "anchor_sections": ["grievance_hearing", "appeal_rights"],
            "anchor_passage_count": 2,
            "upload_candidate_count": 2,
            "mediator_packet_count": 2,
            "uploaded_evidence_count": 1,
            "top_documents": ["ADMINISTRATIVE PLAN", "ADMISSIONS AND CONTINUED OCCUPANCY POLICY"],
        },
        "search_summary": {
            "requested_search_mode": "hybrid",
            "effective_search_mode": "lexical_only",
            "fallback_note": "Requested hybrid search, but vector support is unavailable; using lexical results instead.",
        },
        "requested_relief_annotations": [],
    }

    markdown = MODULE._render_markdown(package)

    assert "## Anchored Chronology" in markdown
    assert "- The intake chronology places notice communication on January 5, 2025, hearing request event on January 8, 2025, and response event on January 20, 2025 in sequence." in markdown
    assert "## Outstanding Intake Gaps" in markdown
    assert "## Intake Blockers" in markdown
    assert "missing_response_timing: Response or non-response events are described without date anchors. (objective: response_dates)" in markdown
    assert "- when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision" in markdown
    assert "## Follow-Up Questions" in markdown
    assert "- When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?" in markdown
    assert "## Grounding Overview" in markdown
    assert "- Anchor sections: grievance_hearing, appeal_rights" in markdown
    assert "- Top documents: ADMINISTRATIVE PLAN, ADMISSIONS AND CONTINUED OCCUPANCY POLICY" in markdown
    assert "## Search Summary" in markdown
    assert "- Requested search mode: hybrid" in markdown
    assert "- Effective search mode: lexical_only" in markdown
    assert "- Search fallback: Requested hybrid search, but vector support is unavailable; using lexical results instead." in markdown


def test_extract_search_summary_uses_seed_metadata_when_no_grounded_summary_is_available():
    seed = {
        '_meta': {
            'hacc_search_mode': 'hybrid',
            'hacc_effective_search_mode': 'lexical_only',
            'hacc_search_fallback_note': 'Requested hybrid search, but vector support is unavailable; using lexical results instead.',
        },
        'key_facts': {
            'search_summary': {
                'requested_search_mode': 'hybrid',
                'effective_search_mode': 'lexical_only',
                'fallback_note': 'Requested hybrid search, but vector support is unavailable; using lexical results instead.',
            }
        },
    }

    summary = MODULE._extract_search_summary(seed)

    assert summary == {
        'requested_search_mode': 'hybrid',
        'effective_search_mode': 'lexical_only',
        'fallback_note': 'Requested hybrid search, but vector support is unavailable; using lexical results instead.',
    }


def test_extract_search_summary_prefers_grounded_run_summary_over_stale_seed_defaults():
    seed = {
        '_meta': {
            'hacc_search_mode': 'package',
            'hacc_effective_search_mode': 'package',
        },
        'key_facts': {
            'search_summary': {
                'requested_search_mode': 'package',
                'effective_search_mode': 'package',
            }
        },
    }
    grounding_bundle = {
        'search_summary': {
            'requested_search_mode': 'package',
            'effective_search_mode': 'hybrid',
            'fallback_note': 'Grounded run used the shared hybrid backend.',
        }
    }
    evidence_upload_report = {
        'search_summary': {
            'requested_search_mode': 'package',
            'effective_search_mode': 'hybrid',
        }
    }

    summary = MODULE._extract_search_summary(seed, grounding_bundle, evidence_upload_report)

    assert summary == {
        'requested_search_mode': 'package',
        'effective_search_mode': 'hybrid',
        'fallback_note': 'Grounded run used the shared hybrid backend.',
    }


def test_grounding_overview_lines_formats_compact_summary():
    lines = MODULE._grounding_overview_lines(
        {
            "evidence_summary": "HACC policy language supporting grievance, appeal, and adverse-action protections.",
            "anchor_sections": ["grievance_hearing", "appeal_rights"],
            "anchor_passage_count": 2,
            "upload_candidate_count": 2,
            "mediator_packet_count": 2,
            "uploaded_evidence_count": 1,
            "top_documents": ["ADMINISTRATIVE PLAN", "ADMISSIONS AND CONTINUED OCCUPANCY POLICY"],
        }
    )

    assert lines == [
        "Evidence summary: HACC policy language supporting grievance, appeal, and adverse-action protections.",
        "Anchor sections: grievance_hearing, appeal_rights",
        "Anchor passages: 2",
        "Upload candidates: 2",
        "Mediator evidence packets: 2",
        "Uploaded evidence items: 1",
        "Top documents: ADMINISTRATIVE PLAN, ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
    ]


def test_build_intake_follow_up_worksheet_creates_fillable_items():
    package = {
        "generated_at": "2026-03-17T00:00:00+00:00",
        "preset": "notice_retaliation",
        "session_id": "session-1",
        "filing_forum": "hud",
        "summary": "Summary text.",
        "outstanding_intake_gaps": [
            "when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision",
            "who at HACC made, communicated, or carried out each decision",
        ],
        "outstanding_intake_follow_up_questions": [
            "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
            "Who at HACC made, communicated, or carried out each decision?",
        ],
    }

    worksheet = MODULE._build_intake_follow_up_worksheet(package)

    assert worksheet["preset"] == "notice_retaliation"
    assert worksheet["follow_up_items"][0]["id"] == "follow_up_01"
    assert worksheet["follow_up_items"][0]["status"] == "open"
    assert worksheet["follow_up_items"][0]["answer"] == ""
    assert worksheet["follow_up_items"][1]["gap"] == "who at HACC made, communicated, or carried out each decision"


def test_build_intake_follow_up_worksheet_prioritizes_grounded_recommended_next_action():
    package = {
        "generated_at": "2026-03-17T00:00:00+00:00",
        "preset": "notice_retaliation",
        "session_id": "session-1",
        "filing_forum": "hud",
        "summary": "Summary text.",
        "grounded_recommended_next_action": {
            "phase_name": "graph_analysis",
            "action": "fill_chronology_gaps",
            "description": "Prioritize dated notices and response timing before broad drafting.",
        },
        "outstanding_intake_gaps": [
            "when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision",
        ],
        "outstanding_intake_follow_up_questions": [
            "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
        ],
    }

    worksheet = MODULE._build_intake_follow_up_worksheet(package)

    assert worksheet["follow_up_items"][0]["id"] == "grounded_priority_01"
    assert worksheet["follow_up_items"][0]["objective"] == "fill_chronology_gaps"
    assert worksheet["follow_up_items"][0]["source"] == "grounded_recommended_next_action"
    assert worksheet["follow_up_items"][1]["id"] == "follow_up_01"


def test_merge_completed_intake_worksheet_adds_answers_and_closes_matching_gaps():
    session = {
        "conversation_history": [],
        "final_state": {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["timeline", "actors"],
                "covered_objectives": [],
                "uncovered_objectives": ["timeline", "actors"],
                "objective_question_counts": {
                    "timeline": 0,
                    "actors": 0,
                },
            }
        },
    }
    worksheet = {
        "follow_up_items": [
            {
                "id": "follow_up_01",
                "question": "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
                "answer": "The denial notice came on January 15, 2026, and I requested review on January 18, 2026.",
                "status": "answered",
            },
            {
                "id": "follow_up_02",
                "question": "Who at HACC made, communicated, or carried out each decision?",
                "answer": "",
                "status": "open",
            },
        ]
    }

    merged = MODULE._merge_completed_intake_worksheet(session, worksheet)

    assert merged["conversation_history"][-1]["content"].startswith("The denial notice came on January 15, 2026")
    summary = merged["final_state"]["adversarial_intake_priority_summary"]
    assert summary["covered_objectives"] == ["timeline"]
    assert summary["uncovered_objectives"] == ["actors"]
    assert summary["objective_question_counts"]["timeline"] == 1


def test_merge_completed_grounded_intake_worksheet_preserves_grounded_source_and_objective():
    session = {
        "conversation_history": [],
        "final_state": {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["documents", "exact_dates"],
                "covered_objectives": [],
                "uncovered_objectives": ["documents", "exact_dates"],
                "objective_question_counts": {
                    "documents": 0,
                    "exact_dates": 0,
                },
            }
        },
    }
    worksheet = {
        "follow_up_items": [
            {
                "id": "grounded_priority_01",
                "objective": "documents",
                "question": "Which repository-backed file should be uploaded first, and what exact fact does it prove?",
                "answer": "Upload the termination notice first because it proves the date and reason for the adverse action.",
                "status": "answered",
                "source": "grounded_recommended_next_action",
            }
        ]
    }

    merged = MODULE._merge_completed_intake_worksheet(
        session,
        worksheet,
        source_name="completed_grounded_intake_follow_up_worksheet",
    )

    assert merged["conversation_history"][-1]["source"] == "completed_grounded_intake_follow_up_worksheet"
    summary = merged["final_state"]["adversarial_intake_priority_summary"]
    assert summary["covered_objectives"] == ["documents"]
    assert summary["uncovered_objectives"] == ["exact_dates"]
    assert summary["objective_question_counts"]["documents"] == 1


def test_grounded_follow_up_answer_summary_counts_chronology_and_evidence_answers():
    session = {
        "conversation_history": [
            {
                "role": "complainant",
                "content": "The denial notice was dated January 15, 2026 and the review request was submitted January 18, 2026.",
                "question": "What exact dates, notice timing, and event order are still missing before drafting?",
                "source": "completed_grounded_intake_follow_up_worksheet",
                "objective": "exact_dates",
            },
            {
                "role": "complainant",
                "content": "Upload the termination notice first because it proves the adverse action date and stated reason.",
                "question": "Which repository-backed file should be uploaded first, and what exact fact does it prove?",
                "source": "completed_grounded_intake_follow_up_worksheet",
                "objective": "documents",
            },
        ]
    }

    summary = MODULE._grounded_follow_up_answer_summary(session)

    assert summary["answered_item_count"] == 2
    assert summary["chronology_answer_count"] == 1
    assert summary["evidence_answer_count"] == 1
    assert summary["objective_counts"]["exact_dates"] == 1
    assert summary["objective_counts"]["documents"] == 1


def test_render_intake_follow_up_worksheet_markdown_includes_fillable_items():
    worksheet = {
        "generated_at": "2026-03-17T00:00:00+00:00",
        "preset": "notice_retaliation",
        "session_id": "session-1",
        "filing_forum": "hud",
        "summary": "Summary text.",
        "outstanding_intake_gaps": [
            "when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision"
        ],
        "follow_up_items": [
            {
                "id": "follow_up_01",
                "gap": "when the key events happened, including the complaint, notice, review or hearing request, and any denial or termination decision",
                "question": "When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?",
                "answer": "",
                "status": "open",
            }
        ],
    }

    markdown = MODULE._render_intake_follow_up_worksheet_markdown(worksheet)

    assert "# Intake Follow-Up Worksheet" in markdown
    assert "## Outstanding Intake Gaps" in markdown
    assert "## Follow-Up Items" in markdown
    assert "- follow_up_01: When did the key events happen, including the complaint, notice, hearing or review request, and any denial or termination decision?" in markdown
    assert "  - Answer: " in markdown


def test_synthesized_blocker_summary_reads_session_blockers():
    session = {
        "final_state": {
            "blocker_follow_up_summary": {
                "blocking_item_count": 1,
                "blocking_objectives": ["exact_dates", "response_dates"],
                "extraction_targets": ["timeline_anchors", "response_timeline"],
                "workflow_phases": ["graph_analysis", "intake_questioning"],
                "blocking_items": [
                    {
                        "blocker_id": "missing_response_timing",
                        "reason": "Response or non-response events are described without date anchors.",
                        "primary_objective": "response_dates",
                    }
                ],
            }
        }
    }

    summary = MODULE._synthesized_blocker_summary(session)

    assert summary == {
        "blocking_item_count": 1,
        "blocking_objectives": ["exact_dates", "response_dates"],
        "extraction_targets": ["timeline_anchors", "response_timeline"],
        "workflow_phases": ["graph_analysis", "intake_questioning"],
        "blocking_items": [
            {
                "blocker_id": "missing_response_timing",
                "reason": "Response or non-response events are described without date anchors.",
                "primary_objective": "response_dates",
            }
        ],
    }


def test_summarize_policy_excerpt_normalizes_hacc_grievance_fragments():
    text = (
        "Grievance: Any dispute a tenant may have with respect to HACC action or failure to "
        "If HUD has issued a due process determination, HACC may exclude from HACC grievance"
    )

    summary = MODULE._summarize_policy_excerpt(text)

    assert "defines a grievance as a tenant dispute" in summary
    assert "due process determination" in summary


def test_summarize_policy_excerpt_normalizes_informal_review_heading():
    text = "16-11 Scheduling an Informal Review"

    assert MODULE._summarize_policy_excerpt(text) == "HACC policy describes scheduling and procedures for informal review."


def test_trim_admin_plan_complaint_preamble_jumps_past_fheo_text():
    text = (
        "Applicants may file a complaint with FHEO and the Office of Fair Housing and Equal Opportunity if they believe "
        "they have been discriminated against. Notice to the Applicant [24 CFR 982.554(a)] HACC must give an applicant "
        "prompt notice of a decision denying assistance."
    )

    trimmed = MODULE._trim_admin_plan_complaint_preamble(text)

    assert trimmed.startswith("Notice to the Applicant")
    assert "file a complaint with FHEO" not in trimmed


def test_trim_admin_plan_complaint_preamble_jumps_past_denial_leadin():
    text = (
        "Denial of assistance includes denying listing on HACC waiting list; denying or withdrawing a voucher; refusing "
        "to enter into a HAP contract or approve a lease. Notice to the Applicant [24 CFR 982.554(a)] HACC must give "
        "an applicant prompt notice of a decision denying assistance. Scheduling an Informal Review HACC Policy A request "
        "for an informal review must be made in writing."
    )

    trimmed = MODULE._trim_admin_plan_complaint_preamble(text)

    assert trimmed.startswith("Notice to the Applicant")
    assert "Denial of assistance includes" not in trimmed


def test_refresh_snippet_from_source_trims_admin_plan_denial_leadin(tmp_path):
    source_path = tmp_path / "admin-plan.txt"
    source_path.write_text(
        "Denial of assistance includes denying listing on HACC waiting list; denying or withdrawing a voucher.\n\n"
        "Notice to the Applicant [24 CFR 982.554(a)] HACC must give an applicant prompt notice of a decision denying assistance.\n\n"
        "Scheduling an Informal Review HACC Policy A request for an informal review must be made in writing.",
        encoding="utf-8",
    )

    refreshed = MODULE._refresh_snippet_from_source(
        str(source_path),
        anchor_terms=["Notice to the Applicant", "Scheduling an Informal Review"],
        fallback_snippet="Scheduling an Informal Review ........ 16-11",
    )

    assert refreshed.startswith("Notice to the Applicant")
    assert "Denial of assistance includes" not in refreshed


def test_specific_refresh_terms_add_notice_headings_for_admin_plan_toc_seed():
    terms = MODULE._specific_refresh_terms(
        "16-11 Scheduling an Informal Review ................................................... 16-11",
        title="ADMINISTRATIVE PLAN",
        section_labels=["grievance_hearing", "appeal_rights", "adverse_action"],
    )

    assert "Notice to the Applicant" in terms
    assert "Scheduling an Informal Review" in terms


def test_should_promote_grounded_snippet_prefers_due_process_expansion():
    current = "I. Definitions applicable to the grievance procedure [24 CFR 966.53] A. Grievance: Any dispute..."
    evidence = (
        "I. Definitions applicable to the grievance procedure [24 CFR 966.53] A. Grievance: Any dispute... "
        "C. Elements of due process: An eviction action or a termination of tenancy in a state or local court..."
    )

    assert MODULE._should_promote_grounded_snippet(current, evidence) is True


def test_single_exhibit_margin_for_retaliation_cause_is_narrow():
    cause = {
        "title": "Retaliation for Protected Fair Housing Activity",
        "theory": "The complainant narrative suggests adverse treatment after raising concerns or invoking grievance protections.",
    }

    assert MODULE._single_exhibit_margin_for_cause(cause) == 1


def test_exhibit_rationale_for_retaliation_mentions_grievance_activity():
    cause = {
        "title": "Retaliation for Protected Fair Housing Activity",
        "theory": "The complainant narrative suggests adverse treatment after raising concerns or invoking grievance protections.",
    }

    rationale = MODULE._exhibit_rationale_for_cause(
        cause,
        [("Exhibit B", "ADMINISTRATIVE PLAN")],
        [],
    )

    assert "grievance activity" in rationale
    assert "retaliation theory" in rationale


def test_merge_seed_with_grounding_replaces_existing_matching_evidence_when_grounded_version_is_stronger():
    seed = {
        "key_facts": {
            "anchor_passages": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "source_path": "/tmp/acop.txt",
                    "snippet": "Grievance: Any dispute...",
                }
            ]
        },
        "hacc_evidence": [
            {
                "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                "source_path": "/tmp/acop.txt",
                "snippet": "Grievance: Any dispute...",
            }
        ],
    }
    grounding_bundle = {
        "search_payload": {
            "results": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "source_path": "/tmp/acop.txt",
                    "snippet": "Grievance: Any dispute...",
                    "matched_rules": [
                        {
                            "section_title": "Definitions applicable to the grievance procedure",
                            "text": (
                                "I. Definitions applicable to the grievance procedure [24 CFR 966.53] "
                                "A. Grievance: Any dispute... C. Elements of due process: An eviction action..."
                            ),
                        }
                    ],
                }
            ]
        }
    }

    merged = MODULE._merge_seed_with_grounding(seed, grounding_bundle)

    merged_snippet = merged["hacc_evidence"][0]["snippet"]
    assert "Elements of due process" in merged_snippet
    assert "Elements of due process" in merged["key_facts"]["anchor_passages"][0]["snippet"]


def test_policy_basis_uses_condensed_summary_and_full_passage():
    seed = {
        "key_facts": {
            "anchor_passages": [
                {
                    "title": "ADMINISTRATIVE PLAN",
                    "snippet": (
                        "Notice to the Applicant [24 CFR 982.554(a)] HACC must give an applicant prompt notice of a decision "
                        "denying assistance. Scheduling an Informal Review HACC Policy A request for an informal review "
                        "must be made in writing."
                    ),
                    "section_labels": ["notice", "hearing", "adverse_action"],
                }
            ]
        }
    }

    basis = MODULE._policy_basis(seed)

    assert len(basis) == 1
    assert "HACC policy describes scheduling and procedures for informal review." in basis[0]
    assert "Full passage:" in basis[0]
    assert "Notice to the Applicant" in basis[0]


def test_evidence_lines_keep_notice_excerpt():
    seed = {
        "hacc_evidence": [
            {
                "title": "ADMINISTRATIVE PLAN",
                "source_path": "/tmp/admin-plan.txt",
                "snippet": (
                    "Notice to the Applicant [24 CFR 982.554(a)] HACC must give an applicant prompt notice of a decision "
                    "denying assistance. Scheduling an Informal Review HACC Policy A request for an informal review "
                    "must be made in writing."
                ),
                "section_labels": ["notice", "hearing", "adverse_action"],
            }
        ]
    }

    lines = MODULE._evidence_lines(seed)

    assert len(lines) == 1
    assert "Notice to the Applicant" in lines[0]
    assert "Scheduling an Informal Review" in lines[0]


def test_anchor_passage_lines_keep_due_process_excerpt():
    seed = {
        "key_facts": {
            "anchor_passages": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "snippet": (
                        "I. Definitions applicable to the grievance procedure [24 CFR 966.53] "
                        "A. Grievance: Any dispute a tenant may have with respect to HACC action or failure to act. "
                        "C. Elements of due process: An eviction action or a termination of tenancy in a state or local court..."
                    ),
                    "section_labels": ["hearing", "adverse_action"],
                }
            ]
        }
    }

    lines = MODULE._anchor_passage_lines(seed)

    assert len(lines) == 1
    assert "defines a grievance as a tenant dispute" in lines[0]
    assert "Elements of due process" in lines[0]
