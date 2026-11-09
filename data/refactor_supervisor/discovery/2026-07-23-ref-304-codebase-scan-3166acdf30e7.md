# REF-304 Codebase Scan Finding

Date: 2026-07-23
Fingerprint: 3166acdf30e7fc8bf2cc1068b6a96ffe60c4064a
Kind: swallowed_exception
Source: tests/test_llm_router_circuit_breaker.py:115
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

The finding identified a real false-positive test path. The half-open probe
caught and discarded every exception from the router, so the test could pass
when the probe raised an unrelated error and did not verify the circuit
breaker's failed-probe behavior.

The test now requires the probe to propagate the expected wrapped service error,
verifies that the half-open state permits exactly one backend call, and confirms
that the failed probe returns the circuit to `OPEN`. Unexpected exception
messages and missing failures therefore fail the test instead of being silently
accepted.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/test_llm_router_circuit_breaker.py
```

Validation results:

- PASS — `python3 -m py_compile tests/test_llm_router_circuit_breaker.py`
- PASS — supervisor task parser loaded the bundle (1 task, `REF-304`)
- PASS — `git diff --check`
- SKIP — the focused pytest case was collected but excluded by the
  repository's default LLM-test policy
