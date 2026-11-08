"""Question-selection methods delegated from ComplaintDenoiser.

The functions keep the original method bodies. Callers on the class forward
here so question selection stays behavior-compatible.
"""

from typing import Any, Dict, List, Optional

from .dependency_graph import DependencyGraph
from .knowledge_graph import KnowledgeGraph
from .denoiser import (
    _BYPASS_DEDUPLICATION_QUESTION_TYPES,
    dependency_lane_for,
    project_stopping_policy,
)


def _build_history_follow_up_questions(
    self,
    max_questions: int,
) -> List[Dict[str, Any]]:
    """Generate follow-up questions from prior low-specificity answers."""
    if max_questions <= 0 or not self.questions_asked:
        return []

    questions: List[Dict[str, Any]] = []
    seen_keys: Set[str] = set()
    recent_history = list(reversed(self.questions_asked[-12:]))

    for entry in recent_history:
        if len(questions) >= max_questions:
            break
        if not isinstance(entry, dict):
            continue
        question = entry.get('question')
        question = question if isinstance(question, dict) else {}
        answer_text = str(entry.get('answer') or '').strip()
        if not answer_text:
            continue

        qtype = str(question.get('type') or '').strip().lower()
        needs_confirmation = self._contains_confirmation_placeholder(answer_text)
        retaliation_context = self._contains_retaliation_context(answer_text)
        causation_signal = self._contains_causation_signal(answer_text)
        has_dates = bool(self._extract_date_strings(answer_text))
        has_named_actors = bool(self._extract_named_role_people(answer_text) or self._extract_named_people_with_titles(answer_text))
        has_documents = bool(self._extract_document_mentions(answer_text))
        has_sequence = self._contains_sequence_signal(answer_text)
        response_timings = self._extract_response_timing_phrases(answer_text)
        has_document_precision = self._contains_document_precision_signal(answer_text)
        has_adverse_action = self._contains_adverse_action_signal(answer_text)

        if needs_confirmation:
            follow_ups = [
                (
                    'timeline',
                    "You noted details that still need confirmation. What is the most specific date (month/day/year) for the event, and who took the action on that date?",
                    {
                        'gap_type': 'missing_exact_action_dates',
                        'follow_up_reason': 'needs_confirmation_placeholder',
                        'workflow_phase': 'graph_analysis',
                        'extraction_targets': ['exact_dates', 'actor_name', 'actor_role', 'event_order'],
                        'patchability_markers': ['chronology_patch_anchor', 'actor_link_patch_anchor'],
                    },
                ),
                (
                    'evidence',
                    "Which exact document, message, email, or notice can confirm that event, and what date appears on it?",
                    {
                        'gap_type': 'missing_written_notice',
                        'follow_up_reason': 'needs_confirmation_placeholder',
                        'workflow_phase': 'document_generation',
                        'extraction_targets': ['document_type', 'document_date', 'document_owner'],
                        'patchability_markers': ['support_patch_anchor', 'notice_chain_patch_anchor'],
                    },
                ),
            ]
            for follow_type, follow_text, follow_context in follow_ups:
                key = f"{follow_type}:{self._normalize_question_text(follow_text)}"
                if key in seen_keys or self._already_asked(follow_text):
                    continue
                seen_keys.add(key)
                questions.append(self._question_candidate(
                    source='history_follow_up',
                    question_type=follow_type,
                    question_text=follow_text,
                    context=follow_context,
                    priority='high',
                ))
                if len(questions) >= max_questions:
                    break

        if len(questions) >= max_questions:
            break

        chronology_gap = (
            qtype in {'timeline', 'responsible_party', 'clarification', 'relationship', 'requirement'}
            and (not has_dates or not has_sequence or not response_timings)
        )
        if chronology_gap and len(questions) < max_questions:
            chronology_text = (
                "Please list each key event in order with the exact date (month/day/year), "
                "who acted, and how long it took for the next response after your request or report."
            )
            key = f"timeline:{self._normalize_question_text(chronology_text)}"
            if key not in seen_keys and not self._already_asked(chronology_text):
                seen_keys.add(key)
                questions.append(self._question_candidate(
                    source='history_follow_up',
                    question_type='timeline',
                    question_text=chronology_text,
                    context={
                        'gap_type': 'missing_decision_timeline',
                        'follow_up_reason': 'chronology_gap_closeout',
                        'workflow_phase': 'graph_analysis',
                        'extraction_targets': ['exact_dates', 'event_order', 'response_timing', 'actor_name', 'actor_role'],
                        'patchability_markers': ['chronology_patch_anchor', 'chronology_response_patch_anchor', 'actor_link_patch_anchor'],
                    },
                    priority='high',
                ))

        should_probe_causation = (
            retaliation_context
            and (qtype in {'timeline', 'responsible_party', 'clarification', 'requirement', 'relationship'} or needs_confirmation)
            and (not causation_signal or not has_dates or not has_named_actors)
        )
        if should_probe_causation:
            causation_text = (
                "Please identify the protected activity, the adverse action, the exact dates for each, "
                "and why you believe the adverse action happened because of the protected activity."
            )
            decision_actor_text = (
                "Who specifically made or approved the adverse decision (full name, title, and organization), "
                "and who communicated it to you?"
            )
            causation_items = [
                (
                    'timeline',
                    causation_text,
                    {
                        'gap_type': 'retaliation_missing_causation_link',
                        'follow_up_reason': 'retaliation_causation_probe',
                        'workflow_phase': 'graph_analysis',
                        'extraction_targets': ['protected_activity', 'adverse_action', 'exact_dates', 'causation_link'],
                        'patchability_markers': ['chronology_patch_anchor', 'causation_patch_anchor'],
                    },
                ),
                (
                    'responsible_party',
                    decision_actor_text,
                    {
                        'gap_type': 'missing_staff_identity',
                        'follow_up_reason': 'retaliation_decision_maker_probe',
                        'workflow_phase': 'graph_analysis',
                        'extraction_targets': ['actor_name', 'actor_role', 'decision_maker'],
                        'patchability_markers': ['actor_link_patch_anchor', 'decision_actor_patch_anchor'],
                    },
                ),
            ]
            for follow_type, follow_text, follow_context in causation_items:
                key = f"{follow_type}:{self._normalize_question_text(follow_text)}"
                if key in seen_keys or self._already_asked(follow_text):
                    continue
                seen_keys.add(key)
                questions.append(self._question_candidate(
                    source='history_follow_up',
                    question_type=follow_type,
                    question_text=follow_text,
                    context=follow_context,
                    priority='high',
                ))
                if len(questions) >= max_questions:
                    break

        if len(questions) >= max_questions:
            break

        needs_decision_precision = (
            qtype in {'timeline', 'responsible_party', 'relationship', 'clarification', 'requirement'}
            and (not has_named_actors or not has_adverse_action)
        )
        if needs_decision_precision and len(questions) < max_questions:
            decision_precision_text = (
                "Who exactly made the adverse decision, what was the specific adverse action, "
                "and what title and organization did that person have at the time?"
            )
            key = f"responsible_party:{self._normalize_question_text(decision_precision_text)}"
            if key not in seen_keys and not self._already_asked(decision_precision_text):
                seen_keys.add(key)
                questions.append(self._question_candidate(
                    source='history_follow_up',
                    question_type='responsible_party',
                    question_text=decision_precision_text,
                    context={
                        'gap_type': 'missing_staff_identity',
                        'follow_up_reason': 'decision_precision_closeout',
                        'workflow_phase': 'graph_analysis',
                        'extraction_targets': ['actor_name', 'actor_role', 'decision_maker', 'adverse_action'],
                        'patchability_markers': ['actor_link_patch_anchor', 'decision_actor_patch_anchor', 'adverse_action_patch_anchor'],
                    },
                    priority='high',
                ))

        if len(questions) >= max_questions:
            break

        # Ask for concrete documentary anchors if narrative detail exists but sources are absent.
        if (retaliation_context or needs_confirmation or chronology_gap) and (not has_documents or not has_document_precision) and len(questions) < max_questions:
            doc_text = (
                "What exact document or message records the decision (document type, date, sender, recipient, and how it was delivered)?"
            )
            key = f"evidence:{self._normalize_question_text(doc_text)}"
            if key not in seen_keys and not self._already_asked(doc_text):
                seen_keys.add(key)
                questions.append(self._question_candidate(
                    source='history_follow_up',
                    question_type='evidence',
                    question_text=doc_text,
                    context={
                        'gap_type': 'missing_written_notice',
                        'follow_up_reason': 'document_anchor_probe',
                        'workflow_phase': 'document_generation',
                        'extraction_targets': ['document_type', 'document_date', 'document_owner', 'actor_name', 'actor_role'],
                        'patchability_markers': ['support_patch_anchor', 'notice_chain_patch_anchor', 'decision_actor_patch_anchor', 'documentary_artifact_patch_anchor'],
                    },
                    priority='high',
                ))

    return questions[:max_questions]


