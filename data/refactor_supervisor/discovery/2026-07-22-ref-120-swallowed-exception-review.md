# REF-120 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/graphrag.py:128`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-120-codebase-scan-1026e36dfbd6.md`

## Decision

The flagged handler treated every `OntologyGenerator` constructor failure as an
absent backend. It discarded the exception and caused `build_ontology` to return
`unavailable`, even though the provider class had imported successfully. This
made dependency and configuration failures indistinguishable from a provider
that was not installed, and could omit the failure reason entirely.

`create_ontology_generator` now returns `None` only when the optional provider
class is genuinely unavailable. Constructor failures propagate from the factory
instead of being swallowed. The `build_ontology` adapter boundary catches those
failures and returns its canonical structured `error` response, preserving the
exception message and accurately reporting that the backend is available but
its operation failed.

## Focused Validation

`tests/test_ipfs_adapter_layer.py` verifies both sides of the contract: direct
factory callers receive constructor failures, while `build_ontology` converts
the same failure into observable error metadata rather than an unavailable
response.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/graphrag.py
```
