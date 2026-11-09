# Objective Bundle: refactor/g7/g7-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-21: REF-021 Move review payload normalization behind explicit DTO helpers

## REF-021 Move review payload normalization behind explicit DTO helpers

- Status: completed
- Completion: manual
- Priority: P1
- Track: G7
- Depends on: 
- Outputs: applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py
- Validation: python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py -q
- Bundle: refactor/g7/g7-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G7.S1
- Missing evidence: Review screens depend on stable payloads that should not be assembled ad hoc in route handlers.
- AST symbols: REVIEW_EXECUTION_COMPATIBILITY_NOTICE, REVIEW_EXECUTION_SUNSET, _apply_review_execution_compatibility_notice, _normalize_required_support_kinds_form, create_claim_support_review_router, attach_claim_support_review_routes, create_review_api_app, _MULTIPART_AVAILABLE, router, claim_support_review, claim_support_execute_follow_up, claim_support_confirm_intake_summary, claim_support_resolve_manual_review, claim_support_save_testimony, claim_support_save_document, app, payload, claim_support_upload_document, claim_support_upload_document_unavailable, file_bytes, DEFAULT_COMPLAINT_OUTPUT_REVIEW_TIMEOUT_S, DEFAULT_UI_REVIEW_TIMEOUT_S, DEFAULT_UI_REVIEW_PROVIDER, DEFAULT_UI_REVIEW_MODELS_BY_PROVIDER, _TEXT_ONLY_UI_REVIEW_PROVIDERS, _TEXT_UI_REVIEW_TIMEOUTS, _MULTIMODAL_RATE_LIMIT_FALLBACKS, _UI_REVIEW_TEXT_ITEM_LIMIT, _UI_REVIEW_SUGGESTION_COUNT_LIMIT, _UI_REVIEW_METADATA_LIST_LIMIT
- Merge key: refactor/g7/g7-s1
- Candidate kind: seed
- Todo vector key: ref-021-movereviewpayloadnormalizationbehindexplicitdtoh
- Acceptance: DTO helpers cover coverage, follow-up, and support-path summaries.; Route response snapshots stay stable.

- [x] Task checkbox-22: REF-022 Create fixture builders for Playwright review and dashboard smoke tests

## REF-022 Create fixture builders for Playwright review and dashboard smoke tests

- Status: completed
- Completion: manual
- Priority: P1
- Track: G7
- Depends on: 
- Outputs: tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py
- Validation: python -m pytest tests/test_claim_support_review_playwright_smoke.py tests/test_review_surface_site_playwright.py -q
- Bundle: refactor/g7/g7-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G7.S1
- Missing evidence: Large Playwright tests should share fixture setup before UI refactors.
- AST symbols: requests, uvicorn, FastAPI, duckdb, pytestmark, _build_browser_smoke_app, _build_document_browser_smoke_app, _build_document_review_browser_smoke_app, _build_document_workflow_priority_fixture, _build_hook_backed_browser_mediator, _build_real_browser_upload_mediator, _serve_app, test_claim_support_review_dashboard_smoke_shows_proactively_repaired_legacy_testimony_links, test_claim_support_review_dashboard_smoke_preserves_support_kind_in_canonical_url, test_document_builder_smoke_renders_question_review_links_with_section_aware_support_kind, test_document_builder_smoke_routes_workflow_priority_back_to_manual_review, test_document_builder_smoke_uses_workflow_phase_plan_for_priority_when_next_action_missing, test_document_builder_smoke_routes_workflow_priority_to_focused_review_surface, test_document_builder_smoke_routes_workflow_priority_to_support_packet_review, test_document_builder_smoke_marks_complete_evidence_as_ready_for_drafting, test_document_builder_smoke_marks_generate_formal_complaint_as_current_priority, test_claim_support_review_dashboard_smoke_renders_intake_evidence_alignment, test_claim_support_review_dashboard_smoke_confirms_intake_summary, test_claim_support_review_dashboard_smoke_reviews_manual_conflicts_from_next_action_banner, test_claim_support_review_dashboard_smoke_reviews_promoted_support_from_next_action_banner, test_claim_support_review_dashboard_smoke_filters_pending_review_alignment_updates, test_claim_support_review_dashboard_smoke_reviews_intake_gaps_from_next_action_banner, test_claim_support_review_dashboard_smoke_uses_workflow_phase_plan_for_graph_banner_when_next_action_missing, test_claim_support_review_dashboard_smoke_reviews_knowledge_graph_inputs_from_next_action_banner, test_claim_support_review_dashboard_smoke_reviews_dependency_inputs_from_next_action_banner
- Merge key: refactor/g7/g7-s1
- Candidate kind: seed
- Todo vector key: ref-022-createfixturebuildersforplaywrightreviewanddashb
- Acceptance: Shared builders remove repeated setup.; Screenshots still render with representative support states.
