import json
from pathlib import Path

import pytest

from complaint_generator import (
    build_ui_ux_review_prompt,
    review_screenshot_audit_with_llm_router,
    run_closed_loop_ui_ux_improvement,
    run_end_to_end_complaint_browser_audit,
    run_iterative_ui_ux_workflow,
    run_playwright_screenshot_audit,
)
from complaint_generator import ui_ux_workflow as workflow_module


pytestmark = [pytest.mark.no_auto_network]


def _write_artifact(directory: Path, name: str, url: str = "http://example.test/workspace") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(
            {
                "name": name,
                "url": url,
                "title": "Unified Complaint Workspace",
                "viewport": {"width": 1440, "height": 1200},
                "text_excerpt": "Unified Complaint Workspace\nEvidence Intake\nDraft and Edit",
                "screenshot_path": str(directory / f"{name}.png"),
            }
        )
    )
    (directory / f"{name}.png").write_bytes(b"fake-png")


def test_ui_ux_workflow_defaults_target_full_feature_audit_and_actor_critic_optimizer():
    assert workflow_module.DEFAULT_SCREENSHOT_TEST.endswith(
        "test_homepage_navigation_can_drive_a_full_complaint_journey_with_real_handoffs"
    )
    assert workflow_module.DEFAULT_OPTIMIZER_METHOD == "actor_critic"
    assert workflow_module.DEFAULT_OPTIMIZER_PRIORITY == 90
    assert any("first-time complainants" in goal for goal in workflow_module.DEFAULT_UI_UX_REVIEW_GOALS)
    assert any("Evidence capture" in item for item in workflow_module.DEFAULT_COMPLAINT_WORKFLOW_CAPABILITIES)
    assert "package, CLI, MCP, and browser SDK" in workflow_module.DEFAULT_UI_UX_REVIEW_NOTES


def test_build_ui_ux_review_prompt_includes_artifacts_and_surface_contract(tmp_path):
    _write_artifact(tmp_path, "workspace")
    (tmp_path / "complaint-export.json").write_text(
        json.dumps(
            {
                "name": "workspace-export-artifacts",
                "url": "http://example.test/workspace?target_tab=integrations",
                "title": "Unified Complaint Workspace",
                "viewport": {"width": 1440, "height": 1200},
                "text_excerpt": "Complaint packet exported",
                "artifact_type": "complaint_export",
                "claim_type": "retaliation",
                "draft_strategy": "llm_router",
                "filing_shape_score": 86,
                "claim_type_alignment_score": 35,
                "claim_type_alignment": {
                    "complaint_heading_matches": False,
                    "count_heading_matches": False,
                },
                "markdown_filename": "jordan-example-complaint.md",
                "pdf_filename": "jordan-example-complaint.pdf",
                "markdown_excerpt": "Jordan Example brings this retaliation complaint against Acme Corporation.",
                "pdf_header": "%PDF-1.4",
                "ui_suggestions_excerpt": "Add stronger export warnings when support gaps remain.",
            }
        )
    )

    prompt = build_ui_ux_review_prompt(
        iteration=2,
        artifacts=workflow_module.collect_screenshot_artifacts(tmp_path),
        previous_review="Previous iteration asked for clearer intake guidance.",
    )

    assert "Iteration: 2" in prompt
    assert "Screenshot path:" in prompt
    assert "workspace.html" not in prompt  # prompt includes file contents, not just filenames
    assert "complaint-mcp-server" in prompt or "complaint-generator-mcp" in prompt
    assert "JavaScript MCP SDK" in prompt or "ComplaintMcpClient" in prompt
    assert "Previous iteration asked for clearer intake guidance." in prompt
    assert "Treat this as an actor/critic workflow audit with adversarial pressure-testing" in prompt
    assert "actor/critic lens" in prompt
    assert "visible buttons, links, tabs, and handoff controls" in prompt
    assert "Required capability audit:" in prompt
    assert "Hidden Or Missing Feature Paths" in prompt
    assert "Stage Findings" in prompt
    assert "Actor Journey Findings" in prompt
    assert "Critic Test Obligations" in prompt
    assert "Actor Plan" in prompt
    assert "Critic Verdict" in prompt
    assert "control audit matrix" in prompt
    assert "Intake`, `Evidence`, `Review`, `Draft`, and `Integration Discovery`" in prompt
    assert "save a shared synopsis for the mediator path" in prompt
    assert "Complaint-output-informed UI suggestions:" in prompt
    assert "Claim type: retaliation" in prompt
    assert "Draft strategy: llm_router" in prompt
    assert "Filing shape score: 86" in prompt
    assert "claim-type alignment data" in prompt
    assert "Add stronger export warnings when support gaps remain." in prompt
    assert "complaint_generator.analyze_complaint_output" in prompt
    assert "complaint-workspace export-markdown" in prompt
    assert "complaint-workspace export-pdf" in prompt
    assert "complaint-workspace analyze-output" in prompt
    assert "complaint.analyze_complaint_output" in prompt
    assert "exportComplaintMarkdown()" in prompt
    assert "exportComplaintPdf()" in prompt
    assert "analyzeComplaintOutput()" in prompt
    assert "Use the screenshot evidence together with any complaint-output analysis excerpts" in prompt
    assert "claim type, draft strategy, and exported complaint filing quality remain aligned" in prompt


