# REF-129 Swallowed Exception Review

Date: 2026-07-22
Source finding: `integrations/ipfs_datasets/loader.py:353`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-129-codebase-scan-992a753ac855.md`

## Decision

The flagged handler is the explicit failure boundary for optional provider
imports. Provider module initialization may raise any ordinary `Exception`, not
only an `ImportError`, and an unavailable provider must degrade the adapter
instead of preventing the application from importing. The exception was not
discarded: it was converted into the loader's stable `ImportFailure` result.
Process-control exceptions outside the `Exception` hierarchy continue to
propagate.

Review uncovered a related contract violation immediately before the flagged
handler. `ensure_import_paths` executes a vendored package's `__init__.py`, but
it ran outside the retry `try` block; an ordinary initialization failure could
therefore escape from a function whose contract is to return optional-import
failures. Vendored path preparation and the second import now share the explicit
conversion boundary. The returned diagnostic preserves the final failure's type
and missing-module name while adding the initial `ModuleNotFoundError` that
triggered recovery, so callers can observe both attempts.

## Focused Validation

`tests/test_ref_129_ipfs_loader_retry.py` verifies that path-preparation and
second-import failures are returned as structured diagnostics with the initial
failure context. It also confirms that `KeyboardInterrupt` is not intercepted.

Required syntax validation:

```text
python3 -m py_compile integrations/ipfs_datasets/loader.py
```

Validation results:

- PASS — `python3 -m py_compile integrations/ipfs_datasets/loader.py`
- PASS — `python3 -m pytest tests/test_ref_129_ipfs_loader_retry.py -q`
  (3 passed)
- PASS — focused existing loader regression suite
  (15 passed across `test_ipfs_adapter_types.py` and
  `test_ipfs_datasets_loader.py`)
