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


class _EvidenceClaimTypeMediator(_ExplodingMediator):
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
        assert user_id == "evidence-claim-user"
        return [
            {
                "id": 202,
                "description": "Grievance denial notice",
                "claim_type": "housing_discrimination",
                "metadata": {"claim_types": ["due_process_failure"]},
            }
        ]


class _HousingProcessMediator(_ExplodingMediator):
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
        assert user_id == "housing-process-user"
        return [
            {
                "id": 303,
                "cid": "bafy-housing-process-1",
                "claim_type": "housing_discrimination",
                "description": "HACC denial notice and review chronology",
                "parsed_text_preview": (
                    "On March 3, 2026, HACC sent Plaintiff a written denial notice signed by HACC hearing officer Maria Lopez. "
                    "On March 4, 2026, Plaintiff submitted a grievance request challenging the denial notice. "
                    "On March 8, 2026, HACC hearing officer Maria Lopez issued the review decision."
                ),
                "metadata": {"claim_types": ["housing_discrimination", "due_process_failure"]},
            }
        ]

    def get_evidence_facts(self, *, evidence_id):
        assert evidence_id == 303
        return [
            {
                "fact_id": "fact-303-1",
                "text": "On March 3, 2026, HACC sent Plaintiff a written denial notice signed by HACC hearing officer Maria Lopez.",
            },
            {
                "fact_id": "fact-303-2",
                "text": "On March 4, 2026, Plaintiff submitted a grievance request challenging the denial notice.",
            },
            {
                "fact_id": "fact-303-3",
                "text": "On March 8, 2026, HACC hearing officer Maria Lopez issued the review decision.",
            },
            {
                "fact_id": "fact-303-4",
                "text": "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
            },
            {
                "fact_id": "fact-303-5",
                "text": "Scheduling an Informal Review requires a written request for review.",
            },
        ]

    def summarize_claim_support(self, *, user_id):
        assert user_id == "housing-process-user"
        return {
            "claims": {
                "due_process_failure": {
                    "elements": [
                        {
                            "element_id": "notice-review-process",
                            "element_text": "Required notice and review process",
                            "links": [
                                {
                                    "support_kind": "authority",
                                    "citation": "24 C.F.R. 982.555",
                                    "title": "Informal review for denial of assistance",
                                    "relevance": "Requires written notice and an opportunity for informal review before a final adverse housing decision is enforced.",
                                }
                            ],
                        }
                    ]
                }
            }
        }


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


def test_derive_claim_types_includes_uploaded_evidence_claim_types_when_intake_is_sparse():
    builder = FormalComplaintDocumentBuilder(_EvidenceClaimTypeMediator())

    claim_types = builder._derive_claim_types(
        generated_complaint={},
        classification={},
        support_claims={},
        requirements={},
        user_id="evidence-claim-user",
    )

    assert "housing_discrimination" in claim_types
    assert "due_process_failure" in claim_types


def test_factual_allegations_exclude_internal_evidence_ranking_narration():
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())

    allegations = builder._build_factual_allegations(
        summary_of_facts=[
            "The strongest supporting material is 'test_hacc_evidence_loader.py'.",
            "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
        ],
        claims_for_relief=[
            {
                "claim_type": "housing_discrimination",
                "count_title": "Housing Discrimination",
                "supporting_facts": [
                    "The strongest supporting material is 'test_hacc_evidence_loader.py'.",
                    "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
                ],
            }
        ],
    )

    assert any("Notice to the Applicant requires prompt written notice" in item for item in allegations)
    assert all("strongest supporting material" not in item.lower() for item in allegations)


