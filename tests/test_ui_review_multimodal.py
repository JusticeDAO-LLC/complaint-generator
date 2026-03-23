from __future__ import annotations

from pathlib import Path

import pytest

from applications import ui_review as ui_review_module


pytestmark = [pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_create_ui_review_report_prefers_multimodal_router(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    artifact_metadata = [
        {
            "artifact_type": "complaint_export",
            "claim_type": "retaliation",
            "draft_strategy": "llm_router",
            "filing_shape_score": 83,
            "markdown_filename": "complaint.md",
            "pdf_filename": "complaint.pdf",
            "ui_suggestions_excerpt": "Add a clearer export warning when support gaps remain.",
        }
    ]

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "ComplaintMcpClient" in prompt
            assert "Complaint export artifacts" in prompt
            assert "Add a clearer export warning when support gaps remain." in prompt
            assert image_paths == [screenshot]
            assert system_prompt
            return (
                '{"summary":"Use calmer next-step guidance.",'
                '"issues":[{"severity":"high","surface":"/workspace","problem":"Too much cognitive load",'
                '"user_impact":"Complainants may freeze","recommended_fix":"Promote one next action"}],'
                '"recommended_changes":[{"title":"Clarify primary path","implementation_notes":"Use a single task card",'
                '"shared_code_path":"templates/workspace.html","sdk_considerations":"Keep bootstrapWorkspace visible"}],'
                '"workflow_gaps":["No clear linear handoff"],'
                '"playwright_followups":["Capture the workspace after sign-in"]}'
            )

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)], artifact_metadata=artifact_metadata)

    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["review"]["summary"] == "Use calmer next-step guidance."
    assert report["complaint_output_feedback"]["export_artifact_count"] == 1
    assert report["complaint_output_feedback"]["claim_types"] == ["retaliation"]
    assert report["complaint_output_feedback"]["draft_strategies"] == ["llm_router"]
    assert report["complaint_output_feedback"]["filing_shape_scores"] == [83]
    assert report["complaint_output_feedback"]["ui_suggestions"] == ["Add a clearer export warning when support gaps remain."]


def test_create_ui_review_report_falls_back_to_text_router(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")

    class FailingMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise RuntimeError("vision offline")

    class FakeTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt):
            assert "Screenshot artifacts" in prompt
            return '{"summary":"Fallback review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)])

    assert report["backend"]["strategy"] == "llm_router"
    assert report["backend"]["fallback_from"] == "multimodal_router"
    assert report["review"]["summary"] == "Fallback review."


