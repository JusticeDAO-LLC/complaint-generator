# REF-223 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/legal_authority_hooks.py:1264`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-223-codebase-scan-6e8c1ae9d978.md`

## Decision

The all-sources search fans out across independent web-archive domains. A
failure from one optional domain should remain non-fatal so authorities found
through later domains are still returned. The flagged handler was defective
because it silently discarded the exception, leaving callers and operators
unable to distinguish complete searches from degraded partial searches.

The domain boundary continues after an exception but now emits the established
`legal_authority_search_error` event with the search type, failed domain, query,
exception type, and exception message. This preserves best-effort search
semantics while making every partial failure attributable and observable.

## Focused Validation

`tests/test_ref_223_web_archive_failure_fallback.py` verifies that a failed
archive domain records actionable structured diagnostics, that the remaining
domains are still queried, and that results from a healthy later domain are
preserved.

Required syntax validation:

```text
python3 -m py_compile mediator/legal_authority_hooks.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/legal_authority_hooks.py`
- PASS — `python3 -m pytest tests/test_ref_223_web_archive_failure_fallback.py -q`
  (1 passed)
- PASS — `python3 -m pytest tests/test_legal_authority_hooks.py -q`
  (30 passed)
