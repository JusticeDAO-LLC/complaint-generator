import importlib.util
import json
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
            "--completed-grounded-intake-worksheet",
            "grounded_answers.json",
            "--show-history",
            "--json",
        ]
    )

    assert args.hacc_preset == "core_hacc_policies"
    assert args.top_k == 2
    assert args.use_hacc_vector_search is True
    assert args.synthesize_complaint is True
    assert args.completed_grounded_intake_worksheet == "grounded_answers.json"
    assert args.show_history is True
    assert args.json is True


def test_load_grounded_workflow_inspection_reads_existing_status_and_history(tmp_path):
    cli = _load_cli_module()
    status_path = tmp_path / "grounded_workflow_status.json"
    history_path = tmp_path / "grounded_workflow_history.json"
    worksheet_path = tmp_path / "completed_grounded_intake_follow_up_worksheet.json"
    refreshed_path = tmp_path / "refreshed_grounding_state.json"
    grounded_answer_path = tmp_path / "grounded_follow_up_answer_summary.json"
    status_path.write_text(
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
    history_path.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-03-22T00:00:00+00:00",
                    "workflow_stage": "pre_grounded_follow_up",
                    "effective_next_action": {"action": "upload_local_repository_evidence"},
                },
                {
                    "timestamp": "2026-03-22T01:00:00+00:00",
                    "workflow_stage": "post_grounded_follow_up",
                    "effective_next_action": {"action": "continue_drafting"},
                },
            ]
        ),
        encoding="utf-8",
    )
    worksheet_path.write_text(
        json.dumps({"follow_up_items": [{"id": "grounded_01"}, {"id": "grounded_02"}]}),
        encoding="utf-8",
    )
    refreshed_path.write_text(
        json.dumps({"status": "chronology_supported"}),
        encoding="utf-8",
    )
    grounded_answer_path.write_text(
        json.dumps({"answered_item_count": 2}),
        encoding="utf-8",
    )

    inspection = cli._load_grounded_workflow_inspection(tmp_path)

    assert inspection["workflow_status"]["workflow_stage"] == "post_grounded_follow_up"
    assert inspection["workflow_history_count"] == 2
    assert inspection["recent_workflow_history"][-1]["effective_next_action"]["action"] == "continue_drafting"
    assert inspection["has_completed_grounded_intake_worksheet"] is True
    assert inspection["completed_grounded_intake_item_count"] == 2
    assert inspection["has_refreshed_grounding_state_artifact"] is True
    assert inspection["grounded_follow_up_answer_summary"]["answered_item_count"] == 2


