from __future__ import annotations

from typing import Any

from integrations.ipfs_accelerate.routers import load_multimodal_symbols


generate_multimodal_text, build_multimodal_messages, encode_image_as_data_url, _router_error = load_multimodal_symbols()

MULTIMODAL_ROUTER_AVAILABLE = generate_multimodal_text is not None
MULTIMODAL_ROUTER_ERROR = _router_error


__all__ = [
    "MULTIMODAL_ROUTER_AVAILABLE",
    "MULTIMODAL_ROUTER_ERROR",
    "build_multimodal_messages",
    "encode_image_as_data_url",
    "generate_multimodal_text",
]
