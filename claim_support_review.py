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


def _summarize_claim_coverage_claim(
    claim_type: str,
    coverage_claim: Dict[str, Any],
    overview_claim: Dict[str, Any],
    gap_claim: Dict[str, Any],
    contradiction_claim: Dict[str, Any],
) -> Dict[str, Any]:
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
    gaps = mediator.get_claim_support_gaps(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        required_support_kinds=required_support_kinds,
    )
    contradiction_candidates = mediator.get_claim_contradiction_candidates(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
    )
    gap_claims = gaps.get("claims", {}) if isinstance(gaps, dict) else {}
    contradiction_claims = (
        contradiction_candidates.get("claims", {})
        if isinstance(contradiction_candidates, dict)
        else {}
    )
    coverage_summary = {
        claim_name: _summarize_claim_coverage_claim(
            claim_name,
            claim_matrix,
            overview_claims.get(claim_name, {}),
            gap_claims.get(claim_name, {}),
            contradiction_claims.get(claim_name, {}),
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