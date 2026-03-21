from document_pipeline import FormalComplaintDocumentBuilder


class _ExplodingMediator:
    def generate_formal_complaint(self, **kwargs):
        raise AttributeError("'NoneType' object has no attribute 'get_entities_by_type'")


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
