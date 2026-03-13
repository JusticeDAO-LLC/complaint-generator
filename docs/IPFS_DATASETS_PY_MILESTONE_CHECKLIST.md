# IPFS Datasets Py Milestone Checklist

Date: 2026-03-12

## Purpose

Turn the `ipfs_datasets_py` roadmap into a milestone-by-milestone execution checklist with concrete file targets, acceptance criteria, and validation expectations.

Use this with:

- `docs/IPFS_DATASETS_PY_INTEGRATION.md`
- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_DEPENDENCY_MAP.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`
- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`

## How To Use This Checklist

- treat each milestone as a release-quality integration slice, not a loose theme
- do not start a later milestone until the earlier milestone exposes stable mediator-visible outputs
- keep `integrations/ipfs_datasets/` as the only production boundary to `ipfs_datasets_py`
- require degraded-mode behavior and focused tests for every milestone

## M0: Adapter and Capability Hardening

Goal:

- stabilize runtime-mode handling and eliminate production import drift before deepening parsing, graphs, or reasoning

Primary files:

- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/loader.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/search.py`
- `integrations/ipfs_datasets/graphs.py`
- `integrations/ipfs_datasets/logic.py`
- `mediator/mediator.py`

Checklist:

- [x] capability entries are stable for documents, knowledge graphs, GraphRAG, logic tools, vector store, and MCP gateway
- [x] degraded-reason payloads use a consistent shape across adapters
- [x] mediator startup logs one consistent capability summary across full, partial, and degraded modes
- [x] no production module imports `ipfs_datasets_py` internals directly outside `integrations/ipfs_datasets/`
- [x] direct production `sys.path` mutation is removed or explicitly isolated to the adapter loader vendored-import fallback

Acceptance criteria:

- complaint-generator starts cleanly with or without optional `ipfs_datasets_py` extras
- missing features degrade into explicit capability payloads rather than import errors
- adapter loader path setup is limited to vendored import fallback instead of eager mutation during routine capability probing

Validation:

- focused adapter tests for capability payloads
- mediator startup smoke checks
- targeted search to confirm no direct production imports remain

Suggested focused validation:

- `./.venv/bin/python -m pytest tests/test_ipfs_adapter_layer.py -q`
- `./.venv/bin/python -m pytest tests/test_ipfs_adapter_types.py -q`

## M1: Shared Parse and Corpus Contract

Goal:

- make `documents.py` the canonical parse layer for uploaded evidence, archived pages, and legal texts

Status:

- core parse contract, provenance alignment, and archived-page corpus identity are implemented and runtime-validated in the current checkout

Primary files:

- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/types.py`
- `integrations/ipfs_datasets/provenance.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`

Checklist:

- [x] `documents.py` accepts raw bytes, file paths, and fetched page payloads through one normalized contract
- [x] parse outputs include normalized text, chunk rows, parse summary, and transform lineage fields
- [x] evidence ingestion routes through the shared parse contract instead of hook-local parse shapes
- [x] web evidence ingestion routes through the shared parse contract instead of hook-local parse shapes
- [x] legal authority text uses the same parse family when source text is available
- [x] provenance fields align across evidence, archived pages, and authority text
- [ ] PDF, DOCX, RTF, HTML, email, and office-document parsing behavior is fully encapsulated inside the adapter layer with no hook-local format branching
- [ ] the existing fact registry is extended into one explicit cross-source durable fact contract; archived pages already flow through the evidence-backed fact path, now carry explicit corpus identity, and are asserted through the shared persisted evidence fact API

Acceptance criteria:

- uploaded evidence, discovered web evidence, and parsed authority text produce one contract family for downstream graph and logic consumers
- document-format handling does not leak into mediator orchestration code

Validation:

- focused parse tests for text, HTML, and PDF where available
- focused mediator tests for evidence, web evidence, and authority parsing payloads
- payload contract updates in `docs/PAYLOAD_CONTRACTS.md` when externally visible fields change

Suggested focused validation:

- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q`

## M2: Persistent Support and Graph Query Plane

Goal:

- move from fallback graph extraction to persisted support traces and reviewable graph-backed support queries

Status:

- typed graph payload, graph snapshot, and graph-support result contracts are now implemented at the adapter boundary; created-versus-reused snapshot semantics flow through storage and mediator projection payloads, and review coverage summaries now aggregate graph-trace lineage

Primary files:

- `integrations/ipfs_datasets/graphs.py`
- `mediator/claim_support_hooks.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `mediator/mediator.py`
- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`

Checklist:

- [x] graph snapshot contracts exist behind the adapter boundary
- [x] graph persistence semantics distinguish created versus reused graph content
- [x] support-query APIs can enumerate artifacts, authorities, and facts supporting a claim element
- [x] graph-support outputs preserve lineage back to source artifacts and authority records
- [x] coverage-matrix semantics are defined for mediator review and drafting readiness
- [x] support queries expose duplicate and semantic-cluster context, not just raw counts

Acceptance criteria:

- mediator review flows can explain why a claim element is covered, partial, or missing using provenance-backed support traces

Validation:

- focused graph adapter tests
- claim-support and review payload tests
- regression tests for graph-projection metadata and support summaries

Suggested focused validation:

- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_review_api.py -q`
- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py tests/test_claim_support_hooks.py tests/test_legal_authority_hooks.py -q`

## M3: Support-Quality and Validation Layer

Goal:

- layer GraphRAG scoring and formal validation on top of the stabilized parse, fact, and graph substrates

Status:

- core proof-aware review, contradiction diagnostics, reasoning diagnostics, and reasoning-aware follow-up planning are already in place; the remaining work is to deepen GraphRAG and replace placeholder-heavy logic-adapter behavior with grounded validation workflows

Primary files:

- `integrations/ipfs_datasets/graphrag.py`
- `integrations/ipfs_datasets/logic.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `complaint_phases/phase_manager.py`
- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`

Checklist:

- [ ] GraphRAG exposes ontology-quality or support-path scoring in a mediator-consumable shape
- [x] support overviews surface quality signals rather than raw support counts alone
- [x] proof-gap and contradiction outputs are persisted or exposed through review surfaces
- [x] follow-up planning consumes proof-decision and reasoning-gap signals from the current validation layer
- [ ] logic adapter wraps text-to-predicate, contradiction, and proof workflows behind stable normalized outputs rather than placeholder-heavy capability output
- [ ] GraphRAG-driven graph-quality or ontology-gap signals are consumable by follow-up planning
- [ ] at least one complaint type has explicit predicate templates and grounded fact mapping

Acceptance criteria:

- complaint-generator can surface support strength, missing premises, and contradictions before drafting for at least one complaint workflow

Validation:

- focused tests for GraphRAG scoring outputs
- focused tests for logic adapter degraded mode
- mediator tests for contradiction and proof-gap payloads

Suggested validation target:

- add dedicated focused tests before implementation lands; do not rely on broad suites alone for first GraphRAG or proof-work slices

## M4: Operator Productization

Goal:

- turn the current review payloads into a fuller operator-facing support workspace

Status:

- the repo already has review payloads, compact coverage summaries, lineage-aware follow-up history/plan/execution summaries, and a dashboard round-trip flow; the remaining work is richer drilldown and support-packet productization

Primary files:

- `applications/review_api.py`
- `mediator/mediator.py`
- `mediator/web_evidence_hooks.py`
- `docs/APPLICATIONS.md`
- `docs/PAYLOAD_CONTRACTS.md`
- future application or UI surfaces to be selected during implementation

Checklist:

- [ ] review payloads expose full support packets with evidence, authority, fact, provenance, and graph-support detail
- [x] contradiction and missing-support summaries are operator-visible
- [ ] timeline, archive-history, and graph-trace drilldowns are operator-visible
- [ ] queued acquisition and enrichment state can be inspected from review surfaces
- [ ] long-running archive, graph, and validation work can move into explicit background workflows where necessary
- [x] documentation for review and execution routes is aligned with actual payloads and compatibility behavior

Acceptance criteria:

- operators can inspect coverage, contradictions, provenance, and queued enrichment work without consulting raw tables
- operators can trace a support decision back to passages, artifacts, archive captures, and graph or validation outputs

Validation:

- focused review API tests
- payload contract updates
- application docs updates

Suggested focused validation:

- `./.venv/bin/python -m pytest tests/test_review_api.py -q`
- `./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py tests/test_claim_support_hooks.py tests/test_review_api.py -q`

## M5: Drafting and Filing Readiness

Goal:

- make the formal complaint builder and export APIs consume support packets, authority-treatment state, graph traces, and validation diagnostics before artifact generation

Status:

- in progress; the formal complaint package now exposes drafting-readiness payloads, the browser workflow renders section and claim-level filing warnings, and operators can navigate between `/document` and `/claim-support-review` with claim context preserved

Primary files:

- `document_pipeline.py`
- `applications/document_api.py`
- `templates/document.html`
- `mediator/mediator.py`
- `mediator/claim_support_hooks.py`
- `claim_support_review.py`
- `docs/APPLICATIONS.md`
- `docs/PAYLOAD_CONTRACTS.md`

Checklist:

- [x] document payloads expose section-level support or warning objects for major complaint sections
- [x] drafting surfaces can distinguish unsupported facts from adverse authority and from proof-gap warnings
- [x] artifact metadata can point back to support provenance or review summaries where appropriate
- [x] browser drafting workflows can surface filing-readiness status without requiring raw JSON inspection
- [x] degraded mode remains usable when treatment, graph, or logic enrichments are unavailable
- [x] drafting payload changes are documented and covered by focused tests

Acceptance criteria:

- at least one complaint workflow can emit a filing draft with explicit readiness and warning metadata tied to source-backed support state
- operators can move from support review into the drafting workflow without losing provenance, authority, or validation context

Validation:

- focused document-pipeline tests
- focused review-surface tests for the browser builder
- payload contract and application-doc updates

Suggested focused validation:

- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q`
- `./.venv/bin/python -m pytest tests/test_claim_support_review_template.py -q`
- `./.venv/bin/python -m pytest tests/test_review_api.py -q`
- `./.venv/bin/python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py tests/test_mediator.py tests/test_cli_commands.py tests/test_formal_document_pipeline.py -q`

## Cross-Milestone Guardrails

- [ ] every milestone lands with at least one mediator-visible consumer
- [ ] every milestone lands with focused tests for touched payloads or adapters
- [ ] every milestone keeps degraded mode supported
- [ ] every externally visible payload change is documented in `docs/PAYLOAD_CONTRACTS.md`
- [ ] no milestone bypasses the adapter boundary to call `ipfs_datasets_py` internals directly from production code

## Recommended Execution Order

1. M0
2. M1
3. M2
4. M3
5. M4
6. M5

## Exit Condition

The integration can be treated as mature when complaint-generator can acquire, archive, parse, organize, validate, and review legal support through one provenance-preserving workflow across full, partial, and degraded runtime modes.