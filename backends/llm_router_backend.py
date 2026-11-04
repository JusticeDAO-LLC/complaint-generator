"""LLM Router Backend."""

import json
import logging
import os
import random
import math
import re
import time
import threading
import uuid

from integrations.ipfs_accelerate.routers import (
    COMPLAINT_PROVIDER_ALIASES,
    INFERENCE_OWNER,
    PINNED_GROK_CANARY_PROMPT,
    PINNED_GROK_MODEL,
    PINNED_GROK_PROVIDER,
    pinned_grok47_adapter_binding,
    unpinned_grok_route_reason,
    load_observed_llm_symbols,
)
from integrations.ipfs_datasets.llm import (
    LLM_ROUTER_AVAILABLE,
    PROVIDER_EGRESS_SCHEMA,
    classify_router_failure,
    generate_text_via_router as generate_text,
    generate_text_with_metadata,
    grok47_route_capability,
    intake_request_response_format,
    intercept_final_provider_request,
    provider_egress_options,
    recorded_case_privacy_context,
    tui_processing_setting,
    _generate_intake_with_metadata,
)

logger = logging.getLogger(__name__)

_PROVIDER_ALIASES = COMPLAINT_PROVIDER_ALIASES

_PROVIDER_ENV_KEYS = (
    'IPFS_DATASETS_PY_LLM_PROVIDER',
    'COMPLAINT_GENERATOR_LLM_PROVIDER',
    'LLM_ROUTER_PROVIDER',
)

# Provider-reported build label accepted for the pinned grok-4.7 route.
SUPPORTED_GROK_47_IDENTITIES = frozenset({PINNED_GROK_MODEL, "grok-4.7-build"})
SYNTHETIC_LIVE_CANARY_IDENTITY = "synthetic-live-canary"
REMOTE_PROVIDERS = frozenset({
    PINNED_GROK_PROVIDER,
    "openai",
    "codex",
    "codex_cli",
    "openrouter",
    "anthropic",
    "gemini",
    "gemini_cli",
    "huggingface_router",
    "hf_router",
    "huggingface_inference",
    "hf_inference_api",
})

_ERROR_TEXT = {
    "provider_unavailable": "Grok 4.7 is unavailable. No Codex or other model was substituted.",
    "substitution_refused": "Refusing a provider or model other than grok_cli/grok-4.7. The session was retained.",
    "route_unverified": "Grok 4.7 selection was not verified against a provider-supported identity.",
    "timeout": "The Grok 4.7 request exceeded its deadline. The session was retained.",
    "cancelled": "The Grok 4.7 request was cancelled. The session was retained.",
    "malformed_output": "Structured output validation failed. The session was retained.",
    "quota": "The Grok 4.7 quota was exhausted. The session was retained.",
    "unpinned_route": "Refusing an unpinned Grok route. No substitute model was contacted.",
    "privacy_denied": "Remote processing is not authorized for this case.",
}


class ProviderRouteError(Exception):
    """Bounded provider failure. The message never includes prompt text."""

    def __init__(self, payload):
        self.payload = dict(payload)
        super().__init__("llm_router_error: " + json.dumps(self.payload, sort_keys=True, default=str))


class _RouterCancelled(BaseException):
    """Unwind native stream capture through its owned-child cleanup."""