def test_factual_allegations_use_complaint_style_missing_detail_language():
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())

    allegations = builder._build_factual_allegations(
        summary_of_facts=[
            "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
            "HACC policy describes scheduling and procedures for informal review.",
        ],
        claims_for_relief=[],
    )

    assert any(
        ("exact date of HACC's hearing or review request remains to be confirmed" in item)
        or ("exact date of the Housing Authority's hearing or review request remains to be confirmed" in item)
        for item in allegations
    )
    assert any("exact dates of the notice, response, and final decision have not yet been confirmed" in item for item in allegations)
    assert any(
        ("does not yet identify by name the HACC official" in item)
        or ("does not yet identify by name the official at HACC" in item)
        or ("does not yet identify by name the official at the Housing Authority" in item)
        for item in allegations
    )
    assert any("occurred in close sequence" in item for item in allegations)
    assert all("the complaint should state" not in item.lower() for item in allegations)
    assert all("should be identified with exact dates" not in item.lower() for item in allegations)


def test_factual_allegations_synthesize_policy_violation_allegations_from_notice_and_review_text():
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())

    allegations = builder._build_factual_allegations(
        summary_of_facts=[
            "HACC policy describes scheduling and procedures for informal review.",
            "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
        ],
        claims_for_relief=[],
    )

    assert any(
        "Notice to the Applicant requires prompt written notice of a decision denying assistance." in item
        for item in allegations
    )
    assert any(
        "failed to provide the informal review, grievance, or appeal process" in item
        for item in allegations
    )
    assert not any(
        "without providing the prompt written notice required" in item
        for item in allegations
    )
    assert any(("the Housing Authority" in item) or ("HACC" in item) for item in allegations)


def test_factual_allegations_dedupe_raw_policy_restatement_when_violation_allegation_exists():
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())

    allegations = builder._build_factual_allegations(
        summary_of_facts=[
            "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
        ],
        claims_for_relief=[
            {
                "claim_type": "housing_discrimination",
                "count_title": "Housing Discrimination",
                "supporting_facts": [
                    "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
                ],
            }
        ],
    )

    assert any(
        "Notice to the Applicant requires prompt written notice of a decision denying assistance." in item
        for item in allegations
    )
    assert not any(
        item.startswith("As to Housing Discrimination, notice to the Applicant requires prompt written notice")
        for item in allegations
    )


def test_factual_allegations_use_case_specific_adverse_action_clause_when_available():
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())

    allegations = builder._build_factual_allegations(
        summary_of_facts=[
            "On March 3, 2026, HACC sent Plaintiff a written denial notice after Plaintiff requested a grievance hearing.",
            "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
            "Scheduling an Informal Review requires a written request for review.",
        ],
        claims_for_relief=[],
    )

    assert any(
        "Plaintiff further alleges that on March 3, 2026, HACC sent Plaintiff a written denial notice after Plaintiff requested a grievance hearing, without the notice and review protections described in the governing process."
        in item
        for item in allegations
    )


def test_factual_allegations_preserve_case_specific_bridge_when_claim_facts_are_prefixed():
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())

    allegations = builder._build_factual_allegations(
        summary_of_facts=[
            "On March 3, 2026, HACC sent Plaintiff a written denial notice after Plaintiff requested a grievance hearing.",
            "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
            "Scheduling an Informal Review requires a written request for review.",
        ],
        claims_for_relief=[
            {
                "claim_type": "housing_discrimination",
                "count_title": "Housing Discrimination",
                "supporting_facts": [
                    "On March 3, 2026, HACC sent Plaintiff a written denial notice after Plaintiff requested a grievance hearing.",
                ],
            }
        ],
    )

    assert any(
        "Plaintiff further alleges that on March 3, 2026, HACC sent Plaintiff a written denial notice after Plaintiff requested a grievance hearing, without the notice and review protections described in the governing process."
        in item
        for item in allegations
    )


