# IPFS Datasets Py Batch 1 Status Audit

Date: 2026-03-12
Status: Current-state audit against Batch 1

Companion docs:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`
- `docs/IPFS_DATASETS_PY_BATCH1_SLICE1_TASKLIST.md`
- `docs/IPFS_DATASETS_PY_BATCH1_SLICE2_TASKLIST.md`

## Purpose

Audit the current repository against Batch 1, parse completion and corpus unification, so the next coding slice is selected from verified gaps instead of assumptions.

This audit scores each Batch 1 slice as:

- `Complete`: implemented strongly enough to treat as baseline
- `Partial`: materially implemented, but still missing contract completion or cross-source consistency
- `Missing`: not meaningfully present yet

## Executive Summary

Batch 1 is not starting from zero.

The current repo already has a real shared parse substrate, legal-authority parsing, web-evidence parse reporting, fact persistence, and claim-support consumption of enriched fact and graph-trace data.

The main remaining Batch 1 work is not “add parsing.” It is to finish contract completion in the areas most likely to fragment the case corpus:

1. archive-specific provenance and timeline normalization for web evidence
2. full cross-source lineage consistency across uploads, archived pages, and authority text
3. durable fact-model consistency so later graph and logic work does not need source-family exceptions
4. stronger parse metadata for richer formats such as PDF, DOCX, RTF, and email-style sources where page- or passage-level review matters

## Batch 1 Slice Scorecard

| Slice | Status | Summary |
|---|---|---|
| Slice 1: Canonical parse envelope completion | Partial | The shared parse contract exists and is already used, but richer format-level semantics and stronger page- or passage-oriented metadata are still incomplete. |
| Slice 2: Provenance and transform-lineage alignment | Complete | Provenance records now carry durable normalized metadata, archived web evidence and authority text persist that metadata, and claim-support review summaries consume provenance-backed lineage consistently. |
| Slice 3: Archived-page corpus normalization | Complete | Web evidence, authority provenance, and claim-support summaries now carry explicit corpus and artifact identity for archived versus live web artifacts and authority-backed artifacts. |
| Slice 4: Legal authority text as corpus asset | Mostly Complete | Authority text parsing, chunks, facts, and graph metadata already exist, but passage-level review semantics and explicit fallback distinctions can still be improved. |
| Slice 5: Shared fact-registry completion | Partial | Evidence, authority, and archived web evidence facts already flow through the same persisted fact substrate, but Batch 1 still needs stronger cross-source enforcement and clearer documentation of that shared contract. |

## Detailed Findings

## Slice 1: Canonical parse envelope completion

Status: Partial

### What is already true

- `integrations/ipfs_datasets/documents.py` already exposes `parse_document_text(...)`, `parse_document_bytes(...)`, and `parse_document_file(...)`.
- `DocumentParseResult` is already being emitted as the shared typed contract.
- the adapter already normalizes several important input families:
  - plain text
  - HTML
  - RTF
  - email-style payloads
  - DOCX
  - PDF fallback extraction
- parse output already includes:
  - normalized text
  - chunk rows
  - parse summary
  - transform lineage
  - metadata including parser version, input format, chunk count, and source

### Evidence supporting that assessment

- `integrations/ipfs_datasets/documents.py` builds `DocumentParseResult` with `summary`, `lineage`, and `metadata`.
- `tests/test_web_evidence_hooks.py` already asserts request-level `parse_summary` and per-record `parse_details`.
- `tests/test_legal_authority_hooks.py` already asserts persisted parser version, parse source, and transform lineage on authority records.

### What is still missing or incomplete

- page-oriented semantics are still weak for richer source families where later review and proof workflows may need passage fidelity.
- OCR and format-specific quality signals are not yet exposed as a clearly complete contract family.
- office-document behavior is normalized behind the adapter in part, but Batch 1 still needs to confirm there are no remaining hook-local format assumptions.
- the current parse envelope is strong enough for fallback workflows, but not yet obviously complete for citation-grade passage review across all supported formats.

### Audit conclusion

The parse envelope exists and is already useful, but it should still be treated as a contract-completion pass rather than as fully finished baseline for every richer format and passage-fidelity use case.

## Slice 2: Provenance and transform-lineage alignment

Status: Complete

### What is already true

- `integrations/ipfs_datasets/provenance.py` already exposes shared helpers for:
  - provenance records
  - content hashing
  - document parse contract construction
  - fact-lineage metadata
- parse-level lineage already preserves source, parser version, input format, and transform lineage.
- metadata merging already supports source, transform lineage, and storage-level parse metadata.

### Evidence supporting that assessment

- `build_document_parse_contract(...)` returns a shared structure containing status, source, chunk count, summary, storage metadata, and lineage.
- `build_fact_lineage_metadata(...)` already injects parse-lineage information into persisted fact metadata.
- `tests/test_web_evidence_hooks.py` and `tests/test_legal_authority_hooks.py` already validate lineage fields such as source and parser version.

### What is now true

- `ProvenanceRecord` carries a durable `metadata` payload in addition to the coarse core provenance fields.
- archived web evidence persists normalized archive context such as capture source, archive URL, version relationship, capture time, and observed time in durable provenance metadata.
- legal authority storage persists normalized source-context metadata such as `authority_full_text` versus `authority_reference_fallback`, `content_source_field`, `fallback_mode`, and `text_available`.
- claim-support packet and trace summaries fall back to provenance-backed normalized record summaries when fact-level lineage is missing or sparse.

### Remaining caveats

- later timeline or archive-comparison workflows may still want richer archived-page-specific drilldown than the current compact lineage summaries expose.
- broader source-family guarantees still depend on finishing the remaining archived-page and shared fact-registry slices.

### Audit conclusion

The shared provenance substrate and cross-source lineage normalization pass are complete for the current Batch 1 contract. Remaining Batch 1 work should move to archived-page corpus behavior and broader shared fact-registry guarantees rather than reopening provenance basics.

## Slice 3: Archived-page corpus normalization

Status: Complete

### What is already true

- web evidence already routes through the evidence storage path instead of remaining only transient search results.
- web evidence storage records already include parse source and parse-document intent.
- web-evidence responses already expose parse details and parse summaries.
- archived discovery modes such as `archived_domain_scrape` already exist in the search and storage workflow.

### Evidence supporting that assessment

- `mediator/web_evidence_hooks.py` builds parse detail from `document_parse_contract` and exposes request-level parse aggregation.
- tests already assert parse summaries, parser versions, and lineage source for web evidence.
- tests also confirm archived-domain discovery results exist as a source family.

### What is now true

- web evidence lineage now persists explicit `corpus_family='web_page'` and stable `artifact_family` identity for live versus archived captures.
- archived-page provenance metadata already preserves capture source, archive URL, version relationship, capture time, and observed time through the durable provenance path.
- legal-authority provenance metadata now persists explicit artifact identity for full-text versus citation-fallback authority records, which keeps support summaries aligned across source families.
- claim-support packet and trace summaries now expose `artifact_family_counts`, so review flows can distinguish archived web pages from live web pages and authority-backed artifacts without inferring from `content_origin`.
- support-summary normalization backfills artifact identity from existing `content_origin` values for older stored records that predate the explicit fields.

### Audit conclusion

Archived pages now participate in the system as first-class corpus artifacts strongly enough for the current Batch 1 contract. Remaining Batch 1 work should move to the shared fact-registry pass.

## Slice 4: Legal authority text as corpus asset

Status: Mostly Complete

### What is already true

- legal-authority ingestion already parses authority text through `parse_document_text(...)`.
- authority metadata already stores:
  - `document_parse_summary`
  - `document_parse_contract`
  - persisted `parse_metadata`
  - persisted `graph_metadata`
- authority chunks are persisted.
- authority facts are persisted.
- authority graph entities and relationships are persisted.
- authority rows already expose `fact_count`, and `get_authority_facts(...)` already returns persisted fact rows.

### Evidence supporting that assessment

- `mediator/legal_authority_hooks.py` contains `_parse_authority_text(...)`, `_store_authority_chunks(...)`, and `_store_authority_facts(...)`.
- `tests/test_legal_authority_hooks.py` asserts parser version, parse source, transform lineage, graph metadata, and fact counts on stored authorities.

### What is still missing or incomplete

- authority parsing currently uses plain-text treatment of authority text rather than a richer authority-document specialization.
- passage-level provenance is present indirectly through chunk and fact linkage, but can still be made more explicit for later adverse-authority and predicate review.
- citation-only fallback remains necessary for missing text, and that fallback can still be made more explicit in operator-facing contracts.

### Audit conclusion

This is the strongest Batch 1 slice today. The right move is to treat it as mostly complete and only refine the remaining passage-level and fallback semantics.

## Slice 5: Shared fact-registry completion

Status: Partial

### What is already true

- claim support already consumes cross-source facts.
- `get_claim_support_facts(...)` already exists.
- claim-support flows already enrich fact rows with source table, support metadata, and graph trace.
- review and claim-support tests already validate:
  - enriched fact rows
  - graph-trace propagation
  - fact counts
  - support-trace aggregation

### Evidence supporting that assessment

- `mediator/claim_support_hooks.py` already builds enriched fact rows and graph traces across evidence and authority links.
- `tests/test_claim_support_hooks.py` asserts `get_claim_support_facts(...)`, `support_facts`, fact counts, and graph-trace lineage.

### What is still missing or incomplete

- archived-page facts now round-trip through the shared persisted evidence fact API with explicit artifact, corpus, and parse-lineage fields, but Batch 1 still needs to keep that contract enforced consistently across the remaining higher-level consumers.
- future graph and logic layers still risk needing source-family exceptions unless fact lineage and source semantics are tightened further.
- the current fact substrate is mediator-usable, but not yet clearly documented and enforced as the one durable corpus fact family for all acquisition paths.

### Audit conclusion

The shared fact registry is already real. Batch 1 should finish it by tightening cross-source guarantees, not by rebuilding it.

## Recommended Next Coding Slice

Based on the current audit, the highest-leverage next slice is:

1. `integrations/ipfs_datasets/types.py`
2. `mediator/evidence_hooks.py`
3. `mediator/web_evidence_hooks.py`
4. `mediator/legal_authority_hooks.py`
5. `mediator/claim_support_hooks.py`
6. focused `tests/test_evidence_hooks.py`
7. focused `tests/test_web_evidence_hooks.py`
8. focused `tests/test_legal_authority_hooks.py`
9. focused `tests/test_claim_support_hooks.py`
10. `docs/PAYLOAD_CONTRACTS.md`
11. Batch 1 planning docs touched by shared fact-registry semantics

### Why this slice is best

- parse, provenance, and archived-page corpus identity are now stable enough that the main remaining Batch 1 risk is fact-contract drift across source families
- the current registry already spans evidence, archived pages, and authorities operationally, so the next gains come from tightening identity and lineage guarantees rather than inventing a new substrate
- graph, contradiction, and proof work will stay simpler if they can consume one explicit fact family instead of reconstructing source semantics from storage tables
- this keeps Batch 1 focused on corpus completion without prematurely pulling in Batch 2 or graph-store redesign work

## Recommended status changes to planning assumptions

These statements should be treated as true for future planning:

- Batch 1 is not “implement shared parsing”; it is “complete and normalize the shared corpus contract”
- legal authority text is already largely a corpus asset when source text is available
- claim-support already has a real cross-source fact substrate
- the biggest remaining Batch 1 weakness is that the shared fact substrate is still stronger in practice than it is as an explicit cross-source contract

## Exit Criteria Reframed For Batch 1

Batch 1 should be considered complete when:

- uploads, fetched pages, archived pages, and authority text all behave like one parse-and-lineage family
- archived-page lineage is normalized enough to support later timeline and contradiction drilldown
- authority text fallback versus full-text corpus behavior is explicit and stable
- claim-support facts can be treated as one durable cross-source corpus substrate by later graph and logic layers

## Final Assessment

Batch 1 is materially underway.

The current repo already contains most of the infrastructure needed for parse completion and corpus unification. The remaining work is mainly contract tightening and lineage completion, especially for archived web material and cross-source fact durability.

That is a good position to be in. It means the next code changes should produce visible structural gains without reopening the entire integration design.