class LLMRouterBackend:
    """Backend that uses ipfs_datasets_py's llm_router for LLM routing."""

    def __init__(self, id, provider=None, model=None, **config):
        """
        Initialize the LLM Router Backend.

        Args:
            id: Backend identifier
            provider: Optional provider name (e.g., 'openrouter', 'local_hf')
            model: Optional model name
            **config: Additional configuration passed to generate_text
        """
        self.id = id
        raw_provider = self._resolve_provider_name(provider)
        self.provider = _PROVIDER_ALIASES.get(raw_provider.lower(), raw_provider) if raw_provider else None
        if model is None:
            if self.provider in {'codex', 'codex_cli'}:
                self.model = 'gpt-5.3-codex'
            elif str(self.provider).strip().lower() in {'hf', 'local_hf', 'hf_inference', 'hf_router', 'huggingface_inference', 'huggingface_router'}:
                self.model = (
                    os.getenv('LLM_ROUTER_FALLBACK_MODEL', '').strip()
                    or os.getenv('IPFS_DATASETS_PY_OPENROUTER_MODEL', '').strip()
                    or os.getenv('IPFS_DATASETS_PY_LLM_MODEL', '').strip()
                    or None
                )
            elif self.provider:
                self.model = (
                    os.getenv('IPFS_DATASETS_PY_LLM_MODEL', '').strip()
                    or os.getenv('COMPLAINT_GENERATOR_LLM_MODEL', '').strip()
                    or os.getenv('LLM_ROUTER_MODEL', '').strip()
                    or None
                )
            else:
                self.model = None
        else:
            self.model = model

        self.retry_max_attempts = int(config.pop('retry_max_attempts', 1) or 1)
        if not 1 <= self.retry_max_attempts <= 3:
            raise ValueError('retry_max_attempts must be between one and three')
        self.retry_backoff_base_s = float(config.pop('retry_backoff_base_s', 0.5) or 0.5)
        self.retry_backoff_max_s = float(config.pop('retry_backoff_max_s', 20.0) or 20.0)
        self.retry_jitter_s = float(config.pop('retry_jitter_s', 0.1) or 0.1)
        self.retryable_error_substrings = list(
            config.pop(
                'retryable_error_substrings',
                [
                    '429',
                    'rate limit',
                    'too many requests',
                    'temporarily unavailable',
                    'timeout',
                    'timed out',
                    'econnreset',
                    'connection reset',
                    'connection aborted',
                    'service unavailable',
                ],
            )
        )
        self.timeout_seconds = config.pop('timeout_seconds', config.pop('timeout', 60 if self.pinned_grok47 else None))
        if self.timeout_seconds is not None:
            self.timeout_seconds = float(self.timeout_seconds)
            if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
                raise ValueError("timeout must be finite and positive")
        self.intake_operation = config.pop('intake_operation', None)
        if self.intake_operation not in (None, 'propose_questions', 'extract_facts'):
            raise ValueError('intake_operation must be propose_questions or extract_facts')
        self.max_output_bytes = config.pop('max_output_bytes', 262144)
        if type(self.max_output_bytes) is not int or not 1 <= self.max_output_bytes <= 262144:
            raise ValueError('max_output_bytes must be between 1 and 262144')
        self.structured_output = bool(config.pop('structured_output', False))
        schema = config.pop('response_schema', None)
        self.response_schema_required = []
        if isinstance(schema, dict):
            required = schema.get("required", [])
            if isinstance(required, list):
                self.response_schema_required = [str(item) for item in required]
        elif isinstance(schema, list):
            self.response_schema_required = [str(item) for item in schema]
        self.forbid_model_substitution = config.pop('forbid_model_substitution', None)
        self.progress_callback = config.pop('progress_callback', None)
        self._cancel_event = config.pop('cancel_event', None) or threading.Event()

        self.config = config
        self.session_id = uuid.uuid4().hex
        self.session_retained = True
        self._recorded_privacy_context = None
        self._recorded_case_binding = None
        self._processing_setting = tui_processing_setting(None)
        self.progress_events = []
        self.task_receipts = []
        self.last_result_metadata = None

        self._stats_lock = threading.Lock()
        self._retry_stats = {
            'calls_total': 0,
            'attempts_total': 0,
            'retries_total': 0,
            'backoff_seconds_total': 0.0,
            'failures_total': 0,
        }

        if not LLM_ROUTER_AVAILABLE:
            raise ImportError(
                "llm_router not available. Please ensure ipfs_datasets_py submodule "
                "is initialized with: git submodule update --init --recursive"
            )

    @property
    def pinned_grok47(self) -> bool:
        return self.provider == PINNED_GROK_PROVIDER and self.model == PINNED_GROK_MODEL

    def apply_recorded_case_consent(self, user_id: str, case_id: str, data_class: str = "raw_intake") -> dict:
        """Bind this backend to the saved per-case choice. Local private stays local."""

        context = recorded_case_privacy_context(user_id=user_id, case_id=case_id, data_class=data_class)
        self._recorded_case_binding = (user_id, case_id, data_class)
        self._recorded_privacy_context = context
        self._processing_setting = tui_processing_setting(context.get("policy"))
        return dict(self._processing_setting)

    def processing_setting(self) -> dict:
        """Clear TUI copy of the processing choice currently bound to this backend."""

        if self._recorded_case_binding is not None:
            user_id, case_id, data_class = self._recorded_case_binding
            self._recorded_privacy_context = recorded_case_privacy_context(
                user_id=user_id, case_id=case_id, data_class=data_class,
            )
            self._processing_setting = tui_processing_setting(self._recorded_privacy_context.get("policy"))
        return dict(self._processing_setting)

    def remote_inference_disclosure(self) -> dict:
        """State whether this route sends complaint text off-box.

        Encryption at rest covers stored snapshots. It does not make a remote
        provider call private.
        """

        provider_name = self.provider if self.provider in REMOTE_PROVIDERS else "local_or_unverified"
        sends_remotely = provider_name in REMOTE_PROVIDERS or provider_name.lower().startswith("grok")
        return {
            "requested_provider": provider_name,
            "requested_model": self.model if self.model in SUPPORTED_GROK_47_IDENTITIES else "unverified",
            "sends_complaint_text_remotely": bool(sends_remotely),
            "encryption_at_rest_implies_private_remote_inference": False,
            "explanation": (
                "A grok_cli/grok-4.7 request sends the generation prompt, including any complaint text placed in that prompt, to the remote Grok provider. "
                "Encryption at rest protects stored session snapshots and does not make that remote inference private. "
                "Local-private processing does not send complaint text to a remote provider."
                if sends_remotely
                else "This provider is treated as local. Complaint text in the prompt is not described as a remote Grok inference. Encryption at rest still does not imply private remote inference."
            ),
        }

    def cancel(self) -> None:
        self._cancel_event.set()

    def configuration_receipt(self) -> dict:
        receipt = self._receipt(
            status="configured",
            error_code="",
            selected_provider="",
            selected_model="",
            route_observation="not_dispatched",
            provider_supported_identity=False,
            request_id="",
        )
        return receipt

    def sanitized_session_diagnostics(self) -> dict:
        latest = self.task_receipts[-1] if self.task_receipts else self.configuration_receipt()
        return {
            "session_id": self.session_id,
            "session_retained": True,
            "router": INFERENCE_OWNER,
            "requested_router": INFERENCE_OWNER,
            "selected_router": latest.get("selected_router") or "",
            "requested_provider": self.provider if self.provider in REMOTE_PROVIDERS else "unverified",
            "selected_provider": latest.get("selected_provider") or "",
            "requested_model": self.model if self.model in SUPPORTED_GROK_47_IDENTITIES else "unverified",
            "selected_model": latest.get("selected_model") or "",
            "route_observation": latest.get("route_observation") or "not_dispatched",
            "provider_supported_identity": bool(latest.get("provider_supported_identity")),
            "status": latest.get("status") or "configured",
            "error_code": latest.get("error_code") or "",
            "prompt_logged": False,
            "live_canary": False,
            "remote_inference": self.remote_inference_disclosure(),
        }

    def task_receipt_snapshot(self) -> list:
        if self.task_receipts:
            return [dict(item) for item in self.task_receipts]
        return [self.configuration_receipt()]

    @staticmethod
    def _resolve_provider_name(provider):
        explicit_provider = str(provider or '').strip()
        if explicit_provider:
            return explicit_provider
        for key in _PROVIDER_ENV_KEYS:
            value = str(os.getenv(key, '')).strip()
            if value:
                return value
        return ''

    def __call__(self, text, **kwargs):
        """
        Generate text using the llm_router.

        Args:
            text: The prompt text

        Returns:
            Generated text response
        """
        with self._stats_lock:
            self._retry_stats['calls_total'] += 1

        if "inference_purpose" in kwargs:
            purpose = kwargs.pop("inference_purpose")
            from mediator.hook_runtime import is_local_only_purpose
            # Purpose labels dispatch only through run_declared_purpose.
            # A direct call must not contact the provider.
            local = is_local_only_purpose(purpose)
            self._record(
                status="local_only" if local else "unavailable",
                error_code="" if local else "use_declared_hook_boundary",
                route_observation="not_dispatched",
            )
            return json.dumps({
                "model_dispatched": False,
                "status": "local_only" if local else "unavailable",
                "purpose": purpose if type(purpose) is str else "",
                "provider_invoked": False,
            })

        supplied = kwargs.get("intake_request_id") or kwargs.get("request_id")
        if type(supplied) is str and re.fullmatch(r"[0-9a-f]{32}", supplied):
            self._request_id = supplied
        else:
            self._request_id = uuid.uuid4().hex
        operation = kwargs["intake_operation"] if "intake_operation" in kwargs else self.intake_operation
        if operation is not None and (type(operation) is not str or operation not in {"propose_questions", "extract_facts"}):
            self._fail("malformed_output", route_observation="malformed")
        self._call_intake_operation = operation
        self._intake_target_refs = kwargs.get("intake_target_refs")
        source_text = kwargs.get("intake_source_text")
        self._intake_source_text = source_text if type(source_text) is str else ""
        privacy_context = kwargs.get("complaint_privacy_context")
        if privacy_context is None and self._recorded_case_binding is not None:
            self.processing_setting()
            privacy_context = self._recorded_privacy_context
        route_block = unpinned_grok_route_reason(self.provider, self.model)
        if route_block or (self._strict_route() and not self.pinned_grok47):
            self._fail("unpinned_route", route_observation="refused", selected_provider="", selected_model="")

        last_error = None
        max_attempts = max(1, self.retry_max_attempts)
        deadline = None
        if self._call_intake_operation:
            max_attempts = 1
            deadline = time.monotonic() + min(float(self.timeout_seconds or 60.0), 60.0)
        elif self._strict_route() and self.timeout_seconds is not None:
            deadline = time.monotonic() + float(self.timeout_seconds)
        for attempt in range(1, max_attempts + 1):
            self._raise_if_cancelled()
            if deadline is not None and time.monotonic() >= deadline:
                self._fail("timeout", route_observation="timeout")
            with self._stats_lock:
                self._retry_stats['attempts_total'] += 1
            self._emit_progress({"phase": "provider_wait", "attempt": attempt, "max_attempts": max_attempts, "router": INFERENCE_OWNER})
            try:
                metadata_payload = self._generate(text, privacy_context=privacy_context, deadline=deadline)
                self._raise_if_cancelled()
                if str(metadata_payload.get("status") or "").strip().lower() != "available":
                    kind = str(metadata_payload.get("failure_kind") or "")
                    error_code = {
                        "quota": "quota",
                        "timeout": "timeout",
                        "cancelled": "cancelled",
                        "malformed": "malformed_output",
                        "privacy_denied": "privacy_denied",
                        "route_unverified": "route_unverified",
                        "substitution_refused": "substitution_refused",
                    }.get(kind, "provider_unavailable")
                    self._fail(
                        error_code,
                        metadata=metadata_payload,
                        route_observation=kind or "unavailable",
                    )
                self._reject_substitution(metadata_payload)
                response = str(metadata_payload.get("text") or "")
                response = self._validate_structured(response)
                self.last_result_metadata = dict(metadata_payload)
                self._record(
                    status="available",
                    error_code="",
                    metadata=metadata_payload,
                    route_observation=self._observation(metadata_payload),
                    provider_supported_identity=self._identity_supported(metadata_payload),
                )
                self._emit_progress({"phase": "provider_done", "attempt": attempt, "router": INFERENCE_OWNER, "status": "available"})
                return response
            except _RouterCancelled:
                self._fail("cancelled", route_observation="cancelled")
            except TimeoutError:
                self._fail("timeout", route_observation="timeout")
            except ProviderRouteError as error:
                last_error = error
                if error.payload.get("error_code") in {"substitution_refused", "route_unverified", "malformed_output", "cancelled", "timeout", "quota", "unpinned_route", "privacy_denied"}:
                    with self._stats_lock:
                        self._retry_stats['failures_total'] += 1
                    raise
                retryable = self._is_retryable_error(error)
                if attempt >= max_attempts or not retryable:
                    with self._stats_lock:
                        self._retry_stats['failures_total'] += 1
                    raise
            except Exception as error:
                if deadline is not None and time.monotonic() >= deadline:
                    self._fail("timeout", route_observation="timeout")
                kind = classify_router_failure(error)
                if kind == "quota":
                    self._fail("quota", route_observation="quota")
                if kind == "malformed":
                    self._fail("malformed_output", route_observation="malformed")
                if kind == "cancelled":
                    self._fail("cancelled", route_observation="cancelled")
                last_error = error
                retryable = self._is_retryable_error(error)
                if attempt >= max_attempts or not retryable:
                    with self._stats_lock:
                        self._retry_stats['failures_total'] += 1
                    if self._strict_route():
                        self._fail("provider_unavailable", route_observation="unavailable")
                    raise Exception(f'llm_router_error: {str(error)}')

            backoff_s = self._compute_backoff_seconds(attempt)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._fail("timeout", route_observation="timeout")
                backoff_s = min(backoff_s, remaining)
            with self._stats_lock:
                self._retry_stats['retries_total'] += 1
                self._retry_stats['backoff_seconds_total'] += float(backoff_s)
            self._emit_progress({"phase": "retry_backoff", "attempt": attempt, "router": INFERENCE_OWNER})
            self._sleep_interruptible(backoff_s, deadline)

        with self._stats_lock:
            self._retry_stats['failures_total'] += 1
        if isinstance(last_error, ProviderRouteError):
            raise last_error
        raise Exception(f'llm_router_error: {str(last_error)}')

    def run_declared_purpose(self, context, purpose_id, inputs, **kwargs):
        """Dispatch a declared hook purpose without treating a fake transport as live Grok."""

        from mediator.hook_runtime import dispatch_declared_hook_purpose

        result = dispatch_declared_hook_purpose(context, purpose_id, inputs, **kwargs)
        identity = result.get("identity") if isinstance(result.get("identity"), dict) else {}
        requested = identity.get("requested") if isinstance(identity.get("requested"), dict) else {}
        selected = identity.get("selected") if isinstance(identity.get("selected"), dict) else {}
        observed = identity.get("observed") if isinstance(identity.get("observed"), dict) else {}
        receipt = self._receipt(
            status="configured" if not result.get("model_dispatched") else "unavailable",
            error_code="" if result.get("status") in {"available", "local_only"} else str(result.get("code") or ""),
            selected_provider=str(selected.get("provider") or ""),
            selected_model=str(selected.get("model") or ""),
            route_observation="not_dispatched" if not result.get("synthetic_transport_invoked") else "synthetic",
            provider_supported_identity=False,
            request_id="",
        )
        receipt["requested_provider"] = str(requested.get("provider") or receipt["requested_provider"])
        receipt["requested_model"] = str(requested.get("model") or receipt["requested_model"])
        receipt["observed_provider"] = str(observed.get("provider") or "")
        receipt["observed_model"] = str(observed.get("model") or "")
        receipt["observed_build"] = str(observed.get("build") or "")
        receipt["live_model_identity_verified"] = False
        receipt["live_build_identity_verified"] = False
        receipt["transport_kind"] = "synthetic" if result.get("synthetic_transport_invoked") or identity else receipt.get("transport_kind", "")
        if identity:
            receipt["live_model_identity_verified"] = bool(identity.get("live_model_identity_verified"))
            receipt["live_build_identity_verified"] = bool(identity.get("live_build_identity_verified"))
            receipt["transport_kind"] = str(identity.get("transport_kind") or "synthetic")
        self.task_receipts.append(receipt)
        self.task_receipts[:] = self.task_receipts[-32:]
        result["backend_receipt"] = {
            "requested_provider": receipt["requested_provider"],
            "requested_model": receipt["requested_model"],
            "selected_provider": receipt["selected_provider"],
            "selected_model": receipt["selected_model"],
            "observed_provider": receipt["observed_provider"],
            "observed_model": receipt["observed_model"],
            "observed_build": receipt["observed_build"],
            "live_model_identity_verified": receipt["live_model_identity_verified"],
            "live_build_identity_verified": receipt["live_build_identity_verified"],
            "provider_supported_identity": False,
            "transport_kind": receipt["transport_kind"],
        }
        return result

    def run_observed_hook_purpose(self, context, purpose_id, inputs, **kwargs):
        """Observed hook dispatch. Fallbacks and injected transports are not used.

        The qualified Native constructor and this backend's cancel event stay
        the resource owners. A failure receipt is recorded and returned so the
        caller can keep the pending case revision.
        """

        from mediator.hook_runtime import dispatch_observed_hook_purpose

        kwargs.pop("model_transport", None)
        kwargs.pop("allow_local_fallback", None)
        kwargs.pop("allow_cross_provider_fallback", None)
        kwargs.setdefault("cancel_event", self._cancel_event)
        if self.timeout_seconds is not None:
            kwargs.setdefault("timeout", min(float(self.timeout_seconds), 60.0))
        result = dispatch_observed_hook_purpose(context, purpose_id, inputs, **kwargs)
        receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
        safe = {key: receipt.get(key) for key in (
            "kind", "purpose_id", "status", "code", "request_id", "pending_revision",
            "pending_revision_recoverable", "case_revision_mutated", "accepted",
            "session_retained", "tools_allowed", "tools_invoked", "allow_local_fallback",
            "allow_cross_provider_fallback", "prompt_logged", "live_canary",
            "live_model_identity_verified", "live_build_identity_verified", "transport_kind",
            "observed_provider", "observed_model", "observed_build",
        )}
        safe["router"] = INFERENCE_OWNER
        safe["provider_supported_identity"] = False
        self.task_receipts.append(safe)
        self.task_receipts[:] = self.task_receipts[-32:]
        self.session_retained = True
        result["backend_receipt"] = dict(safe)
        return result

    def run_synthetic_live_canary(self, *, transport=None, confirm_live=False):
        """Use the existing bounded public-token API once; injected evidence is synthetic."""
        if type(confirm_live) is not bool:
            raise ValueError("confirm_live must be an explicit boolean")
        capability = {}
        requested = confirm_live is True or transport is not None
        if requested:
            options = {"include_canary": True}
            if transport is not None:
                options["canary_transport"] = transport
            try:
                capability = grok47_route_capability(**options)
            except Exception:
                capability = {}
        live = transport is None and capability.get("live_canary") is True
        provider = capability.get("selected_provider_name") if live else ""
        model = capability.get("provider_reported_model") if live else ""
        supported = live and provider == PINNED_GROK_PROVIDER and model in SUPPORTED_GROK_47_IDENTITIES
        receipt = self._receipt(
            status="available" if supported else "unavailable" if requested else "not_requested",
            error_code="" if supported or not requested else "route_unverified",
            selected_provider=provider if supported else "",
            selected_model=model if supported else "",
            route_observation="verified" if supported else "unverified" if requested else "not_dispatched",
            provider_supported_identity=supported,
            request_id=capability.get("request_id", ""),
            canary_identity=SYNTHETIC_LIVE_CANARY_IDENTITY,
            live_canary=supported,
        )
        receipt.update(canary_prompt_class="synthetic_public_token", complaint_data_included=False,
                       evidence_class="native_live_canary" if supported else "synthetic_canary" if requested else "absent")
        self.task_receipts.append(receipt)
        self._emit_progress({"phase": "synthetic_canary", "router": INFERENCE_OWNER,
                             "canary_identity": SYNTHETIC_LIVE_CANARY_IDENTITY})
        return receipt

    def _strict_route(self) -> bool:
        return (str(self.provider or "").lower().startswith("grok")
                or str(self.model or "").lower().startswith("grok")
                or self.forbid_model_substitution is True)

    def _generate(self, text, *, privacy_context, deadline):
        options = dict(self.config)
        if not self.pinned_grok47:
            if privacy_context is not None:
                options["complaint_privacy_context"] = privacy_context
            if self._call_intake_operation:
                options["intake_operation"] = self._call_intake_operation
                options["intake_source_text"] = self._intake_source_text
                options["request_id"] = self._request_id
                options["response_format"] = intake_request_response_format()
            return generate_text_with_metadata(prompt=text, provider=self.provider,
                                               model_name=self.model, **options)
        from integrations.ipfs_datasets.llm import _privacy_context_block_reason, _PRIVATE_GENERATION_OPTIONS

        # Consent admits a pinned generation, never arbitrary provider commands,
        # endpoints, output paths or callback overrides from configuration.
        if any(key not in _PRIVATE_GENERATION_OPTIONS for key in options):
            self._fail("unpinned_route", route_observation="refused")
        options.update(allow_local_fallback=False, allow_cross_provider_fallback=False)
        if self._call_intake_operation:
            return self._generate_intake(text, options, deadline, privacy_context)
        if _privacy_context_block_reason(privacy_context, provider=self.provider,
                                         model_name=self.model, options=options):
            self._fail("privacy_denied", route_observation="refused")
        self._raise_if_cancelled()
        generate, result_type, observation_type = load_observed_llm_symbols()
        if (not callable(generate) or not isinstance(result_type, type) or not isinstance(observation_type, type)
                or pinned_grok47_adapter_binding(generate) is None):
            self._fail("route_unverified", route_observation="unverified")
        request_id = self._request_id
        remaining = deadline - time.monotonic() if deadline is not None else 60.0
        if remaining <= 0:
            self._fail("timeout", route_observation="timeout")

        def progress(summary):
            # Native capture propagates BaseException through its finally block,
            # which terminates and reaps its own child before returning here.
            if self._cancel_event.is_set():
                raise _RouterCancelled()
            self._emit_progress({"phase": "provider_progress", "router": INFERENCE_OWNER})

        # Synchronous ownership is intentional: no abandoned daemon thread can
        # keep generating after the terminal reports cancellation or timeout.
        return self._dispatch_observed(
            text, options, deadline, request_id, generate, result_type, observation_type, progress,
        )

    def _generate_intake(self, text, options, deadline, privacy_context):
        remaining = deadline - time.monotonic() if deadline is not None else 60.0
        if remaining <= 0:
            self._fail("timeout", route_observation="timeout")
        return _generate_intake_with_metadata(text, provider=self.provider, model_name=self.model,
            request_id=self._request_id, operation=self._call_intake_operation,
            source_text=self._intake_source_text, allowed_target_refs=self._intake_target_refs,
            privacy_context=privacy_context, options={**options, "timeout": remaining},
            max_output_bytes=self.max_output_bytes, cancel_event=self._cancel_event,
            progress_callback=self._emit_progress)

    def _dispatch_observed(self, text, options, deadline, request_id, generate, result_type, observation_type, progress):
        try:
            sealed = intercept_final_provider_request({
                "schema": PROVIDER_EGRESS_SCHEMA,
                "provider": PINNED_GROK_PROVIDER,
                "model": PINNED_GROK_MODEL,
                "prompt": text,
                "timeout_seconds": max(0.01, deadline - time.monotonic()) if deadline is not None else 60.0,
                "allow_local_fallback": False,
                "allow_cross_provider_fallback": False,
                "request_id": request_id,
                **provider_egress_options(options),
            })
        except RuntimeError:
            self._fail("privacy_denied", route_observation="refused")
        text = sealed["prompt"]
        result = generate(prompt=text, provider=PINNED_GROK_PROVIDER,
                          model_name=PINNED_GROK_MODEL, observation_request_id=request_id,
                          **{**provider_egress_options(sealed), "timeout": sealed["timeout_seconds"],
                             "allow_local_fallback": False, "allow_cross_provider_fallback": False,
                             "grok_stream_progress": True,
                             "grok_progress_callback": progress, "usage_cancel_event": self._cancel_event,
                             "grok_cli_cmd": ["grok"], "grok_tools": "read_file",
                             "grok_disallowed_tools": "read_file,search_tool,use_tool",
                             "grok_max_turns": 1, "grok_permission_mode": "dontAsk"})
        self._raise_if_cancelled()
        if deadline is not None and time.monotonic() >= deadline:
            self._fail("timeout", route_observation="timeout")
        if type(result) is not result_type or type(result.observation) is not observation_type:
            self._fail("route_unverified", route_observation="unverified")
        observation = result.observation
        if (observation.request_id != request_id
                or not isinstance(observation.invocation_id, str)
                or not re.fullmatch(r"[0-9a-f]{32}", observation.invocation_id)
                or type(observation.native_dispatch_count) is not int or observation.native_dispatch_count != 1
                or observation.invocation_scope != "current_call"
                or observation.schema != "native-grok-invocation-observation@1"
                or observation.observation_only is not True or observation.raw_provider_data_exported is not False
                or type(observation.process_returncode) is not int or observation.process_returncode != 0
                or observation.stream_complete is not True
                or observation.wire_model_observed is not True
                or observation.evidence_class != "native_final_end_model_usage"):
            self._fail("route_unverified", route_observation="unverified")
        if (observation.selected_provider_name != PINNED_GROK_PROVIDER
                or observation.selected_model_name != PINNED_GROK_MODEL
                or observation.provider_reported_model not in SUPPORTED_GROK_47_IDENTITIES):
            self._fail("substitution_refused", route_observation="mismatched")
        if not isinstance(result.text, str):
            self._fail("malformed_output", route_observation="malformed")
        return {"status": "available", "text": result.text, "request_id": request_id,
                "native_invocation_id": observation.invocation_id,
                "observed_provider_name": observation.selected_provider_name,
                "observed_model_name": observation.provider_reported_model,
                "route_observation": "verified", "invocation_bound": True}

    def _reject_substitution(self, metadata):
        if not self._strict_route():
            return
        observed_provider = str(metadata.get("observed_provider_name") or metadata.get("effective_provider_name") or "")
        observed_model = str(metadata.get("observed_model_name") or metadata.get("effective_model_name") or "")
        provider_ok = observed_provider in {"", PINNED_GROK_PROVIDER}
        model_ok = observed_model in {"", *SUPPORTED_GROK_47_IDENTITIES}
        if observed_provider and not provider_ok:
            self._fail(
                "substitution_refused",
                metadata=metadata,
                selected_provider=observed_provider,
                selected_model=observed_model,
                route_observation="mismatched",
            )
        if observed_model and not model_ok:
            self._fail(
                "substitution_refused",
                metadata=metadata,
                selected_provider=observed_provider,
                selected_model=observed_model,
                route_observation="mismatched",
            )
        if self.pinned_grok47 and (not observed_provider or not observed_model or not self._identity_supported(metadata)):
            self._fail(
                "route_unverified",
                metadata=metadata,
                selected_provider=observed_provider,
                selected_model=observed_model,
                route_observation="unverified",
            )

    def _identity_supported(self, metadata) -> bool:
        observed_provider = str(metadata.get("observed_provider_name") or "")
        observed_model = str(metadata.get("observed_model_name") or "")
        if metadata.get("invocation_bound") is True and observed_provider == PINNED_GROK_PROVIDER and observed_model in SUPPORTED_GROK_47_IDENTITIES:
            return True
        if not self.pinned_grok47:
            return bool(observed_provider and observed_model)
        return False

    def _observation(self, metadata) -> str:
        if self._identity_supported(metadata) and self.pinned_grok47:
            return "verified"
        return str(metadata.get("route_observation") or "unverified")

    def _validate_structured(self, text: str) -> str:
        if not self.structured_output:
            return text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            self._fail("malformed_output", route_observation="malformed")
        if not isinstance(payload, dict):
            self._fail("malformed_output", route_observation="malformed")
        missing = [key for key in self.response_schema_required if key not in payload]
        if missing:
            self._fail("malformed_output", route_observation="malformed")
        return text

    def _fail(self, error_code, *, metadata=None, selected_provider="", selected_model="", route_observation="unavailable"):
        if metadata is not None:
            selected_provider = selected_provider or str(metadata.get("observed_provider_name") or metadata.get("effective_provider_name") or "")
            selected_model = selected_model or str(metadata.get("observed_model_name") or metadata.get("effective_model_name") or "")
        status = {
            "cancelled": "cancelled",
            "timeout": "timeout",
            "quota": "quota",
            "malformed_output": "malformed",
            "provider_unavailable": "unavailable",
        }.get(error_code, "error")
        payload = self._record(
            status=status,
            error_code=error_code,
            metadata=metadata,
            selected_provider=selected_provider,
            selected_model=selected_model,
            route_observation=route_observation,
            provider_supported_identity=False,
        )
        raise ProviderRouteError(payload)

    def _record(self, *, status, error_code, metadata=None, selected_provider="", selected_model="", route_observation="", provider_supported_identity=False, request_id=""):
        request_id = request_id or getattr(self, "_request_id", "")
        if metadata is not None:
            request_id = request_id or str(metadata.get("request_id") or "")
            if not selected_provider:
                selected_provider = str(metadata.get("observed_provider_name") or "")
            if not selected_model:
                selected_model = str(metadata.get("observed_model_name") or "")
        receipt = self._receipt(
            status=status,
            error_code=error_code,
            selected_provider=selected_provider,
            selected_model=selected_model,
            route_observation=route_observation,
            provider_supported_identity=provider_supported_identity,
            request_id=request_id,
        )
        if metadata and metadata.get("invocation_bound") is True:
            invocation = metadata.get("native_invocation_id")
            if isinstance(invocation, str) and re.fullmatch(r"[0-9a-f]{32}", invocation):
                receipt["native_invocation_id"] = invocation
        self.task_receipts.append(receipt)
        self.task_receipts[:] = self.task_receipts[-32:]
        self.session_retained = True
        return receipt

    def _receipt(self, *, status, error_code, selected_provider, selected_model, route_observation, provider_supported_identity, request_id, canary_identity="", live_canary=False):
        selected_provider = selected_provider if selected_provider == PINNED_GROK_PROVIDER else ""
        selected_model = selected_model if selected_model in SUPPORTED_GROK_47_IDENTITIES else ""
        request_id = request_id if isinstance(request_id, str) and re.fullmatch(r"[0-9a-f]{32}", request_id) else ""
        selected_router = INFERENCE_OWNER if selected_provider and selected_model else ""
        if status == "configured":
            selected_router = ""
        return {
            "kind": "task_receipt",
            "request_id": request_id,
            "session_id": self.session_id,
            "session_retained": True,
            "router": INFERENCE_OWNER,
            "requested_router": INFERENCE_OWNER,
            "selected_router": selected_router,
            "requested_provider": self.provider if self.provider in REMOTE_PROVIDERS else "unverified",
            "selected_provider": selected_provider,
            "requested_model": self.model if self.model in SUPPORTED_GROK_47_IDENTITIES else "unverified",
            "selected_model": selected_model,
            "route_observation": route_observation,
            "provider_supported_identity": bool(provider_supported_identity),
            "status": status,
            "error_code": error_code,
            "error": _ERROR_TEXT.get(error_code, ""),
            "prompt_logged": False,
            "intake_complete": False,
            "live_canary": bool(live_canary),
            "canary_identity": canary_identity,
            "remote_inference": self.remote_inference_disclosure(),
        }

    def _emit_progress(self, event: dict) -> None:
        safe = {key: value for key, value in event.items() if key in {"phase", "attempt", "max_attempts", "router", "status", "canary_identity"}}
        self.progress_events.append(safe)
        self.progress_events[:] = self.progress_events[-32:]
        callback = self.progress_callback
        if callable(callback):
            try:
                callback(dict(safe))
            except Exception:
                # A display callback cannot cause a second provider dispatch.
                pass
        if os.getenv("COMPLAINT_GENERATOR_ROUTER_PROGRESS", "").strip() in {"1", "true", "yes"}:
            print("router_progress " + json.dumps(safe, sort_keys=True), flush=True)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            self._fail("cancelled", route_observation="cancelled")

    def _sleep_interruptible(self, seconds: float, deadline) -> None:
        end = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < end:
            self._raise_if_cancelled()
            if deadline is not None and time.monotonic() >= deadline:
                self._fail("timeout", route_observation="timeout")
            time.sleep(min(0.05, end - time.monotonic()))

    def _compute_backoff_seconds(self, attempt: int) -> float:
        exp = max(0, attempt - 1)
        base = self.retry_backoff_base_s * (2 ** exp)
        base = min(base, self.retry_backoff_max_s)
        jitter = random.uniform(0.0, max(0.0, self.retry_jitter_s))
        return float(base + jitter)

    def _is_retryable_error(self, error: Exception) -> bool:
        if isinstance(error, ProviderRouteError):
            return error.payload.get("error_code") in {"provider_unavailable", "timeout"}
        message = str(error or '').lower()
        if message.startswith('llm_router_error:'):
            message = message.split(':', 1)[-1].strip()
        return any(s.lower() in message for s in self.retryable_error_substrings)

    def get_retry_stats(self):
        with self._stats_lock:
            return dict(self._retry_stats)


