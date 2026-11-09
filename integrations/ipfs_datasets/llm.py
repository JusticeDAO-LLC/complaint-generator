from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import hmac
import importlib
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid
from typing import Any, Dict, Mapping, Optional

from integrations.ipfs_accelerate.routers import (
	INFERENCE_OWNER,
	PINNED_GROK_CANARY_PROMPT,
	PINNED_GROK_MODEL,
	PINNED_GROK_PROVIDER,
	interpret_canary_dispatch,
	load_llm_symbols,
	load_observed_llm_symbols,
	normalize_accelerate_provider,
	pinned_grok47_adapter_binding,
	pinned_grok47_canary_kwargs,
	pinned_grok47_dispatch_kwargs,
	development_campaign_authorizes_user_complaint_egress,
	unpinned_grok_route_reason,
	vetted_route_observation,
)
from .types import with_adapter_metadata


logger = logging.getLogger(__name__)


generate_text, get_last_generation_trace, _error = load_llm_symbols()
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


def _env_value(name: str, overrides: Optional[Mapping[str, str]] = None) -> str:
	if overrides is not None:
		value = str(overrides.get(name, "") or "").strip()
		if value:
			return value
	return os.getenv(name, "").strip()


def _resolve_hf_token(env_overrides: Optional[Mapping[str, str]] = None) -> str:
	token = (
		_env_value("IPFS_DATASETS_PY_HF_API_TOKEN", env_overrides)
		or _env_value("HUGGINGFACEHUB_API_TOKEN", env_overrides)
		or _env_value("HF_TOKEN", env_overrides)
		or _env_value("HUGGINGFACE_HUB_TOKEN", env_overrides)
		or _env_value("HUGGINGFACE_API_KEY", env_overrides)
		or _env_value("HUGGINGFACE_API_TOKEN", env_overrides)
		or _env_value("HF_API_TOKEN", env_overrides)
	)
	if token:
		return token

	try:
		from ipfs_datasets_py.mcp_server.secrets_vault import get_secrets_vault

		vault = get_secrets_vault()
		for name in (
			"IPFS_DATASETS_PY_HF_API_TOKEN",
			"HUGGINGFACEHUB_API_TOKEN",
			"HF_TOKEN",
			"HUGGINGFACE_HUB_TOKEN",
			"HUGGINGFACE_API_KEY",
			"HUGGINGFACE_API_TOKEN",
			"HF_API_TOKEN",
		):
			resolved = str(vault.get(name) or "").strip()
			if resolved:
				return resolved
	except Exception:
		# The vault is one of several supported credential sources, so its
		# failure must not prevent keyring or Hugging Face CLI credentials from
		# being used. Keep that fallback observable without logging secret values.
		logger.warning(
			"Could not resolve a Hugging Face token from the ipfs_datasets_py "
			"secrets vault; trying the keyring and Hugging Face CLI fallbacks",
			exc_info=True,
		)

	try:
		import keyring  # type: ignore

		for name in (
			"IPFS_DATASETS_PY_HF_API_TOKEN",
			"HUGGINGFACEHUB_API_TOKEN",
			"HF_TOKEN",
			"HUGGINGFACE_HUB_TOKEN",
			"HUGGINGFACE_API_KEY",
			"HUGGINGFACE_API_TOKEN",
			"HF_API_TOKEN",
		):
			resolved = str(keyring.get_password("ipfs_datasets_py", name) or "").strip()
			if resolved:
				return resolved
	except Exception:
		# A broken or unconfigured keyring backend must not prevent the
		# Hugging Face client fallback below, but the degraded credential lookup
		# must remain observable to operators.
		logger.warning(
			"Hugging Face token lookup through keyring failed; "
			"falling back to the Hugging Face client token cache",
			exc_info=True,
		)

	try:
		hub = importlib.import_module("huggingface_hub")
		getter = getattr(hub, "get_token", None)
		resolved = getter() if callable(getter) else ""
		if resolved is not None and str(resolved).strip():
			return str(resolved).strip()
	except Exception:
		return ""
	return ""


def _resolve_openai_api_key(env_overrides: Optional[Mapping[str, str]] = None) -> str:
	token = (
		_env_value("OPENAI_API_KEY", env_overrides)
		or _env_value("OPENAI_KEY", env_overrides)
		or _env_value("OPENAI_TOKEN", env_overrides)
	)
	if token:
		return token

	try:
		from ipfs_datasets_py.mcp_server.secrets_vault import get_secrets_vault

		vault = get_secrets_vault()
		for name in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
			resolved = str(vault.get(name) or "").strip()
			if resolved:
				return resolved
	except Exception:
		# The vault is optional and keyring/common-file lookup can still resolve
		# the key. Surface the degraded lookup without exposing credential values.
		logger.warning(
			"Could not resolve an OpenAI API key from the ipfs_datasets_py "
			"secrets vault; trying the keyring and common-file fallbacks",
			exc_info=True,
		)

	try:
		import keyring  # type: ignore

		for name in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
			resolved = str(keyring.get_password("ipfs_datasets_py", name) or "").strip()
			if resolved:
				return resolved
	except Exception:
		# Keyring is optional and common local configuration may still provide
		# the key. Preserve that fallback while making backend failures visible.
		logger.warning(
			"OpenAI API-key lookup through keyring failed; "
			"falling back to common local configuration files",
			exc_info=True,
		)

	try:
		engine_env = importlib.import_module("ipfs_datasets_py.utils.engine_env")
		getter = getattr(engine_env, "_openai_key_from_common_files", None)
		resolved = getter() if callable(getter) else ""
		if resolved is not None and str(resolved).strip():
			return str(resolved).strip()
	except Exception:
		return ""
	return ""


def _provider_preflight_error(
	*,
	effective_provider: str,
	metadata: Mapping[str, Any],
	env_overrides: Mapping[str, str],
) -> str:
	provider_key = str(effective_provider or "").strip().lower()
	requested_provider = str(metadata.get("requested_provider_name") or "").strip().lower()
	router_base_url = str(metadata.get("router_base_url") or "").strip().lower()

	if provider_key == "openrouter":
		is_hf_router_request = requested_provider in HF_ROUTER_PROVIDER_ALIASES or (
			requested_provider in {"hf", "huggingface"} and "huggingface.co" in router_base_url
		)
		if is_hf_router_request:
			hf_token = _resolve_hf_token(env_overrides)
			if not hf_token:
				return (
					"Hugging Face router unavailable: missing token. "
					"Set HF_TOKEN, HUGGINGFACE_HUB_TOKEN, HUGGINGFACE_API_KEY, or HF_API_TOKEN."
				)
		openrouter_key = _env_value("IPFS_DATASETS_PY_OPENROUTER_API_KEY", env_overrides) or _env_value("OPENROUTER_API_KEY")
		if not openrouter_key:
			return (
				"OpenRouter unavailable: missing API key. "
				"Set OPENROUTER_API_KEY or IPFS_DATASETS_PY_OPENROUTER_API_KEY."
			)

	if provider_key == "openai":
		openai_key = _resolve_openai_api_key(env_overrides)
		if not openai_key:
			return "OpenAI unavailable: missing API key. Set OPENAI_API_KEY, store one in the ipfs_datasets_py vault/keyring, or log in with a compatible local OpenAI CLI config."

	if provider_key == "anthropic":
		anthropic_key = _env_value("ANTHROPIC_API_KEY", env_overrides)
		if not anthropic_key:
			return "Anthropic unavailable: missing API key. Set ANTHROPIC_API_KEY."

	if provider_key in {"gemini", "gemini_cli", "gemini_py"}:
		gemini_key = (
			_env_value("GEMINI_API_KEY", env_overrides)
			or _env_value("GOOGLE_API_KEY", env_overrides)
		)
		if provider_key == "gemini" and not gemini_key:
			return "Gemini unavailable: missing API key. Set GEMINI_API_KEY or GOOGLE_API_KEY."

	if provider_key in {"codex", "codex_cli"} and shutil.which("codex") is None:
		return "Codex CLI unavailable: codex binary not found on PATH."

	if provider_key == PINNED_GROK_PROVIDER:
		model = str(metadata.get("effective_model_name") or "").strip()
		if model != PINNED_GROK_MODEL:
			return unpinned_grok_route_reason(provider_key, model) or (
				"Grok CLI unavailable: model_name must be exactly grok-4.7."
			)

	return ""


def grok_cli_binary_present() -> bool:
	"""PATH-only discovery. Operator home bins are not treated as available."""

	return shutil.which("grok") is not None


def grok_cli_auth_present() -> bool:
	"""Report whether auth is configured. Never read or return secret bytes."""

	for name in (
		"XAI_API_KEY",
		"ipfs_accelerate_py_XAI_API_KEY",
		"IPFS_ACCELERATE_PY_XAI_API_KEY",
		"IPFS_DATASETS_PY_XAI_API_KEY",
		"GROK_AUTH_PROVIDER_COMMAND",
	):
		if os.getenv(name, "").strip():
			return True
	candidates = []
	configured_home = os.getenv("GROK_HOME", "").strip()
	if configured_home:
		candidates.append(Path(configured_home).expanduser() / "auth.json")
	candidates.append(Path.home() / ".grok" / "auth.json")
	for path in candidates:
		try:
			if path.is_file() and path.stat().st_size > 0:
				return True
		except OSError:
			continue
	return False


def _new_request_id() -> str:
	return uuid.uuid4().hex


# One schema family for question proposals and extracted-fact candidates.
# Spans are exact UTF-8 byte offsets into the original source, not code points.
INTAKE_REQUEST_SCHEMA_VERSION = "intake_request_v1"
INTAKE_REQUEST_SCHEMA_NAME = "intake_request_v1"
INTAKE_OPERATIONS = frozenset({"propose_questions", "extract_facts"})
INTAKE_FACT_FIELDS = frozenset({"party", "date", "location", "act", "harm"})
INTAKE_MAX_QUESTIONS = 8
INTAKE_MAX_FACTS = 16
INTAKE_MAX_OUTPUT_BYTES = 262144
_INTAKE_REF = re.compile(r"^[A-Za-z0-9_.:-]{1,128}\Z")
_REQUEST_ID = re.compile(r"^[0-9a-f]{32}\Z")

INTAKE_REQUEST_OBJECT_SCHEMA: Dict[str, Any] = {
	"type": "object",
	"additionalProperties": False,
	"required": ["schema_version", "operation", "request_id", "questions", "facts"],
	"properties": {
		"schema_version": {"type": "string", "const": INTAKE_REQUEST_SCHEMA_VERSION},
		"operation": {"type": "string", "enum": ["propose_questions", "extract_facts"]},
		"request_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
		"questions": {
			"type": "array",
			"maxItems": INTAKE_MAX_QUESTIONS,
			"items": {
				"type": "object",
				"additionalProperties": False,
				"required": ["question_id", "prompt", "target_ref"],
				"properties": {
					"question_id": {"type": "string", "minLength": 1, "maxLength": 64},
					"prompt": {"type": "string", "minLength": 1, "maxLength": 500},
					"target_ref": {"type": "string", "minLength": 1, "maxLength": 128},
				},
			},
		},
		"facts": {
			"type": "array",
			"maxItems": INTAKE_MAX_FACTS,
			"items": {
				"type": "object",
				"additionalProperties": False,
				"required": ["field", "value", "source_start", "source_end", "target_ref"],
				"properties": {
					"field": {"type": "string", "enum": ["party", "date", "location", "act", "harm"]},
					"value": {"type": "string", "minLength": 1, "maxLength": 500},
					"source_start": {"type": "integer", "minimum": 0},
					"source_end": {"type": "integer", "minimum": 0},
					"target_ref": {"type": "string", "minLength": 1, "maxLength": 128},
				},
			},
		},
	},
}


class IntakeContractError(ValueError):
	"""Schema or source-span rejection. The message is a stable code, never model text."""

	def __init__(self, code: str = "malformed"):
		self.code = code if code in {"malformed", "identity", "span"} else "malformed"
		super().__init__(self.code)


def pinned_hook_inference_route() -> Dict[str, Any]:
	"""Pinned Grok route for declared hook purposes. Fallbacks stay off."""

	pin = pinned_grok47_dispatch_kwargs()
	if pin.get("provider") != PINNED_GROK_PROVIDER or pin.get("model_name") != PINNED_GROK_MODEL:
		raise RuntimeError("unpinned_hook_route")
	if pin.get("allow_local_fallback") is not False or pin.get("allow_cross_provider_fallback") is not False:
		raise RuntimeError("hook_fallback_enabled")
	return {
		"inference_owner": INFERENCE_OWNER,
		"router": INFERENCE_OWNER,
		"provider": PINNED_GROK_PROVIDER,
		"model": PINNED_GROK_MODEL,
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
		"tools_allowed": False,
		"may_mark_requirements_satisfied": False,
	}


def _route_identity_slot(slot: Any) -> Dict[str, str]:
	source = slot if isinstance(slot, Mapping) else {}

	def text(key: str) -> str:
		value = source.get(key, "")
		if type(value) is not str:
			return ""
		cleaned = value.strip()
		if len(cleaned) > 128 or any(ord(char) < 32 for char in cleaned):
			return ""
		return cleaned

	return {"router": text("router"), "provider": text("provider"), "model": text("model"), "build": text("build")}


def route_identity_diagnostics(
	*,
	requested: Any,
	selected: Any,
	observed: Any,
	transport_kind: str,
	native_observation_bound: bool = False,
	evidence_class: str = "",
) -> Dict[str, Any]:
	"""Keep requested, selected, and observed identity in separate slots.

	A synthetic transport cannot verify a live model or build, even when the
	payload copies the pinned names or claims native evidence.
	"""

	kind = transport_kind if type(transport_kind) is str else ""
	requested_slot = _route_identity_slot(requested)
	selected_slot = _route_identity_slot(selected)
	observed_slot = _route_identity_slot(observed)
	live_model = False
	live_build = False
	if kind == "native_observation" and native_observation_bound is True and evidence_class == "native_final_end_model_usage":
		live_model = (
			observed_slot["provider"] == PINNED_GROK_PROVIDER
			and observed_slot["model"] == PINNED_GROK_MODEL
			and observed_slot["router"] == INFERENCE_OWNER
		)
		live_build = live_model and observed_slot["build"] in {PINNED_GROK_MODEL, "grok-4.7-build"}
	if kind == "synthetic" or kind != "native_observation":
		live_model = False
		live_build = False
	return {
		"requested": requested_slot,
		"selected": selected_slot,
		"observed": observed_slot,
		"transport_kind": "synthetic" if kind == "synthetic" else (kind or "unspecified"),
		"live_model_identity_verified": live_model,
		"live_build_identity_verified": live_build,
		"inference_owner": INFERENCE_OWNER,
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
	}


