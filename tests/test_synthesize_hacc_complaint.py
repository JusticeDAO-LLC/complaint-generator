import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "synthesize_hacc_complaint.py"
SPEC = importlib.util.spec_from_file_location("synthesize_hacc_complaint", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


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
    ]


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

    assert "## Outstanding Intake Gaps" in markdown
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


def test_extract_search_summary_prefers_seed_metadata():
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
