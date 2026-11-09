import sys
from unittest.mock import patch

import pytest

from integrations.ipfs_datasets import loader as loader_module
from integrations.ipfs_datasets.loader import import_module_optional


pytestmark = pytest.mark.no_auto_heavy

MODULE_NAME = "third_party_optional_provider"


def test_provider_initialization_failure_is_returned_as_structured_state():
    provider_error = RuntimeError("provider configuration is invalid")

    with patch.object(
        loader_module.importlib,
        "import_module",
        side_effect=provider_error,
    ) as import_module_mock:
        module, error = import_module_optional(MODULE_NAME)

    assert module is None
    assert error is not None
    assert error.as_dict() == {
        "module_name": MODULE_NAME,
        "attr_name": "",
        "error_type": "RuntimeError",
        "message": "provider configuration is invalid",
        "missing_module_name": "",
    }
    import_module_mock.assert_called_once_with(MODULE_NAME)


def test_nested_missing_dependency_is_preserved_without_vendored_retry():
    provider_error = ModuleNotFoundError("No module named 'provider_runtime'")
    provider_error.name = "provider_runtime"

    with patch.object(
        loader_module.importlib,
        "import_module",
        side_effect=provider_error,
    ) as import_module_mock:
        with patch.object(loader_module, "ensure_import_paths") as ensure_paths_mock:
            module, error = import_module_optional(MODULE_NAME)

    assert module is None
    assert error is not None
    assert error.error_type == "ModuleNotFoundError"
    assert error.message == "No module named 'provider_runtime'"
    assert error.missing_module_name == "provider_runtime"
    ensure_paths_mock.assert_not_called()
    import_module_mock.assert_called_once_with(MODULE_NAME)


@pytest.mark.parametrize("control_exception", [KeyboardInterrupt(), SystemExit(17)])
def test_process_control_exceptions_are_not_converted(control_exception):
    with patch.object(
        loader_module.importlib,
        "import_module",
        side_effect=control_exception,
    ):
        with pytest.raises(type(control_exception)) as raised:
            import_module_optional(MODULE_NAME)

    assert raised.value is control_exception


def test_failed_provider_import_cannot_leak_sys_path_mutations():
    original_sys_path = list(sys.path)

    def fail_after_mutating_path(module_name):
        assert module_name == MODULE_NAME
        sys.path.insert(0, "/provider/private/import/path")
        raise RuntimeError("provider initialization failed")

    try:
        with patch.object(
            loader_module.importlib,
            "import_module",
            side_effect=fail_after_mutating_path,
        ):
            module, error = import_module_optional(MODULE_NAME)

        assert module is None
        assert error is not None
        assert error.error_type == "RuntimeError"
        assert sys.path == original_sys_path
    finally:
        sys.path[:] = original_sys_path
