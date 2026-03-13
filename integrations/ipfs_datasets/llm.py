from __future__ import annotations

from contextlib import contextmanager
import json
import os
import re
import threading
from typing import Any, Dict, Mapping, Optional

from .loader import import_attr_optional
from .types import with_adapter_metadata


generate_text, _error = import_attr_optional("ipfs_datasets_py.llm_router", "generate_text")
LLM_ROUTER_AVAILABLE = generate_text is not None
LLM_ROUTER_ERROR = _error


HF_ROUTER_DEFAULT_BASE_URL = "https://router.huggingface.co/v1"
HF_ARCH_ROUTER_MODEL = "katanemo/Arch-Router-1.5B"
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


def _coerce_bool(value: Any) -> bool:
	if isinstance(value, bool):
		return value
	if value is None:
		return False
	return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _slugify_route_name(value: str) -> str:
	text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
	return text.strip("_") or "route"


def _normalize_arch_router_routes(value: Any) -> list[Dict[str, str]]:
	routes: list[Dict[str, str]] = []
	if isinstance(value, Mapping):
		for name, route_value in value.items():
			if isinstance(route_value, Mapping):
				model = str(route_value.get("model") or route_value.get("target_model") or "").strip()
				description = str(route_value.get("description") or route_value.get("prompt") or "").strip()
			else:
				model = str(route_value or "").strip()
				description = ""
			if model:
				routes.append({
					"name": _slugify_route_name(str(name)),
					"model": model,
					"description": description or f"Use when the prompt is best handled by {model}.",
				})
		return routes

	if isinstance(value, (list, tuple)):
		for index, item in enumerate(value, start=1):
			if isinstance(item, Mapping):
				model = str(item.get("model") or item.get("target_model") or "").strip()
				name = str(item.get("name") or item.get("route") or model or f"route_{index}").strip()
				description = str(item.get("description") or item.get("prompt") or "").strip()
			elif item is None:
				continue
			else:
				model = str(item).strip()
				name = model
				description = ""
			if model:
				routes.append({
					"name": _slugify_route_name(name),
					"model": model,
					"description": description or f"Use when the prompt is best handled by {model}.",
				})
	return routes


def _extract_arch_router_config(options: Dict[str, Any]) -> Dict[str, Any]:
	nested = options.pop("arch_router", None)
	nested_config = dict(nested) if isinstance(nested, Mapping) else {}
	routes_value = (
		nested_config.pop("routes", None)
		or nested_config.pop("candidates", None)
		or options.pop("arch_router_routes", None)
		or options.pop("routing_candidates", None)
		or options.pop("candidate_models", None)
	)
	routes = _normalize_arch_router_routes(routes_value)
	enabled = _coerce_bool(
		nested_config.pop("enabled", None)
		or nested_config.pop("auto", None)
		or options.pop("arch_router_enabled", None)
		or options.pop("auto_route_model", None)
		or options.pop("auto_model_routing", None)
	)
	if routes and not enabled:
		enabled = True
	return {
		"enabled": enabled,
		"model": str(
			nested_config.pop("model", None)
			or options.pop("arch_router_model", None)
			or _coalesce_env("HF_ARCH_ROUTER_MODEL", "LLM_ROUTER_ARCH_MODEL")
			or HF_ARCH_ROUTER_MODEL
		).strip(),
		"routes": routes,
		"context": str(
			nested_config.pop("context", None)
			or options.pop("arch_router_context", None)
			or ""
		).strip(),
	}


def _strip_code_fences(text: str) -> str:
	stripped = str(text or "").strip()
	if stripped.startswith("```"):
		parts = stripped.splitlines()
		if parts:
			parts = parts[1:]
		while parts and parts[-1].strip().startswith("```"):
			parts = parts[:-1]
		stripped = "\n".join(parts).strip()
	return stripped


