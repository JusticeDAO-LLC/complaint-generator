from document_pipeline import FormalComplaintDocumentBuilder


class _ExplodingMediator:
    def generate_formal_complaint(self, **kwargs):
        raise AttributeError("'NoneType' object has no attribute 'get_entities_by_type'")


class _EvidenceFactMediator:
    def __init__(self):
        self.phase_manager = None
        self.state = type(
            "_State",
            (),
            {
                "legal_classification": {},
                "applicable_statutes": [],
                "summary_judgment_requirements": {},
                "inquiries": [],
                "complaint": None,
                "original_complaint": None,
            },
        )()

    def get_user_evidence(self, *, user_id):
        assert user_id == "evidence-user"
        return [
            {
                "id": 101,
                "cid": "bafy-evidence-1",
                "claim_type": "housing_discrimination",
                "description": "Adverse action notice",
                "parsed_text_preview": "HACC issued a written denial notice after the grievance request.",
                "metadata": {"summary": "Repository-grounded HACC policy and notice record."},
            }
        ]

    def get_evidence_facts(self, *, evidence_id):
        assert evidence_id == 101
        return [
            {
                "fact_id": "fact-1",
                "text": "On March 3, 2026, HACC sent Plaintiff a written denial notice after Plaintiff requested a grievance hearing.",
            }
        ]


def test_build_draft_falls_back_to_legacy_builder_when_canonical_generation_crashes(monkeypatch):
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())
    legacy_calls = {}

    def _fake_legacy_builder(**kwargs):
        legacy_calls.update(kwargs)
        return {
            "title": "Fallback complaint",
            "claims_for_relief": [{"claim_type": "housing_discrimination"}],
            "factual_allegations": ["Fallback factual allegation."],
            "requested_relief": ["Fallback relief."],
            "exhibits": [{"label": "Exhibit A", "title": "Fallback exhibit"}],
            "draft_text": "Fallback complaint draft.",
        }

    monkeypatch.setattr(builder, "_build_legacy_draft", _fake_legacy_builder)

    draft = builder.build_draft(
        user_id="fallback-user",
        court_name="United States District Court",
        district="Northern District of California",
        county=None,
        division=None,
        court_header_override=None,
        case_number=None,
        lead_case_number=None,
        related_case_number=None,
        assigned_judge=None,
        courtroom=None,
        title_override=None,
        plaintiff_names=["Jane Doe"],
        defendant_names=["Housing Authority"],
        requested_relief=None,
        jury_demand=None,
        jury_demand_text=None,
        signer_name=None,
        signer_title=None,
        signer_firm=None,
        signer_bar_number=None,
        signer_contact=None,
        additional_signers=None,
        declarant_name=None,
        service_method=None,
        service_recipients=None,
        service_recipient_details=None,
        signature_date=None,
        verification_date=None,
        service_date=None,
        affidavit_title=None,
        affidavit_intro=None,
        affidavit_facts=None,
        affidavit_supporting_exhibits=None,
        affidavit_include_complaint_exhibits=None,
        affidavit_venue_lines=None,
        affidavit_jurat=None,
        affidavit_notary_block=None,
    )

    assert draft["title"] == "Fallback complaint"
    assert draft["draft_text"] == "Fallback complaint draft."
    assert legacy_calls["user_id"] == "fallback-user"


def test_summary_fact_entries_include_uploaded_evidence_facts_when_intake_facts_are_missing():
    builder = FormalComplaintDocumentBuilder(_EvidenceFactMediator())

    entries = builder._build_summary_fact_entries(
        user_id="evidence-user",
        generated_complaint={},
        classification={},
        state=builder.mediator.state,
    )

    texts = [entry["text"] for entry in entries]

    assert any("On March 3, 2026, HACC sent Plaintiff a written denial notice" in text for text in texts)
    assert not texts[0].startswith("Additional factual development is required before filing")


def test_uploaded_evidence_text_candidates_extract_complaint_usable_fragments():
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())

    fragments = builder._extract_uploaded_evidence_text_candidates(
        """
        ## HACC Policy
        Use for: implementation notes only
        HACC policy requires written notice before an informal hearing.
        from parser import example
        HACC must respond to a grievance request and provide appeal rights.
        """,
        limit=4,
    )

    assert "HACC policy requires written notice before an informal hearing." in fragments
    assert "HACC must respond to a grievance request and provide appeal rights." in fragments
    assert all("from parser import example" not in fragment for fragment in fragments)
