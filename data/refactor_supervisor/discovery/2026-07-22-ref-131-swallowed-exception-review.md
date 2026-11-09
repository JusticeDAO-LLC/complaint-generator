# REF-131 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/loader.py:407`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-131-codebase-scan-7a4409f5374e.md`

## Decision

`import_attr_optional` previously converted every ordinary exception raised by
`getattr` into an `ImportFailure`. Python modules may implement `__getattr__`,
so attribute resolution can execute provider code and raise runtime,
configuration, or dependency errors. Treating all of those failures as a
missing optional capability concealed unexpected provider defects.

The handler now catches only `AttributeError`, Python's explicit signal that an
attribute is absent. A genuinely missing optional attribute still produces the
stable structured diagnostic expected by adapter callers. Any other failure
from dynamic attribute resolution propagates to the caller and can be handled
at the appropriate operation boundary without being mislabeled as capability
unavailability.

## Focused Validation

`tests/test_ref_131_ipfs_loader_attr.py` verifies successful lookup and the
structured missing-attribute result. It also uses a module-level `__getattr__`
that raises `RuntimeError` to confirm unexpected provider failures are no longer
swallowed.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/loader.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/loader.py`
- PASS — focused loader regression suite (7 passed across
  `test_ref_131_ipfs_loader_attr.py`, `test_ref_129_ipfs_loader_retry.py`, and
  `test_ipfs_datasets_loader.py`)
- PASS — broader IPFS adapter regression suite (87 passed across
  `test_ipfs_adapter_layer.py` and `test_ipfs_adapter_types.py`)
