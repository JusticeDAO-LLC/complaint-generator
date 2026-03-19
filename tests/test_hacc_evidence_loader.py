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