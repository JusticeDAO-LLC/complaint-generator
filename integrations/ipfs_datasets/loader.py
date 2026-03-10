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


def import_module_optional(module_name: str) -> tuple[Any | None, str | None]:
    ensure_import_paths()
    try:
        return importlib.import_module(module_name), None
    except Exception as exc:
        return None, str(exc)


def import_attr_optional(module_name: str, attr_name: str) -> tuple[Any | None, str | None]:
    module, error = import_module_optional(module_name)
    if module is None:
        return None, error
    try:
        return getattr(module, attr_name), None
    except Exception as exc:
        return None, str(exc)


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