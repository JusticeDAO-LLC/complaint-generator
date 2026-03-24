from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_email_search_plan.py"
    spec = importlib.util.spec_from_file_location("generate_email_search_plan_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generate_email_search_plan_cli_outputs_json(monkeypatch, capsys) -> None:
    module = _load_script_module()
    monkeypatch.setattr(
        module,
        "build_parser",
        lambda: module.argparse.ArgumentParser(),
    )

    parser = module.argparse.ArgumentParser()
    parser.add_argument("--complaint-query", required=True)
    parser.add_argument("--complaint-keyword", action="append", default=[])
    parser.add_argument("--complaint-keyword-file", action="append", default=[])
    parser.add_argument("--address", action="append", default=[])
    parser.add_argument("--date-after", default=None)
    parser.add_argument("--date-before", default=None)
    parser.add_argument("--max-subject-terms", type=int, default=6)
    monkeypatch.setattr(module, "build_parser", lambda: parser)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "generate_email_search_plan.py",
            "--complaint-query",
            "termination hearing retaliation",
            "--address",
            "tenant@example.com",
        ],
    )

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["address_filters"] == ["tenant@example.com"]
    assert payload["recommended_subject_terms"]
