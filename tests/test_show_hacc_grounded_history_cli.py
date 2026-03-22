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

    args = parser.parse_args(
        ["--grounded-root", "output/hacc_grounded", "--output-dir", "previous", "--list-runs", "--json"]
    )

    assert args.grounded_root == "output/hacc_grounded"
    assert args.output_dir == "previous"
    assert args.list_runs is True
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


def test_resolve_grounded_run_dir_supports_previous_alias(tmp_path):
    cli = _load_cli_module()
    oldest = tmp_path / "20260322_090000"
    older = tmp_path / "20260322_100000"
    newer = tmp_path / "20260322_120000"
    oldest.mkdir()
    older.mkdir()
    newer.mkdir()
    oldest.touch()
    older.touch()
    newer.touch()

    resolved = cli.resolve_grounded_run_dir(output_dir="previous", grounded_root=str(tmp_path))

    assert resolved == older.resolve()


def test_resolve_grounded_run_dir_supports_last_successful_alias(tmp_path):
    cli = _load_cli_module()
    older = tmp_path / "20260322_100000"
    newer = tmp_path / "20260322_120000"
    older.mkdir()
    newer.mkdir()
    older.touch()
    newer.touch()
    (older / "refreshed_grounding_state.json").write_text(
        json.dumps({"status": "chronology_supported"}),
        encoding="utf-8",
    )

    resolved = cli.resolve_grounded_run_dir(output_dir="last-successful", grounded_root=str(tmp_path))

    assert resolved == older.resolve()


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


def test_list_grounded_runs_summarizes_available_run_dirs(tmp_path):
    cli = _load_cli_module()
    older = tmp_path / "20260322_100000"
    newer = tmp_path / "20260322_120000"
    older.mkdir()
    newer.mkdir()
    (older / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "pre_grounded_follow_up",
                "effective_next_action": {"action": "upload_local_repository_evidence"},
                "grounded_follow_up_answer_count": 0,
                "has_refreshed_grounding_state": False,
                "has_persisted_completed_grounded_worksheet": False,
            }
        ),
        encoding="utf-8",
    )
    (newer / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "post_grounded_follow_up",
                "effective_next_action": {"action": "continue_drafting"},
                "grounded_follow_up_answer_count": 3,
                "has_refreshed_grounding_state": True,
                "has_persisted_completed_grounded_worksheet": True,
            }
        ),
        encoding="utf-8",
    )

    runs = cli._list_grounded_runs(tmp_path)

    assert runs[0]["run_name"] == "20260322_120000"
    assert runs[0]["workflow_stage"] == "post_grounded_follow_up"
    assert runs[0]["next_action"] == "continue_drafting"
    assert runs[0]["has_persisted_completed_grounded_worksheet"] is True
    assert runs[1]["run_name"] == "20260322_100000"


def test_resolve_grounded_run_aliases_summarizes_current_targets(tmp_path):
    cli = _load_cli_module()
    older = tmp_path / "20260322_100000"
    newer = tmp_path / "20260322_120000"
    older.mkdir()
    newer.mkdir()
    (older / "refreshed_grounding_state.json").write_text(
        json.dumps({"status": "chronology_supported"}),
        encoding="utf-8",
    )

    aliases = cli._resolve_grounded_run_aliases(tmp_path)

    assert aliases["latest"] == "20260322_120000"
    assert aliases["previous"] == "20260322_100000"
    assert aliases["last-successful"] == "20260322_100000"


