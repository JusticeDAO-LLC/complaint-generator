"""LLM Router Backend."""

import logging
import os
import random
import time
import threading

from integrations.ipfs_datasets.llm import LLM_ROUTER_AVAILABLE, generate_text_via_router as generate_text

logger = logging.getLogger(__name__)

_PROVIDER_ALIASES = {
    'local': 'hf',
    'local_hf': 'hf',
    'huggingface': 'hf',
    'hf': 'hf',
}

_PROVIDER_ENV_KEYS = (
    'IPFS_DATASETS_PY_LLM_PROVIDER',
    'COMPLAINT_GENERATOR_LLM_PROVIDER',
    'LLM_ROUTER_PROVIDER',
)

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
                self.model = 'gpt-5-mini'
            else:
                self.model = None
        else:
            self.model = model

        # Retry/backoff tuning. Defaults to no retries for backward compatibility.
        self.retry_max_attempts = int(config.pop('retry_max_attempts', 1) or 1)
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

        self.config = config

        self._stats_lock = threading.Lock()
        self._retry_stats = {
            'calls_total': 0,
            'attempts_total': 0,
            'retries_total': 0,
            'backoff_seconds_total': 0.0,
            'failures_total': 0,
        }
        
        # Check if llm_router is available
        if not LLM_ROUTER_AVAILABLE:
            raise ImportError(
                "llm_router not available. Please ensure ipfs_datasets_py submodule "
                "is initialized with: git submodule update --init --recursive"
            )

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
    
    def __call__(self, text):
        """
        Generate text using the llm_router.
        
        Args:
            text: The prompt text
            
        Returns:
            Generated text response
        """
        with self._stats_lock:
            self._retry_stats['calls_total'] += 1

        last_error = None
        max_attempts = max(1, self.retry_max_attempts)
        for attempt in range(1, max_attempts + 1):
            with self._stats_lock:
                self._retry_stats['attempts_total'] += 1
            try:
                response = generate_text(
                    prompt=text,
                    provider=self.provider,
                    model_name=self.model,
                    **self.config
                )
                return response
            except Exception as e:
                last_error = e
                retryable = self._is_retryable_error(e)
                if attempt >= max_attempts or not retryable:
                    with self._stats_lock:
                        self._retry_stats['failures_total'] += 1
                    raise Exception(f'llm_router_error: {str(e)}')

                backoff_s = self._compute_backoff_seconds(attempt)
                with self._stats_lock:
                    self._retry_stats['retries_total'] += 1
                    self._retry_stats['backoff_seconds_total'] += float(backoff_s)
                time.sleep(backoff_s)

        # Should be unreachable, but keep a safe fallback.
        with self._stats_lock:
            self._retry_stats['failures_total'] += 1
        raise Exception(f'llm_router_error: {str(last_error)}')

    def _compute_backoff_seconds(self, attempt: int) -> float:
        # attempt is 1-based; backoff applies between attempt and attempt+1.
        exp = max(0, attempt - 1)
        base = self.retry_backoff_base_s * (2 ** exp)
        base = min(base, self.retry_backoff_max_s)
        jitter = random.uniform(0.0, max(0.0, self.retry_jitter_s))
        return float(base + jitter)

    def _is_retryable_error(self, error: Exception) -> bool:
        message = str(error or '').lower()
        # unwrap our own wrapper if present
        if message.startswith('llm_router_error:'):
            message = message.split(':', 1)[-1].strip()
        return any(s.lower() in message for s in self.retryable_error_substrings)

    def get_retry_stats(self):
        with self._stats_lock:
            return dict(self._retry_stats)


# For backward compatibility, create an alias
LLMRouter = LLMRouterBackend
