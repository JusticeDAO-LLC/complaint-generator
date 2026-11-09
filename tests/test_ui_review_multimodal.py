from __future__ import annotations

from pathlib import Path
import time

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
            assert kwargs["provider"] == ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            assert kwargs["model"] == ui_review_module.DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER["codex_cli"]
            assert kwargs["timeout"] == ui_review_module._ui_review_timeout_for_provider(
                ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            )
            assert kwargs["retry_max_attempts"] == 1
            assert kwargs["allow_local_fallback"] is False

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Look at this complaint-generator page screenshot" in prompt
            assert "Complaint-output hints" in prompt
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
    assert report["backend"]["prompt_mode"] == "compact"
    assert report["backend"]["prompt_chars"] > 0
    assert report["backend"]["screenshot_count"] == 1
    assert report["backend"]["elapsed_seconds"] >= 0
    assert report["review"]["summary"] == "Use calmer next-step guidance."
    assert report["complaint_output_feedback"]["export_artifact_count"] == 1
    assert report["complaint_output_feedback"]["claim_types"] == ["retaliation"]
    assert report["complaint_output_feedback"]["draft_strategies"] == ["llm_router"]
    assert report["complaint_output_feedback"]["filing_shape_scores"] == [83]
    assert report["complaint_output_feedback"]["ui_suggestions"] == ["Add a clearer export warning when support gaps remain."]


