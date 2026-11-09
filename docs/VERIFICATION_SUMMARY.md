# Refactor Verification Lanes

This document is the test-lane contract for complaint-generator refactors. The
repository-wide suite remains the final regression authority; these focused lanes
provide a fast, repeatable signal for the architectural surface being changed.

Run commands from the repository root. The Make targets use `python` by default;
set `PYTHON=.venv/bin/python` when the project environment is not already active.
Additional pytest options can be supplied with `PYTEST_ARGS`, for example:

```bash
make test-adapter PYTHON=.venv/bin/python PYTEST_ARGS="-q -x"
```

## Required Validation Order

For a normal refactor:

1. Run `make test-smoke` to catch import, packaging, launcher, and health failures.
2. Run the lane that owns the changed surface.
3. Run every additional lane named in the overlap guidance below when a change
   crosses a package boundary.
4. Run `make test-collect` before handoff. This is equivalent to the supervisor
   gate `python -m pytest --collect-only -q`.
5. Use `make test-refactor` for all five non-browser lanes, or the full regression
   suite when the change is broad or release-bound.

The lane commands inherit the repository's default gates: tests classified as
LLM-, network-, or heavy-dependent skip unless their existing opt-in flag or
environment variable is supplied. A skip is acceptable in a focused local lane
only when the skipped capability is outside the changed behavior; CI or a
capability-specific validation must exercise changed optional behavior.

## Lane Map

The explicit file lists in `Makefile` are the canonical membership for current
tests. This keeps commands deterministic while marker adoption proceeds across
the legacy suite.

| Lane | Command | Owned surfaces | Use it for |
| --- | --- | --- | --- |
| Smoke | `make test-smoke` | package/import boundaries, mediator state, main-chat payload shape, runtime status contracts | Every refactor; changes to packaging, shared state/payloads, or dependency direction |
| Adapter | `make test-adapter` | `integrations/ipfs_datasets`, adapter import boundaries and types, capabilities/degraded mode, provenance | Adapter implementations, optional dependency behavior, shared payload contracts, direct-import cleanup |
| Mediator | `make test-mediator` | mediator facade and workflow services, claim support, evidence, web evidence, legal authority hooks | Orchestration extraction, hook behavior, public mediator compatibility, acquisition and support flows |
| Document | `make test-document` | normalized parsing, parser fallbacks, legal-document parsing, formal drafting, workflow summaries | Ingestion contracts, chunks, drafting payloads, document rendering or export |
| UI | `make test-ui` | application route assembly, review API/view payloads, dashboard and workspace templates | Request handlers, UI state shaping, templates, route contracts, review/document handoff |

`make test-ui` is intentionally browser-free. It verifies server and rendered
contract behavior in lean environments. Run `make test-ui-browser` when changing
JavaScript interactions, browser navigation, accessibility-visible behavior, or
the Playwright fixture/server boundary. The browser lane may skip when Playwright
or its browser runtime is unavailable; browser-impacting work must run it in an
environment where those dependencies are installed.

### Overlap Guidance

Architectural changes often require more than one lane:

| Change | Minimum commands |
| --- | --- |
| An adapter payload consumed by mediator hooks | `make test-adapter`, then `make test-mediator` |
| Document ingestion called through evidence hooks | `make test-adapter`, `make test-mediator`, then `make test-document` |
| A mediator or DTO change rendered by an application | `make test-mediator`, then `make test-ui` |
| Drafting payload or `/document` workflow change | `make test-document`, then `make test-ui` |
| Template or browser interaction change | `make test-ui`, then `make test-ui-browser` |

## P0 Workstream Commands

The P0 workstreams are defined in `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md` and
cross-linked from `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`. Each has one named,
executable validation command. The aliases intentionally compose lanes where a
workstream crosses architectural seams.

| P0 workstream | Named validation command | Lanes exercised |
| --- | --- | --- |
| W1 Adapter hardening | `make validate-w1-adapters` | Adapter |
| W2 Unified acquisition and provenance | `make validate-w2-acquisition` | Adapter, mediator |
| W3 Document and chunk services | `make validate-w3-documents` | Adapter, mediator, document |
| W4 Graph persistence and support queries | `make validate-w4-graphs` | Adapter, mediator |
| W9 Legal corpus search and authority treatment | `make validate-w9-legal` | Adapter, mediator |
| W10 Drafting and filing readiness | `make validate-w10-drafting` | Document, UI |

Run `make validate-p0` when a change spans multiple P0 workstreams. It executes
the union of their non-browser lanes once per Make invocation. Browser-affecting
W10 work additionally requires `make test-ui-browser`.

## Pytest Marker Contract

`pytest.ini` registers the same five architectural markers: `smoke`, `adapter`,
`mediator`, `document`, and `ui`. These markers describe ownership, while existing
markers such as `unit`, `integration`, `browser`, `network`, `llm`, and `heavy`
describe test level or runtime requirements. They are orthogonal and may be
combined:

```python
@pytest.mark.adapter
@pytest.mark.integration
def test_normalized_parse_contract_round_trip():
    ...
```

New focused tests should carry the architectural marker matching their primary
owner. Cross-surface tests may carry multiple architectural markers. Do not move
a test out of the explicit Makefile lane merely because it is marked: marker-only
selection such as `pytest -m adapter` is useful for incremental or plugin suites,
but the Make target remains the stable refactor command until legacy marker
coverage is complete.

## Maintaining the Map

When adding or relocating a test for one of these surfaces:

- add its architectural marker;
- update the corresponding `*_TESTS` list in `Makefile` when it is part of the
  stable fast-confidence set;
- keep optional browser coverage in `UI_BROWSER_TESTS`, not `UI_TESTS`;
- update the overlap or P0 map if ownership changes; and
- confirm both the focused target and `make test-collect` succeed.

Long-running performance, stress, live-network, live-LLM, and full end-to-end
coverage, including workspace dataset tests that require a complete optional
`ipfs_datasets_py` checkout, remain outside these fast lanes. Use the existing
regression, canary, and HACC targets for those concerns.
