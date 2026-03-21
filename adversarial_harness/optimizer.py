
from workflow_phase_guidance import build_workflow_phase_plan
"""
Optimizer Module

Analyzes critic feedback and provides optimization recommendations.
"""

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import UTC, datetime
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class OptimizationReport:
    """Report with optimization insights and recommendations."""
    timestamp: str
    num_sessions_analyzed: int
    
    # Aggregate metrics
    average_score: float
    score_trend: str  # improving, declining, stable
    
    # Analysis by component
    question_quality_avg: float
    information_extraction_avg: float
    empathy_avg: float
    efficiency_avg: float
    coverage_avg: float
    
    # Top issues
    common_weaknesses: List[str]
    common_strengths: List[str]
    
    # Recommendations
    recommendations: List[str]
    priority_improvements: List[str]

    # Graph diagnostics (used to steer graph population/reduction improvements)
    kg_sessions_with_data: int = 0
    dg_sessions_with_data: int = 0
    kg_sessions_empty: int = 0
    dg_sessions_empty: int = 0
    kg_avg_total_entities: Optional[float] = None
    kg_avg_total_relationships: Optional[float] = None
    kg_avg_gaps: Optional[float] = None
    dg_avg_total_nodes: Optional[float] = None
    dg_avg_total_dependencies: Optional[float] = None
    dg_avg_satisfaction_rate: Optional[float] = None
    kg_avg_entities_delta_per_iter: Optional[float] = None
    kg_avg_relationships_delta_per_iter: Optional[float] = None
    kg_avg_gaps_delta_per_iter: Optional[float] = None
    kg_sessions_gaps_not_reducing: int = 0
    
    # Detailed insights
    best_session_id: str = None
    worst_session_id: str = None
    best_score: float = 0.0
    worst_score: float = 1.0
    hacc_preset_performance: Dict[str, Dict[str, Any]] | None = None
    anchor_section_performance: Dict[str, Dict[str, Any]] | None = None
    complaint_type_performance: Dict[str, Dict[str, Any]] | None = None
    evidence_modality_performance: Dict[str, Dict[str, Any]] | None = None
    intake_priority_performance: Dict[str, Any] | None = None
    coverage_remediation: Dict[str, Any] | None = None
    recommended_hacc_preset: str | None = None
    workflow_phase_plan: Dict[str, Any] | None = None
    phase_scorecards: Dict[str, Dict[str, Any]] | None = None
    intake_targeting_summary: Dict[str, Any] | None = None
    workflow_targeting_summary: Dict[str, Any] | None = None
    complaint_type_generalization_summary: Dict[str, Any] | None = None
    evidence_modality_generalization_summary: Dict[str, Any] | None = None
    document_handoff_summary: Dict[str, Any] | None = None
    graph_element_targeting_summary: Dict[str, Any] | None = None
    document_evidence_targeting_summary: Dict[str, Any] | None = None
    document_workflow_execution_summary: Dict[str, Any] | None = None
    document_execution_drift_summary: Dict[str, Any] | None = None
    document_grounding_improvement_summary: Dict[str, Any] | None = None
    cross_phase_findings: List[str] | None = None
    workflow_action_queue: List[Dict[str, Any]] | None = None
    document_provenance_summary: Dict[str, Any] | None = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp,
            'num_sessions_analyzed': self.num_sessions_analyzed,
            'average_score': self.average_score,
            'score_trend': self.score_trend,
            'question_quality_avg': self.question_quality_avg,
            'information_extraction_avg': self.information_extraction_avg,
            'empathy_avg': self.empathy_avg,
            'efficiency_avg': self.efficiency_avg,
            'coverage_avg': self.coverage_avg,
            'common_weaknesses': self.common_weaknesses,
            'common_strengths': self.common_strengths,
            'recommendations': self.recommendations,
            'priority_improvements': self.priority_improvements,
            'kg_sessions_with_data': self.kg_sessions_with_data,
            'dg_sessions_with_data': self.dg_sessions_with_data,
            'kg_sessions_empty': self.kg_sessions_empty,
            'dg_sessions_empty': self.dg_sessions_empty,
            'kg_avg_total_entities': self.kg_avg_total_entities,
            'kg_avg_total_relationships': self.kg_avg_total_relationships,
            'kg_avg_gaps': self.kg_avg_gaps,
            'dg_avg_total_nodes': self.dg_avg_total_nodes,
            'dg_avg_total_dependencies': self.dg_avg_total_dependencies,
            'dg_avg_satisfaction_rate': self.dg_avg_satisfaction_rate,
            'kg_avg_entities_delta_per_iter': self.kg_avg_entities_delta_per_iter,
            'kg_avg_relationships_delta_per_iter': self.kg_avg_relationships_delta_per_iter,
            'kg_avg_gaps_delta_per_iter': self.kg_avg_gaps_delta_per_iter,
            'kg_sessions_gaps_not_reducing': self.kg_sessions_gaps_not_reducing,
            'best_session_id': self.best_session_id,
            'worst_session_id': self.worst_session_id,
            'best_score': self.best_score,
            'worst_score': self.worst_score,
            'hacc_preset_performance': self.hacc_preset_performance or {},
            'anchor_section_performance': self.anchor_section_performance or {},
            'complaint_type_performance': self.complaint_type_performance or {},
            'evidence_modality_performance': self.evidence_modality_performance or {},
            'intake_priority_performance': self.intake_priority_performance or {},
            'coverage_remediation': self.coverage_remediation or {},
            'recommended_hacc_preset': self.recommended_hacc_preset,
            'workflow_phase_plan': self.workflow_phase_plan or {},
            'phase_scorecards': self.phase_scorecards or {},
            'intake_targeting_summary': self.intake_targeting_summary or {},
            'workflow_targeting_summary': self.workflow_targeting_summary or {},
            'complaint_type_generalization_summary': self.complaint_type_generalization_summary or {},
            'evidence_modality_generalization_summary': self.evidence_modality_generalization_summary or {},
            'document_handoff_summary': self.document_handoff_summary or {},
            'graph_element_targeting_summary': self.graph_element_targeting_summary or {},
            'document_evidence_targeting_summary': self.document_evidence_targeting_summary or {},
            'document_provenance_summary': self.document_provenance_summary or {},
            'document_workflow_execution_summary': self.document_workflow_execution_summary or {},
            'document_execution_drift_summary': self.document_execution_drift_summary or {},
            'document_grounding_improvement_summary': self.document_grounding_improvement_summary or {},
            'cross_phase_findings': list(self.cross_phase_findings or []),
            'workflow_action_queue': list(self.workflow_action_queue or []),
        }


@dataclass
class WorkflowOptimizationBundle:
    """Serializable optimization bundle spanning the full complaint workflow."""

    timestamp: str
    num_sessions_analyzed: int
    average_score: float
    workflow_phase_plan: Dict[str, Any]
    global_objectives: List[str]
    phase_tasks: List[Dict[str, Any]]
    shared_context: Dict[str, Any]
    phase_scorecards: Dict[str, Dict[str, Any]] | None = None
    cross_phase_findings: List[str] | None = None
    workflow_action_queue: List[Dict[str, Any]] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "num_sessions_analyzed": self.num_sessions_analyzed,
            "average_score": self.average_score,
            "workflow_phase_plan": dict(self.workflow_phase_plan or {}),
            "global_objectives": list(self.global_objectives or []),
            "phase_tasks": list(self.phase_tasks or []),
            "shared_context": dict(self.shared_context or {}),
            "phase_scorecards": dict(self.phase_scorecards or {}),
            "cross_phase_findings": list(self.cross_phase_findings or []),
            "workflow_action_queue": list(self.workflow_action_queue or []),
        }