def test_build_ui_review_prompt_compacts_large_export_feedback(tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    giant_hint = "Export warning " + ("very long detail " * 200)

    prompt = ui_review_module.build_ui_review_prompt(
        [screenshot],
        artifact_metadata=[
            {
                "artifact_type": "complaint_export",
                "claim_type": "retaliation",
                "draft_strategy": "llm_router",
                "filing_shape_score": 88,
                "markdown_filename": "complaint.md",
                "pdf_filename": "complaint.pdf",
                "ui_suggestions_excerpt": giant_hint,
            }
        ],
        include_full_contract_context=False,
    )

    assert "Complaint-output hints" in prompt
    assert giant_hint not in prompt
    assert "...[truncated]" in prompt
    assert len(prompt) < 4000


def test_create_ui_review_report_falls_back_to_text_router(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")

    class FailingMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")
            assert kwargs["provider"] == ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            assert kwargs["model"] == ui_review_module.DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER["codex_cli"]
            assert kwargs["timeout"] == ui_review_module._ui_review_timeout_for_provider(
                ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            )
            assert kwargs["retry_max_attempts"] == 1
            assert kwargs["allow_local_fallback"] is False

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise RuntimeError("vision offline")

    class FakeTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")
            assert kwargs["provider"] == ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            assert kwargs["model"] == ui_review_module.DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER["codex_cli"]
            assert kwargs["timeout"] == ui_review_module._ui_review_timeout_for_provider(
                ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            )
            assert kwargs["retry_max_attempts"] == 1
            assert kwargs["allow_local_fallback"] is False

        def __call__(self, prompt):
            assert "Look at this complaint-generator page screenshot" in prompt
            return '{"summary":"Fallback review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)])

    assert report["backend"]["strategy"] == "llm_router"
    assert report["backend"]["fallback_from"] == "multimodal_router"
    assert report["backend"]["prompt_mode"] == "compact"
    assert report["backend"]["prompt_chars"] > 0
    assert report["backend"]["screenshot_count"] == 0
    assert report["backend"]["elapsed_seconds"] >= 0
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
            assert kwargs["provider"] == ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            assert kwargs["model"] == ui_review_module.DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER["codex_cli"]
            assert kwargs["timeout"] == ui_review_module._ui_review_timeout_for_provider(
                ui_review_module.DEFAULT_UI_REVIEW_PROVIDER
            )
            assert kwargs["retry_max_attempts"] == 1
            assert kwargs["allow_local_fallback"] is False

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Complaint-output hints" in prompt
            assert "Add clearer draft-readiness warnings before download." in prompt
            return '{"summary":"Workflow review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    report = ui_review_module.run_ui_review_workflow(str(tmp_path))

    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["backend"]["prompt_mode"] == "compact"
    assert report["complaint_output_feedback"]["export_artifact_count"] == 1
    assert report["complaint_output_feedback"]["claim_types"] == ["retaliation"]
    assert report["complaint_output_feedback"]["draft_strategies"] == ["template"]
    assert report["complaint_output_feedback"]["filing_shape_scores"] == [61]
    assert report["complaint_output_feedback"]["markdown_filenames"] == ["complaint.md"]
    assert report["complaint_output_feedback"]["ui_suggestions"] == [
        "Add clearer draft-readiness warnings before download."
    ]


def test_create_ui_review_report_times_out_multimodal_and_falls_back_to_text(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    monkeypatch.setattr(ui_review_module, "_ui_review_timeout_for_provider", lambda provider: 0.01)

    class HangingMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            time.sleep(0.05)
            return '{"summary":"too late","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    class FakeTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt):
            assert "Look at this complaint-generator page screenshot" in prompt
            return '{"summary":"Timed out multimodal, text fallback succeeded.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", HangingMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)])

    assert report["backend"]["strategy"] == "llm_router"
    assert report["backend"]["fallback_from"] == "multimodal_router"
    assert "timed out" in report["backend"]["fallback_error"].lower()
    assert report["review"]["summary"] == "Timed out multimodal, text fallback succeeded."


def test_create_ui_review_report_rate_limit_falls_back_provider_chain(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    monkeypatch.setenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL_HF_INFERENCE_API", "hf-vision-model")

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            if self.provider == "codex_cli":
                raise RuntimeError("Codex usage limit reached")
            if self.provider == "copilot_cli":
                raise RuntimeError("copilot_cli multimodal path unavailable: installed Copilot CLI does not advertise image input support")
            assert self.provider == "hf_inference_api"
            assert self.model == "hf-vision-model"
            return '{"summary":"HF fallback review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    class FakeTextBackend:
        def __init__(self, **kwargs):
            raise AssertionError("text fallback should not run when hf multimodal fallback succeeds")

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)])

    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["backend"]["provider"] == "hf_inference_api"
    assert report["backend"]["model"] == "hf-vision-model"
    assert report["backend"]["provider_fallback_from"] == "codex_cli"
    assert "usage limit" in report["backend"]["fallback_error"].lower()
    assert report["backend"]["fallback_attempts"] == [
        {
            "provider": "copilot_cli",
            "model": None,
            "error": "copilot_cli multimodal path unavailable: installed Copilot CLI does not advertise image input support",
        }
    ]
    assert report["review"]["summary"] == "HF fallback review."


def test_create_ui_review_report_prepares_provider_friendly_images(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    prepared = tmp_path / "workspace.review.jpg"
    prepared.write_bytes(b"fake-jpg")

    def fake_prepare_multimodal_image_paths(screenshots, *, provider, diagnostics_dir):
        assert screenshots == [screenshot]
        assert provider == "hf_inference_api"
        return [prepared], {
            "prepared_image_count": 1,
            "prepared_image_paths": [str(prepared)],
            "original_screenshot_count": 1,
        }

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert image_paths == [prepared]
            return '{"summary":"Prepared image review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "_prepare_multimodal_image_paths", fake_prepare_multimodal_image_paths)
    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)], provider="hf_inference_api")

    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["backend"]["prepared_image_count"] == 1
    assert report["backend"]["prepared_image_paths"] == [str(prepared)]
    assert report["backend"]["original_screenshot_count"] == 1
    assert report["review"]["summary"] == "Prepared image review."


def test_prepare_review_image_copy_preserves_readable_width_for_tall_screenshots(tmp_path: Path):
    Image = pytest.importorskip("PIL.Image")

    screenshot = tmp_path / "workspace-integrations.png"
    output_dir = tmp_path / "prepared"
    image = Image.new("RGB", (1280, 45626), (245, 245, 248))
    image.save(screenshot, format="PNG")

    prepared = ui_review_module._prepare_review_image_copy(
        screenshot,
        output_dir=output_dir,
        provider="codex_cli",
    )

    assert prepared != screenshot
    with Image.open(prepared) as prepared_image:
        width, height = prepared_image.size
    assert width >= 1200
    assert height <= 1600
    assert prepared.suffix == ".jpg"


