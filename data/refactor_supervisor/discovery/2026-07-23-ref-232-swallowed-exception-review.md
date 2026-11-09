# REF-232 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/conftest.py:289`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-232-codebase-scan-3e17c950c7eb.md`

## Decision

The flagged boundary reads each collected test module to infer whether it needs
LLM, network, or heavy-resource opt-ins. The previous broad handler silently
converted every read or classifier failure into `(False, False, False)`. This
could run an unreadable test without its required gates, and it concealed
implementation defects in the keyword classifier itself.

Classification now has an explicit top-level helper that catches only
filesystem `OSError`s. An unreadable source emits a `PytestCollectionWarning`
with the path and exception details and fails closed by requiring all three
opt-ins. Failures after the file is read propagate during collection so they
cannot silently weaken test gating.

## Focused Validation

`tests/test_ref_232_conftest_classification.py` verifies normal keyword
classification, including reserved example URLs; verifies that a read failure
warns and requires every opt-in; and verifies that an unexpected classifier
failure propagates.

Required syntax validation:

```text
python3 -m py_compile tests/conftest.py
```

Validation results:

- PASS — `python3 -m py_compile tests/conftest.py`
- PASS — `python3 -m pytest tests/test_ref_232_conftest_classification.py -q`
  (3 passed; one unrelated pytest-asyncio configuration deprecation warning)
