from __future__ import annotations

from typing import Any

from .loader import import_attr_optional


add_bytes, _add_error = import_attr_optional("ipfs_datasets_py.ipfs_backend_router", "add_bytes")
cat, _cat_error = import_attr_optional("ipfs_datasets_py.ipfs_backend_router", "cat")
pin, _pin_error = import_attr_optional("ipfs_datasets_py.ipfs_backend_router", "pin")
get_ipfs_backend, _backend_error = import_attr_optional(
    "ipfs_datasets_py.ipfs_backend_router",
    "get_ipfs_backend",
)

IPFS_AVAILABLE = all(value is not None for value in (add_bytes, cat, pin))
IPFS_ERROR = _add_error or _cat_error or _pin_error or _backend_error

if get_ipfs_backend is None:
    def get_ipfs_backend() -> Any:
        return None


__all__ = [
    "add_bytes",
    "cat",
    "pin",
    "get_ipfs_backend",
    "IPFS_AVAILABLE",
    "IPFS_ERROR",
]