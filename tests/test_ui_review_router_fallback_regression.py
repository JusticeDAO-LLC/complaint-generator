from __future__ import annotations

from pathlib import Path

import pytest

from applications import ui_review as ui_review_module


pytestmark = [pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_create_ui_review_report_uses_text_router_when_multimodal_review_fails(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")

    class FailingMultimodalBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert image_paths == [screenshot]
            raise RuntimeError("vision offline")

    class FakeTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt):
            assert "Screenshot artifacts" in prompt
            return (
                '{"summary":"Fallback review succeeded.",'
                '"issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'
            )

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)])

    assert report["backend"]["strategy"] == "llm_router"
    assert report["backend"]["fallback_from"] == "multimodal_router"
    assert report["backend"]["fallback_error"] == "vision offline"
    assert report["review"]["summary"] == "Fallback review succeeded."


def test_create_ui_review_report_skips_multimodal_for_text_only_provider(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")

    class UnexpectedMultimodalBackend:
        def __init__(self, **kwargs):
            raise AssertionError("text-only providers should not initialize the multimodal backend")

    class FakeTextBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt):
            assert "Screenshot artifacts" in prompt
            return (
                '{"summary":"Text-only review succeeded.",'
                '"issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'
            )

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", UnexpectedMultimodalBackend)
    monkeypatch.setattr(ui_review_module, "LLMRouterBackend", FakeTextBackend)

    report = ui_review_module.create_ui_review_report([str(screenshot)], provider="copilot_cli")

    assert report["backend"]["strategy"] == "llm_router"
    assert report["backend"]["fallback_from"] == "multimodal_router"
    assert report["backend"]["multimodal_skipped"] is True
    assert "text-only provider" in report["backend"]["fallback_error"]
    assert report["review"]["summary"] == "Text-only review succeeded."


def test_create_ui_review_report_resolves_router_aliases_before_backend_call(monkeypatch, tmp_path: Path):
    screenshot = tmp_path / "workspace.png"
    screenshot.write_bytes(b"fake-png")
    observed_kwargs = {}

    class FakeMultimodalBackend:
        def __init__(self, **kwargs):
            observed_kwargs.update(kwargs)
            self.id = kwargs.get("id", "ui-review")
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert image_paths == [screenshot]
            return (
                '{"summary":"Router alias review succeeded.",'
                '"issues":[],"recommended_changes":[],"workflow_gaps":[],"playwright_followups":[]}'
            )

    monkeypatch.setattr(ui_review_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    report = ui_review_module.create_ui_review_report(
        [str(screenshot)],
        provider="llm_router",
        model="multimodal_router",
    )

    assert observed_kwargs["provider"] == "codex_cli"
    assert observed_kwargs["model"] == "gpt-5.3-codex"
    assert "llm_router" not in {observed_kwargs["provider"], observed_kwargs["model"]}
    assert "multimodal_router" not in {observed_kwargs["provider"], observed_kwargs["model"]}
    assert report["backend"]["strategy"] == "multimodal_router"
    assert report["backend"]["provider"] == "codex_cli"
    assert report["backend"]["requested_provider_alias"] == "llm_router"
    assert report["backend"]["requested_model_alias"] == "multimodal_router"
    assert report["backend"]["route_alias_resolved"] is True
    assert report["review"]["summary"] == "Router alias review succeeded."
