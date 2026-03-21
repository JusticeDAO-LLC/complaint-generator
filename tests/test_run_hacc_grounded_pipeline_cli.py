import importlib.util
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_auto_network


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "run_hacc_grounded_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_hacc_grounded_pipeline", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_supports_grounded_pipeline_options():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args(
        [
            "--hacc-preset",
            "core_hacc_policies",
            "--top-k",
            "2",
            "--use-hacc-vector-search",
            "--synthesize-complaint",
            "--json",
        ]
    )

    assert args.hacc_preset == "core_hacc_policies"
    assert args.top_k == 2
    assert args.use_hacc_vector_search is True
    assert args.synthesize_complaint is True
    assert args.json is True


def test_default_grounding_request_uses_first_query_spec(monkeypatch):
    cli = _load_cli_module()
    monkeypatch.setattr(
        cli,
        "_load_query_specs",
        lambda preset: [{"query": "grievance hearing appeal", "type": "housing_discrimination"}],
    )

    request = cli._default_grounding_request("core_hacc_policies")

    assert request == {
        "query": "grievance hearing appeal",
        "claim_type": "housing_discrimination",
    }
