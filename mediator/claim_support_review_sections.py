"""Extracted claim-support review builders.

The owner module imports these callables and does not define them again.
Owner helpers are bound after that module has finished defining them.
"""

from __future__ import annotations

EXTRACTED_REVIEW_SECTION_NAMES = (
    "_build_review_workflow_priority",
    "summarize_claim_reasoning_review",
    "build_claim_support_review_payload",
)


def _bind_owner_namespace() -> None:
    """Copy owner helpers into this module once the owner is available."""
    import sys

    owner = sys.modules.get("mediator.claim_support_review")
    if owner is None:
        import mediator.claim_support_review as owner  # type: ignore

    extracted = set(EXTRACTED_REVIEW_SECTION_NAMES)
    module_globals = globals()
    for name, value in vars(owner).items():
        if name.startswith("__") or name in extracted or name in module_globals:
            continue
        module_globals[name] = value


def _build_review_workflow_priority(
    *,
    intake_status: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
    workflow_phase_priority: Dict[str, Any],
) -> Dict[str, Any]:
    document_grounding_lane_outcome_summary = (
        intake_case_summary.get("document_grounding_lane_outcome_summary")
        if isinstance(intake_case_summary.get("document_grounding_lane_outcome_summary"), dict)
        else {}
    )
    document_grounding_improvement_next_action = (
        intake_case_summary.get("document_grounding_improvement_next_action")
        if isinstance(intake_case_summary.get("document_grounding_improvement_next_action"), dict)
        else {}
    )
    grounding_action = str(document_grounding_improvement_next_action.get("action") or "").strip().lower()
    if grounding_action in {"refine_document_grounding_strategy", "retarget_document_grounding"}:
        claim_element_id = str(document_grounding_improvement_next_action.get("claim_element_id") or "").strip()
        suggested_claim_element_id = str(document_grounding_improvement_next_action.get("suggested_claim_element_id") or "").strip()
        preferred_support_kind = str(document_grounding_improvement_next_action.get("preferred_support_kind") or "").strip()
        suggested_support_kind = str(document_grounding_improvement_next_action.get("suggested_support_kind") or "").strip()
        focus_section = str(document_grounding_improvement_next_action.get("focus_section") or "").strip()
        status = str(document_grounding_improvement_next_action.get("status") or "stalled").strip().lower() or "stalled"
        attempted_support_kind = str(document_grounding_lane_outcome_summary.get("attempted_support_kind") or "").strip()
        learned_support_kind = str(document_grounding_lane_outcome_summary.get("recommended_future_support_kind") or "").strip()
        chip_labels = [f"grounding status: {humanize_workflow_priority_label(status)}"]
        if claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(claim_element_id)}")
        if suggested_claim_element_id and suggested_claim_element_id != claim_element_id:
            chip_labels.append(f"next target element: {humanize_workflow_priority_label(suggested_claim_element_id)}")
        if focus_section:
            chip_labels.append(f"focus section: {humanize_workflow_priority_label(focus_section)}")
        if preferred_support_kind:
            chip_labels.append(f"current support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        if attempted_support_kind and attempted_support_kind != preferred_support_kind:
            chip_labels.append(f"attempted lane: {humanize_workflow_priority_label(attempted_support_kind)}")
        if learned_support_kind:
            chip_labels.append(f"learned next lane: {humanize_workflow_priority_label(learned_support_kind)}")
        elif suggested_support_kind:
            chip_labels.append(f"suggested next lane: {humanize_workflow_priority_label(suggested_support_kind)}")
        notes = [
            str(
                document_grounding_improvement_next_action.get("description")
                or "Grounding recovery stalled; switch support lanes or retarget the next grounding cycle."
            ).strip(),
            "Review the factual allegations and try a different support lane or narrower claim-element target before continuing broad document revisions.",
        ]
        if learned_support_kind:
            notes.append(
                f"Recent grounding cycles suggest {humanize_workflow_priority_label(learned_support_kind)} is the stronger lane for the next recovery pass."
            )
        if grounding_action == "retarget_document_grounding" and suggested_claim_element_id and suggested_claim_element_id != claim_element_id:
            notes.append(
                f"Shift the next grounding pass from {humanize_workflow_priority_label(claim_element_id)} to {humanize_workflow_priority_label(suggested_claim_element_id)}."
            )
        return {
            "status": "warning",
            "status_id": grounding_action,
            "title": (
                "Retarget document grounding"
                if grounding_action == "retarget_document_grounding"
                else "Refine document grounding strategy"
            ),
            "chip_labels": chip_labels,
            "notes": notes,
            "buttons": [
                _build_review_workflow_priority_button(
                    "intake-next-action-review-grounding-strategy",
                    "Review grounding strategy",
                )
            ],
            "action_id": grounding_action,
            "status_message": (
                "Reviewing document grounding strategy, support-lane targeting, and next claim-element focus."
                if grounding_action == "retarget_document_grounding"
                else "Reviewing document grounding strategy and support-lane targeting."
            ),
        }

    document_drafting_next_action = (
        intake_case_summary.get("document_drafting_next_action")
        if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
        else {}
    )
    if str(document_drafting_next_action.get("action") or "").strip().lower() == "realign_document_drafting":
        target_claim_element_id = str(document_drafting_next_action.get("claim_element_id") or "").strip()
        executed_claim_element_id = str(document_drafting_next_action.get("executed_claim_element_id") or "").strip()
        focus_section = str(document_drafting_next_action.get("focus_section") or "").strip()
        preferred_support_kind = str(document_drafting_next_action.get("preferred_support_kind") or "").strip()
        chip_labels = []
        if target_claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(target_claim_element_id)}")
        if executed_claim_element_id:
            chip_labels.append(f"executed first: {humanize_workflow_priority_label(executed_claim_element_id)}")
        if focus_section:
            chip_labels.append(f"focus section: {humanize_workflow_priority_label(focus_section)}")
        if preferred_support_kind:
            chip_labels.append(f"support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        return {
            "status": "warning",
            "status_id": "realign_document_drafting",
            "title": "Realign drafting before further revisions",
            "chip_labels": chip_labels,
            "notes": [
                str(
                    document_drafting_next_action.get("description")
                    or "Realign drafting to the top targeted claim element before further revisions."
                ).strip(),
                "Open the formal complaint builder and redirect the next draft revision toward the targeted legal element before broadening further edits.",
            ],
            "buttons": [
                _build_review_workflow_priority_button(
                    "intake-next-action-open-document-builder",
                    "Open formal complaint builder",
                )
            ],
            "action_id": "realign_document_drafting",
            "status_message": "Opening the formal complaint builder for drafting realignment.",
        }

    next_action = intake_case_summary.get("next_action") if isinstance(intake_case_summary.get("next_action"), dict) else {}
    if not next_action and isinstance(intake_status.get("next_action"), dict):
        next_action = dict(intake_status.get("next_action") or {})

    action = str(next_action.get("action") or "").strip().lower()
    if not action:
        return _build_review_workflow_priority_from_phase(workflow_phase_priority)

    contradiction_summary = (
        intake_case_summary.get("contradiction_summary")
        if isinstance(intake_case_summary.get("contradiction_summary"), dict)
        else {}
    )
    question_candidate_summary = (
        intake_case_summary.get("question_candidate_summary")
        if isinstance(intake_case_summary.get("question_candidate_summary"), dict)
        else {}
    )
    timeline_anchor_summary = (
        intake_case_summary.get("timeline_anchor_summary")
        if isinstance(intake_case_summary.get("timeline_anchor_summary"), dict)
        else {}
    )
    canonical_fact_summary = (
        intake_case_summary.get("canonical_fact_summary")
        if isinstance(intake_case_summary.get("canonical_fact_summary"), dict)
        else {}
    )
    candidate_claim_summary = (
        intake_case_summary.get("candidate_claim_summary")
        if isinstance(intake_case_summary.get("candidate_claim_summary"), dict)
        else {}
    )
    intake_matching_summary = (
        intake_case_summary.get("intake_matching_summary")
        if isinstance(intake_case_summary.get("intake_matching_summary"), dict)
        else {}
    )
    intake_legal_targeting_summary = (
        intake_case_summary.get("intake_legal_targeting_summary")
        if isinstance(intake_case_summary.get("intake_legal_targeting_summary"), dict)
        else {}
    )
    intake_evidence_alignment_summary = (
        intake_case_summary.get("intake_evidence_alignment_summary")
        if isinstance(intake_case_summary.get("intake_evidence_alignment_summary"), dict)
        else {}
    )
    claim_support_packet_summary = (
        intake_case_summary.get("claim_support_packet_summary")
        if isinstance(intake_case_summary.get("claim_support_packet_summary"), dict)
        else {}
    )
    temporal_issue_registry_summary = (
        intake_case_summary.get("temporal_issue_registry_summary")
        if isinstance(intake_case_summary.get("temporal_issue_registry_summary"), dict)
        else {}
    )
    summary_confirmation = (
        intake_case_summary.get("complainant_summary_confirmation")
        if isinstance(intake_case_summary.get("complainant_summary_confirmation"), dict)
        else {}
    )
    alignment_promotion_drift_summary = (
        intake_case_summary.get("alignment_promotion_drift_summary")
        if isinstance(intake_case_summary.get("alignment_promotion_drift_summary"), dict)
        else {}
    )
    alignment_validation_focus_summary = (
        intake_case_summary.get("alignment_validation_focus_summary")
        if isinstance(intake_case_summary.get("alignment_validation_focus_summary"), dict)
        else {}
    )
    alignment_evidence_tasks = [
        item for item in (intake_case_summary.get("alignment_evidence_tasks") or []) if isinstance(item, dict)
    ]
    alignment_task_updates = [
        item for item in (intake_case_summary.get("alignment_task_updates") or []) if isinstance(item, dict)
    ]
    alignment_task_update_history = [
        item for item in (intake_case_summary.get("alignment_task_update_history") or []) if isinstance(item, dict)
    ]
    visible_alignment_task_updates = alignment_task_update_history or alignment_task_updates

    focused_claim_type = str(next_action.get("claim_type") or "").strip().lower()
    focused_element_id = str(next_action.get("claim_element_id") or "").strip().lower()
    focused_element_label = str(next_action.get("claim_element_label") or "").strip()
    recommended_actions = [
        str(item).strip()
        for item in (next_action.get("recommended_actions") or [])
        if str(item or "").strip()
    ]

    def humanize(value: Any) -> str:
        return humanize_workflow_priority_label(value)

    def build_priority(
        *,
        status: str = "warning",
        title: str,
        status_id: str,
        chip_labels: List[str],
        notes: List[str],
        buttons: List[Dict[str, Any]],
        status_message: str,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "title": title,
            "status_id": status_id,
            "chip_labels": [item for item in chip_labels if item],
            "notes": [item for item in notes if item],
            "buttons": [item for item in buttons if isinstance(item, dict) and item.get("id")],
            "action_id": action,
            "status_message": status_message,
        }

    if action == "validate_promoted_support":
        drift_summary = dict(next_action.get("drift_summary") or {}) if isinstance(next_action.get("drift_summary"), dict) else dict(alignment_promotion_drift_summary)
        primary_validation_target = (
            dict(intake_status.get("primary_validation_target") or {})
            if isinstance(intake_status.get("primary_validation_target"), dict)
            else {}
        )
        if not primary_validation_target and isinstance(next_action.get("primary_validation_target"), dict):
            primary_validation_target = dict(next_action.get("primary_validation_target") or {})
        if not primary_validation_target and isinstance(alignment_validation_focus_summary.get("primary_target"), dict):
            primary_validation_target = dict(alignment_validation_focus_summary.get("primary_target") or {})
        pending_conversion_count = int(next_action.get("pending_conversion_count") or drift_summary.get("pending_conversion_count") or 0)
        promoted_count = int(next_action.get("promoted_count") or drift_summary.get("promoted_count") or 0)
        validation_target_count = int(
            next_action.get("validation_target_count")
            or alignment_validation_focus_summary.get("count")
            or len(alignment_validation_focus_summary.get("targets") or [])
            or 0
        )
        drift_ratio = float(drift_summary.get("drift_ratio") or 0.0)
        proof_readiness_score = float(drift_summary.get("proof_readiness_score") or 0.0)
        chip_labels = [
            f"recommended action: {action}",
            f"pending conversion: {pending_conversion_count}",
            f"promoted updates: {promoted_count}",
            f"validation targets: {validation_target_count}",
            f"drift ratio: {drift_ratio:.2f}",
            f"proof readiness: {proof_readiness_score:.2f}",
        ]
        if focused_claim_type:
            chip_labels.append(f"focus claim: {humanize(focused_claim_type)}")
        if focused_element_id:
            chip_labels.append(f"focus element: {humanize(focused_element_id)}")
        primary_target_claim_type = str(primary_validation_target.get("claim_type") or focused_claim_type or "").strip()
        primary_target_element_id = str(primary_validation_target.get("claim_element_id") or focused_element_id or "").strip()
        if primary_target_element_id:
            chip_labels.append(f"primary target: {humanize(primary_target_element_id)}")
        primary_target_kind = str(primary_validation_target.get("promotion_kind") or "").strip()
        if primary_target_kind:
            chip_labels.append(f"primary promotion kind: {humanize(primary_target_kind)}")
        primary_target_ref = str(primary_validation_target.get("promotion_ref") or "").strip()
        if primary_target_ref:
            chip_labels.append(f"primary promotion ref: {primary_target_ref}")
        notes = [
            "Promoted testimony or document support is accumulating faster than packet validation is reaching resolved supported status.",
        ]
        if primary_target_element_id:
            notes.append(f"Primary validation target: {humanize(primary_target_element_id)}.")
        if primary_target_ref:
            notes.append(f"Primary promotion ref: {primary_target_ref}.")
        notes.append("Review and validate saved support before treating the evidence phase as truly settled.")
        buttons = [
            _build_review_workflow_priority_button(
                "intake-next-action-open-promoted",
                "Review promoted updates",
                data_attrs={
                    "claim_type": primary_target_claim_type,
                    "claim_element_id": primary_target_element_id,
                },
            ),
        ]
        if primary_target_element_id:
            buttons.extend(
                [
                    _build_review_workflow_priority_button(
                        "intake-next-action-prefill-testimony",
                        "Prefill testimony validation",
                        style="tertiary",
                        data_attrs={
                            "claim_type": primary_target_claim_type,
                            "claim_element_id": primary_target_element_id,
                        },
                    ),
                    _build_review_workflow_priority_button(
                        "intake-next-action-prefill-document",
                        "Prefill document validation",
                        style="tertiary",
                        data_attrs={
                            "claim_type": primary_target_claim_type,
                            "claim_element_id": primary_target_element_id,
                        },
                    ),
                ]
            )
        return build_priority(
            title="Validate promoted support",
            status_id=action,
            chip_labels=chip_labels,
            notes=notes,
            buttons=buttons,
            status_message="Showing promoted alignment updates that still need validation.",
        )

    if action == "build_knowledge_graph":
        timeline_anchor_count = int(timeline_anchor_summary.get("count") or 0)
        canonical_fact_count = int(canonical_fact_summary.get("count") or 0)
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        readiness_score = float(next_action.get("intake_readiness_score") or 0.0)
        chip_labels = [
            "recommended action: build_knowledge_graph",
            f"timeline anchors: {timeline_anchor_count}",
            f"canonical facts: {canonical_fact_count}",
            f"question candidates: {question_candidate_count}",
        ]
        if readiness_score > 0:
            chip_labels.append(f"readiness score: {readiness_score:.2f}")
        return build_priority(
            title="Build intake knowledge graph",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Intake facts and timeline anchors are present, but the knowledge graph has not been built into an operator-reviewable structure yet.",
                "Focus the timeline and canonical fact diagnostics before advancing graph-dependent intake work.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-knowledge-graph", "Review intake graph inputs")],
            status_message="Showing timeline and canonical fact inputs for intake graph building.",
        )

    if action == "build_dependency_graph":
        aligned_element_count = int(intake_evidence_alignment_summary.get("aligned_element_count") or 0)
        contradiction_count = int(contradiction_summary.get("count") or 0)
        alignment_task_count = len(alignment_evidence_tasks)
        readiness_score = float(next_action.get("intake_readiness_score") or 0.0)
        chip_labels = [
            "recommended action: build_dependency_graph",
            f"aligned elements: {aligned_element_count}",
            f"alignment tasks: {alignment_task_count}",
            f"contradictions: {contradiction_count}",
        ]
        if readiness_score > 0:
            chip_labels.append(f"readiness score: {readiness_score:.2f}")
        return build_priority(
            title="Build intake dependency graph",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Intake sections are populated enough to map cross-section dependencies, but the dependency graph has not been built yet.",
                "Review contradictions and alignment summaries before dependency-driven intake routing continues.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-dependencies", "Review dependency inputs")],
            status_message="Showing alignment and contradiction inputs for dependency graph review.",
        )

    if action == "continue_denoising":
        intake_blockers = [item for item in (next_action.get("intake_blockers") or []) if str(item or "").strip()]
        contradiction_count = int(contradiction_summary.get("count") or 0)
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        readiness_score = float(next_action.get("intake_readiness_score") or 0.0)
        chip_labels = [
            "recommended action: continue_denoising",
            f"blockers: {len(intake_blockers)}",
            f"contradictions: {contradiction_count}",
            f"question candidates: {question_candidate_count}",
        ]
        if readiness_score > 0:
            chip_labels.append(f"readiness score: {readiness_score:.2f}")
        return build_priority(
            title="Continue intake denoising",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Intake contradictions or open clarification paths still need another denoising pass before the case theory can settle.",
                "Review the contradiction queue and targeted questions that should drive the next intake refinement pass.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-denoising", "Review denoising queue")],
            status_message="Showing contradictions and targeted questions for continued intake denoising.",
        )

    if action == "build_legal_graph":
        candidate_claim_count = int(candidate_claim_summary.get("count") or 0)
        targeted_claims = intake_legal_targeting_summary.get("claims") if isinstance(intake_legal_targeting_summary.get("claims"), dict) else intake_matching_summary.get("claims") if isinstance(intake_matching_summary.get("claims"), dict) else {}
        targeted_claim_entries = list(targeted_claims.items())
        open_legal_element_count = sum(
            int((claim or {}).get("missing_requirement_count") or 0)
            for _, claim in targeted_claim_entries
            if isinstance(claim, dict)
        )
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        return build_priority(
            title="Build legal graph",
            status_id=action,
            chip_labels=[
                "recommended action: build_legal_graph",
                f"candidate claims: {candidate_claim_count}",
                f"targeted claims: {len(targeted_claim_entries)}",
                f"open legal elements: {open_legal_element_count}",
                f"question candidates: {question_candidate_count}",
            ],
            notes=[
                "Claim targeting is available, but the legal graph that organizes statutes and requirements has not been built yet.",
                "Review unresolved legal elements and mapped question targets before building the formalization graph.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-legal-graph", "Review legal graph inputs")],
            status_message="Showing unresolved legal elements and question targets for legal graph review.",
        )

    if action == "perform_neurosymbolic_matching":
        targeted_claims = intake_legal_targeting_summary.get("claims") if isinstance(intake_legal_targeting_summary.get("claims"), dict) else intake_matching_summary.get("claims") if isinstance(intake_matching_summary.get("claims"), dict) else {}
        targeted_claim_entries = list(targeted_claims.items())
        open_legal_element_count = sum(
            int((claim or {}).get("missing_requirement_count") or 0)
            for _, claim in targeted_claim_entries
            if isinstance(claim, dict)
        )
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        return build_priority(
            title="Perform neurosymbolic matching",
            status_id=action,
            chip_labels=[
                "recommended action: perform_neurosymbolic_matching",
                f"targeted claims: {len(targeted_claim_entries)}",
                f"open legal elements: {open_legal_element_count}",
                f"question candidates: {question_candidate_count}",
            ],
            notes=[
                "The legal graph is available, but formal claim-to-law matching still needs operator review support.",
                "Review unresolved legal elements and matching questions before running the neurosymbolic matcher.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-matching", "Review matching inputs")],
            status_message="Showing unresolved legal elements and question targets for neurosymbolic matching.",
        )

    if action == "generate_formal_complaint":
        claim_count = int(claim_support_packet_summary.get("claim_count") or 0)
        element_count = int(claim_support_packet_summary.get("element_count") or 0)
        proof_readiness_score = float(claim_support_packet_summary.get("proof_readiness_score") or 0.0)
        draft_ready_ratio = float(claim_support_packet_summary.get("draft_ready_element_ratio") or 0.0)
        return build_priority(
            title="Generate formal complaint",
            status_id=action,
            chip_labels=[
                "recommended action: generate_formal_complaint",
                f"claims: {claim_count}",
                f"elements: {element_count}",
                f"packet draft ready: {draft_ready_ratio:.2f}",
                f"proof readiness: {proof_readiness_score:.2f}",
            ],
            notes=[
                "Formalization is ready to move from matching outputs into a draft complaint package.",
                "Open the formal complaint builder with the current claim and user context preserved.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-open-formal-generator", "Open formal complaint builder")],
            status_message="Opening the formal complaint builder.",
        )

    if action == "build_claim_support_packets":
        packet_element_count = int(claim_support_packet_summary.get("element_count") or 0)
        packet_claim_count = int(claim_support_packet_summary.get("claim_count") or 0)
        chip_labels = [
            "recommended action: build_claim_support_packets",
            f"claims: {packet_claim_count}",
            f"elements: {packet_element_count}",
        ]
        for item in recommended_actions[:2]:
            chip_labels.append(f"recommended lane: {humanize(item)}")
        return build_priority(
            title="Build claim support packets",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Evidence records exist, but the claim support packet still needs an explicit packet build before evidence review can be trusted.",
                "Execute the packet-building follow-up to refresh packet statuses and downstream review surfaces.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-build-packets", "Build claim support packets")],
            status_message="Executing claim support packet follow-up.",
        )

    if action == "resolve_support_conflicts":
        manual_review_blocker_count = sum(
            1
            for update in visible_alignment_task_updates
            if str((update or {}).get("resolution_status") or "").strip().lower() == "needs_manual_review"
        )
        reviewable_escalations = int(
            claim_support_packet_summary.get("claim_support_reviewable_escalation_count")
            or manual_review_blocker_count
            or 0
        )
        unresolved_without_review_path = int(
            claim_support_packet_summary.get("claim_support_unresolved_without_review_path_count") or 0
        )
        claim_type = str(next_action.get("claim_type") or "").strip()
        claim_element_id = str(next_action.get("claim_element_id") or "").strip()
        claim_element_text = focused_element_label or claim_element_id
        chip_labels = [
            "recommended action: resolve_support_conflicts",
            f"manual review blockers: {manual_review_blocker_count}",
            f"packet escalations: {reviewable_escalations}",
        ]
        if unresolved_without_review_path > 0:
            chip_labels.append(f"without review path: {unresolved_without_review_path}")
        if focused_claim_type:
            chip_labels.append(f"focus claim: {humanize(focused_claim_type)}")
        if focused_element_id:
            chip_labels.append(f"focus element: {humanize(focused_element_id)}")
        support_status = str(next_action.get("support_status") or "").strip()
        if support_status:
            chip_labels.append(f"support status: {humanize(support_status)}")
        for item in recommended_actions[:2]:
            chip_labels.append(f"recommended lane: {humanize(item)}")
        return build_priority(
            title="Resolve support conflicts",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Contradicted or escalated support is blocking evidence completion for a priority element.",
                "Open the manual-review queue and resolve the focused conflict before evidence drift expands.",
            ],
            buttons=[
                _build_review_workflow_priority_button(
                    "intake-next-action-review-conflicts",
                    "Review manual conflicts",
                    data_attrs={
                        "claim_type": claim_type,
                        "claim_element_id": claim_element_id,
                        "claim_element_text": claim_element_text,
                    },
                ),
                _build_review_workflow_priority_button(
                    "intake-next-action-prefill-resolution",
                    "Load into resolution form",
                    style="tertiary",
                    data_attrs={
                        "claim_element_id": claim_element_id,
                        "claim_element_text": claim_element_text,
                    },
                ),
            ],
            status_message="Showing manual-review conflicts that are blocking evidence completion.",
        )

    if action in {"fill_temporal_chronology_gap", "fill_evidence_gaps"}:
        prioritized_alignment_tasks = [item for item in (next_action.get("alignment_tasks") or []) if isinstance(item, dict)]
        focused_alignment_task = next(
            (
                task for task in prioritized_alignment_tasks
                if (
                    not focused_claim_type
                    or str(task.get("claim_type") or "").strip().lower() == focused_claim_type
                )
                and (
                    not focused_element_id
                    or str(task.get("claim_element_id") or "").strip().lower() == focused_element_id
                )
            ),
            {},
        )
        if not focused_alignment_task:
            focused_alignment_task = next(
                (
                    task for task in alignment_evidence_tasks
                    if (
                        not focused_claim_type
                        or str(task.get("claim_type") or "").strip().lower() == focused_claim_type
                    )
                    and (
                        not focused_element_id
                        or str(task.get("claim_element_id") or "").strip().lower() == focused_element_id
                    )
                ),
                {},
            )
        preferred_support_kind = str(focused_alignment_task.get("preferred_support_kind") or "").strip().lower()
        fallback_lanes = [str(item).strip() for item in (focused_alignment_task.get("fallback_lanes") or []) if str(item or "").strip()]
        claim_type = str(next_action.get("claim_type") or "").strip()
        claim_element_id = str(next_action.get("claim_element_id") or "").strip()
        claim_element_text = focused_element_label or claim_element_id
        chip_labels = [f"recommended action: {action}"]
        if action == "fill_temporal_chronology_gap":
            unresolved_issue_ids = []
            for field_name in ("temporal_issue_ids", "timeline_issue_ids"):
                unresolved_issue_ids.extend(
                    [str(item).strip() for item in (focused_alignment_task.get(field_name) or []) if str(item or "").strip()]
                )
            unresolved_issue_ids = list(dict.fromkeys(unresolved_issue_ids))
            unresolved_issue_count = int(
                temporal_issue_registry_summary.get("unresolved_count")
                or len(unresolved_issue_ids)
                or 0
            )
            resolved_issue_count = int(temporal_issue_registry_summary.get("resolved_count") or 0)
            chip_labels.append(f"chronology issues: {unresolved_issue_count}")
            if resolved_issue_count > 0:
                chip_labels.append(f"resolved chronology issues: {resolved_issue_count}")
            title = "Resolve chronology blockers"
            notes = [
                "Temporal ordering is still unresolved for a shared intake-to-packet element.",
                "Review the chronology task, inspect the unresolved issue IDs, and collect support that clears the temporal blocker before advancing evidence completion.",
                f"Unresolved chronology issue IDs: {', '.join(unresolved_issue_ids) if unresolved_issue_ids else 'none recorded'}",
            ]
            if resolved_issue_count > 0:
                notes.append(
                    f"Resolved chronology history retained: {resolved_issue_count} issue(s)."
                )
            button_id = "intake-next-action-review-chronology-task"
            button_label = "Review chronology task"
            status = "blocked"
            status_message = "Showing chronology blocker task and unresolved issue IDs."
        else:
            title = "Fill evidence gaps"
            notes = [
                "Priority evidence is still missing for a shared intake-to-packet element.",
                "Review the focused evidence task and preferred support lane before advancing the packet.",
            ]
            button_id = "intake-next-action-review-evidence-task"
            button_label = "Review evidence task"
            status = "warning"
            status_message = "Showing priority evidence task and preferred support lane."
        if focused_claim_type:
            chip_labels.append(f"focus claim: {humanize(focused_claim_type)}")
        if focused_element_id:
            chip_labels.append(f"focus element: {humanize(focused_element_id)}")
        support_status = str(next_action.get("support_status") or "").strip()
        if support_status:
            chip_labels.append(f"support status: {humanize(support_status)}")
        temporal_objective = str(focused_alignment_task.get("temporal_proof_objective") or "").strip()
        if temporal_objective:
            chip_labels.append(f"chronology objective: {humanize(temporal_objective)}")
        if preferred_support_kind:
            chip_labels.append(f"preferred lane: {humanize(preferred_support_kind)}")
        quality_target = str(focused_alignment_task.get("source_quality_target") or "").strip()
        if quality_target:
            chip_labels.append(f"quality target: {humanize(quality_target)}")
        for lane in fallback_lanes[:2]:
            chip_labels.append(f"fallback lane: {humanize(lane)}")
        return build_priority(
            status=status,
            title=title,
            status_id=action,
            chip_labels=chip_labels,
            notes=notes,
            buttons=[
                _build_review_workflow_priority_button(
                    button_id,
                    button_label,
                    data_attrs={
                        "claim_type": claim_type,
                        "claim_element_id": claim_element_id,
                        "claim_element_text": claim_element_text,
                        "support_kind": preferred_support_kind,
                    },
                )
            ],
            status_message=status_message,
        )

    if action == "complete_evidence":
        proof_readiness_score = float(claim_support_packet_summary.get("proof_readiness_score") or 0.0)
        evidence_completion_ready = bool(claim_support_packet_summary.get("evidence_completion_ready"))
        chip_labels = [
            "recommended action: complete_evidence",
            f"packet completion ready: {'yes' if evidence_completion_ready else 'no'}",
            f"proof readiness: {proof_readiness_score:.2f}",
        ]
        for item in recommended_actions[:2]:
            chip_labels.append(f"recommended lane: {humanize(item)}")
        return build_priority(
            title="Begin formal complaint drafting",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Evidence support is sufficiently assembled to move from packet review into formal complaint drafting.",
                "Open the formal complaint builder with the current claim and user context preserved.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-open-document-builder", "Open formal complaint builder")],
            status_message="Opening the formal complaint builder.",
        )

    if action == "address_gaps":
        action_gaps = [str(item).strip() for item in (next_action.get("gaps") or []) if str(item or "").strip()]
        intake_blockers = [str(item).strip() for item in (next_action.get("intake_blockers") or []) if str(item or "").strip()]
        contradiction_count = int(contradiction_summary.get("count") or 0)
        question_candidate_count = int(question_candidate_summary.get("count") or 0)
        readiness_score = float(next_action.get("intake_readiness_score") or 0.0)
        chip_labels = [
            "recommended action: address_gaps",
            f"gap count: {len(action_gaps)}",
            f"blockers: {len(intake_blockers)}",
            f"contradictions: {contradiction_count}",
            f"question candidates: {question_candidate_count}",
        ]
        if readiness_score > 0:
            chip_labels.append(f"readiness score: {readiness_score:.2f}")
        for gap in action_gaps[:2]:
            chip_labels.append(f"gap: {humanize(gap)}")
        return build_priority(
            title="Review intake gaps",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "Intake still has unresolved proof or chronology gaps that should be clarified before handoff quality degrades.",
                "Review the unresolved intake matching diagnostics and targeted questions.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-review-gaps", "Review intake gaps")],
            status_message="Showing unresolved intake gaps and targeted questions.",
        )

    if action == "confirm_intake_summary":
        current_summary_snapshot = (
            summary_confirmation.get("current_summary_snapshot")
            if isinstance(summary_confirmation.get("current_summary_snapshot"), dict)
            else {}
        )
        chip_labels = [
            "recommended action: confirm_intake_summary",
            f"candidate claims: {int(current_summary_snapshot.get('candidate_claim_count') or 0)}",
            f"canonical facts: {int(current_summary_snapshot.get('canonical_fact_count') or 0)}",
            f"proof leads: {int(current_summary_snapshot.get('proof_lead_count') or 0)}",
        ]
        open_item_count = int(current_summary_snapshot.get("open_item_count") or 0)
        if open_item_count > 0:
            chip_labels.append(f"open items: {open_item_count}")
        return build_priority(
            title="Confirm intake summary",
            status_id=action,
            chip_labels=chip_labels,
            notes=[
                "The latest intake summary snapshot is still waiting for complainant confirmation before the intake phase can fully settle.",
                "Add an optional confirmation note above if needed, then confirm the intake summary.",
            ],
            buttons=[_build_review_workflow_priority_button("intake-next-action-confirm-summary", "Confirm intake summary")],
            status_message="Confirming the current intake summary snapshot.",
        )

    return _build_review_workflow_priority_from_phase(workflow_phase_priority)


