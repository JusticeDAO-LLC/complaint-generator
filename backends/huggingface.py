"""Deprecated legacy HuggingFace backend.

Prefer routing via `ipfs_datasets_py.llm_router`.

This module remains importable for backward compatibility, but it routes
through `LLMRouterBackend` and emits a DeprecationWarning.
"""

from __future__ import annotations

import warnings
from typing import Any, Mapping

from .llm_router_backend import LLMRouterBackend


warnings.warn(
	"`backends.huggingface.HuggingFaceBackend` is deprecated in complaint-generator; "
	"use `backends.LLMRouterBackend` (ipfs_datasets_py.llm_router) instead.",
	DeprecationWarning,
	stacklevel=2,
)


class HuggingFaceBackend(LLMRouterBackend):
	"""Compatibility wrapper that routes HF-style configs via llm_router."""

	def __init__(
		self,
		id: str,
		api_key: str | None = None,
		engine: str | None = None,
		**config: Any,
	):
		# `api_key` is intentionally ignored; llm_router providers read secrets from env.
		if api_key:
			warnings.warn(
				"`api_key` passed to HuggingFaceBackend is ignored; set HF_TOKEN/HUGGINGFACE_HUB_TOKEN in the environment instead.",
				DeprecationWarning,
				stacklevel=2,
			)

		model = config.pop("model", None) or engine
		super().__init__(id=id, provider=config.pop("provider", "huggingface_router"), model=model, **config)

	def __call__(self, payload: str | Mapping[str, Any]):
		# Legacy HF usage sometimes calls with {"inputs": "..."}.
		if isinstance(payload, dict):
			payload = str(payload.get("inputs") or payload.get("prompt") or "")
		return super().__call__(str(payload))