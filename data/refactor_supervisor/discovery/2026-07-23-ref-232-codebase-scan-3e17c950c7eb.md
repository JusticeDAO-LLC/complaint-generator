# REF-232 Codebase Scan Finding

Date: 2026-07-23
Fingerprint: 3e17c950c7ebb0a993a132de91068e9760c0e458
Kind: swallowed_exception
Source: tests/conftest.py:289
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
