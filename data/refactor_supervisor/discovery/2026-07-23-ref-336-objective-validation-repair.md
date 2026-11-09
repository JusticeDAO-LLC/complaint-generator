# REF-336 Objective Validation Repair

Date: 2026-07-23
Goal id: G6.S1
Goal title: Replace silent failures with typed outcomes
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-336-objective-gap-9d4d130f9c91.md
Gap fingerprint: 9d4d130f9c912b62029121a63244a9b437a518ce
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g6-g6-s1.todo.md
Todo vector key: 2d182c29f1a5b191
Canonical task key: task/v1/3dc3b8b32a51dece440638a7aab82becff2bb949b11b4294a5c01aa82d967628
Canonical task CID: baguqeerahxb3rmzkkhpm4raghct2vobl5t7sxokjwenuffffyankqlmwoyua
Merge key: 5d3d3d477614d4e8
Merge family: objective/G6.S1
Merge role: validation_gate

## Repair Summary

The objective scan filed REF-336 after finding every implementation path,
acceptance statement, and validation command for G6.S1 but no task-specific
`objective validation repair` receipt. This record revalidates the typed
outcome and diagnostic-fallback contracts against the current tree and supplies
that missing evidence.

The implementation remains completely and usefully divided into its two
existing work items:

1. REF-017 owns broad-exception boundaries in mediator and adapter paths. It
   documents why unstable third-party boundaries still catch ordinary runtime
   failures, returns list-compatible typed degradation from high-traffic query
   paths, raises typed hook errors for nonrecoverable point operations, and
   logs the original failure context.
2. REF-018 owns formerly silent failures in user-facing workflows. It names
   intentional fallbacks, logs unexpected failures, retains the best available
   deterministic or local-only result, and persists daemon-cycle errors for
   operator inspection.

These slices already separate programmatic failure semantics from
user-workflow fallback behavior. A smaller child goal would duplicate those
owners rather than expose missing work, so G6.S1 needs no objective-heap
refinement.

## Broad-Exception Boundary Audit

| Production cluster | Why a boundary handler remains | Typed or observable outcome |
| --- | --- | --- |
| `mediator/evidence_hooks.py` | DuckDB, optional IPFS tooling, and stored JSON decoding do not expose one stable shared exception hierarchy. | `EvidenceStorageError`, `EvidenceRetrievalError`, `EvidencePersistenceError`, and `EvidenceQueryError` preserve nonrecoverable causes. Best-effort list queries return `DegradedEvidenceResults` with `status`, `operation`, `degraded_reason`, `error_type`, and serialized results. |
| `integrations/ipfs_datasets/search.py` | Optional search engines, Playwright, HTTP clients, filesystem downloads, and `ipfs_datasets_py` adapters fail through unrelated exception families. | `DegradedSearchResults` preserves historical list behavior and fallback records while exposing `status`, `operation`, `degraded_reason`, `error_type`, `fallback_provider`, and `as_dict()`. Other adapter operations return structured status/error dictionaries with adapter metadata. |
| `mediator/mediator.py` | Backend calls and optional neurosymbolic, authority, scraper, and claim-support enrichment are orchestration boundaries. | User/backend errors are logged and re-raised. Optional enrichment returns its documented neutral fallback only after logging an operation, error text, and error type. The module audit explicitly states that no broad handler silently drops an unexpected failure. |
| `applications/ui_review.py` | Multimodal and text model providers are optional and can fail independently or be deliberately bypassed for a text-only provider. | Deliberate text-only routing is named at debug level. Provider failures are warnings with traceback context; fallback attempts retain provider/model/error metadata; final failure returns deterministic review output carrying both multimodal and text fallback errors. |
| `complaint_generator/ui_optimizer_daemon.py` | Process inspection, persisted JSON status, and an entire optimization cycle cross OS, filesystem, browser, and provider boundaries. | Malformed or unavailable state emits a log breadcrumb. Cycle failures persist `error`, `error_kind`, `error_summary`, phase, retry timestamps, and consecutive-error count before retrying or failing at the configured limit. |
| `mediator/state.py` | The legacy remote profile service is optional and may be unavailable while local complaint work continues. | Profile load/save failures append the exception-bearing local-only fallback reason to the state log and return the retained local data instead of silently discarding the failure. Intentional chat-history compatibility fallback is named with debug logs. |

