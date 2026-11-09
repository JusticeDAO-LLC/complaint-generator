# REF-299 Codebase Scan Finding

Date: 2026-07-23
Fingerprint: ca7e00ffc043730bee0761880e61927b6b61d8a5
Kind: swallowed_exception
Source: tests/test_error_boundary_comprehensive.py:139
Priority: P1
Track: quality

## Evidence

```text
except Exception:
```

## Suggested Handling

Review the finding in context, decide whether it represents a bug, missing test,
maintenance risk, or false positive, and land a small fix with validation. If the
finding is a false positive, document why in the changed code or discovery notes
so the supervisor does not keep re-adding the same work.

## Resolution

The finding identified a real false-positive test path. The recovery test caught
and discarded every exception from an empty-text generation call, allowing the
test to continue without proving either that a failure occurred or that the
generator recovered from it. Empty text is a supported input and normally returns
a valid empty ontology, so it was not a reliable error trigger.

The test now injects a deterministic failure into the first entity-extraction
attempt and asserts that the expected `RuntimeError` propagates. It then uses the
same generator for a second extraction, verifies that both attempts occurred, and
checks the recovered result against the required ontology structure.

## Focused Validation

The corrected test explicitly covers both the initial failure and the successful
recovery path. Required syntax validation:

```text
python3 -m py_compile tests/test_error_boundary_comprehensive.py
```

Validation results:

- PASS — `python3 -m py_compile tests/test_error_boundary_comprehensive.py`
- PASS — `python3 -m pytest tests/test_error_boundary_comprehensive.py::TestRecoveryFromErrors::test_recovery_after_error -q`
  (1 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
- PASS — `python3 -m pytest tests/test_error_boundary_comprehensive.py -q`
  (27 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
- PASS — supervisor task parser loaded the bundle (4 tasks, including `REF-299`)
