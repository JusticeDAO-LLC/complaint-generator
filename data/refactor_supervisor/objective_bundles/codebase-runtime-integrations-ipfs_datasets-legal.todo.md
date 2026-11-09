# Codebase Bundle: codebase/runtime/integrations-ipfs_datasets-legal

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-121 Review swallowed exception path in integrations/ipfs_datasets/legal.py:98

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/legal.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/legal.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-legal
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-legal.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-legal
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/legal.py
- AST symbols: __future__, __future__.annotations, _attach_hf_corpus_metadata, _build_hf_search_diagnostic, _build_query_vector, _coerce_vector_payload, _extract_payload_items, _import_attr_from_candidates, _merge_nested_case_fields, _normalize_authority, _normalize_payload_results, _normalize_scraped_authority, _resolve_state_code, _search_hf_parquet_text, _search_scraped_records, _set_hf_search_warning, _set_last_legal_search_diagnostic, attach hf corpus metadata, build hf search diagnostic, build query vector, coerce vector payload, duckdb, extract payload items, future, future annotations, get last legal search diagnostic, get_last_legal_search_diagnostic, huggingface hub, huggingface hub hf hub download, huggingface_hub, huggingface_hub.hf_hub_download, import attr from candidates, loader, loader import attr optional, loader run async compat, loader.import_attr_optional, loader.run_async_compat, merge nested case fields, normalize authority, normalize payload results, normalize scraped authority, pyarrow parquet, pyarrow.parquet, resolve state code, search federal register, search hf parquet text, search recap documents, search scraped records, search state administrative rules, search state laws, search us code, search_federal_register, search_recap_documents, search_state_administrative_rules, search_state_laws, search_us_code, set hf search warning, set last legal search diagnostic, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing list, typing optional, typing.any, typing.dict, typing.list, typing.optional, vector store, vector store embed text, vector store embeddings available, vector store get embeddings router, vector_store, vector_store.embed_text, vector_store.embeddings_available, vector_store.get_embeddings_router
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-legal
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/legal.py:98
- Merge key: codebase/runtime/integrations-ipfs_datasets-legal
- Merge family: integrations/ipfs_datasets/legal.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 11b094c1fe49382a
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/legal.py:98. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-121-codebase-scan-11b094c1fe49.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-122 Review swallowed exception path in integrations/ipfs_datasets/legal.py:112

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/legal.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/legal.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-legal
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-legal.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-legal
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/legal.py
- AST symbols: __future__, __future__.annotations, _attach_hf_corpus_metadata, _build_hf_search_diagnostic, _build_query_vector, _coerce_vector_payload, _extract_payload_items, _import_attr_from_candidates, _merge_nested_case_fields, _normalize_authority, _normalize_payload_results, _normalize_scraped_authority, _resolve_state_code, _search_hf_parquet_text, _search_scraped_records, _set_hf_search_warning, _set_last_legal_search_diagnostic, attach hf corpus metadata, build hf search diagnostic, build query vector, coerce vector payload, duckdb, extract payload items, future, future annotations, get last legal search diagnostic, get_last_legal_search_diagnostic, huggingface hub, huggingface hub hf hub download, huggingface_hub, huggingface_hub.hf_hub_download, import attr from candidates, loader, loader import attr optional, loader run async compat, loader.import_attr_optional, loader.run_async_compat, merge nested case fields, normalize authority, normalize payload results, normalize scraped authority, pyarrow parquet, pyarrow.parquet, resolve state code, search federal register, search hf parquet text, search recap documents, search scraped records, search state administrative rules, search state laws, search us code, search_federal_register, search_recap_documents, search_state_administrative_rules, search_state_laws, search_us_code, set hf search warning, set last legal search diagnostic, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing list, typing optional, typing.any, typing.dict, typing.list, typing.optional, vector store, vector store embed text, vector store embeddings available, vector store get embeddings router, vector_store, vector_store.embed_text, vector_store.embeddings_available, vector_store.get_embeddings_router
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-legal
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/legal.py:112
- Merge key: codebase/runtime/integrations-ipfs_datasets-legal
- Merge family: integrations/ipfs_datasets/legal.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: a99172acf7bba4f1
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/legal.py:112. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-122-codebase-scan-a99172acf7bb.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-123 Review swallowed exception path in integrations/ipfs_datasets/legal.py:662

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/legal.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/legal.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-legal
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-legal.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-legal
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/legal.py
- AST symbols: __future__, __future__.annotations, _attach_hf_corpus_metadata, _build_hf_search_diagnostic, _build_query_vector, _coerce_vector_payload, _extract_payload_items, _import_attr_from_candidates, _merge_nested_case_fields, _normalize_authority, _normalize_payload_results, _normalize_scraped_authority, _resolve_state_code, _search_hf_parquet_text, _search_scraped_records, _set_hf_search_warning, _set_last_legal_search_diagnostic, attach hf corpus metadata, build hf search diagnostic, build query vector, coerce vector payload, duckdb, extract payload items, future, future annotations, get last legal search diagnostic, get_last_legal_search_diagnostic, huggingface hub, huggingface hub hf hub download, huggingface_hub, huggingface_hub.hf_hub_download, import attr from candidates, loader, loader import attr optional, loader run async compat, loader.import_attr_optional, loader.run_async_compat, merge nested case fields, normalize authority, normalize payload results, normalize scraped authority, pyarrow parquet, pyarrow.parquet, resolve state code, search federal register, search hf parquet text, search recap documents, search scraped records, search state administrative rules, search state laws, search us code, search_federal_register, search_recap_documents, search_state_administrative_rules, search_state_laws, search_us_code, set hf search warning, set last legal search diagnostic, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing list, typing optional, typing.any, typing.dict, typing.list, typing.optional, vector store, vector store embed text, vector store embeddings available, vector store get embeddings router, vector_store, vector_store.embed_text, vector_store.embeddings_available, vector_store.get_embeddings_router
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-legal
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/legal.py:662
- Merge key: codebase/runtime/integrations-ipfs_datasets-legal
- Merge family: integrations/ipfs_datasets/legal.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 6e1fbcf47fed79d4
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/legal.py:662. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-123-codebase-scan-6e1fbcf47fed.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
