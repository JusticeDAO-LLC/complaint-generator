"""Single production import path for accelerate inference routers.

Datasets modules named ``llm_router``, ``embeddings_router``, and
``multimodal_router`` are temporary aliases. New call sites use this facade,
which puts the accelerate checkout on ``sys.path`` before importing.
"""

from __future__ import annotations

import inspect
from typing import Any, Mapping

from integrations.ipfs_datasets.loader import ensure_import_paths, import_attr_optional, import_failure_message


COMPLAINT_PROVIDER_ALIASES = {
    "local": "local_hf",
    "local_hf": "local_hf",
    "hf": "local_hf",
    "huggingface": "hf_inference_api",
    "p2p": "p2p_task_queue",
    "p2p_task": "p2p_task_queue",
    "remote_queue": "p2p_task_queue",
    "task_queue": "p2p_task_queue",
}

# Names accelerate's routers accept. Complaint aliases are translated here,
# after the historical Hugging Face router rewrite in llm.py.
_ACCELERATE_PROVIDER_ALIASES = {
    "local": "huggingface",
    "local_hf": "huggingface",
    "hf": "huggingface",
    "hf_inference_api": "huggingface",
    "huggingface_inference": "huggingface",
    "huggingface_router": "huggingface",
    "system_one": "typesafe",
    "openai_vision": "openai",
}


def accelerate_provider_name(provider: str | None) -> str:
    """Return the complaint-facing provider id used by backend objects."""

    raw = str(provider or "").strip()
    if not raw:
        return ""
    return COMPLAINT_PROVIDER_ALIASES.get(raw.lower(), raw)


def normalize_accelerate_provider(provider: str | None) -> str | None:
    """Map a complaint provider id onto the accelerate router provider id."""

    raw = str(provider or "").strip()
    if not raw:
        return None
    mapped = _ACCELERATE_PROVIDER_ALIASES.get(raw.lower(), raw)
    return mapped or None


def _load_symbol(module_name: str, attr_name: str) -> tuple[Any | None, Any]:
    ensure_import_paths(module_name)
    return import_attr_optional(module_name, attr_name)


def load_llm_symbols() -> tuple[Any | None, Any | None, Any]:
    generate_text, error = _load_symbol("ipfs_accelerate_py.llm_router", "generate_text")
    trace, trace_error = _load_symbol("ipfs_accelerate_py.llm_router", "get_last_generation_trace")
    return generate_text, trace, error or trace_error


def load_observed_llm_symbols() -> tuple[Any | None, Any | None, Any | None]:
    """Optional additive native API; absence leaves live evidence unverified."""
    generate, _ = _load_symbol("ipfs_accelerate_py.llm_router", "generate_text_with_observation")
    result_type, _ = _load_symbol("ipfs_accelerate_py.cli_runtime.grok_invocation_observation", "ObservedTextGeneration")
    observation_type, _ = _load_symbol("ipfs_accelerate_py.cli_runtime.grok_invocation_observation", "GrokInvocationObservation")
    return generate, result_type, observation_type


def load_embedding_symbols() -> tuple[Any | None, Any | None, Any | None, Any | None, Any | None, Any]:
    from integrations.ipfs_datasets.loader import import_module_optional

    module_name = "ipfs_accelerate_py.embeddings_router"
    ensure_import_paths(module_name)
    embed_text, embed_text_error = import_attr_optional(module_name, "embed_text")
    embed_texts, embed_texts_error = import_attr_optional(module_name, "embed_texts")
    embed_texts_batched, batched_error = import_attr_optional(module_name, "embed_texts_batched")
    router_cls, router_error = import_attr_optional(module_name, "EmbeddingsRouter")
    embeddings_module, embeddings_module_error = import_module_optional(module_name)
    return (
        embed_text,
        embed_texts,
        embed_texts_batched,
        router_cls,
        embeddings_module,
        embed_text_error or embed_texts_error or batched_error or router_error or embeddings_module_error,
    )


def load_multimodal_symbols() -> tuple[Any | None, Any | None, Any | None, Any]:
    module_name = "ipfs_accelerate_py.multimodal_router"
    generate_multimodal_text, generate_error = _load_symbol(module_name, "generate_multimodal_text")
    build_multimodal_messages, messages_error = _load_symbol(module_name, "build_multimodal_messages")
    encode_image_as_data_url, encode_error = _load_symbol(module_name, "encode_image_as_data_url")
    return (
        generate_multimodal_text,
        build_multimodal_messages,
        encode_image_as_data_url,
        generate_error or messages_error or encode_error,
    )


def load_multimodal_generate() -> tuple[Any | None, Any]:
    return _load_symbol("ipfs_accelerate_py.multimodal_router", "generate_multimodal")


