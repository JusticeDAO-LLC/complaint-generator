# REF-333 Objective Validation Repair

Date: 2026-07-23
Goal id: G6
Goal title: Pay down error-handling and observability debt
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-333-objective-gap-3cddb89025f0.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g6.todo.md
Todo vector key: 524c6d1d9430d914
Canonical task key: task/v1/f1868347c833d8b991b9ed8b39e01c211119c6967c4275f459edaa47a14c4799
Canonical task CID: baguqeera6gdigr6igpmltenz5wfttya4eeirtruwprbhl5cz5wvepikmi6mq
Merge key: de8ccdd4b6a5e381
Merge family: objective/G6

## Repair Summary

The objective scan filed a fresh validation gate for G6. The earlier REF-032
receipt remains useful historical evidence, but it does not serve as the
current REF-333 repair receipt. This record revalidates the implementation,
tests, documentation, and child-goal boundaries against the current tree and
supplies the missing `objective validation repair` evidence for REF-333.

G6 remains completely and usefully divided into two child goals:

1. G6.S1 owns failure semantics at production boundaries. Database and adapter
   query failures return typed, list-compatible degraded results; user-facing
   fallback paths retain a usable result and emit a diagnostic breadcrumb.
2. G6.S2 owns operator-visible runtime state. The UI optimizer, scraper, and
   Gmail importer expose the common `status`, `pid`, `updated_at`, `artifacts`,
   and `last_error` fields, while the observability docs explain artifact
   locations, freshness signals, and safe stale-process/task recovery.

REF-017 through REF-020 are completed and map one-to-one onto those boundaries.
A third child goal would mix or duplicate the existing failure-contract and
runtime-status lanes, so the objective heap does not need further refinement.

## Current Evidence Contract

| G6 boundary | Implementation evidence | Executable or operator evidence |
| --- | --- | --- |
| Typed degraded results | `mediator/evidence_hooks.py` defines `DegradedEvidenceResults`; `integrations/ipfs_datasets/search.py` defines `DegradedSearchResults`. Both preserve legacy list behavior while exposing structured status, operation/provider, and degraded-reason fields. | `tests/test_ipfs_adapter_layer.py` asserts the degraded search contract and the scraper status contract; `tests/test_mediator.py` verifies degraded capability information reaches mediator startup state. |
| Predictable boundary failures | `mediator/evidence_hooks.py` distinguishes typed storage/retrieval failures from query degradation. `integrations/ipfs_datasets/search.py` narrows parsing and HTTP failures and normalizes unstable backend failures. | The mediator and adapter lane passes all 105 tests. |
| Diagnostic user-workflow fallbacks | `applications/ui_review.py` logs decode, artifact, image, backend, and configured-fallback failures. `complaint_generator/ui_optimizer_daemon.py` logs state/process failures and persists cycle errors. `mediator/state.py` records local-only profile fallback reasons instead of silently discarding them. | `tests/test_review_api.py` and the UI optimizer CLI suite pass or are collected under the repository's marker policy; 40 unmarked tests pass. |
| Common runtime status | `complaint_generator/ui_optimizer_daemon.py`, `integrations/ipfs_datasets/scraper_daemon.py`, and `scripts/gmail_duckdb_daemon.py` populate the five common fields. Status readers preserve those fields and normalize legacy error/timestamp aliases. | Adapter tests execute the scraper contract. UI and Gmail CLI contract tests are collected; their eight tests are skipped by the default network/LLM marker policy rather than missing or failing. |
| Operator observability | `docs/OBSERVABILITY_INDEX.md` maps status commands and PID, status, log, queue, checkpoint, and progress artifacts. `docs/observability/TROUBLESHOOTING.md` defines liveness/freshness checks and guarded stale PID and queue-task recovery. | `python scripts/refactor_agent_supervisor.py status` remains the named G6.S2 operator check; repository-wide collection confirms every named G6 test surface is discoverable. |

The intended behavior is:

```text
recoverable provider or persistence failure
  -> typed degraded outcome + diagnostic context
  -> caller keeps compatible fallback behavior

long-running workflow transition
  -> common status snapshot + artifact paths + last error
  -> operator checks PID, freshness, logs, and queue/checkpoint state
  -> guarded recovery only after ownership and staleness are confirmed
```

This preserves behavior while making both programmatic failures and operational
stalls inspectable.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-333-objective-validation-repair.md`
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Canonical backlog evidence: REF-333 in
  `data/refactor_supervisor/refactor_todo.md`
- Bundle identity: `refactor/g6`
- Merge identity: `objective/G6` / `de8ccdd4b6a5e381`
- Existing implementation ownership: REF-017 through REF-020
- Existing child goals: G6.S1 and G6.S2

The heap now points to this task-specific receipt and retains the exact missing
evidence term. The supervisor-fed task already names the same goal, bundle,
merge identity, work scope, validation command, and receipt output directory.
Generated todo status and completion metadata remain supervisor-owned and are
not changed by this repair.

## Validation

- PASS — `python -m pytest --collect-only -q` (5,819 tests collected in
  17.27s on the final post-edit run).
- PASS — `python -m pytest tests/test_mediator.py
  tests/test_ipfs_adapter_layer.py -q` (105 passed in 23.12s).
- PASS — `python -m pytest tests/test_ui_optimizer_daemon_cli.py
  tests/test_review_api.py -q` (40 passed, 3 network-marked tests skipped in
  17.79s).
- COLLECTED — `python -m pytest tests/test_ui_optimizer_daemon_cli.py
  tests/test_gmail_duckdb_daemon_cli.py -q -rs` (3 network-marked and 5
  LLM-marked tests skipped by the repository's default test policy).

All commands exited successfully. The runs emitted only existing pytest-asyncio
and Starlette deprecation warnings.
