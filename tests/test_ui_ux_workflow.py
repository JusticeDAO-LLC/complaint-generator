import json
from pathlib import Path

import pytest

from complaint_generator import (
    build_ui_ux_review_prompt,
    review_screenshot_audit_with_llm_router,
    run_closed_loop_ui_ux_improvement,
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


def test_build_ui_ux_review_prompt_includes_artifacts_and_surface_contract(tmp_path):
    _write_artifact(tmp_path, "workspace")

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
    )

    assert result["workflow_type"] == "ui_ux_closed_loop"
    assert captured["max_rounds"] == 2
    assert captured["notes"] == "Focus on calmer intake wording."
