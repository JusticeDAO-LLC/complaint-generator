import importlib.util
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_auto_network


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "run_hacc_grounding_regression.py"
    spec = importlib.util.spec_from_file_location("run_hacc_grounding_regression", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_supports_list_skip_smoke_and_python_override():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args(["--list", "--skip-smoke", "--python", ".venv/bin/python"])

    assert args.list is True
    assert args.skip_smoke is True
    assert args.python == ".venv/bin/python"


def test_build_hacc_seed_test_command_includes_loader_regression():
    cli = _load_cli_module()

    command = cli.build_hacc_seed_test_command(".venv/bin/python")

    assert command[:4] == [".venv/bin/python", "-m", "pytest", "-q"]
    assert str(cli.WORKSPACE_ROOT / "tests" / "test_hacc_evidence_seed_generation.py") in command
    assert str(cli.PROJECT_ROOT / "tests" / "test_hacc_evidence_loader.py") in command


def test_build_harness_test_command_targets_adversarial_harness_suite():
    cli = _load_cli_module()

    command = cli.build_harness_test_command(".venv/bin/python")

    assert command == [
        ".venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "complaint-generator/tests/test_adversarial_harness.py",
    ]


def test_build_smoke_command_uses_output_dir_and_core_preset():
    cli = _load_cli_module()

    command = cli.build_smoke_command(".venv/bin/python", "/tmp/hacc-smoke")

    assert command[0] == ".venv/bin/python"
    assert str(cli.WORKSPACE_ROOT / "hacc_adversarial_runner.py") in command
    assert "--hacc-preset" in command
    assert "core_hacc_policies" in command
    assert command[-1] == "/tmp/hacc-smoke"
