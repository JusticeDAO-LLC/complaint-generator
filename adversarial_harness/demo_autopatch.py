"""Shared demo autopatch runner for adversarial harness flows."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any, Callable, Dict, Sequence

from adversarial_harness import AdversarialHarness, Optimizer
from mediator import Mediator


def _build_runtime_optimization_guidance(
    workflow_bundle: Dict[str, Any] | None,
    report_payload: Dict[str, Any] | None,
) -> Dict[str, Any]:
    bundle = workflow_bundle if isinstance(workflow_bundle, dict) else {}
    report = report_payload if isinstance(report_payload, dict) else {}
    shared_context = bundle.get("shared_context") if isinstance(bundle.get("shared_context"), dict) else {}
    document_handoff_summary = (
        report.get("document_handoff_summary")
        if isinstance(report.get("document_handoff_summary"), dict)
        else shared_context.get("document_handoff_summary")
    )
    complaint_targets = (
        report.get("complaint_type_generalization_summary")
        if isinstance(report.get("complaint_type_generalization_summary"), dict)
        else shared_context.get("complaint_type_generalization_summary")
    )
    evidence_targets = (
        report.get("evidence_modality_generalization_summary")
        if isinstance(report.get("evidence_modality_generalization_summary"), dict)
        else shared_context.get("evidence_modality_generalization_summary")
    )
    phase_scorecards = (
        bundle.get("phase_scorecards")
        if isinstance(bundle.get("phase_scorecards"), dict)
        else report.get("phase_scorecards")
    )
    workflow_phase_plan = (
        bundle.get("workflow_phase_plan")
        if isinstance(bundle.get("workflow_phase_plan"), dict)
        else report.get("workflow_phase_plan")
    )
    cross_phase_findings = bundle.get("cross_phase_findings")
    if not isinstance(cross_phase_findings, list):
        cross_phase_findings = report.get("cross_phase_findings")
    cross_phase_findings = [str(item).strip() for item in list(cross_phase_findings or []) if str(item).strip()]
    document_evidence_targeting_summary = (
        report.get("document_evidence_targeting_summary")
        if isinstance(report.get("document_evidence_targeting_summary"), dict)
        else shared_context.get("document_evidence_targeting_summary")
    )
    workflow_targeting_summary = (
        report.get("workflow_targeting_summary")
        if isinstance(report.get("workflow_targeting_summary"), dict)
        else shared_context.get("workflow_targeting_summary")
    )
    document_workflow_execution_summary = (
        report.get("document_workflow_execution_summary")
        if isinstance(report.get("document_workflow_execution_summary"), dict)
        else shared_context.get("document_workflow_execution_summary")
    )
    document_execution_drift_summary = (
        report.get("document_execution_drift_summary")
        if isinstance(report.get("document_execution_drift_summary"), dict)
        else shared_context.get("document_execution_drift_summary")
    )

    if not any(
        (
            workflow_phase_plan,
            phase_scorecards,
            document_handoff_summary,
            complaint_targets,
            evidence_targets,
            cross_phase_findings,
            document_evidence_targeting_summary,
            workflow_targeting_summary,
            document_workflow_execution_summary,
            document_execution_drift_summary,
        )
    ):
        return {}

    return {
        "workflow_phase_plan": dict(workflow_phase_plan or {}),
        "phase_scorecards": dict(phase_scorecards or {}),
        "cross_phase_findings": cross_phase_findings,
        "workflow_action_queue": list(bundle.get("workflow_action_queue") or report.get("workflow_action_queue") or []),
        "document_handoff_summary": dict(document_handoff_summary or {}),
        "workflow_targeting_summary": dict(workflow_targeting_summary or {}),
        "document_evidence_targeting_summary": dict(document_evidence_targeting_summary or {}),
        "document_workflow_execution_summary": dict(document_workflow_execution_summary or {}),
        "document_execution_drift_summary": dict(document_execution_drift_summary or {}),
        "complaint_type_generalization_summary": dict(complaint_targets or {}),
        "evidence_modality_generalization_summary": dict(evidence_targets or {}),
    }


class DemoBatchLLMBackend:
    def __init__(self, response_template: str = "Mock response"):
        self.response_template = response_template

    def __call__(self, prompt: str) -> str:
        lower_prompt = prompt.lower()
        if "hacc" in lower_prompt or "grievance" in lower_prompt or "housing authority" in lower_prompt:
            if "generate" in lower_prompt and "complaint" in lower_prompt:
                return (
                    "I asked HACC for a grievance hearing after I complained about discriminatory treatment and the denial "
                    "of housing assistance. HACC sent a notice of adverse action, did not clearly honor my appeal rights, "
                    "and kept moving forward after my complaint."
                )
            if "appeal rights" in lower_prompt or "appeal" in lower_prompt or "deadline" in lower_prompt:
                return (
                    "I received a notice of adverse action on March 3, 2026. It mentioned an appeal, but it did not clearly "
                    "explain the deadline or hearing steps. I kept the notice as a PDF."
                )
            if "hearing" in lower_prompt or "review" in lower_prompt:
                return (
                    "I requested a grievance hearing by email on March 5, 2026 and followed up by phone on March 8, 2026. "
                    "HACC denied or ignored the request in a response email dated March 10, 2026."
                )
            if "who" in lower_prompt or "title" in lower_prompt or "role" in lower_prompt:
                return (
                    "Property Specialist Dana Morris sent the adverse-action notice, and Hearing Coordinator Alex Chen "
                    "handled the review request."
                )
            if "document" in lower_prompt or "email" in lower_prompt or "notice" in lower_prompt or "upload" in lower_prompt:
                return (
                    "I have the March 3 adverse-action notice, the March 5 hearing-request email, the March 10 response "
                    "email, and my earlier discrimination complaint."
                )
            if "harm" in lower_prompt or "remedy" in lower_prompt or "relief" in lower_prompt:
                return (
                    "This put my housing assistance at risk and caused serious stress. I want the denial reversed, a fair "
                    "hearing, protection from retaliation, and compensation for the harm."
                )
            if "protected activity" in lower_prompt or "because" in lower_prompt or "sequence" in lower_prompt:
                return (
                    "I complained about discrimination first, then HACC sent the adverse-action notice, and after I asked "
                    "for a hearing HACC rejected or ignored the request."
                )
        if "generate" in lower_prompt and "complaint" in lower_prompt:
            return (
                "I reported discrimination to human resources after my supervisor denied a promotion "
                "and made repeated comments about women not being fit for leadership. Two days later I was terminated."
            )
        if "scores:" in prompt or "evaluate" in lower_prompt:
            return """SCORES:
