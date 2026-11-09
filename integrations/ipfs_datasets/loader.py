from __future__ import annotations

import asyncio
import importlib
import importlib.util
import re
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
    ipfs_kit_repo: Path | None = None
    mike_repo: Path | None = None


def _first_present(candidates: tuple[Path, ...]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


@dataclass(frozen=True)
class ImportFailure:
    module_name: str
    error_type: str
    message: str
    attr_name: str = ""
    missing_module_name: str = ""

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, str]:
        """Return the stable diagnostic shape used by adapter status payloads."""

        return {
            "module_name": self.module_name,
            "attr_name": self.attr_name,
            "error_type": self.error_type,
            "message": self.message,
            "missing_module_name": self.missing_module_name,
        }


@lru_cache(maxsize=1)
def get_repo_paths() -> RepoPaths:
    repo_root = Path(__file__).resolve().parents[2]
    external = repo_root / "external"
    ipfs_datasets_repo = _first_present(
        (
            external / "ipfs_datasets_py",
            repo_root / "ipfs_datasets_py",
        )
    )
    ipfs_accelerate_repo = _first_present(
        (
            external / "ipfs_accelerate_py",
            ipfs_datasets_repo / "ipfs_accelerate_py",
        )
    )
    ipfs_kit_repo = _first_present(
        (
            external / "ipfs_kit_py",
            ipfs_datasets_repo / "ipfs_kit_py",
        )
    )
    mike_repo = _first_present(
        (
            external / "mike",
            repo_root / "mike",
        )
    )
    return RepoPaths(
        repo_root=repo_root,
        ipfs_datasets_repo=ipfs_datasets_repo,
        ipfs_accelerate_repo=ipfs_accelerate_repo,
        ipfs_kit_repo=ipfs_kit_repo,
        mike_repo=mike_repo,
    )


def declared_submodule_paths(repo_root: Path | None = None) -> frozenset[str]:
    """Return submodule paths declared in ``.gitmodules``.

    This reads the committed declaration only. It does not update submodules
    or walk their trees.
    """

    root = repo_root if repo_root is not None else get_repo_paths().repo_root
    gitmodules = root / ".gitmodules"
    try:
        text = gitmodules.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    paths: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("path =") or stripped.startswith("path="):
            paths.append(stripped.split("=", 1)[1].strip())
    return frozenset(paths)


def classify_owner_checkout(
    owner_path: Path,
    *,
    canonical_relative: str,
    declared_submodule: bool,
) -> dict[str, object]:
    """Distinguish a populated checkout from a committed opaque gitlink.

    A populated checkout has the named canonical source file. A declared
    submodule whose working tree does not contain that file is an opaque
    gitlink, even when the git index itself cannot be read. This does not
    invent a commit id for either case.
    """

    canonical = owner_path / canonical_relative
    try:
        populated = canonical.is_file()
    except OSError:
        populated = False
    if populated:
        kind = "populated_checkout"
    elif declared_submodule:
        kind = "opaque_gitlink"
    else:
        kind = "missing_checkout"
    return {
        "checkout_kind": kind,
        "populated": populated,
        "declared_submodule": declared_submodule,
        "canonical_relative": canonical_relative.replace("\\", "/"),
    }


def observe_checked_out_commit(owner_path: Path) -> dict[str, str]:
    """Read a checked-out commit when ``.git`` is readable.

    Permission errors and unresolved gitdir pointers stay typed unavailable
    records. They are not replaced with a declared pin. A file-shaped ``.git``
    entry is a gitdir pointer even when the sandbox cannot read it.
    """

    unavailable = {"status": "unavailable", "error_type": "", "commit": ""}
    git_entry = owner_path / ".git"
    try:
        if git_entry.is_file():
            try:
                payload = git_entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                unavailable["error_type"] = "GitdirPointer"
                return unavailable
            if payload.startswith("gitdir:"):
                unavailable["error_type"] = "GitdirPointer"
                return unavailable
            unavailable["error_type"] = "NotAGitDirectory"
            return unavailable
        head_path = git_entry / "HEAD"
        head = head_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        unavailable["error_type"] = type(exc).__name__
        return unavailable
    if len(head) == 40 and all(character in "0123456789abcdef" for character in head):
        return {"status": "available", "error_type": "", "commit": head}
    if head.startswith("ref:"):
        ref_name = head.split(":", 1)[1].strip()
        ref_path = git_entry / ref_name
        try:
            commit = ref_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            unavailable["error_type"] = type(exc).__name__
            return unavailable
        if len(commit) == 40 and all(character in "0123456789abcdef" for character in commit):
            return {"status": "available", "error_type": "", "commit": commit}
        unavailable["error_type"] = "UnresolvedHead"
        return unavailable
    unavailable["error_type"] = "UnresolvedHead"
    return unavailable


