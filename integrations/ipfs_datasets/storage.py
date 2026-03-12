from __future__ import annotations

from typing import Any

from .loader import import_attr_optional
from .types import with_adapter_metadata


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


def store_bytes(data: bytes, *, pin_content: bool = True) -> dict[str, Any]:
    if add_bytes is None:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": "",
                "size": len(data),
                "pinned": bool(pin_content),
            },
            operation="store_bytes",
            backend_available=False,
            degraded_reason=IPFS_ERROR,
            implementation_status="unavailable",
        )

    try:
        cid = add_bytes(data, pin=pin_content)
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "cid": "",
                "size": len(data),
                "pinned": bool(pin_content),
                "error": str(exc),
            },
            operation="store_bytes",
            backend_available=True,
            implementation_status="available",
        )

    return with_adapter_metadata(
        {
            "status": "available",
            "cid": cid,
            "size": len(data),
            "pinned": bool(pin_content),
        },
        operation="store_bytes",
        backend_available=True,
        implementation_status="available",
    )


def retrieve_bytes(cid: str) -> dict[str, Any]:
    if cat is None:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": cid,
                "data": b"",
                "size": 0,
            },
            operation="retrieve_bytes",
            backend_available=False,
            degraded_reason=IPFS_ERROR,
            implementation_status="unavailable",
        )

    try:
        data = cat(cid)
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "cid": cid,
                "data": b"",
                "size": 0,
                "error": str(exc),
            },
            operation="retrieve_bytes",
            backend_available=True,
            implementation_status="available",
        )

    payload = data if isinstance(data, (bytes, bytearray)) else bytes(str(data), "utf-8")
    return with_adapter_metadata(
        {
            "status": "available",
            "cid": cid,
            "data": bytes(payload),
            "size": len(payload),
        },
        operation="retrieve_bytes",
        backend_available=True,
        implementation_status="available",
    )


def pin_cid(cid: str) -> dict[str, Any]:
    if pin is None:
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": cid,
                "pinned": False,
                "result": None,
            },
            operation="pin_cid",
            backend_available=False,
            degraded_reason=IPFS_ERROR,
            implementation_status="unavailable",
        )

    try:
        result = pin(cid)
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "cid": cid,
                "pinned": False,
                "result": None,
                "error": str(exc),
            },
            operation="pin_cid",
            backend_available=True,
            implementation_status="available",
        )

    return with_adapter_metadata(
        {
            "status": "available",
            "cid": cid,
            "pinned": True,
            "result": result,
        },
        operation="pin_cid",
        backend_available=True,
        implementation_status="available",
    )


def storage_backend_status() -> dict[str, Any]:
    backend = None
    if IPFS_AVAILABLE:
        try:
            backend = get_ipfs_backend()
        except Exception:
            backend = None

    backend_name = type(backend).__name__ if backend is not None else ""
    return with_adapter_metadata(
        {
            "status": "available" if IPFS_AVAILABLE else "unavailable",
            "backend_name": backend_name,
            "backend_present": backend is not None,
        },
        operation="storage_backend_status",
        backend_available=IPFS_AVAILABLE,
        degraded_reason=IPFS_ERROR if not IPFS_AVAILABLE else None,
        implementation_status="available" if IPFS_AVAILABLE else "unavailable",
    )


__all__ = [
    "add_bytes",
    "cat",
    "pin",
    "get_ipfs_backend",
    "store_bytes",
    "retrieve_bytes",
    "pin_cid",
    "storage_backend_status",
    "IPFS_AVAILABLE",
    "IPFS_ERROR",
]