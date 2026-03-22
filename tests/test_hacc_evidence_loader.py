import inspect
import sys
from pathlib import Path

import adversarial_harness.hacc_evidence as hacc_evidence_module


def test_load_hacc_engine_loads_engine_module_from_repo_root(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    engine_dir = repo_root / "hacc_research"
    engine_dir.mkdir(parents=True)
    (engine_dir / "engine.py").write_text(
        "class HACCResearchEngine:\n    SOURCE = 'file-loader'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: repo_root)
    monkeypatch.delitem(sys.modules, "hacc_research.engine", raising=False)

    engine_cls = hacc_evidence_module._load_hacc_engine()

    assert engine_cls.SOURCE == "file-loader"
    assert str(repo_root) not in sys.path


def test_load_hacc_engine_source_uses_file_based_loader():
    source = inspect.getsource(hacc_evidence_module._load_hacc_engine)

    assert "spec_from_file_location" in source
    assert "module_from_spec" in source
    assert 'import_module("hacc_research")' not in source


def test_build_hacc_evidence_seeds_falls_back_to_repository_grounding(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    scripts_dir = tmp_path / "scripts"
    docs_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)
    (docs_dir / "HACC_INTEGRATION.md").write_text(
        "The HACC grievance hearing process requires written notice, hearing requests, and appeal rights.",
        encoding="utf-8",
    )
    (scripts_dir / "synthesize_hacc_complaint.py").write_text(
        "reasonable accommodation and adverse action notice guidance",
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: Path(tmp_path))
    monkeypatch.setattr(
        hacc_evidence_module,
        "_load_hacc_engine",
        lambda: (_ for _ in ()).throw(ModuleNotFoundError("missing hacc engine")),
    )

    seeds = hacc_evidence_module.build_hacc_evidence_seeds(
        count=1,
        query_specs=[
            {
                "query": "grievance hearing appeal written notice",
                "type": "housing_discrimination",
                "category": "housing",
                "description": "Repository-grounded HACC complaint",
                "anchor_terms": ["grievance hearing", "appeal rights", "written notice"],
            }
        ],
    )

    assert len(seeds) == 1
    key_facts = dict(seeds[0].get("key_facts") or {})
    search_summary = dict(key_facts.get("search_summary") or {})
    synthetic_prompts = dict(key_facts.get("synthetic_prompts") or {})
    assert search_summary["effective_search_mode"] == "repository_fallback"
    assert "Upload the strongest case-specific files first" in synthetic_prompts["evidence_upload_prompt"]
    assert "treated as exhibits" in synthetic_prompts["evidence_upload_prompt"]
    assert key_facts["repository_evidence_candidates"]
    assert key_facts["mediator_evidence_packets"]


def test_merge_synthetic_prompts_adds_upload_and_document_workflow_guidance():
    prompts = hacc_evidence_module._merge_synthetic_prompts(
        complaint_type="housing_discrimination",
        description="Retaliation complaint grounded in HACC process documents",
        query="retaliation grievance hearing appeal due process",
        evidence_summary="Administrative plan language discusses grievances and appeals.",
        anchor_sections=["grievance_hearing", "appeal_rights"],
        anchor_passages=[
            {
                "title": "ADMINISTRATIVE PLAN",
                "snippet": "HACC policy requires written notice and an opportunity for an informal hearing.",
                "section_labels": ["grievance_hearing", "appeal_rights"],
            }
        ],
        repository_candidates=[
            {
                "title": "ADMINISTRATIVE PLAN",
                "relative_path": "hacc_website/admin-plan.txt",
                "snippet": "Written notice is required before an informal hearing.",
            }
        ],
        existing_prompts={},
    )

    assert prompts["complaint_chatbot_prompt"]
    assert prompts["mediator_evidence_review_prompt"]
    assert prompts["document_generation_prompt"]
    assert prompts["workflow_phase_priorities"] == [
        "intake_questioning",
        "evidence_upload",
        "graph_analysis",
        "document_generation",
    ]
    assert "exhibit-ready uploads" in prompts["intake_questionnaire_prompt"]
    assert any("Please upload ADMINISTRATIVE PLAN" in item for item in prompts["evidence_upload_questions"])
    assert any("should become exhibits" in item for item in prompts["mediator_questions"])
    assert "timeline_anchors" in prompts["extraction_targets"]
    assert "claim_support_mapping" in prompts["extraction_targets"]


def test_merge_synthetic_prompts_adds_exhibit_ready_intake_language_for_adverse_action_grounding():
    prompts = hacc_evidence_module._merge_synthetic_prompts(
        complaint_type="housing_discrimination",
        description="Adverse action complaint grounded in HACC process documents",
        query="denial notice grievance hearing review decision adverse action",
        evidence_summary="Administrative plan language discusses denial notices and reviews.",
        anchor_sections=["adverse_action", "grievance_hearing", "appeal_rights"],
        anchor_passages=[
            {
                "title": "ADMINISTRATIVE PLAN",
                "snippet": "HACC policy requires written notice and an opportunity for an informal hearing.",
                "section_labels": ["grievance_hearing", "appeal_rights", "adverse_action"],
            }
        ],
        repository_candidates=[
            {
                "title": "ADMINISTRATIVE PLAN",
                "relative_path": "hacc_website/admin-plan.txt",
                "snippet": "Written notice is required before an informal hearing.",
            }
        ],
        existing_prompts={},
    )

    assert any("should be treated as exhibits" in item for item in prompts["intake_questions"])
    assert "label or subject line" in prompts["evidence_upload_prompt"]


def test_merge_synthetic_prompts_uses_notice_review_examples_for_due_process_theory():
    prompts = hacc_evidence_module._merge_synthetic_prompts(
        complaint_type="housing_discrimination",
        description="Retaliation and due-process complaint grounded in HACC process documents",
        query="retaliation grievance hearing appeal due process notice of adverse action",
        evidence_summary="Administrative plan language discusses denial notices and reviews.",
        anchor_sections=["grievance_hearing", "appeal_rights", "adverse_action"],
        anchor_passages=[],
        repository_candidates=[],
        theory_labels=["retaliation", "due_process_failure"],
        protected_bases=[],
        anchor_terms=["grievance hearing", "review decision", "notice of adverse action"],
        existing_prompts={},
    )

    joined_questions = " ".join(prompts["intake_questions"])
    assert "denial notice" in prompts["evidence_upload_prompt"]
    assert "hearing or review request" in prompts["evidence_upload_prompt"]
    assert "review decision" in joined_questions


def test_merge_synthetic_prompts_uses_accommodation_examples_for_disability_theory():
    prompts = hacc_evidence_module._merge_synthetic_prompts(
        complaint_type="housing_discrimination",
        description="Accommodation complaint grounded in HACC process documents",
        query="reasonable accommodation disability denial informal hearing housing authority",
        evidence_summary="Administrative plan language discusses accommodation requests and decisions.",
        anchor_sections=["reasonable_accommodation", "appeal_rights"],
        anchor_passages=[],
        repository_candidates=[],
        theory_labels=["reasonable_accommodation", "disability_discrimination"],
        protected_bases=["disability"],
        anchor_terms=["reasonable accommodation", "disability", "right to appeal"],
        existing_prompts={},
    )

    joined_questions = " ".join(prompts["intake_questions"])
    assert "accommodation request" in prompts["evidence_upload_prompt"]
    assert "medical or disability-support record" in prompts["evidence_upload_prompt"]
    assert "accommodation request" in joined_questions


def test_merge_synthetic_prompts_adds_non_accommodation_guardrail_when_seed_is_not_accommodation():
    prompts = hacc_evidence_module._merge_synthetic_prompts(
        complaint_type="housing_discrimination",
        description="Retaliation complaint grounded in HACC process documents",
        query="retaliation grievance hearing appeal due process",
        evidence_summary="Administrative plan language discusses grievances, hearings, and appeals.",
        anchor_sections=["grievance_hearing", "appeal_rights"],
        anchor_passages=[
            {
                "title": "ADMINISTRATIVE PLAN",
                "snippet": "Families may request a grievance hearing and receive written notice of appeal rights.",
                "section_labels": ["grievance_hearing", "appeal_rights"],
            }
        ],
        repository_candidates=[],
        existing_prompts={},
    )

    assert "Do not infer a reasonable-accommodation claim" in prompts["complaint_chatbot_prompt"]
    assert "Do not treat accommodation language in policy excerpts as a live claim theory" in prompts["mediator_evidence_review_prompt"]
    assert "avoid adding accommodation allegations unless uploaded evidence supports them" in prompts["document_generation_prompt"]


def test_merge_synthetic_prompts_normalizes_engine_prompt_aliases():
    prompts = hacc_evidence_module._merge_synthetic_prompts(
        complaint_type="housing_discrimination",
        description="Retaliation complaint grounded in HACC process documents",
        query="retaliation grievance hearing appeal due process",
        evidence_summary="Administrative plan language discusses grievances and appeals.",
        anchor_sections=["grievance_hearing", "appeal_rights"],
        anchor_passages=[],
        repository_candidates=[],
        existing_prompts={
            "production_upload_prompt": "Upload the hearing request and denial notice first.",
            "mediator_evaluation_prompt": "Evaluate each uploaded record for chronology and legal support.",
            "evidence_upload_prompts": [
                {"text": "Upload the grievance notice and describe what it proves."}
            ],
        },
    )

    assert prompts["evidence_upload_prompt"] == "Upload the hearing request and denial notice first."
    assert prompts["mediator_evidence_review_prompt"] == "Evaluate each uploaded record for chronology and legal support."


def test_build_seed_packet_text_uses_snippet_for_repository_grounding():
    candidate = {
        "title": "ADMINISTRATIVE PLAN",
        "source_type": "repository_grounding",
        "snippet": (
            "Notice to the Applicant [24 CFR 982.554(a)] HACC must give an applicant prompt notice of a decision denying assistance. "
            "Scheduling an Informal Review HACC Policy A request for an informal review must be made in writing."
        ),
        "metadata": {"grounding_mode": "repository_fallback"},
    }

    document_text = hacc_evidence_module._build_seed_packet_text(
        candidate,
        "import argparse\n\n" + ("x = 1\n" * 400),
    )

    assert document_text.startswith("Notice to the Applicant")
    assert "import argparse" not in document_text


def test_build_seed_packet_text_combines_multiple_anchor_excerpts_for_repository_grounding(tmp_path):
    source = tmp_path / "policy.txt"
    source.write_text(
        (
            "Notice to the Applicant requires prompt written notice of a decision denying assistance. "
            "Scheduling an Informal Review requires a written request for review."
        ),
        encoding="utf-8",
    )
    candidate = {
        "title": "ADMINISTRATIVE PLAN",
        "source_type": "repository_grounding",
        "source_path": str(source),
        "snippet": "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
        "metadata": {
            "grounding_mode": "repository_fallback",
            "anchor_terms": ["Notice to the Applicant", "Scheduling an Informal Review"],
        },
    }

    document_text = hacc_evidence_module._build_seed_packet_text(
        candidate,
        source.read_text(encoding="utf-8"),
    )

    assert "Notice to the Applicant requires prompt written notice" in document_text
    assert "Scheduling an Informal Review requires a written request for review." in document_text


def test_repository_grounding_scoring_prefers_curated_hacc_excerpt_sources(tmp_path, monkeypatch):
    synth = tmp_path / "scripts" / "synthesize_hacc_complaint.py"
    synth.parent.mkdir(parents=True)
    synth.write_text(
        "Scheduling an Informal Review HACC policy says a request for an informal review must be made in writing.",
        encoding="utf-8",
    )
    docs = tmp_path / "docs" / "HACC_INTEGRATION_ARCHITECTURE.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(
        "Scheduling an Informal Review appears in the HACC workflow architecture discussion.",
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repository_grounding_paths", lambda: [docs, synth])

    hits = hacc_evidence_module._build_repository_grounding_hits(
        query="Scheduling an Informal Review",
        complaint_type="housing_discrimination",
        description="Repository-grounded HACC complaint",
        anchor_terms=["Scheduling an Informal Review", "written notice"],
        theory_labels=["due_process_failure"],
        protected_bases=None,
        top_k=2,
    )

    assert hits[0]["source_path"] == str(synth)


def test_repository_grounding_scoring_demotes_operational_regression_docs(tmp_path, monkeypatch):
    synth = tmp_path / "scripts" / "synthesize_hacc_complaint.py"
    synth.parent.mkdir(parents=True)
    synth.write_text(
        "HACC policy describes scheduling and procedures for informal review. Notice to the Applicant requires prompt written notice.",
        encoding="utf-8",
    )
    regression = tmp_path / "docs" / "HACC_GROUNDING_REGRESSION.md"
    regression.parent.mkdir(parents=True, exist_ok=True)
    regression.write_text(
        "HACC Grounding Regression. VS Code task. Related smoke-matrix task. Guarded smoke-matrix task.",
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repository_grounding_paths", lambda: [regression, synth])
    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: tmp_path)

    hits = hacc_evidence_module._build_repository_grounding_hits(
        query="written notice informal review",
        complaint_type="housing_discrimination",
        description="Repository-grounded HACC complaint",
        anchor_terms=["Notice to the Applicant", "Scheduling an Informal Review"],
        theory_labels=["due_process_failure"],
        protected_bases=None,
        top_k=2,
    )

    assert hits[0]["source_path"] == str(synth)


def test_build_hacc_repository_grounded_seed_produces_curated_packets_without_engine(monkeypatch):
    candidate = {
        "title": "ADMINISTRATIVE PLAN",
        "relative_path": "scripts/synthesize_hacc_complaint.py",
        "source_path": "/tmp/admin-plan.txt",
        "snippet": (
            "Notice to the Applicant [24 CFR 982.554(a)] HACC must give an applicant prompt notice of a decision denying assistance. "
            "Scheduling an Informal Review HACC Policy A request for an informal review must be made in writing."
        ),
        "score": 9.5,
        "source_type": "repository_grounding",
        "metadata": {"grounding_mode": "repository_fallback"},
    }

    monkeypatch.setattr(
        hacc_evidence_module,
        "_build_repository_grounding_bundle",
        lambda **kwargs: {
            "search_summary": {
                "requested_search_mode": "repository_fallback",
                "effective_search_mode": "repository_fallback",
            },
            "upload_candidates": [candidate],
            "synthetic_prompts": {},
            "mediator_evidence_packets": [
                {
                    "document_text": candidate["snippet"],
                    "document_label": candidate["title"],
                    "source_path": candidate["source_path"],
                    "filename": "admin-plan.txt",
                    "mime_type": "text/plain",
                    "metadata": {"grounding_mode": "repository_fallback"},
                }
            ],
        },
    )

    seed = hacc_evidence_module.build_hacc_repository_grounded_seed(
        query="notice to the applicant informal review",
        complaint_type="housing_discrimination",
        category="housing",
        description="Repository-grounded HACC complaint",
        anchor_terms=["Notice to the Applicant", "Scheduling an Informal Review"],
        theory_labels=["due_process_failure"],
        top_k=1,
    )

    assert seed is not None
    assert seed["key_facts"]["search_summary"]["effective_search_mode"] == "repository_fallback"
    assert seed["key_facts"]["repository_evidence_candidates"][0]["title"] == "ADMINISTRATIVE PLAN"
    assert seed["key_facts"]["mediator_evidence_packets"][0]["document_text"].startswith("Notice to the Applicant")


def test_repository_grounding_refines_python_source_snippet_to_policy_literal(tmp_path, monkeypatch):
    source = tmp_path / "synthesize_hacc_complaint.py"
    source.write_text(
        """
import argparse

PATTERNS = [
    (
        r"Scheduling an Informal Review",
        "HACC policy describes scheduling and procedures for informal review.",
    ),
    (
        r"Notice to the Applicant",
        "HACC must give an applicant prompt notice of a decision denying assistance.",
    ),
]
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repository_grounding_paths", lambda: [source])
    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: tmp_path)

    hits = hacc_evidence_module._build_repository_grounding_hits(
        query="Scheduling an Informal Review",
        complaint_type="housing_discrimination",
        description="Repository-grounded HACC complaint",
        anchor_terms=["Scheduling an Informal Review", "Notice to the Applicant"],
        theory_labels=["due_process_failure"],
        protected_bases=None,
        top_k=1,
    )

    assert len(hits) == 1
    assert hits[0]["snippet"] == "HACC policy describes scheduling and procedures for informal review."


def test_repository_grounding_refines_python_source_snippet_away_from_meta_literal(tmp_path, monkeypatch):
    source = tmp_path / "synthesize_hacc_complaint.py"
    source.write_text(
        '''
META = "These policy excerpts frame the notice theory and summarize what HACC policy appears to require for written notice or adverse-action disclosures."
POLICY = "Notice to the Applicant requires prompt written notice of a decision denying assistance."
''',
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repository_grounding_paths", lambda: [source])
    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: tmp_path)

    hits = hacc_evidence_module._build_repository_grounding_hits(
        query="written notice denial assistance",
        complaint_type="housing_discrimination",
        description="Repository-grounded HACC complaint",
        anchor_terms=["Notice to the Applicant", "written notice", "denial assistance"],
        theory_labels=["due_process_failure"],
        protected_bases=None,
        top_k=1,
    )

    assert len(hits) == 1
    assert hits[0]["snippet"] == "Notice to the Applicant requires prompt written notice of a decision denying assistance."


def test_build_hacc_evidence_seed_summary_uses_policy_snippet_not_meta_grounding_text():
    payload = {
        "results": [
            {
                "title": "synthesize_hacc_complaint.py",
                "source_path": "/tmp/synthesize_hacc_complaint.py",
                "snippet": "These policy excerpts frame the notice theory and summarize what HACC policy appears to require for written notice.",
                "metadata": {"grounding_mode": "repository_fallback"},
            }
        ],
        "search_summary": {
            "requested_search_mode": "repository_fallback",
            "effective_search_mode": "repository_fallback",
        },
    }
    grounding_bundle = {
        "upload_candidates": [
            {
                "title": "ADMINISTRATIVE PLAN",
                "relative_path": "scripts/synthesize_hacc_complaint.py",
                "source_path": "/tmp/admin-plan.txt",
                "snippet": "Notice to the Applicant requires prompt written notice of a decision denying assistance.",
                "score": 9.5,
                "source_type": "repository_grounding",
                "metadata": {"grounding_mode": "repository_fallback"},
            }
        ],
        "mediator_evidence_packets": [],
        "synthetic_prompts": {},
        "search_summary": payload["search_summary"],
    }

    seed = hacc_evidence_module.build_hacc_evidence_seed(
        payload,
        query="notice to the applicant written notice",
        complaint_type="housing_discrimination",
        category="housing",
        description="Repository-grounded HACC complaint",
        anchor_terms=["Notice to the Applicant", "written notice"],
        grounding_bundle=grounding_bundle,
    )

    assert seed is not None
    assert "These policy excerpts frame" not in seed["summary"]
    assert "Notice to the Applicant requires prompt written notice" in seed["summary"]


def test_build_hacc_evidence_seed_summary_skips_question_prompt_text():
    payload = {
        "results": [
            {
                "title": "synthesize_hacc_complaint.py",
                "source_path": "/tmp/synthesize_hacc_complaint.py",
                "snippet": "What written notice, informal review, grievance hearing, or appeal rights were provided, requested, denied, or ignored?",
                "metadata": {"grounding_mode": "repository_fallback"},
            }
        ],
        "search_summary": {
            "requested_search_mode": "repository_fallback",
            "effective_search_mode": "repository_fallback",
        },
    }
    grounding_bundle = {
        "upload_candidates": [
            {
                "title": "ADMINISTRATIVE PLAN",
                "relative_path": "tests/test_hacc_evidence_loader.py",
                "source_path": "/tmp/admin-plan.txt",
                "snippet": "Notice to the Applicant requires prompt written notice before denying assistance.",
                "score": 8.5,
                "source_type": "repository_grounding",
                "metadata": {"grounding_mode": "repository_fallback"},
            }
        ],
        "mediator_evidence_packets": [],
        "synthetic_prompts": {},
        "search_summary": payload["search_summary"],
    }

    seed = hacc_evidence_module.build_hacc_evidence_seed(
        payload,
        query="notice to the applicant written notice",
        complaint_type="housing_discrimination",
        category="housing",
        description="Repository-grounded HACC complaint",
        anchor_terms=["Notice to the Applicant", "written notice"],
        grounding_bundle=grounding_bundle,
    )

    assert seed is not None
    assert "What written notice" not in seed["summary"]
    assert "Notice to the Applicant requires prompt written notice before denying assistance." in seed["summary"]


def test_repository_grounding_prefers_direct_policy_excerpt_over_analytical_summary(tmp_path, monkeypatch):
    source = tmp_path / "synthesize_hacc_complaint.py"
    source.write_text(
        '''
SUMMARY = "The available policy language suggests the complainant should have received an informal review or hearing, written notice, and a review decision, but the intake narrative describes those protections as missing or unclear"
POLICY = "Notice to the Applicant requires prompt written notice of a decision denying assistance. Scheduling an Informal Review requires a written request."
''',
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repository_grounding_paths", lambda: [source])
    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: tmp_path)

    hits = hacc_evidence_module._build_repository_grounding_hits(
        query="written notice informal review denial assistance",
        complaint_type="housing_discrimination",
        description="Repository-grounded HACC complaint",
        anchor_terms=["Notice to the Applicant", "Scheduling an Informal Review", "written notice"],
        theory_labels=["due_process_failure"],
        protected_bases=None,
        top_k=1,
    )

    assert len(hits) == 1
    assert hits[0]["snippet"].startswith("Notice to the Applicant requires prompt written notice")


def test_repository_grounding_demotes_question_style_source_even_with_curated_path_boost(tmp_path, monkeypatch):
    synth = tmp_path / "scripts" / "synthesize_hacc_complaint.py"
    synth.parent.mkdir(parents=True, exist_ok=True)
    synth.write_text(
        '''
QUESTION = "What written notice, informal review, grievance hearing, or appeal rights were provided, requested, denied, or ignored?"
''',
        encoding="utf-8",
    )
    policy = tmp_path / "tests" / "test_hacc_evidence_loader.py"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        '''
POLICY = "Notice to the Applicant requires prompt written notice of a decision denying assistance."
''',
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repository_grounding_paths", lambda: [synth, policy])
    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: tmp_path)

    hits = hacc_evidence_module._build_repository_grounding_hits(
        query="written notice denial assistance informal review",
        complaint_type="housing_discrimination",
        description="Repository-grounded HACC complaint",
        anchor_terms=["written notice", "informal review", "denial assistance"],
        theory_labels=["due_process_failure"],
        protected_bases=None,
        top_k=2,
    )

    assert len(hits) == 2
    assert hits[0]["source_path"] == str(policy)
    assert hits[0]["snippet"] == "Notice to the Applicant requires prompt written notice of a decision denying assistance."


def test_build_repository_grounding_bundle_excludes_question_style_upload_candidates(tmp_path, monkeypatch):
    synth = tmp_path / "scripts" / "synthesize_hacc_complaint.py"
    synth.parent.mkdir(parents=True, exist_ok=True)
    synth.write_text(
        '''
QUESTION = "What written notice, informal review, grievance hearing, or appeal rights were provided, requested, denied, or ignored?"
''',
        encoding="utf-8",
    )
    policy = tmp_path / "tests" / "test_hacc_evidence_loader.py"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        '''
POLICY = "Notice to the Applicant requires prompt written notice of a decision denying assistance."
''',
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repository_grounding_paths", lambda: [synth, policy])
    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: tmp_path)

    bundle = hacc_evidence_module._build_repository_grounding_bundle(
        query="written notice denial assistance informal review",
        complaint_type="housing_discrimination",
        description="Repository-grounded HACC complaint",
        category="housing",
        anchor_terms=["written notice", "informal review", "denial assistance"],
        theory_labels=["due_process_failure"],
        protected_bases=None,
        authority_hints=None,
        top_k=2,
    )

    titles = [item["title"] for item in bundle["upload_candidates"]]

    assert titles == ["test_hacc_evidence_loader.py"]