def _declared_purpose_short_circuit(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
	"""Local and undeclared purpose labels never enter the provider call."""

	if "inference_purpose" not in kwargs:
		return None
	purpose = kwargs.pop("inference_purpose")
	from mediator.hook_runtime import is_local_only_purpose, is_model_purpose

	if is_local_only_purpose(purpose):
		return {
			"status": "local_only",
			"text": "",
			"dispatch": "none",
			"model_dispatched": False,
			"inference_purpose": purpose,
			"live_canary": False,
			"live_model_identity_verified": False,
			"failure_kind": "",
			"error": "",
			"prompt_logged": False,
			"provider_name": "",
			"model_name": "",
		}
	if is_model_purpose(purpose):
		return {
			"status": "unavailable",
			"text": "",
			"dispatch": "none",
			"model_dispatched": False,
			"inference_purpose": purpose,
			"live_canary": False,
			"live_model_identity_verified": False,
			"failure_kind": "use_declared_hook_boundary",
			"error": "use_declared_hook_boundary",
			"prompt_logged": False,
			"provider_name": PINNED_GROK_PROVIDER,
			"model_name": PINNED_GROK_MODEL,
		}
	return {
		"status": "unavailable",
		"text": "",
		"dispatch": "none",
		"model_dispatched": False,
		"inference_purpose": str(purpose) if type(purpose) is str else "",
		"live_canary": False,
		"live_model_identity_verified": False,
		"failure_kind": "undeclared_purpose",
		"error": "undeclared_purpose",
		"prompt_logged": False,
		"provider_name": "",
		"model_name": "",
	}


def intake_request_response_format() -> Dict[str, Any]:
	"""Fixed schema description; typed streaming enforces it on the host."""

	return {
		"type": "json_schema",
		"json_schema": {
			"name": INTAKE_REQUEST_SCHEMA_NAME,
			"strict": True,
			"schema": deepcopy(INTAKE_REQUEST_OBJECT_SCHEMA),
		},
	}


def _reject_duplicate_keys(items):
	parsed: Dict[str, Any] = {}
	for key, value in items:
		if key in parsed:
			raise IntakeContractError("malformed")
		parsed[key] = value
	return parsed


def _reject_nonfinite(_value):
	raise IntakeContractError("malformed")


def classify_router_failure(exc: BaseException) -> str:
	"""Map a provider failure to one stable kind. The kind never echoes the exception body."""

	name = type(exc).__name__.lower()
	if isinstance(exc, TimeoutError) or name in {"timeoutexpired", "timeouterror"}:
		return "timeout"
	if "cancel" in name:
		return "cancelled"
	text = str(exc).lower()
	if any(token in text for token in ("insufficient_quota", "quota exceeded", "quota_exhausted", "rate limit")):
		return "quota"
	if any(token in text for token in ("does not match the requested schema", "structured output", "malformed json", "duplicate fields")):
		return "malformed"
	return "unavailable"


def _normalize_intake_targets(raw: Any) -> frozenset[str]:
	"""Freeze host authority; a model-selected reference never grants it."""
	if type(raw) not in (tuple, list, set, frozenset) or len(raw) > 256:
		raise IntakeContractError("identity")
	if any(type(item) is not str or _INTAKE_REF.fullmatch(item) is None for item in raw):
		raise IntakeContractError("identity")
	if len(set(raw)) != len(raw):
		raise IntakeContractError("identity")
	return frozenset(raw)


def _host_validate_intake_tree(payload: Any, *, request_id: str, operation: str, source_text: str,
                              allowed_target_refs=None) -> Dict[str, Any]:
	targets = _normalize_intake_targets(allowed_target_refs)
	if type(operation) is not str or type(source_text) is not str:
		raise IntakeContractError("identity")
	if type(payload) is not dict:
		raise IntakeContractError("malformed")
	allowed = {"schema_version", "operation", "request_id", "questions", "facts"}
	if set(payload) != allowed:
		raise IntakeContractError("malformed")
	if payload.get("schema_version") != INTAKE_REQUEST_SCHEMA_VERSION:
		raise IntakeContractError("malformed")
	if type(payload.get("operation")) is not str or payload["operation"] not in INTAKE_OPERATIONS or payload["operation"] != operation:
		raise IntakeContractError("identity")
	if type(payload.get("request_id")) is not str or payload.get("request_id") != request_id or _REQUEST_ID.fullmatch(request_id) is None:
		raise IntakeContractError("identity")
	questions = payload.get("questions")
	facts = payload.get("facts")
	if type(questions) is not list or type(facts) is not list:
		raise IntakeContractError("malformed")
	if len(questions) > INTAKE_MAX_QUESTIONS or len(facts) > INTAKE_MAX_FACTS:
		raise IntakeContractError("malformed")
	if operation == "propose_questions" and facts:
		raise IntakeContractError("malformed")
	if operation == "extract_facts" and questions:
		raise IntakeContractError("malformed")
	try:
		source = source_text.encode("utf-8")
	except UnicodeError:
		raise IntakeContractError("span") from None
	clean_questions = []
	question_ids, question_targets = set(), set()
	for item in questions:
		if type(item) is not dict or set(item) != {"question_id", "prompt", "target_ref"}:
			raise IntakeContractError("malformed")
		question_id = item.get("question_id")
		prompt = item.get("prompt")
		target = item.get("target_ref")
		if type(question_id) is not str or type(prompt) is not str or type(target) is not str:
			raise IntakeContractError("malformed")
		try:
			question_id.encode("utf-8")
			prompt.encode("utf-8")
		except UnicodeError:
			raise IntakeContractError("malformed") from None
		if not (1 <= len(question_id) <= 64 and 1 <= len(prompt) <= 500 and _INTAKE_REF.fullmatch(target)) or target not in targets:
			raise IntakeContractError("malformed")
		if question_id in question_ids or target in question_targets:
			raise IntakeContractError("malformed")
		question_ids.add(question_id)
		question_targets.add(target)
		clean_questions.append({"question_id": question_id, "prompt": prompt, "target_ref": target})
	clean_facts = []
	for item in facts:
		if type(item) is not dict or set(item) != {"field", "value", "source_start", "source_end", "target_ref"}:
			raise IntakeContractError("span")
		field = item.get("field")
		value = item.get("value")
		start = item.get("source_start")
		end = item.get("source_end")
		target = item.get("target_ref")
		if type(field) is not str or field not in INTAKE_FACT_FIELDS or type(value) is not str or type(target) is not str:
			raise IntakeContractError("span")
		if type(start) is not int or type(end) is not int or isinstance(start, bool) or isinstance(end, bool):
			raise IntakeContractError("span")
		if not (1 <= len(value) <= 500 and _INTAKE_REF.fullmatch(target)) or target not in targets:
			raise IntakeContractError("span")
		if start < 0 or end < start or end > len(source):
			raise IntakeContractError("span")
		try:
			excerpt = source[start:end].decode("utf-8")
		except UnicodeDecodeError:
			raise IntakeContractError("span") from None
		if excerpt != value:
			raise IntakeContractError("span")
		clean_facts.append({
			"field": field,
			"value": value,
			"source_start": start,
			"source_end": end,
			"target_ref": target,
		})
	return {
		"schema_version": INTAKE_REQUEST_SCHEMA_VERSION,
		"operation": operation,
		"request_id": request_id,
		"questions": clean_questions,
		"facts": clean_facts,
	}


def parse_intake_request(raw: str, *, request_id: str, operation: str, source_text: str, allowed_target_refs=None) -> Dict[str, Any]:
	"""Validate one model payload. Fenced prose and regex extraction are not accepted."""

	_normalize_intake_targets(allowed_target_refs)
	try:
		if type(raw) is not str or len(raw.encode("utf-8")) > INTAKE_MAX_OUTPUT_BYTES:
			raise IntakeContractError("malformed")
	except (UnicodeError, RecursionError):
		raise IntakeContractError("malformed") from None
	text = raw.strip()
	if not text or text[0] != "{":
		raise IntakeContractError("malformed")
	try:
		payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_nonfinite)
	except IntakeContractError:
		raise
	except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
		raise IntakeContractError("malformed") from None
	return _host_validate_intake_tree(payload, request_id=request_id, operation=operation, source_text=source_text, allowed_target_refs=allowed_target_refs)


def _pop_host_metadata(kwargs: Dict[str, Any]) -> Dict[str, Any]:
	"""Keep correlation and intake controls out of the provider allowlist."""

	request_id = kwargs.pop("request_id", None)
	if request_id is None:
		request_id = kwargs.pop("intake_request_id", None)
	else:
		kwargs.pop("intake_request_id", None)
	operation = kwargs.pop("intake_operation", None)
	source_text = kwargs.pop("intake_source_text", None)
	if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
		request_id = _new_request_id()
	return {
		"request_id": request_id,
		"intake_operation": operation,
		"intake_source_text": source_text if type(source_text) is str else "",
		"intake_target_refs": kwargs.pop("intake_target_refs", None),
		"max_output_bytes": kwargs.pop("max_output_bytes", INTAKE_MAX_OUTPUT_BYTES),
	}


# Only literal first-party preflight messages may enter a public receipt.
# Partial prompt echoes and short credentials cannot be detected by length or
# comparison with the full prompt, so arbitrary exception text is never copied.
_PUBLIC_PREFLIGHT_ERRORS = frozenset({
	"Hugging Face router unavailable: missing token. Set HF_TOKEN, HUGGINGFACE_HUB_TOKEN, HUGGINGFACE_API_KEY, or HF_API_TOKEN.",
	"OpenRouter unavailable: missing API key. Set OPENROUTER_API_KEY or IPFS_DATASETS_PY_OPENROUTER_API_KEY.",
	"OpenAI unavailable: missing API key. Set OPENAI_API_KEY, store one in the ipfs_datasets_py vault/keyring, or log in with a compatible local OpenAI CLI config.",
	"Anthropic unavailable: missing API key. Set ANTHROPIC_API_KEY.",
	"Gemini unavailable: missing API key. Set GEMINI_API_KEY or GOOGLE_API_KEY.",
	"Codex CLI unavailable: codex binary not found on PATH.",
	"Grok CLI unavailable: model_name must be exactly grok-4.7.",
})


def _public_error(message: str, prompt: str) -> str:
	"""Preserve actionable literal diagnostics; drop all dynamic error bodies."""

	return message if type(message) is str and message in _PUBLIC_PREFLIGHT_ERRORS else "provider_exception"


def _apply_pinned_grok_options(provider: str, call_options: Dict[str, Any]) -> None:
	if str(provider or "").strip() != PINNED_GROK_PROVIDER:
		return
	call_options.update(
		{
			"allow_local_fallback": False,
			"allow_cross_provider_fallback": False,
		}
	)


def _redacted_router_trace(trace: Any, *, request_id: str, requested_provider: str, requested_model: str) -> Dict[str, Any]:
	"""Copy route identity only. Prompt, credentials, and raw errors stay out."""

	fields = vetted_route_observation(
		trace if isinstance(trace, Mapping) else None,
		requested_provider=requested_provider,
		requested_model=requested_model,
	)
	fields["request_id"] = request_id
	fields["router_version"] = ""
	fields["configured_provider_name"] = requested_provider
	fields["configured_model_name"] = requested_model
	fields["inference_owner"] = INFERENCE_OWNER
	fields["prompt_logged"] = False
	return fields


def _route_receipt(
	*,
	requested_provider: str,
	requested_model: str,
	observe: bool,
	request_id: str = "",
) -> Dict[str, Any]:
	trace: Any = None
	if observe and callable(get_last_generation_trace):
		try:
			trace = get_last_generation_trace()
		except Exception:
			trace = None
	if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
		request_id = _new_request_id()
	return _redacted_router_trace(
		trace,
		request_id=request_id,
		requested_provider=requested_provider,
		requested_model=requested_model,
	)


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
	except json.JSONDecodeError:
		# Router models do not always honor the JSON-only instruction. Preserve
		# the tolerant regex/plain-text fallbacks only for malformed JSON; parser
		# defects and unexpected runtime failures must remain visible to callers.
		payload = None
	if isinstance(payload, Mapping):
		return str(payload.get("route") or payload.get("name") or "").strip()
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


