import inspect
import sys
from types import SimpleNamespace

import adversarial_harness.hacc_evidence as hacc_evidence_module


def test_load_hacc_engine_imports_hacc_research_package(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    engine_dir = repo_root / "hacc_research"
    engine_dir.mkdir(parents=True)
    (engine_dir / "engine.py").write_text("", encoding="utf-8")

    fake_engine = type("FakeEngine", (), {"SOURCE": "package-import"})
    fake_module = SimpleNamespace(HACCResearchEngine=fake_engine)
    captured = {}

    def fake_import_module(name):
        captured["module_name"] = name
        return fake_module

    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hacc_evidence_module.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(hacc_evidence_module.sys, "path", list(sys.path))

    engine_cls = hacc_evidence_module._load_hacc_engine()

    assert captured["module_name"] == "hacc_research"
    assert str(repo_root) in hacc_evidence_module.sys.path
    assert engine_cls is fake_engine


def test_load_hacc_engine_source_avoids_spec_loader_regression():
    source = inspect.getsource(hacc_evidence_module._load_hacc_engine)

    assert 'importlib.import_module("hacc_research")' in source
    assert "spec_from_file_location" not in source
    assert "module_from_spec" not in source