def test_run_ui_review_workflow_loads_complaint_export_artifacts_from_screenshot_dir(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    (tmp_path / "workspace-export-artifacts.json").write_text(
        (
            '{'
            '"artifact_type":"complaint_export",'
            '"claim_type":"retaliation",'
            '"draft_strategy":"template",'
            '"filing_shape_score":61,'
            '"markdown_filename":"complaint.md",'
            '"pdf_filename":"complaint.pdf",'
            '"ui_suggestions_excerpt":"Add clearer draft-readiness warnings before download."'
            '}'
        )
    )

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Complaint export artifacts" in prompt
            assert "Add clearer draft-readiness warnings before download." in prompt
            return '{"summary":"Workflow review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    report = ui_review_module.run_ui_review_workflow(str(tmp_path))

    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["complaint_output_feedback"]["export_artifact_count"] == 1
    assert report["complaint_output_feedback"]["claim_types"] == ["retaliation"]
    assert report["complaint_output_feedback"]["draft_strategies"] == ["template"]
    assert report["complaint_output_feedback"]["filing_shape_scores"] == [61]
    assert report["complaint_output_feedback"]["markdown_filenames"] == ["complaint.md"]
    assert report["complaint_output_feedback"]["ui_suggestions"] == [
        "Add clearer draft-readiness warnings before download."
    ]


def test_build_complaint_output_review_prompt_includes_claim_type_context():
    prompt = ui_review_module.build_complaint_output_review_prompt(
        "# Complaint\n\nCOMPLAINT FOR HOUSING DISCRIMINATION",
        claim_type="Housing Discrimination",
        claim_guidance="Emphasize housing rights, discriminatory denial, and housing-related harm.",
        synopsis="Jordan Example alleges that housing rights were denied after a protected accommodation request.",
        notes="Use this to diagnose claim-shape drift.",
    )

    assert "Selected claim type:" in prompt
    assert "Housing Discrimination" in prompt
    assert "Claim-type filing guidance:" in prompt
    assert "Shared case synopsis:" in prompt
    assert '"claim_type_alignment_score": 0' in prompt
    assert '"missing_formal_sections": [' in prompt
    assert '"ui_priority_repairs": [' in prompt
    assert '"critic_gate": {' in prompt


def test_review_complaint_output_with_llm_router_generates_filing_shape_feedback(monkeypatch):
    class FakeTextBackend:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] == ui_review_module.DEFAULT_COMPLAINT_OUTPUT_REVIEW_TIMEOUT_S
            assert kwargs["allow_local_fallback"] is False
            assert kwargs["retry_max_attempts"] == 1
            self.id = kwargs.get("id", "complaint-output-review")
            self.provider = kwargs.get("provider", "fake")
            self.model = kwargs.get("model", "fake-model")

        def __call__(self, prompt):
            assert "formal legal complaint" in prompt
            assert "PRAYER FOR RELIEF" in prompt
            assert "Selected claim type:" in prompt
            return (
                '{"summary":"The complaint is closer to a filing than a memo, but still needs stronger venue and exhibit posture.",'
                '"filing_shape_score":82,'
                '"claim_type_alignment_score":91,'
                '"strengths":["Caption is present","Prayer for relief is present"],'
                '"missing_formal_sections":["signature_block"],'
                '"issues":[{"severity":"medium","finding":"Exhibit grounding is thin","complaint_impact":"The filing reads under-supported","ui_implication":"Evidence and draft surfaces are not tying exhibits into the pleading clearly enough"}],'
                '"ui_suggestions":[{"title":"Expose exhibit references in the draft builder","target_surface":"evidence,draft","recommendation":"Show saved exhibits beside the pleading sections they support","why_it_matters":"The final complaint will read more like a supported court filing"}],'
                '"ui_priority_repairs":[{"priority":"high","target_surface":"draft","repair":"Keep filing posture warnings visible before export","filing_benefit":"Stops weak complaints from looking filing-ready too early"}],'
                '"actor_risk_summary":"The actor can reach export without realizing the signature posture is still too thin.",'
                '"critic_gate":{"verdict":"warning","blocking_reason":"Signature posture is still weak","required_repairs":["Preserve signature guidance in the draft view"]}}'
            )

    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.review_complaint_output_with_llm_router(
        "IN THE UNITED STATES DISTRICT COURT\n\nPRAYER FOR RELIEF\nPlaintiff requests relief.",
        claim_type="Retaliation",
        claim_guidance="Emphasize protected activity, causation, and adverse action.",
        synopsis="Jordan Example alleges retaliation after reporting discrimination to HR.",
    )

    assert report["backend"]["strategy"] == "llm_router"
    assert report["review"]["filing_shape_score"] == 82
    assert report["review"]["claim_type_alignment_score"] == 91
    assert report["review"]["missing_formal_sections"] == ["signature_block"]
    assert report["review"]["issues"][0]["finding"] == "Exhibit grounding is thin"
    assert report["review"]["ui_suggestions"][0]["target_surface"] == "evidence,draft"
    assert report["review"]["ui_priority_repairs"][0]["priority"] == "high"
    assert report["review"]["actor_risk_summary"].startswith("The actor can reach export")
    assert report["review"]["critic_gate"]["verdict"] == "warning"


