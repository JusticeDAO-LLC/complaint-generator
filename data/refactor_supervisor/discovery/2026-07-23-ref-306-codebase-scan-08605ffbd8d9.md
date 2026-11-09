# REF-306 Codebase Scan Finding

Date: 2026-07-23
Fingerprint: 08605ffbd8d9b23a386f9b818e78094bf1c2ad1d
Kind: swallowed_exception
Source: tests/test_website_cohesion_playwright.py:407
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

The readiness poll intentionally tolerates connection failures while Uvicorn
starts, but its blanket handler also caught unrelated test and fixture defects
and discarded the only useful startup failure detail.

The poll now retries only `requests.RequestException`, while unexpected
exceptions propagate immediately. It retains the latest request failure or HTTP
status and includes that detail in the timeout error; request failures are also
preserved as the exception cause. Readiness polling is covered by the fixture's
cleanup boundary so every exit path stops the Uvicorn thread. The fixture
therefore remains tolerant of normal startup timing without hiding programming
errors, leaking a server, or producing an unexplained timeout.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/test_website_cohesion_playwright.py
```

Validation results:

- PASS — `python3 -m py_compile tests/test_website_cohesion_playwright.py`
- PASS — direct `_serve_app` validation started a real FastAPI health endpoint,
  verified a successful readiness check, proved that an unexpected polling
  `ValueError` propagates, and confirmed that no server thread leaked
- PASS — supervisor task parser loaded the bundle as one task (`REF-306`)
- PASS — `git diff --check`
- PASS — `python3 -m pytest -q --run-llm
  tests/test_website_cohesion_playwright.py::test_legacy_site_pages_share_profile_state_and_navigation`
  (1 passed)
- SKIP — without `--run-llm`, the same focused case was collected but excluded
  by the repository's default LLM-test policy
