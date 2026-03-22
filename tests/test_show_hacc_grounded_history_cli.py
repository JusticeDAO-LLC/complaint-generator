import importlib.util
import json
from pathlib import Path


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "show_hacc_grounded_history.py"
    spec = importlib.util.spec_from_file_location("show_hacc_grounded_history", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_supports_output_root_and_json():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args(["--grounded-root", "output/hacc_grounded", "--json"])

    assert args.grounded_root == "output/hacc_grounded"
    assert args.json is True


def test_resolve_grounded_run_dir_prefers_latest_child(tmp_path):
    cli = _load_cli_module()
    older = tmp_path / "20260322_100000"
    newer = tmp_path / "20260322_120000"
    older.mkdir()
    newer.mkdir()
    older.touch()
    newer.touch()

    resolved = cli.resolve_grounded_run_dir(output_dir=None, grounded_root=str(tmp_path))

    assert resolved == newer.resolve()


def test_main_prints_inspection_for_latest_run(tmp_path, capsys):
    cli = _load_cli_module()
    grounded_run = tmp_path / "20260322_120000"
    grounded_run.mkdir()
    (grounded_run / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "post_grounded_follow_up",
                "effective_next_action": {
                    "phase_name": "document_generation",
                    "action": "continue_drafting",
                },
            }
        ),
        encoding="utf-8",
    )
    (grounded_run / "grounded_workflow_history.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-03-22T00:00:00+00:00",
                    "workflow_stage": "pre_grounded_follow_up",
                    "effective_next_action": {"action": "upload_local_repository_evidence"},
                }
            ]
        ),
        encoding="utf-8",
    )

    result = cli.main(["--grounded-root", str(tmp_path)])
    captured = capsys.readouterr()

    assert result == 0
    assert "Workflow stage: post_grounded_follow_up" in captured.out
    assert "continue_drafting" in captured.out


def test_main_prints_json_for_explicit_output_dir(tmp_path, capsys):
    cli = _load_cli_module()
    grounded_run = tmp_path / "run_a"
    grounded_run.mkdir()
    (grounded_run / "grounded_workflow_status.json").write_text(
        json.dumps({"workflow_stage": "pre_grounded_follow_up"}),
        encoding="utf-8",
    )
    (grounded_run / "grounded_workflow_history.json").write_text(json.dumps([]), encoding="utf-8")

    result = cli.main(["--output-dir", str(grounded_run), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert payload["output_dir"] == str(grounded_run.resolve())
    assert payload["workflow_status"]["workflow_stage"] == "pre_grounded_follow_up"