LLMRouter = LLMRouterBackend

TERMINAL_GROK_BACKEND_ID = "llm-router-grok-4.7"


def load_terminal_router_backend(config_path: str = "config.llm_router.json", backend_id: str = TERMINAL_GROK_BACKEND_ID):
    """Build the terminal Grok 4.7 backend from config without sending a prompt."""

    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    match = next((item for item in config.get("BACKENDS") or [] if item.get("id") == backend_id), None)
    if not isinstance(match, dict):
        raise KeyError(f"router backend {backend_id} is not configured")
    if match.get("type") != "llm_router":
        raise ValueError("terminal router backend must use llm_router")
    kwargs = dict(match)
    kwargs.pop("type", None)
    resolved_id = str(kwargs.pop("id"))
    provider = kwargs.pop("provider", None)
    model = kwargs.pop("model", None)
    return LLMRouterBackend(resolved_id, provider=provider, model=model, **kwargs)


def router_session_diagnostics_payload(config_path: str = "config.llm_router.json", backend_id: str = TERMINAL_GROK_BACKEND_ID):
    backend = load_terminal_router_backend(config_path, backend_id)
    return backend.sanitized_session_diagnostics()


def router_task_receipt_payload(config_path: str = "config.llm_router.json", backend_id: str = TERMINAL_GROK_BACKEND_ID):
    backend = load_terminal_router_backend(config_path, backend_id)
    return {"session_id": backend.session_id, "session_retained": True, "receipts": backend.task_receipt_snapshot()}
