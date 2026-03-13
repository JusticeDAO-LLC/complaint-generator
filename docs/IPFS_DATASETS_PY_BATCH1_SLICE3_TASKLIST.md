# IPFS Datasets Py Batch 1 Slice 3 Task List

Date: 2026-03-13
Status: In progress

Companion docs:

- `docs/IPFS_DATASETS_PY_BATCH1_STATUS_AUDIT.md`
- `docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`

## Purpose

Turn the next recommended Batch 1 coding slice into an exact implementation task list.

This slice is now the highest-leverage remaining Batch 1 work because shared parse and archived-page corpus identity are in place, but the durable fact substrate still needs to become explicit enough that later graph and logic layers do not infer cross-source fact semantics indirectly from storage tables.

## Slice Goal

Finish shared fact-registry completion for evidence, web evidence, archived pages, and legal authorities by tightening:

- durable fact identity
- cross-source fact lineage
- review-facing fact summaries

so later graph, retrieval, contradiction, and proof workflows can consume one stable fact family across source types.

## Progress update

Completed in the current checkout:

- evidence, authority, and graph-support result contracts now expose explicit cross-source source, artifact, corpus, and parse-lineage fields
- mediator and review-facing tests now use normalized graph-support payloads instead of older minimal mock rows
- archived web evidence facts now round-trip through the shared persisted evidence fact API and are asserted as first-class members of the same durable fact contract
- focused fact-contract and downstream review validation are green

Remaining emphasis:

- keep the flattened fact contract enforced across any remaining higher-level consumers that still infer source semantics indirectly from metadata
- finish task-list and milestone closeout once the broader cross-source contract is explicit enough that later graph and logic layers can rely on it without source-family branches

## Target files

- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`
- `integrations/ipfs_datasets/types.py`
- `docs/PAYLOAD_CONTRACTS.md`
- `tests/test_evidence_hooks.py`
- `tests/test_web_evidence_hooks.py`
- `tests/test_legal_authority_hooks.py`
- `tests/test_claim_support_hooks.py`

## Exact Tasks

## Task 1: Define the remaining durable fact-contract fields

Primary files:

- `integrations/ipfs_datasets/types.py`
- `docs/PAYLOAD_CONTRACTS.md`

Work:

- identify the minimum stable fact fields that every source family should carry for later graph and logic consumers
- make artifact, chunk or passage, provenance, and claim-element linkage expectations explicit where they are already effectively required
- avoid introducing speculative graph or proof fields that belong to later batches

Done when:

- downstream consumers can rely on one durable fact contract across evidence, archived pages, fetched pages, and authority text

## Task 2: Tighten fact persistence consistency across source families

Primary files:

- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`

Work:

- verify extracted facts from each source family persist the same identity and lineage essentials
- remove any remaining source-specific gaps where one source family stores less durable fact context than the others
- preserve compatibility with existing storage tables and degraded mode

Done when:

- fact rows from all major source families expose compatible identity and lineage semantics through the current mediator-backed persistence paths

## Task 3: Normalize review-facing fact summaries

Primary file:

- `mediator/claim_support_hooks.py`

Work:

- ensure support-fact retrieval and support-trace projections preserve the same fact identity and lineage expectations across source families
- make any compact fact-oriented summary fields explicit enough for operator review and later graph consumers
- keep backward compatibility for current review payloads wherever possible

Done when:

- claim-support review flows can inspect fact-backed support without source-family-specific interpretation rules

## Task 4: Add focused cross-source fact assertions

Primary files:

- `tests/test_evidence_hooks.py`
- `tests/test_web_evidence_hooks.py`
- `tests/test_legal_authority_hooks.py`
- `tests/test_claim_support_hooks.py`

Work:

- add or tighten assertions that evidence, archived pages, fetched pages, and authority-backed facts preserve compatible identity and lineage
- verify claim-support fact retrieval surfaces the same durable fact semantics across source families
- keep existing parse, provenance, and packet assertions intact

Done when:

- the focused test suite would fail if any source family drifted away from the shared fact contract

## Task 5: Update Batch 1 documentation

Primary files:

- `docs/PAYLOAD_CONTRACTS.md`
- `docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md`
- `docs/IPFS_DATASETS_PY_BATCH1_STATUS_AUDIT.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`

Work:

- document any durable fact-contract changes that become operator-visible or integration-visible
- keep the wording aligned with the completed provenance and archived-page slices so Batch 1 reads as one coherent corpus-completion effort

Done when:

- the next remaining Batch 1 gap is clearly described as shared fact-registry completion rather than archived-page normalization

## Suggested Implementation Order

1. `integrations/ipfs_datasets/types.py`
2. `mediator/evidence_hooks.py`
3. `mediator/web_evidence_hooks.py`
4. `mediator/legal_authority_hooks.py`
5. `mediator/claim_support_hooks.py`
6. focused tests
7. `docs/PAYLOAD_CONTRACTS.md`

## Acceptance Criteria

This slice is complete when all of the following are true:

- extracted facts from evidence, archived pages, fetched pages, and authority text share one durable contract family
- claim-support review surfaces can project those facts without source-family-specific interpretation rules
- lineage remains strong enough for later graph, contradiction, and proof workflows
- existing parse, provenance, and authority fallback behavior remains intact
- focused evidence, web-evidence, authority, and claim-support tests pass

## Suggested Validation

```bash
./.venv/bin/python -m pytest tests/test_evidence_hooks.py tests/test_web_evidence_hooks.py tests/test_legal_authority_hooks.py tests/test_claim_support_hooks.py -q
```

Suggested follow-up validation if compact review payloads change:

```bash
./.venv/bin/python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py tests/test_claim_support_review_template.py -q
./.venv/bin/python -m pytest tests/test_mediator.py tests/test_cli_commands.py -q
```

## Out of Scope

Do not include these in this slice unless required by a discovered dependency:

- graph snapshot persistence redesign
- authority-treatment expansion
- GraphRAG scoring changes
- theorem-prover grounding
- broad review UI redesign outside fact-contract needs

## Stop Condition

Stop this slice once fact-backed claim support can be treated as one durable cross-source corpus substrate by later graph and logic layers.