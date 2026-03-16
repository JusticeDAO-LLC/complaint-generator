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


def test_specific_refresh_terms_add_notice_headings_for_admin_plan_toc_seed():
    terms = MODULE._specific_refresh_terms(
        title="ADMINISTRATIVE PLAN",
        source_path="/tmp/admin-plan.txt",
        snippet="16-11 Scheduling an Informal Review ................................................... 16-11",
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
