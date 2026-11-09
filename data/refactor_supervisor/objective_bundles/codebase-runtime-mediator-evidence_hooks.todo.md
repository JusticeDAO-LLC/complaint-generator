# Codebase Bundle: codebase/runtime/mediator-evidence_hooks

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-215 Review swallowed exception path in mediator/evidence_hooks.py:1398

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, mediator/evidence_hooks.py
- Validation: python3 -m py_compile mediator/evidence_hooks.py
- Bundle: codebase/runtime/mediator-evidence_hooks
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-mediator-evidence_hooks.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/mediator-evidence_hooks
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: mediator/evidence_hooks.py
- AST symbols: __init__, _check_duckdb_availability, _check_ipfs_availability, _find_existing_evidence_record, _generate_evidence_recommendations, _get_default_db_path, _initialize_schema, _normalize_evidence_fact_row, _prepare_duckdb_path, _resolve_artifact_identity, _serialize_scraper_queue_row, _should_parse_evidence, _store_document_chunks, _store_document_facts, _store_document_graph, add evidence record, add_evidence_record, analyze evidence for claim, analyze_evidence_for_claim, as dict, as_dict, check duckdb availability, check ipfs availability, claim next scraper job, claim support review, claim support review merge intake summary handoff metadata, claim_next_scraper_job, claim_support_review, claim_support_review._merge_intake_summary_handoff_metadata, complete scraper job, complete_scraper_job, datetime, datetime datetime, datetime timedelta, datetime utc, datetime.datetime, datetime.timedelta, datetime.utc, degradedevidenceresults, degradedevidenceresults as dict, degradedevidenceresults init, degradedevidenceresults.__init__, degradedevidenceresults.as_dict, duckdb, enqueue scraper job, enqueue_scraper_job, evidenceanalysishook, evidenceanalysishook analyze evidence for claim, evidenceanalysishook generate evidence recommendations, evidenceanalysishook init, evidenceanalysishook.__init__, evidenceanalysishook._generate_evidence_recommendations, evidenceanalysishook.analyze_evidence_for_claim, evidencehookerror, evidencepersistenceerror, evidenceretrievalerror, evidencestatehook, evidencestatehook add evidence record, evidencestatehook check duckdb availability, evidencestatehook claim next scraper job, evidencestatehook complete scraper job, evidencestatehook enqueue scraper job, evidencestatehook find existing evidence record, evidencestatehook get default db path, evidencestatehook get evidence by cid, evidencestatehook get evidence chunks, evidencestatehook get evidence facts, evidencestatehook get evidence graph, evidencestatehook get evidence statistics, evidencestatehook get scraper queue, evidencestatehook get scraper queue job, evidencestatehook get scraper run details, evidencestatehook get scraper runs, evidencestatehook get scraper tactic performance, evidencestatehook get user evidence, evidencestatehook init, evidencestatehook initialize schema, evidencestatehook persist scraper run, evidencestatehook prepare duckdb path, evidencestatehook serialize scraper queue row
- AST symbol scope: file
- Goal id: codebase/runtime/mediator-evidence_hooks
- Missing evidence: Review swallowed exception path in mediator/evidence_hooks.py:1398
- Merge key: codebase/runtime/mediator-evidence_hooks
- Merge family: mediator/evidence_hooks.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 262ec5d876de373d
- Acceptance: Codebase scan filed this finding from mediator/evidence_hooks.py:1398. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-215-codebase-scan-262ec5d876de.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