def test_factual_allegations_suppress_missing_detail_fallbacks_when_evidence_has_dates_and_official():
    builder = FormalComplaintDocumentBuilder(_ExplodingMediator())

    allegations = builder._build_factual_allegations(
        summary_of_facts=[
            "On March 3, 2026, HACC sent Plaintiff a written denial notice signed by HACC hearing officer Maria Lopez.",
            "On March 4, 2026, Plaintiff submitted a grievance request challenging the denial notice.",
            "On March 8, 2026, HACC hearing officer Maria Lopez issued the review decision.",
            "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
            "Scheduling an Informal Review requires a written request for review.",
        ],
        claims_for_relief=[],
    )

    assert not any("hearing or review request remains to be confirmed" in item for item in allegations)
    assert not any("exact dates of the notice, response, and final decision have not yet been confirmed" in item for item in allegations)
    assert not any("does not yet identify by name the official" in item for item in allegations)
    assert any("Maria Lopez" in item for item in allegations)
    assert any(
        "The chronology shows that on March 3, 2026, HACC sent Plaintiff a written denial notice signed by HACC hearing officer Maria Lopez, on March 4, 2026, Plaintiff submitted a grievance request challenging the denial notice, and on March 8, 2026, HACC hearing officer Maria Lopez issued the review decision."
        in item
        for item in allegations
    )
    assert not any("occurred in close sequence" in item for item in allegations)
    assert not any(
        "Notice to the Applicant requires prompt written notice of a decision denying assistance." in item
        for item in allegations
    )


def test_build_draft_uses_claim_specific_titles_and_housing_process_relief():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    count_titles = [claim.get("count_title") for claim in draft["claims_for_relief"]]
    assert count_titles[0] == "Denial of Required Notice and Informal Review"
    assert "Housing Discrimination and Wrongful Denial of Assistance" in count_titles
    assert "Denial of Required Notice and Informal Review" in count_titles
    assert any(
        "rescind or stay the challenged denial or loss of housing assistance" in item
        for item in draft["requested_relief"]
    )
    assert any(
        "provide the informal review, grievance hearing, appeal, or other process required" in item
        for item in draft["requested_relief"]
    )
    by_type = {claim.get("claim_type"): claim for claim in draft["claims_for_relief"]}
    assert any(
        "denied, limited, or otherwise interfered with housing assistance" in item
        for item in by_type["housing_discrimination"]["legal_standards"]
    )
    assert any(
        "required to provide the written notice, review opportunity, hearing, grievance, appeal, or comparable process" in item
        for item in by_type["due_process_failure"]["legal_standards"]
    )
    assert any(
        "24 C.F.R. 982.555" in item
        for item in by_type["due_process_failure"]["legal_standards"]
    )


def test_factual_allegation_entries_store_real_identifier_lists():
    builder = FormalComplaintDocumentBuilder(_EvidenceFactMediator())

    summary_entries = builder._build_summary_fact_entries(
        user_id="evidence-user",
        generated_complaint={},
        classification={},
        state=builder.mediator.state,
    )
    allegation_entries = builder._build_factual_allegation_entries(
        summary_fact_entries=summary_entries,
        claims_for_relief=[],
    )

    assert allegation_entries
    for entry in allegation_entries:
        assert isinstance(entry.get("fact_ids"), list)
        assert isinstance(entry.get("source_artifact_ids"), list)
        assert isinstance(entry.get("claim_types"), list)
        assert all("generator object" not in str(value) for value in entry.get("fact_ids", []))


def test_synthesized_review_process_allegation_inherits_process_fact_ids():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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
    builder._attach_allegation_references(draft)

    review_paragraph = next(
        paragraph
        for paragraph in draft["factual_allegation_paragraphs"]
        if "failed to provide the informal review" in paragraph["text"]
    )
    assert review_paragraph["fact_ids"]
    assert "fact-303-2" in review_paragraph["fact_ids"]
    assert "fact-303-5" in review_paragraph["fact_ids"]


def test_chronology_allegation_inherits_full_dated_fact_chain():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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
    builder._attach_allegation_references(draft)

    chronology_paragraph = next(
        paragraph
        for paragraph in draft["factual_allegation_paragraphs"]
        if paragraph["text"].startswith("The chronology shows that ")
    )
    assert chronology_paragraph["fact_ids"]
    assert "fact-303-1" in chronology_paragraph["fact_ids"]
    assert "fact-303-2" in chronology_paragraph["fact_ids"]
    assert "fact-303-3" in chronology_paragraph["fact_ids"]
    assert chronology_paragraph["exhibit_label"] == "Exhibit A"
    assert chronology_paragraph["text"].endswith("(See Exhibit A).")


