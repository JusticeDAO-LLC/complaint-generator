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
            "--json",
        ]
    )

    assert args.hacc_preset == "core_hacc_policies"
    assert args.top_k == 2
    assert args.use_hacc_vector_search is True
    assert args.synthesize_complaint is True
    assert args.json is True


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
