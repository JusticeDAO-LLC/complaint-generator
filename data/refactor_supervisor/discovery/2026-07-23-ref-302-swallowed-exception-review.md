# REF-302 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/test_error_boundary_comprehensive.py:357`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-302-codebase-scan-210a7a9f4f81.md`

## Decision

The relationships-invariant test caught every exception raised while generating
an ontology or checking its result. Because `AssertionError`, `KeyError`, and
`TypeError` are all subclasses of `Exception`, the test passed when generation
failed, the result was not a mapping, the `relationships` field was absent, or
the field had the wrong type. It could therefore complete without validating
any of its three inputs.

The scanned inputs are supported edge cases that are expected to produce a
well-formed ontology. The broad handler has been removed, so each call must now
return a dictionary whose `relationships` field is a list. Unexpected
generation errors and invariant failures retain their original traceback and
fail the test. The local variable and docstring now describe the values as
edge-case inputs rather than invalid inputs, matching the generator contract.
Earlier changes in this file shifted the scanned handler from its original line
357 to line 355 before this review.

The neighboring swallowed handler in
`TestGracefulDegradation.test_degradation_with_corrupted_input` is outside this
work item and remains available for its own supervisor finding.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/test_error_boundary_comprehensive.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/test_error_boundary_comprehensive.py::TestInvariantMaintenance::test_relationships_always_list -q
```

Validation results:

- PASS — `python3 -m py_compile tests/test_error_boundary_comprehensive.py`
- PASS — focused relationships-invariant regression (1 passed)
- PASS — complete error-boundary module (27 passed)

Pytest emitted the repository's existing `pytest-asyncio` configuration
deprecation warning; this change introduced no test warnings.
