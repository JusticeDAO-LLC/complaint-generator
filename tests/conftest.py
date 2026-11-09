import importlib
import os
import re
import sys
import warnings

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

_HYPOTHESIS_REQUIRED_TESTS = (
    "test_mcplusplus_v39_session84_properties.py",
    "test_mcplusplus_v39_session84_recovery.py",
    "test_observability_property_based.py",
    "test_property_based_extraction_testing.py",
    "test_ontology_comparator.py",
    "test_ontology_critic_hypothesis.py",
    "test_score_analyzer.py",
)

_OPTIONAL_UPSTREAM_REQUIRED_TESTS = (
    "test_agentic_evidence_download.py",
    "test_attachment_text_extractor.py",
    "test_complaint_generator_tools.py",
    "test_docket_workspace_surface.py",
    "test_email_agentic_search.py",
    "test_email_authority_enrichment.py",
    "test_email_duckdb_index.py",
    "test_email_graphrag.py",
    "test_email_import.py",
    "test_email_seed_planner.py",
    "test_email_timeline_handoff.py",
    "test_evidence_relevance.py",
)

_OPTIONAL_UPSTREAM_MODULES = (
    "ipfs_datasets_py.processors.legal_data.email_relevance",
    "ipfs_datasets_py.processors.legal_data.email_agentic_search",
    "ipfs_datasets_py.processors.legal_data.email_authority_enrichment",
    "ipfs_datasets_py.processors.legal_data.email_corpus",
    "ipfs_datasets_py.processors.legal_data.email_import",
    "ipfs_datasets_py.processors.legal_data.email_seed_planner",
    "ipfs_datasets_py.processors.legal_data.email_timeline_handoff",
    "ipfs_datasets_py.processors.legal_data.workspace_dataset",
    "ipfs_datasets_py.processors.multimedia.attachment_text_extractor",
    "ipfs_datasets_py.processors.multimedia.email_duckdb_index",
)


