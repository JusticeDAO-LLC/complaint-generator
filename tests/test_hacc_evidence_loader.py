import inspect
import sys

import adversarial_harness.hacc_evidence as hacc_evidence_module


def test_load_hacc_engine_loads_engine_module_from_repo_root(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    engine_dir = repo_root / "hacc_research"
    engine_dir.mkdir(parents=True)
    (engine_dir / "engine.py").write_text(
        "class HACCResearchEngine:\n    SOURCE = 'file-loader'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(hacc_evidence_module, "_repo_root", lambda: repo_root)
    monkeypatch.delitem(sys.modules, "hacc_research.engine", raising=False)

    engine_cls = hacc_evidence_module._load_hacc_engine()

    assert engine_cls.SOURCE == "file-loader"
    assert str(repo_root) not in sys.path


def test_load_hacc_engine_source_uses_file_based_loader():
    source = inspect.getsource(hacc_evidence_module._load_hacc_engine)

    assert "spec_from_file_location" in source
    assert "module_from_spec" in source
    assert 'import_module("hacc_research")' not in source
