import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_complaint_supervisor_job.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("run_complaint_supervisor_job", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cli_source_does_not_build_a_control_plane_request():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "SupervisorControlService" not in text
    assert "OperationRequest" not in text
    assert "complaint_workspace_api" not in text


def test_cli_prints_degraded_job_without_loading_the_control_service(tmp_path, capsys):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"prompt": "Repair the count."}), encoding="utf-8")
    probe = {"available": False, "probed": False, "error": "probe failed", "operations": []}
    cli = _load_cli()
    with patch("integrations.ipfs_accelerate.supervisor.probe_agent_supervisor", return_value=probe):
        with patch("integrations.ipfs_accelerate.supervisor.import_module_optional") as importer:
            code = cli.main(["--operation", "draft_repair", "--payload", str(payload)])
    captured = json.loads(capsys.readouterr().out)
    assert code == 2
    assert captured["status"] == "unavailable"
    assert captured["operation"] == "draft_repair"
    assert importer.call_count == 0


def test_cli_returns_zero_when_the_local_job_is_available(tmp_path, capsys):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"prompt": "The employer terminated the worker."}), encoding="utf-8")
    probe = {"available": True, "probed": True, "error": "", "operations": ["capability"]}
    cli = _load_cli()
    with patch("integrations.ipfs_accelerate.supervisor.probe_agent_supervisor", return_value=probe):
        with patch(
            "integrations.ipfs_datasets.llm.generate_text_with_metadata",
            return_value={"status": "available", "text": "The employer terminated the worker."},
        ):
            with patch(
                "integrations.ipfs_datasets.logic.text_to_fol",
                return_value={"metadata": {"logic_path": "logic.fol"}},
            ):
                code = cli.main(["--operation", "draft_repair", "--payload", str(payload)])
    captured = json.loads(capsys.readouterr().out)
    assert code == 0
    assert captured["status"] == "available"
    assert captured["result"]["logic_path"] == "logic.fol"
