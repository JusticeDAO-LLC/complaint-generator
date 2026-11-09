# REF-130 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/loader.py:397`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-130-codebase-scan-9c858e22373c.md`

## Decision

The flagged handler is not a swallowed-exception path. It is the public failure
boundary for optional provider imports: an unavailable or misconfigured
provider must degrade the adapter without making `integrations.ipfs_datasets`
itself unimportable. Provider module initialization executes arbitrary Python
and can raise any ordinary `Exception`, so narrowing the handler to
`ImportError` would violate that availability contract.

The caught exception is converted into the stable `ImportFailure` result. That
result preserves the requested module, optional attribute, concrete exception
type, message, and `ModuleNotFoundError.name`; downstream capability status
payloads expose those values as structured diagnostics. The boundary catches
`Exception`, not `BaseException`, so `KeyboardInterrupt`, `SystemExit`, and
other process-control exceptions continue to propagate. The loader also
restores `sys.path` in a `finally` block before returning a failure.

An explanatory comment now records this policy at the flagged handler so a
future maintainer does not narrow or broaden it based on the catch syntax alone.

## Focused Validation

`tests/test_ref_130_ipfs_loader_failure_boundary.py` verifies that ordinary
provider failures retain all public diagnostic fields, nested missing-module
metadata is preserved without an inappropriate vendored-package retry,
process-control exceptions propagate, and a failing provider cannot leak
`sys.path` mutations.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/loader.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/loader.py`
- PASS — `python3 -m pytest tests/test_ref_130_ipfs_loader_failure_boundary.py -q`
  (5 passed as part of the combined loader run)
- PASS — existing loader regression suite
  (18 passed across `test_ref_129_ipfs_loader_retry.py`,
  `test_ipfs_adapter_types.py`, and `test_ipfs_datasets_loader.py`)
