"""Collection regressions for isolated supervisor worktrees and optional imports."""

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _load_root_conftest():
    source = Path(__file__).with_name("conftest.py")
    spec = importlib.util.spec_from_file_location("optional_collection_conftest", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _package(checkout: Path) -> Path:
    package = checkout / "ipfs_datasets_py"
    package.mkdir(parents=True)
    initializer = package / "__init__.py"
    initializer.write_text("", encoding="utf-8")
    return initializer


def test_explicit_checkout_wins_in_actual_configure_with_empty_worker_gitlinks(
    monkeypatch, tmp_path
):
    conftest = _load_root_conftest()
    parent = tmp_path / "campaign"
    worker = parent / "worktrees" / "worker"
    (worker / "tests").mkdir(parents=True)
    (worker / "external" / "ipfs_datasets_py").mkdir(parents=True)
    (worker / "ipfs_datasets_py").mkdir()
    legacy_init = _package(parent / "ipfs_datasets_py")
    modern_root = tmp_path / "pinned-modern"
    modern_init = _package(modern_root)
    (modern_init.parent / "processors").mkdir()
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(tmp_path / "other"), str(modern_root)]))
    monkeypatch.setattr(conftest, "__file__", str(worker / "tests" / "conftest.py"))

    # Exercise configure without changing the running pytest process's import
    # cache.  A legacy package and child are already cached, and modern source
    # is already on sys.path but behind that legacy package.
    unrelated = object()
    module_cache = {
        "ipfs_datasets_py": SimpleNamespace(__file__=str(legacy_init)),
        "ipfs_datasets_py.legacy_child": object(),
        "unrelated": unrelated,
    }
    process = SimpleNamespace(
        path=[str(legacy_init.parent.parent), str(modern_root)],
        modules=module_cache,
    )
    monkeypatch.setattr(conftest, "sys", process)
    preloaded = []
    monkeypatch.setattr(conftest, "_preload_ipfs_datasets_package", preloaded.append)

    conftest.pytest_configure()

    assert conftest._select_ipfs_dataset_root(str(worker)) == str(modern_root)
    assert process.path[0] == str(modern_root)
    assert process.path.count(str(modern_root)) == 1
    assert str(worker) in process.path
    assert preloaded == [str(modern_init)]
    assert module_cache == {"unrelated": unrelated}


def test_without_explicit_checkout_prefers_initialized_local_submodule(monkeypatch, tmp_path):
    conftest = _load_root_conftest()
    worker = tmp_path / "parent" / "worker"
    local = worker / "external" / "ipfs_datasets_py"
    _package(local)
    _package(tmp_path / "parent" / "ipfs_datasets_py")
    monkeypatch.delenv("PYTHONPATH", raising=False)

    assert conftest._select_ipfs_dataset_root(str(worker)) == str(local)


def test_incomplete_or_relative_pythonpath_does_not_override_local_checkout(monkeypatch, tmp_path):
    conftest = _load_root_conftest()
    worker = tmp_path / "worker"
    local = worker / "external" / "ipfs_datasets_py"
    _package(local)
    empty = tmp_path / "empty-submodule"
    empty.mkdir()
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(empty), "relative-checkout", ""]))

    assert conftest._select_ipfs_dataset_root(str(worker)) == str(local)


@pytest.mark.parametrize("missing", ["ipfs_datasets_py", "ipfs_datasets_py.processors", "ipfs_datasets_py.processors.absent"])
def test_missing_optional_module_or_parent_is_unavailable(monkeypatch, missing):
    conftest = _load_root_conftest()

    def missing_spec(_name):
        raise ModuleNotFoundError(f"No module named {missing!r}", name=missing)

    monkeypatch.setattr(conftest.importlib.util, "find_spec", missing_spec)
    assert conftest._optional_upstream_module_available("ipfs_datasets_py.processors.absent") is False


@pytest.mark.parametrize("result, expected", [(None, False), (object(), True)])
def test_optional_spec_presence(monkeypatch, result, expected):
    conftest = _load_root_conftest()
    monkeypatch.setattr(conftest.importlib.util, "find_spec", lambda _name: result)
    assert conftest._optional_upstream_module_available("optional.module") is expected


@pytest.mark.parametrize(
    "error",
    [
        ModuleNotFoundError("No module named 'boto3'", name="boto3"),
        ImportError("broken optional package initializer"),
        RuntimeError("initializer defect"),
        ValueError("unexpected finder failure"),
    ],
)
def test_optional_probe_does_not_hide_unrelated_import_failures(monkeypatch, error):
    conftest = _load_root_conftest()

    def broken_spec(_name):
        raise error

    monkeypatch.setattr(conftest.importlib.util, "find_spec", broken_spec)
    with pytest.raises(type(error), match=str(error)):
        conftest._optional_upstream_module_available("ipfs_datasets_py.processors.absent")


def test_real_spec_less_module_proxy_is_unavailable(monkeypatch):
    conftest = _load_root_conftest()
    module_name = "complaint_optional_spec_less_proxy"
    monkeypatch.setitem(sys.modules, module_name, ModuleType(module_name))

    assert conftest._optional_upstream_module_available(module_name) is False


def test_real_absent_parent_does_not_abort_optional_file_collection(monkeypatch, tmp_path):
    conftest = _load_root_conftest()
    optional_module = "complaint_absent_optional_parent.child"
    monkeypatch.setattr(conftest, "_OPTIONAL_UPSTREAM_MODULES", (optional_module,))

    assert conftest.pytest_ignore_collect(tmp_path / "test_email_agentic_search.py") is True
    assert conftest.pytest_ignore_collect(tmp_path / "test_tui_intake_baseline.py") is None


def test_real_present_optional_module_remains_collectable(monkeypatch, tmp_path):
    conftest = _load_root_conftest()
    package = tmp_path / "complaint_optional_fixture"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "present.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(conftest, "_OPTIONAL_UPSTREAM_MODULES", ("complaint_optional_fixture.present",))
    try:
        assert conftest.pytest_ignore_collect(tmp_path / "test_email_agentic_search.py") is None
    finally:
        sys.modules.pop("complaint_optional_fixture", None)
