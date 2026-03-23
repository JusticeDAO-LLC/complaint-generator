"""Multimodal router backend for prompt + screenshot workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from integrations.ipfs_datasets.multimodal import (
    MULTIMODAL_ROUTER_AVAILABLE,
    generate_multimodal_text,
)

from .llm_router_backend import LLMRouterBackend


class MultimodalRouterBackend(LLMRouterBackend):
    """Backend that routes prompt + images through ipfs_datasets_py.multimodal_router."""

    def __call__(
        self,
        text: str,
        *,
        image_paths: Sequence[str | Path] | None = None,
        image_urls: Sequence[str] | None = None,
        system_prompt: str | None = None,
        additional_text_blocks: Sequence[str] | None = None,
    ) -> str:
        if not MULTIMODAL_ROUTER_AVAILABLE:
            raise ImportError(
                "multimodal_router not available. Please ensure ipfs_datasets_py includes "
                "ipfs_datasets_py.multimodal_router."
            )
        return generate_multimodal_text(
            prompt=text,
            provider=self.provider,
            model_name=self.model,
            image_paths=image_paths,
            image_urls=image_urls,
            system_prompt=system_prompt,
            additional_text_blocks=additional_text_blocks,
            **self.config,
        )


MultimodalRouter = MultimodalRouterBackend


__all__ = ["MultimodalRouter", "MultimodalRouterBackend"]
