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


def test_clean_policy_text_removes_inline_policy_wrapper():
    text = (
        "This responsibility begins with the first contact by an interested family and continues through every aspect "
        "of the program. HACC Policy HACC will ask all applicants if they require accommodations in writing."
    )
    cleaned = MODULE._clean_policy_text(text)

    assert "HACC Policy" not in cleaned
    assert cleaned.endswith("HACC will ask all applicants if they require accommodations in writing.")


def test_clean_policy_text_keeps_descriptive_policy_phrase():
    text = "Reasonable-accommodation complaint anchored to HACC policy language."

    assert MODULE._clean_policy_text(text) == text


def test_clean_policy_text_strips_acop_exhibit_boilerplate():
    text = (
        "ACOP 11/1/24 EXHIBIT 14-1: SAMPLE GRIEVANCE PROCEDURE "
        "Note: The sample procedure provided below is a sample only and is designed to match up with the default policies in the model ACOP. "
        "If HACC has made policy decisions that do not reflect the default policies in the ACOP, you would need to ensure that the procedure matches those policy decisions. "
        "I. Definitions applicable to the grievance procedure [24 CFR 966.53]"
    )

    assert MODULE._clean_policy_text(text) == "I. Definitions applicable to the grievance procedure [24 CFR 966.53]"


def test_conversation_facts_excludes_scorecard_style_responses():
    facts = MODULE._conversation_facts(
        [
            {"role": "complainant", "content": "SCORES:\nquestion_quality: 0.72\nFEEDBACK:\nGood coverage."},
            {"role": "complainant", "content": "I complained and then received a termination notice two days later."},
        ]
    )

    assert facts == ["I complained and then received a termination notice two days later."]


def test_summarize_policy_excerpt_avoids_table_of_contents_text():
    text = "14 GRIEVANCES AND APPEALS INTRODUCTION ........ 14-1 PART I: INFORMAL HEARINGS ........ 14-2"

    summary = MODULE._summarize_policy_excerpt(text)

    assert "GRIEVANCES AND APPEALS INTRODUCTION" not in summary
    assert len(summary) <= 360


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

    summary = MODULE._summarize_policy_excerpt(text)

    assert summary == "HACC policy describes scheduling and procedures for informal review."


def test_summarize_policy_excerpt_prefers_complaint_grade_sentences():
    text = (
        "This responsibility begins with the first contact by an interested family and continues through every aspect "
        "of the program. HACC will ask all applicants and participants if they require any type of accommodations in "
        "writing, on the intake application, reexamination documents, and notices of adverse action by HACC. "
        "A specific name and phone number of designated staff will be provided to process requests for accommodation."
    )

    summary = MODULE._summarize_policy_excerpt(text)

    assert "first contact by an interested family" not in summary
    assert "must be asked in writing about accommodation needs" in summary
    assert "designated staff contact information" in summary
    assert len(summary) < len(text)
    assert "..." not in summary


def test_evidence_tags_extract_key_policy_topics():
    tags = MODULE._evidence_tags(
        "reasonable accommodation, adverse action",
        "HACC policy says applicants and participants must be asked in writing about accommodation needs on intake, reexamination, and adverse-action notices. HACC policy says designated staff contact information must be provided for accommodation requests.",
    )

    assert "reasonable_accommodation" in tags
    assert "notice" in tags
    assert "contact" in tags
    assert "adverse_action" in tags


def test_claims_theory_and_markdown_include_structured_sections():
    seed = {
        "description": "Retaliation and grievance complaint anchored to the HACC Administrative Plan.",
        "key_facts": {
            "evidence_summary": (
                "The strongest supporting material is 'ADMINISTRATIVE PLAN'. "
                "HACC Policy Written notice and an informal review or hearing are required."
            ),
            "anchor_sections": ["appeal_rights", "adverse_action"],
            "authority_hints": ["Fair Housing Act, 42 U.S.C. 3604"],
            "anchor_passages": [
                {
                    "title": "ADMINISTRATIVE PLAN",
                    "snippet": "HACC Policy Written notice and an informal review or hearing are required.",
                    "section_labels": ["appeal_rights", "adverse_action"],
                }
            ],
        },
        "hacc_evidence": [
            {
                "title": "ADMINISTRATIVE PLAN",
                "snippet": "HACC Policy Written notice and an informal review or hearing are required.",
                "source_path": "/tmp/admin-plan.txt",
            }
        ],
    }
    session = {
        "conversation_history": [
            {
                "role": "complainant",
                "content": (
                    "Late 2025 I raised concerns, and shortly after that HACC moved toward terminating assistance "
                    "without clear written notice."
                ),
            }
        ]
    }

    package = {
        "generated_at": "2026-03-15T00:00:00+00:00",
        "preset": "administrative_plan_retaliation",
        "filing_forum": "court",
        "session_id": "session_1",
        "critic_score": 0.5,
        "summary": MODULE._clean_policy_text(seed["key_facts"]["evidence_summary"]),
        "caption": MODULE._draft_caption(seed, "court"),
        "parties": MODULE._draft_parties("court"),
        "jurisdiction_and_venue": MODULE._jurisdiction_and_venue(seed, "court"),
        "legal_theory_summary": MODULE._legal_theory_summary(seed),
        "factual_allegations": MODULE._factual_allegations(seed, session),
        "claims_theory": MODULE._claims_theory(seed, session),
        "policy_basis": MODULE._policy_basis(seed),
        "causes_of_action": MODULE._causes_of_action(seed, session, "court"),
        "proposed_allegations": MODULE._proposed_allegations(seed, session, "court"),
        "anchor_sections": list(seed["key_facts"]["anchor_sections"]),
        "anchor_passages": MODULE._anchor_passage_lines(seed),
        "supporting_evidence": MODULE._evidence_lines(seed),
        "requested_relief": MODULE._requested_relief_for_forum("court"),
    }

    markdown = MODULE._render_markdown(package)

    assert package["summary"] == "Written notice and an informal review or hearing are required."
    assert any("retaliation theory" in item.lower() for item in package["claims_theory"])
    assert any("Timeline detail from intake" in item for item in package["factual_allegations"])
    assert package["caption"]["case_title"] == "Complainant v. Housing Authority of Clackamas County"
    assert package["parties"]["defendant"] == "Housing Authority of Clackamas County (HACC)."
    assert any(cause["title"] == "Failure to Provide Required Notice and Process" for cause in package["causes_of_action"])
    assert any(cause["title"] == "Retaliation for Protected Complaint Activity" for cause in package["causes_of_action"])
    assert "## Draft Caption" in markdown
    assert "## Parties" in markdown
    assert "## Jurisdiction And Venue" in markdown
    assert "## Legal Theory Summary" in markdown
    assert "## Factual Allegations" in markdown
    assert "## Claims Theory" in markdown
    assert "## Policy Basis" in markdown
    assert "## Causes Of Action" in markdown


def test_policy_basis_leads_with_condensed_summary_and_keeps_full_passage():
    seed = {
        "key_facts": {
            "anchor_passages": [
                {
                    "title": "ADMINISTRATIVE PLAN",
                    "snippet": (
                        "This responsibility begins with the first contact by an interested family and continues through "
                        "every aspect of the program. HACC will ask all applicants and participants if they require any "
                        "type of accommodations in writing, on the intake application, reexamination documents, and "
                        "notices of adverse action by HACC. A specific name and phone number of designated staff will be "
                        "provided to process requests for accommodation."
                    ),
                    "section_labels": ["reasonable_accommodation", "adverse_action"],
                }
            ]
        }
    }

    basis = MODULE._policy_basis(seed)

    assert len(basis) == 1
    assert "supports reasonable accommodation, adverse action:" in basis[0]
    assert "[reasonable_accommodation, notice" in basis[0]
    assert "must be asked in writing about accommodation needs" in basis[0]
    assert "Full passage:" in basis[0]
    assert "first contact by an interested family" in basis[0]


