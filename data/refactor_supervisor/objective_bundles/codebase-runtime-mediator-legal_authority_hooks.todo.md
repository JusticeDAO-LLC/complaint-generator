# Codebase Bundle: codebase/runtime/mediator-legal_authority_hooks

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-223 Review swallowed exception path in mediator/legal_authority_hooks.py:1264

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/legal_authority_hooks.py
- Validation: python3 -m py_compile mediator/legal_authority_hooks.py
- Bundle: codebase/runtime/mediator-legal_authority_hooks
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-legal_authority_hooks.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-legal_authority_hooks
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/legal_authority_hooks.py
- AST symbols: __init__, _attach_treatment_payloads, _authority_record_from_row, _build_authority_provenance_metadata, _build_rule_candidate_summary, _build_treatment_records, _build_treatment_summary, _check_availability, _check_duckdb_availability, _classify_rule_candidate_type, _clone_provenance_record, _collect_search_diagnostics, _dedupe_authority_rows, _extract_authority_graph, _extract_cfr_sections, _extract_rule_candidates, _filter_regulation_results, _find_existing_authority_record, _generate_authority_recommendations, _generate_search_terms, _get_authority_rule_candidates, _get_authority_treatments, _get_default_db_path, _http_get_json, _http_get_text, _init_web_archiving, _initialize_schema, _log_hf_coverage_warning, _merge_handoff_into_provenance_record, _normalize_authority_fact_row, _normalize_courtlistener_result, _normalize_ecfr_result, _normalize_search_programs, _parse_authority_text, _prepare_duckdb_path, _query_terms, _resolve_artifact_identity, _resolve_claim_element, _rule_candidate_confidence, _search_agency_guidance_fallback, _search_courtlistener_fallback, _search_ecfr_fallback, _search_federal_statutes_fallback, _search_oregon_statutes_fallback, _split_rule_candidate_sentences, _store_authority_chunks, _store_authority_facts, _store_authority_graph, _store_authority_rule_candidates, _store_authority_treatments, _strip_html, _text_overlap_score, add authorities bulk, add authority, add_authorities_bulk, add_authority, analyze authorities for claim, analyze_authorities_for_claim, attach treatment payloads, authority record from row, build authority provenance metadata, build rule candidate summary, build search programs, build treatment records, build treatment summary, build_search_programs, check availability, check duckdb availability, claim support review, claim support review merge intake summary handoff metadata, claim_support_review, claim_support_review._merge_intake_summary_handoff_metadata, classify rule candidate type, clone provenance record, collect search diagnostics, datetime, datetime datetime, datetime.datetime, dedupe authority rows, duckdb
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-legal_authority_hooks
- Missing evidence: Review swallowed exception path in mediator/legal_authority_hooks.py:1264
- Merge key: codebase/runtime/mediator-legal_authority_hooks
- Merge family: mediator/legal_authority_hooks.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 6e8c1ae9d9783384
- Acceptance: Codebase scan filed this finding from mediator/legal_authority_hooks.py:1264. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-223-codebase-scan-6e8c1ae9d978.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-224 Review swallowed exception path in mediator/legal_authority_hooks.py:1318

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/legal_authority_hooks.py
- Validation: python3 -m py_compile mediator/legal_authority_hooks.py
- Bundle: codebase/runtime/mediator-legal_authority_hooks
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-legal_authority_hooks.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-legal_authority_hooks
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/legal_authority_hooks.py
- AST symbols: __init__, _attach_treatment_payloads, _authority_record_from_row, _build_authority_provenance_metadata, _build_rule_candidate_summary, _build_treatment_records, _build_treatment_summary, _check_availability, _check_duckdb_availability, _classify_rule_candidate_type, _clone_provenance_record, _collect_search_diagnostics, _dedupe_authority_rows, _extract_authority_graph, _extract_cfr_sections, _extract_rule_candidates, _filter_regulation_results, _find_existing_authority_record, _generate_authority_recommendations, _generate_search_terms, _get_authority_rule_candidates, _get_authority_treatments, _get_default_db_path, _http_get_json, _http_get_text, _init_web_archiving, _initialize_schema, _log_hf_coverage_warning, _merge_handoff_into_provenance_record, _normalize_authority_fact_row, _normalize_courtlistener_result, _normalize_ecfr_result, _normalize_search_programs, _parse_authority_text, _prepare_duckdb_path, _query_terms, _resolve_artifact_identity, _resolve_claim_element, _rule_candidate_confidence, _search_agency_guidance_fallback, _search_courtlistener_fallback, _search_ecfr_fallback, _search_federal_statutes_fallback, _search_oregon_statutes_fallback, _split_rule_candidate_sentences, _store_authority_chunks, _store_authority_facts, _store_authority_graph, _store_authority_rule_candidates, _store_authority_treatments, _strip_html, _text_overlap_score, add authorities bulk, add authority, add_authorities_bulk, add_authority, analyze authorities for claim, analyze_authorities_for_claim, attach treatment payloads, authority record from row, build authority provenance metadata, build rule candidate summary, build search programs, build treatment records, build treatment summary, build_search_programs, check availability, check duckdb availability, claim support review, claim support review merge intake summary handoff metadata, claim_support_review, claim_support_review._merge_intake_summary_handoff_metadata, classify rule candidate type, clone provenance record, collect search diagnostics, datetime, datetime datetime, datetime.datetime, dedupe authority rows, duckdb
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-legal_authority_hooks
- Missing evidence: Review swallowed exception path in mediator/legal_authority_hooks.py:1318
- Merge key: codebase/runtime/mediator-legal_authority_hooks
- Merge family: mediator/legal_authority_hooks.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 64f50cf3d4f3eeb8
- Acceptance: Codebase scan filed this finding from mediator/legal_authority_hooks.py:1318. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-224-codebase-scan-64f50cf3d4f3.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-225 Review swallowed exception path in mediator/legal_authority_hooks.py:2612

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/legal_authority_hooks.py
- Validation: python3 -m py_compile mediator/legal_authority_hooks.py
- Bundle: codebase/runtime/mediator-legal_authority_hooks
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-legal_authority_hooks.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-legal_authority_hooks
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/legal_authority_hooks.py
- AST symbols: __init__, _attach_treatment_payloads, _authority_record_from_row, _build_authority_provenance_metadata, _build_rule_candidate_summary, _build_treatment_records, _build_treatment_summary, _check_availability, _check_duckdb_availability, _classify_rule_candidate_type, _clone_provenance_record, _collect_search_diagnostics, _dedupe_authority_rows, _extract_authority_graph, _extract_cfr_sections, _extract_rule_candidates, _filter_regulation_results, _find_existing_authority_record, _generate_authority_recommendations, _generate_search_terms, _get_authority_rule_candidates, _get_authority_treatments, _get_default_db_path, _http_get_json, _http_get_text, _init_web_archiving, _initialize_schema, _log_hf_coverage_warning, _merge_handoff_into_provenance_record, _normalize_authority_fact_row, _normalize_courtlistener_result, _normalize_ecfr_result, _normalize_search_programs, _parse_authority_text, _prepare_duckdb_path, _query_terms, _resolve_artifact_identity, _resolve_claim_element, _rule_candidate_confidence, _search_agency_guidance_fallback, _search_courtlistener_fallback, _search_ecfr_fallback, _search_federal_statutes_fallback, _search_oregon_statutes_fallback, _split_rule_candidate_sentences, _store_authority_chunks, _store_authority_facts, _store_authority_graph, _store_authority_rule_candidates, _store_authority_treatments, _strip_html, _text_overlap_score, add authorities bulk, add authority, add_authorities_bulk, add_authority, analyze authorities for claim, analyze_authorities_for_claim, attach treatment payloads, authority record from row, build authority provenance metadata, build rule candidate summary, build search programs, build treatment records, build treatment summary, build_search_programs, check availability, check duckdb availability, claim support review, claim support review merge intake summary handoff metadata, claim_support_review, claim_support_review._merge_intake_summary_handoff_metadata, classify rule candidate type, clone provenance record, collect search diagnostics, datetime, datetime datetime, datetime.datetime, dedupe authority rows, duckdb
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-legal_authority_hooks
- Missing evidence: Review swallowed exception path in mediator/legal_authority_hooks.py:2612
- Merge key: codebase/runtime/mediator-legal_authority_hooks
- Merge family: mediator/legal_authority_hooks.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 1cc8e01bb3ed16d4
- Acceptance: Codebase scan filed this finding from mediator/legal_authority_hooks.py:2612. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-225-codebase-scan-1cc8e01bb3ed.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
