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
    assert str(cli.PROJECT_ROOT / "scripts" / "run_hacc_grounded_pipeline.py") in command
    assert "--hacc-preset" in command
    assert "core_hacc_policies" in command
    assert "--top-k" in command
    assert command[-1] == "/tmp/hacc-smoke"


def test_main_list_prints_grounding_regression_commands(capsys):
    cli = _load_cli_module()

    result = cli.main(["--list", "--python", ".venv/bin/python", "--smoke-output-dir", "/tmp/hacc-smoke"])
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line.strip()]

    assert result == 0
    assert len(lines) == 3
    assert lines[0].startswith(".venv/bin/python -m pytest -q ")
    assert "test_hacc_evidence_seed_generation.py" in lines[0]
    assert "test_hacc_evidence_loader.py" in lines[0]
    assert lines[1] == ".venv/bin/python -m pytest -q complaint-generator/tests/test_adversarial_harness.py"
    assert lines[2].startswith(".venv/bin/python ")
    assert "scripts/run_hacc_grounded_pipeline.py" in lines[2]
    assert "--output-dir /tmp/hacc-smoke" in lines[2]


def test_main_list_omits_smoke_command_when_skip_smoke_is_set(capsys):
    cli = _load_cli_module()

    result = cli.main(["--list", "--skip-smoke", "--python", ".venv/bin/python"])
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line.strip()]

    assert result == 0
    assert len(lines) == 2
    assert "test_hacc_evidence_seed_generation.py" in lines[0]
    assert lines[1] == ".venv/bin/python -m pytest -q complaint-generator/tests/test_adversarial_harness.py"
