# REF-229 Codebase Scan Finding

Date: 2026-07-23
Fingerprint: 75935cbef32fb16065bf2da6d88f042c31ae5496
Kind: swallowed_exception
Source: scripts/run_claim_support_review_regression.py:75
Priority: P1
Track: runtime

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

The finding identified a real cleanup and observability defect in the optional
Playwright availability probe. A failure from `playwright.stop()` was discarded,
allowing the regression runner to continue even though the Playwright driver
could still be running. The cleanup handler also referenced `playwright` when
`sync_playwright().start()` failed before assigning it; the resulting
`UnboundLocalError` was silently discarded by the same handler.

The probe now initializes the Playwright handle before startup and calls
`stop()` only after successful startup. Shutdown failures propagate to the CLI,
so leaked or corrupted driver state cannot be reported as a successful probe.
Import, startup, and executable-path probe failures retain the established
`False` result because those cases mean browser-backed tests are unavailable.

## Focused Validation

`tests/test_run_claim_support_review_regression_cli.py` verifies that a shutdown
failure propagates unchanged and that a startup failure returns `False` without
attempting cleanup on an uninitialized handle.

Required syntax validation:

```text
python3 -m py_compile scripts/run_claim_support_review_regression.py
```

Validation results:

- PASS — `python3 -m py_compile scripts/run_claim_support_review_regression.py`
- PASS — `python3 -m pytest tests/test_run_claim_support_review_regression_cli.py -q`
  (11 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
