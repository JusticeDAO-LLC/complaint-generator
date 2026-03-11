import os
import re
import sys

import pytest


_LLM_KEYWORDS = (
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "vertexai",
    "bedrock",
    "ollama",
    "chatcompletion",
    "chat.completions",
    "responses.create",
    "completions.create",
    "transformers",
    "pipeline(",
    "autotokenizer",
    "automodelforcausallm",
)

_NETWORK_KEYWORDS = (
    "requests.",
    "http://",
    "https://",
    "aiohttp",
    "httpx",
    "websocket",
    "websockets",
    "socket.",
    "urllib",
    "selenium",
    "playwright",
)

_HEAVY_KEYWORDS = (
    "cuda",
    "torch",
    "tensorflow",
    "jax",
    "accelerate",
    "bitsandbytes",
    "faiss",
    "sentence_transformers",
    "chromadb",
    "milvus",
)

_RESERVED_EXAMPLE_URL_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*example\.(?:com|org|net)(?:/[^\s\"'<>)]*)?",
    re.IGNORECASE,
)


def _truthy_env(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _strip_reserved_example_urls(text: str) -> str:
    """Ignore reserved example-domain fixtures when auto-classifying network tests."""

    return _RESERVED_EXAMPLE_URL_RE.sub("reserved-example-url", text)


def pytest_addoption(parser):
    group = parser.getgroup("gating")
    group.addoption(
        "--run-llm",
        action="store_true",
        default=False,
        help="Run tests that require an LLM / large model stack.",
    )
    group.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Run tests that require external network access.",
    )
    group.addoption(
        "--run-heavy",
        action="store_true",
        default=False,
        help="Run tests that are resource-heavy (GPU/large deps/datasets).",
    )


def pytest_configure() -> None:
    """Ensure the ipfs_datasets_py submodule package is importable in tests."""

    repo_root = os.path.dirname(os.path.dirname(__file__))
    submodule_root = os.path.join(repo_root, "ipfs_datasets_py")
    if os.path.isdir(submodule_root) and submodule_root not in sys.path:
        sys.path.insert(0, submodule_root)

    # With pytest --import-mode=importlib, the repository root isn't guaranteed to be on
    # sys.path. Add it so first-party modules (e.g. adversarial_harness/) import cleanly.
    # Keep it AFTER the submodule path to avoid resolving `ipfs_datasets_py` to the
    # submodule repo root directory.
    if repo_root not in sys.path:
        insert_at = 1 if sys.path and sys.path[0] == submodule_root else 0
        sys.path.insert(insert_at, repo_root)

    # If something imported `ipfs_datasets_py` before we adjusted sys.path, Python may have
    # created a namespace-like module rooted at complaint-generator/ipfs_datasets_py/ (the
    # submodule repo root), which does not export `llm_router`. Reset it so subsequent
    # imports resolve to the actual package at ipfs_datasets_py/ipfs_datasets_py/.
    expected_init = os.path.join(submodule_root, "ipfs_datasets_py", "__init__.py")
    mod = sys.modules.get("ipfs_datasets_py")
    if mod is not None:
        mod_file = os.path.abspath(getattr(mod, "__file__", "") or "")
        is_namespace_like = getattr(mod, "__file__", None) is None and hasattr(mod, "__path__")
        is_wrong_location = os.path.isfile(expected_init) and mod_file and mod_file != os.path.abspath(expected_init)
        if is_namespace_like or is_wrong_location:
            for name in list(sys.modules.keys()):
                if name == "ipfs_datasets_py" or name.startswith("ipfs_datasets_py."):
                    sys.modules.pop(name, None)

    # Vendored dependency layout: ipfs_accelerate_py/ipfs_accelerate_py/
    accelerate_repo_root = os.path.join(submodule_root, "ipfs_accelerate_py")
    if os.path.isdir(accelerate_repo_root) and accelerate_repo_root not in sys.path:
        sys.path.insert(0, accelerate_repo_root)

    # Best-effort: import the real package now that sys.path is set, so tests can safely
    # do `from ipfs_datasets_py import llm_router` during collection.
    if os.path.isfile(expected_init):
        try:
            import importlib

            importlib.invalidate_caches()
            import ipfs_datasets_py  # noqa: F401
        except Exception:
            pass


def pytest_collection_modifyitems(config, items):
    """Skip LLM/network/heavy tests by default; allow opt-in via flags or env vars."""
    run_llm = bool(getattr(config.option, "run_llm", False)) or _truthy_env("RUN_LLM_TESTS")
    run_network = bool(getattr(config.option, "run_network", False)) or _truthy_env("RUN_NETWORK_TESTS")
    run_heavy = bool(getattr(config.option, "run_heavy", False)) or _truthy_env("RUN_HEAVY_TESTS")

    file_cache: dict[str, tuple[bool, bool, bool]] = {}

    def _classify_file(path: str) -> tuple[bool, bool, bool]:
        cached = file_cache.get(path)
        if cached is not None:
            return cached

        is_llm = False
        is_network = False
        is_heavy = False
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().lower()
            network_text = _strip_reserved_example_urls(text)
            is_llm = any(k in text for k in _LLM_KEYWORDS)
            is_network = any(k in network_text for k in _NETWORK_KEYWORDS)
            is_heavy = any(k in text for k in _HEAVY_KEYWORDS)
        except Exception:
            pass

        file_cache[path] = (is_llm, is_network, is_heavy)
        return file_cache[path]

    skip_llm = pytest.mark.skip(reason="Skipped by default (LLM). Use --run-llm or RUN_LLM_TESTS=1")
    skip_network = pytest.mark.skip(reason="Skipped by default (network). Use --run-network or RUN_NETWORK_TESTS=1")
    skip_heavy = pytest.mark.skip(reason="Skipped by default (heavy). Use --run-heavy or RUN_HEAVY_TESTS=1")

    for item in items:
        marked_llm = item.get_closest_marker("llm") is not None
        marked_network = item.get_closest_marker("network") is not None
        marked_heavy = item.get_closest_marker("heavy") is not None
        marked_no_auto_network = item.get_closest_marker("no_auto_network") is not None

        path = str(getattr(item, "fspath", "") or "")
        auto_llm = False
        auto_network = False
        auto_heavy = False
        if path:
            auto_llm, auto_network, auto_heavy = _classify_file(path)
        if marked_no_auto_network:
            auto_network = False

        if (marked_llm or auto_llm) and not run_llm:
            item.add_marker(skip_llm)
        if (marked_network or auto_network) and not run_network:
            item.add_marker(skip_network)
        if (marked_heavy or auto_heavy) and not run_heavy:
            item.add_marker(skip_heavy)