# REF-230 Swallowed Exception Review

Date: 2026-07-22
Source finding: `test_pipeline_error_recovery.py:402`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-230-codebase-scan-e61544625f39.md`

## Decision

The null-byte resilience test exercises the pipeline's rule-based, in-memory
text extraction path. That path accepts a Python string directly and has no
framework boundary for which rejecting an embedded NUL is part of the contract.
The flagged catch was therefore defective: it treated every exception from
pipeline construction, extraction, evaluation, or result validation as an
acceptable outcome and allowed the test to pass without validating recovery.

The test now selects rule-based operation explicitly, lets unexpected failures
propagate to pytest, and verifies that the returned result includes an ontology.
This makes the stated resilience behavior executable while keeping the test
independent of optional LLM services.

## Focused Validation

`test_pipeline_error_recovery.py::TestPipelineInputValidationAndSanitization::test_pipeline_with_null_bytes_in_text`
now fails on any pipeline exception and verifies the successful result shape for
text containing an embedded null byte.

Required syntax validation:

```text
python3 -m py_compile test_pipeline_error_recovery.py
```

Validation results:

- PASS — `python3 -m py_compile test_pipeline_error_recovery.py`
- PASS — `python3 -m pytest test_pipeline_error_recovery.py::TestPipelineInputValidationAndSanitization::test_pipeline_with_null_bytes_in_text -q`
  (1 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
