# REF-303 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/test_error_boundary_comprehensive.py:408`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-303-codebase-scan-8330728218c4.md`

## Decision

The corrupted-input degradation test caught every exception raised while
generating an ontology or checking its result. Because `AssertionError` is an
`Exception`, the handler also hid assertion failures. The test therefore passed
when ontology generation raised, returned an unexpected type, or produced an
invalid result. It could even complete successfully without validating any of
the three inputs.

All scanned values are strings accepted by the generator's public API, and the
test explicitly promises graceful degradation for them. The broad handler has
therefore been removed. Each call must now complete without raising and return a
dictionary containing the generator's required `entities`, `relationships`, and
`metadata` fields with their documented container types. Unexpected generation
errors and malformed output retain their original traceback and fail the test.

The neighboring swallowed handler in
`TestInvariantMaintenance.test_relationships_always_list` is tracked by the
separate supervisor finding REF-302 and remains outside this work item.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/test_error_boundary_comprehensive.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/test_error_boundary_comprehensive.py::TestGracefulDegradation::test_degradation_with_corrupted_input -q
```

Validation results:

- PASS — `python3 -m py_compile tests/test_error_boundary_comprehensive.py`
- PASS — focused corrupted-input regression (1 passed)
- PASS — complete error-boundary module (27 passed)

Pytest emitted the repository's existing `pytest-asyncio` configuration
deprecation warning; this change introduced no test warnings.
