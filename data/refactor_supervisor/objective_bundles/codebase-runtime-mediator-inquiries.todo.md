# Codebase Bundle: codebase/runtime/mediator-inquiries

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-216 Review swallowed exception path in mediator/inquiries.py:446

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/inquiries.py
- Validation: python3 -m py_compile mediator/inquiries.py
- Bundle: codebase/runtime/mediator-inquiries
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-inquiries.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-inquiries
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/inquiries.py
- AST symbols: __init__, _build_gap_context, _build_index, _clean_question, _extract_questions, _find_unanswered, _index_for, _index_key, _infer_objectives_from_text, _intake_priority_sort_key, _match_intake_objectives, _merge_intake_priority, _normalize_question, _normalize_question_cached, _objectives_for_inquiry, _ordered_intake_objectives, _priority_rank, _register, _state_inquiries, _trim_question_prefix, answer, build gap context, build index, clean question, complaint phases, complaint phases complaintphase, complaint_phases, complaint_phases.complaintphase, explain inquiry, explain_inquiry, extract questions, find unanswered, functools, functools lru cache, functools.lru_cache, generate, get next, get_next, index for, index key, infer objectives from text, init, inquiries, inquiries answer, inquiries build gap context, inquiries build index, inquiries clean question, inquiries explain inquiry, inquiries extract questions, inquiries find unanswered, inquiries generate, inquiries get next, inquiries index for, inquiries index key, inquiries infer objectives from text, inquiries init, inquiries intake priority sort key, inquiries is complete, inquiries match intake objectives, inquiries merge intake priority, inquiries merge legal questions, inquiries normalize question, inquiries objectives for inquiry, inquiries ordered intake objectives, inquiries priority rank, inquiries register, inquiries same question, inquiries state inquiries, inquiries trim question prefix, inquiries.__init__, inquiries._build_gap_context, inquiries._build_index, inquiries._clean_question, inquiries._extract_questions, inquiries._find_unanswered, inquiries._index_for, inquiries._index_key, inquiries._infer_objectives_from_text, inquiries._intake_priority_sort_key, inquiries._match_intake_objectives
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-inquiries
- Missing evidence: Review swallowed exception path in mediator/inquiries.py:446
- Merge key: codebase/runtime/mediator-inquiries
- Merge family: mediator/inquiries.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 038dc49c2e81b4da
- Acceptance: Codebase scan filed this finding from mediator/inquiries.py:446. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-216-codebase-scan-038dc49c2e81.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