Local parsing and validation paths use narrow exception types where their
failure families are known. The remaining broad handlers are therefore
documented adapter or orchestration boundaries, not silent control-flow
shortcuts.

## Typed Outcome Contract

The typed degradation path is deliberately compatible with existing callers:

```text
primary adapter call
  -> ordinary runtime failure at an audited boundary
  -> diagnostic breadcrumb with operation and original error
  -> compatible fallback records
  -> DegradedSearchResults or DegradedEvidenceResults
       status = "degraded"
       operation = stable operation name
       degraded_reason = original failure text
       error_type = original exception class
       results = list-compatible fallback payload
```

This distinguishes an operational failure from a valid empty query without
forcing legacy list consumers to migrate in the same release. Callers that
need machine-readable status can inspect typed fields or call `as_dict()`;
existing iteration, indexing, slicing, equality, and truthiness behavior
remains available.

`tests/test_ipfs_adapter_layer.py` exercises the concrete cross-provider
fallback: when the multi-engine orchestrator raises `RuntimeError("orchestrator
offline")`, Brave fallback records are retained in `DegradedSearchResults`.
The assertions cover every typed field and the serialization-safe dictionary
shape, including `fallback_provider`, `result_count`, and `results`.

## Acceptance Evidence

- **Top production broad-exception clusters are documented.**
  The module audits in `mediator/mediator.py`,
  `mediator/evidence_hooks.py`, and
  `integrations/ipfs_datasets/search.py` identify each unstable production
  boundary, explain why a broad translation boundary remains, and state the
  resulting failure contract. The table above extends that inventory through
  the user-facing workflow surfaces named by G6.S1.
- **At least one cluster returns a typed degraded result.**
  Search adapters return `DegradedSearchResults`; evidence list queries return
  `DegradedEvidenceResults`. Both are concrete list subtypes with structured
  degradation fields and an `as_dict()` representation. The adapter test lane
  executes the multi-engine failure-and-fallback path.
- **Intentional ignores are named.**
  Text-only UI routing logs that multimodal review is skipped and proceeds to
  the named text fallback. State-history compatibility fallback logs why the
  custom extractor was not used. Narrow parse failures use comments or log
  messages that identify discarded malformed input rather than bare `pass`.
- **Unexpected failures leave diagnostic breadcrumbs.**
  Mediator and evidence operations log stable operation names and original
  errors. UI review logs provider failures and includes fallback errors in
  result metadata. The UI optimizer writes cycle errors and retry state to its
  status file. Profile persistence appends the remote failure reason before
  returning local data.
- **Both named regression lanes pass.**
  The mediator/adapter lane passes 105 tests. The UI/review lane passes 40
  tests; its three network-marked daemon CLI tests are collected and skipped
  by the repository's default marker policy rather than missing or failing.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-336-objective-validation-repair.md`
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Canonical backlog evidence: REF-336 in
  `data/refactor_supervisor/refactor_todo.md`
- Bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g6-g6-s1.todo.md`
- Existing implementation ownership: REF-017 and REF-018
- Bundle identity: `refactor/g6/g6-s1`
- Merge identity: `objective/G6.S1` / `5d3d3d477614d4e8`
- Todo vector identity: `2d182c29f1a5b191`

The heap now points to this receipt and retains the exact missing evidence
term. The canonical todo and bundle shard already name G6.S1, the same
implementation surfaces, and the same validation commands. Generated task
status, completion metadata, bundle checkboxes, and vector-index regeneration
remain supervisor-owned and are not changed manually by this repair.

## Validation

- PASS — `python -m pytest tests/test_mediator.py
  tests/test_ipfs_adapter_layer.py -q` (105 passed).
- PASS — `python -m pytest tests/test_ui_optimizer_daemon_cli.py
  tests/test_review_api.py -q` (40 passed, 3 network-marked tests skipped).

Both commands exited successfully. The runs emitted only existing
pytest-asyncio and Starlette deprecation warnings.
