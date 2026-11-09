# Objective Bundle: refactor/g3/g3-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-9: REF-009 Standardize capability status and degraded-reason payloads across adapters

## REF-009 Standardize capability status and degraded-reason payloads across adapters

- Status: completed
- Completion: manual
- Priority: P0
- Track: G3
- Depends on: 
- Outputs: integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py
- Validation: python -m pytest tests/test_ipfs_adapter_layer.py -q
- Bundle: refactor/g3/g3-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G3.S1
- Missing evidence: The existing backlog identifies adapter capability reporting as incomplete.
- AST symbols: get_ipfs_datasets_capabilities, summarize_ipfs_datasets_capabilities, summarize_ipfs_datasets_capability_report, summarize_ipfs_datasets_startup_payload, module_map, capabilities, available_capabilities, degraded_capabilities, capability_report, module_path, degraded_reason, family, RepoPaths, ImportFailure, get_repo_paths, _matches_package_root, _package_dir_for_root, _loaded_package_matches, _prime_repo_package, ensure_import_paths, _should_retry_with_repo_paths, _build_import_failure, import_failure_message, import_failure_type, import_module_optional, import_attr_optional, run_async_compat, __str__, repo_root, ipfs_datasets_repo
- Merge key: refactor/g3/g3-s1
- Candidate kind: seed
- Todo vector key: ref-009-standardizecapabilitystatusanddegraded-reasonpay
- Acceptance: All adapter groups report stable keys.; Missing optional extras produce actionable reasons.

- [x] Task checkbox-10: REF-010 Promote document parsing into a shared ingestion contract

## REF-010 Promote document parsing into a shared ingestion contract

- Status: completed
- Completion: manual
- Priority: P0
- Track: G3
- Depends on: 
- Outputs: integrations/ipfs_datasets/documents.py, mediator/evidence_hooks.py
- Validation: python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q
- Bundle: refactor/g3/g3-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G3.S1
- Missing evidence: Document parsing is still fallback-oriented and should be reusable across ingestion paths.
- AST symbols: DOCUMENTS_AVAILABLE, DOCUMENTS_ERROR, PARSER_VERSION, _TEXT_LIKE_MIME_PREFIXES, _PARSEABLE_MIME_TYPES, _PARSEABLE_EXTENSIONS, _build_parse_summary, _build_transform_lineage, _determine_normalization_label, _estimate_page_count, _compute_parse_quality, _decode_text_fallback, _is_mostly_text, _normalize_whitespace, _strip_html, _looks_like_html, _looks_like_rtf, _looks_like_email, _detect_text_input_format, _strip_rtf, _extract_email_text, _extract_docx_text, _extract_pdf_text_fallback, detect_document_input_format, should_parse_document_input, _split_into_paragraphs, _guess_mime_type, chunk_text, parse_document_text, parse_document_bytes
- Merge key: refactor/g3/g3-s1
- Candidate kind: seed
- Todo vector key: ref-010-promotedocumentparsingintoasharedingestioncontra
- Acceptance: Evidence, authority, and web ingestion can call one parse contract.; Fallback mode preserves current behavior.
