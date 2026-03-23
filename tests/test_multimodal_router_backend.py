from __future__ import annotations

from pathlib import Path
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
