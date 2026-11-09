import builtins
import importlib.util
from pathlib import Path

import pytest


def _load_root_conftest():
    conftest_path = Path(__file__).with_name("conftest.py")
    spec = importlib.util.spec_from_file_location("ref_231_root_conftest", conftest_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fail_ipfs_import(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    original_import = builtins.__import__

    def controlled_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "ipfs_datasets_py":
            raise error
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", controlled_import)


def test_preload_warns_when_optional_package_import_is_unavailable(monkeypatch):
    root_conftest = _load_root_conftest()
    expected_init = "/checkout/ipfs_datasets_py/__init__.py"
    _fail_ipfs_import(monkeypatch, ModuleNotFoundError("missing optional dependency"))

    with pytest.warns(
        pytest.PytestConfigWarning,
        match=r"Could not preload.*missing optional dependency",
    ) as captured:
        root_conftest._preload_ipfs_datasets_package(expected_init)

    assert expected_init in str(captured[0].message)


def test_preload_does_not_swallow_package_initializer_failures(monkeypatch):
    root_conftest = _load_root_conftest()
    _fail_ipfs_import(monkeypatch, RuntimeError("broken package initializer"))

    with pytest.raises(RuntimeError, match="broken package initializer"):
        root_conftest._preload_ipfs_datasets_package(
            "/checkout/ipfs_datasets_py/__init__.py"
        )