def test_main_list_runs_prints_available_runs(tmp_path, capsys):
    cli = _load_cli_module()
    grounded_run = tmp_path / "20260322_120000"
    grounded_run.mkdir()
    (grounded_run / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "post_grounded_follow_up",
                "effective_next_action": {"action": "continue_drafting"},
                "grounded_follow_up_answer_count": 3,
                "has_refreshed_grounding_state": True,
                "has_persisted_completed_grounded_worksheet": True,
            }
        ),
        encoding="utf-8",
    )

    result = cli.main(["--grounded-root", str(tmp_path), "--list-runs"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Available runs: 1" in captured.out
    assert "Alias targets:" in captured.out
    assert "Best candidate to resume:" in captured.out
    assert "Inspect command:" in captured.out
    assert "Synthesis command:" in captured.out
    assert "20260322_120000" in captured.out
    assert "continue_drafting" in captured.out


def test_main_list_runs_json_includes_recommended_aliases(tmp_path, capsys):
    cli = _load_cli_module()
    older = tmp_path / "20260322_100000"
    newer = tmp_path / "20260322_120000"
    older.mkdir()
    newer.mkdir()
    (older / "refreshed_grounding_state.json").write_text(
        json.dumps({"status": "chronology_supported"}),
        encoding="utf-8",
    )
    (older / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "post_grounded_follow_up",
                "effective_next_action": {"action": "continue_drafting"},
                "grounded_follow_up_answer_count": 2,
                "has_refreshed_grounding_state": True,
                "has_persisted_completed_grounded_worksheet": True,
            }
        ),
        encoding="utf-8",
    )
    (newer / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "pre_grounded_follow_up",
                "effective_next_action": {"action": "upload_local_repository_evidence"},
                "grounded_follow_up_answer_count": 0,
                "has_refreshed_grounding_state": False,
                "has_persisted_completed_grounded_worksheet": False,
            }
        ),
        encoding="utf-8",
    )

    result = cli.main(["--grounded-root", str(tmp_path), "--list-runs", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert payload["recommended_aliases"]["latest"] == "20260322_120000"
    assert payload["recommended_aliases"]["previous"] == "20260322_100000"
    assert payload["recommended_aliases"]["last-successful"] == "20260322_100000"
    assert payload["best_resume_candidate"]["run_name"] == "20260322_100000"
    assert "completed grounded worksheet" in payload["best_resume_candidate"]["reason"]
    assert payload["best_resume_candidate"]["resume_command_kind"] == "synthesize"
    assert payload["best_resume_candidate"]["inspect_command"].endswith(
        str((tmp_path / "20260322_100000").resolve())
    )
    assert payload["best_resume_candidate"]["resume_command"].endswith(
        str((tmp_path / "20260322_100000").resolve())
    )


def test_best_resume_candidate_prefers_completed_and_refreshed_runs():
    cli = _load_cli_module()

    candidate = cli._best_resume_candidate(
        [
            {
                "run_name": "20260322_120000",
                "run_dir": "/tmp/20260322_120000",
                "workflow_stage": "pre_grounded_follow_up",
                "has_refreshed_grounding_state": False,
                "has_persisted_completed_grounded_worksheet": False,
                "grounded_follow_up_answer_count": 0,
            },
            {
                "run_name": "20260322_100000",
                "run_dir": "/tmp/20260322_100000",
                "workflow_stage": "post_grounded_follow_up",
                "has_refreshed_grounding_state": True,
                "has_persisted_completed_grounded_worksheet": True,
                "grounded_follow_up_answer_count": 3,
            },
        ]
    )

    assert candidate["run_name"] == "20260322_100000"
    assert "refreshed grounding state" in candidate["reason"]
    assert candidate["resume_command_kind"] == "synthesize"
    assert candidate["inspect_command"] == "python scripts/show_hacc_grounded_history.py --output-dir /tmp/20260322_100000"
    assert candidate["resume_command"] == "python scripts/synthesize_hacc_complaint.py --grounded-run-dir /tmp/20260322_100000"


def test_best_resume_candidate_falls_back_to_inspection_for_pre_follow_up_runs():
    cli = _load_cli_module()

    candidate = cli._best_resume_candidate(
        [
            {
                "run_name": "20260322_120000",
                "run_dir": "/tmp/20260322_120000",
                "workflow_stage": "pre_grounded_follow_up",
                "has_refreshed_grounding_state": False,
                "has_persisted_completed_grounded_worksheet": False,
                "grounded_follow_up_answer_count": 0,
            }
        ]
    )

    assert candidate["run_name"] == "20260322_120000"
    assert candidate["resume_command_kind"] == "rerun"
    assert candidate["inspect_command"] == "python scripts/show_hacc_grounded_history.py --output-dir /tmp/20260322_120000"
    assert candidate["resume_command"] == "python scripts/run_hacc_grounded_pipeline.py --output-dir /tmp/20260322_120000"


def test_main_list_runs_prints_rerun_command_for_pre_follow_up_candidate(tmp_path, capsys):
    cli = _load_cli_module()
    grounded_run = tmp_path / "20260322_120000"
    grounded_run.mkdir()
    (grounded_run / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "pre_grounded_follow_up",
                "effective_next_action": {"action": "upload_local_repository_evidence"},
                "grounded_follow_up_answer_count": 0,
                "has_refreshed_grounding_state": False,
                "has_persisted_completed_grounded_worksheet": False,
            }
        ),
        encoding="utf-8",
    )

    result = cli.main(["--grounded-root", str(tmp_path), "--list-runs"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Grounded rerun command:" in captured.out
    assert "python scripts/run_hacc_grounded_pipeline.py --output-dir" in captured.out
