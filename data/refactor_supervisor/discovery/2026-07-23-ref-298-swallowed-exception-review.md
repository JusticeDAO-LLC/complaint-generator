# REF-298 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/test_error_boundary_comprehensive.py:109`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-298-codebase-scan-d2e342d22946.md`

## Decision

The domain-case test wrapped context construction, generator construction, and
ontology generation in a broad exception handler. Every exception was silently
accepted, so the test could pass without producing an ontology and did not
enforce its stated graceful-handling contract.

Uppercase domain labels are supported by the generator. The broad handler has
therefore been removed so unexpected failures retain their original traceback.
The test now requires a dictionary result and verifies that the supplied
uppercase domain is preserved in both the ontology's top-level domain and its
metadata. This covers the observable case-handling behavior instead of merely
checking that a non-null value was returned.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/test_error_boundary_comprehensive.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/test_error_boundary_comprehensive.py::TestInvalidContextHandling::test_domain_case_sensitivity -q
```

Validation results:

- PASS — `python3 -m py_compile tests/test_error_boundary_comprehensive.py`
- PASS — focused domain-case regression (1 passed)
- PASS — complete error-boundary module (27 passed)

Pytest emitted the repository's existing `pytest-asyncio` configuration
deprecation warning; this change introduced no test warnings.