def summarize_claim_reasoning_review(
    validation_claim: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    preview_limit = 3

    claim_validation = validation_claim if isinstance(validation_claim, dict) else {}
    elements = claim_validation.get("elements", [])
    if not isinstance(elements, list):
        elements = []
    claim_temporal_issue_count = int(
        claim_validation.get("claim_temporal_issue_count", 0) or 0
    )
    claim_unresolved_temporal_issue_count = int(
        claim_validation.get("claim_unresolved_temporal_issue_count", 0) or 0
    )
    claim_resolved_temporal_issue_count = int(
        claim_validation.get("claim_resolved_temporal_issue_count", 0) or 0
    )
    claim_temporal_issue_status_counts = (
        dict(claim_validation.get("claim_temporal_issue_status_counts") or {})
        if isinstance(claim_validation.get("claim_temporal_issue_status_counts"), dict)
        else {}
    )
    claim_temporal_issue_ids = [
        str(item).strip()
        for item in (claim_validation.get("claim_temporal_issue_ids") or [])
        if str(item).strip()
    ]
    claim_missing_temporal_predicates = [
        str(item).strip()
        for item in (claim_validation.get("claim_missing_temporal_predicates") or [])
        if str(item).strip()
    ]
    claim_required_provenance_kinds = [
        str(item).strip()
        for item in (claim_validation.get("claim_required_provenance_kinds") or [])
        if str(item).strip()
    ]

    flagged_elements: List[Dict[str, Any]] = []
    fallback_ontology_element_count = 0
    unavailable_backend_element_count = 0
    degraded_adapter_element_count = 0
    hybrid_bridge_element_count = 0
    hybrid_bridge_available_element_count = 0
    hybrid_tdfol_formula_count = 0
    hybrid_dcec_formula_count = 0
    hybrid_tdfol_formula_preview: List[str] = []
    hybrid_dcec_formula_preview: List[str] = []
    hybrid_formalism = ""
    hybrid_reasoning_mode = ""
    hybrid_compiler_bridge_path = ""
    temporal_element_count = 0
    temporal_fact_count = 0
    temporal_relation_count = 0
    temporal_issue_count = 0
    temporal_partial_order_ready_element_count = 0
    temporal_warning_count = 0
    temporal_warning_preview: List[str] = []
    temporal_relation_type_counts: Dict[str, int] = {}
    temporal_relation_preview: List[str] = []
    temporal_rule_profile_available_element_count = 0
    temporal_rule_profile_satisfied_element_count = 0
    temporal_rule_profile_partial_element_count = 0
    temporal_rule_profile_failed_element_count = 0
    temporal_proof_bundle_count = 0
    temporal_proof_bundle_status_counts: Dict[str, int] = {}
    # T3: proof_bundles keyed by "claim_type:element_id" for direct drilldown access.
    proof_bundles: Dict[str, Any] = {}
    theorem_export_blocked_element_count = 0
    theorem_export_chronology_task_count = 0
    proof_artifact_element_count = 0
    proof_artifact_available_element_count = 0
    proof_artifact_status_counts: Dict[str, int] = {}
    proof_artifact_explanation_element_count = 0
    proof_artifact_preview: List[str] = []

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
            and capability_state_from_payload(summary)
            in {LogicCapabilityState.UNAVAILABLE, LogicCapabilityState.DEGRADED}
        )
        used_fallback_ontology = bool(reasoning.get("used_fallback_ontology"))
        hybrid_reasoning = reasoning.get("hybrid_reasoning", {})
        if not isinstance(hybrid_reasoning, dict):
            hybrid_reasoning = {}
        hybrid_result = hybrid_reasoning.get("result", {})
        if not isinstance(hybrid_result, dict):
            hybrid_result = {}
        hybrid_bridge_used = bool(hybrid_reasoning)
        hybrid_bridge_available = bool(hybrid_result.get("compiler_bridge_available", False))
        element_formalism = str(hybrid_result.get("formalism") or "").strip()
        element_reasoning_mode = str(hybrid_result.get("reasoning_mode") or "").strip()
        element_compiler_bridge_path = str(
            hybrid_result.get("compiler_bridge_path") or ""
        ).strip()
        hybrid_tdfol_formulas = [
            str(formula)
            for formula in (hybrid_result.get("tdfol_formulas", []) or [])
            if str(formula).strip()
        ]
        hybrid_dcec_formulas = [
            str(formula)
            for formula in (hybrid_result.get("dcec_formulas", []) or [])
            if str(formula).strip()
        ]
        proof_artifact = hybrid_result.get("proof_artifact", {})
        if not isinstance(proof_artifact, dict):
            proof_artifact = {}
        element_proof_artifact_available = bool(proof_artifact.get("available", False))
        element_proof_artifact_status = str(
            proof_artifact.get("status") or ""
        ).strip()
        element_proof_artifact_proof_id = str(
            proof_artifact.get("proof_id") or ""
        ).strip()
        element_proof_artifact_proof_status = str(
            proof_artifact.get("proof_status") or ""
        ).strip()
        element_proof_artifact_sentence = str(
            proof_artifact.get("sentence") or ""
        ).strip()
        element_proof_artifact_reason = str(
            proof_artifact.get("reason") or ""
        ).strip()
        element_proof_artifact_violation_count = int(
            proof_artifact.get("violation_count", 0) or 0
        )
        proof_artifact_explanation = proof_artifact.get("explanation", {})
        if not isinstance(proof_artifact_explanation, dict):
            proof_artifact_explanation = {}
        element_proof_artifact_explanation_format = str(
            proof_artifact_explanation.get("format") or ""
        ).strip()
        element_proof_artifact_explanation_steps = list(
            proof_artifact_explanation.get("steps", []) or []
        )
        element_proof_artifact_explanation_text = str(
            proof_artifact_explanation.get("text") or ""
        ).strip()
        element_proof_artifact_theorem_export_metadata = proof_artifact.get(
            "theorem_export_metadata", {}
        )
        if not isinstance(element_proof_artifact_theorem_export_metadata, dict):
            element_proof_artifact_theorem_export_metadata = {}
        temporal_summary = reasoning.get("temporal_summary", {})
        if not isinstance(temporal_summary, dict):
            temporal_summary = {}
        element_temporal_fact_count = int(temporal_summary.get("fact_count", 0) or 0)
        element_temporal_relation_count = int(temporal_summary.get("relation_count", 0) or 0)
        element_temporal_issue_count = int(temporal_summary.get("issue_count", 0) or 0)
        element_temporal_warning_count = int(temporal_summary.get("warning_count", 0) or 0)
        element_temporal_partial_order_ready = bool(
            temporal_summary.get("partial_order_ready", False)
        )
        element_temporal_warnings = [
            str(warning)
            for warning in (temporal_summary.get("warnings", []) or [])
            if str(warning).strip()
        ]
        element_temporal_relation_preview = [
            str(relation)
            for relation in (temporal_summary.get("relation_preview", []) or [])
            if str(relation).strip()
        ]
        element_temporal_relation_type_counts = {
            str(name): int(count or 0)
            for name, count in (temporal_summary.get("relation_type_counts", {}) or {}).items()
            if str(name).strip()
        }
        temporal_rule_profile = reasoning.get("temporal_rule_profile", {})
        if not isinstance(temporal_rule_profile, dict):
            temporal_rule_profile = {}
        element_temporal_rule_profile_id = str(
            temporal_rule_profile.get("profile_id") or ""
        ).strip()
        element_temporal_rule_frame_id = str(
            temporal_rule_profile.get("rule_frame_id") or ""
        ).strip()
        element_temporal_rule_status = str(
            temporal_rule_profile.get("status") or ""
        ).strip()
        element_temporal_rule_blocking_reasons = [
            str(reason)
            for reason in (temporal_rule_profile.get("blocking_reasons", []) or [])
            if str(reason).strip()
        ]
        element_temporal_rule_warnings = [
            str(warning)
            for warning in (temporal_rule_profile.get("warnings", []) or [])
            if str(warning).strip()
        ]
        element_temporal_rule_follow_ups = [
            follow_up
            for follow_up in (temporal_rule_profile.get("recommended_follow_ups", []) or [])
            if isinstance(follow_up, dict)
        ]
        element_temporal_rule_available = bool(temporal_rule_profile.get("available", False))
        temporal_proof_bundle = reasoning.get("temporal_proof_bundle", {})
        if not isinstance(temporal_proof_bundle, dict):
            temporal_proof_bundle = {}
        element_temporal_proof_bundle_id = str(
            temporal_proof_bundle.get("proof_bundle_id") or ""
        ).strip()
        element_temporal_proof_bundle_status = str(
            temporal_proof_bundle.get("status") or ""
        ).strip()
        element_temporal_proof_bundle_fact_ids = [
            str(fact_id)
            for fact_id in (temporal_proof_bundle.get("temporal_fact_ids", []) or [])
            if str(fact_id).strip()
        ]
        element_temporal_proof_bundle_relation_ids = [
            str(relation_id)
            for relation_id in (temporal_proof_bundle.get("temporal_relation_ids", []) or [])
            if str(relation_id).strip()
        ]
        element_temporal_proof_bundle_issue_ids = [
            str(issue_id)
            for issue_id in (temporal_proof_bundle.get("temporal_issue_ids", []) or [])
            if str(issue_id).strip()
        ]
        theorem_exports = temporal_proof_bundle.get("theorem_exports", {})
        if not isinstance(theorem_exports, dict):
            theorem_exports = {}
        element_theorem_export_metadata = theorem_exports.get("theorem_export_metadata", {})
        if not isinstance(element_theorem_export_metadata, dict):
            element_theorem_export_metadata = {}
        element_temporal_proof_bundle_tdfol_preview = [
            str(formula)
            for formula in (
                theorem_exports.get("tdfol_preview")
                or theorem_exports.get("tdfol_formulas")
                or []
            )
            if str(formula).strip()
        ][:preview_limit]
        element_temporal_proof_bundle_dcec_preview = [
            str(formula)
            for formula in (
                theorem_exports.get("dcec_preview")
                or theorem_exports.get("dcec_formulas")
                or []
            )
            if str(formula).strip()
        ][:preview_limit]
        hybrid_tdfol_count = len(hybrid_tdfol_formulas)
        hybrid_dcec_count = len(hybrid_dcec_formulas)
        element_tdfol_preview = hybrid_tdfol_formulas[:preview_limit]
        element_dcec_preview = hybrid_dcec_formulas[:preview_limit]

        if used_fallback_ontology:
            fallback_ontology_element_count += 1
        if unavailable_adapters:
            unavailable_backend_element_count += 1
        if degraded_adapters:
            degraded_adapter_element_count += 1
        if hybrid_bridge_used:
            hybrid_bridge_element_count += 1
        if hybrid_bridge_available:
            hybrid_bridge_available_element_count += 1
        hybrid_tdfol_formula_count += hybrid_tdfol_count
        hybrid_dcec_formula_count += hybrid_dcec_count
        if (
            element_temporal_fact_count
            or element_temporal_relation_count
            or element_temporal_issue_count
            or element_temporal_warning_count
            or element_temporal_relation_type_counts
            or element_temporal_relation_preview
        ):
            temporal_element_count += 1
        temporal_fact_count += element_temporal_fact_count
        temporal_relation_count += element_temporal_relation_count
        temporal_issue_count += element_temporal_issue_count
        temporal_warning_count += element_temporal_warning_count
        if element_temporal_partial_order_ready:
            temporal_partial_order_ready_element_count += 1
        if element_temporal_rule_available:
            temporal_rule_profile_available_element_count += 1
            if element_temporal_rule_status == "satisfied":
                temporal_rule_profile_satisfied_element_count += 1
            elif element_temporal_rule_status == "partial":
                temporal_rule_profile_partial_element_count += 1
            elif element_temporal_rule_status == "failed":
                temporal_rule_profile_failed_element_count += 1
        if element_temporal_proof_bundle_id:
            temporal_proof_bundle_count += 1
            temporal_proof_bundle_status_counts[element_temporal_proof_bundle_status or "unknown"] = (
                temporal_proof_bundle_status_counts.get(
                    element_temporal_proof_bundle_status or "unknown", 0
                )
                + 1
            )
            # T3: build proof_bundles keyed by "claim_type:element_id" so callers can
            # look up a specific element's proof bundle without scanning flagged_elements.
            element_id = str(element.get("element_id") or "").strip()
            proof_bundle_claim_type = str(claim_validation.get("claim_type") or "").strip()
            if element_id and proof_bundle_claim_type:
                bundle_key = f"{proof_bundle_claim_type}:{element_id}"
            elif element_temporal_proof_bundle_id:
                bundle_key = element_temporal_proof_bundle_id
            else:
                bundle_key = ""
            if bundle_key:
                persisted_bundle = deepcopy(temporal_proof_bundle)
                if not isinstance(persisted_bundle, dict):
                    persisted_bundle = {}
                persisted_bundle.setdefault("proof_bundle_id", element_temporal_proof_bundle_id)
                persisted_bundle.setdefault("status", element_temporal_proof_bundle_status)
                persisted_bundle.setdefault("rule_frame_id", element_temporal_rule_frame_id)
                persisted_bundle["fact_ids"] = list(
                    persisted_bundle.get("fact_ids")
                    or persisted_bundle.get("temporal_fact_ids")
                    or element_temporal_proof_bundle_fact_ids
                )
                persisted_bundle["relation_ids"] = list(
                    persisted_bundle.get("relation_ids")
                    or persisted_bundle.get("temporal_relation_ids")
                    or element_temporal_proof_bundle_relation_ids
                )
                persisted_bundle["issue_ids"] = list(
                    persisted_bundle.get("issue_ids")
                    or persisted_bundle.get("temporal_issue_ids")
                    or element_temporal_proof_bundle_issue_ids
                )
                persisted_bundle["tdfol_preview"] = element_temporal_proof_bundle_tdfol_preview
                persisted_bundle["dcec_preview"] = element_temporal_proof_bundle_dcec_preview
                persisted_bundle.setdefault("theorem_export_metadata", element_theorem_export_metadata)
                persisted_bundle.setdefault("blocking_reasons", element_temporal_rule_blocking_reasons)
                persisted_bundle.setdefault("warnings", element_temporal_rule_warnings)
                persisted_bundle.setdefault("recommended_follow_ups", element_temporal_rule_follow_ups)
                proof_bundles[bundle_key] = persisted_bundle
        if bool(element_theorem_export_metadata.get("chronology_blocked", False)):
            theorem_export_blocked_element_count += 1
        theorem_export_chronology_task_count += int(
            element_theorem_export_metadata.get("chronology_task_count", 0) or 0
        )
        if proof_artifact:
            proof_artifact_element_count += 1
            proof_artifact_status_counts[element_proof_artifact_status or "unknown"] = (
                proof_artifact_status_counts.get(element_proof_artifact_status or "unknown", 0)
                + 1
            )
        if element_proof_artifact_available:
            proof_artifact_available_element_count += 1
        if element_proof_artifact_explanation_steps or element_proof_artifact_explanation_text:
            proof_artifact_explanation_element_count += 1
        for preview_value in (
            element_proof_artifact_proof_id,
            element_proof_artifact_sentence,
            element_proof_artifact_reason,
        ):
            if preview_value and preview_value not in proof_artifact_preview:
                proof_artifact_preview.append(preview_value)
            if len(proof_artifact_preview) >= preview_limit:
                break
        for warning in element_temporal_warnings:
            if warning not in temporal_warning_preview:
                temporal_warning_preview.append(warning)
            if len(temporal_warning_preview) >= preview_limit:
                break
        for relation_preview in element_temporal_relation_preview:
            if relation_preview not in temporal_relation_preview:
                temporal_relation_preview.append(relation_preview)
            if len(temporal_relation_preview) >= preview_limit:
                break
        for relation_type, count in element_temporal_relation_type_counts.items():
            temporal_relation_type_counts[relation_type] = (
                temporal_relation_type_counts.get(relation_type, 0) + int(count or 0)
            )
        if element_formalism and not hybrid_formalism:
            hybrid_formalism = element_formalism
        if element_reasoning_mode and not hybrid_reasoning_mode:
            hybrid_reasoning_mode = element_reasoning_mode
        if element_compiler_bridge_path and not hybrid_compiler_bridge_path:
            hybrid_compiler_bridge_path = element_compiler_bridge_path
        for formula in hybrid_tdfol_formulas:
            if formula not in hybrid_tdfol_formula_preview:
                hybrid_tdfol_formula_preview.append(formula)
            if len(hybrid_tdfol_formula_preview) >= preview_limit:
                break
        for formula in hybrid_dcec_formulas:
            if formula not in hybrid_dcec_formula_preview:
                hybrid_dcec_formula_preview.append(formula)
            if len(hybrid_dcec_formula_preview) >= preview_limit:
                break

        if not (
            used_fallback_ontology
            or unavailable_adapters
            or degraded_adapters
            or str(element.get("validation_status") or "") == "contradicted"
            or hybrid_bridge_used
            or proof_artifact
            or element_temporal_fact_count
            or element_temporal_relation_count
            or element_temporal_issue_count
            or element_temporal_warning_count
            or element_temporal_rule_status in {"partial", "failed"}
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
                "hybrid_bridge_used": hybrid_bridge_used,
                "hybrid_bridge_available": hybrid_bridge_available,
                "hybrid_tdfol_formula_count": hybrid_tdfol_count,
                "hybrid_dcec_formula_count": hybrid_dcec_count,
                "hybrid_tdfol_formula_preview": element_tdfol_preview,
                "hybrid_dcec_formula_preview": element_dcec_preview,
                "hybrid_formalism": element_formalism,
                "hybrid_reasoning_mode": element_reasoning_mode,
                "hybrid_compiler_bridge_path": element_compiler_bridge_path,
                "proof_artifact_available": element_proof_artifact_available,
                "proof_artifact_status": element_proof_artifact_status,
                "proof_artifact_proof_id": element_proof_artifact_proof_id,
                "proof_artifact_proof_status": element_proof_artifact_proof_status,
                "proof_artifact_sentence": element_proof_artifact_sentence,
                "proof_artifact_reason": element_proof_artifact_reason,
                "proof_artifact_violation_count": element_proof_artifact_violation_count,
                "proof_artifact_explanation_format": element_proof_artifact_explanation_format,
                "proof_artifact_explanation_step_count": len(element_proof_artifact_explanation_steps),
                "proof_artifact_explanation_text": element_proof_artifact_explanation_text,
                "proof_artifact_theorem_export_metadata": element_proof_artifact_theorem_export_metadata,
                "temporal_fact_count": element_temporal_fact_count,
                "temporal_relation_count": element_temporal_relation_count,
                "temporal_issue_count": element_temporal_issue_count,
                "temporal_partial_order_ready": element_temporal_partial_order_ready,
                "temporal_warning_count": element_temporal_warning_count,
                "temporal_warnings": element_temporal_warnings,
                "temporal_relation_type_counts": element_temporal_relation_type_counts,
                "temporal_relation_preview": element_temporal_relation_preview,
                "temporal_rule_profile_id": element_temporal_rule_profile_id,
                "temporal_rule_frame_id": element_temporal_rule_frame_id,
                "temporal_rule_status": element_temporal_rule_status,
                "temporal_rule_blocking_reasons": element_temporal_rule_blocking_reasons,
                "temporal_rule_warnings": element_temporal_rule_warnings,
                "temporal_rule_follow_ups": element_temporal_rule_follow_ups,
                "temporal_proof_bundle_id": element_temporal_proof_bundle_id,
                "temporal_proof_bundle_status": element_temporal_proof_bundle_status,
                "temporal_proof_bundle_fact_ids": element_temporal_proof_bundle_fact_ids,
                "temporal_proof_bundle_relation_ids": element_temporal_proof_bundle_relation_ids,
                "temporal_proof_bundle_issue_ids": element_temporal_proof_bundle_issue_ids,
                "temporal_proof_bundle_tdfol_preview": element_temporal_proof_bundle_tdfol_preview,
                "temporal_proof_bundle_dcec_preview": element_temporal_proof_bundle_dcec_preview,
                "theorem_export_metadata": element_theorem_export_metadata,
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
        "hybrid_bridge_element_count": hybrid_bridge_element_count,
        "hybrid_bridge_available_element_count": hybrid_bridge_available_element_count,
        "hybrid_tdfol_formula_count": hybrid_tdfol_formula_count,
        "hybrid_dcec_formula_count": hybrid_dcec_formula_count,
        "hybrid_tdfol_formula_preview": hybrid_tdfol_formula_preview,
        "hybrid_dcec_formula_preview": hybrid_dcec_formula_preview,
        "hybrid_formalism": hybrid_formalism,
        "hybrid_reasoning_mode": hybrid_reasoning_mode,
        "hybrid_compiler_bridge_path": hybrid_compiler_bridge_path,
        "temporal_element_count": temporal_element_count,
        "temporal_fact_count": temporal_fact_count,
        "temporal_relation_count": temporal_relation_count,
        "temporal_issue_count": temporal_issue_count,
        "temporal_partial_order_ready_element_count": temporal_partial_order_ready_element_count,
        "temporal_warning_count": temporal_warning_count,
        "temporal_warning_preview": temporal_warning_preview,
        "temporal_relation_type_counts": temporal_relation_type_counts,
        "temporal_relation_preview": temporal_relation_preview,
        "temporal_rule_profile_available_element_count": temporal_rule_profile_available_element_count,
        "temporal_rule_profile_satisfied_element_count": temporal_rule_profile_satisfied_element_count,
        "temporal_rule_profile_partial_element_count": temporal_rule_profile_partial_element_count,
        "temporal_rule_profile_failed_element_count": temporal_rule_profile_failed_element_count,
        "temporal_proof_bundle_count": temporal_proof_bundle_count,
        "temporal_proof_bundle_status_counts": temporal_proof_bundle_status_counts,
        # T3: proof_bundles indexed by "claim_type:element_id" for direct drilldown.
        "proof_bundles": proof_bundles,
        # T4: aggregated, deduplicated, ranked follow-ups from all temporal proof bundles
        # so review surfaces can surface actionable next steps without scanning bundles manually.
        "timeline_gap_follow_ups": _aggregate_timeline_gap_follow_ups(proof_bundles),
        "claim_temporal_issue_count": claim_temporal_issue_count,
        "claim_unresolved_temporal_issue_count": claim_unresolved_temporal_issue_count,
        "claim_resolved_temporal_issue_count": claim_resolved_temporal_issue_count,
        "claim_temporal_issue_status_counts": claim_temporal_issue_status_counts,
        "claim_temporal_issue_ids": claim_temporal_issue_ids,
        "claim_missing_temporal_predicates": claim_missing_temporal_predicates,
        "claim_required_provenance_kinds": claim_required_provenance_kinds,
        "theorem_export_blocked_element_count": theorem_export_blocked_element_count,
        "theorem_export_chronology_task_count": theorem_export_chronology_task_count,
        "proof_artifact_element_count": proof_artifact_element_count,
        "proof_artifact_available_element_count": proof_artifact_available_element_count,
        "proof_artifact_status_counts": proof_artifact_status_counts,
        "proof_artifact_explanation_element_count": proof_artifact_explanation_element_count,
        "proof_artifact_preview": proof_artifact_preview,
        "flagged_elements": flagged_elements,
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
    coverage_matrix_snapshots: Dict[str, Any] = {}
    get_coverage_matrix_snapshots = getattr(
        mediator,
        "get_claim_coverage_matrix_snapshots",
        None,
    )
    if callable(get_coverage_matrix_snapshots):
        candidate_coverage_snapshots = get_coverage_matrix_snapshots(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            required_support_kinds=required_support_kinds,
        )
        if isinstance(candidate_coverage_snapshots, dict):
            coverage_matrix_snapshots = candidate_coverage_snapshots
    snapshot_claims = (
        diagnostic_snapshots.get("claims", {})
        if isinstance(diagnostic_snapshots, dict)
        else {}
    )
    coverage_snapshot_claims = (
        coverage_matrix_snapshots.get("claims", {})
        if isinstance(coverage_matrix_snapshots.get("claims"), dict)
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
    formal_validation_report: Dict[str, Any] = {}
    get_formal_validation_report = getattr(mediator, "get_formal_validation_report", None)
    if callable(get_formal_validation_report):
        candidate_formal_report = get_formal_validation_report(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            required_support_kinds=required_support_kinds,
        )
        if isinstance(candidate_formal_report, dict):
            formal_validation_report = candidate_formal_report

    testimony_payload: Dict[str, Any] = {}
    get_claim_testimony_records = getattr(mediator, "get_claim_testimony_records", None)
    if callable(get_claim_testimony_records):
        candidate_payload = get_claim_testimony_records(
            claim_type=request.claim_type,
            user_id=resolved_user_id,
            limit=25,
        )
        if isinstance(candidate_payload, dict):
            testimony_payload = candidate_payload
    testimony_claims = testimony_payload.get("claims", {}) if isinstance(testimony_payload, dict) else {}
    testimony_summary = testimony_payload.get("summary", {}) if isinstance(testimony_payload, dict) else {}
    document_claims = _collect_claim_document_records(
        mediator,
        resolved_user_id,
        request.claim_type,
        limit=25,
        preview_chunk_limit=3,
    )

    for claim_name, claim_matrix in coverage_claims.items():
        if isinstance(claim_matrix, dict):
            _attach_testimony_to_claim_matrix(
                claim_matrix,
                testimony_claims.get(claim_name, []),
            )
            _attach_documents_to_claim_matrix(
                claim_matrix,
                document_claims.get(claim_name, []),
            )
            _attach_validation_to_claim_matrix(
                mediator,
                resolved_user_id,
                claim_name,
                claim_matrix,
                validation_claims.get(claim_name, {}),
                document_claims.get(claim_name, []),
            )

    coverage_summary = {
        claim_name: _summarize_claim_coverage_claim(
            claim_name,
            claim_matrix,
            overview_claims.get(claim_name, {}),
            gap_claims.get(claim_name, {}),
            contradiction_claims.get(claim_name, {}),
            validation_claims.get(claim_name, {}),
            (formal_validation_report.get("claims", {}) or {}).get(claim_name, {})
            if isinstance(formal_validation_report.get("claims"), dict)
            else {},
        )
        for claim_name, claim_matrix in coverage_claims.items()
        if isinstance(claim_matrix, dict)
    }
    for claim_name, summary in coverage_summary.items():
        if not isinstance(summary, dict):
            continue
        claim_testimony_summary = testimony_summary.get(claim_name, {}) if isinstance(testimony_summary, dict) else {}
        summary["testimony_record_count"] = int(claim_testimony_summary.get("record_count", 0) or 0)
        summary["testimony_linked_element_count"] = int(claim_testimony_summary.get("linked_element_count", 0) or 0)
        summary["testimony_firsthand_status_counts"] = dict(
            claim_testimony_summary.get("firsthand_status_counts", {}) or {}
        )
        claim_document_summary = summarize_claim_document_artifacts_claim(
            document_claims.get(claim_name, [])
        )
        summary["document_record_count"] = int(claim_document_summary.get("record_count", 0) or 0)
        summary["document_linked_element_count"] = int(claim_document_summary.get("linked_element_count", 0) or 0)
        summary["document_total_chunk_count"] = int(claim_document_summary.get("total_chunk_count", 0) or 0)
        summary["document_total_fact_count"] = int(claim_document_summary.get("total_fact_count", 0) or 0)
        summary["document_low_quality_record_count"] = int(claim_document_summary.get("low_quality_record_count", 0) or 0)
        summary["document_graph_ready_record_count"] = int(
            claim_document_summary.get("graph_ready_record_count", 0) or 0
        )

    intake_status = build_intake_status_summary(mediator, include_iteration_count=True)
    intake_case_summary = build_intake_case_review_summary(mediator)
    intake_contradiction_summary = summarize_intake_contradictions(
        intake_status.get("contradictions")
    )
    workflow_phase_plan = _build_review_workflow_phase_plan(
        mediator,
        intake_status=intake_status,
        intake_case_summary=intake_case_summary,
    )
    workflow_phase_priority = _build_review_workflow_phase_priority(workflow_phase_plan)
    workflow_priority = _build_review_workflow_priority(
        intake_status=intake_status,
        intake_case_summary=intake_case_summary,
        workflow_phase_priority=workflow_phase_priority,
    )
    handoff_metadata = _build_confirmed_intake_summary_handoff_metadata(mediator)
    document_focus_preview = _get_formalization_document_focus_preview(mediator)
    heavy_processing_queue = _build_heavy_processing_queue_state(
        mediator,
        resolved_user_id,
        request.claim_type,
    )
    coverage_snapshot_entries = {
        claim_name: claim_snapshot
        for claim_name, claim_snapshot in coverage_snapshot_claims.items()
        if isinstance(claim_snapshot, dict)
    }
    coverage_snapshot_lifecycle = {}
    for claim_name in coverage_claims.keys():
        snapshot = (
            (coverage_snapshot_entries.get(claim_name, {}) or {}).get("snapshot", {})
        )
        coverage_snapshot_lifecycle[claim_name] = summarize_claim_support_snapshot_lifecycle(
            {"coverage_matrix": snapshot}
            if isinstance(snapshot, dict) and snapshot
            else {}
        )

    question_recommendations = {
        claim_name: _build_claim_question_recommendations(
            claim_name,
            gap_claims.get(claim_name, {}),
            contradiction_claims.get(claim_name, {}),
            coverage_claims.get(claim_name, {}),
        )
        for claim_name in coverage_claims.keys()
    }

    payload: Dict[str, Any] = {
        "user_id": resolved_user_id,
        "claim_type": request.claim_type,
        "required_support_kinds": required_support_kinds,
        "intake_status": intake_status,
        "intake_case_summary": intake_case_summary,
        "workflow_targeting_summary": (
            dict(intake_case_summary.get("workflow_targeting_summary") or {})
            if isinstance(intake_case_summary.get("workflow_targeting_summary"), dict)
            else {}
        ),
        "document_workflow_execution_summary": (
            dict(intake_case_summary.get("document_workflow_execution_summary") or {})
            if isinstance(intake_case_summary.get("document_workflow_execution_summary"), dict)
            else {}
        ),
        "document_grounding_improvement_summary": (
            dict(intake_case_summary.get("document_grounding_improvement_summary") or {})
            if isinstance(intake_case_summary.get("document_grounding_improvement_summary"), dict)
            else {}
        ),
        "document_grounding_lane_outcome_summary": (
            dict(intake_case_summary.get("document_grounding_lane_outcome_summary") or {})
            if isinstance(intake_case_summary.get("document_grounding_lane_outcome_summary"), dict)
            else {}
        ),
        "document_grounding_improvement_next_action": (
            dict(intake_case_summary.get("document_grounding_improvement_next_action") or {})
            if isinstance(intake_case_summary.get("document_grounding_improvement_next_action"), dict)
            else {}
        ),
        "document_drafting_next_action": (
            dict(intake_case_summary.get("document_drafting_next_action") or {})
            if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
            else {}
        ),
        "heavy_processing_queue": heavy_processing_queue,
        "document_focus_preview": document_focus_preview,
        "recommended_next_action": (
            str((intake_status.get("next_action") or {}).get("action") or "")
            if isinstance(intake_status.get("next_action"), dict)
            else ""
        ),
        "workflow_phase_plan": workflow_phase_plan,
        "workflow_phase_priority": workflow_phase_priority,
        "workflow_priority": workflow_priority,
        "primary_validation_target": (
            dict(intake_status.get("primary_validation_target"))
            if isinstance(intake_status.get("primary_validation_target"), dict)
            else {}
        ),
        "intake_contradiction_summary": intake_contradiction_summary,
        "claim_coverage_matrix": coverage_claims,
        "claim_coverage_matrix_snapshots": coverage_snapshot_entries,
        "claim_coverage_matrix_snapshot_summary": coverage_snapshot_lifecycle,
        "claim_coverage_summary": coverage_summary,
        "claim_support_gaps": gap_claims,
        "claim_contradiction_candidates": contradiction_claims,
        "claim_support_validation": validation_claims,
        "formal_validation_report": formal_validation_report,
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
            claim_name: _merge_claim_temporal_registry_into_reasoning_review(
                summarize_claim_reasoning_review(
                    validation_claims.get(claim_name, {})
                ),
                intake_case_summary=intake_case_summary,
                claim_type=claim_name,
            )
            for claim_name in coverage_claims.keys()
        },
        "question_recommendations": question_recommendations,
        "question_recommendation_summary": {
            claim_name: _summarize_question_recommendations(recommendations)
            for claim_name, recommendations in question_recommendations.items()
        },
        "testimony_records": testimony_claims,
        "testimony_summary": {
            claim_name: summarize_claim_testimony_claim(
                testimony_claims.get(claim_name, [])
            )
            for claim_name in coverage_claims.keys()
        },
        "document_artifacts": document_claims,
        "document_summary": {
            claim_name: summarize_claim_document_artifacts_claim(
                document_claims.get(claim_name, [])
            )
            for claim_name in coverage_claims.keys()
        },
    }

    recent_follow_up_history = mediator.get_recent_claim_follow_up_execution(
        claim_type=request.claim_type,
        user_id=resolved_user_id,
        limit=10,
    )
    recent_follow_up_claims = (
        recent_follow_up_history.get("claims", {})
        if isinstance(recent_follow_up_history, dict)
        else {}
    )
    payload["follow_up_history"] = recent_follow_up_claims
    payload["follow_up_history_summary"] = {
        claim_name: summarize_follow_up_history_claim(
            recent_follow_up_claims.get(claim_name, [])
        )
        for claim_name in coverage_claims.keys()
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

    if handoff_metadata:
        payload.update(handoff_metadata)

    return payload


_bind_owner_namespace()
