import importlib.util
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_auto_network


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "run_hacc_unit_regression.py"
    spec = importlib.util.spec_from_file_location("run_hacc_unit_regression", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_supports_list_and_python_override():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args(["--list", "--python", ".venv/bin/python"])

    assert args.list is True
    assert args.python == ".venv/bin/python"


def test_resolve_test_targets_returns_hacc_unit_slice():
    cli = _load_cli_module()

    targets = cli.resolve_test_targets()

    assert targets == cli.HACC_UNIT_TESTS


def test_build_pytest_command_places_passthrough_args_before_targets():
    cli = _load_cli_module()

    command = cli.build_pytest_command(
        pytest_args=["-k", "hacc"],
        python_executable=".venv/bin/python",
    )

    assert command[:6] == [
        ".venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "-k",
        "hacc",
    ]
    assert command[6:] == cli.HACC_UNIT_TESTS


def test_main_list_prints_full_hacc_unit_slice(capsys):
    cli = _load_cli_module()

    result = cli.main(["--list", "--python", ".venv/bin/python"])
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out.startswith(".venv/bin/python -m pytest -q ")
    assert "tests/test_hacc_grounded_history_docs.py" in captured.out
    assert "tests/test_show_hacc_grounded_history_cli.py" in captured.out
    assert "tests/test_run_hacc_unit_regression_cli.py" in captured.out
