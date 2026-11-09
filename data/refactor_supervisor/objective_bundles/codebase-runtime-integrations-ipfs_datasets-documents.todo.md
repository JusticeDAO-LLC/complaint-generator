# Codebase Bundle: codebase/runtime/integrations-ipfs_datasets-documents

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-119 Review swallowed exception path in integrations/ipfs_datasets/documents.py:1148

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/documents.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/documents.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-documents
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-documents.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-documents
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/documents.py
- AST symbols: __future__, __future__.annotations, _annotate_chunk_metadata, _build_parse_summary, _build_transform_lineage, _chunk_page_index, _compute_parse_quality, _decode_text_fallback, _detect_text_input_format, _determine_normalization_label, _ensure_output_dir, _estimate_page_count, _extract_docx_text, _extract_email_text, _extract_pdf_text_fallback, _guess_mime_type, _is_mostly_text, _looks_like_email, _looks_like_html, _looks_like_rtf, _materialize_parse_record, _merge_parse_context, _normalize_whitespace, _split_into_paragraphs, _stable_record_id, _strip_html, _strip_rtf, annotate chunk metadata, build parse summary, build transform lineage, chunk page index, chunk text, chunk_text, compute parse quality, decode text fallback, detect document input format, detect text input format, detect_document_input_format, determine normalization label, email parser, email parser bytesparser, email policy, email.parser, email.parser.bytesparser, email.policy, ensure output dir, estimate page count, extract docx text, extract email text, extract pdf text fallback, extract text content, extract_text_content, future, future annotations, guess mime type, hashlib, html, html unescape, html.unescape, ingest download manifest, ingest local document, ingest_download_manifest, ingest_local_document, io, io bytesio, io.bytesio, is mostly text, json, loader, loader import attr optional, loader import module optional, loader.import_attr_optional, loader.import_module_optional, looks like email, looks like html, looks like rtf, materialize parse record, merge parse context, mimetypes, normalize whitespace
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-documents
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/documents.py:1148
- Merge key: codebase/runtime/integrations-ipfs_datasets-documents
- Merge family: integrations/ipfs_datasets/documents.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 13e95d4f65f78f4e
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/documents.py:1148. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-119-codebase-scan-13e95d4f65f7.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
