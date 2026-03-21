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
    assert any("Please upload ADMINISTRATIVE PLAN" in item for item in prompts["evidence_upload_questions"])
    assert "timeline_anchors" in prompts["extraction_targets"]
    assert "claim_support_mapping" in prompts["extraction_targets"]


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