def test_policy_basis_normalizes_acop_accommodation_language():
    seed = {
        "key_facts": {
            "anchor_passages": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "snippet": (
                        "Information of the availability of reasonable accommodation will be provided to all families at "
                        "the time of application. HACC will also ask all applicants and participants if they require any "
                        "type of accommodations, in writing, on the intake application, reexamination documents, and "
                        "notices of adverse action by HACC by utilizing the following language: \"If you or anyone in "
                        "your family is a person with disabilities...\""
                    ),
                    "section_labels": ["reasonable_accommodation", "adverse_action"],
                }
            ]
        }
    }

    basis = MODULE._policy_basis(seed)

    assert "[reasonable_accommodation" in basis[0]
    assert "reasonable accommodation is available" in basis[0]
    assert "must be asked in writing about accommodation needs" in basis[0]
    assert "Full passage:" in basis[0]


def test_anchor_passages_lead_with_condensed_summary_and_keep_full_passage():
    seed = {
        "key_facts": {
            "anchor_passages": [
                {
                    "title": "ADMINISTRATIVE PLAN",
                    "snippet": (
                        "This responsibility begins with the first contact by an interested family and continues through "
                        "every aspect of the program. HACC will ask all applicants and participants if they require any "
                        "type of accommodations in writing, on the intake application, reexamination documents, and "
                        "notices of adverse action by HACC. A specific name and phone number of designated staff will be "
                        "provided to process requests for accommodation."
                    ),
                    "section_labels": ["reasonable_accommodation", "adverse_action"],
                }
            ]
        }
    }

    lines = MODULE._anchor_passage_lines(seed)

    assert "[reasonable_accommodation, notice" in lines[0]
    assert "must be asked in writing about accommodation needs" in lines[0]
    assert "Full passage:" in lines[0]
    assert "first contact by an interested family" in lines[0]


def test_supporting_evidence_leads_with_condensed_summary_and_keeps_source_path():
    seed = {
        "hacc_evidence": [
            {
                "title": "ADMINISTRATIVE PLAN",
                "snippet": (
                    "This responsibility begins with the first contact by an interested family and continues through "
                    "every aspect of the program. HACC will ask all applicants and participants if they require any "
                    "type of accommodations in writing, on the intake application, reexamination documents, and "
                    "notices of adverse action by HACC. A specific name and phone number of designated staff will be "
                    "provided to process requests for accommodation."
                ),
                "source_path": "/tmp/admin-plan.txt",
            }
        ]
    }

    lines = MODULE._evidence_lines(seed)

    assert "[reasonable_accommodation, notice" in lines[0]
    assert "must be asked in writing about accommodation needs" in lines[0]
    assert "Full passage:" in lines[0]
    assert lines[0].endswith("(/tmp/admin-plan.txt)")


def test_hud_forum_changes_caption_and_relief():
    seed = {
        "type": "housing_discrimination",
        "description": "Retaliation and grievance complaint anchored to the HACC Administrative Plan.",
        "key_facts": {"anchor_sections": ["appeal_rights", "adverse_action"]},
    }
    session = {"conversation_history": []}

    caption = MODULE._draft_caption(seed, "hud")
    parties = MODULE._draft_parties("hud")
    jurisdiction = MODULE._jurisdiction_and_venue(seed, "hud")
    causes = MODULE._causes_of_action(seed, session, "hud")
    relief = MODULE._requested_relief_for_forum("hud")

    assert caption["case_title"] == "Administrative Fair Housing Complaint"
    assert "HUD" in caption["court"]
    assert parties["defendant"].endswith("respondent.")
    assert any("HUD jurisdiction" in item for item in jurisdiction)
    assert any(cause["title"] == "Administrative Fair Housing Process Failure" for cause in causes)
    assert any("Administrative investigation" in item for item in relief)
    labels = MODULE._section_labels_for_forum("hud")
    assert labels["parties_plaintiff"] == "Complainant"
    assert labels["parties_defendant"] == "Respondent"
    assert labels["claims_theory"] == "Administrative Theory"
    assert labels["policy_basis"] == "Administrative Basis"
    assert labels["proposed_allegations"] == "Complainant Narrative"


def test_legal_theory_summary_uses_seed_theory_labels_and_protected_bases():
    seed = {
        "key_facts": {
            "theory_labels": ["reasonable_accommodation", "disability_discrimination"],
            "protected_bases": ["disability"],
            "authority_hints": ["Section 504 of the Rehabilitation Act", "Fair Housing Act reasonable accommodation requirements"],
        }
    }

    summary = MODULE._legal_theory_summary(seed, "hud")

    assert summary["theory_labels"] == ["reasonable_accommodation", "disability_discrimination"]
    assert summary["protected_bases"] == ["disability"]
    assert summary["authority_hints"][0] == "Fair Housing Act reasonable accommodation requirements"


def test_claims_and_causes_include_protected_basis_theory():
    seed = {
        "description": "Reasonable-accommodation complaint anchored to HACC policy language.",
        "key_facts": {
            "evidence_summary": "Reasonable accommodation review is required.",
            "anchor_sections": ["reasonable_accommodation", "adverse_action"],
            "theory_labels": ["reasonable_accommodation", "disability_discrimination"],
            "protected_bases": ["disability"],
            "authority_hints": ["Section 504 of the Rehabilitation Act", "Americans with Disabilities Act"],
        },
    }
    session = {"conversation_history": []}

    claims = MODULE._claims_theory(seed, session)
    causes = MODULE._causes_of_action(seed, session, "hud")
    theory_summary = MODULE._legal_theory_summary(seed, "hud")

    assert any("protected basis concerns related to disability" in item.lower() for item in claims)
    assert any("section 504 of the rehabilitation act" in item.lower() for item in claims)
    assert any("Section 504 / ADA Accommodation Theory" == cause["title"] for cause in causes)
    assert any("Section 504 Protected-Basis Administrative Theory" == cause["title"] for cause in causes)
    assert any("Section 504 of the Rehabilitation Act" in cause["theory"] for cause in causes)
    assert theory_summary["authority_hints"] == ["Section 504 of the Rehabilitation Act", "Americans with Disabilities Act"]


def test_authority_hints_are_prioritized_by_forum():
    seed = {
        "key_facts": {
            "authority_hints": [
                "Section 504 of the Rehabilitation Act",
                "Fair Housing Act reasonable accommodation requirements",
                "24 C.F.R. Part 100",
            ]
        }
    }

    hud_hints = MODULE._authority_hints_for_forum(seed, "hud")
    court_hints = MODULE._authority_hints_for_forum(seed, "court")

    assert hud_hints[0] == "Fair Housing Act reasonable accommodation requirements"
    assert hud_hints[1] == "24 C.F.R. Part 100"
    assert court_hints[0] == "Section 504 of the Rehabilitation Act"
    assert court_hints[1] == "Fair Housing Act reasonable accommodation requirements"


def test_dominant_authority_family_prefers_forum_priority_order():
    hints = [
        "Section 504 of the Rehabilitation Act",
        "Fair Housing Act reasonable accommodation requirements",
        "Americans with Disabilities Act",
    ]

    assert MODULE._dominant_authority_family(hints, "hud") == "504_fha"
    assert MODULE._dominant_authority_family(hints, "court") == "504_fha"

    hud_ordered = MODULE._authority_hints_for_forum({"key_facts": {"authority_hints": hints}}, "hud")
    court_ordered = MODULE._authority_hints_for_forum({"key_facts": {"authority_hints": hints}}, "court")

    assert MODULE._dominant_authority_family(hud_ordered, "hud") == "fha_504"
    assert MODULE._dominant_authority_family(court_ordered, "court") == "504_fha"