INFERENCE_OWNER = "ipfs_accelerate_py.llm_router"
PINNED_GROK_PROVIDER = "grok_cli"
PINNED_GROK_MODEL = "grok-4.7"
PINNED_GROK_CANARY_PROMPT = "GROK47_CANARY_OK"
PINNED_GROK_CANARY_MAX_TOKENS = 16
PINNED_GROK_CANARY_TIMEOUT_SECONDS = 60
# Aliases the native router would otherwise accept. They are refused here so
# a caller cannot slide onto Codex, xAI HTTP, or another Grok CLI spelling.
UNPINNED_GROK_PROVIDER_ALIASES = frozenset(
    {
        "grok",
        "grok-cli",
        "xai",
        "xai_cli",
        "xai-cli",
        "xai_api",
        "xai-api",
        "xai_grok",
        "grok_api",
        "grok-api",
        "grok_build",
        "grok-build",
        "grok_build_cli",
        "grok-build-cli",
    }
)


def pinned_grok47_adapter_binding(adapter: Any) -> dict[str, Any] | None:
    """Bind the pinned route to a live adapter signature.

    A missing or incompatible signature is not a successful fallback. Callers
    refuse dispatch when this returns None. The binding never enables fallback
    and never calls the adapter.
    """

    try:
        signature = inspect.signature(adapter)
    except (TypeError, ValueError):
        return None
    proposed = pinned_grok47_dispatch_kwargs()
    try:
        bound = signature.bind_partial(**proposed)
    except TypeError:
        return None
    arguments: dict[str, Any] = {}
    for name, value in bound.arguments.items():
        parameter = signature.parameters[name]
        if parameter.kind is inspect.Parameter.VAR_KEYWORD and isinstance(value, dict):
            arguments.update(value)
        else:
            arguments[name] = value
    if arguments.get("provider") != PINNED_GROK_PROVIDER or arguments.get("model_name") != PINNED_GROK_MODEL:
        return None
    if arguments.get("allow_local_fallback") is not False or arguments.get("allow_cross_provider_fallback") is not False:
        return None
    parameters = signature.parameters
    for name in ("provider", "model_name", "allow_local_fallback", "allow_cross_provider_fallback"):
        parameter = parameters.get(name)
        if parameter is None:
            if not any(item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters.values()):
                return None
        elif parameter.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.VAR_POSITIONAL}:
            return None
    return arguments


def pinned_grok47_dispatch_kwargs() -> dict[str, Any]:
    """Exact native-router kwargs for the pinned Grok 4.7 route.

    ``allow_cross_provider_fallback=False`` also disables the native
    default-model retry. Neither flag may be turned back on by callers.
    """

    return {
        "provider": PINNED_GROK_PROVIDER,
        "model_name": PINNED_GROK_MODEL,
        "allow_local_fallback": False,
        "allow_cross_provider_fallback": False,
    }


def pinned_grok47_canary_kwargs() -> dict[str, Any]:
    """Bounded no-tool canary. The prompt is a public synthetic token."""

    return {
        **pinned_grok47_dispatch_kwargs(),
        "max_tokens": PINNED_GROK_CANARY_MAX_TOKENS,
        "temperature": 0,
        "grok_max_turns": 1,
        "timeout": PINNED_GROK_CANARY_TIMEOUT_SECONDS,
        "grok_cli_cmd": ["grok"],
        "grok_tools": "",
        "grok_disallowed_tools": "search_tool,use_tool",
    }


def unpinned_grok_route_reason(provider: str | None, model_name: str | None) -> str:
    """Return a fixed refusal when the call is not the exact pinned route.

    The reason does not echo the supplied provider, model, or prompt.
    """

    raw_provider = str(provider or "").strip()
    raw_model = str(model_name or "").strip()
    if not raw_provider and not raw_model:
        return ""
    if raw_provider == PINNED_GROK_PROVIDER and raw_model == PINNED_GROK_MODEL:
        return ""
    alias = raw_provider.lower() in UNPINNED_GROK_PROVIDER_ALIASES
    grok_family = raw_provider == PINNED_GROK_PROVIDER or alias or raw_provider.lower().startswith("grok")
    if grok_family or (raw_model.lower().startswith("grok") and raw_provider != PINNED_GROK_PROVIDER):
        return (
            "Grok route unavailable: refusing an unpinned provider or model. "
            "The only admitted route is provider=grok_cli and model_name=grok-4.7. "
            "No Codex, model alias, other Grok version, or secondary cloud was contacted."
        )
    return ""