def test_main_show_history_prints_existing_workflow_summary(tmp_path, capsys):
    cli = _load_cli_module()
    (tmp_path / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "post_grounded_follow_up",
                "effective_next_action": {
                    "phase_name": "document_generation",
                    "action": "continue_drafting",
                },
                "recommended_commands": {
                    "inspect_command": "python scripts/show_hacc_grounded_history.py --output-dir /tmp/example_run",
                    "recommended_command": (
                        "python scripts/synthesize_hacc_complaint.py --grounded-run-dir /tmp/example_run"
                    ),
                    "recommended_command_kind": "synthesize",
                    "pipeline_resume_command": (
                        "python scripts/run_hacc_grounded_pipeline.py --output-dir /tmp/example_run "
                        "--synthesize-complaint --completed-grounded-intake-worksheet "
                        "/tmp/example_run/completed_grounded_intake_follow_up_worksheet.json"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "grounded_workflow_history.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-03-22T00:00:00+00:00",
                    "workflow_stage": "pre_grounded_follow_up",
                    "effective_next_action": {"action": "upload_local_repository_evidence"},
                },
                {
                    "timestamp": "2026-03-22T01:00:00+00:00",
                    "workflow_stage": "post_grounded_follow_up",
                    "effective_next_action": {"action": "continue_drafting"},
                },
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "completed_grounded_intake_follow_up_worksheet.json").write_text(
        json.dumps({"follow_up_items": [{"id": "grounded_01"}, {"id": "grounded_02"}]}),
        encoding="utf-8",
    )
    (tmp_path / "refreshed_grounding_state.json").write_text(
        json.dumps({"status": "chronology_supported"}),
        encoding="utf-8",
    )
    (tmp_path / "grounded_follow_up_answer_summary.json").write_text(
        json.dumps({"answered_item_count": 2}),
        encoding="utf-8",
    )

    result = cli.main(["--output-dir", str(tmp_path), "--show-history"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Workflow stage: post_grounded_follow_up" in captured.out
    assert "Recorded transitions: 2" in captured.out
    assert "Completed grounded worksheet items: 2" in captured.out
    assert "Refreshed grounding status: chronology_supported" in captured.out
    assert "Grounded follow-up answers: 2" in captured.out
    assert "Inspect:" in captured.out
    assert "Recommended synthesis:" in captured.out
    assert "Pipeline resume:" in captured.out
    assert "continue_drafting" in captured.out


def test_main_show_history_json_prints_existing_workflow_summary(tmp_path, capsys):
    cli = _load_cli_module()
    (tmp_path / "grounded_workflow_status.json").write_text(
        json.dumps(
            {
                "workflow_stage": "post_grounded_follow_up",
                "effective_next_action": {
                    "phase_name": "document_generation",
                    "action": "continue_drafting",
                },
                "recommended_commands": {
                    "inspect_command": "python scripts/show_hacc_grounded_history.py --output-dir /tmp/example_run",
                    "recommended_command": (
                        "python scripts/synthesize_hacc_complaint.py --grounded-run-dir /tmp/example_run"
                    ),
                    "recommended_command_kind": "synthesize",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "grounded_workflow_history.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-03-22T00:00:00+00:00",
                    "workflow_stage": "pre_grounded_follow_up",
                    "effective_next_action": {"action": "upload_local_repository_evidence"},
                },
                {
                    "timestamp": "2026-03-22T01:00:00+00:00",
                    "workflow_stage": "post_grounded_follow_up",
                    "effective_next_action": {"action": "continue_drafting"},
                },
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "completed_grounded_intake_follow_up_worksheet.json").write_text(
        json.dumps({"follow_up_items": [{"id": "grounded_01"}, {"id": "grounded_02"}]}),
        encoding="utf-8",
    )
    (tmp_path / "refreshed_grounding_state.json").write_text(
        json.dumps({"status": "chronology_supported"}),
        encoding="utf-8",
    )
    (tmp_path / "grounded_follow_up_answer_summary.json").write_text(
        json.dumps({"answered_item_count": 2}),
        encoding="utf-8",
    )

    result = cli.main(["--output-dir", str(tmp_path), "--show-history", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert payload["workflow_status"]["workflow_stage"] == "post_grounded_follow_up"
    assert payload["workflow_history_count"] == 2
    assert payload["completed_grounded_intake_item_count"] == 2
    assert payload["refreshed_grounding_state"]["status"] == "chronology_supported"
    assert payload["grounded_follow_up_answer_summary"]["answered_item_count"] == 2
    assert payload["workflow_status"]["recommended_commands"]["recommended_command_kind"] == "synthesize"
    assert payload["recent_workflow_history"][-1]["effective_next_action"]["action"] == "continue_drafting"


def test_main_prints_recommended_commands_for_fresh_grounded_run(tmp_path, monkeypatch, capsys):
    cli = _load_cli_module()

    class FakeEngine:
        def __init__(self, repo_root):
            self.repo_root = repo_root

        def research(self, query, **kwargs):
            return {
                "status": "success",
                "local_search_summary": {"status": "success"},
                "research_grounding_summary": {},
                "seeded_discovery_plan": {},
                "research_action_queue": [],
                "recommended_next_action": {
                    "phase_name": "evidence_upload",
                    "action": "upload_local_repository_evidence",
                },
            }

        def build_grounding_bundle(self, query, **kwargs):
            return {
                "status": "success",
                "search_summary": {"status": "success"},
                "synthetic_prompts": {},
                "anchor_passages": [],
                "upload_candidates": [],
                "mediator_evidence_packets": [],
                "claim_support_temporal_handoff": {},
                "document_generation_handoff": {},
                "drafting_readiness": {},
                "graph_completeness_signals": {},
            }

        def simulate_evidence_upload(self, query, **kwargs):
            return {"status": "success", "upload_count": 1, "search_summary": {"status": "success"}}

    monkeypatch.setattr(cli, "_load_hacc_engine", lambda: FakeEngine)
    monkeypatch.setattr(
        cli,
        "_run_adversarial_report",
        lambda **kwargs: {"status": "success", "search_summary": {"status": "success"}},
    )
    monkeypatch.setattr(cli, "_run_complaint_synthesis", lambda **kwargs: {})

    result = cli.main(
        [
            "--output-dir",
            str(tmp_path),
            "--query",
            "termination notice chronology",
            "--claim-type",
            "housing_discrimination",
            "--hacc-preset",
            "core_hacc_policies",
            "--hacc-search-mode",
            "package",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert "Output directory:" in captured.out
    assert "Inspect command:" in captured.out
    assert "Recommended rerun:" in captured.out
    assert "python scripts/run_hacc_grounded_pipeline.py --output-dir" in captured.out


def test_main_prints_recommended_commands_for_synthesis_ready_grounded_run(tmp_path, monkeypatch, capsys):
    cli = _load_cli_module()

    class FakeEngine:
        def __init__(self, repo_root):
            self.repo_root = repo_root

        def research(self, query, **kwargs):
            return {
                "status": "success",
                "local_search_summary": {"status": "success"},
                "research_grounding_summary": {},
                "seeded_discovery_plan": {},
                "research_action_queue": [],
                "recommended_next_action": {
                    "phase_name": "document_generation",
                    "action": "continue_drafting",
                },
            }

        def build_grounding_bundle(self, query, **kwargs):
            return {
                "status": "success",
                "search_summary": {"status": "success"},
                "synthetic_prompts": {},
                "anchor_passages": [],
                "upload_candidates": [],
                "mediator_evidence_packets": [],
                "claim_support_temporal_handoff": {},
                "document_generation_handoff": {},
                "drafting_readiness": {},
                "graph_completeness_signals": {},
            }

        def simulate_evidence_upload(self, query, **kwargs):
            return {"status": "success", "upload_count": 1, "search_summary": {"status": "success"}}

    def fake_run_complaint_synthesis(**kwargs):
        output_dir = tmp_path / "synthesized_complaint"
        output_dir.mkdir(parents=True, exist_ok=True)
        draft_path = output_dir / "draft_complaint_package.json"
        draft_path.write_text(
            json.dumps(
                {
                    "refreshed_grounding_state": {"status": "chronology_supported"},
                    "grounded_follow_up_answer_summary": {"answered_item_count": 1},
                }
            ),
            encoding="utf-8",
        )
        return {
            "output_dir": str(output_dir),
            "draft_complaint_package_json": str(draft_path),
            "draft_complaint_package_md": str(output_dir / "draft_complaint_package.md"),
            "intake_follow_up_worksheet_json": str(output_dir / "intake_follow_up_worksheet.json"),
            "intake_follow_up_worksheet_md": str(output_dir / "intake_follow_up_worksheet.md"),
        }

    completed_grounded_path = tmp_path / "grounded_answers.json"
    completed_grounded_path.write_text(
        json.dumps({"follow_up_items": [{"id": "grounded_priority_01", "answer": "Answered"}]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_load_hacc_engine", lambda: FakeEngine)
    monkeypatch.setattr(
        cli,
        "_run_adversarial_report",
        lambda **kwargs: {"status": "success", "search_summary": {"status": "success"}},
    )
    monkeypatch.setattr(cli, "_run_complaint_synthesis", fake_run_complaint_synthesis)

    result = cli.main(
        [
            "--output-dir",
            str(tmp_path),
            "--query",
            "termination notice chronology",
            "--claim-type",
            "housing_discrimination",
            "--hacc-preset",
            "core_hacc_policies",
            "--hacc-search-mode",
            "package",
            "--synthesize-complaint",
            "--completed-grounded-intake-worksheet",
            str(completed_grounded_path),
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert "Inspect command:" in captured.out
    assert "Recommended synthesis:" in captured.out
    assert "Pipeline resume command:" in captured.out
    assert "python scripts/synthesize_hacc_complaint.py --grounded-run-dir" in captured.out


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


def test_run_hacc_grounded_pipeline_persists_grounding_handoff_artifacts(tmp_path, monkeypatch):
    cli = _load_cli_module()

    class FakeEngine:
        def __init__(self, repo_root):
            self.repo_root = repo_root

        def research(self, query, **kwargs):
            return {
                "status": "success",
                "local_search_summary": {"status": "success"},
                "research_grounding_summary": {
                    "upload_ready_candidate_count": 1,
                    "recommended_upload_paths": ["evidence/notice.pdf"],
                },
                "seeded_discovery_plan": {
                    "queries": ['site:hacc.example "termination notice chronology" policy notice hearing'],
                    "priority": "chronology_first",
                },
                "research_action_queue": [
                    {
                        "phase_name": "evidence_upload",
                        "action": "upload_local_repository_evidence",
                        "priority": 100,
                    }
                ],
                "recommended_next_action": {
                    "phase_name": "evidence_upload",
                    "action": "upload_local_repository_evidence",
                    "priority": 100,
                },
            }

        def discover_seeded_commoncrawl(self, queries, **kwargs):
            return {
                "status": "success",
                "queries": list(queries),
                "candidates": {"sites": {"example.org": {"top": [{"url": "https://example.org/notice"}]}}},
            }

        def build_grounding_bundle(self, query, **kwargs):
            return {
                "status": "success",
                "search_summary": {"status": "success"},
                "synthetic_prompts": {
                    "production_evidence_intake_steps": ["Select the strongest dated notice first."],
                    "mediator_upload_checklist": ["Evaluate chronology anchors and named actors."],
                    "document_generation_checklist": ["Ground each claim element in uploaded artifacts."],
                    "evidence_upload_form_seed": {
                        "claim_type": kwargs.get("claim_type"),
                        "recommended_files": ["Notice of Termination"],
                    },
                },
                "anchor_passages": [{"text": "Notice dated March 4, 2024"}],
                "upload_candidates": [{"relative_path": "evidence/notice.pdf"}],
                "mediator_evidence_packets": [{"relative_path": "evidence/notice.pdf"}],
                "claim_support_temporal_handoff": {"timeline_anchor_count": 1},
                "document_generation_handoff": {"focus_sections": ["claims_for_relief"]},
                "drafting_readiness": {"phase_status": "warning"},
                "graph_completeness_signals": {"graph_complete": False},
                "evidence_summary": "Notice of Termination",
                "anchor_sections": ["adverse_action"],
            }

        def simulate_evidence_upload(self, query, **kwargs):
            return {"status": "success", "upload_count": 1, "search_summary": {"status": "success"}}

    monkeypatch.setattr(cli, "_load_hacc_engine", lambda: FakeEngine)
    monkeypatch.setattr(
        cli,
        "_run_adversarial_report",
        lambda **kwargs: {"status": "success", "search_summary": {"status": "success"}},
    )
    monkeypatch.setattr(cli, "_run_complaint_synthesis", lambda **kwargs: {})

    summary = cli.run_hacc_grounded_pipeline(
        output_dir=tmp_path,
        query="termination notice chronology",
        claim_type="housing_discrimination",
        top_k=1,
    )

    artifacts = summary["artifacts"]
    assert Path(artifacts["production_evidence_intake_steps_json"]).is_file()
    assert Path(artifacts["mediator_upload_checklist_json"]).is_file()
    assert Path(artifacts["document_generation_checklist_json"]).is_file()
    assert Path(artifacts["evidence_upload_form_seed_json"]).is_file()
    assert Path(artifacts["claim_support_temporal_handoff_json"]).is_file()
    assert Path(artifacts["document_generation_handoff_json"]).is_file()
    assert Path(artifacts["drafting_readiness_json"]).is_file()
    assert Path(artifacts["graph_completeness_signals_json"]).is_file()
    assert Path(artifacts["research_package_json"]).is_file()
    assert Path(artifacts["research_grounding_summary_json"]).is_file()
    assert Path(artifacts["seeded_discovery_plan_json"]).is_file()
    assert Path(artifacts["research_action_queue_json"]).is_file()
    assert Path(artifacts["recommended_next_action_json"]).is_file()
    assert Path(artifacts["seeded_commoncrawl_discovery_json"]).is_file()
    assert Path(artifacts["grounded_next_steps_json"]).is_file()
    assert Path(artifacts["grounded_intake_follow_up_worksheet_json"]).is_file()
    assert Path(artifacts["grounded_intake_follow_up_worksheet_md"]).is_file()
    assert Path(artifacts["grounded_workflow_status_json"]).is_file()
    assert Path(artifacts["grounded_workflow_status_md"]).is_file()
    assert Path(artifacts["grounded_workflow_history_json"]).is_file()

    production_steps = json.loads(Path(artifacts["production_evidence_intake_steps_json"]).read_text(encoding="utf-8"))
    mediator_checklist = json.loads(Path(artifacts["mediator_upload_checklist_json"]).read_text(encoding="utf-8"))
    temporal_handoff = json.loads(Path(artifacts["claim_support_temporal_handoff_json"]).read_text(encoding="utf-8"))
    form_seed = json.loads(Path(artifacts["evidence_upload_form_seed_json"]).read_text(encoding="utf-8"))
    research_grounding_summary = json.loads(Path(artifacts["research_grounding_summary_json"]).read_text(encoding="utf-8"))
    research_action_queue = json.loads(Path(artifacts["research_action_queue_json"]).read_text(encoding="utf-8"))
    recommended_next_action = json.loads(Path(artifacts["recommended_next_action_json"]).read_text(encoding="utf-8"))
    seeded_discovery = json.loads(Path(artifacts["seeded_commoncrawl_discovery_json"]).read_text(encoding="utf-8"))
    grounded_next_steps = json.loads(Path(artifacts["grounded_next_steps_json"]).read_text(encoding="utf-8"))
    grounded_follow_up = json.loads(Path(artifacts["grounded_intake_follow_up_worksheet_json"]).read_text(encoding="utf-8"))
    grounded_follow_up_md = Path(artifacts["grounded_intake_follow_up_worksheet_md"]).read_text(encoding="utf-8")
    grounded_workflow_status = json.loads(Path(artifacts["grounded_workflow_status_json"]).read_text(encoding="utf-8"))
    grounded_workflow_status_md = Path(artifacts["grounded_workflow_status_md"]).read_text(encoding="utf-8")
    grounded_workflow_history = json.loads(Path(artifacts["grounded_workflow_history_json"]).read_text(encoding="utf-8"))

    assert production_steps == ["Select the strongest dated notice first."]
    assert mediator_checklist == ["Evaluate chronology anchors and named actors."]
    assert temporal_handoff["timeline_anchor_count"] == 1
    assert form_seed["claim_type"] == "housing_discrimination"
    assert research_grounding_summary["upload_ready_candidate_count"] == 1
    assert research_action_queue[0]["action"] == "upload_local_repository_evidence"
    assert recommended_next_action["action"] == "upload_local_repository_evidence"
    assert seeded_discovery["status"] == "success"
    assert seeded_discovery["queries"][0].startswith("site:hacc.example")
    assert grounded_next_steps["recommended_next_action"]["action"] == "upload_local_repository_evidence"
    assert grounded_next_steps["steps"][0].startswith("Upload the strongest repository-backed evidence")
    assert grounded_follow_up["follow_up_items"][0]["gap"] == "evidence_upload"
    assert "Grounded Intake Follow-Up Worksheet" in grounded_follow_up_md
    assert grounded_workflow_status["workflow_stage"] == "pre_grounded_follow_up"
    assert grounded_workflow_status["effective_next_action"]["action"] == "upload_local_repository_evidence"
    assert grounded_workflow_status["has_persisted_completed_grounded_worksheet"] is False
    assert grounded_workflow_status["recommended_commands"]["recommended_command_kind"] == "rerun"
    assert grounded_workflow_status["recommended_commands"]["inspect_command"].endswith(str(tmp_path))
    assert grounded_workflow_status["recommended_commands"]["recommended_command"].startswith(
        "python scripts/run_hacc_grounded_pipeline.py --output-dir"
    )
    assert grounded_workflow_status["workflow_history_count"] == 1
    assert grounded_workflow_status["last_recorded_transition"]["workflow_stage"] == "pre_grounded_follow_up"
    assert len(grounded_workflow_history) == 1
    assert grounded_workflow_history[0]["workflow_stage"] == "pre_grounded_follow_up"
    assert grounded_workflow_history[0]["effective_next_action"]["action"] == "upload_local_repository_evidence"
    assert "Grounded Workflow Status" in grounded_workflow_status_md
    assert "Workflow stage: pre_grounded_follow_up" in grounded_workflow_status_md
    assert "Recommended Commands" in grounded_workflow_status_md
    assert "Recommended rerun:" in grounded_workflow_status_md
    assert "Recent Workflow Transitions" in grounded_workflow_status_md
    assert "Recorded transitions: 1" in grounded_workflow_status_md


def test_run_hacc_grounded_pipeline_degrades_when_seeded_discovery_raises(tmp_path, monkeypatch):
    cli = _load_cli_module()

    class FakeEngine:
        def __init__(self, repo_root):
            self.repo_root = repo_root

        def research(self, query, **kwargs):
            return {
                "status": "success",
                "local_search_summary": {"status": "success"},
                "research_grounding_summary": {},
                "seeded_discovery_plan": {
                    "queries": ['site:hacc.example "termination notice chronology" policy notice hearing'],
                },
                "research_action_queue": [],
                "recommended_next_action": {},
            }

        def discover_seeded_commoncrawl(self, queries, **kwargs):
            raise RuntimeError("temporary commoncrawl failure")

        def build_grounding_bundle(self, query, **kwargs):
            return {
                "status": "success",
                "synthetic_prompts": {},
                "anchor_passages": [],
                "upload_candidates": [],
                "mediator_evidence_packets": [],
                "claim_support_temporal_handoff": {},
                "document_generation_handoff": {},
                "drafting_readiness": {},
                "graph_completeness_signals": {},
            }

        def simulate_evidence_upload(self, query, **kwargs):
            return {"status": "success", "upload_count": 0}

    monkeypatch.setattr(cli, "_load_hacc_engine", lambda: FakeEngine)
    monkeypatch.setattr(
        cli,
        "_run_adversarial_report",
        lambda **kwargs: {"status": "success", "search_summary": {"status": "success"}},
    )
    monkeypatch.setattr(cli, "_run_complaint_synthesis", lambda **kwargs: {})

    summary = cli.run_hacc_grounded_pipeline(
        output_dir=tmp_path,
        query="termination notice chronology",
        claim_type="housing_discrimination",
        top_k=1,
    )

    seeded_discovery = json.loads(
        Path(summary["artifacts"]["seeded_commoncrawl_discovery_json"]).read_text(encoding="utf-8")
    )
    assert seeded_discovery["status"] == "degraded"
    assert seeded_discovery["reason"] == "seeded_discovery_failed"
    assert "temporary commoncrawl failure" in seeded_discovery["error"]


def test_run_hacc_grounded_pipeline_persists_synthesis_roundtrip_artifacts(tmp_path, monkeypatch):
    cli = _load_cli_module()

    class FakeEngine:
        def __init__(self, repo_root):
            self.repo_root = repo_root

        def research(self, query, **kwargs):
            return {
                "status": "success",
                "local_search_summary": {"status": "success"},
                "research_grounding_summary": {},
                "seeded_discovery_plan": {},
                "research_action_queue": [],
                "recommended_next_action": {},
            }

        def build_grounding_bundle(self, query, **kwargs):
            return {
                "status": "success",
                "synthetic_prompts": {},
                "anchor_passages": [],
                "upload_candidates": [],
                "mediator_evidence_packets": [],
                "claim_support_temporal_handoff": {},
                "document_generation_handoff": {},
                "drafting_readiness": {},
                "graph_completeness_signals": {},
            }

        def simulate_evidence_upload(self, query, **kwargs):
            return {"status": "success", "upload_count": 0}

    def fake_run_complaint_synthesis(**kwargs):
        output_dir = tmp_path / "synthesized_complaint"
        output_dir.mkdir(parents=True, exist_ok=True)
        draft_path = output_dir / "draft_complaint_package.json"
        draft_path.write_text(
            json.dumps(
                {
                    "refreshed_grounding_state": {"status": "chronology_supported"},
                    "grounded_follow_up_answer_summary": {"answered_item_count": 2},
                }
            ),
            encoding="utf-8",
        )
        return {
            "output_dir": str(output_dir),
            "draft_complaint_package_json": str(draft_path),
            "draft_complaint_package_md": str(output_dir / "draft_complaint_package.md"),
            "intake_follow_up_worksheet_json": str(output_dir / "intake_follow_up_worksheet.json"),
            "intake_follow_up_worksheet_md": str(output_dir / "intake_follow_up_worksheet.md"),
        }

    monkeypatch.setattr(cli, "_load_hacc_engine", lambda: FakeEngine)
    monkeypatch.setattr(
        cli,
        "_run_adversarial_report",
        lambda **kwargs: {"status": "success", "search_summary": {"status": "success"}},
    )
    monkeypatch.setattr(cli, "_run_complaint_synthesis", fake_run_complaint_synthesis)
    completed_grounded_path = tmp_path / "grounded_answers.json"
    completed_grounded_path.write_text(
        json.dumps({"follow_up_items": [{"id": "grounded_priority_01", "answer": "Answered"}]}),
        encoding="utf-8",
    )

    summary = cli.run_hacc_grounded_pipeline(
        output_dir=tmp_path,
        query="termination notice chronology",
        claim_type="housing_discrimination",
        top_k=1,
        synthesize_complaint=True,
        completed_grounded_intake_worksheet=str(completed_grounded_path),
    )

    refreshed_path = Path(summary["artifacts"]["refreshed_grounding_state_json"])
    grounded_answer_path = Path(summary["artifacts"]["grounded_follow_up_answer_summary_json"])
    workflow_status_path = Path(summary["artifacts"]["grounded_workflow_status_json"])
    workflow_status_md_path = Path(summary["artifacts"]["grounded_workflow_status_md"])
    workflow_history_path = Path(summary["artifacts"]["grounded_workflow_history_json"])
    completed_copy_path = Path(summary["artifacts"]["completed_grounded_intake_worksheet_json"])
    assert refreshed_path.is_file()
    assert grounded_answer_path.is_file()
    assert workflow_status_path.is_file()
    assert workflow_status_md_path.is_file()
    assert workflow_history_path.is_file()
    assert completed_copy_path.is_file()
    assert json.loads(refreshed_path.read_text(encoding="utf-8"))["status"] == "chronology_supported"
    assert json.loads(grounded_answer_path.read_text(encoding="utf-8"))["answered_item_count"] == 2
    workflow_status = json.loads(workflow_status_path.read_text(encoding="utf-8"))
    workflow_history = json.loads(workflow_history_path.read_text(encoding="utf-8"))
    assert workflow_status["workflow_stage"] == "post_grounded_follow_up"
    assert workflow_status["has_refreshed_grounding_state"] is True
    assert workflow_status["grounded_follow_up_answer_count"] == 2
    assert workflow_status["has_persisted_completed_grounded_worksheet"] is True
    assert workflow_status["persisted_completed_grounded_worksheet_path"] == str(completed_copy_path)
    assert workflow_status["recommended_commands"]["recommended_command_kind"] == "synthesize"
    assert workflow_status["recommended_commands"]["recommended_command"].startswith(
        "python scripts/synthesize_hacc_complaint.py --grounded-run-dir"
    )
    assert "--synthesize-complaint" in workflow_status["recommended_commands"]["pipeline_resume_command"]
    assert workflow_status["workflow_history_count"] == 1
    assert workflow_status["last_recorded_transition"]["workflow_stage"] == "post_grounded_follow_up"
    assert len(workflow_history) == 1
    assert workflow_history[0]["workflow_stage"] == "post_grounded_follow_up"
    assert workflow_history[0]["grounded_follow_up_answer_count"] == 2
    assert "Workflow stage: post_grounded_follow_up" in workflow_status_md_path.read_text(encoding="utf-8")
    assert "Recommended synthesis:" in workflow_status_md_path.read_text(encoding="utf-8")
    assert json.loads(completed_copy_path.read_text(encoding="utf-8"))["follow_up_items"][0]["answer"] == "Answered"


def test_run_hacc_grounded_pipeline_reuses_persisted_completed_grounded_worksheet(tmp_path, monkeypatch):
    cli = _load_cli_module()

    class FakeEngine:
        def __init__(self, repo_root):
            self.repo_root = repo_root

        def research(self, query, **kwargs):
            return {
                "status": "success",
                "local_search_summary": {"status": "success"},
                "research_grounding_summary": {},
                "seeded_discovery_plan": {},
                "research_action_queue": [],
                "recommended_next_action": {},
            }

        def build_grounding_bundle(self, query, **kwargs):
            return {
                "status": "success",
                "synthetic_prompts": {},
                "anchor_passages": [],
                "upload_candidates": [],
                "mediator_evidence_packets": [],
                "claim_support_temporal_handoff": {},
                "document_generation_handoff": {},
                "drafting_readiness": {},
                "graph_completeness_signals": {},
            }

        def simulate_evidence_upload(self, query, **kwargs):
            return {"status": "success", "upload_count": 0}

    captured = {}

    def fake_run_complaint_synthesis(**kwargs):
        captured.update(kwargs)
        return {}

    persisted = tmp_path / "completed_grounded_intake_follow_up_worksheet.json"
    persisted.write_text(
        json.dumps({"follow_up_items": [{"id": "grounded_priority_01", "answer": "Existing answer"}]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_load_hacc_engine", lambda: FakeEngine)
    monkeypatch.setattr(
        cli,
        "_run_adversarial_report",
        lambda **kwargs: {"status": "success", "search_summary": {"status": "success"}},
    )
    monkeypatch.setattr(cli, "_run_complaint_synthesis", fake_run_complaint_synthesis)

    cli.run_hacc_grounded_pipeline(
        output_dir=tmp_path,
        query="termination notice chronology",
        claim_type="housing_discrimination",
        top_k=1,
        synthesize_complaint=True,
    )

    assert captured["completed_grounded_intake_worksheet"] == str(persisted)


def test_run_hacc_grounded_pipeline_appends_workflow_history_across_reruns(tmp_path, monkeypatch):
    cli = _load_cli_module()

    class FakeEngine:
        def __init__(self, repo_root):
            self.repo_root = repo_root

        def research(self, query, **kwargs):
            return {
                "status": "success",
                "local_search_summary": {"status": "success"},
                "research_grounding_summary": {},
                "seeded_discovery_plan": {},
                "research_action_queue": [],
                "recommended_next_action": {
                    "phase_name": "evidence_upload",
                    "action": "upload_local_repository_evidence",
                    "description": "Upload repository evidence first.",
                },
            }

        def build_grounding_bundle(self, query, **kwargs):
            return {
                "status": "success",
                "synthetic_prompts": {},
                "anchor_passages": [],
                "upload_candidates": [],
                "mediator_evidence_packets": [],
                "claim_support_temporal_handoff": {},
                "document_generation_handoff": {},
                "drafting_readiness": {},
                "graph_completeness_signals": {},
            }

        def simulate_evidence_upload(self, query, **kwargs):
            return {"status": "success", "upload_count": 0}

    run_counter = {"count": 0}

    def fake_run_complaint_synthesis(**kwargs):
        run_counter["count"] += 1
        output_dir = tmp_path / "synthesized_complaint"
        output_dir.mkdir(parents=True, exist_ok=True)
        draft_path = output_dir / "draft_complaint_package.json"
        if run_counter["count"] == 1:
            payload = {}
        else:
            payload = {
                "refreshed_grounding_state": {
                    "status": "chronology_supported",
                    "recommended_next_action": {
                        "phase_name": "document_generation",
                        "action": "continue_drafting",
                        "description": "Chronology is now supported enough to continue drafting.",
                    },
                },
                "grounded_follow_up_answer_summary": {"answered_item_count": 3},
            }
        draft_path.write_text(json.dumps(payload), encoding="utf-8")
        return {
            "output_dir": str(output_dir),
            "draft_complaint_package_json": str(draft_path),
            "draft_complaint_package_md": str(output_dir / "draft_complaint_package.md"),
            "intake_follow_up_worksheet_json": str(output_dir / "intake_follow_up_worksheet.json"),
            "intake_follow_up_worksheet_md": str(output_dir / "intake_follow_up_worksheet.md"),
        }

    monkeypatch.setattr(cli, "_load_hacc_engine", lambda: FakeEngine)
    monkeypatch.setattr(
        cli,
        "_run_adversarial_report",
        lambda **kwargs: {"status": "success", "search_summary": {"status": "success"}},
    )
    monkeypatch.setattr(cli, "_run_complaint_synthesis", fake_run_complaint_synthesis)

    first_summary = cli.run_hacc_grounded_pipeline(
        output_dir=tmp_path,
        query="termination notice chronology",
        claim_type="housing_discrimination",
        top_k=1,
        synthesize_complaint=True,
    )
    second_summary = cli.run_hacc_grounded_pipeline(
        output_dir=tmp_path,
        query="termination notice chronology",
        claim_type="housing_discrimination",
        top_k=1,
        synthesize_complaint=True,
    )

    history_path = Path(second_summary["artifacts"]["grounded_workflow_history_json"])
    history = json.loads(history_path.read_text(encoding="utf-8"))

    assert history_path == Path(first_summary["artifacts"]["grounded_workflow_history_json"])
    assert len(history) == 2
    assert history[0]["workflow_stage"] == "pre_grounded_follow_up"
    assert history[0]["effective_next_action"]["action"] == "upload_local_repository_evidence"
    assert history[1]["workflow_stage"] == "post_grounded_follow_up"
    assert history[1]["effective_next_action"]["action"] == "continue_drafting"
    assert history[1]["grounded_follow_up_answer_count"] == 3
    assert second_summary["grounded_workflow_status"]["workflow_history_count"] == 2
    assert second_summary["grounded_workflow_status"]["last_recorded_transition"]["workflow_stage"] == "post_grounded_follow_up"
