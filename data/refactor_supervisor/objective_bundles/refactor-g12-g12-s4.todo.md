# Objective Bundle: refactor/g12/g12-s4

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-287: REF-287 Generalize runtime MTL monitoring to supervisor event traces

## REF-287 Generalize runtime MTL monitoring to supervisor event traces

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-277, REF-279
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/runtime_temporal_monitor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_runtime_temporal_monitor.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_runtime_temporal_monitor.py -q
- Bundle: refactor/g12/g12-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S4
- Missing evidence: Offline plans and proofs need a bounded runtime conformance layer for actual daemon, lane, proof, validation, and merge events.
- AST symbols: _UNKNOWN_TASK, _UNKNOWN_LANE, _UNKNOWN_TREE, _UNKNOWN_EPOCH, _canonical_json, _identity, _text, _boolean, _first_text, _finite_nonnegative, _positive_int, _utc_now, _timestamp, _bounded_public, TemporalPropertyKind, MonitorVerdict, NoticeSeverity, NoticeCode, TemporalProperty, _default_properties, TemporalMonitorPolicy, RuntimeTemporalPolicy, TracePartition, TemporalPartitionKey, TemporalMonitorConfig, RuntimeTemporalMonitorConfig, NormalizedSupervisorEvent, MonitorNotice, TemporalCounterexample, RuntimeTemporalCounterexample
- Merge key: refactor/g12/g12-s4
- Candidate kind: seed
- Todo vector key: ref-287-generalizeruntimemtlmonitoringtosupervisoreventt
- Acceptance: Versioned temporal properties cover event ordering, lease expiration, no action after revocation or cancellation, proof-before-merge, bounded retry, eventual terminal status, and resource-release deadlines.; The monitor handles rotated logs, restart epochs, duplicate events, missing timestamps, and bounded out-of-order windows explicitly.; Violations emit durable counterexamples and reopen affected work; absence of observed violations is not promoted into a proof.; Streaming state is bounded and partitioned by task, lane, tree, and policy identity.

- [!] Task checkbox-288: REF-288 Normalize proof failures and traces into a counterexample knowledge graph

## REF-288 Normalize proof failures and traces into a counterexample knowledge graph

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-256, REF-280, REF-283, REF-287
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_counterexamples.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_counterexamples.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_counterexamples.py -q
- Bundle: refactor/g12/g12-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S4
- Missing evidence: Models should receive compact actionable counterexamples instead of raw solver, model-checker, or runtime transcripts.
- AST symbols: 
- Merge key: refactor/g12/g12-s4
- Candidate kind: seed
- Todo vector key: ref-288-normalizeprooffailuresandtracesintoacounterexamp
- Acceptance: A canonical IR represents SMT models and unsat cores, DCEC or TDFOL contradictions, TLA traces, protocol attacks, hypertraces, kernel errors, and runtime MTL violations.; Graph edges bind each counterexample to plans, tasks, AST scopes, assumptions, obligations, providers, receipts, and invalidated evidence.; Minimization, semantic deduplication, redaction, and byte limits run before persistence or prompt assembly.; Hidden witnesses, credentials, unrelated source, and unbounded prover output never enter a context capsule.

- [!] Task checkbox-289: REF-289 Generate bounded counterexample-guided plan repairs

## REF-289 Generate bounded counterexample-guided plan repairs

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-270, REF-278, REF-288
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_replanner.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_replanner.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_replanner.py -q
- Bundle: refactor/g12/g12-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S4
- Missing evidence: A failed formal plan should yield focused repair work instead of another repository-wide language-model analysis.
- AST symbols: 
- Merge key: refactor/g12/g12-s4
- Candidate kind: seed
- Todo vector key: ref-289-generateboundedcounterexample-guidedplanrepairs
- Acceptance: Typed repair rules can add missing dependencies, split effects, tighten authority, add tests or proof templates, change resource bounds, or request scoped human review.; Every candidate repair is recompiled and rechecked against the original goal and counterexample before taskboard admission.; Semantic identities, retry budgets, refinement depth, and progress measures prevent duplicate or infinite repair generation.; Codex receives only the selected repair transition and bounded counterexample capsule.

- [!] Task checkbox-290: REF-290 Bind plan conformance and formal evidence into goal completion

## REF-290 Bind plan conformance and formal evidence into goal completion

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-289
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_plan_conformance.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_plan_conformance.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_plan_conformance.py -q
- Bundle: refactor/g12/g12-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S4
- Missing evidence: A goal should close only when intended transitions occurred and all required implementation, validation, and proof evidence remains fresh.
- AST symbols: 
- Merge key: refactor/g12/g12-s4
- Candidate kind: seed
- Todo vector key: ref-290-bindplanconformanceandformalevidenceintogoalcomp
- Acceptance: Conformance compares canonical execution events with the accepted plan and distinguishes skipped, reordered, unauthorized, failed, overridden, and superseded transitions.; Plan consistency alone never verifies code; completion policy independently requires configured code, test, kernel, model-check, protocol, and runtime evidence.; Plan, policy, AST, premise, or counterexample changes invalidate affected conformance and reopen the goal.; Restart and replay reproduce the same conformance verdict from JSON or DuckDB evidence.
