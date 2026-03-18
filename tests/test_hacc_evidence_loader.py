import sys
from types import SimpleNamespace

import adversarial_harness.hacc_evidence as hacc_evidence_module


def test_load_hacc_engine_uses_package_import(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    engine_dir = repo_root / "hacc_research"
    engine_dir.mkdir(parents=True)
    (engine_dir / "engine.py").write_text("class HACCResearchEngine:\n    pass\n", encoding="utf-8")

    class FakeEngine:
        pass

    captured = {}

    def fake_import_module(name):
        captured["module_name"] = name
        return SimpleNamespace(HACCResearchEngine=FakeEngine)

    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hacc_evidence_module.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(hacc_evidence_module.sys, "path", list(sys.path))

    engine_cls = hacc_evidence_module._load_hacc_engine()

    assert captured["module_name"] == "hacc_research"
    assert str(repo_root) in hacc_evidence_module.sys.path
    assert engine_cls is FakeEngine