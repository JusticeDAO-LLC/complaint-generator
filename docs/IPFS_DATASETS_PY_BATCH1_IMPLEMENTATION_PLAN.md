# IPFS Datasets Py Batch 1 Implementation Plan

Date: 2026-03-12
Status: Ready for execution

Companion docs:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`
- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`

## Purpose

Turn Batch 1, adapter contract stabilization, into issue-sized implementation slices that can be executed without reopening architecture questions.

This plan assumes the current repository state described in the companion docs is accurate:

- the adapter boundary already exists under `integrations/ipfs_datasets/`
- evidence, web evidence, and legal-authority flows already consume adapter-backed integrations in part
- mediator startup already reports capability information
- later batches depend on Batch 1 producing stable capability and degraded-mode payloads

## Batch 1 outcome

At the end of Batch 1, complaint-generator should have one stable adapter contract family for:

- capability reporting
- degraded-mode payloads
- placeholder or not-yet-implemented payloads
- startup diagnostics and operator-visible capability summaries

The main success criterion is that later parse, graph, GraphRAG, and logic work can evolve without forcing repeated caller rewrites.

## Non-goals

Batch 1 should not attempt to:

- deepen parse pipelines
- add graph persistence
- add GraphRAG scoring
- implement theorem-prover workflows
- redesign mediator review payloads beyond capability reporting

If a change is primarily about corpus parsing, graph querying, or validation semantics, it belongs to later batches.

## Target files

- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/loader.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/search.py`
- `integrations/ipfs_datasets/graphs.py`
- `integrations/ipfs_datasets/logic.py`
- `integrations/ipfs_datasets/types.py`
- `integrations/ipfs_datasets/__init__.py`
- `mediator/mediator.py`
- `tests/test_ipfs_adapter_types.py`
- `tests/test_ipfs_adapter_layer.py`

## Implementation slices

## Slice 1: Canonical capability type family

Goal:

- define one shared structural shape for capability reports and degraded results

Primary files:

- `integrations/ipfs_datasets/types.py`
- `integrations/ipfs_datasets/capabilities.py`

Tasks:

- define or normalize typed payloads for adapter capability status
- define required fields for all capability families such as `available`, `reason`, `details`, and `provider` or `module`
- define one degraded payload family that adapters can return consistently
- ensure placeholder adapters and missing-module adapters share the same top-level keys

Done when:

- callers can assert one stable shape for all adapter capability responses
- adapter tests no longer need per-adapter shape exceptions

Suggested issue title:

- `Normalize IPFS adapter capability payload types`

## Slice 2: Centralized import probing and failure folding

Goal:

- make upstream import drift degrade into explicit status instead of leaking ad hoc import behavior into each adapter

Primary files:

- `integrations/ipfs_datasets/loader.py`
- `integrations/ipfs_datasets/capabilities.py`

Tasks:

- centralize import probing helpers
- centralize exception-to-degraded-status conversion
- remove duplicate import failure handling from adapters where it is only boilerplate
- ensure loader helpers preserve actionable failure reasons such as missing module, deprecated path, or optional dependency unavailable

Done when:

- adapter modules rely on shared loader behavior for import probing
- degraded mode exposes informative reason strings without stack-trace-shaped payloads

Suggested issue title:

- `Centralize IPFS adapter import probing and degraded fallback handling`

## Slice 3: Legal and search adapter shape cleanup

Goal:

- remove upstream path and result-shape drift from the legal and search adapters before deeper workflow work lands

Primary files:

- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/search.py`
- `tests/test_ipfs_adapter_layer.py`

Tasks:

- ensure legal wrappers normalize async upstream scraper results into one sync-safe contract
- ensure search wrappers normalize current web, archive, and Common Crawl outputs into one result family
- keep stable handling for `BraveSearchAPI` and nested Common Crawl module paths
- ensure degraded payloads match the common family defined in Slice 1

Done when:

- mediator consumers do not branch on `results` versus `documents`
- mediator consumers do not care which search backend produced the normalized result family

Suggested issue title:

- `Normalize legal and web-search adapter result families`

## Slice 4: Graph and logic placeholder contract cleanup

Goal:

- make graph and logic adapters safe to extend later without breaking caller assumptions twice

Primary files:

- `integrations/ipfs_datasets/graphs.py`
- `integrations/ipfs_datasets/logic.py`
- `tests/test_ipfs_adapter_layer.py`

