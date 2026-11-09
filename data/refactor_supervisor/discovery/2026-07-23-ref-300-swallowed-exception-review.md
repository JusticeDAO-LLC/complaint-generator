# REF-300 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/test_error_boundary_comprehensive.py:159`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-300-codebase-scan-82bd9c822ff8.md`

## Decision

The multiple-sequential-input test passed whenever ontology generation raised
any exception because its broad handler silently continued to the next input.
Consequently, all four edge-case calls could fail and the test would still only
check the final ordinary call. The inputs are supported by the generator's
graceful-input contract and are already exercised individually elsewhere in the
module, so no exception is expected here.

The handler has been removed. Each sequential call on the same generator
instance must now return a dictionary containing the required `entities`,
`relationships`, and `metadata` fields, as must the ordinary call that follows.
Unexpected failures therefore retain their original traceback, and the test now
verifies that processing edge-case inputs does not corrupt generator state. The
test terminology was also changed from "invalid" to "edge-case" inputs to match
the supported behavior. Earlier changes in this file shifted the scanned
handler from its original line 159 to line 156 before this review.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/test_error_boundary_comprehensive.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/test_error_boundary_comprehensive.py::TestRecoveryFromErrors::test_multiple_sequential_errors -q
```

Validation results:

- PASS — `python3 -m py_compile tests/test_error_boundary_comprehensive.py`
- PASS — focused sequential edge-case regression (1 passed)
- PASS — complete error-boundary module (27 passed)

Pytest emitted the repository's existing `pytest-asyncio` configuration
deprecation warning; this change introduced no test warnings.
