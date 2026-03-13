# IPFS Datasets Py Batch 1 Slice 1 Task List

Date: 2026-03-12
Status: Complete

Completion summary:

- shared provenance records now carry normalized metadata for archive and authority source context
- web evidence persists archive lineage in durable provenance and parse contracts
- legal authority storage persists full-text versus citation-fallback semantics in durable provenance
- claim-support packet and trace summaries now fall back to provenance-backed record summaries when fact-level lineage is sparse
- focused and downstream validation passed across provenance, web evidence, authority, claim support, review, mediator, and CLI surfaces

Companion docs:

- `docs/IPFS_DATASETS_PY_BATCH1_STATUS_AUDIT.md`
- `docs/IPFS_DATASETS_PY_BATCH1_IMPLEMENTATION_PLAN.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`

## Purpose

Turn the recommended next Batch 1 coding slice into an exact implementation task list.

This slice is the highest-leverage remaining Batch 1 work because the shared parse substrate already exists. The main remaining risk is provenance and lineage drift across archived web evidence and legal-authority text.

## Slice Goal

Normalize provenance and transform-lineage handling for:

- archived and fetched web evidence
- legal authority text with full-text parsing

so both source families behave more like one shared case-corpus contract.

## Target files

- `integrations/ipfs_datasets/provenance.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `tests/test_web_evidence_hooks.py`
- `tests/test_legal_authority_hooks.py`

## Exact Tasks

## Task 1: Expand provenance normalization helpers

Primary file:

- `integrations/ipfs_datasets/provenance.py`

Work:

- standardize a richer lineage payload for parse-backed artifacts
- ensure the shared helpers can carry:
  - `source`
  - `source_system`
  - `acquisition_method`
  - `source_type`
  - `content_hash` when available
  - archive-oriented metadata such as capture timestamp or archive source when available
- ensure helper output stays backward-compatible for existing evidence and authority consumers

Done when:

- one helper family can build storage and fact-lineage metadata for both archived web evidence and authority text without source-family-specific post-processing

## Task 2: Normalize archived web evidence lineage

Primary file:

- `mediator/web_evidence_hooks.py`

Work:

- ensure stored web evidence distinguishes live fetches from archived captures in normalized metadata rather than only source-type-specific loose fields
- preserve archive-context metadata in the stored parse contract or storage metadata when available
- make parse details and parse summaries reflect consistent lineage for archived and non-archived web evidence
- keep current compact parse reporting stable while improving the underlying contract

Done when:

- archived web evidence records can be recognized as first-class corpus artifacts with explicit acquisition and history context

## Task 3: Tighten legal-authority lineage and fallback semantics

Primary file:

- `mediator/legal_authority_hooks.py`

Work:

- ensure authority full-text parsing preserves the same lineage fields expected from other corpus artifacts
- make full-text versus citation-only fallback behavior explicit in stored parse metadata
- preserve enough passage-level lineage that later support, contradiction, and predicate review can tell whether a fact came from parsed full text or fallback title or citation material

Done when:

- stored authority rows clearly distinguish parsed-text corpus assets from citation-only fallback records

## Task 4: Add focused archived-web provenance assertions

Primary file:

- `tests/test_web_evidence_hooks.py`

Work:

- add or tighten tests around archived and fetched web evidence provenance normalization
- assert that parse detail or stored metadata exposes the expected lineage fields for web evidence
- keep existing parse-summary expectations intact

Done when:

- the test suite would fail if archived web evidence regressed back into a looser or inconsistent metadata shape

## Task 5: Add focused authority-lineage assertions

Primary file:

- `tests/test_legal_authority_hooks.py`

Work:

- add or tighten assertions that authority parse metadata preserves normalized lineage fields
- assert explicit fallback semantics when full text is absent if the implementation exposes them
- keep existing fact-count, chunk, and graph-metadata expectations intact

Done when:

- the test suite would fail if authority text parsing stopped looking like a shared corpus artifact

## Suggested Implementation Order

1. `integrations/ipfs_datasets/provenance.py`
2. `mediator/web_evidence_hooks.py`
3. `mediator/legal_authority_hooks.py`
4. `tests/test_web_evidence_hooks.py`
5. `tests/test_legal_authority_hooks.py`

## Acceptance Criteria

This slice is complete when all of the following are true:

- archived web evidence has explicit normalized lineage beyond a loose source type label
- legal authority full-text parsing preserves the same lineage family expected of other corpus artifacts
- authority fallback behavior is explicit enough that later consumers can distinguish parsed-text support from citation-only support
- existing parse-summary and fact-persistence behavior remains intact
- focused web-evidence and legal-authority tests pass

## Suggested Validation

```bash
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q
```

Optional follow-up validation if support-fact lineage changes:

```bash
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
./.venv/bin/python -m pytest tests/test_review_api.py -q
```

## Out of Scope

Do not include these in this slice unless required by a discovered dependency:

- graph snapshot persistence redesign
- GraphRAG scoring
- theorem-prover adapter implementation
- review packet drilldown productization
- broad payload-contract redesign in `docs/PAYLOAD_CONTRACTS.md`

## Stop Condition

Stop this slice once provenance normalization is stable enough that later graph and logic work can rely on archived web evidence and authority text behaving like the same corpus family.

Completed validation:

```bash
./.venv/bin/python -m pytest tests/test_ipfs_provenance.py tests/test_web_evidence_hooks.py tests/test_legal_authority_hooks.py tests/test_claim_support_hooks.py tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py tests/test_claim_support_review_template.py tests/test_mediator.py tests/test_cli_commands.py -q
```