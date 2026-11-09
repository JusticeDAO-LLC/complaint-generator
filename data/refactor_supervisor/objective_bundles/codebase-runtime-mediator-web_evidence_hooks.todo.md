# Codebase Bundle: codebase/runtime/mediator-web_evidence_hooks

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-226 Review swallowed exception path in mediator/web_evidence_hooks.py:498

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/web_evidence_hooks.py
- Validation: python3 -m py_compile mediator/web_evidence_hooks.py
- Bundle: codebase/runtime/mediator-web_evidence_hooks
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-web_evidence_hooks.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-web_evidence_hooks
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/web_evidence_hooks.py
- AST symbols: __init__, _accumulate_parse_detail, _add, _aggregate_graph_support_metrics, _build_evidence_context, _build_support_bundle, _build_web_evidence_filename, _build_web_evidence_lineage_context, _build_web_evidence_parse_metadata, _build_web_evidence_payload, _callable_is_mocked, _empty_storage_summary, _enrich_storage_result_parse_contract, _extract_parse_detail, _generate_search_keywords, _get_search_hook, _init_search_tools, _normalize_results, _seed_daemon_tactics, _store_evidence_items, _summarize_claim_coverage_claim, _summarize_follow_up_execution_claim, _summarize_follow_up_plan_claim, accumulate parse detail, add, aggregate graph support metrics, build evidence context, build support bundle, build web evidence filename, build web evidence lineage context, build web evidence parse metadata, build web evidence payload, callable is mocked, claim support review, claim support review build confirmed intake summary handoff metadata, claim support review summarize claim reasoning review, claim support review summarize claim support snapshot lifecycle, claim support review summarize follow up execution claim, claim support review summarize follow up history claim, claim support review summarize follow up plan claim, claim_support_review, claim_support_review._build_confirmed_intake_summary_handoff_metadata, claim_support_review._summarize_follow_up_execution_claim, claim_support_review._summarize_follow_up_plan_claim, claim_support_review.summarize_claim_reasoning_review, claim_support_review.summarize_claim_support_snapshot_lifecycle, claim_support_review.summarize_follow_up_history_claim, complaint phases, complaint phases complaintphase, complaint_phases, complaint_phases.complaintphase, datetime, datetime datetime, datetime.datetime, discover and store evidence, discover evidence for case, discover_and_store_evidence, discover_evidence_for_case, empty storage summary, enrich storage result parse contract, extract parse detail, generate search keywords, get capability registry, get search hook, get_capability_registry, init, init search tools, integrations, integrations graphawareretrievalreranker, integrations integrationfeatureflags, integrations ipfs datasets documents, integrations ipfs datasets documents detect document input format, integrations ipfs datasets provenance, integrations ipfs datasets provenance build document parse contract, integrations ipfs datasets provenance enrich document parse, integrations ipfs datasets scraper daemon, integrations ipfs datasets scraper daemon scraperdaemon, integrations ipfs datasets scraper daemon scraperdaemonconfig, integrations ipfs datasets scraper daemon scrapertactic, integrations ipfs datasets search
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-web_evidence_hooks
- Missing evidence: Review swallowed exception path in mediator/web_evidence_hooks.py:498
- Merge key: codebase/runtime/mediator-web_evidence_hooks
- Merge family: mediator/web_evidence_hooks.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 1296d7ba66dc00cc
- Acceptance: Codebase scan filed this finding from mediator/web_evidence_hooks.py:498. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-226-codebase-scan-1296d7ba66dc.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
