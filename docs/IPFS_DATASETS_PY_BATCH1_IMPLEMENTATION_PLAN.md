# IPFS Datasets Py Batch 1 Implementation Plan

Date: 2026-03-12
Status: In progress; provenance-normalization and archived-page corpus slices completed, shared fact-registry slice next

Companion docs:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`
- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`
- `docs/IPFS_DATASETS_PY_BATCH1_STATUS_AUDIT.md`
- `docs/IPFS_DATASETS_PY_BATCH1_SLICE1_TASKLIST.md`
- `docs/IPFS_DATASETS_PY_BATCH1_SLICE2_TASKLIST.md`
- `docs/IPFS_DATASETS_PY_BATCH1_SLICE3_TASKLIST.md`

## Purpose

Turn the current Batch 1, parse completion and corpus unification, into issue-sized implementation slices that can be executed without reopening architecture questions.

This plan assumes the current repository state described in the companion docs is accurate:

- adapter hardening and capability normalization are already substantially complete
- evidence, web evidence, and legal-authority flows already consume adapter-backed integrations in part
- typed parse and graph contracts already exist under `integrations/ipfs_datasets/types.py`
- later batches depend on Batch 1 producing one dependable artifact, chunk, fact, and provenance model across source families

## Batch 1 outcome

At the end of Batch 1, complaint-generator should have one stable parse and corpus contract family for:

- uploaded evidence
- discovered and scraped web pages
- archived captures
- legal authority text when source text is available

The main success criterion is that graph, retrieval, GraphRAG, and proof workflows can consume the same artifact, chunk, fact, and provenance model regardless of source family.

## Non-goals

Batch 1 should not attempt to:

- redesign adapter capability reporting
- add full graph-store persistence
- add GraphRAG support scoring
- implement theorem-prover workflows end to end
- build the full operator drilldown workspace

If a change is primarily about graph-path scoring, theorem-prover orchestration, or review packet productization, it belongs to later batches.

## Target files

- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/provenance.py`
- `integrations/ipfs_datasets/types.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`
- `tests/test_evidence_hooks.py`
- `tests/test_web_evidence_hooks.py`
- `tests/test_legal_authority_hooks.py`
- `tests/test_claim_support_hooks.py`

## Implementation slices

## Slice 1: Canonical parse envelope completion

Goal:

- finish the shared parse contract so all major ingestion paths produce the same parse envelope

Primary files:

- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/types.py`

Tasks:

- ensure bytes, file-path, fetched-page, and authority-text parsing return one canonical `DocumentParseResult` family
- standardize parse summary fields for content type, extraction mode, OCR usage, page count, chunk count, and warnings
- standardize chunk identity, offsets, page references, and section labels where available
- preserve degraded behavior when format-specific extras are unavailable

Done when:

- downstream callers can treat parse output identically across evidence, web evidence, archived pages, and authority text
- hook code no longer needs source-family-specific parse-shape logic

Suggested issue title:

- `Complete canonical parse envelope across all case artifact families`

## Slice 2: Provenance and transform-lineage alignment

Goal:

- align provenance and lineage metadata so all artifacts can be traced across acquisition, parsing, and later extraction stages

Primary files:

- `integrations/ipfs_datasets/provenance.py`
- `integrations/ipfs_datasets/types.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`

Tasks:

- standardize acquisition method, source system, content hash, archive metadata, and parse-source fields
- preserve transform lineage for parse, graph extraction, and future logic translation stages
- ensure archived pages and authority text use the same provenance model as uploaded evidence
- preserve passage-level lineage needed for later support, contradiction, and predicate review

Done when:

- every stored artifact and authority can be traced from acquisition source through parse stage using one lineage model

Suggested issue title:

- `Unify artifact provenance and transform lineage across evidence, archives, and authorities`

Current status:

- completed in the current checkout
- durable provenance metadata now preserves archive-capture context for web evidence and full-text versus citation-fallback semantics for legal authorities
- claim-support review summaries now consume provenance-backed normalized record summaries instead of relying only on parse-lineage fields

## Slice 3: Archived-page corpus normalization

Goal:

- make archived and fetched web pages first-class case artifacts rather than adjacent evidence-like records

Primary files:

