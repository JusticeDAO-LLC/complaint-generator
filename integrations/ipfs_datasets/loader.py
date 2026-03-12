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


def _matches_package_root(module_name: str, package_root: str) -> bool:
    return module_name == package_root or module_name.startswith(f"{package_root}.")


def ensure_import_paths(module_name: str = "", missing_module_name: str = "") -> RepoPaths:
    paths = get_repo_paths()
    candidate_paths: list[Path] = []

    if _matches_package_root(module_name, "ipfs_datasets_py") or _matches_package_root(
        missing_module_name, "ipfs_datasets_py"
    ):
        candidate_paths.append(paths.ipfs_datasets_repo)

    if _matches_package_root(module_name, "ipfs_accelerate_py") or _matches_package_root(
        missing_module_name, "ipfs_accelerate_py"
    ):
        candidate_paths.append(paths.ipfs_accelerate_repo)

    for path in candidate_paths:
        if path.exists():
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
    return paths


def _should_retry_with_repo_paths(module_name: str, error: ModuleNotFoundError) -> bool:
    missing_module_name = str(getattr(error, "name", "") or "")
    return any(
        _matches_package_root(value, package_root)
        for package_root in ("ipfs_datasets_py", "ipfs_accelerate_py")
        for value in (module_name, missing_module_name)
        if value
    )


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
    try:
        return importlib.import_module(module_name), None
    except ModuleNotFoundError as exc:
        if _should_retry_with_repo_paths(module_name, exc):
            ensure_import_paths(module_name=module_name, missing_module_name=str(getattr(exc, "name", "") or ""))
            try:
                return importlib.import_module(module_name), None
            except Exception as retry_exc:
                return None, _build_import_failure(retry_exc, module_name=module_name)
        return None, _build_import_failure(exc, module_name=module_name)
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