def _matches_package_root(module_name: str, package_root: str) -> bool:
    return module_name == package_root or module_name.startswith(f"{package_root}.")


def _candidate_ipfs_source_roots() -> list[Path]:
    """Find vendored dependency roots from worktrees and the primary checkout."""

    paths = get_repo_paths()
    roots: list[Path] = []
    for candidate in [
        paths.ipfs_datasets_repo,
        *[parent / "ipfs_datasets_py" for parent in (paths.repo_root, *paths.repo_root.parents)],
    ]:
        if candidate not in roots:
            roots.append(candidate)
    return roots


def _package_dir_for_root(package_root: str) -> Path | None:
    paths = get_repo_paths()
    candidates: list[Path] = []
    if package_root == "ipfs_datasets_py":
        for source_root in _candidate_ipfs_source_roots():
            candidates.extend(
                [
                    source_root / "ipfs_datasets_py",
                    source_root
                    / "ipfs_accelerate_py"
                    / "ipfs_datasets_py"
                    / "ipfs_datasets_py",
                ]
            )
    elif package_root == "ipfs_accelerate_py":
        candidates = [
            paths.ipfs_accelerate_repo / "ipfs_accelerate_py",
            *[
                source_root / "ipfs_accelerate_py" / "ipfs_accelerate_py"
                for source_root in _candidate_ipfs_source_roots()
            ],
        ]
    elif package_root == "ipfs_kit_py" and paths.ipfs_kit_repo is not None:
        candidates = [paths.ipfs_kit_repo / "ipfs_kit_py"]

    for candidate in candidates:
        if (candidate / "__init__.py").exists():
            return candidate
    return candidates[0] if candidates else None


def _loaded_package_matches(package_root: str, package_dir: Path) -> bool:
    loaded = sys.modules.get(package_root)
    if loaded is None:
        return False
    loaded_file = str(getattr(loaded, "__file__", "") or "")
    if loaded_file and Path(loaded_file).resolve() == (package_dir / "__init__.py").resolve():
        return True
    loaded_paths = [str(Path(path).resolve()) for path in getattr(loaded, "__path__", [])]
    return str(package_dir.resolve()) in loaded_paths


def _prime_repo_package(package_root: str) -> None:
    package_dir = _package_dir_for_root(package_root)
    if package_dir is None:
        return
    init_file = package_dir / "__init__.py"
    if not init_file.exists():
        return

    if _loaded_package_matches(package_root, package_dir):
        return

    for module_name in list(sys.modules):
        if _matches_package_root(module_name, package_root):
            sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location(
        package_root,
        init_file,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_root] = module
    original_sys_path = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_sys_path


def ensure_import_paths(module_name: str = "", missing_module_name: str = "") -> RepoPaths:
    paths = get_repo_paths()
    for package_root in ("ipfs_datasets_py", "ipfs_accelerate_py", "ipfs_kit_py"):
        if _matches_package_root(module_name, package_root) or _matches_package_root(missing_module_name, package_root):
            _prime_repo_package(package_root)
    return paths


def _should_retry_with_repo_paths(module_name: str, error: ModuleNotFoundError) -> bool:
    missing_module_name = str(getattr(error, "name", "") or "")
    return any(
        _matches_package_root(value, package_root)
        for package_root in ("ipfs_datasets_py", "ipfs_accelerate_py", "ipfs_kit_py")
        for value in (module_name, missing_module_name)
        if value
    )


