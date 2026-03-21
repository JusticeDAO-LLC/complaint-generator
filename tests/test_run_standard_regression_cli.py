import importlib.util
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_auto_network


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "run_standard_regression.py"
    spec = importlib.util.spec_from_file_location("run_standard_regression", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_supports_slice_and_list():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args(["--slice", "full", "--list"])

    assert args.slice == "full"
    assert args.list is True


def test_resolve_test_targets_returns_full_slice_by_default():
    cli = _load_cli_module()

    targets = cli.resolve_test_targets()

    assert targets == cli.REGRESSION_SLICES["full"]


def test_resolve_test_targets_returns_full_slice():
    cli = _load_cli_module()

    targets = cli.resolve_test_targets("full")

    assert targets == cli.REGRESSION_SLICES["full"]
    assert "tests/test_claim_support_review_template.py" in targets
    assert "tests/test_document_pipeline.py" in targets
    assert "tests/test_formal_document_pipeline.py" in targets
    assert "tests/test_claim_support_review_playwright_smoke.py" in targets


def test_build_pytest_command_places_passthrough_args_before_targets():
    cli = _load_cli_module()

    command = cli.build_pytest_command(
        slice_name="review",
        pytest_args=["-k", "claim_support"],
        python_executable=".venv/bin/python",
    )

    assert command[:6] == [
        ".venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "-k",
        "claim_support",
    ]
    assert command[6:] == cli.REGRESSION_SLICES["review"]
    assert "tests/test_claim_support_review_template.py" in command[6:]
    assert "tests/test_document_pipeline.py" in command[6:]
    assert "tests/test_formal_document_pipeline.py" in command[6:]


def test_create_parser_defaults_to_full_slice():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args([])

    assert args.slice == "full"