def test_hud_proposed_allegations_use_complainant_language():
    seed = {
        "description": "Retaliation and grievance complaint anchored to the HACC Administrative Plan.",
        "key_facts": {
            "incident_summary": "Retaliation and grievance complaint anchored to the HACC Administrative Plan.",
            "evidence_summary": "Written notice and an informal review or hearing are required.",
            "anchor_sections": ["appeal_rights"],
        },
    }
    session = {"conversation_history": []}

    allegations = MODULE._proposed_allegations(seed, session, "hud")

    assert allegations[0].startswith("Complainant alleges conduct arising from")
    assert allegations[1].startswith("The available HACC materials suggest that")


def test_hud_markdown_uses_administrative_headings():
    package = {
        "generated_at": "2026-03-15T00:00:00+00:00",
        "preset": "administrative_plan_retaliation",
        "filing_forum": "hud",
        "session_id": "session_1",
        "critic_score": 0.5,
        "summary": "Written notice and an informal review or hearing are required.",
        "caption": {
            "court": "HUD",
            "case_title": "Administrative Fair Housing Complaint",
            "document_title": "Draft HUD Housing Discrimination Complaint",
            "caption_note": "Note",
        },
        "parties": {
            "plaintiff": "Aggrieved person / complainant.",
            "defendant": "HACC, respondent.",
        },
        "jurisdiction_and_venue": ["HUD jurisdiction should be confirmed."],
        "factual_allegations": ["Fact one."],
        "claims_theory": ["Theory one."],
        "policy_basis": ["Policy one."],
        "causes_of_action": [{"title": "Administrative Fair Housing Process Failure", "theory": "Theory", "support": ["Support"]}],
        "proposed_allegations": ["Complainant alleges conduct arising from X."],
        "anchor_sections": ["appeal_rights"],
        "anchor_passages": ["Passage"],
        "supporting_evidence": ["Evidence"],
        "requested_relief": ["Administrative investigation."],
    }

    markdown = MODULE._render_markdown(package)

    assert "- Complainant: Aggrieved person / complainant." in markdown
    assert "- Respondent: HACC, respondent." in markdown
    assert "## Administrative Jurisdiction" in markdown
    assert "## Administrative Theory" in markdown
    assert "## Administrative Basis" in markdown
    assert "## Administrative Claims" in markdown
    assert "## Complainant Narrative" in markdown
    assert "## Requested Administrative Relief" in markdown


def test_markdown_groups_tagged_evidence_sections():
    package = {
        "generated_at": "2026-03-15T00:00:00+00:00",
        "preset": "accommodation_focus",
        "filing_forum": "hud",
        "session_id": "session_1",
        "critic_score": 0.5,
        "summary": "Summary.",
        "caption": {
            "court": "HUD",
            "case_title": "Administrative Fair Housing Complaint",
            "document_title": "Draft HUD Housing Discrimination Complaint",
            "caption_note": "Note",
        },
        "parties": {
            "plaintiff": "Aggrieved person / complainant.",
            "defendant": "HACC, respondent.",
        },
        "jurisdiction_and_venue": ["HUD jurisdiction should be confirmed."],
        "factual_allegations": ["Fact one."],
        "claims_theory": ["Theory one."],
        "policy_basis": [
            "ADMINISTRATIVE PLAN supports reasonable accommodation, adverse action: [reasonable_accommodation, notice, contact, adverse_action] Summary text. Full passage: Source text.",
        ],
        "causes_of_action": [{"title": "Administrative Fair Housing Process Failure", "theory": "Theory", "support": ["Support"]}],
        "claim_selection_summary": [
            {
                "title": "Administrative Fair Housing Process Failure",
                "selection_tags": ["notice", "hearing", "adverse_action"],
                "selected_exhibits": [{"exhibit_id": "Exhibit A", "label": "ADMINISTRATIVE PLAN"}],
                "selection_rationale": "selected for stronger notice and process language",
            }
        ],
        "proposed_allegations": ["Complainant alleges conduct arising from X."],
        "anchor_sections": ["reasonable_accommodation", "adverse_action"],
        "anchor_passages": [
            "ADMINISTRATIVE PLAN [reasonable_accommodation, adverse_action]: [reasonable_accommodation, notice, contact, adverse_action] Summary text. Full passage: Source text.",
        ],
        "supporting_evidence": [
            "ADMINISTRATIVE PLAN: [reasonable_accommodation, notice, contact, adverse_action] Summary text. Full passage: Source text. (/tmp/source.txt)",
        ],
        "requested_relief": ["Administrative investigation."],
    }

    markdown = MODULE._render_markdown(package)

    assert "## Exhibit Index" in markdown
    assert "- Exhibit A: ADMINISTRATIVE PLAN" in markdown
    assert "## Claim Selection Summary" in markdown
    assert "Administrative Fair Housing Process Failure: tags=notice, hearing, adverse_action;" in markdown
    assert "## Administrative Basis" in markdown
    assert "These policy excerpts frame the accommodation theory" in markdown
    assert "- Exhibit A: ADMINISTRATIVE PLAN supports reasonable accommodation, adverse action:" in markdown
    assert "See also Exhibit A (ADMINISTRATIVE PLAN) under Accommodation." in markdown
    assert "## Anchor Passages" in markdown
    assert "### Accommodation" in markdown
    assert "### Notice" in markdown
    assert "These passages support the accommodation theory" in markdown
    assert "See also Exhibit A (ADMINISTRATIVE PLAN [reasonable_accommodation, adverse_action]) under Accommodation." in markdown
    assert "## Supporting Evidence" in markdown
    assert "These materials support the notice theory" in markdown
    assert "See also Exhibit A (ADMINISTRATIVE PLAN) under Accommodation." in markdown
    assert markdown.count("### Accommodation") >= 2
    assert markdown.count("### Notice") >= 2


def test_selection_rationale_from_matrix_captures_tradeoff_metadata():
    matrix_payload = {
        "recommendations": {
            "best_overall": {
                "preset": "accommodation_focus",
                "claim_theory_families": ["accommodation", "process", "protected_basis"],
                "tradeoff_note": "best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing",
            }
        },
        "winner_delta": {
            "runner_up_preset": "administrative_plan_retaliation",
            "winner_only_theory_families": ["accommodation", "protected_basis"],
            "runner_up_only_theory_families": ["retaliation"],
            "shared_theory_families": ["process"],
            "winner_relief_overview": "winner relief overview",
            "runner_up_relief_overview": "runner relief overview",
            "winner_only_relief_families": ["protected_basis"],
            "runner_up_only_relief_families": ["retaliation"],
            "shared_relief_families": ["process"],
            "winner_only_claims": ["Fair Housing Act / Section 504 Accommodation Theory"],
            "runner_up_only_claims": ["Retaliation for Protected Fair Housing Activity"],
            "winner_only_relief": ["Protected-basis remedies."],
            "runner_up_only_relief": ["Retaliation remedies."],
        },
    }

    rationale = MODULE._selection_rationale_from_matrix(matrix_payload, "matrix")

    assert rationale["selected_preset"] == "accommodation_focus"
    assert rationale["claim_theory_families"] == ["accommodation", "process", "protected_basis"]
    assert rationale["tradeoff_note"].startswith("best for accommodation framing")
    assert rationale["runner_up_preset"] == "administrative_plan_retaliation"
    assert rationale["winner_only_theory_families"] == ["accommodation", "protected_basis"]
    assert rationale["winner_only_relief_families"] == ["protected_basis"]
    assert rationale["winner_only_relief"] == ["Protected-basis remedies."]


