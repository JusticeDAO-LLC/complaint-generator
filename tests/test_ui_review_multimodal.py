from __future__ import annotations

from pathlib import Path

import pytest

from applications import ui_review as ui_review_module


pytestmark = [pytest.mark.no_auto_network]


def test_create_ui_review_report_prefers_multimodal_router(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    artifact_metadata = [
        {
            "artifact_type": "complaint_export",
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
    assert report["complaint_output_feedback"]["markdown_filenames"] == ["complaint.md"]
    assert report["complaint_output_feedback"]["ui_suggestions"] == [
        "Add clearer draft-readiness warnings before download."
    ]


def test_review_complaint_output_with_llm_router_generates_filing_shape_feedback(monkeypatch):
    class FakeTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-output-review")
            self.provider = kwargs.get("provider", "fake")
            self.model = kwargs.get("model", "fake-model")

        def __call__(self, prompt):
            assert "formal legal complaint" in prompt
            assert "PRAYER FOR RELIEF" in prompt
            return (
                '{"summary":"The complaint is closer to a filing than a memo, but still needs stronger venue and exhibit posture.",'
                '"filing_shape_score":82,'
                '"strengths":["Caption is present","Prayer for relief is present"],'
                '"issues":[{"severity":"medium","finding":"Exhibit grounding is thin","complaint_impact":"The filing reads under-supported","ui_implication":"Evidence and draft surfaces are not tying exhibits into the pleading clearly enough"}],'
                '"ui_suggestions":[{"title":"Expose exhibit references in the draft builder","target_surface":"evidence,draft","recommendation":"Show saved exhibits beside the pleading sections they support","why_it_matters":"The final complaint will read more like a supported court filing"}]}'
            )

    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.review_complaint_output_with_llm_router(
        "IN THE UNITED STATES DISTRICT COURT\n\nPRAYER FOR RELIEF\nPlaintiff requests relief."
    )

    assert report["backend"]["strategy"] == "llm_router"
    assert report["review"]["filing_shape_score"] == 82
    assert report["review"]["issues"][0]["finding"] == "Exhibit grounding is thin"
    assert report["review"]["ui_suggestions"][0]["target_surface"] == "evidence,draft"
