from types import ModuleType
from unittest.mock import patch

import pytest

from integrations.ipfs_datasets import loader as loader_module
from integrations.ipfs_datasets.loader import import_attr_optional


pytestmark = pytest.mark.no_auto_heavy

MODULE_NAME = "optional_provider"


def test_missing_optional_attribute_is_returned_as_structured_failure() -> None:
    module = ModuleType(MODULE_NAME)

    with patch.object(loader_module, "import_module_optional", return_value=(module, None)):
        value, error = import_attr_optional(MODULE_NAME, "missing_capability")

    assert value is None
    assert error is not None
    assert error.module_name == MODULE_NAME
    assert error.attr_name == "missing_capability"
    assert error.error_type == "AttributeError"
    assert "missing_capability" in error.message


def test_dynamic_attribute_runtime_failure_is_not_swallowed() -> None:
    module = ModuleType(MODULE_NAME)

    def fail_dynamic_lookup(attr_name: str) -> object:
        raise RuntimeError(f"failed to initialize {attr_name}")

    module.__getattr__ = fail_dynamic_lookup  # type: ignore[attr-defined]

    with patch.object(loader_module, "import_module_optional", return_value=(module, None)):
        with pytest.raises(RuntimeError, match="failed to initialize dynamic_capability"):
            import_attr_optional(MODULE_NAME, "dynamic_capability")


def test_available_optional_attribute_is_returned_without_failure() -> None:
    module = ModuleType(MODULE_NAME)
    capability = object()
    module.available_capability = capability

    with patch.object(loader_module, "import_module_optional", return_value=(module, None)):
        value, error = import_attr_optional(MODULE_NAME, "available_capability")

    assert value is capability
    assert error is None
