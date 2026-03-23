import importlib.util
from pathlib import Path


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "run_package_install_smoke.py"
    spec = importlib.util.spec_from_file_location("run_package_install_smoke", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_supports_json_flag():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args(["--json"])

    assert args.json is True


def test_installed_script_path_uses_python_bin_directory():
    cli = _load_cli_module()

    script_path = cli.installed_script_path("complaint-workspace", "/tmp/venv/bin/python")

    assert script_path == Path("/tmp/venv/bin/complaint-workspace")


def test_extract_json_payload_ignores_non_json_preamble():
    cli = _load_cli_module()

    payload = cli.extract_json_payload("notice\n{\"ok\": true}\n")

    assert payload == {"ok": True}