# Objective Bundle: refactor/g6/g6-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-17: REF-017 Audit broad exception handlers in mediator and adapter paths

## REF-017 Audit broad exception handlers in mediator and adapter paths

- Status: completed
- Completion: manual
- Priority: P1
- Track: G6
- Depends on: 
- Outputs: mediator/mediator.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/search.py
- Validation: python -m pytest tests/test_mediator.py tests/test_ipfs_adapter_layer.py -q
- Bundle: refactor/g6/g6-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G6.S1
- Missing evidence: The scan found many broad exception handlers; refactors need predictable failure semantics.
- AST symbols: ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT, FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES, Mediator, __init__, reset, resume, get_state, set_state, response, select_intake_question_candidates, _phase_focus_rank, _phase_focus_bonus, _is_document_question_candidate, _build_exhibit_ready_document_question, _apply_exhibit_ready_intake_questioning, _is_exact_dates_closure_match, _is_staff_names_titles_closure_match, _is_hearing_request_timing_closure_match, _is_response_dates_closure_match, _is_causation_sequence_match, _build_intake_claim_pressure_map, _build_intake_selector_legal_graph, _build_intake_matching_pressure_map, _build_intake_workflow_action_queue, _summarize_intake_workflow_action_queue, _build_evidence_workflow_action_queue, _get_document_provenance_summary, _get_document_grounding_lane_outcome_summary, _get_document_grounding_recovery_action, _get_document_grounding_improvement_next_action
- Merge key: refactor/g6/g6-s1
- Candidate kind: seed
- Todo vector key: ref-017-auditbroadexceptionhandlersinmediatorandadapterp
- Acceptance: Top production broad-exception clusters are documented.; At least one cluster returns a typed degraded result.

- [x] Task checkbox-18: REF-018 Convert silent pass blocks in user-facing workflows into debug logs or explicit fallbacks

## REF-018 Convert silent pass blocks in user-facing workflows into debug logs or explicit fallbacks

- Status: completed
- Completion: manual
- Priority: P1
- Track: G6
- Depends on: 
- Outputs: applications/ui_review.py, complaint_generator/ui_optimizer_daemon.py, mediator/state.py
- Validation: python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_review_api.py -q
- Bundle: refactor/g6/g6-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G6.S1
- Missing evidence: Silent failures hide regressions during long-running automation.
- AST symbols: DEFAULT_COMPLAINT_OUTPUT_REVIEW_TIMEOUT_S, DEFAULT_UI_REVIEW_TIMEOUT_S, DEFAULT_UI_REVIEW_PROVIDER, DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER, _TEXT_ONLY_UI_REVIEW_PROVIDERS, _TEXT_UI_REVIEW_TIMEOUTS, _MULTIMODAL_RATE_LIMIT_FALLBACKS, _UI_REVIEW_TEXT_ITEM_LIMIT, _UI_REVIEW_SUGGESTION_COUNT_LIMIT, _UI_REVIEW_METADATA_LIST_LIMIT, _UI_REVIEW_PROVIDER_IMAGE_LIMITS, _UI_REVIEW_ROUTE_PROVIDER_ALIASES, _UI_REVIEW_ROUTE_MODEL_ALIASES, _format_router_backend_path, _expand_surface_targets, _utc_now, _strip_code_fences, _truncate_text, _parse_json_response, _normalize_paths, _list_screenshots, _screenshot_payload, _list_artifact_metadata, _normalize_artifact_path, _artifact_matches_screenshot, _filter_artifacts_for_page, _page_review_unit_label, _artifact_priority_score, _max_page_reviews_for_provider, _select_screenshots_for_review
- Merge key: refactor/g6/g6-s1
- Candidate kind: seed
- Todo vector key: ref-018-convertsilentpassblocksinuser-facingworkflowsint
- Acceptance: Intentional ignores are named.; Unexpected failures leave diagnostic breadcrumbs.
