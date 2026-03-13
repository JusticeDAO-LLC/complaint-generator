# IPFS Datasets Py Batch 1 Slice 2 Task List

Date: 2026-03-12
Status: Completed 2026-03-13

Companion docs:

- `docs/IPFS_DATASETS_PY_BATCH1_STATUS_AUDIT.md`
- `docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`

## Purpose

Turn the next recommended Batch 1 coding slice into an exact implementation task list.

This slice is the highest-leverage remaining Batch 1 work because provenance normalization is now complete enough that the main remaining corpus risk is archived-page behavior drifting into an evidence-adjacent special case.

## Slice Goal

Normalize archived and fetched web pages into a first-class shared corpus artifact family by tightening:

- archived-page storage semantics
- archived-page review semantics
- archived-page support and fact semantics

so later graph, review, and logic workflows do not need to treat archived pages as a weaker subtype of uploaded evidence.

## Target files

- `mediator/web_evidence_hooks.py`
- `mediator/claim_support_hooks.py`
- `tests/test_web_evidence_hooks.py`
- `tests/test_claim_support_hooks.py`
- `docs/PAYLOAD_CONTRACTS.md`

## Exact Tasks

## Task 1: Tighten archived-page corpus identity in web evidence storage

Primary file:

- `mediator/web_evidence_hooks.py`

Work:

- ensure archived captures and live fetches are distinguished as durable corpus artifacts, not only as loose search result types
- standardize archived-page metadata needed for later corpus consumers, including archive-versus-live identity, historical markers, and version relationships
- keep storage behavior compatible with existing evidence-backed persistence paths while making archived-page semantics explicit

Done when:

- stored web evidence rows expose a stable archived-page identity that later support, graph, and review consumers can rely on without source-family heuristics

## Task 2: Promote archived-page support packets beyond evidence-adjacent lineage

Primary file:

- `mediator/claim_support_hooks.py`

Work:

- ensure support packets and review-facing summaries can treat archived pages as first-class support artifacts rather than only ordinary evidence rows with extra lineage
- make archived-page packet summaries reflect historical-context semantics clearly enough for operator review and later timeline drilldown
- preserve backward compatibility for existing support-trace and compact summary payloads

Done when:

- claim-support review surfaces can distinguish archived-page support as a real corpus artifact family without branching on raw storage tables

## Task 3: Tighten archived-page fact and trace guarantees

Primary files:

- `mediator/web_evidence_hooks.py`
- `mediator/claim_support_hooks.py`

Work:

- confirm archived-page facts participate in the same durable support and trace model as uploaded evidence facts
- ensure archived-page fact lineage remains strong enough for contradiction review, support review, and later predicate grounding
- remove any remaining assumptions that archived-page support is only useful as a document-level link and not a fact-bearing corpus record

Done when:

- archived-page support can be consumed as ordinary fact-backed claim support instead of a weaker review-only attachment

## Task 4: Add focused archived-page corpus assertions

Primary file:

- `tests/test_web_evidence_hooks.py`

Work:

- add or tighten assertions that archived captures retain first-class corpus semantics through storage and response payloads
- verify live-versus-archived distinctions remain explicit in operator-visible payloads
- keep current parse and provenance assertions intact

Done when:

- the test suite would fail if archived pages regressed into a weaker or more ad hoc storage shape

## Task 5: Add focused claim-support assertions for archived-page corpus behavior

Primary file:

- `tests/test_claim_support_hooks.py`

Work:

- add or tighten assertions that archived-page support traces, packets, and summaries behave like ordinary durable support artifacts
- verify archived-page fact and lineage summaries survive into claim-support review outputs
- keep existing evidence and authority support expectations intact

Done when:

- the test suite would fail if archived-page claim support stopped behaving like the shared corpus contract

## Task 6: Update payload and planning documentation

Primary file:

- `docs/PAYLOAD_CONTRACTS.md`

Work:

- document any new archived-page corpus semantics added to support packets, review summaries, or storage-facing payloads
- keep the wording aligned with the completed provenance-normalization slice so the docs describe one coherent Batch 1 contract

Done when:

- archived-page corpus semantics are documented where external or operator-visible payloads changed

## Suggested Implementation Order

1. `mediator/web_evidence_hooks.py`
2. `mediator/claim_support_hooks.py`
3. `tests/test_web_evidence_hooks.py`
4. `tests/test_claim_support_hooks.py`
5. `docs/PAYLOAD_CONTRACTS.md`

## Acceptance Criteria

This slice is complete when all of the following are true:

- archived web pages behave like first-class corpus artifacts instead of only evidence-like rows with extra provenance
- claim-support review surfaces preserve archived-page support as fact-bearing, lineage-rich corpus support
- live-versus-archived distinctions remain explicit in operator-visible payloads
- existing evidence and authority support behavior remains intact
- focused web-evidence and claim-support tests pass

## Suggested Validation

```bash
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
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
- theorem-prover adapter work
- operator drilldown productization beyond corpus-contract needs
- broad review payload redesign outside archived-page corpus semantics

## Stop Condition

Stop this slice once archived-page storage, support packets, and support traces behave strongly enough that later graph and logic work can treat archived pages as first-class shared corpus artifacts.

## Completion Notes

Completed in the current checkout on 2026-03-13.

Implemented outcomes:

- web evidence lineage now carries explicit `corpus_family='web_page'` plus stable `artifact_family` identity for live versus archived captures
- legal-authority provenance metadata now carries explicit `corpus_family='legal_authority'` and `artifact_family` identity for full-text versus citation-fallback authority records
- claim-support packet and trace summaries now surface `artifact_family_counts` so downstream review flows do not need to infer artifact class from `content_origin` alone
- claim-support normalization now backfills artifact identity from older `content_origin` values so legacy stored records remain compatible with the new summaries

Validated with:

```bash
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py tests/test_claim_support_hooks.py tests/test_legal_authority_hooks.py -q
./.venv/bin/python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py tests/test_claim_support_review_template.py tests/test_mediator.py tests/test_cli_commands.py -q
```