def vetted_route_observation(
    trace: Any,
    *,
    requested_provider: str,
    requested_model: str,
) -> dict[str, Any]:
    """Copy only router-selection identity. Never a live-canary claim.

    Response-cache hits populate the same thread-local trace. That proves
    which route the router selected, not that a provider was contacted and
    not the wire model reported by ``end.modelUsage``.
    """

    observed_provider = ""
    observed_model = ""
    if isinstance(trace, Mapping):
        provider_value = trace.get("effective_provider_name")
        model_value = trace.get("effective_model_name")
        if isinstance(provider_value, str):
            observed_provider = provider_value.strip()
        if isinstance(model_value, str):
            observed_model = model_value.strip()
    if not observed_provider or not observed_model:
        observation = "unverified"
        evidence_class = "absent"
    elif observed_provider != requested_provider or observed_model != requested_model:
        observation = "mismatched"
        evidence_class = "router_selection"
    else:
        observation = "verified"
        evidence_class = "router_selection"
    return {
        "requested_provider_name": requested_provider,
        "requested_model_name": requested_model,
        "observed_provider_name": observed_provider,
        "observed_model_name": observed_model,
        "route_observation": observation,
        "route_evidence_class": evidence_class,
        "live_canary": False,
        "provider_reported_model": "",
    }


def provider_reported_model_from_usage(payload: Any) -> str:
    """Read a single model id from ``end.modelUsage`` keys. Ignore values."""

    usage = payload
    if isinstance(payload, Mapping):
        end = payload.get("end")
        if isinstance(end, Mapping) and "modelUsage" in end:
            usage = end.get("modelUsage")
        elif "modelUsage" in payload:
            usage = payload.get("modelUsage")
    if not isinstance(usage, Mapping) or len(usage) != 1:
        return ""
    model_name = str(next(iter(usage.keys()))).strip()
    if not model_name or len(model_name) > 128 or any(char.isspace() for char in model_name):
        return ""
    return model_name


def interpret_canary_dispatch(result: Any) -> dict[str, Any]:
    """Project untrusted transport diagnostics without granting live authority.

    Native ``generate_text`` returns text, not its final wire envelope. An
    injected mapping can manufacture ``dispatch`` and ``end.modelUsage``;
    neither establishes a provider call or a provider-reported model. A future
    native evidence API needs invocation-bound provenance before either claim
    can be published here.
    """

    cache_hit = isinstance(result, Mapping) and (
        result.get("response_cache_hit") is True or result.get("cache_hit") is True
    )
    return {
        "live_canary": False,
        "provider_reported_model": "",
        "response_cache_hit": cache_hit,
        "canary_dispatch": "cache" if cache_hit else "unverified",
    }


def development_campaign_authorizes_user_complaint_egress(settings: Mapping[str, Any] | None) -> bool:
    """A supervisor campaign's Grok model setting is not user consent.

    Development runs use source and synthetic fixtures. Selecting grok-4.7
    for the campaign does not authorize transmission of stored complaints.
    """

    del settings
    return False


def router_symbol_status(loader_name: str) -> dict[str, Any]:
    """Return availability for one accelerate router without raising."""

    loaders = {
        "llm_router": lambda: load_llm_symbols()[0],
        "embeddings_router": lambda: load_embedding_symbols()[1],
        "multimodal_router": lambda: load_multimodal_symbols()[0],
    }
    loader = loaders.get(loader_name)
    if loader is None:
        return {"available": False, "error": f"unknown router {loader_name}"}
    try:
        symbol = loader()
    except Exception as exc:
        return {"available": False, "error": import_failure_message(exc) or str(exc)}
    return {"available": callable(symbol), "error": "" if callable(symbol) else "router symbol is not callable"}


__all__ = [
    "COMPLAINT_PROVIDER_ALIASES",
    "accelerate_provider_name",
    "load_embedding_symbols",
    "load_llm_symbols",
    "load_observed_llm_symbols",
    "load_multimodal_generate",
    "load_multimodal_symbols",
    "INFERENCE_OWNER",
    "PINNED_GROK_CANARY_MAX_TOKENS",
    "PINNED_GROK_CANARY_PROMPT",
    "PINNED_GROK_CANARY_TIMEOUT_SECONDS",
    "PINNED_GROK_MODEL",
    "PINNED_GROK_PROVIDER",
    "UNPINNED_GROK_PROVIDER_ALIASES",
    "interpret_canary_dispatch",
    "normalize_accelerate_provider",
    "pinned_grok47_adapter_binding",
    "pinned_grok47_canary_kwargs",
    "pinned_grok47_dispatch_kwargs",
    "provider_reported_model_from_usage",
    "router_symbol_status",
    "unpinned_grok_route_reason",
    "vetted_route_observation",
    "development_campaign_authorizes_user_complaint_egress",
]
