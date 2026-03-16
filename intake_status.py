from typing import Any, Dict, List


def _build_candidate_claim_summary(candidate_claims: Any) -> Dict[str, Any]:
    claims = candidate_claims if isinstance(candidate_claims, list) else []
    normalized_claims = [claim for claim in claims if isinstance(claim, dict)]
    claim_types: List[str] = []
    ambiguity_flag_counts: Dict[str, int] = {}
    confidence_pairs: List[tuple[float, str]] = []
    ambiguous_claim_types: List[str] = []
    total_confidence = 0.0

    for claim in normalized_claims:
        claim_type = str(claim.get("claim_type") or "").strip()
        if claim_type:
            claim_types.append(claim_type)

        ambiguity_flags = claim.get("ambiguity_flags")
        if isinstance(ambiguity_flags, list) and ambiguity_flags:
            if claim_type:
                ambiguous_claim_types.append(claim_type)
            for flag in ambiguity_flags:
                normalized_flag = str(flag or "").strip()
                if not normalized_flag:
                    continue
                ambiguity_flag_counts[normalized_flag] = (
                    ambiguity_flag_counts.get(normalized_flag, 0) + 1
                )

        try:
            confidence_value = float(claim.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence_value = 0.0
        total_confidence += confidence_value
        confidence_pairs.append((confidence_value, claim_type))

    confidence_pairs.sort(reverse=True)
    close_leading_claims = (
        len(confidence_pairs) > 1
        and confidence_pairs[0][0] >= 0.5
        and (confidence_pairs[0][0] - confidence_pairs[1][0]) < 0.15
    )
    top_confidence, top_claim_type = confidence_pairs[0] if confidence_pairs else (0.0, "")

    return {
        "count": len(normalized_claims),
        "claim_types": claim_types,
        "average_confidence": round(total_confidence / len(normalized_claims), 3)
        if normalized_claims
        else 0.0,
        "top_claim_type": top_claim_type,
        "top_confidence": round(top_confidence, 3),
        "ambiguous_claim_count": len(set(ambiguous_claim_types)),
        "ambiguity_flag_count": sum(ambiguity_flag_counts.values()),
        "ambiguity_flag_counts": ambiguity_flag_counts,
        "close_leading_claims": close_leading_claims,
    }


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
        "contradiction_id": str(candidate.get("contradiction_id") or candidate.get("dependency_id") or "").strip(),
        "summary": summary,
        "left_text": left_text,
        "right_text": right_text,
        "question": str(candidate.get("question") or candidate.get("question_text") or "").strip(),
        "severity": str(candidate.get("severity") or "").strip(),
        "category": str(candidate.get("category") or candidate.get("type") or "").strip(),
        "recommended_resolution_lane": str(candidate.get("recommended_resolution_lane") or "").strip(),
        "current_resolution_status": str(candidate.get("current_resolution_status") or candidate.get("status") or "").strip(),
        "external_corroboration_required": bool(candidate.get("external_corroboration_required", False)),
        "affected_claim_types": list(candidate.get("affected_claim_types")) if isinstance(candidate.get("affected_claim_types"), list) else [],
        "affected_element_ids": list(candidate.get("affected_element_ids")) if isinstance(candidate.get("affected_element_ids"), list) else [],
    }


