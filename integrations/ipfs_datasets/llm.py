from __future__ import annotations

from contextlib import contextmanager
import os
import threading
from typing import Any, Dict, Mapping, Optional

from .loader import import_attr_optional
from .types import with_adapter_metadata


generate_text, _error = import_attr_optional("ipfs_datasets_py.llm_router", "generate_text")
LLM_ROUTER_AVAILABLE = generate_text is not None
LLM_ROUTER_ERROR = _error


HF_ROUTER_DEFAULT_BASE_URL = "https://router.huggingface.co/v1"
HF_ROUTER_PROVIDER_ALIASES = {
	"hf_inference",
	"hf_router",
	"huggingface_inference",
	"huggingface_router",
}
_LLM_ROUTER_ENV_LOCK = threading.RLock()


def _coalesce_env(*names: str) -> str:
	for name in names:
		value = os.getenv(name, "").strip()
		if value:
			return value
	return ""


def _pop_first_string(options: Dict[str, Any], *names: str) -> str:
	for name in names:
		value = options.pop(name, None)
		if value is None:
			continue
		text = str(value).strip()
		if text:
			return text
	return ""


def _normalize_headers(value: Any) -> Dict[str, str]:
	if isinstance(value, Mapping):
		return {
			str(key).strip(): str(item).strip()
			for key, item in value.items()
			if str(key).strip() and str(item).strip()
		}
	return {}


def _is_huggingface_router_request(provider: Optional[str], options: Dict[str, Any]) -> bool:
	provider_key = str(provider or "").strip().lower()
	if provider_key in HF_ROUTER_PROVIDER_ALIASES:
		return True
	base_url = str(
		options.get("base_url")
		or options.get("api_base")
		or options.get("api_base_url")
		or options.get("router_base_url")
		or options.get("llm_router_base_url")
		or ""
	).strip().lower()
	if "huggingface.co" in base_url:
		return True
	return provider_key in {"hf", "huggingface"} and bool(base_url)


def _build_huggingface_router_request(
	provider: Optional[str],
	model_name: Optional[str],
	options: Dict[str, Any],
) -> tuple[str, Optional[str], Dict[str, Any], Dict[str, str], Dict[str, Any]]:
	call_options = dict(options)
	headers = _normalize_headers(call_options.pop("headers", None))
	authorization = headers.pop("Authorization", "")
	bearer_token = ""
	if authorization.lower().startswith("bearer "):
		bearer_token = authorization[7:].strip()

	base_url = _pop_first_string(
		call_options,
		"base_url",
		"api_base",
		"api_base_url",
		"router_base_url",
		"llm_router_base_url",
	) or _coalesce_env(
		"HUGGINGFACE_LLM_ROUTER_BASE_URL",
		"HF_LLM_ROUTER_BASE_URL",
		"LLM_ROUTER_ARCH_BASE_URL",
	) or HF_ROUTER_DEFAULT_BASE_URL

	api_key = _pop_first_string(call_options, "api_key", "token", "access_token") or bearer_token or _coalesce_env(
		"HF_TOKEN",
		"HUGGINGFACE_HUB_TOKEN",
		"HUGGINGFACE_API_KEY",
		"HF_API_TOKEN",
	)
	referer = _pop_first_string(call_options, "http_referer", "referer") or headers.pop("HTTP-Referer", "") or headers.pop("Referer", "")
	app_title = _pop_first_string(call_options, "app_title") or headers.pop("X-Title", "")

	effective_model_name = model_name or _pop_first_string(call_options, "route_model", "fallback_model") or _coalesce_env(
		"LLM_ROUTER_FALLBACK_MODEL",
		"IPFS_DATASETS_PY_OPENROUTER_MODEL",
		"IPFS_DATASETS_PY_LLM_MODEL",
	) or None

	env_overrides = {
		"IPFS_DATASETS_PY_OPENROUTER_BASE_URL": base_url.rstrip("/"),
	}
	if api_key:
		env_overrides["IPFS_DATASETS_PY_OPENROUTER_API_KEY"] = api_key
	if effective_model_name:
		env_overrides["IPFS_DATASETS_PY_OPENROUTER_MODEL"] = str(effective_model_name)
	if referer:
		env_overrides["OPENROUTER_HTTP_REFERER"] = referer
	if app_title:
		env_overrides["OPENROUTER_APP_TITLE"] = app_title

	metadata = {
		"requested_provider_name": provider or "",
		"effective_provider_name": "openrouter",
		"effective_model_name": str(effective_model_name or ""),
		"router_base_url": base_url.rstrip("/"),
	}
	return "openrouter", effective_model_name, call_options, env_overrides, metadata


def _prepare_generate_text_call(
	prompt: str,
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	**kwargs: Any,
) -> tuple[str, Optional[str], Dict[str, Any], Dict[str, str], Dict[str, Any]]:
	call_options = dict(kwargs)
	if _is_huggingface_router_request(provider, call_options):
		return _build_huggingface_router_request(provider, model_name, call_options)
	metadata = {
		"requested_provider_name": provider or "",
		"effective_provider_name": provider or "",
		"effective_model_name": str(model_name or ""),
		"router_base_url": "",
	}
	return str(provider or ""), model_name, call_options, {}, metadata


@contextmanager
def _temporary_env(overrides: Dict[str, str]):
	if not overrides:
		yield
		return
	with _LLM_ROUTER_ENV_LOCK:
		previous = {key: os.environ.get(key) for key in overrides}
		try:
			for key, value in overrides.items():
				os.environ[key] = str(value)
			yield
		finally:
			for key, value in previous.items():
				if value is None:
					os.environ.pop(key, None)
				else:
					os.environ[key] = value


def generate_text_via_router(
	prompt: str,
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	**kwargs: Any,
) -> str:
	if generate_text is None:
		raise RuntimeError(LLM_ROUTER_ERROR or "llm_router unavailable")
	effective_provider, effective_model_name, call_options, env_overrides, _ = _prepare_generate_text_call(
		prompt,
		provider=provider,
		model_name=model_name,
		**kwargs,
	)
	with _temporary_env(env_overrides):
		return generate_text(
			prompt=prompt,
			provider=effective_provider or None,
			model_name=effective_model_name,
			**call_options,
		)


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

	effective_provider, effective_model_name, call_options, env_overrides, metadata = _prepare_generate_text_call(
		prompt,
		provider=provider,
		model_name=model_name,
		**kwargs,
	)

	try:
		with _temporary_env(env_overrides):
			text = generate_text(
				prompt=prompt,
				provider=effective_provider or None,
				model_name=effective_model_name,
				**call_options,
			)
	except Exception as exc:
		return with_adapter_metadata(
			{
				"status": "error",
				"text": "",
				"prompt": prompt,
				"provider_name": provider or "",
				"model_name": model_name or "",
				**metadata,
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
			**metadata,
		},
		operation="generate_text",
		backend_available=True,
		implementation_status="available",
	)


__all__ = [
	"generate_text",
	"generate_text_via_router",
	"generate_text_with_metadata",
	"LLM_ROUTER_AVAILABLE",
	"LLM_ROUTER_ERROR",
	"HF_ROUTER_DEFAULT_BASE_URL",
]