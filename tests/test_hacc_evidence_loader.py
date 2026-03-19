import importlib
import inspect
import sys
from types import SimpleNamespace

import adversarial_harness.hacc_evidence as hacc_evidence_module


def test_load_hacc_engine_loads_engine_module_from_repo_root(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    engine_dir = repo_root / "hacc_research"
    engine_dir.mkdir(parents=True)
    (engine_dir / "__init__.py").write_text("", encoding="utf-8")

    fake_engine = type("FakeEngine", (), {"SOURCE": "package-import"})
    fake_module = SimpleNamespace(HACCResearchEngine=fake_engine)
    captured = {}

    def fake_import_module(name):
        captured.setdefault("module_names", []).append(name)
        if name == "hacc_research":
            return fake_module
        raise AssertionError(f"Unexpected import target: {name}")

    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    monkeypatch.delitem(sys.modules, "hacc_research.engine", raising=False)
    monkeypatch.delitem(sys.modules, "hacc_research", raising=False)

    engine_cls = hacc_evidence_module._load_hacc_engine()

    assert captured["module_names"] == ["hacc_research"]
    assert str(repo_root) in sys.path
    assert engine_cls is fake_engine


def test_load_hacc_engine_source_uses_package_import():
    source = inspect.getsource(hacc_evidence_module._load_hacc_engine)

    assert 'importlib.import_module("hacc_research")' in source
    assert "spec_from_file_location" not in source
    assert "module_from_spec" not in source
