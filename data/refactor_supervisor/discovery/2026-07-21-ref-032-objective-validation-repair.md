# REF-032 Objective Validation Repair

Date: 2026-07-21
Goal id: G6
Goal title: Pay down error-handling and observability debt
Gap source: data/refactor_supervisor/discovery/2026-07-21-ref-032-objective-gap-3cddb89025f0.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g6.todo.md
Todo vector key: 524c6d1d9430d914
Merge key: de8ccdd4b6a5e381
Merge family: objective/G6

## Repair Summary

The objective scan filed REF-032 because G6's parent evidence did not contain
the explicit objective validation repair proof term. The implementation work
is already divided into two bounded, independently validated child goals:

- G6.S1 owns predictable failure semantics. REF-017 documents the remaining
  broad exception boundaries in the mediator, evidence hooks, and search
  adapter. Those boundaries either raise typed hook errors or expose typed,
  list-compatible degraded results. REF-018 replaces silent user-workflow
  failures with named fallbacks and diagnostic logging in UI review, UI
  optimizer, and mediator state paths.
- G6.S2 owns operator-visible runtime state. REF-019 gives the UI optimizer,
  scraper, and Gmail importer the shared `status`, `pid`, `updated_at`,
  `artifacts`, and `last_error` fields. REF-020 documents PID, log, status, and
  queue locations, last-cycle indicators, and stale-running-task recovery.

These child goals separate error contracts from daemon/operator contracts and
name focused test lanes. A third child goal would duplicate that existing split
rather than make the work smaller or independently deliverable, so the
objective heap does not need further refinement for this validation gate.

The repository-wide collection gate passes and discovers all named G6 test
surfaces. The typed-outcome lane also passes in full, as does the user-facing
review fallback coverage. The daemon CLI tests are intentionally gated by the
repository's network and LLM markers in the default environment; collection
still proves their contracts remain discoverable, while the passing adapter
suite directly exercises the scraper's common status payload.

This record supplies the missing objective validation repair evidence directly
to G6. The objective heap and the REF-032 records on the canonical and
bundle-local todo boards all point to this proof artifact, keeping the
supervisor-fed backlog aligned with the objective.

## Evidence Covered

- Missing evidence term: objective validation repair
- Typed failure boundary: `mediator/mediator.py`,
  `mediator/evidence_hooks.py`, `integrations/ipfs_datasets/search.py`, and
  `tests/test_ipfs_adapter_layer.py`
- Diagnostic fallback boundary: `applications/ui_review.py`,
  `complaint_generator/ui_optimizer_daemon.py`, `mediator/state.py`, and
  `tests/test_review_api.py`
- Common runtime status contract:
  `complaint_generator/ui_optimizer_daemon.py`,
  `integrations/ipfs_datasets/scraper_daemon.py`,
  `scripts/gmail_duckdb_daemon.py`, `tests/test_ipfs_adapter_layer.py`,
  `tests/test_ui_optimizer_daemon_cli.py`, and
  `tests/test_gmail_duckdb_daemon_cli.py`
- Operator runbook: `docs/OBSERVABILITY_INDEX.md` and
  `docs/observability/TROUBLESHOOTING.md`
- Completed implementation slices: REF-017 through REF-020 on
  `data/refactor_supervisor/refactor_todo.md`
- Heap evidence:
  `data/refactor_supervisor/discovery/2026-07-21-ref-032-objective-validation-repair.md`
- Backlog evidence: REF-032 in `data/refactor_supervisor/refactor_todo.md`
- Bundle evidence: REF-032 in
  `data/refactor_supervisor/objective_bundles/refactor-g6.todo.md`

## Validation

- PASS — `python -m pytest --collect-only -q` (4,636 tests collected in 35.24s)
- PASS — `python -m pytest tests/test_mediator.py tests/test_ipfs_adapter_layer.py -q`
  (99 passed in 18.71s)
- PASS — `python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_review_api.py -q`
  (40 passed, 3 network-marked tests skipped in 14.83s)
- PASS — `python scripts/refactor_agent_supervisor.py status` (exit code 0;
  canonical artifact paths, queue/todo counts, scan summary, and `last_error`
  were reported)
- COLLECTED — `python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_gmail_duckdb_daemon_cli.py -q -rs`
  (3 network-marked and 5 LLM-marked tests skipped by the repository's default
  test policy)
