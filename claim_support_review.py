from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


DEFAULT_REQUIRED_SUPPORT_KINDS = ["evidence", "authority"]


class ClaimSupportReviewRequest(BaseModel):
    user_id: Optional[str] = None
    claim_type: Optional[str] = None
    required_support_kinds: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )
    follow_up_cooldown_seconds: int = 3600
    include_support_summary: bool = True
    include_overview: bool = True
    include_follow_up_plan: bool = True
    execute_follow_up: bool = False
    follow_up_support_kind: Optional[str] = None
    follow_up_max_tasks_per_claim: int = 3


class ClaimSupportFollowUpExecuteRequest(BaseModel):
    user_id: Optional[str] = None
    claim_type: Optional[str] = None
    required_support_kinds: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )
    follow_up_cooldown_seconds: int = 3600
    follow_up_support_kind: Optional[str] = None
    follow_up_max_tasks_per_claim: int = 3
    follow_up_force: bool = False
    include_post_execution_review: bool = True
    include_support_summary: bool = True
    include_overview: bool = True
    include_follow_up_plan: bool = True


def _resolve_user_id(mediator: Any, user_id: Optional[str]) -> str:
    if user_id:
        return user_id
    state = getattr(mediator, "state", None)
    return (
        getattr(state, "username", None)
        or getattr(state, "hashed_username", None)
        or "anonymous"
    )


