# REF-324 Objective Validation Repair

Date: 2026-07-23
Goal id: G2.S2
Goal title: Reduce application surface coupling
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-324-objective-gap-d2eeaaabba53.md
Gap fingerprint: d2eeaaabba5320268eead80e35f45257b6c59975
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g2-g2-s2.todo.md
Todo vector key: 5d35aa067d5417a1
Canonical task key: task/v1/527f6123ce167318d998b69aa82bee9900d16877b80e38cc4ac68d52b56a85d4
Canonical task CID: baguqeerakj7wci6oczzrrwmyw2nkqk7oteanc2dxxahdrtcky2gvfnlkqxka
Merge key: ae5019ce8c73e7a2
Merge family: objective/G2.S2
Merge role: validation_gate

## Repair Summary

The objective scan filed REF-324 because G2.S2 had every named implementation
path, acceptance statement, and validation command, but it did not have a
durable `objective validation repair` receipt. The two existing implementation
slices already form a complete and appropriately bounded decomposition:

1. REF-007 isolates request-facing workspace mutations behind
   `ComplaintWorkspaceRequestHandlers` and a narrow
   `_ComplaintWorkspaceHandlerBackend` protocol. `ComplaintWorkspaceService`
   remains the compatibility facade used by existing routes, CLI commands, and
   MCP entrypoints.
2. REF-008 moves dashboard catalogs into named Python and JavaScript fixture
   builders. Live route construction resolves one fixture catalog and supports
   explicit injection without mutating module-global route data.

The exact G2.S2 validation commands pass in the current repository. No smaller
child goal is needed: REF-007 owns the workspace request boundary and REF-008
owns dashboard fixture assembly. Splitting either validation gate again would
duplicate those ownership boundaries rather than expose unowned implementation
work.

## Application Boundary Contract

| Surface | Isolated owner | Compatibility boundary | Executable evidence |
| --- | --- | --- | --- |
| Workspace request mutations | `ComplaintWorkspaceRequestHandlers` in `applications/complaint_workspace.py` | The handler group depends on `_ComplaintWorkspaceHandlerBackend` for persistence and state-derived payloads. It owns session retrieval, intake writes, evidence writes/uploads, draft mutations, synopsis/claim-type updates, and reset orchestration. | `tests/test_complaint_generator_tools.py` exercises the same service through CLI, MCP, and `/api/complaint-workspace` routes, including intake chat, generation, upload, session retrieval, and reset response fields. |
| Workspace public facade | `ComplaintWorkspaceService` in `applications/complaint_workspace.py` | Existing public method names and return dictionaries remain in place and delegate to `request_handlers`. State loading, saving, review calculation, synopsis calculation, and draft assembly stay behind the backend protocol. | The required `tests/test_review_api.py` regression gate passes all 40 collected review response-contract tests. |
| Python dashboard fixture catalog | `DashboardFixtures` and `build_dashboard_fixture_data` in `applications/dashboard_ui.py` | Named builders produce complaint links, IPFS entries, and layperson hub data. `create_dashboard_ui_router` binds one resolved catalog; `attach_dashboard_ui_routes` can inject a catalog for tests or previews while retaining the default live catalog. | The Playwright smoke module imports the dashboard surface through `applications.review_ui` successfully; full dashboard router/shell coverage remains in `tests/test_claim_support_review_template.py`. |
| JavaScript preview fixtures | `buildDashboardEntriesFixture`, `buildLaypersonDashboardCardsFixture`, `buildDashboardUtilityCardsFixture`, `buildDashboardSubsectionCardsFixture`, and `buildDashboardFixtures` in `playwright/server.js` | `handleDashboardFixtureRoute`, `handlePlaywrightRequest`, and `createPlaywrightServer` receive an explicit validated catalog. Default behavior still uses `getDashboardFixtures`; callers can inject a fresh catalog without changing live singleton state. | The named builders and route handler are exported for reuse. Duplicate or missing slugs fail during fixture construction instead of surfacing as ambiguous live-route behavior. |
| Browser route mixture | `_build_playwright_fixture_app` and focused wrappers in `tests/test_claim_support_review_playwright_smoke.py` | Review, document, and health route combinations are assembled by reusable named builders rather than repeated inline FastAPI setup. | The required smoke command collects 55 tests and exits successfully in this environment. |

The intended dependency flow is:

```text
HTTP / CLI / MCP request
  -> ComplaintWorkspaceService compatibility method
  -> ComplaintWorkspaceRequestHandlers
  -> narrow state/review/draft backend protocol
  -> unchanged response dictionary

dashboard route creation
  -> named fixture builders
  -> validated immutable-style fixture catalog
  -> explicitly bound Python router or JavaScript preview server
  -> rendered route response
```

This flow keeps request lifecycle decisions separate from workspace state
shaping and keeps representative dashboard data separate from route matching
and rendering.

## Acceptance Evidence

- **One handler group is isolated.**
  `ComplaintWorkspaceRequestHandlers` is a concrete request boundary with a
  narrow backend protocol and injectable clock. Ten public
  `ComplaintWorkspaceService` operations delegate to that group while existing
  service consumers keep their entrypoints.
- **Routes keep the same response shape.**
  The handler boundary centralizes session payload composition and preserves
  the established `session`, `questions`, `next_question`, `review`,
  `case_synopsis`, `draft`, and mutation-result fields. The review API lane
  passes all 40 collected tests, including route registration and refreshed
  post-mutation review payloads.
- **Fixture builders are named and reusable.**
  Both dashboard implementations expose named builders. Python routers accept
  `DashboardFixtures`; the JavaScript server accepts the result of
  `buildDashboardFixtures` and exports the builders, lookup helpers, route
  handler, and server factory.
- **Playwright smoke tests remain stable.**
  `tests/test_claim_support_review_playwright_smoke.py` uses
  `_build_playwright_fixture_app` for its shared route mix, with focused review
  and document wrappers. Its required pytest command exits with status 0.
  Browser-dependent cases are skipped when the optional Playwright package is
  absent, as occurred in this validation environment; the receipt does not
  claim those skipped browser cases executed.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-324-objective-validation-repair.md`
- Canonical backlog evidence: REF-324 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing workspace implementation ownership: REF-007
- Existing dashboard implementation ownership: REF-008
- G2.S2 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g2-g2-s2.todo.md`

The heap now points to this receipt and includes the exact missing evidence
term. The canonical todo and bundle shard already identify G2.S2, the same two
implementation slices, and the same validation commands. Generated bundle and
vector-index regeneration, task completion, and task status remain
supervisor-owned, so this repair does not manually alter REF-324 status or
generated metadata.

## Validation

- PASS — required review API lane:
  `python -m pytest tests/test_review_api.py -q`
  (40 passed).
- PASS — required Playwright smoke lane:
  `python -m pytest tests/test_claim_support_review_playwright_smoke.py -q`
  (1 passed, 54 skipped because the optional Playwright runtime is not
  installed).
- PASS — supplemental dashboard boundary checks: a freshly built Python
  `DashboardFixtures` catalog bound all five expected router paths; a custom
  JavaScript catalog resolved through the exported lookup and server factory;
  duplicate JavaScript slugs were rejected.
- PASS — supervisor parser check: G2.S2 resolves the repair receipt path and
  exact `objective validation repair` term as required evidence.

Both commands exited with status 0. The review lane emitted the existing
Starlette TestClient deprecation warning. The smoke lane emitted existing
invalid-escape `SyntaxWarning` messages from the dashboard HTML/JavaScript
template. Neither lane reported a failure.