# Set while a private complaint turn is being prepared. Architecture-router
# classification must not receive that prompt, and a refusal must not fall
# through to another cloud model.
_BLOCK_ARCH_CLASSIFICATION: ContextVar[bool] = ContextVar(
	"complaint_block_arch_classification",
	default=False,
)
ARCH_CLASSIFICATION_BLOCKED = "privacy_denied:architecture_classification_blocked"
MINIMAL_TURN_SCHEMA = "complaint-minimal-turn-prompt/v1"
PRIVATE_TURN_TIMEOUT_SECONDS = 60.0
_PRIVATE_REQUEST_CACHE: list[Dict[str, Any]] = []
_PRIVATE_REQUEST_TRACES: list[Dict[str, Any]] = []
_PRIVATE_REQUEST_LOCK = threading.Lock()


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
	if _BLOCK_ARCH_CLASSIFICATION.get():
		# Do not copy `prompt` into the route receipt or hand it to a model.
		return {
			"arch_router_status": "refused",
			"arch_router_selected_route": "",
			"arch_router_selected_model": "",
			"arch_router_model_name": "",
			"arch_router_error": ARCH_CLASSIFICATION_BLOCKED,
		}
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

	api_key = _pop_first_string(call_options, "api_key", "token", "access_token") or bearer_token or _resolve_hf_token()
	referer = _pop_first_string(call_options, "http_referer", "referer") or headers.pop("HTTP-Referer", "") or headers.pop("Referer", "")
	app_title = _pop_first_string(call_options, "app_title") or headers.pop("X-Title", "")
	bill_to = _pop_first_string(call_options, "bill_to", "hf_bill_to") or headers.pop("X-HF-Bill-To", "") or _coalesce_env(
		"IPFS_DATASETS_PY_HF_BILL_TO",
		"HUGGINGFACE_BILL_TO",
		"HF_BILL_TO",
		"HF_ORGANIZATION",
		"HUGGINGFACE_ORG",
		"OPENROUTER_HF_BILL_TO",
	)

	effective_model_name = model_name or _pop_first_string(call_options, "route_model", "fallback_model") or _coalesce_env(
		"LLM_ROUTER_FALLBACK_MODEL",
		"IPFS_DATASETS_PY_OPENROUTER_MODEL",
		"IPFS_DATASETS_PY_LLM_MODEL",
	) or None
	try:
		route_selection = _select_huggingface_arch_route(
			prompt,
			base_url=base_url,
			api_key=api_key,
			referer=referer,
			app_title=app_title,
			arch_router_config=arch_router_config,
			fallback_model_name=effective_model_name,
		)
	except Exception as exc:
		route_selection = {
			"arch_router_status": "fallback_error",
			"arch_router_selected_route": "",
			"arch_router_selected_model": str(effective_model_name or ""),
			"arch_router_model_name": str(arch_router_config.get("model") or HF_ARCH_ROUTER_MODEL),
			"arch_router_error": str(exc),
		}
	if str(route_selection.get("arch_router_status") or "") == "refused":
		# Classification refused. Do not keep a fallback cloud model or the
		# original prompt as an outbound request.
		return "", None, {}, {}, {
			"requested_provider_name": provider or "",
			"effective_provider_name": "",
			"effective_model_name": "",
			"router_base_url": "",
			"dispatch": "none",
			**route_selection,
		}
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
	if bill_to:
		env_overrides["OPENROUTER_HF_BILL_TO"] = bill_to

	metadata = {
		"requested_provider_name": provider or "",
		"effective_provider_name": "openrouter",
		"effective_model_name": str(effective_model_name or ""),
		"router_base_url": base_url.rstrip("/"),
		"hf_bill_to": bill_to,
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
	mapped_provider = normalize_accelerate_provider(provider)
	metadata = {
		"requested_provider_name": provider or "",
		"effective_provider_name": mapped_provider or "",
		"effective_model_name": str(model_name or ""),
		"router_base_url": "",
	}
	_apply_pinned_grok_options(str(mapped_provider or ""), call_options)
	return str(mapped_provider or ""), model_name, call_options, {}, metadata


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


def _intake_provider_prompt(prompt, *, request_id, operation, source_text, targets):
	"""Serialize the same fixed host contract for every typed entrypoint."""
	return json.dumps({"schema_version": INTAKE_REQUEST_SCHEMA_VERSION,
		"operation": operation, "request_id": request_id, "source_text": source_text,
		"allowed_target_refs": sorted(targets),
		"schema": intake_request_response_format()["json_schema"]["schema"],
		"instructions": "Return only one JSON object matching the schema and exact request identity. "
			"Use only the supplied host targets and exact source spans. Do not invent facts.",
		"prompt": prompt}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class _IntakeGenerationCancelled(BaseException):
	"""Propagate through native capture's Exception-only callback boundary."""


def _generate_intake_with_metadata(prompt, *, provider, model_name, request_id, operation,
                                  source_text, allowed_target_refs, privacy_context, options,
                                  max_output_bytes=INTAKE_MAX_OUTPUT_BYTES, cancel_event=None,
                                  progress_callback=None):
	"""One private typed generation through the owned native streaming API.

	Schema is enforced on the host after native invocation evidence. NativeA's
	streaming API cannot accept response_format. Its own finalizer owns the
	direct child; this function has no PID registry or abandoned worker thread.
	"""
	base = {"text": "", "request_id": request_id, "provider_name": PINNED_GROK_PROVIDER,
		"model_name": PINNED_GROK_MODEL, "configured_provider_name": PINNED_GROK_PROVIDER,
		"configured_model_name": PINNED_GROK_MODEL, "inference_owner": INFERENCE_OWNER,
		"observed_provider_name": "", "observed_model_name": "", "router_version": "",
		"route_observation": "unverified", "invocation_bound": False,
		"resumable": True, "intake_complete": False, "prompt_logged": False, "live_canary": False,
		"schema_enforcement": "host_fixed_intake_schema", "native_response_format_supported": False}
	attempted = False

	def fail(kind):
		return with_adapter_metadata({**base, "status": kind, "failure_kind": kind,
			"error": "intake_generation_" + kind, "dispatch": "attempted" if attempted else "none"},
			operation="generate_text", backend_available=True, implementation_status="available")

	try:
		targets = _normalize_intake_targets(allowed_target_refs)
		if (type(operation) is not str or operation not in INTAKE_OPERATIONS
			or type(source_text) is not str or type(request_id) is not str
			or _REQUEST_ID.fullmatch(request_id) is None
			or type(max_output_bytes) is not int or not 1 <= max_output_bytes <= INTAKE_MAX_OUTPUT_BYTES):
			return fail("malformed")
		if type(prompt) is not str:
			return fail("malformed")
		source_text.encode("utf-8")
		prompt.encode("utf-8")
		timeout = options.get("timeout", 60.0)
		if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
			return fail("malformed")
		deadline = time.monotonic() + min(float(timeout), 60.0)
		if privacy_context is None or _privacy_context_block_reason(privacy_context,
			provider=provider, model_name=model_name, options=options):
			return fail("privacy_denied")
		if provider != PINNED_GROK_PROVIDER or model_name != PINNED_GROK_MODEL:
			return fail("privacy_denied")
		if cancel_event is not None and cancel_event.is_set():
			return fail("cancelled")
		generate, result_type, observation_type = load_observed_llm_symbols()
		if (not callable(generate) or not isinstance(result_type, type) or not isinstance(observation_type, type)
				or pinned_grok47_adapter_binding(generate) is None):
			return fail("route_unverified")
		provider_prompt = _intake_provider_prompt(prompt, request_id=request_id,
			operation=operation, source_text=source_text, targets=targets)
		remaining = deadline - time.monotonic()
		if remaining <= 0:
			return fail("timeout")
		try:
			sealed = intercept_final_provider_request({
				"schema": PROVIDER_EGRESS_SCHEMA,
				"provider": PINNED_GROK_PROVIDER,
				"model": PINNED_GROK_MODEL,
				"prompt": provider_prompt,
				"timeout_seconds": remaining,
				"allow_local_fallback": False,
				"allow_cross_provider_fallback": False,
				"request_id": request_id,
			})
		except RuntimeError:
			return fail("privacy_denied")
		provider_prompt = sealed["prompt"]

		def progress(_summary):
			if cancel_event is not None and cancel_event.is_set():
				raise _IntakeGenerationCancelled()
			if callable(progress_callback):
				try:
					progress_callback({"phase": "provider_progress", "router": INFERENCE_OWNER})
				except Exception:
					pass

		# Only fixed host-owned controls follow the original per-case gate.
		call_options = {k: v for k, v in options.items() if k in _PRIVATE_GENERATION_OPTIONS
			and k not in {"response_format", "timeout", "grok_max_turns"}}
		attempted = True
		result = generate(prompt=provider_prompt, provider=PINNED_GROK_PROVIDER, model_name=PINNED_GROK_MODEL,
			observation_request_id=request_id, **{**call_options, "timeout": remaining,
			"allow_local_fallback": False, "allow_cross_provider_fallback": False,
			"grok_cli_cmd": ["grok"], "grok_tools": "read_file",
			"grok_disallowed_tools": "read_file,search_tool,use_tool", "grok_permission_mode": "dontAsk",
			"grok_max_turns": 1, "grok_stream_progress": True, "grok_progress_callback": progress,
			"usage_cancel_event": cancel_event})
		if cancel_event is not None and cancel_event.is_set():
			return fail("cancelled")
		if time.monotonic() >= deadline:
			return fail("timeout")
		if type(result) is not result_type or type(result.observation) is not observation_type:
			return fail("route_unverified")
		obs = result.observation
		if (obs.request_id != request_id or type(obs.invocation_id) is not str
			or re.fullmatch(r"[0-9a-f]{32}", obs.invocation_id) is None
			or type(obs.native_dispatch_count) is not int or obs.native_dispatch_count != 1
			or obs.invocation_scope != "current_call" or obs.schema != "native-grok-invocation-observation@1"
			or obs.observation_only is not True or obs.raw_provider_data_exported is not False
			or type(obs.process_returncode) is not int or obs.process_returncode != 0
			or obs.stream_complete is not True or obs.wire_model_observed is not True
			or obs.evidence_class != "native_final_end_model_usage"):
			return fail("route_unverified")
		if (obs.selected_provider_name != PINNED_GROK_PROVIDER or obs.selected_model_name != PINNED_GROK_MODEL
			or obs.provider_reported_model not in {PINNED_GROK_MODEL, "grok-4.7-build"}):
			return fail("substitution_refused")
		if type(result.text) is not str or len(result.text.encode("utf-8")) > max_output_bytes:
			return fail("malformed")
		parsed = parse_intake_request(result.text, request_id=request_id, operation=operation,
			source_text=source_text, allowed_target_refs=targets)
		if time.monotonic() >= deadline:
			return fail("timeout")
		return with_adapter_metadata({**base, "status": "available", "failure_kind": "", "error": "",
			"text": json.dumps(parsed, sort_keys=True, separators=(",", ":")), "resumable": False,
			"native_invocation_id": obs.invocation_id, "observed_provider_name": obs.selected_provider_name,
			"observed_model_name": obs.provider_reported_model, "route_observation": "verified",
			"invocation_bound": True, "successful_empty": not parsed["questions"] and not parsed["facts"],
			"dispatch": "attempted"}, operation="generate_text", backend_available=True, implementation_status="available")
	except _IntakeGenerationCancelled:
		return fail("cancelled")
	except (IntakeContractError, UnicodeError, RecursionError):
		return fail("malformed")
	except Exception as exc:
		return fail(classify_router_failure(exc))


class _HookObservationCancelled(BaseException):
	"""Propagate through native capture so only the owned child is reaped."""


_HOOK_REPORTED_MODELS = frozenset({PINNED_GROK_MODEL, "grok-4.7-build"})


def _qualified_native_observation_types() -> Optional[tuple]:
	"""The pinned Native classes. A test double is not this pair."""

	try:
		from ipfs_accelerate_py.cli_runtime.grok_invocation_observation import (
			GrokInvocationObservation,
			ObservedTextGeneration,
		)
	except Exception:
		return None
	if not isinstance(ObservedTextGeneration, type) or not isinstance(GrokInvocationObservation, type):
		return None
	return (ObservedTextGeneration, GrokInvocationObservation)


def _hook_observation_bound(obs: Any, observation_type: type, request_id: str) -> bool:
	try:
		return bool(
			type(obs) is observation_type
			and obs.request_id == request_id
			and type(obs.invocation_id) is str
			and re.fullmatch(r"[0-9a-f]{32}", obs.invocation_id) is not None
			and type(obs.native_dispatch_count) is int and obs.native_dispatch_count == 1
			and obs.invocation_scope == "current_call"
			and obs.schema == "native-grok-invocation-observation@1"
			and obs.observation_only is True and obs.raw_provider_data_exported is False
			and type(obs.process_returncode) is int and obs.process_returncode == 0
			and obs.stream_complete is True and obs.wire_model_observed is True
			and obs.evidence_class == "native_final_end_model_usage"
		)
	except Exception:
		return False


def generate_observed_hook_purpose(
	*,
	purpose_id: str,
	inputs: Mapping[str, Any],
	request_id: str,
	timeout: float = 30.0,
	cancel_event: Any = None,
	progress_callback: Any = None,
	max_output_bytes: int = 8192,
) -> Dict[str, Any]:
	"""Run one hook purpose through the loaded Native observation seam.

	There is no plain-text fallback and no second provider. Tool execution
	stays denied. The returned receipt never contains the prompt. A fake
	observation type can satisfy the loaded seam and still cannot verify a
	live Grok model.
	"""

	base: Dict[str, Any] = {
		"status": "unavailable",
		"code": "route_unverified",
		"text": "",
		"output_text": "",
		"request_id": request_id if type(request_id) is str else "",
		"native_invocation_id": "",
		"observed_router": "",
		"observed_provider": "",
		"observed_model": "",
		"observed_build": "",
		"route_observation": "unverified",
		"invocation_bound": False,
		"native_observation_bound": False,
		"evidence_class": "",
		"transport_kind": "native_observation",
		"model_dispatched": False,
		"tools_invoked": False,
		"tools_allowed": False,
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
		"prompt_logged": False,
		"live_canary": False,
		"live_model_identity_verified": False,
		"live_build_identity_verified": False,
		"provider_supported_identity": False,
	}

	def finish(kind: str, **extra: Any) -> Dict[str, Any]:
		payload = dict(base)
		payload.update(extra)
		payload["status"] = kind if kind in {"available", "timeout", "cancelled", "quota", "malformed"} else "unavailable"
		payload["code"] = kind
		payload["text"] = ""
		payload["prompt_logged"] = False
		payload["live_canary"] = False
		payload["tools_invoked"] = False
		payload["tools_allowed"] = False
		payload["allow_local_fallback"] = False
		payload["allow_cross_provider_fallback"] = False
		if payload["live_model_identity_verified"] is not True:
			payload["live_model_identity_verified"] = False
			payload["live_build_identity_verified"] = False
			payload["provider_supported_identity"] = False
		return payload

	if type(purpose_id) is not str or type(request_id) is not str or re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
		return finish("malformed")
	if not isinstance(inputs, Mapping):
		return finish("malformed")
	if type(timeout) not in (int, float) or isinstance(timeout, bool) or not math.isfinite(float(timeout)) or float(timeout) <= 0:
		return finish("malformed")
	if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 8192:
		return finish("malformed")
	if cancel_event is not None and cancel_event.is_set():
		return finish("cancelled", route_observation="cancelled")
	generate, result_type, observation_type = load_observed_llm_symbols()
	if not callable(generate) or not isinstance(result_type, type) or not isinstance(observation_type, type):
		return finish("route_unverified", route_observation="unverified")
	if pinned_grok47_adapter_binding(generate) is None:
		return finish("route_unverified", route_observation="unverified")
	qualified = _qualified_native_observation_types()
	native_qualified = qualified is not None and result_type is qualified[0] and observation_type is qualified[1]
	try:
		prompt = json.dumps(
			{"purpose_id": purpose_id, "inputs": dict(inputs),
			 "instructions": "Return one JSON object for this purpose. Do not call tools."},
			sort_keys=True, separators=(",", ":"), ensure_ascii=False,
		)
		prompt.encode("utf-8")
	except (TypeError, ValueError, UnicodeError):
		return finish("malformed")
	deadline = time.monotonic() + min(float(timeout), 60.0)
	remaining = deadline - time.monotonic()
	if remaining <= 0:
		return finish("timeout", route_observation="timeout")

	def progress(_summary: Any) -> None:
		if cancel_event is not None and cancel_event.is_set():
			raise _HookObservationCancelled()
		if callable(progress_callback):
			try:
				progress_callback({"phase": "provider_progress", "router": INFERENCE_OWNER})
			except Exception:
				pass

	try:
		result = generate(
			prompt=prompt,
			provider=PINNED_GROK_PROVIDER,
			model_name=PINNED_GROK_MODEL,
			observation_request_id=request_id,
			timeout=remaining,
			allow_local_fallback=False,
			allow_cross_provider_fallback=False,
			grok_cli_cmd=["grok"],
			grok_tools="read_file",
			grok_disallowed_tools="read_file,search_tool,use_tool",
			grok_permission_mode="dontAsk",
			grok_max_turns=1,
			grok_stream_progress=True,
			grok_progress_callback=progress,
			usage_cancel_event=cancel_event,
		)
	except _HookObservationCancelled:
		return finish("cancelled", model_dispatched=True, route_observation="cancelled")
	except Exception as exc:
		kind = classify_router_failure(exc)
		observation = {"timeout": "timeout", "cancelled": "cancelled", "quota": "quota", "malformed": "malformed"}.get(kind, "unavailable")
		return finish(kind if kind in {"timeout", "cancelled", "quota", "malformed"} else "unavailable",
			model_dispatched=True, route_observation=observation)
	if cancel_event is not None and cancel_event.is_set():
		return finish("cancelled", model_dispatched=True, route_observation="cancelled")
	if time.monotonic() >= deadline:
		return finish("timeout", model_dispatched=True, route_observation="timeout")
	if type(result) is not result_type or not hasattr(result, "observation") or not hasattr(result, "text"):
		return finish("route_unverified", model_dispatched=True, route_observation="unverified")
	obs = result.observation
	if not _hook_observation_bound(obs, observation_type, request_id):
		return finish("route_unverified", model_dispatched=True, route_observation="unverified")
	if (obs.selected_provider_name != PINNED_GROK_PROVIDER or obs.selected_model_name != PINNED_GROK_MODEL
			or obs.provider_reported_model not in _HOOK_REPORTED_MODELS):
		return finish("substitution_refused", model_dispatched=True, route_observation="mismatched",
			observed_provider=str(getattr(obs, "selected_provider_name", "") or ""),
			observed_model=str(getattr(obs, "selected_model_name", "") or ""),
			observed_build=str(getattr(obs, "provider_reported_model", "") or ""))
	if type(result.text) is not str or len(result.text.encode("utf-8")) > max_output_bytes:
		return finish("malformed", model_dispatched=True, route_observation="malformed", invocation_bound=True,
			native_invocation_id=obs.invocation_id)
	bound_native = native_qualified is True
	return finish(
		"available",
		model_dispatched=True,
		output_text=result.text,
		route_observation="verified",
		invocation_bound=True,
		native_observation_bound=bound_native,
		native_invocation_id=obs.invocation_id,
		observed_router=INFERENCE_OWNER,
		observed_provider=obs.selected_provider_name,
		observed_model=obs.selected_model_name,
		observed_build=obs.provider_reported_model,
		evidence_class=obs.evidence_class,
		live_model_identity_verified=bound_native,
		live_build_identity_verified=bound_native and obs.provider_reported_model in _HOOK_REPORTED_MODELS,
		provider_supported_identity=bound_native,
	)


def generate_text_via_router(
	prompt: str,
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	**kwargs: Any,
) -> str:
	short = _declared_purpose_short_circuit(kwargs)
	if short is not None:
		if short["status"] == "local_only":
			raise RuntimeError("local_purpose_no_model_dispatch")
		raise RuntimeError(str(short.get("error") or "undeclared_purpose"))
	if kwargs.get("intake_operation") is not None:
		result = generate_text_with_metadata(prompt, provider=provider, model_name=model_name, **kwargs)
		if result.get("status") != "available":
			raise RuntimeError("intake_generation_" + result["failure_kind"])
		return result["text"]
	host_meta = _pop_host_metadata(kwargs)
	if host_meta["intake_operation"] is not None:
		kwargs["response_format"] = intake_request_response_format()
	privacy_context = kwargs.pop("complaint_privacy_context", None)
	privacy_block = _privacy_context_block_reason(
		privacy_context,
		provider=provider,
		model_name=model_name,
		options=kwargs,
	)
	if privacy_block:
		raise RuntimeError(privacy_block)
	if generate_text is None:
		raise RuntimeError("private_generation_unavailable" if privacy_context is not None else "llm_router_unavailable")
	if privacy_context is not None:
		provider, model_name = PRIVACY_GROK_PROVIDER, PRIVACY_GROK_MODEL
		kwargs = _private_generation_options(kwargs)
	route_block = unpinned_grok_route_reason(provider, model_name)
	if route_block:
		raise RuntimeError("private_generation_preflight_unavailable" if privacy_context is not None else route_block)
	effective_provider, effective_model_name, call_options, env_overrides, prepared = _prepare_generate_text_call(
		prompt,
		provider=provider,
		model_name=model_name,
		**kwargs,
	)
	if str(prepared.get("arch_router_status") or "") == "refused":
		raise RuntimeError(ARCH_CLASSIFICATION_BLOCKED)
	preflight_error = _provider_preflight_error(
		effective_provider=effective_provider,
		metadata=prepared,
		env_overrides=env_overrides,
	)
	if preflight_error:
		if privacy_context is not None:
			raise RuntimeError("private_generation_preflight_unavailable")
		raise RuntimeError(_public_error(preflight_error, prompt))
	try:
		with _temporary_env(env_overrides):
			if privacy_context is not None:
				sealed = intercept_final_provider_request({
					"schema": PROVIDER_EGRESS_SCHEMA,
					"provider": PRIVACY_GROK_PROVIDER,
					"model": PRIVACY_GROK_MODEL,
					"prompt": prompt,
					"timeout_seconds": call_options.get("timeout", 60.0),
					"allow_local_fallback": False,
					"allow_cross_provider_fallback": False,
					"request_id": str(call_options.get("request_id") or ""),
					**_optional_egress_fields(call_options),
				})
				forward = {key: sealed[key] for key in _PROVIDER_EGRESS_OPTIONAL if key in sealed}
				return generate_text(
					prompt=sealed["prompt"],
					provider=PRIVACY_GROK_PROVIDER,
					model_name=PRIVACY_GROK_MODEL,
					timeout=sealed["timeout_seconds"],
					allow_local_fallback=False,
					allow_cross_provider_fallback=False,
					**forward,
				)
			return generate_text(
				prompt=prompt,
				provider=effective_provider or None,
				model_name=effective_model_name,
				**call_options,
			)
	except RuntimeError as exc:
		if privacy_context is not None and str(exc).startswith("privacy_denied:"):
			raise
		if privacy_context is not None:
			raise RuntimeError("private_generation_failed") from None
		# A native grok_cli failure must not retry and must not echo the body.
		if effective_provider == PINNED_GROK_PROVIDER:
			raise RuntimeError("provider_exception") from None
		raise
	except Exception:
		if privacy_context is not None:
			raise RuntimeError("private_generation_failed") from None
		if effective_provider == PINNED_GROK_PROVIDER:
			raise RuntimeError("provider_exception") from None
		raise


def generate_text_with_metadata(
	prompt: str,
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	**kwargs: Any,
) -> Dict[str, Any]:
	short = _declared_purpose_short_circuit(kwargs)
	if short is not None:
		return with_adapter_metadata(
			short,
			operation="generate_text",
			backend_available=generate_text is not None,
			degraded_reason=short.get("error") or None,
			implementation_status="available" if generate_text is not None else "unavailable",
		)
	host_meta = _pop_host_metadata(kwargs)
	request_id = host_meta["request_id"]
	intake_operation = host_meta["intake_operation"]
	intake_source_text = host_meta["intake_source_text"]
	privacy_context = kwargs.pop("complaint_privacy_context", None)
	if intake_operation is not None:
		return _generate_intake_with_metadata(prompt, provider=provider, model_name=model_name,
			request_id=request_id, operation=intake_operation, source_text=intake_source_text,
			allowed_target_refs=host_meta["intake_target_refs"], privacy_context=privacy_context,
			options=kwargs, max_output_bytes=host_meta["max_output_bytes"])
	privacy_block = _privacy_context_block_reason(
		privacy_context,
		provider=provider,
		model_name=model_name,
		options=kwargs,
	)
	if privacy_block:
		return with_adapter_metadata(
			{"status": "error", "text": "", "provider_name": provider or "",
			 "model_name": model_name or "", "error": privacy_block,
			 "privacy_decision": "denied", "dispatch": "none"},
			operation="generate_text", backend_available=generate_text is not None,
			implementation_status="available" if generate_text is not None else "unavailable",
		)
	if generate_text is None:
		return with_adapter_metadata(
			{
				"status": "unavailable",
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				"resumable": True,
				"live_canary": False,
				"request_id": request_id,
				"inference_owner": INFERENCE_OWNER,
				"failure_kind": "unavailable",
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=False,
			degraded_reason="private_generation_unavailable" if privacy_context is not None else "llm_router_unavailable",
			implementation_status="unavailable",
		)

	if privacy_context is not None:
		provider, model_name = PRIVACY_GROK_PROVIDER, PRIVACY_GROK_MODEL
		kwargs = _private_generation_options(kwargs)
	route_block = unpinned_grok_route_reason(provider, model_name)
	if route_block:
		return with_adapter_metadata(
			{
				"status": "unavailable",
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				"requested_provider_name": provider or "",
				"requested_model_name": model_name or "",
				"error": "private_generation_preflight_unavailable" if privacy_context is not None else route_block,
				"availability_hint": "private_generation_preflight_unavailable" if privacy_context is not None else route_block,
				"resumable": True,
				"dispatch": "none",
				"live_canary": False,
				"request_id": request_id,
				"inference_owner": INFERENCE_OWNER,
				"failure_kind": "unavailable",
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=True,
			implementation_status="available",
		)
	effective_provider, effective_model_name, call_options, env_overrides, metadata = _prepare_generate_text_call(
		prompt,
		provider=provider,
		model_name=model_name,
		**kwargs,
	)
	if str(metadata.get("arch_router_status") or "") == "refused":
		return with_adapter_metadata(
			{
				"status": "error",
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				**metadata,
				"error": ARCH_CLASSIFICATION_BLOCKED,
				"privacy_decision": "denied",
				"resumable": True,
				"dispatch": "none",
				"live_canary": False,
				"request_id": request_id,
				"inference_owner": INFERENCE_OWNER,
				"failure_kind": "privacy_denied",
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=True,
			implementation_status="available",
		)
	preflight_error = _provider_preflight_error(
		effective_provider=effective_provider,
		metadata=metadata,
		env_overrides=env_overrides,
	)
	if preflight_error:
		private_preflight = privacy_context is not None
		grok_preflight = str(effective_provider or "") == PINNED_GROK_PROVIDER
		public_preflight = "private_generation_preflight_unavailable" if private_preflight else _public_error(preflight_error, prompt)
		return with_adapter_metadata(
			{
				"status": "error" if private_preflight or not grok_preflight else "unavailable",
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				**metadata,
				"error": public_preflight,
				"availability_hint": public_preflight,
				"resumable": True,
				"dispatch": "none",
				"live_canary": False,
				"request_id": request_id,
				"inference_owner": INFERENCE_OWNER,
				"failure_kind": "unavailable",
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=True,
			implementation_status="available",
		)

	try:
		with _temporary_env(env_overrides):
			if privacy_context is not None:
				sealed = intercept_final_provider_request({
					"schema": PROVIDER_EGRESS_SCHEMA,
					"provider": PRIVACY_GROK_PROVIDER,
					"model": PRIVACY_GROK_MODEL,
					"prompt": prompt,
					"timeout_seconds": call_options.get("timeout", 60.0),
					"allow_local_fallback": False,
					"allow_cross_provider_fallback": False,
					"request_id": request_id,
					**_optional_egress_fields(call_options),
				})
				prompt = sealed["prompt"]
				call_options = {
					"timeout": sealed["timeout_seconds"],
					"allow_local_fallback": False,
					"allow_cross_provider_fallback": False,
					**{key: sealed[key] for key in _PROVIDER_EGRESS_OPTIONAL if key in sealed},
				}
				effective_provider = PRIVACY_GROK_PROVIDER
				effective_model_name = PRIVACY_GROK_MODEL
			text = generate_text(
				prompt=prompt,
				provider=effective_provider or None,
				model_name=effective_model_name,
				**call_options,
			)
	except Exception as exc:
		if privacy_context is not None and isinstance(exc, RuntimeError) and str(exc).startswith("privacy_denied:"):
			return with_adapter_metadata(
				{"status": "error", "text": "", "provider_name": provider or "",
				 "model_name": model_name or "", "error": str(exc),
				 "privacy_decision": "denied", "dispatch": "none", "prompt_logged": False,
				 "request_id": request_id, "failure_kind": "privacy_denied"},
				operation="generate_text", backend_available=True, implementation_status="available",
			)
		private_failure = privacy_context is not None
		grok_failure = str(effective_provider or "") == PINNED_GROK_PROVIDER
		kind = classify_router_failure(exc)
		if private_failure:
			public_error = "private_generation_failed"
			status = "error" if kind == "unavailable" else kind
		elif grok_failure and kind == "unavailable":
			public_error = "provider_exception"
			status = "unavailable"
		elif grok_failure:
			public_error = kind
			status = kind
		else:
			public_error = "provider_exception"
			status = "error" if kind == "unavailable" else kind
		receipt = _route_receipt(
			requested_provider=str(metadata.get("effective_provider_name") or effective_provider or ""),
			requested_model=str(metadata.get("effective_model_name") or effective_model_name or ""),
			observe=True,
			request_id=request_id,
		)
		receipt.pop("requested_provider_name", None)
		receipt.pop("requested_model_name", None)
		return with_adapter_metadata(
			{
				"status": status,
				"text": "",
				"provider_name": provider or "",
				"model_name": model_name or "",
				**metadata,
				**receipt,
				"error": public_error,
				"availability_hint": public_error,
				"failure_kind": kind,
				"resumable": True,
				"dispatch": "attempted",
				"live_canary": False,
				"intake_complete": False,
				"prompt_logged": False,
			},
			operation="generate_text",
			backend_available=True,
			implementation_status="available",
		)

	if type(text) is not str or len(text.encode("utf-8")) > INTAKE_MAX_OUTPUT_BYTES:
		text = ""
		oversize = True
	else:
		oversize = False
	receipt = _route_receipt(
		requested_provider=str(metadata.get("effective_provider_name") or effective_provider or ""),
		requested_model=str(metadata.get("effective_model_name") or effective_model_name or ""),
		observe=True,
		request_id=request_id,
	)
	receipt.pop("requested_provider_name", None)
	receipt.pop("requested_model_name", None)
	successful_empty = False
	return with_adapter_metadata(
		{
			"status": "available",
			"text": text,
			"provider_name": provider or "",
			"model_name": model_name or "",
			**metadata,
			**receipt,
			"resumable": False,
			"failure_kind": "",
			"intake_complete": False,
			"successful_empty": successful_empty,
			"prompt_logged": False,
		},
		operation="generate_text",
		backend_available=True,
		implementation_status="available",
	)


def llm_router_status(
	*,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	prompt: str = "",
	perform_probe: bool = False,
	**kwargs: Any,
) -> Dict[str, Any]:
	privacy_context = kwargs.pop("complaint_privacy_context", None)
	if generate_text is None:
		return with_adapter_metadata(
			{
				"status": "unavailable",
				"configured_provider_name": provider or "",
				"configured_model_name": model_name or "",
				"effective_provider_name": "",
				"effective_model_name": "",
				"probe_performed": False,
				"dispatch": "none",
				"static_capability_only": True,
				"error": "private_generation_unavailable" if privacy_context is not None else "llm_router_unavailable",
			},
			operation="llm_router_status",
			backend_available=False,
			degraded_reason="private_generation_unavailable" if privacy_context is not None else "llm_router_unavailable",
			implementation_status="unavailable",
		)

	if not perform_probe:
		return with_adapter_metadata(
			{
				"status": "available",
				"configured_provider_name": provider or "",
				"configured_model_name": model_name or "",
				"effective_provider_name": "",
				"effective_model_name": "",
				"probe_performed": False,
				"dispatch": "none",
				"static_capability_only": True,
				"error": "",
			},
			operation="llm_router_status",
			backend_available=True,
			implementation_status="available",
		)

	if privacy_context is None:
		privacy_block = PRIVACY_DENIAL_CLOUD_DISABLED
	else:
		privacy_block = _privacy_context_block_reason(
			privacy_context,
			provider=provider,
			model_name=model_name,
			options=kwargs,
		)
	if privacy_block:
		return with_adapter_metadata(
			{
				"status": "error",
				"configured_provider_name": provider or "",
				"configured_model_name": model_name or "",
				"effective_provider_name": "",
				"effective_model_name": "",
				"probe_performed": False,
				"dispatch": "none",
				"static_capability_only": False,
				"privacy_decision": "denied",
				"error": privacy_block,
			},
			operation="llm_router_status",
			backend_available=False,
			degraded_reason=privacy_block,
			implementation_status="available",
		)

	provider, model_name = PRIVACY_GROK_PROVIDER, PRIVACY_GROK_MODEL
	kwargs = _private_generation_options(kwargs)
	effective_provider, effective_model_name, _, env_overrides, metadata = _prepare_generate_text_call(
		prompt or "HACC llm_router health check",
		provider=provider,
		model_name=model_name,
		**kwargs,
	)
	preflight_error = _provider_preflight_error(
		effective_provider=effective_provider,
		metadata=metadata,
		env_overrides=env_overrides,
	)
	payload: Dict[str, Any] = {
		"status": "available" if not preflight_error else "degraded",
		"configured_provider_name": provider or "",
		"configured_model_name": model_name or "",
		"effective_provider_name": effective_provider or "",
		"effective_model_name": effective_model_name or "",
		"probe_performed": False,
		"error": "private_generation_preflight_unavailable" if preflight_error else "",
		**metadata,
	}

	if perform_probe:
		probe_prompt = prompt or "Return a one-line router health confirmation for the HACC complaint workflow."
		probe_kwargs = dict(kwargs)
		if privacy_context is not None:
			probe_kwargs["complaint_privacy_context"] = privacy_context
		probe_payload = generate_text_with_metadata(
			probe_prompt,
			provider=provider,
			model_name=model_name,
			**probe_kwargs,
		)
		payload["probe_performed"] = True
		payload["probe_status"] = probe_payload.get("status")
		payload["probe_error"] = probe_payload.get("error", "")
		payload["probe_text_preview"] = str(probe_payload.get("text") or "")[:160]
		if probe_payload.get("status") != "available":
			payload["status"] = "error"
			payload["error"] = str(probe_payload.get("error") or preflight_error or "")

	return with_adapter_metadata(
		payload,
		operation="llm_router_status",
		backend_available=payload["status"] == "available",
		degraded_reason=payload.get("error") or None,
		implementation_status="available" if payload["status"] != "unavailable" else "unavailable",
	)


def grok47_route_capability(
	*,
	include_canary: bool = False,
	canary_transport: Any = None,
) -> Dict[str, Any]:
	"""Inspect configuration, or explicitly dispatch one synthetic canary.

	Static presence is configuration evidence, never a selected route. An
	injected transport cannot attest a live call. The pinned native router's
	public string result and selection trace do not expose invocation-bound
	wire-model evidence; only the optional native observation API can verify it.
	"""

	if type(include_canary) is not bool:
		raise ValueError("include_canary must be an explicit boolean")
	if canary_transport is not None and not callable(canary_transport):
		raise ValueError("canary_transport must be callable")
	router_ready = callable(generate_text)
	binary_ready = grok_cli_binary_present()
	auth_ready = grok_cli_auth_present()
	gaps = []
	if not router_ready:
		gaps.append("llm_router symbol is unavailable. The pinned route was not dispatched.")
	if not binary_ready:
		gaps.append(
			"Grok CLI unavailable: grok binary not found on PATH. "
			"No fallback provider was contacted."
		)
	if not auth_ready:
		gaps.append(
			"Grok CLI unavailable: missing authentication. "
			"Set XAI_API_KEY or sign in so the active HOME has a non-empty Grok CLI auth file. "
			"No fallback provider was contacted."
		)
	payload: Dict[str, Any] = {
		"inference_owner": INFERENCE_OWNER,
		"requested_provider_name": PINNED_GROK_PROVIDER,
		"requested_model_name": PINNED_GROK_MODEL,
		"selected_provider_name": "",
		"selected_model_name": "",
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
		"router_symbol_available": router_ready,
		"binary_available": binary_ready,
		"auth_present": auth_ready,
		"model_pinned": True,
		"static_capability_only": True,
		"probe_performed": False,
		"canary_enabled": include_canary,
		"live_canary": False,
		"provider_reported_model": "",
		"response_cache_hit": False,
		"canary_token_matched": False,
		"dispatch": "none",
		"request_id": _new_request_id(),
		"text": "",
		"status": "unavailable" if gaps else "available",
		"error": " ".join(gaps),
		"resumable": bool(gaps),
		"route_observation": "unverified",
		"route_evidence_class": "absent",
	}
	if gaps or not include_canary:
		return with_adapter_metadata(
			payload,
			operation="grok47_route_capability",
			backend_available=not gaps and router_ready,
			degraded_reason=payload["error"] or None,
			implementation_status="available" if router_ready else "unavailable",
		)

	injected = canary_transport is not None
	observed_generate, result_type, observation_type = (None, None, None) if injected else load_observed_llm_symbols()
	observed_api = callable(observed_generate) and isinstance(result_type, type) and isinstance(observation_type, type)
	transport = canary_transport if injected else (observed_generate if observed_api else generate_text)
	payload["static_capability_only"] = False
	payload["probe_performed"] = True
	payload["canary_transport"] = "injected" if injected else "llm_router"
	try:
		canary_kwargs = pinned_grok47_canary_kwargs()
		if observed_api:
			canary_kwargs["observation_request_id"] = payload["request_id"]
		result = transport(prompt=PINNED_GROK_CANARY_PROMPT, **canary_kwargs)
	except Exception:
		payload.update({"status": "unavailable", "error": "provider_exception",
			"availability_hint": "provider_exception", "resumable": True, "dispatch": "attempted"})
		return with_adapter_metadata(payload, operation="grok47_route_capability",
			backend_available=True, degraded_reason="provider_exception", implementation_status="available")

	payload.update(interpret_canary_dispatch(result))
	observed_text = result.get("text") if isinstance(result, Mapping) else result
	observation = None
	if observed_api and type(result) is result_type and type(result.observation) is observation_type:
		candidate = result.observation
		if (candidate.request_id == payload["request_id"]
				and type(candidate.invocation_id) is str and re.fullmatch(r"[0-9a-f]{32}", candidate.invocation_id)
				and type(candidate.native_dispatch_count) is int and candidate.native_dispatch_count == 1
				and candidate.invocation_scope == "current_call"
				and candidate.observation_only is True and candidate.raw_provider_data_exported is False
				and candidate.schema == "native-grok-invocation-observation@1"
				and type(candidate.process_returncode) is int and candidate.process_returncode == 0
				and candidate.stream_complete is True
				and candidate.selected_provider_name == PINNED_GROK_PROVIDER
				and candidate.selected_model_name == PINNED_GROK_MODEL):
			observation = candidate
			observed_text = result.text
	payload["canary_token_matched"] = isinstance(observed_text, str) and observed_text.strip() == PINNED_GROK_CANARY_PROMPT
	if observation is not None:
		payload["native_invocation_id"] = observation.invocation_id
		payload["selected_provider_name"] = observation.selected_provider_name
		payload["selected_model_name"] = observation.selected_model_name
		payload["route_observation"] = "verified"
		payload["route_evidence_class"] = "native_invocation"
		if (observation.wire_model_observed is True
				and observation.evidence_class == "native_final_end_model_usage"
				and type(observation.provider_reported_model) is str
				and re.fullmatch(r"grok-[0-9]{1,2}(?:\.[0-9]{1,2}){0,2}(?:-build)?", observation.provider_reported_model)):
			payload["provider_reported_model"] = observation.provider_reported_model
			# The requested route remains exactly grok-4.7. Grok's observed native
			# build label is retained verbatim and accepted only by this explicit set.
			model_matches = observation.provider_reported_model in {PINNED_GROK_MODEL, "grok-4.7-build"}
			if model_matches and payload["canary_token_matched"]:
				payload.update({"live_canary": True, "status": "available", "dispatch": "canary",
					"error": "", "resumable": False})
			else:
				payload.update({"status": "unavailable", "dispatch": "canary_rejected",
					"error": "canary_model_or_token_mismatch", "resumable": True})
	if payload["dispatch"] == "none":
		payload.update({
			"dispatch": "canary_unverified", "status": "unverified",
			"error": "Grok canary lacks invocation-bound wire-model evidence from the native router. Injected or cached results and router selection cannot verify a live canary.",
			"resumable": True,
		})
	return with_adapter_metadata(payload, operation="grok47_route_capability",
		backend_available=payload["status"] == "available", degraded_reason=payload["error"] or None,
		implementation_status="available")


# Versioned complaint privacy contract. The router stays independent of the
# application package; workspace code imports these helpers lazily.
PRIVACY_POLICY_CONTRACT = "complaint_privacy_policy"
PRIVACY_POLICY_VERSION = "1"
PRIVACY_CONTEXT_CONTRACT = "complaint_privacy_context"
PRIVACY_PROCESSING_LOCAL = "local_private"
PRIVACY_PROCESSING_GROK = "grok_cloud"
PRIVACY_GROK_PROVIDER = "grok_cli"
PRIVACY_GROK_MODEL = "grok-4.7"
PRIVACY_SCOPE_USER_CASE = "user_case"
PRIVACY_AT_REST_PROTECTION = "plaintext_pending"
PRIVACY_DENIAL_CLOUD_DISABLED = "privacy_denied:cloud_processing_disabled"
PRIVACY_DENIAL_SCOPE = "privacy_denied:grok_scope_mismatch"
PRIVACY_DENIAL_CASE = "privacy_denied:case_binding"
PRIVACY_DENIAL_VERSION = "privacy_denied:version"
PRIVACY_DENIAL_SCOPE_FIELD = "privacy_denied:scope"
PRIVACY_DENIAL_MALFORMED = "privacy_denied:malformed_consent"

PRIVATE_DATA_CLASSES: tuple[tuple[str, str], ...] = (
	("raw_intake", "Raw intake answers and intake history for one user and case."),
	("attachments", "Attachment names and bytes supplied for the case."),
	("fact_kg", "Claim-specific fact knowledge graph."),
	("claim_dependency_evaluations", "Claim-specific dependency and element evaluations."),
	("annotations", "Document and workspace annotations tied to the case."),
	("drafts_proofs", "Drafts, proof runs, and case theorem exports."),
	("embeddings", "Embeddings derived from private case text."),
	("exports", "Filing exports produced from the case."),
	("logs", "Logs that can quote private case content."),
	("caches", "Caches derived from private case content."),
	("temporary_files", "Temporary files created while processing the case."),
	("backups", "Backups of private session and case state."),
)
PUBLIC_LEGAL_SOURCE_CLASS = (
	"public_legal_source_graph",
	"Published legal sources. Distinct from the private claim fact graph.",
)
_PRIVATE_CLASS_IDS = {item[0] for item in PRIVATE_DATA_CLASSES}
_KNOWN_DATA_CLASSES = _PRIVATE_CLASS_IDS | {PUBLIC_LEGAL_SOURCE_CLASS[0]}
_AMBIENT_PROVIDER_ENVS = (
	"IPFS_DATASETS_PY_LLM_PROVIDER",
	"COMPLAINT_GENERATOR_LLM_PROVIDER",
	"LLM_ROUTER_PROVIDER",
	"COMPLAINT_LLM_PROVIDER",
	"COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER",
)
_CONSENT_STATUSES = {"implicit_local", "explicit_local", "explicit_grok"}


def complaint_data_class_inventory() -> Dict[str, Any]:
	"""Canonical inventory. Does not read session, evidence, export, or secret paths."""

	return {
		"contract": PRIVACY_POLICY_CONTRACT,
		"version": PRIVACY_POLICY_VERSION,
		"private_claim_fact_graph": [
			{"id": class_id, "description": description, "classification": "private"}
			for class_id, description in PRIVATE_DATA_CLASSES
		],
		"public_legal_source_graph": {
			"id": PUBLIC_LEGAL_SOURCE_CLASS[0],
			"description": PUBLIC_LEGAL_SOURCE_CLASS[1],
			"classification": "public",
			"distinct_from": "private_claim_fact_graph",
		},
		"at_rest_protection": PRIVACY_AT_REST_PROTECTION,
		"encryption_at_rest_blocks_remote_llm": False,
		"authenticates_tenant": False,
		"agent_context": {
			"fixtures_only": True,
			"excluded_path_classes": ["session", "evidence", "export", "secret"],
		},
	}


def _local_privacy_policy(user_id: str, case_id: str, *, consent_status: str = "implicit_local") -> Dict[str, Any]:
	return {
		"contract": PRIVACY_POLICY_CONTRACT,
		"version": PRIVACY_POLICY_VERSION,
		"user_id": str(user_id or ""),
		"case_id": str(case_id or ""),
		"processing_mode": PRIVACY_PROCESSING_LOCAL,
		"cloud_processing_enabled": False,
		"permitted_remote": None,
		"scope": PRIVACY_SCOPE_USER_CASE,
		"at_rest_protection": PRIVACY_AT_REST_PROTECTION,
		"encryption_at_rest_blocks_remote_llm": False,
		"authenticates_tenant": False,
		"consent": {"status": consent_status, "cloud_processing": False},
		"data_classes": {
			"private": [class_id for class_id, _description in PRIVATE_DATA_CLASSES],
			"public": [PUBLIC_LEGAL_SOURCE_CLASS[0]],
		},
		"agent_context": {
			"fixtures_only": True,
			"excluded_path_classes": ["session", "evidence", "export", "secret"],
		},
	}


def privacy_policy_for_mode(user_id: str, case_id: str, mode: str) -> Dict[str, Any]:
	normalized = str(mode or "").strip().lower()
	if normalized in {"local", "local_private"}:
		return _local_privacy_policy(user_id, case_id, consent_status="explicit_local")
	if normalized in {"grok", "grok_cloud"}:
		policy = _local_privacy_policy(user_id, case_id, consent_status="explicit_grok")
		policy["processing_mode"] = PRIVACY_PROCESSING_GROK
		policy["cloud_processing_enabled"] = True
		policy["consent"] = {"status": "explicit_grok", "cloud_processing": True}
		policy["permitted_remote"] = {
			"provider": PRIVACY_GROK_PROVIDER,
			"model": PRIVACY_GROK_MODEL,
		}
		return policy
	raise ValueError("privacy_denied:unknown_mode")


def _policy_rejection_reason(raw: Any, *, user_id: str, case_id: str) -> Optional[str]:
	if not isinstance(raw, Mapping):
		return "legacy_missing" if raw is None else PRIVACY_DENIAL_MALFORMED
	if str(raw.get("contract") or "") != PRIVACY_POLICY_CONTRACT:
		return PRIVACY_DENIAL_MALFORMED
	if str(raw.get("version") or "") != PRIVACY_POLICY_VERSION:
		return PRIVACY_DENIAL_VERSION
	if str(raw.get("scope") or "") != PRIVACY_SCOPE_USER_CASE:
		return PRIVACY_DENIAL_SCOPE_FIELD
	policy_user = str(raw.get("user_id") or "")
	policy_case = str(raw.get("case_id") or "")
	if not policy_user or not policy_case or policy_user != str(user_id or "") or policy_case != str(case_id or ""):
		return PRIVACY_DENIAL_CASE
	if raw.get("authenticates_tenant") is not False:
		return PRIVACY_DENIAL_MALFORMED
	if raw.get("encryption_at_rest_blocks_remote_llm") is not False:
		return PRIVACY_DENIAL_MALFORMED
	if str(raw.get("at_rest_protection") or "") != PRIVACY_AT_REST_PROTECTION:
		return PRIVACY_DENIAL_MALFORMED
	consent = raw.get("consent")
	if not isinstance(consent, Mapping) or str(consent.get("status") or "") not in _CONSENT_STATUSES:
		return PRIVACY_DENIAL_MALFORMED
	mode = str(raw.get("processing_mode") or "")
	cloud = raw.get("cloud_processing_enabled")
	permitted = raw.get("permitted_remote")
	consent_status = str(consent.get("status") or "")
	if mode == PRIVACY_PROCESSING_LOCAL:
		if cloud is not False or permitted is not None or consent.get("cloud_processing") is not False:
			return PRIVACY_DENIAL_MALFORMED
		if consent_status == "explicit_grok":
			return PRIVACY_DENIAL_MALFORMED
	elif mode == PRIVACY_PROCESSING_GROK:
		if cloud is not True or consent_status != "explicit_grok" or consent.get("cloud_processing") is not True:
			return PRIVACY_DENIAL_MALFORMED
		if not isinstance(permitted, Mapping):
			return PRIVACY_DENIAL_MALFORMED
		if set(permitted.keys()) != {"provider", "model"}:
			return PRIVACY_DENIAL_MALFORMED
		if str(permitted.get("provider") or "") != PRIVACY_GROK_PROVIDER:
			return PRIVACY_DENIAL_MALFORMED
		if str(permitted.get("model") or "") != PRIVACY_GROK_MODEL:
			return PRIVACY_DENIAL_MALFORMED
	else:
		return PRIVACY_DENIAL_MALFORMED
	data_classes = raw.get("data_classes")
	if not isinstance(data_classes, Mapping):
		return PRIVACY_DENIAL_MALFORMED
	if not isinstance(data_classes.get("private"), list) or data_classes["private"] != [class_id for class_id, _description in PRIVATE_DATA_CLASSES]:
		return PRIVACY_DENIAL_MALFORMED
	if not isinstance(data_classes.get("public"), list) or data_classes["public"] != [PUBLIC_LEGAL_SOURCE_CLASS[0]]:
		return PRIVACY_DENIAL_MALFORMED
	agent_context = raw.get("agent_context")
	if not isinstance(agent_context, Mapping) or agent_context.get("fixtures_only") is not True:
		return PRIVACY_DENIAL_MALFORMED
	if not isinstance(agent_context.get("excluded_path_classes"), list) or agent_context["excluded_path_classes"] != ["session", "evidence", "export", "secret"]:
		return PRIVACY_DENIAL_MALFORMED
	return None


def inspect_privacy_policy(raw: Any, *, user_id: str, case_id: str) -> Dict[str, Any]:
	"""Validate one serialized policy. Malformed input never enables cloud processing."""

	reason = _policy_rejection_reason(raw, user_id=user_id, case_id=case_id)
	if reason is None and isinstance(raw, Mapping):
		admitted = dict(raw)
		return {
			"admitted": True,
			"reason": "ok",
			"cloud_processing_enabled": bool(admitted.get("cloud_processing_enabled")),
			"policy": admitted,
		}
	load_reason = "legacy_missing" if reason == "legacy_missing" else str(reason or PRIVACY_DENIAL_MALFORMED)
	return {
		"admitted": False,
		"reason": load_reason,
		"cloud_processing_enabled": False,
		"policy": _local_privacy_policy(user_id, case_id),
	}


def coerce_effective_privacy_policy(raw: Any, *, user_id: str, case_id: str) -> Dict[str, Any]:
	inspection = inspect_privacy_policy(raw, user_id=user_id, case_id=case_id)
	return inspection["policy"]


def build_complaint_privacy_context(
	policy: Any,
	*,
	user_id: str,
	case_id: str,
	data_class: str,
) -> Dict[str, Any]:
	inspection = inspect_privacy_policy(policy, user_id=user_id, case_id=case_id)
	return {
		"contract": PRIVACY_CONTEXT_CONTRACT,
		"version": PRIVACY_POLICY_VERSION,
		"user_id": str(user_id or ""),
		"case_id": str(case_id or ""),
		"data_class": str(data_class or ""),
		"policy": inspection["policy"],
		"load": {
			"admitted": inspection["admitted"],
			"reason": inspection["reason"],
			"cloud_processing_enabled": inspection["cloud_processing_enabled"],
		},
	}


def _resolved_remote_target(provider: Optional[str], model_name: Optional[str]) -> tuple[str, str]:
	explicit_provider = str(provider or "").strip()
	explicit_model = str(model_name or "").strip()
	ambient: list[str] = []
	for name in _AMBIENT_PROVIDER_ENVS:
		value = os.getenv(name, "").strip()
		if value:
			ambient.append(value)
	unique = {item.lower() for item in ambient}
	if explicit_provider:
		resolved_provider = explicit_provider
	elif len(unique) == 1:
		resolved_provider = ambient[0]
	elif not unique:
		resolved_provider = ""
	else:
		resolved_provider = ""
	return resolved_provider, explicit_model


def _privacy_context_block_reason(
	context: Any,
	*,
	provider: Optional[str],
	model_name: Optional[str],
	options: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
	"""Return a stable denial code, or None when this call may reach preparation.

	A missing context keeps historical callers working. A present context is the
	first-party private boundary and is decided before provider preparation.
	"""

	if context is None:
		return None
	if not isinstance(context, Mapping):
		return PRIVACY_DENIAL_MALFORMED
	if str(context.get("contract") or "") != PRIVACY_CONTEXT_CONTRACT:
		return PRIVACY_DENIAL_MALFORMED
	if str(context.get("version") or "") != PRIVACY_POLICY_VERSION:
		return PRIVACY_DENIAL_VERSION
	data_class = str(context.get("data_class") or "")
	if data_class not in _KNOWN_DATA_CLASSES:
		return PRIVACY_DENIAL_MALFORMED
	user_id = str(context.get("user_id") or "")
	case_id = str(context.get("case_id") or "")
	inspection = inspect_privacy_policy(context.get("policy"), user_id=user_id, case_id=case_id)
	if not inspection["admitted"]:
		reason = str(inspection["reason"] or PRIVACY_DENIAL_MALFORMED)
		if reason == "legacy_missing":
			return PRIVACY_DENIAL_MALFORMED
		return reason
	resolved_provider, resolved_model = _resolved_remote_target(provider, model_name)
	exact_grok = (
		resolved_provider.strip().lower() == PRIVACY_GROK_PROVIDER
		and resolved_model == PRIVACY_GROK_MODEL
	)
	if not inspection["cloud_processing_enabled"]:
		return PRIVACY_DENIAL_CLOUD_DISABLED
	if not exact_grok:
		return PRIVACY_DENIAL_SCOPE
	if options and any(key not in _PRIVATE_GENERATION_OPTIONS and value is not None for key, value in options.items()):
		return PRIVACY_DENIAL_SCOPE
	return None


# Private calls are one pinned generation, not a configurable dispatch route.
# Opaque providers, allocation sessions, custom commands, routing URLs and
# trace destinations cannot inherit case consent.
_PRIVATE_GENERATION_OPTIONS = frozenset({
	"temperature", "max_tokens", "max_output_tokens", "timeout", "stop",
	"top_p", "top_k", "frequency_penalty", "presence_penalty", "seed",
	"response_format", "grok_max_turns",
	"allow_local_fallback", "allow_cross_provider_fallback",
})


def _private_generation_options(options: Mapping[str, Any]) -> Dict[str, Any]:
	return {
		**{key: value for key, value in options.items() if key in _PRIVATE_GENERATION_OPTIONS},
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
	}


# Last remote boundary. Only this object may be copied into a Grok 4.7 call.
# Host CLI controls (progress, cancellation, fixed tool flags) are not fields
# of the serialized provider request and cannot carry case payloads.
PROVIDER_EGRESS_SCHEMA = "complaint-grok47-egress/v1"
_PROVIDER_EGRESS_REQUIRED = frozenset({
	"schema", "provider", "model", "prompt", "timeout_seconds",
	"allow_local_fallback", "allow_cross_provider_fallback", "request_id",
})
_PROVIDER_EGRESS_OPTIONAL = frozenset({
	"temperature", "max_tokens", "max_output_tokens", "top_p", "top_k",
	"frequency_penalty", "presence_penalty", "seed", "stop", "response_format",
})
_PROVIDER_EGRESS_FIELDS = _PROVIDER_EGRESS_REQUIRED | _PROVIDER_EGRESS_OPTIONAL
_PROMPT_JSON_KEYS = frozenset({
	"schema_version", "operation", "request_id", "source_text",
	"allowed_target_refs", "schema", "instructions", "prompt",
	"questions", "facts",
})
_FORBIDDEN_EGRESS_KEYS = frozenset({
	"trace", "trace_jsonl_path", "trace_dir", "embedding", "embeddings",
	"embedding_cache", "enrichment", "enrichment_route", "fallback",
	"fallback_provider", "fallback_model", "provider_instance", "deps",
	"base_url", "api_key", "authorization", "secret", "headers", "messages",
	"cache", "usage_messages", "allocation_path", "allocation_session_id",
})
_BYPASS_KINDS = frozenset({
	"enrichment", "trace", "embedding_cache", "fallback", "alternate_provider",
})
_CASE_CONSENT: Dict[tuple[str, str], Dict[str, Any]] = {}
_PROVIDER_EGRESS_LOG: list[Dict[str, Any]] = []
_EGRESS_LOCK = threading.Lock()


def tui_processing_setting(policy: Any = None) -> Dict[str, Any]:
	"""Plain-language processing choice for one case. Safe to render in the TUI."""

	mode = PRIVACY_PROCESSING_LOCAL
	provider = ""
	model = ""
	if isinstance(policy, Mapping):
		mode = str(policy.get("processing_mode") or PRIVACY_PROCESSING_LOCAL)
		permitted = policy.get("permitted_remote") if isinstance(policy.get("permitted_remote"), Mapping) else {}
		provider = str(permitted.get("provider") or "")
		model = str(permitted.get("model") or "")
	local = mode != PRIVACY_PROCESSING_GROK
	if local:
		value_label = "Local private"
		summary = "Local private: this case never calls a remote provider."
	else:
		value_label = "Grok 4.7 for this case"
		summary = (
			"Grok 4.7 for this case: only sanitized fields go to grok_cli / grok-4.7. "
			"This choice is reused for later turns in this session."
		)
	return {
		"setting_id": "case_processing_mode",
		"label": "Processing",
		"value": PRIVACY_PROCESSING_LOCAL if local else PRIVACY_PROCESSING_GROK,
		"value_label": value_label,
		"summary": summary,
		"scope": "per_case",
		"reusable": True,
		"remote_provider": "" if local else provider,
		"remote_model": "" if local else model,
		"choices": [
			{
				"value": PRIVACY_PROCESSING_LOCAL,
				"label": "Local private",
				"detail": "Never send this case to a remote provider.",
			},
			{
				"value": PRIVACY_PROCESSING_GROK,
				"label": "Grok 4.7 for this case",
				"detail": "Send only sanitized fields to grok_cli / grok-4.7 for later turns in this session.",
			},
		],
	}


def record_case_cloud_consent(*, user_id: str, case_id: str, mode: str) -> Dict[str, Any]:
	"""Cache this session projection; the private workspace owns persistence."""

	policy = privacy_policy_for_mode(user_id, case_id, mode)
	user, case = _case_cache_key(user_id, case_id)
	with _EGRESS_LOCK:
		_CASE_CONSENT[(user, case)] = deepcopy(policy)
	return tui_processing_setting(policy)


def recorded_case_privacy_context(*, user_id: str, case_id: str, data_class: str) -> Dict[str, Any]:
	"""Reuse the recorded choice. A missing record stays local-private."""

	user, case = _case_cache_key(user_id, case_id)
	with _EGRESS_LOCK:
		policy = deepcopy(_CASE_CONSENT.get((user, case)))
	if policy is None:
		policy = _local_privacy_policy(user, case)
	return build_complaint_privacy_context(policy, user_id=user, case_id=case, data_class=data_class)


def clear_case_processing_consent() -> None:
	with _EGRESS_LOCK:
		_CASE_CONSENT.clear()


def provider_egress_captures() -> list[Dict[str, Any]]:
	"""Bounded metadata only; request bodies and caller IDs are never retained."""

	with _EGRESS_LOCK:
		return deepcopy(_PROVIDER_EGRESS_LOG)


def clear_provider_egress_captures() -> None:
	with _EGRESS_LOCK:
		_PROVIDER_EGRESS_LOG.clear()


def _drop_forbidden_egress(value: Any) -> Any:
	if isinstance(value, Mapping):
		return {
			str(key): _drop_forbidden_egress(item)
			for key, item in value.items()
			if str(key) not in _FORBIDDEN_EGRESS_KEYS
		}
	if isinstance(value, list):
		return [_drop_forbidden_egress(item) for item in value]
	if isinstance(value, tuple):
		return [_drop_forbidden_egress(item) for item in value]
	return value


def _sanitize_provider_prompt(prompt: str) -> str:
	stripped = prompt.strip()
	if not stripped.startswith("{") or not stripped.endswith("}"):
		return prompt
	try:
		parsed = json.loads(prompt)
	except (json.JSONDecodeError, RecursionError, ValueError):
		return prompt
	if not isinstance(parsed, dict):
		return prompt
	cleaned = _drop_forbidden_egress(parsed)
	kept = {key: cleaned[key] for key in sorted(cleaned) if key in _PROMPT_JSON_KEYS}
	return json.dumps(kept, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _optional_egress_fields(source: Mapping[str, Any]) -> Dict[str, Any]:
	fields: Dict[str, Any] = {}
	for key in _PROVIDER_EGRESS_OPTIONAL:
		if key not in source:
			continue
		value = source[key]
		if key == "stop":
			if isinstance(value, str):
				fields[key] = value
			elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
				fields[key] = list(value)
			continue
		if key == "response_format":
			if isinstance(value, Mapping):
				fields[key] = _drop_forbidden_egress(dict(value))
			continue
		if key in {"seed", "max_tokens", "max_output_tokens", "top_k"}:
			if type(value) is int and not isinstance(value, bool):
				fields[key] = value
			continue
		if type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(float(value)):
			fields[key] = value
	return fields


def provider_egress_options(source: Mapping[str, Any]) -> Dict[str, Any]:
	"""Copy only vetted generation settings for the actual provider invocation."""

	return _optional_egress_fields(source) if isinstance(source, Mapping) else {}


def intercept_final_provider_request(request: Mapping[str, Any]) -> Dict[str, Any]:
	"""Fail closed. The returned object is the only serialized provider request.

	Unknown fields, alternate providers, traces, embeddings, enrichment payloads
	and fallbacks are rejected. Nothing is appended unless the allowlist holds.
	"""

	if not isinstance(request, Mapping):
		raise RuntimeError(PRIVACY_DENIAL_MALFORMED)
	if any(str(key) in _FORBIDDEN_EGRESS_KEYS for key in request.keys()):
		raise RuntimeError(PRIVACY_DENIAL_SCOPE)
	if set(request.keys()) - _PROVIDER_EGRESS_FIELDS:
		raise RuntimeError(PRIVACY_DENIAL_SCOPE)
	if str(request.get("schema") or "") != PROVIDER_EGRESS_SCHEMA:
		raise RuntimeError(PRIVACY_DENIAL_MALFORMED)
	if str(request.get("provider") or "") != PRIVACY_GROK_PROVIDER:
		raise RuntimeError(PRIVACY_DENIAL_SCOPE)
	if str(request.get("model") or "") != PRIVACY_GROK_MODEL:
		raise RuntimeError(PRIVACY_DENIAL_SCOPE)
	if request.get("allow_local_fallback") is not False or request.get("allow_cross_provider_fallback") is not False:
		raise RuntimeError(PRIVACY_DENIAL_SCOPE)
	prompt = request.get("prompt")
	if type(prompt) is not str:
		raise RuntimeError(PRIVACY_DENIAL_MALFORMED)
	timeout = request.get("timeout_seconds")
	if type(timeout) not in (int, float) or isinstance(timeout, bool) or not math.isfinite(float(timeout)) or float(timeout) <= 0:
		raise RuntimeError(PRIVACY_DENIAL_MALFORMED)
	request_id = request.get("request_id")
	if type(request_id) is not str:
		raise RuntimeError(PRIVACY_DENIAL_MALFORMED)
	sealed: Dict[str, Any] = {
		"schema": PROVIDER_EGRESS_SCHEMA,
		"provider": PRIVACY_GROK_PROVIDER,
		"model": PRIVACY_GROK_MODEL,
		"prompt": _sanitize_provider_prompt(prompt),
		"timeout_seconds": min(float(timeout), 60.0),
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
		"request_id": request_id,
	}
	sealed.update(_optional_egress_fields(request))
	if set(sealed) - _PROVIDER_EGRESS_FIELDS:
		raise RuntimeError(PRIVACY_DENIAL_SCOPE)
	with _EGRESS_LOCK:
		_PROVIDER_EGRESS_LOG.append({
			"schema": PROVIDER_EGRESS_SCHEMA,
			"provider": PRIVACY_GROK_PROVIDER,
			"model": PRIVACY_GROK_MODEL,
			"timeout_seconds": sealed["timeout_seconds"],
			"allow_local_fallback": False,
			"allow_cross_provider_fallback": False,
			"prompt": "",
			"request_id": "",
			"request_reference": os.urandom(16).hex(),
			"capture_kind": "metadata_only",
		})
		del _PROVIDER_EGRESS_LOG[:-8]
	return sealed


def attempt_remote_bypass(kind: str, *, privacy_context: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
	"""Enrichment, trace, embedding cache, fallback and alternate providers stop here.

	The payload is not copied into the egress log and no provider is invoked.
	"""

	normalized = str(kind or "")
	if normalized not in _BYPASS_KINDS:
		normalized = "unknown"
	# Touch the context so a local or cloud choice cannot unlock another route.
	_privacy_context_block_reason(
		privacy_context,
		provider=PRIVACY_GROK_PROVIDER,
		model_name=PRIVACY_GROK_MODEL,
		options={},
	)
	if isinstance(payload, Mapping):
		# A bypass is never a legal provider request. Force a rejected field so
		# a well-formed payload cannot be appended or dispatched from here.
		probe = dict(payload)
		probe["schema"] = PROVIDER_EGRESS_SCHEMA
		if normalized == "alternate_provider":
			probe["provider"] = "codex"
		elif normalized == "fallback":
			probe["allow_local_fallback"] = True
			probe["fallback_provider"] = "codex"
		else:
			probe[normalized] = True
		try:
			intercept_final_provider_request(probe)
		except RuntimeError:
			pass
		else:
			with _EGRESS_LOCK:
				if _PROVIDER_EGRESS_LOG:
					_PROVIDER_EGRESS_LOG.pop()
	return {
		"status": "error",
		"error": f"privacy_denied:bypass_{normalized}",
		"privacy_decision": "denied",
		"dispatch": "none",
		"provider_invoked": False,
		"prompt_logged": False,
	}


# Per-case alias and embedding caches. Keys are (user_id, case_id). Values are
# sealed envelopes only. A lookup never reads another pair's slot.
_CASE_ALIAS_CACHE: Dict[tuple[str, str], Dict[str, bytes]] = {}
_CASE_EMBEDDING_CACHE: Dict[tuple[str, str], Dict[str, bytes]] = {}
_CASE_CACHE_LOCK = threading.Lock()
EMBEDDING_CLASSIFICATION = "private_derived"


def _case_cache_key(user_id: str, case_id: str) -> tuple[str, str]:
	user = str(user_id or "").strip()
	case = str(case_id or "").strip()
	if not user or not case:
		raise ValueError("privacy_denied:case_binding")
	return user, case


def _alias_binding(user_id: str, case_id: str, principal_id: str):
	from integrations.private_storage import PrivateArtifactBinding

	return PrivateArtifactBinding(
		tenant_id=user_id,
		case_id=case_id,
		artifact_kind="case-alias",
		revision="1",
		principal_id=principal_id or user_id,
	)


def _embedding_binding(user_id: str, case_id: str, principal_id: str):
	from integrations.private_storage import PrivateArtifactBinding

	return PrivateArtifactBinding(
		tenant_id=user_id,
		case_id=case_id,
		artifact_kind="embedding",
		revision="1",
		principal_id=principal_id or user_id,
	)


def remember_case_alias(
	*,
	user_id: str,
	case_id: str,
	alias: str,
	canonical: str,
	key: bytes,
	key_id: str,
	principal_id: str = "",
) -> Dict[str, Any]:
	"""Seal one alias mapping into this user and case cache only."""

	from integrations.private_storage import seal_private_artifact

	user, case = _case_cache_key(user_id, case_id)
	alias_text = str(alias or "").strip()
	canonical_text = str(canonical or "").strip()
	if not alias_text or not canonical_text:
		raise ValueError("privacy_denied:malformed_alias")
	alias_id = hashlib.sha256(f"{user}\0{case}\0{alias_text}".encode("utf-8")).hexdigest()
	payload = json.dumps(
		{"alias": alias_text, "canonical": canonical_text},
		separators=(",", ":"),
	).encode("utf-8")
	envelope = seal_private_artifact(
		payload,
		binding=_alias_binding(user, case, principal_id or user),
		key=key,
		key_id=key_id,
	)
	with _CASE_CACHE_LOCK:
		_CASE_ALIAS_CACHE.setdefault((user, case), {})[alias_id] = bytes(envelope)
	return {
		"alias_id": alias_id,
		"encrypted": True,
		"classification": "private",
		"user_id": user,
		"case_id": case,
	}


def resolve_case_alias(
	*,
	user_id: str,
	case_id: str,
	alias: str,
	key: bytes,
	key_id: str,
	principal_id: str = "",
) -> Dict[str, Any]:
	"""Open one alias from the same user and case. Other caches are not consulted."""

	from integrations.private_storage import open_private_artifact

	user, case = _case_cache_key(user_id, case_id)
	alias_text = str(alias or "").strip()
	alias_id = hashlib.sha256(f"{user}\0{case}\0{alias_text}".encode("utf-8")).hexdigest()
	with _CASE_CACHE_LOCK:
		envelope = _CASE_ALIAS_CACHE.get((user, case), {}).get(alias_id)
	if envelope is None:
		return {"found": False, "alias_id": alias_id, "user_id": user, "case_id": case}
	opened = open_private_artifact(
		envelope,
		binding=_alias_binding(user, case, principal_id or user),
		key=key,
		expected_key_id=key_id,
	)
	mapping = json.loads(opened.decode("utf-8"))
	return {
		"found": True,
		"alias_id": alias_id,
		"alias": mapping.get("alias"),
		"canonical": mapping.get("canonical"),
		"user_id": user,
		"case_id": case,
	}


def case_alias_cache_public_view(user_id: str, case_id: str) -> Dict[str, Any]:
	"""Show that the cache holds ciphertext, not names or mappings."""

	user, case = _case_cache_key(user_id, case_id)
	with _CASE_CACHE_LOCK:
		slot = dict(_CASE_ALIAS_CACHE.get((user, case), {}))
	return {
		"entry_count": len(slot),
		"encrypted": all(envelope.startswith(b"CGPE") for envelope in slot.values()) if slot else True,
		"bodies_are_envelopes": True,
		"ciphertext_digests": [hashlib.sha256(envelope).hexdigest() for envelope in slot.values()],
		"joined_ciphertext": "",
	}


def clear_case_private_caches() -> None:
	with _CASE_CACHE_LOCK:
		_CASE_ALIAS_CACHE.clear()
		_CASE_EMBEDDING_CACHE.clear()


def store_private_embedding(
	*,
	user_id: str,
	case_id: str,
	vector: list,
	source_text: str,
	key: bytes,
	key_id: str,
	principal_id: str = "",
	sensitive_literals: Optional[list] = None,
) -> Dict[str, Any]:
	"""Treat an embedding as private derived data and keep it out of the public index."""

	from integrations.ipfs_datasets.storage import publish_public_index_entry
	from integrations.private_storage import seal_private_artifact

	user, case = _case_cache_key(user_id, case_id)
	if not isinstance(vector, list) or not vector:
		raise ValueError("privacy_denied:malformed_embedding")
	embedding_id = os.urandom(32).hex()
	payload = json.dumps(
		{"vector": vector, "source_text": str(source_text or "")},
		separators=(",", ":"),
	).encode("utf-8")
	envelope = seal_private_artifact(
		payload,
		binding=_embedding_binding(user, case, principal_id or user),
		key=key,
		key_id=key_id,
	)
	with _CASE_CACHE_LOCK:
		_CASE_EMBEDDING_CACHE.setdefault((user, case), {})[embedding_id] = bytes(envelope)
	literals = list(sensitive_literals or [])
	if source_text:
		literals.append(str(source_text))
	public_row = publish_public_index_entry(
		{
			"cid": embedding_id,
			"cid_kind": "opaque",
			"artifact_class": "opaque_private_ref",
			"classification": EMBEDDING_CLASSIFICATION,
			"status": "stored",
			"source_text": source_text,
			"embedding": vector,
			"user_name": user,
			"case_name": case,
		},
		sensitive_literals=literals,
	)
	return {
		"embedding_id": embedding_id,
		"classification": EMBEDDING_CLASSIFICATION,
		"encrypted": True,
		"public_index": public_row,
		"user_id": user,
		"case_id": case,
	}


def open_private_embedding(
	*,
	user_id: str,
	case_id: str,
	embedding_id: str,
	key: bytes,
	key_id: str,
	principal_id: str = "",
) -> Dict[str, Any]:
	from integrations.private_storage import open_private_artifact

	user, case = _case_cache_key(user_id, case_id)
	with _CASE_CACHE_LOCK:
		envelope = _CASE_EMBEDDING_CACHE.get((user, case), {}).get(str(embedding_id))
	if envelope is None:
		return {"found": False, "embedding_id": embedding_id, "classification": EMBEDDING_CLASSIFICATION}
	opened = open_private_artifact(
		envelope,
		binding=_embedding_binding(user, case, principal_id or user),
		key=key,
		expected_key_id=key_id,
	)
	payload = json.loads(opened.decode("utf-8"))
	return {
		"found": True,
		"embedding_id": embedding_id,
		"classification": EMBEDDING_CLASSIFICATION,
		"vector": payload.get("vector"),
		"source_text": payload.get("source_text"),
	}


def _bounded_private_timeout(value: Any) -> float:
	if value is None:
		return PRIVATE_TURN_TIMEOUT_SECONDS
	if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0:
		raise ValueError("privacy_denied:malformed_timeout")
	return min(float(value), PRIVATE_TURN_TIMEOUT_SECONDS)


def _apply_case_aliases(text: str, replacements: list[tuple[str, str]]) -> str:
	rendered = str(text)
	for literal, alias in replacements:
		rendered = rendered.replace(literal, alias)
	return rendered


def build_minimal_turn_prompt(
	*,
	user_id: str,
	case_id: str,
	relevant_facts: list,
	rule_gaps: list,
	unrelated_evidence: Optional[list] = None,
	sensitive_literals: Optional[list] = None,
	key: bytes,
	key_id: str,
	principal_id: str = "",
	turn_id: str = "",
) -> Dict[str, Any]:
	"""Build one reversible, case-local prompt from facts and rule gaps.

	Unrelated evidence is not copied into the prompt. Sensitive literals are
	replaced with aliases that ``resolve_case_alias`` can open for this user
	and case only.
	"""

	if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
		raise ValueError("privacy_denied:malformed_key")
	if not isinstance(relevant_facts, list) or not relevant_facts:
		raise ValueError("privacy_denied:malformed_turn")
	if not isinstance(rule_gaps, list) or not rule_gaps:
		raise ValueError("privacy_denied:malformed_turn")
	facts: list[tuple[str, str, list[str]]] = []
	for item in relevant_facts:
		if not isinstance(item, Mapping):
			raise ValueError("privacy_denied:malformed_turn")
		fact_id = str(item.get("fact_id") or "").strip()
		text = str(item.get("text") or "")
		rules = [str(rule).strip() for rule in list(item.get("supports_rules") or []) if str(rule).strip()]
		if not fact_id or not text.strip():
			raise ValueError("privacy_denied:malformed_turn")
		facts.append((fact_id, text, rules))
	gaps: list[tuple[str, str]] = []
	for item in rule_gaps:
		if not isinstance(item, Mapping):
			raise ValueError("privacy_denied:malformed_turn")
		rule_id = str(item.get("rule_id") or "").strip()
		missing = str(item.get("missing") or "").strip()
		if not rule_id or not missing:
			raise ValueError("privacy_denied:malformed_turn")
		gaps.append((rule_id, missing))
	unrelated = [str(item) for item in list(unrelated_evidence or []) if str(item)]
	literals: list[str] = []
	for raw in list(sensitive_literals or []) + unrelated:
		literal = str(raw or "")
		if literal and literal not in literals:
			literals.append(literal)
	literals.sort(key=len, reverse=True)
	replacements: list[tuple[str, str]] = []
	alias_rows: list[Dict[str, Any]] = []
	for literal in literals:
		material = json.dumps([str(user_id), str(case_id), literal], ensure_ascii=True, separators=(",", ":")).encode("utf-8")
		digest = hmac.new(bytes(key), b"complaint-private-turn-alias-v1\0" + material, hashlib.sha256).hexdigest()[:32]
		alias = f"alias_{digest}"
		if literal in alias:
			raise ValueError("privacy_denied:malformed_alias")
		remember_case_alias(
			user_id=user_id,
			case_id=case_id,
			alias=alias,
			canonical=literal,
			key=key,
			key_id=key_id,
			principal_id=principal_id or user_id,
		)
		replacements.append((literal, alias))
		alias_rows.append({"alias": alias, "reversible": True, "case_local": True})
	lines = [
		f"schema: {MINIMAL_TURN_SCHEMA}",
		f"turn_id: {str(turn_id or 'turn').strip() or 'turn'}",
		"relevant_facts:",
	]
	preserved_fact_ids: list[str] = []
	for fact_id, text, rules in facts:
		rendered = _apply_case_aliases(text, replacements)
		rule_text = ",".join(rules)
		lines.append(f"- {fact_id} [{rule_text}]: {rendered}")
		preserved_fact_ids.append(fact_id)
	lines.append("rule_gaps:")
	preserved_rules: list[str] = []
	for rule_id, missing in gaps:
		lines.append(f"- {rule_id}: {_apply_case_aliases(missing, replacements)}")
		preserved_rules.append(rule_id)
	prompt = "\n".join(lines)
	for literal, _alias in replacements:
		if literal in prompt:
			raise ValueError("privacy_denied:literal_survived")
	for blob in unrelated:
		if blob in prompt:
			raise ValueError("privacy_denied:unrelated_evidence_included")
	return {
		"schema": MINIMAL_TURN_SCHEMA,
		"prompt": prompt,
		"aliases": alias_rows,
		"preserved_fact_ids": preserved_fact_ids,
		"preserved_rule_ids": preserved_rules,
		"excluded_evidence_count": len(unrelated),
		"user_id": str(user_id or ""),
		"case_id": str(case_id or ""),
	}


def private_llm_request_cache() -> list[Dict[str, Any]]:
	"""Bounded request metadata; private prompt bodies are never retained here."""

	with _PRIVATE_REQUEST_LOCK:
		return deepcopy(_PRIVATE_REQUEST_CACHE)


def private_llm_request_traces() -> list[Dict[str, Any]]:
	"""Redacted traces. Prompt bodies are omitted."""

	with _PRIVATE_REQUEST_LOCK:
		return deepcopy(_PRIVATE_REQUEST_TRACES)


def clear_private_llm_request_cache() -> None:
	with _PRIVATE_REQUEST_LOCK:
		_PRIVATE_REQUEST_CACHE.clear()
		_PRIVATE_REQUEST_TRACES.clear()


def _privacy_choice_from_context(context: Mapping[str, Any]) -> Dict[str, Any]:
	policy = context.get("policy") if isinstance(context.get("policy"), Mapping) else {}
	permitted = policy.get("permitted_remote") if isinstance(policy.get("permitted_remote"), Mapping) else {}
	return {
		"processing_mode": str(policy.get("processing_mode") or ""),
		"cloud_processing_enabled": bool(policy.get("cloud_processing_enabled")),
		"provider": str(permitted.get("provider") or ""),
		"model": str(permitted.get("model") or ""),
		"scope": str(policy.get("scope") or ""),
		"persisted_opt_in": str(policy.get("processing_mode") or "") == PRIVACY_PROCESSING_GROK,
		"consent_status": str((policy.get("consent") or {}).get("status") or "") if isinstance(policy.get("consent"), Mapping) else "",
	}


def _private_turn_denial(reason: str) -> Dict[str, Any]:
	return {
		"status": "error",
		"text": "",
		"error": reason,
		"privacy_decision": "denied",
		"dispatch": "none",
		"prompt_logged": False,
		"campaign_authorizes_stored_complaints": False,
		"authorized_by": "",
		"timeout_seconds": None,
		"provider_name": "",
		"model_name": "",
		"resumable": True,
	}


def dispatch_private_turn(
	*,
	privacy_context: Any,
	relevant_facts: list,
	rule_gaps: list,
	unrelated_evidence: Optional[list] = None,
	sensitive_literals: Optional[list] = None,
	key: bytes,
	key_id: str,
	provider: Optional[str] = None,
	model_name: Optional[str] = None,
	timeout: Any = None,
	campaign_settings: Optional[Mapping[str, Any]] = None,
	stored_user_complaint: bool = False,
	principal_id: str = "",
	turn_id: str = "",
	**options: Any,
) -> Dict[str, Any]:
	"""Send one minimal prompt only after an explicit Grok opt-in.

	Local private mode returns before preparation, architecture classification,
	provider dispatch, and request caching. A campaign model setting cannot
	supply that opt-in.
	"""

	campaign_authorizes = development_campaign_authorizes_user_complaint_egress(campaign_settings)
	if campaign_authorizes:
		return _private_turn_denial(PRIVACY_DENIAL_MALFORMED)
	block = _privacy_context_block_reason(
		privacy_context,
		provider=provider or PRIVACY_GROK_PROVIDER,
		model_name=model_name or PRIVACY_GROK_MODEL,
		options={key: value for key, value in options.items() if key in _PRIVATE_GENERATION_OPTIONS},
	)
	if privacy_context is None or block:
		reason = block or PRIVACY_DENIAL_CLOUD_DISABLED
		if stored_user_complaint and campaign_settings is not None and reason == PRIVACY_DENIAL_CLOUD_DISABLED:
			reason = PRIVACY_DENIAL_CLOUD_DISABLED
		return _private_turn_denial(str(reason))
	if not isinstance(privacy_context, Mapping):
		return _private_turn_denial(PRIVACY_DENIAL_MALFORMED)
	choice = _privacy_choice_from_context(privacy_context)
	if choice["provider"] != PRIVACY_GROK_PROVIDER or choice["model"] != PRIVACY_GROK_MODEL:
		return _private_turn_denial(PRIVACY_DENIAL_SCOPE)
	if provider is not None and str(provider).strip() not in {"", PRIVACY_GROK_PROVIDER}:
		return _private_turn_denial(PRIVACY_DENIAL_SCOPE)
	if model_name is not None and str(model_name).strip() not in {"", PRIVACY_GROK_MODEL}:
		return _private_turn_denial(PRIVACY_DENIAL_SCOPE)
	if stored_user_complaint and campaign_settings is not None:
		return _private_turn_denial("privacy_denied:supervisor_fixtures_only")
	try:
		bounded_timeout = _bounded_private_timeout(timeout if timeout is not None else options.get("timeout"))
		minimal = build_minimal_turn_prompt(
			user_id=str(privacy_context.get("user_id") or ""),
			case_id=str(privacy_context.get("case_id") or ""),
			relevant_facts=relevant_facts,
			rule_gaps=rule_gaps,
			unrelated_evidence=unrelated_evidence,
			sensitive_literals=sensitive_literals,
			key=key,
			key_id=key_id,
			principal_id=principal_id,
			turn_id=turn_id,
		)
	except ValueError as exc:
		code = str(exc)
		if not code.startswith("privacy_denied:"):
			code = "privacy_denied:malformed_turn"
		return _private_turn_denial(code)
	prompt = str(minimal["prompt"])
	payload = {
		"provider": PRIVACY_GROK_PROVIDER,
		"model": PRIVACY_GROK_MODEL,
		"timeout_seconds": bounded_timeout,
		"prompt": "",
		"request_reference": os.urandom(16).hex(),
		"privacy_choice": dict(choice),
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
	}
	trace = {
		"provider": PRIVACY_GROK_PROVIDER,
		"model": PRIVACY_GROK_MODEL,
		"timeout_seconds": bounded_timeout,
		"privacy_choice": dict(choice),
		"prompt_included": False,
		"dispatch": "attempted",
		"allow_local_fallback": False,
		"allow_cross_provider_fallback": False,
	}
	with _PRIVATE_REQUEST_LOCK:
		_PRIVATE_REQUEST_CACHE.append(dict(payload))
		_PRIVATE_REQUEST_TRACES.append(dict(trace))
		del _PRIVATE_REQUEST_CACHE[:-8]
		del _PRIVATE_REQUEST_TRACES[:-8]
	forward = {
		key: value
		for key, value in options.items()
		if key in _PRIVATE_GENERATION_OPTIONS and key not in {"timeout", "allow_local_fallback", "allow_cross_provider_fallback"}
	}
	token = _BLOCK_ARCH_CLASSIFICATION.set(True)
	try:
		generated = generate_text_with_metadata(
			prompt,
			provider=PRIVACY_GROK_PROVIDER,
			model_name=PRIVACY_GROK_MODEL,
			timeout=bounded_timeout,
			allow_local_fallback=False,
			allow_cross_provider_fallback=False,
			complaint_privacy_context=privacy_context,
			**forward,
		)
	finally:
		_BLOCK_ARCH_CLASSIFICATION.reset(token)
	if not isinstance(generated, dict):
		generated = _private_turn_denial("private_generation_failed")
	result = dict(generated)
	result.pop("prompt", None)
	result["privacy_choice"] = choice
	result["timeout_seconds"] = bounded_timeout
	result["campaign_authorizes_stored_complaints"] = False
	result["authorized_by"] = "explicit_grok_opt_in"
	result["minimal_turn_schema"] = MINIMAL_TURN_SCHEMA
	result["preserved_fact_ids"] = list(minimal["preserved_fact_ids"])
	result["preserved_rule_ids"] = list(minimal["preserved_rule_ids"])
	result["excluded_evidence_count"] = minimal["excluded_evidence_count"]
	return result


RECOVERY_SCHEMA = "intake-model-recovery/v1"
RECOVERY_MAX_ATTEMPTS = 3
RECOVERY_BACKOFF_BASE_S = 0.25
RECOVERY_BACKOFF_CAP_S = 0.20
_RECOVERY_RETRYABLE = frozenset({"rate_limit", "delayed", "disconnect"})
_RECOVERY_TERMINAL = frozenset({
	"auth_failure", "quota", "malformed", "schema_drift", "cancelled",
	"wrong_model", "wrong_provider",
})
_RECOVERY_INJECTIONS = _RECOVERY_RETRYABLE | _RECOVERY_TERMINAL | frozenset({"available"})


def intake_recovery_idempotency_key(request_id: str) -> str:
	"""One stable key for every attempt of the same synthetic interview turn."""

	if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
		raise ValueError("request_id must be 32 lowercase hex characters")
	return "intake-recovery:" + request_id


def _recovery_backoff_seconds(failed_attempts: int) -> float:
	if type(failed_attempts) is not int or failed_attempts < 1:
		raise ValueError("failed_attempts")
	delay = RECOVERY_BACKOFF_BASE_S * (2 ** (failed_attempts - 1))
	if delay > RECOVERY_BACKOFF_CAP_S:
		delay = RECOVERY_BACKOFF_CAP_S
	return delay


def _optional_live_canary(*, include_live_canary: bool, canary_transport: Any) -> Dict[str, Any]:
	"""Label an optional canary without letting it decide the offline result.

	Injected transports can claim ``live_canary``; that claim is ignored.
	"""

	record: Dict[str, Any] = {
		"label": "optional_live_canary" if include_live_canary else "not_requested",
		"blocks_offline_completion": False,
		"live_canary": False,
		"status": "not_requested",
		"fabricated_pass": False,
	}
	if not include_live_canary:
		return record
	record["status"] = "unverified"
	if canary_transport is None:
		record["status"] = "not_dispatched"
		return record
	if not callable(canary_transport):
		raise ValueError("canary_transport must be callable")
	try:
		raw = canary_transport(**pinned_grok47_canary_kwargs())
	except Exception:
		record["status"] = "unavailable"
		return record
	projected = interpret_canary_dispatch(raw)
	record["canary_dispatch"] = projected.get("canary_dispatch", "unverified")
	record["status"] = "unverified"
	record["live_canary"] = False
	return record


def qualify_intake_model_recovery(
	interview_state: Mapping[str, Any],
	*,
	provider: str,
	model_name: str,
	request_id: str,
	script: list,
	transport: Any = None,
	sleeper: Any = None,
	deadline_s: float = 5.0,
	include_live_canary: bool = False,
	canary_transport: Any = None,
	cancel_event: Any = None,
) -> Dict[str, Any]:
	"""Replay one synthetic interview turn under injected provider faults.

	``interview_state`` is only read. Eligible transient faults (``rate_limit``,
	``delayed``, ``disconnect``) retry with one idempotency key and a capped
	backoff. Auth, quota, broken JSON, schema drift, cancellation, and a wrong
	model or provider stop immediately. The optional live canary is a separate
	labeled record and cannot turn an offline run into a live pass.
	"""

	if not isinstance(interview_state, Mapping):
		raise TypeError("interview_state must be a mapping")
	if type(include_live_canary) is not bool:
		raise ValueError("include_live_canary must be an explicit boolean")
	if type(script) is not list or not 1 <= len(script) <= 8:
		raise ValueError("script must list one to eight dispositions")
	if any(type(item) is not str or item not in _RECOVERY_INJECTIONS for item in script):
		raise ValueError("script contains an unknown disposition")
	if type(deadline_s) not in (int, float) or not math.isfinite(float(deadline_s)) or deadline_s <= 0:
		raise ValueError("deadline_s must be a positive finite number")
	if sleeper is None:
		sleeper = time.sleep
	if not callable(sleeper):
		raise ValueError("sleeper must be callable")
	if transport is not None and not callable(transport):
		raise ValueError("transport must be callable")
	before = deepcopy(dict(interview_state))
	key = intake_recovery_idempotency_key(request_id)
	deadline = time.monotonic() + float(deadline_s)
	calls: list[str] = []
	backoffs: list[float] = []

	def finish(disposition: str, *, attempts: int, dispatch: str) -> Dict[str, Any]:
		canary = _optional_live_canary(
			include_live_canary=include_live_canary,
			canary_transport=canary_transport,
		)
		preserved = deepcopy(dict(interview_state)) == before
		pinned = disposition not in {"wrong_model", "wrong_provider"}
		if any(item > RECOVERY_BACKOFF_CAP_S for item in backoffs) or len(set(calls)) > 1:
			disposition = "idempotency_or_backoff_violation"
			preserved = False
		return {
			"schema": RECOVERY_SCHEMA,
			"request_id": request_id,
			"disposition": disposition,
			"failure_kind": "" if disposition == "available" else disposition,
			"attempts": attempts,
			"dispatch": dispatch,
			"idempotency_key": key,
			"idempotency_keys": list(calls),
			"backoff_seconds": list(backoffs),
			"backoff_cap_seconds": RECOVERY_BACKOFF_CAP_S,
			"max_attempts": RECOVERY_MAX_ATTEMPTS,
			"retryable": disposition in _RECOVERY_RETRYABLE,
			"state_preserved": preserved,
			"interview_state": before,
			"live_canary": False,
			"offline_unit_complete": preserved,
			"optional_live_canary": canary,
			"provider": PINNED_GROK_PROVIDER if pinned else "",
			"model_name": PINNED_GROK_MODEL if pinned else "",
			"requested_provider": str(provider or ""),
			"requested_model": str(model_name or ""),
		}

	provider_text = str(provider or "").strip()
	model_text = str(model_name or "").strip()
	if provider_text != PINNED_GROK_PROVIDER or model_text != PINNED_GROK_MODEL:
		disposition = "wrong_model" if provider_text == PINNED_GROK_PROVIDER else "wrong_provider"
		return finish(disposition, attempts=0, dispatch="none")
	if script[0] == "auth_failure":
		return finish("auth_failure", attempts=0, dispatch="none")

	attempts = 0
	disposition = script[-1]
	for index, injection in enumerate(script):
		if attempts >= RECOVERY_MAX_ATTEMPTS:
			break
		if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
			return finish("cancelled", attempts=attempts, dispatch="attempted" if attempts else "none")
		if deadline - time.monotonic() <= 0:
			return finish("delayed", attempts=attempts, dispatch="attempted" if attempts else "none")
		if transport is not None:
			transport(attempt=attempts + 1, idempotency_key=key, injection=injection)
		calls.append(key)
		attempts += 1
		disposition = injection
		if injection == "available":
			return finish("available", attempts=attempts, dispatch="attempted")
		if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
			return finish("cancelled", attempts=attempts, dispatch="attempted")
		if injection not in _RECOVERY_RETRYABLE:
			return finish(injection, attempts=attempts, dispatch="attempted")
		if index + 1 >= len(script) or attempts >= RECOVERY_MAX_ATTEMPTS:
			return finish(injection, attempts=attempts, dispatch="attempted")
		delay = _recovery_backoff_seconds(attempts)
		remaining = deadline - time.monotonic()
		if remaining <= 0:
			return finish(injection, attempts=attempts, dispatch="attempted")
		if delay > remaining:
			delay = remaining
		sleeper(delay)
		backoffs.append(delay)
	return finish(disposition, attempts=attempts, dispatch="attempted" if attempts else "none")


def redact_generation_diagnostic(record: Mapping[str, Any] | None) -> Dict[str, Any]:
	"""Private generation diagnostics share the storage allow-list."""

	from integrations.ipfs_datasets.storage import redact_private_diagnostic

	return redact_private_diagnostic(record)


def public_query_reference(query: str) -> Dict[str, Any]:
	"""Allocate an opaque public reference for a private query."""

	return {
		"schema": "public-query-ref/v1",
		"query_ref": os.urandom(32).hex(),
		"classification": "opaque_private_ref",
	}


# Per-operation consent. Grok raw-intake consent authorizes one provider and
# one data class. It does not authorize web/archive providers, tools, or any
# other case data class. Invocation bindings are process-local and case-scoped.
OPERATION_CONSENT_CONTRACT = "complaint_operation_consent"
OPERATION_CONSENT_VERSION = "1"
_RAW_INTAKE_PURPOSES = frozenset({"extract_facts", "propose_questions"})
_CITATION_PURPOSES = frozenset({"citation_acquisition", "public_law_citation"})
_PURPOSE_QUERY_FIELDS = {
	"extract_facts": ("source_text", "target_ref"),
	"propose_questions": ("gap_code", "target_ref"),
	"explain_candidate": ("candidate_ref", "gap_code"),
	"citation_acquisition": ("citation",),
	"public_law_citation": ("citation",),
}
_UNRELATED_REMOTE_KINDS = frozenset({
	"web_search", "web", "web_provider", "archive", "archive_fetch", "archive_provider", "wayback",
})
_REMOTE_INVOCATIONS: Dict[str, Dict[str, Any]] = {}
_INVOCATION_LOCK = threading.Lock()


def clear_remote_invocation_bindings() -> None:
	with _INVOCATION_LOCK:
		_REMOTE_INVOCATIONS.clear()


def _consent_generation(consent: Any) -> int:
	if not isinstance(consent, Mapping):
		return 0
	raw = consent.get("generation")
	if type(raw) is not int or isinstance(raw, bool) or raw < 0:
		return 0
	return raw


def _bounded_query_piece(value: Any, *, limit: int) -> str:
	if type(value) is not str:
		return ""
	text = value.strip()
	if not text or len(text.encode("utf-8")) > limit:
		return ""
	if any(ord(char) < 32 for char in text):
		return ""
	return text


def minimize_purpose_query(
	purpose: str,
	*,
	private_fields: Optional[Mapping[str, Any]] = None,
	citation: Any = None,
	complaint_text: Any = None,
) -> Dict[str, Any]:
	"""Keep a purpose query to its declared fields.

	Public-law queries carry the citation only. A complaint body passed beside
	the citation is not copied into the query.
	"""

	purpose_id = purpose if type(purpose) is str else ""
	complaint = complaint_text if type(complaint_text) is str else ""
	if purpose_id in _CITATION_PURPOSES:
		citation_text = _bounded_query_piece(citation, limit=160)
		if complaint and citation_text:
			citation_text = citation_text.replace(complaint, "").strip()
		query = {
			"purpose": purpose_id,
			"query_class": "public_law_citation_only",
			"citation": citation_text,
		}
		return query
	allowed = _PURPOSE_QUERY_FIELDS.get(purpose_id, ())
	source = private_fields if isinstance(private_fields, Mapping) else {}
	fields: Dict[str, str] = {}
	for key in allowed:
		piece = _bounded_query_piece(source.get(key), limit=500 if key == "source_text" else 128)
		if piece and (not complaint or piece != complaint):
			fields[key] = piece
	return {
		"purpose": purpose_id,
		"query_class": "minimized_fields",
		"fields": fields,
	}


def _explicit_operation_grant(
	consent: Any,
	*,
	purpose: str,
	provider_kind: str,
	data_class: str,
) -> Optional[Mapping[str, Any]]:
	if not isinstance(consent, Mapping) or consent.get("revoked") is True:
		return None
	grants = consent.get("grants")
	if not isinstance(grants, list):
		return None
	for grant in grants:
		if not isinstance(grant, Mapping) or grant.get("explicit") is not True:
			continue
		if grant.get("tools") is not False:
			continue
		if str(grant.get("purpose") or "") != purpose:
			continue
		if str(grant.get("provider_kind") or "") != provider_kind:
			continue
		if str(grant.get("data_class") or "") != data_class:
			continue
		if provider_kind == "grok_inference":
			if str(grant.get("provider") or "") != PRIVACY_GROK_PROVIDER:
				continue
			if str(grant.get("model") or "") != PRIVACY_GROK_MODEL:
				continue
		return grant
	return None


def evaluate_remote_operation_consent(
	record: Any,
	*,
	user_id: str,
	case_id: str,
	purpose: str,
	provider_kind: str,
	data_class: str,
	tools: bool = False,
) -> Dict[str, Any]:
	"""Decide one remote operation from an already loaded owner/case record.

	This function does not load a provider. Missing, local, and revoked
	records refuse effectful dispatch. Raw-intake Grok consent matches only
	``grok_cli`` / ``grok-4.7`` for ``raw_intake`` purposes that do not use tools.
	"""

	def decision(code: str, *, effectful: bool = False, local: bool = False, generation: int = 0, revoked: bool = False) -> Dict[str, Any]:
		return {
			"effectful_allowed": effectful,
			"local_query_allowed": local,
			"code": code,
			"generation": generation,
			"revoked": revoked,
			"tools_authorized": False,
			"provider": PRIVACY_GROK_PROVIDER if effectful and provider_kind == "grok_inference" else "",
			"model": PRIVACY_GROK_MODEL if effectful and provider_kind == "grok_inference" else "",
			"data_class": data_class if type(data_class) is str else "",
			"provider_kind": provider_kind if type(provider_kind) is str else "",
			"live_model_identity_verified": False,
		}

	if not isinstance(record, Mapping) or record.get("found") is False:
		return decision("consent_missing")
	if record.get("case_match") is False:
		return decision("wrong_case")
	if str(record.get("user_id") or "") != str(user_id or "") or str(record.get("case_id") or "") != str(case_id or ""):
		return decision("wrong_case")
	consent = record.get("operation_consent")
	generation = _consent_generation(consent)
	revoked = isinstance(consent, Mapping) and consent.get("revoked") is True
	purpose_id = purpose if type(purpose) is str else ""
	kind = provider_kind if type(provider_kind) is str else ""
	kind_normalized = kind.strip().lower()
	data = data_class if type(data_class) is str else ""
	local_kind = kind_normalized in {"", "none", "local", "local_private"}
	if purpose_id in _CITATION_PURPOSES and local_kind and tools is not True:
		return decision("local_only", effectful=False, local=True, generation=generation, revoked=revoked)
	if tools is True:
		return decision("tools_not_authorized", effectful=False, generation=generation, revoked=revoked)
	inspection = inspect_privacy_policy(record.get("privacy_policy"), user_id=str(user_id or ""), case_id=str(case_id or ""))
	policy = inspection.get("policy") if isinstance(inspection.get("policy"), Mapping) else {}
	mode = str(policy.get("processing_mode") or "")
	cloud = inspection.get("admitted") is True and inspection.get("cloud_processing_enabled") is True and mode == PRIVACY_PROCESSING_GROK
	if revoked:
		return decision("consent_revoked", effectful=False, generation=generation, revoked=True)
	if not cloud:
		if not inspection.get("admitted"):
			return decision("consent_missing", effectful=False, generation=generation, revoked=False)
		return decision("local_private", effectful=False, generation=generation, revoked=False)
	explicit = _explicit_operation_grant(consent, purpose=purpose_id, provider_kind=kind_normalized, data_class=data)
	raw_intake = (
		explicit is None
		and kind_normalized == "grok_inference"
		and data == "raw_intake"
		and purpose_id in _RAW_INTAKE_PURPOSES
	)
	if explicit is not None or raw_intake:
		return decision("authorized", effectful=True, generation=generation, revoked=False)
	if kind_normalized in _UNRELATED_REMOTE_KINDS or kind_normalized != "grok_inference":
		return decision("provider_not_authorized", effectful=False, generation=generation, revoked=False)
	if data != "raw_intake":
		return decision("data_class_not_authorized", effectful=False, generation=generation, revoked=False)
	return decision("purpose_not_authorized", effectful=False, generation=generation, revoked=False)


def bind_remote_invocation(
	*,
	user_id: str,
	case_id: str,
	purpose: str,
	provider_kind: str,
	data_class: str,
	generation: int,
) -> str:
	"""Bind one invocation to this owner and case. Another case cannot reuse it."""

	invocation_id = os.urandom(16).hex()
	binding = {
		"invocation_id": invocation_id,
		"user_id": str(user_id or ""),
		"case_id": str(case_id or ""),
		"purpose": purpose if type(purpose) is str else "",
		"provider_kind": provider_kind if type(provider_kind) is str else "",
		"data_class": data_class if type(data_class) is str else "",
		"generation": int(generation),
		"live_model_identity_verified": False,
	}
	with _INVOCATION_LOCK:
		_REMOTE_INVOCATIONS[invocation_id] = binding
	return invocation_id


def remote_invocation_binding(invocation_id: str) -> Optional[Dict[str, Any]]:
	if type(invocation_id) is not str:
		return None
	with _INVOCATION_LOCK:
		found = _REMOTE_INVOCATIONS.get(invocation_id)
		return deepcopy(found) if found is not None else None


def accept_late_remote_result(
	record: Any,
	*,
	invocation_id: str,
	user_id: str,
	case_id: str,
	bound_graph_revision: Optional[str] = None,
	current_graph_revision: Optional[str] = None,
	bound_session_revision: Optional[int] = None,
	current_session_revision: Optional[int] = None,
) -> Dict[str, Any]:
	"""Re-read consent before a late result can be accepted.

	The caller supplies the persisted record loaded immediately before this
	call. A revoked choice, a different case, or a changed graph or session
	revision leaves the result unaccepted.
	"""

	binding = remote_invocation_binding(invocation_id)
	if binding is None:
		return {"accepted": False, "code": "invocation_missing", "live_model_identity_verified": False}
	if binding["user_id"] != str(user_id or "") or binding["case_id"] != str(case_id or ""):
		return {"accepted": False, "code": "invocation_not_reusable", "live_model_identity_verified": False}
	revision_checked = (
		bound_graph_revision is not None or current_graph_revision is not None
		or bound_session_revision is not None or current_session_revision is not None
	)
	if revision_checked:
		graph_ok = type(bound_graph_revision) is str and bound_graph_revision == current_graph_revision
		session_ok = (
			bound_session_revision is None and current_session_revision is None
		) or (
			type(bound_session_revision) is int and bound_session_revision == current_session_revision
		)
		if bound_graph_revision is None and current_graph_revision is None:
			graph_ok = True
		if not graph_ok or not session_ok:
			return {"accepted": False, "code": "stale_revision", "live_model_identity_verified": False}
	decision = evaluate_remote_operation_consent(
		record,
		user_id=binding["user_id"],
		case_id=binding["case_id"],
		purpose=str(binding["purpose"]),
		provider_kind=str(binding["provider_kind"]),
		data_class=str(binding["data_class"]),
		tools=False,
	)
	if decision["generation"] != binding["generation"] or decision["revoked"] or not decision["effectful_allowed"]:
		code = "consent_revoked" if decision["revoked"] or decision["generation"] != binding["generation"] else str(decision["code"])
		if decision["code"] == "wrong_case":
			code = "wrong_case"
		return {"accepted": False, "code": code, "live_model_identity_verified": False}
	return {
		"accepted": True,
		"code": "accepted",
		"invocation_id": invocation_id,
		"live_model_identity_verified": False,
	}


__all__ = [
	"generate_text",
	"generate_text_via_router",
	"generate_text_with_metadata",
	"grok47_route_capability",
	"grok_cli_auth_present",
	"grok_cli_binary_present",
	"llm_router_status",
	"LLM_ROUTER_AVAILABLE",
	"LLM_ROUTER_ERROR",
	"HF_ROUTER_DEFAULT_BASE_URL",
	"PRIVACY_POLICY_CONTRACT",
	"PRIVACY_POLICY_VERSION",
	"PRIVACY_AT_REST_PROTECTION",
	"PRIVACY_GROK_PROVIDER",
	"PRIVACY_GROK_MODEL",
	"IntakeContractError",
	"INTAKE_REQUEST_OBJECT_SCHEMA",
	"INTAKE_REQUEST_SCHEMA_NAME",
	"INTAKE_REQUEST_SCHEMA_VERSION",
	"build_complaint_privacy_context",
	"classify_router_failure",
	"intake_request_response_format",
	"parse_intake_request",
	"pinned_hook_inference_route",
	"route_identity_diagnostics",
	"coerce_effective_privacy_policy",
	"complaint_data_class_inventory",
	"inspect_privacy_policy",
	"privacy_policy_for_mode",
	"EMBEDDING_CLASSIFICATION",
	"remember_case_alias",
	"resolve_case_alias",
	"case_alias_cache_public_view",
	"clear_case_private_caches",
	"store_private_embedding",
	"open_private_embedding",
	"redact_generation_diagnostic",
	"public_query_reference",
	"OPERATION_CONSENT_CONTRACT",
	"OPERATION_CONSENT_VERSION",
	"minimize_purpose_query",
	"evaluate_remote_operation_consent",
	"bind_remote_invocation",
	"remote_invocation_binding",
	"accept_late_remote_result",
	"generate_observed_hook_purpose",
	"clear_remote_invocation_bindings",
	"MINIMAL_TURN_SCHEMA",
	"PRIVATE_TURN_TIMEOUT_SECONDS",
	"ARCH_CLASSIFICATION_BLOCKED",
	"build_minimal_turn_prompt",
	"dispatch_private_turn",
	"RECOVERY_SCHEMA",
	"RECOVERY_MAX_ATTEMPTS",
	"RECOVERY_BACKOFF_CAP_S",
	"intake_recovery_idempotency_key",
	"qualify_intake_model_recovery",
	"PROVIDER_EGRESS_SCHEMA",
	"tui_processing_setting",
	"record_case_cloud_consent",
	"recorded_case_privacy_context",
	"clear_case_processing_consent",
	"provider_egress_captures",
	"clear_provider_egress_captures",
	"intercept_final_provider_request",
	"attempt_remote_bypass",
	"private_llm_request_cache",
	"private_llm_request_traces",
	"clear_private_llm_request_cache",
]