def test_markdown_includes_selection_rationale_section():
    package = {
        "generated_at": "2026-03-15T00:00:00+00:00",
        "preset": "accommodation_focus",
        "filing_forum": "hud",
        "session_id": "session_1",
        "critic_score": 0.5,
        "summary": "Summary.",
        "selection_rationale": {
            "selected_preset": "accommodation_focus",
            "claim_theory_families": ["accommodation", "process", "protected_basis"],
            "tradeoff_note": "best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing",
            "runner_up_preset": "administrative_plan_retaliation",
            "winner_only_theory_families": ["accommodation", "protected_basis"],
            "runner_up_only_theory_families": ["retaliation"],
            "shared_theory_families": ["process"],
            "winner_relief_overview": "winner relief overview",
            "runner_up_relief_overview": "runner relief overview",
            "winner_only_relief_families": ["protected_basis"],
            "runner_up_only_relief_families": ["retaliation"],
            "shared_relief_families": ["process"],
            "winner_only_relief": ["Protected-basis remedies."],
            "runner_up_only_relief": ["Retaliation remedies."],
        },
        "caption": {
            "court": "HUD",
            "case_title": "Administrative Fair Housing Complaint",
            "document_title": "Draft HUD Housing Discrimination Complaint",
            "caption_note": "Note",
        },
        "parties": {
            "plaintiff": "Aggrieved person / complainant.",
            "defendant": "HACC, respondent.",
        },
        "jurisdiction_and_venue": ["HUD jurisdiction should be confirmed."],
        "legal_theory_summary": {
            "theory_labels": ["reasonable_accommodation"],
            "protected_bases": ["disability"],
            "authority_hints": ["Section 504 of the Rehabilitation Act"],
        },
        "grounded_evidence_summary": [],
        "factual_allegations": ["Fact one."],
        "claims_theory": ["Theory one."],
        "policy_basis": ["Policy one."],
        "causes_of_action": [{"title": "Cause", "theory": "Theory", "support": ["Support"]}],
        "claim_selection_summary": [],
        "relief_selection_summary": [
            {
                "text": "Relief",
                "strategic_families": ["process"],
                "strategic_role": "shared_baseline",
                "strategic_note": "This relief item tracks the shared process baseline that appeared in both the selected preset and the runner-up.",
                "related_claims": ["Cause"],
            }
        ],
        "proposed_allegations": ["Proposed."],
        "anchor_sections": ["reasonable_accommodation"],
        "anchor_passages": ["Passage"],
        "supporting_evidence": ["Evidence"],
        "requested_relief": ["Relief"],
        "requested_relief_annotations": [
            {
                "text": "Relief",
                "strategic_note": "This relief item tracks the shared process baseline that appeared in both the selected preset and the runner-up.",
            }
        ],
    }

    markdown = MODULE._render_markdown(package)

    assert "## Selection Rationale" in markdown
    assert "- Selected preset: accommodation_focus" in markdown
    assert "- Why this preset won: best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing" in markdown
    assert "- Runner-up preset: administrative_plan_retaliation" in markdown
    assert "- Winner relief overview: winner relief overview" in markdown
    assert "- Runner-up relief overview: runner relief overview" in markdown
    assert "- Winner-only relief families: protected_basis" in markdown
    assert "- Runner-up-only relief families: retaliation" in markdown
    assert "- Shared relief families: process" in markdown
    assert "- Winner-only relief items: Protected-basis remedies." in markdown
    assert "- Runner-up-only relief items: Retaliation remedies." in markdown
    assert "## Relief Selection Summary" in markdown
    assert "families=process; role=shared_baseline; related_claims=Cause" in markdown
    assert "## Requested Administrative Relief" in markdown
    assert "This relief item tracks the shared process baseline that appeared in both the selected preset and the runner-up." in markdown


def test_markdown_selection_rationale_collapses_identical_relief_overviews():
    package = {
        "generated_at": "2026-03-15T00:00:00+00:00",
        "preset": "accommodation_focus",
        "filing_forum": "hud",
        "session_id": "session_1",
        "critic_score": 0.5,
        "summary": "Summary.",
        "selection_rationale": {
            "selected_preset": "accommodation_focus",
            "claim_theory_families": ["accommodation", "process", "protected_basis"],
            "tradeoff_note": "best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing",
            "runner_up_preset": "administrative_plan_retaliation",
            "winner_only_theory_families": ["accommodation", "protected_basis"],
            "runner_up_only_theory_families": ["retaliation"],
            "shared_theory_families": ["process"],
            "winner_relief_overview": "Same relief overview.",
            "runner_up_relief_overview": "Same relief overview.",
            "shared_relief_families": ["other"],
        },
        "caption": {"court": "HUD", "case_title": "Title", "document_title": "Doc", "caption_note": "Note"},
        "parties": {"plaintiff": "Complainant", "defendant": "HACC"},
        "jurisdiction_and_venue": ["Venue."],
        "legal_theory_summary": {"theory_labels": [], "protected_bases": [], "authority_hints": []},
        "grounded_evidence_summary": [],
        "factual_allegations": ["Fact."],
        "claims_theory": ["Theory."],
        "policy_basis": ["Policy."],
        "causes_of_action": [{"title": "Cause", "theory": "Theory", "support": ["Support"]}],
        "claim_selection_summary": [],
        "relief_selection_summary": [],
        "proposed_allegations": ["Proposed."],
        "anchor_sections": [],
        "anchor_passages": ["Passage"],
        "supporting_evidence": ["Evidence"],
        "requested_relief": ["Relief"],
    }

    markdown = MODULE._render_markdown(package)

    assert "Relief posture note: Relief posture was materially similar across the winner and runner-up" in markdown
    assert "- Winner relief overview:" not in markdown
    assert "- Runner-up relief overview:" not in markdown


def test_summary_with_selection_rationale_prefixes_tradeoff_note():
    summary = "HACC policy says applicants must be informed at application that reasonable accommodation is available."
    selection_rationale = {
        "selected_preset": "accommodation_focus",
        "tradeoff_note": "best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing",
    }

    combined = MODULE._summary_with_selection_rationale(summary, selection_rationale)

    assert combined.startswith("This draft follows the `accommodation_focus` path because best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing.")
    assert combined.endswith("HACC policy says applicants must be informed at application that reasonable accommodation is available.")


def test_summary_with_selection_rationale_mentions_when_relief_posture_is_materially_similar():
    summary = "HACC policy says applicants must be informed at application that reasonable accommodation is available."
    selection_rationale = {
        "selected_preset": "accommodation_focus",
        "tradeoff_note": "best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing",
        "winner_relief_overview": "Same relief overview.",
        "runner_up_relief_overview": "Same relief overview.",
        "shared_relief_families": ["other"],
    }

    combined = MODULE._summary_with_selection_rationale(summary, selection_rationale)

    assert "Relief posture was materially similar across the winner and runner-up" in combined
    assert combined.endswith("HACC policy says applicants must be informed at application that reasonable accommodation is available.")


def test_annotate_causes_with_selection_rationale_marks_winner_unique_and_shared_roles():
    causes = [
        {
            "title": "Fair Housing Act / Section 504 Accommodation Theory",
            "theory": "Accommodation theory.",
            "selection_tags": ["reasonable_accommodation", "contact"],
        },
        {
            "title": "Administrative Fair Housing Process Failure",
            "theory": "Notice and hearing theory.",
            "selection_tags": ["notice", "hearing", "adverse_action"],
        },
    ]
    selection_rationale = {
        "winner_only_claims": ["Fair Housing Act / Section 504 Accommodation Theory"],
        "shared_theory_families": ["process"],
        "winner_only_theory_families": ["accommodation", "protected_basis"],
    }

    annotated = MODULE._annotate_causes_with_selection_rationale(causes, selection_rationale)

    assert annotated[0]["strategic_role"] == "winner_unique_strength"
    assert "winner-specific strength" in annotated[0]["strategic_note"]
    assert annotated[1]["strategic_role"] == "shared_baseline"
    assert "shared baseline theory" in annotated[1]["strategic_note"]


