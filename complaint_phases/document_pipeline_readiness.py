"""Drafting readiness and intake questioning guidance for the document pipeline.

These functions keep the original method bodies. Helpers that still live on the
document-pipeline owner are resolved when a function runs, after both modules
have finished loading.
"""

from __future__ import annotations

def _build_intake_questioning_phase_guidance(
    self,
    *,
    drafting_readiness: Dict[str, Any],
    document_optimization: Dict[str, Any],
) -> Dict[str, Any]:
    from complaint_phases import document_pipeline as _owner
    Dict = _owner.Dict
    _dedupe_text_values = _owner._dedupe_text_values
    _safe_float = _owner._safe_float
    Any = _owner.Any
    build_intake_status_summary = _owner.build_intake_status_summary
    DEFAULT_ACTOR_CRITIC_PRIORITY_METRICS = _owner.DEFAULT_ACTOR_CRITIC_PRIORITY_METRICS
    optimization_report = document_optimization if isinstance(document_optimization, dict) else {}
    actor_critic_guidance = self._extract_actor_critic_guidance(optimization_report)
    actor_critic_metrics = dict(actor_critic_guidance.get("metrics") or {}) if actor_critic_guidance else {}
    blocker_signals = self._extract_blocker_follow_up_signals(optimization_report)
    needs_chronology_closure = bool(actor_critic_guidance.get("needs_chronology_closure")) or bool(
        blocker_signals.get("needs_causation_follow_up")
    )
    needs_decision_document_precision = bool(actor_critic_guidance.get("needs_decision_document_precision")) or bool(
        blocker_signals.get("needs_decision_maker_follow_up")
    ) or bool(blocker_signals.get("needs_document_anchor_follow_up"))
    intake_status = (
        optimization_report.get("intake_status")
        if isinstance(optimization_report.get("intake_status"), dict)
        else build_intake_status_summary(self.mediator)
    )
    intake_handoff = (
        intake_status.get("intake_summary_handoff")
        if isinstance(intake_status.get("intake_summary_handoff"), dict)
        else {}
    )
    confirmation = (
        intake_handoff.get("complainant_summary_confirmation")
        if isinstance(intake_handoff.get("complainant_summary_confirmation"), dict)
        else {}
    )
    confirmation_snapshot = (
        confirmation.get("confirmed_summary_snapshot")
        if isinstance(confirmation.get("confirmed_summary_snapshot"), dict)
        else {}
    )
    intake_priority_summary = (
        confirmation_snapshot.get("adversarial_intake_priority_summary")
        if isinstance(confirmation_snapshot.get("adversarial_intake_priority_summary"), dict)
        else {}
    )
    objective_aliases = {
        "staff_names": "staff_names_titles",
        "staff_titles": "staff_names_titles",
        "hearing_timing": "hearing_request_timing",
        "response_timing": "response_dates",
        "causation": "causation_link",
        "adverse_action": "anchor_adverse_action",
        "appeal_rights": "anchor_appeal_rights",
    }

    def _normalize_objective(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        return objective_aliases.get(text, text)

    uncovered_objectives = _dedupe_text_values(
        _normalize_objective(item)
        for item in (intake_priority_summary.get("uncovered_objectives") or [])
        if _normalize_objective(item)
    )
    objective_question_counts = {
        _normalize_objective(key): int(value or 0)
        for key, value in dict(intake_priority_summary.get("objective_question_counts") or {}).items()
        if _normalize_objective(key)
    }
    required_objectives = (
        "timeline",
        "actors",
        "staff_names_titles",
        "causation_link",
        "anchor_adverse_action",
        "anchor_appeal_rights",
        "hearing_request_timing",
        "response_dates",
    )
    missing_required = [
        objective
        for objective in required_objectives
        if objective in uncovered_objectives or int(objective_question_counts.get(objective, 0)) <= 0
    ]
    objective_actions = {
        "timeline": "Capture exact dates for complaint activity, notices, hearing/review requests, and adverse action outcomes.",
        "actors": "Identify who at HACC made, communicated, and carried out each key decision.",
        "staff_names_titles": "Capture each HACC staff member name and title, or best-known title when name is unknown.",
        "causation_link": "Document direct causation facts linking protected activity to adverse action.",
        "anchor_adverse_action": "Confirm the exact denial, termination, or threatened loss of assistance and its communication date.",
        "anchor_appeal_rights": "Confirm whether written notice, informal review, grievance hearing, and appeal rights were provided, requested, denied, or ignored.",
        "hearing_request_timing": "Capture when hearing/review was requested and whether the request timing was acknowledged.",
        "response_dates": "Capture exact response dates for HACC notices, hearing/review responses, and final decision outcomes.",
    }
    if missing_required:
        status = "warning"
        summary = (
            "Intake questioning still needs closure on key blockers (exact dates, staff names/titles, hearing request timing, response dates, "
            "and causation links between protected activity and adverse treatment)."
        )
        actions = _dedupe_text_values(
            objective_actions.get(objective, "")
            for objective in missing_required
            if objective_actions.get(objective, "")
        )
    else:
        status = "ready"
        summary = (
            "Intake questioning currently includes timeline anchors, staff identification, hearing/response timing, and causation probes."
        )
        actions = []

    empathy_score = _safe_float(actor_critic_metrics.get("empathy"), DEFAULT_ACTOR_CRITIC_PRIORITY_METRICS["empathy"])
    question_quality_score = _safe_float(actor_critic_metrics.get("question_quality"), DEFAULT_ACTOR_CRITIC_PRIORITY_METRICS["question_quality"])
    information_extraction_score = _safe_float(actor_critic_metrics.get("information_extraction"), DEFAULT_ACTOR_CRITIC_PRIORITY_METRICS["information_extraction"])
    coverage_score = _safe_float(actor_critic_metrics.get("coverage"), DEFAULT_ACTOR_CRITIC_PRIORITY_METRICS["coverage"])
    efficiency_score = _safe_float(actor_critic_metrics.get("efficiency"), DEFAULT_ACTOR_CRITIC_PRIORITY_METRICS["efficiency"])
    router_backed_question_quality = bool(actor_critic_guidance.get("router_backed_question_quality")) if actor_critic_guidance else False

    if empathy_score < 0.5:
        actions.append(
            "Lead each intake follow-up with a short empathy frame before asking for chronology or decision details."
        )
        actions.append(
            "Use an empathy-forward transition format ('I hear the impact this had. To keep your record accurate...') before requesting exact dates or staff identifiers."
        )
    if question_quality_score < 0.7:
        actions.append(
            "Upgrade question quality by asking one targeted objective per question with explicit date, actor/title, and decision-anchor prompts."
        )
        actions.append(
            "Require each follow-up question to include one objective tag plus a concrete answer target (date, actor/title, notice/response event, or quoted decision language)."
        )
    if information_extraction_score < 0.7:
        actions.append(
            "Improve information extraction by capturing exact event sequence, communication channel, and quoted decision language where available."
        )
    if coverage_score < 0.7:
        actions.append(
            "Increase coverage by ensuring every required objective has at least one answered question and no zero-count objective remains."
        )
    if efficiency_score < 0.75:
        actions.append(
            "Improve intake efficiency by removing multi-part questions and collapsing duplicates to the shortest sufficient prompt."
        )
    if router_backed_question_quality:
        actions.append(
            "Use router-backed question generation to refine prompts for specificity while preserving patchability and objective coverage."
        )
        if question_quality_score < 0.75:
            actions.append(
                "Route low-quality follow-ups through the llm router with an objective-specific schema so each prompt asks for one verifiable fact and one temporal anchor."
            )
        if information_extraction_score < 0.75:
            actions.append(
                "Use router-backed extraction checks to normalize each answer into date, actor/title, event, and source fields before drafting updates."
            )
    if needs_chronology_closure:
        actions.append(
            "Close chronology gaps with follow-up questions that require exact dates, elapsed response timing, and event sequence ordering before drafting updates."
        )
        if router_backed_question_quality:
            actions.append(
                "Use router-backed single-objective prompts to ask one chronology gap at a time (event date, response date, or sequence delta) and reject answers without explicit date anchors."
            )
    if needs_decision_document_precision:
        actions.append(
            "Ask decision-precision follow-ups that capture who made each adverse decision, their title, the exact decision communicated, and the document or notice that records it."
        )
        if router_backed_question_quality:
            actions.append(
                "Use router-backed extraction checks to normalize adverse-action answers into decision-maker, decision detail, communication channel, document artifact, and date fields."
            )
    actions.append(
        "Keep follow-up prompts patchable by using short, single-objective question templates that can be edited independently without changing global intake flow."
    )
    actions = _dedupe_text_values(actions)
    if actions and status == "ready":
        status = "warning"
    if actions and actor_critic_guidance:
        summary = (
            f"{summary} Actor-critic optimization highlights low empathy/question quality/extraction/coverage/efficiency signals that should be addressed before final drafting."
        ).strip()

    return {
        "priority": 2,
        "status": status,
        "summary": summary,
        "signals": {
            "uncovered_objectives": uncovered_objectives,
            "objective_question_counts": objective_question_counts,
            "missing_required_objectives": missing_required,
            "drafting_status": str(drafting_readiness.get("status") or ""),
            "actor_critic_priority": int(actor_critic_guidance.get("priority") or 70) if actor_critic_guidance else None,
            "actor_critic_metrics": actor_critic_metrics if actor_critic_guidance else {},
            "router_backed_question_quality": router_backed_question_quality,
            "blocker_follow_up_signals": blocker_signals,
            "needs_chronology_closure": needs_chronology_closure,
            "needs_decision_document_precision": needs_decision_document_precision,
            "priority_findings": list(actor_critic_guidance.get("priority_findings") or []) if actor_critic_guidance else [],
        },
        "recommended_actions": actions,
    }


def _build_drafting_readiness(
    self,
    *,
    user_id: str,
    draft: Dict[str, Any],
) -> Dict[str, Any]:
    from complaint_phases import document_pipeline as _owner
    Dict = _owner.Dict
    _unique_preserving_order = _owner._unique_preserving_order
    List = _owner.List
    _coerce_list = _owner._coerce_list
    _safe_float = _owner._safe_float
    build_intake_status_summary = _owner.build_intake_status_summary
    _dedupe_text_values = _owner._dedupe_text_values
    _build_runtime_workflow_optimization_guidance = _owner._build_runtime_workflow_optimization_guidance
    _build_workflow_optimization_warning_entries = _owner._build_workflow_optimization_warning_entries
    Any = _owner.Any
    _extract_text_candidates = _owner._extract_text_candidates
    _build_claim_checklist_chip_labels = _owner._build_claim_checklist_chip_labels
    _merge_status = _owner._merge_status
    _coerce_bool = _owner._coerce_bool
    summarize_claim_reasoning_review = _owner.summarize_claim_reasoning_review
    re = _owner.re
    support_summary = self._safe_mediator_dict("summarize_claim_support", user_id=user_id)
    gap_summary = self._safe_mediator_dict("get_claim_support_gaps", user_id=user_id)
    validation_summary = self._safe_mediator_dict("get_claim_support_validation", user_id=user_id)
    drafting_guardrails = self._safe_mediator_dict(
        "get_drafting_guardrails",
        user_id=user_id,
        required_support_kinds=["evidence", "authority"],
    )

    support_claims = support_summary.get("claims", {}) if isinstance(support_summary.get("claims"), dict) else {}
    gap_claims = gap_summary.get("claims", {}) if isinstance(gap_summary.get("claims"), dict) else {}
    validation_claims = validation_summary.get("claims", {}) if isinstance(validation_summary.get("claims"), dict) else {}

    claim_types = _unique_preserving_order(
        _extract_text_candidates((draft.get("source_context") or {}).get("claim_types"))
        + list(support_claims.keys())
        + list(validation_claims.keys())
        + [
            str(claim.get("claim_type") or "").strip()
            for claim in _coerce_list(draft.get("claims_for_relief"))
            if isinstance(claim, dict)
        ]
    )

    claim_readiness: List[Dict[str, Any]] = []
    aggregate_warning_count = 0
    overall_status = "ready"
    draft_claims_by_type = {
        str(claim.get("claim_type") or "").strip(): claim
        for claim in _coerce_list(draft.get("claims_for_relief"))
        if isinstance(claim, dict) and str(claim.get("claim_type") or "").strip()
    }

    for claim_type in claim_types:
        support_claim = support_claims.get(claim_type, {}) if isinstance(support_claims.get(claim_type), dict) else {}
        gap_claim = gap_claims.get(claim_type, {}) if isinstance(gap_claims.get(claim_type), dict) else {}
        validation_claim = validation_claims.get(claim_type, {}) if isinstance(validation_claims.get(claim_type), dict) else {}
        if not isinstance(validation_claim, dict) or not validation_claim:
            claim_validation_payload = self._safe_mediator_dict(
                "get_claim_support_validation",
                claim_type=claim_type,
                user_id=user_id,
            )
            claim_validation_claims = (
                claim_validation_payload.get("claims", {})
                if isinstance(claim_validation_payload.get("claims"), dict)
                else {}
            )
            validation_claim = (
                claim_validation_claims.get(claim_type, {})
                if isinstance(claim_validation_claims.get(claim_type), dict)
                else {}
            )
        draft_claim = draft_claims_by_type.get(claim_type, {}) if isinstance(draft_claims_by_type.get(claim_type), dict) else {}
        overview_payload = self._safe_mediator_dict(
            "get_claim_overview",
            claim_type=claim_type,
            user_id=user_id,
            required_support_kinds=["evidence", "authority"],
        )
        overview_claim = overview_payload.get("claims", {}).get(claim_type, {}) if isinstance(overview_payload.get("claims"), dict) else {}
        treatment_summary = support_claim.get("authority_treatment_summary", {}) if isinstance(support_claim.get("authority_treatment_summary"), dict) else {}
        rule_summary = support_claim.get("authority_rule_candidate_summary", {}) if isinstance(support_claim.get("authority_rule_candidate_summary"), dict) else {}
        source_context = self._extract_support_source_context_counts(support_claim)
        claim_reasoning_summary = summarize_claim_reasoning_review(validation_claim) if validation_claim else {}
        claim_temporal_issue_count = int(claim_reasoning_summary.get("claim_temporal_issue_count", 0) or 0)
        claim_unresolved_temporal_issue_count = int(
            claim_reasoning_summary.get("claim_unresolved_temporal_issue_count", 0) or 0
        )
        claim_resolved_temporal_issue_count = int(
            claim_reasoning_summary.get("claim_resolved_temporal_issue_count", 0) or 0
        )
        claim_temporal_issue_ids = _extract_text_candidates(claim_reasoning_summary.get("claim_temporal_issue_ids"))
        claim_missing_temporal_predicates = _extract_text_candidates(
            claim_reasoning_summary.get("claim_missing_temporal_predicates")
        )
        claim_required_provenance_kinds = _extract_text_candidates(
            claim_reasoning_summary.get("claim_required_provenance_kinds")
        )

        claim_status = "ready"
        warnings: List[Dict[str, Any]] = []

        validation_status = str(validation_claim.get("validation_status") or "")
        if validation_status == "contradicted":
            claim_status = _merge_status(claim_status, "blocked")
            warnings.append(
                {
                    "code": "claim_contradicted",
                    "severity": "blocked",
                    "message": f"{claim_type.title()} has contradiction signals that should be resolved before filing.",
                }
            )
        elif validation_status in {"missing", "incomplete"}:
            claim_status = _merge_status(claim_status, "warning")

        if int(validation_claim.get("proof_gap_count", 0) or 0) > 0:
            claim_status = _merge_status(claim_status, "warning")
            warnings.append(
                {
                    "code": "proof_gaps_present",
                    "severity": "warning",
                    "message": f"{claim_type.title()} still has proof or failed-premise gaps.",
                }
            )

        temporal_gap_hint_count = int(
            (draft_claim.get("support_summary") or {}).get("temporal_gap_hint_count") or 0
        )
        if temporal_gap_hint_count <= 0:
            temporal_gap_hint_count = sum(
                1
                for item in _coerce_list(draft_claim.get("missing_elements"))
                if str(item or "").strip().lower().startswith("chronology gap")
            )
        temporal_gap_hint_count = max(
            temporal_gap_hint_count,
            claim_unresolved_temporal_issue_count,
            len(claim_missing_temporal_predicates),
        )
        if temporal_gap_hint_count > 0:
            claim_status = _merge_status(claim_status, "warning")
            warnings.append(
                {
                    "code": "chronology_gaps_present",
                    "severity": "warning",
                    "message": f"{claim_type.title()} still has {temporal_gap_hint_count} chronology gap(s) that should be resolved before filing.",
                }
            )

        if int(treatment_summary.get("adverse_authority_link_count", 0) or 0) > 0:
            claim_status = _merge_status(claim_status, "warning")
            warnings.append(
                {
                    "code": "adverse_authority_present",
                    "severity": "warning",
                    "message": f"{claim_type.title()} includes adverse or limiting authority that should be reviewed before relying on it in the draft.",
                }
            )

        uncertain_authority_count = int(treatment_summary.get("uncertain_authority_link_count", 0) or 0)
        uncertain_treatment_types = sorted(
            str(name)
            for name in (treatment_summary.get("treatment_type_counts", {}) or {}).keys()
            if str(name) in {"questioned", "limits", "superseded", "good_law_unconfirmed"}
        )
        if uncertain_authority_count > 0 or uncertain_treatment_types:
            claim_status = _merge_status(claim_status, "warning")
            warnings.append(
                {
                    "code": "authority_reliability_uncertain",
                    "severity": "warning",
                    "message": f"{claim_type.title()} has authority support with unresolved treatment or good-law uncertainty.",
                }
            )

        unresolved_elements = int(gap_claim.get("unresolved_count", 0) or 0)
        if unresolved_elements == 0:
            unresolved_elements = len(_coerce_list(overview_claim.get("missing"))) + len(_coerce_list(overview_claim.get("partially_supported")))
        if unresolved_elements > 0:
            claim_status = _merge_status(claim_status, "warning")
            warnings.append(
                {
                    "code": "unresolved_elements",
                    "severity": "warning",
                    "message": f"{claim_type.title()} still has {unresolved_elements} unresolved claim element(s).",
                }
            )

        claim_entry = {
            "claim_type": claim_type,
            "status": claim_status,
            "validation_status": validation_status or ("supported" if claim_status == "ready" else "incomplete"),
            "covered_elements": int(support_claim.get("covered_elements", 0) or 0),
            "total_elements": int(support_claim.get("total_elements", 0) or 0),
            "unresolved_element_count": unresolved_elements,
            "proof_gap_count": int(validation_claim.get("proof_gap_count", 0) or 0),
            "temporal_gap_hint_count": temporal_gap_hint_count,
            "contradiction_candidate_count": int(validation_claim.get("contradiction_candidate_count", 0) or 0),
            "claim_temporal_issue_count": claim_temporal_issue_count,
            "claim_unresolved_temporal_issue_count": claim_unresolved_temporal_issue_count,
            "claim_resolved_temporal_issue_count": claim_resolved_temporal_issue_count,
            "claim_temporal_issue_ids": claim_temporal_issue_ids,
            "claim_missing_temporal_predicates": claim_missing_temporal_predicates,
            "claim_required_provenance_kinds": claim_required_provenance_kinds,
            "support_by_kind": support_claim.get("support_by_kind", {}),
            "support_by_source": source_context["support_by_source"],
            "source_family_counts": source_context["source_family_counts"],
            "record_scope_counts": source_context["record_scope_counts"],
            "artifact_family_counts": source_context["artifact_family_counts"],
            "corpus_family_counts": source_context["corpus_family_counts"],
            "content_origin_counts": source_context["content_origin_counts"],
            "authority_treatment_summary": treatment_summary,
            "authority_rule_candidate_summary": rule_summary,
            "warnings": warnings,
        }
        claim_entry["chip_labels"] = _build_claim_checklist_chip_labels(claim_entry)
        aggregate_warning_count += len(warnings)
        overall_status = _merge_status(overall_status, claim_status)
        claim_readiness.append(claim_entry)

    claims_section_status = "ready"
    for claim_entry in claim_readiness:
        claims_section_status = _merge_status(claims_section_status, claim_entry.get("status", "ready"))

    total_fact_count = sum(int(claim.get("total_facts", 0) or 0) for claim in support_claims.values() if isinstance(claim, dict))
    if total_fact_count <= 0:
        total_fact_count = sum(
            len(self._normalize_text_lines(claim.get("supporting_facts", [])))
            for claim in _coerce_list(draft.get("claims_for_relief"))
            if isinstance(claim, dict)
        )
    summary_fact_count = len(self._normalize_text_lines(draft.get("summary_of_facts", [])))
    exhibits = _coerce_list(draft.get("exhibits"))
    relief_items = self._normalize_text_lines(draft.get("requested_relief", []))
    document_provenance_summary = (
        dict(draft.get("document_provenance_summary") or {})
        if isinstance(draft.get("document_provenance_summary"), dict)
        else {}
    )
    document_fact_backed_ratio = _safe_float(document_provenance_summary.get("fact_backed_ratio"), 0.0)
    document_low_grounding_flag = bool(document_provenance_summary.get("low_grounding_flag"))

    sections: Dict[str, Dict[str, Any]] = {}

    facts_status = "ready" if total_fact_count > 0 and summary_fact_count > 0 else "warning"
    facts_warnings: List[Dict[str, Any]] = []
    if facts_status != "ready":
        facts_warnings.append(
            {
                "code": "fact_support_thin",
                "severity": "warning",
                "message": "The factual allegations section has limited fact-backed support and should be reviewed before filing.",
            }
        )
    sections["summary_of_facts"] = {
        "title": "Summary of Facts",
        "status": facts_status,
        "metrics": {
            "summary_fact_count": summary_fact_count,
            "support_fact_count": total_fact_count,
            "document_fact_backed_ratio": round(document_fact_backed_ratio, 4),
        },
        "warnings": facts_warnings,
    }
    if document_low_grounding_flag:
        sections["summary_of_facts"]["status"] = _merge_status(
            str(sections["summary_of_facts"].get("status") or "ready"),
            "warning",
        )
        sections["summary_of_facts"].setdefault("warnings", []).append(
            {
                "code": "document_provenance_grounding_thin",
                "severity": "warning",
                "message": "The current draft is not grounded enough in canonical facts or artifact-backed support rows.",
            }
        )
        aggregate_warning_count += 1

    jurisdiction_status = "ready" if draft.get("jurisdiction_statement") and draft.get("venue_statement") else "warning"
    jurisdiction_warnings: List[Dict[str, Any]] = []
    procedural_rule_count = sum(
        int((entry.get("authority_rule_candidate_summary", {}).get("rule_type_counts", {}) or {}).get("procedural_prerequisite", 0) or 0)
        for entry in claim_readiness
        if isinstance(entry, dict)
    )
    if jurisdiction_status != "ready":
        jurisdiction_warnings.append(
            {
                "code": "jurisdiction_or_venue_incomplete",
                "severity": "warning",
                "message": "Jurisdiction or venue language is incomplete and should be confirmed before export.",
            }
        )
    if procedural_rule_count > 0:
        jurisdiction_status = _merge_status(jurisdiction_status, "warning")
        jurisdiction_warnings.append(
            {
                "code": "procedural_prerequisites_identified",
                "severity": "warning",
                "message": "Authority-derived procedural prerequisites were identified and should be checked against the current facts before filing.",
            }
        )
    sections["jurisdiction_and_venue"] = {
        "title": "Jurisdiction and Venue",
        "status": jurisdiction_status,
        "metrics": {
            "procedural_rule_count": procedural_rule_count,
        },
        "warnings": jurisdiction_warnings,
    }

    sections["claims_for_relief"] = {
        "title": "Claims for Relief",
        "status": claims_section_status,
        "metrics": {
            "claim_count": len(claim_readiness),
            "blocked_claim_count": len([entry for entry in claim_readiness if entry.get("status") == "blocked"]),
            "warning_claim_count": len([entry for entry in claim_readiness if entry.get("status") == "warning"]),
        },
        "warnings": [
            warning
            for entry in claim_readiness
            for warning in entry.get("warnings", [])
            if isinstance(warning, dict)
        ],
    }

    exhibits_status = "ready" if exhibits else "warning"
    exhibits_warnings: List[Dict[str, Any]] = []
    if not exhibits:
        exhibits_warnings.append(
            {
                "code": "no_exhibits",
                "severity": "warning",
                "message": "No exhibits are currently attached to the draft package.",
            }
        )
    sections["exhibits"] = {
        "title": "Exhibits",
        "status": exhibits_status,
        "metrics": {
            "exhibit_count": len(exhibits),
        },
        "warnings": exhibits_warnings,
    }

    relief_status = "ready" if relief_items else "warning"
    relief_warnings: List[Dict[str, Any]] = []
    if not relief_items:
        relief_warnings.append(
            {
                "code": "requested_relief_missing",
                "severity": "warning",
                "message": "Requested relief should be confirmed before filing.",
            }
        )
    sections["requested_relief"] = {
        "title": "Requested Relief",
        "status": relief_status,
        "metrics": {
            "requested_relief_count": len(relief_items),
        },
        "warnings": relief_warnings,
    }

    for section in sections.values():
        overall_status = _merge_status(overall_status, str(section.get("status") or "ready"))
        aggregate_warning_count += len(section.get("warnings", []) or [])

    graph_signals = self._build_graph_completeness_signals(getattr(self.mediator, "phase_manager", None))
    gap_signals = self._collect_unresolved_readiness_gaps(
        claim_readiness=claim_readiness,
        sections=sections,
        graph_signals=graph_signals,
    )
    intake_status = build_intake_status_summary(self.mediator)
    intake_handoff = (
        intake_status.get("intake_summary_handoff")
        if isinstance(intake_status, dict) and isinstance(intake_status.get("intake_summary_handoff"), dict)
        else {}
    )
    confirmation = (
        intake_handoff.get("complainant_summary_confirmation")
        if isinstance(intake_handoff.get("complainant_summary_confirmation"), dict)
        else {}
    )
    confirmation_snapshot = (
        confirmation.get("confirmed_summary_snapshot")
        if isinstance(confirmation.get("confirmed_summary_snapshot"), dict)
        else {}
    )
    intake_priority_summary = (
        confirmation_snapshot.get("adversarial_intake_priority_summary")
        if isinstance(confirmation_snapshot.get("adversarial_intake_priority_summary"), dict)
        else {}
    )
    objective_aliases = {
        "staff_names": "staff_names_titles",
        "staff_titles": "staff_names_titles",
        "hearing_timing": "hearing_request_timing",
        "response_timing": "response_dates",
        "causation": "causation_link",
        "adverse_action": "anchor_adverse_action",
        "appeal_rights": "anchor_appeal_rights",
    }

    def _normalize_objective(value: Any) -> str:
        objective_text = str(value or "").strip().lower()
        if not objective_text:
            return ""
        return objective_aliases.get(objective_text, objective_text)

    uncovered_intake_objectives = _dedupe_text_values(
        _normalize_objective(item)
        for item in list(intake_priority_summary.get("uncovered_objectives") or [])
        if _normalize_objective(item)
    )
    objective_question_counts = {
        _normalize_objective(key): int(value or 0)
        for key, value in dict(intake_priority_summary.get("objective_question_counts") or {}).items()
        if _normalize_objective(key)
    }
    required_intake_objectives = (
        "timeline",
        "actors",
        "staff_names_titles",
        "causation_link",
        "anchor_adverse_action",
        "anchor_appeal_rights",
        "hearing_request_timing",
        "response_dates",
    )
    missing_required_intake_objectives = [
        objective
        for objective in required_intake_objectives
        if objective in uncovered_intake_objectives or int(objective_question_counts.get(objective, 0)) <= 0
    ]

    summary_fact_lines = self._normalize_text_lines(draft.get("summary_of_facts", []))
    claim_support_lines = [
        line
        for claim in _coerce_list(draft.get("claims_for_relief"))
        if isinstance(claim, dict)
        for line in self._normalize_text_lines(claim.get("supporting_facts", []))
    ]

    def _has_date_anchor(text: str) -> bool:
        candidate = str(text or "").strip().lower()
        if not candidate:
            return False
        return bool(
            re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", candidate)
            or re.search(r"\b\d{4}-\d{2}-\d{2}\b", candidate)
            or re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", candidate)
        )

    def _has_actor_anchor(text: str) -> bool:
        candidate = str(text or "").strip().lower()
        if not candidate:
            return False
        return bool(
            re.search(r"\b(manager|director|coordinator|officer|supervisor|caseworker|staff|agent|representative|administrator)\b", candidate)
            or re.search(r"\b(hacc|housing authority)\b", candidate)
        )

    def _has_evidence_anchor(text: str) -> bool:
        candidate = str(text or "").strip().lower()
        if not candidate:
            return False
        return bool(
            re.search(r"\b(exhibit|policy|document|notice|letter|email|record|file|pdf|attachment|cid|http)\b", candidate)
        )

    summary_date_anchor_count = sum(1 for line in summary_fact_lines if _has_date_anchor(line))
    summary_actor_anchor_count = sum(1 for line in summary_fact_lines if _has_actor_anchor(line))
    summary_evidence_anchor_count = sum(1 for line in summary_fact_lines if _has_evidence_anchor(line))
    claim_support_date_anchor_count = sum(1 for line in claim_support_lines if _has_date_anchor(line))
    claim_support_actor_anchor_count = sum(1 for line in claim_support_lines if _has_actor_anchor(line))
    claim_support_evidence_anchor_count = sum(1 for line in claim_support_lines if _has_evidence_anchor(line))
    structured_handoff_gaps: List[str] = []
    if summary_fact_lines and summary_date_anchor_count <= 0:
        structured_handoff_gaps.append("summary_of_facts_missing_date_anchors")
    if summary_fact_lines and summary_actor_anchor_count <= 0:
        structured_handoff_gaps.append("summary_of_facts_missing_actor_anchors")
    if summary_fact_lines and summary_evidence_anchor_count <= 0:
        structured_handoff_gaps.append("summary_of_facts_missing_evidence_anchors")
    if claim_support_lines and claim_support_date_anchor_count <= 0:
        structured_handoff_gaps.append("claim_support_missing_date_anchors")
    if claim_support_lines and claim_support_actor_anchor_count <= 0:
        structured_handoff_gaps.append("claim_support_missing_actor_anchors")
    if claim_support_lines and claim_support_evidence_anchor_count <= 0:
        structured_handoff_gaps.append("claim_support_missing_evidence_anchors")
    structured_handoff_signals = {
        "summary_fact_count": len(summary_fact_lines),
        "claim_support_fact_count": len(claim_support_lines),
        "summary_date_anchor_count": int(summary_date_anchor_count),
        "summary_actor_anchor_count": int(summary_actor_anchor_count),
        "summary_evidence_anchor_count": int(summary_evidence_anchor_count),
        "claim_support_date_anchor_count": int(claim_support_date_anchor_count),
        "claim_support_actor_anchor_count": int(claim_support_actor_anchor_count),
        "claim_support_evidence_anchor_count": int(claim_support_evidence_anchor_count),
        "gap_codes": _dedupe_text_values(structured_handoff_gaps),
        "gap_count": len(_dedupe_text_values(structured_handoff_gaps)),
    }
    unresolved_factual_gaps = list(gap_signals.get("factual_gaps") or [])
    unresolved_legal_gaps = list(gap_signals.get("legal_gaps") or [])
    if uncovered_intake_objectives:
        unresolved_factual_gaps.insert(
            0,
            "Intake coverage remains incomplete for one or more required objectives; chronology/actor/notice details should be closed before formalization.",
        )
    if missing_required_intake_objectives:
        unresolved_factual_gaps.insert(
            0,
            "Required intake objectives remain uncovered: " + ", ".join(missing_required_intake_objectives[:5]),
        )
    if int(structured_handoff_signals.get("gap_count", 0) or 0) > 0:
        unresolved_factual_gaps.append(
            "Structured drafting handoff is incomplete; promote intake facts, date/actor anchors, and evidence references into summary-of-facts and claim-support before optimization."
        )
    unresolved_factual_gaps = _dedupe_text_values(unresolved_factual_gaps)[:6]
    evidence_modality_signals = self._collect_evidence_modality_signals(
        draft=draft,
        claim_readiness=claim_readiness,
    )
    weak_evidence_modalities = list(evidence_modality_signals.get("weak_modalities") or [])
    weak_complaint_types = [
        claim_type
        for claim_type in claim_types
        if str(claim_type or "").strip().lower() in {"housing_discrimination", "hacc_research_engine"}
    ]
    targeted_weak_evidence_modalities = [
        modality
        for modality in weak_evidence_modalities
        if str(modality or "").strip().lower() in {"policy_document", "file_evidence"}
    ]
    policy_document_count = int(
        dict(evidence_modality_signals.get("modalities") or {}).get("policy_document", 0) or 0
    )
    file_evidence_count = int(
        dict(evidence_modality_signals.get("modalities") or {}).get("file_evidence", 0) or 0
    )
    total_elements = sum(int(entry.get("total_elements", 0) or 0) for entry in claim_readiness if isinstance(entry, dict))
    covered_elements = sum(int(entry.get("covered_elements", 0) or 0) for entry in claim_readiness if isinstance(entry, dict))
    claim_coverage = (
        (float(covered_elements) / float(total_elements))
        if total_elements > 0
        else (1.0 if summary_fact_count > 0 else 0.0)
    )
    ready_section_count = sum(
        1
        for section in sections.values()
        if isinstance(section, dict) and str(section.get("status") or "ready").strip().lower() == "ready"
    )
    section_coverage = (float(ready_section_count) / float(len(sections))) if sections else 0.0
    graph_gap_count = max(
        int(graph_signals.get("remaining_gap_count", 0) or 0),
        int(graph_signals.get("current_gap_count", 0) or 0),
    )
    graph_coverage = 1.0
    if str(graph_signals.get("status") or "ready").strip().lower() != "ready":
        graph_coverage -= 0.05
    if graph_gap_count > 0:
        graph_coverage -= min(0.25, 0.02 * float(graph_gap_count))
    if not _coerce_bool(graph_signals.get("knowledge_graph_enhanced"), default=True):
        graph_coverage -= 0.05
    graph_coverage = max(0.0, min(1.0, graph_coverage))
    graph_gate_active = (
        str(graph_signals.get("status") or "ready").strip().lower() != "ready"
        or graph_gap_count > 0
        or not _coerce_bool(graph_signals.get("knowledge_graph_available"), default=True)
        or not _coerce_bool(graph_signals.get("dependency_graph_available"), default=True)
    )
    coverage = max(
        0.0,
        min(
            1.0,
            round(
                (0.5 * claim_coverage) + (0.25 * section_coverage) + (0.25 * graph_coverage),
                3,
            ),
        ),
    )
    phase_status = str(overall_status or "ready").strip().lower() or "ready"
    if str(graph_signals.get("status") or "ready").strip().lower() != "ready":
        phase_status = _merge_status(phase_status, "warning")
    if graph_gate_active:
        phase_status = _merge_status(phase_status, "blocked")
    if (
        coverage < 0.98
        or unresolved_factual_gaps
        or unresolved_legal_gaps
        or missing_required_intake_objectives
        or targeted_weak_evidence_modalities
        or weak_complaint_types
        or document_low_grounding_flag
    ):
        phase_status = _merge_status(phase_status, "warning")
    if coverage <= 0.05 and (
        graph_gap_count > 0
        or not claim_readiness
        or unresolved_factual_gaps
        or unresolved_legal_gaps
    ):
        phase_status = "critical"
    if document_fact_backed_ratio < 0.25 and document_low_grounding_flag:
        phase_status = _merge_status(phase_status, "blocked")

    blockers: List[str] = []
    if graph_gate_active:
        blockers.append("graph_analysis_not_ready")
    if phase_status in {"warning", "blocked", "critical"}:
        blockers.append("document_generation_not_ready")
    if phase_status == "critical":
        blockers.append("document_generation_critical")
    if unresolved_factual_gaps:
        blockers.append("unresolved_factual_gaps_not_closed")
    if unresolved_legal_gaps:
        blockers.append("unresolved_legal_gaps_not_closed")
    if uncovered_intake_objectives or missing_required_intake_objectives:
        blockers.append("uncovered_intake_objectives")
    if int(structured_handoff_signals.get("gap_count", 0) or 0) > 0:
        blockers.append("structured_intake_handoff_incomplete")
    if weak_complaint_types:
        blockers.append("weak_complaint_type_generalization_needed")
    if targeted_weak_evidence_modalities:
        blockers.append("weak_evidence_modality_support_needed")
    if document_low_grounding_flag:
        blockers.append("document_provenance_grounding_needed")
    blockers = _dedupe_text_values(blockers)

    readiness_payload = {
        "status": overall_status,
        "claim_types": claim_types,
        "warning_count": aggregate_warning_count,
        "claims": claim_readiness,
        "sections": sections,
        "coverage": coverage,
        "phase_status": phase_status,
        "blockers": blockers,
        "unresolved_factual_gaps": unresolved_factual_gaps,
        "unresolved_legal_gaps": unresolved_legal_gaps,
        "uncovered_intake_objectives": uncovered_intake_objectives,
        "missing_required_intake_objectives": missing_required_intake_objectives,
        "objective_question_counts": objective_question_counts,
        "structured_intake_handoff_signals": structured_handoff_signals,
        "weak_complaint_types": weak_complaint_types,
        "evidence_modalities": dict(evidence_modality_signals.get("modalities") or {}),
        "weak_evidence_modalities": weak_evidence_modalities,
        "graph_completeness_signals": graph_signals,
        "document_provenance_summary": document_provenance_summary,
        "document_fact_backed_ratio": round(document_fact_backed_ratio, 4),
        "document_low_grounding_flag": document_low_grounding_flag,
        "drafting_guardrails": drafting_guardrails if drafting_guardrails else {"available": False, "status": "ready", "warning_count": 0, "blocker_count": 0, "warnings": []},
        "drafting_handoff": {
            "gate_on_graph_completeness": bool(graph_gate_active),
            "graph_phase_status": str(graph_signals.get("status") or "ready").strip().lower() or "ready",
            "graph_remaining_gap_count": int(graph_gap_count),
            "coverage": float(coverage),
            "ready_for_formalization": phase_status == "ready" and not blockers,
            "blockers": list(blockers),
            "summary_fact_count": len(summary_fact_lines),
            "claim_support_fact_count": len(claim_support_lines),
            "exhibit_count": len(exhibits),
            "policy_document_count": int(policy_document_count),
            "file_evidence_count": int(file_evidence_count),
            "document_fact_backed_ratio": round(document_fact_backed_ratio, 4),
            "document_low_grounding_flag": bool(document_low_grounding_flag),
            "uncovered_intake_objectives": uncovered_intake_objectives[:8],
            "missing_required_intake_objectives": missing_required_intake_objectives[:8],
            "unresolved_factual_gaps": unresolved_factual_gaps[:6],
            "unresolved_legal_gaps": unresolved_legal_gaps[:6],
            "targeted_weak_complaint_types": weak_complaint_types[:4],
            "targeted_weak_evidence_modalities": targeted_weak_evidence_modalities[:4],
            "structured_intake_handoff_signals": structured_handoff_signals,
            "formalization_readiness_snapshot": {
                "phase_status": phase_status,
                "coverage": float(coverage),
                "graph_gate_active": bool(graph_gate_active),
                "unresolved_factual_gap_count": len(unresolved_factual_gaps),
                "unresolved_legal_gap_count": len(unresolved_legal_gaps),
                "uncovered_intake_objective_count": len(uncovered_intake_objectives),
                "missing_required_intake_objective_count": len(missing_required_intake_objectives),
                "structured_handoff_gap_count": int(structured_handoff_signals.get("gap_count", 0) or 0),
                "weak_complaint_type_count": len(weak_complaint_types),
                "weak_evidence_modality_count": len(targeted_weak_evidence_modalities),
                "document_fact_backed_ratio": round(document_fact_backed_ratio, 4),
                "document_low_grounding_flag": bool(document_low_grounding_flag),
                "ready_for_formalization": phase_status == "ready" and not blockers,
            },
        },
    }
    guardrail_warnings = [
        dict(item)
        for item in list((drafting_guardrails or {}).get("warnings") or [])
        if isinstance(item, dict)
    ]
    if guardrail_warnings:
        readiness_payload["warnings"] = list(readiness_payload.get("warnings") or []) + guardrail_warnings
        readiness_payload["warning_count"] = int(readiness_payload.get("warning_count") or 0) + len(guardrail_warnings)
        guardrail_status = str((drafting_guardrails or {}).get("status") or "ready").strip().lower() or "ready"
        readiness_payload["status"] = _merge_status(
            str(readiness_payload.get("status") or "ready"),
            "blocked" if guardrail_status in {"blocked", "critical"} else guardrail_status,
        )
        readiness_payload["phase_status"] = _merge_status(
            str(readiness_payload.get("phase_status") or "ready"),
            "blocked" if int((drafting_guardrails or {}).get("blocker_count") or 0) > 0 else "warning",
        )
        if int((drafting_guardrails or {}).get("blocker_count") or 0) > 0:
            readiness_payload["blockers"] = _dedupe_text_values(
                list(readiness_payload.get("blockers") or []) + ["drafting_guardrail_blockers"]
            )
    workflow_phase_plan = self._build_runtime_workflow_phase_plan(
        drafting_readiness=readiness_payload,
        document_optimization=None,
    )
    workflow_optimization_guidance = _build_runtime_workflow_optimization_guidance(
        mediator=self.mediator,
        drafting_readiness=readiness_payload,
        workflow_phase_plan=workflow_phase_plan,
        document_optimization=None,
    )
    workflow_warnings = self._build_workflow_phase_warning_entries(workflow_phase_plan)
    optimization_warnings = _build_workflow_optimization_warning_entries(workflow_optimization_guidance)
    if workflow_phase_plan:
        readiness_payload["workflow_phase_plan"] = workflow_phase_plan
    if workflow_optimization_guidance:
        readiness_payload["workflow_optimization_guidance"] = workflow_optimization_guidance
    if workflow_warnings:
        readiness_payload["warnings"] = list(readiness_payload.get("warnings") or []) + workflow_warnings
        readiness_payload["warning_count"] = int(readiness_payload.get("warning_count") or 0) + len(workflow_warnings)
        for warning in workflow_warnings:
            readiness_payload["status"] = _merge_status(
                str(readiness_payload.get("status") or "ready"),
                str(warning.get("severity") or "ready"),
            )
    gap_warnings: List[Dict[str, Any]] = []
    if unresolved_factual_gaps:
        gap_warnings.append(
            {
                "code": "unresolved_factual_gaps",
                "severity": "warning",
                "message": "Unresolved factual gaps remain and should be closed before formalization.",
                "gaps": unresolved_factual_gaps[:5],
            }
        )
    if unresolved_legal_gaps:
        gap_warnings.append(
            {
                "code": "unresolved_legal_gaps",
                "severity": "warning",
                "message": "Unresolved legal gaps remain and should be closed before formalization.",
                "gaps": unresolved_legal_gaps[:5],
            }
        )
    if weak_complaint_types:
        gap_warnings.append(
            {
                "code": "weak_complaint_type_generalization_needed",
                "severity": "warning",
                "message": "Target complaint types still need stronger drafting generalization before formalization.",
                "claim_types": weak_complaint_types[:4],
            }
        )
    if uncovered_intake_objectives or missing_required_intake_objectives:
        gap_warnings.append(
            {
                "code": "uncovered_intake_objectives",
                "severity": "warning",
                "message": "Intake objectives remain uncovered and should be resolved before formalization.",
                "uncovered_objectives": uncovered_intake_objectives[:8],
                "missing_required_objectives": missing_required_intake_objectives[:8],
            }
        )
    if int(structured_handoff_signals.get("gap_count", 0) or 0) > 0:
        gap_warnings.append(
            {
                "code": "structured_intake_handoff_incomplete",
                "severity": "warning",
                "message": (
                    "Structured intake handoff is incomplete; promote facts, date/actor anchors, and evidence references "
                    "into summary-of-facts and claim-support generation before document optimization."
                ),
                "gap_codes": list(structured_handoff_signals.get("gap_codes") or [])[:8],
            }
        )
    if targeted_weak_evidence_modalities:
        gap_warnings.append(
            {
                "code": "weak_evidence_modality_support_needed",
                "severity": "warning",
                "message": "Weak evidence modalities require stronger source-anchored allegations before formalization.",
                "modalities": targeted_weak_evidence_modalities[:4],
            }
        )
    if gap_warnings:
        existing_warnings = [
            dict(item)
            for item in list(readiness_payload.get("warnings") or [])
            if isinstance(item, dict)
        ]
        readiness_payload["warnings"] = existing_warnings + gap_warnings
        readiness_payload["warning_count"] = int(readiness_payload.get("warning_count") or 0) + len(gap_warnings)
        readiness_payload["status"] = _merge_status(str(readiness_payload.get("status") or "ready"), "warning")
        readiness_payload["phase_status"] = _merge_status(str(readiness_payload.get("phase_status") or "ready"), "warning")
    if optimization_warnings:
        readiness_payload.setdefault("warnings", []).extend(optimization_warnings)
        readiness_payload["warning_count"] = int(readiness_payload.get("warning_count") or 0) + len(optimization_warnings)
        for warning in optimization_warnings:
            readiness_payload["status"] = _merge_status(
                str(readiness_payload.get("status") or "ready"),
                str(warning.get("severity") or "ready"),
            )

    return readiness_payload