def test_factual_allegation_groups_prioritize_dated_adverse_action_chronology():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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
    builder._attach_allegation_references(draft)

    adverse_group = next(
        group
        for group in draft["factual_allegation_groups"]
        if group.get("title") == "Adverse Action and Retaliatory Conduct"
    )
    first_paragraph = adverse_group["paragraphs"][0]

    assert first_paragraph["text"].startswith("Plaintiff further alleges that on March 3, 2026")
    assert "fact-303-1" in first_paragraph["fact_ids"]


def test_grouped_factual_allegation_headings_name_primary_evidence_exhibit():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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
    builder._attach_allegation_references(draft)

    grouped_lines = builder._grouped_allegation_text_lines(draft)

    assert "ADVERSE ACTION AND RETALIATORY CONDUCT (Exhibit A)" in grouped_lines


def test_document_provenance_summary_tracks_exhibit_backed_counts():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    summary = draft["document_provenance_summary"]

    assert summary["summary_fact_exhibit_backed_count"] >= 1
    assert summary["factual_allegation_exhibit_backed_count"] >= 1
    assert summary["claim_supporting_fact_exhibit_backed_count"] >= 1


def test_due_process_claim_support_entries_inherit_process_fact_ids():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    due_process_claim = next(
        claim for claim in draft["claims_for_relief"] if claim.get("claim_type") == "due_process_failure"
    )
    process_entry = next(
        entry
        for entry in due_process_claim["supporting_fact_entries"]
        if "HACC policy required prompt written notice of a decision denying assistance" in entry["text"]
    )
    assert process_entry["fact_ids"]
    assert process_entry["fact_ids"] == ["fact-303-1", "fact-303-4", "fact-303-5"]


def test_due_process_claim_support_entries_prefer_evidence_exhibit_for_uploaded_facts():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    due_process_claim = next(
        claim for claim in draft["claims_for_relief"] if claim.get("claim_type") == "due_process_failure"
    )
    uploaded_entry = next(
        entry
        for entry in due_process_claim["supporting_fact_entries"]
        if "On March 3, 2026, HACC sent Plaintiff a written denial notice" in entry["text"]
    )
    merged_support_entry = next(
        entry
        for entry in due_process_claim["supporting_fact_entries"]
        if "HACC policy required prompt written notice of a decision denying assistance" in entry["text"]
    )

    assert uploaded_entry["exhibit_label"] == "Exhibit A"
    assert "(See Exhibit A)" in uploaded_entry["text"]
    assert merged_support_entry["exhibit_label"] == "See Exhibit A and Exhibit B"
    assert "(See Exhibit A and Exhibit B)" in merged_support_entry["text"]


def test_due_process_claim_support_entries_lead_with_dated_evidence_sequence():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    due_process_claim = next(
        claim for claim in draft["claims_for_relief"] if claim.get("claim_type") == "due_process_failure"
    )
    opening_texts = [entry["text"] for entry in due_process_claim["supporting_fact_entries"][:3]]

    assert "On March 3, 2026, HACC sent Plaintiff a written denial notice" in opening_texts[0]
    assert "On March 4, 2026, Plaintiff submitted a grievance request" in opening_texts[1]
    assert "On March 8, 2026, HACC hearing officer Maria Lopez issued the review decision" in opening_texts[2]


def test_due_process_claim_support_entries_prune_redundant_abstract_rows():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    due_process_claim = next(
        claim for claim in draft["claims_for_relief"] if claim.get("claim_type") == "due_process_failure"
    )
    texts = [entry["text"] for entry in due_process_claim["supporting_fact_entries"]]

    assert not any(text.startswith("Element supported: Required notice and review process") for text in texts)
    assert not any("Informal review for denial of assistance" in text for text in texts)
    assert any(
        "HACC policy required prompt written notice of a decision denying assistance and a written opportunity to request informal review"
        in text
        for text in texts
    )


