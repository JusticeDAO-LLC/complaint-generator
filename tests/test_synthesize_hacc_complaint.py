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


def test_claims_theory_and_markdown_include_structured_sections():
    seed = {
        "description": "Retaliation and grievance complaint anchored to the HACC Administrative Plan.",
        "key_facts": {
            "evidence_summary": (
                "The strongest supporting material is 'ADMINISTRATIVE PLAN'. "
                "HACC Policy Written notice and an informal review or hearing are required."
            ),
            "anchor_sections": ["appeal_rights", "adverse_action"],
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
        }
    }

    summary = MODULE._legal_theory_summary(seed)

    assert summary["theory_labels"] == ["reasonable_accommodation", "disability_discrimination"]
    assert summary["protected_bases"] == ["disability"]


def test_claims_and_causes_include_protected_basis_theory():
    seed = {
        "description": "Reasonable-accommodation complaint anchored to HACC policy language.",
        "key_facts": {
            "evidence_summary": "Reasonable accommodation review is required.",
            "anchor_sections": ["reasonable_accommodation", "adverse_action"],
            "theory_labels": ["reasonable_accommodation", "disability_discrimination"],
            "protected_bases": ["disability"],
        },
    }
    session = {"conversation_history": []}

    claims = MODULE._claims_theory(seed, session)
    causes = MODULE._causes_of_action(seed, session, "hud")

    assert any("protected basis concerns related to disability" in item.lower() for item in claims)
    assert any("Protected-Basis Administrative Theory" == cause["title"] for cause in causes)


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
