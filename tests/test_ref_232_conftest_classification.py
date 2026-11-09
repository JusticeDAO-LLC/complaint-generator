import builtins
import importlib.util
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _load_root_conftest():
    conftest_path = Path(__file__).with_name("conftest.py")
    spec = importlib.util.spec_from_file_location("ref_232_root_conftest", conftest_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classify_test_file_detects_gates_and_ignores_reserved_urls(tmp_path):
    root_conftest = _load_root_conftest()
    test_file = tmp_path / "test_gated.py"
    test_file.write_text(
        'MODEL = "AutoModelForCausalLM"\n'
        'DOCS = "https://example.com/reference"\n'
        'DEVICE = "cuda"\n',
        encoding="utf-8",
    )

    assert root_conftest._classify_test_file(str(test_file)) == (True, False, True)


def test_classify_test_file_warns_and_fails_closed_on_read_error(monkeypatch):
    root_conftest = _load_root_conftest()
    test_path = "/checkout/tests/test_external_service.py"
    original_open = builtins.open

    def controlled_open(path, *args, **kwargs):
        if path == test_path:
            raise PermissionError("access denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", controlled_open)

    with pytest.warns(
        pytest.PytestCollectionWarning,
        match=r"Could not read test file.*requiring LLM, network, and heavy.*access denied",
    ) as captured:
        classification = root_conftest._classify_test_file(test_path)

    assert classification == (True, True, True)
    assert test_path in str(captured[0].message)


def test_classify_test_file_does_not_swallow_classifier_defects(
    monkeypatch, tmp_path
):
    root_conftest = _load_root_conftest()
    test_file = tmp_path / "test_classifier_failure.py"
    test_file.write_text("def test_example(): pass\n", encoding="utf-8")

    def fail_to_strip_urls(_text):
        raise RuntimeError("classifier defect")

    monkeypatch.setattr(
        root_conftest, "_strip_reserved_example_urls", fail_to_strip_urls
    )

    with pytest.raises(RuntimeError, match="classifier defect"):
        root_conftest._classify_test_file(str(test_file))
