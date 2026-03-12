from __future__ import annotations

from typing import Any, Dict, Optional

from .loader import import_attr_optional
from .types import with_adapter_metadata


generate_text, _error = import_attr_optional("ipfs_datasets_py.llm_router", "generate_text")
LLM_ROUTER_AVAILABLE = generate_text is not None
LLM_ROUTER_ERROR = _error


def generate_text_with_metadata(
	prompt: str,
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	**kwargs: Any,
) -> Dict[str, Any]:
	if generate_text is None:
		return with_adapter_metadata(
			{
				"status": "unavailable",
				"text": "",
				"prompt": prompt,
				"provider_name": provider or "",
				"model_name": model_name or "",
			},
			operation="generate_text",
			backend_available=False,
			degraded_reason=LLM_ROUTER_ERROR,
			implementation_status="unavailable",
		)

	try:
		text = generate_text(
			prompt=prompt,
			provider=provider,
			model_name=model_name,
			**kwargs,
		)
	except Exception as exc:
		return with_adapter_metadata(
			{
				"status": "error",
				"text": "",
				"prompt": prompt,
				"provider_name": provider or "",
				"model_name": model_name or "",
				"error": str(exc),
			},
			operation="generate_text",
			backend_available=True,
			implementation_status="available",
		)

	return with_adapter_metadata(
		{
			"status": "available",
			"text": text,
			"prompt": prompt,
			"provider_name": provider or "",
			"model_name": model_name or "",
		},
		operation="generate_text",
		backend_available=True,
		implementation_status="available",
	)


__all__ = [
	"generate_text",
	"generate_text_with_metadata",
	"LLM_ROUTER_AVAILABLE",
	"LLM_ROUTER_ERROR",
]