# Codebase Bundle: codebase/runtime/mediator-integrations-graph_tools

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-217 Review swallowed exception path in mediator/integrations/graph_tools.py:133

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/integrations/graph_tools.py
- Validation: python3 -m py_compile mediator/integrations/graph_tools.py
- Bundle: codebase/runtime/mediator-integrations-graph_tools
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-integrations-graph_tools.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-integrations-graph_tools
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/integrations/graph_tools.py
- AST symbols: _extract_readiness_context, _make_id, _tokenize, augment normalized records, augment_normalized_records, build evidence payloads, build_evidence_payloads, complaint phases, complaint phases complaintphase, complaint phases nodetype, complaint_phases, complaint_phases.complaintphase, complaint_phases.nodetype, extract graph terms, extract readiness context, extract_graph_terms, graphawareretrievalreranker, graphawareretrievalreranker augment normalized records, graphawareretrievalreranker extract graph terms, graphawareretrievalreranker extract readiness context, graphawareretrievalreranker should apply canary, graphawareretrievalreranker tokenize, graphawareretrievalreranker._extract_readiness_context, graphawareretrievalreranker._tokenize, graphawareretrievalreranker.augment_normalized_records, graphawareretrievalreranker.extract_graph_terms, graphawareretrievalreranker.should_apply_canary, graphretrievalaugmentor, graphretrievalaugmentor build evidence payloads, graphretrievalaugmentor make id, graphretrievalaugmentor._make_id, graphretrievalaugmentor.build_evidence_payloads, hashlib, make id, re, should apply canary, should_apply_canary, time, tokenize, typing, typing any, typing dict, typing list, typing set, typing.any, typing.dict, typing.list, typing.set
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-integrations-graph_tools
- Missing evidence: Review swallowed exception path in mediator/integrations/graph_tools.py:133
- Merge key: codebase/runtime/mediator-integrations-graph_tools
- Merge family: mediator/integrations/graph_tools.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: bc98904588161cae
- Acceptance: Codebase scan filed this finding from mediator/integrations/graph_tools.py:133. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-217-codebase-scan-bc9890458816.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-218 Review swallowed exception path in mediator/integrations/graph_tools.py:154

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/integrations/graph_tools.py
- Validation: python3 -m py_compile mediator/integrations/graph_tools.py
- Bundle: codebase/runtime/mediator-integrations-graph_tools
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-integrations-graph_tools.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-integrations-graph_tools
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/integrations/graph_tools.py
- AST symbols: _extract_readiness_context, _make_id, _tokenize, augment normalized records, augment_normalized_records, build evidence payloads, build_evidence_payloads, complaint phases, complaint phases complaintphase, complaint phases nodetype, complaint_phases, complaint_phases.complaintphase, complaint_phases.nodetype, extract graph terms, extract readiness context, extract_graph_terms, graphawareretrievalreranker, graphawareretrievalreranker augment normalized records, graphawareretrievalreranker extract graph terms, graphawareretrievalreranker extract readiness context, graphawareretrievalreranker should apply canary, graphawareretrievalreranker tokenize, graphawareretrievalreranker._extract_readiness_context, graphawareretrievalreranker._tokenize, graphawareretrievalreranker.augment_normalized_records, graphawareretrievalreranker.extract_graph_terms, graphawareretrievalreranker.should_apply_canary, graphretrievalaugmentor, graphretrievalaugmentor build evidence payloads, graphretrievalaugmentor make id, graphretrievalaugmentor._make_id, graphretrievalaugmentor.build_evidence_payloads, hashlib, make id, re, should apply canary, should_apply_canary, time, tokenize, typing, typing any, typing dict, typing list, typing set, typing.any, typing.dict, typing.list, typing.set
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-integrations-graph_tools
- Missing evidence: Review swallowed exception path in mediator/integrations/graph_tools.py:154
- Merge key: codebase/runtime/mediator-integrations-graph_tools
- Merge family: mediator/integrations/graph_tools.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: b6c5f32da80aa84b
- Acceptance: Codebase scan filed this finding from mediator/integrations/graph_tools.py:154. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-218-codebase-scan-b6c5f32da80a.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-219 Review swallowed exception path in mediator/integrations/graph_tools.py:187

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/integrations/graph_tools.py
- Validation: python3 -m py_compile mediator/integrations/graph_tools.py
- Bundle: codebase/runtime/mediator-integrations-graph_tools
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-integrations-graph_tools.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-integrations-graph_tools
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/integrations/graph_tools.py
- AST symbols: _extract_readiness_context, _make_id, _tokenize, augment normalized records, augment_normalized_records, build evidence payloads, build_evidence_payloads, complaint phases, complaint phases complaintphase, complaint phases nodetype, complaint_phases, complaint_phases.complaintphase, complaint_phases.nodetype, extract graph terms, extract readiness context, extract_graph_terms, graphawareretrievalreranker, graphawareretrievalreranker augment normalized records, graphawareretrievalreranker extract graph terms, graphawareretrievalreranker extract readiness context, graphawareretrievalreranker should apply canary, graphawareretrievalreranker tokenize, graphawareretrievalreranker._extract_readiness_context, graphawareretrievalreranker._tokenize, graphawareretrievalreranker.augment_normalized_records, graphawareretrievalreranker.extract_graph_terms, graphawareretrievalreranker.should_apply_canary, graphretrievalaugmentor, graphretrievalaugmentor build evidence payloads, graphretrievalaugmentor make id, graphretrievalaugmentor._make_id, graphretrievalaugmentor.build_evidence_payloads, hashlib, make id, re, should apply canary, should_apply_canary, time, tokenize, typing, typing any, typing dict, typing list, typing set, typing.any, typing.dict, typing.list, typing.set
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-integrations-graph_tools
- Missing evidence: Review swallowed exception path in mediator/integrations/graph_tools.py:187
- Merge key: codebase/runtime/mediator-integrations-graph_tools
- Merge family: mediator/integrations/graph_tools.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 35764e29494443fb
- Acceptance: Codebase scan filed this finding from mediator/integrations/graph_tools.py:187. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-219-codebase-scan-35764e294944.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-220 Review swallowed exception path in mediator/integrations/graph_tools.py:209

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/integrations/graph_tools.py
- Validation: python3 -m py_compile mediator/integrations/graph_tools.py
- Bundle: codebase/runtime/mediator-integrations-graph_tools
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-integrations-graph_tools.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-integrations-graph_tools
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/integrations/graph_tools.py
- AST symbols: _extract_readiness_context, _make_id, _tokenize, augment normalized records, augment_normalized_records, build evidence payloads, build_evidence_payloads, complaint phases, complaint phases complaintphase, complaint phases nodetype, complaint_phases, complaint_phases.complaintphase, complaint_phases.nodetype, extract graph terms, extract readiness context, extract_graph_terms, graphawareretrievalreranker, graphawareretrievalreranker augment normalized records, graphawareretrievalreranker extract graph terms, graphawareretrievalreranker extract readiness context, graphawareretrievalreranker should apply canary, graphawareretrievalreranker tokenize, graphawareretrievalreranker._extract_readiness_context, graphawareretrievalreranker._tokenize, graphawareretrievalreranker.augment_normalized_records, graphawareretrievalreranker.extract_graph_terms, graphawareretrievalreranker.should_apply_canary, graphretrievalaugmentor, graphretrievalaugmentor build evidence payloads, graphretrievalaugmentor make id, graphretrievalaugmentor._make_id, graphretrievalaugmentor.build_evidence_payloads, hashlib, logging, make id, re, should apply canary, should_apply_canary, time, tokenize, typing, typing any, typing dict, typing list, typing set, typing.any, typing.dict, typing.list, typing.set
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-integrations-graph_tools
- Missing evidence: Review swallowed exception path in mediator/integrations/graph_tools.py:209
- Merge key: codebase/runtime/mediator-integrations-graph_tools
- Merge family: mediator/integrations/graph_tools.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 3781a2e00c210959
- Acceptance: Codebase scan filed this finding from mediator/integrations/graph_tools.py:209. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-220-codebase-scan-3781a2e00c21.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-221 Review swallowed exception path in mediator/integrations/graph_tools.py:223

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/integrations/graph_tools.py
- Validation: python3 -m py_compile mediator/integrations/graph_tools.py
- Bundle: codebase/runtime/mediator-integrations-graph_tools
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-integrations-graph_tools.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-integrations-graph_tools
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/integrations/graph_tools.py
- AST symbols: _extract_readiness_context, _make_id, _tokenize, augment normalized records, augment_normalized_records, build evidence payloads, build_evidence_payloads, complaint phases, complaint phases complaintphase, complaint phases nodetype, complaint_phases, complaint_phases.complaintphase, complaint_phases.nodetype, extract graph terms, extract readiness context, extract_graph_terms, graphawareretrievalreranker, graphawareretrievalreranker augment normalized records, graphawareretrievalreranker extract graph terms, graphawareretrievalreranker extract readiness context, graphawareretrievalreranker should apply canary, graphawareretrievalreranker tokenize, graphawareretrievalreranker._extract_readiness_context, graphawareretrievalreranker._tokenize, graphawareretrievalreranker.augment_normalized_records, graphawareretrievalreranker.extract_graph_terms, graphawareretrievalreranker.should_apply_canary, graphretrievalaugmentor, graphretrievalaugmentor build evidence payloads, graphretrievalaugmentor make id, graphretrievalaugmentor._make_id, graphretrievalaugmentor.build_evidence_payloads, hashlib, logging, make id, re, should apply canary, should_apply_canary, time, tokenize, typing, typing any, typing dict, typing list, typing set, typing.any, typing.dict, typing.list, typing.set
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-integrations-graph_tools
- Missing evidence: Review swallowed exception path in mediator/integrations/graph_tools.py:223
- Merge key: codebase/runtime/mediator-integrations-graph_tools
- Merge family: mediator/integrations/graph_tools.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 2986b4a153d97f2c
- Acceptance: Codebase scan filed this finding from mediator/integrations/graph_tools.py:223. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-221-codebase-scan-2986b4a153d9.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-222 Review swallowed exception path in mediator/integrations/graph_tools.py:236

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/integrations/graph_tools.py
- Validation: python3 -m py_compile mediator/integrations/graph_tools.py
- Bundle: codebase/runtime/mediator-integrations-graph_tools
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-integrations-graph_tools.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-integrations-graph_tools
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/integrations/graph_tools.py
- AST symbols: _extract_readiness_context, _make_id, _tokenize, augment normalized records, augment_normalized_records, build evidence payloads, build_evidence_payloads, complaint phases, complaint phases complaintphase, complaint phases nodetype, complaint_phases, complaint_phases.complaintphase, complaint_phases.nodetype, extract graph terms, extract readiness context, extract_graph_terms, graphawareretrievalreranker, graphawareretrievalreranker augment normalized records, graphawareretrievalreranker extract graph terms, graphawareretrievalreranker extract readiness context, graphawareretrievalreranker should apply canary, graphawareretrievalreranker tokenize, graphawareretrievalreranker._extract_readiness_context, graphawareretrievalreranker._tokenize, graphawareretrievalreranker.augment_normalized_records, graphawareretrievalreranker.extract_graph_terms, graphawareretrievalreranker.should_apply_canary, graphretrievalaugmentor, graphretrievalaugmentor build evidence payloads, graphretrievalaugmentor make id, graphretrievalaugmentor._make_id, graphretrievalaugmentor.build_evidence_payloads, hashlib, logging, make id, re, should apply canary, should_apply_canary, time, tokenize, typing, typing any, typing dict, typing list, typing set, typing.any, typing.dict, typing.list, typing.set
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-integrations-graph_tools
- Missing evidence: Review swallowed exception path in mediator/integrations/graph_tools.py:236
- Merge key: codebase/runtime/mediator-integrations-graph_tools
- Merge family: mediator/integrations/graph_tools.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 04c62dea806c9d61
- Acceptance: Codebase scan filed this finding from mediator/integrations/graph_tools.py:236. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-222-codebase-scan-04c62dea806c.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
