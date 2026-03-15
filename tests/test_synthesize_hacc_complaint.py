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
        "session_id": "session_1",
        "critic_score": 0.5,
        "summary": MODULE._clean_policy_text(seed["key_facts"]["evidence_summary"]),
        "caption": MODULE._draft_caption(seed),
        "parties": MODULE._draft_parties(),
        "jurisdiction_and_venue": MODULE._jurisdiction_and_venue(seed),
        "factual_allegations": MODULE._factual_allegations(seed, session),
        "claims_theory": MODULE._claims_theory(seed, session),
        "policy_basis": MODULE._policy_basis(seed),
        "causes_of_action": MODULE._causes_of_action(seed, session),
        "proposed_allegations": MODULE._proposed_allegations(seed, session),
        "anchor_sections": list(seed["key_facts"]["anchor_sections"]),
        "anchor_passages": MODULE._anchor_passage_lines(seed),
        "supporting_evidence": MODULE._evidence_lines(seed),
        "requested_relief": ["Declaratory relief."],
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
    assert "## Factual Allegations" in markdown
    assert "## Claims Theory" in markdown
    assert "## Policy Basis" in markdown
    assert "## Causes Of Action" in markdown
