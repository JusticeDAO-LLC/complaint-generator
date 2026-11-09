# REF-121 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/legal.py:98`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-121-codebase-scan-11b094c1fe49.md`

## Decision

The direct `embed_text` call is followed by an embeddings-router compatibility
fallback. Retaining that fallback is necessary because supported provider
versions expose different embedding entry points. The broad exception handler
was nevertheless a defect: it silently discarded provider errors and malformed
vectors, making a degraded request indistinguishable from an unavailable
embedding backend.

The fallback now logs the original exception and adds a structured
`direct_embedding_failure` entry to the existing legal-search diagnostics. The
entry identifies the failed backend, exception type and message, and selected
fallback. It does not include the legal query text. Both state-law search paths
pass their request diagnostics into the query-vector builder, so callers can
inspect the degradation through `get_last_legal_search_diagnostic`.

## Focused Validation

`tests/test_ref_121_legal_query_vector.py` verifies that a failed direct
embedding remains observable while the router fallback returns a normalized
vector. It also verifies that a successful direct embedding produces neither a
warning nor a failure diagnostic and does not instantiate the fallback router.

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/legal.py`
- PASS — `python3 -m pytest tests/test_ref_121_legal_query_vector.py -q`
  (2 passed)
- PASS — `python3 -m pytest tests/test_ipfs_adapter_layer.py -k 'search_state_laws or search_state_administrative_rules' -q`
  (5 passed, 65 deselected)
