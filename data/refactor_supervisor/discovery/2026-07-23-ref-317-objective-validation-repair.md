# REF-317 Objective Validation Repair

Date: 2026-07-23
Goal id: G3.S1
Goal title: Normalize IPFS datasets adapter payloads
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-317-objective-gap-5b5d1a6e63c3.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md
Todo vector key: 49f830b461162392
Canonical task key: task/v1/ac7b23ab143188b49e69a19a9f07a9d69b40b1e2ed058779c72654ad7738b1ec
Canonical task CID: baguqeeravr5shkyuggeljhtjugnj6b5j22nubmpc5ucyo6ohezkk25zywhwa
Merge key: eac2ce316d299bc1
Merge family: goal_packet/ops/integrations/de7d9d2f5784

## Repair Summary

The objective scan filed REF-317 because G3.S1 had all named implementation
paths and validations but no durable `objective validation repair` receipt.
REF-009 and REF-010 already own the two bounded implementation slices:

1. The capability registry is defined independently of import results, so full,
   partial, and degraded installations expose the same ordered adapter groups
   and the same status/detail keys.
2. Optional-provider failures are normalized into typed reason codes, the
   requested and missing module, raw error details, an operator-facing reason,
   and a copyable extra-install command.
3. One source-agnostic `parse_document` entry point accepts text, bytes, files,
   paths, and readable streams while preserving the legacy parser payload and
   fallback behavior.
4. Evidence and web-document ingestion already use that entry point. This
   repair also moves legal-authority ingestion from the legacy text helper to
   `parse_document`, closing the last direct ingestion bypass while retaining
   MIME detection, parser metadata, transform lineage, chunks, graph facts, and
   citation-only fallback semantics.

The focused and packet validation lanes pass. No new child goals are needed:
REF-009 and REF-010 remain the complete G3.S1 decomposition, while REF-011 and
REF-012 own the adjacent graph and logic boundaries in G3.S2.

## G3.S1 Evidence Contract

| Boundary | Authoritative implementation | Executable evidence |
| --- | --- | --- |
| Stable capability groups | `integrations/ipfs_datasets/capabilities.py`, `integrations/ipfs_datasets/types.py` | The canonical 13-group definition drives available and degraded reports. Tests compare ordered group names, outer status keys, and nested diagnostic keys across both runtime modes. |
| Actionable optional failures | `integrations/ipfs_datasets/loader.py`, `integrations/ipfs_datasets/capabilities.py` | Missing modules, API mismatches, import failures, and load failures have stable reason codes and raw diagnostics. Missing extras name the capability and dependency and provide a copyable `pip install` remediation. |
| Shared parse payload | `integrations/ipfs_datasets/documents.py`, `integrations/ipfs_datasets/provenance.py` | Text, bytes, explicit files, paths, and streams return the same status, text, chunks, summary, lineage, metadata, provider, backend, and degraded-reason structure. Invalid or ambiguous inputs fail explicitly. |
| Evidence ingestion | `mediator/evidence_hooks.py` | Uploaded evidence calls `parse_document`; the resulting summary and complete parse contract are stored with the artifact and reused for chunks, facts, and graph projection. |
| Authority ingestion | `mediator/legal_authority_hooks.py` | Authority text now calls `parse_document` directly. HTML/full-text and citation-title fallback paths preserve source identity, content origin, transform lineage, chunks, facts, and provenance. |
| Web ingestion | `mediator/web_evidence_hooks.py` | Web payloads enter the same evidence-storage parse contract with `web_document` source identity, then add archive/live-capture lineage without changing parser-owned format or quality fields. |
| Degraded behavior | `integrations/ipfs_datasets/documents.py`, `tests/test_document_ingestion_contract.py` | With document extras unavailable, deterministic local normalization still returns `fallback` payloads with text and chunks; legacy byte parsing and the shared entry point remain equivalent. |

The normalized flow is:

```text
optional provider probes
  -> stable capability/status/diagnostic payloads

evidence bytes ─┐
authority text ─┼─> parse_document -> normalized parse contract -> storage/graph facts
web documents ──┘
```

Callers consume stable fields and typed status rather than exception strings.
Missing optional packages degrade capability health but do not prevent local
document parsing or import of the mediator ingestion surfaces.

## Shared Goal Packet Coverage

REF-317 is the anchor validation gate for
`goal_packet/ops/integrations/de7d9d2f5784`, which contains G3.S1 and G3.S2.
The complete packet was checked as one adapter lifecycle:

| Goal | Shared evidence confirmed |
| --- | --- |
| G3.S1 | Every capability group reports stable keys and actionable degraded reasons. Evidence, authority, and web ingestion use one normalized parse contract, and fallback parsing preserves current behavior. |
| G3.S2 | Graph extraction, persistence, and support queries retain typed persistence/query/provenance fields and fallback coverage. Logic reports unavailable, degraded, and implemented states through structured fields instead of caller-side string matching. |

This repair does not claim REF-318 completion or replace its G3.S2-specific
receipt. It records the observed shared-packet validation needed by the
REF-317 anchor while leaving completion and generated metadata supervisor-owned.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-317-objective-validation-repair.md`
- Canonical backlog evidence: REF-317 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing G3.S1 implementation ownership: REF-009 and REF-010
- Adjacent G3.S2 implementation ownership: REF-011 and REF-012
- Shared packet validation gates: REF-317 and REF-318
- G3.S1 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md`

The heap points to this receipt and the exact missing evidence term. The
supervisor-fed todo already identifies the same goal, bundle, validation
commands, merge family, and implementation slices. Generated bundle/index
regeneration and task completion remain supervisor-owned; this repair does not
manually change REF-317 or REF-318 status.

## Validation

- PASS — required adapter lane: 73 tests.
- PASS — required document-pipeline lane: 68 passed, 2 skipped.
- PASS — shared parse and full authority regression lane: 42 tests.
- PASS — web-ingestion regression lane: 31 tests.
- PASS — shared graph/fallback lane: 152 tests.
- PASS — shared logic dependency lane: 2 tests.

All commands exited successfully. Runs emitted only existing deprecation and
syntax warnings; the two document-pipeline skips are existing optional-path
skips, not failures.
