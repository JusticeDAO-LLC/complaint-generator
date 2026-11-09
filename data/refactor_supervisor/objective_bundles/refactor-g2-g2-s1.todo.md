# Objective Bundle: refactor/g2/g2-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-5: REF-005 Split mediator/mediator.py by workflow service while preserving public API compatibility

## REF-005 Split mediator/mediator.py by workflow service while preserving public API compatibility

- Status: completed
- Completion: manual
- Priority: P0
- Track: G2
- Depends on: 
- Outputs: mediator/mediator.py, mediator/__init__.py
- Validation: python -m pytest tests/test_mediator.py tests/test_mediator_three_phase.py -q
- Bundle: refactor/g2/g2-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G2.S1
- Missing evidence: The mediator is the largest runtime file and carries high regression risk.
- AST symbols: ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT, FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES, Mediator, __init__, reset, resume, get_state, set_state, response, select_intake_question_candidates, _phase_focus_rank, _phase_focus_bonus, _is_document_question_candidate, _build_exhibit_ready_document_question, _apply_exhibit_ready_intake_questioning, _is_exact_dates_closure_match, _is_staff_names_titles_closure_match, _is_hearing_request_timing_closure_match, _is_response_dates_closure_match, _is_causation_sequence_match, _build_intake_claim_pressure_map, _build_intake_selector_legal_graph, _build_intake_matching_pressure_map, _build_intake_workflow_action_queue, _summarize_intake_workflow_action_queue, _build_evidence_workflow_action_queue, _get_document_provenance_summary, _get_document_grounding_lane_outcome_summary, _get_document_grounding_recovery_action, _get_document_grounding_improvement_next_action
- Merge key: refactor/g2/g2-s1
- Candidate kind: seed
- Todo vector key: ref-005-splitmediator-mediator-pybyworkflowservicewhilep
- Acceptance: One cohesive service is extracted.; Existing imports continue to resolve.

- [x] Task checkbox-6: REF-006 Move claim support orchestration helpers into focused private modules

## REF-006 Move claim support orchestration helpers into focused private modules

- Status: completed
- Completion: manual
- Priority: P0
- Track: G2
- Depends on: 
- Outputs: mediator/claim_support_hooks.py
- Validation: python -m pytest tests/test_claim_support_hooks.py tests/test_claim_support_review_dashboard_flow.py -q
- Bundle: refactor/g2/g2-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G2.S1
- Missing evidence: Claim support hooks are large enough to hide unrelated concerns.
- AST symbols: ClaimSupportHook, DUCKDB_AVAILABLE, _CONTENT_ORIGIN_ARTIFACT_FAMILY, _ARTIFACT_FAMILY_CORPUS_FAMILY, __init__, _get_default_db_path, _with_intake_summary_handoff, _resolve_artifact_identity, _prepare_duckdb_path, _check_duckdb_availability, _initialize_schema, _make_element_id, _make_testimony_id, _summarize_testimony_records, _testimony_quality_summary, _build_testimony_fact_text, _build_testimony_support_label, _build_testimony_support_link, _get_testimony_support_links, _get_enriched_claim_support_links, _tokenize_text, _extract_match_text, _normalize_graph_summary, _build_graph_trace, _summarize_graph_traces, _summarize_authority_treatment_signals, _summarize_authority_rule_candidates, _recommended_support_gap_action, _build_support_trace, _extract_record_parse_summary
- Merge key: refactor/g2/g2-s1
- Candidate kind: seed
- Todo vector key: ref-006-moveclaimsupportorchestrationhelpersintofocusedp
- Acceptance: At least one cohesive helper group moves behind a stable import.; No payload contract changes without tests.
