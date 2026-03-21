import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from adversarial_harness.demo_autopatch import _build_runtime_optimization_guidance


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_hacc_adversarial_report.py"
SPEC = importlib.util.spec_from_file_location("run_hacc_adversarial_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_main_persists_workflow_phase_task_plan(tmp_path, monkeypatch):
    fake_adversarial_harness = ModuleType("adversarial_harness")

    class FakeHarness:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_batch(self, **kwargs):
            return [SimpleNamespace(success=True, critic_score=object())]

        def get_statistics(self):
            return {"successful_sessions": 1, "total_sessions": 1}

        def save_results(self, path):
            Path(path).write_text(json.dumps({"results": []}, indent=2), encoding="utf-8")

        def save_anchor_section_report(self, path, format="csv"):
            Path(path).write_text("stub", encoding="utf-8")

    class FakeReport:
        def to_dict(self):
            return {
                "average_score": 0.82,
                "score_trend": "stable",
                "workflow_phase_plan": {
                    "recommended_order": ["intake_questioning", "graph_analysis"],
                    "phases": {
                        "intake_questioning": {"status": "critical"},
                        "graph_analysis": {"status": "warning"},
                    },
                },
            }

    class FakeOptimizer:
        def analyze(self, results):
            return FakeReport()

        def build_workflow_optimization_bundle(self, results, report=None, components=None):
            return (
                SimpleNamespace(
                    to_dict=lambda: {
                        "timestamp": "2026-03-20T00:00:00+00:00",
                        "num_sessions_analyzed": 1,
                        "average_score": 0.82,
                        "workflow_phase_plan": {
                            "recommended_order": ["intake_questioning", "graph_analysis"],
                            "phases": {
                                "intake_questioning": {"status": "critical"},
                                "graph_analysis": {"status": "warning"},
                            },
                        },
                        "global_objectives": ["Improve intake questioning"],
                        "phase_tasks": [],
                        "shared_context": {"coverage_remediation": {}},
                        "phase_scorecards": {"intake_questioning": {"status": "critical"}},
                        "cross_phase_findings": ["Intake gaps suppress graph quality."],
                        "workflow_action_queue": [{"phase_name": "intake_questioning", "action": "Improve intake targeting."}],
                    }
                ),
                report,
            )

        @staticmethod
        def _fallback_agentic_optimizer_components():
            return {}

        def build_phase_patch_tasks(self, results, report=None, components=None):
            return (
                [
                    SimpleNamespace(
                        task_id="phase_task_1",
                        description="Improve intake questioning",
                        target_files=[Path("adversarial_harness/session.py")],
                        method="ACTOR_CRITIC",
                        priority=70,
                        metadata={"workflow_phase": "intake_questioning"},
                    )
                ],
                report,
            )

    fake_adversarial_harness.AdversarialHarness = FakeHarness
    fake_adversarial_harness.HACC_QUERY_PRESETS = {"core_hacc_policies": {"query": "stub"}}
    fake_adversarial_harness.Optimizer = FakeOptimizer
    monkeypatch.setitem(sys.modules, "adversarial_harness", fake_adversarial_harness)

    fake_backends = ModuleType("backends")
    fake_backends.LLMRouterBackend = lambda **kwargs: SimpleNamespace(**kwargs)
    monkeypatch.setitem(sys.modules, "backends", fake_backends)

    fake_integrations = ModuleType("integrations.ipfs_datasets")
    fake_integrations.ensure_ipfs_backend = lambda prefer_local_fallback=True: None
    fake_integrations.get_router_status_report = lambda **kwargs: {"status": "available"}
    monkeypatch.setitem(sys.modules, "integrations.ipfs_datasets", fake_integrations)

    fake_mediator_module = ModuleType("mediator.mediator")
    fake_mediator_module.Mediator = lambda **kwargs: SimpleNamespace(**kwargs)
    monkeypatch.setitem(sys.modules, "mediator.mediator", fake_mediator_module)

    monkeypatch.setattr(MODULE, "_load_config", lambda path: {"BACKENDS": [{"id": "router", "type": "llm_router"}], "MEDIATOR": {"backends": ["router"]}})
    monkeypatch.setattr(MODULE, "_select_llm_router_backend_config", lambda config, backend_id: ("router", {"id": "router"}, [], True))
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        [
            "run_hacc_adversarial_report.py",
            "--output-dir",
            str(tmp_path),
            "--num-sessions",
            "1",
            "--max-turns",
            "2",
        ],
    )

    exit_code = MODULE.main()

    assert exit_code == 0
    workflow_tasks_path = tmp_path / "workflow_phase_tasks.json"
    workflow_bundle_path = tmp_path / "workflow_optimization_bundle.json"
    summary_path = tmp_path / "run_summary.json"
    assert workflow_tasks_path.is_file()
    assert workflow_bundle_path.is_file()
    assert summary_path.is_file()

    workflow_tasks = json.loads(workflow_tasks_path.read_text(encoding="utf-8"))
    workflow_bundle = json.loads(workflow_bundle_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert workflow_tasks[0]["task_id"] == "phase_task_1"
    assert workflow_tasks[0]["target_files"] == ["adversarial_harness/session.py"]
    assert workflow_bundle["phase_scorecards"]["intake_questioning"]["status"] == "critical"
    assert workflow_bundle["cross_phase_findings"] == ["Intake gaps suppress graph quality."]
    assert workflow_bundle["workflow_action_queue"][0]["phase_name"] == "intake_questioning"
    assert summary["workflow_phase_task_count"] == 1
    assert summary["artifacts"]["workflow_optimization_bundle_json"] == str(workflow_bundle_path)
    assert summary["artifacts"]["workflow_phase_tasks_json"] == str(workflow_tasks_path)
    assert summary["workflow_phase_plan"]["recommended_order"] == ["intake_questioning", "graph_analysis"]
    assert summary["workflow_optimization_bundle"]["phase_scorecards"]["intake_questioning"]["status"] == "critical"


def test_main_can_emit_phase_autopatch_artifacts(tmp_path, monkeypatch):
    fake_adversarial_harness = ModuleType("adversarial_harness")
    fake_adversarial_harness.__path__ = []

    class FakeHarness:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_batch(self, **kwargs):
            return [SimpleNamespace(success=True, critic_score=object())]

        def get_statistics(self):
            return {"successful_sessions": 1, "total_sessions": 1}

        def save_results(self, path):
            Path(path).write_text(json.dumps({"results": []}, indent=2), encoding="utf-8")

        def save_anchor_section_report(self, path, format="csv"):
            Path(path).write_text("stub", encoding="utf-8")

    class FakeReport:
        def to_dict(self):
            return {
                "average_score": 0.82,
                "score_trend": "stable",
                "workflow_phase_plan": {
                    "recommended_order": ["intake_questioning"],
                    "phases": {"intake_questioning": {"status": "critical"}},
                },
            }

    class FakeOptimizer:
        def analyze(self, results):
            return FakeReport()

        @staticmethod
        def _fallback_agentic_optimizer_components():
            return {}

        def build_phase_patch_tasks(self, results, report=None, components=None):
            return (
                [
                    SimpleNamespace(
                        task_id="phase_task_1",
                        description="Improve intake questioning",
                        target_files=[Path("adversarial_harness/session.py")],
                        method="ACTOR_CRITIC",
                        priority=70,
                        metadata={
                            "workflow_phase": "intake_questioning",
                            "report_summary": {"recommendations": ["Add stronger timeline probes"]},
                        },
                    )
                ],
                report,
            )

    class FakeDemoPatchOptimizer:
        def __init__(self, *, project_root, output_dir, marker_prefix):
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)

        def optimize(self, task):
            patch_path = self.output_dir / "phase_task_1.patch"
            patch_path.write_text("patch", encoding="utf-8")
            return SimpleNamespace(success=True, patch_path=patch_path, patch_cid="phase-cid", metadata={"demo": True})

    fake_demo_autopatch = ModuleType("adversarial_harness.demo_autopatch")
    fake_demo_autopatch.DemoPatchOptimizer = FakeDemoPatchOptimizer

    fake_adversarial_harness.AdversarialHarness = FakeHarness
    fake_adversarial_harness.HACC_QUERY_PRESETS = {"core_hacc_policies": {"query": "stub"}}
    fake_adversarial_harness.Optimizer = FakeOptimizer
    monkeypatch.setitem(sys.modules, "adversarial_harness", fake_adversarial_harness)
    monkeypatch.setitem(sys.modules, "adversarial_harness.demo_autopatch", fake_demo_autopatch)

    fake_backends = ModuleType("backends")
    fake_backends.LLMRouterBackend = lambda **kwargs: SimpleNamespace(**kwargs)
    monkeypatch.setitem(sys.modules, "backends", fake_backends)

    fake_integrations = ModuleType("integrations.ipfs_datasets")
    fake_integrations.ensure_ipfs_backend = lambda prefer_local_fallback=True: None
    fake_integrations.get_router_status_report = lambda **kwargs: {"status": "available"}
    monkeypatch.setitem(sys.modules, "integrations.ipfs_datasets", fake_integrations)

    fake_mediator_module = ModuleType("mediator.mediator")
    fake_mediator_module.Mediator = lambda **kwargs: SimpleNamespace(**kwargs)
    monkeypatch.setitem(sys.modules, "mediator.mediator", fake_mediator_module)

    monkeypatch.setattr(MODULE, "_load_config", lambda path: {"BACKENDS": [{"id": "router", "type": "llm_router"}], "MEDIATOR": {"backends": ["router"]}})
    monkeypatch.setattr(MODULE, "_select_llm_router_backend_config", lambda config, backend_id: ("router", {"id": "router"}, [], True))
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        [
            "run_hacc_adversarial_report.py",
            "--output-dir",
            str(tmp_path),
            "--num-sessions",
            "1",
            "--max-turns",
            "2",
            "--emit-phase-autopatch-artifacts",
        ],
    )

    exit_code = MODULE.main()

    assert exit_code == 0
    autopatch_results_path = tmp_path / "workflow_phase_autopatch_results.json"
    summary_path = tmp_path / "run_summary.json"
    assert autopatch_results_path.is_file()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    autopatch_results = json.loads(autopatch_results_path.read_text(encoding="utf-8"))

    assert autopatch_results[0]["phase"] == "intake_questioning"
    assert autopatch_results[0]["patch_cid"] == "phase-cid"
    assert summary["workflow_phase_autopatch_count"] == 1
    assert summary["artifacts"]["workflow_phase_autopatch_results_json"] == str(autopatch_results_path)