- `mediator/web_evidence_hooks.py`
- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/provenance.py`
- `mediator/claim_support_hooks.py`

Tasks:

- ensure fetched and archived page content routes through the shared parse contract
- preserve archive-specific provenance such as capture source, archive timestamp, and historical-context markers
- ensure web evidence storage produces chunk, fact, and parse outputs compatible with uploaded evidence
- surface enough live-versus-archived lineage for later review and timeline drilldown

Done when:

- archived pages can participate in claim support and follow-up review as ordinary corpus artifacts

Suggested issue title:

- `Normalize archived and fetched web pages into the shared case corpus`

Current status:

- completed in the current checkout
- web evidence lineage now persists explicit `corpus_family='web_page'` plus stable `artifact_family` identity for live versus archived captures
- legal-authority provenance metadata now persists explicit artifact identity for full-text versus citation-fallback authority records
- claim-support packet and trace summaries now expose `artifact_family_counts`, with compatibility fallback for older records that only persisted `content_origin`

## Slice 4: Legal authority text as corpus asset

Goal:

- make legal authorities behave like parseable corpus assets whenever full text is available

Primary files:

- `mediator/legal_authority_hooks.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/provenance.py`

Tasks:

- ensure authority text parsing uses the same parse family as evidence and archived pages
- preserve authority parse summaries, chunks, facts, and graph metadata through one normalized contract
- capture passage-level provenance needed for adverse-authority review, contradiction checks, and later predicate grounding
- keep citation-only fallback behavior explicit when source text is unavailable

Done when:

- authorities with source text can participate in chunk-, fact-, and passage-level support review instead of remaining citation-only records

Suggested issue title:

- `Promote legal authority full text into the shared parse and corpus pipeline`

## Slice 5: Shared fact-registry completion

Goal:

- finish the transition from source-specific extracted facts to one durable case fact model

Primary files:

- `mediator/claim_support_hooks.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `integrations/ipfs_datasets/types.py`

Tasks:

- ensure facts derived from uploaded evidence, archived pages, fetched pages, and authority text share one durable contract
- link facts to artifacts, claim elements, chunks or passage spans, and future graph or validation outputs
- preserve enough lineage that later graph and logic consumers do not need source-family exceptions
- keep review and follow-up payloads compatible while upgrading the source fact substrate underneath them

Done when:

- claim-element support can enumerate artifact-backed facts across all acquisition paths using one durable fact model

Suggested issue title:

- `Complete shared fact registry across evidence, archives, and authority text`

Current status:

- in progress
- archived-page corpus identity is now explicit, and archived web evidence facts now round-trip through the shared persisted evidence fact API with the same explicit artifact, corpus, and parse-lineage fields asserted for the broader fact contract
- the remaining Batch 1 gap is broader cross-source enforcement and documentation so later graph and logic consumers can treat that fact substrate as one durable family without source-specific assumptions

## Recommended execution order

1. Slice 1
2. Slice 2
3. Slice 3
4. Slice 4
5. Slice 5

This order matters because parse-envelope completion and lineage alignment should land before archived-page and authority normalization, and the fact-registry pass should sit on top of those contracts.

## Validation plan

Minimum focused validation after each slice:

```bash
./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q
```

Additional Batch 1 corpus validation:

```bash
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
./.venv/bin/python -m pytest tests/test_review_api.py -q
```

Use the claim-support and review slice when parse, fact, or provenance changes alter the support substrate rather than only ingestion.

## Stop or go criteria

Go to Batch 2 only when all of the following are true:

- uploaded evidence, archived pages, fetched pages, and authority text all emit one compatible parse-result family
- provenance and transform-lineage fields are structurally aligned across source families
- archived pages and authority text participate in the shared case corpus rather than as special cases
- the shared fact registry can enumerate cross-source facts for claim-element support
- focused evidence, web-evidence, authority, and claim-support tests pass without source-family-specific shape workarounds

Do not start Batch 2 if the graph and support-query work would still need to branch on different parse, chunk, or fact shapes by source family.

## Risks

### Risk: source-family edge cases reopen contract drift

Mitigation:

- treat Batch 1 as a contract-completion pass, not a feature-sprawl pass
- standardize parse and provenance fields before deepening later graph and proof work

### Risk: archived or authority text behaves like a special-case ingestion path

Mitigation:

- force all available source text through the shared parse contract
- keep citation-only or metadata-only fallback explicit rather than hidden in divergent shapes

### Risk: downstream support logic inherits weak lineage

Mitigation:

- require chunk- or passage-level lineage where available
- keep fact records linked to source artifacts and claim elements from the start

## Deliverable checklist

- [ ] one canonical parse envelope across source families
- [ ] one provenance and transform-lineage model across source families
- [ ] archived and fetched web pages normalized into the shared case corpus
- [ ] legal authority full text normalized into the shared case corpus
- [ ] shared fact registry completed across evidence, archives, and authority text
- [ ] focused ingestion and claim-support tests pass

## Recommended next coding slice

Given the current checkout, the recommended next Batch 1 coding slice is:

1. `mediator/web_evidence_hooks.py`
2. `mediator/claim_support_hooks.py`
3. `tests/test_web_evidence_hooks.py`
4. `tests/test_claim_support_hooks.py`
5. `docs/PAYLOAD_CONTRACTS.md`

That slice had the highest leverage because provenance normalization was stable enough that the main remaining Batch 1 risk was archived-page corpus behavior drifting into an evidence-adjacent special case. Archived-page storage, support packets, and fact-backed review semantics are now covered more explicitly, so the remaining leverage is in keeping the broader cross-source fact contract enforced and documented without prematurely pulling in Batch 2 or graph-store redesign work.