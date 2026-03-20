from __future__ import annotations

from typing import Any, Dict, List

from complaint_phases import ComplaintPhase


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            return default
    return default


def _safe_phase_call(phase_manager: Any, phase: ComplaintPhase, key: str) -> Any:
    if phase_manager is None:
        return None
    get_phase_data = getattr(phase_manager, "get_phase_data", None)
    if not callable(get_phase_data):
        return None
    try:
        return get_phase_data(phase, key)
    except Exception:
        return None


def build_workflow_phase_plan(
    phases: Dict[str, Dict[str, Any]],
    *,
    status_rank: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    normalized_phases = {
        str(name): dict(payload or {})
        for name, payload in (phases or {}).items()
        if isinstance(payload, dict)
    }
    if not normalized_phases:
        return {}

    normalized_status_rank = dict(status_rank or {"blocked": 0, "warning": 1, "ready": 2})
    recommended_order = sorted(
        normalized_phases.keys(),
        key=lambda name: (
            normalized_status_rank.get(str(normalized_phases[name].get("status") or "ready"), len(normalized_status_rank) + 1),
            int(normalized_phases[name].get("priority") or 0),
            name,
        ),
    )
    return {
        "recommended_order": recommended_order,
        "phases": normalized_phases,
    }


def humanize_workflow_priority_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    return text.replace("_", " ").replace("-", " ").title()


def normalize_workflow_phase_recommended_actions(phase_payload: Dict[str, Any]) -> List[str]:
    if not isinstance(phase_payload, dict):
        return []

    recommended_actions: List[str] = []
    for item in phase_payload.get("recommended_actions") or []:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("recommended_action") or item.get("action") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            recommended_actions.append(text)
    return recommended_actions


def resolve_prioritized_workflow_phase(workflow_phase_plan: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(workflow_phase_plan, dict):
        return {}

    phases = workflow_phase_plan.get("phases") if isinstance(workflow_phase_plan.get("phases"), dict) else {}
    ordered_phase_names = [
        phase_name
        for phase_name in (workflow_phase_plan.get("recommended_order") or [])
        if isinstance(phase_name, str) and isinstance(phases.get(phase_name), dict)
    ]
    if not ordered_phase_names:
        return {}

    prioritized_phase_name = next(
        (
            phase_name
            for phase_name in ordered_phase_names
            if str((phases.get(phase_name) or {}).get("status") or "ready").strip().lower() != "ready"
        ),
        ordered_phase_names[0],
    )
    prioritized_phase = dict(phases.get(prioritized_phase_name) or {})
    if not prioritized_phase:
        return {}

    prioritized_status = str(prioritized_phase.get("status") or "ready").strip().lower() or "ready"
    prioritized_signals = (
        dict(prioritized_phase.get("signals") or {})
        if isinstance(prioritized_phase.get("signals"), dict)
        else {}
    )
    return {
        "phase_name": prioritized_phase_name,
        "phase": prioritized_phase,
        "status": prioritized_status,
        "signals": prioritized_signals,
        "recommended_actions": normalize_workflow_phase_recommended_actions(prioritized_phase),
    }


def build_workflow_phase_warning_entries(workflow_phase_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(workflow_phase_plan, dict):
        return []

    phases = workflow_phase_plan.get("phases") if isinstance(workflow_phase_plan.get("phases"), dict) else {}
    warnings: List[Dict[str, Any]] = []
    for phase_name in workflow_phase_plan.get("recommended_order") or []:
        phase_payload = phases.get(phase_name)
        if not isinstance(phase_payload, dict):
            continue
        status = str(phase_payload.get("status") or "ready")
        if status == "ready":
            continue
        warnings.append(
            {
                "code": f"workflow_{phase_name}_{status}",
                "severity": status,
                "message": str(phase_payload.get("summary") or "").strip(),
                "phase": phase_name,
                "recommended_actions": list(phase_payload.get("recommended_actions") or []),
            }
        )
    return warnings


def build_graph_analysis_phase_guidance(phase_manager: Any, *, audience: str = "drafting") -> Dict[str, Any]:
    knowledge_graph = _safe_phase_call(phase_manager, ComplaintPhase.INTAKE, "knowledge_graph")
    dependency_graph = _safe_phase_call(phase_manager, ComplaintPhase.INTAKE, "dependency_graph")
    current_gaps = _safe_phase_call(phase_manager, ComplaintPhase.INTAKE, "current_gaps") or []
    remaining_gaps = _coerce_int(_safe_phase_call(phase_manager, ComplaintPhase.INTAKE, "remaining_gaps"), 0)
    graph_enhanced = bool(
        _safe_phase_call(phase_manager, ComplaintPhase.EVIDENCE, "knowledge_graph_enhanced")
    )

    knowledge_graph_available = bool(knowledge_graph)
    dependency_graph_available = bool(dependency_graph)
    current_gap_count = len(current_gaps) if isinstance(current_gaps, list) else 0

    if not knowledge_graph_available or not dependency_graph_available:
        status = "blocked"
        if audience == "review":
            summary = "Graph analysis is blocked because the intake knowledge graph or dependency graph is missing."
            actions = [
                "Build the intake knowledge graph and dependency graph before relying on cross-phase review outputs.",
            ]
        else:
            summary = "Knowledge-graph analysis is incomplete because the intake knowledge graph or dependency graph is missing."
            actions = [
                "Rebuild the intake knowledge graph and dependency graph before relying on formal drafting output.",
            ]
    elif remaining_gaps > 0 or current_gap_count > 0 or not graph_enhanced:
        status = "warning"
        unresolved_gap_count = max(remaining_gaps, current_gap_count)
        if audience == "review":
            summary = (
                f"Graph analysis still has {unresolved_gap_count} unresolved gap(s) or pending evidence-to-graph updates."
            )
            actions = [
                "Review intake graph inputs and refresh graph-backed evidence projections before final drafting.",
            ]
        else:
            summary = (
                f"Graph analysis still shows {unresolved_gap_count} unresolved gap(s) or unprojected evidence updates."
            )
            actions = [
                "Resolve remaining intake graph gaps and refresh graph projections before filing.",
            ]
            if not graph_enhanced:
                actions.append("Project newly collected evidence into the complaint knowledge graph.")
    else:
        status = "ready"
        if audience == "review":
            summary = "Graph analysis is present and does not currently show unresolved intake graph blockers."
        else:
            summary = "Graph analysis is available and does not show unresolved intake graph blockers."
        actions = []

    return {
        "priority": 0,
        "status": status,
        "summary": summary,
        "signals": {
            "knowledge_graph_available": knowledge_graph_available,
            "dependency_graph_available": dependency_graph_available,
            "remaining_gap_count": remaining_gaps,
            "current_gap_count": current_gap_count,
            "knowledge_graph_enhanced": graph_enhanced,
        },
        "recommended_actions": actions,
    }


def build_review_document_generation_phase_guidance(
    *,
    intake_status: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
) -> Dict[str, Any]:
    next_action = intake_status.get("next_action") if isinstance(intake_status.get("next_action"), dict) else {}
    next_action_name = str(next_action.get("action") or "").strip().lower()
    packet_summary = (
        intake_case_summary.get("claim_support_packet_summary")
        if isinstance(intake_case_summary.get("claim_support_packet_summary"), dict)
        else {}
    )
    unresolved_temporal_issue_count = _coerce_int(packet_summary.get("claim_support_unresolved_temporal_issue_count"), 0)
    unresolved_review_path_count = _coerce_int(packet_summary.get("claim_support_unresolved_without_review_path_count"), 0)
    proof_readiness_score = float(packet_summary.get("proof_readiness_score", 0.0) or 0.0)

    if next_action_name in {"generate_formal_complaint", "complete_evidence"} and unresolved_temporal_issue_count <= 0:
        status = "ready"
        summary = "Review state indicates the complaint can move into formal complaint drafting."
        actions: List[str] = []
    else:
        status = "warning"
        summary = "Document generation should wait until evidence review and packet blockers are reduced further."
        actions = [
            "Reduce unresolved packet blockers and confirm the evidence packet before generating a formal complaint.",
        ]

    return {
        "priority": 1,
        "status": status,
        "summary": summary,
        "signals": {
            "recommended_next_action": next_action_name,
            "proof_readiness_score": proof_readiness_score,
            "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
            "unresolved_without_review_path_count": unresolved_review_path_count,
        },
        "recommended_actions": actions,
    }


def build_drafting_document_generation_phase_guidance(
    *,
    drafting_readiness: Dict[str, Any],
    document_optimization: Dict[str, Any],
) -> Dict[str, Any]:
    sections = drafting_readiness.get("sections") if isinstance(drafting_readiness.get("sections"), dict) else {}
    claims = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []
    readiness_status = str(drafting_readiness.get("status") or "ready")
    section_warning_count = sum(
        1 for section in sections.values() if isinstance(section, dict) and str(section.get("status") or "ready") != "ready"
    )
    claim_warning_count = sum(
        1 for claim in claims if isinstance(claim, dict) and str(claim.get("status") or "ready") != "ready"
    )
    final_score = float(document_optimization.get("final_score") or 0.0) if document_optimization else 0.0
    target_score = float(document_optimization.get("target_score") or 0.0) if document_optimization else 0.0

    if readiness_status == "blocked":
        status = "blocked"
        summary = "Document generation is blocked because the formal complaint package still has blocking filing-readiness issues."
        actions = [
            "Resolve blocked claim or section readiness issues before using the generated complaint package.",
        ]
    elif readiness_status == "warning" or section_warning_count > 0 or claim_warning_count > 0:
        status = "warning"
        summary = (
            f"Document generation still has {section_warning_count} section warning(s) and {claim_warning_count} claim warning(s) to review."
        )
        actions = [
            "Review claims-for-relief, exhibits, and requested-relief warnings before filing.",
        ]
        if target_score > 0.0 and final_score < target_score:
            actions.append("Run another document-optimization pass or accept the draft with recorded review warnings.")
    else:
        status = "ready"
        summary = "Document generation is aligned with the current filing-readiness checks."
        actions = []

    return {
        "priority": 1,
        "status": status,
        "summary": summary,
        "signals": {
            "drafting_readiness_status": readiness_status,
            "warning_count": int(drafting_readiness.get("warning_count") or 0),
            "section_warning_count": section_warning_count,
            "claim_warning_count": claim_warning_count,
            "optimization_final_score": final_score,
            "optimization_target_score": target_score,
        },
        "recommended_actions": actions,
    }