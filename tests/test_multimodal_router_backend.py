from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytestmark = [pytest.mark.no_auto_network]


class TestMultimodalRouterBackend:
    def test_multimodal_router_backend_class_can_be_imported(self):
        from backends.multimodal_router_backend import MultimodalRouterBackend

        assert MultimodalRouterBackend is not None

    def test_multimodal_router_backend_forwards_prompt_and_screenshots(self, tmp_path: Path):
        screenshot = tmp_path / "workspace.png"
        screenshot.write_bytes(b"fake")
        mock_generate = Mock(return_value="review text")

        with patch("backends.multimodal_router_backend.generate_multimodal_text", mock_generate):
            from backends.multimodal_router_backend import MultimodalRouterBackend

            backend = MultimodalRouterBackend(
                id="ui-review",
                provider="vision-provider",
                model="vision-model",
                temperature=0.1,
            )

            result = backend(
                "Review the dashboard",
                image_paths=[screenshot],
                system_prompt="Use the screenshots.",
            )

            assert result == "review text"
            call = mock_generate.call_args
            assert call.kwargs["prompt"] == "Review the dashboard"
            assert call.kwargs["provider"] == "vision-provider"
            assert call.kwargs["model_name"] == "vision-model"
            assert list(call.kwargs["image_paths"]) == [screenshot]
            assert call.kwargs["system_prompt"] == "Use the screenshots."
            assert call.kwargs["temperature"] == 0.1

    def test_multimodal_router_backend_raises_when_unavailable(self):
        with patch("backends.multimodal_router_backend.MULTIMODAL_ROUTER_AVAILABLE", False):
            from backends.multimodal_router_backend import MultimodalRouterBackend

            backend = MultimodalRouterBackend(id="ui-review")
            with pytest.raises(ImportError):
                backend("Review")

    def test_multimodal_router_smoke_uses_repository_image_in_chat_completions_payload(self):
        from ipfs_datasets_py import multimodal_router

        repo_image = Path("templates/chaticon.png").resolve()
        assert repo_image.exists()

        class FakeVisionProvider:
            def chat_completions(self, messages, *, model_name=None, **kwargs):
                raise AssertionError("chat_completions_create should be used instead of direct provider call")

        captured: dict[str, object] = {}

        def fake_chat_completions_create(*, messages, model=None, provider=None, provider_instance=None, deps=None, **kwargs):
            captured["messages"] = messages
            captured["model"] = model
            captured["provider"] = provider
            captured["provider_instance"] = provider_instance
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="vision smoke ok"),
                    )
                ]
            )

        with patch.object(multimodal_router.llm_router, "chat_completions_create", fake_chat_completions_create):
            result = multimodal_router.generate_multimodal_text(
                "Review this repository image.",
                provider="openai",
                model_name="gpt-4.1",
                provider_instance=FakeVisionProvider(),
                image_paths=[repo_image],
                system_prompt="Describe what is visible.",
                additional_text_blocks=["Focus on the icon and primary colors."],
            )

        assert result == "vision smoke ok"
        messages = captured["messages"]
        assert isinstance(messages, list)
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Describe what is visible."
        assert messages[1]["role"] == "user"
        content = messages[1]["content"]
        assert isinstance(content, list)
        image_parts = [part for part in content if isinstance(part, dict) and part.get("type") == "image_url"]
        assert len(image_parts) == 1
        image_url = image_parts[0]["image_url"]["url"]
        assert isinstance(image_url, str)
        assert image_url.startswith("data:image/png;base64,")
        assert captured["provider"] == "openai"
        assert captured["model"] == "gpt-4.1"

    def test_multimodal_router_smoke_fallback_flattens_repository_image_for_text_only_provider(self):
        from ipfs_datasets_py import multimodal_router

        repo_image = Path("templates/chaticon.png").resolve()
        assert repo_image.exists()

        class FakeTextOnlyProvider:
            def __init__(self):
                self.prompt = None

            def generate(self, prompt, *, model_name=None, **kwargs):
                self.prompt = prompt
                return "text fallback ok"

        provider = FakeTextOnlyProvider()
        result = multimodal_router.generate_multimodal_text(
            "Review this repository image.",
            provider="codex_cli",
            model_name="gpt-5.3-codex",
            provider_instance=provider,
            image_paths=[repo_image],
            system_prompt="Describe what is visible.",
            additional_text_blocks=["Focus on the icon and primary colors."],
        )

        assert result == "text fallback ok"
        assert isinstance(provider.prompt, str)
        assert "system: Describe what is visible." in provider.prompt
        assert "user: Review this repository image." in provider.prompt
        assert "[image attachment included]" in provider.prompt
