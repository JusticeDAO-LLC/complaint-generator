# REF-231 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/conftest.py:223`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-231-codebase-scan-dbed21531702.md`

## Decision

The flagged boundary preloads the vendored `ipfs_datasets_py` package after
pytest has corrected its import paths. Preloading is a compatibility aid: an
unavailable optional import should not prevent unrelated tests from collecting,
but the previous broad handler silently discarded every initializer failure.
That made a missing dependency indistinguishable from corrupt package state or
an implementation defect.

The preload now catches only `ImportError` and emits a `PytestConfigWarning`
containing the expected package location, exception type, and message. Other
initializer failures propagate so pytest reports the defect at configuration
time instead of concealing it until a later import.

## Focused Validation

`tests/test_ref_231_conftest_preload.py` verifies that an unavailable optional
import remains non-fatal and produces an actionable configuration warning. It
also verifies that a non-import exception raised by package initialization is
not swallowed.

Required syntax validation:

```text
python3 -m py_compile tests/conftest.py
```

Validation results:

- PASS — `python3 -m py_compile tests/conftest.py`
- PASS — `python3 -m pytest tests/test_ref_231_conftest_preload.py -q`
  (2 passed)
