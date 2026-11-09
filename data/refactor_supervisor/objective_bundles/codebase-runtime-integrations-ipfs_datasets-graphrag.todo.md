# Codebase Bundle: codebase/runtime/integrations-ipfs_datasets-graphrag

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-120 Review swallowed exception path in integrations/ipfs_datasets/graphrag.py:128

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/graphrag.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/graphrag.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-graphrag
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-graphrag.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-graphrag
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/graphrag.py
- AST symbols: __future__, __future__.annotations, _run_pdf_facade, analyze pdf relationships, analyze_pdf_relationships, batch process pdfs, batch_process_pdfs, build ontology, build_ontology, create ontology generator, create_ontology_generator, cross analyze pdf documents, cross_analyze_pdf_documents, extract pdf entities, extract_pdf_entities, future, future annotations, ingest pdf to graphrag, ingest_pdf_to_graphrag, loader, loader import attr optional, loader run async compat, loader.import_attr_optional, loader.run_async_compat, query pdf knowledge graph, query_pdf_knowledge_graph, run pdf facade, run refinement cycle, run_refinement_cycle, types, types with adapter metadata, types.with_adapter_metadata, typing, typing any, typing dict, typing optional, typing.any, typing.dict, typing.optional, validate ontology, validate_ontology
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-graphrag
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/graphrag.py:128
- Merge key: codebase/runtime/integrations-ipfs_datasets-graphrag
- Merge family: integrations/ipfs_datasets/graphrag.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 1026e36dfbd6f72b
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/graphrag.py:128. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-120-codebase-scan-1026e36dfbd6.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
