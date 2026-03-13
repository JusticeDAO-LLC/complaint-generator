# Document Generation Agentic Optimization Plan

This plan focuses on the next slices for improving formal complaint generation after knowledge graph, support-packet, and drafting-readiness data are already available.

## Current Baseline

- [document_pipeline.py](../document_pipeline.py) can run an optional optimization step before rendering artifacts.
- [document_optimization.py](../document_optimization.py) provides the current actor/critic loop and optional IPFS trace persistence.
- [applications/document_api.py](../applications/document_api.py) exposes optimization flags on `/api/documents/formal-complaint`.
- [tests/test_document_pipeline.py](../tests/test_document_pipeline.py) covers the enabled optimization path.

The current seam is useful, but it is still a lightweight text optimization layer. It does not yet optimize the full filing packet or use the richer `ipfs_datasets_py` optimizer surfaces as the backbone of the loop.

## Capability Map

| Need | `ipfs_datasets_py` capability | Current or future local consumer |
|---|---|---|
| Rewrite and critique | `llm_router`, `optimizers.agentic` | `integrations.ipfs_datasets.llm`, `document_optimization.py` |
| Ranked support selection | `embeddings_router` | `integrations.ipfs_datasets.vector_store`, `document_optimization.py` |
| Trace persistence | `ipfs_backend_router` | `integrations.ipfs_datasets.storage` |
| Coverage and gap signals | `optimizers.graphrag` | future `integrations.ipfs_datasets.graphrag` integration |

The adapter boundary under `integrations/ipfs_datasets/*` should remain the only production entrypoint into these capabilities.

## Main Gaps

1. Target selection now uses grounded support facts and critic scoring, but it still operates on a lightweight local heuristic rather than richer contradiction, proof-gap, or authority-treatment signals.
2. The loop optimizes complaint text, but not the full filing packet, including affidavit, certificate of service, and exhibits.
3. The critic output is not yet normalized against contradiction, proof, or adverse-authority signals.
4. Embedding retrieval is still opportunistic rather than a fully repeatable, stored retrieval session.
5. IPFS persistence stores a trace, but not a reusable optimization session object.

## Delivery Slices

### Slice 1: Support-aware target selection

Primary files:

- [document_optimization.py](../document_optimization.py)
- [document_pipeline.py](../document_pipeline.py)
- [mediator/mediator.py](../mediator/mediator.py)

Work:

- prioritize sections using claim-level warnings and unresolved elements
- attach source-family counts and claim support summaries to critic inputs
- emit `optimized_sections` in the report payload

Status:

- implemented in the current baseline using grounded claim-support facts, section scoring, and `optimized_sections` in `document_optimization`

### Slice 2: Artifact-aware optimization

Primary files:

- [document_pipeline.py](../document_pipeline.py)
- [document_optimization.py](../document_optimization.py)
- [mediator/formal_document.py](../mediator/formal_document.py)

Work:

- score affidavit completeness and exhibit consistency
- detect exhibit-reference mismatches before render
- let the actor revise affidavit and service sections directly

### Slice 3: Repeatable retrieval and traceability

Primary files:

- [document_optimization.py](../document_optimization.py)
- `integrations/ipfs_datasets/vector_store.py`

Work:

- store ranked context candidates per section
- preserve provenance metadata for selected snippets
- distinguish embedding ranking from lexical fallback in the trace

### Slice 4: Stronger IPFS session persistence

Primary files:

- [document_optimization.py](../document_optimization.py)
- `integrations/ipfs_datasets/storage.py`

Work:

- persist accepted and rejected revisions, score history, and selected support context
- return a stable optimization session identifier in `document_optimization`

### Slice 5: Closer alignment with `optimizers.agentic`

Primary files:

- [document_optimization.py](../document_optimization.py)
- `integrations/ipfs_datasets/capabilities.py`

Work:

- prefer upstream optimizer abstractions when available
- preserve the local fallback path when upstream capabilities are absent or incompatible
- keep the public report contract stable across both modes

## Acceptance Criteria

1. The mediator can choose sections from support gaps, not only thin text.
2. The actor can revise complaint text plus affidavit/service sections from grounded support.
3. The report exposes section history and selected support context.
4. IPFS persistence stores a reusable optimization session artifact.
5. Router-unavailable degraded mode remains clean and test-covered.

## Recommended Next Code Slice

Implement Slice 2 next. The current seam already proves the optimizer can run with support-aware section selection, so the highest-leverage next step is expanding optimization beyond complaint body text into affidavit, service, and exhibit consistency.