def test_annotate_requested_relief_with_selection_rationale_marks_shared_and_winner_roles():
    causes = [
        {
            "title": "Fair Housing Act / Section 504 Accommodation Theory",
            "strategic_families": ["accommodation"],
            "strategic_role": "winner_unique_strength",
        },
        {
            "title": "Administrative Fair Housing Process Failure",
            "strategic_families": ["process"],
            "strategic_role": "shared_baseline",
        },
    ]
    relief = [
        "Corrective action requiring clear notice, fair review, and non-retaliation safeguards.",
        "Appropriate administrative remedies under fair housing law for accommodation-related harm.",
    ]
    selection_rationale = {
        "winner_only_theory_families": ["accommodation"],
        "shared_theory_families": ["process"],
    }

    annotated = MODULE._annotate_requested_relief_with_selection_rationale(relief, causes, selection_rationale)

    assert annotated[0]["strategic_role"] == "shared_baseline"
    assert "shared process" in annotated[0]["strategic_note"]
    assert annotated[0]["related_claims"] == ["Administrative Fair Housing Process Failure"]
    assert annotated[1]["strategic_role"] == "winner_unique_strength"
    assert "winner-specific accommodation" in annotated[1]["strategic_note"]
    assert annotated[1]["related_claims"] == ["Fair Housing Act / Section 504 Accommodation Theory"]


def test_annotate_requested_relief_with_selection_rationale_uses_only_matched_families_in_note():
    causes = [
        {
            "title": "Administrative Fair Housing Process Failure",
            "strategic_families": ["process"],
            "strategic_role": "shared_baseline",
        }
    ]
    relief = [
        "Corrective action requiring clear notice, fair review, and non-retaliation safeguards.",
    ]

    annotated = MODULE._annotate_requested_relief_with_selection_rationale(
        relief,
        causes,
        {"shared_theory_families": ["process", "retaliation"]},
    )

    assert annotated[0]["strategic_role"] == "shared_baseline"
    assert "shared process baseline" in annotated[0]["strategic_note"]
    assert "retaliation" not in annotated[0]["strategic_note"]


def test_relief_selection_summary_extracts_relief_metadata():
    relief_annotations = [
        {
            "text": "Corrective action requiring clear notice, fair review, and non-retaliation safeguards.",
            "strategic_families": ["process"],
            "strategic_role": "shared_baseline",
            "strategic_note": "This relief item tracks the shared process baseline that appeared in both the selected preset and the runner-up.",
            "related_claims": ["Administrative Fair Housing Process Failure"],
        }
    ]

    summary = MODULE._relief_selection_summary(relief_annotations)

    assert summary == [
        {
            "text": "Corrective action requiring clear notice, fair review, and non-retaliation safeguards.",
            "strategic_families": ["process"],
            "strategic_role": "shared_baseline",
            "strategic_note": "This relief item tracks the shared process baseline that appeared in both the selected preset and the runner-up.",
            "related_claims": ["Administrative Fair Housing Process Failure"],
        }
    ]


def test_grounded_supporting_evidence_merges_packets_and_uploads():
    grounding_bundle = {
        "query": "reasonable accommodation hearing rights",
        "claim_type": "housing_discrimination",
        "mediator_evidence_packets": [
            {
                "document_label": "README.txt",
                "relative_path": "README.txt",
                "source_path": "/tmp/README.txt",
            }
        ],
        "synthetic_prompts": {
            "complaint_chatbot_prompt": "Ground the complaint chatbot in uploaded repository evidence.",
        },
    }
    upload_report = {
        "upload_count": 1,
        "uploads": [
            {
                "title": "README.txt",
                "relative_path": "README.txt",
                "result": {"claim_type": "housing_discrimination"},
            }
        ],
        "support_summary": {"total_links": 2},
    }

    lines = MODULE._grounded_supporting_evidence(grounding_bundle, upload_report)
    summary = MODULE._grounded_summary_lines(grounding_bundle, upload_report)

    assert len(lines) == 1
    assert "prepared as mediator evidence for grounded intake" in lines[0]
    assert "uploaded into mediator evidence store" in lines[0]
    assert any("Grounding query: reasonable accommodation hearing rights" == line for line in summary)
    assert any("Mediator preload / upload count: 1" == line for line in summary)
    assert any("Claim-support links recorded: 2" == line for line in summary)


def test_merge_seed_with_grounding_replaces_toc_summary_with_grounded_snippet():
    seed = {
        "summary": "14 GRIEVANCES AND APPEALS INTRODUCTION ........ 14-1 PART I: INFORMAL HEARINGS ........ 14-2",
        "key_facts": {
            "evidence_summary": "14 GRIEVANCES AND APPEALS INTRODUCTION ........ 14-1 PART I: INFORMAL HEARINGS ........ 14-2",
        },
        "hacc_evidence": [],
    }
    grounding_bundle = {
        "search_payload": {
            "results": [
                {
                    "title": "ADMINISTRATIVE PLAN",
                    "snippet": "Applicants or tenant families who wish to file a VAWA complaint against HACC may request an informal hearing.",
                    "source_path": "/tmp/admin-plan.txt",
                }
            ]
        }
    }

    merged = MODULE._merge_seed_with_grounding(seed, grounding_bundle)

    assert merged["summary"].startswith("Applicants or tenant families")
    assert merged["key_facts"]["evidence_summary"].startswith("Applicants or tenant families")
    assert merged["hacc_evidence"][0]["title"] == "ADMINISTRATIVE PLAN"


def test_merge_seed_with_grounding_promotes_stronger_grounded_evidence_into_anchor_passages(tmp_path):
    source_path = tmp_path / "policy.txt"
    source_path.write_text(
        "I. Definitions applicable to the grievance procedure [24 CFR 966.53]\n\n"
        "A. Grievance: Any dispute a tenant may have with respect to HACC action or failure to act in accordance with the individual tenant's lease or HACC regulations that adversely affects the individual tenant's rights, duties, welfare, or status.\n\n"
        "C. Elements of due process: An eviction action or a termination of tenancy in a state or local court in which adequate notice and an opportunity to refute the evidence are required.\n",
        encoding="utf-8",
    )

    seed = {
        "key_facts": {
            "anchor_titles": ["ADMISSIONS AND CONTINUED OCCUPANCY POLICY"],
            "anchor_source_paths": [str(source_path)],
            "anchor_passages": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "source_path": str(source_path),
                    "snippet": "HACC policy describes an informal hearing process for applicants and residents.",
                    "section_labels": ["grievance_hearing"],
                }
            ],
        },
        "hacc_evidence": [],
    }
    grounding_bundle = {
        "search_payload": {
            "results": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "source_path": str(source_path),
                    "snippet": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
                    "matched_rules": [
                        {
                            "text": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
                            "section_title": "I. Definitions applicable to the grievance procedure [24 CFR 966.53]",
                        },
                        {
                            "text": "C. Elements of due process: An eviction action or a termination of tenancy in a state or local court in which adequate notice and an opportunity to refute the evidence are required.",
                            "section_title": "I. Definitions applicable to the grievance procedure [24 CFR 966.53]",
                        },
                    ],
                }
            ]
        }
    }

    merged = MODULE._merge_seed_with_grounding(seed, grounding_bundle)

    assert "Elements of due process" in merged["hacc_evidence"][0]["snippet"]
    assert "Elements of due process" in merged["key_facts"]["anchor_passages"][0]["snippet"]