def test_create_ui_review_report_non_rate_limit_error_does_not_use_provider_chain(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise RuntimeError("vision parser exploded")

    class FakeTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt):
            return '{"summary":"Text fallback after non-rate-limit error.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)])

    assert report["backend"]["strategy"] == "llm_router"
    assert "fallback_attempts" not in report["backend"]
    assert report["review"]["summary"] == "Text fallback after non-rate-limit error."


def test_ui_review_model_for_provider_defaults_hf_multimodal_profile():
    assert ui_review_module._ui_review_model_for_provider("hf_inference_api") == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert ui_review_module._ui_review_timeout_for_provider("hf_inference_api") == 60


def test_create_ui_review_report_defaults_to_verified_codex_profile(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")
            assert self.provider == "codex_cli"
            assert self.model == "gpt-5.3-codex"
            assert kwargs["timeout"] == ui_review_module._ui_review_timeout_for_provider("codex_cli")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            return '{"summary":"Default profile review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)])

    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["backend"]["provider"] == "codex_cli"
    assert report["backend"]["model"] == "gpt-5.3-codex"
    assert report["backend"]["prompt_mode"] == "compact"


def test_create_ui_review_report_can_force_full_single_page_prompt(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    monkeypatch.setenv("COMPLAINT_UI_REVIEW_FULL_SINGLE_PAGE_PROMPT", "1")

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "ComplaintMcpClient" in prompt
            assert "Screenshot artifacts" in prompt
            return '{"summary":"Full prompt review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)])

    assert report["backend"]["prompt_mode"] == "full"
    assert report["review"]["summary"] == "Full prompt review."


def test_create_ui_review_report_enables_codex_trace_artifacts(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    output_path = tmp_path / "review.json"

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")
            assert kwargs["trace"] is True
            assert kwargs["trace_dir"].endswith("review-codex-diagnostics")
            assert kwargs["trace_jsonl_path"].endswith("workspace.codex.jsonl")
            assert kwargs["trace_stderr_path"].endswith("workspace.codex.stderr.log")
            assert kwargs["trace_metadata_path"].endswith("workspace.codex.metadata.json")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            return '{"summary":"Trace-enabled review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)], output_path=str(output_path))

    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["review"]["summary"] == "Trace-enabled review."


def test_run_ui_review_workflow_defaults_to_inline_page_reviews_for_codex_cli(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    captured = {}

    def fake_create_ui_review_report(screenshot_paths, **kwargs):
        captured["screenshot_paths"] = list(screenshot_paths)
        captured["kwargs"] = dict(kwargs)
        return {"backend": {"strategy": "page_reviews"}, "review": {"summary": "ok"}}

    monkeypatch.setattr(ui_review_module, "create_ui_review_report", fake_create_ui_review_report)

    ui_review_module.run_ui_review_workflow(str(tmp_path))

    assert captured["screenshot_paths"] == [str(screenshot.resolve())]
    assert captured["kwargs"]["provider"] == "codex_cli"
    assert captured["kwargs"]["model"] == "gpt-5.3-codex"
    assert captured["kwargs"]["page_review_executor"] == "inline"


def test_create_ui_review_report_limits_codex_page_reviews_to_high_signal_screenshots(monkeypatch, tmp_path: Path):
    screenshot_names = [
        "workspace-intake.png",
        "workspace-evidence.png",
        "workspace-review.png",
        "workspace-draft.png",
        "workspace-integrations.png",
        "workspace-homepage.png",
    ]
    screenshots = []
    artifact_metadata = []
    for name in screenshot_names:
        path = tmp_path / name
        path.write_bytes(b"fake-png")
        screenshots.append(path)
        artifact_metadata.append(
            {
                "artifact_type": "workspace_surface",
                "name": path.stem,
                "title": path.stem.replace("-", " ").title(),
                "screenshot_path": str(path),
                "text_excerpt": path.stem,
            }
        )

    def fake_run_page_review_task(task):
        return {
            "page_label": task["page_label"],
            "backend": {"strategy": "fallback"},
            "review": {
                "summary": f"reviewed {task['page_label']}",
                "issues": [],
                "recommended_changes": [],
                "broken_controls": [],
                "button_audit": [],
                "route_handoffs": [],
                "workflow_gaps": [],
                "playwright_followups": [],
                "complaint_journey": {},
                "actor_plan": {},
                "critic_review": {},
                "actor_summary": "",
                "critic_summary": "",
                "actor_path_breaks": [],
                "critic_test_obligations": [],
                "stage_findings": {},
            },
        }

    monkeypatch.setattr(ui_review_module, "_run_page_review_task", fake_run_page_review_task)

    report = ui_review_module.create_ui_review_report(
        [str(path) for path in screenshots],
        provider="codex_cli",
        artifact_metadata=artifact_metadata,
        page_review_executor="inline",
    )

    assert report["backend"]["strategy"] == "page_reviews"
    assert report["backend"]["selected_screenshot_count"] == 4
    assert report["backend"]["skipped_screenshot_count"] == 2
    assert report["backend"]["selected_screenshots"] == [
        "workspace-draft.png",
        "workspace-evidence.png",
        "workspace-intake.png",
        "workspace-review.png",
    ]
    assert report["backend"]["skipped_screenshots"] == [
        "workspace-integrations.png",
        "workspace-homepage.png",
    ]
    assert [item["name"] for item in report["screenshots"]] == report["backend"]["selected_screenshots"]
    assert len(report["page_reviews"]) == 4


def test_run_ui_review_workflow_falls_back_to_text_router_when_only_export_artifacts_exist(monkeypatch, tmp_path: Path):
    (tmp_path / "workspace-export-artifacts.json").write_text(
        (
            '{'
            '"artifact_type":"complaint_export",'
            '"claim_type":"retaliation",'
            '"draft_strategy":"llm_router",'
            '"filing_shape_score":94, '
            '"markdown_filename":"complaint.md",'
            '"pdf_filename":"complaint.pdf",'
            '"ui_suggestions_excerpt":"Keep formal pleading warnings visible before download."'
            '}'
        )
    )

    class FailingMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise RuntimeError("no screenshots available for multimodal review")

    class FakeTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt):
            assert "Complaint-output hints" in prompt
            assert "Keep formal pleading warnings visible before download." in prompt
            return '{"summary":"Artifact-only review.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.run_ui_review_workflow(str(tmp_path))

    assert report["backend"]["strategy"] == "llm_router"
    assert report["backend"]["fallback_from"] == "multimodal_router"
    assert report["review"]["summary"] == "Artifact-only review."
    assert report["complaint_output_feedback"]["export_artifact_count"] == 1


def test_create_ui_review_report_uses_artifact_driven_fallback_when_both_router_paths_fail(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace-export-artifacts.png"
    screenshot.write_bytes(b"fake-png")
    artifact_metadata = [
        {
            "artifact_type": "complaint_export",
            "claim_type": "retaliation",
            "draft_strategy": "llm_router",
            "filing_shape_score": 71,
            "release_gate": {"verdict": "warning", "blocking_reason": "Signature posture is still weak."},
            "formal_section_gaps": ["signature_block"],
            "ui_suggestions_excerpt": "Keep filing-shape warnings visible before export.",
        }
    ]

    class FailingMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise TimeoutError("UI review timed out after 60s")

    class FailingTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt):
            raise TimeoutError("UI review timed out after 60s")

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FailingTextBackend)

    report = ui_review_module.create_ui_review_report(
        [str(screenshot)],
        artifact_metadata=artifact_metadata,
    )

    assert report["backend"]["strategy"] == "fallback"
    assert report["review"]["summary"].startswith("Router-driven UI review timed out")
    assert report["review"]["ui_suggestions"][0]["recommendation"] == "Keep filing-shape warnings visible before export."
    assert report["review"]["issues"][0]["recommended_fix"] == "Keep filing-shape warnings visible before export."
    assert report["review"]["broken_controls"][0]["control"] == "UI review automation"


def test_create_ui_review_report_uses_native_multimodal_for_codex_cli(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")
            assert kwargs["provider"] == "codex_cli"

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Look at this complaint-generator page screenshot" in prompt
            assert image_paths == [screenshot]
            assert system_prompt
            return '{"summary":"Codex multimodal review succeeded.","issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'

    class UnexpectedTextBackend:
        def __init__(self, **kwargs):
            raise AssertionError("codex_cli should now use the native multimodal backend for screenshot review")

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", UnexpectedTextBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)], provider="codex_cli")

    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["backend"]["provider"] == "codex_cli"
    assert report["review"]["summary"] == "Codex multimodal review succeeded."


def test_aggregate_page_review_reports_merges_page_level_feedback():
    page_reports = [
        {
            "page_label": "workspace-intake",
            "backend": {"id": "ui-review", "provider": "codex_cli", "strategy": "multimodal_router"},
            "review": {
                "summary": "workspace-intake review complete.",
                "issues": [
                    {
                        "severity": "medium",
                        "surface": "workspace-intake",
                        "problem": "workspace-intake has a confusing CTA.",
                        "user_impact": "Users may hesitate.",
                        "recommended_fix": "Clarify the primary action on workspace-intake.",
                    }
                ],
                "recommended_changes": [
                    {
                        "title": "Repair workspace-intake",
                        "implementation_notes": "Tighten the primary flow for workspace-intake.",
                        "shared_code_path": "templates/workspace.html",
                        "sdk_considerations": "Keep ComplaintMcpClient visible.",
                    }
                ],
                "button_audit": [
                    {
                        "control": "Save Intake",
                        "expected_outcome": "Persist intake answers and move the actor toward evidence capture.",
                        "status": "warning",
                        "notes": "The CTA needs stronger next-step language.",
                    }
                ],
                "route_handoffs": [
                    {
                        "from_surface": "workspace-intake",
                        "to_surface": "chat",
                        "trigger": "handoff-chat-button",
                        "state_requirements": ["shared DID", "case synopsis"],
                        "status": "pass",
                    }
                ],
                "complaint_journey": {
                    "tested_stages": ["intake", "chat"],
                    "journey_gaps": ["Mediator handoff could be clearer from intake."],
                    "sdk_tool_invocations": ["complaint.submit_intake", "complaint.build_mediator_prompt"],
                    "release_blockers": ["Intake CTA hierarchy is still confusing."],
                },
                "workflow_gaps": ["workspace-intake gap"],
                "playwright_followups": ["Capture workspace-intake again after fixes"],
                "stage_findings": {"Evidence": "workspace-intake evidence finding"},
            },
        },
        {
            "page_label": "workspace-evidence",
            "backend": {"id": "ui-review", "provider": "codex_cli", "strategy": "multimodal_router"},
            "review": {
                "summary": "workspace-evidence review complete.",
                "issues": [
                    {
                        "severity": "medium",
                        "surface": "workspace-evidence",
                        "problem": "workspace-evidence has a confusing CTA.",
                        "user_impact": "Users may hesitate.",
                        "recommended_fix": "Clarify the primary action on workspace-evidence.",
                    }
                ],
                "recommended_changes": [
                    {
                        "title": "Repair workspace-evidence",
                        "implementation_notes": "Tighten the primary flow for workspace-evidence.",
                        "shared_code_path": "templates/workspace.html",
                        "sdk_considerations": "Keep ComplaintMcpClient visible.",
                    }
                ],
                "button_audit": [
                    {
                        "control": "Save Evidence",
                        "expected_outcome": "Persist evidence and refresh the support matrix.",
                        "status": "pass",
                        "notes": "The button is visible, but the panel still needs clearer upload guidance.",
                    }
                ],
                "route_handoffs": [
                    {
                        "from_surface": "workspace-evidence",
                        "to_surface": "workspace-review",
                        "trigger": "Review tab",
                        "state_requirements": ["saved evidence"],
                        "status": "pass",
                    }
                ],
                "complaint_journey": {
                    "tested_stages": ["evidence", "review", "draft"],
                    "journey_gaps": ["Evidence upload guidance is still too thin."],
                    "sdk_tool_invocations": ["complaint.save_evidence", "complaint.review_case", "complaint.generate_complaint"],
                    "release_blockers": ["Evidence copy still undersells why uploads matter to the complaint."],
                },
                "workflow_gaps": ["workspace-evidence gap"],
                "playwright_followups": ["Capture workspace-evidence again after fixes"],
                "stage_findings": {"Evidence": "workspace-evidence evidence finding"},
            },
        },
    ]

    aggregated = ui_review_module._aggregate_page_review_reports(page_reports)

    assert "Aggregated 2 page-level screenshot reviews." in aggregated["summary"]
    assert len(aggregated["issues"]) == 2
    assert len(aggregated["recommended_changes"]) == 2
    assert len(aggregated["button_audit"]) == 2
    assert len(aggregated["route_handoffs"]) == 2
    assert len(aggregated["page_reviews"]) == 2
    assert aggregated["critic_review"]["verdict"] == "warning"
    assert aggregated["complaint_journey"]["tested_stages"] == ["intake", "chat", "evidence", "review", "draft"]
    assert aggregated["complaint_journey"]["sdk_tool_invocations"] == [
        "complaint.submit_intake",
        "complaint.build_mediator_prompt",
        "complaint.save_evidence",
        "complaint.review_case",
        "complaint.generate_complaint",
    ]
    assert aggregated["complaint_journey"]["release_blockers"] == [
        "Intake CTA hierarchy is still confusing.",
        "Evidence copy still undersells why uploads matter to the complaint.",
    ]
    assert "workspace-intake: workspace-intake evidence finding" in aggregated["stage_findings"]["Evidence"]
    assert "workspace-evidence: workspace-evidence evidence finding" in aggregated["stage_findings"]["Evidence"]


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
            "backend": {"strategy": "llm_router", "provider": "llm_router", "model": "formal_complaint_reviewer"},
            "review": {
                "summary": "Looks closer to a filing.",
                "filing_shape_score": 88,
                "claim_type_alignment_score": 93,
                "missing_formal_sections": ["signature_block"],
                "issues": [{"finding": "Exhibit grounding is thin"}],
                "ui_suggestions": [{"title": "Expose exhibit references"}],
                "ui_priority_repairs": [{"priority": "high", "target_surface": "draft,integrations"}],
                "actor_risk_summary": "The actor still cannot tell whether the draft is ready to sign.",
                "critic_gate": {"verdict": "warning", "blocking_reason": "Signature posture unclear"},
            },
        }

    monkeypatch.setattr(ui_review_module, "review_complaint_output_with_llm_router", fake_review)

    report = ui_review_module.review_complaint_export_artifacts(artifact_metadata)

    assert report["artifact_count"] == 1
    assert report["aggregate"]["average_filing_shape_score"] == 88
    assert report["aggregate"]["average_claim_type_alignment_score"] == 93
    assert report["aggregate"]["router_backends"][0]["strategy"] == "llm_router"
    assert report["aggregate"]["issue_findings"] == ["Exhibit grounding is thin"]
    assert report["aggregate"]["missing_formal_sections"] == ["signature_block"]
    assert report["aggregate"]["ui_suggestions"][0]["title"] == "Expose exhibit references"
    assert report["aggregate"]["ui_priority_repairs"][0]["target_surface"] == "draft,integrations"
    assert report["aggregate"]["actor_risk_summaries"][0].startswith("The actor still cannot tell")
    assert report["aggregate"]["critic_gates"][0]["verdict"] == "warning"
    assert report["aggregate"]["optimizer_repair_brief"]["top_formal_section_gaps"] == ["signature_block"]
    assert report["aggregate"]["optimizer_repair_brief"]["recommended_surface_targets"] == ["draft", "integrations"]
    assert report["aggregate"]["optimizer_repair_brief"]["router_path_summary"] == "llm_router / formal_complaint_reviewer"


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


def test_ui_review_timeout_honors_environment_override(monkeypatch):
    monkeypatch.setenv("COMPLAINT_GENERATOR_UI_REVIEW_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("COMPLAINT_GENERATOR_UI_REVIEW_TIMEOUT_SECONDS_CODEX_CLI", "4")

    assert ui_review_module._ui_review_timeout_for_provider("codex_cli") == 4
    assert ui_review_module._ui_review_timeout_for_provider("hf_inference_api") == 3


def test_ui_review_timeout_emits_heartbeat(monkeypatch, capsys):
    monkeypatch.setenv("COMPLAINT_GENERATOR_UI_REVIEW_HEARTBEAT_SECONDS", "0.01")

    def slow_call():
        time.sleep(0.04)
        return "ok"

    assert ui_review_module._call_with_timeout(slow_call, timeout_s=0.2, label="test_page") == "ok"
    captured = capsys.readouterr()
    assert "[ui_review] stage=test_page" in captured.out
