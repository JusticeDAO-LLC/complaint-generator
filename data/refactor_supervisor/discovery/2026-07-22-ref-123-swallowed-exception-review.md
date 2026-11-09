# REF-123 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/legal.py:662`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-123-codebase-scan-6e1fbcf47fed.md`

## Decision

The Hugging Face Federal Register index is a preferred search backend, followed
by the upstream Federal Register API as an intentional availability fallback.
Retaining that fallback is necessary, but the broad exception handler was a
defect: it silently discarded index runtime failures and made them
indistinguishable from an index that successfully returned no matches.

The search now emits a warning with the original exception and records a
structured `hf_index_failure` entry in the existing legal-search diagnostics.
The entry identifies the failed backend, exception type and message, and the
selected fallback. Diagnostics also record every attempted backend, the final
selected backend, and the final status for successful, empty, and unavailable
fallback paths. Callers can inspect the result through
`get_last_legal_search_diagnostic("search_federal_register")` without changing
the existing search return shape.

## Focused Validation

`tests/test_ref_123_federal_register_fallback.py` verifies that a failed index
search remains observable while the upstream API fallback still returns
normalized records. It also verifies that a successful preferred-index search
does not warn, does not report a failure, and does not invoke the fallback API.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/legal.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/legal.py`
- PASS — `python3 -m pytest tests/test_ref_123_federal_register_fallback.py -q`
  (2 passed)
- PASS — `python3 -m pytest tests/test_ipfs_adapter_layer.py::test_search_federal_register_normalizes_documents tests/test_ipfs_adapter_layer.py::test_search_federal_register_prefers_huggingface_index_results -q`
  (2 passed)