class Optimizer:
    """
    Analyzes critic feedback to provide optimization recommendations.
    
    The optimizer:
    - Aggregates scores across sessions
    - Identifies patterns in successes and failures
    - Generates actionable recommendations
    - Tracks improvement over time
    """
    
    def __init__(self):
        """Initialize optimizer."""
        self.history = []
        self._last_agentic_generation_diagnostics: List[Dict[str, Any]] = []
        self._last_agentic_optimizer: Any = None

    @staticmethod
    def _load_agentic_optimizer_components() -> Dict[str, Any]:
        try:
            import sys

            from integrations.ipfs_datasets.loader import ensure_import_paths, get_repo_paths, import_attr_optional

            ensure_import_paths(module_name="ipfs_datasets_py.optimizers.agentic")

            repo_paths = get_repo_paths()
            expected_package_root = repo_paths.ipfs_datasets_repo / "ipfs_datasets_py"
            cached_module = sys.modules.get("ipfs_datasets_py")
            cached_paths = [str(path) for path in getattr(cached_module, "__path__", [])]
            if cached_module is not None and str(expected_package_root) not in cached_paths:
                for module_name in list(sys.modules):
                    if module_name == "ipfs_datasets_py" or module_name.startswith("ipfs_datasets_py."):
                        sys.modules.pop(module_name, None)
        except Exception:
            pass

        OptimizationTask, task_error = import_attr_optional(
            "ipfs_datasets_py.optimizers.agentic.base",
            "OptimizationTask",
        )
        OptimizationMethod, method_error = import_attr_optional(
            "ipfs_datasets_py.optimizers.agentic.base",
            "OptimizationMethod",
        )
        OptimizerLLMRouter, router_error = import_attr_optional(
            "ipfs_datasets_py.optimizers.agentic.llm_integration",
            "OptimizerLLMRouter",
        )
        ActorCriticOptimizer, actor_error = import_attr_optional(
            "ipfs_datasets_py.optimizers.agentic.methods.actor_critic",
            "ActorCriticOptimizer",
        )
        AdversarialOptimizer, adversarial_error = import_attr_optional(
            "ipfs_datasets_py.optimizers.agentic.methods.adversarial",
            "AdversarialOptimizer",
        )
        ChaosOptimizer, chaos_error = import_attr_optional(
            "ipfs_datasets_py.optimizers.agentic.methods.chaos",
            "ChaosOptimizer",
        )
        TestDrivenOptimizer, test_driven_error = import_attr_optional(
            "ipfs_datasets_py.optimizers.agentic.methods.test_driven",
            "TestDrivenOptimizer",
        )

        import_errors = [
            error
            for error in (
                task_error,
                method_error,
                router_error,
                actor_error,
                adversarial_error,
                chaos_error,
                test_driven_error,
            )
            if error is not None
        ]
        if import_errors:
            raise RuntimeError(str(import_errors[0]))

        return {
            "OptimizationTask": OptimizationTask,
            "OptimizationMethod": OptimizationMethod,
            "OptimizerLLMRouter": OptimizerLLMRouter,
            "optimizer_classes": {
                "actor_critic": ActorCriticOptimizer,
                "adversarial": AdversarialOptimizer,
                "test_driven": TestDrivenOptimizer,
                "chaos": ChaosOptimizer,
            },
        }

    @staticmethod
    def _fallback_agentic_optimizer_components() -> Dict[str, Any]:
        class FallbackOptimizationTask:
            def __init__(
                self,
                task_id: str,
                description: str,
                target_files: List[Path],
                method: Any,
                priority: int,
                constraints: Dict[str, Any],
                metadata: Dict[str, Any],
            ) -> None:
                self.task_id = task_id
                self.description = description
                self.target_files = target_files
                self.method = method
                self.priority = priority
                self.constraints = constraints
                self.metadata = metadata

        fallback_method = SimpleNamespace(
            ACTOR_CRITIC="ACTOR_CRITIC",
            ADVERSARIAL="ADVERSARIAL",
            TEST_DRIVEN="TEST_DRIVEN",
            CHAOS="CHAOS",
        )
        return {
            "OptimizationTask": FallbackOptimizationTask,
            "OptimizationMethod": fallback_method,
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        }

    def _build_agentic_patch_description(
        self,
        report: OptimizationReport,
        *,
        method: str,
        target_files: List[Path],
    ) -> str:
        focus_items = list(report.priority_improvements or [])[:3]
        if not focus_items:
            focus_items = list(report.common_weaknesses or [])[:3]
        if not focus_items:
            focus_items = ["stabilize adversarial mediator questioning flow"]
        weakest_intake_objectives = self._top_uncovered_intake_objectives(report)

        target_labels = ", ".join(str(path) for path in target_files) or "target files auto-detected"
        focus_text = "; ".join(focus_items)
        description = (
            f"Use the {method} optimizer to improve the complaint-generator adversarial complainant/mediator loop. "
            f"Target files: {target_labels}. Priorities from the latest adversarial batch: {focus_text}. "
            f"Preserve current behavior while improving router-backed question quality, information extraction, coverage, and patchability."
        )
        phase_plan = dict(report.workflow_phase_plan or {})
        phase_order = [str(value) for value in list(phase_plan.get("recommended_order") or []) if str(value)]
        if phase_order:
            description += " Phase focus order: " + ", ".join(phase_order[:3]) + "."
        if weakest_intake_objectives:
            description += (
                " The weakest unresolved intake objectives were: "
                + ", ".join(weakest_intake_objectives[:3])
                + "."
            )
        return description

    @staticmethod
    def _top_uncovered_intake_objectives(report: OptimizationReport, limit: int = 3) -> List[str]:
        coverage_by_objective = dict((report.intake_priority_performance or {}).get("coverage_by_objective") or {})
        weakest = [
            (name, payload)
            for name, payload in sorted(
                coverage_by_objective.items(),
                key=lambda item: (
                    float((item[1] or {}).get("coverage_rate") or 0.0),
                    -int((item[1] or {}).get("expected") or 0),
                    item[0],
                ),
            )
            if int((payload or {}).get("expected") or 0) > 0 and float((payload or {}).get("coverage_rate") or 0.0) < 1.0
        ]
        return [name for name, _payload in weakest[: max(0, int(limit))]]

    @classmethod
    def _recommended_target_files_for_report(cls, report: OptimizationReport) -> List[Path]:
        objectives = cls._top_uncovered_intake_objectives(report, limit=5)
        recommendations: List[Path] = []

        def add_target(path: str) -> None:
            candidate = Path(path)
            if candidate not in recommendations:
                recommendations.append(candidate)

        if objectives:
            add_target("adversarial_harness/session.py")

        if any(
            objective in {"timeline", "actors", "documents", "witnesses", "harm_remedy"}
            or objective in {"exact_dates", "staff_names_titles", "hearing_request_timing", "response_dates", "causation_sequence"}
            or str(objective).startswith("anchor_")
            for objective in objectives
        ):
            add_target("mediator/mediator.py")

        if any(objective in {"harm_remedy", "actors"} for objective in objectives):
            add_target("adversarial_harness/complainant.py")

        if any(
            objective in {"exact_dates", "staff_names_titles", "hearing_request_timing", "response_dates", "causation_sequence"}
            for objective in objectives
        ):
            add_target("complaint_phases/denoiser.py")
            add_target("document_optimization.py")

        if not recommendations and isinstance(report.workflow_phase_plan, dict):
            phases = dict(report.workflow_phase_plan.get("phases") or {})
            for phase_name in list(report.workflow_phase_plan.get("recommended_order") or []):
                phase_payload = dict(phases.get(phase_name) or {})
                if str(phase_payload.get("status") or "ready") == "ready":
                    continue
                for path in list(phase_payload.get("target_files") or []):
                    add_target(str(path))

        return recommendations

    @staticmethod
    def _dedupe_text(values: List[str]) -> List[str]:
        deduped: List[str] = []
        seen = set()
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(text)
        return deduped

    @staticmethod
    def _phase_status(severity: int) -> str:
        if int(severity) >= 5:
            return "critical"
        if int(severity) > 0:
            return "warning"
        return "ready"

    def _build_workflow_phase_plan(
        self,
        *,
        question_quality_avg: float,
        information_extraction_avg: float,
        efficiency_avg: float,
        coverage_avg: float,
        graph_summary: Dict[str, Any],
        coverage_remediation: Dict[str, Any],
        document_evidence_targeting_summary: Optional[Dict[str, Any]] = None,
        document_provenance_summary: Optional[Dict[str, Any]] = None,
        document_workflow_execution_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        document_evidence_targeting_summary = dict(document_evidence_targeting_summary or {})
        document_provenance_summary = dict(document_provenance_summary or {})
        document_workflow_execution_summary = dict(document_workflow_execution_summary or {})
        intake_actions = list((coverage_remediation.get("intake_priorities") or {}).get("recommended_actions") or [])
        intake_signals: List[str] = []
        intake_recommendations: List[Dict[str, Any]] = []
        intake_severity = 0

        if intake_actions:
            intake_signals.append(f"{len(intake_actions)} intake objectives remain uncovered")
            intake_severity += 3
            for item in intake_actions[:3]:
                intake_recommendations.append(
                    {
                        "focus": str(item.get("objective") or "intake_priority"),
                        "signal": "intake_coverage_gap",
                        "recommended_action": str(item.get("recommended_action") or "Add a dedicated intake fallback question."),
                    }
                )
        if question_quality_avg < 0.7:
            intake_signals.append(f"question quality average is {question_quality_avg:.2f}")
            intake_severity += 2 if question_quality_avg < 0.6 else 1
            intake_recommendations.append(
                {
                    "focus": "mediator_questioning",
                    "signal": "question_quality",
                    "recommended_action": "Tighten mediator prompts so each question is specific to the unresolved factual gap and references the strongest available evidence anchor.",
                }
            )
        if efficiency_avg < 0.7:
            intake_signals.append(f"efficiency average is {efficiency_avg:.2f}")
            intake_severity += 2 if efficiency_avg < 0.6 else 1
            intake_recommendations.append(
                {
                    "focus": "question_deduplication",
                    "signal": "efficiency",
                    "recommended_action": "Prefer unanswered objectives before revisiting covered topics, and deduplicate repeated mediator questions across turns.",
                }
            )
        if coverage_avg < 0.7:
            intake_signals.append(f"coverage average is {coverage_avg:.2f}")
            intake_severity += 2 if coverage_avg < 0.6 else 1
            intake_recommendations.append(
                {
                    "focus": "intake_flow",
                    "signal": "coverage",
                    "recommended_action": "Keep timeline, actors, documents, witnesses, and harm/remedy prompts ahead of generic wrap-up questions so intake exits with fewer factual gaps.",
                }
            )

        graph_signals: List[str] = []
        graph_recommendations: List[Dict[str, Any]] = []
        graph_severity = 0
        kg_with = int(graph_summary.get("kg_sessions_with_data") or 0)
        dg_with = int(graph_summary.get("dg_sessions_with_data") or 0)
        kg_empty = int(graph_summary.get("kg_sessions_empty") or 0)
        dg_empty = int(graph_summary.get("dg_sessions_empty") or 0)
        kg_avg_entities = self._safe_float(graph_summary.get("kg_avg_total_entities"))
        dg_avg_nodes = self._safe_float(graph_summary.get("dg_avg_total_nodes"))
        kg_avg_gaps = self._safe_float(graph_summary.get("kg_avg_gaps"))
        kg_gap_delta = self._safe_float(graph_summary.get("kg_avg_gaps_delta_per_iter"))
        kg_entities_delta = self._safe_float(graph_summary.get("kg_avg_entities_delta_per_iter"))
        kg_relationships_delta = self._safe_float(graph_summary.get("kg_avg_relationships_delta_per_iter"))
        dg_satisfaction_rate = self._safe_float(graph_summary.get("dg_avg_satisfaction_rate"))
        kg_not_reducing = int(graph_summary.get("kg_sessions_gaps_not_reducing") or 0)

        if kg_with == 0:
            graph_signals.append("knowledge graph summaries are missing from analyzed sessions")
            graph_severity += 2
            graph_recommendations.append(
                {
                    "focus": "knowledge_graph_capture",
                    "signal": "kg_missing",
                    "recommended_action": "Ensure adversarial sessions persist knowledge-graph summaries so optimizer feedback can steer entity extraction and gap reduction.",
                }
            )
        elif kg_empty == kg_with:
            graph_signals.append("knowledge graphs are empty across analyzed sessions")
            graph_severity += 3
            graph_recommendations.append(
                {
                    "focus": "knowledge_graph_extraction",
                    "signal": "kg_empty",
                    "recommended_action": "Strengthen entity and relationship extraction so intake answers produce a usable knowledge graph before denoising or drafting.",
                }
            )
        elif kg_avg_entities is not None and kg_avg_entities < 2.0:
            graph_signals.append(f"knowledge graphs average only {kg_avg_entities:.2f} entities")
            graph_severity += 1
            graph_recommendations.append(
                {
                    "focus": "knowledge_graph_growth",
                    "signal": "kg_small",
                    "recommended_action": "Add lightweight structured extraction for dates, actors, actions, injuries, and documents so the knowledge graph is not too sparse for downstream reasoning.",
                }
            )

        if dg_with == 0:
            graph_signals.append("dependency graph summaries are missing from analyzed sessions")
            graph_severity += 2
            graph_recommendations.append(
                {
                    "focus": "dependency_graph_capture",
                    "signal": "dg_missing",
                    "recommended_action": "Ensure dependency-graph summaries are captured so missing legal elements can be targeted during denoising.",
                }
            )
        elif dg_empty == dg_with:
            graph_signals.append("dependency graphs are empty across analyzed sessions")
            graph_severity += 3
            graph_recommendations.append(
                {
                    "focus": "dependency_graph_population",
                    "signal": "dg_empty",
                    "recommended_action": "Expand claim-to-requirement modeling so dependency graphs capture missing legal elements and evidence dependencies before drafting.",
                }
            )
        elif dg_avg_nodes is not None and dg_avg_nodes < 2.0:
            graph_signals.append(f"dependency graphs average only {dg_avg_nodes:.2f} nodes")
            graph_severity += 1

        if kg_avg_gaps is not None and kg_avg_gaps >= 3.0:
            graph_signals.append(f"knowledge graphs average {kg_avg_gaps:.2f} unresolved gaps")
            graph_severity += 2
            graph_recommendations.append(
                {
                    "focus": "gap_reduction",
                    "signal": "kg_gap_count",
                    "recommended_action": "Improve denoiser gap selection and answer processing so each turn closes a concrete knowledge-graph gap instead of only restating the narrative.",
                }
            )
        if kg_not_reducing > 0 or (kg_gap_delta is not None and kg_gap_delta >= 0.0):
            graph_signals.append("knowledge-graph gaps are not reliably shrinking across iterations")
            graph_severity += 2
            graph_recommendations.append(
                {
                    "focus": "iterative_graph_updates",
                    "signal": "kg_gap_delta",
                    "recommended_action": "Make answer processing update entities, relationships, and satisfied requirements deterministically when the complainant supplies the missing field.",
                }
            )
        if kg_entities_delta is not None and kg_entities_delta < 0.1:
            graph_signals.append("knowledge-graph entity growth per iteration is low")
            graph_severity += 1
        if kg_relationships_delta is not None and kg_relationships_delta < 0.05:
            graph_signals.append("knowledge-graph relationship growth per iteration is low")
            graph_severity += 1
        if dg_satisfaction_rate is not None and dg_satisfaction_rate < 0.2:
            graph_signals.append(f"dependency satisfaction rate is only {dg_satisfaction_rate:.2f}")
            graph_severity += 2

        document_signals: List[str] = []
        document_recommendations: List[Dict[str, Any]] = []
        document_severity = 0
        uncovered_objectives = [
            str(value)
            for value in list((coverage_remediation.get("intake_priorities") or {}).get("uncovered_objectives") or [])
            if str(value)
        ]
        graph_blocker_objectives = [
            objective
            for objective in uncovered_objectives
            if objective in {"exact_dates", "staff_names_titles", "hearing_request_timing", "response_dates", "causation_sequence", "timeline", "actors"}
        ]
        if graph_blocker_objectives:
            graph_signals.append(
                "graph-blocking intake objectives remain uncovered: " + ", ".join(graph_blocker_objectives[:4])
            )
            graph_severity += 2
            graph_recommendations.append(
                {
                    "focus": "blocker_closure",
                    "signal": "intake_graph_blockers",
                    "recommended_action": "Promote exact dates, staff names/titles, hearing-request timing, response dates, and causation sequencing into graph updates before broadening the next question set.",
                }
            )
        if "documents" in uncovered_objectives:
            document_signals.append("document-focused intake objectives are still uncovered")
            document_severity += 2
            document_recommendations.append(
                {
                    "focus": "exhibit_collection",
                    "signal": "documents_objective",
                    "recommended_action": "Carry early document-request prompts into drafting handoff so exhibits, notices, grievances, and emails are reflected in the complaint package.",
                }
            )
        if "harm_remedy" in uncovered_objectives:
            document_signals.append("harm/remedy objectives are still uncovered")
            document_severity += 1
            document_recommendations.append(
                {
                    "focus": "requested_relief",
                    "signal": "harm_remedy_objective",
                    "recommended_action": "Strengthen the handoff from intake to requested-relief generation so the draft captures both the injury and the remedy sought.",
                }
            )
        if any(
            objective in {"staff_names_titles", "hearing_request_timing", "response_dates", "causation_sequence"}
            for objective in uncovered_objectives
        ):
            document_signals.append("drafting still lacks chronology, staff-identity, or causation-sequence details needed for pleading-ready allegations")
            document_severity += 1
            document_recommendations.append(
                {
                    "focus": "pleading_anchors",
                    "signal": "intake_blocker_handoff",
                    "recommended_action": "Carry blocker-closing intake answers directly into factual allegations, claim support, and exhibit descriptions so drafted complaints preserve timing, actor identity, and causation sequence.",
                }
            )
        if information_extraction_avg < 0.7:
            document_signals.append(f"information extraction average is {information_extraction_avg:.2f}")
            document_severity += 2 if information_extraction_avg < 0.6 else 1
            document_recommendations.append(
                {
                    "focus": "drafting_handoff",
                    "signal": "information_extraction",
                    "recommended_action": "Promote structured intake facts, anchors, and evidence references directly into summary-of-facts and claim-support generation before document optimization runs.",
                }
            )
        if coverage_avg < 0.7:
            document_signals.append(f"overall coverage average is {coverage_avg:.2f}")
            document_severity += 1
        if graph_severity > 0:
            document_signals.append("drafting depends on stronger graph and denoising handoffs")
            document_severity += 1
            document_recommendations.append(
                {
                    "focus": "graph_to_document_handoff",
                    "signal": "graph_dependency",
                    "recommended_action": "Gate document generation on graph completeness signals and surface unresolved factual or legal gaps in drafting readiness before formalization.",
                }
            )
        fact_backed_ratio = self._safe_float((document_provenance_summary or {}).get("avg_fact_backed_ratio"))
        low_grounding_flag = bool((document_provenance_summary or {}).get("low_grounding_flag"))
        if low_grounding_flag or (fact_backed_ratio is not None and fact_backed_ratio < 0.6):
            document_signals.append(
                "draft output is not grounded enough in canonical facts or evidence-backed support rows"
            )
            document_severity += 2 if (fact_backed_ratio is not None and fact_backed_ratio < 0.4) else 1
            document_recommendations.append(
                {
                    "focus": "document_provenance_grounding",
                    "signal": "document_provenance",
                    "recommended_action": (
                        "Carry canonical fact ids, support traces, and artifact-backed support rows through drafting so the complaint text is grounded in traceable evidence."
                    ),
                }
            )
        targeted_document_elements = [
            str(name)
            for name, _count in sorted(
                dict((document_evidence_targeting_summary or {}).get("claim_element_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:2]
            if str(name)
        ]
        first_executed_document_element = str(
            (document_workflow_execution_summary or {}).get("first_targeted_claim_element") or ""
        ).strip()
        if (
            targeted_document_elements
            and first_executed_document_element
            and first_executed_document_element != targeted_document_elements[0]
        ):
            document_signals.append(
                "document execution is not starting with the highest-priority targeted legal element"
            )
            document_severity = max(document_severity + 4, intake_severity + 1)
            document_recommendations.insert(
                0,
                {
                    "focus": "document_execution_alignment",
                    "signal": "document_execution_mismatch",
                    "recommended_action": (
                        "Make the drafting loop prioritize "
                        + targeted_document_elements[0]
                        + " before "
                        + first_executed_document_element
                        + " when selecting focus sections and support rows."
                    ),
                }
            )

        phases = {
            "intake_questioning": {
                "status": self._phase_status(intake_severity),
                "severity": intake_severity,
                "summary": "Improve complainant and mediator questioning so intake exits with stronger factual, evidentiary, and anchor coverage.",
                "signals": self._dedupe_text(intake_signals),
                "recommended_actions": intake_recommendations[:4],
                "target_files": [
                    "adversarial_harness/session.py",
                    "mediator/mediator.py",
                    "adversarial_harness/complainant.py",
                ],
            },
            "graph_analysis": {
                "status": self._phase_status(graph_severity),
                "severity": graph_severity,
                "summary": "Improve knowledge-graph and dependency-graph population so denoising and legal reasoning operate on structured facts instead of raw narrative alone.",
                "signals": self._dedupe_text(graph_signals),
                "recommended_actions": graph_recommendations[:4],
                "target_files": [
                    "complaint_phases/knowledge_graph.py",
                    "complaint_phases/dependency_graph.py",
                    "complaint_phases/denoiser.py",
                    "complaint_phases/intake_case_file.py",
                ],
            },
            "document_generation": {
                "status": self._phase_status(document_severity),
                "severity": document_severity,
                "summary": "Improve drafting handoff so complaint generation reflects the collected facts, exhibits, and unresolved gaps at formalization time.",
                "signals": self._dedupe_text(document_signals),
                "recommended_actions": document_recommendations[:4],
                "target_files": [
                    "document_pipeline.py",
                    "document_optimization.py",
                    "scripts/synthesize_hacc_complaint.py",
                    "mediator/formal_document.py",
                ],
            },
        }

        ordered_names = [
            name
            for name, _payload in sorted(
                phases.items(),
                key=lambda item: (-int(item[1].get("severity") or 0), item[0]),
            )
        ]
        for priority, name in enumerate(ordered_names, start=1):
            phases[name]["priority"] = priority
            phases[name].pop("severity", None)

        return build_workflow_phase_plan(
            phases,
            status_rank={"critical": 0, "warning": 1, "ready": 2},
        )

    @staticmethod
    def _workflow_phase_capabilities(phase_name: str) -> List[str]:
        capabilities = {
            "intake_questioning": [
                "complainant_prompting",
                "mediator_question_ordering",
                "intake_priority_coverage",
                "anchor_section_coverage",
            ],
            "graph_analysis": [
                "knowledge_graph_population",
                "dependency_graph_population",
                "gap_reduction",
                "timeline_and_proof_modeling",
            ],
            "document_generation": [
                "drafting_readiness",
                "document_optimization",
                "complaint_synthesis",
                "evidence_to_exhibit_handoff",
            ],
        }
        return list(capabilities.get(str(phase_name), []))

    @staticmethod
    def _workflow_phase_constraints(
        phase_name: str,
        target_paths: List[Path],
        report: Optional[OptimizationReport] = None,
    ) -> Dict[str, Any]:
        target_map: Dict[str, List[str]] = {}
        intake_targeting_summary = dict(report.intake_targeting_summary or {}) if report else {}
        graph_targeting_summary = dict(report.graph_element_targeting_summary or {}) if report else {}
        document_targeting_summary = dict(report.document_evidence_targeting_summary or {}) if report else {}
        intake_targeted_elements = {
            str(name)
            for name in dict(intake_targeting_summary.get("claim_element_counts") or {}).keys()
            if str(name)
        }
        intake_focus_areas = {
            str(name)
            for name in dict(intake_targeting_summary.get("focus_area_counts") or {}).keys()
            if str(name)
        }
        graph_targeted_elements = {
            str(name)
            for name in dict(graph_targeting_summary.get("claim_element_counts") or {}).keys()
            if str(name)
        }
        graph_focus_areas = {
            str(name)
            for name in dict(graph_targeting_summary.get("focus_area_counts") or {}).keys()
            if str(name)
        }
        targeted_focus_sections = {
            str(item.get("focus_section") or "").strip()
            for item in list(document_targeting_summary.get("targets") or [])
            if isinstance(item, dict) and str(item.get("focus_section") or "").strip()
        }
        targeted_support_kinds = {
            str(name)
            for name in dict(document_targeting_summary.get("support_kind_counts") or {}).keys()
            if str(name)
        }
        for path in target_paths:
            key = path.as_posix()
            if str(phase_name) == "intake_questioning":
                if path.name == "session.py":
                    target_map[key] = [
                        "_inject_intake_prompt_questions",
                    ]
                elif path.name == "mediator.py":
                    target_map[key] = [
                        "build_inquiry_gap_context",
                    ]
                elif path.name == "complainant.py":
                    target_map[key] = [
                        "_build_actor_critic_guidance",
                    ]
            elif str(phase_name) == "graph_analysis":
                if path.name == "knowledge_graph.py":
                    target_map[key] = [
                        "build_from_text",
                        "_extract_entities",
                        "_extract_relationships",
                    ]
                    if {"chronology", "timeline", "actors"} & graph_focus_areas:
                        target_map[key].append("_detect_claim_types")
                elif path.name == "dependency_graph.py":
                    target_map[key] = [
                        "get_claim_readiness",
                    ]
                    if graph_targeted_elements:
                        target_map[key].append("build_from_claims")
                elif path.name == "denoiser.py":
                    target_map[key] = [
                        "process_answer",
                    ]
                    if graph_targeted_elements:
                        target_map[key].extend(
                            [
                                "collect_question_candidates",
                                "generate_questions",
                            ]
                        )
                elif path.name == "intake_case_file.py":
                    target_map[key] = [
                        "build_intake_case_file",
                        "build_timeline_consistency_summary",
                        "build_open_items",
                    ]
                    if {"chronology", "timeline", "actors"} & graph_focus_areas:
                        target_map[key].append("build_intake_sections")
            elif str(phase_name) == "document_generation":
                if path.name == "document_pipeline.py":
                    target_map[key] = [
                        "build_package",
                        "_build_runtime_workflow_phase_plan",
                        "_build_drafting_readiness",
                    ]
                    if targeted_focus_sections:
                        target_map[key].append("_build_runtime_workflow_optimization_guidance")
                elif path.name == "document_optimization.py":
                    target_map[key] = [
                        "_build_workflow_phase_targeting",
                    ]
                    if targeted_support_kinds:
                        target_map[key].extend(
                            [
                                "_select_support_context",
                                "_build_document_evidence_targeting_summary",
                            ]
                        )
                elif path.name == "synthesize_hacc_complaint.py":
                    target_map[key] = [
                        "_merge_seed_with_grounding",
                    ]
                    if "factual_allegations" in targeted_focus_sections:
                        target_map[key].append("_factual_background")
                elif path.name == "formal_document.py":
                    target_map[key] = [
                        "ComplaintDocumentBuilder",
                    ]
        if not target_map:
            return {}
        return {
            "target_symbols": target_map,
            "workflow_phase": str(phase_name),
            "preserve_interfaces": True,
        }

    @staticmethod
    def _select_workflow_phase_targets(
        phase_name: str,
        phase_payload: Dict[str, Any],
        report: OptimizationReport,
        *,
        max_targets: int = 1,
    ) -> List[Path]:
        target_paths = [Path(path) for path in list(phase_payload.get("target_files") or [])]
        if not target_paths:
            return []

        uncovered_objectives = {
            str(value)
            for value in list((report.coverage_remediation or {}).get("intake_priorities", {}).get("uncovered_objectives") or [])
            if str(value)
        }
        blocker_objectives = uncovered_objectives.intersection(
            {"exact_dates", "staff_names_titles", "hearing_request_timing", "response_dates", "causation_sequence"}
        )

        if str(phase_name) == "graph_analysis":
            targeting_summary = dict(report.graph_element_targeting_summary or {})
            targeted_elements = {
                str(name)
                for name in dict(targeting_summary.get("claim_element_counts") or {}).keys()
                if str(name)
            }
            targeted_focus_areas = {
                str(name)
                for name in dict(targeting_summary.get("focus_area_counts") or {}).keys()
                if str(name)
            }
            priorities: List[str] = []
            kg_empty = int(report.kg_sessions_empty or 0) > 0 or float(report.kg_avg_total_entities or 0.0) <= 2.0
            dg_weak = float(report.dg_avg_satisfaction_rate or 0.0) < 0.5
            gaps_high = float(report.kg_avg_gaps or 0.0) >= 1.0 or int(report.kg_sessions_gaps_not_reducing or 0) > 0

            if targeted_elements:
                priorities.extend(["denoiser.py", "dependency_graph.py"])
            if {"chronology", "timeline", "actors"} & targeted_focus_areas:
                priorities.extend(["intake_case_file.py", "knowledge_graph.py"])
            if blocker_objectives:
                priorities.extend(["dependency_graph.py", "denoiser.py", "knowledge_graph.py"])

            if dg_weak:
                priorities.append("dependency_graph.py")
            if gaps_high:
                priorities.append("denoiser.py")
            if kg_empty:
                priorities.append("knowledge_graph.py")
            priorities.append("intake_case_file.py")
            priorities.extend(["dependency_graph.py", "denoiser.py", "knowledge_graph.py", "intake_case_file.py"])

            selected: List[Path] = []
            seen = set()
            for name in priorities:
                for path in target_paths:
                    if path.name == name and path.name not in seen:
                        seen.add(path.name)
                        selected.append(path)
                        break
                if len(selected) >= max(1, int(max_targets or 1)):
                    break
            return selected or target_paths[: max(1, int(max_targets or 1))]

        if str(phase_name) == "document_generation":
            targeting_summary = dict(report.document_evidence_targeting_summary or {})
            targeted_focus_sections = {
                str(item.get("focus_section") or "").strip()
                for item in list(targeting_summary.get("targets") or [])
                if isinstance(item, dict) and str(item.get("focus_section") or "").strip()
            }
            targeted_support_kinds = {
                str(name)
                for name in dict(targeting_summary.get("support_kind_counts") or {}).keys()
                if str(name)
            }
            priorities: List[str] = []
            if targeted_support_kinds:
                priorities.append("document_optimization.py")
            if "factual_allegations" in targeted_focus_sections:
                priorities.append("synthesize_hacc_complaint.py")
            if "claims_for_relief" in targeted_focus_sections:
                priorities.append("formal_document.py")
            if blocker_objectives:
                priorities.extend(["document_optimization.py", "synthesize_hacc_complaint.py", "formal_document.py", "document_pipeline.py"])
            else:
                priorities.extend(
                    [
                        "document_optimization.py",
                        "synthesize_hacc_complaint.py",
                        "document_pipeline.py",
                        "formal_document.py",
                    ]
                )
            selected: List[Path] = []
            seen = set()
            for name in priorities:
                for path in target_paths:
                    if path.name == name and path.name not in seen:
                        seen.add(path.name)
                        selected.append(path)
                        break
                if len(selected) >= max(1, int(max_targets or 1)):
                    break
            return selected or target_paths[: max(1, int(max_targets or 1))]

        if str(phase_name) == "intake_questioning":
            if int(report.num_sessions_analyzed or 0) == 0:
                for path in target_paths:
                    if path.name == "session.py":
                        return [path]
                return target_paths[:1]
            targeting_summary = dict(report.intake_targeting_summary or {})
            targeted_elements = {
                str(name)
                for name in dict(targeting_summary.get("claim_element_counts") or {}).keys()
                if str(name)
            }
            targeted_focus_areas = {
                str(name)
                for name in dict(targeting_summary.get("focus_area_counts") or {}).keys()
                if str(name)
            }
            priorities = (
                ["session.py", "mediator.py", "complainant.py"]
                if blocker_objectives
                else [
                    "session.py",
                    "complainant.py",
                    "mediator.py",
                ]
            )
            if targeted_elements:
                priorities = ["mediator.py", *priorities]
            if {"timeline", "chronology", "proof_leads"} & targeted_focus_areas:
                priorities = ["session.py", "mediator.py", *priorities]
            if {"actors", "harm_remedy"} & targeted_focus_areas:
                priorities = ["complainant.py", *priorities]
            selected: List[Path] = []
            seen = set()
            for name in priorities:
                for path in target_paths:
                    if path.name == name and path.name not in seen:
                        seen.add(path.name)
                        selected.append(path)
                        break
                if len(selected) >= max(1, int(max_targets or 1)):
                    break
            return selected or target_paths[: max(1, int(max_targets or 1))]

        return target_paths

    @staticmethod
    def _build_generalization_summary(
        performance: Dict[str, Dict[str, Any]],
        baseline_score: float,
    ) -> Dict[str, Any]:
        normalized = {
            str(name): dict(payload or {})
            for name, payload in (performance or {}).items()
            if str(name)
        }
        if not normalized:
            return {
                "count": 0,
                "weakest": [],
                "strongest": [],
                "score_spread": 0.0,
                "below_baseline_count": 0,
            }

        ranked = sorted(
            normalized.items(),
            key=lambda item: (
                float(item[1].get("average_score") or 0.0),
                int(item[1].get("count") or 0),
                item[0],
            ),
        )
        weakest = [
            {
                "name": name,
                "average_score": float(payload.get("average_score") or 0.0),
                "count": int(payload.get("count") or 0),
            }
            for name, payload in ranked[:3]
        ]
        strongest = [
            {
                "name": name,
                "average_score": float(payload.get("average_score") or 0.0),
                "count": int(payload.get("count") or 0),
            }
            for name, payload in sorted(
                normalized.items(),
                key=lambda item: (
                    float(item[1].get("average_score") or 0.0),
                    int(item[1].get("count") or 0),
                    item[0],
                ),
                reverse=True,
            )[:3]
        ]
        scores = [float(payload.get("average_score") or 0.0) for payload in normalized.values()]
        below_baseline_count = sum(1 for score in scores if score < float(baseline_score or 0.0))
        return {
            "count": len(normalized),
            "weakest": weakest,
            "strongest": strongest,
            "score_spread": (max(scores) - min(scores)) if scores else 0.0,
            "below_baseline_count": below_baseline_count,
        }

    @staticmethod
    def _build_document_handoff_summary(
        *,
        coverage_remediation: Dict[str, Any],
        workflow_phase_plan: Dict[str, Any],
        complaint_type_summary: Dict[str, Any],
        evidence_modality_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        intake_priorities = dict((coverage_remediation or {}).get("intake_priorities") or {})
        uncovered_objectives = [
            str(value)
            for value in list(intake_priorities.get("uncovered_objectives") or [])
            if str(value)
        ]
        workflow_phases = dict((workflow_phase_plan or {}).get("phases") or {})
        graph_phase = dict(workflow_phases.get("graph_analysis") or {})
        document_phase = dict(workflow_phases.get("document_generation") or {})
        blockers = []
        if uncovered_objectives:
            blockers.append("uncovered_intake_objectives")
        if str(graph_phase.get("status") or "ready") != "ready":
            blockers.append("graph_analysis_not_ready")
        if str(document_phase.get("status") or "ready") != "ready":
            blockers.append("document_generation_not_ready")
        if int((complaint_type_summary or {}).get("below_baseline_count") or 0) > 0:
            blockers.append("complaint_type_generalization_gaps")
        if int((evidence_modality_summary or {}).get("below_baseline_count") or 0) > 0:
            blockers.append("evidence_modality_generalization_gaps")
        return {
            "unresolved_intake_objectives": uncovered_objectives,
            "graph_dependency_status": str(graph_phase.get("status") or "ready"),
            "document_generation_status": str(document_phase.get("status") or "ready"),
            "complaint_type_gap_count": int((complaint_type_summary or {}).get("below_baseline_count") or 0),
            "evidence_modality_gap_count": int((evidence_modality_summary or {}).get("below_baseline_count") or 0),
            "blockers": blockers,
            "ready_for_document_optimization": not blockers,
        }

    @staticmethod
    def _build_document_evidence_targeting_summary(successful_results: List[Any]) -> Dict[str, Any]:
        focus_section_counts: Dict[str, int] = {}
        claim_type_counts: Dict[str, int] = {}
        claim_element_counts: Dict[str, int] = {}
        support_kind_counts: Dict[str, int] = {}
        targets: List[Dict[str, Any]] = []

        for result in successful_results:
            final_state = result.final_state if isinstance(getattr(result, "final_state", None), dict) else {}
            workflow_guidance = (
                final_state.get("workflow_optimization_guidance")
                if isinstance(final_state.get("workflow_optimization_guidance"), dict)
                else {}
            )
            targeting_summary = (
                workflow_guidance.get("document_evidence_targeting_summary")
                if isinstance(workflow_guidance.get("document_evidence_targeting_summary"), dict)
                else final_state.get("document_evidence_targeting_summary")
                if isinstance(final_state.get("document_evidence_targeting_summary"), dict)
                else {}
            )
            for item in list(targeting_summary.get("targets") or []):
                if not isinstance(item, dict):
                    continue
                focus_section = str(item.get("focus_section") or "").strip()
                claim_type = str(item.get("claim_type") or "").strip()
                claim_element_id = str(item.get("claim_element_id") or "").strip()
                support_kind = str(item.get("preferred_support_kind") or "").strip()
                text = str(item.get("text") or "").strip()
                kind = str(item.get("kind") or "").strip()
                if not any((focus_section, claim_type, claim_element_id, support_kind, text)):
                    continue
                if focus_section:
                    focus_section_counts[focus_section] = focus_section_counts.get(focus_section, 0) + 1
                if claim_type:
                    claim_type_counts[claim_type] = claim_type_counts.get(claim_type, 0) + 1
                if claim_element_id:
                    claim_element_counts[claim_element_id] = claim_element_counts.get(claim_element_id, 0) + 1
                if support_kind:
                    support_kind_counts[support_kind] = support_kind_counts.get(support_kind, 0) + 1
                targets.append(
                    {
                        "focus_section": focus_section,
                        "claim_type": claim_type,
                        "claim_element_id": claim_element_id,
                        "preferred_support_kind": support_kind,
                        "kind": kind,
                        "text": text,
                    }
                )

        return {
            "count": len(targets),
            "focus_section_counts": focus_section_counts,
            "claim_type_counts": claim_type_counts,
            "claim_element_counts": claim_element_counts,
            "support_kind_counts": support_kind_counts,
            "targets": targets[:10],
        }

    @staticmethod
    def _build_document_provenance_summary(successful_results: List[Any]) -> Dict[str, Any]:
        summaries: List[Dict[str, Any]] = []
        for result in successful_results:
            final_state = result.final_state if isinstance(getattr(result, "final_state", None), dict) else {}
            workflow_guidance = (
                final_state.get("workflow_optimization_guidance")
                if isinstance(final_state.get("workflow_optimization_guidance"), dict)
                else {}
            )
            provenance_summary = (
                workflow_guidance.get("document_provenance_summary")
                if isinstance(workflow_guidance.get("document_provenance_summary"), dict)
                else final_state.get("document_provenance_summary")
                if isinstance(final_state.get("document_provenance_summary"), dict)
                else {}
            )
            if isinstance(provenance_summary, dict) and provenance_summary:
                summaries.append(provenance_summary)

        if not summaries:
            return {
                "count": 0,
                "sessions_with_summary": 0,
                "avg_fact_backed_ratio": 0.0,
                "avg_summary_fact_backed_ratio": 0.0,
                "avg_factual_allegation_fact_backed_ratio": 0.0,
                "avg_claim_supporting_fact_backed_ratio": 0.0,
                "low_grounding_session_count": 0,
                "low_grounding_flag": False,
            }

        def _ratio(summary: Dict[str, Any], numerator_key: str, denominator_key: str) -> float:
            denominator = int(summary.get(denominator_key) or 0)
            if denominator <= 0:
                return 0.0
            return float(int(summary.get(numerator_key) or 0)) / float(denominator)

        summary_ratios = [_ratio(summary, "summary_fact_backed_count", "summary_fact_count") for summary in summaries]
        allegation_ratios = [
            _ratio(summary, "factual_allegation_fact_backed_count", "factual_allegation_paragraph_count")
            for summary in summaries
        ]
        claim_ratios = [
            _ratio(summary, "claim_supporting_fact_backed_count", "claim_supporting_fact_count")
            for summary in summaries
        ]
        combined_ratios = [
            (summary_ratios[index] + allegation_ratios[index] + claim_ratios[index]) / 3.0
            for index in range(len(summaries))
        ]
        low_grounding_session_count = sum(1 for ratio in combined_ratios if ratio < 0.6)
        return {
            "count": len(summaries),
            "sessions_with_summary": len(summaries),
            "avg_fact_backed_ratio": round(sum(combined_ratios) / len(combined_ratios), 4),
            "avg_summary_fact_backed_ratio": round(sum(summary_ratios) / len(summary_ratios), 4),
            "avg_factual_allegation_fact_backed_ratio": round(sum(allegation_ratios) / len(allegation_ratios), 4),
            "avg_claim_supporting_fact_backed_ratio": round(sum(claim_ratios) / len(claim_ratios), 4),
            "low_grounding_session_count": low_grounding_session_count,
            "low_grounding_flag": bool(low_grounding_session_count),
        }

    @staticmethod
    def _build_document_grounding_improvement_summary(successful_results: List[Any]) -> Dict[str, Any]:
        summaries: List[Dict[str, Any]] = []
        for result in successful_results:
            final_state = result.final_state if isinstance(getattr(result, "final_state", None), dict) else {}
            workflow_guidance = (
                final_state.get("workflow_optimization_guidance")
                if isinstance(final_state.get("workflow_optimization_guidance"), dict)
                else {}
            )
            improvement_summary = (
                workflow_guidance.get("document_grounding_improvement_summary")
                if isinstance(workflow_guidance.get("document_grounding_improvement_summary"), dict)
                else final_state.get("document_grounding_improvement_summary")
                if isinstance(final_state.get("document_grounding_improvement_summary"), dict)
                else {}
            )
            if isinstance(improvement_summary, dict) and improvement_summary:
                summaries.append(improvement_summary)

        if not summaries:
            return {
                "count": 0,
                "sessions_with_summary": 0,
                "avg_initial_fact_backed_ratio": 0.0,
                "avg_final_fact_backed_ratio": 0.0,
                "avg_fact_backed_ratio_delta": 0.0,
                "improved_session_count": 0,
                "regressed_session_count": 0,
                "stalled_session_count": 0,
                "recovery_attempted_session_count": 0,
                "low_grounding_resolved_session_count": 0,
                "improved_flag": False,
            }

        initial_ratios = [float(summary.get("initial_fact_backed_ratio") or 0.0) for summary in summaries]
        final_ratios = [float(summary.get("final_fact_backed_ratio") or 0.0) for summary in summaries]
        deltas = [float(summary.get("fact_backed_ratio_delta") or 0.0) for summary in summaries]
        improved_session_count = sum(1 for summary in summaries if bool(summary.get("improved_flag")))
        regressed_session_count = sum(1 for summary in summaries if bool(summary.get("regressed_flag")))
        stalled_session_count = sum(1 for summary in summaries if bool(summary.get("stalled_flag")))
        recovery_attempted_session_count = sum(
            1 for summary in summaries if bool(summary.get("recovery_attempted_flag"))
        )
        low_grounding_resolved_session_count = sum(
            1 for summary in summaries if bool(summary.get("low_grounding_resolved_flag"))
        )
        return {
            "count": len(summaries),
            "sessions_with_summary": len(summaries),
            "avg_initial_fact_backed_ratio": round(sum(initial_ratios) / len(initial_ratios), 4),
            "avg_final_fact_backed_ratio": round(sum(final_ratios) / len(final_ratios), 4),
            "avg_fact_backed_ratio_delta": round(sum(deltas) / len(deltas), 4),
            "improved_session_count": improved_session_count,
            "regressed_session_count": regressed_session_count,
            "stalled_session_count": stalled_session_count,
            "recovery_attempted_session_count": recovery_attempted_session_count,
            "low_grounding_resolved_session_count": low_grounding_resolved_session_count,
            "improved_flag": improved_session_count > regressed_session_count,
        }

    @staticmethod
    def _build_document_workflow_execution_summary(successful_results: List[Any]) -> Dict[str, Any]:
        focus_section_counts: Dict[str, int] = {}
        top_support_kind_counts: Dict[str, int] = {}
        targeted_claim_element_counts: Dict[str, int] = {}
        preferred_support_kind_counts: Dict[str, int] = {}
        first_focus_section = ""
        first_top_support_kind = ""
        first_targeted_claim_element = ""
        first_preferred_support_kind = ""
        iteration_count = 0
        accepted_iteration_count = 0

        for result in successful_results:
            final_state = result.final_state if isinstance(getattr(result, "final_state", None), dict) else {}
            workflow_guidance = (
                final_state.get("workflow_optimization_guidance")
                if isinstance(final_state.get("workflow_optimization_guidance"), dict)
                else {}
            )
            execution_summary = (
                workflow_guidance.get("document_workflow_execution_summary")
                if isinstance(workflow_guidance.get("document_workflow_execution_summary"), dict)
                else final_state.get("document_workflow_execution_summary")
                if isinstance(final_state.get("document_workflow_execution_summary"), dict)
                else {}
            )
            iteration_count += int(execution_summary.get("iteration_count") or 0)
            accepted_iteration_count += int(execution_summary.get("accepted_iteration_count") or 0)
            for name, count in dict(execution_summary.get("focus_section_counts") or {}).items():
                normalized = str(name or "").strip()
                if normalized:
                    focus_section_counts[normalized] = focus_section_counts.get(normalized, 0) + int(count or 0)
            for name, count in dict(execution_summary.get("top_support_kind_counts") or {}).items():
                normalized = str(name or "").strip()
                if normalized:
                    top_support_kind_counts[normalized] = top_support_kind_counts.get(normalized, 0) + int(count or 0)
            for name, count in dict(execution_summary.get("targeted_claim_element_counts") or {}).items():
                normalized = str(name or "").strip()
                if normalized:
                    targeted_claim_element_counts[normalized] = targeted_claim_element_counts.get(normalized, 0) + int(count or 0)
            for name, count in dict(execution_summary.get("preferred_support_kind_counts") or {}).items():
                normalized = str(name or "").strip()
                if normalized:
                    preferred_support_kind_counts[normalized] = preferred_support_kind_counts.get(normalized, 0) + int(count or 0)
            if not first_focus_section:
                first_focus_section = str(execution_summary.get("first_focus_section") or "").strip()
            if not first_top_support_kind:
                first_top_support_kind = str(execution_summary.get("first_top_support_kind") or "").strip()
            if not first_targeted_claim_element:
                first_targeted_claim_element = str(execution_summary.get("first_targeted_claim_element") or "").strip()
            if not first_preferred_support_kind:
                first_preferred_support_kind = str(execution_summary.get("first_preferred_support_kind") or "").strip()

        return {
            "iteration_count": iteration_count,
            "accepted_iteration_count": accepted_iteration_count,
            "focus_section_counts": focus_section_counts,
            "top_support_kind_counts": top_support_kind_counts,
            "targeted_claim_element_counts": targeted_claim_element_counts,
            "preferred_support_kind_counts": preferred_support_kind_counts,
            "first_focus_section": first_focus_section,
            "first_top_support_kind": first_top_support_kind,
            "first_targeted_claim_element": first_targeted_claim_element,
            "first_preferred_support_kind": first_preferred_support_kind,
        }

    @staticmethod
    def _build_document_execution_drift_summary(
        *,
        document_evidence_targeting_summary: Dict[str, Any],
        document_workflow_execution_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        targeted_counts = (
            document_evidence_targeting_summary.get("claim_element_counts")
            if isinstance(document_evidence_targeting_summary.get("claim_element_counts"), dict)
            else {}
        )
        top_targeted_claim_element = ""
        top_targeted_claim_element_count = 0
        if targeted_counts:
            top_targeted_claim_element, top_targeted_claim_element_count = sorted(
                (
                    (str(name or "").strip(), int(count or 0))
                    for name, count in targeted_counts.items()
                    if str(name or "").strip()
                ),
                key=lambda item: (-item[1], item[0]),
            )[0]
        first_executed_claim_element = str(
            document_workflow_execution_summary.get("first_targeted_claim_element") or ""
        ).strip()
        return {
            "drift_flag": bool(
                top_targeted_claim_element
                and first_executed_claim_element
                and top_targeted_claim_element != first_executed_claim_element
            ),
            "top_targeted_claim_element": top_targeted_claim_element,
            "top_targeted_claim_element_count": top_targeted_claim_element_count,
            "first_executed_claim_element": first_executed_claim_element,
            "first_focus_section": str(document_workflow_execution_summary.get("first_focus_section") or "").strip(),
            "first_preferred_support_kind": str(
                document_workflow_execution_summary.get("first_preferred_support_kind") or ""
            ).strip(),
            "iteration_count": int(document_workflow_execution_summary.get("iteration_count") or 0),
            "accepted_iteration_count": int(document_workflow_execution_summary.get("accepted_iteration_count") or 0),
        }

    @staticmethod
    def _build_graph_element_targeting_summary(successful_results: List[Any]) -> Dict[str, Any]:
        claim_type_counts: Dict[str, int] = {}
        claim_element_counts: Dict[str, int] = {}
        focus_area_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        targets: List[Dict[str, Any]] = []

        def add_target(*, source: str, claim_type: str, claim_element_id: str, focus_areas: List[str], text: str) -> None:
            normalized_claim_type = str(claim_type or "").strip()
            normalized_element = str(claim_element_id or "").strip()
            normalized_focus_areas = [str(item).strip() for item in focus_areas if str(item).strip()]
            normalized_text = str(text or "").strip()
            if not any((normalized_claim_type, normalized_element, normalized_focus_areas, normalized_text)):
                return
            source_counts[source] = source_counts.get(source, 0) + 1
            if normalized_claim_type:
                claim_type_counts[normalized_claim_type] = claim_type_counts.get(normalized_claim_type, 0) + 1
            if normalized_element:
                claim_element_counts[normalized_element] = claim_element_counts.get(normalized_element, 0) + 1
            for focus_area in normalized_focus_areas:
                focus_area_counts[focus_area] = focus_area_counts.get(focus_area, 0) + 1
            targets.append(
                {
                    "source": source,
                    "claim_type": normalized_claim_type,
                    "claim_element_id": normalized_element,
                    "focus_areas": normalized_focus_areas,
                    "text": normalized_text,
                }
            )

        for result in successful_results:
            final_state = result.final_state if isinstance(getattr(result, "final_state", None), dict) else {}

            for action in list(final_state.get("evidence_workflow_action_queue") or []):
                if not isinstance(action, dict):
                    continue
                add_target(
                    source="evidence_workflow_action",
                    claim_type=str(action.get("claim_type") or ""),
                    claim_element_id=str(action.get("claim_element_id") or ""),
                    focus_areas=list(action.get("focus_areas") or []),
                    text=str(action.get("action") or ""),
                )

            for task in list(final_state.get("alignment_evidence_tasks") or []):
                if not isinstance(task, dict):
                    continue
                add_target(
                    source="alignment_evidence_task",
                    claim_type=str(task.get("claim_type") or ""),
                    claim_element_id=str(task.get("claim_element_id") or ""),
                    focus_areas=list(task.get("fallback_lanes") or []),
                    text=str(task.get("action") or ""),
                )

            legal_targeting = final_state.get("intake_legal_targeting_summary")
            if isinstance(legal_targeting, dict):
                for claim_type, payload in dict(legal_targeting.get("claims") or {}).items():
                    if not isinstance(payload, dict):
                        continue
                    for element_id in list(payload.get("missing_requirement_element_ids") or []):
                        add_target(
                            source="intake_legal_targeting",
                            claim_type=str(claim_type or ""),
                            claim_element_id=str(element_id or ""),
                            focus_areas=["claim_elements"],
                            text=f"Unresolved legal requirement for {claim_type}",
                        )

        return {
            "count": len(targets),
            "claim_type_counts": claim_type_counts,
            "claim_element_counts": claim_element_counts,
            "focus_area_counts": focus_area_counts,
            "source_counts": source_counts,
            "targets": targets[:12],
        }

    @staticmethod
    def _build_intake_targeting_summary(successful_results: List[Any]) -> Dict[str, Any]:
        objective_counts: Dict[str, int] = {}
        claim_element_counts: Dict[str, int] = {}
        focus_area_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        targets: List[Dict[str, Any]] = []

        def add_target(*, source: str, objective: str, claim_element_id: str, focus_areas: List[str], text: str) -> None:
            normalized_objective = str(objective or "").strip()
            normalized_element = str(claim_element_id or "").strip()
            normalized_focus_areas = [str(item).strip() for item in focus_areas if str(item).strip()]
            normalized_text = str(text or "").strip()
            if not any((normalized_objective, normalized_element, normalized_focus_areas, normalized_text)):
                return
            source_counts[source] = source_counts.get(source, 0) + 1
            if normalized_objective:
                objective_counts[normalized_objective] = objective_counts.get(normalized_objective, 0) + 1
            if normalized_element:
                claim_element_counts[normalized_element] = claim_element_counts.get(normalized_element, 0) + 1
            for focus_area in normalized_focus_areas:
                focus_area_counts[focus_area] = focus_area_counts.get(focus_area, 0) + 1
            targets.append(
                {
                    "source": source,
                    "objective": normalized_objective,
                    "claim_element_id": normalized_element,
                    "focus_areas": normalized_focus_areas,
                    "text": normalized_text,
                }
            )

        for result in successful_results:
            final_state = result.final_state if isinstance(getattr(result, "final_state", None), dict) else {}

            intake_priority_summary = final_state.get("adversarial_intake_priority_summary")
            if isinstance(intake_priority_summary, dict):
                for objective in list(intake_priority_summary.get("uncovered_objectives") or []):
                    add_target(
                        source="intake_priority",
                        objective=str(objective or ""),
                        claim_element_id="",
                        focus_areas=["intake_priorities"],
                        text=f"Uncovered intake objective: {objective}",
                    )

            for action in list(final_state.get("intake_workflow_action_queue") or []):
                if not isinstance(action, dict):
                    continue
                focus_areas = list(action.get("focus_areas") or [])
                objective = focus_areas[0] if focus_areas else ""
                add_target(
                    source="intake_workflow_action",
                    objective=str(objective or ""),
                    claim_element_id=str(action.get("target_element_id") or ""),
                    focus_areas=focus_areas,
                    text=str(action.get("action") or ""),
                )

            legal_targeting = final_state.get("intake_legal_targeting_summary")
            if isinstance(legal_targeting, dict):
                for _claim_type, payload in dict(legal_targeting.get("claims") or {}).items():
                    if not isinstance(payload, dict):
                        continue
                    for element_id in list(payload.get("missing_requirement_element_ids") or []):
                        add_target(
                            source="intake_legal_targeting",
                            objective="claim_elements",
                            claim_element_id=str(element_id or ""),
                            focus_areas=["claim_elements"],
                            text=f"Missing intake legal element: {element_id}",
                        )

        return {
            "count": len(targets),
            "objective_counts": objective_counts,
            "claim_element_counts": claim_element_counts,
            "focus_area_counts": focus_area_counts,
            "source_counts": source_counts,
            "targets": targets[:12],
        }

    @staticmethod
    def _build_workflow_targeting_summary(
        *,
        intake_targeting_summary: Dict[str, Any],
        graph_element_targeting_summary: Dict[str, Any],
        document_evidence_targeting_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        intake = intake_targeting_summary if isinstance(intake_targeting_summary, dict) else {}
        graph = graph_element_targeting_summary if isinstance(graph_element_targeting_summary, dict) else {}
        document = (
            document_evidence_targeting_summary
            if isinstance(document_evidence_targeting_summary, dict)
            else {}
        )
        phase_summaries = {
            "intake_questioning": dict(intake),
            "graph_analysis": dict(graph),
            "document_generation": dict(document),
        }
        phase_counts = {
            phase_name: int((payload or {}).get("count") or 0)
            for phase_name, payload in phase_summaries.items()
        }
        total_target_count = sum(phase_counts.values())
        phase_order = [
            phase_name
            for phase_name, _count in sorted(
                phase_counts.items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )
            if int(phase_counts.get(phase_name) or 0) > 0
        ]

        shared_claim_elements: Dict[str, int] = {}
        for payload in phase_summaries.values():
            for claim_element_id, count in dict(payload.get("claim_element_counts") or {}).items():
                normalized = str(claim_element_id or "").strip()
                if not normalized:
                    continue
                shared_claim_elements[normalized] = shared_claim_elements.get(normalized, 0) + int(count or 0)

        shared_focus_areas: Dict[str, int] = {}
        for payload in phase_summaries.values():
            focus_counts = {}
            if "focus_area_counts" in payload:
                focus_counts = dict(payload.get("focus_area_counts") or {})
            elif "objective_counts" in payload:
                focus_counts = dict(payload.get("objective_counts") or {})
            for focus_area, count in focus_counts.items():
                normalized = str(focus_area or "").strip()
                if not normalized:
                    continue
                shared_focus_areas[normalized] = shared_focus_areas.get(normalized, 0) + int(count or 0)

        return {
            "count": total_target_count,
            "phase_counts": phase_counts,
            "prioritized_phases": phase_order,
            "shared_claim_element_counts": shared_claim_elements,
            "shared_focus_area_counts": shared_focus_areas,
            "phase_summaries": phase_summaries,
        }

    def _build_phase_scorecards(
        self,
        *,
        report: OptimizationReport,
        graph_summary: Dict[str, Any],
        intake_targeting_summary: Dict[str, Any],
        complaint_type_summary: Dict[str, Any],
        evidence_modality_summary: Dict[str, Any],
        document_handoff_summary: Dict[str, Any],
        graph_element_targeting_summary: Dict[str, Any],
        document_evidence_targeting_summary: Dict[str, Any],
        document_provenance_summary: Dict[str, Any],
        document_grounding_improvement_summary: Dict[str, Any],
        document_workflow_execution_summary: Dict[str, Any],
        document_execution_drift_summary: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        workflow_phases = dict((report.workflow_phase_plan or {}).get("phases") or {})
        weakest_objectives = self._top_uncovered_intake_objectives(report, limit=5)
        targeted_intake_objectives = [
            str(name)
            for name, _count in sorted(
                dict((intake_targeting_summary or {}).get("objective_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name)
        ]
        weakest_complaint_types = [
            str(item.get("name") or "")
            for item in list((complaint_type_summary or {}).get("weakest") or [])
            if str(item.get("name") or "")
        ]
        weakest_modalities = [
            str(item.get("name") or "")
            for item in list((evidence_modality_summary or {}).get("weakest") or [])
            if str(item.get("name") or "")
        ]
        graph_targeted_claim_elements = [
            str(name)
            for name, _count in sorted(
                dict((graph_element_targeting_summary or {}).get("claim_element_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name)
        ]
        targeted_claim_elements = [
            str(name)
            for name, _count in sorted(
                dict((document_evidence_targeting_summary or {}).get("claim_element_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name)
        ]
        executed_claim_elements = [
            str(name)
            for name, _count in sorted(
                dict((document_workflow_execution_summary or {}).get("targeted_claim_element_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name)
        ]
        first_executed_claim_element = str(
            (document_workflow_execution_summary or {}).get("first_targeted_claim_element") or ""
        ).strip()
        document_fact_backed_ratio = self._safe_float((document_provenance_summary or {}).get("avg_fact_backed_ratio")) or 0.0
        execution_mismatch_flag = bool(
            targeted_claim_elements
            and first_executed_claim_element
            and first_executed_claim_element != targeted_claim_elements[0]
        )
        kg_avg_gaps = self._safe_float((graph_summary or {}).get("kg_avg_gaps")) or 0.0
        dg_satisfaction_rate = self._safe_float((graph_summary or {}).get("dg_avg_satisfaction_rate")) or 0.0
        return {
            "intake_questioning": {
                "status": str((workflow_phases.get("intake_questioning") or {}).get("status") or "ready"),
                "score": round(
                    (float(report.question_quality_avg or 0.0) + float(report.efficiency_avg or 0.0) + float(report.coverage_avg or 0.0)) / 3.0,
                    4,
                ),
                "focus_areas": [
                    *weakest_objectives[:2],
                    *targeted_intake_objectives[:2],
                ][:3],
                "generalization_targets": weakest_complaint_types[:3],
                "evidence_targets": weakest_modalities[:3],
                "targeted_intake_objectives": targeted_intake_objectives,
            },
            "graph_analysis": {
                "status": str((workflow_phases.get("graph_analysis") or {}).get("status") or "ready"),
                "score": round(
                    (float(report.information_extraction_avg or 0.0) + max(0.0, 1.0 - min(1.0, kg_avg_gaps / 5.0)) + float(dg_satisfaction_rate or 0.0)) / 3.0,
                    4,
                ),
                "focus_areas": [
                    "gap_reduction" if kg_avg_gaps >= 1.0 else "graph_stability",
                    "dependency_satisfaction" if dg_satisfaction_rate < 0.7 else "dependency_coverage",
                ],
                "generalization_targets": weakest_complaint_types[:3],
                "evidence_targets": weakest_modalities[:3],
                "targeted_claim_elements": graph_targeted_claim_elements,
            },
            "document_generation": {
                "status": str((workflow_phases.get("document_generation") or {}).get("status") or "ready"),
                "score": round(
                    (
                        float(report.coverage_avg or 0.0)
                        + float(report.information_extraction_avg or 0.0)
                        + (1.0 if bool((document_handoff_summary or {}).get("ready_for_document_optimization")) else 0.0)
                    ) / 3.0,
                    4,
                ),
                "focus_areas": [
                    *list((document_handoff_summary or {}).get("unresolved_intake_objectives") or [])[:2],
                    *targeted_claim_elements[:2],
                ][:3],
                "generalization_targets": weakest_complaint_types[:3],
                "evidence_targets": weakest_modalities[:3],
                "targeted_claim_elements": targeted_claim_elements,
                "executed_claim_elements": executed_claim_elements,
                "first_executed_claim_element": first_executed_claim_element,
                "first_focus_section": str((document_workflow_execution_summary or {}).get("first_focus_section") or ""),
                "first_top_support_kind": str((document_workflow_execution_summary or {}).get("first_top_support_kind") or ""),
                "document_fact_backed_ratio": round(document_fact_backed_ratio, 4),
                "document_low_grounding_flag": bool((document_provenance_summary or {}).get("low_grounding_flag")),
                "document_provenance_summary": dict(document_provenance_summary or {}),
                "document_grounding_improvement_summary": dict(document_grounding_improvement_summary or {}),
                "document_grounding_improved_flag": bool((document_grounding_improvement_summary or {}).get("improved_flag")),
                "execution_mismatch_flag": execution_mismatch_flag,
                "execution_drift_summary": dict(document_execution_drift_summary or {}),
            },
        }

    @staticmethod
    def _build_cross_phase_findings(
        *,
        phase_scorecards: Dict[str, Dict[str, Any]],
        document_handoff_summary: Dict[str, Any],
    ) -> List[str]:
        findings: List[str] = []
        intake = dict((phase_scorecards or {}).get("intake_questioning") or {})
        graph = dict((phase_scorecards or {}).get("graph_analysis") or {})
        document = dict((phase_scorecards or {}).get("document_generation") or {})
        if str(intake.get("status") or "ready") != "ready" and str(graph.get("status") or "ready") != "ready":
            findings.append(
                "Intake questioning gaps are likely suppressing graph extraction quality; optimize question targeting before expanding graph heuristics further."
            )
        if str(graph.get("status") or "ready") != "ready" and str(document.get("status") or "ready") != "ready":
            findings.append(
                "Document generation is currently bottlenecked by graph-analysis readiness; improve structured fact and requirement propagation into drafting."
            )
        blockers = list((document_handoff_summary or {}).get("blockers") or [])
        if "complaint_type_generalization_gaps" in blockers or "evidence_modality_generalization_gaps" in blockers:
            findings.append(
                "Generalization gaps across complaint types or evidence modalities should be addressed across intake, graph analysis, and drafting together rather than in a single phase."
            )
        if not findings:
            findings.append(
                "Phase scorecards do not show a dominant cross-phase bottleneck; preserve the current handoff order and focus on consistency."
            )
        return findings

    @staticmethod
    def _build_workflow_action_queue(
        *,
        workflow_phase_plan: Dict[str, Any],
        phase_scorecards: Dict[str, Dict[str, Any]],
        cross_phase_findings: List[str],
    ) -> List[Dict[str, Any]]:
        phases = dict((workflow_phase_plan or {}).get("phases") or {})
        ordered_names = [
            str(name)
            for name in list((workflow_phase_plan or {}).get("recommended_order") or [])
            if str(name)
        ]
        queue: List[Dict[str, Any]] = []
        for index, phase_name in enumerate(ordered_names, start=1):
            phase_payload = dict(phases.get(phase_name) or {})
            scorecard = dict((phase_scorecards or {}).get(phase_name) or {})
            recommended_actions = [
                str((item or {}).get("recommended_action") or "").strip()
                for item in list(phase_payload.get("recommended_actions") or [])
                if isinstance(item, dict) and str((item or {}).get("recommended_action") or "").strip()
            ]
            focus_areas = [
                str(item).strip()
                for item in list(scorecard.get("focus_areas") or [])
                if str(item).strip()
            ]
            queue.append(
                {
                    "rank": index,
                    "phase_name": phase_name,
                    "status": str(phase_payload.get("status") or scorecard.get("status") or "ready"),
                    "action": recommended_actions[0] if recommended_actions else str(phase_payload.get("summary") or "").strip(),
                    "focus_areas": focus_areas[:3],
                    "score": float(scorecard.get("score") or 0.0),
                }
            )
        for finding in list(cross_phase_findings or [])[:3]:
            text = str(finding or "").strip()
            if not text:
                continue
            queue.append(
                {
                    "rank": len(queue) + 1,
                    "phase_name": "cross_phase",
                    "status": "warning",
                    "action": text,
                    "focus_areas": [],
                    "score": 0.0,
                }
            )
        return queue

    def build_agentic_patch_task(
        self,
        results: List[Any],
        *,
        target_files: List[str | Path],
        method: str = "actor_critic",
        priority: int = 70,
        description: Optional[str] = None,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        report: Optional[OptimizationReport] = None,
        components: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, OptimizationReport]:
        components = components or self._load_agentic_optimizer_components()
        task_cls = components["OptimizationTask"]
        method_enum = components["OptimizationMethod"]

        normalized_method = str(method or "actor_critic").strip().lower().replace("-", "_")
        if normalized_method not in {"actor_critic", "adversarial", "test_driven", "chaos"}:
            raise ValueError(f"Unsupported agentic optimization method: {method}")

        report = report or self.analyze(results)
        resolved_targets = [Path(path) for path in target_files]
        recommended_targets = self._recommended_target_files_for_report(report)
        if not resolved_targets:
            resolved_targets = list(recommended_targets)
        resolved_description = description or self._build_agentic_patch_description(
            report,
            method=normalized_method,
            target_files=resolved_targets,
        )

        task = task_cls(
            task_id=f"adversarial_autopatch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            description=resolved_description,
            target_files=resolved_targets,
            method=getattr(method_enum, normalized_method.upper()),
            priority=int(priority),
            constraints=dict(constraints or {}),
            metadata={
                "source": "adversarial_harness",
                "report_summary": {
                    "average_score": report.average_score,
                    "score_trend": report.score_trend,
                    "priority_improvements": list(report.priority_improvements or []),
                    "recommendations": list(report.recommendations or [])[:5],
                    "common_weaknesses": list(report.common_weaknesses or []),
                    "weakest_intake_objectives": self._top_uncovered_intake_objectives(report),
                    "sessions_with_full_intake_coverage": int(
                        (report.intake_priority_performance or {}).get("sessions_with_full_coverage") or 0
                    ),
                    "recommended_target_files": [str(path) for path in recommended_targets],
                    "workflow_phase_plan": dict(report.workflow_phase_plan or {}),
                },
                **dict(metadata or {}),
            },
        )
        return task, report

    def build_phase_patch_tasks(
        self,
        results: List[Any],
        *,
        method: str = "test_driven",
        priority: int = 70,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        report: Optional[OptimizationReport] = None,
        components: Optional[Dict[str, Any]] = None,
        include_ready_phases: bool = True,
    ) -> Tuple[List[Any], OptimizationReport]:
        components = components or self._load_agentic_optimizer_components()
        task_cls = components["OptimizationTask"]
        method_enum = components["OptimizationMethod"]

        normalized_method = str(method or "actor_critic").strip().lower().replace("-", "_")
        if normalized_method not in {"actor_critic", "adversarial", "test_driven", "chaos"}:
            raise ValueError(f"Unsupported agentic optimization method: {method}")

        report = report or self.analyze(results)
        workflow_phase_plan = dict(report.workflow_phase_plan or {})
        phases = dict(workflow_phase_plan.get("phases") or {})
        ordered_names = [
            str(value)
            for value in list(workflow_phase_plan.get("recommended_order") or [])
            if str(value)
        ]

        tasks: List[Any] = []
        timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
        complaint_type_performance = dict(report.complaint_type_performance or {})
        evidence_modality_performance = dict(report.evidence_modality_performance or {})
        graph_signal_context = {
            "kg_avg_gaps": float(report.kg_avg_gaps or 0.0),
            "kg_avg_gaps_delta_per_iter": float(report.kg_avg_gaps_delta_per_iter or 0.0),
            "dg_avg_satisfaction_rate": float(report.dg_avg_satisfaction_rate or 0.0),
            "kg_sessions_gaps_not_reducing": int(report.kg_sessions_gaps_not_reducing or 0),
        }
        intake_signal_context = {
            "question_quality_avg": float(report.question_quality_avg or 0.0),
            "empathy_avg": float(report.empathy_avg or 0.0),
            "efficiency_avg": float(report.efficiency_avg or 0.0),
            "uncovered_intake_objectives": list(
                (report.document_handoff_summary or {}).get("unresolved_intake_objectives") or []
            ),
        }
        document_signal_context = {
            "coverage_avg": float(report.coverage_avg or 0.0),
            "document_generation_status": str(
                (report.workflow_phase_plan or {}).get("phases", {}).get("document_generation", {}).get("status") or ""
            ),
            "document_blockers": list((report.document_handoff_summary or {}).get("blockers") or []),
        }

        weak_complaint_types = [
            name
            for name, payload in sorted(
                complaint_type_performance.items(),
                key=lambda item: (float(item[1].get("average_score") or 0.0), int(item[1].get("count") or 0)),
            )[:3]
            if float(payload.get("average_score") or 0.0) <= float(report.average_score or 0.0)
        ]
        weak_evidence_modalities = [
            name
            for name, payload in sorted(
                evidence_modality_performance.items(),
                key=lambda item: (float(item[1].get("average_score") or 0.0), int(item[1].get("count") or 0)),
            )[:3]
            if float(payload.get("average_score") or 0.0) <= float(report.average_score or 0.0)
        ]

        for phase_name in ordered_names:
            phase_payload = dict(phases.get(phase_name) or {})
            if not include_ready_phases and str(phase_payload.get("status") or "ready") == "ready":
                continue
            target_paths = self._select_workflow_phase_targets(
                phase_name,
                phase_payload,
                report,
                max_targets=1,
            )
            expanded_target_paths = self._select_workflow_phase_targets(
                phase_name,
                phase_payload,
                report,
                max_targets=2,
            )
            secondary_target_paths = [
                path for path in expanded_target_paths
                if path not in target_paths
            ]
            phase_constraints = self._workflow_phase_constraints(phase_name, target_paths)
            secondary_phase_constraints = (
                self._workflow_phase_constraints(phase_name, secondary_target_paths)
                if secondary_target_paths
                else {}
            )
            if str(phase_name) == "intake_questioning" and int(report.num_sessions_analyzed or 0) == 0:
                target_map = dict(phase_constraints.get("target_symbols") or {})
                narrowed_target_map: Dict[str, List[str]] = {}
                for key, value in target_map.items():
                    path = Path(key)
                    if path.name == "session.py":
                        narrowed_target_map[key] = ["_inject_intake_prompt_questions"]
                    else:
                        narrowed_target_map[key] = list(value or [])
                if narrowed_target_map:
                    phase_constraints["target_symbols"] = narrowed_target_map
            phase_actions = [
                str(item.get("recommended_action") or "").strip()
                for item in list(phase_payload.get("recommended_actions") or [])
                if str(item.get("recommended_action") or "").strip()
            ]
            description = (
                f"Use the {normalized_method} optimizer to improve the complaint-generator {phase_name.replace('_', ' ')} phase. "
                f"Target files: {', '.join(str(path) for path in target_paths) or 'auto-detected phase files'}. "
                f"Phase goal: {str(phase_payload.get('summary') or '').strip()}"
            )
            if phase_actions:
                description += " Recommended actions: " + "; ".join(phase_actions[:3]) + "."
            if weak_complaint_types:
                description += " Weak complaint types to generalize for: " + ", ".join(weak_complaint_types[:3]) + "."
            if weak_evidence_modalities:
                description += " Weak evidence modalities to improve: " + ", ".join(weak_evidence_modalities[:3]) + "."
            if phase_name == "intake_questioning":
                targeting_summary = dict(report.intake_targeting_summary or {})
                targeted_objectives = [
                    str(name)
                    for name, _count in sorted(
                        dict(targeting_summary.get("objective_counts") or {}).items(),
                        key=lambda item: (-int(item[1] or 0), item[0]),
                    )[:3]
                    if str(name)
                ]
                targeted_elements = [
                    str(name)
                    for name, _count in sorted(
                        dict(targeting_summary.get("claim_element_counts") or {}).items(),
                        key=lambda item: (-int(item[1] or 0), item[0]),
                    )[:2]
                    if str(name)
                ]
                if targeted_objectives:
                    description += " Intake targets: " + ", ".join(targeted_objectives[:3]) + "."
                if targeted_elements:
                    description += " Legal elements to probe: " + ", ".join(targeted_elements[:2]) + "."
            if phase_name == "graph_analysis":
                targeting_summary = dict(report.graph_element_targeting_summary or {})
                targeted_elements = [
                    str(name)
                    for name, _count in sorted(
                        dict(targeting_summary.get("claim_element_counts") or {}).items(),
                        key=lambda item: (-int(item[1] or 0), item[0]),
                    )[:3]
                    if str(name)
                ]
                targeted_focus_areas = [
                    str(name)
                    for name, _count in sorted(
                        dict(targeting_summary.get("focus_area_counts") or {}).items(),
                        key=lambda item: (-int(item[1] or 0), item[0]),
                    )[:2]
                    if str(name)
                ]
                if targeted_elements:
                    description += " Graph evidence targets: " + ", ".join(targeted_elements[:3]) + "."
                if targeted_focus_areas:
                    description += " Graph focus areas: " + ", ".join(targeted_focus_areas[:2]) + "."
            if phase_name == "document_generation":
                targeting_summary = dict(report.document_evidence_targeting_summary or {})
                targeted_elements = [
                    str(name)
                    for name, _count in sorted(
                        dict(targeting_summary.get("claim_element_counts") or {}).items(),
                        key=lambda item: (-int(item[1] or 0), item[0]),
                    )[:3]
                    if str(name)
                ]
                targeted_support_kinds = [
                    str(name)
                    for name, _count in sorted(
                        dict(targeting_summary.get("support_kind_counts") or {}).items(),
                        key=lambda item: (-int(item[1] or 0), item[0]),
                    )[:2]
                    if str(name)
                ]
                if targeted_elements:
                    description += " Draft loop evidence targets: " + ", ".join(targeted_elements[:3]) + "."
                if targeted_support_kinds:
                    description += " Preferred support lanes: " + ", ".join(targeted_support_kinds[:2]) + "."

            tasks.append(
                task_cls(
                    task_id=f"adversarial_autopatch_{phase_name}_{timestamp}",
                    description=description,
                    target_files=target_paths,
                    method=getattr(method_enum, normalized_method.upper()),
                    priority=int(priority),
                    constraints={
                        **dict(constraints or {}),
                        **phase_constraints,
                    },
                    metadata={
                        "source": "adversarial_harness",
                        "workflow_phase": phase_name,
                        "workflow_phase_priority": int(phase_payload.get("priority") or 0),
                        "workflow_phase_status": str(phase_payload.get("status") or "ready"),
                        "workflow_phase_summary": str(phase_payload.get("summary") or ""),
                        "workflow_phase_actions": phase_actions,
                        "workflow_phase_secondary_target_files": [str(path) for path in secondary_target_paths],
                        "workflow_phase_secondary_constraints": dict(secondary_phase_constraints or {}),
                        "workflow_capabilities": self._workflow_phase_capabilities(phase_name),
                        "weak_complaint_types": weak_complaint_types,
                        "weak_evidence_modalities": weak_evidence_modalities,
                        "phase_scorecard": dict((report.phase_scorecards or {}).get(phase_name) or {}),
                        "phase_signal_context": (
                            graph_signal_context if phase_name == "graph_analysis"
                            else intake_signal_context if phase_name == "intake_questioning"
                            else document_signal_context if phase_name == "document_generation"
                            else {}
                        ),
                        "cross_phase_findings": list(report.cross_phase_findings or []),
                        "intake_targeting_summary": dict(report.intake_targeting_summary or {}),
                        "workflow_targeting_summary": dict(report.workflow_targeting_summary or {}),
                        "graph_element_targeting_summary": dict(report.graph_element_targeting_summary or {}),
                        "document_evidence_targeting_summary": dict(report.document_evidence_targeting_summary or {}),
                        "document_provenance_summary": dict(report.document_provenance_summary or {}),
                        "document_grounding_improvement_summary": dict(report.document_grounding_improvement_summary or {}),
                        "document_workflow_execution_summary": dict(report.document_workflow_execution_summary or {}),
                        "document_execution_drift_summary": dict(report.document_execution_drift_summary or {}),
                        "report_summary": {
                            "average_score": report.average_score,
                            "score_trend": report.score_trend,
                            "priority_improvements": list(report.priority_improvements or []),
                            "workflow_phase_plan": workflow_phase_plan,
                            "complaint_type_performance": complaint_type_performance,
                            "evidence_modality_performance": evidence_modality_performance,
                            "phase_scorecards": dict(report.phase_scorecards or {}),
                            "document_handoff_summary": dict(report.document_handoff_summary or {}),
                            "intake_targeting_summary": dict(report.intake_targeting_summary or {}),
                            "workflow_targeting_summary": dict(report.workflow_targeting_summary or {}),
                            "graph_element_targeting_summary": dict(report.graph_element_targeting_summary or {}),
                            "document_evidence_targeting_summary": dict(report.document_evidence_targeting_summary or {}),
                            "document_provenance_summary": dict(report.document_provenance_summary or {}),
                            "document_grounding_improvement_summary": dict(report.document_grounding_improvement_summary or {}),
                            "document_workflow_execution_summary": dict(report.document_workflow_execution_summary or {}),
                            "document_execution_drift_summary": dict(report.document_execution_drift_summary or {}),
                            "cross_phase_findings": list(report.cross_phase_findings or []),
                        },
                        **dict(metadata or {}),
                    },
                )
            )

        return tasks, report

    def build_workflow_optimization_bundle(
        self,
        results: List[Any],
        *,
        method: str = "test_driven",
        priority: int = 70,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        report: Optional[OptimizationReport] = None,
        components: Optional[Dict[str, Any]] = None,
    ) -> Tuple[WorkflowOptimizationBundle, OptimizationReport]:
        components = components or self._load_agentic_optimizer_components()
        tasks, report = self.build_phase_patch_tasks(
            results,
            method=method,
            priority=priority,
            constraints=constraints,
            metadata=metadata,
            report=report,
            components=components,
        )

        phase_tasks: List[Dict[str, Any]] = []
        for task in tasks:
            phase_tasks.append(
                {
                    "phase_name": str(dict(getattr(task, "metadata", {}) or {}).get("workflow_phase") or ""),
                    "task_id": str(getattr(task, "task_id", "")),
                    "description": str(getattr(task, "description", "")),
                    "target_files": [str(path) for path in list(getattr(task, "target_files", []) or [])],
                    "method": str(getattr(task, "method", "")),
                    "priority": int(getattr(task, "priority", priority) or priority),
                    "constraints": dict(getattr(task, "constraints", {}) or {}),
                    "metadata": dict(getattr(task, "metadata", {}) or {}),
                }
            )

        shared_context = {
            "recommended_hacc_preset": report.recommended_hacc_preset,
            "priority_improvements": list(report.priority_improvements or []),
            "recommendations": list(report.recommendations or []),
            "common_weaknesses": list(report.common_weaknesses or []),
            "common_strengths": list(report.common_strengths or []),
            "complaint_type_performance": dict(report.complaint_type_performance or {}),
            "evidence_modality_performance": dict(report.evidence_modality_performance or {}),
            "intake_priority_performance": dict(report.intake_priority_performance or {}),
            "coverage_remediation": dict(report.coverage_remediation or {}),
            "phase_scorecards": dict(report.phase_scorecards or {}),
            "intake_targeting_summary": dict(report.intake_targeting_summary or {}),
            "workflow_targeting_summary": dict(report.workflow_targeting_summary or {}),
            "complaint_type_generalization_summary": dict(report.complaint_type_generalization_summary or {}),
            "evidence_modality_generalization_summary": dict(report.evidence_modality_generalization_summary or {}),
            "document_handoff_summary": dict(report.document_handoff_summary or {}),
            "graph_element_targeting_summary": dict(report.graph_element_targeting_summary or {}),
            "document_evidence_targeting_summary": dict(report.document_evidence_targeting_summary or {}),
            "document_provenance_summary": dict(report.document_provenance_summary or {}),
            "document_grounding_improvement_summary": dict(report.document_grounding_improvement_summary or {}),
            "document_workflow_execution_summary": dict(report.document_workflow_execution_summary or {}),
            "document_execution_drift_summary": dict(report.document_execution_drift_summary or {}),
            "cross_phase_findings": list(report.cross_phase_findings or []),
            "workflow_action_queue": list(report.workflow_action_queue or []),
        }
        bundle = WorkflowOptimizationBundle(
            timestamp=datetime.now(UTC).isoformat(),
            num_sessions_analyzed=report.num_sessions_analyzed,
            average_score=float(report.average_score or 0.0),
            workflow_phase_plan=dict(report.workflow_phase_plan or {}),
            global_objectives=[
                "Improve complainant and mediator questioning across diverse complaint types.",
                "Improve knowledge-graph and dependency-graph extraction, gap closure, and legal-issue analysis.",
                "Improve drafting and synthesis so complaint outputs reflect the collected facts, evidence, and unresolved gaps.",
                "Improve cross-phase handoffs so intake, graph analysis, and drafting reinforce one another across diverse evidence submissions.",
            ],
            phase_tasks=phase_tasks,
            shared_context=shared_context,
            phase_scorecards=dict(report.phase_scorecards or {}),
            cross_phase_findings=list(report.cross_phase_findings or []),
            workflow_action_queue=list(report.workflow_action_queue or []),
        )
        return bundle, report

    def run_agentic_autopatch(
        self,
        results: List[Any],
        *,
        target_files: List[str | Path],
        method: str = "actor_critic",
        priority: int = 70,
        description: Optional[str] = None,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        report: Optional[OptimizationReport] = None,
        llm_router: Any = None,
        optimizer: Any = None,
        agent_id: str = "adversarial-harness-optimizer",
    ) -> Any:
        if optimizer is not None:
            try:
                components = self._load_agentic_optimizer_components()
            except Exception:
                components = self._fallback_agentic_optimizer_components()
        else:
            components = self._load_agentic_optimizer_components()
        optimizer_classes = components["optimizer_classes"]
        router_cls = components["OptimizerLLMRouter"]

        normalized_method = str(method or "actor_critic").strip().lower().replace("-", "_")
        if optimizer is None and normalized_method not in optimizer_classes:
            raise ValueError(f"Unsupported agentic optimization method: {method}")

        task, report = self.build_agentic_patch_task(
            results,
            target_files=target_files,
            method=normalized_method,
            priority=priority,
            description=description,
            constraints=constraints,
            metadata=metadata,
            report=report,
            components=components,
        )

        resolved_router = llm_router
        if resolved_router is None and router_cls is not None:
            resolved_router = router_cls(enable_tracking=False, enable_caching=True)

        resolved_optimizer = optimizer
        if resolved_optimizer is None:
            resolved_optimizer = optimizer_classes[normalized_method](
                agent_id=agent_id,
                llm_router=resolved_router,
            )
        self._last_agentic_optimizer = resolved_optimizer
        self._last_agentic_generation_diagnostics = []
        try:
            result = resolved_optimizer.optimize(task)
        except Exception as exc:
            diagnostics = getattr(resolved_optimizer, "_last_generation_diagnostics", None)
            if isinstance(diagnostics, list):
                self._last_agentic_generation_diagnostics = list(diagnostics)
            if self._last_agentic_generation_diagnostics:
                first = self._last_agentic_generation_diagnostics[0]
                detail_parts = []
                if first.get("file"):
                    detail_parts.append(f"file={first['file']}")
                if first.get("mode"):
                    detail_parts.append(f"mode={first['mode']}")
                if first.get("error_message"):
                    detail_parts.append(f"detail={first['error_message']}")
                preview = str(first.get("raw_response_preview") or "").strip()
                if preview:
                    compact_preview = " ".join(preview.split())
                    detail_parts.append(f"raw_response_preview={compact_preview[:240]}")
                if detail_parts:
                    raise RuntimeError(f"{exc} | generation diagnostics: {'; '.join(detail_parts)}") from exc
            raise
        result_metadata = getattr(result, "metadata", None)
        if not isinstance(result_metadata, dict):
            result_metadata = {}
            setattr(result, "metadata", result_metadata)
        diagnostics = getattr(resolved_optimizer, "_last_generation_diagnostics", None)
        if isinstance(diagnostics, list):
            self._last_agentic_generation_diagnostics = list(diagnostics)
        result_metadata.setdefault("adversarial_report", report.to_dict())
        result_metadata.setdefault("target_files", [str(path) for path in task.target_files])
        result_metadata.setdefault("agentic_method", normalized_method)
        if self._last_agentic_generation_diagnostics:
            result_metadata.setdefault("generation_diagnostics", list(self._last_agentic_generation_diagnostics))
        return result

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            if isinstance(value, bool):
                return None
            return float(value)
        except Exception:
            return None

    def _extract_graph_metrics(self, result: Any) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[float], Optional[int]]:
        """Return (kg_entities, kg_relationships, dg_nodes, dg_dependencies, dg_satisfaction_rate, kg_gaps)."""
        kg_entities = None
        kg_relationships = None
        kg_gaps = None
        dg_nodes = None
        dg_dependencies = None
        dg_satisfaction_rate = None

        kg_summary = getattr(result, "knowledge_graph_summary", None)
        if isinstance(kg_summary, dict):
            kg_entities = kg_summary.get("total_entities")
            kg_relationships = kg_summary.get("total_relationships")
            kg_gaps = kg_summary.get("gaps")

        dg_summary = getattr(result, "dependency_graph_summary", None)
        if isinstance(dg_summary, dict):
            dg_nodes = dg_summary.get("total_nodes")
            dg_dependencies = dg_summary.get("total_dependencies")
            dg_satisfaction_rate = self._safe_float(dg_summary.get("satisfaction_rate"))

        # Fall back to full graph dict snapshots if summaries are missing.
        kg_dict = getattr(result, "knowledge_graph", None)
        if (kg_entities is None or kg_relationships is None) and isinstance(kg_dict, dict):
            entities = kg_dict.get("entities")
            rels = kg_dict.get("relationships")
            if isinstance(entities, dict):
                kg_entities = len(entities)
            if isinstance(rels, dict):
                kg_relationships = len(rels)

        dg_dict = getattr(result, "dependency_graph", None)
        if (dg_nodes is None or dg_dependencies is None or dg_satisfaction_rate is None) and isinstance(dg_dict, dict):
            nodes = dg_dict.get("nodes")
            deps = dg_dict.get("dependencies")
            if isinstance(nodes, dict):
                dg_nodes = len(nodes)
                try:
                    satisfied = 0
                    for n in nodes.values():
                        if isinstance(n, dict) and n.get("satisfied") is True:
                            satisfied += 1
                    dg_satisfaction_rate = (satisfied / len(nodes)) if nodes else 0.0
                except Exception:
                    dg_satisfaction_rate = dg_satisfaction_rate
            if isinstance(deps, dict):
                dg_dependencies = len(deps)

        def _safe_int(v: Any) -> Optional[int]:
            try:
                if v is None:
                    return None
                if isinstance(v, bool):
                    return None
                return int(v)
            except Exception:
                return None

        return (
            _safe_int(kg_entities),
            _safe_int(kg_relationships),
            _safe_int(dg_nodes),
            _safe_int(dg_dependencies),
            dg_satisfaction_rate,
            _safe_int(kg_gaps),
        )

    def _extract_kg_dynamics(self, result: Any) -> Tuple[Optional[float], Optional[float], Optional[float], bool]:
        """Return (entities_delta_per_iter, relationships_delta_per_iter, gaps_delta_per_iter, gaps_not_reducing)."""
        final_state = getattr(result, "final_state", None)
        if not isinstance(final_state, dict):
            return None, None, None, False
        history = final_state.get("loss_history")
        if not isinstance(history, list) or len(history) < 2:
            # Fall back to convergence_history if present
            history = final_state.get("convergence_history")
        if not isinstance(history, list) or len(history) < 2:
            return None, None, None, False

        def _metric_at(idx: int) -> Dict[str, Any]:
            row = history[idx]
            if not isinstance(row, dict):
                return {}
            m = row.get("metrics")
            return m if isinstance(m, dict) else {}

        m0 = _metric_at(0)
        m1 = _metric_at(-1)
        iters = max(1, len(history) - 1)

        def _int(v: Any) -> Optional[int]:
            try:
                if v is None or isinstance(v, bool):
                    return None
                return int(v)
            except Exception:
                return None

        e0 = _int(m0.get("entities"))
        e1 = _int(m1.get("entities"))
        r0 = _int(m0.get("relationships"))
        r1 = _int(m1.get("relationships"))
        g0 = _int(m0.get("gaps"))
        g1 = _int(m1.get("gaps"))

        de = ((e1 - e0) / iters) if (isinstance(e0, int) and isinstance(e1, int)) else None
        dr = ((r1 - r0) / iters) if (isinstance(r0, int) and isinstance(r1, int)) else None
        dg = ((g1 - g0) / iters) if (isinstance(g0, int) and isinstance(g1, int)) else None
        gaps_not_reducing = bool(isinstance(g0, int) and isinstance(g1, int) and g1 >= g0)
        return de, dr, dg, gaps_not_reducing

    def _extract_seed_meta(self, result: Any) -> Dict[str, Any]:
        seed = getattr(result, "seed_complaint", None)
        if not isinstance(seed, dict):
            return {}
        meta = seed.get("_meta")
        if not isinstance(meta, dict):
            meta = {}
        key_facts = seed.get("key_facts")
        if not isinstance(key_facts, dict):
            key_facts = {}
        anchor_sections = list(meta.get("anchor_sections") or key_facts.get("anchor_sections") or [])
        return {
            "hacc_preset": meta.get("hacc_preset"),
            "include_hacc_evidence": bool(meta.get("include_hacc_evidence")),
            "seed_source": meta.get("seed_source") or seed.get("source"),
            "anchor_sections": anchor_sections,
        }

    def _extract_diversity_meta(self, result: Any) -> Dict[str, Any]:
        seed = getattr(result, "seed_complaint", None)
        if not isinstance(seed, dict):
            return {"complaint_types": [], "evidence_modalities": []}

        meta = dict(seed.get("_meta") or {})
        key_facts = dict(seed.get("key_facts") or {})
        complaint_types: List[str] = []
        evidence_modalities: List[str] = []

        for candidate in (
            seed.get("type"),
            meta.get("seed_source"),
            meta.get("complaint_type"),
            key_facts.get("complaint_type"),
            key_facts.get("category"),
        ):
            value = str(candidate or "").strip().lower()
            if value:
                complaint_types.append(value)

        evidence_candidates: List[Any] = []
        for field in (
            seed.get("hacc_evidence"),
            key_facts.get("anchor_passages"),
            key_facts.get("repository_evidence_candidates"),
            key_facts.get("supporting_evidence"),
        ):
            if isinstance(field, list):
                evidence_candidates.extend(field)

        if key_facts.get("matched_rules"):
            evidence_modalities.append("policy_rule")
        if key_facts.get("grounded_evidence_summary"):
            evidence_modalities.append("grounded_summary")

        for candidate in evidence_candidates:
            if isinstance(candidate, dict):
                source_path = str(
                    candidate.get("source_path")
                    or candidate.get("path")
                    or candidate.get("file_path")
                    or ""
                ).strip().lower()
                title = str(candidate.get("title") or candidate.get("label") or "").strip().lower()
                text = " ".join(
                    [
                        title,
                        str(candidate.get("snippet") or ""),
                        str(candidate.get("summary") or ""),
                    ]
                ).lower()
                if source_path.endswith((".pdf", ".doc", ".docx")):
                    evidence_modalities.append("uploaded_document")
                elif source_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff")):
                    evidence_modalities.append("image_evidence")
                elif source_path.endswith((".eml", ".msg")):
                    evidence_modalities.append("email_record")
                elif source_path.endswith((".txt", ".md")):
                    evidence_modalities.append("text_record")
                elif source_path.endswith((".json", ".csv", ".xlsx")):
                    evidence_modalities.append("structured_record")
                elif "administrative plan" in text or "acop" in text or "policy" in text:
                    evidence_modalities.append("policy_document")
                elif source_path:
                    evidence_modalities.append("file_evidence")
            elif isinstance(candidate, str) and candidate.strip():
                evidence_modalities.append("text_record")

        if not evidence_modalities and bool(meta.get("include_hacc_evidence")):
            evidence_modalities.append("policy_document")

        def _dedupe(values: List[str]) -> List[str]:
            seen = set()
            output: List[str] = []
            for value in values:
                norm = str(value or "").strip().lower()
                if not norm or norm in seen:
                    continue
                seen.add(norm)
                output.append(norm)
            return output

        return {
            "complaint_types": _dedupe(complaint_types) or ["general_complaint"],
            "evidence_modalities": _dedupe(evidence_modalities) or ["narrative_only"],
        }

    def _summarize_group_scores(self, grouped_scores: Dict[str, List[float]]) -> Dict[str, Dict[str, Any]]:
        summary: Dict[str, Dict[str, Any]] = {}
        for key, scores in grouped_scores.items():
            if not scores:
                continue
            summary[key] = {
                "count": len(scores),
                "average_score": sum(scores) / len(scores),
                "min_score": min(scores),
                "max_score": max(scores),
            }
        return summary
    
    def analyze(self, results: List[Any]) -> OptimizationReport:
        """
        Analyze session results and generate optimization report.
        
        Args:
            results: List of SessionResult objects
            
        Returns:
            OptimizationReport with insights and recommendations
        """
        logger.info(f"Analyzing {len(results)} session results")
        
        # Filter successful results
        successful = [r for r in results if r.success and r.critic_score]
        
        if not successful:
            logger.warning("No successful results to analyze")
            return self._empty_report(len(results))
        
        # Calculate aggregate metrics
        scores = [r.critic_score.overall_score for r in successful]
        avg_score = sum(scores) / len(scores)
        
        question_quality_scores = [r.critic_score.question_quality for r in successful]
        info_extraction_scores = [r.critic_score.information_extraction for r in successful]
        empathy_scores = [r.critic_score.empathy for r in successful]
        efficiency_scores = [r.critic_score.efficiency for r in successful]
        coverage_scores = [r.critic_score.coverage for r in successful]
        
        # Find best and worst
        best_result = max(successful, key=lambda r: r.critic_score.overall_score)
        worst_result = min(successful, key=lambda r: r.critic_score.overall_score)

        # Aggregate graph metrics
        kg_entities_vals: List[int] = []
        kg_rels_vals: List[int] = []
        kg_gaps_vals: List[int] = []
        dg_nodes_vals: List[int] = []
        dg_deps_vals: List[int] = []
        dg_rate_vals: List[float] = []
        kg_entities_delta_vals: List[float] = []
        kg_rels_delta_vals: List[float] = []
        kg_gaps_delta_vals: List[float] = []
        kg_with = 0
        dg_with = 0
        kg_empty = 0
        dg_empty = 0
        kg_gaps_not_reducing = 0
        for r in successful:
            kg_e, kg_r, dg_n, dg_d, dg_rate, kg_gaps = self._extract_graph_metrics(r)
            d_e, d_r, d_g, not_reducing = self._extract_kg_dynamics(r)
            if not_reducing:
                kg_gaps_not_reducing += 1
            if isinstance(d_e, (int, float)):
                kg_entities_delta_vals.append(float(d_e))
            if isinstance(d_r, (int, float)):
                kg_rels_delta_vals.append(float(d_r))
            if isinstance(d_g, (int, float)):
                kg_gaps_delta_vals.append(float(d_g))
            if kg_e is not None or kg_r is not None:
                kg_with += 1
                if kg_e == 0:
                    kg_empty += 1
            if dg_n is not None or dg_d is not None:
                dg_with += 1
                if dg_n == 0:
                    dg_empty += 1
            if isinstance(kg_e, int):
                kg_entities_vals.append(kg_e)
            if isinstance(kg_r, int):
                kg_rels_vals.append(kg_r)
            if isinstance(kg_gaps, int):
                kg_gaps_vals.append(kg_gaps)
            if isinstance(dg_n, int):
                dg_nodes_vals.append(dg_n)
            if isinstance(dg_d, int):
                dg_deps_vals.append(dg_d)
            if isinstance(dg_rate, (int, float)):
                dg_rate_vals.append(float(dg_rate))

        def _avg_int(vals: List[int]) -> Optional[float]:
            if not vals:
                return None
            return sum(vals) / len(vals)

        def _avg_float(vals: List[float]) -> Optional[float]:
            if not vals:
                return None
            return sum(vals) / len(vals)
        
        # Aggregate feedback
        all_strengths = []
        all_weaknesses = []
        all_suggestions = []
        all_anchor_missing = []
        all_anchor_covered = []
        preset_scores: Dict[str, List[float]] = {}
        anchor_section_scores: Dict[str, List[float]] = {}
        complaint_type_scores: Dict[str, List[float]] = {}
        evidence_modality_scores: Dict[str, List[float]] = {}
        
        for result in successful:
            all_strengths.extend(result.critic_score.strengths)
            all_weaknesses.extend(result.critic_score.weaknesses)
            all_suggestions.extend(result.critic_score.suggestions)
            all_anchor_missing.extend(getattr(result.critic_score, 'anchor_sections_missing', []) or [])
            all_anchor_covered.extend(getattr(result.critic_score, 'anchor_sections_covered', []) or [])
            seed_meta = self._extract_seed_meta(result)
            preset = seed_meta.get("hacc_preset")
            if isinstance(preset, str) and preset:
                preset_scores.setdefault(preset, []).append(result.critic_score.overall_score)
            for section in list(seed_meta.get("anchor_sections") or []):
                if isinstance(section, str) and section:
                    anchor_section_scores.setdefault(section, []).append(result.critic_score.overall_score)
            diversity_meta = self._extract_diversity_meta(result)
            for complaint_type in list(diversity_meta.get("complaint_types") or []):
                if isinstance(complaint_type, str) and complaint_type:
                    complaint_type_scores.setdefault(complaint_type, []).append(result.critic_score.overall_score)
            for modality in list(diversity_meta.get("evidence_modalities") or []):
                if isinstance(modality, str) and modality:
                    evidence_modality_scores.setdefault(modality, []).append(result.critic_score.overall_score)
        
        # Find most common
        common_strengths = self._most_common(all_strengths, top_n=5)
        common_weaknesses = self._most_common(all_weaknesses, top_n=5)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            avg_score,
            question_quality_scores,
            info_extraction_scores,
            empathy_scores,
            efficiency_scores,
            coverage_scores,
            common_weaknesses,
            all_suggestions,
            anchor_summary={
                "missing": self._most_common(all_anchor_missing, top_n=5),
                "covered": self._most_common(all_anchor_covered, top_n=5),
            },
            graph_summary={
                "kg_sessions_with_data": kg_with,
                "dg_sessions_with_data": dg_with,
                "kg_sessions_empty": kg_empty,
                "dg_sessions_empty": dg_empty,
                "kg_avg_total_entities": _avg_int(kg_entities_vals),
                "kg_avg_total_relationships": _avg_int(kg_rels_vals),
                "kg_avg_gaps": _avg_int(kg_gaps_vals),
                "dg_avg_total_nodes": _avg_int(dg_nodes_vals),
                "dg_avg_total_dependencies": _avg_int(dg_deps_vals),
                "dg_avg_satisfaction_rate": _avg_float(dg_rate_vals),
                "kg_avg_entities_delta_per_iter": _avg_float(kg_entities_delta_vals),
                "kg_avg_relationships_delta_per_iter": _avg_float(kg_rels_delta_vals),
                "kg_avg_gaps_delta_per_iter": _avg_float(kg_gaps_delta_vals),
                "kg_sessions_gaps_not_reducing": kg_gaps_not_reducing,
            },
        )
        
        # Determine priority improvements
        priority_improvements = self._determine_priorities(
            question_quality_scores,
            info_extraction_scores,
            empathy_scores,
            efficiency_scores,
            coverage_scores
        )
        
        # Determine trend
        trend = self._determine_trend(scores)
        hacc_preset_performance = self._summarize_group_scores(preset_scores)
        anchor_section_performance = self._summarize_group_scores(anchor_section_scores)
        complaint_type_performance = self._summarize_group_scores(complaint_type_scores)
        evidence_modality_performance = self._summarize_group_scores(evidence_modality_scores)
        intake_priority_performance = self._summarize_intake_priority(successful)
        coverage_remediation = self._build_coverage_remediation(
            anchor_missing=self._most_common(all_anchor_missing, top_n=5),
            intake_priority_performance=intake_priority_performance,
        )
        document_evidence_targeting_summary = self._build_document_evidence_targeting_summary(successful)
        document_provenance_summary = self._build_document_provenance_summary(successful)
        document_grounding_improvement_summary = self._build_document_grounding_improvement_summary(successful)
        document_workflow_execution_summary = self._build_document_workflow_execution_summary(successful)
        document_execution_drift_summary = self._build_document_execution_drift_summary(
            document_evidence_targeting_summary=document_evidence_targeting_summary,
            document_workflow_execution_summary=document_workflow_execution_summary,
        )
        workflow_phase_plan = self._build_workflow_phase_plan(
            question_quality_avg=sum(question_quality_scores) / len(question_quality_scores),
            information_extraction_avg=sum(info_extraction_scores) / len(info_extraction_scores),
            efficiency_avg=sum(efficiency_scores) / len(efficiency_scores),
            coverage_avg=sum(coverage_scores) / len(coverage_scores),
            graph_summary={
                "kg_sessions_with_data": kg_with,
                "dg_sessions_with_data": dg_with,
                "kg_sessions_empty": kg_empty,
                "dg_sessions_empty": dg_empty,
                "kg_avg_total_entities": _avg_int(kg_entities_vals),
                "kg_avg_total_relationships": _avg_int(kg_rels_vals),
                "kg_avg_gaps": _avg_int(kg_gaps_vals),
                "dg_avg_total_nodes": _avg_int(dg_nodes_vals),
                "dg_avg_total_dependencies": _avg_int(dg_deps_vals),
                "dg_avg_satisfaction_rate": _avg_float(dg_rate_vals),
                "kg_avg_entities_delta_per_iter": _avg_float(kg_entities_delta_vals),
                "kg_avg_relationships_delta_per_iter": _avg_float(kg_rels_delta_vals),
                "kg_avg_gaps_delta_per_iter": _avg_float(kg_gaps_delta_vals),
                "kg_sessions_gaps_not_reducing": kg_gaps_not_reducing,
            },
            coverage_remediation=coverage_remediation,
            document_evidence_targeting_summary=document_evidence_targeting_summary,
            document_provenance_summary=document_provenance_summary,
            document_workflow_execution_summary=document_workflow_execution_summary,
        )
        recommended_hacc_preset = None
        if hacc_preset_performance:
            recommended_hacc_preset = max(
                hacc_preset_performance.items(),
                key=lambda item: (float(item[1].get("average_score") or 0.0), int(item[1].get("count") or 0)),
            )[0]

        if hacc_preset_performance:
            best_preset = recommended_hacc_preset
            weak_presets = [
                name
                for name, payload in hacc_preset_performance.items()
                if float(payload.get("average_score") or 0.0) < avg_score
            ]
            if best_preset:
                recommendations.append(
                    f"Best HACC preset so far is '{best_preset}'. Prefer it when generating evidence-backed adversarial batches."
                )
            if weak_presets:
                recommendations.append(
                    "Lower-performing HACC presets may need different mediator probes or seed curation: "
                    + ", ".join(sorted(weak_presets[:3])) + "."
                )

        if anchor_section_performance:
            weakest_sections = sorted(
                anchor_section_performance.items(),
                key=lambda item: (float(item[1].get("average_score") or 0.0), int(item[1].get("count") or 0)),
            )[:3]
            weak_labels = [name for name, payload in weakest_sections if float(payload.get("average_score") or 0.0) < avg_score]
            if weak_labels:
                recommendations.append(
                    "Decision-tree coverage is weakest for these seeded anchor sections: "
                    + ", ".join(weak_labels) + ". Add more explicit branch logic for them."
                )

        if complaint_type_performance:
            weak_complaint_types = [
                name
                for name, payload in sorted(
                    complaint_type_performance.items(),
                    key=lambda item: (float(item[1].get("average_score") or 0.0), int(item[1].get("count") or 0)),
                )[:3]
                if float(payload.get("average_score") or 0.0) < avg_score
            ]
            if weak_complaint_types:
                recommendations.append(
                    "Generalization is weakest for these complaint types: "
                    + ", ".join(weak_complaint_types)
                    + ". Expand intake prompts, graph updates, and drafting logic so they do not rely on a single complaint template."
                )
                priority_improvements.insert(
                    0,
                    "Improve complaint-type generalization: " + ", ".join(weak_complaint_types[:3]),
                )

        if evidence_modality_performance:
            weak_modalities = [
                name
                for name, payload in sorted(
                    evidence_modality_performance.items(),
                    key=lambda item: (float(item[1].get("average_score") or 0.0), int(item[1].get("count") or 0)),
                )[:3]
                if float(payload.get("average_score") or 0.0) < avg_score
            ]
            if weak_modalities:
                recommendations.append(
                    "Evidence handling is weakest for these evidence modalities: "
                    + ", ".join(weak_modalities)
                    + ". Improve evidence ingestion, graph extraction, and complaint drafting handoff for those submission types."
                )
                priority_improvements.insert(
                    0,
                    "Improve evidence-modality coverage: " + ", ".join(weak_modalities[:3]),
                )

        graph_element_targeting_summary = self._build_graph_element_targeting_summary(successful)
        graph_targeted_elements = [
            str(name)
            for name, _count in sorted(
                dict((graph_element_targeting_summary or {}).get("claim_element_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name)
        ]
        if graph_targeted_elements:
            recommendations.append(
                "Graph analysis is repeatedly targeting these claim elements for stronger structure and support propagation: "
                + ", ".join(graph_targeted_elements)
                + ". Improve KG/DG updates and denoiser routing for those elements."
            )
            priority_improvements.insert(
                0,
                "Improve graph element targeting: " + ", ".join(graph_targeted_elements[:3]),
            )

        targeted_elements = [
            str(name)
            for name, _count in sorted(
                dict((document_evidence_targeting_summary or {}).get("claim_element_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name)
        ]
        targeted_support_kinds = [
            str(name)
            for name, _count in sorted(
                dict((document_evidence_targeting_summary or {}).get("support_kind_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:2]
            if str(name)
        ]
        if targeted_elements:
            recommendations.append(
                "Document optimization is repeatedly targeting these claim elements for stronger support: "
                + ", ".join(targeted_elements)
                + ". Improve drafting handoff and support retrieval for those elements."
            )
            if targeted_support_kinds:
                priority_improvements.insert(
                    0,
                    "Improve document-evidence targeting for "
                    + ", ".join(targeted_elements[:2])
                    + " via "
                    + ", ".join(targeted_support_kinds),
                )
        if bool(document_provenance_summary.get("low_grounding_flag")):
            recommendations.append(
                "Draft grounding is weak across analyzed sessions. Increase canonical-fact and artifact-backed provenance in factual allegations and claim-specific support before relying on the complaint text."
            )
            priority_improvements.insert(
                0,
                "Improve document provenance grounding"
                + (
                    f": fact-backed ratio {float(document_provenance_summary.get('avg_fact_backed_ratio') or 0.0):.2f}"
                    if document_provenance_summary.get("avg_fact_backed_ratio") is not None
                    else ""
                ),
            )
        if bool(document_grounding_improvement_summary.get("recovery_attempted_session_count")) and not bool(
            document_grounding_improvement_summary.get("improved_session_count")
        ):
            recommendations.append(
                "Grounding recovery prompts are being attempted without improving fact-backed ratios. Tighten recovery prompts and the support lanes they request."
            )
            priority_improvements.insert(
                0,
                "Improve document grounding recovery prompts"
                + (
                    f": avg delta {float(document_grounding_improvement_summary.get('avg_fact_backed_ratio_delta') or 0.0):.2f}"
                    if document_grounding_improvement_summary.get("avg_fact_backed_ratio_delta") is not None
                    else ""
                ),
            )
        elif bool(document_grounding_improvement_summary.get("improved_session_count")):
            recommendations.append(
                "Grounding recovery prompts are improving fact-backed ratios in at least some sessions. Preserve and expand those recovery flows."
            )
        first_executed_claim_element = str(
            (document_workflow_execution_summary or {}).get("first_targeted_claim_element") or ""
        ).strip()
        if targeted_elements and first_executed_claim_element and first_executed_claim_element != targeted_elements[0]:
            recommendations.append(
                "Document optimization is not acting on the highest-priority targeted claim element first. "
                f"Targeted first element should be {targeted_elements[0]}, but drafting acted on {first_executed_claim_element}."
            )
            priority_improvements.insert(
                0,
                "Align document execution with targeting priorities: "
                + targeted_elements[0]
                + " before "
                + first_executed_claim_element,
            )

        if intake_priority_performance:
            weakest_objectives = [
                (name, payload)
                for name, payload in sorted(
                    (intake_priority_performance.get("coverage_by_objective") or {}).items(),
                    key=lambda item: (
                        float(item[1].get("coverage_rate") or 0.0),
                        -int(item[1].get("expected") or 0),
                        item[0],
                    ),
                )
                if int(payload.get("expected") or 0) > 0 and float(payload.get("coverage_rate") or 0.0) < 1.0
            ]
            if weakest_objectives:
                formatted = [
                    f"{name} ({int(payload.get('covered') or 0)}/{int(payload.get('expected') or 0)})"
                    for name, payload in weakest_objectives[:3]
                ]
                recommendations.append(
                    "Adversarial intake priorities are not fully covered. Add stronger probes or fallback prompts for: "
                    + ", ".join(formatted) + "."
                )
                priority_improvements.insert(
                    0,
                    "Improve intake priority coverage: "
                    + ", ".join(str(name) for name, _payload in weakest_objectives[:3]),
                )
            elif int(intake_priority_performance.get("sessions_with_full_coverage") or 0) > 0:
                recommendations.append(
                    "Intake-priority objectives achieved full coverage in the analyzed sessions. Preserve the current anchor-aware prompt injection and fallback probes."
                )

        anchor_actions = list((coverage_remediation.get("anchor_sections") or {}).get("recommended_actions") or [])
        if anchor_actions:
            anchor_focus = ", ".join(str(item.get("section") or "") for item in anchor_actions[:3] if str(item.get("section") or ""))
            if anchor_focus:
                priority_improvements.insert(0, f"Close anchor-section coverage gaps: {anchor_focus}")
        
        intake_targeting_summary = self._build_intake_targeting_summary(successful)
        targeted_intake_objectives = [
            str(name)
            for name, _count in sorted(
                dict((intake_targeting_summary or {}).get("objective_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name)
        ]
        targeted_intake_elements = [
            str(name)
            for name, _count in sorted(
                dict((intake_targeting_summary or {}).get("claim_element_counts") or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name)
        ]
        if targeted_intake_objectives or targeted_intake_elements:
            recommendations.append(
                "Intake questioning is repeatedly targeting these objectives/elements: "
                + ", ".join((targeted_intake_objectives + targeted_intake_elements)[:4])
                + ". Improve intake routing, fallback prompts, and legal-element probes for those gaps."
            )
            priority_improvements.insert(
                0,
                "Improve intake targeting: " + ", ".join((targeted_intake_objectives + targeted_intake_elements)[:3]),
            )

        workflow_targeting_summary = self._build_workflow_targeting_summary(
            intake_targeting_summary=intake_targeting_summary,
            graph_element_targeting_summary=graph_element_targeting_summary,
            document_evidence_targeting_summary=document_evidence_targeting_summary,
        )

        complaint_type_generalization_summary = self._build_generalization_summary(
            complaint_type_performance,
            avg_score,
        )
        evidence_modality_generalization_summary = self._build_generalization_summary(
            evidence_modality_performance,
            avg_score,
        )
        graph_summary_payload = {
            "kg_sessions_with_data": kg_with,
            "dg_sessions_with_data": dg_with,
            "kg_sessions_empty": kg_empty,
            "dg_sessions_empty": dg_empty,
            "kg_avg_total_entities": _avg_int(kg_entities_vals),
            "kg_avg_total_relationships": _avg_int(kg_rels_vals),
            "kg_avg_gaps": _avg_int(kg_gaps_vals),
            "dg_avg_total_nodes": _avg_int(dg_nodes_vals),
            "dg_avg_total_dependencies": _avg_int(dg_deps_vals),
            "dg_avg_satisfaction_rate": _avg_float(dg_rate_vals),
            "kg_avg_entities_delta_per_iter": _avg_float(kg_entities_delta_vals),
            "kg_avg_relationships_delta_per_iter": _avg_float(kg_rels_delta_vals),
            "kg_avg_gaps_delta_per_iter": _avg_float(kg_gaps_delta_vals),
            "kg_sessions_gaps_not_reducing": kg_gaps_not_reducing,
        }
        document_handoff_summary = self._build_document_handoff_summary(
            coverage_remediation=coverage_remediation,
            workflow_phase_plan=workflow_phase_plan,
            complaint_type_summary=complaint_type_generalization_summary,
            evidence_modality_summary=evidence_modality_generalization_summary,
        )
        phase_scorecards_placeholder = {}
        report = OptimizationReport(
            timestamp=datetime.now(UTC).isoformat(),
            num_sessions_analyzed=len(successful),
            average_score=avg_score,
            score_trend=trend,
            question_quality_avg=sum(question_quality_scores) / len(question_quality_scores),
            information_extraction_avg=sum(info_extraction_scores) / len(info_extraction_scores),
            empathy_avg=sum(empathy_scores) / len(empathy_scores),
            efficiency_avg=sum(efficiency_scores) / len(efficiency_scores),
            coverage_avg=sum(coverage_scores) / len(coverage_scores),
            common_weaknesses=common_weaknesses,
            common_strengths=common_strengths,
            recommendations=recommendations,
            priority_improvements=priority_improvements,
            kg_sessions_with_data=kg_with,
            dg_sessions_with_data=dg_with,
            kg_sessions_empty=kg_empty,
            dg_sessions_empty=dg_empty,
            kg_avg_total_entities=_avg_int(kg_entities_vals),
            kg_avg_total_relationships=_avg_int(kg_rels_vals),
            kg_avg_gaps=_avg_int(kg_gaps_vals),
            dg_avg_total_nodes=_avg_int(dg_nodes_vals),
            dg_avg_total_dependencies=_avg_int(dg_deps_vals),
            dg_avg_satisfaction_rate=_avg_float(dg_rate_vals),
            kg_avg_entities_delta_per_iter=_avg_float(kg_entities_delta_vals),
            kg_avg_relationships_delta_per_iter=_avg_float(kg_rels_delta_vals),
            kg_avg_gaps_delta_per_iter=_avg_float(kg_gaps_delta_vals),
            kg_sessions_gaps_not_reducing=kg_gaps_not_reducing,
            best_session_id=best_result.session_id,
            worst_session_id=worst_result.session_id,
            best_score=best_result.critic_score.overall_score,
            worst_score=worst_result.critic_score.overall_score,
            hacc_preset_performance=hacc_preset_performance,
            anchor_section_performance=anchor_section_performance,
            complaint_type_performance=complaint_type_performance,
            evidence_modality_performance=evidence_modality_performance,
            intake_priority_performance=intake_priority_performance,
            coverage_remediation=coverage_remediation,
            recommended_hacc_preset=recommended_hacc_preset,
            workflow_phase_plan=workflow_phase_plan,
            phase_scorecards=phase_scorecards_placeholder,
            intake_targeting_summary=intake_targeting_summary,
            workflow_targeting_summary=workflow_targeting_summary,
            complaint_type_generalization_summary=complaint_type_generalization_summary,
            evidence_modality_generalization_summary=evidence_modality_generalization_summary,
            document_handoff_summary=document_handoff_summary,
            graph_element_targeting_summary=graph_element_targeting_summary,
            document_evidence_targeting_summary=document_evidence_targeting_summary,
            document_provenance_summary=document_provenance_summary,
            document_grounding_improvement_summary=document_grounding_improvement_summary,
            document_workflow_execution_summary=document_workflow_execution_summary,
            document_execution_drift_summary=document_execution_drift_summary,
            cross_phase_findings=[],
            workflow_action_queue=[],
        )
        report.phase_scorecards = self._build_phase_scorecards(
            report=report,
            graph_summary=graph_summary_payload,
            intake_targeting_summary=intake_targeting_summary,
            complaint_type_summary=complaint_type_generalization_summary,
            evidence_modality_summary=evidence_modality_generalization_summary,
            document_handoff_summary=document_handoff_summary,
            graph_element_targeting_summary=graph_element_targeting_summary,
            document_evidence_targeting_summary=document_evidence_targeting_summary,
            document_provenance_summary=document_provenance_summary,
            document_grounding_improvement_summary=document_grounding_improvement_summary,
            document_workflow_execution_summary=document_workflow_execution_summary,
            document_execution_drift_summary=document_execution_drift_summary,
        )
        report.cross_phase_findings = self._build_cross_phase_findings(
            phase_scorecards=report.phase_scorecards,
            document_handoff_summary=document_handoff_summary,
        )
        report.workflow_action_queue = self._build_workflow_action_queue(
            workflow_phase_plan=report.workflow_phase_plan,
            phase_scorecards=report.phase_scorecards,
            cross_phase_findings=report.cross_phase_findings,
        )
        
        self.history.append(report)
        logger.info(f"Analysis complete. Average score: {avg_score:.3f}, Trend: {trend}")
        
        return report
    
    def _most_common(self, items: List[str], top_n: int = 5) -> List[str]:
        """Find most common items."""
        if not items:
            return []
        
        counter = Counter(items)
        return [item for item, count in counter.most_common(top_n)]

    def _summarize_intake_priority(self, successful_results: List[Any]) -> Dict[str, Any]:
        expected_counter: Counter[str] = Counter()
        covered_counter: Counter[str] = Counter()
        uncovered_counter: Counter[str] = Counter()
        sessions_with_full_coverage = 0

        for result in successful_results:
            final_state = dict(getattr(result, 'final_state', {}) or {})
            summary = dict(final_state.get('adversarial_intake_priority_summary') or {})
            expected = [str(value) for value in list(summary.get('expected_objectives') or []) if str(value)]
            covered = [str(value) for value in list(summary.get('covered_objectives') or []) if str(value)]
            uncovered = [str(value) for value in list(summary.get('uncovered_objectives') or []) if str(value)]
            expected_counter.update(expected)
            covered_counter.update(covered)
            uncovered_counter.update(uncovered)
            if expected and not uncovered:
                sessions_with_full_coverage += 1

        objective_names = sorted(set(expected_counter) | set(covered_counter) | set(uncovered_counter))
        coverage_by_objective: Dict[str, Dict[str, Any]] = {}
        for name in objective_names:
            expected_count = expected_counter.get(name, 0)
            covered_count = covered_counter.get(name, 0)
            uncovered_count = uncovered_counter.get(name, 0)
            coverage_by_objective[name] = {
                'expected': expected_count,
                'covered': covered_count,
                'uncovered': uncovered_count,
                'coverage_rate': (covered_count / expected_count) if expected_count else 0.0,
            }

        return {
            'expected_counts': dict(expected_counter),
            'covered_counts': dict(covered_counter),
            'uncovered_counts': dict(uncovered_counter),
            'coverage_by_objective': coverage_by_objective,
            'sessions_with_full_coverage': sessions_with_full_coverage,
            'sessions_with_partial_coverage': max(0, len(successful_results) - sessions_with_full_coverage),
        }

    def _build_coverage_remediation(
        self,
        *,
        anchor_missing: List[str],
        intake_priority_performance: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        anchor_actions = [
            {
                'section': section,
                'recommended_action': f"Add or strengthen explicit mediator probes for '{section}' before the session exits intake.",
                'signal': 'critic_missing',
            }
            for section in list(anchor_missing or [])
            if str(section)
        ]

        intake_actions: List[Dict[str, Any]] = []
        intake_coverage = dict((intake_priority_performance or {}).get('coverage_by_objective') or {})
        for objective, payload in sorted(
            intake_coverage.items(),
            key=lambda item: (
                float((item[1] or {}).get('coverage_rate') or 0.0),
                -int((item[1] or {}).get('expected') or 0),
                item[0],
            ),
        ):
            expected = int((payload or {}).get('expected') or 0)
            covered = int((payload or {}).get('covered') or 0)
            uncovered = int((payload or {}).get('uncovered') or 0)
            coverage_rate = float((payload or {}).get('coverage_rate') or 0.0)
            if expected <= 0 or coverage_rate >= 1.0:
                continue
            intake_actions.append(
                {
                    'objective': objective,
                    'expected': expected,
                    'covered': covered,
                    'uncovered': uncovered,
                    'coverage_rate': coverage_rate,
                    'recommended_action': self._intake_objective_action(objective),
                }
            )

        return {
            'anchor_sections': {
                'missing_sections': list(anchor_missing or []),
                'recommended_actions': anchor_actions,
            },
            'intake_priorities': {
                'uncovered_objectives': [item.get('objective') for item in intake_actions if item.get('objective')],
                'recommended_actions': intake_actions,
                'sessions_with_full_coverage': int((intake_priority_performance or {}).get('sessions_with_full_coverage') or 0),
                'sessions_with_partial_coverage': int((intake_priority_performance or {}).get('sessions_with_partial_coverage') or 0),
            },
        }

    def _intake_objective_action(self, objective: str) -> str:
        normalized = str(objective or '').strip()
        if not normalized:
            return "Add a dedicated fallback question for this intake objective."
        if normalized == 'exact_dates':
            return "Ask for exact dates or anchored date ranges and keep chronology follow-ups ahead of generic narrative prompts."
        if normalized == 'staff_names_titles':
            return "Ask for the HACC staff names and titles tied to each decision, notice, hearing, and communication step."
        if normalized == 'hearing_request_timing':
            return "Ask when the hearing or review was requested, how it was requested, and when HACC responded."
        if normalized == 'response_dates':
            return "Ask for exact response dates on notices, review outcomes, hearing decisions, and other official communications."
        if normalized == 'causation_sequence':
            return "Ask the complainant to walk step-by-step through protected activity, response, and adverse action so causation can be modeled directly."
        if normalized == 'timeline':
            return "Ask for a clear chronology early and keep date/sequence follow-ups ahead of generic evidence questions."
        if normalized == 'actors':
            return "Ask who made, communicated, or carried out each decision and capture names, roles, and witnesses."
        if normalized == 'documents':
            return "Request notices, emails, grievances, hearing requests, appeal paperwork, and other written records earlier in intake."
        if normalized == 'harm_remedy':
            return "Ask what harm occurred and what remedy the complainant wants before leaving intake."
        if normalized == 'witnesses':
            return "Ask for witness identities, their relationship to the event, and what each person observed."
        if normalized.startswith('anchor_'):
            anchor_label = normalized[len('anchor_'):].replace('_', ' ')
            return f"Add a dedicated anchor-specific fallback probe for {anchor_label} and keep it ahead of generic catch-all prompts."
        return f"Add a dedicated fallback question for the '{normalized}' intake objective."
    
    def _generate_recommendations(self,
                                  avg_score: float,
                                  question_quality: List[float],
                                  info_extraction: List[float],
                                  empathy: List[float],
                                  efficiency: List[float],
                                  coverage: List[float],
                                  weaknesses: List[str],
                              suggestions: List[str],
                              anchor_summary: Optional[Dict[str, Any]] = None,
                              graph_summary: Optional[Dict[str, Any]] = None) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # Score-based recommendations
        if avg_score < 0.5:
            recommendations.append("Overall performance is below average. Focus on fundamental improvements.")
        elif avg_score < 0.7:
            recommendations.append("Performance is moderate. Targeted improvements can significantly boost quality.")
        else:
            recommendations.append("Performance is good. Focus on consistency and edge cases.")
        
        # Component-specific recommendations
        avg_question_quality = sum(question_quality) / len(question_quality)
        if avg_question_quality < 0.6:
            recommendations.append("Improve question formulation: make questions more specific and relevant.")
        
        avg_info_extraction = sum(info_extraction) / len(info_extraction)
        if avg_info_extraction < 0.6:
            recommendations.append("Enhance information extraction: ask follow-up questions when responses are vague.")
        
        avg_empathy = sum(empathy) / len(empathy)
        if avg_empathy < 0.6:
            recommendations.append("Increase empathy: acknowledge complainant's feelings and concerns.")
        
        avg_efficiency = sum(efficiency) / len(efficiency)
        if avg_efficiency < 0.6:
            recommendations.append("Improve efficiency: avoid repetitive questions and streamline the process.")
        
        avg_coverage = sum(coverage) / len(coverage)
        if avg_coverage < 0.6:
            recommendations.append("Expand topic coverage: ensure all important aspects are addressed.")

        if isinstance(anchor_summary, dict):
            missing_sections = list(anchor_summary.get("missing") or [])
            covered_sections = list(anchor_summary.get("covered") or [])
            if missing_sections:
                recommendations.append(
                    "Decision-tree coverage is incomplete for seeded evidence sections. Add explicit probes for: "
                    + ", ".join(missing_sections) + "."
                )
            elif covered_sections:
                recommendations.append(
                    "Evidence-section coverage is improving. Preserve explicit questioning around: "
                    + ", ".join(covered_sections) + "."
                )

        # Graph-aware recommendations (to steer improvements in KG/DG population/reduction).
        if isinstance(graph_summary, dict):
            kg_with = int(graph_summary.get("kg_sessions_with_data") or 0)
            dg_with = int(graph_summary.get("dg_sessions_with_data") or 0)
            kg_empty = int(graph_summary.get("kg_sessions_empty") or 0)
            dg_empty = int(graph_summary.get("dg_sessions_empty") or 0)
            kg_avg_entities = self._safe_float(graph_summary.get("kg_avg_total_entities"))
            dg_avg_nodes = self._safe_float(graph_summary.get("dg_avg_total_nodes"))
            kg_avg_gaps = self._safe_float(graph_summary.get("kg_avg_gaps"))
            kg_d_entities = self._safe_float(graph_summary.get("kg_avg_entities_delta_per_iter"))
            kg_d_rels = self._safe_float(graph_summary.get("kg_avg_relationships_delta_per_iter"))
            kg_d_gaps = self._safe_float(graph_summary.get("kg_avg_gaps_delta_per_iter"))
            kg_not_reducing = int(graph_summary.get("kg_sessions_gaps_not_reducing") or 0)
            dg_avg_rate = self._safe_float(graph_summary.get("dg_avg_satisfaction_rate"))

            if kg_with == 0:
                recommendations.append(
                    "No knowledge graph data was captured. Ensure Phase 1 builds a KnowledgeGraph and the session extracts/saves knowledge_graph_summary."
                )
            elif kg_empty == kg_with:
                recommendations.append(
                    "All knowledge graphs are empty. Improve entity/relationship extraction in complaint_phases/knowledge_graph.py so downstream phases can reason over claims and facts."
                )
            elif kg_avg_entities is not None and kg_avg_entities < 2:
                recommendations.append(
                    "Knowledge graphs are very small on average. Consider adding lightweight rule-based extraction (dates/actors/employer/action) or LLM extraction to enrich the KG."
                )

            if dg_with == 0:
                recommendations.append(
                    "No dependency graph data was captured. Ensure Phase 1 builds a DependencyGraph and the session extracts/saves dependency_graph_summary."
                )
            elif dg_empty == dg_with:
                recommendations.append(
                    "All dependency graphs are empty. This often indicates missing/empty claims in the KG or claim extraction logic; verify claim entities and dg_builder.build_from_claims inputs."
                )
            elif dg_avg_nodes is not None and dg_avg_nodes < 2:
                recommendations.append(
                    "Dependency graphs are very small on average. Expand claim->requirement modeling so denoising can target missing legal elements and facts."
                )

            if kg_avg_gaps is not None and kg_avg_gaps >= 3:
                recommendations.append(
                    "Knowledge graph gap count is high on average. Improve gap-reduction logic in complaint_phases/denoiser.py and ensure process_answer updates entities/relationships meaningfully."
                )
            if kg_not_reducing > 0:
                recommendations.append(
                    f"In {kg_not_reducing} sessions, KG gaps did not reduce over iterations. Consider making denoiser.process_answer reduce gaps deterministically (e.g., marking gap items as addressed when answers supply the missing fields)."
                )
            if kg_d_entities is not None and kg_d_entities < 0.1:
                recommendations.append(
                    "Knowledge graph is not growing much per iteration. Consider extracting structured entities/relationships from denoising answers to enrich the KG over time."
                )
            if kg_d_rels is not None and kg_d_rels < 0.05:
                recommendations.append(
                    "Knowledge graph relationships are not increasing across iterations. Consider adding relationship updates when answers mention who/what/when/where/why links."
                )
            if kg_d_gaps is not None and kg_d_gaps >= 0.0:
                recommendations.append(
                    "KG gaps are not decreasing on average (or are increasing). Improve gap selection + answer processing so each turn reduces uncertainty."
                )
            if dg_avg_rate is not None and dg_avg_rate < 0.2:
                recommendations.append(
                    "Dependency satisfaction rate is very low on average. Consider having denoising answers mark requirements as satisfied or add evidence/fact nodes as they are provided."
                )
        
        # Add unique suggestions from critics
        unique_suggestions = list(set(suggestions))
        recommendations.extend(unique_suggestions[:3])  # Top 3 suggestions
        
        return recommendations
    
    def _determine_priorities(self,
                             question_quality: List[float],
                             info_extraction: List[float],
                             empathy: List[float],
                             efficiency: List[float],
                             coverage: List[float]) -> List[str]:
        """Determine priority improvements based on lowest scores."""
        components = {
            'question_quality': sum(question_quality) / len(question_quality),
            'information_extraction': sum(info_extraction) / len(info_extraction),
            'empathy': sum(empathy) / len(empathy),
            'efficiency': sum(efficiency) / len(efficiency),
            'coverage': sum(coverage) / len(coverage)
        }
        
        # Sort by score (lowest first)
        sorted_components = sorted(components.items(), key=lambda x: x[1])
        
        # Return bottom 3 as priorities
        priorities = []
        for component, score in sorted_components[:3]:
            if score < 0.7:  # Only if below threshold
                priorities.append(f"Improve {component.replace('_', ' ')}: current avg {score:.2f}")
        
        return priorities
    
    def _determine_trend(self, scores: List[float]) -> str:
        """Determine if scores are improving, declining, or stable."""
        if len(scores) < 3:
            return "insufficient_data"
        
        # Simple linear trend
        first_half = scores[:len(scores)//2]
        second_half = scores[len(scores)//2:]
        
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        
        diff = second_avg - first_avg
        
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "declining"
        else:
            return "stable"
    
    def _empty_report(self, num_sessions: int) -> OptimizationReport:
        """Create empty report when no successful sessions."""
        fallback_phases = {
            "intake_questioning": {
                "priority": 1,
                "status": "critical",
                "summary": "No successful sessions were available to assess intake questioning.",
                "signals": ["No successful sessions were analyzed"],
                "recommended_actions": [
                    {
                        "focus": "system_stability",
                        "signal": "no_data",
                        "recommended_action": "Restore a stable adversarial session flow before tuning intake prompts.",
                    }
                ],
                "target_files": [
                    "adversarial_harness/session.py",
                    "mediator/mediator.py",
                    "adversarial_harness/complainant.py",
                ],
            },
            "graph_analysis": {
                "priority": 2,
                "status": "critical",
                "summary": "No successful sessions were available to assess graph population or denoising.",
                "signals": ["No successful sessions were analyzed"],
                "recommended_actions": [
                    {
                        "focus": "system_stability",
                        "signal": "no_data",
                        "recommended_action": "Restore a stable adversarial session flow before tuning graph extraction and dependency tracking.",
                    }
                ],
                "target_files": [
                    "complaint_phases/knowledge_graph.py",
                    "complaint_phases/dependency_graph.py",
                    "complaint_phases/denoiser.py",
                    "mediator/mediator.py",
                ],
            },
            "document_generation": {
                "priority": 3,
                "status": "critical",
                "summary": "No successful sessions were available to assess drafting handoff quality.",
                "signals": ["No successful sessions were analyzed"],
                "recommended_actions": [
                    {
                        "focus": "system_stability",
                        "signal": "no_data",
                        "recommended_action": "Restore a stable adversarial session flow before tuning document-generation handoffs.",
                    }
                ],
                "target_files": [
                    "document_pipeline.py",
                    "document_optimization.py",
                    "mediator/formal_document.py",
                ],
            },
        }
        return OptimizationReport(
            timestamp=datetime.now(UTC).isoformat(),
            num_sessions_analyzed=0,
            average_score=0.0,
            score_trend="no_data",
            question_quality_avg=0.0,
            information_extraction_avg=0.0,
            empathy_avg=0.0,
            efficiency_avg=0.0,
            coverage_avg=0.0,
            common_weaknesses=["All sessions failed"],
            common_strengths=[],
            recommendations=["Debug system failures before optimization"],
            priority_improvements=["Fix system stability"],
            workflow_phase_plan=build_workflow_phase_plan(
                fallback_phases,
                status_rank={"critical": 0, "warning": 1, "ready": 2},
            ),
        )
    
    def get_history(self) -> List[OptimizationReport]:
        """Get optimization history."""
        return self.history.copy()
    
    def compare_reports(self, report1: OptimizationReport, report2: OptimizationReport) -> Dict[str, Any]:
        """
        Compare two optimization reports.
        
        Args:
            report1: Earlier report
            report2: Later report
            
        Returns:
            Dictionary with comparison metrics
        """
        return {
            'score_change': report2.average_score - report1.average_score,
            'question_quality_change': report2.question_quality_avg - report1.question_quality_avg,
            'info_extraction_change': report2.information_extraction_avg - report1.information_extraction_avg,
            'empathy_change': report2.empathy_avg - report1.empathy_avg,
            'efficiency_change': report2.efficiency_avg - report1.efficiency_avg,
            'coverage_change': report2.coverage_avg - report1.coverage_avg,
            'trend_change': f"{report1.score_trend} -> {report2.score_trend}"
        }
