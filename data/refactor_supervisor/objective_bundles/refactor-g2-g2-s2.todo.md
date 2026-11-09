# Objective Bundle: refactor/g2/g2-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-7: REF-007 Extract complaint workspace request handlers from UI state helpers

## REF-007 Extract complaint workspace request handlers from UI state helpers

- Status: completed
- Completion: manual
- Priority: P1
- Track: G2
- Depends on: 
- Outputs: applications/complaint_workspace.py
- Validation: python -m pytest tests/test_review_api.py -q
- Bundle: refactor/g2/g2-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G2.S2
- Missing evidence: The workspace module mixes UI routing, state shaping, and workflow calls.
- AST symbols: _ensure_local_ipfs_datasets_path, DEFAULT_USER_ID, DEFAULT_UI_UX_OPTIMIZER_METHOD, DEFAULT_UI_UX_OPTIMIZER_PRIORITY, DEFAULT_LLM_DRAFT_PROVIDER, DEFAULT_LLM_DRAFT_TIMEOUT_SECONDS, MIKE_STATUS_CONTRACT_VERSION, MIKE_HANDOFF_CONTRACT_VERSION, MIKE_SYNC_CONTRACT_VERSION, MAX_MIKE_HANDOFF_PARAGRAPHS, MAX_MIKE_WEAK_LINKS_DISPLAY, DEFAULT_UI_UX_SCREENSHOT_TARGET, _DATA_DIR, _SESSION_DIR, _DOCKET_ISSUE_ENTITY_KEYWORDS, _utc_now, _slugify_user_id, _split_lines, _unique_preserve_order, _slugify_graph_id, _normalize_annotation_tags, _build_schema_guided_tooling_recommendations, _normalize_fragment, _extract_person_name, _extract_defendant_name, _condense_timeline_text, _sentence_fragment, _event_fragment, _adverse_action_clause, _pleading_activity_fragment
- Merge key: refactor/g2/g2-s2
- Candidate kind: seed
- Todo vector key: ref-007-extractcomplaintworkspacerequesthandlersfromuist
- Acceptance: One handler group is isolated.; Routes keep the same response shape.

- [x] Task checkbox-8: REF-008 Separate dashboard fixture data from live route logic

## REF-008 Separate dashboard fixture data from live route logic

- Status: completed
- Completion: manual
- Priority: P1
- Track: G2
- Depends on: 
- Outputs: applications/dashboard_ui.py, playwright/server.js
- Validation: python -m pytest tests/test_claim_support_review_playwright_smoke.py -q
- Bundle: refactor/g2/g2-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G2.S2
- Missing evidence: Dashboard behavior is harder to test when fixtures and live assembly are interleaved.
- AST symbols: DashboardEntry, _IPFS_DATASETS_TEMPLATES_DIR, _IPFS_DATASETS_STATIC_DIR, _COMPLAINT_DASHBOARD_LINKS, _IPFS_DASHBOARD_ENTRIES, _IPFS_DASHBOARD_MAP, _LAYPERSON_HUB_ADVANCED_DASHBOARD_SLUGS, _CAPABILITY_CARDS, _JOURNEY_DETAIL_PANELS, _PACKAGE_CAPABILITY_MATRIX, _IMPROVEMENT_PLAN_ITEMS, _ENTRY_PATH_CARDS, _DASHBOARD_SUBSECTION_INDEX, _render_feature_chips, _render_link_row, _render_subsection_nav, _render_entry_path_cards, _render_dashboard_subsection_index, _render_capability_cards, _render_improvement_plan, _render_journey_detail_panels, _render_package_capability_matrix, _render_dashboard_section_nav, _DashboardUndefined, _DashboardMetrics, _IPFS_DASHBOARD_ENV, _static_url_for, _build_ipfs_dashboard_context, _render_ipfs_dashboard, _render_shell_page
- Merge key: refactor/g2/g2-s2
- Candidate kind: seed
- Todo vector key: ref-008-separatedashboardfixturedatafromliveroutelogic
- Acceptance: Fixture builders are named and reusable.; Playwright smoke tests remain stable.
