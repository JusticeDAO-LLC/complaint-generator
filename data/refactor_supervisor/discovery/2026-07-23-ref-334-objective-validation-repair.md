# REF-334 Objective Validation Repair

Date: 2026-07-23
Goal id: G7
Goal title: Rationalize frontend and review surfaces
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-334-objective-gap-eaafaa004d33.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g7.todo.md
Todo vector key: a6b0c4054bac33c2
Canonical task key: task/v1/420c62ea20bc98db3a10c5324d940fa0954edbc7dc00afb8b1ff3899e774b560
Canonical task CID: baguqeeraiiggf2raxsmnwoqqyuze3fapucku5w6h3qak7ofr744jtz3uwvqa
Merge key: 69ba34392fd62c48
Merge family: objective/G7

## Repair Summary

The objective scan filed a fresh validation gate for G7. The earlier REF-033
receipt remains valid historical evidence, but it does not prove the current
tree for REF-334. This task-specific receipt reconnects the implemented review
contracts, frontend fixtures, documentation, and current validation results and
therefore supplies the missing `objective validation repair` evidence.

G7 remains completely and usefully divided by G7.S1 into two completed work
items:

1. REF-021 owns the data boundary. It keeps coverage, follow-up, and support
   path normalization out of route and display assembly while retaining
   extension fields needed by mediator and UI consumers.
2. REF-022 owns browser-level display proof. It centralizes application,
   mediator, representative review, testimony, document, intake-summary, and
   support-state setup so review flows and screenshots exercise the same
   reusable fixtures.

Both work items are independently testable and jointly cover the parent goal.
Another child goal would duplicate these data-contract and browser-display
boundaries, so the objective heap does not need further decomposition.

## Current Evidence Contract

| G7 boundary | Implementation evidence | Executable or documented evidence |
| --- | --- | --- |
| Stable API normalization | `applications/review_api.py` defines the frozen `ReviewSummaryDTO` and dedicated coverage, follow-up, support-path, and whole-response normalizers. Every claim-support route passes its result through the whole-response DTO boundary. | `tests/test_review_api.py` directly verifies valid extension fields, malformed collection values, nested path summaries, route payload snapshots, and follow-up execution responses. |
| Display payload isolation | `applications/ui_review.py` defines the frozen `UIReviewPayloadDTO`. It preserves extension fields while normalizing known list and mapping fields before model-produced data reaches UI consumers. | `docs/ARCHITECTURE.md` assigns DTO adaptation to the review transport layer and keeps automation orchestration separate from UI payload builders. |
| Mediator support-path contract | `mediator/claim_support_hooks.py` defines `ClaimSupportPathSummaryDTO` for support traces, support packets, and optional graph traces. | `tests/test_claim_support_review_dashboard_flow.py` exercises the API-to-dashboard round trip against coverage, follow-up, and review data; the focused contract lane passes all 41 tests. |
| Shared browser setup | `tests/test_claim_support_review_playwright_smoke.py` supplies shared app, mediator, upload, workflow-priority, and document-review builders. `tests/test_review_surface_site_playwright.py` supplies a shared review-surface fixture and representative review/support-state actions. | Both browser modules are collected by the focused and repository-wide gates. Their 66-test focused lane exits successfully in this environment; the environment-independent test passes and 65 browser cases report the explicit `Playwright not available` skip reason. |
| Backlog ownership | `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`, `data/refactor_supervisor/refactor_todo.md`, and the G7/G7.S1 bundle shards map REF-021 and REF-022 to G7.S1 and REF-334 to the G7 validation gate. | The focused validation commands are attached to G7.S1, while G7 retains the repository-wide collection command. |

The intended dependency direction is:

```text
mediator support-path DTO
  -> claim-support payload builders
  -> review API response DTO normalization
  -> dashboard/display consumers
  -> shared representative browser fixtures
  -> route snapshots and browser assertions
```

This direction lets mediator payloads add extension data without forcing route
handlers or display code to assemble summaries ad hoc, while malformed known
collections still normalize at an explicit boundary.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Current repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-334-objective-validation-repair.md`
- Historical repair evidence:
  `data/refactor_supervisor/discovery/2026-07-21-ref-033-objective-validation-repair.md`
- Parent heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Canonical backlog anchor: REF-334 in
  `data/refactor_supervisor/refactor_todo.md`
- Bundle anchor: REF-334 in
  `data/refactor_supervisor/objective_bundles/refactor-g7.todo.md`
- Existing implementation ownership: REF-021 and REF-022
- Existing child goal: G7.S1
- Bundle identity: `refactor/g7`
- Merge identity: `objective/G7` / `69ba34392fd62c48`

The heap now points to this current receipt and retains the exact missing
evidence term. The canonical backlog and bundle shard already declare the same
goal, bundle, merge identity, work scope, validation command, and expected
outputs. Completion status and generated todo-vector metadata remain
supervisor-owned and are not manually changed by this repair.

## Validation

- PASS — `python -m pytest --collect-only -q` (5,819 tests collected in
  45.63s).
- PASS — `python -m pytest tests/test_review_api.py
  tests/test_claim_support_review_dashboard_flow.py -q` (41 passed in 26.55s).
- PASS/COLLECTED — `python -m pytest
  tests/test_claim_support_review_playwright_smoke.py
  tests/test_review_surface_site_playwright.py -q -rs` (66 tests collected;
  1 passed and 65 skipped because the optional Playwright package is not
  installed, in 5.42s).

All commands exited successfully. The runs emitted only existing
pytest-asyncio, Starlette, and dashboard string-literal warnings.
