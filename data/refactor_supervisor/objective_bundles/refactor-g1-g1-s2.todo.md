# Objective Bundle: refactor/g1/g1-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-3: REF-003 Replace production sys.path mutation with package-level imports or adapter loader calls

## REF-003 Replace production sys.path mutation with package-level imports or adapter loader calls

- Status: completed
- Completion: manual
- Priority: P0
- Track: G1
- Depends on: 
- Outputs: applications/complaint_workspace.py, applications/document_api.py, integrations/ipfs_datasets/loader.py, scripts/agentic_complaint_evidence_scraper.py, scripts/agentic_scraper_cli.py, scripts/backfill_claim_testimony_links.py, scripts/check_hacc_routers.py, scripts/enrich_email_timeline_authorities.py, scripts/generate_decision_trees.py, scripts/generate_email_search_plan.py, scripts/generate_hacc_email_seed_plan.py, scripts/gmail_duckdb_daemon.py
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g1/g1-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G1.S2
- Missing evidence: The scan found production-style sys.path mutation that makes runtime behavior environment-sensitive.
- AST symbols: _ensure_local_ipfs_datasets_path, DEFAULT_USER_ID, DEFAULT_UI_UX_OPTIMIZER_METHOD, DEFAULT_UI_UX_OPTIMIZER_PRIORITY, DEFAULT_LLM_DRAFT_PROVIDER, DEFAULT_LLM_DRAFT_TIMEOUT_SECONDS, MIKE_STATUS_CONTRACT_VERSION, MIKE_HANDOFF_CONTRACT_VERSION, MIKE_SYNC_CONTRACT_VERSION, MAX_MIKE_HANDOFF_PARAGRAPHS, MAX_MIKE_WEAK_LINKS_DISPLAY, DEFAULT_UI_UX_SCREENSHOT_TARGET, _DATA_DIR, _SESSION_DIR, _DOCKET_ISSUE_ENTITY_KEYWORDS, _utc_now, _slugify_user_id, _split_lines, _unique_preserve_order, _slugify_graph_id, _normalize_annotation_tags, _build_schema_guided_tooling_recommendations, _normalize_fragment, _extract_person_name, _extract_defendant_name, _condense_timeline_text, _sentence_fragment, _event_fragment, _adverse_action_clause, _pleading_activity_fragment
- Merge key: refactor/g1/g1-s2
- Candidate kind: seed
- Todo vector key: ref-003-replaceproductionsys-pathmutationwithpackage-lev
- Acceptance: No production entrypoint mutates sys.path for normal imports.; Explicit exceptions are isolated to scripts/tests.

- [x] Task checkbox-4: REF-004 Route direct ipfs_datasets_py imports through integrations/ipfs_datasets adapters where production-facing

## REF-004 Route direct ipfs_datasets_py imports through integrations/ipfs_datasets adapters where production-facing

- Status: completed
- Completion: manual
- Priority: P0
- Track: G1
- Depends on: 
- Outputs: applications/complaint_cli.py, applications/complaint_workspace.py
- Validation: python -m pytest tests/test_ipfs_adapter_layer.py -q
- Bundle: refactor/g1/g1-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G1.S2
- Missing evidence: Optional dependency behavior should stay behind the adapter boundary.
- AST symbols: DEFAULT_UI_UX_SCREENSHOT_TARGET, DEFAULT_UI_UX_OPTIMIZER_METHOD, DEFAULT_UI_UX_OPTIMIZER_PRIORITY, app, service, _print, _split_multiline_values, _parse_json_option, session, identity, questions, claim_elements, tools, answer, chat_turn, chat, add_evidence, import_gmail_evidence_command, import_local_evidence_command, migrate_legacy_session_command, run_gmail_duckdb_pipeline_command, search_email_duckdb_command, review, mediator_prompt, complaint_readiness, ui_readiness, client_release_gate, capabilities, tooling_contract, workspace_data_schema
- Merge key: refactor/g1/g1-s2
- Candidate kind: seed
- Todo vector key: ref-004-routedirectipfs-datasets-pyimportsthroughintegra
- Acceptance: Production direct imports are replaced or documented.; Degraded mode still imports cleanly.