def test_runtime_optimization_guidance_preserves_document_evidence_targeting_summary():
    guidance = _build_runtime_optimization_guidance(
        workflow_bundle={"shared_context": {"workflow_targeting_summary": {"count": 2, "phase_counts": {"graph_analysis": 1, "document_generation": 1}}}},
        report_payload={
            "document_evidence_targeting_summary": {
                "count": 1,
                "claim_element_counts": {"protected_activity": 1},
            },
            "document_workflow_execution_summary": {
                "iteration_count": 2,
                "first_focus_section": "claims_for_relief",
                "first_targeted_claim_element": "protected_activity",
            },
            "document_execution_drift_summary": {
                "drift_flag": True,
                "top_targeted_claim_element": "causation",
                "first_executed_claim_element": "protected_activity",
            },
            "document_grounding_improvement_summary": {
                "initial_fact_backed_ratio": 0.2,
                "final_fact_backed_ratio": 0.5,
                "fact_backed_ratio_delta": 0.3,
                "improved_flag": True,
            },
            "workflow_action_queue": [
                {"phase_name": "graph_analysis", "action": "Collect chronology support."}
            ],
        },
    )

    assert guidance["document_evidence_targeting_summary"]["count"] == 1
    assert guidance["document_evidence_targeting_summary"]["claim_element_counts"] == {
        "protected_activity": 1,
    }
    assert guidance["workflow_targeting_summary"]["count"] == 2
    assert guidance["workflow_targeting_summary"]["phase_counts"] == {
        "graph_analysis": 1,
        "document_generation": 1,
    }
    assert guidance["document_workflow_execution_summary"]["iteration_count"] == 2
    assert guidance["document_workflow_execution_summary"]["first_focus_section"] == "claims_for_relief"
    assert guidance["document_execution_drift_summary"]["drift_flag"] is True
    assert guidance["document_execution_drift_summary"]["top_targeted_claim_element"] == "causation"
    assert guidance["document_grounding_improvement_summary"]["improved_flag"] is True
    assert guidance["document_grounding_improvement_summary"]["fact_backed_ratio_delta"] == 0.3
