"""Local conftest for optimizer tests - disable LLM auto-detection for specific test files."""

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """
    Run before global conftest to prevent auto-skipping of lazy backend loader tests.
    Mark them explicitly so globalconftest won't auto-detect them.
    """
    for item in items:
        path = str(item.fspath)
        if "test_lazy_backend_loader" in path:
            # Mark as a unit test to signal it's not an LLM test
            # despite containing "llm" in the code
            item.add_marker(pytest.mark.unit)