question_quality: 0.72
information_extraction: 0.74
empathy: 0.68
efficiency: 0.69
coverage: 0.73

FEEDBACK:
Good coverage, but the mediator can ask more specific timeline and witness questions.

STRENGTHS:
- Clear questioning
- Good coverage of key issues

WEAKNESSES:
- Timeline probing could be more specific
- Witness and documentary evidence follow-ups could be stronger

SUGGESTIONS:
- Add a dedicated timeline probe after the first retaliation allegation
- Ask directly about documentary evidence and witnesses earlier in the loop
"""
        if "when" in lower_prompt or "date" in lower_prompt:
            return "The termination happened on March 5, 2026, two days after I complained to HR."
        if "witness" in lower_prompt:
            return "My coworker Sarah Lee witnessed the retaliation discussion."
        if "document" in lower_prompt or "email" in lower_prompt:
            return "I have the HR complaint email and the termination notice."
        return self.response_template


class DemoBatchKnowledgeGraph:
    def summary(self) -> Dict[str, Any]:
        return {"total_entities": 5, "total_relationships": 4}


class DemoBatchDependencyGraph:
    def summary(self) -> Dict[str, Any]:
        return {"total_nodes": 4, "total_dependencies": 3}


class DemoBatchPhaseManager:
    def get_phase_data(self, phase: Any, key: str) -> Any:
        if key == "knowledge_graph":
            return DemoBatchKnowledgeGraph()
        if key == "dependency_graph":
            return DemoBatchDependencyGraph()
        return None


class DemoBatchMediator:
    def __init__(self):
        self.phase_manager = DemoBatchPhaseManager()
        self.questions_asked = 0

    def start_three_phase_process(self, complaint_text: str) -> Dict[str, Any]:
        return {
            "phase": "intake",
            "initial_questions": [
                {"question": "When exactly did the retaliation happen?", "type": "timeline"}
            ],
        }

    def process_denoising_answer(self, question: Dict[str, Any], answer: str) -> Dict[str, Any]:
        self.questions_asked += 1
        if self.questions_asked == 1:
            next_questions = [
                {"question": "Who witnessed the retaliation or has documents about it?", "type": "evidence"}
            ]
        else:
            next_questions = []
        return {
            "converged": self.questions_asked >= 2,
            "ready_for_evidence_phase": self.questions_asked >= 2,
            "next_questions": next_questions,
        }

    def get_three_phase_status(self) -> Dict[str, Any]:
        return {
            "current_phase": "intake",
            "iteration_count": self.questions_asked,
        }


class DemoPatchOptimizer:
    def __init__(self, *, project_root: Path, output_dir: Path, marker_prefix: str = "Demo autopatch recommendation"):
        self.project_root = project_root
        self.output_dir = output_dir
        self.marker_prefix = marker_prefix

    def optimize(self, task: Any) -> Any:
        target_path = Path(task.target_files[0])
        absolute_target = target_path if target_path.is_absolute() else self.project_root / target_path
        original_text = absolute_target.read_text(encoding="utf-8")
        report_summary = task.metadata.get("report_summary") or {}
        recommendations = list(report_summary.get("recommendations") or [])
        recommendation = recommendations[0] if recommendations else "Improve adversarial session follow-up quality."

        marker = f"# {self.marker_prefix}: {recommendation.strip()}"
        if marker in original_text:
            modified_text = original_text
        else:
            modified_text = original_text.rstrip("\n") + "\n\n" + marker + "\n"

        relative_target = absolute_target.relative_to(self.project_root)
        diff_text = "".join(
            difflib.unified_diff(
                original_text.splitlines(keepends=True),
                modified_text.splitlines(keepends=True),
                fromfile=f"a/{relative_target.as_posix()}",
                tofile=f"b/{relative_target.as_posix()}",
            )
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        patch_name = f"adversarial_autopatch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.patch"
        patch_path = self.output_dir / patch_name
        patch_path.write_text(diff_text, encoding="utf-8")
        patch_cid = "demo-" + hashlib.sha1(diff_text.encode("utf-8")).hexdigest()[:16]
        return SimpleNamespace(
            success=True,
            patch_path=patch_path,
            patch_cid=patch_cid,
            metadata={"demo": True, "patch_size_bytes": patch_path.stat().st_size},
        )


def _serialize_autopatch_result(result: Any) -> Dict[str, Any]:
    return {
        "success": bool(getattr(result, "success", False)),
        "patch_path": str(getattr(result, "patch_path", "")),
        "patch_cid": str(getattr(result, "patch_cid", "")),
        "metadata": dict(getattr(result, "metadata", {}) or {}),
    }


def _run_phase_autopatches(
    *,
    optimizer: Optimizer,
    results: Sequence[Any],
    patch_optimizer: Any,
    method: str = "actor_critic",
) -> tuple[list[Dict[str, Any]], OptimizationReport]:
    phase_tasks, report = optimizer.build_phase_patch_tasks(
        list(results),
        method=method,
    )
    phase_payloads: list[Dict[str, Any]] = []
    for task in phase_tasks:
        phase_result = patch_optimizer.optimize(task)
        phase_payload = _serialize_autopatch_result(phase_result)
        phase_payload.update(
            {
                "phase": str(task.metadata.get("workflow_phase") or ""),
                "phase_status": str(task.metadata.get("workflow_phase_status") or "ready"),
                "phase_priority": int(task.metadata.get("workflow_phase_priority") or 0),
                "target_files": [str(path) for path in list(getattr(task, "target_files", []) or [])],
            }
        )
        phase_payloads.append(phase_payload)
    return phase_payloads, report


def _summarize_runtime_health(results: Sequence[Any]) -> Dict[str, Any]:
    critic_fallback_sessions = 0
    session_errors = 0

    for result in results:
        if not getattr(result, 'success', False) or getattr(result, 'error', None):
            session_errors += 1
        critic_score = getattr(result, 'critic_score', None)
        feedback = str(getattr(critic_score, 'feedback', '') or '').strip().lower()
        if feedback.startswith('evaluation fallback - llm unavailable'):
            critic_fallback_sessions += 1

    degraded_reasons = []
    if critic_fallback_sessions:
        degraded_reasons.append('critic_fallback')
    if session_errors:
        degraded_reasons.append('session_errors')

    return {
        'degraded': bool(degraded_reasons),
        'degraded_reasons': degraded_reasons,
        'critic_fallback_sessions': critic_fallback_sessions,
        'session_error_count': session_errors,
    }


def _backend_label(backend: Any) -> str:
    return str(getattr(backend, 'id', '') or getattr(backend, '__class__', type(backend)).__name__)


def _probe_backend(backend: Any, prompt: str) -> tuple[bool, str]:
    try:
        text = backend(prompt)
    except Exception as exc:
        return False, str(exc)
    if not isinstance(text, str) or not text.strip():
        return False, 'empty_generation'
    return True, ''


def _select_live_backend(backends: Sequence[Any], probe_prompt: str) -> tuple[Any, list[Dict[str, Any]], bool]:
    attempts: list[Dict[str, Any]] = []
    for backend in backends:
        ok, error = _probe_backend(backend, probe_prompt)
        attempts.append({
            'backend_id': _backend_label(backend),
            'ok': ok,
            'error': error,
        })
        if ok:
            return backend, attempts, True
    return backends[0], attempts, False


def _collect_live_preflight_warnings(backends: Sequence[Any]) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()

    def _add(message: str) -> None:
        text = str(message or '').strip()
        if text and text not in seen:
            seen.add(text)
            warnings.append(text)

    hf_token = (
        os.getenv('HF_TOKEN', '').strip()
        or os.getenv('HUGGINGFACE_HUB_TOKEN', '').strip()
        or os.getenv('HUGGINGFACE_API_KEY', '').strip()
        or os.getenv('HF_API_TOKEN', '').strip()
    )

    for backend in backends:
        provider = str(getattr(backend, 'provider', '') or '').strip().lower()
        backend_id = _backend_label(backend)
        if provider in {'hf_inference', 'hf_router', 'huggingface_inference', 'huggingface_router'} and not hf_token:
            _add(
                f"{backend_id}: Hugging Face router requires HF_TOKEN or HUGGINGFACE_HUB_TOKEN in the environment."
            )
        elif provider in {'codex', 'codex_cli'} and shutil.which('codex') is None:
            _add(f"{backend_id}: Codex CLI backend requires a codex binary on PATH.")
        elif provider in {'accelerate', 'ipfs_accelerate_py'}:
            _add(
                f"{backend_id}: accelerate is best-effort and may degrade to local_fallback when distributed inference is unavailable."
            )

    return warnings


def run_demo_autopatch_batch(
    *,
    project_root: str | Path,
    output_dir: str | Path,
    target_file: str | Path = "adversarial_harness/session.py",
    num_sessions: int = 1,
    max_turns: int = 2,
    max_parallel: int = 1,
    session_state_dir: str | Path | None = None,
    marker_prefix: str = "Demo autopatch recommendation",
    phase_mode: str = "single",
) -> Dict[str, Any]:
    resolved_project_root = Path(project_root)
    resolved_output_dir = Path(output_dir)
    resolved_session_state_dir = Path(session_state_dir) if session_state_dir is not None else resolved_output_dir / "sessions"

    harness = AdversarialHarness(
        llm_backend_complainant=DemoBatchLLMBackend(),
        llm_backend_critic=DemoBatchLLMBackend(),
        mediator_factory=DemoBatchMediator,
        max_parallel=max_parallel,
        session_state_dir=str(resolved_session_state_dir),
    )

    results = harness.run_batch(
        num_sessions=num_sessions,
        seed_complaints=[
            {
                "type": "employment_discrimination",
                "summary": "Retaliation after reporting discrimination",
                "key_facts": {"employer": "Acme Corp", "action": "termination"},
            }
        ],
        personalities=["cooperative"],
        max_turns_per_session=max_turns,
    )

    optimizer = Optimizer()
    report = optimizer.analyze(results)
    workflow_bundle = optimizer.build_workflow_optimization_bundle(results, report=report).to_dict()
    normalized_phase_mode = str(phase_mode or "single").strip().lower().replace("-", "_")
    if normalized_phase_mode not in {"single", "workflow"}:
        raise ValueError(f"Unsupported phase mode: {phase_mode}")
    patch_optimizer = DemoPatchOptimizer(
        project_root=resolved_project_root,
        output_dir=resolved_output_dir,
        marker_prefix=marker_prefix,
    )
    autopatch_result = optimizer.run_agentic_autopatch(
        results,
        target_files=[str(target_file)],
        method="actor_critic",
        llm_router=object(),
        optimizer=patch_optimizer,
        report=report,
    )
    phase_payloads: list[Dict[str, Any]] = []
    if normalized_phase_mode == "workflow":
        phase_payloads, report = _run_phase_autopatches(
            optimizer=optimizer,
            results=results,
            patch_optimizer=patch_optimizer,
            method="actor_critic",
        )

    payload = {
        "num_results": len(results),
        "report": report.to_dict(),
        "workflow_optimization_bundle": workflow_bundle,
        "optimization_guidance": _build_runtime_optimization_guidance(workflow_bundle, report.to_dict()),
        "autopatch": _serialize_autopatch_result(autopatch_result),
        "phase_mode": normalized_phase_mode,
        "phase_tasks": phase_payloads,
        "runtime": {
            "mode": "demo",
            **_summarize_runtime_health(results),
        },
    }
    summary_path = resolved_output_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def run_adversarial_autopatch_batch(
    *,
    project_root: str | Path,
    output_dir: str | Path,
    target_file: str | Path = "adversarial_harness/session.py",
    num_sessions: int = 1,
    max_turns: int = 2,
    max_parallel: int = 1,
    session_state_dir: str | Path | None = None,
    marker_prefix: str = "Adversarial autopatch recommendation",
    demo_backend: bool = False,
    backends: Sequence[Any] | None = None,
    mediator_factory: Callable[..., Any] | None = None,
    probe_prompt: str = 'Reply with exactly OK.',
    phase_mode: str = "single",
) -> Dict[str, Any]:
    if demo_backend or not backends:
        payload = run_demo_autopatch_batch(
            project_root=project_root,
            output_dir=output_dir,
            target_file=target_file,
            num_sessions=num_sessions,
            max_turns=max_turns,
            max_parallel=max_parallel,
            session_state_dir=session_state_dir,
            marker_prefix=marker_prefix,
            phase_mode=phase_mode,
        )
        return payload

    resolved_project_root = Path(project_root)
    resolved_output_dir = Path(output_dir)
    resolved_session_state_dir = Path(session_state_dir) if session_state_dir is not None else resolved_output_dir / "sessions"
    resolved_backends = list(backends)
    preflight_warnings = _collect_live_preflight_warnings(resolved_backends)
    shared_backend, probe_attempts, selected_backend_healthy = _select_live_backend(resolved_backends, probe_prompt)

    def _default_mediator_factory(**kwargs: Any) -> Mediator:
        return Mediator(backends=list(resolved_backends))

    harness = AdversarialHarness(
        llm_backend_complainant=shared_backend,
        llm_backend_critic=shared_backend,
        mediator_factory=mediator_factory or _default_mediator_factory,
        max_parallel=max_parallel,
        session_state_dir=str(resolved_session_state_dir),
    )

    results = harness.run_batch(
        num_sessions=num_sessions,
        seed_complaints=[
            {
                "type": "employment_discrimination",
                "summary": "Retaliation after reporting discrimination",
                "key_facts": {"employer": "Acme Corp", "action": "termination"},
            }
        ],
        personalities=["cooperative"],
        max_turns_per_session=max_turns,
    )

    optimizer = Optimizer()
    report = optimizer.analyze(results)
    workflow_bundle = optimizer.build_workflow_optimization_bundle(results, report=report).to_dict()
    normalized_phase_mode = str(phase_mode or "single").strip().lower().replace("-", "_")
    if normalized_phase_mode not in {"single", "workflow"}:
        raise ValueError(f"Unsupported phase mode: {phase_mode}")
    patch_optimizer = DemoPatchOptimizer(
        project_root=resolved_project_root,
        output_dir=resolved_output_dir,
        marker_prefix=marker_prefix,
    )
    autopatch_result = optimizer.run_agentic_autopatch(
        results,
        target_files=[str(target_file)],
        method="actor_critic",
        llm_router=object(),
        optimizer=patch_optimizer,
        report=report,
    )
    phase_payloads: list[Dict[str, Any]] = []
    if normalized_phase_mode == "workflow":
        phase_payloads, report = _run_phase_autopatches(
            optimizer=optimizer,
            results=results,
            patch_optimizer=patch_optimizer,
            method="actor_critic",
        )

    payload = {
        "num_results": len(results),
        "report": report.to_dict(),
        "workflow_optimization_bundle": workflow_bundle,
        "optimization_guidance": _build_runtime_optimization_guidance(workflow_bundle, report.to_dict()),
        "autopatch": _serialize_autopatch_result(autopatch_result),
        "phase_mode": normalized_phase_mode,
        "phase_tasks": phase_payloads,
        "runtime": {
            "mode": "live",
            "backend_count": len(resolved_backends),
            "backend_type": type(shared_backend).__name__,
            "selected_backend_id": _backend_label(shared_backend),
            "selected_backend_healthy": selected_backend_healthy,
            "preflight_warnings": preflight_warnings,
            "probe_attempts": probe_attempts,
            **_summarize_runtime_health(results),
        },
    }
    if not selected_backend_healthy:
        payload["runtime"]["degraded"] = True
        payload["runtime"].setdefault("degraded_reasons", []).insert(0, "backend_probe_failed")
    summary_path = resolved_output_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