def _extract_normalized_intake_contradictions(raw_status: Dict[str, Any]) -> List[Dict[str, Any]]:
    readiness = raw_status.get("intake_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    contradictions = raw_status.get("intake_contradictions")
    if isinstance(contradictions, dict):
        contradictions = contradictions.get("candidates")
    if not isinstance(contradictions, list):
        contradictions = (
            readiness.get("contradictions")
            if isinstance(readiness.get("contradictions"), list)
            else []
        )
    return [
        normalize_intake_contradiction(item)
        for item in contradictions
        if isinstance(item, dict)
    ]


def summarize_intake_contradictions(contradictions: Any) -> Dict[str, Any]:
    items = contradictions if isinstance(contradictions, list) else []
    normalized_items = [
        normalize_intake_contradiction(item)
        for item in items
        if isinstance(item, dict)
    ]
    lane_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    affected_claim_type_counts: Dict[str, int] = {}
    corroboration_required_count = 0

    for item in normalized_items:
        lane = str(item.get("recommended_resolution_lane") or "").strip()
        if lane:
            lane_counts[lane] = lane_counts.get(lane, 0) + 1

        status = str(item.get("current_resolution_status") or "").strip()
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1

        severity = str(item.get("severity") or "").strip()
        if severity:
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        if item.get("external_corroboration_required"):
            corroboration_required_count += 1

        for claim_type in item.get("affected_claim_types") or []:
            normalized_claim_type = str(claim_type or "").strip()
            if not normalized_claim_type:
                continue
            affected_claim_type_counts[normalized_claim_type] = (
                affected_claim_type_counts.get(normalized_claim_type, 0) + 1
            )

    return {
        "count": len(normalized_items),
        "lane_counts": lane_counts,
        "status_counts": status_counts,
        "severity_counts": severity_counts,
        "corroboration_required_count": corroboration_required_count,
        "affected_claim_type_counts": affected_claim_type_counts,
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
    blockers = readiness.get("blockers")
    blocker_list = [str(item).strip() for item in blockers] if isinstance(blockers, list) else []
    normalized_contradictions = _extract_normalized_intake_contradictions(raw_status)
    contradiction_summary = summarize_intake_contradictions(normalized_contradictions)

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
        "contradiction_summary": contradiction_summary,
        "blockers": blocker_list,
        "contradictions": normalized_contradictions,
        "criteria": (
            readiness.get("criteria")
            if isinstance(readiness.get("criteria"), dict)
            else {}
        ),
        "blocking_contradictions": (
            readiness.get("blocking_contradictions")
            if isinstance(readiness.get("blocking_contradictions"), list)
            else []
        ),
        "candidate_claim_count": int(readiness.get("candidate_claim_count", 0) or 0),
        "canonical_fact_count": int(readiness.get("canonical_fact_count", 0) or 0),
        "proof_lead_count": int(readiness.get("proof_lead_count", 0) or 0),
    }
    if include_iteration_count:
        try:
            summary["iteration_count"] = int(raw_status.get("iteration_count"))
        except (TypeError, ValueError):
            summary["iteration_count"] = 0
    return summary


def build_intake_case_review_summary(mediator: Any) -> Dict[str, Any]:
    """Return additive structured intake/evidence review data when available."""
    get_three_phase_status = getattr(mediator, "get_three_phase_status", None)
    if not callable(get_three_phase_status):
        return {}

    raw_status = get_three_phase_status()
    if not isinstance(raw_status, dict):
        return {}

    candidate_claims = raw_status.get("candidate_claims")
    intake_sections = raw_status.get("intake_sections")
    canonical_fact_summary = raw_status.get("canonical_fact_summary")
    canonical_fact_intent_summary = raw_status.get("canonical_fact_intent_summary")
    proof_lead_summary = raw_status.get("proof_lead_summary")
    proof_lead_intent_summary = raw_status.get("proof_lead_intent_summary")
    timeline_anchor_summary = raw_status.get("timeline_anchor_summary")
    harm_profile = raw_status.get("harm_profile")
    remedy_profile = raw_status.get("remedy_profile")
    intake_matching_summary = raw_status.get("intake_matching_summary")
    intake_legal_targeting_summary = raw_status.get("intake_legal_targeting_summary")
    intake_evidence_alignment_summary = raw_status.get("intake_evidence_alignment_summary")
    alignment_evidence_tasks = raw_status.get("alignment_evidence_tasks")
    alignment_task_updates = raw_status.get("alignment_task_updates")
    alignment_task_update_history = raw_status.get("alignment_task_update_history")
    question_candidate_summary = raw_status.get("question_candidate_summary")
    claim_support_packet_summary = raw_status.get("claim_support_packet_summary")
    candidate_claim_summary = _build_candidate_claim_summary(candidate_claims)
    contradiction_summary = summarize_intake_contradictions(
        _extract_normalized_intake_contradictions(raw_status)
    )

    return {
        "candidate_claims": candidate_claims if isinstance(candidate_claims, list) else [],
        "candidate_claim_summary": candidate_claim_summary,
        "intake_sections": intake_sections if isinstance(intake_sections, dict) else {},
        "canonical_fact_summary": (
            canonical_fact_summary if isinstance(canonical_fact_summary, dict) else {}
        ),
        "canonical_fact_intent_summary": (
            canonical_fact_intent_summary
            if isinstance(canonical_fact_intent_summary, dict)
            else {}
        ),
        "proof_lead_summary": (
            proof_lead_summary if isinstance(proof_lead_summary, dict) else {}
        ),
        "proof_lead_intent_summary": (
            proof_lead_intent_summary
            if isinstance(proof_lead_intent_summary, dict)
            else {}
        ),
        "timeline_anchor_summary": (
            timeline_anchor_summary if isinstance(timeline_anchor_summary, dict) else {}
        ),
        "harm_profile": (
            harm_profile if isinstance(harm_profile, dict) else {}
        ),
        "remedy_profile": (
            remedy_profile if isinstance(remedy_profile, dict) else {}
        ),
        "intake_matching_summary": (
            intake_matching_summary if isinstance(intake_matching_summary, dict) else {}
        ),
        "intake_legal_targeting_summary": (
            intake_legal_targeting_summary
            if isinstance(intake_legal_targeting_summary, dict)
            else {}
        ),
        "intake_evidence_alignment_summary": (
            intake_evidence_alignment_summary
            if isinstance(intake_evidence_alignment_summary, dict)
            else {}
        ),
        "alignment_evidence_tasks": (
            alignment_evidence_tasks if isinstance(alignment_evidence_tasks, list) else []
        ),
        "alignment_task_updates": (
            alignment_task_updates if isinstance(alignment_task_updates, list) else []
        ),
        "alignment_task_update_history": (
            alignment_task_update_history if isinstance(alignment_task_update_history, list) else []
        ),
        "question_candidate_summary": (
            question_candidate_summary if isinstance(question_candidate_summary, dict) else {}
        ),
        "contradiction_summary": contradiction_summary,
        "claim_support_packet_summary": (
            claim_support_packet_summary
            if isinstance(claim_support_packet_summary, dict)
            else {}
        ),
    }


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