def test_merge_seed_with_grounding_refreshes_anchor_passages_from_source_text(tmp_path):
    source_path = tmp_path / "policy.txt"
    source_path.write_text(
        "Administrative Plan - Table of Contents\n"
        "Scheduling an Informal Review ........ 16-11\n"
        "Informal Review Procedures ........ 16-11\n\n"
        "Scheduling an Informal Review\n\n"
        "HACC Policy\n\n"
        "A request for an informal review must be made in writing and delivered to HACC.\n"
        "HACC must schedule and send written notice of the informal review within 10 business days.\n",
        encoding="utf-8",
    )

    seed = {
        "summary": "Scheduling an Informal Review ........ 16-11",
        "key_facts": {
            "anchor_terms": ["grievance", "hearing", "appeal"],
            "anchor_passages": [
                {
                    "title": "ADMINISTRATIVE PLAN",
                    "source_path": str(source_path),
                    "snippet": "Scheduling an Informal Review ........ 16-11",
                    "section_labels": ["appeal_rights"],
                }
            ],
        },
        "hacc_evidence": [
            {
                "title": "ADMINISTRATIVE PLAN",
                "source_path": str(source_path),
                "snippet": "Scheduling an Informal Review ........ 16-11",
            }
        ],
    }

    merged = MODULE._merge_seed_with_grounding(seed, {})

    assert "must schedule and send written notice" in merged["key_facts"]["anchor_passages"][0]["snippet"]
    assert "must schedule and send written notice" in merged["hacc_evidence"][0]["snippet"]
    assert "........ 16-11" not in merged["key_facts"]["anchor_passages"][0]["snippet"]


def test_merge_seed_with_grounding_uses_matched_rule_when_refresh_hits_placeholder_text():
    seed = {
        "key_facts": {
            "anchor_terms": ["grievance", "hearing", "appeal"],
            "anchor_passages": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "source_path": "/tmp/acop.txt",
                    "snippet": "[The following is an optional section where the PHA may include referral services to support a family in finding new housing.]",
                    "section_labels": ["grievance_hearing"],
                }
            ],
        },
        "hacc_evidence": [
            {
                "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                "source_path": "/tmp/acop.txt",
                "snippet": "[The following is an optional section where the PHA may include referral services to support a family in finding new housing.]",
                "matched_rules": [
                    {
                        "text": "In states without due process determinations, HACC must grant opportunity for grievance hearings."
                    }
                ],
            }
        ],
    }

    merged = MODULE._merge_seed_with_grounding(seed, {})

    assert "must grant opportunity for grievance hearings" in merged["hacc_evidence"][0]["snippet"]
    assert "must grant opportunity for grievance hearings" in merged["key_facts"]["anchor_passages"][0]["snippet"]


def test_merge_seed_with_grounding_uses_matched_rule_when_snippet_is_generic_chapter_intro():
    seed = {
        "key_facts": {
            "anchor_terms": ["grievance", "hearing", "appeal"],
            "anchor_passages": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "source_path": "/tmp/acop.txt",
                    "snippet": "GRIEVANCES AND APPEALS INTRODUCTION This chapter discusses grievances and appeals pertaining to HACC actions or failures to act that adversely affect public housing applicants or residents.",
                    "section_labels": ["grievance_hearing"],
                }
            ],
        },
        "hacc_evidence": [
            {
                "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                "source_path": "/tmp/acop.txt",
                "snippet": "GRIEVANCES AND APPEALS INTRODUCTION This chapter discusses grievances and appeals pertaining to HACC actions or failures to act that adversely affect public housing applicants or residents.",
                "matched_rules": [
                    {
                        "text": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
                    },
                    {
                        "text": "If HUD has issued a due process determination, HACC may exclude from HACC grievance",
                    },
                ],
            }
        ],
    }

    merged = MODULE._merge_seed_with_grounding(seed, {})

    assert "Grievance: Any dispute" in merged["hacc_evidence"][0]["snippet"]
    assert "If HUD has issued a due process determination" in merged["key_facts"]["anchor_passages"][0]["snippet"]


def test_merge_seed_with_grounding_refreshes_grievance_procedure_with_due_process_section(tmp_path):
    source_path = tmp_path / "policy.txt"
    source_path.write_text(
        "I. Definitions applicable to the grievance procedure [24 CFR 966.53]\n\n"
        "A. Grievance: Any dispute a tenant may have with respect to HACC action or failure to act in accordance with the individual tenant's lease or HACC regulations that adversely affects the individual tenant's rights, duties, welfare, or status.\n\n"
        "B. Complainant: Any tenant whose grievance is presented to HACC.\n\n"
        "C. Elements of due process: An eviction action or a termination of tenancy in a state or local court in which adequate notice and an opportunity to refute the evidence are required.\n",
        encoding="utf-8",
    )

    seed = {
        "key_facts": {
            "anchor_terms": ["grievance", "hearing", "appeal"],
            "anchor_passages": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "source_path": str(source_path),
                    "snippet": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
                    "section_labels": ["grievance_hearing"],
                }
            ],
        },
        "hacc_evidence": [
            {
                "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                "source_path": str(source_path),
                "snippet": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
                "matched_rules": [
                    {
                        "text": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
                        "section_title": "I. Definitions applicable to the grievance procedure [24 CFR 966.53]",
                    }
                ],
            }
        ],
    }

    merged = MODULE._merge_seed_with_grounding(seed, {})

    assert "C. Elements of due process" in merged["hacc_evidence"][0]["snippet"]
    assert "C. Elements of due process" in merged["key_facts"]["anchor_passages"][0]["snippet"]