def _build_import_failure(exc: BaseException, *, module_name: str, attr_name: str = "") -> ImportFailure:
    return ImportFailure(
        module_name=module_name,
        attr_name=attr_name,
        error_type=type(exc).__name__,
        message=str(exc),
        missing_module_name=str(getattr(exc, "name", "") or ""),
    )


def _build_retry_import_failure(
    initial_exc: BaseException,
    retry_exc: BaseException,
    *,
    module_name: str,
) -> ImportFailure:
    """Preserve both failures from a vendored-package recovery attempt."""

    retry_failure = _build_import_failure(retry_exc, module_name=module_name)
    initial_failure = _build_import_failure(initial_exc, module_name=module_name)
    return ImportFailure(
        module_name=retry_failure.module_name,
        attr_name=retry_failure.attr_name,
        error_type=retry_failure.error_type,
        message=(
            f"{retry_failure.message} "
            "(vendored-path recovery was triggered by "
            f"{initial_failure.error_type}: {initial_failure.message})"
        ),
        missing_module_name=retry_failure.missing_module_name,
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


_MISSING_MODULE_PATTERN = re.compile(r"No module named ['\"]([^'\"]+)['\"]")


def import_failure_missing_module(error: Any) -> str:
    """Return the dependency named by an import failure, when one is known.

    ``ModuleNotFoundError.name`` is the authoritative source.  The message
    fallback keeps diagnostics useful for serialized or reconstructed failures
    that no longer carry the original exception object.
    """

    if isinstance(error, ImportFailure):
        missing_module = error.missing_module_name
    else:
        missing_module = str(getattr(error, "name", "") or "")
    if missing_module:
        return missing_module

    if import_failure_type(error) != "ModuleNotFoundError":
        return ""
    match = _MISSING_MODULE_PATTERN.search(import_failure_message(error) or "")
    return match.group(1) if match else ""


def optional_dependency_install_command(
    extra_name: str = "",
    *,
    package_name: str = "ipfs_datasets_py",
) -> str:
    """Build a copyable command for installing an optional provider extra."""

    package = str(package_name or "").strip()
    extra = str(extra_name or "").strip()
    if not package:
        return ""
    requirement = f"{package}[{extra}]" if extra else package
    return f'python -m pip install "{requirement}"'


def build_import_failure_diagnostic(
    error: Any,
    *,
    module_name: str = "",
    capability: str = "",
    install_extra: str = "",
    package_name: str = "ipfs_datasets_py",
) -> dict[str, str | None]:
    """Normalize an optional import result into an actionable stable payload.

    Adapter consumers should not have to parse exception text to distinguish a
    missing extra from an incompatible provider version.  This helper always
    returns the same keys and preserves the raw error separately from the
    operator-facing reason.
    """

    error_type = import_failure_type(error)
    error_message = import_failure_message(error) or ""
    requested_module = str(
        module_name or getattr(error, "module_name", "") or ""
    ).strip()
    capability_name = str(capability or requested_module or "optional integration").strip()
    missing_module = import_failure_missing_module(error)
    attr_name = str(getattr(error, "attr_name", "") or "")

    diagnostic: dict[str, str | None] = {
        "reason_code": "",
        "degraded_reason": None,
        "error_type": error_type,
        "error_message": error_message,
        "missing_module": missing_module,
        "remediation": "",
    }
    if error is None:
        return diagnostic

    install_command = optional_dependency_install_command(
        install_extra,
        package_name=package_name,
    )
    remediation = (
        f"Run `{install_command}` and restart the application."
        if install_command
        else "Install or update the optional provider and restart the application."
    )
    if missing_module == package_name or missing_module.startswith(f"{package_name}."):
        remediation += (
            " For a source checkout, initialize the vendored provider with "
            "`git submodule update --init --recursive ipfs_datasets_py`."
        )

    if error_type == "ModuleNotFoundError" or missing_module:
        reason_code = "missing_optional_dependency"
        subject = missing_module or requested_module
        degraded_reason = (
            f"Optional capability '{capability_name}' is unavailable because Python module "
            f"'{subject}' is missing. {remediation}"
        )
    elif error_type == "AttributeError" or attr_name:
        reason_code = "optional_dependency_api_mismatch"
        required_api = f"attribute '{attr_name}'" if attr_name else "the required API"
        degraded_reason = (
            f"Optional capability '{capability_name}' is unavailable because module "
            f"'{requested_module}' does not provide {required_api}. {remediation}"
        )
    elif error_type == "ImportError":
        reason_code = "optional_dependency_import_error"
        context = f" ({error_message})" if error_message else ""
        degraded_reason = (
            f"Optional capability '{capability_name}' could not import module "
            f"'{requested_module}'{context}. {remediation}"
        )
    else:
        reason_code = "optional_dependency_load_error"
        context = f" ({error_type}: {error_message})" if error_message else ""
        degraded_reason = (
            f"Optional capability '{capability_name}' could not load module "
            f"'{requested_module}'{context}. {remediation}"
        )

    diagnostic.update(
        {
            "reason_code": reason_code,
            "degraded_reason": degraded_reason,
            "remediation": remediation,
        }
    )
    return diagnostic


def actionable_import_failure_message(
    error: Any,
    *,
    module_name: str = "",
    capability: str = "",
    extra_name: str = "",
    package_name: str = "ipfs_datasets_py",
) -> str | None:
    """Return only the operator-facing reason from a normalized diagnostic."""

    return build_import_failure_diagnostic(
        error,
        module_name=module_name,
        capability=capability,
        install_extra=extra_name,
        package_name=package_name,
    )["degraded_reason"]


def _import_module_preserving_sys_path(module_name: str) -> Any:
    """Import an optional provider without leaking provider path side effects."""

    original_sys_path = list(sys.path)
    try:
        return importlib.import_module(module_name)
    finally:
        sys.path[:] = original_sys_path


def import_module_optional(module_name: str) -> tuple[Any | None, ImportFailure | None]:
    """Import an optional provider and return ordinary failures as diagnostics.

    Provider modules execute arbitrary initialization code, so import failures
    are not limited to :class:`ImportError`.  This adapter boundary intentionally
    converts ordinary exceptions into ``ImportFailure`` while allowing process
    control exceptions outside the ``Exception`` hierarchy to propagate.
    """

    try:
        return _import_module_preserving_sys_path(module_name), None
    except ModuleNotFoundError as exc:
        if _should_retry_with_repo_paths(module_name, exc):
            try:
                ensure_import_paths(
                    module_name=module_name,
                    missing_module_name=str(getattr(exc, "name", "") or ""),
                )
                return _import_module_preserving_sys_path(module_name), None
            except Exception as retry_exc:
                # The exception is returned as structured adapter state rather
                # than discarded; this keeps optional-provider degradation
                # non-fatal and observable to every caller.
                return None, _build_retry_import_failure(
                    exc,
                    retry_exc,
                    module_name=module_name,
                )
        return None, _build_import_failure(exc, module_name=module_name)
    except Exception as exc:
        # Intentional optional-provider boundary: return the exception's type,
        # message, and missing-module metadata to the caller.  Do not narrow
        # this to ImportError—provider module initialization can raise any
        # ordinary Exception—or broaden it to process-control BaseExceptions.
        return None, _build_import_failure(exc, module_name=module_name)


def import_attr_optional(module_name: str, attr_name: str) -> tuple[Any | None, ImportFailure | None]:
    """Import an optional module attribute, reporting only genuine absence.

    A module can implement dynamic attribute lookup with ``__getattr__``.  Such
    code may raise arbitrary exceptions, but only ``AttributeError`` represents
    the normal "capability is not exposed" outcome.  Provider runtime failures
    must remain visible to the caller rather than being mislabeled as optional
    capability degradation.
    """

    module, error = import_module_optional(module_name)
    if module is None:
        return None, error
    try:
        return getattr(module, attr_name), None
    except AttributeError as exc:
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
