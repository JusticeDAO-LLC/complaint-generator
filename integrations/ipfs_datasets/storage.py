from __future__ import annotations

import os
import shutil
from pathlib import Path
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


def _repo_local_ipfs_kit_root() -> Path:
    return Path(__file__).resolve().parents[2] / "ipfs_datasets_py" / "ipfs_kit_py"


def _discover_repo_local_kubo_cmd() -> str:
    configured = os.environ.get("IPFS_DATASETS_PY_KUBO_CMD", "").strip()
    if configured:
        return configured

    env_cmd = os.environ.get("KUBO_CMD", "").strip()
    if env_cmd:
        return env_cmd

    resolved_path = shutil.which("ipfs")
    if resolved_path:
        return resolved_path

    candidate = _repo_local_ipfs_kit_root() / "bin" / "ipfs"
    if candidate.exists():
        return str(candidate)

    return ""


def _discover_repo_local_ipfs_path() -> str:
    configured = os.environ.get("IPFS_PATH", "").strip()
    if configured:
        return configured

    candidate = _repo_local_ipfs_kit_root() / ".ipfs"
    config_path = candidate / "config"
    if config_path.exists():
        return str(candidate)

    return ""


def _ensure_local_kubo_environment() -> str:
    discovered_cmd = _discover_repo_local_kubo_cmd()
    if discovered_cmd:
        os.environ.setdefault("IPFS_DATASETS_PY_KUBO_CMD", discovered_cmd)

    discovered_ipfs_path = _discover_repo_local_ipfs_path()
    if discovered_ipfs_path:
        os.environ.setdefault("IPFS_PATH", discovered_ipfs_path)

    return discovered_cmd


def _runtime_backend_probe() -> dict[str, Any]:
    discovered_cmd = _ensure_local_kubo_environment()
    if not IPFS_AVAILABLE:
        return {
            "backend": None,
            "backend_name": "",
            "status": "unavailable",
            "reason": IPFS_ERROR or "ipfs router unavailable",
        }

    try:
        backend = get_ipfs_backend()
    except Exception as exc:
        return {
            "backend": None,
            "backend_name": "",
            "status": "unavailable",
            "reason": str(exc),
        }

    backend_name = type(backend).__name__ if backend is not None else ""
    if backend is None:
        return {
            "backend": None,
            "backend_name": backend_name,
            "status": "unavailable",
            "reason": "no backend instance resolved",
        }

    cmd = getattr(backend, "_cmd", None)
    if backend_name == "KuboCLIBackend":
        resolved = shutil.which(str(cmd or "ipfs"))
        if not resolved and discovered_cmd:
            resolved = discovered_cmd
            try:
                setattr(backend, "_cmd", discovered_cmd)
            except Exception:
                pass
        if not resolved:
            return {
                "backend": backend,
                "backend_name": backend_name,
                "status": "unavailable",
                "reason": f"missing ipfs CLI binary: {cmd or 'ipfs'}",
            }

    return {
        "backend": backend,
        "backend_name": backend_name,
        "status": "available",
        "reason": "",
    }


def store_bytes(data: bytes, *, pin_content: bool = True) -> dict[str, Any]:
    probe = _runtime_backend_probe()
    if add_bytes is None or probe["status"] != "available":
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": "",
                "size": len(data),
                "pinned": bool(pin_content),
                "error": probe["reason"] if probe["status"] != "available" else "",
            },
            operation="store_bytes",
            backend_available=False,
            degraded_reason=probe["reason"] or IPFS_ERROR,
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
    probe = _runtime_backend_probe()
    if cat is None or probe["status"] != "available":
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": cid,
                "data": b"",
                "size": 0,
                "error": probe["reason"] if probe["status"] != "available" else "",
            },
            operation="retrieve_bytes",
            backend_available=False,
            degraded_reason=probe["reason"] or IPFS_ERROR,
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
    probe = _runtime_backend_probe()
    if pin is None or probe["status"] != "available":
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": cid,
                "pinned": False,
                "result": None,
                "error": probe["reason"] if probe["status"] != "available" else "",
            },
            operation="pin_cid",
            backend_available=False,
            degraded_reason=probe["reason"] or IPFS_ERROR,
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
    probe = _runtime_backend_probe()
    backend = probe["backend"]
    backend_name = str(probe["backend_name"] or "")
    return with_adapter_metadata(
        {
            "status": probe["status"],
            "backend_name": backend_name,
            "backend_present": backend is not None,
            "error": probe["reason"] or "",
        },
        operation="storage_backend_status",
        backend_available=probe["status"] == "available",
        degraded_reason=probe["reason"] or (IPFS_ERROR if not IPFS_AVAILABLE else None),
        implementation_status="available" if probe["status"] == "available" else "unavailable",
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
