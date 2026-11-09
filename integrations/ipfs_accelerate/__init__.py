"""Complaint-generator facade for ipfs_accelerate_py inference and supervision."""

from .routers import (
    COMPLAINT_PROVIDER_ALIASES,
    accelerate_provider_name,
    load_embedding_symbols,
    load_llm_symbols,
    load_multimodal_symbols,
    normalize_accelerate_provider,
)

__all__ = [
    "COMPLAINT_PROVIDER_ALIASES",
    "accelerate_provider_name",
    "load_embedding_symbols",
    "load_llm_symbols",
    "load_multimodal_symbols",
    "normalize_accelerate_provider",
]
