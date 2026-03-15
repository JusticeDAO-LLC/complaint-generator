from __future__ import annotations

import os
import hashlib
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
set_default_ipfs_backend, _set_default_error = import_attr_optional(
    "ipfs_datasets_py.ipfs_backend_router",
    "set_default_ipfs_backend",
)
clear_ipfs_backend_router_caches, _clear_cache_error = import_attr_optional(
    "ipfs_datasets_py.ipfs_backend_router",
    "clear_ipfs_backend_router_caches",
)

IPFS_AVAILABLE = all(value is not None for value in (add_bytes, cat, pin))
IPFS_ERROR = _add_error or _cat_error or _pin_error or _backend_error or _set_default_error or _clear_cache_error

if get_ipfs_backend is None:
    def get_ipfs_backend() -> Any:
        return None

if set_default_ipfs_backend is None:
    def set_default_ipfs_backend(_backend: Any) -> None:
        return None

if clear_ipfs_backend_router_caches is None:
    def clear_ipfs_backend_router_caches() -> None:
        return None


class LocalCacheIPFSBackend:
    """Content-addressed local fallback for environments without a working IPFS daemon."""

    def __init__(self, cache_dir: str | None = None) -> None:
        root = cache_dir or os.environ.get("COMPLAINT_GENERATOR_IPFS_CACHE_DIR", "").strip()
        self.cache_dir = Path(root or (Path.home() / ".cache" / "complaint-generator" / "ipfs_fallback"))
        self.blobs_dir = self.cache_dir / "blobs"
        self.pins_dir = self.cache_dir / "pins"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        self.pins_dir.mkdir(parents=True, exist_ok=True)

    def _blob_path(self, cid: str) -> Path:
        return self.blobs_dir / cid

    def _pin_path(self, cid: str) -> Path:
        return self.pins_dir / cid

    def _cid_for_bytes(self, data: bytes) -> str:
        return f"bafy{hashlib.sha256(data).hexdigest()[:55]}"

    def add_bytes(self, data: bytes, *, pin: bool = True) -> str:
        cid = self._cid_for_bytes(data)
        self._blob_path(cid).write_bytes(data)
        if pin:
            self.pin(cid)
        return cid

    def cat(self, cid: str) -> bytes:
        return self._blob_path(cid).read_bytes()

    def pin(self, cid: str) -> None:
        if not self._blob_path(cid).exists():
            raise FileNotFoundError(f"unknown cid: {cid}")
        self._pin_path(cid).write_text("", encoding="utf-8")

    def unpin(self, cid: str) -> None:
        self._pin_path(cid).unlink(missing_ok=True)

    def block_put(self, data: bytes, *, codec: str = "raw") -> str:
        _ = codec
        return self.add_bytes(data, pin=False)

    def block_get(self, cid: str) -> bytes:
        return self.cat(cid)

    def add_path(self, path: str, *, recursive: bool = True, pin: bool = True, chunker: str | None = None) -> str:
        _ = recursive, chunker
        return self.add_bytes(Path(path).read_bytes(), pin=pin)

    def get_to_path(self, cid: str, *, output_path: str) -> None:
        Path(output_path).write_bytes(self.cat(cid))

    def ls(self, cid: str) -> list[str]:
        _ = cid
        return []

    def dag_export(self, cid: str) -> bytes:
        return self.cat(cid)


def ensure_ipfs_backend(*, prefer_local_fallback: bool = False, cache_dir: str | None = None) -> Any:
    if not IPFS_AVAILABLE:
        return None

    try:
        backend = get_ipfs_backend()
    except Exception:
        backend = None

    backend_name = type(backend).__name__ if backend is not None else ""
    if prefer_local_fallback and (
        backend is None
        or (
            backend_name == "KuboCLIBackend"
            and not shutil.which(str(getattr(backend, "_cmd", None) or "ipfs"))
        )
    ):
        fallback_backend = LocalCacheIPFSBackend(cache_dir=cache_dir)
        set_default_ipfs_backend(fallback_backend)
        clear_ipfs_backend_router_caches()
        return fallback_backend

    return backend


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
    if os.environ.get("COMPLAINT_GENERATOR_ENABLE_LOCAL_IPFS_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}:
        ensure_ipfs_backend(prefer_local_fallback=True)
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
    "set_default_ipfs_backend",
    "clear_ipfs_backend_router_caches",
    "LocalCacheIPFSBackend",
    "ensure_ipfs_backend",
    "store_bytes",
    "retrieve_bytes",
    "pin_cid",
    "storage_backend_status",
    "IPFS_AVAILABLE",
    "IPFS_ERROR",
]