Tasks:

- normalize placeholder success or not-implemented payloads
- normalize degraded payloads for unavailable graph or logic dependencies
- ensure graph adapter capability and placeholder query responses use the shared contract family
- ensure logic adapter placeholder proof responses expose stable fields that later batches can extend without removing keys

Done when:

- graph and logic callers can treat current placeholder outputs as stable contracts rather than temporary ad hoc dicts

Suggested issue title:

- `Stabilize graph and logic adapter placeholder contracts`

## Slice 5: Mediator capability summary and startup behavior

Goal:

- make mediator startup consume the shared adapter capability family consistently and visibly

Primary files:

- `mediator/mediator.py`
- `integrations/ipfs_datasets/__init__.py`

Tasks:

- consume the canonical capability summary helper rather than piecing together adapter-specific status checks
- keep startup logs stable across full, partial, and degraded runtime modes
- avoid direct dependency on upstream module path quirks from mediator startup or health reporting

Done when:

- mediator startup logs the same capability groups in all runtime modes
- missing optional features degrade into useful diagnostics rather than surprising behavior

Suggested issue title:

- `Unify mediator startup capability reporting for IPFS adapters`

## Slice 6: Direct-import drift audit

Goal:

- confirm that production code reaches `ipfs_datasets_py` only through the adapter boundary

Primary files:

- `complaint_analysis/indexer.py`
- any additional production modules found during search

Tasks:

- search for direct `ipfs_datasets_py` imports outside `integrations/ipfs_datasets/`
- move remaining production imports behind adapters
- isolate any unavoidable exceptions to tests, benchmarks, or intentionally diagnostic scripts

Done when:

- no production module depends on submodule path knowledge outside the adapter layer

Suggested issue title:

- `Remove remaining direct production imports of ipfs_datasets_py`

## Recommended execution order

1. Slice 1
2. Slice 2
3. Slice 3
4. Slice 4
5. Slice 5
6. Slice 6

This order matters because type and loader normalization should land before adapter-specific cleanup, and mediator cleanup should come after the underlying summary helpers are stable.

## Validation plan

Minimum focused validation after each slice:

```bash
./.venv/bin/python -m pytest tests/test_ipfs_adapter_types.py -q
./.venv/bin/python -m pytest tests/test_ipfs_adapter_layer.py -q
```

Additional slice-specific validation:

```bash
./.venv/bin/python -m pytest tests/test_review_api.py tests/test_claim_support_hooks.py -q
```

Use the mediator-focused slice when startup or capability summary behavior changes.

## Stop or go criteria

Go to Batch 2 only when all of the following are true:

- capability payloads are structurally consistent across adapters
- degraded-mode payloads expose explicit reason fields
- legal and search adapters no longer leak upstream result-shape drift
- graph and logic placeholders expose stable contracts
- mediator startup can render one stable capability summary
- focused adapter tests pass without adapter-specific shape workarounds

Do not start Batch 2 if Batch 1 still requires mediator callers to branch on adapter-specific payload keys.

## Risks

### Risk: over-editing adapters before contract decisions are pinned

Mitigation:

- treat Batch 1 as a contract pass, not a feature pass
- keep later-batch parsing, graph, and validation work out of scope

### Risk: loader cleanup hides useful failure details

Mitigation:

- preserve original import failure context inside reason or details fields
- test degraded payloads explicitly

### Risk: mediator logs drift from actual adapter state

Mitigation:

- derive startup summaries from the shared capability helper instead of duplicating logic in mediator code

## Deliverable checklist

- [ ] shared capability payload family is stable
- [ ] degraded payload family is stable
- [ ] legal adapter success and degraded outputs are normalized
- [ ] search adapter success and degraded outputs are normalized
- [ ] graph placeholder outputs are normalized
- [ ] logic placeholder outputs are normalized
- [ ] mediator startup uses the shared capability summary
- [ ] remaining direct production imports are removed or explicitly isolated
- [ ] focused adapter tests pass

## Immediate next coding slice

If Batch 1 starts now, the recommended first coding slice is:

1. normalize capability payload types in `integrations/ipfs_datasets/types.py`
2. consume those types in `integrations/ipfs_datasets/capabilities.py`
3. add or tighten focused assertions in `tests/test_ipfs_adapter_types.py`

That slice has the highest leverage because every other Batch 1 task depends on the contract it establishes.