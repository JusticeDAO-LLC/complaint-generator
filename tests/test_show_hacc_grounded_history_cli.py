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
    (older / "run_summary.json").write_text(
        json.dumps(
            {
                "grounding_query": "older query",
                "claim_type": "housing_discrimination",
                "hacc_preset": "core_hacc_policies",
                "use_hacc_vector_search": False,
                "hacc_search_mode": "package",
            }
        ),
        encoding="utf-8",
    )
    (newer / "run_summary.json").write_text(
        json.dumps(
            {
                "grounding_query": "newer query",
                "claim_type": "housing_discrimination",
                "hacc_preset": "core_hacc_policies",
                "use_hacc_vector_search": True,
                "hacc_search_mode": "hybrid",
            }
        ),
        encoding="utf-8",
    )
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
                "persisted_completed_grounded_worksheet_path": str(newer / "completed_grounded_intake_follow_up_worksheet.json"),
                "recommended_commands": {
                    "inspect_command": f"python scripts/show_hacc_grounded_history.py --output-dir {newer.resolve()}",
                    "recommended_command": f"python scripts/synthesize_hacc_complaint.py --grounded-run-dir {newer.resolve()}",
                    "recommended_command_kind": "synthesize",
                    "rerun_command": f"python scripts/run_hacc_grounded_pipeline.py --output-dir {newer.resolve()}",
                    "synthesize_command": f"python scripts/synthesize_hacc_complaint.py --grounded-run-dir {newer.resolve()}",
                    "pipeline_resume_command": (
                        f"python scripts/run_hacc_grounded_pipeline.py --output-dir {newer.resolve()} "
                        f"--synthesize-complaint --completed-grounded-intake-worksheet {newer / 'completed_grounded_intake_follow_up_worksheet.json'}"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )

    runs = cli._list_grounded_runs(tmp_path)

    assert runs[0]["run_name"] == "20260322_120000"
    assert runs[0]["workflow_stage"] == "post_grounded_follow_up"
    assert runs[0]["next_action"] == "continue_drafting"
    assert runs[0]["has_persisted_completed_grounded_worksheet"] is True
    assert runs[0]["grounding_query"] == "newer query"
    assert runs[0]["use_hacc_vector_search"] is True
    assert runs[0]["completed_grounded_intake_worksheet_path"].endswith("completed_grounded_intake_follow_up_worksheet.json")
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
                "persisted_completed_grounded_worksheet_path": str(grounded_run / "completed_grounded_intake_follow_up_worksheet.json"),
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
    assert "Pipeline rerun command:" in captured.out
    assert "20260322_120000" in captured.out
    assert "continue_drafting" in captured.out


def test_main_list_runs_prints_alias_targets_and_stage_aware_commands(tmp_path, capsys):
    cli = _load_cli_module()
    older = tmp_path / "20260322_100000"
    newer = tmp_path / "20260322_120000"
    older.mkdir()
    newer.mkdir()
    (older / "run_summary.json").write_text(
        json.dumps(
            {
                "grounding_query": "older chronology query",
                "claim_type": "housing_discrimination",
                "hacc_preset": "core_hacc_policies",
                "use_hacc_vector_search": False,
                "hacc_search_mode": "package",
            }
        ),
        encoding="utf-8",
    )
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
                "persisted_completed_grounded_worksheet_path": str(older / "completed_grounded_intake_follow_up_worksheet.json"),
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

    result = cli.main(["--grounded-root", str(tmp_path), "--list-runs"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Alias targets: latest=20260322_120000, previous=20260322_100000, last-successful=20260322_100000" in captured.out
    assert "Best candidate to resume: 20260322_100000" in captured.out
    assert "Inspect command: python scripts/show_hacc_grounded_history.py --output-dir" in captured.out
    assert "Synthesis command: python scripts/synthesize_hacc_complaint.py --grounded-run-dir" in captured.out
    assert "Pipeline rerun command: python scripts/run_hacc_grounded_pipeline.py --output-dir" in captured.out
    assert "--query older chronology query" in captured.out
    assert "20260322_120000" in captured.out
    assert "20260322_100000" in captured.out


def test_main_list_runs_json_includes_recommended_aliases(tmp_path, capsys):
    cli = _load_cli_module()
    older = tmp_path / "20260322_100000"
    newer = tmp_path / "20260322_120000"
    older.mkdir()
    newer.mkdir()
    (older / "run_summary.json").write_text(
        json.dumps(
            {
                "grounding_query": "older chronology query",
                "claim_type": "housing_discrimination",
                "hacc_preset": "core_hacc_policies",
                "use_hacc_vector_search": False,
                "hacc_search_mode": "package",
            }
        ),
        encoding="utf-8",
    )
    (newer / "run_summary.json").write_text(
        json.dumps(
            {
                "grounding_query": "newer chronology query",
                "claim_type": "housing_discrimination",
                "hacc_preset": "core_hacc_policies",
                "use_hacc_vector_search": True,
                "hacc_search_mode": "hybrid",
            }
        ),
        encoding="utf-8",
    )
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
                "persisted_completed_grounded_worksheet_path": str(older / "completed_grounded_intake_follow_up_worksheet.json"),
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
    assert payload["best_resume_candidate"]["rerun_command"].startswith(
        "python scripts/run_hacc_grounded_pipeline.py --output-dir "
    )
    assert "--query older chronology query" in payload["best_resume_candidate"]["rerun_command"]
    assert payload["best_resume_candidate"]["synthesize_command"].startswith(
        "python scripts/synthesize_hacc_complaint.py --grounded-run-dir "
    )
    assert "--synthesize-complaint" in payload["best_resume_candidate"]["pipeline_resume_command"]
    assert "--completed-grounded-intake-worksheet" in payload["best_resume_candidate"]["pipeline_resume_command"]


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
                "completed_grounded_intake_worksheet_path": "/tmp/20260322_100000/completed_grounded_intake_follow_up_worksheet.json",
            },
        ]
    )

    assert candidate["run_name"] == "20260322_100000"
    assert "refreshed grounding state" in candidate["reason"]
    assert candidate["resume_command_kind"] == "synthesize"
    assert candidate["inspect_command"] == "python scripts/show_hacc_grounded_history.py --output-dir /tmp/20260322_100000"
    assert candidate["resume_command"] == "python scripts/synthesize_hacc_complaint.py --grounded-run-dir /tmp/20260322_100000"
    assert candidate["pipeline_resume_command"] == (
        "python scripts/run_hacc_grounded_pipeline.py "
        "--output-dir /tmp/20260322_100000 "
        "--synthesize-complaint "
        "--completed-grounded-intake-worksheet /tmp/20260322_100000/completed_grounded_intake_follow_up_worksheet.json"
    )


