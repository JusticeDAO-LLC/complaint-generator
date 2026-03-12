from __future__ import annotations

import asyncio
import importlib
import sys
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RepoPaths:
    repo_root: Path
    ipfs_datasets_repo: Path
    ipfs_accelerate_repo: Path


@dataclass(frozen=True)
class ImportFailure:
    module_name: str
    error_type: str
    message: str
    attr_name: str = ""

    def __str__(self) -> str:
        return self.message


@lru_cache(maxsize=1)
def get_repo_paths() -> RepoPaths:
    repo_root = Path(__file__).resolve().parents[2]
    ipfs_datasets_repo = repo_root / "ipfs_datasets_py"
    ipfs_accelerate_repo = ipfs_datasets_repo / "ipfs_accelerate_py"
    return RepoPaths(
        repo_root=repo_root,
        ipfs_datasets_repo=ipfs_datasets_repo,
        ipfs_accelerate_repo=ipfs_accelerate_repo,
    )


def ensure_import_paths() -> RepoPaths:
    paths = get_repo_paths()
    for path in (paths.ipfs_datasets_repo, paths.ipfs_accelerate_repo):
        if path.exists():
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
    return paths


def _build_import_failure(exc: BaseException, *, module_name: str, attr_name: str = "") -> ImportFailure:
    return ImportFailure(
        module_name=module_name,
        attr_name=attr_name,
        error_type=type(exc).__name__,
        message=str(exc),
    )


def import_failure_message(error: Any) -> str | None:
    if error is None:
        return None
    if isinstance(error, ImportFailure):
        return error.message
    message = str(error).strip()
    return message or None


def import_failure_type(error: Any) -> str:
    if isinstance(error, ImportFailure):
        return error.error_type
    if error is None:
        return ""
    return type(error).__name__


def import_module_optional(module_name: str) -> tuple[Any | None, ImportFailure | None]:
    ensure_import_paths()
    try:
        return importlib.import_module(module_name), None
    except Exception as exc:
        return None, _build_import_failure(exc, module_name=module_name)


def import_attr_optional(module_name: str, attr_name: str) -> tuple[Any | None, ImportFailure | None]:
    module, error = import_module_optional(module_name)
    if module is None:
        return None, error
    try:
        return getattr(module, attr_name), None
    except Exception as exc:
        return None, _build_import_failure(exc, module_name=module_name, attr_name=attr_name)


def run_async_compat(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:
            error["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in error:
        raise error["error"]
    return result.get("value")