def _parse_arch_router_route(text: str) -> str:
	stripped = _strip_code_fences(text)
	try:
		payload = json.loads(stripped)
		if isinstance(payload, Mapping):
			return str(payload.get("route") or payload.get("name") or "").strip()
	except Exception:
		pass
	match = re.search(r'"route"\s*:\s*"([^"]+)"', stripped)
	if match:
		return match.group(1).strip()
	return stripped.strip().strip('"')


def _build_arch_router_prompt(prompt: str, routes: list[Dict[str, str]], context: str = "") -> str:
	route_lines = []
	for route in routes:
		route_lines.append(
			"<route>\n"
			f"<name>{route['name']}</name>\n"
			f"<model>{route['model']}</model>\n"
			f"<description>{route['description']}</description>\n"
			"</route>"
		)
	context_block = f"<context>{context}</context>\n" if context else ""
	return (
		"You are a routing model. Select the single best route for the user request. "
		"Return JSON only in the form {\"route\": \"route_name\"}.\n"
		"<routes>\n"
		+ "\n".join(route_lines)
		+ "\n</routes>\n"
		+ context_block
		+ "<user_request>\n"
		+ prompt.strip()
		+ "\n</user_request>"
	)


def _select_huggingface_arch_route(
	prompt: str,
	*,
	base_url: str,
	api_key: str,
	referer: str,
	app_title: str,
	arch_router_config: Dict[str, Any],
	fallback_model_name: Optional[str],
) -> Dict[str, str]:
	routes = list(arch_router_config.get("routes") or [])
	if not arch_router_config.get("enabled") or not routes or generate_text is None:
		return {}

	routing_prompt = _build_arch_router_prompt(prompt, routes, context=str(arch_router_config.get("context") or ""))
	routing_model = str(arch_router_config.get("model") or HF_ARCH_ROUTER_MODEL).strip() or HF_ARCH_ROUTER_MODEL
	env_overrides = {
		"IPFS_DATASETS_PY_OPENROUTER_BASE_URL": base_url.rstrip("/"),
	}
	if api_key:
		env_overrides["IPFS_DATASETS_PY_OPENROUTER_API_KEY"] = api_key
	if referer:
		env_overrides["OPENROUTER_HTTP_REFERER"] = referer
	if app_title:
		env_overrides["OPENROUTER_APP_TITLE"] = app_title

	with _temporary_env(env_overrides):
		raw_response = generate_text(
			prompt=routing_prompt,
			provider="openrouter",
			model_name=routing_model,
			temperature=0,
		)

	selected_route = _slugify_route_name(_parse_arch_router_route(raw_response))
	for route in routes:
		if route["name"] == selected_route:
			return {
				"arch_router_selected_route": selected_route,
				"arch_router_selected_model": route["model"],
				"arch_router_model_name": routing_model,
				"arch_router_status": "selected",
			}

	return {
		"arch_router_selected_route": selected_route,
		"arch_router_selected_model": str(fallback_model_name or ""),
		"arch_router_model_name": routing_model,
		"arch_router_status": "fallback",
	}


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
	prompt: str,
	provider: Optional[str],
	model_name: Optional[str],
	options: Dict[str, Any],
) -> tuple[str, Optional[str], Dict[str, Any], Dict[str, str], Dict[str, Any]]:
	call_options = dict(options)
	headers = _normalize_headers(call_options.pop("headers", None))
	arch_router_config = _extract_arch_router_config(call_options)
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
	route_selection = _select_huggingface_arch_route(
		prompt,
		base_url=base_url,
		api_key=api_key,
		referer=referer,
		app_title=app_title,
		arch_router_config=arch_router_config,
		fallback_model_name=effective_model_name,
	)
	selected_model_name = str(route_selection.get("arch_router_selected_model") or "").strip()
	if selected_model_name:
		effective_model_name = selected_model_name

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
		**route_selection,
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
		return _build_huggingface_router_request(prompt, provider, model_name, call_options)
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