def test_best_resume_candidate_prefers_status_owned_recommended_commands():
    cli = _load_cli_module()

    candidate = cli._best_resume_candidate(
        [
            {
                "run_name": "20260322_100000",
                "run_dir": "/tmp/20260322_100000",
                "workflow_stage": "post_grounded_follow_up",
                "has_refreshed_grounding_state": True,
                "has_persisted_completed_grounded_worksheet": True,
                "grounded_follow_up_answer_count": 3,
                "recommended_commands": {
                    "inspect_command": "python scripts/show_hacc_grounded_history.py --output-dir /tmp/custom",
                    "recommended_command": "python scripts/synthesize_hacc_complaint.py --grounded-run-dir /tmp/custom",
                    "recommended_command_kind": "synthesize",
                    "rerun_command": "python scripts/run_hacc_grounded_pipeline.py --output-dir /tmp/custom",
                    "synthesize_command": "python scripts/synthesize_hacc_complaint.py --grounded-run-dir /tmp/custom",
                    "pipeline_resume_command": "python scripts/run_hacc_grounded_pipeline.py --output-dir /tmp/custom --synthesize-complaint",
                },
            }
        ]
    )

    assert candidate["inspect_command"] == "python scripts/show_hacc_grounded_history.py --output-dir /tmp/custom"
    assert candidate["resume_command"] == "python scripts/synthesize_hacc_complaint.py --grounded-run-dir /tmp/custom"
    assert candidate["pipeline_resume_command"] == "python scripts/run_hacc_grounded_pipeline.py --output-dir /tmp/custom --synthesize-complaint"


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
                "grounding_query": "termination notice chronology",
                "claim_type": "housing_discrimination",
                "hacc_preset": "core_hacc_policies",
                "use_hacc_vector_search": True,
                "hacc_search_mode": "hybrid",
            }
        ]
    )

    assert candidate["run_name"] == "20260322_120000"
    assert candidate["resume_command_kind"] == "rerun"
    assert candidate["inspect_command"] == "python scripts/show_hacc_grounded_history.py --output-dir /tmp/20260322_120000"
    assert candidate["resume_command"] == (
        "python scripts/run_hacc_grounded_pipeline.py "
        "--output-dir /tmp/20260322_120000 "
        "--query termination notice chronology "
        "--claim-type housing_discrimination "
        "--hacc-preset core_hacc_policies "
        "--hacc-search-mode hybrid "
        "--use-hacc-vector-search"
    )


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