def test_review_complaint_export_artifacts_aggregates_router_feedback(monkeypatch):
    artifact_metadata = [
        {
            "artifact_type": "complaint_export",
            "claim_type": "retaliation",
            "draft_strategy": "llm_router",
            "markdown_filename": "complaint.md",
            "pdf_filename": "complaint.pdf",
            "markdown_excerpt": "IN THE UNITED STATES DISTRICT COURT\n\nCOMPLAINT FOR RETALIATION\n\nPRAYER FOR RELIEF",
        }
    ]

    def fake_review(markdown_text, **kwargs):
        assert "COMPLAINT FOR RETALIATION" in markdown_text
        assert kwargs["claim_type"] == "retaliation"
        return {
            "backend": {"strategy": "llm_router"},
            "review": {
                "summary": "Looks closer to a filing.",
                "filing_shape_score": 88,
                "claim_type_alignment_score": 93,
                "missing_formal_sections": ["signature_block"],
                "issues": [{"finding": "Exhibit grounding is thin"}],
                "ui_suggestions": [{"title": "Expose exhibit references"}],
                "ui_priority_repairs": [{"priority": "high", "target_surface": "draft"}],
                "actor_risk_summary": "The actor still cannot tell whether the draft is ready to sign.",
                "critic_gate": {"verdict": "warning", "blocking_reason": "Signature posture unclear"},
            },
        }

    monkeypatch.setattr(ui_review_module, "review_complaint_output_with_llm_router", fake_review)

    report = ui_review_module.review_complaint_export_artifacts(artifact_metadata)

    assert report["artifact_count"] == 1
    assert report["aggregate"]["average_filing_shape_score"] == 88
    assert report["aggregate"]["average_claim_type_alignment_score"] == 93
    assert report["aggregate"]["issue_findings"] == ["Exhibit grounding is thin"]
    assert report["aggregate"]["missing_formal_sections"] == ["signature_block"]
    assert report["aggregate"]["ui_suggestions"][0]["title"] == "Expose exhibit references"
    assert report["aggregate"]["ui_priority_repairs"][0]["target_surface"] == "draft"
    assert report["aggregate"]["actor_risk_summaries"][0].startswith("The actor still cannot tell")
    assert report["aggregate"]["critic_gates"][0]["verdict"] == "warning"
    assert report["aggregate"]["optimizer_repair_brief"]["top_formal_section_gaps"] == ["signature_block"]
    assert report["aggregate"]["optimizer_repair_brief"]["recommended_surface_targets"] == ["draft"]


def test_review_complaint_export_artifacts_falls_back_to_artifact_metadata_when_router_review_fails(monkeypatch):
    artifact_metadata = [
        {
            "artifact_type": "complaint_export",
            "claim_type": "retaliation",
            "draft_strategy": "llm_router",
            "markdown_filename": "complaint.md",
            "pdf_filename": "complaint.pdf",
            "markdown_excerpt": "IN THE UNITED STATES DISTRICT COURT\n\nCOMPLAINT FOR RETALIATION",
            "filing_shape_score": 71,
            "claim_type_alignment_score": 86,
            "formal_section_gaps": ["signature_block", "claim_count"],
            "release_gate": {
                "verdict": "warning",
                "blocking_reason": "Signature posture remains incomplete.",
                "required_repairs": ["Preserve signature guidance before export."],
            },
            "ui_suggestions_excerpt": "Keep filing-shape warnings visible before export.",
        }
    ]

    def failing_review(markdown_text, **kwargs):
        assert "COMPLAINT FOR RETALIATION" in markdown_text
        raise Exception("llm_router_error: Accelerate not available, using local fallback")

    monkeypatch.setattr(ui_review_module, "review_complaint_output_with_llm_router", failing_review)

    report = ui_review_module.review_complaint_export_artifacts(artifact_metadata)

    assert report["artifact_count"] == 1
    assert report["reviews"][0]["backend"]["strategy"] == "artifact_metadata_fallback"
    assert report["reviews"][0]["backend"]["fallback_from"] == "llm_router"
    assert report["aggregate"]["average_filing_shape_score"] == 71
    assert report["aggregate"]["average_claim_type_alignment_score"] == 86
    assert report["aggregate"]["missing_formal_sections"] == ["claim_count", "signature_block"]
    assert report["aggregate"]["critic_gates"][0]["verdict"] == "warning"
    assert report["aggregate"]["ui_priority_repairs"][0]["target_surface"] == "draft"