def summarize_claim_support_snapshot_lifecycle(
    snapshots: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    snapshot_map = snapshots if isinstance(snapshots, dict) else {}
    snapshot_kinds = sorted(
        kind for kind, snapshot in snapshot_map.items() if isinstance(snapshot, dict)
    )
    stale_snapshot_kinds = sorted(
        kind
        for kind in snapshot_kinds
        if bool((snapshot_map.get(kind) or {}).get("is_stale"))
    )
    fresh_snapshot_kinds = [
        kind for kind in snapshot_kinds if kind not in stale_snapshot_kinds
    ]
    retention_limits = sorted(
        {
            int(snapshot.get("retention_limit"))
            for snapshot in snapshot_map.values()
            if isinstance(snapshot, dict) and snapshot.get("retention_limit") is not None
        }
    )
    total_pruned_snapshot_count = sum(
        int((snapshot.get("pruned_snapshot_count", 0) or 0))
        for snapshot in snapshot_map.values()
        if isinstance(snapshot, dict)
    )
    return {
        "total_snapshot_count": len(snapshot_kinds),
        "fresh_snapshot_count": len(fresh_snapshot_kinds),
        "stale_snapshot_count": len(stale_snapshot_kinds),
        "snapshot_kinds": snapshot_kinds,
        "fresh_snapshot_kinds": fresh_snapshot_kinds,
        "stale_snapshot_kinds": stale_snapshot_kinds,
        "retention_limits": retention_limits,
        "total_pruned_snapshot_count": total_pruned_snapshot_count,
    }


def summarize_claim_reasoning_review(
    validation_claim: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    claim_validation = validation_claim if isinstance(validation_claim, dict) else {}
    elements = claim_validation.get("elements", [])
    if not isinstance(elements, list):
        elements = []

    flagged_elements: List[Dict[str, Any]] = []
    fallback_ontology_element_count = 0
    unavailable_backend_element_count = 0
    degraded_adapter_element_count = 0

    for element in elements:
        if not isinstance(element, dict):
            continue
        reasoning = element.get("reasoning_diagnostics", {})
        if not isinstance(reasoning, dict):
            reasoning = {}
        adapter_statuses = reasoning.get("adapter_statuses", {})
        if not isinstance(adapter_statuses, dict):
            adapter_statuses = {}

        unavailable_adapters = sorted(
            name
            for name, summary in adapter_statuses.items()
            if isinstance(summary, dict) and not bool(summary.get("backend_available", False))
        )
        degraded_adapters = sorted(
            name
            for name, summary in adapter_statuses.items()
            if isinstance(summary, dict)
            and str(
                summary.get("implementation_status") or summary.get("status") or ""
            )
            in {"unavailable", "error", "not_implemented"}
        )
        used_fallback_ontology = bool(reasoning.get("used_fallback_ontology"))

        if used_fallback_ontology:
            fallback_ontology_element_count += 1
        if unavailable_adapters:
            unavailable_backend_element_count += 1
        if degraded_adapters:
            degraded_adapter_element_count += 1

        if not (
            used_fallback_ontology
            or unavailable_adapters
            or degraded_adapters
            or str(element.get("validation_status") or "") == "contradicted"
        ):
            continue

        flagged_elements.append(
            {
                "element_id": element.get("element_id"),
                "element_text": element.get("element_text"),
                "validation_status": element.get("validation_status", ""),
                "predicate_count": int(reasoning.get("predicate_count", 0) or 0),
                "used_fallback_ontology": used_fallback_ontology,
                "backend_available_count": int(
                    reasoning.get("backend_available_count", 0) or 0
                ),
                "unavailable_adapters": unavailable_adapters,
                "degraded_adapters": degraded_adapters,
            }
        )

    return {
        "claim_type": claim_validation.get("claim_type", ""),
        "total_element_count": len(
            [element for element in elements if isinstance(element, dict)]
        ),
        "flagged_element_count": len(flagged_elements),
        "fallback_ontology_element_count": fallback_ontology_element_count,
        "unavailable_backend_element_count": unavailable_backend_element_count,
        "degraded_adapter_element_count": degraded_adapter_element_count,
        "flagged_elements": flagged_elements,
    }


def _summarize_claim_coverage_claim(
    claim_type: str,
    coverage_claim: Dict[str, Any],
    overview_claim: Dict[str, Any],
    gap_claim: Dict[str, Any],
    contradiction_claim: Dict[str, Any],
    validation_claim: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    validation_claim = validation_claim if isinstance(validation_claim, dict) else {}
    reasoning_summary = (
        (validation_claim.get("proof_diagnostics") or {}).get("reasoning", {})
        if isinstance(validation_claim.get("proof_diagnostics"), dict)
        else {}
    )
    missing_elements = []
    partially_supported_elements = []

    if isinstance(overview_claim, dict):
        missing_elements = [
            element.get("element_text")
            for element in overview_claim.get("missing", [])
            if isinstance(element, dict) and element.get("element_text")
        ]
        partially_supported_elements = [
            element.get("element_text")
            for element in overview_claim.get("partially_supported", [])
            if isinstance(element, dict) and element.get("element_text")
        ]

    unresolved_elements = []
    recommended_gap_actions: Dict[str, int] = {}
    if isinstance(gap_claim, dict):
        for element in gap_claim.get("unresolved_elements", []):
            if not isinstance(element, dict):
                continue
            element_text = element.get("element_text")
            if element_text:
                unresolved_elements.append(element_text)
            action = str(element.get("recommended_action") or "unspecified")
            recommended_gap_actions[action] = recommended_gap_actions.get(action, 0) + 1

    contradicted_elements = []
    contradiction_candidate_count = 0
    seen_contradicted_elements = set()
    if isinstance(contradiction_claim, dict):
        contradiction_candidate_count = int(
            contradiction_claim.get("candidate_count", 0) or 0
        )
        for candidate in contradiction_claim.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            element_text = candidate.get("claim_element_text")
            if element_text and element_text not in seen_contradicted_elements:
                seen_contradicted_elements.add(element_text)
                contradicted_elements.append(element_text)

    traced_link_count = 0
    snapshot_created_count = 0
    snapshot_reused_count = 0
    source_table_counts: Dict[str, int] = {}
    graph_status_counts: Dict[str, int] = {}
    graph_id_count = 0
    seen_graph_ids = set()

    for element in coverage_claim.get("elements", []):
        if not isinstance(element, dict):
            continue
        for link in element.get("links", []):
            if not isinstance(link, dict):
                continue
            graph_trace = link.get("graph_trace", {})
            if not isinstance(graph_trace, dict) or not graph_trace:
                continue
            traced_link_count += 1

            source_table = str(graph_trace.get("source_table") or "unknown")
            source_table_counts[source_table] = source_table_counts.get(source_table, 0) + 1

            summary = graph_trace.get("summary", {})
            if isinstance(summary, dict):
                graph_status = str(summary.get("status") or "unknown")
                graph_status_counts[graph_status] = graph_status_counts.get(graph_status, 0) + 1

            snapshot = graph_trace.get("snapshot", {})
            if isinstance(snapshot, dict):
                if bool(snapshot.get("created")):
                    snapshot_created_count += 1
                if bool(snapshot.get("reused")):
                    snapshot_reused_count += 1
                graph_id = str(snapshot.get("graph_id") or "")
                if graph_id and graph_id not in seen_graph_ids:
                    seen_graph_ids.add(graph_id)
                    graph_id_count += 1

    return {
        "claim_type": claim_type,
        "validation_status": validation_claim.get("validation_status", ""),
        "validation_status_counts": validation_claim.get("validation_status_counts", {}),
        "proof_gap_count": int(validation_claim.get("proof_gap_count", 0) or 0),
        "elements_requiring_follow_up": validation_claim.get(
            "elements_requiring_follow_up", []
        ),
        "reasoning_adapter_status_counts": reasoning_summary.get(
            "adapter_status_counts", {}
        ),
        "reasoning_backend_available_count": int(
            reasoning_summary.get("backend_available_count", 0) or 0
        ),
        "reasoning_predicate_count": int(
            reasoning_summary.get("predicate_count", 0) or 0
        ),
        "reasoning_ontology_entity_count": int(
            reasoning_summary.get("ontology_entity_count", 0) or 0
        ),
        "reasoning_ontology_relationship_count": int(
            reasoning_summary.get("ontology_relationship_count", 0) or 0
        ),
        "reasoning_fallback_ontology_count": int(
            reasoning_summary.get("fallback_ontology_count", 0) or 0
        ),
        "total_elements": coverage_claim.get("total_elements", 0),
        "total_links": coverage_claim.get("total_links", 0),
        "total_facts": coverage_claim.get("total_facts", 0),
        "support_by_kind": coverage_claim.get("support_by_kind", {}),
        "support_trace_summary": coverage_claim.get("support_trace_summary", {}),
        "status_counts": coverage_claim.get(
            "status_counts",
            {"covered": 0, "partially_supported": 0, "missing": 0},
        ),
        "missing_elements": missing_elements,
        "partially_supported_elements": partially_supported_elements,
        "unresolved_element_count": int(gap_claim.get("unresolved_count", 0) or 0)
        if isinstance(gap_claim, dict)
        else 0,
        "unresolved_elements": unresolved_elements,
        "recommended_gap_actions": recommended_gap_actions,
        "contradiction_candidate_count": contradiction_candidate_count,
        "contradicted_elements": contradicted_elements,
        "graph_trace_summary": {
            "traced_link_count": traced_link_count,
            "snapshot_created_count": snapshot_created_count,
            "snapshot_reused_count": snapshot_reused_count,
            "source_table_counts": source_table_counts,
            "graph_status_counts": graph_status_counts,
            "graph_id_count": graph_id_count,
        },
    }


def _aggregate_graph_support_metrics(tasks: List[Dict[str, Any]]) -> Dict[str, int]:
    semantic_cluster_count = 0
    semantic_duplicate_count = 0
    for task in tasks:
        graph_summary = (task.get("graph_support") or {}).get("summary", {})
        semantic_cluster_count += int(graph_summary.get("semantic_cluster_count", 0) or 0)
        semantic_duplicate_count += int(
            graph_summary.get("semantic_duplicate_count", 0) or 0
        )
    return {
        "semantic_cluster_count": semantic_cluster_count,
        "semantic_duplicate_count": semantic_duplicate_count,
    }


def _summarize_follow_up_plan_claim(claim_plan: Dict[str, Any]) -> Dict[str, Any]:
    tasks = claim_plan.get("tasks", []) if isinstance(claim_plan, dict) else []
    recommended_actions: Dict[str, int] = {}
    for task in tasks:
        action = str(task.get("recommended_action") or "unspecified")
        recommended_actions[action] = recommended_actions.get(action, 0) + 1
    graph_support_metrics = _aggregate_graph_support_metrics(tasks)
    return {
        "task_count": len(tasks),
        "blocked_task_count": claim_plan.get("blocked_task_count", 0),
        "graph_supported_task_count": len(
            [task for task in tasks if task.get("has_graph_support")]
        ),
        "manual_review_task_count": len(
            [task for task in tasks if task.get("execution_mode") == "manual_review"]
        ),
        "suppressed_task_count": len(
            [task for task in tasks if task.get("should_suppress_retrieval")]
        ),
        "semantic_cluster_count": graph_support_metrics["semantic_cluster_count"],
        "semantic_duplicate_count": graph_support_metrics["semantic_duplicate_count"],
        "recommended_actions": recommended_actions,
    }


def _summarize_follow_up_execution_claim(claim_execution: Dict[str, Any]) -> Dict[str, Any]:
    executed_tasks = claim_execution.get("tasks", []) if isinstance(claim_execution, dict) else []
    skipped_tasks = (
        claim_execution.get("skipped_tasks", []) if isinstance(claim_execution, dict) else []
    )
    suppressed = [task for task in skipped_tasks if "suppressed" in task.get("skipped", {})]
    manual_review_skips = [
        task for task in skipped_tasks if "manual_review" in task.get("skipped", {})
    ]
    cooldown_skips = [
        task
        for task in skipped_tasks
        if any(
            value.get("reason") == "duplicate_within_cooldown"
            for value in task.get("skipped", {}).values()
            if isinstance(value, dict)
        )
    ]
    graph_support_metrics = _aggregate_graph_support_metrics(executed_tasks + skipped_tasks)
    return {
        "executed_task_count": len(executed_tasks),
        "skipped_task_count": len(skipped_tasks),
        "suppressed_task_count": len(suppressed),
        "manual_review_task_count": len(manual_review_skips),
        "cooldown_skipped_task_count": len(cooldown_skips),
        "semantic_cluster_count": graph_support_metrics["semantic_cluster_count"],
        "semantic_duplicate_count": graph_support_metrics["semantic_duplicate_count"],
    }


def build_claim_support_review_payload(
    mediator: Any,
    request: ClaimSupportReviewRequest,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, request.user_id)
    required_support_kinds = (
        request.required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    matrix = mediator.get_claim_coverage_matrix(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )
    overview = mediator.get_claim_overview(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )

    coverage_claims = matrix.get("claims", {}) if isinstance(matrix, dict) else {}
    overview_claims = overview.get("claims", {}) if isinstance(overview, dict) else {}
    diagnostic_snapshots = mediator.get_claim_support_diagnostic_snapshots(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )
    snapshot_claims = (
        diagnostic_snapshots.get("claims", {})
        if isinstance(diagnostic_snapshots, dict)
        else {}
    )
    gap_claims = {
        claim_name: claim_snapshot.get("gaps", {})
        for claim_name, claim_snapshot in snapshot_claims.items()
        if isinstance(claim_snapshot, dict)
        and isinstance(claim_snapshot.get("gaps"), dict)
        and not bool(
            ((claim_snapshot.get("snapshots") or {}).get("gaps") or {}).get("is_stale")
        )
    }
    contradiction_claims = {
        claim_name: claim_snapshot.get("contradictions", {})
        for claim_name, claim_snapshot in snapshot_claims.items()
        if isinstance(claim_snapshot, dict)
        and isinstance(claim_snapshot.get("contradictions"), dict)
        and not bool(
            ((claim_snapshot.get("snapshots") or {}).get("contradictions") or {}).get("is_stale")
        )
    }
    missing_gap_claims = [
        claim_name for claim_name in coverage_claims.keys()
        if claim_name not in gap_claims or not gap_claims.get(claim_name)
    ]
    if missing_gap_claims:
        gaps = mediator.get_claim_support_gaps(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            required_support_kinds=required_support_kinds,
        )
        computed_gap_claims = gaps.get("claims", {}) if isinstance(gaps, dict) else {}
        for claim_name in missing_gap_claims:
            if isinstance(computed_gap_claims.get(claim_name), dict):
                gap_claims[claim_name] = computed_gap_claims[claim_name]
    missing_contradiction_claims = [
        claim_name for claim_name in coverage_claims.keys()
        if claim_name not in contradiction_claims or not contradiction_claims.get(claim_name)
    ]
    if missing_contradiction_claims:
        contradiction_candidates = mediator.get_claim_contradiction_candidates(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
        )
        computed_contradiction_claims = (
            contradiction_candidates.get("claims", {})
            if isinstance(contradiction_candidates, dict)
            else {}
        )
        for claim_name in missing_contradiction_claims:
            if isinstance(computed_contradiction_claims.get(claim_name), dict):
                contradiction_claims[claim_name] = computed_contradiction_claims[claim_name]
    validation = mediator.get_claim_support_validation(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )
    validation_claims = validation.get("claims", {}) if isinstance(validation, dict) else {}
    coverage_summary = {
        claim_name: _summarize_claim_coverage_claim(
            claim_name,
            claim_matrix,
            overview_claims.get(claim_name, {}),
            gap_claims.get(claim_name, {}),
            contradiction_claims.get(claim_name, {}),
            validation_claims.get(claim_name, {}),
        )
        for claim_name, claim_matrix in coverage_claims.items()
        if isinstance(claim_matrix, dict)
    }

    payload: Dict[str, Any] = {
        "user_id": resolved_user_id,
        "claim_type": request.claim_type,
        "required_support_kinds": required_support_kinds,
        "claim_coverage_matrix": coverage_claims,
        "claim_coverage_summary": coverage_summary,
        "claim_support_gaps": gap_claims,
        "claim_contradiction_candidates": contradiction_claims,
        "claim_support_validation": validation_claims,
        "claim_support_snapshots": {
            claim_name: claim_snapshot.get("snapshots", {})
            for claim_name, claim_snapshot in snapshot_claims.items()
            if isinstance(claim_snapshot, dict)
        },
        "claim_support_snapshot_summary": {
            claim_name: summarize_claim_support_snapshot_lifecycle(
                (snapshot_claims.get(claim_name, {}) or {}).get("snapshots", {})
            )
            for claim_name in coverage_claims.keys()
        },
        "claim_reasoning_review": {
            claim_name: summarize_claim_reasoning_review(
                validation_claims.get(claim_name, {})
            )
            for claim_name in coverage_claims.keys()
        },
    }

    if request.include_follow_up_plan:
        follow_up_plan = mediator.get_claim_follow_up_plan(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            required_support_kinds=required_support_kinds,
            cooldown_seconds=request.follow_up_cooldown_seconds,
        )
        follow_up_claims = (
            follow_up_plan.get("claims", {}) if isinstance(follow_up_plan, dict) else {}
        )
        payload["follow_up_plan"] = follow_up_claims
        payload["follow_up_plan_summary"] = {
            claim_name: _summarize_follow_up_plan_claim(claim_plan)
            for claim_name, claim_plan in follow_up_claims.items()
            if isinstance(claim_plan, dict)
        }

    if request.execute_follow_up:
        follow_up_execution = mediator.execute_claim_follow_up_plan(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            support_kind=request.follow_up_support_kind,
            max_tasks_per_claim=request.follow_up_max_tasks_per_claim,
            cooldown_seconds=request.follow_up_cooldown_seconds,
        )
        follow_up_execution_claims = (
            follow_up_execution.get("claims", {})
            if isinstance(follow_up_execution, dict)
            else {}
        )
        payload["follow_up_execution"] = follow_up_execution_claims
        payload["follow_up_execution_summary"] = {
            claim_name: _summarize_follow_up_execution_claim(claim_execution)
            for claim_name, claim_execution in follow_up_execution_claims.items()
            if isinstance(claim_execution, dict)
        }

    if request.include_support_summary:
        support_summary = mediator.summarize_claim_support(
            user_id=resolved_user_id,
            claim_type=request.claim_type,
        )
        payload["support_summary"] = (
            support_summary.get("claims", {}) if isinstance(support_summary, dict) else {}
        )

    if request.include_overview:
        payload["claim_overview"] = overview_claims

    return payload


def build_claim_support_follow_up_execution_payload(
    mediator: Any,
    request: ClaimSupportFollowUpExecuteRequest,
) -> Dict[str, Any]:
    resolved_user_id = _resolve_user_id(mediator, request.user_id)
    required_support_kinds = (
        request.required_support_kinds or list(DEFAULT_REQUIRED_SUPPORT_KINDS)
    )

    follow_up_execution = mediator.execute_claim_follow_up_plan(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        support_kind=request.follow_up_support_kind,
        max_tasks_per_claim=request.follow_up_max_tasks_per_claim,
        cooldown_seconds=request.follow_up_cooldown_seconds,
        force=request.follow_up_force,
    )
    follow_up_execution_claims = (
        follow_up_execution.get("claims", {})
        if isinstance(follow_up_execution, dict)
        else {}
    )

    payload: Dict[str, Any] = {
        "user_id": resolved_user_id,
        "claim_type": request.claim_type,
        "required_support_kinds": required_support_kinds,
        "follow_up_support_kind": request.follow_up_support_kind,
        "follow_up_force": request.follow_up_force,
        "follow_up_execution": follow_up_execution_claims,
        "follow_up_execution_summary": {
            claim_name: _summarize_follow_up_execution_claim(claim_execution)
            for claim_name, claim_execution in follow_up_execution_claims.items()
            if isinstance(claim_execution, dict)
        },
    }

    if request.include_post_execution_review:
        payload["post_execution_review"] = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                user_id=resolved_user_id,
                claim_type=request.claim_type,
                required_support_kinds=required_support_kinds,
                follow_up_cooldown_seconds=request.follow_up_cooldown_seconds,
                include_support_summary=request.include_support_summary,
                include_overview=request.include_overview,
                include_follow_up_plan=request.include_follow_up_plan,
                execute_follow_up=False,
                follow_up_support_kind=request.follow_up_support_kind,
                follow_up_max_tasks_per_claim=request.follow_up_max_tasks_per_claim,
            ),
        )

    return payload