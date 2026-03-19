import inspect
import sys
from types import SimpleNamespace

import adversarial_harness.hacc_evidence as hacc_evidence_module


def test_load_hacc_engine_loads_engine_module_from_file(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    engine_dir = repo_root / "hacc_research"
    engine_dir.mkdir(parents=True)
    (engine_dir / "engine.py").write_text("", encoding="utf-8")

    fake_engine = type("FakeEngine", (), {"SOURCE": "package-import"})
    fake_module = SimpleNamespace(HACCResearchEngine=fake_engine)
    captured = {}

    class FakeLoader:
        def exec_module(self, module):
            captured["executed_module"] = module
            module.HACCResearchEngine = fake_engine

    fake_spec = SimpleNamespace(loader=FakeLoader())

    def fake_spec_from_file_location(name, location):
        captured["module_name"] = name
        captured["location"] = location
        return fake_spec

    def fake_module_from_spec(spec):
        captured["spec"] = spec
        return fake_module

    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hacc_evidence_module.importlib.util, "spec_from_file_location", fake_spec_from_file_location)
    monkeypatch.setattr(hacc_evidence_module.importlib.util, "module_from_spec", fake_module_from_spec)
    monkeypatch.delitem(sys.modules, "hacc_research.engine", raising=False)

    engine_cls = hacc_evidence_module._load_hacc_engine()

    assert captured["module_name"] == "hacc_research.engine"
    assert captured["location"] == repo_root / "hacc_research" / "engine.py"
    assert captured["spec"] is fake_spec
    assert captured["executed_module"] is fake_module
    assert sys.modules["hacc_research.engine"] is fake_module
    assert engine_cls is fake_engine


def test_load_hacc_engine_source_uses_file_based_loader():
    source = inspect.getsource(hacc_evidence_module._load_hacc_engine)

    assert "spec_from_file_location" in source
    assert "module_from_spec" in source
    assert 'sys.modules[module_name] = module' in source
    assert 'importlib.import_module("hacc_research")' not in source