def _truthy_env(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _strip_reserved_example_urls(text: str) -> str:
    """Ignore reserved example-domain fixtures when auto-classifying network tests."""

    return _RESERVED_EXAMPLE_URL_RE.sub("reserved-example-url", text)


def _classify_test_file(path: str) -> tuple[bool, bool, bool]:
    """Return the automatic LLM, network, and heavy classifications for a test.

    A collected test file should normally remain readable.  If it becomes
    unavailable between discovery and classification, gate it behind every
    opt-in rather than accidentally running a potentially external or expensive
    test.  Only filesystem errors are recoverable here; classifier defects must
    remain visible during collection.
    """

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as source_file:
            text = source_file.read().lower()
    except OSError as exc:
        warnings.warn(
            (
                f"Could not read test file {path!r} for automatic gating; "
                "requiring LLM, network, and heavy test opt-ins: "
                f"{type(exc).__name__}: {exc}"
            ),
            pytest.PytestCollectionWarning,
            stacklevel=2,
        )
        return True, True, True

    network_text = _strip_reserved_example_urls(text)
    return (
        any(keyword in text for keyword in _LLM_KEYWORDS),
        any(keyword in network_text for keyword in _NETWORK_KEYWORDS),
        any(keyword in text for keyword in _HEAVY_KEYWORDS),
    )


def _candidate_ipfs_dataset_roots(repo_root: str) -> list[str]:
    """Return local or supervisor-parent ipfs_datasets_py checkouts."""

    root = os.path.abspath(repo_root)
    candidates: list[str] = []
    current = root
    while True:
        for candidate in (
            os.path.join(current, "external", "ipfs_datasets_py"),
            os.path.join(current, "ipfs_datasets_py"),
        ):
            if candidate not in candidates:
                candidates.append(candidate)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return candidates


def _select_ipfs_dataset_root(repo_root: str) -> str:
    """Honor explicit source paths before discovering a complete checkout.

    Supervisor worktrees can contain empty submodule directories.  A pinned,
    absolute source checkout supplied through PYTHONPATH must take precedence
    over an unrelated standalone checkout found in a parent directory.
    """

    fallback = os.path.join(repo_root, "ipfs_datasets_py")
    explicit_roots = [
        entry
        for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if os.path.isabs(entry)
    ]
    for candidate in explicit_roots + _candidate_ipfs_dataset_roots(repo_root):
        expected_init = os.path.join(candidate, "ipfs_datasets_py", "__init__.py")
        if os.path.isfile(expected_init):
            return candidate
    return fallback


def _optional_upstream_module_available(module_name: str) -> bool:
    """Probe optional modules without hiding unrelated initializer failures."""

    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError as exc:
        # find_spec imports parents of dotted names.  An absent requested
        # parent means this optional feature is unavailable; a missing import
        # inside a present parent is a different failure and remains visible.
        if exc.name and (
            module_name == exc.name or module_name.startswith(exc.name + ".")
        ):
            return False
        raise
    except ValueError as exc:
        # Some tests install lightweight module proxies without a ModuleSpec.
        # Treat that specific find_spec result as unavailable, not a crash.
        if str(exc) == f"{module_name}.__spec__ is None":
            return False
        raise


def _preload_ipfs_datasets_package(expected_init: str) -> None:
    """Preload the vendored package, reporting only unavailable imports.

    Preloading is a compatibility aid for collection, so an unavailable optional
    import should not prevent unrelated tests from running.  Other exceptions
    indicate a broken package initializer and must remain visible.
    """

    importlib.invalidate_caches()
    try:
        import ipfs_datasets_py  # noqa: F401
    except ImportError as exc:
        warnings.warn(
            (
                "Could not preload the vendored ipfs_datasets_py package from "
                f"{expected_init}: {type(exc).__name__}: {exc}"
            ),
            pytest.PytestConfigWarning,
            stacklevel=2,
        )


def pytest_addoption(parser):
    if importlib.util.find_spec("pytest_asyncio") is None:
        parser.addini(
            "asyncio_mode",
            "Compatibility shim for environments where pytest-asyncio is unavailable.",
            default="auto",
        )

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


def pytest_ignore_collect(collection_path, path=None, config=None):
    """Avoid collection-time import errors for optional property-test deps."""

    candidate = str(collection_path if collection_path is not None else path)
    if importlib.util.find_spec("hypothesis") is None:
        if any(name in candidate for name in _HYPOTHESIS_REQUIRED_TESTS):
            return True
    if any(name in candidate for name in _OPTIONAL_UPSTREAM_REQUIRED_TESTS):
        if any(not _optional_upstream_module_available(module) for module in _OPTIONAL_UPSTREAM_MODULES):
            return True
    return None


def pytest_configure() -> None:
    """Ensure the ipfs_datasets_py submodule package is importable in tests."""

    repo_root = os.path.dirname(os.path.dirname(__file__))
    submodule_root = _select_ipfs_dataset_root(repo_root)
    if os.path.isdir(submodule_root):
        # A prior import/bootstrap may already have put this path behind a
        # legacy checkout.  Reposition it before clearing cached modules.
        sys.path[:] = [entry for entry in sys.path if entry != submodule_root]
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

    # Sibling checkout under external/, with the older nested layout as a fallback.
    external_accelerate = os.path.join(repo_root, "external", "ipfs_accelerate_py")
    nested_accelerate = os.path.join(submodule_root, "ipfs_accelerate_py")
    accelerate_repo_root = external_accelerate if os.path.isdir(external_accelerate) else nested_accelerate
    if os.path.isdir(accelerate_repo_root) and accelerate_repo_root not in sys.path:
        sys.path.insert(0, accelerate_repo_root)

    # Best-effort: import the real package now that sys.path is set, so tests can safely
    # do `from ipfs_datasets_py import llm_router` during collection.
    if os.path.isfile(expected_init):
        _preload_ipfs_datasets_package(expected_init)


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

        # Exclude specific test files from auto-detection
        # (files containing "llm" in code but not actually requiring LLM features)
        if (
            "test_lazy_backend_loader" in path
            or "test_circuit_breaker" in path
            or "test_mcplusplus_v38_session83" in path
            or "test_mcplusplus_v39_session84_properties" in path
            or "test_mcplusplus_v39_session84_recovery" in path
            or "test_mcplusplus_v39_session84_concurrency" in path
            or "test_mcplusplus_v39_session84_observability" in path
            or "test_integration_observability_core" in path
            or "test_batch_264_api_type_contracts" in path
            or "test_batch_265_path_validation_security" in path
            or "test_document_pipeline" in path
            or "test_run_hacc_grounded_pipeline_cli" in path
            or "test_adversarial_harness" in path
            or "test_multimodal_router_backend" in path
            or "test_accelerate_router_facade" in path
            or "test_agent_supervisor_jobs" in path
            or "test_complaint_supervisor_cli" in path
            or "test_multimedia_adapter" in path
            or "test_ipfs_kit_storage_adapter" in path
        ):
            file_cache[path] = (False, False, False)
            return file_cache[path]

        file_cache[path] = _classify_test_file(path)
        return file_cache[path]

    skip_llm = pytest.mark.skip(reason="Skipped by default (LLM). Use --run-llm or RUN_LLM_TESTS=1")
    skip_network = pytest.mark.skip(reason="Skipped by default (network). Use --run-network or RUN_NETWORK_TESTS=1")
    skip_heavy = pytest.mark.skip(reason="Skipped by default (heavy). Use --run-heavy or RUN_HEAVY_TESTS=1")

    for item in items:
        marked_llm = item.get_closest_marker("llm") is not None
        marked_network = item.get_closest_marker("network") is not None
        marked_heavy = item.get_closest_marker("heavy") is not None
        marked_no_auto_llm = item.get_closest_marker("no_auto_llm") is not None
        marked_no_auto_network = item.get_closest_marker("no_auto_network") is not None
        marked_no_auto_heavy = item.get_closest_marker("no_auto_heavy") is not None

        path = str(getattr(item, "fspath", "") or "")
        auto_llm = False
        auto_network = False
        auto_heavy = False
        if path:
            auto_llm, auto_network, auto_heavy = _classify_file(path)
        if marked_no_auto_llm:
            auto_llm = False
        if marked_no_auto_network:
            auto_network = False
        if marked_no_auto_heavy:
            auto_heavy = False

        if (marked_llm or auto_llm) and not run_llm:
            item.add_marker(skip_llm)
        if (marked_network or auto_network) and not run_network:
            item.add_marker(skip_network)
        if (marked_heavy or auto_heavy) and not run_heavy:
            item.add_marker(skip_heavy)