def test_build_ui_ux_review_prompt_uses_default_goals_and_notes_when_not_supplied(tmp_path):
    _write_artifact(tmp_path, "workspace")

    prompt = build_ui_ux_review_prompt(
        iteration=1,
        artifacts=workflow_module.collect_screenshot_artifacts(tmp_path),
    )

    assert "Workflow goals:" in prompt
    assert "first-time complainants" in prompt
    assert "Review notes:" in prompt
    assert "complaint operator both need to succeed" in prompt
    assert "Package, CLI, MCP server, and JavaScript SDK entry points remain discoverable" in prompt


def test_run_playwright_screenshot_audit_uses_configured_artifact_directory(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"

    def fake_run(cmd, cwd, env, stdout, stderr, text, check):
        assert env["COMPLAINT_UI_SCREENSHOT_DIR"] == str(screenshot_dir)
        _write_artifact(screenshot_dir, "workspace")

        class Result:
            returncode = 0
            stdout = "1 passed"
            stderr = ""

        return Result()

    monkeypatch.setattr(workflow_module.subprocess, "run", fake_run)

    result = run_playwright_screenshot_audit(screenshot_dir=screenshot_dir, pytest_executable="pytest")

    assert result["returncode"] == 0
    assert result["artifact_count"] == 1
    assert result["artifacts"][0]["name"] == "workspace"


def test_run_end_to_end_complaint_browser_audit_delegates_to_playwright_audit(monkeypatch, tmp_path):
    captured = {}

    def fake_audit(**kwargs):
        captured.update(kwargs)
        return {"returncode": 0, "artifact_count": 4, "screenshot_dir": str(kwargs["screenshot_dir"])}

    monkeypatch.setattr(workflow_module, "run_playwright_screenshot_audit", fake_audit)

    result = run_end_to_end_complaint_browser_audit(
        screenshot_dir=tmp_path / "screens",
    )

    assert result["returncode"] == 0
    assert result["artifact_count"] == 4
    assert str(captured["screenshot_dir"]).endswith("screens")
    assert str(captured["pytest_target"]).endswith(
        "test_homepage_navigation_can_drive_a_full_complaint_journey_with_real_handoffs"
    )


def test_review_and_iterative_workflow_return_llm_router_output(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"
    _write_artifact(screenshot_dir, "workspace")

    class FakeMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id
            self.provider = provider
            self.model = model

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Unified Complaint Workspace" in prompt
            assert image_paths
            assert system_prompt
            return "# Top Risks\n- Intake flow needs calmer language."

    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    review = review_screenshot_audit_with_llm_router(screenshot_dir=screenshot_dir, iteration=1)
    assert "Top Risks" in review["review"]

    def fake_audit(**kwargs):
        _write_artifact(screenshot_dir, "workspace")
        return {
            "command": ["pytest"],
            "returncode": 0,
            "stdout": "1 passed",
            "stderr": "",
            "artifact_count": 1,
            "artifacts": workflow_module.collect_screenshot_artifacts(screenshot_dir),
            "screenshot_dir": str(screenshot_dir),
        }

    monkeypatch.setattr(workflow_module, "run_playwright_screenshot_audit", fake_audit)

    result = run_iterative_ui_ux_workflow(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        iterations=2,
    )

    assert result["iterations"] == 2
    assert (output_dir / "iteration-01-review.md").exists()
    assert (output_dir / "iteration-02-review.json").exists()


def test_review_workflow_routes_complaint_output_analysis_into_multimodal_prompt(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    _write_artifact(screenshot_dir, "workspace")
    (screenshot_dir / "workspace-export-artifacts.json").write_text(
        json.dumps(
            {
                "name": "workspace-export-artifacts",
                "artifact_type": "complaint_export",
                "markdown_filename": "complaint.md",
                "pdf_filename": "complaint.pdf",
                "markdown_excerpt": "Jordan Example brings this retaliation complaint against Acme Corporation.",
                "pdf_header": "%PDF-1.4",
                "ui_suggestions_excerpt": "Promote the unsupported-elements warning before export.",
            }
        )
    )

    class FakeMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Promote the unsupported-elements warning before export." in prompt
            assert "Jordan Example brings this retaliation complaint against Acme Corporation." in prompt
            assert "Use the screenshot evidence together with any complaint-output analysis excerpts" in prompt
            assert image_paths
            assert system_prompt
            return "# Top Risks\n- Export warnings are still too easy to miss."

    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    review = review_screenshot_audit_with_llm_router(screenshot_dir=screenshot_dir, iteration=1)

    assert "Export warnings are still too easy to miss." in review["review"]


def test_iterative_workflow_routes_supplemental_complaint_output_artifacts_into_prompt(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"
    _write_artifact(screenshot_dir, "workspace")

    def fake_audit(**kwargs):
        _write_artifact(screenshot_dir, "workspace")
        return {
            "command": ["pytest"],
            "returncode": 0,
            "stdout": "1 passed",
            "stderr": "",
            "artifact_count": 1,
            "artifacts": workflow_module.collect_screenshot_artifacts(screenshot_dir),
            "screenshot_dir": str(screenshot_dir),
        }

    class FakeMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Tighten review-to-draft gatekeeping" in prompt
            assert "Add stronger blocker language" in prompt
            assert image_paths
            assert system_prompt
            return "# Top Risks\n- Review picked up complaint-output suggestions."

    monkeypatch.setattr(workflow_module, "run_playwright_screenshot_audit", fake_audit)
    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    result = run_iterative_ui_ux_workflow(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        iterations=1,
        supplemental_artifacts=[
            {
                "name": "workspace-export-artifacts",
                "artifact_type": "complaint_export",
                "markdown_excerpt": "Jordan Example brings this retaliation complaint against Acme Corporation.",
                "ui_suggestions_excerpt": "- Tighten review-to-draft gatekeeping: Add stronger blocker language before export.",
            }
        ],
    )

    assert result["iterations"] == 1
    assert (output_dir / "iteration-01-review.md").exists()


def test_review_workflow_falls_back_to_text_router_when_multimodal_review_fails(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    _write_artifact(screenshot_dir, "workspace")

    class FailingMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise RuntimeError("vision unavailable")

    class FakeFallbackBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id

        def __call__(self, prompt):
            assert "Unified Complaint Workspace" in prompt
            return "# Top Risks\n- Fallback text review."

    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(workflow_module, "LLMRouterBackend", FakeFallbackBackend)

    review = review_screenshot_audit_with_llm_router(screenshot_dir=screenshot_dir, iteration=1)

    assert "Fallback text review" in review["review"]


def test_closed_loop_ui_ux_improvement_delegates_to_optimizer(monkeypatch, tmp_path):
    captured = {}

    def fake_feedback_loop(self, **kwargs):
        captured.update(kwargs)
        return {"workflow_type": "ui_ux_closed_loop", "rounds_executed": 1}

    monkeypatch.setattr("adversarial_harness.optimizer.Optimizer.run_agentic_ui_ux_feedback_loop", fake_feedback_loop)

    result = run_closed_loop_ui_ux_improvement(
        screenshot_dir=tmp_path / "screens",
        output_dir=tmp_path / "reviews",
        max_rounds=2,
        review_iterations=1,
        notes="Focus on calmer intake wording.",
        goals=["keep the full complaint flow visible", "make the intake calmer"],
        method="adversarial",
        priority=92,
        supplemental_artifacts=[{"artifact_type": "complaint_export", "ui_suggestions_excerpt": "Keep export blockers visible."}],
    )

    assert result["workflow_type"] == "ui_ux_closed_loop"
    assert captured["max_rounds"] == 2
    assert captured["notes"] == "Focus on calmer intake wording."
    assert captured["goals"] == ["keep the full complaint flow visible", "make the intake calmer"]
    assert captured["method"] == "adversarial"
    assert captured["priority"] == 92
    assert captured["metadata"]["supplemental_artifacts"][0]["artifact_type"] == "complaint_export"


def test_closed_loop_ui_ux_improvement_uses_default_brief_when_none_is_supplied(monkeypatch, tmp_path):
    captured = {}

    def fake_feedback_loop(self, **kwargs):
        captured.update(kwargs)
        return {"workflow_type": "ui_ux_closed_loop", "rounds_executed": 1}

    monkeypatch.setattr("adversarial_harness.optimizer.Optimizer.run_agentic_ui_ux_feedback_loop", fake_feedback_loop)

    run_closed_loop_ui_ux_improvement(
        screenshot_dir=tmp_path / "screens",
        output_dir=tmp_path / "reviews",
    )

    assert captured["method"] == workflow_module.DEFAULT_OPTIMIZER_METHOD
    assert captured["priority"] == workflow_module.DEFAULT_OPTIMIZER_PRIORITY
    assert captured["goals"] == workflow_module.DEFAULT_UI_UX_REVIEW_GOALS
    assert captured["notes"] == workflow_module.DEFAULT_UI_UX_REVIEW_NOTES
