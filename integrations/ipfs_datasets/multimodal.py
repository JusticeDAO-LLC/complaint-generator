from __future__ import annotations

from typing import Any

from .loader import import_attr_optional


generate_multimodal_text, _generate_error = import_attr_optional(
    "ipfs_datasets_py.multimodal_router",
    "generate_multimodal_text",
)
build_multimodal_messages, _messages_error = import_attr_optional(
    "ipfs_datasets_py.multimodal_router",
    "build_multimodal_messages",
)
encode_image_as_data_url, _encode_error = import_attr_optional(
    "ipfs_datasets_py.multimodal_router",
    "encode_image_as_data_url",
)

MULTIMODAL_ROUTER_AVAILABLE = generate_multimodal_text is not None
MULTIMODAL_ROUTER_ERROR = _generate_error or _messages_error or _encode_error


__all__ = [
    "MULTIMODAL_ROUTER_AVAILABLE",
    "MULTIMODAL_ROUTER_ERROR",
    "build_multimodal_messages",
    "encode_image_as_data_url",
    "generate_multimodal_text",
]
