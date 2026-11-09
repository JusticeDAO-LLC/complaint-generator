from pathlib import Path
from unittest.mock import patch

import pytest

from integrations.ipfs_datasets import loader as loader_module
from integrations.ipfs_datasets.loader import RepoPaths, import_module_optional


pytestmark = pytest.mark.no_auto_heavy

MODULE_NAME = "ipfs_datasets_py.logic"


def _missing_vendored_package() -> ModuleNotFoundError:
    error = ModuleNotFoundError("No module named 'ipfs_datasets_py'")
    error.name = "ipfs_datasets_py"
    return error


def test_vendored_path_preparation_failure_is_returned_with_trigger_context():
    initial_error = _missing_vendored_package()

    with patch.object(
        loader_module.importlib,
        "import_module",
        side_effect=initial_error,
    ) as import_module_mock:
        with patch.object(
            loader_module,
            "ensure_import_paths",
            side_effect=RuntimeError("vendored package initialization failed"),
        ) as ensure_paths_mock:
            module, error = import_module_optional(MODULE_NAME)

    assert module is None
    assert error is not None
    assert error.error_type == "RuntimeError"
    assert error.missing_module_name == ""
    assert "vendored package initialization failed" in error.message
    assert "ModuleNotFoundError: No module named 'ipfs_datasets_py'" in error.message
    ensure_paths_mock.assert_called_once_with(
        module_name=MODULE_NAME,
        missing_module_name="ipfs_datasets_py",
    )
    import_module_mock.assert_called_once_with(MODULE_NAME)


def test_vendored_retry_failure_is_returned_with_both_attempts_observable():
    initial_error = _missing_vendored_package()
    retry_error = ModuleNotFoundError("No module named 'symbolicai'")
    retry_error.name = "symbolicai"

    with patch.object(
        loader_module.importlib,
        "import_module",
        side_effect=[initial_error, retry_error],
    ) as import_module_mock:
        with patch.object(
            loader_module,
            "ensure_import_paths",
            return_value=RepoPaths(
                Path("/repo"),
                Path("/repo/ipfs_datasets_py"),
                Path("/repo/ipfs_datasets_py/ipfs_accelerate_py"),
            ),
        ):
            module, error = import_module_optional(MODULE_NAME)

    assert module is None
    assert error is not None
    assert error.error_type == "ModuleNotFoundError"
    assert error.missing_module_name == "symbolicai"
    assert "No module named 'symbolicai'" in error.message
    assert "ModuleNotFoundError: No module named 'ipfs_datasets_py'" in error.message
    assert import_module_mock.call_count == 2


def test_vendored_retry_does_not_intercept_process_control_exceptions():
    initial_error = _missing_vendored_package()

    with patch.object(
        loader_module.importlib,
        "import_module",
        side_effect=[initial_error, KeyboardInterrupt()],
    ):
        with patch.object(loader_module, "ensure_import_paths"):
            with pytest.raises(KeyboardInterrupt):
                import_module_optional(MODULE_NAME)
