import inspect
import sys
from types import SimpleNamespace

import adversarial_harness.hacc_evidence as hacc_evidence_module


def test_load_hacc_engine_loads_engine_module_from_repo_root(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    engine_dir = repo_root / "hacc_research"
    engine_dir.mkdir(parents=True)
    (engine_dir / "engine.py").write_text(
        "class HACCResearchEngine:\n"
        "    SOURCE = 'direct-file-load'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: repo_root)

    engine_cls = hacc_evidence_module._load_hacc_engine()

    assert engine_cls.__name__ == "HACCResearchEngine"
    assert engine_cls.SOURCE == "direct-file-load"
    assert captured["module_name"] == "hacc_research"
    assert str(repo_root) in hacc_evidence_module.sys.path
    assert engine_cls is fake_engine


def test_load_hacc_engine_source_avoids_spec_loader_regression():
    source = inspect.getsource(hacc_evidence_module._load_hacc_engine)

    assert 'importlib.import_module("hacc_research")' in source
    assert "spec_from_file_location" not in source
    assert "module_from_spec" not in source