def test_housing_claim_support_entries_prune_preview_style_duplicates():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    housing_claim = next(
        claim for claim in draft["claims_for_relief"] if claim.get("claim_type") == "housing_discrimination"
    )
    texts = [entry["text"] for entry in housing_claim["supporting_fact_entries"]]

    assert not any("HACC denial notice and review chronology" in text for text in texts)
    assert any("On March 3, 2026, HACC sent Plaintiff a written denial notice" in text for text in texts)
    assert any(
        "HACC wrongfully denied or maintained the denial of housing assistance without the written notice and informal review"
        in text
        for text in texts
    )
    assert not any("Notice to the Applicant requires prompt written notice" in text for text in texts)
    assert not any("Scheduling an Informal Review requires a written request for review" in text for text in texts)


def test_housing_claim_support_entry_inherits_uploaded_adverse_action_fact_ids():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    housing_claim = next(
        claim for claim in draft["claims_for_relief"] if claim.get("claim_type") == "housing_discrimination"
    )
    merged_entry = next(
        entry
        for entry in housing_claim["supporting_fact_entries"]
        if "HACC wrongfully denied or maintained the denial of housing assistance without the written notice and informal review" in entry["text"]
    )

    assert "fact-303-1" in merged_entry["fact_ids"]
    assert "fact-303-4" in merged_entry["fact_ids"]
    assert "fact-303-5" in merged_entry["fact_ids"]


def test_rendered_draft_uses_compact_count_paragraphs():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    draft_text = draft["draft_text"]
    claims_section = draft_text[draft_text.index("CLAIMS FOR RELIEF"):draft_text.index("REQUESTED RELIEF")]
    assert "Legal Standard:" not in draft_text
    assert "Claim-Specific Support:" not in draft_text
    assert "Before enforcing a final adverse housing decision, Defendant was required to" in claims_section
    assert "Defendant denied, limited, or otherwise interfered with Plaintiff's housing assistance or related housing rights" in claims_section
    assert "Defendant enforced or maintained the denial of housing assistance without the notice, review, and fair treatment required" in claims_section
    assert "That unlawful housing decision caused the resulting denial of housing opportunity" in claims_section
    assert "That failure of notice and process caused the deprivation of housing benefits and review rights" in claims_section
    assert "Plaintiff alleges that Plaintiff alleges that" not in claims_section
    assert "Defendant failed to provide the required written notice and meaningful review process" in claims_section
    assert " and the requested relief addresses " not in claims_section
    assert "The requested relief addresses" not in claims_section
    assert "The pleaded facts further show that on March 3, 2026, HACC sent Plaintiff a written denial notice" in claims_section
    assert "Federal housing regulations, including 24 C.F.R. 982.555, required written notice and an opportunity for informal review" in claims_section
    assert "hACC" not in claims_section


def test_rendered_claim_support_prefers_fact_backed_uploaded_evidence_lines():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    due_process_claim = next(
        claim for claim in draft["claims_for_relief"] if claim.get("claim_type") == "due_process_failure"
    )
    rendered_lines = builder._render_claim_supporting_facts(due_process_claim)

    assert "On March 3, 2026, HACC sent Plaintiff a written denial notice signed by HACC hearing officer Maria Lopez (See Exhibit A)." in rendered_lines[0]
    assert "On March 4, 2026, Plaintiff submitted a grievance request challenging the denial notice (See Exhibit A)." in rendered_lines[1]
    assert "On March 8, 2026, HACC hearing officer Maria Lopez issued the review decision (See Exhibit A)." in rendered_lines[2]


def test_count_incorporation_clause_names_primary_evidence_exhibit():
    builder = FormalComplaintDocumentBuilder(_HousingProcessMediator())

    draft = builder.build_draft(
        user_id="housing-process-user",
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
        defendant_names=["Housing Authority of the County of Contra Costa"],
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

    due_process_claim = next(
        claim for claim in draft["claims_for_relief"] if claim.get("claim_type") == "due_process_failure"
    )
    rendered_lines = builder._build_claim_render_lines(due_process_claim)

    assert "Exhibit A (HACC denial notice and review chronology) and Exhibit B (Informal review for denial of assistance)" in rendered_lines[0]
