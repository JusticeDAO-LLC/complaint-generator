# REF-301 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/test_error_boundary_comprehensive.py:341`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-301-codebase-scan-a988f6f70a4f.md`

## Decision

The entities-invariant test caught every exception raised while generating an
ontology or checking its result. That handler also caught `AssertionError`, so
the test passed when ontology generation failed, the result was not a mapping,
the `entities` field was absent, or the field had the wrong type. If all three
iterations failed, the test completed without making a successful assertion.

The scanned inputs are supported edge cases that are exercised as successful
calls elsewhere in the same module. No exception is expected for them, so the
broad handler has been removed. Each call must now return a dictionary whose
`entities` field is a list. Unexpected generation errors and invariant failures
retain their original traceback and fail the test. The local variable and
docstring now describe these values as edge-case inputs rather than invalid
inputs, matching the generator contract.

The neighboring swallowed handler in
`TestInvariantMaintenance.test_relationships_always_list` is a separate
supervisor finding (REF-302) and remains outside this work item.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/test_error_boundary_comprehensive.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/test_error_boundary_comprehensive.py::TestInvariantMaintenance::test_entities_always_list -q
```

Validation results:

- PASS — `python3 -m py_compile tests/test_error_boundary_comprehensive.py`
- PASS — focused entities-invariant regression (1 passed)
- PASS — complete error-boundary module (27 passed)

Pytest emitted the repository's existing `pytest-asyncio` configuration
deprecation warning; this change introduced no test warnings.