def collect_question_candidates(
    self,
    knowledge_graph: KnowledgeGraph,
    dependency_graph: DependencyGraph,
    max_questions: int = 10,
    intake_case_file: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Collect ranked question candidates before final rendering/exploration."""
    questions: List[Dict[str, Any]] = []
    candidate_budget = max(int(max_questions or 0), 0)
    if candidate_budget <= 0:
        return []
    working_pool_limit = max(candidate_budget * 4, candidate_budget + 12)

    contradiction_questions = self._build_contradiction_questions(dependency_graph, working_pool_limit)
    questions.extend(contradiction_questions)

    claim_element_questions = self._build_claim_element_questions(
        intake_case_file,
        working_pool_limit,
    )
    questions.extend(claim_element_questions[:working_pool_limit])

    proof_lead_questions = self._build_proof_lead_questions(
        intake_case_file,
        working_pool_limit,
    )
    questions.extend(proof_lead_questions[:working_pool_limit])

    temporal_gap_questions = self._build_claim_temporal_gap_questions(
        intake_case_file,
        working_pool_limit,
    )
    questions.extend(temporal_gap_questions[:working_pool_limit])

    history_follow_up_questions = self._build_history_follow_up_questions(
        working_pool_limit,
    )
    questions.extend(history_follow_up_questions[:working_pool_limit])

    kg_gaps = knowledge_graph.find_gaps()
    for gap in kg_gaps[:working_pool_limit]:
        if gap['type'] == 'low_confidence_entity':
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='clarification',
                question_text=gap['suggested_question'],
                context={
                    'entity_id': gap['entity_id'],
                    'entity_name': gap['entity_name'],
                    'confidence': gap['confidence']
                },
                priority='medium',
            ))
        elif gap['type'] == 'unsupported_claim':
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='evidence',
                question_text=gap['suggested_question'],
                context={
                    'claim_id': gap['entity_id'],
                    'claim_name': gap['claim_name']
                },
                priority='high',
            ))
        elif gap['type'] == 'isolated_entity':
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='relationship',
                question_text=gap['suggested_question'],
                context={
                    'entity_id': gap['entity_id'],
                    'entity_name': gap['entity_name']
                },
                priority='low',
            ))
        elif gap['type'] == 'missing_timeline':
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='timeline',
                question_text=gap['suggested_question'],
                context={},
                priority='high',
            ))
        elif gap['type'] == 'missing_responsible_party':
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='responsible_party',
                question_text=gap['suggested_question'],
                context={},
                priority='high',
            ))
        elif gap['type'] == 'missing_impact_remedy':
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='impact',
                question_text=gap['suggested_question'],
                context={
                    'missing_impact': gap.get('missing_impact'),
                    'missing_remedy': gap.get('missing_remedy'),
                    'gap_type': gap.get('type'),
                },
                priority='high',
            ))
        elif gap['type'] in {'missing_written_notice', 'missing_response_dates'}:
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='evidence',
                question_text=gap['suggested_question'],
                context={'gap_type': gap.get('type')},
                priority='high',
            ))
        elif gap['type'] in {'missing_hearing_request_date', 'missing_decision_timeline', 'missing_exact_action_dates'}:
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='timeline',
                question_text=gap['suggested_question'],
                context={'gap_type': gap.get('type')},
                priority='high',
            ))
        elif gap['type'] in {'missing_staff_identity', 'missing_staff_title'}:
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='responsible_party',
                question_text=gap['suggested_question'],
                context={'gap_type': gap.get('type')},
                priority='high',
            ))
        elif gap['type'] in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequencing_dates'}:
            questions.append(self._question_candidate(
                source='knowledge_graph_gap',
                question_type='timeline',
                question_text=gap['suggested_question'],
                context={'gap_type': gap.get('type')},
                priority='high',
            ))

    unsatisfied = dependency_graph.find_unsatisfied_requirements()
    for req in unsatisfied[:working_pool_limit]:
        missing_deps = req.get('missing_dependencies', [])
        for dep in missing_deps[:2]:
            questions.append(self._question_candidate(
                source='dependency_graph_requirement',
                question_type='requirement',
                question_text=(
                    f"What do you recall, or what dates, people, or documents can you share, "
                    f"about '{dep['source_name']}' in relation to '{req['node_name']}'?"
                ),
                context={
                    'claim_id': req['node_id'],
                    'claim_name': req['node_name'],
                    'requirement_id': dep['source_node_id'],
                    'requirement_name': dep['source_name']
                },
                priority='high',
            ))
            if len(questions) >= working_pool_limit:
                break
        if len(questions) >= working_pool_limit:
            break

    blocker_issues = []
    if hasattr(dependency_graph, 'get_blocker_follow_up_issues'):
        try:
            blocker_issues = dependency_graph.get_blocker_follow_up_issues()
        except Exception:
            blocker_issues = []
    for issue in blocker_issues[:working_pool_limit]:
        if not isinstance(issue, dict):
            continue
        questions.append(self._question_candidate(
            source='dependency_graph_requirement',
            question_type=str(issue.get('question_type') or 'timeline'),
            question_text=str(issue.get('suggested_question') or 'Can you provide the missing follow-up details for this blocker?'),
            context={
                'issue_id': issue.get('issue_id'),
                'issue_type': issue.get('issue_type'),
                'node_id': issue.get('node_id'),
                'node_name': issue.get('node_name'),
                'gap_type': issue.get('issue_type'),
                'recommended_resolution_lane': issue.get('recommended_resolution_lane'),
                'workflow_phase': issue.get('workflow_phase'),
                'workflow_phase_rank': issue.get('workflow_phase_rank'),
                'extraction_targets': list(issue.get('extraction_targets') or []),
                'patchability_markers': list(issue.get('patchability_markers') or []),
            },
            priority='high' if str(issue.get('severity') or '').lower() == 'blocking' else 'medium',
        ))
        if len(questions) >= working_pool_limit:
            break

    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    questions.sort(
        key=lambda q: (
            int(q.get('proof_priority', self._phase1_proof_priority(q.get('type', '')))),
            priority_order.get(q.get('priority', 'low'), 3),
        )
    )
    # Suppress duplicate question objectives: keep only the highest-priority representative
    # for each (question_type, target_element_id) pair to avoid flooding the candidate list
    # with redundant asks.
    deduped: List[Dict[str, Any]] = []
    seen_objective_keys: set = set()
    for q in questions:
        if not isinstance(q, dict):
            continue
        q = self._annotate_proof_directed_candidate(q)
        q_type = str(q.get('type') or q.get('question_type') or '').strip().lower()
        q_element = self._question_target_element_id(q)
        q_objective_key = str(q.get('question_objective_key') or self._question_objective_key(q))
        # Only deduplicate candidates that explicitly target a specific element;
        # generic/clarification questions are always kept.
        if q_element and q_type not in _BYPASS_DEDUPLICATION_QUESTION_TYPES:
            if q_objective_key in seen_objective_keys:
                continue
            seen_objective_keys.add(q_objective_key)
        deduped.append(q)
    selected = self._select_proof_directed_candidates(
        deduped,
        max_questions=candidate_budget,
        preserve_order=True,
    )
    for required_source in ('intake_claim_element_gap', 'intake_proof_gap'):
        if any(candidate.get('candidate_source') == required_source for candidate in selected):
            continue
        source_candidate = next(
            (
                candidate
                for candidate in deduped
                if isinstance(candidate, dict) and candidate.get('candidate_source') == required_source
            ),
            None,
        )
        if not source_candidate:
            continue
        source_candidate = self._annotate_proof_directed_candidate(source_candidate, selected=selected)
        if len(selected) < candidate_budget:
            selected.append(source_candidate)
            continue
        replacement_index = None
        for index in range(len(selected) - 1, -1, -1):
            if selected[index].get('candidate_source') in {'knowledge_graph_gap', 'standard_intake_backstop'}:
                replacement_index = index
                break
        if replacement_index is not None:
            selected[replacement_index] = source_candidate
    return selected[:candidate_budget]


def evaluate_interview_stop(
    self,
    *,
    open_questions: Optional[List[Dict[str, Any]]] = None,
    intake_case_file: Optional[Dict[str, Any]] = None,
    provider_status: Any = None,
    cancelled: bool = False,
    iteration_count: Optional[int] = None,
    iteration_cap: Optional[int] = None,
    question_limit: Optional[int] = None,
    loss_converged: bool = False,
    pool_empty: Optional[bool] = None,
    paused: bool = False,
    needs_review: bool = False,
    repeat_attempts: Optional[int] = None,
    no_information_attempts: Optional[int] = None,
    model_retries: Optional[int] = None,
    contradictions: Optional[List[Dict[str, Any]]] = None,
    open_dependencies: Optional[List[Dict[str, Any]]] = None,
    hook_completed: bool = False,
    budget_exhausted: bool = False,
    worker_stalled: bool = False,
) -> Dict[str, Any]:
    """Classify the interview stop. Shortcuts cannot claim completion.

    ``needs_answer`` means a relevant user-answerable target is still open.
    ``saturated`` means every relevant answerable target is answered or
    explicitly disposed, and the result carries an unresolved-issue summary.
    ``deferred_unknown`` is an unknown-only stop and is not core-fact completion.
    ``provider_unavailable``, ``cancelled``, and ``limit_reached`` never
    advertise intake completion or filing readiness.
    """
    if isinstance(intake_case_file, dict):
        self.load_question_dispositions(intake_case_file)
    limit = self.QUESTION_COUNT_LIMIT if question_limit is None else int(question_limit)
    open_targets: List[Dict[str, Any]] = []
    seen_open = set()
    for question in open_questions or []:
        if not isinstance(question, dict):
            continue
        bound = self._bind_unresolved_target(question)
        target = bound.get("unresolved_target") if isinstance(bound.get("unresolved_target"), dict) else {}
        target_id = str(target.get("target_id") or bound.get("target_id") or "").strip()
        revision = str(target.get("target_revision") or bound.get("target_revision") or "").strip()
        if not target_id or target.get("user_answerability") not in {None, "", "user_observable"}:
            if target.get("user_answerability") not in {None, "", "user_observable"}:
                continue
        if not target_id:
            continue
        if target.get("user_answerability") and target.get("user_answerability") != "user_observable":
            continue
        if self.is_question_target_closed(target_id, revision or None):
            continue
        if target_id in seen_open:
            continue
        seen_open.add(target_id)
        open_targets.append({
            "target_id": target_id,
            "target_revision": revision or None,
            "target_kind": str(target.get("target_kind") or bound.get("target_kind") or "") or None,
            "reason": "open_answerable_target",
        })

    dependency_items: List[Dict[str, Any]] = []
    lanes: List[str] = []
    for dependency in open_dependencies or []:
        lane = dependency_lane_for(dependency)
        if lane is None or not isinstance(dependency, dict):
            continue
        target_id = str(dependency.get("target_id") or dependency.get("id") or "").strip() or None
        dependency_items.append({
            "target_id": target_id,
            "target_revision": str(dependency.get("target_revision") or "") or None,
            "target_kind": str(dependency.get("target_kind") or dependency.get("kind") or lane),
            "reason": lane,
            "dependency_lane": lane,
        })
        lanes.append(lane)
    primary_lane = None
    for lane_name in ("source_research", "evidence_request", "review"):
        if lane_name in lanes:
            primary_lane = lane_name
            break

    disposed: List[Dict[str, Any]] = []
    unknown_only = True
    answered_count = 0
    for record in self.question_disposition_records:
        if not isinstance(record, dict) or record.get("reopened"):
            continue
        target_id = str(record.get("target_id") or "").strip()
        if not target_id:
            continue
        disposition = str(record.get("disposition") or "").strip().lower()
        if disposition not in self._CLOSED_TARGET_DISPOSITIONS and disposition not in self._NON_FACT_DISPOSITIONS:
            continue
        if target_id in seen_open:
            continue
        item = {
            "target_id": target_id,
            "target_revision": str(record.get("target_revision") or "") or None,
            "target_kind": record.get("target_kind"),
            "disposition": disposition,
            "reason": "explicit_disposition",
        }
        disposed.append(item)
        if disposition == "answered":
            answered_count += 1
            unknown_only = False
        elif disposition not in self._UNKNOWN_DISPOSITIONS:
            unknown_only = False

    provider_token = str(provider_status or "").strip().lower()
    stalled = bool(worker_stalled) or provider_token in {"worker_stalled", "stalled", "stuck"}
    provider_down = provider_token in self._PROVIDER_UNAVAILABLE_STATUSES
    asked_count = len(self.questions_asked)
    over_question_limit = asked_count > limit
    over_iteration_cap = (
        iteration_count is not None
        and iteration_cap is not None
        and int(iteration_count) >= int(iteration_cap)
    )
    rejected_shortcuts = []
    if pool_empty is None:
        pool_empty = len(self.questions_pool) == 0 and not open_targets
    if pool_empty and not disposed:
        rejected_shortcuts.append("empty_question_list")
    if loss_converged:
        rejected_shortcuts.append("loss_convergence")
    if over_question_limit:
        rejected_shortcuts.append("question_count_limit")
    if over_iteration_cap:
        rejected_shortcuts.append("iteration_cap")

    observed_repeats = max([int(value or 0) for value in self.objective_repeat_counts.values()] or [0])
    repeat_count = observed_repeats if repeat_attempts is None else int(repeat_attempts)
    no_info_count = (
        int(getattr(self, "no_information_attempts", 0) or 0)
        if no_information_attempts is None
        else int(no_information_attempts)
    )
    retry_count = (
        int(getattr(self, "model_retry_count", 0) or 0)
        if model_retries is None
        else int(model_retries)
    )
    repeat_bounded = repeat_count >= self.MAX_REPEAT_ATTEMPTS
    no_info_bounded = no_info_count >= self.MAX_NO_INFORMATION_ATTEMPTS
    retry_bounded = retry_count >= self.MAX_MODEL_RETRIES
    if repeat_bounded:
        rejected_shortcuts.append("repeat_attempt_bound")
    if no_info_bounded:
        rejected_shortcuts.append("no_information_bound")
    if retry_bounded:
        rejected_shortcuts.append("model_retry_bound")
    if hook_completed:
        rejected_shortcuts.append("completed_hook")
    if any(
        str(item.get("disposition") or "") in {"unknown", "skipped", "refused", "deferred"}
        for item in disposed
    ):
        rejected_shortcuts.append("skipped_or_unknown_answer")
    if budget_exhausted:
        rejected_shortcuts.append("budget_exhausted")
    review_requested = bool(needs_review) or bool(contradictions)

    unresolved_items = list(open_targets)
    unresolved_items.extend(dependency_items)
    for item in disposed:
        if item.get("disposition") != "answered":
            unresolved_items.append(dict(item))
    for diagnostic in self.source_operator_diagnostics:
        if isinstance(diagnostic, dict):
            unresolved_items.append({
                "target_id": None,
                "reason": "source_operator_diagnostic",
                "message": diagnostic.get("message"),
            })
    summary = {
        "items": unresolved_items,
        "open_answerable_count": len(open_targets),
        "disposed_count": len(disposed),
        "answered_count": answered_count,
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
        "filing_ready": False,
        "rejected_shortcuts": rejected_shortcuts,
        "repeat_attempts": repeat_count,
        "no_information_attempts": no_info_count,
        "model_retries": retry_count,
    }

    if cancelled or provider_token == "cancelled":
        state = "cancelled"
    elif provider_down:
        state = "provider_unavailable"
    elif stalled:
        state = "no_progress"
    elif budget_exhausted:
        state = "no_progress"
    elif over_iteration_cap or over_question_limit:
        state = "limit_reached"
    elif open_targets and not (repeat_bounded or no_info_bounded or retry_bounded):
        state = "needs_answer"
    elif disposed and unknown_only and answered_count == 0 and not (repeat_bounded or no_info_bounded or retry_bounded) and not primary_lane:
        state = "deferred_unknown"
    elif not open_targets and primary_lane and not (repeat_bounded or no_info_bounded or retry_bounded):
        state = {
            "source_research": "saturated",
            "evidence_request": "deferred_needs_evidence",
            "review": "needs_review",
        }[primary_lane]
    elif disposed and not open_targets and not (repeat_bounded or no_info_bounded or retry_bounded):
        state = "saturated"
    elif repeat_bounded or no_info_bounded or retry_bounded:
        state = "no_progress"
    elif review_requested and not open_targets:
        state = "needs_review"
    elif self.source_operator_diagnostics and not disposed:
        state = "provider_unavailable"
    elif open_targets:
        state = "needs_answer"
    else:
        state = "needs_answer"

    targets_accounted_for = bool(disposed) and not open_targets and state == "saturated"
    intake_complete = (
        state == "saturated"
        and not unresolved_items
        and answered_count > 0
        and not unknown_only
    )
    summary["core_facts_complete"] = False
    stop = {
        "state": state,
        "targets_accounted_for": targets_accounted_for,
        "intake_complete": intake_complete,
        "filing_ready": False,
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
        "ready_for_evidence_phase": False,
        "awaiting_user": state == "needs_answer" and not stalled,
        "worker_stalled": stalled,
        "budget_exhausted": bool(budget_exhausted),
        "dependency_lane": None if open_targets or stalled or budget_exhausted else primary_lane,
        "hook_completed": bool(hook_completed),
        "supervisory_restart": False,
        "busy_loop": False,
        "reads_developer_stdin": False,
        "unresolved_issue_summary": summary,
        "message": self._interview_stop_message(state, intake_complete),
    }
    if not paused:
        wait = getattr(self, "intentional_user_wait", None)
        paused = isinstance(wait, dict) and bool(wait.get("paused")) and bool(wait.get("intentional"))
    projected = project_stopping_policy(
        stop,
        paused=paused,
        needs_review=bool(review_requested) and not open_targets,
    )
    stop.update({
        "outcome": projected["outcome"],
        "remaining_issues": projected["remaining_issues"],
        "resumable_next_action": projected["resumable_next_action"],
        "stopping_distinction": projected["stopping_distinction"],
        "operation_terminated": projected["operation_terminated"],
        "busy_loop": False,
        "reads_developer_stdin": False,
    })
    stop["awaiting_user"] = projected["outcome"] in {"awaiting_user", "paused"} and not stalled
    self.last_interview_stop = stop
    return stop


def generate_evidence_questions(self,
                               knowledge_graph: KnowledgeGraph,
                               dependency_graph: DependencyGraph,
                               evidence_gaps: List[Dict[str, Any]],
                               alignment_evidence_tasks: Optional[List[Dict[str, Any]]] = None,
                               evidence_workflow_action_queue: Optional[List[Dict[str, Any]]] = None,
                               max_questions: int = 5) -> List[Dict[str, Any]]:
    """
    Generate denoising questions for evidence phase.

    Args:
        knowledge_graph: Current knowledge graph
        dependency_graph: Current dependency graph
        evidence_gaps: Identified evidence gaps
        alignment_evidence_tasks: Shared intake/evidence element tasks to prioritize
        evidence_workflow_action_queue: Ranked workflow steering actions for evidence follow-up
        max_questions: Maximum questions to generate

    Returns:
        List of evidence-focused denoising questions
    """
    questions = []

    prioritized_tasks = (
        alignment_evidence_tasks
        if isinstance(alignment_evidence_tasks, list)
        else []
    )
    workflow_actions = (
        evidence_workflow_action_queue
        if isinstance(evidence_workflow_action_queue, list)
        else []
    )
    priority_workflow_actions = []
    remaining_workflow_actions = []
    for action in workflow_actions:
        if not isinstance(action, dict):
            continue
        action_code = str(action.get('action_code') or '').strip().lower()
        if (
            action_code in {'refine_document_grounding_strategy', 'retarget_document_grounding'}
            and (
                bool(action.get('learned_support_lane_priority'))
                or str(action.get('learned_support_kind') or '').strip()
            )
        ):
            priority_workflow_actions.append(action)
        else:
            remaining_workflow_actions.append(action)

    ordered_workflow_actions = [*priority_workflow_actions, *remaining_workflow_actions]

    def _append_workflow_action_question(action: Dict[str, Any]) -> None:
        if len(questions) >= max_questions:
            return
        phase_name = str(action.get('phase_name') or '').strip().lower()
        if phase_name not in {'graph_analysis', 'document_generation', 'evidence_collection', 'cross_phase'}:
            return
        action_code = str(action.get('action_code') or '').strip().lower()
        focus_areas = [
            str(item).strip()
            for item in (action.get('focus_areas') or [])
            if str(item).strip()
        ]
        action_text = str(action.get('action') or '').strip()
        if not action_text:
            return
        claim_type = str(action.get('claim_type') or 'this claim').strip()
        original_claim_element_id = str(action.get('claim_element_id') or '').strip()
        suggested_claim_element_id = str(action.get('suggested_claim_element_id') or '').strip()
        claim_element_id = (
            suggested_claim_element_id
            if action_code == 'retarget_document_grounding' and suggested_claim_element_id
            else original_claim_element_id
        )
        claim_element_label = str(
            action.get('claim_element_label')
            or claim_element_id
            or (focus_areas[0] if focus_areas else 'this issue')
        ).strip()
        preferred_support_kind = str(action.get('preferred_support_kind') or '').strip().lower()
        missing_fact_bundle = [
            str(item).strip()
            for item in (action.get('missing_fact_bundle') or [])
            if str(item).strip()
        ]
        if action_code == 'recover_document_grounding':
            bundle_hint = (
                f" I still need grounding facts about {missing_fact_bundle[0]}."
                if missing_fact_bundle
                else ''
            )
            if preferred_support_kind == 'authority':
                question_text = (
                    f"What legal authority, policy, or official document can ground "
                    f"{claim_element_label} for {claim_type}?{bundle_hint}"
                )
            elif preferred_support_kind == 'testimony':
                question_text = (
                    f"What first-hand testimony or witness detail can ground "
                    f"{claim_element_label} for {claim_type}?{bundle_hint}"
                )
            else:
                question_text = (
                    f"What evidence would best ground {claim_element_label} for {claim_type}?{bundle_hint}"
                )
        elif action_code in {'refine_document_grounding_strategy', 'retarget_document_grounding'}:
            suggested_support_kind = str(action.get('suggested_support_kind') or '').strip().lower()
            alternate_support_kinds = [
                str(item).strip().lower()
                for item in (action.get('alternate_support_kinds') or [])
                if str(item).strip()
            ]
            next_lane = suggested_support_kind or (alternate_support_kinds[0] if alternate_support_kinds else '')
            if action_code == 'retarget_document_grounding':
                bundle_hint = (
                    f" Focus especially on {missing_fact_bundle[0]}."
                    if missing_fact_bundle
                    else ''
                )
                retarget_hint = (
                    f" Instead of staying on {original_claim_element_id.replace('_', ' ')}, "
                    if suggested_claim_element_id and original_claim_element_id and suggested_claim_element_id != original_claim_element_id
                    else ''
                )
                question_text = (
                    f"The learned {next_lane or 'support'} lane still did not improve grounding enough. "
                    f"{retarget_hint}what more specific fact, date, witness detail, or document can narrow the grounding gap "
                    f"for {claim_element_label} in {claim_type}?{bundle_hint}"
                )
            elif next_lane == 'authority':
                question_text = (
                    f"The last grounding pass did not improve enough. What legal authority, policy, or official document can better ground "
                    f"{claim_element_label} for {claim_type}?"
                )
            elif next_lane == 'testimony':
                question_text = (
                    f"The last grounding pass did not improve enough. What first-hand testimony or witness detail can better ground "
                    f"{claim_element_label} for {claim_type}?"
                )
            else:
                question_text = (
                    f"The last grounding pass did not improve enough. What stronger evidence can better ground "
                    f"{claim_element_label} for {claim_type}?"
                )
        else:
            question_text = (
                f"What evidence would best help us {action_text.lower()}"
                + (f" Focus first on {focus_areas[0]}." if focus_areas else "")
            )
        questions.append({
            'question': self._with_empathy(question_text, 'evidence_clarification'),
            'type': 'evidence_clarification',
            'context': {
                'workflow_action': True,
                'workflow_phase': phase_name,
                'workflow_rank': int(action.get('rank', 0) or 0),
                'workflow_focus_areas': focus_areas,
                'action_code': action_code,
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
                'original_claim_element_id': original_claim_element_id,
                'suggested_claim_element_id': suggested_claim_element_id,
                'claim_element_label': claim_element_label,
                'preferred_support_kind': preferred_support_kind,
                'learned_support_kind': str(action.get('learned_support_kind') or '').strip().lower(),
                'suggested_support_kind': str(action.get('suggested_support_kind') or '').strip().lower(),
                'alternate_support_kinds': list(action.get('alternate_support_kinds') or []),
                'missing_fact_bundle': missing_fact_bundle,
                'document_grounding_recovery': action_code == 'recover_document_grounding',
                'document_grounding_strategy_refinement': action_code == 'refine_document_grounding_strategy',
                'document_grounding_retargeting': action_code == 'retarget_document_grounding',
                'learned_support_lane_priority': bool(action.get('learned_support_lane_priority')),
            },
            'priority': 'high',
            'proof_priority': 0,
        })

    for action in priority_workflow_actions:
        _append_workflow_action_question(action)

    for task in prioritized_tasks[:max_questions]:
        if len(questions) >= max_questions:
            break
        if not isinstance(task, dict):
            continue
        claim_type = str(task.get('claim_type') or 'this claim').strip()
        claim_element_id = str(task.get('claim_element_id') or '').strip()
        claim_element_label = str(
            task.get('claim_element_label')
            or claim_element_id
            or 'this issue'
        ).strip()
        support_status = str(task.get('support_status') or '').strip().lower()
        action = str(task.get('action') or 'fill_evidence_gaps').strip().lower()
        preferred_support_kind = str(task.get('preferred_support_kind') or '').strip().lower()
        preferred_evidence_classes = [
            str(item).strip().replace('_', ' ')
            for item in (task.get('preferred_evidence_classes') or [])
            if str(item).strip()
        ]
        missing_fact_bundle = [
            str(item).strip()
            for item in (task.get('missing_fact_bundle') or [])
            if str(item).strip()
        ]
        recommended_queries = [
            str(item).strip()
            for item in (task.get('recommended_queries') or [])
            if str(item).strip()
        ]
        evidence_hint = ''
        if preferred_evidence_classes:
            evidence_hint = f" such as {', '.join(preferred_evidence_classes[:3])}"
        bundle_hint = f" I still need facts about {missing_fact_bundle[0]}." if missing_fact_bundle else ''
        temporal_next_actions = [
            item
            for item in (task.get('temporal_next_actions') if isinstance(task.get('temporal_next_actions'), list) else [])
            if isinstance(item, dict)
        ]
        primary_temporal_action = temporal_next_actions[0] if temporal_next_actions else {}
        temporal_question_objective = str(primary_temporal_action.get('question_objective') or '').strip()
        temporal_follow_up_target = str(primary_temporal_action.get('follow_up_target') or '').strip()
        if action == 'fill_temporal_chronology_gap':
            temporal_blocking_reasons = task.get('temporal_rule_blocking_reasons')
            if isinstance(temporal_blocking_reasons, list):
                temporal_blocking_reason = next((str(item).strip() for item in temporal_blocking_reasons if str(item).strip()), '')
            else:
                temporal_blocking_reason = str(temporal_blocking_reasons or '').strip()
            temporal_reason = str(
                primary_temporal_action.get('reason')
                or temporal_blocking_reason
                or ''
            ).strip()
            question_objective = str(
                temporal_question_objective
                or 'anchor_capture'
            ).strip()
            follow_up_target = str(primary_temporal_action.get('follow_up_target') or '').strip().lower()
            temporal_question_objective = question_objective
            temporal_follow_up_target = follow_up_target
            affected_rule = (
                primary_temporal_action.get('affected_rule')
                if isinstance(primary_temporal_action.get('affected_rule'), dict)
                else {}
            )
            rule_hint = str(
                affected_rule.get('rule_frame_id')
                or primary_temporal_action.get('affected_rule_frame_id')
                or task.get('temporal_rule_profile_id')
                or ''
            ).strip()
            if question_objective == 'contradiction_resolution':
                question_text = (
                    f"What dated record or firsthand detail resolves the conflicting chronology for "
                    f"{claim_element_label} in {claim_type}?"
                )
            elif question_objective == 'deadline_verification':
                question_text = (
                    f"What filing, notice, or agency record verifies the deadline timing for "
                    f"{claim_element_label} in {claim_type}?"
                )
            elif follow_up_target == 'document_request':
                question_text = (
                    f"What dated document anchors the chronology for {claim_element_label} "
                    f"in {claim_type}?"
                )
            elif follow_up_target == 'external_corroboration':
                question_text = (
                    f"What external record can corroborate the timing for {claim_element_label} "
                    f"in {claim_type}?"
                )
            else:
                question_text = (
                    f"What exact date, sequence, or first-hand chronology detail resolves "
                    f"{claim_element_label} for {claim_type}?"
                )
            if temporal_reason:
                question_text = f"{question_text} This is needed because {temporal_reason}"
            if rule_hint:
                question_text = f"{question_text} Affected rule: {rule_hint}."
            question_type = 'timeline'
            priority = 'high'
        elif support_status == 'contradicted' or action == 'resolve_support_conflicts':
            question_text = (
                f"What evidence best resolves the conflict around {claim_element_label} "
                f"for {claim_type}?{bundle_hint}"
            )
            question_type = 'evidence_conflict'
            priority = 'high'
        else:
            if preferred_support_kind == 'authority':
                question_text = (
                    f"What legal authority or official policy material do you have to support "
                    f"{claim_element_label} for {claim_type}?{bundle_hint}"
                )
            elif preferred_support_kind == 'testimony':
                question_text = (
                    f"What first-hand testimony or witness account can support {claim_element_label} "
                    f"for {claim_type}?{bundle_hint}"
                )
            else:
                question_text = (
                    f"What evidence{evidence_hint} do you have to support {claim_element_label} "
                    f"for {claim_type}?{bundle_hint}"
                )
            question_type = 'evidence_clarification'
            priority = 'high' if bool(task.get('blocking')) else 'medium'
        questions.append({
            'type': question_type,
            'question': question_text,
            'context': {
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
                'claim_element_label': claim_element_label,
                'support_status': support_status,
                'alignment_task': True,
                'preferred_support_kind': preferred_support_kind,
                'preferred_evidence_classes': list(task.get('preferred_evidence_classes') or []),
                'missing_fact_bundle': list(task.get('missing_fact_bundle') or []),
                'success_criteria': list(task.get('success_criteria') or []),
                'recommended_queries': recommended_queries,
                'temporal_next_actions': temporal_next_actions,
                'temporal_missingness_kind': str(task.get('temporal_missingness_kind') or ''),
                'question_objective': temporal_question_objective,
                'follow_up_target': temporal_follow_up_target,
                'affected_rule': (
                    dict(primary_temporal_action.get('affected_rule'))
                    if isinstance(primary_temporal_action.get('affected_rule'), dict)
                    else {}
                ),
                'affected_fact_ids': list(primary_temporal_action.get('affected_fact_ids') or []),
                'affected_issue_ids': list(primary_temporal_action.get('affected_issue_ids') or []),
            },
            'priority': priority,
            'question_objective': temporal_question_objective,
            'follow_up_target': temporal_follow_up_target,
            'proof_priority': 0 if action == 'fill_temporal_chronology_gap' else self._phase1_proof_priority(question_type),
        })

    for action in remaining_workflow_actions:
        _append_workflow_action_question(action)

    # Questions about missing evidence
    remaining_slots = max(0, max_questions - len(questions))
    for gap in evidence_gaps[:remaining_slots]:
        questions.append({
            'type': 'evidence_clarification',
            'question': f"Do you have evidence to support: {gap.get('name', 'this claim')}?",
            'context': {
                'gap_id': gap.get('id'),
                'claim_id': gap.get('related_claim'),
                'gap_type': gap.get('type', 'missing_evidence')
            },
            'priority': 'high'
        })

    # Questions about evidence quality/completeness
    evidence_entities = knowledge_graph.get_entities_by_type('evidence')
    for evidence in evidence_entities[:max(0, max_questions - len(questions))]:
        if evidence.confidence < 0.7:
            questions.append({
                'type': 'evidence_quality',
                'question': f"Can you provide more details about this evidence: {evidence.name}?",
                'context': {
                    'evidence_id': evidence.id,
                    'evidence_name': evidence.name,
                    'confidence': evidence.confidence
                },
                'priority': 'medium'
            })

    return questions[:max_questions]
