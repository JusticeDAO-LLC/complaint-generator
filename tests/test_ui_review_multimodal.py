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
