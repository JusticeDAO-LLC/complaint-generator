from typing import Any, Dict, List


def normalize_intake_contradiction(contradiction: Any) -> Dict[str, Any]:
    candidate = contradiction if isinstance(contradiction, dict) else {}
    left_text = str(
        candidate.get("left_text")
        or candidate.get("left_fact_text")
        or candidate.get("statement_a")
        or ""
    ).strip()
    right_text = str(
        candidate.get("right_text")
        or candidate.get("right_fact_text")
        or candidate.get("statement_b")
        or ""
    ).strip()
    summary = str(candidate.get("summary") or "").strip()
    if not summary:
        if left_text and right_text:
            summary = f"{left_text} <> {right_text}"
        else:
            summary = left_text or right_text or "Unresolved contradiction"
    return {
        "summary": summary,
        "left_text": left_text,
        "right_text": right_text,
        "question": str(candidate.get("question") or candidate.get("question_text") or "").strip(),
        "severity": str(candidate.get("severity") or "").strip(),
        "category": str(candidate.get("category") or candidate.get("type") or "").strip(),
    }


def build_intake_status_summary(
    mediator: Any,
    *,
    include_iteration_count: bool = False,
) -> Dict[str, Any]:
    get_three_phase_status = getattr(mediator, "get_three_phase_status", None)
    if not callable(get_three_phase_status):
        return {}

    raw_status = get_three_phase_status()
    if not isinstance(raw_status, dict):
        return {}

    readiness = raw_status.get("intake_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    contradictions = raw_status.get("intake_contradictions")
    if not isinstance(contradictions, list):
        contradictions = (
            readiness.get("contradictions")
            if isinstance(readiness.get("contradictions"), list)
            else []
        )
    blockers = readiness.get("blockers")
    blocker_list = [str(item).strip() for item in blockers] if isinstance(blockers, list) else []
    normalized_contradictions = [
        normalize_intake_contradiction(item)
        for item in contradictions
        if isinstance(item, dict)
    ]

    try:
        score = float(readiness.get("score"))
    except (TypeError, ValueError):
        score = 0.0
    try:
        remaining_gap_count = int(readiness.get("remaining_gap_count"))
    except (TypeError, ValueError):
        remaining_gap_count = 0
    try:
        contradiction_count = int(readiness.get("contradiction_count"))
    except (TypeError, ValueError):
        contradiction_count = len(normalized_contradictions)

    summary = {
        "current_phase": str(raw_status.get("current_phase") or "").strip(),
        "ready_to_advance": bool(readiness.get("ready_to_advance", False)),
        "score": score,
        "remaining_gap_count": remaining_gap_count,
        "contradiction_count": contradiction_count,
        "blockers": blocker_list,
        "contradictions": normalized_contradictions,
    }
    if include_iteration_count:
        try:
            summary["iteration_count"] = int(raw_status.get("iteration_count"))
        except (TypeError, ValueError):
            summary["iteration_count"] = 0
    return summary


def build_intake_warning_entries(intake_status: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(intake_status, dict) or not intake_status:
        return []
    warnings: List[Dict[str, Any]] = []
    blockers = intake_status.get("blockers")
    blocker_list = blockers if isinstance(blockers, list) else []
    for blocker in blocker_list:
        blocker_text = str(blocker).strip()
        if not blocker_text:
            continue
        warnings.append(
            {
                "severity": "warning",
                "code": "intake_blocker",
                "message": f"Intake blocker: {blocker_text}",
            }
        )
    contradictions = intake_status.get("contradictions")
    contradiction_list = contradictions if isinstance(contradictions, list) else []
    for contradiction in contradiction_list[:2]:
        if not isinstance(contradiction, dict):
            continue
        summary = str(contradiction.get("summary") or "").strip() or "Unresolved intake contradiction"
        question = str(contradiction.get("question") or "").strip()
        message = summary if not question else f"{summary}. Clarify: {question}"
        warnings.append(
            {
                "severity": "warning",
                "code": "intake_contradiction",
                "message": message,
            }
        )
    return warnings