def test_best_grounding_result_excerpt_combines_truncated_rule_with_followup_rule():
    item = {
        "snippet": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
        "matched_rules": [
            {"text": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to"},
            {"text": "In states without due process determinations, HACC must grant opportunity for grievance hearings."},
        ],
    }

    excerpt = MODULE._best_grounding_result_excerpt(item)

    assert "Grievance: Any dispute" in excerpt
    assert "must grant opportunity for grievance hearings" in excerpt


def test_best_grounding_result_excerpt_expands_truncated_rule_from_source(tmp_path):
    source_path = tmp_path / "policy.txt"
    source_path.write_text(
        "EXHIBIT 14-1: SAMPLE GRIEVANCE PROCEDURE\n\n"
        "I. Definitions applicable to the grievance procedure [24 CFR 966.53]\n\n"
        "A. Grievance: Any dispute a tenant may have with respect to HACC action or failure to act in accordance with the individual tenant's lease or HACC regulations that adversely affects the individual tenant's rights, duties, welfare, or status.\n",
        encoding="utf-8",
    )

    item = {
        "source_path": str(source_path),
        "snippet": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
        "matched_rules": [
            {
                "text": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
                "section_title": "EXHIBIT 14-1: SAMPLE GRIEVANCE PROCEDURE",
            }
        ],
    }

    excerpt = MODULE._best_grounding_result_excerpt(item)

    assert "Definitions applicable to the grievance procedure" in excerpt
    assert "adversely affects the individual tenant's rights" in excerpt


def test_best_grounding_result_excerpt_prefers_source_expansion_over_combined_truncated_rules(tmp_path):
    source_path = tmp_path / "policy.txt"
    source_path.write_text(
        "I. Definitions applicable to the grievance procedure [24 CFR 966.53]\n\n"
        "A. Grievance: Any dispute a tenant may have with respect to HACC action or failure to act in accordance with the individual tenant's lease or HACC regulations that adversely affects the individual tenant's rights, duties, welfare, or status.\n\n"
        "C. Elements of due process: An eviction action or a termination of tenancy in a state or local court in which the following procedural safeguards are required.\n\n"
        "If HUD has issued a due process determination, HACC may exclude from HACC grievance procedure any grievance concerning a termination of tenancy or eviction that involves criminal activity.\n",
        encoding="utf-8",
    )

    item = {
        "source_path": str(source_path),
        "snippet": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
        "matched_rules": [
            {
                "text": "Grievance: Any dispute a tenant may have with respect to HACC action or failure to",
                "section_title": "I. Definitions applicable to the grievance procedure [24 CFR 966.53]",
            },
            {
                "text": "If HUD has issued a due process determination, HACC may exclude from HACC grievance",
            },
        ],
    }

    excerpt = MODULE._best_grounding_result_excerpt(item)

    assert "act in accordance with the individual tenant's lease" in excerpt
    assert "Elements of due process" in excerpt
    assert "exclude from HACC grievance procedure" in excerpt


def test_best_grounding_result_excerpt_expands_toc_like_informal_review_snippet(tmp_path):
    source_path = tmp_path / "policy.txt"
    source_path.write_text(
        "Scheduling an Informal Review ........ 16-11\n\n"
        "The notice must describe how to obtain the informal review.\n\n"
        "Scheduling an Informal Review\n\n"
        "HACC Policy\n\n"
        "A request for an informal review must be made in writing and delivered to HACC.\n"
        "HACC must schedule and send written notice of the informal review within 10 business days.\n",
        encoding="utf-8",
    )

    item = {
        "source_path": str(source_path),
        "snippet": "16-11 Scheduling an Informal Review ................................................... 16-11 Informal Review Procedures [24 CFR 982.554(b)] ..................... 16-11",
        "matched_rules": [],
    }

    excerpt = MODULE._best_grounding_result_excerpt(item)

    assert "must schedule and send written notice" in excerpt
    assert "Informal Review Procedures" not in excerpt


def test_grounding_results_to_seed_evidence_refreshes_toc_like_informal_review_snippet(tmp_path):
    source_path = tmp_path / "policy.txt"
    source_path.write_text(
        "Scheduling an Informal Review ........ 16-11\n\n"
        "The notice must describe how to obtain the informal review.\n\n"
        "Scheduling an Informal Review\n\n"
        "HACC Policy\n\n"
        "A request for an informal review must be made in writing and delivered to HACC.\n"
        "HACC must schedule and send written notice of the informal review within 10 business days.\n",
        encoding="utf-8",
    )

    grounding_bundle = {
        "search_payload": {
            "results": [
                {
                    "title": "ADMINISTRATIVE PLAN",
                    "source_path": str(source_path),
                    "snippet": "16-11 Scheduling an Informal Review ................................................... 16-11 Informal Review Procedures [24 CFR 982.554(b)] ..................... 16-11",
                    "matched_rules": [],
                }
            ]
        }
    }

    evidence = MODULE._grounding_results_to_seed_evidence(grounding_bundle)

    assert "must schedule and send written notice" in evidence[0]["snippet"]
    assert "Informal Review Procedures" not in evidence[0]["snippet"]


def test_anchor_passage_lines_omit_full_passage_for_toc_like_snippet():
    seed = {
        "key_facts": {
            "anchor_passages": [
                {
                    "title": "ADMINISTRATIVE PLAN",
                    "section_labels": ["grievance_hearing"],
                    "snippet": "16-11 Scheduling an Informal Review ................................................... 16-11 Informal Review Procedures [24 CFR 982.554(b)] ..................... 16-11",
                }
            ]
        }
    }

    lines = MODULE._anchor_passage_lines(seed)

    assert len(lines) == 1
    assert "Full passage:" not in lines[0]
    assert "describes scheduling and procedures for informal review" in lines[0]


def test_anchor_passage_lines_omit_full_passage_for_generic_chapter_intro():
    seed = {
        "key_facts": {
            "anchor_passages": [
                {
                    "title": "ADMISSIONS AND CONTINUED OCCUPANCY POLICY",
                    "section_labels": ["grievance_hearing"],
                    "snippet": "GRIEVANCES AND APPEALS INTRODUCTION This chapter discusses grievances and appeals pertaining to HACC actions or failures to act that adversely affect public housing applicants or residents. The policies are discussed in the following three parts: Part I: Informal Hearings for Public Housing Applicants.",
                }
            ]
        }
    }

    lines = MODULE._anchor_passage_lines(seed)

    assert len(lines) == 1
    assert "Full passage:" not in lines[0]
def test_filter_grounding_evidence_for_seed_prefers_anchor_titles():
    seed = {
        "key_facts": {
            "anchor_titles": ["ADMINISTRATIVE PLAN"],
        }
    }
    evidence_items = [
        {"title": "Supportive Housing Services Program", "source_path": "/tmp/other.txt"},
        {"title": "ADMINISTRATIVE PLAN", "source_path": "/tmp/admin-plan.txt"},
    ]

    filtered = MODULE._filter_grounding_evidence_for_seed(seed, evidence_items)

    assert filtered == [{"title": "ADMINISTRATIVE PLAN", "source_path": "/tmp/admin-plan.txt"}]
def test_markdown_includes_grounded_evidence_run_section():
    package = {
        "generated_at": "2026-03-15T00:00:00+00:00",
        "preset": "core_hacc_policies",
        "filing_forum": "court",
        "session_id": "session_1",
        "critic_score": 0.7,
        "summary": "Summary.",
        "caption": {
            "court": "Court to be determined",
            "case_title": "Complainant v. Housing Authority of Clackamas County",
            "document_title": "Draft Complaint",
            "caption_note": "Note",
        },
        "parties": {
            "plaintiff": "Complainant",
            "defendant": "HACC",
        },
        "jurisdiction_and_venue": ["Venue statement."],
        "legal_theory_summary": {
            "theory_labels": ["reasonable_accommodation"],
            "protected_bases": ["disability"],
            "authority_hints": ["Section 504 of the Rehabilitation Act"],
        },
        "grounded_evidence_summary": [
            "Grounding query: reasonable accommodation hearing rights",
            "Mediator preload / upload count: 1",
        ],
        "factual_allegations": ["Fact one."],
        "claims_theory": ["Theory one."],
        "policy_basis": ["Policy one."],
        "causes_of_action": [{"title": "Cause", "theory": "Theory", "support": ["Support"]}],
        "claim_selection_summary": [],
        "proposed_allegations": ["Proposed."],
        "anchor_sections": ["reasonable_accommodation"],
        "anchor_passages": ["Passage"],
        "supporting_evidence": ["Evidence"],
        "requested_relief": ["Relief"],
    }

    markdown = MODULE._render_markdown(package)

    assert "## Grounded Evidence Run" in markdown
    assert "- Grounding query: reasonable accommodation hearing rights" in markdown
    assert "- Mediator preload / upload count: 1" in markdown


def test_inject_exhibit_references_adds_citations_to_claims_and_facts():
    package = {
        "claims_theory": [
            "The strongest policy support for these theories is: Written notice and accommodation language are required.",
        ],
        "factual_allegations": [
            "The complainant contends that accommodation-related concerns were not fairly addressed.",
        ],
        "causes_of_action": [
            {
                "title": "Administrative Fair Housing Process Failure",
                "theory": "Theory text about notice and adverse-action process.",
                "support": ["Support text."],
            },
            {
                "title": "Fair Housing Act / Section 504 Accommodation Theory",
                "theory": "Theory text about accommodation rights.",
                "support": ["Support text."],
            }
        ],
        "policy_basis": [
            "ADMINISTRATIVE PLAN supports reasonable accommodation, adverse action: [reasonable_accommodation, notice, contact] Summary. Full passage: Source.",
            "NOTICE POLICY supports adverse action: [notice, adverse_action, hearing] Summary. Full passage: Source.",
        ],
        "anchor_passages": [
            "ADMINISTRATIVE PLAN [reasonable_accommodation, adverse_action]: [reasonable_accommodation, notice] Summary. Full passage: Source.",
        ],
        "supporting_evidence": [
            "ADMINISTRATIVE PLAN: [reasonable_accommodation, notice] Summary. Full passage: Source. (/tmp/source.txt)",
        ],
    }

    MODULE._inject_exhibit_references(package)

    assert "Exhibit A (ADMINISTRATIVE PLAN)" in package["claims_theory"][0]
    assert any("Exhibit A (ADMINISTRATIVE PLAN)" in item for item in package["factual_allegations"])
    assert any(
        item.startswith("Documentary support: Exhibit B (NOTICE POLICY). Rationale:")
        for item in package["causes_of_action"][0]["support"]
    )
    assert any(
        item.startswith("Documentary support: Exhibit A (ADMINISTRATIVE PLAN). Rationale:")
        for item in package["causes_of_action"][1]["support"]
    )
    assert package["causes_of_action"][0]["selected_exhibits"][0]["label"] == "NOTICE POLICY"
    assert package["causes_of_action"][1]["selected_exhibits"][0]["label"] == "ADMINISTRATIVE PLAN"
    assert package["causes_of_action"][0]["selection_rationale"]
    assert "notice" in package["causes_of_action"][0]["selection_tags"]


def test_claim_selection_summary_extracts_cause_metadata():
    causes = [
        {
            "title": "Administrative Fair Housing Process Failure",
            "selection_tags": ["notice", "hearing", "adverse_action"],
            "selected_exhibits": [{"exhibit_id": "Exhibit B", "label": "ADMINISTRATIVE PLAN"}],
            "selection_rationale": "selected for stronger notice and process language",
        }
    ]

    summary = MODULE._claim_selection_summary(causes)

    assert summary == [
        {
            "title": "Administrative Fair Housing Process Failure",
            "selection_tags": ["notice", "hearing", "adverse_action"],
            "selected_exhibits": [{"exhibit_id": "Exhibit B", "label": "ADMINISTRATIVE PLAN"}],
            "selection_rationale": "selected for stronger notice and process language",
        }
    ]


def test_single_exhibit_margin_varies_by_cause_type():
    process_cause = {"title": "Administrative Fair Housing Process Failure", "theory": "Notice and hearing theory."}
    accommodation_cause = {"title": "Fair Housing Act / Section 504 Accommodation Theory", "theory": "Accommodation and disability theory."}
    protected_basis_cause = {"title": "Protected-Basis Administrative Theory", "theory": "Disability discrimination theory."}

    assert MODULE._single_exhibit_margin_for_cause(process_cause) == 3
    assert MODULE._single_exhibit_margin_for_cause(accommodation_cause) == 1
    assert MODULE._single_exhibit_margin_for_cause(protected_basis_cause) == 1


def test_protected_basis_cause_uses_dedicated_selection_tag():
    protected_basis_cause = {"title": "Protected-Basis Administrative Theory", "theory": "Disability discrimination theory."}

    assert MODULE._cause_target_tags(protected_basis_cause) == ["protected_basis"]


def test_accommodation_cause_prefers_narrow_selection_tags():
    accommodation_cause = {
        "title": "Fair Housing Act / Section 504 Accommodation Theory",
        "theory": "Accommodation-related issues intersected with adverse-action or review procedures.",
    }

    assert MODULE._cause_target_tags(accommodation_cause) == ["reasonable_accommodation", "contact"]


def test_summarize_timeline_fact_condenses_numbered_intake_timeline():
    fact = (
        "I'm very cooperative. Here's the best timeline I can give right now: "
        "1. Late 2025 - I raised concerns and started using the grievance process. "
        "2. Shortly after - HACC moved toward denying or terminating my assistance. "
        "3. Following that - I tried to get an informal review/hearing and a written decision. "
        "4. Within the next few weeks - I had to explain the situation to the initial PHA without documentation."
    )

    summary = MODULE._summarize_timeline_fact(fact)

    assert "Late 2025 - I raised concerns and started using the grievance process" in summary
    assert "Shortly after - HACC moved toward denying or terminating my assistance" in summary
    assert "Within the next few weeks - I had to explain the situation to the initial PHA without documentation" in summary
    assert "Here's the best timeline" not in summary


def test_factual_allegations_keep_single_deduped_timeline():
    seed = {
        "description": "Retaliation and grievance complaint anchored to the HACC Administrative Plan.",
        "key_facts": {"anchor_sections": ["appeal_rights", "adverse_action"]},
    }
    session = {
        "conversation_history": [
            {
                "role": "complainant",
                "content": (
                    "Here's the best timeline I can give right now: 1. Late 2025 - I raised concerns and started "
                    "using the grievance process. 2. Shortly after - HACC moved toward denying or terminating my "
                    "assistance. 3. Following that - I tried to get an informal review/hearing and a written decision."
                ),
            },
            {
                "role": "complainant",
                "content": (
                    "Here's the fuller timeline as I remember it: 1. Late 2025 (roughly November/December) - I "
                    "raised concerns and tried to use the grievance process. 2. Within a short time after that - "
                    "HACC moved toward denying or terminating my assistance. 3. After that - I asked for an "
                    "informal review/hearing and a written decision."
                ),
            },
        ]
    }

    allegations = MODULE._factual_allegations(seed, session)
    timeline_items = [item for item in allegations if item.startswith("Timeline detail from intake:")]

    assert len(timeline_items) == 1
    assert "Late 2025" in timeline_items[0]
    assert "HACC moved toward denying or terminating my assistance" in timeline_items[0]


def test_proposed_allegations_summarize_intake_transcript():
    seed = {
        "description": "Retaliation and grievance complaint anchored to the HACC Administrative Plan.",
        "key_facts": {
            "incident_summary": "Retaliation and grievance complaint anchored to the HACC Administrative Plan.",
            "evidence_summary": "Written notice and an informal review or hearing are required.",
            "anchor_sections": ["appeal_rights", "adverse_action"],
        },
    }
    session = {
        "conversation_history": [
            {
                "role": "complainant",
                "content": (
                    "I'm filing a complaint about retaliation and the way my grievance and appeal were handled. "
                    "I did not receive clear written notice of the adverse action or a meaningful opportunity to be heard. "
                    "This has been extremely stressful and destabilizing."
                ),
            },
            {
                "role": "complainant",
                "content": (
                    "The impact has been really destabilizing. I didn't get clear written notice of the adverse action "
                    "or a written hearing decision, so I was left in limbo."
                ),
            },
        ]
    }

    allegations = MODULE._proposed_allegations(seed, session, "court")
    intake_items = [item for item in allegations if item.startswith("During intake, the complainant stated that")]

    assert intake_items
    assert any("retaliation" in item.lower() for item in intake_items)
    assert any("written notice" in item.lower() for item in intake_items)
    assert all(len(item) < 260 for item in intake_items)


def test_summary_and_narrative_use_condensed_policy_excerpt():
    seed = {
        "description": "Reasonable-accommodation complaint anchored to HACC policy language.",
        "key_facts": {
            "incident_summary": "Reasonable-accommodation complaint anchored to HACC policy language.",
            "evidence_summary": (
                "This responsibility begins with the first contact by an interested family and continues through every "
                "aspect of the program. HACC will ask all applicants and participants if they require any type of "
                "accommodations in writing, on the intake application, reexamination documents, and notices of adverse "
                "action by HACC. A specific name and phone number of designated staff will be provided to process "
                "requests for accommodation."
            ),
            "anchor_sections": ["reasonable_accommodation"],
        },
    }
    session = {"conversation_history": []}

    summary = MODULE._summarize_policy_excerpt(seed["key_facts"]["evidence_summary"])
    allegations = MODULE._proposed_allegations(seed, session, "hud")

    assert "first contact by an interested family" not in summary
    assert "must be asked in writing about accommodation needs" in summary
    assert any("must be asked in writing about accommodation needs" in item for item in allegations)
    assert not any("first contact by an interested family" in item for item in allegations)
