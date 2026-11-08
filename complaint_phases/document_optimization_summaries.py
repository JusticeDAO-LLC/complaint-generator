"""Document-optimization summary builders extracted from the owner module.

The entry points below keep their original bodies. Private helpers that still
live on the document-optimization owner are resolved when a function runs,
after both modules have finished loading.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from intake_status import summarize_temporal_issue_registry


def _optimizer_helper(name: str):
    """Return a helper that remains defined on the document-optimization owner."""
    from complaint_phases import document_optimization as owner

    return getattr(owner, name)


def _unique_preserving_order(values: Iterable[str]) -> List[str]:
    return _optimizer_helper("_unique_preserving_order")(values)


def _dedupe_text_values(values: Iterable[Any]) -> List[str]:
    return _optimizer_helper("_dedupe_text_values")(values)


def _format_timeline_date(value: Any) -> str:
    return _optimizer_helper("_format_timeline_date")(value)


def _chronology_fact_label(fact: Dict[str, Any]) -> str:
    return _optimizer_helper("_chronology_fact_label")(fact)


def _join_chronology_segments(segments: List[str]) -> str:
    return _optimizer_helper("_join_chronology_segments")(segments)


def _claim_temporal_gap_focus(claim_type: str, claim_name: str) -> Dict[str, set[str]]:
    return _optimizer_helper("_claim_temporal_gap_focus")(claim_type, claim_name)


def _build_workflow_targeting_summary(
    *,
    existing_summary: Any,
    document_evidence_targeting_summary: Any,
) -> Dict[str, Any]:
    existing = existing_summary if isinstance(existing_summary, dict) else {}
    document = (
        document_evidence_targeting_summary
        if isinstance(document_evidence_targeting_summary, dict)
        else {}
    )
    phase_summaries = {
        "intake_questioning": dict((existing.get("phase_summaries") or {}).get("intake_questioning") or {}),
        "graph_analysis": dict((existing.get("phase_summaries") or {}).get("graph_analysis") or {}),
        "document_generation": dict(document),
    }
    phase_counts = {
        phase_name: int((payload or {}).get("count") or 0)
        for phase_name, payload in phase_summaries.items()
    }
    total_target_count = sum(phase_counts.values())
    prioritized_phases = [
        phase_name
        for phase_name, count in sorted(
            phase_counts.items(),
            key=lambda item: (-int(item[1] or 0), item[0]),
        )
        if int(count or 0) > 0
    ]

    shared_claim_element_counts: Dict[str, int] = {}
    shared_focus_area_counts: Dict[str, int] = {}
    for payload in phase_summaries.values():
        for claim_element_id, count in dict(payload.get("claim_element_counts") or {}).items():
            normalized = str(claim_element_id or "").strip()
            if not normalized:
                continue
            shared_claim_element_counts[normalized] = (
                shared_claim_element_counts.get(normalized, 0) + int(count or 0)
            )
        focus_counts = {}
        if "focus_area_counts" in payload:
            focus_counts = dict(payload.get("focus_area_counts") or {})
        elif "objective_counts" in payload:
            focus_counts = dict(payload.get("objective_counts") or {})
        elif "focus_section_counts" in payload:
            focus_counts = dict(payload.get("focus_section_counts") or {})
        for focus_area, count in focus_counts.items():
            normalized = str(focus_area or "").strip()
            if not normalized:
                continue
            shared_focus_area_counts[normalized] = (
                shared_focus_area_counts.get(normalized, 0) + int(count or 0)
            )

    return {
        "count": total_target_count,
        "phase_counts": phase_counts,
        "prioritized_phases": prioritized_phases,
        "shared_claim_element_counts": shared_claim_element_counts,
        "shared_focus_area_counts": shared_focus_area_counts,
        "phase_summaries": phase_summaries,
    }


def _build_document_grounding_improvement_summary(
    *,
    initial_document_provenance_summary: Any,
    final_document_provenance_summary: Any,
    workflow_optimization_guidance: Any = None,
) -> Dict[str, Any]:
    initial_summary = (
        initial_document_provenance_summary
        if isinstance(initial_document_provenance_summary, dict)
        else {}
    )
    final_summary = (
        final_document_provenance_summary
        if isinstance(final_document_provenance_summary, dict)
        else {}
    )
    guidance = workflow_optimization_guidance if isinstance(workflow_optimization_guidance, dict) else {}
    if not initial_summary and not final_summary:
        return {}

    initial_ratio = float(initial_summary.get("fact_backed_ratio") or 0.0)
    final_ratio = float(final_summary.get("fact_backed_ratio") or 0.0)
    delta = round(final_ratio - initial_ratio, 4)
    evidence_workflow_action_queue = (
        guidance.get("evidence_workflow_action_queue")
        if isinstance(guidance.get("evidence_workflow_action_queue"), list)
        else []
    )
    workflow_action_queue = (
        guidance.get("workflow_action_queue")
        if isinstance(guidance.get("workflow_action_queue"), list)
        else []
    )
    recovery_actions = [
        action
        for action in [*evidence_workflow_action_queue, *workflow_action_queue]
        if isinstance(action, dict)
        and (
            bool(action.get("document_grounding_recovery"))
            or str(action.get("action_code") or "").strip().lower() == "recover_document_grounding"
            or str(action.get("action") or "").strip().lower() == "recover document grounding"
        )
    ]
    refinement_actions = [
        action
        for action in [*evidence_workflow_action_queue, *workflow_action_queue]
        if isinstance(action, dict)
        and (
            bool(action.get("document_grounding_strategy_refinement"))
            or str(action.get("action_code") or "").strip().lower() == "refine_document_grounding_strategy"
            or str(action.get("action") or "").strip().lower() == "refine document grounding strategy"
        )
    ]
    targeted_claim_elements = _unique_preserving_order(
        str((action or {}).get("claim_element_id") or "").strip()
        for action in recovery_actions
        if isinstance(action, dict)
    )
    preferred_support_kinds = _unique_preserving_order(
        str((action or {}).get("preferred_support_kind") or "").strip()
        for action in recovery_actions
        if isinstance(action, dict)
    )
    learned_support_kinds = _unique_preserving_order(
        str(
            (action or {}).get("learned_support_kind")
            or (action or {}).get("suggested_support_kind")
            or ""
        ).strip()
        for action in refinement_actions
        if isinstance(action, dict)
    )
    improved_flag = delta > 0.02
    regressed_flag = delta < -0.02
    stalled_flag = not improved_flag and not regressed_flag
    low_grounding_resolved_flag = bool(
        initial_summary.get("low_grounding_flag") and not final_summary.get("low_grounding_flag")
    )
    return {
        "initial_fact_backed_ratio": round(initial_ratio, 4),
        "final_fact_backed_ratio": round(final_ratio, 4),
        "fact_backed_ratio_delta": delta,
        "initial_low_grounding_flag": bool(initial_summary.get("low_grounding_flag")),
        "final_low_grounding_flag": bool(final_summary.get("low_grounding_flag")),
        "recovery_action_count": len(recovery_actions),
        "refinement_action_count": len(refinement_actions),
        "recovery_attempted_flag": bool(recovery_actions),
        "targeted_claim_elements": targeted_claim_elements,
        "preferred_support_kinds": preferred_support_kinds,
        "learned_support_kinds": learned_support_kinds,
        "learned_support_kind": learned_support_kinds[0] if learned_support_kinds else "",
        "improved_flag": improved_flag,
        "regressed_flag": regressed_flag,
        "stalled_flag": stalled_flag,
        "low_grounding_resolved_flag": low_grounding_resolved_flag,
    }


def _build_document_grounding_lane_outcome_summary(
    *,
    document_grounding_improvement_summary: Any,
    document_workflow_execution_summary: Any,
) -> Dict[str, Any]:
    improvement_summary = (
        document_grounding_improvement_summary
        if isinstance(document_grounding_improvement_summary, dict)
        else {}
    )
    execution_summary = (
        document_workflow_execution_summary
        if isinstance(document_workflow_execution_summary, dict)
        else {}
    )
    if not improvement_summary and not execution_summary:
        return {}

    preferred_support_kinds = (
        improvement_summary.get("preferred_support_kinds")
        if isinstance(improvement_summary.get("preferred_support_kinds"), list)
        else []
    )
    learned_support_kind = str(improvement_summary.get("learned_support_kind") or "").strip()
    attempted_support_kind = str(
        execution_summary.get("first_preferred_support_kind")
        or (preferred_support_kinds[0] if preferred_support_kinds else "")
        or ""
    ).strip()
    targeted_claim_elements = _unique_preserving_order(
        str(item).strip()
        for item in (improvement_summary.get("targeted_claim_elements") or [])
        if str(item).strip()
    )
    if bool(improvement_summary.get("improved_flag")):
        outcome_status = "improved"
    elif bool(improvement_summary.get("regressed_flag")):
        outcome_status = "regressed"
    else:
        outcome_status = "stalled"
    learned_support_lane_attempted_flag = bool(
        learned_support_kind and attempted_support_kind and learned_support_kind == attempted_support_kind
    )
    learned_support_lane_effective_flag = bool(
        learned_support_lane_attempted_flag and bool(improvement_summary.get("improved_flag"))
    )
    recommended_future_claim_element = ""
    if len(targeted_claim_elements) > 1:
        recommended_future_claim_element = str(targeted_claim_elements[1] or "").strip()
    first_targeted_claim_element = str(execution_summary.get("first_targeted_claim_element") or "").strip()
    if (
        not recommended_future_claim_element
        and first_targeted_claim_element
        and first_targeted_claim_element not in {"", str(targeted_claim_elements[0] if targeted_claim_elements else "")}
    ):
        recommended_future_claim_element = first_targeted_claim_element
    return {
        "attempted_support_kind": attempted_support_kind,
        "outcome_status": outcome_status,
        "fact_backed_ratio_delta": float(improvement_summary.get("fact_backed_ratio_delta") or 0.0),
        "targeted_claim_elements": targeted_claim_elements,
        "learned_support_kind": learned_support_kind,
        "learned_support_lane_attempted_flag": learned_support_lane_attempted_flag,
        "learned_support_lane_effective_flag": learned_support_lane_effective_flag,
        "recommended_future_support_kind": (
            attempted_support_kind
            if outcome_status == "improved"
            else (learned_support_kind if learned_support_kind and learned_support_kind != attempted_support_kind else "")
        ),
        "recommended_future_claim_element": recommended_future_claim_element,
        "improved_flag": bool(improvement_summary.get("improved_flag")),
        "regressed_flag": bool(improvement_summary.get("regressed_flag")),
        "stalled_flag": bool(improvement_summary.get("stalled_flag")),
    }


def _build_anchored_chronology_summary(intake_case_file: Dict[str, Any], *, limit: int = 3) -> List[str]:
    case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
    facts = [dict(item) for item in list(case_file.get("canonical_facts") or []) if isinstance(item, dict)]
    relations = [dict(item) for item in list(case_file.get("timeline_relations") or []) if isinstance(item, dict)]
    if not facts or not relations:
        return []

    fact_by_id = {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if str(fact.get("fact_id") or "").strip()
    }
    relation_records = []
    for relation in relations:
        if str(relation.get("relation_type") or "").strip().lower() != "before":
            continue
        source_id = str(relation.get("source_fact_id") or "").strip()
        target_id = str(relation.get("target_fact_id") or "").strip()
        source_fact = fact_by_id.get(source_id)
        target_fact = fact_by_id.get(target_id)
        if not source_fact or not target_fact:
            continue
        source_date = _format_timeline_date((source_fact.get("temporal_context") or {}).get("start_date") or relation.get("source_start_date"))
        target_date = _format_timeline_date((target_fact.get("temporal_context") or {}).get("start_date") or relation.get("target_start_date"))
        if not source_date or not target_date:
            continue
        relation_records.append(
            {
                "key": (source_id, target_id),
                "source_id": source_id,
                "target_id": target_id,
                "source_fact": source_fact,
                "target_fact": target_fact,
                "source_date": source_date,
                "target_date": target_date,
            }
        )
    if not relation_records:
        return []

    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    incoming_count: Dict[str, int] = {}
    for record in relation_records:
        outgoing.setdefault(record["source_id"], []).append(record)
        incoming_count[record["target_id"]] = incoming_count.get(record["target_id"], 0) + 1
        incoming_count.setdefault(record["source_id"], incoming_count.get(record["source_id"], 0))

    lines: List[str] = []
    seen = set()
    used_keys = set()
    for record in relation_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        if incoming_count.get(record["source_id"], 0) != 0 or len(outgoing.get(record["source_id"], [])) != 1:
            continue
        chain = [record]
        next_id = record["target_id"]
        temp_used = {record["key"]}
        while len(outgoing.get(next_id, [])) == 1 and incoming_count.get(next_id, 0) == 1:
            next_record = outgoing[next_id][0]
            if next_record["key"] in temp_used:
                break
            chain.append(next_record)
            temp_used.add(next_record["key"])
            next_id = next_record["target_id"]
        if len(chain) < 2:
            continue
        segments = [
            f"{_chronology_fact_label(chain[0]['source_fact'])} on {chain[0]['source_date']}"
        ]
        segments.extend(
            f"{_chronology_fact_label(item['target_fact'])} on {item['target_date']}"
            for item in chain
        )
        line = f"{_join_chronology_segments(segments)} occurred in sequence."
        last_target = chain[-1]["target_fact"]
        target_context = last_target.get("temporal_context") if isinstance(last_target.get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f". The later date is currently derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        used_keys.update(temp_used)
        lines.append(line)

    for record in relation_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        source_label = _chronology_fact_label(record["source_fact"])
        target_label = _chronology_fact_label(record["target_fact"])
        line = f"{source_label} on {record['source_date']} preceded {target_label.lower()} on {record['target_date']}."
        target_context = record["target_fact"].get("temporal_context") if isinstance(record["target_fact"].get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f". The later date is currently derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def _build_claim_support_temporal_handoff(intake_case_summary: Any) -> Dict[str, Any]:
    summary = intake_case_summary if isinstance(intake_case_summary, dict) else {}
    packet_summary = summary.get("claim_support_packet_summary")
    packet_summary = packet_summary if isinstance(packet_summary, dict) else {}
    alignment_tasks = summary.get("alignment_evidence_tasks")
    alignment_tasks = alignment_tasks if isinstance(alignment_tasks, list) else []
    temporal_issue_registry_summary = summarize_temporal_issue_registry(
        summary.get("temporal_issue_registry_summary")
    )

    def _collect_temporal_registry_identifiers(registry: Any, *keys: str) -> List[str]:
        identifiers: List[str] = []
        for entry in registry if isinstance(registry, list) else []:
            if not isinstance(entry, dict):
                continue
            for key in keys:
                text = str(entry.get(key) or "").strip()
                if text:
                    identifiers.append(text)
                    break
        return _dedupe_text_values(identifiers)

    def _collect_unresolved_temporal_issue_identifiers(registry: Any) -> List[str]:
        issue_ids: List[str] = []
        for entry in registry if isinstance(registry, list) else []:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("current_resolution_status") or entry.get("status") or "open").strip().lower()
            if status in {"resolved", "closed", "complete", "completed"}:
                continue
            issue_id = str(
                entry.get("temporal_issue_id")
                or entry.get("issue_id")
                or entry.get("timeline_issue_id")
                or ""
            ).strip()
            if issue_id:
                issue_ids.append(issue_id)
        return _dedupe_text_values(issue_ids)

    unresolved_temporal_issue_ids = _dedupe_text_values(
        packet_summary.get("claim_support_unresolved_temporal_issue_ids") or []
    )
    event_ids: List[str] = []
    temporal_fact_ids: List[str] = []
    temporal_relation_ids: List[str] = []
    timeline_anchor_ids: List[str] = []
    timeline_issue_ids: List[str] = []
    temporal_issue_ids: List[str] = []
    missing_temporal_predicates: List[str] = []
    required_provenance_kinds: List[str] = []
    temporal_proof_bundle_ids: List[str] = []
    temporal_proof_objectives: List[str] = []

    for task in alignment_tasks:
        if not isinstance(task, dict):
            continue
        event_ids.extend(_dedupe_text_values(task.get("event_ids") or []))
        temporal_fact_ids.extend(_dedupe_text_values(task.get("temporal_fact_ids") or []))
        temporal_relation_ids.extend(_dedupe_text_values(task.get("temporal_relation_ids") or []))
        timeline_anchor_ids.extend(_dedupe_text_values(task.get("anchor_ids") or task.get("timeline_anchor_ids") or []))
        timeline_issue_ids.extend(_dedupe_text_values(task.get("timeline_issue_ids") or []))
        temporal_issue_ids.extend(_dedupe_text_values(task.get("temporal_issue_ids") or []))
        missing_temporal_predicates.extend(_dedupe_text_values(task.get("missing_temporal_predicates") or []))
        required_provenance_kinds.extend(_dedupe_text_values(task.get("required_provenance_kinds") or []))
        proof_bundle_id = str(task.get("temporal_proof_bundle_id") or "").strip()
        if proof_bundle_id:
            temporal_proof_bundle_ids.append(proof_bundle_id)
        proof_objective = str(task.get("temporal_proof_objective") or "").strip()
        if proof_objective:
            temporal_proof_objectives.append(proof_objective)

    raw_event_ids = _collect_temporal_registry_identifiers(
        summary.get("event_ledger"),
        "event_id",
        "temporal_fact_id",
        "fact_id",
    )
    raw_temporal_fact_ids = _collect_temporal_registry_identifiers(
        summary.get("temporal_fact_registry"),
        "temporal_fact_id",
        "fact_id",
        "event_id",
    )
    if not raw_temporal_fact_ids:
        raw_temporal_fact_ids = _collect_temporal_registry_identifiers(
            summary.get("event_ledger"),
            "temporal_fact_id",
            "event_id",
            "fact_id",
        )
    raw_temporal_relation_ids = _collect_temporal_registry_identifiers(
        summary.get("temporal_relation_registry"),
        "temporal_relation_id",
        "relation_id",
    )
    if not raw_temporal_relation_ids:
        raw_temporal_relation_ids = _collect_temporal_registry_identifiers(
            summary.get("timeline_relations"),
            "temporal_relation_id",
            "relation_id",
        )
    raw_timeline_anchor_ids = _collect_temporal_registry_identifiers(
        summary.get("timeline_anchors"),
        "anchor_id",
        "timeline_anchor_id",
    )
    raw_temporal_issue_ids = _collect_temporal_registry_identifiers(
        summary.get("temporal_issue_registry"),
        "temporal_issue_id",
        "issue_id",
        "timeline_issue_id",
    )
    raw_unresolved_temporal_issue_ids = _collect_unresolved_temporal_issue_identifiers(
        summary.get("temporal_issue_registry")
    )
    summary_issue_ids = _dedupe_text_values(temporal_issue_registry_summary.get("issue_ids") or [])
    summary_missing_temporal_predicates = _dedupe_text_values(
        temporal_issue_registry_summary.get("missing_temporal_predicates") or []
    )
    summary_required_provenance_kinds = _dedupe_text_values(
        temporal_issue_registry_summary.get("required_provenance_kinds") or []
    )

    unresolved_temporal_issue_count = int(
        packet_summary.get("claim_support_unresolved_temporal_issue_count", 0) or 0
    )
    if not unresolved_temporal_issue_count and raw_unresolved_temporal_issue_ids:
        unresolved_temporal_issue_count = len(raw_unresolved_temporal_issue_ids)
    if not unresolved_temporal_issue_count:
        unresolved_temporal_issue_count = int(temporal_issue_registry_summary.get("unresolved_count") or 0)
    if not unresolved_temporal_issue_ids:
        unresolved_temporal_issue_ids = raw_unresolved_temporal_issue_ids

    temporal_handoff = {
        "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
        "unresolved_temporal_issue_ids": unresolved_temporal_issue_ids,
        "chronology_task_count": int(packet_summary.get("temporal_gap_task_count", 0) or 0),
        "event_ids": _dedupe_text_values(event_ids) or raw_event_ids,
        "temporal_fact_ids": _dedupe_text_values(temporal_fact_ids) or raw_temporal_fact_ids,
        "temporal_relation_ids": _dedupe_text_values(temporal_relation_ids) or raw_temporal_relation_ids,
        "timeline_issue_ids": _dedupe_text_values(timeline_issue_ids) or raw_temporal_issue_ids or summary_issue_ids,
        "temporal_issue_ids": _dedupe_text_values(temporal_issue_ids) or raw_temporal_issue_ids or summary_issue_ids,
        "temporal_proof_bundle_ids": _dedupe_text_values(temporal_proof_bundle_ids),
        "temporal_proof_objectives": _dedupe_text_values(temporal_proof_objectives),
    }
    normalized_timeline_anchor_ids = _dedupe_text_values(timeline_anchor_ids) or raw_timeline_anchor_ids
    if normalized_timeline_anchor_ids:
        temporal_handoff["timeline_anchor_ids"] = normalized_timeline_anchor_ids
    normalized_missing_temporal_predicates = _dedupe_text_values(missing_temporal_predicates) or summary_missing_temporal_predicates
    if normalized_missing_temporal_predicates:
        temporal_handoff["missing_temporal_predicates"] = normalized_missing_temporal_predicates
    normalized_required_provenance_kinds = _dedupe_text_values(required_provenance_kinds) or summary_required_provenance_kinds
    if normalized_required_provenance_kinds:
        temporal_handoff["required_provenance_kinds"] = normalized_required_provenance_kinds
    if not temporal_handoff["unresolved_temporal_issue_count"] and not any(
        temporal_handoff.get(key)
        for key in (
            "unresolved_temporal_issue_ids",
            "event_ids",
            "temporal_fact_ids",
            "temporal_relation_ids",
            "timeline_anchor_ids",
            "timeline_issue_ids",
            "temporal_issue_ids",
            "missing_temporal_predicates",
            "required_provenance_kinds",
            "temporal_proof_bundle_ids",
            "temporal_proof_objectives",
        )
    ):
        return {}
    return temporal_handoff


def _build_claim_reasoning_theorem_export_metadata(
    intake_case_summary: Any,
    *,
    claim_type: str,
    claim_element_id: str,
) -> Dict[str, Any]:
    summary = intake_case_summary if isinstance(intake_case_summary, dict) else {}
    packet_summary = summary.get("claim_support_packet_summary")
    packet_summary = packet_summary if isinstance(packet_summary, dict) else {}
    alignment_tasks = summary.get("alignment_evidence_tasks")
    alignment_tasks = alignment_tasks if isinstance(alignment_tasks, list) else []
    temporal_handoff = _build_claim_support_temporal_handoff(summary)
    temporal_handoff = temporal_handoff if isinstance(temporal_handoff, dict) else {}

    normalized_claim_type = str(claim_type or "").strip()
    normalized_claim_element_id = str(claim_element_id or "").strip()
    matching_task: Dict[str, Any] = {}
    fallback_task: Dict[str, Any] = {}

    for task in alignment_tasks:
        if not isinstance(task, dict):
            continue
        task_claim_type = str(task.get("claim_type") or "").strip()
        task_claim_element_id = str(task.get("claim_element_id") or "").strip()
        if normalized_claim_type and task_claim_type == normalized_claim_type and not fallback_task:
            fallback_task = task
        if (
            normalized_claim_type
            and normalized_claim_element_id
            and task_claim_type == normalized_claim_type
            and task_claim_element_id == normalized_claim_element_id
        ):
            matching_task = task
            break

    selected_task = matching_task or fallback_task
    unresolved_temporal_issue_ids = _dedupe_text_values(
        selected_task.get("temporal_issue_ids")
        or temporal_handoff.get("unresolved_temporal_issue_ids")
        or packet_summary.get("claim_support_unresolved_temporal_issue_ids")
        or []
    )
    event_ids = _dedupe_text_values(
        selected_task.get("event_ids") or temporal_handoff.get("event_ids") or []
    )
    temporal_fact_ids = _dedupe_text_values(
        selected_task.get("temporal_fact_ids") or temporal_handoff.get("temporal_fact_ids") or []
    )
    temporal_relation_ids = _dedupe_text_values(
        selected_task.get("temporal_relation_ids") or temporal_handoff.get("temporal_relation_ids") or []
    )
    timeline_anchor_ids = _dedupe_text_values(
        selected_task.get("anchor_ids")
        or selected_task.get("timeline_anchor_ids")
        or temporal_handoff.get("timeline_anchor_ids")
        or []
    )
    timeline_issue_ids = _dedupe_text_values(
        selected_task.get("timeline_issue_ids")
        or temporal_handoff.get("timeline_issue_ids")
        or unresolved_temporal_issue_ids
    )
    temporal_issue_ids = _dedupe_text_values(
        selected_task.get("temporal_issue_ids")
        or temporal_handoff.get("temporal_issue_ids")
        or unresolved_temporal_issue_ids
    )
    temporal_proof_bundle_ids = _dedupe_text_values(
        ([selected_task.get("temporal_proof_bundle_id")] if selected_task.get("temporal_proof_bundle_id") else [])
        or temporal_handoff.get("temporal_proof_bundle_ids")
        or []
    )
    temporal_proof_objectives = _dedupe_text_values(
        ([selected_task.get("temporal_proof_objective")] if selected_task.get("temporal_proof_objective") else [])
        or temporal_handoff.get("temporal_proof_objectives")
        or []
    )
    missing_temporal_predicates = _dedupe_text_values(
        selected_task.get("missing_temporal_predicates")
        or temporal_handoff.get("missing_temporal_predicates")
        or []
    )
    required_provenance_kinds = _dedupe_text_values(
        selected_task.get("required_provenance_kinds")
        or temporal_handoff.get("required_provenance_kinds")
        or []
    )
    proof_bundle_id = str(
        selected_task.get("temporal_proof_bundle_id")
        or (temporal_proof_bundle_ids[0] if temporal_proof_bundle_ids else "")
    ).strip()
    chronology_task_count = int(
        temporal_handoff.get("chronology_task_count")
        or packet_summary.get("temporal_gap_task_count", 0)
        or 0
    )

    metadata_claim_element_id = str(
        selected_task.get("claim_element_id") or normalized_claim_element_id
    ).strip()

    metadata = {
        "contract_version": "claim_support_temporal_handoff_v1",
        "claim_type": normalized_claim_type,
        "claim_element_id": metadata_claim_element_id,
        "proof_bundle_id": proof_bundle_id,
        "chronology_blocked": bool(
            chronology_task_count
            or unresolved_temporal_issue_ids
            or timeline_issue_ids
            or temporal_issue_ids
        ),
        "chronology_task_count": chronology_task_count,
        "unresolved_temporal_issue_ids": unresolved_temporal_issue_ids,
        "event_ids": event_ids,
        "temporal_fact_ids": temporal_fact_ids,
        "temporal_relation_ids": temporal_relation_ids,
        "timeline_issue_ids": timeline_issue_ids,
        "temporal_issue_ids": temporal_issue_ids,
        "temporal_proof_bundle_ids": temporal_proof_bundle_ids,
        "temporal_proof_objectives": temporal_proof_objectives,
    }
    if timeline_anchor_ids:
        metadata["timeline_anchor_ids"] = timeline_anchor_ids
    if missing_temporal_predicates:
        metadata["missing_temporal_predicates"] = missing_temporal_predicates
    if required_provenance_kinds:
        metadata["required_provenance_kinds"] = required_provenance_kinds
    if not any(
        metadata[key]
        for key in (
            "claim_type",
            "claim_element_id",
            "proof_bundle_id",
            "unresolved_temporal_issue_ids",
            "event_ids",
            "temporal_fact_ids",
            "temporal_relation_ids",
            "timeline_anchor_ids",
            "timeline_issue_ids",
            "temporal_issue_ids",
            "missing_temporal_predicates",
            "required_provenance_kinds",
            "temporal_proof_bundle_ids",
            "temporal_proof_objectives",
        )
    ) and not metadata["chronology_task_count"]:
        return {}
    return metadata


def _build_claim_temporal_gap_hints(
    intake_case_file: Dict[str, Any],
    *,
    claim_type: str,
    claim_name: str,
    limit: int = 3,
) -> List[str]:
    case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
    focus = _claim_temporal_gap_focus(claim_type, claim_name)
    normalized_claim_type = str(claim_type or "").strip().lower()
    hints: List[str] = []

    for issue in list(case_file.get("temporal_issue_registry") or []):
        if not isinstance(issue, dict):
            continue
        status = str(issue.get("status") or "open").strip().lower()
        if status not in {"open", "blocking", "warning"}:
            continue
        issue_claim_types = {
            str(item).strip().lower()
            for item in list(issue.get("claim_types") or [])
            if str(item).strip()
        }
        issue_element_tags = {
            str(item).strip().lower()
            for item in list(issue.get("element_tags") or [])
            if str(item).strip()
        }
        if issue_claim_types:
            if normalized_claim_type not in issue_claim_types:
                continue
        elif issue_element_tags and not (issue_element_tags & focus["element_tags"]):
            continue
        summary = str(issue.get("summary") or "").strip()
        if summary:
            hints.append(f"Chronology gap: {summary}")

    blocker_follow_up_summary = (
        case_file.get("blocker_follow_up_summary")
        if isinstance(case_file.get("blocker_follow_up_summary"), dict)
        else {}
    )
    for blocker in list(blocker_follow_up_summary.get("blocking_items") or []):
        if not isinstance(blocker, dict):
            continue
        issue_family = str(blocker.get("issue_family") or "").strip().lower()
        primary_objective = str(blocker.get("primary_objective") or "").strip().lower()
        blocker_objectives = {
            str(item).strip().lower()
            for item in list(blocker.get("blocker_objectives") or [])
            if str(item).strip()
        }
        matched_objectives = ({primary_objective} if primary_objective else set()) | blocker_objectives
        if issue_family:
            if issue_family not in focus["issue_families"] and not (matched_objectives & focus["objectives"]):
                continue
        elif not (matched_objectives & focus["objectives"]):
            continue
        reason = str(blocker.get("reason") or "").strip()
        if reason:
            hints.append(f"Chronology gap: {reason}")

    return _unique_preserving_order(hints)[:limit]
