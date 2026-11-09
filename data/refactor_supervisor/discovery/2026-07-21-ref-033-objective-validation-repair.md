# REF-033 Objective Validation Repair

Date: 2026-07-21
Goal id: G7
Goal title: Rationalize frontend and review surfaces
Gap source: data/refactor_supervisor/discovery/2026-07-21-ref-033-objective-gap-eaafaa004d33.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g7.todo.md
Todo vector key: a6b0c4054bac33c2
Merge key: 69ba34392fd62c48
Merge family: objective/G7

## Repair Summary

The objective scan filed REF-033 because G7's parent evidence did not contain
the explicit objective validation repair proof term. The frontend and review
work is already divided into two bounded implementation claims under G7.S1:

- REF-021 owns the review contract boundary in `applications/review_api.py`,
  `applications/ui_review.py`, and `mediator/claim_support_hooks.py`. It moves
  coverage, follow-up, and support-path normalization behind explicit DTO
  helpers while preserving route response snapshots.
- REF-022 owns the browser validation boundary in
  `tests/test_claim_support_review_playwright_smoke.py` and
  `tests/test_review_surface_site_playwright.py`. It extracts shared fixture
  builders while retaining representative support states and screenshot
  assertions.

These claims separate production payload assembly from display-test assembly,
have disjoint primary edit surfaces, and name focused validation commands. They
are independently deliverable while remaining under the single G7.S1 contract,
so another child goal would duplicate the existing split rather than make the
work smaller or safer.

The repository-wide collection gate passes and discovers both focused review
test lanes. This record supplies the missing objective validation repair
evidence directly to G7. The objective heap and the REF-033 records on the
canonical and bundle-local todo boards all point to this same proof artifact,
keeping the supervisor-fed backlog aligned with the objective.

## Evidence Covered

- Missing evidence term: objective validation repair
- Review contract lane: REF-021 and G7.S1 in
  `data/refactor_supervisor/refactor_objective_heap.md`
- Browser fixture lane: REF-022 and G7.S1 in
  `data/refactor_supervisor/refactor_objective_heap.md`
- Architecture boundary: `docs/ARCHITECTURE.md`
- Contract validation surfaces: `tests/test_review_api.py` and
  `tests/test_claim_support_review_dashboard_flow.py`
- Browser validation surfaces:
  `tests/test_claim_support_review_playwright_smoke.py` and
  `tests/test_review_surface_site_playwright.py`
- Heap evidence:
  `data/refactor_supervisor/discovery/2026-07-21-ref-033-objective-validation-repair.md`
- Backlog evidence: REF-033 in `data/refactor_supervisor/refactor_todo.md`
- Bundle evidence: REF-033 in
  `data/refactor_supervisor/objective_bundles/refactor-g7.todo.md`

## Validation

Command: `python -m pytest --collect-only -q`

Result: passed on 2026-07-21; 4,631 tests collected in 35.10 seconds, exit code
0. The only diagnostic was the existing `pytest-asyncio` deprecation warning
for the unset `asyncio_default_fixture_loop_scope` option.
