from __future__ import annotations

from .loader import import_attr_optional


generate_text, _error = import_attr_optional("ipfs_datasets_py.llm_router", "generate_text")
LLM_ROUTER_AVAILABLE = generate_text is not None
LLM_ROUTER_ERROR = _error

__all__ = ["generate_text", "LLM_ROUTER_AVAILABLE", "LLM_ROUTER_ERROR"]